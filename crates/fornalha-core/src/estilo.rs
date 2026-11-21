//! Checagem do guia visual: mede quanto de cada imagem e modelo gerado está na
//! paleta da bíblia (distância de cor em Lab, que segue o olho humano). Pixels
//! neutros (cinzas, fundo claro) contam à parte. A checagem de forma e conteúdo
//! (o "evitar" da bíblia) precisa de um modelo de visão no Ignis (pedido 7).

use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::projeto::Projeto;

/// Distância (ΔE76) até a cor da paleta para contar como "na paleta".
const PERTO: f32 = 28.0;
/// Fração mínima dos pixels coloridos que precisa estar na paleta.
pub const LIMITE_PADRAO: f32 = 0.4;
const PASTAS: [&str; 6] = ["Characters", "Enemies", "Weapons", "Items", "World", "ai/conceitos"];

fn hex_para_rgb(h: &str) -> Option<[u8; 3]> {
    let h = h.trim().trim_start_matches('#');
    if h.len() != 6 {
        return None;
    }
    let v = u32::from_str_radix(h, 16).ok()?;
    Some([(v >> 16) as u8, (v >> 8) as u8, v as u8])
}

fn rgb_para_hex(c: [u8; 3]) -> String {
    format!("#{:02x}{:02x}{:02x}", c[0], c[1], c[2])
}

fn linear(c: f32) -> f32 {
    if c <= 0.04045 {
        c / 12.92
    } else {
        ((c + 0.055) / 1.055).powf(2.4)
    }
}

fn srgb_de_linear(c: f32) -> f32 {
    if c <= 0.003_130_8 {
        c * 12.92
    } else {
        1.055 * c.powf(1.0 / 2.4) - 0.055
    }
}

/// sRGB (0–255) → CIE Lab (D65).
pub fn lab(c: [u8; 3]) -> [f32; 3] {
    let [r, g, b] = c.map(|x| linear(x as f32 / 255.0));
    let x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
    let y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    let z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
    let f = |t: f32| if t > 0.008_856 { t.cbrt() } else { 7.787 * t + 16.0 / 116.0 };
    let (fx, fy, fz) = (f(x), f(y), f(z));
    [116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)]
}

fn delta_e(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

/// Cinza, quase branco ou quase preto: não conta contra a paleta.
fn neutro(c: [u8; 3]) -> bool {
    let mx = *c.iter().max().unwrap() as f32;
    let mn = *c.iter().min().unwrap() as f32;
    let sat = if mx <= 0.0 { 0.0 } else { (mx - mn) / mx };
    sat < 0.15 || mx < 30.0
}

/// Pixels RGB de um PNG (amostrados para no máximo ~40 mil).
pub fn pixels_png(bytes: &[u8]) -> Option<Vec<[u8; 3]>> {
    let mut dec = png::Decoder::new(std::io::Cursor::new(bytes));
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut leitor = dec.read_info().ok()?;
    let mut buf = vec![0u8; leitor.output_buffer_size()?];
    let info = leitor.next_frame(&mut buf).ok()?;
    let canais = match info.color_type {
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        png::ColorType::Indexed => return None,
    };
    let total = (info.width * info.height) as usize;
    let passo = (total / 40_000).max(1);
    let mut v = Vec::with_capacity(total / passo + 1);
    for i in (0..total).step_by(passo) {
        let o = i * canais;
        let px = &buf[o..o + canais];
        let (rgb, alfa) = match canais {
            4 => ([px[0], px[1], px[2]], px[3]),
            3 => ([px[0], px[1], px[2]], 255),
            2 => ([px[0], px[0], px[0]], px[1]),
            _ => ([px[0], px[0], px[0]], 255),
        };
        if alfa > 16 {
            v.push(rgb);
        }
    }
    Some(v)
}

/// Cores de um glb: as cores dos materiais e os pixels das texturas PNG embutidas.
pub fn cores_glb(bytes: &[u8]) -> Option<Vec<[u8; 3]>> {
    if bytes.len() < 20 || &bytes[0..4] != b"glTF" {
        return None;
    }
    let tam_json = u32::from_le_bytes(bytes[12..16].try_into().ok()?) as usize;
    let gltf: Value = serde_json::from_slice(bytes.get(20..20 + tam_json)?).ok()?;
    let inicio_bin = 20 + tam_json + 8;
    let bin = bytes.get(inicio_bin..).unwrap_or(&[]);
    let mut cores = Vec::new();
    for m in gltf["materials"].as_array().cloned().unwrap_or_default() {
        if m["name"].as_str().is_some_and(|n| n.to_lowercase().contains("colis")) {
            continue;
        }
        if m["pbrMetallicRoughness"]["baseColorTexture"].is_object() {
            continue; // a textura entra pelos pixels
        }
        if let Some(f) = m["pbrMetallicRoughness"]["baseColorFactor"].as_array() {
            let c: Vec<f32> = f.iter().take(3).filter_map(|x| x.as_f64()).map(|x| x as f32).collect();
            if c.len() == 3 {
                let rgb = [0, 1, 2].map(|i| (srgb_de_linear(c[i].clamp(0.0, 1.0)) * 255.0).round() as u8);
                // peso de uma cor de material: como 400 pixels
                cores.extend(std::iter::repeat_n(rgb, 400));
            }
        }
    }
    for img in gltf["images"].as_array().cloned().unwrap_or_default() {
        if img["mimeType"].as_str() != Some("image/png") {
            continue;
        }
        let Some(bv) = img["bufferView"].as_u64().and_then(|i| gltf["bufferViews"].get(i as usize)) else { continue };
        let off = bv["byteOffset"].as_u64().unwrap_or(0) as usize;
        let len = bv["byteLength"].as_u64().unwrap_or(0) as usize;
        if let Some(px) = bin.get(off..off + len).and_then(pixels_png) {
            cores.extend(px.into_iter().filter(|c| c.iter().map(|x| *x as u32).sum::<u32>() > 6));
        }
    }
    Some(cores)
}

/// Mede um conjunto de cores contra a paleta.
pub fn medir(cores: &[[u8; 3]], paleta: &[[u8; 3]], limite: f32) -> Value {
    let pal_lab: Vec<[f32; 3]> = paleta.iter().map(|c| lab(*c)).collect();
    let mut neutros = 0usize;
    let mut na_paleta = 0usize;
    let mut por_cor = vec![0usize; paleta.len()];
    let mut baldes: std::collections::HashMap<u16, (usize, [u32; 3])> = std::collections::HashMap::new();
    for c in cores {
        if neutro(*c) {
            neutros += 1;
            continue;
        }
        let l = lab(*c);
        let (i, d) = pal_lab.iter().enumerate().map(|(i, p)| (i, delta_e(l, *p))).fold((0, f32::MAX), |a, b| if b.1 < a.1 { b } else { a });
        if d <= PERTO {
            na_paleta += 1;
            por_cor[i] += 1;
        }
        let chave = ((c[0] as u16 >> 4) << 8) | ((c[1] as u16 >> 4) << 4) | (c[2] as u16 >> 4);
        let e = baldes.entry(chave).or_insert((0, [0, 0, 0]));
        e.0 += 1;
        for (soma, canal) in e.1.iter_mut().zip(c) {
            *soma += *canal as u32;
        }
    }
    let coloridos = cores.len() - neutros;
    let fracao = if coloridos == 0 { 1.0 } else { na_paleta as f32 / coloridos as f32 };
    let mut dominantes: Vec<(usize, [u8; 3])> = baldes.into_values().map(|(n, s)| (n, s.map(|x| (x / n as u32) as u8))).collect();
    dominantes.sort_by_key(|d| std::cmp::Reverse(d.0));
    let fora: Vec<String> = dominantes
        .iter()
        .take(6)
        .filter(|(_, c)| pal_lab.iter().all(|p| delta_e(lab(*c), *p) > PERTO))
        .map(|(_, c)| rgb_para_hex(*c))
        .collect();
    json!({
        "amostras": cores.len(),
        "neutros": round2(if cores.is_empty() { 0.0 } else { neutros as f32 / cores.len() as f32 }),
        "na_paleta": round2(fracao),
        "aprovado": fracao >= limite,
        "cores_dominantes": dominantes.iter().take(5).map(|(_, c)| rgb_para_hex(*c)).collect::<Vec<_>>(),
        "fora_da_paleta": fora,
        "uso_da_paleta": paleta.iter().zip(por_cor).map(|(c, n)| json!({"cor": rgb_para_hex(*c), "fracao": round2(if coloridos == 0 { 0.0 } else { n as f32 / coloridos as f32 })})).collect::<Vec<_>>(),
    })
}

fn round2(x: f32) -> f64 {
    (x as f64 * 100.0).round() / 100.0
}

fn assets_do_projeto(raiz: &Path) -> Vec<PathBuf> {
    fn andar(d: &Path, v: &mut Vec<PathBuf>) {
        for e in std::fs::read_dir(d).into_iter().flatten().flatten() {
            let p = e.path();
            if p.is_dir() {
                andar(&p, v);
            } else if let Some(ext) = p.extension().and_then(|x| x.to_str()) {
                let nome = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
                let e_previa = nome.contains(".previa.") || nome.contains(".folha.");
                if ext.eq_ignore_ascii_case("glb") || (ext.eq_ignore_ascii_case("png") && !e_previa) {
                    v.push(p);
                }
            }
        }
    }
    let mut v = Vec::new();
    for pasta in PASTAS {
        andar(&raiz.join(pasta), &mut v);
    }
    v.sort();
    v
}

/// check_style: um arquivo ou todos os assets do projeto contra a paleta da bíblia.
pub fn conferir(p: &Projeto, arquivo: Option<&Path>, limite: Option<f32>) -> Resultado<Value> {
    let paleta: Vec<[u8; 3]> = p.biblia.guia_visual.paleta.iter().filter_map(|h| hex_para_rgb(h)).collect();
    if paleta.is_empty() {
        return Err(Erro::novo("sem_paleta", "A bíblia ainda não tem paleta (guia visual). Defina as cores do jogo e confira de novo."));
    }
    let limite = limite.unwrap_or(LIMITE_PADRAO).clamp(0.0, 1.0);
    let arquivos = match arquivo {
        Some(a) => vec![a.to_path_buf()],
        None => assets_do_projeto(&p.raiz),
    };
    let mut resultados = Vec::new();
    for a in &arquivos {
        let bytes = std::fs::read(a).map_err(|e| Erro::io(a, e))?;
        let cores = if a.extension().is_some_and(|e| e.eq_ignore_ascii_case("glb")) { cores_glb(&bytes) } else { pixels_png(&bytes) };
        let rel = a.strip_prefix(&p.raiz).unwrap_or(a).to_string_lossy().replace('\\', "/");
        match cores {
            Some(c) if !c.is_empty() => {
                let mut m = medir(&c, &paleta, limite);
                m["arquivo"] = json!(rel);
                resultados.push(m);
            }
            _ => {
                resultados.push(json!({"arquivo": rel, "aprovado": Value::Null, "motivo": "sem cores para medir (formato não suportado)"}))
            }
        }
    }
    let aprovados = resultados.iter().filter(|r| r["aprovado"] == true).count();
    let reprovados: Vec<Value> = resultados.iter().filter(|r| r["aprovado"] == false).map(|r| r["arquivo"].clone()).collect();
    Ok(json!({
        "paleta": paleta.iter().map(|c| rgb_para_hex(*c)).collect::<Vec<_>>(),
        "limite": limite,
        "conferidos": resultados.len(),
        "aprovados": aprovados,
        "fora_do_guia": reprovados,
        "resultados": resultados,
        "nota": "Mede as cores contra a paleta. Forma e conteúdo (o \"evitar\" da bíblia) precisam do modelo de visão no Ignis.",
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lab_e_distancia() {
        let branco = lab([255, 255, 255]);
        assert!((branco[0] - 100.0).abs() < 0.5);
        assert!(delta_e(lab([200, 30, 30]), lab([205, 35, 28])) < 5.0);
        assert!(delta_e(lab([200, 30, 30]), lab([30, 50, 210])) > 60.0);
    }

    #[test]
    fn medir_paleta() {
        let pal = [[200, 30, 30], [30, 50, 210]];
        let mut cores = vec![[198, 32, 33]; 60];
        cores.extend(vec![[40, 180, 40]; 40]); // verde fora da paleta
        cores.extend(vec![[128, 128, 128]; 100]); // neutro
        let m = medir(&cores, &pal, 0.5);
        assert_eq!(m["na_paleta"], 0.6);
        assert_eq!(m["aprovado"], true);
        assert_eq!(m["neutros"], 0.5);
        assert_eq!(m["fora_da_paleta"].as_array().unwrap().len(), 1);
        assert!(!medir(&cores, &pal, 0.7)["aprovado"].as_bool().unwrap());
    }
}
