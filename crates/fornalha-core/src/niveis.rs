//! Os 4 níveis de qualidade: Leve, Equilibrado, Qualidade e Máximo.

use serde::{Deserialize, Serialize};

use crate::gpu::{Detection, Vendor};
use crate::licencas::{escolher, Catalogo, ContextoRota, Escolha};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Nivel {
    Leve,
    Equilibrado,
    Qualidade,
    Maximo,
}

impl Nivel {
    pub const TODOS: [Nivel; 4] = [Nivel::Leve, Nivel::Equilibrado, Nivel::Qualidade, Nivel::Maximo];

    pub fn id(&self) -> &'static str {
        match self {
            Nivel::Leve => "leve",
            Nivel::Equilibrado => "equilibrado",
            Nivel::Qualidade => "qualidade",
            Nivel::Maximo => "maximo",
        }
    }

    pub fn from_id(id: &str) -> Option<Self> {
        Self::TODOS.into_iter().find(|n| n.id() == id.trim().to_lowercase().replace('á', "a"))
    }
}

impl Nivel {
    /// Nome mostrado para a pessoa.
    pub fn nome(&self) -> &'static str {
        match self {
            Nivel::Leve => "Leve",
            Nivel::Equilibrado => "Equilibrado",
            Nivel::Qualidade => "Qualidade",
            Nivel::Maximo => "Máximo",
        }
    }

    /// Memória de vídeo de referência do nível.
    pub fn faixa(&self) -> &'static str {
        match self {
            Nivel::Leve => "até 8 GB",
            Nivel::Equilibrado => "12 GB",
            Nivel::Qualidade => "16 GB",
            Nivel::Maximo => "24 GB ou mais",
        }
    }

    pub fn placas_exemplo(&self) -> &'static str {
        match self {
            Nivel::Leve => "RX 580, RTX 3060 8 GB, RTX 4060",
            Nivel::Equilibrado => "RTX 3060 12 GB, RX 7700 XT",
            Nivel::Qualidade => "RTX 4060 Ti 16 GB, RTX 5060 Ti 16 GB, RX 9060 XT 16 GB",
            Nivel::Maximo => "RTX 3090, 4090, 5090",
        }
    }
}

/// Aceleradores que a máquina tem (o que decide quais modelos rodam na placa).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Aceleradores {
    pub cuda: bool,
    pub rocm: bool,
    pub vulkan: bool,
}

/// Alvos gfx da AMD com ROCm oficial (os outros usam Vulkan).
const GFX_COM_ROCM: [&str; 11] =
    ["gfx90a", "gfx942", "gfx950", "gfx1030", "gfx1100", "gfx1101", "gfx1102", "gfx1150", "gfx1151", "gfx1200", "gfx1201"];

pub fn aceleradores(det: &Detection) -> Aceleradores {
    let dedicadas = || det.placas.iter().filter(|g| !g.integrada);
    let cuda = dedicadas().any(|g| g.fabricante == Vendor::Nvidia);
    let rocm = dedicadas().any(|g| g.fabricante == Vendor::Amd && g.alvo_gfx.as_deref().is_some_and(|x| GFX_COM_ROCM.contains(&x)));
    let vulkan = det.placas.iter().any(|g| g.fabricante != Vendor::Outro) || det.ferramentas.iter().any(|f| f == "vulkaninfo");
    Aceleradores { cuda, rocm, vulkan }
}

/// Nível pela memória da placa. As placas de 16 GB aparecem com um pouco menos
/// (16 076 MB no DXGI), por isso os limites ficam abaixo dos números redondos.
pub fn nivel_por_vram(vram_mb: Option<u64>) -> Nivel {
    match vram_mb.unwrap_or(0) {
        v if v >= 22_000 => Nivel::Maximo,
        v if v >= 15_000 => Nivel::Qualidade,
        v if v >= 11_000 => Nivel::Equilibrado,
        _ => Nivel::Leve,
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Sugestao {
    pub nivel: Nivel,
    pub motivo: String,
    /// Placa principal (resumo), se houver placa dedicada.
    pub placa: Option<String>,
    pub vram_mb: Option<u64>,
    pub aceleradores: Aceleradores,
    pub avisos: Vec<String>,
}

/// Sugere o nível pela placa principal.
pub fn sugerir(det: &Detection) -> Sugestao {
    let acel = aceleradores(det);
    let principal = det.principal().filter(|g| !g.integrada);
    let mut avisos = Vec::new();
    let Some(g) = principal else {
        avisos.push("Sem placa de vídeo dedicada: tudo roda no processador, bem devagar. A fila da noite e o modo turbo ajudam.".into());
        return Sugestao {
            nivel: Nivel::Leve,
            motivo: "Nenhuma placa dedicada encontrada.".into(),
            placa: None,
            vram_mb: None,
            aceleradores: acel,
            avisos,
        };
    };
    let nivel = nivel_por_vram(g.vram_total_mb);
    if !acel.cuda {
        avisos.push(
            "Sem CUDA (placa não NVIDIA): TRELLIS.2, UniRig e Audio2Face usam a opção do nível que não depende de CUDA até o porte para AMD ficar pronto."
                .into(),
        );
    }
    if g.fabricante == Vendor::Amd && !acel.rocm {
        avisos.push("Placa AMD sem ROCm: cérebro e transcrição pelo Vulkan no Ignis; 3D em fila lenta.".into());
    }
    if det.ram_total_mb > 0 && det.ram_total_mb < 24_000 {
        avisos.push("Menos de 32 GB de RAM: o modo pouca VRAM fica mais lento.".into());
    }
    let vram = g.vram_total_mb;
    Sugestao {
        nivel,
        motivo: format!("{} com {} MB de memória de vídeo: nível {} ({}).", g.nome, vram.unwrap_or(0), nivel.nome(), nivel.faixa()),
        placa: Some(g.nome.clone()),
        vram_mb: vram,
        aceleradores: acel,
        avisos,
    }
}

/// Uma linha da tabela de níveis: o modelo escolhido para cada função.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct LinhaNivel {
    pub nivel: Nivel,
    pub nome: String,
    pub faixa: String,
    pub placas_exemplo: String,
    pub funcoes: Vec<Escolha>,
}

/// A tabela dos 4 níveis para este projeto e esta máquina.
pub fn tabela(cat: &Catalogo, ctx: &ContextoRota) -> Vec<LinhaNivel> {
    Nivel::TODOS
        .into_iter()
        .map(|n| LinhaNivel {
            nivel: n,
            nome: n.nome().into(),
            faixa: n.faixa().into(),
            placas_exemplo: n.placas_exemplo().into(),
            funcoes: cat.funcoes.iter().filter_map(|f| escolher(cat, &f.id, n, ctx).ok()).collect(),
        })
        .collect()
}
