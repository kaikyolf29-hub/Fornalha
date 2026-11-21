//! Workers de placa: modelos que só rodam com placa NVIDIA (CUDA), cada um num
//! ambiente Python só dele, instalado pela Fornalha em `<dados>/workers/<id>`:
//! - TRELLIS.2: imagem de conceito → malha alta com cor por vértice (sem o
//!   nvdiffrast; a textura é assada depois no Blender);
//! - UniRig: esqueleto e pesos para criaturas que não são humanoides;
//! - HY-Motion: texto → movimento (SMPL), aplicado no esqueleto padrão no Blender.
//!
//! O protocolo é o mesmo da Forja: `python <worker>.py tarefa.json resultado.json`.
//! Sem a placa ou sem o worker instalado, a Fornalha usa a alternativa que roda
//! em qualquer computador (Forja, esqueleto padrão, biblioteca de animações).

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::externas;
use crate::paths::Paths;

const SCRIPTS: [(&str, &str); 6] = [
    ("fw_comum.py", include_str!("../workers/fw_comum.py")),
    ("trellis2_fornalha.py", include_str!("../workers/trellis2_fornalha.py")),
    ("unirig_fornalha.py", include_str!("../workers/unirig_fornalha.py")),
    ("hymotion_fornalha.py", include_str!("../workers/hymotion_fornalha.py")),
    ("pacotes.py", include_str!("../workers/pacotes.py")),
    ("instalar.py", include_str!("../workers/instalar.py")),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Worker {
    Trellis2,
    UniRig,
    HyMotion,
}

impl Worker {
    pub const TODOS: [Worker; 3] = [Worker::Trellis2, Worker::UniRig, Worker::HyMotion];

    pub fn id(self) -> &'static str {
        match self {
            Worker::Trellis2 => "trellis2",
            Worker::UniRig => "unirig",
            Worker::HyMotion => "hy-motion",
        }
    }

    pub fn nome(self) -> &'static str {
        match self {
            Worker::Trellis2 => "TRELLIS.2 (3D da imagem de conceito)",
            Worker::UniRig => "UniRig (esqueleto para criaturas)",
            Worker::HyMotion => "HY-Motion (movimento a partir do texto)",
        }
    }

    pub fn de_id(id: &str) -> Option<Self> {
        Self::TODOS.into_iter().find(|w| w.id() == id)
    }

    /// Worker que roda um modelo do catálogo.
    pub fn do_modelo(modelo: &str) -> Option<Self> {
        if modelo.starts_with("trellis2") {
            Some(Worker::Trellis2)
        } else if modelo == "unirig" {
            Some(Worker::UniRig)
        } else if modelo.starts_with("hy-motion") {
            Some(Worker::HyMotion)
        } else {
            None
        }
    }

    fn script(self) -> &'static str {
        match self {
            Worker::Trellis2 => "trellis2_fornalha.py",
            Worker::UniRig => "unirig_fornalha.py",
            Worker::HyMotion => "hymotion_fornalha.py",
        }
    }

    /// Grupo de licença que a pessoa precisa aceitar na janela antes de instalar.
    pub fn aceite(self) -> Option<&'static str> {
        match self {
            Worker::HyMotion => Some("tencent-hunyuan"),
            _ => None,
        }
    }

    fn variavel(self) -> String {
        format!("FORNALHA_WORKER_{}", self.id().to_uppercase().replace('-', "_"))
    }
}

/// O que o instalador deixou pronto (`instalacao.json`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Instalacao {
    pub worker: String,
    pub python: PathBuf,
    pub repo: PathBuf,
    /// Dependências proibidas que a verificação comprovou que o worker não usa.
    #[serde(default)]
    pub sem: Vec<String>,
    #[serde(default)]
    pub instalado_em: String,
    #[serde(default)]
    pub verificado_em: Option<String>,
    #[serde(skip)]
    pub arquivo: PathBuf,
}

pub fn pasta(paths: &Paths, w: Worker) -> PathBuf {
    paths.data_dir.join("workers").join(w.id())
}

fn arquivo_da_instalacao(paths: &Paths, w: Worker) -> PathBuf {
    std::env::var_os(w.variavel()).map(PathBuf::from).unwrap_or_else(|| pasta(paths, w).join("instalacao.json"))
}

/// A instalação do worker, se existir e o Python dela ainda estiver no lugar.
pub fn instalacao(paths: &Paths, w: Worker) -> Option<Instalacao> {
    let arq = arquivo_da_instalacao(paths, w);
    let mut inst: Instalacao = serde_json::from_slice(&std::fs::read(&arq).ok()?).ok()?;
    if !inst.python.is_file() || !inst.repo.is_dir() {
        return None;
    }
    inst.arquivo = arq;
    Some(inst)
}

fn guardar(inst: &Instalacao) -> Resultado<()> {
    let texto = serde_json::to_vec_pretty(inst).unwrap_or_default();
    std::fs::write(&inst.arquivo, texto).map_err(|e| Erro::io(&inst.arquivo, e))
}

/// Dependências sem licença comercial que algum worker instalado comprovou não usar.
pub fn sem_dependencias(paths: &Paths) -> Vec<String> {
    let mut v: Vec<String> = Vec::new();
    for w in Worker::TODOS {
        if let Some(i) = instalacao(paths, w) {
            if i.verificado_em.is_some() {
                for d in i.sem {
                    if !v.contains(&d) {
                        v.push(d);
                    }
                }
            }
        }
    }
    v
}

fn assinatura() -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    for (nome, texto) in SCRIPTS {
        h.update(nome.as_bytes());
        h.update(texto.as_bytes());
    }
    hex::encode(&h.finalize()[..6])
}

/// Escreve os scripts dos workers numa pasta da Fornalha.
pub fn preparar_scripts(pasta_dados: &Path) -> Resultado<PathBuf> {
    let pasta = pasta_dados.join("workers").join("scripts").join(assinatura());
    if pasta.join(SCRIPTS[SCRIPTS.len() - 1].0).is_file() {
        return Ok(pasta);
    }
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    for (nome, texto) in SCRIPTS {
        let arq = pasta.join(nome);
        std::fs::write(&arq, texto).map_err(|e| Erro::io(&arq, e))?;
    }
    Ok(pasta)
}

/// Roda uma tarefa no worker e devolve o resultado (JSON do script).
pub async fn rodar(paths: &Paths, w: Worker, inst: &Instalacao, tarefa: &Value, tempo: Duration) -> Resultado<Value> {
    let scripts = preparar_scripts(&paths.data_dir)?;
    let tmp = paths.data_dir.join("tmp");
    std::fs::create_dir_all(&tmp).map_err(|e| Erro::io(&tmp, e))?;
    let id = crate::util::id_aleatorio(6);
    let arq_tarefa = tmp.join(format!("worker_{id}.json"));
    let arq_resultado = tmp.join(format!("worker_{id}.resultado.json"));
    std::fs::write(&arq_tarefa, serde_json::to_vec_pretty(tarefa).unwrap_or_default()).map_err(|e| Erro::io(&arq_tarefa, e))?;
    let script = scripts.join(w.script()).to_string_lossy().into_owned();
    let t_s = arq_tarefa.to_string_lossy().into_owned();
    let r_s = arq_resultado.to_string_lossy().into_owned();
    let repo = inst.repo.to_string_lossy().into_owned();
    let hf = pasta(paths, w).join("hf").to_string_lossy().into_owned();
    let mut env: Vec<(&str, &str)> = vec![("PYTHONPATH", repo.as_str()), ("PYTHONIOENCODING", "utf-8"), ("PYTHONUTF8", "1")];
    if std::env::var_os("HF_HOME").is_none() {
        env.push(("HF_HOME", hf.as_str()));
    }
    let saida = externas::rodar_com_env(&inst.python, &[&script, &t_s, &r_s], tempo, Some(&inst.repo), &env).await?;
    let _ = std::fs::remove_file(&arq_tarefa);
    let resultado: Option<Value> = std::fs::read(&arq_resultado).ok().and_then(|b| serde_json::from_slice(&b).ok());
    let _ = std::fs::remove_file(&arq_resultado);
    if saida.tempo_esgotado {
        return Err(Erro::novo("worker_demorou", format!("O {} passou do tempo-limite ({} s).", w.nome(), tempo.as_secs())));
    }
    match resultado {
        Some(r) if r["ok"] == Value::Bool(true) => {
            let proibidos: Vec<&str> =
                r["proibidos_carregados"].as_array().map(|a| a.iter().filter_map(|x| x.as_str()).collect()).unwrap_or_default();
            if !proibidos.is_empty() {
                return Err(Erro::novo(
                    "worker_usou_proibido",
                    format!("O {} carregou {} (licença só de pesquisa): o resultado foi descartado.", w.nome(), proibidos.join(", ")),
                ));
            }
            Ok(r)
        }
        Some(r) => {
            Err(Erro::novo("worker_falhou", format!("O {} não conseguiu: {}", w.nome(), r["erro"].as_str().unwrap_or("erro desconhecido"))))
        }
        None => {
            Err(Erro::novo("worker_falhou", format!("O {} parou sem resultado. Final da saída:\n{}", w.nome(), saida.final_da_saida(12))))
        }
    }
}

/// Confere a instalação com uma geração de teste. No TRELLIS.2, comprova que o
/// nvdiffrast não foi usado: só então o modelo entra em projeto comercial.
pub async fn verificar(paths: &Paths, w: Worker) -> Resultado<Value> {
    let mut inst = instalacao(paths, w).ok_or_else(|| Erro::novo("worker_nao_instalado", format!("O {} não está instalado.", w.nome())))?;
    let pasta_v = pasta(paths, w).join("verificacao");
    std::fs::create_dir_all(&pasta_v).map_err(|e| Erro::io(&pasta_v, e))?;
    let r = match w {
        Worker::Trellis2 => {
            let saida = pasta_v.join("verificacao.ply");
            rodar(paths, w, &inst, &json!({"tarefa": "verificar", "saida": saida, "seed": 1}), Duration::from_secs(1800)).await?
        }
        Worker::UniRig | Worker::HyMotion => {
            let codigo = "import torch, json; print(json.dumps({'cuda': torch.cuda.is_available()}))";
            let s = externas::rodar(&inst.python, &["-c", codigo], Duration::from_secs(300), Some(&inst.repo)).await?;
            let v: Value = s.stdout.lines().rev().find_map(|l| serde_json::from_str(l).ok()).unwrap_or(Value::Null);
            if v["cuda"] != true {
                return Err(Erro::novo(
                    "worker_sem_cuda",
                    format!("O {} não achou a placa NVIDIA (CUDA): {}", w.nome(), s.final_da_saida(6)),
                ));
            }
            json!({"ok": true, "cuda": true})
        }
    };
    inst.sem = if r["sem_nvdiffrast"] == true { vec!["nvdiffrast".into()] } else { vec![] };
    inst.verificado_em = Some(crate::util::agora_iso());
    guardar(&inst)?;
    Ok(json!({"worker": w.id(), "verificado": true, "sem": inst.sem, "resultado": r}))
}

/// Python do sistema (3.10 ou mais novo) para criar os ambientes dos workers.
pub async fn python_do_sistema() -> Option<PathBuf> {
    let nomes: &[&str] = if cfg!(windows) { &["python.exe", "python3.exe"] } else { &["python3", "python"] };
    let caminhos: Vec<PathBuf> = std::env::var_os("PATH").map(|p| std::env::split_paths(&p).collect()).unwrap_or_default();
    for dir in caminhos {
        for n in nomes {
            let c = dir.join(n);
            if !c.is_file() {
                continue;
            }
            let codigo = "import sys; print(sys.version_info[0] * 100 + sys.version_info[1])";
            if let Ok(s) = externas::rodar(&c, &["-c", codigo], Duration::from_secs(20), None).await {
                if s.stdout.trim().parse::<u32>().is_ok_and(|v| v >= 310) {
                    return Some(c);
                }
            }
        }
    }
    None
}

async fn comando_de_instalacao(paths: &Paths, w: Worker, pular_pesos: bool) -> Resultado<(tokio::process::Command, PathBuf)> {
    let python = python_do_sistema().await.ok_or_else(|| {
        Erro::novo("python_ausente", "Precisa do Python 3.10 ou mais novo instalado (python.org) para criar o ambiente do modelo.")
    })?;
    let scripts = preparar_scripts(&paths.data_dir)?;
    let destino = pasta(paths, w);
    std::fs::create_dir_all(&destino).map_err(|e| Erro::io(&destino, e))?;
    let mut cmd = tokio::process::Command::new(&python);
    cmd.arg(scripts.join("instalar.py")).arg(w.id()).arg(&destino);
    if pular_pesos {
        cmd.arg("--pular-pesos");
    }
    Ok((cmd, destino))
}

/// Instala aqui mesmo, mostrando o progresso no terminal, e verifica no fim (linha de comando).
pub async fn instalar_e_esperar(paths: &Paths, w: Worker, pular_pesos: bool) -> Resultado<Value> {
    let (mut cmd, _) = comando_de_instalacao(paths, w, pular_pesos).await?;
    let ok = cmd.status().await.map(|s| s.success()).unwrap_or(false);
    if !ok {
        return Err(Erro::novo(
            "instalacao_falhou",
            format!("A instalação do {} falhou: veja o instalacao.log na pasta do modelo.", w.nome()),
        ));
    }
    verificar(paths, w).await
}

/// Começa a instalação em segundo plano (download de vários GB). O progresso fica
/// em `<pasta>/instalacao.log`; quando termina, a Fornalha verifica sozinha.
pub async fn instalar(paths: &Paths, w: Worker, pular_pesos: bool) -> Resultado<Value> {
    let (mut cmd, destino) = comando_de_instalacao(paths, w, pular_pesos).await?;
    cmd.stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    let mut filho = cmd.spawn().map_err(|e| Erro::novo("instalacao_falhou", format!("Não consegui abrir o instalador: {e}")))?;
    std::fs::write(destino.join("instalando"), crate::util::agora_iso()).ok();
    let paths2 = paths.clone();
    tokio::spawn(async move {
        let ok = filho.wait().await.map(|s| s.success()).unwrap_or(false);
        let _ = std::fs::remove_file(pasta(&paths2, w).join("instalando"));
        if ok {
            let _ = verificar(&paths2, w).await;
        }
    });
    Ok(json!({"worker": w.id(), "iniciado": true, "log": destino.join("instalacao.log")}))
}

fn final_do_log(arq: &Path, linhas: usize) -> Vec<String> {
    let texto = std::fs::read_to_string(arq).unwrap_or_default();
    let todas: Vec<&str> = texto.lines().filter(|l| l.starts_with('[')).collect();
    todas[todas.len().saturating_sub(linhas)..].iter().map(|s| s.to_string()).collect()
}

/// Situação de cada worker, para a janela e o get_status.
pub fn estado(paths: &Paths) -> Value {
    let lista: Vec<Value> = Worker::TODOS
        .into_iter()
        .map(|w| {
            let inst = instalacao(paths, w);
            let p = pasta(paths, w);
            json!({
                "id": w.id(),
                "nome": w.nome(),
                "instalado": inst.is_some(),
                "verificado": inst.as_ref().is_some_and(|i| i.verificado_em.is_some()),
                "sem": inst.as_ref().map(|i| i.sem.clone()).unwrap_or_default(),
                "instalando": p.join("instalando").is_file(),
                "aceite": w.aceite(),
                "log": final_do_log(&p.join("instalacao.log"), 6),
            })
        })
        .collect();
    json!(lista)
}
