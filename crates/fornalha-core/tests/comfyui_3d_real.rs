//! 3D pela IA de verdade (só roda com FORNALHA_TESTE_COMFYUI_3D=<porta>, como no CI "ComfyUI 3D"):
//! a imagem de conceito do templário (gerada pela própria Fornalha com o Z-Image Turbo) vira uma
//! malha texturizada pelo TRELLIS.2 nos nós nativos do ComfyUI. O .glb vai para FORNALHA_TESTE_SAIDA.

use fornalha_core::comfyui;

#[tokio::test]
async fn trellis2_transforma_imagem_em_malha() {
    let Some(porta) = std::env::var("FORNALHA_TESTE_COMFYUI_3D").ok().and_then(|p| p.parse::<u16>().ok()) else {
        eprintln!("FORNALHA_TESTE_COMFYUI_3D não definido: teste pulado");
        return;
    };
    let saida = std::path::PathBuf::from(std::env::var("FORNALHA_TESTE_SAIDA").unwrap_or_else(|_| "comfyui-3d-saida".into()));
    std::fs::create_dir_all(&saida).unwrap();
    // o fluxo convertido (para conferir os nós, mesmo se a geração falhar)
    let info: serde_json::Value = reqwest::get(format!("http://127.0.0.1:{porta}/object_info")).await.unwrap().json().await.unwrap();
    let fluxo = comfyui::fluxo_trellis2(&info, "templario_conceito.png", true, 7).unwrap();
    std::fs::write(saida.join("fluxo_api.json"), serde_json::to_string_pretty(&fluxo).unwrap()).unwrap();
    eprintln!(
        "fluxo com {} nós: {:?}",
        fluxo.as_object().unwrap().len(),
        fluxo.as_object().unwrap().values().map(|n| n["class_type"].as_str().unwrap_or("")).collect::<Vec<_>>()
    );
    // FORNALHA_TESTE_PEDIDO: gera o conceito antes pelo motor de imagem (Z-Image) e faz o 3D dele;
    // sem ele, usa o conceito do templário guardado no repositório
    let png = match std::env::var("FORNALHA_TESTE_PEDIDO").ok().filter(|p| !p.trim().is_empty()) {
        Some(pedido) => {
            let largura: u32 = std::env::var("FORNALHA_TESTE_LARGURA").ok().and_then(|v| v.parse().ok()).unwrap_or(640);
            let altura: u32 = std::env::var("FORNALHA_TESTE_ALTURA").ok().and_then(|v| v.parse().ok()).unwrap_or(960);
            let (png, info) = comfyui::gerar_imagem(porta, &pedido, largura, altura, 11, 8).await.unwrap();
            eprintln!("conceito: {:.0} s", info["segundos"].as_f64().unwrap_or(0.0));
            std::fs::write(saida.join("conceito.png"), &png).unwrap();
            std::fs::write(saida.join("pedido.txt"), &pedido).unwrap();
            png
        }
        None => std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/dados/templario_conceito.png")).unwrap(),
    };
    let horas: u64 = std::env::var("FORNALHA_TESTE_HORAS").ok().and_then(|h| h.parse().ok()).unwrap_or(5);
    let (glb, info) = comfyui::gerar_3d(porta, png, "templario_conceito.png", 7, horas * 3600).await.unwrap();
    assert_eq!(&glb[0..4], b"glTF", "não é glb");
    assert!(glb.len() > 100_000, "malha pequena demais ({} bytes)", glb.len());
    std::fs::write(saida.join("templario_trellis2.glb"), &glb).unwrap();
    std::fs::write(saida.join("relatorio.json"), serde_json::to_string_pretty(&info).unwrap()).unwrap();
    eprintln!("malha: {} KB em {:.0} s", glb.len() / 1024, info["segundos"].as_f64().unwrap_or(0.0));
}
