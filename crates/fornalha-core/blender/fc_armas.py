# Fornalha: armas e objetos low-poly. A arma nasce de pé (+Z) com o encaixe da mão
# na origem; o objeto nasce apoiado no chão (z = 0).
import math
import random

import bpy
from mathutils import Matrix, Vector

import fc_comum as c

ARMAS = ("espada", "machado", "lanca", "martelo", "adaga", "cajado", "escudo")
OBJETOS = ("barril", "caixa", "bau", "arvore", "pedra", "casa", "tocha", "cerca", "pocao")


def _mats(p):
    cor = lambda chave, padrao: c.cor_hex(p.get(chave) or padrao)
    return (
        c.material("metal_arma", cor("cor_metal", "#b7c0c9"), 0.3, 0.95),
        c.material("couro_arma", cor("cor_couro", "#4a3122"), 0.75),
        c.material("madeira", cor("cor_madeira", "#6b4a2b"), 0.8),
        c.material("detalhe", cor("cor_detalhe", "#c9a227"), 0.35, 0.8),
    )


def criar_arma(p):
    tipo = p.get("tipo", "espada")
    e = float(p.get("escala") or 1.0)
    metal, couro, madeira, detalhe = _mats(p)
    k = c.Construtor()
    s = lambda v: v * e
    if tipo == "espada":
        k.cilindro((0, 0, s(-0.08)), (0, 0, s(0.08)), s(0.016), s(0.016), couro)
        k.esfera((0, 0, s(-0.1)), s(0.025), detalhe, u=8, v=6, liso=False)
        k.caixa((0, 0, s(0.095)), (s(0.18), s(0.035), s(0.025)), detalhe)
        k.caixa((0, 0, s(0.46)), (s(0.055), s(0.012), s(0.70)), metal)
        k.cone((0, 0, s(0.81)), (0, 0, s(0.90)), s(0.039), metal, lados=4)
    elif tipo == "adaga":
        k.cilindro((0, 0, s(-0.05)), (0, 0, s(0.05)), s(0.014), s(0.014), couro)
        k.caixa((0, 0, s(0.06)), (s(0.09), s(0.025), s(0.018)), detalhe)
        k.caixa((0, 0, s(0.2)), (s(0.04), s(0.01), s(0.26)), metal)
        k.cone((0, 0, s(0.33)), (0, 0, s(0.38)), s(0.028), metal, lados=4)
    elif tipo == "machado":
        k.cilindro((0, 0, s(-0.2)), (0, 0, s(0.62)), s(0.02), s(0.018), madeira)
        k.caixa((0, s(0.07), s(0.55)), (s(0.025), s(0.14), s(0.08)), metal)
        k.caixa((0, s(0.15), s(0.55)), (s(0.02), s(0.05), s(0.22)), metal)
    elif tipo == "martelo":
        k.cilindro((0, 0, s(-0.2)), (0, 0, s(0.55)), s(0.02), s(0.02), madeira)
        k.caixa((0, 0, s(0.58)), (s(0.12), s(0.24), s(0.12)), metal)
    elif tipo == "lanca":
        k.cilindro((0, 0, s(-0.7)), (0, 0, s(1.2)), s(0.017), s(0.015), madeira)
        k.cone((0, 0, s(1.18)), (0, 0, s(1.42)), s(0.04), metal, lados=4)
    elif tipo == "cajado":
        k.cilindro((0, 0, s(-0.8)), (0, 0, s(0.9)), s(0.02), s(0.017), madeira)
        cristal = c.material("cristal", c.cor_hex(p.get("cor_magia") or "#56c7ff"), 0.1, 0.0, emissao=c.cor_hex(p.get("cor_magia") or "#56c7ff"))
        k.esfera((0, 0, s(0.98)), s(0.06), cristal, u=6, v=4, liso=False)
    elif tipo == "escudo":
        k.cilindro((0, -0.01, 0), (0, 0.04, 0), s(0.28), s(0.28), madeira, lados=10)
        k.cilindro((0, -0.02, 0), (0, 0.0, 0), s(0.08), s(0.08), metal, lados=8)
        k.cilindro((0, 0.04, 0), (0, 0.05, 0), s(0.29), s(0.29), metal, lados=10)
    else:
        raise ValueError(f"arma desconhecida: {tipo}")
    obj = k.objeto(p.get("id", tipo))
    return obj


def criar_objeto(p):
    tipo = p.get("tipo", "caixa")
    e = float(p.get("escala") or 1.0)
    metal, couro, madeira, detalhe = _mats(p)
    rnd = random.Random(int(p.get("seed", 1)))
    k = c.Construtor()
    s = lambda v: v * e
    if tipo == "barril":
        k.cilindro((0, 0, 0), (0, 0, s(0.45)), s(0.26), s(0.3), madeira, lados=10)
        k.cilindro((0, 0, s(0.45)), (0, 0, s(0.9)), s(0.3), s(0.26), madeira, lados=10)
        for z in (0.12, 0.45, 0.78):
            k.cilindro((0, 0, s(z - 0.02)), (0, 0, s(z + 0.02)), s(0.305 - abs(z - 0.45) * 0.1), s(0.305 - abs(z - 0.45) * 0.1), metal, lados=10)
    elif tipo == "caixa":
        k.caixa((0, 0, s(0.3)), (s(0.6), s(0.6), s(0.6)), madeira)
        for x in (-1, 1):
            for y in (-1, 1):
                k.caixa((x * s(0.28), y * s(0.28), s(0.3)), (s(0.06), s(0.06), s(0.62)), couro)
    elif tipo == "bau":
        k.caixa((0, 0, s(0.22)), (s(0.8), s(0.5), s(0.44)), madeira)
        k.cilindro((s(-0.4), 0, s(0.44)), (s(0.4), 0, s(0.44)), s(0.25), s(0.25), madeira, lados=8)
        for x in (-0.3, 0.3):
            k.caixa((s(x), 0, s(0.35)), (s(0.05), s(0.52), s(0.72)), metal)
        k.caixa((0, s(-0.26), s(0.42)), (s(0.08), s(0.03), s(0.1)), detalhe)
    elif tipo == "arvore":
        folha = c.material("folha", c.cor_hex(p.get("cor_folha") or "#3f6b35"), 0.85)
        altura = s(rnd.uniform(3.2, 5.0))
        k.cilindro((0, 0, 0), (0, 0, altura * 0.45), s(0.22), s(0.16), madeira, lados=7)
        for i, (z, r) in enumerate(((0.35, 1.3), (0.6, 1.0), (0.82, 0.65))):
            k.cone((0, 0, altura * z), (0, 0, altura * (z + 0.32)), s(r), folha, lados=7)
    elif tipo == "pedra":
        rocha = c.material("rocha", c.cor_hex(p.get("cor_pedra") or "#7d7a73"), 0.95)
        vs = k.esfera((0, 0, s(0.35)), s(0.5), rocha, escala=(1.2, 1.0, 0.75), u=8, v=6, liso=False)
        for v in vs:
            v.co *= rnd.uniform(0.85, 1.15)
            v.co.z = max(v.co.z, 0.0)
    elif tipo == "casa":
        parede = c.material("parede", c.cor_hex(p.get("cor_parede") or "#c8b79a"), 0.9)
        telhado = c.material("telhado", c.cor_hex(p.get("cor_telhado") or "#8a3b2a"), 0.8)
        L, P, A = s(5.0), s(4.0), s(3.0)
        k.caixa((0, 0, A / 2), (L, P, A), parede)
        # telhado em duas águas
        for lado in (-1, 1):
            rot = Matrix.Rotation(math.radians(32 * lado), 4, "X").to_quaternion()
            k.caixa((0, lado * P * 0.25, A + s(0.75)), (L + s(0.5), P * 0.62, s(0.18)), telhado, rot=rot)
        k.caixa((0, -P / 2 - 0.01, s(1.0)), (s(1.0), s(0.08), s(2.0)), madeira)
    elif tipo == "tocha":
        fogo = c.material("fogo", (1.0, 0.45, 0.08), 0.5, 0.0, emissao=(1.0, 0.4, 0.05))
        k.cilindro((0, 0, 0), (0, 0, s(1.6)), s(0.04), s(0.035), madeira, lados=6)
        k.cone((0, 0, s(1.6)), (0, 0, s(1.9)), s(0.08), fogo, lados=5)
    elif tipo == "cerca":
        for x in (-1.0, 0.0, 1.0):
            k.caixa((s(x), 0, s(0.5)), (s(0.1), s(0.1), s(1.0)), madeira)
        for z in (0.35, 0.75):
            k.caixa((0, 0, s(z)), (s(2.1), s(0.06), s(0.1)), madeira)
    elif tipo == "pocao":
        vidro = c.material("vidro", c.cor_hex(p.get("cor_magia") or "#d1293d"), 0.1, 0.0, emissao=c.cor_hex(p.get("cor_magia") or "#d1293d"))
        k.esfera((0, 0, s(0.1)), s(0.09), vidro, u=8, v=6, liso=True)
        k.cilindro((0, 0, s(0.17)), (0, 0, s(0.25)), s(0.03), s(0.03), vidro, lados=6)
        k.cilindro((0, 0, s(0.25)), (0, 0, s(0.29)), s(0.035), s(0.035), madeira, lados=6)
    else:
        raise ValueError(f"objeto desconhecido: {tipo}")
    return k.objeto(p.get("id", tipo))


def colisao_simples(obj, nome=None):
    """Caixa de colisão (a Godot e a Erethea criam o corpo físico pelo sufixo -colonly)."""
    mn, mx = c.caixa_envolvente([obj])
    k = c.Construtor()
    k.caixa((mn + mx) / 2, (mx - mn), c.material("colisao", (1, 0, 1), 1.0))
    col = k.objeto((nome or obj.name) + "-colonly")
    col.display_type = "WIRE"
    col.hide_render = True
    return col
