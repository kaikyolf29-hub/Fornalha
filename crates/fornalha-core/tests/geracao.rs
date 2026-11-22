//! As gerações pelo MCP, como o Claude Code chama: personagem, inimigo novo
//! testado na engine (o pronto da Fase 4), mundo, efeitos, música, código,
//! recibos de tudo e o relatório de créditos.
//! Precisa do Blender e da Godot/Erethea (FORNALHA_TESTE_BLENDER / _GODOT / _ERETHEA
//! ou instalados); o Ignis é opcional (FORNALHA_TESTE_IGNIS=<porta>).

mod comum;

use std::sync::Arc;

use fornalha_core::externas::{self, Programa};
use fornalha_core::mcp::{ServidorMcp, Sessao};
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};

async fn fornalha_com_ferramentas(dir: &std::path::Path) -> Option<Arc<Fornalha>> {
    let blender = externas::achar_para_teste(Programa::Blender).await?;
    let engine = match externas::achar_para_teste(Programa::Erethea).await {
        Some(e) => (Programa::Erethea, e),
        None => (Programa::Godot, externas::achar_para_teste(Programa::Godot).await?),
    };
    let f = Fornalha::para_testes(Paths::under(dir), comum::detection("sem-placa"));
    f.definir_programa(Programa::Blender, Some(blender.caminho)).await.unwrap();
    f.definir_programa(engine.0, Some(engine.1.caminho)).await.unwrap();
    if let Some(p) = std::env::var("FORNALHA_TESTE_IGNIS").ok().and_then(|p| p.parse().ok()) {
        f.definir_porta_ignis(p).unwrap();
    }
    Some(f)
}

async fn chamar(s: &ServidorMcp, sessao: &mut Sessao, id: u64, nome: &str, args: Value) -> Value {
    let r = s
        .tratar(json!({"jsonrpc": "2.0", "id": id, "method": "tools/call", "params": {"name": nome, "arguments": args}}), sessao)
        .await
        .unwrap();
    let res = &r["result"];
    assert_eq!(res["isError"], false, "{nome} falhou: {}", res["content"][0]["text"]);
    res["structuredContent"].clone()
}

#[tokio::test]
async fn crie_um_inimigo_novo_vira_inimigo_testado_na_engine() {
    let tmp = tempfile::tempdir().unwrap();
    let Some(f) = fornalha_com_ferramentas(tmp.path()).await else {
        eprintln!("Blender ou engine não encontrados: teste pulado");
        return;
    };
    let s = ServidorMcp::new(f.clone());
    let mut sessao = Sessao::default();
    s.tratar(json!({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude-code", "version": "teste"}}}), &mut sessao).await;

    let p = chamar(
        &s,
        &mut sessao,
        1,
        "create_project",
        json!({"nome": "Reino de Cinzas", "genero": "action RPG", "camera": "terceira pessoa"}),
    )
    .await;
    let raiz = std::path::PathBuf::from(p["raiz"].as_str().unwrap());
    chamar(&s, &mut sessao, 2, "update_project", json!({"alteracoes": {"guia_visual": {"paleta": ["#5b7a3a", "#7a2e22", "#2f3640"], "texto_de_estilo": "low poly, cores quentes"},
        "mundo": {"areas": [{"id": "vila", "nome": "Vila de Brasa", "tipo": "vila"}, {"id": "floresta", "nome": "Mata Escura", "tipo": "floresta"}, {"id": "arena", "nome": "Arena", "tipo": "arena"}]}}})).await;

    // o herói
    let heroi = chamar(
        &s,
        &mut sessao,
        3,
        "create_character",
        json!({"nome": "Aren", "papel": "protagonista", "descricao": "ferreiro com machado", "arma": "machado", "conceito": true}),
    )
    .await;
    assert!(raiz.join("Characters/aren/aren.glb").is_file(), "{heroi}");
    assert!(heroi["arquivos"]["folha"].as_str().is_some());

    // mundo, efeitos e música
    let mundo = chamar(&s, &mut sessao, 4, "generate_blockout", json!({})).await;
    assert_eq!(mundo["estatisticas"]["areas"], 3);
    let sfx = chamar(&s, &mut sessao, 5, "generate_sfx", json!({})).await;
    assert!(sfx["arquivos"].as_array().unwrap().len() >= 20);
    let musica = chamar(&s, &mut sessao, 6, "generate_music", json!({"situacao": "vila", "compassos": 8})).await;
    assert_eq!(musica["loop"], true);
    assert!(raiz.join("Audio/musica/vila.wav").is_file());
    let espada = chamar(&s, &mut sessao, 7, "generate_3d", json!({"tipo": "arma", "modelo": "espada"})).await;
    assert!(raiz.join("Weapons/espada.glb").is_file(), "{espada}");

    // "crie um inimigo novo": ficha, 3D, esqueleto, animações, cena na engine e teste
    let inimigo = chamar(
        &s,
        &mut sessao,
        8,
        "create_character",
        json!({"papel": "inimigo", "descricao": "orc grandalhão com martelo", "testar_na_engine": true}),
    )
    .await;
    let id = inimigo["ficha"]["id"].as_str().unwrap();
    assert!(raiz.join(format!("Enemies/{id}/{id}.glb")).is_file(), "{inimigo}");
    let teste = &inimigo["teste"];
    eprintln!("run_test: {}", serde_json::to_string_pretty(teste).unwrap());
    assert_eq!(teste["passou"], true, "{teste}");
    assert_eq!(teste["erros"], json!([]));
    assert!(teste["inimigos"]["perseguiram"].as_u64().unwrap() >= 1, "o inimigo novo viu o jogador");
    assert!(teste["jogador"]["andou_m"].as_f64().unwrap() > 3.0);

    // a bíblia ganhou os dois personagens e quem pediu foi o Claude Code
    let b = chamar(&s, &mut sessao, 9, "get_project", json!({})).await;
    assert_eq!(b["biblia"]["personagens"].as_array().unwrap().len(), 2);
    let recibos = chamar(&s, &mut sessao, 10, "list_receipts", json!({})).await;
    let lista = recibos["recibos"].as_array().unwrap();
    assert!(lista.len() > 30);
    assert!(lista.iter().all(|r| r["quem_pediu"] == "claude-code"));
    // tudo que foi gerado tem recibo e licença que deixa vender
    let pend = chamar(&s, &mut sessao, 11, "check_licenses", json!({})).await;
    assert_eq!(pend["pode_vender"], true, "{pend}");
    let creditos = chamar(&s, &mut sessao, 12, "export_credits", json!({})).await;
    assert!(creditos["markdown"].as_str().unwrap().contains("Forja da Fornalha"));
    // o guia visual: as cores dos modelos contra a paleta da bíblia
    let estilo = chamar(&s, &mut sessao, 13, "check_style", json!({})).await;
    eprintln!("check_style: {} de {} dentro da paleta; fora: {}", estilo["aprovados"], estilo["conferidos"], estilo["fora_do_guia"]);
    assert!(estilo["conferidos"].as_u64().unwrap() >= 4, "{estilo}");
    if let Ok(d) = std::env::var("FORNALHA_TESTE_SAIDA") {
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(std::path::Path::new(&d).join("guia_visual.json"), serde_json::to_vec_pretty(&estilo).unwrap()).unwrap();
    }

    if let Ok(d) = std::env::var("FORNALHA_TESTE_SAIDA") {
        // guarda o projeto inteiro para ver depois (CI sobe como artefato)
        let destino = std::path::Path::new(&d).join("projeto-gerado");
        let _ = std::fs::remove_dir_all(&destino);
        copiar(&raiz, &destino);
    }
}

#[tokio::test]
async fn pedido_livre_vai_para_a_fila_e_gera_de_verdade() {
    let tmp = tempfile::tempdir().unwrap();
    let Some(f) = fornalha_com_ferramentas(tmp.path()).await else {
        eprintln!("Blender ou engine não encontrados: teste pulado");
        return;
    };
    f.definir_porta_ignis(1).unwrap(); // sem Ignis: o plano sai das regras
    let p = f.chamar("create_project", json!({"nome": "Pedido Livre"}), "codex").await.unwrap();
    let raiz = std::path::PathBuf::from(p["raiz"].as_str().unwrap());
    let r = f.chamar("plan_request", json!({"pedido": "um goblin inimigo, uma lança e a música da masmorra"}), "codex").await.unwrap();
    let nomes: Vec<&str> = r["passos"].as_array().unwrap().iter().filter_map(|x| x["ferramenta"].as_str()).collect();
    assert_eq!(nomes, ["create_character", "generate_3d", "generate_music"], "{r}");
    while let Some(t) = fornalha_core::fila::rodar_proxima(&f, false).await {
        assert_eq!(t.situacao, fornalha_core::fila::Situacao::Feita, "{} falhou: {:?}", t.ferramenta, t.erro);
    }
    let fichas = f.chamar("get_project", json!({}), "codex").await.unwrap();
    let goblin = &fichas["biblia"]["personagens"][0];
    assert_eq!(goblin["tipo"], "goblin", "{goblin}");
    let id = goblin["id"].as_str().unwrap();
    assert!(raiz.join(format!("Enemies/{id}/{id}.glb")).is_file());
    assert!(raiz.join("Weapons/lanca.glb").is_file());
    assert!(raiz.join("Audio/musica/masmorra.wav").is_file());
}

/// Com os pacotes de conteúdo (FORNALHA_PACOTE_MAKEHUMAN / _ANIMACOES / _MATERIAIS):
/// o personagem sai realista, com roupa medieval PBR e animações de captura, e roda no jogo.
#[tokio::test]
async fn personagem_realista_com_pacotes_testado_na_engine() {
    let tmp = tempfile::tempdir().unwrap();
    let Some(f) = fornalha_com_ferramentas(tmp.path()).await else {
        eprintln!("Blender ou engine não encontrados: teste pulado");
        return;
    };
    if fornalha_core::pacotes::para_a_forja(&f.paths).is_none() {
        eprintln!("pacotes de conteúdo não encontrados: teste pulado");
        return;
    }
    f.definir_porta_ignis(1).unwrap();
    let p = f.chamar("create_project", json!({"nome": "Ordem do Templo"}), "claude-code").await.unwrap();
    let raiz = std::path::PathBuf::from(p["raiz"].as_str().unwrap());
    // nível Qualidade: armadura com o desgaste assado num atlas e pele com poros e rugas (2K)
    f.chamar(
        "update_project",
        json!({"alteracoes": {"nivel": "qualidade", "guia_visual": {"paleta": ["#d9d3c3", "#7a1c18", "#3d2a1c"]}}}),
        "claude-code",
    )
    .await
    .unwrap();
    let heroi = f
        .chamar("create_character", json!({"nome": "Godofredo", "papel": "protagonista", "descricao": "cavaleiro templário", "armadura": "pesada", "arma": "espada", "porte": "forte", "conceito": false}), "claude-code")
        .await
        .unwrap();
    eprintln!("herói: {}", serde_json::to_string_pretty(&heroi["estatisticas"]).unwrap());
    assert_eq!(heroi["modelo_3d"], "humano-fornalha", "{heroi}");
    let nomes: Vec<&str> = heroi["estatisticas"]["animacoes"].as_array().unwrap().iter().filter_map(|a| a["nome"].as_str()).collect();
    for n in ["parado", "andar", "correr", "atacar", "defender", "esquivar", "dano", "morrer"] {
        assert!(nomes.contains(&n), "falta a animação {n}: {nomes:?}");
    }
    assert!(heroi["estatisticas"]["triangulos"].as_u64().unwrap() > 20000);
    // templário: as placas viraram uma malha só (atlas com desgaste)
    let pecas: Vec<&str> = heroi["estatisticas"]["pecas"].as_array().unwrap().iter().filter_map(|p| p.as_str()).collect();
    assert!(pecas.iter().any(|p| p.ends_with("_armadura")), "{pecas:?}");
    assert!(pecas.iter().any(|p| p.ends_with("_sobreveste")), "{pecas:?}");
    let inimigo = f
        .chamar("create_character", json!({"papel": "inimigo", "descricao": "mercenário com espada", "armadura": "leve", "arma": "espada", "testar_na_engine": true, "conceito": false}), "claude-code")
        .await
        .unwrap();
    let teste = &inimigo["teste"];
    eprintln!("run_test: {}", serde_json::to_string_pretty(teste).unwrap());
    assert_eq!(inimigo["modelo_3d"], "humano-fornalha");
    assert_eq!(teste["passou"], true, "{teste}");
    assert_eq!(teste["erros"], json!([]));
    // movimento no humano realista (esqueleto de jogo): árvore, pés no chão, olhar e golpe andando
    comum::conferir_movimento(teste);
    let pend = f.chamar("check_licenses", json!({}), "claude-code").await.unwrap();
    assert_eq!(pend["pode_vender"], true, "{pend}");
    if let Ok(d) = std::env::var("FORNALHA_TESTE_SAIDA") {
        let destino = std::path::Path::new(&d).join("realista");
        let _ = std::fs::remove_dir_all(&destino);
        copiar(&raiz, &destino);
    }
}

fn copiar(de: &std::path::Path, para: &std::path::Path) {
    std::fs::create_dir_all(para).unwrap();
    for e in std::fs::read_dir(de).unwrap().flatten() {
        let nome = e.file_name();
        if nome == ".godot" {
            continue;
        }
        let alvo = para.join(&nome);
        if e.path().is_dir() {
            copiar(&e.path(), &alvo);
        } else {
            std::fs::copy(e.path(), alvo).unwrap();
        }
    }
}
