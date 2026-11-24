# Fornalha: o centro das partes da malha (braço, perna, cauda, pescoço) por um campo de distância.
# A malha da IA vem partida nas costuras de textura e com normais trocadas, então nem a ligação dos
# vértices nem a normal servem para saber o que é dentro. Aqui a malha vira voxels pela paridade dos
# cruzamentos (raios nos três eixos, voto da maioria), os buracos fechados por dentro são preenchidos
# e cada voxel ganha a distância até a superfície. O centro de um braço é o cume desse campo: o
# rastreio segue o cume, corte por corte, do ombro até a ponta — a manopla encostada na sobreveste
# continua separada dela (dois cumes com um vale no meio), e o antebraço dobrado para a frente sai certo.
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _coords(obj):
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(obj.matrix_world)
    return co @ m[:3, :3].T + m[:3, 3]


class Campo:
    """Voxels de dentro da malha e a distância de cada um até a superfície (em metros)."""

    def __init__(self, obj, passo):
        co = _coords(obj)
        bvh = BVHTree.FromPolygons([Vector(v) for v in co.tolist()], [tuple(p.vertices) for p in obj.data.polygons])
        self.passo = p = float(passo)
        self.mn = co.min(0) - 3 * p
        dims = np.ceil((co.max(0) + 3 * p - self.mn) / p).astype(int)
        self.dims = dims
        dentro = np.zeros(dims, dtype=np.int16)
        valido = np.zeros(dims, dtype=np.int16)
        grande = float(np.linalg.norm(dims * p)) + 1.0
        for eixo in range(3):
            a, b = [k for k in range(3) if k != eixo]
            d = Vector([1.0 if k == eixo else 0.0 for k in range(3)])
            for i in range(dims[a]):
                for j in range(dims[b]):
                    o = [0.0, 0.0, 0.0]
                    o[a] = self.mn[a] + (i + 0.5) * p
                    o[b] = self.mn[b] + (j + 0.5) * p
                    o[eixo] = self.mn[eixo] - p
                    o = Vector(o)
                    ts = []
                    andado = 0.0
                    for _ in range(64):
                        loc, _n, _f, dist = bvh.ray_cast(o, d, grande - andado)
                        if loc is None:
                            break
                        andado += dist
                        # o mesmo ponto acertado duas vezes (aresta entre dois triângulos) não conta
                        if not ts or andado - ts[-1] > 1e-6:
                            ts.append(andado)
                        o = loc + d * 1e-6
                        andado += 1e-6
                    if len(ts) % 2:
                        continue  # coluna furada: não vota
                    idx = [slice(None)] * 3
                    idx[a], idx[b] = i, j
                    col_d = np.zeros(dims[eixo], dtype=np.int16)
                    for t0, t1 in zip(ts[0::2], ts[1::2]):
                        k0 = int(np.ceil((t0 - p) / p - 0.5))
                        k1 = int(np.floor((t1 - p) / p - 0.5))
                        if k1 >= k0:
                            col_d[max(k0, 0):min(k1 + 1, dims[eixo])] = 1
                    dentro[tuple(idx)] += col_d
                    valido[tuple(idx)] += 1
        solido = (2 * dentro > valido) & (valido > 0)
        # o que não é alcançável de fora é dentro (cavidades fechadas, cascas ocas)
        fora = np.zeros(dims, dtype=bool)
        fora[0, :, :] = fora[-1, :, :] = fora[:, 0, :] = fora[:, -1, :] = fora[:, :, 0] = fora[:, :, -1] = True
        fora &= ~solido
        while True:
            novo = _dilatar(fora) & ~solido
            if (novo == fora).all():
                break
            fora = novo
        self.dentro = ~fora
        # distância até a superfície: camadas de erosão (alternando 6 e 26 vizinhos ≈ distância real)
        dist = np.zeros(dims, dtype=np.float32)
        atual = self.dentro.copy()
        k = 0
        while atual.any():
            dist[atual] += 1.0
            atual = _erodir(atual, completo=bool(k % 2))
            k += 1
        self.dist = dist * p

    def valor(self, pts):
        """Distância (metros) nos pontos, pelo voxel mais perto; 0 fora da grade."""
        ijk = np.floor((np.asarray(pts) - self.mn) / self.passo).astype(int)
        ok = np.all((ijk >= 0) & (ijk < self.dims), axis=-1)
        v = np.zeros(ijk.shape[:-1], dtype=np.float32)
        ii = ijk[ok]
        v[ok] = self.dist[ii[:, 0], ii[:, 1], ii[:, 2]]
        return v


def _dilatar(m):
    r = m.copy()
    r[1:] |= m[:-1]
    r[:-1] |= m[1:]
    r[:, 1:] |= m[:, :-1]
    r[:, :-1] |= m[:, 1:]
    r[:, :, 1:] |= m[:, :, :-1]
    r[:, :, :-1] |= m[:, :, 1:]
    return r


def _erodir(m, completo=False):
    r = m.copy()
    if not completo:
        r[1:] &= m[:-1]
        r[:-1] &= m[1:]
        r[:, 1:] &= m[:, :-1]
        r[:, :-1] &= m[:, 1:]
        r[:, :, 1:] &= m[:, :, :-1]
        r[:, :, :-1] &= m[:, :, 1:]
        r[0] = r[-1] = False
        r[:, 0] = r[:, -1] = False
        r[:, :, 0] = r[:, :, -1] = False
        return r
    p = np.pad(m, 1, constant_values=False)
    n0, n1, n2 = m.shape
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx or dy or dz:
                    r &= p[1 + dx:1 + dx + n0, 1 + dy:1 + dy + n1, 1 + dz:1 + dz + n2]
    return r


def _base(u):
    a = np.array([1.0, 0.0, 0.0]) if abs(u[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(u, a)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(u, e1)


def _cumes(campo, centro, u, raio):
    """Máximos locais do campo no corte (plano perpendicular a `u` em `centro`): [(ponto, valor)]."""
    e1, e2 = _base(u)
    h = campo.passo * 0.7
    n = int(np.ceil(raio / h))
    g = np.arange(-n, n + 1) * h
    A, B = np.meshgrid(g, g, indexing="ij")
    pts = centro + A[..., None] * e1 + B[..., None] * e2
    v = campo.valor(pts)
    pad = np.pad(v, 1, constant_values=0.0)
    m = v > 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                m &= v >= pad[1 + dx:1 + dx + v.shape[0], 1 + dy:1 + dy + v.shape[1]]
    out = []
    for i, j in zip(*np.where(m)):
        # o meio do platô (o voxel dá degraus): média dos vizinhos com o mesmo valor
        viz = (np.abs(A - A[i, j]) <= 2 * h) & (np.abs(B - B[i, j]) <= 2 * h) & (v >= v[i, j] - 1e-6)
        out.append((pts[viz].mean(0), float(v[i, j])))
    return out


def seguir_tubo(campo, inicio, u, comp_max, raio_busca, razao=2.2):
    """Segue o cume do campo a partir de `inicio` na direção `u`. Devolve (linha, raio em cada ponto); a
    linha termina na ponta da parte (o último centro mais o raio, na direção em que vinha)."""
    u = np.asarray(u, dtype=float)
    u /= np.linalg.norm(u)
    c = np.asarray(inicio, dtype=float)
    # encaixa o começo no cume mais perto
    cs = _cumes(campo, c, u, raio_busca)
    if not cs:
        return None, None
    c, r = min(cs, key=lambda x: np.linalg.norm(x[0] - c))
    linha = [c]
    raios = [r]
    andado = 0.0
    while andado < comp_max:
        h = max(campo.passo, 0.6 * r)
        prev = c + u * h
        cs = _cumes(campo, prev, u, max(2.5 * r, 3 * campo.passo) + raio_busca * 0.3)
        cs = [(q, v) for q, v in cs if 1.0 / razao < v / max(r, 1e-6) < razao
              and np.linalg.norm(q - prev) < max(1.3 * r, 2.5 * campo.passo)]
        if not cs:
            break
        q, v = min(cs, key=lambda x: np.linalg.norm(x[0] - prev))
        passo = q - c
        if np.linalg.norm(passo) < 1e-9:
            break
        u = 0.6 * u + 0.4 * passo / np.linalg.norm(passo)
        u /= np.linalg.norm(u)
        andado += float(np.linalg.norm(passo))
        c = q
        r = 0.7 * r + 0.3 * v
        linha.append(c)
        raios.append(v)
    linha.append(c + u * r)
    raios.append(r)
    return np.array(linha), np.array(raios)


def reamostrar(seq, passo):
    seg = np.linalg.norm(np.diff(seq, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] < 1e-9:
        return seq[:1]
    alvo = np.append(np.arange(0.0, s[-1], passo), s[-1])
    return np.stack([np.interp(alvo, s, seq[:, j]) for j in range(3)], axis=1)


def alisar(seq, k=3):
    if len(seq) < 3:
        return seq
    pad = np.concatenate([np.repeat(seq[:1], k, 0), seq, np.repeat(seq[-1:], k, 0)])
    lisa = np.array([pad[j:j + 2 * k + 1].mean(0) for j in range(len(seq))])
    lisa[0], lisa[-1] = seq[0], seq[-1]
    return lisa


def no_comprimento(seq, comp):
    """Ponto da linha a `comp` metros do começo (seguindo a linha)."""
    seg = np.linalg.norm(np.diff(seq, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    comp = float(np.clip(comp, 0.0, s[-1]))
    return np.array([np.interp(comp, s, seq[:, j]) for j in range(3)])


def comprimento(seq):
    return float(np.linalg.norm(np.diff(seq, axis=0), axis=1).sum()) if len(seq) > 1 else 0.0


def dobra(seq, de, ate, janela):
    """(comprimento, ângulo em graus) da maior dobra da linha entre `de` e `ate` metros."""
    melhor = (None, 0.0)
    total = comprimento(seq)
    for c in np.arange(max(de, janela), min(ate, total - janela), janela / 4):
        a, b, d = no_comprimento(seq, c - janela), no_comprimento(seq, c), no_comprimento(seq, c + janela)
        u, v = b - a, d - b
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        if nu < 1e-9 or nv < 1e-9:
            continue
        ang = float(np.degrees(np.arccos(np.clip(u @ v / (nu * nv), -1.0, 1.0))))
        if ang > melhor[1]:
            melhor = (float(c), ang)
    return melhor


def braco(campo, H, ombro, inicio, direcao):
    """Juntas do braço pelo cume do campo: segue do braço (logo abaixo do ombro) até a ponta da mão.
    A ponta é onde o tubo afina de vez (o pano pendurado embaixo da mão é fino) ou o comprimento de um
    braço humano, o que vier antes. Cotovelo na dobra quando ela existe (senão, pela proporção); pulso
    pelo antebraço proporcional ao braço medido. None se o tubo não chegou a um braço plausível."""
    tubo, raios = seguir_tubo(campo, inicio, direcao, 0.60 * H, 0.06 * H)
    if tubo is None or len(tubo) < 4:
        return None
    pts = np.vstack([np.asarray(ombro)[None, :], tubo])
    rr = np.concatenate([[raios[0]], raios])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arco = np.concatenate([[0.0], np.cumsum(seg)])
    # espessura do antebraço (entre 0,25 H e 0,38 H do ombro) e onde o tubo fica fino depois dele
    ref = rr[(arco > 0.25 * H) & (arco < 0.38 * H)]
    corte = len(pts)
    if len(ref):
        fino = rr < 0.4 * float(np.median(ref))
        for k in range(len(pts)):
            if arco[k] > 0.33 * H and fino[k:k + 3].all() and len(fino[k:k + 3]) == 3:
                corte = k + 1
                break
    corte = min(corte, int(np.searchsorted(arco, 0.47 * H)) + 1, len(pts))
    pts = pts[:corte]
    seq = reamostrar(alisar(pts), 0.005 * H)
    total = comprimento(seq)
    if total < 0.30 * H:
        return None
    # cotovelo e pulso pelas medidas do corpo humano ao longo do tubo (braço 0,186 H, antebraço
    # 0,146 H); a dobra do tubo só ajusta o cotovelo quando está perto de onde ele deve estar. A mão é o
    # resto até a ponta: punho fechado ou dedos abertos, os dois cabem
    c_prop = 0.186 * H
    c_dobra, ang = dobra(seq, c_prop - 0.05 * H, c_prop + 0.05 * H, 0.04 * H)
    c_cot = c_dobra if (c_dobra is not None and ang > 25.0) else c_prop
    c_pulso = min(c_cot + 0.146 * H, total - 0.045 * H)
    return {"cotovelo": no_comprimento(seq, c_cot), "pulso": no_comprimento(seq, c_pulso),
            "ponta": seq[-1], "comprimento": total, "dobra": ang, "linha": seq}


def rotular(campo, ossos, passo_amostra=None):
    """Divide o volume da malha entre os ossos (divisor de águas pelo campo de distância): cada osso
    começa nos voxels por onde passa e cresce do miolo para a beirada; dois lobos que se encostam (a
    manopla na sobreveste) se separam no vale entre eles, não pela distância em linha reta.
    `ossos`: {nome: (cabeça, cauda)}. Devolve (rótulos por voxel, -1 fora; lista de nomes)."""
    import heapq as hq
    nomes = list(ossos)
    lab = np.full(campo.dims, -1, dtype=np.int16)
    p = campo.passo
    h = passo_amostra or p * 0.5
    H = float(campo.dims[2] * p)
    raio_busca = 0.03 * H
    fila = []
    cont = 0
    sementes = {}
    for k, n in enumerate(nomes):
        a, b = (np.asarray(x, dtype=float) for x in ossos[n])
        comp = float(np.linalg.norm(b - a))
        ts = np.linspace(0.1, 0.9, max(int(comp / h), 2))
        pts = a + ts[:, None] * (b - a)
        ijk = _sementes(campo, pts, raio_busca)
        if not len(ijk):
            # osso fora do volume: o voxel de dentro mais perto do meio dele
            meio = (a + b) / 2
            dd = np.argwhere(campo.dentro)
            if not len(dd):
                continue
            c = campo.mn + (dd + 0.5) * p
            ijk = dd[[int(np.argmin(np.linalg.norm(c - meio, axis=1)))]]
        sementes[n] = len(ijk)
        for i, j, l in ijk:
            if lab[i, j, l] < 0:
                lab[i, j, l] = k
                hq.heappush(fila, (-float(campo.dist[i, j, l]), cont, int(i), int(j), int(l)))
                cont += 1
    viz = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    nx, ny, nz = (int(x) for x in campo.dims)
    dentro = campo.dentro
    dist = campo.dist
    while fila:
        _, _, i, j, l = hq.heappop(fila)
        k = lab[i, j, l]
        for dx, dy, dz in viz:
            a, b, c = i + dx, j + dy, l + dz
            if 0 <= a < nx and 0 <= b < ny and 0 <= c < nz and dentro[a, b, c] and lab[a, b, c] < 0:
                lab[a, b, c] = k
                hq.heappush(fila, (-float(dist[a, b, c]), cont, a, b, c))
                cont += 1
    poucas = [f"{n} {c}" for n, c in sementes.items() if c < 3]
    if poucas:
        print("[eixo] ossos com poucas sementes: " + ", ".join(poucas))
    return lab, nomes


def _sementes(campo, pts, raio):
    """Voxels de dentro por onde o osso passa; a amostra que cai fora do volume (osso raspando na
    beirada de um antebraço fino) pega o voxel de dentro mais central a menos de `raio`."""
    p = campo.passo
    r = max(1, int(np.ceil(raio / p)))
    g = np.arange(-r, r + 1)
    off = np.stack(np.meshgrid(g, g, g, indexing="ij"), axis=-1).reshape(-1, 3)
    off = off[np.linalg.norm(off, axis=1) <= r]
    out = []
    for q in pts:
        b = np.floor((q - campo.mn) / p).astype(int)
        if np.all((b >= 0) & (b < campo.dims)) and campo.dentro[b[0], b[1], b[2]]:
            out.append(b)
            continue
        viz = b + off
        ok = np.all((viz >= 0) & (viz < campo.dims), axis=1)
        viz = viz[ok]
        if not len(viz):
            continue
        d = campo.dist[viz[:, 0], viz[:, 1], viz[:, 2]]
        if d.max() <= 0:
            continue
        out.append(viz[int(np.argmax(d))])
    return np.unique(np.array(out, dtype=int).reshape(-1, 3), axis=0)


def rotulo_dos_vertices(campo, lab, co, alcance=3):
    """Rótulo de cada vértice: o do voxel rotulado mais perto (o vértice fica na casca, o voxel dentro).
    -1 se não há voxel rotulado a menos de `alcance` voxels."""
    p = campo.passo
    base = np.floor((co - campo.mn) / p).astype(int)
    melhor = np.full(len(co), np.inf)
    out = np.full(len(co), -1, dtype=np.int16)
    r = range(-alcance, alcance + 1)
    for dx in r:
        for dy in r:
            for dz in r:
                ijk = base + np.array([dx, dy, dz])
                ok = np.all((ijk >= 0) & (ijk < campo.dims), axis=1)
                lv = np.full(len(co), -1, dtype=np.int16)
                lv[ok] = lab[ijk[ok, 0], ijk[ok, 1], ijk[ok, 2]]
                c = campo.mn + (ijk + 0.5) * p
                d = np.linalg.norm(c - co, axis=1)
                m = (lv >= 0) & (d < melhor)
                melhor[m] = d[m]
                out[m] = lv[m]
    return out


def suave(a, b, x):
    t = np.clip((x - a) / max(b - a, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def na_cadeia(co, juntas, distancia=False):
    """Comprimento ao longo da cadeia de juntas (ombro → cotovelo → pulso → ponta) do ponto da cadeia
    mais perto de cada vértice (e a distância até ele, com `distancia`)."""
    juntas = [np.asarray(j, dtype=float) for j in juntas]
    melhor = np.full(len(co), np.inf)
    arco = np.zeros(len(co))
    acum = 0.0
    for a, b in zip(juntas[:-1], juntas[1:]):
        ab = b - a
        L = float(np.linalg.norm(ab))
        t = np.clip(((co - a) @ ab) / max(L * L, 1e-12), 0.0, 1.0)
        d = np.linalg.norm(co - (a + t[:, None] * ab), axis=1)
        m = d < melhor
        melhor[m] = d[m]
        arco[m] = acum + t[m] * L
        acum += L
    return (arco, melhor) if distancia else arco
