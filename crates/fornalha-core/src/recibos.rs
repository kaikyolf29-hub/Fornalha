//! Recibo de licença por asset.
//!
//! Cada arquivo gerado ganha uma linha no banco do projeto (`ai/recibos.jsonl`):
//! modelo, versão, licença e link, prompt, referências, seed, data e quem pediu.
//! Com isso a Fornalha mostra o que impede a venda e exporta o relatório de
//! créditos e licenças (para os créditos do jogo e o formulário de IA da Steam).

use std::collections::{BTreeMap, HashMap};
use std::io::Write;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::erro::{Erro, Resultado};
use crate::licencas::{situacao_no_catalogo, Catalogo, ContextoRota, Situacao, UsoComercial};
use crate::projeto::{Projeto, ARQUIVO_BIBLIA, ARQUIVO_RECIBOS};
use crate::util::{agora_iso, id_aleatorio};

/// Asset feito pelo estúdio, sem IA.
pub const MODELO_AUTORAL: &str = "autoral";
pub const ARQUIVO_RELATORIO: &str = "ai/creditos-e-licencas.md";

/// Pastas de assets que precisam de recibo (código, documentos e arquivos de trabalho ficam de fora).
const PASTAS_DE_ASSETS: [&str; 10] =
    ["World", "Characters", "Enemies", "Items", "Weapons", "Animations", "Audio", "VFX", "Cutscenes", "UI"];
const EXTENSOES_DE_ASSETS: [&str; 24] = [
    "png", "jpg", "jpeg", "webp", "tga", "exr", "hdr", "bmp", "glb", "gltf", "fbx", "obj", "bvh", "wav", "ogg", "mp3", "flac", "opus",
    "mp4", "webm", "mov", "mkv", "vrm", "usdz",
];

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct NovoRecibo {
    /// Caminho do arquivo (relativo à pasta do projeto, ou absoluto dentro dela).
    pub arquivo: String,
    /// Id do modelo no catálogo, ou "autoral".
    pub modelo: String,
    pub versao: Option<String>,
    pub prompt: Option<String>,
    pub referencias: Vec<String>,
    pub seed: Option<u64>,
    /// "pessoa", "cerebro", "claude-code", "codex"...
    pub quem_pediu: Option<String>,
    /// Outros parâmetros da geração (passos, resolução...).
    pub parametros: Option<Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModeloNoRecibo {
    pub id: String,
    pub nome: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub versao: Option<String>,
    pub licenca: String,
    pub url_licenca: String,
    pub uso_comercial: UsoComercial,
    pub onde: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Recibo {
    pub id: String,
    pub arquivo: String,
    pub sha256: String,
    pub tamanho_bytes: u64,
    pub funcao: String,
    pub modelo: ModeloNoRecibo,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prompt: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub referencias: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub seed: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parametros: Option<Value>,
    pub criado_em: String,
    pub quem_pediu: String,
    /// O projeto era comercial quando o asset foi gerado.
    pub projeto_comercial: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub obrigacoes: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub avisos: Vec<String>,
}

impl Recibo {
    pub fn gerado_por_ia(&self) -> bool {
        self.funcao != MODELO_AUTORAL
    }
}

fn hash_arquivo(caminho: &Path) -> Resultado<(String, u64)> {
    let mut f = std::fs::File::open(caminho).map_err(|e| Erro::io(caminho, e))?;
    let mut h = Sha256::new();
    let n = std::io::copy(&mut f, &mut h).map_err(|e| Erro::io(caminho, e))?;
    Ok((hex::encode(h.finalize()), n))
}

/// Caminho relativo com "/" (igual no Windows e no Linux).
fn relativo(base: &Path, caminho: &Path) -> Option<String> {
    let rel = caminho.strip_prefix(base).ok()?;
    let partes: Vec<String> = rel
        .components()
        .map(|c| match c {
            Component::Normal(s) => Some(s.to_string_lossy().into_owned()),
            _ => None,
        })
        .collect::<Option<_>>()?;
    Some(partes.join("/"))
}

/// Resolve o arquivo pedido e garante que ele está dentro do projeto.
fn resolver(raiz: &Path, pedido: &str) -> Resultado<(PathBuf, String)> {
    let texto = pedido.trim();
    if texto.is_empty() {
        return Err(Erro::argumento("Diga qual arquivo recebe o recibo."));
    }
    let p = PathBuf::from(texto.replace('\\', std::path::MAIN_SEPARATOR_STR));
    let candidato = if p.is_absolute() { p } else { raiz.join(p) };
    let raiz_real = std::fs::canonicalize(raiz).map_err(|e| Erro::io(raiz, e))?;
    let real = std::fs::canonicalize(&candidato)
        .map_err(|_| Erro::novo("arquivo_nao_encontrado", format!("O arquivo {texto} não existe no projeto.")))?;
    let Some(rel) = relativo(&raiz_real, &real) else {
        return Err(Erro::novo("arquivo_fora_do_projeto", format!("{texto} está fora da pasta do projeto.")));
    };
    if !real.is_file() {
        return Err(Erro::novo("arquivo_invalido", format!("{texto} é uma pasta, não um arquivo.")));
    }
    if rel == ARQUIVO_BIBLIA || rel == ARQUIVO_RECIBOS || rel == ARQUIVO_RELATORIO {
        return Err(Erro::novo("arquivo_invalido", format!("{rel} é da própria Fornalha e não leva recibo.")));
    }
    Ok((real, rel))
}

fn modelo_autoral() -> ModeloNoRecibo {
    ModeloNoRecibo {
        id: MODELO_AUTORAL.into(),
        nome: "Feito pelo estúdio (sem IA)".into(),
        versao: None,
        licenca: "Do próprio estúdio".into(),
        url_licenca: String::new(),
        uso_comercial: UsoComercial::Sim,
        onde: "pessoa".into(),
    }
}

fn limpar_quem_pediu(q: Option<&str>) -> String {
    let q: String = q.unwrap_or("").trim().chars().filter(|c| !c.is_control()).take(60).collect();
    if q.is_empty() {
        "pessoa".into()
    } else {
        q
    }
}

/// Registra o recibo de um asset. Recusa o que a licença não deixa.
pub fn registrar(projeto: &Projeto, cat: &Catalogo, ctx: &ContextoRota, novo: NovoRecibo) -> Resultado<Recibo> {
    let (real, rel) = resolver(&projeto.raiz, &novo.arquivo)?;
    let modelo_id = novo.modelo.trim();
    let (funcao, mut modelo, obrigacoes, avisos) = if modelo_id == MODELO_AUTORAL {
        (MODELO_AUTORAL.to_string(), modelo_autoral(), Vec::new(), Vec::new())
    } else {
        let m = cat.modelo(modelo_id).ok_or_else(|| {
            Erro::novo("modelo_desconhecido", format!("O modelo \"{modelo_id}\" não está no catálogo da Fornalha (use list_models)."))
        })?;
        let avisos = match situacao_no_catalogo(cat, m, ctx) {
            Situacao::Liberado { avisos } => avisos,
            Situacao::Bloqueado { motivo } => return Err(Erro::novo("licenca_bloqueada", motivo)),
            Situacao::PrecisaAceite { texto, .. } => {
                return Err(Erro::novo("precisa_aceite", format!("{}: precisa do aceite da licença na Fornalha. {texto}", m.nome)))
            }
            Situacao::PrecisaReceita { teto_usd } => {
                return Err(Erro::novo(
                    "precisa_receita",
                    format!("{}: licença grátis só até US$ {teto_usd} por ano. Informe a receita do estúdio na Fornalha.", m.nome),
                ))
            }
        };
        let mr = ModeloNoRecibo {
            id: m.id.clone(),
            nome: m.nome.clone(),
            versao: None,
            licenca: m.licenca.clone(),
            url_licenca: m.url_licenca.clone(),
            uso_comercial: m.uso_comercial,
            onde: serde_json::to_value(m.onde).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_default(),
        };
        (m.funcao.clone(), mr, m.obrigacoes.clone(), avisos)
    };
    modelo.versao = novo.versao.filter(|v| !v.trim().is_empty());
    let (sha256, tamanho_bytes) = hash_arquivo(&real)?;
    let recibo = Recibo {
        id: format!("rec_{}", id_aleatorio(8)),
        arquivo: rel,
        sha256,
        tamanho_bytes,
        funcao,
        modelo,
        prompt: novo.prompt.filter(|p| !p.trim().is_empty()),
        referencias: novo.referencias,
        seed: novo.seed,
        parametros: novo.parametros,
        criado_em: agora_iso(),
        quem_pediu: limpar_quem_pediu(novo.quem_pediu.as_deref()),
        projeto_comercial: projeto.biblia.comercial,
        obrigacoes,
        avisos,
    };
    let banco = projeto.raiz.join(ARQUIVO_RECIBOS);
    let mut linha = serde_json::to_vec(&recibo).map_err(|e| Erro::novo("erro_interno", e.to_string()))?;
    linha.push(b'\n');
    let mut f = std::fs::OpenOptions::new().create(true).append(true).open(&banco).map_err(|e| Erro::io(&banco, e))?;
    f.write_all(&linha).map_err(|e| Erro::io(&banco, e))?;
    Ok(recibo)
}

/// Todos os recibos, na ordem em que foram feitos. Linhas corrompidas são puladas.
pub fn listar(raiz: &Path) -> Resultado<Vec<Recibo>> {
    let banco = raiz.join(ARQUIVO_RECIBOS);
    let texto = match std::fs::read_to_string(&banco) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => return Err(Erro::io(&banco, e)),
    };
    Ok(texto
        .lines()
        .enumerate()
        .filter(|(_, l)| !l.trim().is_empty())
        .filter_map(|(i, l)| match serde_json::from_str::<Recibo>(l) {
            Ok(r) => Some(r),
            Err(e) => {
                tracing::warn!("recibo ilegível na linha {} de {}: {e}", i + 1, banco.display());
                None
            }
        })
        .collect())
}

/// O recibo mais novo de cada arquivo.
pub fn atuais(raiz: &Path) -> Resultado<BTreeMap<String, Recibo>> {
    let mut m = BTreeMap::new();
    for r in listar(raiz)? {
        m.insert(r.arquivo.clone(), r);
    }
    Ok(m)
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Bloqueio {
    pub arquivo: String,
    pub modelo: String,
    pub motivo: String,
}

/// O que falta resolver antes de vender o jogo.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct Pendencias {
    /// Assets feitos com modelo sem licença comercial.
    pub bloqueiam_venda: Vec<Bloqueio>,
    /// Assets com licença que pede aceite ou receita.
    pub precisam_atencao: Vec<Bloqueio>,
    /// Assets nas pastas do jogo sem recibo nenhum.
    pub sem_recibo: Vec<String>,
    /// Mudaram depois do recibo (limpeza no Blender, edição à mão...). Só aviso.
    pub alterados: Vec<String>,
    /// Têm recibo, mas o arquivo sumiu. Só aviso.
    pub sumidos: Vec<String>,
}

impl Pendencias {
    pub fn pode_vender(&self) -> bool {
        self.bloqueiam_venda.is_empty() && self.precisam_atencao.is_empty() && self.sem_recibo.is_empty()
    }
}

/// Imagens e vídeos de conferência das bancadas (movimento, esqueleto, roupa): servem para a IA e a
/// pessoa olharem, não vão para o jogo e não precisam de recibo.
pub const MARCAS_DE_CONFERENCIA: [&str; 5] = [".movimento.", ".conferencia.", ".esqueleto.", ".vestido.", ".ver_"];

fn eh_asset(p: &Path) -> bool {
    let nome = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
    if MARCAS_DE_CONFERENCIA.iter().any(|m| nome.contains(m)) {
        return false;
    }
    p.extension().and_then(|e| e.to_str()).is_some_and(|e| EXTENSOES_DE_ASSETS.contains(&e.to_ascii_lowercase().as_str()))
}

fn listar_assets(raiz: &Path) -> Vec<String> {
    fn andar(base: &Path, dir: &Path, out: &mut Vec<String>) {
        let Ok(rd) = std::fs::read_dir(dir) else { return };
        for e in rd.flatten() {
            let p = e.path();
            match e.file_type() {
                Ok(t) if t.is_dir() => andar(base, &p, out),
                Ok(t) if t.is_file() && eh_asset(&p) => {
                    if let Some(r) = relativo(base, &p) {
                        out.push(r);
                    }
                }
                _ => {}
            }
        }
    }
    let mut out = Vec::new();
    for pasta in PASTAS_DE_ASSETS {
        andar(raiz, &raiz.join(pasta), &mut out);
    }
    out.sort();
    out
}

/// Textura que a engine (Godot/Erethea) tirou de dentro de um `.glb` ao importar
/// (`pasta/nome_Textura.png` ao lado de `pasta/nome.glb`): o recibo do `.glb` vale para ela.
fn derivado_de_glb(arquivo: &str, atuais: &BTreeMap<String, Recibo>) -> bool {
    let (pasta, nome) = arquivo.rsplit_once('/').unwrap_or(("", arquivo));
    let ext = nome.rsplit('.').next().unwrap_or("").to_lowercase();
    if !["png", "jpg", "jpeg", "webp"].contains(&ext.as_str()) {
        return false;
    }
    atuais.keys().any(|k| {
        let Some(base) = k.strip_suffix(".glb") else { return false };
        let (p2, n2) = base.rsplit_once('/').unwrap_or(("", base));
        p2 == pasta && nome.starts_with(&format!("{n2}_"))
    })
}

/// Confere os assets do projeto contra os recibos, como se ele fosse à venda.
pub fn pendencias(projeto: &Projeto, cat: &Catalogo, ctx: &ContextoRota) -> Resultado<Pendencias> {
    let atuais = atuais(&projeto.raiz)?;
    let venda = ContextoRota { comercial: true, ..ctx.clone() };
    let mut p = Pendencias::default();
    for (arquivo, r) in &atuais {
        let caminho = projeto.raiz.join(arquivo);
        if !caminho.is_file() {
            p.sumidos.push(arquivo.clone());
            continue;
        }
        if hash_arquivo(&caminho).map(|(h, _)| h != r.sha256).unwrap_or(false) {
            p.alterados.push(arquivo.clone());
        }
        if !r.gerado_por_ia() {
            continue;
        }
        let situacao = match cat.modelo(&r.modelo.id) {
            Some(m) => situacao_no_catalogo(cat, m, &venda),
            None if r.modelo.uso_comercial == UsoComercial::Nao => {
                Situacao::Bloqueado { motivo: format!("{} não tem licença comercial ({}).", r.modelo.nome, r.modelo.licenca) }
            }
            None => Situacao::Liberado { avisos: vec![] },
        };
        let bloqueio = |motivo: String| Bloqueio { arquivo: arquivo.clone(), modelo: r.modelo.nome.clone(), motivo };
        match situacao {
            Situacao::Liberado { .. } => {}
            Situacao::Bloqueado { motivo } => p.bloqueiam_venda.push(bloqueio(motivo)),
            Situacao::PrecisaAceite { texto, .. } => p.precisam_atencao.push(bloqueio(format!("Precisa do aceite da licença. {texto}"))),
            Situacao::PrecisaReceita { teto_usd } => {
                p.precisam_atencao.push(bloqueio(format!("Licença grátis só até US$ {teto_usd} por ano: informe a receita do estúdio.")))
            }
        }
    }
    p.sem_recibo = listar_assets(&projeto.raiz).into_iter().filter(|a| !atuais.contains_key(a) && !derivado_de_glb(a, &atuais)).collect();
    Ok(p)
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct LinhaModelo {
    pub id: String,
    pub nome: String,
    pub licenca: String,
    pub url_licenca: String,
    pub assets: usize,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Relatorio {
    pub markdown: String,
    pub arquivo: PathBuf,
    pub assets_com_ia: usize,
    pub assets_autorais: usize,
    pub modelos: Vec<LinhaModelo>,
    pub pendencias: Pendencias,
}

fn nome_tipo(funcao: &str, cat: &Catalogo) -> String {
    cat.funcao(funcao).map(|f| f.nome.clone()).unwrap_or_else(|| funcao.to_string())
}

/// Monta e grava o relatório de créditos e licenças (`ai/creditos-e-licencas.md`).
pub fn relatorio(projeto: &Projeto, cat: &Catalogo, ctx: &ContextoRota) -> Resultado<Relatorio> {
    let atuais: Vec<Recibo> = atuais(&projeto.raiz)?.into_values().filter(|r| projeto.raiz.join(&r.arquivo).is_file()).collect();
    let pend = pendencias(projeto, cat, ctx)?;
    let com_ia: Vec<&Recibo> = atuais.iter().filter(|r| r.gerado_por_ia()).collect();
    let autorais: Vec<&Recibo> = atuais.iter().filter(|r| !r.gerado_por_ia()).collect();

    let mut por_modelo: BTreeMap<String, LinhaModelo> = BTreeMap::new();
    let mut obrigacoes: Vec<String> = Vec::new();
    for r in &com_ia {
        let l = por_modelo.entry(r.modelo.id.clone()).or_insert_with(|| LinhaModelo {
            id: r.modelo.id.clone(),
            nome: r.modelo.nome.clone(),
            licenca: r.modelo.licenca.clone(),
            url_licenca: r.modelo.url_licenca.clone(),
            assets: 0,
        });
        l.assets += 1;
        for o in &r.obrigacoes {
            if !obrigacoes.contains(o) {
                obrigacoes.push(o.clone());
            }
        }
    }
    let modelos: Vec<LinhaModelo> = por_modelo.into_values().collect();

    let b = &projeto.biblia;
    let mut md = String::new();
    md.push_str(&format!("# Créditos e licenças: {}\n\n", b.nome));
    md.push_str(&format!(
        "Gerado pela Fornalha em {}. Projeto {}.\n\n",
        agora_iso(),
        if b.comercial { "comercial" } else { "não comercial (teste)" }
    ));
    md.push_str("## Modelos de IA usados\n\n");
    if modelos.is_empty() {
        md.push_str("Nenhum asset gerado por IA até agora.\n\n");
    } else {
        md.push_str("| Modelo | Licença | Assets |\n|---|---|---|\n");
        for m in &modelos {
            md.push_str(&format!("| {} | [{}]({}) | {} |\n", m.nome, m.licenca, m.url_licenca, m.assets));
        }
        md.push('\n');
    }
    md.push_str("## Obrigações\n\n");
    if obrigacoes.is_empty() {
        md.push_str("Nenhuma obrigação extra de licença.\n\n");
    } else {
        for o in &obrigacoes {
            md.push_str(&format!("- {o}\n"));
        }
        md.push('\n');
    }
    md.push_str("## Conteúdo gerado por IA (para o formulário de IA da Steam)\n\n");
    md.push_str(&format!(
        "Conteúdo pré-gerado com IA durante o desenvolvimento: {} assets. Nenhum conteúdo é gerado por IA enquanto o jogo roda.\n\n",
        com_ia.len()
    ));
    let mut por_tipo: HashMap<String, Vec<&Recibo>> = HashMap::new();
    for r in &com_ia {
        por_tipo.entry(nome_tipo(&r.funcao, cat)).or_default().push(r);
    }
    let mut tipos: Vec<_> = por_tipo.into_iter().collect();
    tipos.sort_by(|a, b| a.0.cmp(&b.0));
    for (tipo, lista) in tipos {
        md.push_str(&format!("### {tipo} ({})\n\n", lista.len()));
        for r in lista {
            md.push_str(&format!("- `{}`: {}\n", r.arquivo, r.modelo.nome));
        }
        md.push('\n');
    }
    md.push_str(&format!("## Feito pelo estúdio, sem IA ({})\n\n", autorais.len()));
    for r in &autorais {
        md.push_str(&format!("- `{}`\n", r.arquivo));
    }
    if !autorais.is_empty() {
        md.push('\n');
    }
    md.push_str("## Antes de vender\n\n");
    if pend.pode_vender() {
        md.push_str("Tudo certo: todos os assets têm recibo e licença que deixa vender.\n");
    } else {
        for x in &pend.bloqueiam_venda {
            md.push_str(&format!("- Bloqueia a venda: `{}` ({}). {}\n", x.arquivo, x.modelo, x.motivo));
        }
        for x in &pend.precisam_atencao {
            md.push_str(&format!("- Precisa de atenção: `{}` ({}). {}\n", x.arquivo, x.modelo, x.motivo));
        }
        for a in &pend.sem_recibo {
            md.push_str(&format!("- Sem recibo: `{a}`\n"));
        }
    }
    let arquivo = projeto.raiz.join(ARQUIVO_RELATORIO);
    crate::paths::write_atomic(&arquivo, md.as_bytes()).map_err(|e| Erro::io(&arquivo, e))?;
    Ok(Relatorio { markdown: md, arquivo, assets_com_ia: com_ia.len(), assets_autorais: autorais.len(), modelos, pendencias: pend })
}

#[cfg(test)]
mod testes_conferencia {
    use super::*;

    #[test]
    fn imagens_das_bancadas_nao_sao_asset() {
        for n in [
            "Characters/a/a.movimento.mp4",
            "Characters/a/a.conferencia.png",
            "Characters/a/a.esqueleto.png",
            "Characters/a/a.vestido.png",
            "Characters/a/a.ver_soco.lado.png",
        ] {
            assert!(!eh_asset(Path::new(n)), "{n}");
        }
        assert!(eh_asset(Path::new("Characters/a/a.glb")));
    }
}
