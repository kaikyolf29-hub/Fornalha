# Fornalha: esqueleto de jogo (nomes do padrão Unreal, os mesmos do humano da Fornalha) encaixado numa
# malha humanoide de fora — a do 3D pela IA (TRELLIS.2), que vem numa peça só, de pé, de frente para -Y.
# Os pontos das juntas saem das proporções do corpo medidas na própria malha (altura, onde estão as mãos,
# a largura dos ombros e o centro do tronco em cada altura). Assim a mesma captura de movimento do
# humano (Quaternius, CC0) roda nela: a retargetagem alinha a pose de descanso dela à da captura.
import bpy
import numpy as np
from mathutils import Vector

# hierarquia: (osso, pai)
HIERARQUIA = [
    ("pelvis", None), ("spine_01", "pelvis"), ("spine_02", "spine_01"), ("spine_03", "spine_02"),
    ("neck_01", "spine_03"), ("head", "neck_01"),
    ("clavicle_l", "spine_03"), ("upperarm_l", "clavicle_l"), ("lowerarm_l", "upperarm_l"), ("hand_l", "lowerarm_l"),
    ("clavicle_r", "spine_03"), ("upperarm_r", "clavicle_r"), ("lowerarm_r", "upperarm_r"), ("hand_r", "lowerarm_r"),
    ("thigh_l", "pelvis"), ("calf_l", "thigh_l"), ("foot_l", "calf_l"), ("ball_l", "foot_l"),
    ("thigh_r", "pelvis"), ("calf_r", "thigh_r"), ("foot_r", "calf_r"), ("ball_r", "foot_r"),
]


# o campo de distância da última malha medida (os pesos do braço usam o mesmo volume)
ULTIMO = {"campo": None}


def _vertices(obj):
    m = obj.matrix_world
    return np.array([(m @ v.co)[:] for v in obj.data.vertices])


def normalizar(obj, altura):
    """Pés no chão (z = 0), centro em x/y = 0 e a altura pedida (a malha da IA vem com ~1 m)."""
    co = _vertices(obj)
    mn, mx = co.min(0), co.max(0)
    esc = altura / max(mx[2] - mn[2], 1e-6)
    obj.scale = obj.scale * esc
    bpy.context.view_layer.update()
    co = _vertices(obj)
    mn, mx = co.min(0), co.max(0)
    obj.location = obj.location - Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, mn[2]))
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def medir(obj):
    """Pontos das juntas (em metros, z para cima, frente em -Y) pelas proporções medidas na malha."""
    co = _vertices(obj)
    H = float(co[:, 2].max())

    def faixa(z0, z1):
        return co[(co[:, 2] >= z0 * H) & (co[:, 2] <= z1 * H)]

    def centro_y(z0, z1):
        f = faixa(z0, z1)
        f = f[np.abs(f[:, 0]) < 0.06 * H] if len(f) else f
        return float(np.median(f[:, 1])) if len(f) else 0.0

    # ponta da mão: o braço é seguido do peito para baixo, fatia por fatia, enquanto é um grupo de
    # vértices separado do corpo (o grupo mais de fora, com vão para o resto); a última fatia é a ponta
    # dos dedos. Só a metade da frente: a capa pendurada atrás pode ser mais larga que as mãos.
    cab = faixa(0.88, 0.97)
    y_meio = (float(cab[:, 1].min()) + float(cab[:, 1].max())) / 2 if len(cab) else 0.0
    pontas = {}
    trilhas = {}
    for lado, s in (("l", 1.0), ("r", -1.0)):
        trilha = []
        for zf in np.arange(0.70, 0.28, -0.008):
            f = co[(np.abs(co[:, 2] - zf * H) < 0.005 * H) & (co[:, 1] < y_meio + 0.06 * H) & (co[:, 0] * s > 0.04 * H)]
            if len(f) < 4:
                break
            xs = np.sort(f[:, 0] * s)[::-1]
            vaos = np.where(-np.diff(xs) > 0.012 * H)[0]
            if not len(vaos):
                break  # o braço encostou no corpo (ou acabou)
            limite = xs[vaos[0]]
            g = f[f[:, 0] * s >= limite - 1e-6]
            c = g.mean(0)
            if trilha and np.linalg.norm(c[:2] - trilha[-1][:2]) > 0.06 * H:
                break
            trilha.append(np.array([c[0], c[1], zf * H]))
        pontas[lado] = trilha[-1] if trilha else None
        trilhas[lado] = trilha
    # o centro do braço pelo campo de distância da malha (segue o antebraço dobrado e a mão encostada no
    # corpo, que as fatias perdem); a linha reta até a ponta das fatias fica de reserva
    try:
        import fc_eixo
        campo = fc_eixo.Campo(obj, 0.008 * H)
    except Exception as e:  # malha estranha: fica a medição pelas fatias
        print(f"[rig] sem campo de distância: {e}")
        campo = None
    ULTIMO["campo"] = campo
    # ombros: metade da largura do tronco na altura do peito, sem passar da mão
    f = faixa(0.70, 0.76)
    largura = float(np.percentile(np.abs(f[:, 0]), 90)) if len(f) else 0.13 * H
    ombro_x = float(np.clip(largura * 0.78, 0.085 * H, 0.13 * H))
    p = {}
    # profundidade (y) das pernas pelos pés, que aparecem embaixo da roupa; a da cabeça pelo elmo/rosto
    # (compacto, sem capa). A média de uma fatia do tronco puxa para a frente da sobreveste ou para a capa.
    pes = {}
    for lado, s in (("l", 1.0), ("r", -1.0)):
        f = faixa(0.0, 0.07)
        f = f[f[:, 0] * s > 0.01 * H]
        if len(f):
            pes[lado] = (float(np.median(f[:, 0])), float(f[:, 1].min()), float(f[:, 1].max()))
        else:
            pes[lado] = (s * 0.06 * H, -0.06 * H, 0.06 * H)
    f = faixa(0.88, 0.97)
    cab_y = (float(f[:, 1].min()) + float(f[:, 1].max())) / 2 if len(f) else 0.0
    # tornozelo um pouco para trás do meio do pé (o calcanhar fica atrás)
    tornozelo_y = float(np.mean([(pes[k][1] + pes[k][2]) / 2 + 0.2 * (pes[k][2] - pes[k][1]) for k in ("l", "r")]))
    quadril_y = tornozelo_y + 0.004 * H
    yc = {"pelvis": quadril_y, "s1": quadril_y + 0.002 * H, "s2": (2 * quadril_y + cab_y) / 3, "s3": (quadril_y + 2 * cab_y) / 3,
          "pescoco": cab_y + 0.01 * H, "cabeca": cab_y}
    p["pelvis"] = ((0, yc["pelvis"], 0.53 * H), (0, yc["s1"], 0.585 * H))
    p["spine_01"] = (p["pelvis"][1], (0, yc["s2"], 0.65 * H))
    p["spine_02"] = (p["spine_01"][1], (0, yc["s3"], 0.72 * H))
    p["spine_03"] = (p["spine_02"][1], (0, yc["pescoco"], 0.835 * H))
    p["neck_01"] = (p["spine_03"][1], (0, yc["cabeca"], 0.875 * H))
    p["head"] = (p["neck_01"][1], (0, yc["cabeca"], 1.0 * H))
    for lado, s in (("l", 1.0), ("r", -1.0)):
        ombro = np.array([s * ombro_x, yc["s3"], 0.815 * H])
        b = None
        if campo is not None:
            tr = trilhas[lado]
            if len(tr) >= 3:
                ini = np.asarray(tr[0])
                u = np.asarray(tr[min(6, len(tr) - 1)]) - ini
            else:
                ini = np.array([s * (ombro_x + 0.02 * H), yc["s3"], 0.70 * H])
                u = np.array([s * 0.15, 0.0, -1.0])
            if np.linalg.norm(u) < 1e-6:
                u = np.array([s * 0.15, 0.0, -1.0])
            try:
                b = fc_eixo.braco(campo, H, ombro, ini, u)
            except Exception as e:
                print(f"[rig] braço {lado} pelo campo falhou: {e}")
        if b is not None:
            print(f"[rig] braço {lado} pelo centro da malha: {b['comprimento'] / H:.2f} H, dobra {b['dobra']:.0f}°, "
                  f"mão em z {b['ponta'][2]:.2f} m")
            p[f"clavicle_{lado}"] = ((s * 0.02 * H, yc["s3"] - 0.01 * H, 0.81 * H), tuple(ombro))
            p[f"upperarm_{lado}"] = (tuple(ombro), tuple(b["cotovelo"]))
            p[f"lowerarm_{lado}"] = (tuple(b["cotovelo"]), tuple(b["pulso"]))
            p[f"hand_{lado}"] = (tuple(b["pulso"]), tuple(b["ponta"]))
        # braço pelas proporções do corpo humano ao longo da linha ombro → ponta dos dedos
        # (braço 0,186 H, antebraço 0,146 H, mão 0,108 H); se a ponta medida não cabe (a mão encostou
        # no corpo e a trilha parou no pulso), a ponta vai para o comprimento do braço na mesma direção
        ponta = pontas[lado]
        if ponta is None:
            ponta = ombro + np.array([s * 0.05 * H, 0.0, -0.44 * H])
        v = ponta - ombro
        comp = float(np.linalg.norm(v))
        if not 0.36 * H < comp < 0.50 * H:
            v = v / max(comp, 1e-6) * 0.44 * H
            comp = 0.44 * H
        u = v / comp
        cot = ombro + u * comp * (0.186 / 0.44) + np.array([s * 0.006 * H, 0.012 * H, 0.0])
        pulso = ombro + u * comp * (0.332 / 0.44)
        fim = ombro + v
        if b is None:
            p[f"clavicle_{lado}"] = ((s * 0.02 * H, yc["s3"] - 0.01 * H, 0.81 * H), tuple(ombro))
            p[f"upperarm_{lado}"] = (tuple(ombro), tuple(cot))
            p[f"lowerarm_{lado}"] = (tuple(cot), tuple(pulso))
            p[f"hand_{lado}"] = (tuple(pulso), tuple(fim))
        px, ymin, ymax = pes[lado]
        tor_y = (ymin + ymax) / 2 + 0.2 * (ymax - ymin)
        quadril = (s * 0.055 * H, quadril_y, 0.5 * H)
        joelho = (float(np.clip(px, s * 0.04 * H, s * 0.07 * H) if s > 0 else np.clip(px, s * 0.07 * H, s * 0.04 * H)), tor_y - 0.012 * H, 0.275 * H)
        tornozelo = (px, tor_y, 0.045 * H)
        bola = (px, ymin + 0.3 * (ymax - ymin), 0.012 * H)
        ponta = (px, ymin, 0.012 * H)
        p[f"thigh_{lado}"] = (quadril, joelho)
        p[f"calf_{lado}"] = (joelho, tornozelo)
        p[f"foot_{lado}"] = (tornozelo, bola)
        p[f"ball_{lado}"] = (bola, ponta)
    return p, H


def criar_esqueleto(nome, pontos):
    dados = bpy.data.armatures.new(nome + "_esqueleto")
    arm = bpy.data.objects.new(nome, dados)
    bpy.context.scene.collection.objects.link(arm)
    for o in bpy.context.scene.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = {}
    for osso, pai in HIERARQUIA:
        eb = dados.edit_bones.new(osso)
        eb.head, eb.tail = Vector(pontos[osso][0]), Vector(pontos[osso][1])
        if (eb.tail - eb.head).length < 1e-4:
            eb.tail = eb.head + Vector((0, 0, 0.03))
        # rolagem alinhada ao mundo (a retargetagem compensa a diferença de descanso)
        eb.align_roll(Vector((0, -1, 0)) if osso.startswith(("thigh", "calf", "spine", "pelvis", "neck", "head")) else Vector((0, 0, 1)))
        if pai:
            eb.parent = ebs[pai]
        ebs[osso] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def _seg(co, a, b):
    ab = b - a
    t = np.clip(((co - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(co - (a + t[:, None] * ab), axis=1)


def _saia(co, H, arm, mw):
    """(máscara, peso do quadril, lado esquerdo 0–1) dos vértices da saia; None se não há saia."""
    joelho = max((mw @ arm.data.bones[f"calf_{l}"].head_local).z for l in "lr")
    quadril = (mw @ arm.data.bones["pelvis"].head_local).z
    perna_y = float(np.mean([(mw @ arm.data.bones[f"thigh_{l}"].head_local).y for l in "lr"]))
    barra = None
    for z in np.arange(0.12 * H, quadril - 0.04 * H, 0.01 * H):
        # pano bem à frente das pernas (painel da túnica: 0,13 a 0,15 H no templário). A malha da IA muitas
        # vezes vem com as coxas grudadas por uma membrana até o meio da coxa: ela fica entre as pernas
        # (0,01 a 0,07 H à frente), e contava como barra de saia — a calça rasgava em pontas ao andar
        meio = (np.abs(co[:, 2] - z) < 0.006 * H) & (np.abs(co[:, 0]) < 0.02 * H) & (co[:, 1] < perna_y - 0.08 * H)
        if meio.sum() >= 3:
            barra = float(z)
            break
    # saia é pano comprido (a túnica do templário desce até 0,20 H): barra de jaqueta ou camisa logo abaixo
    # do quadril não é saia. Com a margem de 0,06 H a jaqueta aberta virava "saia" e a calça embaixo dela
    # ganhava peso de quadril com canela, sem a coxa: rasgava em pontas ao andar
    if barra is None or barra > quadril - 0.15 * H:
        return None
    dy = co[:, 1] - perna_y
    # na frente o painel da sobreveste fica bem à frente das pernas (no cavaleiro de referência, 0,124 H):
    # fora da janela ele seguia a coxa inteira e virava um lençol na corrida
    m = (co[:, 2] > barra - 0.015 * H) & (co[:, 2] < quadril) & (dy > -0.18 * H) & (dy < 0.12 * H)
    # abaixo da barra do meio da frente o pano continua (laterais e costas descem mais): é saia o que
    # está longe das pernas (as grevas ficam justas no osso); antes essa faixa seguia a canela do molde e
    # virava um lençol quando o joelho subia
    d_perna = np.full(len(co), np.inf)
    for lado in "lr":
        for n in (f"thigh_{lado}", f"calf_{lado}"):
            b = arm.data.bones.get(n)
            if b is not None:
                d_perna = np.minimum(d_perna, _seg(co, np.array(mw @ b.head_local), np.array(mw @ b.tail_local)))
    m |= (co[:, 2] > 0.1 * H) & (co[:, 2] <= barra - 0.015 * H) & (d_perna > 0.065 * H) & (dy > -0.18 * H) & (dy < 0.12 * H)
    t = np.clip((co[:, 2] - barra) / max(quadril - 0.04 * H - barra, 1e-6), 0.0, 1.0)
    t = t * t * (3 - 2 * t)
    # longe das pernas em profundidade (a capa atrás) vai sumindo a parte das pernas, sem degrau; o painel
    # da frente ainda acompanha um pouco as coxas (o joelho não fura o pano na passada)
    f = np.clip((0.12 * H - np.abs(dy)) / (0.06 * H), 0.0, 1.0)
    f = f * f * (3 - 2 * f)
    f = np.where(dy < 0, np.maximum(f, 0.5), f)
    p_quadril = 1.0 - (0.5 - 0.5 * t) * f
    # divisão esquerda/direita suave: o painel anda inteiro, sem rasgar no meio quando as coxas se cruzam
    lado_l = 1.0 / (1.0 + np.exp(-co[:, 0] / (0.05 * H)))
    # abaixo do joelho a barra segue a canela; acima, a coxa
    canela = co[:, 2] < joelho
    return m, p_quadril, lado_l, canela, barra


def pesos_por_regioes(obj, arm, H, capa=False):
    """Pesos pela distância aos ossos, mas cada região só nos ossos que fazem sentido: a mão e o
    antebraço só pegam o que está perto do braço (a mão da malha não fica para trás do osso, e a arma
    acompanha); as pernas só o que está perto da perna; a capa e a saia (longe das pernas, abaixo da
    cintura) ficam no quadril, para não dobrarem junto com as pernas."""
    co = _vertices(obj)
    mw = arm.matrix_world
    # os ossos da capa ficam de fora da regra geral (a capa é pesada à parte, depois)
    ossos = [b for b in arm.data.bones if b.name not in CAPA]
    nomes = [b.name for b in ossos]
    seg = {b.name: (np.array(mw @ b.head_local), np.array(mw @ b.tail_local)) for b in ossos}
    D = np.stack([_seg(co, *seg[n]) for n in nomes], axis=1)
    idx = {n: i for i, n in enumerate(nomes)}
    valido = np.ones_like(D, dtype=bool)
    braco = {lado: [f"upperarm_{lado}", f"lowerarm_{lado}", f"hand_{lado}"] for lado in "lr"}
    perna = {lado: [f"thigh_{lado}", f"calf_{lado}", f"foot_{lado}", f"ball_{lado}"] for lado in "lr"}
    tronco = ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "clavicle_l", "clavicle_r"]
    d_tronco = D[:, [idx[n] for n in tronco]].min(1)
    for lado in "lr":
        d_braco = D[:, [idx[n] for n in braco[lado]]].min(1)
        # raio por osso: ombreira grande no braço, manopla justa na mão (a saia e a bainha ao lado da
        # mão não podem ir junto com ela)
        # antebraço e mão: só o que não está para dentro do eixo do braço (o pano da sobreveste ao lado
        # do braço caído fica com o corpo; antes ele ia junto e virava uma aba quando o braço cruzava)
        s_lado = 1.0 if lado == "l" else -1.0
        dentro_ok = np.ones(len(co), dtype=bool)
        for n in (f"lowerarm_{lado}", f"hand_{lado}"):
            a, b = seg[n]
            ab = b - a
            t = np.clip(((co - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
            prox = a + t[:, None] * ab
            dentro_ok &= ~((D[:, idx[n]] < 0.06 * H) & (s_lado * (co[:, 0] - prox[:, 0]) < -0.028 * H))
        perto_osso = ((D[:, idx[f"upperarm_{lado}"]] < 0.08 * H)
                      | ((D[:, idx[f"lowerarm_{lado}"]] < 0.05 * H) & dentro_ok)
                      | ((D[:, idx[f"hand_{lado}"]] < 0.045 * H) & dentro_ok))
        no_braco = perto_osso & (d_braco < d_tronco + 0.01 * H)
        for n in braco[lado]:
            valido[:, idx[n]] = no_braco
        d_perna = D[:, [idx[n] for n in perna[lado]]].min(1)
        na_perna = (d_perna < 0.07 * H) & ~no_braco
        for n in perna[lado]:
            valido[:, idx[n]] = na_perna
    # capa e saia: abaixo da cintura e longe das duas pernas → só quadril (e um pouco de spine_01);
    # perto da perna a mistura é gradual (sem "rasgo" entre o que segue a perna e o que fica no quadril)
    d_pernas = np.minimum(D[:, [idx[n] for n in perna["l"]]].min(1), D[:, [idx[n] for n in perna["r"]]].min(1))
    # o braço (mão pendurada ao lado do quadril) fica fora da regra do pano: antes a mão ia para o
    # quadril e a espada, presa no osso da mão, saía andando sozinha
    no_bracos = np.zeros(len(co), dtype=bool)
    for lado in "lr":
        no_bracos |= valido[:, idx[f"hand_{lado}"]]
    baixo = (co[:, 2] < 0.56 * H) & ~no_bracos
    pano = baixo & (d_pernas >= 0.07 * H)
    for n in nomes:
        if n not in ("pelvis", "spine_01"):
            valido[pano, idx[n]] = False
    # quanto do quadril entra no lugar da perna (0 colado na perna, 1 já na roupa solta)
    mistura = np.where(baixo, np.clip((d_pernas - 0.03 * H) / (0.07 * H - 0.03 * H), 0.0, 1.0), 0.0)
    mistura = mistura * mistura * (3 - 2 * mistura)
    # cabeça e elmo: acima do pescoço, só cabeça/pescoço
    alto = co[:, 2] > 0.885 * H
    for n in nomes:
        if n not in ("head", "neck_01"):
            valido[alto, idx[n]] = False
    Dm = np.where(valido, D, np.inf)
    sem = ~np.isfinite(Dm).any(1)
    Dm[sem] = np.where(np.isin(np.arange(len(nomes)), [idx[n] for n in tronco]), D[sem], np.inf)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    grupos = {n: obj.vertex_groups.new(name=n) for n in nomes}
    ordem = np.argsort(Dm, axis=1)[:, :3]
    suave = 0.012 * H
    i_pelvis = idx["pelvis"]
    # saia (sobreveste, túnica): a barra é a altura mais baixa em que o pano liga as duas pernas na
    # frente (há malha no meio, entre as pernas). Entre a barra e o quadril o pano fica no quadril, com
    # a parte de baixo seguindo as coxas aos poucos (o meio, entre as pernas, segue a média das duas):
    # a frente da saia não sai junto com uma perna só nem deixa o joelho furar o pano.
    saia = _saia(co, H, arm, mw)
    if saia is not None:
        # a mão pendurada ao lado da saia não é saia
        saia = (saia[0] & ~no_bracos,) + tuple(saia[1:])
    if saia is not None:
        print(f"[rig_ia] saia: barra a {saia[4]:.2f} m")
    for vi in range(len(co)):
        if saia is not None and saia[0][vi]:
            _, p_quadril, lado_l, canela, _ = saia
            p = float(p_quadril[vi])
            wl = float(lado_l[vi])
            osso = "calf" if canela[vi] else "thigh"
            for kk, peso in ((i_pelvis, p), (idx[f"{osso}_l"], (1 - p) * wl), (idx[f"{osso}_r"], (1 - p) * (1 - wl))):
                if peso > 0.01:
                    grupos[nomes[kk]].add([vi], peso, "REPLACE")
            continue
        k = ordem[vi]
        d = Dm[vi, k]
        ok = np.isfinite(d)
        if not ok.any():
            continue
        w = np.where(ok, 1.0 / (np.where(ok, d, 1.0) + suave) ** 4, 0.0)
        w /= w.sum()
        pesos = {int(kk): float(peso) for kk, peso in zip(k, w)}
        a = float(mistura[vi])
        if a > 0:
            pesos = {kk: peso * (1 - a) for kk, peso in pesos.items()}
            pesos[i_pelvis] = pesos.get(i_pelvis, 0.0) + a
        for kk, peso in pesos.items():
            if peso > 0.01:
                grupos[nomes[kk]].add([vi], peso, "REPLACE")
    # alisa as fronteiras (poucas passadas: não espalha a mão para a coxa) e renormaliza
    if capa:
        pesar_capa(obj, arm, H)
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    try:
        # o alisar só roda no modo de pintura de pesos
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=3)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    except Exception as e:
        print(f"[rig_ia] sem alisar os pesos: {e}")
    finally:
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    if not any(m.type == "ARMATURE" for m in obj.modifiers):
        mod = obj.modifiers.new("esqueleto", "ARMATURE")
        mod.object = arm
    obj.parent = arm


def vestir(obj, arm):
    """Pesos pelo calor; se o Blender não achar solução (malha fundida da IA), pela distância aos ossos."""
    for o in bpy.context.scene.objects:
        o.select_set(o in (obj, arm))
    bpy.context.view_layer.objects.active = arm
    metodo = "calor"
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception:
        metodo = ""
    vazios = sum(1 for v in obj.data.vertices if not v.groups)
    if not metodo or vazios > 0.02 * len(obj.data.vertices):
        import fc_criatura

        fc_criatura.pesos_por_distancia(obj, arm, vizinhos=3, potencia=4.0)
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("esqueleto", "ARMATURE")
            mod.object = arm
        obj.parent = arm
        metodo = "distancia"
    return metodo


CAPA = ["capa_1", "capa_2", "capa_3"]


def cadeia_da_capa(obj, arm, H):
    """Capa (pano atrás das pernas, abaixo do quadril): três ossos no meio dela, do quadril para baixo,
    filhos da pelve (sem captura, seguem o quadril como antes; na engine viram molas e balançam).
    Devolve os nomes, ou [] sem capa."""
    co = _vertices(obj)
    mw = arm.matrix_world
    perna_y = float(np.mean([(mw @ arm.data.bones[f"thigh_{lado}"].head_local).y for lado in "lr"]))
    atras = (co[:, 1] > perna_y + 0.07 * H) & (co[:, 2] < 0.45 * H) & (co[:, 2] > 0.05 * H) & (np.abs(co[:, 0]) < 0.2 * H)
    if atras.sum() < 200:
        return []
    pontos = []
    for z in (0.56, 0.40, 0.24, 0.08):
        f = co[(np.abs(co[:, 2] - z * H) < 0.03 * H) & (co[:, 1] > perna_y + 0.02 * H) & (np.abs(co[:, 0]) < 0.12 * H)]
        y = float(np.percentile(f[:, 1], 70)) if len(f) else perna_y + 0.08 * H
        pontos.append(Vector((0.0, y - 0.01 * H, z * H)))
    for o in bpy.context.scene.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb_pai = arm.data.edit_bones["pelvis"]
    for i, nome in enumerate(CAPA):
        eb = arm.data.edit_bones.new(nome)
        eb.head, eb.tail = pontos[i], pontos[i + 1]
        eb.align_roll(Vector((0, 1, 0)))
        eb.parent = eb_pai
        eb.use_connect = i > 0
        eb_pai = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    return list(CAPA)


def pesar_capa(obj, arm, H):
    """Os vértices da capa passam para a cadeia (o topo mistura com a pelve; perto das pernas, a regra
    de antes continua: a passagem é gradual)."""
    co = _vertices(obj)
    mw = arm.matrix_world
    perna_y = float(np.mean([(mw @ arm.data.bones[f"thigh_{lado}"].head_local).y for lado in "lr"]))
    dy = co[:, 1] - perna_y
    c = np.clip((dy - 0.06 * H) / (0.05 * H), 0.0, 1.0) * (co[:, 2] < 0.56 * H)
    # quem já é do braço (mão, antebraço) continua do braço
    nomes_idx0 = {g.index: g.name for g in obj.vertex_groups}
    for vi in np.where(c > 0.01)[0]:
        if any(nomes_idx0.get(g.group, "").startswith(("hand_", "lowerarm_")) and g.weight > 0.3 for g in obj.data.vertices[int(vi)].groups):
            c[vi] = 0.0
    c = c * c * (3 - 2 * c)
    segs = [(np.array(mw @ arm.data.bones[n].head_local), np.array(mw @ arm.data.bones[n].tail_local)) for n in CAPA]
    d = np.stack([_seg(co, a, b) for a, b in segs], axis=1)
    topo = np.clip((co[:, 2] - 0.50 * H) / (0.06 * H), 0.0, 1.0)
    grupos = {g.name: g for g in obj.vertex_groups}
    for n in CAPA:
        if n not in grupos:
            grupos[n] = obj.vertex_groups.new(name=n)
    nomes_idx = {g.index: g.name for g in obj.vertex_groups}
    for vi in np.where(c > 0.01)[0]:
        v = obj.data.vertices[int(vi)]
        antes = {nomes_idx[g.group]: g.weight for g in v.groups}
        w = 1.0 / (d[vi] + 0.01 * H) ** 4
        w /= w.sum()
        cadeia = {n: float(w[k]) * (1 - topo[vi]) for k, n in enumerate(CAPA)}
        cadeia["pelvis"] = cadeia.get("pelvis", 0.0) + float(topo[vi])
        novos = {n: p * (1 - c[vi]) for n, p in antes.items()}
        for n, p in cadeia.items():
            novos[n] = novos.get(n, 0.0) + p * float(c[vi])
        for n, p in novos.items():
            grupos[n].add([int(vi)], p, "REPLACE")


def rigar(obj, nome, altura=1.8):
    """Normaliza, mede, cria o esqueleto e pesa. Devolve (armadura, info)."""
    normalizar(obj, altura)
    pontos, H = medir(obj)
    arm = criar_esqueleto(nome, pontos)
    capa = cadeia_da_capa(obj, arm, H)
    # a malha da IA vem fundida (mão encostada na coxa, capa por cima das pernas): o calor do Blender
    # espalha os pesos entre o que se toca. Pesos por regiões resolvem isso.
    pesos_por_regioes(obj, arm, H, capa=bool(capa))
    metodo = "regioes"
    return arm, {"altura_m": round(H, 3), "pesos": metodo, "ossos": len(arm.data.bones), "molas": capa}
