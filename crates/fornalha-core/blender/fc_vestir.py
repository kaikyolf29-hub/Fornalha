# Fornalha: roupa por cima. Primeiro o movimento (no corpo, conferido); depois a roupa: a malha de roupa
# ou armadura (da IA, de pacote, feita à mão) recebe os pesos do corpo que já se mexe certo, pela
# superfície mais próxima (fc_molde.transferir). Cada peça pequena e de um osso só (placa de armadura,
# ombreira, manopla, elmo) fica rígida nesse osso, como se pesa armadura em jogo; o pano grande (capa,
# sobreveste, saia) dobra com o corpo.
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
    try:
        for o in roupa:
            W, _ = fc_molde.transferir(molde, o, nomes, H)
            if rigido != "nao":
                co = fc_molde._co(o)
                ilhas = fc_molde._ilhas(o)
                for k in np.unique(ilhas):
                    idx = np.nonzero(ilhas == k)[0]
                    soma = W[idx].sum(0)
                    if soma.sum() <= 0:
                        continue
                    dono = int(np.argmax(soma))
                    parte = float(soma[dono] / soma.sum())
                    tamanho = float(np.ptp(co[idx], axis=0).max()) if len(idx) > 1 else 0.0
                    # placa: de um osso só e pequena; pano: grande ou dividida entre ossos
                    placa = rigido == "sim" or (parte > 0.55 and tamanho < 0.3 * H and len(idx) < 6000)
                    if placa:
                        W[idx] = 0.0
                        W[idx, dono] = 1.0
                        resumo["ilhas_rigidas"] += 1
                        resumo["placas"].append({"osso": nomes[dono], "vertices": int(len(idx)), "tamanho_cm": round(tamanho * 100, 1)})
                    else:
                        resumo["ilhas_de_pano"] += 1
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
            dono_geral = nomes[int(np.argmax(W.sum(0)))] if len(W) else None
            resumo["pecas"].append({"nome": o.name, "vertices": len(o.data.vertices), "osso_principal": dono_geral})
    finally:
        bpy.data.objects.remove(molde, do_unlink=True)
        arm.data.pose_position = pose
    return resumo
