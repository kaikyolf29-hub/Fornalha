//! A janela (app/ui): o app.js roda assim que é carregado, então todo elemento que ele pega pelo id
//! ($("id")) tem de existir no index.html ANTES do <script src="app.js">. Um elemento depois do script
//! quebrava o carregamento inteiro e a navegação entre as telas parava (o visualizador 3D ficou assim).

use std::collections::BTreeSet;

fn arquivo(rel: &str) -> String {
    let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../app/ui").join(rel);
    std::fs::read_to_string(&base).unwrap_or_else(|e| panic!("{}: {e}", base.display()))
}

/// Ids usados no nível de cima do app.js (linhas que começam com `$("…")`): rodam ao carregar.
fn ids_usados(js: &str) -> BTreeSet<String> {
    js.lines()
        .filter_map(|l| l.strip_prefix("$(\""))
        .filter_map(|r| r.split('"').next())
        .filter(|id| !id.is_empty() && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'))
        .map(String::from)
        .collect()
}

#[test]
fn elementos_do_app_js_existem_antes_do_script() {
    let html = arquivo("index.html");
    let js = arquivo("app.js");
    let corte = html.find("<script src=\"app.js\"></script>").expect("index.html carrega o app.js");
    let antes = &html[..corte];
    let faltam: Vec<String> = ids_usados(&js).into_iter().filter(|id| !antes.contains(&format!("id=\"{id}\""))).collect();
    assert!(faltam.is_empty(), "elementos usados pelo app.js que não existem antes do <script>: {faltam:?}");
}

#[test]
fn telas_novas_estao_na_janela() {
    let html = arquivo("index.html");
    for id in [
        "comfyui",
        "apis",
        "bruto-rodar",
        "bruto-nivel",
        "bruto-resultado",
        "visualizador",
        "modelos-placa",
        "est-movimento",
        "mov-banco",
        "mov-resultado",
    ] {
        assert!(html.contains(&format!("id=\"{id}\"")), "falta #{id} na janela");
    }
}
