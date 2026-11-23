//! 3D por partes: a cabeça sai do conceito do corpo inteiro (recortada e refinada em close pelo motor
//! de imagem, com o mesmo desenho), vira malha própria no TRELLIS.2 e é encaixada no corpo no Blender
//! antes do esqueleto. Num conceito de corpo inteiro a cabeça ocupa ~1/8 da imagem; em close ela
//! ocupa a grade inteira do 3D, com muito mais detalhe (elmo, rosto, cabelo).

use serde::Serialize;
use serde_json::{json, Value};

/// Uma imagem RGB inteira.
#[derive(Debug, Clone, PartialEq)]
pub struct Imagem {
    pub largura: u32,
    pub altura: u32,
    pub px: Vec<[u8; 3]>,
}

impl Imagem {
    fn em(&self, x: u32, y: u32) -> [u8; 3] {
        self.px[(y * self.largura + x) as usize]
    }
}

pub fn ler_png(bytes: &[u8]) -> Option<Imagem> {
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
    let px = (0..total)
        .map(|i| {
            let p = &buf[i * canais..];
            if canais >= 3 {
                [p[0], p[1], p[2]]
            } else {
                [p[0], p[0], p[0]]
            }
        })
        .collect();
    Some(Imagem { largura: info.width, altura: info.height, px })
}

pub fn escrever_png(img: &Imagem) -> Vec<u8> {
    let mut saida = Vec::new();
    {
        let mut enc = png::Encoder::new(&mut saida, img.largura, img.altura);
        enc.set_color(png::ColorType::Rgb);
        enc.set_depth(png::BitDepth::Eight);
        let mut w = enc.write_header().expect("cabeçalho PNG");
        let dados: Vec<u8> = img.px.iter().flat_map(|p| p.iter().copied()).collect();
        w.write_image_data(&dados).expect("dados PNG");
    }
    saida
}

/// Onde a cabeça está no conceito e como o recorte se relaciona com a figura inteira (frações da
/// altura da figura, para o Blender saber a altura da cabeça no corpo).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Recorte {
    pub x: i64,
    pub y: i64,
    pub lado: u32,
    pub fundo: [u8; 3],
    /// topo e base do recorte, medidos do topo da figura, em frações da altura da figura
    pub topo_frac: f64,
    pub base_frac: f64,
    /// onde cortar o corpo (o pescoço), em fração da altura da figura a partir do topo
    pub corte_frac: f64,
}

fn mediana(mut v: Vec<i64>) -> i64 {
    v.sort_unstable();
    v[v.len() / 2]
}

/// Acha a figura pelo fundo liso (cor dos cantos) e recorta a cabeça num quadrado com folga.
pub fn recorte_da_cabeca(img: &Imagem) -> Option<Recorte> {
    let (w, h) = (img.largura, img.altura);
    if w < 64 || h < 64 {
        return None;
    }
    // fundo: a mediana de cada canal nos quatro cantos
    let mut cantos = Vec::new();
    for (cx, cy) in [(0, 0), (w - 8, 0), (0, h - 8), (w - 8, h - 8)] {
        for y in cy..cy + 8 {
            for x in cx..cx + 8 {
                cantos.push(img.em(x, y));
            }
        }
    }
    let fundo = [0, 1, 2].map(|c| mediana(cantos.iter().map(|p| p[c] as i64).collect()) as u8);
    // o fundo do estúdio costuma ter degradê de cima para baixo: o fundo de cada linha são as bordas dela
    let borda = (w / 40).max(4);
    let fundo_da_linha = |y: u32| -> [i64; 3] {
        let v: Vec<[u8; 3]> = (0..borda).chain(w - borda..w).map(|x| img.em(x, y)).collect();
        [0, 1, 2].map(|c| mediana(v.iter().map(|p| p[c] as i64).collect()))
    };
    // linhas com figura (ignora poeira: ao menos 3 pixels)
    let linhas: Vec<Vec<u32>> = (0..h)
        .map(|y| {
            let f = fundo_da_linha(y);
            (0..w)
                .filter(|&x| {
                    let p = img.em(x, y);
                    (0..3).map(|c| (p[c] as i64 - f[c]).abs()).sum::<i64>() > 40
                })
                .collect()
        })
        .collect();
    let com: Vec<u32> = (0..h).filter(|&y| linhas[y as usize].len() >= 3).collect();
    let (topo, base) = (*com.first()?, *com.last()?);
    let alt = (base - topo + 1) as f64;
    if alt < 0.4 * h as f64 {
        return None; // não é um corpo inteiro
    }
    // a cabeça: o primeiro 1/10 da figura
    let ate = topo + (0.10 * alt) as u32;
    let xs: Vec<i64> = (topo..=ate).flat_map(|y| linhas[y as usize].iter().map(|&x| x as i64)).collect();
    if xs.is_empty() {
        return None;
    }
    let cx = mediana(xs.clone());
    let largura_cab = {
        let mut v = xs;
        v.sort_unstable();
        (v[v.len() * 95 / 100] - v[v.len() * 5 / 100]) as f64
    };
    let lado = (0.24 * alt).max(1.7 * largura_cab).round() as i64;
    if lado as f64 > 0.4 * alt {
        return None; // o topo da figura não é uma cabeça (asas abertas, braços erguidos…)
    }
    let y0 = topo as i64 - (0.03 * alt).round() as i64;
    let x0 = cx - lado / 2;
    let base_frac = ((y0 + lado) - topo as i64) as f64 / alt;
    Some(Recorte {
        x: x0,
        y: y0,
        lado: lado as u32,
        fundo,
        topo_frac: (y0 - topo as i64) as f64 / alt,
        base_frac,
        corte_frac: 0.14_f64.min(base_frac - 0.04),
    })
}

/// O quadrado do recorte (fora da imagem vira fundo), ampliado para `saida` px (bilinear).
pub fn recortar(img: &Imagem, r: &Recorte, saida: u32) -> Imagem {
    let lado = r.lado as f64;
    let amostra = |x: f64, y: f64| -> [f64; 3] {
        let xi = x.floor() as i64;
        let yi = y.floor() as i64;
        let pega = |xx: i64, yy: i64| -> [f64; 3] {
            if xx < 0 || yy < 0 || xx >= img.largura as i64 || yy >= img.altura as i64 {
                r.fundo.map(|c| c as f64)
            } else {
                img.em(xx as u32, yy as u32).map(|c| c as f64)
            }
        };
        let (fx, fy) = (x - xi as f64, y - yi as f64);
        let (a, b, c, d) = (pega(xi, yi), pega(xi + 1, yi), pega(xi, yi + 1), pega(xi + 1, yi + 1));
        [0, 1, 2].map(|k| a[k] * (1.0 - fx) * (1.0 - fy) + b[k] * fx * (1.0 - fy) + c[k] * (1.0 - fx) * fy + d[k] * fx * fy)
    };
    let mut px = Vec::with_capacity((saida * saida) as usize);
    for y in 0..saida {
        for x in 0..saida {
            let sx = r.x as f64 + (x as f64 + 0.5) * lado / saida as f64 - 0.5;
            let sy = r.y as f64 + (y as f64 + 0.5) * lado / saida as f64 - 0.5;
            px.push(amostra(sx, sy).map(|c| c.round().clamp(0.0, 255.0) as u8));
        }
    }
    Imagem { largura: saida, altura: saida, px }
}

/// Pedido do refino da cabeça (img2img com força média: mantém o desenho, acrescenta detalhe).
pub fn pedido_da_cabeca(descricao: &str) -> String {
    format!(
        "extreme close-up of the head and shoulders of the same character, exactly the same design, colors and materials: \
         {descricao}. Sharp focus, highly detailed, realistic textures, plain light gray studio background, even soft lighting, \
         front view"
    )
}

/// Resumo do recorte para o Blender (tarefa rig: "cabeca").
pub fn para_o_blender(r: &Recorte, malha: &std::path::Path) -> Value {
    json!({"malha": malha, "topo_frac": r.topo_frac, "base_frac": r.base_frac, "corte_frac": r.corte_frac})
}

/// A cabeça por partes no ComfyUI: recorta do conceito, refina em close (Z-Image, imagem → imagem) e
/// faz a malha (TRELLIS.2). Escreve em `pasta` o recorte, a imagem refinada, a malha e cabeca.json
/// (o que a tarefa rig do Blender usa para encaixar). Devolve o cabeca.json.
pub async fn cabeca_no_comfyui(
    porta: u16,
    conceito: &[u8],
    descricao: &str,
    pasta: &std::path::Path,
    semente: u64,
    segundos_3d: u64,
) -> crate::erro::Resultado<Value> {
    use crate::erro::Erro;
    let img = ler_png(conceito).ok_or_else(|| Erro::novo("imagem_invalida", "O conceito não é um PNG que a Fornalha leia."))?;
    let r = recorte_da_cabeca(&img).ok_or_else(|| {
        Erro::novo("sem_figura", "Não achei uma figura de corpo inteiro no conceito (fundo liso) para recortar a cabeça.")
    })?;
    std::fs::create_dir_all(pasta).map_err(|e| Erro::io(pasta, e))?;
    let recorte = escrever_png(&recortar(&img, &r, 1024));
    let arq = pasta.join("cabeca_recorte.png");
    std::fs::write(&arq, &recorte).map_err(|e| Erro::io(&arq, e))?;
    let (refinada, info_img) = crate::comfyui::gerar_imagem_de_imagem(
        porta,
        recorte,
        "fornalha_cabeca_recorte.png",
        &pedido_da_cabeca(descricao),
        1024,
        semente,
        0.5,
    )
    .await?;
    let arq = pasta.join("cabeca_refinada.png");
    std::fs::write(&arq, &refinada).map_err(|e| Erro::io(&arq, e))?;
    let (glb, info_3d) = crate::comfyui::gerar_3d(porta, refinada, "fornalha_cabeca.png", semente, segundos_3d).await?;
    let malha = pasta.join("cabeca_trellis2.glb");
    std::fs::write(&malha, &glb).map_err(|e| Erro::io(&malha, e))?;
    let mut v = para_o_blender(&r, &malha);
    v["recorte"] = json!(r);
    v["refino"] = info_img;
    v["3d"] = info_3d;
    let arq = pasta.join("cabeca.json");
    std::fs::write(&arq, serde_json::to_string_pretty(&v).unwrap_or_default()).map_err(|e| Erro::io(&arq, e))?;
    Ok(v)
}

#[cfg(test)]
mod testes {
    use super::*;

    /// Boneco de palito: cabeça (quadrado) em cima de um corpo (retângulo), fundo cinza.
    fn boneco() -> Imagem {
        let (w, h) = (200u32, 400u32);
        let mut px = vec![[200u8, 200, 204]; (w * h) as usize];
        let mut pinta = |x0: u32, y0: u32, x1: u32, y1: u32, cor: [u8; 3]| {
            for y in y0..y1 {
                for x in x0..x1 {
                    px[(y * w + x) as usize] = cor;
                }
            }
        };
        pinta(90, 40, 110, 80, [90, 70, 60]); // cabeça 20 px de largura, do 40 ao 80
        pinta(70, 80, 130, 380, [40, 40, 120]); // corpo até 380
        Imagem { largura: w, altura: h, px }
    }

    #[test]
    fn acha_a_cabeca_no_topo_da_figura() {
        let img = boneco();
        let r = recorte_da_cabeca(&img).expect("recorte");
        // figura de 40 a 379 (340 px): lado = max(0,24·340, 1,7·20) ≈ 82
        assert_eq!(r.fundo, [200, 200, 204]);
        assert!((80..=84).contains(&r.lado), "{r:?}");
        assert!(r.x <= 90 && r.x + r.lado as i64 >= 110, "o recorte pega a cabeça inteira: {r:?}");
        assert!(r.y < 40, "folga acima da cabeça: {r:?}");
        assert!(r.topo_frac < 0.0 && r.base_frac > 0.15 && r.corte_frac <= r.base_frac - 0.04, "{r:?}");
    }

    #[test]
    fn recorte_amplia_e_volta_em_png() {
        let img = boneco();
        let r = recorte_da_cabeca(&img).unwrap();
        let c = recortar(&img, &r, 256);
        assert_eq!((c.largura, c.altura, c.px.len()), (256, 256, 256 * 256));
        // o meio de cima do recorte (≈ a cabeça) tem a cor da cabeça
        let meio = c.px[(256 * 90 + 128) as usize];
        assert!(meio[0] < 120 && meio[2] < 100, "{meio:?}");
        let png = escrever_png(&c);
        let de_volta = ler_png(&png).unwrap();
        assert_eq!(de_volta, c);
    }

    #[test]
    fn sem_figura_nao_recorta() {
        let img = Imagem { largura: 100, altura: 100, px: vec![[128, 128, 128]; 10_000] };
        assert!(recorte_da_cabeca(&img).is_none());
    }
}
