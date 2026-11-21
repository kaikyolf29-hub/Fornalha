# Fornalha: baixa os pacotes de conteúdo CC0 (só quando a pessoa pede, pela janela
# ou pela linha de comando). Nada é enviado; só baixado. Fica só o que a Fornalha
# usa (dados e imagens); arquivos de código ou de outros programas são descartados.
#   python pacotes.py <makehuman|animacoes|materiais> <pasta>
import io
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

AGENTE = "Fornalha/0.1 (pacotes de conteudo)"

MAKEHUMAN = {
    "mpfb": "https://extensions.blender.org/download/sha256:c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad/add-on-mpfb-v2.0.18.zip",
    "assets": "http://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip",
}
ANIMACOES = {
    "ual1": "https://opengameart.org/sites/default/files/universal_animation_librarystandard.zip",
    "ual2": "https://opengameart.org/sites/default/files/universal_animation_library_2standard.zip",
}
MATERIAIS = ["Metal038", "Metal056C", "Metal048C", "Chainmail004", "Leather037", "Leather026", "Fabric031", "Fabric019",
             "Planks037A", "PavingStones153", "Bricks113A", "RoofingTiles014B", "Ground106", "Rock051"]
CEUS = ["DayEnvironmentHDRI113", "DaySkyHDRI069A"]
MAPAS = ("_Color.jpg", "_NormalGL.jpg", "_Roughness.jpg", "_Metalness.jpg", "_AmbientOcclusion.jpg", "_Opacity.jpg", "_HDR.exr")


def log(pasta, texto):
    linha = f"[{time.strftime('%H:%M:%S')}] {texto}"
    print(linha, flush=True)
    with open(os.path.join(pasta, "pacote.log"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def extrair(dados, destino, filtro):
    """Extrai do zip só o que passa no filtro(caminho) → caminho relativo de destino (ou None)."""
    n = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            alvo = filtro(info.filename)
            if not alvo or ".." in alvo.replace("\\", "/").split("/"):
                continue
            caminho = os.path.join(destino, alvo)
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            with z.open(info) as src, open(caminho, "wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
    return n


def makehuman(pasta):
    log(pasta, "Baixando os dados do MakeHuman (malha base, formas e esqueletos, CC0)")
    dados = baixar(MAKEHUMAN["mpfb"])

    def so_dados(nome):
        partes = nome.split("/")
        if "data" in partes:
            i = partes.index("data")
            resto = partes[i + 1:]
            if resto and resto[0] in ("3dobjs", "targets", "rigs"):
                return os.path.join("dados", *resto)
        return None

    log(pasta, f"{extrair(dados, pasta, so_dados)} arquivos de dados")
    log(pasta, "Baixando o pacote de pele, olhos, cabelo e roupas (CC0, ~280 MB)")
    assets = baixar(MAKEHUMAN["assets"])
    tipos = ("skins", "eyes", "eyebrows", "eyelashes", "teeth", "tongue", "hair", "clothes")

    def so_assets(nome):
        partes = nome.split("/")
        for i, p in enumerate(partes):
            if p in tipos:
                return os.path.join("assets", *partes[i:])
        return None

    log(pasta, f"{extrair(assets, pasta, so_assets)} arquivos de assets")
    return {"dados": os.path.join(pasta, "dados"), "assets": os.path.join(pasta, "assets"),
            "licenca": "CC0 (MakeHuman: malha base, formas, pesos e assets do sistema)", "fontes": list(MAKEHUMAN.values())}


def animacoes(pasta):
    saida = {}
    for chave, url in ANIMACOES.items():
        log(pasta, f"Baixando {chave} (Quaternius Universal Animation Library, CC0)")
        dados = baixar(url)
        alvo = {}

        def so_glb(nome, chave=chave):
            if nome.lower().endswith(".glb") and ("Godot" in nome or "Unreal-Godot" in nome) and "Mannequin_F" not in nome:
                alvo["glb"] = os.path.join(chave, os.path.basename(nome))
                return alvo["glb"]
            if nome.endswith("License.txt"):
                return os.path.join(chave, "License.txt")
            return None

        extrair(dados, pasta, so_glb)
        if "glb" in alvo:
            saida[chave] = os.path.join(pasta, alvo["glb"])
    return {"bibliotecas": saida, "licenca": "CC0 (Quaternius)", "fontes": list(ANIMACOES.values())}


def materiais(pasta, resolucao="1K"):
    feitos = []
    for ident in MATERIAIS:
        log(pasta, f"Baixando {ident} ({resolucao}, ambientCG, CC0)")
        dados = baixar(f"https://ambientcg.com/get?file={ident}_{resolucao}-JPG.zip")
        extrair(dados, os.path.join(pasta, ident), lambda n: os.path.basename(n) if n.endswith(MAPAS) else None)
        feitos.append(ident)
    for ident in CEUS:
        log(pasta, f"Baixando o céu {ident} (2K, ambientCG, CC0)")
        dados = baixar(f"https://ambientcg.com/get?file={ident}_2K.zip")
        extrair(dados, os.path.join(pasta, ident), lambda n: os.path.basename(n) if n.endswith(MAPAS) else None)
        feitos.append(ident)
    ceu = os.path.join(pasta, CEUS[0], f"{CEUS[0]}_2K_HDR.exr")
    return {"materiais": pasta, "ceu": ceu, "itens": feitos, "licenca": "CC0 (ambientCG)", "fontes": ["https://ambientcg.com"]}


PACOTES = {"makehuman": makehuman, "animacoes": animacoes, "materiais": materiais}


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in PACOTES:
        print(f"uso: python pacotes.py <{'|'.join(PACOTES)}> <pasta>", file=sys.stderr)
        sys.exit(2)
    pacote, pasta = sys.argv[1], os.path.abspath(sys.argv[2])
    os.makedirs(pasta, exist_ok=True)
    try:
        info = PACOTES[pacote](pasta)
        info.update({"pacote": pacote, "instalado_em": time.strftime("%Y-%m-%dT%H:%M:%S")})
        with open(os.path.join(pasta, "pacote.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        log(pasta, "Pronto.")
    except Exception as e:
        log(pasta, f"ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
