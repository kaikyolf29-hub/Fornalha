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

const TEMPO_BLENDER: Duration = Duration::from_secs(900);

fn rel(raiz: &Path, arq: &Path) -> String {
    arq.strip_prefix(raiz).unwrap_or(arq).to_string_lossy().replace('\\', "/")
}

/// Registra o recibo de um arquivo gerado.
#[allow(clippy::too_many_arguments)]
async fn recibo(
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

async fn forjar(f: &Fornalha, tarefa: &Value) -> Resultado<Value> {
    let b = blender(f).await?;
    forja::rodar(&b, &f.paths.data_dir, tarefa, TEMPO_BLENDER).await
}

fn paleta(p: &Projeto) -> Vec<String> {
    p.biblia.guia_visual.paleta.clone()
}

fn texto_do_projeto(p: &Projeto) -> String {
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
    /// Vídeo curto das animações.
    pub video: Option<bool>,
    /// Montar na engine e rodar o teste depois (o pronto da Fase 4).
    pub testar_na_engine: Option<bool>,
    pub seed: Option<u64>,
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
        ("morto-vivo", "esqueleto"),
        ("zumbi", "esqueleto"),
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
                "armadura": {"type": "string", "enum": ["nenhuma", "leve", "pesada"]},
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

    // conceito (imagem pelo Ignis)
    if a.conceito.unwrap_or(true) {
        match gerar_imagem_conceito(f, &p, &descrever_para_imagem(&p, &ficha), &pasta.join("conceito.png"), seed, quem).await {
            Ok(arq) => {
                arquivos.insert("conceito".into(), json!(arq));
            }
            Err(e) => avisos.push(format!("Conceito sem imagem: {}", e.mensagem)),
        }
    }

    // 3D (Forja). Com placa NVIDIA e o worker do TRELLIS.2 liberado, o 3D sairia da imagem de conceito.
    let ctx = f.contexto(Some(&p)).await;
    let nivel = f.nivel_em_uso(Some(&p)).await;
    let escolha = crate::licencas::escolher(&f.catalogo, "3d", nivel, &ctx)?;
    let modelo_3d = escolha.modelo.as_ref().map(|m| m.id.clone()).unwrap_or_default();
    if modelo_3d != "forja-3d" {
        avisos.push(format!(
            "O roteador escolheu {} para o 3D, mas o worker dele ainda não está instalado nesta máquina: usei a Forja da Fornalha.",
            escolha.modelo.as_ref().map(|m| m.nome.as_str()).unwrap_or("?")
        ));
    }
    let glb = pasta.join(format!("{id}.glb"));
    let tarefa = json!({"tarefa": "personagem", "saida": glb, "folha": true, "video": a.video.unwrap_or(false), "amostras": 20, "personagem": ficha});
    let r = forjar(f, &tarefa).await?;
    std::fs::write(pasta.join(format!("{id}.forja.json")), serde_json::to_vec_pretty(&r).unwrap_or_default()).ok();
    let parametros = json!({"tipo": ficha["tipo"], "arma": ficha["arma"], "armadura": ficha["armadura"], "nivel": nivel.id()});
    for (chave, arq) in r["arquivos"].as_object().cloned().unwrap_or_default() {
        if let Some(s) = arq.as_str() {
            recibo(f, &p, Path::new(s), "forja-3d", ficha["descricao"].as_str().map(String::from), Some(seed), parametros.clone(), quem)
                .await?;
            arquivos.insert(chave, json!(s));
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
        "ficha": ficha, "pasta": pasta, "arquivos": arquivos, "estatisticas": r["estatisticas"], "segundos_blender": r["segundos"],
        "modelo_3d": "forja-3d", "avisos": avisos,
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

fn descrever_para_imagem(p: &Projeto, ficha: &Value) -> String {
    let estilo = if p.biblia.guia_visual.texto_de_estilo.is_empty() {
        "arte de jogo 3D estilizada, low poly".to_string()
    } else {
        p.biblia.guia_visual.texto_de_estilo.clone()
    };
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

/// generate_concept: imagem avulsa com o guia visual junto.
pub async fn conceito_avulso(f: &Fornalha, p: &Projeto, descricao: &str, destino: &Path, seed: u64, quem: &str) -> Resultado<Value> {
    let estilo = if p.biblia.guia_visual.texto_de_estilo.is_empty() {
        "arte de jogo 3D estilizada".to_string()
    } else {
        p.biblia.guia_visual.texto_de_estilo.clone()
    };
    let prompt = format!("{estilo}. {descricao}. Paleta: {}.", paleta(p).join(", "));
    let arq = gerar_imagem_conceito(f, p, &prompt, destino, seed, quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, destino)]);
    Ok(json!({"arquivo": arq, "prompt": prompt}))
}

async fn gerar_imagem_conceito(f: &Fornalha, p: &Projeto, prompt: &str, destino: &Path, seed: u64, quem: &str) -> Resultado<String> {
    let cap = ignis::capacidades(f.porta_ignis()).await;
    if cap["imagem"].as_array().is_none_or(|v| v.is_empty()) {
        return Err(Erro::novo(
            "ignis_sem_imagem",
            "o Ignis não está aberto ou a geração de imagem não foi preparada nele (janela do Ignis → Imagem).",
        ));
    }
    let sem_placa = f.deteccao(false).await.principal().is_none();
    let (tamanho, passos) = if sem_placa { ("384x384", 6) } else { ("1024x1024", 8) };
    let (png, info) = ignis::gerar_imagem(f.porta_ignis(), prompt, tamanho, seed, passos).await?;
    if let Some(d) = destino.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    std::fs::write(destino, &png).map_err(|e| Erro::io(destino, e))?;
    recibo(
        f,
        p,
        destino,
        "z-image-turbo-ignis",
        Some(prompt.into()),
        Some(seed),
        json!({"tamanho": tamanho, "passos": passos, "ignis": info}),
        quem,
    )
    .await?;
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
    crate::paths::write_json(&arq_boca, &json!({"quadros_por_segundo": 30, "abertura": boca})).map_err(|e| Erro::io(&arq_boca, e))?;
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
}

pub async fn gerar_3d(f: &Fornalha, a: Args3d, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let seed = a.seed.unwrap_or(1);
    let (tarefa, pasta, nome) = if let Some(entrada) = &a.entrada {
        let nome = projeto::nome_de_pasta(a.nome.as_deref().unwrap_or("modelo"));
        let pasta = p.raiz.join("Items");
        (
            json!({"tarefa": "limpar", "entrada": f.resolver_no_projeto(&p, entrada), "nome": nome, "altura_m": a.altura_m, "triangulos_max": a.triangulos_max}),
            pasta,
            nome,
        )
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
    Ok(json!({"arquivos": arquivos, "estatisticas": r["estatisticas"], "segundos": r["segundos"]}))
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
}

/// create_skeleton: malha de fora (TRELLIS.2, Hunyuan3D, feita à mão) ganha o esqueleto padrão e animações.
pub async fn criar_esqueleto(f: &Fornalha, a: ArgsEsqueleto, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let nome = projeto::nome_de_pasta(a.nome.as_deref().unwrap_or("personagem"));
    let pasta = p.raiz.join(if a.inimigo.unwrap_or(false) { "Enemies" } else { "Characters" }).join(&nome);
    let saida = pasta.join(format!("{nome}.glb"));
    let r = forjar(
        f,
        &json!({"tarefa": "rig", "entrada": f.resolver_no_projeto(&p, &a.entrada), "saida": saida, "nome": nome, "altura_m": a.altura_m.unwrap_or(1.8),
                "girar_graus": a.girar_graus, "animacoes": a.animacoes, "triangulos_max": 20000}),
    )
    .await?;
    std::fs::write(pasta.join(format!("{nome}.forja.json")), serde_json::to_vec_pretty(&r).unwrap_or_default()).ok();
    for arq in r["arquivos"].as_object().cloned().unwrap_or_default().values().filter_map(|v| v.as_str()) {
        recibo(f, &p, Path::new(arq), "rigify-blender", None, None, json!({"entrada": a.entrada}), quem).await?;
    }
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    Ok(json!({"arquivos": r["arquivos"], "estatisticas": r["estatisticas"]}))
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
}

/// generate_animation (sem origem) e retarget_animation (com origem).
pub async fn animar(f: &Fornalha, a: ArgsAnimacao, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    let tarefa = match &a.origem {
        Some(o) => {
            json!({"tarefa": "retarget", "entrada": arquivo, "origem": f.resolver_no_projeto(&p, o), "saida": arquivo, "animacoes": a.animacoes})
        }
        None => json!({"tarefa": "animar", "entrada": arquivo, "saida": arquivo, "animacoes": a.animacoes}),
    };
    let r = forjar(f, &tarefa).await?;
    let modelo = if a.origem.is_some() { "forja-3d" } else { "biblioteca-fornalha" };
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
    f.avisar_ponte(vec![rel(&p.raiz, &arq)]);
    Ok(json!({"arquivo": arq, "situacao": m.situacao, "bpm": m.bpm, "compassos": m.compassos, "tonica": m.tonica,
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

/// Antes do teste na engine: o jogo precisa de chão e de sons.
async fn garantir_mundo_e_sons(f: &Fornalha, p: &Projeto, quem: &str) -> Resultado<()> {
    if !p.raiz.join("World/blockout.glb").is_file() {
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

pub async fn importar_na_engine(f: &Fornalha, a: ArgsEngine, _quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let mut avisos = Vec::new();
    let eng = engine_do_projeto(f, &p, &mut avisos).await?;
    let preparo = engine::preparar_projeto(&p, eng.versao.as_deref().unwrap_or(""))?;
    let manifesto = engine::escrever_manifesto(&p.raiz, a.jogador.as_deref(), a.inimigo_perto.unwrap_or(false))?;
    if manifesto["personagens"].as_array().is_none_or(|v| v.is_empty()) {
        avisos.push("Ainda não há personagem nem inimigo: crie com create_character para o jogo ter quem jogar.".into());
    }
    let montado = engine::montar(&eng, &p.raiz).await?;
    f.avisar_ponte(vec!["principal.tscn".into()]);
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
