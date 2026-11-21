# Fornalha: materiais PBR a partir das texturas CC0 do ambientCG (cor, normal,
# rugosidade, metal, oclusão). Só as imagens são lidas; os .blend do pacote não.
import os

import bpy

import fc_comum as c

# nome da Fornalha → pasta do ambientCG, escala da textura (repetições por metro), metal
BIBLIOTECA = {
    "aco": ("Metal038", 2.5, 1.0),
    "ferro_velho": ("Metal056C", 2.0, 1.0),
    "ouro": ("Metal048C", 3.0, 1.0),
    "cota_de_malha": ("Chainmail004", 9.0, 1.0),
    "couro": ("Leather037", 3.0, 0.0),
    "couro_escuro": ("Leather026", 3.0, 0.0),
    "tecido": ("Fabric031", 22.0, 0.0),
    "tecido_grosso": ("Fabric031", 5.0, 0.0),
    "madeira": ("Planks037A", 1.2, 0.0),
    "calcamento": ("PavingStones153", 0.5, 0.0),
    "pedra": ("Bricks113A", 0.6, 0.0),
    "telha": ("RoofingTiles014B", 0.8, 0.0),
    "terra": ("Ground106", 0.35, 0.0),
    "grama": ("Grass004", 0.4, 0.0),
    "chao_floresta": ("Ground037", 0.35, 0.0),
    "casca": ("Bark014", 1.5, 0.0),
    "reboco": ("Plaster007", 0.6, 0.0),
    "viga": ("WoodFloor064", 1.0, 0.0),
    "rocha": ("Rock051", 0.5, 0.0),
}

_PASTA = {"raiz": None}


def definir_pasta(pasta):
    _PASTA["raiz"] = pasta


def _mapa(pasta, ident, sufixos):
    for s in sufixos:
        for res in ("2K", "1K", "4K"):
            p = os.path.join(pasta, f"{ident}_{res}-JPG_{s}.jpg")
            if os.path.isfile(p):
                return p
    return None


def disponivel(nome):
    if not _PASTA["raiz"] or nome not in BIBLIOTECA:
        return False
    ident = BIBLIOTECA[nome][0]
    return _mapa(os.path.join(_PASTA["raiz"], ident), ident, ("Color",)) is not None


_CACHE_FINAL = {}


def _cor_final(img, tom, fator, modo, caminho_ao):
    """Imagem nova = textura tingida (como o nó Mix) × oclusão. Fica empacotada no glb."""
    if img is None or (not tom and not caminho_ao):
        return None
    chave = (img.name, tom, round(fator, 3), modo, caminho_ao)
    if chave in _CACHE_FINAL:
        return _CACHE_FINAL[chave]
    import numpy as np

    w, h = img.size
    if not w or not h:
        return None
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    rgb = px[:, :3]
    if tom:
        if modo != "MIX":
            fator = max(fator, 0.92)  # pano pintado: quase toda a cor vem do tom pedido
        t = np.array([int(tom.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)
        if modo == "MIX":
            alvo = np.broadcast_to(t, rgb.shape)
        else:  # COLOR: mantém o desenho claro/escuro da textura, mas na média vira a cor pedida
            pesos_l = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            lum = (rgb @ pesos_l)[:, None]
            media = max(float(lum.mean()), 1e-4)
            # contraste do desenho reduzido para cores claras (pano branco não fica cinza manchado)
            lum_t = float(t @ pesos_l)
            contraste = 1.0 - 0.6 * max(0.0, lum_t - 0.5) / 0.5
            rel = 1.0 + (lum / media - 1.0) * contraste
            alvo = np.clip(rel * t, 0.0, 1.0)
        rgb = rgb * (1 - fator) + alvo * fator
    if caminho_ao and os.path.isfile(caminho_ao):
        ao_img = bpy.data.images.load(caminho_ao, check_existing=True)
        if tuple(ao_img.size) == (w, h):
            ao = np.empty(w * h * 4, dtype=np.float32)
            ao_img.pixels.foreach_get(ao)
            ao = ao.reshape(-1, 4)[:, :1]
            rgb = rgb * (1 - 0.8 + 0.8 * ao)
    px[:, :3] = rgb
    nova = bpy.data.images.new(f"{img.name}_final_{len(_CACHE_FINAL)}", w, h, alpha=False)
    nova.pixels.foreach_set(px.ravel())
    nova.pack()
    _CACHE_FINAL[chave] = nova
    return nova


def material(nome, tipo, tom=None, escala=None, rugosidade_extra=0.0, mistura_tom=0.75):
    """Material PBR; sem as texturas, cai para uma cor lisa (o asset continua saindo)."""
    mat = bpy.data.materials.new(nome)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    info = BIBLIOTECA.get(tipo)
    if not info or not disponivel(tipo):
        bsdf.inputs["Base Color"].default_value = (*c.cor_hex(tom or "#808080"), 1.0)
        bsdf.inputs["Metallic"].default_value = info[2] if info else 0.0
        bsdf.inputs["Roughness"].default_value = 0.45 if info and info[2] else 0.75
        mat["pbr"] = False
        return mat
    ident, esc_padrao, metal = info
    pasta = os.path.join(_PASTA["raiz"], ident)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapa = nt.nodes.new("ShaderNodeMapping")
    e = escala if escala is not None else esc_padrao
    mapa.inputs["Scale"].default_value = (e, e, e)
    nt.links.new(coord.outputs["UV"], mapa.inputs["Vector"])

    def textura(caminho, cor=True):
        no = nt.nodes.new("ShaderNodeTexImage")
        no.image = bpy.data.images.load(caminho, check_existing=True)
        if not cor:
            no.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mapa.outputs["Vector"], no.inputs["Vector"])
        return no

    if metal and not tom:
        # as texturas de metal do pacote são escuras para aço; puxa para o refletir de aço de verdade
        tom, mistura_tom = "#c9cbd1", 0.55
    caminho_cor = _mapa(pasta, ident, ("Color",))
    oclusao = _mapa(pasta, ident, ("AmbientOcclusion",))
    cor = textura(caminho_cor)
    # o tingido e a oclusão vão direto nos pixels: o glTF (e a engine) recebe a cor final
    final = _cor_final(cor.image, tom, mistura_tom, "MIX" if metal else "COLOR", oclusao)
    if final is not None:
        cor.image = final
    nt.links.new(cor.outputs["Color"], bsdf.inputs["Base Color"])
    rug = _mapa(pasta, ident, ("Roughness",))
    if rug:
        nt.links.new(textura(rug, cor=False).outputs["Color"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.5 + rugosidade_extra
    met = _mapa(pasta, ident, ("Metalness",))
    if met:
        nt.links.new(textura(met, cor=False).outputs["Color"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = metal
    nor = _mapa(pasta, ident, ("NormalGL",))
    if nor:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(textura(nor, cor=False).outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    opac = _mapa(pasta, ident, ("Opacity",))
    if opac:
        nt.links.new(textura(opac, cor=False).outputs["Color"], bsdf.inputs["Alpha"])
    mat["pbr"] = True
    return mat
