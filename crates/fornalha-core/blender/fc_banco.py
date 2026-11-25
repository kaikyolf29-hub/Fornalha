# Fornalha: banco de movimento. Cataloga as capturas (Quaternius, ACCAD, 100STYLE, Mixamo da pessoa,
# CMU, qualquer BVH/FBX/glb) com etiquetas em português, e aplica as escolhidas num personagem com o
# esqueleto de jogo: recorte, velocidade, "no lugar" (tira o deslocamento do quadril) e recorte de
# ciclo automático (acha o trecho que fecha em laço numa tomada longa).
import math
import os
import re

import bpy
import numpy as np
from mathutils import Matrix, Vector

import fc_retarget

FPS = 30

# palavra no nome do clipe (inglês ou português) → etiqueta
ETIQUETAS = [
    (r"idle|stand(?!to)|parado|ready|relax", "parado"),
    (r"walk|andar|stroll|swagger|skip", "andar"),
    (r"run|jog|sprint|correr", "correr"),
    (r"sprint", "rapido"),
    (r"backward|_b[rw]\b|back_?walk", "de_costas"),
    (r"side_?step|strafe|_s[rw]\b|lateral", "de_lado"),
    (r"turn|virar", "virar"),
    (r"jump|hop|leap|pul", "pular"),
    (r"sword|espada|slash|greatsword", "espada"),
    (r"shield|escudo", "escudo"),
    (r"attack|atac|slash|stab|combo|sword_regular|swing", "ataque"),
    (r"punch|jab|cross|hook|uppercut|backfist|soco", "soco"),
    (r"kick|roundhouse|crescent|chute|capoeira", "chute"),
    (r"block|defend|defen|parry|guard", "defesa"),
    (r"dodge|duck|roll|esquiv", "esquiva"),
    (r"death|die|dying|morr|morte", "morte"),
    (r"hit|knockback|dano|damage|stagger", "dano"),
    (r"crouch|agach|sneak", "agachado"),
    (r"crawl|rastej", "rastejar"),
    (r"zombie|zumbi", "zumbi"),
    (r"box|pick_?up|carry|lift|put_?down", "carregar"),
    (r"victory|taunt|bow(?!l)|wave|cheer|gesto", "gesto"),
    (r"dance|danc|capoeira|form_", "danca"),
    (r"lie|deitad|lying", "deitado"),
    (r"spell|cast|magic|magia", "magia"),
    (r"interact|(^|_)(use|open)(_|$)", "interagir"),
    (r"fall|cair|land|aterr", "cair"),
    (r"swim|nadar", "nadar"),
    (r"climb|escal", "escalar"),
    (r"sit|sentar", "sentar"),
    (r"female|mulher", "feminino"),
    (r"martial|kick|roundhouse|crescent|punch|jab|hook|uppercut|backfist|block|dodge|duck|form_", "luta"),
]
# 100STYLE: <Estilo>_<código>.bvh
CODIGOS_100STYLE = {"BR": ["correr", "de_costas"], "BW": ["andar", "de_costas"], "FR": ["correr"], "FW": ["andar"], "ID": ["parado"],
                    "SR": ["correr", "de_lado"], "SW": ["andar", "de_lado"], "TR1": ["virar"], "TR2": ["virar"], "TR3": ["virar"]}


def etiquetas(nome, fonte=""):
    n = nome.replace("-", "_")
    out = []
    if fonte == "100style":
        m = re.match(r"^(.+?)_([A-Z]+\d?)$", n)
        if m:
            out += CODIGOS_100STYLE.get(m.group(2), []) + ["estilo:" + m.group(1).lower()]
    baixo = n.lower()
    for padrao, et in ETIQUETAS:
        if re.search(padrao, baixo) and et not in out:
            out.append(et)
    return out


def _limpar(objs, acoes):
    for o in objs:
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    for a in acoes:
        if a.name in bpy.data.actions:
            bpy.data.actions.remove(a)
    for arm in list(bpy.data.armatures):
        if arm.users == 0:
            bpy.data.armatures.remove(arm)


def _quadril(arm):
    mapa = fc_retarget.mapa_do_esqueleto([b.name for b in arm.data.bones])
    for fonte, alvo in mapa.items():
        if alvo == "pelvis":
            return fonte
    return None


def _usar(arm, acao):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = acao
    if hasattr(ad, "action_slot") and ad.action_slot is None and getattr(acao, "slots", None):
        try:
            ad.action_slot = acao.slots[0]
        except Exception:
            pass


def _medir(arm, acao, quadril):
    """Duração, deslocamento do quadril no chão, altura e se fecha em laço."""
    _usar(arm, acao)
    ini, fim = (int(round(x)) for x in acao.frame_range)
    cena = bpy.context.scene
    pos = []
    rot = []
    mapa = fc_retarget.mapa_do_esqueleto([b.name for b in arm.data.bones])
    principais = [n for n, a in mapa.items() if re.match(r"^(thigh|calf|upperarm|lowerarm|spine_0\d|head)", a)]
    for q in (ini, fim):
        cena.frame_set(q)
        if quadril:
            pos.append(arm.matrix_world @ arm.pose.bones[quadril].head)
        rot.append([arm.pose.bones[n].matrix_basis.to_quaternion() for n in principais])
    desloca = (pos[1] - pos[0]) if len(pos) == 2 else Vector()
    altura = (arm.matrix_world @ arm.pose.bones[quadril].bone.head_local).z if quadril else 1.0
    escala = 1.0 / altura if altura > 0.05 else 1.0  # em "alturas do quadril" (independe da unidade)
    dif = max((math.degrees(2 * math.acos(min(1.0, abs(a.dot(b))))) for a, b in zip(rot[0], rot[1])), default=0.0)
    return {
        "quadros": fim - ini + 1,
        "segundos": round((fim - ini + 1) / FPS, 2),
        "desloca_no_chao": round(math.hypot(desloca.x, desloca.y) * escala, 2),
        "laco": dif < 20.0 and math.hypot(desloca.x, desloca.y) * escala < 0.15,
    }


def catalogar(fontes):
    """fontes: [{"id": "accad", "arquivos": [caminhos], "licenca": ..., "credito": ...}]. Devolve os clipes."""
    clipes = []
    for fonte in fontes:
        for caminho in fonte["arquivos"]:
            try:
                arm, objs, acoes = fc_retarget._importar(caminho)
            except Exception as e:
                clipes.append({"fonte": fonte["id"], "arquivo": caminho, "erro": str(e)})
                continue
            if arm is None:
                _limpar(objs, acoes)
                continue
            quadril = _quadril(arm)
            mapa = fc_retarget.mapa_do_esqueleto([b.name for b in arm.data.bones])
            for a in acoes:
                nome = a.name.split("|")[-1]
                if len(acoes) == 1 and not caminho.lower().endswith((".glb", ".gltf")):
                    nome = os.path.splitext(os.path.basename(caminho))[0]
                try:
                    m = _medir(arm, a, quadril)
                except Exception as e:
                    m = {"erro": str(e)}
                clipes.append({
                    "id": f"{fonte['id']}:{os.path.basename(caminho)}:{a.name.split('|')[-1]}",
                    "nome": nome,
                    "fonte": fonte["id"],
                    "arquivo": caminho,
                    "acao": a.name.split("|")[-1],
                    "etiquetas": etiquetas(nome, fonte["id"]),
                    "ossos_reconhecidos": len(mapa),
                    **m,
                })
            _limpar(objs, acoes)
    return clipes


# ------------------------------------------------------------------ aplicar no personagem

def _achar_acao(acoes, nome):
    por_nome = {a.name.split("|")[-1]: a for a in acoes}
    if not nome or nome == "*" or len(acoes) == 1:
        return por_nome.get(nome) or acoes[0] if acoes else None
    return por_nome.get(nome) or next((x for k, x in por_nome.items() if k.endswith(nome)), None)


def _feicao(S, rt, acao, quadros):
    """Pose de cada quadro da fonte como vetor (para achar o ciclo)."""
    _usar(S, acao)
    cena = bpy.context.scene
    nomes = [s for s, t in rt.pares.items() if re.match(r"^(thigh|calf|foot|upperarm|lowerarm|spine_0\d|pelvis)", t)]
    F = []
    for q in quadros:
        cena.frame_set(int(q), subframe=q - int(q))
        v = []
        for n in nomes:
            qb = S.pose.bones[n].matrix_basis.to_quaternion()
            if qb.w < 0:
                qb = -qb
            v += [qb.w, qb.x, qb.y, qb.z]
        F.append(v)
    return np.array(F)


def achar_ciclo(S, rt, acao, min_s=0.6, max_s=2.6):
    """O trecho [i, j) que fecha em laço melhor (pose de j parecida com a de i, e o movimento também)."""
    ini, fim = (int(round(x)) for x in acao.frame_range)
    quadros = list(range(ini, fim + 1))
    if len(quadros) < int(min_s * FPS) + 3:
        return ini, fim, None
    F = _feicao(S, rt, acao, quadros)
    V = np.gradient(F, axis=0)
    n = len(F)
    melhor = (1e9, ini, fim)
    candidatos = range(0, max(1, min(n - int(min_s * FPS), int(4 * FPS))), 2)
    for i in candidatos:
        js = np.arange(i + int(min_s * FPS), min(n, i + int(max_s * FPS)))
        if not len(js):
            continue
        d = np.linalg.norm(F[js] - F[i], axis=1) + 0.5 * FPS * np.linalg.norm(V[js] - V[i], axis=1)
        k = int(np.argmin(d))
        if d[k] < melhor[0]:
            melhor = (float(d[k]), quadros[i], quadros[int(js[k])])
    return melhor[1], melhor[2] - 1, round(melhor[0], 3)


def _desvios(S, rt, quadros_fonte, no_lugar, laco):
    """Quanto tirar do quadril no chão em cada quadro: o começo da captura vai para o centro (a pessoa
    estava em algum canto da sala de captura); "no lugar" também tira a reta do deslocamento (o balanço
    do quadril fica)."""
    quadril = rt.inverso.get("pelvis")
    if not quadril:
        return None
    cena = bpy.context.scene

    def em(q):
        cena.frame_set(int(q), subframe=q - int(q))
        p = S.matrix_world @ S.pose.bones[quadril].head
        return Vector((p.x, p.y, 0.0))

    pos = [em(q) for q in quadros_fonte]
    base = Vector((rt.pelvis_s0.x, rt.pelvis_s0.y, 0.0))
    inicio = pos[0] - base
    if not no_lugar:
        return [inicio for _ in pos]
    n = len(pos)
    if laco and n > 1:
        # o laço fecha no quadro seguinte ao último
        passo = quadros_fonte[1] - quadros_fonte[0]
        total = em(quadros_fonte[-1] + passo) - pos[0]
        return [inicio + total * (k / n) for k in range(n)]
    total = pos[-1] - pos[0]
    return [inicio + total * (k / max(n - 1, 1)) for k in range(n)]


def quadro_de_referencia(S, alvo, rt, acao, passo=3):
    """O quadro da captura mais parecido com a pose de descanso do alvo (direção dos membros e da
    coluna): vira a referência do retarget no lugar do descanso do arquivo."""
    nomes = [t for t in ("spine_01", "spine_02", "spine_03", "neck_01", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
                         "thigh_l", "thigh_r", "calf_l", "calf_r", "clavicle_l", "clavicle_r") if t in rt.inverso]
    if len(nomes) < 6:
        return None
    mt = alvo.matrix_world
    dir_t = {}
    for t in nomes:
        c = fc_retarget.PRIMARIO.get(t)
        b = alvo.data.bones[t]
        d = (mt @ alvo.data.bones[c].head_local - mt @ b.head_local) if c in alvo.data.bones else (mt @ b.tail_local - mt @ b.head_local)
        dir_t[t] = d.normalized()
    _usar(S, acao)
    ini, fim = (int(round(x)) for x in acao.frame_range)
    cena = bpy.context.scene
    mw = S.matrix_world
    melhor = (1e9, ini)
    esq_t = mt @ alvo.data.bones["thigh_l"].head_local - mt @ alvo.data.bones["thigh_r"].head_local if "thigh_l" in rt.inverso else None
    for q in range(ini, fim + 1, passo):
        cena.frame_set(q)
        # compara de frente: tira o giro do corpo em volta do eixo vertical
        giro = Matrix.Identity(3)
        if esq_t is not None and "thigh_r" in rt.inverso:
            esq = mw @ S.pose.bones[rt.inverso["thigh_l"]].head - mw @ S.pose.bones[rt.inverso["thigh_r"]].head
            a = math.atan2(esq.x * esq_t.y - esq.y * esq_t.x, esq.x * esq_t.x + esq.y * esq_t.y)
            giro = Matrix.Rotation(a, 3, "Z")
        custo = 0.0
        for t in nomes:
            s_ = rt.inverso[t]
            c = fc_retarget.PRIMARIO.get(t)
            pb = S.pose.bones[s_]
            if c in rt.inverso:
                d = mw @ S.pose.bones[rt.inverso[c]].head - mw @ pb.head
            else:
                d = mw @ pb.tail - mw @ pb.head
            if d.length < 1e-6:
                continue
            custo += (giro @ d.normalized()).angle(dir_t[t])
        if custo < melhor[0]:
            melhor = (custo, q)
    return melhor[1]


def virar_para_frente(S, alvo, rt, acao, quadro, ate=None):
    """Gira a captura (em volta do eixo vertical) para o corpo começar olhando para a frente do alvo.
    Com `ate` (ciclo de andar), a frente é a direção em que o quadril anda (a passada fica reta)."""
    if not all(x in rt.inverso for x in ("thigh_l", "thigh_r")):
        return 0.0
    _usar(S, acao)
    cena = bpy.context.scene
    mw = S.matrix_world
    mt = alvo.matrix_world
    esq_t = mt @ alvo.data.bones["thigh_l"].head_local - mt @ alvo.data.bones["thigh_r"].head_local
    cima = Vector((0, 0, 1))
    ft = esq_t.cross(cima)
    fs = None
    if ate is not None and "pelvis" in rt.inverso:
        cena.frame_set(int(quadro))
        p0 = mw @ S.pose.bones[rt.inverso["pelvis"]].head
        cena.frame_set(int(ate))
        p1 = mw @ S.pose.bones[rt.inverso["pelvis"]].head
        anda = p1 - p0
        anda.z = 0
        cena.frame_set(int(quadro))
        esq = mw @ S.pose.bones[rt.inverso["thigh_l"]].head - mw @ S.pose.bones[rt.inverso["thigh_r"]].head
        olha = esq.cross(cima)
        altura = max((mw @ S.pose.bones[rt.inverso["pelvis"]].head).z, 1e-3)
        # anda de verdade e mais ou menos para onde olha (não é andar de lado nem de costas)
        if anda.length > 0.2 * altura and olha.length > 1e-6 and anda.normalized().dot(olha.normalized()) > 0.5:
            fs = anda
    if fs is None:
        cena.frame_set(int(quadro))
        esq = mw @ S.pose.bones[rt.inverso["thigh_l"]].head - mw @ S.pose.bones[rt.inverso["thigh_r"]].head
        fs = esq.cross(cima)
    fs.z = ft.z = 0
    if fs.length < 1e-6 or ft.length < 1e-6:
        return 0.0
    ang = math.atan2(fs.x * ft.y - fs.y * ft.x, fs.dot(ft))
    from mathutils import Matrix

    S.matrix_world = Matrix.Rotation(ang, 4, "Z") @ S.matrix_world
    bpy.context.view_layer.update()
    return math.degrees(ang)


def gravar(rt, acao_fonte, nome, laco, quadros_fonte, no_lugar):
    S, T = rt.S, rt.T
    _usar(S, acao_fonte)
    desvios = _desvios(S, rt, quadros_fonte, no_lugar, laco)
    ad = T.animation_data or T.animation_data_create()
    velha = bpy.data.actions.get(nome)
    if velha:
        bpy.data.actions.remove(velha)
    act = bpy.data.actions.new(nome)
    act.use_fake_user = True
    ad.action = act
    for pb in T.pose.bones:
        pb.rotation_mode = "QUATERNION"
    cena = bpy.context.scene
    _usar(S, acao_fonte)
    for k, q in enumerate(quadros_fonte, start=1):
        cena.frame_set(int(q), subframe=q - int(q))
        rt.desvio = desvios[k - 1] if desvios else None
        bases = rt.quadro()
        for pb in T.pose.bones:
            base = bases.get(pb.name)
            if base is None:
                continue
            loc, rot, _ = base.decompose()
            pb.rotation_quaternion = rot
            pb.keyframe_insert("rotation_quaternion", frame=k, group=pb.name)
            if pb.name == "pelvis":
                pb.location = loc
                pb.keyframe_insert("location", frame=k, group=pb.name)
    rt.desvio = None
    try:
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = len(quadros_fonte)
        act.use_cyclic = laco
    except Exception:
        pass
    act["laco"] = laco
    return act


def aplicar(alvo, pedidos):
    """pedidos: [{"arquivo", "acao" (ou "*"), "como" (nome no jogo), "laco", "inicio", "fim" (quadros da
    fonte), "velocidade", "no_lugar", "ciclo"}]. Devolve (ações criadas, notas)."""
    por_arquivo = {}
    for p in pedidos:
        por_arquivo.setdefault(p["arquivo"], []).append(p)
    criadas, notas = [], []
    for caminho, lista in por_arquivo.items():
        S, novos, acoes = fc_retarget._importar(caminho)
        if S is None:
            notas.append({"arquivo": caminho, "erro": "o arquivo não tem esqueleto"})
            _limpar(novos, acoes)
            continue
        original = S.matrix_world.copy()
        rt = fc_retarget.Retarget(S, alvo)
        if len(rt.pares) < 10:
            notas.append({"arquivo": caminho, "erro": f"só {len(rt.pares)} ossos reconhecidos: esqueleto de nomes desconhecidos"})
        for p in lista:
            a = _achar_acao(acoes, p.get("acao"))
            if a is None:
                notas.append({"arquivo": caminho, "acao": p.get("acao"), "erro": "animação não encontrada no arquivo"})
                continue
            ini, fim = (int(round(x)) for x in a.frame_range)
            nota = {"como": p["como"], "de": os.path.basename(caminho), "acao": a.name.split("|")[-1]}
            # cada clipe começa de frente e no centro
            S.matrix_world = original
            bpy.context.view_layer.update()
            if p.get("virar_para_frente", True):
                giro = virar_para_frente(S, alvo, fc_retarget.Retarget(S, alvo), a, int(p.get("inicio") or ini),
                                         ate=int(p.get("fim") or fim) if (p.get("ciclo") or p.get("laco")) else None)
                if abs(giro) > 1:
                    nota["virado_graus"] = round(giro, 1)
            ref = None
            if not caminho.lower().endswith((".glb", ".gltf")) or p.get("calibrar"):
                ref = quadro_de_referencia(S, alvo, fc_retarget.Retarget(S, alvo), a)
                nota["quadro_de_referencia"] = ref
            rt = fc_retarget.Retarget(S, alvo, ref)
            if p.get("ciclo"):
                ci, cf, erro = achar_ciclo(S, rt, a)
                ini, fim = ci, cf
                nota["ciclo"] = {"inicio": ci, "fim": cf, "diferenca": erro}
            ini = int(p.get("inicio") or ini)
            fim = int(p.get("fim") or fim)
            vel = float(p.get("velocidade") or 1.0)
            n = max(2, int(round((fim - ini) / max(vel, 0.05))) + 1)
            quadros = list(np.linspace(ini, fim, n))
            laco = bool(p["laco"]) if p.get("laco") is not None else bool(p.get("ciclo"))
            no_lugar = bool(p["no_lugar"]) if p.get("no_lugar") is not None else laco
            criadas.append(gravar(rt, a, p["como"], laco, quadros, no_lugar))
            nota.update({"quadros": n, "laco": laco, "no_lugar": no_lugar})
            notas.append(nota)
        _limpar(novos, acoes)
    for pb in alvo.pose.bones:
        pb.location = Vector()
    if alvo.animation_data and criadas:
        alvo.animation_data.action = criadas[0]
    return criadas, notas
