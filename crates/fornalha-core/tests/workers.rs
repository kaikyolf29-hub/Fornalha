//! Workers de placa (TRELLIS.2, HY-Motion, UniRig) de ponta a ponta, sem placa:
//! o worker de verdade da Fornalha roda com um modelo "de mentira" que tem a mesma
//! interface (tests/workers_falsos), e o resultado passa pelo Blender, pelo
//! roteador de licenças e pelos recibos como numa máquina com placa NVIDIA.
//! Precisa do Python com numpy e Pillow e do Blender (FORNALHA_TESTE_BLENDER).

mod comum;

use std::path::{Path, PathBuf};
use std::sync::Arc;

use fornalha_core::externas::{self, Programa};
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use fornalha_core::workers::{self, Worker};
use serde_json::{json, Value};

fn falsos() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/workers_falsos")
}

fn copiar(de: &Path, para: &Path) {
    std::fs::create_dir_all(para).unwrap();
    for e in std::fs::read_dir(de).unwrap().flatten() {
        let alvo = para.join(e.file_name());
        if e.path().is_dir() {
            copiar(&e.path(), &alvo);
        } else {
            std::fs::copy(e.path(), alvo).unwrap();
        }
    }
}

/// Python do sistema com numpy e Pillow (o que os workers precisam fora do modelo).
async fn python() -> Option<PathBuf> {
    let p = workers::python_do_sistema().await?;
    let s = externas::rodar(&p, &["-c", "import numpy, PIL; print('ok')"], std::time::Duration::from_secs(60), None).await.ok()?;
    s.stdout.contains("ok").then_some(p)
}

/// "Instala" um worker de mentira: o repositório falso e o Python do sistema.
fn instalar_falso(paths: &Paths, w: Worker, repo_falso: &str, python: &Path) -> PathBuf {
    let pasta = workers::pasta(paths, w);
    let repo = pasta.join("repo");
    copiar(&falsos().join(repo_falso), &repo);
    let info = json!({"worker": w.id(), "python": python, "repo": repo, "instalado_em": "teste", "sem": []});
    std::fs::write(pasta.join("instalacao.json"), serde_json::to_vec_pretty(&info).unwrap()).unwrap();
    repo
}

async fn fornalha(dir: &Path) -> Option<(Arc<Fornalha>, PathBuf)> {
    let py = python().await;
    let blender = externas::achar_para_teste(Programa::Blender).await;
    let (Some(py), Some(blender)) = (py, blender) else {
        eprintln!("Python com numpy/Pillow ou Blender não encontrados: teste pulado");
        return None;
    };
    // placa NVIDIA (CUDA) de mentira: o roteador escolhe os modelos de placa
    let f = Fornalha::para_testes(Paths::under(dir), comum::detection("rtx4060ti16-windows"));
    f.definir_programa(Programa::Blender, Some(blender.caminho)).await.unwrap();
    f.definir_porta_ignis(1).unwrap(); // sem Ignis: a ficha sai das regras
    Some((f, py))
}

async fn chamar(f: &Fornalha, nome: &str, args: Value) -> Value {
    match f.chamar(nome, args, "claude-code").await {
        Ok(v) => v,
        Err(e) => panic!("{nome} falhou: {} ({})", e.mensagem, e.codigo),
    }
}

fn imagem_de_teste(py: &Path, arquivo: &Path) {
    std::fs::create_dir_all(arquivo.parent().unwrap()).unwrap();
    let codigo = "import sys; from PIL import Image, ImageDraw\n\
                  i = Image.new('RGB', (256, 256), (200, 30, 30)); d = ImageDraw.Draw(i)\n\
                  d.rectangle((0, 128, 256, 256), fill=(30, 50, 210)); i.save(sys.argv[1])";
    let s = std::process::Command::new(py).args(["-c", codigo, &arquivo.to_string_lossy()]).output().unwrap();
    assert!(s.status.success(), "{}", String::from_utf8_lossy(&s.stderr));
}

#[test]
fn sem_nada_instalado_nenhum_worker_aparece() {
    let tmp = tempfile::tempdir().unwrap();
    let paths = Paths::under(tmp.path());
    let e = workers::estado(&paths);
    assert_eq!(e.as_array().unwrap().len(), 3);
    assert!(e.as_array().unwrap().iter().all(|w| w["instalado"] == false));
    assert!(workers::sem_dependencias(&paths).is_empty());
    assert_eq!(Worker::do_modelo("trellis2-1024-poucavram"), Some(Worker::Trellis2));
    assert_eq!(Worker::do_modelo("hy-motion-lite"), Some(Worker::HyMotion));
    assert_eq!(Worker::do_modelo("unirig"), Some(Worker::UniRig));
    assert_eq!(Worker::do_modelo("forja-3d"), None);
    assert_eq!(Worker::HyMotion.aceite(), Some("tencent-hunyuan"));
}

#[test]
fn instalacao_cujo_python_sumiu_nao_vale() {
    let tmp = tempfile::tempdir().unwrap();
    let paths = Paths::under(tmp.path());
    let pasta = workers::pasta(&paths, Worker::Trellis2);
    std::fs::create_dir_all(pasta.join("repo")).unwrap();
    let info = json!({"worker": "trellis2", "python": pasta.join("nao-existe"), "repo": pasta.join("repo"), "sem": ["nvdiffrast"], "verificado_em": "x"});
    std::fs::write(pasta.join("instalacao.json"), info.to_string()).unwrap();
    assert!(workers::instalacao(&paths, Worker::Trellis2).is_none());
    assert!(workers::sem_dependencias(&paths).is_empty(), "sem instalação válida, nada é liberado");
}

#[tokio::test]
async fn trellis_de_mentira_vira_modelo_com_textura_e_libera_venda_depois_da_verificacao() {
    let tmp = tempfile::tempdir().unwrap();
    let Some((f, py)) = fornalha(tmp.path()).await else { return };
    instalar_falso(&f.paths, Worker::Trellis2, "trellis2", &py);
    let p = chamar(&f, "create_project", json!({"nome": "Estátuas"})).await;
    let raiz = PathBuf::from(p["raiz"].as_str().unwrap());

    // antes da verificação, o projeto comercial não aceita o TRELLIS.2 (nvdiffrast)
    let e = chamar(&f, "choose_model", json!({"funcao": "3d"})).await;
    assert_eq!(e["modelo"]["id"], "humano-fornalha", "{e}");
    imagem_de_teste(&py, &raiz.join("ai/conceitos/estatua.png"));
    let err = f.chamar("generate_3d", json!({"imagem": "ai/conceitos/estatua.png", "nome": "estatua"}), "claude-code").await.unwrap_err();
    assert_eq!(err.codigo, "sem_modelo_de_imagem_para_3d", "{}", err.mensagem);

    // a verificação roda o worker de verdade: o nvdiffrast fica de fora (só o substituto)
    let v = workers::verificar(&f.paths, Worker::Trellis2).await.unwrap();
    eprintln!("verificação: {v}");
    assert_eq!(v["sem"], json!(["nvdiffrast"]));
    assert_eq!(v["resultado"]["proibidos_carregados"], json!([]));
    let e = chamar(&f, "choose_model", json!({"funcao": "3d"})).await;
    let modelo = e["modelo"]["id"].as_str().unwrap().to_string();
    assert!(modelo.starts_with("trellis2"), "{e}");

    // imagem → TRELLIS.2 → Blender (textura assada) → glb com colisão e recibo
    let r = chamar(&f, "generate_3d", json!({"imagem": "ai/conceitos/estatua.png", "nome": "estatua", "altura_m": 1.2})).await;
    eprintln!("generate_3d: {}", serde_json::to_string_pretty(&r).unwrap());
    assert!(raiz.join("Items/estatua.glb").is_file());
    assert_eq!(r["modelo"], modelo);
    let assar = &r["estatisticas"]["assar"];
    assert!(assar["triangulos"].as_u64().unwrap() <= 20000);
    assert!(assar["triangulos_da_malha_alta"].as_u64().unwrap() > assar["triangulos"].as_u64().unwrap());
    assert!(assar["cobertura_da_textura"].as_f64().unwrap() > 0.2, "{assar}");
    let cor = assar["cor_media"].as_array().unwrap();
    let (vermelho, verde, azul) = (cor[0].as_f64().unwrap(), cor[1].as_f64().unwrap(), cor[2].as_f64().unwrap());
    assert!(vermelho > verde && azul > verde, "as cores da imagem chegaram na textura: {cor:?}");
    assert!((assar["altura_m"].as_f64().unwrap() - 1.2).abs() < 0.01);
    assert!(r["estatisticas"]["trellis"]["cores_achadas"].as_f64().unwrap() > 0.95);
    // o pipeline.json oficial pede o RMBG-2.0 (não comercial): a Fornalha usa o BiRefNet (MIT)
    assert_eq!(r["estatisticas"]["trellis"]["removedor_de_fundo"], "ZhengPeng7/BiRefNet", "{r}");

    let recibos = chamar(&f, "list_receipts", json!({})).await;
    let lista = recibos["recibos"].as_array().unwrap();
    assert!(lista.iter().any(|x| x["arquivo"] == "Items/estatua.glb" && x["modelo"]["id"] == modelo.as_str()), "{recibos}");
    let pend = chamar(&f, "check_licenses", json!({})).await;
    assert_eq!(pend["pode_vender"], true, "{pend}");
    if let Ok(d) = std::env::var("FORNALHA_TESTE_SAIDA") {
        std::fs::create_dir_all(&d).unwrap();
        for (de, para) in [("Items/estatua.glb", "trellis_estatua.glb"), ("Items/estatua.previa.png", "trellis_estatua.previa.png")] {
            let _ = std::fs::copy(raiz.join(de), Path::new(&d).join(para));
        }
    }
}

#[tokio::test]
async fn hymotion_de_mentira_vira_animacao_nova_no_esqueleto_padrao() {
    let tmp = tempfile::tempdir().unwrap();
    let Some((f, py)) = fornalha(tmp.path()).await else { return };
    instalar_falso(&f.paths, Worker::HyMotion, "hymotion", &py);
    chamar(&f, "create_project", json!({"nome": "Movimentos"})).await;
    chamar(&f, "create_character", json!({"nome": "Aren", "arma": "espada", "conceito": false})).await;

    // sem o aceite da Tencent (só pela janela), o movimento por texto não roda
    let err = f
        .chamar("generate_animation", json!({"arquivo": "Characters/aren/aren.glb", "descricao": "acena para o jogador"}), "claude-code")
        .await
        .unwrap_err();
    assert_eq!(err.codigo, "sem_modelo_de_movimento", "{}", err.mensagem);
    assert!(err.mensagem.contains("parado"), "lista a biblioteca como alternativa: {}", err.mensagem);

    f.definir_estudio(fornalha_core::config::Estudio { receita_anual_usd: None, licencas_aceitas: vec!["tencent-hunyuan".into()] })
        .unwrap();
    let r = chamar(
        &f,
        "generate_animation",
        json!({"arquivo": "Characters/aren/aren.glb", "descricao": "abaixa os braços devagar", "nome_animacao": "abaixar", "segundos": 2}),
    )
    .await;
    eprintln!("generate_animation: {}", serde_json::to_string_pretty(&r["estatisticas"]["posicoes"]).unwrap());
    assert!(r["modelo"].as_str().unwrap().starts_with("hy-motion"), "{r}");
    let nomes: Vec<&str> = r["estatisticas"]["animacoes"].as_array().unwrap().iter().filter_map(|a| a["nome"].as_str()).collect();
    assert!(nomes.contains(&"abaixar") && nomes.contains(&"andar") && nomes.contains(&"atacar"), "{nomes:?}");
    let mao = &r["estatisticas"]["posicoes"]["LeftHand"];
    let (z0, z1) = (mao["inicio"][2].as_f64().unwrap(), mao["fim"][2].as_f64().unwrap());
    assert!(z0 - z1 > 0.4, "o braço desceu: {z0} → {z1}");
    assert_eq!(r["movimento"]["quadros"], 60);

    // uma animação da biblioteca pelo nome não precisa do HY-Motion
    let b = chamar(&f, "generate_animation", json!({"arquivo": "Characters/aren/aren.glb", "descricao": "andar"})).await;
    assert!(b["estatisticas"]["animacoes"].as_array().unwrap().iter().any(|a| a["nome"] == "andar"));
}

#[cfg(unix)]
#[tokio::test]
async fn unirig_de_mentira_passa_pelo_worker_para_criaturas() {
    let tmp = tempfile::tempdir().unwrap();
    let Some((f, py)) = fornalha(tmp.path()).await else { return };
    instalar_falso(&f.paths, Worker::UniRig, "unirig", &py);
    chamar(&f, "create_project", json!({"nome": "Bichos"})).await;
    // uma malha qualquer para servir de criatura
    let barril = chamar(&f, "generate_3d", json!({"tipo": "objeto", "modelo": "barril", "nome": "lobo"})).await;
    let entrada = barril["arquivos"]["modelo"].as_str().unwrap().to_string();
    let r = chamar(&f, "create_skeleton", json!({"entrada": entrada, "nome": "lobo", "criatura": true, "inimigo": true})).await;
    assert_eq!(r["modelo"], "unirig", "{r}");
    assert!(r["arquivos"]["modelo"].as_str().unwrap().ends_with("lobo.glb"));
    // humanoide continua no esqueleto padrão
    let h = chamar(&f, "create_skeleton", json!({"entrada": entrada, "nome": "barrilzinho"})).await;
    assert_eq!(h["modelo"], "rigify-blender");
}
