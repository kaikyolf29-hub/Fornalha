# Fornalha: instala um worker de placa (TRELLIS.2, UniRig ou HY-Motion) numa pasta
# só dele, com ambiente Python próprio. Não instala o nvdiffrast nem o nvdiffrec.
#   python instalar.py <trellis2|unirig|hy-motion> <pasta> [--pular-pesos]
# Escreve o progresso em <pasta>/instalacao.log e, no fim, <pasta>/instalacao.json.
import json
import os
import platform
import shutil
import subprocess
import sys
import time

WINDOWS = platform.system() == "Windows"
TORCH = ["torch==2.6.0", "torchvision==0.21.0"]
INDICE_TORCH = "https://download.pytorch.org/whl/cu124"
PYG = "https://data.pyg.org/whl/torch-2.6.0+cu124.html"

WORKERS = {
    "trellis2": {
        "repo": "https://github.com/microsoft/TRELLIS.2.git",
        "pip": ["pillow", "imageio", "imageio-ffmpeg", "tqdm", "easydict", "opencv-python-headless", "ninja", "trimesh",
                "transformers", "huggingface_hub", "safetensors", "scipy", "numpy<2.3"],
        "precisa_nvcc": True,
    },
    "unirig": {
        "repo": "https://github.com/VAST-AI-Research/UniRig.git",
        "pip": ["spconv-cu124", "numpy<2.3"],
        "requirements": "requirements.txt",
        "pyg": ["torch_scatter", "torch_cluster"],
        "precisa_bash": True,
    },
    "hy-motion": {
        "repo": "https://github.com/Tencent-Hunyuan/HY-Motion-1.0.git",
        "pip": ["huggingface_hub", "numpy<2.3"],
        "requirements": "requirements.txt",
        "pesos": ("tencent/HY-Motion-1.0", os.path.join("ckpts", "tencent")),
    },
}


class Instalador:
    def __init__(self, worker, pasta):
        self.worker = worker
        self.cfg = WORKERS[worker]
        self.pasta = os.path.abspath(pasta)
        os.makedirs(self.pasta, exist_ok=True)
        self.log = open(os.path.join(self.pasta, "instalacao.log"), "a", encoding="utf-8")
        self.repo = os.path.join(self.pasta, "repo")
        self.venv = os.path.join(self.pasta, "venv")
        self.python = os.path.join(self.venv, "Scripts" if WINDOWS else "bin", "python.exe" if WINDOWS else "python")

    def etapa(self, texto):
        linha = f"[{time.strftime('%H:%M:%S')}] {texto}"
        print(linha, flush=True)
        self.log.write(linha + "\n")
        self.log.flush()

    def rodar(self, cmd, cwd=None, env=None):
        self.etapa("$ " + " ".join(cmd))
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
        for linha in p.stdout:
            self.log.write(linha)
        self.log.flush()
        if p.wait() != 0:
            raise RuntimeError(f"falhou (código {p.returncode}): {' '.join(cmd[:4])}… veja {self.log.name}")

    def pip(self, pacotes, *extra):
        if pacotes:
            self.rodar([self.python, "-m", "pip", "install", "--upgrade", *extra, *pacotes])

    def conferir(self):
        if shutil.which("git") is None:
            raise RuntimeError("precisa do Git instalado (git-scm.com)")
        if shutil.which("nvidia-smi") is None:
            raise RuntimeError("precisa de placa NVIDIA com o driver instalado (nvidia-smi não encontrado)")
        if self.cfg.get("precisa_nvcc") and shutil.which("nvcc") is None:
            raise RuntimeError("precisa do CUDA Toolkit 12.4 (nvcc) para compilar as extensões do modelo")
        if self.cfg.get("precisa_bash") and WINDOWS and not any(
            os.path.isfile(c) for c in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe")
        ) and shutil.which("bash") is None:
            raise RuntimeError("o UniRig precisa do bash do Git for Windows")

    def instalar(self, pular_pesos=False):
        self.etapa(f"Instalando {self.worker} em {self.pasta}")
        self.conferir()
        if not os.path.isdir(os.path.join(self.repo, ".git")):
            self.rodar(["git", "clone", "--depth", "1", "--recursive", self.cfg["repo"], self.repo])
        if not os.path.isfile(self.python):
            self.rodar([sys.executable, "-m", "venv", self.venv])
        self.pip(["pip", "wheel", "setuptools"])
        self.pip(TORCH, "--index-url", INDICE_TORCH)
        if self.cfg.get("requirements") and os.path.isfile(os.path.join(self.repo, self.cfg["requirements"])):
            self.rodar([self.python, "-m", "pip", "install", "-r", self.cfg["requirements"]], cwd=self.repo)
        self.pip(self.cfg.get("pip", []))
        if self.cfg.get("pyg"):
            self.pip(self.cfg["pyg"], "-f", PYG)
        if self.worker == "trellis2":
            self.extensoes_trellis2()
        if self.cfg.get("pesos") and not pular_pesos:
            repo_hf, destino = self.cfg["pesos"]
            self.etapa(f"Baixando os pesos de {repo_hf}")
            codigo = (
                "from huggingface_hub import snapshot_download; import sys; "
                "snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2])"
            )
            self.rodar([self.python, "-c", codigo, repo_hf, os.path.join(self.repo, destino)])
        self.rodar([self.python, "-c", "import torch; assert torch.cuda.is_available(), 'CUDA indisponível'; print(torch.cuda.get_device_name(0))"])
        info = {
            "worker": self.worker,
            "python": self.python,
            "repo": self.repo,
            "instalado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sem": [],
            "sistema": platform.platform(),
        }
        with open(os.path.join(self.pasta, "instalacao.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        self.etapa("Pronto. A Fornalha confere a instalação com uma geração de teste.")
        return info

    def extensoes_trellis2(self):
        """As extensões de CUDA do TRELLIS.2, menos o nvdiffrast e o nvdiffrec (licença só de pesquisa)."""
        setup = os.path.join(self.repo, "setup.sh")
        if not WINDOWS and os.path.isfile(setup):
            env = dict(os.environ)
            env["PATH"] = os.path.dirname(self.python) + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = self.venv
            self.rodar(["bash", "-c", "source ./setup.sh --basic --flash-attn --cumesh --o-voxel --flexgemm"], cwd=self.repo, env=env)
        else:
            self.pip(["git+https://github.com/JeffreyXiang/CuMesh.git", "git+https://github.com/JeffreyXiang/FlexGEMM.git"], "--no-build-isolation")
            ovoxel = os.path.join(self.repo, "o-voxel")
            if os.path.isdir(ovoxel):
                self.pip([ovoxel], "--no-build-isolation")
        for proibido in ("nvdiffrast", "nvdiffrec"):
            self.rodar([self.python, "-m", "pip", "uninstall", "-y", proibido])


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in WORKERS:
        print(f"uso: python instalar.py <{'|'.join(WORKERS)}> <pasta> [--pular-pesos]", file=sys.stderr)
        sys.exit(2)
    inst = Instalador(sys.argv[1], sys.argv[2])
    try:
        inst.instalar("--pular-pesos" in sys.argv)
    except Exception as e:
        inst.etapa(f"ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
