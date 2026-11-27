#![recursion_limit = "256"]
//! Núcleo da Fornalha.
//!
//! Tudo o que não é janela nem bandeja mora aqui, para poder ser testado sem
//! interface gráfica e sem placa de vídeo.
//!
//! `gpu`, `distro`, `janela` e `util` vieram do Ignis (licença MIT, veja AVISOS.md).

pub mod api;
pub mod apis;
pub mod audio;
pub mod bruto;
pub mod comfyui;
pub mod comfyui_ui;
pub mod config;
pub mod consts;
pub mod distro;
pub mod engine;
pub mod erro;
pub mod estilo;
pub mod externas;
pub mod ferramentas;
pub mod fila;
pub mod forja;
pub mod geracao;
pub mod gpu;
pub mod guia;
pub mod ignis;
pub mod janela;
pub mod licencas;
pub mod mcp;
pub mod movimento;
pub mod niveis;
pub mod pacotes;
pub mod partes;
pub mod paths;
pub mod plano;
pub mod programas;
pub mod projeto;
pub mod recibos;
pub mod servico;
pub mod util;
pub mod vistas;
pub mod workers;
