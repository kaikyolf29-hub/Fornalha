//! Bíblia do jogo (game.project.json): criar, abrir e atualizar projetos.

use fornalha_core::projeto::{self, NovoProjeto, ARQUIVO_BIBLIA, PASTAS_PADRAO};
use serde_json::json;

fn novo(nome: &str) -> NovoProjeto {
    NovoProjeto { nome: nome.into(), ..Default::default() }
}

#[test]
fn criar_projeto_faz_as_pastas_padrao_e_a_biblia() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Reino de Cinzas"), tmp.path()).unwrap();

    assert_eq!(p.raiz, tmp.path().join("reino-de-cinzas"));
    for pasta in PASTAS_PADRAO {
        assert!(p.raiz.join(pasta).is_dir(), "faltou a pasta {pasta}");
    }
    assert!(p.raiz.join(ARQUIVO_BIBLIA).is_file());
    assert!(p.raiz.join("ai/recibos.jsonl").is_file(), "banco de recibos nasce vazio");
    assert_eq!(p.biblia.nome, "Reino de Cinzas");
    assert_eq!(p.biblia.formato, 1);
    assert!(p.biblia.comercial, "projeto nasce comercial: só modelo que deixa vender");
    assert_eq!(p.biblia.engine, "godot");
    assert_eq!(p.biblia.id.len(), 16);
    assert!(p.biblia.criado_em.ends_with('Z'));
}

#[test]
fn as_pastas_sao_as_do_plano() {
    assert_eq!(
        PASTAS_PADRAO,
        [
            "GameDesign",
            "World",
            "Characters",
            "Enemies",
            "Items",
            "Weapons",
            "Animations",
            "Audio",
            "VFX",
            "Cutscenes",
            "UI",
            "Scripts",
            "blender",
            "ai"
        ]
    );
}

#[test]
fn pasta_pai_e_nome_da_pasta_podem_ser_escolhidos() {
    let tmp = tempfile::tempdir().unwrap();
    let pai = tmp.path().join("meus jogos");
    let n = NovoProjeto { nome: "Teste".into(), pasta_pai: Some(pai.clone()), pasta: Some("teste-1".into()), ..Default::default() };
    let p = projeto::criar(&n, tmp.path().join("ignorada").as_path()).unwrap();
    assert_eq!(p.raiz, pai.join("teste-1"));
}

#[test]
fn conceito_inicial_vai_para_a_biblia() {
    let tmp = tempfile::tempdir().unwrap();
    let mut n = novo("Action RPG");
    n.comercial = Some(false);
    n.conceito =
        Some(serde_json::from_value(json!({"genero": "action RPG", "camera": "terceira pessoa", "estilo": "estilizado"})).unwrap());
    let p = projeto::criar(&n, tmp.path()).unwrap();
    assert!(!p.biblia.comercial);
    assert_eq!(p.biblia.conceito.genero, "action RPG");
    assert_eq!(p.biblia.conceito.camera, "terceira pessoa");
}

#[test]
fn nome_da_pasta_tira_acento_e_simbolo() {
    assert_eq!(projeto::nome_de_pasta("Reino de Cinzas"), "reino-de-cinzas");
    assert_eq!(projeto::nome_de_pasta("  Ação & Coração!  "), "acao-coracao");
    assert_eq!(projeto::nome_de_pasta("???"), "projeto");
    assert_eq!(projeto::nome_de_pasta("CON"), "con-projeto", "nome reservado do Windows");
    assert_eq!(projeto::nome_de_pasta("../../etc"), "etc");
    assert!(projeto::nome_de_pasta(&"a".repeat(200)).len() <= 64);
}

#[test]
fn nome_vazio_ou_com_quebra_de_linha_e_recusado() {
    let tmp = tempfile::tempdir().unwrap();
    for nome in ["", "   ", "linha\nquebrada", &"x".repeat(81)] {
        let e = projeto::criar(&novo(nome), tmp.path()).unwrap_err();
        assert_eq!(e.codigo, "nome_invalido", "{nome:?}");
    }
}

#[test]
fn nome_de_pasta_escolhido_nao_pode_sair_da_pasta_pai() {
    let tmp = tempfile::tempdir().unwrap();
    for pasta in ["../fora", "a/b", "a\\b", "..", ""] {
        let n = NovoProjeto { nome: "X".into(), pasta: Some(pasta.into()), ..Default::default() };
        let e = projeto::criar(&n, tmp.path()).unwrap_err();
        assert_eq!(e.codigo, "pasta_invalida", "{pasta:?}");
    }
}

#[test]
fn nao_cria_por_cima_de_pasta_com_coisas() {
    let tmp = tempfile::tempdir().unwrap();
    let alvo = tmp.path().join("meu-jogo");
    std::fs::create_dir_all(&alvo).unwrap();
    std::fs::write(alvo.join("importante.txt"), "não apagar").unwrap();
    let e = projeto::criar(&novo("Meu Jogo"), tmp.path()).unwrap_err();
    assert_eq!(e.codigo, "pasta_ja_existe");
    assert_eq!(std::fs::read_to_string(alvo.join("importante.txt")).unwrap(), "não apagar");
}

#[test]
fn pasta_vazia_ja_existente_pode_virar_projeto() {
    let tmp = tempfile::tempdir().unwrap();
    std::fs::create_dir_all(tmp.path().join("meu-jogo")).unwrap();
    assert!(projeto::criar(&novo("Meu Jogo"), tmp.path()).is_ok());
}

#[test]
fn abrir_pela_pasta_ou_pelo_arquivo() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Abrir"), tmp.path()).unwrap();
    let a = projeto::abrir(&p.raiz).unwrap();
    let b = projeto::abrir(&p.raiz.join(ARQUIVO_BIBLIA)).unwrap();
    assert_eq!(a.biblia, p.biblia);
    assert_eq!(b.raiz, p.raiz);
}

#[test]
fn abrir_pasta_sem_biblia_explica_o_problema() {
    let tmp = tempfile::tempdir().unwrap();
    let e = projeto::abrir(tmp.path()).unwrap_err();
    assert_eq!(e.codigo, "nao_e_projeto");
    assert!(e.mensagem.contains(ARQUIVO_BIBLIA));
}

#[test]
fn biblia_corrompida_e_avisada() {
    let tmp = tempfile::tempdir().unwrap();
    std::fs::write(tmp.path().join(ARQUIVO_BIBLIA), "{ isto não é json").unwrap();
    assert_eq!(projeto::abrir(tmp.path()).unwrap_err().codigo, "biblia_invalida");
}

#[test]
fn atualizar_mescla_so_o_que_veio() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Mesclar"), tmp.path()).unwrap();
    let b = projeto::atualizar(&p.raiz, &json!({"conceito": {"genero": "plataforma 3D", "mecanicas": ["pulo duplo"]}})).unwrap();
    assert_eq!(b.conceito.genero, "plataforma 3D");
    assert_eq!(b.conceito.mecanicas, vec!["pulo duplo"]);
    let b = projeto::atualizar(&p.raiz, &json!({"conceito": {"camera": "isométrica"}})).unwrap();
    assert_eq!(b.conceito.genero, "plataforma 3D", "o resto fica");
    assert_eq!(b.conceito.camera, "isométrica");
    // gravou no disco
    assert_eq!(projeto::abrir(&p.raiz).unwrap().biblia.conceito.camera, "isométrica");
}

#[test]
fn atualizar_com_null_apaga_o_campo() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Apagar"), tmp.path()).unwrap();
    projeto::atualizar(&p.raiz, &json!({"nivel": "qualidade"})).unwrap();
    let b = projeto::atualizar(&p.raiz, &json!({"nivel": null})).unwrap();
    assert_eq!(b.nivel, None);
}

#[test]
fn campos_que_a_fornalha_controla_nao_mudam() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Protegido"), tmp.path()).unwrap();
    for campo in ["id", "formato", "criado_em", "atualizado_em"] {
        let e = projeto::atualizar(&p.raiz, &json!({ campo: "outro" })).unwrap_err();
        assert_eq!(e.codigo, "campo_protegido", "{campo}");
    }
    assert_eq!(projeto::abrir(&p.raiz).unwrap().biblia, p.biblia, "nada foi gravado");
}

#[test]
fn atualizar_valida_antes_de_gravar() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Validar"), tmp.path()).unwrap();
    let ruins = [
        json!({"nivel": "ultra"}),
        json!({"nome": ""}),
        json!({"comercial": "talvez"}),
        json!({"guia_visual": {"paleta": ["vermelho"]}}),
        json!({"personagens": [{"id": "heroi", "nome": "A"}, {"id": "heroi", "nome": "B"}]}),
        json!({"personagens": [{"id": "", "nome": "Sem id"}]}),
        json!({"mundo": {"areas": [{"id": "vila", "nome": "Vila"}, {"id": "vila", "nome": "Outra"}]}}),
    ];
    for r in ruins {
        let e = projeto::atualizar(&p.raiz, &r).unwrap_err();
        assert_eq!(e.codigo, "biblia_invalida", "{r}");
    }
    assert_eq!(projeto::abrir(&p.raiz).unwrap().biblia, p.biblia, "nada foi gravado");
}

#[test]
fn personagens_mundo_e_guia_visual_sao_guardados() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Completo"), tmp.path()).unwrap();
    let b = projeto::atualizar(
        &p.raiz,
        &json!({
            "guia_visual": {"paleta": ["#1a2b3c", "#FFAA00"], "traco": "cel shading", "evitar": ["neon"],
                            "referencias": [{"arquivo": "ai/referencias/vila.png", "aprovada": true}]},
            "personagens": [{"id": "heroi", "nome": "Aren", "papel": "protagonista", "roupa": "armadura leve", "arma": "machado"}],
            "mundo": {"areas": [{"id": "vila", "nome": "Vila de Brasa", "tipo": "vila"}]}
        }),
    )
    .unwrap();
    assert_eq!(b.guia_visual.paleta.len(), 2);
    assert!(b.guia_visual.referencias[0].aprovada);
    assert_eq!(b.personagens[0].arma, "machado");
    assert_eq!(b.mundo.areas[0].nome, "Vila de Brasa");
}

#[test]
fn campos_desconhecidos_sao_preservados() {
    // O agente (ou uma versão mais nova da Fornalha) pode guardar coisas que esta versão não conhece.
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Futuro"), tmp.path()).unwrap();
    projeto::atualizar(&p.raiz, &json!({"trilha": {"tema": "épico"}, "conceito": {"chefes": 3}})).unwrap();
    projeto::atualizar(&p.raiz, &json!({"conceito": {"genero": "soulslike"}})).unwrap();
    let texto = std::fs::read_to_string(p.raiz.join(ARQUIVO_BIBLIA)).unwrap();
    let v: serde_json::Value = serde_json::from_str(&texto).unwrap();
    assert_eq!(v["trilha"]["tema"], "épico");
    assert_eq!(v["conceito"]["chefes"], 3);
    assert_eq!(v["conceito"]["genero"], "soulslike");
}

#[test]
fn atualizado_em_muda_e_criado_em_fica() {
    let tmp = tempfile::tempdir().unwrap();
    let p = projeto::criar(&novo("Datas"), tmp.path()).unwrap();
    let b = projeto::atualizar(&p.raiz, &json!({"conceito": {"publico": "adolescentes"}})).unwrap();
    assert_eq!(b.criado_em, p.biblia.criado_em);
    assert!(b.atualizado_em >= p.biblia.atualizado_em);
}

#[test]
fn data_iso_em_utc() {
    assert_eq!(fornalha_core::util::iso_utc(0), "1970-01-01T00:00:00Z");
    assert_eq!(fornalha_core::util::iso_utc(1_795_132_800), "2026-11-20T00:00:00Z");
    assert_eq!(fornalha_core::util::iso_utc(951_782_400), "2000-02-29T00:00:00Z", "ano bissexto");
}
