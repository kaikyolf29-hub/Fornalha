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


def atlas_de_mechas(cor, res=2048, semente=3, grisalho=0.0, fios=(230, 45), espessura=1.0, onda=1.0):
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
    nx = np.zeros((H, res), dtype=np.float32)  # normal de cada fio (cilindro): o brilho quebra fio a fio
    v = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]  # 0 = raiz (linha de cima), 1 = ponta
    cols = np.arange(W, dtype=np.float32)[None, :]
    for k in range(VARIANTES):
        n_fios = int(np.interp(k, [0, VARIANTES - 1], list(fios)))
        x0 = k * W
        for _ in range(n_fios):
            cx = rng.uniform(0.04, 0.96) * W
            fim = rng.uniform(0.6, 1.0) if k < 5 else rng.uniform(0.45, 1.0)
            amp = rng.uniform(0.3, 2.2) * onda
            fase, freq = rng.uniform(0, 2 * np.pi), rng.uniform(0.6, 2.4) * (1.0 + 0.5 * (onda - 1.0))
            esp = rng.uniform(0.5, 1.0) * (W / 256.0) * espessura
            # fio branco é mais fino e um pouco transparente: grisalho de perto é sal e pimenta fino,
            # não risco claro grosso (que lia como rabisco)
            branco = rng.random() < grisalho
            if branco:
                esp *= 0.6
            curva = rng.uniform(-0.06, 0.06) * W
            x = cx + amp * np.sin(v * freq * 2 * np.pi + fase) + curva * v ** 2
            d = np.abs(cols - x)
            a = np.exp(-((d / esp) ** 2))
            a = a * (v <= fim) * np.clip((fim - v) / 0.1, 0, 1) * np.clip(v / 0.04 + 0.35, 0, 1)
            # menos fios na borda da mecha (a fita não aparece)
            a = a * np.clip(min(cx, W - cx) / (0.15 * W), 0.3, 1.0) * (0.8 if branco else 1.0)
            idf = rng.uniform(0.0, 1.0)
            pf = rng.uniform(0.0, 1.0)
            sub = alfa[:, x0:x0 + W]
            muda = a > sub
            # cada fio com o seu tom: a maioria perto da cor, alguns mais claros (sol) ou mais escuros;
            # com a idade, uma parte dos fios fica branca/grisalha
            tom = base * (0.84 + 0.3 * idf)
            if rng.random() < 0.06:
                tom = np.clip(base * 1.3 + 0.02, 0, 1)
            if branco:
                tom = np.array([0.36, 0.35, 0.33], dtype=np.float32) * rng.uniform(0.75, 1.15)
            cs = cor_img[:, x0:x0 + W]
            cs[muda] = np.broadcast_to(tom, cs.shape)[muda]
            ps = prof[:, x0:x0 + W]
            ps[muda] = pf
            ns = nx[:, x0:x0 + W]
            ns[muda] = np.broadcast_to(np.clip((cols - x) / (esp * 1.6), -1, 1), ns.shape)[muda]
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
    nz = np.sqrt(np.clip(1 - nx * nx, 0, 1))
    img_normal = fc_pele._imagem("cabelo_atlas_normal", np.stack([nx * 0.5 + 0.5, np.full_like(nx, 0.5), nz * 0.5 + 0.5], -1), True)
    return img_cor, img_dados, img_normal


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


def material_cards(nome, img_cor, img_dados, img_normal=None):
    """Material dos cards (render e glTF): cor + alfa com hash, oclusão no canal de oclusão do
    glTF (a engine lê os dados de lá) e brilho anisotrópico pela direção do fio (V do UV)."""
    mat = bpy.data.materials.new(nome)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = img_cor
    # tom de cada mecha (cor de vértice "Col"; sem ela, branco)
    tom = nt.nodes.new("ShaderNodeVertexColor")
    tom.layer_name = "Col"
    mult = nt.nodes.new("ShaderNodeMix")
    mult.data_type = "RGBA"
    mult.blend_type = "MULTIPLY"
    mult.inputs["Factor"].default_value = 1.0
    nt.links.new(tc.outputs["Color"], mult.inputs["A"])
    nt.links.new(tom.outputs["Color"], mult.inputs["B"])
    nt.links.new(mult.outputs["Result"], bsdf.inputs["Base Color"])
    nt.links.new(tc.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.58
    if img_normal is not None:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img_normal
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.uv_map = "UVMap"
        nm.inputs["Strength"].default_value = 0.9
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    for k, v in (("Specular IOR Level", 0.28), ("Anisotropic", 0.8), ("Sheen Weight", 0.0), ("Coat Weight", 0.0)):
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
    img_cor, img_dados, img_normal = atlas_de_mechas(cor, res_atlas, grisalho=grisalho)
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
    malha.materials.append(material_cards(f"{nome}_cabelo_cards", img_cor, img_dados, img_normal))
    branco = malha.color_attributes.new("Col", "BYTE_COLOR", "POINT")  # tom neutro (o material multiplica)
    branco.data.foreach_set("color", np.ones(len(malha.vertices) * 4, dtype=np.float32))
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


# ---------------- cards guiados pela malha do penteado (médio e comprido) ----------------

def _fluxo_por_triangulo(V, T, UV, sinal):
    """Direção raiz→ponta em cada triângulo: para onde o V do UV anda (a textura tem a raiz em cima)."""
    p0, p1, p2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    t0, t1, t2 = UV[:, 0], UV[:, 1], UV[:, 2]
    e1, e2 = p1 - p0, p2 - p0
    du1, dv1 = (t1 - t0)[:, 0:1], (t1 - t0)[:, 1:2]
    du2, dv2 = (t2 - t0)[:, 0:1], (t2 - t0)[:, 1:2]
    det = du1 * dv2 - du2 * dv1
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    B = (e2 * du1 - e1 * du2) / det  # direção em que o V cresce
    B = B * sinal
    n = np.cross(e1, e2)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    B -= n * np.sum(B * n, axis=1, keepdims=True)  # no plano do triângulo
    B /= np.maximum(np.linalg.norm(B, axis=1, keepdims=True), 1e-12)
    return B, n


PESOS_DO_CABELO = ("head", "neck", "spine", "clavicle")


def limpar_pesos_cabelo(obj):
    """Cabelo só segue cabeça, pescoço, costas e clavícula (o pacote põe peso de braço, quadril e coxa
    nas pontas do comprido: o braço arrastaria o cabelo). Renormaliza; sem peso nenhum vai para spine_03."""
    nomes = {g.index: g.name for g in obj.vertex_groups}
    ruins = [g for g in obj.vertex_groups if not g.name.startswith(PESOS_DO_CABELO)]
    reserva = obj.vertex_groups.get("spine_03") or obj.vertex_groups.new(name="spine_03")
    bons = {g.index for g in obj.vertex_groups if g.name.startswith(PESOS_DO_CABELO)} | {reserva.index}
    for v in obj.data.vertices:
        pares = [(ge.group, ge.weight) for ge in v.groups if ge.group in bons and ge.weight > 1e-4]
        tot = sum(w for _, w in pares)
        if tot < 1e-4:
            reserva.add([v.index], 1.0, "REPLACE")
            continue
        for gi, w in pares:
            obj.vertex_groups[nomes.get(gi, reserva.name)].add([v.index], w / tot, "REPLACE")
    for g in ruins:
        obj.vertex_groups.remove(g)


def _escurecer_camada_de_baixo(guia, cor, escuro=0.6, borda_suave=True):
    img = _imagem_de_cor(guia)
    for m in guia.data.materials:
        if m and m.use_nodes:
            bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is not None:
                bsdf.inputs["Roughness"].default_value = 0.75
    if img is None:
        return
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    lum = px[..., :3] @ np.array([0.3, 0.59, 0.11], np.float32)
    media = float(lum[px[..., 3] > 0.3].mean()) if (px[..., 3] > 0.3).any() else 0.5
    alvo = np.array([int(cor.lstrip("#")[k:k + 2], 16) / 255.0 for k in (0, 2, 4)], np.float32) * escuro  # sRGB, mais escuro
    var = np.clip(0.55 + 0.45 * lum / max(media, 1e-3), 0.3, 1.4)[..., None]  # mantém o desenho dos fios
    novo = np.empty_like(px)
    novo[..., :3] = np.clip(alvo * var, 0, 1)
    novo[..., 3] = np.clip(px[..., 3] * 2.2, 0, 1)  # camada funda densa: o couro não aparece por ela
    if borda_suave:  # com os cards por cima, a borda dela vai sumindo (linha do cabelo sem degrau)
        novo[..., 3] *= _borda_suave(guia, w, h)
    nova = bpy.data.images.new(f"{img.name}_fundo", width=w, height=h, alpha=True)
    nova.pixels.foreach_set(novo.ravel())
    nova.pack()
    for m in guia.data.materials:
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image == img:
                    n.image = nova


def _borda_suave(guia, w, h, largura_m=0.007):
    """Fator de alfa (h×w) que cai a zero na borda da malha-guia (linha do cabelo, costeleta, nuca):
    a linha do cabelo nasce aos poucos, em vez da borda dura de peruca (com a pele vermelha embaixo)."""
    import fc_pele
    from collections import Counter

    me = guia.data
    uvl = me.uv_layers.active
    if uvl is None:
        return np.ones((h, w), np.float32)
    conta = Counter(k for p_ in me.polygons for k in p_.edge_keys)
    borda = np.zeros((h, w), np.float32)
    px_por_m = []
    for p_ in me.polygons:
        ls = list(p_.loop_indices)
        for i, li in enumerate(ls):
            lj = ls[(i + 1) % len(ls)]
            va, vb = me.loops[li].vertex_index, me.loops[lj].vertex_index
            ua, ub = np.array(uvl.data[li].uv) * (w, h), np.array(uvl.data[lj].uv) * (w, h)
            mundo = (me.vertices[va].co - me.vertices[vb].co).length
            if mundo > 1e-6:
                px_por_m.append(np.linalg.norm(ua - ub) / mundo)
            if conta[(min(va, vb), max(va, vb))] != 1:
                continue
            n = int(np.linalg.norm(ub - ua) * 2) + 2
            for t in np.linspace(0.0, 1.0, n):
                x, y = (ua + (ub - ua) * t).astype(int)
                if 0 <= x < w and 0 <= y < h:
                    borda[y, x] = 1.0
    if not borda.any() or not px_por_m:
        return np.ones((h, w), np.float32)
    r = max(2, int(float(np.median(px_por_m)) * largura_m / 2))
    perto = fc_pele.borrar(borda, r)
    perto = perto / max(float(np.percentile(perto[borda > 0], 50)), 1e-6)  # 1 em cima da borda
    return np.clip(1.0 - perto, 0.0, 1.0) ** 0.7


def _imagem_de_cor(obj):
    for m in obj.data.materials:
        if m is None or not m.use_nodes:
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        for l_ in m.node_tree.links:
            if l_.to_node == bsdf and l_.to_socket.name == "Base Color" and l_.from_node.type == "TEX_IMAGE":
                return l_.from_node.image
    return None


def _fluxo_da_textura(guia, V, T, UV, saindo):
    """Direção dos fios em cada triângulo pela textura do penteado (tensor de estrutura: os fios correm
    perpendiculares ao gradiente de brilho), levada para 3D pelo mapeamento do UV; sentido raiz → ponta."""
    img = _imagem_de_cor(guia)
    if img is None or img.size[0] < 16:
        return None
    import fc_pele

    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    lum = (px[..., :3] @ np.array([0.3, 0.59, 0.11], np.float32)) * px[..., 3]
    gy, gx = np.gradient(lum)
    r = max(2, w // 256)
    jxx, jyy, jxy = (fc_pele.borrar(a, r) for a in (gx * gx, gy * gy, gx * gy))
    tri_uv = UV.mean(axis=1)
    cx = np.clip((tri_uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(np.int64)
    cy = np.clip((tri_uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(np.int64)
    a_, b_, c_ = jxx[cy, cx], jyy[cy, cx], jxy[cy, cx]
    ang = 0.5 * np.arctan2(2 * c_, a_ - b_) + np.pi / 2  # perpendicular ao gradiente = ao longo do fio
    coer = np.sqrt((a_ - b_) ** 2 + 4 * c_ ** 2) / np.maximum(a_ + b_, 1e-9)
    opaco = px[cy, cx, 3] > 0.3
    du = np.cos(ang)
    dv = np.sin(ang)
    p0, p1, p2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = UV[:, 1] - UV[:, 0], UV[:, 2] - UV[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    dpdu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]
    dpdv = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]
    d3 = dpdu * du[:, None] + dpdv * dv[:, None]
    n = np.cross(e1, e2)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    d3 -= n * np.sum(d3 * n, axis=1, keepdims=True)
    d3 /= np.maximum(np.linalg.norm(d3, axis=1, keepdims=True), 1e-12)
    d3 *= np.where(np.sum(d3 * saindo, axis=1) < 0, -1.0, 1.0)[:, None]  # da raiz (topo) para a ponta
    return d3, coer, opaco


def _suavizar_fluxo(B, T, saindo, passes=4):
    """Média com os vizinhos (o fluxo da textura tem ruído); o sentido continua do topo para fora."""
    from collections import defaultdict

    viz = defaultdict(list)
    por_v = defaultdict(list)
    for i, t in enumerate(T):
        for v in t:
            por_v[v].append(i)
    for lst in por_v.values():
        for i in lst:
            viz[i].extend(lst)
    idx = [np.unique(viz[i]) for i in range(len(T))]
    for _ in range(passes):
        novo = np.array([B[j].sum(axis=0) for j in idx])
        novo /= np.maximum(np.linalg.norm(novo, axis=1, keepdims=True), 1e-12)
        novo *= np.where(np.sum(novo * saindo, axis=1) < 0, -1.0, 1.0)[:, None]
        B = novo
    return B


ESTILO_CABELO = {"volume_cm": 1.0, "agrupamento": 0.55, "ondulacao": 0.15, "frizz": 0.15, "densidade": 1.0}
# para onde vão os fios (raiz → ponta). "caindo": do topo da cabeça para fora e para baixo (comprido, bob);
# "para_tras": da testa para a nuca (penteado para trás); "para_frente": da coroa para a testa (franja)
DIRECAO_PADRAO = {"short04": "para_tras", "short02": "para_frente", "short03": "para_frente"}
DIRECOES = ("auto", "caindo", "para_tras", "para_frente")


def cards_guiados(nome, guia, cor, arm, n_cards=800, semente=7, grisalho=0.0, res_atlas=2048, estilo=None, penteado=""):
    """Cards traçados SOBRE a malha do penteado (o cabelo do pacote), da raiz à ponta, seguindo a
    direção dos fios dada pelo UV dela. A malha vira a camada de baixo (mais escura, cobre o couro) e
    os cards por cima dão os fios e a silhueta, sem espetar para fora da forma do penteado."""
    from mathutils.bvhtree import BVHTree

    rng = np.random.default_rng(semente)
    est = dict(ESTILO_CABELO)
    est.update({k: float(v) for k, v in (estilo or {}).items() if k in est})
    n_cards = max(50, int(n_cards * est["densidade"]))
    vol, agr, ond, friz = est["volume_cm"] / 100.0, est["agrupamento"], est["ondulacao"], est["frizz"]
    me = guia.data
    me.calc_loop_triangles()
    M = np.array(guia.matrix_world)
    V = np.array([v.co[:] for v in me.vertices], dtype=np.float64)
    V = V @ M[:3, :3].T + M[:3, 3]
    T = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.int64)
    uvl = me.uv_layers.active
    if uvl is None or not len(T):
        return []
    UVloop = np.array([d.uv[:] for d in uvl.data], dtype=np.float64)
    UV = UVloop[np.array([t.loops[:] for t in me.loop_triangles], dtype=np.int64)]
    # a direção dos fios na textura muda de penteado para penteado (V ou U, num sentido ou no outro):
    # fica a que mais aponta do topo da cabeça para fora e para baixo (raiz → ponta)
    centro_tri = (V[T[:, 0]] + V[T[:, 1]] + V[T[:, 2]]) / 3
    topo = np.array([V[:, 0].mean(), V[:, 1].mean(), V[:, 2].max()])
    saindo = centro_tri - topo
    saindo /= np.maximum(np.linalg.norm(saindo, axis=1, keepdims=True), 1e-9)
    direcao = (estilo or {}).get("direcao") or DIRECAO_PADRAO.get(penteado, "auto")
    if direcao in ("para_tras", "para_frente"):
        # no Blender a frente é -Y: para trás = +Y (e um pouco para baixo); a ponta vai nesse rumo
        rumo = np.array([0.0, 1.0 if direcao == "para_tras" else -1.0, -0.45])
        rumo /= np.linalg.norm(rumo)
        # atrás da cabeça o cabelo cai: mistura o rumo com o "para fora e para baixo"
        atras = np.clip((centro_tri[:, 1] - V[:, 1].mean()) / max(np.ptp(V[:, 1]) * 0.5, 1e-6), 0, 1)[:, None]
        if direcao == "para_frente":
            atras = 1.0 - np.clip((V[:, 1].mean() - centro_tri[:, 1]) / max(np.ptp(V[:, 1]) * 0.5, 1e-6), 0, 1)[:, None]
        saindo = rumo[None, :] * (1 - atras) + saindo * atras
        saindo /= np.maximum(np.linalg.norm(saindo, axis=1, keepdims=True), 1e-9)
    area_t = np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
    melhor = None
    for eixo in (1, 0):
        UVe = UV if eixo == 1 else UV[:, :, ::-1]  # U no lugar do V
        for sinal in (-1.0, 1.0):
            Bc, Nc = _fluxo_por_triangulo(V, T, UVe, sinal)
            nota = float((np.sum(Bc * saindo, axis=1) * area_t).sum() / area_t.sum())
            if melhor is None or nota > melhor[0]:
                melhor = (nota, Bc, Nc, eixo, sinal)
    _, B, N, eixo_fio, _ = melhor
    # melhor ainda: a direção dos fios lida na própria textura (cada penteado desenha os fios de um jeito,
    # às vezes irradiando do topo); onde a textura não diz nada, fica a do eixo do UV
    fluxo_tex = _fluxo_da_textura(guia, V, T, UV, saindo)
    if fluxo_tex is not None:
        Bt, coer, opaco = fluxo_tex
        # a textura só manda onde é nítida (fios bem desenhados) ou onde concorda com o eixo do UV;
        # em mancha, brilho ou borda (coroa do long01) fica o eixo
        concorda = np.abs(np.sum(Bt * B, axis=1)) > 0.65
        usa = opaco & ((coer > 0.55) | (concorda & (coer > 0.25)))
        B = np.where(usa[:, None], Bt, B)
        B = _suavizar_fluxo(B, T, saindo)
    if direcao in ("para_tras", "para_frente"):
        # penteado pedido: o fio segue o rumo penteado deitado na superfície; o UV/textura do pacote só
        # dá a variação (sozinhos, viravam fios cruzando em zigue-zague, "rabiscados")
        Nf = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-12)
        proj = saindo - Nf * np.sum(saindo * Nf, axis=1, keepdims=True)
        proj /= np.maximum(np.linalg.norm(proj, axis=1, keepdims=True), 1e-9)
        B = proj * 0.75 + B * 0.25
        B /= np.maximum(np.linalg.norm(B, axis=1, keepdims=True), 1e-9)
        B = _suavizar_fluxo(B, T, saindo, passes=6)
    bvh = BVHTree.FromPolygons(V.tolist(), T.tolist())
    area = np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1) / 2
    passo = 0.012
    img_cor, img_dados, img_normal = atlas_de_mechas(cor, res_atlas, grisalho=grisalho)
    verts, faces, uvs, tons = [], [], [], []
    comprimentos = []

    def seguir(p, sentido, maximo):
        pts = [p]
        antes = None
        for _ in range(maximo):
            loc, _n, f, _d = bvh.find_nearest(Vector(pts[-1]))
            if f is None:
                break
            if antes is not None and float(B[f] @ B[antes]) < 0.6:
                break  # costura do UV (a risca): a direção dos fios vira de repente
            antes = f
            prox = np.array(loc) + B[f] * passo * sentido
            loc2, _n2, f2, d2 = bvh.find_nearest(Vector(prox))
            if f2 is None or d2 > passo * 0.8:
                break  # saiu pela borda da malha (raiz ou ponta)
            if np.linalg.norm(np.array(loc2) - pts[-1]) < passo * 0.3:
                break  # parou (redemoinho no UV)
            pts.append(np.array(loc2))
        return pts

    # triângulos na costura do UV (vizinho com o fio para outro lado) não semeiam mecha
    from collections import defaultdict

    por_aresta = defaultdict(list)
    for i_t, (a_, b_, c_) in enumerate(T):
        for e in ((a_, b_), (b_, c_), (c_, a_)):
            por_aresta[(min(e), max(e))].append(i_t)
    costura = np.zeros(len(T), bool)
    for lista in por_aresta.values():
        if len(lista) == 2 and float(B[lista[0]] @ B[lista[1]]) < 0.6:
            costura[lista] = True
    peso = area * ~costura
    escolhidos = rng.choice(len(T), size=n_cards, p=peso / peso.sum())

    def ponto_no(f):
        a, b = rng.random(2)
        if a + b > 1:
            a, b = 1 - a, 1 - b
        return V[T[f, 0]] + (V[T[f, 1]] - V[T[f, 0]]) * a + (V[T[f, 2]] - V[T[f, 0]]) * b

    def linha_por(f):
        p = ponto_no(f)
        return np.array(seguir(p, -1.0, 80)[::-1] + seguir(p, 1.0, 120)[1:])

    # mechas: linhas-guia de grupos de fios; os cards de cada grupo se juntam a ela rumo à ponta (vão
    # escuro entre as mechas, em vez de uma folha lisa de fios grudados)
    from mathutils.kdtree import KDTree

    mechas = [m for m in (linha_por(f) for f in rng.choice(len(T), size=max(12, n_cards // 6), p=peso / peso.sum())) if len(m) >= 4]
    kd_m = KDTree(sum(len(m) for m in mechas) or 1)
    quem = []
    for mi, m in enumerate(mechas):
        for j, q in enumerate(m):
            kd_m.insert(Vector(q), len(quem))
            quem.append((mi, j))
    kd_m.balance()
    fases = rng.uniform(0, 2 * np.pi, max(len(mechas), 1))
    usadas = {}
    deslocamentos = []
    for k, f in enumerate(escolhidos):
        linha = linha_por(f)
        if len(linha) < 4:
            continue
        # camada: a maioria rente à malha, algumas por fora (volume e quebra da silhueta); ~7% são fios
        # soltos: finos, ralos, saindo um pouco da forma no meio do caminho (o contorno não fica liso)
        solto = rng.random() < 0.04 + 0.12 * friz
        camada = 0.0015
        # profundidade da mecha no volume (0 = funda, 1 = por fora): um terço forma a camada de dentro,
        # densa, larga e pouco agrupada (cobre a malha-guia: sem vão liso entre as mechas de fora)
        interna = rng.random() < 0.35
        k_cam = rng.uniform(0.03, 0.18) if interna else rng.uniform(0.3, 1.0)
        larg = rng.uniform(0.010, 0.022) * (1.0 - 0.3 * k_cam) * (1.5 if interna else 1.0)
        var = int(rng.integers(0, VARIANTES)) if k_cam > 0.4 else int(rng.integers(0, 4))
        if solto:
            larg = rng.uniform(0.003, 0.006)
            var = VARIANTES - 1
            corte = int(len(linha) * rng.uniform(0.2, 0.5))
            linha = linha[corte:]
            if len(linha) < 4:
                continue
        # as de dentro mais escuras (sombra das de fora), cada mecha com o seu tom
        tom = float(np.clip(rng.normal(1.0, 0.07), 0.82, 1.15)) * (0.7 + 0.3 * k_cam)
        giro = rng.uniform(-0.25, 0.25)
        comp = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(linha, axis=0), axis=1))])
        total = max(comp[-1], 1e-6)
        comprimentos.append(total)
        sfr = comp / total
        alcance_v = float(np.clip(total / 0.45, 0.35, 1.0))  # quanto do fio do atlas a mecha usa
        nrms, lados_ = [], []
        for q in linha:
            _l, nrm, f_, _d = bvh.find_nearest(Vector(q))
            n_ = np.array(nrm) if nrm is not None else np.array([0, 0, 1.0])
            t_ = B[f_] if f_ is not None else np.array([0, 0, -1.0])
            lado = np.cross(n_, t_)
            nrms.append(n_)
            lados_.append(lado / max(np.linalg.norm(lado), 1e-9))
        nrms, lados_ = np.array(nrms), np.array(lados_)
        pos = linha.copy()
        fase = rng.uniform(0, 2 * np.pi)
        if mechas and agr > 0:
            _co, ii, dist = kd_m.find(Vector(linha[0]))
            if dist < 0.03:
                mi, j0 = quem[ii]
                alvo = mechas[mi][np.clip(j0 + np.arange(len(linha)), 0, len(mechas[mi]) - 1)]
                puxa = (agr * (0.3 if interna else 1.0) * sfr ** 1.3)[:, None]
                pos = pos * (1 - puxa) + alvo * puxa
                fase = fases[mi]
                usadas[mi] = usadas.get(mi, 0) + 1
        # onda comum à mecha (o grupo ondula junto)
        lam = float(np.clip(total * 0.35, 0.03, 0.09))
        pos += lados_ * (ond * 0.01 * np.sin(2 * np.pi * comp / lam + fase))[:, None]
        # volume: a raiz sobe do couro e o fio vai deitando para a ponta
        lift = vol * k_cam * (1 - np.exp(-comp / 0.025)) * (1 - 0.55 * sfr)
        if solto:
            lift = lift + 0.012 * sfr ** 1.5
        pos += nrms * (camada + lift)[:, None]
        deslocamentos.extend((camada + lift).tolist())
        # frizz: as pontas se desarrumam (passeio aleatório suave, mais forte na ponta)
        if friz > 0:
            rw = np.cumsum(rng.normal(0, 1, (len(linha), 2)), axis=0) / np.sqrt(np.arange(1, len(linha) + 1))[:, None]
            a_ = friz * 0.004 * sfr ** 1.5 * min(1.0, total / 0.3)
            pos += lados_ * (rw[:, 0] * a_)[:, None] + nrms * (np.abs(rw[:, 1]) * a_)[:, None]
        base = len(verts)
        for i in range(len(linha)):
            n_ = nrms[i]
            lado = lados_[i] * np.cos(giro) + n_ * np.sin(giro)  # leve torção: a mecha não é uma fita chapada
            s = sfr[i]
            # a raiz nasce fina (na risca as mechas dos dois lados não se cruzam) e a ponta afina
            w = larg * min(1.0, 0.25 + s * 12.0) * (1.0 - 0.65 * s ** 1.5) / 2
            centro = pos[i]
            verts.append(centro - lado * w)
            verts.append(centro + lado * w)
            u0, u1 = var / VARIANTES + 0.01, (var + 1) / VARIANTES - 0.01
            uvs.append((u0, 1.0 - s * alcance_v))
            uvs.append((u1, 1.0 - s * alcance_v))
            tons.extend((tom, tom))
            if i:
                j = base + 2 * i
                faces.append((j - 2, j - 1, j + 1, j))
    if not faces:
        return []
    malha = bpy.data.meshes.new(f"{nome}_hair_cards")
    malha.from_pydata([tuple(v) for v in verts], [], faces)
    uv = malha.uv_layers.new(name="UVMap")
    lv = np.empty(len(malha.loops), dtype=np.int64)
    malha.loops.foreach_get("vertex_index", lv)
    uv.data.foreach_set("uv", np.array(uvs, dtype=np.float32)[lv].ravel())
    for p_ in malha.polygons:
        p_.use_smooth = True
    cards = bpy.data.objects.new(malha.name, malha)
    bpy.context.scene.collection.objects.link(cards)
    malha.materials.append(material_cards(f"{nome}_cabelo_cards", img_cor, img_dados, img_normal))
    # tom de cada mecha (cor de vértice): mechas iguais lado a lado é o que mais parece plástico
    ca = malha.color_attributes.new("Col", "BYTE_COLOR", "POINT")
    ca.data.foreach_set("color", np.array([(t, t * 0.99, t * 0.97, 1.0) for t in tons], dtype=np.float32).ravel())
    # a malha do pacote vira a camada de baixo: mais escura, na cor do cabelo e mais densa. Gravado na
    # própria imagem (o glTF não leva nós de multiplicar: na engine ela chegava laranja e rala)
    _escurecer_camada_de_baixo(guia, cor)
    # pesos da malha-guia (o comprido segue pescoço e costas como o cabelo do pacote)
    if guia.vertex_groups:
        limpar_pesos_cabelo(guia)
        gv = {g.index: g.name for g in guia.vertex_groups}
        pesos_guia = [{gv[e.group]: e.weight for e in v.groups if e.weight > 1e-3} for v in me.vertices]
        from mathutils.kdtree import KDTree

        kd = KDTree(len(V))
        for i, p in enumerate(V):
            kd.insert(Vector(p), i)
        kd.balance()
        grupos = {}
        for i, q in enumerate(verts):
            perto = kd.find_n(Vector(q), 3)
            soma = {}
            tot = 0.0
            for _co, j, d in perto:
                w = 1.0 / max(d, 1e-4)
                tot += w
                for nome_g, peso in pesos_guia[j].items():
                    soma[nome_g] = soma.get(nome_g, 0.0) + peso * w
            for nome_g, peso in soma.items():
                grupos.setdefault(nome_g, []).append((i, peso / tot))
        for nome_g, lista in grupos.items():
            g = cards.vertex_groups.new(name=nome_g)
            for i, peso in lista:
                g.add([i], peso, "REPLACE")
    elif arm is not None:
        g = cards.vertex_groups.new(name="head")
        g.add(list(range(len(cards.data.vertices))), 1.0, "REPLACE")
    if arm is not None:
        mod = cards.modifiers.new("esqueleto", "ARMATURE")
        mod.object = arm
        cards.parent = arm
        cards.matrix_parent_inverse = arm.matrix_world.inverted()
    # medidas: quanto do cabelo entra no corpo (ninguém quer fio atravessando o pescoço)
    est["direcao"] = direcao
    cards["medidas_cabelo"] = {"cards": len(comprimentos), "triangulos": 2 * len(faces),
                               "mechas": int(sum(1 for v in usadas.values() if v >= 3)),
                               "descola_do_penteado_cm": round(float(np.mean(deslocamentos)) * 100, 2) if deslocamentos else 0.0,
                               "estilo": est,
                               "comprimento_medio_cm": round(float(np.mean(comprimentos)) * 100, 1) if comprimentos else 0.0}
    return [cards]


# ---------------- barba em cards ----------------

ESTILO_BARBA = {"comprimento_cm": 1.8, "densidade": 1.0, "ondulacao": 1.0, "volume": 1.0}


def _suavizar_nos_vizinhos(valor, T, passes=4):
    viz = [[] for _ in range(len(valor))]
    for a, b, c_ in T:
        viz[a] += (b, c_)
        viz[b] += (a, c_)
        viz[c_] += (a, b)
    idx = [np.unique(v) if v else np.array([i]) for i, v in enumerate(viz)]
    for _ in range(passes):
        valor = np.array([0.5 * valor[i] + 0.5 * valor[j].mean() for i, j in enumerate(idx)])
    return valor


def barba_em_cards(nome, corpo, pontos, cabeca_peso, cor, arm, tipo="cheia", semente=17, grisalho=0.0, res_atlas=2048, estilo=None):
    """Barba de verdade: fio curto, grosso e ondulado (atlas próprio), cards pequenos e densos em camadas,
    plantados na pele do queixo, mandíbula, bochecha baixa (linha diagonal da barba), bigode e costeleta,
    rareando na borda (máscara suavizada na pele) e crescendo em redemoinhos (não tudo reto para baixo).
    Abaixo da boca segue o osso do queixo (acompanha a fala). Controles em ESTILO_BARBA."""
    est = dict(ESTILO_BARBA)
    if tipo == "curta":
        est["comprimento_cm"] = 0.7
    est.update({k: float(v) for k, v in (estilo or {}).items() if k in est})
    rng = np.random.default_rng(semente)
    me = corpo.data
    me.calc_loop_triangles()
    co = np.array([v.co[:] for v in me.vertices])
    T = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.int64)
    s = pontos["s"]
    oz, nz, bz = pontos["olho_z"], pontos["nariz"][2], pontos["boca"][2]
    qz, ny, mb = pontos["queixo"][2], pontos["nariz"][1], pontos["meia_boca"]
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    ax = np.abs(x)
    frente = y < ny + 0.085 * s
    linha = np.where(ax < mb * 1.15, nz - 0.006 * s, bz + 0.012 * s + (ax - mb) * 0.55)
    rosto = frente & (z < linha) & (z > qz - 0.05 * s)
    bigode = (ax < mb * 1.3) & (z > bz + 0.006 * s) & (z < nz - 0.006 * s) & frente
    labios = (ax < mb * 1.1) & (np.abs(z - bz) < 0.0085 * s) & (y < ny + 0.03 * s)
    costeleta = (ax > 0.055 * s) & (z < oz - 0.004 * s) & (z > bz - 0.01 * s) & (y > ny + 0.05 * s) & (y < ny + 0.1 * s)
    pescoco = (z < qz) & (z > qz - 0.06 * s) & (y < pontos["queixo"][1] + 0.05 * s)
    zona = (((rosto | bigode | costeleta) & ~labios & (cabeca_peso > 0.3)) | (pescoco & (cabeca_peso > 0.05))).astype(float)
    if tipo == "curta":
        zona *= ~(pescoco & (z < qz - 0.03 * s))
    # borda suave: a barba rareia na bochecha e no pescoço em vez de acabar numa linha
    mascara = np.clip(_suavizar_nos_vizinhos(zona, T, 5) * 1.6 - 0.25, 0, 1) * (~labios)
    tri = T[(mascara[T] > 0.05).all(axis=1)]
    if not len(tri):
        return []
    p0, p1, p2 = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0)
    area = np.linalg.norm(cr, axis=1) / 2
    nrm_t = cr / np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-12)
    m_tri = mascara[tri].mean(axis=1)
    peso = area * m_tri ** 1.5
    n_cards = int(peso.sum() * 1e4 * 26.0 * est["densidade"])
    escolhidos = rng.choice(len(tri), size=max(n_cards, 1), p=peso / peso.sum())
    # fio de barba: menos fios por card, mais grossos e bem mais ondulados que os do cabelo
    img_cor, img_dados, img_normal = atlas_de_mechas(cor, res_atlas, semente=semente, grisalho=grisalho, fios=(110, 30),
                                                     espessura=1.3, onda=1.0 + 2.0 * est["ondulacao"])
    verts, faces, uvs, tons, jaw = [], [], [], [], []
    fase_r = rng.uniform(0, 2 * np.pi, 3)
    for f in escolhidos:
        a, b = rng.random(2)
        if a + b > 1:
            a, b = 1 - a, 1 - b
        p = p0[f] + (p1[f] - p0[f]) * a + (p2[f] - p0[f]) * b
        n_ = nrm_t[f]
        g = np.array([0.0, 0.0, -1.0])
        d = g - n_ * (n_ @ g)
        if np.linalg.norm(d) < 0.25:  # embaixo do queixo: para a frente e para baixo
            d = np.array([0.0, -1.0, -0.3]) - n_ * (n_ @ np.array([0.0, -1.0, -0.3]))
        no_bigode = abs(p[0]) < mb * 1.3 and bz + 0.004 * s < p[2] < nz
        if no_bigode:
            d = d + np.array([np.sign(p[0]) * 0.9, 0.0, 0.0])
        d /= max(np.linalg.norm(d), 1e-9)
        # redemoinho: gira a direção em volta da normal por um campo suave (+ um pouco de acaso)
        ang = 0.45 * np.sin(p[0] * 90 + fase_r[0]) * np.cos(p[2] * 70 + fase_r[1]) + rng.normal(0, 0.15)
        lado0 = np.cross(n_, d)
        d = d * np.cos(ang) + lado0 * np.sin(ang)
        borda = float(np.clip(m_tri[f], 0, 1))
        camada = rng.choice([0.4, 0.7, 1.0], p=[0.45, 0.35, 0.2])  # baixo curto e denso, meio, por cima
        # na borda (bochecha, pescoço) o fio é bem mais curto: a barba rareia em vez de espetar para fora
        comp = est["comprimento_cm"] / 100 * rng.uniform(0.7, 1.25) * camada * (0.3 + 0.7 * borda ** 1.5) * s
        if not no_bigode and p[2] < bz - 0.01 * s:
            comp *= 1.0 + 0.5 * np.exp(-(p[0] / (0.022 * s)) ** 2)  # mais comprida no queixo
        if no_bigode:
            comp = min(comp, 0.012 * s)
        larg = rng.uniform(0.0016, 0.003) * s * (0.8 + 0.4 * camada)
        var = int(rng.integers(0, VARIANTES))
        tom = float(np.clip(rng.normal(1.0, 0.1), 0.75, 1.2)) * (0.75 + 0.25 * camada)
        pts = [p + n_ * 0.0003]
        sai = 0.08 + 0.18 * camada * est["volume"] * borda  # quanto o fio sai da pele (volume; deitado na borda)
        dirr = d * (1 - sai) + n_ * sai
        curva = np.cross(n_, d) * rng.uniform(-0.3, 0.3) * est["ondulacao"]
        for k in range(4):
            dirr = dirr + d * 0.2 - n_ * 0.05 + curva
            dirr /= np.linalg.norm(dirr)
            pts.append(pts[-1] + dirr * comp / 4)
        lado = np.cross(n_, d)
        lado /= max(np.linalg.norm(lado), 1e-9)
        lado = lado * np.cos(rng.uniform(-0.5, 0.5)) + n_ * np.sin(rng.uniform(-0.35, 0.35))
        peso_jaw = float(np.clip((bz - 0.004 * s - p[2]) / (0.012 * s), 0.0, 1.0))
        base = len(verts)
        for i, q in enumerate(pts):
            t = i / 4
            # raiz estreita (sai de um ponto da pele) e ponta afinando: sem a "lasca" de borda reta que fazia
            # a barba parecer palha colada
            w = larg * min(1.0, 0.3 + 2.8 * t) * (1.0 - 0.8 * t) / 2
            verts += [q - lado * w, q + lado * w]
            u0, u1 = var / VARIANTES + 0.01, (var + 1) / VARIANTES - 0.01
            uvs += [(u0, 1.0 - 0.92 * t), (u1, 1.0 - 0.92 * t)]  # quase o fio todo: as pontas terminam soltas
            tons += [tom, tom]
            jaw += [peso_jaw, peso_jaw]
            if i:
                j = base + 2 * i
                faces.append((j - 2, j - 1, j + 1, j))
    malha = bpy.data.meshes.new(f"{nome}_barba")
    malha.from_pydata([tuple(v) for v in verts], [], faces)
    uv = malha.uv_layers.new(name="UVMap")
    lv = np.empty(len(malha.loops), dtype=np.int64)
    malha.loops.foreach_get("vertex_index", lv)
    uv.data.foreach_set("uv", np.array(uvs, dtype=np.float32)[lv].ravel())
    for p_ in malha.polygons:
        p_.use_smooth = True
    ca = malha.color_attributes.new("Col", "BYTE_COLOR", "POINT")
    ca.data.foreach_set("color", np.array([(t, t * 0.99, t * 0.97, 1.0) for t in tons], dtype=np.float32).ravel())
    malha.materials.append(material_cards(f"{nome}_barba_cabelo_cards", img_cor, img_dados, img_normal))
    o = bpy.data.objects.new(malha.name, malha)
    bpy.context.scene.collection.objects.link(o)
    o.matrix_world = corpo.matrix_world
    if arm is not None:
        tem_jaw = "jaw" in arm.data.bones
        gh = o.vertex_groups.new(name="head")
        gj = o.vertex_groups.new(name="jaw") if tem_jaw else None
        for i, wj in enumerate(jaw):
            wj = wj if tem_jaw else 0.0
            if wj < 1.0:
                gh.add([i], 1.0 - wj, "REPLACE")
            if wj > 0.0 and gj is not None:
                gj.add([i], wj, "REPLACE")
        mod = o.modifiers.new("esqueleto", "ARMATURE")
        mod.object = arm
        o.parent = arm
        o.matrix_parent_inverse = arm.matrix_world.inverted()
    o["medidas_barba"] = {"cards": len(faces) // 4, "triangulos": 2 * len(faces), "tipo": tipo, "estilo": est,
                          "area_cm2": round(float(area[m_tri > 0.5].sum()) * 1e4, 1)}
    return [o]
