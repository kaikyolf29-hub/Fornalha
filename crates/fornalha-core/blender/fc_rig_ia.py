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
        f = f[f[:, 0] * s > 0.08 * H]
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
    yc = {k: centro_y(a, b) for k, a, b in (("pelvis", 0.5, 0.56), ("s1", 0.56, 0.62), ("s2", 0.63, 0.69),
                                            ("s3", 0.7, 0.76), ("pescoco", 0.84, 0.87), ("cabeca", 0.88, 0.96))}
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
        quadril = (s * 0.055 * H, yc["pelvis"], 0.5 * H)
        joelho = (s * 0.052 * H, yc["pelvis"] - 0.012 * H, 0.275 * H)
        tornozelo = (s * 0.055 * H, yc["pelvis"] + 0.01 * H, 0.045 * H)
        bola = (s * 0.058 * H, yc["pelvis"] - 0.065 * H, 0.012 * H)
        ponta = (s * 0.06 * H, yc["pelvis"] - 0.11 * H, 0.012 * H)
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
    metodo = vestir(obj, arm)
    return arm, {"altura_m": round(H, 3), "pesos": metodo, "ossos": len(HIERARQUIA)}
