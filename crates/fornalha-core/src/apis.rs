//! APIs pagas de geração (opcionais): desligadas por padrão; a pessoa liga e põe a chave na janela,
//! vendo antes o preço e a licença. A chave fica só neste computador (arquivo próprio na pasta de
//! dados, fora dos projetos) e vai para o script à parte pela variável de ambiente, nunca pela linha de
//! comando. O núcleo continua sem HTTPS: quem fala com o serviço é o script (`api_3d.py`).

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::paths::Paths;

/// Um serviço de 3D por API.
#[derive(Debug, Clone, Serialize)]
pub struct Provedor {
    pub id: &'static str,
    pub nome: &'static str,
    /// id do modelo no manifesto (para o recibo de licença)
    pub modelo: &'static str,
    pub preco: &'static str,
    pub licenca: &'static str,
    pub url_licenca: &'static str,
    pub url_chave: &'static str,
    pub pronto: bool,
}

pub const PROVEDORES_3D: [Provedor; 3] = [
    Provedor {
        id: "meshy",
        nome: "Meshy (imagem → 3D)",
        modelo: "meshy-pago",
        preco: "30 créditos por modelo com textura 2K (Meshy 7.1; tabela de preços da API da Meshy em 23/11/2026). A API exige plano pago.",
        licenca: "Termos da Meshy (plano pago): uso comercial do modelo gerado. Confira os termos antes de ligar.",
        url_licenca: "https://www.meshy.ai/",
        url_chave: "https://www.meshy.ai/settings/api",
        pronto: true,
    },
    Provedor {
        id: "tripo",
        nome: "Tripo (imagem → 3D)",
        modelo: "tripo-pago",
        preco: "30 créditos (US$ 0,30) por modelo com textura padrão (v3.1; tabela da API da Tripo em 23/11/2026). Créditos de tarefa que falhar voltam.",
        licenca: "Termos da Tripo: no plano pago os direitos sobre o modelo são seus (uso comercial); no grátis a Tripo fica com os direitos. Use só com plano pago.",
        url_licenca: "https://developers.tripo3d.ai/en/terms",
        url_chave: "https://developers.tripo3d.ai/en/keys",
        pronto: true,
    },
    Provedor {
        id: "rodin",
        nome: "Rodin / Hyper3D (imagem → 3D)",
        modelo: "rodin-pago",
        preco: "0,5 crédito por geração Gen-2.5 (mais 0,5 no nível mais alto; tabela da Hyper3D em 23/11/2026). Planos a partir de US$ 24/mês.",
        licenca: "Termos da Hyper3D: no plano pago a exportação e o uso são livres; no grátis não. Use só com plano pago.",
        url_licenca: "https://hyper3d.ai/legal/terms",
        url_chave: "https://hyper3d.ai/workspace/api-dashboard",
        pronto: true,
    },
];

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub(crate) struct Guardado {
    pub(crate) ligadas: Vec<String>,
    pub(crate) chaves: BTreeMap<String, String>,
    /// Modelo escolhido por API (o cérebro por API: Claude, Gemini).
    pub(crate) modelos: BTreeMap<String, String>,
    /// Lista de modelos que a própria API devolveu (botão "Atualizar lista").
    pub(crate) listas: BTreeMap<String, Vec<String>>,
}

fn arquivo(paths: &Paths) -> PathBuf {
    paths.data_dir.join("chaves_api.json")
}

pub(crate) fn ler(paths: &Paths) -> Guardado {
    std::fs::read_to_string(arquivo(paths)).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default()
}

pub(crate) fn gravar(paths: &Paths, g: &Guardado) -> Resultado<()> {
    let arq = arquivo(paths);
    if let Some(d) = arq.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    std::fs::write(&arq, serde_json::to_vec_pretty(g).unwrap_or_default()).map_err(|e| Erro::io(&arq, e))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&arq, std::fs::Permissions::from_mode(0o600));
    }
    Ok(())
}

pub fn provedor(id: &str) -> Option<&'static Provedor> {
    PROVEDORES_3D.iter().find(|p| p.id == id)
}

/// Situação de cada API (nunca mostra a chave).
pub fn estado(paths: &Paths) -> Value {
    let g = ler(paths);
    json!(PROVEDORES_3D
        .iter()
        .map(|p| json!({"id": p.id, "nome": p.nome, "preco": p.preco, "licenca": p.licenca, "url_licenca": p.url_licenca,
                        "url_chave": p.url_chave, "ligada": g.ligadas.iter().any(|x| x == p.id),
                        "tem_chave": g.chaves.get(p.id).is_some_and(|c| !c.is_empty()), "pronto": p.pronto}))
        .collect::<Vec<_>>())
}

/// Liga/desliga e guarda (ou apaga, com texto vazio) a chave. Só pela janela, pela pessoa.
pub fn definir(paths: &Paths, id: &str, ligada: Option<bool>, chave: Option<String>) -> Resultado<Value> {
    let p = provedor(id).ok_or_else(|| Erro::argumento(format!("API desconhecida: {id}")))?;
    let mut g = ler(paths);
    if let Some(c) = chave {
        let c = c.trim().to_string();
        if c.is_empty() {
            g.chaves.remove(p.id);
        } else {
            g.chaves.insert(p.id.to_string(), c);
        }
    }
    if let Some(l) = ligada {
        g.ligadas.retain(|x| x != p.id);
        if l {
            if !g.chaves.contains_key(p.id) {
                return Err(Erro::novo("api_sem_chave", format!("Ponha a chave da {} antes de ligar.", p.nome)));
            }
            g.ligadas.push(p.id.to_string());
        }
    }
    gravar(paths, &g)?;
    Ok(estado(paths))
}

/// A API de 3D ligada e com chave (a primeira), se houver.
pub fn ligada_3d(paths: &Paths) -> Option<&'static Provedor> {
    let g = ler(paths);
    PROVEDORES_3D.iter().find(|p| p.pronto && g.ligadas.iter().any(|x| x == p.id) && g.chaves.get(p.id).is_some_and(|c| !c.is_empty()))
}

/// Imagem → .glb pela API. Devolve o resumo (créditos gastos, tempo).
pub async fn gerar_3d(paths: &Paths, p: &Provedor, imagem: &Path, saida: &Path, opcoes: &Value) -> Resultado<Value> {
    let chave = ler(paths)
        .chaves
        .get(p.id)
        .cloned()
        .filter(|c| !c.is_empty())
        .ok_or_else(|| Erro::novo("api_sem_chave", format!("Sem chave da {} (Máquina → APIs).", p.nome)))?;
    let python = crate::workers::python_para(paths).await.ok_or_else(|| {
        Erro::novo("python_ausente", "Para usar a API precisa do Python 3.10+ ou do Blender baixado em Máquina → Programas.")
    })?;
    let scripts = crate::workers::preparar_scripts(&paths.data_dir)?;
    let tmp = paths.data_dir.join("tmp");
    std::fs::create_dir_all(&tmp).map_err(|e| Erro::io(&tmp, e))?;
    let id = crate::util::id_aleatorio(6);
    let arq_opcoes = tmp.join(format!("api_{id}.opcoes.json"));
    let arq_resultado = tmp.join(format!("api_{id}.resultado.json"));
    std::fs::write(&arq_opcoes, serde_json::to_vec(opcoes).unwrap_or_default()).map_err(|e| Erro::io(&arq_opcoes, e))?;
    let script = scripts.join("api_3d.py");
    let args: Vec<String> = vec![
        script.to_string_lossy().into_owned(),
        p.id.to_string(),
        imagem.to_string_lossy().into_owned(),
        saida.to_string_lossy().into_owned(),
        arq_resultado.to_string_lossy().into_owned(),
        arq_opcoes.to_string_lossy().into_owned(),
    ];
    let refs: Vec<&str> = args.iter().map(String::as_str).collect();
    let s =
        crate::externas::rodar_com_env(&python, &refs, Duration::from_secs(45 * 60), Some(&tmp), &[("FORNALHA_CHAVE_API", chave.as_str())])
            .await?;
    let r: Value = std::fs::read(&arq_resultado).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(Value::Null);
    let _ = std::fs::remove_file(&arq_opcoes);
    let _ = std::fs::remove_file(&arq_resultado);
    if r["ok"] != true || !saida.is_file() {
        let msg = r["erro"].as_str().map(String::from).unwrap_or_else(|| s.final_da_saida(5));
        return Err(Erro::novo("api_falhou", format!("A {} não gerou o 3D: {msg}", p.nome)));
    }
    Ok(r)
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn liga_so_com_chave_e_nao_mostra_a_chave() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = Paths::under(tmp.path());
        assert!(ligada_3d(&paths).is_none());
        assert_eq!(definir(&paths, "meshy", Some(true), None).unwrap_err().codigo, "api_sem_chave");
        let e = definir(&paths, "meshy", Some(true), Some("segredo-123".into())).unwrap();
        assert_eq!(e[0]["ligada"], true);
        assert_eq!(e[0]["tem_chave"], true);
        assert!(!e.to_string().contains("segredo-123"), "a chave nunca aparece no estado");
        assert_eq!(ligada_3d(&paths).unwrap().id, "meshy");
        definir(&paths, "meshy", Some(false), None).unwrap();
        assert!(ligada_3d(&paths).is_none(), "desligada não gera");
    }
}
