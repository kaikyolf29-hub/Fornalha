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

fn sem_acento(t: &str) -> String {
    t.to_lowercase()
        .chars()
        .map(|c| match c {
            'á' | 'à' | 'â' | 'ã' => 'a',
            'é' | 'ê' => 'e',
            'í' => 'i',
            'ó' | 'ô' | 'õ' => 'o',
            'ú' => 'u',
            'ç' => 'c',
            x => x,
        })
        .collect()
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
            busca.as_ref().is_none_or(|b| nome.contains(b.as_str()) || et.iter().any(|e| sem_acento(e).contains(&sem_acento(b))))
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
    /// Tomada longa de luta (guarda → golpe → guarda): fica só o golpe, em volta do pico da mão.
    pub golpe: Option<bool>,
    /// Mão fechada (soco, mão na arma). Padrão: fecha nos golpes, quando a captura não traz os dedos.
    pub punho: Option<bool>,
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
                            "inicio": c.inicio, "fim": c.fim, "velocidade": c.velocidade, "golpe": c.golpe, "punho": c.punho}));
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

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsVerMovimento {
    pub projeto: Option<String>,
    pub arquivo: String,
    /// Animação a ver (padrão: parado).
    pub animacao: Option<String>,
    /// Quantos quadros espalhados (2 a 16, padrão 8) ou a lista exata dos quadros (30 por segundo).
    pub quadros: Option<Value>,
    /// tres_quartos, frente, lado, costas, cima (padrão: tres_quartos e lado).
    pub angulos: Option<Vec<String>>,
    /// material (o do jogo), barro (só a forma) ou anime (dois tons e contorno).
    pub estilo: Option<String>,
    pub rastro: Option<bool>,
    pub esqueleto: Option<bool>,
    pub de_perto: Option<bool>,
}

pub const ANGULOS_DE_VER: [&str; 5] = ["tres_quartos", "frente", "lado", "costas", "cima"];
pub const ESTILOS_DE_VER: [&str; 3] = ["material", "barro", "anime"];

/// show_motion: folhas do movimento em quadros grandes para a IA ver (ângulos, rastro, esqueleto, de perto).
pub async fn ver_movimento(f: &Fornalha, a: ArgsVerMovimento) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    if !arquivo.is_file() {
        return Err(Erro::argumento(format!("Não achei o personagem {}.", arquivo.display())));
    }
    let angulos = a.angulos.clone().unwrap_or_else(|| vec!["tres_quartos".into(), "lado".into()]);
    if let Some(x) = angulos.iter().find(|x| !ANGULOS_DE_VER.contains(&x.as_str())) {
        return Err(Erro::argumento(format!("Ângulo {x} desconhecido: use {}.", ANGULOS_DE_VER.join(", "))));
    }
    if angulos.is_empty() || angulos.len() > 4 {
        return Err(Erro::argumento("Peça de 1 a 4 ângulos."));
    }
    let estilo = a.estilo.clone().unwrap_or_else(|| "material".into());
    if !ESTILOS_DE_VER.contains(&estilo.as_str()) {
        return Err(Erro::argumento(format!("Estilo {estilo} desconhecido: use {}.", ESTILOS_DE_VER.join(", "))));
    }
    let quadros = match &a.quadros {
        None | Some(Value::Null) => json!(8),
        Some(Value::Number(n)) => json!(n.as_u64().unwrap_or(8).clamp(2, 16)),
        Some(Value::Array(v)) if !v.is_empty() && v.len() <= 16 && v.iter().all(|x| x.is_u64()) => json!(v),
        _ => return Err(Erro::argumento("quadros: um número de 2 a 16, ou a lista dos quadros (até 16).")),
    };
    let r = forjar(
        f,
        &json!({"tarefa": "ver_movimento", "entrada": arquivo, "animacao": a.animacao, "quadros": quadros, "angulos": angulos,
                "estilo": estilo, "rastro": a.rastro.unwrap_or(true), "esqueleto": a.esqueleto.unwrap_or(true),
                "de_perto": a.de_perto.unwrap_or(true), "materiais": null}),
    )
    .await?;
    let c = &r["conferencia"];
    Ok(json!({
        "animacao": c["nome"],
        "folhas": r["folhas"],
        "quadros": r["quadros"],
        "estilo": r["estilo"],
        "cores_do_rastro": r["cores_do_rastro"],
        "aprovado_pela_regua": c["aprovado"],
        "problemas": c["problemas"],
        "medidas": c["medidas"],
        "animacoes": r["animacoes"],
        "dica": "Olhe cada folha antes de dizer que o movimento está bom: a régua mede ossos, pé, chão, mão e arma, mas não sabe se o golpe tem peso, se a pose lê bem ou se o estilo combina. Os quadros contam a 30 por segundo. Rastro: o caminho da mão, do pé e da ponta da arma na animação inteira (arco limpo = bom; zigue-zague = tremido). Chão em quadrados de 25 cm: pé parado que muda de quadrado escorrega. Para ajustar, use edit_motion (girar ou mover um osso num quadro, com o efeito espalhado nos vizinhos) e veja de novo.",
    }))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsEditarMovimento {
    pub projeto: Option<String>,
    pub arquivo: String,
    pub animacao: String,
    /// [{osso, quadro, giro: [x,y,z,w] no mundo do glTF (Y para cima), mover: [x,y,z] em metros, suavizar}].
    pub edicoes: Vec<Value>,
    /// Quadros para cada lado em que o ajuste some suavemente (padrão 6).
    pub suavizar: Option<u32>,
    /// Grava como outra animação (a original fica).
    pub salvar_como: Option<String>,
    pub corrigir: bool,
}

/// edit_motion: ajustes do estúdio (ou da IA) numa animação, conferidos de novo e gravados.
pub async fn editar_movimento(f: &Fornalha, a: ArgsEditarMovimento, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    if !arquivo.is_file() {
        return Err(Erro::argumento(format!("Não achei o personagem {}.", arquivo.display())));
    }
    if a.animacao.trim().is_empty() {
        return Err(Erro::argumento("Diga a animação (animacao)."));
    }
    if a.edicoes.is_empty() {
        return Err(Erro::argumento("Diga os ajustes (edicoes): [{osso, quadro, giro: [x,y,z,w]} ou mover: [x,y,z]]."));
    }
    for e in &a.edicoes {
        let ok_osso = e["osso"].as_str().is_some_and(|s| !s.is_empty());
        let ok_giro = e["giro"].as_array().is_some_and(|v| v.len() == 4 && v.iter().all(|x| x.is_number()));
        let ok_mover = e["mover"].as_array().is_some_and(|v| v.len() == 3 && v.iter().all(|x| x.is_number()));
        if !ok_osso
            || !e["quadro"].is_u64()
            || !(ok_giro || ok_mover)
            || (!e["giro"].is_null() && !ok_giro)
            || (!e["mover"].is_null() && !ok_mover)
        {
            return Err(Erro::argumento(format!(
                "Ajuste inválido: {e}. Cada um precisa de osso, quadro e giro [x,y,z,w] e/ou mover [x,y,z]."
            )));
        }
    }
    if let Some(n) = &a.salvar_como {
        if !n.trim().is_empty() && !n.chars().all(|c| c.is_alphanumeric() || c == '_') {
            return Err(Erro::argumento("salvar_como: só letras, números e _ (é o nome da animação no jogo)."));
        }
    }
    let r = forjar(
        f,
        &json!({"tarefa": "editar_movimento", "entrada": arquivo, "saida": arquivo, "animacao": a.animacao, "edicoes": a.edicoes,
                "suavizar": a.suavizar.unwrap_or(6).min(30), "salvar_como": a.salvar_como, "corrigir": a.corrigir, "materiais": null}),
    )
    .await?;
    recibo(f, &p, &arquivo, "forja-3d", None, None, json!({"bancada": "estudio", "animacao": r["animacao"], "edicoes": a.edicoes}), quem)
        .await?;
    f.avisar_ponte(vec![rel(&p.raiz, &arquivo)]);
    Ok(json!({
        "animacao": r["animacao"],
        "edicoes": r["edicoes"],
        "aprovado_pela_regua": r["aprovado"],
        "conferencia": {"problemas": r["conferencia"]["problemas"], "medidas": r["conferencia"]["medidas"]},
        "correcoes": r["correcoes"],
        "animacoes": r["animacoes"],
        "arquivos": r["arquivos"],
        "dica": "Veja o resultado com show_motion antes de dar por pronto (a régua não julga se ficou bonito).",
    }))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsRoupa {
    pub projeto: Option<String>,
    /// O personagem (glb com esqueleto) que serve de manequim: a roupa nasce na pele dele.
    pub corpo: String,
    pub nome: Option<String>,
    /// Partes: casca, faixa, saia, adorno (veja a descrição da ferramenta).
    pub pecas: Vec<Value>,
    pub materiais: Option<Value>,
}

pub const TIPOS_DE_PARTE_DA_ROUPA: [&str; 5] = ["casca", "faixa", "saia", "adorno", "rebites"];

/// create_garment: roupa ou armadura separada, feita no corpo do manequim, para vestir depois.
pub async fn criar_roupa(f: &Fornalha, a: ArgsRoupa, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let corpo = f.resolver_no_projeto(&p, &a.corpo);
    if !corpo.is_file() {
        return Err(Erro::argumento(format!("Não achei o corpo {} (um personagem com esqueleto).", corpo.display())));
    }
    if a.pecas.is_empty() {
        return Err(Erro::argumento("Diga as partes da roupa (pecas): casca, faixa, saia, adorno ou rebites."));
    }
    if a.pecas.len() > 200 {
        return Err(Erro::argumento("No máximo 200 partes por roupa."));
    }
    for (i, x) in a.pecas.iter().enumerate() {
        let tipo = x["tipo"].as_str().unwrap_or("");
        if !TIPOS_DE_PARTE_DA_ROUPA.contains(&tipo) {
            return Err(Erro::argumento(format!("Parte {i}: tipo \"{tipo}\" não existe. Use {}.", TIPOS_DE_PARTE_DA_ROUPA.join(", "))));
        }
    }
    let nome = crate::projeto::nome_de_pasta(a.nome.as_deref().unwrap_or("roupa"));
    let pasta = corpo.parent().map(|d| d.join("roupas")).unwrap_or_else(|| p.raiz.join("Characters").join("roupas"));
    let saida = pasta.join(format!("{nome}.glb"));
    let mut materiais = a.materiais.clone().unwrap_or_else(|| json!({}));
    if materiais.as_object().is_none_or(|m| m.is_empty()) {
        materiais = json!({"principal": {"cor": "#8a8580", "tipo": "tecido"}});
    }
    let r = forjar(
        f,
        &json!({"tarefa": "roupa", "entrada": corpo, "saida": saida, "roupa": {"id": nome, "pecas": a.pecas, "materiais": materiais}}),
    )
    .await?;
    recibo(
        f,
        &p,
        &saida,
        "forja-3d",
        None,
        None,
        json!({"bancada": "roupa", "corpo": rel(&p.raiz, &corpo), "partes": a.pecas.len()}),
        quem,
    )
    .await?;
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    Ok(json!({
        "roupa": saida,
        "arquivos": r["arquivos"],
        "partes": r["partes"],
        "triangulos": r["triangulos"],
        "avisos": r["avisos"],
        "corpo": r["corpo"],
        "proximo": format!("Olhe as duas imagens (sozinha e no manequim de barro). Ajuste e gere de novo até ficar como a referência; depois vista com dress_character (arquivo: {}, roupa: {}) e confira o movimento com check_motion e show_motion.", rel(&p.raiz, &corpo), rel(&p.raiz, &saida)),
    }))
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct ArgsVestir {
    pub projeto: Option<String>,
    /// Personagem (glb) com esqueleto, pesos e as animações já conferidas.
    pub arquivo: String,
    /// Malha da roupa ou armadura (glb, obj, fbx), feita para este corpo (ou com encaixar: true).
    pub roupa: String,
    /// auto (padrão: peça pequena de um osso só fica rígida), sim (todas rígidas) ou nao (tudo dobra).
    pub rigido: Option<String>,
    /// Leva a roupa para o tamanho e o lugar do corpo (altura, centro, chão).
    pub encaixar: bool,
    /// Onde gravar (padrão: o próprio personagem).
    pub saida: Option<String>,
    /// Arma na mão direita depois de vestir (espada, machado, lanca, martelo, adaga, cajado).
    pub arma: Option<String>,
    /// Escudo na mão esquerda.
    pub escudo: bool,
}

/// dress_character: roupa por cima de um personagem que já se mexe.
pub async fn vestir(f: &Fornalha, a: ArgsVestir, quem: &str) -> Resultado<Value> {
    let p = f.projeto(a.projeto.as_deref())?;
    let arquivo = f.resolver_no_projeto(&p, &a.arquivo);
    let roupa = f.resolver_no_projeto(&p, &a.roupa);
    for (x, o) in [(&arquivo, "personagem"), (&roupa, "roupa")] {
        if !x.is_file() {
            return Err(Erro::argumento(format!("Não achei o arquivo da {o}: {}.", x.display())));
        }
    }
    let rigido = a.rigido.clone().unwrap_or_else(|| "auto".into());
    if !["auto", "sim", "nao"].contains(&rigido.as_str()) {
        return Err(Erro::argumento("rigido: auto, sim ou nao."));
    }
    if let Some(arma) = a.arma.as_deref() {
        if arma != "nenhuma" && !crate::forja::ARMAS.contains(&arma) {
            return Err(Erro::argumento(format!("arma: {} ou nenhuma.", crate::forja::ARMAS.join(", "))));
        }
    }
    let escudo = a.escudo || a.arma.as_deref() == Some("escudo");
    let arma = a.arma.as_deref().filter(|x| *x != "escudo");
    let saida = a.saida.as_deref().map(|s| f.resolver_no_projeto(&p, s)).unwrap_or_else(|| arquivo.clone());
    let r = forjar(
        f,
        &json!({"tarefa": "vestir", "entrada": arquivo, "roupa": roupa, "saida": saida, "rigido": rigido, "encaixar": a.encaixar, "materiais": null,
                "arma": arma, "escudo": escudo}),
    )
    .await?;
    recibo(f, &p, &saida, "forja-3d", None, None, json!({"bancada": "roupa", "roupa": a.roupa, "rigido": rigido}), quem).await?;
    f.avisar_ponte(vec![rel(&p.raiz, &saida)]);
    let mut out = resultado(&r, None);
    out["roupa"] = r["roupa"].clone();
    out["dica"] = json!("A roupa segue as animações que o personagem já tinha. Placas (ilhas_rigidas) ficam presas no osso de baixo; pano grande dobra com o corpo. Se a conferência reprovar por corpo sólido, a roupa é grossa demais ali: afaste com check_motion (corrigir) ou ajuste a peça.");
    Ok(out)
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
