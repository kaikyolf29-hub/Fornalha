//! Áudio feito pela própria Fornalha, sem modelo de IA e sem placa de vídeo:
//! efeitos por evento (`efeitos`) e música em loop por área e situação
//! (`musica`). É a versão "parecida" do plano para o MOSS-SoundEffect e o
//! ACE-Step, que entram no lugar quando houver placa. Licença: do próprio estúdio.

pub mod efeitos;
pub mod musica;
pub mod sintese;

/// Amostras por segundo de tudo que a Fornalha gera.
pub const TAXA: u32 = 44_100;

/// WAV mono 16 bits (o formato que a Godot e a Erethea importam direto).
pub fn wav_mono_16(amostras: &[f32]) -> Vec<u8> {
    wav_mono_16_taxa(amostras, TAXA)
}

/// Reescreve um WAV com o cabeçalho certo (o de stream, com tamanhos errados, trava a importação da Godot).
pub fn normalizar_wav(bytes: &[u8]) -> Option<Vec<u8>> {
    let (taxa, amostras) = ler_wav_16(bytes)?;
    Some(wav_mono_16_taxa(&amostras, taxa))
}

/// WAV mono 16 bits numa taxa qualquer.
pub fn wav_mono_16_taxa(amostras: &[f32], taxa: u32) -> Vec<u8> {
    let dados = amostras.len() as u32 * 2;
    let mut v = Vec::with_capacity(44 + dados as usize);
    v.extend_from_slice(b"RIFF");
    v.extend_from_slice(&(36 + dados).to_le_bytes());
    v.extend_from_slice(b"WAVEfmt ");
    v.extend_from_slice(&16u32.to_le_bytes());
    v.extend_from_slice(&1u16.to_le_bytes()); // PCM
    v.extend_from_slice(&1u16.to_le_bytes()); // mono
    v.extend_from_slice(&taxa.to_le_bytes());
    v.extend_from_slice(&(taxa * 2).to_le_bytes());
    v.extend_from_slice(&2u16.to_le_bytes());
    v.extend_from_slice(&16u16.to_le_bytes());
    v.extend_from_slice(b"data");
    v.extend_from_slice(&dados.to_le_bytes());
    for &a in amostras {
        let x = if a.is_finite() { a.clamp(-1.0, 1.0) } else { 0.0 };
        v.extend_from_slice(&((x * i16::MAX as f32).round() as i16).to_le_bytes());
    }
    v
}

/// Lê um WAV PCM 16 bits mono (para a curva da boca da dublagem).
pub fn ler_wav_16(bytes: &[u8]) -> Option<(u32, Vec<f32>)> {
    if bytes.len() < 44 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return None;
    }
    let mut i = 12;
    let mut taxa = 0u32;
    let mut canais = 1u16;
    let mut bits = 16u16;
    while i + 8 <= bytes.len() {
        let id = &bytes[i..i + 4];
        let tam = u32::from_le_bytes(bytes[i + 4..i + 8].try_into().ok()?) as usize;
        let corpo = bytes.get(i + 8..(i + 8 + tam).min(bytes.len()))?;
        if id == b"fmt " && corpo.len() >= 16 {
            canais = u16::from_le_bytes(corpo[2..4].try_into().ok()?);
            taxa = u32::from_le_bytes(corpo[4..8].try_into().ok()?);
            bits = u16::from_le_bytes(corpo[14..16].try_into().ok()?);
        } else if id == b"data" {
            if bits != 16 || canais == 0 {
                return None;
            }
            let passo = 2 * canais as usize;
            let amostras = corpo.chunks_exact(passo).map(|c| i16::from_le_bytes([c[0], c[1]]) as f32 / i16::MAX as f32).collect();
            return Some((taxa, amostras));
        }
        i += 8 + tam + (tam & 1);
    }
    None
}

/// Curva de abertura da boca (0 a 1) por quadro, a partir do volume da fala.
/// É o movimento de boca simples; o Audio2Face-3D entra no lugar com placa NVIDIA.
pub fn curva_da_boca(taxa: u32, amostras: &[f32], quadros_por_segundo: u32) -> Vec<f32> {
    let por_quadro = (taxa / quadros_por_segundo.max(1)).max(1) as usize;
    let rms: Vec<f32> = amostras.chunks(por_quadro).map(|c| (c.iter().map(|x| x * x).sum::<f32>() / c.len() as f32).sqrt()).collect();
    let max = rms.iter().cloned().fold(1e-6f32, f32::max);
    let mut suave = 0.0f32;
    rms.iter()
        .map(|r| {
            let alvo = ((r / max) * 1.4).min(1.0);
            suave += (alvo - suave) * 0.6;
            (suave * 100.0).round() / 100.0
        })
        .collect()
}
