//! Um item do jogo pelo caminho grátis, de verdade (só roda com FORNALHA_TESTE_ITEM=<pedido>, como no CI
//! "Itens pela IA"): o pedido vira a imagem de conceito pelo Z-Image no ComfyUI do processador
//! (FORNALHA_TESTE_COMFYUI=<porta>), o conceito vira malha pelo TRELLIS.2 (fluxo reduzido no CI), a
//! textura é refeita pelas quatro vistas de objeto e o item é limpo pelo Blender (tamanho, pivô,
//! triângulos, colisão). Grava em FORNALHA_TESTE_SAIDA o conceito, as malhas, as vistas e as folhas de
//! antes e depois.

use std::path::PathBuf;
use std::time::Duration;

use fornalha_core::externas::{self, Programa};
use serde_json::json;

#[tokio::test]
async fn item_do_jogo_pelo_caminho_gratis() {
    let Some(pedido) = std::env::var("FORNALHA_TESTE_ITEM").ok().filter(|p| !p.trim().is_empty()) else {
        eprintln!("FORNALHA_TESTE_ITEM não definido: teste pulado");
        return;
    };
    let porta: u16 = std::env::var("FORNALHA_TESTE_COMFYUI").ok().and_then(|p| p.parse().ok()).expect("FORNALHA_TESTE_COMFYUI=<porta>");
    let blender = externas::achar_para_teste(Programa::Blender).await.expect("precisa do Blender (FORNALHA_TESTE_BLENDER)");
    let saida = PathBuf::from(std::env::var("FORNALHA_TESTE_SAIDA").unwrap_or_else(|_| "item-saida".into()));
    let dados = saida.join("dados");
    std::fs::create_dir_all(&dados).unwrap();
    let altura: f64 = std::env::var("FORNALHA_TESTE_ALTURA_M").ok().and_then(|v| v.parse().ok()).unwrap_or(1.0);
    let tipo = std::env::var("FORNALHA_TESTE_TIPO").unwrap_or_else(|_| "objeto".into());
    let inicio = std::time::Instant::now();

    // 1. o conceito (o mesmo pedido que o generate_3d monta, sem o estilo da bíblia)
    let o_que = if tipo == "arma" {
        "Uma arma só, inteira, de pé e reta, vista de frente"
    } else {
        "Um objeto só, inteiro, apoiado no chão, vista de frente e reto"
    };
    let prompt = format!(
        "realista, muito detalhado, asset de jogo AAA. {o_que}, centralizado, sem pessoas, sem texto, sem moldura, fundo cinza claro liso, \
         luz suave e uniforme, sombra leve embaixo. {pedido}"
    );
    let (conceito, info_img) = fornalha_core::comfyui::gerar_imagem(porta, &prompt, 768, 768, 11, 8).await.unwrap();
    let arq_conceito = saida.join("conceito.png");
    std::fs::write(&arq_conceito, &conceito).unwrap();
    eprintln!("conceito: {:.0} s", info_img["segundos"].as_f64().unwrap_or(0.0));

    // 2. a malha pelo TRELLIS.2 no processador
    let horas: u64 = std::env::var("FORNALHA_TESTE_HORAS").ok().and_then(|h| h.parse().ok()).unwrap_or(4);
    let (glb, info_3d) = fornalha_core::comfyui::gerar_3d(porta, conceito, "item_conceito.png", 7, horas * 3600, false).await.unwrap();
    let alta = saida.join("item_ia_alta.glb");
    std::fs::write(&alta, &glb).unwrap();
    eprintln!("malha: {} KB em {:.0} s", glb.len() / 1024, info_3d["segundos"].as_f64().unwrap_or(0.0));

    // 3. antes: a folha da malha como saiu da IA
    fornalha_core::forja::rodar(
        &blender,
        &dados,
        &json!({"tarefa": "projetar_folha", "entrada": alta, "saida": saida.join("antes_folha.png")}),
        Duration::from_secs(1200),
    )
    .await
    .unwrap();

    // 4. as quatro vistas de objeto
    let com_vistas = saida.join("item_ia_vistas.glb");
    let vistas = fornalha_core::vistas::refinar_textura_de(
        &blender,
        &dados,
        Some(porta),
        &alta,
        Some(&arq_conceito),
        &pedido,
        &saida.join("vistas"),
        7,
        &com_vistas,
        2048,
        Some(&saida.join("depois_folha.png")),
        fornalha_core::vistas::Assunto::Objeto,
    )
    .await
    .unwrap();

    // 5. a limpeza do item (como o generate_3d faz)
    let item = saida.join("item.glb");
    let r = fornalha_core::forja::rodar(
        &blender,
        &dados,
        &json!({"tarefa": "limpar", "entrada": com_vistas, "saida": item, "nome": "item", "altura_m": altura, "triangulos_max": 20000,
                "colisao": true, "previa": true, "amostras": 16}),
        Duration::from_secs(1800),
    )
    .await
    .unwrap();
    let relatorio = json!({"pedido": pedido, "conceito": info_img, "3d": info_3d, "vistas": vistas, "limpar": r,
                           "segundos": inicio.elapsed().as_secs_f64()});
    std::fs::write(saida.join("relatorio.json"), serde_json::to_string_pretty(&relatorio).unwrap()).unwrap();
    assert!(item.is_file(), "sem o item limpo: {r}");
    let tris = r["estatisticas"]["triangulos"].as_u64().unwrap_or(0);
    assert!(tris > 500 && tris <= 20_500, "triângulos fora do esperado: {tris}");
    // o refino das vistas de lado e de costas rodou no motor de imagem
    let n = vistas["refinadas"].as_object().map(|m| m.len()).unwrap_or(0);
    assert!(n >= 3, "só {n} vistas refinadas: {}", vistas["avisos"]);
}
