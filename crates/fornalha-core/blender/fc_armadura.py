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


def moldar(obj, origem, direcao, fatia=0.02, setores=72, sigma_ang=4.0, sigma_fatia=1.6, folga_extra=0.0, margem=0.005):
    """Molda a placa numa forma lisa de metal batido: para cada fatia ao longo do eixo, o contorno
    externo (envelope) é suavizado em ângulo e ao longo do eixo, e TODO vértice vai para ele.
    Some a anatomia (peito, músculos, mamilos); fica só o volume."""
    m = obj.data
    co = np.array([v.co[:] for v in m.vertices])
    if len(co) < 8:
        return
    o = np.array(origem, dtype=float)
    d = np.array(direcao, dtype=float)
    d = d / (np.linalg.norm(d) or 1.0)
    rel = co - o
    t = rel @ d
    radial = rel - np.outer(t, d)
    a = np.cross(d, [0.0, 0.0, 1.0]) if abs(d[2]) < 0.9 else np.cross(d, [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    x, y = radial @ a, radial @ b
    ang = np.arctan2(y, x)
    r = np.hypot(x, y)
    t0 = t.min()
    nf = int((t.max() - t0) / fatia) + 1
    fi = np.clip(((t - t0) / fatia).astype(int), 0, nf - 1)
    si = (((ang + np.pi) / (2 * np.pi)) * setores).astype(int) % setores
    env = np.full((nf, setores), np.nan)
    for f_, s_, rr in zip(fi, si, r):
        if np.isnan(env[f_, s_]) or rr > env[f_, s_]:
            env[f_, s_] = rr
    tem = ~np.isnan(env)
    # suavização gaussiana (com peso só onde há placa), circular no ângulo
    def gauss(n, sig, circular):
        k = np.arange(-int(3 * sig) - 1, int(3 * sig) + 2)
        w = np.exp(-0.5 * (k / sig) ** 2)
        return k, w / w.sum()
    val = np.where(tem, env, 0.0)
    peso = tem.astype(float)
    k, w = gauss(setores, sigma_ang, True)
    v2 = sum(wi * np.roll(val, ki, axis=1) for ki, wi in zip(k, w))
    p2 = sum(wi * np.roll(peso, ki, axis=1) for ki, wi in zip(k, w))
    k, w = gauss(nf, sigma_fatia, False)
    pad_v = np.pad(v2, ((len(k) // 2, len(k) // 2), (0, 0)), mode="edge")
    pad_p = np.pad(p2, ((len(k) // 2, len(k) // 2), (0, 0)), mode="edge")
    v3 = sum(wi * pad_v[j:j + nf] for j, wi in enumerate(w))
    p3 = sum(wi * pad_p[j:j + nf] for j, wi in enumerate(w))
    liso = np.where(p3 > 1e-6, v3 / np.maximum(p3, 1e-6), np.nan)
    # o envelope liso não pode afundar abaixo do corpo: compensa a média para cima
    falta = np.where(tem, env - liso, 0.0)
    liso = liso + max(0.0, float(np.percentile(falta[tem], 92)))
    # interpolação bilinear (fatia contínua, setor contínuo)
    tf = (t - t0) / fatia - 0.5
    sf = ((ang + np.pi) / (2 * np.pi)) * setores - 0.5
    f0 = np.clip(np.floor(tf).astype(int), 0, nf - 1)
    f1 = np.clip(f0 + 1, 0, nf - 1)
    s0 = np.floor(sf).astype(int) % setores
    s1 = (s0 + 1) % setores
    ft = np.clip(tf - np.floor(tf), 0, 1)
    st = sf - np.floor(sf)

    def pega(ff, ss):
        vv = liso[ff, ss]
        return np.where(np.isnan(vv), r, vv)

    novo_r = (pega(f0, s0) * (1 - ft) * (1 - st) + pega(f1, s0) * ft * (1 - st) + pega(f0, s1) * (1 - ft) * st + pega(f1, s1) * ft * st)
    # nunca afunda mais que a margem (senão o que está por baixo, cota ou corpo, fura a peça)
    novo_r = np.maximum(novo_r, r - margem) + folga_extra
    fator = np.where(r > 1e-6, novo_r / np.maximum(r, 1e-6), 1.0)
    novo = o + np.outer(t, d) + radial * fator[:, None]
    for v, p_ in zip(m.vertices, novo):
        v.co = p_
    m.update()


def _arestas_de_borda(m):
    contagem = {}
    for p in m.polygons:
        vs = list(p.vertices)
        for i in range(len(vs)):
            k = tuple(sorted((vs[i], vs[(i + 1) % len(vs)])))
            contagem[k] = contagem.get(k, 0) + 1
    return [k for k, c in contagem.items() if c == 1]


def limpar_dentes(obj, passes=2):
    """Tira as faces soltas na borda (3 ou mais lados na borda): o recorte vira uma linha, não uma escada."""
    for _ in range(passes):
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        dentes = [f for f in bm.faces if sum(1 for e in f.edges if e.is_boundary) >= 3 and len(bm.faces) > 8]
        if dentes:
            bmesh.ops.delete(bm, geom=dentes, context="FACES")
            soltos = [v for v in bm.verts if not v.link_faces]
            bmesh.ops.delete(bm, geom=soltos, context="VERTS")
        bm.to_mesh(obj.data)
        bm.free()
        if not dentes:
            break
    obj.data.update()


def alisar_borda(obj, iteracoes=24, lam=0.55, mu=-0.58):
    """Suaviza só o contorno da placa, ao longo dele (λ/μ, sem encolher): a borda fica uma curva limpa."""
    m = obj.data
    viz = {}
    for a, b in _arestas_de_borda(m):
        viz.setdefault(a, []).append(b)
        viz.setdefault(b, []).append(a)
    ids = np.array([v for v, lista in viz.items() if len(lista) == 2], dtype=np.int64)
    if not len(ids):
        return
    nb = np.array([viz[int(v)] for v in ids], dtype=np.int64)
    co = np.array([v.co[:] for v in m.vertices])
    for k in range(iteracoes * 2):
        f = lam if k % 2 == 0 else mu
        media = (co[nb[:, 0]] + co[nb[:, 1]]) * 0.5
        co[ids] += (media - co[ids]) * f
    for i in ids:
        m.vertices[int(i)].co = co[i]
    m.update()


def lacos_de_borda(bm, minimo=8):
    """Contornos da placa, em ordem: [(pontos, normais, fechado)]."""
    viz = {}
    for e in bm.edges:
        if e.is_boundary:
            a, b = e.verts
            viz.setdefault(a, []).append(b)
            viz.setdefault(b, []).append(a)
    vistos, lacos = set(), []
    for v0 in list(viz):
        if v0 in vistos or len(viz[v0]) != 2:
            continue
        laco, ant, atual, fechado = [v0], None, v0, False
        vistos.add(v0)
        while True:
            prox = [w for w in viz[atual] if w is not ant]
            if not prox:
                break
            w = prox[0]
            if w is v0:
                fechado = True
                break
            if w in vistos or len(viz[w]) != 2:
                break
            laco.append(w)
            vistos.add(w)
            ant, atual = atual, w
        if len(laco) >= minimo:
            lacos.append(([v.co.copy() for v in laco], [v.normal.copy() for v in laco], fechado))
    return lacos


def tubo_de_borda(bm, pontos, normais, fechado, raio, subir, lados=8):
    """Borda virada (enrolada) da placa: um tubo que corre pelo contorno, por fora."""
    n = len(pontos)
    if n < 3:
        return
    # o contorno ainda tem degraus pequenos: média móvel antes de fazer o tubo
    P = np.array([p[:] for p in pontos])
    N = np.array([q[:] for q in normais])
    for _ in range(3):
        if fechado:
            P = (np.roll(P, 1, 0) + 2 * P + np.roll(P, -1, 0)) / 4
            N = (np.roll(N, 1, 0) + 2 * N + np.roll(N, -1, 0)) / 4
        else:
            P[1:-1] = (P[:-2] + 2 * P[1:-1] + P[2:]) / 4
            N[1:-1] = (N[:-2] + 2 * N[1:-1] + N[2:]) / 4
    aneis = []
    for i in range(n):
        if fechado:
            t = P[(i + 1) % n] - P[i - 1]
        else:
            t = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        t = Vector(t).normalized()
        nn = Vector(N[i]).normalized()
        nn = (nn - t * nn.dot(t)).normalized()
        b = t.cross(nn)
        centro = Vector(P[i]) + nn * subir
        anel = [bm.verts.new(centro + raio * (math.cos(2 * math.pi * k / lados) * nn + math.sin(2 * math.pi * k / lados) * b)) for k in range(lados)]
        aneis.append(anel)
    pares = range(n) if fechado else range(n - 1)
    for i in pares:
        a, b = aneis[i], aneis[(i + 1) % n]
        for k in range(lados):
            try:
                f = bm.faces.new((a[k], a[(k + 1) % lados], b[(k + 1) % lados], b[k]))
                f.smooth = True
            except ValueError:
                pass
    if not fechado:
        for anel in (aneis[0], aneis[-1]):
            try:
                bm.faces.new(anel)
            except ValueError:
                pass


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
              material=None, inflar=0.0, cobrir=True, eixo=None, rolar=None):
        """rolar: raio da borda virada (None = automático pela espessura; 0 = sem)."""
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
            if len(eixo) > 2 and eixo[2] == "moldar":
                moldar(obj, eixo[0], eixo[1], **(eixo[3] if len(eixo) > 3 else {}))
            else:
                convexificar(obj, eixo[0], eixo[1])
        limpar_dentes(obj)
        if not obj.data.polygons:
            bpy.data.objects.remove(obj)
            return None
        alisar_borda(obj)
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
        bm.normal_update()
        raio = max(espessura * 1.15, 0.0035) if rolar is None else rolar
        contornos = lacos_de_borda(bm) if raio else []
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
        if contornos:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            for pts, nrm, fechado in contornos:
                tubo_de_borda(bm, pts, nrm, fechado, raio, espessura * 0.5 + raio * 0.35)
            bm.to_mesh(obj.data)
            bm.free()
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
                sobrepor=0.35, rebites=True, crescer=0.003, extremos=False, rolar=None):
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
            if extremos:
                # a primeira e a última lâmina vão até o fim da região (calcanhar e ponta do pé)
                a0 = -1e9 if k == 0 else a0
                a1 = 1e9 if k == n - 1 else a1

            def na_faixa(f, a0=a0, a1=a1):
                c = Vector(h.coords[f].mean(axis=0))
                t = (c - ini).dot(dirv) / L
                return a0 <= t <= a1

            faces = [f for f in todas if na_faixa(f)]
            o = self.placa(f"{nome}_{k + 1}", faces, folga + crescer * k, espessura, suavizar=25, pesos=pesos, rolar=rolar)
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

    # -------------------------------------------------- elmo armet (modelado, não tirado do rosto)

    def elmo_armet(self, folga=0.024, espessura=0.003, n=96):
        """Elmo fechado de placas: crânio com crista, viseira em bico de pardal com fenda dos olhos e
        respiros, queixeira que fecha no pescoço, borda virada embaixo e rebites do pivô da viseira."""
        h = self.h
        cab = self.a.W.get("head")
        idx = np.nonzero(cab >= 0.9)[0]
        if not len(idx):
            return None
        pts = h.coords[idx]
        x0, x1 = np.percentile(pts[:, 0], [1, 99])
        y0, y1 = np.percentile(pts[:, 1], [1, 99])
        z0, z1 = np.percentile(pts[:, 2], [1, 99.5])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ex, ey = (x1 - x0) / 2 + folga, (y1 - y0) / 2 + folga
        olhos = float(np.percentile(pts[:, 2], 62))
        queixo = float(z0)
        pesc = self.osso("neck_01").head_local
        topo = float(z1) + folga * 0.9
        base = min(queixo - 0.05, pesc.z + 0.035)
        cranio = olhos + 0.03  # onde a cúpula começa
        r_pesc = 0.062 + folga * 0.6

        def perfil(z):
            """(semi-eixo x, semi-eixo y, centro y) da seção na altura z."""
            if z >= cranio:
                u = min(1.0, (z - cranio) / (topo - cranio))
                k = math.sqrt(max(0.0, 1 - u ** 2.2))
                return ex * k, ey * k, cy + 0.006 * u
            if z >= queixo:
                u = (z - queixo) / (cranio - queixo)
                return ex * (0.86 + 0.14 * u ** 0.6), ey * (0.93 + 0.07 * u), cy
            u = (z - base) / max(queixo - base, 1e-4)
            s = u * u * (3 - 2 * u)
            ax = r_pesc + (ex * 0.86 - r_pesc) * s
            ay = r_pesc * 1.05 + (ey * 0.93 - r_pesc * 1.05) * s
            return ax, ay, cy + (pesc.y - cy) * (1 - s) * 0.6

        def bico(z):
            """quanto a viseira avança na frente (bico de pardal), por altura"""
            c, larg = olhos - 0.045, 0.055
            return 0.042 * math.exp(-((z - c) / larg) ** 2)

        aneis = 60
        zs = [topo - (topo - base) * (i / aneis) ** 1.05 for i in range(1, aneis + 1)]
        bm = bmesh.new()
        polo = bm.verts.new((cx, cy + 0.006, topo))
        rings = []
        for z in zs:
            ax, ay, ccy = perfil(z)
            anel = []
            for j in range(n):
                th = 2 * math.pi * j / n - math.pi / 2  # j=0 na frente (-y)
                ct, st = math.cos(th), math.sin(th)
                # superelipse (um pouco quadrada dos lados, como elmo batido)
                e = 2.3
                rx = ax * (abs(ct) ** (2 / e)) * (1 if ct >= 0 else -1)
                ry = ay * (abs(st) ** (2 / e)) * (1 if st >= 0 else -1)
                x, y = cx + rx, ccy + ry
                frente = max(0.0, -st)
                if z < cranio + 0.01:
                    # bico: aresta viva no meio, avança só na frente
                    y -= bico(z) * frente ** 6 * max(0.0, 1 - abs(ct) * 2.2)
                zz = z
                if z >= cranio - 0.02:
                    # crista do crânio, de frente para trás
                    zz = z + 0.008 * math.exp(-((x - cx) / 0.014) ** 2) * min(1.0, (z - cranio + 0.02) / 0.05)
                anel.append(bm.verts.new((x, y, zz)))
            rings.append(anel)
        for j in range(n):
            bm.faces.new((polo, rings[0][(j + 1) % n], rings[0][j]))
        for a_, b_ in zip(rings, rings[1:]):
            for j in range(n):
                bm.faces.new((a_[j], a_[(j + 1) % n], b_[(j + 1) % n], b_[j]))
        bm.normal_update()
        # normais para fora (o polo é o topo)
        if sum((f.normal.dot(f.calc_center_median() - Vector((cx, cy, (topo + base) / 2)))) for f in bm.faces) < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        # fenda dos olhos (com a barra do meio) e respiros do lado direito da viseira
        tira = []
        for f in bm.faces:
            c = f.calc_center_median()
            na_frente = c.y < cy - ey * 0.55
            dx = c.x - cx
            if na_frente and abs(c.z - olhos) < 0.0062 and 0.007 < abs(dx) < 0.075:
                tira.append(f)
            elif na_frente and -0.068 < dx < -0.018 and olhos - 0.085 < c.z < olhos - 0.028:
                col = int((dx + 1) / 0.0072)
                lin = int((c.z + 1) / 0.0105)
                if col % 2 == 0 and lin % 2 == 0:
                    tira.append(f)
        bmesh.ops.delete(bm, geom=tira, context="FACES")
        malha = bpy.data.meshes.new(f"{self.a.prefixo}_elmo")
        bm.to_mesh(malha)
        bm.free()
        o = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(o)
        self._ativo(o)
        for p_ in malha.polygons:
            p_.use_smooth = True
        # borda virada embaixo (no pescoço)
        bm = bmesh.new()
        bm.from_mesh(malha)
        bm.normal_update()
        contornos = [c for c in lacos_de_borda(bm, minimo=40)]
        bm.free()
        sol = o.modifiers.new("espessura", "SOLIDIFY")
        sol.thickness = espessura
        sol.offset = -1.0
        sol.use_rim = True
        sol.use_even_offset = True
        bpy.ops.object.modifier_apply(modifier=sol.name)
        bm = bmesh.new()
        bm.from_mesh(malha)
        for pts_, nrm, fechado in contornos:
            if fechado and np.mean([p_.z for p_ in pts_]) < queixo:
                tubo_de_borda(bm, pts_, nrm, fechado, 0.0045, -espessura * 0.5)
        # linha da viseira (friso que contorna a frente na altura do crânio) e os pivôs
        frente_pts, frente_n = [], []
        for j in range(-30, 31):
            th = 2 * math.pi * j / n - math.pi / 2
            ax, ay, ccy = perfil(cranio - 0.004)
            ct, st = math.cos(th), math.sin(th)
            e = 2.3
            x = cx + ax * (abs(ct) ** (2 / e)) * (1 if ct >= 0 else -1)
            y = ccy + ay * (abs(st) ** (2 / e)) * (1 if st >= 0 else -1)
            frente_pts.append(Vector((x, y, cranio - 0.004)))
            frente_n.append(Vector((x - cx, y - ccy, 0)).normalized())
        tubo_de_borda(bm, frente_pts, frente_n, False, 0.0032, 0.0015)
        bm.to_mesh(malha)
        bm.free()
        bev = o.modifiers.new("borda", "BEVEL")
        bev.width = 0.0015
        bev.segments = 2
        bev.limit_method = "ANGLE"
        bev.angle_limit = math.radians(45)
        bpy.ops.object.modifier_apply(modifier=bev.name)
        wn = o.modifiers.new("normais", "WEIGHTED_NORMAL")
        wn.keep_sharp = True
        bpy.ops.object.modifier_apply(modifier=wn.name)
        self._uv(o)
        o.data.materials.append(self.mat)
        self._pesar(o, {"head": 1.0})
        self.pecas.append(o)
        ax, ay, ccy = perfil(cranio - 0.004)
        for lado in (1, -1):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=14, ring_count=8, radius=0.009, location=(cx + lado * (ax + 0.001), ccy + 0.01, cranio - 0.004))
            r = bpy.context.active_object
            r.name = f"{o.name}_pivo"
            r.scale = (0.45, 1, 1)
            bpy.ops.object.transform_apply(scale=True)
            for p_ in r.data.polygons:
                p_.use_smooth = True
            r.data.materials.append(self.mat_det)
            self._pesar(r, {"head": 1.0})
            self.pecas.append(r)
        for f in self.regiao(["head"], 0.5, None):
            self.a.cobertos.update(f)
        return o

    # -------------------------------------------------- elmo grande (templário)

    def elmo_grande(self, folga=0.026, espessura=0.003, n=96):
        """Elmo de barril: cilindro batido com topo levemente abaulado, quilha na frente, fendas dos
        olhos com a barra do meio, respiros dos dois lados, cruz de reforço rebitada e borda virada."""
        h = self.h
        cab = self.a.W.get("head")
        idx = np.nonzero(cab >= 0.9)[0]
        if not len(idx):
            return None
        pts = h.coords[idx]
        x0, x1 = np.percentile(pts[:, 0], [1, 99])
        y0, y1 = np.percentile(pts[:, 1], [1, 99])
        z0, z1 = np.percentile(pts[:, 2], [1, 99.5])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ex, ey = (x1 - x0) / 2 + folga, (y1 - y0) / 2 + folga
        olhos = float(np.percentile(pts[:, 2], 62))
        topo = float(z1) + folga * 0.7
        base = float(z0) - 0.045
        coroa = topo - 0.035  # onde o cilindro vira a tampa

        def perfil(z):
            if z >= coroa:
                u = (z - coroa) / (topo - coroa)
                k = math.sqrt(max(0.0, 1 - u ** 3))
                return ex * 0.97 * k, ey * 0.97 * k
            u = (z - base) / (coroa - base)
            return ex * (1.03 - 0.06 * u), ey * (1.04 - 0.07 * u)

        def ponto(z, j, ax=None, ay=None):
            if ax is None:
                ax, ay = perfil(z)
            th = 2 * math.pi * j / n - math.pi / 2
            ct, st = math.cos(th), math.sin(th)
            e = 2.15
            x = cx + ax * (abs(ct) ** (2 / e)) * (1 if ct >= 0 else -1)
            y = cy + ay * (abs(st) ** (2 / e)) * (1 if st >= 0 else -1)
            frente = max(0.0, -st)
            # quilha vertical: aresta viva no meio da frente
            y -= 0.014 * frente ** 10 * max(0.0, 1 - abs(ct) * 3.0) * (1.0 if z < coroa else max(0.0, 1 - (z - coroa) / (topo - coroa)))
            return Vector((x, y, z)), Vector((x - cx, y - cy, 0)).normalized()

        aneis = 64
        zs = [topo - (topo - base) * (i / aneis) for i in range(1, aneis + 1)]
        bm = bmesh.new()
        polo = bm.verts.new((cx, cy, topo))
        rings = [[bm.verts.new(ponto(z, j)[0]) for j in range(n)] for z in zs]
        for j in range(n):
            bm.faces.new((polo, rings[0][(j + 1) % n], rings[0][j]))
        for a_, b_ in zip(rings, rings[1:]):
            for j in range(n):
                bm.faces.new((a_[j], a_[(j + 1) % n], b_[(j + 1) % n], b_[j]))
        bm.normal_update()
        if sum(f.normal.dot(f.calc_center_median() - Vector((cx, cy, (topo + base) / 2))) for f in bm.faces) < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        tira = []
        for f in bm.faces:
            c = f.calc_center_median()
            dx = c.x - cx
            na_frente = c.y < cy - ey * 0.5
            if na_frente and abs(c.z - olhos) < 0.0085 and 0.011 < abs(dx) < 0.085:
                tira.append(f)
            elif na_frente and 0.016 < abs(dx) < 0.07 and olhos - 0.10 < c.z < olhos - 0.035:
                col = int((abs(dx) + 1) / 0.0068)
                lin = int((c.z + 1) / 0.011)
                if col % 2 == 0 and lin % 2 == 0:
                    tira.append(f)
        bmesh.ops.delete(bm, geom=tira, context="FACES")
        malha = bpy.data.meshes.new(f"{self.a.prefixo}_elmo")
        bm.to_mesh(malha)
        bm.free()
        o = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(o)
        self._ativo(o)
        for p_ in malha.polygons:
            p_.use_smooth = True
        bm = bmesh.new()
        bm.from_mesh(malha)
        bm.normal_update()
        contornos = lacos_de_borda(bm, minimo=40)
        bm.free()
        sol = o.modifiers.new("espessura", "SOLIDIFY")
        sol.thickness = espessura
        sol.offset = -1.0
        sol.use_rim = True
        sol.use_even_offset = True
        bpy.ops.object.modifier_apply(modifier=sol.name)
        bm = bmesh.new()
        bm.from_mesh(malha)
        for pts_, nrm, fechado in contornos:
            if fechado and np.mean([p_.z for p_ in pts_]) < olhos - 0.05:
                tubo_de_borda(bm, pts_, nrm, fechado, 0.005, -espessura * 0.5)
        # cruz de reforço: faixa vertical na frente e faixa em volta acima dos olhos; costura da tampa
        faixa_v = [ponto(z, 0) for z in np.linspace(coroa + 0.01, olhos + 0.012, 14)] + [ponto(z, 0) for z in np.linspace(olhos - 0.012, base + 0.01, 18)]
        tubo_de_borda(bm, [p_ for p_, _ in faixa_v[:14]], [q for _, q in faixa_v[:14]], False, 0.0042, 0.0012, lados=6)
        tubo_de_borda(bm, [p_ for p_, _ in faixa_v[14:]], [q for _, q in faixa_v[14:]], False, 0.0042, 0.0012, lados=6)
        anel_olhos = [ponto(olhos + 0.016, j) for j in range(n)]
        tubo_de_borda(bm, [p_ for p_, _ in anel_olhos], [q for _, q in anel_olhos], True, 0.0035, 0.0012, lados=6)
        anel_coroa = [ponto(coroa, j) for j in range(n)]
        tubo_de_borda(bm, [p_ for p_, _ in anel_coroa], [q for _, q in anel_coroa], True, 0.003, 0.001, lados=6)
        bm.to_mesh(malha)
        bm.free()
        bev = o.modifiers.new("borda", "BEVEL")
        bev.width = 0.0012
        bev.segments = 2
        bev.limit_method = "ANGLE"
        bev.angle_limit = math.radians(45)
        bpy.ops.object.modifier_apply(modifier=bev.name)
        wn = o.modifiers.new("normais", "WEIGHTED_NORMAL")
        wn.keep_sharp = True
        bpy.ops.object.modifier_apply(modifier=wn.name)
        self._uv(o)
        o.data.materials.append(self.mat)
        self._pesar(o, {"head": 1.0})
        self.pecas.append(o)
        # rebites na faixa de cima dos olhos
        for j in list(range(-14, 15, 4)):
            p_, q = ponto(olhos + 0.016, j % n)
            self._rebite(p_ + q * 0.004, {"head": 1.0}, 0.0042)
        for f in self.regiao(["head"], 0.5, None):
            self.a.cobertos.update(f)
        return o

    def _rebite(self, local, pesos, raio=0.0045):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=raio, location=local)
        r = bpy.context.active_object
        r.name = f"{self.a.prefixo}_rebite"
        for p_ in r.data.polygons:
            p_.use_smooth = True
        r.data.materials.append(self.mat_det)
        self._pesar(r, pesos)
        self.pecas.append(r)
        return r

    # -------------------------------------------------- templário: placas por cima da cota

    def templario(self, com_elmo=True):
        """Ombreiras, cotoveleiras, braçais, manoplas, joelheiras, grevas e sapatos de placa; o tronco
        fica por conta da cota de malha e da sobreveste (como na referência)."""
        b = self.osso
        tornozelo_z = b("foot_l").head_local.z
        for lado, s in (("l", 1), ("r", -1)):
            ombro = b(f"upperarm_{lado}").head_local
            cotovelo = b(f"lowerarm_{lado}").head_local
            pulso = b(f"hand_{lado}").head_local
            joelho = b(f"calf_{lado}").head_local
            self.laminas(f"ombreira_{lado}", [f"clavicle_{lado}", f"upperarm_{lado}", "spine_03"], ombro + Vector((0, 0, 0.1)),
                         ombro - Vector((0, 0, 0.16)), 5, 0.034, pesos={f"upperarm_{lado}": 0.75, f"clavicle_{lado}": 0.25}, limiar=0.4,
                         filtro=lambda c, o=ombro, s=s: (c[0] - o.x) * s > -0.08 and c[2] > o.z - 0.17, espessura=0.004)
            self.placa(f"cotoveleira_{lado}", self.regiao([f"upperarm_{lado}", f"lowerarm_{lado}"], 0.4,
                       lambda c, e=cotovelo: (Vector(c) - e).length < 0.075), 0.026, 0.004, suavizar=20,
                       pesos={f"lowerarm_{lado}": 0.5, f"upperarm_{lado}": 0.5}, inflar=0.012)
            self.placa(f"bracal_{lado}", self.regiao([f"lowerarm_{lado}"], 0.7, lambda c, e=cotovelo, p=pulso: (Vector(c) - e).length > 0.065 and (Vector(c) - p).length > 0.03),
                       0.016, 0.004, suavizar=30, pesos={f"lowerarm_{lado}": 1.0},
                       eixo=(b(f"lowerarm_{lado}").head_local, b(f"lowerarm_{lado}").tail_local - b(f"lowerarm_{lado}").head_local, "moldar"))
            self.placa(f"manopla_{lado}", self.regiao([f"hand_{lado}"], 0.6), 0.013, 0.003, suavizar=15, pesos={f"hand_{lado}": 1.0}, rolar=0.003)
            for dedo in ("index", "middle", "ring", "pinky", "thumb"):
                for n_ in ("01", "02"):
                    osso = f"{dedo}_{n_}_{lado}"
                    self.placa(f"dedo_{osso}", self.regiao([osso], 0.6), 0.006, 0.002, suavizar=6, pesos={osso: 1.0}, chanfro=0.001, rolar=0)
            self.placa(f"joelheira_{lado}", self.regiao([f"thigh_{lado}", f"calf_{lado}"], 0.4,
                       lambda c, j=joelho: (Vector(c) - j).length < 0.08 and c[1] < 0.02), 0.028, 0.004, suavizar=20,
                       pesos={f"calf_{lado}": 0.5, f"thigh_{lado}": 0.5}, inflar=0.014)
            self.placa(f"greva_{lado}", self.regiao([f"calf_{lado}"], 0.7, lambda c, j=joelho: tornozelo_z + 0.02 < c[2] < j.z - 0.065), 0.019, 0.004,
                       suavizar=30, pesos={f"calf_{lado}": 1.0},
                       eixo=(b(f"calf_{lado}").head_local, b(f"calf_{lado}").tail_local - b(f"calf_{lado}").head_local, "moldar"))
            pe = b(f"foot_{lado}")
            self.laminas(f"sapato_{lado}", [f"foot_{lado}", f"ball_{lado}"], pe.head_local, b(f"ball_{lado}").tail_local, 5, 0.012,
                         pesos={f"foot_{lado}": 1.0}, limiar=0.25, rebites=False, extremos=True)
            for f in self.regiao([f"foot_{lado}", f"ball_{lado}"], 0.15):
                self.a.cobertos.update(f)
        if com_elmo:
            self.elmo_grande()
        return self.pecas

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
                   pesos={"spine_03": 0.6, "spine_02": 0.4}, crista=0.016, inflar=0.012, eixo=(*tronco, "moldar"))
        self.placa("costeiro", [f for f in couraca if h.coords[f].mean(axis=0)[1] >= tronco[0].y], 0.02, 0.005, suavizar=40,
                   pesos={"spine_03": 0.6, "spine_02": 0.4}, eixo=(*tronco, "moldar"))
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
                       0.016, 0.004, suavizar=30, pesos={f"upperarm_{lado}": 1.0}, eixo=(b(f"upperarm_{lado}").head_local, b(f"upperarm_{lado}").tail_local - b(f"upperarm_{lado}").head_local, "moldar"))
            self.placa(f"cotoveleira_{lado}", self.regiao([f"upperarm_{lado}", f"lowerarm_{lado}"], 0.4,
                       lambda c, e=cotovelo: (Vector(c) - e).length < 0.07), 0.024, 0.004, suavizar=20,
                       pesos={f"lowerarm_{lado}": 0.5, f"upperarm_{lado}": 0.5}, inflar=0.01)
            self.placa(f"bracal_{lado}", self.regiao([f"lowerarm_{lado}"], 0.7, lambda c, e=cotovelo, p=pulso: (Vector(c) - e).length > 0.06 and (Vector(c) - p).length > 0.035),
                       0.014, 0.004, suavizar=30, pesos={f"lowerarm_{lado}": 1.0}, eixo=(b(f"lowerarm_{lado}").head_local, b(f"lowerarm_{lado}").tail_local - b(f"lowerarm_{lado}").head_local, "moldar"))
            # manopla: costas da mão + dedos em lâminas
            self.placa(f"manopla_{lado}", self.regiao([f"hand_{lado}"], 0.6), 0.012, 0.003, suavizar=15, pesos={f"hand_{lado}": 1.0}, rolar=0.003)
            for dedo in ("index", "middle", "ring", "pinky", "thumb"):
                for n in ("01", "02"):
                    osso = f"{dedo}_{n}_{lado}"
                    self.placa(f"dedo_{osso}", self.regiao([osso], 0.6), 0.006, 0.002, suavizar=6, pesos={osso: 1.0}, chanfro=0.001, rolar=0)
            # coxote, joelheira, greva e sapato
            self.placa(f"coxote_{lado}", self.regiao([f"thigh_{lado}"], 0.7, lambda c, j=joelho: c[2] > j.z + 0.06 and c[1] < 0.03), 0.02, 0.004,
                       suavizar=30, pesos={f"thigh_{lado}": 1.0}, eixo=(b(f"thigh_{lado}").head_local, b(f"thigh_{lado}").tail_local - b(f"thigh_{lado}").head_local, "moldar"))
            self.placa(f"joelheira_{lado}", self.regiao([f"thigh_{lado}", f"calf_{lado}"], 0.4,
                       lambda c, j=joelho: (Vector(c) - j).length < 0.075 and c[1] < 0.02), 0.026, 0.004, suavizar=20,
                       pesos={f"calf_{lado}": 0.5, f"thigh_{lado}": 0.5}, inflar=0.012)
            self.placa(f"greva_{lado}", self.regiao([f"calf_{lado}"], 0.7, lambda c, j=joelho: tornozelo_z + 0.02 < c[2] < j.z - 0.06), 0.018, 0.004,
                       suavizar=30, pesos={f"calf_{lado}": 1.0}, eixo=(b(f"calf_{lado}").head_local, b(f"calf_{lado}").tail_local - b(f"calf_{lado}").head_local, "moldar"))
            pe = b(f"foot_{lado}")
            self.laminas(f"sapato_{lado}", [f"foot_{lado}", f"ball_{lado}"], pe.head_local, b(f"ball_{lado}").tail_local, 4, 0.012,
                         pesos={f"foot_{lado}": 1.0}, limiar=0.25, rebites=False, extremos=True)
            # o pé inteiro some por baixo do sapato (nada de pele nos dedos ou no calcanhar)
            for f in self.regiao([f"foot_{lado}", f"ball_{lado}"], 0.15):
                self.a.cobertos.update(f)
        if com_elmo:
            self.elmo_armet()
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


# ------------------------------------------------------------------ desgaste assado
# Como nos jogos AAA: a armadura vira UMA malha com UM atlas de textura, e o desgaste
# fica pintado nele (quinas polidas, sujeira e ferrugem nos vãos, oclusão entre as placas).

def _curvatura(obj):
    """Por vértice: quanto a malha é convexa (quina) ou côncava (vão), de 0 a 1."""
    m = obj.data
    n = len(m.vertices)
    co = np.empty(n * 3)
    m.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nor = np.empty(n * 3)
    m.vertex_normals.foreach_get("vector", nor)
    nor = nor.reshape(-1, 3)
    ar = np.empty(len(m.edges) * 2, dtype=np.int64)
    m.edges.foreach_get("vertices", ar)
    ar = ar.reshape(-1, 2)
    a, b = ar[:, 0], ar[:, 1]
    d = co[b] - co[a]
    soma = np.zeros((n, 3))
    np.add.at(soma, a, d)
    np.add.at(soma, b, -d)
    cont = np.bincount(ar.ravel(), minlength=n).astype(float)
    comp = np.zeros(n)
    L = np.linalg.norm(d, axis=1)
    np.add.at(comp, a, L)
    np.add.at(comp, b, L)
    cont = np.maximum(cont, 1)
    lap = soma / cont[:, None]
    curv = -(lap * nor).sum(1) / np.maximum(comp / cont, 1e-5)
    # espalha um pouco (a quina gasta pega uma faixa, não só a aresta)
    for _ in range(2):
        acc = np.zeros(n)
        np.add.at(acc, a, curv[b])
        np.add.at(acc, b, curv[a])
        curv = 0.5 * curv + 0.5 * acc / cont
    alto = np.percentile(curv, [80, 98])
    baixo = np.percentile(curv, [3, 22])
    quina = np.clip((curv - alto[0]) / max(alto[1] - alto[0], 1e-6), 0, 1)
    vao = np.clip((baixo[1] - curv) / max(baixo[1] - baixo[0], 1e-6), 0, 1)
    attr = m.color_attributes.new("desgaste", "FLOAT_COLOR", "POINT")
    cores = np.zeros((n, 4))
    cores[:, 0], cores[:, 1], cores[:, 3] = quina, vao, 1.0
    attr.data.foreach_set("color", cores.ravel())


def _juntar_em_um(objs, nome):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    alvo = objs[0]
    bpy.context.view_layer.objects.active = alvo
    if len(objs) > 1:
        bpy.ops.object.join()
    alvo.name = nome
    alvo.data.name = nome
    # um só modificador de esqueleto (o join pode deixar repetidos)
    vistos = False
    for mod in list(alvo.modifiers):
        if mod.type == "ARMATURE":
            if vistos:
                alvo.modifiers.remove(mod)
            vistos = True
    return alvo


def _mix(nt, tipo, modo="MIX"):
    """Nó Mix com as entradas certas para o tipo (o nó tem A/B repetidos por tipo)."""
    no = nt.nodes.new("ShaderNodeMix")
    no.data_type = tipo
    if tipo == "RGBA":
        no.blend_type = modo
    t = "RGBA" if tipo == "RGBA" else "VALUE"
    ent = {}
    for sk in no.inputs:
        if sk.name == "Factor" and sk.type == "VALUE":
            ent.setdefault("Factor", sk)
        elif sk.name in ("A", "B") and sk.type == t:
            ent.setdefault(sk.name, sk)
    sai = next(sk for sk in no.outputs if sk.type == t)
    return no, ent["Factor"], ent["A"], ent["B"], sai


def _no_imagem(nt, img):
    no = nt.nodes.new("ShaderNodeTexImage")
    no.image = img
    nt.nodes.active = no
    no.select = True
    return no


def assar_desgaste(objs, nome, acabamento="aco", resolucao=1024, amostras=8):
    """Junta as peças de metal, faz um atlas e assa cor, rugosidade e normal com o desgaste.
    Devolve o objeto único (com os pesos de cada osso preservados)."""
    objs = [o for o in objs if o and o.type == "MESH" and len(o.data.polygons)]
    if not objs:
        return None
    cena = bpy.context.scene
    arm = next((o.parent for o in objs if o.parent and o.parent.type == "ARMATURE"), None)
    pose_antes = arm.data.pose_position if arm else None
    if arm:
        arm.data.pose_position = "REST"
    obj = _juntar_em_um(objs, nome)
    m = obj.data
    if not m.uv_layers:
        m.uv_layers.new(name="UVMap")
    base_uv = m.uv_layers[0].name
    atlas = m.uv_layers.new(name="atlas")
    m.uv_layers.active = atlas
    for o in cena.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.002, area_weight=0.0, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    m.uv_layers[base_uv].active_render = True
    _curvatura(obj)

    motor, amostras_antes = cena.render.engine, cena.cycles.samples
    cena.render.engine = "CYCLES"
    cena.cycles.samples = amostras
    try:
        cena.cycles.device = "CPU"
    except Exception:
        pass
    imgs = {
        "mascara": bpy.data.images.new(f"{nome}_mascara", resolucao, resolucao, alpha=False, float_buffer=False),
        "cor": bpy.data.images.new(f"{nome}_cor", resolucao, resolucao, alpha=False),
        "rugosidade": bpy.data.images.new(f"{nome}_rugosidade", resolucao, resolucao, alpha=False),
        "normal": bpy.data.images.new(f"{nome}_normal", resolucao, resolucao, alpha=False),
    }
    for k in ("mascara", "rugosidade", "normal"):
        imgs[k].colorspace_settings.name = "Non-Color"
    ferrugem = acabamento == "ferro_velho"

    def preparar(mat):
        """Nós de assar em cada material: (saída, emissão, alvo, cor, rugosidade)."""
        nt = mat.node_tree
        saida = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        for n in nt.nodes:
            if n.type == "TEX_IMAGE" or n.type == "NORMAL_MAP":
                try:
                    n.uv_map = base_uv
                except Exception:
                    pass
                for entrada in n.inputs:
                    if entrada.name == "Vector" and not entrada.is_linked:
                        uvn = nt.nodes.new("ShaderNodeUVMap")
                        uvn.uv_map = base_uv
                        nt.links.new(uvn.outputs["UV"], entrada)
            if n.type == "TEX_COORD":
                uvn = nt.nodes.new("ShaderNodeUVMap")
                uvn.uv_map = base_uv
                for l in list(n.outputs["UV"].links):
                    nt.links.new(uvn.outputs["UV"], l.to_socket)

        def fonte(nome_entrada, padrao):
            e = bsdf.inputs[nome_entrada] if bsdf else None
            if e is not None and e.is_linked:
                return e.links[0].from_socket
            rgb = nt.nodes.new("ShaderNodeRGB")
            v = e.default_value if e is not None else padrao
            rgb.outputs[0].default_value = (v[0], v[1], v[2], 1.0) if hasattr(v, "__len__") else (v, v, v, 1.0)
            return rgb.outputs[0]

        cor = fonte("Base Color", (0.7, 0.7, 0.72, 1.0))
        rug = fonte("Roughness", 0.4)
        emi = nt.nodes.new("ShaderNodeEmission")
        alvo = _no_imagem(nt, imgs["mascara"])
        return {"nt": nt, "saida": saida, "bsdf": bsdf, "emi": emi, "alvo": alvo, "cor": cor, "rug": rug}

    preps = [preparar(ms.material) for ms in obj.material_slots if ms.material and ms.material.use_nodes]

    def assar(tipo, img, margem=6):
        for p_ in preps:
            p_["alvo"].image = img
            p_["nt"].nodes.active = p_["alvo"]
        bpy.ops.object.bake(type=tipo, margin=margem, use_clear=True, normal_space="TANGENT", uv_layer="atlas")

    # 1) máscara: R = quina gasta, G = sujeira (vão + oclusão), B = manchas (ruído)
    for p_ in preps:
        nt = p_["nt"]
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "desgaste"
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(attr.outputs["Color"], sep.inputs["Color"])
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.samples = 8
        ao.inputs["Distance"].default_value = 0.06
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(ao.outputs["AO"], inv.inputs[1])
        suj = nt.nodes.new("ShaderNodeMath")
        suj.operation = "MAXIMUM"
        suj.use_clamp = True
        nt.links.new(sep.outputs["Green"], suj.inputs[0])
        nt.links.new(inv.outputs[0], suj.inputs[1])
        coord = nt.nodes.new("ShaderNodeTexCoord")
        ruido = nt.nodes.new("ShaderNodeTexNoise")
        ruido.inputs["Scale"].default_value = 9.0
        ruido.inputs["Detail"].default_value = 10.0
        ruido.inputs["Roughness"].default_value = 0.62
        nt.links.new(coord.outputs["Object"], ruido.inputs["Vector"])
        junta = nt.nodes.new("ShaderNodeCombineColor")
        nt.links.new(sep.outputs["Red"], junta.inputs["Red"])
        nt.links.new(suj.outputs[0], junta.inputs["Green"])
        nt.links.new(ruido.outputs["Fac"], junta.inputs["Blue"])
        nt.links.new(junta.outputs["Color"], p_["emi"].inputs["Color"])
        nt.links.new(p_["emi"].outputs["Emission"], p_["saida"].inputs["Surface"])
    assar("EMIT", imgs["mascara"])

    # 2) cor e 3) rugosidade a partir da máscara (rápido: 1 amostra)
    cena.cycles.samples = 1
    for p_ in preps:
        nt = p_["nt"]
        uva = nt.nodes.new("ShaderNodeUVMap")
        uva.uv_map = "atlas"
        msk = nt.nodes.new("ShaderNodeTexImage")
        msk.image = imgs["mascara"]
        msk.interpolation = "Linear"
        nt.links.new(uva.outputs["UV"], msk.inputs["Vector"])
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(msk.outputs["Color"], sep.inputs["Color"])
        # sujeira com manchas: vão × (0.55 + 0.45·ruído)
        mancha = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(sep.outputs["Blue"], mancha.inputs["Value"])
        mancha.inputs["From Min"].default_value, mancha.inputs["From Max"].default_value = 0.3, 0.7
        mancha.inputs["To Min"].default_value, mancha.inputs["To Max"].default_value = 0.45, 1.0
        suj = nt.nodes.new("ShaderNodeMath")
        suj.operation = "MULTIPLY"
        suj.use_clamp = True
        nt.links.new(sep.outputs["Green"], suj.inputs[0])
        nt.links.new(mancha.outputs["Result"], suj.inputs[1])
        # cor: quina polida clareia, vão escurece (fuligem) e, no ferro velho, enferruja
        _, fa, a_, b_, polido = _mix(nt, "RGBA", "SCREEN")
        nt.links.new(sep.outputs["Red"], fa)
        nt.links.new(p_["cor"], a_)
        b_.default_value = (0.55, 0.56, 0.58, 1.0)
        fator_f = nt.nodes.new("ShaderNodeMath")
        fator_f.operation = "MULTIPLY"
        fator_f.inputs[1].default_value = 0.85
        nt.links.new(suj.outputs[0], fator_f.inputs[0])
        _, fa, a_, b_, fuligem = _mix(nt, "RGBA")
        nt.links.new(fator_f.outputs[0], fa)
        nt.links.new(polido, a_)
        b_.default_value = (0.36, 0.25, 0.15, 1.0) if ferrugem else (0.075, 0.068, 0.06, 1.0)
        nt.links.new(fuligem, p_["emi"].inputs["Color"])
        # rugosidade: quina lisa (0.12), vão fosco (0.8)
        _, fa, a_, b_, r1 = _mix(nt, "FLOAT")
        nt.links.new(sep.outputs["Red"], fa)
        nt.links.new(p_["rug"], a_)
        b_.default_value = 0.12
        _, fa, a_, b_, r2 = _mix(nt, "FLOAT")
        nt.links.new(suj.outputs[0], fa)
        nt.links.new(r1, a_)
        b_.default_value = 0.8
        p_["rug_final"] = r2
    assar("EMIT", imgs["cor"])
    for p_ in preps:
        p_["nt"].links.new(p_["rug_final"], p_["emi"].inputs["Color"])
    assar("EMIT", imgs["rugosidade"])
    # 4) normal (do mapa de relevo da textura) no espaço do atlas
    for p_ in preps:
        if p_["bsdf"] is not None:
            p_["nt"].links.new(p_["bsdf"].outputs["BSDF"], p_["saida"].inputs["Surface"])
    assar("NORMAL", imgs["normal"])

    cena.render.engine, cena.cycles.samples = motor, amostras_antes
    for img in imgs.values():
        img.pack()
    # material final: só o atlas (o glTF e a engine recebem exatamente isto)
    mat = bpy.data.materials.new(f"{nome}_metal")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = imgs["cor"]
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    tr = nt.nodes.new("ShaderNodeTexImage")
    tr.image = imgs["rugosidade"]
    nt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
    bsdf.inputs["Metallic"].default_value = 1.0
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = imgs["normal"]
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    mat["pbr"] = True
    m.materials.clear()
    m.materials.append(mat)
    for p in m.polygons:
        p.material_index = 0
    # fica só o atlas
    m.uv_layers.remove(m.uv_layers[base_uv])
    m.uv_layers["atlas"].name = "UVMap"
    m.uv_layers.active = m.uv_layers["UVMap"]
    m.uv_layers["UVMap"].active_render = True
    if "desgaste" in m.color_attributes:
        m.color_attributes.remove(m.color_attributes["desgaste"])
    if arm:
        arm.data.pose_position = pose_antes
    return obj


def armadura_de_placas(alfaiate, prefixo, acabamento="aco", com_elmo=True, textura=None):
    """acabamento: aco (polido), aco_escuro, ferro_velho (com ferrugem) ou ouro.
    textura: resolução do atlas com desgaste assado (None = 1024 com o pacote de materiais; 0 = não assa)."""
    # aço escurecido (a referência): aço riscado puxado para o grafite
    base, tom, mistura = {"aco_escuro": ("aco", "#9a9ca3", 0.5), "ferro_velho": ("ferro_velho", "#8a8b90", 0.35)}.get(acabamento, (acabamento, None, 0.0))
    mat = fc_pbr.material(f"{prefixo}_placas", base, tom, escala=2.2, mistura_tom=mistura)
    acabamento = base
    det = fc_pbr.material(f"{prefixo}_rebites", "aco" if acabamento != "aco" else "ferro_velho", escala=8.0)
    pecas = Armeiro(alfaiate, mat, det).completa(com_elmo)
    if textura is None:
        textura = 1024 if fc_pbr.disponivel(base) else 0
    if textura:
        unica = assar_desgaste(pecas, f"{prefixo}_armadura", base, int(textura))
        return [unica] if unica else []
    return pecas


def armadura_templario(alfaiate, prefixo, acabamento="aco", com_elmo=True, textura=None):
    """Placas do templário (sobre a cota e a sobreveste), com o desgaste assado num atlas."""
    base, tom, mistura = {"aco_escuro": ("aco", "#9a9ca3", 0.5), "ferro_velho": ("ferro_velho", "#8a8b90", 0.35)}.get(acabamento, (acabamento, None, 0.0))
    mat = fc_pbr.material(f"{prefixo}_placas", base, tom, escala=2.2, mistura_tom=mistura)
    det = fc_pbr.material(f"{prefixo}_rebites", "aco" if base != "aco" else "ferro_velho", escala=8.0)
    pecas = Armeiro(alfaiate, mat, det).templario(com_elmo)
    if textura is None:
        textura = 1024 if fc_pbr.disponivel(base) else 0
    if textura:
        unica = assar_desgaste(pecas, f"{prefixo}_armadura", base, int(textura))
        return [unica] if unica else []
    return pecas
