//! ComfyUI local: o motor de fluxos (imagem, referência, textura, 3D, movimento) que roda na placa
//! da pessoa — NVIDIA (CUDA), AMD com ROCm (Linux) ou só no processador. A Fornalha só fala com ele em
//! 127.0.0.1 (nada sai do computador): manda um fluxo no formato de API do ComfyUI, espera terminar e
//! baixa as saídas (imagens, malhas .glb, vídeos).
//!
//! Placas sem CUDA nem ROCm (AMD e Intel no Windows, inclusive a RX 580; AMD antigas no Linux) usam o
//! motor Vulkan: o stable-diffusion.cpp (MIT) chamado pela linha de comando com os mesmos arquivos de
//! modelo. O ComfyUI tirou o DirectML em 11/11/2026 (o último PyTorch com DirectML é o 2.5).
//!
//! Só entram fluxos com modelos de licença comercial conferida (manifest/modelos.json, `onde: comfyui`).

use std::collections::BTreeSet;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};

/// Porta padrão do ComfyUI.
pub const PORTA_PADRAO: u16 = 8188;

#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct EstadoComfy {
    pub conectado: bool,
    pub endereco: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub versao: Option<String>,
    /// Placas que o ComfyUI enxerga (nome, tipo: cuda/cpu…, VRAM em MB).
    pub dispositivos: Vec<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub erro: Option<String>,
}

fn cliente(segundos: u64) -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(segundos))
        .connect_timeout(Duration::from_millis(1500))
        .no_proxy()
        .user_agent(crate::consts::USER_AGENT)
        .build()
        .expect("cliente HTTP simples")
}

fn url(porta: u16, rota: &str) -> String {
    format!("http://127.0.0.1:{porta}{rota}")
}

/// Pergunta ao ComfyUI como ele está (`/system_stats`). Nunca espera mais de ~3 s.
pub async fn consultar(porta: u16) -> EstadoComfy {
    let endereco = url(porta, "");
    let r = match cliente(3).get(url(porta, "/system_stats")).send().await {
        Ok(r) if r.status().is_success() => r,
        Ok(r) => return EstadoComfy { endereco, erro: Some(format!("respondeu {}", r.status())), ..Default::default() },
        Err(_) => return EstadoComfy { endereco, ..Default::default() },
    };
    let v: Value = r.json().await.unwrap_or(Value::Null);
    let dispositivos = v["devices"]
        .as_array()
        .map(|d| {
            d.iter()
                .map(|x| json!({"nome": x["name"], "tipo": x["type"], "vram_mb": x["vram_total"].as_u64().map(|b| b / (1024 * 1024))}))
                .collect()
        })
        .unwrap_or_default();
    EstadoComfy { conectado: true, endereco, versao: v["system"]["comfyui_version"].as_str().map(String::from), dispositivos, erro: None }
}

/// Arquivos de modelo instalados numa pasta do ComfyUI ("diffusion_models", "text_encoders", "vae",
/// "checkpoints"…).
pub async fn modelos(porta: u16, pasta: &str) -> Vec<String> {
    match cliente(10).get(url(porta, &format!("/models/{pasta}"))).send().await {
        Ok(r) if r.status().is_success() => r.json::<Vec<String>>().await.unwrap_or_default(),
        _ => vec![],
    }
}

/// Uma saída de um fluxo: o arquivo que o ComfyUI gravou, já baixado.
#[derive(Debug, Clone)]
pub struct Saida {
    pub nome: String,
    /// "images", "gifs", "3d"… (a chave da saída no histórico do ComfyUI)
    pub tipo: String,
    pub bytes: Vec<u8>,
}

/// Manda o fluxo (formato de API do ComfyUI), espera até `segundos` e baixa todas as saídas.
pub async fn executar(porta: u16, fluxo: &Value, segundos: u64) -> Resultado<Vec<Saida>> {
    let c = cliente(60);
    let r = c.post(url(porta, "/prompt")).json(&json!({"prompt": fluxo, "client_id": "fornalha"})).send().await.map_err(|e| {
        Erro::novo("comfyui_fora", format!("Não consegui falar com o ComfyUI em {}: {e}. Ele está aberto?", url(porta, "")))
    })?;
    let status = r.status();
    let v: Value = r.json().await.unwrap_or(Value::Null);
    if !status.is_success() {
        // o ComfyUI explica o nó que falhou (modelo faltando, nó desconhecido…)
        let detalhe = v["error"]["message"].as_str().unwrap_or("sem detalhe");
        let nos: Vec<String> = v["node_errors"]
            .as_object()
            .map(|m| {
                m.values()
                    .flat_map(|n| n["errors"].as_array().cloned().unwrap_or_default())
                    .filter_map(|e| e["details"].as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default();
        return Err(Erro::novo("comfyui_recusou", format!("O ComfyUI recusou o fluxo ({status}): {detalhe} {}", nos.join("; "))));
    }
    let id = v["prompt_id"].as_str().ok_or_else(|| Erro::novo("comfyui_recusou", "O ComfyUI não devolveu o número do pedido."))?;
    let inicio = Instant::now();
    let historico = loop {
        if inicio.elapsed() > Duration::from_secs(segundos) {
            let _ = c.post(url(porta, "/interrupt")).send().await;
            return Err(Erro::novo("comfyui_demorou", format!("O ComfyUI não terminou em {segundos} s; o pedido foi interrompido.")));
        }
        let h: Value = match c.get(url(porta, &format!("/history/{id}"))).send().await {
            Ok(r) => r.json().await.unwrap_or(Value::Null),
            Err(_) => Value::Null,
        };
        if let Some(item) = h.get(id) {
            if item["status"]["status_str"] == "error" {
                let msg = item["status"]["messages"]
                    .as_array()
                    .and_then(|m| m.iter().find(|x| x[0] == "execution_error"))
                    .map(|x| x[1]["exception_message"].as_str().unwrap_or("erro").to_string())
                    .unwrap_or_else(|| "erro sem detalhe".into());
                return Err(Erro::novo("comfyui_falhou", format!("O fluxo falhou no ComfyUI: {msg}")));
            }
            if item["outputs"].as_object().is_some_and(|o| !o.is_empty()) || item["status"]["completed"] == true {
                break item.clone();
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    };
    let mut saidas = vec![];
    for no in historico["outputs"].as_object().into_iter().flat_map(|o| o.values()) {
        for (tipo, itens) in no.as_object().into_iter().flatten() {
            for it in itens.as_array().into_iter().flatten() {
                let Some(nome) = it["filename"].as_str() else { continue };
                let endereco = reqwest::Url::parse_with_params(
                    &url(porta, "/view"),
                    &[
                        ("filename", nome),
                        ("subfolder", it["subfolder"].as_str().unwrap_or("")),
                        ("type", it["type"].as_str().unwrap_or("output")),
                    ],
                )
                .map_err(|e| Erro::novo("comfyui_recusou", format!("Nome de arquivo inválido vindo do ComfyUI ({nome}): {e}")))?;
                let r = c
                    .get(endereco)
                    .send()
                    .await
                    .map_err(|e| Erro::novo("comfyui_fora", format!("Não consegui baixar {nome} do ComfyUI: {e}")))?;
                if !r.status().is_success() {
                    return Err(Erro::novo("comfyui_recusou", format!("O ComfyUI não entregou {nome} ({})", r.status())));
                }
                let bytes = r.bytes().await.map_err(|e| Erro::novo("comfyui_fora", format!("Download de {nome} cortado: {e}")))?.to_vec();
                saidas.push(Saida { nome: nome.to_string(), tipo: tipo.clone(), bytes });
            }
        }
    }
    if saidas.is_empty() {
        return Err(Erro::novo("comfyui_recusou", "O fluxo terminou sem nenhuma saída."));
    }
    Ok(saidas)
}

// ------------------------------------------------------------------ fluxos

/// Modelo de imagem no ComfyUI que a Fornalha sabe usar, com os arquivos que ele precisa.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ModeloImagem {
    /// id no manifest (licença conferida)
    pub id: &'static str,
    pub difusao: String,
    pub texto: String,
    pub vae: String,
    /// arquivos quantizados (GGUF, pelo nó ComfyUI-GGUF): cabem em placas de 8 GB e no processador
    pub difusao_gguf: bool,
    pub texto_gguf: bool,
}

/// Se o ComfyUI tem um nó instalado (`/object_info/{nó}`).
pub async fn tem_no(porta: u16, no: &str) -> bool {
    match cliente(10).get(url(porta, &format!("/object_info/{no}"))).send().await {
        Ok(r) if r.status().is_success() => r.json::<Value>().await.is_ok_and(|v| v.get(no).is_some()),
        _ => false,
    }
}

/// Procura nos modelos instalados um modelo de imagem de licença comercial que a Fornalha sabe montar.
/// Hoje: Z-Image Turbo (Apache 2.0; texto Qwen3-4B Apache 2.0; VAE do pacote do Z-Image), inteiro
/// (bf16/fp8) ou quantizado (GGUF). Com pouca memória de vídeo (ou só processador), prefere o GGUF.
pub async fn modelo_de_imagem(porta: u16) -> Option<ModeloImagem> {
    let e = consultar(porta).await;
    let vram = e.dispositivos.iter().filter(|d| d["tipo"] != "cpu").filter_map(|d| d["vram_mb"].as_u64()).max().unwrap_or(0);
    let mut difusao = modelos(porta, "diffusion_models").await;
    let mut texto = modelos(porta, "text_encoders").await;
    let vae = modelos(porta, "vae").await;
    // os .gguf o nó ComfyUI-GGUF lista em pastas próprias ("unet_gguf", "clip_gguf"); sem o nó, não servem
    difusao.retain(|n| !n.ends_with(".gguf"));
    texto.retain(|n| !n.ends_with(".gguf"));
    if tem_no(porta, "UnetLoaderGGUF").await {
        difusao.extend(modelos(porta, "unet_gguf").await.into_iter().filter(|n| n.ends_with(".gguf")));
    }
    if tem_no(porta, "CLIPLoaderGGUF").await {
        texto.extend(modelos(porta, "clip_gguf").await.into_iter().filter(|n| n.ends_with(".gguf")));
    }
    escolher_imagem(&difusao, &texto, &vae, vram < 13_000)
}

/// Nome sem maiúsculas, "_", "-" e espaços ("Qwen3-4B" e "qwen_3_4b" viram "qwen34b").
fn normal(n: &str) -> String {
    n.to_lowercase().chars().filter(|c| !matches!(c, '_' | '-' | ' ')).collect()
}

fn achar<'a>(lista: &'a [String], partes: &[&str], gguf_primeiro: bool) -> Option<&'a String> {
    let bate = |n: &&String| {
        let b = normal(n);
        partes.iter().all(|p| b.contains(&normal(p)))
    };
    let (a, b): (Vec<&String>, Vec<&String>) = lista.iter().filter(bate).partition(|n| n.ends_with(".gguf") == gguf_primeiro);
    a.into_iter().next().or_else(|| b.into_iter().next())
}

fn escolher_imagem(difusao: &[String], texto: &[String], vae: &[String], pouca_memoria: bool) -> Option<ModeloImagem> {
    let d = achar(difusao, &["z_image_turbo"], pouca_memoria)?;
    let t = achar(texto, &["qwen_3_4b"], pouca_memoria)?;
    // o VAE do pacote do Z-Image se chama "ae.safetensors" (o do FLUX.2 é outro e espera a licença)
    let v = vae.iter().find(|n| n.eq_ignore_ascii_case("ae.safetensors")).or_else(|| achar(vae, &["z_image"], false))?;
    let difusao_gguf = d.ends_with(".gguf");
    let id = if difusao_gguf {
        "z-image-turbo-gguf-comfyui"
    } else if d.to_lowercase().contains("fp8") {
        "z-image-turbo-fp8"
    } else {
        "z-image-turbo-comfyui"
    };
    Some(ModeloImagem { id, difusao: d.clone(), texto: t.clone(), vae: v.clone(), difusao_gguf, texto_gguf: t.ends_with(".gguf") })
}

/// Texto → imagem com o Z-Image Turbo (o fluxo oficial do ComfyUI: Qwen3-4B como texto, AuraFlow
/// shift 3, cfg 1, res_multistep/simple; 8 passos).
pub fn fluxo_z_image(m: &ModeloImagem, prompt: &str, largura: u32, altura: u32, semente: u64, passos: u32) -> Value {
    let unet = if m.difusao_gguf {
        json!({"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": m.difusao}})
    } else {
        json!({"class_type": "UNETLoader", "inputs": {"unet_name": m.difusao, "weight_dtype": "default"}})
    };
    let clip = if m.texto_gguf {
        json!({"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": m.texto, "type": "lumina2"}})
    } else {
        json!({"class_type": "CLIPLoader", "inputs": {"clip_name": m.texto, "type": "lumina2", "device": "default"}})
    };
    json!({
        "1": unet,
        "2": clip,
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": m.vae}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": largura, "height": altura, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
              "seed": semente, "steps": passos, "cfg": 1.0, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "fornalha"}},
    })
}

/// Imagem → imagem com o Z-Image Turbo (refino: a imagem enviada vira o ponto de partida; `denoise`
/// perto de 0,5 mantém o desenho e acrescenta detalhe). A imagem é escalada para `largura` × `altura`.
#[allow(clippy::too_many_arguments)]
pub fn fluxo_z_image_de_imagem(
    m: &ModeloImagem,
    prompt: &str,
    imagem: &str,
    largura: u32,
    altura: u32,
    semente: u64,
    passos: u32,
    denoise: f64,
) -> Value {
    let mut f = fluxo_z_image(m, prompt, largura, altura, semente, passos);
    f["11"] = json!({"class_type": "LoadImage", "inputs": {"image": imagem}});
    f["12"] = json!({"class_type": "ImageScale", "inputs": {"image": ["11", 0], "upscale_method": "lanczos", "width": largura, "height": altura,
                     "crop": "center"}});
    f["7"] = json!({"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["3", 0]}});
    f["8"]["inputs"]["denoise"] = json!(denoise);
    f
}

/// Refina uma imagem no ComfyUI (Z-Image Turbo, imagem → imagem). Devolve o PNG e o resumo.
#[allow(clippy::too_many_arguments)]
pub async fn gerar_imagem_de_imagem(
    porta: u16,
    png: Vec<u8>,
    nome: &str,
    prompt: &str,
    largura: u32,
    altura: u32,
    semente: u64,
    denoise: f64,
) -> Resultado<(Vec<u8>, Value)> {
    let m = modelo_de_imagem(porta)
        .await
        .ok_or_else(|| Erro::novo("comfyui_sem_modelo", "O ComfyUI está aberto, mas sem o Z-Image Turbo para refinar a imagem."))?;
    let enviada = enviar_imagem(porta, nome, png).await?;
    let fluxo = fluxo_z_image_de_imagem(&m, prompt, &enviada, largura, altura, semente, 8, denoise);
    let inicio = Instant::now();
    let saidas = executar(porta, &fluxo, 6 * 3600).await?;
    let png = saidas
        .into_iter()
        .find(|s| s.tipo == "images")
        .map(|s| s.bytes)
        .ok_or_else(|| Erro::novo("comfyui_recusou", "O refino não devolveu imagem."))?;
    Ok((png, json!({"modelo": m, "segundos": inicio.elapsed().as_secs_f64(), "largura": largura, "altura": altura, "denoise": denoise})))
}

/// Nós que um fluxo usa (para conferir antes de mandar).
pub fn nos_do_fluxo(fluxo: &Value) -> BTreeSet<String> {
    fluxo.as_object().into_iter().flat_map(|m| m.values()).filter_map(|n| n["class_type"].as_str().map(String::from)).collect()
}

/// Gera uma imagem (PNG) no ComfyUI. Devolve os bytes e o que foi usado (para o recibo).
pub async fn gerar_imagem(porta: u16, prompt: &str, largura: u32, altura: u32, semente: u64, passos: u32) -> Resultado<(Vec<u8>, Value)> {
    let m = modelo_de_imagem(porta).await.ok_or_else(|| {
        Erro::novo(
            "comfyui_sem_modelo",
            "O ComfyUI está aberto, mas sem um modelo de imagem de licença comercial que a Fornalha conheça \
             (Z-Image Turbo: z_image_turbo_* (.safetensors ou .gguf com o nó ComfyUI-GGUF) em diffusion_models, \
             qwen_3_4b.safetensors ou Qwen3-4B-*.gguf em text_encoders, ae.safetensors em vae).",
        )
    })?;
    let fluxo = fluxo_z_image(&m, prompt, largura, altura, semente, passos);
    let inicio = Instant::now();
    let saidas = executar(porta, &fluxo, 6 * 3600).await?;
    let png = saidas
        .into_iter()
        .find(|s| s.tipo == "images")
        .map(|s| s.bytes)
        .ok_or_else(|| Erro::novo("comfyui_recusou", "O fluxo não devolveu imagem."))?;
    Ok((png, json!({"modelo": m, "segundos": inicio.elapsed().as_secs_f64(), "largura": largura, "altura": altura, "passos": passos})))
}

// ------------------------------------------------------------------ instalação e abertura

/// Como o ComfyUI roda nesta máquina (escolhido pela placa).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Caminho {
    /// "nvidia" (ComfyUI com CUDA), "rocm" (ComfyUI na AMD no Linux), "vulkan" (stable-diffusion.cpp:
    /// AMD/Intel sem CUDA nem ROCm, inclusive a RX 580) ou "cpu" (ComfyUI no processador)
    pub backend: &'static str,
    /// HSA_OVERRIDE_GFX_VERSION para as AMD RDNA2 menores no ROCm (RX 6600/6700)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hsa: Option<&'static str>,
    /// "gguf" (quantizado, cabe em 8 GB e no processador) ou "inteiro"
    pub modelos: &'static str,
    /// placa com até ~10 GB: o ComfyUI abre com --lowvram e o motor Vulkan decodifica em blocos
    /// (o que não couber vai para a RAM)
    #[serde(default)]
    pub pouca_vram: bool,
    pub motivo: String,
    /// também os modelos do 3D pela IA (TRELLIS.2 + DINOv3 + BiRefNet): só depois do aceite da
    /// licença do DINOv3 pela pessoa
    #[serde(default)]
    pub tres_d: bool,
}

/// Escolhe o caminho do ComfyUI para a placa principal da máquina.
pub fn caminho_para(det: &crate::gpu::Detection) -> Caminho {
    use crate::gpu::Vendor;
    let windows = det.sistema.familia == crate::distro::Familia::Windows;
    let Some(g) = det.principal() else {
        return Caminho {
            backend: "cpu",
            hsa: None,
            modelos: "gguf",
            pouca_vram: false,
            motivo: "sem placa de vídeo: no processador (lento, mas funciona)".into(),
            tres_d: false,
        };
    };
    let vram = g.vram_total_mb.unwrap_or(0);
    let modelos = if vram >= 16_000 { "inteiro" } else { "gguf" };
    let pouca_vram = vram > 0 && vram <= 10_240;
    match g.fabricante {
        Vendor::Nvidia => {
            Caminho { pouca_vram, backend: "nvidia", hsa: None, modelos, motivo: format!("{} com CUDA", g.nome), tres_d: false }
        }
        Vendor::Amd if windows => Caminho {
            pouca_vram,
            backend: "vulkan",
            hsa: None,
            modelos: "gguf",
            motivo: format!("{} no Windows pelo Vulkan (stable-diffusion.cpp; funciona em qualquer AMD, inclusive a RX 580)", g.nome),
            tres_d: false,
        },
        Vendor::Amd => {
            let gfx = g.alvo_gfx.as_deref().unwrap_or("");
            let hsa = matches!(gfx, "gfx1031" | "gfx1032" | "gfx1033" | "gfx1034" | "gfx1035" | "gfx1036").then_some("10.3.0");
            let rocm =
                gfx == "gfx1030" || hsa.is_some() || gfx.starts_with("gfx110") || gfx.starts_with("gfx115") || gfx.starts_with("gfx120");
            if rocm {
                Caminho { pouca_vram, backend: "rocm", hsa, modelos, motivo: format!("{} ({gfx}) pelo ROCm", g.nome), tres_d: false }
            } else {
                Caminho {
                    pouca_vram,
                    backend: "vulkan",
                    hsa: None,
                    modelos: "gguf",
                    motivo: format!(
                        "{} ({}) não tem ROCm no Linux: imagem pelo Vulkan (stable-diffusion.cpp)",
                        g.nome,
                        if gfx.is_empty() { "alvo desconhecido" } else { gfx }
                    ),
                    tres_d: false,
                }
            }
        }
        Vendor::Intel => Caminho {
            pouca_vram,
            backend: "vulkan",
            hsa: None,
            modelos: "gguf",
            motivo: format!("{} pelo Vulkan (stable-diffusion.cpp)", g.nome),
            tres_d: false,
        },
        _ => {
            Caminho { pouca_vram, backend: "cpu", hsa: None, modelos: "gguf", motivo: format!("{}: no processador", g.nome), tres_d: false }
        }
    }
}

/// Pasta da instalação do ComfyUI feita pela Fornalha.
pub fn pasta(paths: &crate::paths::Paths) -> std::path::PathBuf {
    paths.data_dir.join("comfyui")
}

/// O que o instalador gravou (`instalacao.json`): como abrir o ComfyUI.
pub fn instalacao(paths: &crate::paths::Paths) -> Option<Value> {
    instalacao_em(&pasta(paths))
}

fn instalacao_em(p: &std::path::Path) -> Option<Value> {
    serde_json::from_str(&std::fs::read_to_string(p.join("instalacao.json")).ok()?).ok()
}

/// ComfyUI só para o 3D pela IA no processador, ao lado do motor de imagem pelo Vulkan (placas sem CUDA
/// nem ROCm, como a RX 580): a imagem continua rápida na placa e o TRELLIS.2 roda no processador (horas
/// por modelo; bom para a fila da noite). Pasta e porta próprias, para um não apagar o outro.
pub fn pasta_3d(paths: &crate::paths::Paths) -> std::path::PathBuf {
    paths.data_dir.join("comfyui-3d")
}

pub fn instalacao_3d(paths: &crate::paths::Paths) -> Option<Value> {
    instalacao_em(&pasta_3d(paths))
}

/// Porta do ComfyUI do 3D no processador: a do motor principal + 1.
pub fn porta_3d(porta: u16) -> u16 {
    porta.saturating_add(1)
}

/// Caminho do 3D pela IA quando o motor de imagem desta máquina é o Vulkan: ComfyUI no processador, só
/// com os modelos do 3D (o de imagem já está no Vulkan).
pub fn caminho_3d_no_processador(principal: &Caminho) -> Caminho {
    Caminho {
        backend: "cpu",
        hsa: None,
        modelos: "nenhum",
        pouca_vram: false,
        motivo: format!(
            "{} — o 3D pela IA roda no processador, numa instalação à parte (horas por modelo: use a fila da noite)",
            principal.motivo
        ),
        tres_d: true,
    }
}

/// Situação da instalação, para a janela e o get_status.
pub fn estado_instalacao(paths: &crate::paths::Paths) -> Value {
    estado_em(&pasta(paths))
}

/// Situação do ComfyUI do 3D no processador (só existe nas máquinas do motor Vulkan).
pub fn estado_instalacao_3d(paths: &crate::paths::Paths) -> Value {
    estado_em(&pasta_3d(paths))
}

fn estado_em(p: &std::path::Path) -> Value {
    let p = p.to_path_buf();
    let log: Vec<String> = std::fs::read_to_string(p.join("instalacao.log"))
        .unwrap_or_default()
        .lines()
        .filter(|l| l.starts_with('['))
        .map(String::from)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .take(6)
        .rev()
        .collect();
    json!({"instalado": instalacao_em(&p).is_some(), "instalando": p.join("instalando").is_file(), "pasta": p, "log": log,
           "instalacao": instalacao_em(&p)})
}

async fn comando_de_instalacao(
    paths: &crate::paths::Paths,
    c: &Caminho,
    porta: u16,
    destino: std::path::PathBuf,
) -> Resultado<(tokio::process::Command, std::path::PathBuf)> {
    // o motor Vulkan só baixa arquivos: serve o Python que vem dentro do Blender; o ComfyUI cria um
    // ambiente próprio e precisa do Python do sistema
    let python = if c.backend == "vulkan" { crate::workers::python_para(paths).await } else { crate::workers::python_do_sistema().await };
    let python = python.ok_or_else(|| {
        Erro::novo(
            "python_ausente",
            if c.backend == "vulkan" {
                "Para instalar o motor de imagem precisa do Python 3.10+ (python.org) ou do Blender baixado em Máquina → Programas."
            } else {
                "Precisa do Python 3.10 ou mais novo instalado (python.org) para instalar o ComfyUI."
            },
        )
    })?;
    let scripts = crate::workers::preparar_scripts(&paths.data_dir)?;
    std::fs::create_dir_all(&destino).map_err(|e| Erro::io(&destino, e))?;
    let mut cmd = tokio::process::Command::new(&python);
    cmd.arg(scripts.join("instalar_comfyui.py")).arg(&destino).arg(c.backend).args(["--modelos", c.modelos, "--porta", &porta.to_string()]);
    if let Some(h) = c.hsa {
        cmd.args(["--hsa", h]);
    }
    if c.pouca_vram && c.backend != "cpu" {
        cmd.arg("--pouca-vram");
    }
    if c.tres_d && c.backend != "vulkan" {
        cmd.arg("--3d");
    }
    Ok((cmd, destino))
}

/// Instala aqui mesmo, mostrando o progresso no terminal (linha de comando).
pub async fn instalar_e_esperar(paths: &crate::paths::Paths, c: &Caminho, porta: u16) -> Resultado<Value> {
    let (mut cmd, destino) = comando_de_instalacao(paths, c, porta, pasta(paths)).await?;
    let ok = cmd.status().await.map(|s| s.success()).unwrap_or(false);
    if !ok {
        return Err(Erro::novo(
            "instalacao_falhou",
            format!("A instalação do ComfyUI falhou: veja {}", destino.join("instalacao.log").display()),
        ));
    }
    Ok(estado_instalacao(paths))
}

/// Começa a instalação em segundo plano (vários GB). O progresso fica em `<pasta>/instalacao.log`.
pub async fn instalar(paths: &crate::paths::Paths, c: &Caminho, porta: u16) -> Resultado<Value> {
    instalar_em(paths, c, porta, pasta(paths)).await
}

/// O mesmo que `instalar_3d_no_processador`, esperando aqui (linha de comando).
pub async fn instalar_3d_no_processador_e_esperar(paths: &crate::paths::Paths, principal: &Caminho, porta: u16) -> Resultado<Value> {
    let (mut cmd, destino) = comando_de_instalacao(paths, &caminho_3d_no_processador(principal), porta_3d(porta), pasta_3d(paths)).await?;
    if !cmd.status().await.map(|s| s.success()).unwrap_or(false) {
        return Err(Erro::novo(
            "instalacao_falhou",
            format!("A instalação do 3D no processador falhou: veja {}", destino.join("instalacao.log").display()),
        ));
    }
    Ok(estado_instalacao_3d(paths))
}

/// Instala o ComfyUI do 3D no processador ao lado do motor Vulkan (pasta e porta próprias).
pub async fn instalar_3d_no_processador(paths: &crate::paths::Paths, principal: &Caminho, porta: u16) -> Resultado<Value> {
    instalar_em(paths, &caminho_3d_no_processador(principal), porta_3d(porta), pasta_3d(paths)).await
}

async fn instalar_em(paths: &crate::paths::Paths, c: &Caminho, porta: u16, pasta_destino: std::path::PathBuf) -> Resultado<Value> {
    let (mut cmd, destino) = comando_de_instalacao(paths, c, porta, pasta_destino).await?;
    cmd.stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    let mut filho = cmd.spawn().map_err(|e| Erro::novo("instalacao_falhou", format!("Não consegui abrir o instalador do ComfyUI: {e}")))?;
    std::fs::write(destino.join("instalando"), crate::util::agora_iso()).ok();
    let marca = destino.join("instalando");
    tokio::spawn(async move {
        let _ = filho.wait().await;
        let _ = std::fs::remove_file(marca);
    });
    Ok(json!({"iniciado": true, "caminho": c, "log": destino.join("instalacao.log")}))
}

/// Abre o ComfyUI instalado pela Fornalha (se ainda não estiver aberto) e espera ele responder.
pub async fn abrir(paths: &crate::paths::Paths, porta: u16) -> Resultado<EstadoComfy> {
    abrir_em(&pasta(paths), porta).await
}

/// Abre o ComfyUI do 3D no processador (na porta dele) e espera responder.
pub async fn abrir_3d(paths: &crate::paths::Paths, porta: u16) -> Resultado<EstadoComfy> {
    abrir_em(&pasta_3d(paths), porta_3d(porta)).await
}

async fn abrir_em(pasta_comfy: &std::path::Path, porta: u16) -> Resultado<EstadoComfy> {
    let e = consultar(porta).await;
    if e.conectado {
        return Ok(e);
    }
    let inst = instalacao_em(pasta_comfy)
        .ok_or_else(|| Erro::novo("comfyui_ausente", "O ComfyUI não está instalado (Máquina → ComfyUI → Instalar)."))?;
    if inst["motor"] == "sdcpp" {
        return Err(Erro::novo(
            "motor_vulkan",
            "Esta máquina usa o motor Vulkan (stable-diffusion.cpp): ele não fica aberto, a Fornalha chama na hora de gerar.",
        ));
    }
    let python = inst["python"].as_str().unwrap_or_default();
    let dir = inst["pasta_comfyui"].as_str().unwrap_or_default();
    let mut args: Vec<String> = inst["argumentos"].as_array().into_iter().flatten().filter_map(|a| a.as_str().map(String::from)).collect();
    if let Some(i) = args.iter().position(|a| a == "--port") {
        if let Some(v) = args.get_mut(i + 1) {
            *v = porta.to_string();
        }
    }
    let log = std::fs::File::create(pasta_comfy.join("comfyui.log")).map_err(|e| Erro::io(pasta_comfy, e))?;
    let mut cmd = tokio::process::Command::new(python);
    cmd.args(&args)
        .current_dir(dir)
        .stdin(std::process::Stdio::null())
        .stdout(log.try_clone().map_err(|e| Erro::io(pasta_comfy, e))?)
        .stderr(log);
    for (k, v) in inst["ambiente"].as_object().into_iter().flatten() {
        if let Some(v) = v.as_str() {
            cmd.env(k, v);
        }
    }
    #[cfg(windows)]
    {
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.kill_on_drop(false);
    cmd.spawn().map_err(|e| Erro::novo("comfyui_fora", format!("Não consegui abrir o ComfyUI: {e}")))?;
    let inicio = Instant::now();
    while inicio.elapsed() < Duration::from_secs(180) {
        tokio::time::sleep(Duration::from_secs(2)).await;
        let e = consultar(porta).await;
        if e.conectado {
            return Ok(e);
        }
    }
    Err(Erro::novo("comfyui_fora", "O ComfyUI não respondeu em 3 minutos depois de aberto (veja comfyui.log na pasta dele)."))
}

// ------------------------------------------------------------------ 3D pela IA (TRELLIS.2)

/// Fluxo oficial do ComfyUI "imagem → malha" (Pixal3D/TRELLIS.2, Comfy-Org/workflow_templates, MIT).
pub const FLUXO_TRELLIS2: &str = include_str!("../comfyui/trellis2_imagem_para_malha.json");

/// Arquivos do 3D pela IA que precisam estar no ComfyUI (pasta, nome).
pub const ARQUIVOS_3D: [(&str, &str); 5] = [
    ("diffusion_models", "trellis_2_int8_convrot.safetensors"),
    ("vae", "trellis_2_shape_vae_bf16.safetensors"),
    ("vae", "trellis_2_texture_vae_bf16.safetensors"),
    ("clip_vision", "dino_v3_vit_l.safetensors"),
    ("background_removal", "birefnet.safetensors"),
];

/// Envia uma imagem para a pasta de entrada do ComfyUI (`/upload/image`). Devolve o nome lá dentro.
pub async fn enviar_imagem(porta: u16, nome: &str, png: Vec<u8>) -> Resultado<String> {
    let parte = reqwest::multipart::Part::bytes(png)
        .file_name(nome.to_string())
        .mime_str("image/png")
        .map_err(|e| Erro::novo("comfyui_recusou", format!("Imagem inválida: {e}")))?;
    let form = reqwest::multipart::Form::new().part("image", parte).text("overwrite", "true");
    let r = cliente(120)
        .post(url(porta, "/upload/image"))
        .multipart(form)
        .send()
        .await
        .map_err(|e| Erro::novo("comfyui_fora", format!("Não consegui enviar a imagem ao ComfyUI: {e}")))?;
    let v: Value = r.json().await.unwrap_or(Value::Null);
    let nome = v["name"].as_str().ok_or_else(|| Erro::novo("comfyui_recusou", format!("O ComfyUI não aceitou a imagem: {v}")))?;
    Ok(match v["subfolder"].as_str().filter(|s| !s.is_empty()) {
        Some(sub) => format!("{sub}/{nome}"),
        None => nome.to_string(),
    })
}

/// Troca, nos nós de um tipo, todo valor fixo igual a `de` por `para` (para mexer nos fluxos oficiais
/// sem depender do nome interno de cada entrada).
pub fn trocar_valor(api: &mut Value, tipo: &str, de: &Value, para: Value) -> usize {
    let mut n = 0;
    for no in api.as_object_mut().into_iter().flat_map(|m| m.values_mut()) {
        if no["class_type"] != tipo {
            continue;
        }
        for v in no["inputs"].as_object_mut().into_iter().flat_map(|e| e.values_mut()) {
            if v == de {
                *v = para.clone();
                n += 1;
            }
        }
    }
    n
}

/// O fluxo do TRELLIS.2 pronto para a API: ramo do TRELLIS.2 (não o Pixal3D), nossa imagem, nossos
/// arquivos e, no processador, tamanhos menores (horas em vez de dias).
/// `reduzido`: no processador, tamanhos menores (2 a 4 h em vez de uma noite inteira). No nível Máximo a
/// Fornalha manda o fluxo inteiro mesmo no processador: a pessoa escolheu esperar pela qualidade.
pub fn fluxo_trellis2(object_info: &Value, imagem: &str, reduzido: bool, semente: u64) -> Resultado<Value> {
    let ui: Value =
        serde_json::from_str(FLUXO_TRELLIS2).map_err(|e| Erro::novo("comfyui_fluxo", format!("Fluxo 3D embutido inválido: {e}")))?;
    let mut api = crate::comfyui_ui::para_api(&ui, object_info)?;
    crate::comfyui_ui::trocar(&mut api, "PrimitiveBoolean", "value", json!(true)); // true = TRELLIS.2
    crate::comfyui_ui::resolver_interruptores(&mut api);
    // a saída do modelo oficial (Save3DAdvanced) pede o estado da câmera da interface: no lugar dela, o
    // SaveGLB, que só precisa da malha
    for no in api.as_object_mut().into_iter().flat_map(|m| m.values_mut()) {
        if no["class_type"] == "Save3DAdvanced" {
            let malha = no["inputs"]["model_3d"].clone();
            *no = json!({"class_type": "SaveGLB", "inputs": {"mesh": malha, "filename_prefix": "3d/fornalha"}, "_meta": {"title": "Salvar a malha"}});
        }
    }
    crate::comfyui_ui::podar(&mut api, &["SaveGLB"])?;
    crate::comfyui_ui::trocar(&mut api, "LoadImage", "image", json!(imagem));
    trocar_valor(&mut api, "CLIPVisionLoader", &json!("dino_v3_L_naf_fp32.safetensors"), json!("dino_v3_vit_l.safetensors"));
    for no in api.as_object_mut().into_iter().flat_map(|m| m.values_mut()) {
        if no["class_type"] == "KSampler" {
            no["inputs"]["seed"] = json!(semente);
        }
    }
    if reduzido {
        trocar_valor(&mut api, "Trellis2UpsampleStage", &json!(1536), json!(1024));
        trocar_valor(&mut api, "PrimitiveInt", &json!(4096), json!(2048));
        trocar_valor(&mut api, "DecimateMesh", &json!(700000), json!(200000));
        trocar_valor(&mut api, "RemeshMesh", &json!(768), json!(512));
    }
    Ok(api)
}

/// Imagem → malha texturizada (.glb) pelo TRELLIS.2 no ComfyUI aberto. No processador pode levar horas.
pub async fn gerar_3d(porta: u16, png: Vec<u8>, nome: &str, semente: u64, segundos: u64, completo: bool) -> Resultado<(Vec<u8>, Value)> {
    let e = consultar(porta).await;
    if !e.conectado {
        return Err(Erro::novo("comfyui_fora", "O ComfyUI não está aberto."));
    }
    let processador = e.dispositivos.iter().all(|d| d["tipo"] == "cpu");
    let info: Value = cliente(120)
        .get(url(porta, "/object_info"))
        .send()
        .await
        .map_err(|e| Erro::novo("comfyui_fora", format!("Não consegui ler os nós do ComfyUI: {e}")))?
        .json()
        .await
        .map_err(|e| Erro::novo("comfyui_recusou", format!("Lista de nós do ComfyUI ilegível: {e}")))?;
    let imagem = enviar_imagem(porta, nome, png).await?;
    let fluxo = fluxo_trellis2(&info, &imagem, processador && !completo, semente)?;
    let inicio = Instant::now();
    let saidas = executar(porta, &fluxo, segundos).await?;
    let glb = saidas.iter().find(|s| s.nome.to_lowercase().ends_with(".glb")).ok_or_else(|| {
        Erro::novo(
            "comfyui_recusou",
            format!("O fluxo 3D terminou sem .glb (saídas: {:?}).", saidas.iter().map(|s| &s.nome).collect::<Vec<_>>()),
        )
    })?;
    Ok((
        glb.bytes.clone(),
        json!({"modelo": "trellis2-comfyui", "segundos": inicio.elapsed().as_secs_f64(), "processador": processador, "tamanho_completo": !processador || completo, "nos": fluxo.as_object().map(|m| m.len()),
               "dispositivos": e.dispositivos}),
    ))
}

// ------------------------------------------------------------------ motor Vulkan (stable-diffusion.cpp)

/// O motor Vulkan instalado pela Fornalha: o executável e os três arquivos do Z-Image Turbo.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct MotorVulkan {
    pub sd_cli: std::path::PathBuf,
    pub difusao: std::path::PathBuf,
    pub texto: std::path::PathBuf,
    pub vae: std::path::PathBuf,
    pub pouca_vram: bool,
    pub versao: String,
}

impl MotorVulkan {
    /// Id do modelo no manifesto (para o recibo de licença).
    pub fn id(&self) -> &'static str {
        "z-image-turbo-gguf-vulkan"
    }
}

/// O motor Vulkan, se foi ele que o instalador deixou pronto (com o executável e os modelos no disco).
pub fn motor_vulkan(paths: &crate::paths::Paths) -> Option<MotorVulkan> {
    let inst = instalacao(paths)?;
    if inst["motor"] != "sdcpp" {
        return None;
    }
    let arq = |k: &str| inst[k].as_str().map(std::path::PathBuf::from).filter(|p| p.is_file());
    Some(MotorVulkan {
        sd_cli: arq("sd_cli")?,
        difusao: arq("difusao")?,
        texto: arq("texto")?,
        vae: arq("vae")?,
        pouca_vram: inst["pouca_vram"].as_bool().unwrap_or(false),
        versao: inst["sdcpp_versao"].as_str().unwrap_or("").to_string(),
    })
}

/// Argumentos do sd-cli para o Z-Image Turbo (o mesmo fluxo do ComfyUI: CFG 1, 8 passos).
pub fn argumentos_vulkan(
    m: &MotorVulkan,
    prompt: &str,
    largura: u32,
    altura: u32,
    semente: u64,
    passos: u32,
    saida: &std::path::Path,
) -> Vec<String> {
    let mut a: Vec<String> = vec![
        "--diffusion-model".into(),
        m.difusao.to_string_lossy().into_owned(),
        "--llm".into(),
        m.texto.to_string_lossy().into_owned(),
        "--vae".into(),
        m.vae.to_string_lossy().into_owned(),
        "-p".into(),
        prompt.to_string(),
        "--cfg-scale".into(),
        "1.0".into(),
        "--steps".into(),
        passos.to_string(),
        "-W".into(),
        (largura / 16 * 16).to_string(),
        "-H".into(),
        (altura / 16 * 16).to_string(),
        "-s".into(),
        (semente % (i64::MAX as u64)).to_string(),
        "--rng".into(),
        "cpu".into(),
        "-o".into(),
        saida.to_string_lossy().into_owned(),
    ];
    if m.pouca_vram {
        // placa de 8 GB (RX 580): o VAE decodifica em blocos; os pesos que não couberem vão para a RAM
        // sozinhos (o --auto-fit do sd.cpp vem ligado)
        a.push("--vae-tiling".into());
    }
    a
}

/// Dispositivos que o motor Vulkan enxerga (`sd-cli --list-devices`): "Vulkan0\tAMD Radeon RX 580…",
/// "CPU\t…". Lista vazia se não rodar.
pub async fn dispositivos_vulkan(m: &MotorVulkan) -> Vec<String> {
    let d: Vec<String> = match crate::externas::rodar(&m.sd_cli, &["--list-devices"], Duration::from_secs(60), m.sd_cli.parent()).await {
        Ok(s) => s.stdout.lines().map(str::trim).filter(|l| l.contains('\t')).map(String::from).collect(),
        Err(_) => vec![],
    };
    if !d.is_empty() {
        // guardado para o estado da janela (que não roda o executável a cada consulta)
        let _ = std::fs::write(arquivo_de_dispositivos(m), serde_json::to_string(&d).unwrap_or_default());
    }
    d
}

fn arquivo_de_dispositivos(m: &MotorVulkan) -> std::path::PathBuf {
    m.sd_cli.with_file_name("dispositivos.json")
}

/// Os dispositivos da última vez que o motor Vulkan rodou (sem rodar de novo).
pub fn dispositivos_vulkan_guardados(m: &MotorVulkan) -> Vec<String> {
    std::fs::read_to_string(arquivo_de_dispositivos(m)).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default()
}

/// Se só o processador aparece (sem Vulkan): imagem larga leva tempo demais para o dia a dia.
pub fn so_processador(dispositivos: &[String]) -> bool {
    !dispositivos.iter().any(|d| {
        let n = d.split('\t').next().unwrap_or("").to_lowercase();
        n.starts_with("vulkan") || n.starts_with("cuda") || n.starts_with("rocm") || n.starts_with("metal")
    })
}

/// Gera uma imagem pelo motor Vulkan. Devolve o PNG e um resumo (tempo, dispositivos, versão).
pub async fn gerar_imagem_vulkan(
    m: &MotorVulkan,
    prompt: &str,
    largura: u32,
    altura: u32,
    semente: u64,
    passos: u32,
) -> Resultado<(Vec<u8>, Value)> {
    let pasta = std::env::temp_dir().join(format!("fornalha-sdcpp-{}", std::process::id()));
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    let saida = pasta.join(format!("{semente}-{largura}x{altura}.png"));
    let _ = std::fs::remove_file(&saida);
    let args = argumentos_vulkan(m, prompt, largura, altura, semente, passos, &saida);
    let refs: Vec<&str> = args.iter().map(String::as_str).collect();
    let inicio = Instant::now();
    // no processador (sem Vulkan) uma imagem grande pode levar muitos minutos: margem larga
    let r = crate::externas::rodar(&m.sd_cli, &refs, Duration::from_secs(90 * 60), m.sd_cli.parent()).await?;
    let png = std::fs::read(&saida).map_err(|_| {
        Erro::novo("vulkan_falhou", format!("O motor Vulkan não gerou a imagem. Final da saída:\n{}", r.final_da_saida(25)))
    })?;
    let _ = std::fs::remove_file(&saida);
    let usou: Vec<String> = format!("{}\n{}", r.stdout, r.stderr)
        .lines()
        .filter(|l| {
            let l = l.to_lowercase();
            l.contains("vulkan") || l.contains("using cpu") || l.contains("backend")
        })
        .take(6)
        .map(|l| l.trim().to_string())
        .collect();
    Ok((
        png,
        json!({"motor": "stable-diffusion.cpp", "versao": m.versao, "segundos": inicio.elapsed().as_secs_f64(),
               "largura": largura, "altura": altura, "passos": passos, "pouca_vram": m.pouca_vram, "registro": usou}),
    ))
}

#[cfg(test)]
mod testes {
    use super::*;

    /// Com a lista de nós de verdade (FORNALHA_OBJECT_INFO=<object_info.json> baixado do CI), mostra o
    /// fluxo do TRELLIS.2 convertido. Rodar com `--ignored`.
    #[test]
    #[ignore]
    fn fluxo_trellis2_com_a_lista_real() {
        let Ok(arq) = std::env::var("FORNALHA_OBJECT_INFO") else { return };
        let info: Value = serde_json::from_str(&std::fs::read_to_string(arq).unwrap()).unwrap();
        let f = fluxo_trellis2(&info, "conceito.png", true, 7).unwrap();
        println!("{}", serde_json::to_string_pretty(&f).unwrap());
    }

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| x.to_string()).collect()
    }

    /// RX 580 (motor de imagem pelo Vulkan): o 3D pela IA vai para um ComfyUI no processador em pasta e
    /// porta próprias, sem apagar o motor Vulkan (antes os dois disputavam a mesma instalacao.json).
    #[test]
    fn tres_d_no_processador_fica_ao_lado_do_vulkan() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = crate::paths::Paths::under(tmp.path());
        let vulkan =
            Caminho { backend: "vulkan", hsa: None, modelos: "gguf", pouca_vram: true, motivo: "AMD Radeon RX 580".into(), tres_d: false };
        let c = caminho_3d_no_processador(&vulkan);
        assert_eq!((c.backend, c.modelos, c.tres_d, c.pouca_vram), ("cpu", "nenhum", true, false));
        assert!(c.motivo.contains("RX 580") && c.motivo.contains("processador"));
        assert_ne!(pasta(&paths), pasta_3d(&paths));
        assert_eq!(porta_3d(PORTA_PADRAO), PORTA_PADRAO + 1);
        // as duas instalações convivem e cada uma lê a sua
        std::fs::create_dir_all(pasta(&paths)).unwrap();
        std::fs::create_dir_all(pasta_3d(&paths)).unwrap();
        std::fs::write(pasta(&paths).join("instalacao.json"), r#"{"motor":"sdcpp"}"#).unwrap();
        std::fs::write(pasta_3d(&paths).join("instalacao.json"), r#"{"motor":"comfyui","modelos":["trellis_2_int8_convrot.safetensors"]}"#)
            .unwrap();
        assert_eq!(instalacao(&paths).unwrap()["motor"], "sdcpp");
        assert_eq!(instalacao_3d(&paths).unwrap()["motor"], "comfyui");
        assert_eq!(estado_instalacao_3d(&paths)["instalado"], true);
        assert_eq!(estado_instalacao(&paths)["instalacao"]["motor"], "sdcpp");
    }

    #[test]
    fn escolhe_z_image_so_com_os_tres_arquivos() {
        let d = s(&["flux-2-klein-4b.safetensors", "z_image_turbo_bf16.safetensors"]);
        let t = s(&["qwen_3_4b.safetensors"]);
        let v = s(&["ae.safetensors", "flux2-vae.safetensors"]);
        let m = escolher_imagem(&d, &t, &v, false).unwrap();
        assert_eq!(m.id, "z-image-turbo-comfyui");
        assert_eq!(m.difusao, "z_image_turbo_bf16.safetensors");
        assert!(escolher_imagem(&d, &[], &v, false).is_none(), "sem o texto não monta");
        assert!(escolher_imagem(&s(&["flux-2-klein-4b.safetensors"]), &t, &v, false).is_none(), "o FLUX.2 klein espera a licença do VAE");
        let fp8 = escolher_imagem(&s(&["z_image_turbo_fp8_e4m3fn.safetensors"]), &t, &v, false).unwrap();
        assert_eq!(fp8.id, "z-image-turbo-fp8");
    }

    #[test]
    fn pouca_memoria_prefere_o_gguf() {
        let d = s(&["z_image_turbo_bf16.safetensors", "z_image_turbo-Q4_K_M.gguf"]);
        let t = s(&["Qwen3-4B-Q4_K_M.gguf", "qwen_3_4b.safetensors"]);
        let v = s(&["ae.safetensors"]);
        let m = escolher_imagem(&d, &t, &v, true).unwrap();
        assert_eq!(m.id, "z-image-turbo-gguf-comfyui");
        assert!(m.difusao_gguf && m.texto_gguf);
        let f = fluxo_z_image(&m, "x", 512, 512, 1, 8);
        assert_eq!(f["1"]["class_type"], "UnetLoaderGGUF");
        assert_eq!(f["2"]["class_type"], "CLIPLoaderGGUF");
        assert_eq!(f["2"]["inputs"]["type"], "lumina2");
        let grande = escolher_imagem(&d, &t, &v, false).unwrap();
        assert_eq!(grande.difusao, "z_image_turbo_bf16.safetensors");
        assert!(!grande.texto_gguf);
    }

    fn deteccao(
        familia: crate::distro::Familia,
        vendor: crate::gpu::Vendor,
        nome: &str,
        vram: u64,
        gfx: Option<&str>,
    ) -> crate::gpu::Detection {
        let g = crate::gpu::Gpu {
            fabricante: vendor,
            nome: nome.to_string(),
            pci_dispositivo: None,
            vram_total_mb: Some(vram),
            vram_livre_mb: None,
            driver: None,
            versao_driver: None,
            alvo_gfx: gfx.map(String::from),
            integrada: false,
            fontes: vec![],
        };
        crate::gpu::Detection {
            sistema: crate::distro::Sistema { familia, nome: String::new(), versao: None, flatpak: false, appimage: false },
            arq: "x86_64".into(),
            placas: vec![g],
            ram_total_mb: 16000,
            ram_livre_mb: 8000,
            libs: Default::default(),
            kfd_acessivel: false,
            ferramentas: vec![],
            fontes_brutas: Default::default(),
        }
    }

    #[test]
    fn caminho_pela_placa() {
        use crate::distro::Familia;
        use crate::gpu::Vendor;
        let rx580_win = caminho_para(&deteccao(Familia::Windows, Vendor::Amd, "Radeon RX 580", 8192, Some("gfx803")));
        assert_eq!((rx580_win.backend, rx580_win.modelos, rx580_win.pouca_vram), ("vulkan", "gguf", true));
        let rx580_linux = caminho_para(&deteccao(Familia::Fedora, Vendor::Amd, "Radeon RX 580", 8192, Some("gfx803")));
        assert_eq!(rx580_linux.backend, "vulkan");
        assert!(rx580_linux.motivo.contains("Vulkan"));
        let rx7800_win = caminho_para(&deteccao(Familia::Windows, Vendor::Amd, "Radeon RX 7800 XT", 16368, Some("gfx1101")));
        assert_eq!(rx7800_win.backend, "vulkan");
        let arc = caminho_para(&deteccao(Familia::Windows, Vendor::Intel, "Arc A770", 16000, None));
        assert_eq!(arc.backend, "vulkan");
        let rx6600 = caminho_para(&deteccao(Familia::Fedora, Vendor::Amd, "Radeon RX 6600", 8176, Some("gfx1032")));
        assert_eq!((rx6600.backend, rx6600.hsa), ("rocm", Some("10.3.0")));
        let rx9060 = caminho_para(&deteccao(Familia::Arch, Vendor::Amd, "Radeon RX 9060 XT", 16304, Some("gfx1200")));
        assert_eq!((rx9060.backend, rx9060.hsa, rx9060.modelos), ("rocm", None, "inteiro"));
        let rtx = caminho_para(&deteccao(Familia::Windows, Vendor::Nvidia, "GeForce RTX 3060", 12288, None));
        assert_eq!((rtx.backend, rtx.modelos), ("nvidia", "gguf"));
    }

    #[test]
    fn argumentos_do_motor_vulkan() {
        let m = MotorVulkan {
            sd_cli: "sd-cli".into(),
            difusao: "z_image_turbo-Q4_K_M.gguf".into(),
            texto: "Qwen3-4B-Q4_K_M.gguf".into(),
            vae: "ae.safetensors".into(),
            pouca_vram: true,
            versao: "x".into(),
        };
        let a = argumentos_vulkan(&m, "um templário", 1530, 640, 42, 8, std::path::Path::new("saida.png"));
        let par = |k: &str| a.iter().position(|x| x == k).map(|i| a[i + 1].clone());
        assert_eq!(par("--diffusion-model").as_deref(), Some("z_image_turbo-Q4_K_M.gguf"));
        assert_eq!(par("--llm").as_deref(), Some("Qwen3-4B-Q4_K_M.gguf"));
        assert_eq!(par("--cfg-scale").as_deref(), Some("1.0"));
        assert_eq!(par("-W").as_deref(), Some("1520"), "múltiplo de 16");
        assert_eq!(par("-s").as_deref(), Some("42"));
        assert!(a.contains(&"--vae-tiling".to_string()));
        assert!(so_processador(&["CPU\tAMD Ryzen".into()]));
        assert!(!so_processador(&["Vulkan0\tAMD Radeon RX 580 Series".into(), "CPU\tx".into()]));
    }

    #[test]
    fn refino_parte_da_imagem_enviada() {
        let m = ModeloImagem {
            id: "z-image-turbo-comfyui",
            difusao: "z.safetensors".into(),
            texto: "q.safetensors".into(),
            vae: "ae.safetensors".into(),
            difusao_gguf: false,
            texto_gguf: false,
        };
        let f = fluxo_z_image_de_imagem(&m, "cabeça", "cabeca.png", 1024, 1024, 7, 8, 0.5);
        let nos = nos_do_fluxo(&f);
        assert!(nos.contains("LoadImage") && nos.contains("ImageScale") && nos.contains("VAEEncode"), "{nos:?}");
        assert!(!nos.contains("EmptySD3LatentImage"));
        assert_eq!(f["8"]["inputs"]["latent_image"], json!(["7", 0]));
        assert_eq!(f["8"]["inputs"]["denoise"], json!(0.5));
        assert_eq!(f["11"]["inputs"]["image"], "cabeca.png");
        assert_eq!(f["12"]["inputs"]["width"], 1024);
    }

    #[test]
    fn fluxo_do_z_image_bate_com_o_oficial() {
        let m = ModeloImagem {
            id: "z-image-turbo-comfyui",
            difusao: "z.safetensors".into(),
            texto: "q.safetensors".into(),
            vae: "ae.safetensors".into(),
            difusao_gguf: false,
            texto_gguf: false,
        };
        let f = fluxo_z_image(&m, "um templário", 1024, 768, 7, 8);
        let nos = nos_do_fluxo(&f);
        for n in [
            "UNETLoader",
            "CLIPLoader",
            "VAELoader",
            "ModelSamplingAuraFlow",
            "CLIPTextEncode",
            "ConditioningZeroOut",
            "EmptySD3LatentImage",
            "KSampler",
            "VAEDecode",
            "SaveImage",
        ] {
            assert!(nos.contains(n), "falta {n}");
        }
        assert_eq!(f["2"]["inputs"]["type"], "lumina2");
        assert_eq!(f["8"]["inputs"]["sampler_name"], "res_multistep");
        assert_eq!(f["8"]["inputs"]["seed"], 7);
        assert_eq!(f["7"]["inputs"]["height"], 768);
    }
}
