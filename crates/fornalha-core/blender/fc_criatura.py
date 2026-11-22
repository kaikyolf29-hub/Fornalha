# Fornalha: criaturas com esqueleto próprio (o rig não trava em humanos). Começa pelo dragão:
# coluna longa, pescoço articulado, cauda com vários ossos, asas com membrana, mandíbula ("jaw", o
# mesmo nome dos humanos, para a engine abrir a boca pela fala/rugido) e quatro patas digitígradas.
# Malha orgânica pelo modificador Skin (raios por junta) + subdivisão, membrana das asas à parte,
# pesos pelo calor do Blender (com plano B por distância aos ossos) e animações procedurais.
# Eixos como no resto da Forja: frente = -Y, cima = +Z, esquerda = +X.
import math

import bmesh
import bpy
import numpy as np
from mathutils import Quaternion, Vector

FPS = 30
ANIMACOES_DRAGAO = ("parado", "andar", "correr", "voar", "rugir", "atacar", "atacar_2", "dano", "morrer")


def _V(*a):
    return Vector(a)


class Dragao:
    """Pontos do esqueleto (em metros, escala 1 ≈ 4 m de altura na cabeça, 10 m da cabeça à cauda)."""

    def __init__(self, escala=1.0):
        S = float(escala)
        self.S = S

        def P(x, y, z):
            return Vector((x * S, y * S, z * S))

        self.P = P
        # coluna (do quadril ao peito)
        self.coluna = [P(0, 0.8, 1.6), P(0, 0.25, 1.75), P(0, -0.35, 1.85), P(0, -0.85, 1.92), P(0, -1.15, 1.95)]
        # pescoço em S: sobe saindo do peito e vai para a frente; a cabeça fica à frente do peito
        self.pescoco = [P(0, -1.15, 1.95), P(0, -1.7, 2.35), P(0, -2.2, 2.7), P(0, -2.65, 2.92), P(0, -3.05, 3.02), P(0, -3.4, 3.05)]
        self.cabeca = [P(0, -3.4, 3.05), P(0, -4.3, 2.88)]
        self.jaw = [P(0, -3.5, 2.9), P(0, -4.2, 2.68)]
        cauda = [P(0, 0.8, 1.6)]
        for k in range(1, 11):
            t = k / 10
            cauda.append(P(0.25 * math.sin(t * 2.2) * t, 0.8 + 5.4 * t, 1.6 - 1.15 * t ** 0.8))
        self.cauda = cauda
        self.perna_tras = {}
        self.perna_frente = {}
        self.asa = {}
        for lado, s in (("l", 1), ("r", -1)):
            self.perna_tras[lado] = [P(s * 0.55, 0.55, 1.45), P(s * 0.68, -0.05, 0.92), P(s * 0.62, 0.55, 0.42), P(s * 0.62, 0.15, 0.07),
                                     P(s * 0.62, -0.32, 0.03)]
            self.perna_frente[lado] = [P(s * 0.55, -0.95, 1.55), P(s * 0.72, -0.62, 0.95), P(s * 0.68, -1.02, 0.36), P(s * 0.68, -1.27, 0.06),
                                       P(s * 0.68, -1.55, 0.03)]
            raiz = P(s * 0.42, -0.75, 2.25)
            cotovelo = P(s * 2.0, -0.35, 3.0)
            pulso = P(s * 3.8, -0.95, 3.35)
            dedos = [P(s * 6.0, -0.65, 3.05), P(s * 5.7, 0.75, 2.6), P(s * 4.1, 1.75, 2.25)]
            self.asa[lado] = {"raiz": raiz, "cotovelo": cotovelo, "pulso": pulso, "dedos": dedos, "costas": P(s * 0.38, 0.65, 2.0)}
        # chifres (saem de trás da cabeça para trás e para cima)
        self.chifres = {lado: [P(s * 0.16, -3.25, 3.25), P(s * 0.3, -2.85, 3.55), P(s * 0.34, -2.45, 3.62)] for lado, s in (("l", 1), ("r", -1))}

    # ------------------------------------------------------------------ esqueleto

    def ossos(self):
        """[(nome, cabeça, cauda, pai)] — a ordem garante o pai antes do filho."""
        b = []
        P = self.P
        b.append(("raiz", P(0, 0, 0), P(0, -0.6, 0), None))
        b.append(("quadril", self.coluna[0], self.coluna[0] + P(0, -0.3, 0.05), "raiz"))
        pai = "quadril"
        for k in range(len(self.coluna) - 1):
            nome = f"coluna_{k + 1}"
            b.append((nome, self.coluna[k], self.coluna[k + 1], pai))
            pai = nome
        peito = pai
        for k in range(len(self.pescoco) - 1):
            nome = f"pescoco_{k + 1}"
            b.append((nome, self.pescoco[k], self.pescoco[k + 1], pai))
            pai = nome
        b.append(("cabeca", self.cabeca[0], self.cabeca[1], pai))
        b.append(("jaw", self.jaw[0], self.jaw[1], "cabeca"))
        pai = "quadril"
        for k in range(len(self.cauda) - 1):
            nome = f"cauda_{k + 1}"
            b.append((nome, self.cauda[k], self.cauda[k + 1], pai))
            pai = nome
        for lado in ("l", "r"):
            t = self.perna_tras[lado]
            for k, nome in enumerate(("coxa", "canela", "tarso", "dedos_pe")):
                b.append((f"{nome}_{lado}", t[k], t[k + 1], "quadril" if k == 0 else f"{('coxa', 'canela', 'tarso')[k - 1]}_{lado}"))
            f = self.perna_frente[lado]
            for k, nome in enumerate(("ombro", "antebraco", "mao", "garras")):
                b.append((f"{nome}_{lado}", f[k], f[k + 1], peito if k == 0 else f"{('ombro', 'antebraco', 'mao')[k - 1]}_{lado}"))
            a = self.asa[lado]
            b.append((f"asa_umero_{lado}", a["raiz"], a["cotovelo"], "coluna_3"))
            b.append((f"asa_antebraco_{lado}", a["cotovelo"], a["pulso"], f"asa_umero_{lado}"))
            for k, ponta in enumerate(a["dedos"]):
                b.append((f"asa_dedo_{k + 1}_{lado}", a["pulso"], ponta, f"asa_antebraco_{lado}"))
        return b

    def esqueleto(self, nome):
        dados = bpy.data.armatures.new(nome + "_esqueleto")
        arm = bpy.data.objects.new(nome + "_esqueleto", dados)
        bpy.context.scene.collection.objects.link(arm)
        _ativo(arm)
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = {}
        for nome_osso, h, t, pai in self.ossos():
            eb = dados.edit_bones.new(nome_osso)
            eb.head, eb.tail = h, t
            if pai:
                eb.parent = ebs[pai]
                eb.use_connect = (ebs[pai].tail - h).length < 1e-4 and not nome_osso.startswith("asa_dedo_")
            ebs[nome_osso] = eb
        # rolagem coerente: o eixo Z de cada osso para cima (frente/trás nos ossos de pé)
        for eb in dados.edit_bones:
            eb.align_roll(Vector((0, 0, 1)) if abs(eb.vector.normalized().z) < 0.9 else Vector((0, -1, 0)))
        bpy.ops.object.mode_set(mode="OBJECT")
        return arm

    # ------------------------------------------------------------------ malha

    def _corrente(self, bm, skin, pontos, raios, inicio=None):
        """Vértices ligados em corrente com raio (rx, ry) por ponto. Devolve os vértices."""
        vs = []
        anterior = inicio
        for p, r in zip(pontos, raios):
            if anterior is not None and (anterior.co - p).length < 1e-5:
                v = anterior
            else:
                v = bm.verts.new(p)
                if anterior is not None:
                    bm.edges.new((anterior, v))
            v[skin].radius = r if isinstance(r, tuple) else (r, r)
            vs.append(v)
            anterior = v
        return vs

    def _bolas(self, mb, pontos, raios, passo=0.45, achatar=(1.0, 1.0)):
        """Esferas de metaball ao longo de uma corrente, com raio interpolado (fundem como argila)."""
        for k in range(len(pontos) - 1):
            a, b = pontos[k], pontos[k + 1]
            ra, rb = raios[k], raios[k + 1]
            n = max(1, int((b - a).length / (passo * max(min(ra, rb), 0.03 * self.S))))
            for i in range(n + (1 if k == len(pontos) - 2 else 0)):
                t = i / n
                r = ra + (rb - ra) * t
                e = mb.elements.new(type="ELLIPSOID")
                e.co = a.lerp(b, t)
                e.radius = r
                e.size_x, e.size_y, e.size_z = achatar[0], 1.0, achatar[1]
                e.stiffness = 2.0

    def corpo(self, nome):
        """Corpo, pescoço, cabeça, cauda e patas em metaballs → malha remalhada e reduzida para jogo."""
        S = self.S
        mb = bpy.data.metaballs.new(nome + "_massa")
        mb.resolution = 0.07 * S
        mb.render_resolution = 0.07 * S
        mb.threshold = 0.6
        R = lambda r: r * S * 1.25  # noqa: E731  (o metaball fica um pouco menor que o raio)
        # tronco: costela funda (mais alta que larga), barriga e quadril
        self._bolas(mb, self.coluna, [R(0.66), R(0.8), R(0.86), R(0.8), R(0.66)], achatar=(0.85, 1.12))
        self._bolas(mb, [self.P(0, -0.6, 1.55), self.P(0, 0.3, 1.5)], [R(0.66), R(0.6)], achatar=(0.95, 0.85))  # barriga
        self._bolas(mb, self.pescoco, [R(0.6), R(0.46), R(0.38), R(0.32), R(0.29), R(0.3)], passo=0.4, achatar=(0.9, 1.05))
        # cabeça: crânio, focinho, sobrancelhas, bochechas e mandíbula
        P = self.P
        c0, c1 = self.cabeca
        self._bolas(mb, [c0, c0.lerp(c1, 0.35), c1], [R(0.33), R(0.24), R(0.13)], passo=0.35, achatar=(0.9, 0.85))
        self._bolas(mb, self.jaw, [R(0.17), R(0.09)], passo=0.35, achatar=(0.95, 0.7))
        for s_ in (1, -1):
            lat = Vector((s_ * 0.14 * S, 0, 0))
            self._bolas(mb, [c0 + lat + Vector((0, -0.1 * S, 0.17 * S)), c0.lerp(c1, 0.35) + lat * 0.85 + Vector((0, 0, 0.08 * S))], [R(0.1), R(0.07)], passo=0.35)
            self._bolas(mb, [c0 + lat * 1.2 + Vector((0, -0.1 * S, -0.13 * S)), c0.lerp(c1, 0.45) + lat * 0.85 + Vector((0, 0, -0.1 * S))], [R(0.13), R(0.08)],
                        passo=0.35)
        n = len(self.cauda)
        self._bolas(mb, self.cauda, [R(0.66)] + [R(0.56 * (1 - k / (n - 0.5)) ** 1.25 + 0.025) for k in range(1, n)], passo=0.4,
                    achatar=(0.9, 1.0))
        for lado, s_ in (("l", 1), ("r", -1)):
            t = self.perna_tras[lado]
            # coxa musculosa (sai de dentro do quadril), canela, tarso e pé
            self._bolas(mb, [P(s_ * 0.3, 0.6, 1.5), t[0], t[1]], [R(0.5), R(0.46), R(0.24)], passo=0.35)
            self._bolas(mb, t[1:], [R(0.24), R(0.15), R(0.12), R(0.06)], passo=0.35)
            f = self.perna_frente[lado]
            self._bolas(mb, [P(s_ * 0.3, -0.95, 1.6), f[0], f[1]], [R(0.42), R(0.36), R(0.19)], passo=0.35)
            self._bolas(mb, f[1:], [R(0.19), R(0.12), R(0.1), R(0.05)], passo=0.35)
            # base da asa (músculo nas costas)
            a = self.asa[lado]
            self._bolas(mb, [P(s_ * 0.25, -0.7, 2.2), a["raiz"], a["raiz"].lerp(a["cotovelo"], 0.35)], [R(0.3), R(0.22), R(0.15)], passo=0.35)
        massa = bpy.data.objects.new(nome + "_massa", mb)
        bpy.context.scene.collection.objects.link(massa)
        _ativo(massa)
        bpy.ops.object.convert(target="MESH")
        obj = bpy.context.view_layer.objects.active
        obj.name = nome + "_corpo"
        obj.data.name = nome + "_corpo"
        # malha limpa e uniforme, depois reduzida para jogo
        m = obj.modifiers.new("remalha", "REMESH")
        m.mode = "VOXEL"
        m.voxel_size = 0.035 * S
        m.adaptivity = 0.0
        bpy.ops.object.modifier_apply(modifier=m.name)
        m = obj.modifiers.new("alisa", "SMOOTH")
        m.factor = 0.5
        m.iterations = 4
        bpy.ops.object.modifier_apply(modifier=m.name)
        alvo_tris = 36000
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        if tris > alvo_tris:
            m = obj.modifiers.new("reduz", "DECIMATE")
            m.ratio = alvo_tris / tris
            bpy.ops.object.modifier_apply(modifier=m.name)
        # ossos finos (dedos e braço das asas, chifres, garras) pelo Skin e juntos ao corpo
        finos = self._finos(nome)
        _ativo(obj)
        finos.select_set(True)
        bpy.ops.object.join()
        for p in obj.data.polygons:
            p.use_smooth = True
        return obj

    def _finos(self, nome):
        S = self.S
        bm = bmesh.new()
        skin = bm.verts.layers.skin.verify()
        R = lambda *r: tuple(x * S for x in r)  # noqa: E731
        raizes = []
        for lado in ("l", "r"):
            a = self.asa[lado]
            braco = self._corrente(bm, skin, [a["raiz"].lerp(a["cotovelo"], 0.25), a["cotovelo"], a["pulso"]], [R(0.13, 0.13), R(0.1, 0.1), R(0.08, 0.08)])
            raizes.append(braco[0])
            for ponta in a["dedos"]:
                self._corrente(bm, skin, [a["pulso"], a["pulso"].lerp(ponta, 0.5), ponta], [R(0.08, 0.08), R(0.045, 0.045), R(0.015, 0.015)],
                               inicio=braco[-1])
            c = self._corrente(bm, skin, self.chifres[lado], [R(0.09, 0.09), R(0.055, 0.055), R(0.01, 0.01)])
            raizes.append(c[0])
            for pata in (self.perna_tras[lado], self.perna_frente[lado]):
                base, ponta = pata[-2], pata[-1]
                for dx in (-0.09, 0.0, 0.09):
                    off = Vector((dx * S, 0, 0))
                    g = self._corrente(bm, skin, [base + off * 0.5 + Vector((0, 0, 0.03 * S)), ponta + off + Vector((0, -0.12 * S, -0.02 * S))],
                                       [R(0.04, 0.035), R(0.006, 0.006)])
                    raizes.append(g[0])
        for v in raizes:
            v[skin].use_root = True
        malha = bpy.data.meshes.new(nome + "_finos")
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        _ativo(obj)
        m = obj.modifiers.new("pele", "SKIN")
        m.use_smooth_shade = True
        bpy.ops.object.modifier_apply(modifier=m.name)
        m = obj.modifiers.new("lisa", "SUBSURF")
        m.levels = 1
        bpy.ops.object.modifier_apply(modifier=m.name)
        # marca para o material de osso (chifres e garras); os braços da asa ficam com a pele
        obj["_finos"] = True
        return obj

    def membrana(self, nome, lado):
        """Membrana da asa: polígono entre o braço, os dedos e as costas, com recortes entre os dedos."""
        a = self.asa[lado]
        d1, d2, d3 = a["dedos"]
        p = a["pulso"]

        def recorte(x, y, fundo=0.22):
            meio = x.lerp(y, 0.5)
            return meio.lerp(p, fundo)

        contorno = [a["raiz"], a["cotovelo"], p, d1, recorte(d1, d2), d2, recorte(d2, d3), d3, recorte(d3, a["costas"], 0.3), a["costas"]]
        bm = bmesh.new()
        vs = [bm.verts.new(c) for c in contorno]
        bm.faces.new(vs)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
        for _ in range(3):
            bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
        # leve barriga para baixo (a membrana não é uma placa reta)
        borda = {v for e in bm.edges if e.is_boundary for v in e.verts}
        for v in bm.verts:
            if v not in borda:
                d = min((v.co - b.co).length for b in borda)
                v.co.z -= min(0.25 * self.S, 0.18 * d)
        malha = bpy.data.meshes.new(f"{nome}_membrana_{lado}")
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        for pl in obj.data.polygons:
            pl.use_smooth = True
        _ativo(obj)
        m = obj.modifiers.new("espessura", "SOLIDIFY")
        m.thickness = 0.02 * self.S
        m.offset = 0.0
        bpy.ops.object.modifier_apply(modifier=m.name)
        return obj


# ------------------------------------------------------------------ utilidades


def _ativo(obj):
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj


def _segmento(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def pesos_por_distancia(obj, arm, permitidos=None, vizinhos=3, potencia=4.0):
    """Plano B (e membranas): peso pelo inverso da distância aos ossos permitidos (soma 1)."""
    co = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
    ossos = [b for b in arm.data.bones if b.name != "raiz" and (permitidos is None or b.name in permitidos)]
    mw = arm.matrix_world
    dist = np.stack([_segmento(co, np.array(mw @ b.head_local), np.array(mw @ b.tail_local)) for b in ossos], axis=1)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    grupos = {b.name: obj.vertex_groups.new(name=b.name) for b in ossos}
    ordem = np.argsort(dist, axis=1)[:, :vizinhos]
    for vi in range(len(co)):
        idx = ordem[vi]
        w = 1.0 / (dist[vi, idx] + 0.02 * arm.dimensions.length / 10) ** potencia
        w /= w.sum()
        for k, peso in zip(idx, w):
            if peso > 0.01:
                grupos[ossos[k].name].add([vi], float(peso), "REPLACE")


def vestir(obj, arm, permitidos=None):
    """Pesos pelo calor (bons em malha fechada); se o Blender não achar solução, por distância."""
    ok = False
    if permitidos is None:
        _ativo(arm)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            ok = bool(obj.vertex_groups) and any(
                g.weight > 0 for v in obj.data.vertices[: min(200, len(obj.data.vertices))] for g in v.groups
            )
        except RuntimeError as e:
            print(f"[criatura] pesos pelo calor falharam em {obj.name}: {e}")
    if not ok:
        pesos_por_distancia(obj, arm, permitidos)
        obj.parent = arm
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("esqueleto", "ARMATURE")
            mod.object = arm


def _uv(obj):
    _ativo(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.005)
    bpy.ops.object.mode_set(mode="OBJECT")


def _materiais(obj, nome, cores):
    """Dorso em couro escuro tingido, barriga mais clara (faces viradas para baixo), chifres e garras de osso."""
    import fc_pbr

    dorso = fc_pbr.material(f"{nome}_escamas", "couro_escuro", cores.get("principal") or "#4a1712", escala=6.0)
    barriga = fc_pbr.material(f"{nome}_barriga", "couro", cores.get("secundaria") or "#8a6a3c", escala=5.0)
    osso = bpy.data.materials.new(f"{nome}_chifre")
    osso.use_nodes = True
    bsdf = next(n for n in osso.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.55, 0.5, 0.42, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    obj.data.materials.append(dorso)
    obj.data.materials.append(barriga)
    obj.data.materials.append(osso)
    for p in obj.data.polygons:
        c = obj.matrix_world @ p.center
        if p.normal.z < -0.45 and c.z > 0.5:
            p.material_index = 1
    return dorso, osso


def marcar_osso(obj, pontos_chifre, pontas_garra, raio):
    """Faces perto dos chifres e das garras ganham o material de osso (índice 2)."""
    alvos = [np.array(p) for p in pontos_chifre + pontas_garra]
    for p in obj.data.polygons:
        c = np.array(obj.matrix_world @ p.center)
        if any(np.linalg.norm(c - a) < raio for a in alvos):
            p.material_index = 2


def _material_membrana(obj, nome, cores):
    import fc_pbr

    m = fc_pbr.material(f"{nome}_membrana", "couro", cores.get("membrana") or "#5a2318", escala=3.0)
    obj.data.materials.append(m)


# ------------------------------------------------------------------ escamas assadas


def _no(nt, tipo, **props):
    n = nt.nodes.new(tipo)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def _hex(h, padrao):
    h = (h or padrao).lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb] + [1.0]


def _material_escamas_procedural(nome, cores, S):
    """Escamas em Voronoi (centro alto, borda funda e mais escura, cada escama com o seu tom), barriga em
    placas transversais mais claras, rugosidade maior nas frestas. Só para assar."""
    mat = bpy.data.materials.new(nome + "_escamas_proc")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    L = nt.links.new
    saida = _no(nt, "ShaderNodeOutputMaterial")
    bsdf = _no(nt, "ShaderNodeBsdfPrincipled")
    coord = _no(nt, "ShaderNodeTexCoord")
    mapa = _no(nt, "ShaderNodeMapping")
    mapa.inputs["Scale"].default_value = (9.0 / S, 9.0 / S, 9.0 / S)  # escamas de ~10 cm no dorso
    L(coord.outputs["Object"], mapa.inputs["Vector"])
    vor = _no(nt, "ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    L(mapa.outputs["Vector"], vor.inputs["Vector"])
    vor_c = _no(nt, "ShaderNodeTexVoronoi", feature="F1")
    L(mapa.outputs["Vector"], vor_c.inputs["Vector"])
    # altura da escama: borda funda, centro abaulado
    alt = _no(nt, "ShaderNodeMapRange")
    alt.inputs["From Min"].default_value = 0.0
    alt.inputs["From Max"].default_value = 0.3
    L(vor.outputs["Distance"], alt.inputs["Value"])
    # barriga: normal virada para baixo; placas transversais (ondas ao longo do corpo)
    geo = _no(nt, "ShaderNodeNewGeometry")
    sep = _no(nt, "ShaderNodeSeparateXYZ")
    L(geo.outputs["Normal"], sep.inputs["Vector"])
    barriga = _no(nt, "ShaderNodeMapRange")
    barriga.inputs["From Min"].default_value = -0.25
    barriga.inputs["From Max"].default_value = -0.6
    L(sep.outputs["Z"], barriga.inputs["Value"])
    onda = _no(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y")
    onda.inputs["Scale"].default_value = 1.6 / S
    onda.inputs["Distortion"].default_value = 1.5
    L(coord.outputs["Object"], onda.inputs["Vector"])
    placa = _no(nt, "ShaderNodeMath", operation="POWER")
    L(onda.outputs["Fac"], placa.inputs[0])
    placa.inputs[1].default_value = 0.35
    altura = _no(nt, "ShaderNodeMix", data_type="FLOAT")
    L(barriga.outputs["Result"], altura.inputs["Factor"])
    L(alt.outputs["Result"], altura.inputs[2])
    L(placa.outputs[0], altura.inputs[3])
    bump = _no(nt, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = 0.02 * S
    L(altura.outputs[0], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # cor: tom por escama (cor do Voronoi), frestas escuras, barriga clara
    tom = _no(nt, "ShaderNodeSeparateColor")
    L(vor_c.outputs["Color"], tom.inputs["Color"])
    var = _no(nt, "ShaderNodeMapRange")
    var.inputs["To Min"].default_value = 0.72
    var.inputs["To Max"].default_value = 1.18
    L(tom.outputs["Red"], var.inputs["Value"])
    dorso = _no(nt, "ShaderNodeRGB")
    dorso.outputs[0].default_value = _hex(cores.get("principal"), "#4a1712")
    claro = _no(nt, "ShaderNodeRGB")
    claro.outputs[0].default_value = _hex(cores.get("secundaria"), "#8a6a3c")
    escuro = _no(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    escuro.inputs["Factor"].default_value = 1.0
    L(dorso.outputs[0], escuro.inputs[6])
    fresta = _no(nt, "ShaderNodeMapRange")
    fresta.inputs["To Min"].default_value = 0.18
    fresta.inputs["To Max"].default_value = 1.0
    L(alt.outputs["Result"], fresta.inputs["Value"])
    cinza = _no(nt, "ShaderNodeCombineColor")
    m1 = _no(nt, "ShaderNodeMath", operation="MULTIPLY")
    L(var.outputs["Result"], m1.inputs[0])
    L(fresta.outputs["Result"], m1.inputs[1])
    for c in ("Red", "Green", "Blue"):
        L(m1.outputs[0], cinza.inputs[c])
    L(cinza.outputs["Color"], escuro.inputs[7])
    cor = _no(nt, "ShaderNodeMix", data_type="RGBA")
    L(barriga.outputs["Result"], cor.inputs["Factor"])
    L(escuro.outputs[2], cor.inputs[6])
    L(claro.outputs[0], cor.inputs[7])
    L(cor.outputs[2], bsdf.inputs["Base Color"])
    rug = _no(nt, "ShaderNodeMapRange")
    rug.inputs["To Min"].default_value = 0.78
    rug.inputs["To Max"].default_value = 0.42
    L(alt.outputs["Result"], rug.inputs["Value"])
    L(rug.outputs["Result"], bsdf.inputs["Roughness"])
    L(bsdf.outputs["BSDF"], saida.inputs["Surface"])
    return mat, cor.outputs[2], rug.outputs["Result"]


def assar_escamas(obj, nome, cores, S, res=2048):
    """Assa as escamas procedurais em cor, normal e rugosidade (imagens que vão para o glb)."""
    mat, saida_cor, saida_rug = _material_escamas_procedural(nome, cores, S)
    originais = [ms.material for ms in obj.material_slots]
    for i in (0, 1):
        if i < len(obj.material_slots):
            obj.material_slots[i].material = mat
    imgs = {k: bpy.data.images.new(f"{nome}_escamas_{k}", res, res, alpha=False) for k in ("cor", "normal", "rugosidade")}
    for k in ("normal", "rugosidade"):
        imgs[k].colorspace_settings.name = "Non-Color"
    materiais = [m for m in {ms.material for ms in obj.material_slots} if m and m.use_nodes]
    alvos = {}
    for m in materiais:
        n = m.node_tree.nodes.new("ShaderNodeTexImage")
        alvos[m] = n
    cena = bpy.context.scene
    motor, amostras = cena.render.engine, cena.cycles.samples
    cena.render.engine = "CYCLES"
    cena.cycles.samples = 4
    try:
        cena.cycles.device = "CPU"
    except Exception:
        pass
    _ativo(obj)
    nt = mat.node_tree
    saida = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    emi = nt.nodes.new("ShaderNodeEmission")

    def assar(tipo, img):
        for m, n in alvos.items():
            n.image = img
            m.node_tree.nodes.active = n
        bpy.ops.object.bake(type=tipo, margin=8, use_clear=True, normal_space="TANGENT")

    try:
        nt.links.new(saida_cor, emi.inputs["Color"])
        nt.links.new(emi.outputs["Emission"], saida.inputs["Surface"])
        assar("EMIT", imgs["cor"])
        nt.links.new(saida_rug, emi.inputs["Color"])
        assar("EMIT", imgs["rugosidade"])
        nt.links.new(bsdf.outputs["BSDF"], saida.inputs["Surface"])
        assar("NORMAL", imgs["normal"])
    finally:
        cena.render.engine, cena.cycles.samples = motor, amostras
        for m, n in alvos.items():
            m.node_tree.nodes.remove(n)
    for img in imgs.values():
        img.pack()
    # material final de jogo: as três imagens
    final = bpy.data.materials.new(nome + "_escamas")
    final.use_nodes = True
    fnt = final.node_tree
    fb = next(n for n in fnt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = fnt.nodes.new("ShaderNodeTexImage")
    tc.image = imgs["cor"]
    fnt.links.new(tc.outputs["Color"], fb.inputs["Base Color"])
    tr = fnt.nodes.new("ShaderNodeTexImage")
    tr.image = imgs["rugosidade"]
    fnt.links.new(tr.outputs["Color"], fb.inputs["Roughness"])
    tn = fnt.nodes.new("ShaderNodeTexImage")
    tn.image = imgs["normal"]
    nm = fnt.nodes.new("ShaderNodeNormalMap")
    fnt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    fnt.links.new(nm.outputs["Normal"], fb.inputs["Normal"])
    for i in (0, 1):
        if i < len(obj.material_slots):
            obj.material_slots[i].material = final
    for m in originais[:2]:
        if m and m.users == 0:
            bpy.data.materials.remove(m)
    return final


# ------------------------------------------------------------------ animações


def _q(rotacoes):
    q = Quaternion()
    for eixo, graus in rotacoes:
        q = Quaternion({"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[eixo], math.radians(graus)) @ q
    return q


def _local(pb, q_mundo):
    R = pb.bone.matrix_local.to_3x3()
    return (R.inverted() @ q_mundo.to_matrix() @ R).to_quaternion()


def asa(lado, abrir=0.0, varrer=0.0, dobrar=0.0, dedos=0.0):
    """Asa em graus: abrir (sobe a asa), varrer (para trás), dobrar (cotovelo/pulso), dedos (fecha o leque)."""
    s = 1 if lado == "l" else -1
    return {
        f"asa_umero_{lado}": [("Z", s * varrer), ("Y", -s * abrir)],
        f"asa_antebraco_{lado}": [("Z", -s * dobrar), ("Y", s * dobrar * 0.3)],
        f"asa_dedo_1_{lado}": [("Z", -s * dedos * 0.6)],
        f"asa_dedo_2_{lado}": [("Z", -s * dedos)],
        f"asa_dedo_3_{lado}": [("Z", -s * dedos * 1.2)],
    }


def pose_apontada(arm, alvos):
    """Pose em que cada osso de `alvos` aponta a ponta para o ponto dado (mundo, na ordem pai → filho).
    Devolve {osso: quaternion local} para usar nas chaves."""
    from mathutils import Matrix

    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    bpy.context.view_layer.update()
    inv = arm.matrix_world.inverted()
    resultado = {}
    for nome, alvo in alvos:
        pb = arm.pose.bones[nome]
        cabeca = pb.matrix.translation.copy()
        atual = (pb.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
        desejado = ((inv @ alvo) - cabeca).normalized()
        giro = atual.rotation_difference(desejado).to_matrix().to_4x4()
        pb.matrix = Matrix.Translation(cabeca) @ giro @ Matrix.Translation(-cabeca) @ pb.matrix
        bpy.context.view_layer.update()
        resultado[nome] = pb.rotation_quaternion.copy()
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
    bpy.context.view_layer.update()
    return resultado


def asas_fechadas(arm, S=1.0):
    """Asas recolhidas como as de um morcego: cotovelo para trás e para baixo, pulso à frente perto do
    ombro, dedos deitados para trás ao longo do corpo."""
    alvos = []
    for lado, s in (("l", 1), ("r", -1)):
        P = lambda x, y, z: Vector((s * x * S, y * S, z * S))  # noqa: E731
        alvos += [
            (f"asa_umero_{lado}", P(1.05, 0.75, 2.45)),
            (f"asa_antebraco_{lado}", P(0.95, -0.85, 2.75)),
            (f"asa_dedo_1_{lado}", P(1.15, 2.4, 2.35)),
            (f"asa_dedo_2_{lado}", P(1.0, 2.6, 1.95)),
            (f"asa_dedo_3_{lado}", P(0.9, 1.9, 1.75)),
        ]
    return pose_apontada(arm, alvos)


def pata(osso_coxa, frente=0.0, joelho=0.0, lado="l", tras=True):
    """Passo de uma pata (graus): frente (para a frente), joelho (dobra)."""
    if tras:
        return {f"coxa_{lado}": [("X", -frente)], f"canela_{lado}": [("X", joelho)], f"tarso_{lado}": [("X", -joelho * 0.8)]}
    return {f"ombro_{lado}": [("X", -frente)], f"antebraco_{lado}": [("X", -joelho)], f"mao_{lado}": [("X", joelho * 0.7)]}


def cauda(curva=0.0, onda=0.0, fase=0.0, n=10, subir=0.0):
    """Cauda balançando: curva (para o lado), onda (ondulação), subir (ergue)."""
    return {f"cauda_{k}": [("Z", curva / n + onda * math.sin(fase - k * 0.6) / n * 2.5), ("X", -subir / n)] for k in range(1, n + 1)}


def pescoco(subir=0.0, virar=0.0, n=5):
    return {f"pescoco_{k}": [("X", -subir / n), ("Z", virar / n)] for k in range(1, n + 1)}


def juntar(*partes):
    """Junta poses: listas de rotações se somam; um quaternion pronto (pose apontada) vale como está."""
    p = {}
    for parte in partes:
        for k, v in parte.items():
            if isinstance(v, Quaternion) or isinstance(p.get(k), Quaternion):
                p[k] = v
            else:
                p[k] = p.get(k, []) + v
    return p


class AnimadorDragao:
    def __init__(self, arm, escala):
        self.arm = arm
        self.S = escala
        self.acoes = []

    def acao(self, nome, quadros, chaves, laco=True):
        """chaves: (quadro, poses, deslocamento do quadril em m (x, y, z))."""
        arm = self.arm
        ad = arm.animation_data or arm.animation_data_create()
        act = bpy.data.actions.new(nome)
        act.use_fake_user = True
        ad.action = act
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
        for quadro, poses, quadril in chaves:
            for pb in arm.pose.bones:
                pb.rotation_quaternion = Quaternion()
                pb.location = Vector()
                if pb.name in poses:
                    v = poses[pb.name]
                    pb.rotation_quaternion = v.copy() if isinstance(v, Quaternion) else _local(pb, _q(v))
            q = arm.pose.bones["quadril"]
            R = q.bone.matrix_local.to_3x3()
            q.location = R.inverted() @ (Vector(quadril or (0, 0, 0)) * self.S)
            for pb in arm.pose.bones:
                pb.keyframe_insert(data_path="rotation_quaternion", frame=quadro, group=pb.name)
            q.keyframe_insert(data_path="location", frame=quadro, group="quadril")
        try:
            act.use_frame_range = True
            act.frame_start = 1
            act.frame_end = quadros
            act.use_cyclic = laco
        except Exception:
            pass
        act["laco"] = laco
        self.acoes.append(act)
        return act

    def tudo(self):
        A = self.acao
        fech = asas_fechadas(self.arm, self.S)
        # parado: respira, cauda balança devagar, asas recolhidas
        A("parado", 90, [(1, juntar(fech, cauda(10, 6, 0), pescoco(0)), (0, 0, 0)),
                         (46, juntar(fech, cauda(-8, 6, math.pi), pescoco(5), {"coluna_3": [("X", 1.5)]}), (0, 0, 0.03)),
                         (91, juntar(fech, cauda(10, 6, 0), pescoco(0)), (0, 0, 0))])
        # andar: patas em diagonal (frente esquerda com trás direita), cauda serpenteando
        def passo(fase, amp, joelho, onda):
            s = math.sin(fase)
            return juntar(
                fech,
                pata("", amp * s, joelho * max(0, -math.cos(fase)), "l", True), pata("", -amp * s, joelho * max(0, math.cos(fase)), "r", True),
                pata("", -amp * s, joelho * max(0, math.cos(fase)), "l", False), pata("", amp * s, joelho * max(0, -math.cos(fase)), "r", False),
                cauda(0, onda, fase), pescoco(-4, 4 * math.sin(fase)), {"coluna_2": [("Z", 3 * s)], "coluna_4": [("Z", -3 * s)]})
        A("andar", 48, [(1 + k * 6, passo(k * math.pi / 4, 22, 30, 12), (0, 0, -0.03 * abs(math.sin(k * math.pi / 4)))) for k in range(9)])
        A("correr", 24, [(1 + k * 3, passo(k * math.pi / 4, 34, 45, 18), (0, 0, 0.08 * math.sin(k * math.pi / 4 * 2))) for k in range(9)])
        # voar: bate as asas (o cotovelo atrasa), patas recolhidas, corpo ondula
        def voo(fase):
            s = math.sin(fase)
            asas = {}
            for lado in ("l", "r"):
                asas.update(asa(lado, abrir=38 * s, varrer=-5, dobrar=18 * max(0.0, -s), dedos=-6 * s))
            return juntar(asas, pata("", -35, 60, "l", True), pata("", -35, 60, "r", True), pata("", -20, 70, "l", False),
                          pata("", -20, 70, "r", False), cauda(0, 8, fase, subir=10), pescoco(-10), {"coluna_3": [("X", 4 * s)]})
        A("voar", 30, [(1 + k * 5, voo(k * math.pi / 3), (0, 0, 0.6 + 0.12 * math.sin(k * math.pi / 3 + 1.0))) for k in range(7)])
        # rugir: ergue o pescoço, abre a boca e as asas
        abre = {}
        for lado in ("l", "r"):
            abre.update(asa(lado, abrir=25, varrer=-10, dobrar=10, dedos=-5))
        A("rugir", 60, [(1, juntar(fech, pescoco(0)), (0, 0, 0)), (14, juntar(abre, pescoco(30), {"cabeca": [("X", -20)], "jaw": [("X", 30)]}, cauda(0, 0, 0, subir=8)),
                        (0, 0.1, 0.1)), (44, juntar(abre, pescoco(26, 6), {"cabeca": [("X", -16)], "jaw": [("X", 34)]}), (0, 0.1, 0.1)),
                        (61, juntar(fech, pescoco(0)), (0, 0, 0))], laco=False)
        # atacar: bote com mordida
        A("atacar", 36, [(1, juntar(fech, pescoco(0)), (0, 0, 0)), (10, juntar(fech, pescoco(25, 0), {"cabeca": [("X", -10)], "jaw": [("X", 25)]}), (0, 0.25, 0.05)),
                         (18, juntar(fech, pescoco(-30), {"cabeca": [("X", 15)], "jaw": [("X", 2)]}, {"coluna_4": [("X", 6)]}), (0, -0.45, -0.1)),
                         (36, juntar(fech, pescoco(0)), (0, 0, 0))], laco=False)
        # atacar_2: chicotada da cauda girando o corpo
        A("atacar_2", 40, [(1, juntar(fech, cauda(0)), (0, 0, 0)), (14, juntar(fech, cauda(-60, 10, 0), {"coluna_2": [("Z", -12)], "coluna_3": [("Z", -10)]}), (0, 0, 0)),
                           (24, juntar(fech, cauda(80, 14, math.pi), {"coluna_2": [("Z", 14)], "coluna_3": [("Z", 12)]}), (0, 0, 0.05)),
                           (40, juntar(fech, cauda(0)), (0, 0, 0))], laco=False)
        A("dano", 20, [(1, juntar(fech, pescoco(0)), (0, 0, 0)), (6, juntar(fech, pescoco(15, -15), {"cabeca": [("Z", -12)], "jaw": [("X", 15)]}), (0, 0.2, 0)),
                       (20, juntar(fech, pescoco(0)), (0, 0, 0))], laco=False)
        caido = juntar(fech, pescoco(-35, 40), {"cabeca": [("Z", 25)], "jaw": [("X", 12)]}, cauda(30, 0, 0), pata("", 30, 70, "l", True),
                       pata("", 30, 70, "r", True), pata("", 40, 80, "l", False), pata("", 40, 80, "r", False))
        A("morrer", 50, [(1, juntar(fech, pescoco(0)), (0, 0, 0)), (16, juntar(fech, pescoco(20, 10), {"jaw": [("X", 30)]}), (0, 0, 0.1)),
                         (40, caido, (0.3, 0, -0.95)), (50, caido, (0.3, 0, -0.95))], laco=False)
        return self.acoes


def criar_dragao(p):
    """Dragão completo. Devolve (armadura, [malhas], ações)."""
    nome = p.get("id", "dragao")
    escala = float(p.get("escala") or (float(p.get("altura") or 4.0) / 4.0))
    d = Dragao(escala)
    arm = d.esqueleto(nome)
    corpo = d.corpo(nome)
    _uv(corpo)
    _materiais(corpo, nome, p.get("cores") or {})
    chifres = [pt for lado in ("l", "r") for pt in d.chifres[lado][1:]]
    garras = [pata[-1] + Vector((dx * escala, -0.06 * escala, 0)) for lado in ("l", "r") for pata in (d.perna_tras[lado], d.perna_frente[lado])
              for dx in (-0.09, 0.0, 0.09)]
    marcar_osso(corpo, chifres, garras, 0.16 * escala)
    if p.get("escamas", True):
        try:
            assar_escamas(corpo, nome, p.get("cores") or {}, escala, int(p.get("textura") or 4096))
        except Exception as e:  # sem as escamas, fica o couro tingido
            print(f"[criatura] escamas não assaram: {e}")
    vestir(corpo, arm)
    membranas = []
    for lado in ("l", "r"):
        mb = d.membrana(nome, lado)
        _uv(mb)
        _material_membrana(mb, nome, p.get("cores") or {})
        permitidos = {f"asa_umero_{lado}", f"asa_antebraco_{lado}", "asa_dedo_1_" + lado, "asa_dedo_2_" + lado, "asa_dedo_3_" + lado,
                      "coluna_2", "coluna_3", "quadril"}
        vestir(mb, arm, permitidos)
        membranas.append(mb)
    acoes = AnimadorDragao(arm, escala).tudo()
    arm.animation_data.action = acoes[0]
    return arm, [corpo] + membranas, acoes
