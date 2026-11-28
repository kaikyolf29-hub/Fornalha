//! Baixar o Blender, a Godot e a Erethea para a pasta da Fornalha, só quando a pessoa clica (Máquina →
//! Programas → Baixar) ou pede pela linha de comando. Versões fixas, conferidas pela soma publicada
//! pelo próprio projeto (Blender: SHA-256 de download.blender.org; Godot: SHA-512 de SHA512-SUMS.txt;
//! Erethea: SHA-256 do "digest" do instalador na release do GitHub). A Erethea vem como instalador do
//! Windows (sem perguntas, na pasta da Fornalha); no Linux ainda não há build público.
//!
//! O núcleo continua sem HTTPS de saída: o download é o `curl` do sistema (no Windows 10/11 o de
//! System32) e a extração é o `tar` do sistema (no Windows o bsdtar de System32, que abre zip). Os
//! programas ficam em `<dados>/ferramentas/blender` e `<dados>/ferramentas/godot`, onde a detecção
//! já procura primeiro. Blender é GPL e Godot é MIT: rodam como programas separados.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::{json, Value};
use sha2::Digest;

use crate::erro::{Erro, Resultado};
use crate::externas::Programa;
use crate::paths::Paths;

/// Soma publicada pelo projeto para o arquivo.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Soma {
    Sha256(&'static str),
    Sha512(&'static str),
}

/// Um download fixo de um programa.
#[derive(Debug, Clone, PartialEq)]
pub struct Download {
    pub programa: Programa,
    pub versao: &'static str,
    pub url: &'static str,
    /// espelhos oficiais com o mesmo arquivo (a soma é conferida igual), tentados se o principal recusar
    pub espelhos: &'static [&'static str],
    pub arquivo: &'static str,
    pub soma: Soma,
    /// tamanho aproximado, para a janela
    pub tamanho: &'static str,
}

pub const BLENDER_VERSAO: &str = "5.3.0";
pub const GODOT_VERSAO: &str = "4.6.1";
pub const ERETHEA_VERSAO: &str = "1.0.3";

/// O download do programa para o sistema (a Erethea só no Windows: é o build público que existe).
pub fn download(programa: Programa, windows: bool) -> Option<Download> {
    let d = match (programa, windows) {
        (Programa::Blender, true) => Download {
            programa,
            versao: BLENDER_VERSAO,
            url: "https://download.blender.org/release/Blender5.3/blender-5.3.0-windows-x64.zip",
            espelhos: &[
                "https://mirrors.ocf.berkeley.edu/blender/release/Blender5.3/blender-5.3.0-windows-x64.zip",
                "https://ftp.nluug.nl/pub/graphics/blender/release/Blender5.3/blender-5.3.0-windows-x64.zip",
            ],
            arquivo: "blender-5.3.0-windows-x64.zip",
            soma: Soma::Sha256("3ac567a63d59d9934f7b9213bfb27ba05760e1fb366f8f55c381573ec3eabfa8"),
            tamanho: "≈ 430 MB",
        },
        (Programa::Blender, false) => Download {
            programa,
            versao: BLENDER_VERSAO,
            url: "https://download.blender.org/release/Blender5.3/blender-5.3.0-linux-x64.tar.xz",
            espelhos: &[
                "https://mirrors.ocf.berkeley.edu/blender/release/Blender5.3/blender-5.3.0-linux-x64.tar.xz",
                "https://ftp.nluug.nl/pub/graphics/blender/release/Blender5.3/blender-5.3.0-linux-x64.tar.xz",
            ],
            arquivo: "blender-5.3.0-linux-x64.tar.xz",
            soma: Soma::Sha256("dacb8264197a3f7fda6001285a5a506fc97ee943881261c2c3bd63c882f22e05"),
            tamanho: "≈ 410 MB",
        },
        (Programa::Godot, true) => Download {
            programa,
            versao: GODOT_VERSAO,
            url: "https://github.com/godotengine/godot/releases/download/4.6.1-stable/Godot_v4.6.1-stable_win64.exe.zip",
            espelhos: &[],
            arquivo: "Godot_v4.6.1-stable_win64.exe.zip",
            soma: Soma::Sha512(
                "67c63291115c66ebe7145415b5aac235e1667e417d6cd3d1975848670a1d31cbfad111c8231cb53195bb62e6e4fde951d97aaca227736a94f93dcbf8f23b1fbb",
            ),
            tamanho: "≈ 70 MB",
        },
        (Programa::Godot, false) => Download {
            programa,
            versao: GODOT_VERSAO,
            url: "https://github.com/godotengine/godot/releases/download/4.6.1-stable/Godot_v4.6.1-stable_linux.x86_64.zip",
            espelhos: &[],
            arquivo: "Godot_v4.6.1-stable_linux.x86_64.zip",
            soma: Soma::Sha512(
                "a76fd0fe1d44a2dd6c065b6f7b434ad75f5593c07bda3d3017f8304f2d069acbcf0f39cb5d0976f0434b56e9ea852032ddbcbdb7e0ce1c75a47e1dacb6794bd7",
            ),
            tamanho: "≈ 70 MB",
        },
        // 1.0.3 (28/11/2026): corrige o cabelo fio a fio e o mapa de normais no renderizador de compatibilidade
        // (o pedido 7); SHA-256 do HANDOFF da Erethea, conferido no arquivo baixado e no CI pela release
        (Programa::Erethea, true) => Download {
            programa,
            versao: ERETHEA_VERSAO,
            url: "https://github.com/kaikyolf29-hub/-Erethea-Engine/releases/download/v1.0.3/erethea-setup-x86_64.exe",
            espelhos: &[],
            arquivo: "erethea-setup-x86_64.exe",
            soma: Soma::Sha256("7d93e40822fc3d125a6316cbfce4ecedc129cabff8236e1aaf1e146067b12d11"),
            tamanho: "≈ 100 MB",
        },
        (Programa::Erethea, false) => return None,
    };
    Some(d)
}

/// Pasta onde a Fornalha guarda os programas que baixou (a mesma que a detecção olha primeiro).
pub fn pasta(paths: &Paths) -> PathBuf {
    paths.data_dir.join("ferramentas")
}

fn marca(paths: &Paths, p: Programa) -> PathBuf {
    pasta(paths).join(format!("{}.baixando", p.id()))
}

fn log(paths: &Paths, p: Programa) -> PathBuf {
    pasta(paths).join(format!("{}.log", p.id()))
}

/// Situação dos downloads, para a janela: baixando (com MB já recebidos) e a última linha do registro.
pub fn estado(paths: &Paths) -> Value {
    let mut m = serde_json::Map::new();
    for p in [Programa::Blender, Programa::Godot, Programa::Erethea] {
        let Some(d) = download(p, cfg!(windows)) else { continue };
        let parte = pasta(paths).join(format!("{}.parte", d.arquivo));
        let mb = std::fs::metadata(&parte).map(|m| m.len() / (1024 * 1024)).unwrap_or(0);
        let ultima = std::fs::read_to_string(log(paths, p)).ok().and_then(|t| t.lines().last().map(String::from));
        m.insert(
            p.id().into(),
            json!({"baixando": marca(paths, p).is_file(), "mb": mb, "versao": d.versao, "tamanho": d.tamanho, "ultima": ultima}),
        );
    }
    Value::Object(m)
}

/// Programa do sistema: no Windows o de System32 (o `tar` do Git não abre zip), nos outros pelo PATH.
fn do_sistema(nome: &str) -> PathBuf {
    if cfg!(windows) {
        let raiz = std::env::var_os("SystemRoot").map(PathBuf::from).unwrap_or_else(|| PathBuf::from(r"C:\Windows"));
        let c = raiz.join("System32").join(format!("{nome}.exe"));
        if c.is_file() {
            return c;
        }
    }
    PathBuf::from(nome)
}

fn registrar(paths: &Paths, p: Programa, texto: &str) {
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(log(paths, p)) {
        let _ = writeln!(f, "[{}] {texto}", crate::util::agora_iso());
    }
}

/// Confere a soma do arquivo.
pub fn conferir(arquivo: &Path, soma: Soma) -> Resultado<()> {
    use std::io::Read;
    let mut f = std::fs::File::open(arquivo).map_err(|e| Erro::io(arquivo, e))?;
    let mut buf = vec![0u8; 1 << 20];
    let (calculada, esperada) = match soma {
        Soma::Sha256(h) => {
            let mut s = sha2::Sha256::new();
            loop {
                let n = f.read(&mut buf).map_err(|e| Erro::io(arquivo, e))?;
                if n == 0 {
                    break;
                }
                s.update(&buf[..n]);
            }
            (hex(&s.finalize()), h)
        }
        Soma::Sha512(h) => {
            let mut s = sha2::Sha512::new();
            loop {
                let n = f.read(&mut buf).map_err(|e| Erro::io(arquivo, e))?;
                if n == 0 {
                    break;
                }
                s.update(&buf[..n]);
            }
            (hex(&s.finalize()), h)
        }
    };
    if calculada != esperada {
        return Err(Erro::novo(
            "download_corrompido",
            format!("O arquivo baixado não confere com a soma publicada ({}…). Tente de novo.", &calculada[..16]),
        ));
    }
    Ok(())
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// Onde fica o executável depois de instalado.
pub fn executavel(paths: &Paths, p: Programa) -> PathBuf {
    let exe = |n: &str| if cfg!(windows) { format!("{n}.exe") } else { n.to_string() };
    match p {
        Programa::Blender => pasta(paths).join("blender").join(exe("blender")),
        Programa::Godot if cfg!(windows) => pasta(paths).join("godot").join("godot_console.exe"),
        Programa::Erethea if cfg!(windows) => pasta(paths).join("erethea").join("erethea.console.exe"),
        _ => pasta(paths).join(p.id()).join(p.id()),
    }
}

/// Baixa, confere, extrai e põe no lugar. Devolve o executável. Demora (centenas de MB).
pub async fn baixar_e_esperar(paths: &Paths, p: Programa) -> Resultado<PathBuf> {
    let d = download(p, cfg!(windows)).ok_or_else(|| Erro::novo("sem_download", format!("O {} não é baixado pela Fornalha.", p.nome())))?;
    let base = pasta(paths);
    std::fs::create_dir_all(&base).map_err(|e| Erro::io(&base, e))?;
    std::fs::write(marca(paths, p), crate::util::agora_iso()).ok();
    let r = instalar(paths, &d, &base).await;
    let _ = std::fs::remove_file(marca(paths, p));
    match &r {
        Ok(exe) => registrar(paths, p, &format!("pronto: {}", exe.display())),
        Err(e) => registrar(paths, p, &format!("ERRO: {}", e.mensagem)),
    }
    r
}

async fn instalar(paths: &Paths, d: &Download, base: &Path) -> Resultado<PathBuf> {
    let p = d.programa;
    let parte = base.join(format!("{}.parte", d.arquivo));
    let _ = std::fs::remove_file(&parte);
    registrar(paths, p, &format!("baixando {} {} ({})", p.nome(), d.versao, d.tamanho));
    let parte_s = parte.to_string_lossy().into_owned();
    let curl = do_sistema("curl");
    // o site principal às vezes recusa (403) máquinas de nuvem: tenta os espelhos oficiais em sequência
    let mut falhas = Vec::new();
    for url in std::iter::once(d.url).chain(d.espelhos.iter().copied()) {
        let _ = std::fs::remove_file(&parte);
        let s = crate::externas::rodar(
            &curl,
            &["-fsSL", "--retry", "3", "--retry-delay", "5", "-o", &parte_s, url],
            Duration::from_secs(60 * 60),
            Some(base),
        )
        .await
        .map_err(|e| Erro::novo("download_falhou", format!("Não consegui rodar o curl para baixar o {}: {}", p.nome(), e.mensagem)))?;
        if s.ok() && parte.is_file() {
            falhas.clear();
            break;
        }
        registrar(paths, p, &format!("falhou em {url}; tentando o próximo endereço"));
        falhas.push(format!("{}: {}", url, s.final_da_saida(2)));
    }
    if !falhas.is_empty() || !parte.is_file() {
        return Err(Erro::novo("download_falhou", format!("O download do {} falhou: {}", p.nome(), falhas.join(" | "))));
    }
    registrar(paths, p, "conferindo a soma publicada");
    if let Err(e) = conferir(&parte, d.soma) {
        let _ = std::fs::remove_file(&parte);
        return Err(e);
    }
    // com o nome de verdade (a extensão diz zip ou tar.xz); extrai numa pasta nova e só troca no fim
    // (a versão antiga continua funcionando até lá)
    let arquivo = base.join(d.arquivo);
    std::fs::rename(&parte, &arquivo).map_err(|e| Erro::io(&arquivo, e))?;
    if p == Programa::Erethea {
        return instalar_erethea(paths, d, base, &arquivo).await;
    }
    let novo = base.join(format!("{}.novo", p.id()));
    let _ = std::fs::remove_dir_all(&novo);
    std::fs::create_dir_all(&novo).map_err(|e| Erro::io(&novo, e))?;
    registrar(paths, p, "extraindo");
    let extraido = extrair(&arquivo, &novo).await;
    let _ = std::fs::remove_file(&arquivo);
    if let Err(e) = extraido {
        let _ = std::fs::remove_dir_all(&novo);
        return Err(e);
    }
    let destino = base.join(p.id());
    match p {
        Programa::Blender => {
            // o arquivo traz uma pasta blender-<versão>-<sistema>
            let interna = std::fs::read_dir(&novo)
                .map_err(|e| Erro::io(&novo, e))?
                .flatten()
                .map(|e| e.path())
                .find(|c| c.is_dir() && c.file_name().is_some_and(|n| n.to_string_lossy().starts_with("blender")))
                .ok_or_else(|| Erro::novo("download_estranho", "O arquivo do Blender não tem a pasta esperada."))?;
            trocar(&interna, &destino)?;
            let _ = std::fs::remove_dir_all(&novo);
        }
        Programa::Godot => {
            let arquivos: Vec<PathBuf> = std::fs::read_dir(&novo).map_err(|e| Erro::io(&novo, e))?.flatten().map(|e| e.path()).collect();
            for a in &arquivos {
                let n = a.file_name().map(|n| n.to_string_lossy().to_lowercase()).unwrap_or_default();
                let alvo = if cfg!(windows) {
                    if n.ends_with("_console.exe") {
                        "godot_console.exe"
                    } else if n.ends_with(".exe") {
                        "godot.exe"
                    } else {
                        continue;
                    }
                } else if n.starts_with("godot_v") {
                    "godot"
                } else {
                    continue;
                };
                std::fs::rename(a, novo.join(alvo)).map_err(|e| Erro::io(a, e))?;
            }
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = std::fs::set_permissions(novo.join("godot"), std::fs::Permissions::from_mode(0o755));
            }
            trocar(&novo, &destino)?;
        }
        Programa::Erethea => {}
    }
    let exe = executavel(paths, p);
    if !exe.is_file() {
        return Err(Erro::novo("download_estranho", format!("Depois de extrair, o {} não apareceu em {}.", p.nome(), exe.display())));
    }
    std::fs::write(
        destino.join("fornalha-download.json"),
        serde_json::to_string_pretty(&json!({"versao": d.versao, "url": d.url, "baixado_em": crate::util::agora_iso()}))
            .unwrap_or_default(),
    )
    .ok();
    Ok(exe)
}

/// A Erethea vem como instalador do Windows (Inno Setup): roda sem perguntas, só para esta pessoa e na
/// pasta da Fornalha (onde a detecção procura). Uma versão antiga ali é atualizada pelo próprio instalador.
async fn instalar_erethea(paths: &Paths, d: &Download, base: &Path, instalador: &Path) -> Resultado<PathBuf> {
    let p = d.programa;
    let destino = base.join(p.id());
    registrar(paths, p, "instalando (sem perguntas, na pasta da Fornalha)");
    let dir = format!("/DIR={}", destino.display());
    let s = crate::externas::rodar(
        instalador,
        &["/VERYSILENT", "/SUPPRESSMSGBOXES", "/CURRENTUSER", "/NORESTART", &dir],
        Duration::from_secs(30 * 60),
        Some(base),
    )
    .await;
    let _ = std::fs::remove_file(instalador);
    let s = s.map_err(|e| Erro::novo("instalacao_falhou", format!("Não consegui abrir o instalador da Erethea: {}", e.mensagem)))?;
    if !s.ok() {
        return Err(Erro::novo("instalacao_falhou", format!("O instalador da Erethea falhou: {}", s.final_da_saida(3))));
    }
    let exe = executavel(paths, p);
    if !exe.is_file() {
        return Err(Erro::novo("download_estranho", format!("Depois de instalar, a Erethea não apareceu em {}.", exe.display())));
    }
    std::fs::write(
        destino.join("fornalha-download.json"),
        serde_json::to_string_pretty(&json!({"versao": d.versao, "url": d.url, "baixado_em": crate::util::agora_iso()}))
            .unwrap_or_default(),
    )
    .ok();
    Ok(exe)
}

fn trocar(de: &Path, para: &Path) -> Resultado<()> {
    if para.exists() {
        std::fs::remove_dir_all(para).map_err(|e| Erro::io(para, e))?;
    }
    std::fs::rename(de, para).map_err(|e| Erro::io(para, e))
}

/// Extrai zip ou tar.xz com o que o sistema tem: no Windows o bsdtar de System32 abre os dois; no
/// Linux o tar abre o .tar.xz e, para zip, unzip, bsdtar ou o zipfile do Python.
async fn extrair(arquivo: &Path, destino: &Path) -> Resultado<()> {
    let a = arquivo.to_string_lossy().into_owned();
    let d = destino.to_string_lossy().into_owned();
    let zip = a.ends_with(".zip");
    let tentativas: Vec<(PathBuf, Vec<String>)> = if cfg!(windows) || !zip {
        vec![(do_sistema("tar"), vec!["-xf".into(), a.clone(), "-C".into(), d.clone()])]
    } else {
        vec![
            (PathBuf::from("unzip"), vec!["-oq".into(), a.clone(), "-d".into(), d.clone()]),
            (PathBuf::from("bsdtar"), vec!["-xf".into(), a.clone(), "-C".into(), d.clone()]),
            (PathBuf::from("python3"), vec!["-I".into(), "-m".into(), "zipfile".into(), "-e".into(), a.clone(), d.clone()]),
        ]
    };
    let mut ultimo = String::new();
    for (prog, args) in tentativas {
        let refs: Vec<&str> = args.iter().map(String::as_str).collect();
        match crate::externas::rodar(&prog, &refs, Duration::from_secs(30 * 60), None).await {
            Ok(s) if s.ok() => return Ok(()),
            Ok(s) => ultimo = s.final_da_saida(5),
            Err(e) => ultimo = e.mensagem,
        }
    }
    Err(Erro::novo("extracao_falhou", format!("Não consegui extrair {}: {ultimo}", arquivo.display())))
}

/// Começa o download em segundo plano (para a janela). O progresso aparece em `estado`.
pub async fn baixar(paths: &Paths, p: Programa) -> Resultado<Value> {
    let d = download(p, cfg!(windows)).ok_or_else(|| Erro::novo("sem_download", format!("O {} não é baixado pela Fornalha.", p.nome())))?;
    if marca(paths, p).is_file() {
        return Ok(json!({"iniciado": false, "ja_baixando": true}));
    }
    let base = pasta(paths);
    std::fs::create_dir_all(&base).map_err(|e| Erro::io(&base, e))?;
    std::fs::write(marca(paths, p), crate::util::agora_iso()).ok();
    let paths = paths.clone();
    tokio::spawn(async move {
        let _ = baixar_e_esperar(&paths, p).await;
    });
    Ok(json!({"iniciado": true, "versao": d.versao, "tamanho": d.tamanho}))
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn downloads_fixos_com_soma() {
        for w in [true, false] {
            for p in [Programa::Blender, Programa::Godot] {
                let d = download(p, w).unwrap();
                for u in std::iter::once(d.url).chain(d.espelhos.iter().copied()) {
                    assert!(u.starts_with("https://") && u.ends_with(d.arquivo), "{d:?}");
                }
                match d.soma {
                    Soma::Sha256(h) => assert_eq!(h.len(), 64),
                    Soma::Sha512(h) => assert_eq!(h.len(), 128),
                }
            }
        }
        // a Erethea: instalador público só para Windows, com o SHA-256 do "digest" da release
        let e = download(Programa::Erethea, true).unwrap();
        assert!(e.url.starts_with("https://github.com/kaikyolf29-hub/-Erethea-Engine/releases/download/v") && e.url.ends_with(e.arquivo));
        assert!(e.url.contains(&format!("/v{}/", e.versao)), "a versão do endereço é a fixada: {e:?}");
        assert!(matches!(e.soma, Soma::Sha256(h) if h.len() == 64 && h.chars().all(|c| c.is_ascii_hexdigit())));
        assert!(download(Programa::Erethea, false).is_none(), "no Linux ainda não há build público");
    }

    #[test]
    fn confere_a_soma() {
        let tmp = tempfile::tempdir().unwrap();
        let a = tmp.path().join("x.bin");
        std::fs::write(&a, b"abc").unwrap();
        conferir(&a, Soma::Sha256("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")).unwrap();
        assert_eq!(
            conferir(&a, Soma::Sha256("0000000000000000000000000000000000000000000000000000000000000000")).unwrap_err().codigo,
            "download_corrompido"
        );
        conferir(
            &a,
            Soma::Sha512(
                "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
            ),
        )
        .unwrap();
    }
}

#[cfg(test)]
mod testes_python {
    #[test]
    fn acha_o_python_dentro_do_blender() {
        let tmp = tempfile::tempdir().unwrap();
        let b = tmp.path().join("blender");
        assert!(crate::workers::python_do_blender(&b).is_none());
        let bin = b.join("5.2").join("python").join("bin");
        std::fs::create_dir_all(&bin).unwrap();
        std::fs::create_dir_all(b.join("lib")).unwrap();
        std::fs::write(bin.join("python3.13-config"), b"").unwrap();
        assert!(crate::workers::python_do_blender(&b).is_none());
        std::fs::write(bin.join("python3.13"), b"").unwrap();
        assert_eq!(crate::workers::python_do_blender(&b), Some(bin.join("python3.13")));
        let b2 = tmp.path().join("blender-win");
        let bin2 = b2.join("5.2").join("python").join("bin");
        std::fs::create_dir_all(&bin2).unwrap();
        std::fs::write(bin2.join("python313.dll"), b"").unwrap();
        assert!(crate::workers::python_do_blender(&b2).is_none(), "dll não é o Python");
        std::fs::write(bin2.join("python.exe"), b"").unwrap();
        assert_eq!(crate::workers::python_do_blender(&b2), Some(bin2.join("python.exe")));
    }
}
