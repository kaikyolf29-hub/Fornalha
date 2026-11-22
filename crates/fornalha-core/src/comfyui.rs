//! ComfyUI local: o motor de fluxos (imagem, referência, textura, 3D, movimento) que roda na placa
//! da pessoa — NVIDIA (CUDA), AMD (ROCm no Linux, DirectML/ZLUDA no Windows) ou só no processador.
//! A Fornalha só fala com ele em 127.0.0.1 (nada sai do computador): manda um fluxo no formato de API
//! do ComfyUI, espera terminar e baixa as saídas (imagens, malhas .glb, vídeos).
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
    /// Placas que o ComfyUI enxerga (nome, tipo: cuda/directml/cpu…, VRAM em MB).
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
    /// "nvidia" (CUDA), "rocm" (AMD no Linux), "directml" (AMD/Intel no Windows) ou "cpu"
    pub backend: &'static str,
    /// HSA_OVERRIDE_GFX_VERSION para as AMD RDNA2 menores no ROCm (RX 6600/6700)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hsa: Option<&'static str>,
    /// "gguf" (quantizado, cabe em 8 GB e no processador) ou "inteiro"
    pub modelos: &'static str,
    /// placa com até ~10 GB: o ComfyUI abre com --lowvram (descarrega para a RAM o que não couber)
    #[serde(default)]
    pub pouca_vram: bool,
    pub motivo: String,
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
        };
    };
    let vram = g.vram_total_mb.unwrap_or(0);
    let modelos = if vram >= 16_000 { "inteiro" } else { "gguf" };
    let pouca_vram = vram > 0 && vram <= 10_240;
    match g.fabricante {
        Vendor::Nvidia => Caminho { pouca_vram, backend: "nvidia", hsa: None, modelos, motivo: format!("{} com CUDA", g.nome) },
        Vendor::Amd if windows => Caminho {
            pouca_vram,
            backend: "directml",
            hsa: None,
            modelos: "gguf",
            motivo: format!("{} no Windows pelo DirectML (funciona em qualquer AMD com DirectX 12, inclusive a RX 580)", g.nome),
        },
        Vendor::Amd => {
            let gfx = g.alvo_gfx.as_deref().unwrap_or("");
            let hsa = matches!(gfx, "gfx1031" | "gfx1032" | "gfx1033" | "gfx1034" | "gfx1035" | "gfx1036").then_some("10.3.0");
            let rocm =
                gfx == "gfx1030" || hsa.is_some() || gfx.starts_with("gfx110") || gfx.starts_with("gfx115") || gfx.starts_with("gfx120");
            if rocm {
                Caminho { pouca_vram, backend: "rocm", hsa, modelos, motivo: format!("{} ({gfx}) pelo ROCm", g.nome) }
            } else {
                Caminho {
                    pouca_vram,
                    backend: "cpu",
                    hsa: None,
                    modelos: "gguf",
                    motivo: format!(
                        "{} ({}) não tem ROCm no Linux: o ComfyUI roda no processador; para imagem rápida nesta placa use o Ignis pelo Vulkan",
                        g.nome,
                        if gfx.is_empty() { "alvo desconhecido" } else { gfx }
                    ),
                }
            }
        }
        Vendor::Intel if windows => {
            Caminho { pouca_vram, backend: "directml", hsa: None, modelos: "gguf", motivo: format!("{} pelo DirectML", g.nome) }
        }
        _ => Caminho { pouca_vram, backend: "cpu", hsa: None, modelos: "gguf", motivo: format!("{}: no processador", g.nome) },
    }
}

/// Pasta da instalação do ComfyUI feita pela Fornalha.
pub fn pasta(paths: &crate::paths::Paths) -> std::path::PathBuf {
    paths.data_dir.join("comfyui")
}

/// O que o instalador gravou (`instalacao.json`): como abrir o ComfyUI.
pub fn instalacao(paths: &crate::paths::Paths) -> Option<Value> {
    let arq = pasta(paths).join("instalacao.json");
    serde_json::from_str(&std::fs::read_to_string(arq).ok()?).ok()
}

/// Situação da instalação, para a janela e o get_status.
pub fn estado_instalacao(paths: &crate::paths::Paths) -> Value {
    let p = pasta(paths);
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
    json!({"instalado": instalacao(paths).is_some(), "instalando": p.join("instalando").is_file(), "pasta": p, "log": log,
           "instalacao": instalacao(paths)})
}

async fn comando_de_instalacao(
    paths: &crate::paths::Paths,
    c: &Caminho,
    porta: u16,
) -> Resultado<(tokio::process::Command, std::path::PathBuf)> {
    let python = crate::workers::python_do_sistema().await.ok_or_else(|| {
        Erro::novo("python_ausente", "Precisa do Python 3.10 ou mais novo instalado (python.org) para instalar o ComfyUI.")
    })?;
    let scripts = crate::workers::preparar_scripts(&paths.data_dir)?;
    let destino = pasta(paths);
    std::fs::create_dir_all(&destino).map_err(|e| Erro::io(&destino, e))?;
    let mut cmd = tokio::process::Command::new(&python);
    cmd.arg(scripts.join("instalar_comfyui.py")).arg(&destino).arg(c.backend).args(["--modelos", c.modelos, "--porta", &porta.to_string()]);
    if let Some(h) = c.hsa {
        cmd.args(["--hsa", h]);
    }
    if c.pouca_vram && c.backend != "cpu" {
        cmd.arg("--pouca-vram");
    }
    Ok((cmd, destino))
}

/// Instala aqui mesmo, mostrando o progresso no terminal (linha de comando).
pub async fn instalar_e_esperar(paths: &crate::paths::Paths, c: &Caminho, porta: u16) -> Resultado<Value> {
    let (mut cmd, destino) = comando_de_instalacao(paths, c, porta).await?;
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
    let (mut cmd, destino) = comando_de_instalacao(paths, c, porta).await?;
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
    let e = consultar(porta).await;
    if e.conectado {
        return Ok(e);
    }
    let inst =
        instalacao(paths).ok_or_else(|| Erro::novo("comfyui_ausente", "O ComfyUI não está instalado (Máquina → ComfyUI → Instalar)."))?;
    let python = inst["python"].as_str().unwrap_or_default();
    let dir = inst["pasta_comfyui"].as_str().unwrap_or_default();
    let mut args: Vec<String> = inst["argumentos"].as_array().into_iter().flatten().filter_map(|a| a.as_str().map(String::from)).collect();
    if let Some(i) = args.iter().position(|a| a == "--port") {
        if let Some(v) = args.get_mut(i + 1) {
            *v = porta.to_string();
        }
    }
    let log = std::fs::File::create(pasta(paths).join("comfyui.log")).map_err(|e| Erro::io(&pasta(paths), e))?;
    let mut cmd = tokio::process::Command::new(python);
    cmd.args(&args)
        .current_dir(dir)
        .stdin(std::process::Stdio::null())
        .stdout(log.try_clone().map_err(|e| Erro::io(&pasta(paths), e))?)
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

#[cfg(test)]
mod testes {
    use super::*;

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| x.to_string()).collect()
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
        assert_eq!((rx580_win.backend, rx580_win.modelos, rx580_win.pouca_vram), ("directml", "gguf", true));
        let rx580_linux = caminho_para(&deteccao(Familia::Fedora, Vendor::Amd, "Radeon RX 580", 8192, Some("gfx803")));
        assert_eq!(rx580_linux.backend, "cpu");
        assert!(rx580_linux.motivo.contains("Vulkan"));
        let rx6600 = caminho_para(&deteccao(Familia::Fedora, Vendor::Amd, "Radeon RX 6600", 8176, Some("gfx1032")));
        assert_eq!((rx6600.backend, rx6600.hsa), ("rocm", Some("10.3.0")));
        let rx9060 = caminho_para(&deteccao(Familia::Arch, Vendor::Amd, "Radeon RX 9060 XT", 16304, Some("gfx1200")));
        assert_eq!((rx9060.backend, rx9060.hsa, rx9060.modelos), ("rocm", None, "inteiro"));
        let rtx = caminho_para(&deteccao(Familia::Windows, Vendor::Nvidia, "GeForce RTX 3060", 12288, None));
        assert_eq!((rtx.backend, rtx.modelos), ("nvidia", "gguf"));
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
