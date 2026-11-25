//! Bíblia do jogo: o `game.project.json` de cada projeto.
//!
//! É a fonte da verdade do projeto (gênero, câmera, personagens, mundo e guia
//! visual). Toda geração recebe esse contexto, para nada sair fora do jogo.
//!
//! Campos que esta versão não conhece são preservados (`extras`), para o
//! agente ou uma versão mais nova da Fornalha poderem guardar mais coisas.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::erro::{Erro, Resultado};
use crate::niveis::Nivel;
use crate::paths::write_json;
use crate::util::{agora_iso, id_aleatorio, merge_patch};

pub const ARQUIVO_BIBLIA: &str = "game.project.json";
/// Banco de recibos de licença (uma linha JSON por asset).
pub const ARQUIVO_RECIBOS: &str = "ai/recibos.jsonl";
pub const FORMATO_ATUAL: u32 = 1;

/// Pastas padrão de todo projeto, na ordem do plano.
pub const PASTAS_PADRAO: [&str; 14] = [
    "GameDesign",
    "World",
    "Characters",
    "Enemies",
    "Items",
    "Weapons",
    "Animations",
    "Audio",
    "VFX",
    "Cutscenes",
    "UI",
    "Scripts",
    "blender",
    "ai",
];

/// Campos que só a Fornalha muda.
const CAMPOS_PROTEGIDOS: [&str; 4] = ["id", "formato", "criado_em", "atualizado_em"];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Biblia {
    pub formato: u32,
    pub id: String,
    pub nome: String,
    pub criado_em: String,
    pub atualizado_em: String,
    /// Projeto à venda: o roteador não deixa modelo sem licença comercial tocar nele.
    pub comercial: bool,
    /// Nível de qualidade preferido do projeto (`None` = o da máquina).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nivel: Option<String>,
    /// Engine de destino: a Erethea Engine (a principal, decisão do criador em 25/11/2026). Sem ela
    /// instalada, a Fornalha monta e testa na Godot e avisa (o projeto abre igual nas duas).
    #[serde(default = "engine_padrao")]
    pub engine: String,
    #[serde(default)]
    pub conceito: Conceito,
    #[serde(default)]
    pub guia_visual: GuiaVisual,
    #[serde(default)]
    pub personagens: Vec<Personagem>,
    #[serde(default)]
    pub mundo: Mundo,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

fn engine_padrao() -> String {
    "erethea".into()
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Conceito {
    pub genero: String,
    /// "estilizado", "realista" ou o que o guia visual decidir.
    pub estilo: String,
    pub plataformas: Vec<String>,
    pub camera: String,
    pub historia: String,
    pub ambientacao: String,
    pub mecanicas: Vec<String>,
    pub publico: String,
    pub duracao: String,
    pub referencias_visuais: Vec<String>,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct GuiaVisual {
    /// Texto de estilo que vai junto em toda geração.
    pub texto_de_estilo: String,
    /// Cores em #RRGGBB.
    pub paleta: Vec<String>,
    pub traco: String,
    /// Imagens de referência (5 a 10 aprovadas, pelo plano).
    pub referencias: Vec<Referencia>,
    /// O que evitar.
    pub evitar: Vec<String>,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Referencia {
    /// Caminho relativo à pasta do projeto.
    pub arquivo: String,
    pub aprovada: bool,
    pub nota: String,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Personagem {
    pub id: String,
    pub nome: String,
    pub papel: String,
    pub roupa: String,
    pub arma: String,
    pub descricao: String,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Mundo {
    pub areas: Vec<Area>,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Area {
    pub id: String,
    pub nome: String,
    /// vila, floresta, montanha, masmorra, arena...
    pub tipo: String,
    pub descricao: String,
    /// Acústica escolhida à mão (caverna, castelo, salao, floresta, vila, aberto…). Sem ela, a
    /// Erethea escolhe o eco pelo tipo da área.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub acustica: Option<String>,
    #[serde(flatten)]
    pub extras: Map<String, Value>,
}

/// Pedido de projeto novo.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct NovoProjeto {
    pub nome: String,
    /// Onde criar (padrão: a pasta de projetos da Fornalha).
    pub pasta_pai: Option<PathBuf>,
    /// Nome da pasta (padrão: tirado do nome do projeto).
    pub pasta: Option<String>,
    /// Padrão: comercial.
    pub comercial: Option<bool>,
    pub conceito: Option<Conceito>,
}

/// Projeto aberto: onde ele está e a bíblia.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Projeto {
    pub raiz: PathBuf,
    pub biblia: Biblia,
}

impl Projeto {
    pub fn arquivo_biblia(&self) -> PathBuf {
        self.raiz.join(ARQUIVO_BIBLIA)
    }
}

/// Nome de pasta seguro em Windows e Linux, a partir do nome do projeto.
pub fn nome_de_pasta(nome: &str) -> String {
    let mut s = String::new();
    for c in nome.chars().flat_map(sem_acento) {
        if c.is_ascii_alphanumeric() {
            s.push(c.to_ascii_lowercase());
        } else if !s.ends_with('-') && !s.is_empty() {
            s.push('-');
        }
    }
    let mut s: String = s.trim_matches('-').chars().take(64).collect();
    while s.ends_with('-') {
        s.pop();
    }
    if s.is_empty() {
        return "projeto".into();
    }
    if nome_reservado_windows(&s) {
        s.push_str("-projeto");
    }
    s
}

fn sem_acento(c: char) -> Vec<char> {
    let base = match c {
        'á' | 'à' | 'â' | 'ã' | 'ä' | 'å' => 'a',
        'Á' | 'À' | 'Â' | 'Ã' | 'Ä' | 'Å' => 'A',
        'é' | 'è' | 'ê' | 'ë' => 'e',
        'É' | 'È' | 'Ê' | 'Ë' => 'E',
        'í' | 'ì' | 'î' | 'ï' => 'i',
        'Í' | 'Ì' | 'Î' | 'Ï' => 'I',
        'ó' | 'ò' | 'ô' | 'õ' | 'ö' => 'o',
        'Ó' | 'Ò' | 'Ô' | 'Õ' | 'Ö' => 'O',
        'ú' | 'ù' | 'û' | 'ü' => 'u',
        'Ú' | 'Ù' | 'Û' | 'Ü' => 'U',
        'ç' => 'c',
        'Ç' => 'C',
        'ñ' => 'n',
        'Ñ' => 'N',
        _ => c,
    };
    vec![base]
}

fn nome_reservado_windows(s: &str) -> bool {
    let s = s.to_ascii_uppercase();
    matches!(s.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || ((s.starts_with("COM") || s.starts_with("LPT")) && s.len() == 4 && s.as_bytes()[3].is_ascii_digit())
}

fn validar_nome(nome: &str) -> Resultado<()> {
    let n = nome.trim();
    if n.is_empty() {
        return Err(Erro::novo("nome_invalido", "O projeto precisa de um nome."));
    }
    if n.chars().count() > 80 {
        return Err(Erro::novo("nome_invalido", "O nome do projeto pode ter no máximo 80 letras."));
    }
    if n.chars().any(char::is_control) {
        return Err(Erro::novo("nome_invalido", "O nome do projeto não pode ter quebra de linha nem tabulação."));
    }
    Ok(())
}

fn validar_pasta(pasta: &str) -> Resultado<()> {
    let ok = !pasta.trim().is_empty()
        && pasta != "."
        && pasta != ".."
        && !pasta.contains(['/', '\\', ':'])
        && !pasta.chars().any(char::is_control)
        && !nome_reservado_windows(pasta);
    if ok {
        Ok(())
    } else {
        Err(Erro::novo("pasta_invalida", format!("\"{pasta}\" não serve como nome de pasta (sem barras, \"..\" ou nomes reservados).")))
    }
}

/// Confere tudo o que a Fornalha exige da bíblia.
pub fn validar(b: &Biblia) -> Resultado<()> {
    let ruim = |m: String| Err(Erro::novo("biblia_invalida", m));
    if b.formato == 0 || b.formato > FORMATO_ATUAL {
        return ruim(format!(
            "Formato {} da bíblia não é suportado por esta versão (até {FORMATO_ATUAL}). Atualize a Fornalha.",
            b.formato
        ));
    }
    if let Err(e) = validar_nome(&b.nome) {
        return ruim(e.mensagem);
    }
    if let Some(n) = &b.nivel {
        if Nivel::from_id(n).is_none() {
            return ruim(format!("Nível \"{n}\" não existe. Use leve, equilibrado, qualidade ou maximo."));
        }
    }
    for cor in &b.guia_visual.paleta {
        let hex = cor.strip_prefix('#').unwrap_or("");
        if hex.len() != 6 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
            return ruim(format!("A cor \"{cor}\" da paleta precisa estar no formato #RRGGBB."));
        }
    }
    let mut ids = HashSet::new();
    for p in &b.personagens {
        if p.id.trim().is_empty() {
            return ruim(format!("O personagem \"{}\" precisa de um id.", p.nome));
        }
        if !ids.insert(p.id.as_str()) {
            return ruim(format!("Dois personagens com o mesmo id \"{}\".", p.id));
        }
    }
    let mut ids = HashSet::new();
    for a in &b.mundo.areas {
        if a.id.trim().is_empty() {
            return ruim(format!("A área \"{}\" precisa de um id.", a.nome));
        }
        if !ids.insert(a.id.as_str()) {
            return ruim(format!("Duas áreas com o mesmo id \"{}\".", a.id));
        }
    }
    Ok(())
}

fn pasta_vazia_ou_inexistente(p: &Path) -> bool {
    match std::fs::read_dir(p) {
        Ok(mut rd) => rd.next().is_none(),
        Err(_) => !p.exists(),
    }
}

/// Cria a pasta do projeto, as pastas padrão, a bíblia e o banco de recibos.
pub fn criar(novo: &NovoProjeto, pasta_padrao: &Path) -> Resultado<Projeto> {
    validar_nome(&novo.nome)?;
    let pasta = match &novo.pasta {
        Some(p) => {
            validar_pasta(p)?;
            p.trim().to_string()
        }
        None => nome_de_pasta(&novo.nome),
    };
    let pai = novo.pasta_pai.clone().unwrap_or_else(|| pasta_padrao.to_path_buf());
    let raiz = pai.join(&pasta);
    if !pasta_vazia_ou_inexistente(&raiz) {
        return Err(Erro::novo(
            "pasta_ja_existe",
            format!("Já existe uma pasta com arquivos em {}. Escolha outro nome ou outra pasta.", raiz.display()),
        ));
    }
    let agora = agora_iso();
    let biblia = Biblia {
        formato: FORMATO_ATUAL,
        id: id_aleatorio(8),
        nome: novo.nome.trim().to_string(),
        criado_em: agora.clone(),
        atualizado_em: agora,
        comercial: novo.comercial.unwrap_or(true),
        nivel: None,
        engine: engine_padrao(),
        conceito: novo.conceito.clone().unwrap_or_default(),
        guia_visual: GuiaVisual::default(),
        personagens: Vec::new(),
        mundo: Mundo::default(),
        extras: Map::new(),
    };
    validar(&biblia)?;
    for p in PASTAS_PADRAO {
        let d = raiz.join(p);
        std::fs::create_dir_all(&d).map_err(|e| Erro::io(&d, e))?;
    }
    let recibos = raiz.join(ARQUIVO_RECIBOS);
    std::fs::write(&recibos, b"").map_err(|e| Erro::io(&recibos, e))?;
    let arquivo = raiz.join(ARQUIVO_BIBLIA);
    write_json(&arquivo, &biblia).map_err(|e| Erro::io(&arquivo, e))?;
    let p = Projeto { raiz, biblia };
    // o guia para qualquer agente de IA (AGENTS.md e os arquivos de cada um) nasce com o projeto
    crate::guia::escrever(&p)?;
    Ok(p)
}

/// Abre um projeto pela pasta ou pelo próprio `game.project.json`.
pub fn abrir(caminho: &Path) -> Resultado<Projeto> {
    let raiz = if caminho.file_name().is_some_and(|n| n == ARQUIVO_BIBLIA) {
        caminho.parent().map(Path::to_path_buf).unwrap_or_default()
    } else {
        caminho.to_path_buf()
    };
    let arquivo = raiz.join(ARQUIVO_BIBLIA);
    let texto = std::fs::read(&arquivo)
        .map_err(|_| Erro::novo("nao_e_projeto", format!("{} não é um projeto da Fornalha: falta o {ARQUIVO_BIBLIA}.", raiz.display())))?;
    let biblia: Biblia = serde_json::from_slice(&texto)
        .map_err(|e| Erro::novo("biblia_invalida", format!("O {ARQUIVO_BIBLIA} de {} está com erro: {e}", raiz.display())))?;
    validar(&biblia)?;
    Ok(Projeto { raiz, biblia })
}

/// Aplica alterações (JSON Merge Patch) na bíblia, valida e grava.
pub fn atualizar(raiz: &Path, alteracoes: &Value) -> Resultado<Biblia> {
    let Value::Object(obj) = alteracoes else {
        return Err(Erro::argumento("As alterações precisam ser um objeto JSON."));
    };
    if let Some(c) = CAMPOS_PROTEGIDOS.iter().find(|c| obj.contains_key(**c)) {
        return Err(Erro::novo("campo_protegido", format!("O campo \"{c}\" é controlado pela Fornalha e não pode ser mudado.")));
    }
    let projeto = abrir(raiz)?;
    let mut v = serde_json::to_value(&projeto.biblia).map_err(|e| Erro::novo("biblia_invalida", e.to_string()))?;
    merge_patch(&mut v, alteracoes);
    let mut nova: Biblia = serde_json::from_value(v).map_err(|e| Erro::novo("biblia_invalida", format!("Alteração recusada: {e}")))?;
    nova.atualizado_em = agora_iso();
    validar(&nova)?;
    let arquivo = projeto.arquivo_biblia();
    write_json(&arquivo, &nova).map_err(|e| Erro::io(&arquivo, e))?;
    Ok(nova)
}
