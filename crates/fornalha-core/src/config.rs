//! Configuração da Fornalha (por máquina): pasta dos projetos, recentes,
//! portas, nível preferido e as decisões do estúdio sobre licenças.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::paths::{read_json, write_json, Paths};

const MAX_RECENTES: usize = 12;

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    /// Onde os projetos novos nascem (padrão: Documentos/Fornalha).
    pub pasta_projetos: Option<PathBuf>,
    /// Do mais novo para o mais antigo.
    pub projetos_recentes: Vec<PathBuf>,
    pub porta_api: Option<u16>,
    pub porta_ignis: Option<u16>,
    /// Nível escolhido pela pessoa para esta máquina (`None` = o sugerido pela placa).
    pub nivel: Option<String>,
    /// Estilo dos botões da janela ("auto", "windows", "gnome", "kde", "mac").
    pub estilo_janela: Option<String>,
    /// Caminhos escolhidos pela pessoa (senão a Fornalha procura sozinha).
    pub blender: Option<PathBuf>,
    pub godot: Option<PathBuf>,
    pub erethea: Option<PathBuf>,
    pub estudio: Estudio,
    /// Horário da fila da noite (hora local, 0–23). Padrão: das 23h às 7h.
    pub noite: Noite,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Noite {
    pub inicio_hora: u8,
    pub fim_hora: u8,
}

impl Default for Noite {
    fn default() -> Self {
        Self { inicio_hora: 23, fim_hora: 7 }
    }
}

impl Noite {
    /// A hora (0–23) está dentro da noite? Aceita noite que vira o dia (23h → 7h).
    pub fn contem(&self, hora: u8) -> bool {
        let (i, f) = (self.inicio_hora % 24, self.fim_hora % 24);
        if i == f {
            true
        } else if i < f {
            hora >= i && hora < f
        } else {
            hora >= i || hora < f
        }
    }
}

/// Decisões que só a pessoa toma (pela janela), nunca um agente.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Estudio {
    /// Receita anual do estúdio em US$ (para licenças com teto de receita).
    pub receita_anual_usd: Option<u64>,
    /// Grupos de licença aceitos (ex.: "tencent-hunyuan").
    pub licencas_aceitas: Vec<String>,
}

impl Config {
    pub fn carregar(paths: &Paths) -> Self {
        read_json(&paths.config_file()).unwrap_or_default()
    }

    pub fn salvar(&self, paths: &Paths) -> std::io::Result<()> {
        write_json(&paths.config_file(), self)
    }

    /// Põe o projeto no topo dos recentes.
    pub fn lembrar_projeto(&mut self, raiz: &Path) {
        self.projetos_recentes.retain(|p| p != raiz);
        self.projetos_recentes.insert(0, raiz.to_path_buf());
        self.projetos_recentes.truncate(MAX_RECENTES);
    }

    pub fn pasta_projetos(&self, paths: &Paths) -> PathBuf {
        self.pasta_projetos.clone().unwrap_or_else(|| paths.pasta_projetos_padrao())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noite_que_vira_o_dia() {
        let n = Noite::default();
        assert!(n.contem(23) && n.contem(0) && n.contem(6));
        assert!(!n.contem(7) && !n.contem(12) && !n.contem(22));
        let tarde = Noite { inicio_hora: 13, fim_hora: 15 };
        assert!(tarde.contem(14) && !tarde.contem(15));
        assert!(Noite { inicio_hora: 5, fim_hora: 5 }.contem(17), "início igual ao fim = o dia todo");
    }

    #[test]
    fn recentes_sem_repetir_e_com_limite() {
        let mut c = Config::default();
        for i in 0..20 {
            c.lembrar_projeto(Path::new(&format!("/p/{i}")));
        }
        c.lembrar_projeto(Path::new("/p/5"));
        assert_eq!(c.projetos_recentes.len(), MAX_RECENTES);
        assert_eq!(c.projetos_recentes[0], Path::new("/p/5"));
        assert_eq!(c.projetos_recentes.iter().filter(|p| p.as_path() == Path::new("/p/5")).count(), 1);
    }

    #[test]
    fn salvar_e_carregar() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = Paths::under(tmp.path());
        let mut c = Config::default();
        c.estudio.receita_anual_usd = Some(10);
        c.salvar(&paths).unwrap();
        assert_eq!(Config::carregar(&paths), c);
    }

    #[test]
    fn arquivo_corrompido_volta_ao_padrao() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = Paths::under(tmp.path());
        std::fs::create_dir_all(&paths.config_dir).unwrap();
        std::fs::write(paths.config_file(), "{ ruim").unwrap();
        assert_eq!(Config::carregar(&paths), Config::default());
    }
}
