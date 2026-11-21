# Fornalha: worker do HY-Motion (texto → movimento), da Tencent.
# Só roda depois do aceite da licença da Tencent na janela da Fornalha.
# Roda a inferência oficial do repositório e converte a saída (SMPL/SMPL-H) para
# o formato neutro da Fornalha, que o Blender aplica no esqueleto padrão:
#   {"fps", "eixo_cima": "Y", "rotacoes": [quadro][22][3] (eixo-ângulo), "translacao": [quadro][3]}
#   tarefa: {"texto", "segundos", "saida", "modelo", "pesos", "seed", "pasta_temporaria"}
import glob
import json
import os
import pickle
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fw_comum as fw  # noqa: E402

PASTA_DO_MODELO = {
    "hy-motion-lite": "HY-Motion-1.0-Lite",
    "hy-motion-1.0-q": "HY-Motion-1.0",
    "hy-motion-1.0": "HY-Motion-1.0",
}
JUNTAS = 22
CHAVES_TRANSLACAO = ("trans", "transl", "root_trans", "root_translation", "translation")
CHAVES_FPS = ("fps", "mocap_framerate", "frame_rate", "framerate")


# ------------------------------------------------------------------ conversão


def _rot6d_para_matriz(r6):
    import numpy as np

    a1, a2 = r6[..., 0:3], r6[..., 3:6]
    b1 = a1 / np.maximum(np.linalg.norm(a1, axis=-1, keepdims=True), 1e-8)
    b2 = a2 - (b1 * a2).sum(-1, keepdims=True) * b1
    b2 = b2 / np.maximum(np.linalg.norm(b2, axis=-1, keepdims=True), 1e-8)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=-1)


def _matriz_para_eixo_angulo(m):
    import numpy as np

    tr = np.clip((np.trace(m, axis1=-2, axis2=-1) - 1.0) / 2.0, -1.0, 1.0)
    ang = np.arccos(tr)
    eixo = np.stack([m[..., 2, 1] - m[..., 1, 2], m[..., 0, 2] - m[..., 2, 0], m[..., 1, 0] - m[..., 0, 1]], axis=-1)
    s = np.sin(ang)[..., None]
    pequeno = np.abs(s) < 1e-6
    eixo = np.where(pequeno, 0.0, eixo / np.where(pequeno, 1.0, 2.0 * s))
    return eixo * ang[..., None]


def _achatar(d, prefixo=""):
    """dict aninhado (pkl) → {chave: array}."""
    import numpy as np

    saida = {}
    for k, v in d.items():
        nome = f"{prefixo}{k}"
        if isinstance(v, dict):
            saida.update(_achatar(v, nome + "."))
        else:
            try:
                arr = np.asarray(v)
                if arr.dtype != object:
                    saida[nome] = arr
            except Exception:
                pass
    return saida


def ler_arquivo(caminho):
    import numpy as np

    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".npz":
        with np.load(caminho, allow_pickle=True) as z:
            d = {}
            for k in z.files:
                arr = z[k]
                if arr.dtype == object and arr.shape == ():
                    item = arr.item()
                    if isinstance(item, dict):
                        d.update(_achatar(item, k + "."))
                        continue
                d[k] = arr
            return d
    if ext == ".npy":
        arr = np.load(caminho, allow_pickle=True)
        if arr.dtype == object and arr.shape == ():
            return _achatar(arr.item())
        return {"poses": arr}
    if ext in (".pkl", ".pickle"):
        with open(caminho, "rb") as f:
            return _achatar(pickle.load(f))
    if ext == ".json":
        with open(caminho, encoding="utf-8") as f:
            return _achatar(json.load(f))
    raise ValueError(f"formato de movimento não suportado: {ext}")


def _procurar(d, nomes):
    for n in nomes:
        for k, v in d.items():
            if k == n or k.endswith("." + n):
                return v
    return None


def converter(d, fps_padrao=30.0):
    """Arrays do SMPL/SMPL-H → formato da Fornalha (22 juntas do corpo)."""
    import numpy as np

    rot = None
    r6 = _procurar(d, ("rot6d", "rotation_6d", "poses_6d"))
    rm = _procurar(d, ("rotmat", "rotation_matrix", "rot_mats"))
    poses = _procurar(d, ("poses", "smpl_poses", "pose", "full_pose"))
    go = _procurar(d, ("global_orient", "root_orient"))
    bp = _procurar(d, ("body_pose", "pose_body"))
    if r6 is not None:
        r6 = np.asarray(r6, dtype=np.float64)
        r6 = r6.reshape(r6.shape[0], -1, 6)
        rot = _matriz_para_eixo_angulo(_rot6d_para_matriz(r6))
    elif rm is not None:
        rm = np.asarray(rm, dtype=np.float64)
        rot = _matriz_para_eixo_angulo(rm.reshape(rm.shape[0], -1, 3, 3))
    elif go is not None and bp is not None:
        go = np.asarray(go, dtype=np.float64).reshape(-1, 1, 3)
        bp = np.asarray(bp, dtype=np.float64)
        rot = np.concatenate([go, bp.reshape(bp.shape[0], -1, 3)], axis=1)
    elif poses is not None:
        poses = np.asarray(poses, dtype=np.float64)
        if poses.ndim == 3 and poses.shape[-1] == 3:
            rot = poses
        else:
            rot = poses.reshape(poses.shape[0], -1, 3)
    if rot is None:
        raise ValueError(f"não achei as rotações do SMPL na saída (chaves: {sorted(d)[:20]})")
    if rot.ndim != 3 or rot.shape[1] < JUNTAS:
        raise ValueError(f"esperava ao menos {JUNTAS} juntas, veio {rot.shape}")
    rot = rot[:, :JUNTAS, :]
    tr = _procurar(d, CHAVES_TRANSLACAO)
    tr = np.zeros((rot.shape[0], 3)) if tr is None else np.asarray(tr, dtype=np.float64).reshape(-1, 3)[: rot.shape[0]]
    fps = _procurar(d, CHAVES_FPS)
    fps = float(np.asarray(fps).reshape(-1)[0]) if fps is not None else fps_padrao
    return {
        "fps": fps,
        "eixo_cima": "Y",
        "rotacoes": np.round(rot, 5).tolist(),
        "translacao": np.round(tr, 5).tolist(),
        "juntas": "smpl-22",
    }


# ------------------------------------------------------------------ inferência


def inferir(t, pasta):
    """Roda a inferência oficial do HY-Motion e devolve o arquivo de saída."""
    repo = os.getcwd()
    entrada = os.path.join(pasta, "entrada")
    saida = os.path.join(pasta, "saida")
    os.makedirs(entrada, exist_ok=True)
    os.makedirs(saida, exist_ok=True)
    with open(os.path.join(entrada, "fornalha.txt"), "w", encoding="utf-8") as f:
        f.write(t["texto"].strip() + "\n")
    modelo = t.get("modelo") or "hy-motion-lite"
    pesos = t.get("pesos") or os.path.join(repo, "ckpts", "tencent", PASTA_DO_MODELO.get(modelo, "HY-Motion-1.0-Lite"))
    script = next((s for s in ("local_infer.py", "infer.py", "inference.py") if os.path.isfile(os.path.join(repo, s))), None)
    if script is None:
        raise FileNotFoundError("não achei o script de inferência do HY-Motion no repositório")
    tentativas = [
        [sys.executable, script, "--model_path", pesos, "--input_text_dir", entrada, "--output_dir", saida],
        [sys.executable, script, "--model_path", pesos, "--prompt", t["texto"], "--output_dir", saida],
    ]
    env = dict(os.environ)
    env["FORNALHA_SEGUNDOS"] = str(t.get("segundos") or 4)
    env["FORNALHA_SEED"] = str(t.get("seed") or 1)
    if modelo.endswith("-q"):
        env["FORNALHA_TEXTO_QUANTIZADO"] = "1"
    log = []
    for cmd in tentativas:
        r = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log.append({"comando": cmd[1:3], "codigo": r.returncode, "stderr": r.stderr[-1500:]})
        achados = []
        for ext in ("npz", "npy", "pkl", "json"):
            achados += glob.glob(os.path.join(saida, "**", f"*.{ext}"), recursive=True)
        if r.returncode == 0 and achados:
            return max(achados, key=os.path.getmtime), log
    raise RuntimeError("a inferência do HY-Motion não gerou movimento: " + json.dumps(log, ensure_ascii=False)[-2500:])


def tarefa(t):
    pasta = t.get("pasta_temporaria") or os.path.join(os.path.dirname(os.path.abspath(t["saida"])), "hy-motion")
    if t.get("arquivo_de_movimento"):  # converter uma saída que já existe
        arquivo, log = t["arquivo_de_movimento"], []
    else:
        arquivo, log = inferir(t, pasta)
    mov = converter(ler_arquivo(arquivo))
    os.makedirs(os.path.dirname(os.path.abspath(t["saida"])), exist_ok=True)
    with open(t["saida"], "w", encoding="utf-8") as f:
        json.dump(mov, f)
    quadros = len(mov["rotacoes"])
    return {
        "arquivos": {"movimento": t["saida"], "saida_original": arquivo},
        "estatisticas": {"quadros": quadros, "fps": mov["fps"], "segundos_de_movimento": round(quadros / mov["fps"], 2)},
        "modelo": t.get("modelo") or "hy-motion-lite",
        "log": log,
    }


if __name__ == "__main__":
    fw.executar(tarefa)
