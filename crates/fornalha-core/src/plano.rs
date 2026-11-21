//! O cérebro coordenando: um pedido livre ("faça a vila com dois goblins, uma
//! espada e música de combate, e teste o jogo") vira um plano de ferramentas.
//! Com o Ignis aberto, o cérebro (Qwen3) escreve o plano em JSON; sem ele, a
//! Fornalha usa regras para os pedidos mais comuns. O plano vai para a fila
//! (agora ou à noite) amarrado ao projeto em que foi pedido.

use serde::Deserialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::fila::{self, Quando, FERRAMENTAS_DA_FILA};
use crate::forja;
use crate::ignis;
use crate::projeto::Projeto;
use crate::servico::Fornalha;

const MAX_PASSOS: usize = 12;

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsPedido {
    pub projeto: Option<String>,
    pub pedido: String,
    /// "agora" (padrão), "noite" ou "nao" (só mostra o plano).
    pub executar: Option<String>,
}

fn sem_acento(t: &str) -> String {
    t.to_lowercase()
        .chars()
        .map(|c| match c {
            'á' | 'à' | 'â' | 'ã' => 'a',
            'é' | 'ê' => 'e',
            'í' => 'i',
            'ó' | 'ô' | 'õ' => 'o',
            'ú' | 'ü' => 'u',
            'ç' => 'c',
            x => x,
        })
        .collect()
}

/// Quantos (um, dois, 3...) aparece logo antes da palavra.
fn quantidade_antes(texto: &str, pos: usize) -> usize {
    let antes: Vec<&str> = texto[..pos].split_whitespace().rev().take(3).collect();
    for p in antes {
        let n = match p.trim_matches(|c: char| !c.is_alphanumeric()) {
            "um" | "uma" | "1" => 1,
            "dois" | "duas" | "2" => 2,
            "tres" | "3" => 3,
            "quatro" | "4" => 4,
            "cinco" | "5" => 5,
            _ => continue,
        };
        return n;
    }
    1
}

fn passo(ferramenta: &str, argumentos: Value, motivo: &str) -> Value {
    json!({"ferramenta": ferramenta, "argumentos": argumentos, "motivo": motivo})
}

/// Plano por regras (sem o cérebro), para os pedidos mais comuns.
pub fn plano_por_regras(pedido: &str) -> Vec<Value> {
    let t = sem_acento(pedido);
    let mut passos = Vec::new();
    let tem = |ps: &[&str]| ps.iter().any(|p| t.contains(p));

    // mundo ("música da floresta" é o clima da música, não um pedido de mundo)
    let da_musica = |pos: usize| t[..pos].split_whitespace().rev().take(3).any(|w| w.starts_with("musica") || w.starts_with("trilha"));
    let areas: Vec<&str> = forja::AREAS.iter().copied().filter(|a| t.match_indices(a).any(|(pos, _)| !da_musica(pos))).collect();
    if !areas.is_empty() || tem(&["mundo", "mapa", "cenario", "blockout", "fase do jogo"]) {
        let lista: Vec<Value> = areas.iter().map(|a| json!({"id": a, "tipo": a})).collect();
        let args = if lista.is_empty() { json!({}) } else { json!({"areas": lista}) };
        passos.push(passo("generate_blockout", args, "o mundo em blockout"));
    }
    // personagens
    let mut inimigos: Vec<(String, usize)> = Vec::new();
    for (palavra, tipo) in [("goblin", "goblin"), ("orc", "orc"), ("esquelet", "esqueleto"), ("demonio", "demonio"), ("monstro", "orc")] {
        if let Some(pos) = t.find(palavra) {
            inimigos.push((tipo.into(), quantidade_antes(&t, pos)));
        }
    }
    if inimigos.is_empty() {
        if let Some(pos) = t.find("inimigo") {
            inimigos.push(("orc".into(), quantidade_antes(&t, pos)));
        }
    }
    let chefe = tem(&["chefe", "boss"]);
    for (tipo, n) in &inimigos {
        for i in 0..(*n).min(5) {
            passos.push(passo(
                "create_character",
                json!({"papel": "inimigo", "tipo": tipo, "descricao": format!("{tipo} inimigo"), "conceito": true, "seed": 11 + i as u64}),
                "inimigo pedido",
            ));
        }
    }
    if chefe {
        passos.push(passo("create_character", json!({"papel": "chefe", "descricao": "chefe da área", "conceito": true}), "chefe pedido"));
    }
    if tem(&["heroi", "protagonista", "personagem principal", "jogador"]) {
        passos.push(passo("create_character", json!({"papel": "protagonista", "conceito": true}), "o herói"));
    }
    for (palavra, papel) in
        [("ferreiro", "ferreiro"), ("mercador", "mercador"), ("aldeao", "aldeão"), ("aliado", "aliado"), ("npc", "aliado")]
    {
        if t.contains(palavra) {
            passos.push(passo("create_character", json!({"papel": "aliado", "descricao": papel, "conceito": true}), "personagem pedido"));
        }
    }
    // armas e objetos
    for a in forja::ARMAS {
        if t.contains(a) || (a == "lanca" && t.contains("lanca")) {
            passos.push(passo("generate_3d", json!({"tipo": "arma", "modelo": a}), "arma pedida"));
        }
    }
    for (palavra, o) in [
        ("barril", "barril"),
        ("caixa", "caixa"),
        ("bau", "bau"),
        ("arvore", "arvore"),
        ("pedra", "pedra"),
        ("casa", "casa"),
        ("tocha", "tocha"),
        ("cerca", "cerca"),
        ("pocao", "pocao"),
    ] {
        if t.contains(palavra) {
            passos.push(passo("generate_3d", json!({"tipo": "objeto", "modelo": o}), "objeto pedido"));
        }
    }
    // áudio
    if tem(&["musica", "trilha"]) {
        let situacao = ["chefe", "combate", "masmorra", "floresta", "vila", "exploracao"]
            .into_iter()
            .find(|s| t.contains(s) || (*s == "combate" && t.contains("batalha")))
            .unwrap_or("exploracao");
        passos.push(passo("generate_music", json!({"situacao": situacao}), "trilha pedida"));
    }
    if tem(&["efeito", "efeitos", "sfx", "sons", "som "]) {
        passos.push(passo("generate_sfx", json!({}), "efeitos sonoros"));
    }
    if tem(&["codigo", "script"]) {
        passos.push(passo("generate_code", json!({}), "código do jogo"));
    }
    if tem(&["teste", "testa", "testar", "jogar", "rodar o jogo", "roda o jogo"]) {
        passos.push(passo("import_to_engine", json!({}), "montar as cenas na engine"));
        passos.push(passo("run_test", json!({"video": true}), "testar o jogo"));
    }
    passos.truncate(MAX_PASSOS);
    passos
}

async fn plano_pelo_cerebro(f: &Fornalha, p: &Projeto, pedido: &str) -> Resultado<Vec<Value>> {
    let ferramentas: Vec<Value> = crate::ferramentas::lista()
        .into_iter()
        .filter(|t| FERRAMENTAS_DA_FILA.contains(&t.nome))
        .map(|t| json!({"nome": t.nome, "descricao": t.descricao, "argumentos": t.esquema["properties"]}))
        .collect();
    let esquema = json!({
        "type": "object", "additionalProperties": false,
        "properties": {"passos": {"type": "array", "maxItems": MAX_PASSOS, "items": {
            "type": "object", "additionalProperties": false,
            "properties": {
                "ferramenta": {"type": "string", "enum": FERRAMENTAS_DA_FILA},
                "argumentos": {"type": "object"},
                "motivo": {"type": "string"}
            },
            "required": ["ferramenta", "argumentos", "motivo"]
        }}},
        "required": ["passos"]
    });
    let sistema = format!(
        "Você é o diretor de produção de um estúdio de jogos e coordena as ferramentas da Fornalha. \
         Transforme o pedido em passos, na ordem certa (mundo e personagens antes de montar na engine; testar por último). \
         Use só as ferramentas da lista e só os argumentos de cada uma; não invente caminhos de arquivo. \
         Não inclua o argumento \"projeto\". Responda só o JSON.\nFerramentas: {}",
        serde_json::to_string(&ferramentas).unwrap_or_default()
    );
    let pedido = format!("{}.\nPedido: {pedido}", crate::geracao::texto_do_projeto(p));
    let v = ignis::conversar_json(f.porta_ignis(), None, &sistema, &pedido, &esquema).await?;
    Ok(v["passos"].as_array().cloned().unwrap_or_default())
}

const ARGUMENTOS_DE_ARQUIVO: [&str; 5] = ["arquivo", "entrada", "jogador", "origem", "imagem"];

fn tipo_confere(valor: &Value, esquema: &Value) -> bool {
    match esquema["type"].as_str() {
        Some("string") => valor.is_string(),
        Some("integer") => valor.is_u64() || valor.is_i64(),
        Some("number") => valor.is_number(),
        Some("boolean") => valor.is_boolean(),
        Some("array") => valor.is_array(),
        Some("object") => valor.is_object(),
        _ => true,
    }
}

/// Confere cada passo do cérebro contra o esquema da ferramenta: tira argumento que
/// não existe, valor fora da lista ou do tipo, arquivo que não está no projeto; o
/// que é obrigatório e faltou vem do plano por regras. Passo sem conserto sai.
pub fn sanear(passos: Vec<Value>, pedido: &str, raiz: &std::path::Path, avisos: &mut Vec<String>) -> Vec<Value> {
    let regras = plano_por_regras(pedido);
    let esquemas: std::collections::HashMap<&str, Value> = crate::ferramentas::lista().into_iter().map(|t| (t.nome, t.esquema)).collect();
    let mut saida = Vec::new();
    for mut s in passos.into_iter().take(MAX_PASSOS) {
        let Some(nome) = s["ferramenta"].as_str().filter(|n| FERRAMENTAS_DA_FILA.contains(n)).map(String::from) else { continue };
        let esquema = esquemas.get(nome.as_str()).cloned().unwrap_or(Value::Null);
        let props = esquema["properties"].as_object().cloned().unwrap_or_default();
        let mut args = serde_json::Map::new();
        let mut tirados = Vec::new();
        for (k, v) in s["argumentos"].as_object().cloned().unwrap_or_default() {
            if k == "projeto" {
                continue; // a fila sempre usa o projeto em que o pedido foi feito
            }
            let Some(p) = props.get(&k) else {
                tirados.push(k);
                continue;
            };
            let na_lista = p["enum"].as_array().is_none_or(|l| l.contains(&v));
            let arquivo_ok = !ARGUMENTOS_DE_ARQUIVO.contains(&k.as_str()) || v.as_str().is_some_and(|c| raiz.join(c).is_file());
            if tipo_confere(&v, p) && na_lista && arquivo_ok {
                args.insert(k, v);
            } else {
                tirados.push(k);
            }
        }
        for obrig in esquema["required"].as_array().cloned().unwrap_or_default().iter().filter_map(|x| x.as_str()) {
            if args.contains_key(obrig) {
                continue;
            }
            let dica = regras.iter().find(|r| r["ferramenta"] == nome.as_str()).and_then(|r| r["argumentos"].get(obrig)).cloned();
            if let Some(v) = dica {
                args.insert(obrig.to_string(), v);
            }
        }
        let falta: Vec<&str> = esquema["required"]
            .as_array()
            .map(|l| l.iter().filter_map(|x| x.as_str()).filter(|r| !args.contains_key(*r)).collect())
            .unwrap_or_default();
        if !falta.is_empty() {
            avisos.push(format!("Tirei o passo {nome} do plano do cérebro: faltou {}.", falta.join(", ")));
            continue;
        }
        if !tirados.is_empty() {
            avisos.push(format!("No passo {nome}, ignorei argumentos que não servem: {}.", tirados.join(", ")));
        }
        s["argumentos"] = Value::Object(args);
        saida.push(s);
    }
    saida
}

/// O que as regras acharam no pedido e o cérebro esqueceu (ferramenta que nem
/// aparece no plano dele) entra antes de montar na engine e testar.
pub fn completar_com_regras(mut passos: Vec<Value>, pedido: &str, avisos: &mut Vec<String>) -> Vec<Value> {
    let regras = plano_por_regras(pedido);
    let tem: std::collections::HashSet<String> = passos.iter().filter_map(|s| s["ferramenta"].as_str().map(String::from)).collect();
    let faltando: Vec<Value> = regras.into_iter().filter(|r| r["ferramenta"].as_str().is_some_and(|n| !tem.contains(n))).collect();
    if faltando.is_empty() {
        return passos;
    }
    let nomes: std::collections::BTreeSet<&str> = faltando.iter().filter_map(|r| r["ferramenta"].as_str()).collect();
    avisos.push(format!(
        "Completei o plano do cérebro com o que ele esqueceu do pedido: {}.",
        nomes.into_iter().collect::<Vec<_>>().join(", ")
    ));
    passos.extend(faltando);
    // gerar primeiro, depois montar na engine, testar por último (a ordem de cada grupo fica)
    let ordem = |s: &Value| match s["ferramenta"].as_str() {
        Some("import_to_engine") => 1,
        Some("run_test") => 2,
        _ => 0,
    };
    passos.sort_by_key(ordem);
    passos.truncate(MAX_PASSOS);
    passos
}

/// plan_request: pedido livre → plano (cérebro ou regras) → fila.
pub async fn planejar(f: &Fornalha, a: ArgsPedido, quem: &str) -> Resultado<Value> {
    if a.pedido.trim().is_empty() {
        return Err(Erro::argumento("Escreva o pedido (ex.: \"faça a vila com dois goblins e música de combate, e teste o jogo\")."));
    }
    let p = f.projeto(a.projeto.as_deref())?;
    let mut avisos = Vec::new();
    let mut origem = "regras";
    let cap = ignis::capacidades(f.porta_ignis()).await;
    let mut passos = Vec::new();
    if cap["conectado"] == true && cap["conversa"].as_array().is_some_and(|v| !v.is_empty()) {
        match plano_pelo_cerebro(f, &p, &a.pedido).await {
            Ok(v) => {
                passos = sanear(v, &a.pedido, &p.raiz, &mut avisos);
                if !passos.is_empty() {
                    passos = completar_com_regras(passos, &a.pedido, &mut avisos);
                }
                origem = "cerebro";
            }
            Err(e) => avisos.push(format!("O cérebro não fez o plano ({}); usei as regras da Fornalha.", e.mensagem)),
        }
    } else {
        avisos.push("O Ignis não está aberto: o plano saiu das regras da Fornalha, sem o cérebro.".into());
    }
    if passos.is_empty() {
        passos = plano_por_regras(&a.pedido);
        origem = "regras";
    }
    if passos.is_empty() {
        return Err(Erro::novo(
            "pedido_sem_plano",
            "Não consegui transformar o pedido em passos. Abra o Ignis (o cérebro entende pedidos livres) ou peça algo como \
             \"um orc inimigo, uma espada, a música da vila e testar o jogo\".",
        ));
    }
    let quando = match a.executar.as_deref().unwrap_or("agora") {
        "nao" | "não" => None,
        "noite" => Some(Quando::Noite),
        _ => Some(Quando::Agora),
    };
    let mut tarefas = Vec::new();
    if let Some(q) = quando {
        let grupo = format!("plano_{}", crate::util::id_aleatorio(6));
        let quem_faz = if origem == "cerebro" { format!("cerebro, a pedido de {quem}") } else { quem.to_string() };
        for s in &passos {
            let mut args = s["argumentos"].clone();
            args["projeto"] = json!(p.raiz);
            let t = fila::enfileirar(
                f,
                s["ferramenta"].as_str().unwrap_or_default(),
                args,
                &quem_faz,
                q,
                s["motivo"].as_str().map(String::from),
                Some(grupo.clone()),
            )?;
            tarefas.push(t.id);
        }
    }
    Ok(json!({
        "pedido": a.pedido, "origem": origem, "passos": passos, "tarefas": tarefas,
        "quando": quando.map(|q| if q == Quando::Noite { "noite" } else { "agora" }).unwrap_or("so_o_plano"),
        "avisos": avisos,
    }))
}
