//! Fornalha: aplicativo com ícone na bandeja (perto do relógio).
//!
//! Um executável, três jeitos (a casca veio do Ignis):
//! - **Núcleo** (`fornalha` / `fornalha --minimizado`): bandeja + API local +
//!   MCP por HTTP. Nunca abre WebView, por isso fica leve em repouso.
//! - **Janela** (`fornalha --janela`, aberta pelo núcleo): só existe enquanto a
//!   janela está aberta. Fechar a janela devolve a memória; a Fornalha continua
//!   na bandeja. "Sair" fica no menu do ícone.
//! - **MCP por stdio** (`fornalha --mcp`): para o Claude Code ou o Codex
//!   chamarem a Fornalha mesmo com o app fechado. Não abre janela nem bandeja.
//!
//! A janela fala com o núcleo por um canal local exclusivo (porta aleatória em
//! 127.0.0.1 + senha aleatória), que funciona mesmo se a porta da API estiver ocupada.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::extract::{Request, State};
use axum::http::StatusCode;
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Json;
use fornalha_core::config::Estudio;
use fornalha_core::consts::{APP_NAME, APP_VERSION};
use fornalha_core::niveis::Nivel;
use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;
use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use tokio::sync::Notify;

const JANELA: &str = "principal";
const BANDEJA: &str = "bandeja";
const ARG_JANELA: &str = "--janela";
const ARG_MINIMIZADO: &str = "--minimizado";
const ARG_MCP: &str = "--mcp";
const ENV_PORTA: &str = "FORNALHA_JANELA_PORTA";
const ENV_SENHA: &str = "FORNALHA_JANELA_SENHA";
const HEADER_SENHA: &str = "x-fornalha-janela";

fn iniciar_registro(paths: &Paths, nome: &str) {
    let _ = std::fs::create_dir_all(paths.logs_dir());
    let arquivo = paths.logs_dir().join(nome);
    if std::fs::metadata(&arquivo).map(|m| m.len() > 5 * 1024 * 1024).unwrap_or(false) {
        let _ = std::fs::rename(&arquivo, paths.logs_dir().join(format!("{nome}.1")));
    }
    let filtro = std::env::var("RUST_LOG").unwrap_or_else(|_| "info".into());
    match std::fs::OpenOptions::new().create(true).append(true).open(&arquivo) {
        Ok(f) => {
            let _ = tracing_subscriber::fmt().with_env_filter(filtro).with_ansi(false).with_writer(Mutex::new(f)).try_init();
        }
        Err(_) => {
            let _ = tracing_subscriber::fmt().with_env_filter(filtro).with_writer(std::io::stderr).try_init();
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let paths = Paths::from_env();
    if args.iter().any(|a| a == ARG_MCP) {
        // Saída padrão só para o protocolo; registros vão para arquivo.
        iniciar_registro(&paths, "mcp.log");
        let rt = tokio::runtime::Builder::new_multi_thread().enable_all().build().expect("runtime do MCP");
        let r = rt.block_on(fornalha_core::mcp::servir_stdio(Fornalha::new(paths)));
        std::process::exit(if r.is_ok() { 0 } else { 1 });
    }
    if args.iter().any(|a| a == ARG_JANELA) {
        iniciar_registro(&paths, "janela.log");
        janela::rodar(paths);
    } else {
        iniciar_registro(&paths, "fornalha.log");
        nucleo::rodar(paths, args.iter().any(|a| a == ARG_MINIMIZADO));
    }
}

// =====================================================================
// Núcleo: bandeja + API + MCP por HTTP
// =====================================================================
mod nucleo {
    use super::*;

    pub struct Estado {
        pub fornalha: Arc<Fornalha>,
        pub janela: Mutex<Option<Child>>,
        pub foco: Arc<Notify>,
        pub porta_janela: Mutex<Option<u16>>,
        pub senha: String,
        /// A API principal abriu? (falha se a porta estiver ocupada)
        pub api_ok: Arc<Mutex<Option<Result<u16, String>>>>,
    }

    /// Abre a janela (processo separado) ou traz para a frente se já estiver aberta.
    pub fn abrir_janela(app: &AppHandle) {
        let st = app.state::<Estado>();
        let mut j = st.janela.lock().unwrap();
        if let Some(c) = j.as_mut() {
            if c.try_wait().ok().flatten().is_none() {
                st.foco.notify_waiters();
                return;
            }
        }
        let Some(porta) = *st.porta_janela.lock().unwrap() else {
            tracing::warn!("canal da janela ainda não está pronto");
            return;
        };
        let exe = match std::env::current_exe() {
            Ok(e) => e,
            Err(e) => {
                tracing::error!("não sei onde está o executável: {e}");
                return;
            }
        };
        match Command::new(exe).arg(ARG_JANELA).env(ENV_PORTA, porta.to_string()).env(ENV_SENHA, &st.senha).spawn() {
            Ok(c) => *j = Some(c),
            Err(e) => tracing::error!("não consegui abrir a janela: {e}"),
        }
    }

    fn fechar_janela(app: &AppHandle) {
        if let Some(mut c) = app.state::<Estado>().janela.lock().unwrap().take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }

    async fn checar_senha(State(senha): State<Arc<String>>, req: Request, next: Next) -> Response {
        let ok = req.headers().get(HEADER_SENHA).and_then(|v| v.to_str().ok()) == Some(senha.as_str());
        if !ok {
            return (StatusCode::FORBIDDEN, "senha da janela inválida").into_response();
        }
        next.run(req).await
    }

    #[derive(Clone)]
    struct Canal {
        fornalha: Arc<Fornalha>,
        foco: Arc<Notify>,
        api_ok: Arc<Mutex<Option<Result<u16, String>>>>,
    }

    async fn esperar_foco(State(c): State<Canal>) -> Response {
        tokio::select! {
            _ = c.foco.notified() => Json(json!({"foco": true})).into_response(),
            _ = tokio::time::sleep(Duration::from_secs(25)) => Json(json!({"foco": false})).into_response(),
        }
    }

    /// O que só a janela sabe mostrar: comandos para ligar agentes, versão, configuração.
    async fn info(State(c): State<Canal>) -> Json<Value> {
        let f = &c.fornalha;
        let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_else(|_| "fornalha".into());
        let porta = f.porta_api();
        let api = c.api_ok.lock().unwrap().clone();
        let cfg = f.config();
        Json(json!({
            "app": APP_NAME,
            "versao": APP_VERSION,
            "fase": fornalha_core::consts::FASE,
            "exe": exe,
            "porta": porta,
            "api_ok": matches!(api, Some(Ok(_))),
            "api_erro": api.and_then(|r| r.err()),
            "endereco_mcp": format!("http://127.0.0.1:{porta}/mcp"),
            "comandos": {
                "claude_http": format!("claude mcp add --transport http fornalha http://127.0.0.1:{porta}/mcp"),
                "claude_stdio": format!("claude mcp add fornalha -- \"{exe}\" --mcp"),
                "codex": format!("codex mcp add fornalha -- \"{exe}\" --mcp"),
            },
            "pasta_projetos": f.pasta_projetos(),
            "pasta_projetos_escolhida": cfg.pasta_projetos.is_some(),
            "nivel_da_maquina": cfg.nivel,
            "noite": cfg.noite,
            "estilo_janela": cfg.estilo_janela.unwrap_or_else(|| "auto".into()),
            "estudio": cfg.estudio,
            "grupos_de_aceite": f.catalogo.grupos_de_aceite,
        }))
    }

    async fn definir_estudio(State(c): State<Canal>, Json(e): Json<Estudio>) -> Response {
        match c.fornalha.definir_estudio(e) {
            Ok(()) => Json(json!({"ok": true})).into_response(),
            Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"erro": e}))).into_response(),
        }
    }

    async fn definir_ajustes(State(c): State<Canal>, Json(v): Json<Value>) -> Response {
        let f = &c.fornalha;
        let mut r = Ok(());
        if let Some(n) = v.get("nivel") {
            let nivel = n.as_str().and_then(Nivel::from_id);
            if n.is_string() && nivel.is_none() && n != "auto" {
                return (StatusCode::BAD_REQUEST, Json(json!({"erro": {"codigo": "argumento_invalido", "mensagem": "Nível inválido."}})))
                    .into_response();
            }
            r = r.and(f.definir_nivel_da_maquina(nivel));
        }
        if let Some(n) = v.get("noite") {
            match serde_json::from_value::<fornalha_core::config::Noite>(n.clone()) {
                Ok(noite) => r = r.and(f.definir_noite(noite)),
                Err(_) => {
                    return (
                        StatusCode::BAD_REQUEST,
                        Json(json!({"erro": {"codigo": "argumento_invalido", "mensagem": "Horário da noite inválido."}})),
                    )
                        .into_response()
                }
            }
        }
        if let Some(e) = v.get("estilo_janela") {
            let estilo = e.as_str().filter(|s| fornalha_core::janela::ESTILOS.contains(s) && *s != "auto").map(String::from);
            r = r.and(f.definir_estilo_janela(estilo));
        }
        if let Some(prog) = v.get("programa") {
            let nome = prog["nome"].as_str().unwrap_or("");
            let programa = match nome {
                "blender" => Some(fornalha_core::externas::Programa::Blender),
                "godot" => Some(fornalha_core::externas::Programa::Godot),
                "erethea" => Some(fornalha_core::externas::Programa::Erethea),
                _ => None,
            };
            let Some(programa) = programa else {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"erro": {"codigo": "argumento_invalido", "mensagem": "Programa desconhecido."}})),
                )
                    .into_response();
            };
            let caminho = prog["caminho"].as_str().filter(|s| !s.trim().is_empty()).map(std::path::PathBuf::from);
            r = r.and(f.definir_programa(programa, caminho).await);
        }
        if let Some(p) = v.get("pasta_projetos") {
            r = r.and(f.definir_pasta_projetos(p.as_str().filter(|s| !s.trim().is_empty()).map(Into::into)));
        }
        match r {
            Ok(()) => Json(json!({"ok": true})).into_response(),
            Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"erro": e}))).into_response(),
        }
    }

    /// Instalar ou verificar um modelo de placa: só a pessoa, pela janela (downloads de
    /// vários GB e, no HY-Motion, a licença da Tencent aceita antes).
    async fn modelo_de_placa(State(c): State<Canal>, Json(v): Json<Value>) -> Response {
        use fornalha_core::workers::{self, Worker};
        let Some(w) = v["id"].as_str().and_then(Worker::de_id) else {
            return (StatusCode::BAD_REQUEST, Json(json!({"erro": {"mensagem": "Modelo desconhecido."}}))).into_response();
        };
        let r = match v["acao"].as_str() {
            Some("instalar") => {
                if let Some(g) = w.aceite() {
                    if !c.fornalha.estudio().licencas_aceitas.iter().any(|a| a == g) {
                        let m = "Aceite a licença em Licenças antes de instalar este modelo.";
                        return (StatusCode::BAD_REQUEST, Json(json!({"erro": {"mensagem": m}}))).into_response();
                    }
                }
                workers::instalar(&c.fornalha.paths, w, false).await
            }
            Some("verificar") => workers::verificar(&c.fornalha.paths, w).await,
            _ => return (StatusCode::BAD_REQUEST, Json(json!({"erro": {"mensagem": "Ação desconhecida."}}))).into_response(),
        };
        match r {
            Ok(v) => Json(v).into_response(),
            Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"erro": e}))).into_response(),
        }
    }

    /// Canal exclusivo da janela: a mesma API (como "pessoa") + rotas que só a pessoa usa.
    async fn servir_canal_janela(app: AppHandle) {
        let st = app.state::<Estado>();
        let senha = Arc::new(st.senha.clone());
        let canal = Canal { fornalha: st.fornalha.clone(), foco: st.foco.clone(), api_ok: st.api_ok.clone() };
        let rotas = fornalha_core::api::router(st.fornalha.clone())
            .merge(
                axum::Router::new()
                    .route("/janela/esperar-foco", get(esperar_foco))
                    .route("/janela/info", get(info))
                    .route("/janela/estudio", post(definir_estudio))
                    .route("/janela/ajustes", post(definir_ajustes))
                    .route("/janela/modelo-de-placa", post(modelo_de_placa))
                    .with_state(canal),
            )
            .layer(middleware::from_fn_with_state(senha, checar_senha));
        let listener = match tokio::net::TcpListener::bind(("127.0.0.1", 0)).await {
            Ok(l) => l,
            Err(e) => {
                tracing::error!("canal da janela: {e}");
                return;
            }
        };
        let porta = listener.local_addr().map(|a| a.port()).ok();
        *st.porta_janela.lock().unwrap() = porta;
        tracing::info!("canal da janela na porta {porta:?}");
        let _ = axum::serve(listener, rotas).await;
    }

    fn montar_bandeja(app: &AppHandle, porta: u16) -> tauri::Result<()> {
        let abrir = MenuItem::with_id(app, "abrir", "Abrir Fornalha", true, None::<&str>)?;
        let api = MenuItem::with_id(app, "api", format!("API e MCP em 127.0.0.1:{porta}"), false, None::<&str>)?;
        let sair = MenuItem::with_id(app, "sair", "Sair", true, None::<&str>)?;
        let sep1 = PredefinedMenuItem::separator(app)?;
        let sep2 = PredefinedMenuItem::separator(app)?;
        let menu = Menu::with_items(app, &[&abrir, &sep1, &api, &sep2, &sair])?;
        let icone = app.default_window_icon().cloned().ok_or_else(|| tauri::Error::AssetNotFound("ícone".into()))?;
        TrayIconBuilder::with_id(BANDEJA)
            .icon(icone)
            .tooltip(APP_NAME)
            .menu(&menu)
            .show_menu_on_left_click(false)
            .on_menu_event(|app, ev| match ev.id().as_ref() {
                "abrir" => abrir_janela(app),
                "sair" => {
                    fechar_janela(app);
                    app.exit(0);
                }
                _ => {}
            })
            .on_tray_icon_event(|tray, ev| {
                // clique simples abre a janela (no Linux só o menu aparece)
                if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                    abrir_janela(tray.app_handle());
                }
            })
            .build(app)?;
        Ok(())
    }

    pub fn rodar(paths: Paths, minimizado: bool) {
        tracing::info!("{APP_NAME} {APP_VERSION} iniciando (minimizado: {minimizado})");
        let app = tauri::Builder::default()
            .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| abrir_janela(app)))
            .setup(move |app| {
                let fornalha = Fornalha::new(paths.clone());
                let porta = fornalha.porta_api();
                let api_ok = Arc::new(Mutex::new(None));
                app.manage(Estado {
                    fornalha: fornalha.clone(),
                    janela: Mutex::new(None),
                    foco: Arc::new(Notify::new()),
                    porta_janela: Mutex::new(None),
                    senha: fornalha_core::util::id_aleatorio(32),
                    api_ok: api_ok.clone(),
                });
                // fila da noite: uma tarefa por vez, as de "noite" só no horário da noite
                tauri::async_runtime::spawn(fornalha_core::fila::vigiar(fornalha.clone()));
                // API principal (agentes) — se a porta estiver ocupada, a janela avisa.
                let f2 = fornalha.clone();
                tauri::async_runtime::spawn(async move {
                    // Detecta a placa já no começo, para a janela abrir pronta.
                    let f3 = f2.clone();
                    tauri::async_runtime::spawn(async move {
                        f3.deteccao(false).await;
                    });
                    match tokio::net::TcpListener::bind(("127.0.0.1", porta)).await {
                        Ok(l) => {
                            *api_ok.lock().unwrap() = Some(Ok(porta));
                            tracing::info!("API da Fornalha em http://127.0.0.1:{porta}");
                            let _ = axum::serve(l, fornalha_core::api::router(f2)).await;
                        }
                        Err(e) => {
                            tracing::error!("porta {porta} ocupada: {e}");
                            *api_ok.lock().unwrap() = Some(Err(format!(
                                "A porta {porta} já está em uso (outra Fornalha aberta?). Agentes não conseguem se conectar."
                            )));
                        }
                    }
                });
                let h = app.handle().clone();
                tauri::async_runtime::spawn(async move { servir_canal_janela(h).await });
                montar_bandeja(app.handle(), porta)?;
                if !minimizado {
                    let h = app.handle().clone();
                    tauri::async_runtime::spawn(async move {
                        // espera o canal da janela ficar pronto
                        for _ in 0..100 {
                            if h.state::<Estado>().porta_janela.lock().unwrap().is_some() {
                                break;
                            }
                            tokio::time::sleep(Duration::from_millis(50)).await;
                        }
                        abrir_janela(&h);
                    });
                }
                Ok(())
            })
            .build(tauri::generate_context!())
            .expect("erro ao iniciar a Fornalha");

        app.run(|app, ev| match ev {
            // sem janelas no núcleo: só "Sair" encerra
            RunEvent::ExitRequested { api, code, .. } if code.is_none() => api.prevent_exit(),
            RunEvent::Exit => fechar_janela(app),
            _ => {}
        });
    }
}

// =====================================================================
// Janela: processo separado que só vive enquanto a janela está aberta
// =====================================================================
mod janela {
    use super::*;

    struct Canal {
        base: String,
        senha: String,
        http: reqwest::Client,
    }

    /// A janela fala com o núcleo pelo canal exclusivo. Tudo que ela pede é "da pessoa".
    #[tauri::command]
    async fn api(canal: tauri::State<'_, Canal>, method: String, path: String, body: Option<Value>) -> Result<Value, String> {
        if !path.starts_with("/fornalha/") && !path.starts_with("/janela/") {
            return Err("rota não permitida pela janela".into());
        }
        let metodo = reqwest::Method::from_bytes(method.as_bytes()).map_err(|e| e.to_string())?;
        let mut req = canal
            .http
            .request(metodo, format!("{}{}", canal.base, path))
            .header(HEADER_SENHA, &canal.senha)
            .header(fornalha_core::api::HEADER_CLIENTE, "pessoa");
        if let Some(b) = body {
            req = req.json(&b);
        }
        let r = req.send().await.map_err(|_| "Sem conexão com o núcleo da Fornalha.".to_string())?;
        let status = r.status().as_u16();
        let corpo: Value = r.json().await.unwrap_or(Value::Null);
        Ok(json!({"status": status, "corpo": corpo}))
    }

    /// Abre um link no navegador (só endereços conhecidos: licenças e documentação).
    #[tauri::command]
    fn abrir_link(app: AppHandle, url: String) -> Result<(), String> {
        let permitido = [
            "https://huggingface.co/",
            "https://github.com/",
            "https://www.blender.org/",
            "http://mocap.cs.cmu.edu/",
            "https://www.meshy.ai/",
            "https://helpx.adobe.com/",
            "https://code.claude.com/",
            "https://developers.openai.com/",
            "https://www.blender.org/download/",
            "https://godotengine.org/",
            "https://github.com/kaikyolf29-hub/",
        ];
        if !permitido.iter().any(|p| url.starts_with(p)) {
            return Err("link não permitido".into());
        }
        app.opener().open_url(url, None::<&str>).map_err(|e| e.to_string())
    }

    /// Abre uma pasta de projeto (ou a de registros) no gerenciador de arquivos.
    #[tauri::command]
    fn abrir_pasta(app: AppHandle, caminho: String) -> Result<(), String> {
        let p = if caminho == "registros" { Paths::from_env().logs_dir() } else { std::path::PathBuf::from(&caminho) };
        if !p.is_dir() {
            return Err("pasta não encontrada".into());
        }
        app.opener().open_path(p.to_string_lossy(), None::<&str>).map_err(|e| e.to_string())
    }

    /// Só arquivos de dentro de um projeto da Fornalha (uma pasta acima tem o game.project.json).
    fn dentro_de_projeto(caminho: &std::path::Path) -> Option<std::path::PathBuf> {
        let real = std::fs::canonicalize(caminho).ok()?;
        let mut d = real.parent();
        while let Some(pasta) = d {
            if pasta.join("game.project.json").is_file() {
                return Some(real);
            }
            d = pasta.parent();
        }
        None
    }

    /// Lê um arquivo do projeto para a janela mostrar (prévias, capturas, áudio).
    #[tauri::command]
    fn ler_arquivo(caminho: String) -> Result<Value, String> {
        use base64::Engine;
        let real = dentro_de_projeto(std::path::Path::new(&caminho)).ok_or("arquivo fora de um projeto da Fornalha")?;
        let tamanho = std::fs::metadata(&real).map_err(|e| e.to_string())?.len();
        if tamanho > 25 * 1024 * 1024 {
            return Err("arquivo grande demais para a prévia".into());
        }
        let mime = match real.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase().as_str() {
            "png" => "image/png",
            "jpg" | "jpeg" => "image/jpeg",
            "webp" => "image/webp",
            "wav" => "audio/wav",
            "mp4" => "video/mp4",
            "json" | "md" => "text/plain",
            _ => "application/octet-stream",
        };
        let bytes = std::fs::read(&real).map_err(|e| e.to_string())?;
        Ok(json!({"mime": mime, "base64": base64::engine::general_purpose::STANDARD.encode(bytes)}))
    }

    /// Abre um arquivo do projeto no programa padrão do sistema (vídeo do teste, modelo 3D).
    #[tauri::command]
    fn abrir_arquivo(app: AppHandle, caminho: String) -> Result<(), String> {
        let real = dentro_de_projeto(std::path::Path::new(&caminho)).ok_or("arquivo fora de um projeto da Fornalha")?;
        app.opener().open_path(real.to_string_lossy(), None::<&str>).map_err(|e| e.to_string())
    }

    /// Janela do sistema para escolher um arquivo (executável do Blender, da Godot, da Erethea).
    #[tauri::command]
    async fn escolher_arquivo(app: AppHandle, titulo: String) -> Option<String> {
        let (tx, rx) = tokio::sync::oneshot::channel();
        app.dialog().file().set_title(titulo).pick_file(move |p| {
            let _ = tx.send(p.and_then(|f| f.into_path().ok()).map(|p| p.to_string_lossy().into_owned()));
        });
        rx.await.ok().flatten()
    }

    /// Janela do sistema para escolher uma pasta.
    #[tauri::command]
    async fn escolher_pasta(app: AppHandle, titulo: String) -> Option<String> {
        let (tx, rx) = tokio::sync::oneshot::channel();
        app.dialog().file().set_title(titulo).pick_folder(move |p| {
            let _ = tx.send(p.and_then(|f| f.into_path().ok()).map(|p| p.to_string_lossy().into_owned()));
        });
        rx.await.ok().flatten()
    }

    /// O que o sistema diz sobre os botões da janela (lado, ordem, tema).
    struct SistemaJanela(fornalha_core::janela::Sistema);

    fn sistema_da_janela() -> fornalha_core::janela::Sistema {
        let so = if cfg!(windows) {
            "windows"
        } else if cfg!(target_os = "macos") {
            "mac"
        } else {
            "linux"
        };
        #[allow(unused_mut)]
        let mut s = fornalha_core::janela::Sistema {
            so: so.into(),
            desktop: std::env::var("XDG_CURRENT_DESKTOP").ok().filter(|d| !d.is_empty()),
            ..Default::default()
        };
        #[cfg(target_os = "linux")]
        {
            use gtk::prelude::*;
            // O GNOME e o KDE (e o portal, no Flatpak) preenchem estas configurações do GTK.
            if let Some(cfg) = gtk::Settings::default() {
                s.layout = cfg.property::<Option<String>>("gtk-decoration-layout");
                s.tema = cfg.property::<Option<String>>("gtk-theme-name");
            }
        }
        s
    }

    #[tauri::command]
    fn botoes_janela(sis: tauri::State<'_, SistemaJanela>, preferido: Option<String>) -> fornalha_core::janela::BotoesJanela {
        fornalha_core::janela::escolher(&sis.0, preferido.as_deref().unwrap_or("auto"))
    }

    pub fn rodar(_paths: Paths) {
        let (Ok(porta), Ok(senha)) = (std::env::var(ENV_PORTA), std::env::var(ENV_SENHA)) else {
            eprintln!("A janela da Fornalha é aberta pela própria Fornalha (ícone perto do relógio).");
            std::process::exit(2);
        };
        let base = format!("http://127.0.0.1:{porta}");
        let http = reqwest::Client::builder().no_proxy().build().expect("cliente HTTP local");
        let canal = Canal { base: base.clone(), senha: senha.clone(), http: http.clone() };
        tauri::Builder::default()
            .plugin(tauri_plugin_opener::init())
            .plugin(tauri_plugin_dialog::init())
            .manage(canal)
            .invoke_handler(tauri::generate_handler![
                api,
                abrir_link,
                abrir_pasta,
                escolher_pasta,
                escolher_arquivo,
                ler_arquivo,
                abrir_arquivo,
                botoes_janela
            ])
            .setup(move |app| {
                // Na thread principal, com o GTK já iniciado.
                let sistema = sistema_da_janela();
                tracing::info!(?sistema, "botões da janela");
                app.manage(SistemaJanela(sistema));
                let w = WebviewWindowBuilder::new(app, JANELA, WebviewUrl::App("index.html".into()))
                    .title(APP_NAME)
                    .inner_size(1080.0, 740.0)
                    .min_inner_size(800.0, 560.0)
                    // Barra de título integrada: o topo da própria Fornalha faz o papel
                    // da barra (arrastar, duplo clique, botões). No Windows a sombra
                    // e os cantos arredondados continuam sendo do sistema.
                    .decorations(false)
                    .shadow(true)
                    .center()
                    .build()?;
                let _ = w.set_focus();
                // Espera pedidos de foco do núcleo; se o núcleo sumir, fecha.
                let h = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let mut falhas = 0;
                    loop {
                        let r = http
                            .get(format!("{base}/janela/esperar-foco"))
                            .header(HEADER_SENHA, &senha)
                            .timeout(Duration::from_secs(30))
                            .send()
                            .await;
                        match r {
                            Ok(resp) if resp.status().is_success() => {
                                falhas = 0;
                                let v: Value = resp.json().await.unwrap_or(Value::Null);
                                if v["foco"] == json!(true) {
                                    if let Some(w) = h.get_webview_window(JANELA) {
                                        let _ = w.unminimize();
                                        let _ = w.show();
                                        let _ = w.set_focus();
                                    }
                                }
                            }
                            _ => {
                                falhas += 1;
                                if falhas >= 5 {
                                    tracing::warn!("núcleo não responde; fechando a janela");
                                    h.exit(0);
                                    break;
                                }
                                tokio::time::sleep(Duration::from_secs(2)).await;
                            }
                        }
                    }
                });
                Ok(())
            })
            .run(tauri::generate_context!())
            .expect("erro ao abrir a janela da Fornalha");
    }
}
