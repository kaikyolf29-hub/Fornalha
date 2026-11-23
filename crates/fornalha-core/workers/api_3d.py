# Fornalha: 3D por API paga (opcional, desligada por padrão; a pessoa liga e põe a chave na janela).
#   python api_3d.py <provedor> <imagem.png> <saida.glb> <resultado.json> [opcoes.json]
# A chave vem na variável FORNALHA_CHAVE_API (nunca na linha de comando nem no registro).
# meshy: https://docs.meshy.ai/en/api/image-to-3d (plano pago; 30 créditos com textura 2K, Meshy 7.1).
# tripo: https://developers.tripo3d.ai/en/docs (upload → image-to-model v3.1 → tarefa; 30 créditos = US$ 0,30).
# rodin: https://docs.hyper3d.ai/en/api-specification/rodin-gen2-5 (multipart → status → download; 0,5 crédito).
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


def _multipart(campos, arquivos):
    """Corpo multipart/form-data: campos de texto e (nome, caminho) de arquivos PNG."""
    limite = "----fornalha" + os.urandom(8).hex()
    partes = []
    for k, v in campos:
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, caminho in arquivos:
        with open(caminho, "rb") as f:
            dados = f.read()
        nome = os.path.basename(caminho)
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{nome}\"\r\n"
                      f"Content-Type: image/png\r\n\r\n".encode() + dados + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def pedir_form(url, chave, campos, arquivos, tempo=180):
    corpo, tipo = _multipart(campos, arquivos)
    req = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Authorization": f"Bearer {chave}", "Content-Type": tipo, "User-Agent": "Fornalha"})
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")[:400]
        if e.code == 401:
            raise RuntimeError("a chave da API foi recusada (401): confira a chave em Máquina → APIs")
        raise RuntimeError(f"a API respondeu {e.code}: {texto}")


def esperar(consultar, minutos, intervalo):
    inicio = time.time()
    espera = intervalo
    while True:
        pronto, info = consultar()
        if pronto:
            return info, time.time() - inicio
        if time.time() - inicio > minutos * 60:
            raise RuntimeError("o serviço não terminou a tempo")
        time.sleep(espera)
        espera = min(espera * 1.3, 30.0)


def tripo(imagem, saida, opcoes, chave):
    base = os.environ.get("FORNALHA_API_BASE", "https://openapi.tripo3d.ai")
    token = pedir_form(f"{base}/v3/files", chave, [], [("file", imagem)])["data"]["file_token"]
    corpo = {"input": token, "model": opcoes.get("modelo", "v3.1-20260211"), "texture": True, "pbr": True,
             "face_limit": int(opcoes.get("triangulos", 60000))}
    tarefa = pedir("POST", f"{base}/v3/generation/image-to-model", chave, corpo)["data"]["task_id"]
    print(f"tarefa {tarefa}", flush=True)

    def consultar():
        d = pedir("GET", f"{base}/v3/tasks/{tarefa}", chave)["data"]
        st = d.get("status")
        if st == "success":
            return True, d
        if st in ("failed", "cancelled", "banned", "expired"):
            raise RuntimeError(f"a Tripo não conseguiu: {d.get('error_message') or st}")
        print(f"  {st} {d.get('progress', 0)}%", flush=True)
        return False, None

    d, seg = esperar(consultar, float(opcoes.get("minutos", 30)), float(opcoes.get("intervalo", 5)))
    url = (d.get("output") or {}).get("model_url")
    if not url:
        raise RuntimeError("a Tripo terminou sem o arquivo do modelo")
    baixar(url, saida)
    return {"provedor": "tripo", "tarefa": tarefa, "creditos": d.get("credits_consumed"), "segundos": round(seg, 1)}


def rodin(imagem, saida, opcoes, chave):
    base = os.environ.get("FORNALHA_API_BASE", "https://api.hyper3d.com")
    campos = [("tier", opcoes.get("tier", "Gen-2.5-Low")), ("geometry_file_format", "glb")]
    r = pedir_form(f"{base}/api/v2/rodin", chave, campos, [("images", imagem)])
    if r.get("error") or not r.get("uuid"):
        raise RuntimeError(f"a Rodin recusou: {r.get('error') or r}")
    uuid, assinatura = r["uuid"], r["jobs"]["subscription_key"]
    print(f"tarefa {uuid}", flush=True)

    def consultar():
        jobs = pedir("POST", f"{base}/api/v2/status", chave, {"subscription_key": assinatura}).get("jobs", [])
        if any(j.get("status") == "Failed" for j in jobs):
            raise RuntimeError("a Rodin não conseguiu gerar")
        if jobs and all(j.get("status") == "Done" for j in jobs):
            return True, jobs
        print(f"  {[j.get('status') for j in jobs]}", flush=True)
        return False, None

    _, seg = esperar(consultar, float(opcoes.get("minutos", 30)), float(opcoes.get("intervalo", 5)))
    lista = pedir("POST", f"{base}/api/v2/download", chave, {"task_uuid": uuid}).get("list", [])
    url = next((x["url"] for x in lista if str(x.get("name", "")).endswith(".glb")), None)
    if not url:
        raise RuntimeError("a Rodin terminou sem o arquivo .glb")
    baixar(url, saida)
    return {"provedor": "rodin", "tarefa": uuid, "creditos": r.get("consumed"), "segundos": round(seg, 1)}


PROVEDORES = {"meshy": None, "tripo": tripo, "rodin": rodin}


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
        if provedor not in PROVEDORES:
            raise RuntimeError(f"provedor desconhecido: {provedor}")
        r = (PROVEDORES[provedor] or meshy)(imagem, saida, opcoes, chave)
        r["ok"] = True
    except Exception as e:
        r = {"ok": False, "erro": str(e)}
    with open(resultado, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
