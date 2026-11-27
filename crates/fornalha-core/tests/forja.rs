//! A Forja de verdade no Blender: personagem com esqueleto e animações, arma,
//! objeto, mundo em blockout, limpeza e esqueleto em malha de fora.
//! Roda quando o Blender está nesta máquina (o CI instala); senão avisa e pula.

mod comum;

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

/// Bancada de mapa: o plano vira relevo, rio, estradas, vegetação e construções, e as medidas aprovam.
#[tokio::test]
async fn mapa_pelo_plano_com_medidas() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let pasta = tmp.path().join("World/mapa");
    // a casa que a IA montou por peças vira a casa da vila
    let casa = json!({"id": "casa_teste", "materiais": {"parede": {"cor": "#9a948a", "tipo": "pedra"}, "telha": {"cor": "#4e5258", "tipo": "telha"}},
        "pecas": [{"tipo": "caixa", "material": "parede", "centro": [0, 0, 1.6], "tamanho": [8, 6, 3.2]},
                  {"tipo": "extrusao", "plano": "lado", "material": "telha", "espessura": 8.6, "contorno": [[-3.4, 3.2], [3.4, 3.2], [0, 5.8]]}]});
    forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "objeto", "saida": tmp.path().join("Items/casa_teste.glb"), "previa": false, "objeto": casa}),
        TEMPO,
    )
    .await
    .unwrap();
    let plano = json!({"tamanho_m": 256, "seed": 3, "rio": true, "hora": "por_do_sol",
        "regioes": [{"id": "vila", "tipo": "vila", "casas": ["Items/casa_teste.glb", "Items/nao_existe.glb"]}, {"id": "mata", "tipo": "floresta", "posicao": "norte"},
                    {"id": "cripta", "tipo": "masmorra", "posicao": "leste"}, {"id": "x", "tipo": "nave_espacial"}]});
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "mapa", "saida": pasta, "plano": plano, "fotos": false, "projeto_raiz": tmp.path()}),
        TEMPO,
    )
    .await
    .unwrap();
    assert!(r["avisos"].to_string().contains("nao_existe.glb"), "casa que falta vira aviso");
    let est = String::from_utf8_lossy(&std::fs::read(pasta.join("estruturas.glb")).unwrap()).into_owned();
    assert!(est.contains("vila_casa_0-col") && est.contains("casa_teste_parede"), "a vila usa a casa montada");
    assert_eq!(r["plano"]["regioes"][0]["casas"][0], "Items/casa_teste.glb");
    assert!(r["plano"]["regioes"][0].get("_casas_arq").is_none(), "caminho da máquina não fica no plano");
    let med = &r["medidas"];
    assert_eq!(med["aprovado"], true, "{med}");
    assert!(r["avisos"].as_array().unwrap().iter().any(|a| a.as_str().unwrap().contains("nave_espacial")), "tipo errado vira aviso");
    for arq in [
        "relevo.r32",
        "relevo.r16",
        "pintura.png",
        "terreno.glb",
        "agua.glb",
        "estruturas.glb",
        "vegetacao.glb",
        "espalhamento.json",
        "mapa.json",
        "mapa.png",
    ] {
        assert!(pasta.join(arq).is_file(), "falta {arq}");
    }
    let info: serde_json::Value = serde_json::from_slice(&std::fs::read(pasta.join("mapa.json")).unwrap()).unwrap();
    let n = info["pontos_por_lado"].as_u64().unwrap();
    assert_eq!(std::fs::metadata(pasta.join("relevo.r32")).unwrap().len(), n * n * 4);
    assert_eq!(info["regioes"].as_array().unwrap().len(), 4);
    assert!(info["fotos"].as_array().unwrap().len() >= 4);
    assert_eq!(info["luz"]["sol_elevacao"], 7);
    assert!(!info["spawn_inimigos"].as_array().unwrap().is_empty(), "a masmorra tem inimigos");
    let st = &r["estatisticas"];
    assert!(st["arvores"].as_u64().unwrap() > 100 && st["pedras"].as_u64().unwrap() > 10, "{st}");
    let itens = med["itens"].as_array().unwrap();
    let valor = |nome: &str| itens.iter().find(|i| i["nome"] == nome).map(|i| i["valor"].clone()).unwrap();
    assert_eq!(valor("arvores_em_barranco"), 0);
    assert_eq!(valor("regioes_sem_ligacao"), json!([]));
    assert!(valor("estrada_rampa_max_graus").as_f64().unwrap() <= 12.0);
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

/// Caixa (8 vértices, 6 faces) em OBJ, do canto `a` ao canto `b`, com os índices a partir de `base`.
fn caixa_obj(a: [f64; 3], b: [f64; 3], base: usize) -> String {
    let mut s = String::new();
    for &x in &[a[0], b[0]] {
        for &y in &[a[1], b[1]] {
            for &z in &[a[2], b[2]] {
                s += &format!("v {x} {z} {}\n", -y); // OBJ em Y para cima; o Blender importa para Z para cima
            }
        }
    }
    for f in [[1, 2, 4, 3], [5, 7, 8, 6], [1, 5, 6, 2], [3, 4, 8, 7], [1, 3, 7, 5], [2, 6, 8, 4]] {
        s += &format!("f {} {} {} {}\n", f[0] + base, f[1] + base, f[2] + base, f[3] + base);
    }
    s
}

/// Roupa por cima: uma placa no peito e uma braçadeira no antebraço esquerdo ficam rígidas no osso certo
/// e a roupa acompanha as animações que o personagem já tinha.
#[tokio::test]
async fn roupa_por_cima_com_placas_rigidas() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("aren.glb");
    forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "personagem", "saida": saida, "previa": false, "personagem": {"id": "aren", "tipo": "humano"}}),
        TEMPO,
    )
    .await
    .unwrap();
    // o esqueleto diz onde ficam o peito e o antebraço
    let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "esqueleto_ver", "entrada": saida}), TEMPO).await.unwrap();
    let osso = |n: &str| r["ossos"].as_array().unwrap().iter().find(|o| o["nome"] == n).unwrap().clone();
    let (peito, ante) = (osso("Chest"), osso("LeftLowerArm"));
    let p = |o: &serde_json::Value, k: &str, i: usize| o[k][i].as_f64().unwrap();
    let zc = (p(&peito, "cabeca", 2) + p(&peito, "ponta", 2)) / 2.0;
    let mut obj = caixa_obj([-0.16, -0.16, zc - 0.07], [0.16, -0.10, zc + 0.07], 0);
    let (xa, xb, za) = (p(&ante, "cabeca", 0), p(&ante, "ponta", 0), p(&ante, "cabeca", 2));
    let (x0, x1) = (xa.min(xb) + 0.03, xa.max(xb) - 0.03);
    obj += &caixa_obj([x0, -0.05, za - 0.05], [x1, 0.05, za + 0.05], 8);
    let roupa = tmp.path().join("armadura.obj");
    std::fs::write(&roupa, obj).unwrap();
    let vestido = tmp.path().join("aren_vestido.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "vestir", "entrada": saida, "roupa": roupa, "saida": vestido, "imagens": "nenhuma"}),
        TEMPO,
    )
    .await
    .unwrap();
    assert_eq!(r["roupa"]["ilhas_rigidas"], 2, "as duas placas rígidas: {}", r["roupa"]);
    let mut donos: Vec<&str> = r["roupa"]["placas"].as_array().unwrap().iter().map(|x| x["osso"].as_str().unwrap()).collect();
    donos.sort();
    assert_eq!(donos, ["Chest", "LeftLowerArm"], "cada placa no osso de baixo dela: {}", r["roupa"]);
    assert!(vestido.is_file());
    assert!(r["clipes"].as_array().unwrap().len() >= 9, "a roupa entra nas animações que já existiam");
    // os ossos donos: confere no esqueleto do glb vestido
    let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "esqueleto_ver", "entrada": vestido}), TEMPO).await.unwrap();
    let carrega =
        |n: &str| r["ossos"].as_array().unwrap().iter().find(|o| o["nome"] == n).unwrap()["vertices_que_carrega"].as_u64().unwrap();
    assert!(carrega("LeftLowerArm") > 0 && carrega("Chest") > 0);
}

#[tokio::test]
async fn comparacao_com_a_referencia_lado_a_lado() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let glb = tmp.path().join("barril.glb");
    forja::rodar(&blender, tmp.path(), &json!({"tarefa": "objeto", "saida": glb, "amostras": 6, "objeto": {"tipo": "barril"}}), TEMPO)
        .await
        .unwrap();
    let mut difs = vec![];
    for (nome, cor) in [("perto", [120u8, 80, 45]), ("longe", [40u8, 90, 220])] {
        let refe = tmp.path().join(format!("ref_{nome}.png"));
        comum::referencia_png(&refe, cor, 300, 400);
        let saida = tmp.path().join(format!("ai/comparacoes/barril_{nome}.png"));
        let r = forja::rodar(
            &blender,
            tmp.path(),
            &json!({"tarefa": "comparar", "referencia": refe, "arquivo": glb, "saida": saida, "vista": "frente", "amostras": 6}),
            TEMPO,
        )
        .await
        .unwrap();
        assert!(saida.is_file(), "a imagem lado a lado sai em ai/comparacoes");
        assert_eq!(r["enquadramento"], "corpo", "objeto baixo: enquadra inteiro");
        assert!(r["paleta_referencia"].as_array().is_some_and(|p| !p.is_empty()));
        assert!(r["paleta_resultado"].as_array().is_some_and(|p| !p.is_empty()));
        assert!(r["silhueta_referencia"]["altura_sobre_largura"].as_f64().is_some());
        assert!(r["silhueta_resultado"]["altura_sobre_largura"].as_f64().is_some());
        let dif = r["diferenca_de_cor"].as_f64().unwrap();
        if nome == "longe" {
            assert!(r["dica"].as_str().unwrap().contains("cores"), "{r}");
        }
        difs.push(dif);
    }
    assert!(difs[1] > difs[0] + 0.05, "o azul fica mais longe do barril que o marrom: {difs:?}");
}

#[tokio::test]
async fn montagem_livre_por_pecas() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("Weapons/espada_longa.glb");
    let arma = json!({"id": "espada_longa",
    "materiais": {"aco": {"cor": "#c9ced4", "tipo": "metal"}, "couro": {"cor": "#3a2416", "tipo": "couro"}},
    "pecas": [
        {"tipo": "extrusao", "material": "aco", "espessura": 0.007, "gume": 0.016,
         "contorno": [[-0.026, 0.11], [0.026, 0.11], [0.024, 0.55], [0.02, 0.86], [0.0, 0.98], [-0.02, 0.86], [-0.024, 0.55]]},
        {"tipo": "caixa", "material": "aco", "centro": [0.07, 0, 0.1], "tamanho": [0.12, 0.03, 0.02], "chanfro": 0.004, "espelhar": "x"},
        {"tipo": "torno", "material": "couro", "perfil": [[0.0, -0.11], [0.016, -0.11], [0.018, -0.05], [0.016, 0.085], [0.0, 0.085]]},
        {"tipo": "tubo", "material": "nao_existe", "raio": [0.004, 0.003], "pontos": [[0.02, 0, -0.1], [0.0, 0.02, -0.05], [-0.02, 0, 0.0]]},
        {"tipo": "esfera", "material": "aco", "centro": [0, 0, -0.13], "raio": 0.025},
        {"tipo": "cilindro", "material": "aco", "de": [0, 0, 0.09], "para": [0, 0, 0.11], "raio": 0.02}
    ]});
    let r =
        forja::rodar(&blender, tmp.path(), &json!({"tarefa": "arma", "saida": saida, "amostras": 4, "arma": arma}), TEMPO).await.unwrap();
    assert!(saida.is_file());
    let st = &r["estatisticas"];
    assert!(st["triangulos"].as_u64().unwrap() > 150, "{st}");
    let mats: Vec<String> = st["materiais"].as_array().unwrap().iter().map(|m| m.as_str().unwrap().to_string()).collect();
    assert!(mats.iter().any(|m| m.starts_with("espada_longa_aco")) && mats.iter().any(|m| m.starts_with("espada_longa_couro")), "{mats:?}");
    // a lâmina fica de pé, com a ponta perto de 0,98 m e a guarda espelhada dos dois lados
    assert!((st["altura_m"].as_f64().unwrap() - 1.135).abs() < 0.03, "{st}");
    assert!((st["largura_m"].as_f64().unwrap() - 0.26).abs() < 0.02, "guarda espelhada: {st}");
    assert!(r["avisos"].to_string().contains("nao_existe"), "material que falta vira aviso: {r}");
    let glb = std::fs::read(&saida).unwrap();
    assert!(String::from_utf8_lossy(&glb).contains("-colonly"));
    // peça errada: erro que diz qual
    let ruim = json!({"id": "x", "pecas": [{"tipo": "piramide"}]});
    let e = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "objeto", "saida": tmp.path().join("x.glb"), "previa": false, "objeto": ruim}),
        TEMPO,
    )
    .await
    .unwrap_err();
    assert!(e.to_string().contains("piramide"), "{e}");
}

#[tokio::test]
async fn roupa_moderna_de_jaqueta() {
    let blender = blender_ou_pula!();
    let Some(mh) = std::env::var_os("FORNALHA_PACOTE_MAKEHUMAN").map(std::path::PathBuf::from) else {
        eprintln!("pacote MakeHuman não encontrado: teste pulado (defina FORNALHA_PACOTE_MAKEHUMAN)");
        return;
    };
    let tmp = tempfile::tempdir().unwrap();
    let saida = tmp.path().join("Characters/andarilho/andarilho.glb");
    let r = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "humano", "saida": saida, "previa": false, "animacoes": null,
                "makehuman": {"dados": mh.join("dados"), "assets": mh.join("assets")},
                "humano": {"id": "andarilho", "macro": {"genero": 1.0, "idade": 0.7}, "cabelo": "short02", "arma": "nenhuma",
                           "roupa": {"estilo": "jaqueta", "capa": false, "cores": {"principal": "#3f3024", "secundaria": "#58606a", "detalhe": "#241a14"}}}}),
        TEMPO,
    )
    .await
    .unwrap();
    assert!(saida.is_file());
    let pecas: Vec<String> = r["estatisticas"]["pecas"].as_array().unwrap().iter().map(|p| p.as_str().unwrap().to_string()).collect();
    for p in ["_camisa", "_colarinho", "_botoes", "_jaqueta", "_gola", "_bolso_e", "_bolso_d", "_calcas", "_botas"] {
        assert!(pecas.iter().any(|x| x.ends_with(p)), "falta {p}: {pecas:?}");
    }
    assert_eq!(r["estatisticas"]["qa"]["passou"], true, "{}", r["estatisticas"]["qa"]);
}

/// Quatro vistas sem o motor de imagem: a malha é vista de frente, dos lados e de costas (sem luz) e as
/// vistas voltam projetadas numa textura nova (o caminho do 3D pela IA; aqui num objeto da Forja).
#[tokio::test]
async fn quatro_vistas_projetam_de_volta_na_textura() {
    let blender = blender_ou_pula!();
    let tmp = tempfile::tempdir().unwrap();
    let glb = tmp.path().join("barril.glb");
    forja::rodar(&blender, tmp.path(), &json!({"tarefa": "objeto", "objeto": {"tipo": "barril", "id": "barril"}, "saida": glb}), TEMPO)
        .await
        .unwrap();
    let pasta = tmp.path().join("vistas");
    let r = forja::rodar(&blender, tmp.path(), &json!({"tarefa": "vistas", "entrada": glb, "pasta": pasta}), TEMPO).await.unwrap();
    for v in ["frente", "esquerda", "costas", "direita"] {
        assert!(pasta.join(format!("vista_{v}.png")).is_file(), "sem a vista {v}: {r}");
    }
    let imagens: serde_json::Map<String, serde_json::Value> =
        ["frente", "esquerda", "costas", "direita"].iter().map(|v| (v.to_string(), json!(pasta.join(format!("vista_{v}.png"))))).collect();
    let saida = tmp.path().join("barril_vistas.glb");
    let p = forja::rodar(
        &blender,
        tmp.path(),
        &json!({"tarefa": "projetar", "entrada": glb, "vistas": pasta.join("vistas.json"), "imagens": imagens, "saida": saida, "lado": 512}),
        TEMPO,
    )
    .await
    .unwrap();
    assert!(saida.is_file(), "{p}");
    let cob = &p["projecao"]["malhas"][0]["cobertura"];
    assert!(cob["frente"].as_f64().unwrap() > 0.05 && cob["costas"].as_f64().unwrap() > 0.05, "cobertura: {cob}");
    // a textura nova vai dentro do glb
    let b = std::fs::read(&saida).unwrap();
    let n = u32::from_le_bytes(b[12..16].try_into().unwrap()) as usize;
    let g: serde_json::Value = serde_json::from_slice(&b[20..20 + n]).unwrap();
    assert!(g["images"].as_array().is_some_and(|i| !i.is_empty()), "sem imagem no glb");
}
