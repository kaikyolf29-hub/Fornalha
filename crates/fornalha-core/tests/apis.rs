//! API paga de 3D (Meshy) contra um servidor falso em 127.0.0.1 que fala a mesma API: a chave vai no
//! cabeçalho (nunca na linha de comando), a imagem vai como data URI e o .glb volta para o projeto.

use std::sync::{Arc, Mutex};

use axum::extract::{Path, State};
use axum::http::HeaderMap;
use axum::routing::{get, post};
use axum::Json;
use fornalha_core::apis;
use fornalha_core::paths::Paths;
use serde_json::{json, Value};

#[derive(Default)]
struct Visto {
    chave: String,
    imagem_ok: bool,
    pose: String,
    consultas: usize,
    porta: u16,
}

type Estado = Arc<Mutex<Visto>>;

async fn criar(State(v): State<Estado>, h: HeaderMap, Json(corpo): Json<Value>) -> Json<Value> {
    let mut g = v.lock().unwrap();
    g.chave = h.get("authorization").and_then(|x| x.to_str().ok()).unwrap_or("").to_string();
    g.imagem_ok = corpo["image_url"].as_str().is_some_and(|u| u.starts_with("data:image/png;base64,"));
    g.pose = corpo["pose_mode"].as_str().unwrap_or("").to_string();
    Json(json!({"result": "tarefa-1"}))
}

async fn consultar(State(v): State<Estado>, Path(id): Path<String>) -> Json<Value> {
    let mut g = v.lock().unwrap();
    g.consultas += 1;
    assert_eq!(id, "tarefa-1");
    if g.consultas < 2 {
        return Json(json!({"status": "IN_PROGRESS", "progress": 50}));
    }
    Json(json!({"status": "SUCCEEDED", "consumed_credits": 30,
                "model_urls": {"glb": format!("http://127.0.0.1:{}/arquivo/modelo.glb", g.porta)}}))
}

async fn tripo_arquivo(body: axum::body::Bytes) -> Json<Value> {
    assert!(String::from_utf8_lossy(&body).contains("name=\"file\"; filename="), "upload multipart com o campo file");
    Json(json!({"code": 0, "data": {"file_token": "arq-1"}}))
}

async fn tripo_criar(h: HeaderMap, Json(corpo): Json<Value>) -> Json<Value> {
    assert_eq!(h.get("authorization").unwrap(), "Bearer chave-tripo");
    assert_eq!(corpo["input"], "arq-1");
    assert_eq!(corpo["pbr"], true);
    Json(json!({"code": 0, "data": {"task_id": "t-2"}}))
}

async fn tripo_tarefa(State(v): State<Estado>) -> Json<Value> {
    let porta = v.lock().unwrap().porta;
    Json(json!({"code": 0, "data": {"status": "success", "credits_consumed": 30,
                                      "output": {"model_url": format!("http://127.0.0.1:{porta}/arquivo/modelo.glb")}}}))
}

async fn rodin_criar(body: axum::body::Bytes) -> Json<Value> {
    let t = String::from_utf8_lossy(&body);
    assert!(t.contains("name=\"images\"; filename=") && t.contains("Gen-2.5"), "multipart com images e tier");
    Json(json!({"message": "Submitted.", "uuid": "u-3", "jobs": {"uuids": ["j"], "subscription_key": "k-3"}, "consumed": 0.5}))
}

async fn rodin_status(Json(corpo): Json<Value>) -> Json<Value> {
    assert_eq!(corpo["subscription_key"], "k-3");
    Json(json!({"jobs": [{"uuid": "j", "status": "Done"}]}))
}

async fn rodin_baixar(State(v): State<Estado>, Json(corpo): Json<Value>) -> Json<Value> {
    assert_eq!(corpo["task_uuid"], "u-3");
    let porta = v.lock().unwrap().porta;
    Json(
        json!({"list": [{"name": "preview.webp", "url": "x"}, {"name": "model.glb", "url": format!("http://127.0.0.1:{porta}/arquivo/modelo.glb")}]}),
    )
}

async fn arquivo() -> Vec<u8> {
    let mut b = b"glTF".to_vec();
    b.extend(std::iter::repeat_n(0u8, 2000));
    b
}

#[tokio::test]
async fn apis_de_3d_geram_o_glb_com_a_chave_no_cabecalho() {
    let tmp = tempfile::tempdir().unwrap();
    let paths = Paths::under(tmp.path());
    if fornalha_core::workers::python_para(&paths).await.is_none() {
        eprintln!("sem Python: teste pulado");
        return;
    }
    let visto: Estado = Arc::default();
    let app = axum::Router::new()
        .route("/openapi/v1/image-to-3d", post(criar))
        .route("/openapi/v1/image-to-3d/{id}", get(consultar))
        .route("/arquivo/modelo.glb", get(arquivo))
        .route("/v3/files", post(tripo_arquivo))
        .route("/v3/generation/image-to-model", post(tripo_criar))
        .route("/v3/tasks/{id}", get(tripo_tarefa))
        .route("/api/v2/rodin", post(rodin_criar))
        .route("/api/v2/status", post(rodin_status))
        .route("/api/v2/download", post(rodin_baixar))
        .with_state(visto.clone());
    let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let porta = l.local_addr().unwrap().port();
    visto.lock().unwrap().porta = porta;
    tokio::spawn(async move { axum::serve(l, app).await.unwrap() });
    // só no teste: o script fala com o servidor falso
    std::env::set_var("FORNALHA_API_BASE", format!("http://127.0.0.1:{porta}"));
    apis::definir(&paths, "meshy", Some(true), Some("chave-teste".into())).unwrap();
    let p = apis::ligada_3d(&paths).unwrap();
    let img = tmp.path().join("conceito.png");
    std::fs::write(&img, b"\x89PNG\r\n\x1a\nfalso").unwrap();
    let saida = tmp.path().join("modelo.glb");
    let r = apis::gerar_3d(&paths, p, &img, &saida, &json!({"intervalo": 0.1})).await.unwrap();
    assert_eq!(r["creditos"], 30);
    assert_eq!(&std::fs::read(&saida).unwrap()[0..4], b"glTF");
    {
        let g = visto.lock().unwrap();
        assert_eq!(g.chave, "Bearer chave-teste");
        assert!(g.imagem_ok, "a imagem vai como data URI");
        assert_eq!(g.pose, "a-pose", "pose A para o esqueleto encaixar");
    }
    // Tripo e Rodin pelo mesmo caminho (o mesmo servidor falso responde as três APIs)
    apis::definir(&paths, "meshy", Some(false), None).unwrap();
    for (id, chave) in [("tripo", "chave-tripo"), ("rodin", "chave-rodin")] {
        apis::definir(&paths, id, Some(true), Some(chave.into())).unwrap();
        let p = apis::provedor(id).unwrap();
        let saida = tmp.path().join(format!("{id}.glb"));
        let r = apis::gerar_3d(&paths, p, &img, &saida, &json!({"intervalo": 0.1})).await.unwrap();
        assert_eq!(r["provedor"], id);
        assert_eq!(&std::fs::read(&saida).unwrap()[0..4], b"glTF", "{id}");
        apis::definir(&paths, id, Some(false), None).unwrap();
    }
}
