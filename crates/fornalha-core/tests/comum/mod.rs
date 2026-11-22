//! Ajudantes compartilhados pelos testes.
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::path::PathBuf;

use fornalha_core::distro::{Familia, Sistema};
use fornalha_core::gpu::{merge, Detection, RawSources};

pub fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

/// Monta as fontes brutas a partir de uma pasta de fixtures.
pub fn fixture(name: &str) -> RawSources {
    let d = fixtures_dir().join(name);
    let read = |f: &str| std::fs::read_to_string(d.join(f)).ok();
    fn json<T: serde::de::DeserializeOwned + Default>(d: &std::path::Path, f: &str) -> T {
        std::fs::read_to_string(d.join(f)).map(|s| serde_json::from_str(&s).expect(f)).unwrap_or_default()
    }
    RawSources {
        sysfs: json(&d, "sysfs.json"),
        kfd: json(&d, "kfd.json"),
        dxgi: json(&d, "dxgi.json"),
        vulkaninfo: read("vulkaninfo.txt"),
        rocminfo: read("rocminfo.txt"),
        nvidia_smi: read("nvidia-smi.csv"),
        kernel: read("kernel.txt").map(|s| s.trim().to_string()),
        nvidia_modulo: None,
    }
}

pub fn sistema(familia: Familia) -> Sistema {
    Sistema { familia, nome: format!("{familia:?}"), versao: None, flatpak: false, appimage: false }
}

/// Detecção completa a partir de fixtures (sistema Fedora, libs à escolha).
pub fn detection(name: &str) -> Detection {
    detection_with(name, Familia::Fedora, &[])
}

pub fn detection_with(name: &str, familia: Familia, libs: &[(&str, bool)]) -> Detection {
    let raw = fixture(name);
    let windows = name.ends_with("-windows");
    Detection {
        sistema: sistema(if windows { Familia::Windows } else { familia }),
        arq: "x86_64".into(),
        placas: merge(&raw),
        ram_total_mb: 32000,
        ram_livre_mb: 24000,
        libs: libs.iter().map(|(k, v)| (k.to_string(), *v)).collect::<BTreeMap<_, _>>(),
        kfd_acessivel: true,
        ferramentas: vec![],
        fontes_brutas: raw,
    }
}

/// Movimento (etapa 1.6): AnimationTree, IK dos pés (TwoBoneIK3D), olhar (LookAtModifier3D),
/// golpe andando e os pés a menos de 3 cm do chão com o personagem parado.
pub fn conferir_movimento(rel: &serde_json::Value) {
    let mov = &rel["movimento"];
    eprintln!("movimento: {mov}");
    for chave in ["arvore", "ik_pes", "olhar", "atacou_andando"] {
        assert_eq!(mov[chave], true, "movimento sem {chave}: {mov}");
    }
    let pes = &mov["pes_parado_cm"];
    assert!(pes["amostras"].as_u64().unwrap_or(0) >= 5, "poucos quadros parados para medir os pés: {mov}");
    assert!(pes["max"].as_f64().unwrap() < 3.0, "os pés têm de ficar a menos de 3 cm do chão parado: {mov}");
    let ciclos = &mov["velocidade_dos_ciclos"];
    assert!(ciclos["andar"].as_f64().unwrap_or(0.0) > 0.3, "velocidade do ciclo de andar medida nos pés: {mov}");
}
