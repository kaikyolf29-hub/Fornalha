# Fornalha: conferência do movimento. Mede cada animação de um personagem com esqueleto e reprova o
# que fica feio no jogo, para a IA corrigir antes de entregar:
# - torção de osso além do limite (antebraço, braço, coxa, mão, cabeça…): o "braço virado";
# - junta de dobradiça dobrando ao contrário ou de lado (cotovelo, joelho);
# - salto brusco de rotação de um quadro para o outro (osso que "vira" de repente), em qualquer corpo;
# - corpo sólido: braço atravessando o tronco, pernas atravessando uma a outra (cápsulas por osso);
# - pé (ou pata) escorregando enquanto está no chão;
# - corpo abaixo do chão, ou flutuando quando devia pisar.
# Vale para o esqueleto de jogo do humano (nomes Unreal), o esqueleto padrão da Forja e as criaturas
# (as regras de humano só entram quando os ossos existem; as gerais valem para todos).
import math
import os
import re

import bpy
import numpy as np
from mathutils import Vector

# ------------------------------------------------------------------ regras (o que reprova)

# torção máxima em relação ao descanso, em graus (padrão do nome sem o lado)
TORCAO = {
    "upperarm": 100, "lowerarm": 110, "hand": 60, "clavicle": 45,
    "thigh": 80, "calf": 50, "foot": 60,
    "neck_01": 75, "head": 85, "spine_01": 45, "spine_02": 45, "spine_03": 45,
    "UpperArm": 100, "LowerArm": 110, "Hand": 60, "Shoulder": 45,
    "UpperLeg": 80, "LowerLeg": 50, "Foot": 60, "Neck": 75, "Head": 85, "Spine": 45, "Chest": 45,
}
# dobradiças: (pai, filho, para onde o filho vai ao dobrar: "frente" ou "tras")
DOBRADICAS = [
    ("upperarm_{l}", "lowerarm_{l}", "frente", "cotovelo"),
    ("thigh_{l}", "calf_{l}", "tras", "joelho"),
    ("{L}UpperArm", "{L}LowerArm", "frente", "cotovelo"),
    ("{L}UpperLeg", "{L}LowerLeg", "tras", "joelho"),
]
LADOS = (("l", "Left", "esquerdo"), ("r", "Right", "direito"))
AO_CONTRARIO_MAX = 12.0  # graus dobrando ao contrário
DE_LADO_MAX = {"cotovelo": 45.0, "joelho": 35.0}  # graus fora do plano da dobradiça
SALTO_MAX = 50.0  # graus de um quadro para o outro, e 3× mais que os quadros vizinhos (tranco)
ATRAVESSA_MAX_CM = 5.5  # e mais de 50% do raio da cápsula menor (o braço encostando no tronco é normal)
ESCORREGA_MAX_CM = 5.0
CHAO_MAX_CM = 4.0
FLUTUA_MIN_CM = 6.0
TRONCO_TORCAO_MAX = 55.0  # graus que o peito gira em volta da coluna em relação ao quadril
TRONCO_DOBRA_MAX = 75.0  # graus que o peito dobra em relação ao quadril
TRONCO_PARES = (("pelvis", "spine_03"), ("Hips", "Chest"), ("quadril", "coluna_3"))
SEM_CHAO = ("pular", "no_ar", "jump", "pulo", "voar", "voo", "fly")

# cápsulas do corpo sólido (padrões dos nomes; o raio sai da malha)
TRONCO = ("pelvis", "spine_01", "spine_02", "spine_03", "Hips", "Spine", "Chest")
BRACO = ("upperarm_", "lowerarm_", "UpperArm", "LowerArm")
PERNA_PARES = (("thigh_l", "thigh_r"), ("calf_l", "calf_r"), ("LeftUpperLeg", "RightUpperLeg"), ("LeftLowerLeg", "RightLowerLeg"))
PES = re.compile(r"^(foot_[lr]|(Left|Right)Foot|.*_pe|pata_\d+_pe|pe_.*)$")


def regras():
    return {"tronco_torcao_graus": TRONCO_TORCAO_MAX, "tronco_dobra_graus": TRONCO_DOBRA_MAX, "torcao_graus": TORCAO, "ao_contrario_graus": AO_CONTRARIO_MAX, "de_lado_graus": DE_LADO_MAX, "salto_graus_por_quadro": SALTO_MAX,
            "atravessa_cm": ATRAVESSA_MAX_CM, "escorrega_cm": ESCORREGA_MAX_CM, "abaixo_do_chao_cm": CHAO_MAX_CM, "flutua_cm": FLUTUA_MIN_CM}


# ------------------------------------------------------------------ geometria

def _twist_graus(q):
    """Torção em volta do eixo do osso (Y no Blender) de uma rotação local, em graus (-180..180)."""
    if q.w < 0:
        q = -q
    return math.degrees(2.0 * math.atan2(q.y, q.w))


def _angulo_quat(a, b):
    d = abs(a.dot(b))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


def _dist_segmentos(p1, q1, p2, q2):
    """Menor distância entre os segmentos p1-q1 e p2-q2 (numpy)."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    if a < 1e-12 and e < 1e-12:
        return float(np.linalg.norm(r))
    if a < 1e-12:
        s, t = 0.0, np.clip(f / e, 0, 1)
    else:
        c = d1 @ r
        if e < 1e-12:
            t, s = 0.0, np.clip(-c / a, 0, 1)
        else:
            b = d1 @ d2
            den = a * e - b * b
            s = np.clip((b * f - c * e) / den, 0, 1) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, np.clip(-c / a, 0, 1)
            elif t > 1:
                t, s = 1.0, np.clip((b - c) / a, 0, 1)
    return float(np.linalg.norm((p1 + d1 * s) - (p2 + d2 * t)))


def _malhas_do(arm):
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]


def _co_avaliado(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    co = co.reshape(-1, 3)
    mw = np.array(obj.matrix_world, dtype=np.float32)
    return co @ mw[:3, :3].T + mw[:3, 3]


def _raios(arm, malhas, nomes, H):
    """Raio da cápsula de cada osso: mediana da distância dos vértices que ele carrega (peso > 0,5) até o
    segmento do osso, no descanso. Sem malha (ou poucos vértices), uma fração da altura."""
    padrao = {"pelvis": 0.085, "spine": 0.085, "Hips": 0.085, "Spine": 0.085, "Chest": 0.09, "upperarm": 0.032, "UpperArm": 0.032,
              "lowerarm": 0.027, "LowerArm": 0.027, "thigh": 0.05, "UpperLeg": 0.05, "calf": 0.038, "LowerLeg": 0.038}
    raios = {}
    mw = arm.matrix_world
    for n in nomes:
        base = next((v for k, v in padrao.items() if n.startswith(k)), 0.03)
        raios[n] = base * H
    # junta as distâncias de todas as peças (corpo, armadura, roupa, capa) antes de medir
    dist = {n: [] for n in nomes}
    for obj in malhas:
        if len(obj.data.vertices) >= 400000:
            continue
        grupos = {g.index: g.name for g in obj.vertex_groups if g.name in nomes}
        if not grupos:
            continue
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        M = np.array(obj.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
        por_osso = {n: [] for n in grupos.values()}
        for v in obj.data.vertices:
            for g in v.groups:
                n = grupos.get(g.group)
                if n and g.weight > 0.5:
                    por_osso[n].append(v.index)
        for n, idx in por_osso.items():
            if not idx:
                continue
            b = arm.data.bones[n]
            a, c = np.array(mw @ b.head_local), np.array(mw @ b.tail_local)
            ab = c - a
            pts = co[idx]
            t = np.clip(((pts - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
            dist[n].append(np.linalg.norm(pts - (a + t[:, None] * ab), axis=1))
    for n, partes in dist.items():
        d = np.concatenate(partes) if partes else np.empty(0)
        if len(d) < 12:
            continue
        if n in TRONCO:
            # tronco é mais largo que fundo: o braço atravessa pela frente e por trás (profundidade)
            raios[n] = float(np.percentile(d, 30)) * 0.9
        else:
            fator = 0.65 if n.startswith(("thigh", "calf", "UpperLeg", "LowerLeg", "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg")) else 0.8
            raios[n] = float(np.median(d)) * fator
    return raios


def _frente(arm):
    """Para onde o personagem olha no descanso (horizontal): pelos pés; sem pés, -Y (padrão da Fornalha)."""
    v = Vector()
    for n in ("foot_l", "foot_r", "LeftFoot", "RightFoot"):
        b = arm.data.bones.get(n)
        if b:
            d = arm.matrix_world.to_3x3() @ (b.tail_local - b.head_local)
            d.z = 0
            v += d
    if v.length < 1e-6:
        return Vector((0, -1, 0))
    return v.normalized()


FPS = 30


def apoios(pes, frente, H):
    """Fases de apoio de cada pé. pes: {pé: [(cabeça, ponta) em mundo por quadro]}. Primeiro acha a
    velocidade do chão: na captura no lugar, o pé de apoio corre para trás numa velocidade constante;
    com deslocamento (ou parado), o pé de apoio fica parado. É a velocidade que deixa mais quadros com o
    pé baixo e quieto. Devolve (velocidade do chão em m/s no plano, {pé: (xy do ponto baixo, [(a, b)])})."""
    tol = max(0.03, 0.02 * H)
    tras = -np.array([frente.x, frente.y])
    dados = {}
    for p, seq in pes.items():
        if len(seq) < 6:
            continue
        baixo = np.array([h if h[2] < t[2] else t for h, t in seq])
        z = baixo[:, 2]
        ref = float(np.percentile(z, 5))
        xy = baixo[:, :2]
        v = np.gradient(xy, axis=0) * FPS
        dados[p] = (xy, v, z < ref + tol)
    if not dados:
        return None, {}
    melhor, cont = 0.0, -1
    for vel in np.arange(0.0, 8.01, 0.05):
        alvo = tras * vel
        n = sum(int(np.sum(baixo & (np.linalg.norm(v - alvo, axis=1) < 0.3))) for _, v, baixo in dados.values())
        if n > cont + 2:  # empate: fica a menor velocidade
            melhor, cont = vel, n
    alvo = tras * melhor
    out = {}
    for p, (xy, v, baixo) in dados.items():
        apoio = baixo & (np.linalg.norm(v - alvo, axis=1) < 0.6)
        fases, ini = [], None
        for i, c in enumerate(apoio):
            if c and ini is None:
                ini = i
            if (not c or i == len(apoio) - 1) and ini is not None:
                fim = i if c else i - 1
                if fim - ini >= 3:
                    fases.append((ini, fim))
                ini = None
        out[p] = (xy, fases)
    return alvo, out


# ------------------------------------------------------------------ medidas

class Conferencia:
    def __init__(self, arm, H=None):
        self.arm = arm
        self.ossos = {b.name for b in arm.data.bones}
        self.malhas = _malhas_do(arm)
        mn = min((min((o.matrix_world @ Vector(cc)).z for cc in o.bound_box) for o in self.malhas), default=0.0)
        mx = max((max((o.matrix_world @ Vector(cc)).z for cc in o.bound_box) for o in self.malhas), default=0.0)
        if H is None:
            H = (mx - mn) if self.malhas and mx > mn else max((arm.matrix_world @ b.tail_local).z for b in arm.data.bones)
        self.H = max(float(H), 0.1)
        self.chao = 0.0
        self.frente = _frente(arm)
        self.cima = Vector((0, 0, 1))
        # dobradiças presentes neste esqueleto
        self.dobradicas = []
        for pai, filho, para, nome in DOBRADICAS:
            for l, L, lado in LADOS:
                p, f = pai.format(l=l, L=L), filho.format(l=l, L=L)
                if p in self.ossos and f in self.ossos:
                    self.dobradicas.append((p, f, para, f"{nome} {lado}"))
        self._eixo_dobradica()
        # cápsulas
        tronco = [n for n in self.ossos if n in TRONCO]
        bracos = [n for n in self.ossos if n.startswith(BRACO)]
        self.pares = [(a, b) for a in bracos for b in tronco]
        self.pares += [(a, b) for a, b in PERNA_PARES if a in self.ossos and b in self.ossos]
        usados = sorted({n for par in self.pares for n in par})
        self.raios = _raios(arm, self.malhas, usados, self.H)
        self.pes = [b.name for b in arm.data.bones if PES.match(b.name)]
        self.tronco = next(((a, b) for a, b in TRONCO_PARES if a in self.ossos and b in self.ossos), None)
        if self.tronco:
            mw3 = arm.matrix_world.to_3x3()
            bp, bc = arm.data.bones[self.tronco[0]], arm.data.bones[self.tronco[1]]
            self.tronco_rest = ((mw3 @ bp.matrix_local.to_3x3()).normalized(), (mw3 @ bc.matrix_local.to_3x3()).normalized())
            # eixo da coluna no descanso (do quadril ao peito)
            self.tronco_eixo = (mw3 @ (bc.head_local - bp.head_local)).normalized()
        self._descanso()

    def _segmento(self, n, h, t):
        """O braço só conta da metade para a ponta contra o tronco: a junta do ombro fica dentro dele."""
        if n.startswith(("upperarm_", "UpperArm", "LeftUpperArm", "RightUpperArm")):
            return h + 0.45 * (t - h), t
        return h, t

    def _fundo(self, a, b, cap):
        pa, qa = self._segmento(a, *cap[a])
        pb, qb = self._segmento(b, *cap[b])
        return self.raios[a] + self.raios[b] - _dist_segmentos(pa, qa, pb, qb)

    def _descanso(self):
        """Chão e sobreposições do próprio modelo parado no descanso (a régua desconta isso)."""
        mw = self.arm.matrix_world
        cap = {}
        for n in {x for par in self.pares for x in par}:
            b = self.arm.data.bones[n]
            cap[n] = (np.array(mw @ b.head_local), np.array(mw @ b.tail_local))
        self.base = {f"{a} × {b}": max(0.0, self._fundo(a, b, cap)) for a, b in self.pares}
        z = []
        for o in self.malhas:
            co = np.array([o.matrix_world @ v.co for v in o.data.vertices[:: max(1, len(o.data.vertices) // 200000)]])
            if len(co):
                z.append(float(co[:, 2].min()))
        self.chao = min(z) if z else 0.0
        self.chao_descanso_cm = round(self.chao * 100, 1)

    def _eixo_dobradica(self):
        """Eixo natural de cada dobradiça, guardado no espaço do osso pai (acompanha o braço girando)."""
        mw = self.arm.matrix_world
        self.eixos = {}
        for p, f, para, _ in self.dobradicas:
            bp = self.arm.data.bones[p]
            t = (mw.to_3x3() @ (bp.tail_local - bp.head_local)).normalized()
            d = self.frente if para == "frente" else -self.frente
            natural = (t + 0.6 * d).normalized()
            n = t.cross(natural)
            if n.length < 1e-6:
                continue
            Rp = (mw @ bp.matrix_local).to_3x3().normalized()
            self.eixos[p] = Rp.inverted() @ n.normalized()

    def _mundo(self, n):
        pb = self.arm.pose.bones[n]
        mw = self.arm.matrix_world
        return np.array(mw @ pb.head), np.array(mw @ pb.tail), (mw @ pb.matrix).to_3x3().normalized()

    def medir(self, acao, malha_a_cada=2, max_amostras_malha=40):
        arm = self.arm
        ad = arm.animation_data or arm.animation_data_create()
        ad.action = acao
        if hasattr(ad, "action_slot") and ad.action_slot is None and getattr(acao, "slots", None):
            try:
                ad.action_slot = acao.slots[0]
            except Exception:
                pass
        ini, fim = (int(round(x)) for x in acao.frame_range)
        quadros = list(range(ini, fim + 1))
        cena = bpy.context.scene
        nome = acao.name
        sem_chao = any(s in nome.lower() for s in SEM_CHAO)
        laco = bool(acao.get("laco", getattr(acao, "use_cyclic", False)))
        torcao = {}
        contrario = {}
        de_lado = {}
        salto = {}
        atravessa = {}
        pes = {p: [] for p in self.pes}
        min_z = []
        anterior = None
        # medida dos ossos com a malha desligada (rápido); a malha entra só nas amostras do chão
        tronco = {"torcao": (0.0, None), "dobra": (0.0, None)}
        mods = [m for o in self.malhas for m in o.modifiers if m.type == "ARMATURE"]
        estados = [m.show_viewport for m in mods]
        for m in mods:
            m.show_viewport = False
        try:
            for i, q in enumerate(quadros):
                cena.frame_set(q)
                rot = {}
                for pb in arm.pose.bones:
                    b = pb.matrix_basis.to_quaternion()
                    rot[pb.name] = b
                    base = re.sub(r"_[lr]$", "", pb.name)
                    base = re.sub(r"^(Left|Right)", "", base)
                    lim = TORCAO.get(pb.name) or TORCAO.get(base)
                    if lim:
                        tw = abs(_twist_graus(b))
                        if tw > torcao.get(pb.name, (0, 0))[0]:
                            torcao[pb.name] = (tw, q)
                    if anterior is not None:
                        salto.setdefault(pb.name, []).append((_angulo_quat(anterior[pb.name], b), q))
                anterior = rot
                for p, f, para, rotulo in self.dobradicas:
                    if p not in self.eixos:
                        continue
                    hp, tp, Rp = self._mundo(p)
                    hf, tf, _ = self._mundo(f)
                    t = (tp - hp) / max(np.linalg.norm(tp - hp), 1e-9)
                    s = (tf - hf) / max(np.linalg.norm(tf - hf), 1e-9)
                    eixo = np.array(Rp @ self.eixos[p])
                    no_plano = s - eixo * (s @ eixo)
                    dobra = math.degrees(math.atan2(float(np.cross(t, no_plano) @ eixo), float(t @ no_plano)))
                    lado = math.degrees(math.asin(min(1.0, abs(float(s @ eixo)))))
                    if -dobra > contrario.get(rotulo, (0, 0))[0]:
                        contrario[rotulo] = (-dobra, q)
                    # de lado só conta com a junta dobrada (esticada, o "lado" não quer dizer nada)
                    if abs(dobra) > 25 and lado > de_lado.get(rotulo, (0, 0))[0]:
                        de_lado[rotulo] = (lado, q)
                cap = {}
                for a, b in self.pares:
                    for n in (a, b):
                        if n not in cap:
                            h, tt, _ = self._mundo(n)
                            cap[n] = (h, tt)
                    chave = f"{a} × {b}"
                    fundo = self._fundo(a, b, cap) - self.base[chave]
                    rel = fundo / max(min(self.raios[a], self.raios[b]), 1e-6)
                    if fundo > atravessa.get(chave, (0, 0, 0))[0]:
                        atravessa[chave] = (fundo, q, rel)
                for p in self.pes:
                    h, tt, _ = self._mundo(p)
                    pes[p].append((h, tt))
                if self.tronco:
                    Rp = self._mundo(self.tronco[0])[2]
                    Rc = self._mundo(self.tronco[1])[2]
                    Rp0, Rc0 = self.tronco_rest
                    # giro do peito em relação ao quadril, comparado com o descanso, no espaço do descanso
                    d = (Rp0 @ Rp.inverted() @ Rc @ Rc0.inverted()).to_quaternion()
                    if d.w < 0:
                        d = -d
                    ax = self.tronco_eixo
                    tw = math.degrees(2.0 * math.atan2(d.x * ax.x + d.y * ax.y + d.z * ax.z, d.w))
                    total = math.degrees(2.0 * math.acos(min(1.0, d.w)))
                    dobra = math.sqrt(max(0.0, total * total - tw * tw))
                    if abs(tw) > tronco["torcao"][0]:
                        tronco["torcao"] = (abs(tw), q)
                    if dobra > tronco["dobra"][0]:
                        tronco["dobra"] = (dobra, q)
        finally:
            for m, e in zip(mods, estados):
                m.show_viewport = e
        # chão: a malha de verdade em algumas amostras
        passo = max(malha_a_cada, int(math.ceil(len(quadros) / max_amostras_malha)))
        for q in quadros[::passo]:
            cena.frame_set(q)
            z = []
            for o in self.malhas:
                co = _co_avaliado(o)
                if len(co):
                    z.append(float(co[:, 2].min()))
            if not z:
                z = [min(float(min(h[2], t[2])) for h, t in (self._mundo(n)[:2] for n in self.ossos))]
            min_z.append((min(z), q))
        escorrega = self._escorrega(pes, quadros, laco)
        salto = self._trancos(salto)
        self._ultimo_tronco = tronco
        return self._julgar(nome, quadros, laco, sem_chao, torcao, contrario, de_lado, salto, atravessa, escorrega, min_z)

    def _trancos(self, seqs):
        """Tranco: um quadro gira muito mais que os vizinhos (osso virando de repente), não um golpe rápido."""
        out = {}
        for n, seq in seqs.items():
            v = [a for a, _ in seq]
            pior = (0.0, None)
            for i, (a, q) in enumerate(seq):
                viz = max(v[i - 1] if i > 0 else 0.0, v[i + 1] if i + 1 < len(v) else 0.0)
                if a > SALTO_MAX and a > 3 * viz and a > pior[0]:
                    pior = (a, q)
            maximo = max(v, default=0.0)
            out[n] = (pior[0], pior[1], maximo)
        return out

    def _escorrega(self, pes, quadros, laco):
        """Pé escorregando: em cada fase de apoio (veja `apoios`), o quanto o pé foge da velocidade do
        chão. Devolve {pé: (cm, quadro, no_lugar)}."""
        out = {}
        alvo, fases_de = apoios(pes, self.frente, self.H)
        if alvo is None:
            return out
        vel = float(np.linalg.norm(alvo))
        self.ultima_locomocao = vel > 0.25
        self.velocidade_do_chao = round(vel, 2)
        for p, (xy, fases) in fases_de.items():
            pior, quadro = 0.0, None
            for a, b in fases:
                tt = np.arange(b - a + 1, dtype=np.float64) / FPS
                resto = xy[a:b + 1] - (xy[a] + np.outer(tt, alvo))
                d = np.linalg.norm(resto, axis=1)
                k = int(np.argmax(d))
                if d[k] * 100 > pior:
                    pior, quadro = float(d[k] * 100), quadros[a + k]
            out[p] = (pior, quadro, self.ultima_locomocao)
        return out

    def _julgar(self, nome, quadros, laco, sem_chao, torcao, contrario, de_lado, salto, atravessa, escorrega, min_z):
        prob = []

        def add(tipo, osso, valor, limite, quadro, unidade, texto):
            prob.append({"tipo": tipo, "osso": osso, "valor": round(float(valor), 1), "limite": limite, "quadro": quadro, "unidade": unidade, "explicacao": texto})

        for n, (v, q) in torcao.items():
            base = re.sub(r"^(Left|Right)", "", re.sub(r"_[lr]$", "", n))
            lim = TORCAO.get(n) or TORCAO.get(base)
            if v > lim:
                add("torcao", n, v, lim, q, "graus", f"{n} torcido {v:.0f}° em volta do próprio eixo (máximo {lim}°): parece virado ou quebrado")
        for rot, (v, q) in contrario.items():
            if v > AO_CONTRARIO_MAX:
                add("ao_contrario", rot, v, AO_CONTRARIO_MAX, q, "graus", f"{rot} dobrando {v:.0f}° ao contrário")
        for rot, (v, q) in de_lado.items():
            lim = DE_LADO_MAX["cotovelo" if rot.startswith("cotovelo") else "joelho"]
            if v > lim:
                add("de_lado", rot, v, lim, q, "graus", f"{rot} dobrando {v:.0f}° para o lado (máximo {lim:.0f}°)")
        for n, (v, q, _) in salto.items():
            if q is not None:
                add("salto", n, v, SALTO_MAX, q, "graus", f"{n} gira {v:.0f}° de um quadro para o outro (tranco ou osso virando)")
        for par, (fundo, q, rel) in atravessa.items():
            cm = fundo * 100
            if cm > ATRAVESSA_MAX_CM and rel > 0.5:
                add("atravessa", par, cm, ATRAVESSA_MAX_CM, q, "cm", f"{par.replace(' × ', ' entra ')} {cm:.1f} cm (corpo sólido)")
        for p, (cm, q, loc) in escorrega.items():
            if cm > ESCORREGA_MAX_CM:
                add("escorrega", p, cm, ESCORREGA_MAX_CM, q, "cm", f"{p} escorrega {cm:.1f} cm enquanto está no chão" + (" (fora do ritmo da passada)" if loc else ""))
        abaixo = None
        if min_z and not sem_chao:
            z, q = min(min_z)
            if (self.chao - z) * 100 > CHAO_MAX_CM:
                abaixo = ((self.chao - z) * 100, q)
                add("abaixo_do_chao", "malha", abaixo[0], CHAO_MAX_CM, q, "cm", f"o corpo entra {abaixo[0]:.1f} cm no chão")
            if True:
                zz = min(x for x, _ in min_z)
                if (zz - self.chao) * 100 > FLUTUA_MIN_CM:
                    add("flutua", "malha", (zz - self.chao) * 100, FLUTUA_MIN_CM, quadros[0], "cm", f"nenhum pé encosta no chão: fica {(zz - self.chao) * 100:.0f} cm no ar")
        tronco = getattr(self, "_ultimo_tronco", None)
        if tronco and self.tronco:
            v, q = tronco["torcao"]
            if v > TRONCO_TORCAO_MAX:
                add("tronco", self.tronco[1], v, TRONCO_TORCAO_MAX, q, "graus", f"tronco torcido: o peito gira {v:.0f}° em relação ao quadril (máximo {TRONCO_TORCAO_MAX:.0f}°)")
            v, q = tronco["dobra"]
            if v > TRONCO_DOBRA_MAX:
                add("tronco", self.tronco[1], v, TRONCO_DOBRA_MAX, q, "graus", f"tronco dobrado {v:.0f}° em relação ao quadril (máximo {TRONCO_DOBRA_MAX:.0f}°)")
        prob.sort(key=lambda x: -x["valor"] / max(x["limite"], 1e-6))
        medidas = {
            "torcao_max_graus": {n: round(v, 1) for n, (v, _) in sorted(torcao.items(), key=lambda kv: -kv[1][0])[:6]},
            "ao_contrario_max_graus": {n: round(v, 1) for n, (v, _) in contrario.items()},
            "giro_por_quadro_max_graus": round(max((m for _, _, m in salto.values()), default=0.0), 1),
            "tranco_graus": {n: round(v, 1) for n, (v, q, _) in salto.items() if q is not None},
            "atravessa_max_cm": round(max((f * 100 for f, _, _ in atravessa.values()), default=0.0), 1),
            "escorrega_max_cm": {p: round(v[0], 1) for p, v in escorrega.items()},
            "chao_min_cm": round((min(min_z)[0] - self.chao) * 100, 1) if min_z else None,
        }
        if tronco and self.tronco:
            medidas["tronco_torcao_max_graus"] = round(tronco["torcao"][0], 1)
            medidas["tronco_dobra_max_graus"] = round(tronco["dobra"][0], 1)
        medidas["locomocao_no_lugar"] = bool(getattr(self, "ultima_locomocao", False))
        medidas["velocidade_da_passada_m_s"] = getattr(self, "velocidade_do_chao", 0.0)
        return {"nome": nome, "quadros": len(quadros), "laco": laco, "aprovado": not prob, "problemas": prob[:12], "medidas": medidas}


# ------------------------------------------------------------------ imagem

def _marcar(arm, problemas, raios, H):
    """Cápsulas vermelhas nos ossos com problema (no quadro atual)."""
    mat = bpy.data.materials.get("fc_problema") or bpy.data.materials.new("fc_problema")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (1.0, 0.05, 0.02, 1)
        for k in ("Emission Color", "Emission"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = (1.0, 0.1, 0.02, 1)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 3.0
    criados = []
    mw = arm.matrix_world
    nomes = set()
    for p in problemas:
        for n in re.split(r" × ", p["osso"]):
            if n in arm.pose.bones:
                nomes.add(n)
    for n in nomes:
        pb = arm.pose.bones[n]
        a, b = mw @ pb.head, mw @ pb.tail
        r = max(0.6 * raios.get(n, 0.03 * H), 0.012 * H)
        d = b - a
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=max(d.length, 1e-3), location=(a + b) / 2)
        o = bpy.context.active_object
        o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        o.data.materials.append(mat)
        o.show_in_front = True
        criados.append(o)
    return criados


def folha(caminho, conf, resultados, acoes, largura=300, altura=380, amostras=8, todos=False):
    """Uma imagem por animação (no pior quadro, com os ossos ruins em vermelho), lado a lado."""
    import fc_comum as c

    escolhidas = [(r, a) for r, a in zip(resultados, acoes) if todos or not r["aprovado"]]
    if not escolhidas:
        return None
    arm = conf.arm
    objs = conf.malhas or [arm]
    partes = []
    tmp = caminho + ".tmp"
    for i, (r, a) in enumerate(escolhidas[:12]):
        arm.animation_data.action = a
        q = r["problemas"][0]["quadro"] if r["problemas"] else int((a.frame_range[0] + a.frame_range[1]) / 2)
        bpy.context.scene.frame_set(q)
        marcas = _marcar(arm, r["problemas"][:3], conf.raios, conf.H)
        arq = f"{tmp}{i}.png"
        c.renderizar(arq, objs, direcao=(-0.6, -1.0, 0.35), largura=largura, altura=altura, amostras=amostras)
        for o in marcas:
            bpy.data.objects.remove(o, do_unlink=True)
        img = bpy.data.images.load(arq)
        px = np.empty(largura * altura * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(altura, largura, 4)
        # faixa embaixo: verde aprovado, vermelho reprovado
        px[:10, :, :3] = (0.15, 0.6, 0.3) if r["aprovado"] else (0.85, 0.12, 0.05)
        partes.append(px)
        bpy.data.images.remove(img)
        os.remove(arq)
    colunas = min(4, len(partes))
    linhas = int(math.ceil(len(partes) / colunas))
    vazio = np.zeros((altura, largura, 4), dtype=np.float32)
    vazio[..., 3] = 1
    partes += [vazio] * (linhas * colunas - len(partes))
    # a imagem do Blender começa embaixo: a primeira linha da folha fica no alto
    linhas_img = [np.concatenate(partes[k * colunas:(k + 1) * colunas], axis=1) for k in range(linhas)]
    junta = np.concatenate(linhas_img[::-1], axis=0)
    final = bpy.data.images.new("conferencia", width=largura * colunas, height=altura * linhas, alpha=True)
    final.pixels.foreach_set(junta.ravel())
    final.filepath_raw = caminho
    final.file_format = "PNG"
    final.save()
    return {"arquivo": caminho, "ordem": [r["nome"] for r, _ in escolhidas[:12]], "colunas": colunas}


def conferir(arm, acoes, H=None):
    conf = Conferencia(arm, H)
    resultados = [conf.medir(a) for a in acoes]
    return conf, resultados
