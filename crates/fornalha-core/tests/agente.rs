//! O agente completo da Fase 4 e a checagem do guia visual da Fase 2:
//! pedido livre → plano → fila (agora ou à noite) → gerações; e as cores dos
//! assets medidas contra a paleta da bíblia. Roda sem placa, sem Blender e sem Ignis.

mod comum;

use std::path::{Path, PathBuf};
use std::sync::Arc;

use fornalha_core::fila::{self, Situacao};
use fornalha_core::paths::Paths;
use fornalha_core::plano;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};

fn fornalha(dir: &Path) -> Arc<Fornalha> {
    Fornalha::para_testes(Paths::under(dir), comum::detection("sem-placa"))
}

async fn chamar(f: &Fornalha, nome: &str, args: Value) -> Value {
    match f.chamar(nome, args, "claude-code").await {
        Ok(v) => v,
        Err(e) => panic!("{nome} falhou: {} ({})", e.mensagem, e.codigo),
    }
}

fn ferramentas(passos: &[Value]) -> Vec<&str> {
    passos.iter().filter_map(|p| p["ferramenta"].as_str()).collect()
}

#[test]
fn pedido_livre_vira_plano_pelas_regras() {
    let passos = plano::plano_por_regras(
        "Crie a vila e a floresta com dois goblins, uma espada, um barril, a música de combate e depois teste o jogo",
    );
    assert_eq!(
        ferramentas(&passos),
        [
            "generate_blockout",
            "create_character",
            "create_character",
            "generate_3d",
            "generate_3d",
            "generate_music",
            "import_to_engine",
            "run_test"
        ]
    );
    assert_eq!(passos[0]["argumentos"]["areas"], json!([{"id": "vila", "tipo": "vila"}, {"id": "floresta", "tipo": "floresta"}]));
    assert_eq!(passos[1]["argumentos"]["tipo"], "goblin");
    assert_eq!(passos[1]["argumentos"]["papel"], "inimigo");
    assert_eq!(passos[3]["argumentos"], json!({"tipo": "arma", "modelo": "espada"}));
    assert_eq!(passos[5]["argumentos"]["situacao"], "combate");
    // nada reconhecível: plano vazio (a ferramenta explica o que pedir)
    assert!(plano::plano_por_regras("bom dia").is_empty());
    // um chefe e um ferreiro
    let p = plano::plano_por_regras("um chefe orc e um ferreiro aliado");
    assert!(p.iter().any(|x| x["argumentos"]["papel"] == "chefe"));
    assert!(p.iter().any(|x| x["argumentos"]["descricao"] == "ferreiro"));
}

#[tokio::test]
async fn fila_roda_uma_por_vez_e_as_da_noite_so_a_noite() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path());
    let p = chamar(&f, "create_project", json!({"nome": "Fila"})).await;
    let raiz = PathBuf::from(p["raiz"].as_str().unwrap());

    let a = chamar(&f, "queue_job", json!({"ferramenta": "generate_music", "argumentos": {"situacao": "vila", "compassos": 4}})).await;
    let b = chamar(
        &f,
        "queue_job",
        json!({"ferramenta": "generate_sfx", "argumentos": {"efeitos": ["golpe"], "variacoes": 1}, "quando": "noite"}),
    )
    .await;
    let c = chamar(&f, "queue_job", json!({"ferramenta": "generate_code", "quando": "noite"})).await;
    assert_eq!(a["tarefa"]["situacao"], "esperando");
    // a tarefa fica amarrada ao projeto em que foi pedida
    assert_eq!(a["tarefa"]["argumentos"]["projeto"], json!(raiz));
    // só ferramenta de geração ou teste vai para a fila
    let err = f.chamar("queue_job", json!({"ferramenta": "update_project"}), "claude-code").await.unwrap_err();
    assert!(err.mensagem.contains("não vai para a fila"), "{}", err.mensagem);

    // de dia: roda a de "agora" e para
    let t = fila::rodar_proxima(&f, false).await.expect("a de agora roda");
    assert_eq!(t.situacao, Situacao::Feita, "{:?}", t.erro);
    assert!(raiz.join("Audio/musica/vila.wav").is_file());
    assert!(fila::rodar_proxima(&f, false).await.is_none(), "as da noite esperam");
    // cancelar a de código; à noite roda a de efeitos
    chamar(&f, "cancel_job", json!({"id": c["tarefa"]["id"]})).await;
    let t = fila::rodar_proxima(&f, true).await.expect("à noite roda");
    assert_eq!(t.id, b["tarefa"]["id"].as_str().unwrap());
    assert_eq!(t.situacao, Situacao::Feita);
    assert_eq!(t.quem, "claude-code");
    assert!(fila::rodar_proxima(&f, true).await.is_none(), "a cancelada não roda");

    let l = chamar(&f, "list_queue", json!({})).await;
    let situacoes: Vec<&str> = l["tarefas"].as_array().unwrap().iter().filter_map(|t| t["situacao"].as_str()).collect();
    assert_eq!(situacoes, ["feita", "feita", "cancelada"]);
    assert_eq!(l["esperando"], 0);
    assert_eq!(l["noite"]["inicio_hora"], 23);
    // os recibos dizem quem pediu
    let rec = chamar(&f, "list_receipts", json!({})).await;
    assert!(rec["recibos"].as_array().unwrap().iter().all(|r| r["quem_pediu"] == "claude-code"));
    // tirar as terminadas
    assert_eq!(chamar(&f, "cancel_job", json!({"limpar": true})).await["removidas"], 3);
}

#[tokio::test]
async fn tarefa_que_falha_guarda_o_erro_e_a_fila_segue() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path());
    chamar(&f, "create_project", json!({"nome": "Falhas"})).await;
    chamar(&f, "queue_job", json!({"ferramenta": "generate_music", "argumentos": {"situacao": "nao-existe-isso"}})).await;
    chamar(&f, "queue_job", json!({"ferramenta": "generate_music", "argumentos": {"situacao": "combate", "compassos": 4}})).await;
    let t1 = fila::rodar_proxima(&f, false).await.unwrap();
    let t2 = fila::rodar_proxima(&f, false).await.unwrap();
    assert_eq!(t1.situacao, Situacao::Falhou);
    assert!(t1.erro.as_deref().is_some_and(|e| !e.is_empty()));
    assert_eq!(t2.situacao, Situacao::Feita);
}

#[tokio::test]
async fn tarefa_rodando_quando_a_fornalha_fechou_volta_a_esperar() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path());
    chamar(&f, "create_project", json!({"nome": "Retomar"})).await;
    chamar(&f, "queue_job", json!({"ferramenta": "generate_code"})).await;
    // simula a Fornalha fechando no meio da tarefa
    let arq = f.paths.data_dir.join("fila.json");
    let texto = std::fs::read_to_string(&arq).unwrap().replace("\"esperando\"", "\"rodando\"");
    std::fs::write(&arq, texto).unwrap();
    assert!(fila::rodar_proxima(&f, true).await.is_none());
    assert_eq!(fila::retomar_interrompidas(&f).unwrap(), 1);
    assert_eq!(fila::rodar_proxima(&f, false).await.unwrap().situacao, Situacao::Feita);
}

#[tokio::test]
async fn plan_request_sem_ignis_planeja_por_regras_e_poe_na_fila() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path());
    let p = chamar(&f, "create_project", json!({"nome": "Pedido"})).await;
    let raiz = PathBuf::from(p["raiz"].as_str().unwrap());

    let so_plano = chamar(&f, "plan_request", json!({"pedido": "a música da floresta e os efeitos sonoros", "executar": "nao"})).await;
    assert_eq!(so_plano["quando"], "so_o_plano");
    assert!(so_plano["tarefas"].as_array().unwrap().is_empty());

    let r = chamar(&f, "plan_request", json!({"pedido": "a música da floresta e os efeitos sonoros"})).await;
    assert_eq!(r["origem"], "regras");
    assert!(r["avisos"][0].as_str().unwrap().contains("Ignis"));
    assert_eq!(ferramentas(r["passos"].as_array().unwrap()), ["generate_music", "generate_sfx"]);
    assert_eq!(r["tarefas"].as_array().unwrap().len(), 2);
    while fila::rodar_proxima(&f, false).await.is_some() {}
    assert!(raiz.join("Audio/musica/floresta.wav").is_file());
    let l = chamar(&f, "list_queue", json!({})).await;
    let tarefas = l["tarefas"].as_array().unwrap();
    assert!(tarefas.iter().all(|t| t["situacao"] == "feita"), "{l}");
    assert!(tarefas.iter().all(|t| t["grupo"] == tarefas[0]["grupo"]), "o plano é um grupo só");

    let err = f.chamar("plan_request", json!({"pedido": "bom dia"}), "claude-code").await.unwrap_err();
    assert_eq!(err.codigo, "pedido_sem_plano");
}

fn png_listrado(caminho: &Path, cores: &[[u8; 3]]) {
    let (w, h) = (64u32, 64u32);
    let mut dados = Vec::with_capacity((w * h * 3) as usize);
    for y in 0..h {
        let c = cores[(y as usize * cores.len()) / h as usize];
        for _ in 0..w {
            dados.extend_from_slice(&c);
        }
    }
    std::fs::create_dir_all(caminho.parent().unwrap()).unwrap();
    let arq = std::fs::File::create(caminho).unwrap();
    let mut enc = png::Encoder::new(std::io::BufWriter::new(arq), w, h);
    enc.set_color(png::ColorType::Rgb);
    enc.set_depth(png::BitDepth::Eight);
    enc.write_header().unwrap().write_image_data(&dados).unwrap();
}

#[tokio::test]
async fn guia_visual_mede_as_cores_contra_a_paleta() {
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha(tmp.path());
    let p = chamar(&f, "create_project", json!({"nome": "Guia"})).await;
    let raiz = PathBuf::from(p["raiz"].as_str().unwrap());
    // sem paleta, explica
    let err = f.chamar("check_style", json!({}), "claude-code").await.unwrap_err();
    assert_eq!(err.codigo, "sem_paleta");
    chamar(&f, "update_project", json!({"alteracoes": {"guia_visual": {"paleta": ["#5b7a3a", "#7a2e22", "#2f3640"]}}})).await;

    png_listrado(&raiz.join("ai/conceitos/dentro.png"), &[[92, 122, 58], [122, 46, 34], [200, 200, 200]]);
    png_listrado(&raiz.join("Characters/fora.png"), &[[230, 30, 200], [20, 220, 230]]);
    let r = chamar(&f, "check_style", json!({})).await;
    eprintln!("{}", serde_json::to_string_pretty(&r).unwrap());
    assert_eq!(r["conferidos"], 2);
    assert_eq!(r["aprovados"], 1);
    assert_eq!(r["fora_do_guia"], json!(["Characters/fora.png"]));
    let dentro = r["resultados"].as_array().unwrap().iter().find(|x| x["arquivo"] == "ai/conceitos/dentro.png").unwrap();
    assert!(dentro["na_paleta"].as_f64().unwrap() > 0.95);
    assert!(dentro["neutros"].as_f64().unwrap() > 0.3, "o cinza conta como neutro");
    // um arquivo só, com limite pedido
    let um = chamar(&f, "check_style", json!({"arquivo": "Characters/fora.png", "limite": 0.0})).await;
    assert_eq!(um["aprovados"], 1);
}

#[test]
fn plano_do_cerebro_e_conferido_contra_o_esquema() {
    let tmp = tempfile::tempdir().unwrap();
    let mut avisos = Vec::new();
    // o que o Qwen3 0.6B devolveu de verdade no teste com o Ignis
    let passos = vec![
        json!({"ferramenta": "create_character", "argumentos": {"papel": "inimigo", "tipo": "orc", "arma": "martelo", "cor_roupa": "azul", "projeto": "/outro"}, "motivo": "orc"}),
        json!({"ferramenta": "generate_music", "argumentos": {"efeitos": ["música de combate"]}, "motivo": "música"}),
        json!({"ferramenta": "import_to_engine", "argumentos": {"inimigo_perto": true, "jogador": "orc"}, "motivo": "montar"}),
        json!({"ferramenta": "run_test", "argumentos": {"video": true, "segundos": 20}, "motivo": "testar"}),
        json!({"ferramenta": "update_project", "argumentos": {}, "motivo": "fora da fila"}),
        json!({"ferramenta": "generate_animation", "argumentos": {"arquivo": "Characters/nao/existe.glb"}, "motivo": "sem arquivo"}),
    ];
    let s = plano::sanear(passos, "um orc inimigo com martelo e a música de combate, depois teste o jogo", tmp.path(), &mut avisos);
    assert_eq!(ferramentas(&s), ["create_character", "generate_music", "import_to_engine", "run_test"]);
    assert_eq!(s[0]["argumentos"]["arma"], "martelo");
    assert!(s[0]["argumentos"].get("projeto").is_none());
    assert_eq!(s[1]["argumentos"], json!({"situacao": "combate"}), "o obrigatório veio das regras");
    assert_eq!(s[2]["argumentos"], json!({"inimigo_perto": true}), "arquivo que não existe sai");
    assert!(avisos.iter().any(|a| a.contains("generate_animation") && a.contains("arquivo")), "{avisos:?}");
}
