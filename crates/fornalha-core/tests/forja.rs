//! A Forja de verdade no Blender: personagem com esqueleto e animações, arma,
//! objeto, mundo em blockout, limpeza e esqueleto em malha de fora.
//! Roda quando o Blender está nesta máquina (o CI instala); senão avisa e pula.

use std::time::Duration;

use fornalha_core::externas::{self, Programa};
use fornalha_core::forja;
use serde_json::json;

macro_rules! blender_ou_pula {
    () => {
        match externas::achar_para_teste(Programa::Blender).await {
            Some(b) => b,
            None => {
                eprintln!("Blender não encontrado: teste pulado (defina FORNALHA_TESTE_BLENDER)");
                return;
            }
        }
    };
}

const TEMPO: Duration = Duration::from_secs(600);

#[tokio::test]
async fn personagem_com_esqueleto_animacoes_e_arma() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("Characters/aren/aren.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "personagem", "saida": saida, "amostras": 8,
                "personagem": {"id": "aren", "tipo": "humano", "arma": "machado", "armadura": "leve", "capa": true}}),
        TEMPO,
    )
    .await
    .unwrap();
    assert!(saida.is_file());
    let st = &r["estatisticas"];
    assert!(st["triangulos"].as_u64().unwrap() > 300, "{st}");
    let ossos: Vec<&str> = st["nomes_dos_ossos"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    for o in ["Hips", "Spine", "Chest", "Head", "LeftUpperArm", "RightHand", "LeftUpperLeg", "RightFoot"] {
        assert!(ossos.contains(&o), "faltou o osso {o}");
    }
    let anims: Vec<&str> = st["animacoes"].as_array().unwrap().iter().map(|a| a["nome"].as_str().unwrap()).collect();
    for a in ["parado", "andar", "correr", "pular", "atacar", "defender", "esquivar", "dano", "morrer"] {
        assert!(anims.contains(&a), "faltou a animação {a}: {anims:?}");
    }
    let altura = st["altura_m"].as_f64().unwrap();
    assert!((1.6..2.1).contains(&altura), "escala real: {altura} m");
    assert!(std::path::Path::new(r["arquivos"]["previa"].as_str().unwrap()).is_file());
    // o glTF leva as animações de verdade
    let glb = std::fs::read(&saida).unwrap();
    let json_len = u32::from_le_bytes(glb[12..16].try_into().unwrap()) as usize;
    let gltf: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
    assert!(gltf["animations"].as_array().unwrap().len() >= 9);
    assert_eq!(gltf["skins"].as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn tipos_diferentes_saem_diferentes() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let mut alturas = Vec::new();
    for tipo in ["goblin", "orc"] {
        let r = forja::rodar(
            &blender,
            tmp.path(),
            &json!({"tarefa": "personagem", "saida": tmp.path().join(format!("{tipo}.glb")), "previa": false, "animacoes": ["parado"],
                    "personagem": {"id": tipo, "tipo": tipo, "arma": "adaga"}}),
            TEMPO,
        )
        .await
        .unwrap();
        alturas.push(r["estatisticas"]["altura_m"].as_f64().unwrap());
    }
    assert!(alturas[0] < 1.4 && alturas[1] > 1.8, "goblin baixo e orc alto: {alturas:?}");
}

#[tokio::test]
async fn arma_e_objeto_com_colisao() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    for (tarefa, campo, tipo) in [("arma", "arma", "espada"), ("objeto", "objeto", "barril")] {
        let saida = tmp.path().join(format!("{tipo}.glb"));
        let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": tarefa, "saida": saida, "amostras": 6, campo: {"tipo": tipo}}), TEMPO)
            .await
            .unwrap();
        assert!(saida.is_file(), "{tipo}");
        assert!(r["estatisticas"]["triangulos"].as_u64().unwrap() > 20);
        let glb = std::fs::read(&saida).unwrap();
        assert!(String::from_utf8_lossy(&glb).contains("-colonly"), "{tipo} leva a caixa de colisão");
    }
}

#[tokio::test]
async fn mundo_em_blockout_com_colisao_e_pontos() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("World/blockout.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "mundo", "saida": saida, "amostras": 4,
                "mundo": {"seed": 5, "areas": [{"id": "vila", "tipo": "vila"}, {"id": "masmorra", "tipo": "masmorra"}, {"id": "arena", "tipo": "arena"}]}}),
        TEMPO,
    )
    .await
    .unwrap();
    assert!(saida.is_file());
    let st = &r["estatisticas"];
    assert_eq!(st["areas"], 3);
    assert!(st["colisoes"].as_u64().unwrap() > 20, "{st}");
    let info: serde_json::Value = serde_json::from_slice(&std::fs::read(r["arquivos"]["info"].as_str().unwrap()).unwrap()).unwrap();
    assert!(info["spawn_inimigos"].as_array().unwrap().len() >= 4);
    assert_eq!(info["spawn_jogador"].as_array().unwrap().len(), 3);
    assert!(std::path::Path::new(r["arquivos"]["mapa"].as_str().unwrap()).is_file());
}

#[tokio::test]
async fn malha_de_fora_ganha_limpeza_esqueleto_e_animacoes() {
    // Simula o que vem do TRELLIS.2: uma malha parada, sem esqueleto e em escala errada.
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let base = tmp.path().join("base.glb");
    forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "personagem", "saida": base, "previa": false, "animacoes": ["parado"], "personagem": {"id": "base"}}),
        TEMPO,
    )
    .await
    .unwrap();
    let parada = tmp.path().join("parada.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "limpar", "entrada": base, "saida": parada, "altura_m": 1.7, "triangulos_max": 500, "previa": false, "colisao": false}),
        TEMPO,
    )
    .await
    .unwrap();
    let st = &r["estatisticas"];
    assert!((st["altura_m"].as_f64().unwrap() - 1.7).abs() < 0.02, "escala real: {st}");
    assert!(st["triangulos_depois"].as_u64().unwrap() <= 520, "decimada: {st}");
    let com_rig = tmp.path().join("com_rig.glb");
    let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "rig", "entrada": parada, "saida": com_rig, "previa": false}), TEMPO)
        .await
        .unwrap();
    let st = &r["estatisticas"];
    assert_eq!(st["ossos"], 23);
    assert!(st["animacoes"].as_array().unwrap().len() >= 9);
}
