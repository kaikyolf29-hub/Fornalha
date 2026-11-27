//! Contrato com a engine (Erethea): o que a Fornalha entrega e o que a cena montada tem de ter, num
//! formato que o agente lê (`ai/contrato_da_engine.json` em cada projeto e a ferramenta
//! `get_engine_contract`). Combinado com a Erethea em 27/11/2026, para as duas continuarem coerentes:
//! - **esqueleto**: os nomes dos ossos (o de jogo, com 5 dedos por mão, e o da Forja), os eixos e as
//!   regras do corpo, para a animação gerada dentro do editor bater osso por osso;
//! - **animações**: as que a Fornalha entrega em cada personagem, com o nome e se é laço;
//! - **conferência da cena**: o que a cena precisa ter (personagens, objetos, mapa, estilo) e como medir
//!   cada coisa, para o agente montar pelo MCP da Erethea, tirar `take_screenshot` e conferir;
//! - **montagem**: o `montar.gd` (pelo `run_script` da Erethea com o editor aberto, ou `--script` sem ele).

use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::projeto::Projeto;

pub const ARQUIVO: &str = "ai/contrato_da_engine.json";
pub const FORMATO: u32 = 1;

/// Esqueleto de jogo (humano realista, malha da IA e roupa vestida): nomes no padrão da Unreal, 60 ossos.
/// (osso, pai). Conferido no glb do templário de 27/11 e no teste do personagem realista.
pub const OSSOS_DO_JOGO: [(&str, &str); 60] = [
    ("Root", ""),
    ("pelvis", "Root"),
    ("spine_01", "pelvis"),
    ("spine_02", "spine_01"),
    ("spine_03", "spine_02"),
    ("clavicle_l", "spine_03"),
    ("upperarm_l", "clavicle_l"),
    ("lowerarm_l", "upperarm_l"),
    ("hand_l", "lowerarm_l"),
    ("index_01_l", "hand_l"),
    ("index_02_l", "index_01_l"),
    ("index_03_l", "index_02_l"),
    ("middle_01_l", "hand_l"),
    ("middle_02_l", "middle_01_l"),
    ("middle_03_l", "middle_02_l"),
    ("pinky_01_l", "hand_l"),
    ("pinky_02_l", "pinky_01_l"),
    ("pinky_03_l", "pinky_02_l"),
    ("ring_01_l", "hand_l"),
    ("ring_02_l", "ring_01_l"),
    ("ring_03_l", "ring_02_l"),
    ("thumb_01_l", "hand_l"),
    ("thumb_02_l", "thumb_01_l"),
    ("thumb_03_l", "thumb_02_l"),
    ("clavicle_r", "spine_03"),
    ("upperarm_r", "clavicle_r"),
    ("lowerarm_r", "upperarm_r"),
    ("hand_r", "lowerarm_r"),
    ("index_01_r", "hand_r"),
    ("index_02_r", "index_01_r"),
    ("index_03_r", "index_02_r"),
    ("middle_01_r", "hand_r"),
    ("middle_02_r", "middle_01_r"),
    ("middle_03_r", "middle_02_r"),
    ("pinky_01_r", "hand_r"),
    ("pinky_02_r", "pinky_01_r"),
    ("pinky_03_r", "pinky_02_r"),
    ("ring_01_r", "hand_r"),
    ("ring_02_r", "ring_01_r"),
    ("ring_03_r", "ring_02_r"),
    ("thumb_01_r", "hand_r"),
    ("thumb_02_r", "thumb_01_r"),
    ("thumb_03_r", "thumb_02_r"),
    ("neck_01", "spine_03"),
    ("head", "neck_01"),
    ("eye_l", "head"),
    ("eye_r", "head"),
    ("eyelid_lower_l", "head"),
    ("eyelid_lower_r", "head"),
    ("eyelid_upper_l", "head"),
    ("eyelid_upper_r", "head"),
    ("jaw", "head"),
    ("thigh_l", "pelvis"),
    ("calf_l", "thigh_l"),
    ("foot_l", "calf_l"),
    ("ball_l", "foot_l"),
    ("thigh_r", "pelvis"),
    ("calf_r", "thigh_r"),
    ("foot_r", "calf_r"),
    ("ball_r", "foot_r"),
];

/// Esqueleto da Forja (personagem estilizado feito por código, nível Leve): 23 ossos, mão sem dedos.
pub const OSSOS_DA_FORJA: [(&str, &str); 23] = [
    ("Root", ""),
    ("Hips", "Root"),
    ("LeftUpperLeg", "Hips"),
    ("LeftLowerLeg", "LeftUpperLeg"),
    ("LeftFoot", "LeftLowerLeg"),
    ("LeftToes", "LeftFoot"),
    ("RightUpperLeg", "Hips"),
    ("RightLowerLeg", "RightUpperLeg"),
    ("RightFoot", "RightLowerLeg"),
    ("RightToes", "RightFoot"),
    ("Spine", "Hips"),
    ("Chest", "Spine"),
    ("LeftShoulder", "Chest"),
    ("LeftUpperArm", "LeftShoulder"),
    ("LeftLowerArm", "LeftUpperArm"),
    ("LeftHand", "LeftLowerArm"),
    ("Neck", "Chest"),
    ("Head", "Neck"),
    ("Jaw", "Head"),
    ("RightShoulder", "Chest"),
    ("RightUpperArm", "RightShoulder"),
    ("RightLowerArm", "RightUpperArm"),
    ("RightHand", "RightLowerArm"),
];

/// Animações que todo humano com o esqueleto de jogo recebe: (nome, laço, o que é).
pub const ANIMACOES_PADRAO: [(&str, bool, &str); 15] = [
    ("parado", true, "em pé, respirando"),
    ("andar", true, "andar no lugar (o jogo move o corpo)"),
    ("correr", true, "correr no lugar"),
    ("correr_rapido", true, "disparada no lugar"),
    ("pular", false, "impulso do pulo"),
    ("no_ar", true, "no ar, entre o pulo e a queda"),
    ("aterrissar", false, "chegada no chão"),
    ("atacar", false, "golpe 1 (com a arma da mão)"),
    ("atacar_2", false, "golpe 2"),
    ("atacar_3", false, "golpe 3"),
    ("defender", false, "bloqueio"),
    ("esquivar", false, "rolamento"),
    ("dano", false, "recebe um golpe"),
    ("morrer", false, "cai e fica no chão"),
    ("parado_espada", true, "parado em guarda, com a arma"),
];

/// Outras que a Fornalha sabe fazer pela captura (banco de movimento), sob pedido.
pub const ANIMACOES_EXTRAS: [&str; 10] =
    ["combo", "dano_forte", "soco", "soco_2", "agachar", "agachado_andar", "interagir", "zumbi_parado", "zumbi_andar", "zumbi_ataque"];

/// As do personagem da Forja (esqueleto sem dedos).
pub const ANIMACOES_DA_FORJA: [&str; 9] = ["parado", "andar", "correr", "pular", "atacar", "defender", "esquivar", "dano", "morrer"];

/// As regras do corpo em palavras (as mesmas do `check_motion`, em `fc_conferir.regras_do_corpo`).
pub const REGRAS_DO_CORPO: [&str; 7] = [
    "Um humano tem 2 braços, 2 pernas e 5 dedos em cada mão: o polegar com 2 juntas que dobram, os outros 4 com 3.",
    "Cada junta de dedo só fecha para a palma (até ~120° somados por junta); para trás quase nada, para o lado pouco, sem torcer.",
    "Cotovelo e joelho dobram para um lado só; nenhum osso torce além do limite dele (antebraço, braço, coxa, pescoço).",
    "A animação não tem física: equilíbrio, peso e contato são garantidos por quem anima. Parado, o quadril fica sobre os pés; o pé que pisa não escorrega; nada entra no chão nem atravessa o próprio corpo.",
    "Fluido: começa e termina devagar (entrada e saída), antecipa antes do golpe e continua depois; nenhum osso vira de repente nem treme indo e voltando de um quadro para o outro.",
    "Ciclo (andar, correr, parado) fecha no mesmo quadro em que começa.",
    "Prefira captura do banco (list_motions/apply_motion) a inventar; confira com check_motion e corrija com edit_motion o que for reprovado. Aprovado = a régua não achou o que ela mede; olhe as folhas antes de dizer que ficou bom.",
];

fn ossos(lista: &[(&str, &str)]) -> Value {
    json!(lista
        .iter()
        .map(|(o, p)| if p.is_empty() { json!({"osso": o, "pai": null}) } else { json!({"osso": o, "pai": p}) })
        .collect::<Vec<_>>())
}

fn esqueleto_do_glb(gltf: &Value) -> (&'static str, Vec<String>) {
    let nos = gltf["nodes"].as_array().cloned().unwrap_or_default();
    let nomes: Vec<String> = gltf["skins"][0]["joints"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|i| i.as_u64().and_then(|i| nos.get(i as usize)).and_then(|n| n["name"].as_str()).map(String::from))
        .collect();
    let tipo = if nomes.iter().any(|n| n == "pelvis") && nomes.iter().any(|n| n == "hand_l") {
        "fornalha-jogo-1"
    } else if nomes.iter().any(|n| n == "Hips") && nomes.iter().any(|n| n == "LeftHand") {
        "fornalha-forja-1"
    } else if nomes.is_empty() {
        "sem_esqueleto"
    } else {
        "proprio"
    };
    (tipo, nomes)
}

/// Os personagens que já existem no projeto (Characters/ e Enemies/): arquivo, esqueleto e animações.
fn personagens_no_disco(raiz: &Path) -> Vec<Value> {
    let mut out = Vec::new();
    for pasta in ["Characters", "Enemies"] {
        let Ok(ler) = std::fs::read_dir(raiz.join(pasta)) else { continue };
        let mut dirs: Vec<PathBuf> = ler.flatten().map(|e| e.path()).filter(|p| p.is_dir()).collect();
        dirs.sort();
        for d in dirs {
            let id = d.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            let glb = d.join(format!("{id}.glb"));
            let Some(gltf) = crate::bruto::json_do_glb(&glb) else { continue };
            let (tipo, nomes) = esqueleto_do_glb(&gltf);
            let mut anims: Vec<String> =
                gltf["animations"].as_array().into_iter().flatten().filter_map(|a| a["name"].as_str().map(String::from)).collect();
            anims.sort();
            let rel = glb.strip_prefix(raiz).map(|r| r.to_string_lossy().replace('\\', "/")).unwrap_or_default();
            out.push(json!({"id": id, "pasta": pasta, "arquivo": rel, "esqueleto": tipo, "ossos": nomes.len(), "animacoes": anims}));
        }
    }
    out
}

/// glbs de objetos e armas já feitos (Items/, Weapons/), relativos à raiz.
fn objetos_no_disco(raiz: &Path) -> Vec<String> {
    let mut out = Vec::new();
    for pasta in ["Items", "Weapons"] {
        let Ok(ler) = std::fs::read_dir(raiz.join(pasta)) else { continue };
        for e in ler.flatten() {
            let p = e.path();
            let glbs: Vec<PathBuf> =
                if p.is_dir() { std::fs::read_dir(&p).into_iter().flatten().flatten().map(|x| x.path()).collect() } else { vec![p] };
            for g in glbs {
                if g.extension().is_some_and(|x| x == "glb") && !g.to_string_lossy().contains(".previa") {
                    out.push(g.strip_prefix(raiz).map(|r| r.to_string_lossy().replace('\\', "/")).unwrap_or_default());
                }
            }
        }
    }
    out.sort();
    out
}

/// O contrato do projeto (sempre calculado do disco e da bíblia de agora).
pub fn contrato(p: &Projeto) -> Value {
    let b = &p.biblia;
    let raiz = &p.raiz;
    let no_disco = personagens_no_disco(raiz);
    let personagens: Vec<Value> = b
        .personagens
        .iter()
        .map(|c| {
            let feito = no_disco.iter().find(|d| d["id"] == c.id.as_str());
            json!({"id": c.id, "nome": c.nome, "papel": c.papel, "arma": c.arma,
            "arquivo": feito.map(|d| d["arquivo"].clone()).unwrap_or(Value::Null),
            "feito": feito.is_some(),
            "animacoes_obrigatorias": match feito.map(|d| d["esqueleto"].as_str().unwrap_or("")) {
                Some("fornalha-forja-1") => json!(ANIMACOES_DA_FORJA),
                _ => json!(ANIMACOES_PADRAO.iter().map(|(n, _, _)| *n).collect::<Vec<_>>()),
            }})
        })
        .collect();
    let mapa = raiz.join("World/mapa/mapa.json");
    let render = b.guia_visual.extras.get("render").and_then(Value::as_str).unwrap_or("realista");
    json!({
        "formato": FORMATO,
        "gerado_por": format!("{} {}", crate::consts::APP_NAME, crate::consts::APP_VERSION),
        "projeto": {"id": b.id, "nome": b.nome, "engine": b.engine, "comercial": b.comercial},
        "eixos": {"cima": "+Y", "frente_do_personagem": "+Z", "lado_esquerdo_l": "+X", "unidade": "metro", "formato": "glTF 2.0 (.glb)",
                  "quadros_por_segundo": 30},
        "esqueletos": {
            "fornalha-jogo-1": {"uso": "humano realista, malha da IA, roupa vestida (o padrão)", "ossos": ossos(&OSSOS_DO_JOGO),
                "dedos": {"por_mao": 5, "nomes": ["thumb", "index", "middle", "ring", "pinky"], "ossos_por_dedo": 3,
                          "padrao_do_nome": "<dedo>_0<1..3>_<l|r>", "nota": "o polegar tem 3 ossos (a base dele fica na palma) e 2 juntas que dobram"},
                "rosto": ["jaw", "eye_l", "eye_r", "eyelid_upper_l", "eyelid_upper_r", "eyelid_lower_l", "eyelid_lower_r"],
                "raiz_do_movimento": "pelvis (o Root fica parado no chão)",
                "extras": "roupa e cabelo podem trazer ossos próprios além destes (capa, saia, mechas; mola_<grupo>_1..N viram mola no jogo): a animação do corpo não mexe neles"},
            "fornalha-forja-1": {"uso": "personagem estilizado feito por código (nível Leve)", "ossos": ossos(&OSSOS_DA_FORJA),
                "dedos": {"por_mao": 0, "nota": "mão sem dedos"}, "raiz_do_movimento": "Hips"},
            "proprio": {"uso": "criaturas e corpos editados (dragão, monstro): cada um com o esqueleto dele; ossos mola_<grupo>_1..N viram mola no jogo"}
        },
        "regras_do_corpo": REGRAS_DO_CORPO,
        "animacoes": {
            "convencao": "nome em português, minúsculo, com _; laço = o último quadro encaixa no primeiro; locomoção no lugar (o jogo move o corpo); 30 quadros por segundo",
            "padrao": ANIMACOES_PADRAO.iter().map(|(n, l, o)| json!({"nome": n, "laco": l, "o_que_e": o})).collect::<Vec<_>>(),
            "extras_sob_pedido": ANIMACOES_EXTRAS,
            "da_forja": ANIMACOES_DA_FORJA,
            "nome_de_animacao_nova": "use o verbo em português (acenar, sentar_no_bau, colher); a Fornalha confere qualquer nome com check_motion"
        },
        "conferencia_da_cena": {
            "personagens": personagens,
            "personagens_no_disco": no_disco,
            "objetos_no_disco": objetos_no_disco(raiz),
            "mapa": {"arquivo": "World/mapa/mapa.json", "existe": mapa.is_file(),
                     "areas": b.mundo.areas.iter().map(|a| json!({"id": a.id, "nome": a.nome, "tipo": a.tipo})).collect::<Vec<_>>()},
            "estilo": {"render": render, "paleta": b.guia_visual.paleta, "texto_de_estilo": b.guia_visual.texto_de_estilo,
                       "evitar": b.guia_visual.evitar, "camera": b.conceito.camera},
            "criterios": [
                {"id": "personagens_presentes", "cobra": "cada personagem da bíblia que já foi feito está na cena, com o glb dele",
                 "como_medir": "listar os nós da cena pelo MCP da Erethea e comparar com conferencia_da_cena.personagens[].arquivo"},
                {"id": "animacoes_ligadas", "cobra": "cada personagem toca as animacoes_obrigatorias com estes nomes",
                 "como_medir": "AnimationPlayer de cada personagem; os nomes batem com animacoes.padrao (ou da_forja)"},
                {"id": "esqueleto_bate", "cobra": "animação gerada no editor usa os ossos do esqueleto do personagem, com 5 dedos por mão no fornalha-jogo-1",
                 "como_medir": "nomes das trilhas = esqueletos.<tipo>.ossos; depois check_motion na Fornalha (dedos, tremedeira, pé no chão)"},
                {"id": "objetos_presentes", "cobra": "os objetos e armas feitos estão na cena ou na mão de quem usa",
                 "como_medir": "nós da cena contra objetos_no_disco"},
                {"id": "mapa_montado", "cobra": "as áreas da bíblia aparecem e o chão cobre o mapa (sem buraco nem personagem caindo)",
                 "como_medir": "montar.gd (ou run_script) e take_screenshot de cima; run_test com --agent-test"},
                {"id": "estilo", "cobra": "as cores da captura ficam na paleta do guia visual e o render é o pedido (realista ou anime)",
                 "como_medir": "take_screenshot da Erethea → check_style da Fornalha com o arquivo da captura (mede quanto está na paleta)"},
                {"id": "referencia", "cobra": "quando a bíblia tem referência aprovada, a cena chega perto dela",
                 "como_medir": "compare_reference da Fornalha com a captura e a referência"},
                {"id": "sem_erros", "cobra": "a cena roda sem erro e o jogador anda",
                 "como_medir": "run_test (Fornalha) ou get_errors (Erethea)"}
            ]
        },
        "montagem": {
            "script": "res://Scripts/fornalha/montar.gd",
            "com_o_editor_aberto": "run_script do MCP da Erethea com o conteúdo do montar.gd (com desfazer)",
            "sem_o_editor": "erethea.console.exe --headless --path <projeto> --script res://Scripts/fornalha/montar.gd (o import_to_engine da Fornalha faz isso)",
            "monta_quando": "existe World/mapa/mapa.json, ou depois de import_to_engine"
        },
        "mcp": {"fornalha": format!("http://127.0.0.1:{}/mcp", crate::consts::PORTA_PADRAO),
                "erethea": format!("http://127.0.0.1:{}/mcp", crate::guia::PORTA_MCP_ERETHEA)}
    })
}

/// Grava o contrato em `ai/contrato_da_engine.json`. Devolve o caminho relativo.
pub fn escrever(p: &Projeto) -> Resultado<String> {
    let arq = p.raiz.join(ARQUIVO);
    if let Some(d) = arq.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    let texto = serde_json::to_string_pretty(&contrato(p)).unwrap_or_default() + "\n";
    std::fs::write(&arq, texto).map_err(|e| Erro::io(&arq, e))?;
    Ok(ARQUIVO.to_string())
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn esqueleto_de_jogo_tem_cinco_dedos_por_mao_e_pais_validos() {
        for lado in ["l", "r"] {
            for dedo in ["thumb", "index", "middle", "ring", "pinky"] {
                for j in 1..=3 {
                    let n = format!("{dedo}_0{j}_{lado}");
                    assert!(OSSOS_DO_JOGO.iter().any(|(o, _)| *o == n), "falta {n}");
                }
            }
        }
        for lista in [&OSSOS_DO_JOGO[..], &OSSOS_DA_FORJA[..]] {
            for (o, p) in lista {
                assert!(p.is_empty() || lista.iter().any(|(x, _)| x == p), "{o}: pai {p} não existe");
            }
            assert_eq!(lista.iter().filter(|(_, p)| p.is_empty()).count(), 1, "uma raiz só");
        }
    }

    #[test]
    fn regras_e_animacoes_iguais_as_do_blender() {
        // as regras em palavras são as mesmas que o check_motion devolve
        let conferir = include_str!("../blender/fc_conferir.py");
        for r in REGRAS_DO_CORPO {
            assert!(conferir.contains(r), "regra fora de sincronia com fc_conferir.regras_do_corpo: {r}");
        }
        // as animações padrão são as que a retarget entrega (fc_retarget.PADRAO)
        let retarget = include_str!("../blender/fc_retarget.py");
        let padrao = retarget.split("PADRAO = [").nth(1).and_then(|s| s.split(']').next()).unwrap_or("");
        for (n, _, _) in ANIMACOES_PADRAO {
            assert!(padrao.contains(&format!("\"{n}\"")), "{n} não está no PADRAO do fc_retarget");
        }
        for n in ANIMACOES_EXTRAS {
            assert!(retarget.contains(&format!("\"{n}\": (")), "{n} não está nos CLIPES do fc_retarget");
        }
    }

    #[test]
    fn contrato_do_projeto_novo_e_gravado() {
        let tmp = tempfile::tempdir().unwrap();
        let p = crate::projeto::criar(
            &crate::projeto::NovoProjeto { nome: "Contrato".into(), pasta_pai: Some(tmp.path().to_path_buf()), ..Default::default() },
            tmp.path(),
        )
        .unwrap();
        let c = contrato(&p);
        assert_eq!(c["formato"], FORMATO);
        assert_eq!(c["esqueletos"]["fornalha-jogo-1"]["ossos"].as_array().unwrap().len(), 60);
        assert_eq!(c["esqueletos"]["fornalha-jogo-1"]["dedos"]["por_mao"], 5);
        assert_eq!(c["animacoes"]["padrao"].as_array().unwrap().len(), 15);
        assert!(c["conferencia_da_cena"]["criterios"].as_array().unwrap().len() >= 6);
        assert!(p.raiz.join(ARQUIVO).is_file(), "o projeto novo já nasce com o contrato");
    }
}
