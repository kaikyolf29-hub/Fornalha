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
        if nome.startswith("hand_"):
            # a mão da IA é medida até a ponta do punho fechado: os dedos do molde ficam no tamanho do
            # corpo (escalados pelo comprimento da mão eles iam a 30 cm do pulso e a pegada saía da manopla)
            u = H / max(H_molde, 1e-6)
            esc = Matrix.Diagonal((u, u, u))
        elif nome in UNIFORMES:
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
        # o lado do tronco e da sobreveste embaixo do braço (para dentro do eixo do braço) é do tronco:
        # antes ele subia junto quando o braço erguia a espada e virava uma cortina
        dentro_up = (s_lado * (co[:, 0] - p_up[:, 0]) < -0.03 * H) & (d_up > 0.035 * H)
        braco = ((d_up < 0.08 * H) & ~atras & ~dentro_up) | (((d_lo < 0.05 * H) | (d_ha < 0.05 * H)) & ~dentro & ~atras)
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


DEDOS = ("thumb", "index", "middle", "ring", "pinky")


def _ilhas(obj):
    """Número da peça de cada vértice: as ilhas do mapa de textura (existem mesmo com a malha soldada);
    sem UV, as partes ligadas por arestas."""
    me = obj.data
    n = len(me.vertices)
    if me.uv_layers:
        try:
            from bpy_extras import mesh_utils

            ilhas = np.full(n, -1, dtype=np.int64)
            for k, polis in enumerate(mesh_utils.mesh_linked_uv_islands(me)):
                for pi in polis:
                    for vi in me.polygons[pi].vertices:
                        if ilhas[vi] < 0:
                            ilhas[vi] = k
            sem = ilhas < 0
            ilhas[sem] = ilhas.max() + 1 + np.arange(int(sem.sum()))
            return ilhas
        except Exception as e:
            print(f"[molde] sem ilhas de UV: {e}")
    pai = np.arange(n)

    def raiz(x):
        r = x
        while pai[r] != r:
            r = pai[r]
        while pai[x] != r:
            pai[x], x = r, pai[x]
        return r
    for e in me.edges:
        a, b = raiz(e.vertices[0]), raiz(e.vertices[1])
        if a != b:
            pai[a] = b
    r = np.array([raiz(i) for i in range(n)])
    return np.unique(r, return_inverse=True)[1]


def _por_ilha(ilhas, m, maximo=1500):
    """A máscara vale para a peça inteira quando a maior parte dela está dentro (e some quando não).
    Peça grande demais (a sobreveste inteira numa ilha só) fica vértice a vértice."""
    tot = np.bincount(ilhas)
    den = np.bincount(ilhas, weights=m.astype(float), minlength=len(tot))
    voto = (den / np.maximum(tot, 1))[ilhas] > 0.5
    grande = tot[ilhas] > maximo
    return np.where(grande, m, voto)


def bracos_pelo_volume(obj, arm, nomes, W, H, D=None):
    """Braços pela divisão do volume da malha entre os ossos (fc_eixo.rotular): o que é do lobo do braço
    fica rígido por segmento, com transição curta no cotovelo e no pulso (como se pesa armadura); o que
    não é do braço não pega osso do braço — a sobreveste encostada na manopla deixa de ir junto com a
    mão. Devolve (W, máscara dos vértices do braço) ou (W, None) sem o campo."""
    import fc_eixo
    campo = fc_rig_ia.ULTIMO.get("campo")
    if campo is None:
        return W, None
    mw = arm.matrix_world
    ossos = {}
    for b in arm.data.bones:
        n = b.name
        if n == "Root" or n.split("_")[0] in DEDOS or n.startswith("capa"):
            continue
        ossos[n] = (np.array(mw @ b.head_local), np.array(mw @ b.tail_local))
    lab, ln = fc_eixo.rotular(campo, ossos)
    co = _co(obj)
    rv = fc_eixo.rotulo_dos_vertices(campo, lab, co)
    nome_v = np.array([ln[k] if k >= 0 else "" for k in rv])
    ilhas = _ilhas(obj)
    ii = {n: i for i, n in enumerate(nomes)}
    W = W.copy()
    do_braco = np.zeros(len(co), dtype=bool)
    b = 0.022 * H
    for lado in "lr":
        cadeia = [f"upperarm_{lado}", f"lowerarm_{lado}", f"hand_{lado}"]
        juntas = [ossos[cadeia[0]][0], ossos[cadeia[1]][0], ossos[cadeia[2]][0], ossos[cadeia[2]][1]]
        m = np.isin(nome_v, cadeia)
        # e perto da cadeia (ombreira larga, manopla justa); o que passa da ponta da mão é outra coisa
        # (o punho da espada embainhada encostado na mão, a bainha, a beirada do pano)
        s_all, d_all = fc_eixo.na_cadeia(co, juntas, distancia=True)
        c_cot0 = float(np.linalg.norm(juntas[1] - juntas[0]))
        c_pul0 = c_cot0 + float(np.linalg.norm(juntas[2] - juntas[1]))
        c_fim0 = c_pul0 + float(np.linalg.norm(juntas[3] - juntas[2]))
        raio = np.where(s_all < c_cot0, 0.085 * H, np.where(s_all < c_pul0, 0.06 * H, 0.05 * H))
        ab = juntas[3] - juntas[2]
        alem = ((co - juntas[3]) @ ab) / max(float(np.linalg.norm(ab)), 1e-9) > 0.02 * H
        n_rot = int(m.sum())
        m &= (d_all < raio) & ~alem
        n_raio = int(m.sum())
        # cada peça da malha (ilha) decide inteira: placa da armadura não rasga no meio, pano encostado
        # não fica meio no braço e meio no corpo
        m = _por_ilha(ilhas, m)
        print(f"[molde] braço {lado}: rotulado {n_rot}, no raio {n_raio}, por peça {int(m.sum())}")
        if not m.any():
            continue
        do_braco |= m
        s = s_all[m]
        c_cot = float(np.linalg.norm(juntas[1] - juntas[0]))
        c_pul = c_cot + float(np.linalg.norm(juntas[2] - juntas[1]))
        w_lo = fc_eixo.suave(c_cot - b, c_cot + b, s)
        w_ha = fc_eixo.suave(c_pul - 0.7 * b, c_pul + 0.7 * b, s)
        # o começo do braço divide com a clavícula (o ombro dobra macio)
        w_cl = 1.0 - fc_eixo.suave(0.0, 1.5 * b, s)
        linhas = np.zeros((int(m.sum()), len(nomes)), dtype=np.float32)
        linhas[:, ii[f"clavicle_{lado}"]] = w_cl * 0.5
        linhas[:, ii[cadeia[0]]] = (1 - w_lo) * (1 - w_cl * 0.5)
        linhas[:, ii[cadeia[1]]] = w_lo * (1 - w_ha) * (1 - w_cl * 0.5)
        linhas[:, ii[cadeia[2]]] = w_ha * (1 - w_cl * 0.5)
        # dedos da malha: da metade da mão para a ponta, os pesos dos dedos do molde (do tamanho do
        # corpo, encaixado no pulso): a manopla fecha na pegada da arma junto com a captura
        dedos_i = [i for n, i in ii.items() if n.endswith(f"_{lado}") and n.split("_")[0] in DEDOS]
        if dedos_i:
            c_fim = c_pul + float(np.linalg.norm(juntas[3] - juntas[2]))
            r_dedo = fc_eixo.suave(c_pul + 0.35 * (c_fim - c_pul), c_pul + 0.6 * (c_fim - c_pul), s)
            Wt = W[m][:, dedos_i]
            soma = Wt.sum(1)
            tem = soma > 0.05
            frac = np.where(tem, np.clip(soma, 0.0, 1.0), 0.0) * r_dedo
            Wd = np.where(tem[:, None], Wt / np.maximum(soma, 1e-6)[:, None], 0.0) * frac[:, None]
            linhas[:, dedos_i] = Wd
            linhas[:, ii[cadeia[2]]] *= 1.0 - frac
        W[m] = linhas
        print(f"[molde] braço {lado} pelo volume: {int(m.sum())} vértices "
              f"(mão {int(np.isin(nome_v[m], [cadeia[2]]).sum())})")
    # fora do lobo do braço, nada de osso do braço (o ombro do tronco ainda divide com o braço perto da
    # junta, para o deltoide não rasgar)
    braco_ii = [i for n, i in ii.items() if n.split("_")[0] in ("upperarm", "lowerarm", "hand") + DEDOS]
    fora = ~do_braco
    if fora.any():
        perto_ombro = np.zeros(len(co), dtype=bool)
        for lado in "lr":
            perto_ombro |= np.linalg.norm(co - ossos[f"upperarm_{lado}"][0], axis=1) < 0.07 * H
        zerar = fora & ~perto_ombro
        for i in braco_ii:
            W[zerar, i] = 0.0
        so_ombro = fora & perto_ombro
        for i in braco_ii:
            if not nomes[i].startswith("upperarm"):
                W[so_ombro, i] = 0.0
        vazio = fora & (W.sum(1) < 0.2)
        if vazio.any() and D is not None:
            ok = np.array([i not in braco_ii for i in range(len(nomes))])
            Dv = np.where(ok[None, :], D[vazio], np.inf)
            w = 1.0 / (Dv + 0.01 * H) ** 4
            w[~np.isfinite(Dv)] = 0.0
            W[vazio] = w
    s = W.sum(1, keepdims=True)
    s[s < 1e-6] = 1.0
    return W / s, do_braco


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


SAIA = "saia"


def _criar_osso_da_saia(arm, comprimento):
    """Osso "saia" do quadril até a barra, apontando para baixo (pai: a raiz, se houver)."""
    _ativo(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb_p = arm.data.edit_bones["pelvis"]
    eb = arm.data.edit_bones.new(SAIA)
    eb.head = eb_p.head.copy()
    eb.tail = eb_p.head - Vector((0.0, 0.0, max(comprimento, 0.05)))
    eb.align_roll(Vector((0.0, -1.0, 0.0)))
    raiz = arm.data.edit_bones.get("Root")
    eb.parent = raiz
    eb.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return SAIA


def assar_saia(arm, acoes, giro=0.25):
    """Grava em cada ação o osso da barra: no lugar do quadril, com o giro dele em volta do eixo
    vertical e só `giro` da inclinação (o pano pende de pé, como numa simulação parada)."""
    from mathutils import Quaternion

    if SAIA not in arm.pose.bones or not acoes:
        return 0
    cena = bpy.context.scene
    ad = arm.animation_data or arm.animation_data_create()
    antes = ad.action
    pp = arm.pose.bones["pelvis"]
    ps = arm.pose.bones[SAIA]
    ps.rotation_mode = "QUATERNION"
    rest_p = pp.bone.matrix_local.to_quaternion()
    rest_s = ps.bone.matrix_local
    # sem deformar a malha enquanto grava (só o esqueleto importa aqui)
    mods = []
    for o in bpy.data.objects:
        for m in getattr(o, "modifiers", []):
            if m.type == "ARMATURE" and m.object == arm and m.show_viewport:
                m.show_viewport = False
                mods.append(m)
    n = 0
    try:
        for a in acoes:
            ad.action = a
            try:
                if a.slots:
                    ad.action_slot = a.slots[0]
            except Exception:
                pass
            ini, fim = (int(round(x)) for x in a.frame_range)
            for f in range(ini, fim + 1):
                cena.frame_set(f)
                mp = pp.matrix
                q = mp.to_quaternion() @ rest_p.inverted()
                # giro em volta do eixo vertical (pela frente do corpo girada)
                frente = q @ Vector((0.0, -1.0, 0.0))
                yaw = Quaternion((0.0, 0.0, 1.0), float(np.arctan2(frente.x, -frente.y))) if frente.xy.length > 1e-6 else Quaternion()
                alvo = yaw.slerp(q, giro)
                m4 = (alvo.to_matrix().to_4x4() @ rest_s.to_3x3().to_4x4())
                m4.translation = mp.translation
                ps.matrix = m4
                ps.keyframe_insert("rotation_quaternion", frame=f, group=SAIA)
                ps.keyframe_insert("location", frame=f, group=SAIA)
            n += 1
    finally:
        for m in mods:
            m.show_viewport = True
        ad.action = antes
    return n


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
    W, do_braco = bracos_pelo_volume(obj, arm, nomes, W, H, D)
    gravar_pesos(obj, nomes, W)
    bpy.data.objects.remove(molde, do_unlink=True)
    # saia e capa: as mesmas regras do esqueleto medido (barra pela malha; cadeia de molas na capa)
    capa = fc_rig_ia.cadeia_da_capa(obj, arm, H)
    co = _co(obj)
    mw = arm.matrix_world
    saia = fc_rig_ia._saia(co, H, arm, mw)
    print(f"[molde] saia: {'barra a %.2f m, %d vértices' % (saia[4], int(saia[0].sum())) if saia is not None else 'não achada'}")
    paineis = []
    saia_osso = None
    if saia is not None:
        # a mão pendurada ao lado da saia continua da mão
        ii = {n: i for i, n in enumerate(nomes)}
        if do_braco is not None:
            mao = do_braco
        else:
            mao = pode[:, ii["hand_l"]] | pode[:, ii["hand_r"]] | pode[:, ii["lowerarm_l"]] | pode[:, ii["lowerarm_r"]]
        mascara, p_quadril, lado_l, canela, barra = saia
        # osso da barra: segue o quadril no lugar e no giro em volta do eixo vertical, mas fica de pé (a
        # barra rígida no quadril subia para trás quando a corrida inclina o quadril); na engine ganha mola
        quadril_z = float((mw @ arm.data.bones["pelvis"].head_local).z)
        saia_osso = _criar_osso_da_saia(arm, quadril_z - barra)
        tt = np.clip((co[:, 2] - barra) / max(quadril_z - barra, 1e-6), 0.0, 1.0)
        for vi in np.where(mascara & ~mao)[0]:
            v = obj.data.vertices[int(vi)]
            for gg in list(v.groups):
                obj.vertex_groups[gg.group].remove([int(vi)])
            # o pano fica mais no quadril (na corrida a canela vai longe e esticava a barra): no máximo
            # um quarto do peso nas coxas, só na barra
            p = 0.5 + 0.5 * float(p_quadril[vi])
            wl = float(lado_l[vi])
            osso = "thigh"
            q = 0.7 * (1.0 - float(tt[vi])) ** 1.5 if saia_osso else 0.0
            for n, w in (("pelvis", p * (1 - q)), (saia_osso, p * q), (f"{osso}_l", (1 - p) * wl),
                         (f"{osso}_r", (1 - p) * (1 - wl))):
                if n and w > 0.01:
                    g = obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n)
                    g.add([int(vi)], w, "REPLACE")
    pernas_separadas = separar_pernas(obj, arm, H, None if saia is None else saia[0])
    print(f"[molde] pernas separadas: {pernas_separadas} arestas abertas entre as pernas")
    # com saia (túnica, sobreveste, vestido), o pano abaixo dela é pano comprido, não calça
    perna_devolvida = pernas_sem_tronco(obj, arm, H, None, bool(capa)) if saia is None else 0
    print(f"[molde] calça atrás da perna devolvida à perna: {perna_devolvida} vértices")
    joelhos = joelhos_suaves(obj, arm, H, None if saia is None else saia[0], bool(capa))
    print(f"[molde] joelhos com a dobra suave: {joelhos} vértices")
    mao_solta = separar_bracos(obj, arm, H)
    print(f"[molde] braço solto do corpo: {mao_solta} arestas abertas")
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
    manopla = _manopla_firme(obj, arm)
    manopla += _pes_firmes(obj, arm)
    obj.parent = arm
    mod = obj.modifiers.new("esqueleto", "ARMATURE")
    mod.object = arm
    return arm, {"altura_m": round(H, 3), "pesos": "molde-makehuman", "ossos": len(arm.data.bones), "manopla_firme": manopla,
                 "pesos_pela_superficie": round(float(conhecido.mean()), 3), "molas": capa, "paineis": paineis,
                 "osso_da_saia": saia_osso, "pernas_separadas": pernas_separadas, "calca_devolvida_a_perna": perna_devolvida,
                 "braco_solto_do_corpo": mao_solta, "joelhos_suaves": joelhos}


def separar_pernas(obj, arm, H, fora=None):
    """A malha da IA vem com as pernas grudadas por uma membrana (da virilha até o meio da coxa, às vezes
    atrás das canelas). Com o peso das duas pernas, ela esticava em pontas ao andar (a calça "rasgava").
    Abaixo da virilha, perto dos ossos da perna, cada face fica com a perna do lado dela: a costura entre
    os dois lados é aberta (cada lado com os seus vértices) e cada lado perde o peso da outra perna.
    Saia (`fora`) e capa (atrás das pernas) ficam como estão: abrir o pano rasgaria. Devolve quantas
    arestas foram abertas."""
    import bmesh

    mw = arm.matrix_world
    ossos = arm.data.bones
    if not all(ossos.get(f"{n}_{lado}") for n in ("thigh", "calf") for lado in "lr"):
        return 0
    pelvis = mw @ ossos["pelvis"].head_local
    perna_y = float(np.mean([(mw @ ossos[f"thigh_{lado}"].head_local).y for lado in "lr"]))
    virilha = min((mw @ ossos[f"thigh_{lado}"].head_local).z for lado in "lr") - 0.03 * H
    segs = [(np.array(mw @ ossos[f"{n}_{lado}"].head_local), np.array(mw @ ossos[f"{n}_{lado}"].tail_local))
            for n in ("thigh", "calf") for lado in "lr"]
    fora_set = set(np.nonzero(fora)[0].tolist()) if fora is not None else set()
    mo = obj.matrix_world
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    centros = np.array([(mo @ f.calc_center_median())[:] for f in bm.faces])
    d_perna = np.full(len(centros), np.inf)
    for a, b in segs:
        d_perna = np.minimum(d_perna, fc_rig_ia._seg(centros, a, b))
    lado = {}
    for f, c, d in zip(bm.faces, centros, d_perna):
        if c[2] >= virilha or d > 0.09 * H or c[1] > perna_y + 0.06 * H:
            continue
        if fora_set and any(v.index in fora_set for v in f.verts):
            continue
        lado[f] = "l" if c[0] > pelvis.x else "r"
    cortar = [e for e in bm.edges if len({lado[f] for f in e.link_faces if f in lado}) == 2]
    if not cortar:
        bm.free()
        return 0
    bmesh.ops.split_edges(bm, edges=cortar)
    camada = bm.verts.layers.deform.active
    gi = {g.name: g.index for g in obj.vertex_groups}
    da_perna = {s: [gi[f"{n}_{s}"] for n in ("thigh", "calf", "foot", "ball") if f"{n}_{s}" in gi] for s in "lr"}
    if camada is not None:
        for v in bm.verts:
            lados = {lado.get(f) for f in v.link_faces}
            if len(lados) != 1 or None in lados:
                continue
            s = lados.pop()
            outro = "r" if s == "l" else "l"
            dv = v[camada]
            for g in da_perna[outro]:
                if g in dv:
                    del dv[g]
            total = sum(dv.values())
            if total > 1e-6:
                for k in list(dv.keys()):
                    dv[k] = dv[k] / total
            elif da_perna[s]:
                dv[da_perna[s][0]] = 1.0
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(cortar)


def separar_bracos(obj, arm, H):
    """A malha da IA cola a mão (e às vezes o antebraço) na coxa ou no quadril. Com os dois pesos, a
    pele entre eles esticava em pontas quando o braço balança. Abaixo da axila, cada face fica com o
    braço (se o peso dele domina) ou com o corpo; a costura entre os dois é aberta e cada lado perde os
    ossos do outro. Devolve quantas arestas foram abertas."""
    import bmesh

    ossos = arm.data.bones
    mw = arm.matrix_world
    if not all(ossos.get(f"upperarm_{lado}") for lado in "lr"):
        return 0
    axila = min((mw @ ossos[f"upperarm_{lado}"].head_local).z for lado in "lr") - 0.06 * H
    dedos = ("thumb", "index", "middle", "ring", "pinky")
    gi = {g.name: g.index for g in obj.vertex_groups}
    do_braco = {lado: {gi[n] for n in gi if n.endswith(f"_{lado}") and (n.split("_")[0] in ("upperarm", "lowerarm", "hand") + dedos)}
                for lado in "lr"}
    todos_braco = do_braco["l"] | do_braco["r"]
    mo = obj.matrix_world
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    camada = bm.verts.layers.deform.active
    if camada is None:
        bm.free()
        return 0

    def peso_braco(v, lado):
        dv = v[camada]
        return sum(w for g, w in dv.items() if g in do_braco[lado])

    classe = {}
    for f in bm.faces:
        if (mo @ f.calc_center_median()).z >= axila:
            continue
        pl = sum(peso_braco(v, "l") for v in f.verts) / len(f.verts)
        pr = sum(peso_braco(v, "r") for v in f.verts) / len(f.verts)
        classe[f] = "l" if pl > 0.5 else ("r" if pr > 0.5 else "corpo")
    cortar = [e for e in bm.edges if len({classe[f] for f in e.link_faces if f in classe}) == 2]
    if not cortar:
        bm.free()
        return 0
    bmesh.ops.split_edges(bm, edges=cortar)
    for v in bm.verts:
        cl = {classe.get(f) for f in v.link_faces}
        if len(cl) != 1 or None in cl:
            continue
        c = cl.pop()
        dv = v[camada]
        manter = do_braco[c] if c in "lr" else None
        for g in list(dv.keys()):
            if (manter is not None and g not in manter) or (manter is None and g in todos_braco):
                del dv[g]
        total = sum(dv.values())
        if total > 1e-6:
            for k in list(dv.keys()):
                dv[k] = dv[k] / total
        elif manter:
            dv[max(manter)] = 1.0
        elif "pelvis" in gi:
            dv[gi["pelvis"]] = 1.0
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(cortar)


def joelhos_suaves(obj, arm, H, fora=None, com_capa=False, faixa=0.045):
    """A dobra do joelho: perto da junta, o peso passa da coxa para a canela aos poucos, pelo plano que
    divide o ângulo entre os dois ossos (como numa dobra de verdade). Na malha da IA o molde encaixado
    deixava a passagem torta, e a calça devolvida à perna vinha com peso cheio num osso só: o joelho
    quebrava para dentro parado e fazia uma dobra escura andando. Só mexe na coxa e na canela (o resto do
    peso fica). Devolve quantos vértices mudaram."""
    mw = arm.matrix_world
    ossos = arm.data.bones
    gi = {g.name: g.index for g in obj.vertex_groups}
    if not all(f"{n}_{lado}" in gi and ossos.get(f"{n}_{lado}") for n in ("thigh", "calf") for lado in "lr"):
        return 0
    pelvis = mw @ ossos["pelvis"].head_local
    perna_y = float(np.mean([(mw @ ossos[f"thigh_{lado}"].head_local).y for lado in "lr"]))
    co = _co(obj)
    n_fora = len(fora) if fora is not None else 0
    b = faixa * H
    mudou = 0
    for lado in "lr":
        q = np.array(mw @ ossos[f"thigh_{lado}"].head_local)
        k = np.array(mw @ ossos[f"calf_{lado}"].head_local)
        t = np.array(mw @ ossos[f"calf_{lado}"].tail_local)
        u = (k - q) / max(np.linalg.norm(k - q), 1e-9)
        v = (t - k) / max(np.linalg.norm(t - k), 1e-9)
        eixo = u + v
        eixo /= max(np.linalg.norm(eixo), 1e-9)
        gt, gc = gi[f"thigh_{lado}"], gi[f"calf_{lado}"]
        d = (co - k) @ eixo
        perto = np.abs(d) < 2 * b
        perto &= (co[:, 0] > pelvis.x) if lado == "l" else (co[:, 0] <= pelvis.x)
        perto &= np.linalg.norm(co - k, axis=1) < 0.16 * H
        if com_capa:
            perto &= co[:, 1] < perna_y + 0.07 * H
        for i in np.nonzero(perto)[0]:
            if i < n_fora and fora[i]:
                continue
            v_ = obj.data.vertices[int(i)]
            pesos = {g.group: g.weight for g in v_.groups}
            perna = pesos.get(gt, 0.0) + pesos.get(gc, 0.0)
            total = sum(pesos.values())
            if total <= 1e-6 or perna < 0.5 * total:
                continue
            x = float(np.clip((d[i] + b) / (2 * b), 0.0, 1.0))
            canela = x * x * (3 - 2 * x)
            obj.vertex_groups[gt].add([int(i)], perna * (1 - canela), "REPLACE")
            obj.vertex_groups[gc].add([int(i)], perna * canela, "REPLACE")
            mudou += 1
    return mudou


def pernas_sem_tronco(obj, arm, H, fora=None, com_capa=False):
    """Abaixo da virilha, pano que não é saia nem capa e ficou só com peso de tronco (a parte de trás da
    calça larga passa da distância da regra "pano atrás da perna é capa") volta para a perna do lado dele:
    com peso de quadril e coluna na altura da canela, a calça esticava em pontas ao andar. Devolve quantos
    vértices voltaram."""
    mw = arm.matrix_world
    ossos = arm.data.bones
    if not all(ossos.get(f"{n}_{lado}") for n in ("thigh", "calf") for lado in "lr"):
        return 0
    pelvis = mw @ ossos["pelvis"].head_local
    perna_y = float(np.mean([(mw @ ossos[f"thigh_{lado}"].head_local).y for lado in "lr"]))
    virilha = min((mw @ ossos[f"thigh_{lado}"].head_local).z for lado in "lr") - 0.03 * H
    perna = {f"{n}_{lado}" for n in ("thigh", "calf", "foot", "ball") for lado in "lr"}
    gi = {g.index: g.name for g in obj.vertex_groups}
    co = _co(obj)
    n_fora = len(fora) if fora is not None else 0
    segs = {n: (np.array(mw @ ossos[n].head_local), np.array(mw @ ossos[n].tail_local))
            for n in perna if ossos.get(n) is not None}
    devolvidos = 0
    for v in obj.data.vertices:
        i = v.index
        p = co[i]
        if p[2] >= virilha or (i < n_fora and fora[i]):
            continue
        if com_capa and p[1] > perna_y + 0.07 * H:
            continue
        d_perna = min(float(fc_rig_ia._seg(p[None, :], *segs[n])[0]) for n in segs)
        if d_perna > 0.16 * H:
            continue  # longe das pernas: pano solto, não calça
        pesos = {gi[g.group]: g.weight for g in v.groups if g.weight > 1e-4}
        if sum(w for n, w in pesos.items() if n in perna) >= 0.5:
            continue
        lado = "l" if p[0] > pelvis.x else "r"
        melhor, dmin = None, np.inf
        for n in (f"thigh_{lado}", f"calf_{lado}", f"foot_{lado}"):
            if n not in segs:
                continue
            d = float(fc_rig_ia._seg(p[None, :], *segs[n])[0])
            if d < dmin:
                melhor, dmin = n, d
        if melhor is None:
            continue
        for g in list(v.groups):
            obj.vertex_groups[g.group].remove([i])
        g = obj.vertex_groups.get(melhor) or obj.vertex_groups.new(name=melhor)
        g.add([i], 1.0, "REPLACE")
        devolvidos += 1
    return devolvidos


def _manopla_firme(obj, arm, raio=0.11):
    """Mão da malha da IA presa à mão do esqueleto: a manopla (ou a mão grande) é maior que a mão do
    molde e a transferência pela superfície deixava ~54% do peso no antebraço; com o punho girando (golpe)
    a mão visível ficava para trás e a espada parecia solta. Depois do pulso, o peso do antebraço passa
    para a mão (mistura em 3 cm em volta do pulso); os dedos ficam como estão."""
    mw = arm.matrix_world
    total = 0
    grupos = {g.name: g for g in obj.vertex_groups}
    for lado in ("l", "r"):
        L = "Left" if lado == "l" else "Right"
        mao = arm.data.bones.get(f"hand_{lado}") or arm.data.bones.get(f"{L}Hand")
        braco = arm.data.bones.get(f"lowerarm_{lado}") or arm.data.bones.get(f"{L}LowerArm") or arm.data.bones.get(f"{L}ForeArm")
        if mao is None or braco is None or braco.name not in grupos:
            continue
        g_mao = grupos.get(mao.name) or obj.vertex_groups.new(name=mao.name)
        g_braco = grupos[braco.name]
        pulso = mw @ mao.head_local
        eixo = (mw @ mao.head_local - mw @ braco.head_local).normalized()
        ponta = mw @ mao.tail_local
        for v in obj.data.vertices:
            p = obj.matrix_world @ v.co
            t = (p - pulso).dot(eixo)
            if t < -0.015 or (p - pulso).length > raio + (ponta - pulso).length:
                continue
            w_b = next((ge.weight for ge in v.groups if ge.group == g_braco.index), 0.0)
            if w_b <= 0.0:
                continue
            k = min(1.0, max(0.0, (t + 0.015) / 0.03))  # 0 antes do pulso, 1 a 1,5 cm depois
            if k <= 0.0:
                continue
            passa = w_b * k
            w_m = next((ge.weight for ge in v.groups if ge.group == g_mao.index), 0.0)
            g_braco.add([v.index], w_b - passa, "REPLACE")
            g_mao.add([v.index], w_m + passa, "REPLACE")
            total += 1
    return total


def _pes_firmes(obj, arm):
    """Bota (sabatão) da malha da IA presa ao pé: abaixo do tornozelo o peso da canela passa para o pé
    (mistura em 4 cm) e metade do peso dos dedos (ball) vai para o pé. Com o peso dividido, a sola
    esticava em bico no golpe e saía uma aba no tornozelo."""
    mw = arm.matrix_world
    total = 0
    grupos = {g.name: g for g in obj.vertex_groups}
    for lado in ("l", "r"):
        L = "Left" if lado == "l" else "Right"
        pe = arm.data.bones.get(f"foot_{lado}") or arm.data.bones.get(f"{L}Foot")
        canela = arm.data.bones.get(f"calf_{lado}") or arm.data.bones.get(f"{L}LowerLeg") or arm.data.bones.get(f"{L}Leg")
        dedo = arm.data.bones.get(f"ball_{lado}") or arm.data.bones.get(f"{L}Toes") or arm.data.bones.get(f"{L}ToeBase")
        if pe is None or canela is None:
            continue
        g_pe = grupos.get(pe.name) or obj.vertex_groups.new(name=pe.name)
        g_can = grupos.get(canela.name)
        g_ded = grupos.get(dedo.name) if dedo is not None else None
        tornozelo = mw @ pe.head_local
        ponta = mw @ (dedo.tail_local if dedo is not None else pe.tail_local)
        raio = max(0.16, (ponta - tornozelo).length + 0.06)
        for v in obj.data.vertices:
            p = obj.matrix_world @ v.co
            if (p - tornozelo).length > raio or p.z > tornozelo.z + 0.02:
                continue
            k = min(1.0, max(0.0, (tornozelo.z + 0.02 - p.z) / 0.04))
            pesos = {ge.group: ge.weight for ge in v.groups}
            passa = 0.0
            if g_can is not None and pesos.get(g_can.index, 0.0) > 0:
                w = pesos[g_can.index]
                passa += w * k
                g_can.add([v.index], w * (1 - k), "REPLACE")
            if g_ded is not None and pesos.get(g_ded.index, 0.0) > 0:
                w = pesos[g_ded.index]
                passa += w * 0.5
                g_ded.add([v.index], w * 0.5, "REPLACE")
            if passa > 0:
                g_pe.add([v.index], pesos.get(g_pe.index, 0.0) + passa, "REPLACE")
                total += 1
    return total
