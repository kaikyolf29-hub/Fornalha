# Fornalha: montagem livre por peças. A IA olha a referência (arma, casa, objeto) e descreve a forma
# com peças simples que juntas chegam em qualquer silhueta: caixa (com chanfro), cilindro, esfera,
# torno (perfil girado: pomo, barril, vaso, coluna), extrusão de um contorno com gume (lâmina, cabeça
# de machado, guarda, escudo, empena) e tubo por pontos (cabo curvo, chifre, corda, galho).
# Medidas em metros. Frente = olhando para +Y: x à direita, z para cima (o plano "frente" de um
# contorno é o que se vê na foto de frente). Arma: de pé (+Z), encaixe da mão na origem. Objeto: no chão.
import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

import fc_comum as c

TIPOS = ("caixa", "cilindro", "esfera", "torno", "extrusao", "tubo")
PLANOS = {
    # (eixo u, eixo v, normal) no mundo
    "frente": (Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0))),
    "lado": (Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))),
    "cima": (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))),
}
# palavra do tipo de material → nome que o pacote PBR (CC0) reconhece, quando ele está instalado
TIPO_PBR = {"metal": "metal", "madeira": "madeira", "couro": "couro", "pedra": "pedra", "tecido": "tecido",
            "telha": "telhado", "reboco": "reboco", "rocha": "rocha", "osso": "osso", "vidro": "vidro"}


def _v3(x, padrao=(0.0, 0.0, 0.0)):
    if x is None:
        return Vector(padrao)
    x = list(x) + [0.0] * (3 - len(x))
    return Vector([float(a) for a in x[:3]])


def _materiais(id_, spec):
    mats = {}
    for nome, m in (spec or {}).items():
        m = m if isinstance(m, dict) else {"cor": m}
        tipo = str(m.get("tipo", "")).lower()
        chave = f"{id_}_{nome}" + (f"_{TIPO_PBR[tipo]}" if tipo in TIPO_PBR else "")
        emissao = c.cor_hex(m["emissao"]) if m.get("emissao") else None
        metal = float(m.get("metal", 1.0 if tipo == "metal" else 0.0))
        rug = float(m.get("rugosidade", 0.35 if metal > 0.5 else 0.75))
        mats[nome] = c.material(chave, c.cor_hex(m.get("cor", "#8a8580")), rug, metal, emissao=emissao)
    return mats


# ------------------------------------------------------------------ contorno 2D (extrusão com gume)

def _area(pts):
    return 0.5 * sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))  # > 0: anti-horário


def _limpar_contorno(pts):
    out = []
    for p in pts:
        p = (float(p[0]), float(p[1]))
        if not out or math.dist(out[-1], p) > 1e-5:
            out.append(p)
    if len(out) > 2 and math.dist(out[0], out[-1]) < 1e-5:
        out.pop()
    if len(out) < 3:
        raise ValueError("contorno precisa de pelo menos 3 pontos")
    if _area(out) < 0:
        out.reverse()  # sempre anti-horário: a normal de dentro fica à esquerda
    return out


def _raio_para_dentro(o, d, pts):
    """Distância de o, andando na direção d, até a primeira aresta do contorno (o quanto cabe)."""
    melhor = math.inf
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-12:
            continue
        ax, ay = a[0] - o[0], a[1] - o[1]
        t = (ax * ey - ay * ex) / den
        u = (ax * d[1] - ay * d[0]) / den
        if t > 1e-6 and -1e-9 <= u <= 1 + 1e-9:
            melhor = min(melhor, t)
    return melhor


def _contorno_para_dentro(pts, gume):
    """Contorno recuado `gume` metros (até no máximo 45% do que cabe em cada ponto: na ponta da
    lâmina o recuo diminui e o fio continua fechando em ponta)."""
    n = len(pts)
    dentro = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1 = Vector((p1[0] - p0[0], p1[1] - p0[1])).normalized()
        e2 = Vector((p2[0] - p1[0], p2[1] - p1[1])).normalized()
        n1, n2 = Vector((-e1.y, e1.x)), Vector((-e2.y, e2.x))  # normais para dentro (contorno anti-horário)
        b = n1 + n2
        if b.length < 1e-6:
            b = n1
        b.normalize()
        seno = max(0.2, b.dot(n1))  # canto fechado: o recuo anda mais na bissetriz
        quer = gume / seno
        cabe = _raio_para_dentro(p1, (b.x, b.y), pts)
        k = min(quer, 0.45 * cabe) if math.isfinite(cabe) else quer
        dentro.append((p1[0] + b.x * k, p1[1] + b.y * k))
    return dentro


def _extrusao(bm, p):
    """Contorno no plano (frente, lado ou cima) com espessura. `gume` (m) afina a borda até `borda`
    (espessura da borda, 0 = fio): lâmina, machado, folha. Sem gume: placa reta (empena, escudo)."""
    pts = _limpar_contorno(p["contorno"])
    e = float(p.get("espessura", 0.02))
    gume = float(p.get("gume", 0.0))
    borda = float(p.get("borda", 0.0 if gume > 0 else e))
    borda = min(borda, e)
    u, v, nrm = PLANOS.get(p.get("plano", "frente"), PLANOS["frente"])
    base = _v3(p.get("posicao"))

    def ponto(q, h):
        return base + u * q[0] + v * q[1] + nrm * h

    camadas = []  # (contorno 2D, altura) do meio para fora em cada lado
    if gume > 0:
        miolo = _contorno_para_dentro(pts, gume)
        if borda > 0:
            camadas = [(pts, -borda / 2), (miolo, -e / 2), (pts, borda / 2), (miolo, e / 2)]
            baixo, cima = [(pts, -borda / 2), (miolo, -e / 2)], [(pts, borda / 2), (miolo, e / 2)]
        else:
            baixo, cima = [(pts, 0.0), (miolo, -e / 2)], [(pts, 0.0), (miolo, e / 2)]
    else:
        baixo, cima = [(pts, -e / 2)], [(pts, e / 2)]
    novos = []

    def anel(cont, h):
        vs = [bm.verts.new(ponto(q, h)) for q in cont]
        novos.extend(vs)
        return vs

    # lado de cima (normal +nrm) e de baixo; a borda de fora é partilhada quando o fio é 0
    a_cima = [anel(cc, h) for cc, h in cima]
    if gume > 0 and borda <= 0:
        a_baixo = [a_cima[0], anel(baixo[1][0], baixo[1][1])]
    else:
        a_baixo = [anel(cc, h) for cc, h in baixo]
    n = len(pts)
    faces = []
    for aneis, sinal in ((a_cima, 1), (a_baixo, -1)):
        for k in range(len(aneis) - 1):
            r0, r1 = aneis[k], aneis[k + 1]
            for i in range(n):
                j = (i + 1) % n
                q = [r0[i], r0[j], r1[j], r1[i]]
                faces.append(bm.faces.new(q if sinal > 0 else q[::-1]))
        tampa = aneis[-1]
        faces.append(bm.faces.new(tampa if sinal > 0 else tampa[::-1]))
    # parede da borda (entre o anel de fora de cima e o de baixo)
    if not (gume > 0 and borda <= 0):
        r0, r1 = a_baixo[0], a_cima[0]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new([r0[j], r0[i], r1[i], r1[j]]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return novos


# ------------------------------------------------------------------ torno e tubo

def _torno(bm, p):
    """Perfil [[raio, altura], ...] girado em volta do eixo (z por padrão) que passa em `posicao`."""
    perfil = [(max(0.0, float(r)), float(h)) for r, h in p["perfil"]]
    if len(perfil) < 2:
        raise ValueError("torno precisa de pelo menos 2 pontos no perfil")
    lados = int(p.get("lados", 24))
    base = _v3(p.get("posicao"))
    eixo = str(p.get("eixo", "z"))
    rot = {"z": Matrix.Identity(3), "x": Matrix.Rotation(math.radians(90), 3, "Y"), "y": Matrix.Rotation(math.radians(-90), 3, "X")}[eixo]
    aneis = []
    novos = []
    for r, h in perfil:
        if r < 1e-6:
            v = bm.verts.new(base + rot @ Vector((0, 0, h)))
            novos.append(v)
            aneis.append([v])
        else:
            vs = [bm.verts.new(base + rot @ Vector((r * math.cos(2 * math.pi * i / lados), r * math.sin(2 * math.pi * i / lados), h))) for i in range(lados)]
            novos.extend(vs)
            aneis.append(vs)
    faces = []
    for a, b in zip(aneis[:-1], aneis[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for i in range(lados):
            j = (i + 1) % lados
            if len(a) == 1:
                faces.append(bm.faces.new([a[0], b[i], b[j]]))
            elif len(b) == 1:
                faces.append(bm.faces.new([a[i], b[0], a[j]]))
            else:
                faces.append(bm.faces.new([a[i], b[i], b[j], a[j]]))
    for ponta in (aneis[0], aneis[-1]):
        if len(ponta) > 2:
            faces.append(bm.faces.new(ponta))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return novos


def _catmull(pontos, passos=4):
    if len(pontos) < 3:
        return pontos
    out = []
    ps = [pontos[0]] + pontos + [pontos[-1]]
    for i in range(1, len(ps) - 2):
        p0, p1, p2, p3 = ps[i - 1], ps[i], ps[i + 1], ps[i + 2]
        for k in range(passos):
            t = k / passos
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pontos[-1])
    return out


def _tubo(bm, p):
    """Tubo por pontos [[x, y, z], ...] com raio (um só ou um por ponto); `suave` arredonda a curva."""
    pts = [_v3(q) for q in p["pontos"]]
    if len(pts) < 2:
        raise ValueError("tubo precisa de pelo menos 2 pontos")
    raios = p.get("raio", 0.02)
    raios = [float(r) for r in raios] if isinstance(raios, list) else [float(raios)] * len(pts)
    raios = (raios + [raios[-1]] * len(pts))[:len(pts)]
    if p.get("suave", True) and len(pts) > 2:
        # o raio acompanha a curva suavizada
        rr = _catmull([Vector((r, 0, 0)) for r in raios])
        pts = _catmull(pts)
        raios = [r.x for r in rr]
    lados = int(p.get("lados", 10))
    aneis, novos = [], []
    tangentes = [(pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(len(pts))]
    ref = Vector((0, 0, 1)) if abs(tangentes[0].z) < 0.9 else Vector((1, 0, 0))
    a = tangentes[0].cross(ref).normalized()
    for i, q in enumerate(pts):
        t = tangentes[i]
        if i:
            # transporte paralelo: o quadro só gira o quanto a curva gira (o tubo não torce)
            a = tangentes[i - 1].rotation_difference(t) @ a
            a = (a - t * a.dot(t)).normalized()
        b = t.cross(a).normalized()
        vs = [bm.verts.new(q + (a * math.cos(2 * math.pi * k / lados) + b * math.sin(2 * math.pi * k / lados)) * raios[i]) for k in range(lados)]
        aneis.append(vs)
        novos.extend(vs)
    faces = []
    for r0, r1 in zip(aneis[:-1], aneis[1:]):
        for k in range(lados):
            j = (k + 1) % lados
            faces.append(bm.faces.new([r0[k], r0[j], r1[j], r1[k]]))
    faces.append(bm.faces.new(aneis[0]))
    faces.append(bm.faces.new(aneis[-1][::-1]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return novos


# ------------------------------------------------------------------ montagem

def _peca(k, p, mats, padrao):
    tipo = p.get("tipo")
    if tipo not in TIPOS:
        raise ValueError(f"peça de tipo desconhecido: {tipo!r} (use {', '.join(TIPOS)})")
    m = mats.get(p.get("material")) or padrao
    liso = bool(p.get("liso", tipo in ("esfera", "torno", "tubo")))
    antes = set(k.bm.verts)
    if tipo == "caixa":
        rot = Euler([math.radians(a) for a in _v3(p.get("rotacao"))]).to_quaternion() if p.get("rotacao") else None
        vs = k.caixa(_v3(p.get("centro")), _v3(p.get("tamanho"), (0.1, 0.1, 0.1)), m, rot=rot)
        if float(p.get("chanfro", 0)) > 0:
            arestas = list({e for v in vs for e in v.link_edges})
            bmesh.ops.bevel(k.bm, geom=arestas, offset=float(p["chanfro"]), segments=int(p.get("segmentos", 1)), affect="EDGES", clamp_overlap=True)
    elif tipo == "cilindro":
        vs = k.cilindro(_v3(p.get("de")), _v3(p.get("para"), (0, 0, 0.1)), float(p.get("raio", 0.02)), float(p.get("raio_fim", p.get("raio", 0.02))),
                        m, lados=int(p.get("lados", 16)), liso=liso)
    elif tipo == "esfera":
        lados = int(p.get("lados", 16))
        vs = k.esfera(_v3(p.get("centro")), float(p.get("raio", 0.05)), m, escala=tuple(_v3(p.get("escala"), (1, 1, 1))), u=lados, v=max(4, lados * 2 // 3), liso=liso)
    else:
        construir = {"torno": _torno, "extrusao": _extrusao, "tubo": _tubo}[tipo]
        construir(k.bm, p)
        vs = [v for v in k.bm.verts if v not in antes]
        k._registrar(vs, m, None, liso)
    vs = [v for v in k.bm.verts if v not in antes and v.is_valid]
    faces = list({f for v in vs for f in v.link_faces})
    mi = k._mat(m)
    for f in faces:
        f.material_index = mi
        f.smooth = liso
    if p.get("rotacao") and tipo != "caixa":
        centro = sum((v.co for v in vs), Vector()) / max(1, len(vs))
        pivo = _v3(p["pivo"]) if p.get("pivo") is not None else centro
        R = Euler([math.radians(a) for a in _v3(p["rotacao"])]).to_matrix().to_4x4()
        bmesh.ops.transform(k.bm, matrix=Matrix.Translation(pivo) @ R @ Matrix.Translation(-pivo), verts=vs)
    espelho = p.get("espelhar")
    if espelho in ("x", "y", "z"):
        eixo = "xyz".index(espelho)
        geom = vs + list({e for v in vs for e in v.link_edges}) + faces
        r = bmesh.ops.duplicate(k.bm, geom=geom)
        novos = [g for g in r["geom"] if isinstance(g, bmesh.types.BMVert)]
        escala = [1.0, 1.0, 1.0]
        escala[eixo] = -1.0
        bmesh.ops.scale(k.bm, vec=Vector(escala), verts=novos)
        novas_faces = [g for g in r["geom"] if isinstance(g, bmesh.types.BMFace)]
        bmesh.ops.reverse_faces(k.bm, faces=novas_faces)
        vs += novos
    return len(vs)


def montar(spec):
    """{"id", "pecas": [...], "materiais": {...}} → um objeto (malha só, materiais por peça)."""
    id_ = spec.get("id", "modelo")
    pecas = spec.get("pecas") or []
    if not pecas:
        raise ValueError("montagem sem peças")
    if len(pecas) > 400:
        raise ValueError("no máximo 400 peças por modelo")
    mats = _materiais(id_, spec.get("materiais"))
    padrao = next(iter(mats.values()), None) or c.material(f"{id_}_padrao", c.cor_hex("#8a8580"), 0.7)
    k = c.Construtor()
    avisos = []
    for i, p in enumerate(pecas):
        try:
            _peca(k, p, mats, padrao)
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"peça {i} ({p.get('tipo')}): {e}") from e
        if p.get("material") and p["material"] not in mats:
            avisos.append(f"peça {i}: material {p['material']!r} não está em materiais (usei o primeiro)")
    bmesh.ops.remove_doubles(k.bm, verts=list(k.bm.verts), dist=1e-6)
    obj = k.objeto(id_)
    # objeto apoiado no chão (z = 0) quando pedido; arma fica onde a IA pôs (encaixe na origem)
    if spec.get("no_chao"):
        zmin = min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
        for v in obj.data.vertices:
            v.co.z -= zmin
    return obj, avisos
