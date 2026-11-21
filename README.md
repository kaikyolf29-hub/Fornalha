<p align="center"><img src="app/ui/icone.png" width="96" height="96" alt=""></p>

<h1 align="center">Fornalha</h1>

<p align="center"><strong>Fábrica de jogos 3D com IA, na placa de vídeo do seu computador.</strong><br>
Modelos gratuitos com licença que deixa vender o jogo, recibo de licença por asset<br>
e uma API e servidor MCP para o Claude Code, o Codex ou qualquer agente.</p>

<p align="center">
  <a href="https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/ci.yml"><img alt="Testes" src="https://img.shields.io/github/actions/workflow/status/kaikyolf29-hub/Fornalha/ci.yml?label=testes"></a>
  <img alt="Windows primeiro" src="https://img.shields.io/badge/Windows%20primeiro-Linux%20também-4b5563">
  <img alt="Fase 0" src="https://img.shields.io/badge/plano-Fase%200-c2410c">
</p>

## Onde está
**Fase 0 (base)** do Plano 1. Pronto quando: *o Claude Code cria um projeto novo pelo MCP* — provado no CI com o SDK oficial do MCP e com o Claude Code de verdade.

| Fase | O que entrega | Situação |
|---|---|---|
| 0 · Base | Casca do Ignis, bíblia do jogo, recibos, placa e 4 níveis, API local e MCP | **pronta** (falta o teste do criador) |
| 1 · Primeiro personagem | Conceito e 3D na placa, limpeza e rig no Blender, 3 animações, envio para a engine | próxima |
| 2 · Mundo, armas e estilo | Blockout, cenário, armas com encaixe, guia visual com checagem | — |
| 3 · Áudio | Efeitos por evento, música por área, dublagem pt-BR e boca | — |
| 4 · Agente completo | Cérebro no Ignis coordenando tudo, fila da noite | — |
| 5 · Venda | Trailer, relatório de licenças, chave de ativação, atualização privada | — |

## O que a Fase 0 faz
- **Bíblia do jogo** (`game.project.json`): conceito, guia visual, personagens e mundo; toda geração vai receber esse contexto. Projeto novo já nasce com as pastas `GameDesign/`, `World/`, `Characters/`, `Enemies/`, `Items/`, `Weapons/`, `Animations/`, `Audio/`, `VFX/`, `Cutscenes/`, `UI/`, `Scripts/`, `blender/` e `ai/`.
- **Licenças:** catálogo com a licença, o link e o uso comercial de cada modelo do plano. Num projeto comercial, o roteador pula o que não pode ser vendido e explica por quê.
- **Recibo por asset** (`ai/recibos.jsonl`): modelo, versão, licença, prompt, referências, seed, data e quem pediu (você, o cérebro, o Claude Code ou o Codex). Mostra o que impede a venda e exporta o relatório de créditos (`ai/creditos-e-licencas.md`), com a parte do formulário de IA da Steam.
- **Placa e 4 níveis:** detecta a placa (NVIDIA, AMD, Intel ou só processador — código do Ignis) e sugere Leve, Equilibrado, Qualidade ou Máximo, com o modelo de cada função.
- **API local e MCP:** os mesmos comandos para a janela, a API (`http://127.0.0.1:11480/fornalha/*`) e o MCP (stdio com `fornalha --mcp`, ou HTTP em `http://127.0.0.1:11480/mcp`).
- **Janela:** barra de título integrada no jeito de cada sistema, bandeja, janela em processo separado, instância única.

## Conectar o Claude Code
Com a Fornalha aberta (perto do relógio):
```bash
claude mcp add --transport http fornalha http://127.0.0.1:11480/mcp
```
Ou mesmo com o app fechado (o Claude Code abre a Fornalha sem janela):
```bash
claude mcp add fornalha -- "%LOCALAPPDATA%\Fornalha\fornalha.exe" --mcp
```
Codex: `codex mcp add fornalha -- "<caminho do fornalha.exe>" --mcp`. A janela, em **Agentes**, mostra os comandos com o caminho certo para copiar.

Ferramentas: `get_status`, `create_project`, `open_project`, `list_projects`, `get_project`, `update_project`, `detect_gpu`, `list_quality_levels`, `choose_model`, `list_models`, `record_receipt`, `list_receipts`, `check_licenses`, `export_credits`. As de geração (`create_character`, `generate_3d`, `generate_animation`…) chegam a partir da Fase 1.

## Baixar (versões de teste)
Ainda não há versão oficial (a venda é da Fase 5). Cada mudança gera instaladores de teste em
**[Actions → Instaladores](https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/instaladores.yml)**: abra a execução mais recente com ✓ e baixe em *Artifacts* (`fornalha-windows`, `fornalha-linux`).

## Para desenvolver
Requisitos: Rust estável e Node 22. No Linux, também
`libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libxdo-dev libssl-dev`.
```bash
cargo test --workspace
```
```bash
cargo run -p fornalha-app
```
```bash
cargo run -p fornalha-cli -- detectar
```
Teste do MCP com o SDK oficial (stdio e HTTP):
```bash
cargo build -p fornalha-cli && cd testes/mcp-e2e && npm ci && node teste.mjs ../../target/debug/fornalha-cli
```

### Estrutura
| Pasta | O que tem |
|---|---|
| `crates/fornalha-core` | Núcleo: bíblia do jogo, licenças e roteador, recibos, níveis, placa, API local e MCP |
| `crates/fornalha-core/manifest/modelos.json` | Catálogo de modelos com licença e a tabela dos 4 níveis |
| `crates/fornalha-cli` | Linha de comando: `mcp`, `servir`, `detectar`, `chamar` |
| `app/src-tauri` | Aplicativo (bandeja + janela em processo separado + `--mcp`) |
| `app/ui` | Janela em HTML/CSS/JS puro, em português |
| `testes/mcp-e2e` | Teste de ponta a ponta com o SDK oficial do MCP |

Documentos: [ESTADO.md](ESTADO.md) (situação, decisões e pedidos para o Ignis),
[TESTE_DO_CRIADOR.md](TESTE_DO_CRIADOR.md) (o teste na sua máquina), [AVISOS.md](AVISOS.md) (código de terceiros).

## Licença
Todos os direitos reservados (veja [LICENSE](LICENSE)). Partes vieram do Ignis, sob MIT ([AVISOS.md](AVISOS.md)).
