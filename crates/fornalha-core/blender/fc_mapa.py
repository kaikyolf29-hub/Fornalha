# Fornalha: bancada de mapa. A IA escreve o plano do mapa (regiões, relevo, rio, estradas, clima e hora);
# aqui ele vira relevo com erosão, chão pintado por inclinação e altura, vegetação espalhada por regras,
# vila e masmorra de peças, ponte onde a estrada cruza o rio, e as medidas que dizem o que está errado.
# Coordenadas do plano como na engine: x para o leste, z para o sul, em metros a partir do centro.
# Por dentro, a grade tem linha = z e coluna = x; no Blender, y = -z.
import heapq
import json
import math
import os
import random
import time
from collections import deque

import bpy
import numpy as np
from mathutils import Matrix, Vector

import fc_comum as c
import fc_armas
import fc_masmorra
import fc_mundo

# amplitude do ruído e peso das cristas por estilo de relevo
ESTILOS = {"plano": (0.25, 0.0), "colinas": (1.0, 0.15), "montanhoso": (1.5, 0.6), "vale": (0.9, 0.2)}
CLIMAS = ("temperado", "seco", "frio", "neve", "chuvoso")
HORAS = ("amanhecer", "manha", "meio_dia", "tarde", "por_do_sol", "noite")
RAIO_PADRAO = {"vila": 38, "cidade": 50, "aldeia": 30, "floresta": 110, "bosque": 70, "pantano": 60, "campo": 70, "lago": 40,
               "montanha": 80, "colina": 60, "vulcao": 80, "masmorra": 20, "caverna": 18, "castelo": 32, "ruinas": 24,
               "arena": 18, "coliseu": 24}
DURAS = {"vila", "cidade", "aldeia", "masmorra", "caverna", "castelo", "ruinas", "arena", "coliseu", "lago"}
PLANAS = {"vila", "cidade", "aldeia", "arena", "coliseu", "campo"}
ENCOSTA = {"masmorra", "caverna", "ruinas"}
MORRO = {"montanha", "colina", "vulcao"}
MATA = {"floresta": 0.85, "bosque": 0.6, "pantano": 0.3}
KIT = {"vila": "vila", "cidade": "vila", "aldeia": "vila", "masmorra": "masmorra", "caverna": "masmorra", "castelo": "masmorra",
       "ruinas": "masmorra", "arena": "arena", "coliseu": "arena"}
POSICOES = {"centro": (0, 0), "norte": (0, -1), "sul": (0, 1), "leste": (1, 0), "oeste": (-1, 0), "nordeste": (0.75, -0.75),
            "noroeste": (-0.75, -0.75), "sudeste": (0.75, 0.75), "sudoeste": (-0.75, 0.75)}
CORES_CAMADAS = {"grama": "#4c7232", "terra": "#7a6145", "rocha": "#7f7a72", "areia": "#c4b088", "neve": "#e9eef2"}
GRAMA_CLIMA = {"temperado": "#4c7232", "seco": "#8a8546", "frio": "#4f6a45", "neve": "#5d6e55", "chuvoso": "#3f6a2c"}
FOLHA = {"temperado": "#3f6b35", "seco": "#7d7a3c", "frio": "#2f5a3a", "neve": "#2b4d36", "chuvoso": "#355f30"}
# sol (elevação, cor, energia), céu (topo, horizonte) e névoa por hora do dia
LUZ = {
    "amanhecer": (9, "#ffb27a", 1.1, "#4a6a9a", "#f0b48a", "#d9b8a0"),
    "manha": (32, "#fff1dc", 1.5, "#4f7fb8", "#cfd9e0", "#c9d6df"),
    "meio_dia": (64, "#fffaf0", 1.8, "#3d6fb5", "#bcd0e0", "#c4d3df"),
    "tarde": (34, "#ffe2b8", 1.6, "#4a72ad", "#e3cfb4", "#d8cdbd"),
    "por_do_sol": (7, "#ff9a52", 1.3, "#3b4f7a", "#f29a5e", "#d59a78"),
    "noite": (38, "#9db4ff", 0.22, "#050914", "#1a2340", "#141b2c"),
}
NEVOA_CLIMA = {"temperado": 1.0, "seco": 0.6, "frio": 1.2, "neve": 1.4, "chuvoso": 1.7}


def _ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _id(texto):
    s = "".join(ch if ch.isalnum() else "_" for ch in str(texto).lower()).strip("_")
    return s or "regiao"


# ---------------- plano ----------------

def normalizar(plano, areas=None):
    """Completa o plano com padrões e devolve (plano, avisos). Nada inventado fica escondido: vai nos avisos."""
    p = dict(plano or {})
    avisos = []
    L = float(p.get("tamanho_m") or 512)
    if not 128 <= L <= 2048:
        avisos.append(f"tamanho_m {L:g} fora de 128 a 2048: usei {min(max(L, 128), 2048):g}.")
        L = min(max(L, 128.0), 2048.0)
    res = float(p.get("resolucao_m") or (1.0 if L <= 1024 else 2.0))
    if L / res > 1024:
        res = L / 1024
        avisos.append(f"resolução limitada a {res:g} m por ponto (no máximo 1025 × 1025 pontos).")
    relevo = dict(p.get("relevo") or {})
    estilo = str(relevo.get("estilo") or "colinas")
    if estilo not in ESTILOS:
        avisos.append(f"relevo.estilo \"{estilo}\" não existe ({', '.join(ESTILOS)}): usei colinas.")
        estilo = "colinas"
    relevo = {"estilo": estilo, "altura_m": float(min(max(float(relevo.get("altura_m", 40)), 2.0), 400.0)),
              "erosao": float(min(max(float(relevo.get("erosao", 0.6)), 0.0), 1.0))}
    clima = str(p.get("clima") or "temperado")
    if clima not in CLIMAS:
        avisos.append(f"clima \"{clima}\" não existe ({', '.join(CLIMAS)}): usei temperado.")
        clima = "temperado"
    hora = str(p.get("hora") or "tarde")
    if hora not in HORAS:
        avisos.append(f"hora \"{hora}\" não existe ({', '.join(HORAS)}): usei tarde.")
        hora = "tarde"
    brutas = p.get("regioes") or [{"id": a.get("id"), "tipo": a.get("tipo"), "nome": a.get("nome")} for a in (areas or [])]
    if not brutas:
        brutas = [{"id": "vila", "tipo": "vila"}, {"id": "floresta", "tipo": "floresta"}, {"id": "masmorra", "tipo": "masmorra"}]
    regioes, vistos = [], set()
    for i, r in enumerate(brutas):
        tipo = str(r.get("tipo") or "campo").lower()
        if tipo not in RAIO_PADRAO:
            avisos.append(f"região do tipo \"{tipo}\" não existe: virou campo ({', '.join(sorted(RAIO_PADRAO))}).")
            tipo = "campo"
        ident = _id(r.get("id") or tipo)
        while ident in vistos:
            ident += f"_{i}"
        vistos.add(ident)
        raio = float(r.get("raio_m") or r.get("raio") or RAIO_PADRAO[tipo])
        raio = float(min(max(raio, 8.0), L * 0.4))
        centro = None
        if isinstance(r.get("centro"), (list, tuple)) and len(r["centro"]) >= 2:
            centro = [float(r["centro"][0]), float(r["centro"][-1])]
        elif r.get("posicao") in POSICOES:
            dx, dz = POSICOES[r["posicao"]]
            centro = [dx * L * 0.3, dz * L * 0.3]
        regioes.append({"id": ident, "tipo": tipo, "nome": r.get("nome") or ident, "raio_m": raio, "centro": centro})
    ids = [r["id"] for r in regioes]
    spawn = p.get("spawn")
    if spawn not in ids:
        spawn = next((r["id"] for r in regioes if KIT.get(r["tipo"]) == "vila"), ids[0])
    inicio = next(r for r in regioes if r["id"] == spawn)
    if inicio["centro"] is None:
        inicio["centro"] = [0.0, L * 0.05]  # quem começa fica perto do meio do mapa
    _arrumar_regioes(regioes, L, int(p.get("seed", 7)), avisos)
    rio = p.get("rio")
    if rio in (None, False):
        rio = None
    elif rio is True or rio == "auto":
        rio = {"auto": True}
    elif isinstance(rio, dict):
        rio = dict(rio)
    else:
        avisos.append("rio precisa ser true, \"auto\" ou {\"pontos\": [[x, z], ...]}: fiquei sem rio.")
        rio = None
    if rio is not None:
        rio["largura_m"] = float(min(max(float(rio.get("largura_m", 8)), 2.0), 40.0))
        rio["profundidade_m"] = float(min(max(float(rio.get("profundidade_m", 2.0)), 0.5), 8.0))
    estradas = p.get("estradas")
    largura_estrada = float(min(max(float(p.get("largura_estrada_m", 4.0)), 2.0), 12.0))
    if estradas is None:
        estradas = [{"de": spawn, "para": r["id"]} for r in regioes if r["id"] != spawn and r["tipo"] not in ("lago",)]
    lista = []
    for e in estradas or []:
        if e.get("de") in ids and e.get("para") in ids and e["de"] != e["para"]:
            lista.append({"de": e["de"], "para": e["para"]})
        else:
            avisos.append(f"estrada {e} ignorada: \"de\" e \"para\" precisam ser ids de regiões diferentes ({', '.join(ids)}).")
    return {
        "tamanho_m": L, "resolucao_m": res, "seed": int(p.get("seed", 7)), "relevo": relevo, "clima": clima, "hora": hora,
        "nevoa": float(min(max(float(p.get("nevoa", 0.35)), 0.0), 1.0)), "sol_azimute": float(p.get("sol_azimute", 35.0)),
        "regioes": regioes, "rio": rio, "estradas": lista, "largura_estrada_m": largura_estrada, "spawn": spawn,
    }, avisos


def _arrumar_regioes(regioes, L, seed, avisos):
    """Põe no mapa as regiões sem centro e afasta as duras (vila, masmorra, lago...) que se sobrepõem."""
    rnd = random.Random(seed * 31 + 5)
    limite = L / 2 - L * 0.12
    soltas = [r for r in regioes if r["centro"] is None]
    ang0 = rnd.uniform(0, math.tau)
    for i, r in enumerate(soltas):
        ang = ang0 + i * 2.39996  # ângulo de ouro: espalha sem repetir
        dist = L * (0.26 + 0.08 * ((i * 0.618) % 1.0))
        r["centro"] = [math.cos(ang) * dist, math.sin(ang) * dist]
    for _ in range(60):
        mexeu = False
        for a in regioes:
            for b in regioes:
                if a is b or a["tipo"] not in DURAS or b["tipo"] not in DURAS:
                    continue
                va = Vector((a["centro"][0], a["centro"][1]))
                vb = Vector((b["centro"][0], b["centro"][1]))
                minimo = a["raio_m"] + b["raio_m"] + 16
                d = (va - vb).length
                if d < minimo:
                    direcao = (va - vb).normalized() if d > 1e-3 else Vector((1, 0))
                    va += direcao * (minimo - d) * 0.5
                    a["centro"] = [va.x, va.y]
                    mexeu = True
        for r in regioes:
            m = max(limite - (r["raio_m"] if r["tipo"] in DURAS else 0), 0)
            x, z = r["centro"]
            if abs(x) > m or abs(z) > m:
                r["centro"] = [max(-m, min(m, x)), max(-m, min(m, z))]
        if not mexeu:
            break
    else:
        avisos.append("não coube tudo sem encostar: algumas regiões ficaram coladas (aumente tamanho_m).")
    for r in regioes:
        r["centro"] = [round(r["centro"][0], 2), round(r["centro"][1], 2)]


# ---------------- ruído e relevo ----------------

def _ruido_valor(n, celulas, rng):
    celulas = max(1, int(celulas))
    g = rng.random((celulas + 3, celulas + 3))
    o = rng.random()
    t = np.linspace(o, o + celulas, n)
    i = np.minimum(t.astype(np.int64), celulas + 1)
    f = t - i
    f = f * f * f * (f * (f * 6 - 15) + 10)
    a, b = g[np.ix_(i, i)], g[np.ix_(i, i + 1)]
    cc, d = g[np.ix_(i + 1, i)], g[np.ix_(i + 1, i + 1)]
    fr, fc = f[:, None], f[None, :]
    return (a * (1 - fc) + b * fc) * (1 - fr) + (cc * (1 - fc) + d * fc) * fr


def _fbm(n, celulas, oitavas, rng, crista=False):
    soma = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(oitavas):
        cel = min(celulas * 2 ** o, n // 2)
        v = _ruido_valor(n, cel, rng)
        v = (1 - np.abs(2 * v - 1)) ** 2 if crista else 2 * v - 1
        soma += amp * v
        tot += amp
        amp *= 0.5
    return soma / tot


class Grade:
    def __init__(self, L, res):
        self.L = L
        self.n = int(round(L / res)) + 1
        self.res = L / (self.n - 1)
        eixo = -L / 2 + np.arange(self.n) * self.res
        self.X, self.Z = np.meshgrid(eixo, eixo)  # X[linha, coluna], Z[linha, coluna]

    def indice(self, x, z):
        return (np.asarray(x) + self.L / 2) / self.res, (np.asarray(z) + self.L / 2) / self.res

    def amostrar(self, A, x, z):
        cx, cz = self.indice(x, z)
        cx = np.clip(cx, 0, self.n - 1.001)
        cz = np.clip(cz, 0, self.n - 1.001)
        ix, iz = cx.astype(np.int64), cz.astype(np.int64)
        fx, fz = cx - ix, cz - iz
        return (A[iz, ix] * (1 - fx) * (1 - fz) + A[iz, ix + 1] * fx * (1 - fz) + A[iz + 1, ix] * (1 - fx) * fz
                + A[iz + 1, ix + 1] * fx * fz)

    def dist(self, cx, cz):
        return np.hypot(self.X - cx, self.Z - cz)


def _erosao(H, intensidade, rng):
    """Erosão hidráulica por gotas, todas andando juntas (numpy): cava os vales e deposita nas baixadas."""
    if intensidade <= 0:
        return H
    n = H.shape[0]
    lo, hi = float(H.min()), float(H.max())
    esc = max(hi - lo, 1e-3)
    h = (H - lo) / esc
    total = int(n * n * 0.6 * intensidade)
    inercia, capacidade, inc_min, depos, erod, evap, grav, passos = 0.05, 4.0, 0.01, 0.3, 0.3, 0.015, 4.0, 40
    pincel = [(dy, dx, w / 16.0) for dy, dx, w in ((-1, -1, 1), (-1, 0, 2), (-1, 1, 1), (0, -1, 2), (0, 0, 4), (0, 1, 2),
                                                    (1, -1, 1), (1, 0, 2), (1, 1, 1))]
    lim = n - 2
    lote = 8192
    for ini in range(0, total, lote):
        m = min(lote, total - ini)
        px = rng.random(m) * (lim - 2) + 1
        py = rng.random(m) * (lim - 2) + 1
        dx, dy = np.zeros(m), np.zeros(m)
        vel, agua, sed = np.ones(m), np.ones(m), np.zeros(m)
        vivo = np.ones(m, bool)
        for _ in range(passos):
            ix, iy = px.astype(np.int64), py.astype(np.int64)
            fx, fy = px - ix, py - iy
            h00, h10, h01, h11 = h[iy, ix], h[iy, ix + 1], h[iy + 1, ix], h[iy + 1, ix + 1]
            gx = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
            gy = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
            alt = h00 * (1 - fx) * (1 - fy) + h10 * fx * (1 - fy) + h01 * (1 - fx) * fy + h11 * fx * fy
            dx = dx * inercia - gx * (1 - inercia)
            dy = dy * inercia - gy * (1 - inercia)
            comp = np.hypot(dx, dy)
            vivo &= comp > 1e-12
            comp = np.maximum(comp, 1e-12)
            dx, dy = dx / comp, dy / comp
            nx, ny = px + dx, py + dy
            vivo &= (nx >= 1) & (nx < lim) & (ny >= 1) & (ny < lim)
            if not vivo.any():
                break
            nxc, nyc = np.clip(nx, 1, lim - 1e-3), np.clip(ny, 1, lim - 1e-3)
            jx, jy = nxc.astype(np.int64), nyc.astype(np.int64)
            ex, ey = nxc - jx, nyc - jy
            alt2 = (h[jy, jx] * (1 - ex) * (1 - ey) + h[jy, jx + 1] * ex * (1 - ey) + h[jy + 1, jx] * (1 - ex) * ey
                    + h[jy + 1, jx + 1] * ex * ey)
            dh = alt2 - alt
            cap = np.maximum(-dh, inc_min) * vel * agua * capacidade
            dep = (sed > cap) | (dh > 0)
            qd = np.where(dh > 0, np.minimum(dh, sed), (sed - cap) * depos)
            qe = np.minimum((cap - sed) * erod, np.maximum(-dh, 0.0))
            qd = np.where(dep & vivo, qd, 0.0)
            qe = np.where(~dep & vivo, qe, 0.0)
            sed += qe - qd
            for oy, ox, w in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
                np.add.at(h, (iy + oy, ix + ox), qd * w)
            cx, cy = np.rint(px).astype(np.int64), np.rint(py).astype(np.int64)
            for oy, ox, w in pincel:
                np.add.at(h, (cy + oy, cx + ox), -qe * w)
            vel = np.sqrt(np.maximum(vel * vel - dh * grav, 0.0))
            agua *= 1 - evap
            px, py = np.where(vivo, nx, px), np.where(vivo, ny, py)
    return h * esc + lo


def _suavizar(A, vezes=1):
    for _ in range(vezes):
        B = A.copy()
        B[1:-1, 1:-1] = (A[1:-1, 1:-1] * 4 + A[:-2, 1:-1] + A[2:, 1:-1] + A[1:-1, :-2] + A[1:-1, 2:]) / 8
        A = B
    return A


# ---------------- linhas: rio e estradas ----------------

def _chaikin(pts, vezes=3):
    pts = np.asarray(pts, float)
    for _ in range(vezes):
        novo = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            novo += [a * 0.75 + b * 0.25, a * 0.25 + b * 0.75]
        novo.append(pts[-1])
        pts = np.array(novo)
    return pts


def _rdp(pts, eps):
    """Tira os degraus da grade (Ramer-Douglas-Peucker) antes de arredondar a linha."""
    pts = np.asarray(pts, float)
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    l2 = float(ab @ ab)
    if l2 < 1e-12:
        d = np.hypot(*(pts - a).T)
    else:
        d = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / math.sqrt(l2)
    i = int(np.argmax(d))
    if d[i] > eps:
        return np.vstack([_rdp(pts[: i + 1], eps)[:-1], _rdp(pts[i:], eps)])
    return np.array([a, b])


def _lados(pts):
    tang = np.gradient(pts, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    return np.stack([-tang[:, 1], tang[:, 0]], axis=1)


def _serpentear(pts, s, amp, onda, rnd):
    """Curvas de rio de verdade: desvio lateral em duas ondas, zero nas pontas."""
    f1, f2 = rnd.uniform(0, math.tau), rnd.uniform(0, math.tau)
    desvio = amp * (np.sin(2 * math.pi * s / onda + f1) + 0.45 * np.sin(2 * math.pi * s / (onda * 1.73) + f2))
    desvio *= _ss(0, 40, s) * _ss(0, 40, s[-1] - s)
    return pts + _lados(pts) * desvio[:, None]


def _reamostrar(pts, passo):
    pts = np.asarray(pts, float)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < passo:
        return pts, s
    novo_s = np.linspace(0, s[-1], max(int(s[-1] / passo) + 1, 2))
    return np.stack([np.interp(novo_s, s, pts[:, 0]), np.interp(novo_s, s, pts[:, 1])], axis=1), novo_s


def _dist_linha(g, pts, alcance):
    """Distância de cada ponto da grade até a linha e a posição (metros ao longo dela) do ponto mais perto."""
    d = np.full((g.n, g.n), np.inf)
    t = np.zeros((g.n, g.n))
    seg = np.hypot(*np.diff(pts, axis=0).T)
    acum = np.concatenate([[0], np.cumsum(seg)])
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        x0, x1 = min(a[0], b[0]) - alcance, max(a[0], b[0]) + alcance
        z0, z1 = min(a[1], b[1]) - alcance, max(a[1], b[1]) + alcance
        c0, r0 = g.indice(x0, z0)
        c1, r1 = g.indice(x1, z1)
        c0, r0 = max(int(c0), 0), max(int(r0), 0)
        c1, r1 = min(int(c1) + 2, g.n), min(int(r1) + 2, g.n)
        if c0 >= c1 or r0 >= r1:
            continue
        X, Z = g.X[r0:r1, c0:c1], g.Z[r0:r1, c0:c1]
        ab = b - a
        l2 = max(float(ab @ ab), 1e-9)
        u = np.clip(((X - a[0]) * ab[0] + (Z - a[1]) * ab[1]) / l2, 0, 1)
        dd = np.hypot(X - (a[0] + u * ab[0]), Z - (a[1] + u * ab[1]))
        sub_d, sub_t = d[r0:r1, c0:c1], t[r0:r1, c0:c1]
        perto = dd < sub_d
        sub_d[perto] = dd[perto]
        sub_t[perto] = (acum[k] + u * seg[k])[perto]
    return d, t


def _menor_caminho(alt, extra, ini, fim, passo_m, peso_inclinacao, inclinacao_max=None):
    """A* na grade grossa: o custo cresce com a inclinação e com o 'extra' de cada célula (inf = bloqueada)."""
    m = alt.shape[0]
    A = alt.tolist()
    E = extra.tolist()
    alvo_r, alvo_c = fim
    dist = {ini: 0.0}
    de = {}
    heap = [(0.0, 0.0, ini)]
    viz = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while heap:
        _, gu, u = heapq.heappop(heap)
        if u == fim:
            break
        if gu > dist.get(u, math.inf) + 1e-9:
            continue
        r, c_ = u
        for dr, dc in viz:
            rr, cc = r + dr, c_ + dc
            if not (0 <= rr < m and 0 <= cc < m):
                continue
            e = E[rr][cc]
            if e == math.inf:
                continue
            dd = passo_m * (1.41421356 if dr and dc else 1.0)
            inc = (A[rr][cc] - A[r][c_]) / dd
            ng = gu + dd * (1.0 + peso_inclinacao * inc * inc + e)
            if inclinacao_max is not None and abs(inc) > inclinacao_max:
                ng += dd * 400.0 * (abs(inc) - inclinacao_max) / inclinacao_max  # sobe fazendo curvas
            if ng < dist.get((rr, cc), math.inf):
                dist[(rr, cc)] = ng
                de[(rr, cc)] = u
                heur = math.hypot(rr - alvo_r, cc - alvo_c) * passo_m
                heapq.heappush(heap, (ng + heur, ng, (rr, cc)))
    if fim not in de and fim != ini:
        return None
    caminho = [fim]
    while caminho[-1] != ini:
        caminho.append(de[caminho[-1]])
    return caminho[::-1]


def _tabuleiro(perfil, ponte, nivel_agua):
    """A ponte é uma reta de uma margem à outra, acima da água mais alta da travessia."""
    perfil = np.array(perfil, float)
    idx = np.flatnonzero(ponte)
    for gr in (np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []):
        i0, i1 = max(gr[0] - 1, 0), min(gr[-1] + 1, len(perfil) - 1)
        reta = np.interp(gr, [i0, i1], [perfil[i0], perfil[i1]])
        perfil[gr] = reta + max(0.0, float((nivel_agua[gr] + 1.4 - reta).max()))
    return perfil


def _perfil_suave(valores, janela, inclinacao_max, passo, fixos=None):
    v = np.array(valores, float)
    fixos = np.zeros(len(v), bool) if fixos is None else fixos
    if len(v) > 3 and janela > 1:
        k = np.ones(janela) / janela
        v = np.convolve(np.pad(v, janela // 2, mode="edge"), k, mode="valid")[: len(valores)]
    sobe = inclinacao_max * passo
    if fixos.any():
        # faixa possível de cada ponto pelos pontos presos; se não houver jeito, o meio da faixa
        # (o excesso se espalha pelo trecho em vez de virar degrau)
        i_fix = np.flatnonzero(fixos)
        dist = np.abs(np.arange(len(v))[:, None] - i_fix[None, :]) * sobe
        baixo = (v[i_fix][None, :] - dist).max(axis=1)
        alto = (v[i_fix][None, :] + dist).min(axis=1)
        sem_jeito = (baixo > alto) & ~fixos
        if sem_jeito.any():
            # entre dois pontos presos sem distância para a rampa: reta entre eles (rampa igual no trecho)
            for i in np.flatnonzero(sem_jeito):
                antes_f, depois_f = i_fix[i_fix < i], i_fix[i_fix > i]
                if len(antes_f) and len(depois_f):
                    a_, b_ = antes_f[-1], depois_f[0]
                    v[i] = v[a_] + (v[b_] - v[a_]) * (i - a_) / (b_ - a_)
                else:
                    v[i] = (baixo[i] + alto[i]) / 2
            fixos = fixos | sem_jeito
        v = np.where(fixos, v, np.clip(v, baixo, alto))
    for _ in range(40):  # ida e volta até assentar
        antes = v.copy()
        for i in range(1, len(v)):
            if not fixos[i]:
                v[i] = min(max(v[i], v[i - 1] - sobe), v[i - 1] + sobe)
        for i in range(len(v) - 2, -1, -1):
            if not fixos[i]:
                v[i] = min(max(v[i], v[i + 1] - sobe), v[i + 1] + sobe)
        if np.allclose(antes, v, atol=1e-4):
            break
    return v


# ---------------- gerar ----------------

def gerar(plano, paleta=None):
    t0 = time.time()
    P = plano
    L, rel = P["tamanho_m"], P["relevo"]
    g = Grade(L, P["resolucao_m"])
    n, res = g.n, g.res
    rng = np.random.default_rng(P["seed"])
    rnd = random.Random(P["seed"])
    altura = rel["altura_m"]
    amp, peso_crista = ESTILOS[rel["estilo"]]
    regioes = P["regioes"]
    por_id = {r["id"]: r for r in regioes}
    spawn = por_id[P["spawn"]]
    d_reg = {r["id"]: g.dist(*r["centro"]) for r in regioes}

    # 1. relevo de base: ruído, cristas, morros das regiões e a borda que fecha o mapa
    base = _fbm(n, max(2, int(L / 170)), 6, rng)
    crista = _fbm(n, max(2, int(L / 230)), 5, rng, crista=True)
    H = altura * (0.5 * amp * base + peso_crista * crista)
    if rel["estilo"] == "vale":
        H += altura * 0.7 * (np.hypot(g.X, g.Z) / (L / 2)) ** 2
    for r in regioes:
        d = d_reg[r["id"]]
        if r["tipo"] in MORRO:
            alto = 1.6 if r["tipo"] == "montanha" else (1.1 if r["tipo"] == "vulcao" else 0.8)
            H += altura * alto * np.exp(-(d / r["raio_m"]) ** 2 * 1.6) * (0.75 + 0.5 * crista)
        elif r["tipo"] in ENCOSTA:
            # a masmorra entra num morro: o morro fica atrás da entrada, do lado oposto ao de quem chega
            ida = Vector((r["centro"][0] - spawn["centro"][0], r["centro"][1] - spawn["centro"][1]))
            ida = ida.normalized() if ida.length > 1e-3 else Vector((0, -1))
            mx, mz = r["centro"][0] + ida.x * r["raio_m"] * 1.2, r["centro"][1] + ida.y * r["raio_m"] * 1.2
            H += max(altura * 0.6, 12.0) * np.exp(-(g.dist(mx, mz) / (r["raio_m"] * 2.0)) ** 2 * 1.4)
        elif r["tipo"] == "castelo":
            H += max(altura * 0.4, 8.0) * np.exp(-(d / (r["raio_m"] * 2.2)) ** 2 * 1.4)
    torto = _fbm(n, max(3, int(L / 110)), 3, rng)
    e = ((np.abs(g.X) / (L / 2)) ** 6 + (np.abs(g.Z) / (L / 2)) ** 6) ** (1 / 6) * (1 + 0.07 * torto)
    H += altura * 0.9 * _ss(0.8, 1.0, e) ** 1.5 * (0.55 + 0.9 * crista) + 6.0 * _ss(0.82, 1.0, e)

    # 2. erosão
    H = _erosao(H, rel["erosao"], rng)

    # 3. chão plano das regiões (vila, arena...) e o patamar da entrada da masmorra, antes do rio
    chao = {}  # altura do chão plano de cada região
    # campo e pântano antes: o chão da vila, da arena e da masmorra (que vêm depois) fica por cima
    for r in sorted(regioes, key=lambda r_: 0 if r_["tipo"] in ("campo", "pantano") else 1):
        d, raio = d_reg[r["id"]], r["raio_m"]
        if r["tipo"] in PLANAS or r["tipo"] in ENCOSTA or r["tipo"] == "castelo":
            nucleo = d < raio * 0.8
            alvo = float(np.median(H[nucleo])) if nucleo.any() else float(g.amostrar(H, *r["centro"]))
            if r["tipo"] in ENCOSTA and nucleo.any():
                alvo = float(np.percentile(H[nucleo], 25))  # a entrada corta o pé do morro
            if r["tipo"] == "castelo":
                alvo = float(g.amostrar(H, *r["centro"]))
            chao[r["id"]] = alvo
            fora = 0.9 if r["tipo"] in ENCOSTA else 0.85
            w = (1 - _ss(raio * fora, raio * 1.6, d)) * (0.6 if r["tipo"] == "campo" else 1.0)
            H = H * (1 - w) + alvo * w
            if r["tipo"] == "campo":
                chao.pop(r["id"], None)  # campo é chão suave, não patamar
        elif r["tipo"] == "pantano":
            w = (1 - _ss(raio * 0.6, raio * 1.2, d)) * 0.7
            H = H * (1 - w) + (np.percentile(H, 15)) * w

    # 4. rio: segue o terreno baixo; a água só desce
    agua_nivel = np.full((n, n), np.nan)
    rios = []
    d_rio = np.full((n, n), np.inf)
    t_rio = np.zeros((n, n))
    nivel_rio = None
    if P["rio"]:
        rio = P["rio"]
        passo_c = 4.0
        s = max(int(round(passo_c / res)), 1)
        alt_c = H[::s, ::s]
        m = alt_c.shape[0]
        hn = (alt_c - alt_c.min()) / max(np.ptp(alt_c), 1e-6)
        extra = 10.0 * hn * hn + 2.0 * (_fbm(m, max(3, int(L / 70)), 3, rng) + 1)
        Xc, Zc = g.X[::s, ::s], g.Z[::s, ::s]
        for r in regioes:
            dc = np.hypot(Xc - r["centro"][0], Zc - r["centro"][1])
            if r["tipo"] == "lago":
                extra = np.where(dc < r["raio_m"] * 1.9, math.inf, extra)
            elif r["tipo"] in DURAS:
                extra = extra + 60.0 * (dc < r["raio_m"] * 1.5)
        if rio.get("pontos"):
            pts = np.array([[float(p[0]), float(p[-1])] for p in rio["pontos"]])
        else:
            lado = rnd.choice(("ns", "lo"))
            k0, k1 = rnd.uniform(0.25, 0.75), rnd.uniform(0.25, 0.75)
            if lado == "ns":
                ini, fim = (1, int(k0 * (m - 1))), (m - 2, int(k1 * (m - 1)))
            else:
                ini, fim = (int(k0 * (m - 1)), 1), (int(k1 * (m - 1)), m - 2)
            cam = _menor_caminho(hn, extra, ini, fim, passo_c, 0.0)
            pts = np.array([[Xc[a, b], Zc[a, b]] for a, b in cam]) if cam else np.array([[-L / 2, 0.0], [L / 2, 0.0]])
        w, prof = rio["largura_m"], rio["profundidade_m"]
        pts = _chaikin(_rdp(pts, 6.0), 3)
        if not rio.get("pontos"):
            pts, s_rio = _reamostrar(pts, 3.0)
            pts = _serpentear(pts, s_rio, w * 0.8 + 5, rnd.uniform(80, 130), rnd)
            pts = _chaikin(pts, 1)
            for r in regioes:  # a curva não pode entrar na vila, na masmorra nem no lago
                if r["tipo"] in DURAS:
                    folga = r["raio_m"] * (1.8 if r["tipo"] == "lago" else 1.35) + w
                    v = pts - np.array(r["centro"])
                    dist = np.hypot(*v.T)
                    dentro_r = dist < folga
                    pts[dentro_r] = np.array(r["centro"]) + v[dentro_r] / np.maximum(dist[dentro_r, None], 1e-6) * folga
        pts, s_rio = _reamostrar(pts, 3.0)
        perfil = g.amostrar(H, pts[:, 0], pts[:, 1])
        perfil = np.minimum.accumulate(_perfil_suave(perfil, 9, 1.0, 3.0))
        nivel = perfil - 0.4
        meio_s = w / 2 * (1 + 0.22 * np.sin(2 * math.pi * s_rio / 150 + rnd.uniform(0, 6)))
        d_rio, t_rio = _dist_linha(g, pts, w / 2 + 60)
        nivel_rio = np.interp(t_rio, s_rio, nivel)
        meio = np.interp(t_rio, s_rio, meio_s)
        dd = d_rio - meio
        # leito em U, margem que sobe devagar e vai ficando mais íngreme (sem degrau na beira do vale)
        alvo = np.where(dd < 0, nivel_rio - prof * (1 - (d_rio / meio) ** 2), nivel_rio + 0.3 * dd + 0.012 * dd * dd)
        patamar = np.zeros((n, n), bool)
        for r in regioes:
            if r["id"] in chao:
                patamar |= d_reg[r["id"]] < r["raio_m"] * 0.9
        H = np.where(np.isfinite(d_rio) & ~patamar, np.minimum(H, alvo), H)
        margem = (dd >= 0) & (dd < 3)
        H = np.where(margem, np.maximum(H, nivel_rio + 0.15), H)
        agua_nivel = np.where(dd < 1.0, nivel_rio, agua_nivel)
        rios.append({"pontos": pts, "s": s_rio, "nivel": nivel, "largura_m": w, "meio": meio_s})

    # 5. lagos de margem torta
    lagos = []
    forma = 1 + 0.4 * _fbm(n, max(3, int(L / 55)), 3, rng)
    for r in regioes:
        d, raio = d_reg[r["id"]], r["raio_m"]
        if r["tipo"] == "lago":
            d = d / forma  # margem torta, não um círculo
            anel = (d > raio) & (d < raio * 1.3)
            nivel = float(np.percentile(H[anel], 30)) - 0.5 if anel.any() else float(H.mean())
            prof = max(2.0, raio * 0.08)
            alvo = nivel - prof * (1 - (d / raio) ** 2)
            w = 1 - _ss(raio * 0.95, raio * 1.5, d)
            H = np.minimum(H, H * (1 - w) + alvo * w)
            # margem: onde o chão em volta é mais baixo que a água, sobe em rampa suave (sem degrau)
            falta = np.maximum(nivel + 0.25 - H, 0) * (1 - _ss(raio * 1.45, raio * 1.9, d)) * (d >= raio * 0.98)
            H = H + np.where(d_rio < 30, 0.0, falta)
            agua_nivel = np.where(d < raio * 1.25, nivel, agua_nivel)
            lagos.append({"id": r["id"], "centro": r["centro"], "raio_m": raio * 1.6, "nivel": nivel, "d": d, "raio": raio})

    # 6. estradas: A* que foge de barranco e de água; o chão se acerta ao perfil suave; ponte no rio
    estradas = []
    larg = P["largura_estrada_m"]
    d_estrada = np.full((n, n), np.inf)
    passo_c = 4.0
    s = max(int(round(passo_c / res)), 1)
    alt_c = H[::s, ::s]
    Xc, Zc = g.X[::s, ::s], g.Z[::s, ::s]
    m = alt_c.shape[0]
    extra = np.zeros((m, m))
    if rios:
        extra += np.where(d_rio[::s, ::s] < rios[0]["largura_m"] / 2 + 2, 25.0, 0.0)
    for lg in lagos:
        extra = np.where(lg["d"][::s, ::s] < lg["raio"] * 1.1, math.inf, extra)
    extra += np.where(np.maximum(np.abs(Xc), np.abs(Zc)) > L / 2 * 0.9, 30.0, 0.0)
    for est in P["estradas"]:
        a, b = por_id[est["de"]], por_id[est["para"]]

        def celula(cx, cz):
            cc, rr = g.indice(cx, cz)
            return (int(min(max(round(rr / s), 0), m - 1)), int(min(max(round(cc / s), 0), m - 1)))

        cam = _menor_caminho(alt_c, extra, celula(*a["centro"]), celula(*b["centro"]), passo_c, 60.0, inclinacao_max=0.14)
        if not cam:
            estradas.append({"de": a["id"], "para": b["id"], "pontos": None})
            continue
        pts = np.array([[Xc[i, j], Zc[i, j]] for i, j in cam])
        pts = _chaikin(_rdp(pts, 4.0), 4)
        pts, s_est = _reamostrar(pts, 2.0)
        cru = g.amostrar(H, pts[:, 0], pts[:, 1])
        ponte = np.zeros(len(pts), bool)
        nr = np.full(len(pts), -1e6)
        if rios:
            dr = g.amostrar(np.where(np.isfinite(d_rio), d_rio, 1e6), pts[:, 0], pts[:, 1])
            ponte = dr < rios[0]["largura_m"] / 2 + 2.5
            nr = g.amostrar(np.where(np.isfinite(agua_nivel), agua_nivel, -1e6), pts[:, 0], pts[:, 1])
            cru = _tabuleiro(cru, ponte, nr)
        perfil = _perfil_suave(cru, 13, 0.16, 2.0)
        presos = np.zeros(len(pts), bool)
        for r in (a, b):
            if r["id"] in chao:
                dentro_r = np.hypot(pts[:, 0] - r["centro"][0], pts[:, 1] - r["centro"][1]) < r["raio_m"] * 0.95
                perfil[dentro_r] = chao[r["id"]]
                presos |= dentro_r
        for _ in range(4):
            perfil = _tabuleiro(perfil, ponte, nr)
            perfil = _perfil_suave(perfil, 1, 0.16, 2.0, fixos=presos | ponte)
        d, t = _dist_linha(g, pts, larg / 2 + 8)
        alvo = np.interp(t, s_est, perfil)
        w = 1 - _ss(larg / 2 + 0.3, larg / 2 + 5.0, d)
        if rios:
            w = np.where(d_rio < rios[0]["largura_m"] / 2 + 1.5, 0.0, w)
        for r in regioes:  # o chão plano das regiões já está certo: a estrada não mexe nele
            if r["id"] in chao:
                w = w * _ss(r["raio_m"] * 0.85, r["raio_m"] * 1.05, d_reg[r["id"]])
        H = H * (1 - w) + alvo * w
        d_estrada = np.minimum(d_estrada, d)
        estradas.append({"de": a["id"], "para": b["id"], "pontos": pts, "s": s_est, "perfil": perfil, "ponte": ponte})

    # 7. inclinação, água e pintura do chão
    dz, dx = np.gradient(H, res)
    inclin = np.degrees(np.arctan(np.hypot(dx, dz)))
    prof_agua = np.where(np.isfinite(agua_nivel), agua_nivel - H, -np.inf)
    d_agua = np.minimum(d_rio - (rios[0]["largura_m"] / 2 if rios else 0), np.inf)
    for lg in lagos:
        d_agua = np.minimum(d_agua, (lg["d"] - lg["raio"]) * forma)
    d_agua = np.maximum(d_agua, 0)
    hmin, hmax = float(H.min()), float(H.max())
    hrel = (H - hmin) / max(hmax - hmin, 1e-6)
    manchas = _fbm(n, max(4, int(L / 40)), 4, rng)
    rocha = _ss(27, 40, inclin + manchas * 4)
    estrada_m = 1 - _ss(larg / 2 - 0.6, larg / 2 + 0.9 + manchas * 0.6, d_estrada)
    terra = np.maximum(estrada_m, _ss(16, 27, inclin) * 0.45 + _ss(0.25, 0.7, manchas) * 0.25)
    for r in regioes:
        if KIT.get(r["tipo"]) in ("vila", "arena", "masmorra"):
            terra = np.maximum(terra, (1 - _ss(r["raio_m"] * 0.35, r["raio_m"] * 0.85, d_reg[r["id"]] + manchas * 3)) * 0.7)
    ultima = "neve" if P["clima"] == "neve" else "areia"
    if ultima == "neve":
        quarta = _ss(0.45, 0.6, hrel + manchas * 0.05) * (1 - rocha * 0.6)
    else:
        quarta = (1 - _ss(1.5, 5.0, d_agua + manchas * 1.5)) * (prof_agua > -2.5)
        if P["clima"] == "seco":
            quarta = np.maximum(quarta, _ss(0.1, 0.6, manchas) * 0.35)
    camadas = np.stack([np.ones_like(H), terra, rocha, quarta], axis=-1)
    camadas[..., 0] = np.clip(1 - terra - rocha - quarta, 0, 1)
    camadas /= np.maximum(camadas.sum(-1, keepdims=True), 1e-6)

    # 8. vegetação e pedras por regras
    fundo = {"seco": 0.03, "neve": 0.06}.get(P["clima"], 0.1)
    umid = np.exp(-d_agua / 35.0) if (rios or lagos) else np.zeros_like(H)
    bosques = _ss(0.05, 0.45, _fbm(n, max(3, int(L / 90)), 3, rng))
    # fora das florestas, a mata vem em bosques (não salpicada) e acompanha a água (mata ciliar)
    mata = fundo * (0.15 + 2.5 * np.maximum(bosques, 0.75 * umid))
    mata_regioes = np.zeros((n, n))
    for r in regioes:
        if r["tipo"] in MATA:
            borda_ruido = manchas * r["raio_m"] * 0.15
            m_r = MATA[r["tipo"]] * (1 - _ss(r["raio_m"] * 0.75, r["raio_m"] * 1.15, d_reg[r["id"]] + borda_ruido))
            mata = np.maximum(mata, m_r)
            mata_regioes = np.maximum(mata_regioes, m_r)
        if r["tipo"] == "campo":
            mata = np.where(d_reg[r["id"]] < r["raio_m"], mata * 0.2, mata)
            # o campo é clareira de propósito: fica fora da conta "perto da água × longe" (como a floresta)
            mata_regioes = np.maximum(mata_regioes, (d_reg[r["id"]] < r["raio_m"] * 1.1).astype(float))
    inclin_viz = inclin.copy()  # a pior inclinação em volta (a árvore tem raiz, não é um ponto)
    for dz_, dx_ in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        inclin_viz = np.maximum(inclin_viz, np.roll(np.roll(inclin, dz_, 0), dx_, 1))
    proibido = (inclin_viz > 27) | (prof_agua > -0.6) | (d_agua < 3) | (d_estrada < larg / 2 + 3) | (e > 0.985)
    proibido |= hrel > 0.82  # acima da linha das árvores
    for r in regioes:
        if r["tipo"] in DURAS:
            proibido |= d_reg[r["id"]] < r["raio_m"] * 1.05
    proibido |= g.dist(*spawn["centro"]) < 14
    densidade_arv = mata * (1 + 1.5 * umid) * (0.25 + 1.1 * _ss(-0.35, 0.45, manchas))
    if P["clima"] == "seco":
        densidade_arv *= 0.4

    def espalhar(espacamento, dens, proib, semente):
        r2 = np.random.default_rng(semente)
        eixo = np.arange(-L / 2 + espacamento / 2, L / 2, espacamento)
        PX, PZ = np.meshgrid(eixo, eixo)
        PX = PX + r2.uniform(-0.45, 0.45, PX.shape) * espacamento
        PZ = PZ + r2.uniform(-0.45, 0.45, PZ.shape) * espacamento
        PX, PZ = PX.ravel(), PZ.ravel()
        ci, ri = g.indice(PX, PZ)
        ci = np.clip(np.rint(ci).astype(np.int64), 0, n - 1)
        ri = np.clip(np.rint(ri).astype(np.int64), 0, n - 1)
        ok = (~proib[ri, ci]) & (r2.random(PX.shape) < np.clip(dens[ri, ci], 0, 1))
        return PX[ok], PZ[ok], r2

    def instancias(px, pz, r2, variantes, pesos, escala, afunda):
        h = g.amostrar(H, px, pz)
        inc = g.amostrar(inclin, px, pz)
        var = r2.choice(len(variantes), size=len(px), p=np.asarray(pesos) / np.sum(pesos)) if len(px) else np.array([], int)
        esc = r2.uniform(*escala, size=len(px))
        rot = r2.uniform(0, math.tau, size=len(px))
        y = h - afunda * esc - np.tan(np.radians(inc)) * 0.4 * esc
        return np.stack([var, px, y, pz, rot, esc], axis=1)

    arv_x, arv_z, r2 = espalhar(5.0, densidade_arv, proibido, P["seed"] + 1)
    pinheiros = {"temperado": 0.35, "seco": 0.1, "frio": 0.75, "neve": 0.9, "chuvoso": 0.4}[P["clima"]]
    arvores = instancias(arv_x, arv_z, r2, range(4), [(1 - pinheiros) / 2] * 2 + [pinheiros / 2] * 2, (0.8, 1.3), 0.15)
    dens_arb = 0.05 + 0.4 * mata * (1 - mata) * 2 + 0.3 * umid + 0.15 * ((d_estrada > larg / 2 + 2) & (d_estrada < larg / 2 + 7))
    proib_arb = (inclin > 32) | (prof_agua > -0.3) | (d_estrada < larg / 2 + 1.5) | (e > 0.985)
    for r in regioes:
        if r["tipo"] in DURAS:
            proib_arb |= d_reg[r["id"]] < r["raio_m"] * 0.9
    arb_x, arb_z, r3 = espalhar(4.0, dens_arb * (0.4 if P["clima"] == "seco" else 1.0), proib_arb, P["seed"] + 2)
    arbustos = instancias(arb_x, arb_z, r3, range(3), [1, 1, 1], (0.7, 1.4), 0.12)
    dens_ped = 0.03 + 0.5 * _ss(14, 34, inclin) + 0.25 * _ss(0.55, 0.8, hrel)
    proib_ped = (inclin > 48) | (prof_agua > 0.4) | (d_estrada < larg / 2 + 1.0)
    for r in regioes:
        if r["tipo"] in DURAS and r["tipo"] != "lago":
            proib_ped |= d_reg[r["id"]] < r["raio_m"] * 0.9
    ped_x, ped_z, r4 = espalhar(8.0, dens_ped, proib_ped, P["seed"] + 3)
    pedras = instancias(ped_x, ped_z, r4, range(4), [1, 1, 1, 1], (0.6, 2.6), 0.3)

    return {
        "g": g, "H": H, "inclin": inclin, "camadas": camadas, "ultima": ultima, "agua_nivel": agua_nivel, "prof_agua": prof_agua,
        "d_agua": d_agua, "d_estrada": d_estrada, "rios": rios, "lagos": lagos, "estradas": estradas, "arvores": arvores,
        "arbustos": arbustos, "pedras": pedras, "d_reg": d_reg, "segundos": round(time.time() - t0, 1), "e": e,
        "mata_regioes": mata_regioes, "proibido": proibido,
    }


# ---------------- medidas ----------------

def medir(P, R):
    g, H, inclin = R["g"], R["H"], R["inclin"]
    n, res, L = g.n, g.res, g.L
    larg = P["largura_estrada_m"]
    itens = []

    def item(nome, valor, ok, limite, explica):
        itens.append({"nome": nome, "valor": valor, "limite": limite, "ok": bool(ok), "explica": explica})

    dentro = R["e"] < 0.88
    submerso = R["prof_agua"] > 0.6
    andavel = (inclin < 35) & ~submerso
    pct = float(andavel[dentro].mean() * 100)
    item("area_andavel_pct", round(pct, 1), pct >= 55, ">= 55", "parte do mapa (sem a borda) com inclinação abaixo de 35° e fora da água funda")
    # ligação: dá para chegar andando do ponto inicial a cada região (estrada e ponte contam)
    s = max(int(round(2.0 / res)), 1)
    passa = (andavel | (R["d_estrada"] < larg / 2))[::s, ::s]
    m = passa.shape[0]
    spawn = next(r for r in P["regioes"] if r["id"] == P["spawn"])
    ci, ri = g.indice(*spawn["centro"])
    ini = (int(round(ri / s)), int(round(ci / s)))
    visto = np.zeros_like(passa)
    if 0 <= ini[0] < m and 0 <= ini[1] < m:
        fila = deque([ini])
        visto[ini] = True
        lista = passa.tolist()
        vis = visto.tolist()
        while fila:
            r, c_ = fila.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c_ + dc
                if 0 <= rr < m and 0 <= cc < m and not vis[rr][cc] and lista[rr][cc]:
                    vis[rr][cc] = True
                    fila.append((rr, cc))
        visto = np.array(vis)
    sem_ligacao = []
    for r in P["regioes"]:
        if r["tipo"] == "lago":
            continue
        perto = R["d_reg"][r["id"]][::s, ::s] < max(r["raio_m"] * 0.5, 6)
        if not (visto & perto).any():
            sem_ligacao.append(r["id"])
    item("regioes_sem_ligacao", sem_ligacao, not sem_ligacao, "[]", "regiões aonde não se chega andando a partir do ponto inicial")
    rampas = []
    onde = None
    for est in R["estradas"]:
        if est["pontos"] is None:
            rampas.append(None)
            continue
        dp = np.abs(np.diff(est["perfil"])) / 2.0
        graus = round(float(np.degrees(np.arctan(dp.max()))) if len(dp) else 0.0, 1)
        if graus > max([x for x in rampas if x is not None], default=-1):
            i = int(np.argmax(dp))
            onde = {"estrada": f'{est["de"]}→{est["para"]}', "x": round(float(est["pontos"][i][0]), 1), "z": round(float(est["pontos"][i][1]), 1)}
        rampas.append(graus)
    faltou = [f'{e["de"]}→{e["para"]}' for e in R["estradas"] if e["pontos"] is None]
    item("estradas_sem_caminho", faltou, not faltou, "[]", "estradas que o A* não achou (água ou barranco no meio)")
    pior = max([x for x in rampas if x is not None], default=0.0)
    item("estrada_rampa_max_graus", pior, pior <= 12, "<= 12", f"a rampa mais forte das estradas (onde: {onde})")
    arv = R["arvores"]
    if len(arv):
        ax, az = arv[:, 1], arv[:, 3]
        inc_a = g.amostrar(inclin, ax, az)
        barranco = int((inc_a > 30).sum())
        na_agua = int((g.amostrar(np.where(np.isfinite(R["prof_agua"]), R["prof_agua"], -1e6), ax, az) > -0.3).sum())
        na_estrada = int((g.amostrar(np.where(np.isfinite(R["d_estrada"]), R["d_estrada"], 1e6), ax, az) < larg / 2 + 1).sum())
    else:
        barranco = na_agua = na_estrada = 0
    item("arvores_em_barranco", barranco, barranco == 0, "0", "árvores em chão com mais de 30° de inclinação")
    item("arvores_na_agua", na_agua, na_agua == 0, "0", "árvores dentro ou na beira da água")
    item("arvores_na_estrada", na_estrada, na_estrada == 0, "0", "árvores em cima da estrada")
    if (R["rios"] or R["lagos"]) and len(arv):
        da = g.amostrar(np.where(np.isfinite(R["d_agua"]), R["d_agua"], 1e6), arv[:, 1], arv[:, 3])
        fora_mata = g.amostrar(R["mata_regioes"], arv[:, 1], arv[:, 3]) < 0.05
        area = lambda msk: max(float(msk.sum()) * res * res / 10000.0, 1e-6)  # noqa: E731
        livre = dentro & (R["mata_regioes"] < 0.05) & ~R["proibido"]  # só o chão onde árvore pode nascer
        perto_m = (R["d_agua"] < 40) & livre & (R["prof_agua"] < -0.3)
        longe_m = (R["d_agua"] > 80) & livre
        dp_ = float(((da < 40) & fora_mata).sum()) / area(perto_m)
        dl_ = float(((da > 80) & fora_mata).sum()) / max(area(longe_m), 1e-6)
        # com pouco chão livre perto ou longe da água (mapa pequeno, tudo floresta ou campo) não dá para comparar
        razao = round(dp_ / max(dl_, 1e-6), 2) if min(area(perto_m), area(longe_m)) >= 0.5 else None
        item("arvores_perto_da_agua_vs_longe", razao, razao is None or razao >= 1.2, ">= 1.2", "fora das florestas e campos, mais árvores perto da água do que longe dela (no chão onde árvore pode nascer)")
    planura = {}
    for r in P["regioes"]:
        if KIT.get(r["tipo"]):
            nucleo = R["d_reg"][r["id"]] < r["raio_m"] * (0.6 if r["tipo"] in ENCOSTA else 0.8)
            planura[r["id"]] = round(float(H[nucleo].std()), 2) if nucleo.any() else 0.0
    pior_planura = max(planura.values(), default=0.0)
    item("chao_das_construcoes_desvio_m", planura, pior_planura <= 0.35, "<= 0.35", "quanto o chão da vila, arena e masmorra varia")
    if R["rios"]:
        desce = bool(np.all(np.diff(R["rios"][0]["nivel"]) <= 1e-6))
        item("rio_so_desce", desce, desce, "true", "a água do rio nunca sobe ao longo do caminho")
    reprovado = [i["nome"] for i in itens if not i["ok"]]
    return {"aprovado": not reprovado, "reprovado": reprovado, "itens": itens}


# ---------------- objetos (Blender) ----------------

def _malha_terreno(g, H, camadas, ultima, tamanho_bloco=64.0):
    """O terreno em blocos de 64 m (a engine faz o LOD de cada um), com normais da grade inteira (sem costura)."""
    n, res = g.n, g.res
    dz, dx = np.gradient(H, res)
    normal = np.stack([-dx, dz, np.ones_like(H)], axis=-1)  # Blender: y = -z
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    cores = np.array([c.cor_hex(CORES_CAMADAS[k]) for k in ("grama", "terra", "rocha", ultima)])
    cor = camadas @ cores
    passo = max(int(round(tamanho_bloco / res)), 4)
    mat = c.material("terreno", c.cor_hex(CORES_CAMADAS["grama"]), 0.95)
    objs = []
    for r0 in range(0, n - 1, passo):
        for c0 in range(0, n - 1, passo):
            r1, c1 = min(r0 + passo, n - 1), min(c0 + passo, n - 1)
            nr, nc = r1 - r0 + 1, c1 - c0 + 1
            X, Z = g.X[r0:r1 + 1, c0:c1 + 1], g.Z[r0:r1 + 1, c0:c1 + 1]
            verts = np.stack([X, -Z, H[r0:r1 + 1, c0:c1 + 1]], axis=-1).reshape(-1, 3)
            ii = np.arange(nr * nc).reshape(nr, nc)
            a, b = ii[:-1, :-1].ravel(), ii[:-1, 1:].ravel()
            cc, d = ii[1:, 1:].ravel(), ii[1:, :-1].ravel()
            faces = np.stack([a, d, cc, b], axis=1)  # anti-horário visto de cima (Blender)
            me = bpy.data.meshes.new(f"terreno_{r0 // passo:02d}_{c0 // passo:02d}")
            me.from_pydata(verts.tolist(), [], faces.tolist())
            me.polygons.foreach_set("use_smooth", np.ones(len(faces), bool))
            uv = me.uv_layers.new(name="UVMap")
            lp = np.array([lo.vertex_index for lo in me.loops])
            u = (verts[lp, 0] / g.L + 0.5)
            v = (-verts[lp, 1] / g.L + 0.5)
            uv.data.foreach_set("uv", np.stack([u, 1 - v], axis=1).ravel())
            ca = me.color_attributes.new("Col", "BYTE_COLOR", "POINT")
            cv = cor[r0:r1 + 1, c0:c1 + 1].reshape(-1, 3)
            ca.data.foreach_set("color", np.concatenate([cv, np.ones((len(cv), 1))], axis=1).ravel())
            me.normals_split_custom_set_from_vertices(normal[r0:r1 + 1, c0:c1 + 1].reshape(-1, 3).tolist())
            me.materials.append(mat)
            o = bpy.data.objects.new(me.name, me)
            bpy.context.scene.collection.objects.link(o)
            objs.append(o)
    return objs


def _terreno_longe(g, H, altura, seed):
    """Morros baixos em volta do mapa (só para o horizonte, sem colisão): a borda não acaba no vazio."""
    rng = np.random.default_rng(seed + 77)
    passo = 16.0
    lado = g.L * 3
    m = int(lado / passo) + 1
    eixo = -lado / 2 + np.arange(m) * passo
    X, Z = np.meshgrid(eixo, eixo)
    borda = g.amostrar(H, np.clip(X, -g.L / 2, g.L / 2), np.clip(Z, -g.L / 2, g.L / 2))
    fora = np.maximum(np.abs(X), np.abs(Z)) - g.L / 2
    morros = float(np.median(H)) + altura * (0.6 + 0.8 * _fbm(m, 6, 4, rng, crista=True))
    t = _ss(0, g.L * 0.35, fora)
    Y = borda * (1 - t) + morros * t - np.where(fora > 0, 0.0, 30.0)  # por dentro afunda (fica sob o terreno)
    verts = np.stack([X, -Z, Y], axis=-1).reshape(-1, 3)
    ii = np.arange(m * m).reshape(m, m)
    dentro = (np.abs(X) < g.L / 2 - passo) & (np.abs(Z) < g.L / 2 - passo)
    quad = ~(dentro[:-1, :-1] & dentro[1:, 1:] & dentro[:-1, 1:] & dentro[1:, :-1])
    a, b = ii[:-1, :-1][quad], ii[:-1, 1:][quad]
    cc, d = ii[1:, 1:][quad], ii[1:, :-1][quad]
    me = bpy.data.meshes.new("terreno_longe")
    me.from_pydata(verts.tolist(), [], np.stack([a, d, cc, b], axis=1).tolist())
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    me.materials.append(c.material("terreno", c.cor_hex(CORES_CAMADAS["grama"]), 0.95))
    o = bpy.data.objects.new("terreno_longe", me)
    bpy.context.scene.collection.objects.link(o)
    return o


def _arbusto(seed, cor):
    rnd = random.Random(seed)
    k = c.Construtor()
    folha = c.material("folha_arbusto", c.cor_hex(cor), 0.85)
    for _ in range(rnd.randint(3, 5)):
        ang, r = rnd.uniform(0, math.tau), rnd.uniform(0, 0.45)
        centro = Vector((math.cos(ang) * r, math.sin(ang) * r, rnd.uniform(0.35, 0.6)))
        vs = k.esfera(centro, rnd.uniform(0.45, 0.7), folha, escala=(1, 1, 0.75), u=9, v=6, liso=True)
        for v in vs:
            v.co += (v.co - centro).normalized() * rnd.uniform(-0.08, 0.08)
    return k.objeto(f"arbusto_{seed}")


def _e_pinheiro(seed):
    r = random.Random(seed)
    r.uniform(4.5, 7.5)
    return r.random() < 0.45


def _variantes(P, paleta):
    folha = fc_mundo._verde(paleta or [], FOLHA[P["clima"]])
    folhosas = [s for s in range(1, 400) if not _e_pinheiro(s)][:2]
    pinheiros = [s for s in range(1, 400) if _e_pinheiro(s)][:2]
    arv = [fc_armas.criar_objeto({"tipo": "arvore", "id": f"arvore_{i}", "seed": s, "escala": 1.0, "cor_folha": folha})
           for i, s in enumerate(folhosas + pinheiros)]
    arb = [_arbusto(11 + i * 7, folha) for i in range(3)]
    ped = [fc_armas.criar_objeto({"tipo": "pedra", "id": f"pedra_{i}", "seed": 21 + i * 13, "escala": 1.0}) for i in range(4)]
    for lista, nome in ((arv, "arvore"), (arb, "arbusto"), (ped, "pedra")):
        for i, o in enumerate(lista):
            o.name = f"{nome}_{i}"
    return {"arvore": arv, "arbusto": arb, "pedra": ped}


def _agua(R):
    mat = c.material("agua", c.cor_hex("#2f5f78"), 0.05)
    objs = []
    for i, rio in enumerate(R["rios"]):
        pts, nivel = rio["pontos"], rio["nivel"]
        w = (rio["meio"] + 1.5)[:, None]
        lado = _lados(pts)
        esq, dir_ = pts + lado * w, pts - lado * w
        verts = []
        for k in range(len(pts)):
            verts.append((esq[k, 0], -esq[k, 1], nivel[k]))
            verts.append((dir_[k, 0], -dir_[k, 1], nivel[k]))
        faces = [(2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2) for k in range(len(pts) - 1)]
        me = bpy.data.meshes.new(f"agua_rio_{i}")
        me.from_pydata(verts, [], faces)
        for p_ in me.polygons:
            if p_.normal.z < 0:
                p_.flip()
        me.materials.append(mat)
        o = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(o)
        objs.append(o)
    g = R["g"]
    for lg in R["lagos"]:
        # a água cobre só o contorno torto do lago (em quadrados de 2 m), não um disco
        s = max(int(round(2.0 / g.res)), 1)
        dentro = lg["d"][::s, ::s] < lg["raio"] * 1.3
        X, Z = g.X[::s, ::s], g.Z[::s, ::s]
        verts, faces, idx = [], [], {}

        def v(i, j):
            if (i, j) not in idx:
                idx[(i, j)] = len(verts)
                verts.append((float(X[i, j]), float(-Z[i, j]), lg["nivel"]))
            return idx[(i, j)]

        m = dentro.shape[0]
        for i in range(m - 1):
            for j in range(m - 1):
                if dentro[i, j] or dentro[i + 1, j] or dentro[i, j + 1] or dentro[i + 1, j + 1]:
                    faces.append((v(i, j), v(i + 1, j), v(i + 1, j + 1), v(i, j + 1)))
        me = bpy.data.meshes.new(f"agua_lago_{lg['id']}")
        me.from_pydata(verts, [], faces)
        for p_ in me.polygons:
            if p_.normal.z < 0:
                p_.flip()
        me.materials.append(mat)
        o = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(o)
        objs.append(o)
    return objs


def _estruturas(P, R, paleta):
    g, H = R["g"], R["H"]
    rnd = random.Random(P["seed"] + 9)
    pal = lambda i, padrao: paleta[i] if paleta and len(paleta) > i else padrao  # noqa: E731
    mats = {"grama": fc_mundo._verde(paleta or [], "#4d7a3a"), "caminho": "#8b7355", "parede": "#c8b79a", "telhado": pal(1, "#8a3b2a"),
            "folha": fc_mundo._verde((paleta or [])[1:], "#3f6b35"), "rocha": "#7d7a73", "masmorra": "#5a5550", "arena": "#9b8f7a"}
    objs, inimigos = [], []
    spawn = next(r for r in P["regioes"] if r["id"] == P["spawn"])
    for r in P["regioes"]:
        kit = KIT.get(r["tipo"])
        if not kit:
            continue
        cx, cz = r["centro"]
        h = float(g.amostrar(H, cx, cz))
        centro = Vector((cx, -cz, h))
        if kit == "vila":
            _vila(r, centro, rnd, mats, objs, R, P["largura_estrada_m"])
            continue
        antes, antes_i = len(objs), len(inimigos)
        if kit == "masmorra":  # salas e corredores por peças encaixadas
            fc_masmorra.gerar(r["id"], centro, rnd, mats, objs, inimigos, r["raio_m"])
        else:
            fc_mundo.GERADORES[kit](r["id"], centro, rnd, mats, objs, inimigos)
        # a entrada (que nasce virada para -Y) olha para o ponto inicial
        alvo = Vector((spawn["centro"][0], -spawn["centro"][1], h)) - centro
        if alvo.length > 1e-3:
            ang = math.atan2(alvo.y, alvo.x) + math.pi / 2
            giro = Matrix.Translation(centro) @ Matrix.Rotation(ang, 4, "Z") @ Matrix.Translation(-centro)
            bpy.context.view_layer.update()
            for o in objs[antes:]:
                o.matrix_world = giro @ o.matrix_world
            for i in range(antes_i, len(inimigos)):
                inimigos[i] = giro @ inimigos[i]
    madeira = c.material("ponte_madeira", c.cor_hex("#6b4f36"), 0.85)
    larg = P["largura_estrada_m"]
    pontes = 0
    for est in R["estradas"]:
        if est["pontos"] is None or not est["ponte"].any():
            continue
        idx = np.flatnonzero(est["ponte"])
        for gr in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
            a, b = max(gr[0] - 2, 0), min(gr[-1] + 2, len(est["pontos"]) - 1)
            objs.append(_ponte(est["pontos"][a:b + 1], est["perfil"][a:b + 1], larg, madeira, g, H, f"ponte_{pontes}-col"))
            pontes += 1
    return objs, inimigos


def _vila(r, centro, rnd, mats, objs, R, larg):
    """Vila de verdade: praça com poço no meio e casas dos dois lados das ruas, de frente para elas."""
    raio = r["raio_m"]
    c2 = Vector((centro.x, centro.y))
    ruas = []  # trechos das estradas dentro da vila, em coordenadas do Blender (x, y)
    for e_ in R["estradas"]:
        if e_["pontos"] is None or r["id"] not in (e_["de"], e_["para"]):
            continue
        pts = [Vector((p_[0], -p_[1])) for p_ in e_["pontos"]]
        if e_["para"] == r["id"]:
            pts = pts[::-1]
        ruas.append([p_ for p_ in pts if (p_ - c2).length < raio * 0.9])
    casas = []

    def livre(pos, folga=9.5):
        if (pos - c2).length > raio * 0.82 or (pos - c2).length < 10.5:
            return False
        if any((pos - q).length < folga for q in casas):
            return False
        return all(min(((pos - q).length for q in rua), default=99) > larg / 2 + 3.6 for rua in ruas)

    def casa(pos, frente):
        i = len(casas)
        o = fc_armas.criar_objeto({"tipo": "casa", "id": f"{r['id']}_casa_{i}-col", "seed": rnd.randint(0, 9999),
                                   "cor_parede": mats["parede"], "cor_telhado": mats["telhado"]})
        o.location = (pos.x, pos.y, centro.z)
        o.rotation_euler.z = math.atan2(frente.y, frente.x) + math.pi / 2  # a porta (-Y) olha para a rua
        objs.append(o)
        casas.append(pos)
        if rnd.random() < 0.6:
            lado = Vector((-frente.y, frente.x)) * rnd.choice((-1, 1))
            tipo = rnd.choice(("barril", "caixa", "barril"))
            b = fc_armas.criar_objeto({"tipo": tipo, "id": f"{r['id']}_{tipo}_{i}-col"})
            p_ = pos + frente * 3.6 + lado * 3.8
            b.location = (p_.x, p_.y, centro.z)
            objs.append(b)

    for rua in ruas:
        for k in range(len(rua) - 1):
            a, b = rua[k], rua[k + 1]
            dist = (a - c2).length
            if k % 6 or dist < 11:
                continue
            tang = (b - a).normalized() if (b - a).length > 1e-6 else Vector((1, 0))
            for lado in (-1, 1):
                normal = Vector((-tang.y, tang.x)) * lado
                pos = a + normal * (larg / 2 + 6.0) + tang * rnd.uniform(-1.5, 1.5)
                if livre(pos):
                    casa(pos, -normal)
    alvo = max(6, int(raio / 5))
    for tentativa in range(80):
        if len(casas) >= alvo:
            break
        ang = rnd.uniform(0, math.tau)
        pos = c2 + Vector((math.cos(ang), math.sin(ang))) * rnd.uniform(13, raio * 0.78)
        if livre(pos):
            casa(pos, (c2 - pos).normalized())
    pedra = c.material("pedra_poco", c.cor_hex("#8a8578"), 0.9)
    k = c.Construtor()
    k.cilindro(centro, centro + Vector((0, 0, 0.9)), 1.0, 1.0, pedra, lados=12)
    objs.append(k.objeto(f"{r['id']}_poco-col"))
    for i in range(4):
        t = fc_armas.criar_objeto({"tipo": "tocha", "id": f"{r['id']}_tocha_{i}", "escala": 1.0})
        t.location = centro + Vector((math.cos(i * math.pi / 2 + 0.4) * 6.5, math.sin(i * math.pi / 2 + 0.4) * 6.5, 0))
        objs.append(t)


def _ponte(pts, perfil, larg, madeira, g, H, nome):
    """Ponte de verdade: tabuleiro contínuo com espessura, postes e corrimão dos dois lados, pilares no rio."""
    import bmesh

    lado = _lados(pts)
    w = larg / 2 + 0.3
    bm = bmesh.new()
    cima, baixo = [], []
    for k in range(len(pts)):
        for sinal in (1, -1):
            x, z = pts[k] + lado[k] * w * sinal
            cima.append(bm.verts.new((x, -z, perfil[k] + 0.05)))
            baixo.append(bm.verts.new((x, -z, perfil[k] - 0.4)))
    for k in range(len(pts) - 1):
        e0, d0, e1, d1 = 2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 3
        bm.faces.new((cima[e0], cima[e1], cima[d1], cima[d0]))
        bm.faces.new((baixo[e0], baixo[d0], baixo[d1], baixo[e1]))
        bm.faces.new((cima[e0], baixo[e0], baixo[e1], cima[e1]))
        bm.faces.new((cima[d0], cima[d1], baixo[d1], baixo[d0]))
    for e, d in ((0, 1), (2 * len(pts) - 2, 2 * len(pts) - 1)):
        bm.faces.new((cima[e], cima[d], baixo[d], baixo[e]))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    k_ = c.Construtor()
    k_.bm.free()
    k_.bm = bm
    k_._registrar(list(bm.verts), madeira, None)
    # postes a cada ~4 m e corrimão a 1 m do tabuleiro
    topo = []
    for k in range(0, len(pts), 2):
        for sinal in (1, -1):
            x, z = pts[k] + lado[k] * (w - 0.1) * sinal
            base = Vector((x, -z, perfil[k] + 0.05))
            k_.caixa(base + Vector((0, 0, 0.5)), (0.14, 0.14, 1.0), madeira)
            topo.append((sinal, k, base + Vector((0, 0, 1.0))))
    for sinal in (1, -1):
        lista = [t[2] for t in topo if t[0] == sinal]
        for p0, p1 in zip(lista[:-1], lista[1:]):
            vet = p1 - p0
            k_.caixa((p0 + p1) / 2, (0.09, vet.length + 0.08, 0.09), madeira, rot=vet.to_track_quat("Y", "Z"))
    # pilares até o fundo do rio no meio da ponte
    meio = len(pts) // 2
    for sinal in (1, -1):
        x, z = pts[meio] + lado[meio] * (w - 0.4) * sinal
        fundo = float(g.amostrar(H, x, z)) - 0.5
        alto = perfil[meio] - 0.4
        if alto - fundo > 0.3:
            k_.caixa(Vector((x, -z, (alto + fundo) / 2)), (0.35, 0.35, alto - fundo), madeira)
    return k_.objeto(nome)


# ---------------- imagens ----------------

def _salvar_png(caminho, rgba, dados=False):
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(os.path.basename(caminho), width=w, height=h, alpha=True)
    if dados:
        img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1], dtype=np.float32).ravel())
    img.filepath_raw = caminho
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return caminho


def _hex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def mapa_de_cima(caminho, P, R, cores_regioes):
    """O mapa visto de cima: chão pintado com sombra do relevo, água, estradas, árvores e as regiões."""
    g, H = R["g"], R["H"]
    paleta = np.stack([_hex(GRAMA_CLIMA[P["clima"]] if k == "grama" else CORES_CAMADAS[k]) for k in ("grama", "terra", "rocha", R["ultima"])])
    cor = R["camadas"] @ paleta
    dz, dx = np.gradient(H, g.res)
    nrm = np.stack([-dx, np.ones_like(H), -dz], axis=-1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    luz = np.array([-0.5, 0.75, -0.45])
    luz /= np.linalg.norm(luz)
    sombra = np.clip(nrm @ luz, 0, 1) * 0.75 + 0.35
    cor = np.clip(cor * sombra[..., None], 0, 1)
    prof = np.where(np.isfinite(R["prof_agua"]), R["prof_agua"], -1)
    agua = np.clip(prof / 1.5, 0, 1)[..., None] * (prof > 0)[..., None]
    cor = cor * (1 - agua * 0.85) + _hex("#2f6a8a") * agua * 0.85
    est = np.where(np.isfinite(R["d_estrada"]), R["d_estrada"], 1e6)
    borda_est = ((est > P["largura_estrada_m"] / 2 - 0.4) & (est < P["largura_estrada_m"] / 2 + 0.4))[..., None]
    cor = np.where(borda_est, cor * 0.6, cor)
    escala = 2
    img = np.kron(cor, np.ones((escala, escala, 1)))
    N = img.shape[0]

    def ponto(x, z, raio, rgb, anel=False):
        px, pz = g.indice(x, z)
        px, pz = px * escala, pz * escala
        r0, r1 = int(max(pz - raio - 1, 0)), int(min(pz + raio + 2, N))
        c0, c1 = int(max(px - raio - 1, 0)), int(min(px + raio + 2, N))
        if r0 >= r1 or c0 >= c1:
            return
        yy, xx = np.mgrid[r0:r1, c0:c1]
        d = np.hypot(yy - pz, xx - px)
        msk = (np.abs(d - raio) < 1.6) if anel else (d <= raio)
        img[r0:r1, c0:c1][msk] = rgb

    escuro = _hex("#1f3d1c")
    for a in R["arvores"]:
        ponto(a[1], a[3], 1.6 * a[5], escuro)
    for p_ in R["pedras"]:
        ponto(p_[1], p_[3], 0.9 * p_[5], _hex("#5f5c58"))
    for r in P["regioes"]:
        rgb = _hex(cores_regioes[r["id"]])
        ponto(r["centro"][0], r["centro"][1], r["raio_m"] / g.res * escala, rgb, anel=True)
        ponto(r["centro"][0], r["centro"][1], 5, rgb)
    sp = next(r for r in P["regioes"] if r["id"] == P["spawn"])
    ponto(sp["centro"][0], sp["centro"][1], 3, np.array([1.0, 1.0, 1.0]))
    rgba = np.concatenate([img, np.ones(img.shape[:2] + (1,))], axis=-1)
    return _salvar_png(caminho, rgba)


# ---------------- pontos de foto ----------------

def _subir_para_ver(g, H, a, b, folga=0.6):
    """Quanto a câmera em a precisa subir para ver b por cima do chão do meio."""
    k = np.linspace(0.04, 0.96, 48)
    xs, zs = a[0] + (b[0] - a[0]) * k, a[2] + (b[2] - a[2]) * k
    ys = a[1] + (b[1] - a[1]) * k
    falta = g.amostrar(H, xs, zs) + folga - ys
    return float(max(0.0, np.max(falta / (1 - k))))


def _pontos_de_foto(P, R, sp):
    """Uma foto de cada região, de quem chega pela estrada, na altura dos olhos (sobe só se o morro tapar)."""
    g, H = R["g"], R["H"]
    altura_em = lambda x, z: float(g.amostrar(H, x, z))  # noqa: E731
    lim = g.L / 2 * 0.9
    fotos = []
    for r in P["regioes"]:
        cx, cz = r["centro"]
        dist = min(r["raio_m"] * 1.25 + 8, g.L * 0.3)
        x = z = y_chao = None
        for e_ in R["estradas"]:
            if e_["pontos"] is None or r["id"] not in (e_["de"], e_["para"]):
                continue
            ordem = slice(None) if e_["para"] == r["id"] else slice(None, None, -1)
            if r["id"] == sp["id"]:  # o ponto inicial: de fora, voltando pela primeira estrada
                ordem = slice(None, None, -1) if e_["de"] == r["id"] else slice(None)
            pts, perfil = e_["pontos"][ordem], e_["perfil"][ordem]
            d = np.hypot(pts[:, 0] - cx, pts[:, 1] - cz)
            fora = np.flatnonzero((d >= dist) & ~e_["ponte"][ordem])
            if len(fora):
                i = fora[-1]
                x, z, y_chao = float(pts[i, 0]), float(pts[i, 1]), float(perfil[i])
                break
        if x is None:
            ida = Vector((sp["centro"][0] - cx, sp["centro"][1] - cz))
            ida = ida.normalized() if ida.length > 1e-3 else Vector((0.0, 1.0))
            x, z = cx + ida.x * dist, cz + ida.y * dist
        x, z = max(-lim, min(lim, x)), max(-lim, min(lim, z))
        alvo = [cx, altura_em(cx, cz) + (4.0 if KIT.get(r["tipo"]) else 1.5), cz]
        pos = [x, (y_chao if y_chao is not None else altura_em(x, z)) + 1.7, z]
        pos[1] += min(_subir_para_ver(g, H, pos, alvo, folga=2.0), 25.0)
        fotos.append({"id": r["id"], "pos": [round(v, 2) for v in pos], "olha": [round(v, 2) for v in alvo]})
    return fotos


# ---------------- tarefa ----------------

CORES_REGIAO = ["#e8c547", "#e8743b", "#c44f9d", "#4fa3e8", "#9de84f", "#e84f4f", "#4fe8c8", "#b07be8"]


def tarefa(t):
    pasta = t["saida"]
    os.makedirs(pasta, exist_ok=True)
    P, avisos = normalizar(t.get("plano"), t.get("areas"))
    paleta = t.get("paleta") or []
    R = gerar(P, paleta)
    medidas = medir(P, R)
    g, H = R["g"], R["H"]
    arquivos = {}
    # dados para a engine (e para o terreno nativo da Erethea / Terrain3D)
    H.astype("<f4").tofile(os.path.join(pasta, "relevo.r32"))
    hmin, hmax = float(H.min()), float(H.max())
    ((H - hmin) / max(hmax - hmin, 1e-6) * 65535).round().astype("<u2").tofile(os.path.join(pasta, "relevo.r16"))
    arquivos["relevo"] = os.path.join(pasta, "relevo.r32")
    arquivos["pintura"] = _salvar_png(os.path.join(pasta, "pintura.png"), R["camadas"].astype(np.float32), dados=True)
    cores_regioes = {r["id"]: CORES_REGIAO[i % len(CORES_REGIAO)] for i, r in enumerate(P["regioes"])}
    arquivos["mapa"] = mapa_de_cima(os.path.join(pasta, "mapa.png"), P, R, cores_regioes)
    # malhas
    terreno = _malha_terreno(g, H, R["camadas"], R["ultima"])
    longe = _terreno_longe(g, H, P["relevo"]["altura_m"], P["seed"])
    c.exportar_glb(os.path.join(pasta, "terreno.glb"), terreno + [longe], animacoes=False, imagens="JPEG")
    arquivos["terreno"] = os.path.join(pasta, "terreno.glb")
    agua = _agua(R)
    if agua:
        c.exportar_glb(os.path.join(pasta, "agua.glb"), agua, animacoes=False, imagens="JPEG")
        arquivos["agua"] = os.path.join(pasta, "agua.glb")
    estruturas, inimigos = _estruturas(P, R, paleta)
    if estruturas:
        c.exportar_glb(os.path.join(pasta, "estruturas.glb"), estruturas, animacoes=False, imagens="JPEG")
        arquivos["estruturas"] = os.path.join(pasta, "estruturas.glb")
    variantes = _variantes(P, paleta)
    # toda a vegetação num GLB só (as texturas vão uma vez); cada variante é um nó com o nome dela
    todas = [o for lista in variantes.values() for o in lista]
    c.exportar_glb(os.path.join(pasta, "vegetacao.glb"), todas, animacoes=False, imagens="JPEG")
    arquivos["vegetacao"] = os.path.join(pasta, "vegetacao.glb")
    tipos = {nome: [f"vegetacao.glb#{o.name}" for o in lista] for nome, lista in variantes.items()}
    G = lambda v: [round(float(v[0]), 3), round(float(v[2]), 3), round(float(-v[1]), 3)]  # noqa: E731  Blender -> engine
    arred = lambda a: [[int(x[0])] + [round(float(v), 3) for v in x[1:]] for x in a]  # noqa: E731
    with open(os.path.join(pasta, "espalhamento.json"), "w", encoding="utf-8") as f:
        json.dump({"formato": ["variante", "x", "y", "z", "giro_y", "escala"], "tipos": tipos,
                   "instancias": {"arvore": arred(R["arvores"]), "arbusto": arred(R["arbustos"]), "pedra": arred(R["pedras"])}}, f)
    arquivos["espalhamento"] = os.path.join(pasta, "espalhamento.json")
    # luz, regiões, pontos de foto
    elev, cor_sol, energia, topo, horizonte, cor_nevoa = LUZ[P["hora"]]
    luz = {"sol_elevacao": elev, "sol_azimute": P["sol_azimute"], "sol_cor": cor_sol, "sol_energia": energia, "ceu_topo": topo,
           "ceu_horizonte": horizonte, "nevoa_cor": cor_nevoa,
           "nevoa_densidade": round(0.0003 + 0.0035 * P["nevoa"] * NEVOA_CLIMA[P["clima"]], 5), "nevoa_altura": round(hmin + 6.0, 2)}
    altura_em = lambda x, z: float(g.amostrar(H, x, z))  # noqa: E731
    regioes = [dict(r, centro=[r["centro"][0], round(altura_em(*r["centro"]), 3), r["centro"][1]], cor=cores_regioes[r["id"]])
               for r in P["regioes"]]
    sp = next(r for r in P["regioes"] if r["id"] == P["spawn"])
    fotos = _pontos_de_foto(P, R, sp)
    fotos.append({"id": "vista_alta", "pos": [round(-g.L * 0.42, 2), round(hmax + g.L * 0.12, 2), round(g.L * 0.42, 2)],
                  "olha": [0.0, round(float(np.median(H)), 2), 0.0]})
    sx, sz = sp["centro"]
    est0 = next((e for e in R["estradas"] if e["pontos"] is not None and e["de"] == sp["id"]), None)
    if est0 is not None:
        k = min(len(est0["pontos"]) - 1, int(sp["raio_m"] * 0.6 / 2.0) + 2)
        sx, sz = float(est0["pontos"][k][0]), float(est0["pontos"][k][1])
    spawn_jogador = [round(sx, 3), round(altura_em(sx, sz) + 0.2, 3), round(sz, 3)]
    info = {
        "versao": 1, "tamanho_m": g.L, "resolucao_m": g.res, "pontos_por_lado": g.n, "altura_min": round(hmin, 3),
        "altura_max": round(hmax, 3), "camadas": ["grama", "terra", "rocha", R["ultima"]], "clima": P["clima"], "hora": P["hora"],
        "cores_camadas": {k: (GRAMA_CLIMA.get(P["clima"], CORES_CAMADAS[k]) if k == "grama" else CORES_CAMADAS[k])
                          for k in ("grama", "terra", "rocha", R["ultima"])},
        "luz": luz, "regioes": regioes,
        "rios": [{"largura_m": r_["largura_m"], "pontos": [[round(float(p_[0]), 2), round(float(nv), 2), round(float(p_[1]), 2)]
                                                         for p_, nv in zip(r_["pontos"][::4], r_["nivel"][::4])]} for r_ in R["rios"]],
        "lagos": [{"id": lg["id"], "centro": [lg["centro"][0], round(lg["nivel"], 2), lg["centro"][1]], "raio_m": lg["raio_m"]} for lg in R["lagos"]],
        "estradas": [{"de": e_["de"], "para": e_["para"], "largura_m": P["largura_estrada_m"],
                      "pontes": int(e_["ponte"].any()) if e_["pontos"] is not None else 0,
                      "pontos": None if e_["pontos"] is None else [[round(float(p_[0]), 2), round(float(h_), 2), round(float(p_[1]), 2)]
                                                                    for p_, h_ in zip(e_["pontos"][::3], e_["perfil"][::3])]}
                     for e_ in R["estradas"]],
        "arquivos": {"relevo_r32": "relevo.r32", "relevo_r16": "relevo.r16", "pintura": "pintura.png", "terreno": "terreno.glb",
                     "agua": "agua.glb" if agua else "", "estruturas": "estruturas.glb" if estruturas else "",
                     "espalhamento": "espalhamento.json"},
        "spawn_jogador": spawn_jogador, "spawn_inimigos": [G(v) for v in inimigos], "fotos": fotos, "medidas": medidas,
        "plano": P, "avisos": avisos,
    }
    with open(os.path.join(pasta, "mapa.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    arquivos["info"] = os.path.join(pasta, "mapa.json")
    st = {"arvores": len(R["arvores"]), "arbustos": len(R["arbustos"]), "pedras": len(R["pedras"]),
          "triangulos_terreno": sum(len(o.data.polygons) * 2 for o in terreno), "pontes": sum(1 for o in estruturas if o.name.startswith("ponte")),
          "segundos_gerando": R["segundos"], "altura_min": round(hmin, 2), "altura_max": round(hmax, 2)}
    if t.get("fotos", True):
        arquivos.update(fotos_blender(pasta, P, R, terreno, agua, estruturas, variantes, info, int(t.get("amostras", 12))))
    return {"arquivos": arquivos, "estatisticas": st, "medidas": medidas, "avisos": avisos, "plano": P,
            "regioes": regioes, "spawn_jogador": spawn_jogador, "fotos": fotos}


def fotos_blender(pasta, P, R, terreno, agua, estruturas, variantes, info, amostras):
    """Duas fotos para a IA olhar antes da engine: a vista alta e a chegada pela estrada."""
    cena = bpy.context.scene
    c._preparar_render(960, 540, amostras)
    # chão com a cor das camadas; vegetação por instâncias (cópias ligadas: leve para o Cycles)
    mat = bpy.data.materials.get("terreno")
    if mat is not None and mat.use_nodes:
        nos = mat.node_tree.nodes
        bsdf = next((x for x in nos if x.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            at = nos.new("ShaderNodeVertexColor")
            at.layer_name = "Col"
            mat.node_tree.links.new(at.outputs["Color"], bsdf.inputs["Base Color"])
    col = bpy.data.collections.new("vegetacao_fotos")
    cena.collection.children.link(col)
    for nome, arr in (("arvore", R["arvores"]), ("arbusto", R["arbustos"]), ("pedra", R["pedras"])):
        base = variantes[nome]
        for v, x, y, z, rot, esc in arr:
            o = bpy.data.objects.new(f"i_{nome}", base[int(v)].data)
            o.location = (x, -z, y)
            o.rotation_euler = (0, 0, rot)
            o.scale = (esc, esc, esc)
            col.objects.link(o)
    for lista in variantes.values():
        for o in lista:
            o.hide_render = True
    mundo = cena.world
    luz = info["luz"]
    try:
        arv = mundo.node_tree
        fundo = next(x for x in arv.nodes if x.type == "BACKGROUND")
        for l_ in list(arv.links):
            if l_.to_node == fundo:
                arv.links.remove(l_)
        ceu = arv.nodes.new("ShaderNodeTexSky")
        ceu.sky_type = "MULTIPLE_SCATTERING"
        ceu.sun_disc = False
        ceu.sun_elevation = math.radians(max(luz["sol_elevacao"], 2))
        ceu.sun_rotation = math.radians(luz["sol_azimute"])
        ceu.ground_albedo = 0.6
        arv.links.new(ceu.outputs["Color"], fundo.inputs[0])
        fundo.inputs[1].default_value = 0.3 if P["hora"] != "noite" else 0.02
        saida = next(x for x in arv.nodes if x.type == "OUTPUT_WORLD")
        arv.links.new(fundo.outputs[0], saida.inputs["Surface"])
    except Exception:
        pass
    k = c.Construtor()
    k.caixa((0, 0, info["altura_min"] - 1.5), (R["g"].L * 8, R["g"].L * 8, 0.5), c.material("chao_longe", c.cor_hex("#6f7d5a"), 1.0))
    k.objeto("chao_longe")
    sol_d = bpy.data.lights.new("sol_mapa", "SUN")
    sol_d.energy = 4.0 * luz["sol_energia"]
    sol_d.color = c.cor_hex(luz["sol_cor"])
    sol_d.angle = math.radians(1.5)
    sol = bpy.data.objects.new("sol_mapa", sol_d)
    cena.collection.objects.link(sol)
    sol.rotation_euler = (math.radians(90 - luz["sol_elevacao"]), 0, math.radians(luz["sol_azimute"]))
    cam = cena.camera or c._camera()
    cena.camera = cam
    cam.data.type = "PERSP"
    cam.data.clip_end = R["g"].L * 3
    saidas = {}
    for ft in info["fotos"]:
        if ft["id"] not in ("vista_alta", P["spawn"]):
            continue
        pos, olha = Vector((ft["pos"][0], -ft["pos"][2], ft["pos"][1])), Vector((ft["olha"][0], -ft["olha"][2], ft["olha"][1]))
        cam.location = pos
        cam.rotation_euler = (olha - pos).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = 24 if ft["id"] == "vista_alta" else 28
        nome = "vista_alta" if ft["id"] == "vista_alta" else "vista_chegada"
        cena.render.filepath = os.path.join(pasta, f"{nome}.png")
        bpy.ops.render.render(write_still=True)
        saidas[nome] = cena.render.filepath
    return saidas
