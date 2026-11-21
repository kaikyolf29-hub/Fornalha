# Fornalha: armadura de placas medieval sobre o corpo do MakeHuman.
# Cada placa sai da região do corpo que ela cobre, é simplificada (sem o desenho
# dos músculos), afastada, ganha espessura, borda virada e chanfro, e fica presa
# a UM osso (placa é rígida: não estica na animação). Peças em lâminas
# sobrepostas (ombreiras, faldas, sapatos, dedos da manopla) ganham rebites.
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import fc_pbr
from fc_roupa import Alfaiate, TRONCO


def taubin(obj, iteracoes=30, lam=0.5, mu=-0.53, prender_borda=True):
    """Suaviza tirando o desenho dos músculos sem encolher a peça (passos λ/μ) e com a borda presa."""
    m = obj.data
    n = len(m.vertices)
    if not n:
        return
    co = np.array([v.co[:] for v in m.vertices])
    viz = [[] for _ in range(n)]
    for e in m.edges:
        a, b = e.vertices
        viz[a].append(b)
        viz[b].append(a)
    borda = np.zeros(n, dtype=bool)
    if prender_borda:
        contagem = {}
        for p in m.polygons:
            vs = list(p.vertices)
            for i in range(len(vs)):
                k = tuple(sorted((vs[i], vs[(i + 1) % len(vs)])))
                contagem[k] = contagem.get(k, 0) + 1
        for (a, b), c in contagem.items():
            if c == 1:
                borda[a] = borda[b] = True
    idx = [np.array(v, dtype=np.int64) for v in viz]
    for k in range(iteracoes * 2):
        f = lam if k % 2 == 0 else mu
        media = np.array([co[i].mean(axis=0) if len(i) else co[j] for j, i in enumerate(idx)])
        delta = (media - co) * f
        delta[borda] = 0.0
        co = co + delta
    for v, p in zip(m.vertices, co):
        v.co = p
    m.update()


def convexificar(obj, origem, direcao, fatia=0.02, setores=48, suavizar_setores=5, janela=3):
    """Empurra cada vértice até o contorno externo da sua fatia (perpendicular ao eixo):
    a placa passa por cima das reentrâncias do corpo, como metal de verdade."""
    m = obj.data
    co = np.array([v.co[:] for v in m.vertices])
    if not len(co):
        return
    o = np.array(origem, dtype=float)
    d = np.array(direcao, dtype=float)
    d = d / (np.linalg.norm(d) or 1.0)
    rel = co - o
    t = rel @ d
    radial = rel - np.outer(t, d)
    # base do plano da fatia
    a = np.cross(d, [0.0, 0.0, 1.0]) if abs(d[2]) < 0.9 else np.cross(d, [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    x, y = radial @ a, radial @ b
    ang = np.arctan2(y, x)
    r = np.hypot(x, y)
    fz = np.floor(t / fatia).astype(int)
    setor = ((ang + np.pi) / (2 * np.pi) * setores).astype(int) % setores
    rmax = {}
    for f, s_, rr in zip(fz, setor, r):
        k = (f, s_)
        rmax[k] = max(rmax.get(k, 0.0), rr)
    novo_r = r.copy()
    for i, (f, s_) in enumerate(zip(fz, setor)):
        vals = [rmax.get((ff, (s_ + j) % setores), 0.0) for ff in range(f - janela, f + janela + 1) for j in range(-suavizar_setores, suavizar_setores + 1)]
        alvo = max(vals) if vals else r[i]
        novo_r[i] = max(r[i], alvo * 0.97)
    fator = np.where(r > 1e-6, novo_r / np.maximum(r, 1e-6), 1.0)
    novo = o + np.outer(t, d) + radial * fator[:, None]
    for v, p_ in zip(m.vertices, novo):
        v.co = p_
    m.update()


class Armeiro:
    def __init__(self, alfaiate, material, material_detalhe=None):
        self.a = alfaiate
        self.h = alfaiate.h
        self.mat = material
        self.mat_det = material_detalhe or material
        self.pecas = []

    # -------------------------------------------------- regiões

    def regiao(self, ossos, limiar=0.5, filtro=None):
        h = self.h
        s = self.a.soma(ossos)
        faces = []
        for vi, _ in self.a.faces_corpo:
            if s[vi].mean() >= limiar:
                c = h.coords[vi].mean(axis=0)
                if filtro is None or filtro(c):
                    faces.append(vi)
        return faces

    def osso(self, nome):
        return self.h.arm.data.bones[nome]

    # -------------------------------------------------- placa

    def placa(self, nome, faces, folga, espessura=0.004, suavizar=30, pesos=None, crista=0.0, eixo_crista_x=0.0, chanfro=0.0025,
              material=None, inflar=0.0, cobrir=True, eixo=None):
        if not faces:
            return None
        h = self.h
        vs = sorted({v for f in faces for v in f})
        novo = {v: i for i, v in enumerate(vs)}
        malha = bpy.data.meshes.new(f"{self.a.prefixo}_{nome}")
        malha.from_pydata(h.coords[vs].tolist(), [], [[novo[v] for v in f] for f in faces])
        malha.validate()
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        self._ativo(obj)
        if eixo is not None:
            convexificar(obj, eixo[0], eixo[1])
        if suavizar:
            taubin(obj, suavizar)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        centro = Vector(np.mean([v.co for v in bm.verts], axis=0)) if bm.verts else Vector()
        for v in bm.verts:
            d = folga
            if inflar:
                d += inflar * max(0.0, 1 - (v.co - centro).length / 0.3)
            if crista:
                # quilha no meio (peitoral, elmo): sobe perto do eixo
                k = max(0.0, 1 - abs(v.co.x - eixo_crista_x) / 0.06)
                d += crista * k * k
            v.co += v.normal * d
        bm.to_mesh(obj.data)
        bm.free()
        for p in obj.data.polygons:
            p.use_smooth = True
        sol = obj.modifiers.new("espessura", "SOLIDIFY")
        sol.thickness = espessura
        sol.offset = 1.0
        sol.use_rim = True
        sol.use_quality_normals = True
        sol.thickness_clamp = 1.0
        bpy.ops.object.modifier_apply(modifier=sol.name)
        if chanfro:
            bev = obj.modifiers.new("borda", "BEVEL")
            bev.width = chanfro
            bev.segments = 2
            bev.limit_method = "ANGLE"
            bev.angle_limit = math.radians(40)
            bpy.ops.object.modifier_apply(modifier=bev.name)
        wn = obj.modifiers.new("normais", "WEIGHTED_NORMAL")
        wn.keep_sharp = True
        bpy.ops.object.modifier_apply(modifier=wn.name)
        self._uv(obj)
        obj.data.materials.append(material or self.mat)
        self._pesar(obj, pesos or {})
        if cobrir:
            for f in faces:
                self.a.cobertos.update(f)
        self.pecas.append(obj)
        return obj

    def laminas(self, nome, ossos, eixo_inicio, eixo_fim, n, folga, espessura=0.0035, pesos=None, limiar=0.5, filtro=None,
                sobrepor=0.35, rebites=True, crescer=0.003):
        """Divide a região em n faixas ao longo de um eixo (ex.: do ombro para o cotovelo) e faz uma placa por faixa."""
        ini, fim = Vector(eixo_inicio), Vector(eixo_fim)
        eixo = fim - ini
        L = eixo.length or 1.0
        dirv = eixo / L
        h = self.h
        objs = []
        todas = self.regiao(ossos, limiar, filtro)
        print(f"[armadura] {nome}: {len(todas)} faces na região")
        for k in range(n):
            a0 = (k - sobrepor * (k > 0)) / n
            a1 = (k + 1) / n

            def na_faixa(f, a0=a0, a1=a1):
                c = Vector(h.coords[f].mean(axis=0))
                t = (c - ini).dot(dirv) / L
                return a0 <= t <= a1

            faces = [f for f in todas if na_faixa(f)]
            o = self.placa(f"{nome}_{k + 1}", faces, folga + crescer * k, espessura, suavizar=25, pesos=pesos)
            if o is not None:
                objs.append(o)
                if rebites:
                    self.rebites(o, pesos or {})
        return objs

    def rebites(self, placa, pesos, raio=0.0045):
        """Dois rebites nas pontas laterais da lâmina."""
        vs = [placa.matrix_world @ v.co for v in placa.data.vertices]
        if not vs:
            return
        xs = sorted(vs, key=lambda v: v.x)
        for v in (xs[len(xs) // 20], xs[-1 - len(xs) // 20]):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=raio, location=v)
            r = bpy.context.active_object
            r.name = placa.name + "_rebite"
            r.scale = (1, 1, 0.6)
            bpy.ops.object.transform_apply(scale=True)
            for p in r.data.polygons:
                p.use_smooth = True
            r.data.materials.append(self.mat_det)
            self._pesar(r, pesos)
            self.pecas.append(r)

    # -------------------------------------------------- elmo fechado

    def elmo_fechado(self):
        h = self.h
        cab = self.a.W.get("head")
        faces = self.regiao(["head", "neck_01"], 0.55, None)
        cabeca = self.osso("head")
        o = self.placa("elmo", faces, 0.03, 0.004, suavizar=60, pesos={"head": 1.0}, crista=0.014, chanfro=0.002, inflar=0.006, cobrir=False,
                       eixo=(cabeca.head_local - Vector((0, 0, 0.1)), Vector((0, 0, 1))))
        if o is None:
            return None
        idx = np.nonzero(cab >= 0.9)[0]
        pts = h.coords[idx]
        frente_y = pts[:, 1].min()
        olhos_z = float(np.percentile(pts[:, 2], 62))
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        fendas = []
        for f in bm.faces:
            c = f.calc_center_median()
            na_frente = c.y < frente_y + 0.05
            # duas fendas dos olhos
            if na_frente and abs(abs(c.x) - 0.035) < 0.028 and abs(c.z - olhos_z) < 0.0065:
                fendas.append(f)
            # respiros do lado direito da viseira
            elif na_frente and -0.07 < c.x < -0.02 and olhos_z - 0.07 < c.z < olhos_z - 0.03 and int((c.x + 1) / 0.009) % 2 == 0:
                fendas.append(f)
        bmesh.ops.delete(bm, geom=fendas, context="FACES")
        bm.to_mesh(o.data)
        bm.free()
        # o rosto fica escondido dentro do elmo
        for f in self.regiao(["head"], 0.6, None):
            self.a.cobertos.update(f)
        return o

    # -------------------------------------------------- armadura completa

    def completa(self, com_elmo=True):
        h = self.h
        b = self.osso
        peito_z = b("spine_03").head_local.z
        cintura_z = b("spine_01").head_local.z
        quadril_z = b("pelvis").head_local.z
        joelho_z = b("calf_l").head_local.z
        tornozelo_z = b("foot_l").head_local.z
        axila_z = b("upperarm_l").head_local.z - 0.05
        pesc_z = b("neck_01").head_local.z
        # couraça (peitoral com quilha + costeiro)
        couraca = self.regiao(["spine_02", "spine_03"], 0.45, lambda c: cintura_z - 0.02 < c[2] < pesc_z - 0.03)
        tronco = (Vector((0, float(np.mean(h.coords[[v for f in couraca for v in f]][:, 1])), cintura_z)), Vector((0, 0, 1)))
        self.placa("peitoral", [f for f in couraca if h.coords[f].mean(axis=0)[1] < tronco[0].y], 0.022, 0.005, suavizar=40,
                   pesos={"spine_03": 0.6, "spine_02": 0.4}, crista=0.016, inflar=0.012, eixo=tronco)
        self.placa("costeiro", [f for f in couraca if h.coords[f].mean(axis=0)[1] >= tronco[0].y], 0.02, 0.005, suavizar=40,
                   pesos={"spine_03": 0.6, "spine_02": 0.4}, eixo=tronco)
        # gorjal
        self.laminas("gorjal", ["neck_01", "spine_03", "clavicle_l", "clavicle_r"], (0, 0, pesc_z + 0.04), (0, 0, pesc_z - 0.07), 3, 0.022,
                     pesos={"spine_03": 0.5, "neck_01": 0.5}, limiar=0.35, filtro=lambda c: c[2] > pesc_z - 0.08, rebites=False)
        # faldas (lâminas da cintura ao quadril)
        self.laminas("falda", ["spine_01", "pelvis", "thigh_l", "thigh_r"], (0, 0, cintura_z), (0, 0, quadril_z - 0.12), 4, 0.032,
                     pesos={"pelvis": 1.0}, limiar=0.3, filtro=lambda c: quadril_z - 0.13 < c[2] < cintura_z + 0.01)
        for lado, s in (("l", 1), ("r", -1)):
            ombro = b(f"upperarm_{lado}").head_local
            cotovelo = b(f"lowerarm_{lado}").head_local
            pulso = b(f"hand_{lado}").head_local
            joelho = b(f"calf_{lado}").head_local
            # ombreira em lâminas
            self.laminas(f"ombreira_{lado}", [f"clavicle_{lado}", f"upperarm_{lado}", "spine_03"], ombro + Vector((0, 0, 0.09)),
                         ombro - Vector((0, 0, 0.13)), 4, 0.03, pesos={f"upperarm_{lado}": 0.75, f"clavicle_{lado}": 0.25}, limiar=0.4,
                         filtro=lambda c, o=ombro, s=s: (c[0] - o.x) * s > -0.07 and c[2] > o.z - 0.14)
            # braçal de cima, cotoveleira e braçal
            self.placa(f"bracal_cima_{lado}", self.regiao([f"upperarm_{lado}"], 0.7, lambda c, o=ombro, e=cotovelo: e.z + 0.04 < c[2] < o.z - 0.12),
                       0.016, 0.004, suavizar=30, pesos={f"upperarm_{lado}": 1.0}, eixo=(b(f"upperarm_{lado}").head_local, b(f"upperarm_{lado}").tail_local - b(f"upperarm_{lado}").head_local))
            self.placa(f"cotoveleira_{lado}", self.regiao([f"upperarm_{lado}", f"lowerarm_{lado}"], 0.4,
                       lambda c, e=cotovelo: (Vector(c) - e).length < 0.07), 0.024, 0.004, suavizar=20,
                       pesos={f"lowerarm_{lado}": 0.5, f"upperarm_{lado}": 0.5}, inflar=0.01)
            self.placa(f"bracal_{lado}", self.regiao([f"lowerarm_{lado}"], 0.7, lambda c, e=cotovelo, p=pulso: (Vector(c) - e).length > 0.06 and (Vector(c) - p).length > 0.035),
                       0.014, 0.004, suavizar=30, pesos={f"lowerarm_{lado}": 1.0}, eixo=(b(f"lowerarm_{lado}").head_local, b(f"lowerarm_{lado}").tail_local - b(f"lowerarm_{lado}").head_local))
            # manopla: costas da mão + dedos em lâminas
            self.placa(f"manopla_{lado}", self.regiao([f"hand_{lado}"], 0.6), 0.012, 0.003, suavizar=15, pesos={f"hand_{lado}": 1.0})
            for dedo in ("index", "middle", "ring", "pinky", "thumb"):
                for n in ("01", "02"):
                    osso = f"{dedo}_{n}_{lado}"
                    self.placa(f"dedo_{osso}", self.regiao([osso], 0.6), 0.006, 0.002, suavizar=6, pesos={osso: 1.0}, chanfro=0.001)
            # coxote, joelheira, greva e sapato
            self.placa(f"coxote_{lado}", self.regiao([f"thigh_{lado}"], 0.7, lambda c, j=joelho: c[2] > j.z + 0.06 and c[1] < 0.03), 0.02, 0.004,
                       suavizar=30, pesos={f"thigh_{lado}": 1.0}, eixo=(b(f"thigh_{lado}").head_local, b(f"thigh_{lado}").tail_local - b(f"thigh_{lado}").head_local))
            self.placa(f"joelheira_{lado}", self.regiao([f"thigh_{lado}", f"calf_{lado}"], 0.4,
                       lambda c, j=joelho: (Vector(c) - j).length < 0.075 and c[1] < 0.02), 0.026, 0.004, suavizar=20,
                       pesos={f"calf_{lado}": 0.5, f"thigh_{lado}": 0.5}, inflar=0.012)
            self.placa(f"greva_{lado}", self.regiao([f"calf_{lado}"], 0.7, lambda c, j=joelho: tornozelo_z + 0.02 < c[2] < j.z - 0.06), 0.018, 0.004,
                       suavizar=30, pesos={f"calf_{lado}": 1.0}, eixo=(b(f"calf_{lado}").head_local, b(f"calf_{lado}").tail_local - b(f"calf_{lado}").head_local))
            pe = b(f"foot_{lado}")
            self.laminas(f"sapato_{lado}", [f"foot_{lado}", f"ball_{lado}"], pe.head_local, b(f"ball_{lado}").tail_local, 4, 0.012,
                         pesos={f"foot_{lado}": 1.0}, limiar=0.4, rebites=False)
        if com_elmo:
            self.elmo_fechado()
        return self.pecas

    # -------------------------------------------------- utilidades

    def _ativo(self, obj):
        bpy.context.view_layer.objects.active = obj
        for o in bpy.context.scene.objects:
            o.select_set(o == obj)

    def _uv(self, obj):
        self._ativo(obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01)
        bpy.ops.object.mode_set(mode="OBJECT")

    def _pesar(self, obj, pesos):
        for osso, w in pesos.items():
            if osso not in self.h.arm.data.bones:
                continue
            g = obj.vertex_groups.get(osso) or obj.vertex_groups.new(name=osso)
            g.add(list(range(len(obj.data.vertices))), w, "REPLACE")
        mod = obj.modifiers.new("esqueleto", "ARMATURE")
        mod.object = self.h.arm
        obj.parent = self.h.arm


def armadura_de_placas(alfaiate, prefixo, acabamento="ferro_velho", com_elmo=True):
    """acabamento: ferro_velho (escuro, com ferrugem), aco (polido) ou ouro."""
    # aço escurecido (a referência): aço riscado puxado para o grafite
    base, tom, mistura = {"aco_escuro": ("aco", "#9a9ca3", 0.5), "ferro_velho": ("ferro_velho", "#8a8b90", 0.35)}.get(acabamento, (acabamento, None, 0.0))
    mat = fc_pbr.material(f"{prefixo}_placas", base, tom, escala=2.2, mistura_tom=mistura)
    acabamento = base
    det = fc_pbr.material(f"{prefixo}_rebites", "aco" if acabamento != "aco" else "ferro_velho", escala=8.0)
    return Armeiro(alfaiate, mat, det).completa(com_elmo)
