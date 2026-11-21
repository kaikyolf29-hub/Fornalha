//! Efeitos sonoros por evento: passos por tipo de chão, golpes, impactos, pulo,
//! dano, morte, moeda e clique de interface. Cada semente dá uma variação.

use super::sintese::{amostras, env, normalizar, Osc, PassaAlta, PassaBaixa, PassaFaixa, Rng, SR};
use crate::erro::{Erro, Resultado};

pub const NOMES: [&str; 14] = [
    "passo_grama",
    "passo_pedra",
    "passo_agua",
    "passo_madeira",
    "golpe",
    "golpe_pesado",
    "impacto",
    "espada",
    "pulo",
    "aterrissagem",
    "dano",
    "morte",
    "moeda",
    "ui_clique",
];

fn ruido_filtrado(n: usize, rng: &mut Rng, mut f: impl FnMut(usize, f32) -> f32) -> Vec<f32> {
    (0..n).map(|i| f(i, rng.bipolar())).collect()
}

fn passo(rng: &mut Rng, dur: f32, corte_alto: f32, corte_baixo: f32, graos: f32, grave: f32) -> Vec<f32> {
    let n = amostras(dur);
    let (mut ha, mut lp, mut osc) = (PassaAlta::default(), PassaBaixa::default(), Osc::default());
    let segundo = rng.entre(0.025, 0.05);
    ruido_filtrado(n, rng, |i, r| {
        let t = i as f32 / SR;
        let e = env(t, 0.004, dur * 0.25) + 0.6 * env(t - segundo, 0.003, dur * 0.2);
        let mut x = lp.processar(ha.processar(r, corte_alto), corte_baixo);
        if graos > 0.0 && (r * 97.0).fract().abs() < graos {
            x += r.signum() * 0.8;
        }
        x * e + osc.seno(90.0 + 60.0 * grave) * grave * env(t, 0.002, 0.03)
    })
}

/// Gera um efeito pelo nome. A mesma semente dá sempre o mesmo som.
pub fn gerar(nome: &str, semente: u64) -> Resultado<Vec<f32>> {
    let mut rng = Rng::new(semente ^ (nome.len() as u64) << 32);
    let mut a = match nome {
        "passo_grama" => passo(&mut rng, 0.2, 900.0, 7000.0, 0.03, 0.0),
        "passo_pedra" => passo(&mut rng, 0.11, 1800.0, 6000.0, 0.0, 0.7),
        "passo_madeira" => {
            let mut v = passo(&mut rng, 0.14, 300.0, 2500.0, 0.0, 1.0);
            let mut bp = PassaFaixa::default();
            for (i, x) in v.iter_mut().enumerate() {
                *x = bp.processar(*x, 850.0, 3.0) * 2.0 + *x * 0.3 * env(i as f32 / SR, 0.001, 0.02);
            }
            v
        }
        "passo_agua" => {
            let n = amostras(0.42);
            let mut bp = PassaFaixa::default();
            let mut bolhas = Osc::default();
            let inicio_bolha = rng.entre(0.08, 0.16);
            let f_bolha = rng.entre(450.0, 800.0);
            ruido_filtrado(n, &mut rng, |i, r| {
                let t = i as f32 / SR;
                let centro = 600.0 + 2600.0 * (t / 0.42);
                bp.processar(r, centro, 1.2) * 1.6 * env(t, 0.01, 0.12)
                    + bolhas.seno(f_bolha * (1.0 + 2.5 * (t - inicio_bolha).max(0.0))) * 0.35 * env(t - inicio_bolha, 0.002, 0.04)
            })
        }
        "golpe" | "golpe_pesado" => {
            let pesado = nome == "golpe_pesado";
            let dur = if pesado { 0.5 } else { 0.32 };
            let n = amostras(dur);
            let mut bp = PassaFaixa::default();
            let (f0, f1) = if pesado { (250.0, 900.0) } else { (500.0, 2400.0) };
            ruido_filtrado(n, &mut rng, |i, r| {
                let t = i as f32 / dur / SR;
                let sino = (t * std::f32::consts::PI).sin().powi(2);
                bp.processar(r, f0 + (f1 - f0) * t, 2.5) * 3.0 * sino
            })
        }
        "impacto" | "aterrissagem" => {
            let dur = if nome == "impacto" { 0.45 } else { 0.3 };
            let n = amostras(dur);
            let mut lp = PassaBaixa::default();
            let mut osc = Osc::default();
            let f = rng.entre(55.0, 75.0);
            ruido_filtrado(n, &mut rng, |i, r| {
                let t = i as f32 / SR;
                osc.seno(f * (1.0 + 2.0 * (-t * 30.0).exp())) * env(t, 0.002, 0.12) + lp.processar(r, 1200.0) * 1.5 * env(t, 0.001, 0.05)
            })
        }
        "espada" => {
            let n = amostras(1.1);
            let parciais = [523.0, 1312.0, 2149.0, 3401.0, 4733.0].map(|f| f * rng.entre(0.97, 1.03));
            let mut oscs = vec![Osc::default(); parciais.len()];
            let mut ha = PassaAlta::default();
            ruido_filtrado(n, &mut rng, |i, r| {
                let t = i as f32 / SR;
                let mut x = ha.processar(r, 3000.0) * env(t, 0.0005, 0.01);
                for (k, (f, o)) in parciais.iter().zip(oscs.iter_mut()).enumerate() {
                    x += o.seno(*f) * env(t, 0.001, 0.5 / (k as f32 + 1.0)) * 0.4;
                }
                x
            })
        }
        "pulo" => {
            let n = amostras(0.28);
            let mut bp = PassaFaixa::default();
            ruido_filtrado(n, &mut rng, |i, r| {
                let t = i as f32 / SR;
                bp.processar(r, 400.0 + 3000.0 * (t / 0.28), 2.0) * 2.5 * env(t, 0.03, 0.08)
            })
        }
        "dano" | "morte" => {
            // gemido: serra com formantes de vogal ("uh" / "aaah")
            let morte = nome == "morte";
            let dur = if morte { 0.9 } else { 0.28 };
            let n = amostras(dur);
            let (mut osc, mut f1, mut f2) = (Osc::default(), PassaFaixa::default(), PassaFaixa::default());
            let base = rng.entre(110.0, 150.0);
            (0..n)
                .map(|i| {
                    let t = i as f32 / SR;
                    let queda = if morte { 1.0 - 0.45 * (t / dur) } else { 1.0 + 0.2 * (t / dur) };
                    let s = osc.serra(base * queda * (1.0 + 0.01 * (t * 33.0).sin()));
                    (f1.processar(s, 700.0, 6.0) * 1.0 + f2.processar(s, 1150.0, 7.0) * 0.6) * env(t, 0.02, dur * 0.45)
                })
                .collect()
        }
        "moeda" => {
            let n = amostras(0.4);
            let (mut a, mut b) = (Osc::default(), Osc::default());
            (0..n)
                .map(|i| {
                    let t = i as f32 / SR;
                    a.seno(1318.5) * env(t, 0.001, 0.06) + b.seno(1760.0) * env(t - 0.07, 0.001, 0.15) * 0.9
                })
                .collect()
        }
        "ui_clique" => {
            let n = amostras(0.03);
            let mut bp = PassaFaixa::default();
            ruido_filtrado(n, &mut rng, |i, r| bp.processar(r, 3200.0, 4.0) * 4.0 * env(i as f32 / SR, 0.0005, 0.006))
        }
        outro => {
            return Err(Erro::novo(
                "efeito_desconhecido",
                format!("O efeito \"{outro}\" não existe. Use um destes: {}.", NOMES.join(", ")),
            ));
        }
    };
    normalizar(&mut a, 0.85);
    Ok(a)
}

/// O pacote que o jogo usa (os nomes batem com o `Sons.tocar` dos scripts).
pub fn pacote_padrao() -> Vec<(String, Vec<f32>)> {
    let mut v = Vec::new();
    for (nome, variacoes) in [
        ("passo_grama", 4),
        ("passo_pedra", 3),
        ("passo_agua", 2),
        ("passo_madeira", 2),
        ("golpe", 3),
        ("golpe_pesado", 2),
        ("impacto", 3),
        ("espada", 2),
        ("pulo", 2),
        ("aterrissagem", 2),
        ("dano", 3),
        ("morte", 2),
        ("moeda", 1),
        ("ui_clique", 1),
    ] {
        for k in 1..=variacoes {
            if let Ok(a) = gerar(nome, k as u64 * 7919) {
                v.push((format!("{nome}_{k:02}"), a));
            }
        }
    }
    v
}
