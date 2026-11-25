//! Do zero até o jogo rodando: projeto, personagem, inimigo e mundo na Forja
//! (Blender), código e cenas na engine (Godot ou Erethea) e o run_test.
//! Precisa do Blender e da Godot (o CI instala os dois); sem eles, pula.

mod comum;

use std::time::Duration;

use fornalha_core::engine::{self, OpcoesTeste};
use fornalha_core::externas::{self, Programa};
use fornalha_core::forja;
use fornalha_core::projeto::{self, NovoProjeto};
use serde_json::{json, Value};

#[test]
fn erros_da_engine_sao_reconhecidos() {
    let saida = "Godot Engine v4.6.1\nSCRIPT ERROR: Parse Error: Identifier not declared\nERROR: Failed to load script\nALSA lib pcm.c: ERROR: Unknown PCM\nWARNING: algo\nERROR: Failed to load script\n";
    let e = engine::erros_da_saida(saida);
    assert_eq!(e.len(), 2, "{e:?}");
    assert!(e[0].starts_with("SCRIPT ERROR"));
}

#[test]
fn erros_coloridos_da_engine_tambem_sao_pegos() {
    // A Godot põe códigos de cor (ANSI) antes do ERROR: mesmo com a saída num arquivo.
    let saida = "\u{1b}[1;31mSCRIPT ERROR: Parse Error: Cannot infer the type\u{1b}[0m\n\u{1b}[0;91m   at: GDScript::reload\n\u{1b}[1;31mERROR:\u{1b}[0;91m Failed to load script\u{1b}[0m\n";
    let e = engine::erros_da_saida(saida);
    assert_eq!(e.len(), 2, "{e:?}");
    assert!(e[0].starts_with("SCRIPT ERROR"), "{e:?}");
}

#[test]
fn preparar_projeto_escreve_scripts_e_respeita_edicoes() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&NovoProjeto { nome: "Teste Engine".into(), ..Default::default() }, tmp.path()).unwrap();
    let r = engine::preparar_projeto(&p, "4.8.beta4").unwrap();
    let pg = std::fs::read_to_string(p.raiz.join("project.godot")).unwrap();
    assert!(pg.contains("config/name=\"Teste Engine\""));
    assert!(pg.contains("\"4.8\""), "versão da engine nos recursos");
    assert!(pg.contains("TesteFornalha=") && pg.contains("fornalha_ponte/plugin.cfg"));
    assert!(r.escritos.iter().any(|e| e.ends_with("jogador.gd")));
    assert!(r.escritos.iter().any(|e| e.ends_with("movimento.gd")), "o movimento (árvore, IK e olhar) vai junto");
    assert!(p.raiz.join("blender/.gdignore").is_file());
    // a pessoa edita o jogador: a Fornalha não sobrescreve
    let jog = p.raiz.join("Scripts/fornalha/jogador.gd");
    std::fs::write(&jog, "extends CharacterBody3D\n# meu jeito\n").unwrap();
    let r = engine::preparar_projeto(&p, "4.6.1.stable").unwrap();
    assert!(r.mantidos.iter().any(|m| m.ends_with("jogador.gd")), "{r:?}");
    assert!(std::fs::read_to_string(&jog).unwrap().contains("meu jeito"));
}

#[tokio::test]
async fn do_zero_ao_jogo_rodando_na_engine() {
    let (Some(blender), Some(godot)) = (externas::achar_para_teste(Programa::Blender).await, achar_engine().await) else {
        eprintln!("Blender ou Godot/Erethea não encontrados: teste pulado");
        return;
    };
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&NovoProjeto { nome: "Reino de Cinzas".into(), ..Default::default() }, tmp.path()).unwrap();
    let raiz = p.raiz.clone();
    let t = Duration::from_secs(600);
    // Forja: herói, inimigo e mundo
    for (saida, pers) in [
        ("Characters/aren/aren.glb", json!({"id": "aren", "tipo": "humano", "arma": "machado", "capa": true})),
        ("Enemies/orc/orc.glb", json!({"id": "orc", "tipo": "orc", "arma": "martelo", "cor_roupa": "#4a3b2a"})),
    ] {
        let arq = raiz.join(saida);
        let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "personagem", "saida": arq, "previa": false, "personagem": pers}), t)
            .await
            .unwrap();
        std::fs::write(arq.with_extension("forja.json"), serde_json::to_vec(&r).unwrap()).unwrap();
    }
    forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "mundo", "saida": raiz.join("World/blockout.glb"), "previa": false,
                "mundo": {"seed": 2, "areas": [{"id": "vila", "tipo": "vila"}, {"id": "floresta", "tipo": "floresta"}, {"id": "arena", "tipo": "arena"}]}}),
        t,
    )
    .await
    .unwrap();
    // engine: código, cenas e teste
    engine::preparar_projeto(&p, godot.versao.as_deref().unwrap_or("")).unwrap();
    let m = engine::escrever_manifesto(&raiz, None, true).unwrap();
    assert_eq!(m["jogador"], "aren");
    assert_eq!(m["inimigos"], json!(["orc"]));
    let montado = engine::montar(&godot, &raiz).await.unwrap();
    let cenas: Vec<&str> = montado["cenas"].as_array().unwrap().iter().map(|c| c.as_str().unwrap()).collect();
    assert!(cenas.contains(&"res://principal.tscn"), "{montado}");
    assert!(cenas.contains(&"res://Characters/aren/aren.tscn"));
    assert!(raiz.join("principal.tscn").is_file());
    let tem_tela = std::env::var_os("DISPLAY").is_some() || cfg!(windows);
    let op = OpcoesTeste {
        segundos: 9.0,
        sem_janela: !tem_tela,
        // FORNALHA_TESTE_COM_PLACA=1: roda com a placa (Forward+), não no modo de compatibilidade
        sem_placa: std::env::var_os("FORNALHA_TESTE_COM_PLACA").is_none(),
        video: tem_tela && std::env::var_os("FORNALHA_TESTE_VIDEO").is_some(),
    };
    let pasta = std::env::var_os("FORNALHA_TESTE_SAIDA").map(std::path::PathBuf::from).unwrap_or_else(|| tmp.path().join("teste"));
    let rel = engine::testar(&godot, &raiz, &pasta, &op).await.unwrap();
    eprintln!("relatório do run_test: {}", serde_json::to_string_pretty(&rel).unwrap());
    assert_eq!(rel["erros"], json!([]), "a engine não pode dar erro");
    assert!(rel["jogador"]["andou_m"].as_f64().unwrap() > 3.0, "o jogador andou: {}", rel["jogador"]);
    assert_eq!(rel["jogador"]["caiu_do_mapa"], false);
    assert!(rel["inimigos"]["total"].as_u64().unwrap() >= 2);
    assert!(rel["inimigos"]["perseguiram"].as_u64().unwrap() >= 1, "o inimigo perto viu o jogador");
    let total = rel["inimigos"]["total"].as_u64().unwrap();
    assert!(rel["inimigos"]["vivos"].as_u64().unwrap() < total, "o jogador derrotou o inimigo que chegou perto: {}", rel["inimigos"]);
    assert!(rel["assets"].as_array().unwrap().iter().any(|a| a["arquivo"] == "World/blockout.glb"));
    comum::conferir_movimento(&rel);
    if tem_tela && !rel["modo"].as_str().unwrap_or("").starts_with("sem janela") {
        assert!(!rel["capturas"].as_array().unwrap().is_empty(), "capturas do jogo");
    }
    assert_eq!(rel["passou"], Value::Bool(true));
}

async fn achar_engine() -> Option<externas::Achado> {
    match externas::achar_para_teste(Programa::Erethea).await {
        Some(e) => Some(e),
        None => externas::achar_para_teste(Programa::Godot).await,
    }
}

#[tokio::test]
async fn scripts_do_jogo_compilam_na_engine() {
    let Some(godot) = achar_engine().await else {
        eprintln!("Godot/Erethea não encontrada: teste pulado");
        return;
    };
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&NovoProjeto { nome: "Compila".into(), ..Default::default() }, tmp.path()).unwrap();
    engine::preparar_projeto(&p, godot.versao.as_deref().unwrap_or("")).unwrap();
    let raiz = p.raiz.to_string_lossy().into_owned();
    for s in ["jogador", "inimigo", "movimento", "hud", "sons", "teste_automatico", "principal", "montar"] {
        let script = format!("res://Scripts/fornalha/{s}.gd");
        let saida = externas::rodar(
            &godot.caminho,
            &["--headless", "--path", &raiz, "--check-only", "--script", &script],
            Duration::from_secs(120),
            None,
        )
        .await
        .unwrap();
        let erros = engine::erros_da_saida(&format!("{}\n{}", saida.stdout, saida.stderr));
        assert!(erros.is_empty(), "{s}.gd não compila: {erros:?}");
    }
}

/// Pedido da Erethea: o run_test chama `--agent-test=<pasta>` e lê `<pasta>/report.json`, e roda junto o
/// teste_automatico da Fornalha (o jogador anda, o inimigo reage); saída 2 (opções desconhecidas) fica só
/// com o da Fornalha.
#[cfg(unix)]
#[tokio::test]
async fn erethea_usa_o_teste_de_agente_dela() {
    use std::os::unix::fs::PermissionsExt;
    let tmp = tempfile::tempdir().unwrap();
    let raiz = tmp.path().join("jogo");
    std::fs::create_dir_all(&raiz).unwrap();
    let falsa = tmp.path().join("erethea");
    std::fs::write(
        &falsa,
        "#!/bin/sh\nf=\nfor a in \"$@\"; do [ \"$f\" = 1 ] && { mkdir -p \"$a\"; printf '{\"jogador\": {\"andou_m\": 5, \"caiu_do_mapa\": false}}' > \"$a/relatorio.json\"; exit 0; }\n\
         case \"$a\" in --fornalha-teste) f=1;; --agent-test=*) d=\"${a#--agent-test=}\";; --agent-test-seconds=*) s=\"${a#--agent-test-seconds=}\";; esac; done\n\
         [ -z \"$d\" ] && exit 2\nmkdir -p \"$d\"\nprintf '{\"passou\": true, \"segundos\": %s, \"quadros\": 240}' \"$s\" > \"$d/report.json\"\nexit 0\n",
    )
    .unwrap();
    std::fs::set_permissions(&falsa, std::fs::Permissions::from_mode(0o755)).unwrap();
    let eng = externas::Achado { programa: Programa::Erethea, caminho: falsa.clone(), versao: Some("4.8-erethea".into()) };
    let op = OpcoesTeste { segundos: 4.0, sem_janela: true, ..Default::default() };
    let rel = engine::testar(&eng, &raiz, &tmp.path().join("saida"), &op).await.unwrap();
    assert_eq!(rel["teste"], "fornalha + erethea --agent-test");
    assert_eq!(rel["passou"], true, "{rel}");
    assert_eq!(rel["jogador"]["andou_m"], 5, "o teste da Fornalha também rodou: {rel}");
    assert_eq!(rel["erethea"]["quadros"], 240);
    assert_eq!(rel["erethea"]["segundos"], 4);
    // Erethea antiga (sai com 2): a Fornalha tenta o teste dela (que aqui não roda, pois a "engine" é falsa)
    std::fs::write(&falsa, "#!/bin/sh\nexit 2\n").unwrap();
    let e = engine::testar(&eng, &raiz, &tmp.path().join("saida2"), &op).await.unwrap_err();
    assert_eq!(e.codigo, "jogo_nao_rodou");
}
