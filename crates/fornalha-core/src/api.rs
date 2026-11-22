//! API HTTP local da Fornalha, só em 127.0.0.1 (porta padrão 11480).
//!
//! - `GET  /fornalha/estado`                 estado (igual à ferramenta get_status)
//! - `GET  /fornalha/ferramentas`            lista de ferramentas com esquema
//! - `POST /fornalha/ferramentas/{nome}`     chama uma ferramenta (corpo = argumentos)
//! - `POST /mcp`                             MCP por HTTP (Streamable HTTP, respostas JSON)
//!
//! Quem chama pela API pode se identificar com o cabeçalho `x-fornalha-cliente`
//! (vai para os recibos). Pedidos com Host ou Origin de fora são recusados
//! (proteção contra DNS rebinding).

use std::sync::Arc;

use axum::body::Bytes;
use axum::extract::{Path, Request, State};
use axum::http::{HeaderMap, HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde_json::{json, Value};

use crate::erro::Erro;
use crate::ferramentas;
use crate::mcp::{ServidorMcp, Sessao};
use crate::servico::Fornalha;

pub const HEADER_CLIENTE: &str = "x-fornalha-cliente";
const HEADER_SESSAO: &str = "mcp-session-id";

#[derive(Clone)]
struct Estado {
    fornalha: Arc<Fornalha>,
    mcp: ServidorMcp,
}

fn status_do_erro(e: &Erro) -> StatusCode {
    match e.codigo {
        "ferramenta_desconhecida" => StatusCode::NOT_FOUND,
        "pasta_ja_existe" => StatusCode::CONFLICT,
        "erro_de_arquivo" | "erro_interno" => StatusCode::INTERNAL_SERVER_ERROR,
        _ => StatusCode::BAD_REQUEST,
    }
}

fn resposta_erro(e: &Erro) -> Response {
    (status_do_erro(e), Json(json!({"erro": {"codigo": e.codigo, "mensagem": e.mensagem}}))).into_response()
}

fn host_local(h: &str) -> bool {
    let sem_porta = if let Some(resto) = h.strip_prefix('[') {
        resto.split(']').next().unwrap_or("")
    } else {
        h.rsplit_once(':').map(|(a, _)| a).unwrap_or(h)
    };
    matches!(sem_porta, "127.0.0.1" | "localhost" | "::1")
}

fn origem_local(o: &str) -> bool {
    if matches!(o, "tauri://localhost" | "http://tauri.localhost" | "https://tauri.localhost" | "null") {
        return true;
    }
    let Some(resto) = o.strip_prefix("http://").or_else(|| o.strip_prefix("https://")) else { return false };
    host_local(resto.split('/').next().unwrap_or(""))
}

/// Só aceita pedidos para 127.0.0.1/localhost e sem Origin de site de fora.
async fn so_local(req: Request, next: Next) -> Response {
    let headers = req.headers();
    let host_ok = headers.get(http::header::HOST).and_then(|v| v.to_str().ok()).is_none_or(host_local);
    let origem_ok = headers.get(http::header::ORIGIN).and_then(|v| v.to_str().ok()).is_none_or(origem_local);
    if !host_ok || !origem_ok {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"erro": {"codigo": "origem_recusada", "mensagem": "A API da Fornalha só atende pedidos deste computador."}})),
        )
            .into_response();
    }
    next.run(req).await
}

fn cliente(headers: &HeaderMap) -> String {
    headers
        .get(HEADER_CLIENTE)
        .and_then(|v| v.to_str().ok())
        .map(|c| crate::mcp::quem_pelo_cliente(Some(c)))
        .unwrap_or_else(|| "api".into())
}

async fn estado(State(e): State<Estado>, headers: HeaderMap) -> Response {
    match e.fornalha.chamar("get_status", json!({}), &cliente(&headers)).await {
        Ok(v) => Json(v).into_response(),
        Err(err) => resposta_erro(&err),
    }
}

async fn lista() -> Json<Value> {
    let f: Vec<Value> = ferramentas::lista()
        .into_iter()
        .map(|t| json!({"nome": t.nome, "titulo": t.titulo, "descricao": t.descricao, "esquema": t.esquema, "so_leitura": t.so_leitura}))
        .collect();
    Json(json!({"ferramentas": f}))
}

async fn chamar(State(e): State<Estado>, Path(nome): Path<String>, headers: HeaderMap, corpo: Bytes) -> Response {
    let args: Value = if corpo.iter().all(u8::is_ascii_whitespace) {
        json!({})
    } else {
        match serde_json::from_slice(&corpo) {
            Ok(v) => v,
            Err(err) => return resposta_erro(&Erro::argumento(format!("O corpo precisa ser JSON: {err}"))),
        }
    };
    match e.fornalha.chamar(&nome, args, &cliente(&headers)).await {
        Ok(v) => Json(json!({"resultado": v})).into_response(),
        Err(err) => resposta_erro(&err),
    }
}

async fn mcp_post(State(e): State<Estado>, headers: HeaderMap, corpo: Bytes) -> Response {
    let msg: Value = match serde_json::from_slice(&corpo) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"jsonrpc": "2.0", "id": null, "error": {"code": -32700, "message": "JSON inválido."}})),
            )
                .into_response()
        }
    };
    let eh_initialize = msg.get("method").and_then(Value::as_str) == Some("initialize");
    let id_sessao = headers.get(HEADER_SESSAO).and_then(|v| v.to_str().ok()).map(String::from);
    let mut sessao = match (&id_sessao, eh_initialize) {
        (_, true) => Sessao::default(),
        (Some(id), false) => match e.mcp.sessao(id) {
            Some(s) => s,
            None => return (StatusCode::NOT_FOUND, "Sessão MCP desconhecida: comece de novo com initialize.").into_response(),
        },
        // Sem sessão: atende assim mesmo (cliente simples), identificando pelo cabeçalho.
        (None, false) => Sessao { cliente: headers.get(HEADER_CLIENTE).and_then(|v| v.to_str().ok()).map(String::from), versao: None },
    };
    let resposta = e.mcp.tratar(msg, &mut sessao).await;
    let mut r = match resposta {
        Some(v) => Json(v).into_response(),
        None => StatusCode::ACCEPTED.into_response(),
    };
    if eh_initialize {
        let id = e.mcp.nova_sessao(sessao);
        if let Ok(v) = HeaderValue::from_str(&id) {
            r.headers_mut().insert(HEADER_SESSAO, v);
        }
    }
    r
}

async fn mcp_delete(State(e): State<Estado>, headers: HeaderMap) -> StatusCode {
    match headers.get(HEADER_SESSAO).and_then(|v| v.to_str().ok()) {
        Some(id) if e.mcp.encerrar_sessao(id) => StatusCode::NO_CONTENT,
        _ => StatusCode::NOT_FOUND,
    }
}

/// Ponte com a engine: o plugin do editor (Godot/Erethea) pergunta se há assets novos.
async fn ponte(State(e): State<Estado>) -> Json<Value> {
    let (versao, arquivos) = e.fornalha.estado_ponte();
    Json(json!({"versao": versao, "arquivos": arquivos, "websocket": "/fornalha/ponte/ws", "engine": e.fornalha.engine_ao_vivo(),
                "cenas": e.fornalha.cenas_da_engine()}))
}

/// Elo ao vivo com a engine (Erethea): ela manda {"tipo":"ola",…,"monta_cenas"} e {"tipo":"cenas",…};
/// a Fornalha empurra {"tipo":"ponte","versao","arquivos"} sempre que grava algo.
async fn ponte_ws(State(e): State<Estado>, ws: axum::extract::ws::WebSocketUpgrade) -> Response {
    ws.on_upgrade(move |socket| conversa_da_ponte(e.fornalha, socket))
}

async fn conversa_da_ponte(f: Arc<Fornalha>, mut socket: axum::extract::ws::WebSocket) {
    use axum::extract::ws::Message;
    use tokio::sync::broadcast::error::RecvError;
    let mut avisos = f.assinar_ponte();
    let msg_ponte = |(versao, arquivos): (u64, Vec<String>)| {
        Message::Text(json!({"tipo": "ponte", "versao": versao, "arquivos": arquivos}).to_string().into())
    };
    if socket.send(msg_ponte(f.estado_ponte())).await.is_err() {
        return;
    }
    loop {
        tokio::select! {
            m = socket.recv() => match m {
                Some(Ok(Message::Text(t))) => {
                    let v: Value = serde_json::from_str(&t).unwrap_or(Value::Null);
                    match v["tipo"].as_str() {
                        Some("ola") => {
                            f.registrar_engine(Some(v));
                            let r = json!({"tipo": "ola", "programa": crate::consts::APP_NAME, "versao": crate::consts::APP_VERSION});
                            if socket.send(Message::Text(r.to_string().into())).await.is_err() {
                                break;
                            }
                        }
                        Some("cenas") => f.registrar_cenas(v),
                        _ => {}
                    }
                }
                Some(Ok(Message::Close(_))) | Some(Err(_)) | None => break,
                _ => {}
            },
            a = avisos.recv() => match a {
                Ok(p) => {
                    if socket.send(msg_ponte(p)).await.is_err() {
                        break;
                    }
                }
                Err(RecvError::Lagged(_)) => continue,
                Err(RecvError::Closed) => break,
            },
        }
    }
    f.registrar_engine(None);
}

async fn nao_encontrado() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({"erro": {"codigo": "rota_desconhecida", "mensagem": "Rota desconhecida. Veja GET /fornalha/ferramentas."}})),
    )
        .into_response()
}

/// Rotas da API (sem abrir porta; usado também pelo canal da janela).
pub fn router(fornalha: Arc<Fornalha>) -> Router {
    let estado_app = Estado { mcp: ServidorMcp::new(fornalha.clone()), fornalha };
    Router::new()
        .route("/fornalha/estado", get(estado))
        .route("/fornalha/ferramentas", get(lista))
        .route("/fornalha/ferramentas/{nome}", post(chamar))
        .route("/fornalha/ponte", get(ponte))
        .route("/fornalha/ponte/ws", get(ponte_ws))
        .route("/mcp", post(mcp_post).delete(mcp_delete).get(|| async { StatusCode::METHOD_NOT_ALLOWED }))
        .fallback(nao_encontrado)
        .with_state(estado_app)
        .layer(middleware::from_fn(so_local))
}

/// Abre a API em 127.0.0.1 na porta configurada.
pub async fn servir(fornalha: Arc<Fornalha>) -> std::io::Result<()> {
    let porta = fornalha.porta_api();
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", porta)).await?;
    tracing::info!("API da Fornalha em http://127.0.0.1:{porta}");
    axum::serve(listener, router(fornalha)).await
}
