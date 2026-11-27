//! Quatro vistas (e o rosto): a textura da malha do 3D pela IA fica mais nítida e mais fiel ao conceito,
//! pelo caminho grátis.
//!
//! O TRELLIS.2 vê só a imagem de frente e inventa o resto; no processador a textura sai menor e borrada
//! (o rosto vira mancha). Aqui a malha é vista de frente, dos dois lados e de costas, sem luz; cada vista
//! de lado e de costas é refinada pelo motor de imagem (Z-Image, imagem → imagem: mesmo desenho, mais
//! detalhe); a frente é o próprio conceito, alinhado à silhueta da malha; o rosto é refinado em close. Tudo
//! volta projetado na textura (Blender, `fc_projetar.py`). Sem o motor de imagem, só o conceito e o rosto
//! dele entram (já tira o borrado da frente).

use std::path::Path;
use std::time::Duration;

use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::externas::Achado;

/// Vistas refinadas pelo motor de imagem: (vista, como pedir, denoise). A frente vem do conceito.
pub const REFINAR: [(&str, &str, f64); 4] = [
    ("esquerda", "left side view, full body profile", 0.35),
    ("costas", "back view, full body seen from behind", 0.35),
    ("direita", "right side view, full body profile", 0.35),
    ("rosto", "extreme close-up portrait of the face, front view, sharp detailed eyes, skin pores", 0.42),
];

/// O pedido do refino de uma vista: o mesmo personagem, só mais detalhe.
pub fn pedido_da_vista(descricao: &str, como: &str) -> String {
    let d = descricao.trim();
    let d = if d.is_empty() { "the character in the image".to_string() } else { d.to_string() };
    format!(
        "the same character, exactly the same design, colors, clothes and materials: {d}. {como}. Sharp focus, highly detailed, \
         realistic textures, plain light gray studio background, even soft lighting"
    )
}

/// Lado da textura nova: 4096 no Máximo, 2048 nos outros.
pub fn lado_da_textura(maximo: bool) -> u32 {
    if maximo {
        4096
    } else {
        2048
    }
}

/// A textura da malha refeita pelas vistas. `porta`: o ComfyUI com o Z-Image (None = sem refino).
/// Escreve em `pasta` as vistas, as refinadas e o vistas.json; grava a malha nova em `saida`.
#[allow(clippy::too_many_arguments)]
pub async fn refinar_textura(
    blender: &Achado,
    pasta_dados: &Path,
    porta: Option<u16>,
    malha: &Path,
    conceito: Option<&Path>,
    descricao: &str,
    pasta: &Path,
    semente: u64,
    saida: &Path,
    lado: u32,
    previa: Option<&Path>,
) -> Resultado<Value> {
    std::fs::create_dir_all(pasta).map_err(|e| Erro::io(pasta, e))?;
    let r = crate::forja::rodar(
        blender,
        pasta_dados,
        &json!({"tarefa": "vistas", "entrada": malha, "pasta": pasta, "conceito": conceito}),
        Duration::from_secs(30 * 60),
    )
    .await?;
    let vistas = &r["vistas"];
    let mut imagens = serde_json::Map::new();
    for (nome, v) in vistas["vistas"].as_object().into_iter().flatten() {
        if let Some(arq) = v["imagem"].as_str() {
            imagens.insert(nome.clone(), json!(arq));
        }
    }
    let frente_do_conceito = vistas["frente_conceito"].as_str().is_some();
    if let Some(f) = vistas["frente_conceito"].as_str() {
        imagens.insert("frente".into(), json!(f));
    }
    let mut refinadas = serde_json::Map::new();
    let mut avisos: Vec<String> = Vec::new();
    if let Some(porta) = porta {
        for (k, (nome, como, denoise)) in REFINAR.iter().enumerate() {
            let Some(v) = vistas["vistas"].get(*nome) else { continue };
            let Some(arq) = v["imagem"].as_str() else { continue };
            let Ok(png) = std::fs::read(arq) else { continue };
            // o refino trabalha em múltiplos de 64 perto do tamanho da vista (no processador, menor = mais rápido)
            let (lv, av) = (
                v["largura"].as_u64().unwrap_or(vistas["largura"].as_u64().unwrap_or(768)),
                v["altura"].as_u64().unwrap_or(vistas["altura"].as_u64().unwrap_or(1152)),
            );
            let escala = (1024.0 / av.max(lv) as f64).min(1.0);
            let (largura, altura) = (((lv as f64 * escala) as u32 / 64).max(1) * 64, ((av as f64 * escala) as u32 / 64).max(1) * 64);
            match crate::comfyui::gerar_imagem_de_imagem(
                porta,
                png,
                &format!("fornalha_vista_{nome}.png"),
                &pedido_da_vista(descricao, como),
                largura,
                altura,
                semente.wrapping_add(k as u64),
                *denoise,
            )
            .await
            {
                Ok((png, info)) => {
                    let destino = pasta.join(format!("vista_{nome}_refinada.png"));
                    std::fs::write(&destino, &png).map_err(|e| Erro::io(&destino, e))?;
                    imagens.insert((*nome).into(), json!(destino));
                    refinadas.insert((*nome).into(), info);
                }
                Err(e) => avisos.push(format!("A vista {nome} não foi refinada ({}): entrou como estava.", e.mensagem)),
            }
        }
    } else {
        avisos.push("Sem o motor de imagem (Z-Image) aberto: entraram só o conceito na frente e o rosto dele.".into());
    }
    let p = crate::forja::rodar(
        blender,
        pasta_dados,
        &json!({"tarefa": "projetar", "entrada": malha, "vistas": pasta.join("vistas.json"), "imagens": imagens,
                "frente_do_conceito": frente_do_conceito, "saida": saida, "lado": lado, "previa": previa}),
        Duration::from_secs(60 * 60),
    )
    .await?;
    let resumo = json!({"vistas": pasta.join("vistas.json"), "imagens": imagens, "refinadas": refinadas, "projecao": p["projecao"],
                        "alinhamento": vistas["alinhamento"], "arquivos": p["arquivos"], "avisos": avisos});
    let arq = pasta.join("vistas_resumo.json");
    std::fs::write(&arq, serde_json::to_string_pretty(&resumo).unwrap_or_default()).map_err(|e| Erro::io(&arq, e))?;
    Ok(resumo)
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn pedido_pede_o_mesmo_personagem_e_a_vista() {
        let p = pedido_da_vista("homem de jaqueta de couro", "back view");
        assert!(p.contains("the same character") && p.contains("homem de jaqueta de couro") && p.contains("back view"));
        assert!(pedido_da_vista("  ", "x").contains("the character in the image"));
    }

    #[test]
    fn textura_maior_no_maximo() {
        assert_eq!(lado_da_textura(true), 4096);
        assert_eq!(lado_da_textura(false), 2048);
    }

    #[test]
    fn frente_nao_e_refinada_pelo_motor() {
        // a frente é o conceito (já nítido); refinar ela inventaria outro desenho
        assert!(REFINAR.iter().all(|(n, _, _)| *n != "frente"));
        assert!(REFINAR.iter().all(|(_, _, d)| *d > 0.2 && *d < 0.5));
    }
}
