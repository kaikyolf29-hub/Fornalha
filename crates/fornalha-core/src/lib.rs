//! Núcleo da Fornalha.
//!
//! Tudo o que não é janela nem bandeja mora aqui, para poder ser testado sem
//! interface gráfica e sem placa de vídeo.
//!
//! `gpu`, `distro`, `janela` e `util` vieram do Ignis (licença MIT, veja AVISOS.md).

pub mod api;
pub mod audio;
pub mod config;
pub mod consts;
pub mod distro;
pub mod engine;
pub mod erro;
pub mod externas;
pub mod ferramentas;
pub mod forja;
pub mod geracao;
pub mod gpu;
pub mod ignis;
pub mod janela;
pub mod licencas;
pub mod mcp;
pub mod niveis;
pub mod paths;
pub mod projeto;
pub mod recibos;
pub mod servico;
pub mod util;
