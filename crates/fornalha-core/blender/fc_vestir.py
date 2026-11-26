# Fornalha: roupa por cima. Primeiro o movimento (no corpo, conferido); depois a roupa: a malha de roupa
# ou armadura (da IA, de pacote, feita à mão) recebe os pesos do corpo que já se mexe certo, pela
# superfície mais próxima (fc_molde.transferir). Cada peça pequena e de um osso só (placa de armadura,
# ombreira, manopla, elmo) fica rígida nesse osso, como se pesa armadura em jogo; o pano grande (capa,
# sobreveste, saia) dobra com o corpo.
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import fc_molde


def _juntar_copias(objs, nome):
    """Uma malha só com as cópias do corpo (para servir de molde dos pesos), na pose de descanso."""
    copias = []
    for o in objs:
        c = o.copy()
        c.data = o.data.copy()
        c.modifiers.clear()
        c.parent = None
        c.matrix_world = o.matrix_world.copy()
        bpy.context.scene.collection.objects.link(c)
        copias.append(c)
    for o in bpy.context.scene.objects:
        o.select_set(o in copias)
    bpy.context.view_layer.objects.active = copias[0]
    if len(copias) > 1:
        bpy.ops.object.join()
    m = bpy.context.view_layer.objects.active
    m.name = nome
    return m


def encaixar(roupa, corpo):
    """Leva a roupa para o tamanho e o lugar do corpo (altura, centro e chão) quando ela veio de outro lugar."""
    import fc_comum as c

    mn_c, mx_c = c.caixa_envolvente(corpo)
    mn_r, mx_r = c.caixa_envolvente(roupa)
    hc, hr = mx_c.z - mn_c.z, mx_r.z - mn_r.z
    if hr < 1e-6:
        return 1.0
    s = hc / hr
    centro_c = Vector(((mn_c.x + mx_c.x) / 2, (mn_c.y + mx_c.y) / 2, mn_c.z))
    centro_r = Vector(((mn_r.x + mx_r.x) / 2, (mn_r.y + mx_r.y) / 2, mn_r.z))
    M = Matrix.Translation(centro_c) @ Matrix.Scale(s, 4) @ Matrix.Translation(-centro_r)
    for o in roupa:
        o.matrix_world = M @ o.matrix_world
    bpy.context.view_layer.update()
    return s


PERNA_NO_PANO = 0.4  # quanto da perna a saia/capa ainda segue


def vestir(arm, corpo, roupa, H, rigido="auto"):
    """corpo: malhas do personagem com pesos; roupa: malhas novas. Devolve o resumo."""
    pose = arm.data.pose_position
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    nomes = sorted({g.name for o in corpo for g in o.vertex_groups if g.name in arm.data.bones})
    if not nomes:
        raise ValueError("o corpo não tem pesos nos ossos: monte o esqueleto antes de vestir")
    molde = _juntar_copias(corpo, "molde_da_roupa")
    resumo = {"pecas": [], "ilhas_rigidas": 0, "ilhas_de_pano": 0, "placas": []}
    # o adorno colado (cruz na saia, fivela no cinto) vem depois da peça dele e copia os pesos dela:
    # assim a cruz anda com a saia e não estica entre as duas coxas
    roupa = sorted(roupa, key=lambda o: 1 if o.get("colado_em") else 0)
    feitos = {}
    try:
        for o in roupa:
            dono = feitos.get(o.get("colado_em") or "")
            if dono is not None:
                from mathutils.kdtree import KDTree

                Wd, cod = dono
                kd = KDTree(len(cod))
                for i, q in enumerate(cod):
                    kd.insert(q, i)
                kd.balance()
                co_o = fc_molde._co(o)
                W = np.array([Wd[kd.find(q)[1]] for q in co_o])
                fc_molde.gravar_pesos(o, nomes, W)
                for m in list(o.modifiers):
                    if m.type == "ARMATURE":
                        o.modifiers.remove(m)
                mundo = o.matrix_world.copy()
                o.parent = arm
                o.matrix_parent_inverse = arm.matrix_world.inverted()
                o.matrix_world = mundo
                mod = o.modifiers.new("esqueleto", "ARMATURE")
                mod.object = arm
                resumo["pecas"].append({"nome": o.name, "vertices": len(o.data.vertices), "colado_em": dono and o.get("colado_em")})
                continue
            W, _ = fc_molde.transferir(molde, o, nomes, H)
            if o.get("pano_solto") and len(W):
                # saia e capa seguem o quadril; das pernas fica só um pouco (o pano não gruda na coxa e a
                # barra não varre o chão quando a perna vai para a frente ou para trás)
                pernas = [i for i, n in enumerate(nomes) if n.startswith(("thigh", "calf", "foot", "ball", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"))]
                quadril = next((i for i, n in enumerate(nomes) if n in ("pelvis", "Hips")), None)
                if pernas and quadril is not None:
                    tirado = W[:, pernas].sum(1) * (1.0 - PERNA_NO_PANO)
                    W[:, pernas] *= PERNA_NO_PANO
                    W[:, quadril] += tirado
                    resumo.setdefault("pano_solto", []).append(o.name)
            if rigido != "nao":
                co = fc_molde._co(o)
                ilhas = np.zeros(len(co), dtype=np.int64) if o.get("peca_inteira") else fc_molde._ilhas(o)
                for k in np.unique(ilhas):
                    idx = np.nonzero(ilhas == k)[0]
                    soma = W[idx].sum(0)
                    if soma.sum() <= 0:
                        continue
                    dono = int(np.argmax(soma))
                    parte = float(soma[dono] / soma.sum())
                    tamanho = float(np.ptp(co[idx], axis=0).max()) if len(idx) > 1 else 0.0
                    # placa: de um osso só e pequena; pano: grande ou dividida entre ossos
                    # placa: de um osso só e pequena (a malha da IA), ou marcada rígida no create_garment
                    placa = not o.get("pano_solto") and (rigido == "sim" or bool(o.get("rigido"))
                                                         or (parte > 0.55 and tamanho < 0.3 * H and len(idx) < 6000))
                    if placa:
                        W[idx] = 0.0
                        W[idx, dono] = 1.0
                        resumo["ilhas_rigidas"] += 1
                        resumo["placas"].append({"osso": nomes[dono], "vertices": int(len(idx)), "tamanho_cm": round(tamanho * 100, 1)})
                    else:
                        resumo["ilhas_de_pano"] += 1
            fc_molde.gravar_pesos(o, nomes, W)
            feitos[o.name] = (W, fc_molde._co(o))
            for m in list(o.modifiers):
                if m.type == "ARMATURE":
                    o.modifiers.remove(m)
            mundo = o.matrix_world.copy()
            o.parent = arm
            o.matrix_parent_inverse = arm.matrix_world.inverted()
            o.matrix_world = mundo
            mod = o.modifiers.new("esqueleto", "ARMATURE")
            mod.object = arm
            dono_geral = nomes[int(np.argmax(W.sum(0)))] if len(W) else None
            resumo["pecas"].append({"nome": o.name, "vertices": len(o.data.vertices), "osso_principal": dono_geral})
        resumo["pele_escondida"] = esconder_pele_coberta(corpo, [o for o in roupa if not o.get("pano_solto")])
    finally:
        bpy.data.objects.remove(molde, do_unlink=True)
        arm.data.pose_position = pose
    return resumo


def esconder_pele_coberta(corpo, justas, folga=0.05):
    """Tira do corpo a pele que a roupa justa cobre (como os jogos fazem): no movimento a pele não fura a
    cota, a calça nem a armadura. Só apaga o que está coberto por fora a até `folga` metros pela normal;
    pano solto (saia, capa) não conta, porque mexe e mostraria o buraco. Devolve quantos vértices saíram."""
    from mathutils.bvhtree import BVHTree

    if not justas:
        return 0
    dg = bpy.context.evaluated_depsgraph_get()
    arvores = [BVHTree.FromObject(o, dg, deform=True) for o in justas]
    mundos = [(o.matrix_world.copy(), o.matrix_world.inverted()) for o in justas]
    total = 0
    pele = [o for o in corpo if any(k in o.name.lower() for k in ("corpo", "body", "pele"))] or corpo[:1]
    for o in pele:
        mw = o.matrix_world
        rot = mw.to_3x3()
        coberto = []
        for v in o.data.vertices:
            p = mw @ v.co
            n = (rot @ v.normal).normalized()
            achou = False
            for arv, (M, Mi) in zip(arvores, mundos):
                # por fora (a roupa por cima) e um pouco por dentro (casca que afundou na pele)
                loc, _, _, _ = arv.ray_cast(Mi @ (p - n * 0.002), (Mi.to_3x3() @ n).normalized(), folga)
                if loc is None:
                    loc, _, _, _ = arv.ray_cast(Mi @ (p + n * 0.002), (Mi.to_3x3() @ -n).normalized(), 0.02)
                if loc is not None:
                    achou = True
                    break
            coberto.append(achou)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.verts.ensure_lookup_table()
        tirar = [f for f in bm.faces if all(coberto[v.index] for v in f.verts)]
        if tirar:
            bmesh.ops.delete(bm, geom=tirar, context="FACES")
            bm.to_mesh(o.data)
            o.data.update()
        bm.free()
        total += sum(coberto)
    return total
