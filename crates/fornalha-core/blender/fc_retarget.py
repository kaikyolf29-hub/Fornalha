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


# ACCAD (Ohio State, CC BY 3.0): nomes do Mixamo sem prefixo, com ToSpine
_ACCAD = dict(_MIXAMO, **{"ToSpine": "spine_01", "Spine": "spine_02", "Spine1": "spine_03"})
# 100STYLE (Ian Mason, CC BY 4.0)
_100STYLE = {"Hips": "pelvis", "Chest": "spine_01", "Chest2": "spine_02", "Chest4": "spine_03", "Neck": "neck_01", "Head": "head"}
for _L, _l in (("Left", "_l"), ("Right", "_r")):
    _100STYLE.update({f"{_L}Collar": "clavicle" + _l, f"{_L}Shoulder": "upperarm" + _l, f"{_L}Elbow": "lowerarm" + _l, f"{_L}Wrist": "hand" + _l,
                      f"{_L}Hip": "thigh" + _l, f"{_L}Knee": "calf" + _l, f"{_L}Ankle": "foot" + _l, f"{_L}Toe": "ball" + _l})


def mapa_do_esqueleto(nomes):
    """Mapa nome-da-fonte → nome do esqueleto de jogo, pelo conjunto de ossos (algumas convenções usam
    o mesmo nome para ossos diferentes, como "Spine")."""
    curtos = {n.split(":")[-1] for n in nomes}
    if "ToSpine" in curtos and "LeftUpLeg" in curtos:
        return {n: _ACCAD[n.split(":")[-1]] for n in nomes if n.split(":")[-1] in _ACCAD}
    if "Chest2" in curtos and "LeftHip" in curtos:
        return {n: _100STYLE[n.split(":")[-1]] for n in nomes if n.split(":")[-1] in _100STYLE}
    if "LeftUpLeg" in curtos and "Spine1" in curtos and "LowerBack" not in curtos:
        # Mixamo sem o prefixo "mixamorig:" (exportado de outro programa)
        return {n: _MIXAMO[n.split(":")[-1]] for n in nomes if n.split(":")[-1] in _MIXAMO}
    return {n: p for n in nomes if (p := nome_padrao(n))}


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
        # capturas a 60 ou 120 qps entram no ritmo da cena (30 qps)
        bpy.ops.import_anim.bvh(filepath=caminho, rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y", use_fps_scale=True, update_scene_fps=False)
    else:
        raise ValueError(f"formato de animação não suportado: {ext}")
    novos = [o for o in bpy.data.objects if o not in antes]
    acoes = [a for a in bpy.data.actions if a not in acoes_antes]
    arm = next((o for o in novos if o.type == "ARMATURE"), None)
    return arm, novos, acoes


def _rot(m):
    return m.to_3x3().normalized()


# filho que dá a direção de cada osso (a ponta do osso no BVH e em outros programas é arbitrária quando
# o osso tem vários filhos; a cabeça do filho certo não é)
PRIMARIO = {"pelvis": "spine_01", "spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "neck_01", "neck_01": "head"}
for _l in ("l", "r"):
    PRIMARIO.update({f"clavicle_{_l}": f"upperarm_{_l}", f"upperarm_{_l}": f"lowerarm_{_l}", f"lowerarm_{_l}": f"hand_{_l}",
                     f"hand_{_l}": f"middle_01_{_l}", f"thigh_{_l}": f"calf_{_l}", f"calf_{_l}": f"foot_{_l}", f"foot_{_l}": f"ball_{_l}"})
    for _d in _DEDOS:
        PRIMARIO.update({f"{_d}_01_{_l}": f"{_d}_02_{_l}", f"{_d}_02_{_l}": f"{_d}_03_{_l}"})


def _quadro_do_quadril(cabeca, esq, dir_, cima):
    """Base (3x3) do corpo: x para a esquerda do personagem, z para cima, y para trás (frente = -y)."""
    x = (esq - dir_)
    z = cima.normalized()
    x = (x - z * x.dot(z)).normalized()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed()


class Retarget:
    """Retarget por pose: a fonte é posta, osso por osso do quadril para as pontas, na pose de descanso
    do alvo (o quadril pela base do corpo; cada osso pela direção até o filho certo, girando o mínimo
    a partir do pai). Daí em diante, cada osso do alvo faz o mesmo giro que o osso da fonte faz a partir
    dessa pose. Funciona com fontes de descanso esquisito (BVH com a coluna deitada, A-pose, T-pose)
    sem torcer os ossos."""

    def __init__(self, fonte, alvo, quadro_ref=None):
        """quadro_ref: quadro da animação da fonte que serve de pose de referência (no lugar do descanso),
        para fontes de descanso que não é uma pose natural (BVH de alguns programas)."""
        self.S = fonte
        self.T = alvo
        self.pares = {}
        mapa = mapa_do_esqueleto([b.name for b in fonte.data.bones])
        for b in fonte.data.bones:
            p = mapa.get(b.name)
            if p and p in alvo.data.bones and p not in self.pares.values():
                self.pares[b.name] = p
        self.inverso = {v: k for k, v in self.pares.items()}
        mw_s, mw_t = fonte.matrix_world, alvo.matrix_world
        if quadro_ref is not None:
            bpy.context.scene.frame_set(int(quadro_ref))
            cab_s = {pb.name: mw_s @ pb.head for pb in fonte.pose.bones}
            cau_s = {pb.name: mw_s @ pb.tail for pb in fonte.pose.bones}
            rot_s = {pb.name: _rot(mw_s @ pb.matrix) for pb in fonte.pose.bones}
        else:
            cab_s = {b.name: mw_s @ b.head_local for b in fonte.data.bones}
            cau_s = {b.name: mw_s @ b.tail_local for b in fonte.data.bones}
            rot_s = {b.name: _rot(mw_s @ b.matrix_local) for b in fonte.data.bones}
        cab_t = {b.name: mw_t @ b.head_local for b in alvo.data.bones}
        cau_t = {b.name: mw_t @ b.tail_local for b in alvo.data.bones}

        def direcoes(t):
            c = PRIMARIO.get(t)
            s = self.inverso[t]
            if c and c in cab_t and c in self.inverso:
                ds, dt = cab_s[self.inverso[c]] - cab_s[s], cab_t[c] - cab_t[t]
                if ds.length > 1e-6 and dt.length > 1e-6:
                    return ds.normalized(), dt.normalized()
            ds, dt = cau_s[s] - cab_s[s], cau_t[t] - cab_t[t]
            if ds.length > 1e-6 and dt.length > 1e-6:
                return ds.normalized(), dt.normalized()
            return None

        # giro de cada osso da fonte até a pose do alvo (em mundo), do quadril para as pontas
        G = {}
        for b in self._ordem_de(fonte):
            pai = G.get(b.parent.name) if b.parent else Matrix.Identity(3)
            t = self.pares.get(b.name)
            g = pai
            if t == "pelvis" and all(x in self.inverso for x in ("thigh_l", "thigh_r", "spine_01")):
                Fs = _quadro_do_quadril(cab_s[b.name], cab_s[self.inverso["thigh_l"]], cab_s[self.inverso["thigh_r"]],
                                        cab_s[self.inverso["spine_01"]] - cab_s[b.name])
                Ft = _quadro_do_quadril(cab_t["pelvis"], cab_t["thigh_l"], cab_t["thigh_r"], cab_t["spine_01"] - cab_t["pelvis"])
                g = Ft @ Fs.transposed()
            elif t:
                d = direcoes(t)
                if d:
                    atual = (pai @ d[0]).normalized()
                    g = atual.rotation_difference(d[1]).to_matrix() @ pai
            G[b.name] = g
        self.ref_t = {}
        self.rest_s_inv = {}
        for s, t in self.pares.items():
            Rs = rot_s[s]
            Rt = _rot(mw_t @ alvo.data.bones[t].matrix_local)
            # a fonte "na pose do alvo": G @ Rs; o alvo nessa pose: Rt
            self.rest_s_inv[s] = (G[s] @ Rs).inverted()
            self.ref_t[t] = Rt
        pel_s = fonte.data.bones.get(self.inverso.get("pelvis", ""))
        pel_t = alvo.data.bones.get("pelvis")
        self.pelvis_s0 = (cab_s[pel_s.name] if quadro_ref is not None else mw_s @ pel_s.head_local) if pel_s else Vector()
        self.pelvis_t0 = (mw_t @ pel_t.head_local) if pel_t else Vector()
        self.escala = (self.pelvis_t0.z / self.pelvis_s0.z) if pel_s and self.pelvis_s0.z > 0.05 else 1.0
        self.ordem = []
        self.desvio = None

        def andar(b):
            self.ordem.append(b)
            for f in b.children:
                andar(f)

        for b in alvo.data.bones:
            if b.parent is None:
                andar(b)

    @staticmethod
    def _ordem_de(arm):
        ordem = []

        def andar(b):
            ordem.append(b)
            for f in b.children:
                andar(f)

        for b in arm.data.bones:
            if b.parent is None:
                andar(b)
        return ordem

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
                    if self.desvio is not None:
                        # "no lugar": tira o deslocamento do quadril no chão (e o giro do corpo fica)
                        atual = atual - self.desvio
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
