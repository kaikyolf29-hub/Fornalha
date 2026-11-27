# Fornalha: utilidades comuns dos scripts do Blender (Blender 4.2+ e 5.x).
# Rodam com: blender -b --factory-startup --python-exit-code 1 -P fornalha_main.py -- tarefa.json resultado.json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


def limpar_cena():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for colecao in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.actions, bpy.data.cameras, bpy.data.lights):
        for item in list(colecao):
            if item.users == 0:
                colecao.remove(item)
    cena = bpy.context.scene
    cena.render.fps = 30
    cena.frame_start = 1
    cena.unit_settings.system = "METRIC"
    cena.unit_settings.scale_length = 1.0


def cor_hex(h, padrao=(0.5, 0.5, 0.5)):
    try:
        h = h.strip().lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        # sRGB para linear (o Principled BSDF trabalha em linear)
        lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return (lin(r), lin(g), lin(b))
    except Exception:
        return padrao


# Com o pacote de materiais, os materiais da Forja viram PBR pelo nome (tingidos com a cor pedida).
PBR = {"ativo": False}
_PBR_POR_NOME = (
    (("caminho", "estrada", "calcada", "praca"), "calcamento"),
    (("telhado", "telha"), "telha"),
    (("parede", "pedra", "muro", "castelo", "masmorra", "arena", "poco", "torre"), "pedra"),
    (("rocha", "montanha", "penhasco"), "rocha"),
    (("grama",), "grama"),
    (("chao", "terra", "areia", "solo"), "terra"),
    (("casca", "tronco"), "casca"),
    (("reboco",), "reboco"),
    (("viga",), "viga"),
    (("madeira", "tabua", "cerca", "barril", "caixa", "bau", "porta", "cabo", "janela"), "madeira"),
    (("metal", "aco", "ferro", "lamina"), "aco"),
    (("couro",), "couro"),
    (("roupa", "tecido", "capa"), "tecido"),
)


def _hex_de_linear(cor):
    srgb = lambda c: 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return "#" + "".join(f"{int(max(0, min(1, srgb(x))) * 255):02x}" for x in cor[:3])


def material(nome, cor, rugosidade=0.7, metal=0.0, emissao=None):
    m = bpy.data.materials.get(nome)
    if m is not None:
        return m
    if PBR["ativo"] and emissao is None:
        import fc_pbr

        chave = nome.lower()
        tipo = next((t for palavras, t in _PBR_POR_NOME if any(p in chave for p in palavras)), None)
        if tipo and fc_pbr.disponivel(tipo):
            m = fc_pbr.material(nome, tipo, _hex_de_linear(cor), mistura_tom=0.55)
            m["uv_mundo"] = True
            return m
    m = bpy.data.materials.new(nome)
    try:
        m.use_nodes = True
    except Exception:
        pass
    m.diffuse_color = (*cor, 1.0)
    m.roughness = rugosidade
    m.metallic = metal
    arvore = getattr(m, "node_tree", None)
    if arvore is not None:
        bsdf = next((n for n in arvore.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*cor, 1.0)
            bsdf.inputs["Roughness"].default_value = rugosidade
            bsdf.inputs["Metallic"].default_value = metal
            if emissao is not None:
                for nome_entrada in ("Emission Color", "Emission"):
                    if nome_entrada in bsdf.inputs:
                        bsdf.inputs[nome_entrada].default_value = (*emissao, 1.0)
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 3.0
    return m


def matriz_entre(a, b):
    """Matriz que leva o eixo Z do primitivo para o segmento a→b (centrado no meio)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    comprimento = d.length
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()) if comprimento > 1e-6 else Quaternion()
    return Matrix.Translation((a + b) / 2) @ rot.to_matrix().to_4x4(), comprimento


class Construtor:
    """Junta primitivos numa malha só, guardando material e osso de cada parte."""

    def __init__(self):
        self.bm = bmesh.new()
        self.materiais = []
        self.ossos = {}  # nome do osso -> lista de BMVert

    def _mat(self, m):
        if m not in self.materiais:
            self.materiais.append(m)
        return self.materiais.index(m)

    def _registrar(self, verts, m, osso, liso=False):
        indice = self._mat(m)
        faces = set()
        for v in verts:
            faces.update(v.link_faces)
        for f in faces:
            f.material_index = indice
            f.smooth = liso
        if osso:
            self.ossos.setdefault(osso, []).extend(verts)
        return verts

    def caixa(self, centro, tamanho, m, osso=None, rot=None):
        M = Matrix.Translation(Vector(centro))
        if rot is not None:
            M = M @ rot.to_matrix().to_4x4()
        M = M @ Matrix.Diagonal((*tamanho, 1.0))
        r = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        return self._registrar(r["verts"], m, osso)

    def cilindro(self, a, b, r1, r2, m, osso=None, lados=8, liso=False):
        M, comp = matriz_entre(a, b)
        r = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=lados, radius1=r1, radius2=r2, depth=max(comp, 1e-4), matrix=M)
        return self._registrar(r["verts"], m, osso, liso)

    def cone(self, base, ponta, r, m, osso=None, lados=6):
        M, comp = matriz_entre(base, ponta)
        r_ = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=True, segments=lados, radius1=r, radius2=0.0, depth=max(comp, 1e-4), matrix=M)
        return self._registrar(r_["verts"], m, osso)

    def esfera(self, centro, raio, m, osso=None, escala=(1, 1, 1), u=12, v=8, liso=True, cortar_abaixo=None):
        M = Matrix.Translation(Vector(centro)) @ Matrix.Diagonal((*escala, 1.0))
        try:
            r = bmesh.ops.create_uvsphere(self.bm, u_segments=u, v_segments=v, radius=raio, matrix=M)
        except TypeError:
            r = bmesh.ops.create_uvsphere(self.bm, u_segments=u, v_segments=v, diameter=raio, matrix=M)
        verts = r["verts"]
        if cortar_abaixo is not None:
            fora = [x for x in verts if x.co.z < cortar_abaixo]
            bmesh.ops.delete(self.bm, geom=fora, context="VERTS")
            verts = [x for x in verts if x.is_valid]
        return self._registrar(verts, m, osso, liso)

    def objeto(self, nome, colecao=None):
        malha = bpy.data.meshes.new(nome)
        self.bm.normal_update()
        self.bm.verts.index_update()
        grupos = {osso: sorted({v.index for v in vs if v.is_valid}) for osso, vs in self.ossos.items()}
        self.bm.to_mesh(malha)
        self.bm.free()
        for m in self.materiais:
            malha.materials.append(m)
        obj = bpy.data.objects.new(nome, malha)
        (colecao or bpy.context.scene.collection).objects.link(obj)
        for osso, indices in grupos.items():
            g = obj.vertex_groups.new(name=osso)
            if indices:
                g.add(indices, 1.0, "REPLACE")
        return obj


def uv_mundo(objs, escala=1.0):
    """UV em metros do mundo (projeção pela face dominante): a textura não estica em peça grande."""
    for o in objs:
        if o.type != "MESH" or not any(ms.material and ms.material.get("uv_mundo") for ms in o.material_slots):
            continue
        me = o.data
        uv = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
        mw = o.matrix_world
        rot = mw.to_3x3()
        for p in me.polygons:
            n = (rot @ p.normal).normalized()
            ax = max(range(3), key=lambda i: abs(n[i]))
            for li in p.loop_indices:
                co = mw @ me.vertices[me.loops[li].vertex_index].co
                if ax == 0:
                    u, v = co.y, co.z
                elif ax == 1:
                    u, v = co.x, co.z
                else:
                    u, v = co.x, co.y
                uv.data[li].uv = (u * escala, v * escala)


def triangulos(objs):
    total = 0
    deps = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(deps)
        malha = ev.to_mesh()
        malha.calc_loop_triangles()
        total += len(malha.loop_triangles)
        ev.to_mesh_clear()
    return total


def caixa_envolvente(objs):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(deps)
        malha = ev.to_mesh()
        mw = o.matrix_world
        pts.extend(mw @ v.co for v in malha.vertices)
        ev.to_mesh_clear()
    if not pts:
        return Vector((0, 0, 0)), Vector((1, 1, 1))
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def tirar_ajudantes_do_gltf():
    """O importador de glTF do Blender cria uma esfera de 1 m para desenhar os ossos (coleção
    glTF_not_exported). Ela não é do modelo: entrava na conta do enquadramento (a comparação saía com o
    personagem pequeno) e podia entrar numa junção de malhas. Sai logo depois de importar."""
    col = bpy.data.collections.get("glTF_not_exported")
    if col is None:
        return
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(col)


def exportar_glb(caminho, selecionados=None, animacoes=True, imagens=None):
    if PBR["ativo"]:
        uv_mundo(selecionados if selecionados is not None else list(bpy.context.scene.objects))
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    if selecionados is not None:
        for o in bpy.context.scene.objects:
            o.select_set(o in selecionados)
    opcoes = dict(
        filepath=caminho,
        export_format="GLB",
        use_selection=selecionados is not None,
        export_apply=True,
        export_yup=True,
        export_animations=animacoes,
        export_animation_mode="ACTIONS",
        export_skins=True,
        export_morph=False,
        export_extras=True,
        export_force_sampling=True,
        export_optimize_animation_size=False,
    )
    if imagens:
        opcoes["export_image_format"] = imagens  # "JPEG": arquivo bem menor (mundo, vegetação)
    objs = selecionados if selecionados is not None else list(bpy.context.scene.objects)
    if any(o.type == "MESH" and o.get("fornalha_fios") for o in objs):
        # cabelo fio a fio: as arestas soltas viram LINES no glTF (o nome da opção mudou no Blender 4.x).
        # Nas outras malhas, aresta solta é sobra invisível: sai, para não virar linha na engine
        opcoes["use_mesh_edges"] = True
        opcoes["export_loose_edges"] = True
        for o in objs:
            if o.type == "MESH" and not o.get("fornalha_fios") and o.data.users == 1:
                bm = bmesh.new()
                bm.from_mesh(o.data)
                soltas = [e for e in bm.edges if not e.link_faces]
                if soltas:
                    bmesh.ops.delete(bm, geom=soltas, context="EDGES")
                    bm.to_mesh(o.data)
                bm.free()
    # Algumas opções mudam de nome entre versões: tira a que o exportador não conhece e tenta de novo.
    for _ in range(len(opcoes)):
        try:
            bpy.ops.export_scene.gltf(**opcoes)
            return os.path.getsize(caminho)
        except TypeError as e:
            texto = str(e)
            ruim = next((k for k in list(opcoes) if k != "filepath" and f'"{k}"' in texto), None)
            if ruim is None:
                raise
            opcoes.pop(ruim)
    raise RuntimeError("não consegui exportar o glTF")


# ---------------- prévia (render) ----------------

CEU = {"hdri": None, "forca": 2.2}


def definir_ceu(caminho, forca=2.2):
    CEU["hdri"] = caminho if caminho and os.path.isfile(caminho) else None
    CEU["forca"] = forca


def _preparar_render(largura, altura, amostras=24):
    cena = bpy.context.scene
    cena.render.engine = "CYCLES"
    cena.cycles.device = "CPU"
    cena.cycles.samples = amostras
    try:
        cena.cycles.use_denoising = True
    except Exception:
        pass
    cena.render.resolution_x = largura
    cena.render.resolution_y = altura
    cena.render.resolution_percentage = 100
    cena.render.film_transparent = False
    cena.render.image_settings.file_format = "PNG"
    try:
        cena.view_settings.view_transform = "AgX"
        cena.view_settings.look = "AgX - Medium High Contrast"
        cena.view_settings.exposure = 0.35
    except Exception:
        pass
    mundo = cena.world or bpy.data.worlds.new("mundo")
    cena.world = mundo
    try:
        mundo.use_nodes = True
    except Exception:
        pass
    arv = getattr(mundo, "node_tree", None)
    if arv is not None:
        fundo = next((n for n in arv.nodes if n.type == "BACKGROUND"), None)
        if fundo is not None:
            fundo.inputs[0].default_value = (0.045, 0.04, 0.05, 1.0)
            fundo.inputs[1].default_value = 1.0
            if CEU["hdri"] and not arv.nodes.get("ceu_hdri"):
                # o céu ilumina e reflete nos metais; a câmera continua vendo o fundo escuro
                env = arv.nodes.new("ShaderNodeTexEnvironment")
                env.name = "ceu_hdri"
                env.image = bpy.data.images.load(CEU["hdri"], check_existing=True)
                luz = arv.nodes.new("ShaderNodeBackground")
                luz.inputs[1].default_value = CEU["forca"]
                arv.links.new(env.outputs["Color"], luz.inputs["Color"])
                caminho_luz = arv.nodes.new("ShaderNodeLightPath")
                mistura = arv.nodes.new("ShaderNodeMixShader")
                saida = next(n for n in arv.nodes if n.type == "OUTPUT_WORLD")
                arv.links.new(caminho_luz.outputs["Is Camera Ray"], mistura.inputs[0])
                arv.links.new(luz.outputs["Background"], mistura.inputs[1])
                arv.links.new(fundo.outputs["Background"], mistura.inputs[2])
                arv.links.new(mistura.outputs["Shader"], saida.inputs["Surface"])
            elif not CEU["hdri"] and not arv.nodes.get("estudio_reflexo"):
                # sem céu HDRI, o metal refletia só o fundo escuro e saía preto (a foto de referência é
                # de estúdio): os reflexos veem um estúdio cinza, claro em cima e escuro embaixo; a
                # câmera e a luz difusa continuam como antes
                coord = arv.nodes.new("ShaderNodeTexCoord")
                sep = arv.nodes.new("ShaderNodeSeparateXYZ")
                faixa = arv.nodes.new("ShaderNodeMapRange")
                faixa.inputs["From Min"].default_value = -0.6
                faixa.inputs["From Max"].default_value = 0.9
                faixa.inputs["To Min"].default_value = 0.05
                faixa.inputs["To Max"].default_value = 0.75
                estudio = arv.nodes.new("ShaderNodeBackground")
                estudio.name = "estudio_reflexo"
                arv.links.new(coord.outputs["Generated"], sep.inputs[0])
                arv.links.new(sep.outputs["Z"], faixa.inputs["Value"])
                arv.links.new(faixa.outputs["Result"], estudio.inputs["Color"])
                caminho_luz = arv.nodes.new("ShaderNodeLightPath")
                mistura = arv.nodes.new("ShaderNodeMixShader")
                saida = next(n for n in arv.nodes if n.type == "OUTPUT_WORLD")
                arv.links.new(caminho_luz.outputs["Is Glossy Ray"], mistura.inputs[0])
                arv.links.new(fundo.outputs["Background"], mistura.inputs[1])
                arv.links.new(estudio.outputs["Background"], mistura.inputs[2])
                arv.links.new(mistura.outputs["Shader"], saida.inputs["Surface"])
    else:
        mundo.color = (0.045, 0.04, 0.05)


def _luzes(centro, tamanho):
    for nome, energia, direcao, cor in (
        ("sol", 4.2, (-0.6, -0.8, 1.0), (1.0, 0.95, 0.9)),
        ("contra", 1.4, (0.8, 1.0, 0.7), (0.92, 0.86, 0.8)),
    ):
        luz = bpy.data.lights.new(nome, "SUN")
        luz.energy = energia
        luz.color = cor
        luz.angle = math.radians(8)
        o = bpy.data.objects.new(nome, luz)
        bpy.context.scene.collection.objects.link(o)
        o.rotation_euler = Vector(direcao).to_track_quat("Z", "Y").to_euler()
    fill = bpy.data.lights.new("preenchimento", "AREA")
    fill.energy = 60.0 * max(tamanho, 1.0) ** 2
    fill.size = max(tamanho, 1.0) * 2
    o = bpy.data.objects.new("preenchimento", fill)
    bpy.context.scene.collection.objects.link(o)
    o.location = centro + Vector((-tamanho * 2.5, -tamanho * 2.5, tamanho * 1.5))
    o.rotation_euler = (centro - o.location).to_track_quat("-Z", "Y").to_euler()


def _camera(nome="camera"):
    cam = bpy.data.cameras.new(nome)
    cam.lens = 50
    o = bpy.data.objects.new(nome, cam)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.scene.camera = o
    return o


def enquadrar(cam, mn, mx, direcao, margem=1.25, orto=False):
    centro = (mn + mx) / 2
    tamanho = (mx - mn).length
    d = Vector(direcao).normalized()
    if orto:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z) * margem
        distancia = tamanho * 2
    else:
        cam.data.type = "PERSP"
        meia = math.atan(cam.data.sensor_width / (2 * cam.data.lens))
        distancia = (tamanho / 2) * margem / math.tan(meia)
    cam.location = centro + d * distancia
    cam.rotation_euler = (centro - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = distancia * 4 + tamanho * 4
    return centro


def renderizar(caminho, objs, direcao=(-0.55, -1.0, 0.45), largura=640, altura=720, amostras=24, orto=False, chao=True):
    _preparar_render(largura, altura, amostras)
    mn, mx = caixa_envolvente(objs)
    centro = (mn + mx) / 2
    tamanho = (mx - mn).length
    if not bpy.data.objects.get("sol"):
        _luzes(centro, tamanho)
    if chao and not bpy.data.objects.get("chao_previa"):
        bpy.ops.mesh.primitive_plane_add(size=tamanho * 8, location=(centro.x, centro.y, mn.z - 0.001))
        p = bpy.context.active_object
        p.name = "chao_previa"
        p.data.materials.append(material("chao_previa", (0.09, 0.08, 0.085), 0.9))
    cam = bpy.context.scene.camera or _camera()
    enquadrar(cam, mn, mx, direcao, orto=orto)
    bpy.context.scene.render.filepath = caminho
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return caminho


def folha_de_modelo(caminho, objs, largura=420, altura=640, amostras=20):
    """Frente, lado e costas lado a lado numa imagem só."""
    import numpy as np

    partes = []
    tmp = caminho + ".tmp"
    for i, d in enumerate(((0, -1, 0.12), (1, 0, 0.12), (0, 1, 0.12))):
        arq = f"{tmp}{i}.png"
        renderizar(arq, objs, direcao=d, largura=largura, altura=altura, amostras=amostras)
        img = bpy.data.images.load(arq)
        px = np.empty(largura * altura * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        partes.append(px.reshape(altura, largura, 4))
        bpy.data.images.remove(img)
        os.remove(arq)
    junta = np.concatenate(partes, axis=1)
    final = bpy.data.images.new("folha", width=largura * 3, height=altura, alpha=True)
    final.pixels.foreach_set(junta.ravel())
    final.filepath_raw = caminho
    final.file_format = "PNG"
    final.save()
    return caminho


def video(caminho, objs, acoes, armadura, largura=640, altura=720, amostras=14):
    """Vídeo curto das animações (MP4 pelo ffmpeg que vem no Blender)."""
    cena = bpy.context.scene
    _preparar_render(largura, altura, amostras)
    mn, mx = caixa_envolvente(objs)
    cam = cena.camera or _camera()
    enquadrar(cam, mn - Vector((0.3, 0.3, 0)), mx + Vector((0.3, 0.3, 0.2)), (-0.7, -1.0, 0.35))
    s = cena.render.image_settings
    try:
        s.media_type = "VIDEO"
    except Exception:
        pass
    s.file_format = "FFMPEG"
    cena.render.ffmpeg.format = "MPEG4"
    cena.render.ffmpeg.codec = "H264"
    cena.render.ffmpeg.constant_rate_factor = "MEDIUM"
    # As ações uma depois da outra na NLA, só para o vídeo.
    ad = armadura.animation_data or armadura.animation_data_create()
    ad.action = None
    trilha = ad.nla_tracks.new()
    inicio = 1
    for a in acoes:
        tira = trilha.strips.new(a.name, inicio, a)
        inicio = int(tira.frame_end) + 1
    cena.frame_start, cena.frame_end = 1, inicio - 1
    cena.render.filepath = caminho
    bpy.ops.render.render(animation=True)
    ad.nla_tracks.remove(trilha)
    try:
        s.media_type = "IMAGE"
    except Exception:
        pass
    s.file_format = "PNG"
    return caminho


def retrato(caminho, centro, largura=900, altura=1100, amostras=64, distancia=0.85, lente=85):
    """Close de estúdio (rosto ou objeto): luz principal suave, recorte e fundo escuro."""
    _preparar_render(largura, altura, amostras)
    centro = Vector(centro)
    # luz de estúdio de retrato (chave suave de lado, recorte atrás, quase nada de preenchimento)
    for nome, energia, pos, tamanho, cor in (
        ("chave_retrato", 38.0, (-1.0, -0.75, 0.55), 0.7, (1.0, 0.94, 0.88)),
        ("recorte_retrato", 45.0, (0.85, 0.8, 0.35), 0.35, (1.0, 0.86, 0.74)),
        ("preench_retrato", 3.0, (0.9, -1.0, -0.15), 1.4, (0.7, 0.8, 1.0)),
    ):
        if bpy.data.objects.get(nome):
            continue
        luz = bpy.data.lights.new(nome, "AREA")
        luz.energy = energia
        luz.size = tamanho
        luz.color = cor
        o = bpy.data.objects.new(nome, luz)
        bpy.context.scene.collection.objects.link(o)
        o.location = centro + Vector(pos)
        o.rotation_euler = (centro - o.location).to_track_quat("-Z", "Y").to_euler()
    for nome in ("sol", "contra", "preenchimento"):
        o = bpy.data.objects.get(nome)
        if o:
            o.hide_render = True
    chao = bpy.data.objects.get("chao_previa")
    if chao:
        chao.hide_render = True
    exposicao = bpy.context.scene.view_settings.exposure
    bpy.context.scene.view_settings.exposure = 0.0
    mundo = bpy.context.scene.world
    forca_ceu = None
    if mundo and mundo.node_tree and "Background" in mundo.node_tree.nodes:
        fundo = mundo.node_tree.nodes["Background"]
        forca_ceu = fundo.inputs["Strength"].default_value
        fundo.inputs["Strength"].default_value = forca_ceu * 0.25
    cam = bpy.context.scene.camera or _camera()
    cam.data.type = "PERSP"
    cam.data.lens = lente
    cam.location = centro + Vector((-0.22, -1.0, 0.02)).normalized() * distancia
    cam.rotation_euler = (centro - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = 0.01
    bpy.context.scene.render.filepath = caminho
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    for nome in ("sol", "contra", "preenchimento"):
        o = bpy.data.objects.get(nome)
        if o:
            o.hide_render = False
    if chao:
        chao.hide_render = False
    bpy.context.scene.view_settings.exposure = exposicao
    if forca_ceu is not None:
        mundo.node_tree.nodes["Background"].inputs["Strength"].default_value = forca_ceu
    cam.data.lens = 50
    return caminho
