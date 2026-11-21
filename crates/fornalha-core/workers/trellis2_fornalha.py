# Fornalha: worker do TRELLIS.2 (imagem → 3D), sem o nvdiffrast.
# A cor de cada vértice sai direto dos voxels do TRELLIS.2 (sem rasterizar) e a
# textura é assada depois no Blender (tarefa "assar"). O nvdiffrast, que só pode
# ser usado em pesquisa, nem é carregado: recebe um substituto vazio.
#   tarefa: {"tarefa": "gerar"|"verificar", "imagem", "saida", "modelo", "seed", "pesos", "faces_max"}
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import fw_comum as fw  # noqa: E402

fw.bloquear_proibidos()

# id do modelo no catálogo → (tipo de pipeline do TRELLIS.2, pouca VRAM)
TIPOS = {
    "trellis2-512-poucavram": ("512", True),
    "trellis2-512": ("512", False),
    "trellis2-1024-poucavram": ("1024_cascade", True),
    "trellis2-1536": ("1536_cascade", False),
}
PESOS_PADRAO = "microsoft/TRELLIS.2-4B"


def carregar(pesos, pouca_vram):
    from trellis2.pipelines import Trellis2ImageTo3DPipeline

    pipe = Trellis2ImageTo3DPipeline.from_pretrained(pesos or PESOS_PADRAO)
    if pouca_vram and hasattr(pipe, "low_vram"):
        pipe.low_vram = True
    if hasattr(pipe, "cuda"):
        pipe.cuda()
    return pipe


def rodar_pipeline(pipe, imagem, tipo, seed):
    erro = None
    for kw in (dict(seed=seed, pipeline_type=tipo), dict(seed=seed), {}):
        try:
            saida = pipe.run(imagem, **kw)
            return saida[0] if isinstance(saida, (list, tuple)) else saida
        except TypeError as e:  # versão do TRELLIS.2 com outros argumentos
            erro = e
    raise erro


def _fatia(layout, nome, padrao):
    f = layout.get(nome) if isinstance(layout, dict) else None
    if f is None:
        return padrao
    if isinstance(f, slice):
        return f
    if isinstance(f, (list, tuple)) and len(f) == 2:
        return slice(int(f[0]), int(f[1]))
    return padrao


def cores_nos_vertices(malha):
    """Cor de cada vértice pelo voxel onde ele cai (procura nos vizinhos se cair num vazio)."""
    import numpy as np

    v = fw.para_numpy(malha.vertices).astype(np.float64).reshape(-1, 3)
    coords = fw.para_numpy(malha.coords).astype(np.int64)
    if coords.shape[1] == 4:  # primeira coluna = índice do lote
        coords = coords[:, 1:]
    attrs = fw.para_numpy(malha.attrs).astype(np.float32)
    cor = attrs[:, _fatia(getattr(malha, "layout", {}), "base_color", slice(0, 3))][:, :3]
    voxel = float(np.asarray(fw.para_numpy(malha.voxel_size)).reshape(-1)[0])
    res = int(round(1.0 / voxel))
    minimo = -0.5
    iv = np.clip(np.floor((v - minimo) / voxel).astype(np.int64), 0, res - 1)
    chaves = (coords[:, 0] * res + coords[:, 1]) * res + coords[:, 2]
    ordem = np.argsort(chaves)
    ordenadas = chaves[ordem]

    def procurar(p):
        ch = (p[:, 0] * res + p[:, 1]) * res + p[:, 2]
        pos = np.clip(np.searchsorted(ordenadas, ch), 0, len(ordenadas) - 1)
        return ordem[pos], ordenadas[pos] == ch

    idx, ok = procurar(iv)
    vizinhos = sorted(
        [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)],
        key=lambda d: abs(d[0]) + abs(d[1]) + abs(d[2]),
    )
    for d in vizinhos:
        falta = np.nonzero(~ok)[0]
        if not len(falta):
            break
        idx2, ok2 = procurar(np.clip(iv[falta] + np.array(d), 0, res - 1))
        idx[falta[ok2]] = idx2[ok2]
        ok[falta[ok2]] = True
    cores = cor[idx].astype(np.float64)
    if cores.min() < -0.05:  # alguns modelos guardam a cor entre -1 e 1
        cores = (cores + 1.0) / 2.0
    if ok.any() and not ok.all():
        cores[~ok] = cores[ok].mean(axis=0)
    return np.clip(np.round(cores * 255.0), 0, 255).astype(np.uint8), float(ok.mean()), res


def imagem_de_verificacao(caminho):
    """Figura simples para a verificação da instalação (sem depender de arquivo de fora)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (512, 512), (235, 235, 235))
    d = ImageDraw.Draw(img)
    d.ellipse((206, 60, 306, 160), fill=(224, 172, 126))
    d.rectangle((196, 160, 316, 330), fill=(122, 46, 34))
    d.rectangle((150, 170, 196, 300), fill=(122, 46, 34))
    d.rectangle((316, 170, 362, 300), fill=(122, 46, 34))
    d.rectangle((206, 330, 250, 470), fill=(47, 54, 64))
    d.rectangle((262, 330, 306, 470), fill=(47, 54, 64))
    img.save(caminho)
    return caminho


def tarefa(t):
    import numpy as np
    from PIL import Image

    try:
        import torch
    except ImportError:  # o teste da Fornalha roda sem torch, com um TRELLIS.2 de mentira
        torch = None
    verificar = t.get("tarefa") == "verificar"
    modelo = t.get("modelo") or ("trellis2-512-poucavram" if verificar else "trellis2-512")
    tipo, pouca_vram = TIPOS.get(modelo, ("512", False))
    seed = int(t.get("seed") or 1)
    if torch is not None:
        torch.manual_seed(seed)
    caminho_img = t.get("imagem")
    if verificar or not caminho_img:
        caminho_img = imagem_de_verificacao(os.path.splitext(t["saida"])[0] + ".entrada.png")
    imagem = Image.open(caminho_img).convert("RGB")
    pipe = carregar(t.get("pesos"), pouca_vram)
    malha = rodar_pipeline(pipe, imagem, tipo, seed)
    faces_max = int(t.get("faces_max") or 1_000_000)
    if hasattr(malha, "simplify"):
        try:
            malha.simplify(faces_max)
        except Exception as e:  # simplificar é só para o Blender ficar leve
            print(f"simplify falhou: {e}", file=sys.stderr)
    cores, achadas, res = cores_nos_vertices(malha)
    v = fw.para_numpy(malha.vertices).reshape(-1, 3)
    f = fw.para_numpy(malha.faces).reshape(-1, 3)
    fw.escrever_ply(t["saida"], v, f, cores)
    return {
        "arquivos": {"malha_alta": t["saida"]},
        "estatisticas": {
            "vertices": int(len(v)),
            "faces": int(len(f)),
            "cores_achadas": round(achadas, 4),
            "resolucao_voxels": res,
            "tipo": tipo,
            "pouca_vram": pouca_vram,
            "cor_media": [int(x) for x in np.asarray(cores).mean(axis=0).round()],
        },
        "eixo_cima": t.get("eixo_cima_da_saida", "Z"),
        "verificacao": verificar,
        "sem_nvdiffrast": not fw.proibidos_carregados(),
        "modelo": modelo,
        "imagem": caminho_img,
    }


if __name__ == "__main__":
    fw.executar(tarefa)
