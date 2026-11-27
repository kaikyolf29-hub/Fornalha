# Fornalha: ponto de entrada dos scripts do Blender.
# blender -b --factory-startup --python-exit-code 1 -P fornalha_main.py -- tarefa.json resultado.json
import json
import math
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import fc_comum as c  # noqa: E402

GODOT = lambda v: [round(v[0], 3), round(v[2], 3), round(-v[1], 3)]  # Blender (Z para cima) → Godot (Y para cima)


def estatisticas(objs, arm=None, acoes=()):
    mn, mx = c.caixa_envolvente(objs)
    return {
        "triangulos": c.triangulos(objs),
        "ossos": len(arm.data.bones) if arm else 0,
        "nomes_dos_ossos": [b.name for b in arm.data.bones] if arm else [],
        "animacoes": [{"nome": a.name, "quadros": int(a.frame_range[1] - a.frame_range[0]) + 1, "laco": bool(a.get("laco", False))} for a in acoes],
        "materiais": sorted({m.name for o in objs if o.type == "MESH" for m in o.data.materials if m}),
        "altura_m": round(mx.z - mn.z, 3),
        "largura_m": round(mx.x - mn.x, 3),
        "profundidade_m": round(mx.y - mn.y, 3),
    }


def previas(t, objs, saida, arm=None, acoes=()):
    arquivos = {}
    if not t.get("previa", True):
        return arquivos
    base = os.path.splitext(saida)[0]
    if arm is not None and acoes:
        arm.animation_data.action = acoes[0]
        bpy.context.scene.frame_set(1)
    amostras = int(t.get("amostras", 24))
    arquivos["previa"] = c.renderizar(base + ".previa.png", objs, amostras=amostras)
    if t.get("folha"):
        arquivos["folha"] = c.folha_de_modelo(base + ".folha.png", objs, amostras=max(8, amostras - 6))
    if t.get("video") and arm is not None and acoes:
        escolhidas = [a for a in acoes if a.name in t.get("video_animacoes", ["andar", "atacar"])] or list(acoes)[:2]
        arquivos["video"] = c.video(base + ".video.mp4", objs, escolhidas, arm)
    return arquivos


def acabar_malhas(arm, pecas):
    """Acabamento antes do QA: faces de área zero (invisíveis, mas quebram normal e tangente na engine)
    saem, e o personagem pisa no chão: a sola mais baixa vai para z = 0 subindo o esqueleto (as peças e
    as animações vão juntas). O templário saía com 7 faces degeneradas e a bota 2,7 cm abaixo do chão."""
    import bmesh

    tiradas = 0
    for o in pecas:
        if o.type != "MESH" or not o.data.polygons:
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        zero = [f for f in bm.faces if f.calc_area() < 1e-10]
        if zero:
            bmesh.ops.delete(bm, geom=zero, context="FACES_ONLY")
            bm.to_mesh(o.data)
            o.data.update()
            tiradas += len(zero)
        bm.free()
    pose = arm.data.pose_position
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    zmin = min((min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in pecas if o.type == "MESH" and o.data.vertices), default=0.0)
    subiu = 0.0
    if -0.08 < zmin < -0.002:
        arm.location.z -= zmin
        subiu = -zmin
        bpy.context.view_layer.update()
    arm.data.pose_position = pose
    bpy.context.view_layer.update()
    return {"faces_degeneradas_tiradas": tiradas, "subiu_para_o_chao_cm": round(subiu * 100, 1)}


def movimento_conferido(t, arm, acoes):
    """Conferência e correção automática das animações recém-feitas (bancada de movimento). O resumo
    vai nas estatísticas; o que não deu para corrigir fica listado para a IA trocar o clipe."""
    if not acoes or not t.get("conferir_movimento", True):
        return None
    # a conferência passa por todas as animações e quadros: no fim volta tudo como estava (o QA, as
    # prévias e o retrato que vêm depois medem e mostram a mesma pose de antes)
    cena = bpy.context.scene
    ad = arm.animation_data
    acao0 = ad.action if ad else None
    slot0 = getattr(ad, "action_slot", None) if ad else None
    quadro0 = cena.frame_current
    try:
        _, res, corr, antes = _conferir_e_corrigir(t, None, arm, list(acoes), True)
    except Exception as e:  # a conferência nunca impede o personagem de sair
        print(f"[movimento] conferência falhou: {e}")
        return {"erro": f"{type(e).__name__}: {e}"}
    finally:
        if ad is not None:
            ad.action = acao0
            if slot0 is not None and hasattr(ad, "action_slot"):
                try:
                    ad.action_slot = slot0
                except Exception:
                    pass
        cena.frame_set(quadro0)
    return {
        "aprovado": all(r["aprovado"] for r in res),
        "reprovados": [r["nome"] for r in res if not r["aprovado"]],
        "corrigidas": sorted(corr),
        "problemas_antes": antes,
        "problemas_que_ficaram": {r["nome"]: [p["explicacao"] for p in r["problemas"]] for r in res if not r["aprovado"]},
    }


def tarefa_personagem(t):
    import fc_animacoes
    import fc_personagem

    p = t.get("personagem", {})
    arm, corpo, arma = fc_personagem.criar_personagem(p)
    H = arm.data.bones["Head"].tail_local.z
    acoes = fc_animacoes.aplicar_biblioteca(arm, H, t.get("animacoes"))
    saida = t["saida"]
    objs = [corpo] + ([arma] if arma else [])
    tamanho = c.exportar_glb(saida, [arm, corpo] + ([arma] if arma else []) + [o for o in bpy.data.objects if o.type == "EMPTY"])
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, objs, saida, arm, acoes))
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": estatisticas(objs, arm, acoes)}


def tarefa_criatura(t):
    """Criatura com esqueleto próprio (hoje: dragão), animações procedurais e prévias."""
    import fc_criatura

    p = t.get("criatura", {})
    tipo = p.get("tipo", "dragao")
    if tipo != "dragao":
        raise ValueError(f"criatura desconhecida: {tipo} (por enquanto: dragao)")
    arm, objs, acoes = fc_criatura.criar_dragao(p)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [arm] + objs)
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, objs, saida, arm, acoes))
    r = {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": estatisticas(objs, arm, acoes)}
    r["boca"] = {"osso": "jaw", "eixo_modelo": [1.0, 0.0, 0.0], "graus_aberta": 30}
    r["esqueleto"] = "dragao"
    return r


def tarefa_humano(t):
    """Humano realista a partir dos dados CC0 do MakeHuman, com esqueleto de jogo."""
    import fc_humano

    ficha = t.get("humano", {})
    if t.get("materiais"):
        import fc_pbr

        fc_pbr.definir_pasta(t["materiais"])
    if t.get("ceu"):
        c.definir_ceu(t["ceu"])
    arm, pecas, h = fc_humano.criar_humano(t["makehuman"]["dados"], t["makehuman"]["assets"], ficha)
    acoes = []
    if t.get("animacoes_de"):
        import fc_retarget

        clipes = None
        if ficha.get("zumbi"):
            # zumbi: os mesmos nomes do jogo (a engine troca por velocidade), com o andar arrastado, o
            # balanço parado e o ataque de agarrar/arranhar da biblioteca (Quaternius, CC0)
            clipes = {"parado": ("ual2", "Zombie_Idle_Loop", True), "andar": ("ual2", "Zombie_Walk_Fwd_Loop", True),
                      "atacar": ("ual2", "Zombie_Scratch", False)}
        acoes = fc_retarget.aplicar_biblioteca(arm, t["animacoes_de"], t.get("animacoes"), clipes)
    movimento = movimento_conferido(t, arm, acoes)
    saida = t["saida"]
    acabamento = acabar_malhas(arm, pecas)
    # QA automático (bíblia técnica 9.3): o resultado vai junto, para a janela e o agente verem
    import fc_lookdev

    qa = fc_lookdev.qa([arm] + pecas, arm, corpo=pecas[0] if pecas else None,
                       cabelo=[o for o in pecas if o.name.endswith(("_hair", "_hair_cards")) or "couro_cabeludo" in o.name] or None)
    tamanho = c.exportar_glb(saida, [arm] + pecas, animacoes=bool(acoes))
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, pecas, saida, arm if acoes else None, acoes))
    if t.get("retrato", True):
        # o rosto na pose em que o personagem está (a animação parada mexe a cabeça)
        # retrato na pose de descanso: cabeça reta, olhando para a frente
        pose = arm.data.pose_position
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        rosto = arm.matrix_world @ (arm.data.bones["head"].head_local + Vector((0, -0.01, 0.075)))
        arquivos["retrato"] = c.retrato(os.path.splitext(saida)[0] + ".retrato.png", rosto, amostras=int(t.get("amostras", 48)))
        arm.data.pose_position = pose
    st = estatisticas(pecas, arm, acoes)
    st["pecas"] = [o.name for o in pecas]
    st["qa"] = qa
    st["movimento"] = movimento
    st["acabamento"] = acabamento
    cab = next((o for o in pecas if "medidas_cabelo" in o.keys()), None)
    if cab is not None:
        st["cabelo"] = cab["medidas_cabelo"].to_dict()
    barba = next((o for o in pecas if "medidas_barba" in o.keys()), None)
    if barba is not None:
        st["barba"] = barba["medidas_barba"].to_dict()
    r = {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}
    if arm is not None and "jaw" in arm.data.bones:
        # a engine (Erethea/Godot) abre a boca pela curva da fala: girar o osso em torno do eixo X do
        # modelo, no sentido positivo, até ~20° (medido: o queixo desce 1,5 cm e os dentes de baixo vão junto)
        r["boca"] = {"osso": "jaw", "eixo_modelo": [1.0, 0.0, 0.0], "graus_aberta": 20}
    if arm is not None and all(n in arm.data.bones for n in ("eye_l", "eye_r", "eyelid_upper_l", "eyelid_upper_r")):
        # olhos e pálpebras (do rig padrão do MakeHuman). Eixos no espaço do modelo do glTF (Y para cima):
        # os olhos giram em Y para os lados e em X para cima/baixo; a pálpebra de cima fecha girando +30° em
        # X e a de baixo sobe girando −8° (medido no render: o olho fecha inteiro, os cílios acompanham)
        r["olhos"] = {"ossos": ["eye_l", "eye_r"], "eixo_lados_modelo": [0.0, 1.0, 0.0], "eixo_cima_modelo": [1.0, 0.0, 0.0],
                      "graus_max_lados": 25, "graus_max_cima": 15}
        r["palpebras"] = {"cima": ["eyelid_upper_l", "eyelid_upper_r"], "baixo": ["eyelid_lower_l", "eyelid_lower_r"],
                          "eixo_modelo": [1.0, 0.0, 0.0], "graus_fechar_cima": 30, "graus_fechar_baixo": -8}
    return r


def tarefa_arma(t):
    import fc_armas

    p = t.get("arma", {})
    avisos = []
    if p.get("pecas"):
        import fc_pecas

        obj, avisos = fc_pecas.montar(p)
    else:
        obj = fc_armas.criar_arma(p)
    encaixe = bpy.data.objects.new("encaixe_mao", None)
    bpy.context.scene.collection.objects.link(encaixe)
    col = fc_armas.colisao_simples(obj)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [obj, encaixe, col], animacoes=False)
    arquivos = {"modelo": saida}
    col.hide_set(True)
    arquivos.update(previas(t, [obj], saida))
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": estatisticas([obj]), "avisos": avisos}


def tarefa_objeto(t):
    import fc_armas

    p = t.get("objeto", {})
    avisos = []
    if p.get("pecas"):
        import fc_pecas

        obj, avisos = fc_pecas.montar({**p, "no_chao": p.get("no_chao", True)})
    else:
        obj = fc_armas.criar_objeto(p)
    col = fc_armas.colisao_simples(obj)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [obj, col], animacoes=False)
    arquivos = {"modelo": saida}
    col.hide_set(True)
    arquivos.update(previas(t, [obj], saida))
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": estatisticas([obj]), "avisos": avisos}


def tarefa_mundo(t):
    import fc_mundo

    objs, marcadores, areas = fc_mundo.criar_mundo(t.get("mundo", {}))
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, objs + marcadores, animacoes=False)
    arquivos = {"modelo": saida}
    if t.get("previa", True):
        base = os.path.splitext(saida)[0]
        visiveis = [o for o in objs if o.type == "MESH"]
        arquivos["previa"] = c.renderizar(base + ".previa.png", visiveis, direcao=(-0.5, -1.0, 0.8), largura=960, altura=640, amostras=int(t.get("amostras", 16)), chao=False)
        cam = bpy.context.scene.camera
        mn, mx = c.caixa_envolvente(visiveis)
        c.enquadrar(cam, mn, mx, (0, -0.001, 1), margem=1.02, orto=True)
        bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 800
        bpy.context.scene.render.filepath = base + ".mapa.png"
        bpy.ops.render.render(write_still=True)
        arquivos["mapa"] = base + ".mapa.png"
        # vista da rua: na altura dos olhos, entrando na primeira área
        cam.data.type = "PERSP"
        cam.data.lens = 28
        cam.location = Vector((2.5, -15.0, 1.75))
        alvo = Vector((0.0, 4.0, 2.2))
        cam.rotation_euler = (alvo - cam.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = 1280, 720
        bpy.context.scene.cycles.samples = max(24, int(t.get("amostras", 16)))
        bpy.context.scene.render.filepath = base + ".rua.png"
        mundo = bpy.context.scene.world
        if mundo and mundo.node_tree and mundo.node_tree.nodes.get("ceu_hdri"):
            # na rua o céu aparece (não o fundo escuro de estúdio)
            mix = next((n for n in mundo.node_tree.nodes if n.type == "MIX_SHADER"), None)
            if mix:
                mix.inputs[0].default_value = 0.0
                for l in list(mundo.node_tree.links):
                    if l.to_node == mix and l.to_socket == mix.inputs[0]:
                        mundo.node_tree.links.remove(l)
        bpy.ops.render.render(write_still=True)
        arquivos["rua"] = base + ".rua.png"
    info = {
        "areas": [dict(a, centro=GODOT(a["centro"])) for a in areas],
        "spawn_jogador": GODOT(bpy.data.objects["spawn_jogador"].location),
        "spawn_inimigos": [GODOT(m.location) for m in marcadores if m.name.startswith("spawn_inimigo")],
    }
    caminho_info = os.path.splitext(saida)[0] + ".info.json"
    with open(caminho_info, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    arquivos["info"] = caminho_info
    st = estatisticas([o for o in objs if o.type == "MESH"])
    st["areas"] = len(areas)
    st["objetos"] = len(objs)
    st["colisoes"] = sum(1 for o in objs if o.name.endswith("-col"))
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st, "info": info}


def tarefa_comparar(t):
    import fc_comparar

    return fc_comparar.tarefa(t)


def tarefa_mapa(t):
    import fc_mapa

    return fc_mapa.tarefa(t)


def _importar(caminho):
    antes = set(bpy.data.objects)
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=caminho)
        c.tirar_ajudantes_do_gltf()
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=caminho)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=caminho)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=caminho)
    else:
        raise ValueError(f"formato não suportado: {ext}")
    return [o for o in bpy.data.objects if o not in antes]


def _juntar_malhas(objs, nome):
    # colisões exportadas pela própria Fornalha (-col/-colonly) não entram na malha visível
    colisoes = [o for o in objs if o.type == "MESH" and o.name.lower().split(".")[0].endswith(("-col", "-colonly"))]
    for o in colisoes:
        bpy.data.objects.remove(o, do_unlink=True)
    objs = [o for o in objs if o not in colisoes]
    malhas = [o for o in objs if o.type == "MESH"]
    if not malhas:
        raise ValueError("o arquivo não tem malha")
    outros = [o.name for o in objs if o.type != "MESH"]
    for o in bpy.context.scene.objects:
        o.select_set(o in malhas)
    bpy.context.view_layer.objects.active = malhas[0]
    if len(malhas) > 1:
        bpy.ops.object.join()
    m = bpy.context.view_layer.objects.active
    m.name = nome
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for n in outros:
        o = bpy.data.objects.get(n)
        if o is not None and o != m:
            bpy.data.objects.remove(o, do_unlink=True)
    return m


def posicionar(m, t):
    """Em pé (Z para cima), virado para -Y, na altura pedida e com o pivô nos pés."""
    if str(t.get("cima", "Z")).upper() == "Y":
        m.rotation_euler.x = math.radians(90)
        bpy.ops.object.transform_apply(rotation=True)
    if t.get("girar_graus"):
        m.rotation_euler.z = math.radians(float(t["girar_graus"]))
        bpy.ops.object.transform_apply(rotation=True)
    mn, mx = c.caixa_envolvente([m])
    altura = float(t.get("altura_m") or 0)
    if altura > 0 and (mx.z - mn.z) > 1e-6:
        f = altura / (mx.z - mn.z)
        m.scale = (f, f, f)
        bpy.ops.object.transform_apply(scale=True)
        mn, mx = c.caixa_envolvente([m])
    # pivô no centro dos pés (z = 0)
    m.location -= Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
    bpy.ops.object.transform_apply(location=True)


def limpar_malha(m, t):
    """Limpeza do plano: escala real, pivô nos pés, decimar, UV, normais."""
    for o in bpy.context.scene.objects:
        o.select_set(o == m)
    bpy.context.view_layer.objects.active = m
    posicionar(m, t)
    tris_antes = c.triangulos([m])
    alvo = int(t.get("triangulos_max") or 0)
    if alvo and tris_antes > alvo:
        d = m.modifiers.new("decimar", "DECIMATE")
        d.ratio = max(0.01, alvo / tris_antes)
        bpy.ops.object.modifier_apply(modifier=d.name)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    if not m.data.uv_layers:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"triangulos_antes": tris_antes, "triangulos_depois": c.triangulos([m])}


def tarefa_limpar(t):
    objs = _importar(t["entrada"])
    m = _juntar_malhas(objs, t.get("nome", "modelo"))
    info = limpar_malha(m, t)
    col = None
    if t.get("colisao", True):
        import fc_armas

        col = fc_armas.colisao_simples(m)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [m] + ([col] if col else []), animacoes=False)
    arquivos = {"modelo": saida}
    if col:
        col.hide_set(True)
    arquivos.update(previas(t, [m], saida))
    st = estatisticas([m])
    st.update(info)
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}


def limpar_manchas_da_ia(m, res=1024):
    """A IA de 3D só vê a frente no conceito e inventa as costas: no pano claro de trás (capa, sobreveste)
    aparecem manchas escuras soltas, como queimado. Na metade de trás da malha, onde o pano em volta é
    claro e sem cor, o que é bem mais escuro que a vizinhança vira a cor do pano em volta (com um pouco do
    desenho original). A frente (cruz, emblema) não é tocada. Devolve quantos texels mudaram."""
    import numpy as np

    import fc_pele

    img = None
    for mat in m.data.materials:
        if mat is None or not mat.use_nodes:
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        for l_ in mat.node_tree.links:
            if l_.to_node == bsdf and l_.to_socket.name == "Base Color" and l_.from_node.type == "TEX_IMAGE":
                img = l_.from_node.image
                no = l_.from_node
    if img is None or not m.data.uv_layers:
        return 0
    W, H = img.size
    r = min(res, W)
    px = fc_pele._pixels(img)  # de cima para baixo, 0..1 (como no arquivo)
    pos, mask, _ = fc_pele.rasterizar(m, r)
    mw = np.array(m.matrix_world, dtype=np.float32)
    pw = pos @ mw[:3, :3].T + mw[:3, 3]
    if not mask.any():
        return 0
    ys = pw[..., 1][mask]
    alto = float(np.ptp(pw[..., 2][mask])) or 1.0
    costas = mask & (pw[..., 1] > float(np.median(ys)) + 0.03 * alto)  # no Blender a frente é -Y
    pq = fc_pele._redimensionar(px, r)
    L = pq @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    if not costas.any():
        return 0
    claro = costas & (L > np.percentile(L[costas], 35))
    raio = max(4, r // 48)
    w = fc_pele.borrar(claro.astype(np.float32), raio)
    ref = np.stack([fc_pele.borrar(pq[..., k] * claro, raio) for k in range(3)], -1) / np.maximum(w[..., None], 1e-4)
    refL = ref @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    sat = ref.max(-1) - ref.min(-1)
    mancha = costas & (w > 0.15) & (refL > 0.55) & (sat < 0.12) & (L < refL - 0.18)
    mancha = fc_pele.borrar(mancha.astype(np.float32), 2) > 0.2
    n = int(mancha.sum())
    if n < 30:
        return 0
    grande = fc_pele._redimensionar(mancha.astype(np.float32)[..., None], W)[..., 0] > 0.35 if W != r else mancha
    ref_g = fc_pele._redimensionar(ref, W) if W != r else ref
    Lg = px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    refLg = ref_g @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    # guarda a trama do pano (variação fina) e tira o escuro da mancha
    detalhe = np.clip(Lg - fc_pele.borrar(Lg, 3), -0.08, 0.08)[..., None]
    novo = px.copy()
    novo[grande] = np.clip(ref_g[grande] * (1.0 + detalhe[grande] / np.maximum(refLg[grande][:, None], 0.2)), 0, 1)
    rgba = np.ones((H, W, 4), dtype=np.float32)
    rgba[..., :3] = novo
    nova = bpy.data.images.new(f"{img.name}_limpa", W, H, alpha=True)
    nova.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
    nova.pack()
    no.image = nova
    return n


def corrigir_metal_da_ia(m, limite=0.85):
    """O 3D pela IA às vezes devolve o mapa de metal todo em 1 (o pelo da fera saía prata). Mede o metal
    nos pontos da textura que a malha usa; se quase tudo é metal, o mapa é descartado (material não
    metálico). Armadura de verdade tem metal e pano misturados e passa. Devolve a média medida (ou None)."""
    import numpy as np

    me = m.data
    if not me.uv_layers or not me.materials:
        return None
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    media = None
    for mat in me.materials:
        if not mat or not mat.use_nodes:
            continue
        b = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is None or not b.inputs["Metallic"].is_linked:
            continue
        lig = b.inputs["Metallic"].links[0]
        no, canal = lig.from_node, lig.from_socket.name
        img_no = no
        while img_no is not None and img_no.type != "TEX_IMAGE":
            ent = next((i for i in img_no.inputs if i.is_linked), None)
            img_no = ent.links[0].from_node if ent else None
        if img_no is None or img_no.image is None:
            continue
        img = img_no.image
        w, h = img.size
        if w * h == 0:
            continue
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)
        k = {"Red": 0, "Green": 1, "Blue": 2}.get(canal, 0) if no.type in ("SEPARATE_COLOR", "SEPRGB", "SEPARATE_RGB") else 0
        amostra = uv[:: max(1, len(uv) // 50000)]
        xs = np.clip((amostra[:, 0] % 1.0) * w, 0, w - 1).astype(int)
        ys = np.clip((amostra[:, 1] % 1.0) * h, 0, h - 1).astype(int)
        media = float(px[ys, xs, k].mean())
        if media > limite:
            mat.node_tree.links.remove(lig)
            b.inputs["Metallic"].default_value = 0.0
            print(f"[rig] mapa de metal da IA descartado em {mat.name} (média {media:.2f}: tudo metal)")
    return None if media is None else round(media, 3)


def cor_pelo_conceito(m, caminho, forca=0.75):
    """A textura da malha da IA sai mais clara que a imagem da pessoa (as pontas do pelo, que no conceito
    são reflexo de luz, viram cor clara: a fera escura saía cinza-clara). Casa a distribuição de
    luminância da textura com a do bicho no conceito (quantil por quantil, mantendo o matiz), com força
    parcial: a luz pintada no conceito não vira cor. O fundo do conceito sai por linha (estúdio em
    degradê). Devolve as medianas antes e depois, ou None."""
    import numpy as np

    me = m.data
    if not os.path.isfile(caminho) or not me.uv_layers or not me.materials:
        return None
    try:
        ic = bpy.data.images.load(caminho, check_existing=True)
    except Exception as e:
        print(f"[rig] conceito não abriu: {e}")
        return None
    w, h = ic.size
    pc = np.empty(w * h * 4, dtype=np.float32)
    ic.pixels.foreach_get(pc)
    bpy.data.images.remove(ic)
    pc = pc.reshape(h, w, 4)[..., :3]
    lado = max(4, w // 64)
    fundo = np.median(np.concatenate([pc[:, :lado], pc[:, -lado:]], axis=1), axis=1)
    bicho = pc[np.abs(pc - fundo[:, None, :]).sum(-1) > 0.15]
    if len(bicho) < 1000:
        return None
    pesos = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    qs = np.linspace(0.0, 1.0, 101)
    cq = np.quantile(bicho @ pesos, qs)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[:: max(1, len(me.loops) // 60000)]
    feito = None
    for mat in me.materials:
        if not mat or not mat.use_nodes:
            continue
        b = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is None or not b.inputs["Base Color"].is_linked:
            continue
        no = b.inputs["Base Color"].links[0].from_node
        if no.type != "TEX_IMAGE" or no.image is None:
            continue
        img = no.image
        tw, th = img.size
        px = np.empty(tw * th * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(th, tw, 4)
        xs = np.clip((uv[:, 0] % 1.0) * tw, 0, tw - 1).astype(int)
        ys = np.clip((uv[:, 1] % 1.0) * th, 0, th - 1).astype(int)
        tq = np.quantile(px[ys, xs, :3] @ pesos, qs)
        # já parecida (o cavaleiro: 0,52 contra 0,50): não mexe; a fera estava 0,49 contra 0,22
        if abs(float(tq[50] - cq[50])) < 0.08:
            continue
        lum = px[..., :3] @ pesos
        alvo = np.interp(lum, np.maximum.accumulate(tq), cq)
        razao = (alvo + 1e-3) / (lum + 1e-3)
        novo = px[..., :3] * razao[..., None]
        # cores fortes (cinto vermelho, olhos âmbar) ficam como estão
        mx, mn = px[..., :3].max(-1), px[..., :3].min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-3)
        f = forca * (1.0 - 0.85 * np.clip((sat - 0.25) / 0.35, 0.0, 1.0))
        px[..., :3] = np.clip(px[..., :3] + f[..., None] * (novo - px[..., :3]), 0.0, 1.0)
        img.pixels.foreach_set(px.ravel())
        img.update()
        try:
            img.pack()
        except Exception:
            pass
        depois = float(np.median(px[ys, xs, :3] @ pesos))
        feito = {"mediana_antes": round(float(tq[50]), 3), "mediana_conceito": round(float(cq[50]), 3),
                 "mediana_depois": round(depois, 3)}
        print(f"[rig] cor casada com o conceito em {mat.name}: mediana {tq[50]:.2f} → {depois:.2f} (conceito {cq[50]:.2f})")
    return feito


def tarefa_rig(t):
    """Malha de fora (TRELLIS.2, Hunyuan3D, feita à mão) ganha o esqueleto padrão, pesos e animações."""
    import fc_animacoes
    import fc_personagem

    objs = _importar(t["entrada"])
    m = _juntar_malhas(objs, t.get("nome", "personagem"))
    # malha de jogo: a alta guarda o relevo para o mapa de normais da leve (só quando decima de verdade)
    alta = None
    alvo = int(t.get("triangulos_max") or 0)
    if t.get("esqueleto") in ("jogo", "dragao", "auto", "criatura") and t.get("normal_da_alta", True) and alvo and c.triangulos([m]) > 1.25 * alvo:
        alta = m.copy()
        alta.data = m.data.copy()
        bpy.context.scene.collection.objects.link(alta)
    info = limpar_malha(m, t)
    metal = corrigir_metal_da_ia(m)
    if metal is not None:
        info["metal_da_ia"] = metal
    try:
        manchas = limpar_manchas_da_ia(m)
        if manchas:
            info["manchas_limpas_nas_costas"] = manchas
    except Exception as e:  # sem a limpeza, a textura segue como veio
        print(f"[rig] limpeza das manchas não rodou: {e}")
    if t.get("conceito"):
        cor = cor_pelo_conceito(m, t["conceito"])
        if cor:
            info["cor_pelo_conceito"] = cor
    if alta is not None:
        import fc_placa

        try:
            img = fc_placa.assar_normal(alta, m, int(t.get("normal_px") or 2048), f"{t.get('nome', 'personagem')}_normal")
            info["normal_da_alta"] = bool(img)
        except Exception as e:  # sem o mapa, segue com a malha leve como está
            print(f"[rig] mapa de normais não assou: {e}")
            info["normal_da_alta"] = False
        bpy.data.objects.remove(alta, do_unlink=True)
    esq = t.get("esqueleto")
    if esq == "auto":
        # qualquer corpo: humanoide (duas patas, de pé), alado (asas grandes) ou criatura de patas
        esq = _tipo_de_corpo(m)
        info["corpo_detectado"] = esq
    if esq == "jogo":
        return _rig_de_jogo(t, m, info)
    if esq == "dragao":
        return _rig_de_dragao(t, m, info)
    if esq == "criatura":
        return _rig_de_criatura(t, m, info)
    mn, mx = c.caixa_envolvente([m])
    H = mx.z - mn.z
    porte = max(0.7, min(1.4, ((mx.x - mn.x) / H) / 0.9)) if H > 0 else 1.0
    arm = fc_personagem.criar_armadura(t.get("nome", "personagem"), H, porte)
    for o in bpy.context.scene.objects:
        o.select_set(o in (m, arm))
    bpy.context.view_layer.objects.active = arm
    metodo = "automatico"
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception:
        metodo = "envelope"
        bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
    if not any(len(g.name) for g in m.vertex_groups):
        metodo = "envelope"
        bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
    acoes = fc_animacoes.aplicar_biblioteca(arm, H, t.get("animacoes"))
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [arm, m])
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, [m], saida, arm, acoes))
    st = estatisticas([m], arm, acoes)
    st.update(info)
    st["pesos"] = metodo
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}


def _rig_de_jogo(t, m, info):
    """Malha humanoide da IA com o esqueleto de jogo (nomes Unreal) e a captura de movimento CC0 — o
    mesmo movimento do humano da Fornalha."""
    import fc_retarget
    import fc_rig_ia

    nome = t.get("nome", "personagem")
    info_partes = {}
    if t.get("cabeca"):
        # por partes: a cabeça feita em close entra no lugar da cabeça do corpo antes do esqueleto
        import fc_partes

        fc_rig_ia.normalizar(m, float(t.get("altura_m") or 1.8))
        info_partes = fc_partes.trocar_cabeca(m, t["cabeca"])
    if t.get("makehuman") and t.get("molde", True):
        # o mesmo esqueleto (com dedos) e pesos do humano da Fornalha, passados de um corpo-molde
        # encaixado na malha: o movimento e a pegada da arma ficam iguais aos do humano
        import fc_molde

        arm, info_rig = fc_molde.rigar(m, nome, float(t.get("altura_m") or 1.8), t["makehuman"])
    else:
        arm, info_rig = fc_rig_ia.rigar(m, nome, float(t.get("altura_m") or 1.8))
    info_rig.update(info_partes)
    import fc_armas_pbr

    clipes = {}
    if t.get("escudo"):
        clipes.update(fc_armas_pbr.CLIPES_DA_ARMA["escudo"])
    acoes = fc_retarget.aplicar_biblioteca(arm, t["animacoes_de"], t.get("animacoes"), clipes) if t.get("animacoes_de") else []
    # antes da saia: a saia é assada sobre as pernas já corrigidas
    info_rig["movimento"] = movimento_conferido(t, arm, acoes)
    if acoes and info_rig.get("osso_da_saia"):
        import fc_molde

        info_rig["acoes_com_saia"] = fc_molde.assar_saia(arm, acoes)
    objs = [m]
    arma = t.get("arma")
    if arma and arma != "nenhuma":
        import fc_armas_pbr

        if arma == "espada":
            o = fc_armas_pbr.espada_longa(nome, t.get("cores_arma"))
        else:
            import fc_armas

            o = fc_armas.criar_arma({"tipo": arma, "id": f"{nome}_{arma}", "escala": 1.0})
        fc_armas_pbr.prender_na_mao(o, arm, "r")
        if acoes and "thumb_01_r" not in arm.data.bones:
            # sem dedos no esqueleto, o giro da arma vem da captura (com dedos, é o do humano)
            info_rig["giro_da_arma_graus"] = fc_armas_pbr.acertar_giro(o, arm, acoes, "r")
        objs.append(o)
    if t.get("escudo"):
        import fc_armas_pbr

        e = fc_armas_pbr.escudo_pipa(nome)
        fc_armas_pbr.prender_na_mao(e, arm, "l", escudo=True)
        objs.append(e)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [arm] + objs, animacoes=bool(acoes))
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, objs, saida, arm if acoes else None, acoes))
    st = estatisticas(objs, arm, acoes)
    st.update(info)
    st.update(info_rig)
    st["pecas"] = [o.name for o in objs]
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}


def _tipo_de_corpo(m):
    """'jogo' (humanoide de pé), 'dragao' (asas grandes) ou 'criatura' (patas), medido na malha."""
    import numpy as np

    import fc_rig_generico

    co = np.array([(m.matrix_world @ v.co)[:] for v in m.data.vertices])
    mn, mx = co.min(0), co.max(0)
    W, L, H = (mx - mn).tolist()
    cx = (mn[0] + mx[0]) / 2
    z = co[:, 2] - mn[2]
    asas = float(np.mean((np.abs(co[:, 0] - cx) > 0.25 * W) & (z > 0.35 * H)))
    pes = fc_rig_generico.contar_pes(co)
    if pes == 2 and H > 1.15 * L and asas < 0.2:
        return "jogo"
    if asas > 0.2 and W > 0.9 * L:
        return "dragao"
    return "criatura"


def _rig_de_criatura(t, m, info):
    """Criatura de patas (qualquer número) com o esqueleto medido e as animações procedurais."""
    import fc_rig_generico

    nome = t.get("nome", "criatura")
    arm, acoes, info_rig = fc_rig_generico.rigar(m, nome, float(t.get("altura_m") or 2.0))
    pedidas = t.get("animacoes")
    if pedidas:
        fora = [a for a in acoes if a.name not in pedidas]
        acoes = [a for a in acoes if a.name in pedidas]
        arm.animation_data.action = acoes[0] if acoes else None
        for a in fora:
            bpy.data.actions.remove(a)
    info_rig["movimento"] = movimento_conferido(t, arm, acoes)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [arm, m], animacoes=bool(acoes))
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, [m], saida, arm if acoes else None, acoes))
    st = estatisticas([m], arm, acoes)
    st.update(info)
    st.update(info_rig)
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}


def _rig_de_dragao(t, m, info):
    """Malha de dragão da IA com o esqueleto e as animações do dragão da Fornalha (asas, pescoço, cauda)."""
    import fc_rig_criatura

    nome = t.get("nome", "dragao")
    arm, acoes, info_rig = fc_rig_criatura.rigar(m, nome, float(t.get("altura_m") or 5.0))
    pedidas = t.get("animacoes")
    if pedidas:
        fora = [a for a in acoes if a.name not in pedidas]
        acoes = [a for a in acoes if a.name in pedidas]
        arm.animation_data.action = acoes[0] if acoes else None
        for a in fora:
            bpy.data.actions.remove(a)
    info_rig["movimento"] = movimento_conferido(t, arm, acoes)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [arm, m], animacoes=bool(acoes))
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, [m], saida, arm if acoes else None, acoes))
    st = estatisticas([m], arm, acoes)
    st.update(info)
    st.update(info_rig)
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}


def tarefa_assar(t):
    """Malha alta com cores por vértice (TRELLIS.2) → malha leve com UV e textura assada no Blender."""
    import fc_placa

    nome = t.get("nome", "modelo")
    alta = _juntar_malhas(_importar(t["entrada"]), nome + "_alta")
    fc_placa.material_das_cores(alta)
    posicionar(alta, t)
    baixa = alta.copy()
    baixa.data = alta.data.copy()
    baixa.name = nome
    bpy.context.scene.collection.objects.link(baixa)
    for o in bpy.context.scene.objects:
        o.select_set(o == baixa)
    bpy.context.view_layer.objects.active = baixa
    for a in list(baixa.data.uv_layers):
        baixa.data.uv_layers.remove(a)
    info = limpar_malha(baixa, {"triangulos_max": t.get("triangulos_max") or 12000})
    img = fc_placa.assar_textura(alta, baixa, int(t.get("textura_px") or 1024), nome + "_textura")
    st_textura = {"textura_px": img.size[0], "cobertura_da_textura": fc_placa.cobertura(img), "cor_media": fc_placa.cor_media(img)}
    while len(baixa.data.color_attributes):
        baixa.data.color_attributes.remove(baixa.data.color_attributes[0])
    tris_alta = c.triangulos([alta])
    bpy.data.objects.remove(alta, do_unlink=True)
    objs = [baixa]
    col = None
    if t.get("colisao", False):
        import fc_armas

        col = fc_armas.colisao_simples(baixa)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, objs + ([col] if col else []), animacoes=False)
    if col:
        col.hide_set(True)
    arquivos = {"modelo": saida}
    arquivos.update(previas(t, objs, saida))
    st = estatisticas(objs)
    st.update(info)
    st.update(st_textura)
    st["triangulos_da_malha_alta"] = tris_alta
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": st}


def tarefa_movimento(t):
    """Movimento SMPL (HY-Motion) vira animação do esqueleto padrão; as outras animações continuam."""
    import json as _json

    import fc_placa

    objs = _importar(t["entrada"])
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("o modelo não tem esqueleto: use create_skeleton antes")
    ossos = {b.name for b in arm.data.bones}
    jogo = {"pelvis", "spine_01", "head", "upperarm_l", "upperarm_r", "thigh_l", "thigh_r"} <= ossos
    faltando = {"Hips", "Spine", "Chest", "Head", "LeftUpperArm", "RightUpperArm", "LeftUpperLeg", "RightUpperLeg"} - ossos
    if faltando and not jogo:
        raise ValueError(f"o esqueleto não é o padrão da Fornalha nem o de jogo (faltam {sorted(faltando)})")
    fc_placa.guardar_acoes(arm)
    with open(t["movimento"], encoding="utf-8") as f:
        mov = _json.load(f)
    nome = t.get("nome_animacao") or "movimento"
    laco, no_lugar = bool(t.get("laco", False)), bool(t.get("no_lugar", True))
    if jogo:
        act, quadros = fc_placa.movimento_por_retarget(arm, mov, nome, laco, no_lugar)
        nomes = {"LeftHand": "hand_l", "RightHand": "hand_r", "LeftFoot": "foot_l", "RightFoot": "foot_r", "Head": "head"}
    else:
        act, quadros, _ = fc_placa.aplicar_movimento(arm, mov, nome, laco, no_lugar)
        nomes = {k: k for k in ("LeftHand", "RightHand", "LeftFoot", "RightFoot", "Head")}
    conferir = {}
    for chave, osso in nomes.items():
        conferir[chave] = {"inicio": fc_placa.posicao_do_osso(arm, osso, 1, act), "fim": fc_placa.posicao_do_osso(arm, osso, quadros, act)}
    arm.animation_data.action = act
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, objs)
    malhas = [o for o in objs if o.type == "MESH"]
    acoes = [a for a in bpy.data.actions if a.use_fake_user]
    st = estatisticas(malhas, arm, acoes)
    st["quadros_novos"] = quadros
    st["posicoes"] = conferir
    return {"arquivos": {"modelo": saida}, "tamanho_bytes": tamanho, "estatisticas": st}


def tarefa_retarget(t):
    """Copia as animações de um personagem com o esqueleto padrão para outro."""
    origem = _importar(t["origem"])
    acoes_origem = list(bpy.data.actions)
    alvo = _importar(t["entrada"])
    arm = next((o for o in alvo if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("o personagem de destino não tem esqueleto")
    for o in origem:
        bpy.data.objects.remove(o, do_unlink=True)
    nomes_alvo = {b.name for b in arm.data.bones}
    copiadas = []
    quero = set(t.get("animacoes") or [])
    for a in acoes_origem:
        nome = a.name.split("|")[-1]
        if quero and nome not in quero:
            continue
        a.name = nome
        a.use_fake_user = True
        copiadas.append(a)
    ad = arm.animation_data or arm.animation_data_create()
    if copiadas:
        ad.action = copiadas[0]
    malhas = [o for o in alvo if o.type == "MESH"]
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, alvo)
    return {"arquivos": {"modelo": saida}, "tamanho_bytes": tamanho, "estatisticas": estatisticas(malhas, arm, copiadas), "ossos_iguais": len(nomes_alvo)}


def tarefa_animar(t):
    """Personagem com o esqueleto padrão ganha (de novo) as animações da biblioteca."""
    import fc_animacoes

    objs = _importar(t["entrada"])
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("o modelo não tem esqueleto: use create_skeleton antes")
    ossos = {b.name for b in arm.data.bones}
    if {"pelvis", "spine_01", "head", "upperarm_l", "thigh_l"} <= ossos:
        # esqueleto de jogo (humano realista): animações de captura do pacote
        if not t.get("animacoes_de"):
            raise ValueError("este personagem usa as animações de captura: baixe o pacote de animações (Máquina → Pacotes)")
        import fc_retarget

        import fc_placa

        fc_placa.guardar_acoes(arm)
        acoes = fc_retarget.aplicar_biblioteca(arm, t["animacoes_de"], t.get("animacoes"))
        saida = t["saida"]
        tamanho = c.exportar_glb(saida, objs)
        malhas = [o for o in objs if o.type == "MESH"]
        todas = [a for a in bpy.data.actions if a.use_fake_user]
        return {"arquivos": {"modelo": saida}, "tamanho_bytes": tamanho, "estatisticas": estatisticas(malhas, arm, todas), "novas": [a.name for a in acoes]}
    faltando = {"Hips", "Spine", "Chest", "Head", "LeftUpperArm", "RightUpperArm", "LeftUpperLeg", "RightUpperLeg"} - ossos
    if faltando:
        raise ValueError(f"o esqueleto não é o padrão da Fornalha (faltam {sorted(faltando)})")
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    H = arm.data.bones["Head"].tail_local.z * arm.matrix_world.to_scale().z
    acoes = fc_animacoes.aplicar_biblioteca(arm, H, t.get("animacoes"))
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, objs)
    malhas = [o for o in objs if o.type == "MESH"]
    return {"arquivos": {"modelo": saida}, "tamanho_bytes": tamanho, "estatisticas": estatisticas(malhas, arm, acoes)}


def _acoes_do_glb(objs, arm):
    """As animações que vieram no glb (o importador do glTF guarda cada uma como ação)."""
    acoes = [a for a in bpy.data.actions if a.users or a.use_fake_user]
    # glTF chama "<animação>" ou "<objeto>|<animação>": fica o nome do jogo
    for a in acoes:
        if "|" in a.name:
            a.name = a.name.split("|")[-1]
    return sorted(acoes, key=lambda a: a.name)


def tarefa_conferir(t):
    """Conferência do movimento: mede cada animação e reprova o que fica feio no jogo."""
    import fc_conferir

    objs = _importar(t["entrada"])
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("o modelo não tem esqueleto: monte o esqueleto antes")
    acoes = _acoes_do_glb(objs, arm)
    quero = set(t.get("animacoes") or [])
    if quero:
        acoes = [a for a in acoes if a.name in quero]
    if not acoes:
        raise ValueError("o modelo não tem animações para conferir")
    conf, res, correcoes, antes = _conferir_e_corrigir(t, objs, arm, acoes, bool(t.get("corrigir")))
    if correcoes:
        for a in bpy.data.actions:
            a.use_fake_user = True
        c.exportar_glb(t.get("saida") or t["entrada"], objs)
    else:
        correcoes = None
    arquivos = {}
    imagens = t.get("imagens", "reprovados")
    if imagens != "nenhuma":
        base = os.path.splitext(t.get("saida") or t["entrada"])[0]
        f = fc_conferir.folha(base + ".conferencia.png", conf, res, acoes, todos=imagens == "todas")
        if f:
            arquivos["imagem"] = f["arquivo"]
            arquivos["ordem_da_imagem"] = f["ordem"]
    reprovados = [r["nome"] for r in res if not r["aprovado"]]
    if correcoes:
        arquivos["modelo"] = t.get("saida") or t["entrada"]
    return {
        "correcoes": correcoes,
        "problemas_antes": antes,
        "arquivos": arquivos,
        "aprovado": not reprovados,
        "reprovados": reprovados,
        "clipes": res,
        "altura_m": round(conf.H, 3),
        "chao_do_descanso_cm": conf.chao_descanso_cm,
        "pes": conf.pes,
        "regras": fc_conferir.regras(),
        "regras_do_corpo": fc_conferir.regras_do_corpo(),
    }


def tarefa_banco(t):
    """Catálogo do banco de movimento (duração, deslocamento, laço, etiquetas) das fontes pedidas."""
    import fc_banco

    clipes = fc_banco.catalogar(t["fontes"])
    return {"arquivos": {}, "clipes": clipes}


def _conferir_e_corrigir(t, objs, arm, acoes, corrigir=True):
    import fc_conferir

    conf, res = fc_conferir.conferir(arm, acoes, t.get("altura_m"))
    correcoes, antes = {}, None
    if corrigir and any(not r["aprovado"] for r in res):
        import fc_corrigir

        quais = t.get("correcoes") or ("trancos", "dobradicas", "pes", "corpo_solido", "torcao", "chao", "pesos")
        antes = {r["nome"]: [p["explicacao"] for p in r["problemas"]] for r in res if not r["aprovado"]}
        # algumas correções criam problema novo (o cotovelo certo pede braço mais torcido): confere de
        # novo e corrige o que sobrou, até 3 rodadas
        for _ in range(int(t.get("rodadas", 3))):
            feito = fc_corrigir.corrigir(arm, acoes, conf, res, quais)
            for nome, log in feito.items():
                correcoes.setdefault(nome, []).append(log)
            res = [conf.medir(a) for a in acoes]
            if all(r["aprovado"] for r in res):
                break
    return conf, res, correcoes, antes


def tarefa_aplicar_banco(t):
    """Clipes do banco de movimento no personagem (retarget, recorte, ciclo, no lugar), conferidos e
    corrigidos; as animações que o personagem já tinha continuam (a não ser as de mesmo nome)."""
    import fc_banco
    import fc_conferir

    objs = _importar(t["entrada"])
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("o personagem não tem esqueleto: monte o esqueleto antes")
    for a in bpy.data.actions:
        a.use_fake_user = True
        if "|" in a.name:
            a.name = a.name.split("|")[-1]
    novas, notas = fc_banco.aplicar(arm, t["clipes"])
    if not novas:
        raise ValueError("nenhum clipe entrou: " + "; ".join(n.get("erro", "") for n in notas if n.get("erro")))
    conf, res, correcoes, antes = _conferir_e_corrigir(t, objs, arm, novas, t.get("corrigir", True))
    saida = t.get("saida") or t["entrada"]
    todas = [a for a in bpy.data.actions if a.use_fake_user]
    if arm.animation_data:
        arm.animation_data.action = novas[0]
    tamanho = c.exportar_glb(saida, objs)
    arquivos = {"modelo": saida}
    if t.get("imagens", "todas") != "nenhuma":
        f = fc_conferir.folha(os.path.splitext(saida)[0] + ".movimento.png", conf, res, novas, todos=True)
        if f:
            arquivos["imagem"] = f["arquivo"]
            arquivos["ordem_da_imagem"] = f["ordem"]
    if t.get("video"):
        malhas = [o for o in objs if o.type == "MESH"]
        arquivos["video"] = c.video(os.path.splitext(saida)[0] + ".movimento.mp4", malhas, novas, arm, largura=480, altura=540, amostras=8)
    return {
        "arquivos": arquivos,
        "tamanho_bytes": tamanho,
        "notas": notas,
        "aprovado": all(r["aprovado"] for r in res),
        "reprovados": [r["nome"] for r in res if not r["aprovado"]],
        "clipes": res,
        "correcoes": correcoes,
        "problemas_antes": antes,
        "animacoes": sorted(a.name for a in todas),
    }


def _com_esqueleto(t):
    objs = _importar(t["entrada"])
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("o modelo não tem esqueleto: use create_skeleton (esqueleto automático) antes")
    for a in bpy.data.actions:
        a.use_fake_user = True
        if "|" in a.name:
            a.name = a.name.split("|")[-1]
    return objs, arm


def tarefa_esqueleto_ver(t):
    """Imagem (frente, lado, cima) com os ossos numerados e a lista com avisos, para a IA conferir."""
    import fc_esqueleto

    objs, arm = _com_esqueleto(t)
    base = os.path.splitext(t.get("saida") or t["entrada"])[0]
    ossos, avisos, H = fc_esqueleto.ver(arm, base + ".esqueleto.png")
    return {"arquivos": {"imagem": base + ".esqueleto.png"}, "ossos": ossos, "avisos": avisos, "altura_m": round(H, 3),
            "animacoes": sorted(a.name for a in bpy.data.actions)}


def tarefa_esqueleto_editar(t):
    """Mudanças no esqueleto pedidas pela IA, pesos refeitos e a imagem nova."""
    import fc_esqueleto

    objs, arm = _com_esqueleto(t)
    feitas, mexidos = fc_esqueleto.editar(arm, t.get("mudancas") or [])
    malhas = fc_esqueleto._malhas(arm, com_pesos=True)
    pesos = t.get("pesos") or "locais"
    if pesos == "locais":
        fc_esqueleto.pesar_por_distancia(arm, malhas, so_perto_de=mexidos)
    elif pesos == "distancia":
        fc_esqueleto.pesar_por_distancia(arm, malhas)
    elif pesos == "auto":
        for o in bpy.context.scene.objects:
            o.select_set(o in malhas or o == arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    saida = t.get("saida") or t["entrada"]
    if arm.animation_data is None or arm.animation_data.action is None:
        acoes = [a for a in bpy.data.actions]
        if acoes:
            (arm.animation_data or arm.animation_data_create()).action = acoes[0]
    tamanho = c.exportar_glb(saida, [o for o in bpy.context.scene.objects if o in objs or o.type in ("MESH", "ARMATURE", "EMPTY")])
    ossos, avisos, H = fc_esqueleto.ver(arm, os.path.splitext(saida)[0] + ".esqueleto.png")
    return {"arquivos": {"modelo": saida, "imagem": os.path.splitext(saida)[0] + ".esqueleto.png"}, "tamanho_bytes": tamanho,
            "feitas": feitas, "pesos": pesos, "ossos": ossos, "avisos": avisos, "altura_m": round(H, 3)}


def tarefa_vestir(t):
    """Roupa por cima de um personagem que já se mexe: os pesos vêm do corpo, as placas ficam rígidas num
    osso, e a conferência roda com a roupa (corpo sólido mede a roupa também)."""
    import fc_conferir
    import fc_esqueleto
    import fc_vestir

    objs, arm = _com_esqueleto(t)
    corpo = fc_esqueleto._malhas(arm, com_pesos=True)
    if not corpo:
        raise ValueError("o personagem não tem malha com pesos para servir de molde")
    novos = _importar(t["roupa"])
    roupa = [o for o in novos if o.type == "MESH"]
    for o in novos:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    for o in roupa:
        mundo = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mundo
        o.modifiers.clear()
        o.vertex_groups.clear()
        # o glTF separa os vértices nas costuras da textura: sem juntar de novo, cada pedaço de costura
        # virava uma "ilha" (uma placa) com o próprio osso, e o braçal virava cunha no cotovelo
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(o.data)
        bm.free()
    if not roupa:
        raise ValueError("o arquivo da roupa não tem malha")
    escala = fc_vestir.encaixar(roupa, corpo) if t.get("encaixar") else None
    mn, mx = c.caixa_envolvente(corpo)
    H = mx.z - mn.z
    resumo = fc_vestir.vestir(arm, corpo, roupa, H, t.get("rigido", "auto"))
    if escala:
        resumo["escala_do_encaixe"] = round(escala, 3)
    acoes = sorted((a for a in bpy.data.actions if a.use_fake_user), key=lambda a: a.name)
    arma = t.get("arma")
    if arma and arma != "nenhuma" or t.get("escudo"):
        import fc_armas_pbr

        nome = os.path.splitext(os.path.basename(t.get("saida") or t["entrada"]))[0]
        presos = {o.parent_bone for o in bpy.context.scene.objects if o.parent == arm and o.parent_type == "BONE"}
        if arma and arma != "nenhuma":
            if presos & {"hand_r", "RightHand", "mixamorig:RightHand"}:
                raise ValueError("o personagem já tem uma arma na mão direita")
            if arma == "espada":
                o = fc_armas_pbr.espada_longa(nome, t.get("cores_arma"))
            else:
                import fc_armas

                o = fc_armas.criar_arma({"tipo": arma, "id": f"{nome}_{arma}", "escala": 1.0})
            fc_armas_pbr.prender_na_mao(o, arm, "r")
            if acoes and "thumb_01_r" not in arm.data.bones:
                resumo["giro_da_arma_graus"] = fc_armas_pbr.acertar_giro(o, arm, acoes, "r")
            resumo["arma"] = arma
        if t.get("escudo"):
            e = fc_armas_pbr.escudo_pipa(nome)
            fc_armas_pbr.prender_na_mao(e, arm, "l", escudo=True)
            resumo["escudo"] = True
    res = []
    arquivos = {}
    saida = t.get("saida") or t["entrada"]
    if acoes:
        conf, res = fc_conferir.conferir(arm, acoes, t.get("altura_m"))
        arm.animation_data.action = acoes[0]
    tamanho = c.exportar_glb(saida, [o for o in bpy.context.scene.objects if o.type in ("MESH", "ARMATURE", "EMPTY")])
    arquivos["modelo"] = saida
    if acoes and t.get("imagens", "todas") != "nenhuma":
        f = fc_conferir.folha(os.path.splitext(saida)[0] + ".vestido.png", conf, res, acoes, todos=True)
        if f:
            arquivos["imagem"] = f["arquivo"]
            arquivos["ordem_da_imagem"] = f["ordem"]
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "roupa": resumo,
            "aprovado": all(r["aprovado"] for r in res), "reprovados": [r["nome"] for r in res if not r["aprovado"]], "clipes": res}


def tarefa_material(t):
    """Recolore os materiais: cores pedidas por nome, ou a paleta do guia visual em ordem."""
    objs = _importar(t["entrada"])
    malhas = [o for o in objs if o.type == "MESH" and not o.name.endswith("-colonly")]
    mats = []
    for o in malhas:
        for m in o.data.materials:
            if m and m not in mats:
                mats.append(m)
    cores = t.get("cores") or {}
    paleta = t.get("paleta") or []
    mudados = {}
    for i, m in enumerate(mats):
        hexa = cores.get(m.name) or (paleta[i % len(paleta)] if paleta and not cores else None)
        if not hexa:
            continue
        cor = c.cor_hex(hexa)
        m.diffuse_color = (*cor, 1.0)
        arv = getattr(m, "node_tree", None)
        bsdf = next((n for n in arv.nodes if n.type == "BSDF_PRINCIPLED"), None) if arv else None
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*cor, 1.0)
            if t.get("rugosidade") is not None:
                bsdf.inputs["Roughness"].default_value = float(t["rugosidade"])
        mudados[m.name] = hexa
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, objs)
    return {"arquivos": {"modelo": saida}, "tamanho_bytes": tamanho, "materiais": mudados, "estatisticas": estatisticas(malhas)}


def tarefa_previa(t):
    objs = _importar(t["entrada"])
    malhas = [o for o in objs if o.type == "MESH" and not o.name.endswith("-colonly")]
    for o in objs:
        if o.name.endswith("-colonly"):
            o.hide_render = True
    caminho = t.get("saida") or os.path.splitext(t["entrada"])[0] + ".previa.png"
    c.renderizar(caminho, malhas, amostras=int(t.get("amostras", 24)))
    return {"arquivos": {"previa": caminho}, "estatisticas": estatisticas(malhas)}


def _acao_pedida(t, arm):
    acoes = {a.name: a for a in bpy.data.actions}
    nome = t.get("animacao")
    if not nome:
        nome = next((n for n in ("parado", "andar") if n in acoes), None) or (sorted(acoes)[0] if acoes else None)
    if nome not in acoes:
        raise ValueError(f"a animação {nome} não existe; o modelo tem: {', '.join(sorted(acoes)) or 'nenhuma'}")
    return acoes[nome]


def tarefa_ver_movimento(t):
    """Folhas do movimento em quadros grandes para a IA (e a pessoa) verem: ângulos, rastro, esqueleto e de perto."""
    import fc_conferir
    import fc_estudio

    objs, arm = _com_esqueleto(t)
    acao = _acao_pedida(t, arm)
    conf, res = fc_conferir.conferir(arm, [acao], t.get("altura_m"))
    r = res[0]
    vermelhos = {}
    for p in r["problemas"]:
        vermelhos.setdefault(p["quadro"], []).append(p["osso"])
        vermelhos.setdefault("todos", []).append(p["osso"])
    estilo = t.get("estilo") or "material"
    # o estilo entra no nome: ver em anime não apaga a folha em material
    base = os.path.splitext(t.get("saida") or t["entrada"])[0] + f".ver_{acao.name}" + ("" if estilo == "material" else f"_{estilo}")
    v = fc_estudio.ver(arm, acao, base, quadros=t.get("quadros") or 8, angulos=tuple(t.get("angulos") or ("tres_quartos", "lado")),
                       estilo=t.get("estilo") or "material", rastro=t.get("rastro", True), ossos=t.get("esqueleto", True),
                       zoom=t.get("de_perto", True), vermelhos_por_quadro=vermelhos, amostras=int(t.get("amostras", 14)))
    v["conferencia"] = r
    v["animacoes"] = sorted(a.name for a in bpy.data.actions)
    v["arquivos"] = {"folhas": [f["arquivo"] for f in v["folhas"]]}
    return v


def tarefa_editar_movimento(t):
    """Ajustes do estúdio (girar/mover ossos em quadros) aplicados na animação, conferidos de novo e gravados."""
    import fc_estudio

    objs, arm = _com_esqueleto(t)
    acao = _acao_pedida(t, arm)
    como = (t.get("salvar_como") or "").strip()
    if como and como != acao.name:
        velha = bpy.data.actions.get(como)
        if velha is not None:
            bpy.data.actions.remove(velha)
        copia = acao.copy()
        copia.name = como
        copia.use_fake_user = True
        acao = copia
    feitos = fc_estudio.editar(arm, acao, t.get("edicoes") or [], int(t.get("suavizar", 6)))
    conf, res, correcoes, antes = _conferir_e_corrigir(t, objs, arm, [acao], bool(t.get("corrigir")))
    saida = t.get("saida") or t["entrada"]
    if arm.animation_data:
        arm.animation_data.action = acao
    tamanho = c.exportar_glb(saida, objs)
    return {
        "arquivos": {"modelo": saida},
        "tamanho_bytes": tamanho,
        "animacao": acao.name,
        "edicoes": feitos,
        "conferencia": res[0],
        "aprovado": res[0]["aprovado"],
        "correcoes": correcoes or None,
        "problemas_antes": antes,
        "animacoes": sorted(a.name for a in bpy.data.actions if a.use_fake_user or a.users),
    }


MARCOS_DO_CORPO = ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l",
                   "thigh_l", "calf_l", "foot_l", "ball_l")


def _marcos(arm, corpo):
    """Onde fica cada parte do corpo (metros, x = esquerda do personagem, y = para trás, z = para cima),
    para a IA pôr cintura, peito, joelho e barra no lugar certo."""
    mw = arm.matrix_world
    ossos = {}
    for n in MARCOS_DO_CORPO:
        b = arm.data.bones.get(n)
        if b is not None:
            h, t = mw @ b.head_local, mw @ b.tail_local
            ossos[n] = {"cabeca": [round(x, 3) for x in h], "ponta": [round(x, 3) for x in t]}
    return {"altura_m": round(corpo.H, 3), "chao_z": round(corpo.z0, 3), "topo_z": round(corpo.z1, 3), "ossos": ossos,
            "dica": "Os ossos do lado direito (_r) são o espelho do esquerdo em x. A cintura é a cabeça do spine_01; o peito, a do spine_03; o joelho, a cabeça do calf; o tornozelo, a do foot."}


def tarefa_roupa(t):
    """Roupa ou armadura feita separada no corpo do manequim (casca, faixa, saia, adorno): grava só a
    roupa (para vestir depois) e as imagens dela sozinha e no manequim de barro."""
    import fc_casca
    import fc_esqueleto

    objs, arm = _com_esqueleto(t)
    corpo_malhas = fc_esqueleto._malhas(arm, com_pesos=True)
    if not corpo_malhas:
        raise ValueError("o corpo não tem malha com pesos: use um personagem com esqueleto (create_character)")
    partes, avisos, corpo = fc_casca.montar(arm, corpo_malhas, t["roupa"])
    saida = t["saida"]
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    tamanho = c.exportar_glb(saida, partes, animacoes=False)
    base = os.path.splitext(saida)[0]
    arquivos = {"modelo": saida}
    if t.get("previa", True):
        # folhas de modelo (ortográficas: frente, lado, costas) e o tronco de perto em três quartos: sozinha
        # (o que vai ser vestido) e no manequim de barro (assenta? cobre o que devia?)
        import fc_estudio

        corpo_objs = [o for o in corpo_malhas if o not in partes]
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        amostras = int(t.get("amostras", 16))

        def folha(caminho, objs):
            for o in bpy.data.objects:
                if o.name == "chao_previa":
                    bpy.data.objects.remove(o, do_unlink=True)
            mn, mx = c.caixa_envolvente(objs)
            mn.z = min(mn.z, 0.0)
            fc_estudio._chao_xadrez(mn, mx, max(mx.z - mn.z, 0.5))
            celulas = []
            for i, (d, nome) in enumerate((((0, -1, 0.0), "frente"), ((1, 0, 0.0), "lado"), ((0, 1, 0.0), "costas"))):
                fc_estudio._carimbo(nome, 16)
                arq = f"{caminho}.tmp{i}.png"
                fc_estudio._render(arq, objs, d, 400, 760, amostras, caixa=(mn, mx), margem=1.06, orto=True)
                celulas.append(fc_estudio._pixels(arq, 400, 760))
            altura = mx.z - mn.z
            meio = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z + 0.62 * altura))
            r = 0.2 * altura
            fc_estudio._carimbo("tronco de perto", 16)
            arq = f"{caminho}.tmp3.png"
            fc_estudio._render(arq, objs, (0.7, -1.0, 0.25), 400, 760, amostras, caixa=(meio - Vector((r, r, r * 1.4)), meio + Vector((r, r, r * 1.4))), margem=1.0)
            celulas.append(fc_estudio._pixels(arq, 400, 760))
            fc_estudio._juntar(caminho, celulas, 4, 400, 760)
            bpy.context.scene.render.use_stamp = False

        for o in corpo_objs:
            o.hide_render = True
        folha(base + ".ver_sozinha.png", partes)
        barro = c.material("fc_barro_manequim", (0.55, 0.53, 0.5), 0.75)
        for o in corpo_objs:
            o.hide_render = False
            o.data.materials.clear()
            o.data.materials.append(barro)
        folha(base + ".ver_no_corpo.png", corpo_objs + partes)
        arquivos["sozinha"] = base + ".ver_sozinha.png"
        arquivos["no_corpo"] = base + ".ver_no_corpo.png"
    lista = []
    for o in partes:
        o.data.calc_loop_triangles()
        lista.append({"nome": o.name, "triangulos": len(o.data.loop_triangles), "material": o.data.materials[0].name if o.data.materials else None})
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "partes": lista, "triangulos": sum(x["triangulos"] for x in lista),
            "avisos": avisos, "corpo": _marcos(arm, corpo)}


TAREFAS = {
    "personagem": tarefa_personagem,
    "arma": tarefa_arma,
    "objeto": tarefa_objeto,
    "mundo": tarefa_mundo,
    "mapa": tarefa_mapa,
    "comparar": tarefa_comparar,
    "limpar": tarefa_limpar,
    "rig": tarefa_rig,
    "retarget": tarefa_retarget,
    "previa": tarefa_previa,
    "animar": tarefa_animar,
    "material": tarefa_material,
    "assar": tarefa_assar,
    "humano": tarefa_humano,
    "criatura": tarefa_criatura,
    "movimento": tarefa_movimento,
    "conferir": tarefa_conferir,
    "banco": tarefa_banco,
    "aplicar_banco": tarefa_aplicar_banco,
    "esqueleto_ver": tarefa_esqueleto_ver,
    "esqueleto_editar": tarefa_esqueleto_editar,
    "vestir": tarefa_vestir,
    "ver_movimento": tarefa_ver_movimento,
    "editar_movimento": tarefa_editar_movimento,
    "roupa": tarefa_roupa,
    "vistas": lambda t: __import__("fc_projetar").tarefa_vistas(t),
    "projetar": lambda t: __import__("fc_projetar").tarefa_projetar(t),
    "projetar_folha": lambda t: __import__("fc_projetar").tarefa_folha(t),
}


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    caminho_tarefa, caminho_resultado = args[0], args[1]
    with open(caminho_tarefa, encoding="utf-8") as f:
        t = json.load(f)
    # pacote de materiais CC0 (qualquer tarefa): PBR e céu HDRI nas prévias
    if t.get("materiais"):
        import fc_pbr

        fc_pbr.definir_pasta(t["materiais"])
        c.PBR["ativo"] = True
    if t.get("ceu"):
        c.definir_ceu(t["ceu"])
    inicio = time.time()
    try:
        c.limpar_cena()
        r = TAREFAS[t["tarefa"]](t)
        r["ok"] = True
    except Exception as e:
        r = {"ok": False, "erro": f"{type(e).__name__}: {e}", "detalhe": traceback.format_exc()}
    r["segundos"] = round(time.time() - inicio, 2)
    r["blender"] = bpy.app.version_string
    with open(caminho_resultado, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    if not r["ok"]:
        print(r["detalhe"], file=sys.stderr)
        sys.exit(1)


main()
