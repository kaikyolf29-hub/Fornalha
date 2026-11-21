//! Nome e constantes do aplicativo.

/// Nome mostrado para a pessoa.
pub const APP_NAME: &str = "Fornalha";
/// Nome que a pessoa vê (janela, bandeja, instalador). O APP_NAME fica para a API e as pastas.
pub const NOME_EXIBIDO: &str = "Fornalha 3D";
/// Nome usado em pastas, chave Run do Windows e arquivo .desktop.
pub const APP_ID: &str = "fornalha";
/// Versão do aplicativo (vem do Cargo).
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
/// Versão do contrato da API (/fornalha/*). Sobe só quando algo quebra a compatibilidade.
pub const API_VERSION: u32 = 1;
/// Porta padrão da API local e do MCP por HTTP (a do Ignis é 11470).
pub const PORTA_PADRAO: u16 = 11480;
/// Porta padrão da API do Ignis (o cérebro local).
pub const PORTA_IGNIS: u16 = 11470;
/// Fase do plano em que o app está.
pub const FASE: u32 = 0;
/// User-Agent genérico (sem dados da pessoa).
pub const USER_AGENT: &str = concat!("Fornalha/", env!("CARGO_PKG_VERSION"));
