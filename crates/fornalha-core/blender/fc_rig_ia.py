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

    # mãos: o ponto mais de fora de cada lado entre o quadril e a cintura (braços caídos ao lado)
    maos = {}
    for lado, s in (("l", 1.0), ("r", -1.0)):
        f = faixa(0.38, 0.62)
        # só a metade da frente: a capa pendurada atrás pode ser mais larga que as mãos
        cab = faixa(0.88, 0.97)
        y_meio = (float(cab[:, 1].min()) + float(cab[:, 1].max())) / 2 if len(cab) else 0.0
        f = f[(f[:, 0] * s > 0.08 * H) & (f[:, 1] < y_meio + 0.04 * H)]
        if len(f):
            ext = f[np.argmax(f[:, 0] * s)]
            perto = f[np.abs(f[:, 0] - ext[0]) < 0.035 * H]
            maos[lado] = np.array([ext[0] - s * 0.025 * H, float(np.median(perto[:, 1])), float(np.median(perto[:, 2]))])
        else:
            maos[lado] = np.array([s * 0.19 * H, 0.0, 0.48 * H])
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
        mao = maos[lado]
        # cotovelo: no meio, um pouco para trás e para fora (braço relaxado)
        cot = (ombro + mao) / 2 + np.array([s * 0.012 * H, 0.012 * H, 0.0])
        dir_mao = (mao - cot) / max(np.linalg.norm(mao - cot), 1e-6)
        p[f"clavicle_{lado}"] = ((s * 0.02 * H, yc["s3"] - 0.01 * H, 0.81 * H), tuple(ombro))
        p[f"upperarm_{lado}"] = (tuple(ombro), tuple(cot))
        p[f"lowerarm_{lado}"] = (tuple(cot), tuple(mao))
        p[f"hand_{lado}"] = (tuple(mao), tuple(mao + dir_mao * 0.055 * H))
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


def pesos_por_regioes(obj, arm, H):
    """Pesos pela distância aos ossos, mas cada região só nos ossos que fazem sentido: a mão e o
    antebraço só pegam o que está perto do braço (a mão da malha não fica para trás do osso, e a arma
    acompanha); as pernas só o que está perto da perna; a capa e a saia (longe das pernas, abaixo da
    cintura) ficam no quadril, para não dobrarem junto com as pernas."""
    co = _vertices(obj)
    mw = arm.matrix_world
    ossos = [b for b in arm.data.bones]
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
        no_braco = (d_braco < 0.075 * H) & (d_braco < d_tronco + 0.01 * H)
        for n in braco[lado]:
            valido[:, idx[n]] = no_braco
        d_perna = D[:, [idx[n] for n in perna[lado]]].min(1)
        na_perna = (d_perna < 0.07 * H) & ~no_braco
        for n in perna[lado]:
            valido[:, idx[n]] = na_perna
    # capa e saia: abaixo da cintura e longe das duas pernas → só quadril (e um pouco de spine_01);
    # perto da perna a mistura é gradual (sem "rasgo" entre o que segue a perna e o que fica no quadril)
    d_pernas = np.minimum(D[:, [idx[n] for n in perna["l"]]].min(1), D[:, [idx[n] for n in perna["r"]]].min(1))
    baixo = co[:, 2] < 0.56 * H
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
    for vi in range(len(co)):
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
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=3)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    except Exception as e:
        print(f"[rig_ia] sem alisar os pesos: {e}")
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


def rigar(obj, nome, altura=1.8):
    """Normaliza, mede, cria o esqueleto e pesa. Devolve (armadura, info)."""
    normalizar(obj, altura)
    pontos, H = medir(obj)
    arm = criar_esqueleto(nome, pontos)
    # a malha da IA vem fundida (mão encostada na coxa, capa por cima das pernas): o calor do Blender
    # espalha os pesos entre o que se toca. Pesos por regiões resolvem isso.
    pesos_por_regioes(obj, arm, H)
    metodo = "regioes"
    return arm, {"altura_m": round(H, 3), "pesos": metodo, "ossos": len(HIERARQUIA)}
