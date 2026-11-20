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
}

impl Fornalha {
    pub fn new(paths: Paths) -> Arc<Self> {
        let _ = paths.ensure();
        let config = Config::carregar(&paths);
        Arc::new(Self {
            paths,
            catalogo: Catalogo::embutido(),
            config: Mutex::new(config),
            deteccao: tokio::sync::Mutex::new(None),
            deteccao_fixa: false,
            projeto_atual: Mutex::new(None),
            porta_fixa: Mutex::new(None),
        })
    }

    /// Para testes: placa fixa e Ignis numa porta fechada.
    pub fn para_testes(paths: Paths, deteccao: Detection) -> Arc<Self> {
        let _ = paths.ensure();
        let mut config = Config::carregar(&paths);
        config.porta_ignis.get_or_insert(1);
        Arc::new(Self {
            paths,
            catalogo: Catalogo::embutido(),
            config: Mutex::new(config),
            deteccao: tokio::sync::Mutex::new(Some(deteccao)),
            deteccao_fixa: true,
            projeto_atual: Mutex::new(None),
            porta_fixa: Mutex::new(None),
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

    pub fn porta_ignis(&self) -> u16 {
        self.config().porta_ignis.unwrap_or(PORTA_IGNIS)
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

    /// Chama uma ferramenta pelo nome. `quem` vai para os recibos ("pessoa", "claude-code"...).
    pub async fn chamar(&self, nome: &str, args: Value, quem: &str) -> Resultado<Value> {
        crate::ferramentas::chamar(self, nome, args, quem).await
    }
}
