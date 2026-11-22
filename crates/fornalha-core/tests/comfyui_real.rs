//! Motor de imagem de verdade (só roda no CI "ComfyUI no processador"): com FORNALHA_TESTE_COMFYUI=<porta>
//! fala com o ComfyUI aberto; com FORNALHA_TESTE_VULKAN=1 chama o motor Vulkan (stable-diffusion.cpp)
//! instalado em FORNALHA_HOME. Gera referências de personagem, criatura e cenário com o Z-Image Turbo
//! e grava em FORNALHA_TESTE_SAIDA (vira artefato do CI para o criador ver a qualidade).

use fornalha_core::comfyui;
use serde_json::Value;

enum Motor {
    Comfy(u16),
    Vulkan(comfyui::MotorVulkan),
}

impl Motor {
    async fn gerar(&self, prompt: &str, largura: u32, altura: u32, semente: u64) -> (Vec<u8>, Value) {
        match self {
            Motor::Comfy(porta) => comfyui::gerar_imagem(*porta, prompt, largura, altura, semente, 8).await.unwrap(),
            Motor::Vulkan(m) => comfyui::gerar_imagem_vulkan(m, prompt, largura, altura, semente, 8).await.unwrap(),
        }
    }
}

const PEDIDOS: &[(&str, &str)] = &[
    (
        "templario",
        "full body concept art of a medieval Knight Templar, white surcoat with a red cross pattee, chainmail hauberk and coif, \
         great helm in hand, red leather belts with brass buckles, long white cape, realistic game character, \
         neutral gray studio background, front view, AAA video game quality",
    ),
    (
        "dragao",
        "photorealistic ancient dragon creature design, huge scaled body, horned head, leathery torn wings, standing on rocks, \
         dark fantasy game creature, dramatic lighting, AAA video game concept art",
    ),
    (
        "castelo",
        "dark fantasy gothic castle courtyard at dusk, wet cobblestones, torches, fog, ruined stone walls, \
         game environment concept art, souls-like atmosphere, highly detailed",
    ),
];

#[tokio::test]
async fn comfyui_de_verdade_gera_referencias() {
    let saida = std::path::PathBuf::from(std::env::var("FORNALHA_TESTE_SAIDA").unwrap_or_else(|_| "comfyui-saida".into()));
    let motor = if std::env::var("FORNALHA_TESTE_VULKAN").is_ok() {
        let paths = fornalha_core::paths::Paths::from_env();
        let m = comfyui::motor_vulkan(&paths)
            .expect("motor Vulkan instalado em FORNALHA_HOME (fornalha-cli comfyui instalar --backend vulkan)");
        eprintln!("motor Vulkan {} — dispositivos: {:?}", m.versao, comfyui::dispositivos_vulkan(&m).await);
        Motor::Vulkan(m)
    } else if let Some(porta) = std::env::var("FORNALHA_TESTE_COMFYUI").ok().and_then(|p| p.parse::<u16>().ok()) {
        let e = comfyui::consultar(porta).await;
        assert!(e.conectado, "o ComfyUI não respondeu na porta {porta}");
        eprintln!("ComfyUI {:?} em {:?}", e.versao, e.dispositivos);
        for pasta in ["diffusion_models", "text_encoders", "vae", "unet_gguf", "clip_gguf"] {
            eprintln!("{pasta}: {:?}", comfyui::modelos(porta, pasta).await);
        }
        eprintln!("nós GGUF: {} {}", comfyui::tem_no(porta, "UnetLoaderGGUF").await, comfyui::tem_no(porta, "CLIPLoaderGGUF").await);
        let m = comfyui::modelo_de_imagem(porta).await.expect("modelo de imagem instalado (Z-Image Turbo)");
        eprintln!("modelo: {m:?}");
        Motor::Comfy(porta)
    } else {
        eprintln!("FORNALHA_TESTE_COMFYUI / FORNALHA_TESTE_VULKAN não definidos: teste pulado");
        return;
    };
    std::fs::create_dir_all(&saida).unwrap();
    let lado: u32 = std::env::var("FORNALHA_TESTE_LADO").ok().and_then(|v| v.parse().ok()).unwrap_or(512);
    let mut relatorio = vec![];
    // FORNALHA_TESTE_SO_UM: só a primeira imagem (prova rápida de um caminho novo ou lento)
    let so_um = std::env::var("FORNALHA_TESTE_SO_UM").is_ok();
    for (i, (nome, prompt)) in PEDIDOS.iter().enumerate().take(if so_um { 1 } else { PEDIDOS.len() }) {
        let (png, info) = motor.gerar(prompt, lado, lado, 1000 + i as u64).await;
        assert!(png.starts_with(&[0x89, b'P', b'N', b'G']), "{nome}: não é PNG");
        assert!(png.len() > 20_000, "{nome}: imagem pequena demais ({} bytes)", png.len());
        std::fs::write(saida.join(format!("{nome}.png")), &png).unwrap();
        eprintln!("{nome}: {:.0} s", info["segundos"].as_f64().unwrap_or(0.0));
        relatorio.push(serde_json::json!({"nome": nome, "prompt": prompt, "info": info}));
    }
    if so_um {
        std::fs::write(saida.join("relatorio.json"), serde_json::to_string_pretty(&relatorio).unwrap()).unwrap();
        return;
    }
    // folha de modelo (frente, perfil, costas) para guiar a malha: larga e baixa
    let folha = "game character model sheet of a medieval Knight Templar: front view, side view and back view of the same character, \
                 full body, A-pose with arms away from the body, legs slightly apart, open hands with separated fingers, symmetric, \
                 white surcoat with red cross, chainmail, neutral flat gray background, even lighting, consistent design";
    let (png, info) = motor.gerar(folha, lado * 3 / 2, lado * 5 / 8, 2000).await;
    assert!(png.starts_with(&[0x89, b'P', b'N', b'G']));
    std::fs::write(saida.join("templario_folha.png"), &png).unwrap();
    eprintln!("folha de modelo: {:.0} s", info["segundos"].as_f64().unwrap_or(0.0));
    relatorio.push(serde_json::json!({"nome": "templario_folha", "prompt": folha, "info": info}));
    std::fs::write(saida.join("relatorio.json"), serde_json::to_string_pretty(&relatorio).unwrap()).unwrap();
}
