# Fornalha: base dos workers de placa (TRELLIS.2, UniRig, HY-Motion).
# python <worker>.py tarefa.json resultado.json
# O worker roda no ambiente Python do modelo (instalado pela Fornalha) e devolve
# um JSON com {"ok", "arquivos", "estatisticas", "segundos", ...}.
import importlib.util
import json
import os
import sys
import time
import traceback

# Bibliotecas sem licença comercial: o resultado diz se alguma foi carregada.
PROIBIDOS = ("nvdiffrast", "nvdiffrec")


def proibidos_instalados():
    """Instalados no ambiente (procura direto no disco, sem passar pelo substituto)."""
    import importlib.machinery

    return [m for m in PROIBIDOS if importlib.machinery.PathFinder.find_spec(m) is not None]


def proibidos_carregados():
    """Módulos proibidos de verdade na memória (o substituto da Fornalha não conta)."""
    achados = []
    for nome, mod in list(sys.modules.items()):
        raiz = nome.split(".")[0]
        if raiz in PROIBIDOS and not getattr(mod, "__fornalha_substituto__", False) and raiz not in achados:
            achados.append(raiz)
    return achados


class _Substituto:
    """No lugar do nvdiffrast: o import funciona, mas qualquer uso falha com explicação."""

    def __init__(self, nome):
        self.__name__ = nome
        self.__fornalha_substituto__ = True
        self.__path__ = []
        self.__spec__ = None

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        raise RuntimeError(f"{self.__name__}.{attr}: o nvdiffrast está bloqueado pela Fornalha (licença só de pesquisa)")


def bloquear_proibidos():
    """O código do modelo não carrega o nvdiffrast nesta execução: recebe um substituto vazio."""
    import importlib.abc
    import importlib.machinery

    class _Carregador(importlib.abc.Loader):
        def create_module(self, spec):
            return _Substituto(spec.name)

        def exec_module(self, module):
            return None

    class _Bloqueio(importlib.abc.MetaPathFinder):
        def find_spec(self, nome, caminho=None, alvo=None):
            if nome.split(".")[0] in PROIBIDOS:
                return importlib.machinery.ModuleSpec(nome, _Carregador(), is_package=True)
            return None

    sys.meta_path.insert(0, _Bloqueio())


def executar(funcao):
    tarefa_path, resultado_path = sys.argv[1], sys.argv[2]
    with open(tarefa_path, encoding="utf-8") as f:
        t = json.load(f)
    inicio = time.time()
    try:
        r = funcao(t)
        r["ok"] = True
    except Exception as e:
        r = {"ok": False, "erro": f"{type(e).__name__}: {e}", "detalhe": traceback.format_exc()}
    r["segundos"] = round(time.time() - inicio, 2)
    r["proibidos_carregados"] = proibidos_carregados()
    r["proibidos_instalados"] = proibidos_instalados()
    r["python"] = sys.version.split()[0]
    with open(resultado_path, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    if not r["ok"]:
        print(r.get("detalhe", ""), file=sys.stderr)
        sys.exit(1)


def para_numpy(x):
    import numpy as np

    if hasattr(x, "detach"):
        x = x.detach()
    if hasattr(x, "cpu"):
        x = x.cpu()
    if hasattr(x, "float") and str(getattr(x, "dtype", "")).startswith("torch.bfloat16"):
        x = x.float()
    return np.asarray(x)


def escrever_ply(caminho, vertices, faces, cores):
    """PLY binário com cor por vértice (o Blender importa sem plugin)."""
    import numpy as np

    v = np.ascontiguousarray(vertices, dtype="<f4").reshape(-1, 3)
    f = np.ascontiguousarray(faces, dtype="<i4").reshape(-1, 3)
    c = np.ascontiguousarray(np.clip(cores, 0, 255), dtype=np.uint8).reshape(-1, 3)
    if len(c) != len(v):
        raise ValueError("número de cores diferente do de vértices")
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    cab = (
        "ply\nformat binary_little_endian 1.0\ncomment Fornalha\n"
        f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n"
    ).encode("ascii")
    reg_v = np.empty(len(v), dtype=[("p", "<f4", 3), ("c", "u1", 3)])
    reg_v["p"] = v
    reg_v["c"] = c
    reg_f = np.empty(len(f), dtype=[("n", "u1"), ("i", "<i4", 3)])
    reg_f["n"] = 3
    reg_f["i"] = f
    with open(caminho, "wb") as arq:
        arq.write(cab)
        arq.write(reg_v.tobytes())
        arq.write(reg_f.tobytes())
    return caminho


def ler_ply_cabecalho(caminho):
    with open(caminho, "rb") as arq:
        linhas = []
        while True:
            l = arq.readline().decode("ascii", "replace").strip()
            linhas.append(l)
            if l == "end_header" or len(linhas) > 50:
                break
    return linhas

