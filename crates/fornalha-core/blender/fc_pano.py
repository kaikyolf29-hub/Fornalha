# Fornalha: caimento de pano de verdade (simulação de tecido do Blender, só na geração).
# A peça (sobreveste, manto, túnica, saia) é presa onde a roupa segura (ombros, cintura, cinto),
# cai pela gravidade, bate no corpo e nas outras roupas e assenta com dobras naturais. O resultado
# é aplicado na malha: no jogo não há simulação pesada (leve em qualquer placa), só os pesos de
# osso para acompanhar a animação (e a mola da capa).
import bpy
import numpy as np
from mathutils import Vector


def _ativo(obj):
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj


def grupo_de_pinos(obj, nome, peso_por_vertice):
    """Cria o grupo de vértices presos (peso 1 = preso, 0 = solto)."""
    g = obj.vertex_groups.get(nome) or obj.vertex_groups.new(name=nome)
    for i, w in enumerate(peso_por_vertice):
        if w > 0.0:
            g.add([i], float(min(1.0, w)), "REPLACE")
    return g


def drapear(obj, colisores, pinos, quadros=50, qualidade=6, massa=0.25, rigidez=12.0, dobra=0.4, espessura=0.004, auto_colisao=False,
            atrito=3.0):
    """Simula o pano por `quadros` quadros e aplica o resultado na malha de `obj`.
    `pinos`: nome do grupo de vértices presos. Os colisores ganham colisão só durante a simulação."""
    cena = bpy.context.scene
    tirar = []
    for c in colisores:
        if c is None or c.type != "MESH":
            continue
        if not any(m.type == "COLLISION" for m in c.modifiers):
            m = c.modifiers.new("colisao_pano", "COLLISION")
            tirar.append((c, m.name))
        c.collision.thickness_outer = espessura
        c.collision.cloth_friction = atrito
    mod = obj.modifiers.new("pano", "CLOTH")
    # o pano vem antes de qualquer outro modificador (espessura, esqueleto)
    while obj.modifiers.find(mod.name) > 0:
        _ativo(obj)
        bpy.ops.object.modifier_move_up(modifier=mod.name)
    s = mod.settings
    s.quality = qualidade
    s.mass = massa
    s.tension_stiffness = rigidez
    s.compression_stiffness = rigidez
    s.shear_stiffness = rigidez * 0.4
    s.bending_stiffness = dobra
    s.air_damping = 4.0
    s.vertex_group_mass = pinos
    cs = mod.collision_settings
    cs.use_collision = True
    cs.distance_min = espessura * 0.75
    cs.use_self_collision = auto_colisao  # o pano dobrado não atravessa ele mesmo
    cs.self_distance_min = espessura * 0.75
    mod.point_cache.frame_start = 1
    mod.point_cache.frame_end = quadros
    inicio, fim, atual = cena.frame_start, cena.frame_end, cena.frame_current
    cena.frame_start, cena.frame_end = 1, quadros
    cena.frame_set(0)
    for f in range(1, quadros + 1):
        cena.frame_set(f)
    # o resultado do último quadro vai para a malha (sem o modificador e sem as chaves de forma)
    co = coordenadas_avaliadas(obj)
    obj.modifiers.remove(mod)
    if obj.data.shape_keys:
        ad = obj.data.shape_keys.animation_data
        acao = ad.action if ad else None
        obj.shape_key_clear()
        if acao is not None and acao.users == 0:
            bpy.data.actions.remove(acao)  # a animação do cinto não vai para o glb
    if len(co) == len(obj.data.vertices):
        obj.data.vertices.foreach_set("co", co.ravel())
        obj.data.update()
    else:
        print("[pano] a simulação mudou a malha; a peça fica como estava")
    cena.frame_start, cena.frame_end = inicio, fim
    cena.frame_set(atual)
    for c, nome in tirar:
        if nome in c.modifiers:
            c.modifiers.remove(c.modifiers[nome])
    g = obj.vertex_groups.get(pinos)
    if g is not None:
        obj.vertex_groups.remove(g)
    return obj


def coordenadas_avaliadas(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = ev.to_mesh()
    co = np.empty(len(m.vertices) * 3)
    m.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    return co.reshape(-1, 3)


def _coords(obj):
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


BRACOS = ("upperarm", "lowerarm", "hand", "clavicle", "thumb", "index", "middle", "ring", "pinky")


def _pontos(colisores, z0, z1, ignorar=BRACOS):
    """Vértices (mundo) dos colisores entre as alturas z1 e z0, sem os que seguem os ossos de `ignorar`
    (o braço na pose em A fica ao lado da cintura e não é onde o pano apoia)."""
    pts = []
    for c in colisores:
        if c is None or c.type != "MESH":
            continue
        co = _coords(c)
        if len(co) == 0:
            continue
        if ignorar and c.vertex_groups:
            fora = {g.index for g in c.vertex_groups if g.name.startswith(ignorar)}
            if fora:
                manter = np.ones(len(co), dtype=bool)
                for v in c.data.vertices:
                    if v.groups:
                        g = max(v.groups, key=lambda e: e.weight)
                        if g.group in fora:
                            manter[v.index] = False
                co = co[manter]
        m = np.array(c.matrix_world)
        pts.append(co @ m[:3, :3].T + m[:3, 3])
    p = np.concatenate(pts) if pts else np.zeros((1, 3))
    return p[(p[:, 2] < z0 + 0.02) & (p[:, 2] > z1 - 0.05)]


def perfil_pendurado(pontos, lado, xs, zs, saida_topo):
    """Superfície em que um pano preso no cinto e caindo pela gravidade se apoia, coluna a coluna:
    o "barbante esticado" do cinto até as partes mais salientes (coxa, joelheira) e reto para baixo
    depois delas. lado=-1 frente, +1 costas; saida_topo[i] = quanto o cinto está para fora (m).
    Devolve a "saída" (−y na frente, +y atrás) para cada coluna (xs) e altura (zs, de cima para baixo)."""
    saida = np.zeros((len(zs), len(xs)))
    passo = abs(zs[1] - zs[0]) if len(zs) > 1 else 0.01
    for i, x in enumerate(xs):
        q = pontos[np.abs(pontos[:, 0] - x) < 0.03]
        o_bin = np.full(len(zs), -np.inf)
        if len(q):
            o = q[:, 1] * lado
            k = np.clip(np.round((zs[0] - q[:, 2]) / passo).astype(int), 0, len(zs) - 1)
            np.maximum.at(o_bin, k, o)
        topo = saida_topo[i]
        dz = zs[0] - zs  # 0 no cinto, cresce para baixo
        col = np.full(len(zs), topo)
        for kq in np.nonzero(np.isfinite(o_bin))[0]:
            if kq == 0:
                col = np.maximum(col, o_bin[kq])
                continue
            # reta do cinto até o ponto (acima dele) e reto para baixo dele em diante
            reta = topo + (o_bin[kq] - topo) * np.minimum(dz / dz[kq], 1.0)
            col = np.maximum(col, reta)
        saida[:, i] = col
    # alisa entre colunas e entre alturas, sem nunca entrar (envelope)
    for _ in range(4):
        s2 = saida.copy()
        s2[:, 1:-1] = (saida[:, :-2] + saida[:, 1:-1] + saida[:, 2:]) / 3
        s2[1:-1, :] = (s2[:-2, :] + s2[1:-1, :] + s2[2:, :]) / 3
        saida = np.maximum(saida, s2)
    return saida


def _grade(nome, xs, zs, ys, lado, material=None):
    """Malha em grade (linhas de cima para baixo), normal para fora."""
    nx, nz = len(xs) - 1, len(zs) - 1
    verts = [(xs[i], ys[k, i], zs[k]) for k in range(nz + 1) for i in range(nx + 1)]
    faces = []
    for k in range(nz):
        for i in range(nx):
            a0 = k * (nx + 1) + i
            f = (a0, a0 + 1, a0 + nx + 2, a0 + nx + 1)
            faces.append(f[::-1] if lado < 0 else f)
    malha = bpy.data.meshes.new(nome)
    malha.from_pydata(verts, [], faces)
    if material is not None:
        malha.materials.append(material)
    obj = bpy.data.objects.new(nome, malha)
    bpy.context.scene.collection.objects.link(obj)
    return obj, verts


def densidade_uv(obj):
    """Unidades de UV por metro na malha (para o pano novo ter a mesma escala de tecido da roupa)."""
    m = obj.data
    uvl = m.uv_layers.active
    if uvl is None or not m.polygons:
        return 0.5
    uv = np.empty(len(m.loops) * 2)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    a3 = au = 0.0
    for p in m.polygons:
        q = uv[list(p.loop_indices)]
        au += 0.5 * abs(float(np.dot(q[:, 0], np.roll(q[:, 1], 1)) - np.dot(q[:, 1], np.roll(q[:, 0], 1))))
        a3 += p.area
    return float(np.sqrt(au / a3)) if a3 > 0 and au > 0 else 0.5


def paineis_franzidos(prefixo, material, corpo, z_cinto, z_barra, largura, colisores, pesos_de, franzido=1.22,
                      folga_cinto=0.026, passo=0.011, quadros=80):
    """Abas da frente e de trás de uma sobreveste/túnica: retângulos de pano mais largos que a cintura,
    presos no cinto (o cinto franze o pano) e caindo pela gravidade sobre as pernas e a armadura.
    `pesos_de(x, t, lado)` devolve {osso: peso} (t = 0 no cinto, 1 na barra). Devolve os objetos."""
    objs = []
    d_uv = densidade_uv(corpo)
    comprimento = z_cinto - z_barra
    nx = max(8, int(round(largura / passo)))
    nz = max(8, int(round(comprimento / passo)))
    us = np.linspace(-0.5, 0.5, nx + 1)
    zs = np.linspace(z_cinto, z_barra, nz + 1)
    pontos = _pontos(colisores, z_cinto, z_barra)
    cintura = _pontos([corpo], z_cinto, z_cinto)
    cintura = cintura[np.abs(cintura[:, 2] - z_cinto) < 0.015]
    for lado, nome in ((-1, "frente"), (1, "tras")):
        xs = us * largura
        # onde o cinto segura: a frente (ou as costas) da cintura medida coluna a coluna, com a folga do
        # cinto; as pontas sem corpo seguem a última coluna medida. Frente e costas planas, abertas dos
        # lados (como a sobreveste histórica). O mesmo perfil vira o colisor liso, então a borda presa
        # nunca nasce dentro dele.
        topo = np.full(len(xs), np.nan)
        for i, x in enumerate(xs):
            q = cintura[np.abs(cintura[:, 0] - x) < 0.02]
            if len(q):
                topo[i] = float((q[:, 1] * lado).max()) + folga_cinto
        ok = ~np.isnan(topo)
        topo = np.interp(xs, xs[ok], topo[ok]) if ok.any() else np.full(len(xs), 0.12 + folga_cinto)
        saida = perfil_pendurado(pontos, lado, xs, zs, topo)
        # a borda de cima franzida: as colunas apertadas na largura da cintura, em cima do perfil
        x_alvo = us * largura / franzido
        arco = [Vector((x, lado * float(np.interp(x, xs, saida[0])), z_cinto)) for x in x_alvo]
        # colisor liso e invisível: o pano desliza sobre ele (bater direto na cota e nas placas amassava);
        # perto do cinto o colisor recua para dentro do caminho do pano (a borda presa fica por fora dele;
        # se o pano nascesse cruzando a borda do colisor, a simulação explodia)
        recuo = 0.022 * (1.0 - _sstep(0.0, 0.1, (zs[0] - zs)))[:, None]
        colisor, _ = _grade(f"{prefixo}_colisor_{nome}", xs, zs[1:], lado * (saida[1:] + 0.006 - recuo[1:]), lado)
        # o pano nasce logo fora do colisor
        ys = lado * (saida + 0.02)
        verts, faces, uvs, alvo = [], [], [], []
        for k in range(nz + 1):
            t = k / nz
            z = zs[k]
            for i in range(nx + 1):
                verts.append((xs[i], ys[k, i], z))
                uvs.append((0.5 + xs[i] * d_uv, 0.5 - comprimento * t * d_uv))
                a = arco[i]
                alvo.append((a.x, a.y, z) if k == 0 else (xs[i], ys[k, i], z))
        for k in range(nz):
            for i in range(nx):
                a0 = k * (nx + 1) + i
                f = (a0, a0 + 1, a0 + nx + 2, a0 + nx + 1)
                faces.append(f[::-1] if lado < 0 else f)  # normal para fora
        malha = bpy.data.meshes.new(f"{prefixo}_aba_{nome}")
        malha.from_pydata(verts, [], faces)
        uv = malha.uv_layers.new(name="UVMap")
        lv = np.empty(len(malha.loops), dtype=np.int64)
        malha.loops.foreach_get("vertex_index", lv)
        uv.data.foreach_set("uv", np.array(uvs, dtype=np.float32)[lv].ravel())
        for p_ in malha.polygons:
            p_.use_smooth = True
        # marca as faces da aba (1 frente, 2 costas): desenhos (cruz, brasão) são recortados pela posição
        # do pano antes de cair, guardada no UV, e acompanham as dobras como um bordado
        at = malha.attributes.new("aba", "INT", "FACE")
        at.data.foreach_set("value", [1 if lado < 0 else 2] * len(malha.polygons))
        malha.materials.append(material)
        obj = bpy.data.objects.new(malha.name, malha)
        bpy.context.scene.collection.objects.link(obj)
        # pesos de osso (antes do caimento: dependem da posição de origem)
        grupos = {}
        for vi, (x, _, z) in enumerate(verts):
            for osso, w in pesos_de(x, (z_cinto - z) / comprimento, lado).items():
                if w <= 0:
                    continue
                if osso not in grupos:
                    grupos[osso] = obj.vertex_groups.new(name=osso)
                grupos[osso].add([vi], float(w), "REPLACE")
        # o cinto franze a borda de cima (chave animada) e ela fica presa
        obj.shape_key_add(name="Basis", from_mix=False)
        kb = obj.shape_key_add(name="cinto", from_mix=False)
        kb.data.foreach_set("co", np.array(alvo, dtype=np.float64).ravel())
        kb.value = 0.0
        kb.keyframe_insert("value", frame=1)
        kb.value = 1.0
        kb.keyframe_insert("value", frame=14)
        z_vert = np.array([v[2] for v in verts])
        grupo_de_pinos(obj, "pinos_pano", (z_vert > z_cinto - 0.5 * passo).astype(float))
        # lã grossa: quase não estica e dobra em vincos largos (dobra baixa = papel amassado)
        drapear(obj, [colisor], "pinos_pano", quadros=quadros, qualidade=8, massa=0.5, rigidez=30.0, dobra=12.0, auto_colisao=True,
                atrito=1.0)
        cf = _coords(obj)
        print(f"[pano] aba {nome}: altura {cf[:, 2].min():.2f}-{cf[:, 2].max():.2f} m, largura {cf[:, 0].max() - cf[:, 0].min():.2f} m")
        bpy.data.objects.remove(colisor, do_unlink=True)
        objs.append(obj)
    return objs


def posicao_plana(z_cinto, d_uv):
    """Função (u, v) -> (x, z) do pano das abas antes de cair (inversa do UV de `paineis_franzidos`)."""
    return lambda u, v: ((u - 0.5) / d_uv, z_cinto - (0.5 - v) / d_uv)


def juntar(destino, outros):
    """Junta as malhas em `destino` (grupos de osso e UV pelo nome)."""
    outros = [o for o in outros if o is not None]
    if not outros:
        return destino
    for o in bpy.context.scene.objects:
        o.select_set(o == destino or o in outros)
    bpy.context.view_layer.objects.active = destino
    bpy.ops.object.join()
    return destino


def capa_caindo(obj, topo_z, colisores, quadros=70):
    """Capa presa no alto (gola/ombros) caindo pelas costas por cima da roupa e da armadura.
    Nasce fora de tudo e desliza sobre um colisor liso das costas (o mesmo "barbante esticado")."""
    co = _coords(obj)
    if len(co) == 0:
        return obj
    x0, x1 = float(co[:, 0].min()), float(co[:, 0].max())
    z_baixo = float(co[:, 2].min())
    xs = np.linspace(x0 - 0.02, x1 + 0.02, 48)
    zs = np.linspace(topo_z, z_baixo - 0.05, max(8, int((topo_z - z_baixo + 0.05) / 0.012)))
    pontos = _pontos(colisores, topo_z, z_baixo)
    topo_y = float(co[co[:, 2] > topo_z - 0.01, 1].max()) if (co[:, 2] > topo_z - 0.01).any() else float(co[:, 1].min())
    saida = perfil_pendurado(pontos, 1, xs, zs, np.full(len(xs), topo_y))
    # cada vértice da capa vai para fora do perfil (interpolação na grade)
    fx = np.interp(co[:, 0], xs, np.arange(len(xs)))
    fz = np.interp(-co[:, 2], -zs, np.arange(len(zs)))
    i0, k0 = np.floor(fx).astype(int), np.floor(fz).astype(int)
    i1, k1 = np.minimum(i0 + 1, len(xs) - 1), np.minimum(k0 + 1, len(zs) - 1)
    tx, tz = fx - i0, fz - k0
    sv = (saida[k0, i0] * (1 - tx) * (1 - tz) + saida[k0, i1] * tx * (1 - tz) + saida[k1, i0] * (1 - tx) * tz
          + saida[k1, i1] * tx * tz)
    presa = co[:, 2] > topo_z - 0.02
    co[:, 1] = np.where(presa, co[:, 1], np.maximum(co[:, 1], sv + 0.02))
    obj.data.vertices.foreach_set("co", co.ravel())
    obj.data.update()
    recuo = 0.022 * (1.0 - _sstep(0.0, 0.12, (zs[0] - zs)))[:, None]
    colisor, _ = _grade(f"{obj.name}_colisor", xs, zs[1:], saida[1:] + 0.006 - recuo[1:], 1)
    w = _sstep(topo_z - 0.06, topo_z - 0.015, co[:, 2])
    grupo_de_pinos(obj, "pinos_pano", w)
    drapear(obj, [colisor], "pinos_pano", quadros=quadros, massa=0.5, rigidez=30.0, dobra=10.0, qualidade=8, atrito=1.0)
    bpy.data.objects.remove(colisor, do_unlink=True)
    return obj


# ------------------------------------------------------------------ desgaste do pano (textura única)


def _atributo_borda(obj):
    """Atributo "borda": distância (m) de cada vértice até a borda aberta mais perto (bainha)."""
    from mathutils.kdtree import KDTree
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    borda = [v.co.copy() for v in bm.verts if v.is_boundary]
    bm.free()
    at = obj.data.attributes.get("borda") or obj.data.attributes.new("borda", "FLOAT", "POINT")
    if not borda:
        at.data.foreach_set("value", [1.0] * len(obj.data.vertices))
        return
    kd = KDTree(len(borda))
    for i, c in enumerate(borda):
        kd.insert(c, i)
    kd.balance()
    at.data.foreach_set("value", [kd.find(v.co)[2] for v in obj.data.vertices])


def assar_desgaste_pano(obj, nome, z_chao=0.0, res=2048, cor_lama=(0.24, 0.15, 0.07)):
    """Textura única da peça: o tecido original com lama subindo da barra (com manchas), sujeira nas
    dobras (oclusão), faixa de bainha mais escura junto às bordas e rugosidade de acordo. Cor, normal e
    rugosidade assadas num atlas próprio; a peça sai com um material só de imagens (o glb leva isso)."""
    m = obj.data
    if not m.polygons or not m.uv_layers:
        return None
    _atributo_borda(obj)
    # a lama sobe da barra da própria peça (uma sobreveste a meia canela não toca o chão, mas é ali
    # que os respingos e a sujeira se juntam)
    zs = [(obj.matrix_world @ v.co).z for v in m.vertices]
    z_chao = max(z_chao, min(zs) - 0.06)
    uv_orig = m.uv_layers.active.name
    atlas = m.uv_layers.new(name="atlas")
    m.uv_layers.active = atlas
    _ativo(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    m.uv_layers[uv_orig].active_render = True
    imgs = {k: bpy.data.images.new(f"{nome}_{k}", res, res, alpha=False) for k in ("cor", "rugosidade", "normal")}
    for k in ("rugosidade", "normal"):
        imgs[k].colorspace_settings.name = "Non-Color"
    preps = []
    for ms in obj.material_slots:
        mat = ms.material
        if not mat or not mat.use_nodes:
            continue
        nt = mat.node_tree
        saida = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        # as texturas do tecido seguem no UV original
        for n in nt.nodes:
            if n.type in ("TEX_IMAGE", "NORMAL_MAP"):
                if n.type == "NORMAL_MAP":
                    n.uv_map = uv_orig
                for e in n.inputs:
                    if e.name == "Vector" and not e.is_linked:
                        uvn = nt.nodes.new("ShaderNodeUVMap")
                        uvn.uv_map = uv_orig
                        nt.links.new(uvn.outputs["UV"], e)

        def fonte(nome_e, padrao):
            e = bsdf.inputs[nome_e]
            if e.is_linked:
                return e.links[0].from_socket
            rgb = nt.nodes.new("ShaderNodeRGB")
            v = e.default_value
            rgb.outputs[0].default_value = (v[0], v[1], v[2], 1.0) if hasattr(v, "__len__") else (v, v, v, 1.0)
            return rgb.outputs[0]

        cor0, rug0 = fonte("Base Color", None), fonte("Roughness", None)
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
        # lama: mancha que sobe da barra até ~30 cm com a borda irregular (a água sobe pelo tecido de
        # forma desigual), mais forte embaixo; acima dela, pingos finos e esparsos
        def ruido(escala, detalhe, de, ate, ate_saida=1.0, de_saida=0.0):
            r = nt.nodes.new("ShaderNodeTexNoise")
            r.inputs["Scale"].default_value = escala
            r.inputs["Detail"].default_value = detalhe
            nt.links.new(geo.outputs["Position"], r.inputs["Vector"])
            f = nt.nodes.new("ShaderNodeMapRange")
            f.inputs["From Min"].default_value = de
            f.inputs["From Max"].default_value = ate
            f.inputs["To Min"].default_value = de_saida
            f.inputs["To Max"].default_value = ate_saida
            nt.links.new(r.outputs["Fac"], f.inputs["Value"])
            return f.outputs["Result"]

        def faixa(z, z_baixo, z_alto, expoente):
            r = nt.nodes.new("ShaderNodeMapRange")
            r.interpolation_type = "SMOOTHSTEP"
            r.inputs["From Min"].default_value = z_alto
            r.inputs["From Max"].default_value = z_baixo
            nt.links.new(z, r.inputs["Value"])
            return op("POWER", r.outputs["Result"], expoente)

        def op(tipo, a, b, clamp=True):
            n = nt.nodes.new("ShaderNodeMath")
            n.operation = tipo
            n.use_clamp = clamp
            for i, v in enumerate((a, b)):
                if isinstance(v, float):
                    n.inputs[i].default_value = v
                else:
                    nt.links.new(v, n.inputs[i])
            return n.outputs[0]

        z_torto = op("ADD", sep.outputs["Z"], ruido(7.0, 5.0, 0.3, 0.7, 0.045, -0.045), clamp=False)
        mancha = faixa(z_torto, z_chao + 0.05, z_chao + 0.3, 1.3)
        lama_barra = op("MULTIPLY", mancha, ruido(2.5, 4.0, 0.3, 0.7, 1.0, 0.6))
        pingos = op("MULTIPLY", faixa(sep.outputs["Z"], z_chao + 0.06, z_chao + 0.42, 1.5), ruido(220.0, 2.0, 0.62, 0.68))
        f_lama_no = nt.nodes.new("ShaderNodeMath")
        f_lama_no.operation = "MAXIMUM"
        f_lama_no.use_clamp = True
        nt.links.new(lama_barra, f_lama_no.inputs[0])
        nt.links.new(op("MULTIPLY", pingos, 0.6), f_lama_no.inputs[1])
        f_lama = f_lama_no
        # dobras: oclusão
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.samples = 8
        ao.inputs["Distance"].default_value = 0.05
        vao = nt.nodes.new("ShaderNodeMath")
        vao.operation = "SUBTRACT"
        vao.inputs[0].default_value = 1.0
        nt.links.new(ao.outputs["AO"], vao.inputs[1])
        # bainha: faixa a 0,6–2 cm da borda
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "borda"
        bainha = nt.nodes.new("ShaderNodeMapRange")
        bainha.interpolation_type = "SMOOTHSTEP"
        bainha.inputs["From Min"].default_value = 0.024
        bainha.inputs["From Max"].default_value = 0.014
        nt.links.new(attr.outputs["Fac"], bainha.inputs["Value"])
        # cor = tecido × (1 − 0,35·dobra) × (1 − 0,18·bainha), misturado com lama
        k1 = nt.nodes.new("ShaderNodeMath")
        k1.operation = "MULTIPLY_ADD"
        nt.links.new(vao.outputs[0], k1.inputs[0])
        k1.inputs[1].default_value = -0.5
        k1.inputs[2].default_value = 1.0
        k2 = nt.nodes.new("ShaderNodeMath")
        k2.operation = "MULTIPLY_ADD"
        nt.links.new(bainha.outputs["Result"], k2.inputs[0])
        k2.inputs[1].default_value = -0.25
        k2.inputs[2].default_value = 1.0
        k = nt.nodes.new("ShaderNodeMath")
        k.operation = "MULTIPLY"
        nt.links.new(k1.outputs[0], k.inputs[0])
        nt.links.new(k2.outputs[0], k.inputs[1])
        escuro = nt.nodes.new("ShaderNodeMix")
        escuro.data_type = "RGBA"
        escuro.blend_type = "MULTIPLY"
        escuro.inputs["Factor"].default_value = 1.0
        nt.links.new(cor0, escuro.inputs[6])
        cinza = nt.nodes.new("ShaderNodeCombineColor")
        for canal in ("Red", "Green", "Blue"):
            nt.links.new(k.outputs[0], cinza.inputs[canal])
        nt.links.new(cinza.outputs["Color"], escuro.inputs[7])
        com_lama = nt.nodes.new("ShaderNodeMix")
        com_lama.data_type = "RGBA"
        f75 = nt.nodes.new("ShaderNodeMath")
        f75.operation = "MULTIPLY"
        f75.inputs[1].default_value = 0.88
        nt.links.new(f_lama.outputs[0], f75.inputs[0])
        nt.links.new(f75.outputs[0], com_lama.inputs["Factor"])
        nt.links.new(escuro.outputs[2], com_lama.inputs[6])
        com_lama.inputs[7].default_value = (*cor_lama, 1.0)
        rug = nt.nodes.new("ShaderNodeMix")
        rug.data_type = "FLOAT"
        nt.links.new(f_lama.outputs[0], rug.inputs["Factor"])
        nt.links.new(rug0, rug.inputs[2])
        rug.inputs[3].default_value = 0.95
        emi = nt.nodes.new("ShaderNodeEmission")
        alvo = nt.nodes.new("ShaderNodeTexImage")
        uva = nt.nodes.new("ShaderNodeUVMap")
        uva.uv_map = "atlas"
        nt.links.new(uva.outputs["UV"], alvo.inputs["Vector"])
        preps.append({"nt": nt, "saida": saida, "bsdf": bsdf, "emi": emi, "alvo": alvo, "cor": com_lama.outputs[2], "rug": rug.outputs[0]})
    if not preps:
        return None
    cena = bpy.context.scene
    motor, amostras = cena.render.engine, cena.cycles.samples
    cena.render.engine = "CYCLES"
    cena.cycles.samples = 8
    try:
        cena.cycles.device = "CPU"
    except Exception:
        pass
    _ativo(obj)

    def assar(tipo, img):
        for p_ in preps:
            p_["alvo"].image = img
            p_["nt"].nodes.active = p_["alvo"]
        bpy.ops.object.bake(type=tipo, margin=6, use_clear=True, normal_space="TANGENT", uv_layer="atlas")

    try:
        for p_ in preps:
            p_["nt"].links.new(p_["cor"], p_["emi"].inputs["Color"])
            p_["nt"].links.new(p_["emi"].outputs["Emission"], p_["saida"].inputs["Surface"])
        assar("EMIT", imgs["cor"])
        for p_ in preps:
            p_["nt"].links.new(p_["rug"], p_["emi"].inputs["Color"])
        assar("EMIT", imgs["rugosidade"])
        for p_ in preps:
            p_["nt"].links.new(p_["bsdf"].outputs["BSDF"], p_["saida"].inputs["Surface"])
        assar("NORMAL", imgs["normal"])
    finally:
        cena.render.engine, cena.cycles.samples = motor, amostras
    for img in imgs.values():
        img.pack()
    final = bpy.data.materials.new(f"{nome}_pano")
    final.use_nodes = True
    fnt = final.node_tree
    fb = next(n for n in fnt.nodes if n.type == "BSDF_PRINCIPLED")
    for chave, entrada in (("cor", "Base Color"), ("rugosidade", "Roughness")):
        t = fnt.nodes.new("ShaderNodeTexImage")
        t.image = imgs[chave]
        fnt.links.new(t.outputs["Color"], fb.inputs[entrada])
    tn = fnt.nodes.new("ShaderNodeTexImage")
    tn.image = imgs["normal"]
    nm = fnt.nodes.new("ShaderNodeNormalMap")
    fnt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    fnt.links.new(nm.outputs["Normal"], fb.inputs["Normal"])
    m.materials.clear()
    m.materials.append(final)
    for p in m.polygons:
        p.material_index = 0
    # fica só o atlas (o glb leva um UV, o da textura única)
    m.uv_layers.remove(m.uv_layers[uv_orig])
    m.uv_layers.active = m.uv_layers["atlas"]
    if "borda" in m.attributes:
        m.attributes.remove(m.attributes["borda"])
    return final
