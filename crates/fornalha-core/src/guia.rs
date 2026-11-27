//! Guia para a IA dentro de cada projeto de jogo (Etapa 3): qualquer agente (Claude Code, Codex, Gemini
//! CLI, Cursor, Copilot, Windsurf…) que abrir a pasta do jogo sabe como trabalhar com a Erethea Engine (a
//! principal) e a Fornalha 3D (a ajudante): como conectar os dois MCP, a ordem das receitas e as regras.
//!
//! O texto mora no `AGENTS.md` (o padrão aberto que a maioria dos agentes lê), num bloco marcado que a
//! Fornalha atualiza sem tocar no resto do arquivo. Os outros arquivos só apontam para ele e não são
//! sobrescritos se a pessoa já tiver o dela: `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`,
//! `.cursor/rules/fornalha.mdc`, `.windsurfrules`. As configurações de MCP vão para `.mcp.json` (Claude
//! Code), `.cursor/mcp.json`, `.vscode/mcp.json` e `.gemini/settings.json`, pelo HTTP local; o Codex lê o
//! MCP do arquivo do usuário (`~/.codex/config.toml`), e o trecho para colar está no guia.

use std::path::Path;

use serde_json::json;

use crate::consts::PORTA_PADRAO;
use crate::erro::{Erro, Resultado};
use crate::projeto::Projeto;

const INICIO: &str = "<!-- fornalha:guia:inicio (a Fornalha atualiza este bloco; escreva fora dele) -->";
const FIM: &str = "<!-- fornalha:guia:fim -->";
/// Porta padrão do servidor MCP do editor da Erethea (erethea/mcp/port).
pub const PORTA_MCP_ERETHEA: u16 = 11481;

fn bloco(p: &Projeto) -> String {
    let b = &p.biblia;
    let porta = PORTA_PADRAO;
    let engine =
        if b.engine == "godot" { "Godot (a Erethea Engine é a principal; o projeto abre igual nas duas)" } else { "Erethea Engine" };
    format!(
        r#"{INICIO}
# {nome}: guia para a IA

Este jogo é feito pela IA (você) com duas ferramentas que trabalham juntas:
- **Erethea Engine** (a principal): o fork da Godot 4.8 do criador. Abre a cena, roda o jogo, renderiza, mede
  desempenho. Engine deste projeto: {engine}.
- **Fornalha 3D** (a ajudante): gera e confere os assets com licença comercial (personagens, movimento,
  roupa, armas, mundo, sons, música, dublagem) e monta tudo na engine. Ela não traz jogo pronto: dá a você
  ferramentas, imagens e medidas. Olhe as imagens e os vídeos que as ferramentas devolvem antes de seguir.

## Conectar (MCP)
- Fornalha: `http://127.0.0.1:{porta}/mcp` (a Fornalha aberta na bandeja). Sem ela aberta, use o stdio com o
  caminho do programa (`"<caminho>/fornalha" --mcp`); a janela da Fornalha, em **Agentes**, mostra o comando
  certo para copiar.
- Erethea: `http://127.0.0.1:{pe}/mcp` (liga sozinho quando o projeto abre na Erethea 1.0.2 ou mais nova;
  noutra porta, `ERETHEA_MCP_PORT=<porta>`; para desligar num projeto, `editor/erethea_fornalha/mcp_server=false`
  no `project.godot`). Ferramentas da cena, `take_screenshot`, `run_test`, `get_errors`,
  `build_fornalha_scenes`, `check_export`.
- Os arquivos de MCP para Claude Code, Cursor, VS Code/Copilot e Gemini CLI já estão nesta pasta. No Codex,
  cole no `~/.codex/config.toml`:
  ```toml
  [mcp_servers.fornalha]
  url = "http://127.0.0.1:{porta}/mcp"
  [mcp_servers.erethea]
  url = "http://127.0.0.1:{pe}/mcp"
  ```

## Ordem das receitas
1. **Bíblia**: `get_project` / `update_project` (`game.project.json` é a fonte da verdade: gênero, estilo,
   paleta, áreas do mundo). Referência em estilo anime/cel: `guia_visual.render = "anime"` (no jogo, luz
   em faixas e contorno); fotorrealista: `"realista"` (padrão).
2. **Personagem**: `create_character` (com `imagem` para usar um conceito pronto; `corpo` para criaturas).
   Controles finos do humano: `cabelo` (penteado, cor, volume, agrupamento, ondulação, frizz, rente,
   grisalho, direção), `barba` (tipo, cor, comprimento, densidade, grisalho), `idade`, `genero`,
   `corpo_humano`, `rosto` (alvos do MakeHuman, inclusive expressão), `pele` (sardas, manchas, poros,
   rugas, bronzeado), `cor_olhos`, `sobrancelha`, `roupa` (estilo e cores).
   Malha pronta (TRELLIS.2, API, artista, armadura inteira): `create_skeleton` com `arma` — o manequim
   entra como molde e ela ganha o esqueleto de jogo, a captura de movimento conferida e a arma na mão.
   Golpes: com o pacote ACCAD, captura real (corte, estocada, aparar) para espada, machado, martelo e adaga.
   **Com referência** (personagem, arma, casa, mapa): passe `referencia` ou use `compare_reference`, olhe o
   lado a lado e as medidas (paleta, diferença de cor, silhueta), ajuste e gere de novo até chegar o mais perto
   possível. Fique sempre com o melhor resultado; não entregue o que está visivelmente pior que a referência.
3. **Movimento antes da roupa**: `check_motion` (com `corrigir`), `list_motions` → `apply_motion` (banco
   Quaternius, ACCAD, 100STYLE, Mixamo/CMU trazidos com `import_motion`; `golpe: true` recorta a tomada
   longa de luta no golpe); `show_skeleton` / `edit_skeleton` para qualquer corpo (ossos
   `mola_<grupo>_1..N` viram mola no jogo). A régua também reprova arma fora da mão e mão/pé da malha que
   não segue o osso. **Veja antes de aprovar**: `show_motion` (quadros grandes de 3/4 e de lado, rastro da
   mão, do pé e da ponta da arma, chão de 25 cm, esqueleto com o osso reprovado em vermelho, mão e pés de
   perto; estilos material, barro e anime). Para ajustar um quadro: `edit_motion` (girar/mover um osso,
   espalhado suave nos vizinhos; `salvar_como` guarda a original) e veja de novo. A pessoa faz o mesmo no
   Estúdio 3D da janela (estação Movimento).
4. **Roupa separada, depois vestida**: com referência de roupa ou armadura, faça um manequim
   (`create_character` com `roupa: {{estilo: "manequim"}}`), faça a roupa no corpo dele com
   `create_garment` (casca do corpo para peitoral, espaldar, ombreira, braçal, greva e camisa, `convexa` e
   `laminas` para placa de metal em lâminas; faixa para cinto, gola e punho, com `inclinacao` para o cinto
   cruzado; saia para túnica, sobreveste e capa; adorno para cruz, fivela, broche, bainha e bordado;
   rebites pela beira da placa ou do cinto; `desgaste` no material de metal para riscos e marcas de uso),
   olhe as imagens (sozinha e no manequim de barro, frente, lado, costas e o tronco de perto) e ajuste até
   ficar como a referência; depois `dress_character` (placas rígidas no osso, pano dobra; `arma` põe a arma
   na mão) e confira o movimento vestido (`check_motion` e `show_motion`).
5. **Armas, objetos e casas**: `generate_3d`. Para chegar perto de uma referência, monte a forma por
   peças (`pecas`: caixa com chanfro, cilindro, esfera, torno pelo perfil, extrusão do contorno com gume,
   tubo por pontos; `materiais` com cor e tipo) olhando a imagem, passe `referencia` e ajuste até ficar
   perto. Placa NVIDIA: `imagem` faz o 3D direto da imagem (TRELLIS.2). **Mundo**: escreva o plano do mapa
   e use `generate_map` (relevo, rio, estradas, vila, masmorra, vegetação, luz da hora; olhe o `mapa.png`,
   as medidas e as fotos de cada região no `run_test`); a vila usa as casas que você montou
   (`regioes[].casas`); `generate_blockout` só para um teste rápido.
6. **Som**: `generate_sfx`, `generate_music`, `generate_voice` (dublagem com a boca mexendo).
   **Cena curta**: `create_cutscene` com o roteiro (quem fala, o texto, enquadramento close/medio/aberto/
   ombro/dois, animação, para quem olha); no jogo, `CenasCurtas.tocar("id")`.
7. **Montar e testar**: `import_to_engine` e `run_test` (na Erethea roda também o teste de agente dela);
   veja as capturas e o vídeo.
8. **Antes de vender**: `check_licenses` e `export_credits` (créditos obrigatórios, como ACCAD e 100STYLE).

## Regras
- Só entra modelo e captura com licença comercial; todo arquivo gerado tem recibo (`record_receipt` quando
  for feito à mão). Licença que pede aceite só a pessoa aceita, na janela da Fornalha: nunca aceite por ela.
- "Aprovado" numa conferência quer dizer que a régua não achou o que ela mede; pronto é depois de olhar o
  vídeo e de a pessoa ver.
- Não diga que algo funciona numa placa de vídeo sem ter rodado nela.
- Os scripts em `Scripts/fornalha/` são da Fornalha (o que você mudar neles é mantido na próxima montagem).
- Coerência: todo personagem, arma, objeto e mapa segue a bíblia (estilo, paleta, época); as cores que você
  não der saem da paleta do projeto.
- Fale com a pessoa em português do Brasil.
{FIM}"#,
        nome = b.nome,
        pe = PORTA_MCP_ERETHEA,
    )
}

const PONTEIRO: &str = "As instruções deste jogo para agentes de IA estão no AGENTS.md, na raiz do projeto: leia antes de começar.\n";

fn escrever_se_faltar(arq: &Path, texto: &str) -> Resultado<bool> {
    if arq.exists() {
        return Ok(false);
    }
    if let Some(d) = arq.parent() {
        std::fs::create_dir_all(d).map_err(|e| Erro::io(d, e))?;
    }
    std::fs::write(arq, texto).map_err(|e| Erro::io(arq, e))?;
    Ok(true)
}

/// Grava (ou atualiza o bloco da Fornalha) do guia e os arquivos de cada agente. Devolve o que foi escrito.
pub fn escrever(p: &Projeto) -> Resultado<Vec<String>> {
    let raiz = &p.raiz;
    let mut feitos = Vec::new();
    // AGENTS.md: o bloco da Fornalha é trocado; o que a pessoa escreveu fora dele fica
    let agentes = raiz.join("AGENTS.md");
    let novo = bloco(p);
    let texto = match std::fs::read_to_string(&agentes) {
        Ok(atual) => match (atual.find(INICIO), atual.find(FIM)) {
            (Some(a), Some(b)) if b > a => format!("{}{}{}", &atual[..a], novo, &atual[b + FIM.len()..]),
            _ => format!("{novo}\n\n{atual}"),
        },
        Err(_) => format!("{novo}\n"),
    };
    std::fs::write(&agentes, texto).map_err(|e| Erro::io(&agentes, e))?;
    feitos.push("AGENTS.md".to_string());
    // ponteiros para os agentes que leem outro arquivo
    let ponteiro_claude = "@AGENTS.md\n";
    let cursor = format!("---\ndescription: Guia do jogo (Erethea + Fornalha)\nalwaysApply: true\n---\n{PONTEIRO}");
    for (rel, conteudo) in [
        ("CLAUDE.md", ponteiro_claude.to_string()),
        ("GEMINI.md", PONTEIRO.to_string()),
        (".github/copilot-instructions.md", PONTEIRO.to_string()),
        (".cursor/rules/fornalha.mdc", cursor),
        (".windsurfrules", PONTEIRO.to_string()),
    ] {
        if escrever_se_faltar(&raiz.join(rel), &conteudo)? {
            feitos.push(rel.to_string());
        }
    }
    // MCP: os dois pelo HTTP local (a Fornalha na bandeja, a Erethea no editor); o caminho do programa
    // muda de máquina para máquina, então o stdio fica no guia e na janela, não nos arquivos
    let url_fornalha = format!("http://127.0.0.1:{PORTA_PADRAO}/mcp");
    let url_erethea = format!("http://127.0.0.1:{PORTA_MCP_ERETHEA}/mcp");
    let claude = json!({"mcpServers": {
        "fornalha": {"type": "http", "url": url_fornalha},
        "erethea": {"type": "http", "url": url_erethea},
    }});
    let cursor_mcp = json!({"mcpServers": {
        "fornalha": {"url": url_fornalha},
        "erethea": {"url": url_erethea},
    }});
    let vscode = json!({"servers": {
        "fornalha": {"type": "http", "url": url_fornalha},
        "erethea": {"type": "http", "url": url_erethea},
    }});
    let gemini = json!({"mcpServers": {
        "fornalha": {"httpUrl": url_fornalha},
        "erethea": {"httpUrl": url_erethea},
    }});
    for (rel, v) in
        [(".mcp.json", claude), (".cursor/mcp.json", cursor_mcp), (".vscode/mcp.json", vscode), (".gemini/settings.json", gemini)]
    {
        let texto = serde_json::to_string_pretty(&v).unwrap_or_default() + "\n";
        if escrever_se_faltar(&raiz.join(rel), &texto)? {
            feitos.push(rel.to_string());
        }
    }
    Ok(feitos)
}

#[cfg(test)]
mod testes {
    use super::*;
    use crate::projeto::{criar, NovoProjeto};

    #[test]
    fn guia_para_qualquer_agente_e_bloco_atualizavel() {
        let tmp = tempfile::tempdir().unwrap();
        let p = criar(&NovoProjeto { nome: "Reino de Cinzas".into(), ..Default::default() }, tmp.path()).unwrap();
        for rel in [
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            ".github/copilot-instructions.md",
            ".cursor/rules/fornalha.mdc",
            ".windsurfrules",
            ".mcp.json",
            ".cursor/mcp.json",
            ".vscode/mcp.json",
            ".gemini/settings.json",
        ] {
            assert!(p.raiz.join(rel).is_file(), "falta {rel}");
        }
        let a = std::fs::read_to_string(p.raiz.join("AGENTS.md")).unwrap();
        assert!(a.contains("Reino de Cinzas") && a.contains("apply_motion") && a.contains(":11481/mcp"));
        let mcp: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(p.raiz.join(".mcp.json")).unwrap()).unwrap();
        assert_eq!(mcp["mcpServers"]["fornalha"]["url"], "http://127.0.0.1:11480/mcp");
        // o que a pessoa escreve fora do bloco fica; o bloco é trocado
        std::fs::write(p.raiz.join("AGENTS.md"), format!("{a}\n## Minhas notas\nnão apagar\n")).unwrap();
        std::fs::write(p.raiz.join("CLAUDE.md"), "meu claude\n").unwrap();
        escrever(&p).unwrap();
        let b = std::fs::read_to_string(p.raiz.join("AGENTS.md")).unwrap();
        assert!(b.contains("não apagar") && b.matches(INICIO).count() == 1, "{b}");
        assert_eq!(std::fs::read_to_string(p.raiz.join("CLAUDE.md")).unwrap(), "meu claude\n");
    }
}
