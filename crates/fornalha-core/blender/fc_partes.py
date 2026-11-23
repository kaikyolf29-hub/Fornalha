# Fornalha: 3D por partes — a cabeça feita em close (recorte do conceito refinado pelo motor de imagem e
# malha do TRELLIS.2) entra no lugar da cabeça da malha do corpo, antes do esqueleto. O recorte diz a
# altura: a malha da cabeça vai do topo da figura até a base do recorte (frações da altura da figura).
import bpy
import numpy as np
from mathutils import Vector


def _co(obj):
    m = obj.matrix_world
    return np.array([(m @ v.co)[:] for v in obj.data.vertices])


def _ativo(obj):
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj


def _apagar_vertices(obj, manter):
    """Apaga os vértices (e as faces deles) onde `manter` é falso."""
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    fora = [v for v in bm.verts if not manter[v.index]]
    bmesh.ops.delete(bm, geom=fora, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def trocar_cabeca(corpo, info, triangulos=30000):
    """`corpo` já normalizado (pés em z = 0, de frente para -Y). `info`: {"malha", "base_frac",
    "corte_frac"}. Devolve um resumo."""
    co = _co(corpo)
    H = float(co[:, 2].max())
    z_base = H * (1.0 - float(info["base_frac"]))
    z_corte = H * (1.0 - float(info["corte_frac"]))
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=info["malha"])
    novos = [o for o in bpy.data.objects if o not in antes]
    malhas = [o for o in novos if o.type == "MESH"]
    if not malhas:
        raise RuntimeError("a malha da cabeça veio vazia")
    for o in novos:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    _ativo(malhas[0])
    for o in malhas:
        o.select_set(True)
    if len(malhas) > 1:
        bpy.ops.object.join()
    cab = bpy.context.view_layer.objects.active
    cab.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # leve antes de juntar: a cabeça fica com até `triangulos`
    n = sum(len(p.vertices) - 2 for p in cab.data.polygons)
    if n > triangulos:
        mod = cab.modifiers.new("leve", "DECIMATE")
        mod.ratio = triangulos / n
        bpy.ops.object.modifier_apply(modifier=mod.name)
    cc = _co(cab)
    alt = float(cc[:, 2].max() - cc[:, 2].min())
    esc = (H - z_base) / max(alt, 1e-6)
    cab.scale = (esc, esc, esc)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(scale=True)
    cc = _co(cab)
    # topo com topo; x e profundidade pelo centro do alto da cabeça (6% de cima) nas duas malhas
    faixa = 0.06 * H
    topo_c = co[co[:, 2] > H - faixa]
    topo_k = cc[cc[:, 2] > cc[:, 2].max() - faixa]
    desloc = Vector((
        float(np.median(topo_c[:, 0]) - np.median(topo_k[:, 0])),
        float(np.median(topo_c[:, 1]) - np.median(topo_k[:, 1])),
        float(H - cc[:, 2].max()),
    ))
    cab.location = desloc
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=True)
    # o corpo perde a cabeça acima do pescoço; a cabeça nova perde o que fica abaixo (1% de sobra)
    _apagar_vertices(corpo, co[:, 2] <= z_corte)
    cc = _co(cab)
    _apagar_vertices(cab, cc[:, 2] >= z_corte - 0.01 * H)
    _ativo(corpo)
    cab.select_set(True)
    bpy.context.view_layer.objects.active = corpo
    bpy.ops.object.join()
    return {"cabeca_por_partes": True, "escala_da_cabeca": round(esc, 4), "corte_m": round(z_corte, 3),
            "triangulos_da_cabeca": min(n, triangulos)}
