# Fornalha: humanos realistas a partir dos dados CC0 do MakeHuman (malha base hm08,
# alvos de forma, esqueleto de jogo, pesos, pele, olhos, sobrancelhas, cílios, dentes,
# cabelo e roupas). Só os DADOS são usados, lidos por este código; nenhum código do
# MakeHuman ou do MPFB roda aqui.
#   dados  = pasta "data" do MPFB (3dobjs/base.obj, targets/, rigs/standard/)
#   assets = pacote "makehuman_system_assets" (skins/, eyes/, hair/, clothes/...)
import gzip
import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import fc_comum as c

ESCALA = 0.1  # o MakeHuman trabalha em decímetros

# ------------------------------------------------------------------ arquivos


def ler_obj(caminho):
    """OBJ do MakeHuman: vértices, UVs, faces (índices 0-based) e grupos."""
    v, vt, faces, grupos = [], [], [], {}
    grupo = None
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            if linha.startswith("v "):
                v.append([float(x) for x in linha.split()[1:4]])
            elif linha.startswith("vt "):
                vt.append([float(x) for x in linha.split()[1:3]])
            elif linha.startswith("g "):
                grupo = linha.split(None, 1)[1].strip()
                grupos.setdefault(grupo, [])
            elif linha.startswith("f "):
                vi, ti = [], []
                for p in linha.split()[1:]:
                    partes = p.split("/")
                    vi.append(int(partes[0]) - 1)
                    ti.append(int(partes[1]) - 1 if len(partes) > 1 and partes[1] else -1)
                faces.append((vi, ti))
                if grupo is not None:
                    grupos[grupo].append(len(faces) - 1)
    return np.array(v, dtype=np.float64), np.array(vt, dtype=np.float64) if vt else None, faces, grupos


def ler_alvo(caminho):
    with gzip.open(caminho, "rt") if caminho.endswith(".gz") else open(caminho) as f:
        dados = np.loadtxt(f, ndmin=2)
    if not len(dados):
        return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
    return dados[:, 0].astype(np.int64), dados[:, 1:4]


def ler_mhmat(caminho):
    m = {"_pasta": os.path.dirname(caminho)}
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            k, _, resto = linha.partition(" ")
            m[k] = resto.strip()
    return m


def ler_mhclo(caminho):
    """Proxy do MakeHuman: cada vértice preso a 3 vértices da malha base, com peso e deslocamento."""
    info = {"_pasta": os.path.dirname(caminho), "refs": [], "pesos": [], "desloc": [], "apagar": [], "escala": {}}
    secao = None
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            s = linha.strip()
            if not s or s.startswith("#"):
                continue
            partes = s.split()
            chave = partes[0]
            if chave in ("verts", "delete_verts", "weights", "offsets"):
                secao = chave
                continue
            if chave in ("x_scale", "y_scale", "z_scale"):
                info["escala"][chave[0]] = (int(partes[1]), int(partes[2]), float(partes[3]))
                continue
            if secao == "verts" and partes[0].lstrip("-").isdigit():
                if len(partes) == 1:
                    info["refs"].append((int(partes[0]),) * 3)
                    info["pesos"].append((1.0, 0.0, 0.0))
                    info["desloc"].append((0.0, 0.0, 0.0))
                else:
                    info["refs"].append(tuple(int(x) for x in partes[0:3]))
                    info["pesos"].append(tuple(float(x) for x in partes[3:6]))
                    info["desloc"].append(tuple(float(x) for x in partes[6:9]) if len(partes) >= 9 else (0.0, 0.0, 0.0))
                continue
            if secao == "delete_verts":
                for p in partes:
                    if "-" in p[1:]:
                        a, b = p.split("-")
                        info["apagar"].extend(range(int(a), int(b) + 1))
                    elif p.lstrip("-").isdigit():
                        info["apagar"].append(int(p))
                continue
            if chave in ("obj_file", "material", "name", "z_depth"):
                info[chave] = " ".join(partes[1:])
    return info


# ------------------------------------------------------------------ forma (macro)


def _partes(valor, partes_def):
    """Valor 0–1 → {rótulo: peso} pelas faixas do macro.json."""
    pesos = {}
    for p in partes_def:
        if p["lowest"] <= valor <= p["highest"]:
            ini = max(0.0, p["lowest"])
            fim = min(1.0, p["highest"])
            t = 0.0 if fim <= ini else (valor - ini) / (fim - ini)
            t = min(1.0, max(0.0, t))
            if p["low"]:
                pesos[p["low"]] = pesos.get(p["low"], 0.0) + (1 - t)
            if p["high"]:
                pesos[p["high"]] = pesos.get(p["high"], 0.0) + t
            break
    return pesos


def alvos_macro(dados, macro):
    """Lista de (arquivo, peso) dos alvos de corpo inteiro (gênero, idade, músculo, peso, altura, proporções, etnia)."""
    pasta = os.path.join(dados, "targets", "macrodetails")
    with open(os.path.join(pasta, "macro.json")) as f:
        defs = json.load(f)["macrotargets"]
    g = _partes(macro.get("genero", 0.5), defs["gender"]["parts"])
    a = _partes(macro.get("idade", 0.5), defs["age"]["parts"])
    m = _partes(macro.get("musculo", 0.5), defs["muscle"]["parts"])
    w = _partes(macro.get("peso", 0.5), defs["weight"]["parts"])
    h = _partes(macro.get("altura", 0.5), defs["height"]["parts"])
    pr = _partes(macro.get("proporcoes", 0.5), defs["proportions"]["parts"])
    racas = macro.get("racas") or {"caucasian": 1.0}
    total = sum(racas.values()) or 1.0
    lista = []
    for gn, gp in g.items():
        for an, ap in a.items():
            for rn, rp in racas.items():
                lista.append((os.path.join(pasta, f"{rn}-{gn}-{an}.target.gz"), rp / total * gp * ap))
            for mn, mp in m.items():
                for wn, wp in w.items():
                    base = gp * ap * mp * wp
                    lista.append((os.path.join(pasta, f"universal-{gn}-{an}-{mn}-{wn}.target.gz"), base))
                    for hn, hp in h.items():
                        lista.append((os.path.join(pasta, "height", f"{gn}-{an}-{mn}-{wn}-{hn}.target.gz"), base * hp))
                    for pn, pp in pr.items():
                        lista.append((os.path.join(pasta, "proportions", f"{gn}-{an}-{mn}-{wn}-{pn}.target.gz"), base * pp))
    return [(arq, p) for arq, p in lista if p > 1e-4 and os.path.isfile(arq)]


def aplicar_alvos(coords, lista):
    for arq, peso in lista:
        idx, d = ler_alvo(arq)
        if len(idx):
            coords[idx] += d * peso
    return coords


def alvos_de_detalhe(dados, detalhes):
    """{"nose/nose-width-incr": 0.4, ...} → [(arquivo, peso)] (valores negativos usam o alvo oposto)."""
    lista = []
    for nome, valor in (detalhes or {}).items():
        arq = os.path.join(dados, "targets", nome + ".target.gz")
        if os.path.isfile(arq) and abs(valor) > 1e-4:
            lista.append((arq, float(valor)))
    return lista


# ------------------------------------------------------------------ coordenadas


def para_blender(p):
    """MakeHuman (Y para cima, decímetros, olhando +Z) → Blender (Z para cima, metros, olhando -Y)."""
    p = np.asarray(p, dtype=np.float64) * ESCALA
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], axis=-1)


def vertices_do_grupo(faces, grupos, nome):
    vs = set()
    for fi in grupos.get(nome, []):
        vs.update(faces[fi][0])
    return sorted(vs)


# ------------------------------------------------------------------ materiais


def _imagem(caminho):
    if not caminho or not os.path.isfile(caminho):
        return None
    img = bpy.data.images.load(caminho, check_existing=True)
    return img


def material_pele(nome, mhmat, tom=None):
    mat = bpy.data.materials.new(nome)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = _imagem(os.path.join(mhmat["_pasta"], mhmat.get("diffuseTexture", ""))) if mhmat else None
    if tex:
        no = nt.nodes.new("ShaderNodeTexImage")
        # tom de pele pedido (orc, goblin, demônio ou tom humano): recolore os pixels
        no.image = tingir_imagem(tex, tom, 0.8) if tom else tex
        cor_saida = no.outputs["Color"]
        nt.links.new(cor_saida, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*c.cor_hex(tom or "#d6a58a"), 1.0)
    bsdf.inputs["Roughness"].default_value = 0.52
    for k, v in (("Subsurface Weight", 0.12), ("Subsurface Scale", 0.012), ("Specular IOR Level", 0.45)):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    # poros e rugas finos (só no render; o jogo usa a textura)
    bump = nt.nodes.new("ShaderNodeBump")
    ruido = nt.nodes.new("ShaderNodeTexNoise")
    ruido.inputs["Scale"].default_value = 900.0
    ruido.inputs["Detail"].default_value = 6.0
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(ruido.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


_TINGIDAS = {}


def _olho_natural(mat):
    """O branco do olho do pacote é branco-azulado demais e a íris saturada: puxa para o natural
    (esclera marfim, um pouco de rosa nos cantos) e põe a camada molhada (verniz) por cima."""
    nt = mat.node_tree
    no = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image is not None), None)
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if no is not None:
        img = no.image
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)
        lin = np.clip(px[..., :3], 0, 1) ** 2.2
        lum = (lin @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[..., None]
        lin = lum + (lin - lum) * 0.72
        branco = np.clip((lum - 0.45) / 0.3, 0, 1)
        lin = lin * (1 - branco * 0.22) * np.array([1.0, 0.95, 0.9], dtype=np.float32)
        px[..., :3] = np.clip(lin, 0, 1) ** (1 / 2.2)
        nova = bpy.data.images.new(img.name + "_natural", w, h, alpha=True)
        nova.pixels.foreach_set(px.ravel())
        nova.pack()
        no.image = nova
    for k, v in (("Coat Weight", 1.0), ("Coat Roughness", 0.02), ("Coat IOR", 1.376), ("Roughness", 0.25), ("Subsurface Weight", 0.2)):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v


def tingir_imagem(img, cor, contraste=1.0):
    """Recolore a textura mantendo o desenho claro/escuro (fios do cabelo, pelos da sobrancelha):
    a média vira a cor pedida. Vai nos pixels, então o glb e a engine recebem a mesma cor."""
    chave = (img.name, cor, contraste)
    if chave in _TINGIDAS:
        return _TINGIDAS[chave]
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    rgb = np.clip(px[:, :3], 0, 1) ** 2.2
    alfa = px[:, 3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    vis = alfa > 0.3
    media = float(lum[vis].mean()) if vis.any() else float(lum.mean()) or 1e-3
    alvo = np.array(c.cor_hex(cor), dtype=np.float32)
    rel = 1.0 + (lum / max(media, 1e-4) - 1.0) * contraste
    novo = np.clip(rel[:, None] * alvo[None, :], 0, 1) ** (1 / 2.2)
    px[:, :3] = novo
    nova = bpy.data.images.new(f"{img.name}_{cor.lstrip('#')}", w, h, alpha=True)
    nova.pixels.foreach_set(px.ravel())
    nova.pack()
    _TINGIDAS[chave] = nova
    return nova


def material_de_mhmat(nome, mhmat, alfa=False, rugosidade=0.6, metal=0.0, cor=None):
    mat = bpy.data.materials.new(nome)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = None
    if mhmat:
        tex = _imagem(os.path.join(mhmat["_pasta"], mhmat.get("diffuseTexture", "")))
    if tex:
        no = nt.nodes.new("ShaderNodeTexImage")
        no.image = tingir_imagem(tex, cor, 0.9) if cor else tex
        nt.links.new(no.outputs["Color"], bsdf.inputs["Base Color"])
        if alfa:
            nt.links.new(no.outputs["Alpha"], bsdf.inputs["Alpha"])
            try:
                mat.blend_method = "HASHED"
            except Exception:
                pass
        nm = mhmat.get("normalmapTexture")
        if nm and _imagem(os.path.join(mhmat["_pasta"], nm)):
            nmt = nt.nodes.new("ShaderNodeTexImage")
            nmt.image = _imagem(os.path.join(mhmat["_pasta"], nm))
            nmt.image.colorspace_settings.name = "Non-Color"
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(nmt.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    elif cor:
        bsdf.inputs["Base Color"].default_value = (*c.cor_hex(cor), 1.0)
    bsdf.inputs["Roughness"].default_value = rugosidade
    bsdf.inputs["Metallic"].default_value = metal
    return mat


# ------------------------------------------------------------------ montagem


class Humano:
    """Corpo do MakeHuman com esqueleto de jogo, pesos e acessórios (proxies)."""

    def __init__(self, dados, assets, ficha):
        self.dados = dados
        self.assets = assets
        self.ficha = ficha
        self.v_obj, self.vt, self.faces, self.grupos = ler_obj(os.path.join(dados, "3dobjs", "base.obj"))
        coords = self.v_obj.copy()
        aplicar_alvos(coords, alvos_macro(dados, ficha.get("macro", {})))
        aplicar_alvos(coords, alvos_de_detalhe(dados, ficha.get("detalhes")))
        self.coords_mh = coords
        bl = para_blender(coords)
        self.chao = bl[vertices_do_grupo(self.faces, self.grupos, "body"), 2].min()
        bl[:, 2] -= self.chao
        self.coords = bl
        self.pesos = {}

    # -- corpo
    def corpo(self, nome):
        faces_corpo = [self.faces[i] for i in self.grupos["body"]]
        malha = bpy.data.meshes.new(nome)
        malha.from_pydata(self.coords.tolist(), [], [f[0] for f in faces_corpo])
        if self.vt is not None:
            uv = malha.uv_layers.new(name="UVMap")
            k = 0
            for f in faces_corpo:
                for t in f[1]:
                    uv.data[k].uv = self.vt[t] if t >= 0 else (0.0, 0.0)
                    k += 1
        malha.validate()
        obj = bpy.data.objects.new(nome, malha)
        bpy.context.scene.collection.objects.link(obj)
        for p in malha.polygons:
            p.use_smooth = True
        self.obj = obj
        return obj

    # -- esqueleto
    def _posicao(self, d):
        estrategia = d.get("strategy", "CUBE")
        if estrategia == "CUBE" and d.get("cube_name"):
            vs = vertices_do_grupo(self.faces, self.grupos, d["cube_name"])
            if vs:
                return Vector(self.coords[vs].mean(axis=0))
        if d.get("vertex_indices"):
            return Vector(self.coords[d["vertex_indices"]].mean(axis=0))
        if d.get("vertex_index") is not None:
            return Vector(self.coords[d["vertex_index"]])
        p = d.get("default_position", [0, 0, 0])
        return Vector((p[0], p[1], p[2] - self.chao))

    def esqueleto(self, nome, rig="game_engine"):
        with open(os.path.join(self.dados, "rigs", "standard", f"rig.{rig}.json")) as f:
            defs = json.load(f)
        dados = bpy.data.armatures.new(nome + "_esqueleto")
        arm = bpy.data.objects.new(nome + "_esqueleto", dados)
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        for o in bpy.context.scene.objects:
            o.select_set(o == arm)
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = {}
        for osso, d in defs.items():
            eb = dados.edit_bones.new(osso)
            eb.head = self._posicao(d["head"])
            eb.tail = self._posicao(d["tail"])
            if (eb.tail - eb.head).length < 1e-4:
                eb.tail = eb.head + Vector((0, 0, 0.02))
            eb.roll = float(d.get("roll", 0.0))
            ebs[osso] = eb
        for osso, d in defs.items():
            if d.get("parent"):
                ebs[osso].parent = ebs[d["parent"]]
                ebs[osso].use_connect = bool(d.get("use_connect", False))
        # mandíbula (do rig padrão do MakeHuman): a engine abre a boca pela curva da fala
        jaw = None
        if "jaw" not in defs and "head" in ebs:
            arq = os.path.join(self.dados, "rigs", "standard", "rig.default.json")
            if os.path.isfile(arq):
                with open(arq) as f:
                    jaw = json.load(f).get("jaw")
            if jaw:
                eb = dados.edit_bones.new("jaw")
                eb.head = self._posicao(jaw["head"])
                eb.tail = self._posicao(jaw["tail"])
                if (eb.tail - eb.head).length < 1e-4:
                    eb.tail = eb.head + Vector((0, -0.04, -0.05))
                eb.roll = float(jaw.get("roll", 0.0))
                eb.parent = ebs["head"]
        bpy.ops.object.mode_set(mode="OBJECT")
        with open(os.path.join(self.dados, "rigs", "standard", f"weights.{rig}.json")) as f:
            self.pesos = json.load(f)["weights"]
        if jaw:
            with open(os.path.join(self.dados, "rigs", "standard", "weights.default.json")) as f:
                w_jaw = json.load(f)["weights"].get("jaw", [])
            if w_jaw:
                # o queixo e o lábio de baixo passam da cabeça para a mandíbula (a soma continua 1)
                jw = {int(vi): float(w) for vi, w in w_jaw}
                for osso in ("head", "neck_01"):
                    if osso in self.pesos:
                        self.pesos[osso] = [[vi, w * (1.0 - jw.get(int(vi), 0.0))] for vi, w in self.pesos[osso]]
                self.pesos["jaw"] = [[vi, w] for vi, w in jw.items()]
        self.arm = arm
        return arm

    def pesar(self, obj, pesos_por_vertice=None):
        """Grupos de vértices do esqueleto. Sem pesos dados, usa os da malha base (mesmos índices)."""
        pesos = pesos_por_vertice or self.pesos
        for osso, lista in pesos.items():
            if not lista:
                continue
            g = obj.vertex_groups.get(osso) or obj.vertex_groups.new(name=osso)
            for vi, w in lista:
                if vi < len(obj.data.vertices):
                    g.add([int(vi)], float(w), "REPLACE")
        mod = obj.modifiers.new("esqueleto", "ARMATURE")
        mod.object = self.arm
        obj.parent = self.arm

    # -- proxies (olhos, sobrancelhas, cabelo, roupa)
    def encaixar(self, caminho_mhclo, nome, material=None, alfa=False, cor=None, rugosidade=0.6):
        info = ler_mhclo(caminho_mhclo)
        obj_arq = os.path.join(info["_pasta"], info.get("obj_file", ""))
        if not os.path.isfile(obj_arq):
            return None
        v, vt, faces, _ = ler_obj(obj_arq)
        refs = np.array(info["refs"], dtype=np.int64)
        pesos = np.array(info["pesos"])
        desloc = np.array(info["desloc"])
        escala = np.ones(3)
        for i, eixo in enumerate("xyz"):
            if eixo in info["escala"]:
                a, b, den = info["escala"][eixo]
                escala[i] = abs(self.coords_mh[a, i] - self.coords_mh[b, i]) / den if den else 1.0
        base = (self.coords_mh[refs] * pesos[..., None]).sum(axis=1)
        pos_mh = base + desloc * escala
        pos = para_blender(pos_mh)
        pos[:, 2] -= self.chao
        n = min(len(pos), len(v))
        malha = bpy.data.meshes.new(nome)
        malha.from_pydata(pos[:n].tolist(), [], [f[0] for f in faces if max(f[0]) < n])
        if vt is not None:
            uv = malha.uv_layers.new(name="UVMap")
            k = 0
            for f in faces:
                if max(f[0]) >= n:
                    continue
                for t in f[1]:
                    uv.data[k].uv = vt[t] if t >= 0 else (0.0, 0.0)
                    k += 1
        malha.validate()
        for p in malha.polygons:
            p.use_smooth = True
        obj = bpy.data.objects.new(nome, malha)
        bpy.context.scene.collection.objects.link(obj)
        mhmat = None
        if info.get("material"):
            arq_mat = os.path.join(info["_pasta"], info["material"])
            if os.path.isfile(arq_mat):
                mhmat = ler_mhmat(arq_mat)
        if material is None:
            material = material_de_mhmat(nome + "_mat", mhmat, alfa=alfa, cor=cor, rugosidade=rugosidade)
        obj.data.materials.append(material)
        # pesos do proxy = mistura dos pesos dos 3 vértices da malha base
        if self.pesos:
            por_vertice = {}
            mapa = {}
            for osso, lista in self.pesos.items():
                for vi, w in lista:
                    mapa.setdefault(int(vi), []).append((osso, w))
            for i in range(n):
                acum = {}
                for r, wr in zip(refs[i], pesos[i]):
                    for osso, w in mapa.get(int(r), []):
                        acum[osso] = acum.get(osso, 0.0) + w * wr
                for osso, w in acum.items():
                    if w > 1e-4:
                        por_vertice.setdefault(osso, []).append((i, w))
            self.pesar(obj, por_vertice)
        obj["apagar"] = info["apagar"]
        return obj

    def esconder_sob_roupa(self, indices):
        """Apaga do corpo os vértices que a roupa cobre (evita a pele atravessar)."""
        if not indices:
            return
        bm = bmesh.new()
        bm.from_mesh(self.obj.data)
        bm.verts.ensure_lookup_table()
        alvo = [bm.verts[i] for i in set(indices) if i < len(bm.verts)]
        bmesh.ops.delete(bm, geom=alvo, context="VERTS")
        bm.to_mesh(self.obj.data)
        bm.free()

    def limpar_soltos(self):
        bm = bmesh.new()
        bm.from_mesh(self.obj.data)
        soltos = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=soltos, context="VERTS")
        bm.to_mesh(self.obj.data)
        bm.free()


def _primeiro(pasta, padrao_nome=None):
    if not os.path.isdir(pasta):
        return None
    for raiz, _, arquivos in os.walk(pasta):
        for a in sorted(arquivos):
            if a.endswith(".mhclo") and (padrao_nome is None or padrao_nome in a):
                return os.path.join(raiz, a)
    return None


def pele_para(assets, ficha):
    """Escolhe a textura de pele pela idade, gênero e tom."""
    m = ficha.get("macro", {})
    genero = "male" if m.get("genero", 0.5) >= 0.5 else "female"
    idade = m.get("idade", 0.5)
    faixa = "young" if idade < 0.62 else ("middleage" if idade < 0.85 else "old")
    racas = m.get("racas") or {"caucasian": 1.0}
    raca = max(racas, key=racas.get)
    pasta = os.path.join(assets, "skins")
    for nome in (f"{faixa}_{raca}_{genero}", f"young_{raca}_{genero}", f"middleage_{raca}_{genero}", f"young_caucasian_{genero}"):
        p = os.path.join(pasta, nome, nome + ".mhmat")
        if os.path.isfile(p):
            return ler_mhmat(p)
    return None


def _olho_leitoso(mat):
    """Olho de morto-vivo: íris e pupila cobertas por um véu leitoso, esclera amarelada com vasinhos."""
    nt = mat.node_tree
    no = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image is not None), None)
    if no is None:
        return
    img = no.image
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    lin = np.clip(px[..., :3], 0, 1) ** 2.2
    lum = (lin @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[..., None]
    branco = np.clip((lum - 0.45) / 0.3, 0, 1)
    veu = np.array([0.62, 0.64, 0.6], dtype=np.float32)
    # onde não é esclera (íris e pupila): véu leitoso por cima, deixando só um vestígio da íris
    lin = lin * branco + (veu * 0.6 + lin * 0.4 + lum * 0.1) * (1 - branco)
    lin = lin * (1 - 0.25 * branco) + np.array([0.55, 0.45, 0.3], dtype=np.float32) * 0.25 * branco
    px[..., :3] = np.clip(lin, 0, 1) ** (1 / 2.2)
    nova = bpy.data.images.new(img.name + "_leitoso", w, h, alpha=True)
    nova.pixels.foreach_set(px.ravel())
    nova.pack()
    no.image = nova


def criar_humano(dados, assets, ficha):
    """Humano completo: corpo, pele, olhos, sobrancelhas, cílios, dentes, cabelo e roupas do pacote."""
    nome = ficha.get("id", "humano")
    h = Humano(dados, assets, ficha)
    corpo = h.corpo(nome + "_corpo")
    arm = h.esqueleto(nome, ficha.get("rig", "game_engine"))
    corpo.data.materials.append(material_pele(nome + "_pele", pele_para(assets, ficha), ficha.get("tom_de_pele")))
    h.pesar(corpo)
    pecas = [corpo]
    acessorios = [
        ("eyes", ficha.get("olhos_modelo", "high-poly"), False, None),
        ("eyebrows", ficha.get("sobrancelha") or ("eyebrow012" if ficha.get("macro", {}).get("genero", 0.5) >= 0.5 else "eyebrow011"), True,
         ficha.get("cor_cabelo")),
        ("eyelashes", ficha.get("cilios", "eyelashes01"), True, None),
        ("teeth", "teeth_base", False, None),
    ]
    res_pele = int(ficha.get("textura_pele") or 0)
    tem_cabelo = ficha.get("cabelo", "short02") not in (None, "", "nenhum")
    import fc_cabelo

    # cabelo curto: penteado fio a fio + cards (pipeline AAA); médio/comprido: ainda o do pacote,
    # até a queda com colisão nos ombros ficar pronta (plano, etapa 1.2)
    cards = bool(res_pele) and tem_cabelo and fc_cabelo.estilo_de(ficha.get("cabelo")) == "curto"
    if tem_cabelo and not cards:
        acessorios.append(("hair", ficha.get("cabelo", "short02"), True, ficha.get("cor_cabelo")))
    for roupa in ficha.get("roupas_makehuman", []):
        acessorios.append(("clothes", roupa, False, None))
    apagar = []
    for tipo, quem, alfa, cor in acessorios:
        mhclo = _primeiro(os.path.join(assets, tipo, quem)) or _primeiro(os.path.join(assets, tipo), quem)
        if not mhclo:
            continue
        mat = None
        if tipo == "eyes":
            cor_olho = ficha.get("cor_olhos", "brown")
            arq = os.path.join(assets, "eyes", "materials", cor_olho + ".mhmat")
            mat = material_de_mhmat(nome + "_olhos", ler_mhmat(arq) if os.path.isfile(arq) else None, alfa=True, rugosidade=0.05)
            _olho_natural(mat)
            if ficha.get("zumbi"):
                _olho_leitoso(mat)
        o = h.encaixar(mhclo, f"{nome}_{tipo}", material=mat, alfa=alfa, cor=cor, rugosidade=0.45 if tipo == "hair" else 0.6)
        if o is not None:
            pecas.append(o)
            if tipo == "clothes":
                apagar.extend(o.get("apagar", []))
    h.esconder_sob_roupa(apagar)
    if ficha.get("roupa"):
        import fc_roupa

        r = ficha["roupa"]
        pecas.extend(fc_roupa.vestir(h, nome, r.get("estilo", "campones"), r.get("cores", {}), capa=r.get("capa", True),
                                    pano=r.get("pano", False), sujo=r.get("sujo", bool(ficha.get("zumbi")))))
    if res_pele and corpo.data.polygons:
        # pele em alta: poros, rugas pela idade, barba rala e vermelhidão assados em cor/rugosidade/normal
        import fc_pele

        mat = corpo.data.materials[0]
        olhos = next((o for o in pecas if o.name.endswith("_eyes")), None)
        dentes = next((o for o in pecas if o.name.endswith("_teeth")), None)
        cor, rug, nor = fc_pele.gerar(corpo, fc_pele.base_da_pele(mat), ficha, olhos, dentes, res=res_pele,
                                      cor_barba=ficha.get("cor_cabelo") or "#2a1e16")
        fc_pele.aplicar(mat, cor, rug, nor)
        # no render a malha é subdividida (silhueta lisa); no glb e na engine vai a malha do jogo
        sub = corpo.modifiers.new("subdivisao_render", "SUBSURF")
        sub.levels = 0
        sub.render_levels = 2
        sub.quality = 3
        if cards:
            # cabelo em cards (mechas com textura de fios), no lugar do "capacete" do pacote

            g = corpo.vertex_groups.get("head")
            peso = np.zeros(len(corpo.data.vertices))
            if g is not None:
                for v in corpo.data.vertices:
                    for ge in v.groups:
                        if ge.group == g.index:
                            peso[v.index] = ge.weight
            pontos = fc_pele.pontos_do_rosto(corpo, olhos, dentes)
            cor_cab = ficha.get("cor_cabelo") or "#3b2a1e"
            # padrão AAA (bíblia técnica, seção 4): o penteado fio a fio é a fonte; o render e a
            # engine recebem o couro cabeludo com fade e os cards em 3 camadas com o atlas de mechas
            idade = float(ficha.get("macro", {}).get("idade", 0.5))
            pecas.extend(fc_cabelo.cabelo_em_cards(nome, corpo, pontos, peso, cor_cab, fc_cabelo.estilo_de(ficha.get("cabelo")), arm,
                                                   escala_n=1.0 if res_pele >= 4096 else 0.7,
                                                   grisalho=float(np.clip((idade - 0.62) / 0.3, 0.0, 0.7))))
    arma = ficha.get("arma")
    if arma and arma != "nenhuma":
        import fc_armas_pbr

        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        if arma == "espada":
            o = fc_armas_pbr.espada_longa(nome, ficha.get("cores_arma"))
        else:
            import fc_armas

            o = fc_armas.criar_arma({"tipo": arma, "id": f"{nome}_{arma}", "escala": 1.0})
        fc_armas_pbr.prender_na_mao(o, arm, "r")
        pecas.append(o)
        if ficha.get("escudo"):
            cores = (ficha.get("roupa") or {}).get("cores", {})
            e = fc_armas_pbr.escudo_pipa(nome, cores.get("secundaria", "#d8d2c4"), cores.get("principal", "#8a1f1a"))
            fc_armas_pbr.prender_na_mao(e, arm, "l", escudo=True)
            pecas.append(e)
        arm.data.pose_position = "POSE"
    h.limpar_soltos()
    return arm, pecas, h
