//! ComfyUI local (127.0.0.1): conector testado contra um ComfyUI falso que fala a mesma API
//! (/system_stats, /models, /prompt, /history, /view). O ComfyUI de verdade no processador roda no CI.

mod comum;

use std::sync::{Arc, Mutex};

use axum::extract::{Path, Query, State};
use axum::routing::{get, post};
use axum::Json;
use fornalha_core::comfyui;
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};

// PNG 1x1 válido
const PNG: &[u8] = &[
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00,
    0x00, 0x01, 0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41, 0x54, 0x08, 0xD7, 0x63,
    0xF8, 0xCF, 0xC0, 0x00, 0x00, 0x03, 0x01, 0x01, 0x00, 0x18, 0xDD, 0x8D, 0xB0, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
    0x42, 0x60, 0x82,
];

#[derive(Default)]
struct Visto {
    fluxos: Vec<Value>,
    consultas_historico: usize,
}

type Estado = Arc<Mutex<Visto>>;

async fn comfy_falso(com_modelos: bool) -> (u16, Estado) {
    let visto: Estado = Arc::default();
    let app = axum::Router::new()
        .route(
            "/system_stats",
            get(|| async {
                Json(json!({"system": {"comfyui_version": "0.4.1", "os": "posix"},
                            "devices": [{"name": "cpu", "type": "cpu", "vram_total": 0}]}))
            }),
        )
        .route(
            "/models/{pasta}",
            get(move |Path(pasta): Path<String>| async move {
                let lista: Vec<&str> = match (com_modelos, pasta.as_str()) {
                    (true, "diffusion_models") => vec!["z_image_turbo_bf16.safetensors"],
                    (true, "text_encoders") => vec!["qwen_3_4b.safetensors"],
                    (true, "vae") => vec!["ae.safetensors"],
                    _ => vec![],
                };
                Json(json!(lista))
            }),
        )
        .route(
            "/prompt",
            post(|State(v): State<Estado>, Json(corpo): Json<Value>| async move {
                v.lock().unwrap().fluxos.push(corpo["prompt"].clone());
                Json(json!({"prompt_id": "pedido-1", "number": 1, "node_errors": {}}))
            }),
        )
        .route(
            "/history/{id}",
            get(|State(v): State<Estado>, Path(id): Path<String>| async move {
                let mut g = v.lock().unwrap();
                g.consultas_historico += 1;
                if g.consultas_historico < 2 {
                    return Json(json!({})); // ainda na fila
                }
                Json(json!({id: {"status": {"status_str": "success", "completed": true},
                    "outputs": {"10": {"images": [{"filename": "fornalha_00001_.png", "subfolder": "", "type": "output"}]}}}}))
            }),
        )
        .route(
            "/view",
            get(|Query(q): Query<std::collections::HashMap<String, String>>| async move {
                assert_eq!(q.get("filename").map(String::as_str), Some("fornalha_00001_.png"));
                PNG.to_vec()
            }),
        )
        .with_state(visto.clone());
    let l = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let porta = l.local_addr().unwrap().port();
    tokio::spawn(async move { axum::serve(l, app).await.unwrap() });
    (porta, visto)
}

#[tokio::test]
async fn comfyui_ligado_mostra_a_placa() {
    let (porta, _) = comfy_falso(true).await;
    let e = comfyui::consultar(porta).await;
    assert!(e.conectado);
    assert_eq!(e.versao.as_deref(), Some("0.4.1"));
    assert_eq!(e.dispositivos[0]["tipo"], "cpu");
    let m = comfyui::modelo_de_imagem(porta).await.expect("Z-Image Turbo instalado");
    assert_eq!(m.id, "z-image-turbo-comfyui");
}

#[tokio::test]
async fn comfyui_desligado_nao_trava() {
    let porta = {
        let l = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        l.local_addr().unwrap().port()
    };
    let t = std::time::Instant::now();
    let e = comfyui::consultar(porta).await;
    assert!(!e.conectado);
    assert!(t.elapsed().as_secs() < 4);
}

#[tokio::test]
async fn gera_imagem_pelo_fluxo_do_z_image() {
    let (porta, visto) = comfy_falso(true).await;
    let (png, info) = comfyui::gerar_imagem(porta, "templário de capa branca", 512, 512, 42, 8).await.unwrap();
    assert_eq!(png, PNG);
    assert_eq!(info["modelo"]["id"], "z-image-turbo-comfyui");
    let g = visto.lock().unwrap();
    let f = &g.fluxos[0];
    assert_eq!(f["5"]["inputs"]["text"], "templário de capa branca");
    assert_eq!(f["8"]["inputs"]["seed"], 42);
    assert_eq!(f["1"]["inputs"]["unet_name"], "z_image_turbo_bf16.safetensors");
}

#[tokio::test]
async fn sem_modelo_comercial_explica_o_que_falta() {
    let (porta, _) = comfy_falso(false).await;
    let e = comfyui::gerar_imagem(porta, "x", 512, 512, 1, 8).await.unwrap_err();
    assert_eq!(e.codigo, "comfyui_sem_modelo");
    assert!(e.mensagem.contains("qwen_3_4b"));
}

#[tokio::test]
async fn conceito_usa_o_comfyui_e_registra_a_licenca() {
    let (porta, visto) = comfy_falso(true).await;
    let tmp = tempfile::tempdir().unwrap();
    let f = Fornalha::para_testes(Paths::under(tmp.path()), comum::detection("rx580"));
    f.definir_porta_comfyui(porta).unwrap();
    f.chamar("create_project", json!({"nome": "Ordem"}), "claude-code").await.unwrap();
    let r = f.chamar("generate_concept", json!({"descricao": "templário"}), "claude-code").await.unwrap();
    let arq = std::path::PathBuf::from(r["arquivo"].as_str().unwrap());
    assert_eq!(std::fs::read(&arq).unwrap(), PNG);
    assert_eq!(visto.lock().unwrap().fluxos.len(), 1);
    let rec = f.chamar("list_receipts", json!({}), "claude-code").await.unwrap();
    let r0 = &rec["recibos"][0];
    assert_eq!(r0["modelo"]["id"], "z-image-turbo-comfyui", "{r0}");
    let st = f.chamar("get_status", json!({}), "claude-code").await.unwrap();
    assert_eq!(st["comfyui"]["estado"]["conectado"], true);
    assert_eq!(st["comfyui"]["modelo_de_imagem"]["id"], "z-image-turbo-comfyui");
}
