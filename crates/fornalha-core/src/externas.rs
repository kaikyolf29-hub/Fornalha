//! Programas de fora que a Fornalha comanda pela linha de comando:
//! Blender (limpeza, rig, animação, exportação, mundo), Godot e Erethea Engine
//! (importar, montar as cenas e testar o jogo).
//!
//! A Erethea é o fork da Godot 4.8 do criador: abre os mesmos projetos, por isso
//! a Fornalha gera um projeto só e abre na engine escolhida na bíblia.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Serialize;

use crate::erro::{Erro, Resultado};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Programa {
    Blender,
    Godot,
    Erethea,
}

impl Programa {
    pub fn nome(&self) -> &'static str {
        match self {
            Programa::Blender => "Blender",
            Programa::Godot => "Godot",
            Programa::Erethea => "Erethea Engine",
        }
    }

    pub fn id(&self) -> &'static str {
        match self {
            Programa::Blender => "blender",
            Programa::Godot => "godot",
            Programa::Erethea => "erethea",
        }
    }

    /// A engine da bíblia ("godot" ou "erethea").
    pub fn from_engine(e: &str) -> Option<Self> {
        match e.trim().to_lowercase().as_str() {
            "godot" => Some(Programa::Godot),
            "erethea" | "erethea engine" | "erethea-engine" => Some(Programa::Erethea),
            _ => None,
        }
    }

    pub fn variavel(&self) -> &'static str {
        match self {
            Programa::Blender => "FORNALHA_BLENDER",
            Programa::Godot => "FORNALHA_GODOT",
            Programa::Erethea => "FORNALHA_ERETHEA",
        }
    }

    pub fn pagina_download(&self) -> &'static str {
        match self {
            Programa::Blender => "https://www.blender.org/download/",
            Programa::Godot => "https://godotengine.org/download/",
            Programa::Erethea => "https://github.com/kaikyolf29-hub/-Erethea-Engine/releases",
        }
    }
}

/// O que se sabe da máquina para procurar os programas (separado para testar).
#[derive(Debug, Clone, Default)]
pub struct Ambiente {
    pub windows: bool,
    /// Caminho escolhido pela pessoa nas configurações.
    pub escolhido: Option<PathBuf>,
    /// Caminho da variável FORNALHA_BLENDER / FORNALHA_GODOT / FORNALHA_ERETHEA.
    pub variavel: Option<PathBuf>,
    pub program_files: Option<PathBuf>,
    pub program_files_x86: Option<PathBuf>,
    pub local_app_data: Option<PathBuf>,
    pub home: Option<PathBuf>,
    /// Pasta onde a Fornalha guarda as ferramentas dela.
    pub pasta_fornalha: PathBuf,
    pub path: Vec<PathBuf>,
}

impl Ambiente {
    pub fn do_sistema(programa: Programa, escolhido: Option<PathBuf>, pasta_fornalha: PathBuf) -> Self {
        let env = |n: &str| std::env::var_os(n).map(PathBuf::from);
        Self {
            windows: cfg!(windows),
            escolhido,
            variavel: env(programa.variavel()),
            program_files: env("ProgramFiles"),
            program_files_x86: env("ProgramFiles(x86)"),
            local_app_data: env("LOCALAPPDATA"),
            home: dirs::home_dir(),
            pasta_fornalha,
            path: std::env::var_os("PATH").map(|p| std::env::split_paths(&p).collect()).unwrap_or_default(),
        }
    }
}

const VERSOES_BLENDER: [&str; 10] = ["5.4", "5.3", "5.2", "5.1", "5.0", "4.5", "4.4", "4.3", "4.2", "4.1"];

/// Lugares onde procurar, do mais provável para o menos (só monta a lista, não olha o disco).
pub fn candidatos(programa: Programa, a: &Ambiente) -> Vec<PathBuf> {
    let mut c: Vec<PathBuf> = Vec::new();
    c.extend(a.escolhido.clone());
    c.extend(a.variavel.clone());
    let exe = |n: &str| if a.windows { format!("{n}.exe") } else { n.to_string() };
    match programa {
        Programa::Blender => {
            c.push(a.pasta_fornalha.join("blender").join(exe("blender")));
            if a.windows {
                if let Some(pf) = &a.program_files {
                    for v in VERSOES_BLENDER {
                        c.push(pf.join("Blender Foundation").join(format!("Blender {v}")).join("blender.exe"));
                    }
                }
                for pf in [&a.program_files_x86, &a.program_files].into_iter().flatten() {
                    c.push(pf.join("Steam").join("steamapps").join("common").join("Blender").join("blender.exe"));
                }
            } else {
                for d in &a.path {
                    c.push(d.join("blender"));
                }
                c.push(PathBuf::from("/snap/bin/blender"));
                if let Some(h) = &a.home {
                    c.push(h.join(".local/share/Steam/steamapps/common/Blender/blender"));
                }
            }
        }
        Programa::Godot => {
            c.push(a.pasta_fornalha.join("godot").join(exe("godot_console")));
            c.push(a.pasta_fornalha.join("godot").join(exe("godot")));
            if a.windows {
                for pf in [&a.program_files_x86, &a.program_files].into_iter().flatten() {
                    let steam = pf.join("Steam").join("steamapps").join("common").join("Godot Engine");
                    c.push(steam.join("godot.windows.opt.tools.64.exe"));
                }
                if let Some(l) = &a.local_app_data {
                    c.push(l.join("Godot").join("godot.exe"));
                }
                for d in &a.path {
                    c.push(d.join("godot.exe"));
                }
            } else {
                for d in &a.path {
                    c.push(d.join("godot"));
                    c.push(d.join("godot4"));
                }
                if let Some(h) = &a.home {
                    c.push(h.join(".local/share/Steam/steamapps/common/Godot Engine/godot.x11.opt.tools.64"));
                }
            }
        }
        Programa::Erethea => {
            if a.windows {
                if let Some(l) = &a.local_app_data {
                    c.push(l.join("Erethea").join("erethea.console.exe"));
                    c.push(l.join("Erethea").join("erethea.exe"));
                }
                for d in &a.path {
                    c.push(d.join("erethea.console.exe"));
                    c.push(d.join("erethea.exe"));
                }
            } else {
                for d in &a.path {
                    c.push(d.join("erethea"));
                }
                if let Some(h) = &a.home {
                    c.push(h.join(".local/share/erethea/erethea"));
                }
            }
            c.push(a.pasta_fornalha.join("erethea").join(exe("erethea")));
        }
    }
    let mut vistos = std::collections::HashSet::new();
    c.retain(|p| vistos.insert(p.clone()));
    c
}

/// Pastas onde a versão vem no nome (Godot portátil baixado, Blender de versão nova):
/// olha o disco e devolve executáveis achados.
fn procurar_no_disco(programa: Programa, a: &Ambiente) -> Vec<PathBuf> {
    let mut achados = Vec::new();
    let mut olhar = |dir: &Path, filtro: &dyn Fn(&str) -> bool| {
        if let Ok(rd) = std::fs::read_dir(dir) {
            let mut v: Vec<PathBuf> =
                rd.flatten().map(|e| e.path()).filter(|p| p.file_name().and_then(|n| n.to_str()).is_some_and(filtro)).collect();
            v.sort();
            v.reverse(); // versão mais nova primeiro
            achados.extend(v);
        }
    };
    match programa {
        Programa::Blender => {
            if let Some(pf) = &a.program_files {
                let base = pf.join("Blender Foundation");
                if let Ok(rd) = std::fs::read_dir(&base) {
                    let mut v: Vec<PathBuf> = rd.flatten().map(|e| e.path().join("blender.exe")).collect();
                    v.sort();
                    v.reverse();
                    achados.extend(v);
                }
            }
            if let Ok(rd) = std::fs::read_dir(&a.pasta_fornalha) {
                for e in rd.flatten().filter(|e| e.file_name().to_string_lossy().starts_with("blender")) {
                    achados.push(e.path().join(if a.windows { "blender.exe" } else { "blender" }));
                }
            }
        }
        Programa::Godot => {
            let eh_godot = |n: &str| {
                let n = n.to_lowercase();
                n.starts_with("godot_v4") && (n.ends_with(".exe") || n.ends_with(".x86_64")) && !n.contains("mono")
            };
            // console primeiro no Windows (mostra a saída)
            let console = |n: &str| eh_godot(n) && (!n.ends_with(".exe") || n.contains("console"));
            for d in [
                Some(a.pasta_fornalha.join("godot")),
                a.home.as_ref().map(|h| h.join("Downloads")),
                a.home.as_ref().map(|h| h.join("Desktop")),
            ]
            .into_iter()
            .flatten()
            {
                olhar(&d, &console);
                olhar(&d, &eh_godot);
            }
            for d in &a.path {
                olhar(d, &eh_godot);
            }
        }
        Programa::Erethea => {
            let eh = |n: &str| n.to_lowercase().starts_with("erethea") && !n.ends_with(".pck");
            olhar(&a.pasta_fornalha.join("erethea"), &eh);
        }
    }
    achados
}

/// "Blender 5.2.4 LTS" → "5.2.4 LTS"; "4.6.1.stable.official.x" → "4.6.1.stable".
pub fn ler_versao(programa: Programa, saida: &str) -> Option<String> {
    match programa {
        Programa::Blender => saida
            .lines()
            .find_map(|l| l.trim().strip_prefix("Blender "))
            .map(|v| v.trim().to_string())
            .filter(|v| v.starts_with(char::is_numeric)),
        Programa::Godot | Programa::Erethea => {
            for linha in saida.lines() {
                for palavra in linha.split_whitespace() {
                    let p = palavra.trim_start_matches('v');
                    let partes: Vec<&str> = p.split('.').collect();
                    if partes.len() >= 2 && partes[0].chars().all(|c| c.is_ascii_digit()) && !partes[0].is_empty() {
                        let mut v: Vec<&str> = Vec::new();
                        for parte in &partes {
                            v.push(parte);
                            if !parte.chars().all(|c| c.is_ascii_digit()) {
                                break;
                            }
                        }
                        if v.len() >= 2 {
                            return Some(v.join("."));
                        }
                    }
                }
            }
            None
        }
    }
}

/// "4.6.1.stable" → "4.6" (vai em config/features do project.godot).
pub fn recurso_da_engine(versao: &str) -> String {
    let p: Vec<&str> = versao.split('.').take(2).collect();
    if p.len() == 2 && p.iter().all(|x| !x.is_empty() && x.chars().all(|c| c.is_ascii_digit())) {
        p.join(".")
    } else {
        "4.6".into()
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Achado {
    pub programa: Programa,
    pub caminho: PathBuf,
    pub versao: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Saida {
    pub codigo: Option<i32>,
    pub stdout: String,
    pub stderr: String,
    pub segundos: f64,
    pub tempo_esgotado: bool,
}

impl Saida {
    pub fn ok(&self) -> bool {
        self.codigo == Some(0) && !self.tempo_esgotado
    }
    /// Últimas linhas da saída, para mensagens de erro.
    pub fn final_da_saida(&self, n: usize) -> String {
        let tudo = format!("{}\n{}", self.stdout, self.stderr);
        let linhas: Vec<&str> = tudo.lines().filter(|l| !l.trim().is_empty()).collect();
        linhas[linhas.len().saturating_sub(n)..].join("\n")
    }
}

/// Roda um programa com tempo-limite, sem abrir janela de console no Windows.
pub async fn rodar(caminho: &Path, args: &[&str], tempo: Duration, pasta: Option<&Path>) -> Resultado<Saida> {
    rodar_com_env(caminho, args, tempo, pasta, &[]).await
}

pub async fn rodar_com_env(caminho: &Path, args: &[&str], tempo: Duration, pasta: Option<&Path>, env: &[(&str, &str)]) -> Resultado<Saida> {
    let mut cmd = tokio::process::Command::new(caminho);
    cmd.args(args)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);
    for (k, v) in env {
        cmd.env(k, v);
    }
    if let Some(p) = pasta {
        cmd.current_dir(p);
    }
    crate::util::hide_console(&mut cmd);
    let inicio = std::time::Instant::now();
    let filho = cmd.spawn().map_err(|e| Erro::novo("programa_nao_abriu", format!("Não consegui abrir {}: {e}", caminho.display())))?;
    match tokio::time::timeout(tempo, filho.wait_with_output()).await {
        Ok(Ok(out)) => Ok(Saida {
            codigo: out.status.code(),
            stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
            segundos: inicio.elapsed().as_secs_f64(),
            tempo_esgotado: false,
        }),
        Ok(Err(e)) => Err(Erro::novo("programa_falhou", format!("{} falhou: {e}", caminho.display()))),
        Err(_) => Ok(Saida {
            codigo: None,
            stdout: String::new(),
            stderr: format!("passou do tempo-limite de {} s", tempo.as_secs()),
            segundos: inicio.elapsed().as_secs_f64(),
            tempo_esgotado: true,
        }),
    }
}

/// Procura o programa: candidatos em ordem, o primeiro que existe e responde a `--version`.
pub async fn achar_no(programa: Programa, a: &Ambiente) -> Option<Achado> {
    let mut lista = candidatos(programa, a);
    lista.extend(procurar_no_disco(programa, a));
    for caminho in lista {
        if !caminho.is_file() {
            continue;
        }
        let versao = match rodar(&caminho, &["--version"], Duration::from_secs(60), None).await {
            Ok(s) => ler_versao(programa, &format!("{}\n{}", s.stdout, s.stderr)),
            Err(_) => continue,
        };
        return Some(Achado { programa, caminho, versao });
    }
    None
}

/// Para os testes: usa FORNALHA_TESTE_<PROGRAMA> ou procura no sistema.
pub async fn achar_para_teste(programa: Programa) -> Option<Achado> {
    let var = format!("FORNALHA_TESTE_{}", programa.id().to_uppercase());
    let escolhido = std::env::var_os(&var).map(PathBuf::from);
    let a = Ambiente::do_sistema(programa, escolhido, std::env::temp_dir().join("fornalha-sem-ferramentas"));
    achar_no(programa, &a).await
}
