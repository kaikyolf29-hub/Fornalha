# Fornalha: masmorra por peças encaixadas (bancada de mapa). Uma grade de 4 m: salas e corredores
# sorteados e ligados, e as peças (piso, parede, parede com arco, pilar, portal de entrada) postas onde
# a grade pede. Sem teto (câmera em terceira pessoa); paredes altas, tochas, baú na última sala.
import math
import random

from mathutils import Matrix, Vector

import fc_comum as c
import fc_armas

CEL = 4.0  # lado da célula da grade, em metros
ALTURA = 4.2
ESPESSURA = 0.7


def _layout(rnd, n):
    """Salas (2x2 a 3x3) numa grade n×n, ligadas por corredores de uma célula. Devolve as células e as salas."""
    ocupadas = {}
    salas = []
    alvo = max(2, n // 3 + 1)
    for tentativa in range(200):
        if len(salas) >= alvo:
            break
        grande = 3 if tentativa < 100 else 2  # se não couber, salas menores
        w, h = rnd.randint(2, grande), rnd.randint(2, grande)
        x, y = rnd.randint(0, n - w), rnd.randint(1, n - h)
        celulas = {(x + i, y + j) for i in range(w) for j in range(h)}
        vizinhas = {(a + da, b + db) for a, b in celulas for da in (-1, 0, 1) for db in (-1, 0, 1)}
        if vizinhas & set(ocupadas):
            continue
        k = len(salas)
        for cel in celulas:
            ocupadas[cel] = ("sala", k)
        salas.append({"celulas": sorted(celulas), "centro": (x + (w - 1) / 2, y + (h - 1) / 2)})
    # corredores em L: da primeira sala até cada uma das outras (em ordem)
    for a, b in zip(salas[:-1], salas[1:]):
        x0, y0 = (int(round(v)) for v in a["centro"])
        x1, y1 = (int(round(v)) for v in b["centro"])
        passo_x = 1 if x1 >= x0 else -1
        for x in range(x0, x1 + passo_x, passo_x):
            ocupadas.setdefault((x, y0), ("corredor", -1))
        passo_y = 1 if y1 >= y0 else -1
        for y in range(y0, y1 + passo_y, passo_y):
            ocupadas.setdefault((x1, y), ("corredor", -1))
    # entrada: da primeira sala reto para baixo (y = 0), onde fica o portal
    x0, y0 = (int(round(v)) for v in salas[0]["centro"])
    for y in range(0, y0):
        ocupadas.setdefault((x0, y), ("corredor", -1))
    return ocupadas, salas, (x0, 0)


def gerar(id_, centro, rnd, mats, objs, inimigos, raio):
    """Masmorra centrada em `centro` (Blender), com a entrada virada para -Y (quem chega)."""
    n = max(4, min(8, int(raio * 0.318)))  # o quadrado cabe no patamar plano (meia diagonal < 0,9 do raio)
    for _ in range(12):  # uma sala só não é masmorra: sorteia de novo
        ocupadas, salas, entrada = _layout(rnd, n)
        if len(salas) >= 2:
            break
    pedra = c.material("pedra_masmorra", c.cor_hex(mats.get("masmorra", "#5a5550")), 0.9)
    piso = c.material("piso_masmorra", c.cor_hex("#4a4540"), 0.95)
    escura = c.material("junta_masmorra", c.cor_hex("#2c2926"), 1.0)
    origem = Vector(centro) - Vector(((n - 1) * CEL / 2, (n - 1) * CEL / 2 + CEL * 0.5, 0))

    def pos(cx, cy, z=0.0):
        return origem + Vector((cx * CEL, cy * CEL, z))

    pilares = set()
    k_piso = c.Construtor()
    k_parede = c.Construtor()
    for (cx, cy) in ocupadas:
        p = pos(cx, cy)
        k_piso.caixa(p + Vector((0, 0, 0.1)), (CEL - 0.06, CEL - 0.06, 0.2), piso)  # lajes com junta
        k_piso.caixa(p + Vector((0, 0, 0.02)), (CEL, CEL, 0.04), escura)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (cx + dx, cy + dy) in ocupadas:
                continue
            centro_p = p + Vector((dx * CEL / 2, dy * CEL / 2, ALTURA / 2))
            # parede com 4 m certos: vizinhas só se tocam (sobrepostas, as faces brigam e ficam pretas);
            # os cantos ficam com os pilares
            tam = (ESPESSURA, CEL, ALTURA) if dx else (CEL, ESPESSURA, ALTURA)
            if (cx, cy) == entrada and dy == -1:
                _portal(k_parede, centro_p, pedra, escura)
                continue
            k_parede.caixa(centro_p, tam, pedra)
            # fiadas de pedra: friso escuro a cada 1,4 m e a coroa irregular de ruína
            for z in (1.4, 2.8):
                fr = (tam[0] + 0.04, tam[1] - 0.02, 0.06) if dx else (tam[0] - 0.02, tam[1] + 0.04, 0.06)
                k_parede.caixa(centro_p + Vector((0, 0, z - ALTURA / 2)), fr, escura)
            if rnd.random() < 0.5:
                topo = (tam[0], tam[1] * rnd.uniform(0.3, 0.6), rnd.uniform(0.4, 0.9)) if dx else (tam[0] * rnd.uniform(0.3, 0.6), tam[1], rnd.uniform(0.4, 0.9))
                k_parede.caixa(centro_p + Vector((0, 0, ALTURA / 2 + topo[2] / 2)), topo, pedra)
        # pilares nos cantos onde duas paredes se encontram
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            canto = (2 * cx + dx, 2 * cy + dy)  # um pilar por canto (cada canto é de até 4 células)
            if canto in pilares:
                continue
            if (cx + dx, cy) not in ocupadas or (cx, cy + dy) not in ocupadas:
                pilares.add(canto)
                k_parede.caixa(p + Vector((dx * CEL / 2, dy * CEL / 2, ALTURA / 2 + 0.2)), (1.0, 1.0, ALTURA + 0.4), pedra)
    objs.append(k_piso.objeto(f"{id_}_piso-col"))
    objs.append(k_parede.objeto(f"{id_}_paredes-col"))
    # tochas nas salas, inimigos e baú na última sala
    for i, s in enumerate(salas):
        cx, cy = s["centro"]
        p = pos(cx, cy, 0.2)
        t = fc_armas.criar_objeto({"tipo": "tocha", "id": f"{id_}_tocha_{i}", "escala": 1.0})
        t.location = p + Vector((CEL * 0.6, 0, 0))
        objs.append(t)
        if i > 0:
            inimigos.append(p + Vector((rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5), 0)))
    ultima = salas[-1]
    b = fc_armas.criar_objeto({"tipo": "bau", "id": f"{id_}_bau-col"})
    b.location = pos(*ultima["centro"], 0.2)
    objs.append(b)
    return len(ocupadas)


def _portal(k, centro, pedra, escura):
    """Portal de entrada: duas colunas, verga com arco de aduelas e degraus para fora."""
    vao, alto = 2.2, 3.1
    lado = CEL / 2 - 0.5 - vao / 2 + 0.1  # da porta até o pilar do canto (sem face no mesmo plano dele)
    fundo = ESPESSURA + 0.45
    for s in (-1, 1):
        k.caixa(centro + Vector((s * (vao / 2 + lado / 2), 0, 0)), (lado, fundo, ALTURA), pedra)
    base = centro.z - ALTURA / 2
    k.caixa(Vector((centro.x, centro.y, base + alto + (ALTURA - alto) / 2 + 0.3)), (vao + 0.2, fundo - 0.1, ALTURA - alto + 0.6), pedra)
    for i in range(7):  # aduelas do arco
        a = math.pi * i / 6
        p = Vector((centro.x + math.cos(a) * vao / 2, centro.y, base + alto - 0.6 + math.sin(a) * 0.6))
        rot = Matrix.Rotation(-a + math.pi / 2, 4, "Y").to_quaternion()
        k.caixa(p, (0.35, ESPESSURA + 0.5, 0.5), escura, rot=rot)
    for d in range(3):  # degraus
        k.caixa(Vector((centro.x, centro.y - ESPESSURA / 2 - 0.4 - d * 0.5, base + 0.15 - d * 0.12)), (vao + 1.0, 0.5, 0.3), pedra)
