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


def _casa_medieval(k, p, rnd, s, madeira):
    """Casa medieval: térreo de pedra, andar de cima em reboco com enxaimel (vigas), empena,
    telhado de telha com beiral, chaminé, porta e janelas com venezianas."""
    pedra = c.material("pedra_casa", c.cor_hex(p.get("cor_parede") or "#b7aa95"), 0.9)
    reboco = c.material("reboco", c.cor_hex("#ded6c4"), 0.95)
    viga = c.material("viga", c.cor_hex("#3b2a1c"), 0.85)
    telhado = c.material("telhado", c.cor_hex(p.get("cor_telhado") or "#8a3b2a"), 0.8)
    escuro = c.material("janela_escura", c.cor_hex("#151311"), 0.6)
    L = s(rnd.uniform(5.5, 7.0))
    P = s(rnd.uniform(4.5, 5.5))
    A1, A2 = s(2.7), s(2.4)
    balanco = s(0.25)
    k.caixa((0, 0, A1 / 2), (L, P, A1), pedra)
    # andar de cima avança um pouco na frente e atrás (como nas casas da época)
    P2 = P + 2 * balanco
    k.caixa((0, 0, A1 + A2 / 2), (L, P2, A2), reboco)
    e = s(0.17)
    for lado in (-1, 1):
        y = lado * (P2 / 2 + 0.01)
        k.caixa((0, y, A1 + e / 2), (L + 0.02, e, e), viga)
        k.caixa((0, y, A1 + A2 - e / 2), (L + 0.02, e, e), viga)
        n = max(3, int(L / s(1.2)))
        for i in range(n + 1):
            x = -L / 2 + L * i / n
            k.caixa((x, y, A1 + A2 / 2), (e, e, A2), viga)
            if 0 < i < n and i % 2 == 1:
                for d in (-1, 1):
                    rot = Matrix.Rotation(math.radians(38 * d), 4, "Y").to_quaternion()
                    k.caixa((x + d * L / n / 2, y, A1 + A2 / 2), (e * 0.8, e * 0.8, A2 * 1.08), viga, rot=rot)
    for lado in (-1, 1):
        x = lado * (L / 2 + 0.01)
        k.caixa((x, 0, A1 + A2 / 2), (e, P2, e), viga)
        for yy in (-P2 / 2, 0, P2 / 2):
            k.caixa((x, yy, A1 + A2 / 2), (e, e, A2), viga)
    # empenas (triângulos de reboco) e telhado em duas águas com beiral
    inclinacao = math.radians(42)
    h_empena = (P2 / 2) * math.tan(inclinacao)
    topo = A1 + A2
    for lado in (-1, 1):
        x = lado * (L / 2 - s(0.05))
        for i in range(6):
            t0 = i / 6
            larg = P2 * (1 - t0)
            k.caixa((x, 0, topo + h_empena * (t0 + 1 / 12)), (s(0.12), larg, h_empena / 6), reboco)
    comp = (P2 / 2 + s(0.45)) / math.cos(inclinacao)
    for lado in (-1, 1):
        rot = Matrix.Rotation(-lado * inclinacao, 4, "X").to_quaternion()
        cy = lado * (P2 / 2 + s(0.45)) / 2
        cz = topo + h_empena - (h_empena + s(0.45) * math.tan(inclinacao)) / 2 + s(0.1)
        k.caixa((0, cy, cz), (L + s(0.7), comp, s(0.16)), telhado, rot=rot)
    k.caixa((0, 0, topo + h_empena + s(0.06)), (L + s(0.75), s(0.22), s(0.14)), viga)  # cumeeira
    # chaminé de pedra
    k.caixa((L * 0.28, P2 * 0.18, topo + h_empena * 0.75), (s(0.7), s(0.7), h_empena * 1.3 + s(0.6)), pedra)
    # porta e janelas
    k.caixa((rnd.uniform(-L * 0.2, L * 0.2), -P / 2 - s(0.04), s(1.05)), (s(1.1), s(0.1), s(2.1)), madeira)
    for x in (-L * 0.32, L * 0.32):
        k.caixa((x, -P / 2 - s(0.03), s(1.5)), (s(0.8), s(0.08), s(0.75)), escuro)
        k.caixa((x, -P / 2 - s(0.06), s(1.5)), (s(0.95), s(0.05), s(0.1)), viga)
    for x in (-L * 0.25, L * 0.25):
        y = -P2 / 2 - s(0.03)
        k.caixa((x, y, A1 + A2 * 0.5), (s(0.75), s(0.08), s(0.85)), escuro)
        for d in (-1, 1):
            k.caixa((x + d * s(0.62), y - s(0.03), A1 + A2 * 0.5), (s(0.42), s(0.05), s(0.9)), madeira)


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
        casca = c.material("casca_arvore", c.cor_hex("#5a4632"), 0.9)
        altura = s(rnd.uniform(4.5, 7.5))
        if rnd.random() < 0.45:
            # pinheiro: tronco reto e camadas de galhos
            k.cilindro((0, 0, 0), (0, 0, altura), s(0.26), s(0.06), casca, lados=10)
            camadas = 6
            for i in range(camadas):
                t = i / camadas
                z = altura * (0.28 + 0.66 * t)
                k.cone((0, 0, z), (0, 0, z + altura * 0.26), s(1.7 * (1 - t) + 0.35), folha, lados=9)
        else:
            # folhosa: tronco que se abre em galhos e copa em tufos
            topo = altura * 0.55
            k.cilindro((0, 0, 0), (0, 0, topo), s(0.32), s(0.2), casca, lados=10)
            k.cilindro((0, 0, -0.05), (0, 0, s(0.35)), s(0.48), s(0.32), casca, lados=10)  # raízes
            for g in range(4):
                ang = g / 4 * math.tau + rnd.uniform(-0.3, 0.3)
                ponta = Vector((math.cos(ang) * s(1.4), math.sin(ang) * s(1.4), topo + s(1.3)))
                k.cilindro((0, 0, topo - s(0.3)), ponta, s(0.14), s(0.06), casca, lados=7)
            for t in range(9):
                ang = rnd.uniform(0, math.tau)
                r = rnd.uniform(0.0, 1.6)
                centro = Vector((math.cos(ang) * s(r), math.sin(ang) * s(r), topo + s(rnd.uniform(1.0, 2.6))))
                vs = k.esfera(centro, s(rnd.uniform(1.0, 1.6)), folha, escala=(1.0, 1.0, 0.8), u=10, v=7, liso=True)
                for v in vs:
                    v.co += (v.co - centro).normalized() * s(rnd.uniform(-0.18, 0.18))
    elif tipo == "pedra":
        rocha = c.material("rocha", c.cor_hex(p.get("cor_pedra") or "#7d7a73"), 0.95)
        vs = k.esfera((0, 0, s(0.35)), s(0.6), rocha, escala=(1.25, 1.0, 0.72), u=14, v=10, liso=True)
        for v in vs:
            n = math.sin(v.co.x * 7.1 + rnd.random()) * math.cos(v.co.y * 5.3) * 0.12
            v.co *= rnd.uniform(0.9, 1.08) + n
            v.co.z = max(v.co.z, -0.05)
    elif tipo == "casa":
        _casa_medieval(k, p, rnd, s, madeira)
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
