//! Áudio feito pela própria Fornalha (sem modelo, sem placa): efeitos por evento
//! e música em loop por área e situação.

use fornalha_core::audio::{self, efeitos, musica, TAXA};

fn rms(a: &[f32]) -> f32 {
    (a.iter().map(|x| x * x).sum::<f32>() / a.len().max(1) as f32).sqrt()
}

fn cruzamentos_por_segundo(a: &[f32]) -> f32 {
    let n = a.windows(2).filter(|w| (w[0] >= 0.0) != (w[1] >= 0.0)).count();
    n as f32 / (a.len() as f32 / TAXA as f32)
}

#[test]
fn wav_valido() {
    let wav = audio::wav_mono_16(&[0.0, 0.5, -0.5, 1.5, -2.0]);
    assert_eq!(&wav[0..4], b"RIFF");
    assert_eq!(&wav[8..12], b"WAVE");
    assert_eq!(u32::from_le_bytes(wav[24..28].try_into().unwrap()), TAXA);
    assert_eq!(u16::from_le_bytes(wav[22..24].try_into().unwrap()), 1, "mono");
    assert_eq!(wav.len(), 44 + 5 * 2);
    // valores fora de [-1, 1] são limitados (sem estouro)
    assert_eq!(i16::from_le_bytes(wav[50..52].try_into().unwrap()), i16::MAX);
}

#[test]
fn todos_os_efeitos_tem_som_sem_estourar() {
    for nome in efeitos::NOMES {
        let a = efeitos::gerar(nome, 1).unwrap();
        let dur = a.len() as f32 / TAXA as f32;
        assert!((0.01..2.0).contains(&dur), "{nome}: {dur} s");
        let pico = a.iter().fold(0.0f32, |m, x| m.max(x.abs()));
        assert!(pico > 0.2 && pico <= 1.0, "{nome}: pico {pico}");
        assert!(a.iter().all(|x| x.is_finite()), "{nome}");
    }
}

#[test]
fn efeito_desconhecido_explica() {
    let e = efeitos::gerar("trovao_magico", 1).unwrap_err();
    assert_eq!(e.codigo, "efeito_desconhecido");
}

#[test]
fn mesma_semente_mesmo_som_e_semente_nova_varia() {
    assert_eq!(efeitos::gerar("passo_grama", 7).unwrap(), efeitos::gerar("passo_grama", 7).unwrap());
    assert_ne!(efeitos::gerar("passo_grama", 7).unwrap(), efeitos::gerar("passo_grama", 8).unwrap());
}

#[test]
fn passo_na_pedra_e_mais_seco_que_na_agua() {
    let pedra = efeitos::gerar("passo_pedra", 1).unwrap();
    let agua = efeitos::gerar("passo_agua", 1).unwrap();
    assert!(pedra.len() < agua.len(), "pedra é curto, água espirra");
}

#[test]
fn passo_na_grama_e_mais_agudo_que_o_impacto() {
    let grama = efeitos::gerar("passo_grama", 3).unwrap();
    let impacto = efeitos::gerar("impacto", 3).unwrap();
    assert!(cruzamentos_por_segundo(&grama) > cruzamentos_por_segundo(&impacto) * 2.0);
}

#[test]
fn pacote_padrao_tem_as_variacoes_que_o_jogo_usa() {
    let lista = efeitos::pacote_padrao();
    let nomes: Vec<&str> = lista.iter().map(|(n, _)| n.as_str()).collect();
    for base in ["passo_grama_01", "passo_pedra_01", "pulo_01", "golpe_01", "impacto_01", "morte_01", "dano_01"] {
        assert!(nomes.contains(&base), "faltou {base}");
    }
    assert!(nomes.iter().filter(|n| n.starts_with("passo_grama")).count() >= 3, "variações de passo");
}

#[test]
fn musica_tem_o_tamanho_exato_do_loop() {
    let m = musica::compor("exploracao", 8, 1).unwrap();
    let esperado = (8.0 * 4.0 * 60.0 / m.bpm as f64 * TAXA as f64).round() as usize;
    assert_eq!(m.amostras.len(), esperado);
    assert_eq!(m.compassos, 8);
}

#[test]
fn musica_emenda_sem_estalo() {
    for situacao in musica::SITUACOES {
        let m = musica::compor(situacao, 4, 2).unwrap();
        let a = &m.amostras;
        let janela = (TAXA as usize) / 50; // 20 ms
        let fim = rms(&a[a.len() - janela..]);
        let comeco = rms(&a[..janela]);
        assert!(fim > 0.005 && comeco > 0.005, "{situacao}: tem som nas pontas");
        assert!((fim / comeco) < 4.0 && (comeco / fim) < 4.0, "{situacao}: volume parecido nas pontas ({fim} x {comeco})");
        assert!((a[a.len() - 1] - a[0]).abs() < 0.25, "{situacao}: sem degrau na emenda");
        let pico = a.iter().fold(0.0f32, |p, x| p.max(x.abs()));
        assert!(pico <= 1.0 && pico > 0.3, "{situacao}: pico {pico}");
    }
}

#[test]
fn combate_e_mais_rapido_que_exploracao_e_masmorra_e_a_mais_lenta() {
    let c = musica::compor("combate", 2, 1).unwrap();
    let e = musica::compor("exploracao", 2, 1).unwrap();
    let m = musica::compor("masmorra", 2, 1).unwrap();
    assert!(c.bpm > e.bpm && e.bpm > m.bpm);
}

#[test]
fn situacao_desconhecida_usa_a_mais_parecida_ou_explica() {
    assert_eq!(musica::compor("chefe_final", 2, 1).unwrap().situacao, "chefe");
    assert_eq!(musica::compor("Vila", 2, 1).unwrap().situacao, "vila");
    assert_eq!(musica::compor("espaco_sideral", 2, 1).unwrap_err().codigo, "situacao_desconhecida");
}

#[test]
fn wav_com_cabecalho_de_stream_e_reescrito_certo() {
    // A voz do Ignis vem com os tamanhos do cabeçalho errados (WAV de stream) e a Godot trava ao importar.
    let mut ruim = audio::wav_mono_16(&[0.1f32; 1000]);
    ruim[4..8].copy_from_slice(&7u32.to_le_bytes()); // RIFF errado
    ruim[40..44].copy_from_slice(&0xFFFF_FFFFu32.to_le_bytes()); // data "infinito"
    ruim[24..28].copy_from_slice(&24_000u32.to_le_bytes());
    let bom = audio::normalizar_wav(&ruim).expect("dá para consertar");
    assert_eq!(u32::from_le_bytes(bom[4..8].try_into().unwrap()) as usize, bom.len() - 8);
    assert_eq!(u32::from_le_bytes(bom[40..44].try_into().unwrap()) as usize, bom.len() - 44);
    assert_eq!(u32::from_le_bytes(bom[24..28].try_into().unwrap()), 24_000, "mantém a taxa da voz");
    assert_eq!((bom.len() - 44) / 2, 1000);
}
