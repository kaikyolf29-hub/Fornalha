//! Programas de fora que a Fornalha comanda: Blender, Godot e Erethea Engine.

use std::path::PathBuf;

use fornalha_core::externas::{self, Ambiente, Programa};

fn amb_windows() -> Ambiente {
    Ambiente {
        windows: true,
        program_files: Some(PathBuf::from(r"C:\Program Files")),
        program_files_x86: Some(PathBuf::from(r"C:\Program Files (x86)")),
        local_app_data: Some(PathBuf::from(r"C:\Users\kaiky\AppData\Local")),
        home: Some(PathBuf::from(r"C:\Users\kaiky")),
        pasta_fornalha: PathBuf::from(r"C:\Users\kaiky\AppData\Local\fornalha\ferramentas"),
        path: vec![PathBuf::from(r"C:\Windows\System32")],
        ..Default::default()
    }
}

#[test]
fn nomes_e_executaveis() {
    assert_eq!(Programa::Blender.nome(), "Blender");
    assert_eq!(Programa::Erethea.nome(), "Erethea Engine");
    assert_eq!(Programa::from_engine("erethea"), Some(Programa::Erethea));
    assert_eq!(Programa::from_engine("godot"), Some(Programa::Godot));
    assert_eq!(Programa::from_engine("unity"), None);
}

#[test]
fn erethea_no_windows_vem_da_pasta_do_instalador() {
    let c = externas::candidatos(Programa::Erethea, &amb_windows());
    let console = PathBuf::from(r"C:\Users\kaiky\AppData\Local").join("Erethea").join("erethea.console.exe");
    let janela = PathBuf::from(r"C:\Users\kaiky\AppData\Local").join("Erethea").join("erethea.exe");
    let i = c.iter().position(|p| *p == console).expect("console do instalador");
    let j = c.iter().position(|p| *p == janela).expect("exe do instalador");
    assert!(i < j, "a versão de console vem antes (mostra os erros nos testes)");
}

#[test]
fn blender_no_windows_procura_program_files_e_steam() {
    let c = externas::candidatos(Programa::Blender, &amb_windows());
    let txt: Vec<String> = c.iter().map(|p| p.to_string_lossy().into_owned()).collect();
    assert!(txt.iter().any(|p| p.contains("Blender Foundation")), "{txt:?}");
    assert!(txt.iter().any(|p| p.contains("steamapps") && p.ends_with("blender.exe")), "{txt:?}");
    assert!(txt.iter().any(|p| p.contains(r"fornalha\ferramentas")), "pasta da própria Fornalha: {txt:?}");
}

#[test]
fn caminho_escolhido_pela_pessoa_vem_primeiro() {
    let mut a = amb_windows();
    a.escolhido = Some(PathBuf::from(r"D:\Apps\Godot\Godot_v4.6.1-stable_win64.exe"));
    let c = externas::candidatos(Programa::Godot, &a);
    assert_eq!(c[0], PathBuf::from(r"D:\Apps\Godot\Godot_v4.6.1-stable_win64.exe"));
}

#[test]
fn variavel_de_ambiente_vem_logo_depois() {
    let mut a = amb_windows();
    a.variavel = Some(PathBuf::from("/opt/blender/blender"));
    let c = externas::candidatos(Programa::Blender, &a);
    assert_eq!(c[0], PathBuf::from("/opt/blender/blender"));
}

#[test]
fn linux_procura_no_path_e_em_opt() {
    let a = Ambiente {
        windows: false,
        path: vec![PathBuf::from("/usr/local/bin"), PathBuf::from("/usr/bin")],
        home: Some(PathBuf::from("/home/k")),
        pasta_fornalha: PathBuf::from("/home/k/.local/share/fornalha/ferramentas"),
        ..Default::default()
    };
    let c = externas::candidatos(Programa::Godot, &a);
    assert!(c.contains(&PathBuf::from("/usr/bin/godot")));
    assert!(c.contains(&PathBuf::from("/usr/local/bin/godot4")));
    let c = externas::candidatos(Programa::Blender, &a);
    assert!(c.contains(&PathBuf::from("/usr/bin/blender")));
}

#[test]
fn versoes() {
    assert_eq!(externas::ler_versao(Programa::Blender, "Blender 5.2.4 LTS\n\tbuild date: 2026-11-10"), Some("5.2.4 LTS".into()));
    assert_eq!(externas::ler_versao(Programa::Godot, "4.6.1.stable.official.14d19694e\n"), Some("4.6.1.stable".into()));
    assert_eq!(externas::ler_versao(Programa::Erethea, "Godot Engine v4.8.beta4.erethea\n4.8.beta4.erethea.abc"), Some("4.8.beta4".into()));
    assert_eq!(externas::ler_versao(Programa::Godot, "lixo"), None);
}

#[test]
fn versao_da_engine_para_o_project_godot() {
    assert_eq!(externas::recurso_da_engine("4.6.1.stable"), "4.6");
    assert_eq!(externas::recurso_da_engine("4.8.beta4"), "4.8");
    assert_eq!(externas::recurso_da_engine(""), "4.6");
}

/// Roda o Blender de verdade se ele estiver nesta máquina (FORNALHA_TESTE_BLENDER ou achado sozinho).
#[tokio::test]
async fn blender_de_verdade_responde() {
    let Some(achado) = externas::achar_para_teste(Programa::Blender).await else {
        eprintln!("Blender não encontrado: teste pulado (o CI instala o Blender)");
        return;
    };
    assert!(achado.versao.as_deref().unwrap_or("").starts_with(char::is_numeric), "{achado:?}");
    let saida = externas::rodar(&achado.caminho, &["--version"], std::time::Duration::from_secs(60), None).await.unwrap();
    assert!(saida.ok());
    assert!(saida.stdout.contains("Blender"));
}
