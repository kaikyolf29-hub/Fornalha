# ESTADO do projeto Fornalha

> Toda retomada começa por aqui. Atualizado antes de cada pausa.

## Situação (21/11/2026)
**Fase 0 (base) pronta no código e nos testes.** Falta o teste do criador na máquina dele
(TESTE_DO_CRIADOR.md). Nenhuma versão oficial publicada (venda e atualização privada são da Fase 5);
instaladores de teste saem em Actions → Instaladores.

Pronto da Fase 0 ("o Claude Code cria um projeto novo pelo MCP"):
- provado com o **SDK oficial do MCP** (o mesmo do Claude Code), por stdio (`fornalha --mcp` e `fornalha-cli mcp`) e por HTTP (`/mcp`), no Linux e no CI do Windows;
- provado com o **Claude Code 2.1 de verdade** (`claude mcp list` → "Connected" nos dois transportes);
- falta: o criador pedir no Claude Code dele e ver o projeto aparecer.

## O que está pronto
- **Núcleo** (`crates/fornalha-core`), testado sem placa e sem janela:
  - `projeto`: bíblia do jogo (`game.project.json`), pastas padrão, validação, JSON Merge Patch, campos desconhecidos preservados;
  - `licencas` + `manifest/modelos.json`: catálogo da tabela do plano (39 modelos), roteador por licença, placa (CUDA) e nível, com queda para o nível de baixo e motivo de cada recusa;
  - `niveis`: sugestão pela placa principal (limites 11/15/22 GB), aceleradores (CUDA, ROCm, Vulkan), tabela dos 4 níveis;
  - `recibos`: recibo por asset em `ai/recibos.jsonl` (SHA-256, modelo, licença, prompt, seed, quem pediu), pendências antes de vender, relatório `ai/creditos-e-licencas.md` com a parte da Steam, asset "autoral";
  - `ferramentas` + `servico`: 14 ferramentas, uma lista só para janela, API e MCP;
  - `api`: `/fornalha/estado`, `/fornalha/ferramentas`, `POST /fornalha/ferramentas/{nome}`, `/mcp`; só 127.0.0.1, recusa Host/Origin de fora;
  - `mcp`: JSON-RPC 2.0, versões 2025-11-25, 2025-06-18, 2025-03-26 e 2024-11-05, sessões no HTTP, quem pediu vem do cliente (o agente não se passa pela pessoa);
  - `ignis`: lê `/motor/estado` e `/motor/versao` do Ignis (porta 11470);
  - do Ignis (MIT): `gpu/`, `distro`, `janela`, parte de `util`, com os testes e fixtures.
- **App** (`app/`, Tauri 2): bandeja, janela em processo separado, instância única, barra de título integrada (Windows 11, GNOME, KDE, Mac, Matsu OS), telas Início, Projetos, Placa e níveis, Licenças, Agentes e Ajustes; `fornalha --mcp`.
- **CLI** (`crates/fornalha-cli`): `mcp`, `servir --porta`, `detectar`, `chamar`, `ferramentas`.
- **CI**: `ci.yml` (fmt, clippy, testes e MCP de ponta a ponta no Windows e no Linux) e `instaladores.yml` (NSIS; .deb, .rpm e AppImage; instala, abre o app, confere janela e API, testa o MCP do instalado e tira foto da tela).

## Provado vs. falta provar
- Provado aqui (Linux, sem placa): todos os testes, o app abrindo numa tela virtual (janela, bandeja, API, criar projeto clicando, aceite de licença, fechar para a bandeja, instância única), MCP pelo executável do app.
- Provado no CI: veja o último run de **CI** e **Instaladores** (Windows instalado de verdade, com foto da janela).
- Falta provar (só na máquina do criador): detecção da RX 580 e da placa nova reais, bandeja do Windows, cantos e Aero Snap do Windows 11, Claude Code dele criando o projeto.

## Decisões (do plano, 20/11/2026) e as tomadas na Fase 0
- Nome Fornalha; engine do Plano 2 é a Erethea Engine (até lá, Godot: `engine: "godot"` na bíblia).
- Windows primeiro; nada que impeça o Linux (o CI já roda nos dois).
- Repositório público sem licença aberta (todos os direitos reservados).
- Porta da API e do MCP: **11480** (a do Ignis é 11470). *Decisão da Fase 0.*
- Projeto novo nasce **comercial** (só entra modelo que deixa vender). *Decisão da Fase 0.*
- Recibos em **JSON Lines** (`ai/recibos.jsonl`), legível e bom para Git, em vez de banco SQLite. *Decisão da Fase 0.*
- Aceite de licença com condição e receita do estúdio: **só a pessoa, pela janela**. *Decisão da Fase 0.*
- Nomes das ferramentas em inglês (como no plano), argumentos e textos em português.

## Achado que muda o plano: TRELLIS.2 e o nvdiffrast
Os pesos do TRELLIS.2 são MIT, mas a etapa de textura usa o **nvdiffrast** (NVIDIA Source Code
License: só pesquisa e avaliação). Por isso o catálogo marca o TRELLIS.2 como bloqueado em projeto
comercial até a Fase 1 assar a textura sem o nvdiffrast (no Blender, por exemplo). Até lá, o único
3D liberado para venda é o Hunyuan3D-2mini (só forma), com o aceite da licença da Tencent (que não
vale na União Europeia, no Reino Unido e na Coreia do Sul).
Outras notas do catálogo: ACE-Step 1.5 é MIT, mas o repositório dos pesos ainda não traz o LICENSE;
o Audio2Emotion (junto do Audio2Face) só pode ser usado com o Audio2Face; HY-Motion e Hunyuan3D têm a
mesma regra de território da Tencent.

## Pedidos para o Ignis
Os 8 do plano continuam valendo (voz comercial com Chatterbox, imagem pelo Vulkan, reserva de placa,
`uso_comercial` nos modelos, aceleradores e VRAM em `/motor/estado`, `response_format` com
`json_schema`, modelo de visão leve, dois modelos carregados). Detalhe que a Fase 0 sugere para o
pedido 5, para a integração ser direta:

> Em `/motor/estado`, um campo `aceleradores: {"cuda": bool, "rocm": bool, "vulkan": bool}` e, em
> `placa`, `vram_total_mb` e `vram_livre_mb` (números em MB). A Fornalha usa exatamente esse formato
> internamente (`niveis::Aceleradores`) e passa a perguntar ao Ignis em vez de detectar de novo.

## Próximo passo
1. Criador: rodar o TESTE_DO_CRIADOR.md no Windows (e, se quiser, no Linux).
2. Fase 1 (primeiro personagem): workers Python (TRELLIS.2, UniRig), ComfyUI sem janela, Blender por linha de comando, textura sem nvdiffrast, 3 animações da biblioteca, exportar glTF para a Godot.
