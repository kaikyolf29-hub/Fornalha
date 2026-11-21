# Fornalha: worker do UniRig (esqueleto e pesos automáticos para qualquer criatura).
# Roda os três passos oficiais do repositório (esqueleto, pele e juntar) e devolve
# o modelo com esqueleto. Para humanoides a Fornalha usa o esqueleto padrão dela
# (que recebe as animações da biblioteca); o UniRig é para o que não é humanoide.
#   tarefa: {"entrada", "saida", "seed", "pasta_temporaria"}
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fw_comum as fw  # noqa: E402


def achar_bash():
    for c in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError("o UniRig precisa do bash (no Windows, o do Git for Windows)")


def passo(bash, script, args, env, log):
    cmd = [bash, script] + args
    r = subprocess.run(cmd, cwd=os.getcwd(), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log.append({"passo": os.path.basename(script), "codigo": r.returncode, "stderr": r.stderr[-1500:]})
    if r.returncode != 0:
        raise RuntimeError(f"{os.path.basename(script)} falhou (código {r.returncode}): {r.stderr[-800:]}")


def tarefa(t):
    entrada = os.path.abspath(t["entrada"])
    saida = os.path.abspath(t["saida"])
    pasta = os.path.abspath(t.get("pasta_temporaria") or os.path.join(os.path.dirname(saida), "unirig"))
    os.makedirs(pasta, exist_ok=True)
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    bash = achar_bash()
    env = dict(os.environ)
    # os scripts chamam "python": que seja o do ambiente do UniRig
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    base = os.path.join("launch", "inference")
    esqueleto = os.path.join(pasta, "esqueleto.fbx")
    pele = os.path.join(pasta, "pele.fbx")
    log = []
    seed = str(t.get("seed") or 12345)
    passo(bash, os.path.join(base, "generate_skeleton.sh"), ["--input", entrada, "--output", esqueleto, "--seed", seed], env, log)
    passo(bash, os.path.join(base, "generate_skin.sh"), ["--input", esqueleto, "--output", pele], env, log)
    passo(bash, os.path.join(base, "merge.sh"), ["--source", pele, "--target", entrada, "--output", saida], env, log)
    if not os.path.isfile(saida):
        raise RuntimeError("o UniRig terminou sem gerar o modelo com esqueleto")
    return {"arquivos": {"modelo": saida}, "estatisticas": {"bytes": os.path.getsize(saida)}, "log": log}


if __name__ == "__main__":
    fw.executar(tarefa)
