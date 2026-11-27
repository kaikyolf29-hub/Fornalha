//! As gerações do plano, encadeadas: ficha (cérebro no Ignis), conceito (imagem
//! no Ignis), 3D, esqueleto e animações (Forja no Blender), voz (Ignis), efeitos
//! e música (síntese da Fornalha), mundo em blockout, código e cenas na engine
//! (Godot ou Erethea) e o run_test. Todo arquivo gerado ganha recibo de licença.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Deserialize;
use serde_json::{json, Value};

use crate::audio::{self, efeitos, musica};
use crate::engine::{self, OpcoesTeste};
use crate::erro::{Erro, Resultado};
use crate::externas::{Achado, Programa};
use crate::forja;
use crate::ignis;
use crate::projeto::{self, Projeto};
use crate::recibos::{self, NovoRecibo};
use crate::servico::Fornalha;
use crate::workers::{self, Instalacao, Worker};

const TEMPO_BLENDER: Duration = Duration::from_secs(900);
const TEMPO_PLACA: Duration = Duration::from_secs(1800);

/// Modelo de placa que o roteador escolheu para a função, se o worker dele estiver
/// instalado nesta máquina. Sem isso, quem chama usa a alternativa sem placa.
async fn modelo_de_placa(f: &Fornalha, p: &Projeto, funcao: &str, avisos: &mut Vec<String>) -> Option<(Worker, String, Instalacao)> {
    let ctx = f.contexto(Some(p)).await;
    let nivel = f.nivel_em_uso(Some(p)).await;
    let escolha = crate::licencas::escolher(&f.catalogo, funcao, nivel, &ctx).ok()?;
    let m = escolha.modelo?;
    let w = Worker::do_modelo(&m.id)?;
    match workers::instalacao(&f.paths, w) {
        Some(i) => Some((w, m.id, i)),
        None => {
            avisos.push(format!(
                "O roteador escolheu {} ({funcao}), mas ele ainda não está instalado nesta máquina (Máquina → Modelos de placa): usei a alternativa sem placa.",
                m.nome
            ));
            None
        }
    }
}

/// Penteados do pacote MakeHuman (CC0) que a bancada de cabelo sabe guiar.
pub const PENTEADOS: [&str; 11] =
    ["short01", "short02", "short03", "short04", "bob01", "bob02", "long01", "ponytail01", "braid01", "afro01", "nenhum"];

/// Estilos que o alfaiate da Fornalha sabe vestir (fc_roupa.py).
pub const ESTILOS_DE_ROUPA: [&str; 8] =
    ["campones", "mercenario", "soldado", "cavaleiro", "cavaleiro_placas", "templario", "nobre", "jaqueta"];

/// Idade em anos → o "idade" do MakeHuman (0,1875 = 11 anos, 0,5 = 25, 1 = 90).
fn idade_mh(anos: f64) -> f64 {
    let a = anos.clamp(11.0, 90.0);
    if a <= 25.0 {
        0.1875 + (a - 11.0) / 14.0 * (0.5 - 0.1875)
    } else {
        0.5 + (a - 25.0) / 65.0 * 0.5
    }
}

/// Os controles finos da IA por cima do que a ficha decidiu (cabelo, barba, idade, corpo, rosto, olhos).
fn aplicar_controles(h: &mut Value, ctl: &Value, feminino_pelo_texto: bool) {
    let feminino = match ctl["genero"].as_str() {
        Some(g) if g.starts_with('f') => true,
        Some(g) if g.starts_with('m') => false,
        _ => feminino_pelo_texto,
    };
    if ctl["genero"].is_string() {
        h["macro"]["genero"] = json!(if feminino { 0.0 } else { 1.0 });
        if ctl["cabelo"].is_null() && h["cabelo"] != "nenhum" {
            h["cabelo"] = json!(if feminino { "long01" } else { "short04" });
        }
    }
    if let Some(anos) = ctl["idade"].as_f64() {
        h["macro"]["idade"] = json!(idade_mh(anos));
    }
    if let Some(o) = ctl["corpo_humano"].as_object() {
        for chave in ["altura", "peso", "musculo", "proporcoes"] {
            if let Some(v) = o.get(chave).and_then(Value::as_f64) {
                h["macro"][chave] = json!(v.clamp(0.0, 1.0));
            }
        }
    }
    // penteado fora da lista do pacote não existe na bancada: fica o que a ficha escolheu
    let penteado = |p: &str| PENTEADOS.contains(&p).then(|| json!(p));
    match &ctl["cabelo"] {
        Value::String(p) => {
            if let Some(v) = penteado(p) {
                h["cabelo"] = v;
            }
        }
        Value::Object(o) => {
            if let Some(v) = o.get("penteado").and_then(Value::as_str).and_then(penteado) {
                h["cabelo"] = v;
            }
            if let Some(cor) = o.get("cor").and_then(Value::as_str) {
                h["cor_cabelo"] = json!(cor);
            }
            let estilo: serde_json::Map<String, Value> =
                o.iter().filter(|(k, _)| !matches!(k.as_str(), "penteado" | "cor")).map(|(k, v)| (k.clone(), v.clone())).collect();
            if !estilo.is_empty() {
                h["cabelo_estilo"] = Value::Object(estilo);
            }
        }
        _ => {}
    }
    match &ctl["barba"] {
        Value::String(t) => h["barba"] = json!(t),
        Value::Object(o) => {
            h["barba"] = json!(o.get("tipo").and_then(Value::as_str).unwrap_or("cheia"));
            if let Some(cor) = o.get("cor").and_then(Value::as_str) {
                h["cor_barba"] = json!(cor);
            }
            let estilo: serde_json::Map<String, Value> =
                o.iter().filter(|(k, _)| !matches!(k.as_str(), "tipo" | "cor")).map(|(k, v)| (k.clone(), v.clone())).collect();
            if !estilo.is_empty() {
                h["barba_estilo"] = Value::Object(estilo);
            }
        }
        _ => {}
    }
    if ctl["rosto"].is_object() {
        h["detalhes"] = ctl["rosto"].clone();
    }
    if ctl["pele"].is_object() {
        h["pele"] = ctl["pele"].clone();
    }
    if ctl["roupa"]["estilo"] == "manequim" {
        // manequim: o corpo sem roupa e com a pele inteira (nada apagado por baixo), para fazer a roupa
        // separada no corpo dele (create_garment) e vestir depois (dress_character)
        if let Some(o) = h.as_object_mut() {
            o.remove("roupa");
        }
        h["manequim"] = json!(true);
    } else if let Some(r) = ctl["roupa"].as_object() {
        if let Some(e) = r.get("estilo").and_then(Value::as_str).filter(|e| ESTILOS_DE_ROUPA.contains(e)) {
            h["roupa"]["estilo"] = json!(e);
        }
        if let Some(cores) = r.get("cores").and_then(Value::as_object) {
            for (k, v) in cores {
                h["roupa"]["cores"][k] = v.clone();
            }
        }
        if let Some(c) = r.get("capa").and_then(Value::as_bool) {
            h["roupa"]["capa"] = json!(c);
        }
    }
    for (de, para) in [("cor_olhos", "cor_olhos"), ("sobrancelha", "sobrancelha")] {
        if let Some(v) = ctl[de].as_str() {
            h[para] = json!(v);
        }
    }
}

/// Ficha do personagem → humano realista (MakeHuman + roupa medieval + arma).
fn humano_da_ficha(ficha: &Value, nivel: crate::niveis::Nivel) -> Value {
    let texto = format!(
        "{} {} {}",
        ficha["descricao"].as_str().unwrap_or(""),
        ficha["papel"].as_str().unwrap_or(""),
        ficha["nome"].as_str().unwrap_or("")
    )
    .to_lowercase();
    let tem = |ps: &[&str]| ps.iter().any(|p| texto.contains(p));
    let feminino = tem(&["mulher", "guerreira", "feminin", "rainha", "princesa", "bruxa", "feiticeira", "camponesa", "ferreira", "dama"]);
    let velho = tem(&["velho", "velha", "anci", "idos"]);
    let tipo = ficha["tipo"].as_str().unwrap_or("humano");
    let (musculo, peso) = match ficha["porte"].as_str().unwrap_or("medio") {
        "forte" => (0.85, 0.62),
        "magro" => (0.35, 0.35),
        _ => (0.6, 0.5),
    };
    let altura = match tipo {
        "anao" | "goblin" => 0.0,
        "orc" | "demonio" => 1.0,
        "elfo" => 0.8,
        _ => 0.55,
    };
    let zumbi = tipo == "zumbi";
    let pele = match tipo {
        "orc" => Some("#6f8f4e"),
        "goblin" => Some("#8fae5a"),
        "demonio" => Some("#8e3b32"),
        _ => None,
    }
    .map(String::from)
    .or_else(|| ficha["cor_pele"].as_str().map(String::from));
    let inimigo = ficha["inimigo"] == true;
    let armadura = ficha["armadura"].as_str().unwrap_or("leve");
    let estilo = if tem(&["rei", "rainha", "nobre", "príncipe", "principe", "princesa", "lorde", "duque"]) {
        "nobre"
    } else if tem(&["templ", "cruzad", "teutônic", "teutonic", "hospitalár", "hospitalar"]) {
        "templario"
    } else if armadura == "placas" || tem(&["armadura de placas", "armadura completa", "placas de aço", "full plate"]) {
        "cavaleiro_placas"
    } else if zumbi {
        // morto-vivo: a roupa de camponês de quando era vivo, encardida
        "campones"
    } else {
        match armadura {
            "pesada" => "cavaleiro",
            "nenhuma" => "campones",
            _ if inimigo => "mercenario",
            _ => "soldado",
        }
    };
    let pesado = matches!(estilo, "cavaleiro" | "templario" | "cavaleiro_placas");
    // atlas da armadura com o desgaste assado: maior no nível mais alto
    let textura = match nivel {
        crate::niveis::Nivel::Leve => 0,
        crate::niveis::Nivel::Equilibrado => 1024,
        _ => 2048,
    };
    // pele com poros e rugas (textura do corpo): 4K no máximo, 2K na qualidade
    let textura_pele = match nivel {
        crate::niveis::Nivel::Leve | crate::niveis::Nivel::Equilibrado => 0,
        crate::niveis::Nivel::Qualidade => 2048,
        crate::niveis::Nivel::Maximo => 4096,
    };
    let arma = ficha["arma"].as_str().unwrap_or("nenhuma");
    let mut h = json!({
        "id": ficha["id"],
        "macro": {"genero": if feminino { 0.0 } else { 1.0 }, "idade": if velho { 0.88 } else { 0.55 }, "musculo": musculo, "peso": peso,
                  "altura": altura, "proporcoes": 0.75},
        "tom_de_pele": pele,
        "cabelo": if pesado { "nenhum" } else if feminino { "long01" } else { "short04" },
        "cor_cabelo": ficha["cor_cabelo"],
        // caimento simulado (sobreveste franzida no cinto, capa caindo pelas costas) junto com a pele em alta
        "roupa": {"estilo": estilo, "capa": ficha["capa"].as_bool().unwrap_or(matches!(estilo, "cavaleiro" | "templario")), "pano": textura_pele > 0,
                  "cores": {"principal": ficha["cor_roupa"], "secundaria": ficha["cor_roupa_secundaria"], "detalhe": "#3d2a1c",
                            "emblema": if matches!(estilo, "cavaleiro" | "templario") && !inimigo { "cruz" } else { "nenhum" },
                            "textura": textura}},
        "arma": arma,
        "escudo": matches!(estilo, "cavaleiro" | "cavaleiro_placas") && arma == "espada",
        "textura_pele": textura_pele,
    });
    if zumbi {
        // pele de morto, olhos leitosos (sobre a íris cinza), barba por fazer e animações de zumbi
        h["zumbi"] = json!(true);
        h["cor_olhos"] = json!("grey");
        h["barba"] = json!("rala");
        h["tom_de_pele"] = json!("#c9b8a6");
        // linho encardido e calça escura (o pano escurece mais com o encardido e o sangue seco)
        if ficha["cor_roupa"].is_null() {
            h["roupa"]["cores"]["principal"] = json!("#a39a86");
            h["roupa"]["cores"]["secundaria"] = json!("#4a443a");
        }
    }
    // os controles da IA por último: o que ela pediu vale mais que o padrão do tipo
    aplicar_controles(&mut h, &ficha["controles"], feminino);
    h
}

/// Altura de cada tipo de personagem (a mesma da Forja), para pôr a malha de fora em escala.
fn altura_do_tipo(tipo: &str) -> f64 {
    match tipo {
        "elfo" => 1.85,
        "anao" => 1.35,
        "orc" => 1.95,
        "goblin" => 1.15,
        "demonio" => 2.0,
        "dragao" => 4.0,
        _ => 1.8,
    }
}

/// Trabalho pesado na placa fora do Ignis (ComfyUI, TRELLIS.2, UniRig, HY-Motion): pede ao Ignis para
/// soltar a memória de vídeo antes (um modelo por vez na placa, essencial numa RX 580 de 8 GB) e
/// devolve a placa no fim. Sem o Ignis aberto, só faz o trabalho.
pub(crate) async fn com_placa<T>(f: &Fornalha, mb: u64, minutos: u32, trabalho: impl std::future::Future<Output = T>) -> T {
    let porta = f.porta_ignis();
    let reservou = f.estado_ignis().await.conectado && ignis::reservar_placa(porta, mb, minutos).await.is_ok();
    let r = trabalho.await;
    if reservou {
        let _ = ignis::liberar_placa(porta).await;
    }
    r
}

/// TRELLIS.2 (imagem → malha alta com cor) e Blender (malha leve com textura assada).
#[allow(clippy::too_many_arguments)]
async fn trellis_e_assar(
    f: &Fornalha,
    inst: &Instalacao,
    modelo: &str,
    imagem: &Path,
    pasta: &Path,
    nome: &str,
    altura_m: f64,
    seed: u64,
    colisao: bool,
) -> Resultado<(PathBuf, Value)> {
    let alta = pasta.join(format!("{nome}.alta.ply"));
    let r = com_placa(
        f,
        16_000,
        30,
        workers::rodar(
            &f.paths,
            Worker::Trellis2,
            inst,
            &json!({"tarefa": "gerar", "imagem": imagem, "saida": alta, "modelo": modelo, "seed": seed}),
            TEMPO_PLACA,
        ),
    )
    .await?;
    let malha = pasta.join(format!("{nome}.malha.glb"));
    let a = forjar(
        f,
        &json!({"tarefa": "assar", "entrada": alta, "saida": malha, "nome": nome, "altura_m": altura_m, "triangulos_max": 20000,
                "textura_px": 2048, "cima": r["eixo_cima"].as_str().unwrap_or("Z"), "colisao": colisao, "previa": true, "amostras": 16}),
    )
    .await?;
    let _ = std::fs::remove_file(&alta);
    Ok((malha, json!({"trellis": r["estatisticas"], "assar": a["estatisticas"], "previa": a["arquivos"]["previa"]})))
}

pub(crate) fn rel(raiz: &Path, arq: &Path) -> String {
    arq.strip_prefix(raiz).unwrap_or(arq).to_string_lossy().replace('\\', "/")
}

/// Registra o recibo de um arquivo gerado.
#[allow(clippy::too_many_arguments)]
pub(crate) async fn recibo(
    f: &Fornalha,
    p: &Projeto,
    arq: &Path,
    modelo: &str,
    prompt: Option<String>,
    seed: Option<u64>,
    parametros: Value,
    quem: &str,
) -> Resultado<()> {
    let ctx = f.contexto(Some(p)).await;
    recibos::registrar(
        p,
        &f.catalogo,
        &ctx,
        NovoRecibo {
            arquivo: arq.to_string_lossy().into_owned(),
            modelo: modelo.into(),
            versao: Some(crate::consts::APP_VERSION.into()),
            prompt,
            referencias: vec![],
            seed,
            quem_pediu: Some(quem.into()),
            parametros: Some(parametros),
        },
    )?;
    Ok(())
}

async fn blender(f: &Fornalha) -> Resultado<Achado> {
    f.programa(Programa::Blender).await
}

pub(crate) async fn forjar(f: &Fornalha, tarefa: &Value) -> Resultado<Value> {
    let b = blender(f).await?;
    let mut t = tarefa.clone();
    // com o pacote de materiais (CC0), tudo sai em PBR e as prévias usam o céu HDRI
    if t.get("materiais").is_none() {
        if let Some(m) = crate::pacotes::materiais_da_forja(&f.paths) {
            t["materiais"] = m["materiais"].clone();
            t["ceu"] = m["ceu"].clone();
        }
    }
    forja::rodar(&b, &f.paths.data_dir, &t, TEMPO_BLENDER).await
}

fn paleta(p: &Projeto) -> Vec<String> {
    p.biblia.guia_visual.paleta.clone()
}

pub(crate) fn texto_do_projeto(p: &Projeto) -> String {
    let b = &p.biblia;
    let c = &b.conceito;
    let mut partes = vec![format!("Jogo: {}", b.nome)];
    for (rotulo, valor) in
        [("gênero", &c.genero), ("estilo", &c.estilo), ("câmera", &c.camera), ("ambientação", &c.ambientacao), ("história", &c.historia)]
    {
        if !valor.is_empty() {
            partes.push(format!("{rotulo}: {valor}"));
        }
    }
    if !b.guia_visual.texto_de_estilo.is_empty() {
        partes.push(format!("guia visual: {}", b.guia_visual.texto_de_estilo));
    }
    if !b.guia_visual.paleta.is_empty() {
        partes.push(format!("paleta: {}", b.guia_visual.paleta.join(", ")));
    }
    if !b.guia_visual.evitar.is_empty() {
        partes.push(format!("evitar: {}", b.guia_visual.evitar.join(", ")));
    }
    let nomes: Vec<&str> = b.personagens.iter().map(|x| x.nome.as_str()).collect();
    if !nomes.is_empty() {
        partes.push(format!("personagens que já existem: {}", nomes.join(", ")));
    }
    partes.join(". ")
}

// ---------------------------------------------------------------- ficha

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsPersonagem {
    pub projeto: Option<String>,
    pub nome: Option<String>,
    /// protagonista, aliado, inimigo, chefe...
    pub papel: Option<String>,
    pub descricao: Option<String>,
    pub tipo: Option<String>,
    pub arma: Option<String>,
    pub armadura: Option<String>,
    pub porte: Option<String>,
    pub cor_roupa: Option<String>,
    pub cor_roupa_secundaria: Option<String>,
    pub cor_pele: Option<String>,
    pub cor_cabelo: Option<String>,
    pub capa: Option<bool>,
    pub capuz: Option<bool>,
    /// Fala para dublar (Chatterbox pelo Ignis).
    pub fala: Option<String>,
    /// Gerar a imagem de conceito (padrão: sim, se o Ignis tiver imagem).
    pub conceito: Option<bool>,
    /// Folha de modelo (frente, perfil, costas). Padrão: só quando o 3D sai pela IA (ela guia a malha);
    /// no 3D da Forja ela não muda nada e custa minutos de placa.
    pub folha_de_modelo: Option<bool>,
    /// Vídeo curto das animações.
    pub video: Option<bool>,
    /// Montar na engine e rodar o teste depois (o pronto da Fase 4).
    pub testar_na_engine: Option<bool>,
    pub seed: Option<u64>,
    /// Por partes, com aceitar ou refazer: para depois do conceito de corpo inteiro (o que vira 3D) e
    /// devolve a imagem; a chamada seguinte com o mesmo nome usa esse conceito.
    pub parar_no_conceito: Option<bool>,
    /// Apaga o conceito de corpo inteiro guardado e faz outro (com outra semente).
    pub refazer_conceito: Option<bool>,
    /// Imagem pronta (feita em outro lugar, como o Gemini) que vira o 3D sem ser refeita.
    pub imagem: Option<String>,
    /// Tipo de corpo: auto (medido na malha), humanoide, alado, quadrupede, aranha, inseto, serpente,
    /// criatura. Decide o esqueleto e as animações.
    pub corpo: Option<String>,
    /// Controles finos do humano realista (para chegar perto de uma referência): penteado e estilo do
    /// cabelo, barba, idade em anos, gênero, corpo, rosto (alvos do MakeHuman), olhos e sobrancelha.
    pub cabelo: Option<Value>,
    pub barba: Option<Value>,
    pub idade: Option<f64>,
    pub genero: Option<String>,
    pub corpo_humano: Option<Value>,
    pub rosto: Option<Value>,
    pub cor_olhos: Option<String>,
    pub sobrancelha: Option<String>,
    /// Roupa: {estilo (campones, mercenario, soldado, cavaleiro, cavaleiro_placas, templario, nobre,
    /// jaqueta), cores {principal, secundaria, detalhe}, capa}.
    pub roupa: Option<Value>,
    /// Pele: {sardas, manchas, poros, rugas, bronzeado} de 0 a 1 (curtida de sol, envelhecida...).
    pub pele: Option<Value>,
    /// Golpes e defesa de quem luta com arma de mão: "luta" (padrão: captura real do ACCAD, quando
    /// instalado) ou "biblioteca" (os da biblioteca CC0, estilizados).
    pub golpes: Option<String>,
    /// Imagem de referência: no fim, o resultado sai lado a lado com ela (compare_reference).
    pub referencia: Option<String>,
}

fn eh_inimigo(papel: &str) -> bool {
    let p = papel.to_lowercase();
    ["inimigo", "chefe", "vilão", "vilao", "monstro", "boss", "capanga"].iter().any(|x| p.contains(x))
}

fn tipo_por_texto(t: &str) -> Option<&'static str> {
    let t = t.to_lowercase();
    [
        ("orc", "orc"),
        ("goblin", "goblin"),
        ("esquelet", "esqueleto"),
        ("morto-vivo", "zumbi"),
        ("zumbi", "zumbi"),
        ("zombie", "zumbi"),
        ("elf", "elfo"),
        ("anão", "anao"),
        ("anao", "anao"),
        ("demôn", "demonio"),
        ("demon", "demonio"),
        ("diabo", "demonio"),
    ]
    .iter()
    .find(|(k, _)| t.contains(k))
    .map(|(_, v)| *v)
}

fn arma_por_texto(t: &str) -> Option<&'static str> {
    let t = t.to_lowercase();
    forja::ARMAS.iter().find(|a| t.contains(*a)).copied().or_else(|| {
        if t.contains("lança") {
            Some("lanca")
        } else if t.contains("mago") || t.contains("feiticeir") || t.contains("bruxa") {
            Some("cajado")
        } else {
            None
        }
    })
}

fn cor_valida(c: &Option<String>) -> Option<String> {
    c.as_ref().filter(|s| s.len() == 7 && s.starts_with('#') && s[1..].chars().all(|x| x.is_ascii_hexdigit())).cloned()
}

/// Monta a ficha: o que veio no pedido + o cérebro do Ignis (se estiver ligado) + a paleta da bíblia.
async fn montar_ficha(f: &Fornalha, p: &Projeto, a: &ArgsPersonagem, avisos: &mut Vec<String>) -> Value {
    let papel = a.papel.clone().unwrap_or_else(|| "protagonista".into());
    let inimigo = eh_inimigo(&papel);
    let descricao = a.descricao.clone().unwrap_or_default();
    let mut cerebro = Value::Null;
    let cap = ignis::capacidades(f.porta_ignis()).await;
    if cap["conectado"] == true && cap["conversa"].as_array().is_some_and(|v| !v.is_empty()) {
        let esquema = json!({
            "type": "object", "additionalProperties": false,
            "properties": {
                "nome": {"type": "string"}, "descricao": {"type": "string"},
                "tipo": {"type": "string", "enum": forja::TIPOS_DE_PERSONAGEM},
                "arma": {"type": "string", "enum": forja::ARMAS},
                "armadura": {"type": "string", "enum": ["nenhuma", "leve", "pesada", "placas"]},
                "porte": {"type": "string", "enum": ["magro", "medio", "forte"]},
                "cor_roupa": {"type": "string"}, "cor_roupa_secundaria": {"type": "string"}, "cor_cabelo": {"type": "string"},
                "capa": {"type": "boolean"}, "capuz": {"type": "boolean"}, "fala": {"type": "string"}
            },
            "required": ["nome", "descricao", "tipo", "arma", "armadura", "porte", "cor_roupa", "cor_roupa_secundaria", "cor_cabelo", "capa", "capuz", "fala"]
        });
        let sistema = "Você é o diretor de arte de um estúdio de jogos. Crie a ficha de personagem pedida, coerente com o jogo. \
            Cores em #RRGGBB, de preferência da paleta do jogo. A fala é uma frase curta em português que o personagem diria. Responda só o JSON.";
        let pedido = format!(
            "{}.\nPersonagem pedido: papel {papel}{}{}.",
            texto_do_projeto(p),
            a.nome.as_ref().map(|n| format!(", nome {n}")).unwrap_or_default(),
            if descricao.is_empty() { String::new() } else { format!(", {descricao}") }
        );
        match ignis::conversar_json(f.porta_ignis(), None, sistema, &pedido, &esquema).await {
            Ok(v) => cerebro = v,
            Err(e) => avisos.push(format!("O cérebro (Ignis) não escreveu a ficha ({}); usei as regras da Fornalha.", e.mensagem)),
        }
    } else {
        avisos.push("O Ignis não está aberto (ou sem modelo de conversa): a ficha saiu das regras da Fornalha, sem o cérebro.".into());
    }
    let pal = paleta(p);
    let c = |chave: &str| cerebro[chave].as_str().map(String::from);
    let texto = format!("{papel} {descricao} {}", a.nome.clone().unwrap_or_default());
    let nome = a.nome.clone().or_else(|| c("nome")).filter(|n| !n.trim().is_empty()).unwrap_or_else(|| {
        if inimigo {
            "Inimigo".into()
        } else {
            "Herói".into()
        }
    });
    let tipo = a
        .tipo
        .clone()
        .filter(|t| forja::TIPOS_DE_PERSONAGEM.contains(&t.as_str()))
        .or_else(|| tipo_por_texto(&texto).map(String::from))
        .or_else(|| c("tipo").filter(|t| forja::TIPOS_DE_PERSONAGEM.contains(&t.as_str())))
        .unwrap_or_else(|| if inimigo { "orc".into() } else { "humano".into() });
    let arma = a
        .arma
        .clone()
        .filter(|x| forja::ARMAS.contains(&x.as_str()) || x == "nenhuma")
        .or_else(|| arma_por_texto(&texto).map(String::from))
        .or_else(|| c("arma").filter(|x| forja::ARMAS.contains(&x.as_str())))
        .unwrap_or_else(|| if inimigo { "martelo".into() } else { "espada".into() });
    let cor = |pedido: &Option<String>, chave: &str, i: usize, padrao: &str| -> String {
        cor_valida(pedido).or_else(|| cor_valida(&c(chave))).or_else(|| pal.get(i).cloned()).unwrap_or_else(|| padrao.into())
    };
    // sem nome (nem da pessoa nem do cérebro): o do tipo, com número se já houver um com esse nome
    // (antes todo inimigo sem nome virava "Inimigo" e o segundo apagava o primeiro)
    let sem_nome = a.nome.as_deref().is_none_or(|n| n.trim().is_empty()) && c("nome").is_none_or(|n| n.trim().is_empty());
    let nome = if sem_nome {
        let base = match tipo.as_str() {
            "humano" => nome,
            t => {
                let mut cs = t.chars();
                cs.next().map(|p| p.to_uppercase().collect::<String>() + cs.as_str()).unwrap_or(nome)
            }
        };
        let existe = |n: &str| {
            let id = projeto::nome_de_pasta(n);
            p.raiz.join("Enemies").join(&id).exists() || p.raiz.join("Characters").join(&id).exists()
        };
        (1..100).map(|i| if i == 1 { base.clone() } else { format!("{base} {i}") }).find(|n| !existe(n)).unwrap_or(base)
    } else {
        nome
    };
    let id = projeto::nome_de_pasta(&nome);
    json!({
        "id": id, "nome": nome, "papel": papel, "inimigo": inimigo,
        "descricao": if descricao.is_empty() { c("descricao").unwrap_or_default() } else { descricao },
        "tipo": tipo, "arma": arma,
        "armadura": a.armadura.clone().or_else(|| c("armadura")).unwrap_or_else(|| "leve".into()),
        "porte": a.porte.clone().or_else(|| c("porte")).unwrap_or_else(|| "medio".into()),
        "cor_roupa": cor(&a.cor_roupa, "cor_roupa", 1, if inimigo { "#4a3b2a" } else { "#7a2e22" }),
        "cor_roupa_secundaria": cor(&a.cor_roupa_secundaria, "cor_roupa_secundaria", 2, "#2f3640"),
        "cor_cabelo": cor(&a.cor_cabelo, "cor_cabelo", 99, "#2b1d14"),
        "cor_pele": cor_valida(&a.cor_pele),
        "capa": a.capa.or(cerebro["capa"].as_bool()).unwrap_or(!inimigo),
        "capuz": a.capuz.or(cerebro["capuz"].as_bool()).unwrap_or(false),
        "fala": a.fala.clone().or_else(|| c("fala")).unwrap_or_default(),
        "cerebro": if cerebro.is_null() { Value::Null } else { json!("ignis") },
        "controles": {
            "cabelo": a.cabelo, "barba": a.barba, "idade": a.idade, "genero": a.genero, "corpo_humano": a.corpo_humano,
            "rosto": a.rosto, "cor_olhos": a.cor_olhos, "sobrancelha": a.sobrancelha, "roupa": a.roupa, "pele": a.pele,
        },
    })
}

fn guardar_na_biblia(p: &Projeto, ficha: &Value) -> Resultado<()> {
    let mut lista: Vec<Value> = p.biblia.personagens.iter().map(|x| serde_json::to_value(x).unwrap_or(Value::Null)).collect();
    let id = ficha["id"].as_str().unwrap_or("");
    let novo = json!({
        "id": id, "nome": ficha["nome"], "papel": ficha["papel"], "roupa": format!("{} e {}", ficha["cor_roupa"].as_str().unwrap_or(""), ficha["cor_roupa_secundaria"].as_str().unwrap_or("")),
        "arma": ficha["arma"], "descricao": ficha["descricao"], "tipo": ficha["tipo"], "armadura": ficha["armadura"],
    });
    match lista.iter_mut().find(|x| x["id"] == id) {
        Some(x) => *x = novo,
        None => lista.push(novo),
    }
    projeto::atualizar(&p.raiz, &json!({"personagens": lista}))?;
    Ok(())
}

/// create_character: ficha → conceito → 3D com esqueleto e animações → voz → recibos (→ engine e teste).
pub async fn criar_personagem(f: &Fornalha, a: ArgsPersonagem, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let mut avisos: Vec<String> = Vec::new();
    let ficha = montar_ficha(f, &p, &a, &mut avisos).await;
    let id = ficha["id"].as_str().unwrap_or("personagem").to_string();
    let inimigo = ficha["inimigo"] == true;
    let pasta = p.raiz.join(if inimigo { "Enemies" } else { "Characters" }).join(&id);
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    guardar_na_biblia(&p, &ficha)?;
    let seed = a.seed.unwrap_or(7);
    let mut arquivos = serde_json::Map::new();

    // por partes na janela: primeiro o conceito de corpo inteiro (o que vira 3D), para aceitar ou refazer
    let img_3d = pasta.join("conceito_3d.png");
    if a.refazer_conceito.unwrap_or(false) {
        let _ = std::fs::remove_file(&img_3d);
    }
    if let Some(origem) = a.imagem.as_deref().map(PathBuf::from) {
        // a imagem que a pessoa trouxe é o conceito: não é refeita nem retocada
        if !origem.is_file() {
            return Err(Erro::novo("imagem_nao_existe", format!("A imagem {} não existe.", origem.display())));
        }
        let bytes = std::fs::read(&origem).map_err(|e| Erro::io(&origem, e))?;
        if !bytes.starts_with(&[0x89, b'P', b'N', b'G']) {
            return Err(Erro::novo("imagem_nao_png", "Mande a imagem em PNG (o 3D pela IA lê PNG)."));
        }
        std::fs::write(&img_3d, &bytes).map_err(|e| Erro::io(&img_3d, e))?;
        arquivos.insert("imagem_da_pessoa".into(), json!(origem));
    }
    if a.parar_no_conceito.unwrap_or(false) {
        if !img_3d.is_file() {
            gerar_imagem_conceito(f, &p, &descrever_para_3d(&p, &ficha), &img_3d, seed.wrapping_add(3), quem).await?;
        }
        arquivos.insert("conceito_3d".into(), json!(img_3d));
        return Ok(json!({"situacao": "conceito_pronto", "ficha": ficha, "arquivos": arquivos, "avisos": avisos,
                         "proximo": "chame de novo com o mesmo nome (sem parar_no_conceito) para fazer o 3D deste conceito, ou com refazer_conceito para outro"}));
    }

    // 3D pela IA de verdade (API ligada, ou ComfyUI com o TRELLIS.2 e o aceite do DINOv3): só então
    // a folha de modelo e o conceito de corpo inteiro para a malha valem as imagens. O motor de imagem
    // pelo Vulkan (RX 580 e outras AMD/Intel) gera imagem, não malha: lá o 3D é da Forja.
    let ia_3d = pode_3d_pela_ia(f).await;
    // conceito (imagem pelo Ignis)
    if a.conceito.unwrap_or(true) {
        match gerar_imagem_conceito(f, &p, &descrever_para_imagem(&p, &ficha), &pasta.join("conceito.png"), seed, quem).await {
            Ok(arq) => {
                arquivos.insert("conceito".into(), json!(arq));
            }
            Err(e) => avisos.push(format!("Conceito sem imagem: {}", e.mensagem)),
        }
        if a.folha_de_modelo.unwrap_or(ia_3d) {
            match gerar_folha_de_modelo(f, &p, &ficha, &pasta.join("folha_de_modelo.png"), seed, quem).await {
                Ok(Some(arq)) => {
                    arquivos.insert("folha_de_modelo".into(), json!(arq));
                }
                Ok(None) => {}
                Err(e) => avisos.push(format!("Folha de modelo sem imagem: {}", e.mensagem)),
            }
        }
    }

    // 3D: com placa NVIDIA e o TRELLIS.2 instalado e liberado, sai da imagem de conceito
    // (malha com textura assada no Blender + esqueleto padrão); senão, a Forja monta pela ficha.
    let nivel = f.nivel_em_uso(Some(&p)).await;
    let glb = pasta.join(format!("{id}.glb"));
    let parametros = json!({"tipo": ficha["tipo"], "arma": ficha["arma"], "armadura": ficha["armadura"], "nivel": nivel.id()});
    let mut modelo_3d = "forja-3d".to_string();
    let mut r = Value::Null;
    let conceito = arquivos.get("conceito").and_then(|v| v.as_str()).map(PathBuf::from);
    // criaturas (dragão…) têm esqueleto próprio: saem da Forja de criaturas, não do humano nem do TRELLIS.2
    // esqueleto pelo tipo de corpo: o pedido manda; com imagem pronta e sem pedido, mede na malha
    let corpo = a.corpo.clone().unwrap_or_else(|| if a.imagem.is_some() { "auto".into() } else { String::new() });
    let esqueleto = match corpo.as_str() {
        "humanoide" => "jogo",
        "alado" | "dragao" => "dragao",
        "quadrupede" | "aranha" | "inseto" | "serpente" | "criatura" | "monstro" => "criatura",
        "auto" => "auto",
        _ if ficha["tipo"] == "dragao" => "dragao",
        _ => "jogo",
    };
    let criatura = esqueleto != "jogo";
    // 3D pela IA no ComfyUI (TRELLIS.2) ou numa API ligada: conceito próprio de corpo inteiro → malha →
    // esqueleto (de jogo com a captura de movimento e a arma na mão; no dragão, o do dragão da Fornalha)
    if ficha["tipo"] != "esqueleto" && a.conceito.unwrap_or(true) && ia_3d {
        let img = img_3d.clone();
        let pronto =
            img.is_file() || gerar_imagem_conceito(f, &p, &descrever_para_3d(&p, &ficha), &img, seed.wrapping_add(3), quem).await.is_ok();
        let alta = pasta.join(format!("{id}_ia_alta.glb"));
        if pronto {
            if let Some(info) = malha_pela_ia(f, &img, &alta, &id, seed, nivel == crate::niveis::Nivel::Maximo, &mut avisos).await {
                let base = crate::pacotes::para_a_forja(&f.paths).unwrap_or(json!({}));
                // quatro vistas (Qualidade e Máximo, 3D local): a textura borrada do processador fica nítida e
                // fiel ao conceito (frente pelo conceito, lados e costas refinados pelo Z-Image, rosto em close)
                let mut alta = alta.clone();
                let mut vistas = Value::Null;
                if info["modelo"] == "trellis2-comfyui" && matches!(nivel, crate::niveis::Nivel::Qualidade | crate::niveis::Nivel::Maximo) {
                    let com_vistas = pasta.join(format!("{id}_ia_vistas.glb"));
                    let porta = porta_com_motor_de_imagem(f).await;
                    let descricao = descrever_para_3d(&p, &ficha);
                    match blender(f).await {
                        Ok(b) => match crate::vistas::refinar_textura(
                            &b,
                            &f.paths.data_dir,
                            porta,
                            &alta,
                            Some(&img),
                            &descricao,
                            &pasta.join(format!("{id}_vistas")),
                            seed,
                            &com_vistas,
                            crate::vistas::lado_da_textura(nivel == crate::niveis::Nivel::Maximo),
                            None,
                        )
                        .await
                        {
                            Ok(v) => {
                                avisos.extend(v["avisos"].as_array().into_iter().flatten().filter_map(|a| a.as_str().map(String::from)));
                                vistas = v;
                                alta = com_vistas;
                            }
                            Err(e) => avisos.push(format!("As quatro vistas não saíram ({}): ficou a textura da IA.", e.mensagem)),
                        },
                        Err(e) => avisos.push(format!("Sem o Blender para as quatro vistas ({}).", e.mensagem)),
                    }
                }
                // por partes (Qualidade e Máximo): a cabeça recortada do conceito, refinada em close e
                // feita malha própria, entra no lugar da cabeça do corpo
                // só com placa (CUDA/ROCm): no processador do CI a cabeça em close passou de 6 h só na
                // textura (a grade fica cheia), fora as 3,4 h do corpo
                let no_processador = info["processador"].as_bool().unwrap_or(false);
                let cabeca = if !criatura
                    && !no_processador
                    && info["modelo"] == "trellis2-comfyui"
                    && matches!(nivel, crate::niveis::Nivel::Qualidade | crate::niveis::Nivel::Maximo)
                {
                    let descricao = format!("{} ({})", ficha["descricao"].as_str().unwrap_or(""), ficha["armadura"].as_str().unwrap_or(""));
                    match std::fs::read(&img) {
                        Ok(b) => match com_placa(
                            f,
                            12_000,
                            360,
                            crate::partes::cabeca_no_comfyui(
                                f.porta_comfyui(),
                                &b,
                                &descricao,
                                &pasta.join(format!("{id}_cabeca")),
                                seed,
                                8 * 3600,
                            ),
                        )
                        .await
                        {
                            Ok(v) => v,
                            Err(e) => {
                                avisos.push(format!("A cabeça por partes não saiu ({}): ficou a cabeça da malha do corpo.", e.mensagem));
                                Value::Null
                            }
                        },
                        Err(_) => Value::Null,
                    }
                } else {
                    Value::Null
                };
                let tarefa = if criatura {
                    // dragão: a altura conta as asas abertas; criatura de patas: pela ficha
                    let altura = if esqueleto == "dragao" { altura_do_tipo("dragao") * 1.25 } else { 2.2 };
                    json!({"tarefa": "rig", "entrada": alta, "saida": glb, "nome": id,
                               "altura_m": altura, "triangulos_max": 80000, "esqueleto": esqueleto,
                               "makehuman": base["makehuman"], "animacoes_de": base["animacoes_de"],
                               "materiais": base["materiais"], "ceu": base["ceu"], "folha": true, "video": a.video.unwrap_or(false),
                               "video_animacoes": ["voar", "rugir", "andar", "correr", "atacar"], "amostras": 20, "conceito": img})
                } else {
                    json!({"tarefa": "rig", "entrada": alta, "saida": glb, "nome": id,
                               "altura_m": altura_do_tipo(ficha["tipo"].as_str().unwrap_or("")), "triangulos_max": 60000,
                               "esqueleto": "jogo", "makehuman": base["makehuman"], "animacoes_de": base["animacoes_de"], "materiais": base["materiais"],
                               "ceu": base["ceu"], "arma": ficha["arma"], "escudo": ficha["escudo"].as_bool().unwrap_or(false),
                               "cabeca": cabeca, "folha": true, "video": a.video.unwrap_or(false), "amostras": 20, "conceito": img})
                };
                match forjar(f, &tarefa).await {
                    Ok(mut rr) => {
                        modelo_3d = info["modelo"].as_str().unwrap_or("trellis2-comfyui").to_string();
                        rr["ia"] = info;
                        rr["vistas"] = vistas;
                        arquivos.insert("conceito_3d".into(), json!(img));
                        r = rr;
                    }
                    Err(e) => avisos.push(format!("O esqueleto na malha da IA falhou ({}): segui pelo caminho seguinte.", e.mensagem)),
                }
            }
        }
    }
    // sem o 3D pela IA, o dragão sai da Forja de criaturas (esqueleto e malha procedurais)
    if r.is_null() && criatura && esqueleto != "dragao" {
        return Err(Erro::novo(
            "criatura_sem_3d_pela_ia",
            "Criatura de qualquer corpo sai pelo 3D pela IA (imagem → malha → esqueleto medido): instale o 3D pela IA em \
             Máquina → Motor de imagem (com o aceite do DINOv3) ou ligue uma API de 3D.",
        ));
    }
    if r.is_null() && esqueleto == "dragao" {
        let cores = json!({"principal": ficha["cor_pele"].as_str().or(ficha["cor_roupa"].as_str()),
                           "secundaria": ficha["cor_roupa_secundaria"]});
        let tarefa = json!({"tarefa": "criatura", "saida": glb, "folha": true, "video": a.video.unwrap_or(false), "amostras": 20,
                            "criatura": {"id": id, "tipo": "dragao", "altura": altura_do_tipo("dragao"), "cores": cores}});
        let mut base = crate::pacotes::materiais_da_forja(&f.paths).unwrap_or(json!({}));
        if let (Some(b), Some(t)) = (base.as_object_mut(), tarefa.as_object()) {
            b.extend(t.clone());
        }
        r = forjar(f, &base).await?;
        modelo_3d = "forja-criatura".into();
    }
    // TRELLIS.2 como worker próprio (NVIDIA), a partir da imagem de conceito
    if !r.is_null() || criatura {
        // já saiu (criatura ou 3D pela IA)
    } else if let Some(img) = conceito.filter(|c| c.is_file()) {
        if let Some((Worker::Trellis2, modelo, inst)) = modelo_de_placa(f, &p, "3d", &mut avisos).await {
            let altura = altura_do_tipo(ficha["tipo"].as_str().unwrap_or(""));
            match trellis_e_assar(f, &inst, &modelo, &img, &pasta, &id, altura, seed, false).await {
                Ok((malha, info)) => {
                    let rig = forjar(
                        f,
                        &json!({"tarefa": "rig", "entrada": malha, "saida": glb, "nome": id, "altura_m": altura, "triangulos_max": 20000,
                                "folha": true, "video": a.video.unwrap_or(false), "amostras": 20}),
                    )
                    .await;
                    match rig {
                        Ok(mut rr) => {
                            let _ = std::fs::remove_file(&malha);
                            rr["placa"] = info;
                            modelo_3d = modelo;
                            r = rr;
                        }
                        Err(e) => avisos.push(format!("O esqueleto na malha do TRELLIS.2 falhou ({}): usei a Forja.", e.mensagem)),
                    }
                }
                Err(e) => avisos.push(format!("O TRELLIS.2 não conseguiu ({}): usei a Forja da Fornalha.", e.mensagem)),
            }
        }
    } else if let Some(m) = crate::licencas::escolher(&f.catalogo, "3d", nivel, &f.contexto(Some(&p)).await).ok().and_then(|e| e.modelo) {
        if Worker::do_modelo(&m.id) == Some(Worker::Trellis2) {
            avisos.push("O TRELLIS.2 faz o 3D a partir da imagem de conceito, que não saiu: usei a Forja da Fornalha.".into());
        }
    }
    if r.is_null() && ficha["tipo"] != "esqueleto" && !criatura {
        // humano realista: MakeHuman (CC0) + roupas e armaduras PBR + animações de captura
        if let Some(base) = crate::pacotes::para_a_forja(&f.paths) {
            let mut tarefa = base;
            tarefa["tarefa"] = json!("humano");
            tarefa["saida"] = json!(glb);
            tarefa["folha"] = json!(true);
            tarefa["video"] = json!(a.video.unwrap_or(false));
            tarefa["amostras"] = json!(24);
            tarefa["humano"] = humano_da_ficha(&ficha, nivel);
            match forjar(f, &tarefa).await {
                Ok(rr) => {
                    modelo_3d = "humano-fornalha".into();
                    r = rr;
                }
                Err(e) => avisos.push(format!("O humano realista falhou ({}): usei a Forja simples.", e.mensagem)),
            }
        } else {
            avisos.push("Sem os pacotes de conteúdo (Máquina → Pacotes), o personagem sai da Forja simples. Baixe o MakeHuman, as animações e os materiais para o nível realista.".into());
        }
    }
    if r.is_null() {
        let tarefa = json!({"tarefa": "personagem", "saida": glb, "folha": true, "video": a.video.unwrap_or(false), "amostras": 20, "personagem": ficha});
        r = forjar(f, &tarefa).await?;
    }
    std::fs::write(pasta.join(format!("{id}.forja.json")), serde_json::to_vec_pretty(&r).unwrap_or_default()).ok();
    for (chave, arq) in r["arquivos"].as_object().cloned().unwrap_or_default() {
        if let Some(s) = arq.as_str() {
            recibo(f, &p, Path::new(s), &modelo_3d, ficha["descricao"].as_str().map(String::from), Some(seed), parametros.clone(), quem)
                .await?;
            arquivos.insert(chave, json!(s));
        }
    }
    let golpes = golpes_de_luta(f, &p, &glb, ficha["arma"].as_str().unwrap_or(""), &r, a.golpes.as_deref(), quem, &mut avisos).await;

    // com referência: o resultado lado a lado com ela (cores e proporção medidas) para a IA ajustar
    let mut comparacao = Value::Null;
    if let Some(referencia) = a.referencia.as_deref() {
        match comparar_referencia(
            f,
            ArgsComparar {
                projeto: Some(p.raiz.to_string_lossy().into_owned()),
                referencia: referencia.into(),
                arquivo: glb.to_string_lossy().into_owned(),
                vista: None,
                enquadramento: None,
            },
        )
        .await
        {
            Ok(c) => comparacao = c,
            Err(e) => avisos.push(format!("A comparação com a referência falhou: {}", e.mensagem)),
        }
    }

    // voz (Chatterbox pelo Ignis) + boca
    let fala = ficha["fala"].as_str().unwrap_or("").to_string();
    if !fala.is_empty() {
        match gerar_fala(f, &p, &id, &fala, "pt", seed, quem).await {
            Ok(v) => {
                arquivos.insert("voz".into(), v["arquivo"].clone());
                arquivos.insert("boca".into(), v["boca"].clone());
            }
            Err(e) => avisos.push(format!("Fala sem dublagem: {}", e.mensagem)),
        }
    }
    f.avisar_ponte(arquivos.values().filter_map(|v| v.as_str()).map(|s| rel(&p.raiz, Path::new(s))).collect());

    let mut resposta = json!({
        "comparacao": comparacao,
        "ficha": ficha, "pasta": pasta, "arquivos": arquivos, "estatisticas": r["estatisticas"], "segundos_blender": r["segundos"],
        "modelo_3d": modelo_3d, "golpes": golpes, "avisos": avisos,
    });
    if a.testar_na_engine.unwrap_or(false) {
        garantir_mundo_e_sons(f, &p, quem).await?;
        let montado =
            importar_na_engine(f, ArgsEngine { projeto: a.projeto.clone(), jogador: None, inimigo_perto: Some(inimigo) }, quem).await?;
        let teste = rodar_teste(f, ArgsTeste { projeto: a.projeto.clone(), segundos: None, video: Some(true) }).await?;
        resposta["engine"] = montado;
        resposta["teste"] = teste;
    }
    Ok(resposta)
}

/// O estilo das imagens: o texto do guia visual; sem ele, o estilo do projeto (conceito.estilo, ex.
/// "realista"); sem nenhum, o `padrao`. Antes caía sempre em "estilizada", mesmo em projeto realista.
fn estilo_das_imagens(p: &Projeto, padrao: &str) -> String {
    let g = p.biblia.guia_visual.texto_de_estilo.trim();
    if !g.is_empty() {
        return g.to_string();
    }
    let e = p.biblia.conceito.estilo.trim();
    if e.is_empty() {
        return padrao.to_string();
    }
    let baixo = e.to_lowercase();
    if baixo.contains("realis") {
        format!("arte de jogo 3D realista ({e}), materiais realistas, iluminação natural")
    } else {
        format!("arte de jogo 3D, estilo {e}")
    }
}

fn paleta_no_prompt(p: &Projeto) -> String {
    let pal = paleta(p);
    if pal.is_empty() {
        String::new()
    } else {
        format!(" Paleta: {}.", pal.join(", "))
    }
}

fn descrever_para_imagem(p: &Projeto, ficha: &Value) -> String {
    let estilo = estilo_das_imagens(p, "arte de jogo 3D");
    let evitar = p.biblia.guia_visual.evitar.join(", ");
    format!(
        "{estilo}. Personagem de corpo inteiro, de frente, em pé, fundo neutro claro. {} ({}), {}. Roupa nas cores {} e {}. Arma: {}. Armadura {}.{}",
        ficha["nome"].as_str().unwrap_or(""),
        ficha["tipo"].as_str().unwrap_or(""),
        ficha["descricao"].as_str().unwrap_or(""),
        ficha["cor_roupa"].as_str().unwrap_or(""),
        ficha["cor_roupa_secundaria"].as_str().unwrap_or(""),
        ficha["arma"].as_str().unwrap_or(""),
        ficha["armadura"].as_str().unwrap_or(""),
        if evitar.is_empty() { String::new() } else { format!(" Sem: {evitar}.") }
    )
}

/// Conceito para o 3D pela IA: corpo inteiro de frente, fundo liso, braços um pouco afastados e mãos
/// livres (a arma sai como peça própria e vai para a mão no esqueleto).
fn descrever_para_3d(p: &Projeto, ficha: &Value) -> String {
    let estilo = estilo_das_imagens(p, "realista, muito detalhado, personagem de jogo AAA");
    if ficha["tipo"] == "dragao" {
        return format!(
            "{estilo}. Corpo inteiro de um dragão em pé no chão, asas abertas, cauda longa apoiada no chão, cabeça com chifres \
             e a boca fechada, escamas detalhadas, vista de três quartos de frente, fundo cinza claro liso, luz suave e \
             uniforme. {}: {}. Cores {} e {}.",
            ficha["nome"].as_str().unwrap_or(""),
            ficha["descricao"].as_str().unwrap_or(""),
            ficha["cor_pele"].as_str().or(ficha["cor_roupa"].as_str()).unwrap_or(""),
            ficha["cor_roupa_secundaria"].as_str().unwrap_or(""),
        );
    }
    format!(
        "{estilo}. Foto de corpo inteiro de frente, em pé e reto, braços relaxados um pouco afastados do corpo, mãos \
         abertas e vazias, fundo cinza claro liso, luz suave e uniforme. {} ({}): {}. Roupa nas cores {} e {}. Armadura {}.",
        ficha["nome"].as_str().unwrap_or(""),
        ficha["tipo"].as_str().unwrap_or(""),
        ficha["descricao"].as_str().unwrap_or(""),
        ficha["cor_roupa"].as_str().unwrap_or(""),
        ficha["cor_roupa_secundaria"].as_str().unwrap_or(""),
        ficha["armadura"].as_str().unwrap_or(""),
    )
}

/// 3D pela IA: com o TRELLIS.2 instalado no ComfyUI (e o aceite do DINOv3), a imagem vira malha
/// texturizada. Devolve o .glb da malha alta, ou None se o caminho não está disponível.
/// O 3D pela IA pode rodar aqui? API de 3D ligada, ou ComfyUI de verdade (não só o motor de imagem
/// pelo Vulkan) com o aceite do DINOv3 dado pela pessoa.
async fn pode_3d_pela_ia(f: &Fornalha) -> bool {
    if crate::apis::ligada_3d(&f.paths).is_some() {
        return true;
    }
    if !f.estudio().licencas_aceitas.iter().any(|a| a == "meta-dinov3") {
        return false;
    }
    (crate::comfyui::instalacao(&f.paths).is_some() && crate::comfyui::motor_vulkan(&f.paths).is_none())
        || crate::comfyui::instalacao_3d(&f.paths).is_some()
        || crate::comfyui::consultar(f.porta_comfyui()).await.conectado
}

/// O ComfyUI aberto que tem o Z-Image (o do 3D no processador ou o principal), para o refino das vistas.
async fn porta_com_motor_de_imagem(f: &Fornalha) -> Option<u16> {
    for porta in [crate::comfyui::porta_3d(f.porta_comfyui()), f.porta_comfyui()] {
        if crate::comfyui::modelo_de_imagem(porta).await.is_some() {
            return Some(porta);
        }
    }
    None
}

/// `completo` (nível Máximo): no processador, o fluxo inteiro do TRELLIS.2 (uma noite) em vez do reduzido.
async fn malha_pela_ia(
    f: &Fornalha,
    imagem: &Path,
    destino: &Path,
    nome: &str,
    seed: u64,
    completo: bool,
    avisos: &mut Vec<String>,
) -> Option<Value> {
    // 1º a API paga, se a pessoa ligou (minutos em vez de horas)
    if let Some(p) = crate::apis::ligada_3d(&f.paths) {
        match crate::apis::gerar_3d(&f.paths, p, imagem, destino, &json!({"triangulos": 60000})).await {
            Ok(mut r) => {
                r["modelo"] = json!(p.modelo);
                return Some(r);
            }
            Err(e) => avisos.push(format!("A API ({}) não gerou ({}): tentei o 3D local.", p.nome, e.mensagem)),
        }
    }
    if !f.estudio().licencas_aceitas.iter().any(|a| a == "meta-dinov3") {
        return None; // o 3D pela IA usa o DINOv3: só com o aceite da pessoa (Licenças)
    }
    // o ComfyUI principal (NVIDIA, ROCm ou processador); nas máquinas do motor Vulkan (RX 580), o ComfyUI
    // do 3D no processador, instalado à parte
    let mut porta = f.porta_comfyui();
    let mut e = crate::comfyui::consultar(porta).await;
    if !e.conectado && crate::comfyui::instalacao(&f.paths).is_some() && crate::comfyui::motor_vulkan(&f.paths).is_none() {
        e = crate::comfyui::abrir(&f.paths, porta).await.ok()?;
    }
    if !e.conectado && crate::comfyui::instalacao_3d(&f.paths).is_some() {
        porta = crate::comfyui::porta_3d(f.porta_comfyui());
        e = crate::comfyui::abrir_3d(&f.paths, f.porta_comfyui()).await.ok()?;
    }
    if !e.conectado {
        return None;
    }
    let difusao = crate::comfyui::modelos(porta, "diffusion_models").await;
    if !difusao.iter().any(|m| m.contains("trellis_2")) {
        return None;
    }
    let png = std::fs::read(imagem).ok()?;
    // no processador leva horas (2,5 h no CI de 4 núcleos no fluxo reduzido; o inteiro, uma noite); numa
    // NVIDIA, minutos
    let limite = if completo { 14 * 3600 } else { 8 * 3600 };
    match com_placa(f, 12_000, 360, crate::comfyui::gerar_3d(porta, png, &format!("{nome}_conceito_3d.png"), seed, limite, completo)).await
    {
        Ok((glb, info)) => {
            std::fs::write(destino, &glb).ok()?;
            Some(info)
        }
        Err(e) => {
            avisos.push(format!("O 3D pela IA não saiu ({}): usei o caminho seguinte.", e.mensagem));
            None
        }
    }
}

/// Folha de modelo (frente, perfil e costas) para guiar a malha: pose A com os braços afastados do
/// tronco, pernas um pouco abertas, dedos separados, simetria e proporções reais (plano 1.2).
fn descrever_folha(p: &Projeto, ficha: &Value) -> String {
    let estilo = estilo_das_imagens(p, "arte de jogo 3D");
    let criatura = ficha["tipo"] == "dragao";
    let pose = if criatura {
        "vista de frente, vista de lado e vista de trás do mesmo corpo, asas abertas, de pé nas quatro patas"
    } else {
        "vista de frente, vista de perfil e vista de costas do mesmo personagem, corpo inteiro, pose A com os braços afastados do \
         tronco, pernas levemente separadas, mãos abertas com os dedos separados, simétrico, proporções reais"
    };
    format!(
        "{estilo}. Folha de modelo de personagem de jogo (model sheet), {pose}, fundo cinza neutro liso, iluminação uniforme, sem \
         sombras fortes, o mesmo design nas três vistas. {} ({}): {}. Roupa nas cores {} e {}.",
        ficha["nome"].as_str().unwrap_or(""),
        ficha["tipo"].as_str().unwrap_or(""),
        ficha["descricao"].as_str().unwrap_or(""),
        ficha["cor_roupa"].as_str().unwrap_or(""),
        ficha["cor_roupa_secundaria"].as_str().unwrap_or(""),
    )
}

/// A folha de modelo sai do motor de imagem local (larga, três vistas). Só com placa: no processador
/// uma imagem larga leva tempo demais para o dia a dia (o Teste de Fogo e o nível Máximo pedem mesmo assim).
pub async fn gerar_folha_de_modelo(
    f: &Fornalha,
    p: &Projeto,
    ficha: &Value,
    destino: &Path,
    seed: u64,
    quem: &str,
) -> Resultado<Option<String>> {
    let Some(motor) = motor_de_imagem(f, false).await else { return Ok(None) };
    let nivel = f.nivel_em_uso(Some(p)).await;
    if motor.so_processador() && nivel != crate::niveis::Nivel::Maximo {
        return Ok(None);
    }
    let (largura, altura) = if motor.so_processador() { (768, 320) } else { (1536, 640) };
    let prompt = descrever_folha(p, ficha);
    let (png, modelo, info) = motor.gerar(f, &prompt, largura, altura, seed.wrapping_add(17), 40).await?;
    if let Some(d) = destino.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    std::fs::write(destino, &png).map_err(|e| Erro::io(destino, e))?;
    let mut info = info;
    info["folha_de_modelo"] = json!(true);
    recibo(f, p, destino, modelo, Some(prompt), Some(seed.wrapping_add(17)), info, quem).await?;
    Ok(Some(destino.to_string_lossy().into_owned()))
}

/// O motor de imagem local pronto agora: o ComfyUI (aberto, ou instalado pela Fornalha e aberto na
/// hora se `abrir`) ou o motor Vulkan (stable-diffusion.cpp, chamado na hora).
enum MotorImagem {
    Comfy(crate::comfyui::ModeloImagem, crate::comfyui::EstadoComfy),
    Vulkan(crate::comfyui::MotorVulkan, Vec<String>),
}

impl MotorImagem {
    fn so_processador(&self) -> bool {
        match self {
            MotorImagem::Comfy(_, e) => e.dispositivos.iter().all(|d| d["tipo"] == "cpu"),
            MotorImagem::Vulkan(_, d) => crate::comfyui::so_processador(d),
        }
    }

    /// Gera com a placa reservada no Ignis (um modelo por vez na VRAM). Devolve PNG, id do modelo
    /// (manifesto) e os parâmetros para o recibo.
    async fn gerar(
        &self,
        f: &Fornalha,
        prompt: &str,
        largura: u32,
        altura: u32,
        seed: u64,
        minutos: u32,
    ) -> Resultado<(Vec<u8>, &'static str, Value)> {
        match self {
            MotorImagem::Comfy(m, e) => {
                let mb = if m.difusao_gguf { 7_000 } else { 15_000 };
                let (png, info) =
                    com_placa(f, mb, minutos, crate::comfyui::gerar_imagem(f.porta_comfyui(), prompt, largura, altura, seed, 8)).await?;
                Ok((png, m.id, json!({"comfyui": info, "dispositivos": e.dispositivos})))
            }
            MotorImagem::Vulkan(m, d) => {
                // sem memória de vídeo (outro programa segurando a placa, como o Ignis reabrindo): espera,
                // reserva de novo e tenta outra vez; na última, em 768 px. As tentativas vão no recibo.
                let mut tentativas = Vec::new();
                let mut lado = (largura, altura);
                for k in 0..3 {
                    if k > 0 {
                        tokio::time::sleep(std::time::Duration::from_secs(20)).await;
                    }
                    if k == 2 {
                        lado = ((largura * 3 / 4).max(512), (altura * 3 / 4).max(512));
                    }
                    match com_placa(f, 7_000, minutos, crate::comfyui::gerar_imagem_vulkan(m, prompt, lado.0, lado.1, seed, 8)).await {
                        Ok((png, info)) => {
                            return Ok((
                                png,
                                m.id(),
                                json!({"vulkan": info, "dispositivos": d, "tentativas_antes": tentativas, "lado": lado.0}),
                            ))
                        }
                        Err(e) if falta_memoria_de_video(&e.mensagem) && k < 2 => tentativas.push(e.mensagem.clone()),
                        Err(e) => return Err(e),
                    }
                }
                Err(Erro::novo("sem_memoria_de_video", "a placa ficou sem memória de vídeo três vezes seguidas"))
            }
        }
    }
}

/// O motor de imagem caiu por falta de memória de vídeo (Vulkan: ErrorOutOfDeviceMemory)?
fn falta_memoria_de_video(msg: &str) -> bool {
    let m = msg.to_lowercase();
    m.contains("outofdevicememory") || m.contains("out of device memory") || m.contains("out_of_device_memory")
}

async fn motor_de_imagem(f: &Fornalha, abrir: bool) -> Option<MotorImagem> {
    let mut comfy = crate::comfyui::consultar(f.porta_comfyui()).await;
    if !comfy.conectado {
        if let Some(m) = crate::comfyui::motor_vulkan(&f.paths) {
            let d = crate::comfyui::dispositivos_vulkan(&m).await;
            return Some(MotorImagem::Vulkan(m, d));
        }
        if abrir && crate::comfyui::instalacao(&f.paths).is_some() {
            // instalado pela Fornalha e fechado: abre sozinho
            comfy = crate::comfyui::abrir(&f.paths, f.porta_comfyui()).await.ok()?;
        }
    }
    if !comfy.conectado {
        return None;
    }
    let m = crate::comfyui::modelo_de_imagem(f.porta_comfyui()).await?;
    Some(MotorImagem::Comfy(m, comfy))
}

/// generate_concept: imagem avulsa com o guia visual junto.
pub async fn conceito_avulso(f: &Fornalha, p: &Projeto, descricao: &str, destino: &Path, seed: u64, quem: &str) -> Resultado<Value> {
    let estilo = estilo_das_imagens(p, "arte de jogo 3D");
    // pedido de personagem (não de cena): um só, de corpo inteiro (o "templário medieval" saía com seis
    // cavaleiros em volta de uma mesa)
    let baixo = descricao.to_lowercase();
    let cena = [
        "cena",
        "paisagem",
        "cenário",
        "cenario",
        "castelo",
        "vila",
        "cidade",
        "mapa",
        "floresta",
        "interior",
        "grupo",
        "exército",
        "exercito",
        "batalha",
        "taverna",
        "masmorra",
        "ambiente",
        "sala",
        "ruína",
        "ruina",
    ]
    .iter()
    .any(|k| baixo.contains(k));
    let sujeito = if cena { String::new() } else { " Um único personagem, de corpo inteiro, de frente, fundo neutro.".to_string() };
    let prompt = format!("{estilo}. {descricao}.{sujeito}{}", paleta_no_prompt(p));
    let arq = gerar_imagem_conceito(f, p, &prompt, destino, seed, quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, destino)]);
    Ok(json!({"arquivo": arq, "prompt": prompt}))
}

async fn gerar_imagem_conceito(f: &Fornalha, p: &Projeto, prompt: &str, destino: &Path, seed: u64, quem: &str) -> Resultado<String> {
    let sem_placa = f.deteccao(false).await.principal().is_none();
    // 1º o motor local (ComfyUI na NVIDIA, AMD com ROCm ou processador; Vulkan nas outras placas,
    // inclusive a RX 580), 2º o Ignis
    let (png, modelo, parametros) = if let Some(motor) = motor_de_imagem(f, true).await {
        let lado = if sem_placa || motor.so_processador() { 512 } else { 1024 };
        motor.gerar(f, prompt, lado, lado, seed, 30).await?
    } else {
        let cap = ignis::capacidades(f.porta_ignis()).await;
        if cap["imagem"].as_array().is_none_or(|v| v.is_empty()) {
            return Err(Erro::novo(
                "sem_gerador_de_imagem",
                "nem o motor de imagem local (ComfyUI ou Vulkan, com o Z-Image Turbo) nem o Ignis (com a imagem \
                 preparada) estão prontos. Instale o motor em Máquina → ComfyUI ou abra o Ignis → Imagem.",
            ));
        }
        let (tamanho, passos) = if sem_placa { ("384x384", 6) } else { ("1024x1024", 8) };
        let (png, info) = ignis::gerar_imagem(f.porta_ignis(), prompt, tamanho, seed, passos).await?;
        (png, "z-image-turbo-ignis", json!({"tamanho": tamanho, "passos": passos, "ignis": info}))
    };
    if let Some(d) = destino.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    std::fs::write(destino, &png).map_err(|e| Erro::io(destino, e))?;
    recibo(f, p, destino, modelo, Some(prompt.into()), Some(seed), parametros, quem).await?;
    Ok(destino.to_string_lossy().into_owned())
}

async fn gerar_fala(f: &Fornalha, p: &Projeto, id: &str, texto: &str, idioma: &str, seed: u64, quem: &str) -> Resultado<Value> {
    let bruto = ignis::falar(f.porta_ignis(), texto, idioma, seed).await?;
    // o WAV do Ignis vem com o cabeçalho de stream; reescrito para a engine importar sem travar
    let wav = audio::normalizar_wav(&bruto).ok_or_else(|| Erro::novo("ignis_recusou", "a voz não veio em WAV de 16 bits"))?;
    let pasta = p.raiz.join("Audio/dublagem");
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    let mut n = 1;
    while pasta.join(format!("{id}_{n:02}.wav")).exists() {
        n += 1;
    }
    let arq = pasta.join(format!("{id}_{n:02}.wav"));
    std::fs::write(&arq, &wav).map_err(|e| Erro::io(&arq, e))?;
    let (taxa, amostras) = audio::ler_wav_16(&wav).ok_or_else(|| Erro::novo("ignis_recusou", "a voz não veio em WAV"))?;
    let boca = audio::curva_da_boca(taxa, &amostras, 30);
    let arq_boca = arq.with_extension("boca.json");
    crate::paths::write_json(&arq_boca, &json!({"personagem": id, "texto": texto, "quadros_por_segundo": 30, "abertura": boca}))
        .map_err(|e| Erro::io(&arq_boca, e))?;
    recibo(f, p, &arq, "chatterbox-ptbr", Some(texto.into()), Some(seed), json!({"idioma": idioma}), quem).await?;
    Ok(json!({"arquivo": arq, "boca": arq_boca, "segundos": amostras.len() as f64 / taxa as f64}))
}

// ---------------------------------------------------------------- 3D avulso

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct Args3d {
    pub projeto: Option<String>,
    /// arma, objeto ou personagem
    pub tipo: String,
    /// espada, machado... (arma) / barril, caixa... (objeto)
    pub modelo: Option<String>,
    pub nome: Option<String>,
    pub cores: Option<Value>,
    pub seed: Option<u64>,
    /// Malha de fora para limpar (escala real, pivô, decimar, UV, colisão).
    pub entrada: Option<String>,
    pub altura_m: Option<f64>,
    pub triangulos_max: Option<u64>,
    /// Imagem (do projeto) para virar 3D com o TRELLIS.2 (placa NVIDIA).
    pub imagem: Option<String>,
    /// Montagem livre: a forma descrita peça por peça (caixa, cilindro, esfera, torno, extrusao, tubo).
    pub pecas: Option<Vec<Value>>,
    /// Materiais das peças: {"lamina": {"cor": "#c9ced4", "tipo": "metal", "rugosidade": 0.25}}.
    pub materiais: Option<Value>,
    /// Imagem de referência: no fim, a comparação lado a lado (compare_reference) vem junto.
    pub referencia: Option<String>,
    pub vista: Option<String>,
    /// Qualquer item do jogo descrito em texto ("baú de madeira com ferragens de ferro", "casa de pedra de
    /// dois andares"): vira a imagem de conceito (motor de imagem) e dela o 3D pela IA, como `imagem`.
    pub pedido: Option<String>,
    /// Quatro vistas na textura (padrão: sim nos níveis Qualidade e Máximo, no 3D local).
    pub vistas: Option<bool>,
}

/// O pedido da imagem de conceito de um item do jogo: um só objeto, inteiro, de frente (a frente do conceito
/// vira a textura da frente nas quatro vistas), no fundo de estúdio que o 3D pela IA separa bem.
pub fn descrever_item(p: &Projeto, tipo: &str, pedido: &str) -> String {
    let estilo = estilo_das_imagens(p, "realista, muito detalhado, asset de jogo AAA");
    let o_que = match tipo {
        "arma" => "Uma arma só, inteira, de pé e reta, vista de frente",
        _ => "Um objeto só, inteiro, apoiado no chão, vista de frente e reto",
    };
    format!(
        "{estilo}. {o_que}, centralizado, sem pessoas, sem texto, sem moldura, fundo cinza claro liso, luz suave e uniforme, \
         sombra leve embaixo. {}",
        pedido.trim()
    )
}

/// Tamanho padrão do item quando a IA não diz (m): arma de mão ~1 m, construção ~6 m, objeto ~1 m.
fn altura_padrao_do_item(tipo: &str, texto: &str) -> f64 {
    let t = texto.to_lowercase();
    if tipo == "arma" {
        return 1.0;
    }
    if ["casa", "construção", "construcao", "torre", "templo", "igreja", "castelo", "moinho", "ponte", "muralha", "cabana"]
        .iter()
        .any(|k| t.contains(k))
    {
        return 6.0;
    }
    if ["árvore", "arvore"].iter().any(|k| t.contains(k)) {
        return 5.0;
    }
    1.0
}

/// Qualquer item do jogo pela IA de 3D (arma, escudo, baú, barril, móvel, casa, pedra, árvore, construção):
/// da imagem dada ou do conceito feito pelo `pedido`. O 3D sai pela placa NVIDIA (TRELLIS.2 no worker),
/// senão pela API paga ligada, senão pelo TRELLIS.2 no processador (o caminho grátis: no Máximo, o fluxo
/// inteiro); depois as quatro vistas (Qualidade e Máximo) e a limpeza (tamanho real, pivô no chão, menos
/// triângulos, UV e colisão).
async fn gerar_3d_da_imagem(f: &Fornalha, p: &Projeto, a: &Args3d, imagem: &str, quem: &str) -> Resultado<Value> {
    let nome = projeto::nome_de_pasta(a.nome.as_deref().or(a.modelo.as_deref()).unwrap_or("modelo"));
    let pasta = p.raiz.join(if a.tipo == "arma" { "Weapons" } else { "Items" });
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    let seed = a.seed.unwrap_or(1);
    let mut avisos = Vec::new();
    let img = if imagem.trim().is_empty() {
        // sem imagem: o conceito pelo pedido
        let pedido = a.pedido.clone().unwrap_or_default();
        let destino = pasta.join(format!("{nome}_conceito.png"));
        gerar_imagem_conceito(f, p, &descrever_item(p, &a.tipo, &pedido), &destino, seed, quem).await?;
        destino
    } else {
        f.resolver_no_projeto(p, imagem)
    };
    if !img.is_file() {
        return Err(Erro::argumento(format!("A imagem {} não existe.", img.display())));
    }
    let texto = format!("{} {}", a.pedido.as_deref().unwrap_or(""), nome);
    let altura = a.altura_m.unwrap_or_else(|| altura_padrao_do_item(&a.tipo, &texto));
    let Some((Worker::Trellis2, modelo, inst)) = modelo_de_placa(f, p, "3d", &mut avisos).await else {
        return item_sem_placa(f, p, a, &img, &pasta, &nome, altura, seed, avisos, quem).await;
    };
    let (malha, info) = trellis_e_assar(f, &inst, &modelo, &img, &pasta, &nome, altura, seed, true).await?;
    let saida = pasta.join(format!("{nome}.glb"));
    std::fs::rename(&malha, &saida).map_err(|e| Erro::io(&saida, e))?;
    let mut arquivos = serde_json::Map::new();
    arquivos.insert("modelo".into(), json!(saida));
    if let Some(prev) = info["previa"].as_str() {
        let destino = pasta.join(format!("{nome}.previa.png"));
        if std::fs::rename(prev, &destino).is_ok() {
            arquivos.insert("previa".into(), json!(destino));
        }
    }
    for arq in arquivos.values().filter_map(|v| v.as_str()) {
        recibo(f, p, Path::new(arq), &modelo, None, Some(seed), json!({"imagem": imagem, "textura": "assada no Blender"}), quem).await?;
    }
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    Ok(json!({"arquivos": arquivos, "estatisticas": info, "modelo": modelo, "avisos": avisos}))
}

/// O item pela IA sem placa NVIDIA: a API paga (se ligada) ou o TRELLIS.2 no processador, as quatro
/// vistas e a limpeza.
#[allow(clippy::too_many_arguments)]
async fn item_sem_placa(
    f: &Fornalha,
    p: &Projeto,
    a: &Args3d,
    img: &Path,
    pasta: &Path,
    nome: &str,
    altura: f64,
    seed: u64,
    mut avisos: Vec<String>,
    quem: &str,
) -> Resultado<Value> {
    let nivel = f.nivel_em_uso(Some(p)).await;
    let maximo = nivel == crate::niveis::Nivel::Maximo;
    let alta = pasta.join(format!("{nome}_ia_alta.glb"));
    let Some(info) = malha_pela_ia(f, img, &alta, nome, seed, maximo, &mut avisos).await else {
        return Err(Erro::novo(
            "sem_modelo_de_imagem_para_3d",
            format!(
                "Não há 3D pela IA disponível aqui para o item: sem placa NVIDIA, sem API de 3D ligada e sem o 3D pela IA no \
                 processador (Máquina → Motor de imagem → Instalar o 3D pela IA, com o aceite do DINOv3 em Licenças). Sem \
                 isso, a IA monta o item por peças (pecas) olhando a imagem. {}",
                avisos.join(" ")
            ),
        ));
    };
    let modelo = info["modelo"].as_str().unwrap_or("trellis2-comfyui").to_string();
    // quatro vistas: a textura borrada do processador fica nítida e fiel ao conceito
    let mut entrada = alta.clone();
    let mut vistas = Value::Null;
    let quer_vistas = a.vistas.unwrap_or(matches!(nivel, crate::niveis::Nivel::Qualidade | crate::niveis::Nivel::Maximo));
    if quer_vistas && modelo == "trellis2-comfyui" {
        let com_vistas = pasta.join(format!("{nome}_ia_vistas.glb"));
        let descricao = a.pedido.clone().unwrap_or_else(|| nome.replace(['_', '-'], " "));
        match blender(f).await {
            Ok(b) => match crate::vistas::refinar_textura_de(
                &b,
                &f.paths.data_dir,
                porta_com_motor_de_imagem(f).await,
                &alta,
                Some(img),
                &descricao,
                &pasta.join(format!("{nome}_vistas")),
                seed,
                &com_vistas,
                crate::vistas::lado_da_textura(maximo),
                None,
                crate::vistas::Assunto::Objeto,
            )
            .await
            {
                Ok(v) => {
                    avisos.extend(v["avisos"].as_array().into_iter().flatten().filter_map(|x| x.as_str().map(String::from)));
                    vistas = v;
                    entrada = com_vistas;
                }
                Err(e) => avisos.push(format!("As quatro vistas não saíram ({}): ficou a textura da IA.", e.mensagem)),
            },
            Err(e) => avisos.push(format!("Sem o Blender para as quatro vistas ({}).", e.mensagem)),
        }
    }
    let saida = pasta.join(format!("{nome}.glb"));
    let triangulos = a.triangulos_max.unwrap_or(if maximo { 40_000 } else { 20_000 });
    let r = forjar(
        f,
        &json!({"tarefa": "limpar", "entrada": entrada, "saida": saida, "nome": nome, "altura_m": altura,
                "triangulos_max": triangulos, "colisao": true, "previa": true, "amostras": 16}),
    )
    .await?;
    let mut arquivos = r["arquivos"].as_object().cloned().unwrap_or_default();
    arquivos.insert("conceito".into(), json!(img));
    for arq in arquivos.values().filter_map(|v| v.as_str()) {
        let arq = Path::new(arq);
        if arq.starts_with(&p.raiz) && arq.extension().is_some_and(|e| e == "glb" || e == "png") {
            recibo(f, p, arq, &modelo, None, Some(seed), json!({"imagem": img, "vistas": !vistas.is_null()}), quem).await?;
        }
    }
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    let mut resposta = json!({"arquivos": arquivos, "estatisticas": r["estatisticas"], "modelo": modelo, "ia": info,
                              "vistas": vistas, "avisos": avisos});
    if let Some(refe) = a.referencia.clone().filter(|s| !s.trim().is_empty()) {
        let c = comparar_referencia(
            f,
            ArgsComparar {
                projeto: a.projeto.clone(),
                referencia: refe,
                arquivo: saida.to_string_lossy().into_owned(),
                vista: a.vista.clone(),
                enquadramento: Some("corpo".into()),
            },
        )
        .await;
        resposta["comparacao"] = c.unwrap_or_else(|e| json!({"erro": e.to_string()}));
    }
    Ok(resposta)
}

pub async fn gerar_3d(f: &Fornalha, a: Args3d, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    if let Some(img) = a.imagem.clone().filter(|s| !s.trim().is_empty()) {
        return gerar_3d_da_imagem(f, &p, &a, &img, quem).await;
    }
    // pelo pedido em texto (sem peças nem malha de fora): o conceito e o 3D pela IA
    if a.pedido.as_deref().is_some_and(|s| !s.trim().is_empty()) && a.pecas.as_ref().is_none_or(|v| v.is_empty()) && a.entrada.is_none() {
        return gerar_3d_da_imagem(f, &p, &a, "", quem).await;
    }
    let seed = a.seed.unwrap_or(1);
    let (tarefa, pasta, nome) = if let Some(entrada) = &a.entrada {
        let nome = projeto::nome_de_pasta(a.nome.as_deref().unwrap_or("modelo"));
        let pasta = p.raiz.join("Items");
        (
            json!({"tarefa": "limpar", "entrada": f.resolver_no_projeto(&p, entrada), "nome": nome, "altura_m": a.altura_m, "triangulos_max": a.triangulos_max}),
            pasta,
            nome,
        )
    } else if let Some(pecas) = a.pecas.clone().filter(|p| !p.is_empty()) {
        // montagem livre: a IA descreve a forma da referência peça por peça
        let nome = projeto::nome_de_pasta(a.nome.as_deref().or(a.modelo.as_deref()).unwrap_or("modelo"));
        let mut materiais = a.materiais.clone().unwrap_or_else(|| json!({}));
        if materiais.as_object().is_none_or(|m| m.is_empty()) {
            // sem materiais: as cores da paleta do guia visual, em ordem (coerência com o resto do jogo)
            let pal = paleta(&p);
            materiais = json!({"principal": {"cor": pal.first().cloned().unwrap_or_else(|| "#8a8580".into())}});
        }
        let spec = json!({"id": nome, "pecas": pecas, "materiais": materiais});
        match a.tipo.as_str() {
            "arma" => (json!({"tarefa": "arma", "arma": spec}), p.raiz.join("Weapons"), nome),
            "objeto" => (json!({"tarefa": "objeto", "objeto": spec}), p.raiz.join("Items"), nome),
            outro => {
                return Err(Erro::argumento(format!(
                    "Montagem por peças: tipo \"{outro}\" não existe. Use arma ou objeto (casa, móvel, prop)."
                )))
            }
        }
    } else {
        match a.tipo.as_str() {
            "arma" => {
                let modelo = a.modelo.clone().unwrap_or_else(|| "espada".into());
                if !forja::ARMAS.contains(&modelo.as_str()) {
                    return Err(Erro::argumento(format!("Arma \"{modelo}\" não existe. Use: {}.", forja::ARMAS.join(", "))));
                }
                let nome = projeto::nome_de_pasta(a.nome.as_deref().unwrap_or(&modelo));
                let mut arma = json!({"tipo": modelo, "id": nome});
                mesclar_cores(&mut arma, &a.cores, &paleta(&p));
                (json!({"tarefa": "arma", "arma": arma}), p.raiz.join("Weapons"), nome)
            }
            "objeto" => {
                let modelo = a.modelo.clone().unwrap_or_else(|| "barril".into());
                if !forja::OBJETOS.contains(&modelo.as_str()) {
                    return Err(Erro::argumento(format!("Objeto \"{modelo}\" não existe. Use: {}.", forja::OBJETOS.join(", "))));
                }
                let nome = projeto::nome_de_pasta(a.nome.as_deref().unwrap_or(&modelo));
                let mut obj = json!({"tipo": modelo, "id": nome, "seed": seed});
                mesclar_cores(&mut obj, &a.cores, &paleta(&p));
                (json!({"tarefa": "objeto", "objeto": obj}), p.raiz.join("Items"), nome)
            }
            "personagem" | "inimigo" => {
                return Err(Erro::argumento(
                    "Para personagem e inimigo use create_character (faz ficha, conceito, 3D, esqueleto, animações e voz).",
                ));
            }
            outro => return Err(Erro::argumento(format!("Tipo \"{outro}\" não existe. Use arma, objeto (ou create_character)."))),
        }
    };
    let saida = pasta.join(format!("{nome}.glb"));
    let mut t = tarefa;
    t["saida"] = json!(saida);
    t["amostras"] = json!(18);
    let r = forjar(f, &t).await?;
    let mut arquivos = serde_json::Map::new();
    let modelo_recibo = "forja-3d";
    for (chave, arq) in r["arquivos"].as_object().cloned().unwrap_or_default() {
        if let Some(s) = arq.as_str() {
            recibo(f, &p, Path::new(s), modelo_recibo, None, Some(seed), json!({"tipo": a.tipo, "modelo": a.modelo}), quem).await?;
            arquivos.insert(chave, json!(s));
        }
    }
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    let mut resposta = json!({"arquivos": arquivos, "estatisticas": r["estatisticas"], "segundos": r["segundos"]});
    if r["avisos"].as_array().is_some_and(|v| !v.is_empty()) {
        resposta["avisos"] = r["avisos"].clone();
    }
    if let Some(refe) = a.referencia.clone().filter(|s| !s.trim().is_empty()) {
        // o ciclo da referência: o lado a lado já vem junto para a IA olhar e ajustar as peças
        let c = comparar_referencia(
            f,
            ArgsComparar {
                projeto: a.projeto.clone(),
                referencia: refe,
                arquivo: saida.to_string_lossy().into_owned(),
                vista: a.vista.clone(),
                enquadramento: Some("corpo".into()),
            },
        )
        .await;
        resposta["comparacao"] = c.unwrap_or_else(|e| json!({"erro": e.to_string()}));
    }
    Ok(resposta)
}

fn mesclar_cores(alvo: &mut Value, cores: &Option<Value>, paleta: &[String]) {
    if let Some(m) = cores.as_ref().and_then(|c| c.as_object()) {
        for (k, v) in m {
            alvo[format!("cor_{}", k.trim_start_matches("cor_"))] = v.clone();
        }
    } else if !paleta.is_empty() {
        alvo["cor_detalhe"] = json!(paleta[0]);
    }
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsEsqueleto {
    pub projeto: Option<String>,
    pub entrada: String,
    pub nome: Option<String>,
    pub altura_m: Option<f64>,
    pub girar_graus: Option<f64>,
    pub animacoes: Option<Vec<String>>,
    pub inimigo: Option<bool>,
    /// Criatura que não é humanoide (bicho, monstro de quatro patas...): esqueleto pelo UniRig.
    pub criatura: Option<bool>,
    /// Arma na mão (espada, machado...) no esqueleto de jogo.
    pub arma: Option<String>,
    /// Imagem de conceito da malha (acerta a cor do metal e do pano pela imagem).
    pub conceito: Option<String>,
    /// Vídeo do movimento (andar, correr, atacar) junto.
    pub video: Option<bool>,
    /// true: o esqueleto simples de antes (23 ossos, malha reduzida a 20 mil triângulos).
    pub simples: Option<bool>,
    /// "luta" (padrão) ou "biblioteca": de onde vêm os golpes e a defesa (veja create_character).
    pub golpes: Option<String>,
}

/// create_skeleton: malha de fora (TRELLIS.2, Hunyuan3D, feita à mão) ganha o esqueleto padrão e animações.
/// Criatura que não é humanoide ganha o esqueleto do UniRig (placa NVIDIA), sem as animações da biblioteca.
pub async fn criar_esqueleto(f: &Fornalha, a: ArgsEsqueleto, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let nome = projeto::nome_de_pasta(a.nome.as_deref().unwrap_or("personagem"));
    let pasta = p.raiz.join(if a.inimigo.unwrap_or(false) { "Enemies" } else { "Characters" }).join(&nome);
    let saida = pasta.join(format!("{nome}.glb"));
    let mut avisos = Vec::new();
    if a.criatura.unwrap_or(false) {
        if let Some((Worker::UniRig, modelo, inst)) = modelo_de_placa(f, &p, "rig", &mut avisos).await {
            std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
            // a malha vai limpa (escala, pivô, triângulos) para o UniRig
            let limpa = pasta.join(format!("{nome}.limpa.glb"));
            forjar(
                f,
                &json!({"tarefa": "limpar", "entrada": f.resolver_no_projeto(&p, &a.entrada), "saida": limpa, "nome": nome,
                        "altura_m": a.altura_m, "girar_graus": a.girar_graus, "triangulos_max": 20000, "colisao": false, "previa": false}),
            )
            .await?;
            match com_placa(
                f,
                12_000,
                20,
                workers::rodar(
                    &f.paths,
                    Worker::UniRig,
                    &inst,
                    &json!({"entrada": limpa, "saida": saida, "pasta_temporaria": f.paths.data_dir.join("tmp").join(format!("unirig_{nome}"))}),
                    TEMPO_PLACA,
                ),
            )
            .await
            {
                Ok(r) => {
                    let _ = std::fs::remove_file(&limpa);
                    recibo(f, &p, &saida, &modelo, None, None, json!({"entrada": a.entrada, "criatura": true}), quem).await?;
                    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
                    return Ok(json!({"arquivos": {"modelo": saida}, "estatisticas": r["estatisticas"], "modelo": modelo,
                        "avisos": ["Esqueleto do UniRig: as animações da biblioteca são do esqueleto humanoide; anime a criatura na engine ou no Blender."]}));
                }
                Err(e) => avisos.push(format!("O UniRig não conseguiu ({}): usei o esqueleto padrão (humanoide).", e.mensagem)),
            }
        } else {
            avisos
                .push("Criatura sem o UniRig (precisa de placa NVIDIA e do worker instalado): usei o esqueleto padrão (humanoide).".into());
        }
    }
    // humanoide com os pacotes instalados: o caminho de jogo (o manequim do MakeHuman encaixado dentro
    // da malha como molde: o mesmo esqueleto com dedos, pesos e captura de movimento do humano, com a
    // conferência e a correção do movimento e a arma na mão). Sem os pacotes, o esqueleto simples.
    let base = crate::pacotes::para_a_forja(&f.paths).unwrap_or(json!({}));
    let de_jogo = !a.simples.unwrap_or(false) && base["makehuman"].is_object() && !base["animacoes_de"].is_null();
    let tarefa = if de_jogo {
        json!({"tarefa": "rig", "entrada": f.resolver_no_projeto(&p, &a.entrada), "saida": saida, "nome": nome,
               "altura_m": a.altura_m.unwrap_or(1.8), "girar_graus": a.girar_graus, "animacoes": a.animacoes, "triangulos_max": 60000,
               "esqueleto": "jogo", "makehuman": base["makehuman"], "animacoes_de": base["animacoes_de"], "materiais": base["materiais"],
               "ceu": base["ceu"], "arma": a.arma.clone().unwrap_or_else(|| "nenhuma".into()), "folha": true, "video": a.video.unwrap_or(false),
               "amostras": 20, "conceito": a.conceito.as_deref().map(|c| f.resolver_no_projeto(&p, c))})
    } else {
        if !a.simples.unwrap_or(false) {
            avisos.push(
                "Sem os pacotes MakeHuman e de animações: usei o esqueleto simples (baixe em Máquina → Pacotes para o de jogo).".into(),
            );
        }
        json!({"tarefa": "rig", "entrada": f.resolver_no_projeto(&p, &a.entrada), "saida": saida, "nome": nome, "altura_m": a.altura_m.unwrap_or(1.8),
               "girar_graus": a.girar_graus, "animacoes": a.animacoes, "triangulos_max": 20000})
    };
    let r = forjar(f, &tarefa).await?;
    std::fs::write(pasta.join(format!("{nome}.forja.json")), serde_json::to_vec_pretty(&r).unwrap_or_default()).ok();
    let modelo = if de_jogo { "forja-3d" } else { "rigify-blender" };
    for arq in r["arquivos"].as_object().cloned().unwrap_or_default().values().filter_map(|v| v.as_str()) {
        recibo(f, &p, Path::new(arq), modelo, None, None, json!({"entrada": a.entrada}), quem).await?;
    }
    let golpes = if de_jogo {
        golpes_de_luta(f, &p, &saida, a.arma.as_deref().unwrap_or(""), &r, a.golpes.as_deref(), quem, &mut avisos).await
    } else {
        None
    };
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    Ok(
        json!({"arquivos": r["arquivos"], "estatisticas": r["estatisticas"], "modelo": modelo, "esqueleto": if de_jogo { "jogo" } else { "simples" },
              "movimento": r["estatisticas"]["movimento"], "golpes": golpes, "avisos": avisos}),
    )
}

/// Golpes e defesa de quem luta com arma de mão, de captura real (ACCAD, CC BY 3.0): gancho vira corte
/// na horizontal, uppercut vira corte subindo, cruzado vira estocada e o bloqueio alto vira aparar com a
/// espada, tudo na base de luta (peso nos pés). Os de espada da biblioteca CC0 são estilizados (braços
/// abertos, estocada quase sentada e a defesa de braços abertos): no templário pareciam errados.
const GOLPES_DE_LUTA: [(&str, &str); 4] = [
    ("accad:Male2_E6_HookRight.bvh:Male2_E6_HookRight", "atacar"),
    ("accad:Male2_E8_UppercutRight.bvh:Male2_E8_UppercutRight", "atacar_2"),
    ("accad:Male2_E4_CrossRight.bvh:Male2_E4_CrossRight", "atacar_3"),
    ("accad:Male2_E13_BlockRightHigh.bvh:Male2_E13_BlockRightHigh", "defender"),
];

#[allow(clippy::too_many_arguments)]
async fn golpes_de_luta(
    f: &Fornalha,
    p: &Projeto,
    glb: &Path,
    arma: &str,
    r: &Value,
    pedido: Option<&str>,
    quem: &str,
    avisos: &mut Vec<String>,
) -> Option<Value> {
    if pedido == Some("biblioteca") || !matches!(arma, "espada" | "machado" | "martelo" | "adaga") || !glb.is_file() {
        return None;
    }
    // só no esqueleto de jogo (o da Forja simples não recebe captura)
    if r["estatisticas"]["ossos"].as_u64().unwrap_or(0) < 50 {
        return None;
    }
    if !crate::movimento::fontes(f, Some(p)).iter().any(|x| x.id == "accad") {
        avisos.push(
            "Golpes e defesa da biblioteca CC0 (estilizados). Com o pacote ACCAD (Máquina → Pacotes), saem de captura real: corte, estocada e aparar com a arma.".into(),
        );
        return None;
    }
    let clipes = GOLPES_DE_LUTA
        .iter()
        .map(|(id, como)| crate::movimento::Clipe {
            id: (*id).into(),
            como: (*como).into(),
            no_lugar: Some(true),
            golpe: Some(true),
            velocidade: Some(1.15),
            ..Default::default()
        })
        .collect();
    let args = crate::movimento::ArgsAplicar {
        projeto: Some(p.raiz.to_string_lossy().into_owned()),
        arquivo: glb.to_string_lossy().into_owned(),
        clipes,
        corrigir: Some(true),
        video: None,
    };
    match crate::movimento::aplicar(f, args, quem).await {
        Ok(v) => Some(json!({"fonte": "ACCAD Open Motion Project (CC BY 3.0)", "aprovado": v["aprovado"],
                             "animacoes": GOLPES_DE_LUTA.iter().map(|(_, c)| *c).collect::<Vec<_>>(), "creditos": v["creditos"]})),
        Err(e) => {
            avisos.push(format!("Golpes de captura (ACCAD) não entraram ({}): ficaram os da biblioteca.", e.mensagem));
            None
        }
    }
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsAnimacao {
    pub projeto: Option<String>,
    /// Personagem com o esqueleto padrão (glb).
    pub arquivo: String,
    /// Origem das animações (retarget) — outro personagem com o esqueleto padrão.
    pub origem: Option<String>,
    pub animacoes: Option<Vec<String>>,
    /// Movimento descrito em texto ("acena com a mão direita"): HY-Motion (placa NVIDIA + aceite da Tencent).
    pub descricao: Option<String>,
    /// Nome da animação nova (com descricao).
    pub nome_animacao: Option<String>,
    pub segundos: Option<f64>,
    pub laco: Option<bool>,
    pub seed: Option<u64>,
}

/// Movimento por texto: HY-Motion no worker e o Blender aplica no esqueleto padrão.
async fn animar_por_texto(f: &Fornalha, p: &Projeto, a: &ArgsAnimacao, descricao: &str, quem: &str) -> Resultado<Value> {
    let arquivo = f.resolver_no_projeto(p, &a.arquivo);
    let mut avisos = Vec::new();
    let Some((Worker::HyMotion, modelo, inst)) = modelo_de_placa(f, p, "animacao", &mut avisos).await else {
        let motivo = avisos.pop().unwrap_or_else(|| {
            "o roteador não liberou o HY-Motion aqui (precisa de placa NVIDIA e do aceite da licença da Tencent na janela)".into()
        });
        return Err(Erro::novo(
            "sem_modelo_de_movimento",
            format!(
                "Movimento por texto precisa do HY-Motion: {motivo}. Sem ele, use as animações da biblioteca: {}.",
                forja::ANIMACOES.join(", ")
            ),
        ));
    };
    let nome = projeto::nome_de_pasta(a.nome_animacao.as_deref().unwrap_or("movimento")).replace('-', "_");
    let tmp = f.paths.data_dir.join("tmp").join(format!("hymotion_{}", crate::util::id_aleatorio(6)));
    let mov = tmp.join("movimento.json");
    let r = com_placa(
        f,
        16_000,
        20,
        workers::rodar(
            &f.paths,
            Worker::HyMotion,
            &inst,
            &json!({"texto": descricao, "segundos": a.segundos.unwrap_or(4.0), "saida": mov, "modelo": modelo, "seed": a.seed.unwrap_or(1), "pasta_temporaria": tmp}),
            TEMPO_PLACA,
        ),
    )
    .await?;
    let b = forjar(
        f,
        &json!({"tarefa": "movimento", "entrada": arquivo, "saida": arquivo, "movimento": mov, "nome_animacao": nome, "laco": a.laco.unwrap_or(false)}),
    )
    .await?;
    let _ = std::fs::remove_dir_all(&tmp);
    recibo(f, p, &arquivo, &modelo, Some(descricao.into()), a.seed, json!({"animacao": nome, "segundos": a.segundos}), quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    Ok(
        json!({"arquivo": arquivo, "animacao": nome, "modelo": modelo, "movimento": r["estatisticas"], "estatisticas": b["estatisticas"], "avisos": avisos}),
    )
}

/// generate_animation (sem origem) e retarget_animation (com origem).
pub async fn animar(f: &Fornalha, a: ArgsAnimacao, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    if let Some(d) = a.descricao.clone().filter(|s| !s.trim().is_empty()) {
        // o nome de uma animação da biblioteca não precisa do HY-Motion
        let chave = projeto::nome_de_pasta(&d);
        if !forja::ANIMACOES.contains(&chave.as_str()) {
            return animar_por_texto(f, &p, &a, &d, quem).await;
        }
    }
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    let tarefa = match &a.origem {
        Some(o) => {
            json!({"tarefa": "retarget", "entrada": arquivo, "origem": f.resolver_no_projeto(&p, o), "saida": arquivo, "animacoes": a.animacoes})
        }
        None => {
            let mut t = json!({"tarefa": "animar", "entrada": arquivo, "saida": arquivo, "animacoes": a.animacoes});
            if let Some(an) = crate::pacotes::info(&f.paths, crate::pacotes::Pacote::Animacoes) {
                t["animacoes_de"] = an["bibliotecas"].clone();
            }
            t
        }
    };
    let r = forjar(f, &tarefa).await?;
    let modelo = if a.origem.is_some() {
        "forja-3d"
    } else if r.get("novas").is_some() {
        "biblioteca-quaternius"
    } else {
        "biblioteca-fornalha"
    };
    recibo(f, &p, &arquivo, modelo, None, None, json!({"animacoes": a.animacoes, "origem": a.origem}), quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    Ok(json!({"arquivo": arquivo, "estatisticas": r["estatisticas"]}))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsMaterial {
    pub projeto: Option<String>,
    pub arquivo: String,
    /// nome do material → cor #RRGGBB (ex.: {"roupa": "#224466"}); sem isso, usa a paleta da bíblia.
    pub cores: Option<Value>,
    pub rugosidade: Option<f64>,
}

/// create_material: recolore os materiais de um modelo (pela paleta do guia visual ou pelas cores pedidas).
pub async fn criar_material(f: &Fornalha, a: ArgsMaterial, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    let r = forjar(f, &json!({"tarefa": "material", "entrada": arquivo, "saida": arquivo, "cores": a.cores, "paleta": paleta(&p), "rugosidade": a.rugosidade})).await?;
    recibo(f, &p, &arquivo, "forja-3d", None, None, json!({"cores": a.cores}), quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    Ok(json!({"arquivo": arquivo, "materiais": r["materiais"], "estatisticas": r["estatisticas"]}))
}

// ---------------------------------------------------------------- áudio

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsEfeitos {
    pub projeto: Option<String>,
    /// Efeitos a gerar (padrão: o pacote que o jogo usa).
    pub efeitos: Option<Vec<String>>,
    pub variacoes: Option<u32>,
}

pub async fn gerar_efeitos(f: &Fornalha, a: ArgsEfeitos, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let pasta = p.raiz.join("Audio/efeitos");
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    let lista: Vec<(String, Vec<f32>)> = match &a.efeitos {
        None => efeitos::pacote_padrao(),
        Some(nomes) => {
            let mut v = Vec::new();
            for nome in nomes {
                for k in 1..=a.variacoes.unwrap_or(2).clamp(1, 8) {
                    v.push((format!("{nome}_{k:02}"), efeitos::gerar(nome, k as u64 * 7919)?));
                }
            }
            v
        }
    };
    let mut arquivos = Vec::new();
    for (nome, amostras) in &lista {
        let arq = pasta.join(format!("{nome}.wav"));
        std::fs::write(&arq, audio::wav_mono_16(amostras)).map_err(|e| Erro::io(&arq, e))?;
        recibo(f, &p, &arq, "sintese-fornalha", Some(nome.clone()), None, json!({}), quem).await?;
        arquivos.push(rel(&p.raiz, &arq));
    }
    f.avisar_ponte(arquivos.clone());
    Ok(json!({"pasta": pasta, "arquivos": arquivos, "modelo": "sintese-fornalha"}))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsMusica {
    pub projeto: Option<String>,
    /// exploracao, vila, floresta, combate, chefe, masmorra (ou o nome de uma área)
    pub situacao: String,
    pub compassos: Option<u32>,
    pub seed: Option<u64>,
}

pub async fn gerar_musica(f: &Fornalha, a: ArgsMusica, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let seed = a.seed.unwrap_or(1);
    let m = musica::compor(&a.situacao, a.compassos.unwrap_or(16), seed)?;
    let pasta = p.raiz.join("Audio/musica");
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    let arq = pasta.join(format!("{}.wav", m.situacao));
    std::fs::write(&arq, audio::wav_mono_16(&m.amostras)).map_err(|e| Erro::io(&arq, e))?;
    // para a Erethea marcar o laço e trocar de música no fim do compasso
    let arq_info = pasta.join(format!("{}.musica.json", m.situacao));
    crate::paths::write_json(
        &arq_info,
        &json!({"situacao": m.situacao, "bpm": m.bpm, "compassos": m.compassos, "tonica": m.tonica, "loop": true}),
    )
    .map_err(|e| Erro::io(&arq_info, e))?;
    recibo(
        f,
        &p,
        &arq,
        "compositor-fornalha",
        Some(a.situacao.clone()),
        Some(seed),
        json!({"bpm": m.bpm, "compassos": m.compassos, "tonica": m.tonica}),
        quem,
    )
    .await?;
    f.avisar_ponte(vec![rel(&p.raiz, &arq), rel(&p.raiz, &arq_info)]);
    Ok(json!({"arquivo": arq, "info": arq_info, "situacao": m.situacao, "bpm": m.bpm, "compassos": m.compassos, "tonica": m.tonica,
              "segundos": m.amostras.len() as f64 / audio::TAXA as f64, "loop": true}))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsVoz {
    pub projeto: Option<String>,
    pub texto: String,
    pub personagem: Option<String>,
    pub idioma: Option<String>,
    pub seed: Option<u64>,
}

pub async fn gerar_voz(f: &Fornalha, a: ArgsVoz, quem: &str) -> Resultado<Value> {
    if a.texto.trim().is_empty() {
        return Err(Erro::argumento("Diga o texto da fala."));
    }
    let p = f.projeto(a.projeto.as_deref())?;
    let id = projeto::nome_de_pasta(a.personagem.as_deref().unwrap_or("fala"));
    let r = gerar_fala(f, &p, &id, &a.texto, a.idioma.as_deref().unwrap_or("pt"), a.seed.unwrap_or(1), quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, Path::new(r["arquivo"].as_str().unwrap_or("")))]);
    Ok(r)
}

// ---------------------------------------------------------------- comparação com a referência

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsComparar {
    pub projeto: Option<String>,
    /// A imagem que a pessoa mandou (personagem, arma, casa, mapa).
    pub referencia: String,
    /// O resultado: um modelo (.glb, .obj, .fbx), renderizado na mesma vista, ou uma imagem/captura.
    pub arquivo: String,
    /// frente (padrão), lado, costas, tres_quartos, cima.
    pub vista: Option<String>,
    /// auto (padrão: pela forma da referência), corpo, busto, rosto.
    pub enquadramento: Option<String>,
}

/// Referência × resultado lado a lado, com a paleta das duas, a diferença de cor e a proporção da
/// silhueta: a IA olha, ajusta os controles (cores, porte, penteado, forma) e gera de novo.
pub async fn comparar_referencia(f: &Fornalha, a: ArgsComparar) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let referencia = f.resolver_no_projeto(&p, &a.referencia);
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    for arq in [&referencia, &arquivo] {
        if !arq.is_file() {
            return Err(Erro::argumento(format!("{} não existe.", arq.display())));
        }
    }
    let nome = arquivo.file_stem().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "resultado".into());
    let saida = p.raiz.join("ai/comparacoes").join(format!("{nome}_{}.png", chrono::Utc::now().format("%Y%m%d-%H%M%S")));
    let r = forjar(
        f,
        &json!({"tarefa": "comparar", "referencia": referencia, "arquivo": arquivo, "saida": saida,
                "vista": a.vista.unwrap_or_else(|| "frente".into()), "enquadramento": a.enquadramento.unwrap_or_else(|| "auto".into()), "amostras": 24}),
    )
    .await?;
    Ok(r)
}

// ---------------------------------------------------------------- cena curta

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct LinhaDaCena {
    /// Quem fala ou age (id do personagem, como em Characters/<id> ou Enemies/<id>).
    pub quem: String,
    pub fala: Option<String>,
    /// Animação do personagem nessa linha (ex.: "acenar", "ataque_1").
    pub animacao: Option<String>,
    /// close, medio, aberto, ombro ou dois.
    pub camera: Option<String>,
    /// Para quem olhar (id de outro personagem): os dois se viram um para o outro.
    pub olhar_para: Option<String>,
    pub duracao: Option<f64>,
    pub idioma: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsCena {
    pub projeto: Option<String>,
    pub id: String,
    pub roteiro: Vec<LinhaDaCena>,
    /// Sem dublar (só legenda): rascunho rápido, sem o Ignis.
    pub sem_voz: Option<bool>,
    pub idioma: Option<String>,
    pub seed: Option<u64>,
}

const ENQUADRAMENTOS: [&str; 5] = ["close", "medio", "aberto", "ombro", "dois"];

/// Cena curta: cada fala do roteiro é dublada (com a curva da boca) e vira uma linha do
/// Cutscenes/<id>.cena.json, que o autoload CenasCurtas toca no jogo (câmera, animação, olhar, legenda).
pub async fn criar_cena(f: &Fornalha, a: ArgsCena, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let id = projeto::nome_de_pasta(&a.id);
    if a.id.trim().is_empty() || a.roteiro.is_empty() {
        return Err(Erro::argumento("Diga o id da cena e o roteiro (uma linha por fala ou ação)."));
    }
    let conhecidos: Vec<String> = engine::achar_personagens(&p.raiz).into_iter().map(|x| x.id).collect();
    let mut avisos = Vec::new();
    let mut linhas = Vec::new();
    let mut total = 0.0;
    for (i, l) in a.roteiro.iter().enumerate() {
        let camera = l.camera.clone().unwrap_or_else(|| "medio".into());
        if !ENQUADRAMENTOS.contains(&camera.as_str()) {
            return Err(Erro::argumento(format!("Enquadramento \"{camera}\" não existe. Use: {}.", ENQUADRAMENTOS.join(", "))));
        }
        for nome in std::iter::once(&l.quem).chain(l.olhar_para.as_ref()) {
            if !conhecidos.contains(nome) {
                avisos.push(format!("Linha {}: \"{nome}\" ainda não é personagem do projeto (crie com create_character).", i + 1));
            }
        }
        let texto = l.fala.clone().unwrap_or_default();
        let (mut audio, mut segundos) = (String::new(), 0.0);
        if !texto.trim().is_empty() && !a.sem_voz.unwrap_or(false) {
            let idioma = l.idioma.as_deref().or(a.idioma.as_deref()).unwrap_or("pt");
            let r = gerar_fala(f, &p, &projeto::nome_de_pasta(&l.quem), &texto, idioma, a.seed.unwrap_or(1) + i as u64, quem).await?;
            audio = format!("res://{}", rel(&p.raiz, Path::new(r["arquivo"].as_str().unwrap_or(""))));
            segundos = r["segundos"].as_f64().unwrap_or(0.0);
        }
        let leitura = if audio.is_empty() && !texto.is_empty() { 1.5 + texto.chars().count() as f64 * 0.06 } else { 0.0 };
        let dur = l.duracao.unwrap_or(0.0).max(segundos + if audio.is_empty() { 0.0 } else { 0.3 }).max(leitura).max(1.0);
        total += dur;
        linhas.push(json!({
            "quem": l.quem, "texto": texto, "audio": audio, "segundos": segundos, "animacao": l.animacao.clone().unwrap_or_default(),
            "camera": camera, "olhar_para": l.olhar_para.clone().unwrap_or_default(), "duracao": dur,
        }));
    }
    let arq = p.raiz.join(format!("Cutscenes/{id}.cena.json"));
    crate::paths::write_json(&arq, &json!({"id": id, "linhas": linhas})).map_err(|e| Erro::io(&arq, e))?;
    f.avisar_ponte(vec![rel(&p.raiz, &arq)]);
    Ok(json!({
        "arquivo": arq, "linhas": linhas, "segundos": (total * 10.0_f64).round() / 10.0, "avisos": avisos,
        "como_tocar": format!("No jogo: CenasCurtas.tocar(\"{id}\") (o jogador e os inimigos esperam; o sinal terminou avisa o fim). O run_test toca a primeira cena e tira uma foto de cada linha (cena_curta no relatório)."),
    }))
}

// ---------------------------------------------------------------- mundo e engine

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsMundo {
    pub projeto: Option<String>,
    /// [{"id","tipo"}] — padrão: as áreas da bíblia (ou vila e floresta).
    pub areas: Option<Vec<Value>>,
    pub seed: Option<u64>,
}

pub async fn gerar_blockout(f: &Fornalha, a: ArgsMundo, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let areas: Vec<Value> = match a.areas {
        Some(v) if !v.is_empty() => v,
        _ if !p.biblia.mundo.areas.is_empty() => {
            p.biblia.mundo.areas.iter().map(|x| json!({"id": x.id, "tipo": x.tipo, "nome": x.nome})).collect()
        }
        _ => vec![json!({"id": "vila", "tipo": "vila", "nome": "Vila"}), json!({"id": "floresta", "tipo": "floresta", "nome": "Floresta"})],
    };
    for ar in &areas {
        let t = ar["tipo"].as_str().unwrap_or("");
        if !forja::AREAS.contains(&t) {
            return Err(Erro::argumento(format!("Área do tipo \"{t}\" não existe. Use: {}.", forja::AREAS.join(", "))));
        }
    }
    if p.biblia.mundo.areas.is_empty() {
        let lista: Vec<Value> = areas
            .iter()
            .map(|x| json!({"id": x["id"], "tipo": x["tipo"], "nome": x.get("nome").cloned().unwrap_or(x["id"].clone())}))
            .collect();
        projeto::atualizar(&p.raiz, &json!({"mundo": {"areas": lista}}))?;
    }
    let seed = a.seed.unwrap_or(7);
    let saida = p.raiz.join("World/blockout.glb");
    let r = forjar(
        f,
        &json!({"tarefa": "mundo", "saida": saida, "amostras": 14, "mundo": {"seed": seed, "areas": areas, "paleta": paleta(&p)}}),
    )
    .await?;
    for arq in r["arquivos"].as_object().cloned().unwrap_or_default().values().filter_map(|v| v.as_str()) {
        let caminho = Path::new(arq);
        if caminho.extension().is_some_and(|e| e == "glb" || e == "png") {
            recibo(f, &p, caminho, "forja-3d", Some("mundo em blockout".into()), Some(seed), json!({"areas": areas}), quem).await?;
        }
    }
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    Ok(json!({"arquivos": r["arquivos"], "estatisticas": r["estatisticas"], "info": r["info"]}))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsMapa {
    pub projeto: Option<String>,
    /// O plano do mapa (regiões, relevo, rio, estradas, clima, hora). Sem ele: o último plano
    /// (World/mapa/plano.json) ou um plano feito das áreas da bíblia.
    pub plano: Option<Value>,
    pub seed: Option<u64>,
    /// Fotos do Blender (vista alta e chegada). Padrão: sim.
    pub fotos: Option<bool>,
    /// Muda só alguns campos do último plano (ex.: {"clima": "neve", "relevo": {"estilo": "vale"}}).
    pub mudar: Option<Value>,
}

/// Texturas CC0 do pacote de materiais (ambientCG) para cada camada do chão do mapa.
const TEXTURAS_DO_MAPA: [(&str, &str); 3] = [("grama", "Grass004"), ("terra", "Ground037"), ("rocha", "Rock051")];

fn achar_mapa(pasta: &Path, sufixo: &str) -> Option<PathBuf> {
    std::fs::read_dir(pasta).ok()?.flatten().map(|e| e.path()).find(|p| p.to_string_lossy().ends_with(sufixo))
}

/// Bancada de mapa: o plano da IA vira relevo com erosão, rio, lago, estradas com ponte, chão pintado,
/// vegetação por regras, vila e masmorra, luz pela hora; volta com as medidas e as imagens.
pub async fn gerar_mapa(f: &Fornalha, a: ArgsMapa, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let pasta = p.raiz.join("World/mapa");
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    let arq_plano = pasta.join("plano.json");
    let mut plano = match a.plano {
        Some(v) if v.is_object() => v,
        Some(_) => return Err(Erro::argumento("O plano do mapa precisa ser um objeto JSON (veja a descrição de generate_map).")),
        None => std::fs::read(&arq_plano).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(json!({})),
    };
    if let Some(Value::Object(m)) = a.mudar {
        for (k, v) in m {
            match (plano.get_mut(&k), v) {
                (Some(Value::Object(dentro)), Value::Object(novo)) => dentro.extend(novo),
                (_, v) => plano[&k] = v,
            }
        }
    }
    if let Some(s) = a.seed {
        plano["seed"] = json!(s);
    }
    let areas: Vec<Value> = p.biblia.mundo.areas.iter().map(|x| json!({"id": x.id, "tipo": x.tipo, "nome": x.nome})).collect();
    let r = forjar(
        f,
        &json!({"tarefa": "mapa", "saida": pasta, "plano": plano, "areas": areas, "paleta": paleta(&p), "projeto_raiz": p.raiz,
                "fotos": a.fotos.unwrap_or(true), "amostras": 12}),
    )
    .await?;
    // o plano completo (com o que a Fornalha preencheu) fica para a IA editar e mandar de novo
    crate::paths::write_json(&arq_plano, &r["plano"]).map_err(|e| Erro::io(&arq_plano, e))?;
    let seed = r["plano"]["seed"].as_u64();
    let gerados: Vec<PathBuf> =
        r["arquivos"].as_object().map(|o| o.values().filter_map(|v| v.as_str()).map(PathBuf::from).collect()).unwrap_or_default();
    for arq in gerados.iter().filter(|c| c.extension().is_some_and(|e| e == "glb" || e == "png")) {
        recibo(f, &p, arq, "forja-3d", Some("mapa (bancada de mapa)".into()), seed, json!({"plano": r["plano"]}), quem).await?;
    }
    // texturas do chão (CC0) quando o pacote de materiais está instalado
    let mut texturas = Vec::new();
    if let Some(dir) = crate::pacotes::materiais_da_forja(&f.paths).and_then(|m| m["materiais"].as_str().map(PathBuf::from)) {
        let destino = pasta.join("texturas");
        for (camada, id) in TEXTURAS_DO_MAPA {
            for (sufixo, nome) in [("_Color.jpg", "cor"), ("_NormalGL.jpg", "normal")] {
                let Some(origem) = achar_mapa(&dir.join(id), sufixo) else { continue };
                std::fs::create_dir_all(&destino).map_err(|e| Erro::io(&destino, e))?;
                let alvo = destino.join(format!("{camada}_{nome}.jpg"));
                if !alvo.is_file() {
                    std::fs::copy(&origem, &alvo).map_err(|e| Erro::io(&alvo, e))?;
                    recibo(f, &p, &alvo, "materiais-ambientcg", None, None, json!({"fonte": id}), quem).await?;
                }
                texturas.push(rel(&p.raiz, &alvo));
            }
        }
    }
    f.avisar_ponte(vec![rel(&p.raiz, &pasta.join("mapa.json"))]);
    let aprovado = r["medidas"]["aprovado"].as_bool().unwrap_or(false);
    Ok(json!({
        "arquivos": r["arquivos"], "medidas": r["medidas"], "estatisticas": r["estatisticas"], "avisos": r["avisos"],
        "plano": r["plano"], "regioes": r["regioes"], "fotos": r["fotos"], "texturas": texturas,
        "proximo": if aprovado {
            "Olhe o mapa.png e as vistas; ajuste o plano (World/mapa/plano.json) se quiser e gere de novo. Depois: import_to_engine e run_test (tira uma foto de cada região, com o FPS)."
        } else {
            "As medidas reprovaram algo (veja medidas.reprovado e o explica de cada item): mude o plano e gere de novo."
        },
    }))
}

/// Antes do teste na engine: o jogo precisa de chão e de sons.
async fn garantir_mundo_e_sons(f: &Fornalha, p: &Projeto, quem: &str) -> Resultado<()> {
    if !p.raiz.join("World/blockout.glb").is_file() && !p.raiz.join("World/mapa/mapa.json").is_file() {
        gerar_blockout(f, ArgsMundo { projeto: Some(p.raiz.to_string_lossy().into_owned()), ..Default::default() }, quem).await?;
    }
    if !p.raiz.join("Audio/efeitos").is_dir() {
        gerar_efeitos(f, ArgsEfeitos { projeto: Some(p.raiz.to_string_lossy().into_owned()), ..Default::default() }, quem).await?;
    }
    Ok(())
}

/// A engine da bíblia (godot ou erethea); se não estiver instalada, a outra, com aviso.
async fn engine_do_projeto(f: &Fornalha, p: &Projeto, avisos: &mut Vec<String>) -> Resultado<Achado> {
    let quer = Programa::from_engine(&p.biblia.engine).unwrap_or(Programa::Godot);
    match f.programa(quer).await {
        Ok(a) => Ok(a),
        Err(e) => {
            let outra = if quer == Programa::Godot { Programa::Erethea } else { Programa::Godot };
            match f.programa(outra).await {
                Ok(a) => {
                    avisos.push(format!("{} não encontrada; usei a {} (o projeto abre igual nas duas).", quer.nome(), outra.nome()));
                    Ok(a)
                }
                Err(_) => Err(e),
            }
        }
    }
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsProjetoSimples {
    pub projeto: Option<String>,
}

/// generate_code: escreve o código do jogo (jogador, inimigo, HUD, sons, teste) e o project.godot.
pub async fn gerar_codigo(f: &Fornalha, a: ArgsProjetoSimples) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let mut avisos = Vec::new();
    let versao = match engine_do_projeto(f, &p, &mut avisos).await {
        Ok(e) => e.versao.unwrap_or_default(),
        Err(_) => {
            avisos.push("Nenhuma engine encontrada: o código foi escrito para a Godot 4.6 (abre também na Erethea).".into());
            "4.6".into()
        }
    };
    let r = engine::preparar_projeto(&p, &versao)?;
    f.avisar_ponte(r.escritos.clone());
    Ok(json!({"escritos": r.escritos, "mantidos_por_voce": r.mantidos, "avisos": avisos,
              "scripts": engine::PASTA_SCRIPTS, "engine": p.biblia.engine}))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsEngine {
    pub projeto: Option<String>,
    pub jogador: Option<String>,
    /// Põe o primeiro inimigo bem na frente do jogador (para testar o inimigo novo).
    pub inimigo_perto: Option<bool>,
}

pub async fn importar_na_engine(f: &Fornalha, a: ArgsEngine, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let mut avisos = Vec::new();
    let eng = engine_do_projeto(f, &p, &mut avisos).await?;
    let preparo = engine::preparar_projeto(&p, eng.versao.as_deref().unwrap_or(""))?;
    // céu HDRI do pacote de materiais (CC0) para a luz e os reflexos do jogo
    if let Some(ceu) = crate::pacotes::materiais_da_forja(&f.paths).and_then(|m| m["ceu"].as_str().map(PathBuf::from)) {
        let destino = p.raiz.join("World/ceu.exr");
        if ceu.is_file() && !destino.is_file() {
            std::fs::create_dir_all(p.raiz.join("World")).map_err(|e| Erro::io(&destino, e))?;
            std::fs::copy(&ceu, &destino).map_err(|e| Erro::io(&destino, e))?;
            recibo(
                f,
                &p,
                &destino,
                "materiais-ambientcg",
                None,
                None,
                json!({"fonte": ceu.file_name().map(|n| n.to_string_lossy().into_owned())}),
                quem,
            )
            .await?;
        }
    }
    let manifesto = engine::escrever_manifesto(&p.raiz, a.jogador.as_deref(), a.inimigo_perto.unwrap_or(false))?;
    if manifesto["personagens"].as_array().is_none_or(|v| v.is_empty()) {
        avisos.push("Ainda não há personagem nem inimigo: crie com create_character para o jogo ter quem jogar.".into());
    }
    // com a Erethea ligada ao vivo dizendo que monta as cenas, a Fornalha só avisa (sem o montar.gd)
    let montado = if f.engine_monta_cenas(&p.raiz) {
        f.avisar_ponte(vec![".fornalha/cena.json".into()]);
        json!({"cenas": f.cenas_da_engine().unwrap_or(json!({"montadas_pela": "erethea"})), "erros_da_engine": []})
    } else {
        let m = engine::montar(&eng, &p.raiz).await?;
        f.avisar_ponte(vec!["principal.tscn".into()]);
        m
    };
    Ok(
        json!({"engine": eng.programa.nome(), "versao": eng.versao, "cenas": montado["cenas"], "erros_da_engine": montado["erros_da_engine"],
              "scripts_escritos": preparo.escritos, "scripts_mantidos": preparo.mantidos, "manifesto": manifesto, "avisos": avisos}),
    )
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsTeste {
    pub projeto: Option<String>,
    pub segundos: Option<f64>,
    pub video: Option<bool>,
}

/// run_test: abre o jogo em modo de teste, coleta erros e tira capturas.
pub async fn rodar_teste(f: &Fornalha, a: ArgsTeste) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let mut avisos = Vec::new();
    let eng = engine_do_projeto(f, &p, &mut avisos).await?;
    if !p.raiz.join("principal.tscn").is_file() {
        return Err(Erro::novo("sem_cena", "O jogo ainda não foi montado: use import_to_engine antes do run_test."));
    }
    let tem_tela = cfg!(windows)
        || cfg!(target_os = "macos")
        || std::env::var_os("DISPLAY").is_some()
        || std::env::var_os("WAYLAND_DISPLAY").is_some();
    let sem_placa = f.deteccao(false).await.principal().is_none();
    let pasta: PathBuf = p.raiz.join("ai/testes").join(crate::util::agora_iso().replace(':', "-"));
    let op =
        OpcoesTeste { segundos: a.segundos.unwrap_or(9.0), sem_janela: !tem_tela, sem_placa, video: a.video.unwrap_or(true) && tem_tela };
    let mut rel = engine::testar(&eng, &p.raiz, &pasta, &op).await?;
    if !tem_tela {
        avisos.push("Sem tela nesta máquina: o teste rodou sem janela (sem capturas).".into());
    }
    rel["avisos"] = json!(avisos);
    rel["pasta"] = json!(pasta);
    Ok(rel)
}

#[cfg(test)]
mod testes_itens {
    use super::*;

    #[test]
    fn tamanho_padrao_pelo_que_o_item_e() {
        assert_eq!(altura_padrao_do_item("arma", "espada longa"), 1.0);
        assert_eq!(altura_padrao_do_item("objeto", "casa de pedra de dois andares"), 6.0);
        assert_eq!(altura_padrao_do_item("objeto", "Torre de vigia"), 6.0);
        assert_eq!(altura_padrao_do_item("objeto", "árvore seca"), 5.0);
        assert_eq!(altura_padrao_do_item("objeto", "baú de madeira"), 1.0);
    }
}

#[cfg(test)]
mod testes_controles {
    use serde_json::json;

    fn ficha(controles: serde_json::Value) -> serde_json::Value {
        json!({"id": "x", "nome": "Teste", "descricao": "andarilho", "papel": "heroi", "porte": "medio", "controles": controles})
    }

    #[test]
    fn idade_em_anos_vira_a_do_makehuman() {
        assert!((super::idade_mh(25.0) - 0.5).abs() < 1e-9);
        assert!((super::idade_mh(11.0) - 0.1875).abs() < 1e-9);
        assert!((super::idade_mh(90.0) - 1.0).abs() < 1e-9);
        assert!((super::idade_mh(5.0) - 0.1875).abs() < 1e-9, "abaixo de 11 anos fica em 11");
        assert!(super::idade_mh(50.0) > 0.5 && super::idade_mh(50.0) < 1.0);
    }

    #[test]
    fn controles_de_cabelo_barba_e_corpo_chegam_ao_humano() {
        let h = super::humano_da_ficha(
            &ficha(json!({
                "genero": "masculino", "idade": 50,
                "cabelo": {"penteado": "short02", "cor": "#4f4842", "volume_cm": 1.6, "ondulacao": 0.4},
                "barba": {"tipo": "cheia", "cor": "#6b6660", "comprimento_cm": 2.5, "grisalho": 0.4},
                "corpo_humano": {"altura": 0.7, "musculo": 2.0},
                "rosto": {"nariz_largura": 0.3}, "cor_olhos": "green", "sobrancelha": "eyebrow002"
            })),
            crate::niveis::Nivel::Qualidade,
        );
        assert_eq!(h["macro"]["genero"], 1.0);
        assert!((h["macro"]["idade"].as_f64().unwrap() - super::idade_mh(50.0)).abs() < 1e-9);
        assert_eq!(h["cabelo"], "short02");
        assert_eq!(h["cor_cabelo"], "#4f4842");
        assert_eq!(h["cabelo_estilo"]["volume_cm"], 1.6);
        assert!(h["cabelo_estilo"].get("penteado").is_none() && h["cabelo_estilo"].get("cor").is_none());
        assert_eq!(h["barba"], "cheia");
        assert_eq!(h["cor_barba"], "#6b6660");
        assert_eq!(h["barba_estilo"]["comprimento_cm"], 2.5);
        assert_eq!(h["macro"]["altura"], 0.7);
        assert_eq!(h["macro"]["musculo"], 1.0, "fora de 0..1 fica no limite");
        assert_eq!(h["detalhes"]["nariz_largura"], 0.3);
        assert_eq!(h["cor_olhos"], "green");
        assert_eq!(h["sobrancelha"], "eyebrow002");
        let pl = super::humano_da_ficha(&ficha(json!({"pele": {"sardas": 0.7, "bronzeado": 0.3}})), crate::niveis::Nivel::Qualidade);
        assert_eq!(pl["pele"]["sardas"], 0.7);
        let j = super::humano_da_ficha(
            &ficha(json!({"roupa": {"estilo": "jaqueta", "cores": {"principal": "#5b4632"}, "capa": false}})),
            crate::niveis::Nivel::Qualidade,
        );
        assert_eq!(j["roupa"]["estilo"], "jaqueta");
        assert_eq!(j["roupa"]["cores"]["principal"], "#5b4632");
        assert_eq!(j["roupa"]["capa"], false);
        let m = super::humano_da_ficha(&ficha(json!({"roupa": {"estilo": "manequim"}})), crate::niveis::Nivel::Qualidade);
        assert!(m.get("roupa").is_none() && m["manequim"] == true, "manequim sai sem roupa");
        let x = super::humano_da_ficha(&ficha(json!({"roupa": {"estilo": "astronauta"}})), crate::niveis::Nivel::Qualidade);
        assert_ne!(x["roupa"]["estilo"], "astronauta", "estilo que o alfaiate não faz não entra");
    }

    #[test]
    fn penteado_desconhecido_nao_entra_e_genero_troca_o_padrao() {
        let h = super::humano_da_ficha(&ficha(json!({"cabelo": "moicano_inventado"})), crate::niveis::Nivel::Qualidade);
        assert_eq!(h["cabelo"], "short04", "fica o penteado da ficha");
        let f = super::humano_da_ficha(&ficha(json!({"genero": "feminino"})), crate::niveis::Nivel::Qualidade);
        assert_eq!(f["macro"]["genero"], 0.0);
        assert_eq!(f["cabelo"], "long01");
    }

    #[test]
    fn controle_da_ia_vale_mais_que_o_padrao_do_zumbi() {
        let mut fz = ficha(json!({"barba": "nenhuma", "cor_olhos": "brown"}));
        fz["tipo"] = json!("zumbi");
        let h = super::humano_da_ficha(&fz, crate::niveis::Nivel::Qualidade);
        assert_eq!(h["zumbi"], true);
        assert_eq!(h["barba"], "nenhuma");
        assert_eq!(h["cor_olhos"], "brown");
        let sem = super::humano_da_ficha(
            &{
                let mut f = ficha(json!(null));
                f["tipo"] = json!("zumbi");
                f
            },
            crate::niveis::Nivel::Qualidade,
        );
        assert_eq!(sem["barba"], "rala");
    }
}

#[cfg(test)]
mod testes_memoria {
    #[test]
    fn reconhece_falta_de_memoria_de_video() {
        assert!(super::falta_memoria_de_video("z_image graph execution failed on Vulkan0: vk::Queue::submit: ErrorOutOfDeviceMemory"));
        assert!(!super::falta_memoria_de_video("modelo não encontrado"));
    }
}
