# Fornalha: instala o ComfyUI (processo à parte, licença GPL-3.0, falando com a Fornalha só por
# 127.0.0.1) numa pasta só dele, com ambiente Python próprio, o nó ComfyUI-GGUF e os modelos de
# licença comercial que a Fornalha usa.
#   python instalar_comfyui.py <pasta> <nvidia|rocm|directml|cpu> [--modelos gguf|inteiro|nenhum]
#                              [--hsa 10.3.0] [--porta 8188]
# nvidia: CUDA · rocm: AMD no Linux (RX 6000/7000/9000) · directml: AMD/Intel no Windows (inclusive
# RX 580) · cpu: sem placa (lento, mas funciona).
# Escreve o progresso em <pasta>/instalacao.log e, no fim, <pasta>/instalacao.json (como abrir).
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

WINDOWS = platform.system() == "Windows"
COMFYUI = "https://github.com/Comfy-Org/ComfyUI.git"
GGUF = "https://github.com/city96/ComfyUI-GGUF.git"
INDICE = {
    "nvidia": "https://download.pytorch.org/whl/cu128",
    "rocm": "https://download.pytorch.org/whl/rocm6.4",
    "cpu": "https://download.pytorch.org/whl/cpu",
}
# (pasta em models/, nome, endereço) — licenças conferidas em manifest/modelos.json
MODELOS = {
    "gguf": [
        ("diffusion_models", "z_image_turbo-Q4_K_M.gguf", "https://huggingface.co/jayn7/Z-Image-Turbo-GGUF/resolve/main/z_image_turbo-Q4_K_M.gguf"),
        ("text_encoders", "Qwen3-4B-Q4_K_M.gguf", "https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"),
        ("vae", "ae.safetensors", "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors"),
    ],
    "inteiro": [
        ("diffusion_models", "z_image_turbo_bf16.safetensors",
         "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors"),
        ("text_encoders", "qwen_3_4b.safetensors",
         "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors"),
        ("vae", "ae.safetensors", "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors"),
    ],
    "nenhum": [],
}


class Instalador:
    def __init__(self, pasta, backend):
        self.pasta = os.path.abspath(pasta)
        self.backend = backend
        os.makedirs(self.pasta, exist_ok=True)
        self.log = open(os.path.join(self.pasta, "instalacao.log"), "a", encoding="utf-8")
        self.repo = os.path.join(self.pasta, "ComfyUI")
        self.venv = os.path.join(self.pasta, "venv")
        self.python = os.path.join(self.venv, "Scripts" if WINDOWS else "bin", "python.exe" if WINDOWS else "python")

    def etapa(self, texto):
        linha = f"[{time.strftime('%H:%M:%S')}] {texto}"
        print(linha, flush=True)
        self.log.write(linha + "\n")
        self.log.flush()

    def rodar(self, cmd, cwd=None):
        self.etapa("$ " + " ".join(cmd))
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace")
        for linha in p.stdout:
            self.log.write(linha)
        self.log.flush()
        if p.wait() != 0:
            raise RuntimeError(f"falhou (código {p.returncode}): {' '.join(cmd[:4])}… veja {self.log.name}")

    def pip(self, *args):
        self.rodar([self.python, "-m", "pip", "install", *args])

    def clonar(self, url, destino):
        if os.path.isdir(os.path.join(destino, ".git")):
            self.rodar(["git", "-C", destino, "pull", "--ff-only"])
        else:
            self.rodar(["git", "clone", "--depth", "1", url, destino])
        return subprocess.run(["git", "-C", destino, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

    def baixar(self, pasta, nome, url):
        destino = os.path.join(self.repo, "models", pasta, nome)
        if os.path.isfile(destino) and os.path.getsize(destino) > 0:
            self.etapa(f"já baixado: {pasta}/{nome}")
            return destino
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        parte = destino + ".parte"
        self.etapa(f"baixando {pasta}/{nome}")
        pedido = urllib.request.Request(url, headers={"User-Agent": "Fornalha"})
        for tentativa in range(5):
            try:
                with urllib.request.urlopen(pedido, timeout=120) as r, open(parte, "wb") as f:
                    total = int(r.headers.get("Content-Length") or 0)
                    feito, ultimo = 0, 0.0
                    while True:
                        bloco = r.read(1 << 20)
                        if not bloco:
                            break
                        f.write(bloco)
                        feito += len(bloco)
                        if time.time() - ultimo > 10:
                            ultimo = time.time()
                            pct = f"{100 * feito / total:.0f}%" if total else f"{feito >> 20} MB"
                            self.etapa(f"  {nome}: {pct}")
                os.replace(parte, destino)
                return destino
            except Exception as e:  # rede instável: tenta de novo
                self.etapa(f"  falha no download ({e}); tentativa {tentativa + 2} de 5")
                time.sleep(10 * (tentativa + 1))
        raise RuntimeError(f"não consegui baixar {nome}")

    def instalar(self, modelos, hsa, porta):
        if shutil.which("git") is None:
            raise RuntimeError("precisa do Git instalado (git-scm.com)")
        self.etapa(f"ComfyUI para {self.backend} em {self.pasta}")
        commit = self.clonar(COMFYUI, self.repo)
        commit_gguf = self.clonar(GGUF, os.path.join(self.repo, "custom_nodes", "ComfyUI-GGUF"))
        if not os.path.isfile(self.python):
            self.rodar([sys.executable, "-m", "venv", self.venv])
        self.pip("--upgrade", "pip")
        if self.backend == "directml":
            # DirectML: qualquer placa DirectX 12 no Windows (AMD GCN como a RX 580, RDNA, Intel)
            self.pip("torch-directml")
        else:
            self.pip("torch", "torchvision", "torchaudio", "--index-url", INDICE[self.backend])
        self.pip("-r", os.path.join(self.repo, "requirements.txt"))
        self.pip("-r", os.path.join(self.repo, "custom_nodes", "ComfyUI-GGUF", "requirements.txt"))
        baixados = [self.baixar(*m) for m in MODELOS[modelos]]
        args = ["main.py", "--listen", "127.0.0.1", "--port", str(porta), "--preview-method", "none"]
        if self.backend == "directml":
            args.append("--directml")
        elif self.backend == "cpu":
            args.append("--cpu")
        env = {"HSA_OVERRIDE_GFX_VERSION": hsa} if hsa else {}
        info = {
            "backend": self.backend,
            "python": self.python,
            "pasta_comfyui": self.repo,
            "argumentos": args,
            "ambiente": env,
            "porta": porta,
            "comfyui_commit": commit,
            "comfyui_gguf_commit": commit_gguf,
            "modelos": [os.path.relpath(b, self.repo) for b in baixados],
            "instalado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(os.path.join(self.pasta, "instalacao.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
        self.etapa("pronto")


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[1] not in ("nvidia", "rocm", "directml", "cpu"):
        print(__doc__ or "uso: instalar_comfyui.py <pasta> <nvidia|rocm|directml|cpu> [--modelos gguf|inteiro|nenhum]")
        sys.exit(2)

    def opcao(nome, padrao):
        return a[a.index(nome) + 1] if nome in a and a.index(nome) + 1 < len(a) else padrao

    modelos = opcao("--modelos", "gguf")
    if modelos not in MODELOS:
        print(f"--modelos deve ser gguf, inteiro ou nenhum (veio {modelos})")
        sys.exit(2)
    inst = Instalador(a[0], a[1])
    try:
        inst.instalar(modelos, opcao("--hsa", ""), int(opcao("--porta", "8188")))
    except Exception as e:
        inst.etapa(f"ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
