//! Erro único da Fornalha: um código estável (para agentes e para a API) e uma
//! mensagem em português (para a pessoa).

use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, thiserror::Error)]
#[error("{mensagem}")]
pub struct Erro {
    pub codigo: &'static str,
    pub mensagem: String,
}

impl Erro {
    pub fn novo(codigo: &'static str, mensagem: impl Into<String>) -> Self {
        Self { codigo, mensagem: mensagem.into() }
    }

    /// Erro de leitura ou gravação de arquivo, com o caminho.
    pub fn io(caminho: &std::path::Path, e: std::io::Error) -> Self {
        Self::novo("erro_de_arquivo", format!("Não consegui usar {}: {e}", caminho.display()))
    }

    /// Argumento ruim numa chamada de ferramenta.
    pub fn argumento(mensagem: impl Into<String>) -> Self {
        Self::novo("argumento_invalido", mensagem)
    }
}

pub type Resultado<T> = Result<T, Erro>;
