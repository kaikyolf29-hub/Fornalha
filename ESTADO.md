# ESTADO do projeto Fornalha

> Toda retomada começa por aqui. Atualizado antes de cada pausa.

## Situação (21/11/2026)
**Fases 0 a 4 implementadas e testadas sem placa de vídeo; gerações de verdade provadas no CI
do Windows e do Linux.** Falta o teste do criador na máquina dele (TESTE_DO_CRIADOR.md) e falta
provar, numa placa NVIDIA de verdade, os três modelos de placa (TRELLIS.2, UniRig, HY-Motion).
Fase 5 (venda e atualização privada) não começou: só quando o criador pedir.
O app é para **Windows e Linux** (nada específico do Matsu OS, a pedido do criador).

| Fase | O que entrega | Situação |
|---|---|---|
| 0 · Base | Bíblia, recibos, placa e 4 níveis, API local e MCP | pronta |
| 1 · Primeiro personagem | Conceito (Ignis), 3D com esqueleto e animações (Forja no Blender), engine | pronta sem placa; TRELLIS.2/UniRig ligados, falta prova em placa NVIDIA |
| 2 · Mundo, armas e estilo | Blockout pela bíblia, armas na mão, objetos com colisão, checagem do guia visual (cores) | pronta; checagem de forma/conteúdo espera o modelo de visão do Ignis |
| 3 · Áudio | Efeitos por evento, música por área em laço, dublagem pt-BR (Chatterbox no Ignis) e boca | pronta |
| 4 · Agente completo | 33 ferramentas no MCP, "crie um inimigo novo" testado na engine, pedido livre pelo cérebro, fila da noite | pronta |
| 5 · Venda | Trailer, chave de ativação, atualização privada | não começou (só quando o criador pedir) |

## Rodada de qualidade (Fornalha 3D, 21/11/2026, a pedido do criador)
Meta do criador: personagens, armaduras, armas, cenário e movimento no nível das referências
(templário, cavaleiro de placas, rosto realista, captura de movimento fluida tipo GTA/Resident Evil).
- **Pacotes de conteúdo CC0** (Máquina → Pacotes, ou `fornalha-cli baixar-pacote`): MakeHuman
  (malha base, formas, esqueleto de jogo, pele, olhos, cabelo), Quaternius Universal Animation
  Library 1 e 2 (89 animações de jogo) e ambientCG (texturas PBR e céus HDRI). Baixam **só no clique
  da pessoa**; o núcleo continua sem HTTPS de saída (o download é um script Python à parte).
- **Humano realista**: corpo e rosto do MakeHuman lidos por código próprio (o código do MPFB não roda;
  a sessão barrou executar extensão baixada e o caminho por dados é mais seguro), pele com SSS e poros
  no render, olhos, sobrancelhas, cílios, dentes, cabelo, esqueleto de jogo (nomes Unreal) e pesos.
- **Roupa medieval PBR**: cota de malha, sobreveste com cruz, cinto, botas, luvas, capa com pregas.
- **Armadura de placas** (`cavaleiro_placas`): placas rígidas por osso, superfície convexa sobre o
  corpo, borda chanfrada, lâminas com rebites (ombreiras, faldas, sapatos, dedos), elmo com fendas e
  respiros; espada longa com lâmina em losango e escudo de pipa com a cruz.
- **Movimento**: retarget de captura (Quaternius; também lê Mixamo e CMU em BVH) entre poses de descanso
  diferentes; 15 animações por personagem. No jogo: sequência de golpes com memória de comando, pique,
  no ar e aterrissar, **capa simulada por mola** (SpringBoneSimulator3D) e **ragdoll** na morte.
- **Render do jogo**: céu HDRI, AgX, SSAO/SSIL, SDFGI, névoa volumétrica e TAA (Forward+).
- **Janela**: nome exibido Fornalha 3D, pacotes em Máquina, visualizador 3D girável na Galeria.
- Provado aqui: personagem realista criado pelo MCP, montado na Godot 4.6.1 e testado (0 erros, o
  jogador andou ~12 m, inimigos derrotados caindo pela física, "pode vender").

Falta para chegar nas referências (próximas rodadas):
1. **Cenário**: já tem terreno com relevo (colisão acompanha), árvores (pinheiros e folhosas com casca),
   pedras, casas medievais (térreo de pedra, enxaimel, empena, telhado de telha, chaminé, janelas) e tudo
   em PBR com grama, terra, pedra, reboco, vigas e telha. Falta: castelo/muralha, interiores, objetos de
   rua (carroças, bancas), grama em tufos, água e uma vila com ruas em vez do anel atual.
2. **Armadura**: bordas viradas com rebites no peitoral, viseira trabalhada, desgaste/ferrugem nas
   bordas "assado" em textura (hoje a cor final só existe no render; o glTF leva a textura base).
3. **Rosto**: detalhe de pele (poros, rugas por idade) assado em mapa normal; cabelo melhor.
4. **Mais movimento**: 100STYLE (CC BY 4.0, 100 estilos de andar) e CMU (lutas), importar Mixamo baixado
   pela pessoa, pés firmes no chão (TwoBoneIK3D), mistura de locomoção por velocidade.
5. **Máximo com placa NVIDIA**: TRELLIS.2 / Step1X-3D (Apache 2.0) para peças únicas a partir da arte.
6. Futuro (criador): captura de movimento pelo Kinect ou por webcam.

## O que está pronto
- **Núcleo** (`crates/fornalha-core`):
  - `projeto`, `licencas` + `manifest/modelos.json`, `niveis`, `recibos`, `api`, `mcp` (Fase 0);
  - `externas`: acha e roda o **Blender**, a **Godot** e a **Erethea Engine** (caminho escolhido, variável de ambiente, pastas padrão do Windows e do Linux, Steam, PATH);
  - `forja` + `blender/*.py`: a **Forja** — personagem low-poly de 7 tipos com esqueleto padrão (nomes do perfil humanoide da Godot), pesos, arma na mão e 9 animações (parado, andar, correr, pular, atacar, defender, esquivar, dano, morrer); 7 armas e 9 objetos com colisão; mundo em blockout com 15 tipos de área, caminhos e pontos de nascimento; limpar malha de fora; esqueleto em malha de fora; copiar animações; recolorir pela paleta; **assar textura** (cor por vértice → textura, sem o nvdiffrast); **movimento SMPL** → animação no esqueleto padrão; prévia, folha de modelo e vídeo;
  - `engine` + `godot/*.gd`: projeto Godot/Erethea com o código do jogo (jogador em terceira pessoa, inimigo com perseguir/atacar/morrer, HUD, sons), cenas montadas pela própria engine, plugin de ponte no editor, `run_test` (o jogador anda, pula e ataca sozinho; erros, FPS, polígonos, capturas e vídeo); sem tela, roda sem janela;
  - `audio`: síntese de 14 efeitos com variações, compositor de música por situação com laço sem emenda, WAV normalizado e curva da boca;
  - `ignis`: cérebro (ficha e plano em JSON com `json_schema`), imagem (Z-Image Turbo) e voz (Chatterbox) do Ignis 0.4.0;
  - `geracao`: as gerações encadeadas, todas com recibo;
  - `workers` + `workers/*.py`: **modelos de placa** — TRELLIS.2 (imagem → 3D, cor tirada dos voxels e textura assada no Blender), UniRig (esqueleto de criatura), HY-Motion (texto → movimento), cada um num ambiente Python só dele, instalados pela janela ou pela linha de comando; sem placa ou sem instalar, a Fornalha usa a Forja, o esqueleto padrão e a biblioteca;
  - `fila`: **fila da noite** (agora ou das 23h às 7h, uma tarefa por vez, sobrevive a fechar o app);
  - `plano`: **pedido livre** → plano pelo cérebro (conferido contra o esquema de cada ferramenta) ou por regras com o Ignis fechado → fila;
  - `estilo`: **checagem do guia visual** — cores de cada png e glb contra a paleta da bíblia.
- **App** (`app/`, Tauri 2): visual próprio (grafite, cobre e brasa; fonte Archivo), estações Projeto, Forjar (moldes, pedido livre, fila), Galeria (prévias e guia visual), Testar, Licenças, Máquina (placa, programas, modelos de placa, níveis), Agentes e Ajustes; bandeja, janela em processo separado, instância única, `fornalha --mcp`.
- **CLI** (`crates/fornalha-cli`): `mcp`, `servir`, `detectar`, `chamar`, `ferramentas`, `modelos`, `instalar-modelo`.
- **CI**: `ci.yml` (fmt, clippy, testes, MCP com o SDK oficial e o job **Gerações de verdade** no Windows e no Linux, com Blender 5.2.4 e Godot 4.6.1 baixados e artefato com o projeto gerado) e `instaladores.yml`.

## Provado vs. falta provar
- **Provado no CI** (Windows Server e Ubuntu, sem placa):
  - run 44892635516 (commit b8a36cc), job "Gerações de verdade (Windows)": a Forja fez herói, orc, espada e mundo; a Godot 4.6.1 montou as cenas e rodou o jogo — jogador andou 8,17 m, o inimigo perseguiu, **0 erros**, 5 capturas e vídeo; `check_licenses` → pode vender; artefato `geracoes-Windows` com 130 arquivos. O mesmo no Linux;
  - run 44908546429 (commit f2c14c3), tudo verde: os testes dos **workers de placa** de ponta a ponta com modelos de mentira de mesma interface (TRELLIS.2 → textura assada → recibo; HY-Motion → animação nova; verificação "sem nvdiffrast" liberando o TRELLIS.2 em projeto comercial);
  - run 44910393345 (commit 0f6b23f), tudo verde: fila da noite, pedido livre (plano por regras e conferência do plano do cérebro), checagem do guia visual e o pedido livre gerando de verdade pela fila (goblin, lança e música da masmorra) no Windows e no Linux;
  - instaladores (NSIS no Windows; .deb, .rpm e AppImage no Linux) instalados e abertos a cada commit.
- **Provado aqui** (Linux, sem placa): o Ignis 0.4.0 de verdade — voz pela Chatterbox, ficha pelo Qwen3, imagem de conceito pela Z-Image no processador, e o **plano de um pedido livre feito pelo Qwen3 0.6B** (orc → música → montar → testar, com argumentos conferidos); o jogo com janela numa tela virtual; o painel da janela.
- **Falta provar** (só na máquina do criador ou numa placa NVIDIA):
  - TRELLIS.2, UniRig e HY-Motion **de verdade** (instalação, a geração, a orientação da malha do TRELLIS.2, o formato de saída do HY-Motion e se o TRELLIS.2 roda com o nvdiffrast substituído);
  - Erethea Engine de verdade (o CI testa a Godot 4.6.1; a Fornalha procura a Erethea e usa a mesma linha de comando);
  - detecção da RX 580 e da placa nova, bandeja e Aero Snap do Windows 11, memória em repouso, Claude Code do criador.

## Decisões
- Do plano (20/11): nome Fornalha; Windows primeiro, Linux também; repositório público sem licença aberta; engine Godot ou **Erethea Engine** (opção na bíblia e em Máquina).
- Fase 0: porta 11480; projeto nasce comercial; recibos em JSON Lines; aceite de licença e receita só pela janela; nomes das ferramentas em inglês, textos em português.
- Fases 1–4 (21/11):
  - **Forja** no Blender como gerador 3D que roda em qualquer computador (o plano previa só modelos de placa; sem a Forja, a RX 580 não teria 3D);
  - biblioteca de animações **procedural** da Fornalha (no lugar das capturas da CMU, que não entraram);
  - efeitos e música por **síntese própria** quando não há modelo de áudio liberado;
  - **TRELLIS.2 sem o nvdiffrast**: a cor sai dos voxels e a textura é assada no Blender; o nvdiffrast recebe um substituto vazio; em projeto comercial o TRELLIS.2 só entra depois que a verificação da instalação comprova, na máquina, que ele não foi carregado;
  - UniRig só para criaturas que não são humanoides (humanoide usa o esqueleto padrão, que recebe as animações);
  - HY-Motion precisa de CUDA e do aceite da licença da Tencent na janela;
  - fila da noite das 23h às 7h (muda em Ajustes/config), uma tarefa por vez;
  - plano do cérebro sempre conferido: argumento que não existe sai, o obrigatório que falta vem das regras, arquivo que não existe sai, e o que as regras acham no pedido e o cérebro esqueceu entra (ordem: gerar, montar, testar);
  - checagem do guia visual por cor (ΔE em Lab, 40% dos pixels coloridos na paleta); forma e conteúdo esperam o modelo de visão.

## Achado: TRELLIS.2 e o nvdiffrast
Os pesos do TRELLIS.2 são MIT, mas a textura oficial usa o **nvdiffrast** (licença só de pesquisa).
A Fornalha resolve sem ele (veja Decisões) e o catálogo continua bloqueando o TRELLIS.2 em projeto
comercial até a verificação passar na máquina. Outras notas: ACE-Step 1.5 é MIT, mas o repositório
dos pesos ainda não traz o LICENSE; HY-Motion e Hunyuan3D têm a regra de território da Tencent
(não vale na União Europeia, no Reino Unido e na Coreia do Sul).

## Decisões que são do criador
- **Rede**: o CLAUDE.md diz que a Fornalha só fala com 127.0.0.1. Os pacotes CC0 e os modelos de placa
  baixam de sites de fora **só quando você clica** (nada é enviado). Se preferir, eles podem ir dentro
  do instalador (fica ~500 MB maior).
- **Nome do instalador**: a janela e a bandeja já dizem Fornalha 3D; o instalador e a pasta continuam
  "Fornalha" para não mudar caminhos antes da Fase 5.

## Pedidos para o Ignis
Já entregues no Ignis 0.4.0 e usados pela Fornalha: voz comercial (Chatterbox), imagem (Z-Image
Turbo), reserva da placa, `uso_comercial` nos modelos, aceleradores em `/motor/estado` e
`response_format` com `json_schema`. Continuam valendo:
1. **Cabeçalho do WAV da voz:** o `/v1/audio/speech` devolve o WAV com o cabeçalho de stream (tamanhos
   do RIFF e do `data` errados). A importação da Godot trava com esse arquivo. A Fornalha já reescreve
   o cabeçalho, mas o certo é o Ignis gravar os tamanhos reais quando a resposta não é streaming.
2. **Modelo de visão leve** (pedido 7 do plano): para a checagem do guia visual olhar forma e conteúdo
   (o "evitar" da bíblia), não só as cores.
3. **Dois modelos carregados** (pedido 8 do plano): o cérebro e a imagem juntos, para o pedido livre
   não descarregar um para usar o outro.

## Notas para a Erethea Engine
A Fornalha trata a Erethea como a Godot: procura `erethea.console.exe`/`erethea.exe` em
`%LOCALAPPDATA%\Erethea` (ou o caminho escolhido em Máquina, ou `FORNALHA_ERETHEA`) e usa
`--headless --import`, `--script`, `--write-movie` e o plugin de ponte do editor. Se a Erethea mudar
algum desses, avise aqui.

## Próximo passo
1. Criador: rodar o TESTE_DO_CRIADOR.md no Windows (e, se quiser, no Linux).
2. Com a placa NVIDIA nova: instalar os modelos de placa em Máquina e rodar a parte 9 do teste.
3. Fase 5 só quando o criador pedir.
