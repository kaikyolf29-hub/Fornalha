# Fornalha: comparação com a referência. A imagem que a pessoa mandou (personagem, arma, casa, mapa) e o
# resultado (um GLB renderizado na mesma vista, ou uma imagem/captura da engine) lado a lado, com medidas
# que a IA usa para ajustar e tentar de novo: paleta das duas, diferença de cor e proporção da silhueta.
import os

import bpy
import numpy as np

import fc_comum as c

VISTAS = {"frente": (0, -1, 0.12), "lado": (1, 0, 0.12), "costas": (0, 1, 0.12), "tres_quartos": (0.7, -1, 0.2), "cima": (0.0, -0.4, 1.0)}


def _carregar(caminho):
    img = bpy.data.images.load(caminho)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1]  # linha 0 em cima


def _redimensionar(px, altura):
    h, w = px.shape[:2]
    nw = max(1, int(round(w * altura / h)))
    ys = (np.arange(altura) * h / altura).astype(int)
    xs = (np.arange(nw) * w / nw).astype(int)
    return px[ys][:, xs]


def _frente(px):
    """Máscara do assunto: o que difere do fundo. O fundo sai da metade de cima das laterais e da linha de
    cima (o assunto costuma encostar embaixo); faixa preta de cinema (letterbox) também é fundo."""
    rgb = px[..., :3]
    h = rgb.shape[0]
    escura = lambda a: a.max(axis=-1) < 0.06  # noqa: E731
    linhas = [r for r in range(h) if escura(rgb[r]).mean() > 0.97]
    topo = next((r for r in range(h) if r not in linhas), 0)
    amostra = np.concatenate([rgb[topo, :], rgb[topo:h // 2, 0], rgb[topo:h // 2, -1]])
    amostra = amostra[~escura(amostra)] if (~escura(amostra)).sum() > 10 else amostra
    fundo = np.median(amostra, axis=0)
    d = np.linalg.norm(rgb - fundo, axis=-1)
    mask = d > max(0.08, float(np.percentile(d, 40)) * 0.5)
    if linhas:
        faixa = np.zeros(h, bool)
        faixa[linhas] = True
        mask &= ~faixa[:, None]
    if px.shape[-1] == 4 and float(px[..., 3].min()) < 0.5:
        mask &= px[..., 3] > 0.5
    return mask


def _paleta(px, mask, k=5, semente=1):
    """k cores principais (k-means simples) com a fração de cada uma, em hex."""
    cores = px[..., :3][mask]
    if len(cores) < k:
        return []
    rng = np.random.default_rng(semente)
    amostra = cores[rng.choice(len(cores), min(len(cores), 20000), replace=False)]
    centros = amostra[rng.choice(len(amostra), k, replace=False)]
    for _ in range(12):
        lab = np.argmin(((amostra[:, None, :] - centros[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            if (lab == j).any():
                centros[j] = amostra[lab == j].mean(0)
    frac = np.bincount(lab, minlength=k) / len(lab)
    ordem = np.argsort(-frac)
    return [{"cor": "#%02x%02x%02x" % tuple(int(v * 255) for v in np.clip(centros[i], 0, 1)), "fracao": round(float(frac[i]), 3),
             "_rgb": centros[i]} for i in ordem]


def _diferenca(p1, p2):
    """Distância média (0 = igual) entre as paletas, pesada pela fração (cada cor procura a mais perto)."""
    if not p1 or not p2:
        return None
    a = np.array([q["_rgb"] for q in p1])
    b = np.array([q["_rgb"] for q in p2])
    fa = np.array([q["fracao"] for q in p1])
    fb = np.array([q["fracao"] for q in p2])
    d = np.linalg.norm(a[:, None] - b[None], axis=-1)
    return round(float((d.min(1) * fa).sum() / fa.sum() + (d.min(0) * fb).sum() / fb.sum()) / 2, 3)


def _silhueta(mask):
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    return {"altura_sobre_largura": round(float(h / w), 3), "preenchimento": round(float(mask.sum() / (h * w)), 3)}


def _pose_parada(arm):
    """A foto de referência é de alguém parado: o personagem entra na animação de parado (quadro 1) ou,
    sem ela, na pose de repouso. O importador deixa ativa a primeira animação do arquivo (que pode ser um
    golpe, agachado e virado)."""
    ad = arm.animation_data
    acoes = [a for a in bpy.data.actions if a.users or a.use_fake_user]
    parado = next((a for a in acoes if a.name.lower().split("|")[-1] in ("parado", "idle")), None) or \
        next((a for a in acoes if "parado" in a.name.lower() or "idle" in a.name.lower()), None)
    if ad is not None:
        ad.action = parado
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()


def _bracos_para_baixo(arm, folga_graus=22.0):
    """Pose em T/A → braços quase junto do corpo (como nas fotos de referência): o braço gira em volta
    da frente até ficar a `folga_graus` da vertical."""
    from mathutils import Matrix, Vector

    for pb in arm.pose.bones:
        n = pb.name.lower()
        if not ("upperarm" in n or n in ("leftarm", "rightarm") or n.endswith(("upper_arm.l", "upper_arm.r"))):
            continue
        bpy.context.view_layer.update()
        cabeca = arm.matrix_world @ pb.head
        cauda = arm.matrix_world @ pb.tail
        d = (cauda - cabeca).normalized()
        baixo = Vector((0, 0, -1))
        ang = d.angle(baixo) - np.radians(folga_graus)
        if ang <= 0:
            continue
        eixo = d.cross(baixo)
        if eixo.length < 1e-6:
            continue
        R = Matrix.Rotation(ang, 4, eixo.normalized())
        mw = arm.matrix_world
        giro = mw.inverted() @ Matrix.Translation(cabeca) @ R @ Matrix.Translation(-cabeca) @ mw
        pb.matrix = giro @ pb.matrix


def tarefa(t):
    ref, arq, saida = t["referencia"], t["arquivo"], t["saida"]
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    if arq.lower().endswith((".glb", ".gltf", ".obj", ".fbx")):
        antes = set(bpy.data.objects)
        if arq.lower().endswith((".glb", ".gltf")):
            bpy.ops.import_scene.gltf(filepath=arq)
            c.tirar_ajudantes_do_gltf()
        elif arq.lower().endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=arq)
        else:
            bpy.ops.import_scene.fbx(filepath=arq)
        objs = [o for o in bpy.data.objects if o not in antes and o.type == "MESH"]
        for arm in [o for o in bpy.data.objects if o not in antes and o.type == "ARMATURE"]:
            _pose_parada(arm)
            _bracos_para_baixo(arm)
        bpy.context.view_layer.update()
        refpx = _carregar(ref)
        h, w = refpx.shape[:2]
        escala = 900 / max(h, w)
        render = saida + ".render.png"
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        pts = np.array([(o.matrix_world @ v.co)[:] for o in objs for v in o.evaluated_get(dg).to_mesh().vertices])
        zmin, zmax = float(pts[:, 2].min()), float(pts[:, 2].max())
        # enquadramento como o da referência: corpo inteiro, busto (cabeça e ombros) ou rosto
        enq = t.get("enquadramento", "auto")
        if enq == "auto":
            sa = _silhueta(_frente(refpx))
            enq = "busto" if (zmax - zmin) > 1.2 and sa and sa["altura_sobre_largura"] < 1.8 else "corpo"
        t["_enq_usado"] = enq
        frac = {"corpo": 1.0, "meio_corpo": 0.3, "busto": 0.27, "rosto": 0.13}.get(enq, 1.0)
        regiao = pts[pts[:, 2] >= zmax - (zmax - zmin) * frac]
        if enq in ("meio_corpo", "busto", "rosto"):
            # sem os braços abertos da pose em T: só a largura dos ombros (ou da cabeça) em volta do meio
            cx, cy = np.median(regiao[:, 0]), np.median(regiao[:, 1])
            meia = {"meio_corpo": 0.25, "busto": 0.26}.get(enq, 0.12)
            regiao = regiao[(np.abs(regiao[:, 0] - cx) < meia) & (np.abs(regiao[:, 1] - cy) < 0.25)]
        me = bpy.data.meshes.new("enquadramento")
        me.from_pydata([tuple(regiao.min(0)), tuple(regiao.max(0))], [], [])
        alvo = bpy.data.objects.new("enquadramento", me)
        bpy.context.scene.collection.objects.link(alvo)
        alvo.hide_render = True
        c.renderizar(render, [alvo], direcao=VISTAS.get(t.get("vista", "frente"), VISTAS["frente"]),
                     largura=max(64, int(w * escala)), altura=max(64, int(h * escala)), amostras=int(t.get("amostras", 24)), chao=False)
        modelo = _carregar(render)
    else:
        modelo = _carregar(arq)
        refpx = _carregar(ref)
    altura = 700
    a, b = _redimensionar(refpx, altura), _redimensionar(modelo, altura)
    ma, mb = _frente(a), _frente(b)
    pa, pb = _paleta(a, ma), _paleta(b, mb)
    lado = np.concatenate([a[..., :3], np.full((altura, 12, 3), 0.1, np.float32), b[..., :3]], axis=1)
    rgba = np.concatenate([lado, np.ones(lado.shape[:2] + (1,), np.float32)], -1)[::-1]
    img = bpy.data.images.new("comparacao", lado.shape[1], altura, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(rgba).ravel())
    img.filepath_raw = saida
    img.file_format = "PNG"
    img.save()
    sa, sb = _silhueta(ma), _silhueta(mb)
    dica = []
    dif = _diferenca(pa, pb)
    if dif is not None and dif > 0.12:
        dica.append("as cores estão longe da referência: ajuste as cores (roupa, cabelo, pele, paleta) pela paleta da referência")
    if sa and sb and abs(sa["altura_sobre_largura"] - sb["altura_sobre_largura"]) / sa["altura_sobre_largura"] > 0.15:
        dica.append("a proporção da silhueta difere: ajuste porte/altura/peso (personagem) ou a forma (arma, casa)")
    limpa = lambda p: [{k: v for k, v in q.items() if k != "_rgb"} for q in p]  # noqa: E731
    return {"arquivos": {"comparacao": saida}, "enquadramento": t.get("_enq_usado"), "paleta_referencia": limpa(pa), "paleta_resultado": limpa(pb), "diferenca_de_cor": dif,
            "silhueta_referencia": sa, "silhueta_resultado": sb,
            "dica": "; ".join(dica) or "perto da referência nas cores e na proporção: olhe a imagem lado a lado para os detalhes"}
