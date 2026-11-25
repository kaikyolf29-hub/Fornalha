# Fornalha: esqueleto que a IA vê e edita. `ver` desenha a malha clara com os ossos coloridos e
# numerados (frente, lado e cima) e devolve a lista dos ossos (pai, cabeça, ponta, quantos vértices cada
# um carrega) com avisos (osso sem peso, osso longe da malha, lados diferentes). `editar` aplica as
# mudanças pedidas (mover, criar, apagar, renomear, trocar o pai, espelhar) e refaz os pesos.
# Ossos chamados "mola_<grupo>_<n>" (cauda, cabelo, asa, orelha, rabo de cavalo…) viram mola no jogo.
import math
import re

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import fc_comum as c

CORES = [(1.0, 0.75, 0.1), (0.2, 0.8, 1.0), (1.0, 0.3, 0.3), (0.4, 1.0, 0.4), (0.9, 0.4, 1.0), (1.0, 0.55, 0.2)]


def _malhas(arm, com_pesos=False):
    """Malhas do personagem. com_pesos: só as que dobram com o esqueleto (pele, roupa); as presas inteiras
    num osso (arma, escudo) ficam de fora."""
    out = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        pele = any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)
        if pele or (not com_pesos and o.parent == arm):
            out.append(o)
    return out


def _cor_do_osso(nome):
    if re.search(r"(_l|Left|_esq)", nome):
        return CORES[1]
    if re.search(r"(_r|Right|_dir)", nome):
        return CORES[2]
    if nome.startswith("mola_"):
        return CORES[4]
    if re.match(r"(pata|perna|leg|thigh|calf|foot)", nome):
        return CORES[3]
    return CORES[0]


def _material(nome, cor, emissao=2.5, alfa=1.0):
    m = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (*cor, 1)
        for k in ("Emission Color", "Emission"):
            if k in b.inputs:
                b.inputs[k].default_value = (*cor, 1)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = emissao
        b.inputs["Alpha"].default_value = alfa
        b.inputs["Roughness"].default_value = 0.8
    try:
        m.blend_method = "BLEND"
    except Exception:
        pass
    return m


def lista(arm, malhas):
    """Os ossos em ordem (pai antes dos filhos), numerados a partir de 1."""
    mw = arm.matrix_world
    ordem = []

    def andar(b):
        ordem.append(b)
        for f in b.children:
            andar(f)

    for b in arm.data.bones:
        if b.parent is None:
            andar(b)
    pesos = {b.name: 0 for b in ordem}
    for o in malhas:
        idx = {g.index: g.name for g in o.vertex_groups if g.name in pesos}
        for v in o.data.vertices:
            for g in v.groups:
                n = idx.get(g.group)
                if n and g.weight > 0.1:
                    pesos[n] += 1
    bvh = None
    if malhas:
        verts, tris, base = [], [], 0
        for o in malhas:
            M = o.matrix_world
            verts += [M @ v.co for v in o.data.vertices]
            for p in o.data.polygons:
                vs = list(p.vertices)
                tris += [(base + vs[0], base + vs[k], base + vs[k + 1]) for k in range(1, len(vs) - 1)]
            base += len(o.data.vertices)
        if tris:
            bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True)
    out = []
    for i, b in enumerate(ordem, start=1):
        h, t = mw @ b.head_local, mw @ b.tail_local
        meio = (h + t) / 2
        dist = None
        if bvh is not None:
            achado = bvh.find_nearest(meio)
            if achado[0] is not None:
                dist = round(achado[3] * 100, 1)
        out.append({"n": i, "nome": b.name, "pai": b.parent.name if b.parent else None,
                    "cabeca": [round(x, 3) for x in h], "ponta": [round(x, 3) for x in t],
                    "comprimento_cm": round((t - h).length * 100, 1), "ligado_ao_pai": bool(b.use_connect),
                    "vertices_que_carrega": pesos.get(b.name, 0), "meio_ate_a_malha_cm": dist,
                    "mola": b.name.startswith("mola_")})
    return out


def avisos(ossos, H):
    av = []
    por_nome = {o["nome"]: o for o in ossos}
    for o in ossos:
        if o["pai"] is None:
            continue
        if o["vertices_que_carrega"] == 0 and not o["nome"].startswith(("ik_", "raiz", "root", "Root")):
            av.append(f"osso {o['n']} ({o['nome']}) não carrega nenhum vértice: não mexe nada na malha")
        if o["meio_ate_a_malha_cm"] is not None and o["meio_ate_a_malha_cm"] > 25 * H:
            av.append(f"osso {o['n']} ({o['nome']}) está a {o['meio_ate_a_malha_cm']} cm da malha: fora do corpo?")
    for n, o in por_nome.items():
        m = re.match(r"^(.*?)(_l|Left)(.*)$", n)
        if not m:
            continue
        par = m.group(1) + ("_r" if m.group(2) == "_l" else "Right") + m.group(3)
        p = por_nome.get(par)
        if not p:
            av.append(f"{n} não tem o par do outro lado ({par})")
            continue
        if abs(o["comprimento_cm"] - p["comprimento_cm"]) > 0.15 * max(o["comprimento_cm"], p["comprimento_cm"], 1e-6):
            av.append(f"{n} ({o['comprimento_cm']} cm) e {par} ({p['comprimento_cm']} cm) com tamanhos diferentes")
        if abs(o["cabeca"][0] + p["cabeca"][0]) > 0.06 * H or abs(o["cabeca"][2] - p["cabeca"][2]) > 0.06 * H:
            av.append(f"{n} e {par} fora de espelho (x {o['cabeca'][0]} × {p['cabeca'][0]}, altura {o['cabeca'][2]} × {p['cabeca'][2]})")
    return av


def _desenhar(arm, ossos, H):
    """Cilindros nos ossos, esferas nas juntas e o número de cada osso (de frente para a câmera)."""
    criados = []
    raio = max(0.006 * H, 0.004)
    for o in ossos:
        h, t = Vector(o["cabeca"]), Vector(o["ponta"])
        cor = _cor_do_osso(o["nome"])
        mat = _material("fc_osso_" + "_".join(f"{x:.2f}" for x in cor), cor)
        d = t - h
        if d.length > 1e-5:
            bpy.ops.mesh.primitive_cylinder_add(radius=raio, depth=d.length, location=(h + t) / 2, vertices=8)
            cil = bpy.context.active_object
            cil.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
            cil.data.materials.append(mat)
            criados.append(cil)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=raio * 2.2, location=h, segments=10, ring_count=6)
        esf = bpy.context.active_object
        esf.data.materials.append(mat)
        criados.append(esf)
        txt = bpy.data.curves.new(f"n{o['n']}", "FONT")
        txt.body = str(o["n"])
        txt.size = 0.035 * H
        txt.align_x = "CENTER"
        obj = bpy.data.objects.new(f"n{o['n']}", txt)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = h + (d * 0.5 if d.length > 0.05 * H else Vector()) + Vector((0, 0, 0.012 * H))
        obj.data.materials.append(_material("fc_numero", (1.0, 1.0, 1.0), emissao=4.0))
        criados.append(obj)
    return criados


def ver(arm, caminho, largura=600, altura=600, amostras=6):
    """Imagem (frente, lado, cima) com a malha clara e os ossos numerados, e a lista com avisos."""
    malhas = _malhas(arm)
    objs = malhas or [arm]
    mn, mx = c.caixa_envolvente(objs)
    H = max((mx - mn).z, (mx - mn).y, (mx - mn).x, 0.1)
    ossos = lista(arm, malhas)
    # a pose de descanso (os ossos da lista são do descanso)
    pose = arm.data.pose_position
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    fantasma = _material("fc_fantasma", (0.75, 0.75, 0.78), emissao=0.0, alfa=0.28)
    guardados = {}
    for o in malhas:
        guardados[o.name] = [s.material for s in o.material_slots]
        if not o.material_slots:
            o.data.materials.append(fantasma)
        for s in o.material_slots:
            s.material = fantasma
    criados = _desenhar(arm, ossos, H)
    partes = []
    tmp = caminho + ".tmp"
    vistas = [(0, -1, 0.0001), (1, 0, 0.0001), (0.0001, -0.0001, 1)]
    for i, d in enumerate(vistas):
        cam = bpy.context.scene.camera or c._camera()
        for o in criados:
            if o.type == "FONT":
                o.rotation_euler = Vector(d).to_track_quat("Z", "Y").to_euler()
        arq = f"{tmp}{i}.png"
        c.renderizar(arq, objs + criados, direcao=d, largura=largura, altura=altura, amostras=amostras, orto=True, chao=False)
        img = bpy.data.images.load(arq)
        px = np.empty(largura * altura * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        partes.append(px.reshape(altura, largura, 4))
        bpy.data.images.remove(img)
        import os

        os.remove(arq)
        del cam
    junta = np.concatenate(partes, axis=1)
    final = bpy.data.images.new("esqueleto", width=largura * 3, height=altura, alpha=True)
    final.pixels.foreach_set(junta.ravel())
    final.filepath_raw = caminho
    final.file_format = "PNG"
    final.save()
    for o in criados:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in malhas:
        for s, m in zip(o.material_slots, guardados[o.name]):
            s.material = m
    arm.data.pose_position = pose
    return ossos, avisos(ossos, H), H


# ------------------------------------------------------------------ editar

def _nome(arm, x):
    """Osso pelo nome ou pelo número da lista do `ver`."""
    if isinstance(x, int) or (isinstance(x, str) and x.isdigit()):
        ordem = [o["nome"] for o in lista(arm, [])]
        k = int(x) - 1
        if 0 <= k < len(ordem):
            return ordem[k]
        raise ValueError(f"não há osso número {x}")
    if x not in arm.data.bones:
        raise ValueError(f"não há osso {x}")
    return x


def editar(arm, mudancas):
    """Aplica as mudanças no modo de edição. Coordenadas em metros, no mundo (as do `ver`). Devolve (o que
    foi feito, ossos mexidos)."""
    mwi = arm.matrix_world.inverted()
    # nomes resolvidos antes (os números mudam quando a lista muda)
    feitas = []
    mexidos = set()
    resolvidos = []
    novos = set()
    for m in mudancas:
        r = dict(m)
        op = r.get("op")
        if op == "criar":
            novos.add(r["osso"])
        elif r.get("osso") is not None:
            r["osso"] = _nome(arm, r["osso"])
        if r.get("pai") is not None and r["pai"] not in novos:
            r["pai"] = _nome(arm, r["pai"])
        resolvidos.append(r)
    for o in bpy.context.scene.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    try:
        for m in resolvidos:
            op = m.get("op")
            if op == "mover":
                b = eb[m["osso"]]
                if m.get("cabeca") is not None:
                    b.head = mwi @ Vector(m["cabeca"])
                if m.get("ponta") is not None:
                    b.tail = mwi @ Vector(m["ponta"])
                feitas.append(f"movi {b.name}")
                mexidos |= {b.name} | {f.name for f in b.children}
            elif op == "criar":
                n = m["osso"]
                if n in eb:
                    raise ValueError(f"já existe o osso {n}")
                b = eb.new(n)
                b.head = mwi @ Vector(m["cabeca"])
                b.tail = mwi @ Vector(m["ponta"])
                if m.get("pai"):
                    b.parent = eb[m["pai"]]
                    b.use_connect = bool(m.get("ligado", False))
                feitas.append(f"criei {n}")
                mexidos.add(n)
            elif op == "apagar":
                b = eb[m["osso"]]
                pai = b.parent
                for f in list(b.children):
                    f.use_connect = False
                    f.parent = pai
                mexidos |= {f.name for f in b.children} | ({pai.name} if pai else set())
                eb.remove(b)
                feitas.append(f"apaguei {m['osso']}")
            elif op == "renomear":
                eb[m["osso"]].name = m["novo"]
                feitas.append(f"{m['osso']} agora é {m['novo']}")
            elif op == "pai":
                b = eb[m["osso"]]
                b.use_connect = False
                b.parent = eb[m["pai"]] if m.get("pai") else None
                feitas.append(f"{b.name} agora é filho de {m.get('pai')}")
            elif op == "espelhar":
                # cada osso de um lado ganha (ou atualiza) o par do outro lado, espelhado em X
                de = m.get("de", "_l")
                para = {"_l": "_r", "_r": "_l", "Left": "Right", "Right": "Left"}[de]
                for b in [b for b in eb if de in b.name]:
                    n2 = b.name.replace(de, para)
                    b2 = eb.get(n2) or eb.new(n2)
                    b2.head = Vector((-b.head.x, b.head.y, b.head.z))
                    b2.tail = Vector((-b.tail.x, b.tail.y, b.tail.z))
                    b2.roll = -b.roll
                    if b.parent:
                        b2.parent = eb.get(b.parent.name.replace(de, para)) or b.parent
                        b2.use_connect = b.use_connect
                    mexidos.add(n2)
                feitas.append(f"espelhei os ossos {de} para {para}")
            else:
                raise ValueError(f"mudança desconhecida: {op} (use mover, criar, apagar, renomear, pai, espelhar)")
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    # renomear mantém os pesos (o Blender renomeia os grupos junto)
    mexidos = {n for n in mexidos if n in arm.data.bones}
    return feitas, mexidos


def pesar_por_distancia(arm, malhas, suavizar=2, so_perto_de=None):
    """Pesos pelo inverso da distância aos 3 ossos mais perto (segmentos), com as fronteiras alisadas.
    Serve para qualquer corpo depois de mexer no esqueleto. Com `so_perto_de` (ossos mexidos), só os
    vértices mais perto desses ossos (ou presos a osso que sumiu) ganham peso novo; o resto fica."""
    mw = arm.matrix_world
    ossos = [b for b in arm.data.bones if b.parent is not None or len(arm.data.bones) == 1]
    if not ossos:
        return
    segs = [(np.array(mw @ b.head_local), np.array(mw @ b.tail_local)) for b in ossos]
    for obj in malhas:
        M = np.array(obj.matrix_world)
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        D = np.empty((len(co), len(segs)))
        for k, (a, b) in enumerate(segs):
            ab = b - a
            t = np.clip(((co - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
            D[:, k] = np.linalg.norm(co - (a + t[:, None] * ab), axis=1)
        tam = float(np.ptp(co, axis=0).max()) if len(co) else 1.0
        ordem = np.argsort(D, axis=1)[:, :3]
        eps = 0.01 * tam
        nomes = [b.name for b in ossos]
        refazer = np.ones(len(co), dtype=bool)
        if so_perto_de is not None:
            mexidos = {i for i, n in enumerate(nomes) if n in so_perto_de}
            existentes = set(nomes)
            sumidos = {g.index for g in obj.vertex_groups if g.name not in existentes}
            refazer = np.array([ordem[vi][0] in mexidos for vi in range(len(co))])
            for v in obj.data.vertices:
                if not refazer[v.index] and (not v.groups or any(g.group in sumidos and g.weight > 0.01 for g in v.groups)):
                    refazer[v.index] = True
            if not refazer.any():
                continue
            # tira os vértices refeitos de todos os grupos (e os grupos de ossos que sumiram)
            idx = [int(i) for i in np.nonzero(refazer)[0]]
            for g in list(obj.vertex_groups):
                if g.name not in existentes:
                    obj.vertex_groups.remove(g)
                else:
                    g.remove(idx)
            grupos = [obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n) for n in nomes]
        else:
            for g in list(obj.vertex_groups):
                obj.vertex_groups.remove(g)
            grupos = [obj.vertex_groups.new(name=n) for n in nomes]
        for vi in np.nonzero(refazer)[0]:
            ks = ordem[vi]
            d = D[vi, ks]
            # só entra quem está perto do mais perto (não puxa pele de outra parte do corpo)
            ok = d < d[0] * 1.8 + eps
            w = 1.0 / (d[ok] + eps) ** 4
            w /= w.sum()
            for k, peso in zip(ks[ok], w):
                if peso > 0.02:
                    grupos[k].add([int(vi)], float(peso), "REPLACE")
        for o in bpy.context.scene.objects:
            o.select_set(o == obj)
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
            if suavizar:
                bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=suavizar)
            bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
            bpy.ops.object.vertex_group_normalize_all(lock_active=False)
        finally:
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("esqueleto", "ARMATURE")
            mod.object = arm
        if obj.parent != arm:
            mundo = obj.matrix_world.copy()
            obj.parent = arm
            obj.matrix_parent_inverse = arm.matrix_world.inverted()
            obj.matrix_world = mundo
