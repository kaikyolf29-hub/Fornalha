"""Quatro vistas: a textura da malha da IA fica mais nítida e mais fiel ao conceito.

O 3D pela IA (TRELLIS.2) vê só a imagem de frente e inventa o resto; no processador a textura sai menor
e borrada. Aqui:
1. `vistas`: a malha é vista de frente, do lado esquerdo, de costas e do lado direito, sem luz (só a cor),
   em câmera ortográfica com o mesmo enquadramento; a imagem do conceito é alinhada à vista de frente
   pela silhueta.
2. Fora do Blender, cada vista é refinada pelo motor de imagem (imagem → imagem: mesmo desenho, mais
   detalhe); a frente pode ser o próprio conceito.
3. `projetar`: as quatro imagens voltam para a textura: cada ponto da malha pega a cor das vistas que o
   enxergam de frente (peso pelo ângulo, sem ponto escondido atrás de outro), e o que nenhuma vista vê
   fica com a cor que já tinha.
"""

import json
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import fc_comum as c

# de onde a câmera olha (do centro para a câmera); o personagem olha para -y, a esquerda dele é +x
VISTAS = {
    "frente": (0.0, -1.0, 0.0),
    "esquerda": (1.0, 0.0, 0.0),
    "costas": (0.0, 1.0, 0.0),
    "direita": (-1.0, 0.0, 0.0),
}
LARGURA, ALTURA = 768, 1152
FUNDO = (0.78, 0.78, 0.78)


def _importar(caminho):
    c.limpar_cena()
    bpy.ops.import_scene.gltf(filepath=caminho)
    c.tirar_ajudantes_do_gltf()
    malhas = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not malhas:
        raise ValueError("a malha da IA não tem malha")
    return malhas


def _enquadramento(malhas):
    mn, mx = c.caixa_envolvente(malhas)
    centro = (mn + mx) / 2
    aspecto = LARGURA / ALTURA
    lado_max = max(mx.x - mn.x, mx.y - mn.y)
    escala = max(mx.z - mn.z, lado_max / aspecto) * 1.06
    return centro, escala


def _eixos(d):
    """Direita e cima da imagem para a câmera que está em `d` (olhando para o centro)."""
    d = Vector(d).normalized()
    frente = -d
    cima = Vector((0, 0, 1))
    direita = frente.cross(cima).normalized()
    return direita, cima


def _cor_da_textura(mat):
    """O nó que dá a cor de base (a textura da IA), para ver sem luz e para trocar depois."""
    if mat is None or not mat.use_nodes:
        return None, None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None or not bsdf.inputs["Base Color"].is_linked:
        return bsdf, None
    return bsdf, bsdf.inputs["Base Color"].links[0].from_socket


def _sem_luz(malhas):
    """Troca a superfície de cada material pela própria cor (emissão): a vista mostra a textura, não a luz."""
    for o in malhas:
        for mat in o.data.materials:
            if mat is None or mat.get("_fc_sem_luz"):
                continue
            mat["_fc_sem_luz"] = True
            arv = mat.node_tree if mat.use_nodes else None
            if arv is None:
                continue
            bsdf, cor = _cor_da_textura(mat)
            saida = next((n for n in arv.nodes if n.type == "OUTPUT_MATERIAL"), None)
            if saida is None:
                continue
            em = arv.nodes.new("ShaderNodeEmission")
            if cor is not None:
                arv.links.new(cor, em.inputs["Color"])
            elif bsdf is not None:
                em.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
            arv.links.new(em.outputs["Emission"], saida.inputs["Surface"])


def _render_sem_luz(caminho, centro, escala, d):
    cena = bpy.context.scene
    cena.render.engine = "CYCLES"
    cena.cycles.samples = 16
    cena.cycles.use_denoising = False
    cena.render.resolution_x, cena.render.resolution_y = LARGURA, ALTURA
    cena.render.resolution_percentage = 100
    cena.render.film_transparent = True
    cena.render.image_settings.file_format = "PNG"
    cena.render.image_settings.color_mode = "RGBA"
    cena.view_settings.view_transform = "Standard"
    cena.view_settings.look = "None"
    cam = cena.camera or c._camera("camera_vistas")
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = escala
    cam.data.sensor_fit = "AUTO"
    cam.location = centro + Vector(d).normalized() * (escala * 3)
    cam.rotation_euler = (-Vector(d)).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = escala * 10
    cena.render.filepath = caminho
    bpy.ops.render.render(write_still=True)


def _pixels(caminho):
    img = bpy.data.images.load(caminho, check_existing=False)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return px  # de baixo para cima, como o Blender guarda


def _gravar(caminho, px):
    h, w = px.shape[:2]
    img = bpy.data.images.new(os.path.basename(caminho), w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(px, dtype=np.float32).ravel())
    img.filepath_raw = caminho
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def _encolher(mascara, passos):
    """Máscara encolhida `passos` pixels e com a beira em rampa (0 fora, 1 bem dentro)."""
    m = mascara.astype(np.float32)
    acc = m.copy()
    for _ in range(passos):
        m = np.minimum.reduce([m, np.roll(m, 1, 0), np.roll(m, -1, 0), np.roll(m, 1, 1), np.roll(m, -1, 1)])
        acc += m
    return acc / (passos + 1)


def _caixa(mascara):
    # linha/coluna da figura: com uma fração boa de pixels dela (o degradê do estúdio deixa pontos soltos)
    h, w = mascara.shape
    linhas = np.nonzero(mascara.sum(1) > max(2, 0.015 * w))[0]
    colunas = np.nonzero(mascara.sum(0) > max(2, 0.015 * h))[0]
    if len(linhas) < 10 or len(colunas) < 5:
        return None
    return linhas[0], linhas[-1], colunas[0], colunas[-1]


def _conceito_na_vista(conceito, alfa_frente, assunto="personagem"):
    """O conceito (foto de estúdio, fundo liso) no enquadramento da vista de frente: mesma altura e o
    mesmo centro da silhueta. Devolve a imagem RGBA (fundo cinza) ou None se não achar a figura."""
    px = _pixels(conceito)
    rgb = px[..., :3]
    cantos = np.concatenate([rgb[:8, :8].reshape(-1, 3), rgb[:8, -8:].reshape(-1, 3), rgb[-8:, :8].reshape(-1, 3), rgb[-8:, -8:].reshape(-1, 3)])
    fundo = np.median(cantos, axis=0)
    # o estúdio tem degradê: o fundo de cada linha pelas bordas dela
    borda = np.concatenate([rgb[:, :6], rgb[:, -6:]], axis=1)
    fundo_linha = np.median(borda, axis=1)[:, None, :]
    dist = np.minimum(np.linalg.norm(rgb - fundo_linha, axis=-1), np.linalg.norm(rgb - fundo, axis=-1))
    figura = dist > 0.07
    cx = _caixa(figura)
    cr = _caixa(alfa_frente > 0.5)
    if cx is None or cr is None:
        return None
    c0, c1, cc0, cc1 = cx
    r0, r1, rc0, rc1 = cr
    s = (r1 - r0) / max(1, (c1 - c0))
    h, w = alfa_frente.shape
    yy, xx = np.mgrid[0:h, 0:w]
    # na altura: o pé e o alto da cabeça casam; na largura, linha a linha: as bordas de fora da silhueta
    # do conceito vão nas da malha (a IA às vezes sai mais larga no tronco ou nas pernas)
    sy = c0 + (yy - r0) / s
    mascara_r = alfa_frente > 0.5

    def bordas(m):
        tem = m.any(1)
        esq = np.where(tem, m.argmax(1), -1).astype(np.float64)
        dir_ = np.where(tem, m.shape[1] - 1 - m[:, ::-1].argmax(1), -1).astype(np.float64)
        return tem, esq, dir_

    tem_r, er, dr = bordas(mascara_r)
    linha_c = np.clip(np.round(c0 + (np.arange(h) - r0) / s).astype(int), 0, figura.shape[0] - 1)
    # o chão do estúdio (degradê, sombra dos pés) vira pedaço falso de figura: no conceito só vale o que
    # cai perto de onde a silhueta da malha diz que a figura está
    meio_c, meio_r = (cc0 + cc1) / 2, (rc0 + rc1) / 2
    folga = 0.06 * figura.shape[1]
    limpa = np.zeros_like(figura)
    for y in range(h):
        if not tem_r[y]:
            continue
        a_ = int(max(0, meio_c + (er[y] - meio_r) / s - folga))
        b_ = int(min(figura.shape[1], meio_c + (dr[y] - meio_r) / s + folga + 1))
        limpa[linha_c[y], a_:b_] = figura[linha_c[y], a_:b_]
    figura = limpa
    tem_c, ec, dc = bordas(figura)
    ok = tem_r & tem_c[linha_c] & ((dr - er) > 4) & ((dc[linha_c] - ec[linha_c]) > 4)
    if ok.sum() > 20:
        # linha em que o conceito foge da proporção geral (sombra no chão, degradê): fica de fora e é
        # interpolada das vizinhas
        larg = (dc[linha_c] - ec[linha_c]) / np.maximum(dr - er, 1.0)
        g = np.median(larg[ok])
        centro_r = (er + dr) / 2
        centro_c = (ec[linha_c] + dc[linha_c]) / 2
        desvio = np.abs((centro_c - (cc0 + cc1) / 2) - (centro_r - (rc0 + rc1) / 2) / s)
        ok &= (np.abs(larg / max(g, 1e-6) - 1) < 0.18) & (desvio < 0.06 * figura.shape[1])
    sx = (cc0 + cc1) / 2 + (xx - (rc0 + rc1) / 2) / s
    if ok.sum() > 20:
        idx = np.nonzero(ok)[0]
        todas = np.arange(h)
        e_r = np.interp(todas, idx, er[idx])
        d_r = np.interp(todas, idx, dr[idx])
        e_c = np.interp(todas, idx, ec[linha_c][idx])
        d_c = np.interp(todas, idx, dc[linha_c][idx])
        fator = (d_c - e_c) / np.maximum(d_r - e_r, 1.0)
        mapa = e_c[:, None] + (xx - e_r[:, None]) * fator[:, None]
        # pedaço por pedaço (cada perna, cada braço solto, o tronco): quando a linha tem o mesmo número
        # de pedaços nas duas, cada borda vai na sua par (a IA às vezes abre mais as pernas que o desenho)
        def pedacos(linha):
            d = np.diff(np.concatenate([[0], linha.astype(np.int8), [0]]))
            ini, fim = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
            bons = (fim - ini) > 4
            return ini[bons], fim[bons]

        for y in range(idx[0], idx[-1] + 1):
            ir, fr = pedacos(mascara_r[y])
            ic, fc_ = pedacos(figura[linha_c[y]])
            if len(ir) != len(ic) or len(ir) < 2:
                continue
            xr = np.ravel(np.stack([ir, fr], 1)).astype(np.float64)
            xc = np.ravel(np.stack([ic, fc_], 1)).astype(np.float64)
            if np.any(np.diff(xr) <= 0) or np.any(np.diff(xc) <= 0):
                continue
            xr = np.concatenate([[xr[0] - 400], xr, [xr[-1] + 400]])
            xc = np.concatenate([[xc[0] - 400 * fator[y]], xc, [xc[-1] + 400 * fator[y]]])
            mapa[y] = np.interp(xx[y], xr, xc)
        # alisado na altura (sem tremer de linha para linha)
        from numpy.lib.stride_tricks import sliding_window_view

        k = 11
        pad = np.pad(mapa, ((k // 2, k // 2), (0, 0)), mode="edge")
        mapa = np.median(sliding_window_view(pad, k, axis=0), axis=-1)
        sx = np.where((yy >= idx[0]) & (yy <= idx[-1]), mapa, sx)
    dentro = (sy >= 0) & (sy < px.shape[0] - 1) & (sx >= 0) & (sx < px.shape[1] - 1)
    y0 = np.clip(sy.astype(int), 0, px.shape[0] - 2)
    x0 = np.clip(sx.astype(int), 0, px.shape[1] - 2)
    fy, fx = (sy - y0)[..., None], (sx - x0)[..., None]
    amostra = (rgb[y0, x0] * (1 - fx) * (1 - fy) + rgb[y0, x0 + 1] * fx * (1 - fy)
               + rgb[y0 + 1, x0] * (1 - fx) * fy + rgb[y0 + 1, x0 + 1] * fx * fy)
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = np.where(dentro[..., None], amostra, np.array(FUNDO, np.float32))
    # confiança (alfa): dentro da silhueta da malha, longe da beira, e nada nos pés (a sombra e o chão do
    # estúdio grudam neles no conceito); sobe em rampa para não deixar remendo com borda
    conf = _encolher(alfa_frente > 0.5, 4)
    # o que no conceito tem cor de fundo de estúdio (chão claro entre as pernas e embaixo da barra, que a
    # malha cobre um pouco diferente) não vale, com folga de alguns pixels: a borda entre o chão e a roupa
    # virava linha clara e remendo na canela
    fundo_no_conceito = (dist < 0.15)[y0, x0] & dentro
    fundo_largo = fundo_no_conceito.copy()
    for _ in range(5):
        fundo_largo = fundo_largo | np.roll(fundo_largo, 1, 0) | np.roll(fundo_largo, -1, 0) | np.roll(fundo_largo, 1, 1) | np.roll(fundo_largo, -1, 1)
    conf = conf * ~fundo_largo
    altura_fig = max(1, r1 - r0)
    if assunto == "personagem":
        rampa_pes = np.clip((yy - (r0 + 0.1 * altura_fig)) / (0.1 * altura_fig), 0.0, 1.0)
    else:
        rampa_pes = np.ones_like(conf)  # objeto: a base é parte dele (só a sombra do chão sai, pela cor)
    out[..., 3] = conf * rampa_pes * dentro
    # quanto a silhueta do conceito alinhado casa com a da malha (1 = igual): abaixo de 0,75 o conceito
    # está em outro ângulo ou outra pose e não entra na frente (entraria torto)
    fig_vista = figura[y0, x0] & dentro
    m_r = alfa_frente > 0.5
    iou = float((fig_vista & m_r).sum() / max(1, (fig_vista | m_r).sum()))
    return out, {"escala": round(float(s), 4), "caixa_conceito": [int(c0), int(c1), int(cc0), int(cc1)],
                 "caixa_vista": [int(r0), int(r1), int(rc0), int(rc1)], "silhueta_igual": round(iou, 3)}


def _reamostrar(px, lado):
    h, w = px.shape[:2]
    ys = np.linspace(0, h - 1, lado)
    xs = np.linspace(0, w - 1, lado)
    y0 = np.clip(ys.astype(int), 0, h - 2)[:, None]
    x0 = np.clip(xs.astype(int), 0, w - 2)[None, :]
    fy = (ys - y0[:, 0])[:, None, None]
    fx = (xs - x0[0])[None, :, None]
    return (px[y0, x0] * (1 - fx) * (1 - fy) + px[y0, x0 + 1] * fx * (1 - fy)
            + px[y0 + 1, x0] * (1 - fx) * fy + px[y0 + 1, x0 + 1] * fx * fy)


def _rosto(conceito_na_vista, alfa_frente, centro, escala, pasta, lado=768):
    """Quinta vista: o rosto em close (o rosto ocupa poucos pixels no conceito de corpo inteiro e saía
    borrado na malha). O recorte do conceito alinhado, ampliado; fora do Blender é refinado em close e
    volta projetado só na cabeça, com peso maior."""
    cx = _caixa(alfa_frente > 0.5)
    if cx is None:
        return None
    r0, r1, _c0, _c1 = cx
    lado_px = int(0.15 * (r1 - r0))
    if lado_px < 24:
        return None
    topo = r1 + int(0.01 * (r1 - r0))
    base = topo - lado_px
    linhas = alfa_frente[max(0, base):topo] > 0.5
    cols = np.nonzero(linhas.any(0))[0]
    if not len(cols):
        return None
    meio_x = int((cols[0] + cols[-1]) / 2)
    x0 = meio_x - lado_px // 2
    h, w = alfa_frente.shape
    if base < 0 or x0 < 0 or x0 + lado_px > w or topo > h:
        return None
    recorte = conceito_na_vista[base:topo, x0:x0 + lado_px]
    grande = _reamostrar(recorte, lado).astype(np.float32)
    arq = os.path.join(pasta, "rosto_conceito.png")
    _gravar(arq, grande)
    # a confiança à parte (o refino devolve a imagem sem alfa)
    conf = np.ones_like(grande)
    conf[..., :3] = grande[..., 3:4]
    arq_conf = os.path.join(pasta, "rosto_confianca.png")
    _gravar(arq_conf, conf)
    # câmera do recorte: o centro dele no mundo (vista de frente: direita = +x, cima = +z)
    meia_h = escala / 2
    meia_w = escala * (LARGURA / ALTURA) / 2
    bx, by = x0 + lado_px / 2, base + lado_px / 2
    X = centro.x + (bx / w - 0.5) * 2 * meia_w
    Z = centro.z + (by / h - 0.5) * 2 * meia_h
    return {"imagem": arq, "confianca": arq_conf, "direcao": list(VISTAS["frente"]), "centro": [X, centro.y, Z],
            "escala": escala * lado_px / h, "largura": lado, "altura": lado}


def tarefa_vistas(t):
    malhas = _importar(t["entrada"])
    pasta = t["pasta"]
    os.makedirs(pasta, exist_ok=True)
    centro, escala = _enquadramento(malhas)
    _sem_luz(malhas)
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("mundo")
    saida = {"centro": list(centro), "escala": escala, "largura": LARGURA, "altura": ALTURA, "vistas": {}}
    alfa_frente = None
    for nome, d in VISTAS.items():
        cru = os.path.join(pasta, f"vista_{nome}_alfa.png")
        _render_sem_luz(cru, centro, escala, d)
        px = _pixels(cru)
        a = px[..., 3:4].copy()
        px[..., :3] = px[..., :3] * a + np.array(FUNDO, np.float32) * (1 - a)
        px[..., 3] = 1.0
        arq = os.path.join(pasta, f"vista_{nome}.png")
        _gravar(arq, px)
        conf = np.zeros_like(px)
        conf[..., :3] = _encolher(a[..., 0] > 0.5, 3)[..., None]
        conf[..., 3] = 1.0
        arq_conf = os.path.join(pasta, f"vista_{nome}_confianca.png")
        _gravar(arq_conf, conf)
        if nome == "frente":
            alfa_frente = a[..., 0]
        saida["vistas"][nome] = {"imagem": arq, "confianca": arq_conf, "direcao": list(d)}
    if t.get("conceito") and alfa_frente is not None:
        assunto = t.get("assunto", "personagem")
        r = _conceito_na_vista(t["conceito"], alfa_frente, assunto)
        if r is not None and r[1]["silhueta_igual"] < float(t.get("silhueta_minima", 0.75)):
            saida["alinhamento"] = dict(r[1], usado=False)
            r = None
        if r is not None:
            arq = os.path.join(pasta, "frente_conceito.png")
            _gravar(arq, r[0])
            saida["frente_conceito"] = arq
            saida["alinhamento"] = r[1]
            conf = np.ones_like(r[0])
            conf[..., :3] = r[0][..., 3:4]
            arq_conf = os.path.join(pasta, "frente_conceito_confianca.png")
            _gravar(arq_conf, conf)
            saida["frente_conceito_confianca"] = arq_conf
            rosto = _rosto(r[0], alfa_frente, centro, escala, pasta) if assunto == "personagem" else None
            if rosto is not None:
                saida["vistas"]["rosto"] = rosto
    with open(os.path.join(pasta, "vistas.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    return {"arquivos": {"vistas": os.path.join(pasta, "vistas.json")}, "vistas": saida}


def _no_de_imagem(arv, img, uv_nome, x, y):
    uv = arv.nodes.new("ShaderNodeUVMap")
    uv.uv_map = uv_nome
    uv.location = (x - 250, y)
    tx = arv.nodes.new("ShaderNodeTexImage")
    tx.image = img
    tx.extension = "EXTEND"
    tx.location = (x, y)
    arv.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    return tx


def tarefa_projetar(t):
    """As vistas (refinadas) de volta na textura de cor da malha. t: entrada, vistas (o vistas.json),
    imagens {vista: png}, saida, lado (pixels da textura nova), peso_original, nitidez (expoente do
    ângulo: maior = só o que está bem de frente)."""
    malhas = _importar(t["entrada"])
    with open(t["vistas"], encoding="utf-8") as f:
        info = json.load(f)
    centro = Vector(info["centro"])
    escala = float(info["escala"])
    meia_h = escala / 2
    meia_w = escala * (info["largura"] / info["altura"]) / 2
    conhecidas = list(VISTAS) + [k for k in info["vistas"] if k not in VISTAS]
    imagens = {k: v for k, v in (t.get("imagens") or {}).items() if k in conhecidas and v and os.path.isfile(v)}
    if not imagens:
        raise ValueError("projetar: nenhuma imagem de vista")
    ordem = [k for k in conhecidas if k in imagens][:8]
    pesos_vista = {"frente": 1.4, "costas": 1.0, "esquerda": 0.9, "direita": 0.9, "rosto": 4.0}
    pesos_vista.update({k: float(v) for k, v in (t.get("pesos") or {}).items()})
    nitidez = float(t.get("nitidez", 3.0))
    peso_original = float(t.get("peso_original", 0.06))
    lado = int(t.get("lado", 2048))
    dg = bpy.context.evaluated_depsgraph_get()
    resumo = {"vistas": ordem, "malhas": []}
    feitos = {}
    for m in malhas:
        me = m.data
        if not me.polygons:
            continue
        if not me.materials:
            mat = bpy.data.materials.new(f"{m.name}_cor")
            mat.use_nodes = True
            me.materials.append(mat)
        if not me.uv_layers:
            # malha sem UV (feita à mão, de outro programa): desdobra antes de assar a cor nova
            for o in bpy.context.scene.objects:
                o.select_set(o == m)
            bpy.context.view_layer.objects.active = m
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004)
            bpy.ops.object.mode_set(mode="OBJECT")
        uv_base = me.uv_layers.active.name
        mw = m.matrix_world
        co = np.array([(mw @ v.co)[:] for v in me.vertices])
        nr = np.array([(mw.to_3x3() @ v.normal).normalized()[:] for v in me.vertices])
        arv_bvh = BVHTree.FromObject(m, dg)
        lv = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", lv)
        pesos = np.zeros((len(me.loops), 8), np.float32)
        cobertura = {}
        for k, nome in enumerate(ordem):
            vi = info["vistas"].get(nome) or {}
            d = Vector(vi.get("direcao") or VISTAS[nome]).normalized()
            direita, cima = _eixos(d)
            c_v = np.array(vi.get("centro") or centro)
            e_v = float(vi.get("escala") or escala)
            asp = float(vi.get("largura") or info["largura"]) / float(vi.get("altura") or info["altura"])
            mh = e_v / 2 if asp <= 1 else e_v / 2 / asp
            mw_ = mh * asp
            rel = co - c_v
            u = 0.5 + rel @ np.array(direita) / (2 * mw_)
            v = 0.5 + rel @ np.array(cima) / (2 * mh)
            frente = np.clip(nr @ np.array(d), 0.0, 1.0) ** nitidez
            # escondido atrás de outra parte da malha (braço na frente do tronco na vista de lado)
            visivel = np.zeros(len(co), bool)
            for i in np.nonzero(frente > 1e-3)[0]:
                p = Vector(co[i]) + Vector(nr[i]) * 0.002 + d * 0.001
                hit = arv_bvh.ray_cast(p, d, escala * 4)
                visivel[i] = hit[0] is None
            w = frente * visivel * ((u > 0) & (u < 1) & (v > 0) & (v < 1)) * pesos_vista.get(nome, 1.0)
            pesos[:, k] = w[lv]
            camada = me.uv_layers.new(name=f"vista_{k}")
            camada.data.foreach_set("uv", np.stack([u[lv], v[lv]], -1).astype(np.float32).ravel())
            cobertura[nome] = round(float((w > 0.05).mean()), 3)
        for g in range(2):
            atr = me.color_attributes.new(f"pesos_vistas_{g}", "FLOAT_COLOR", "CORNER")
            atr.data.foreach_set("color", np.ascontiguousarray(pesos[:, 4 * g:4 * g + 4]).ravel())
        me.uv_layers.active = me.uv_layers[uv_base]
        # material só para assar: média das vistas pelos pesos, com um pouco da cor que já tinha
        bake = bpy.data.materials.new(f"{m.name}_projetar")
        bake.use_nodes = True
        arv = bake.node_tree
        for n in list(arv.nodes):
            arv.nodes.remove(n)
        saida = arv.nodes.new("ShaderNodeOutputMaterial")
        em = arv.nodes.new("ShaderNodeEmission")
        arv.links.new(em.outputs["Emission"], saida.inputs["Surface"])
        canais = []
        for g in range(2):
            atr_no = arv.nodes.new("ShaderNodeAttribute")
            atr_no.attribute_type = "GEOMETRY"
            atr_no.attribute_name = f"pesos_vistas_{g}"
            sep = arv.nodes.new("ShaderNodeSeparateColor")
            arv.links.new(atr_no.outputs["Color"], sep.inputs["Color"])
            canais += [sep.outputs["Red"], sep.outputs["Green"], sep.outputs["Blue"], atr_no.outputs["Alpha"]]
        orig_mat = me.materials[0]
        _bsdf, cor_orig = _cor_da_textura(orig_mat)
        img_orig = cor_orig.node.image if cor_orig is not None and cor_orig.node.type == "TEX_IMAGE" else None
        soma, soma_w = None, None
        termos = []
        tx_orig = _no_de_imagem(arv, img_orig, uv_base, -400, -300) if img_orig is not None else None
        for k, nome in enumerate(ordem):
            img = bpy.data.images.load(imagens[nome], check_existing=False)
            tx = _no_de_imagem(arv, img, f"vista_{k}", -400, 300 * k)
            peso = canais[k]
            # confiança: o alfa da própria imagem (o conceito alinhado traz) ou a máscara da vista
            arq_conf = (info["vistas"].get(nome) or {}).get("confianca")
            if nome == "frente" and t.get("frente_do_conceito") and info.get("frente_conceito_confianca"):
                arq_conf = info["frente_conceito_confianca"]
            # o alfa traz a confiança no conceito alinhado e no rosto (enquanto não passou pelo refino,
            # que devolve sem alfa: aí vale a máscara da vista, se houver)
            tem_alfa = img.channels == 4 and os.path.basename(imagens[nome]).startswith(("frente_conceito", "rosto_conceito"))
            fonte = None
            if tem_alfa:
                fonte = tx.outputs["Alpha"]
            elif arq_conf and os.path.isfile(arq_conf):
                img_c = bpy.data.images.load(arq_conf, check_existing=False)
                img_c.colorspace_settings.name = "Non-Color"
                fonte = _no_de_imagem(arv, img_c, f"vista_{k}", -700, 300 * k).outputs["Color"]
            if fonte is not None:
                mult = arv.nodes.new("ShaderNodeMath")
                mult.operation = "MULTIPLY"
                arv.links.new(peso, mult.inputs[0])
                arv.links.new(fonte, mult.inputs[1])
                peso = mult.outputs["Value"]
            if tx_orig is not None:
                # trava: onde a vista foge demais da cor que a malha já tinha (desalinhada, fundo do
                # estúdio caindo na beira), ela perde o peso
                dist = arv.nodes.new("ShaderNodeVectorMath")
                dist.operation = "DISTANCE"
                arv.links.new(tx.outputs["Color"], dist.inputs[0])
                arv.links.new(tx_orig.outputs["Color"], dist.inputs[1])
                faixa = arv.nodes.new("ShaderNodeMapRange")
                faixa.inputs["From Min"].default_value = float(t.get("diferenca_aceita", 0.35))
                faixa.inputs["From Max"].default_value = float(t.get("diferenca_maxima", 0.9))
                faixa.inputs["To Min"].default_value = 1.0
                faixa.inputs["To Max"].default_value = 0.0
                faixa.clamp = True
                arv.links.new(dist.outputs["Value"], faixa.inputs["Value"])
                vezes = arv.nodes.new("ShaderNodeMath")
                vezes.operation = "MULTIPLY"
                arv.links.new(peso, vezes.inputs[0])
                arv.links.new(faixa.outputs["Result"], vezes.inputs[1])
                peso = vezes.outputs["Value"]
            termos.append((tx.outputs["Color"], peso))
        if img_orig is not None:
            tx = tx_orig
            valor = arv.nodes.new("ShaderNodeValue")
            valor.outputs[0].default_value = peso_original
            termos.append((tx.outputs["Color"], valor.outputs[0]))
        for cor, w in termos:
            esc = arv.nodes.new("ShaderNodeVectorMath")
            esc.operation = "SCALE"
            arv.links.new(cor, esc.inputs[0])
            arv.links.new(w, esc.inputs["Scale"])
            if soma is None:
                soma, soma_w = esc.outputs["Vector"], w
            else:
                ad = arv.nodes.new("ShaderNodeVectorMath")
                ad.operation = "ADD"
                arv.links.new(soma, ad.inputs[0])
                arv.links.new(esc.outputs["Vector"], ad.inputs[1])
                soma = ad.outputs["Vector"]
                aw = arv.nodes.new("ShaderNodeMath")
                aw.operation = "ADD"
                arv.links.new(soma_w, aw.inputs[0])
                arv.links.new(w, aw.inputs[1])
                soma_w = aw.outputs["Value"]
        piso = arv.nodes.new("ShaderNodeMath")
        piso.operation = "MAXIMUM"
        arv.links.new(soma_w, piso.inputs[0])
        piso.inputs[1].default_value = 1e-4
        inv = arv.nodes.new("ShaderNodeMath")
        inv.operation = "DIVIDE"
        inv.inputs[0].default_value = 1.0
        arv.links.new(piso.outputs["Value"], inv.inputs[1])
        media = arv.nodes.new("ShaderNodeVectorMath")
        media.operation = "SCALE"
        arv.links.new(soma, media.inputs[0])
        arv.links.new(inv.outputs["Value"], media.inputs["Scale"])
        arv.links.new(media.outputs["Vector"], em.inputs["Color"])
        alvo_img = bpy.data.images.new(f"{m.name}_cor_vistas", lado, lado, alpha=False)
        alvo_img.colorspace_settings.name = "sRGB"
        alvo = arv.nodes.new("ShaderNodeTexImage")
        alvo.image = alvo_img
        uv_alvo = arv.nodes.new("ShaderNodeUVMap")
        uv_alvo.uv_map = uv_base
        arv.links.new(uv_alvo.outputs["UV"], alvo.inputs["Vector"])
        for n in arv.nodes:
            n.select = False
        alvo.select = True
        arv.nodes.active = alvo
        originais = list(me.materials)
        for i in range(len(me.materials)):
            me.materials[i] = bake
        cena = bpy.context.scene
        cena.render.engine = "CYCLES"
        cena.cycles.samples = 1
        cena.render.bake.margin = 12
        cena.render.bake.use_clear = True
        for o in bpy.context.scene.objects:
            o.select_set(o == m)
        bpy.context.view_layer.objects.active = m
        bpy.ops.object.bake(type="EMIT", uv_layer=uv_base)
        for i, mat in enumerate(originais):
            me.materials[i] = mat
        arq = os.path.join(os.path.dirname(os.path.abspath(t["saida"])), f"{m.name}_cor_vistas.png")
        alvo_img.filepath_raw = arq
        alvo_img.file_format = "PNG"
        alvo_img.save()
        # a cor nova no lugar da textura da IA (o resto do material fica: metal, aspereza, normal); sem
        # textura de cor (só uma cor lisa), a imagem nova entra ligada na cor de base
        for mat in originais:
            if mat is None or not mat.use_nodes:
                continue
            b_, cor = _cor_da_textura(mat)
            if cor is not None and cor.node.type == "TEX_IMAGE" and (img_orig is None or cor.node.image is img_orig):
                cor.node.image = alvo_img
            elif cor is None and b_ is not None:
                tx = mat.node_tree.nodes.new("ShaderNodeTexImage")
                tx.image = alvo_img
                uvn = mat.node_tree.nodes.new("ShaderNodeUVMap")
                uvn.uv_map = uv_base
                mat.node_tree.links.new(uvn.outputs["UV"], tx.inputs["Vector"])
                mat.node_tree.links.new(tx.outputs["Color"], b_.inputs["Base Color"])
        for k in range(len(ordem)):
            camada = me.uv_layers.get(f"vista_{k}")
            if camada is not None:
                me.uv_layers.remove(camada)
        for g in range(2):
            me.color_attributes.remove(me.color_attributes[f"pesos_vistas_{g}"])
        bpy.data.materials.remove(bake)
        feitos[m.name] = arq
        resumo["malhas"].append({"nome": m.name, "cobertura": cobertura, "textura": arq, "lado": lado})
    if not feitos:
        raise ValueError("projetar: a malha não tem UV nem textura de cor")
    tamanho = c.exportar_glb(t["saida"], [o for o in bpy.context.scene.objects if o.type == "MESH"], animacoes=False)
    arquivos = {"modelo": t["saida"]}
    if t.get("previa"):
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        c.folha_de_modelo(t["previa"], objs, largura=420, altura=640, amostras=24)
        arquivos["previa"] = t["previa"]
    return {"arquivos": arquivos, "tamanho_bytes": tamanho, "projecao": resumo}


def tarefa_folha(t):
    """Folha (frente, lado, costas) de uma malha como está, para comparar antes e depois das vistas."""
    malhas = _importar(t["entrada"])
    c.folha_de_modelo(t["saida"], malhas, largura=420, altura=640, amostras=int(t.get("amostras", 24)))
    return {"arquivos": {"folha": t["saida"]}}
