//! Catálogo de modelos com licença e o roteador de licenças.
//!
//! Licença é regra do app, não lembrete: num projeto marcado como comercial, o
//! roteador não deixa um modelo sem licença comercial tocar no projeto.

use std::collections::{BTreeMap, HashSet};

use serde::{Deserialize, Serialize};

use crate::erro::{Erro, Resultado};
use crate::niveis::Nivel;

const CATALOGO_EMBUTIDO: &str = include_str!("../manifest/modelos.json");

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum UsoComercial {
    Sim,
    Nao,
    Condicional,
}

/// Onde o modelo roda.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Onde {
    /// No Ignis (cérebro, transcrição).
    Ignis,
    /// No ComfyUI sem janela.
    Comfyui,
    /// No stable-diffusion.cpp pelo Vulkan (AMD/Intel sem CUDA nem ROCm, inclusive a RX 580).
    Vulkan,
    /// Workers Python próprios (3D, rig, animação).
    Worker,
    /// Blender em segundo plano.
    Blender,
    /// Biblioteca própria (capturas).
    Biblioteca,
    /// Serviço pago, só no modo turbo.
    Api,
    /// Gerador da própria Fornalha (sem modelo de IA, sem placa).
    Fornalha,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Modelo {
    pub id: String,
    pub nome: String,
    pub funcao: String,
    pub onde: Onde,
    pub licenca: String,
    pub url_licenca: String,
    pub uso_comercial: UsoComercial,
    /// Grupo de licença que a pessoa precisa aceitar antes do uso comercial.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub aceite: Option<String>,
    /// Receita anual (US$) a partir da qual a licença deixa de valer de graça.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub teto_receita_usd: Option<u64>,
    #[serde(default)]
    pub requer_cuda: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vram_mb: Option<u64>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub dependencias: Vec<String>,
    /// O que o asset leva junto (crédito, marca d'água...).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub obrigacoes: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nota: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Dependencia {
    pub nome: String,
    pub licenca: String,
    pub url_licenca: String,
    pub uso_comercial: UsoComercial,
    pub como_resolver: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GrupoAceite {
    pub nome: String,
    pub texto: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Funcao {
    pub id: String,
    pub nome: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Catalogo {
    pub formato: u32,
    pub atualizado_em: String,
    #[serde(default)]
    pub nota: String,
    pub funcoes: Vec<Funcao>,
    /// nível → função → modelos em ordem de preferência.
    pub niveis: BTreeMap<String, BTreeMap<String, Vec<String>>>,
    pub modelos: Vec<Modelo>,
    #[serde(default)]
    pub dependencias: BTreeMap<String, Dependencia>,
    #[serde(default)]
    pub grupos_de_aceite: BTreeMap<String, GrupoAceite>,
}

impl Catalogo {
    /// O catálogo que vem dentro do app.
    pub fn embutido() -> Self {
        serde_json::from_str(CATALOGO_EMBUTIDO).expect("manifest/modelos.json embutido é válido (testado)")
    }

    pub fn modelo(&self, id: &str) -> Option<&Modelo> {
        self.modelos.iter().find(|m| m.id == id)
    }

    pub fn funcao(&self, id: &str) -> Option<&Funcao> {
        self.funcoes.iter().find(|f| f.id == id)
    }

    /// Modelos de um nível para uma função, na ordem de preferência.
    pub fn candidatos(&self, nivel: Nivel, funcao: &str) -> Vec<&Modelo> {
        self.niveis
            .get(nivel.id())
            .and_then(|f| f.get(funcao))
            .map(|ids| ids.iter().filter_map(|id| self.modelo(id)).collect())
            .unwrap_or_default()
    }

    /// Lista o que está errado no catálogo (vazio = tudo certo).
    pub fn conferir(&self) -> Vec<String> {
        let mut erros = Vec::new();
        let mut ids = HashSet::new();
        let funcoes: HashSet<&str> = self.funcoes.iter().map(|f| f.id.as_str()).collect();
        for m in &self.modelos {
            if !ids.insert(m.id.as_str()) {
                erros.push(format!("modelo repetido: {}", m.id));
            }
            if !funcoes.contains(m.funcao.as_str()) {
                erros.push(format!("{}: função {} não existe", m.id, m.funcao));
            }
            if !(m.url_licenca.starts_with("https://") || m.url_licenca.starts_with("http://mocap.cs.cmu.edu/")) {
                erros.push(format!("{}: link da licença precisa ser https", m.id));
            }
            let tem_condicao = m.aceite.is_some() || m.teto_receita_usd.is_some();
            if (m.uso_comercial == UsoComercial::Condicional) != tem_condicao {
                erros.push(format!("{}: 'condicional' precisa de aceite ou teto de receita (e só ele)", m.id));
            }
            if let Some(g) = &m.aceite {
                if !self.grupos_de_aceite.contains_key(g) {
                    erros.push(format!("{}: grupo de aceite {g} não existe", m.id));
                }
            }
            for d in &m.dependencias {
                if !self.dependencias.contains_key(d) {
                    erros.push(format!("{}: dependência {d} não existe", m.id));
                }
            }
        }
        for n in Nivel::TODOS {
            let Some(por_funcao) = self.niveis.get(n.id()) else {
                erros.push(format!("falta o nível {}", n.id()));
                continue;
            };
            for f in &self.funcoes {
                if !por_funcao.contains_key(&f.id) {
                    erros.push(format!("nível {} sem a função {}", n.id(), f.id));
                }
            }
            for (funcao, lista) in por_funcao {
                if !funcoes.contains(funcao.as_str()) {
                    erros.push(format!("nível {}: função {funcao} não existe", n.id()));
                }
                for id in lista {
                    match self.modelo(id) {
                        None => erros.push(format!("nível {}/{funcao}: modelo {id} não existe", n.id())),
                        Some(m) if &m.funcao != funcao => erros.push(format!("nível {}/{funcao}: {id} é da função {}", n.id(), m.funcao)),
                        Some(m) if m.uso_comercial == UsoComercial::Nao => {
                            erros.push(format!("nível {}/{funcao}: {id} não tem licença comercial", n.id()))
                        }
                        Some(m) if m.onde == Onde::Api => {
                            erros.push(format!("nível {}/{funcao}: {id} é serviço pago (só modo turbo)", n.id()))
                        }
                        _ => {}
                    }
                }
            }
        }
        erros
    }
}

/// O que o roteador precisa saber sobre o projeto, o estúdio e a máquina.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ContextoRota {
    /// Projeto à venda.
    pub comercial: bool,
    /// Placa NVIDIA com CUDA.
    pub cuda: bool,
    /// Receita anual do estúdio em US$ (perguntada uma vez).
    pub receita_anual_usd: Option<u64>,
    /// Grupos de licença que a pessoa aceitou.
    pub licencas_aceitas: Vec<String>,
    /// Dependências sem licença comercial que a Fornalha comprovou, nesta máquina,
    /// que o worker do modelo não usa (ex.: o TRELLIS.2 verificado sem o nvdiffrast).
    #[serde(default)]
    pub sem_dependencias: Vec<String>,
}

/// Pode usar este modelo neste projeto?
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "situacao", rename_all = "snake_case")]
pub enum Situacao {
    Liberado { avisos: Vec<String> },
    Bloqueado { motivo: String },
    PrecisaAceite { grupo: String, texto: String },
    PrecisaReceita { teto_usd: u64 },
}

/// Situação da licença de um modelo (sem olhar a placa).
pub fn situacao_no_catalogo(cat: &Catalogo, m: &Modelo, ctx: &ContextoRota) -> Situacao {
    let mut avisos = Vec::new();
    if !ctx.comercial {
        if m.uso_comercial != UsoComercial::Sim {
            avisos.push(format!("{} não pode ir para um jogo à venda: o projeto está marcado como não comercial.", m.nome));
        }
        return Situacao::Liberado { avisos };
    }
    if m.uso_comercial == UsoComercial::Nao {
        return Situacao::Bloqueado { motivo: format!("{} não tem licença comercial ({}).", m.nome, m.licenca) };
    }
    for d in &m.dependencias {
        let Some(dep) = cat.dependencias.get(d) else { continue };
        if ctx.sem_dependencias.iter().any(|s| s == d) {
            avisos.push(format!("{} roda sem o {} nesta máquina (verificado pela Fornalha).", m.nome, dep.nome));
            continue;
        }
        if dep.uso_comercial == UsoComercial::Nao {
            return Situacao::Bloqueado {
                motivo: format!("{} usa o {} ({}), que não permite uso comercial. {}", m.nome, dep.nome, dep.licenca, dep.como_resolver),
            };
        }
    }
    if let Some(g) = &m.aceite {
        if !ctx.licencas_aceitas.iter().any(|a| a == g) {
            let texto = cat.grupos_de_aceite.get(g).map(|x| x.texto.clone()).unwrap_or_default();
            return Situacao::PrecisaAceite { grupo: g.clone(), texto };
        }
    }
    if let Some(teto) = m.teto_receita_usd {
        match ctx.receita_anual_usd {
            None => return Situacao::PrecisaReceita { teto_usd: teto },
            Some(r) if r >= teto => {
                return Situacao::Bloqueado {
                    motivo: format!("A receita do estúdio passou do limite de US$ {teto} da licença do {}.", m.nome),
                }
            }
            Some(_) => avisos.push(format!("{}: grátis só até US$ {teto} de receita por ano.", m.nome)),
        }
    }
    Situacao::Liberado { avisos }
}

/// Atalho para `situacao_no_catalogo` com o catálogo embutido.
pub fn situacao(m: &Modelo, ctx: &ContextoRota) -> Situacao {
    situacao_no_catalogo(&Catalogo::embutido(), m, ctx)
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Recusa {
    pub modelo: String,
    pub motivo: String,
}

/// Resultado do roteador para uma função num nível.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Escolha {
    pub funcao: String,
    pub nivel: Nivel,
    pub modelo: Option<Modelo>,
    /// Nível de onde o modelo saiu (pode ser mais baixo que o pedido).
    pub nivel_usado: Option<Nivel>,
    pub recusados: Vec<Recusa>,
    pub avisos: Vec<String>,
    pub obrigacoes: Vec<String>,
}

fn motivo_recusa(s: &Situacao) -> Option<String> {
    match s {
        Situacao::Liberado { .. } => None,
        Situacao::Bloqueado { motivo } => Some(motivo.clone()),
        Situacao::PrecisaAceite { texto, .. } => Some(format!("Precisa do seu aceite da licença. {texto}")),
        Situacao::PrecisaReceita { teto_usd } => {
            Some(format!("Licença grátis só até US$ {teto_usd} de receita por ano: informe a receita do estúdio."))
        }
    }
}

/// Escolhe o modelo de uma função: o primeiro liberado do nível pedido; se não
/// houver, desce de nível. Placa sem CUDA usa a opção que não depende de CUDA.
pub fn escolher(cat: &Catalogo, funcao: &str, nivel: Nivel, ctx: &ContextoRota) -> Resultado<Escolha> {
    if cat.funcao(funcao).is_none() {
        let validas: Vec<&str> = cat.funcoes.iter().map(|f| f.id.as_str()).collect();
        return Err(Erro::novo("funcao_desconhecida", format!("Função \"{funcao}\" não existe. Use uma destas: {}.", validas.join(", "))));
    }
    let mut escolha = Escolha {
        funcao: funcao.to_string(),
        nivel,
        modelo: None,
        nivel_usado: None,
        recusados: Vec::new(),
        avisos: Vec::new(),
        obrigacoes: Vec::new(),
    };
    let mut vistos = HashSet::new();
    for n in Nivel::TODOS.into_iter().rev().filter(|n| *n <= nivel) {
        for m in cat.candidatos(n, funcao) {
            if !vistos.insert(m.id.clone()) {
                continue;
            }
            let motivo = if m.requer_cuda && !ctx.cuda {
                Some(format!("{} precisa de placa NVIDIA (CUDA); o porte para AMD e Intel ainda não está pronto.", m.nome))
            } else {
                motivo_recusa(&situacao_no_catalogo(cat, m, ctx))
            };
            if let Some(motivo) = motivo {
                escolha.recusados.push(Recusa { modelo: m.id.clone(), motivo });
                continue;
            }
            if let Situacao::Liberado { avisos } = situacao_no_catalogo(cat, m, ctx) {
                escolha.avisos.extend(avisos);
            }
            if n != nivel {
                escolha.avisos.push(format!("Nenhuma opção do nível {} serviu; usando a do nível {}.", nome_nivel(nivel), nome_nivel(n)));
            }
            escolha.obrigacoes = m.obrigacoes.clone();
            escolha.modelo = Some(m.clone());
            escolha.nivel_usado = Some(n);
            return Ok(escolha);
        }
    }
    Ok(escolha)
}

fn nome_nivel(n: Nivel) -> &'static str {
    n.nome()
}
