"""Estúdio do movimento: o que a IA e a pessoa precisam para VER e MEXER numa animação.

- `ver(...)`: folhas em quadros grandes (no máximo 4 por linha, para a IA ler sem a imagem encolher),
  enquadramento fixo na animação inteira (o tamanho do gesto aparece), rastro das mãos, dos pés e da ponta
  da arma, chão xadrez de 25 cm (pé escorregando aparece), aproximação da mão e dos pés, esqueleto com os
  ossos reprovados em vermelho, e três estilos de exibição: material (o do jogo), barro (só a forma, para
  ler dobra e volume) e anime (cor chapada em dois tons e contorno, igual ao visual anime do jogo).
- `editar(...)`: aplica os ajustes do estúdio (girar/mover um osso num quadro, com o efeito espalhado
  suavemente nos quadros vizinhos) e devolve a ação pronta para conferir de novo.

Os giros chegam no espaço do glTF (Y para cima), como o three.js da janela mede.
"""

import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

import fc_comum as c
import fc_conferir

ANGULOS = {
    "tres_quartos": (0.75, -1.0, 0.2),
    "frente": (0.0, -1.0, 0.1),
    "lado": (1.0, 0.0, 0.1),
    "costas": (0.0, 1.0, 0.12),
    "cima": (0.15, -0.35, 1.0),
}
ROTULOS = {"tres_quartos": "3/4", "frente": "frente", "lado": "lado", "costas": "costas", "cima": "de cima"}
CORES_RASTRO = {"mao_d": (1.0, 0.45, 0.05), "mao_e": (0.1, 0.65, 1.0), "pe_d": (0.95, 0.85, 0.1), "pe_e": (0.2, 0.9, 0.35), "arma": (1.0, 1.0, 1.0)}
AJUDANTES = ("chao_previa", "Icosphere", "fc_rastro", "fc_osso", "fc_marca")


# ------------------------------------------------------------------ utilidades

def _usar(arm, acao):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = acao
    if hasattr(ad, "action_slot") and getattr(acao, "slots", None):
        try:
            ad.action_slot = acao.slots[0]
        except Exception:
            pass


def _malhas_visiveis():
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith(AJUDANTES)]


def _caixa_da_animacao(objs, quadros):
    """Caixa que cabe a animação inteira (amostras), para a câmera não pular de um quadro para o outro."""
    cena = bpy.context.scene
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for q in quadros:
        cena.frame_set(q)
        for o in objs:
            co = fc_conferir._co_avaliado(o)
            if len(co) == 0:
                continue
            a, b = co.min(axis=0), co.max(axis=0)
            mn = Vector((min(mn.x, a[0]), min(mn.y, a[1]), min(mn.z, a[2])))
            mx = Vector((max(mx.x, b[0]), max(mx.y, b[1]), max(mx.z, b[2])))
    return mn, mx


def _osso(arm, *nomes):
    for n in nomes:
        if n in arm.pose.bones:
            return n
    return None


def _material_emissao(nome, cor, forca=2.5):
    m = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*cor, 1.0)
    em.inputs["Strength"].default_value = forca
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def _linha(nome, pontos, cor, raio):
    cu = bpy.data.curves.new(nome, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = raio
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(pontos) - 1)
    for p, ponto in zip(sp.points, pontos):
        p.co = (ponto.x, ponto.y, ponto.z, 1.0)
    o = bpy.data.objects.new(nome, cu)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(_material_emissao(f"fc_rastro_{nome}", cor))
    return o


def _chao_xadrez(mn, mx, H):
    """Chão com quadrados de 25 cm: o pé que escorrega aparece contra as linhas."""
    velho = bpy.data.objects.get("chao_previa")
    if velho:
        bpy.data.objects.remove(velho, do_unlink=True)
    centro = (mn + mx) / 2
    tamanho = max((mx - mn).length, H) * 8
    bpy.ops.mesh.primitive_plane_add(size=tamanho, location=(centro.x, centro.y, 0.0))
    p = bpy.context.active_object
    p.name = "chao_previa"
    m = bpy.data.materials.new("fc_chao_xadrez")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    xad = nt.nodes.new("ShaderNodeTexChecker")
    xad.inputs["Scale"].default_value = 1.0
    xad.inputs["Color1"].default_value = (0.32, 0.31, 0.3, 1)
    xad.inputs["Color2"].default_value = (0.22, 0.215, 0.21, 1)
    # o xadrez usa as coordenadas do objeto: escala 1 = quadrados de 0,5 m; 2 = 0,25 m
    esc = nt.nodes.new("ShaderNodeVectorMath")
    esc.operation = "SCALE"
    esc.inputs["Scale"].default_value = 2.0
    nt.links.new(coord.outputs["Object"], esc.inputs[0])
    nt.links.new(esc.outputs["Vector"], xad.inputs["Vector"])
    nt.links.new(xad.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    p.data.materials.append(m)
    return p


# ------------------------------------------------------------------ estilos de exibição

def _fonte_da_cor(nt):
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return None, (0.6, 0.6, 0.6, 1.0), None, 1.0
    cor = bsdf.inputs["Base Color"]
    alfa = bsdf.inputs["Alpha"]
    fonte_cor = cor.links[0].from_socket if cor.links else None
    fonte_alfa = alfa.links[0].from_socket if alfa.links else None
    return fonte_cor, tuple(cor.default_value), fonte_alfa, float(alfa.default_value)


def _socket(no, nome, tipo):
    return next(s for s in no.inputs if s.name == nome and s.type == tipo)


def _saida(no, tipo):
    return next(s for s in no.outputs if s.type == tipo)


def _estilo_barro(objs):
    """Barro: a cor some e fica só a forma (dobra, volume, peso). O alfa do cabelo continua."""
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m is None or not m.use_nodes:
                continue
            nt = m.node_tree
            fonte_cor, _, fonte_alfa, alfa = _fonte_da_cor(nt)
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
            if out is None:
                continue
            barro = nt.nodes.new("ShaderNodeBsdfPrincipled")
            barro.inputs["Base Color"].default_value = (0.58, 0.56, 0.54, 1) if o.parent_type != "BONE" else (0.42, 0.42, 0.44, 1)
            barro.inputs["Roughness"].default_value = 0.62
            if fonte_alfa is not None:
                nt.links.new(fonte_alfa, barro.inputs["Alpha"])
            else:
                barro.inputs["Alpha"].default_value = alfa
            nt.links.new(barro.outputs[0], out.inputs["Surface"])


def _estilo_anime(objs, luz=(-0.45, -0.75, 0.85), H=1.8):
    """Anime: cor chapada em dois tons pela direção da luz (como o anime.gdshader do jogo) e contorno
    preto por casco invertido. Sem depender da luz da cena: a sombra é uma só e bem marcada."""
    d = Vector(luz).normalized()
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m is None or not m.use_nodes or m.get("fc_anime"):
                continue
            nt = m.node_tree
            fonte_cor, cor_fixa, fonte_alfa, alfa = _fonte_da_cor(nt)
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
            if out is None:
                continue
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            dir_luz = nt.nodes.new("ShaderNodeCombineXYZ")
            for i, v in enumerate(d):
                dir_luz.inputs[i].default_value = v
            dot = nt.nodes.new("ShaderNodeVectorMath")
            dot.operation = "DOT_PRODUCT"
            nt.links.new(geo.outputs["Normal"], dot.inputs[0])
            nt.links.new(dir_luz.outputs[0], dot.inputs[1])
            degrau = nt.nodes.new("ShaderNodeMapRange")
            degrau.inputs["From Min"].default_value = -0.02
            degrau.inputs["From Max"].default_value = 0.06
            degrau.clamp = True
            nt.links.new(_saida(dot, "VALUE"), degrau.inputs["Value"])
            sombra = nt.nodes.new("ShaderNodeMix")
            sombra.data_type = "RGBA"
            sombra.blend_type = "MULTIPLY"
            _socket(sombra, "Factor", "VALUE").default_value = 1.0
            _socket(sombra, "B", "RGBA").default_value = (0.55, 0.5, 0.62, 1)
            if fonte_cor is not None:
                nt.links.new(fonte_cor, _socket(sombra, "A", "RGBA"))
            else:
                _socket(sombra, "A", "RGBA").default_value = cor_fixa
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            nt.links.new(degrau.outputs["Result"], _socket(mix, "Factor", "VALUE"))
            nt.links.new(_saida(sombra, "RGBA"), _socket(mix, "A", "RGBA"))
            if fonte_cor is not None:
                nt.links.new(fonte_cor, _socket(mix, "B", "RGBA"))
            else:
                _socket(mix, "B", "RGBA").default_value = cor_fixa
            em = nt.nodes.new("ShaderNodeEmission")
            em.inputs["Strength"].default_value = 1.0
            nt.links.new(_saida(mix, "RGBA"), em.inputs["Color"])
            final = em.outputs[0]
            if fonte_alfa is not None or alfa < 0.999:
                tr = nt.nodes.new("ShaderNodeBsdfTransparent")
                mx = nt.nodes.new("ShaderNodeMixShader")
                if fonte_alfa is not None:
                    nt.links.new(fonte_alfa, mx.inputs[0])
                else:
                    mx.inputs[0].default_value = alfa
                nt.links.new(tr.outputs[0], mx.inputs[1])
                nt.links.new(em.outputs[0], mx.inputs[2])
                final = mx.outputs[0]
            nt.links.new(final, out.inputs["Surface"])
            m["fc_anime"] = True
    # contorno: casco invertido (o lado de trás do casco aparece só em volta da silhueta)
    contorno = bpy.data.materials.get("fc_contorno") or bpy.data.materials.new("fc_contorno")
    contorno.use_nodes = True
    nt = contorno.node_tree
    nt.nodes.clear()
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    preto = nt.nodes.new("ShaderNodeEmission")
    preto.inputs["Color"].default_value = (0.02, 0.015, 0.02, 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(geo.outputs["Backfacing"], mx.inputs[0])
    nt.links.new(preto.outputs[0], mx.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    for o in objs:
        if any(m.type == "SOLIDIFY" and m.name == "fc_contorno" for m in o.modifiers):
            continue
        # cabelo em cartões não ganha contorno (viraria uma grade preta)
        if any(s.material and "cabelo" in s.material.name.lower() for s in o.material_slots) and len(o.material_slots) == 1:
            continue
        o.data.materials.append(contorno)
        s = o.modifiers.new("fc_contorno", "SOLIDIFY")
        s.thickness = 0.007 * H
        s.offset = 1.0
        s.use_flip_normals = True
        s.use_rim = False
        s.material_offset = len(o.material_slots) - 1
    cena = bpy.context.scene
    try:
        cena.view_settings.view_transform = "Standard"
        cena.view_settings.look = "None"
        cena.view_settings.exposure = 0.0
    except Exception:
        pass


# ------------------------------------------------------------------ rastro e esqueleto

def _pontas(arm):
    return {
        "mao_d": _osso(arm, "hand_r", "RightHand", "mixamorig:RightHand"),
        "mao_e": _osso(arm, "hand_l", "LeftHand", "mixamorig:LeftHand"),
        "pe_d": _osso(arm, "foot_r", "RightFoot", "mixamorig:RightFoot"),
        "pe_e": _osso(arm, "foot_l", "LeftFoot", "mixamorig:LeftFoot"),
    }


def _ponta_da_arma(arma):
    """O vértice mais longe da pegada (a ponta da lâmina, a cabeça do martelo)."""
    co = np.empty(len(arma.data.vertices) * 3, dtype=np.float32)
    arma.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if not len(co):
        return None
    return Vector(co[int(np.argmax(np.linalg.norm(co, axis=1)))].tolist())


def _rastros(arm, quadros_todos, H, armas):
    cena = bpy.context.scene
    mw = arm.matrix_world
    pontas = {k: v for k, v in _pontas(arm).items() if v}
    trilhas = {k: [] for k in pontas}
    pontas_armas = [(a, _ponta_da_arma(a)) for a in armas]
    trilhas.update({f"arma:{a.name}": [] for a, p in pontas_armas if p is not None})
    for q in quadros_todos:
        cena.frame_set(q)
        for k, n in pontas.items():
            pb = arm.pose.bones[n]
            # mão: o meio da mão; pé: a ponta (onde pisa)
            trilhas[k].append(mw @ (pb.head.lerp(pb.tail, 0.5) if k.startswith("mao") else pb.tail))
        for a, p in pontas_armas:
            if p is not None:
                trilhas[f"arma:{a.name}"].append(a.matrix_world @ p)
    criados = []
    for k, pts in trilhas.items():
        if len(pts) < 2:
            continue
        cor = CORES_RASTRO["arma" if k.startswith("arma") else k]
        criados.append(_linha(f"fc_rastro_{k}", pts, cor, 0.0035 * H))
    return criados


def _esqueleto(arm, vermelhos, H):
    """Varetas dos ossos que deformam (vermelho = reprovado no quadro), para a fileira do esqueleto."""
    mw = arm.matrix_world
    criados = []
    for pb in arm.pose.bones:
        if not pb.bone.use_deform:
            continue
        a, b = mw @ pb.head, mw @ pb.tail
        if (b - a).length < 1e-4:
            continue
        ruim = pb.name in vermelhos
        pano = pb.name.startswith(("saia", "capa", "cabelo", "rabo"))
        cor = (1.0, 0.08, 0.03) if ruim else (0.45, 0.5, 0.6) if pano else (0.9, 0.87, 0.8)
        o = _linha(f"fc_osso_{pb.name}", [a, b], cor, (0.009 if ruim else 0.0025 if pano else 0.006) * H)
        criados.append(o)
    return criados


# ------------------------------------------------------------------ render das folhas

def _carimbo(texto, tamanho=18):
    r = bpy.context.scene.render
    r.use_stamp = True
    for k in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_frame", "use_stamp_frame_range", "use_stamp_memory",
              "use_stamp_hostname", "use_stamp_camera", "use_stamp_lens", "use_stamp_scene", "use_stamp_marker", "use_stamp_filename",
              "use_stamp_sequencer_strip", "use_stamp_peak_memory"):
        if hasattr(r, k):
            setattr(r, k, False)
    r.use_stamp_note = True
    r.stamp_note_text = texto
    r.stamp_font_size = tamanho
    r.stamp_background = (0.0, 0.0, 0.0, 0.55)


def _render(arq, objs, direcao, largura, altura, amostras, caixa=None, margem=1.12, orto=False):
    cena = bpy.context.scene
    c._preparar_render(largura, altura, amostras)
    mn, mx = caixa if caixa else c.caixa_envolvente(objs)
    if not bpy.data.objects.get("sol"):
        c._luzes((mn + mx) / 2, (mx - mn).length)
    cam = cena.camera or c._camera()
    c.enquadrar(cam, mn, mx, direcao, margem=margem, orto=orto)
    if orto:
        # vista de modelo: cabe a altura (ou a largura vista nesse ângulo) com a margem
        d = Vector(direcao).normalized()
        lado = Vector((-d.y, d.x, 0)).normalized() if abs(d.z) < 0.9 else Vector((1, 0, 0))
        ext = mx - mn
        largura_vista = abs(ext.x * lado.x) + abs(ext.y * lado.y)
        cam.data.sensor_fit = "AUTO"
        cam.data.ortho_scale = max(ext.z * largura / altura if largura > altura else ext.z, largura_vista * (altura / largura if altura > largura else 1.0)) * margem
    cena.render.filepath = arq
    os.makedirs(os.path.dirname(os.path.abspath(arq)), exist_ok=True)
    bpy.ops.render.render(write_still=True)


def _pixels(arq, largura, altura):
    img = bpy.data.images.load(arq)
    px = np.empty(largura * altura * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    os.remove(arq)
    return px.reshape(altura, largura, 4)


def _juntar(caminho, celulas, colunas, largura, altura):
    linhas = int(math.ceil(len(celulas) / colunas))
    vazio = np.zeros((altura, largura, 4), dtype=np.float32)
    vazio[..., 3] = 1
    celulas = celulas + [vazio] * (linhas * colunas - len(celulas))
    # fio escuro entre os quadros
    for cel in celulas:
        cel[:, :2, :3] = 0.02
        cel[:2, :, :3] = 0.02
    linhas_img = [np.concatenate(celulas[k * colunas:(k + 1) * colunas], axis=1) for k in range(linhas)]
    junta = np.concatenate(linhas_img[::-1], axis=0)
    final = bpy.data.images.new("fc_folha", width=largura * colunas, height=altura * linhas, alpha=True)
    final.pixels.foreach_set(junta.ravel())
    final.filepath_raw = caminho
    final.file_format = "PNG"
    final.save()
    bpy.data.images.remove(final)
    return caminho


def quadros_de(acao, pedido, n_padrao=8):
    ini, fim = (int(round(x)) for x in acao.frame_range)
    if isinstance(pedido, list) and pedido:
        return sorted({min(fim, max(ini, int(q))) for q in pedido})
    n = int(pedido or n_padrao)
    n = max(2, min(16, n))
    return sorted({int(round(ini + (fim - ini) * i / (n - 1))) for i in range(n)})


def ver(arm, acao, base, quadros=8, angulos=("tres_quartos", "lado"), estilo="material", rastro=True, ossos=True, zoom=True,
        vermelhos_por_quadro=None, largura=384, altura=560, amostras=14, nome=None):
    """Folhas do movimento para a IA (e a pessoa) verem. Devolve a lista de imagens e o que cada uma mostra."""
    cena = bpy.context.scene
    _usar(arm, acao)
    nome = nome or acao.name
    ini, fim = (int(round(x)) for x in acao.frame_range)
    qs = quadros_de(acao, quadros)
    objs = _malhas_visiveis()
    armas = [o for o in objs if o.parent == arm and o.parent_type == "BONE"]
    H = max(0.5, (c.caixa_envolvente(objs)[1] - c.caixa_envolvente(objs)[0]).z) if objs else 1.8
    mn, mx = _caixa_da_animacao(objs, qs)
    # o chão no zero (o pé pisa nele) e a caixa encosta no chão
    mn.z = min(mn.z, 0.0)
    if estilo == "barro":
        _estilo_barro(objs)
    elif estilo == "anime":
        _estilo_anime(objs, H=H)
    _chao_xadrez(mn, mx, H)
    criados = _rastros(arm, list(range(ini, fim + 1)), H, armas) if rastro else []
    folhas = []
    vermelhos_por_quadro = vermelhos_por_quadro or {}
    try:
        for ang in angulos:
            d = ANGULOS.get(ang, ANGULOS["tres_quartos"])
            celulas = []
            for q in qs:
                cena.frame_set(q)
                _carimbo(f"{nome} · q{q} · {ROTULOS.get(ang, ang)}")
                arq = f"{base}.tmp_{ang}_{q}.png"
                _render(arq, objs + criados, d, largura, altura, amostras, caixa=(mn, mx))
                celulas.append(_pixels(arq, largura, altura))
            for k in range(0, len(celulas), 8):
                parte = celulas[k:k + 8]
                arq = f"{base}.{ang}{'' if k == 0 else '_' + str(k // 8 + 1)}.png"
                _juntar(arq, parte, min(4, len(parte)), largura, altura)
                folhas.append({"arquivo": arq, "mostra": f"{ang.replace('_', ' ')}: quadros {', '.join(map(str, qs[k:k + 8]))}", "quadros": qs[k:k + 8]})
        if ossos:
            esconder = [o for o in objs if o not in armas]
            for o in esconder:
                o.hide_render = True
            celulas = []
            try:
                for q in qs:
                    cena.frame_set(q)
                    varetas = _esqueleto(arm, set(vermelhos_por_quadro.get(q, [])) | set(vermelhos_por_quadro.get("todos", [])), H)
                    _carimbo(f"{nome} · q{q} · esqueleto")
                    arq = f"{base}.tmp_ossos_{q}.png"
                    _render(arq, objs + criados, ANGULOS["tres_quartos"], largura, altura, amostras, caixa=(mn, mx))
                    for o in varetas:
                        bpy.data.objects.remove(o, do_unlink=True)
                    celulas.append(_pixels(arq, largura, altura))
            finally:
                for o in esconder:
                    o.hide_render = False
            for k in range(0, len(celulas), 8):
                parte = celulas[k:k + 8]
                arq = f"{base}.esqueleto{'' if k == 0 else '_' + str(k // 8 + 1)}.png"
                _juntar(arq, parte, min(4, len(parte)), largura, altura)
                folhas.append({"arquivo": arq, "mostra": f"esqueleto (vermelho = osso reprovado): quadros {', '.join(map(str, qs[k:k + 8]))}", "quadros": qs[k:k + 8]})
        if zoom:
            for o in criados:
                o.hide_render = True
            folhas += _zoom(arm, objs, armas, base, nome, qs, largura, altura, amostras, H)
    finally:
        for o in criados:
            bpy.data.objects.remove(o, do_unlink=True)
        cena.render.use_stamp = False
    return {"folhas": folhas, "quadros": qs, "estilo": estilo, "angulos": list(angulos), "rastro": bool(rastro),
            "cores_do_rastro": {"mao_d": "laranja", "mao_e": "azul", "pe_d": "amarelo", "pe_e": "verde", "arma": "branco"} if rastro else None}


def _zoom(arm, objs, armas, base, nome, qs, largura, altura, amostras, H):
    """Perto da mão que segura a arma (ou da direita) e dos pés, em 4 quadros espalhados cada."""
    cena = bpy.context.scene
    mw = arm.matrix_world
    pontas = _pontas(arm)
    mao = (armas[0].parent_bone if armas else None) or pontas["mao_d"] or pontas["mao_e"]
    pes = [p for p in (pontas["pe_e"], pontas["pe_d"]) if p]
    escolha = [qs[int(round(i * (len(qs) - 1) / 3))] for i in range(4)] if len(qs) >= 4 else qs
    celulas, linhas = [], []
    for alvo, rotulo in ((mao, "mão"), (pes, "pés")):
        if not alvo:
            continue
        for q in escolha:
            cena.frame_set(q)
            direcao = ANGULOS["tres_quartos"]
            if rotulo == "mão":
                pb = arm.pose.bones[alvo]
                centro = mw @ pb.head.lerp(pb.tail, 0.6)
                meio = 0.16 * H / 1.8
                # a câmera vem do lado em que a mão está (de fora do corpo), um pouco de frente: assim o
                # corpo e a túnica não tampam a mão
                quadril = mw @ arm.pose.bones[0].head
                fora = Vector((centro.x - quadril.x, centro.y - quadril.y, 0.0))
                if fora.length > 1e-3:
                    fora.normalize()
                    d = fora + Vector((0.0, -0.7, 0.0)) + Vector((0.0, 0.0, 0.35))
                    direcao = tuple(d.normalized())
            else:
                pts = [mw @ arm.pose.bones[p].head for p in alvo] + [mw @ arm.pose.bones[p].tail for p in alvo]
                centro = sum(pts, Vector()) / len(pts)
                centro.z = max(centro.z, 0.08)
                meio = max(0.3 * H / 1.8, max((p - centro).length for p in pts) + 0.12)
            caixa = (centro - Vector((meio, meio, meio)), centro + Vector((meio, meio, meio)))
            _carimbo(f"{nome} · q{q} · {rotulo} de perto")
            arq = f"{base}.tmp_zoom_{rotulo}_{q}.png"
            _render(arq, objs, direcao, largura, altura, amostras, caixa=caixa, margem=1.0)
            celulas.append(_pixels(arq, largura, altura))
        linhas.append(rotulo)
    if not celulas:
        return []
    arq = f"{base}.de_perto.png"
    _juntar(arq, celulas, min(4, len(escolha)), largura, altura)
    return [{"arquivo": arq, "mostra": f"de perto ({' e '.join(linhas)}): quadros {', '.join(map(str, escolha))}", "quadros": escolha}]


# ------------------------------------------------------------------ edição

def _quat_do_gltf(q):
    """[x, y, z, w] no espaço do glTF (Y para cima) → Quaternion do Blender (Z para cima)."""
    x, y, z, w = (float(v) for v in q)
    return Quaternion((w, x, -z, y)).normalized()


def _vec_do_gltf(v):
    x, y, z = (float(a) for a in v)
    return Vector((x, -z, y))


def editar(arm, acao, edicoes, suavizar=6):
    """Aplica os ajustes do estúdio na ação. Cada ajuste: {osso, quadro, giro: [x,y,z,w] (o quanto o osso
    gira, no mundo do glTF), mover: [x,y,z] (metros, mundo do glTF; para o quadril/raiz)}. O efeito é
    inteiro no quadro pedido e some suavemente em `suavizar` quadros para cada lado (sem tranco).
    Devolve o que mudou."""
    cena = bpy.context.scene
    _usar(arm, acao)
    ini, fim = (int(round(x)) for x in acao.frame_range)
    mw = arm.matrix_world
    mw_inv = mw.inverted()
    feitos = []
    for e in edicoes:
        nome = e.get("osso")
        if nome not in arm.pose.bones:
            raise ValueError(f"o osso {nome} não existe neste esqueleto")
        pb = arm.pose.bones[nome]
        if pb.rotation_mode != "QUATERNION":
            pb.rotation_mode = "QUATERNION"
        q0 = int(e.get("quadro", ini))
        k = int(e.get("suavizar", suavizar))
        giro = _quat_do_gltf(e["giro"]) if e.get("giro") else None
        mover = _vec_do_gltf(e["mover"]) if e.get("mover") else None
        if giro is None and mover is None:
            continue
        mudados = 0
        for q in range(max(ini, q0 - k), min(fim, q0 + k) + 1):
            # cosseno: 1 no quadro pedido, 0 em ±(k+1)
            w = 1.0 if k == 0 else 0.5 * (1 + math.cos(math.pi * abs(q - q0) / (k + 1)))
            if w <= 1e-4:
                continue
            cena.frame_set(q)
            M = mw @ pb.matrix
            loc, rot, esc = M.decompose()
            if giro is not None:
                rot = Quaternion().slerp(giro, w) @ rot
            if mover is not None:
                loc = loc + mover * w
            novo = Matrix.LocRotScale(loc, rot, esc)
            pb.matrix = mw_inv @ novo
            bpy.context.view_layer.update()
            pb.keyframe_insert("rotation_quaternion", frame=q, group=nome)
            if mover is not None:
                pb.keyframe_insert("location", frame=q, group=nome)
            mudados += 1
        feitos.append({"osso": nome, "quadro": q0, "quadros_mudados": mudados})
    return feitos
