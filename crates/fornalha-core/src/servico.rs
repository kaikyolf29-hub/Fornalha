//! O orquestrador da Fase 0: junta configuração, catálogo, placa e projeto
//! atual, e atende as ferramentas (pela janela, pela API e pelo MCP).

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde_json::Value;

use crate::config::{Config, Estudio};
use crate::consts::{PORTA_IGNIS, PORTA_PADRAO};
use crate::erro::{Erro, Resultado};
use crate::gpu::Detection;
use crate::licencas::{Catalogo, ContextoRota};
use crate::niveis::{self, Nivel, Sugestao};
use crate::paths::Paths;
use crate::projeto::{self, Projeto};

pub struct Fornalha {
    pub paths: Paths,
    pub catalogo: Catalogo,
    config: Mutex<Config>,
    deteccao: tokio::sync::Mutex<Option<Detection>>,
    /// Testes usam uma placa fixa e não consultam o sistema.
    deteccao_fixa: bool,
    projeto_atual: Mutex<Option<PathBuf>>,
    /// Porta escolhida só para esta execução (ex.: `fornalha-cli servir --porta`).
    porta_fixa: Mutex<Option<u16>>,
    ignis: crate::ignis::Cache,
    programas: tokio::sync::Mutex<std::collections::HashMap<crate::externas::Programa, crate::externas::Achado>>,
    ponte: Mutex<(u64, Vec<String>)>,
    /// Avisos da ponte para a engine ligada por WebSocket (Erethea).
    ponte_tx: tokio::sync::broadcast::Sender<(u64, Vec<String>)>,
    /// O que a engine disse no "ola" (programa, versão, projeto, monta_cenas) e o último relatório de cenas.
    engine_ao_vivo: Mutex<Option<Value>>,
    cenas_da_engine: Mutex<Option<Value>>,
    /// Uma tarefa da fila por vez (a placa e o Blender são um só).
    pub(crate) fila: tokio::sync::Mutex<()>,
}

impl Fornalha {
    pub fn new(paths: Paths) -> Arc<Self> {
        let _ = paths.ensure();
        let config = Config::carregar(&paths);
        // reabre o último projeto que ainda existe
        let ultimo = config.projetos_recentes.iter().find(|r| r.join(projeto::ARQUIVO_BIBLIA).is_file()).cloned();
        Arc::new(Self {
            paths,
            catalogo: Catalogo::embutido(),
            config: Mutex::new(config),
            deteccao: tokio::sync::Mutex::new(None),
            deteccao_fixa: false,
            projeto_atual: Mutex::new(ultimo),
            porta_fixa: Mutex::new(None),
            ignis: crate::ignis::Cache::new(std::time::Duration::from_secs(10)),
            programas: tokio::sync::Mutex::new(std::collections::HashMap::new()),
            ponte: Mutex::new((0, Vec::new())),
            ponte_tx: tokio::sync::broadcast::channel(32).0,
            engine_ao_vivo: Mutex::new(None),
            cenas_da_engine: Mutex::new(None),
            fila: tokio::sync::Mutex::new(()),
        })
    }

    /// Para testes: placa fixa e Ignis e ComfyUI numa porta fechada.
    pub fn para_testes(paths: Paths, deteccao: Detection) -> Arc<Self> {
        let _ = paths.ensure();
        let mut config = Config::carregar(&paths);
        config.porta_ignis.get_or_insert(1);
        config.porta_comfyui.get_or_insert(1);
        Arc::new(Self {
            paths,
            catalogo: Catalogo::embutido(),
            config: Mutex::new(config),
            deteccao: tokio::sync::Mutex::new(Some(deteccao)),
            deteccao_fixa: true,
            projeto_atual: Mutex::new(None),
            porta_fixa: Mutex::new(None),
            ignis: crate::ignis::Cache::new(std::time::Duration::from_secs(10)),
            programas: tokio::sync::Mutex::new(std::collections::HashMap::new()),
            ponte: Mutex::new((0, Vec::new())),
            ponte_tx: tokio::sync::broadcast::channel(32).0,
            engine_ao_vivo: Mutex::new(None),
            cenas_da_engine: Mutex::new(None),
            fila: tokio::sync::Mutex::new(()),
        })
    }

    pub fn config(&self) -> Config {
        self.config.lock().unwrap().clone()
    }

    fn mudar_config(&self, f: impl FnOnce(&mut Config)) -> Resultado<()> {
        let mut c = self.config.lock().unwrap();
        f(&mut c);
        c.salvar(&self.paths).map_err(|e| Erro::io(&self.paths.config_file(), e))
    }

    pub fn porta_api(&self) -> u16 {
        self.porta_fixa.lock().unwrap().or(self.config().porta_api).unwrap_or(PORTA_PADRAO)
    }

    /// Usa outra porta só nesta execução, sem mudar a configuração.
    pub fn fixar_porta(&self, porta: u16) {
        *self.porta_fixa.lock().unwrap() = Some(porta);
    }

    /// Estado do Ignis (guardado por 10 s).
    pub async fn estado_ignis(&self) -> crate::ignis::EstadoIgnis {
        self.ignis.consultar(self.porta_ignis()).await
    }

    pub fn porta_ignis(&self) -> u16 {
        self.config().porta_ignis.unwrap_or(PORTA_IGNIS)
    }

    pub fn porta_comfyui(&self) -> u16 {
        self.config().porta_comfyui.unwrap_or(crate::comfyui::PORTA_PADRAO)
    }

    pub fn pasta_projetos(&self) -> PathBuf {
        self.config().pasta_projetos(&self.paths)
    }

    /// Decisões do estúdio sobre licenças. Só a janela chama isto.
    pub fn estudio(&self) -> Estudio {
        self.config().estudio
    }

    pub fn definir_estudio(&self, estudio: Estudio) -> Resultado<()> {
        self.mudar_config(|c| c.estudio = estudio)
    }

    /// Nível escolhido pela pessoa para esta máquina (só pela janela).
    pub fn definir_nivel_da_maquina(&self, nivel: Option<Nivel>) -> Resultado<()> {
        self.mudar_config(|c| c.nivel = nivel.map(|n| n.id().to_string()))
    }

    pub fn definir_pasta_projetos(&self, pasta: Option<PathBuf>) -> Resultado<()> {
        self.mudar_config(|c| c.pasta_projetos = pasta)
    }

    pub fn definir_porta_ignis(&self, porta: u16) -> Resultado<()> {
        self.mudar_config(|c| c.porta_ignis = Some(porta))
    }

    pub fn definir_porta_comfyui(&self, porta: u16) -> Resultado<()> {
        self.mudar_config(|c| c.porta_comfyui = Some(porta))
    }

    pub fn definir_noite(&self, noite: crate::config::Noite) -> Resultado<()> {
        if noite.inicio_hora > 23 || noite.fim_hora > 23 {
            return Err(crate::erro::Erro::argumento("As horas da noite vão de 0 a 23."));
        }
        self.mudar_config(|c| c.noite = noite)
    }

    pub fn definir_estilo_janela(&self, estilo: Option<String>) -> Resultado<()> {
        self.mudar_config(|c| c.estilo_janela = estilo)
    }

    /// Detecção da placa (feita uma vez; `atualizar` força de novo).
    pub async fn deteccao(&self, atualizar: bool) -> Detection {
        let mut d = self.deteccao.lock().await;
        if d.is_none() || (atualizar && !self.deteccao_fixa) {
            *d = Some(crate::gpu::detect(&[]).await);
        }
        d.clone().expect("acabou de detectar")
    }

    pub async fn sugestao(&self) -> Sugestao {
        niveis::sugerir(&self.deteccao(false).await)
    }

    pub fn projeto_atual(&self) -> Option<PathBuf> {
        self.projeto_atual.lock().unwrap().clone()
    }

    /// Marca o projeto como atual e o coloca nos recentes.
    pub fn usar_projeto(&self, raiz: &Path) -> Resultado<()> {
        *self.projeto_atual.lock().unwrap() = Some(raiz.to_path_buf());
        self.mudar_config(|c| c.lembrar_projeto(raiz))
    }

    /// Abre o projeto pedido, ou o atual.
    pub fn projeto(&self, caminho: Option<&str>) -> Resultado<Projeto> {
        match caminho.map(str::trim).filter(|c| !c.is_empty()) {
            Some(c) => projeto::abrir(&self.resolver_caminho(c)),
            None => match self.projeto_atual() {
                Some(r) => projeto::abrir(&r),
                None => Err(Erro::novo("sem_projeto", "Nenhum projeto aberto: use create_project ou open_project.")),
            },
        }
    }

    /// Caminho relativo vale a partir da pasta de projetos.
    pub fn resolver_caminho(&self, c: &str) -> PathBuf {
        let p = PathBuf::from(c);
        if p.is_absolute() {
            p
        } else {
            self.pasta_projetos().join(p)
        }
    }

    /// Contexto do roteador para um projeto nesta máquina.
    pub async fn contexto(&self, projeto: Option<&Projeto>) -> ContextoRota {
        let estudio = self.estudio();
        let acel = niveis::aceleradores(&self.deteccao(false).await);
        ContextoRota {
            comercial: projeto.map(|p| p.biblia.comercial).unwrap_or(true),
            cuda: acel.cuda,
            receita_anual_usd: estudio.receita_anual_usd,
            licencas_aceitas: estudio.licencas_aceitas,
            sem_dependencias: crate::workers::sem_dependencias(&self.paths),
        }
    }

    /// Nível em uso: o do projeto, senão o escolhido para a máquina, senão o sugerido pela placa.
    pub async fn nivel_em_uso(&self, projeto: Option<&Projeto>) -> Nivel {
        if let Some(n) = projeto.and_then(|p| p.biblia.nivel.as_deref()).and_then(Nivel::from_id) {
            return n;
        }
        if let Some(n) = self.config().nivel.as_deref().and_then(Nivel::from_id) {
            return n;
        }
        self.sugestao().await.nivel
    }

    /// Blender, Godot ou Erethea: o caminho escolhido nas configurações, ou procura no sistema.
    pub async fn programa(&self, programa: crate::externas::Programa) -> Resultado<crate::externas::Achado> {
        use crate::externas::Programa;
        let mut cache = self.programas.lock().await;
        if let Some(a) = cache.get(&programa) {
            if a.caminho.is_file() {
                return Ok(a.clone());
            }
        }
        let cfg = self.config();
        let escolhido = match programa {
            Programa::Blender => cfg.blender,
            Programa::Godot => cfg.godot,
            Programa::Erethea => cfg.erethea,
        };
        let amb = crate::externas::Ambiente::do_sistema(programa, escolhido, self.paths.data_dir.join("ferramentas"));
        match crate::externas::achar_no(programa, &amb).await {
            Some(a) => {
                cache.insert(programa, a.clone());
                Ok(a)
            }
            None => Err(Erro::novo(
                "programa_nao_encontrado",
                format!(
                    "Não achei o {} neste computador. Instale ({}) ou escolha o executável em Ajustes da Fornalha.",
                    programa.nome(),
                    programa.pagina_download()
                ),
            )),
        }
    }

    /// Escolhe (ou esquece) o caminho de um programa. Só pela janela.
    pub async fn definir_programa(&self, programa: crate::externas::Programa, caminho: Option<PathBuf>) -> Resultado<()> {
        use crate::externas::Programa;
        self.programas.lock().await.remove(&programa);
        self.mudar_config(|c| match programa {
            Programa::Blender => c.blender = caminho,
            Programa::Godot => c.godot = caminho,
            Programa::Erethea => c.erethea = caminho,
        })
    }

    /// Avisa a ponte com a engine que há arquivos novos (o plugin do editor reimporta).
    pub fn avisar_ponte(&self, arquivos: Vec<String>) {
        let mut p = self.ponte.lock().unwrap();
        p.0 += 1;
        p.1 = arquivos;
        let _ = self.ponte_tx.send(p.clone()); // sem ninguém ligado, tudo bem
    }

    /// Para o WebSocket da ponte: recebe cada aviso novo.
    pub fn assinar_ponte(&self) -> tokio::sync::broadcast::Receiver<(u64, Vec<String>)> {
        self.ponte_tx.subscribe()
    }

    /// A engine ligada ao vivo (o "ola" dela), ou `None` quando desligou.
    pub fn registrar_engine(&self, ola: Option<Value>) {
        *self.engine_ao_vivo.lock().unwrap() = ola;
    }

    pub fn engine_ao_vivo(&self) -> Option<Value> {
        self.engine_ao_vivo.lock().unwrap().clone()
    }

    /// A engine ligada disse que monta as cenas ela mesma (a Fornalha não roda o montar.gd).
    pub fn engine_monta_cenas(&self) -> bool {
        self.engine_ao_vivo().is_some_and(|v| v["monta_cenas"] == true)
    }

    pub fn registrar_cenas(&self, relatorio: Value) {
        *self.cenas_da_engine.lock().unwrap() = Some(relatorio);
    }

    pub fn cenas_da_engine(&self) -> Option<Value> {
        self.cenas_da_engine.lock().unwrap().clone()
    }

    pub fn estado_ponte(&self) -> (u64, Vec<String>) {
        self.ponte.lock().unwrap().clone()
    }

    /// Caminho relativo vale a partir da pasta do projeto.
    pub fn resolver_no_projeto(&self, p: &Projeto, c: &str) -> PathBuf {
        let caminho = PathBuf::from(c.replace('\\', std::path::MAIN_SEPARATOR_STR));
        if caminho.is_absolute() {
            caminho
        } else {
            p.raiz.join(caminho)
        }
    }

    /// Chama uma ferramenta pelo nome. `quem` vai para os recibos ("pessoa", "claude-code"...).
    pub async fn chamar(&self, nome: &str, args: Value, quem: &str) -> Resultado<Value> {
        crate::ferramentas::chamar(self, nome, args, quem).await
    }
}
