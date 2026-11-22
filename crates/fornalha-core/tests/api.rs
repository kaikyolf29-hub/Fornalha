//! API HTTP local (/fornalha/*) e MCP por HTTP (/mcp), só em 127.0.0.1.

mod comum;

use axum::body::Body;
use fornalha_core::api;
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

fn app(dir: &std::path::Path) -> axum::Router {
    api::router(Fornalha::para_testes(Paths::under(dir), comum::detection("rtx3060")))
}

async fn enviar(app: &axum::Router, req: Request<Body>) -> (StatusCode, http::HeaderMap, Value) {
    let r = app.clone().oneshot(req).await.unwrap();
    let status = r.status();
    let headers = r.headers().clone();
    let bytes = r.into_body().collect().await.unwrap().to_bytes();
    let v = if bytes.is_empty() { Value::Null } else { serde_json::from_slice(&bytes).unwrap_or(Value::Null) };
    (status, headers, v)
}

fn get(uri: &str) -> Request<Body> {
    Request::get(uri).header("host", "127.0.0.1:11480").body(Body::empty()).unwrap()
}

fn post(uri: &str, corpo: Value) -> Request<Body> {
    Request::post(uri)
        .header("host", "127.0.0.1:11480")
        .header("content-type", "application/json")
        .header("accept", "application/json, text/event-stream")
        .body(Body::from(corpo.to_string()))
        .unwrap()
}

#[tokio::test]
async fn estado() {
    let tmp = tempfile::tempdir().unwrap();
    let (s, _, v) = enviar(&app(tmp.path()), get("/fornalha/estado")).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(v["app"], "Fornalha");
    assert_eq!(v["api"], 1);
}

#[tokio::test]
async fn lista_de_ferramentas() {
    let tmp = tempfile::tempdir().unwrap();
    let (s, _, v) = enviar(&app(tmp.path()), get("/fornalha/ferramentas")).await;
    assert_eq!(s, StatusCode::OK);
    assert!(v["ferramentas"].as_array().unwrap().iter().any(|f| f["nome"] == "create_project"));
}

#[tokio::test]
async fn chamar_ferramenta_por_http() {
    let tmp = tempfile::tempdir().unwrap();
    let a = app(tmp.path());
    let (s, _, v) = enviar(&a, post("/fornalha/ferramentas/create_project", json!({"nome": "Pela API"}))).await;
    assert_eq!(s, StatusCode::OK, "{v}");
    assert_eq!(v["resultado"]["biblia"]["nome"], "Pela API");
    let (s, _, v) = enviar(&a, post("/fornalha/ferramentas/create_project", json!({"nome": "Pela API"}))).await;
    assert_eq!(s, StatusCode::CONFLICT);
    assert_eq!(v["erro"]["codigo"], "pasta_ja_existe");
    let (s, _, v) = enviar(&a, post("/fornalha/ferramentas/voar", json!({}))).await;
    assert_eq!(s, StatusCode::NOT_FOUND);
    assert_eq!(v["erro"]["codigo"], "ferramenta_desconhecida");
}

#[tokio::test]
async fn corpo_invalido_e_400() {
    let tmp = tempfile::tempdir().unwrap();
    let req = Request::post("/fornalha/ferramentas/get_status")
        .header("host", "127.0.0.1:11480")
        .header("content-type", "application/json")
        .body(Body::from("{ ruim"))
        .unwrap();
    let (s, _, v) = enviar(&app(tmp.path()), req).await;
    assert_eq!(s, StatusCode::BAD_REQUEST);
    assert_eq!(v["erro"]["codigo"], "argumento_invalido");
}

#[tokio::test]
async fn corpo_vazio_vale_como_objeto_vazio() {
    let tmp = tempfile::tempdir().unwrap();
    let req = Request::post("/fornalha/ferramentas/get_status").header("host", "localhost:11480").body(Body::empty()).unwrap();
    let (s, _, _) = enviar(&app(tmp.path()), req).await;
    assert_eq!(s, StatusCode::OK);
}

#[tokio::test]
async fn site_de_fora_nao_entra() {
    // Proteção contra DNS rebinding: só 127.0.0.1/localhost, e nenhum site de fora.
    let tmp = tempfile::tempdir().unwrap();
    let a = app(tmp.path());
    let req = Request::get("/fornalha/estado").header("host", "malicioso.com").body(Body::empty()).unwrap();
    assert_eq!(enviar(&a, req).await.0, StatusCode::FORBIDDEN);
    let req = Request::post("/mcp")
        .header("host", "127.0.0.1:11480")
        .header("origin", "https://malicioso.com")
        .header("content-type", "application/json")
        .body(Body::from(json!({"jsonrpc": "2.0", "id": 1, "method": "ping"}).to_string()))
        .unwrap();
    assert_eq!(enviar(&a, req).await.0, StatusCode::FORBIDDEN);
    let req = Request::get("/fornalha/estado")
        .header("host", "localhost:11480")
        .header("origin", "http://localhost:3000")
        .body(Body::empty())
        .unwrap();
    assert_eq!(enviar(&a, req).await.0, StatusCode::OK);
}

#[tokio::test]
async fn mcp_por_http_com_sessao() {
    let tmp = tempfile::tempdir().unwrap();
    let a = app(tmp.path());
    let init = json!({"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "codex", "version": "1"}}});
    let (s, h, v) = enviar(&a, post("/mcp", init)).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(v["result"]["serverInfo"]["name"], "fornalha");
    let sessao = h.get("mcp-session-id").expect("sessão criada").to_str().unwrap().to_string();

    let com_sessao = |corpo: Value| {
        Request::post("/mcp")
            .header("host", "127.0.0.1:11480")
            .header("content-type", "application/json")
            .header("accept", "application/json, text/event-stream")
            .header("mcp-session-id", &sessao)
            .header("mcp-protocol-version", "2025-06-18")
            .body(Body::from(corpo.to_string()))
            .unwrap()
    };
    let (s, _, v) = enviar(&a, com_sessao(json!({"jsonrpc": "2.0", "method": "notifications/initialized"}))).await;
    assert_eq!(s, StatusCode::ACCEPTED);
    assert!(v.is_null());

    let (s, _, v) = enviar(
        &a,
        com_sessao(json!({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "create_project", "arguments": {"nome": "Pelo Codex"}}})),
    )
    .await;
    assert_eq!(s, StatusCode::OK);
    let raiz = std::path::PathBuf::from(v["result"]["structuredContent"]["raiz"].as_str().unwrap());
    std::fs::write(raiz.join("Audio/passo.wav"), b"wav").unwrap();
    let (_, _, v) = enviar(
        &a,
        com_sessao(json!({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "record_receipt", "arguments": {"arquivo": "Audio/passo.wav", "modelo": "moss-soundeffect-v2"}}})),
    )
    .await;
    assert_eq!(v["result"]["structuredContent"]["recibo"]["quem_pediu"], "codex");
}

#[tokio::test]
async fn sessao_mcp_desconhecida_e_404() {
    let tmp = tempfile::tempdir().unwrap();
    let req = Request::post("/mcp")
        .header("host", "127.0.0.1:11480")
        .header("content-type", "application/json")
        .header("mcp-session-id", "nao-existe")
        .body(Body::from(json!({"jsonrpc": "2.0", "id": 1, "method": "ping"}).to_string()))
        .unwrap();
    assert_eq!(enviar(&app(tmp.path()), req).await.0, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn get_no_mcp_nao_abre_stream() {
    let tmp = tempfile::tempdir().unwrap();
    assert_eq!(enviar(&app(tmp.path()), get("/mcp")).await.0, StatusCode::METHOD_NOT_ALLOWED);
}

#[tokio::test]
async fn servidor_de_verdade_numa_porta() {
    let tmp = tempfile::tempdir().unwrap();
    let f = Fornalha::para_testes(Paths::under(tmp.path()), comum::detection("rtx3060"));
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let porta = listener.local_addr().unwrap().port();
    tokio::spawn(async move { axum::serve(listener, api::router(f)).await.unwrap() });
    let v: Value = reqwest::get(format!("http://127.0.0.1:{porta}/fornalha/estado")).await.unwrap().json().await.unwrap();
    assert_eq!(v["app"], "Fornalha");
}

#[tokio::test]
async fn ponte_ao_vivo_por_websocket() {
    // pedido da Erethea: /fornalha/ponte/ws; ela diz "ola" (monta_cenas) e manda o relatório de cenas;
    // a Fornalha empurra {"tipo":"ponte"} quando grava algo
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::tungstenite::Message;
    let tmp = tempfile::tempdir().unwrap();
    let f = Fornalha::para_testes(Paths::under(tmp.path()), comum::detection("rx580"));
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let porta = listener.local_addr().unwrap().port();
    let f2 = f.clone();
    tokio::spawn(async move { axum::serve(listener, api::router(f2)).await.unwrap() });
    let v: Value = reqwest::get(format!("http://127.0.0.1:{porta}/fornalha/ponte")).await.unwrap().json().await.unwrap();
    assert_eq!(v["websocket"], "/fornalha/ponte/ws");
    let (mut ws, _) = tokio_tungstenite::connect_async(format!("ws://127.0.0.1:{porta}/fornalha/ponte/ws")).await.unwrap();
    let ler = |m: Option<Result<Message, _>>| -> Value {
        match m {
            Some(Ok(Message::Text(t))) => serde_json::from_str(&t).unwrap(),
            outro => panic!("mensagem inesperada: {outro:?}"),
        }
    };
    let primeira = ler(ws.next().await);
    assert_eq!(primeira["tipo"], "ponte");
    let ola = json!({"tipo": "ola", "programa": "Erethea", "versao": "0.1", "projeto": "x", "monta_cenas": true});
    ws.send(Message::Text(ola.to_string().into())).await.unwrap();
    assert_eq!(ler(ws.next().await)["tipo"], "ola");
    // espera a Fornalha registrar a engine
    for _ in 0..50 {
        if f.engine_monta_cenas() {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    }
    assert!(f.engine_monta_cenas());
    ws.send(Message::Text(json!({"tipo": "cenas", "principal": "res://principal.tscn"}).to_string().into())).await.unwrap();
    f.avisar_ponte(vec!["Characters/heroi/heroi.glb".into()]);
    let aviso = ler(ws.next().await);
    assert_eq!(aviso["tipo"], "ponte");
    assert_eq!(aviso["arquivos"][0], "Characters/heroi/heroi.glb");
    for _ in 0..50 {
        if f.cenas_da_engine().is_some() {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    }
    assert_eq!(f.cenas_da_engine().unwrap()["principal"], "res://principal.tscn");
    ws.close(None).await.unwrap();
    for _ in 0..50 {
        if f.engine_ao_vivo().is_none() {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    }
    assert!(f.engine_ao_vivo().is_none(), "ao desligar, a Fornalha volta a montar as cenas");
}
