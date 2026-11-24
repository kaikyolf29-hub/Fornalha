//! A Forja: os scripts do Blender que a Fornalha leva dentro dela e roda por
//! linha de comando (`blender -b`). Gera personagens com esqueleto e animações,
//! armas, objetos e o mundo em blockout; limpa e põe esqueleto em malhas de fora
//! (TRELLIS.2, Hunyuan3D ou feitas à mão); copia animações entre personagens.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::Value;

use crate::erro::{Erro, Resultado};
use crate::externas::{self, Achado};

const SCRIPTS: [(&str, &str); 24] = [
    ("fornalha_main.py", include_str!("../blender/fornalha_main.py")),
    ("fc_comum.py", include_str!("../blender/fc_comum.py")),
    ("fc_personagem.py", include_str!("../blender/fc_personagem.py")),
    ("fc_animacoes.py", include_str!("../blender/fc_animacoes.py")),
    ("fc_armas.py", include_str!("../blender/fc_armas.py")),
    ("fc_mundo.py", include_str!("../blender/fc_mundo.py")),
    ("fc_placa.py", include_str!("../blender/fc_placa.py")),
    ("fc_humano.py", include_str!("../blender/fc_humano.py")),
    ("fc_roupa.py", include_str!("../blender/fc_roupa.py")),
    ("fc_pbr.py", include_str!("../blender/fc_pbr.py")),
    ("fc_retarget.py", include_str!("../blender/fc_retarget.py")),
    ("fc_armas_pbr.py", include_str!("../blender/fc_armas_pbr.py")),
    ("fc_armadura.py", include_str!("../blender/fc_armadura.py")),
    ("fc_pele.py", include_str!("../blender/fc_pele.py")),
    ("fc_cabelo.py", include_str!("../blender/fc_cabelo.py")),
    ("fc_lookdev.py", include_str!("../blender/fc_lookdev.py")),
    ("fc_pano.py", include_str!("../blender/fc_pano.py")),
    ("fc_criatura.py", include_str!("../blender/fc_criatura.py")),
    ("fc_rig_ia.py", include_str!("../blender/fc_rig_ia.py")),
    ("fc_rig_criatura.py", include_str!("../blender/fc_rig_criatura.py")),
    ("fc_partes.py", include_str!("../blender/fc_partes.py")),
    ("fc_molde.py", include_str!("../blender/fc_molde.py")),
    ("fc_rig_generico.py", include_str!("../blender/fc_rig_generico.py")),
    ("fc_eixo.py", include_str!("../blender/fc_eixo.py")),
];

/// Tipos que a Forja sabe fazer.
pub const TIPOS_DE_PERSONAGEM: [&str; 9] = ["humano", "elfo", "anao", "orc", "goblin", "esqueleto", "zumbi", "demonio", "dragao"];
pub const ARMAS: [&str; 7] = ["espada", "machado", "lanca", "martelo", "adaga", "cajado", "escudo"];
pub const OBJETOS: [&str; 9] = ["barril", "caixa", "bau", "arvore", "pedra", "casa", "tocha", "cerca", "pocao"];
pub const ANIMACOES: [&str; 9] = ["parado", "andar", "correr", "pular", "atacar", "defender", "esquivar", "dano", "morrer"];
pub const AREAS: [&str; 15] = [
    "vila", "cidade", "aldeia", "floresta", "bosque", "pantano", "montanha", "colina", "vulcao", "masmorra", "caverna", "castelo",
    "ruinas", "arena", "coliseu",
];

/// Versão dos scripts (muda a pasta quando o conteúdo muda).
fn assinatura() -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    for (nome, texto) in SCRIPTS {
        h.update(nome.as_bytes());
        h.update(texto.as_bytes());
    }
    hex::encode(&h.finalize()[..6])
}

/// Escreve os scripts numa pasta da Fornalha e devolve o caminho do principal.
pub fn preparar_scripts(pasta_dados: &Path) -> Resultado<PathBuf> {
    let pasta = pasta_dados.join("blender").join(assinatura());
    let principal = pasta.join("fornalha_main.py");
    if principal.is_file() {
        return Ok(principal);
    }
    std::fs::create_dir_all(&pasta).map_err(|e| Erro::io(&pasta, e))?;
    for (nome, texto) in SCRIPTS {
        let arq = pasta.join(nome);
        std::fs::write(&arq, texto).map_err(|e| Erro::io(&arq, e))?;
    }
    Ok(principal)
}

/// Roda uma tarefa da Forja no Blender e devolve o resultado (JSON do script).
pub async fn rodar(blender: &Achado, pasta_dados: &Path, tarefa: &Value, tempo: Duration) -> Resultado<Value> {
    let principal = preparar_scripts(pasta_dados)?;
    let tmp = pasta_dados.join("tmp");
    std::fs::create_dir_all(&tmp).map_err(|e| Erro::io(&tmp, e))?;
    let id = crate::util::id_aleatorio(6);
    let arq_tarefa = tmp.join(format!("tarefa_{id}.json"));
    let arq_resultado = tmp.join(format!("resultado_{id}.json"));
    std::fs::write(&arq_tarefa, serde_json::to_vec_pretty(tarefa).unwrap_or_default()).map_err(|e| Erro::io(&arq_tarefa, e))?;
    let principal_s = principal.to_string_lossy().into_owned();
    let t_s = arq_tarefa.to_string_lossy().into_owned();
    let r_s = arq_resultado.to_string_lossy().into_owned();
    let saida = externas::rodar(
        &blender.caminho,
        &["-b", "--factory-startup", "--python-exit-code", "1", "-P", &principal_s, "--", &t_s, &r_s],
        tempo,
        None,
    )
    .await?;
    let _ = std::fs::remove_file(&arq_tarefa);
    let resultado: Option<Value> = std::fs::read(&arq_resultado).ok().and_then(|b| serde_json::from_slice(&b).ok());
    let _ = std::fs::remove_file(&arq_resultado);
    if saida.tempo_esgotado {
        return Err(Erro::novo("blender_demorou", format!("O Blender passou do tempo-limite ({} s).", tempo.as_secs())));
    }
    match resultado {
        Some(r) if r["ok"] == Value::Bool(true) => Ok(r),
        Some(r) => {
            Err(Erro::novo("blender_falhou", format!("O Blender não conseguiu: {}", r["erro"].as_str().unwrap_or("erro desconhecido"))))
        }
        None => Err(Erro::novo("blender_falhou", format!("O Blender parou sem resultado. Final da saída:\n{}", saida.final_da_saida(12)))),
    }
}
