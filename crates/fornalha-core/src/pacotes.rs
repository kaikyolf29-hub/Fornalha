//! Pacotes de conteúdo CC0 que sobem a qualidade das gerações:
//! - MakeHuman: malha base, formas, esqueleto de jogo, pele, olhos e cabelo (humanos realistas);
//! - Animações: Quaternius Universal Animation Library 1 e 2 (captura de movimento limpa);
//! - Materiais: texturas PBR e céus HDRI do ambientCG (aço, cota de malha, couro, tecido, pedra...);
//! - ACCAD (CC BY 3.0) e 100STYLE (CC BY 4.0): capturas de movimento para o banco de movimento
//!   (luta, passos, carregar; 100 estilos de andar), com crédito obrigatório.
//!
//! Só baixam quando a pessoa pede (janela ou `fornalha-cli baixar-pacote`), por um
//! script à parte: o núcleo da Fornalha continua falando só com 127.0.0.1.
//! `FORNALHA_PACOTE_<ID>` aponta uma pasta já pronta (testes e CI).

use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::paths::Paths;
use crate::workers;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Pacote {
    MakeHuman,
    Animacoes,
    Materiais,
    Accad,
    Estilos100,
}

impl Pacote {
    pub const TODOS: [Pacote; 5] = [Pacote::MakeHuman, Pacote::Animacoes, Pacote::Materiais, Pacote::Accad, Pacote::Estilos100];

    pub fn id(self) -> &'static str {
        match self {
            Pacote::MakeHuman => "makehuman",
            Pacote::Animacoes => "animacoes",
            Pacote::Materiais => "materiais",
            Pacote::Accad => "accad",
            Pacote::Estilos100 => "100style",
        }
    }

    pub fn nome(self) -> &'static str {
        match self {
            Pacote::MakeHuman => "Humanos realistas (MakeHuman, CC0)",
            Pacote::Animacoes => "Animações de captura (Quaternius, CC0)",
            Pacote::Materiais => "Materiais PBR e céus (ambientCG, CC0)",
            Pacote::Accad => "Capturas de luta e passos (ACCAD, CC BY 3.0)",
            Pacote::Estilos100 => "100 estilos de andar e correr (100STYLE, CC BY 4.0)",
        }
    }

    pub fn tamanho(self) -> &'static str {
        match self {
            Pacote::MakeHuman => "~330 MB",
            Pacote::Animacoes => "~25 MB",
            Pacote::Materiais => "~110 MB",
            Pacote::Accad => "~20 MB",
            Pacote::Estilos100 => "~1,5 GB",
        }
    }

    pub fn de_id(id: &str) -> Option<Self> {
        Self::TODOS.into_iter().find(|p| p.id() == id)
    }

    fn variavel(self) -> String {
        format!("FORNALHA_PACOTE_{}", self.id().to_uppercase())
    }
}

pub fn pasta(paths: &Paths, p: Pacote) -> PathBuf {
    std::env::var_os(p.variavel()).map(PathBuf::from).unwrap_or_else(|| paths.data_dir.join("pacotes").join(p.id()))
}

/// O `pacote.json` do pacote instalado.
pub fn info(paths: &Paths, p: Pacote) -> Option<Value> {
    let v: Value = serde_json::from_slice(&std::fs::read(pasta(paths, p).join("pacote.json")).ok()?).ok()?;
    let existe = |k: &str| v[k].as_str().is_none_or(|c| Path::new(c).exists());
    match p {
        Pacote::MakeHuman if !(existe("dados") && existe("assets")) => None,
        Pacote::Materiais if !existe("materiais") => None,
        _ => Some(v),
    }
}

/// O que a Forja recebe para fazer humanos realistas (só com o pacote MakeHuman).
pub fn para_a_forja(paths: &Paths) -> Option<Value> {
    let mh = info(paths, Pacote::MakeHuman)?;
    let mut t = json!({"makehuman": {"dados": mh["dados"], "assets": mh["assets"]}});
    if let Some(a) = info(paths, Pacote::Animacoes) {
        t["animacoes_de"] = a["bibliotecas"].clone();
    }
    if let Some(m) = info(paths, Pacote::Materiais) {
        t["materiais"] = m["materiais"].clone();
        t["ceu"] = m["ceu"].clone();
    }
    Some(t)
}

/// Materiais PBR e céu para qualquer tarefa da Forja (armas, objetos, mundo).
pub fn materiais_da_forja(paths: &Paths) -> Option<Value> {
    let m = info(paths, Pacote::Materiais)?;
    Some(json!({"materiais": m["materiais"], "ceu": m["ceu"]}))
}

fn final_do_log(arq: &Path) -> Vec<String> {
    let texto = std::fs::read_to_string(arq).unwrap_or_default();
    let linhas: Vec<&str> = texto.lines().collect();
    linhas[linhas.len().saturating_sub(4)..].iter().map(|s| s.to_string()).collect()
}

pub fn estado(paths: &Paths) -> Value {
    json!(Pacote::TODOS
        .into_iter()
        .map(|p| {
            let dir = pasta(paths, p);
            json!({"id": p.id(), "nome": p.nome(), "tamanho": p.tamanho(), "instalado": info(paths, p).is_some(),
                   "baixando": dir.join("baixando").is_file(), "log": final_do_log(&dir.join("pacote.log"))})
        })
        .collect::<Vec<_>>())
}

async fn comando(paths: &Paths, p: Pacote) -> Resultado<(tokio::process::Command, PathBuf)> {
    let python = workers::python_para(paths).await.ok_or_else(|| {
        Erro::novo(
            "python_ausente",
            "Para baixar os pacotes precisa do Python 3.10+ (python.org) ou do Blender baixado em Máquina → Programas (ele traz um Python).",
        )
    })?;
    let scripts = workers::preparar_scripts(&paths.data_dir)?;
    let destino = paths.data_dir.join("pacotes").join(p.id());
    std::fs::create_dir_all(&destino).map_err(|e| Erro::io(&destino, e))?;
    let mut cmd = tokio::process::Command::new(python);
    cmd.arg(scripts.join("pacotes.py")).arg(p.id()).arg(&destino);
    Ok((cmd, destino))
}

/// Baixa em segundo plano (pela janela). O andamento fica em `pacote.log`.
pub async fn baixar(paths: &Paths, p: Pacote) -> Resultado<Value> {
    let (mut cmd, destino) = comando(paths, p).await?;
    cmd.stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        cmd.creation_flags(0x0800_0000);
    }
    let mut filho = cmd.spawn().map_err(|e| Erro::novo("pacote_falhou", format!("Não consegui começar o download: {e}")))?;
    std::fs::write(destino.join("baixando"), crate::util::agora_iso()).ok();
    let marca = destino.join("baixando");
    tokio::spawn(async move {
        let _ = filho.wait().await;
        let _ = std::fs::remove_file(marca);
    });
    Ok(json!({"pacote": p.id(), "iniciado": true}))
}

/// Baixa aqui mesmo, mostrando o andamento (linha de comando).
pub async fn baixar_e_esperar(paths: &Paths, p: Pacote) -> Resultado<Value> {
    let (mut cmd, _) = comando(paths, p).await?;
    let ok = cmd.status().await.map(|s| s.success()).unwrap_or(false);
    if !ok {
        return Err(Erro::novo("pacote_falhou", format!("O download de {} falhou: veja o pacote.log.", p.nome())));
    }
    info(paths, p).ok_or_else(|| Erro::novo("pacote_falhou", "O pacote terminou incompleto."))
}
