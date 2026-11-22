//! Converte um fluxo salvo pela interface do ComfyUI (o formato dos modelos oficiais, com "nodes" e
//! "links") para o formato que a API executa (`/prompt`), usando a lista oficial de nós do próprio
//! ComfyUI (`/object_info`) para saber o nome de cada valor. Assim a Fornalha usa os fluxos oficiais
//! (3D, textura, etc.) sem reescrever cada um à mão.
//!
//! Também "poda" o fluxo: resolve os interruptores fixos (ComfySwitchNode com valor constante), tira
//! os nós que não levam às saídas escolhidas e troca valores (imagem de entrada, passos, tamanhos).

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{json, Map, Value};

use crate::erro::{Erro, Resultado};

/// Tipos que só existem na interface (não vão para a API).
const SO_INTERFACE: [&str; 5] = ["Note", "MarkdownNote", "Reroute", "PrimitiveNode", "Label"];

/// O que entra no lugar de um link: outro nó (id, saída) ou um valor fixo.
#[derive(Debug, Clone, PartialEq)]
enum Fonte {
    No(String, u64),
    Valor(Value),
    Nada,
}

struct Grafo<'a> {
    nos: BTreeMap<String, &'a Value>,
    /// id do link → (nó de origem, saída de origem)
    links: BTreeMap<u64, (String, u64)>,
}

fn id_de(v: &Value) -> String {
    match v {
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        _ => String::new(),
    }
}

impl<'a> Grafo<'a> {
    fn novo(ui: &'a Value) -> Resultado<Self> {
        let lista =
            ui["nodes"].as_array().ok_or_else(|| Erro::argumento("O fluxo não tem \"nodes\" (não é um fluxo da interface do ComfyUI)."))?;
        let nos = lista.iter().map(|n| (id_de(&n["id"]), n)).collect();
        let mut links = BTreeMap::new();
        for l in ui["links"].as_array().into_iter().flatten() {
            // [id, origem, saída, destino, entrada, tipo] (ou objeto, nos fluxos novos)
            let (id, de, saida) = if let Some(a) = l.as_array() {
                (a.first().and_then(Value::as_u64), a.get(1).map(id_de), a.get(2).and_then(Value::as_u64))
            } else {
                (l["id"].as_u64(), Some(id_de(&l["origin_id"])), l["origin_slot"].as_u64())
            };
            if let (Some(id), Some(de), Some(saida)) = (id, de, saida) {
                links.insert(id, (de, saida));
            }
        }
        Ok(Self { nos, links })
    }

    fn modo(&self, id: &str) -> u64 {
        self.nos.get(id).and_then(|n| n["mode"].as_u64()).unwrap_or(0)
    }

    /// Segue o link até um nó de verdade (atravessa Reroute e nós desviados; PrimitiveNode vira valor).
    fn resolver(&self, link: u64, profundidade: usize) -> Fonte {
        if profundidade > 64 {
            return Fonte::Nada;
        }
        let Some((de, saida)) = self.links.get(&link) else { return Fonte::Nada };
        let Some(n) = self.nos.get(de) else { return Fonte::Nada };
        let tipo = n["type"].as_str().unwrap_or("");
        let entrada_link = |i: usize| n["inputs"].as_array().and_then(|e| e.get(i)).and_then(|e| e["link"].as_u64());
        match (tipo, self.modo(de)) {
            ("Reroute", _) => entrada_link(0).map(|l| self.resolver(l, profundidade + 1)).unwrap_or(Fonte::Nada),
            ("PrimitiveNode", _) => n["widgets_values"].get(0).cloned().map(Fonte::Valor).unwrap_or(Fonte::Nada),
            (_, 2) => Fonte::Nada,
            (_, 4) => {
                // desviado: a saída vira a primeira entrada do mesmo tipo
                let tipo_saida =
                    n["outputs"].as_array().and_then(|o| o.get(*saida as usize)).and_then(|o| o["type"].as_str()).unwrap_or("");
                let achou =
                    n["inputs"].as_array().into_iter().flatten().find(|e| e["type"].as_str() == Some(tipo_saida) && e["link"].is_u64());
                achou.and_then(|e| e["link"].as_u64()).map(|l| self.resolver(l, profundidade + 1)).unwrap_or(Fonte::Nada)
            }
            _ => Fonte::No(de.clone(), *saida),
        }
    }
}

/// Tipos que a interface mostra como campo (widget) e guarda em `widgets_values`.
const TIPOS_WIDGET: [&str; 11] =
    ["INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COMFY_DYNAMICCOMBO_V3", "LOAD_3D", "CURVE", "COLOR", "IMAGECOMPARE", "AUDIO_RECORD"];

/// O valor de entrada é um "widget" (número, texto, lista de opções) e não um link de outro nó?
fn eh_widget(spec: &Value) -> bool {
    match spec.get(0) {
        Some(Value::Array(_)) => true,
        Some(Value::String(t)) => TIPOS_WIDGET.contains(&t.as_str()),
        _ => false,
    }
}

/// Depois deste valor a interface guarda mais um (o "fixed"/"randomize" da semente, o botão de enviar)?
fn valores_extras(nome: &str, spec: &Value) -> usize {
    let o = opcoes(spec);
    let verdade = |v: &Value| match v {
        Value::Bool(b) => *b,
        Value::String(s) => !s.is_empty(),
        Value::Null => false,
        _ => true,
    };
    let semente = spec.get(0).and_then(Value::as_str) == Some("INT") && matches!(nome, "seed" | "noise_seed");
    let mut n = 0;
    if verdade(&o["control_after_generate"]) || semente {
        n += 1;
    }
    if verdade(&o["image_upload"]) || verdade(&o["video_upload"]) || verdade(&o["audio_upload"]) {
        n += 1;
    }
    n
}

fn opcoes(spec: &Value) -> &Value {
    spec.get(1).unwrap_or(&Value::Null)
}

/// Converte o fluxo da interface para o formato da API.
pub fn para_api(ui: &Value, object_info: &Value) -> Resultado<Value> {
    let g = Grafo::novo(ui)?;
    let mut api = Map::new();
    let mut desconhecidos = BTreeSet::new();
    for (id, n) in &g.nos {
        let tipo = n["type"].as_str().unwrap_or("");
        if SO_INTERFACE.contains(&tipo) || matches!(g.modo(id), 2 | 4) {
            continue;
        }
        let Some(def) = object_info.get(tipo) else {
            desconhecidos.insert(tipo.to_string());
            continue;
        };
        let entradas_ui: BTreeMap<&str, &Value> =
            n["inputs"].as_array().into_iter().flatten().filter_map(|e| e["name"].as_str().map(|nome| (nome, e))).collect();
        let valores_ui = &n["widgets_values"];
        let mut indice = 0usize;
        let mut entradas = Map::new();
        let mut ordem: Vec<(String, &Value)> = vec![];
        for grupo in ["required", "optional"] {
            let nomes: Vec<String> = def["input_order"][grupo]
                .as_array()
                .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                .unwrap_or_else(|| def["input"][grupo].as_object().map(|m| m.keys().cloned().collect()).unwrap_or_default());
            for nome in nomes {
                if let Some(spec) = def["input"][grupo].get(&nome) {
                    ordem.push((nome, spec));
                }
            }
        }
        // entradas na ordem dos widgets; os combos dinâmicos trazem as entradas da opção escolhida logo
        // depois deles, com o nome "combo.entrada"
        let mut fila: std::collections::VecDeque<(String, Value)> = ordem.into_iter().map(|(n, s)| (n, s.clone())).collect();
        while let Some((nome, spec)) = fila.pop_front() {
            let na_ui = entradas_ui.get(nome.as_str());
            let link = na_ui.and_then(|e| e["link"].as_u64());
            // é campo se a interface marcou como widget, ou se nem aparece entre os encaixes do nó
            let widget = match na_ui {
                Some(e) => e.get("widget").is_some_and(|w| !w.is_null()),
                None => eh_widget(&spec),
            };
            if widget {
                let valor = match valores_ui {
                    Value::Array(a) => {
                        let v = a.get(indice).cloned();
                        indice += 1 + valores_extras(&nome, &spec);
                        v
                    }
                    Value::Object(m) => m.get(&nome).cloned(),
                    _ => None,
                };
                if spec.get(0).and_then(Value::as_str) == Some("COMFY_DYNAMICCOMBO_V3") {
                    let chave = valor.as_ref().and_then(Value::as_str).unwrap_or("");
                    if let Some(op) = opcoes(&spec)["options"].as_array().and_then(|o| o.iter().find(|o| o["key"] == chave)) {
                        let mut aninhadas = vec![];
                        for grupo in ["required", "optional"] {
                            for (sub, sspec) in op["inputs"][grupo].as_object().into_iter().flatten() {
                                aninhadas.push((format!("{nome}.{sub}"), sspec.clone()));
                            }
                        }
                        for item in aninhadas.into_iter().rev() {
                            fila.push_front(item);
                        }
                    }
                }
                match link.map(|l| g.resolver(l, 0)) {
                    Some(Fonte::No(de, saida)) => {
                        entradas.insert(nome, json!([de, saida]));
                    }
                    Some(Fonte::Valor(v)) => {
                        entradas.insert(nome, v);
                    }
                    _ => {
                        if let Some(v) = valor {
                            entradas.insert(nome, v);
                        }
                    }
                }
            } else if let Some(l) = link {
                match g.resolver(l, 0) {
                    Fonte::No(de, saida) => {
                        entradas.insert(nome, json!([de, saida]));
                    }
                    Fonte::Valor(v) => {
                        entradas.insert(nome, v);
                    }
                    Fonte::Nada => {}
                }
            }
        }
        let titulo = n["title"].as_str().unwrap_or(tipo);
        api.insert(id.clone(), json!({"class_type": tipo, "inputs": entradas, "_meta": {"title": titulo}}));
    }
    if !desconhecidos.is_empty() {
        return Err(Erro::novo(
            "comfyui_no_desconhecido",
            format!(
                "O ComfyUI instalado não conhece estes nós do fluxo: {}. Atualize o ComfyUI.",
                desconhecidos.into_iter().collect::<Vec<_>>().join(", ")
            ),
        ));
    }
    Ok(Value::Object(api))
}

/// Resolve os interruptores com valor fixo (ComfySwitchNode / "switch" constante, direto ou vindo de
/// um PrimitiveBoolean): quem usava a saída do interruptor passa a usar o ramo escolhido.
pub fn resolver_interruptores(api: &mut Value) {
    let Some(m) = api.as_object() else { return };
    let mut troca: BTreeMap<String, Value> = BTreeMap::new();
    for (id, n) in m {
        if !n["class_type"].as_str().is_some_and(|t| t.contains("Switch")) {
            continue;
        }
        let e = &n["inputs"];
        let chave = match &e["switch"] {
            Value::Bool(b) => Some(*b),
            Value::Array(l) => {
                let de = l.first().map(id_de).unwrap_or_default();
                m.get(&de).filter(|p| p["class_type"] == "PrimitiveBoolean").and_then(|p| p["inputs"]["value"].as_bool())
            }
            _ => None,
        };
        if let Some(b) = chave {
            let ramo = if b { &e["on_true"] } else { &e["on_false"] };
            if !ramo.is_null() {
                troca.insert(id.clone(), ramo.clone());
            }
        }
    }
    if troca.is_empty() {
        return;
    }
    let ids: Vec<String> = m.keys().cloned().collect();
    for id in ids {
        if troca.contains_key(&id) {
            continue;
        }
        if let Some(entradas) = api[&id]["inputs"].as_object_mut() {
            for v in entradas.values_mut() {
                // vários interruptores em cadeia: segue até um que não seja interruptor
                for _ in 0..8 {
                    let alvo = v.as_array().and_then(|l| l.first()).map(id_de);
                    match alvo.and_then(|a| troca.get(&a)) {
                        Some(r) => *v = r.clone(),
                        None => break,
                    }
                }
            }
        }
    }
    if let Some(m) = api.as_object_mut() {
        for id in troca.keys() {
            m.remove(id);
        }
    }
}

/// Fica só com as saídas escolhidas (pelo tipo) e o que leva até elas.
pub fn podar(api: &mut Value, saidas: &[&str]) -> Resultado<()> {
    let m = api.as_object().cloned().unwrap_or_default();
    let mut pilha: Vec<String> =
        m.iter().filter(|(_, n)| n["class_type"].as_str().is_some_and(|t| saidas.contains(&t))).map(|(id, _)| id.clone()).collect();
    if pilha.is_empty() {
        return Err(Erro::novo("comfyui_fluxo", format!("O fluxo não tem nenhuma das saídas {saidas:?}.")));
    }
    let mut vivos = BTreeSet::new();
    while let Some(id) = pilha.pop() {
        if !vivos.insert(id.clone()) {
            continue;
        }
        for v in m.get(&id).and_then(|n| n["inputs"].as_object()).into_iter().flat_map(|e| e.values()) {
            if let Some(de) = v.as_array().and_then(|l| (l.len() == 2 && l[1].is_u64()).then(|| id_de(&l[0]))) {
                pilha.push(de);
            }
        }
    }
    if let Some(mm) = api.as_object_mut() {
        mm.retain(|id, _| vivos.contains(id));
    }
    Ok(())
}

/// Troca um valor de entrada em todos os nós de um tipo (ex.: a imagem do LoadImage, os passos).
pub fn trocar(api: &mut Value, tipo: &str, entrada: &str, valor: Value) -> usize {
    let mut n = 0;
    for no in api.as_object_mut().into_iter().flat_map(|m| m.values_mut()) {
        if no["class_type"] == tipo && !no["inputs"][entrada].is_array() {
            no["inputs"][entrada] = valor.clone();
            n += 1;
        }
    }
    n
}

#[cfg(test)]
mod testes {
    use super::*;

    fn info() -> Value {
        json!({
            "LoadImage": {"input": {"required": {"image": [["a.png", "b.png"], {"image_upload": true}]}},
                          "input_order": {"required": ["image"]}},
            "KSampler": {"input": {"required": {
                    "model": ["MODEL"], "seed": ["INT", {"default": 0, "control_after_generate": true}], "steps": ["INT", {"default": 20}],
                    "cfg": ["FLOAT", {}], "sampler_name": [["euler", "dpmpp"]], "scheduler": [["normal", "simple"]],
                    "positive": ["CONDITIONING"], "negative": ["CONDITIONING"], "latent_image": ["LATENT"], "denoise": ["FLOAT", {}]}},
                "input_order": {"required": ["model", "seed", "steps", "cfg", "sampler_name", "scheduler", "positive", "negative", "latent_image", "denoise"]}},
            "UNETLoader": {"input": {"required": {"unet_name": [["x.safetensors"]], "weight_dtype": [["default"]]}},
                           "input_order": {"required": ["unet_name", "weight_dtype"]}},
            "Cond": {"input": {"required": {"image": ["IMAGE"]}}, "input_order": {"required": ["image"]}},
            "PrimitiveBoolean": {"input": {"required": {"value": ["BOOLEAN", {}]}}, "input_order": {"required": ["value"]}},
            "ComfySwitchNode": {"input": {"required": {"switch": ["BOOLEAN", {}]}, "optional": {"on_false": ["*", {"lazy": true}], "on_true": ["*", {"lazy": true}]}},
                                "input_order": {"required": ["switch"], "optional": ["on_false", "on_true"]}},
            "Save": {"input": {"required": {"latent": ["LATENT"]}}, "input_order": {"required": ["latent"]}}
        })
    }

    fn ui() -> Value {
        json!({
            "nodes": [
                {"id": 1, "type": "LoadImage", "mode": 0, "widgets_values": ["b.png", "image"], "outputs": [{"type": "IMAGE"}]},
                {"id": 2, "type": "UNETLoader", "mode": 0, "widgets_values": ["x.safetensors", "default"]},
                {"id": 9, "type": "UNETLoader", "mode": 0, "widgets_values": ["outro.safetensors", "default"]},
                {"id": 3, "type": "Reroute", "mode": 0, "inputs": [{"name": "", "link": 1}]},
                {"id": 4, "type": "KSampler", "mode": 0, "widgets_values": [7, "fixed", 12, 7.5, "euler", "simple", 1.0],
                 "inputs": [{"name": "model", "link": 2}, {"name": "positive", "link": 3}, {"name": "negative", "link": 3},
                            {"name": "latent_image", "link": 4}, {"name": "steps", "link": 5, "widget": {"name": "steps"}}]},
                {"id": 5, "type": "PrimitiveNode", "mode": 0, "widgets_values": [30]},
                {"id": 6, "type": "Cond", "mode": 0, "inputs": [{"name": "image", "link": 6}]},
                {"id": 7, "type": "Note", "mode": 0, "widgets_values": ["texto"]},
                {"id": 8, "type": "Save", "mode": 0, "inputs": [{"name": "latent", "link": 7}]},
                {"id": 10, "type": "PrimitiveBoolean", "mode": 0, "widgets_values": [true]},
                {"id": 11, "type": "ComfySwitchNode", "mode": 0, "widgets_values": [false],
                 "inputs": [{"name": "on_false", "link": 8}, {"name": "on_true", "link": 9}, {"name": "switch", "link": 10, "widget": {"name": "switch"}}]},
                {"id": 12, "type": "Save", "mode": 2, "inputs": [{"name": "latent", "link": 7}]}
            ],
            "links": [
                [1, 6, 0, 3, 0, "CONDITIONING"], [2, 11, 0, 4, 0, "MODEL"], [3, 3, 0, 4, 1, "CONDITIONING"], [4, 1, 0, 4, 3, "LATENT"],
                [5, 5, 0, 4, 4, "INT"], [6, 1, 0, 6, 0, "IMAGE"], [7, 4, 0, 8, 0, "LATENT"],
                [8, 9, 0, 11, 0, "MODEL"], [9, 2, 0, 11, 1, "MODEL"], [10, 10, 0, 11, 2, "BOOLEAN"]
            ]
        })
    }

    #[test]
    fn converte_widgets_links_reroute_e_primitivo() {
        let api = para_api(&ui(), &info()).unwrap();
        let k = &api["4"]["inputs"];
        assert_eq!(k["seed"], 7);
        assert_eq!(k["steps"], 30, "o PrimitiveNode da interface vira valor");
        assert_eq!(k["cfg"], 7.5, "pulou o \"fixed\" depois da semente");
        assert_eq!(k["scheduler"], "simple");
        assert_eq!(k["positive"], json!(["6", 0]), "o Reroute é atravessado");
        assert_eq!(api["1"]["inputs"]["image"], "b.png");
        assert!(api.get("7").is_none() && api.get("3").is_none() && api.get("12").is_none(), "nota, reroute e nó mudo saem");
        assert_eq!(api["11"]["inputs"]["switch"], json!(["10", 0]));
    }

    #[test]
    fn resolve_interruptor_e_poda() {
        let mut api = para_api(&ui(), &info()).unwrap();
        resolver_interruptores(&mut api);
        assert_eq!(api["4"]["inputs"]["model"], json!(["2", 0]), "PrimitiveBoolean = true → on_true");
        podar(&mut api, &["Save"]).unwrap();
        let ids: BTreeSet<&str> = api.as_object().unwrap().keys().map(String::as_str).collect();
        assert_eq!(ids, ["1", "2", "4", "6", "8"].into_iter().collect(), "o UNETLoader do outro ramo e o booleano saem");
        assert_eq!(trocar(&mut api, "LoadImage", "image", json!("minha.png")), 1);
        assert_eq!(api["1"]["inputs"]["image"], "minha.png");
    }
}
