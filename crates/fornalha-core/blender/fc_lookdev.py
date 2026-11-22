# Fornalha: estúdio de look-dev padronizado e QA automático (bíblia técnica, seção 9).
# Todo personagem é avaliado no MESMO estúdio: fundo cinza 18%, luz de 3 pontos (chave a 45°,
# preenchimento suave, recorte atrás), esferas de calibração (cromo e cinza 18%) e câmeras fixas
# (corpo inteiro de frente, 3/4, perfil e costas; rosto; linha do cabelo; coroa; nuca).
# O QA roda em código antes de mostrar o resultado e devolve o que passou e o que falhou.
import math
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

CINZA_18 = (0.18, 0.18, 0.18)  # linear (≈ #767676 de reflectância; o fundo visto fica ~#4A4A4A)


def _limpar_estudio():
    for o in list(bpy.data.objects):
        if o.name.startswith("ld_"):
            bpy.data.objects.remove(o, do_unlink=True)


def _luz(nome, energia, pos, alvo, tamanho, cor=(1, 1, 1)):
    luz = bpy.data.lights.new(nome, "AREA")
    luz.energy = energia
    luz.size = tamanho
    luz.color = cor
    o = bpy.data.objects.new(nome, luz)
    bpy.context.scene.collection.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(alvo) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return o


def _esfera(nome, pos, raio, metal, rug, cor):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=raio, location=pos)
    o = bpy.context.active_object
    o.name = nome
    for p in o.data.polygons:
        p.use_smooth = True
    m = bpy.data.materials.new(nome + "_mat")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*cor, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rug
    o.data.materials.append(m)
    return o


def estudio(altura, centro_xy=(0.0, 0.0)):
    """Monta o estúdio em volta de um personagem de `altura` metros."""
    _limpar_estudio()
    cena = bpy.context.scene
    mundo = bpy.data.worlds.get("ld_mundo") or bpy.data.worlds.new("ld_mundo")
    cena.world = mundo
    mundo.use_nodes = True
    fundo = mundo.node_tree.nodes.get("Background")
    for l in list(fundo.inputs["Color"].links):
        mundo.node_tree.links.remove(l)
    fundo.inputs["Color"].default_value = (*CINZA_18, 1.0)
    fundo.inputs["Strength"].default_value = 0.35
    cx, cy = centro_xy
    a = altura
    _luz("ld_chave", 260.0 * a, (cx - 1.6 * a, cy - 1.6 * a, 1.25 * a), (cx, cy, 0.6 * a), 1.2 * a, (1.0, 0.96, 0.92))
    _luz("ld_preench", 70.0 * a, (cx + 1.8 * a, cy - 1.2 * a, 0.7 * a), (cx, cy, 0.55 * a), 2.0 * a, (0.9, 0.95, 1.0))
    _luz("ld_recorte", 220.0 * a, (cx + 0.6 * a, cy + 1.8 * a, 1.3 * a), (cx, cy, 0.75 * a), 0.8 * a, (1.0, 0.98, 0.95))
    # chão cinza (sombra de contato) e esferas de calibração no canto
    bpy.ops.mesh.primitive_plane_add(size=12 * a, location=(cx, cy, 0.0))
    chao = bpy.context.active_object
    chao.name = "ld_chao"
    mc = bpy.data.materials.new("ld_chao_mat")
    mc.use_nodes = True
    bc = next(n for n in mc.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bc.inputs["Base Color"].default_value = (*CINZA_18, 1.0)
    bc.inputs["Roughness"].default_value = 0.8
    chao.data.materials.append(mc)
    r = 0.07 * a
    _esfera("ld_cromo", (cx + 0.42 * a, cy - 0.15 * a, r), r, 1.0, 0.0, (0.95, 0.95, 0.95))
    _esfera("ld_cinza18", (cx + 0.42 * a + 2.4 * r, cy - 0.15 * a, r), r, 0.0, 0.5, CINZA_18)
    cena.view_settings.view_transform = "AgX"
    try:
        cena.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    cena.view_settings.exposure = 0.0


CAMERAS = {
    # nome: (alvo relativo à altura (x, y, z), direção da câmera, distância em alturas, lente)
    "frente": ((0, 0, 0.52), (0.0, -1.0, 0.05), 2.1, 50),
    "tres_quartos": ((0, 0, 0.52), (-0.75, -0.75, 0.08), 2.1, 50),
    "perfil": ((0, 0, 0.52), (-1.0, 0.0, 0.05), 2.1, 50),
    "costas": ((0, 0, 0.52), (0.0, 1.0, 0.08), 2.1, 50),
    "rosto": ((0, -0.01, 0.925), (-0.22, -1.0, 0.03), 0.42, 85),
    "linha_cabelo": ((0, -0.02, 0.965), (-0.15, -1.0, 0.55), 0.3, 85),
    "coroa": ((0, 0.02, 0.985), (0.25, 0.6, 1.0), 0.3, 85),
    "nuca": ((0, 0.04, 0.92), (0.2, 1.0, 0.15), 0.32, 85),
}


def fotos(caminho_base, altura, cameras=None, largura=720, altura_px=900, amostras=48):
    """Renderiza as câmeras de inspeção. Devolve {nome: arquivo}."""
    cena = bpy.context.scene
    cena.render.engine = "CYCLES"
    cena.cycles.samples = amostras
    cena.cycles.use_denoising = True
    cena.render.resolution_x, cena.render.resolution_y = largura, altura_px
    cam = bpy.data.objects.get("ld_camera")
    if cam is None:
        cam = bpy.data.objects.new("ld_camera", bpy.data.cameras.new("ld_camera"))
        cena.collection.objects.link(cam)
    cena.camera = cam
    cam.data.clip_start = 0.01
    saida = {}
    for nome in cameras or CAMERAS:
        alvo_r, direcao, dist, lente = CAMERAS[nome]
        alvo = Vector((alvo_r[0] * altura, alvo_r[1] * altura, alvo_r[2] * altura))
        cam.data.lens = lente
        cam.location = alvo + Vector(direcao).normalized() * dist * altura
        cam.rotation_euler = (alvo - cam.location).to_track_quat("-Z", "Y").to_euler()
        arq = f"{caminho_base}.ld_{nome}.png"
        cena.render.filepath = arq
        bpy.ops.render.render(write_still=True)
        saida[nome] = arq
    return saida


def folha(arquivos, caminho, colunas=4):
    """Junta as fotos numa folha só (sem Pillow: pelas imagens do Blender)."""
    imgs = []
    for nome, arq in arquivos.items():
        im = bpy.data.images.load(arq, check_existing=False)
        w, h = im.size
        px = np.empty(w * h * 4, dtype=np.float32)
        im.pixels.foreach_get(px)
        imgs.append(px.reshape(h, w, 4))
        bpy.data.images.remove(im)
    if not imgs:
        return None
    h, w = imgs[0].shape[:2]
    linhas = math.ceil(len(imgs) / colunas)
    tela = np.zeros((linhas * h, colunas * w, 4), dtype=np.float32)
    tela[..., 3] = 1.0
    for k, im in enumerate(imgs):
        lin = linhas - 1 - k // colunas  # o Blender guarda de baixo para cima
        col = k % colunas
        tela[lin * h:(lin + 1) * h, col * w:(col + 1) * w] = im[:h, :w]
    out = bpy.data.images.new("ld_folha", colunas * w, linhas * h, alpha=False)
    out.pixels.foreach_set(tela.ravel())
    out.filepath_raw = caminho
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    return caminho


# ------------------------------------------------------------------ QA automático

def _malhas(objs):
    return [o for o in objs if o.type == "MESH" and len(o.data.polygons)]


def qa(objs, arm=None, corpo=None, cabelo=None):
    """Verificações da bíblia (9.3). Devolve {"passou": bool, "itens": [{nome, ok, detalhe}]}."""
    itens = []

    def item(nome, ok, detalhe=""):
        itens.append({"nome": nome, "ok": bool(ok), "detalhe": detalhe})

    malhas = _malhas(objs)
    # 1. transformações
    ruins = [o.name for o in malhas if any(abs(s - 1.0) > 1e-4 for s in o.scale) or any(abs(r) > 1e-4 for r in o.rotation_euler)]
    item("escala 1 e rotação 0 em tudo que é exportado", not ruins, ", ".join(ruins[:5]))
    # faces degeneradas
    degeneradas = 0
    for o in malhas:
        areas = np.empty(len(o.data.polygons))
        o.data.polygons.foreach_get("area", areas)
        degeneradas += int((areas < 1e-10).sum())
    item("sem faces degeneradas", degeneradas == 0, f"{degeneradas} faces")
    # pesos somando 1 nas malhas com esqueleto
    sem_peso = []
    for o in malhas:
        if not any(m.type == "ARMATURE" for m in o.modifiers):
            continue
        soma = np.zeros(len(o.data.vertices))
        for v in o.data.vertices:
            soma[v.index] = sum(g.weight for g in v.groups)
        if (soma < 0.98).mean() > 0.01:
            sem_peso.append(f"{o.name} ({(soma < 0.98).mean() * 100:.0f}%)")
    item("pesos de osso somando 1", not sem_peso, ", ".join(sem_peso[:5]))
    # 2. cabelo: couro cabeludo encostado no crânio e sem buracos
    if corpo is not None and cabelo:
        co = np.array([(corpo.matrix_world @ v.co)[:] for v in corpo.data.vertices])
        kd = KDTree(len(co))
        for i, p in enumerate(co):
            kd.insert(p, i)
        kd.balance()
        cap = next((o for o in cabelo if "couro_cabeludo" in o.name), None)
        if cap is not None:
            dist = [kd.find(cap.matrix_world @ v.co)[2] for v in cap.data.vertices]
            mx = float(np.percentile(dist, 99)) if dist else 0.0
            item("couro cabeludo a menos de 2 mm do crânio", mx < 0.002, f"{mx * 1000:.2f} mm")
        cards = next((o for o in cabelo if o.name.endswith("_hair")), None)
        if cards is not None:
            g = cards.vertex_groups.get("head")
            ok = g is not None and all(any(ge.group == g.index and ge.weight > 0.999 for ge in v.groups) for v in cards.data.vertices)
            item("cabelo todo preso ao osso da cabeça", ok)
        item("cobertura do couro cabeludo (raios de fora para dentro)", *_cobertura(corpo, cabelo))
    # 3. texturas: mapas de dados em Non-Color, albedo de dielétrico na faixa física
    cor_errada, albedo_fora = [], []
    for o in malhas:
        for ms in o.material_slots:
            m = ms.material
            if not m or not m.use_nodes:
                continue
            b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if b is None:
                continue
            for entrada in ("Roughness", "Metallic", "Normal"):
                for l in b.inputs[entrada].links:
                    no = l.from_node
                    if no.type == "NORMAL_MAP" and no.inputs["Color"].links:
                        no = no.inputs["Color"].links[0].from_node
                    if no.type == "TEX_IMAGE" and no.image and no.image.colorspace_settings.name not in ("Non-Color", "Linear", "Raw", "Linear Rec.709"):
                        cor_errada.append(f"{m.name}:{entrada}")
            pelo = any(k in m.name.lower() for k in ("eyelash", "eyebrow", "cabelo", "hair", "couro_cabeludo", "olhos", "teeth"))
            if not pelo and b.inputs["Metallic"].default_value < 0.5 and not b.inputs["Metallic"].links:
                media = _media_albedo(b)
                if media is not None and not (0.04 <= media <= 0.9):
                    albedo_fora.append(f"{m.name} ({media:.2f})")
    item("mapas de dados em Non-Color", not cor_errada, ", ".join(cor_errada[:5]))
    item("albedo de dielétrico na faixa física (0,04–0,9)", not albedo_fora, ", ".join(albedo_fora[:5]))
    # 4. pés no chão na pose de descanso (o ponto mais baixo de todas as peças: bota, sapato ou pé)
    if malhas:
        zmin = min(min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in malhas)
        # até 2 cm abaixo: a sola da bota/sapato tem espessura
        item("pés no chão (pose de descanso)", -0.02 <= zmin <= 0.02, f"{zmin * 100:.1f} cm")
    return {"passou": all(i["ok"] for i in itens), "itens": itens}


def _media_albedo(bsdf):
    e = bsdf.inputs["Base Color"]
    if e.links and e.links[0].from_node.type == "TEX_IMAGE" and e.links[0].from_node.image:
        img = e.links[0].from_node.image
        w, h = img.size
        if not w:
            return None
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(-1, 4)
        vis = px[:, 3] > 0.5
        rgb = px[vis, :3] if vis.any() else px[:, :3]
        return float((rgb @ np.array([0.2126, 0.7152, 0.0722])).mean())
    if not e.links:
        c = e.default_value
        return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) ** (1 / 2.2)
    return None


def _cobertura(corpo, cabelo, n=600):
    """Raios de fora para dentro na região do couro cabeludo: o primeiro objeto atingido tem de
    ser o cabelo (couro cabeludo ou cards), não a pele."""
    dg = bpy.context.evaluated_depsgraph_get()
    cena = bpy.context.scene
    cap = next((o for o in cabelo if "couro_cabeludo" in o.name), None)
    if cap is None:
        return False, "sem couro cabeludo"
    vs = np.array([(cap.matrix_world @ v.co)[:] for v in cap.data.vertices])
    if not len(vs):
        return False, "couro cabeludo vazio"
    c = vs.mean(0)
    # miolo: tira os vértices da borda da peça (o fade da linha do cabelo)
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(cap.data)
    borda = {v.index for e in bm.edges if e.is_boundary for v in e.verts}
    anel = {w.index for v in bm.verts if v.index in borda for e in v.link_edges for w in e.verts}
    bm.free()
    miolo = [i for i in range(len(vs)) if i not in anel]
    if len(miolo) > 20:
        vs = vs[miolo]
    rng = np.random.default_rng(1)
    alvo = vs[rng.choice(len(vs), min(n, len(vs)), replace=False)]
    acertos = total = 0
    nomes_cabelo = {o.name for o in cabelo}
    # só conta raio que acerta cabelo ou a pele da cabeça (gola, orelha de fora etc. não contam);
    # e só onde o couro cabeludo é de verdade (miolo da peça, não o anel de fade da borda)
    for p in alvo:
        d = p - c
        d /= np.linalg.norm(d) + 1e-9
        origem = Vector(p + d * 0.12)
        ok, loc, nrm, idx, obj, mat = cena.ray_cast(dg, origem, Vector(-d))
        if not ok:
            continue
        if obj.name in nomes_cabelo:
            total += 1
            acertos += 1
        elif obj == corpo:
            total += 1
    if not total:
        return False, "nenhum raio acertou"
    frac = acertos / total
    return frac >= 0.97, f"{frac * 100:.1f}% dos raios acertam o cabelo"


def caminho_ok(p):
    return bool(p) and os.path.isfile(p)
