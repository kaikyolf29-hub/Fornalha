//! Cérebro por API (opcional, pago): o Claude (API da Anthropic) ou o Gemini (API do Google) no lugar do
//! Ignis, quando a pessoa liga e põe a chave na janela (Agentes → Cérebro por API). Desligado por padrão,
//! com o preço e os termos à vista antes de ligar; a chave fica só neste computador (o mesmo arquivo das
//! APIs de 3D) e nunca aparece no estado, no registro nem na linha de comando.
//!
//! Dois usos:
//! - escrever JSON (a ficha do personagem, o plano do pedido) quando o Ignis não está aberto;
//! - "Pedir à IA": o modelo escolhido conduz as próprias ferramentas da Fornalha (as mesmas do MCP), um
//!   passo por vez, até terminar, com teto de gasto por pedido. Só a pessoa começa, pela janela.
//!
//! O núcleo continua sem HTTPS: quem fala com o serviço é o `curl` do sistema (como nos downloads), com a
//! configuração (endereço e chave) entregue pela entrada padrão (`curl -K -`), fora da linha de comando.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use serde::Serialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::paths::Paths;
use crate::servico::Fornalha;

/// Um modelo da tabela da Fornalha (preços conferidos nas páginas em 27/11/2026).
#[derive(Debug, Clone, Serialize)]
pub struct Modelo {
    pub id: &'static str,
    pub nome: &'static str,
    /// US$ por milhão de tokens de entrada e de saída.
    pub entrada: f64,
    pub saida: f64,
    /// Preço maior quando o pedido passa de tantos tokens: (limite, entrada, saída).
    pub longo: Option<(u64, f64, f64)>,
    pub nota: &'static str,
}

/// Uma API de cérebro.
#[derive(Debug, Clone, Serialize)]
pub struct Provedor {
    pub id: &'static str,
    pub nome: &'static str,
    /// id do modelo no manifesto (licença do que ele escreve)
    pub manifesto: &'static str,
    pub padrao: &'static str,
    pub modelos: &'static [Modelo],
    pub termos: &'static str,
    pub url_termos: &'static str,
    pub url_chave: &'static str,
    pub url_precos: &'static str,
}

pub const PROVEDORES: [Provedor; 2] = [
    Provedor {
        id: "anthropic",
        nome: "Claude (API da Anthropic)",
        manifesto: "claude-api",
        padrao: "claude-haiku-5-5",
        modelos: &[
            Modelo {
                id: "claude-haiku-5-5",
                nome: "Claude Haiku 5.5 — econômico (sugerido)",
                entrada: 0.10,
                saida: 0.50,
                longo: Some((100_000, 0.50, 2.50)),
                nota: "US$ 0,10 por milhão de tokens de entrada e 0,50 de saída (pedido de até 100 mil tokens; acima, 0,50 e 2,50). \
                       Rápido e bom para conduzir as ferramentas: um pedido comum sai por centavos.",
            },
            Modelo {
                id: "claude-sonnet-5-5",
                nome: "Claude Sonnet 5.5 — equilibrado",
                entrada: 2.0,
                saida: 10.0,
                longo: None,
                nota: "US$ 2 por milhão de tokens de entrada e 10 de saída. Pensa melhor em pedidos longos.",
            },
            Modelo {
                id: "claude-opus-5-5",
                nome: "Claude Opus 5.5 — o mais caprichado",
                entrada: 4.0,
                saida: 20.0,
                longo: None,
                nota: "US$ 4 por milhão de tokens de entrada e 20 de saída. Para o pedido difícil.",
            },
        ],
        termos: "Termos Comerciais da Anthropic (17/06/2025): o que o modelo escreve é seu (seção B) e a Anthropic não treina \
                 com o que você manda. Cobra por token dos créditos da sua conta no Console da Anthropic.",
        url_termos: "https://www.anthropic.com/legal/commercial-terms",
        url_chave: "https://console.anthropic.com/settings/keys",
        url_precos: "https://platform.claude.com/docs/en/about-claude/pricing",
    },
    Provedor {
        id: "gemini",
        nome: "Gemini (API do Google)",
        manifesto: "gemini-api",
        padrao: "gemini-3.5-flash-lite",
        modelos: &[
            Modelo {
                id: "gemini-3.5-flash-lite",
                nome: "Gemini 3.5 Flash-Lite — econômico (sugerido)",
                entrada: 0.30,
                saida: 2.50,
                longo: None,
                nota: "US$ 0,30 por milhão de tokens de entrada e 2,50 de saída. Tem plano grátis (veja os termos).",
            },
            Modelo {
                id: "gemini-3.1-flash-lite",
                nome: "Gemini 3.1 Flash-Lite — o mais barato",
                entrada: 0.25,
                saida: 1.50,
                longo: None,
                nota: "US$ 0,25 por milhão de tokens de entrada e 1,50 de saída. Tem plano grátis.",
            },
            Modelo {
                id: "gemini-3.8-flash",
                nome: "Gemini 3.8 Flash — melhor para agente",
                entrada: 0.75,
                saida: 3.75,
                longo: None,
                nota: "US$ 0,75 e 3,75 por milhão de tokens até 31/12/2026; a partir de 1/1/2027, 1,50 e 7,50. Tem plano grátis.",
            },
            Modelo {
                id: "gemini-4-hydrogen",
                nome: "Gemini 4 Hydrogen — código e agentes",
                entrada: 1.50,
                saida: 7.50,
                longo: None,
                nota: "US$ 1,50 por milhão de tokens de entrada e 7,50 de saída. Tem plano grátis.",
            },
        ],
        termos: "Termos da API do Gemini: o Google não reivindica o que é gerado. No plano grátis o Google usa o que você manda \
                 e as respostas para melhorar os produtos e pessoas podem ler (não mande nada pessoal ou secreto); no plano \
                 pago, não. Exige 18 anos ou mais.",
        url_termos: "https://ai.google.dev/gemini-api/terms",
        url_chave: "https://aistudio.google.com/apikey",
        url_precos: "https://ai.google.dev/gemini-api/docs/pricing",
    },
];

/// Teto de gasto de um "Pedir à IA" quando a janela não diz outro (US$).
pub const TETO_PADRAO_USD: f64 = 0.50;
/// Voltas de conversa no máximo num pedido (cada volta pode usar várias ferramentas).
pub const MAX_VOLTAS: usize = 40;
/// Tamanho máximo do resultado de uma ferramenta devolvido ao modelo (o resto é cortado).
const MAX_RESULTADO: usize = 12_000;
const VERSAO_ANTHROPIC: &str = "2026-10-21";

pub fn provedor(id: &str) -> Option<&'static Provedor> {
    PROVEDORES.iter().find(|p| p.id == id)
}

/// O modelo da tabela (com preço), se for um dos conhecidos.
pub fn modelo_da_tabela(p: &Provedor, id: &str) -> Option<&'static Modelo> {
    p.modelos.iter().find(|m| m.id == id)
}

fn modelo_valido(id: &str) -> bool {
    !id.is_empty() && id.len() <= 100 && id.chars().all(|c| c.is_ascii_alphanumeric() || "-._:@".contains(c))
}

/// Situação das APIs de cérebro (nunca mostra a chave).
pub fn estado(paths: &Paths) -> Value {
    let g = crate::apis::ler(paths);
    json!(PROVEDORES
        .iter()
        .map(|p| {
            let escolhido = g.modelos.get(p.id).cloned().unwrap_or_else(|| p.padrao.to_string());
            let tabela = modelo_da_tabela(p, &escolhido);
            json!({"id": p.id, "nome": p.nome, "termos": p.termos, "url_termos": p.url_termos, "url_chave": p.url_chave,
                   "url_precos": p.url_precos, "ligada": g.ligadas.iter().any(|x| x == p.id),
                   "tem_chave": g.chaves.get(p.id).is_some_and(|c| !c.is_empty()), "modelo": escolhido, "sugerido": p.padrao,
                   "preco": tabela.map(|m| m.nota).unwrap_or("Modelo fora da tabela da Fornalha: confira o preço na página de preços antes de usar. \
                                                              Sem o preço, o teto de gasto não tem como ser conferido (vale só o limite de voltas)."),
                   "modelos": p.modelos, "da_api": g.listas.get(p.id).cloned().unwrap_or_default()})
        })
        .collect::<Vec<_>>())
}

/// Liga/desliga, guarda (ou apaga, com texto vazio) a chave e escolhe o modelo. Só pela janela, pela pessoa.
/// Ligar um cérebro desliga o outro (um só conduz).
pub fn definir(paths: &Paths, id: &str, ligada: Option<bool>, chave: Option<String>, modelo: Option<String>) -> Resultado<Value> {
    let p = provedor(id).ok_or_else(|| Erro::argumento(format!("Cérebro por API desconhecido: {id}")))?;
    let mut g = crate::apis::ler(paths);
    if let Some(c) = chave {
        let c = c.trim().to_string();
        if c.is_empty() {
            g.chaves.remove(p.id);
            g.ligadas.retain(|x| x != p.id);
        } else {
            g.chaves.insert(p.id.to_string(), c);
        }
    }
    if let Some(m) = modelo {
        let m = m.trim().trim_start_matches("models/").to_string();
        if !modelo_valido(&m) {
            return Err(Erro::argumento(format!("Nome de modelo inválido: {m}")));
        }
        g.modelos.insert(p.id.to_string(), m);
    }
    if let Some(l) = ligada {
        g.ligadas.retain(|x| x != p.id);
        if l {
            if !g.chaves.get(p.id).is_some_and(|c| !c.is_empty()) {
                return Err(Erro::novo("api_sem_chave", format!("Ponha a chave do {} antes de ligar.", p.nome)));
            }
            g.ligadas.retain(|x| provedor(x).is_none());
            g.ligadas.push(p.id.to_string());
        }
    }
    crate::apis::gravar(paths, &g)?;
    Ok(estado(paths))
}

/// O cérebro por API ligado, com o modelo escolhido e a chave.
#[derive(Clone)]
pub struct Ativo {
    pub provedor: &'static Provedor,
    pub modelo: String,
    chave: String,
}

impl std::fmt::Debug for Ativo {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Ativo").field("provedor", &self.provedor.id).field("modelo", &self.modelo).finish_non_exhaustive()
    }
}

impl Ativo {
    /// Como aparece nos recibos e nos avisos.
    pub fn nome(&self) -> String {
        format!("{} ({})", self.modelo, self.provedor.nome)
    }
    fn tabela(&self) -> Option<&'static Modelo> {
        modelo_da_tabela(self.provedor, &self.modelo)
    }
}

pub fn ativo(paths: &Paths) -> Option<Ativo> {
    let g = crate::apis::ler(paths);
    PROVEDORES.iter().find_map(|p| {
        let chave = g.chaves.get(p.id).filter(|c| !c.is_empty())?;
        g.ligadas.iter().any(|x| x == p.id).then(|| Ativo {
            provedor: p,
            modelo: g.modelos.get(p.id).cloned().unwrap_or_else(|| p.padrao.to_string()),
            chave: chave.clone(),
        })
    })
}

// ---------------------------------------------------------------- o fio (curl do sistema)

fn base(id: &str) -> String {
    if let Some(b) = std::env::var("FORNALHA_CEREBRO_BASE").ok().filter(|b| !b.trim().is_empty()) {
        return b.trim_end_matches('/').to_string();
    }
    match id {
        "anthropic" => "https://api.anthropic.com".into(),
        _ => "https://generativelanguage.googleapis.com".into(),
    }
}

fn curl() -> std::path::PathBuf {
    if cfg!(windows) {
        let raiz = std::env::var_os("SystemRoot").map(std::path::PathBuf::from).unwrap_or_else(|| r"C:\Windows".into());
        let c = raiz.join("System32").join("curl.exe");
        if c.is_file() {
            return c;
        }
    }
    "curl".into()
}

/// Texto entre aspas no arquivo de configuração do curl.
fn aspas(s: &str) -> String {
    format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
}

/// Uma chamada HTTPS pelo curl. Devolve (código HTTP, corpo em JSON — ou o texto, se não for JSON).
async fn https(
    paths: &Paths,
    metodo: &str,
    url: &str,
    cabecalhos: &[(&str, &str)],
    corpo: Option<&Value>,
    segundos: u64,
) -> Resultado<(u16, Value)> {
    use tokio::io::AsyncWriteExt;
    let tmp = paths.data_dir.join("tmp");
    std::fs::create_dir_all(&tmp).map_err(|e| Erro::io(&tmp, e))?;
    let id = crate::util::id_aleatorio(6);
    let arq_corpo = tmp.join(format!("cerebro_{id}.pedido.json"));
    let arq_resposta = tmp.join(format!("cerebro_{id}.resposta.json"));
    let mut cfg = format!("url = {}\nrequest = {}\n", aspas(url), aspas(metodo));
    for (k, v) in cabecalhos {
        cfg += &format!("header = {}\n", aspas(&format!("{k}: {v}")));
    }
    if let Some(c) = corpo {
        std::fs::write(&arq_corpo, serde_json::to_vec(c).unwrap_or_default()).map_err(|e| Erro::io(&arq_corpo, e))?;
        cfg += "header = \"content-type: application/json\"\n";
        cfg += &format!("data-binary = {}\n", aspas(&format!("@{}", arq_corpo.to_string_lossy())));
    }
    cfg += &format!("output = {}\n", aspas(&arq_resposta.to_string_lossy()));
    cfg += &format!(
        "write-out = \"%{{http_code}}\"\nsilent\nshow-error\nmax-time = {segundos}\nconnect-timeout = 20\nnoproxy = \"127.0.0.1,localhost\"\n"
    );
    let mut cmd = tokio::process::Command::new(curl());
    cmd.args(["-K", "-"])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);
    crate::util::hide_console(&mut cmd);
    let mut filho = cmd.spawn().map_err(|e| {
        Erro::novo(
            "curl_ausente",
            format!("Não consegui rodar o curl do sistema ({e}). No Windows 10/11 ele já vem; no Linux, instale o curl."),
        )
    })?;
    if let Some(mut entrada) = filho.stdin.take() {
        let _ = entrada.write_all(cfg.as_bytes()).await;
    }
    let saida = tokio::time::timeout(Duration::from_secs(segundos + 30), filho.wait_with_output()).await;
    let _ = std::fs::remove_file(&arq_corpo);
    let bruto = std::fs::read(&arq_resposta).unwrap_or_default();
    let _ = std::fs::remove_file(&arq_resposta);
    let saida = saida
        .map_err(|_| Erro::novo("api_demorou", format!("A API não respondeu em {segundos} s.")))?
        .map_err(|e| Erro::novo("curl_ausente", format!("O curl falhou: {e}")))?;
    let codigo: u16 = String::from_utf8_lossy(&saida.stdout).trim().parse().unwrap_or(0);
    if codigo == 0 {
        let host = url.split('/').nth(2).unwrap_or(url);
        let erro = String::from_utf8_lossy(&saida.stderr).trim().to_string();
        return Err(Erro::novo("api_fora", format!("Não consegui falar com {host}: {erro}. A internet está ligada?")));
    }
    let v = serde_json::from_slice(&bruto).unwrap_or_else(|_| Value::String(String::from_utf8_lossy(&bruto).chars().take(400).collect()));
    Ok((codigo, v))
}

fn erro_da_api(p: &Provedor, codigo: u16, v: &Value) -> Erro {
    let msg = v["error"]["message"].as_str().or_else(|| v.as_str()).unwrap_or("sem detalhe").to_string();
    let baixo = msg.to_lowercase();
    let dica = if codigo == 401 || (codigo == 403 && p.id == "anthropic") || baixo.contains("api key not valid") {
        " A chave foi recusada: confira em Agentes → Cérebro por API."
    } else if codigo == 402 || baixo.contains("credit balance") || baixo.contains("billing") {
        " Sem créditos na conta: confira o saldo na página da API."
    } else if codigo == 429 {
        " Limite de pedidos por minuto (ou de créditos): espere um pouco e peça de novo."
    } else if codigo == 404 {
        " Esse modelo não existe para a sua chave: escolha outro (ou atualize a lista)."
    } else if codigo >= 500 {
        " O serviço está sobrecarregado: tente de novo em instantes."
    } else {
        ""
    };
    Erro::novo("api_cerebro_recusou", format!("A API {} respondeu {codigo}: {msg}.{dica}", p.nome))
}

/// POST com até duas novas tentativas quando o serviço está ocupado (429, 5xx).
async fn postar(paths: &Paths, a: &Ativo, url: &str, corpo: &Value) -> Resultado<Value> {
    let cab: Vec<(&str, &str)> = match a.provedor.id {
        "anthropic" => vec![("x-api-key", a.chave.as_str()), ("anthropic-version", VERSAO_ANTHROPIC)],
        _ => vec![("x-goog-api-key", a.chave.as_str())],
    };
    let mut espera = 5;
    for tentativa in 0..3 {
        let (codigo, v) = https(paths, "POST", url, &cab, Some(corpo), 600).await?;
        if (200..300).contains(&codigo) {
            return Ok(v);
        }
        if tentativa < 2 && (codigo == 429 || codigo >= 500) {
            tokio::time::sleep(Duration::from_secs(espera)).await;
            espera *= 3;
            continue;
        }
        return Err(erro_da_api(a.provedor, codigo, &v));
    }
    unreachable!("o laço sempre devolve")
}

/// Lista os modelos que a chave enxerga (botão "Atualizar lista") e guarda.
pub async fn atualizar_modelos(paths: &Paths, id: &str) -> Resultado<Value> {
    let p = provedor(id).ok_or_else(|| Erro::argumento(format!("Cérebro por API desconhecido: {id}")))?;
    let g = crate::apis::ler(paths);
    let chave = g
        .chaves
        .get(p.id)
        .filter(|c| !c.is_empty())
        .cloned()
        .ok_or_else(|| Erro::novo("api_sem_chave", format!("Ponha a chave do {} antes de atualizar a lista.", p.nome)))?;
    let ids: Vec<String> = if p.id == "anthropic" {
        let url = format!("{}/v1/models?limit=100", base(p.id));
        let (c, v) = https(paths, "GET", &url, &[("x-api-key", chave.as_str()), ("anthropic-version", VERSAO_ANTHROPIC)], None, 60).await?;
        if !(200..300).contains(&c) {
            return Err(erro_da_api(p, c, &v));
        }
        v["data"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|m| m["id"].as_str())
            .filter(|i| i.starts_with("claude-"))
            .map(String::from)
            .collect()
    } else {
        let url = format!("{}/v1beta/models?pageSize=1000", base(p.id));
        let (c, v) = https(paths, "GET", &url, &[("x-goog-api-key", chave.as_str())], None, 60).await?;
        if !(200..300).contains(&c) {
            return Err(erro_da_api(p, c, &v));
        }
        const FORA: [&str; 10] = ["image", "tts", "live", "embedding", "robotics", "transcribe", "translate", "audio", "decision", "omni"];
        v["models"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|m| m["supportedGenerationMethods"].as_array().is_none_or(|g| g.iter().any(|x| x == "generateContent")))
            .filter_map(|m| m["name"].as_str())
            .map(|n| n.trim_start_matches("models/").to_string())
            .filter(|n| n.starts_with("gemini-") && !FORA.iter().any(|f| n.contains(f)))
            .collect()
    };
    let mut g = crate::apis::ler(paths);
    g.listas.insert(p.id.to_string(), ids.into_iter().filter(|i| modelo_valido(i)).collect());
    crate::apis::gravar(paths, &g)?;
    Ok(estado(paths))
}

// ---------------------------------------------------------------- gasto

/// Tokens e dinheiro de um pedido (o dinheiro só para os modelos da tabela).
#[derive(Debug, Clone, Copy, Default, Serialize)]
pub struct Gasto {
    pub entrada: u64,
    pub saida: u64,
    pub cache_lida: u64,
    pub cache_escrita: u64,
    pub usd: f64,
    /// false: o modelo não está na tabela e o dinheiro não foi contado.
    pub com_preco: bool,
}

impl Gasto {
    fn somar(&mut self, outro: Gasto) {
        self.entrada += outro.entrada;
        self.saida += outro.saida;
        self.cache_lida += outro.cache_lida;
        self.cache_escrita += outro.cache_escrita;
        self.usd += outro.usd;
        self.com_preco = outro.com_preco;
    }
}

fn gasto_de(a: &Ativo, uso: &Value) -> Gasto {
    let n = |v: &Value| v.as_u64().unwrap_or(0);
    let (entrada, saida, cache_lida, cache_escrita) = if a.provedor.id == "anthropic" {
        (n(&uso["input_tokens"]), n(&uso["output_tokens"]), n(&uso["cache_read_input_tokens"]), n(&uso["cache_creation_input_tokens"]))
    } else {
        // no Gemini o pensamento é cobrado como saída; o cache implícito é contado como entrada cheia (por cima)
        (n(&uso["promptTokenCount"]), n(&uso["candidatesTokenCount"]) + n(&uso["thoughtsTokenCount"]), 0, 0)
    };
    let mut g = Gasto { entrada, saida, cache_lida, cache_escrita, usd: 0.0, com_preco: false };
    if let Some(m) = a.tabela() {
        let pedido = entrada + cache_lida + cache_escrita;
        let (pe, ps) = match m.longo {
            Some((limite, e, s)) if pedido > limite => (e, s),
            _ => (m.entrada, m.saida),
        };
        g.usd = (entrada as f64 * pe + cache_escrita as f64 * pe * 1.25 + cache_lida as f64 * pe * 0.1 + saida as f64 * ps) / 1e6;
        g.com_preco = true;
    }
    g
}

// ---------------------------------------------------------------- JSON (ficha, plano)

fn tem_objeto_livre(esquema: &Value) -> bool {
    match esquema {
        Value::Object(o) => {
            let objeto = o.get("type").and_then(Value::as_str) == Some("object");
            if objeto && (o.get("properties").is_none() || o.get("additionalProperties") != Some(&Value::Bool(false))) {
                return true;
            }
            o.values().any(tem_objeto_livre)
        }
        Value::Array(a) => a.iter().any(tem_objeto_livre),
        _ => false,
    }
}

/// Tira o que a saída em JSON da Anthropic não aceita (limites de número, de texto e de lista).
fn esquema_para_formato(esquema: &Value) -> Value {
    match esquema {
        Value::Object(o) => Value::Object(
            o.iter()
                .filter(|(k, _)| {
                    !matches!(k.as_str(), "minimum" | "maximum" | "multipleOf" | "minLength" | "maxLength" | "minItems" | "maxItems")
                })
                .map(|(k, v)| (k.clone(), esquema_para_formato(v)))
                .collect(),
        ),
        Value::Array(a) => Value::Array(a.iter().map(esquema_para_formato).collect()),
        outro => outro.clone(),
    }
}

fn json_do_texto(texto: &str) -> Resultado<Value> {
    let inicio = texto.find('{').unwrap_or(0);
    let fim = texto.rfind('}').map(|i| i + 1).unwrap_or(texto.len());
    serde_json::from_str(texto.get(inicio..fim).unwrap_or("")).map_err(|e| {
        Erro::novo(
            "cerebro_respondeu_errado",
            format!("O cérebro não devolveu JSON válido ({e}): {}", texto.chars().take(300).collect::<String>()),
        )
    })
}

fn texto_anthropic(r: &Value) -> String {
    r["content"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|b| b["type"] == "text")
        .filter_map(|b| b["text"].as_str())
        .collect::<Vec<_>>()
        .join("\n")
}

fn texto_gemini(r: &Value) -> String {
    r["candidates"][0]["content"]["parts"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|p| p["thought"] != true)
        .filter_map(|p| p["text"].as_str())
        .collect::<Vec<_>>()
        .join("\n")
}

/// Conversa pedindo uma resposta que siga o esquema JSON (como `ignis::conversar_json`).
pub async fn conversar_json(paths: &Paths, a: &Ativo, sistema: &str, pedido: &str, esquema: &Value) -> Resultado<(Value, Gasto)> {
    let conhecido = a.tabela().is_some();
    if a.provedor.id == "anthropic" {
        let url = format!("{}/v1/messages", base("anthropic"));
        let mut corpo = json!({"model": a.modelo, "max_tokens": 8000, "system": sistema,
                               "messages": [{"role": "user", "content": pedido}]});
        if conhecido {
            corpo["output_config"] = json!({"effort": "low"});
            if !tem_objeto_livre(esquema) {
                corpo["output_config"]["format"] = json!({"type": "json_schema", "schema": esquema_para_formato(esquema)});
            }
        }
        let r = match postar(paths, a, &url, &corpo).await {
            Ok(r) => r,
            // o esquema não serviu para a saída em JSON: pede de novo só pelo texto
            Err(e) if e.mensagem.contains(" 400:") && corpo["output_config"].get("format").is_some() => {
                corpo["output_config"].as_object_mut().map(|o| o.remove("format"));
                postar(paths, a, &url, &corpo).await?
            }
            Err(e) => return Err(e),
        };
        if r["stop_reason"] == "refusal" {
            return Err(Erro::novo("cerebro_recusou", "O modelo recusou o pedido (filtro de segurança da Anthropic)."));
        }
        Ok((json_do_texto(&texto_anthropic(&r))?, gasto_de(a, &r["usage"])))
    } else {
        let url = format!("{}/v1beta/models/{}:generateContent", base("gemini"), a.modelo);
        let mut corpo = json!({"systemInstruction": {"parts": [{"text": sistema}]},
                               "contents": [{"role": "user", "parts": [{"text": pedido}]}],
                               "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": esquema, "maxOutputTokens": 8000}});
        let r = match postar(paths, a, &url, &corpo).await {
            Ok(r) => r,
            Err(e) if e.mensagem.contains(" 400:") => {
                corpo["generationConfig"].as_object_mut().map(|o| o.remove("responseJsonSchema"));
                postar(paths, a, &url, &corpo).await?
            }
            Err(e) => return Err(e),
        };
        Ok((json_do_texto(&texto_gemini(&r))?, gasto_de(a, &r["usageMetadata"])))
    }
}

/// O cérebro que a Fornalha usa para escrever JSON: o Ignis aberto com modelo de conversa (local, grátis)
/// ou, sem ele, a API ligada pela pessoa.
pub enum Cerebro {
    Ignis,
    Api(Ativo),
}

impl Cerebro {
    pub fn nome(&self) -> String {
        match self {
            Cerebro::Ignis => "Ignis".into(),
            Cerebro::Api(a) => a.nome(),
        }
    }

    /// Para os recibos: "ignis" ou "api:<modelo>".
    pub fn id(&self) -> String {
        match self {
            Cerebro::Ignis => "ignis".into(),
            Cerebro::Api(a) => format!("api:{}", a.modelo),
        }
    }

    pub async fn conversar_json(&self, f: &Fornalha, sistema: &str, pedido: &str, esquema: &Value) -> Resultado<Value> {
        match self {
            Cerebro::Ignis => crate::ignis::conversar_json(f.porta_ignis(), None, sistema, pedido, esquema).await,
            Cerebro::Api(a) => conversar_json(&f.paths, a, sistema, pedido, esquema).await.map(|(v, _)| v),
        }
    }
}

pub async fn qual(f: &Fornalha) -> Option<Cerebro> {
    let cap = crate::ignis::capacidades(f.porta_ignis()).await;
    if cap["conectado"] == true && cap["conversa"].as_array().is_some_and(|v| !v.is_empty()) {
        return Some(Cerebro::Ignis);
    }
    ativo(&f.paths).map(Cerebro::Api)
}

// ---------------------------------------------------------------- "Pedir à IA" (o modelo conduz as ferramentas)

/// O que o modelo lê antes de tudo (fixo, para o cache da API valer entre as voltas).
pub const SISTEMA_DO_AGENTE: &str = "Você é o cérebro da Fornalha 3D, a bancada de quem faz jogos. A pessoa escreveu um pedido \
na janela; faça o pedido usando as ferramentas da Fornalha, uma etapa por vez, e no fim diga em português do Brasil, \
curto, o que foi feito, onde ficou e o que falta (se faltar).

Como trabalhar:
- Se não souber o estado, comece por get_status (projeto aberto, placa, programas, motores).
- Trabalhe no projeto aberto; só crie outro se a pessoa pedir. Siga a bíblia do jogo (estilo, paleta, câmera).
- Não invente caminho de arquivo: use os que as ferramentas devolveram.
- Se uma ferramenta der erro, leia a mensagem: corrija o argumento e tente de novo uma vez, ou explique o que a pessoa \
precisa fazer.
- Aceite de licença, receita do estúdio e chaves são só da pessoa, pela janela: se faltar, diga onde ela clica.
- Seja econômico: não repita a mesma chamada à toa e não peça o que já sabe.

Movimento (vale para luta e para tudo: andar, pegar, sentar, colher, nadar, gesto):
- Um corpo humano tem 2 braços, 2 pernas e 5 dedos em cada mão (o polegar com 2 juntas que dobram, os outros com 3).
- A animação não tem física: o equilíbrio, o peso e o contato são você que garante. O quadril fica sobre os pés \
quando o personagem está parado; o pé que pisa não escorrega; nada atravessa o chão nem o próprio corpo.
- Cotovelo e joelho dobram para um lado só; dedo só fecha para a palma; nada torce além do limite do osso.
- Fluido: o movimento começa e termina devagar (entrada e saída), tem antecipação antes do golpe e continuação \
depois, sem tranco de um quadro para o outro; o ciclo de andar e correr fecha no mesmo quadro em que começa.
- Prefira as capturas do banco (list_motions, apply_motion) a inventar do zero; depois confira com check_motion e \
corrija com edit_motion o que a conferência reprovar. \"Aprovado\" quer dizer que a régua não achou o que ela mede: \
olhe as folhas do show_motion antes de dizer que ficou bom.";

/// Estado do "Pedir à IA" (um por vez), lido pela janela.
#[derive(Default)]
pub struct Conversa {
    estado: std::sync::Mutex<Value>,
    parar: AtomicBool,
}

impl Conversa {
    pub fn ver(&self) -> Value {
        let e = self.estado.lock().map(|e| e.clone()).unwrap_or(Value::Null);
        if e.is_null() {
            json!({"rodando": false, "passos": []})
        } else {
            e
        }
    }

    pub fn parar(&self) {
        self.parar.store(true, Ordering::Relaxed);
        self.anotar("aviso", "Parando a pedido da pessoa (termina a ferramenta que está rodando).");
    }

    fn parado(&self) -> bool {
        self.parar.load(Ordering::Relaxed)
    }

    fn anotar(&self, tipo: &str, texto: &str) {
        if let Ok(mut e) = self.estado.lock() {
            if let Some(p) = e["passos"].as_array_mut() {
                if p.len() >= 400 {
                    p.remove(0);
                }
                p.push(json!({"tipo": tipo, "texto": texto.chars().take(1500).collect::<String>(), "quando": crate::util::agora_iso()}));
            }
        }
    }

    fn gasto(&self, g: &Gasto) {
        if let Ok(mut e) = self.estado.lock() {
            e["gasto"] = json!(g);
        }
    }

    fn terminar(&self, resposta: Option<String>, erro: Option<String>) {
        if let Ok(mut e) = self.estado.lock() {
            e["rodando"] = json!(false);
            e["terminou"] = json!(crate::util::agora_iso());
            if let Some(r) = resposta {
                e["resposta"] = json!(r);
            }
            if let Some(x) = erro {
                e["erro"] = json!(x);
            }
        }
    }
}

fn cortar(texto: &str, max: usize) -> String {
    if texto.len() <= max {
        return texto.to_string();
    }
    let mut fim = max;
    while !texto.is_char_boundary(fim) {
        fim -= 1;
    }
    format!("{} …(cortado: {} caracteres a mais)", &texto[..fim], texto.len() - fim)
}

fn resumo_args(v: &Value) -> String {
    cortar(&v.to_string(), 300)
}

async fn usar_ferramenta(f: &Fornalha, c: &Conversa, nome: &str, args: Value, quem: &str) -> (String, bool) {
    c.anotar("ferramenta", &format!("{nome} {}", resumo_args(&args)));
    let r = match crate::ferramentas::chamar(f, nome, args, quem).await {
        Ok(v) => (cortar(&v.to_string(), MAX_RESULTADO), false),
        Err(e) => (format!("{}: {}", e.codigo, e.mensagem), true),
    };
    c.anotar(if r.1 { "erro" } else { "resultado" }, &cortar(&r.0, 600));
    r
}

/// Começa um "Pedir à IA" em segundo plano. Só a janela chama (gasta o dinheiro da pessoa).
pub fn pedir(f: Arc<Fornalha>, pedido: &str, teto_usd: Option<f64>) -> Resultado<Value> {
    let pedido = pedido.trim().to_string();
    if pedido.is_empty() {
        return Err(Erro::argumento("Escreva o pedido (ex.: \"faça um ferreiro que martela na bigorna e confira o movimento\")."));
    }
    let a = ativo(&f.paths).ok_or_else(|| {
        Erro::novo("sem_cerebro_api", "Ligue o Claude ou o Gemini em Agentes → Cérebro por API (com a chave) antes de pedir.")
    })?;
    let teto = teto_usd.filter(|t| t.is_finite() && *t > 0.0).unwrap_or(TETO_PADRAO_USD).min(20.0);
    {
        let c = f.conversa_ia();
        let mut e = c.estado.lock().map_err(|_| Erro::novo("interno", "estado do pedido travado"))?;
        if e["rodando"] == true {
            return Err(Erro::novo("pedido_rodando", "Já tem um pedido rodando: espere terminar ou clique em Parar."));
        }
        c.parar.store(false, Ordering::Relaxed);
        *e = json!({"rodando": true, "pedido": pedido, "provedor": a.provedor.id, "modelo": a.modelo, "teto_usd": teto,
                    "com_preco": a.tabela().is_some(), "comecou": crate::util::agora_iso(), "passos": [], "gasto": Gasto::default()});
    }
    let f2 = f.clone();
    tokio::spawn(async move {
        let c = f2.conversa_ia();
        let r = if a.provedor.id == "anthropic" {
            laco_anthropic(&f2, c, &a, &pedido, teto).await
        } else {
            laco_gemini(&f2, c, &a, &pedido, teto).await
        };
        match r {
            Ok(resposta) => c.terminar(Some(resposta), None),
            Err(e) => {
                c.anotar("erro", &e.mensagem);
                c.terminar(None, Some(e.mensagem));
            }
        }
    });
    Ok(f.conversa_ia().ver())
}

/// Confere o teto depois de cada volta. Devolve o aviso se passou.
fn passou_do_teto(g: &Gasto, teto: f64) -> Option<String> {
    (g.com_preco && g.usd >= teto)
        .then(|| format!("Parei no teto de gasto deste pedido (US$ {teto:.2}; gasto US$ {:.4}). Peça de novo para continuar.", g.usd))
}

async fn laco_anthropic(f: &Fornalha, c: &Conversa, a: &Ativo, pedido: &str, teto: f64) -> Resultado<String> {
    let url = format!("{}/v1/messages", base("anthropic"));
    let ferramentas: Vec<Value> = crate::ferramentas::lista()
        .into_iter()
        .map(|t| json!({"name": t.nome, "description": t.descricao, "input_schema": t.esquema}))
        .collect();
    let quem = format!("cerebro-api:{}", a.modelo);
    let mut mensagens = vec![json!({"role": "user", "content": pedido})];
    let mut gasto = Gasto::default();
    let mut resposta = String::new();
    for _ in 0..MAX_VOLTAS {
        if c.parado() {
            return Ok(format!("{resposta}\n(parado pela pessoa)").trim().to_string());
        }
        let mut corpo = json!({"model": a.modelo, "max_tokens": 16000, "system": SISTEMA_DO_AGENTE, "tools": ferramentas,
                               "messages": mensagens, "cache_control": {"type": "ephemeral"}});
        if a.tabela().is_some() {
            corpo["output_config"] = json!({"effort": "medium"});
        }
        let r = postar(&f.paths, a, &url, &corpo).await?;
        gasto.somar(gasto_de(a, &r["usage"]));
        c.gasto(&gasto);
        let conteudo = r["content"].clone();
        // a resposta inteira volta para a conversa (com os blocos de pensamento, sem mexer)
        mensagens.push(json!({"role": "assistant", "content": conteudo}));
        let texto = texto_anthropic(&r);
        if !texto.trim().is_empty() {
            c.anotar("texto", &texto);
            resposta = texto;
        }
        match r["stop_reason"].as_str().unwrap_or("") {
            "tool_use" => {
                let mut resultados = Vec::new();
                for b in conteudo.as_array().into_iter().flatten().filter(|b| b["type"] == "tool_use") {
                    if c.parado() {
                        resultados.push(
                            json!({"type": "tool_result", "tool_use_id": b["id"], "content": "Parado pela pessoa.", "is_error": true}),
                        );
                        continue;
                    }
                    let (txt, erro) = usar_ferramenta(f, c, b["name"].as_str().unwrap_or(""), b["input"].clone(), &quem).await;
                    resultados.push(json!({"type": "tool_result", "tool_use_id": b["id"], "content": txt, "is_error": erro}));
                }
                mensagens.push(json!({"role": "user", "content": resultados}));
            }
            "pause_turn" => {}
            "refusal" => {
                c.anotar("aviso", "O modelo recusou continuar (filtro de segurança da Anthropic).");
                return Ok(resposta);
            }
            "max_tokens" => {
                c.anotar("aviso", "A resposta passou do tamanho máximo e foi cortada.");
                return Ok(resposta);
            }
            _ => return Ok(resposta),
        }
        if let Some(aviso) = passou_do_teto(&gasto, teto) {
            c.anotar("aviso", &aviso);
            return Ok(format!("{resposta}\n{aviso}").trim().to_string());
        }
    }
    let aviso = format!("Parei depois de {MAX_VOLTAS} voltas. Peça de novo para continuar.");
    c.anotar("aviso", &aviso);
    Ok(format!("{resposta}\n{aviso}").trim().to_string())
}

async fn laco_gemini(f: &Fornalha, c: &Conversa, a: &Ativo, pedido: &str, teto: f64) -> Resultado<String> {
    let url = format!("{}/v1beta/models/{}:generateContent", base("gemini"), a.modelo);
    let declaracoes: Vec<Value> = crate::ferramentas::lista()
        .into_iter()
        .map(|t| json!({"name": t.nome, "description": t.descricao, "parametersJsonSchema": t.esquema}))
        .collect();
    let quem = format!("cerebro-api:{}", a.modelo);
    let mut conteudos = vec![json!({"role": "user", "parts": [{"text": pedido}]})];
    let mut gasto = Gasto::default();
    let mut resposta = String::new();
    for _ in 0..MAX_VOLTAS {
        if c.parado() {
            return Ok(format!("{resposta}\n(parado pela pessoa)").trim().to_string());
        }
        let corpo = json!({"systemInstruction": {"parts": [{"text": SISTEMA_DO_AGENTE}]}, "contents": conteudos,
                           "tools": [{"functionDeclarations": declaracoes}], "generationConfig": {"maxOutputTokens": 16000}});
        let r = postar(&f.paths, a, &url, &corpo).await?;
        gasto.somar(gasto_de(a, &r["usageMetadata"]));
        c.gasto(&gasto);
        let candidato = &r["candidates"][0];
        let Some(conteudo) = candidato.get("content").filter(|v| v["parts"].is_array()) else {
            let motivo =
                candidato["finishReason"].as_str().or_else(|| r["promptFeedback"]["blockReason"].as_str()).unwrap_or("sem resposta");
            c.anotar("aviso", &format!("O Gemini não respondeu ({motivo})."));
            return Ok(resposta);
        };
        // a parte volta inteira (com a assinatura do pensamento, sem mexer)
        conteudos.push(conteudo.clone());
        let texto = texto_gemini(&r);
        if !texto.trim().is_empty() {
            c.anotar("texto", &texto);
            resposta = texto;
        }
        let chamadas: Vec<Value> =
            conteudo["parts"].as_array().into_iter().flatten().filter_map(|p| p.get("functionCall").cloned()).collect();
        if chamadas.is_empty() {
            let fim = candidato["finishReason"].as_str().unwrap_or("STOP");
            if fim != "STOP" {
                c.anotar("aviso", &format!("O Gemini parou: {fim}."));
            }
            return Ok(resposta);
        }
        let mut partes = Vec::new();
        for ch in chamadas {
            let nome = ch["name"].as_str().unwrap_or("").to_string();
            let (txt, erro) = if c.parado() {
                ("Parado pela pessoa.".to_string(), true)
            } else {
                usar_ferramenta(f, c, &nome, ch["args"].clone(), &quem).await
            };
            let mut fr = json!({"name": nome, "response": if erro { json!({"erro": txt}) } else { json!({"resultado": txt}) }});
            if let Some(id) = ch.get("id") {
                fr["id"] = id.clone();
            }
            partes.push(json!({"functionResponse": fr}));
        }
        conteudos.push(json!({"role": "user", "parts": partes}));
        if let Some(aviso) = passou_do_teto(&gasto, teto) {
            c.anotar("aviso", &aviso);
            return Ok(format!("{resposta}\n{aviso}").trim().to_string());
        }
    }
    let aviso = format!("Parei depois de {MAX_VOLTAS} voltas. Peça de novo para continuar.");
    c.anotar("aviso", &aviso);
    Ok(format!("{resposta}\n{aviso}").trim().to_string())
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn liga_so_com_chave_um_por_vez_e_nao_mostra_a_chave() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = Paths::under(tmp.path());
        assert!(ativo(&paths).is_none(), "desligado por padrão");
        assert_eq!(definir(&paths, "anthropic", Some(true), None, None).unwrap_err().codigo, "api_sem_chave");
        let e = definir(&paths, "anthropic", Some(true), Some("sk-segredo-1".into()), None).unwrap();
        assert!(!e.to_string().contains("sk-segredo-1"), "a chave nunca aparece no estado");
        assert_eq!(e[0]["ligada"], true);
        assert_eq!(e[0]["modelo"], "claude-haiku-5-5", "sugestão econômica");
        assert_eq!(ativo(&paths).unwrap().modelo, "claude-haiku-5-5");
        // ligar o Gemini desliga o Claude
        definir(&paths, "gemini", None, Some("g-segredo".into()), Some("models/gemini-3.8-flash".into())).unwrap();
        let e = definir(&paths, "gemini", Some(true), None, None).unwrap();
        assert_eq!(e[0]["ligada"], false);
        assert_eq!(e[1]["ligada"], true);
        assert_eq!(e[1]["modelo"], "gemini-3.8-flash");
        let a = ativo(&paths).unwrap();
        assert_eq!((a.provedor.id, a.modelo.as_str()), ("gemini", "gemini-3.8-flash"));
        assert!(!format!("{a:?}").contains("g-segredo"));
        assert!(definir(&paths, "gemini", None, None, Some("x; rm -rf".into())).is_err());
        // apagar a chave desliga
        definir(&paths, "gemini", None, Some(String::new()), None).unwrap();
        assert!(ativo(&paths).is_none());
        // as APIs de 3D continuam desligadas
        assert!(crate::apis::ligada_3d(&paths).is_none());
    }

    #[test]
    fn gasto_pela_tabela() {
        let p = provedor("anthropic").unwrap();
        let a = Ativo { provedor: p, modelo: "claude-haiku-5-5".into(), chave: String::new() };
        // até 100 mil tokens no pedido: US$ 0,10 / 0,50 por milhão
        let g = gasto_de(&a, &json!({"input_tokens": 100_000, "output_tokens": 1_000_000}));
        assert!(g.com_preco && (g.usd - 0.51).abs() < 1e-9, "{g:?}");
        // pedido acima de 100 mil tokens: o preço maior
        let g = gasto_de(&a, &json!({"input_tokens": 200_000, "output_tokens": 0}));
        assert!((g.usd - 0.10).abs() < 1e-9, "{g:?}");
        // cache lido custa 10%
        let g = gasto_de(&a, &json!({"input_tokens": 0, "cache_read_input_tokens": 50_000, "output_tokens": 0}));
        assert!((g.usd - 0.0005).abs() < 1e-9, "{g:?}");
        let gm = Ativo { provedor: provedor("gemini").unwrap(), modelo: "gemini-3.5-flash-lite".into(), chave: String::new() };
        let g = gasto_de(&gm, &json!({"promptTokenCount": 1_000_000, "candidatesTokenCount": 500_000, "thoughtsTokenCount": 500_000}));
        assert!((g.usd - 2.80).abs() < 1e-9, "{g:?}");
        let fora = Ativo { provedor: p, modelo: "claude-modelo-novo".into(), chave: String::new() };
        assert!(!gasto_de(&fora, &json!({"input_tokens": 10})).com_preco);
        assert!(passou_do_teto(&Gasto { usd: 0.6, com_preco: true, ..Default::default() }, 0.5).is_some());
        assert!(passou_do_teto(&Gasto { usd: 9.0, com_preco: false, ..Default::default() }, 0.5).is_none());
    }

    #[test]
    fn esquema_com_objeto_livre_nao_vai_como_formato() {
        let livre = json!({"type": "object", "additionalProperties": false, "properties": {"argumentos": {"type": "object"}}});
        assert!(tem_objeto_livre(&livre));
        let fechado = json!({"type": "object", "additionalProperties": false, "properties": {"n": {"type": "integer", "minimum": 1}}, "required": ["n"]});
        assert!(!tem_objeto_livre(&fechado));
        assert!(esquema_para_formato(&fechado)["properties"]["n"].get("minimum").is_none());
    }

    #[test]
    fn configuracao_do_curl_escapa_caminhos() {
        assert_eq!(aspas(r#"C:\Users\a "b""#), r#""C:\\Users\\a \"b\"""#);
        assert!(cortar(&"á".repeat(10), 5).contains("cortado"));
    }

    #[test]
    fn cada_cerebro_tem_licenca_no_manifesto() {
        let c = crate::licencas::Catalogo::embutido();
        for p in &PROVEDORES {
            let m = c.modelo(p.manifesto).unwrap_or_else(|| panic!("{} fora do manifesto", p.manifesto));
            assert_eq!(m.funcao, "cerebro");
            assert!(modelo_da_tabela(p, p.padrao).is_some(), "a sugestão tem preço na tabela");
        }
    }

    #[test]
    fn o_agente_conhece_as_regras_do_corpo() {
        for t in ["5 dedos", "não tem física", "dobram para um lado só", "check_motion", "pela janela"] {
            assert!(SISTEMA_DO_AGENTE.contains(t), "falta no sistema: {t}");
        }
        assert!(SISTEMA_DO_AGENTE.contains("polegar"));
    }
}
