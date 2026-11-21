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
              suavizar=0, filtro_extra=None):
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
        nx, nz = 22, 30
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
                dobra = pregas * 0.028 * t ** 0.8
                y = costas_y + 0.16 * t ** 1.2 + dobra - curva
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


def _mat(nome, tipo, tom=None, escala=None):
    return fc_pbr.material(nome, tipo, tom, escala)


def vestir(h, prefixo, estilo, cores, capa=True):
    """estilo: cavaleiro, soldado, campones, nobre, mercenario. cores: principal, secundaria, detalhe."""
    a = Alfaiate(h, prefixo)
    p = cores.get("principal", "#8a1f1a")
    sec = cores.get("secundaria", "#d8d2c4")
    det = cores.get("detalhe", "#4a3020")
    chao_joelho = h.arm.data.bones["calf_l"].head_local.z
    cintura = h.arm.data.bones["spine_01"].head_local.z
    abaixo_do_joelho = lambda co: co[2] < chao_joelho - 0.06
    if estilo == "cavaleiro_placas":
        import fc_armadura

        # cota de malha por baixo (aparece nas juntas), gibão e saia de malha, e a armadura de placas por cima
        a.casca("cota", TRONCO + BRACOS + ["neck_01"], 0.007, 0.004, _mat(f"{prefixo}_cota", "cota_de_malha"), limiar=0.45)
        a.casca("calcas", PERNAS, 0.006, 0.004, _mat(f"{prefixo}_calcas", "cota_de_malha"))
        a.casca("cinto", TRONCO, 0.05, 0.01, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.07)) < 0.025,
                cobrir=0, suavizar=10)
        a.pecas.extend(fc_armadura.armadura_de_placas(a, prefixo, cores.get("acabamento", "aco_escuro"), com_elmo=cores.get("elmo", True)))
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
    elif estilo == "nobre":
        a.casca("gibao", TRONCO + BRACOS, 0.008, 0.005, _mat(f"{prefixo}_gibao", "tecido", p), grupos_extra=["helper-skirt"])
        a.casca("calcas", PERNAS, 0.005, 0.003, _mat(f"{prefixo}_calcas", "tecido", "#2b2b30"))
        a.casca("botas", PES + ["calf_l", "calf_r"], 0.008, 0.005, _mat(f"{prefixo}_botas", "couro_escuro"), filtro=lambda co: co[2] < chao_joelho - 0.05)
        a.casca("cinto", TRONCO, 0.02, 0.008, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.02)) < 0.03, cobrir=0)
        if capa:
            a.capa(_mat(f"{prefixo}_capa", "tecido", sec))
    else:  # camponês / mercenário
        a.casca("tunica", TRONCO + BRACOS, 0.008, 0.005, _mat(f"{prefixo}_tunica", "tecido", p),
                filtro=lambda co: True, grupos_extra=["helper-skirt"] if estilo == "campones" else ())
        a.casca("calcas", PERNAS, 0.005, 0.003, _mat(f"{prefixo}_calcas", "tecido", sec))
        a.casca("botas", PES + ["calf_l", "calf_r"], 0.008, 0.005, _mat(f"{prefixo}_botas", "couro", det), filtro=lambda co: co[2] < chao_joelho - 0.12)
        a.casca("cinto", TRONCO, 0.02, 0.008, _mat(f"{prefixo}_cinto", "couro_escuro"), filtro=lambda co: abs(co[2] - (cintura - 0.02)) < 0.03, cobrir=0)
        if estilo == "mercenario":
            a.casca("couraca", ["spine_02", "spine_03"], 0.016, 0.006, _mat(f"{prefixo}_couraca", "couro", "#5a3a22"), limiar=0.6)
    a.esconder_corpo()
    return a.pecas
