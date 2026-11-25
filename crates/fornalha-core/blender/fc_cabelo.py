# Fornalha: cabelo fio a fio. Os fios crescem do couro cabeludo pelo penteado, colados no crânio
# de verdade (campo de distância da cabeça), com mechas e poucos fios soltos. No render são curvas
# de cabelo do Cycles; na engine vão os mesmos fios como fitas que o shader vira para a câmera.
#   estilos: curto (para trás com risca lateral), medio (até o queixo), longo (até as costas)
import bpy
import numpy as np
from mathutils import Vector

import fc_comum as c


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def estilo_de(nome):
    nome = (nome or "").lower()
    if nome.startswith("long") or nome.startswith("braid") or nome.startswith("ponytail") or nome == "afro01":
        return "longo"
    if nome.startswith("bob") or nome == "medio":
        return "medio"
    return "curto"


# ------------------------------------------------------------------ couro cabeludo

def mascara_couro(x, y, z, pontos, ruido=None, suave=1.0):
    """0..1 onde nasce cabelo (linha da testa, têmporas, costeleta curta, nuca), com bordas suaves;
    nunca na orelha nem no rosto. ruido (opcional, mesmo formato) deixa a linha irregular;
    suave > 1 alarga todas as transições (pintura da pele, sem cantos retos)."""
    s, oz = pontos["s"], pontos["olho_z"]
    oy = (pontos["olho_l"][1] + pontos["olho_r"][1]) / 2
    qz = pontos["queixo"][2]
    k = suave
    ax = np.abs(x)
    atras = y - oy
    testa = oz + 0.06 * s - 0.008 * s * _sstep(0.025 * s, 0.05 * s, ax)
    tempora = oz + 0.008 * s
    nuca = qz + 0.03 * s
    # têmpora em curva (entrada arredondada), não em canto reto
    linha = testa + (tempora - testa) * _sstep(0.018 * s, 0.075 * s, atras)
    linha = linha + (nuca - linha) * _sstep(0.11 * s, 0.15 * s, atras)
    # costeleta: desce na frente da orelha e afina para baixo (a borda da frente recua com a altura)
    fundo = tempora - (oz - 0.012 * s)
    desce = np.clip((tempora - z) / max(fundo, 1e-6), 0.0, 1.0)
    frente = 0.053 * s + 0.01 * s * desce
    cost = (_sstep(0.057 * s - 0.003 * s * k, 0.057 * s + 0.003 * s * k, ax)
            * _sstep(frente - 0.004 * s * k, frente + 0.004 * s * k, atras)
            * _sstep(0.075 * s + 0.005 * s * k, 0.075 * s - 0.005 * s * k, atras))
    linha = linha * (1 - cost) + (oz - 0.012 * s) * cost
    if ruido is not None:
        linha = linha + ruido * 0.004 * s
    orelha = (_sstep(0.058 * s - 0.004 * s * k, 0.058 * s + 0.004 * s * k, ax)
              * _sstep(0.066 * s - 0.004 * s * k, 0.066 * s + 0.004 * s * k, atras)
              * _sstep(0.117 * s + 0.005 * s * k, 0.117 * s - 0.005 * s * k, atras)
              * _sstep(oz + 0.018 * s + 0.004 * s * k, oz + 0.018 * s - 0.004 * s * k, z)
              * _sstep(oz - 0.046 * s - 0.006 * s * k, oz - 0.046 * s + 0.006 * s * k, z))
    rosto = (_sstep(0.05 * s + 0.006 * s * k, 0.05 * s - 0.006 * s * k, atras)
             * _sstep(oz + 0.05 * s + 0.006 * s * k, oz + 0.05 * s - 0.006 * s * k, z))
    return _sstep(linha - 0.006 * s * k, linha + 0.006 * s * k, z) * (1 - orelha) * (1 - rosto)


def couro_cabeludo(corpo, pontos, cabeca_peso, estilo):
    """Faces do corpo onde nasce cabelo (pela mesma máscara que pinta o couro na pele)."""
    co = np.array([v.co[:] for v in corpo.data.vertices])
    ok = (cabeca_peso > 0.5) & (mascara_couro(co[:, 0], co[:, 1], co[:, 2], pontos) > 0.5)
    faces = [p for p in corpo.data.polygons if all(ok[i] for i in p.vertices)]
    return faces, co


# ------------------------------------------------------------------ fio a fio

FIOS = {
    # comprimento em cima / nos lados (m), altura do volume na frente / em cima / nos lados (m)
    "curto": dict(cima=(0.09, 0.115), lados=(0.02, 0.03), h_frente=0.016, h_cima=0.009, h_lados=0.004, grav=0.1, fios=70000, guias=0, segs=16),
    "medio": dict(cima=(0.15, 0.2), lados=(0.13, 0.18), h_frente=0.01, h_cima=0.007, h_lados=0.006, grav=0.9, fios=70000, guias=2400, segs=18),
    # comprido: o caminho sobre o crânio gasta ~0,25 m; o resto pende até os ombros e as costas
    "longo": dict(cima=(0.55, 0.68), lados=(0.42, 0.55), h_frente=0.012, h_cima=0.010, h_lados=0.009, grav=1.3, fios=80000, guias=2600, segs=30),
}


class CampoCombinado:
    """O campo fino da cabeça onde ele vale (dentro da grade dele) e o do tronco no resto: o cabelo
    comprido sai da grade da cabeça e o campo dela devolvia direções erradas (cards espetados)."""

    def __init__(self, cabeca, corpo):
        self.a, self.b = cabeca, corpo
        self.lo = cabeca.o + cabeca.h
        self.hi = cabeca.o + (cabeca.n - 2) * cabeca.h

    def __call__(self, P):
        P = np.asarray(P)
        d1, g1 = self.a(P)
        d2, g2 = self.b(P)
        dentro = np.all((P >= self.lo) & (P <= self.hi), axis=-1)
        return np.where(dentro, d1, d2), np.where(dentro[..., None], g1, g2)


class CampoDistancia:
    """Distância com sinal até a pele da cabeça (de verdade, não uma forma oval), numa grade 3D,
    com gradiente. Os fios usam isso para ficar colados no crânio na altura certa."""

    def __init__(self, co, normais, sel, passo=0.005, margem=0.07):
        from mathutils.kdtree import KDTree

        pts, nrm = co[sel], normais[sel]
        kd = KDTree(len(pts))
        for i, q in enumerate(pts):
            kd.insert(q, i)
        kd.balance()
        self.o = pts.min(0) - margem
        fim = pts.max(0) + margem
        self.n = (np.ceil((fim - self.o) / passo).astype(int) + 1)
        self.h = passo
        gx, gy, gz = (self.o[k] + np.arange(self.n[k]) * passo for k in range(3))
        G = np.stack(np.meshgrid(gx, gy, gz, indexing="ij"), -1).reshape(-1, 3)
        d = np.empty(len(G))
        for k, q in enumerate(G):
            _, i, dist = kd.find(q)
            d[k] = dist if np.dot(q - pts[i], nrm[i]) >= 0 else -dist
        d = d.reshape(tuple(self.n))
        # a distância pelo vértice mais perto é "serrilhada": suaviza antes de tirar o gradiente
        for _ in range(3):
            acc = d.copy()
            for eixo in range(3):
                acc += np.roll(d, 1, eixo) + np.roll(d, -1, eixo)
            d = acc / 7.0
        self.d = d
        self.g = np.stack(np.gradient(self.d, passo), -1)

    def __call__(self, P):
        f = (np.asarray(P) - self.o) / self.h
        i0 = np.clip(np.floor(f).astype(int), 0, self.n - 2)
        t = np.clip(f - i0, 0.0, 1.0)
        dist = np.zeros(f.shape[:-1])
        grad = np.zeros(f.shape)
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = ((t[..., 0] if dx else 1 - t[..., 0]) * (t[..., 1] if dy else 1 - t[..., 1]) * (t[..., 2] if dz else 1 - t[..., 2]))
                    ix, iy, iz = i0[..., 0] + dx, i0[..., 1] + dy, i0[..., 2] + dz
                    dist += w * self.d[ix, iy, iz]
                    grad += w[..., None] * self.g[ix, iy, iz]
        grad /= np.linalg.norm(grad, axis=-1, keepdims=True) + 1e-9
        return dist, grad


def assentar_fios(P, livre, campo_corpo, s, folga=0.006, perto=0.04, peso_queda=0.45, z_corte=None):
    """Cabelo que pende (médio, comprido): a parte penteada sobre o crânio fica; daí em diante cada ponto
    segue o anterior no mesmo comprimento, virando aos poucos para baixo (gravidade), e se encostar na
    pele contorna por fora (cabeça, pescoço, ombros, costas). Uma passada só, da raiz para a ponta: com
    várias rodadas o ruído do campo virava fio crespo, e colidir fora da passada fazia laços.
    "Dentro" só vale perto da pele (`perto`): longe dela o sinal do campo não é confiável.
    livre: índice do primeiro ponto solto de cada fio (o fio inteiro preso: npts)."""
    nf, npts, _ = P.shape
    X = P.astype(np.float64).copy()
    L = np.linalg.norm(np.diff(X, axis=1), axis=-1)
    baixo = np.array([0.0, 0.0, -1.0])
    dirs = np.diff(X, axis=1)
    dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True) + 1e-12
    ant = dirs[np.arange(nf), np.clip(livre - 1, 0, npts - 2)].copy()
    # quem sai do crânio subindo (coroa) começa na horizontal: cabelo não sobe sozinho
    ant[:, 2] = np.minimum(ant[:, 2], 0.0)
    ant /= np.linalg.norm(ant, axis=-1, keepdims=True) + 1e-12
    for k in range(1, npts):
        m = livre <= k
        if not m.any():
            continue
        dd = ant[m] * (1 - peso_queda) + baixo * peso_queda
        dd /= np.linalg.norm(dd, axis=-1, keepdims=True) + 1e-12
        q = X[m, k - 1] + dd * L[m, k - 1][:, None]
        dist, n = campo_corpo(q)
        pen = np.where(dist > -perto * s, np.maximum(folga * s - dist, 0.0), 0.0)
        if z_corte is not None:
            pen = pen * (q[:, 2] > z_corte)
        q = q + n * pen[:, None]
        d = q - X[m, k - 1]
        d /= np.linalg.norm(d, axis=-1, keepdims=True) + 1e-12
        X[m, k] = X[m, k - 1] + d * L[m, k - 1][:, None]
        ant[m] = d
    return X


def _alisar_fios(P, passes=3):
    """Suaviza cada fio ao longo do comprimento (a raiz fica presa): tira o zigue-zague."""
    P = P.copy()
    for _ in range(passes):
        meio = (P[:, :-2] + 2 * P[:, 1:-1] + P[:, 2:]) / 4
        P[:, 1:-1] = meio
    return P


def _amostrar(faces, co, n, rng):
    areas = np.array([f.area for f in faces])
    esc = rng.choice(len(faces), size=n, p=areas / areas.sum())
    tri = np.array([[co[i] for i in faces[k].vertices[:3]] for k in esc])
    a, b = rng.random(n), rng.random(n)
    troca = a + b > 1
    a[troca], b[troca] = 1 - a[troca], 1 - b[troca]
    return tri[:, 0] + (tri[:, 1] - tri[:, 0]) * a[:, None] + (tri[:, 2] - tri[:, 0]) * b[:, None]


def crescer_fios(corpo, pontos, cabeca_peso, estilo="curto", semente=11, fios=None, devolver_campo=False):
    """Cada fio caminha SOBRE a superfície do crânio seguindo o penteado (para trás, com risca
    lateral) e fica a uma altura fixa da pele (volume maior na frente): não sai voando nem afunda.
    Mechas leves, poucos fios soltos e linha do cabelo macia. Devolve (P: fios × pontos × 3, raios)."""
    rng = np.random.default_rng(semente)
    e = FIOS.get(estilo, FIOS["curto"])
    faces, co = couro_cabeludo(corpo, pontos, cabeca_peso, estilo)
    if not faces:
        return (None, None, None) if devolver_campo else (None, None)
    s, oz = pontos["s"], pontos["olho_z"]
    oy = (pontos["olho_l"][1] + pontos["olho_r"][1]) / 2
    qz = pontos["queixo"][2]
    normais = np.empty(len(corpo.data.vertices) * 3)
    corpo.data.vertex_normals.foreach_get("vector", normais)
    # pele da cabeça E do pescoço (os fios de trás descem até a nuca)
    perto = (cabeca_peso > 0.25) | ((co[:, 2] > qz - 0.12 * s) & (np.abs(co[:, 0]) < 0.12 * s) & (np.abs(co[:, 1] - oy - 0.08 * s) < 0.14 * s))
    campo = CampoDistancia(co, normais.reshape(-1, 3), perto)
    segs = e["segs"]
    nf = int(fios or e["fios"])
    R = _amostrar(faces, co, nf, rng)
    alto = _sstep(oz + 0.035 * s, oz + 0.085 * s, R[:, 2])
    lado = _sstep(0.04 * s, 0.066 * s, np.abs(R[:, 0]))
    frente = _sstep(0.085 * s, 0.035 * s, R[:, 1] - oy)
    cima = alto * (1 - lado)
    longo = estilo != "curto"
    comp = (rng.uniform(*e["lados"], nf) * (1 - cima) + rng.uniform(*e["cima"], nf) * cima) * s
    if not longo:
        # corte de verdade: comprido na frente, vai encurtando até a coroa e a nuca
        para_frente = _sstep(oy + 0.15 * s, oy + 0.05 * s, R[:, 1])
        comp = comp * (0.42 + 0.58 * para_frente) + rng.uniform(*e["lados"], nf) * s * (1 - para_frente) * 0.35
    h_pico = (e["h_lados"] * (1 - cima) + (e["h_cima"] + (e["h_frente"] - e["h_cima"]) * frente) * cima) * s
    if longo:
        # camadas: uns fios rentes, outros por cima (o volume do cabelo comprido)
        h_pico = h_pico * rng.uniform(0.35, 1.9, nf)
    borda = mascara_couro(R[:, 0], R[:, 1], R[:, 2], pontos)
    comp *= rng.uniform(0.88, 1.04, nf) * (0.45 + 0.55 * np.clip((borda - 0.5) * 2, 0, 1))
    # leve variação de direção, suave de um fio para o vizinho (cabelo de verdade não é régua)
    k1, k2 = rng.normal(0, 55, 3), rng.normal(0, 90, 3)
    f1, f2 = rng.uniform(0, 2 * np.pi, 2)
    ang = 0.13 * np.sin(R @ k1 + f1) + 0.07 * np.sin(R @ k2 + f2)

    # o pente sai de um ponto na frente da testa: em cima vai para trás, atrás desce, nos lados
    # vai para trás e para baixo (nunca sobe na nuca)
    pivo = np.array([0.0, oy - 0.07 * s, oz + 0.035 * s])

    def pente(q, nrm):
        x = q[:, 0]
        lado_p = _sstep(0.042 * s, 0.068 * s, np.abs(x))[:, None]
        f = q - pivo
        f /= np.linalg.norm(f, axis=-1, keepdims=True) + 1e-9
        # atrás da coroa o cabelo desce e se abre para os lados (a nuca afina: sem juntar no meio)
        atras_p = _sstep(oy + 0.12 * s, oy + 0.17 * s, q[:, 1])
        f = f + np.stack([x / (0.03 * s) * 0.35 * atras_p, np.zeros(len(q)), -0.9 * atras_p], -1)
        # sem risca (os dois lados da risca se cruzavam e abriam buracos): penteado reto para trás,
        # nas laterais para trás e para baixo
        f = f + np.stack([np.zeros(len(q)), np.zeros(len(q)), -0.35 * lado_p[:, 0]], -1)
        f = f - nrm * (f * nrm).sum(-1, keepdims=True)
        f /= np.linalg.norm(f, axis=-1, keepdims=True) + 1e-9
        b = np.cross(nrm, f)
        return f * np.cos(ang)[:, None] + b * np.sin(ang)[:, None]

    P = np.zeros((nf, segs + 1, 3), dtype=np.float64)
    Q = R.copy()
    passo = (comp / segs)[:, None]
    solto = np.zeros(nf, dtype=bool)  # cabelo comprido: abaixo do crânio cai livre
    livre = np.full(nf, segs + 1)
    d_livre = np.zeros((nf, 3))
    for j in range(segs + 1):
        t = j / segs
        dist, nrm = campo(Q)
        if longo:
            # fora da grade da cabeça o campo devolve lixo: o fio que sai dela solta (não é puxado)
            fora = np.any((Q <= campo.o + campo.h) | (Q >= campo.o + (campo.n - 2) * campo.h), axis=-1) | (np.abs(dist) > 0.03 * s)
            novos = fora & ~solto
            livre[novos] = j
            solto |= fora
        Q = np.where(solto[:, None], Q, Q - nrm * dist[:, None])
        h = (0.0007 * s + (h_pico - 0.0007 * s) * _sstep(0.0, 0.22, t)) * (1.0 - 0.25 * t)
        P[:, j] = np.where(solto[:, None], Q, Q + nrm * h[:, None])
        if j == segs:
            break
        F = pente(Q, nrm)
        if longo:
            abaixo = (Q[:, 2] < oz - 0.02 * s) & ~solto
            livre[abaixo] = j + 1
            d_livre[abaixo] = F[abaixo]
            solto |= abaixo
            Q[abaixo] = P[abaixo, j]
            d_livre = d_livre * 0.7 + np.array([0.0, 0.08, -1.0]) * 0.3
            d_livre /= np.linalg.norm(d_livre, axis=-1, keepdims=True) + 1e-9
            F = np.where(solto[:, None], d_livre, F)
        Q = Q + F * passo
    campo_corpo = None
    if longo:
        # o tronco de cima (cabeça, pescoço, ombros, peito e costas) para o cabelo assentar em cima
        # só o tronco (sem os braços, abertos na pose de descanso: o cabelo enroscava neles)
        z_corte = qz - 0.85 * s
        sel = co[:, 2] > z_corte
        z_colisao = qz - 0.45 * s
        nrm_v = normais.reshape(-1, 3)
        campo_corpo = CampoDistancia(co, nrm_v, sel, passo=0.012 * s, margem=max(0.12 * s, float(np.max(comp)) * 0.6))
        import os as _os

        _dbg = _os.environ.get("FORNALHA_DEBUG_FIOS")
        if _dbg:
            np.save(_dbg + "_antes.npy", P[::40].astype(np.float32))
            np.save(_dbg + "_corpo_co.npy", co[sel].astype(np.float32))
            np.save(_dbg + "_corpo_n.npy", nrm_v[sel].astype(np.float32))
            np.save(_dbg + "_params.npy", np.array([s, qz, z_colisao], dtype=np.float64))
            np.save(_dbg + "_livre.npy", livre[::40])
        P = assentar_fios(P, livre, campo_corpo, s, z_corte=z_colisao)
        if _dbg:
            np.save(_dbg + "_depois.npy", P[::40].astype(np.float32))
        campo = CampoCombinado(campo, campo_corpo)
    # mechas: puxa cada fio um pouco para o fio-guia mais perto (mais na ponta)
    nc = max(400, nf // 15)
    centros = rng.choice(nf, nc, replace=False)
    t = np.linspace(0, 1, segs + 1)[None, :, None]
    for a in range(0, nf, 4000):
        b = min(nf, a + 4000)
        dd = np.linalg.norm(R[a:b, None, :] - R[None, centros, :], axis=-1)
        c = centros[np.argmin(dd, axis=1)]
        forca = rng.uniform(0.04, 0.14, (b - a, 1, 1)) * t ** 1.3
        P[a:b] = P[a:b] * (1 - forca) + P[c] * forca
    # poucos fios soltos e uma ondulação bem fina
    frizz = np.cumsum(rng.normal(0, 0.00012 * s, P.shape), axis=1) * t
    soltos = rng.random((nf, 1, 1)) < 0.003
    P = P + frizz * np.where(soltos, 4.0, 1.0)
    P = _alisar_fios(P, 2)
    dist, nrm = campo(P)
    P = P + nrm * np.maximum(0.0007 * s - dist, 0)[..., None]  # nunca entra na pele
    if campo_corpo is not None:
        dist, nrm = campo_corpo(P)
        P = P + nrm * np.maximum(0.002 * s - dist, 0)[..., None]
    raios = np.linspace(0.00004, 0.000012, segs + 1, dtype=np.float32)
    if devolver_campo:
        return P.astype(np.float32), raios, campo
    return P.astype(np.float32), raios


def objeto_de_fios(nome, P, raios, cor, arm=None):
    """Objeto de curvas de cabelo (para o render no Cycles), preso ao osso da cabeça."""
    nf, npts = P.shape[:2]
    cv = bpy.data.hair_curves.new(nome)
    cv.add_curves([npts] * nf)
    cv.position_data.foreach_set("vector", P.reshape(-1).astype(np.float32))
    r = cv.attributes.get("radius") or cv.attributes.new("radius", "FLOAT", "POINT")
    r.data.foreach_set("value", np.tile(raios, nf).astype(np.float32))
    obj = bpy.data.objects.new(nome, cv)
    bpy.context.scene.collection.objects.link(obj)
    mat = bpy.data.materials.new(nome + "_fios_render")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    saida = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    cabelo = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    # cor do cabelo → melanina (o modelo físico do fio): escuro = muita melanina, ruivo = feomelanina
    srgb = [int(cor.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lum = 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2]
    sat = (max(srgb) - min(srgb)) / max(max(srgb), 1e-3)
    try:
        cabelo.parametrization = "MELANIN"
    except Exception:
        pass
    for k, v in (("Melanin", float(np.clip(1.33 - 1.75 * lum, 0.03, 1.0))),
                 ("Melanin Redness", float(np.clip((srgb[0] - srgb[2]) / max(srgb[0], 1e-3), 0, 1) * 0.35 * min(1.0, sat * 2.0))),
                 ("Random Color", 0.1)):
        if k in cabelo.inputs:
            cabelo.inputs[k].default_value = v
    for k, v in (("Roughness", 0.32), ("Radial Roughness", 0.35), ("Coat", 0.12), ("Random Color", 0.12), ("Random Roughness", 0.15)):
        if k in cabelo.inputs:
            cabelo.inputs[k].default_value = v
    nt.links.new(cabelo.outputs[0], saida.inputs["Surface"])
    cv.materials.append(mat)
    if arm is not None:
        bpy.context.view_layer.update()
        mw = obj.matrix_world.copy()
        obj.parent = arm
        obj.parent_type = "BONE"
        obj.parent_bone = "head"
        bpy.context.view_layer.update()
        obj.matrix_world = mw
    return obj


def malha_de_fios(nome, P, cor, n_jogo, largura=0.0005, arm=None, semente=5):
    """Os mesmos fios para a engine: cada fio vira uma fita de largura quase zero; a normal guarda a
    direção do fio e o shader de cabelo da Fornalha abre a fita de frente para a câmera."""
    rng = np.random.default_rng(semente)
    nf, npts = P.shape[:2]
    escolha = rng.choice(nf, size=min(n_jogo, nf), replace=False)
    Q = P[escolha]
    # menos pontos por fio no jogo (de 2 em 2)
    Q = Q[:, ::2] if npts > 9 else Q
    n, m = Q.shape[:2]
    tang = np.gradient(Q, axis=1)
    tang /= np.linalg.norm(tang, axis=-1, keepdims=True) + 1e-9
    lado = np.cross(tang, np.array([0.0, 0.0, 1.0]))
    lado /= np.linalg.norm(lado, axis=-1, keepdims=True) + 1e-9
    esq = Q - lado * largura * 0.05
    dir_ = Q + lado * largura * 0.05
    V = np.stack([esq, dir_], axis=2).reshape(-1, 3)  # fio, ponto, lado
    idx = np.arange(n * m * 2).reshape(n, m, 2)
    a, b = idx[:, :-1, 0], idx[:, :-1, 1]
    c_, d_ = idx[:, 1:, 1], idx[:, 1:, 0]
    F = np.stack([a, b, c_, d_], -1).reshape(-1, 4)
    malha = bpy.data.meshes.new(nome)
    malha.from_pydata(V.tolist(), [], F.tolist())
    uv = malha.uv_layers.new(name="UVMap")
    tt = np.linspace(0, 1, m)
    uvs = np.zeros((n, m, 2, 2), dtype=np.float32)
    uvs[:, :, 0, 0], uvs[:, :, 1, 0] = 0.0, 1.0
    uvs[:, :, :, 1] = tt[None, :, None]
    lv = np.empty(len(malha.loops), dtype=np.int64)
    malha.loops.foreach_get("vertex_index", lv)
    uv.data.foreach_set("uv", uvs.reshape(-1, 2)[lv].ravel())
    # normal = direção do fio (o shader usa para virar a fita para a câmera)
    tn = np.stack([tang, tang], axis=2).reshape(-1, 3)
    malha.normals_split_custom_set_from_vertices(tn.tolist())
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.scene.collection.objects.link(obj)
    # a largura do fio vai no nome do material (o shader da engine lê: _cabelo_fios_70 = 0,7 mm)
    mat = bpy.data.materials.new(nome.replace("_hair", "") + f"_cabelo_fios_{int(round(largura * 1e5))}")
    mat.use_nodes = True
    bsdf = next(nd for nd in mat.node_tree.nodes if nd.type == "BSDF_PRINCIPLED")
    cl = np.array(c.cor_hex(cor))
    lum = float(cl @ np.array([0.2126, 0.7152, 0.0722]))
    cl = (lum + (cl - lum) * 0.75) * 0.7
    bsdf.inputs["Base Color"].default_value = (*cl.tolist(), 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    mat.use_backface_culling = False
    mat["fornalha_cabelo"] = True
    malha.materials.append(mat)
    if arm is not None:
        g = obj.vertex_groups.new(name="head")
        g.add(list(range(len(malha.vertices))), 1.0, "REPLACE")
        mod = obj.modifiers.new("esqueleto", "ARMATURE")
        mod.object = arm
        obj.parent = arm
    # no render aparecem os fios de verdade; esta malha é a da engine
    obj.hide_render = True
    return obj


# ------------------------------------------------------------------ cards em 4 camadas (padrão AAA)
# Bíblia técnica, seção 4: o penteado de fios é a FONTE; o jogo recebe
#   camada 0: couro cabeludo (casca a 0,5 mm com fade na linha do cabelo),
#   camada 1: cards largos e densos (volume), camada 2: cards médios (quebra de volume),
#   camada 3: fios soltos finos (linha da testa, coroa, nuca),
# com um atlas de mechas (cor com raiz escura e variação por fio, alfa fio a fio, e um mapa de
# dados: oclusão, profundidade e raiz) e normais transferidas de uma casca lisa (volume único).

VARIANTES = 8


def atlas_de_mechas(cor, res=2048, semente=3, grisalho=0.0):
    """Atlas com 8 mechas lado a lado, da mais densa (0) à mais rala (7). Raiz em cima (V=1).
    Devolve (imagem_cor RGBA, imagem_dados RGB: R=oclusão, G=profundidade, B=raiz→ponta)."""
    rng = np.random.default_rng(semente)
    W = res // VARIANTES
    H = res
    base = np.array(c.cor_hex(cor), dtype=np.float32)  # linear
    cor_img = np.zeros((H, res, 3), dtype=np.float32)
    alfa = np.zeros((H, res), dtype=np.float32)
    prof = np.zeros((H, res), dtype=np.float32)
    dens = np.zeros((H, res), dtype=np.float32)
    v = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]  # 0 = raiz (linha de cima), 1 = ponta
    cols = np.arange(W, dtype=np.float32)[None, :]
    for k in range(VARIANTES):
        n_fios = int(np.interp(k, [0, VARIANTES - 1], [230, 45]))
        x0 = k * W
        for _ in range(n_fios):
            cx = rng.uniform(0.04, 0.96) * W
            fim = rng.uniform(0.6, 1.0) if k < 5 else rng.uniform(0.45, 1.0)
            amp = rng.uniform(0.3, 2.2)
            fase, freq = rng.uniform(0, 2 * np.pi), rng.uniform(0.6, 2.4)
            esp = rng.uniform(0.5, 1.0) * (W / 256.0)
            curva = rng.uniform(-0.06, 0.06) * W
            x = cx + amp * np.sin(v * freq * 2 * np.pi + fase) + curva * v ** 2
            d = np.abs(cols - x)
            a = np.exp(-((d / esp) ** 2))
            a = a * (v <= fim) * np.clip((fim - v) / 0.1, 0, 1) * np.clip(v / 0.04 + 0.35, 0, 1)
            # menos fios na borda da mecha (a fita não aparece)
            a = a * np.clip(min(cx, W - cx) / (0.15 * W), 0.3, 1.0)
            idf = rng.uniform(0.0, 1.0)
            pf = rng.uniform(0.0, 1.0)
            sub = alfa[:, x0:x0 + W]
            muda = a > sub
            # cada fio com o seu tom: a maioria perto da cor, alguns mais claros (sol) ou mais escuros;
            # com a idade, uma parte dos fios fica branca/grisalha
            tom = base * (0.84 + 0.3 * idf)
            if rng.random() < 0.06:
                tom = np.clip(base * 1.3 + 0.02, 0, 1)
            if rng.random() < grisalho:
                tom = np.array([0.55, 0.53, 0.5], dtype=np.float32) * rng.uniform(0.8, 1.1)
            cs = cor_img[:, x0:x0 + W]
            cs[muda] = np.broadcast_to(tom, cs.shape)[muda]
            ps = prof[:, x0:x0 + W]
            ps[muda] = pf
            alfa[:, x0:x0 + W] = np.maximum(sub, a)
            dens[:, x0:x0 + W] += a
    raiz = np.broadcast_to(np.clip(v * 1.6, 0, 1), (H, res))
    # oclusão: onde há muitos fios e perto da raiz fica mais escuro
    import fc_pele

    ao = 1.0 - 0.35 * np.clip(fc_pele.borrar(dens, 3) / 3.0, 0, 1) * (1.0 - 0.6 * raiz)
    # raiz só um pouco mais escura: nas mechas curtas (lados e nuca) raiz escura + ponta clara virava
    # "carimbo" claro/escuro repetido; o escuro de profundidade vem do couro e da oclusão
    cor_img = cor_img * (0.76 + 0.24 * raiz[..., None]) * ao[..., None]
    vazio = alfa < 0.01
    cor_img[vazio] = base * 0.6
    srgb = np.clip(cor_img, 0, 1) ** (1 / 2.2)
    img_cor = fc_pele._imagem("cabelo_atlas_cor", np.concatenate([srgb, alfa[..., None]], -1), False, alfa=True)
    img_dados = fc_pele._imagem("cabelo_atlas_dados", np.stack([ao, prof, raiz], -1), True)
    return img_cor, img_dados


def _caminho_medio(P, membros):
    return P[membros].mean(0)


def cards_do_penteado(P, campo, pontos, semente=7, escala_n=1.0, faixas=None, longo=False):
    """Monta os cards das camadas 1-3 a partir dos fios. Devolve listas de vértices/faces/uvs."""
    rng = np.random.default_rng(semente)
    s = pontos["s"]
    nf, npts = P.shape[:2]
    R = P[:, 0]
    borda = mascara_couro(R[:, 0], R[:, 1], R[:, 2], pontos)
    # fios soltos/ondulados não servem de centro de mecha (a fita enrolaria junto)
    seg = np.diff(P, axis=1)
    seg /= np.linalg.norm(seg, axis=-1, keepdims=True) + 1e-9
    giro = np.degrees(np.arccos(np.clip((seg[:, 1:] * seg[:, :-1]).sum(-1), -1, 1))).sum(1)
    liso = giro <= np.percentile(giro, 85)
    camadas = [
        # (n cards, largura min/max m, altura extra m, variantes, só borda?)
        (int(520 * escala_n), (0.012, 0.024), 0.0, (0, 1, 2), False),
        # camada do meio mais densa: o couro cabeludo aparecia entre as mechas no alto (manchas)
        (int(860 * escala_n), (0.006, 0.012), 0.0011, (2, 3, 4, 5), False),
        (int(220 * escala_n), (0.0022, 0.0045), 0.0018, (6, 7), True),
    ]
    if longo:
        # comprido: fitas longas cobrem com menos cards, mais largos, em camadas (base larga, meio e
        # algumas mechas soltas na borda); muitas fitas estreitas se cruzavam e viravam moita
        camadas = [
            (int(300 * escala_n), (0.022, 0.040), 0.0, (0, 1, 2), False),
            (int(480 * escala_n), (0.010, 0.020), 0.0015, (2, 3, 4, 5), False),
            (int(140 * escala_n), (0.003, 0.006), 0.0025, (6, 7), True),
        ]
    oy = (pontos["olho_l"][1] + pontos["olho_r"][1]) / 2
    eixo = np.array([0.0, oy + 0.085 * s, 0.0])
    V, F, UV = [], [], []
    for n, (lmin, lmax), extra, variantes, so_borda in camadas:
        pesos = np.where(liso, 1.0, 0.0)
        if so_borda:
            pesos = pesos * np.where((borda > 0.45) & (borda < 0.9), 6.0, 1.0)
        pesos = pesos / pesos.sum()
        centros = rng.choice(nf, n, replace=False, p=pesos)
        # agrupa os fios pelo centro mais perto: pela raiz no curto; no comprido pelo caminho inteiro
        # (fios de raízes vizinhas caem por lados diferentes do ombro, e a média virava zigue-zague)
        dono = np.empty(nf, dtype=np.int64)
        if longo:
            amostra = np.linspace(0, npts - 1, 7).astype(int)
            D = P[:, amostra].reshape(nf, -1)
            Dc = D[centros]
        for a in range(0, nf, 5000):
            b = min(nf, a + 5000)
            if longo:
                dd = np.linalg.norm(D[a:b, None, :] - Dc[None, :, :], axis=-1)
            else:
                dd = np.linalg.norm(R[a:b, None, :] - R[None, centros, :], axis=-1)
            dono[a:b] = np.argmin(dd, axis=1)
        for k, ci in enumerate(centros):
            membros = np.nonzero(dono == k)[0]
            if len(membros) < 3:
                continue
            lisos = membros[liso[membros]]
            if so_borda or len(lisos) < 3 or longo:
                caminho = P[ci].copy()
            else:
                # caminho da mecha: média dos fios lisos, puxada para o fio central (não encolhe)
                caminho = 0.6 * P[lisos].mean(0) + 0.4 * P[ci]
            caminho = _alisar_fios(caminho[None], 4)[0]
            dist, nrm = campo(caminho)
            if longo:
                # longe da pele a normal do campo não diz onde é "fora" do cabelo: lá a face do card
                # olha para fora a partir do eixo da cabeça (o cabelo que pende é uma casca em volta)
                radial = caminho - eixo
                radial[:, 2] = 0.0
                radial /= np.linalg.norm(radial, axis=-1, keepdims=True) + 1e-9
                w = np.clip((dist - 0.012 * s) / (0.02 * s), 0.0, 1.0)[:, None]
                nrm = nrm * (1 - w) + radial * w
                nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
                dist = np.where(w[:, 0] > 0, 1.0, dist)
            caminho = caminho + nrm * (extra + max(0.0, 0.0008 * s - float(dist.min())))
            tang = np.gradient(caminho, axis=0)
            tang /= np.linalg.norm(tang, axis=-1, keepdims=True) + 1e-9
            lado = np.cross(tang, nrm)
            lado /= np.linalg.norm(lado, axis=-1, keepdims=True) + 1e-9
            espalho = np.abs(((P[membros, 0] - P[ci, 0]) * lado[0]).sum(-1))
            larg = np.clip(2.2 * float(np.percentile(espalho, 80)) if len(espalho) else lmin, lmin, lmax) * s
            if so_borda:
                larg = rng.uniform(lmin, lmax) * s
            torcao = rng.normal(0, 0.25 if so_borda else 0.12) * (0.4 if longo else 1.0)
            var = int(rng.choice(variantes))
            u0, u1 = var / VARIANTES, (var + 1) / VARIANTES
            base_i = len(V)
            m = len(caminho)
            if faixas is not None:
                faixas.append((base_i, m))
            for j in range(m):
                t = j / (m - 1)
                w = larg * (1.0 - 0.35 * t)
                ang = torcao * t
                ld = lado[j] * np.cos(ang) + nrm[j] * np.sin(ang)
                # perfil em "U" suave: o meio do card um pouco mais alto (não some de perfil)
                meio = caminho[j] + nrm[j] * (0.0006 * s * (w / (0.01 * s)))
                V.extend([caminho[j] - ld * w / 2, meio, caminho[j] + ld * w / 2])
                vv = 1.0 - t
                UV.extend([(u0, vv), ((u0 + u1) / 2, vv), (u1, vv)])
            for j in range(m - 1):
                a0 = base_i + j * 3
                b0 = a0 + 3
                F.append((a0, a0 + 1, b0 + 1, b0))
                F.append((a0 + 1, a0 + 2, b0 + 2, b0 + 1))
    return np.array(V), F, UV


def material_cards(nome, img_cor, img_dados):
    """Material dos cards (render e glTF): cor + alfa com hash, oclusão no canal de oclusão do
    glTF (a engine lê os dados de lá) e brilho anisotrópico pela direção do fio (V do UV)."""
    mat = bpy.data.materials.new(nome)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = img_cor
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tc.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.42
    for k, v in (("Specular IOR Level", 0.5), ("Anisotropic", 0.75), ("Sheen Weight", 0.2), ("Sheen Roughness", 0.4)):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    tg = nt.nodes.new("ShaderNodeTangent")
    tg.direction_type = "UV_MAP"
    tg.uv_map = "UVMap"
    if "Tangent" in bsdf.inputs:
        nt.links.new(tg.outputs["Tangent"], bsdf.inputs["Tangent"])
    # oclusão (o exportador glTF leva a imagem como occlusionTexture: R=oclusão, G=profundidade, B=raiz)
    td = nt.nodes.new("ShaderNodeTexImage")
    td.image = img_dados
    gltf = bpy.data.node_groups.get("glTF Material Output")
    if gltf is None:
        gltf = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        gltf.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    gnode = nt.nodes.new("ShaderNodeGroup")
    gnode.node_tree = gltf
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(td.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Red"], gnode.inputs["Occlusion"])
    try:
        mat.blend_method = "HASHED"
    except Exception:
        pass
    mat.use_backface_culling = False
    mat["fornalha_cabelo_cards"] = True
    return mat


def couro_cabeludo_cap(corpo, pontos, cor, res=2048, semente=9):
    """Camada 0: o couro cabeludo duplicado a 0,5 mm da pele, com a cor do cabelo, fios curtinhos
    e fade suave e irregular na linha do cabelo (sem faixa escura dura)."""
    import fc_pele

    rng = np.random.default_rng(semente)
    m = corpo.data
    co = np.array([v.co[:] for v in m.vertices])
    mk = mascara_couro(co[:, 0], co[:, 1], co[:, 2], pontos)
    dentro = {i for p in m.polygons if max(mk[i] for i in p.vertices) > 0.02 for i in p.vertices}
    faces = [p for p in m.polygons if any(i in dentro for i in p.vertices)]  # + um anel de faces
    if not faces:
        return None
    vs = sorted({i for p in faces for i in p.vertices})
    novo = {v: k for k, v in enumerate(vs)}
    nor = np.empty(len(m.vertices) * 3)
    m.vertex_normals.foreach_get("vector", nor)
    nor = nor.reshape(-1, 3)
    pts = co[vs] + nor[vs] * 0.0005
    malha = bpy.data.meshes.new(corpo.name.replace("_corpo", "") + "_couro_cabeludo")
    malha.from_pydata(pts.tolist(), [], [[novo[i] for i in p.vertices] for p in faces])
    uv_src = m.uv_layers.active.data
    uv = malha.uv_layers.new(name="UVMap")
    k = 0
    for p in faces:
        for li in p.loop_indices:
            uv.data[k].uv = uv_src[li].uv
            k += 1
    obj = bpy.data.objects.new(malha.name, malha)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = corpo.matrix_world
    for p_ in malha.polygons:
        p_.use_smooth = True
    # textura no UV do corpo: cor do cabelo com fios curtos e alfa = máscara com linha irregular
    pos, mask, _ = fc_pele.rasterizar(corpo, res)
    irregular = fc_pele._normalizar(fc_pele.borrar(rng.standard_normal((res, res)).astype(np.float32), 1)) * 0.6
    # bordas mais largas que as das raízes dos cards: a linha da têmpora e a costeleta sem cantos retos
    a = mascara_couro(pos[..., 0], pos[..., 1], pos[..., 2], pontos, irregular, suave=2.2) * mask
    pontinhos = np.clip(fc_pele._normalizar(fc_pele.borrar(rng.standard_normal((res, res)).astype(np.float32), 1)) * 0.5 + 0.5, 0, 1)
    base = np.array(c.cor_hex(cor), dtype=np.float32)
    # o que aparece entre os cards é a massa de cabelo na sombra: cor uniforme, um pouco mais escura que
    # as mechas e com pouco contraste (manchas grandes viravam "camuflagem" no topo e nos lados)
    cor_img = base[None, None, :] * (0.78 + 0.06 * pontinhos[..., None])
    # opaco por dentro (não aparece pele entre os cards); só a faixa de fora da linha esmaece, irregular
    borda_fina = np.clip(_sstep(0.12, 0.55, a) - 0.18 * (1.0 - a) * pontinhos, 0, 1)
    alfa = np.where(a > 0.55, 1.0, borda_fina)
    rgba = np.concatenate([np.clip(cor_img, 0, 1) ** (1 / 2.2), alfa[..., None]], -1)
    rgba = fc_pele.dilatar(rgba, mask)
    img = fc_pele._imagem(malha.name + "_cor", rgba, False, alfa=True)
    mat = bpy.data.materials.new(malha.name + "_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.7
    try:
        mat.blend_method = "HASHED"
    except Exception:
        pass
    mat["fornalha_couro_cabeludo"] = True
    malha.materials.append(mat)
    return obj


def transferir_normais(alvo, casca):
    """Normais dos cards vindas da casca lisa do penteado: a luz envolve o cabelo como um volume
    único (sem "pedaços de papelão")."""
    for o in bpy.context.scene.objects:
        o.select_set(o == alvo)
    bpy.context.view_layer.objects.active = alvo
    mod = alvo.modifiers.new("normais_da_casca", "DATA_TRANSFER")
    mod.object = casca
    mod.use_loop_data = True
    mod.data_types_loops = {"CUSTOM_NORMAL"}
    mod.loop_mapping = "POLYINTERP_NEAREST"
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception as e:  # sem a transferência, os cards ficam com as normais próprias
        print(f"[cabelo] transferência de normais falhou: {e}")
        alvo.modifiers.remove(mod)


def normais_de_capsula(cards, pontos):
    """Normais de volume para o cabelo que pende: esfera em volta do crânio no alto e cilindro abaixo
    (o eixo da cabeça). A casca do couro cabeludo só cobre o crânio; nos cards longe dela a normal
    transferida saía errada e o brilho estourava em branco."""
    s = pontos["s"]
    oy = (pontos["olho_l"][1] + pontos["olho_r"][1]) / 2
    cy, cz = oy + 0.085 * s, pontos["olho_z"] + 0.03 * s
    me = cards.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(cards.matrix_world)
    mundo = co @ M[:3, :3].T + M[:3, 3]
    centro = np.stack([np.zeros(len(mundo)), np.full(len(mundo), cy), np.minimum(mundo[:, 2], cz)], -1)
    n = mundo - centro
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    # de volta para o espaço do objeto (só rotação)
    R = np.linalg.inv(M[:3, :3]).T
    n = n @ R.T
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    try:
        me.normals_split_custom_set_from_vertices([tuple(v) for v in n])
    except Exception as e:  # sem isso, ficam as normais dos próprios cards
        print(f"[cabelo] normais de cápsula falharam: {e}")


def cabelo_em_cards(nome, corpo, pontos, cabeca_peso, cor, estilo, arm, escala_n=1.0, res_atlas=2048, grisalho=0.0):
    """Pipeline completo de cabelo AAA. Devolve [couro_cabeludo, cards] (objetos do jogo)."""
    P, raios, campo = crescer_fios(corpo, pontos, cabeca_peso, estilo, devolver_campo=True)
    if P is None:
        return []
    img_cor, img_dados = atlas_de_mechas(cor, res_atlas, grisalho=grisalho)
    V, F, UV = cards_do_penteado(P, campo, pontos, escala_n=escala_n, longo=estilo != "curto")
    malha = bpy.data.meshes.new(f"{nome}_hair")
    malha.from_pydata(V.tolist(), [], F)
    uv = malha.uv_layers.new(name="UVMap")
    lv = np.empty(len(malha.loops), dtype=np.int64)
    malha.loops.foreach_get("vertex_index", lv)
    uv.data.foreach_set("uv", np.array(UV, dtype=np.float32)[lv].ravel())
    for p_ in malha.polygons:
        p_.use_smooth = True
    cards = bpy.data.objects.new(malha.name, malha)
    bpy.context.scene.collection.objects.link(cards)
    cards.matrix_world = corpo.matrix_world
    malha.materials.append(material_cards(f"{nome}_cabelo_cards", img_cor, img_dados))
    # casca lisa do penteado (envolve os cards) só para transferir as normais
    cap = couro_cabeludo_cap(corpo, pontos, cor)
    if cap is not None:
        casca = cap.copy()
        casca.data = cap.data.copy()
        bpy.context.scene.collection.objects.link(casca)
        bm_co = np.array([v.co[:] for v in casca.data.vertices])
        dist, nrm = campo(bm_co)
        alto = pontos["olho_z"] + 0.06 * pontos["s"]
        h = np.where(bm_co[:, 2] > alto, 0.008, 0.004) * pontos["s"]
        for v, n_, hh in zip(casca.data.vertices, nrm, h):
            v.co = v.co + Vector(n_ * hh)
        sm = casca.modifiers.new("lisa", "SMOOTH")
        sm.factor, sm.iterations = 1.0, 20
        for o in bpy.context.scene.objects:
            o.select_set(o == casca)
        bpy.context.view_layer.objects.active = casca
        bpy.ops.object.modifier_apply(modifier=sm.name)
        if estilo == "curto":
            transferir_normais(cards, casca)
        else:
            normais_de_capsula(cards, pontos)
        bpy.data.objects.remove(casca)
    objs = [o for o in (cap, cards) if o is not None]
    for o in objs:
        if arm is not None:
            g = o.vertex_groups.new(name="head")
            g.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
            mod = o.modifiers.new("esqueleto", "ARMATURE")
            mod.object = arm
            o.parent = arm
    return objs
