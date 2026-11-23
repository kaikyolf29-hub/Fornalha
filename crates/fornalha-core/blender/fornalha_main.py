# Fornalha: ponto de entrada dos scripts do Blender.
# blender -b --factory-startup --python-exit-code 1 -P fornalha_main.py -- tarefa.json resultado.json
import json
import math
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    saida = t["saida"]
    # QA automático (bíblia técnica 9.3): o resultado vai junto, para a janela e o agente verem
    import fc_lookdev

    qa = fc_lookdev.qa([arm] + pecas, arm, corpo=pecas[0] if pecas else None,
                       cabelo=[o for o in pecas if o.name.endswith("_hair") or "couro_cabeludo" in o.name] or None)
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
    obj = fc_armas.criar_arma(p)
    encaixe = bpy.data.objects.new("encaixe_mao", None)
    bpy.context.scene.collection.objects.link(encaixe)
    col = fc_armas.colisao_simples(obj)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [obj, encaixe, col], animacoes=False)
    arquivos = {"modelo": saida}
    col.hide_set(True)
    arquivos.update(previas(t, [obj], saida))
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": estatisticas([obj])}


def tarefa_objeto(t):
    import fc_armas

    p = t.get("objeto", {})
    obj = fc_armas.criar_objeto(p)
    col = fc_armas.colisao_simples(obj)
    saida = t["saida"]
    tamanho = c.exportar_glb(saida, [obj, col], animacoes=False)
    arquivos = {"modelo": saida}
    col.hide_set(True)
    arquivos.update(previas(t, [obj], saida))
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "estatisticas": estatisticas([obj])}


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


def _importar(caminho):
    antes = set(bpy.data.objects)
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=caminho)
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


def tarefa_rig(t):
    """Malha de fora (TRELLIS.2, Hunyuan3D, feita à mão) ganha o esqueleto padrão, pesos e animações."""
    import fc_animacoes
    import fc_personagem

    objs = _importar(t["entrada"])
    m = _juntar_malhas(objs, t.get("nome", "personagem"))
    info = limpar_malha(m, t)
    if t.get("esqueleto") == "jogo":
        return _rig_de_jogo(t, m, info)
    if t.get("esqueleto") == "dragao":
        return _rig_de_dragao(t, m, info)
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
    arm, info_rig = fc_rig_ia.rigar(m, nome, float(t.get("altura_m") or 1.8))
    acoes = fc_retarget.aplicar_biblioteca(arm, t["animacoes_de"], t.get("animacoes")) if t.get("animacoes_de") else []
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


TAREFAS = {
    "personagem": tarefa_personagem,
    "arma": tarefa_arma,
    "objeto": tarefa_objeto,
    "mundo": tarefa_mundo,
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
