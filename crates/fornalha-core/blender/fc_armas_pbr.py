# Fornalha: armas com forma de verdade e materiais PBR (aço riscado, couro, ouro,
# madeira pintada): espada longa com lâmina em losango e sulco central, guarda
# curva, cabo enrolado e pomo de roda; escudo em forma de pipa com borda de metal,
# umbo e a cruz. Origem no ponto da pegada; a lâmina aponta para +Z.
import math

import bmesh
import bpy
from mathutils import Vector

import fc_pbr


def _secao(bm, pontos, z):
    return [bm.verts.new((x, y, z)) for x, y in pontos]


def _ligar(bm, a, b, fechar=True):
    n = len(a)
    for i in range(n if fechar else n - 1):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))


def _obj(bm, nome, material):
    malha = bpy.data.meshes.new(nome)
    bm.normal_update()
    bm.to_mesh(malha)
    bm.free()
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    for p in malha.polygons:
        p.use_smooth = True
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    m = obj.modifiers.new("arestas", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.008)
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def lamina(nome, mat, comprimento=0.86, largura=0.052, espessura=0.0085, base_z=0.11):
    """Seção em losango com sulco (fuller) no primeiro terço; afina até a ponta."""
    bm = bmesh.new()
    secoes = []
    n = 26
    for k in range(n + 1):
        t = k / n
        z = base_z + comprimento * t
        w = largura / 2 * (1 - 0.55 * t) * (1 if t < 0.93 else max(0.02, (1 - t) / 0.07))
        e = espessura / 2 * (1 - 0.6 * t) * (1 if t < 0.93 else max(0.05, (1 - t) / 0.07))
        sulco = e * (0.35 if t < 0.62 else 1.0)
        pontos = [(w, 0.0), (w * 0.45, e * 0.9), (0.0, sulco), (-w * 0.45, e * 0.9), (-w, 0.0), (-w * 0.45, -e * 0.9), (0.0, -sulco), (w * 0.45, -e * 0.9)]
        secoes.append(_secao(bm, pontos, z))
    for a, b in zip(secoes, secoes[1:]):
        _ligar(bm, a, b)
    ponta = bm.verts.new((0, 0, base_z + comprimento + 0.012))
    for i in range(8):
        bm.faces.new((secoes[-1][i], secoes[-1][(i + 1) % 8], ponta))
    bm.faces.new(list(reversed(secoes[0])))
    return _obj(bm, nome, mat)


def guarda(nome, mat, largura=0.22, z=0.1):
    bm = bmesh.new()
    secoes = []
    n = 18
    for k in range(n + 1):
        t = k / n - 0.5
        x = t * largura
        zz = z - (abs(t) * 2) ** 2.2 * 0.018
        r = 0.011 * (1.0 + 0.5 * (abs(t) * 2) ** 6)
        pontos = [(r * math.cos(a), r * math.sin(a)) for a in [i * math.pi / 4 for i in range(8)]]
        secoes.append([bm.verts.new((x, y * 0.8, zz + yy)) for y, yy in pontos])
    for a, b in zip(secoes, secoes[1:]):
        _ligar(bm, a, b)
    bm.faces.new(list(reversed(secoes[0])))
    bm.faces.new(secoes[-1])
    return _obj(bm, nome, mat)


def cabo(nome, mat, z0=-0.11, z1=0.095):
    bm = bmesh.new()
    secoes = []
    n = 14
    for k in range(n + 1):
        t = k / n
        z = z0 + (z1 - z0) * t
        r = 0.0145 + 0.002 * math.sin(t * math.pi) + 0.0012 * math.sin(t * math.pi * 14)  # tiras de couro
        secoes.append([bm.verts.new((r * math.cos(a), r * 0.88 * math.sin(a), z)) for a in [i * math.pi / 6 for i in range(12)]])
    for a, b in zip(secoes, secoes[1:]):
        _ligar(bm, a, b)
    bm.faces.new(list(reversed(secoes[0])))
    bm.faces.new(secoes[-1])
    return _obj(bm, nome, mat)


def pomo(nome, mat, z=-0.13):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.032, depth=0.022, location=(0, 0, z), rotation=(math.pi / 2, 0, 0))
    o = bpy.context.active_object
    o.name = nome
    bev = o.modifiers.new("chanfro", "BEVEL")
    bev.width = 0.006
    bev.segments = 3
    bpy.ops.object.modifier_apply(modifier=bev.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(mat)
    return o


def espada_longa(prefixo, cores=None):
    cores = cores or {}
    aco = fc_pbr.material(f"{prefixo}_aco_lamina", "aco", cores.get("metal"), escala=6.0)
    ouro = fc_pbr.material(f"{prefixo}_guarda", "ouro" if cores.get("guarda", "ouro") == "ouro" else "ferro_velho")
    couro = fc_pbr.material(f"{prefixo}_cabo", "couro_escuro", escala=10.0)
    partes = [lamina(f"{prefixo}_lamina", aco), guarda(f"{prefixo}_guarda", ouro), cabo(f"{prefixo}_cabo", couro), pomo(f"{prefixo}_pomo", ouro)]
    return _juntar(partes, f"{prefixo}_espada")


def escudo_pipa(prefixo, cor_campo="#d8d2c4", cor_cruz="#8a1f1a"):
    """Escudo de pipa (normando), curvo, com borda de ferro, umbo e cruz pintada."""
    alt, larg = 0.95, 0.56
    contorno = []
    n = 40
    for i in range(n + 1):
        t = i / n
        # meia silhueta: topo arredondado e ponta embaixo
        if t < 0.25:
            a = t / 0.25 * math.pi / 2
            x, z = larg / 2 * math.sin(a), alt * 0.82 + (alt * 0.18) * math.cos(a)
        else:
            u = (t - 0.25) / 0.75
            x, z = larg / 2 * (1 - u) ** 1.25, alt * 0.82 * (1 - u)
        contorno.append((x, z))
    pontos = [(-x, z) for x, z in reversed(contorno)] + [(x, z) for x, z in contorno[1:]]
    curva = lambda x: -((x / (larg / 2)) ** 2) * 0.07  # curvatura para trás

    def placa(espessura, escala_xy=1.0, y0=0.0):
        bm = bmesh.new()
        frente = [bm.verts.new((x * escala_xy, curva(x) + y0, z * escala_xy + (1 - escala_xy) * alt / 2)) for x, z in pontos]
        tras = [bm.verts.new((v.co.x, v.co.y + espessura, v.co.z)) for v in frente]
        bm.faces.new(frente)
        bm.faces.new(list(reversed(tras)))
        _ligar(bm, frente, tras)
        return bm

    madeira = fc_pbr.material(f"{prefixo}_escudo_campo", "madeira", cor_campo, escala=2.0, mistura_tom=0.85)
    campo = _obj(placa(0.022), f"{prefixo}_escudo", madeira)
    ferro = fc_pbr.material(f"{prefixo}_escudo_borda", "ferro_velho")
    borda = _obj(placa(0.03, 1.0, -0.004), f"{prefixo}_escudo_borda", ferro)
    bm = bmesh.new()
    bm.from_mesh(borda.data)
    # só o anel de borda: apaga o miolo da placa de ferro
    miolo = [f for f in bm.faces if len(f.verts) > 8]
    bmesh.ops.delete(bm, geom=miolo, context="FACES_ONLY")
    bm.to_mesh(borda.data)
    bm.free()
    sol = borda.modifiers.new("aro", "SOLIDIFY")
    sol.thickness = 0.012
    bpy.context.view_layer.objects.active = borda
    bpy.ops.object.modifier_apply(modifier=sol.name)
    # cruz pintada (um pouco à frente do campo)
    tinta = fc_pbr.material(f"{prefixo}_escudo_cruz", "tecido", cor_cruz, escala=12.0)
    partes = [campo, borda]
    # a cruz é recortada pelo contorno do escudo (menor 8%): nada de pintura saindo pela ponta
    def dentro(x, z, k=0.9):
        cx_, cz_ = 0.0, alt / 2
        pol = [((px - cx_) * k + cx_, (pz - cz_) * k + cz_) for px, pz in pontos]
        d = False
        for i in range(len(pol)):
            (x1, z1), (x2, z2) = pol[i], pol[i - 1]
            if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / ((z2 - z1) or 1e-9) + x1:
                d = not d
        return d

    braco_v, braco_h = 0.11, 0.11
    cruz_z = alt * 0.68

    def na_cruz(x, z):
        return (abs(x) <= braco_v / 2 or abs(z - cruz_z) <= braco_h / 2) and dentro(x, z)

    passo = 0.01
    bm = bmesh.new()
    vmap = {}

    def vert(i, j):
        if (i, j) not in vmap:
            x, z = i * passo, j * passo
            vmap[(i, j)] = bm.verts.new((x, curva(x) - 0.0015, z))
        return vmap[(i, j)]

    for i in range(int(-larg / 2 / passo) - 1, int(larg / 2 / passo) + 1):
        for j in range(0, int(alt / passo) + 1):
            x, z = (i + 0.5) * passo, (j + 0.5) * passo
            if na_cruz(x, z):
                bm.faces.new((vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)))
    partes.append(_obj(bm, f"{prefixo}_escudo_cruz", tinta))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=0.06, location=(0, -0.01, alt * 0.66))
    umbo = bpy.context.active_object
    umbo.scale = (1, 0.45, 1)
    bpy.ops.object.transform_apply(scale=True)
    for p in umbo.data.polygons:
        p.use_smooth = True
    umbo.data.materials.append(ferro)
    partes.append(umbo)
    escudo = _juntar(partes, f"{prefixo}_escudo")
    # origem na alça (meio da parte de trás)
    return escudo


def _juntar(partes, nome):
    for o in bpy.context.scene.objects:
        o.select_set(o in partes)
    bpy.context.view_layer.objects.active = partes[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = nome
    return o


def prender_na_mao(obj, arm, lado="r", escudo=False):
    """Põe a arma na pegada da mão (pela palma e pelo polegar) e prende no osso."""
    mw = arm.matrix_world
    mao = arm.data.bones[f"hand_{lado}"]
    meio = arm.data.bones.get(f"middle_01_{lado}")
    pol = arm.data.bones.get(f"thumb_01_{lado}")
    if escudo:
        braco = arm.data.bones[f"lowerarm_{lado}"]
        ini, fim = mw @ braco.head_local, mw @ braco.tail_local
        eixo = (fim - ini).normalized()
        centro = ini + (fim - ini) * 0.55
        fora = Vector((1 if lado == "l" else -1, 0, 0))
        frente = eixo.cross(Vector((0, 0, 1))).normalized()
        if frente.y > 0:
            frente = -frente
        z = Vector((0, 0, 1))
        x = z.cross(frente).normalized()
        from mathutils import Matrix

        rot = Matrix((x, frente, z)).transposed().to_4x4()
        obj.matrix_world = Matrix.Translation(centro + fora * 0.07 + frente * -0.02 - Vector((0, 0, 0.45))) @ rot
        osso = braco.name
    else:
        from mathutils import Matrix

        pulso = mw @ mao.head_local
        dedos = (mw @ meio.head_local) if meio else (mw @ mao.tail_local)
        dir_mao = (dedos - pulso).normalized()
        polegar = ((mw @ pol.head_local) - pulso) if pol else Vector((0, -1, 0))
        lamina = (polegar - dir_mao * polegar.dot(dir_mao)).normalized()
        y = dir_mao.cross(lamina).normalized()
        x = y.cross(lamina).normalized()
        rot = Matrix((x, y, lamina)).transposed().to_4x4()
        pegada = pulso + dir_mao * 0.075
        obj.matrix_world = Matrix.Translation(pegada) @ rot
        osso = mao.name
    for o in bpy.context.scene.objects:
        o.select_set(False)
    arm.data.bones.active = arm.data.bones[osso]
    obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="BONE", keep_transform=True)
    return obj
