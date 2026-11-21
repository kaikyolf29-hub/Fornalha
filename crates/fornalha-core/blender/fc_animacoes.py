# Fornalha: biblioteca de animações procedurais para o esqueleto padrão.
# As poses são escritas em eixos do mundo (frente = -Y, cima = +Z, esquerda = +X)
# e convertidas para o espaço de cada osso, então valem para qualquer altura e porte.
import math

import bpy
from mathutils import Quaternion, Vector

FPS = 30
ANIMACOES = ("parado", "andar", "correr", "pular", "atacar", "defender", "esquivar", "dano", "morrer")
EIXOS = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}


def _q(rotacoes):
    """Lista de (eixo, graus) aplicadas em ordem → quaternion no espaço da armadura."""
    q = Quaternion()
    for eixo, graus in rotacoes:
        q = Quaternion(EIXOS[eixo], math.radians(graus)) @ q
    return q


def _local(pb, q_mundo):
    R = pb.bone.matrix_local.to_3x3()
    return (R.inverted() @ q_mundo.to_matrix() @ R).to_quaternion()


def _desloc_local(pb, v):
    R = pb.bone.matrix_local.to_3x3()
    return R.inverted() @ Vector(v)


def base():
    """Pose de pé com os braços para baixo (a T-pose é só a do esqueleto)."""
    return {
        "LeftUpperArm": [("Y", 72)],
        "RightUpperArm": [("Y", -72)],
        "LeftLowerArm": [("Z", -14)],
        "RightLowerArm": [("Z", 14)],
        "LeftHand": [("Z", -6)],
        "RightHand": [("Z", 6)],
    }


def braco(lado, frente=0.0, abrir=0.0, cotovelo=14.0):
    """Braço caído que balança para a frente (graus) e abre para o lado."""
    s = 1 if lado == "Left" else -1
    return {
        f"{lado}UpperArm": [("Y", s * (72 - abrir)), ("X", -frente)],
        f"{lado}LowerArm": [("Z", -s * cotovelo)],
    }


def perna(lado, frente=0.0, joelho=0.0, pe=None):
    return {
        f"{lado}UpperLeg": [("X", -frente)],
        f"{lado}LowerLeg": [("X", joelho)],
        f"{lado}Foot": [("X", -(pe if pe is not None else (joelho - frente) * 0.5))],
    }


def juntar(*partes):
    p = {}
    for parte in partes:
        p.update(parte)
    return p


class Animador:
    def __init__(self, arm, altura):
        self.arm = arm
        self.H = altura
        self.acoes = []

    def acao(self, nome, quadros, chaves, laco=True):
        """chaves: lista de (quadro, poses, deslocamento_quadril, rotacao_raiz)."""
        arm = self.arm
        ad = arm.animation_data or arm.animation_data_create()
        act = bpy.data.actions.new(nome)
        act.use_fake_user = True
        ad.action = act
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
        for quadro, poses, quadril, raiz in chaves:
            for pb in arm.pose.bones:
                pb.rotation_quaternion = Quaternion()
                pb.location = Vector()
                if pb.name in poses:
                    pb.rotation_quaternion = _local(pb, _q(poses[pb.name]))
            hips = arm.pose.bones["Hips"]
            hips.location = _desloc_local(hips, [x * self.H for x in (quadril or (0, 0, 0))])
            if raiz:
                root = arm.pose.bones["Root"]
                root.rotation_quaternion = _local(root, _q(raiz))
            for pb in arm.pose.bones:
                pb.keyframe_insert(data_path="rotation_quaternion", frame=quadro, group=pb.name)
                if pb.name in ("Hips", "Root"):
                    pb.keyframe_insert(data_path="location", frame=quadro, group=pb.name)
        try:
            act.use_frame_range = True
            act.frame_start = 1
            act.frame_end = quadros
            act.use_cyclic = laco
        except Exception:
            pass
        act["laco"] = laco
        self.acoes.append(act)
        return act

    def tudo(self):
        H = self.H
        A = self.acao
        b = base()
        # parado: respiração
        A("parado", 60, [(1, b, (0, 0, 0), None), (31, juntar(b, {"Chest": [("X", 2)], "Spine": [("X", 1)]}), (0, 0, -0.004), None), (61, b, (0, 0, 0), None)])
        # andar
        def passo(esq_frente):
            s = 1 if esq_frente else -1
            return juntar(
                perna("Left", 24 * s, 6 if esq_frente else 22),
                perna("Right", -24 * s, 22 if esq_frente else 6),
                braco("Left", -20 * s),
                braco("Right", 20 * s),
                {"Spine": [("Z", 4 * s)], "Chest": [("Z", -6 * s)]},
            )
        def passando(esq_apoio):
            return juntar(
                perna("Left", 0 if esq_apoio else 8, 4 if esq_apoio else 40),
                perna("Right", 8 if esq_apoio else 0, 40 if esq_apoio else 4),
                braco("Left", 0),
                braco("Right", 0),
            )
        A("andar", 30, [
            (1, passo(True), (0, 0, -0.012), None),
            (8, passando(False), (0, 0, 0.006), None),
            (16, passo(False), (0, 0, -0.012), None),
            (23, passando(True), (0, 0, 0.006), None),
            (31, passo(True), (0, 0, -0.012), None),
        ])
        # correr
        def corrida(esq):
            s = 1 if esq else -1
            return juntar(
                perna("Left", 40 * s, 15 if esq else 75),
                perna("Right", -40 * s, 75 if esq else 15),
                braco("Left", -38 * s, 6, 85),
                braco("Right", 38 * s, 6, 85),
                {"Spine": [("X", 10)], "Chest": [("X", 4), ("Z", -8 * s)], "Head": [("X", -8)]},
            )
        A("correr", 20, [(1, corrida(True), (0, 0, -0.02), None), (6, corrida(True), (0, 0, 0.02), None), (11, corrida(False), (0, 0, -0.02), None), (16, corrida(False), (0, 0, 0.02), None), (21, corrida(True), (0, 0, -0.02), None)])
        # pular
        agacha = juntar(perna("Left", 40, 80, -30), perna("Right", 40, 80, -30), braco("Left", -25), braco("Right", -25), {"Spine": [("X", 18)]})
        estica = juntar(perna("Left", 0, 0, 10), perna("Right", 0, 0, 10), braco("Left", 150, 10, 10), braco("Right", 150, 10, 10))
        encolhe = juntar(perna("Left", 55, 70), perna("Right", 55, 70), braco("Left", 90, 20, 30), braco("Right", 90, 20, 30))
        A("pular", 30, [(1, b, (0, 0, 0), None), (7, agacha, (0, 0, -0.13), None), (12, estica, (0, 0, 0.04), None), (19, encolhe, (0, 0, 0.08), None), (25, agacha, (0, 0, -0.10), None), (31, b, (0, 0, 0), None)], laco=False)
        # atacar (golpe por cima, com a arma na mão direita)
        guarda = juntar(b, braco("Right", 35, 0, 40), {"Spine": [("Z", -5)]})
        prepara = juntar(b, {"RightUpperArm": [("Y", -60), ("X", -165)], "RightLowerArm": [("Z", 70)], "Chest": [("Z", 18)], "Spine": [("X", -6)]}, perna("Left", 15, 10), perna("Right", -10, 10))
        golpe = juntar(b, {"RightUpperArm": [("Y", -60), ("X", -30)], "RightLowerArm": [("Z", 5)], "Chest": [("Z", -22)], "Spine": [("X", 16)]}, perna("Left", 25, 30), perna("Right", -15, 10))
        A("atacar", 24, [(1, guarda, (0, 0, 0), None), (9, prepara, (0, 0, 0.005), None), (13, golpe, (0, 0, -0.03), None), (18, golpe, (0, 0, -0.03), None), (25, guarda, (0, 0, 0), None)], laco=False)
        # defender (guarda alta, segura)
        defesa = juntar(b, {"LeftUpperArm": [("Y", 30), ("X", -75)], "LeftLowerArm": [("Z", -95)], "RightUpperArm": [("Y", -50), ("X", -40)], "RightLowerArm": [("Z", 70)], "Spine": [("X", 6)]}, perna("Left", 15, 25), perna("Right", -10, 25))
        A("defender", 18, [(1, b, (0, 0, 0), None), (6, defesa, (0, 0, -0.03), None), (19, defesa, (0, 0, -0.03), None)], laco=False)
        # esquivar (passo rápido para o lado)
        abaixa = juntar(b, perna("Left", 20, 60), perna("Right", 20, 60), braco("Left", 20, 30), braco("Right", 20, 30), {"Spine": [("X", 20), ("Y", -10)]})
        A("esquivar", 20, [(1, b, (0, 0, 0), None), (6, abaixa, (-0.12, 0, -0.10), None), (13, abaixa, (-0.20, 0, -0.08), None), (21, b, (0, 0, 0), None)], laco=False)
        # dano
        A("dano", 14, [(1, b, (0, 0, 0), None), (4, juntar(b, {"Chest": [("X", -14)], "Head": [("X", -12)], "Spine": [("X", -6)]}, braco("Left", 10, 25), braco("Right", 10, 25)), (0, 0.02, 0), None), (15, b, (0, 0, 0), None)], laco=False)
        # morrer (cai de costas a partir dos pés)
        cai = juntar(b, {"Chest": [("X", -20)], "Head": [("X", -15)]}, perna("Left", 10, 40), perna("Right", 10, 40), braco("Left", 30, 40), braco("Right", 30, 40))
        caido = juntar(b, braco("Left", 60, 70, 10), braco("Right", 60, 70, 10), {"Head": [("Y", 20)]})
        A("morrer", 42, [(1, b, (0, 0, 0), None), (8, cai, (0, 0, -0.06), [("X", -12)]), (22, cai, (0, 0, -0.10), [("X", -70)]), (30, caido, (0, 0, 0.03), [("X", -90)]), (43, caido, (0, 0, 0.03), [("X", -90)])], laco=False)
        self.arm.animation_data.action = self.acoes[0]
        return self.acoes


def aplicar_biblioteca(arm, altura, nomes=None):
    an = Animador(arm, altura)
    acoes = an.tudo()
    if nomes:
        quero = set(nomes)
        ficam = [a for a in acoes if a.name in quero]
        saem = [a for a in acoes if a.name not in quero]
        if ficam:
            arm.animation_data.action = ficam[0]
        for a in saem:
            bpy.data.actions.remove(a)
        acoes = ficam
    return acoes
