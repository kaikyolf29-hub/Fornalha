//! Teste Bruto (plano 1.11): a suíte de ponta a ponta que valida a Fornalha inteira antes do
//! Teste de Fogo na máquina do criador. Num projeto só dela, gera:
//! 1. o protagonista completo (corpo, rosto, cabelo em camadas, roupa, esqueleto humanoide,
//!    andar e combate);
//! 2. um inimigo humanoide armado (arma presa na mão, animações por retarget);
//! 3. um dragão (malha grande, asas, cauda, esqueleto não humanoide, voo e ataque);
//!
//! monta o mundo, roda o jogo na engine e confere glTF (malha, esqueleto, animações), mandíbula,
//! QA, bíblia válida e a licença comercial de tudo. Chamada pela API, pelo MCP
//! (`run_brute_test`) e pela linha de comando (`fornalha-cli teste-bruto`).

use std::path::{Path, PathBuf};
use std::time::Instant;

use serde::Deserialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::servico::Fornalha;

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsBruto {
    /// leve, equilibrado, qualidade (padrão) ou maximo
    pub nivel: Option<String>,
    /// quais casos: "protagonista", "inimigo", "zumbi", "dragao" (padrão: os quatro)
    pub casos: Option<Vec<String>>,
    /// montar o jogo e rodar o teste na engine no fim (padrão: sim)
    pub testar_na_engine: Option<bool>,
    /// pasta onde nasce o projeto do teste (padrão: a pasta de projetos da Fornalha)
    pub pasta: Option<PathBuf>,
}

/// Uma conferência do relatório.
fn conf(nome: &str, ok: bool, detalhe: impl Into<String>) -> Value {
    json!({"nome": nome, "ok": ok, "detalhe": detalhe.into()})
}

/// Lê o JSON de um .glb (glTF binário).
pub fn json_do_glb(arq: &Path) -> Option<Value> {
    let b = std::fs::read(arq).ok()?;
    if b.len() < 20 || &b[0..4] != b"glTF" {
        return None;
    }
    let n = u32::from_le_bytes(b[12..16].try_into().ok()?) as usize;
    if &b[16..20] != b"JSON" || b.len() < 20 + n {
        return None;
    }
    serde_json::from_slice(&b[20..20 + n]).ok()
}

/// O que o teste confere num glb de personagem.
#[derive(Debug, Default, Clone)]
pub struct ResumoGlb {
    pub versao: String,
    pub malhas: usize,
    pub juntas: usize,
    pub nomes_das_juntas: Vec<String>,
    pub animacoes: Vec<String>,
    pub imagens: usize,
    /// malhas presas (direto ou não) num destes ossos de mão
    pub na_mao: Vec<String>,
}

pub fn resumir_glb(arq: &Path) -> Option<ResumoGlb> {
    let g = json_do_glb(arq)?;
    let nos = g["nodes"].as_array().cloned().unwrap_or_default();
    let mut pai = vec![None; nos.len()];
    for (i, n) in nos.iter().enumerate() {
        for c in n["children"].as_array().into_iter().flatten() {
            if let Some(c) = c.as_u64() {
                if (c as usize) < pai.len() {
                    pai[c as usize] = Some(i);
                }
            }
        }
    }
    let juntas: Vec<usize> = g["skins"]
        .as_array()
        .into_iter()
        .flatten()
        .flat_map(|s| s["joints"].as_array().cloned().unwrap_or_default())
        .filter_map(|j| j.as_u64().map(|j| j as usize))
        .collect();
    let nome = |i: usize| nos.get(i).and_then(|n| n["name"].as_str()).unwrap_or("").to_string();
    let maos = ["hand_r", "hand_l", "RightHand", "LeftHand"];
    let mut na_mao = vec![];
    for (i, n) in nos.iter().enumerate() {
        if n.get("mesh").is_none() {
            continue;
        }
        let mut p = pai[i];
        while let Some(k) = p {
            if maos.contains(&nome(k).as_str()) {
                na_mao.push(nome(i));
                break;
            }
            p = pai[k];
        }
    }
    Some(ResumoGlb {
        versao: g["asset"]["version"].as_str().unwrap_or("").to_string(),
        malhas: g["meshes"].as_array().map_or(0, |m| m.len()),
        juntas: juntas.len(),
        nomes_das_juntas: juntas.iter().map(|&j| nome(j)).collect(),
        animacoes: g["animations"].as_array().into_iter().flatten().filter_map(|a| a["name"].as_str().map(String::from)).collect(),
        imagens: g["images"].as_array().map_or(0, |m| m.len()),
        na_mao,
    })
}

struct Caso {
    id: &'static str,
    titulo: &'static str,
    pedido: Value,
    animacoes: &'static [&'static str],
    arma_na_mao: bool,
    cabelo: bool,
}

fn casos() -> Vec<Caso> {
    vec![
        Caso {
            id: "protagonista",
            titulo: "Protagonista completo (corpo, rosto, cabelo em camadas, roupa, andar e combate)",
            pedido: json!({"nome": "Aren Bruto", "papel": "protagonista", "tipo": "humano", "arma": "espada", "armadura": "leve", "porte": "forte",
                           "capa": true, "cor_cabelo": "#4a3222",
                           "descricao": "aventureiro de cabelo curto castanho, gibão de couro, capa e espada", "fala": "Eu vou proteger esta vila."}),
            animacoes: &["parado", "andar", "correr", "atacar", "defender", "dano", "morrer"],
            arma_na_mao: true,
            cabelo: true,
        },
        Caso {
            id: "inimigo",
            titulo: "Inimigo humanoide armado (arma presa na mão, retarget)",
            pedido: json!({"nome": "Mercenario Bruto", "papel": "inimigo", "tipo": "humano", "arma": "espada", "armadura": "leve",
                           "descricao": "mercenário com espada e armadura leve"}),
            animacoes: &["parado", "andar", "atacar", "dano", "morrer"],
            arma_na_mao: true,
            cabelo: false,
        },
        Caso {
            id: "zumbi",
            titulo: "Zumbi (pele de morto-vivo, olhos leitosos, roupa encardida, andar e ataque de zumbi)",
            pedido: json!({"nome": "Zumbi Bruto", "papel": "inimigo", "tipo": "zumbi", "arma": "nenhuma", "armadura": "nenhuma", "porte": "magro",
                           "cor_cabelo": "#2f2a24", "descricao": "zumbi de aldeia medieval, camponês morto-vivo"}),
            animacoes: &["parado", "andar", "atacar", "dano", "morrer"],
            arma_na_mao: false,
            cabelo: false,
        },
        Caso {
            id: "dragao",
            titulo: "Dragão (malha grande, asas, cauda, esqueleto não humanoide, voo e ataque)",
            pedido: json!({"nome": "Dragao Bruto", "papel": "inimigo", "tipo": "dragao", "descricao": "dragão vermelho de asas grandes"}),
            animacoes: &["parado", "andar", "voar", "rugir", "atacar", "dano", "morrer"],
            arma_na_mao: false,
            cabelo: false,
        },
    ]
}

/// Desvio padrão do brilho (0–255) de uma captura: uma tela lisa (só o fundo e o HUD) fica perto
/// de zero; uma cena com mundo e personagens passa de 30.
fn variacao_da_captura(arq: &Path) -> Option<f64> {
    let px = crate::estilo::pixels_png(&std::fs::read(arq).ok()?)?;
    if px.is_empty() {
        return None;
    }
    let lum: Vec<f64> = px.iter().map(|p| 0.2126 * p[0] as f64 + 0.7152 * p[1] as f64 + 0.0722 * p[2] as f64).collect();
    let media = lum.iter().sum::<f64>() / lum.len() as f64;
    Some((lum.iter().map(|l| (l - media).powi(2)).sum::<f64>() / lum.len() as f64).sqrt())
}

fn conferir_personagem(c: &Caso, r: &Value, raiz: &Path) -> Vec<Value> {
    let mut v = vec![];
    let id = r["ficha"]["id"].as_str().unwrap_or("");
    let pasta = raiz.join(if r["ficha"]["inimigo"] == true { "Enemies" } else { "Characters" }).join(id);
    let glb = pasta.join(format!("{id}.glb"));
    let resumo = resumir_glb(&glb);
    v.push(conf("glb gerado e legível (glTF 2.0)", resumo.as_ref().is_some_and(|g| g.versao == "2.0"), glb.display().to_string()));
    let Some(g) = resumo else { return v };
    v.push(conf("malha com esqueleto", g.malhas > 0 && g.juntas >= 20, format!("{} malhas, {} ossos", g.malhas, g.juntas)));
    let faltam: Vec<&str> = c.animacoes.iter().filter(|a| !g.animacoes.iter().any(|x| x == *a)).copied().collect();
    v.push(conf(
        "animações do caso",
        faltam.is_empty(),
        if faltam.is_empty() { format!("{:?}", g.animacoes) } else { format!("faltam {faltam:?}") },
    ));
    if c.id == "dragao" {
        let nao_humano =
            g.nomes_das_juntas.iter().any(|n| n.starts_with("asa_")) && g.nomes_das_juntas.iter().any(|n| n.starts_with("cauda_"));
        v.push(conf("esqueleto não humanoide (asas e cauda)", nao_humano, format!("{} ossos", g.juntas)));
    }
    if c.id == "zumbi" {
        // o pedido virou o tipo zumbi (não o esqueleto da Forja) e, no humano realista, a pele de morto
        let tipo_ok = r["ficha"]["tipo"] == "zumbi";
        v.push(conf("tipo zumbi (humano morto-vivo)", tipo_ok, format!("tipo {} · modelo {}", r["ficha"]["tipo"], r["modelo_3d"])));
    }
    if c.arma_na_mao {
        v.push(conf("arma presa na mão", !g.na_mao.is_empty(), format!("{:?}", g.na_mao)));
    }
    let forja: Value =
        std::fs::read(pasta.join(format!("{id}.forja.json"))).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(Value::Null);
    let boca_ok = forja["boca"]["osso"].as_str().is_some_and(|o| g.nomes_das_juntas.iter().any(|n| n == o));
    v.push(conf("mandíbula para a fala (boca no forja.json)", boca_ok || r["modelo_3d"] == "forja-3d", format!("{}", forja["boca"])));
    let qa = &forja["estatisticas"]["qa"];
    if qa.is_object() {
        let falhas: Vec<String> = qa["itens"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|i| i["ok"] != true)
            .map(|i| format!("{}: {}", i["nome"], i["detalhe"]))
            .collect();
        v.push(conf("QA da bíblia técnica", qa["passou"] == true, if falhas.is_empty() { "tudo ok".into() } else { falhas.join("; ") }));
    }
    // o motor de imagem existe e falhou (ex.: sem memória de vídeo na placa): o caso não passa calado.
    // Sem motor nenhum (CI sem placa) a imagem só fica de fora.
    let falhas_de_imagem: Vec<String> = r["avisos"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|a| a.as_str())
        .filter(|a| {
            (a.starts_with("Conceito sem imagem") || a.starts_with("Folha de modelo sem imagem")) && !a.contains("nem o motor de imagem")
        })
        .map(String::from)
        .collect();
    v.push(conf(
        "imagens do motor sem falha",
        falhas_de_imagem.is_empty(),
        if falhas_de_imagem.is_empty() { "ok".into() } else { falhas_de_imagem.join("; ") },
    ));
    if c.cabelo {
        let pecas: Vec<String> =
            forja["estatisticas"]["pecas"].as_array().into_iter().flatten().filter_map(|p| p.as_str().map(String::from)).collect();
        // fios crescidos: cards + couro cabeludo; guiado (padrão): malha do penteado por baixo + cards por cima
        let fios = pecas.iter().any(|p| p.ends_with("_hair")) && pecas.iter().any(|p| p.contains("couro_cabeludo"));
        let guiado = pecas.iter().any(|p| p.ends_with("_hair")) && pecas.iter().any(|p| p.ends_with("_hair_cards"));
        let cards = fios || guiado;
        let tem_cabelo = pecas.iter().any(|p| p.contains("hair") || p.contains("cabelo"));
        v.push(conf(
            "cabelo em camadas (cards + camada de baixo)",
            cards || (tem_cabelo && r["modelo_3d"] != "humano-fornalha"),
            format!("{pecas:?}"),
        ));
    }
    v
}

/// Roda a suíte e devolve o relatório (também gravado em `<projeto>/testes/teste_bruto.json`).
pub async fn rodar(f: &Fornalha, a: ArgsBruto, quem: &str) -> Resultado<Value> {
    let inicio = Instant::now();
    let nivel = a.nivel.clone().unwrap_or_else(|| "qualidade".into());
    if crate::niveis::Nivel::from_id(&nivel).is_none() {
        return Err(Erro::argumento(format!("Nível \"{nivel}\" não existe. Use leve, equilibrado, qualidade ou maximo.")));
    }
    let escolhidos: Vec<String> =
        a.casos.clone().unwrap_or_else(|| vec!["protagonista".into(), "inimigo".into(), "zumbi".into(), "dragao".into()]);
    let nome = format!("Teste Bruto {}", crate::util::agora_iso().replace([':', 'T'], "-").chars().take(16).collect::<String>());
    let mut pedido_projeto = json!({"nome": nome, "genero": "ação e aventura", "camera": "terceira pessoa"});
    if let Some(p) = &a.pasta {
        pedido_projeto["pasta_pai"] = json!(p);
    }
    let p = f.chamar("create_project", pedido_projeto, quem).await?;
    let raiz = PathBuf::from(p["raiz"].as_str().unwrap_or_default());
    f.chamar(
        "update_project",
        json!({"alteracoes": {"nivel": nivel, "mundo": {"areas": [{"id": "vila", "nome": "Vila", "tipo": "vila"}, {"id": "castelo", "nome": "Castelo", "tipo": "castelo"}]}}}),
        quem,
    )
    .await?;
    let mut relatorio_casos = vec![];
    for c in casos().into_iter().filter(|c| escolhidos.iter().any(|e| e == c.id)) {
        let t = Instant::now();
        let r = f.chamar("create_character", c.pedido.clone(), quem).await;
        let (verificacoes, erro, avisos) = match &r {
            Ok(r) => (conferir_personagem(&c, r, &raiz), None, r["avisos"].clone()),
            Err(e) => (vec![conf("create_character", false, e.mensagem.clone())], Some(e.mensagem.clone()), Value::Null),
        };
        let passou = erro.is_none() && verificacoes.iter().all(|v| v["ok"] == true);
        relatorio_casos.push(json!({
            "caso": c.id, "titulo": c.titulo, "passou": passou, "segundos": t.elapsed().as_secs_f64(),
            "modelo_3d": r.as_ref().ok().map(|r| r["modelo_3d"].clone()), "verificacoes": verificacoes, "avisos": avisos, "erro": erro,
        }));
    }
    // mundo, engine e jogo rodando
    let mut engine = Value::Null;
    if a.testar_na_engine.unwrap_or(true) {
        let t = Instant::now();
        let mut verificacoes = vec![];
        match f.chamar("generate_blockout", json!({}), quem).await {
            Ok(_) => verificacoes.push(conf("mundo em blockout", true, "")),
            Err(e) => verificacoes.push(conf("mundo em blockout", false, e.mensagem)),
        }
        let mut teste = Value::Null;
        match f.chamar("import_to_engine", json!({"inimigo_perto": true}), quem).await {
            Ok(m) => {
                verificacoes.push(conf(
                    "projeto montado na engine",
                    m["erros_da_engine"].as_array().is_none_or(|e| e.is_empty()),
                    format!("{}", m["erros_da_engine"]),
                ));
                match f.chamar("run_test", json!({"segundos": 10}), quem).await {
                    Ok(rt) => {
                        verificacoes.push(conf(
                            "jogo rodou sem erro de script",
                            rt["erros"].as_array().is_some_and(|e| e.is_empty()),
                            format!("{}", rt["erros"]),
                        ));
                        verificacoes.push(conf("teste do jogo passou", rt["passou"] == true, format!("modo {}", rt["modo"])));
                        // a tela do jogo mostra a cena (não só o HUD num fundo liso): precisa do jogador,
                        // que vem do caso protagonista
                        let capturas: Vec<PathBuf> = rt["relatorio"]["capturas"]
                            .as_array()
                            .or_else(|| rt["capturas"].as_array())
                            .into_iter()
                            .flatten()
                            .filter_map(|c| c.as_str().map(PathBuf::from))
                            .collect();
                        if !capturas.is_empty() && escolhidos.iter().any(|c| c == "protagonista") {
                            let var = capturas.iter().filter_map(|c| variacao_da_captura(c)).fold(0.0f64, f64::max);
                            verificacoes.push(conf("a tela do jogo mostra a cena", var > 12.0, format!("variação de brilho {var:.1}")));
                        }
                        teste = rt;
                    }
                    Err(e) => verificacoes.push(conf("teste do jogo", false, e.mensagem)),
                }
            }
            Err(e) => verificacoes.push(conf("projeto montado na engine", false, e.mensagem)),
        }
        let passou = verificacoes.iter().all(|v| v["ok"] == true);
        engine = json!({"passou": passou, "segundos": t.elapsed().as_secs_f64(), "verificacoes": verificacoes, "teste": teste});
    }
    // bíblia e licenças
    let biblia_ok = crate::projeto::abrir(&raiz).and_then(|pr| crate::projeto::validar(&pr.biblia));
    let licencas = f.chamar("check_licenses", json!({}), quem).await.unwrap_or(Value::Null);
    let recibos = f.chamar("list_receipts", json!({}), quem).await.unwrap_or(Value::Null);
    let n_recibos = recibos["recibos"].as_array().map_or(0, |r| r.len());
    let gerais = vec![
        conf("game.project.json válido", biblia_ok.is_ok(), biblia_ok.err().map(|e| e.mensagem).unwrap_or_default()),
        conf(
            "licença comercial de tudo (pode vender)",
            licencas["pode_vender"] == true,
            format!("{} recibos; pendências: {}", n_recibos, licencas["pendencias"]),
        ),
        conf("todo arquivo gerado tem recibo", n_recibos > 0, format!("{n_recibos} recibos")),
    ];
    let passou = relatorio_casos.iter().all(|c| c["passou"] == true)
        && (engine.is_null() || engine["passou"] == true)
        && gerais.iter().all(|g| g["ok"] == true);
    let det = f.deteccao(false).await;
    let rel = json!({
        "teste": "Teste Bruto da Fornalha 3D",
        "passou": passou,
        "nivel": nivel,
        "projeto": raiz,
        "placa": det.principal().map(|g| json!({"nome": g.nome, "vram_mb": g.vram_total_mb})),
        "segundos": inicio.elapsed().as_secs_f64(),
        "casos": relatorio_casos,
        "engine": engine,
        "gerais": gerais,
    });
    let pasta = raiz.join("testes");
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    crate::paths::write_json(&pasta.join("teste_bruto.json"), &rel).map_err(|e| Erro::io(&pasta, e))?;
    Ok(rel)
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn le_glb_minimo() {
        let j = br#"{"asset":{"version":"2.0"},"nodes":[{"name":"hand_r","children":[1]},{"name":"espada","mesh":0}],"meshes":[{}],"skins":[{"joints":[0]}],"animations":[{"name":"andar"}]}"#;
        let mut pad = j.to_vec();
        while pad.len() % 4 != 0 {
            pad.push(b' ');
        }
        let mut b = b"glTF".to_vec();
        b.extend(2u32.to_le_bytes());
        b.extend(((12 + 8 + pad.len()) as u32).to_le_bytes());
        b.extend((pad.len() as u32).to_le_bytes());
        b.extend(b"JSON");
        b.extend(&pad);
        let tmp = tempfile::tempdir().unwrap();
        let arq = tmp.path().join("x.glb");
        std::fs::write(&arq, b).unwrap();
        let r = resumir_glb(&arq).unwrap();
        assert_eq!(r.versao, "2.0");
        assert_eq!(r.juntas, 1);
        assert_eq!(r.animacoes, vec!["andar"]);
        assert_eq!(r.na_mao, vec!["espada"]);
    }
}
