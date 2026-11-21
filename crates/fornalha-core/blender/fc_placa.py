# Fornalha: o que chega dos modelos de placa (TRELLIS.2, UniRig, HY-Motion) vira
# asset de jogo aqui no Blender, sem o nvdiffrast (que não deixa vender):
#   - assar: malha alta com cores por vértice → malha leve com UV e textura assada;
#   - movimento: rotações SMPL (22 juntas do corpo) → animação no esqueleto padrão.
import math

import bpy
from mathutils import Quaternion, Vector

import fc_comum as c

# ------------------------------------------------------------------ textura assada


def _principled(nt):
    return next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")


def material_das_cores(m):
    """Material que lê a cor de cada vértice (a malha alta do TRELLIS.2)."""
    attrs = m.data.color_attributes
    if not len(attrs):
        raise ValueError("a malha não tem cores por vértice")
    cor = attrs.active_color or attrs[0]
    mat = bpy.data.materials.new(m.name + "_cores")
    mat.use_nodes = True
    nt = mat.node_tree
    no = nt.nodes.new("ShaderNodeVertexColor")
    no.layer_name = cor.name
    nt.links.new(no.outputs["Color"], _principled(nt).inputs["Base Color"])
    m.data.materials.clear()
    m.data.materials.append(mat)
    return cor.name


def assar_textura(alta, baixa, tamanho, nome):
    """Assa a cor da malha alta na textura da malha leve (Cycles na CPU, sem placa)."""
    img = bpy.data.images.new(nome, tamanho, tamanho, alpha=False)
    mat = bpy.data.materials.new(nome)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = _principled(nt)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    nt.nodes.active = tex
    baixa.data.materials.clear()
    baixa.data.materials.append(mat)

    cena = bpy.context.scene
    cena.render.engine = "CYCLES"
    cena.cycles.device = "CPU"
    cena.cycles.samples = 2
    for o in cena.objects:
        o.select_set(False)
    alta.hide_render = False
    alta.select_set(True)
    baixa.select_set(True)
    bpy.context.view_layer.objects.active = baixa
    tam = max(baixa.dimensions) or 1.0
    bpy.ops.object.bake(
        type="DIFFUSE",
        pass_filter={"COLOR"},
        use_selected_to_active=True,
        cage_extrusion=0.01 * tam,
        max_ray_distance=0.04 * tam,
        margin=6,
    )
    img.pack()
    return img


def cobertura(img):
    """Fração da textura que recebeu cor (pixels que não ficaram pretos)."""
    px = list(img.pixels)
    total = len(px) // 4
    cheios = sum(1 for i in range(0, len(px), 4) if px[i] + px[i + 1] + px[i + 2] > 0.02)
    return round(cheios / max(1, total), 3)


def cor_media(img):
    px = img.pixels[:]
    soma, n = [0.0, 0.0, 0.0], 0
    for i in range(0, len(px), 4):
        if px[i] + px[i + 1] + px[i + 2] > 0.02:
            soma[0] += px[i]
            soma[1] += px[i + 1]
            soma[2] += px[i + 2]
            n += 1
    return [round(s / max(1, n), 3) for s in soma]


# ------------------------------------------------------------------ movimento SMPL

# Junta SMPL → osso do esqueleto padrão. As duas últimas vértebras (spine2 e
# spine3) viram o Chest juntas. A pose de descanso das duas é a T-pose.
SMPL_PARA_PADRAO = {
    0: "Hips",
    1: "LeftUpperLeg",
    2: "RightUpperLeg",
    3: "Spine",
    4: "LeftLowerLeg",
    5: "RightLowerLeg",
    6: "Chest",
    7: "LeftFoot",
    8: "RightFoot",
    9: "Chest",
    10: "LeftToes",
    11: "RightToes",
    12: "Neck",
    13: "LeftShoulder",
    14: "RightShoulder",
    15: "Head",
    16: "LeftUpperArm",
    17: "RightUpperArm",
    18: "LeftLowerArm",
    19: "RightLowerArm",
    20: "LeftHand",
    21: "RightHand",
}
ALTURA_QUADRIL_SMPL = 0.93


def _eixo_angulo(v):
    v = Vector(v)
    ang = v.length
    if ang < 1e-9:
        return Quaternion()
    return Quaternion(v / ang, ang)


def _local(pb, q_mundo):
    R = pb.bone.matrix_local.to_3x3()
    return (R.inverted() @ q_mundo.to_matrix() @ R).to_quaternion()


def aplicar_movimento(arm, mov, nome, laco, no_lugar=True, fps=30):
    """mov: {"fps", "rotacoes": [quadro][22][3] eixo-ângulo, "translacao": [quadro][3], "eixo_cima": "Y"|"Z"}."""
    rot = mov["rotacoes"]
    if not rot:
        raise ValueError("o movimento veio sem quadros")
    trans = mov.get("translacao") or [[0.0, 0.0, 0.0]] * len(rot)
    fps_origem = float(mov.get("fps") or 30)
    # SMPL tem o Y para cima e olha para +Z; o Blender tem o Z para cima e o personagem olha para -Y.
    C = Quaternion((1, 0, 0), math.radians(90)) if mov.get("eixo_cima", "Y").upper() == "Y" else Quaternion()
    Ci = C.inverted()
    H = arm.data.bones["Head"].tail_local.z
    quadril = arm.data.bones["Hips"].head_local.z
    escala = float(mov.get("escala") or (quadril / float(mov.get("altura_quadril_m") or ALTURA_QUADRIL_SMPL)))
    nomes = {b.name for b in arm.data.bones}

    ad = arm.animation_data or arm.animation_data_create()
    velha = bpy.data.actions.get(nome)
    if velha:
        bpy.data.actions.remove(velha)
    act = bpy.data.actions.new(nome)
    act.use_fake_user = True
    ad.action = act
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    duracao = (len(rot) - 1) / fps_origem
    quadros = max(1, int(round(duracao * fps)) + 1)
    t0 = C @ Vector(trans[0])
    for k in range(quadros):
        i = min(len(rot) - 1, int(round(k * fps_origem / fps)))
        juntas = rot[i]
        por_osso = {}
        for j, osso in SMPL_PARA_PADRAO.items():
            if j >= len(juntas) or osso not in nomes:
                continue
            q = C @ _eixo_angulo(juntas[j]) @ Ci
            # Chest = spine2 seguido de spine3 (rotações locais na ordem da cadeia)
            por_osso[osso] = por_osso[osso] @ q if osso in por_osso else q
        for pb in arm.pose.bones:
            pb.rotation_quaternion = _local(pb, por_osso[pb.name]) if pb.name in por_osso else Quaternion()
            pb.location = Vector()
        d = (C @ Vector(trans[i]) - t0) * escala
        if no_lugar:
            d.x = 0.0
            d.y = 0.0
        hips = arm.pose.bones["Hips"]
        hips.location = hips.bone.matrix_local.to_3x3().inverted() @ d
        for pb in arm.pose.bones:
            pb.keyframe_insert(data_path="rotation_quaternion", frame=k + 1, group=pb.name)
            if pb.name == "Hips":
                pb.keyframe_insert(data_path="location", frame=k + 1, group=pb.name)
    try:
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = quadros
        act.use_cyclic = laco
    except Exception:
        pass
    act["laco"] = laco
    return act, quadros, H


def posicao_do_osso(arm, osso, quadro, acao):
    arm.animation_data.action = acao
    bpy.context.scene.frame_set(quadro)
    bpy.context.view_layer.update()
    pb = arm.pose.bones[osso]
    p = arm.matrix_world @ pb.tail
    return [round(p.x, 3), round(p.y, 3), round(p.z, 3)]


def guardar_acoes(arm):
    """As animações que já vieram no arquivo continuam no glb exportado."""
    for a in bpy.data.actions:
        a.use_fake_user = True
        nome = a.name.split("|")[-1]
        if nome != a.name and not bpy.data.actions.get(nome):
            a.name = nome
    return list(bpy.data.actions)


def caixa(objs):
    return c.caixa_envolvente(objs)
