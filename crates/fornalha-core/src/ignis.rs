//! O Ignis é o motor local de IA (o cérebro da Fornalha). Aqui só lemos o
//! estado dele pela API local; nada sai do computador.

use std::time::Duration;

use serde::Serialize;
use serde_json::Value;

#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct EstadoIgnis {
    pub conectado: bool,
    pub endereco: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub versao: Option<String>,
    /// Fase do motor em texto ("Pronto", "Carregando"...).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fase: Option<String>,
    /// Modelo carregado agora.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub modelo: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub erro: Option<String>,
}

fn cliente() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_millis(1500))
        .connect_timeout(Duration::from_millis(800))
        .no_proxy()
        .user_agent(crate::consts::USER_AGENT)
        .build()
        .expect("cliente HTTP simples")
}

/// Pergunta ao Ignis (em 127.0.0.1) como ele está. Nunca espera mais de ~2 s.
pub async fn consultar(porta: u16) -> EstadoIgnis {
    let endereco = format!("http://127.0.0.1:{porta}");
    let http = cliente();
    let estado = match http.get(format!("{endereco}/motor/estado")).send().await {
        Ok(r) if r.status().is_success() => r.json::<Value>().await.unwrap_or(Value::Null),
        Ok(r) => {
            return EstadoIgnis { endereco, erro: Some(format!("O Ignis respondeu {}.", r.status())), ..Default::default() };
        }
        Err(_) => {
            return EstadoIgnis {
                endereco,
                erro: Some("O Ignis não está aberto (ou usa outra porta). O cérebro do app roda nele.".into()),
                ..Default::default()
            };
        }
    };
    let versao = match http.get(format!("{endereco}/motor/versao")).send().await {
        Ok(r) => r.json::<Value>().await.ok().and_then(|v| v["app"]["versao"].as_str().map(String::from)),
        Err(_) => None,
    };
    let texto = |v: &Value| v.as_str().map(String::from);
    EstadoIgnis {
        conectado: true,
        endereco,
        versao,
        fase: texto(&estado["fase_texto"]).or_else(|| texto(&estado["fase"])),
        modelo: texto(&estado["modelo"]["nome"]).or_else(|| texto(&estado["modelo"]["modelo_nome"])),
        erro: None,
    }
}

/// Guarda a última resposta do Ignis por um tempo, para as telas não esperarem a cada clique.
pub struct Cache {
    validade: Duration,
    ultimo: tokio::sync::Mutex<Option<(std::time::Instant, u16, EstadoIgnis)>>,
}

impl Cache {
    pub fn new(validade: Duration) -> Self {
        Self { validade, ultimo: tokio::sync::Mutex::new(None) }
    }

    pub async fn consultar(&self, porta: u16) -> EstadoIgnis {
        let mut u = self.ultimo.lock().await;
        if let Some((quando, p, e)) = u.as_ref() {
            if *p == porta && quando.elapsed() < self.validade {
                return e.clone();
            }
        }
        let e = consultar(porta).await;
        *u = Some((std::time::Instant::now(), porta, e.clone()));
        e
    }
}

// ---------------- geração pelo Ignis (0.4.0) ----------------

fn cliente_geracao(segundos: u64) -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(segundos))
        .connect_timeout(Duration::from_secs(3))
        .no_proxy()
        .user_agent(crate::consts::USER_AGENT)
        .build()
        .expect("cliente HTTP simples")
}

fn erro_do_ignis(status: reqwest::StatusCode, corpo: &Value) -> crate::erro::Erro {
    let msg = corpo["erro"].as_str().or_else(|| corpo["error"]["message"].as_str()).unwrap_or("sem detalhe");
    let codigo = corpo["error"]["code"].as_str().unwrap_or("");
    let dica = match codigo {
        "audio_nao_preparado" => " Abra o Ignis e prepare a voz/imagem (ou peça à Fornalha para preparar).",
        "placa_reservada" => " A placa está reservada por outra geração; tente de novo em instantes.",
        "sem_modelo" | "sem_motor" => " Abra o Ignis e clique em Preparar.",
        _ => "",
    };
    crate::erro::Erro::novo("ignis_recusou", format!("O Ignis respondeu {status}: {msg}.{dica}"))
}

async fn post_json(porta: u16, rota: &str, corpo: &Value, segundos: u64) -> crate::erro::Resultado<Value> {
    let url = format!("http://127.0.0.1:{porta}{rota}");
    let r =
        cliente_geracao(segundos).post(&url).json(corpo).send().await.map_err(|e| {
            crate::erro::Erro::novo("ignis_fora", format!("Não consegui falar com o Ignis em {url}: {e}. Ele está aberto?"))
        })?;
    let status = r.status();
    let v: Value = r.json().await.unwrap_or(Value::Null);
    if !status.is_success() {
        return Err(erro_do_ignis(status, &v));
    }
    Ok(v)
}

/// Conversa com o cérebro pedindo uma resposta que siga o esquema JSON.
pub async fn conversar_json(
    porta: u16,
    modelo: Option<&str>,
    sistema: &str,
    pedido: &str,
    esquema: &Value,
) -> crate::erro::Resultado<Value> {
    let corpo = serde_json::json!({
        "model": modelo.unwrap_or("default"),
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": pedido}],
        "temperature": 0.6,
        "max_tokens": 900,
        "response_format": {"type": "json_schema", "json_schema": {"name": "resposta", "strict": true, "schema": esquema}},
    });
    let v = post_json(porta, "/v1/chat/completions", &corpo, 300).await?;
    let texto = v["choices"][0]["message"]["content"].as_str().unwrap_or("");
    // Modelos pensantes (Qwen3) podem mandar <think>...</think> antes do JSON.
    let limpo = match texto.rfind("</think>") {
        Some(i) => &texto[i + 8..],
        None => texto,
    };
    let inicio = limpo.find('{').unwrap_or(0);
    let fim = limpo.rfind('}').map(|i| i + 1).unwrap_or(limpo.len());
    serde_json::from_str(&limpo[inicio..fim])
        .map_err(|e| crate::erro::Erro::novo("cerebro_respondeu_errado", format!("O cérebro não devolveu JSON válido ({e}): {texto}")))
}

/// Gera uma imagem (PNG) pelo Ignis (Z-Image Turbo, Apache 2.0).
pub async fn gerar_imagem(porta: u16, prompt: &str, tamanho: &str, semente: u64, passos: u32) -> crate::erro::Resultado<(Vec<u8>, Value)> {
    use base64::Engine;
    let corpo = serde_json::json!({"prompt": prompt, "n": 1, "size": tamanho, "output_format": "png", "seed": semente, "steps": passos,
        "negative_prompt": "borrado, texto, marca d'água, deformado"});
    let v = post_json(porta, "/v1/images/generations", &corpo, 3600).await?;
    let b64 =
        v["data"][0]["b64_json"].as_str().ok_or_else(|| crate::erro::Erro::novo("ignis_recusou", "O Ignis não devolveu a imagem."))?;
    let png = base64::engine::general_purpose::STANDARD
        .decode(b64)
        .map_err(|e| crate::erro::Erro::novo("ignis_recusou", format!("Imagem inválida: {e}")))?;
    Ok((png, v["ignis"].clone()))
}

/// Fala (WAV 24 kHz) pelo Ignis com a voz comercial (Chatterbox, MIT).
pub async fn falar(porta: u16, texto: &str, idioma: &str, semente: u64) -> crate::erro::Resultado<Vec<u8>> {
    let url = format!("http://127.0.0.1:{porta}/v1/audio/speech");
    let corpo = serde_json::json!({"model": "chatterbox", "input": texto, "language": idioma, "response_format": "wav", "seed": semente});
    let r =
        cliente_geracao(900).post(&url).json(&corpo).send().await.map_err(|e| {
            crate::erro::Erro::novo("ignis_fora", format!("Não consegui falar com o Ignis em {url}: {e}. Ele está aberto?"))
        })?;
    let status = r.status();
    if !status.is_success() {
        let v: Value = r.json().await.unwrap_or(Value::Null);
        return Err(erro_do_ignis(status, &v));
    }
    Ok(r.bytes().await.map_err(|e| crate::erro::Erro::novo("ignis_fora", e.to_string()))?.to_vec())
}

/// Reserva a placa no Ignis antes de um trabalho pesado fora dele (TRELLIS.2, Blender).
pub async fn reservar_placa(porta: u16, mb: u64, minutos: u32) -> crate::erro::Resultado<Value> {
    post_json(porta, "/motor/reservar", &serde_json::json!({"mb": mb, "minutos": minutos}), 60).await
}

pub async fn liberar_placa(porta: u16) -> crate::erro::Resultado<Value> {
    post_json(porta, "/motor/reservar/liberar", &serde_json::json!({}), 30).await
}

/// O que o Ignis tem pronto para a Fornalha (modelos de conversa, voz e imagem).
pub async fn capacidades(porta: u16) -> Value {
    let url = format!("http://127.0.0.1:{porta}/v1/models");
    match cliente().get(&url).send().await {
        Ok(r) => {
            let v: Value = r.json().await.unwrap_or(Value::Null);
            let modelos = v["data"].as_array().cloned().unwrap_or_default();
            let tipo = |m: &Value| m["ignis"]["tipo"].as_str().unwrap_or("conversa").to_string();
            let ids =
                |t: &str| modelos.iter().filter(|m| tipo(m) == t).filter_map(|m| m["id"].as_str().map(String::from)).collect::<Vec<_>>();
            serde_json::json!({"conectado": true, "conversa": ids("conversa"), "voz": ids("voz"), "imagem": ids("imagem")})
        }
        Err(_) => serde_json::json!({"conectado": false, "conversa": [], "voz": [], "imagem": []}),
    }
}
