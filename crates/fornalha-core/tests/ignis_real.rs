//! Geração de verdade pelo Ignis 0.4.0 (cérebro, voz comercial e imagem).
//! Só roda com FORNALHA_TESTE_IGNIS=<porta> (o Ignis aberto e preparado).

mod comum;

use fornalha_core::{audio, ignis};
use serde_json::json;

fn porta() -> Option<u16> {
    std::env::var("FORNALHA_TESTE_IGNIS").ok().and_then(|p| p.parse().ok())
}

#[tokio::test]
async fn voz_comercial_de_verdade_e_curva_da_boca() {
    let Some(p) = porta() else {
        eprintln!("FORNALHA_TESTE_IGNIS não definido: teste pulado");
        return;
    };
    let wav = ignis::falar(p, "Eu sou Aren, o ferreiro de Brasa. Ninguém passa por esta ponte.", "pt", 7).await.unwrap();
    let (taxa, amostras) = audio::ler_wav_16(&wav).expect("WAV válido");
    let segundos = amostras.len() as f32 / taxa as f32;
    assert!(segundos > 1.5, "fala de verdade: {segundos} s");
    let boca = audio::curva_da_boca(taxa, &amostras, 30);
    assert!(boca.iter().any(|v| *v > 0.5) && boca.iter().any(|v| *v < 0.1), "a boca abre e fecha");
    if let Ok(d) = std::env::var("FORNALHA_TESTE_SAIDA") {
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(format!("{d}/fala_aren.wav"), &wav).unwrap();
    }
}

#[tokio::test]
async fn cerebro_escreve_a_ficha_em_json() {
    let Some(p) = porta() else {
        eprintln!("FORNALHA_TESTE_IGNIS não definido: teste pulado");
        return;
    };
    let esquema = json!({"type": "object", "additionalProperties": false,
        "properties": {"nome": {"type": "string"}, "papel": {"type": "string"}, "arma": {"type": "string", "enum": ["espada", "machado", "lanca", "martelo", "adaga", "cajado"]},
                       "fala": {"type": "string"}},
        "required": ["nome", "papel", "arma", "fala"]});
    let v = ignis::conversar_json(
        p,
        None,
        "Você cria personagens de jogo. Responda só com o JSON pedido, em português.",
        "Crie um inimigo orc para um action RPG medieval.",
        &esquema,
    )
    .await
    .unwrap();
    assert!(v["nome"].as_str().is_some_and(|s| !s.is_empty()), "{v}");
    assert!(["espada", "machado", "lanca", "martelo", "adaga", "cajado"].contains(&v["arma"].as_str().unwrap_or("")), "{v}");
}

#[tokio::test]
async fn imagem_de_verdade_quando_preparada() {
    let Some(p) = porta() else {
        eprintln!("FORNALHA_TESTE_IGNIS não definido: teste pulado");
        return;
    };
    let cap = ignis::capacidades(p).await;
    if cap["imagem"].as_array().is_none_or(|a| a.is_empty()) {
        eprintln!("imagem ainda não preparada no Ignis: teste pulado");
        return;
    }
    let (png, info) =
        ignis::gerar_imagem(p, "personagem de jogo, ferreiro medieval com machado, estilo low poly, fundo neutro", "256x256", 3, 4)
            .await
            .unwrap();
    assert_eq!(&png[1..4], b"PNG", "{info}");
    if let Ok(d) = std::env::var("FORNALHA_TESTE_SAIDA") {
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(format!("{d}/conceito_teste.png"), &png).unwrap();
    }
}

#[tokio::test]
async fn cerebro_planeja_um_pedido_livre() {
    let Some(p) = porta() else {
        eprintln!("FORNALHA_TESTE_IGNIS não definido: teste pulado");
        return;
    };
    let tmp = tempfile::tempdir().unwrap();
    let f = fornalha_core::servico::Fornalha::para_testes(fornalha_core::paths::Paths::under(tmp.path()), comum::detection("sem-placa"));
    f.definir_porta_ignis(p).unwrap();
    f.chamar("create_project", json!({"nome": "Reino de Cinzas", "genero": "action RPG"}), "claude-code").await.unwrap();
    let r = f
        .chamar(
            "plan_request",
            json!({"pedido": "Crie um orc inimigo com martelo e a música de combate, depois teste o jogo", "executar": "nao"}),
            "claude-code",
        )
        .await
        .unwrap();
    eprintln!("plano: {}", serde_json::to_string_pretty(&r).unwrap());
    let passos = r["passos"].as_array().unwrap();
    assert!(!passos.is_empty());
    let nomes: Vec<&str> = passos.iter().filter_map(|x| x["ferramenta"].as_str()).collect();
    assert!(nomes.iter().all(|n| fornalha_core::fila::FERRAMENTAS_DA_FILA.contains(n)), "{nomes:?}");
    if r["origem"] == "cerebro" {
        assert!(nomes.contains(&"create_character") || nomes.contains(&"generate_music"), "o plano do cérebro tem o pedido: {nomes:?}");
    }
}
