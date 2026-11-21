<p align="center"><img src="app/ui/icone.png" width="96" height="96" alt=""></p>

<h1 align="center">Fornalha</h1>

<p align="center"><strong>Fábrica de jogos 3D com IA, na placa de vídeo do seu computador.</strong><br>
Modelos gratuitos com licença que deixa vender o jogo, recibo de licença por asset<br>
e uma API e servidor MCP para o Claude Code, o Codex ou qualquer agente.</p>

<p align="center">
  <a href="https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/ci.yml"><img alt="Testes" src="https://img.shields.io/github/actions/workflow/status/kaikyolf29-hub/Fornalha/ci.yml?label=testes"></a>
  <img alt="Windows e Linux" src="https://img.shields.io/badge/Windows%20primeiro-Linux%20também-4b5563">
  <img alt="Fases 0 a 4" src="https://img.shields.io/badge/plano-Fases%200%20a%204-c2410c">
</p>

## Onde está
**Fases 0 a 4 do Plano 1**, testadas sem placa de vídeo e com as gerações de verdade rodando no CI do
Windows e do Linux (Blender 5.2.4 e Godot 4.6.1): personagem com esqueleto e animações, armas,
objetos, mundo, efeitos, música, código do jogo, cenas montadas na engine e o jogo testado sozinho.
Veja [ESTADO.md](ESTADO.md) para o que foi provado e o que falta provar.

| Fase | O que entrega | Situação |
|---|---|---|
| 0 · Base | Bíblia do jogo, recibos, placa e 4 níveis, API local e MCP | pronta |
| 1 · Primeiro personagem | Conceito, 3D com esqueleto e 9 animações, envio para a engine | pronta (modelos de placa: falta prova em NVIDIA) |
| 2 · Mundo, armas e estilo | Blockout pela bíblia, armas na mão, objetos com colisão, checagem do guia visual | pronta (forma e conteúdo esperam a visão do Ignis) |
| 3 · Áudio | Efeitos por evento, música por área, dublagem pt-BR e boca | pronta |
| 4 · Agente completo | Pedido livre pelo cérebro no Ignis, fila da noite, "crie um inimigo novo" testado na engine | pronta |
| 5 · Venda | Trailer, chave de ativação, atualização privada | quando o criador pedir |

## O que ela gera
| Pedido | Quem faz (sem placa) | Quem faz (com NVIDIA, se instalado) |
|---|---|---|
| Personagem / inimigo (`create_character`) | ficha pelo cérebro do Ignis, conceito pela Z-Image, 3D pela **Forja** no Blender, voz pela Chatterbox | 3D da imagem de conceito pelo **TRELLIS.2** (textura assada no Blender, sem o nvdiffrast) |
| Arma, objeto, malha de fora (`generate_3d`) | Forja: 7 armas e 9 objetos com colisão; limpeza de malha | 3D de qualquer imagem pelo TRELLIS.2 |
| Esqueleto (`create_skeleton`) | esqueleto padrão com os nomes do perfil humanoide da Godot | criaturas pelo **UniRig** |
| Animações (`generate_animation`, `retarget_animation`) | biblioteca: parado, andar, correr, pular, atacar, defender, esquivar, dano, morrer | movimento por texto pelo **HY-Motion** (com o aceite da Tencent) |
| Mundo (`generate_blockout`) | áreas da bíblia em anel, caminhos, colisão e pontos de nascimento | — |
| Efeitos e música (`generate_sfx`, `generate_music`) | síntese da Fornalha, música em laço sem emenda | — |
| Voz (`generate_voice`) | Chatterbox no Ignis (pt-BR) + curva da boca | — |
| Código e cenas (`generate_code`, `import_to_engine`) | projeto Godot/Erethea com jogador, inimigos, HUD e sons; cenas montadas pela engine | — |
| Teste (`run_test`) | o jogo roda sozinho: erros, FPS, polígonos, inimigos, capturas e vídeo | — |
| Pedido livre (`plan_request`) | regras para os pedidos comuns | plano pelo cérebro (Qwen3 no Ignis) |
| Fila (`queue_job`, `list_queue`, `cancel_job`) | agora ou à noite (23h–7h), uma por vez | — |
| Guia visual (`check_style`) | cores de cada asset contra a paleta da bíblia | — |

Tudo o que sai ganha **recibo de licença** (`ai/recibos.jsonl`) e entra no relatório de créditos.
Num projeto comercial, o roteador só usa o que deixa vender.

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

São 33 ferramentas: as da base (`get_status`, `create_project`, `update_project`, `choose_model`, `record_receipt`, `check_licenses`, `export_credits`…) e as de geração e teste da tabela acima. Peça em português, por exemplo: *"crie um inimigo novo, um orc com martelo, e teste no jogo"*.

## Baixar (versões de teste)
Ainda não há versão oficial (a venda é da Fase 5). Cada mudança gera instaladores de teste em
**[Actions → Instaladores](https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/instaladores.yml)**: abra a execução mais recente com ✓ e baixe em *Artifacts* (`fornalha-windows`, `fornalha-linux`).

## Para desenvolver
Requisitos: Rust estável e Node 22; para as gerações, Blender 5.2 e Godot 4.6 (ou a Erethea). No Linux, também
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
Gerações de verdade (como no CI), com o Blender e a Godot baixados por `scripts/baixar-ferramentas.sh`:
```bash
FORNALHA_TESTE_BLENDER=~/ferramentas/blender/blender FORNALHA_TESTE_GODOT=~/ferramentas/godot/godot cargo test -p fornalha-core --test forja --test engine --test geracao --test workers -- --test-threads 1
```
Teste do MCP com o SDK oficial (stdio e HTTP):
```bash
cargo build -p fornalha-cli && cd testes/mcp-e2e && npm ci && node teste.mjs ../../target/debug/fornalha-cli
```

### Estrutura
| Pasta | O que tem |
|---|---|
| `crates/fornalha-core` | Núcleo: bíblia, licenças e roteador, recibos, níveis, placa, gerações, fila, plano, guia visual, API e MCP |
| `crates/fornalha-core/blender` | A Forja: scripts do Blender (personagem, armas, mundo, rig, animações, textura assada) |
| `crates/fornalha-core/godot` | O código do jogo e o teste automático para a Godot e a Erethea |
| `crates/fornalha-core/workers` | Modelos de placa (TRELLIS.2, UniRig, HY-Motion) e o instalador |
| `crates/fornalha-core/manifest/modelos.json` | Catálogo de modelos com licença e a tabela dos 4 níveis |
| `crates/fornalha-cli` | Linha de comando: `mcp`, `servir`, `detectar`, `chamar`, `modelos`, `instalar-modelo` |
| `app/src-tauri` | Aplicativo (bandeja + janela em processo separado + `--mcp`) |
| `app/ui` | Janela em HTML/CSS/JS puro, em português |
| `testes/mcp-e2e` | Teste de ponta a ponta com o SDK oficial do MCP |

Documentos: [ESTADO.md](ESTADO.md) (situação, decisões e pedidos para o Ignis),
[TESTE_DO_CRIADOR.md](TESTE_DO_CRIADOR.md) (o teste na sua máquina), [AVISOS.md](AVISOS.md) (código de terceiros).

## Licença
Todos os direitos reservados (veja [LICENSE](LICENSE)). Partes vieram do Ignis, sob MIT ([AVISOS.md](AVISOS.md)).
