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

#[test]
fn todo_script_do_blender_vai_dentro_da_fornalha() {
    let tmp = tempfile::tempdir().unwrap();
    let principal = fornalha_core::forja::preparar_scripts(tmp.path()).unwrap();
    let pasta = principal.parent().unwrap();
    let fonte = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("blender");
    for e in std::fs::read_dir(fonte).unwrap().flatten() {
        let nome = e.file_name();
        if nome.to_string_lossy().ends_with(".py") {
            assert!(pasta.join(&nome).is_file(), "{nome:?} não está na lista SCRIPTS de forja.rs");
        }
    }
}

/// Bancada de movimento: a conferência acha o que fica feio (as animações procedurais da Forja têm
/// braço torcido no golpe e o corpo entra no chão na morte) e a correção automática deixa tudo aprovado.
#[tokio::test]
async fn conferencia_do_movimento_reprova_e_corrige() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("aren.glb");
    forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "personagem", "saida": saida, "previa": false,
                "personagem": {"id": "aren", "tipo": "humano", "arma": "machado", "armadura": "leve"}}),
        TEMPO,
    )
    .await
    .unwrap();
    let r =
        forja::rodar(&blender, tmp.path(), &json!({"tarefa": "conferir", "entrada": saida, "imagens": "reprovados"}), TEMPO).await.unwrap();
    assert_eq!(r["pes"], json!(["LeftFoot", "RightFoot"]), "{r}");
    let reprovados: Vec<&str> = r["reprovados"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    assert!(reprovados.contains(&"morrer"), "a morte entra no chão: {r}");
    let parado = r["clipes"].as_array().unwrap().iter().find(|c| c["nome"] == "parado").unwrap();
    assert_eq!(parado["aprovado"], true, "parado é limpo: {parado}");
    assert!(std::path::Path::new(r["arquivos"]["imagem"].as_str().unwrap()).is_file());
    let tipos: Vec<&str> = r["clipes"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|c| c["problemas"].as_array().unwrap())
        .map(|p| p["tipo"].as_str().unwrap())
        .collect();
    assert!(tipos.contains(&"abaixo_do_chao"), "{tipos:?}");
    // a correção automática
    let corrigido = tmp.path().join("aren_corrigido.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "conferir", "entrada": saida, "saida": corrigido, "corrigir": true, "imagens": "nenhuma"}),
        TEMPO,
    )
    .await
    .unwrap();
    assert_eq!(r["aprovado"], true, "depois da correção: {}", r["clipes"]);
    assert!(r["correcoes"]["morrer"].is_array(), "{}", r["correcoes"]);
    assert!(corrigido.is_file());
    // o glb corrigido continua com todas as animações
    let glb = std::fs::read(&corrigido).unwrap();
    let json_len = u32::from_le_bytes(glb[12..16].try_into().unwrap()) as usize;
    let gltf: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
    assert!(gltf["animations"].as_array().unwrap().len() >= 9);
}

/// BVH com os nomes do ACCAD (Mixamo sem prefixo, com ToSpine), 40 quadros de passada.
fn bvh_de_teste() -> String {
    let mut h =
        String::from("HIERARCHY\nROOT Hips\n{\n OFFSET 0 94 0\n CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation\n");
    fn junta(nome: &str, off: (f64, f64, f64), filhos: &[String]) -> String {
        let mut s = format!("JOINT {nome}\n{{\n OFFSET {} {} {}\n CHANNELS 3 Zrotation Xrotation Yrotation\n", off.0, off.1, off.2);
        if filhos.is_empty() {
            s += " End Site\n {\n  OFFSET 0 5 0\n }\n";
        }
        for f in filhos {
            s += f;
        }
        s + "}\n"
    }
    let cabeca = junta("Neck", (0.0, 20.0, 0.0), &[junta("Head", (0.0, 10.0, 0.0), &[])]);
    let mut bracos = Vec::new();
    for (lado, x) in [("Left", 1.0), ("Right", -1.0)] {
        let mao = junta(&format!("{lado}Hand"), (x * 25.0, 0.0, 0.0), &[]);
        let ante = junta(&format!("{lado}ForeArm"), (x * 27.0, 0.0, 0.0), &[mao]);
        let braco = junta(&format!("{lado}Arm"), (x * 15.0, 0.0, 0.0), &[ante]);
        bracos.push(junta(&format!("{lado}Shoulder"), (x * 3.0, 18.0, 0.0), &[braco]));
    }
    let mut filhos_peito = vec![cabeca];
    filhos_peito.extend(bracos);
    let peito = junta("Spine1", (0.0, 12.0, 0.0), &filhos_peito);
    let coluna = junta("ToSpine", (0.0, 6.0, 0.0), &[junta("Spine", (0.0, 10.0, 0.0), &[peito])]);
    h += &coluna;
    for (lado, x) in [("Left", 1.0), ("Right", -1.0)] {
        let dedo = junta(&format!("{lado}ToeBase"), (0.0, -4.0, 12.0), &[]);
        let pe = junta(&format!("{lado}Foot"), (0.0, -42.0, 0.0), &[dedo]);
        let canela = junta(&format!("{lado}Leg"), (0.0, -43.0, 0.0), &[pe]);
        h += &junta(&format!("{lado}UpLeg"), (x * 9.0, -2.0, 0.0), &[canela]);
    }
    h += "}\n";
    // canais: Hips 6, outras 21 juntas × 3
    let n = 40;
    h += &format!("MOTION\nFrames: {n}\nFrame Time: 0.0333333\n");
    for q in 0..n {
        let fase = (q as f64) / (n as f64) * std::f64::consts::TAU;
        let mut v = vec![0.0, 94.0, q as f64 * 3.0, 0.0, 0.0, 0.0];
        for j in 0..21 {
            // as coxas (juntas 15 e 18) balançam em X
            let x = if j == 14 {
                25.0 * fase.sin()
            } else if j == 17 {
                -25.0 * fase.sin()
            } else {
                0.0
            };
            v.extend([0.0, x, 0.0]);
        }
        h += &v.iter().map(|x| format!("{x:.3}")).collect::<Vec<_>>().join(" ");
        h += "\n";
    }
    h
}

#[tokio::test]
async fn banco_de_movimento_cataloga_bvh_do_accad() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let arq = tmp.path().join("Male9_B3_Walk.bvh");
    std::fs::write(&arq, bvh_de_teste()).unwrap();
    let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "banco", "fontes": [{"id": "accad", "arquivos": [arq]}]}), TEMPO)
        .await
        .unwrap();
    let c = &r["clipes"][0];
    assert_eq!(c["nome"], "Male9_B3_Walk", "{r}");
    assert_eq!(c["id"], "accad:Male9_B3_Walk.bvh:Male9_B3_Walk");
    assert_eq!(c["ossos_reconhecidos"], 22, "todos os ossos do ACCAD no mapa: {c}");
    assert!(c["etiquetas"].as_array().unwrap().contains(&json!("andar")), "{c}");
    assert_eq!(c["quadros"], 40);
    // anda 117 cm em 94 cm de quadril: ~1,2 alturas do quadril
    let d = c["desloca_no_chao"].as_f64().unwrap();
    assert!((1.0..1.4).contains(&d), "{c}");
    assert_eq!(c["laco"], false);
}

/// Bancada de esqueleto: a imagem numerada, a lista com avisos e a edição (corrente de mola nova, osso
/// apagado, renomeado pelo número) com os pesos refeitos só perto do que mudou.
#[tokio::test]
async fn esqueleto_visto_e_editado_pela_ia() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("aren.glb");
    forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "personagem", "saida": saida, "previa": false, "personagem": {"id": "aren", "tipo": "humano", "arma": "machado"}}),
        TEMPO,
    )
    .await
    .unwrap();
    let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "esqueleto_ver", "entrada": saida}), TEMPO).await.unwrap();
    assert!(std::path::Path::new(r["arquivos"]["imagem"].as_str().unwrap()).is_file());
    let ossos = r["ossos"].as_array().unwrap();
    let antes =
        |nome: &str, lista: &Vec<serde_json::Value>| lista.iter().find(|o| o["nome"] == nome).map(|o| o["vertices_que_carrega"].clone());
    let perna = antes("RightUpperLeg", ossos).unwrap();
    let pescoco = ossos.iter().find(|o| o["nome"] == "Neck").unwrap()["n"].as_u64().unwrap();
    let editado = tmp.path().join("aren_editado.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "esqueleto_editar", "entrada": saida, "saida": editado, "mudancas": [
            {"op": "criar", "osso": "mola_rabo_1", "pai": "Head", "cabeca": [0, 0.09, 1.78], "ponta": [0, 0.16, 1.62]},
            {"op": "criar", "osso": "mola_rabo_2", "pai": "mola_rabo_1", "cabeca": [0, 0.16, 1.62], "ponta": [0, 0.18, 1.45], "ligado": true},
            {"op": "apagar", "osso": "Jaw"},
            {"op": "renomear", "osso": pescoco, "novo": "Pescoco"}]}),
        TEMPO,
    )
    .await
    .unwrap();
    let ossos = r["ossos"].as_array().unwrap();
    let nomes: Vec<&str> = ossos.iter().map(|o| o["nome"].as_str().unwrap()).collect();
    assert!(nomes.contains(&"mola_rabo_2") && nomes.contains(&"Pescoco") && !nomes.contains(&"Jaw"), "{nomes:?}");
    assert!(antes("mola_rabo_1", ossos).unwrap().as_u64().unwrap() > 0, "a corrente nova carrega a parte de trás da cabeça");
    assert_eq!(antes("RightUpperLeg", ossos).unwrap(), perna, "longe do que mudou, os pesos ficam");
    assert!(editado.is_file());
}
