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
use crate::geracao;
use crate::licencas::{self, situacao_no_catalogo};
use crate::niveis::{self, Nivel};
use crate::projeto::{self, Conceito, NovoProjeto};
use crate::recibos::{self, NovoRecibo};
use crate::servico::Fornalha;

#[derive(Deserialize)]
struct ArgsConceito {
    projeto: Option<String>,
    descricao: String,
    arquivo: Option<String>,
    seed: Option<u64>,
}

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
        Ferramenta {
            nome: "create_character",
            titulo: "Criar personagem ou inimigo",
            descricao: "Cria um personagem do zero: a ficha (o cérebro do Ignis completa o que faltar, coerente com a bíblia), a imagem de conceito (Ignis), o modelo 3D com o esqueleto padrão e 9 animações (parado, andar, correr, pular, atacar, defender, esquivar, dano, morrer), a arma na mão, prévia e folha de modelo, e a fala dublada com a curva da boca. Grava em Characters/<id>/ (ou Enemies/<id>/ se o papel for inimigo ou chefe), atualiza a bíblia e registra os recibos. Com testar_na_engine, monta o jogo e roda o teste (o inimigo novo aparece na frente do jogador). Pode levar alguns minutos.",
            esquema: json!({
                "type": "object",
                "properties": {
                    "projeto": projeto_opcional(),
                    "nome": {"type": "string"},
                    "papel": {"type": "string", "description": "protagonista, aliado, inimigo, chefe..."},
                    "descricao": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["humano", "elfo", "anao", "orc", "goblin", "esqueleto", "demonio"]},
                    "arma": {"type": "string", "enum": ["espada", "machado", "lanca", "martelo", "adaga", "cajado", "escudo", "nenhuma"]},
                    "armadura": {"type": "string", "enum": ["nenhuma", "leve", "pesada"]},
                    "porte": {"type": "string", "enum": ["magro", "medio", "forte"]},
                    "cor_roupa": {"type": "string"}, "cor_roupa_secundaria": {"type": "string"}, "cor_pele": {"type": "string"}, "cor_cabelo": {"type": "string"},
                    "capa": {"type": "boolean"}, "capuz": {"type": "boolean"},
                    "fala": {"type": "string", "description": "Frase para dublar em português."},
                    "conceito": {"type": "boolean", "description": "Gerar a imagem de conceito (padrão: sim, se o Ignis tiver imagem)."},
                    "video": {"type": "boolean", "description": "Vídeo curto das animações."},
                    "testar_na_engine": {"type": "boolean", "description": "Montar na engine e rodar o teste no fim."},
                    "seed": {"type": "integer", "minimum": 0}
                }
            }),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_concept",
            titulo: "Gerar imagem de conceito",
            descricao: "Gera uma imagem de conceito pelo Ignis (Z-Image Turbo, licença Apache 2.0) com o guia visual da bíblia junto. Grava em ai/conceitos/ (ou no caminho pedido) com recibo.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "descricao": {"type": "string"}, "arquivo": {"type": "string"}, "seed": {"type": "integer", "minimum": 0}}, "required": ["descricao"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_3d",
            titulo: "Gerar modelo 3D (arma, objeto, de uma imagem) ou limpar malha",
            descricao: "Gera uma arma (espada, machado, lanca, martelo, adaga, cajado, escudo) ou um objeto (barril, caixa, bau, arvore, pedra, casa, tocha, cerca, pocao) low-poly no estilo do jogo, com colisão simples e prévia; com imagem, faz o 3D da imagem pelo TRELLIS.2 (placa NVIDIA; textura assada no Blender, sem o nvdiffrast); ou, com entrada, limpa uma malha de fora (escala real, pivô nos pés, decimar, UV e colisão). Personagens: use create_character.",
            esquema: json!({"type": "object", "properties": {
                "projeto": projeto_opcional(),
                "tipo": {"type": "string", "enum": ["arma", "objeto"]},
                "modelo": {"type": "string"}, "nome": {"type": "string"},
                "cores": {"type": "object", "description": "ex.: {\"metal\": \"#aabbcc\", \"madeira\": \"#553311\"}"},
                "entrada": {"type": "string", "description": "Malha de fora (.glb, .gltf, .obj, .fbx, .ply) para limpar."},
                "imagem": {"type": "string", "description": "Imagem do projeto para virar 3D com o TRELLIS.2 (precisa de placa NVIDIA e do modelo instalado)."},
                "altura_m": {"type": "number"}, "triangulos_max": {"type": "integer"}, "seed": {"type": "integer", "minimum": 0}
            }}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "create_material",
            titulo: "Aplicar materiais e cores",
            descricao: "Recolore os materiais de um modelo pela paleta do guia visual (em ordem) ou pelas cores pedidas por nome de material.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"}, "cores": {"type": "object"}, "rugosidade": {"type": "number"}}, "required": ["arquivo"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "create_skeleton",
            titulo: "Pôr esqueleto e animações numa malha",
            descricao: "Uma malha de personagem sem esqueleto (do TRELLIS.2, Hunyuan3D ou feita à mão) ganha limpeza, o esqueleto padrão (nomes do perfil humanoide da Godot), pesos automáticos e as animações da biblioteca. Com criatura: true (bicho, monstro que não é humanoide), o esqueleto sai do UniRig (placa NVIDIA), sem as animações da biblioteca.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "entrada": {"type": "string"}, "nome": {"type": "string"}, "altura_m": {"type": "number"}, "girar_graus": {"type": "number"}, "inimigo": {"type": "boolean"}, "criatura": {"type": "boolean"}, "animacoes": {"type": "array", "items": {"type": "string"}}}, "required": ["entrada"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_animation",
            titulo: "Gerar animações",
            descricao: "Gera (de novo) as animações da biblioteca num personagem com o esqueleto padrão: parado, andar, correr, pular, atacar, defender, esquivar, dano, morrer (todas, ou as pedidas). Com descricao (ex.: \"acena com a mão direita e depois cruza os braços\"), cria uma animação nova pelo HY-Motion (placa NVIDIA e aceite da licença da Tencent na janela) e mantém as outras.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"},
                "animacoes": {"type": "array", "items": {"type": "string", "enum": ["parado", "andar", "correr", "pular", "atacar", "defender", "esquivar", "dano", "morrer"]}},
                "descricao": {"type": "string", "description": "Movimento em texto (HY-Motion)."}, "nome_animacao": {"type": "string"},
                "segundos": {"type": "number", "minimum": 1, "maximum": 12}, "laco": {"type": "boolean"}, "seed": {"type": "integer", "minimum": 0}}, "required": ["arquivo"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "retarget_animation",
            titulo: "Copiar animações entre personagens",
            descricao: "Copia as animações de um personagem para outro com o mesmo esqueleto padrão.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string", "description": "Personagem que recebe."}, "origem": {"type": "string"}, "animacoes": {"type": "array", "items": {"type": "string"}}}, "required": ["arquivo", "origem"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_sfx",
            titulo: "Gerar efeitos sonoros",
            descricao: "Gera os efeitos por evento em Audio/efeitos/ (passos na grama, pedra, água e madeira, golpes, impacto, espada, pulo, aterrissagem, dano, morte, moeda, clique), com variações. Sem efeitos pedidos, gera o pacote que o jogo usa.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "efeitos": {"type": "array", "items": {"type": "string"}}, "variacoes": {"type": "integer", "minimum": 1, "maximum": 8}}}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_music",
            titulo: "Gerar música em loop",
            descricao: "Compõe a trilha de uma área ou situação (exploracao, vila, floresta, combate, chefe, masmorra), pronta para tocar em loop, em Audio/musica/.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "situacao": {"type": "string"}, "compassos": {"type": "integer", "minimum": 1, "maximum": 64}, "seed": {"type": "integer", "minimum": 0}}, "required": ["situacao"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_voice",
            titulo: "Gerar fala dublada",
            descricao: "Dubla uma fala em português pelo Ignis (Chatterbox, licença MIT, pode ir para jogo à venda) e grava a curva de abertura da boca para a animação.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "texto": {"type": "string"}, "personagem": {"type": "string"}, "idioma": {"type": "string"}, "seed": {"type": "integer", "minimum": 0}}, "required": ["texto"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_blockout",
            titulo: "Gerar o mundo em blockout",
            descricao: "Transforma as áreas da bíblia (vila, floresta, montanha, masmorra, arena, caverna, castelo...) num mapa em blocos testável na engine, com colisão, caminhos entre as áreas e pontos de nascimento do jogador e dos inimigos. Grava World/blockout.glb, a prévia e o mapa visto de cima.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "areas": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "tipo": {"type": "string"}, "nome": {"type": "string"}}}}, "seed": {"type": "integer", "minimum": 0}}}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "generate_code",
            titulo: "Gerar o código do jogo",
            descricao: "Escreve o código do jogo para a engine da bíblia (Godot ou Erethea Engine): jogador em terceira pessoa, inimigo com IA básica, HUD, sons, teste automático e o plugin da ponte com a Fornalha. Não sobrescreve script que você editou.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional()}}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "import_to_engine",
            titulo: "Levar para a engine e montar as cenas",
            descricao: "Importa os assets na engine (Godot ou Erethea) e monta as cenas: personagem com as animações ligadas e câmera, inimigos com IA nos pontos do mapa, arma na mão, mundo com luz e céu, HUD e música. Cena principal: principal.tscn.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "jogador": {"type": "string"}, "inimigo_perto": {"type": "boolean"}}}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "run_test",
            titulo: "Testar o jogo na engine",
            descricao: "Abre o jogo em modo de teste: o jogador anda, pula e ataca sozinho; devolve os erros da engine, quadros por segundo, polígonos e tamanho de cada modelo, se os inimigos reagiram, capturas de tela e um vídeo (em ai/testes/).",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "segundos": {"type": "number"}, "video": {"type": "boolean"}}}),
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
            let ignis = f.estado_ignis().await;
            let recursos_ignis =
                if ignis.conectado { crate::ignis::capacidades(f.porta_ignis()).await } else { json!({"conectado": false}) };
            let sugestao = f.sugestao().await;
            let mut programas = serde_json::Map::new();
            for p in [crate::externas::Programa::Blender, crate::externas::Programa::Godot, crate::externas::Programa::Erethea] {
                programas.insert(
                    p.id().into(),
                    match f.programa(p).await {
                        Ok(a) => json!({"achado": true, "nome": p.nome(), "versao": a.versao, "caminho": a.caminho}),
                        Err(_) => json!({"achado": false, "nome": p.nome(), "pagina": p.pagina_download()}),
                    },
                );
            }
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
                "recursos_ignis": recursos_ignis,
                "programas": programas,
                "modelos_de_placa": crate::workers::estado(&f.paths),
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
        "create_character" => geracao::criar_personagem(f, args(a)?, quem).await,
        "generate_concept" => {
            let a: ArgsConceito = args(a)?;
            let p = f.projeto(a.projeto.as_deref())?;
            let nome = crate::projeto::nome_de_pasta(&a.descricao.chars().take(40).collect::<String>());
            let destino = match &a.arquivo {
                Some(c) => f.resolver_no_projeto(&p, c),
                None => p.raiz.join("ai/conceitos").join(format!("{nome}.png")),
            };
            geracao::conceito_avulso(f, &p, &a.descricao, &destino, a.seed.unwrap_or(1), quem).await
        }
        "generate_3d" => geracao::gerar_3d(f, args(a)?, quem).await,
        "create_material" => geracao::criar_material(f, args(a)?, quem).await,
        "create_skeleton" => geracao::criar_esqueleto(f, args(a)?, quem).await,
        "generate_animation" => {
            let mut x: geracao::ArgsAnimacao = args(a)?;
            x.origem = None;
            geracao::animar(f, x, quem).await
        }
        "retarget_animation" => {
            let x: geracao::ArgsAnimacao = args(a)?;
            if x.origem.is_none() {
                return Err(Erro::argumento("Diga de onde copiar as animações (origem)."));
            }
            geracao::animar(f, x, quem).await
        }
        "generate_sfx" => geracao::gerar_efeitos(f, args(a)?, quem).await,
        "generate_music" => geracao::gerar_musica(f, args(a)?, quem).await,
        "generate_voice" => geracao::gerar_voz(f, args(a)?, quem).await,
        "generate_blockout" => geracao::gerar_blockout(f, args(a)?, quem).await,
        "generate_code" => geracao::gerar_codigo(f, args(a)?).await,
        "import_to_engine" => geracao::importar_na_engine(f, args(a)?, quem).await,
        "run_test" => geracao::rodar_teste(f, args(a)?).await,
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
