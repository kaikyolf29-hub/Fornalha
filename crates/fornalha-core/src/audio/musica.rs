//! Trilha por área e situação, pronta para tocar em loop: o final emenda no
//! começo sem estalo (a cauda das notas volta para o início do arquivo).

use serde::Serialize;

use super::sintese::{amostras, corda, env, normalizar, reverb, somar, Osc, PassaAlta, PassaBaixa, Rng, SR};
use crate::erro::{Erro, Resultado};

pub const SITUACOES: [&str; 6] = ["exploracao", "vila", "floresta", "combate", "chefe", "masmorra"];

#[derive(Debug, Clone, Serialize)]
pub struct Musica {
    pub situacao: String,
    pub bpm: u32,
    pub compassos: u32,
    pub tonica: String,
    #[serde(skip)]
    pub amostras: Vec<f32>,
}

struct Estilo {
    bpm: u32,
    tonica: f32, // Hz da nota base
    nome_tonica: &'static str,
    escala: &'static [i32],
    acordes: &'static [i32], // graus da escala, um por compasso
    pad: f32,
    arpejo: f32,
    melodia: f32,
    baixo: f32,
    bateria: f32,
    sino: f32,
    reverb: f32,
}

const MENOR: [i32; 7] = [0, 2, 3, 5, 7, 8, 10];
const DORICO: [i32; 7] = [0, 2, 3, 5, 7, 9, 10];
const MAIOR: [i32; 7] = [0, 2, 4, 5, 7, 9, 11];
const FRIGIO: [i32; 7] = [0, 1, 3, 5, 7, 8, 10];

fn estilo(situacao: &str) -> Option<(&'static str, Estilo)> {
    let s = situacao.trim().to_lowercase();
    let chave = SITUACOES.iter().find(|x| s == **x).copied().or_else(|| {
        if s.contains("chefe") || s.contains("boss") {
            Some("chefe")
        } else if s.contains("combate") || s.contains("luta") || s.contains("batalha") {
            Some("combate")
        } else if s.contains("vila") || s.contains("cidade") || s.contains("aldeia") {
            Some("vila")
        } else if s.contains("floresta") || s.contains("bosque") {
            Some("floresta")
        } else if s.contains("masmorra") || s.contains("caverna") || s.contains("cripta") {
            Some("masmorra")
        } else if s.contains("explor") || s.contains("campo") || s.contains("viagem") {
            Some("exploracao")
        } else {
            None
        }
    })?;
    let e = match chave {
        "exploracao" => Estilo {
            bpm: 92,
            tonica: 146.83,
            nome_tonica: "Ré dórico",
            escala: &DORICO,
            acordes: &[0, 6, 5, 6],
            pad: 0.5,
            arpejo: 0.5,
            melodia: 0.45,
            baixo: 0.35,
            bateria: 0.25,
            sino: 0.0,
            reverb: 0.3,
        },
        "vila" => Estilo {
            bpm: 104,
            tonica: 196.0,
            nome_tonica: "Sol maior",
            escala: &MAIOR,
            acordes: &[0, 4, 5, 3],
            pad: 0.35,
            arpejo: 0.6,
            melodia: 0.55,
            baixo: 0.35,
            bateria: 0.3,
            sino: 0.0,
            reverb: 0.22,
        },
        "floresta" => Estilo {
            bpm: 86,
            tonica: 164.81,
            nome_tonica: "Mi menor",
            escala: &MENOR,
            acordes: &[0, 5, 2, 6],
            pad: 0.55,
            arpejo: 0.35,
            melodia: 0.5,
            baixo: 0.25,
            bateria: 0.12,
            sino: 0.2,
            reverb: 0.38,
        },
        "combate" => Estilo {
            bpm: 140,
            tonica: 110.0,
            nome_tonica: "Lá menor",
            escala: &MENOR,
            acordes: &[0, 5, 2, 6],
            pad: 0.3,
            arpejo: 0.55,
            melodia: 0.35,
            baixo: 0.6,
            bateria: 0.7,
            sino: 0.0,
            reverb: 0.15,
        },
        "chefe" => Estilo {
            bpm: 150,
            tonica: 82.41,
            nome_tonica: "Mi frígio",
            escala: &FRIGIO,
            acordes: &[0, 1, 0, 6],
            pad: 0.55,
            arpejo: 0.45,
            melodia: 0.3,
            baixo: 0.7,
            bateria: 0.8,
            sino: 0.0,
            reverb: 0.2,
        },
        "masmorra" => Estilo {
            bpm: 68,
            tonica: 130.81,
            nome_tonica: "Dó menor",
            escala: &MENOR,
            acordes: &[0, 3, 0, 4],
            pad: 0.65,
            arpejo: 0.0,
            melodia: 0.2,
            baixo: 0.4,
            bateria: 0.1,
            sino: 0.45,
            reverb: 0.45,
        },
        _ => return None,
    };
    Some((chave, e))
}

fn nota(e: &Estilo, grau: i32, oitava: i32) -> f32 {
    let n = e.escala.len() as i32;
    let o = grau.div_euclid(n) + oitava;
    let semitom = e.escala[grau.rem_euclid(n) as usize] + 12 * o;
    e.tonica * 2f32.powf(semitom as f32 / 12.0)
}

fn pad(freqs: &[f32], dur: f32) -> Vec<f32> {
    let n = amostras(dur + 0.8);
    let mut oscs: Vec<Osc> = (0..freqs.len() * 3).map(|_| Osc::default()).collect();
    let mut lp = PassaBaixa::default();
    (0..n)
        .map(|i| {
            let t = i as f32 / SR;
            let mut x = 0.0;
            for (k, f) in freqs.iter().enumerate() {
                for (j, d) in [0.997f32, 1.0, 1.004].iter().enumerate() {
                    x += oscs[k * 3 + j].serra(f * d);
                }
            }
            let e = if t < dur { (t / 0.35).min(1.0) } else { (-(t - dur) / 0.3).exp() };
            lp.processar(x / (freqs.len() as f32 * 3.0), 1400.0) * e
        })
        .collect()
}

fn baixo(f: f32, dur: f32) -> Vec<f32> {
    let n = amostras(dur + 0.1);
    let (mut o, mut lp) = (Osc::default(), PassaBaixa::default());
    (0..n).map(|i| lp.processar(o.quadrada(f) * 0.6 + o.seno(f) * 0.4, 500.0) * env(i as f32 / SR, 0.005, dur * 0.8)).collect()
}

fn sino(f: f32) -> Vec<f32> {
    let n = amostras(2.0);
    let (mut c, mut m) = (Osc::default(), Osc::default());
    (0..n)
        .map(|i| {
            let t = i as f32 / SR;
            let modulo = m.seno(f * 3.5) * 2.0 * env(t, 0.001, 0.6);
            c.seno(f * (1.0 + modulo * 0.02)) * env(t, 0.002, 0.8)
        })
        .collect()
}

fn flauta(f: f32, dur: f32, rng: &mut Rng) -> Vec<f32> {
    let n = amostras(dur + 0.15);
    let (mut o, mut vib, mut lp) = (Osc::default(), Osc::default(), PassaBaixa::default());
    (0..n)
        .map(|i| {
            let t = i as f32 / SR;
            let v = 1.0 + 0.006 * vib.seno(5.2) * (t / 0.3).min(1.0);
            let sopro = lp.processar(rng.bipolar(), 3000.0) * 0.05;
            let e = if t < dur { (t / 0.04).min(1.0) } else { (-(t - dur) / 0.08).exp() };
            (o.seno(f * v) + 0.2 * o.seno(f * 2.0 * v) + sopro) * e
        })
        .collect()
}

fn bumbo() -> Vec<f32> {
    let n = amostras(0.35);
    let mut o = Osc::default();
    (0..n)
        .map(|i| {
            let t = i as f32 / SR;
            o.seno(45.0 + 110.0 * (-t * 35.0).exp()) * env(t, 0.001, 0.12)
        })
        .collect()
}

fn caixa(rng: &mut Rng) -> Vec<f32> {
    let n = amostras(0.22);
    let (mut ha, mut o) = (PassaAlta::default(), Osc::default());
    (0..n)
        .map(|i| {
            let t = i as f32 / SR;
            ha.processar(rng.bipolar(), 1500.0) * env(t, 0.001, 0.06) * 0.8 + o.seno(190.0) * env(t, 0.001, 0.04) * 0.5
        })
        .collect()
}

fn chimbal(rng: &mut Rng) -> Vec<f32> {
    let n = amostras(0.06);
    let mut ha = PassaAlta::default();
    (0..n).map(|i| ha.processar(rng.bipolar(), 7000.0) * env(i as f32 / SR, 0.0005, 0.018) * 0.5).collect()
}

/// Compõe `compassos` compassos (4 tempos) para a situação.
pub fn compor(situacao: &str, compassos: u32, semente: u64) -> Resultado<Musica> {
    let Some((chave, e)) = estilo(situacao) else {
        return Err(Erro::novo(
            "situacao_desconhecida",
            format!("Não sei compor para \"{situacao}\". Use uma destas: {}.", SITUACOES.join(", ")),
        ));
    };
    let compassos = compassos.clamp(1, 64);
    let mut rng = Rng::new(semente.wrapping_add(chave.len() as u64 * 131));
    let tempo = 60.0 / e.bpm as f32;
    let total = (compassos as f64 * 4.0 * tempo as f64 * SR as f64).round() as usize;
    let mut mix = vec![0.0f32; total];
    let pos = |batida: f32| (batida * tempo * SR) as usize;
    // motivo da melodia: graus que se repetem com variação a cada 2 compassos
    let motivo: Vec<i32> = (0..8).map(|_| [0, 1, 2, 3, 4, 2, 4, 5][(rng.proximo() % 8) as usize]).collect();
    let ritmo: Vec<f32> = match chave {
        "combate" | "chefe" => vec![0.0, 0.75, 1.5, 2.0, 2.5, 3.0],
        "masmorra" => vec![0.0, 2.5],
        _ => vec![0.0, 1.0, 1.5, 2.0, 3.0],
    };
    for c in 0..compassos {
        let grau = e.acordes[c as usize % e.acordes.len()];
        let inicio = c as f32 * 4.0;
        let acorde: Vec<f32> = [0, 2, 4].iter().map(|d| nota(&e, grau + d, 0)).collect();
        if e.pad > 0.0 {
            somar(&mut mix, &pad(&acorde, 4.0 * tempo), pos(inicio), e.pad * 0.5);
        }
        if e.baixo > 0.0 {
            let passos: &[f32] = if e.bpm >= 130 { &[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5] } else { &[0.0, 2.0] };
            let dur = if e.bpm >= 130 { 0.5 } else { 2.0 } * tempo;
            for p in passos {
                somar(&mut mix, &baixo(nota(&e, grau, -1), dur), pos(inicio + p), e.baixo * 0.45);
            }
        }
        if e.arpejo > 0.0 {
            let sub = if e.bpm >= 130 { 0.25 } else { 0.5 };
            let mut b = 0.0;
            let mut k = 0;
            while b < 4.0 {
                let f = nota(&e, grau + [0, 2, 4, 7][k % 4], 1);
                somar(&mut mix, &corda(f, 0.9, 0.6, &mut rng), pos(inicio + b), e.arpejo * 0.28);
                b += sub;
                k += 1;
            }
        }
        if e.melodia > 0.0 {
            let variacao = if c % 4 >= 2 { 1 } else { 0 };
            for (k, r) in ritmo.iter().enumerate() {
                let g = motivo[(k + c as usize * 2) % motivo.len()] + variacao;
                let dur = ritmo.get(k + 1).copied().unwrap_or(4.0) - r;
                somar(&mut mix, &flauta(nota(&e, g, 1), dur * tempo * 0.9, &mut rng), pos(inicio + r), e.melodia * 0.3);
            }
        }
        if e.sino > 0.0 && c % 2 == 0 {
            somar(&mut mix, &sino(nota(&e, grau + 4, 2)), pos(inicio + 1.0), e.sino * 0.3);
        }
        if e.bateria > 0.0 {
            let pesada = e.bpm >= 130;
            for b in 0..4 {
                let bf = b as f32;
                if b == 0 || b == 2 || (pesada && b == 3) {
                    somar(&mut mix, &bumbo(), pos(inicio + bf), e.bateria * 0.7);
                }
                if b == 1 || b == 3 {
                    somar(&mut mix, &caixa(&mut rng), pos(inicio + bf), e.bateria * 0.45);
                }
                for meio in [0.0, 0.5] {
                    somar(&mut mix, &chimbal(&mut rng), pos(inicio + bf + meio), e.bateria * 0.35);
                }
            }
        }
    }
    let mut mix = reverb(&mix, e.reverb, 1.0);
    // emenda: a cauda que passou do fim volta para o começo
    let cauda: Vec<f32> = mix.drain(total..).collect();
    for (i, x) in cauda.into_iter().enumerate() {
        mix[i % total] += x;
    }
    normalizar(&mut mix, 0.8);
    Ok(Musica { situacao: chave.into(), bpm: e.bpm, compassos, tonica: e.nome_tonica.into(), amostras: mix })
}
