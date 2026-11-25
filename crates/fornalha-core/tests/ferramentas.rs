//! As ferramentas que a pessoa, o cérebro e o Claude Code/Codex usam do mesmo jeito.

mod comum;

use std::sync::Arc;

use fornalha_core::config::Config;
use fornalha_core::ferramentas;
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};

fn fornalha(dir: &std::path::Path, placa: &str) -> Arc<Fornalha> {
    Fornalha::para_testes(Paths::under(dir), comum::detection(placa))
}

async fn chamar(f: &Fornalha, nome: &str, args: Value) -> Value {
    match f.chamar(nome, args, "claude-code").await {
        Ok(v) => v,
        Err(e) => panic!("{nome} falhou: {} ({})", e.mensagem, e.codigo),
    }
}

#[test]
fn nomes_das_ferramentas_seguem_o_plano() {
    let nomes: Vec<&str> = ferramentas::lista().iter().map(|f| f.nome).collect();
    for n in [
        "get_status",
        "create_project",
        "open_project",
        "list_projects",
        "get_project",
        "update_project",
        "detect_gpu",
        "list_quality_levels",
        "choose_model",
        "list_models",
        "record_receipt",
        "list_receipts",
        "check_licenses",
        "export_credits",
    ] {
        assert!(nomes.contains(&n), "faltou {n}");
    }
}

#[test]
fn toda_ferramenta_tem_descricao_e_esquema_de_objeto() {
    for f in ferramentas::lista() {
        assert!(!f.descricao.is_empty(), "{}", f.nome);
        assert_eq!(f.esquema["type"], "object", "{}", f.nome);
        assert!(f.nome.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_'), "{}", f.nome);
    }
}

#[tokio::test]
async fn criar_projeto_vira_o_projeto_atual_e_entra_nos_recentes() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    let r = chamar(&f, "create_project", json!({"nome": "Reino de Cinzas", "genero": "action RPG", "camera": "terceira pessoa"})).await;
    let raiz = r["raiz"].as_str().unwrap().to_string();
    assert!(std::path::Path::new(&raiz).join("game.project.json").is_file());
    assert_eq!(r["biblia"]["conceito"]["genero"], "action RPG");
    assert_eq!(r["biblia"]["comercial"], true);

    let atual = chamar(&f, "get_project", json!({})).await;
    assert_eq!(atual["biblia"]["nome"], "Reino de Cinzas");

    let lista = chamar(&f, "list_projects", json!({})).await;
    assert_eq!(lista["recentes"][0]["raiz"], raiz);
    // ficou gravado na configuração
    let cfg = Config::carregar(&Paths::under(tmp.path()));
    assert_eq!(cfg.projetos_recentes[0].to_string_lossy(), raiz);
}

#[tokio::test]
async fn sem_projeto_aberto_explica_o_que_fazer() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    let e = f.chamar("get_project", json!({}), "claude-code").await.unwrap_err();
    assert_eq!(e.codigo, "sem_projeto");
    assert!(e.mensagem.contains("create_project"));
}

#[tokio::test]
async fn ferramenta_desconhecida_e_argumento_ruim() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    assert_eq!(f.chamar("voar", json!({}), "x").await.unwrap_err().codigo, "ferramenta_desconhecida");
    assert_eq!(f.chamar("create_project", json!({"nome": 3}), "x").await.unwrap_err().codigo, "argumento_invalido");
    assert_eq!(f.chamar("create_project", json!("texto"), "x").await.unwrap_err().codigo, "argumento_invalido");
}

#[tokio::test]
async fn abrir_e_atualizar_projeto() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    let r = chamar(&f, "create_project", json!({"nome": "Abrir"})).await;
    let raiz = r["raiz"].as_str().unwrap().to_string();
    let f2 = fornalha(tmp.path(), "rtx3060");
    chamar(&f2, "open_project", json!({"caminho": raiz})).await;
    let b = chamar(&f2, "update_project", json!({"alteracoes": {"conceito": {"historia": "Um ferreiro contra o rei das cinzas."}}})).await;
    assert_eq!(b["biblia"]["conceito"]["historia"], "Um ferreiro contra o rei das cinzas.");
}

#[tokio::test]
async fn detectar_placa_traz_a_sugestao() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rx580");
    let d = chamar(&f, "detect_gpu", json!({})).await;
    assert_eq!(d["sugestao"]["nivel"], "leve");
    assert_eq!(d["sugestao"]["aceleradores"]["cuda"], false);
    assert!(d["placas"][0]["nome"].as_str().unwrap().contains("RX 580"));
}

#[tokio::test]
async fn nivel_em_uso_segue_projeto_depois_maquina() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    chamar(&f, "create_project", json!({"nome": "Níveis"})).await;
    let t = chamar(&f, "list_quality_levels", json!({})).await;
    assert_eq!(t["nivel_sugerido"], "equilibrado");
    assert_eq!(t["nivel_em_uso"], "equilibrado");
    assert_eq!(t["tabela"].as_array().unwrap().len(), 4);
    chamar(&f, "update_project", json!({"alteracoes": {"nivel": "maximo"}})).await;
    let t = chamar(&f, "list_quality_levels", json!({})).await;
    assert_eq!(t["nivel_em_uso"], "maximo");
}

#[tokio::test]
async fn escolher_modelo_usa_projeto_e_placa() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rx9060xt"); // AMD 16 GB: Qualidade, sem CUDA
    chamar(&f, "create_project", json!({"nome": "AMD"})).await;
    let e = chamar(&f, "choose_model", json!({"funcao": "rig"})).await;
    assert_eq!(e["nivel"], "qualidade");
    assert_eq!(e["modelo"]["id"], "rigify-blender");
    let e = chamar(&f, "choose_model", json!({"funcao": "cerebro", "nivel": "leve"})).await;
    assert_eq!(e["modelo"]["id"], "qwen3-4b");
    let erro = f.chamar("choose_model", json!({"funcao": "cerebro", "nivel": "ultra"}), "x").await.unwrap_err();
    assert_eq!(erro.codigo, "argumento_invalido");
}

#[tokio::test]
async fn listar_modelos_mostra_a_situacao_no_projeto() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    chamar(&f, "create_project", json!({"nome": "Modelos"})).await;
    let m = chamar(&f, "list_models", json!({"funcao": "voz"})).await;
    let lista = m["modelos"].as_array().unwrap();
    assert!(lista.iter().all(|x| x["funcao"] == "voz"));
    let omni = lista.iter().find(|x| x["id"] == "omnivoice").unwrap();
    assert_eq!(omni["situacao"]["situacao"], "bloqueado");
    let chatter = lista.iter().find(|x| x["id"] == "chatterbox-ptbr").unwrap();
    assert_eq!(chatter["situacao"]["situacao"], "liberado");
}

#[tokio::test]
async fn recibo_pelo_agente_marca_quem_pediu() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    let r = chamar(&f, "create_project", json!({"nome": "Recibo"})).await;
    let raiz = std::path::PathBuf::from(r["raiz"].as_str().unwrap());
    std::fs::write(raiz.join("Characters/heroi.png"), b"png").unwrap();
    let rec =
        chamar(&f, "record_receipt", json!({"arquivo": "Characters/heroi.png", "modelo": "flux2-klein-4b", "prompt": "herói", "seed": 7}))
            .await;
    assert_eq!(rec["recibo"]["quem_pediu"], "claude-code");
    let lista = chamar(&f, "list_receipts", json!({})).await;
    assert_eq!(lista["recibos"].as_array().unwrap().len(), 1);
    let pend = chamar(&f, "check_licenses", json!({})).await;
    assert_eq!(pend["pode_vender"], true);
    let rel = chamar(&f, "export_credits", json!({})).await;
    assert!(rel["markdown"].as_str().unwrap().contains("FLUX.2 klein 4B"));
}

#[tokio::test]
async fn aceite_de_licenca_so_pela_janela() {
    // O agente não aceita licença em nome da pessoa: isso só existe no canal da janela.
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    assert!(ferramentas::lista().iter().all(|t| !t.nome.contains("accept")));
    f.definir_estudio(fornalha_core::config::Estudio { receita_anual_usd: Some(50_000), licencas_aceitas: vec!["tencent-hunyuan".into()] })
        .unwrap();
    chamar(&f, "create_project", json!({"nome": "Aceite"})).await;
    let e = chamar(&f, "choose_model", json!({"funcao": "animacao", "nivel": "maximo"})).await;
    assert_eq!(e["modelo"]["id"], "hy-motion-1.0");
    // aceite gravado na configuração
    let cfg = Config::carregar(&Paths::under(tmp.path()));
    assert_eq!(cfg.estudio.licencas_aceitas, ["tencent-hunyuan"]);
}

#[tokio::test]
async fn estado_mostra_versao_fase_e_ignis() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rtx3060");
    let s = chamar(&f, "get_status", json!({})).await;
    assert_eq!(s["app"], "Fornalha");
    assert_eq!(s["fase"], 0);
    assert!(s["ignis"]["conectado"].is_boolean());
    assert!(s["projeto_atual"].is_null());
}

#[tokio::test]
async fn musica_grava_os_dados_do_laco_para_a_erethea() {
    // pedido da Erethea: <situacao>.musica.json ao lado do .wav (bpm, compassos, tônica, loop)
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "rx580");
    let r = chamar(&f, "create_project", json!({"nome": "Trilha"})).await;
    let raiz = std::path::PathBuf::from(r["raiz"].as_str().unwrap());
    chamar(&f, "generate_music", json!({"situacao": "combate", "compassos": 2})).await;
    assert!(raiz.join("Audio/musica/combate.wav").is_file());
    let info: Value = serde_json::from_slice(&std::fs::read(raiz.join("Audio/musica/combate.musica.json")).unwrap()).unwrap();
    assert_eq!(info["situacao"], "combate");
    assert_eq!(info["compassos"], 2);
    assert_eq!(info["loop"], true);
    assert!(info["bpm"].as_u64().unwrap() > 0);
    assert!(!info["tonica"].as_str().unwrap().is_empty());
}

/// Cena curta: o roteiro vira Cutscenes/<id>.cena.json (aqui só com legenda, sem o Ignis), com aviso
/// para quem ainda não é personagem e recusa de enquadramento que não existe.
#[tokio::test]
async fn cena_curta_pelo_roteiro() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path(), "nenhuma");
    chamar(&f, "create_project", json!({"nome": "Cena"})).await;
    let r = chamar(
        &f,
        "create_cutscene",
        json!({"id": "Abertura da Vila", "sem_voz": true, "roteiro": [
            {"quem": "aren", "fala": "A vila precisa de ajuda.", "camera": "close", "olhar_para": "mira"},
            {"quem": "mira", "fala": "Então vamos.", "camera": "ombro", "olhar_para": "aren", "animacao": "acenar"},
            {"quem": "aren", "camera": "aberto", "duracao": 2.5}]}),
    )
    .await;
    let arq = std::path::PathBuf::from(r["arquivo"].as_str().unwrap());
    assert!(arq.ends_with("Cutscenes/abertura-da-vila.cena.json"), "{arq:?}");
    let cena: Value = serde_json::from_slice(&std::fs::read(&arq).unwrap()).unwrap();
    let linhas = cena["linhas"].as_array().unwrap();
    assert_eq!(linhas.len(), 3);
    assert_eq!(linhas[1]["camera"], "ombro");
    assert_eq!(linhas[1]["animacao"], "acenar");
    assert_eq!(linhas[0]["audio"], "", "sem_voz: só legenda");
    assert!(linhas[0]["duracao"].as_f64().unwrap() > 2.0, "tempo de leitura da legenda");
    assert_eq!(linhas[2]["duracao"], 2.5);
    assert!(r["avisos"].as_array().unwrap().iter().any(|a| a.as_str().unwrap().contains("aren")), "personagem que não existe vira aviso");
    let e = f
        .chamar("create_cutscene", json!({"id": "x", "sem_voz": true, "roteiro": [{"quem": "aren", "camera": "drone"}]}), "claude-code")
        .await
        .unwrap_err();
    assert!(e.mensagem.contains("drone"), "{}", e.mensagem);
}
