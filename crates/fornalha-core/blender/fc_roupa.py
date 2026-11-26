# Fornalha: roupas e armaduras medievais feitas sobre o corpo do MakeHuman.
# Cada peça é uma "casca" tirada das regiões do corpo (pelos pesos dos ossos),
# afastada da pele, com espessura e material PBR; herda os pesos do corpo, então
# acompanha as animações. Elmo, ombreiras, cinto e capa são modelados aqui.
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import fc_comum as c
import fc_pbr

TRONCO = ["pelvis", "spine_01", "spine_02", "spine_03"]
BRACOS = ["clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r"]
MAOS = [f"{d}_{n}_{l}" for l in "lr" for d in ("index", "middle", "ring", "pinky", "thumb") for n in ("01", "02", "03")] + ["hand_l", "hand_r"]
PERNAS = ["thigh_l", "thigh_r", "calf_l", "calf_r"]
PES = ["foot_l", "foot_r", "ball_l", "ball_r"]


class Alfaiate:
    def __init__(self, h, prefixo):
        self.h = h
        self.prefixo = prefixo
        n = len(h.coords)
        self.W = {}
        for osso, lista in h.pesos.items():
            arr = np.zeros(n)
            for vi, w in lista:
                if vi < n:
                    arr[int(vi)] = w
            self.W[osso] = arr
        self.cobertos = set()
        self.pecas = []
        self.pano = False  # caimento simulado (fc_pano) nas peças soltas
        self.faces_corpo = [h.faces[i] for i in h.grupos["body"]]

    def soma(self, ossos):
        s = np.zeros(len(self.h.coords))
        for o in ossos:
            if o in self.W:
                s += self.W[o]
        return s

    def _objeto(self, nome, vs, faces, uvs, material):
        h = self.h
        novo = {v: i for i, v in enumerate(vs)}
        malha = bpy.data.meshes.new(nome)
        malha.from_pydata(h.coords[vs].tolist(), [], [[novo[v] for v in f] for f in faces])
        if uvs is not None:
            uv = malha.uv_layers.new(name="UVMap")
            k = 0
            for f in uvs:
                for t in f:
                    uv.data[k].uv = h.vt[t] if t >= 0 else (0.0, 0.0)
                    k += 1
        malha.validate()
        obj = bpy.data.objects.new(nome, malha)
        bpy.context.scene.collection.objects.link(obj)
        for osso, arr in self.W.items():
            sel = [(novo[v], arr[v]) for v in vs if arr[v] > 1e-4]
            if sel:
                g = obj.vertex_groups.new(name=osso)
                for i, w in sel:
                    g.add([i], float(w), "REPLACE")
        obj.data.materials.append(material)
        return obj

    def casca(self, nome, ossos, folga, espessura, material, limiar=0.5, filtro=None, grupos_extra=(), cobrir=0.85, subdividir=0,
              suavizar=0, filtro_extra=None, preparo=None):
        """Peça que veste as regiões dos ossos. filtro(centro_xyz) escolhe parte da região."""
        h = self.h
        s = self.soma(ossos)
        faces, uvs = [], []
        for vi, ti in self.faces_corpo:
            if s[vi].mean() >= limiar:
                centro = h.coords[vi].mean(axis=0)
                if filtro is None or filtro(centro):
                    faces.append(vi)
                    uvs.append(ti)
        for g in grupos_extra:
            for fi in h.grupos.get(g, []):
                vi = h.faces[fi][0]
                if filtro_extra is None or filtro_extra(h.coords[vi].mean(axis=0)):
                    faces.append(vi)
                    uvs.append(h.faces[fi][1])
        if not faces:
            return None
        vs = sorted({v for f in faces for v in f})
        obj = self._objeto(f"{self.prefixo}_{nome}", vs, faces, uvs, material)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * folga
        bm.to_mesh(obj.data)
        bm.free()
        for p in obj.data.polygons:
            p.use_smooth = True
        if suavizar:
            bpy.context.view_layer.objects.active = obj
            for o in bpy.context.scene.objects:
                o.select_set(o == obj)
            m = obj.modifiers.new("caimento", "SMOOTH")
            m.factor = 0.9
            m.iterations = suavizar
            bpy.ops.object.modifier_apply(modifier=m.name)
        if preparo:
            preparo(obj)
        self._aplicar(obj, espessura, subdividir)
        self._vestir(obj)
        if cobrir:
            cob = s >= cobrir
            for v in vs:
                if cob[v] and (filtro is None or filtro(h.coords[v])):
                    self.cobertos.add(v)
        return obj

    def _aplicar(self, obj, espessura, subdividir=0):
        bpy.context.view_layer.objects.active = obj
        for o in bpy.context.scene.objects:
            o.select_set(o == obj)
        if subdividir:
            m = obj.modifiers.new("sub", "SUBSURF")
            m.levels = subdividir
            m.render_levels = subdividir
            bpy.ops.object.modifier_apply(modifier=m.name)
        if espessura > 0:
            m = obj.modifiers.new("espessura", "SOLIDIFY")
            m.thickness = espessura
            m.offset = 1.0
            m.use_even_offset = False
            m.use_quality_normals = True
            m.thickness_clamp = 1.0
            bpy.ops.object.modifier_apply(modifier=m.name)
        m = obj.modifiers.new("borda", "WEIGHTED_NORMAL")
        m.keep_sharp = True
        bpy.ops.object.modifier_apply(modifier=m.name)

    def _vestir(self, obj):
        normalizar_pesos(obj, self.h.arm)
        mod = obj.modifiers.new("esqueleto", "ARMATURE")
        mod.object = self.h.arm
        obj.parent = self.h.arm
        self.pecas.append(obj)

    def _peso_fixo(self, obj, pesos):
        for osso, w in pesos.items():
            g = obj.vertex_groups.get(osso) or obj.vertex_groups.new(name=osso)
            g.add(list(range(len(obj.data.vertices))), w, "REPLACE")

    def ossos(self, nome):
        return self.h.arm.data.bones[nome]

    def estampa(self, base, nome, filtro, material, afastar=0.0018, cortes=3, plano=None):
        """Desenho costurado/pintado por cima de uma peça (cruz, brasão): copia a face de FORA da peça
        onde o desenho cai, subdivide, recorta fino pelo filtro, alisa o contorno e afasta 1-2 mm.
        plano=(aba, uv->(x, z)): recorta pela posição do pano antes do caimento (só nas faces da aba
        marcada), e o desenho acompanha as dobras."""
        import fc_armadura

        bm = bmesh.new()
        bm.from_mesh(base.data)
        bm.normal_update()
        camada_aba = bm.faces.layers.int.get("aba") if plano else None
        camada_uv = bm.loops.layers.uv.active

        def posicao(f):
            c = f.calc_center_median()
            if plano is None:
                return (c.x, c.y, c.z)
            if camada_aba is None or camada_uv is None or f[camada_aba] != plano[0]:
                return None
            u = sum(lp[camada_uv].uv.x for lp in f.loops) / len(f.loops)
            v = sum(lp[camada_uv].uv.y for lp in f.loops) / len(f.loops)
            x, z = plano[1](u, v)
            return (x, -1.0, z)  # na frente plana (y negativo = frente)

        centro = Vector(np.mean([v.co[:] for v in bm.verts], axis=0)) if bm.verts else Vector()
        fora = []
        for f in bm.faces:
            c = f.calc_center_median()
            radial = Vector((c.x - centro.x, c.y - centro.y, 0))
            pos = posicao(f)
            if pos is not None and f.normal.dot(radial) > 0 and filtro(pos, folga=0.03):
                fora.append(f)
        apagar = [f for f in bm.faces if f not in set(fora)]
        bmesh.ops.delete(bm, geom=apagar, context="FACES")
        # só a camada de fora (a de dentro do pano tem normal para dentro e já saiu); subdivide e recorta
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cortes, use_grid_fill=True)
        bm.faces.ensure_lookup_table()
        fora_fino = [f for f in bm.faces if posicao(f) is None or not filtro(posicao(f), folga=0.0)]
        bmesh.ops.delete(bm, geom=fora_fino, context="FACES")
        soltos = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=soltos, context="VERTS")
        if not bm.faces:
            bm.free()
            print(f"[roupa] estampa {nome}: nenhuma face da peça sob o desenho")
            return None
        malha = bpy.data.meshes.new(f"{self.prefixo}_{nome}")
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        for g in base.vertex_groups:
            obj.vertex_groups.new(name=g.name)
        # pesos: copia do vértice mais perto da peça base
        from mathutils.kdtree import KDTree

        kd = KDTree(len(base.data.vertices))
        for v in base.data.vertices:
            kd.insert(v.co, v.index)
        kd.balance()
        nomes = {g.index: g.name for g in base.vertex_groups}
        for v in malha.vertices:
            _, i, _ = kd.find(v.co)
            for ge in base.data.vertices[i].groups:
                obj.vertex_groups[nomes[ge.group]].add([v.index], ge.weight, "REPLACE")
        fc_armadura.limpar_dentes(obj)
        fc_armadura.alisar_borda(obj, iteracoes=10)
        bm = bmesh.new()
        bm.from_mesh(malha)
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * afastar
        bm.to_mesh(malha)
        bm.free()
        for p_ in malha.polygons:
            p_.use_smooth = True
        obj.data.materials.append(material)
        self._uv(obj)
        self._vestir(obj)
        return obj

    def alongar_barra(self, obj, comprimento, bico=0.55, abrir=0.04, abaixo_de=None, passos=1):
        """Estica a barra da saia/sobreveste para baixo (com bico no meio e abrindo um pouco).
        `passos` > 1 faz a extensão em várias fileiras (resolução para o caimento simulado)."""
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bordas = [e for e in bm.edges if e.is_boundary and all(abaixo_de is None or v.co.z < abaixo_de for v in e.verts)]
        if not bordas:
            bm.free()
            return
        origem = {v: v.co.copy() for e in bordas for v in e.verts}  # vértice da ponta -> posição na barra original
        cx = np.mean([c.x for c in origem.values()])
        cy = np.mean([c.y for c in origem.values()])
        for k in range(1, passos + 1):
            res = bmesh.ops.extrude_edge_only(bm, edges=bordas)
            novos = {g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)}
            bordas = [g for g in res["geom"] if isinstance(g, bmesh.types.BMEdge) and all(v in novos for v in g.verts)]
            f = k / passos
            proximo = {}
            for v in novos:
                ant = next((e.other_vert(v) for e in v.link_edges if e.other_vert(v) in origem), None)
                if ant is None:
                    continue
                o = origem[ant]
                proximo[v] = o
                dx = abs(o.x - cx)
                L = max(0.05, comprimento - bico * max(0.0, dx - 0.02) ** 1.2)
                radial = Vector((o.x - cx, o.y - cy, 0))
                v.co = o - Vector((0, 0, L * f))
                if radial.length > 1e-6:
                    v.co += radial.normalized() * abrir * (L / comprimento) * f
            origem = proximo
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

    # -------------------------------------------------- peças modeladas

    def elmo(self, material, tipo="grande"):
        h = self.h
        cab = self.W.get("head")
        idx = np.nonzero(cab >= 0.9)[0] if cab is not None else []
        pts = h.coords[idx]
        mn, mx = pts.min(axis=0), pts.max(axis=0)
        centro = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
        raio = max(mx[0] - mn[0], mx[1] - mn[1]) / 2 + 0.022
        base_z = mn[2] - 0.035
        topo_z = mx[2] + 0.02
        bm = bmesh.new()
        lados, aneis = 28, 10
        anel_ant = None
        for k in range(aneis + 1):
            t = k / aneis
            z = base_z + (topo_z - base_z) * t
            # cilindro que fecha em cúpula no último terço
            fech = 1.0 if t < 0.66 else math.cos((t - 0.66) / 0.34 * math.pi / 2) ** 0.6
            r = raio * (1.04 - 0.06 * t) * max(fech, 0.05)
            anel = []
            for i in range(lados):
                a = 2 * math.pi * i / lados
                anel.append(bm.verts.new((centro.x + r * math.sin(a), centro.y - r * math.cos(a) * 1.08, z)))
            if anel_ant:
                for i in range(lados):
                    j = (i + 1) % lados
                    bm.faces.new((anel_ant[i], anel_ant[j], anel[j], anel[i]))
            anel_ant = anel
        bm.faces.new(list(reversed(anel_ant)))
        # fenda dos olhos na frente
        olhos_z = centro.z + 0.015
        apagar = [f for f in bm.faces if abs(f.calc_center_median().z - olhos_z) < 0.012 and f.calc_center_median().y < centro.y - raio * 0.55]
        bmesh.ops.delete(bm, geom=apagar, context="FACES")
        malha = bpy.data.meshes.new(f"{self.prefixo}_elmo")
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        for p in malha.polygons:
            p.use_smooth = True
        obj.data.materials.append(material)
        self._uv(obj)
        self._aplicar(obj, 0.004)
        self._peso_fixo(obj, {"head": 1.0})
        self._vestir(obj)
        return obj

    def ombreiras(self, material):
        objs = []
        for lado, s in (("l", 1), ("r", -1)):
            b = self.ossos(f"upperarm_{lado}")
            topo = b.head_local + Vector((s * 0.015, 0, 0.035))
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.085, location=topo)
            o = bpy.context.active_object
            o.name = f"{self.prefixo}_ombreira_{lado}"
            o.scale = (1.15, 1.05, 0.62)
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.15], context="VERTS")
            bm.to_mesh(o.data)
            bm.free()
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            for p in o.data.polygons:
                p.use_smooth = True
            o.data.materials.append(material)
            self._uv(o)
            self._aplicar(o, 0.005)
            self._peso_fixo(o, {f"upperarm_{lado}": 0.7, f"clavicle_{lado}": 0.3})
            self._vestir(o)
            objs.append(o)
        return objs

    def capa(self, material, comprimento=0.95):
        h = self.h
        ombro_l = self.ossos("upperarm_l").head_local
        ombro_r = self.ossos("upperarm_r").head_local
        pesc = self.ossos("neck_01").head_local
        largura = (ombro_l - ombro_r).length * 1.25
        topo_z = pesc.z - 0.02
        costas_y = max(h.coords[self.soma(["spine_03"]) > 0.6][:, 1]) + 0.03
        nx, nz = (40, 56) if self.pano else (22, 30)
        bm = bmesh.new()
        grade = []
        rng = np.random.default_rng(3)
        fases = rng.uniform(0, 2 * math.pi, 3)
        largura_topo = (ombro_l - ombro_r).length * 0.95
        for k in range(nz + 1):
            t = k / nz
            z = topo_z - comprimento * t
            larg = largura_topo + (largura - largura_topo) * min(1.0, t * 1.6)
            linha = []
            for i in range(nx + 1):
                u = i / nx - 0.5
                x = u * larg
                # envolve as costas no alto e cai reta embaixo
                curva = (u * 2) ** 2 * 0.11 * (1 - t) ** 1.5
                pregas = sum(math.sin(u * math.pi * (7 + 2 * j) + fases[j]) for j in range(3)) / 3
                dobra = pregas * (0.012 if self.pano else 0.028) * t ** 0.8
                y = costas_y + (0.1 if self.pano else 0.16) * t ** 1.2 + dobra - curva
                linha.append(bm.verts.new((x, y, z)))
            grade.append(linha)
        for k in range(nz):
            for i in range(nx):
                bm.faces.new((grade[k][i], grade[k][i + 1], grade[k + 1][i + 1], grade[k + 1][i]))
        malha = bpy.data.meshes.new(f"{self.prefixo}_capa")
        bm.to_mesh(malha)
        bm.free()
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        for p in malha.polygons:
            p.use_smooth = True
        uv = obj.data.uv_layers.new(name="UVMap")
        for poly in obj.data.polygons:
            for li in poly.loop_indices:
                co = obj.data.vertices[obj.data.loops[li].vertex_index].co
                uv.data[li].uv = ((co.x / largura) + 0.5, (co.z - topo_z) / comprimento + 1)
        obj.data.materials.append(material)
        # ossos da capa (a engine simula com mola: a capa balança ao andar e virar)
        arm = self.h.arm
        n_ossos = 4
        bpy.context.view_layer.objects.active = arm
        for o in bpy.context.scene.objects:
            o.select_set(o == arm)
        bpy.ops.object.mode_set(mode="EDIT")
        pai = arm.data.edit_bones["spine_03"]
        for k in range(n_ossos):
            eb = arm.data.edit_bones.new(f"capa_{k + 1}")
            z0 = topo_z - comprimento * k / n_ossos
            z1 = topo_z - comprimento * (k + 1) / n_ossos
            eb.head = Vector((0, costas_y + 0.16 * (k / n_ossos) ** 1.2, z0))
            eb.tail = Vector((0, costas_y + 0.16 * ((k + 1) / n_ossos) ** 1.2, z1))
            eb.parent = pai
            eb.use_connect = k > 0
            pai = eb
        bpy.ops.object.mode_set(mode="OBJECT")
        grupos = [obj.vertex_groups.new(name=f"capa_{k + 1}") for k in range(n_ossos)]
        topo = obj.vertex_groups.new(name="spine_03")
        for v in obj.data.vertices:
            t = min(1.0, max(0.0, (topo_z - v.co.z) / comprimento)) * n_ossos
            if t < 0.35:
                topo.add([v.index], 1.0 - t / 0.35, "REPLACE")
            k = min(n_ossos - 1, int(t))
            f = t - k
            grupos[k].add([v.index], 1.0 - f * 0.5, "REPLACE")
            if k + 1 < n_ossos:
                grupos[k + 1].add([v.index], f * 0.5, "REPLACE")
        if self.pano:
            # a capa cai de verdade pelas costas, por cima da roupa e da armadura
            import fc_pano

            fc_pano.capa_caindo(obj, topo_z, [self.h.obj] + list(self.pecas))
        self._aplicar(obj, 0.003)
        self._vestir(obj)
        return obj

    def _uv(self, obj):
        bpy.context.view_layer.objects.active = obj
        for o in bpy.context.scene.objects:
            o.select_set(o == obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01)
        bpy.ops.object.mode_set(mode="OBJECT")

    def esconder_corpo(self):
        self.h.esconder_sob_roupa(sorted(self.cobertos))


# peças de tecido (ganham sujeira/lama assada no nível de qualidade); couro e metal têm o caminho deles
PECAS_DE_PANO = ("_sobreveste", "_capa", "_gibao", "_tunica", "_calcas_pano", "_manto", "_vestido", "_saia", "_capuz", "_camisa", "_jaqueta")


def normalizar_pesos(obj, arm):
    """Pesos de osso de cada vértice somando 1 (a capa e as peças com dois ossos somavam mais ou menos)."""
    ossos = {b.name for b in arm.data.bones}
    grupos = {g.index: g for g in obj.vertex_groups if g.name in ossos}
    for v in obj.data.vertices:
        ws = [(grupos[e.group], e.weight) for e in v.groups if e.group in grupos and e.weight > 0]
        total = sum(w for _, w in ws)
        if total > 0 and abs(total - 1.0) > 1e-3:
            for g, w in ws:
                g.add([v.index], w / total, "REPLACE")


def _fivela(a, nome, centro, material, pesos, larg=0.05, alt=0.042, prof=0.006, aro=0.007):
    """Fivela de metal (moldura com a lingueta), de frente para -Y, presa aos ossos."""
    bm = bmesh.new()
    fora = [(-larg / 2, -alt / 2), (larg / 2, -alt / 2), (larg / 2, alt / 2), (-larg / 2, alt / 2)]
    dentro = [(x - math.copysign(aro, x), z - math.copysign(aro, z)) for x, z in fora]
    vf = [bm.verts.new((centro.x + x, centro.y, centro.z + z)) for x, z in fora]
    vd = [bm.verts.new((centro.x + x, centro.y, centro.z + z)) for x, z in dentro]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((vf[i], vf[j], vd[j], vd[i]))
    # lingueta no meio
    q = [(-0.0018, -alt / 2 + aro), (0.0018, -alt / 2 + aro), (0.0018, alt / 2 - aro * 0.3), (-0.0018, alt / 2 - aro * 0.3)]
    bm.faces.new([bm.verts.new((centro.x + x, centro.y - 0.002, centro.z + z)) for x, z in q])
    ext = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    for v in [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.y -= prof
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    malha = bpy.data.meshes.new(f"{a.prefixo}_{nome}")
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(malha.name, malha)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bev = obj.modifiers.new("borda", "BEVEL")
    bev.width = 0.0012
    bev.segments = 2
    bpy.ops.object.modifier_apply(modifier=bev.name)
    for p_ in malha.polygons:
        p_.use_smooth = True
    obj.data.materials.append(material)
    a._uv(obj)
    a._peso_fixo(obj, pesos)
    a._vestir(obj)
    return obj


def _frente_do_corpo(a, z, ossos=TRONCO, folga=0.0):
    """Ponto da frente do corpo (menor y) na altura z, no meio."""
    h = a.h
    s = a.soma(ossos)
    sel = (s > 0.4) & (np.abs(h.coords[:, 2] - z) < 0.02) & (np.abs(h.coords[:, 0]) < 0.04)
    if not sel.any():
        return Vector((0, -0.12, z))
    y = float(h.coords[sel][:, 1].min())
    return Vector((0, y - folga, z))



def _mat(nome, tipo, tom=None, escala=None, rugosidade_extra=0.0):
    return fc_pbr.material(nome, tipo, tom, escala, rugosidade_extra=rugosidade_extra)


def vestir(h, prefixo, estilo, cores, capa=True, pano=False, sujo=False):
    """estilo: cavaleiro, soldado, campones, nobre, mercenario, jaqueta (moderno). cores: principal, secundaria, detalhe.
    pano: caimento simulado (sobreveste franzida no cinto, capa caindo pelas costas)."""
    a = Alfaiate(h, prefixo)
    a.pano = bool(pano)
    p = cores.get("principal") or "#8a1f1a"
    sec = cores.get("secundaria") or ("#e9e5db" if estilo == "templario" else "#d8d2c4")
    det = cores.get("detalhe") or "#4a3020"
    chao_joelho = h.arm.data.bones["calf_l"].head_local.z
    cintura = h.arm.data.bones["spine_01"].head_local.z
    abaixo_do_joelho = lambda co: co[2] < chao_joelho - 0.06
    if estilo == "templario":
        import fc_armadura

        # cota de malha inteira (camisa, calças e coifa), sobreveste longa com a cruz pátea,
        # cintos de couro com fivelas de latão, placas nos membros, elmo de barril e manto
        malha_mat = _mat(f"{prefixo}_cota", "cota_de_malha")
        a.casca("cota", TRONCO + BRACOS + ["neck_01"], 0.007, 0.004, malha_mat, limiar=0.45)
        a.casca("calcas", PERNAS, 0.006, 0.004, malha_mat)
        quadril = h.arm.data.bones["pelvis"].head_local.z
        peito = h.arm.data.bones["spine_03"].head_local.z

        def barra(co):
            # bainha em bico na frente e atrás; laterais abertas abaixo do quadril
            if abs(co[0]) > 0.115 and co[2] < quadril - 0.06:
                return False
            return co[2] > chao_joelho - 0.2 + 0.55 * max(0.0, abs(co[0]) - 0.02) ** 1.2

        tronco_y = float(np.mean(h.coords[a.soma(["spine_02", "spine_03"]) > 0.6][:, 1]))

        z_cinto = cintura - 0.05
        if a.pano:
            # as placas vêm antes: o pano cai por cima das joelheiras e grevas em vez de atravessá-las
            a.pecas.extend(fc_armadura.armadura_templario(a, prefixo, cores.get("acabamento", "aco"), com_elmo=cores.get("elmo", True),
                                                          textura=cores.get("textura")))

        def caimento(o):
            # o pano cai do peito para baixo sem marcar o corpo, e a barra desce até o meio da canela
            fc_armadura.moldar(o, (0.0, tronco_y, 0.0), (0.0, 0.0, 1.0), sigma_ang=3.0, sigma_fatia=2.5)
            a.alongar_barra(o, 0.24, abaixo_de=chao_joelho + 0.12)

        mat_sob = _mat(f"{prefixo}_sobreveste", "tecido_grosso", sec)
        if a.pano:
            import fc_pano

            ombros = (a.ossos("upperarm_l").head_local - a.ossos("upperarm_r").head_local).length
            xl = h.arm.data.bones["thigh_l"].head_local.x or 0.1

            def pesos_aba(x, t, lado):
                # perto do cinto segue a bacia; logo abaixo do quadril cada lado da aba acompanha quase
                # inteiro a coxa do seu lado (senão a coxa atravessa o pano quando a perna mexe); no meio,
                # entre as pernas, a transição é suave
                perna = 0.85 * float(fc_pano._sstep(0.05, 0.4, t))
                f = float(np.clip(0.5 + 0.9 * x / xl, 0.0, 1.0))
                return {"pelvis": 1.0 - perna, "thigh_l": perna * f, "thigh_r": perna * (1.0 - f)}

            def caimento_pano(o):
                # do peito ao cinto: a casca moldada (sem marcar o peito); abaixo do cinto: abas de pano
                # franzidas pelo cinto
                fc_armadura.moldar(o, (0.0, tronco_y, 0.0), (0.0, 0.0, 1.0), sigma_ang=3.0, sigma_fatia=2.5)
                fc_armadura.taubin(o, iteracoes=20)
                abas = fc_pano.paineis_franzidos(prefixo, mat_sob, h.obj, z_cinto, chao_joelho - 0.2, ombros * 1.15,
                                                 [h.obj] + list(a.pecas), pesos_aba)
                fc_pano.juntar(o, abas)

            # a costura entre o peito e as abas fica escondida embaixo do cinto
            sob = a.casca("sobreveste", TRONCO, 0.024, 0.004, mat_sob, limiar=0.5, filtro=lambda co: co[2] > z_cinto - 0.012,
                          suavizar=12, preparo=caimento_pano)
        else:
            sob = a.casca("sobreveste", TRONCO, 0.024, 0.004, mat_sob, limiar=0.5,
                          grupos_extra=["helper-skirt"], suavizar=12, filtro_extra=barra, preparo=caimento)

        def patea(co, cz, L, a0, a1, folga=0.0):
            dx, dz = abs(co[0]), abs(co[2] - cz)
            if co[1] > tronco_y:  # só a frente (a aba simulada pode cair bem rente às pernas)
                return False
            L2 = L + folga
            vert = dz <= L2 and dx <= a0 + folga + (a1 - a0) * min(1.0, dz / L) ** 1.6
            hor = dx <= L * 0.92 + folga and dz <= a0 + folga + (a1 - a0) * min(1.0, dx / (L * 0.92)) ** 1.6
            return vert or hor

        if sob is not None and cores.get("emblema", "cruz") != "nenhum":
            tinta = _mat(f"{prefixo}_cruz", "tecido", p, escala=40.0)
            a.estampa(sob, "cruz", lambda co, folga=0.0: patea(co, peito + 0.02, 0.11, 0.022, 0.064, folga), tinta)
            plano = (1, fc_pano.posicao_plana(z_cinto, fc_pano.densidade_uv(h.obj))) if a.pano else None
            a.estampa(sob, "cruz_barra", lambda co, folga=0.0: patea(co, chao_joelho + 0.05, 0.045, 0.008, 0.026, folga), tinta, cortes=5,
                      plano=plano)
        couro_v = _mat(f"{prefixo}_cinto", "couro", "#7c1a14")
        latao = _mat(f"{prefixo}_latao", "ouro")
        a.casca("cinto", TRONCO, 0.036, 0.006, couro_v, filtro=lambda co: abs(co[2] - z_cinto) < 0.02, cobrir=0, suavizar=6)
        z_quad = cintura - 0.14
        a.casca("cinto_espada", TRONCO + ["thigh_l", "thigh_r"], 0.04, 0.006, couro_v, limiar=0.3,
                filtro=lambda co: abs((co[2] - z_quad) - 0.32 * co[0]) < 0.017 and co[2] > quadril - 0.1, cobrir=0, suavizar=6)
        _fivela(a, "fivela", _frente_do_corpo(a, z_cinto, folga=0.044), latao, {"spine_01": 0.6, "pelvis": 0.4})
        _fivela(a, "fivela_2", _frente_do_corpo(a, z_quad, TRONCO + ["thigh_l", "thigh_r"], folga=0.048) + Vector((0.05, 0, 0.016)), latao,
                {"pelvis": 1.0}, larg=0.04, alt=0.034)
        if not a.pano:
            a.pecas.extend(fc_armadura.armadura_templario(a, prefixo, cores.get("acabamento", "aco"), com_elmo=cores.get("elmo", True),
                                                          textura=cores.get("textura")))
        if capa:
            a.capa(_mat(f"{prefixo}_capa", "tecido_grosso", sec), comprimento=1.15)
    elif estilo == "cavaleiro_placas":
        import fc_armadura

        # cota de malha por baixo (aparece nas juntas), gibão e saia de malha, e a armadura de placas por cima
        a.casca("cota", TRONCO + BRACOS + ["neck_01"], 0.007, 0.004, _mat(f"{prefixo}_cota", "cota_de_malha"), limiar=0.45)
        a.casca("calcas", PERNAS, 0.006, 0.004, _mat(f"{prefixo}_calcas", "cota_de_malha"))
        a.casca("cinto", TRONCO, 0.05, 0.01, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.07)) < 0.025,
                cobrir=0, suavizar=10)
        a.pecas.extend(fc_armadura.armadura_de_placas(a, prefixo, cores.get("acabamento", "aco"), com_elmo=cores.get("elmo", True),
                                                      textura=cores.get("textura")))
        if capa:
            a.capa(_mat(f"{prefixo}_capa", "tecido", p))
    elif estilo in ("cavaleiro", "soldado"):
        a.casca("cota", TRONCO + BRACOS + ["neck_01"], 0.007, 0.004, _mat(f"{prefixo}_cota", "cota_de_malha"), limiar=0.45)
        a.casca("calcas", PERNAS, 0.005, 0.004, _mat(f"{prefixo}_calcas", "cota_de_malha" if estilo == "cavaleiro" else "tecido", "#3a3a3a"))
        a.casca("sobreveste", TRONCO, 0.022, 0.004, _mat(f"{prefixo}_sobreveste", "tecido", sec), limiar=0.5, grupos_extra=["helper-skirt"],
                suavizar=12, filtro_extra=lambda co: co[2] > chao_joelho + 0.04)
        a.casca("cinto", TRONCO, 0.024, 0.008, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.02)) < 0.035, cobrir=0)
        a.casca("botas", PES + ["calf_l", "calf_r"], 0.016, 0.006, _mat(f"{prefixo}_botas", "couro_escuro"), filtro=lambda co: co[2] < chao_joelho - 0.1,
                suavizar=25, cobrir=0.3, limiar=0.3)
        a.casca("luvas", MAOS, 0.004, 0.002, _mat(f"{prefixo}_luvas", "couro_escuro"), limiar=0.3, suavizar=2, cobrir=0.5)
        # a cruz da ordem na frente e nas costas da sobreveste
        peito = h.arm.data.bones["spine_03"].head_local.z
        if cores.get("emblema", "cruz") == "cruz":
            def cruz(co):
                vertical = abs(co[0]) < 0.045 and (cintura - 0.25) < co[2] < peito + 0.12
                horizontal = abs(co[2] - (peito + 0.02)) < 0.04 and abs(co[0]) < 0.17
                return vertical or horizontal
            a.casca("cruz", TRONCO, 0.0265, 0.002, _mat(f"{prefixo}_cruz", "tecido", p), limiar=0.5, filtro=cruz, cobrir=0, suavizar=12,
                    grupos_extra=["helper-skirt"], filtro_extra=lambda co: abs(co[0]) < 0.045 and co[2] > chao_joelho + 0.04)
        aco = _mat(f"{prefixo}_aco", "aco")
        a.ombreiras(aco)
        if estilo == "cavaleiro":
            a.elmo(aco)
        if capa:
            a.capa(_mat(f"{prefixo}_capa", "tecido", p))
    elif estilo == "jaqueta":
        # moderno: camisa de brim por baixo (gola em volta do pescoço), jaqueta de couro aberta na frente
        # (abertura em V até o pescoço), gola larga de tecido grosso, dois bolsos no peito com aba, calça
        # jeans e botas. cores: principal = jaqueta, secundaria = camisa, detalhe = gola
        ossos = h.arm.data.bones
        pesc = ossos["neck_01"].head_local.z
        peito = ossos["spine_03"].head_local.z
        meio_y = ossos["spine_02"].head_local.y
        frente = lambda co: co[1] < meio_y - 0.02  # noqa: E731 (no Blender a frente é -Y)

        def abertura(z):
            t = min(1.0, max(0.0, (z - cintura) / max(pesc - cintura, 1e-3)))
            return 0.012 + 0.03 * t ** 2.5

        def decote(co):  # a camisa aberta no pescoço (V raso), como camisa de botão com o primeiro aberto
            k = (co[2] - (pesc - 0.075)) / 0.075
            return frente(co) and k > 0 and abs(co[0]) < 0.006 + 0.03 * k

        camisa = _mat(f"{prefixo}_camisa", "tecido", cores.get("secundaria") or "#767b82")
        a.casca("camisa", TRONCO + BRACOS + ["neck_01"], 0.006, 0.003, camisa, limiar=0.45,
                filtro=lambda co: cintura - 0.3 < co[2] < pesc + 0.02 and not decote(co), suavizar=6)
        # colarinho virado (aberto na frente) e os botões de pressão na carcela
        a.casca("colarinho", TRONCO + ["neck_01"], 0.013, 0.004, camisa, limiar=0.3,
                filtro=lambda co: pesc - 0.03 < co[2] < pesc + 0.025 and abs(co[0]) < 0.1 and not (frente(co) and abs(co[0]) < 0.035),
                cobrir=0, suavizar=4)
        a.casca("botoes", TRONCO, 0.009, 0.003, _mat(f"{prefixo}_botoes", "aco", "#c9c9c4"),
                filtro=lambda co: frente(co) and abs(co[0]) < 0.007 and cintura - 0.2 < co[2] < pesc - 0.04 and (co[2] % 0.085) < 0.011, cobrir=0)
        # camurça: couro fosco (sem o brilho de couro envernizado)
        jaq = _mat(f"{prefixo}_jaqueta", "couro", p, rugosidade_extra=0.35)
        # jaqueta larga (não marca peito nem barriga: alisada bem mais que a camisa)
        a.casca("jaqueta", TRONCO + BRACOS, 0.026, 0.006, jaq, limiar=0.5,
                filtro=lambda co: cintura - 0.2 < co[2] < pesc - 0.01 and not (frente(co) and abs(co[0]) < abertura(co[2])), suavizar=14)
        # gola deitada: só em volta da base do pescoço (sem escorrer pelos ombros), aberta na frente
        a.casca("gola", TRONCO + ["neck_01", "clavicle_l", "clavicle_r"], 0.036, 0.01,
                _mat(f"{prefixo}_gola", "tecido_grosso", cores.get("detalhe") or "#3b2a20"), limiar=0.3,
                filtro=lambda co: pesc - 0.06 < co[2] < pesc + 0.012 and abs(co[0]) < 0.13 and not (frente(co) and abs(co[0]) < abertura(co[2]) + 0.012),
                cobrir=0, suavizar=6)
        for lado in (-1, 1):
            # bolso no peito (placa um pouco por fora da jaqueta) e a aba por cima
            x0, x1 = 0.035, 0.135
            zb = peito + 0.09  # altura do bolso: no peito, não na barriga
            a.casca(f"bolso_{'e' if lado > 0 else 'd'}", TRONCO, 0.031, 0.004, jaq,
                    filtro=lambda co, lado=lado: frente(co) and x0 < co[0] * lado < x1 and zb - 0.12 < co[2] < zb, cobrir=0)
            a.casca(f"aba_{'e' if lado > 0 else 'd'}", TRONCO, 0.036, 0.005, jaq,
                    filtro=lambda co, lado=lado: frente(co) and x0 - 0.005 < co[0] * lado < x1 + 0.005 and zb - 0.035 < co[2] < zb + 0.005, cobrir=0)
        a.casca("calcas", PERNAS + ["pelvis"], 0.006, 0.003, _mat(f"{prefixo}_calcas", "tecido", "#3d4450"),
                filtro=lambda co: co[2] < cintura - 0.04)
        a.casca("botas", PES + ["calf_l", "calf_r"], 0.012, 0.005, _mat(f"{prefixo}_botas", "couro_escuro", "#3a2a1e"),
                filtro=lambda co: co[2] < chao_joelho - 0.14, suavizar=12)
        a.casca("cinto", TRONCO, 0.012, 0.006, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.05)) < 0.02, cobrir=0)
    elif estilo == "nobre":
        a.casca("gibao", TRONCO + BRACOS, 0.008, 0.005, _mat(f"{prefixo}_gibao", "tecido", p), grupos_extra=["helper-skirt"])
        a.casca("calcas", PERNAS, 0.005, 0.003, _mat(f"{prefixo}_calcas", "tecido", "#2b2b30"))
        a.casca("botas", PES + ["calf_l", "calf_r"], 0.008, 0.005, _mat(f"{prefixo}_botas", "couro_escuro"), filtro=lambda co: co[2] < chao_joelho - 0.05)
        a.casca("cinto", TRONCO, 0.02, 0.008, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.02)) < 0.03, cobrir=0)
        if capa:
            a.capa(_mat(f"{prefixo}_capa", "tecido", sec))
    else:  # camponês / mercenário
        # camponês: túnica longa (saia até a canela); morto-vivo (sujo): a saia cortada no meio da coxa,
        # que não vira "vestido" quando ele anda curvado
        saia = estilo == "campones"
        corte = cintura - 0.3 if sujo else -1.0
        # sujo (morto-vivo): mais folga e alisada, como pano largo (sem marcar o peito)
        a.casca("tunica", TRONCO + BRACOS, 0.016 if sujo else 0.008, 0.005, _mat(f"{prefixo}_tunica", "tecido", p),
                filtro=lambda co: co[2] > corte, grupos_extra=["helper-skirt"] if saia else (),
                filtro_extra=lambda co: co[2] > corte, suavizar=10 if sujo else 0)
        a.casca("calcas", PERNAS, 0.005, 0.003, _mat(f"{prefixo}_calcas", "tecido", sec))
        # alisada: sem isso a casca copia os dedos e a bota parece pé descalço
        a.casca("botas", PES + ["calf_l", "calf_r"], 0.012, 0.005, _mat(f"{prefixo}_botas", "couro", det), filtro=lambda co: co[2] < chao_joelho - 0.12,
                suavizar=12)
        a.casca("cinto", TRONCO, 0.02, 0.008, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.02)) < 0.03, cobrir=0)
        if estilo == "mercenario":
            a.casca("couraca", ["spine_02", "spine_03"], 0.016, 0.006, _mat(f"{prefixo}_couraca", "couro", "#5a3a22"), limiar=0.6)
    if a.pano:
        # nível de qualidade: cada peça de pano ganha textura única com lama na barra, dobras e bainha
        import fc_pano

        for o in list(a.pecas):
            # calças de tecido também (as de cota de malha dos cavaleiros não: perderiam a transparência)
            calcas_de_tecido = o.name.endswith("_calcas") and estilo in ("campones", "mercenario", "nobre")
            if o.type == "MESH" and (o.name.endswith(PECAS_DE_PANO) or (sujo and calcas_de_tecido)):
                try:
                    fc_pano.assar_desgaste_pano(o, o.name, z_chao=0.0, res=2048 if o.name.endswith(("_sobreveste", "_capa")) else 1024,
                                                forte=sujo)
                except Exception as e:  # sem o desgaste, a peça fica com o tecido limpo
                    print(f"[roupa] desgaste de {o.name} não assou: {e}")
    a.esconder_corpo()
    return a.pecas
