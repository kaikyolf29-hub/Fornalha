# Fornalha: personagem humanoide low-poly com esqueleto padrão, pesos e acessórios.
# Os nomes dos ossos seguem o perfil humanoide da Godot (Hips, Spine, Chest, Neck,
# Head, LeftUpperArm...), então a Godot e a Erethea fazem o retarget sozinhas.
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

import fc_comum as c

# Tipos de personagem: altura (m), porte, cor da pele padrão e extras.
TIPOS = {
    "humano": dict(altura=1.80, porte=1.0, pele="#e0ac7e", cabelo=True),
    "elfo": dict(altura=1.85, porte=0.88, pele="#f0c9a5", cabelo=True, orelhas=True),
    "anao": dict(altura=1.35, porte=1.30, pele="#d9a07a", cabelo=True, barba=True),
    "orc": dict(altura=1.95, porte=1.30, pele="#6f8f4e", cabelo=False, presas=True),
    "goblin": dict(altura=1.15, porte=0.90, pele="#8fae5a", cabelo=False, orelhas=True),
    "esqueleto": dict(altura=1.80, porte=0.80, pele="#e6dfc8", cabelo=False, olhos_grandes=True),
    "zumbi": dict(altura=1.78, porte=0.85, pele="#9aa38f", cabelo=True),
    "demonio": dict(altura=2.00, porte=1.15, pele="#8e3b32", cabelo=False, chifres=True),
}


def ossos_padrao(H, w):
    """(nome, cabeça, cauda, pai) do esqueleto padrão em T-pose, de frente para -Y."""
    xl = 0.06 * H * w
    zq, zj, zt = 0.52 * H, 0.285 * H, 0.055 * H
    zs, zc, zn, zh = 0.565 * H, 0.70 * H, 0.82 * H, 0.865 * H
    zb = 0.80 * H
    xo = 0.11 * H * w
    lista = [
        ("Root", (0, 0, 0), (0, 0, 0.06 * H), None),
        ("Hips", (0, 0, zq + 0.02 * H), (0, 0, zs), "Root"),
        ("Spine", (0, 0, zs), (0, 0, zc), "Hips"),
        ("Chest", (0, 0, zc), (0, 0, zn), "Spine"),
        ("Neck", (0, 0, zn), (0, 0, zh), "Chest"),
        ("Head", (0, 0, zh), (0, 0, H), "Neck"),
        ("Jaw", (0, -0.01 * H, zh + 0.035 * H), (0, -0.06 * H, zh + 0.02 * H), "Head"),
    ]
    for lado, s in (("Left", 1), ("Right", -1)):
        lista += [
            (f"{lado}Shoulder", (s * 0.02 * H * w, 0, zb - 0.01 * H), (s * xo, 0, zb), "Chest"),
            (f"{lado}UpperArm", (s * xo, 0, zb), (s * 0.28 * H, 0, zb), f"{lado}Shoulder"),
            (f"{lado}LowerArm", (s * 0.28 * H, 0, zb), (s * 0.43 * H, 0, zb), f"{lado}UpperArm"),
            (f"{lado}Hand", (s * 0.43 * H, 0, zb), (s * 0.51 * H, 0, zb), f"{lado}LowerArm"),
            (f"{lado}UpperLeg", (s * xl, 0, zq), (s * xl, 0, zj), "Hips"),
            (f"{lado}LowerLeg", (s * xl, 0, zj), (s * xl, 0, zt), f"{lado}UpperLeg"),
            (f"{lado}Foot", (s * xl, 0, zt), (s * xl, -0.07 * H, 0.015 * H), f"{lado}LowerLeg"),
            (f"{lado}Toes", (s * xl, -0.07 * H, 0.015 * H), (s * xl, -0.115 * H, 0.015 * H), f"{lado}Foot"),
        ]
    return lista


def criar_armadura(nome, H, w):
    dados = bpy.data.armatures.new(nome + "_esqueleto")
    arm = bpy.data.objects.new(nome + "_esqueleto", dados)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = dados.edit_bones
    for osso, cabeca, cauda, pai in ossos_padrao(H, w):
        b = eb.new(osso)
        b.head = cabeca
        b.tail = cauda
        b.roll = 0.0
        if pai:
            b.parent = eb[pai]
    bpy.ops.object.mode_set(mode="OBJECT")
    dados.display_type = "STICK"
    return arm


def construir_corpo(p, H, w):
    """Monta o corpo inteiro numa malha (cada parte presa a um osso)."""
    cor = lambda chave, padrao: c.cor_hex(p.get(chave) or padrao)
    tipo = TIPOS.get(p.get("tipo", "humano"), TIPOS["humano"])
    pele = c.material("pele", cor("cor_pele", tipo["pele"]), 0.65)
    roupa = c.material("roupa", cor("cor_roupa", "#7a2e22"), 0.8)
    roupa2 = c.material("roupa_secundaria", cor("cor_roupa_secundaria", "#3b3f4a"), 0.85)
    couro = c.material("couro", cor("cor_couro", "#4a3122"), 0.75)
    metal = c.material("metal", cor("cor_metal", "#9aa3ad"), 0.35, 0.9)
    cabelo = c.material("cabelo", cor("cor_cabelo", "#2b1d14"), 0.9)
    escuro = c.material("olhos", (0.02, 0.02, 0.025), 0.4)
    boca = c.material("boca", (0.25, 0.04, 0.05), 0.6)
    armadura = p.get("armadura", "leve")
    if armadura == "placas":
        armadura = "pesada"  # a Forja simples não tem placas separadas: usa a armadura pesada
    k = c.Construtor()

    xl = 0.06 * H * w
    zb = 0.80 * H
    # tronco
    k.caixa((0, 0, 0.535 * H), (0.17 * H * w, 0.10 * H, 0.075 * H), roupa2, "Hips")
    k.caixa((0, 0, 0.575 * H), (0.172 * H * w, 0.104 * H, 0.022 * H), couro, "Hips")  # cinto
    k.caixa((0, 0.0, 0.625 * H), (0.158 * H * w, 0.094 * H, 0.10 * H), roupa, "Spine")
    k.caixa((0, 0.0, 0.738 * H), (0.205 * H * w, 0.112 * H, 0.13 * H), roupa, "Chest")
    if armadura == "pesada":
        k.caixa((0, -0.004 * H, 0.735 * H), (0.215 * H * w, 0.118 * H, 0.12 * H), metal, "Chest")
        for s in (1, -1):
            k.esfera((s * 0.125 * H * w, 0, 0.805 * H), 0.05 * H, metal, f"{'Left' if s > 0 else 'Right'}UpperArm", escala=(1.15, 1.1, 0.7), u=8, v=6, liso=False)
    # pescoço e cabeça
    k.cilindro((0, 0, 0.79 * H), (0, 0, 0.86 * H), 0.03 * H, 0.027 * H, pele, "Neck")
    zcab = 0.915 * H
    k.esfera((0, 0, zcab), 0.068 * H, pele, "Head", escala=(1.0, 1.05, 1.12), u=10, v=8, liso=False)
    k.caixa((0, -0.072 * H, 0.905 * H), (0.013 * H, 0.014 * H, 0.018 * H), pele, "Head")  # nariz
    olho = (0.018 * H, 0.008 * H, 0.016 * H) if tipo.get("olhos_grandes") else (0.012 * H, 0.006 * H, 0.012 * H)
    for s in (1, -1):
        k.caixa((s * 0.025 * H, -0.066 * H, 0.918 * H), olho, escuro, "Head")
    k.caixa((0, -0.064 * H, 0.886 * H), (0.03 * H, 0.008 * H, 0.008 * H), boca, "Jaw")
    if tipo.get("cabelo") and p.get("cabelo", True):
        k.esfera((0, 0.008 * H, zcab + 0.004 * H), 0.073 * H, cabelo, "Head", escala=(1.03, 1.07, 1.1), u=10, v=8, liso=False, cortar_abaixo=zcab + 0.022 * H)
        k.caixa((0, 0.05 * H, zcab - 0.005 * H), (0.12 * H, 0.04 * H, 0.09 * H), cabelo, "Head")  # nuca
    if tipo.get("barba"):
        k.caixa((0, -0.05 * H, 0.87 * H), (0.09 * H, 0.04 * H, 0.06 * H), cabelo, "Jaw")
    if tipo.get("orelhas"):
        for s in (1, -1):
            k.cone((s * 0.058 * H, 0.0, 0.92 * H), (s * 0.11 * H, 0.012 * H, 0.95 * H), 0.012 * H, pele, "Head")
    if tipo.get("chifres") or p.get("chifres"):
        for s in (1, -1):
            k.cone((s * 0.035 * H, 0, 0.965 * H), (s * 0.06 * H, 0.01 * H, 1.04 * H), 0.014 * H, couro, "Head")
    if tipo.get("presas"):
        for s in (1, -1):
            k.cone((s * 0.015 * H, -0.058 * H, 0.878 * H), (s * 0.017 * H, -0.06 * H, 0.905 * H), 0.005 * H, c.material("osso", (0.9, 0.86, 0.75), 0.6), "Jaw")
    if p.get("capuz"):
        k.esfera((0, 0.008 * H, zcab + 0.004 * H), 0.075 * H, roupa2, "Head", escala=(1.05, 1.1, 1.12), u=10, v=8, liso=False, cortar_abaixo=zcab - 0.03 * H)
    if armadura == "pesada" and p.get("elmo", True):
        k.esfera((0, 0.0, zcab + 0.01 * H), 0.072 * H, metal, "Head", escala=(1.02, 1.06, 1.05), u=10, v=8, liso=False, cortar_abaixo=zcab + 0.012 * H)
    # braços
    manga = roupa if armadura != "nenhuma" else pele
    for lado, s in (("Left", 1), ("Right", -1)):
        k.esfera((s * 0.105 * H * w, 0, zb - 0.005 * H), 0.043 * H * w, manga, f"{lado}UpperArm", escala=(1.0, 1.0, 0.95), u=8, v=6, liso=False)
        k.cilindro((s * 0.10 * H * w, 0, zb), (s * 0.28 * H, 0, zb), 0.034 * H * w, 0.029 * H * w, manga, f"{lado}UpperArm")
        k.cilindro((s * 0.28 * H, 0, zb), (s * 0.43 * H, 0, zb), 0.028 * H * w, 0.023 * H * w, pele, f"{lado}LowerArm")
        if armadura in ("leve", "pesada"):
            k.cilindro((s * 0.36 * H, 0, zb), (s * 0.425 * H, 0, zb), 0.03 * H * w, 0.027 * H * w, couro if armadura == "leve" else metal, f"{lado}LowerArm")
        k.caixa((s * 0.468 * H, 0, zb), (0.075 * H, 0.04 * H, 0.03 * H), pele, f"{lado}Hand")
    # pernas
    bota = couro
    for lado, s in (("Left", 1), ("Right", -1)):
        k.cilindro((s * xl, 0, 0.535 * H), (s * xl, 0, 0.285 * H), 0.052 * H * w, 0.04 * H * w, roupa2, f"{lado}UpperLeg")
        k.cilindro((s * xl, 0, 0.285 * H), (s * xl, 0, 0.10 * H), 0.039 * H * w, 0.031 * H * w, roupa2, f"{lado}LowerLeg")
        k.cilindro((s * xl, 0, 0.17 * H), (s * xl, 0, 0.05 * H), 0.037 * H * w, 0.034 * H * w, bota, f"{lado}LowerLeg")
        k.caixa((s * xl, -0.03 * H, 0.025 * H), (0.064 * H * w, 0.115 * H, 0.05 * H), bota, f"{lado}Foot")
        k.caixa((s * xl, -0.095 * H, 0.02 * H), (0.06 * H * w, 0.04 * H, 0.04 * H), bota, f"{lado}Toes")
    if p.get("capa"):
        k.caixa((0, 0.068 * H, 0.60 * H), (0.22 * H * w, 0.012 * H, 0.40 * H), roupa2, "Chest")
    return k


def prender_no_osso(obj, arm, osso, matriz_mundo):
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = osso
    bpy.context.view_layer.update()
    obj.matrix_world = matriz_mundo


def criar_personagem(p):
    """Cria o personagem e devolve (armadura, corpo, arma ou None)."""
    import fc_armas

    tipo = TIPOS.get(p.get("tipo", "humano"), TIPOS["humano"])
    H = float(p.get("altura") or tipo["altura"])
    porte = {"magro": 0.85, "medio": 1.0, "forte": 1.2}.get(p.get("porte", ""), tipo["porte"])
    nome = p.get("id", "personagem")
    arm = criar_armadura(nome, H, porte)
    k = construir_corpo(p, H, porte)
    corpo = k.objeto(nome)
    corpo.parent = arm
    mod = corpo.modifiers.new("esqueleto", "ARMATURE")
    mod.object = arm
    # encaixes (cintura e costas) para armas guardadas
    for encaixe, osso, pos in (("encaixe_cintura", "Hips", (0.1 * H, 0, 0.55 * H)), ("encaixe_costas", "Chest", (0, 0.08 * H, 0.75 * H))):
        e = bpy.data.objects.new(encaixe, None)
        e.empty_display_size = 0.05
        bpy.context.scene.collection.objects.link(e)
        prender_no_osso(e, arm, osso, Matrix.Translation(pos))
    arma = None
    tipo_arma = p.get("arma")
    if tipo_arma and tipo_arma != "nenhuma":
        arma = fc_armas.criar_arma({"tipo": tipo_arma, "id": f"{nome}_{tipo_arma}", "cor_metal": p.get("cor_metal"), "cor_couro": p.get("cor_couro"), "escala": H / 1.8})
        # Na T-pose a mão direita aponta para -X; a lâmina fica para a frente (-Y).
        mao = Vector((-0.468 * H, 0, 0.80 * H))
        # Queremos a arma para a frente e um pouco para baixo com o braço caído (girado -72° em Y);
        # na T-pose isso é a direção desfeita por essa rotação.
        final = Vector((0.0, -0.75, -0.66)).normalized()
        repouso = Matrix.Rotation(math.radians(72), 3, "Y") @ final
        rot = Vector((0, 0, 1)).rotation_difference(repouso).to_matrix().to_4x4()
        prender_no_osso(arma, arm, "RightHand", Matrix.Translation(mao) @ rot)
        e = bpy.data.objects.new("encaixe_mao_direita", None)
        e.empty_display_size = 0.05
        bpy.context.scene.collection.objects.link(e)
        prender_no_osso(e, arm, "RightHand", Matrix.Translation(mao))
    return arm, corpo, arma
