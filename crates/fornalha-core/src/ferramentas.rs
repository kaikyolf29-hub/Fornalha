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
            descricao: "Cria um personagem do zero: a ficha (o cérebro do Ignis completa o que faltar, coerente com a bíblia), a imagem de conceito (Ignis), o modelo 3D com o esqueleto padrão e 9 animações (parado, andar, correr, pular, atacar, defender, esquivar, dano, morrer), a arma na mão, prévia e folha de modelo, e a fala dublada com a curva da boca. Grava em Characters/<id>/ (ou Enemies/<id>/ se o papel for inimigo ou chefe), atualiza a bíblia e registra os recibos. Com testar_na_engine, monta o jogo e roda o teste (o inimigo novo aparece na frente do jogador). Também cria qualquer criatura ou monstro: mande `imagem` (um PNG que a pessoa já tem, do Gemini ou de onde for) e `corpo` (ou auto) — a imagem vira a malha pela IA sem ser refeita, e o esqueleto e as animações vêm da forma do corpo (humanoide, alado ou de patas, qualquer número). Pode levar alguns minutos (horas no 3D pela IA sem placa).",
            esquema: json!({
                "type": "object",
                "properties": {
                    "projeto": projeto_opcional(),
                    "nome": {"type": "string"},
                    "papel": {"type": "string", "description": "protagonista, aliado, inimigo, chefe..."},
                    "descricao": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["humano", "elfo", "anao", "orc", "goblin", "esqueleto", "zumbi", "demonio", "dragao"],
                             "description": "dragao: criatura com esqueleto próprio (asas, cauda, pescoço, mandíbula) e animações de voo e ataque."},
                    "arma": {"type": "string", "enum": ["espada", "machado", "lanca", "martelo", "adaga", "cajado", "escudo", "nenhuma"]},
                    "armadura": {"type": "string", "enum": ["nenhuma", "leve", "pesada", "placas"]},
                    "porte": {"type": "string", "enum": ["magro", "medio", "forte"]},
                    "cor_roupa": {"type": "string"}, "cor_roupa_secundaria": {"type": "string"}, "cor_pele": {"type": "string"}, "cor_cabelo": {"type": "string"},
                    "capa": {"type": "boolean"}, "capuz": {"type": "boolean"},
                    "fala": {"type": "string", "description": "Frase para dublar em português."},
                    "conceito": {"type": "boolean", "description": "Gerar a imagem de conceito (padrão: sim, se o Ignis tiver imagem)."},
                    "video": {"type": "boolean", "description": "Vídeo curto das animações."},
                    "testar_na_engine": {"type": "boolean", "description": "Montar na engine e rodar o teste no fim."},
                    "seed": {"type": "integer", "minimum": 0},
                    "parar_no_conceito": {"type": "boolean", "description": "Por partes: para no conceito de corpo inteiro (o que vira 3D) e devolve a imagem para aceitar ou refazer; a chamada seguinte com o mesmo nome usa esse conceito."},
                    "refazer_conceito": {"type": "boolean", "description": "Apaga o conceito de corpo inteiro guardado e faz outro (mande outra seed)."},
                    "imagem": {"type": "string", "description": "Caminho de uma imagem PNG pronta (feita no Gemini, no ChatGPT, desenhada…): ela vira o 3D como está, sem ser refeita; esqueleto e animações vêm da malha."},
                    "corpo": {"type": "string", "enum": ["auto", "humanoide", "alado", "quadrupede", "aranha", "inseto", "serpente", "criatura"],
                              "description": "Tipo de corpo: decide o esqueleto e as animações. auto mede na malha (padrão quando há imagem). humanoide: esqueleto do humano com dedos e captura de movimento; alado: asas, pescoço e cauda; os outros: patas achadas na malha (qualquer número), passada com IK, coluna e cauda em onda, bote."}
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
            nome: "list_motions",
            titulo: "Banco de movimento",
            descricao: "Lista as capturas de movimento com licença comercial que a Fornalha tem (Quaternius CC0, ACCAD CC BY 3.0 com luta e passos, 100STYLE CC BY 4.0 com 100 estilos de andar, e o que a pessoa trouxe: Mixamo, CMU, capturas próprias), com etiquetas em português (andar, correr, ataque, espada, soco, chute, defesa, esquiva, morte, dano, zumbi, agachado, de_costas, de_lado, virar, pular, carregar, gesto, estilo:<nome>), duração, se fecha em laço e quanto anda. Filtre por busca, etiquetas, fonte ou laço. Os ids vão para apply_motion.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "busca": {"type": "string"},
                "etiquetas": {"type": "array", "items": {"type": "string"}}, "fonte": {"type": "string"}, "laco": {"type": "boolean"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 500}}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "apply_motion",
            titulo: "Pôr movimentos do banco no personagem",
            descricao: "Passa clipes do banco de movimento para um personagem com esqueleto de jogo (o do humano da Fornalha ou o da malha da IA), com o nome que cada um terá no jogo. Retarget por pose (funciona com BVH de descanso esquisito), começa de frente e no centro; ciclo: true recorta sozinho o trecho que fecha em laço numa tomada longa (andar e correr do ACCAD e do 100STYLE); no_lugar tira o deslocamento; inicio/fim/velocidade recortam e aceleram. Depois confere cada animação (braço virado, cotovelo ou joelho ao contrário ou de lado, tranco, braço atravessando o tronco, pernas se cruzando, pé escorregando, corpo no chão ou flutuando) e corrige sozinho o que der (pé travado no chão por IK, junta endireitada, torção passada para o antebraço, membro afastado do corpo, quadril assentado). Devolve aprovado/reprovado com números, a imagem do pior quadro (ossos ruins em vermelho) e, com video, o vídeo. Mantém as outras animações do personagem.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string", "description": "Personagem (glb) com esqueleto de jogo."},
                "clipes": {"type": "array", "items": {"type": "object", "properties": {
                    "id": {"type": "string", "description": "id do list_motions, ou caminho de um BVH/FBX/glb."},
                    "como": {"type": "string", "description": "Nome da animação no jogo (andar, correr, atacar, chute…)."},
                    "laco": {"type": "boolean"}, "ciclo": {"type": "boolean"}, "no_lugar": {"type": "boolean"},
                    "inicio": {"type": "integer", "minimum": 0}, "fim": {"type": "integer", "minimum": 0},
                    "velocidade": {"type": "number", "minimum": 0.1, "maximum": 4}}, "required": ["id", "como"]}},
                "corrigir": {"type": "boolean", "description": "Corrigir sozinho o que reprovar (padrão: sim)."},
                "video": {"type": "boolean", "description": "Vídeo das animações novas (lento no processador)."}},
                "required": ["arquivo", "clipes"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "check_motion",
            titulo: "Conferir o movimento",
            descricao: "Mede todas as animações de um personagem e reprova o que fica feio no jogo: osso torcido além do natural (braço virado), cotovelo ou joelho dobrando ao contrário ou de lado, tranco (osso que vira de um quadro para o outro), corpo sólido (braço atravessando o tronco, pernas se cruzando), pé escorregando no chão, corpo entrando no chão ou flutuando. Vale para humano e para criaturas (as regras de humano só entram com os ossos de humano). Com corrigir: true, corrige sozinho e regrava o glb. Devolve números por animação, o pior quadro de cada problema e uma imagem com os ossos ruins em vermelho.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"},
                "animacoes": {"type": "array", "items": {"type": "string"}}, "corrigir": {"type": "boolean"},
                "imagens": {"type": "string", "enum": ["reprovados", "todas", "nenhuma"]}}, "required": ["arquivo"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "import_motion",
            titulo: "Trazer capturas de movimento",
            descricao: "Copia para o banco de movimento do projeto (Motion/<fonte>/) capturas que a pessoa baixou: Mixamo (com a conta Adobe dela; o uso comercial depende do aceite dela pela janela), CMU, ACCAD, 100STYLE ou captura própria do estúdio. Aceita arquivos BVH, FBX e glb, ou pastas com eles.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivos": {"type": "array", "items": {"type": "string"}},
                "fonte": {"type": "string", "enum": ["mixamo", "cmu", "accad", "100style", "propria"]}}, "required": ["arquivos", "fonte"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "show_skeleton",
            titulo: "Ver o esqueleto",
            descricao: "Mostra o esqueleto de um personagem ou criatura para conferir: imagem com a malha clara e os ossos coloridos e numerados (frente, lado e cima; azul = esquerda, vermelho = direita, amarelo = meio, roxo = mola) e a lista dos ossos (número, nome, pai, cabeça e ponta em metros, comprimento, quantos vértices carrega, distância até a malha), com avisos (osso que não mexe nada, osso longe do corpo, lados diferentes ou fora de espelho).",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"}}, "required": ["arquivo"]}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "edit_skeleton",
            titulo: "Mexer no esqueleto",
            descricao: "Muda o esqueleto de qualquer corpo (humano, criatura de patas, asas, cauda, tentáculos): mover a cabeça ou a ponta de um osso, criar osso (com pai e se fica ligado), apagar (os filhos sobem para o pai), renomear, trocar o pai, espelhar um lado no outro. Ossos pelo nome ou pelo número do show_skeleton; posições em metros como no show_skeleton. Ossos chamados mola_<grupo>_1..N (mola_cauda_1, mola_cabelo_1, mola_asa_l_1) viram mola no jogo. Os pesos são refeitos só perto dos ossos mexidos (pesos: locais), no corpo todo (distancia), pelo Blender (auto) ou ficam (manter). Devolve a imagem nova e a lista.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"},
                "mudancas": {"type": "array", "items": {"type": "object", "properties": {
                    "op": {"type": "string", "enum": ["mover", "criar", "apagar", "renomear", "pai", "espelhar"]},
                    "osso": {"type": ["string", "integer"]}, "pai": {"type": ["string", "integer", "null"]},
                    "cabeca": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "ponta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "ligado": {"type": "boolean"}, "novo": {"type": "string"}, "de": {"type": "string", "enum": ["_l", "_r", "Left", "Right"]}},
                    "required": ["op"]}},
                "pesos": {"type": "string", "enum": ["locais", "distancia", "auto", "manter"]}}, "required": ["arquivo", "mudancas"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "dress_character",
            titulo: "Vestir roupa ou armadura",
            descricao: "Roupa por cima de um personagem que já se mexe (primeiro o movimento, depois a roupa): a malha de roupa ou armadura (da IA, de pacote ou feita à mão; glb, obj ou fbx) recebe os pesos do corpo pela superfície mais próxima. Cada peça pequena de um osso só (placa, ombreira, manopla, elmo) fica rígida nesse osso, como armadura de jogo; pano grande (capa, sobreveste, saia) dobra com o corpo. Depois confere todas as animações com a roupa (corpo sólido mede a roupa também). encaixar: true leva a roupa para o tamanho e o lugar do corpo.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string", "description": "Personagem com esqueleto e animações."},
                "roupa": {"type": "string"}, "rigido": {"type": "string", "enum": ["auto", "sim", "nao"]}, "encaixar": {"type": "boolean"},
                "saida": {"type": "string"}}, "required": ["arquivo", "roupa"]}),
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
        Ferramenta {
            nome: "run_brute_test",
            titulo: "Teste Bruto (suíte de ponta a ponta)",
            descricao: "Num projeto só do teste, gera o protagonista completo (corpo, rosto, cabelo em camadas, roupa, andar e combate), um inimigo humanoide armado (arma presa na mão) e um dragão (esqueleto não humanoide, voo e ataque); monta o mundo, roda o jogo na engine e confere glTF (malha, esqueleto, animações), mandíbula para a fala, QA, bíblia válida e a licença comercial de tudo. Devolve o relatório (também em testes/teste_bruto.json). Leva vários minutos.",
            esquema: json!({"type": "object", "properties": {
                "nivel": {"type": "string", "enum": ["leve", "equilibrado", "qualidade", "maximo"], "description": "padrão: qualidade"},
                "casos": {"type": "array", "items": {"type": "string", "enum": ["protagonista", "inimigo", "zumbi", "dragao"]}},
                "testar_na_engine": {"type": "boolean"}}}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "plan_request",
            titulo: "Pedido livre (o cérebro planeja)",
            descricao: "Transforma um pedido livre (\"faça a vila com dois goblins, uma espada e música de combate, e teste o jogo\") em passos com as ferramentas da Fornalha — pelo cérebro no Ignis, ou por regras se o Ignis estiver fechado — e põe na fila: agora (padrão), à noite ou só mostra o plano (executar: \"nao\").",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "pedido": {"type": "string"}, "executar": {"type": "string", "enum": ["agora", "noite", "nao"]}}, "required": ["pedido"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "queue_job",
            titulo: "Pôr na fila (agora ou à noite)",
            descricao: "Põe uma ferramenta de geração ou de teste na fila, para rodar assim que a fila estiver livre (quando: agora) ou só no horário da noite (quando: noite; padrão das 23h às 7h). Uma tarefa por vez.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "ferramenta": {"type": "string", "enum": crate::fila::FERRAMENTAS_DA_FILA},
                "argumentos": {"type": "object"}, "quando": {"type": "string", "enum": ["agora", "noite"]}, "descricao": {"type": "string"}}, "required": ["ferramenta"]}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "list_queue",
            titulo: "Ver a fila",
            descricao: "Lista a fila: o que espera, o que está rodando, o que terminou (com o resultado ou o erro) e o horário da noite.",
            esquema: json!({"type": "object", "properties": {}}),
            so_leitura: true,
        },
        Ferramenta {
            nome: "cancel_job",
            titulo: "Cancelar tarefa da fila",
            descricao: "Cancela uma tarefa que ainda está esperando (pelo id de list_queue). Com limpar: true, tira da lista o que já terminou.",
            esquema: json!({"type": "object", "properties": {"id": {"type": "string"}, "limpar": {"type": "boolean"}}}),
            so_leitura: false,
        },
        Ferramenta {
            nome: "check_style",
            titulo: "Conferir o guia visual",
            descricao: "Mede as cores de um asset (png ou glb) — ou de todos os assets do projeto — contra a paleta do guia visual da bíblia: quanto está na paleta, as cores dominantes e as que fogem dela.",
            esquema: json!({"type": "object", "properties": {"projeto": projeto_opcional(), "arquivo": {"type": "string"}, "limite": {"type": "number", "minimum": 0, "maximum": 1}}}),
            so_leitura: true,
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
            let comfyui = {
                let e = crate::comfyui::consultar(f.porta_comfyui()).await;
                let modelo = if e.conectado { crate::comfyui::modelo_de_imagem(f.porta_comfyui()).await } else { None };
                let caminho = crate::comfyui::caminho_para(&f.deteccao(false).await);
                let vulkan = crate::comfyui::motor_vulkan(&f.paths).map(
                    |m| json!({"id_do_modelo": m.id(), "dispositivos": crate::comfyui::dispositivos_vulkan_guardados(&m), "motor": m}),
                );
                json!({"estado": e, "modelo_de_imagem": modelo, "instalacao": crate::comfyui::estado_instalacao(&f.paths),
                       "caminho": caminho, "vulkan": vulkan})
            };
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
                "comfyui": comfyui,
                "programas": programas,
                "downloads_de_programas": crate::programas::estado(&f.paths),
                "apis_3d": crate::apis::estado(&f.paths),
                "modelos_de_placa": crate::workers::estado(&f.paths),
                "pacotes": crate::pacotes::estado(&f.paths),
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
            // projeto antigo ganha o guia para a IA; o bloco da Fornalha no AGENTS.md é atualizado
            let guia = crate::guia::escrever(&p)?;
            Ok(json!({"raiz": p.raiz, "biblia": p.biblia, "recibos": n, "guia_para_ia": guia}))
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
        "list_motions" => crate::movimento::listar(f, args(a)?).await,
        "apply_motion" => crate::movimento::aplicar(f, args(a)?, quem).await,
        "check_motion" => crate::movimento::conferir(f, args(a)?, quem).await,
        "import_motion" => crate::movimento::importar(f, args(a)?).await,
        "show_skeleton" => crate::movimento::ver_esqueleto(f, args(a)?).await,
        "edit_skeleton" => crate::movimento::editar_esqueleto(f, args(a)?, quem).await,
        "dress_character" => crate::movimento::vestir(f, args(a)?, quem).await,
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
        // a suíte chama as outras ferramentas: a chamada vai numa caixa (função assíncrona recursiva)
        "run_brute_test" => Box::pin(crate::bruto::rodar(f, args(a)?, quem)).await,
        "plan_request" => crate::plano::planejar(f, args(a)?, quem).await,
        "queue_job" => {
            #[derive(serde::Deserialize, Default)]
            #[serde(default)]
            struct A {
                projeto: Option<String>,
                ferramenta: String,
                argumentos: Option<Value>,
                quando: Option<crate::fila::Quando>,
                descricao: Option<String>,
            }
            let x: A = args(a)?;
            let p = f.projeto(x.projeto.as_deref())?;
            let mut argumentos = x.argumentos.unwrap_or_else(|| json!({}));
            if argumentos.is_object() && argumentos.get("projeto").is_none() {
                argumentos["projeto"] = json!(p.raiz);
            }
            let t = crate::fila::enfileirar(f, &x.ferramenta, argumentos, quem, x.quando.unwrap_or_default(), x.descricao, None)?;
            Ok(json!({"tarefa": t}))
        }
        "list_queue" => Ok(crate::fila::listar(f)),
        "cancel_job" => {
            #[derive(serde::Deserialize, Default)]
            #[serde(default)]
            struct A {
                id: Option<String>,
                limpar: Option<bool>,
            }
            let x: A = args(a)?;
            if x.limpar.unwrap_or(false) {
                return Ok(json!({"removidas": crate::fila::limpar(f)?}));
            }
            let id = x.id.ok_or_else(|| Erro::argumento("Diga o id da tarefa (veja list_queue)."))?;
            Ok(json!({"tarefa": crate::fila::cancelar(f, &id)?}))
        }
        "check_style" => {
            #[derive(serde::Deserialize, Default)]
            #[serde(default)]
            struct A {
                projeto: Option<String>,
                arquivo: Option<String>,
                limite: Option<f32>,
            }
            let x: A = args(a)?;
            let p = f.projeto(x.projeto.as_deref())?;
            let arq = x.arquivo.as_deref().map(|c| f.resolver_no_projeto(&p, c));
            crate::estilo::conferir(&p, arq.as_deref(), x.limite)
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
