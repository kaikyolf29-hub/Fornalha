//! Conversa com o Ignis (o cérebro local) pela API dele.

use axum::routing::get;
use axum::Json;
use fornalha_core::ignis;
use serde_json::json;

async fn ignis_falso() -> u16 {
    let app = axum::Router::new()
        .route(
            "/motor/estado",
            get(|| async { Json(json!({"fase": "pronto", "fase_texto": "Pronto", "modelo": {"nome": "Qwen3 8B", "motor_nome": "CUDA"}})) }),
        )
        .route("/motor/versao", get(|| async { Json(json!({"app": {"nome": "Ignis", "versao": "0.3.1", "api": 1}})) }));
    let l = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let porta = l.local_addr().unwrap().port();
    tokio::spawn(async move { axum::serve(l, app).await.unwrap() });
    porta
}

#[tokio::test]
async fn ignis_ligado() {
    let porta = ignis_falso().await;
    let e = ignis::consultar(porta).await;
    assert!(e.conectado);
    assert_eq!(e.versao.as_deref(), Some("0.3.1"));
    assert_eq!(e.fase.as_deref(), Some("Pronto"));
    assert_eq!(e.modelo.as_deref(), Some("Qwen3 8B"));
    assert_eq!(e.endereco, format!("http://127.0.0.1:{porta}"));
}

#[tokio::test]
async fn ignis_desligado_nao_trava() {
    let porta = {
        let l = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        l.local_addr().unwrap().port()
    }; // porta fechada
    let inicio = std::time::Instant::now();
    let e = ignis::consultar(porta).await;
    assert!(!e.conectado);
    assert!(e.erro.is_some());
    assert!(inicio.elapsed() < std::time::Duration::from_secs(3));
}
