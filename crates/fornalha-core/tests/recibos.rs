//! Recibo de licença por asset, pendências antes de vender e relatório de créditos.

use std::path::Path;

use fornalha_core::licencas::{Catalogo, ContextoRota};
use fornalha_core::projeto::{self, NovoProjeto, Projeto, ARQUIVO_RECIBOS};
use fornalha_core::recibos::{self, NovoRecibo, MODELO_AUTORAL};

fn projeto_em(dir: &Path, comercial: bool) -> Projeto {
    let n = NovoProjeto { nome: "Recibos".into(), comercial: Some(comercial), ..Default::default() };
    projeto::criar(&n, dir).unwrap()
}

fn ctx(p: &Projeto) -> ContextoRota {
    ContextoRota { comercial: p.biblia.comercial, cuda: true, receita_anual_usd: None, licencas_aceitas: vec![] }
}

fn asset(p: &Projeto, rel: &str, conteudo: &[u8]) {
    let f = p.raiz.join(rel);
    std::fs::create_dir_all(f.parent().unwrap()).unwrap();
    std::fs::write(f, conteudo).unwrap();
}

fn pedido(arquivo: &str, modelo: &str) -> NovoRecibo {
    NovoRecibo {
        arquivo: arquivo.into(),
        modelo: modelo.into(),
        prompt: Some("herói com machado".into()),
        seed: Some(42),
        quem_pediu: Some("claude-code".into()),
        ..Default::default()
    }
}

#[test]
fn registrar_guarda_tudo_que_o_plano_pede() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Characters/heroi/conceito.png", b"png falso");
    let mut n = pedido("Characters/heroi/conceito.png", "flux2-klein-4b");
    n.referencias = vec!["ai/referencias/estilo.png".into()];
    n.versao = Some("2026-10".into());
    let r = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), n).unwrap();

    assert_eq!(r.arquivo, "Characters/heroi/conceito.png");
    assert_eq!(r.sha256.len(), 64);
    assert_eq!(r.tamanho_bytes, 9);
    assert_eq!(r.modelo.id, "flux2-klein-4b");
    assert_eq!(r.modelo.licenca, "Apache 2.0");
    assert!(r.modelo.url_licenca.starts_with("https://"));
    assert_eq!(r.modelo.versao.as_deref(), Some("2026-10"));
    assert_eq!(r.funcao, "imagem");
    assert_eq!(r.prompt.as_deref(), Some("herói com machado"));
    assert_eq!(r.referencias, vec!["ai/referencias/estilo.png"]);
    assert_eq!(r.seed, Some(42));
    assert_eq!(r.quem_pediu, "claude-code");
    assert!(r.criado_em.ends_with('Z'));
    assert!(r.projeto_comercial);

    let linhas = std::fs::read_to_string(p.raiz.join(ARQUIVO_RECIBOS)).unwrap();
    assert_eq!(linhas.lines().count(), 1, "uma linha JSON por recibo");
    assert_eq!(recibos::listar(&p.raiz).unwrap(), vec![r]);
}

#[test]
fn quem_pediu_padrao_e_a_pessoa() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "UI/botao.png", b"x");
    let n = NovoRecibo { arquivo: "UI/botao.png".into(), modelo: "flux2-klein-4b".into(), ..Default::default() };
    assert_eq!(recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), n).unwrap().quem_pediu, "pessoa");
}

#[test]
fn barra_invertida_do_windows_vira_barra_normal() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Audio/passo.wav", b"wav");
    let r = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Audio\\passo.wav", "moss-soundeffect-v2")).unwrap();
    assert_eq!(r.arquivo, "Audio/passo.wav");
}

#[test]
fn caminho_absoluto_dentro_do_projeto_vira_relativo() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Audio/chuva.wav", b"wav");
    let abs = p.raiz.join("Audio/chuva.wav").to_string_lossy().into_owned();
    let r = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido(&abs, "moss-soundeffect-v2")).unwrap();
    assert_eq!(r.arquivo, "Audio/chuva.wav");
}

#[test]
fn arquivo_fora_do_projeto_e_recusado() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    std::fs::write(tmp.path().join("fora.png"), b"x").unwrap();
    let fora_abs = tmp.path().join("fora.png").to_string_lossy().into_owned();
    for caminho in ["../fora.png", fora_abs.as_str()] {
        let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido(caminho, "flux2-klein-4b")).unwrap_err();
        assert_eq!(e.codigo, "arquivo_fora_do_projeto", "{caminho}");
    }
}

#[test]
fn arquivos_da_propria_fornalha_nao_levam_recibo() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    for caminho in ["game.project.json", "ai/recibos.jsonl"] {
        let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido(caminho, "flux2-klein-4b")).unwrap_err();
        assert_eq!(e.codigo, "arquivo_invalido", "{caminho}");
    }
}

#[test]
fn arquivo_que_nao_existe_e_recusado() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Items/nada.glb", "trellis2-512")).unwrap_err();
    assert_eq!(e.codigo, "arquivo_nao_encontrado");
}

#[test]
fn modelo_fora_do_catalogo_e_recusado() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Items/espada.glb", b"glb");
    let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Items/espada.glb", "modelo-misterioso")).unwrap_err();
    assert_eq!(e.codigo, "modelo_desconhecido");
}

#[test]
fn projeto_comercial_recusa_modelo_nao_comercial_e_nao_grava_nada() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Audio/fala.wav", b"wav");
    let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Audio/fala.wav", "omnivoice")).unwrap_err();
    assert_eq!(e.codigo, "licenca_bloqueada");
    assert!(recibos::listar(&p.raiz).unwrap().is_empty());
}

#[test]
fn licenca_com_condicao_precisa_do_aceite() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Animations/ataque.glb", b"glb");
    let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Animations/ataque.glb", "hy-motion-1.0")).unwrap_err();
    assert_eq!(e.codigo, "precisa_aceite");
    let mut c = ctx(&p);
    c.licencas_aceitas.push("tencent-hunyuan".into());
    assert!(recibos::registrar(&p, &Catalogo::embutido(), &c, pedido("Animations/ataque.glb", "hy-motion-1.0")).is_ok());
}

#[test]
fn teto_de_receita_precisa_da_receita() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Audio/vento.wav", b"wav");
    let e = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Audio/vento.wav", "stable-audio-open")).unwrap_err();
    assert_eq!(e.codigo, "precisa_receita");
}

#[test]
fn obrigacoes_do_modelo_vao_para_o_recibo() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "Audio/dublagem/aren_01.wav", b"wav");
    let r = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("Audio/dublagem/aren_01.wav", "chatterbox-ptbr")).unwrap();
    assert!(r.obrigacoes.iter().any(|o| o.contains("marca d'água")));
}

#[test]
fn asset_feito_a_mao_leva_recibo_autoral() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "UI/logo.png", b"png");
    let r = recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("UI/logo.png", MODELO_AUTORAL)).unwrap();
    assert_eq!(r.funcao, "autoral");
    assert!(!r.gerado_por_ia());
}

#[test]
fn linha_corrompida_nao_derruba_a_lista() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    asset(&p, "UI/a.png", b"a");
    recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("UI/a.png", "flux2-klein-4b")).unwrap();
    use std::io::Write;
    let mut f = std::fs::OpenOptions::new().append(true).open(p.raiz.join(ARQUIVO_RECIBOS)).unwrap();
    writeln!(f, "{{ linha quebrada").unwrap();
    asset(&p, "UI/b.png", b"b");
    recibos::registrar(&p, &Catalogo::embutido(), &ctx(&p), pedido("UI/b.png", "flux2-klein-4b")).unwrap();
    let lista = recibos::listar(&p.raiz).unwrap();
    assert_eq!(lista.iter().map(|r| r.arquivo.as_str()).collect::<Vec<_>>(), ["UI/a.png", "UI/b.png"]);
}

#[test]
fn pendencias_antes_de_vender() {
    let tmp = tempfile::tempdir().unwrap();
    // Começou como projeto de teste e usou um modelo não comercial.
    let p = projeto_em(tmp.path(), false);
    let cat = Catalogo::embutido();
    asset(&p, "Audio/teste.wav", b"wav");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Audio/teste.wav", "omnivoice")).unwrap();
    asset(&p, "Items/pocao.png", b"v1");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Items/pocao.png", "flux2-klein-4b")).unwrap();
    asset(&p, "Items/pocao.png", b"v2 editada");
    asset(&p, "Weapons/machado.glb", b"glb");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Weapons/machado.glb", "trellis2-512")).unwrap();
    std::fs::remove_file(p.raiz.join("Weapons/machado.glb")).unwrap();
    asset(&p, "Characters/sem_recibo.png", b"?");
    asset(&p, "blender/trabalho.blend", b"ignorado");
    asset(&p, "Scripts/jogador.gd", b"codigo nao e asset");

    let pend = recibos::pendencias(&p, &cat, &ContextoRota { comercial: true, ..ctx(&p) }).unwrap();
    assert_eq!(pend.bloqueiam_venda.iter().map(|x| x.arquivo.as_str()).collect::<Vec<_>>(), ["Audio/teste.wav"]);
    assert_eq!(pend.sem_recibo, ["Characters/sem_recibo.png"]);
    assert_eq!(pend.alterados, ["Items/pocao.png"]);
    assert_eq!(pend.sumidos, ["Weapons/machado.glb"]);
    assert!(!pend.pode_vender());
}

#[test]
fn recibo_novo_do_mesmo_arquivo_vale_mais_que_o_antigo() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), false);
    let cat = Catalogo::embutido();
    asset(&p, "Audio/fala.wav", b"v1");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Audio/fala.wav", "omnivoice")).unwrap();
    asset(&p, "Audio/fala.wav", b"v2 refeita com chatterbox");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Audio/fala.wav", "chatterbox-ptbr")).unwrap();
    let pend = recibos::pendencias(&p, &cat, &ContextoRota { comercial: true, ..ctx(&p) }).unwrap();
    assert!(pend.bloqueiam_venda.is_empty(), "{:?}", pend.bloqueiam_venda);
    assert!(pend.pode_vender());
}

#[test]
fn relatorio_de_creditos_e_licencas() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto_em(tmp.path(), true);
    let cat = Catalogo::embutido();
    asset(&p, "Characters/heroi.png", b"png");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Characters/heroi.png", "flux2-klein-4b")).unwrap();
    asset(&p, "Audio/fala.wav", b"wav");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("Audio/fala.wav", "chatterbox-ptbr")).unwrap();
    asset(&p, "UI/logo.png", b"png");
    recibos::registrar(&p, &cat, &ctx(&p), pedido("UI/logo.png", MODELO_AUTORAL)).unwrap();

    let rel = recibos::relatorio(&p, &cat, &ctx(&p)).unwrap();
    assert!(rel.markdown.contains("FLUX.2 klein 4B"));
    assert!(rel.markdown.contains("Apache 2.0"));
    assert!(rel.markdown.contains("Chatterbox"));
    assert!(rel.markdown.contains("marca d'água"), "obrigações aparecem");
    assert!(rel.markdown.contains("Steam"), "seção para o formulário de IA da Steam");
    assert!(rel.markdown.contains("Characters/heroi.png"));
    assert_eq!(rel.assets_com_ia, 2);
    assert_eq!(rel.assets_autorais, 1);
    let salvo = std::fs::read_to_string(p.raiz.join("ai/creditos-e-licencas.md")).unwrap();
    assert_eq!(salvo, rel.markdown);
    assert_eq!(rel.arquivo, p.raiz.join("ai/creditos-e-licencas.md"));
}
