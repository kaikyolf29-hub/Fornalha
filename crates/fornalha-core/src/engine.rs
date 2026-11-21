//! A engine do jogo: Godot ou Erethea Engine (o fork da Godot 4.8 do criador).
//! As duas abrem o mesmo projeto, então a pasta do projeto da Fornalha também é
//! o projeto da engine (`project.godot` ao lado do `game.project.json`).
//!
//! - `preparar_projeto`: project.godot, scripts do jogo (jogador, inimigo, HUD,
//!   sons, teste automático) e a ponte com a engine;
//! - `montar`: importa os assets e monta as cenas dentro da própria engine;
//! - `testar` (run_test): abre o jogo em modo de teste, coleta erros, quadros por
//!   segundo, polígonos e tamanhos, tira capturas e grava um vídeo.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Serialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::externas::{self, Achado};
use crate::projeto::Projeto;

/// Scripts do jogo que a Fornalha escreve em `Scripts/fornalha/`.
/// (caminho no projeto, conteúdo). A ponte é um plugin do editor (vale na Godot e na Erethea).
const SCRIPTS: [(&str, &str); 9] = [
    ("Scripts/fornalha/jogador.gd", include_str!("../godot/jogador.gd")),
    ("Scripts/fornalha/inimigo.gd", include_str!("../godot/inimigo.gd")),
    ("Scripts/fornalha/hud.gd", include_str!("../godot/hud.gd")),
    ("Scripts/fornalha/sons.gd", include_str!("../godot/sons.gd")),
    ("Scripts/fornalha/teste_automatico.gd", include_str!("../godot/teste_automatico.gd")),
    ("Scripts/fornalha/principal.gd", include_str!("../godot/principal.gd")),
    ("Scripts/fornalha/montar.gd", include_str!("../godot/montar.gd")),
    ("addons/fornalha_ponte/plugin.cfg", include_str!("../godot/ponte_plugin.cfg")),
    ("addons/fornalha_ponte/ponte_plugin.gd", include_str!("../godot/ponte_plugin.gd")),
];
pub const PASTA_SCRIPTS: &str = "Scripts/fornalha";
const REGISTRO: &str = ".fornalha/scripts.json";

fn hash(texto: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(&Sha256::digest(texto)[..10])
}

fn escapar(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn project_godot(nome: &str, descricao: &str, recurso: &str) -> String {
    format!(
        r#"; Gerado pela Fornalha. Abre na Godot e na Erethea Engine.
; Pode editar: a Fornalha só acrescenta o que faltar.

config_version=5

[application]

config/name="{nome}"
config/description="{descricao}"
run/main_scene="res://principal.tscn"
config/features=PackedStringArray("{recurso}", "Forward Plus")

[autoload]

TesteFornalha="*res://Scripts/fornalha/teste_automatico.gd"
Sons="*res://Scripts/fornalha/sons.gd"

[editor_plugins]

enabled=PackedStringArray("res://addons/fornalha_ponte/plugin.cfg")

[display]

window/size/viewport_width=1280
window/size/viewport_height=720

[layer_names]

3d_physics/layer_1="mundo"
3d_physics/layer_2="jogador"
3d_physics/layer_3="inimigos"

[rendering]

renderer/rendering_method="forward_plus"
anti_aliasing/quality/msaa_3d=1
"#,
        nome = escapar(nome),
        descricao = escapar(descricao),
        recurso = recurso
    )
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct Preparo {
    pub escritos: Vec<String>,
    /// Scripts que a pessoa editou e a Fornalha não sobrescreveu.
    pub mantidos: Vec<String>,
}

/// Escreve project.godot (se faltar), os scripts do jogo e os .gdignore.
pub fn preparar_projeto(projeto: &Projeto, versao_engine: &str) -> Resultado<Preparo> {
    let raiz = &projeto.raiz;
    let mut preparo = Preparo::default();
    let escrever = |rel: &str, conteudo: &[u8]| -> Resultado<()> {
        let arq = raiz.join(rel);
        if let Some(p) = arq.parent() {
            std::fs::create_dir_all(p).map_err(|e| Erro::io(p, e))?;
        }
        std::fs::write(&arq, conteudo).map_err(|e| Erro::io(&arq, e))
    };
    let pg = raiz.join("project.godot");
    if !pg.is_file() {
        let b = &projeto.biblia;
        let descricao = [b.conceito.genero.as_str(), b.conceito.camera.as_str()]
            .iter()
            .filter(|s| !s.is_empty())
            .cloned()
            .collect::<Vec<_>>()
            .join(", ");
        escrever("project.godot", project_godot(&b.nome, &descricao, &externas::recurso_da_engine(versao_engine)).as_bytes())?;
        preparo.escritos.push("project.godot".into());
    } else {
        // acrescenta os autoloads que faltarem, sem mexer no resto
        let mut texto = std::fs::read_to_string(&pg).map_err(|e| Erro::io(&pg, e))?;
        let mut mudou = false;
        for (nome, script) in [("TesteFornalha", "teste_automatico.gd"), ("Sons", "sons.gd")] {
            if !texto.contains(&format!("{nome}=")) {
                let linha = format!("{nome}=\"*res://{PASTA_SCRIPTS}/{script}\"\n");
                if let Some(i) = texto.find("[autoload]\n") {
                    texto.insert_str(i + "[autoload]\n".len(), &format!("\n{linha}"));
                } else {
                    texto.push_str(&format!("\n[autoload]\n\n{linha}"));
                }
                mudou = true;
            }
        }
        if mudou {
            escrever("project.godot", texto.as_bytes())?;
            preparo.escritos.push("project.godot (autoloads)".into());
        }
    }
    // Pastas que a engine não deve importar (arquivos de trabalho e da Fornalha).
    for pasta in ["blender", "ai", "GameDesign", ".fornalha"] {
        let arq = format!("{pasta}/.gdignore");
        if !raiz.join(&arq).is_file() {
            escrever(&arq, b"")?;
        }
    }
    // Scripts: sobrescreve só os que a pessoa não editou.
    let reg_arq = raiz.join(REGISTRO);
    let mut registro: BTreeMap<String, String> =
        std::fs::read(&reg_arq).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default();
    for (rel, conteudo) in SCRIPTS {
        let rel = rel.to_string();
        let arq = raiz.join(&rel);
        if arq.is_file() {
            let atual = std::fs::read(&arq).unwrap_or_default();
            let editado = registro.get(&rel).is_none_or(|h| *h != hash(&atual));
            if hash(&atual) == hash(conteudo.as_bytes()) {
                continue;
            }
            if editado {
                preparo.mantidos.push(rel);
                continue;
            }
        }
        escrever(&rel, conteudo.as_bytes())?;
        registro.insert(rel.clone(), hash(conteudo.as_bytes()));
        preparo.escritos.push(rel);
    }
    escrever(REGISTRO, &serde_json::to_vec_pretty(&registro).unwrap_or_default())?;
    Ok(preparo)
}

/// Um personagem ou inimigo pronto para a engine (glb com esqueleto da Forja).
#[derive(Debug, Clone, Serialize)]
pub struct Personagem {
    pub id: String,
    /// "jogador" ou "inimigo".
    pub tipo: String,
    pub modelo: String,
    pub altura: f64,
}

fn res(raiz: &Path, arq: &Path) -> String {
    let rel = arq.strip_prefix(raiz).unwrap_or(arq);
    format!("res://{}", rel.to_string_lossy().replace('\\', "/"))
}

/// Procura os modelos prontos: Characters/<id>/<id>.glb e Enemies/<id>/<id>.glb.
pub fn achar_personagens(raiz: &Path) -> Vec<Personagem> {
    let mut lista = Vec::new();
    for (pasta, tipo) in [("Characters", "jogador"), ("Enemies", "inimigo")] {
        let Ok(rd) = std::fs::read_dir(raiz.join(pasta)) else { continue };
        let mut dirs: Vec<PathBuf> = rd.flatten().map(|e| e.path()).filter(|p| p.is_dir()).collect();
        dirs.sort();
        for d in dirs {
            let id = d.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            let glb = d.join(format!("{id}.glb"));
            if glb.is_file() {
                let altura = std::fs::read(d.join(format!("{id}.forja.json")))
                    .ok()
                    .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
                    .and_then(|v| v["estatisticas"]["altura_m"].as_f64())
                    .unwrap_or(1.8);
                lista.push(Personagem { id, tipo: tipo.into(), modelo: res(raiz, &glb), altura });
            }
        }
    }
    lista
}

/// Escreve res://.fornalha/cena.json com o que a engine deve montar.
pub fn escrever_manifesto(raiz: &Path, jogador: Option<&str>, inimigo_perto: bool) -> Resultado<Value> {
    let personagens = achar_personagens(raiz);
    let jogador =
        jogador.map(String::from).or_else(|| personagens.iter().find(|p| p.tipo == "jogador").map(|p| p.id.clone())).unwrap_or_default();
    let inimigos: Vec<String> = personagens.iter().filter(|p| p.tipo == "inimigo").map(|p| p.id.clone()).collect();
    let mundo_glb = raiz.join("World/blockout.glb");
    let info: Value =
        std::fs::read(raiz.join("World/blockout.info.json")).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(json!({}));
    let musica = ["exploracao", "vila", "floresta", "combate"]
        .iter()
        .map(|n| raiz.join(format!("Audio/musica/{n}.wav")))
        .find(|p| p.is_file())
        .map(|p| res(raiz, &p))
        .unwrap_or_default();
    let m = json!({
        "personagens": personagens.iter().map(|p| json!({
            "id": p.id, "tipo": p.tipo, "modelo": p.modelo, "altura": p.altura,
            "cena": p.modelo.trim_end_matches(".glb").to_string() + ".tscn",
        })).collect::<Vec<_>>(),
        "jogador": jogador,
        "inimigos": inimigos,
        "inimigo_perto": inimigo_perto,
        "mundo": if mundo_glb.is_file() { json!({"modelo": res(raiz, &mundo_glb), "cena": "res://World/mundo.tscn"}) } else { json!({}) },
        "spawn_jogador": info.get("spawn_jogador").cloned().unwrap_or(json!([0.0, 0.2, 0.0])),
        "spawn_inimigos": info.get("spawn_inimigos").cloned().unwrap_or(json!([])),
        "musica": musica,
        "principal": "res://principal.tscn",
    });
    let arq = raiz.join(".fornalha/cena.json");
    crate::paths::write_json(&arq, &m).map_err(|e| Erro::io(&arq, e))?;
    Ok(m)
}

/// Tira os códigos de cor (ANSI) que a engine põe na saída.
fn sem_cores(l: &str) -> String {
    let mut out = String::with_capacity(l.len());
    let mut it = l.chars().peekable();
    while let Some(c) = it.next() {
        if c == '\u{1b}' {
            if it.peek() == Some(&'[') {
                it.next();
                for d in it.by_ref() {
                    if d.is_ascii_alphabetic() {
                        break;
                    }
                }
            }
            continue;
        }
        out.push(c);
    }
    out
}

/// Linhas de erro da saída da engine (o que importa para o agente consertar).
pub fn erros_da_saida(texto: &str) -> Vec<String> {
    let mut v: Vec<String> = Vec::new();
    for l in texto.lines() {
        let limpa = sem_cores(l);
        let t = limpa.trim();
        let erro = t.starts_with("ERROR:") || t.starts_with("SCRIPT ERROR:") || t.starts_with("USER ERROR:") || t.contains("Parse Error:");
        // Avisos conhecidos de máquina sem placa/som não são do jogo.
        let ruido = t.contains("ALSA")
            || t.contains("PulseAudio")
            || t.contains("vkCreateInstance")
            || t.contains("Your video card drivers seem not to support");
        if erro && !ruido && !v.iter().any(|x| x == t) {
            v.push(t.to_string());
        }
    }
    v
}

/// Triângulos e tamanho de um glb (lendo só o JSON de dentro dele).
pub fn estatisticas_glb(arq: &Path) -> Option<(u64, u64)> {
    let b = std::fs::read(arq).ok()?;
    if b.len() < 20 || &b[0..4] != b"glTF" {
        return None;
    }
    let n = u32::from_le_bytes(b[12..16].try_into().ok()?) as usize;
    let g: Value = serde_json::from_slice(b.get(20..20 + n)?).ok()?;
    let acessores = g["accessors"].as_array()?;
    let mut tris = 0u64;
    for malha in g["meshes"].as_array().into_iter().flatten() {
        for prim in malha["primitives"].as_array().into_iter().flatten() {
            let modo = prim["mode"].as_u64().unwrap_or(4);
            if modo != 4 {
                continue;
            }
            let qtd = match prim["indices"].as_u64() {
                Some(i) => acessores.get(i as usize).and_then(|a| a["count"].as_u64()).unwrap_or(0),
                None => prim["attributes"]["POSITION"]
                    .as_u64()
                    .and_then(|i| acessores.get(i as usize))
                    .and_then(|a| a["count"].as_u64())
                    .unwrap_or(0),
            };
            tris += qtd / 3;
        }
    }
    Some((tris, b.len() as u64))
}

fn caminho_str(p: &Path) -> String {
    p.to_string_lossy().into_owned()
}

/// Importa os assets e monta as cenas dentro da engine (sem janela).
pub async fn montar(engine: &Achado, raiz: &Path) -> Resultado<Value> {
    let r = caminho_str(raiz);
    let imp = externas::rodar(&engine.caminho, &["--headless", "--path", &r, "--import"], Duration::from_secs(600), None).await?;
    let mut erros = erros_da_saida(&format!("{}\n{}", imp.stdout, imp.stderr));
    let script = format!("res://{PASTA_SCRIPTS}/montar.gd");
    let mon = externas::rodar(&engine.caminho, &["--headless", "--path", &r, "--script", &script], Duration::from_secs(300), None).await?;
    let saida = format!("{}\n{}", mon.stdout, mon.stderr);
    erros.extend(erros_da_saida(&saida));
    let resultado = saida
        .lines()
        .find_map(|l| l.trim().strip_prefix("FORNALHA_MONTAR ").map(String::from))
        .and_then(|j| serde_json::from_str::<Value>(&j).ok());
    let Some(resultado) = resultado else {
        return Err(Erro::novo("engine_falhou", format!("A engine não montou as cenas. Final da saída:\n{}", mon.final_da_saida(15))));
    };
    if resultado["ok"] != Value::Bool(true) {
        return Err(Erro::novo("engine_falhou", format!("A engine montou com erros: {}", resultado["erros"])));
    }
    Ok(json!({"cenas": resultado["cenas"], "erros_da_engine": erros, "importar_segundos": imp.segundos, "montar_segundos": mon.segundos}))
}

#[derive(Debug, Clone, Default)]
pub struct OpcoesTeste {
    pub segundos: f64,
    /// Sem janela (CI sem tela): sem capturas nem vídeo.
    pub sem_janela: bool,
    /// Máquina sem placa de vídeo: usa o renderizador de compatibilidade (OpenGL).
    pub sem_placa: bool,
    pub video: bool,
}

/// run_test: abre o jogo em modo de teste e devolve o relatório. Se a janela
/// não abrir (máquina sem placa nem OpenGL), roda de novo sem janela.
pub async fn testar(engine: &Achado, raiz: &Path, pasta_saida: &Path, op: &OpcoesTeste) -> Resultado<Value> {
    match testar_uma_vez(engine, raiz, pasta_saida, op).await {
        Err(e) if e.codigo == "jogo_nao_rodou" && !op.sem_janela => {
            let sem = OpcoesTeste { sem_janela: true, video: false, ..op.clone() };
            let mut rel = testar_uma_vez(engine, raiz, pasta_saida, &sem).await?;
            rel["modo"] = json!("sem janela (a janela da engine não abriu nesta máquina)");
            rel["aviso_janela"] = json!(e.mensagem);
            Ok(rel)
        }
        outro => outro,
    }
}

async fn testar_uma_vez(engine: &Achado, raiz: &Path, pasta_saida: &Path, op: &OpcoesTeste) -> Resultado<Value> {
    std::fs::create_dir_all(pasta_saida).map_err(|e| Erro::io(pasta_saida, e))?;
    let _ = std::fs::remove_file(pasta_saida.join("relatorio.json"));
    let r = caminho_str(raiz);
    let saida_s = caminho_str(pasta_saida);
    let segundos = if op.segundos > 0.0 { op.segundos } else { 9.0 };
    let seg_s = format!("{segundos}");
    let video = pasta_saida.join("jogo.avi");
    let video_s = caminho_str(&video);
    let mut args: Vec<&str> = vec!["--path", &r];
    if op.sem_janela {
        args.push("--headless");
    } else {
        args.extend(["--resolution", "960x540", "--audio-driver", "Dummy"]);
        if op.sem_placa {
            args.extend(["--rendering-driver", "opengl3", "--rendering-method", "gl_compatibility"]);
        }
        if op.video {
            args.extend(["--write-movie", &video_s, "--fixed-fps", "30"]);
        }
    }
    args.extend(["res://principal.tscn", "--", "--fornalha-teste", &saida_s, "--segundos", &seg_s]);
    let tempo = Duration::from_secs_f64(segundos * 12.0 + 120.0);
    let s = externas::rodar(&engine.caminho, &args, tempo, None).await?;
    let texto = format!("{}\n{}", s.stdout, s.stderr);
    let erros = erros_da_saida(&texto);
    let rel: Option<Value> = std::fs::read(pasta_saida.join("relatorio.json")).ok().and_then(|b| serde_json::from_slice(&b).ok());
    let Some(mut rel) = rel else {
        return Err(Erro::novo(
            "jogo_nao_rodou",
            format!(
                "O jogo não terminou o teste{}. Final da saída:\n{}",
                if s.tempo_esgotado { " (tempo esgotado)" } else { "" },
                s.final_da_saida(20)
            ),
        ));
    };
    let mut assets = Vec::new();
    for p in walk_glb(raiz) {
        if let Some((tris, bytes)) = estatisticas_glb(&p) {
            assets.push(json!({"arquivo": p.strip_prefix(raiz).unwrap_or(&p).to_string_lossy().replace('\\', "/"), "triangulos": tris, "bytes": bytes}));
        }
    }
    rel["erros"] = json!(erros);
    rel["assets"] = json!(assets);
    rel["video"] = if video.is_file() { json!(caminho_str(&video)) } else { Value::Null };
    rel["modo"] = json!(if op.sem_janela {
        "sem janela"
    } else if op.sem_placa {
        "compatibilidade (sem placa)"
    } else {
        "normal"
    });
    rel["engine_caminho"] = json!(caminho_str(&engine.caminho));
    rel["engine_versao"] = json!(engine.versao);
    rel["passou"] = json!(erros.is_empty() && rel["jogador"]["caiu_do_mapa"] != Value::Bool(true));
    Ok(rel)
}

fn walk_glb(raiz: &Path) -> Vec<PathBuf> {
    let mut v = Vec::new();
    for pasta in ["Characters", "Enemies", "Weapons", "Items", "World"] {
        let mut pilha = vec![raiz.join(pasta)];
        while let Some(d) = pilha.pop() {
            let Ok(rd) = std::fs::read_dir(&d) else { continue };
            for e in rd.flatten() {
                let p = e.path();
                if p.is_dir() {
                    pilha.push(p);
                } else if p.extension().is_some_and(|x| x == "glb") {
                    v.push(p);
                }
            }
        }
    }
    v.sort();
    v
}
