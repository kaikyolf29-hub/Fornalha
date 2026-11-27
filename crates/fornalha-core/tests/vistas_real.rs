//! Quatro vistas de verdade (só roda com FORNALHA_TESTE_VISTAS_MALHA, como no CI "Quatro vistas"): a
//! malha do TRELLIS.2 feita no processador (com o conceito dela) ganha a textura refeita pelas vistas — a
//! frente pelo conceito, lados e costas refinados pelo Z-Image no ComfyUI (FORNALHA_TESTE_COMFYUI=<porta>)
//! e o rosto em close. Grava em FORNALHA_TESTE_SAIDA a malha nova, as vistas, as refinadas e as folhas de
//! antes e depois.

use std::path::PathBuf;
use std::time::Duration;

use fornalha_core::externas::{self, Programa};
use serde_json::json;

#[tokio::test]
async fn quatro_vistas_deixam_a_textura_nitida() {
    let Some(malha) = std::env::var_os("FORNALHA_TESTE_VISTAS_MALHA").map(PathBuf::from) else {
        eprintln!("FORNALHA_TESTE_VISTAS_MALHA não definido: teste pulado");
        return;
    };
    let blender = externas::achar_para_teste(Programa::Blender).await.expect("precisa do Blender (FORNALHA_TESTE_BLENDER)");
    let conceito = std::env::var_os("FORNALHA_TESTE_VISTAS_CONCEITO").map(PathBuf::from);
    let descricao = std::env::var("FORNALHA_TESTE_VISTAS_PEDIDO").unwrap_or_default();
    let porta = std::env::var("FORNALHA_TESTE_COMFYUI").ok().and_then(|p| p.parse::<u16>().ok());
    let saida = PathBuf::from(std::env::var("FORNALHA_TESTE_SAIDA").unwrap_or_else(|_| "vistas-saida".into()));
    std::fs::create_dir_all(&saida).unwrap();
    let dados = saida.join("dados");
    std::fs::create_dir_all(&dados).unwrap();
    // antes: a folha da malha como saiu da IA
    let antes = saida.join("antes_folha.png");
    fornalha_core::forja::rodar(
        &blender,
        &dados,
        &json!({"tarefa": "projetar_folha", "entrada": malha, "saida": antes}),
        Duration::from_secs(1200),
    )
    .await
    .unwrap();
    let inicio = std::time::Instant::now();
    let r = fornalha_core::vistas::refinar_textura(
        &blender,
        &dados,
        porta,
        &malha,
        conceito.as_deref(),
        &descricao,
        &saida.join("vistas"),
        7,
        &saida.join("malha_com_vistas.glb"),
        fornalha_core::vistas::lado_da_textura(std::env::var("FORNALHA_TESTE_NIVEL").is_ok_and(|n| n == "maximo")),
        Some(&saida.join("depois_folha.png")),
    )
    .await
    .unwrap();
    eprintln!("quatro vistas em {:.0} s: {}", inicio.elapsed().as_secs_f64(), serde_json::to_string_pretty(&r).unwrap());
    std::fs::write(saida.join("relatorio.json"), serde_json::to_string_pretty(&r).unwrap()).unwrap();
    assert!(saida.join("malha_com_vistas.glb").is_file());
    assert!(saida.join("depois_folha.png").is_file());
    let cob = &r["projecao"]["malhas"][0]["cobertura"];
    assert!(cob["frente"].as_f64().unwrap_or(0.0) > 0.2, "a frente quase não pegou: {cob}");
    if porta.is_some() {
        // com o motor de imagem, os dois lados, as costas e o rosto voltam refinados
        let n = r["refinadas"].as_object().map(|m| m.len()).unwrap_or(0);
        assert!(n >= 3, "só {n} vistas refinadas: {}", r["avisos"]);
    }
}
