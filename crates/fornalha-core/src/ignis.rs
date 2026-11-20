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
