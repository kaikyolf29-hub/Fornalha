//! Blocos de síntese: ruído, osciladores, filtros, envelopes e reverberação.

use std::f32::consts::TAU;

use super::TAXA;

pub const SR: f32 = TAXA as f32;

/// Gerador pseudoaleatório (xorshift) com semente: mesmo pedido, mesmo som.
#[derive(Clone)]
pub struct Rng(u64);

impl Rng {
    pub fn new(semente: u64) -> Self {
        Rng(semente.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    pub fn proximo(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }
    /// Entre -1 e 1.
    pub fn bipolar(&mut self) -> f32 {
        (self.proximo() >> 40) as f32 / (1u64 << 23) as f32 - 1.0
    }
    /// Entre 0 e 1.
    pub fn unit(&mut self) -> f32 {
        (self.proximo() >> 40) as f32 / (1u64 << 24) as f32
    }
    pub fn entre(&mut self, a: f32, b: f32) -> f32 {
        a + (b - a) * self.unit()
    }
}

pub fn amostras(segundos: f32) -> usize {
    (segundos * SR).round().max(1.0) as usize
}

/// Passa-baixa de um polo.
#[derive(Clone, Default)]
pub struct PassaBaixa {
    y: f32,
}
impl PassaBaixa {
    pub fn processar(&mut self, x: f32, corte: f32) -> f32 {
        let a = 1.0 - (-TAU * corte.clamp(10.0, SR * 0.45) / SR).exp();
        self.y += a * (x - self.y);
        self.y
    }
}

/// Passa-alta de um polo.
#[derive(Clone, Default)]
pub struct PassaAlta {
    lp: PassaBaixa,
}
impl PassaAlta {
    pub fn processar(&mut self, x: f32, corte: f32) -> f32 {
        x - self.lp.processar(x, corte)
    }
}

/// Biquad passa-faixa (RBJ), com centro que pode mudar a cada amostra.
#[derive(Clone, Default)]
pub struct PassaFaixa {
    x1: f32,
    x2: f32,
    y1: f32,
    y2: f32,
}
impl PassaFaixa {
    pub fn processar(&mut self, x: f32, centro: f32, q: f32) -> f32 {
        let w = TAU * centro.clamp(20.0, SR * 0.45) / SR;
        let alfa = w.sin() / (2.0 * q.max(0.1));
        let a0 = 1.0 + alfa;
        let (b0, b2) = (alfa / a0, -alfa / a0);
        let (a1, a2) = (-2.0 * w.cos() / a0, (1.0 - alfa) / a0);
        let y = b0 * x + b2 * self.x2 - a1 * self.y1 - a2 * self.y2;
        self.x2 = self.x1;
        self.x1 = x;
        self.y2 = self.y1;
        self.y1 = y;
        y
    }
}

/// Envelope de ataque e queda exponencial.
pub fn env(t: f32, ataque: f32, queda: f32) -> f32 {
    if t < 0.0 {
        0.0
    } else if t < ataque {
        t / ataque.max(1e-5)
    } else {
        (-(t - ataque) / queda.max(1e-5)).exp()
    }
}

/// Senoide com frequência que varia (fase acumulada).
#[derive(Clone, Default)]
pub struct Osc {
    fase: f32,
}
impl Osc {
    pub fn seno(&mut self, freq: f32) -> f32 {
        self.fase = (self.fase + freq / SR) % 1.0;
        (self.fase * TAU).sin()
    }
    pub fn serra(&mut self, freq: f32) -> f32 {
        self.fase = (self.fase + freq / SR) % 1.0;
        2.0 * self.fase - 1.0
    }
    pub fn quadrada(&mut self, freq: f32) -> f32 {
        self.fase = (self.fase + freq / SR) % 1.0;
        if self.fase < 0.5 {
            1.0
        } else {
            -1.0
        }
    }
}

/// Corda de Karplus-Strong (dedilhado).
pub fn corda(freq: f32, segundos: f32, brilho: f32, rng: &mut Rng) -> Vec<f32> {
    let periodo = (SR / freq.max(20.0)).round().max(2.0) as usize;
    let mut linha: Vec<f32> = (0..periodo).map(|_| rng.bipolar()).collect();
    let n = amostras(segundos);
    let mut out = Vec::with_capacity(n);
    let mut i = 0;
    let perda = 0.996 - (1.0 - brilho.clamp(0.0, 1.0)) * 0.01;
    for _ in 0..n {
        let a = linha[i];
        let b = linha[(i + 1) % periodo];
        linha[i] = perda * 0.5 * (a + b);
        out.push(a);
        i = (i + 1) % periodo;
    }
    out
}

/// Reverberação de Schroeder (4 pentes + 2 passa-tudo), só para dar ambiente.
pub fn reverb(entrada: &[f32], mistura: f32, tamanho: f32) -> Vec<f32> {
    let pentes = [1557usize, 1617, 1491, 1422].map(|d| ((d as f32) * tamanho) as usize);
    let passatudos = [225usize, 556];
    let mut saida = vec![0.0f32; entrada.len()];
    for d in pentes {
        let mut buf = vec![0.0f32; d.max(1)];
        let mut lp = 0.0f32;
        for (i, &x) in entrada.iter().enumerate() {
            let k = i % buf.len();
            let y = buf[k];
            lp = y * 0.75 + lp * 0.25;
            buf[k] = x + lp * 0.80;
            saida[i] += y * 0.25;
        }
    }
    for d in passatudos {
        let mut buf = vec![0.0f32; d];
        let mut k = 0;
        for s in saida.iter_mut() {
            let y = buf[k];
            let v = *s + y * 0.5;
            buf[k] = v;
            *s = y - v * 0.5;
            k = (k + 1) % d;
        }
    }
    entrada.iter().zip(saida).map(|(x, r)| x * (1.0 - mistura) + r * mistura).collect()
}

/// Deixa o pico em `alvo`, com uma saturação leve.
pub fn normalizar(a: &mut [f32], alvo: f32) {
    for x in a.iter_mut() {
        *x = (*x * 1.2).tanh();
    }
    let pico = a.iter().fold(0.0f32, |m, x| m.max(x.abs()));
    if pico > 1e-6 {
        let g = alvo / pico;
        for x in a.iter_mut() {
            *x *= g;
        }
    }
}

/// Soma `b` em `a` a partir de `inicio` (aumenta `a` se precisar).
pub fn somar(a: &mut Vec<f32>, b: &[f32], inicio: usize, ganho: f32) {
    if a.len() < inicio + b.len() {
        a.resize(inicio + b.len(), 0.0);
    }
    for (i, x) in b.iter().enumerate() {
        a[inicio + i] += x * ganho;
    }
}
