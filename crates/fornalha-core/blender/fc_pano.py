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
