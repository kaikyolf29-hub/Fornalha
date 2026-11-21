//! Catálogo de modelos, licenças e roteador (quem pode tocar num projeto à venda).

use fornalha_core::licencas::{self, Catalogo, ContextoRota, Situacao, UsoComercial};
use fornalha_core::niveis::Nivel;

fn cat() -> Catalogo {
    Catalogo::embutido()
}

/// Projeto comercial numa NVIDIA, sem nada aceito e sem receita informada.
fn ctx_nvidia() -> ContextoRota {
    ContextoRota { comercial: true, cuda: true, receita_anual_usd: None, licencas_aceitas: vec![] }
}

#[test]
fn catalogo_embutido_e_coerente() {
    let c = cat();
    let erros = c.conferir();
    assert!(erros.is_empty(), "catálogo com problemas: {erros:#?}");
}

#[test]
fn todas_as_funcoes_do_plano_existem() {
    let c = cat();
    let ids: Vec<&str> = c.funcoes.iter().map(|f| f.id.as_str()).collect();
    assert_eq!(ids, ["cerebro", "imagem", "3d", "rig", "animacao", "efeitos", "musica", "voz", "boca", "video"]);
}

#[test]
fn bloqueados_do_plano_estao_marcados_como_nao_comerciais() {
    let c = cat();
    for id in ["flux2-dev", "flux2-klein-9b", "qwen-image-2.1", "omnivoice", "audiogen"] {
        let m = c.modelo(id).unwrap_or_else(|| panic!("faltou {id}"));
        assert_eq!(m.uso_comercial, UsoComercial::Nao, "{id}");
    }
}

#[test]
fn comerciais_com_condicao_do_plano() {
    let c = cat();
    assert_eq!(c.modelo("stable-audio-open").unwrap().teto_receita_usd, Some(1_000_000));
    assert_eq!(c.modelo("ltx-2").unwrap().teto_receita_usd, Some(10_000_000));
    for id in ["hy-motion-1.0", "hy-motion-lite", "hunyuan3d-2mini"] {
        assert_eq!(c.modelo(id).unwrap().aceite.as_deref(), Some("tencent-hunyuan"), "{id}");
    }
}

#[test]
fn modelo_nao_comercial_nunca_esta_num_nivel() {
    let c = cat();
    for (nivel, funcoes) in &c.niveis {
        for (funcao, ids) in funcoes {
            for id in ids {
                let m = c.modelo(id).unwrap();
                assert_ne!(m.uso_comercial, UsoComercial::Nao, "{id} em {nivel}/{funcao}");
            }
        }
    }
}

#[test]
fn nao_comercial_e_bloqueado_em_projeto_comercial() {
    let c = cat();
    let s = licencas::situacao(c.modelo("omnivoice").unwrap(), &ctx_nvidia());
    assert!(matches!(s, Situacao::Bloqueado { .. }), "{s:?}");
}

#[test]
fn nao_comercial_e_liberado_em_projeto_de_teste() {
    let c = cat();
    let ctx = ContextoRota { comercial: false, ..ctx_nvidia() };
    assert!(matches!(licencas::situacao(c.modelo("omnivoice").unwrap(), &ctx), Situacao::Liberado { .. }));
}

#[test]
fn dependencia_nao_comercial_bloqueia_o_modelo() {
    // TRELLIS.2 é MIT, mas a textura passa pelo nvdiffrast (NVIDIA, só pesquisa).
    let c = cat();
    let m = c.modelo("trellis2-1024-poucavram").unwrap();
    match licencas::situacao(m, &ctx_nvidia()) {
        Situacao::Bloqueado { motivo } => assert!(motivo.contains("nvdiffrast"), "{motivo}"),
        s => panic!("esperava bloqueado: {s:?}"),
    }
}

#[test]
fn licenca_com_aceite_precisa_do_aceite() {
    let c = cat();
    let m = c.modelo("hy-motion-1.0").unwrap();
    assert!(matches!(licencas::situacao(m, &ctx_nvidia()), Situacao::PrecisaAceite { .. }));
    let ctx = ContextoRota { licencas_aceitas: vec!["tencent-hunyuan".into()], ..ctx_nvidia() };
    assert!(matches!(licencas::situacao(m, &ctx), Situacao::Liberado { .. }));
}

#[test]
fn teto_de_receita_pergunta_e_depois_respeita() {
    let c = cat();
    let m = c.modelo("stable-audio-open").unwrap();
    assert!(matches!(licencas::situacao(m, &ctx_nvidia()), Situacao::PrecisaReceita { teto_usd: 1_000_000 }));
    let abaixo = ContextoRota { receita_anual_usd: Some(200_000), ..ctx_nvidia() };
    assert!(matches!(licencas::situacao(m, &abaixo), Situacao::Liberado { .. }));
    let acima = ContextoRota { receita_anual_usd: Some(1_000_000), ..ctx_nvidia() };
    assert!(matches!(licencas::situacao(m, &acima), Situacao::Bloqueado { .. }));
}

#[test]
fn roteador_escolhe_o_modelo_do_nivel() {
    let c = cat();
    let e = licencas::escolher(&c, "cerebro", Nivel::Qualidade, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.unwrap().id, "qwen3-14b");
    let e = licencas::escolher(&c, "musica", Nivel::Maximo, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.unwrap().id, "ace-step-1.5-xl");
    let e = licencas::escolher(&c, "imagem", Nivel::Leve, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.unwrap().id, "flux2-klein-4b-q");
}

#[test]
fn sem_aceite_da_tencent_a_animacao_cai_para_a_biblioteca() {
    let c = cat();
    let e = licencas::escolher(&c, "animacao", Nivel::Qualidade, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.as_ref().unwrap().id, "biblioteca-fornalha");
    assert!(e.recusados.iter().any(|r| r.modelo == "hy-motion-1.0-q"));
    let ctx = ContextoRota { licencas_aceitas: vec!["tencent-hunyuan".into()], ..ctx_nvidia() };
    let e = licencas::escolher(&c, "animacao", Nivel::Qualidade, &ctx).unwrap();
    assert_eq!(e.modelo.unwrap().id, "hy-motion-1.0-q");
}

#[test]
fn placa_sem_cuda_usa_a_opcao_que_nao_depende_de_cuda() {
    let c = cat();
    let amd = ContextoRota { cuda: false, ..ctx_nvidia() };
    let e = licencas::escolher(&c, "rig", Nivel::Qualidade, &amd).unwrap();
    assert_eq!(e.modelo.as_ref().unwrap().id, "rigify-blender");
    let r = e.recusados.iter().find(|r| r.modelo == "unirig").expect("UniRig recusado");
    assert!(r.motivo.contains("CUDA"), "{}", r.motivo);
    // com NVIDIA o UniRig vale
    let e = licencas::escolher(&c, "rig", Nivel::Qualidade, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.unwrap().id, "unirig");
}

#[test]
fn nada_liberado_explica_cada_recusa() {
    // Projeto comercial, sem aceite da Tencent: o TRELLIS.2 (nvdiffrast) e o Hunyuan3D ficam de fora
    // e a Forja da Fornalha entra, com o motivo de cada recusa.
    let c = cat();
    let e = licencas::escolher(&c, "3d", Nivel::Maximo, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.as_ref().unwrap().id, "forja-3d");
    assert!(e.recusados.iter().any(|r| r.modelo.starts_with("trellis2")));
    assert!(e.recusados.iter().all(|r| !r.motivo.is_empty()));
}

#[test]
fn opcao_de_nivel_mais_baixo_e_usada_com_aviso() {
    // Vídeo no Leve é só captura do jogo; no Qualidade há Wan 2.2.
    let c = cat();
    let e = licencas::escolher(&c, "video", Nivel::Leve, &ctx_nvidia()).unwrap();
    assert!(e.modelo.is_none(), "no Leve o trailer usa só captura do jogo");
    // Sem vídeo no Leve nem fallback, nenhuma opção; com o Leve tendo opção, a escolha desce de nível com aviso.
    let ctx = ContextoRota { licencas_aceitas: vec!["tencent-hunyuan".into()], ..ctx_nvidia() };
    let e = licencas::escolher(&c, "video", Nivel::Equilibrado, &ctx).unwrap();
    assert_eq!(e.modelo.as_ref().unwrap().id, "wan2.2-5b-gguf");
    let amd = ContextoRota { cuda: false, ..ctx_nvidia() };
    let e = licencas::escolher(&c, "boca", Nivel::Maximo, &amd).unwrap();
    assert_eq!(e.modelo.as_ref().unwrap().id, "boca-fornalha", "sem CUDA o Audio2Face sai e a boca pela voz entra");
}

#[test]
fn funcao_desconhecida_e_erro() {
    let e = licencas::escolher(&cat(), "teletransporte", Nivel::Leve, &ctx_nvidia()).unwrap_err();
    assert_eq!(e.codigo, "funcao_desconhecida");
}

#[test]
fn obrigacoes_do_modelo_vem_na_escolha() {
    let c = cat();
    let e = licencas::escolher(&c, "voz", Nivel::Equilibrado, &ctx_nvidia()).unwrap();
    assert_eq!(e.modelo.as_ref().unwrap().id, "chatterbox-ptbr");
    assert!(e.obrigacoes.iter().any(|o| o.contains("marca d'água")), "{:?}", e.obrigacoes);
}

#[test]
fn regras_de_provedor_do_plano() {
    let c = cat();
    assert!(c.modelo("meshy-gratis").unwrap().obrigacoes.iter().any(|o| o.contains("CC BY 4.0")));
    assert!(c.modelo("mixamo").unwrap().obrigacoes.iter().any(|o| o.contains("pacote de assets")));
}
