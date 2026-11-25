# Fornalha: correção automática do movimento, a partir do que a conferência (fc_conferir) acusa.
# Cada correção mexe só no que precisa e guarda a posição das mãos, pés e cabeça no mundo:
# - trancos: o quadro que gira muito mais que os vizinhos vira a média dos vizinhos;
# - dobradiças (cotovelo, joelho): o osso de cima gira em volta do próprio eixo até a junta dobrar no
#   plano certo e para o lado certo; o osso de baixo continua apontando para o mesmo lugar;
# - torção da mão: o pulso não gira em volta do próprio eixo; a torção passa para o antebraço
#   (que é quem gira de verdade), e a mão fica onde estava;
# - chão: o quadril sobe o que o corpo entrou no chão (e nada mais), suavizado entre os quadros.
import math
import re

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

import fc_conferir

MAO_PULSO = (("hand_l", "lowerarm_l"), ("hand_r", "lowerarm_r"), ("LeftHand", "LeftLowerArm"), ("RightHand", "RightLowerArm"))
TORCAO_DA_MAO_FICA = 15.0  # graus que a mão pode guardar


def _rel(pb):
    """Descanso do osso em relação ao pai (espaço da armadura)."""
    b = pb.bone
    return (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local.copy()


class Poses:
    """Poses de um quadro em espaço da armadura, recalculadas por conta própria (sem depender da
    avaliação do Blender a cada mudança)."""

    def __init__(self, arm):
        self.arm = arm
        self.ordem = []

        def andar(b):
            self.ordem.append(arm.pose.bones[b.name])
            for f in b.children:
                andar(f)

        for b in arm.data.bones:
            if b.parent is None:
                andar(b)
        self.rel = {pb.name: _rel(pb) for pb in self.ordem}

    def ler(self):
        self.base = {pb.name: pb.matrix_basis.copy() for pb in self.ordem}
        self.recalcular()

    def recalcular(self):
        self.M = {}
        for pb in self.ordem:
            pai = self.M[pb.parent.name] if pb.parent else Matrix.Identity(4)
            self.M[pb.name] = pai @ self.rel[pb.name] @ self.base[pb.name]

    def por_mundo(self, nome, desejada):
        """Muda o osso para ficar com a matriz `desejada` (espaço da armadura), com os pais como estão."""
        pb = self.arm.pose.bones[nome]
        pai = self.M[pb.parent.name] if pb.parent else Matrix.Identity(4)
        self.base[nome] = (pai @ self.rel[nome]).inverted() @ desejada

    def gravar(self, nomes, quadro, local=False):
        for n in nomes:
            pb = self.arm.pose.bones[n]
            loc, rot, _ = self.base[n].decompose()
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = rot
            pb.keyframe_insert("rotation_quaternion", frame=quadro, group=n)
            if local:
                pb.location = loc
                pb.keyframe_insert("location", frame=quadro, group=n)


def _girar_em_volta(M, eixo, angulo):
    """Gira a matriz M (osso) em volta do eixo (espaço da armadura) que passa pela cabeça do osso."""
    cabeca = M.to_translation()
    R = Matrix.Rotation(angulo, 4, eixo)
    return Matrix.Translation(cabeca) @ R @ Matrix.Translation(-cabeca) @ M


def _quadros(acao):
    ini, fim = (int(round(x)) for x in acao.frame_range)
    return list(range(ini, fim + 1))


def _usar(arm, acao):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = acao
    if hasattr(ad, "action_slot") and ad.action_slot is None and getattr(acao, "slots", None):
        try:
            ad.action_slot = acao.slots[0]
        except Exception:
            pass


def _sequencia(arm, acao, nomes):
    """Rotação local (quaternion) de cada osso em cada quadro."""
    cena = bpy.context.scene
    seq = {n: [] for n in nomes}
    for q in _quadros(acao):
        cena.frame_set(q)
        for n in nomes:
            seq[n].append(arm.pose.bones[n].matrix_basis.to_quaternion())
    return seq


def tirar_trancos(arm, acao, problemas, rodadas=4):
    """Quadro que gira muito mais que os vizinhos (osso virando de repente) vira a média dos vizinhos;
    repete até não sobrar tranco (um tranco às vezes some e aparece no quadro do lado)."""
    nomes = sorted({p["osso"] for p in problemas if p["tipo"] == "salto" and p["osso"] in arm.pose.bones}) if problemas is not None else [b.name for b in arm.pose.bones]
    if not nomes:
        return 0
    qs = _quadros(acao)
    seq = _sequencia(arm, acao, nomes)
    mudados = {}
    for n in nomes:
        v = seq[n]
        for _ in range(rodadas):
            ang = [0.0] + [fc_conferir._angulo_quat(v[i - 1], v[i]) for i in range(1, len(v))]
            achou = False
            if len(v) > 2 and ang[1] > fc_conferir.SALTO_MAX * 0.8 and ang[1] > 2.5 * ang[2]:
                # o primeiro quadro é o que destoa
                v[0] = v[1].copy()
                mudados.setdefault(n, set()).add(0)
                achou = True
            for i in range(2, len(v) - 1):
                viz = max(ang[i - 1], ang[i + 1])
                if ang[i] > fc_conferir.SALTO_MAX * 0.8 and ang[i] > 2.5 * viz:
                    a, b = v[i - 1], v[i + 1]
                    if a.dot(b) < 0:
                        b = -b
                    v[i] = a.slerp(b, 0.5)
                    mudados.setdefault(n, set()).add(i)
                    achou = True
            if not achou:
                break
    feitos = 0
    for n, idx in mudados.items():
        pb = arm.pose.bones[n]
        pb.rotation_mode = "QUATERNION"
        for i in sorted(idx):
            pb.rotation_quaternion = seq[n][i]
            pb.keyframe_insert("rotation_quaternion", frame=qs[i], group=n)
            feitos += 1
    return feitos


def _giro_da_dobradica(P, conf, p, c):
    """Quanto o osso de cima precisa girar em volta do próprio eixo para a junta dobrar no plano certo,
    para o lado natural (radianos), e o peso (0 com a junta quase esticada)."""
    Mp, Mc = P.M[p], P.M[c]
    t = (Mp.to_3x3() @ Vector((0, 1, 0))).normalized()
    s = (Mc.to_3x3() @ Vector((0, 1, 0))).normalized()
    n = (Mp.to_3x3().normalized() @ conf.eixos[p]).normalized()
    n = (n - t * n.dot(t)).normalized()
    dobra = math.degrees(t.angle(s)) if s.length and t.length else 0.0
    peso = min(1.0, max(0.0, (dobra - 8.0) / 17.0))
    if peso <= 0:
        return 0.0, 0.0
    tn = t.cross(n)
    phi = math.atan2(-n.dot(s), tn.dot(s))
    for cand in (phi, phi + math.pi):
        nn = n * math.cos(cand) + tn * math.sin(cand)
        if t.cross(s).dot(nn) >= 0:
            phi = cand
            break
    return math.atan2(math.sin(phi), math.cos(phi)), peso


def endireitar(arm, acao, conf, passo_max=20.0):
    """Cotovelos e joelhos dobrando no plano certo. Duas passadas: mede o giro de cada quadro, deixa a
    sequência contínua e sem saltos (no máximo `passo_max` graus de um quadro para o outro) e só então
    aplica."""
    dob = [(p, c) for p, c, _, _ in conf.dobradicas if p in conf.eixos]
    if not dob:
        return 0
    P = Poses(arm)
    cena = bpy.context.scene
    qs = _quadros(acao)
    giros = {p: [] for p, _ in dob}
    for q in qs:
        cena.frame_set(q)
        P.ler()
        for p, c in dob:
            phi, peso = _giro_da_dobradica(P, conf, p, c)
            giros[p].append((phi, peso))
    finais = {}
    for p, lista in giros.items():
        phis = np.unwrap(np.array([a for a, _ in lista]))
        pesos = np.array([w for _, w in lista])
        alvo = phis * pesos
        # sem saltos: limita a variação por quadro
        lim = math.radians(passo_max)
        out = alvo.copy()
        for i in range(1, len(out)):
            out[i] = out[i - 1] + np.clip(alvo[i] - out[i - 1], -lim, lim)
        finais[p] = out
    mudou = 0
    for i, q in enumerate(qs):
        cena.frame_set(q)
        P.ler()
        tocados = set()
        for p, c in dob:
            phi = float(finais[p][i])
            if abs(math.degrees(phi)) < 1.0:
                continue
            Mp, Mc = P.M[p], P.M[c]
            t = (Mp.to_3x3() @ Vector((0, 1, 0))).normalized()
            P.por_mundo(p, _girar_em_volta(Mp, t, phi))
            P.recalcular()
            P.por_mundo(c, Mc)
            P.recalcular()
            tocados |= {p, c}
        if tocados:
            P.gravar(sorted(tocados), q)
            mudou += 1
    return mudou


def passar_torcao_da_mao(arm, acao):
    """A torção da mão em volta do próprio eixo passa para o antebraço (a mão fica onde estava), até o
    limite do antebraço; o que passar disso é tirado (a arma gira um pouco menos, o braço não vira)."""
    pares = [(m, a) for m, a in MAO_PULSO if m in arm.pose.bones and a in arm.pose.bones]
    if not pares:
        return 0
    lim_ante = fc_conferir.TORCAO.get("lowerarm", 110) - 8
    P = Poses(arm)
    cena = bpy.context.scene
    mudou = 0
    for q in _quadros(acao):
        cena.frame_set(q)
        P.ler()
        tocados = set()
        for mao, ante in pares:
            tw = fc_conferir._twist_graus(P.base[mao].to_quaternion())
            excesso = tw - math.copysign(min(abs(tw), TORCAO_DA_MAO_FICA), tw)
            tw_a = fc_conferir._twist_graus(P.base[ante].to_quaternion())
            if abs(excesso) < 1.0 and abs(tw_a) <= lim_ante:
                continue
            Mm, Ma = P.M[mao], P.M[ante]
            eixo = (Ma.to_3x3() @ Vector((0, 1, 0))).normalized()
            # quanto o antebraço ainda aguenta: o resto não gira (a mão acompanha o antebraço)
            novo = tw_a + excesso
            novo_lim = max(-lim_ante, min(lim_ante, novo))
            P.por_mundo(ante, _girar_em_volta(Ma, eixo, math.radians(novo_lim - tw_a)))
            P.recalcular()
            # a mão guarda a posição no mundo menos o que foi tirado
            sobra = novo - novo_lim
            P.por_mundo(mao, _girar_em_volta(Mm, eixo, math.radians(-sobra)))
            P.recalcular()
            tocados |= {mao, ante}
        if tocados:
            P.gravar(sorted(tocados), q)
            mudou += 1
    return mudou


def limitar_torcao(arm, acao, nomes, margem=6.0):
    """Osso torcido além do natural volta para dentro do limite girando em volta do próprio eixo (os
    filhos acompanham). Muda um pouco para onde o joelho ou o cotovelo aponta, mas não deixa a malha
    torcida como um pano espremido."""
    alvo = []
    for n in nomes:
        if n not in arm.pose.bones:
            continue
        base = re.sub(r"^(Left|Right)", "", re.sub(r"_[lr]$", "", n))
        lim = fc_conferir.TORCAO.get(n) or fc_conferir.TORCAO.get(base)
        if lim:
            alvo.append((n, lim - margem))
    if not alvo:
        return 0
    cena = bpy.context.scene
    mudou = 0
    for q in _quadros(acao):
        cena.frame_set(q)
        tocados = []
        for n, lim in alvo:
            pb = arm.pose.bones[n]
            qb = pb.matrix_basis.to_quaternion()
            tw = fc_conferir._twist_graus(qb)
            if abs(tw) <= lim:
                continue
            volta = math.radians(math.copysign(abs(tw) - lim, tw))
            # torção em volta do Y do osso: tira pelo lado de dentro (depois da rotação atual)
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = qb @ Quaternion((0, 1, 0), -volta)
            pb.keyframe_insert("rotation_quaternion", frame=q, group=n)
            tocados.append(n)
        if tocados:
            mudou += 1
    return mudou


RAIZ_DO_MEMBRO = {"lowerarm_l": "upperarm_l", "lowerarm_r": "upperarm_r", "upperarm_l": "upperarm_l", "upperarm_r": "upperarm_r",
                  "calf_l": "thigh_l", "calf_r": "thigh_r", "thigh_l": "thigh_l", "thigh_r": "thigh_r",
                  "LeftLowerArm": "LeftUpperArm", "RightLowerArm": "RightUpperArm", "LeftUpperArm": "LeftUpperArm", "RightUpperArm": "RightUpperArm",
                  "LeftLowerLeg": "LeftUpperLeg", "RightLowerLeg": "RightUpperLeg", "LeftUpperLeg": "LeftUpperLeg", "RightUpperLeg": "RightUpperLeg"}


def _pontos_proximos(p1, q1, p2, q2):
    """Pontos mais próximos entre dois segmentos (Vector)."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
    c = d1.dot(r)
    b = d1.dot(d2)
    den = a * e - b * b
    s = min(1.0, max(0.0, (b * f - c * e) / den)) if den > 1e-12 and a > 1e-12 else 0.0
    t = (b * s + f) / e if e > 1e-12 else 0.0
    if t < 0:
        t, s = 0.0, (min(1.0, max(0.0, -c / a)) if a > 1e-12 else 0.0)
    elif t > 1:
        t, s = 1.0, (min(1.0, max(0.0, (b - c) / a)) if a > 1e-12 else 0.0)
    return p1 + d1 * s, p2 + d2 * t


def afastar(arm, acao, conf, problemas, folga=0.008, rodadas=3):
    """Membro que atravessa o corpo (braço no peito, canela na outra canela) gira no ombro ou no quadril
    só o bastante para sair, a cada quadro; a mão ou o pé andam um pouco junto."""
    pares = set()
    for p in problemas:
        if p["tipo"] == "atravessa":
            a, b = p["osso"].split(" × ")
            pares.add((a, b))
    if not pares:
        return 0
    mw = arm.matrix_world
    mwi = mw.inverted()
    P = Poses(arm)
    cena = bpy.context.scene

    def seg(n):
        M = P.M[n]
        h = mw @ M.to_translation()
        comp = arm.data.bones[n].length
        t = mw @ (M @ Vector((0, comp, 0)))
        h, t = conf._segmento(n, np.array(h), np.array(t))
        return Vector(h), Vector(t)

    mudou = 0
    for q in _quadros(acao):
        cena.frame_set(q)
        P.ler()
        tocados = set()
        for _ in range(rodadas):
            algum = False
            for a, b in pares:
                ha, ta = seg(a)
                hb, tb = seg(b)
                ca, cb = _pontos_proximos(ha, ta, hb, tb)
                d = (ca - cb).length
                fundo = conf.raios[a] + conf.raios[b] - d - conf.base.get(f"{a} × {b}", 0.0)
                if fundo <= 0:
                    continue
                algum = True
                # quem se mexe: o membro (os dois, metade cada, se forem dois membros)
                membros = [x for x in (a, b) if x in RAIZ_DO_MEMBRO]
                for k, m in enumerate(membros):
                    raiz = RAIZ_DO_MEMBRO[m]
                    longe = ca if m == a else cb
                    perto = cb if m == a else ca
                    u = (longe - perto)
                    if u.length < 1e-6:
                        u = Vector((0, 0, 1)).cross(mw.to_3x3() @ Vector((1, 0, 0)))
                    u.normalize()
                    pivo = mw @ P.M[raiz].to_translation()
                    r = longe - pivo
                    if r.length < 1e-4:
                        continue
                    eixo = r.cross(u)
                    if eixo.length < 1e-6:
                        continue
                    ang = math.atan2((fundo + folga) / len(membros), r.length)
                    eixo_arm = (mwi.to_3x3() @ eixo).normalized()
                    M = P.M[raiz]
                    P.por_mundo(raiz, _girar_em_volta(M, eixo_arm, ang))
                    P.recalcular()
                    tocados.add(raiz)
            if not algum:
                break
        if tocados:
            P.gravar(sorted(tocados), q)
            mudou += 1
    return mudou


def _ik_dois_ossos(P, mw, coxa, canela, pe, alvo_mundo):
    """Põe a cabeça do `pe` em `alvo_mundo` dobrando coxa e canela (o joelho fica no plano em que está),
    e o pé guarda o giro que tinha no mundo."""
    mwi = mw.inverted()
    alvo = mwi @ alvo_mundo
    Mq, Mj, Mp = P.M[coxa], P.M[canela], P.M[pe]
    H = Mq.to_translation()
    K = Mj.to_translation()
    A = Mp.to_translation()
    L1, L2 = (K - H).length, (A - K).length
    if L1 < 1e-6 or L2 < 1e-6:
        return False
    d_vec = alvo - H
    d = min(max(d_vec.length, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    u = d_vec.normalized()
    w = (K - H) - u * (K - H).dot(u)
    if w.length < 1e-6:
        w = (Mq.to_3x3() @ Vector((0, 0, 1)))
        w = w - u * w.dot(u)
    w.normalize()
    cos_a = max(-1.0, min(1.0, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)))
    K2 = H + L1 * (cos_a * u + math.sqrt(max(0.0, 1 - cos_a * cos_a)) * w)
    A2 = H + u * d
    rot_pe = Mp.to_3x3().normalized()
    # coxa: gira o mínimo para apontar para o joelho novo
    giro = (K - H).normalized().rotation_difference((K2 - H).normalized()).to_matrix().to_4x4()
    P.por_mundo(coxa, Matrix.Translation(H) @ giro @ Matrix.Translation(-H) @ Mq)
    P.recalcular()
    Mj = P.M[canela]
    K1 = Mj.to_translation()
    giro = (P.M[pe].to_translation() - K1).normalized().rotation_difference((A2 - K1).normalized()).to_matrix().to_4x4()
    P.por_mundo(canela, Matrix.Translation(K1) @ giro @ Matrix.Translation(-K1) @ Mj)
    P.recalcular()
    novo = rot_pe.to_4x4()
    novo.translation = P.M[pe].to_translation()
    P.por_mundo(pe, novo)
    P.base[pe] = Matrix.LocRotScale(None, P.base[pe].to_quaternion(), None)
    P.recalcular()
    return True


def travar_pes(arm, acao, conf, rampa=3):
    """Pé no chão: em cada fase de apoio o pé fica parado (ou anda na velocidade do chão, no ciclo no
    lugar) e a perna dobra para isso (IK de dois ossos); entra e sai aos poucos nas pontas da fase."""
    cadeias = []
    for p in conf.pes:
        b = arm.data.bones[p]
        if b.parent and b.parent.parent:
            cadeias.append((b.parent.parent.name, b.parent.name, p))
    if not cadeias:
        return 0
    mw = arm.matrix_world
    P = Poses(arm)
    cena = bpy.context.scene
    qs = _quadros(acao)
    seq = {pe: [] for _, _, pe in cadeias}
    tornozelo = {pe: [] for _, _, pe in cadeias}
    contato = {}
    for q in qs:
        cena.frame_set(q)
        P.ler()
        for _, _, pe in cadeias:
            M = P.M[pe]
            comp = arm.data.bones[pe].length
            h = mw @ M.to_translation()
            t = mw @ (M @ Vector((0, comp, 0)))
            seq[pe].append((np.array(h), np.array(t)))
            tornozelo[pe].append(h.copy())
            contato.setdefault(pe, []).append(h.copy() if h.z < t.z else t.copy())
    vel, fases_de = fc_conferir.apoios(seq, conf.frente, conf.H)
    if vel is None:
        return 0
    alvos = {}
    for coxa, canela, pe in cadeias:
        if pe not in fases_de:
            continue
        _, fases = fases_de[pe]
        for a, b in fases:
            meio = (a + b) // 2
            # trava o ponto que toca o chão (calcanhar ou ponta): o pé pode girar na ponta, como num chute
            base = contato[pe][meio]
            for i in range(max(0, a - rampa), min(len(qs), b + rampa + 1)):
                dt = (i - meio) / fc_conferir.FPS
                fuga = Vector((base.x + vel[0] * dt - contato[pe][i].x, base.y + vel[1] * dt - contato[pe][i].y, 0.0))
                travado = tornozelo[pe][i] + fuga
                if i < a:
                    w = (i - (a - rampa)) / (rampa + 1)
                elif i > b:
                    w = ((b + rampa) - i) / (rampa + 1)
                else:
                    w = 1.0
                w = max(0.0, min(1.0, w))
                alvos.setdefault(i, []).append((coxa, canela, pe, tornozelo[pe][i].lerp(travado, w)))
    mudou = 0
    for i, lista in sorted(alvos.items()):
        cena.frame_set(qs[i])
        P.ler()
        tocados = []
        for coxa, canela, pe, alvo in lista:
            if (alvo - (mw @ P.M[pe].to_translation())).length < 0.002:
                continue
            if _ik_dois_ossos(P, mw, coxa, canela, pe, alvo):
                tocados += [coxa, canela, pe]
        if tocados:
            P.gravar(sorted(set(tocados)), qs[i])
            mudou += 1
    return mudou


def assentar_no_chao(arm, acao, conf, malhas, raiz="pelvis"):
    """Sobe o quadril o que o corpo entrou no chão em cada quadro (suavizado)."""
    if raiz not in arm.pose.bones:
        raiz = next((n for n in ("Hips", "quadril", "raiz") if n in arm.pose.bones), None)
    if raiz is None or not malhas:
        return 0
    cena = bpy.context.scene
    qs = _quadros(acao)
    falta = []
    for q in qs:
        cena.frame_set(q)
        z = min(float(fc_conferir._co_avaliado(o)[:, 2].min()) for o in malhas)
        falta.append(max(0.0, conf.chao - z))
    falta = np.array(falta)
    if falta.max() < 0.01:
        return 0
    # suaviza (janela de 5) sem baixar o máximo local
    k = np.ones(5) / 5
    suave = np.maximum(np.convolve(np.pad(falta, 2, mode="edge"), k, mode="valid"), falta) + 0.005
    pb = arm.pose.bones[raiz]
    P = Poses(arm)
    mw3 = arm.matrix_world.to_3x3()
    for q, sobe in zip(qs, suave):
        if sobe < 0.002:
            continue
        cena.frame_set(q)
        P.ler()
        M = P.M[raiz].copy()
        delta = mw3.inverted() @ Vector((0, 0, float(sobe)))
        M.translation = M.translation + delta
        P.por_mundo(raiz, M)
        P.gravar([raiz], q, local=True)
    return int(np.sum(suave >= 0.002))


def corrigir(arm, acoes, conf, resultados, quais=("trancos", "dobradicas", "pes", "corpo_solido", "torcao", "chao")):
    """Corrige cada animação reprovada. Devolve {animação: {correção: quadros mudados}}."""
    feito = {}
    mods = [m for o in conf.malhas for m in o.modifiers if m.type == "ARMATURE"]
    for acao, r in zip(acoes, resultados):
        if r["aprovado"]:
            continue
        tipos = {p["tipo"] for p in r["problemas"]}
        _usar(arm, acao)
        log = {}
        estados = [m.show_viewport for m in mods]
        for m in mods:
            m.show_viewport = False
        try:
            if "trancos" in quais and "salto" in tipos:
                log["trancos"] = tirar_trancos(arm, acao, r["problemas"])
            if "dobradicas" in quais and tipos & {"ao_contrario", "de_lado"}:
                log["dobradicas"] = endireitar(arm, acao, conf)
            if "pes" in quais and "escorrega" in tipos:
                log["pe_no_chao"] = travar_pes(arm, acao, conf)
            if "corpo_solido" in quais and "atravessa" in tipos:
                log["corpo_solido"] = afastar(arm, acao, conf, r["problemas"])
            if "torcao" in quais and any(p["tipo"] == "torcao" and re.match(r"^(hand_[lr]|(Left|Right)Hand|lowerarm_[lr]|(Left|Right)LowerArm)$", p["osso"]) for p in r["problemas"]):
                log["torcao_da_mao"] = passar_torcao_da_mao(arm, acao)
        finally:
            for m, e in zip(mods, estados):
                m.show_viewport = e
        torcidos = [p["osso"] for p in r["problemas"] if p["tipo"] == "torcao" and not re.match(r"^(hand_[lr]|(Left|Right)Hand|lowerarm_[lr]|(Left|Right)LowerArm)$", p["osso"])]
        if "torcao" in quais and torcidos:
            log["torcao_limitada"] = limitar_torcao(arm, acao, torcidos)
        if "trancos" in quais and log:
            # as correções podem criar tranco novo: uma passada final em todos os ossos
            for m in mods:
                m.show_viewport = False
            try:
                n = tirar_trancos(arm, acao, None)
            finally:
                for m, e in zip(mods, estados):
                    m.show_viewport = e
            if n:
                log["trancos_no_fim"] = n
        if "chao" in quais and "abaixo_do_chao" in tipos:
            log["chao"] = assentar_no_chao(arm, acao, conf, conf.malhas)
        feito[acao.name] = log
    return feito
