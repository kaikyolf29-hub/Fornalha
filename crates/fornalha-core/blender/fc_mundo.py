# Fornalha: mundo em blockout. As áreas da bíblia (vila, floresta, montanha,
# masmorra, arena...) viram um mapa em blocos simples, com colisão e pontos de
# nascimento, testável na engine antes de qualquer arte.
import math
import random

import bpy
from mathutils import Matrix, Vector

import fc_comum as c
import fc_armas

RAIO_AREA = 16.0


def _bloco(nome, centro, tamanho, mat, rot_z=0.0, colisao=True):
    k = c.Construtor()
    k.caixa(centro, tamanho, mat, rot=Matrix.Rotation(rot_z, 4, "Z").to_quaternion() if rot_z else None)
    return k.objeto(nome + ("-col" if colisao else ""))


def _marcador(nome, pos):
    e = bpy.data.objects.new(nome, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 1.0
    e.location = pos
    bpy.context.scene.collection.objects.link(e)
    return e


def _mover(obj, pos, rot_z=0.0):
    obj.location = Vector(obj.location) + Vector(pos)
    obj.rotation_euler.z = rot_z
    return obj


def area_vila(id_, centro, rnd, mats, objs, inimigos):
    for i in range(7):
        ang = i / 7 * math.tau + rnd.uniform(-0.15, 0.15)
        r = rnd.uniform(9, 12)
        casa = fc_armas.criar_objeto({"tipo": "casa", "id": f"{id_}_casa_{i}-col", "seed": rnd.randint(0, 9999), "cor_parede": mats["parede"], "cor_telhado": mats["telhado"]})
        objs.append(_mover(casa, centro + Vector((math.cos(ang) * r, math.sin(ang) * r, 0)), ang + math.pi / 2))
    poco = c.Construtor()
    poco.cilindro(centro, centro + Vector((0, 0, 0.9)), 1.0, 1.0, c.material("pedra_poco", c.cor_hex("#8a8578"), 0.9), lados=10)
    objs.append(poco.objeto(f"{id_}_poco-col"))
    for i in range(4):
        t = fc_armas.criar_objeto({"tipo": "tocha", "id": f"{id_}_tocha_{i}", "escala": 1.0})
        objs.append(_mover(t, centro + Vector((math.cos(i * math.pi / 2) * 4, math.sin(i * math.pi / 2) * 4, 0))))


def area_floresta(id_, centro, rnd, mats, objs, inimigos):
    for i in range(28):
        ang = rnd.uniform(0, math.tau)
        r = math.sqrt(rnd.uniform(0.05, 1)) * RAIO_AREA
        pos = centro + Vector((math.cos(ang) * r, math.sin(ang) * r, 0))
        a = fc_armas.criar_objeto({"tipo": "arvore", "id": f"{id_}_arvore_{i}-col", "seed": rnd.randint(0, 9999), "escala": rnd.uniform(0.8, 1.3), "cor_folha": mats["folha"]})
        objs.append(_mover(a, pos, rnd.uniform(0, math.tau)))
    for i in range(6):
        ang = rnd.uniform(0, math.tau)
        pedra = fc_armas.criar_objeto({"tipo": "pedra", "id": f"{id_}_pedra_{i}-col", "seed": rnd.randint(0, 9999), "escala": rnd.uniform(0.8, 2.0)})
        objs.append(_mover(pedra, centro + Vector((math.cos(ang) * 8, math.sin(ang) * 8, 0))))
    for i in range(3):
        inimigos.append(centro + Vector((rnd.uniform(-6, 6), rnd.uniform(-6, 6), 0.1)))


def area_montanha(id_, centro, rnd, mats, objs, inimigos):
    rocha = c.material("rocha_mont", c.cor_hex(mats["rocha"]), 0.95)
    for i, (r, a) in enumerate(((14, 3.0), (10, 6.5), (6, 10.0))):
        k = c.Construtor()
        k.cilindro(centro, centro + Vector((0, 0, a)), r, r * 0.92, rocha, lados=9)
        objs.append(k.objeto(f"{id_}_patamar_{i}-col"))
    # rampas entre os patamares
    for i, (z0, z1, r) in enumerate(((0, 3.0, 14), (3.0, 6.5, 10), (6.5, 10.0, 6))):
        comprimento = 9.0
        inclinacao = math.atan2(z1 - z0, comprimento)
        ang = i * 2.2
        base = centro + Vector((math.cos(ang) * (r + 3.5), math.sin(ang) * (r + 3.5), (z0 + z1) / 2))
        k = c.Construtor()
        rot = (Matrix.Rotation(ang + math.pi / 2, 4, "Z") @ Matrix.Rotation(inclinacao, 4, "X")).to_quaternion()
        k.caixa(base, (3.0, comprimento, 0.4), rocha, rot=rot)
        objs.append(k.objeto(f"{id_}_rampa_{i}-col"))
    inimigos.append(centro + Vector((0, 0, 10.2)))


def area_masmorra(id_, centro, rnd, mats, objs, inimigos):
    parede = c.material("parede_masmorra", c.cor_hex(mats["masmorra"]), 0.9)
    chao = c.material("chao_masmorra", c.cor_hex("#3a3633"), 0.95)
    objs.append(_bloco(f"{id_}_piso", centro + Vector((0, 0, 0.05)), (26, 26, 0.1), chao))
    L, A, E = 26.0, 4.0, 0.8
    # paredes externas com entrada no lado voltado para o centro do mapa
    for i, (dx, dy, sx, sy) in enumerate(((0, L / 2, L, E), (0, -L / 2, L, E), (L / 2, 0, E, L), (-L / 2, 0, E, L))):
        if i == 1:  # porta
            for lado in (-1, 1):
                objs.append(_bloco(f"{id_}_parede_{i}_{lado}", centro + Vector((lado * (L / 4 + 1.5), dy, A / 2)), (L / 2 - 3, E, A), parede))
        else:
            objs.append(_bloco(f"{id_}_parede_{i}", centro + Vector((dx, dy, A / 2)), (sx, sy, A), parede))
    # corredores internos
    for i, (x, y, sx, sy) in enumerate(((-4, 3, 0.8, 12), (4, -3, 0.8, 12), (0, 7, 10, 0.8), (6, 2, 6, 0.8))):
        objs.append(_bloco(f"{id_}_interna_{i}", centro + Vector((x, y, A / 2)), (sx, sy, A), parede))
    for i, (x, y) in enumerate(((8, 8), (-8, 8), (-8, -8))):
        inimigos.append(centro + Vector((x, y, 0.2)))
        b = fc_armas.criar_objeto({"tipo": "bau" if i == 0 else "barril", "id": f"{id_}_obj_{i}-col"})
        objs.append(_mover(b, centro + Vector((x + 1.5, y, 0.1))))


def area_arena(id_, centro, rnd, mats, objs, inimigos):
    pedra = c.material("pedra_arena", c.cor_hex(mats["arena"]), 0.9)
    areia = c.material("areia", c.cor_hex("#c9a86a"), 1.0)
    k = c.Construtor()
    k.cilindro(centro, centro + Vector((0, 0, 0.08)), 13, 13, areia, lados=24)
    objs.append(k.objeto(f"{id_}_areia-col"))
    n = 18
    for i in range(n):
        if i in (0, 1):  # entrada
            continue
        ang = i / n * math.tau - math.pi / 2
        pos = centro + Vector((math.cos(ang) * 14, math.sin(ang) * 14, 1.5))
        objs.append(_bloco(f"{id_}_muro_{i}", pos, (5.0, 1.2, 3.0), pedra, rot_z=ang + math.pi / 2))
    inimigos.append(centro + Vector((0, 4, 0.2)))
    inimigos.append(centro + Vector((3, -2, 0.2)))


GERADORES = {
    "vila": area_vila, "cidade": area_vila, "aldeia": area_vila,
    "floresta": area_floresta, "bosque": area_floresta, "pantano": area_floresta,
    "montanha": area_montanha, "colina": area_montanha, "vulcao": area_montanha,
    "masmorra": area_masmorra, "caverna": area_masmorra, "castelo": area_masmorra, "ruinas": area_masmorra,
    "arena": area_arena, "coliseu": area_arena,
}


def criar_mundo(p):
    rnd = random.Random(int(p.get("seed", 7)))
    paleta = p.get("paleta") or []
    pal = lambda i, padrao: paleta[i] if len(paleta) > i else padrao
    mats = {
        "grama": pal(0, "#4d7a3a"), "caminho": "#8b7355", "parede": "#c8b79a", "telhado": pal(1, "#8a3b2a"),
        "folha": pal(2, "#3f6b35"), "rocha": "#7d7a73", "masmorra": "#5a5550", "arena": "#9b8f7a",
    }
    areas = p.get("areas") or [{"id": "vila", "tipo": "vila"}, {"id": "floresta", "tipo": "floresta"}]
    objs, inimigos = [], []
    # a primeira área fica no centro; as outras num círculo em volta, ligadas por caminhos
    posicoes = [Vector((0, 0, 0))]
    n = max(len(areas) - 1, 1)
    for i in range(1, len(areas)):
        ang = (i - 1) / n * math.tau + math.pi / 2
        posicoes.append(Vector((math.cos(ang) * 46, math.sin(ang) * 46, 0)))
    extensao = max((v.length for v in posicoes), default=0) + RAIO_AREA * 2 + 10
    objs.append(_bloco("chao", (0, 0, -0.25), (extensao * 2, extensao * 2, 0.5), c.material("grama", c.cor_hex(mats["grama"]), 0.95)))
    caminho = c.material("caminho", c.cor_hex(mats["caminho"]), 1.0)
    for i, pos in enumerate(posicoes[1:], 1):
        meio = pos / 2
        objs.append(_bloco(f"caminho_{i}", (meio.x, meio.y, 0.02), (3.5, pos.length, 0.06), caminho, rot_z=math.atan2(pos.y, pos.x) - math.pi / 2, colisao=False))
    info_areas = []
    for area, pos in zip(areas, posicoes):
        tipo = (area.get("tipo") or "vila").lower()
        gerador = GERADORES.get(tipo, area_vila)
        antes = len(inimigos)
        antes_objs = len(objs)
        gerador(area.get("id", tipo), pos, rnd, mats, objs, inimigos)
        if pos.length > 1e-3:
            # cada área nasce com a entrada para -Y; gira para a entrada olhar a área central
            ang = math.atan2(-pos.y, -pos.x) + math.pi / 2
            giro = Matrix.Translation(pos) @ Matrix.Rotation(ang, 4, "Z") @ Matrix.Translation(-pos)
            bpy.context.view_layer.update()  # matrix_world só fica certa depois de atualizar
            for o in objs[antes_objs:]:
                o.matrix_world = giro @ o.matrix_world
            for i in range(antes, len(inimigos)):
                inimigos[i] = giro @ inimigos[i]
        info_areas.append({"id": area.get("id", tipo), "tipo": tipo, "centro": [pos.x, pos.y, pos.z], "inimigos": len(inimigos) - antes})
    marcadores = [_marcador("spawn_jogador", (0, -5, 0.2))]
    for i, pos in enumerate(inimigos):
        marcadores.append(_marcador(f"spawn_inimigo_{i:02d}", pos))
    return objs, marcadores, info_areas
