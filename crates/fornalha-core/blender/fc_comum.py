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


def material(nome, cor, rugosidade=0.7, metal=0.0, emissao=None):
    m = bpy.data.materials.get(nome)
    if m is not None:
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


def exportar_glb(caminho, selecionados=None, animacoes=True):
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
    else:
        mundo.color = (0.045, 0.04, 0.05)


def _luzes(centro, tamanho):
    for nome, energia, direcao, cor in (
        ("sol", 3.2, (-0.6, -0.8, 1.0), (1.0, 0.94, 0.86)),
        ("contra", 1.6, (0.8, 1.0, 0.7), (1.0, 0.62, 0.35)),
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


def video(caminho, objs, acoes, armadura, largura=400, altura=450, amostras=6):
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
