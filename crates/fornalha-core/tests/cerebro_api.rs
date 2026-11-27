//! Cérebro por API (Claude e Gemini) contra um servidor falso em 127.0.0.1 que fala como as APIs de
//! verdade (FORNALHA_CEREBRO_BASE): a chave vai no cabeçalho certo e nunca na linha de comando; o plano
//! sai pelo cérebro por API quando o Ignis está fechado; o "Pedir à IA" chama as ferramentas da Fornalha,
//! devolve os resultados, passa adiante sem mexer o pensamento (Claude) e a assinatura (Gemini), conta o
//! gasto e para no erro de chave. Roda sem internet e sem gastar nada (precisa só do curl do sistema).

mod comum;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::extract::{Path as Caminho, State};
use axum::http::{HeaderMap, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use fornalha_core::cerebro_api;
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};

#[derive(Clone, Default)]
struct Falso {
    pedidos: Arc<Mutex<Vec<(String, Value, Value)>>>, // (rota, cabeçalhos que importam, corpo)
}

fn cab(h: &HeaderMap) -> Value {
    let v = |k: &str| h.get(k).and_then(|x| x.to_str().ok()).unwrap_or("").to_string();
    json!({"x-api-key": v("x-api-key"), "anthropic-version": v("anthropic-version"), "x-goog-api-key": v("x-goog-api-key")})
}

async fn mensagens(State(s): State<Falso>, h: HeaderMap, Json(corpo): Json<Value>) -> (StatusCode, Json<Value>) {
    s.pedidos.lock().unwrap().push(("messages".into(), cab(&h), corpo.clone()));
    if h.get("x-api-key").and_then(|x| x.to_str().ok()) != Some("sk-ant-teste") {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})),
        );
    }
    let uso = json!({"input_tokens": 1200, "output_tokens": 80, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0});
    if corpo.get("tools").is_none() {
        // escrever JSON: o plano (esquema com objeto livre → sem a saída em JSON)
        let texto =
            json!({"passos": [{"ferramenta": "generate_sfx", "argumentos": {"efeitos": ["passos na grama"]}, "motivo": "efeito pedido"}]});
        return (
            StatusCode::OK,
            Json(json!({"content": [{"type": "text", "text": texto.to_string()}], "stop_reason": "end_turn", "usage": uso})),
        );
    }
    let n = corpo["messages"].as_array().map(|m| m.len()).unwrap_or(0);
    if n == 1 {
        (
            StatusCode::OK,
            Json(json!({"content": [
                {"type": "thinking", "thinking": "", "signature": "assinatura-do-pensamento"},
                {"type": "text", "text": "Vou ver o estado."},
                {"type": "tool_use", "id": "toolu_1", "name": "get_status", "input": {}}
            ], "stop_reason": "tool_use", "usage": uso})),
        )
    } else {
        (
            StatusCode::OK,
            Json(
                json!({"content": [{"type": "text", "text": "Pronto: olhei o estado da Fornalha."}], "stop_reason": "end_turn", "usage": uso}),
            ),
        )
    }
}

async fn modelos_anthropic(State(s): State<Falso>, h: HeaderMap) -> Json<Value> {
    s.pedidos.lock().unwrap().push(("models".into(), cab(&h), Value::Null));
    Json(json!({"data": [{"id": "claude-haiku-5-5"}, {"id": "claude-sonnet-5-5"}, {"id": "outro-modelo"}]}))
}

async fn gemini(State(s): State<Falso>, Caminho(resto): Caminho<String>, h: HeaderMap, Json(corpo): Json<Value>) -> Json<Value> {
    s.pedidos.lock().unwrap().push((format!("gemini:{resto}"), cab(&h), corpo.clone()));
    let uso = json!({"promptTokenCount": 2000, "candidatesTokenCount": 50, "thoughtsTokenCount": 30});
    let n = corpo["contents"].as_array().map(|m| m.len()).unwrap_or(0);
    let partes = if n == 1 {
        json!([{"functionCall": {"name": "get_status", "args": {}, "id": "chamada-1"}, "thoughtSignature": "assinatura-gemini"}])
    } else {
        json!([{"text": "Pronto pelo Gemini."}])
    };
    Json(json!({"candidates": [{"content": {"role": "model", "parts": partes}, "finishReason": "STOP"}], "usageMetadata": uso}))
}

async fn modelos_gemini() -> Json<Value> {
    Json(json!({"models": [
        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-2", "supportedGenerationMethods": ["embedContent"]}
    ]}))
}

async fn esperar_terminar(f: &Fornalha) -> Value {
    for _ in 0..300 {
        let e = f.conversa_ia().ver();
        if e["rodando"] == false {
            return e;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    panic!("o pedido não terminou: {}", f.conversa_ia().ver());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn claude_e_gemini_conduzem_as_ferramentas_pelo_servidor_falso() {
    let falso = Falso::default();
    let app = Router::new()
        .route("/v1/messages", post(mensagens))
        .route("/v1/models", get(modelos_anthropic))
        .route("/v1beta/models", get(modelos_gemini))
        .route("/v1beta/models/{*resto}", post(gemini))
        .with_state(falso.clone());
    let ouvinte = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let porta = ouvinte.local_addr().unwrap().port();
    tokio::spawn(async move { axum::serve(ouvinte, app).await.unwrap() });
    std::env::set_var("FORNALHA_CEREBRO_BASE", format!("http://127.0.0.1:{porta}"));

    let tmp = tempfile::tempdir().unwrap();
    let f = Fornalha::para_testes(Paths::under(tmp.path()), comum::detection("sem-placa"));
    f.chamar("create_project", json!({"nome": "Cérebro"}), "pessoa").await.unwrap();

    // desligado por padrão: o plano sai das regras e "Pedir à IA" recusa
    let r = f.chamar("plan_request", json!({"pedido": "efeitos de passos na grama", "executar": "nao"}), "claude-code").await.unwrap();
    assert_eq!(r["origem"], "regras");
    assert_eq!(cerebro_api::pedir(f.clone(), "olhe o estado", None).unwrap_err().codigo, "sem_cerebro_api");

    // a pessoa liga o Claude pela janela
    cerebro_api::definir(&f.paths, "anthropic", Some(true), Some("sk-ant-teste".into()), None).unwrap();
    let e = cerebro_api::atualizar_modelos(&f.paths, "anthropic").await.unwrap();
    assert_eq!(e[0]["da_api"], json!(["claude-haiku-5-5", "claude-sonnet-5-5"]), "só os modelos claude-*");
    let st = f.chamar("get_status", json!({}), "pessoa").await.unwrap();
    assert!(!st.to_string().contains("sk-ant-teste"), "a chave nunca aparece no estado");
    assert_eq!(st["cerebro_api"][0]["ligada"], true);

    // o plano agora sai pelo cérebro por API
    let r = f.chamar("plan_request", json!({"pedido": "efeitos de passos na grama", "executar": "nao"}), "claude-code").await.unwrap();
    assert_eq!(r["origem"], "cerebro", "{r}");
    assert_eq!(r["cerebro"], "api:claude-haiku-5-5");
    assert_eq!(r["passos"][0]["ferramenta"], "generate_sfx");

    // "Pedir à IA" pelo Claude: chama get_status e termina
    cerebro_api::pedir(f.clone(), "olhe o estado da Fornalha", Some(0.25)).unwrap();
    assert_eq!(cerebro_api::pedir(f.clone(), "outro", None).unwrap_err().codigo, "pedido_rodando", "um por vez");
    let e = esperar_terminar(&f).await;
    assert_eq!(e["resposta"], "Pronto: olhei o estado da Fornalha.", "{e}");
    let passos = e["passos"].as_array().unwrap();
    assert!(passos.iter().any(|p| p["tipo"] == "ferramenta" && p["texto"].as_str().unwrap().starts_with("get_status")), "{e}");
    assert!(passos.iter().any(|p| p["tipo"] == "resultado"), "{e}");
    assert_eq!(e["gasto"]["entrada"], 2400);
    assert!(e["gasto"]["usd"].as_f64().unwrap() > 0.0 && e["gasto"]["com_preco"] == true);
    {
        let ped = falso.pedidos.lock().unwrap();
        let agente: Vec<&(String, Value, Value)> = ped.iter().filter(|(r, _, c)| r == "messages" && c.get("tools").is_some()).collect();
        assert_eq!(agente.len(), 2);
        let (_, cabecalhos, primeiro) = agente[0];
        assert_eq!(cabecalhos["x-api-key"], "sk-ant-teste");
        assert_eq!(cabecalhos["anthropic-version"], "2026-10-21");
        assert_eq!(primeiro["model"], "claude-haiku-5-5");
        assert_eq!(primeiro["cache_control"]["type"], "ephemeral");
        assert_eq!(primeiro["output_config"]["effort"], "medium");
        assert!(primeiro.get("temperature").is_none(), "sem parâmetros de amostragem");
        assert!(primeiro["tools"].as_array().unwrap().iter().any(|t| t["name"] == "check_motion" && t["input_schema"]["type"] == "object"));
        assert!(primeiro["system"].as_str().unwrap().contains("5 dedos"));
        let (_, _, segundo) = agente[1];
        // o pensamento volta sem mexer e o resultado vai na mensagem do usuário
        assert_eq!(
            segundo["messages"][1]["content"][0],
            json!({"type": "thinking", "thinking": "", "signature": "assinatura-do-pensamento"})
        );
        let res = &segundo["messages"][2]["content"][0];
        assert_eq!((res["type"].as_str(), res["tool_use_id"].as_str()), (Some("tool_result"), Some("toolu_1")));
        assert!(res["content"].as_str().unwrap().contains("Fornalha"), "o resultado do get_status volta ao modelo");
        // a configuração do curl leva a chave pela entrada padrão: nada de chave em arquivo que fica
        assert!(std::fs::read_dir(f.paths.data_dir.join("tmp")).unwrap().all(|x| !x
            .unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with("cerebro_")));
    }

    // o Gemini: a pessoa liga, e o Claude se desliga sozinho (um cérebro conduz por vez)
    cerebro_api::definir(&f.paths, "gemini", Some(false), Some("g-teste".into()), None).unwrap();
    let e = cerebro_api::atualizar_modelos(&f.paths, "gemini").await.unwrap();
    assert_eq!(e[1]["da_api"], json!(["gemini-3.5-flash-lite"]), "sem imagem nem embedding");
    cerebro_api::definir(&f.paths, "gemini", Some(true), None, None).unwrap();
    assert_eq!(cerebro_api::ativo(&f.paths).unwrap().provedor.id, "gemini");
    cerebro_api::pedir(f.clone(), "olhe o estado", None).unwrap();
    let e = esperar_terminar(&f).await;
    assert_eq!(e["resposta"], "Pronto pelo Gemini.", "{e}");
    assert_eq!(e["modelo"], "gemini-3.5-flash-lite");
    {
        let ped = falso.pedidos.lock().unwrap();
        let g: Vec<&(String, Value, Value)> = ped.iter().filter(|(r, _, _)| r.starts_with("gemini:")).collect();
        assert_eq!(g.len(), 2);
        assert_eq!(g[0].0, "gemini:gemini-3.5-flash-lite:generateContent");
        assert_eq!(g[0].1["x-goog-api-key"], "g-teste");
        assert!(g[0].2["tools"][0]["functionDeclarations"]
            .as_array()
            .unwrap()
            .iter()
            .any(|d| d["name"] == "get_status" && d.get("parametersJsonSchema").is_some()));
        let c = &g[1].2["contents"];
        assert_eq!(c[1]["parts"][0]["thoughtSignature"], "assinatura-gemini", "a assinatura volta sem mexer");
        assert_eq!(c[2]["role"], "user");
        assert_eq!(c[2]["parts"][0]["functionResponse"]["id"], "chamada-1");
        assert!(c[2]["parts"][0]["functionResponse"]["response"]["resultado"].is_string());
    }

    // chave errada: o pedido termina com o erro explicado
    cerebro_api::definir(&f.paths, "anthropic", Some(true), Some("sk-ant-errada".into()), None).unwrap();
    cerebro_api::pedir(f.clone(), "olhe o estado", None).unwrap();
    let e = esperar_terminar(&f).await;
    assert!(e["erro"].as_str().unwrap_or("").contains("chave foi recusada"), "{e}");
}
