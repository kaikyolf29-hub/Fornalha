# Fornalha: 3D por API paga (opcional, desligada por padrão; a pessoa liga e põe a chave na janela).
#   python api_3d.py <provedor> <imagem.png> <saida.glb> <resultado.json> [opcoes.json]
# A chave vem na variável FORNALHA_CHAVE_API (nunca na linha de comando nem no registro).
# meshy: https://docs.meshy.ai/en/api/image-to-3d (plano pago; 30 créditos com textura 2K, Meshy 7.1).
# FORNALHA_API_BASE troca o endereço (só para os testes, com um servidor falso em 127.0.0.1).
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request


def pedir(metodo, url, chave, corpo=None, tempo=120):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Authorization": f"Bearer {chave}", "Content-Type": "application/json", "User-Agent": "Fornalha"})
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")[:400]
        if e.code == 401:
            raise RuntimeError("a chave da API foi recusada (401): confira a chave em Máquina → APIs")
        if e.code == 402:
            raise RuntimeError("sem créditos ou sem plano pago na Meshy (402): a API exige plano pago")
        raise RuntimeError(f"a API respondeu {e.code}: {texto}")


def baixar(url, destino):
    req = urllib.request.Request(url, headers={"User-Agent": "Fornalha"})
    with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)


def meshy(imagem, saida, opcoes, chave):
    base = os.environ.get("FORNALHA_API_BASE", "https://api.meshy.ai")
    with open(imagem, "rb") as f:
        uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    corpo = {
        "image_url": uri,
        "ai_model": opcoes.get("ai_model", "latest"),
        "should_texture": True,
        "enable_pbr": True,
        "should_remesh": True,
        "topology": "triangle",
        "target_polycount": int(opcoes.get("triangulos", 60000)),
        # pose A: o esqueleto encaixa melhor
        "pose_mode": opcoes.get("pose_mode", "a-pose"),
        "target_formats": ["glb"],
    }
    tarefa = pedir("POST", f"{base}/openapi/v1/image-to-3d", chave, corpo)["result"]
    print(f"tarefa {tarefa}", flush=True)
    inicio = time.time()
    while True:
        t = pedir("GET", f"{base}/openapi/v1/image-to-3d/{tarefa}", chave)
        st = t.get("status")
        if st == "SUCCEEDED":
            break
        if st in ("FAILED", "CANCELED"):
            raise RuntimeError(f"a Meshy não conseguiu: {(t.get('task_error') or {}).get('message', st)}")
        if time.time() - inicio > float(opcoes.get("minutos", 30)) * 60:
            raise RuntimeError("a Meshy não terminou a tempo")
        print(f"  {st} {t.get('progress', 0)}%", flush=True)
        time.sleep(float(opcoes.get("intervalo", 5)))
    url = (t.get("model_urls") or {}).get("glb")
    if not url:
        raise RuntimeError("a Meshy terminou sem o arquivo .glb")
    baixar(url, saida)
    return {"provedor": "meshy", "tarefa": tarefa, "creditos": t.get("consumed_credits"), "segundos": round(time.time() - inicio, 1)}


def main():
    a = sys.argv[1:]
    if len(a) < 4:
        print("uso: api_3d.py <provedor> <imagem.png> <saida.glb> <resultado.json> [opcoes.json]")
        sys.exit(2)
    provedor, imagem, saida, resultado = a[:4]
    opcoes = json.load(open(a[4], encoding="utf-8")) if len(a) > 4 else {}
    chave = os.environ.get("FORNALHA_CHAVE_API", "")
    try:
        if not chave:
            raise RuntimeError("sem chave da API (ponha em Máquina → APIs)")
        if provedor != "meshy":
            raise RuntimeError(f"provedor ainda não suportado: {provedor}")
        r = meshy(imagem, saida, opcoes, chave)
        r["ok"] = True
    except Exception as e:
        r = {"ok": False, "erro": str(e)}
    with open(resultado, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
