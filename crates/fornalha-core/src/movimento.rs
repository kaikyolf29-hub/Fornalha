//! Bancada de movimento: o banco de capturas (Quaternius, ACCAD, 100STYLE, Mixamo e CMU trazidos pela
//! pessoa), a aplicação no personagem (retarget por pose, recorte, ciclo, no lugar) e a conferência que
//! mede e reprova o que fica feio no jogo (braço virado, junta ao contrário, membro atravessando o corpo,
//! pé escorregando, corpo no chão), com correção automática e imagem para a IA ver.
//!
//! O trabalho pesado é do Blender (`fc_banco.py`, `fc_conferir.py`, `fc_corrigir.py`); aqui ficam as
//! fontes, as licenças, o catálogo guardado e os recibos.

use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::geracao::{forjar, recibo, rel};
use crate::licencas::Situacao;
use crate::pacotes::{self, Pacote};
use crate::projeto::Projeto;
use crate::servico::Fornalha;

/// Extensões de captura que o banco lê.
const EXTENSOES: [&str; 4] = ["bvh", "fbx", "glb", "gltf"];

/// Uma fonte de capturas: de onde vem, licença e o modelo do catálogo que vai no recibo.
#[derive(Debug, Clone)]
pub struct Fonte {
    pub id: String,
    pub nome: String,
    pub licenca: String,
    pub credito: Option<String>,
    /// id no catálogo de modelos (recibo), ou `autoral`.
    pub modelo: String,
    pub arquivos: Vec<PathBuf>,
    /// onde o catálogo desta fonte fica guardado
    pub cache: PathBuf,
}

fn arquivos_em(pasta: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut pilha = vec![pasta.to_path_buf()];
    while let Some(d) = pilha.pop() {
        let Ok(it) = std::fs::read_dir(&d) else { continue };
        for e in it.flatten() {
            let p = e.path();
            if p.is_dir() {
                pilha.push(p);
            } else if p.extension().and_then(|x| x.to_str()).is_some_and(|x| EXTENSOES.contains(&x.to_lowercase().as_str())) {
                out.push(p);
            }
        }
    }
    out.sort();
    out
}

/// Fonte que a pessoa trouxe para o projeto (`Motion/<fonte>/`), pelo id.
fn fonte_importada(id: &str) -> (&'static str, &'static str, Option<&'static str>, &'static str) {
    match id {
        "mixamo" => ("Mixamo (Adobe), trazido pela pessoa", "Termos da Adobe (Mixamo)", None, "captura-mixamo"),
        "cmu" => (
            "CMU Graphics Lab Motion Capture",
            "Uso livre da CMU",
            Some("Carnegie Mellon University Motion Capture Database"),
            "captura-cmu",
        ),
        "accad" => (
            "ACCAD (trazido pela pessoa)",
            "CC BY 3.0",
            Some("Open Motion Project by ACCAD/The Ohio State University (CC BY 3.0)"),
            "captura-accad",
        ),
        "100style" => {
            ("100STYLE (trazido pela pessoa)", "CC BY 4.0", Some("The 100STYLE Dataset - Ian Mason (CC BY 4.0)"), "captura-100style")
        }
        _ => ("Captura própria do estúdio", "do próprio estúdio", None, crate::recibos::MODELO_AUTORAL),
    }
}

/// As fontes disponíveis agora (pacotes instalados e o que a pessoa trouxe para o projeto).
pub fn fontes(f: &Fornalha, p: Option<&Projeto>) -> Vec<Fonte> {
    let cache = f.paths.data_dir.join("movimento");
    let mut out = Vec::new();
    if let Some(a) = pacotes::info(&f.paths, Pacote::Animacoes) {
        let arquivos: Vec<PathBuf> =
            a["bibliotecas"].as_object().map(|m| m.values().filter_map(|v| v.as_str()).map(PathBuf::from).collect()).unwrap_or_default();
        out.push(Fonte {
            id: "quaternius".into(),
            nome: "Quaternius Universal Animation Library 1 e 2".into(),
            licenca: "CC0".into(),
            credito: None,
            modelo: "biblioteca-quaternius".into(),
            arquivos,
            cache: cache.join("quaternius.json"),
        });
    }
    for (pac, id, nome, licenca, credito, modelo) in [
        (
            Pacote::Accad,
            "accad",
            "ACCAD Open Motion Project (luta, passos, carregar)",
            "CC BY 3.0",
            "Open Motion Project by ACCAD/The Ohio State University (CC BY 3.0)",
            "captura-accad",
        ),
        (
            Pacote::Estilos100,
            "100style",
            "100STYLE (100 estilos de andar e correr)",
            "CC BY 4.0",
            "The 100STYLE Dataset - Ian Mason (CC BY 4.0)",
            "captura-100style",
        ),
    ] {
        if pacotes::info(&f.paths, pac).is_some() {
            out.push(Fonte {
                id: id.into(),
                nome: nome.into(),
                licenca: licenca.into(),
                credito: Some(credito.into()),
                modelo: modelo.into(),
                arquivos: arquivos_em(&pacotes::pasta(&f.paths, pac)),
                cache: cache.join(format!("{id}.json")),
            });
        }
    }
    if let Some(p) = p {
        let raiz = p.raiz.join("Motion");
        if let Ok(it) = std::fs::read_dir(&raiz) {
            let mut dirs: Vec<PathBuf> = it.flatten().map(|e| e.path()).filter(|d| d.is_dir()).collect();
            dirs.sort();
            for d in dirs {
                let id = d.file_name().and_then(|n| n.to_str()).unwrap_or("propria").to_string();
                let (nome, licenca, credito, modelo) = fonte_importada(&id);
                out.push(Fonte {
                    id: format!("projeto/{id}"),
                    nome: nome.into(),
                    licenca: licenca.into(),
                    credito: credito.map(String::from),
                    modelo: modelo.into(),
                    arquivos: arquivos_em(&d),
                    cache: d.join("banco.json"),
                });
            }
        }
    }
    out
}

/// Assinatura dos arquivos (muda quando algum entra, sai ou muda).
fn assinatura(arqs: &[PathBuf]) -> String {
    let mut total: u64 = 0;
    let mut tempo: u64 = 0;
    for a in arqs {
        if let Ok(m) = std::fs::metadata(a) {
            total = total.wrapping_add(m.len());
            if let Ok(t) = m.modified() {
                tempo = tempo.max(t.duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0));
            }
        }
    }
    format!("{}-{total}-{tempo}", arqs.len())
}

/// O catálogo de uma fonte (guardado; refeito no Blender quando os arquivos mudam).
async fn catalogo_da_fonte(f: &Fornalha, fonte: &Fonte) -> Resultado<Vec<Value>> {
    let ass = assinatura(&fonte.arquivos);
    if let Ok(b) = std::fs::read(&fonte.cache) {
        if let Ok(v) = serde_json::from_slice::<Value>(&b) {
            if v["assinatura"] == json!(ass) {
                return Ok(v["clipes"].as_array().cloned().unwrap_or_default());
            }
        }
    }
    if fonte.arquivos.is_empty() {
        return Ok(Vec::new());
    }
    let r = forjar(
        f,
        &json!({"tarefa": "banco", "fontes": [{"id": fonte.id, "arquivos": fonte.arquivos}], "materiais": null, "previa": false}),
    )
    .await?;
    let clipes = r["clipes"].as_array().cloned().unwrap_or_default();
    if let Some(d) = fonte.cache.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    let guardado = json!({"assinatura": ass, "clipes": clipes});
    std::fs::write(&fonte.cache, serde_json::to_vec_pretty(&guardado).unwrap_or_default()).map_err(|e| Erro::io(&fonte.cache, e))?;
    Ok(clipes)
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsListar {
    pub projeto: Option<String>,
    /// Texto no nome do clipe ("walk", "jab", "sword").
    pub busca: Option<String>,
    /// Todas estas etiquetas (andar, correr, ataque, espada, soco, chute, defesa, esquiva, morte, dano,
    /// zumbi, agachado, de_costas, de_lado, virar, pular, carregar, gesto, estilo:<nome>…).
    pub etiquetas: Vec<String>,
    pub fonte: Option<String>,
    pub laco: Option<bool>,
    pub limite: Option<usize>,
}

/// list_motions: o banco de movimento, filtrado.
pub async fn listar(f: &Fornalha, a: ArgsListar) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref()).ok();
    let todas = fontes(f, p.as_ref());
    let mut resumo = Vec::new();
    let mut clipes = Vec::new();
    for fonte in &todas {
        if a.fonte.as_deref().is_some_and(|x| !fonte.id.ends_with(x)) {
            continue;
        }
        let lista = catalogo_da_fonte(f, fonte).await?;
        resumo.push(json!({"id": fonte.id, "nome": fonte.nome, "licenca": fonte.licenca, "credito": fonte.credito, "clipes": lista.len()}));
        clipes.extend(lista.into_iter().filter(|c| c.get("erro").is_none()));
    }
    let busca = a.busca.as_deref().map(str::to_lowercase);
    let filtrados: Vec<Value> = clipes
        .into_iter()
        .filter(|c| {
            let nome = c["nome"].as_str().unwrap_or("").to_lowercase();
            let et: Vec<&str> = c["etiquetas"].as_array().map(|v| v.iter().filter_map(|x| x.as_str()).collect()).unwrap_or_default();
            busca.as_ref().is_none_or(|b| nome.contains(b.as_str()))
                && a.etiquetas.iter().all(|e| et.contains(&e.as_str()))
                && a.laco.is_none_or(|l| c["laco"].as_bool() == Some(l))
        })
        .collect();
    let total = filtrados.len();
    let limite = a.limite.unwrap_or(60).clamp(1, 500);
    let mut sem_pacote = Vec::new();
    for (pac, dica) in [
        (Pacote::Animacoes, "animacoes (Quaternius, CC0)"),
        (Pacote::Accad, "accad (luta e passos, CC BY 3.0)"),
        (Pacote::Estilos100, "100style (100 estilos de andar, CC BY 4.0, 1,5 GB)"),
    ] {
        if pacotes::info(&f.paths, pac).is_none() {
            sem_pacote.push(dica);
        }
    }
    Ok(json!({
        "fontes": resumo,
        "total": total,
        "clipes": filtrados.into_iter().take(limite).map(|c| json!({
            "id": c["id"], "nome": c["nome"], "fonte": c["fonte"], "etiquetas": c["etiquetas"], "segundos": c["segundos"],
            "laco": c["laco"], "desloca_no_chao": c["desloca_no_chao"],
        })).collect::<Vec<_>>(),
        "pacotes_que_faltam": sem_pacote,
        "dica": "Use o id em apply_motion. Tomada longa de andar ou correr (ACCAD, 100STYLE): mande ciclo: true para recortar o laço. desloca_no_chao é em alturas do quadril; laço com deslocamento vira \"no lugar\".",
    }))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct Clipe {
    /// id do list_motions (fonte:arquivo:animação), ou um caminho de arquivo BVH/FBX/glb.
    pub id: String,
    /// Nome da animação no jogo (andar, atacar, chute_alto…).
    pub como: String,
    pub laco: Option<bool>,
    pub ciclo: Option<bool>,
    pub no_lugar: Option<bool>,
    pub inicio: Option<u32>,
    pub fim: Option<u32>,
    pub velocidade: Option<f64>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsAplicar {
    pub projeto: Option<String>,
    /// Personagem com esqueleto de jogo (glb).
    pub arquivo: String,
    pub clipes: Vec<Clipe>,
    /// Corrigir sozinho o que a conferência reprovar (padrão: sim).
    pub corrigir: Option<bool>,
    pub video: Option<bool>,
}

/// apply_motion: clipes do banco no personagem, conferidos e corrigidos.
pub async fn aplicar(f: &Fornalha, a: ArgsAplicar, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    if a.clipes.is_empty() {
        return Err(Erro::argumento("Diga os clipes (ids do list_motions) e o nome de cada um no jogo (como)."));
    }
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    if !arquivo.is_file() {
        return Err(Erro::argumento(format!("Não achei o personagem {}.", arquivo.display())));
    }
    let todas = fontes(f, Some(&p));
    let mut pedidos = Vec::new();
    let mut modelos: Vec<(String, Option<String>)> = Vec::new();
    for c in &a.clipes {
        if c.como.trim().is_empty() {
            return Err(Erro::argumento(format!("Falta o nome no jogo (como) do clipe {}.", c.id)));
        }
        let (caminho, acao, modelo, credito) = if let Some((fonte_id, resto)) = c.id.split_once(':') {
            let (arq, acao) = resto.rsplit_once(':').unwrap_or((resto, "*"));
            let fonte = todas.iter().find(|x| x.id == fonte_id).ok_or_else(|| {
                Erro::argumento(format!("A fonte {fonte_id} não está instalada (veja list_motions → pacotes_que_faltam)."))
            })?;
            let caminho = fonte
                .arquivos
                .iter()
                .find(|x| x.file_name().and_then(|n| n.to_str()) == Some(arq))
                .ok_or_else(|| Erro::argumento(format!("Não achei {arq} na fonte {fonte_id}.")))?;
            (caminho.clone(), acao.to_string(), fonte.modelo.clone(), fonte.credito.clone())
        } else {
            let caminho = f.resolver_no_projeto(&p, &c.id);
            if !caminho.is_file() {
                return Err(Erro::argumento(format!("O clipe {} não é um id do banco nem um arquivo.", c.id)));
            }
            (caminho, "*".into(), crate::recibos::MODELO_AUTORAL.to_string(), None)
        };
        // licença antes de mexer no arquivo (Mixamo pede o aceite da pessoa pela janela)
        if modelo != crate::recibos::MODELO_AUTORAL {
            if let Some(m) = f.catalogo.modelo(&modelo) {
                let ctx = f.contexto(Some(&p)).await;
                match crate::licencas::situacao_no_catalogo(&f.catalogo, m, &ctx) {
                    Situacao::Liberado { .. } => {}
                    Situacao::PrecisaAceite { texto, .. } => {
                        return Err(Erro::novo("precisa_aceite", format!("{}: a pessoa precisa aceitar pela janela. {texto}", m.nome)))
                    }
                    Situacao::Bloqueado { motivo } => return Err(Erro::novo("licenca_bloqueada", motivo)),
                    Situacao::PrecisaReceita { .. } => {
                        return Err(Erro::novo("precisa_receita", format!("{}: informe a receita na janela.", m.nome)))
                    }
                }
            }
        }
        if !modelos.iter().any(|(m, _)| *m == modelo) {
            modelos.push((modelo, credito));
        }
        pedidos.push(json!({"arquivo": caminho, "acao": acao, "como": c.como, "laco": c.laco, "ciclo": c.ciclo, "no_lugar": c.no_lugar,
                            "inicio": c.inicio, "fim": c.fim, "velocidade": c.velocidade}));
    }
    let r = forjar(
        f,
        &json!({"tarefa": "aplicar_banco", "entrada": arquivo, "saida": arquivo, "clipes": pedidos,
                "corrigir": a.corrigir.unwrap_or(true), "video": a.video.unwrap_or(false), "materiais": null}),
    )
    .await?;
    for (modelo, credito) in &modelos {
        recibo(
            f,
            &p,
            &arquivo,
            modelo,
            None,
            None,
            json!({"bancada": "movimento", "clipes": a.clipes.iter().map(|c| &c.id).collect::<Vec<_>>(), "credito": credito}),
            quem,
        )
        .await?;
    }
    f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    Ok(resultado(&r, Some(modelos.iter().filter_map(|(_, c)| c.clone()).collect())))
}

fn resultado(r: &Value, creditos: Option<Vec<String>>) -> Value {
    let clipes: Vec<Value> = r["clipes"]
        .as_array()
        .map(|v| {
            v.iter()
                .map(|c| json!({"nome": c["nome"], "aprovado": c["aprovado"], "problemas": c["problemas"], "medidas": c["medidas"]}))
                .collect()
        })
        .unwrap_or_default();
    let mut out = json!({
        "aprovado": r["aprovado"],
        "reprovados": r["reprovados"],
        "animacoes": clipes,
        "correcoes": r["correcoes"],
        "problemas_antes_da_correcao": r["problemas_antes"],
        "arquivos": r["arquivos"],
        "notas": r["notas"],
        "regras": r["regras"],
    });
    if let Some(c) = creditos.filter(|c| !c.is_empty()) {
        out["creditos_obrigatorios"] = json!(c);
    }
    out["dica"] = json!(if r["aprovado"].as_bool() == Some(true) {
        "Tudo aprovado. A imagem mostra cada animação (faixa verde: aprovada)."
    } else {
        "Animação reprovada mesmo depois da correção automática: troque por outro clipe do banco (list_motions) ou recorte o trecho bom (inicio/fim). A imagem mostra o pior quadro com os ossos ruins em vermelho."
    });
    out
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsConferir {
    pub projeto: Option<String>,
    pub arquivo: String,
    pub animacoes: Option<Vec<String>>,
    /// Corrigir sozinho o que reprovar (regrava o glb).
    pub corrigir: bool,
    /// "reprovados" (padrão), "todas" ou "nenhuma".
    pub imagens: Option<String>,
}

/// check_motion: confere (e corrige) as animações de um personagem.
pub async fn conferir(f: &Fornalha, a: ArgsConferir, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    if !arquivo.is_file() {
        return Err(Erro::argumento(format!("Não achei o personagem {}.", arquivo.display())));
    }
    let r = forjar(
        f,
        &json!({"tarefa": "conferir", "entrada": arquivo, "saida": arquivo, "animacoes": a.animacoes, "corrigir": a.corrigir,
                "imagens": a.imagens.clone().unwrap_or_else(|| "reprovados".into()), "materiais": null}),
    )
    .await?;
    if a.corrigir && r["correcoes"].as_object().is_some_and(|m| !m.is_empty()) {
        recibo(f, &p, &arquivo, "forja-3d", None, None, json!({"bancada": "movimento", "correcao": r["correcoes"]}), quem).await?;
        f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    }
    Ok(resultado(&r, None))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsImportar {
    pub projeto: Option<String>,
    /// Arquivos BVH, FBX ou glb (ou pastas com eles) que a pessoa baixou.
    pub arquivos: Vec<String>,
    /// mixamo, cmu, accad, 100style ou propria.
    pub fonte: String,
}

/// import_motion: traz capturas da pessoa para o banco do projeto (`Motion/<fonte>/`).
pub async fn importar(f: &Fornalha, a: ArgsImportar) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let fonte = match a.fonte.trim().to_lowercase().as_str() {
        "" => return Err(Erro::argumento("Diga de onde vêm as capturas (fonte): mixamo, cmu, accad, 100style ou propria.")),
        x @ ("mixamo" | "cmu" | "accad" | "100style" | "propria") => x.to_string(),
        outro => return Err(Erro::argumento(format!("Fonte {outro} desconhecida: use mixamo, cmu, accad, 100style ou propria."))),
    };
    let destino = p.raiz.join("Motion").join(&fonte);
    std::fs::create_dir_all(&destino).map_err(|e| Erro::io(&destino, e))?;
    let mut copiados = Vec::new();
    for c in &a.arquivos {
        let origem = f.resolver_caminho(c);
        let lista = if origem.is_dir() { arquivos_em(&origem) } else { vec![origem.clone()] };
        for arq in lista {
            let ok = arq.extension().and_then(|x| x.to_str()).is_some_and(|x| EXTENSOES.contains(&x.to_lowercase().as_str()));
            if !ok || !arq.is_file() {
                continue;
            }
            let Some(nome) = arq.file_name() else { continue };
            let alvo = destino.join(nome);
            std::fs::copy(&arq, &alvo).map_err(|e| Erro::io(&alvo, e))?;
            copiados.push(rel(&p.raiz, &alvo));
        }
    }
    if copiados.is_empty() {
        return Err(Erro::argumento("Nenhum arquivo BVH, FBX ou glb entre os que foram mandados."));
    }
    let (nome, licenca, credito, modelo) = fonte_importada(&fonte);
    let mut aviso = None;
    if let Some(m) = f.catalogo.modelo(modelo) {
        let ctx = f.contexto(Some(&p)).await;
        if let Situacao::PrecisaAceite { texto, .. } = crate::licencas::situacao_no_catalogo(&f.catalogo, m, &ctx) {
            aviso = Some(format!("Para usar estas capturas num projeto comercial, a pessoa precisa aceitar pela janela: {texto}"));
        }
    }
    Ok(
        json!({"fonte": format!("projeto/{fonte}"), "nome": nome, "licenca": licenca, "credito": credito, "copiados": copiados, "aviso": aviso,
              "dica": "Os clipes aparecem no list_motions (fonte projeto/<fonte>)."}),
    )
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsEsqueleto {
    pub projeto: Option<String>,
    pub arquivo: String,
    /// Mudanças (edit_skeleton): [{op: mover|criar|apagar|renomear|pai|espelhar, osso, pai, cabeca, ponta, ligado, novo, de}].
    pub mudancas: Vec<Value>,
    /// locais (padrão: só perto dos ossos mexidos), distancia (o corpo todo), auto (Blender) ou manter.
    pub pesos: Option<String>,
}

/// show_skeleton: imagem com os ossos numerados (frente, lado, cima) e a lista com avisos.
pub async fn ver_esqueleto(f: &Fornalha, a: ArgsEsqueleto) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    if !arquivo.is_file() {
        return Err(Erro::argumento(format!("Não achei {}.", arquivo.display())));
    }
    let r = forjar(f, &json!({"tarefa": "esqueleto_ver", "entrada": arquivo, "materiais": null})).await?;
    Ok(
        json!({"imagem": r["arquivos"]["imagem"], "ossos": r["ossos"], "avisos": r["avisos"], "altura_m": r["altura_m"], "animacoes": r["animacoes"],
              "dica": "Coordenadas em metros (x: esquerda do personagem, y: para trás, z: para cima; o personagem olha para -y). Edite com edit_skeleton pelo nome ou pelo número. Ossos mola_<grupo>_1..N (cauda, cabelo, asa, orelha) viram mola no jogo."}),
    )
}

/// edit_skeleton: muda o esqueleto como a IA pediu, refaz os pesos e devolve a imagem nova.
pub async fn editar_esqueleto(f: &Fornalha, a: ArgsEsqueleto, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    if !arquivo.is_file() {
        return Err(Erro::argumento(format!("Não achei {}.", arquivo.display())));
    }
    if a.mudancas.is_empty() {
        return Err(Erro::argumento("Diga as mudanças (mudancas): mover, criar, apagar, renomear, pai ou espelhar."));
    }
    let pesos = a.pesos.clone().unwrap_or_else(|| "locais".into());
    if !["locais", "distancia", "auto", "manter"].contains(&pesos.as_str()) {
        return Err(Erro::argumento("pesos: locais, distancia, auto ou manter."));
    }
    let r = forjar(
        f,
        &json!({"tarefa": "esqueleto_editar", "entrada": arquivo, "saida": arquivo, "mudancas": a.mudancas, "pesos": pesos, "materiais": null}),
    )
    .await?;
    recibo(f, &p, &arquivo, "forja-3d", None, None, json!({"bancada": "esqueleto", "mudancas": a.mudancas}), quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    Ok(json!({"feitas": r["feitas"], "pesos": r["pesos"], "imagem": r["arquivos"]["imagem"], "ossos": r["ossos"], "avisos": r["avisos"],
              "dica": "As animações que já existiam continuam (cada osso guarda o giro dele); confira com check_motion. Ossos novos não têm animação: use mola_<grupo>_<n> para eles balançarem no jogo."}))
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn assinatura_muda_com_os_arquivos() {
        let dir = std::env::temp_dir().join(format!("fornalha-mov-{}", std::process::id()));
        std::fs::create_dir_all(dir.join("sub")).unwrap();
        std::fs::write(dir.join("a.bvh"), b"HIERARCHY").unwrap();
        std::fs::write(dir.join("sub").join("b.FBX"), b"x").unwrap();
        std::fs::write(dir.join("leia.txt"), b"x").unwrap();
        let arqs = arquivos_em(&dir);
        assert_eq!(arqs.len(), 2, "só as capturas: {arqs:?}");
        let a1 = assinatura(&arqs);
        std::fs::write(dir.join("c.bvh"), b"HIERARCHY 2").unwrap();
        assert_ne!(a1, assinatura(&arquivos_em(&dir)));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn fontes_importadas_tem_modelo_no_catalogo() {
        let cat = crate::licencas::Catalogo::embutido();
        for id in ["mixamo", "cmu", "accad", "100style"] {
            let (_, _, _, modelo) = fonte_importada(id);
            assert!(cat.modelo(modelo).is_some(), "{modelo} falta no manifest");
        }
        assert_eq!(fonte_importada("propria").3, crate::recibos::MODELO_AUTORAL);
    }
}
