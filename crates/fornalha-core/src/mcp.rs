//! Servidor MCP (Model Context Protocol) da Fornalha.
//!
//! O mesmo tratador atende dois transportes:
//! - stdio (`fornalha --mcp` ou `fornalha-cli mcp`): uma mensagem JSON por linha;
//! - HTTP (`POST http://127.0.0.1:11480/mcp`, "Streamable HTTP", respostas em JSON).
//!
//! Só ferramentas (`tools/list` e `tools/call`); a lista é a de `ferramentas`.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt};

use crate::consts::{APP_NAME, APP_VERSION};
use crate::ferramentas;
use crate::servico::Fornalha;

/// Versões do protocolo que a Fornalha entende, da mais nova para a mais antiga.
pub const VERSOES: [&str; 4] = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];

const INSTRUCOES: &str = "Fornalha: fábrica de jogos 3D com IA local. Fluxo: get_status → create_project (ou open_project) → \
update_project para preencher o conceito e o guia visual → choose_model para saber qual modelo usar em cada função → \
depois de gerar um arquivo, record_receipt (nada entra na engine sem recibo) → check_licenses e export_credits antes de vender. \
A bíblia do jogo (get_project) é a fonte da verdade: leia antes de gerar. Projeto comercial bloqueia modelo sem licença comercial.";

/// Estado de uma conexão MCP.
#[derive(Debug, Clone, Default)]
pub struct Sessao {
    /// Nome do cliente (clientInfo.name), ex.: "claude-code".
    pub cliente: Option<String>,
    pub versao: Option<String>,
}

impl Sessao {
    /// Quem pediu, para os recibos.
    pub fn quem(&self) -> String {
        quem_pelo_cliente(self.cliente.as_deref())
    }

    fn com_structured_content(&self) -> bool {
        // structuredContent entrou na versão 2025-06-18.
        self.versao.as_deref().is_none_or(|v| v >= "2025-06-18")
    }
}

/// "claude-code" → claude-code, "Codex CLI" → codex, outros: o nome limpo (ou "agente").
pub fn quem_pelo_cliente(nome: Option<&str>) -> String {
    let n = nome.unwrap_or("").trim().to_lowercase();
    if n.contains("claude") {
        return "claude-code".into();
    }
    if n.contains("codex") {
        return "codex".into();
    }
    let limpo: String = n.chars().filter(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.')).take(40).collect();
    if limpo.is_empty() {
        "agente".into()
    } else {
        limpo
    }
}

fn erro(id: Value, codigo: i64, mensagem: &str) -> Value {
    json!({"jsonrpc": "2.0", "id": id, "error": {"code": codigo, "message": mensagem}})
}

fn ok(id: Value, resultado: Value) -> Value {
    json!({"jsonrpc": "2.0", "id": id, "result": resultado})
}

pub fn descricao_das_ferramentas() -> Vec<Value> {
    ferramentas::lista()
        .into_iter()
        .map(|t| {
            json!({
                "name": t.nome,
                "title": t.titulo,
                "description": t.descricao,
                "inputSchema": t.esquema,
                "annotations": {
                    "title": t.titulo,
                    "readOnlyHint": t.so_leitura,
                    "destructiveHint": false,
                    "openWorldHint": false
                }
            })
        })
        .collect()
}

#[derive(Clone)]
pub struct ServidorMcp {
    pub fornalha: Arc<Fornalha>,
    /// Sessões do transporte HTTP (Mcp-Session-Id → sessão).
    sessoes: Arc<Mutex<HashMap<String, Sessao>>>,
}

impl ServidorMcp {
    pub fn new(fornalha: Arc<Fornalha>) -> Self {
        Self { fornalha, sessoes: Arc::new(Mutex::new(HashMap::new())) }
    }

    /// Trata uma mensagem JSON-RPC. Notificações e respostas não têm retorno.
    pub async fn tratar(&self, msg: Value, sessao: &mut Sessao) -> Option<Value> {
        let Some(obj) = msg.as_object() else {
            return Some(erro(Value::Null, -32600, "Mensagem JSON-RPC precisa ser um objeto."));
        };
        let id = obj.get("id").cloned();
        let Some(metodo) = obj.get("method").and_then(Value::as_str) else {
            // Resposta do cliente (não pedimos nada) ou mensagem inválida.
            if obj.contains_key("result") || obj.contains_key("error") {
                return None;
            }
            return Some(erro(id.unwrap_or(Value::Null), -32600, "Falta o campo \"method\"."));
        };
        let params = obj.get("params").cloned().unwrap_or(Value::Null);
        let Some(id) = id.filter(|i| !i.is_null()) else {
            // Notificação (notifications/initialized, notifications/cancelled...): nada a responder.
            return None;
        };
        Some(match metodo {
            "initialize" => {
                let pedida = params["protocolVersion"].as_str().unwrap_or("");
                let versao = VERSOES.iter().find(|v| **v == pedida).copied().unwrap_or(VERSOES[0]);
                sessao.versao = Some(versao.to_string());
                sessao.cliente = params["clientInfo"]["name"].as_str().map(String::from);
                ok(
                    id,
                    json!({
                        "protocolVersion": versao,
                        "capabilities": {"tools": {"listChanged": false}},
                        "serverInfo": {"name": "fornalha", "title": APP_NAME, "version": APP_VERSION},
                        "instructions": INSTRUCOES
                    }),
                )
            }
            "ping" => ok(id, json!({})),
            "tools/list" => ok(id, json!({"tools": descricao_das_ferramentas()})),
            "tools/call" => {
                let Some(nome) = params["name"].as_str() else {
                    return Some(erro(id, -32602, "Falta o nome da ferramenta (params.name)."));
                };
                if !ferramentas::lista().iter().any(|t| t.nome == nome) {
                    return Some(erro(id, -32602, &format!("Ferramenta desconhecida: {nome}")));
                }
                let argumentos = params.get("arguments").cloned().unwrap_or(Value::Null);
                match self.fornalha.chamar(nome, argumentos, &sessao.quem()).await {
                    Ok(v) => {
                        let texto = serde_json::to_string_pretty(&v).unwrap_or_default();
                        let mut r = json!({"content": [{"type": "text", "text": texto}], "isError": false});
                        if sessao.com_structured_content() && v.is_object() {
                            r["structuredContent"] = v;
                        }
                        ok(id, r)
                    }
                    Err(e) => ok(
                        id,
                        json!({"content": [{"type": "text", "text": format!("{} (código: {})", e.mensagem, e.codigo)}], "isError": true}),
                    ),
                }
            }
            outro => erro(id, -32601, &format!("Método não suportado: {outro}")),
        })
    }

    /// Trata uma linha de texto (transporte stdio). Devolve a linha de resposta, se houver.
    pub async fn tratar_texto(&self, linha: &str, sessao: &mut Sessao) -> Option<String> {
        let msg: Value = match serde_json::from_str(linha) {
            Ok(v) => v,
            Err(_) => return Some(erro(Value::Null, -32700, "JSON inválido.").to_string()),
        };
        let resposta = match msg {
            // Lotes (versões antigas do protocolo).
            Value::Array(itens) => {
                let mut respostas = Vec::new();
                for item in itens {
                    if let Some(r) = self.tratar(item, sessao).await {
                        respostas.push(r);
                    }
                }
                if respostas.is_empty() {
                    None
                } else {
                    Some(Value::Array(respostas))
                }
            }
            outro => self.tratar(outro, sessao).await,
        };
        resposta.map(|r| r.to_string())
    }

    // ---- sessões do transporte HTTP ----

    pub fn nova_sessao(&self, s: Sessao) -> String {
        let id = crate::util::id_aleatorio(16);
        self.sessoes.lock().unwrap().insert(id.clone(), s);
        id
    }

    pub fn sessao(&self, id: &str) -> Option<Sessao> {
        self.sessoes.lock().unwrap().get(id).cloned()
    }

    pub fn encerrar_sessao(&self, id: &str) -> bool {
        self.sessoes.lock().unwrap().remove(id).is_some()
    }
}

/// Atende o MCP pelo stdin/stdout até o cliente fechar a entrada.
/// Nada além das respostas vai para a saída padrão (registros vão para o stderr).
pub async fn servir_stdio(fornalha: Arc<Fornalha>) -> std::io::Result<()> {
    let servidor = ServidorMcp::new(fornalha);
    let mut sessao = Sessao::default();
    let mut linhas = tokio::io::BufReader::new(tokio::io::stdin()).lines();
    let mut saida = tokio::io::stdout();
    while let Some(linha) = linhas.next_line().await? {
        if linha.trim().is_empty() {
            continue;
        }
        if let Some(r) = servidor.tratar_texto(&linha, &mut sessao).await {
            saida.write_all(r.as_bytes()).await?;
            saida.write_all(b"\n").await?;
            saida.flush().await?;
        }
    }
    Ok(())
}
