//! A fila da noite: pedidos pesados (personagens, mundos, testes na engine) ficam
//! esperando e rodam um de cada vez — na hora (`agora`) ou só no horário da noite
//! (`noite`, padrão das 23h às 7h), com o computador livre para você de dia.
//! A fila fica em `<dados>/fila.json` e sobrevive a fechar e abrir a Fornalha.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::erro::{Erro, Resultado};
use crate::servico::Fornalha;

/// Ferramentas que podem ir para a fila (as de geração e teste).
pub const FERRAMENTAS_DA_FILA: [&str; 14] = [
    "create_character",
    "generate_concept",
    "generate_3d",
    "create_material",
    "create_skeleton",
    "generate_animation",
    "retarget_animation",
    "generate_sfx",
    "generate_music",
    "generate_voice",
    "generate_blockout",
    "generate_code",
    "import_to_engine",
    "run_test",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum Quando {
    #[default]
    Agora,
    Noite,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Situacao {
    Esperando,
    Rodando,
    Feita,
    Falhou,
    Cancelada,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tarefa {
    pub id: String,
    pub ferramenta: String,
    pub argumentos: Value,
    /// Quem pediu (a pessoa, o cérebro, o Claude Code...): vai para os recibos.
    pub quem: String,
    pub quando: Quando,
    pub situacao: Situacao,
    #[serde(default)]
    pub descricao: Option<String>,
    /// Pedidos que vieram juntos (um plano do cérebro).
    #[serde(default)]
    pub grupo: Option<String>,
    pub criada_em: String,
    #[serde(default)]
    pub comecou_em: Option<String>,
    #[serde(default)]
    pub terminou_em: Option<String>,
    #[serde(default)]
    pub resultado: Option<Value>,
    #[serde(default)]
    pub erro: Option<String>,
}

fn arquivo(f: &Fornalha) -> PathBuf {
    f.paths.data_dir.join("fila.json")
}

fn ler(f: &Fornalha) -> Vec<Tarefa> {
    std::fs::read(arquivo(f)).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
}

fn gravar(f: &Fornalha, lista: &[Tarefa]) -> Resultado<()> {
    let arq = arquivo(f);
    crate::paths::write_json(&arq, &lista).map_err(|e| Erro::io(&arq, e))
}

/// Uma escrita por vez no arquivo da fila.
static ARQUIVO: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn mudar<T>(f: &Fornalha, m: impl FnOnce(&mut Vec<Tarefa>) -> T) -> Resultado<T> {
    let _g = ARQUIVO.lock().unwrap_or_else(|e| e.into_inner());
    let mut lista = ler(f);
    let r = m(&mut lista);
    gravar(f, &lista)?;
    Ok(r)
}

/// Põe um pedido na fila.
pub fn enfileirar(
    f: &Fornalha,
    ferramenta: &str,
    argumentos: Value,
    quem: &str,
    quando: Quando,
    descricao: Option<String>,
    grupo: Option<String>,
) -> Resultado<Tarefa> {
    if !FERRAMENTAS_DA_FILA.contains(&ferramenta) {
        return Err(Erro::argumento(format!("\"{ferramenta}\" não vai para a fila. Use uma destas: {}.", FERRAMENTAS_DA_FILA.join(", "))));
    }
    if !argumentos.is_object() {
        return Err(Erro::argumento("Os argumentos da tarefa precisam ser um objeto JSON."));
    }
    let t = Tarefa {
        id: format!("tarefa_{}", crate::util::id_aleatorio(8)),
        ferramenta: ferramenta.into(),
        argumentos,
        quem: quem.into(),
        quando,
        situacao: Situacao::Esperando,
        descricao,
        grupo,
        criada_em: crate::util::agora_iso(),
        comecou_em: None,
        terminou_em: None,
        resultado: None,
        erro: None,
    };
    let copia = t.clone();
    mudar(f, move |l| l.push(t))?;
    Ok(copia)
}

/// A fila inteira (mais nova por último) e se agora é noite.
pub fn listar(f: &Fornalha) -> Value {
    let noite = f.config().noite;
    let lista = ler(f);
    let esperando = lista.iter().filter(|t| t.situacao == Situacao::Esperando).count();
    json!({
        "tarefas": lista,
        "esperando": esperando,
        "noite": {"inicio_hora": noite.inicio_hora, "fim_hora": noite.fim_hora, "agora_e_noite": noite.contem(hora_local())},
    })
}

pub fn cancelar(f: &Fornalha, id: &str) -> Resultado<Tarefa> {
    mudar(f, |l| {
        let t = l.iter_mut().find(|t| t.id == id).ok_or_else(|| Erro::argumento(format!("A tarefa {id} não existe.")))?;
        if t.situacao != Situacao::Esperando {
            return Err(Erro::argumento("Só dá para cancelar tarefa que ainda está esperando."));
        }
        t.situacao = Situacao::Cancelada;
        t.terminou_em = Some(crate::util::agora_iso());
        Ok(t.clone())
    })?
}

/// Tira da lista o que já terminou (feitas, falhas e canceladas).
pub fn limpar(f: &Fornalha) -> Resultado<usize> {
    mudar(f, |l| {
        let antes = l.len();
        l.retain(|t| matches!(t.situacao, Situacao::Esperando | Situacao::Rodando));
        antes - l.len()
    })
}

pub fn hora_local() -> u8 {
    use chrono::Timelike;
    chrono::Local::now().hour() as u8
}

/// Roda a próxima tarefa que pode rodar agora (as de "noite" só no horário da noite).
/// Devolve a tarefa terminada, ou `None` se não havia nada para rodar.
pub async fn rodar_proxima(f: &Fornalha, e_noite: bool) -> Option<Tarefa> {
    let _uma_por_vez = f.fila.try_lock().ok()?;
    let escolhida = mudar(f, |l| {
        let t = l.iter_mut().find(|t| t.situacao == Situacao::Esperando && (t.quando == Quando::Agora || e_noite))?;
        t.situacao = Situacao::Rodando;
        t.comecou_em = Some(crate::util::agora_iso());
        Some(t.clone())
    })
    .ok()??;
    let r = Box::pin(f.chamar(&escolhida.ferramenta, escolhida.argumentos.clone(), &escolhida.quem)).await;
    let id = escolhida.id.clone();
    mudar(f, move |l| {
        let t = l.iter_mut().find(|t| t.id == id)?;
        t.terminou_em = Some(crate::util::agora_iso());
        match r {
            Ok(v) => {
                t.situacao = Situacao::Feita;
                t.resultado = Some(v);
            }
            Err(e) => {
                t.situacao = Situacao::Falhou;
                t.erro = Some(e.mensagem);
            }
        }
        Some(t.clone())
    })
    .ok()?
}

/// Tarefa que ficou "rodando" quando a Fornalha fechou volta a esperar.
pub fn retomar_interrompidas(f: &Fornalha) -> Resultado<usize> {
    mudar(f, |l| {
        let mut n = 0;
        for t in l.iter_mut().filter(|t| t.situacao == Situacao::Rodando) {
            t.situacao = Situacao::Esperando;
            t.comecou_em = None;
            n += 1;
        }
        n
    })
}

/// Vigia da fila (no núcleo do app e no `fornalha-cli servir`): olha a cada 20 s.
pub async fn vigiar(f: Arc<Fornalha>) {
    let _ = retomar_interrompidas(&f);
    loop {
        let noite = f.config().noite.contem(hora_local());
        while rodar_proxima(&f, noite).await.is_some() {}
        tokio::time::sleep(Duration::from_secs(20)).await;
    }
}
