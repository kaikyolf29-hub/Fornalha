# Fornalha: esqueleto de dragão encaixado numa malha de fora — a do 3D pela IA (TRELLIS.2), numa peça só,
# de frente para -Y, asas abertas. Os pontos saem da própria malha: pés (fatia do chão), quadril, raiz das
# asas (onde a membrana encosta no corpo), focinho, topo da cabeça, ponta da cauda, pulso da asa (topo) e
# as pontas dos dedos (os picos mais longe do pulso). Os ossos e as animações são os do dragão da Fornalha
# (fc_criatura): as rotações são no espaço do mundo, então valem para outra pose de descanso.
import math

import bpy
import numpy as np
from mathutils import Vector

import fc_criatura as fcc
import fc_rig_ia


def _co(obj):
    m = obj.matrix_world
    return np.array([(m @ v.co)[:] for v in obj.data.vertices])


def _nucleo(co, z0, z1, W):
    """Meia largura do corpo numa faixa de altura: até o primeiro vão em |x| (separa a asa do corpo)."""
    f = co[(co[:, 2] >= z0) & (co[:, 2] < z1)]
    if not len(f):
        return 0.0
    xs = np.sort(np.abs(f[:, 0]))
    vaos = np.where(np.diff(xs) > 0.02 * W)[0]
    return float(xs[vaos[0]] if len(vaos) else xs[-1])


def _grupos_1d(v, vao):
    """Agrupa valores ordenados quando o vão entre vizinhos passa de `vao`. Devolve listas de índices."""
    ordem = np.argsort(v)
    grupos, atual = [], [ordem[0]]
    for a, b in zip(ordem[:-1], ordem[1:]):
        if v[b] - v[a] > vao:
            grupos.append(atual)
            atual = []
        atual.append(b)
    grupos.append(atual)
    return grupos


def medir(obj):
    """Pontos do esqueleto do dragão (metros; z para cima, frente em -Y). Devolve (Dragao, info)."""
    co = _co(obj)
    mn, mx = co.min(0), co.max(0)
    W, L, H = (mx - mn).tolist()
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    d = fcc.Dragao(1.0)

    # --- pés: a fatia do chão, por lado; o grupo maior de cada lado é a pata (a ponta da cauda no chão é menor)
    chao = z < 0.03 * H
    patas_tras, patas_frente = {}, {}
    for lado, s in (("l", 1), ("r", -1)):
        m = np.where(chao & (s * x > 0.02 * W))[0]
        if not len(m):
            m = np.where(chao)[0]
        grupos = sorted(_grupos_1d(y[m], 0.05 * L), key=len, reverse=True)
        principal = m[grupos[0]]
        patas_tras[lado] = principal
        # quadrúpede: outro grupo grande à frente da pata principal
        for g in grupos[1:]:
            gi = m[g]
            if len(gi) > 0.3 * len(principal) and y[gi].mean() < y[principal].mean() - 0.08 * L:
                patas_frente[lado] = gi
            elif len(gi) > 0.3 * len(principal) and y[gi].mean() > y[principal].mean() + 0.08 * L:
                patas_frente[lado], patas_tras[lado] = principal, gi
                principal = gi
    quadrupede = len(patas_frente) == 2

    # --- raiz das asas: o ponto mais alto onde a membrana encosta no corpo (núcleo largo)
    faixas = np.arange(0.2, 0.95, 0.025) * H
    larg = [_nucleo(co, a, a + 0.025 * H, W) for a in faixas]
    largas = [k for k, w in enumerate(larg) if w > 0.2 * W]
    if largas:
        k_topo = max(largas)
        k_base = min(largas)
        z_raiz = float(faixas[k_topo]) - 0.02 * H
        corpo_meia = max(0.03 * W, larg[max(0, k_base - 2)] * 0.8)
    else:  # asas que não encostam no corpo nas fatias: ombro a 60% da altura
        z_raiz = 0.6 * H
        corpo_meia = 0.06 * W
    rx = min(corpo_meia, 0.09 * W)
    f = co[(np.abs(z - z_raiz) < 0.04 * H) & (np.abs(x) < rx)]
    y_raiz = float(np.median(f[:, 1])) + 0.02 * L if len(f) else 0.0

    # --- quadril: entre as patas de trás, a ~58% da altura do ombro
    pes = np.concatenate([patas_tras["l"], patas_tras["r"]])
    pe_y = float(y[pes].mean())
    z_quad = 0.58 * z_raiz
    f = co[(np.abs(z - z_quad) < 0.04 * H) & (np.abs(x) < 0.06 * W) & (y < y[pes].max() + 0.1 * L)]
    y_quad = float(np.median(f[:, 1])) if len(f) else pe_y + 0.05 * L

    # --- cabeça: focinho (o ponto mais à frente acima dos ombros) e o topo do crânio
    acima = (z > z_raiz) & (np.abs(x) < 0.05 * W)
    i_foc = np.where(acima)[0][np.argmin(y[acima])]
    focinho = Vector(co[i_foc])
    centro = acima & (np.abs(x) < 0.03 * W)
    z_topo = float(z[centro].max())
    f = co[centro & (z > z_topo - 0.1 * H)]
    y_topo = float(np.median(f[:, 1]))
    base_cab = Vector((0.0, y_topo, z_topo - 0.12 * H))
    # a base não pode ficar à frente do focinho nem abaixo dele demais
    if (focinho - base_cab).length < 0.1 * H:
        base_cab = focinho + Vector((0, 0.18 * H, 0.06 * H))
    peito = Vector((0.0, y_raiz - 0.01 * L, z_raiz + 0.02 * H))

    # --- cauda: ponta = o ponto mais atrás; o meio pelas fatias em y (centro do que está abaixo do quadril)
    i_ponta = int(np.argmax(y))
    ponta = Vector(co[i_ponta])
    quadril = Vector((0.0, y_quad, z_quad))
    cauda = [quadril.copy()]
    baixo = (z < z_quad + 0.12 * H) & (np.abs(x) < 0.2 * W)
    for k in range(1, 11):
        t = k / 10
        yc = y_quad + (ponta.y - y_quad) * t
        f = co[baixo & (np.abs(y - yc) < 0.02 * L)]
        if k == 10 or len(f) < 5:
            p = quadril.lerp(ponta, t) if k < 10 else ponta
        else:
            # só a parte de baixo da fatia: a ponta enrolada e os espinhos das costas não puxam o meio
            f = f[f[:, 2] < f[:, 2].min() + 0.1 * H]
            p = Vector((float(np.median(f[:, 0])), yc, float(np.median(f[:, 2]))))
        cauda.append(p)

    # --- coluna (quadril → peito, num arco leve para a frente) e pescoço (peito → base da cabeça)
    def arco(a, b, n, frente):
        pts = []
        for k in range(n):
            t = k / (n - 1)
            p = a.lerp(b, t)
            p.y -= frente * math.sin(math.pi * t)
            pts.append(p)
        return pts

    d.coluna = arco(quadril, peito, 5, 0.02 * L)
    d.pescoco = arco(peito, base_cab, 6, 0.03 * L)
    d.cabeca = [base_cab, focinho]
    eixo = focinho - base_cab
    cima = Vector((0, 0, 1))
    hl = eixo.length
    d.jaw = [base_cab + eixo * 0.11 - cima * 0.16 * hl, focinho - eixo * 0.11 - cima * 0.2 * hl]
    d.cauda = cauda

    # --- pernas de trás: pé medido; joelho e jarrete nas proporções do dragão da Fornalha
    for lado, s in (("l", 1), ("r", -1)):
        p = co[patas_tras[lado]]
        fx = float(np.median(p[:, 0]))
        y0, y1 = float(p[:, 1].min()), float(p[:, 1].max())
        bola = Vector((fx, (y0 + y1) / 2, 0.03 * H))
        dedo = Vector((fx, y0, 0.02 * H))
        quad = Vector((s * max(abs(fx) * 0.75, 0.03 * W), y_quad, z_quad - 0.02 * H))
        h = quad.z - bola.z
        joelho = Vector((s * abs(fx) * 1.05, quad.y - 0.3 * h, quad.z - 0.38 * h))
        jarrete = Vector((fx, bola.y + 0.29 * h * 0.6, bola.z + 0.25 * h))
        d.perna_tras[lado] = [quad, joelho, jarrete, bola, dedo]
        if quadrupede:
            pf = co[patas_frente[lado]]
            fxf = float(np.median(pf[:, 0]))
            yf0, yf1 = float(pf[:, 1].min()), float(pf[:, 1].max())
            ombro = Vector((s * rx * 0.9, peito.y + 0.02 * L, z_raiz - 0.08 * H))
            hf = ombro.z
            d.perna_frente[lado] = [ombro, Vector((s * abs(fxf), ombro.y + 0.15 * hf, ombro.z - 0.4 * hf)),
                                    Vector((fxf, (yf0 + yf1) / 2 + 0.1 * hf, 0.12 * hf)), Vector((fxf, (yf0 + yf1) / 2, 0.02 * H)),
                                    Vector((fxf, yf0, 0.01 * H))]
        else:
            # sem patas da frente (serpe): bracinhos recolhidos dentro do peito, sem peso na malha
            o = peito + Vector((s * rx * 0.5, -0.01 * L, -0.06 * H))
            passo = 0.015 * H
            d.perna_frente[lado] = [o, o + Vector((0, 0, -passo)), o + Vector((0, 0, -2 * passo)), o + Vector((0, 0, -3 * passo)),
                                    o + Vector((0, -passo, -3 * passo))]

    # --- asas: raiz no ombro, pulso no topo da asa, dedos nos picos mais longe do pulso
    for lado, s in (("l", 1), ("r", -1)):
        raiz = Vector((s * rx, y_raiz, z_raiz))
        asa_m = (s * x > rx + 0.04 * W) & (z > 0.2 * H)
        if asa_m.sum() < 50:
            continue
        pa = co[asa_m]
        z_max = pa[:, 2].max()
        topo = pa[pa[:, 2] > z_max - 0.05 * H]
        pulso = Vector(topo.mean(0))
        v = pa - np.array(pulso)
        ang = np.degrees(np.arctan2(v[:, 2], s * v[:, 0]))
        dist = np.linalg.norm(v, axis=1)
        bins = np.floor((ang + 180) / 3).astype(int)
        melhor = {}
        for i in np.argsort(dist):
            melhor[bins[i]] = i  # o mais longe de cada faixa de ângulo fica por último
        chaves = sorted(melhor)
        dist_b = np.array([dist[melhor[b]] for b in chaves])
        picos = []
        for k, b in enumerate(chaves):
            viz = [dist_b[j] for j in range(len(chaves)) if abs(chaves[j] - b) <= 4 and j != k]
            if not viz or dist_b[k] >= max(viz):
                picos.append((dist_b[k], b))
        picos.sort(reverse=True)
        escolhidos = []
        for dd, b in picos:
            if dd < 0.25 * max(p[0] for p in picos):
                continue
            if all(abs(b - e) >= 5 for _, e in escolhidos):
                escolhidos.append((dd, b))
            if len(escolhidos) == 3:
                break
        pontas = [Vector(pa[melhor[b]]) for _, b in escolhidos]
        while len(pontas) < 3:
            pontas.append(pulso + (pontas[-1] - pulso) * 0.8 if pontas else pulso + Vector((s * 0.2 * W, 0.05 * L, -0.2 * H)))
        pontas.sort(key=lambda p: -s * p.x)
        cotovelo = raiz.lerp(pulso, 0.42) + Vector((0, 0.04 * L, -0.02 * H))
        d.asa[lado] = {"raiz": raiz, "cotovelo": cotovelo, "pulso": pulso, "dedos": pontas, "costas": raiz + Vector((0, 0.1 * L, -0.1 * H))}

    info = {"quadrupede": quadrupede, "altura_m": round(H, 3), "envergadura_m": round(W, 3), "comprimento_m": round(L, 3)}
    return d, info


def _seg(co, a, b):
    ab = b - a
    t = np.clip(((co - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(co - (a + t[:, None] * ab), axis=1)


def pesos(obj, arm, d, quadrupede):
    """Pesos por regiões: asa só nos ossos da asa (o peito só perto da raiz), pernas só na perna,
    cauda só na cauda, cabeça e mandíbula só na cabeça; dentro de cada região, o inverso da distância."""
    co = _co(obj)
    mn, mx = co.min(0), co.max(0)
    W, L, H = (mx - mn).tolist()
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    ossos = [b for b in arm.data.bones if b.name != "raiz"]
    nomes = [b.name for b in ossos]
    idx = {n: i for i, n in enumerate(nomes)}
    mw = arm.matrix_world
    dist = np.stack([_seg(co, np.array(mw @ b.head_local), np.array(mw @ b.tail_local)) for b in ossos], axis=1)
    pode = np.zeros_like(dist, dtype=bool)

    def liberar(mask, grupo):
        cols = [idx[n] for n in grupo if n in idx]
        pode[np.ix_(np.where(mask)[0], cols)] = True

    tronco = ["quadril"] + [f"coluna_{k}" for k in range(1, 5)]
    pescoco = [f"pescoco_{k}" for k in range(1, 6)]
    cauda = [f"cauda_{k}" for k in range(1, 11)]
    raiz_l = d.asa["l"]["raiz"]
    rx = abs(raiz_l.x)
    z_quad = d.coluna[0].z
    y_quad = d.coluna[0].y
    z_raiz = raiz_l.z
    restante = np.ones(len(co), dtype=bool)
    for lado, s in (("l", 1), ("r", -1)):
        asa = [f"asa_umero_{lado}", f"asa_antebraco_{lado}"] + [f"asa_dedo_{k}_{lado}" for k in (1, 2, 3)]
        m_asa = (s * x > rx + 0.02 * W) & (z > 0.2 * H) & ~((z < z_quad + 0.05 * H) & (s * x < 0.16 * W))
        liberar(m_asa, asa + ["coluna_4"])
        restante &= ~m_asa
        pe = d.perna_tras[lado]
        perna = [f"coxa_{lado}", f"canela_{lado}", f"tarso_{lado}", f"dedos_pe_{lado}"]
        y_pe0 = min(p.y for p in pe) - 0.04 * L
        y_pe1 = max(p.y for p in pe) + 0.06 * L
        m_perna = restante & (z < z_quad + 0.02 * H) & (s * x > 0.012 * W) & (y > y_pe0) & (y < y_pe1)
        liberar(m_perna, perna + ["quadril", "coluna_1"])
        restante &= ~m_perna
        if quadrupede:
            pf = d.perna_frente[lado]
            braco = [f"ombro_{lado}", f"antebraco_{lado}", f"mao_{lado}", f"garras_{lado}"]
            m_braco = restante & (z < pf[0].z) & (s * x > 0.012 * W) & (y < min(p.y for p in pf) + 0.25 * L) & (y < y_pe0)
            liberar(m_braco, braco + ["coluna_4", "coluna_3"])
            restante &= ~m_braco
    # cauda: atrás do quadril e abaixo dele
    m_cauda = restante & (y > y_quad + 0.04 * L) & (z < z_quad + 0.1 * H)
    liberar(m_cauda, cauda + ["quadril"])
    restante &= ~m_cauda
    # cabeça e mandíbula: acima do pescoço; mandíbula abaixo da linha da boca
    base, foc = d.cabeca
    eixo = foc - base
    m_cab = restante & (z > z_raiz + 0.05 * H) & (_seg(co, np.array(base), np.array(foc)) < 0.6 * eixo.length)
    j0, j1 = d.jaw
    # linha da boca: do canto (um pouco acima do começo da mandíbula) até logo acima da ponta dela
    canto = j0 + (base - j0) * 0.35
    ponta_boca = j1 + (foc - j1) * 0.45
    t = np.clip(((co - np.array(canto)) @ np.array(ponta_boca - canto)) / max((ponta_boca - canto).length_squared, 1e-9), 0, 1)
    z_linha = canto.z + t * (ponta_boca.z - canto.z)
    frente_do_canto = ((co - np.array(canto)) @ np.array(eixo.normalized())) > 0
    m_jaw = m_cab & (z < z_linha) & frente_do_canto
    liberar(m_jaw, ["jaw"])
    liberar(m_cab & ~m_jaw, ["cabeca", "pescoco_5"])
    restante &= ~m_cab
    # pescoço e tronco: o resto
    m_pesc = restante & (z > z_raiz - 0.02 * H)
    liberar(m_pesc, pescoco + ["cabeca", "coluna_4"])
    liberar(restante & ~m_pesc, tronco + ["pescoco_1", "cauda_1"])

    d2 = np.where(pode, dist, np.inf)
    sem = ~np.isfinite(d2).any(axis=1)
    d2[sem] = dist[sem]
    ordem = np.argsort(d2, axis=1)[:, :3]
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    grupos = {n: obj.vertex_groups.new(name=n) for n in nomes}
    eps = 0.01 * H
    for vi in range(len(co)):
        ids = ordem[vi]
        dd = d2[vi, ids]
        ok = np.isfinite(dd)
        ids, dd = ids[ok], dd[ok]
        w = 1.0 / (dd + eps) ** 4
        w /= w.sum()
        for k, peso in zip(ids, w):
            if peso > 0.01:
                grupos[nomes[k]].add([vi], float(peso), "REPLACE")
    # fronteiras alisadas (sem rasgos entre regiões) e soma 1
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    try:
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=2)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    obj.parent = arm
    mod = obj.modifiers.new("esqueleto", "ARMATURE")
    mod.object = arm


def _elevacao(raiz, pulso):
    v = pulso - raiz
    return math.degrees(math.atan2(v.z, math.hypot(v.x, v.y)))


def rigar(obj, nome, altura=5.0):
    """Malha de dragão da IA → (armadura, ações, info). `altura` é a altura total (com as asas)."""
    fc_rig_ia.normalizar(obj, altura)
    d, info = medir(obj)
    arm = d.esqueleto(nome)
    pesos(obj, arm, d, info["quadrupede"])
    # a asa da IA vem erguida: o bater das asas é centrado como o do dragão da Fornalha (~18° acima)
    base = 18.0 - _elevacao(d.asa["l"]["raiz"], d.asa["l"]["pulso"])
    escala = altura / 4.6
    acoes = fcc.AnimadorDragao(arm, escala, dragao=d, abrir_base=base).tudo()
    # andar e correr com o pé no chão (IK de dois ossos, a mesma passada das criaturas de patas): as
    # asas, o pescoço e a cauda ficam como o animador do dragão fez
    import fc_rig_generico

    patas = [[f"coxa_{l}", f"canela_{l}", f"tarso_{l}"] for l in ("l", "r")]
    if info["quadrupede"]:
        patas += [[f"ombro_{l}", f"antebraco_{l}", f"mao_{l}"] for l in ("l", "r")]
    for a in acoes:
        if a.name in ("andar", "correr"):
            ini, fim = (int(round(x)) for x in a.frame_range)
            fc_rig_generico.passada_com_ik(arm, a, patas, a.name == "correr", fim)
    arm.animation_data.action = acoes[0]
    info.update({"pesos": "regioes", "ossos": len(arm.data.bones), "abrir_base_graus": round(base, 1)})
    return arm, acoes, info
