//! Sugestão do nível de qualidade pela placa (fixtures das placas de referência).

mod comum;

use fornalha_core::distro::Familia;
use fornalha_core::licencas::{Catalogo, ContextoRota};
use fornalha_core::niveis::{self, Nivel};

#[test]
fn ids_dos_niveis() {
    assert_eq!(Nivel::TODOS.map(|n| n.id()), ["leve", "equilibrado", "qualidade", "maximo"]);
    assert_eq!(Nivel::from_id("Máximo"), Some(Nivel::Maximo));
    assert_eq!(Nivel::from_id("QUALIDADE"), Some(Nivel::Qualidade));
    assert_eq!(Nivel::from_id("ultra"), None);
}

#[test]
fn rx580_8gb_fica_no_leve_sem_cuda_nem_rocm() {
    let s = niveis::sugerir(&comum::detection("rx580"));
    assert_eq!(s.nivel, Nivel::Leve);
    assert!(!s.aceleradores.cuda);
    assert!(!s.aceleradores.rocm, "gfx803 saiu do ROCm");
    assert!(s.aceleradores.vulkan);
    assert_eq!(s.vram_mb, Some(8192));
    assert!(s.placa.as_deref().unwrap().contains("RX 580"));
}

#[test]
fn rtx3060_12gb_fica_no_equilibrado() {
    let s = niveis::sugerir(&comum::detection("rtx3060"));
    assert_eq!(s.nivel, Nivel::Equilibrado);
    assert!(s.aceleradores.cuda);
}

#[test]
fn rtx4060ti_16gb_no_windows_fica_no_qualidade() {
    let d = comum::detection_with("rtx4060ti16-windows", Familia::Windows, &[]);
    let s = niveis::sugerir(&d);
    assert_eq!(s.nivel, Nivel::Qualidade);
    assert!(s.aceleradores.cuda);
    assert_eq!(s.vram_mb, Some(16380), "nvidia-smi manda na VRAM");
}

#[test]
fn rx9060xt_16gb_fica_no_qualidade_com_rocm_e_avisa_do_3d() {
    let s = niveis::sugerir(&comum::detection("rx9060xt"));
    assert_eq!(s.nivel, Nivel::Qualidade, "a integrada não conta");
    assert!(s.aceleradores.rocm);
    assert!(!s.aceleradores.cuda);
    assert!(s.avisos.iter().any(|a| a.contains("CUDA")), "{:?}", s.avisos);
}

#[test]
fn sem_placa_fica_no_leve_e_avisa() {
    let s = niveis::sugerir(&comum::detection("sem-placa"));
    assert_eq!(s.nivel, Nivel::Leve);
    assert!(s.placa.is_none());
    assert!(s.avisos.iter().any(|a| a.contains("processador")), "{:?}", s.avisos);
}

#[test]
fn limites_de_vram() {
    assert_eq!(niveis::nivel_por_vram(Some(4096)), Nivel::Leve);
    assert_eq!(niveis::nivel_por_vram(Some(8192)), Nivel::Leve);
    assert_eq!(niveis::nivel_por_vram(Some(12_288)), Nivel::Equilibrado);
    assert_eq!(niveis::nivel_por_vram(Some(16_076)), Nivel::Qualidade, "16 GB visto pelo DXGI");
    assert_eq!(niveis::nivel_por_vram(Some(24_564)), Nivel::Maximo);
    assert_eq!(niveis::nivel_por_vram(Some(32_768)), Nivel::Maximo);
    assert_eq!(niveis::nivel_por_vram(None), Nivel::Leve);
}

#[test]
fn tabela_tem_os_4_niveis_e_todas_as_funcoes() {
    let cat = Catalogo::embutido();
    let ctx = ContextoRota { comercial: true, cuda: true, receita_anual_usd: None, licencas_aceitas: vec![] };
    let t = niveis::tabela(&cat, &ctx);
    assert_eq!(t.len(), 4);
    for linha in &t {
        assert_eq!(linha.funcoes.len(), cat.funcoes.len(), "{:?}", linha.nivel);
    }
    let qualidade = t.iter().find(|l| l.nivel == Nivel::Qualidade).unwrap();
    let cerebro = qualidade.funcoes.iter().find(|e| e.funcao == "cerebro").unwrap();
    assert_eq!(cerebro.modelo.as_ref().unwrap().id, "qwen3-14b");
}
