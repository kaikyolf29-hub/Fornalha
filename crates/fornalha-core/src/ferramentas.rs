//! As ferramentas da Fornalha: uma lista só, usada pela janela, pela API local
//! e pelo servidor MCP (Claude Code, Codex ou qualquer agente).
//!
//! Os nomes seguem o plano (inglês, como `create_character` e `generate_3d`,
//! que chegam nas próximas fases); argumentos e textos ficam em português.

use std::path::PathBuf;

use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::consts::{API_VERSION, APP_NAME, APP_VERSION, FASE};
use crate::erro::{Erro, Resultado};
use crate::licencas::{self, situacao_no_catalogo};
use crate::niveis::{self, Nivel};
use crate::projeto::{self, Conceito, NovoProjeto};
use crate::recibos::{self, NovoRecibo};
use crate::servico::Fornalha;

/// Descrição de uma ferramenta (vira `tools/list` no MCP e `/fornalha/ferramentas` na API).
#[derive(Debug, Clone)]
pub struct Ferramenta {
    pub nome: &'static str,
    pub titulo: &'static str,
    pub descricao: &'static str,
    pub esquema: Value,
    /// Só lê (não muda nada no disco).
    pub so_leitura: bool,
}

fn projeto_opcional() -> Value {
    json!({"type": "string", "description": "Pasta do projeto. Se faltar, usa o projeto aberto agora."})
}

pub fn lista() -> Vec<Ferramenta> {
    vec![
        Ferramenta {
            nome: "get_status",
            titulo: "Estado da Fornalha",
            descricao: "Versão, fase do plano, endereço da API, projeto aberto, nível sugerido para a placa e se o Ignis (o cérebro local) está ligado.",
            esquema: json!({"type": "object", "properties": {}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "create_project",
            titulo: "Criar projeto de jogo",
            descricao: "Cria um projeto de jogo novo: a pasta padrão (GameDesign/, World/, Characters/, Enemies/, Items/, Weapons/, Animations/, Audio/, VFX/, Cutscenes/, UI/, Scripts/, blender/ e ai/), a bíblia do jogo (game.project.json) e o banco de recibos de licença. O projeto vira o projeto aberto. Por padrão é comercial: só entram modelos que deixam vender o jogo.",
            esquema: json!({
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Nome do jogo (até 80 letras)."},
                    "pasta_pai": {"type": "string", "description": "Onde criar. Padrão: a pasta de projetos da Fornalha (Documentos/Fornalha)."},
                    "pasta": {"type": "string", "description": "Nome da pasta. Padrão: tirado do nome do jogo."},
                    "comercial": {"type": "boolean", "description": "Jogo à venda (padrão: true). Em projeto comercial, modelo sem licença comercial fica bloqueado."},
                    "genero": {"type": "string", "description": "Ex.: action RPG, plataforma 3D."},
                    "estilo": {"type": "string", "description": "Ex.: estilizado, realista."},
                    "camera": {"type": "string", "description": "Ex.: terceira pessoa, isométrica."},
                    "plataformas": {"type": "array", "items": {"type": "string"}},
                    "historia": {"type": "string"},
                    "ambientacao": {"type": "string"}
                },
                "required": ["nome"]
            }),
            so_leitura: false,
        },
        Ferramenta {
            nome: "open_project",
            titulo: "Abrir projeto",
            descricao: "Abre um projeto existente (a pasta ou o game.project.json) e o torna o projeto aberto.",
            esquema: json!({
                "type": "object",
                "properties": {"caminho": {"type": "string", "description": "Pasta do projeto ou caminho do game.project.json."}},
                "required": ["caminho"]
            }),
            so_leitura: false,
        },
        Ferramenta {
            nome: "list_projects",
            titulo: "Projetos recentes",
            descricao: "Lista os projetos abertos recentemente e a pasta onde os projetos novos são criados.",
            esquema: json!({"type": "object", "properties": {}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "get_project",
            titulo: "Ler a bíblia do jogo",
            descricao: "Devolve a bíblia do jogo (game.project.json): conceito, guia visual, personagens e mundo. Use antes de gerar qualquer coisa, para nada sair fora do jogo.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional()}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "update_project",
            titulo: "Atualizar a bíblia do jogo",
            descricao: "Muda a bíblia do jogo com um JSON Merge Patch: objetos se mesclam, null apaga o campo. Campos: nome, comercial, nivel (leve, equilibrado, qualidade, maximo), engine, conceito {genero, estilo, plataformas, camera, historia, ambientacao, mecanicas, publico, duracao, referencias_visuais}, guia_visual {texto_de_estilo, paleta (#RRGGBB), traco, referencias [{arquivo, aprovada, nota}], evitar}, personagens [{id, nome, papel, roupa, arma, descricao}], mundo {areas [{id, nome, tipo, descricao}]}. Listas são trocadas inteiras. id, formato, criado_em e atualizado_em não mudam.",
            esquema: json!({
                "type": "object",
                "properties": {
                    "projeto": projeto_opcional(),
                    "alteracoes": {"type": "object", "description": "JSON Merge Patch aplicado na bíblia."}
                },
                "required": ["alteracoes"]
            }),
            so_leitura: false,
        },
        Ferramenta {
            nome: "detect_gpu",
            titulo: "Detectar a placa de vídeo",
            descricao: "Detecta a placa de vídeo (fabricante, memória, driver), a RAM e os aceleradores (CUDA, ROCm, Vulkan), e sugere o nível de qualidade.",
            esquema: json!({"type": "object", "properties": {"atualizar": {"type": "boolean", "description": "Detectar de novo em vez de usar a última detecção."}}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "list_quality_levels",
            titulo: "Níveis de qualidade",
            descricao: "Os 4 níveis (Leve, Equilibrado, Qualidade, Máximo) com o modelo que cada função usaria neste projeto e nesta máquina, o nível sugerido pela placa e o nível em uso.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional()}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "choose_model",
            titulo: "Escolher o modelo de uma função",
            descricao: "Pergunta ao roteador qual modelo usar para uma função (cerebro, imagem, 3d, rig, animacao, efeitos, musica, voz, boca, video), respeitando a licença do projeto e a placa. Explica cada modelo recusado.",
            esquema: json!({
                "type": "object",
                "properties": {
                    "funcao": {"type": "string", "enum": ["cerebro", "imagem", "3d", "rig", "animacao", "efeitos", "musica", "voz", "boca", "video"]},
                    "nivel": {"type": "string", "enum": ["leve", "equilibrado", "qualidade", "maximo"], "description": "Padrão: o nível em uso."},
                    "projeto": projeto_opcional()
                },
                "required": ["funcao"]
            }),
            so_leitura: true,
        },
        Ferramenta {
            nome: "list_models",
            titulo: "Catálogo de modelos e licenças",
            descricao: "O catálogo de modelos com licença, link da licença, uso comercial (sim, não, condicional), obrigações e a situação de cada um no projeto aberto.",
            esquema: json!({"type": "object", "properties": {"funcao": {"type": "string", "description": "Filtra por função."}, "projeto": projeto_opcional()}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "record_receipt",
            titulo: "Registrar recibo de licença",
            descricao: "Registra o recibo de licença de um arquivo gerado: modelo (id do catálogo, ou \"autoral\" para feito à mão), versão, prompt, referências, seed e data. Quem pediu é registrado sozinho. Recusa modelo sem licença comercial em projeto comercial. Nada entra na engine sem recibo.",
            esquema: json!({
                "type": "object",
                "properties": {
                    "projeto": projeto_opcional(),
                    "arquivo": {"type": "string", "description": "Caminho do arquivo dentro do projeto (ex.: Characters/heroi/heroi.glb)."},
                    "modelo": {"type": "string", "description": "Id do modelo no catálogo (list_models) ou \"autoral\"."},
                    "versao": {"type": "string"},
                    "prompt": {"type": "string"},
                    "referencias": {"type": "array", "items": {"type": "string"}},
                    "seed": {"type": "integer", "minimum": 0},
                    "parametros": {"type": "object", "description": "Outros parâmetros da geração."}
                },
                "required": ["arquivo", "modelo"]
            }),
            so_leitura: false,
        },
        Ferramenta {
            nome: "list_receipts",
            titulo: "Recibos de licença",
            descricao: "Lista os recibos de licença do projeto (todos, ou só os de um arquivo).",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"}}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "check_licenses",
            titulo: "Pendências antes de vender",
            descricao: "Confere os assets do projeto contra os recibos, como se o jogo fosse à venda: o que bloqueia a venda, o que precisa de atenção, assets sem recibo, alterados depois do recibo e recibos de arquivos que sumiram.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional()}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "export_credits",
            titulo: "Exportar créditos e licenças",
            descricao: "Gera o relatório de créditos e licenças (ai/creditos-e-licencas.md) para os créditos do jogo e para o formulário de conteúdo de IA da Steam.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional()}}),
            so_leitura: false,
        },
    ]
}

fn args<T: DeserializeOwned>(v: Value) -> Resultado<T> {
    let v = if v.is_null() { json!({}) } else { v };
    if !v.is_object() {
        return Err(Erro::argumento("Os argumentos precisam ser um objeto JSON."));
    }
    serde_json::from_value(v).map_err(|e| Erro::argumento(format!("Argumentos inválidos: {e}")))
}

fn json_de<T: serde::Serialize>(v: &T) -> Value {
    serde_json::to_value(v).unwrap_or(Value::Null)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ArgsCriar {
    nome: String,
    pasta_pai: Option<String>,
    pasta: Option<String>,
    comercial: Option<bool>,
    genero: Option<String>,
    estilo: Option<String>,
    camera: Option<String>,
    plataformas: Option<Vec<String>>,
    historia: Option<String>,
    ambientacao: Option<String>,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct ArgsProjeto {
    projeto: Option<String>,
}

#[derive(Deserialize)]
struct ArgsAbrir {
    caminho: String,
}

#[derive(Deserialize)]
struct ArgsAtualizar {
    projeto: Option<String>,
    alteracoes: Value,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct ArgsDetectar {
    atualizar: bool,
}

#[derive(Deserialize)]
struct ArgsEscolher {
    funcao: String,
    nivel: Option<String>,
    projeto: Option<String>,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct ArgsModelos {
    funcao: Option<String>,
    projeto: Option<String>,
}

#[derive(Deserialize)]
struct ArgsRecibo {
    projeto: Option<String>,
    arquivo: String,
    modelo: String,
    versao: Option<String>,
    prompt: Option<String>,
    #[serde(default)]
    referencias: Vec<String>,
    seed: Option<u64>,
    parametros: Option<Value>,
    /// Ignorado: quem pediu vem de quem chamou (o agente não se passa pela pessoa).
    #[serde(default, rename = "quem_pediu")]
    _quem_pediu: Option<String>,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct ArgsRecibos {
    projeto: Option<String>,
    arquivo: Option<String>,
}

fn nivel_arg(n: Option<&str>) -> Resultado<Option<Nivel>> {
    match n {
        None => Ok(None),
        Some(t) => Nivel::from_id(t)
            .map(Some)
            .ok_or_else(|| Erro::argumento(format!("Nível \"{t}\" não existe. Use leve, equilibrado, qualidade ou maximo."))),
    }
}

/// Atende uma ferramenta.
pub async fn chamar(f: &Fornalha, nome: &str, a: Value, quem: &str) -> Resultado<Value> {
    match nome {
        "get_status" => {
            let ignis = crate::ignis::consultar(f.porta_ignis()).await;
            let sugestao = f.sugestao().await;
            let atual = f.projeto_atual().and_then(|r| projeto::abrir(&r).ok());
            Ok(json!({
                "app": APP_NAME,
                "versao": APP_VERSION,
                "api": API_VERSION,
                "fase": FASE,
                "endereco_api": format!("http://127.0.0.1:{}", f.porta_api()),
                "endereco_mcp": format!("http://127.0.0.1:{}/mcp", f.porta_api()),
                "projeto_atual": atual.map(|p| json!({"raiz": p.raiz, "nome": p.biblia.nome, "comercial": p.biblia.comercial})),
                "nivel_sugerido": sugestao.nivel,
                "placa": sugestao.placa,
                "ignis": ignis,
            }))
        }
        "create_project" => {
            let a: ArgsCriar = args(a)?;
            let conceito = Conceito {
                genero: a.genero.unwrap_or_default(),
                estilo: a.estilo.unwrap_or_default(),
                camera: a.camera.unwrap_or_default(),
                plataformas: a.plataformas.unwrap_or_default(),
                historia: a.historia.unwrap_or_default(),
                ambientacao: a.ambientacao.unwrap_or_default(),
                ..Default::default()
            };
            let novo = NovoProjeto {
                nome: a.nome,
                pasta_pai: a.pasta_pai.map(|p| f.resolver_caminho(&p)),
                pasta: a.pasta,
                comercial: a.comercial,
                conceito: Some(conceito),
            };
            let p = projeto::criar(&novo, &f.pasta_projetos())?;
            f.usar_projeto(&p.raiz)?;
            Ok(json!({
                "raiz": p.raiz,
                "biblia": p.biblia,
                "proximo_passo": "Preencha o conceito e o guia visual com update_project antes de gerar assets.",
            }))
        }
        "open_project" => {
            let a: ArgsAbrir = args(a)?;
            let p = projeto::abrir(&f.resolver_caminho(&a.caminho))?;
            f.usar_projeto(&p.raiz)?;
            let n = recibos::listar(&p.raiz)?.len();
            Ok(json!({"raiz": p.raiz, "biblia": p.biblia, "recibos": n}))
        }
        "list_projects" => {
            let recentes: Vec<Value> = f
                .config()
                .projetos_recentes
                .iter()
                .map(|r| {
                    let p = projeto::abrir(r).ok();
                    json!({"raiz": r, "nome": p.as_ref().map(|p| p.biblia.nome.clone()), "existe": p.is_some()})
                })
                .collect();
            Ok(json!({"pasta_projetos": f.pasta_projetos(), "projeto_atual": f.projeto_atual(), "recentes": recentes}))
        }
        "get_project" => {
            let a: ArgsProjeto = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            Ok(json!({"raiz": p.raiz, "biblia": p.biblia}))
        }
        "update_project" => {
            let a: ArgsAtualizar = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            let b = projeto::atualizar(&p.raiz, &a.alteracoes)?;
            Ok(json!({"raiz": p.raiz, "biblia": b}))
        }
        "detect_gpu" => {
            let a: ArgsDetectar = args(a)?;
            let d = f.deteccao(a.atualizar).await;
            let sugestao = niveis::sugerir(&d);
            Ok(json!({
                "sistema": d.sistema,
                "arquitetura": d.arq,
                "placas": d.placas,
                "ram_total_mb": d.ram_total_mb,
                "ram_livre_mb": d.ram_livre_mb,
                "ferramentas": d.ferramentas,
                "sugestao": sugestao,
            }))
        }
        "list_quality_levels" => {
            let a: ArgsProjeto = args(a)?;
            let p = projeto_se_houver(f, a.projeto.as_deref())?;
            let ctx = f.contexto(p.as_ref()).await;
            let sugestao = f.sugestao().await;
            Ok(json!({
                "nivel_sugerido": sugestao.nivel,
                "motivo": sugestao.motivo,
                "nivel_em_uso": f.nivel_em_uso(p.as_ref()).await,
                "avisos": sugestao.avisos,
                "funcoes": f.catalogo.funcoes,
                "tabela": niveis::tabela(&f.catalogo, &ctx),
            }))
        }
        "choose_model" => {
            let a: ArgsEscolher = args(a)?;
            let nivel = nivel_arg(a.nivel.as_deref())?;
            let p = projeto_se_houver(f, a.projeto.as_deref())?;
            let nivel = match nivel {
                Some(n) => n,
                None => f.nivel_em_uso(p.as_ref()).await,
            };
            let ctx = f.contexto(p.as_ref()).await;
            Ok(json_de(&licencas::escolher(&f.catalogo, &a.funcao, nivel, &ctx)?))
        }
        "list_models" => {
            let a: ArgsModelos = args(a)?;
            let p = projeto_se_houver(f, a.projeto.as_deref())?;
            let ctx = f.contexto(p.as_ref()).await;
            let modelos: Vec<Value> = f
                .catalogo
                .modelos
                .iter()
                .filter(|m| a.funcao.as_deref().is_none_or(|x| m.funcao == x))
                .map(|m| {
                    let mut v = json_de(m);
                    v["situacao"] = json_de(&situacao_no_catalogo(&f.catalogo, m, &ctx));
                    v
                })
                .collect();
            Ok(json!({
                "comercial": ctx.comercial,
                "funcoes": f.catalogo.funcoes,
                "modelos": modelos,
                "dependencias": f.catalogo.dependencias,
                "grupos_de_aceite": f.catalogo.grupos_de_aceite,
            }))
        }
        "record_receipt" => {
            let a: ArgsRecibo = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            let ctx = f.contexto(Some(&p)).await;
            let novo = NovoRecibo {
                arquivo: a.arquivo,
                modelo: a.modelo,
                versao: a.versao,
                prompt: a.prompt,
                referencias: a.referencias,
                seed: a.seed,
                quem_pediu: Some(quem.to_string()),
                parametros: a.parametros,
            };
            let r = recibos::registrar(&p, &f.catalogo, &ctx, novo)?;
            Ok(json!({"recibo": r}))
        }
        "list_receipts" => {
            let a: ArgsRecibos = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            let alvo = a.arquivo.map(|x| x.replace('\\', "/"));
            let lista: Vec<_> = recibos::listar(&p.raiz)?.into_iter().filter(|r| alvo.as_deref().is_none_or(|x| r.arquivo == x)).collect();
            Ok(json!({"raiz": p.raiz, "recibos": lista}))
        }
        "check_licenses" => {
            let a: ArgsProjeto = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            let ctx = f.contexto(Some(&p)).await;
            let pend = recibos::pendencias(&p, &f.catalogo, &ctx)?;
            let mut v = json_de(&pend);
            v["pode_vender"] = json!(pend.pode_vender());
            v["comercial"] = json!(p.biblia.comercial);
            Ok(v)
        }
        "export_credits" => {
            let a: ArgsProjeto = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            let ctx = f.contexto(Some(&p)).await;
            Ok(json_de(&recibos::relatorio(&p, &f.catalogo, &ctx)?))
        }
        outro => Err(Erro::novo("ferramenta_desconhecida", format!("A ferramenta \"{outro}\" não existe."))),
    }
}

/// O projeto pedido, o atual, ou nenhum (para ferramentas que funcionam sem projeto).
fn projeto_se_houver(f: &Fornalha, caminho: Option<&str>) -> Resultado<Option<projeto::Projeto>> {
    match f.projeto(caminho) {
        Ok(p) => Ok(Some(p)),
        Err(e) if e.codigo == "sem_projeto" => Ok(None),
        Err(e) => Err(e),
    }
}

/// Usado pela janela: caminhos de projetos recentes que ainda existem.
pub fn recentes_existentes(f: &Fornalha) -> Vec<PathBuf> {
    f.config().projetos_recentes.into_iter().filter(|r| r.join(projeto::ARQUIVO_BIBLIA).is_file()).collect()
}
