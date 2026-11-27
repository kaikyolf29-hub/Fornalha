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

TIPOS = ("casca", "faixa", "saia", "adorno", "rebites")
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
for _l in ("l", "r"):
    _dedos = [f"{d}_0{i}_{_l}" for d in ("thumb", "index", "middle", "ring", "pinky") for i in (1, 2, 3)]
    _L = "Left" if _l == "l" else "Right"
    _dedos += [f"{_L}Hand{d}{i}" for d in ("Thumb", "Index", "Middle", "Ring", "Pinky") for i in (1, 2, 3)]
    REGIOES[f"mao_inteira_{_l}"] = REGIOES[f"mao_{_l}"] + _dedos
for _k in ("ombro", "braco", "antebraco", "mao", "mao_inteira", "coxa", "canela", "pe", "clavicula"):
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

    def arvore(self):
        """Busca do ponto mais perto da pele (com a normal de fora)."""
        if getattr(self, "_arvore", None) is None:
            from mathutils.bvhtree import BVHTree

            self._arvore = BVHTree.FromPolygons([tuple(x) for x in self.co], [tuple(int(i) for i in t) for t in self.tri])
        return self._arvore

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
        # onde a reta do centro nesse ângulo cruza o laço (no meio de um lado, se for o caso): a frente da
        # saia fica no meio mesmo entre as duas pernas, não no canto do joelho mais perto
        d = np.array([math.cos(inicio), math.sin(inicio)])
        for i in range(len(laco)):
            a, b = fech[i], fech[i + 1]
            m = np.array([[d[0], a[0] - b[0]], [d[1], a[1] - b[1]]])
            if abs(np.linalg.det(m)) < 1e-12:
                continue
            r, f = np.linalg.solve(m, a - centro)
            if r > 0 and -1e-9 <= f <= 1 + 1e-9:
                desloc = acc[i] + f * seg[i]
                break
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

def _textura_de_malha(nome, cor, lado=1024, aneis=48):
    """Cota de malha de verdade: anéis entrelaçados (fileiras desencontradas), em imagem (vai no glb para o
    jogo): cor (metal com o vão escuro) e normal (o relevo do anel). 1 metro = 2 voltas da textura."""
    s = lado / aneis
    yy, xx = np.mgrid[0:lado, 0:lado].astype(np.float32) + 0.5
    R, t = 0.36 * s, 0.13 * s
    h = np.zeros((lado, lado), dtype=np.float32)
    passo_y = s * 0.5
    j0 = np.floor(yy / passo_y)
    for dj in (-1, 0, 1, 2):
        j = j0 + dj
        cy = j * passo_y
        desloc = (np.mod(j, 2)) * s * 0.5
        i0 = np.round((xx - desloc) / s)
        for di in (-1, 0, 1):
            cx = (i0 + di) * s + desloc
            dx = (xx - cx + lado / 2) % lado - lado / 2
            dy = (yy - cy + lado / 2) % lado - lado / 2
            d = np.sqrt(dx * dx + dy * dy)
            anel = np.sqrt(np.clip(t * t - (d - R) ** 2, 0, None)) / t
            h = np.maximum(h, anel)
    gy, gx = np.gradient(h)
    forca = 2.2
    nx, ny, nz = -gx * forca, -gy * forca, np.ones_like(h)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([nx / n * 0.5 + 0.5, ny / n * 0.5 + 0.5, nz / n * 0.5 + 0.5, np.ones_like(h)], -1)
    vao = np.clip(h * 3.0, 0, 1)[..., None]
    base = np.array(cor[:3], dtype=np.float32)
    cor_px = base * (0.25 + 0.75 * vao) * (0.85 + 0.15 * h[..., None])
    cor_img = np.concatenate([cor_px, np.ones((lado, lado, 1), dtype=np.float32)], -1)
    imgs = []
    for sufixo, px, dados in (("cor", cor_img, False), ("normal", normal, True)):
        img = bpy.data.images.new(f"{nome}_{sufixo}", lado, lado, alpha=False)
        if dados:
            img.colorspace_settings.name = "Non-Color"
        img.pixels.foreach_set(px.astype(np.float32).ravel())
        img.pack()
        imgs.append(img)
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = imgs[0]
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = imgs[1]
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.42
    m["uv_mundo"] = True
    return m


def _metal_usado(nome, cor, desgaste=0.5, rugosidade=0.25, lado=1024, semente=7):
    """Metal com marcas de uso, em imagem (vai no glb): riscos finos em várias direções (mais claros e
    mais lisos), amassados e pontos de corrosão (mais escuros e ásperos), manchas largas de tom e a
    rugosidade variando. `desgaste` de 0 (polido) a 1 (de campanha). 1 m = 2 voltas da textura."""
    rng = np.random.default_rng(semente)
    d = float(np.clip(desgaste, 0.0, 1.0))
    H = W = lado

    def ruido(escala, oitavas=4):
        out = np.zeros((H, W), dtype=np.float32)
        amp, soma = 1.0, 0.0
        for o in range(oitavas):
            n = max(2, int(escala * 2 ** o))
            g = rng.random((n + 1, n + 1)).astype(np.float32)
            g[-1, :], g[:, -1] = g[0, :], g[:, 0]  # emenda sem costura
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            fy, fx = yy / H * n, xx / W * n
            y0, x0 = np.floor(fy).astype(int), np.floor(fx).astype(int)
            ty, tx = fy - y0, fx - x0
            ty, tx = ty * ty * (3 - 2 * ty), tx * tx * (3 - 2 * tx)
            v = (g[y0, x0] * (1 - tx) + g[y0, x0 + 1] * tx) * (1 - ty) + (g[y0 + 1, x0] * (1 - tx) + g[y0 + 1, x0 + 1] * tx) * ty
            out += amp * v
            soma += amp
            amp *= 0.5
        return out / soma

    manchas = ruido(3, 4)  # tom e sujeira largos
    riscos = np.zeros((H, W), dtype=np.float32)
    # muitos riscos finos e fracos (o polimento gasto), poucos maiores; quase todos na mesma direção
    for i in range(int(250 + 1400 * d)):
        grande = i % 25 == 0
        x, y = rng.random() * W, rng.random() * H
        ang = rng.normal(0.4, 0.45 if not grande else 0.9)
        n = int(rng.uniform(25, 90) if grande else rng.uniform(4, 22))
        xs = (x + np.cos(ang) * np.arange(n)) % W
        ys = (y + np.sin(ang) * np.arange(n)) % H
        forca = rng.uniform(0.35, 0.7) if grande else rng.uniform(0.08, 0.3)
        riscos[ys.astype(int), xs.astype(int)] = np.maximum(riscos[ys.astype(int), xs.astype(int)], forca)
    pontos = np.zeros((H, W), dtype=np.float32)
    for _ in range(int(20 + 160 * d)):
        x, y = int(rng.random() * W), int(rng.random() * H)
        r = int(rng.uniform(1, 2 + 3 * d))
        yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
        disco = np.clip(1 - np.sqrt(xx * xx + yy * yy) / (r + 0.5), 0, 1)
        ys, xs = (np.arange(y - r, y + r + 1) % H)[:, None], (np.arange(x - r, x + r + 1) % W)[None, :]
        pontos[ys, xs] = np.maximum(pontos[ys, xs], disco * rng.uniform(0.4, 1.0))
    base = np.array(cor[:3], dtype=np.float32)
    tom = 1.0 - 0.18 * d * (manchas - 0.5) * 2 - 0.25 * d * pontos + 0.16 * riscos
    cor_px = np.clip(base[None, None, :] * tom[..., None], 0, 1)
    # o que mais mostra o uso no metal é a rugosidade: riscos um pouco mais foscos, manchas variando
    rug = np.clip(rugosidade + 0.3 * d * manchas + 0.25 * d * pontos + 0.1 * riscos, 0.05, 0.95)
    altura = -0.4 * riscos - 0.6 * pontos * d + 0.1 * manchas
    gy, gx = np.gradient(altura)
    nx, ny, nz = -gx * 2.0, -gy * 2.0, np.ones_like(altura)
    nn = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([nx / nn * 0.5 + 0.5, ny / nn * 0.5 + 0.5, nz / nn * 0.5 + 0.5], -1)
    um = np.ones((H, W, 1), dtype=np.float32)
    imgs = {}
    for sufixo, px, dados in (("cor", np.concatenate([cor_px, um], -1), False),
                              ("rugosidade", np.concatenate([np.repeat(rug[..., None], 3, -1), um], -1), True),
                              ("normal", np.concatenate([normal, um], -1), True)):
        img = bpy.data.images.new(f"{nome}_{sufixo}", W, H, alpha=False)
        if dados:
            img.colorspace_settings.name = "Non-Color"
        img.pixels.foreach_set(px.astype(np.float32).ravel())
        img.pack()
        imgs[sufixo] = img
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED")
    tc, tr, tn = (nt.nodes.new("ShaderNodeTexImage") for _ in range(3))
    tc.image, tr.image, tn.image = imgs["cor"], imgs["rugosidade"], imgs["normal"]
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Metallic"].default_value = 1.0
    m["uv_mundo"] = True
    return m


def _materiais(id_, spec):
    spec = dict(spec or {})
    malhas = {k: v for k, v in spec.items() if isinstance(v, dict) and str(v.get("tipo", "")).lower() in ("malha", "cota")}
    usados = {k: v for k, v in spec.items() if isinstance(v, dict) and str(v.get("tipo", "")).lower() == "metal" and float(v.get("desgaste", 0) or 0) > 0}
    for k in list(malhas) + list(usados):
        spec.pop(k)
    mats = fc_pecas._materiais(id_, spec)
    for k, v in malhas.items():
        mats[k] = _textura_de_malha(f"{id_}_{k}_malha", c.cor_hex(v.get("cor", "#7b7e83")))
    for k, v in usados.items():
        mats[k] = _metal_usado(f"{id_}_{k}_metal_usado", c.cor_hex(v.get("cor", "#c6cbd1")), float(v["desgaste"]), float(v.get("rugosidade", 0.25)))
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
        # espessura simples: a "igual" joga vértice longe nas dobras fechadas (espinhos de 1 m no elmo)
        s.use_even_offset = False
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
    if p.get("perto_de"):
        # em volta de uma junta (cotoveleira, joelheira, pomo do ombro): a cabeça do osso dado (ou um
        # ponto ao_longo dele), num raio
        h, t = corpo.osso(p["perto_de"])
        centro = np.array(h.lerp(t, float(p.get("ao_longo", 0.0))))
        sel &= np.linalg.norm(corpo.co - centro, axis=1) <= float(p.get("raio", 0.07))
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
    if p.get("convexa"):
        # o fecho usa os vértices da região inteira (com de/ate e x_min/x_max), sem o filtro de lado:
        # o lado abre depois, no casco
        idx = np.nonzero(sel)[0]
        if len(idx) < 12:
            raise ValueError(f"a casca {nome!r} não achou pele nessa região/altura")
        if p.get("forma") == "elmo_fechado":
            o = _elmo_fechado(nome, p, mat, corpo.co[idx])
        else:
            o = _convexa(corpo, nome, p, mat, corpo.co[idx], ossos)
        # placa (elmo, ombreira, braçal, greva, joelheira, sabatão): vestida, fica rígida no osso dela
        o["rigido"] = bool(p.get("rigido", True))
        return o
    if len(tri) < 8:
        raise ValueError(f"a casca {nome!r} pegou pele demais pouca ({len(tri)} triângulos): confira regiao, de/ate e lado")
    # só a pele de fora: tira o que aponta para dentro do osso (boca, órbita do olho, orelha por dentro)
    segs = [corpo.osso(n) for n in ossos if corpo.arm.data.bones.get(n) is not None]
    if segs:
        a, b, cc = (corpo.co[tri[:, i]] for i in range(3))
        centro = (a + b + cc) / 3
        nrm = np.cross(b - a, cc - a)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        melhor = np.full(len(tri), np.inf)
        dirs = np.zeros_like(centro)
        for h, t in segs:
            h, t = np.array(h), np.array(t)
            seg = t - h
            k = np.clip(((centro - h) @ seg) / max(seg @ seg, 1e-12), 0, 1)
            perto = h + k[:, None] * seg
            d = centro - perto
            dist = np.linalg.norm(d, axis=1)
            troca = dist < melhor
            melhor[troca] = dist[troca]
            dirs[troca] = d[troca]
        dirs /= np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-12)
        tri = tri[(nrm * dirs).sum(1) > -0.1]
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
    _limpar_e_fechar(bm)
    # triângulos do corpo viram quadrados onde der (subdivisão mais limpa)
    bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=math.radians(40), angle_shape_threshold=math.radians(40))
    _alisar_borda(bm, 6)
    # alisar: tira a anatomia (músculo, mamilo, dedos) e deixa a forma de placa ou pano
    for _ in range(int(p.get("alisar", 12))):
        bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    # a pele vira roupa: para fora, pela normal
    afastar = float(p.get("afastar", 0.012))
    for v in bm.verts:
        v.co += v.normal * afastar
    # alisar encolhe a casca (no músculo da coxa ela afundava dentro da pele e a pele aparecia por cima da
    # cota no movimento): o que ficou dentro do corpo volta para fora, até a distância pedida
    arv = corpo.arvore()
    for v in bm.verts:
        perto, nrm, _, _ = arv.find_nearest(v.co)
        if perto is None:
            continue
        d = (v.co - perto).dot(nrm)
        if d < afastar * 0.9:
            v.co += nrm * (afastar - d)
    lacos = _lacos_da_borda(bm)
    o = _objeto_de_bmesh(nome, bm, mat)
    _guardar_borda(o, lacos)
    _acabamento(o, float(p.get("espessura", 0.006)), float(p.get("borda", 0.003)), int(p.get("detalhe", 1)))
    return o


def _limpar_e_fechar(bm):
    """Tira pedacinhos soltos e fecha os furos pequenos (olho, boca, narina) da casca; a abertura grande
    (pescoço, punho, cintura) fica."""
    # pedaços: fica só o que tem pelo menos 5% das faces do maior
    vistos, pedacos = set(), []
    for f in bm.faces:
        if f in vistos:
            continue
        pilha, grupo = [f], []
        vistos.add(f)
        while pilha:
            x = pilha.pop()
            grupo.append(x)
            for e in x.edges:
                for y in e.link_faces:
                    if y not in vistos:
                        vistos.add(y)
                        pilha.append(y)
        pedacos.append(grupo)
    if len(pedacos) > 1:
        maior = max(len(g) for g in pedacos)
        soltos = [f for g in pedacos if len(g) < 0.05 * maior for f in g]
        if soltos:
            bmesh.ops.delete(bm, geom=soltos, context="FACES")
    # laços de borda
    borda = {e for e in bm.edges if e.is_boundary}
    lacos = []
    while borda:
        e0 = borda.pop()
        laco, pilha = [e0], [e0]
        while pilha:
            e = pilha.pop()
            for v in e.verts:
                for e2 in v.link_edges:
                    if e2 in borda:
                        borda.discard(e2)
                        laco.append(e2)
                        pilha.append(e2)
        lacos.append(laco)
    if len(lacos) > 1:
        comp = [sum(e.calc_length() for e in laco) for laco in lacos]
        maior = max(comp)
        for laco, L in zip(lacos, comp):
            if L < 0.35 * maior:
                r = bmesh.ops.holes_fill(bm, edges=laco, sides=0)
                novas = r.get("faces", [])
                if novas:
                    bmesh.ops.triangulate(bm, faces=novas)


def _alisar_borda(bm, vezes=6):
    """A beira da casca sai em dente (o corte segue os triângulos do corpo): alisa a beira ao longo dela."""
    borda = [v for v in bm.verts if v.is_boundary]
    for _ in range(vezes):
        novo = {}
        for v in borda:
            viz = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(viz) == 2:
                novo[v] = v.co * 0.5 + (viz[0].co + viz[1].co) * 0.25
        for v, co in novo.items():
            v.co = co


def _elmo_fechado(nome, p, mat, pontos):
    """Elmo fechado (great helm, barbuta, elmo de balde): um cilindro de frente chata e costas redondas
    em volta da cabeça, topo quase plano com a quina arredondada, aberto embaixo, e uma nervura no meio
    da cara (a quina da frente). Visor, frestas e rebites vão por cima como adorno e rebites."""
    P = np.asarray(pontos, dtype=np.float64)
    afastar = float(p.get("afastar", 0.02))
    x0, x1 = P[:, 0].min(), P[:, 0].max()
    y0, y1 = P[:, 1].min(), P[:, 1].max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    a = (x1 - x0) / 2 + afastar
    b = (y1 - y0) / 2 + afastar
    z_base = float(p.get("de", P[:, 2].min()))
    z_topo = P[:, 2].max() + afastar
    quina = min(0.025, 0.3 * a)
    nervura = float(p.get("nervura", 0.012))
    lados = 96

    def contorno(th, s=1.0):
        # superelipse: frente (-y) quase reta, costas redondas; a nervura puxa o meio da frente
        c, sn = math.cos(th), math.sin(th)
        n = 5.0 if sn < 0 else 2.2
        x = a * math.copysign(abs(c) ** (2 / n), c)
        y = b * math.copysign(abs(sn) ** (2 / n), sn)
        if sn < 0:
            y -= nervura * max(0.0, 1.0 - abs(c) / 0.12) * (-sn)
        return cx + x * s, cy + y * s

    aneis = []
    n_parede = max(6, int((z_topo - quina - z_base) / 0.015))
    for i in range(n_parede + 1):
        aneis.append((z_base + (z_topo - quina - z_base) * i / n_parede, 1.0))
    for k in range(1, 7):  # quina arredondada
        f = math.radians(90 * k / 6)
        aneis.append((z_topo - quina + quina * math.sin(f), 1.0 - (quina / a) * (1 - math.cos(f))))
    s_fim = aneis[-1][1]
    for k in range(1, 8):  # topo quase plano, levemente abaulado
        s_ = s_fim * (1 - k / 8)
        aneis.append((z_topo + 0.012 * (1 - (s_ / s_fim) ** 2), s_))
    bm = bmesh.new()
    anel_v = []
    for z, s_ in aneis:
        anel_v.append([bm.verts.new((*contorno(2 * math.pi * j / lados - math.pi / 2, s_), z)) for j in range(lados)])
    for i in range(len(anel_v) - 1):
        for j in range(lados):
            j2 = (j + 1) % lados
            bm.faces.new((anel_v[i][j], anel_v[i][j2], anel_v[i + 1][j2], anel_v[i + 1][j]))
    topo = bm.verts.new((cx, cy, z_topo + 0.012))
    for j in range(lados):
        bm.faces.new((anel_v[-1][j], anel_v[-1][(j + 1) % lados], topo))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lacos = _lacos_da_borda(bm)
    o = _objeto_de_bmesh(nome, bm, mat)
    for f in o.data.polygons:
        f.use_smooth = True
    _guardar_borda(o, lacos)
    _acabamento(o, float(p.get("espessura", 0.004)), float(p.get("borda", 0.003)), int(p.get("detalhe", 1)))
    return o


def _convexa(corpo, nome, p, mat, pontos, ossos):
    """Casca convexa (elmo, ombreira, joelheira, sabatão, capuz): o fecho dos pontos da região, refeito em
    malha uniforme, alisado e aberto do lado pedido. Não copia nariz, boca nem dedos."""
    bm = bmesh.new()
    for q in pontos:
        bm.verts.new(Vector(q))
    r = bmesh.ops.convex_hull(bm, input=list(bm.verts))
    sobra = list({g for g in r.get("geom_interior", []) + r.get("geom_unused", []) if isinstance(g, bmesh.types.BMVert) and g.is_valid})
    if sobra:
        bmesh.ops.delete(bm, geom=sobra, context="VERTS")
    o = _objeto_de_bmesh(nome + "_casco", bm, None)
    rm = o.modifiers.new("uniforme", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = float(p.get("resolucao", 0.008 * corpo.H / 1.8))
    sm = o.modifiers.new("liso", "SMOOTH")
    sm.factor = 0.6
    sm.iterations = int(p.get("alisar", 6))
    _aplicar(o, [rm, sm])
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bpy.data.objects.remove(o, do_unlink=True)
    bm.normal_update()
    # afasta pela normal (o fecho já passa por fora da pele nas pontas)
    afastar = float(p.get("afastar", 0.012))
    for v in bm.verts:
        v.co += v.normal * afastar
    bm.normal_update()
    # abrir: tira o lado pedido (frente aberta do capuz, dentro da ombreira, sola do sabatão); abrir_pontas
    # abre as duas pontas pelo eixo do osso (braçal, greva, manga: serve em braço inclinado também)
    eixo = None
    if p.get("abrir_pontas") and ossos:
        h, t = corpo.osso(ossos[0])
        if (t - h).length > 1e-6:
            eixo = (t - h).normalized()
    tirar = []
    lado = p.get("lado")
    for f in bm.faces:
        n = f.normal
        c0 = f.calc_center_median()
        if lado == "frente" and n.y > -float(p.get("corte", 0.0)):
            tirar.append(f)
        elif lado == "costas" and n.y < float(p.get("corte", 0.0)):
            tirar.append(f)
        elif p.get("so_fora") and (Vector((c0.x, c0.y, 0)) - Vector((0, 0, 0))).length > 1e-6:
            fora = Vector((c0.x, c0.y, 0)).normalized()
            if n.dot(fora) < float(p.get("so_fora", 0.0)):
                tirar.append(f)
        elif eixo is not None and abs(n.dot(eixo)) > 0.75:
            tirar.append(f)
        elif p.get("abrir_embaixo") and n.z < -0.6:
            tirar.append(f)
        elif p.get("abrir_em_cima") and n.z > 0.6:
            tirar.append(f)
        if p.get("de") is not None and c0.z < float(p["de"]) and f not in tirar:
            tirar.append(f)
        if p.get("ate") is not None and c0.z > float(p["ate"]) and f not in tirar:
            tirar.append(f)
    if tirar and len(tirar) < len(bm.faces):
        bmesh.ops.delete(bm, geom=tirar, context="FACES")
    _alisar_borda(bm, 8)
    n_laminas = int(p.get("laminas", 0))
    if n_laminas >= 2:
        # eixo das lâminas: o do último osso da região (o braço na ombreira, a canela na greva)
        h, t = corpo.osso(ossos[-1])
        eixo_l = (t - h).normalized() if (t - h).length > 1e-6 else Vector((0, 0, -1))
        espessura = float(p.get("espessura", 0.004))
        novo = _laminas(bm, eixo_l, min(8, n_laminas), float(p.get("passo_laminas", max(0.01, espessura * 2.5))))
        bm.free()
        bm = novo
    lacos = _lacos_da_borda(bm)
    o = _objeto_de_bmesh(nome, bm, mat)
    _guardar_borda(o, lacos)
    _acabamento(o, float(p.get("espessura", 0.004)), float(p.get("borda", 0.003)), int(p.get("detalhe", 1)))
    return o


def _lacos_da_borda(bm):
    """Laços da beira da casca (antes da espessura), em pontos, para os rebites seguirem a beira."""
    borda = {e for e in bm.edges if e.is_boundary}
    lacos = []
    while borda:
        e0 = borda.pop()
        v0 = e0.verts[0]
        laco, v, e = [v0.co.copy()], e0.other_vert(v0), e0
        for _ in range(100000):
            laco.append(v.co.copy())
            prox = [x for x in v.link_edges if x in borda]
            if not prox:
                break
            e = prox[0]
            borda.discard(e)
            v = e.other_vert(v)
        if len(laco) >= 4:
            lacos.append(laco)
    return lacos


def _guardar_borda(o, lacos):
    pts, tam = [], []
    for laco in lacos:
        tam.append(len(laco))
        for q in laco:
            pts += [float(q.x), float(q.y), float(q.z)]
    o["fc_borda"] = pts
    o["fc_borda_tam"] = tam


def _ler_borda(o):
    pts, tam = list(o.get("fc_borda", [])), list(o.get("fc_borda_tam", []))
    lacos, i = [], 0
    for n in tam:
        lacos.append([Vector(pts[3 * k:3 * k + 3]) for k in range(i, i + int(n))])
        i += int(n)
    return lacos


def _laminas(bm, eixo, n, passo, sobre=0.18):
    """A placa em `n` lâminas sobrepostas ao longo do eixo (ombreira, cotoveleira, sabatão): cada faixa
    sai um pouco mais para fora que a de cima, como as lâminas articuladas da armadura de verdade."""
    ts = [v.co.dot(eixo) for v in bm.verts]
    t0, t1 = min(ts), max(ts)
    L = (t1 - t0) / n
    final = bmesh.new()
    for k in range(n):
        a, b = t0 + k * L - sobre * L, t0 + (k + 1) * L + sobre * L
        parte = bm.copy()
        fora = [f for f in parte.faces if not (a <= f.calc_center_median().dot(eixo) <= b)]
        if fora:
            bmesh.ops.delete(parte, geom=fora, context="FACES")
        if not parte.faces:
            parte.free()
            continue
        parte.normal_update()
        # cada lâmina sai mais na beira de baixo (abre em leque) e cobre o começo da de baixo, como
        # telhas: a beira de cada uma aparece como um degrau
        for v in parte.verts:
            rel = min(1.0, max(0.0, (v.co.dot(eixo) - a) / max(b - a, 1e-6)))
            # todas começam no mesmo lugar e abrem `passo` na beira de baixo: a beira de cada lâmina fica
            # um degrau acima do começo da de baixo (sem inchar a peça inteira)
            v.co += v.normal * (passo * (0.3 + rel))
        _alisar_borda(parte, 4)
        me = bpy.data.meshes.new("fc_lamina_tmp")
        parte.to_mesh(me)
        parte.free()
        final.from_mesh(me)
        bpy.data.meshes.remove(me)
    return final


def _limitar_triangulos(o, maximo):
    """Diminui a malha (colapso, que guarda a forma) até o máximo de triângulos."""
    o.data.calc_loop_triangles()
    n = len(o.data.loop_triangles)
    if maximo <= 0 or n <= maximo:
        return n
    d = o.modifiers.new("limite", "DECIMATE")
    d.decimate_type = "COLLAPSE"
    d.ratio = max(0.01, maximo / n)
    d.use_collapse_triangulate = False
    _aplicar(o, [d])
    o.data.calc_loop_triangles()
    return len(o.data.loop_triangles)


LIMITE_POR_TIPO = {"casca": 24000, "saia": 24000, "faixa": 6000, "adorno": 6000, "rebites": 30000}


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
        # inclinação (graus): em volta da frente (o cinto desce para um lado; dois com sinais trocados
        # fazem os cintos cruzados) e em volta do lado (a frente mais baixa que as costas)
        normal = (Matrix.Rotation(math.radians(float(p.get("inclinacao", 0.0))), 3, "Y")
                  @ Matrix.Rotation(math.radians(float(p.get("inclinacao_frente", 0.0))), 3, "X")) @ Vector((0, 0, 1))
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
    # a linha do meio, por fora do cinto: tachas e rebites vão em fila nela (recuo 0)
    meio = sum(laco, Vector()) / len(laco)
    fora = [q + (q - meio).normalized() * espessura for q in laco]
    _guardar_borda(o, [fora + [fora[0]]])
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
    # abertura: graus abertos de cima a baixo, centrados em `abertura_centro` (0 = frente): capa (aberta na
    # frente), avental (aberto atrás), tabardo (os dois lados)
    abertura = float(p.get("abertura", 0.0))
    abertura_centro = float(p.get("abertura_centro", 0.0))
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
    # dobras do pano (crescem para a barra) e barra em ponta na frente/atrás (sobreveste, tabardo)
    dobras = int(p.get("dobras", 0))
    fundo = float(p.get("dobra_profundidade", 0.012))
    ponta_f, ponta_c = float(p.get("ponta_frente", 0.0)), float(p.get("ponta_costas", 0.0))
    # com fendas, a ponta é um V do tamanho do painel (da frente: entre as fendas mais perto de 0°; de
    # trás: perto de 180°), como a barra do tabardo; sem fendas, uma curva suave
    ang_f = [a % 360 for a in fendas]
    meia_f = math.radians(min([a for a in ang_f if 0 < a <= 180] + [360 - a for a in ang_f if a > 180] or [0]))
    meia_c = math.radians(min([abs(180 - a) for a in ang_f] or [0]))

    def _ponta(ang):
        a = (ang + math.pi) % (2 * math.pi) - math.pi  # -pi..pi, 0 = frente
        if meia_f > 0:
            f = ponta_f * max(0.0, 1.0 - abs(a) / meia_f)
        else:
            f = ponta_f * max(0.0, math.cos(a)) ** 3
        b = math.pi - abs(a)  # distância até as costas
        if meia_c > 0:
            k = ponta_c * max(0.0, 1.0 - b / meia_c)
        else:
            k = ponta_c * max(0.0, -math.cos(a)) ** 3
        return f + k

    n_aneis = len(pts)
    for i in range(n_aneis):
        t = i / max(1, n_aneis - 1)
        meio = pts[i].mean(0)
        for j in range(lados):
            ang = 2 * math.pi * j / lados
            if dobras:
                radial = pts[i, j, :2] - meio[:2]
                nr = np.linalg.norm(radial)
                if nr > 1e-6:
                    pts[i, j, :2] += radial / nr * fundo * (t ** 1.3) * math.sin(dobras * ang)
            if ponta_f or ponta_c:
                pts[i, j, 2] -= t * _ponta(ang)
    bm = bmesh.new()
    vs = [[bm.verts.new(Vector(q)) for q in linha] for linha in pts]
    # fendas: ângulos (graus; 0 = frente, 90 = esquerda do personagem, 180 = costas) abertas da barra até fenda_altura
    def aberta(i, j):
        meio = ((j + 0.5) / lados) * 360.0
        if abertura > 0 and abs(((meio - abertura_centro) + 180) % 360 - 180) < abertura / 2:
            return True
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
    spec = {k: v for k, v in p.items() if k not in ("material", "nome", "colar", "ponto", "lado")}
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
        u, z = float(ponto[0]), float(ponto[-1])
        # frente/costas: ponto [x, z]; esquerda/direita (ombreira, lado da coxa): ponto [y, z]
        origem, direcao = {
            "frente": (Vector((u, -5.0, z)), Vector((0, 1, 0))),
            "costas": (Vector((u, 5.0, z)), Vector((0, -1, 0))),
            "esquerda": (Vector((5.0, u, z)), Vector((-1, 0, 0))),
            "direita": (Vector((-5.0, u, z)), Vector((1, 0, 0))),
        }.get(lado, (Vector((u, -5.0, z)), Vector((0, 1, 0))))
        dg = bpy.context.evaluated_depsgraph_get()
        inv = dono.matrix_world.inverted()
        ok, loc, nrm, _ = dono.evaluated_get(dg).ray_cast(inv @ origem, (inv.to_3x3() @ direcao).normalized())
        if not ok:
            # diz onde a parte está nessa coluna, para a IA acertar o ponto sem tentar às cegas
            eixo_u = 0 if lado in ("frente", "costas") else 1
            mw = dono.matrix_world
            zs = [(mw @ v.co).z for v in dono.data.vertices if abs((mw @ v.co)[eixo_u] - u) < 0.02]
            onde = (f"; perto de {u:+.2f} ela vai de z {min(zs):.2f} a {max(zs):.2f}" if zs else "; ela não passa por essa coluna")
            raise ValueError(f"adorno {nome!r}: o ponto {ponto} não cai em cima de {alvo!r}{onde}")
        loc = dono.matrix_world @ loc
        nrm = (dono.matrix_world.to_3x3() @ nrm).normalized()
        # a peça foi descrita de frente (como na foto): o -y dela vira a normal da superfície
        obj["colado_em"] = dono.name
        R = nrm.to_track_quat("-Y", "Z").to_matrix().to_4x4()
        afundar = float(p.get("afundar", 0.0))
        # a altura de cada ponto acima da base da peça (no -y dela), antes de virar: é o que fica por
        # cima da superfície depois de assentar
        alturas = [max(0.0, -v.co.y) for v in obj.data.vertices]
        obj.matrix_world = Matrix.Translation(loc - nrm * afundar) @ R @ obj.matrix_world
        if p.get("conformar", True):
            # a peça plana assenta na superfície curva (peito, ombreira): picada em triângulos pequenos
            # (até 8 mm), cada ponto vai para a superfície mais perto, mais a própria altura pela normal
            # dali — os braços da cruz dobram com o peito em vez de afundar no pano
            from mathutils.bvhtree import BVHTree

            bmc = bmesh.new()
            bmc.from_mesh(obj.data)
            bmesh.ops.triangulate(bmc, faces=bmc.faces)
            for _ in range(6):
                longas = [e for e in bmc.edges if e.calc_length() > 0.008]
                if not longas:
                    break
                bmesh.ops.subdivide_edges(bmc, edges=longas, cuts=1, use_grid_fill=False)
                bmesh.ops.triangulate(bmc, faces=[f for f in bmc.faces if len(f.verts) > 3])
            bmc.to_mesh(obj.data)
            bmc.free()
            obj.data.update()
            # as alturas de novo (com os pontos novos): as coordenadas locais ainda são as da montagem
            alturas = [max(0.0, -v.co.y) for v in obj.data.vertices]

            arv = BVHTree.FromObject(dono, dg)
            mw = obj.matrix_world.copy()
            iv = mw.inverted()
            dir_local = (inv.to_3x3() @ -nrm).normalized()
            for v, h in zip(obj.data.vertices, alturas):
                w = mw @ v.co
                # como um decalque: o raio vem de fora pela normal da colagem e pega a face de fora
                # (o "mais perto" às vezes pegava a face de dentro do pano e serrilhava a beira da cruz)
                hit, n2, _, _ = arv.ray_cast(inv @ (w + nrm * 0.08), dir_local, 0.3)
                if hit is None:
                    continue
                hit, n2 = dono.matrix_world @ hit, (dono.matrix_world.to_3x3() @ n2).normalized()
                if n2.dot(nrm) < 0:
                    n2 = -n2
                v.co = iv @ (hit + n2 * (h + float(p.get("folga", 0.0012))))
    return obj, avisos


def _rebites(nome, p, mat, feitos):
    """Rebites (ou tachas) em fila pela beira de uma parte já feita: a cada `espacamento`, um pouco para
    dentro da beira (`recuo`), assentados na superfície e virados pela normal dela."""
    alvo = p.get("colar")
    dono = feitos.get(alvo or "")
    if dono is None:
        raise ValueError(f"rebites {nome!r}: diga em que parte (colar) — uma parte anterior da lista")
    lacos = _ler_borda(dono)
    if not lacos:
        raise ValueError(f"rebites {nome!r}: a parte {alvo!r} não tem beira (é fechada)")
    esp = float(p.get("espacamento", 0.03))
    raio = float(p.get("raio", 0.0045))
    recuo = float(p.get("recuo", 0.012))
    so_laco = p.get("lacos")  # índices dos laços (0 = o primeiro); sem isso, todos
    from mathutils.bvhtree import BVHTree

    dg = bpy.context.evaluated_depsgraph_get()
    arv = BVHTree.FromObject(dono, dg)
    mw, inv = dono.matrix_world, dono.matrix_world.inverted()
    bm = bmesh.new()
    n = 0
    for i, laco in enumerate(lacos):
        if so_laco is not None and i not in so_laco:
            continue
        centro = sum(laco, Vector()) / len(laco)
        acc = 0.0
        for a, b in zip(laco[:-1], laco[1:]):
            seg = (b - a).length
            while acc <= seg and seg > 1e-9:
                q = a.lerp(b, acc / seg)
                dentro = (centro - q)
                q = q + (dentro.normalized() * recuo if dentro.length > 1e-6 else Vector())
                loc, nrm, _, _ = arv.find_nearest(inv @ q)
                if loc is not None:
                    loc, nrm = mw @ loc, (mw.to_3x3() @ nrm).normalized()
                    r = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=raio)
                    M = Matrix.Translation(loc + nrm * (raio * 0.15)) @ nrm.to_track_quat("Z", "Y").to_matrix().to_4x4() @ Matrix.Diagonal((1, 1, 0.55, 1))
                    bmesh.ops.transform(bm, matrix=M, verts=r["verts"])
                    n += 1
                acc += esp
            acc -= seg
    if n == 0:
        raise ValueError(f"rebites {nome!r}: nenhum ficou em cima de {alvo!r}")
    o = _objeto_de_bmesh(nome, bm, mat)
    for poly in o.data.polygons:
        poly.use_smooth = True
    o["colado_em"] = dono.name
    return o


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
            elif tipo == "rebites":
                o = _rebites(nome, p, mat, feitos)
            else:
                o, av = _adorno(corpo, nome, p, mats, padrao, feitos)
                avisos += av
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"parte {i} ({nome}, {tipo}): {e}") from e
        o.name = f"{id_}_{nome}"
        # cada parte já é uma peça inteira (as ilhas do UV no mundo são pedaços da projeção, não peças)
        o["peca_inteira"] = True
        if tipo == "saia":
            # pano solto (saia, sobreveste, capa): vestido, segue mais o quadril que as pernas, e a barra que
            # roça o chão não conta como "o corpo entrou no chão"
            o["pano_solto"] = True
        _limitar_triangulos(o, int(p.get("triangulos", LIMITE_POR_TIPO[tipo])))
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
            if "fc_borda" in copia:
                b = list(copia["fc_borda"])
                copia["fc_borda"] = [-v if i % 3 == 0 else v for i, v in enumerate(b)]
            ordem.append(copia)
            feitos[f"{nome}_espelho"] = copia
        feitos[nome] = o
        ordem.append(o)
    # orçamento da roupa inteira (o jogo precisa caber): divide igual entre as partes grandes
    total = 0
    for o in ordem:
        o.data.calc_loop_triangles()
        total += len(o.data.loop_triangles)
    orcamento = int(spec.get("triangulos_max", 220000))
    if total > orcamento:
        r = orcamento / total
        for o in ordem:
            n = len(o.data.loop_triangles)
            if n > 4000:
                _limitar_triangulos(o, int(n * r))
    for o in ordem:
        c.uv_mundo([o], escala=float(spec.get("escala_uv", 2.0)))
    corpo.arm.data.pose_position = "POSE"
    return ordem, avisos, corpo
