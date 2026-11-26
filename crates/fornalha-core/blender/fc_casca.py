"""Roupa e armadura feitas separadas, no corpo do manequim (create_garment).

A IA olha a referência e descreve a peça em partes que nascem do próprio corpo, então servem nele:
- casca: a pele de uma região do corpo (peito, costas, braço, coxa, canela...) alisada, afastada,
  com espessura, borda arredondada e subdivisão. Peitoral, espaldar, ombreira, braçal, grevas, camisa.
- faixa: um anel em volta do corpo numa altura ou em volta de um osso, seguindo o contorno de verdade
  (cinto, gola, bracelete, punho, cano da bota, faixa da coxa).
- saia: do quadril para baixo, pelo contorno do corpo, abrindo até a barra, com fendas (saia, túnica,
  sobreveste, cota de malha longa, capa curta).
- adorno: as peças da montagem livre (caixa, cilindro, esfera, torno, extrusao, tubo), soltas ou
  coladas na superfície de outra parte (cruz no peito, rebite, fivela, emblema).

Coordenadas do corpo, as do show_skeleton: x = esquerda do personagem, y = para trás, z = para cima,
metros; o personagem olha para -y.
"""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import fc_comum as c
import fc_pecas

TIPOS = ("casca", "faixa", "saia", "adorno")
# regiões em ossos do esqueleto de jogo (e dos nomes do Mixamo)
REGIOES = {
    "tronco": ["pelvis", "spine_01", "spine_02", "spine_03", "Hips", "Spine", "Spine1", "Spine2", "Chest", "UpperChest"],
    "peito": ["spine_02", "spine_03", "Spine1", "Spine2", "Chest", "UpperChest"],
    "barriga": ["spine_01", "Spine"],
    "quadril": ["pelvis", "Hips"],
    "pescoco": ["neck_01", "neck_02", "Neck"],
    "cabeca": ["head", "Head"],
    "clavicula_l": ["clavicle_l", "LeftShoulder"], "clavicula_r": ["clavicle_r", "RightShoulder"],
    "ombro_l": ["clavicle_l", "upperarm_l", "LeftShoulder", "LeftArm", "LeftUpperArm"],
    "ombro_r": ["clavicle_r", "upperarm_r", "RightShoulder", "RightArm", "RightUpperArm"],
    "braco_l": ["upperarm_l", "LeftArm", "LeftUpperArm"], "braco_r": ["upperarm_r", "RightArm", "RightUpperArm"],
    "antebraco_l": ["lowerarm_l", "LeftForeArm", "LeftLowerArm"], "antebraco_r": ["lowerarm_r", "RightForeArm", "RightLowerArm"],
    "mao_l": ["hand_l", "LeftHand"], "mao_r": ["hand_r", "RightHand"],
    "coxa_l": ["thigh_l", "LeftUpLeg", "LeftUpperLeg"], "coxa_r": ["thigh_r", "RightUpLeg", "RightUpperLeg"],
    "canela_l": ["calf_l", "LeftLeg", "LeftLowerLeg"], "canela_r": ["calf_r", "RightLeg", "RightLowerLeg"],
    "pe_l": ["foot_l", "ball_l", "LeftFoot", "LeftToeBase"], "pe_r": ["foot_r", "ball_r", "RightFoot", "RightToeBase"],
}
for _k in ("ombro", "braco", "antebraco", "mao", "coxa", "canela", "pe", "clavicula"):
    REGIOES[_k] = REGIOES[_k + "_l"] + REGIOES[_k + "_r"]
REGIOES["braco_inteiro_l"] = REGIOES["braco_l"] + REGIOES["antebraco_l"]
REGIOES["braco_inteiro_r"] = REGIOES["braco_r"] + REGIOES["antebraco_r"]
REGIOES["perna_l"] = REGIOES["coxa_l"] + REGIOES["canela_l"]
REGIOES["perna_r"] = REGIOES["coxa_r"] + REGIOES["canela_r"]
FRENTE = Vector((0.0, -1.0, 0.0))


# ------------------------------------------------------------------ corpo

class Corpo:
    """A pele do manequim no repouso: vértices, triângulos, normais e quanto cada vértice é de cada osso."""

    def __init__(self, arm, malhas):
        self.arm = arm
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        # a pele: a malha do corpo pelo nome, senão a com pesos de mais vértices (roupa e cabelo ficam de fora)
        por_nome = [o for o in malhas if any(k in o.name.lower() for k in ("corpo", "body", "pele", "base"))]
        pele = max(por_nome or malhas, key=lambda o: len(o.data.vertices))
        self.obj = pele
        me = pele.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        M = np.array(pele.matrix_world, dtype=np.float64)
        self.co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        me.calc_loop_triangles()
        tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tri)
        self.tri = tri.reshape(-1, 3)
        self.grupos = {g.index: g.name for g in pele.vertex_groups}
        self.pesos = {}
        for v in me.vertices:
            for ge in v.groups:
                if ge.weight > 0.01:
                    nome = self.grupos.get(ge.group)
                    if nome:
                        self.pesos.setdefault(nome, np.zeros(n, dtype=np.float32))[v.index] = ge.weight
        self.z0 = float(self.co[:, 2].min())
        self.z1 = float(self.co[:, 2].max())
        self.H = self.z1 - self.z0

    def ossos(self, regiao):
        nomes = regiao if isinstance(regiao, list) else REGIOES.get(regiao, [regiao])
        achados = [n for n in nomes if n in self.pesos]
        if not achados:
            raise ValueError(f"a região {regiao!r} não achou ossos com pele neste corpo (regiões: {', '.join(sorted(REGIOES))})")
        return achados

    def peso(self, nomes):
        w = np.zeros(len(self.co), dtype=np.float32)
        for n in nomes:
            w += self.pesos[n]
        return w

    def osso(self, nome):
        b = self.arm.data.bones.get(nome)
        if b is None:
            raise ValueError(f"o osso {nome!r} não existe neste esqueleto")
        mw = self.arm.matrix_world
        return mw @ b.head_local, mw @ b.tail_local

    def sem_bracos(self):
        """Máscara da pele que não é do braço: com os braços para baixo, a mão fica na altura do quadril e
        a saia e o cinto dariam a volta nela."""
        nomes = [n for n in self.pesos if any(n.startswith(k) for k in ("upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky",
                                                                           "Left", "Right")) and not any(k in n for k in ("Leg", "Foot", "Toe", "UpLeg"))]
        return self.peso(nomes) < 0.5 if nomes else np.ones(len(self.co), dtype=bool)

    def corte(self, ponto, normal, perto=None, raio=None, so=None):
        """Contorno da pele cortada por um plano: pontos (N×3). Com perto/raio, só os pedaços perto do ponto;
        com `so` (máscara de vértices), só os triângulos dessa parte da pele."""
        p = np.asarray(ponto, dtype=np.float64)
        nrm = np.asarray(normal, dtype=np.float64)
        nrm = nrm / max(np.linalg.norm(nrm), 1e-9)
        d = (self.co - p) @ nrm
        tri = self.tri if so is None else self.tri[so[self.tri].all(1)]
        sd = d[tri]
        lado = sd > 0
        cruzam = lado.any(1) & ~lado.all(1)
        pts = []
        for t, s in zip(tri[cruzam], sd[cruzam]):
            for a, b in ((0, 1), (1, 2), (2, 0)):
                if (s[a] > 0) != (s[b] > 0):
                    k = s[a] / (s[a] - s[b])
                    pts.append(self.co[t[a]] + k * (self.co[t[b]] - self.co[t[a]]))
        pts = np.array(pts) if pts else np.zeros((0, 3))
        if perto is not None and raio is not None and len(pts):
            pts = pts[np.linalg.norm(pts - np.asarray(perto), axis=1) < raio]
        return pts


def _base_do_plano(normal):
    n = Vector(normal).normalized()
    u = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
    u = (u - n * u.dot(n)).normalized()
    v = n.cross(u).normalized()
    return u, v, n


def _casco_2d(pts):
    """Fecho convexo (monotone chain) de pontos 2D: a volta da roupa por fora do corpo."""
    p = sorted(set(map(tuple, np.round(pts, 6))))
    if len(p) < 3:
        return np.array(p)

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    baixo, cima = [], []
    for q in p:
        while len(baixo) >= 2 and cruz(baixo[-2], baixo[-1], q) <= 0:
            baixo.pop()
        baixo.append(q)
    for q in reversed(p):
        while len(cima) >= 2 and cruz(cima[-2], cima[-1], q) <= 0:
            cima.pop()
        cima.append(q)
    return np.array(baixo[:-1] + cima[:-1])


def _reamostrar(laco, n, inicio=None):
    """Laço fechado 2D → n pontos igualmente espaçados (começando no ângulo `inicio`, se dado)."""
    fech = np.vstack([laco, laco[:1]])
    seg = np.linalg.norm(np.diff(fech, axis=0), axis=1)
    acc = np.concatenate([[0], np.cumsum(seg)])
    total = acc[-1]
    centro = laco.mean(0)
    desloc = 0.0
    if inicio is not None:
        ang = np.arctan2(laco[:, 1] - centro[1], laco[:, 0] - centro[0])
        i0 = int(np.argmin(np.abs(((ang - inicio) + np.pi) % (2 * np.pi) - np.pi)))
        desloc = acc[i0]
    alvo = (desloc + np.linspace(0, total, n, endpoint=False)) % total
    xs = np.interp(alvo, acc, fech[:, 0])
    ys = np.interp(alvo, acc, fech[:, 1])
    return np.stack([xs, ys], 1)


def _afastar_2d(laco, d):
    """Afasta o laço convexo d metros para fora (pelo centro e pela normal do segmento)."""
    centro = laco.mean(0)
    out = []
    for i, p in enumerate(laco):
        a, b = laco[i - 1], laco[(i + 1) % len(laco)]
        t = b - a
        nrm = np.array([t[1], -t[0]])
        nrm /= max(np.linalg.norm(nrm), 1e-9)
        if nrm @ (p - centro) < 0:
            nrm = -nrm
        out.append(p + nrm * d)
    return np.array(out)


# ------------------------------------------------------------------ peças

def _materiais(id_, spec):
    mats = fc_pecas._materiais(id_, spec)
    return mats, (next(iter(mats.values()), None) or c.material(f"{id_}_padrao", c.cor_hex("#8a8580"), 0.6))


def _objeto_de_bmesh(nome, bm, material):
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(nome, me)
    bpy.context.scene.collection.objects.link(o)
    if material is not None:
        me.materials.append(material)
    return o


def _aplicar(o, mods):
    bpy.context.view_layer.objects.active = o
    for o2 in bpy.context.scene.objects:
        o2.select_set(o2 == o)
    for m in mods:
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError:
            o.modifiers.remove(m)


def _acabamento(o, espessura, borda, detalhe, para_dentro=True):
    """Espessura (para dentro: a face de fora fica onde a IA pôs), borda arredondada e subdivisão."""
    mods = []
    if espessura > 0:
        s = o.modifiers.new("espessura", "SOLIDIFY")
        s.thickness = espessura
        s.offset = -1.0 if para_dentro else 1.0
        s.use_even_offset = True
        s.use_rim = True
        s.use_quality_normals = True
        mods.append(s)
    if borda > 0:
        b = o.modifiers.new("borda", "BEVEL")
        b.width = borda
        b.segments = 3
        b.limit_method = "ANGLE"
        b.angle_limit = math.radians(40)
        b.harden_normals = False
        mods.append(b)
    if detalhe > 0:
        sub = o.modifiers.new("detalhe", "SUBSURF")
        sub.levels = sub.render_levels = int(detalhe)
        mods.append(sub)
    _aplicar(o, mods)
    for p in o.data.polygons:
        p.use_smooth = True
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
    except Exception:
        pass


def _casca(corpo, nome, p, mat):
    ossos = corpo.ossos(p.get("regiao", "tronco"))
    w = corpo.peso(ossos)
    minimo = float(p.get("peso_minimo", 0.5))
    sel = w >= minimo
    de, ate = p.get("de"), p.get("ate")
    if de is not None:
        sel &= corpo.co[:, 2] >= float(de)
    if ate is not None:
        sel &= corpo.co[:, 2] <= float(ate)
    if p.get("x_min") is not None:
        sel &= corpo.co[:, 0] >= float(p["x_min"])
    if p.get("x_max") is not None:
        sel &= corpo.co[:, 0] <= float(p["x_max"])
    tri = corpo.tri[sel[corpo.tri].all(1)]
    if p.get("lado") in ("frente", "costas"):
        a, b, cc = (corpo.co[tri[:, i]] for i in range(3))
        nrm = np.cross(b - a, cc - a)
        frente = nrm[:, 1] < 0  # o personagem olha para -y
        corte = float(p.get("corte", 0.0))
        ny = -nrm[:, 1] / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
        tri = tri[ny >= corte] if p["lado"] == "frente" else tri[ny <= -corte]
        del frente
    if len(tri) < 8:
        raise ValueError(f"a casca {nome!r} pegou pele demais pouca ({len(tri)} triângulos): confira regiao, de/ate e lado")
    usados, inv = np.unique(tri, return_inverse=True)
    bm = bmesh.new()
    vs = [bm.verts.new(Vector(corpo.co[i])) for i in usados]
    inv = inv.reshape(-1, 3)
    for t in inv:
        try:
            bm.faces.new((vs[t[0]], vs[t[1]], vs[t[2]]))
        except ValueError:
            pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    # triângulos do corpo viram quadrados onde der (subdivisão mais limpa)
    bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=math.radians(40), angle_shape_threshold=math.radians(40))
    # alisar: tira a anatomia (músculo, mamilo, dedos) e deixa a forma de placa ou pano
    for _ in range(int(p.get("alisar", 12))):
        bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    # a pele vira roupa: para fora, pela normal (média com a direção do osso mais perto não precisa: alisada já basta)
    afastar = float(p.get("afastar", 0.012))
    for v in bm.verts:
        v.co += v.normal * afastar
    # borda solta da casca: um pouco para dentro (a ponta não fica rente à pele)
    o = _objeto_de_bmesh(nome, bm, mat)
    _acabamento(o, float(p.get("espessura", 0.006)), float(p.get("borda", 0.003)), int(p.get("detalhe", 1)))
    return o


def _laco_do_corpo(corpo, ponto, normal, raio, afastar, lados, inicio=None, so=None):
    u, v, n = _base_do_plano(normal)
    pts = corpo.corte(ponto, n, perto=ponto, raio=raio, so=so)
    if len(pts) < 6:
        return None
    P = Vector(ponto)
    q = np.array([[(Vector(x) - P).dot(u), (Vector(x) - P).dot(v)] for x in pts])
    casco = _casco_2d(q)
    if len(casco) < 3:
        return None
    laco = _reamostrar(_afastar_2d(casco, afastar), lados, inicio)
    return [P + u * float(a) + v * float(b) for a, b in laco], (u, v, n)


def _anel(bm, laco, n, largura, espessura):
    """Faixa: o laço vira um anel com largura (ao longo de n) e espessura (para fora)."""
    centro = sum(laco, Vector()) / len(laco)
    camadas = []
    for dz in (-largura / 2, largura / 2):
        for fora in (0.0, espessura):
            linha = []
            for p in laco:
                r = (p - centro)
                r = r - n * r.dot(n)
                r = r.normalized() if r.length > 1e-9 else Vector((1, 0, 0))
                linha.append(bm.verts.new(p + n * dz + r * fora))
            camadas.append(linha)
    # camadas: 0 = embaixo dentro, 1 = embaixo fora, 2 = em cima dentro, 3 = em cima fora
    N = len(laco)
    for a, b in ((0, 1), (1, 3), (3, 2), (2, 0)):
        for i in range(N):
            j = (i + 1) % N
            try:
                bm.faces.new((camadas[a][i], camadas[a][j], camadas[b][j], camadas[b][i]))
            except ValueError:
                pass


def _faixa(corpo, nome, p, mat):
    lados = int(p.get("lados", 64))
    largura = float(p.get("largura", 0.05))
    espessura = float(p.get("espessura", 0.006))
    afastar = float(p.get("afastar", 0.008))
    if p.get("osso"):
        h, t = corpo.osso(p["osso"])
        k = float(p.get("ao_longo", 0.5))
        ponto = h.lerp(t, k)
        normal = (t - h).normalized()
        raio = float(p.get("raio", 0.12 * corpo.H))
        # só a pele desse osso e dos vizinhos (o plano do braço também corta o tronco perto do sovaco)
        b = corpo.arm.data.bones[p["osso"]]
        vizinhos = [x.name for x in [b, b.parent, *b.children] if x is not None and x.name in corpo.pesos]
        so = corpo.peso(vizinhos) >= 0.3 if vizinhos else None
    else:
        if p.get("altura") is None:
            raise ValueError(f"a faixa {nome!r} precisa de altura (z em metros) ou de osso")
        z = float(p["altura"])
        ponto = Vector((float(p.get("x", 0.0)), float(p.get("y", 0.0)), z))
        normal = Vector((0, 0, 1))
        raio = float(p.get("raio", 0.35 * corpo.H))
        so = corpo.sem_bracos()
    r = _laco_do_corpo(corpo, ponto, normal, raio, afastar, lados, so=so)
    if r is None:
        raise ValueError(f"a faixa {nome!r} não achou o corpo nessa altura/osso")
    laco, (_, _, n) = r
    bm = bmesh.new()
    _anel(bm, laco, n, largura, espessura)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _objeto_de_bmesh(nome, bm, mat)
    _acabamento(o, 0.0, float(p.get("borda", min(0.002, espessura / 3))), int(p.get("detalhe", 1)))
    return o


def _saia(corpo, nome, p, mat):
    """Do quadril até a barra pelo contorno do corpo (as duas pernas juntas), abrindo para baixo."""
    z0 = float(p.get("de", corpo.z0 + 0.53 * corpo.H))
    z1 = float(p.get("ate", corpo.z0 + 0.25 * corpo.H))
    if z1 >= z0:
        raise ValueError("saia: 'ate' (a barra) tem de ficar abaixo de 'de' (a cintura)")
    lados = int(p.get("lados", 72))
    aneis = int(p.get("aneis", max(8, int((z0 - z1) / 0.04))))
    abrir = float(p.get("abrir", 0.08))
    afastar = float(p.get("afastar", 0.015))
    fendas = p.get("fendas") or []
    fenda_altura = float(p.get("fenda_altura", 0.5))
    centro = Vector((0, 0, 0))
    pelve = corpo.arm.data.bones.get("pelvis") or corpo.arm.data.bones.get("Hips")
    if pelve is not None:
        centro = corpo.arm.matrix_world @ pelve.head_local
    linhas = []
    ultimo = None
    so = corpo.sem_bracos()
    for i in range(aneis + 1):
        t = i / aneis
        z = z0 + (z1 - z0) * t
        ponto = Vector((centro.x, centro.y, z))
        r = _laco_do_corpo(corpo, ponto, Vector((0, 0, 1)), 0.45 * corpo.H, afastar + abrir * t * t, lados, inicio=-math.pi / 2, so=so)
        if r is None:
            if ultimo is None:
                continue
            laco = [Vector((q.x, q.y, z)) + (Vector((q.x, q.y, 0)) - Vector((centro.x, centro.y, 0))).normalized() * (abrir * t * t * 0.3) for q in ultimo]
        else:
            laco = r[0]
        ultimo = laco
        linhas.append(laco)
    if len(linhas) < 2:
        raise ValueError("saia: não achei o corpo entre 'de' e 'ate'")
    # o contorno sai de pernas separadas (a barra embaixo dos joelhos): o fecho convexo já junta as duas;
    # alisa a descida entre os anéis para não ondular
    pts = np.array([[list(q) for q in laco] for laco in linhas])
    for _ in range(int(p.get("alisar", 3))):
        pts[1:-1] = 0.25 * pts[:-2] + 0.5 * pts[1:-1] + 0.25 * pts[2:]
    bm = bmesh.new()
    vs = [[bm.verts.new(Vector(q)) for q in linha] for linha in pts]
    # fendas: ângulos (graus; 0 = frente, 90 = esquerda do personagem, 180 = costas) abertas da barra até fenda_altura
    def aberta(i, j):
        if not fendas:
            return False
        t = i / (len(vs) - 1)
        if t < 1.0 - fenda_altura:
            return False
        ang = (j / lados) * 360.0
        return any(abs(((ang - float(f)) + 180) % 360 - 180) < (180.0 / lados) * 1.01 for f in fendas)

    for i in range(len(vs) - 1):
        for j in range(lados):
            if aberta(i, j):
                continue
            k = (j + 1) % lados
            bm.faces.new((vs[i][j], vs[i][k], vs[i + 1][k], vs[i + 1][j]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # normais para fora
    bm.normal_update()
    meio = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    fora = sum(((f.calc_center_median() - meio).dot(f.normal) for f in bm.faces), 0.0)
    if fora < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    o = _objeto_de_bmesh(nome, bm, mat)
    _acabamento(o, float(p.get("espessura", 0.005)), float(p.get("borda", 0.002)), int(p.get("detalhe", 1)))
    return o


def _adorno(corpo, nome, p, mats, padrao, feitos):
    spec = dict(p)
    spec["tipo"] = p.get("forma", "caixa")
    obj, avisos = fc_pecas.montar({"id": nome, "pecas": [spec], "materiais": {}})
    m = mats.get(p.get("material")) or padrao
    obj.data.materials.clear()
    obj.data.materials.append(m)
    alvo = p.get("colar")
    if alvo:
        dono = feitos.get(alvo)
        if dono is None:
            raise ValueError(f"adorno {nome!r}: colar em {alvo!r}, mas essa parte não existe (antes dele na lista)")
        ponto = p.get("ponto")
        if not ponto or len(ponto) < 2:
            raise ValueError(f"adorno {nome!r}: diga o ponto [x, z] onde colar")
        lado = p.get("lado", "frente")
        x, z = float(ponto[0]), float(ponto[-1])
        origem = Vector((x, -5.0, z)) if lado == "frente" else Vector((x, 5.0, z))
        direcao = Vector((0, 1, 0)) if lado == "frente" else Vector((0, -1, 0))
        dg = bpy.context.evaluated_depsgraph_get()
        inv = dono.matrix_world.inverted()
        ok, loc, nrm, _ = dono.evaluated_get(dg).ray_cast(inv @ origem, (inv.to_3x3() @ direcao).normalized())
        if not ok:
            raise ValueError(f"adorno {nome!r}: o ponto {ponto} não cai em cima de {alvo!r}")
        loc = dono.matrix_world @ loc
        nrm = (dono.matrix_world.to_3x3() @ nrm).normalized()
        # a peça foi descrita de frente (como na foto): o -y dela vira a normal da superfície
        R = nrm.to_track_quat("-Y", "Z").to_matrix().to_4x4()
        afundar = float(p.get("afundar", 0.0))
        obj.matrix_world = Matrix.Translation(loc - nrm * afundar) @ R @ obj.matrix_world
    return obj, avisos


def montar(arm, malhas, spec):
    """{"id", "pecas": [...], "materiais": {...}} no corpo do manequim → lista de objetos (uma malha por parte)."""
    id_ = spec.get("id", "roupa")
    pecas = spec.get("pecas") or []
    if not pecas:
        raise ValueError("a roupa precisa de peças (pecas)")
    if len(pecas) > 200:
        raise ValueError("no máximo 200 partes por roupa")
    corpo = Corpo(arm, malhas)
    mats, padrao = _materiais(id_, spec.get("materiais"))
    feitos, avisos, ordem = {}, [], []
    for i, p in enumerate(pecas):
        tipo = p.get("tipo")
        if tipo not in TIPOS:
            raise ValueError(f"parte {i}: tipo {tipo!r} desconhecido (use {', '.join(TIPOS)})")
        nome = str(p.get("nome") or f"{tipo}_{i}")
        mat = mats.get(p.get("material")) or padrao
        if p.get("material") and p["material"] not in mats:
            avisos.append(f"parte {nome}: material {p['material']!r} não está em materiais (usei o primeiro)")
        try:
            if tipo == "casca":
                o = _casca(corpo, nome, p, mat)
            elif tipo == "faixa":
                o = _faixa(corpo, nome, p, mat)
            elif tipo == "saia":
                o = _saia(corpo, nome, p, mat)
            else:
                o, av = _adorno(corpo, nome, p, mats, padrao, feitos)
                avisos += av
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"parte {i} ({nome}, {tipo}): {e}") from e
        o.name = f"{id_}_{nome}"
        espelho = p.get("espelhar") if tipo != "adorno" else None
        if espelho == "x":
            copia = o.copy()
            copia.data = o.data.copy()
            bpy.context.scene.collection.objects.link(copia)
            copia.name = f"{id_}_{nome}_espelho"
            bm = bmesh.new()
            bm.from_mesh(copia.data)
            for v in bm.verts:
                v.co.x = -v.co.x
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
            bm.to_mesh(copia.data)
            bm.free()
            ordem.append(copia)
        feitos[nome] = o
        ordem.append(o)
    for o in ordem:
        c.uv_mundo([o], escala=float(spec.get("escala_uv", 2.0)))
    corpo.arm.data.pose_position = "POSE"
    return ordem, avisos, corpo
