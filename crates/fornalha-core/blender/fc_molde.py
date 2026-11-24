# Fornalha: malha humanoide de fora (3D pela IA) com o MESMO esqueleto e a mesma qualidade de pesos do
# humano da Fornalha (MakeHuman, CC0): um corpo-molde do MakeHuman é encaixado nas juntas medidas na
# malha (pose por osso: cabeça na junta, ponta na direção da próxima, comprimento igual), vira a pose
# de descanso, e os pesos dele passam para a malha da IA pela superfície mais próxima (onde a superfície
# bate de perto e na mesma direção); o resto (capa, saia, ombreira solta) é preenchido pelos vizinhos na
# própria malha. O esqueleto final tem dedos: a captura de movimento e a pegada da arma são as do humano.
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import fc_rig_ia

# corpo-molde: homem adulto de porte médio (só serve de guia para os pesos)
MACRO = {"genero": 1.0, "idade": 0.5, "musculo": 0.6, "peso": 0.55, "altura": 0.6, "proporcoes": 0.75}

# ordem de encaixe (pai antes do filho); mão e cabeça escalam por igual (dedos e rosto vão junto)
ENCAIXE = ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head",
           "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l", "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
           "thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r"]
UNIFORMES = {"hand_l", "hand_r", "head"}
ROSTO = ("jaw", "eye_l", "eye_r", "eyelid_upper_l", "eyelid_upper_r", "eyelid_lower_l", "eyelid_lower_r")


def _ativo(obj):
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj


def _co(obj):
    m = obj.matrix_world
    return np.array([(m @ v.co)[:] for v in obj.data.vertices])


def encaixar(arm, pontos, H_molde, H):
    """Pose do esqueleto do molde com as juntas nos pontos medidos na malha da IA."""
    _ativo(arm)
    bpy.ops.object.mode_set(mode="POSE")
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.matrix_basis = Matrix()
    bpy.context.view_layer.update()
    for nome in ENCAIXE:
        if nome not in arm.pose.bones or nome not in pontos:
            continue
        pb = arm.pose.bones[nome]
        b = pb.bone
        ha, ta = Vector(pontos[nome][0]), Vector(pontos[nome][1])
        rest = b.matrix_local.to_3x3().normalized()
        y0 = rest.col[1].normalized()
        alvo = ta - ha
        if alvo.length < 1e-5:
            continue
        giro = y0.rotation_difference(alvo.normalized()).to_matrix()
        s = alvo.length / max(b.length, 1e-6)
        if nome in UNIFORMES:
            esc = Matrix.Diagonal((s, s, s))
        else:
            esc = Matrix.Diagonal((1.0, s, 1.0))
        m3 = giro @ rest @ esc
        m4 = m3.to_4x4()
        m4.translation = ha
        pb.matrix = m4
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")


def _pesos_da_malha(obj, nomes):
    """Matriz (vértices × ossos) dos grupos de vértices."""
    idx = {n: i for i, n in enumerate(nomes)}
    W = np.zeros((len(obj.data.vertices), len(nomes)), dtype=np.float32)
    mapa = {g.index: idx[g.name] for g in obj.vertex_groups if g.name in idx}
    for v in obj.data.vertices:
        for g in v.groups:
            k = mapa.get(g.group)
            if k is not None:
                W[v.index, k] = g.weight
    return W


def _mascara_por_regiao(obj, arm, nomes, H):
    """Que ossos podem pesar em cada vértice, pela geometria (o molde não tem capa nem saia: sem isso a
    frente da sobreveste pegava o peso da mão do molde)."""
    co = _co(obj)
    mw = arm.matrix_world
    seg = {}
    for b in arm.data.bones:
        seg[b.name] = (np.array(mw @ b.head_local), np.array(mw @ b.tail_local))

    def dist(n):
        a, b = seg[n]
        ab = b - a
        t = np.clip(((co - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
        prox = a + t[:, None] * ab
        return np.linalg.norm(co - prox, axis=1), prox
    pode = np.ones((len(co), len(nomes)), dtype=bool)
    idx = {n: i for i, n in enumerate(nomes)}
    for lado in "lr":
        s_lado = 1.0 if lado == "l" else -1.0
        d_up, p_up = dist(f"upperarm_{lado}")
        d_lo, p_lo = dist(f"lowerarm_{lado}")
        d_ha, p_ha = dist(f"hand_{lado}")
        dentro = ((d_lo < 0.06 * H) & (s_lado * (co[:, 0] - p_lo[:, 0]) < -0.028 * H)) | \
                 ((d_ha < 0.06 * H) & (s_lado * (co[:, 0] - p_ha[:, 0]) < -0.028 * H))
        # a capa pendurada atrás do braço não é braço (só o que encosta no osso)
        atras = (((co[:, 1] - p_up[:, 1]) > 0.035 * H) & (d_up > 0.04 * H)) | \
                (((co[:, 1] - p_lo[:, 1]) > 0.018 * H) & (d_lo > 0.025 * H)) | \
                (((co[:, 1] - p_ha[:, 1]) > 0.018 * H) & (d_ha > 0.025 * H))
        braco = ((d_up < 0.08 * H) & ~atras) | (((d_lo < 0.05 * H) | (d_ha < 0.05 * H)) & ~dentro & ~atras)
        # depois da ponta dos dedos é pano (a beirada da capa ou da saia logo abaixo da mão)
        a_h, b_h = seg[f"hand_{lado}"]
        ab_h = b_h - a_h
        t_h = ((co - a_h) @ ab_h) / max(float(ab_h @ ab_h), 1e-12)
        alem = (t_h > 0.97) & (d_ha > 0.03 * H)
        braco &= ~alem
        mao = (d_ha < 0.06 * H) & ~dentro & ~atras & ~alem
        for n in nomes:
            if n.endswith(f"_{lado}") and n.split("_")[0] in ("upperarm", "lowerarm", "clavicle"):
                pode[:, idx[n]] &= braco | (n.startswith("clavicle") & (co[:, 2] > 0.7 * H))
            if n.endswith(f"_{lado}") and (n.startswith("hand") or n.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky")):
                pode[:, idx[n]] &= mao
        for n in (f"thigh_{lado}", f"calf_{lado}", f"foot_{lado}", f"ball_{lado}"):
            if n in idx:
                d, prox = dist(n)
                # a capa pendurada atrás da perna não é perna (só o que encosta na grevas/coxote)
                atras_perna = ((co[:, 1] - prox[:, 1]) > 0.045 * H) & (d > 0.05 * H)
                pode[:, idx[n]] &= (d < 0.11 * H) & ~atras_perna
    if "head" in idx:
        pode[:, idx["head"]] &= co[:, 2] > 0.8 * H
        # elmo, capuz e cabeça inteiros na cabeça (o molde é menor que um elmo: a nuca do elmo pegava o
        # peito e entortava ao virar a cabeça)
        h0 = seg["head"][0]
        acima = (co[:, 2] > h0[2] + 0.015 * H) & (np.linalg.norm(co[:, :2] - h0[:2], axis=1) < 0.12 * H)
        for n in nomes:
            if n != "head":
                pode[acima, idx[n]] = False
    # distância a cada osso (para preencher quem ficou sem peso permitido)
    D = np.stack([dist(n)[0] for n in nomes], axis=1)
    return pode, D


def transferir(molde, obj, nomes, H, pode=None, D=None):
    """Pesos do molde para a malha: pela superfície mais próxima quando ela está perto e virada para o
    mesmo lado; o resto é preenchido pelos vizinhos (difusão na malha). Devolve a matriz de pesos."""
    Wm = _pesos_da_malha(molde, nomes)
    me = molde.data
    tris = []
    for p in me.polygons:
        vs = list(p.vertices)
        for k in range(1, len(vs) - 1):
            tris.append((vs[0], vs[k], vs[k + 1]))
    tris = np.array(tris, dtype=np.int64)
    cm = _co(molde)
    bvh = BVHTree.FromPolygons([Vector(v) for v in cm], [tuple(t) for t in tris], all_triangles=True)
    co = _co(obj)
    nrm_mw = obj.matrix_world.to_3x3().inverted().transposed()
    nrm = np.array([(nrm_mw @ v.normal).normalized()[:] for v in obj.data.vertices])
    W = np.zeros((len(co), len(nomes)), dtype=np.float32)
    conhecido = np.zeros(len(co), dtype=bool)
    lim = 0.035 * H
    for i in range(len(co)):
        loc, n, ti, d = bvh.find_nearest(Vector(co[i]), 0.12 * H)
        if loc is None:
            continue
        a, b, c = (cm[j] for j in tris[ti])
        # baricêntricas do ponto no triângulo
        v0, v1, v2 = b - a, c - a, np.array(loc) - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-14:
            u, v, w = 1.0, 0.0, 0.0
        else:
            v = (d11 * d20 - d01 * d21) / den
            w = (d00 * d21 - d01 * d20) / den
            u = 1.0 - v - w
        W[i] = u * Wm[tris[ti][0]] + v * Wm[tris[ti][1]] + w * Wm[tris[ti][2]]
        # perto e na mesma direção (a superfície de fora do braço não serve para o pano ao lado)
        if d < lim and float(np.dot(nrm[i], n)) > 0.35:
            conhecido[i] = True
        elif d < 0.6 * lim:
            conhecido[i] = True
    if pode is not None:
        # só os ossos que fazem sentido ali; se não sobrar nada, o vértice é preenchido pelos vizinhos
        W = np.where(pode, W, 0.0)
        conhecido &= W.sum(1) > 0.3
    # vizinhos pela malha da IA
    arestas = np.array([e.vertices[:] for e in obj.data.edges], dtype=np.int64)
    if len(arestas) and (~conhecido).any():
        a, b = arestas[:, 0], arestas[:, 1]
        grau = np.zeros(len(co), dtype=np.float32)
        np.add.at(grau, a, 1.0)
        np.add.at(grau, b, 1.0)
        grau = np.maximum(grau, 1.0)[:, None]
        livre = ~conhecido
        # começa do palpite da superfície mais próxima e só os desconhecidos mudam
        for _ in range(140):
            soma = np.zeros_like(W)
            np.add.at(soma, a, W[b])
            np.add.at(soma, b, W[a])
            W[livre] = (soma / grau)[livre]
    W = np.clip(W, 0.0, None)
    if pode is not None:
        # a difusão espalha peso por pedaços soltos (a bainha pendurada perto da mão ganhava a mão):
        # a regra de região vale de novo, e quem fica sem peso vai para o osso permitido mais perto
        W = np.where(pode, W, 0.0)
        vazio = W.sum(1) < 0.2
        if vazio.any() and D is not None:
            dedos = np.array([n.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky") for n in nomes])
            Dv = np.where(pode[vazio] & ~dedos[None, :], D[vazio], np.inf)
            w = 1.0 / (Dv + 0.01 * H) ** 4
            w[~np.isfinite(Dv)] = 0.0
            W[vazio] = w
    s = W.sum(1, keepdims=True)
    s[s < 1e-6] = 1.0
    return W / s, conhecido


def gravar_pesos(obj, nomes, W, minimo=0.01):
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    grupos = [obj.vertex_groups.new(name=n) for n in nomes]
    # até 4 ossos por vértice (o que a engine usa), renormalizado
    top = np.argsort(-W, axis=1)[:, :4]
    for vi in range(len(W)):
        ks = top[vi]
        ws = W[vi, ks]
        t = ws.sum()
        if t <= 1e-6:
            continue
        for k, w in zip(ks, ws / t):
            if w > minimo:
                grupos[k].add([vi], float(w), "REPLACE")


def rigar(obj, nome, altura, makehuman):
    """Malha humanoide da IA → (armadura do humano da Fornalha, info). A malha fica pesada e presa nela."""
    import fc_humano

    fc_rig_ia.normalizar(obj, altura)
    pontos, H = fc_rig_ia.medir(obj)
    h = fc_humano.Humano(makehuman["dados"], makehuman["assets"], {"macro": MACRO})
    molde = h.corpo(nome + "_molde")
    arm = h.esqueleto(nome)
    h.pesar(molde)
    H_molde = float(max(v.co.z for v in molde.data.vertices))
    # o rosto não serve na malha da IA (elmo, capuz): sai do esqueleto e os pesos vão para a cabeça
    _ativo(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for n in ROSTO:
        eb = arm.data.edit_bones.get(n)
        if eb:
            arm.data.edit_bones.remove(eb)
    bpy.ops.object.mode_set(mode="OBJECT")
    for n in ROSTO:
        g = molde.vertex_groups.get(n)
        if g:
            gh = molde.vertex_groups.get("head") or molde.vertex_groups.new(name="head")
            for v in molde.data.vertices:
                for gg in v.groups:
                    if gg.group == g.index and gg.weight > 0:
                        gh.add([v.index], gg.weight, "ADD")
            molde.vertex_groups.remove(g)
    encaixar(arm, pontos, H_molde, H)
    # a forma do molde na pose vira malha fixa (o modificador aplicado) e a pose vira o descanso
    _ativo(molde)
    for m in list(molde.modifiers):
        if m.type == "ARMATURE":
            bpy.ops.object.modifier_apply(modifier=m.name)
    molde.parent = None
    _ativo(arm)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    nomes = [b.name for b in arm.data.bones if b.name != "Root"]
    pode, D = _mascara_por_regiao(obj, arm, nomes, H)
    W, conhecido = transferir(molde, obj, nomes, H, pode, D)
    gravar_pesos(obj, nomes, W)
    bpy.data.objects.remove(molde, do_unlink=True)
    # saia e capa: as mesmas regras do esqueleto medido (barra pela malha; cadeia de molas na capa)
    capa = fc_rig_ia.cadeia_da_capa(obj, arm, H)
    co = _co(obj)
    mw = arm.matrix_world
    saia = fc_rig_ia._saia(co, H, arm, mw)
    print(f"[molde] saia: {'barra a %.2f m, %d vértices' % (saia[4], int(saia[0].sum())) if saia is not None else 'não achada'}")
    paineis = []
    if saia is not None:
        # a mão pendurada ao lado da saia continua da mão
        ii = {n: i for i, n in enumerate(nomes)}
        mao = pode[:, ii["hand_l"]] | pode[:, ii["hand_r"]] | pode[:, ii["lowerarm_l"]] | pode[:, ii["lowerarm_r"]]
        mascara, p_quadril, lado_l, canela, _ = saia
        for vi in np.where(mascara & ~mao)[0]:
            v = obj.data.vertices[int(vi)]
            for gg in list(v.groups):
                obj.vertex_groups[gg.group].remove([int(vi)])
            # o pano fica mais no quadril (na corrida a canela vai longe e esticava a barra): no máximo
            # um quarto do peso nas coxas, só na barra
            p = 0.5 + 0.5 * float(p_quadril[vi])
            wl = float(lado_l[vi])
            osso = "thigh"
            for n, w in (("pelvis", p), (f"{osso}_l", (1 - p) * wl), (f"{osso}_r", (1 - p) * (1 - wl))):
                if w > 0.01:
                    obj.vertex_groups[n].add([int(vi)], w, "REPLACE")
    if capa:
        fc_rig_ia.pesar_capa(obj, arm, H)
    _ativo(obj)
    try:
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.4, repeat=2)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    except Exception as e:
        print(f"[molde] sem alisar: {e}")
    finally:
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    obj.parent = arm
    mod = obj.modifiers.new("esqueleto", "ARMATURE")
    mod.object = arm
    return arm, {"altura_m": round(H, 3), "pesos": "molde-makehuman", "ossos": len(arm.data.bones),
                 "pesos_pela_superficie": round(float(conhecido.mean()), 3), "molas": capa, "paineis": paineis}
