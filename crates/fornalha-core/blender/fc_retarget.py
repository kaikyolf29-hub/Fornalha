# Fornalha: passa animações de captura/biblioteca (Quaternius UAL 1 e 2, Mixamo,
# CMU em BVH) para o esqueleto de jogo do personagem. As poses de descanso podem ser
# diferentes (T-pose na fonte, A-pose no MakeHuman): cada osso do alvo é primeiro
# alinhado à direção do osso da fonte em descanso, e daí em diante segue a rotação
# da fonte quadro a quadro. O quadril leva o deslocamento, na escala do alvo.
import os
import re

import bpy
from mathutils import Matrix, Quaternion, Vector

# nome do osso na fonte → nome no esqueleto de jogo (padrão Unreal, o do MakeHuman)
_DEDOS = ("index", "middle", "ring", "pinky", "thumb")


def _mapa_ual1(n):
    m = re.match(r"DEF-(.+)$", n)
    if not m:
        return None
    s = m.group(1)
    lado = "_l" if s.endswith(".L") else "_r" if s.endswith(".R") else ""
    base = s[:-2] if lado else s
    tabela = {"hips": "pelvis", "spine.001": "spine_01", "spine.002": "spine_02", "spine.003": "spine_03", "neck": "neck_01", "head": "head",
              "shoulder": "clavicle", "upper_arm": "upperarm", "forearm": "lowerarm", "hand": "hand", "thigh": "thigh", "shin": "calf",
              "foot": "foot", "toe": "ball"}
    if base in tabela:
        return tabela[base] + lado
    d = re.match(r"(?:f_)?(index|middle|ring|pinky|thumb)\.0(\d)$", base)
    if d:
        return f"{d.group(1)}_0{d.group(2)}{lado}"
    return None


_MIXAMO = {"Hips": "pelvis", "Spine": "spine_01", "Spine1": "spine_02", "Spine2": "spine_03", "Neck": "neck_01", "Head": "head",
           "LeftShoulder": "clavicle_l", "LeftArm": "upperarm_l", "LeftForeArm": "lowerarm_l", "LeftHand": "hand_l",
           "RightShoulder": "clavicle_r", "RightArm": "upperarm_r", "RightForeArm": "lowerarm_r", "RightHand": "hand_r",
           "LeftUpLeg": "thigh_l", "LeftLeg": "calf_l", "LeftFoot": "foot_l", "LeftToeBase": "ball_l",
           "RightUpLeg": "thigh_r", "RightLeg": "calf_r", "RightFoot": "foot_r", "RightToeBase": "ball_r"}
_CMU = {"Hips": "pelvis", "LowerBack": "spine_01", "Spine": "spine_02", "Spine1": "spine_03", "Neck": "neck_01", "Head": "head",
        "LeftShoulder": "clavicle_l", "LeftArm": "upperarm_l", "LeftForeArm": "lowerarm_l", "LeftHand": "hand_l",
        "RightShoulder": "clavicle_r", "RightArm": "upperarm_r", "RightForeArm": "lowerarm_r", "RightHand": "hand_r",
        "LeftUpLeg": "thigh_l", "LeftLeg": "calf_l", "LeftFoot": "foot_l", "LeftToeBase": "ball_l",
        "RightUpLeg": "thigh_r", "RightLeg": "calf_r", "RightFoot": "foot_r", "RightToeBase": "ball_r"}


_SMPL = {"smpl_pelvis": "pelvis", "smpl_left_hip": "thigh_l", "smpl_right_hip": "thigh_r", "smpl_spine1": "spine_01",
         "smpl_left_knee": "calf_l", "smpl_right_knee": "calf_r", "smpl_spine2": "spine_02", "smpl_left_ankle": "foot_l",
         "smpl_right_ankle": "foot_r", "smpl_spine3": "spine_03", "smpl_left_foot": "ball_l", "smpl_right_foot": "ball_r",
         "smpl_neck": "neck_01", "smpl_left_collar": "clavicle_l", "smpl_right_collar": "clavicle_r", "smpl_head": "head",
         "smpl_left_shoulder": "upperarm_l", "smpl_right_shoulder": "upperarm_r", "smpl_left_elbow": "lowerarm_l",
         "smpl_right_elbow": "lowerarm_r", "smpl_left_wrist": "hand_l", "smpl_right_wrist": "hand_r"}


def nome_padrao(n):
    """Qualquer convenção conhecida → nome do esqueleto de jogo (ou None)."""
    if n in _SMPL:
        return _SMPL[n]
    if n.startswith("DEF-"):
        return _mapa_ual1(n)
    curto = n.split(":")[-1]
    if curto in _MIXAMO and n != curto:
        return _MIXAMO[curto]
    m = re.match(r"(Left|Right)Hand(Index|Middle|Ring|Pinky|Thumb)(\d)$", curto)
    if m:
        return f"{m.group(2).lower()}_0{m.group(3)}_{'l' if m.group(1) == 'Left' else 'r'}"
    if curto == "Head":
        return "head"
    if re.match(r"^(pelvis|spine_0\d|neck_01|head|clavicle_[lr]|upperarm_[lr]|lowerarm_[lr]|hand_[lr]|thigh_[lr]|calf_[lr]|foot_[lr]|ball_[lr]|"
                r"(index|middle|ring|pinky|thumb)_0[123]_[lr])$", curto):
        return curto
    if curto in _CMU:
        return _CMU[curto]
    return None


def _importar(caminho):
    antes = set(bpy.data.objects)
    acoes_antes = set(bpy.data.actions)
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=caminho)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=caminho, automatic_bone_orientation=False)
    elif ext == ".bvh":
        bpy.ops.import_anim.bvh(filepath=caminho, rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y")
    else:
        raise ValueError(f"formato de animação não suportado: {ext}")
    novos = [o for o in bpy.data.objects if o not in antes]
    acoes = [a for a in bpy.data.actions if a not in acoes_antes]
    arm = next((o for o in novos if o.type == "ARMATURE"), None)
    return arm, novos, acoes


def _rot(m):
    return m.to_3x3().normalized()


class Retarget:
    def __init__(self, fonte, alvo):
        self.S = fonte
        self.T = alvo
        self.pares = {}
        for b in fonte.data.bones:
            p = nome_padrao(b.name)
            if p and p in alvo.data.bones and p not in self.pares.values():
                self.pares[b.name] = p
        self.inverso = {v: k for k, v in self.pares.items()}
        mw_s, mw_t = fonte.matrix_world, alvo.matrix_world
        self.ref_t = {}
        self.rest_s_inv = {}
        for s, t in self.pares.items():
            bs, bt = fonte.data.bones[s], alvo.data.bones[t]
            Rs = _rot(mw_s @ bs.matrix_local)
            Rt = _rot(mw_t @ bt.matrix_local)
            dir_s = (mw_s.to_3x3() @ (bs.tail_local - bs.head_local)).normalized()
            dir_t = (mw_t.to_3x3() @ (bt.tail_local - bt.head_local)).normalized()
            alinhar = dir_t.rotation_difference(dir_s).to_matrix() if dir_s.length and dir_t.length else Matrix.Identity(3)
            self.ref_t[t] = alinhar @ Rt
            self.rest_s_inv[s] = Rs.inverted()
        pel_s = fonte.data.bones.get(self.inverso.get("pelvis", ""))
        pel_t = alvo.data.bones.get("pelvis")
        self.pelvis_s0 = (mw_s @ pel_s.head_local) if pel_s else Vector()
        self.pelvis_t0 = (mw_t @ pel_t.head_local) if pel_t else Vector()
        self.escala = (self.pelvis_t0.z / self.pelvis_s0.z) if pel_s and self.pelvis_s0.z > 0.05 else 1.0
        self.ordem = []

        def andar(b):
            self.ordem.append(b)
            for f in b.children:
                andar(f)

        for b in alvo.data.bones:
            if b.parent is None:
                andar(b)

    def quadro(self):
        """Poses do alvo (base local de cada osso) para o quadro atual da fonte."""
        mw_s, mw_t = self.S.matrix_world, self.T.matrix_world
        mw_t_inv = mw_t.inverted()
        mundo = {}
        bases = {}
        for b in self.ordem:
            pai = b.parent
            rest_rel = (pai.matrix_local.inverted() @ b.matrix_local) if pai else b.matrix_local
            pai_mundo = mundo[pai.name] if pai else mw_t
            sem_pose = pai_mundo @ rest_rel
            s = self.inverso.get(b.name)
            if s:
                pb_s = self.S.pose.bones[s]
                Ws = _rot(mw_s @ pb_s.matrix)
                Q = Ws @ self.rest_s_inv[s] @ self.ref_t[b.name]
                pos = sem_pose.to_translation()
                if b.name == "pelvis":
                    atual = mw_s @ pb_s.head
                    pos = self.pelvis_t0 + (atual - self.pelvis_s0) * self.escala
                desejado = Matrix.Translation(pos) @ Q.to_4x4()
                base = sem_pose.inverted() @ desejado
            else:
                base = Matrix.Identity(4)
            bases[b.name] = base
            mundo[b.name] = sem_pose @ base
        return bases

    def gravar(self, acao_fonte, nome, laco):
        self.S.animation_data_create()
        self.S.animation_data.action = acao_fonte
        ini, fim = (int(round(x)) for x in acao_fonte.frame_range)
        ad = self.T.animation_data or self.T.animation_data_create()
        velha = bpy.data.actions.get(nome)
        if velha:
            bpy.data.actions.remove(velha)
        act = bpy.data.actions.new(nome)
        act.use_fake_user = True
        ad.action = act
        for pb in self.T.pose.bones:
            pb.rotation_mode = "QUATERNION"
        cena = bpy.context.scene
        for f in range(ini, fim + 1):
            cena.frame_set(f)
            bases = self.quadro()
            k = f - ini + 1
            for pb in self.T.pose.bones:
                base = bases.get(pb.name, Matrix.Identity(4))
                loc, rot, _ = base.decompose()
                pb.rotation_quaternion = rot
                pb.keyframe_insert("rotation_quaternion", frame=k, group=pb.name)
                if pb.name == "pelvis":
                    pb.location = loc
                    pb.keyframe_insert("location", frame=k, group=pb.name)
        try:
            act.use_frame_range = True
            act.frame_start = 1
            act.frame_end = fim - ini + 1
            act.use_cyclic = laco
        except Exception:
            pass
        act["laco"] = laco
        return act


# nome no jogo → (biblioteca, clipe, em laço)
CLIPES = {
    "parado": ("ual1", "Idle_Loop", True),
    "andar": ("ual1", "Walk_Loop", True),
    "correr": ("ual1", "Jog_Fwd_Loop", True),
    "correr_rapido": ("ual1", "Sprint_Loop", True),
    "pular": ("ual1", "Jump_Start", False),
    "no_ar": ("ual1", "Jump_Loop", True),
    "aterrissar": ("ual1", "Jump_Land", False),
    "atacar": ("ual2", "Sword_Regular_A", False),
    "atacar_2": ("ual2", "Sword_Regular_B", False),
    "atacar_3": ("ual2", "Sword_Regular_C", False),
    "combo": ("ual2", "Sword_Regular_Combo", False),
    "defender": ("ual2", "Sword_Block", False),
    "parado_espada": ("ual1", "Sword_Idle", True),
    "esquivar": ("ual1", "Roll", False),
    "dano": ("ual1", "Hit_Chest", False),
    "dano_forte": ("ual2", "Hit_Knockback", False),
    "morrer": ("ual1", "Death01", False),
    "soco": ("ual1", "Punch_Jab", False),
    "soco_2": ("ual1", "Punch_Cross", False),
    "agachar": ("ual1", "Crouch_Idle_Loop", True),
    "agachado_andar": ("ual1", "Crouch_Fwd_Loop", True),
    "interagir": ("ual1", "Interact", False),
    "zumbi_parado": ("ual2", "Zombie_Idle_Loop", True),
    "zumbi_andar": ("ual2", "Zombie_Walk_Fwd_Loop", True),
    "zumbi_ataque": ("ual2", "Zombie_Scratch", False),
}
PADRAO = ["parado", "andar", "correr", "correr_rapido", "pular", "no_ar", "aterrissar", "atacar", "atacar_2", "atacar_3", "defender",
          "esquivar", "dano", "morrer", "parado_espada"]


def aplicar_biblioteca(alvo, fontes, nomes=None, clipes=None):
    """fontes: {"ual1": caminho.glb, "ual2": caminho.glb, ...}. Devolve as ações criadas."""
    tabela = dict(CLIPES)
    tabela.update(clipes or {})
    quero = nomes or PADRAO
    por_fonte = {}
    for n in quero:
        if n in tabela:
            por_fonte.setdefault(tabela[n][0], []).append(n)
    criadas = []
    for chave, lista in por_fonte.items():
        caminho = fontes.get(chave)
        if not caminho or not os.path.isfile(caminho):
            continue
        S, novos, acoes = _importar(caminho)
        if S is None:
            continue
        rt = Retarget(S, alvo)
        por_nome = {a.name.split("|")[-1]: a for a in acoes}
        for n in lista:
            clipe = tabela[n][1]
            a = por_nome.get(clipe) or next((x for k, x in por_nome.items() if k.endswith(clipe)), None)
            if a is None:
                continue
            criadas.append(rt.gravar(a, n, tabela[n][2]))
        for o in novos:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in acoes:
            bpy.data.actions.remove(a)
    if alvo.animation_data and criadas:
        alvo.animation_data.action = criadas[0]
    for pb in alvo.pose.bones:
        pb.location = Vector()
    return criadas
