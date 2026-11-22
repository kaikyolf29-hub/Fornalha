//! ComfyUI de verdade (só roda com FORNALHA_TESTE_COMFYUI=<porta>, como no CI "ComfyUI no processador").
//! Gera referências de personagem, criatura e cenário com o Z-Image Turbo e grava em
//! FORNALHA_TESTE_SAIDA (vira artefato do CI para o criador ver a qualidade).

use fornalha_core::comfyui;

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
    let Some(porta) = std::env::var("FORNALHA_TESTE_COMFYUI").ok().and_then(|p| p.parse::<u16>().ok()) else {
        eprintln!("FORNALHA_TESTE_COMFYUI não definido: teste pulado");
        return;
    };
    let saida = std::path::PathBuf::from(std::env::var("FORNALHA_TESTE_SAIDA").unwrap_or_else(|_| "comfyui-saida".into()));
    std::fs::create_dir_all(&saida).unwrap();
    let e = comfyui::consultar(porta).await;
    assert!(e.conectado, "o ComfyUI não respondeu na porta {porta}");
    eprintln!("ComfyUI {:?} em {:?}", e.versao, e.dispositivos);
    for pasta in ["diffusion_models", "text_encoders", "vae", "unet_gguf", "clip_gguf"] {
        eprintln!("{pasta}: {:?}", comfyui::modelos(porta, pasta).await);
    }
    eprintln!("nós GGUF: {} {}", comfyui::tem_no(porta, "UnetLoaderGGUF").await, comfyui::tem_no(porta, "CLIPLoaderGGUF").await);
    let m = comfyui::modelo_de_imagem(porta).await.expect("modelo de imagem instalado (Z-Image Turbo)");
    eprintln!("modelo: {m:?}");
    let lado: u32 = std::env::var("FORNALHA_TESTE_LADO").ok().and_then(|v| v.parse().ok()).unwrap_or(512);
    let mut relatorio = vec![];
    for (i, (nome, prompt)) in PEDIDOS.iter().enumerate() {
        let (png, info) = comfyui::gerar_imagem(porta, prompt, lado, lado, 1000 + i as u64, 8).await.unwrap();
        assert!(png.starts_with(&[0x89, b'P', b'N', b'G']), "{nome}: não é PNG");
        assert!(png.len() > 20_000, "{nome}: imagem pequena demais ({} bytes)", png.len());
        std::fs::write(saida.join(format!("{nome}.png")), &png).unwrap();
        eprintln!("{nome}: {:.0} s", info["segundos"].as_f64().unwrap_or(0.0));
        relatorio.push(serde_json::json!({"nome": nome, "prompt": prompt, "info": info}));
    }
    // folha de modelo (frente, perfil, costas) para guiar a malha: larga e baixa
    let folha = "game character model sheet of a medieval Knight Templar: front view, side view and back view of the same character, \
                 full body, A-pose with arms away from the body, legs slightly apart, open hands with separated fingers, symmetric, \
                 white surcoat with red cross, chainmail, neutral flat gray background, even lighting, consistent design";
    let (png, info) = comfyui::gerar_imagem(porta, folha, lado * 3 / 2, lado * 5 / 8, 2000, 8).await.unwrap();
    assert!(png.starts_with(&[0x89, b'P', b'N', b'G']));
    std::fs::write(saida.join("templario_folha.png"), &png).unwrap();
    eprintln!("folha de modelo: {:.0} s", info["segundos"].as_f64().unwrap_or(0.0));
    relatorio.push(serde_json::json!({"nome": "templario_folha", "prompt": folha, "info": info}));
    std::fs::write(saida.join("relatorio.json"), serde_json::to_string_pretty(&relatorio).unwrap()).unwrap();
}
