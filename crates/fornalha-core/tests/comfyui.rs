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
    // porta 1: ninguém escuta (uma porta livre "emprestada" podia ser pega pelo servidor falso de outro
    // teste rodando ao mesmo tempo)
    let porta = 1;
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

/// Numa placa de 8 GB, um modelo por vez: antes de gerar no ComfyUI a Fornalha pede ao Ignis para
/// soltar a memória de vídeo (POST /motor/reservar) e devolve no fim (/motor/reservar/liberar).
#[tokio::test]
async fn reserva_a_placa_no_ignis_durante_o_comfyui() {
    let (porta_comfy, _) = comfy_falso(true).await;
    let pedidos: Arc<Mutex<Vec<String>>> = Arc::default();
    let p2 = pedidos.clone();
    let p3 = pedidos.clone();
    let app = axum::Router::new()
        .route("/motor/estado", get(|| async { Json(json!({"fase": "pronto", "fase_texto": "Pronto"})) }))
        .route("/motor/versao", get(|| async { Json(json!({"app": {"nome": "Ignis", "versao": "0.4.0", "api": 1}})) }))
        .route(
            "/motor/reservar",
            post(move |Json(c): Json<Value>| {
                let p = p2.clone();
                async move {
                    p.lock().unwrap().push(format!("reservar {}", c["mb"]));
                    Json(json!({"ok": true}))
                }
            }),
        )
        .route(
            "/motor/reservar/liberar",
            post(move || {
                let p = p3.clone();
                async move {
                    p.lock().unwrap().push("liberar".into());
                    Json(json!({"ok": true}))
                }
            }),
        );
    let l = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let porta_ignis = l.local_addr().unwrap().port();
    tokio::spawn(async move { axum::serve(l, app).await.unwrap() });
    let tmp = tempfile::tempdir().unwrap();
    let f = Fornalha::para_testes(Paths::under(tmp.path()), comum::detection("rx580"));
    f.definir_porta_comfyui(porta_comfy).unwrap();
    f.definir_porta_ignis(porta_ignis).unwrap();
    f.chamar("create_project", json!({"nome": "Placa"}), "claude-code").await.unwrap();
    f.chamar("generate_concept", json!({"descricao": "templário"}), "claude-code").await.unwrap();
    let p = pedidos.lock().unwrap().clone();
    assert_eq!(p, vec!["reservar 15000".to_string(), "liberar".to_string()], "{p:?}");
}

/// Folha de modelo (frente, perfil, costas) pelo ComfyUI: só com placa; no processador, só no nível
/// Máximo (imagem larga demora). O pedido descreve a pose A e os dedos separados.
#[tokio::test]
async fn folha_de_modelo_pelo_comfyui() {
    let (porta, visto) = comfy_falso(true).await; // o falso diz que só tem processador
    let tmp = tempfile::tempdir().unwrap();
    let f = Fornalha::para_testes(Paths::under(tmp.path()), comum::detection("rx580"));
    f.definir_porta_comfyui(porta).unwrap();
    f.chamar("create_project", json!({"nome": "Folha"}), "claude-code").await.unwrap();
    let p = f.projeto(None).unwrap();
    let ficha = json!({"nome": "Aren", "tipo": "humano", "descricao": "cavaleiro de capa", "cor_roupa": "#ffffff", "cor_roupa_secundaria": "#aa0000"});
    let destino = p.raiz.join("Characters/aren/folha_de_modelo.png");
    let nada = fornalha_core::geracao::gerar_folha_de_modelo(&f, &p, &ficha, &destino, 3, "claude-code").await.unwrap();
    assert!(nada.is_none(), "no processador e fora do Máximo, não gera");
    f.chamar("update_project", json!({"alteracoes": {"nivel": "maximo"}}), "claude-code").await.unwrap();
    let p = f.projeto(None).unwrap();
    let arq = fornalha_core::geracao::gerar_folha_de_modelo(&f, &p, &ficha, &destino, 3, "claude-code").await.unwrap().unwrap();
    assert_eq!(std::fs::read(&arq).unwrap(), PNG);
    let g = visto.lock().unwrap();
    let fluxo = g.fluxos.last().unwrap();
    let texto = fluxo["5"]["inputs"]["text"].as_str().unwrap();
    assert!(texto.contains("pose A") && texto.contains("dedos separados") && texto.contains("vista de costas"), "{texto}");
    assert_eq!(fluxo["7"]["inputs"]["width"], 768);
    assert_eq!(fluxo["7"]["inputs"]["height"], 320);
}

/// Motor Vulkan (stable-diffusion.cpp) na RX 580: sem ComfyUI aberto, a Fornalha chama o sd-cli que o
/// instalador deixou (aqui um falso que grava os argumentos e devolve o PNG), com o recibo do modelo
/// "pelo Vulkan" e a folha de modelo larga quando o Vulkan enxerga a placa.
#[cfg(unix)]
#[tokio::test]
async fn motor_vulkan_gera_conceito_e_folha() {
    use std::os::unix::fs::PermissionsExt;
    let tmp = tempfile::tempdir().unwrap();
    let paths = Paths::under(tmp.path());
    let f = Fornalha::para_testes(paths.clone(), comum::detection("rx580"));
    let pasta = comfyui::pasta(&paths);
    let modelos = pasta.join("ComfyUI/models");
    std::fs::create_dir_all(modelos.join("diffusion_models")).unwrap();
    std::fs::create_dir_all(modelos.join("text_encoders")).unwrap();
    std::fs::create_dir_all(modelos.join("vae")).unwrap();
    for m in ["diffusion_models/z_image_turbo-Q4_K_M.gguf", "text_encoders/Qwen3-4B-Q4_K_M.gguf", "vae/ae.safetensors"] {
        std::fs::write(modelos.join(m), b"x").unwrap();
    }
    let png = tmp.path().join("modelo.png");
    std::fs::write(&png, PNG).unwrap();
    let args_log = tmp.path().join("args.txt");
    let sd = pasta.join("sdcpp/sd-cli");
    std::fs::create_dir_all(sd.parent().unwrap()).unwrap();
    std::fs::write(
        &sd,
        format!(
            "#!/bin/sh\nif [ \"$1\" = \"--list-devices\" ]; then printf 'Vulkan0\\tAMD Radeon RX 580 Series\\nCPU\\tfalso\\n'; exit 0; fi\n\
             printf '%s\\n' \"$@\" >> '{log}'\necho '---' >> '{log}'\nsaida=''\nwhile [ $# -gt 0 ]; do [ \"$1\" = \"-o\" ] && saida=\"$2\"; shift; done\n\
             echo 'using Vulkan0'\ncp '{png}' \"$saida\"\n",
            log = args_log.display(),
            png = png.display()
        ),
    )
    .unwrap();
    std::fs::set_permissions(&sd, std::fs::Permissions::from_mode(0o755)).unwrap();
    std::fs::write(
        pasta.join("instalacao.json"),
        serde_json::to_string(&json!({
            "backend": "vulkan", "motor": "sdcpp", "sd_cli": sd, "sdcpp_versao": "master-1045-6225bf8", "pouca_vram": true,
            "difusao": modelos.join("diffusion_models/z_image_turbo-Q4_K_M.gguf"),
            "texto": modelos.join("text_encoders/Qwen3-4B-Q4_K_M.gguf"),
            "vae": modelos.join("vae/ae.safetensors"),
        }))
        .unwrap(),
    )
    .unwrap();
    let m = comfyui::motor_vulkan(&paths).expect("motor Vulkan instalado");
    assert_eq!(comfyui::dispositivos_vulkan(&m).await, vec!["Vulkan0\tAMD Radeon RX 580 Series".to_string(), "CPU\tfalso".to_string()]);
    // abrir não se aplica ao motor Vulkan (não é servidor)
    assert_eq!(comfyui::abrir(&paths, 1).await.unwrap_err().codigo, "motor_vulkan");

    f.chamar("create_project", json!({"nome": "Vulkan"}), "claude-code").await.unwrap();
    let r = f.chamar("generate_concept", json!({"descricao": "templário"}), "claude-code").await.unwrap();
    assert_eq!(std::fs::read(r["arquivo"].as_str().unwrap()).unwrap(), PNG);
    let rec = f.chamar("list_receipts", json!({}), "claude-code").await.unwrap();
    assert_eq!(rec["recibos"][0]["modelo"]["id"], "z-image-turbo-gguf-vulkan", "{rec}");
    let log = std::fs::read_to_string(&args_log).unwrap();
    let primeiro: Vec<&str> = log.split("---").next().unwrap().lines().collect();
    let par = |k: &str| primeiro.iter().position(|x| *x == k).map(|i| primeiro[i + 1]);
    assert_eq!(par("-W"), Some("1024"), "placa vista pelo Vulkan: 1024 px\n{log}");
    assert_eq!(par("--cfg-scale"), Some("1.0"));
    assert!(primeiro.contains(&"--vae-tiling"), "8 GB: VAE em blocos");
    assert!(par("-p").unwrap().contains("templário"));

    // folha de modelo larga (o Vulkan enxerga a placa: não precisa do Máximo)
    let p = f.projeto(None).unwrap();
    let ficha =
        json!({"nome": "Aren", "tipo": "humano", "descricao": "cavaleiro", "cor_roupa": "#ffffff", "cor_roupa_secundaria": "#aa0000"});
    let destino = p.raiz.join("Characters/aren/folha_de_modelo.png");
    let arq = fornalha_core::geracao::gerar_folha_de_modelo(&f, &p, &ficha, &destino, 3, "claude-code").await.unwrap().unwrap();
    assert_eq!(std::fs::read(&arq).unwrap(), PNG);
    let log = std::fs::read_to_string(&args_log).unwrap();
    let segundo: Vec<&str> = log.split("---").nth(1).unwrap().lines().filter(|l| !l.is_empty()).collect();
    let par2 = |k: &str| segundo.iter().position(|x| *x == k).map(|i| segundo[i + 1]);
    assert_eq!((par2("-W"), par2("-H")), (Some("1536"), Some("640")), "{log}");
    let st = f.chamar("get_status", json!({}), "claude-code").await.unwrap();
    assert_eq!(st["comfyui"]["instalacao"]["instalacao"]["motor"], "sdcpp");
}
