//! Linha de comando da Fornalha (para agentes, CI e diagnóstico).
//!
//! - `fornalha-cli mcp`                   servidor MCP por stdio (Claude Code, Codex)
//! - `fornalha-cli servir [--porta N]`    API local e MCP por HTTP, sem janela
//! - `fornalha-cli detectar`              placa, aceleradores e nível sugerido (JSON)
//! - `fornalha-cli chamar <ferramenta> [json]`  chama uma ferramenta e imprime o resultado

use fornalha_core::paths::Paths;
use fornalha_core::servico::Fornalha;

const AJUDA: &str = "Fornalha (linha de comando)

Uso:
  fornalha-cli mcp                         servidor MCP por stdio
  fornalha-cli servir [--porta N]          API local e MCP por HTTP (127.0.0.1)
  fornalha-cli detectar                    placa, aceleradores e nível sugerido
  fornalha-cli chamar <ferramenta> [json]  chama uma ferramenta
  fornalha-cli ferramentas                 lista as ferramentas
  fornalha-cli modelos                     modelos de placa (TRELLIS.2, UniRig, HY-Motion)
  fornalha-cli pacotes                     pacotes de conteúdo (MakeHuman, animações, materiais)
  fornalha-cli baixar-pacote <id>          baixa um pacote de conteúdo CC0 (makehuman, animacoes, materiais)
  fornalha-cli baixar-programa <id>        baixa o Blender ou a Godot (versão fixa, soma conferida) para a pasta da Fornalha
  fornalha-cli instalar-modelo <id> [--pular-pesos]   instala e verifica um modelo de placa
  fornalha-cli teste-bruto [--nivel qualidade|maximo|equilibrado|leve] [--casos protagonista,inimigo,zumbi,dragao] [--sem-engine]
                                           suíte de ponta a ponta (protagonista, inimigo armado, dragão, jogo na engine)
  fornalha-cli comfyui [estado|instalar|abrir] [--modelos gguf|inteiro|nenhum] [--backend nvidia|rocm|vulkan|cpu]
                                           motor de imagem local (ComfyUI ou Vulkan) na placa desta máquina
  fornalha-cli comfyui gerar <pedido> [--lado 512] [--saida imagem.png]
  fornalha-cli comfyui cabeca <conceito.png> [--pedido texto] [--saida pasta] [--horas 6] [--so-recorte]
                                           uma imagem pelo motor instalado (para testar a placa)
  fornalha-cli versao

A variável FORNALHA_HOME coloca configuração e projetos numa pasta só.";

fn registro_no_stderr() {
    let filtro = std::env::var("RUST_LOG").unwrap_or_else(|_| "warn".into());
    let _ = tracing_subscriber::fmt().with_env_filter(filtro).with_writer(std::io::stderr).with_ansi(false).try_init();
}

#[tokio::main]
async fn main() {
    registro_no_stderr();
    let args: Vec<String> = std::env::args().skip(1).collect();
    let paths = Paths::from_env();
    let codigo = match args.first().map(String::as_str) {
        Some("mcp") => match fornalha_core::mcp::servir_stdio(Fornalha::new(paths)).await {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("MCP encerrado com erro: {e}");
                1
            }
        },
        Some("servir") => {
            let f = Fornalha::new(paths);
            if let Some(i) = args.iter().position(|a| a == "--porta") {
                let Some(p) = args.get(i + 1).and_then(|p| p.parse::<u16>().ok()) else {
                    eprintln!("--porta precisa de um número");
                    std::process::exit(2);
                };
                f.fixar_porta(p);
            }
            servir(f).await
        }
        Some("detectar") => {
            let f = Fornalha::new(paths);
            imprimir(f.chamar("detect_gpu", serde_json::json!({}), "pessoa").await)
        }
        Some("chamar") => {
            let Some(nome) = args.get(1) else {
                eprintln!("{AJUDA}");
                std::process::exit(2);
            };
            let json = match args.get(2) {
                Some(t) => match serde_json::from_str(t) {
                    Ok(v) => v,
                    Err(e) => {
                        eprintln!("argumentos não são JSON: {e}");
                        std::process::exit(2);
                    }
                },
                None => serde_json::json!({}),
            };
            imprimir(Fornalha::new(paths).chamar(nome, json, "pessoa").await)
        }
        Some("ferramentas") => {
            for t in fornalha_core::ferramentas::lista() {
                println!("{:<22} {}", t.nome, t.titulo);
            }
            0
        }
        Some("modelos") => {
            println!("{}", serde_json::to_string_pretty(&fornalha_core::workers::estado(&paths)).unwrap_or_default());
            0
        }
        Some("pacotes") => {
            println!("{}", serde_json::to_string_pretty(&fornalha_core::pacotes::estado(&paths)).unwrap_or_default());
            0
        }
        Some("baixar-pacote") => {
            use fornalha_core::pacotes::{self, Pacote};
            let Some(p) = args.get(1).and_then(|id| Pacote::de_id(id)) else {
                eprintln!("Diga qual: makehuman, animacoes, materiais, accad ou 100style.");
                std::process::exit(2);
            };
            imprimir(pacotes::baixar_e_esperar(&paths, p).await)
        }
        Some("baixar-programa") => {
            use fornalha_core::externas::Programa;
            let p = match args.get(1).map(String::as_str) {
                Some("blender") => Programa::Blender,
                Some("godot") => Programa::Godot,
                _ => {
                    eprintln!("Diga qual: blender ou godot.");
                    std::process::exit(2);
                }
            };
            eprintln!("Baixando o {} para {}…", p.nome(), fornalha_core::programas::pasta(&paths).display());
            imprimir(fornalha_core::programas::baixar_e_esperar(&paths, p).await.map(|exe| serde_json::json!({"executavel": exe})))
        }
        Some("instalar-modelo") => {
            use fornalha_core::workers::{self, Worker};
            let Some(w) = args.get(1).and_then(|id| Worker::de_id(id)) else {
                eprintln!("Diga qual: trellis2, unirig ou hy-motion.");
                std::process::exit(2);
            };
            let f = Fornalha::new(paths.clone());
            if let Some(g) = w.aceite() {
                if !f.estudio().licencas_aceitas.iter().any(|a| a == g) {
                    eprintln!("Este modelo precisa do aceite da licença na janela da Fornalha (Licenças) antes de instalar.");
                    std::process::exit(2);
                }
            }
            imprimir(workers::instalar_e_esperar(&paths, w, args.iter().any(|a| a == "--pular-pesos")).await)
        }
        Some("teste-bruto") => {
            let f = Fornalha::new(paths.clone());
            let opcao = |nome: &str| args.iter().position(|a| a == nome).and_then(|i| args.get(i + 1)).cloned();
            let a = fornalha_core::bruto::ArgsBruto {
                nivel: opcao("--nivel"),
                casos: opcao("--casos").map(|c| c.split(',').map(|x| x.trim().to_string()).collect()),
                testar_na_engine: Some(!args.iter().any(|a| a == "--sem-engine")),
                pasta: opcao("--pasta").map(std::path::PathBuf::from),
            };
            match fornalha_core::bruto::rodar(&f, a, "linha-de-comando").await {
                Ok(r) => {
                    println!("{}", serde_json::to_string_pretty(&r).unwrap_or_default());
                    if r["passou"] == true {
                        0
                    } else {
                        1
                    }
                }
                Err(e) => imprimir(Err(e)),
            }
        }
        Some("comfyui") => {
            use fornalha_core::comfyui;
            let f = Fornalha::new(paths.clone());
            let opcao = |nome: &str| args.iter().position(|a| a == nome).and_then(|i| args.get(i + 1)).cloned();
            let mut c = comfyui::caminho_para(&f.deteccao(false).await);
            if let Some(m) = opcao("--modelos") {
                c.modelos = match m.as_str() {
                    "inteiro" => "inteiro",
                    "nenhum" => "nenhum",
                    _ => "gguf",
                };
            }
            if let Some(b) = opcao("--backend") {
                c.backend = match b.as_str() {
                    "nvidia" => "nvidia",
                    "rocm" => "rocm",
                    // o ComfyUI tirou o DirectML: AMD/Intel sem ROCm vão pelo Vulkan (stable-diffusion.cpp)
                    "vulkan" | "directml" => "vulkan",
                    _ => "cpu",
                };
            }
            // 3D pela IA: o criador aceitou a licença do DINOv3 para os testes; na janela, pelo aceite
            c.tres_d = args.iter().any(|a| a == "--3d");
            match args.get(1).map(String::as_str) {
                Some("instalar") => {
                    eprintln!("Instalando o ComfyUI: {} ({}), modelos {}", c.backend, c.motivo, c.modelos);
                    imprimir(comfyui::instalar_e_esperar(&paths, &c, f.porta_comfyui()).await)
                }
                Some("abrir") => imprimir(comfyui::abrir(&paths, f.porta_comfyui()).await.map(|e| serde_json::json!(e))),
                Some("gerar") => {
                    // uma imagem direto pelo motor instalado (ComfyUI aberto ou Vulkan): para testar a placa
                    let prompt = args.get(2).cloned().unwrap_or_else(|| "medieval knight templar, white surcoat with red cross".into());
                    let lado: u32 = opcao("--lado").and_then(|v| v.parse().ok()).unwrap_or(512);
                    let saida = std::path::PathBuf::from(opcao("--saida").unwrap_or_else(|| "imagem.png".into()));
                    let r = if let Some(m) = comfyui::motor_vulkan(&paths) {
                        eprintln!("Motor Vulkan: {:?}", comfyui::dispositivos_vulkan(&m).await);
                        comfyui::gerar_imagem_vulkan(&m, &prompt, lado, lado, 1000, 8).await
                    } else {
                        comfyui::gerar_imagem(f.porta_comfyui(), &prompt, lado, lado, 1000, 8).await
                    };
                    imprimir(r.and_then(|(png, info)| {
                        std::fs::write(&saida, &png).map_err(|e| fornalha_core::erro::Erro::io(&saida, e))?;
                        Ok(serde_json::json!({"arquivo": saida, "info": info}))
                    }))
                }
                Some("cabeca") => {
                    // 3D por partes: a cabeça recortada do conceito, refinada em close e feita malha
                    let conceito = std::path::PathBuf::from(args.get(2).cloned().unwrap_or_default());
                    let descricao = opcao("--pedido").unwrap_or_default();
                    let saida = std::path::PathBuf::from(opcao("--saida").unwrap_or_else(|| "cabeca".into()));
                    let horas: u64 = opcao("--horas").and_then(|v| v.parse().ok()).unwrap_or(6);
                    let bytes = std::fs::read(&conceito).map_err(|e| fornalha_core::erro::Erro::io(&conceito, e));
                    imprimir(match bytes {
                        Ok(b) if args.iter().any(|a| a == "--so-recorte") => {
                            // só o recorte (sem ComfyUI), para conferir onde a cabeça foi achada
                            let img = fornalha_core::partes::ler_png(&b);
                            match img.as_ref().and_then(fornalha_core::partes::recorte_da_cabeca) {
                                Some(r) => {
                                    let _ = std::fs::create_dir_all(&saida);
                                    let png = fornalha_core::partes::escrever_png(&fornalha_core::partes::recortar(
                                        img.as_ref().unwrap(),
                                        &r,
                                        1024,
                                    ));
                                    let arq = saida.join("cabeca_recorte.png");
                                    std::fs::write(&arq, png)
                                        .map_err(|e| fornalha_core::erro::Erro::io(&arq, e))
                                        .map(|_| serde_json::json!(r))
                                }
                                None => Err(fornalha_core::erro::Erro::novo("sem_figura", "não achei a figura de corpo inteiro")),
                            }
                        }
                        Ok(b) => {
                            fornalha_core::partes::cabeca_no_comfyui(f.porta_comfyui(), &b, &descricao, &saida, 1000, horas * 3600).await
                        }
                        Err(e) => Err(e),
                    })
                }
                _ => {
                    let e = comfyui::consultar(f.porta_comfyui()).await;
                    let vulkan = match comfyui::motor_vulkan(&paths) {
                        Some(m) => serde_json::json!({"motor": m, "dispositivos": comfyui::dispositivos_vulkan(&m).await}),
                        None => serde_json::Value::Null,
                    };
                    imprimir(Ok(serde_json::json!({"estado": e, "caminho": c, "instalacao": comfyui::estado_instalacao(&paths),
                                                   "vulkan": vulkan})))
                }
            }
        }
        Some("versao" | "--version" | "-V") => {
            println!("fornalha-cli {}", fornalha_core::consts::APP_VERSION);
            0
        }
        _ => {
            println!("{AJUDA}");
            if args.is_empty() || matches!(args[0].as_str(), "ajuda" | "--help" | "-h") {
                0
            } else {
                2
            }
        }
    };
    std::process::exit(codigo);
}

async fn servir(f: std::sync::Arc<Fornalha>) -> i32 {
    tokio::spawn(fornalha_core::fila::vigiar(f.clone()));
    eprintln!("Fornalha: API em http://127.0.0.1:{} (MCP em /mcp). Ctrl+C para sair.", f.porta_api());
    match fornalha_core::api::servir(f).await {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("Não consegui abrir a API: {e}");
            1
        }
    }
}

fn imprimir(r: Result<serde_json::Value, fornalha_core::erro::Erro>) -> i32 {
    match r {
        Ok(v) => {
            println!("{}", serde_json::to_string_pretty(&v).unwrap_or_default());
            0
        }
        Err(e) => {
            eprintln!("Erro ({}): {}", e.codigo, e.mensagem);
            1
        }
    }
}
