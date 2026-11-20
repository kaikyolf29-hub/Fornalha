//! Servidor MCP (JSON-RPC 2.0): o protocolo que o Claude Code e o Codex usam.

mod comum;

use fornalha_core::mcp::{ServidorMcp, Sessao};
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};

fn servidor(dir: &std::path::Path) -> ServidorMcp {
    ServidorMcp::new(Fornalha::para_testes(Paths::under(dir), comum::detection("rtx3060")))
}

async fn pedir(s: &ServidorMcp, sessao: &mut Sessao, id: u64, metodo: &str, params: Value) -> Value {
    let r = s.tratar(json!({"jsonrpc": "2.0", "id": id, "method": metodo, "params": params}), sessao).await;
    let r = r.expect("pedido com id tem resposta");
    assert_eq!(r["jsonrpc"], "2.0");
    assert_eq!(r["id"], id);
    r
}

async fn iniciar(s: &ServidorMcp, versao: &str) -> (Sessao, Value) {
    let mut sessao = Sessao::default();
    let r = pedir(
        s,
        &mut sessao,
        1,
        "initialize",
        json!({"protocolVersion": versao, "capabilities": {}, "clientInfo": {"name": "claude-code", "version": "2.5.0"}}),
    )
    .await;
    let n = s.tratar(json!({"jsonrpc": "2.0", "method": "notifications/initialized"}), &mut sessao).await;
    assert!(n.is_none(), "notificação não tem resposta");
    (sessao, r)
}

#[tokio::test]
async fn initialize_responde_capacidades_e_versao() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (_, r) = iniciar(&s, "2025-06-18").await;
    assert_eq!(r["result"]["protocolVersion"], "2025-06-18");
    assert_eq!(r["result"]["serverInfo"]["name"], "fornalha");
    assert!(r["result"]["capabilities"]["tools"].is_object());
    assert!(r["result"]["instructions"].as_str().unwrap().contains("create_project"));
}

#[tokio::test]
async fn versao_desconhecida_recebe_a_mais_nova_que_o_servidor_tem() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (_, r) = iniciar(&s, "1999-01-01").await;
    assert_eq!(r["result"]["protocolVersion"], fornalha_core::mcp::VERSOES[0]);
}

#[tokio::test]
async fn tools_list_traz_todas_as_ferramentas_com_esquema() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, _) = iniciar(&s, "2025-06-18").await;
    let r = pedir(&s, &mut sessao, 2, "tools/list", json!({})).await;
    let tools = r["result"]["tools"].as_array().unwrap();
    assert_eq!(tools.len(), fornalha_core::ferramentas::lista().len());
    let criar = tools.iter().find(|t| t["name"] == "create_project").unwrap();
    assert_eq!(criar["inputSchema"]["type"], "object");
    assert_eq!(criar["inputSchema"]["required"][0], "nome");
    assert!(criar["description"].as_str().unwrap().len() > 20);
}

#[tokio::test]
async fn claude_code_cria_um_projeto_pelo_mcp() {
    // O teste de pronto da Fase 0.
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, _) = iniciar(&s, "2025-06-18").await;
    let r = pedir(
        &s,
        &mut sessao,
        3,
        "tools/call",
        json!({"name": "create_project", "arguments": {"nome": "Pelo MCP", "genero": "plataforma"}}),
    )
    .await;
    let res = &r["result"];
    assert_eq!(res["isError"], false);
    let raiz = res["structuredContent"]["raiz"].as_str().unwrap();
    assert!(std::path::Path::new(raiz).join("game.project.json").is_file());
    let texto = res["content"][0]["text"].as_str().unwrap();
    assert_eq!(res["content"][0]["type"], "text");
    let v: Value = serde_json::from_str(texto).unwrap();
    assert_eq!(v["biblia"]["nome"], "Pelo MCP");
}

#[tokio::test]
async fn quem_pediu_vem_do_cliente_mcp() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, _) = iniciar(&s, "2025-06-18").await;
    let r = pedir(&s, &mut sessao, 3, "tools/call", json!({"name": "create_project", "arguments": {"nome": "Quem"}})).await;
    let raiz = std::path::PathBuf::from(r["result"]["structuredContent"]["raiz"].as_str().unwrap());
    std::fs::write(raiz.join("Items/pocao.png"), b"png").unwrap();
    let r = pedir(
        &s,
        &mut sessao,
        4,
        "tools/call",
        json!({"name": "record_receipt", "arguments": {"arquivo": "Items/pocao.png", "modelo": "flux2-klein-4b", "quem_pediu": "pessoa"}}),
    )
    .await;
    assert_eq!(r["result"]["structuredContent"]["recibo"]["quem_pediu"], "claude-code", "o agente não se passa pela pessoa");
}

#[tokio::test]
async fn erro_da_ferramenta_volta_como_resultado_com_iserror() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, _) = iniciar(&s, "2025-06-18").await;
    let r = pedir(&s, &mut sessao, 5, "tools/call", json!({"name": "get_project", "arguments": {}})).await;
    assert_eq!(r["result"]["isError"], true);
    assert!(r["result"]["content"][0]["text"].as_str().unwrap().contains("create_project"));
}

#[tokio::test]
async fn ferramenta_que_nao_existe_e_erro_de_protocolo() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, _) = iniciar(&s, "2025-06-18").await;
    let r = pedir(&s, &mut sessao, 6, "tools/call", json!({"name": "voar", "arguments": {}})).await;
    assert_eq!(r["error"]["code"], -32602);
}

#[tokio::test]
async fn metodo_desconhecido_e_ping() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, _) = iniciar(&s, "2025-06-18").await;
    let r = pedir(&s, &mut sessao, 7, "resources/list", json!({})).await;
    assert_eq!(r["error"]["code"], -32601);
    let r = pedir(&s, &mut sessao, 8, "ping", json!({})).await;
    assert_eq!(r["result"], json!({}));
}

#[tokio::test]
async fn mensagem_quebrada_recebe_erro_de_jsonrpc() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let mut sessao = Sessao::default();
    let r = s.tratar_texto("{ isto não é json", &mut sessao).await.unwrap();
    let v: Value = serde_json::from_str(&r).unwrap();
    assert_eq!(v["error"]["code"], -32700);
    let r = s.tratar(json!({"jsonrpc": "2.0", "id": 1}), &mut sessao).await.unwrap();
    assert_eq!(r["error"]["code"], -32600);
}

#[tokio::test]
async fn id_em_texto_volta_igual() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let mut sessao = Sessao::default();
    let r = s.tratar(json!({"jsonrpc": "2.0", "id": "abc-1", "method": "ping"}), &mut sessao).await.unwrap();
    assert_eq!(r["id"], "abc-1");
}

#[tokio::test]
async fn versao_antiga_sem_structured_content() {
    let tmp = tempfile::tempdir().unwrap();
    let s = servidor(tmp.path());
    let (mut sessao, r) = iniciar(&s, "2024-11-05").await;
    assert_eq!(r["result"]["protocolVersion"], "2024-11-05");
    let r = pedir(&s, &mut sessao, 2, "tools/call", json!({"name": "get_status", "arguments": {}})).await;
    assert!(r["result"].get("structuredContent").is_none());
    assert!(r["result"]["content"][0]["text"].is_string());
}
