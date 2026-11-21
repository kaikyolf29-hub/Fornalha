# Fornalha: pele em alta resolução para o humano realista (etapa 1 do plano por etapas: rosto).
# Tudo é calculado por texel no espaço da textura (UV) do corpo, sem IA e sem placa de vídeo:
#   - cada texel recebe a sua posição 3D (rasterização dos triângulos no UV);
#   - pontos do rosto (olhos, nariz, boca, queixo) saem da própria malha e dos acessórios;
#   - relevo: poros, microtextura cruzada e rugas por idade (testa, entre as sobrancelhas, pés de
#     galinha, olheiras, bigode chinês, marionete, lábios e pescoço);
#   - cor: vermelhidão (bochechas, nariz, orelhas, lábios), barba rala, manchas da idade e sombra nos
#     sulcos; rugosidade: zona T oleosa, lábios, poros e sulcos;
#   - o relevo vira mapa normal (espaço tangente, padrão OpenGL/glTF).
# As três imagens vão empacotadas no glb: a engine recebe a mesma pele do render.
import math

import bpy
import numpy as np


def _caixa(a, r, eixo):
    """Média móvel (caixa) de raio r ao longo de um eixo, com a borda repetida."""
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[eixo] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    cs = np.cumsum(p, axis=eixo, dtype=np.float64)
    n = a.shape[eixo]
    hi = [slice(None)] * a.ndim
    lo = [slice(None)] * a.ndim
    hi[eixo] = slice(2 * r + 1, 2 * r + 1 + n)
    lo[eixo] = slice(0, n)
    return ((cs[tuple(hi)] - cs[tuple(lo)]) / (2 * r + 1)).astype(np.float32)


def borrar(a, rx, ry=None, passes=3):
    """Borrado quase gaussiano (3 caixas). rx no eixo das colunas, ry no das linhas."""
    ry = rx if ry is None else ry
    for _ in range(passes):
        a = _caixa(a, int(rx), 1)
        a = _caixa(a, int(ry), 0)
    return a


def _normalizar(a):
    a = a - a.mean()
    return a / (a.std() + 1e-8)


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sulco(d, w):
    return np.exp(-((d / w) ** 2))


# ------------------------------------------------------------------ rasterização no UV

def rasterizar(obj, res):
    """Para cada texel: posição 3D (espaço do objeto), máscara e tamanho do texel em metros."""
    m = obj.data
    m.calc_loop_triangles()
    nt = len(m.loop_triangles)
    loops = np.empty(nt * 3, dtype=np.int64)
    m.loop_triangles.foreach_get("loops", loops)
    vs = np.empty(nt * 3, dtype=np.int64)
    m.loop_triangles.foreach_get("vertices", vs)
    uvl = m.uv_layers.active.data
    uv = np.empty(len(uvl) * 2, dtype=np.float64)
    uvl.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[loops].reshape(-1, 3, 2)
    co = np.empty(len(m.vertices) * 3, dtype=np.float64)
    m.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)[vs].reshape(-1, 3, 3)
    pos = np.zeros((res, res, 3), dtype=np.float32)
    mask = np.zeros((res, res), dtype=bool)
    escala = np.zeros((res, res), dtype=np.float32)
    P = np.stack([uv[..., 0] * res, (1.0 - uv[..., 1]) * res], -1)
    for t in range(nt):
        (x0, y0), (x1, y1), (x2, y2) = P[t]
        xa, xb = max(int(math.floor(min(x0, x1, x2))), 0), min(int(math.ceil(max(x0, x1, x2))), res - 1)
        ya, yb = max(int(math.floor(min(y0, y1, y2))), 0), min(int(math.ceil(max(y0, y1, y2))), res - 1)
        if xb < xa or yb < ya:
            continue
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-10:
            continue
        xs, ys = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
        l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / d
        l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / d
        l2 = 1.0 - l0 - l1
        dentro = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not dentro.any():
            continue
        c0, c1, c2 = co[t]
        p = l0[..., None] * c0 + l1[..., None] * c1 + l2[..., None] * c2
        area3 = np.linalg.norm(np.cross(c1 - c0, c2 - c0)) / 2
        esc = math.sqrt(area3 / (abs(d) / 2)) if area3 > 0 else 0.0
        sub_pos = pos[ya:yb + 1, xa:xb + 1]
        sub_pos[dentro] = p[dentro]
        mask[ya:yb + 1, xa:xb + 1] |= dentro
        sub_esc = escala[ya:yb + 1, xa:xb + 1]
        sub_esc[dentro] = esc
    return pos, mask, escala


def dilatar(img, mask, passos=6):
    """Espalha a cor para fora das ilhas do UV (sem costura escura no mipmap)."""
    img = img.copy()
    m = mask.astype(np.float32)
    for _ in range(passos):
        soma = np.zeros_like(img)
        cont = np.zeros_like(m)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            soma += np.roll(np.roll(img * m[..., None] if img.ndim == 3 else img * m, dy, 0), dx, 1)
            cont += np.roll(np.roll(m, dy, 0), dx, 1)
        novo = cont > 0
        livre = (m == 0) & novo
        if img.ndim == 3:
            img[livre] = soma[livre] / cont[livre][:, None]
        else:
            img[livre] = soma[livre] / cont[livre]
        m = np.where(livre, 1.0, m)
    return img


# ------------------------------------------------------------------ pontos do rosto

def pontos_do_rosto(corpo, olhos=None, dentes=None):
    """Olhos, ponta do nariz, boca e queixo no espaço do objeto do corpo."""
    co = np.array([v.co[:] for v in corpo.data.vertices])
    if olhos is not None and len(olhos.data.vertices):
        mw = corpo.matrix_world.inverted() @ olhos.matrix_world
        e = np.array([(mw @ v.co)[:] for v in olhos.data.vertices])
        ol = e[e[:, 0] > 0].mean(0)
        orr = e[e[:, 0] <= 0].mean(0)
    else:
        topo = co[:, 2].max()
        cab = co[co[:, 2] > topo - 0.25]
        z = topo - 0.12
        y = cab[:, 1].min() + 0.03
        ol, orr = np.array([0.032, y, z]), np.array([-0.032, y, z])
    olho_z = (ol[2] + orr[2]) / 2
    s = max(abs(ol[0] - orr[0]) / 0.064, 0.6)
    perto = co[(np.abs(co[:, 0]) < 0.008 * s) & (co[:, 2] < olho_z) & (co[:, 2] > olho_z - 0.07 * s)]
    nariz = perto[np.argmin(perto[:, 1])] if len(perto) else np.array([0, ol[1] - 0.02, olho_z - 0.045 * s])
    if dentes is not None and len(dentes.data.vertices):
        mw = corpo.matrix_world.inverted() @ dentes.matrix_world
        d = np.array([(mw @ v.co)[:] for v in dentes.data.vertices])
        boca = np.array([0.0, d[:, 1].min() - 0.004 * s, (d[:, 2].min() + d[:, 2].max()) / 2])
        meia_boca = max((d[:, 0].max() - d[:, 0].min()) * 0.55, 0.02 * s)
    else:
        boca = np.array([0.0, nariz[1] + 0.012 * s, nariz[2] - 0.03 * s])
        meia_boca = 0.024 * s
    frente = co[(np.abs(co[:, 0]) < 0.01 * s) & (co[:, 2] < boca[2]) & (co[:, 2] > boca[2] - 0.08 * s) & (co[:, 1] < nariz[1] + 0.05 * s)]
    queixo = np.array([0.0, frente[:, 1].min(), frente[:, 2].min()]) if len(frente) else boca - np.array([0, -0.01, 0.045 * s])
    return {"olho_l": ol, "olho_r": orr, "olho_z": olho_z, "s": s, "nariz": nariz, "boca": boca, "meia_boca": meia_boca, "queixo": queixo}


# ------------------------------------------------------------------ a pele

def gerar(corpo, base_img, ficha, olhos=None, dentes=None, res=4096, cor_barba="#2a1e16", semente=7):
    """Devolve (imagem_cor, imagem_rugosidade, imagem_normal) prontas para o material."""
    rng = np.random.default_rng(semente)
    m = ficha.get("macro", {})
    idade = float(m.get("idade", 0.5))
    a = float(np.clip((idade - 0.5) / 0.4, 0.0, 1.0))  # 0 jovem … 1 idoso
    homem = float(m.get("genero", 0.5)) >= 0.5
    barba = ficha.get("barba", "rala" if homem else "nenhuma")
    pos, mask, escala = rasterizar(corpo, res)
    P = pontos_do_rosto(corpo, olhos, dentes)
    s = P["s"]
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    oz = P["olho_z"]
    oy = (P["olho_l"][1] + P["olho_r"][1]) / 2
    odx = abs(P["olho_l"][0])
    nz, ny = P["nariz"][2], P["nariz"][1]
    bz, by, mb = P["boca"][2], P["boca"][1], P["meia_boca"]
    qz = P["queixo"][2]
    topo = float(z[mask].max()) if mask.any() else oz + 0.12
    # máscaras de região (todas suaves)
    cabeca = sstep(qz - 0.06 * s, qz - 0.02 * s, z) * mask
    frente = sstep(oy + 0.06 * s, oy + 0.01 * s, y)
    rosto = cabeca * frente
    labios = sstep(1.0, 0.75, np.hypot(x / (mb * 1.05), (z - bz) / (0.0105 * s))) * rosto
    def bolha(cx, cz, r, so_frente=True):
        g = np.exp(-(((ax - cx) ** 2 + (z - cz) ** 2) / (r * r)))
        return g * (rosto if so_frente else cabeca)
    bochecha = bolha(odx + 0.004 * s, oz - 0.03 * s, 0.022 * s)
    narizm = bolha(0.0, nz + 0.006 * s, 0.014 * s)
    testa = sstep(oz + 0.02 * s, oz + 0.035 * s, z) * sstep(topo - 0.02 * s, topo - 0.06 * s, z) * rosto
    zona_t = np.maximum(testa * sstep(0.05 * s, 0.025 * s, ax), narizm)
    orelha = sstep(0.06 * s, 0.072 * s, ax) * cabeca * sstep(oz + 0.03 * s, oz + 0.01 * s, z) * sstep(oz - 0.05 * s, oz - 0.03 * s, z)
    pescoco = sstep(qz + 0.005 * s, qz - 0.01 * s, z) * sstep(qz - 0.12 * s, qz - 0.08 * s, z) * mask

    # ---------- relevo (metros; negativo = sulco)
    H = np.zeros((res, res), dtype=np.float32)
    ruido = lambda r: _normalizar(borrar(rng.standard_normal((res, res)).astype(np.float32), r))
    # poros: pontinhos afundados, mais fortes no nariz e nas bochechas, nada nos lábios
    px = res / 4096.0
    p = ruido(max(1, round(1.2 * px)))
    poros = np.clip(p - 1.1, 0, None)
    poros /= poros.max() + 1e-6
    dens = 0.35 + 0.45 * rosto + 0.7 * np.maximum(bochecha, narizm) + 0.25 * testa
    dens *= 1.0 - labios
    H -= 0.000055 * poros * dens
    # microtextura cruzada (pele não é lisa nem no jovem)
    h1 = ruido(1)
    l1 = borrar(h1, max(1, round(5 * px)), 0, passes=2)
    l2 = borrar(h1, 0, max(1, round(5 * px)), passes=2)
    micro = -(np.abs(_normalizar(l1)) + np.abs(_normalizar(l2)))
    H += 0.000012 * (1 + 3.0 * a) * micro * mask
    # quebra das linhas (nenhuma ruga é perfeita)
    quebra = 0.55 + 0.45 * np.clip(_normalizar(borrar(rng.standard_normal((res, res)).astype(np.float32), round(18 * px))), -1, 1)
    rugas = np.zeros_like(H)
    # testa: linhas horizontais levemente curvas
    # ondulação de baixa frequência (as linhas da testa sobem, descem e se partem)
    onda = _normalizar(borrar(rng.standard_normal((res, res)).astype(np.float32), round(30 * px)))
    zf = z - (oz + 0.03 * s) - 1.2 * x * x / s + 0.0016 * s * onda
    esp = [0.0042, 0.0125, 0.0205, 0.0292, 0.037]
    linhas = sum((0.6 + 0.4 * ((k * 7919) % 5) / 4.0) * sulco(zf - e * s, (0.0009 + 0.0004 * (k % 2)) * s) for k, e in enumerate(esp))
    rugas += (0.15 + a) * 0.0006 * linhas * testa * sstep(0.055 * s, 0.035 * s, ax)
    # entre as sobrancelhas (duas verticais)
    rugas += a * 0.0006 * sulco(ax - 0.0055 * s, 0.0011 * s) * sstep(oz - 0.002 * s, oz + 0.006 * s, z) * sstep(oz + 0.032 * s, oz + 0.022 * s, z) * rosto
    # pés de galinha: raios no canto de fora de cada olho
    cx = odx + 0.019 * s
    rx, rz = ax - cx, z - (oz - 0.002 * s)
    r = np.hypot(rx, rz)
    th = np.arctan2(rz, np.maximum(rx, 1e-6))
    raios = (0.5 + 0.5 * np.cos(th * 16 + 2.0 * quebra)) ** 8
    rugas += a * 0.0006 * raios * sstep(0.003 * s, 0.007 * s, r) * sstep(0.026 * s, 0.014 * s, r) * (rx > 0) * sstep(1.25, 0.9, np.abs(th)) * cabeca
    # olheiras: arcos embaixo do olho (e a bolsa um pouco estufada)
    ro = np.hypot(ax - odx, z - oz)
    baixo = sstep(oz - 0.002 * s, oz - 0.007 * s, z) * sstep(0.022 * s, 0.014 * s, np.abs(ax - odx)) * rosto
    arcos = (sulco(ro - 0.0125 * s, 0.0012 * s) + 0.9 * a * sulco(ro - 0.0172 * s, 0.0013 * s)
             + 0.7 * a * sulco(ro - 0.0215 * s, 0.0015 * s) + 0.5 * a * sulco(ro - 0.026 * s, 0.0017 * s))
    # rugas finas que descem da olheira (a pele fina do idoso dobra em leque)
    leque = (0.5 + 0.5 * np.cos(np.arctan2(z - oz, ax - odx) * 22 + 2.0 * quebra)) ** 6
    rugas += (0.2 + a) * 0.0008 * arcos * baixo + a * 0.00035 * leque * baixo * sstep(0.012 * s, 0.016 * s, ro)
    H += a * 0.0016 * sstep(0.019 * s, 0.0115 * s, ro) * baixo  # bolsa embaixo do olho
    # bigode chinês (da asa do nariz ao canto da boca) e marionete (do canto da boca para baixo)
    def dist_seg(pa, pb):
        ux, uz = ax - pa[0], z - pa[1]
        vx, vz = pb[0] - pa[0], pb[1] - pa[1]
        t = np.clip((ux * vx + uz * vz) / (vx * vx + vz * vz), 0, 1)
        return np.hypot(ux - t * vx, uz - t * vz), t
    d, t = dist_seg((0.016 * s, nz + 0.004 * s), (mb + 0.006 * s, bz - 0.008 * s))
    rugas += (0.25 + 0.75 * a) * 0.0013 * sulco(d, (0.0018 + 0.0014 * a) * s) * sstep(0, 0.15, t) * rosto
    d, t = dist_seg((mb + 0.002 * s, bz - 0.004 * s), (mb - 0.002 * s, bz - 0.032 * s))
    rugas += a * 0.0009 * sulco(d, 0.0018 * s) * rosto
    # bochecha do idoso: linhas diagonais finas e a pele "crepe" (cruzada mais forte)
    diag = (0.5 + 0.5 * np.cos(((ax - odx) * 0.8 + (z - oz)) / (0.0045 * s) * 2 * np.pi + 2.5 * quebra)) ** 10
    rugas += a * 0.0003 * diag * bochecha * sstep(oz - 0.012 * s, oz - 0.02 * s, z)
    # lábios: risquinhos verticais
    rugas += (0.3 + 0.7 * a) * 0.00008 * (0.5 + 0.5 * np.cos(x / (0.0016 * s) * 2 * np.pi + 3 * quebra)) ** 4 * labios
    # pescoço: dobras horizontais
    rugas += (0.15 + a) * 0.00035 * sum(sulco(z - (qz - (0.03 + 0.022 * k) * s), 0.0016 * s) for k in range(3)) * pescoco * sstep(oy + 0.08 * s, oy + 0.04 * s, y)
    rugas *= quebra
    H -= rugas

    # ---------- cor
    base = _redimensionar(_pixels(base_img), res) if base_img is not None else np.full((res, res, 3), (0.8, 0.62, 0.52), dtype=np.float32)
    if ficha.get("cabelo") in (None, "", "nenhum"):
        couro = cabeca * sstep(oz + 0.045 * s, oz + 0.075 * s, z)
        couro = np.maximum(couro, cabeca * sstep(oy + 0.03 * s, oy + 0.07 * s, y) * sstep(oz - 0.01 * s, oz + 0.02 * s, z))
        liso = borrar(base, round(14 * px))
        base = base * (1 - couro[..., None]) + liso * couro[..., None]
    lin = base ** 2.2
    # pele com menos "plástico": um pouco mais escura e quente, com variação de tom em manchas grandes
    var = _normalizar(borrar(rng.standard_normal((res, res)).astype(np.float32), round(40 * px)))[..., None]
    lum = (lin @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[..., None]
    lin = lum + (lin - lum) * 0.82  # a textura do MakeHuman é saturada (laranja) demais
    lin = lin * (0.88 + 0.05 * var) * np.array([1.0, 0.975, 0.975], dtype=np.float32)
    verm = np.clip(0.55 * bochecha + 0.6 * narizm + 0.45 * orelha + 0.3 * labios, 0, 1)[..., None]
    lin = lin * (1 - 0.45 * verm) + lin * np.array([1.18, 0.86, 0.84], dtype=np.float32) * 0.45 * verm
    sulcos = np.clip(rugas / 0.0008, 0, 1)[..., None]
    lin *= 1 - 0.35 * sulcos
    # pálpebra e olheira mais escuras e arroxeadas (dá profundidade ao olhar)
    olheira = np.clip(sstep(0.024 * s, 0.01 * s, ro) * rosto * sstep(oz + 0.012 * s, oz + 0.004 * s, z), 0, 1)[..., None]
    lin = lin * (1 - (0.25 + 0.2 * a) * olheira) + lin * np.array([0.85, 0.72, 0.78], dtype=np.float32) * (0.25 + 0.2 * a) * olheira
    lin *= (1 - 0.1 * poros * dens)[..., None]
    if barba != "nenhuma" and homem:
        zona = rosto * sstep(nz - 0.004 * s, nz - 0.012 * s, z) * (1 - labios)
        zona = np.maximum(zona, cabeca * sstep(qz + 0.002 * s, qz - 0.03 * s, z) * sstep(qz - 0.06 * s, qz - 0.035 * s, z))
        # sobe pela lateral até a costeleta
        lateral = cabeca * sstep(0.045 * s, 0.06 * s, ax) * sstep(oz + 0.005 * s, oz - 0.01 * s, z) * sstep(qz - 0.01 * s, qz + 0.01 * s, z)
        zona = np.clip(np.maximum(zona, lateral) * (1 - 0.8 * bochecha * sstep(nz - 0.01 * s, nz + 0.01 * s, z)), 0, 1)
        # fios curtinhos e densos (pontos finos), mais escuros onde a barba é mais cerrada
        fios = np.clip(ruido(1) - 0.05, 0, None)
        fios = np.clip(fios / (np.percentile(fios, 99) + 1e-6), 0, 1)
        cb = np.array([int(cor_barba.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32) ** 2.2
        k = (0.85 if barba == "cheia" else 0.6) * zona[..., None]
        lin = lin * (1 - 0.32 * k) + np.array([0.08, 0.08, 0.09], dtype=np.float32) * 0.32 * k  # sombra azulada da barba feita
        lin = lin * (1 - fios[..., None] * k) + cb * fios[..., None] * k
        H -= 0.000015 * fios * zona
    if a > 0.4:
        manchas = np.clip(_normalizar(borrar(rng.standard_normal((res, res)).astype(np.float32), round(10 * px))) - 1.6, 0, None)
        manchas = np.clip(manchas * 2, 0, 1)[..., None] * (a - 0.4) * 1.4 * cabeca[..., None]
        lin = lin * (1 - 0.35 * manchas) + lin * np.array([0.8, 0.62, 0.48], dtype=np.float32) * 0.35 * manchas
    cor = np.clip(lin, 0, 1) ** (1 / 2.2)

    # ---------- rugosidade
    rug = 0.5 - 0.14 * zona_t - 0.16 * labios + 0.1 * poros * dens + 0.12 * np.clip(rugas / 0.0006, 0, 1) + 0.06 * (1 - cabeca)
    rug = np.clip(rug, 0.2, 0.9).astype(np.float32)

    # ---------- normal a partir do relevo (texel em metros)
    esc = np.where(escala > 0, escala, np.median(escala[mask]) if mask.any() else 1e-4)
    gx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / (2 * esc)
    gy = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / (2 * esc)  # linha cresce para baixo = v diminui
    nxm, nym = -gx, gy
    n = np.stack([nxm, nym, np.ones_like(H)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    nor = n * 0.5 + 0.5

    cor = dilatar(cor, mask)
    rug = dilatar(rug, mask)
    nor = dilatar(nor, mask)
    nome = corpo.name
    return (_imagem(f"{nome}_pele_cor", cor, False), _imagem(f"{nome}_pele_rugosidade", rug, True),
            _imagem(f"{nome}_pele_normal", nor, True))


def _imagem(nome, arr, dados):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(nome, w, h, alpha=False)
    if dados:
        img.colorspace_settings.name = "Non-Color"
    rgba = np.ones((h, w, 4), dtype=np.float32)
    if arr.ndim == 2:
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = arr
    else:
        rgba[..., :3] = arr
    # Blender guarda de baixo para cima
    img.pixels.foreach_set(rgba[::-1].ravel())
    img.pack()
    return img


def aplicar(mat, cor, rug, nor):
    """Troca a pele do material pelas três imagens (o procedural do render sai)."""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for n in list(nt.nodes):
        if n.type in ("TEX_IMAGE", "MIX", "BUMP", "TEX_NOISE", "NORMAL_MAP"):
            nt.nodes.remove(n)
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = cor
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    tr = nt.nodes.new("ShaderNodeTexImage")
    tr.image = rug
    nt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = nor
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.0
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    for k, v in (("Subsurface Weight", 0.35), ("Subsurface Scale", 0.006), ("Specular IOR Level", 0.5), ("Coat Weight", 0.0)):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.36, 0.18)
    mat["pele_alta"] = True


def base_da_pele(mat):
    """A imagem de pele do MakeHuman que o material usa (ou None)."""
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image
    return None


def _pixels(img):
    """Imagem do Blender → array (linhas de cima para baixo, RGB, 0..1, como está no arquivo)."""
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return np.clip(px.reshape(h, w, 4)[::-1, :, :3], 0, 1)


def _redimensionar(arr, res):
    """Bilinear em numpy (o Python do Blender não tem Pillow)."""
    h, w = arr.shape[:2]
    ys = (np.arange(res) + 0.5) * h / res - 0.5
    xs = (np.arange(res) + 0.5) * w / res - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 1)
    y1, x1 = np.clip(y0 + 1, 0, h - 1), np.clip(x0 + 1, 0, w - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None, None]
    fx = np.clip(xs - x0, 0, 1)[None, :, None]
    a = arr[y0][:, x0] * (1 - fx) + arr[y0][:, x1] * fx
    b = arr[y1][:, x0] * (1 - fx) + arr[y1][:, x1] * fx
    return (a * (1 - fy) + b * fy).astype(np.float32)
