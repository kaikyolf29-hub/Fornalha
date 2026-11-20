//! Linha de comando da Fornalha (para agentes, CI e diagnóstico).
//!
//! - `fornalha-cli mcp`                   servidor MCP por stdio (Claude Code, Codex)
//! - `fornalha-cli servir [--porta N]`    API local e MCP por HTTP, sem janela
//! - `fornalha-cli detectar`              placa, aceleradores e nível sugerido (JSON)
//! - `fornalha-cli chamar <ferramenta> [json]`  chama uma ferramenta e imprime o resultado

use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;

const AJUDA: &str = "Fornalha (linha de comando)

Uso:
  fornalha-cli mcp                         servidor MCP por stdio
  fornalha-cli servir [--porta N]          API local e MCP por HTTP (127.0.0.1)
  fornalha-cli detectar                    placa, aceleradores e nível sugerido
  fornalha-cli chamar <ferramenta> [json]  chama uma ferramenta
  fornalha-cli ferramentas                 lista as ferramentas
  fornalha-cli versao

A variável FORNALHA_HOME coloca configuração e projetos numa pasta só.";

fn registro_no_stderr() {
    let filtro = std::env::var("RUST_LOG").unwrap_or_else(|_| "warn".into());
    let _ = tracing_subscriber::fmt().with_env_filter(filtro).with_writer(std::io::stderr).with_ansi(false).try_init();
}

#[tokio::main]
async fn main() {
    registro_no_stderr();
    let args: Vec<String> = std::env::args().skip(1).collect();
    let paths = Paths::from_env();
    let codigo = match args.first().map(String::as_str) {
        Some("mcp") => match fornalha_core::mcp::servir_stdio(Fornalha::new(paths)).await {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("MCP encerrado com erro: {e}");
                1
            }
        },
        Some("servir") => {
            let f = Fornalha::new(paths);
            if let Some(i) = args.iter().position(|a| a == "--porta") {
                let Some(p) = args.get(i + 1).and_then(|p| p.parse::<u16>().ok()) else {
                    eprintln!("--porta precisa de um número");
                    std::process::exit(2);
                };
                f.fixar_porta(p);
            }
            servir(f).await
        }
        Some("detectar") => {
            let f = Fornalha::new(paths);
            imprimir(f.chamar("detect_gpu", serde_json::json!({}), "pessoa").await)
        }
        Some("chamar") => {
            let Some(nome) = args.get(1) else {
                eprintln!("{AJUDA}");
                std::process::exit(2);
            };
            let json = match args.get(2) {
                Some(t) => match serde_json::from_str(t) {
                    Ok(v) => v,
                    Err(e) => {
                        eprintln!("argumentos não são JSON: {e}");
                        std::process::exit(2);
                    }
                },
                None => serde_json::json!({}),
            };
            imprimir(Fornalha::new(paths).chamar(nome, json, "pessoa").await)
        }
        Some("ferramentas") => {
            for t in fornalha_core::ferramentas::lista() {
                println!("{:<22} {}", t.nome, t.titulo);
            }
            0
        }
        Some("versao" | "--version" | "-V") => {
            println!("fornalha-cli {}", fornalha_core::consts::APP_VERSION);
            0
        }
        _ => {
            println!("{AJUDA}");
            if args.is_empty() || matches!(args[0].as_str(), "ajuda" | "--help" | "-h") {
                0
            } else {
                2
            }
        }
    };
    std::process::exit(codigo);
}

async fn servir(f: std::sync::Arc<Fornalha>) -> i32 {
    eprintln!("Fornalha: API em http://127.0.0.1:{} (MCP em /mcp). Ctrl+C para sair.", f.porta_api());
    match fornalha_core::api::servir(f).await {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("Não consegui abrir a API: {e}");
            1
        }
    }
}

fn imprimir(r: Result<serde_json::Value, fornalha_core::erro::Erro>) -> i32 {
    match r {
        Ok(v) => {
            println!("{}", serde_json::to_string_pretty(&v).unwrap_or_default());
            0
        }
        Err(e) => {
            eprintln!("Erro ({}): {}", e.codigo, e.mensagem);
            1
        }
    }
}
