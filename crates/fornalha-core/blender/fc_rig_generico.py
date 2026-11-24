# Fornalha: esqueleto e animações para QUALQUER criatura de patas (quatro patas, aranha, inseto, ave,
# fera de duas patas com o corpo deitado) feita pela IA. Nada é feito para um bicho só: as patas são
# achadas pelos pés no chão e seguidas para cima até entrarem no corpo; a coluna é o meio do corpo ao
# longo do comprimento; cabeça na frente, cauda atrás. As animações são procedurais (como nos jogos com
# criaturas geradas): passada com fases por número de patas, pé no chão com IK de dois ossos, corpo que
# sobe e desce com o passo, coluna e cauda em onda com atraso, cabeça estabilizada; ataque com
# preparação, bote e volta; dano e morte. Tudo assado em ações (a engine recebe pronto).
import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

import fc_rig_ia

FPS = 30


def _co(obj):
    m = obj.matrix_world
    return np.array([(m @ v.co)[:] for v in obj.data.vertices])


def _componentes(pts, celula):
    """Componentes ligados (grade 2D em x, y) de pontos. Devolve lista de arrays de índices."""
    if not len(pts):
        return []
    g = np.floor(pts[:, :2] / celula).astype(np.int64)
    chaves = {}
    for i, (a, b) in enumerate(g):
        chaves.setdefault((int(a), int(b)), []).append(i)
    visto = set()
    comps = []
    for k in chaves:
        if k in visto:
            continue
        pilha, comp = [k], []
        visto.add(k)
        while pilha:
            c = pilha.pop()
            comp.extend(chaves[c])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (c[0] + dx, c[1] + dy)
                    if n in chaves and n not in visto:
                        visto.add(n)
                        pilha.append(n)
        comps.append(np.array(comp))
    return comps


def contar_pes(co):
    """Quantos pés (pedaços compactos na fatia do chão)."""
    mn, mx = co.min(0), co.max(0)
    W, L, H = (mx - mn).tolist()
    tam = max(W, L, H)
    chao = np.where(co[:, 2] - mn[2] < 0.035 * H)[0]
    n = 0
    for c in _componentes(co[chao], 0.02 * tam):
        if len(c) < 12:
            continue
        ext = co[chao[c], :2].max(0) - co[chao[c], :2].min(0)
        if max(ext) <= 0.22 * max(W, L):
            n += 1
    return n


class Medida:
    """Pontos do esqueleto medidos na malha (z para cima, frente em -Y)."""

    def __init__(self, obj):
        co = _co(obj)
        self.co = co
        mn, mx = co.min(0), co.max(0)
        self.W, self.L, self.H = (mx - mn).tolist()
        self.tam = max(self.W, self.L, self.H)
        self.patas = []        # [{"pe":, "tornozelo":, "joelho":, "quadril":, "vertices": idx}]
        self._achar_patas()
        self._coluna()

    def _achar_patas(self):
        co, H, tam = self.co, self.H, self.tam
        cel = 0.02 * tam
        chao = np.where(co[:, 2] < 0.035 * H)[0]
        comps = [chao[c] for c in _componentes(co[chao], cel)]
        comps = [c for c in comps if len(c) >= 12]
        # pé é compacto; um pedaço comprido no chão (cauda, barriga) não é pé
        pes = []
        for c in comps:
            ext = co[c, :2].max(0) - co[c, :2].min(0)
            if max(ext) > 0.22 * max(self.W, self.L):
                continue
            pes.append(c)
        usados = np.zeros(len(co), dtype=bool)
        for c in pes:
            cen = co[c, :2].mean(0)
            trilha = [np.array([cen[0], cen[1], float(co[c, 2].min())])]
            area0 = None
            verts = list(c)
            z = 0.035 * H
            passo = 0.02 * H
            while z < 0.8 * H:
                fatia = np.where((co[:, 2] >= z) & (co[:, 2] < z + passo))[0]
                if not len(fatia):
                    break
                cs = [fatia[k] for k in _componentes(co[fatia], cel)]
                # o pedaço que continua a pata (centro mais perto do último)
                melhor, dmin = None, 1e9
                for k in cs:
                    d = float(np.linalg.norm(co[k, :2].mean(0) - trilha[-1][:2]))
                    if d < dmin:
                        melhor, dmin = k, d
                if melhor is None or dmin > 0.08 * tam:
                    break
                ext = co[melhor, :2].max(0) - co[melhor, :2].min(0)
                area = float(ext[0] * ext[1]) + 1e-9
                if area0 is None:
                    area0 = area
                # entrou no corpo: o pedaço fica muito maior que a pata
                if area > 6.0 * area0 and z > 0.12 * H:
                    break
                cen = co[melhor].mean(0)
                trilha.append(np.array([cen[0], cen[1], z + passo / 2]))
                verts.extend(list(melhor))
                z += passo
            if len(trilha) < 4:
                continue
            tr = np.array(trilha)
            alt = tr[-1, 2] - tr[0, 2]

            def em(frac):
                alvo = tr[0, 2] + alt * frac
                i = int(np.argmin(np.abs(tr[:, 2] - alvo)))
                return tr[i]
            pe = tr[0].copy()
            pe[2] = 0.01 * H
            self.patas.append({"pe": pe, "tornozelo": em(0.18), "joelho": em(0.55), "quadril": tr[-1] + np.array([0, 0, 0.03 * H]),
                               "vertices": np.array(sorted(set(verts)))})
            usados[np.array(verts)] = True
        self.nas_patas = usados
        # frente para trás, depois esquerda/direita
        self.patas.sort(key=lambda p: (round(p["quadril"][1] / (0.15 * self.L + 1e-9)), -p["quadril"][0]))

    def _coluna(self):
        co, H = self.co, self.H
        corpo = co[~self.nas_patas] if self.nas_patas.any() else co
        z_quadris = np.median([p["quadril"][2] for p in self.patas]) if self.patas else 0.3 * H
        corpo = corpo[corpo[:, 2] > z_quadris * 0.6] if len(corpo) > 100 else corpo
        y0, y1 = float(corpo[:, 1].min()), float(corpo[:, 1].max())
        pts = []
        for t in np.linspace(0.0, 1.0, 24):
            y = y0 + (y1 - y0) * t
            f = corpo[np.abs(corpo[:, 1] - y) < 0.03 * self.L + 1e-6]
            if len(f) >= 5:
                pts.append(np.array([float(np.median(f[:, 0])), y, float(np.median(f[:, 2]))]))
        self.linha = np.array(pts) if pts else np.array([[0, y0, 0.5 * H], [0, y1, 0.5 * H]])
        # quadril e peito pelos quadris das patas de trás e da frente
        if self.patas:
            ys = np.array([p["quadril"][1] for p in self.patas])
            self.y_peito, self.y_quadril = float(ys.min()), float(ys.max())
        else:
            self.y_peito, self.y_quadril = y0 + 0.3 * (y1 - y0), y0 + 0.7 * (y1 - y0)
        if self.y_quadril - self.y_peito < 0.15 * self.L:
            meio = (self.y_quadril + self.y_peito) / 2
            self.y_peito, self.y_quadril = meio - 0.12 * self.L, meio + 0.12 * self.L

    def na_linha(self, y):
        ln = self.linha
        i = np.argsort(ln[:, 1])
        return np.array([np.interp(y, ln[i, 1], ln[i, k]) for k in range(3)])


def criar_esqueleto(nome, m):
    """Ossos: raiz, quadril, coluna_1..3 (quadril → peito), pescoço e cabeça (frente), cauda (trás) e
    três ossos por pata (coxa, canela, pé). Devolve (armadura, mapa de nomes)."""
    dados = bpy.data.armatures.new(nome + "_esqueleto")
    arm = bpy.data.objects.new(nome + "_esqueleto", dados)
    bpy.context.scene.collection.objects.link(arm)
    for o in bpy.context.scene.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = {}

    def osso(n, a, b, pai=None, ligado=False):
        eb = dados.edit_bones.new(n)
        eb.head, eb.tail = Vector(a), Vector(b)
        if (eb.tail - eb.head).length < 1e-4:
            eb.tail = eb.head + Vector((0, -0.02 * m.tam, 0))
        eb.align_roll(Vector((0, 0, 1)) if abs((eb.tail - eb.head).normalized().z) < 0.9 else Vector((0, -1, 0)))
        if pai:
            eb.parent = ebs[pai]
            eb.use_connect = ligado
        ebs[n] = eb
        return eb

    ln = m.linha
    y_frente, y_tras = float(ln[:, 1].min()), float(ln[:, 1].max())
    q = m.na_linha(m.y_quadril)
    p = m.na_linha(m.y_peito)
    osso("raiz", (0, 0, 0), (0, -0.1 * m.tam, 0))
    osso("quadril", q, q + np.array([0, -0.05 * m.L, 0]), "raiz")
    pontos = [m.na_linha(m.y_quadril + (m.y_peito - m.y_quadril) * t) for t in np.linspace(0, 1, 4)]
    pai = "quadril"
    for k in range(3):
        osso(f"coluna_{k + 1}", pontos[k], pontos[k + 1], pai, ligado=k > 0)
        pai = f"coluna_{k + 1}"
    # pescoço e cabeça: do peito até a frente (a cabeça é o último terço)
    frente = m.na_linha(y_frente)
    # a cabeça costuma ficar mais alta que a linha: usa o topo do que está na frente
    f = m.co[m.co[:, 1] < y_frente + 0.12 * m.L]
    if len(f):
        frente = np.array([float(np.median(f[:, 0])), y_frente, float(np.percentile(f[:, 2], 60))])
    pesc = [p + (frente - p) * t for t in (0.0, 0.33, 0.62, 1.0)]
    osso("pescoco_1", pesc[0], pesc[1], "coluna_3", ligado=True)
    osso("pescoco_2", pesc[1], pesc[2], "pescoco_1", ligado=True)
    osso("cabeca", pesc[2], pesc[3], "pescoco_2", ligado=True)
    nomes = {"cauda": []}
    if y_tras - m.y_quadril > 0.12 * m.L:
        n = 6 if y_tras - m.y_quadril > 0.35 * m.L else 3
        cau = [m.na_linha(m.y_quadril + (y_tras - m.y_quadril) * t) for t in np.linspace(0, 1, n + 1)]
        pai = "quadril"
        for k in range(n):
            osso(f"cauda_{k + 1}", cau[k], cau[k + 1], pai, ligado=k > 0)
            nomes["cauda"].append(f"cauda_{k + 1}")
            pai = f"cauda_{k + 1}"
    nomes["patas"] = []
    for i, pt in enumerate(m.patas):
        pai = "coluna_3" if abs(pt["quadril"][1] - m.y_peito) < abs(pt["quadril"][1] - m.y_quadril) else "quadril"
        ponta = pt["pe"] + np.array([0, -0.04 * m.tam, 0])
        osso(f"pata_{i}_coxa", pt["quadril"], pt["joelho"], pai)
        osso(f"pata_{i}_canela", pt["joelho"], pt["tornozelo"], f"pata_{i}_coxa", ligado=True)
        osso(f"pata_{i}_pe", pt["tornozelo"], ponta, f"pata_{i}_canela", ligado=True)
        nomes["patas"].append([f"pata_{i}_coxa", f"pata_{i}_canela", f"pata_{i}_pe"])
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm, nomes


def pesar(obj, arm, m, nomes):
    """Pata só nos ossos dela (os vértices que a trilha juntou); o resto (corpo, pescoço, cabeça, cauda)
    pelo inverso da distância aos ossos do corpo; fronteiras alisadas."""
    co = m.co
    mw = arm.matrix_world
    ossos = [b for b in arm.data.bones if b.name != "raiz"]
    idx = {b.name: i for i, b in enumerate(ossos)}

    def seg(b):
        a, c = np.array(mw @ b.head_local), np.array(mw @ b.tail_local)
        ab = c - a
        t = np.clip(((co - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
        return np.linalg.norm(co - (a + t[:, None] * ab), axis=1)
    D = np.stack([seg(b) for b in ossos], axis=1)
    pode = np.zeros_like(D, dtype=bool)
    corpo = [n for n in idx if not n.startswith("pata_")]
    pode[:, [idx[n] for n in corpo]] = True
    for i, pt in enumerate(m.patas):
        vs = pt["vertices"]
        cols = [idx[n] for n in nomes["patas"][i]]
        pode[vs] = False
        pode[np.ix_(vs, cols)] = True
        # o alto da pata mistura com o corpo
        alto = vs[co[vs, 2] > pt["joelho"][2] + 0.6 * (pt["quadril"][2] - pt["joelho"][2])]
        pode[np.ix_(alto, [idx[n] for n in corpo])] = True
    Dm = np.where(pode, D, np.inf)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    grupos = {b.name: obj.vertex_groups.new(name=b.name) for b in ossos}
    ordem = np.argsort(Dm, axis=1)[:, :3]
    eps = 0.01 * m.tam
    for vi in range(len(co)):
        ks = ordem[vi]
        d = Dm[vi, ks]
        ok = np.isfinite(d)
        if not ok.any():
            continue
        w = 1.0 / (d[ok] + eps) ** 4
        w /= w.sum()
        for k, peso in zip(ks[ok], w):
            if peso > 0.01:
                grupos[ossos[k].name].add([vi], float(peso), "REPLACE")
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=2)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    finally:
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    obj.parent = arm
    mod = obj.modifiers.new("esqueleto", "ARMATURE")
    mod.object = arm


# ---------------------------------------------------------------- animação procedural

def _fases(m, correndo):
    """Fase de cada pata no ciclo (0 a 1), pelo número de patas e pelo lado."""
    n = len(m.patas)
    lado = [1 if p["quadril"][0] > 0 else -1 for p in m.patas]
    if n == 4:
        # andar: sequência lateral (FE, TD, FD, TE); correr: trote (diagonais juntas)
        ordem = sorted(range(4), key=lambda i: m.patas[i]["quadril"][1])
        frente, tras = ordem[:2], ordem[2:]
        fe = next(i for i in frente if lado[i] > 0) if any(lado[i] > 0 for i in frente) else frente[0]
        fd = [i for i in frente if i != fe][0]
        te = next(i for i in tras if lado[i] > 0) if any(lado[i] > 0 for i in tras) else tras[0]
        td = [i for i in tras if i != te][0]
        if correndo:
            f = {fe: 0.0, td: 0.0, fd: 0.5, te: 0.5}
        else:
            f = {fe: 0.0, td: 0.25, fd: 0.5, te: 0.75}
        return [f[i] for i in range(4)]
    if n == 2:
        return [0.0 if lado[i] > 0 else 0.5 for i in range(2)]
    if n >= 6:
        # trípode/tetrápode alternado com uma onda da frente para trás
        ordem = sorted(range(n), key=lambda i: (lado[i], m.patas[i]["quadril"][1]))
        f = [0.0] * n
        por_lado = {1: [i for i in ordem if lado[i] > 0], -1: [i for i in ordem if lado[i] < 0]}
        for s, lista in por_lado.items():
            for k, i in enumerate(lista):
                f[i] = (0.5 * ((k + (0 if s > 0 else 1)) % 2) + 0.06 * k) % 1.0
        return f
    return [i / max(n, 1) for i in range(n)]


def _dois_ossos(arm, a, b, alvo, dica, mw):
    """IK de dois ossos (a: coxa, b: canela) para a ponta de b chegar no alvo (mundo); o joelho dobra
    para o lado da `dica` (direção do joelho no descanso)."""
    pa, pb_ = arm.pose.bones[a], arm.pose.bones[b]
    l1, l2 = pa.bone.length, pb_.bone.length
    ombro = mw @ pa.head
    d = alvo - ombro
    dist = max(abs(l1 - l2) + 1e-4, min(d.length, l1 + l2 - 1e-4))
    eixo = d.normalized()
    k = dica - eixo * dica.dot(eixo)
    if k.length < 1e-5:
        k = Vector((0, -1, 0)) - eixo * eixo.y * -1
    k.normalize()
    x = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(l1 * l1 - x * x, 0.0))
    joelho = ombro + eixo * x + k * h
    _apontar(pa, joelho, mw)
    _apontar(pb_, ombro + eixo * dist, mw)


def _apontar(pb, alvo_mundo, mw):
    inv = mw.inverted()
    cabeca = pb.matrix.translation.copy()
    atual = (pb.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
    desejado = ((inv @ alvo_mundo) - cabeca).normalized()
    giro = atual.rotation_difference(desejado).to_matrix().to_4x4()
    pb.matrix = Matrix.Translation(cabeca) @ giro @ Matrix.Translation(-cabeca) @ pb.matrix
    bpy.context.view_layer.update()


class Animador:
    def __init__(self, arm, m, nomes):
        self.arm, self.m, self.nomes = arm, m, nomes
        self.mw = arm.matrix_world
        self.acoes = []
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
        bpy.context.view_layer.update()
        # descanso: onde ficam o tornozelo e o pé de cada pata e para onde dobra o joelho
        self.descanso = []
        for i, ns in enumerate(nomes["patas"]):
            c, ca, p = (arm.data.bones[n] for n in ns)
            tor = self.mw @ ca.tail_local
            joe = self.mw @ c.tail_local
            qua = self.mw @ c.head_local
            meio = qua.lerp(tor, 0.5)
            self.descanso.append({"tornozelo": tor, "dica": (joe - meio)})
        alturas = [self.mw @ arm.data.bones[ns[0]].head_local for ns in nomes["patas"]]
        self.altura_pata = float(np.mean([a.z for a in alturas])) if alturas else 0.3 * m.H

    def _limpar(self):
        for pb in self.arm.pose.bones:
            pb.rotation_quaternion = Quaternion()
            pb.location = Vector()
        bpy.context.view_layer.update()

    def _girar(self, nome, eixo, graus):
        """Gira o osso em volta de um eixo do mundo (graus), somando ao que já tem."""
        pb = self.arm.pose.bones.get(nome)
        if pb is None:
            return
        R = pb.bone.matrix_local.to_3x3()
        q = Quaternion(Vector(eixo), math.radians(graus))
        local = (R.inverted() @ q.to_matrix() @ R).to_quaternion()
        pb.rotation_quaternion = local @ pb.rotation_quaternion

    def _chave(self, quadro):
        for pb in self.arm.pose.bones:
            pb.keyframe_insert("rotation_quaternion", frame=quadro, group=pb.name)
        q = self.arm.pose.bones["quadril"]
        q.keyframe_insert("location", frame=quadro, group="quadril")

    def _nova_acao(self, nome, quadros, laco):
        ad = self.arm.animation_data or self.arm.animation_data_create()
        act = bpy.data.actions.new(nome)
        act.use_fake_user = True
        ad.action = act
        act["laco"] = laco
        try:
            act.use_frame_range = True
            act.frame_start, act.frame_end = 1, quadros
            act.use_cyclic = laco
        except Exception:
            pass
        self.acoes.append(act)
        return act

    def _quadril(self, desloc):
        q = self.arm.pose.bones["quadril"]
        R = q.bone.matrix_local.to_3x3()
        q.location = R.inverted() @ Vector(desloc)

    def _coluna_onda(self, fase, amp_lado, amp_cima):
        for k in (1, 2, 3):
            self._girar(f"coluna_{k}", (0, 0, 1), amp_lado * math.sin(fase - k * 0.4) / 3)
            self._girar(f"coluna_{k}", (1, 0, 0), amp_cima * math.sin(2 * fase - k * 0.4) / 3)
        for k, n in enumerate(self.nomes["cauda"], 1):
            self._girar(n, (0, 0, 1), amp_lado * 1.6 * math.sin(fase - 0.6 - k * 0.55) * (0.6 + 0.4 * k / len(self.nomes["cauda"])))
            self._girar(n, (1, 0, 0), -amp_cima * 0.5 * math.sin(2 * fase - k * 0.5))

    def _cabeca_firme(self, fase, amp):
        # o pescoço compensa o balanço da coluna: a cabeça fica quase parada (como os bichos de verdade)
        self._girar("pescoco_1", (0, 0, 1), -amp * 0.6 * math.sin(fase - 1.2))
        self._girar("pescoco_2", (1, 0, 0), amp * 0.3 * math.sin(2 * fase - 1.0))

    def _patas(self, t_ciclo, fases, passo, altura_pe, apoio, desloc_corpo):
        """Põe cada pata na fase dela: no apoio o pé vai para trás no chão; no ar, volta pela frente."""
        bpy.context.view_layer.update()
        frente = Vector((0, -1, 0))
        for i, ns in enumerate(self.nomes["patas"]):
            f = (t_ciclo + fases[i]) % 1.0
            base = self.descanso[i]["tornozelo"]
            if f < apoio:
                u = f / apoio
                av = (0.5 - u) * passo
                sobe = 0.0
            else:
                u = (f - apoio) / (1 - apoio)
                av = (-0.5 + u) * passo
                sobe = math.sin(math.pi * u) * altura_pe
            alvo = base + frente * av + Vector((0, 0, sobe))
            _dois_ossos(self.arm, ns[0], ns[1], alvo, self.descanso[i]["dica"], self.mw)
            # o pé dobra um pouco no ar (os dedos apontam para baixo) e fica reto no chão
            if f >= apoio:
                self._girar(ns[2], (1, 0, 0), 25 * math.sin(math.pi * (f - apoio) / (1 - apoio)))
            bpy.context.view_layer.update()

    def ciclo(self, nome, quadros, correndo):
        m = self.m
        fases = _fases(m, correndo)
        perna = max(self.altura_pata, 0.05 * m.H)
        passo = (0.85 if correndo else 0.5) * perna
        altura_pe = (0.32 if correndo else 0.2) * perna
        apoio = 0.45 if correndo else 0.65
        self._nova_acao(nome, quadros, True)
        for q in range(1, quadros + 1):
            t = (q - 1) / quadros
            fase = 2 * math.pi * t
            self._limpar()
            # corpo: sobe e desce duas vezes por ciclo; no correr, inclina para a frente
            bob = (0.035 if correndo else 0.018) * perna * math.cos(2 * fase)
            self._quadril((0, 0, bob - (0.04 if correndo else 0.0) * perna))
            if correndo:
                self._girar("quadril", (1, 0, 0), -4)
            self._coluna_onda(fase, 6 if correndo else 4, 3 if correndo else 1.5)
            self._cabeca_firme(fase, 6 if correndo else 4)
            bpy.context.view_layer.update()
            self._patas(t, fases, passo, altura_pe, apoio, 0)
            self._chave(q)

    def parado(self, quadros=90):
        self._nova_acao("parado", quadros, True)
        for q in range(1, quadros + 1):
            fase = 2 * math.pi * (q - 1) / quadros
            self._limpar()
            self._quadril((0, 0, 0.006 * self.m.H * math.sin(fase)))
            self._girar("coluna_3", (1, 0, 0), 1.5 * math.sin(fase))
            self._girar("pescoco_1", (0, 0, 1), 8 * math.sin(fase * 0.5))
            self._girar("cabeca", (1, 0, 0), 3 * math.sin(fase + 0.6))
            for k, n in enumerate(self.nomes["cauda"], 1):
                self._girar(n, (0, 0, 1), 5 * math.sin(fase - k * 0.5))
            bpy.context.view_layer.update()
            self._patas(0.0, [0.0] * len(self.nomes["patas"]), 0.0, 0.0, 1.0, 0)
            self._chave(q)

    def atacar(self, quadros=36):
        """Preparação (recua e ergue a frente), bote (avança com a cabeça baixa), volta."""
        m = self.m
        self._nova_acao("atacar", quadros, False)
        for q in range(1, quadros + 1):
            t = (q - 1) / (quadros - 1)
            if t < 0.4:
                u = math.sin(t / 0.4 * math.pi / 2)
                recuo, ergue, bote = 0.12 * u, 18 * u, 0.0
            elif t < 0.6:
                u = (t - 0.4) / 0.2
                recuo, ergue, bote = 0.12 * (1 - u), 18 * (1 - u) - 22 * u, 0.25 * u
            else:
                u = (t - 0.6) / 0.4
                e = 1 - (1 - u) ** 2
                recuo, ergue, bote = 0.0, -22 * (1 - e), 0.25 * (1 - e)
            self._limpar()
            self._quadril((0, (recuo - bote) * m.L * 0.5, 0.0))
            self._girar("coluna_3", (1, 0, 0), -ergue * 0.4)
            self._girar("pescoco_1", (1, 0, 0), -ergue * 0.4)
            self._girar("cabeca", (1, 0, 0), ergue * 0.5)
            for k, n in enumerate(self.nomes["cauda"], 1):
                self._girar(n, (1, 0, 0), ergue * 0.15)
            bpy.context.view_layer.update()
            self._patas(0.0, [0.0] * len(self.nomes["patas"]), 0.0, 0.0, 1.0, 0)
            # as patas da frente (aranha, fera) levantam na preparação e golpeiam no bote
            for i, ns in enumerate(self.nomes["patas"][:2] if len(self.nomes["patas"]) >= 6 else []):
                self._girar(ns[0], (1, 0, 0), -ergue * 2.2)
            self._chave(q)

    def dano(self, quadros=20):
        self._nova_acao("dano", quadros, False)
        for q in range(1, quadros + 1):
            t = (q - 1) / (quadros - 1)
            u = math.sin(min(t / 0.3, 1.0) * math.pi / 2) * (1 - max(0.0, (t - 0.3) / 0.7))
            self._limpar()
            self._quadril((0, 0.04 * self.m.L * u, 0))
            self._girar("coluna_3", (1, 0, 0), 8 * u)
            self._girar("pescoco_1", (0, 0, 1), 14 * u)
            self._girar("cabeca", (1, 0, 0), -10 * u)
            bpy.context.view_layer.update()
            self._patas(0.0, [0.0] * len(self.nomes["patas"]), 0.0, 0.0, 1.0, 0)
            self._chave(q)

    def morrer(self, quadros=50):
        self._nova_acao("morrer", quadros, False)
        m = self.m
        for q in range(1, quadros + 1):
            t = (q - 1) / (quadros - 1)
            u = min(1.0, t / 0.7)
            u = u * u * (3 - 2 * u)
            self._limpar()
            self._quadril((0.0, 0.0, -0.75 * self.altura_pata * u))
            self._girar("quadril", (0, 1, 0), 25 * u)
            self._girar("pescoco_1", (1, 0, 0), 25 * u)
            self._girar("cabeca", (0, 0, 1), 20 * u)
            for k, n in enumerate(self.nomes["cauda"], 1):
                self._girar(n, (0, 0, 1), 10 * u)
            bpy.context.view_layer.update()
            # as patas dobram e o corpo deita
            for i, ns in enumerate(self.nomes["patas"]):
                s = 1 if self.m.patas[i]["quadril"][0] > 0 else -1
                self._girar(ns[0], (0, 1, 0), -s * 35 * u)
                self._girar(ns[1], (1, 0, 0), 40 * u)
            self._chave(q)

    def tudo(self):
        self.parado()
        self.ciclo("andar", 40, False)
        self.ciclo("correr", 22, True)
        self.atacar()
        self.dano()
        self.morrer()
        self.arm.animation_data.action = self.acoes[0]
        return self.acoes


def rigar(obj, nome, altura):
    """Criatura de patas da IA → (armadura, ações, info)."""
    fc_rig_ia.normalizar(obj, altura)
    m = Medida(obj)
    arm, nomes = criar_esqueleto(nome, m)
    pesar(obj, arm, m, nomes)
    acoes = Animador(arm, m, nomes).tudo() if nomes["patas"] else []
    return arm, acoes, {"patas": len(m.patas), "cauda": len(nomes["cauda"]), "ossos": len(arm.data.bones), "pesos": "patas-e-corpo",
                        "envergadura_m": round(m.W, 3), "comprimento_m": round(m.L, 3)}


# ---------------------------------------------------------------- passada com IK em outro esqueleto

class _PataSimples:
    def __init__(self, quadril):
        self.q = quadril


def passada_com_ik(arm, acao, patas, correndo, quadros):
    """Põe a passada com pé no chão (IK de dois ossos, fases pelo número de patas) nas patas de um
    esqueleto que já tem a ação (ex.: o dragão: asas, pescoço e cauda ficam como estão). `patas` é a
    lista de [coxa, canela, pé] de cada pata. Regrava só as patas."""
    mw = arm.matrix_world
    ad = arm.animation_data
    antes = ad.action
    ad.action = acao
    cena = bpy.context.scene
    malhas = [o for o in cena.objects if o.type == "MESH" and any(md.type == "ARMATURE" for md in o.modifiers)]
    estados = [(md, md.show_viewport) for o in malhas for md in o.modifiers if md.type == "ARMATURE"]
    for md, _ in estados:
        md.show_viewport = False
    try:
        # descanso de cada pata (sem a ação): tornozelo e dobra do joelho
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        descanso = []
        quadris = []
        for ns in patas:
            c, ca = arm.data.bones[ns[0]], arm.data.bones[ns[1]]
            tor, joe, qua = mw @ ca.tail_local, mw @ c.tail_local, mw @ c.head_local
            descanso.append({"tornozelo": tor, "dica": joe - qua.lerp(tor, 0.5)})
            quadris.append(np.array(qua[:]))
        arm.data.pose_position = "POSE"
        bpy.context.view_layer.update()

        class M:
            pass
        m = M()
        m.patas = [{"quadril": q} for q in quadris]
        fases = _fases(m, correndo)
        perna = float(np.mean([q[2] for q in quadris]))
        passo = (0.85 if correndo else 0.5) * perna
        altura_pe = (0.3 if correndo else 0.18) * perna
        apoio = 0.45 if correndo else 0.65
        frente = Vector((0, -1, 0))
        for q in range(1, quadros + 1):
            t = (q - 1) / quadros
            cena.frame_set(q)
            for i, ns in enumerate(patas):
                for n in ns:
                    arm.pose.bones[n].rotation_quaternion = Quaternion()
            bpy.context.view_layer.update()
            for i, ns in enumerate(patas):
                f = (t + fases[i]) % 1.0
                if f < apoio:
                    av, sobe = (0.5 - f / apoio) * passo, 0.0
                else:
                    u = (f - apoio) / (1 - apoio)
                    av, sobe = (-0.5 + u) * passo, math.sin(math.pi * u) * altura_pe
                # o pé fica no chão do mundo (o quadril sobe e desce, o pé não)
                alvo = descanso[i]["tornozelo"] + frente * av + Vector((0, 0, sobe))
                _dois_ossos(arm, ns[0], ns[1], alvo, descanso[i]["dica"], mw)
                for n in ns:
                    arm.pose.bones[n].keyframe_insert("rotation_quaternion", frame=q, group=n)
    finally:
        ad.action = antes
        for md, v in estados:
            md.show_viewport = v
