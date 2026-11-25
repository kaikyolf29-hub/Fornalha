# ESTADO do projeto Fornalha

> Toda retomada começa por aqui. Atualizado antes de cada pausa.

## Rumo novo (25/11/2026, combinado com o criador)
O trabalho segue o **[docs/PLANO_3_ETAPAS.md](docs/PLANO_3_ETAPAS.md)**: a Fornalha 3D é a bancada
da IA (Claude Code, Codex), e a **Erethea Engine é a principal**. A Fornalha continua fazendo tudo o
que faz hoje (conceito, 3D, APIs, dublagem, boca e olhos, música, efeitos, organização do projeto) e
ganha bancadas com imagens e medidas: 1) movimento para qualquer corpo e roupa por cima; 2) cabelo e
mapa; 3) guia para a IA dentro de cada projeto de jogo e a prova com um jogo pequeno completo.
Pendente da rodada anterior: a projeção do conceito na malha (`fc_projetar.py`) foi feita numa sessão
de outra conta e não chegou ao repositório até 25/11.

### Etapa 1 — bancada de movimento (25/11, em andamento)
**Feito e provado aqui** (Linux, Blender 5.2.4, sem placa; testes `cargo test --test forja`):
- **Conferência do movimento** (`fc_conferir.py`, MCP `check_motion`): por animação mede torção de osso
  além do natural (braço virado), cotovelo/joelho ao contrário ou de lado, tranco (osso que vira de um
  quadro para o outro), corpo sólido (cápsulas por osso: braço no tronco, pernas se cruzando), pé
  escorregando (acha sozinho a velocidade do chão: captura no lugar ou parada), corpo abaixo do chão ou
  flutuando. Vale para o esqueleto de jogo, o da Forja e as criaturas. Devolve números, o pior quadro e
  imagem com os ossos ruins em vermelho.
- **Correção automática** (`fc_corrigir.py`), em até 3 rodadas: trancos, dobradiças endireitadas (o osso
  de cima gira no próprio eixo, sem salto entre quadros), torção da mão passada para o antebraço com
  limite, torção limitada, membro afastado do corpo, **pé travado no chão por IK** (o ponto que toca o
  chão; o pé pode girar na ponta) e quadril assentado. Roda sozinha no fim do `create_character`
  (humano, malha da IA, criaturas e dragão): o templário sai com as 15 animações aprovadas (antes: 13 de
  15 reprovadas na régua nova; rolamento e morte entravam ~70 cm no chão). Custa ~20 s a mais.
- **Banco de movimento** (`fc_banco.py`, MCP `list_motions`, `apply_motion`, `import_motion`):
  Quaternius (89 clipes), **ACCAD** (pacote novo `accad`, 299 BVH, CC BY 3.0, com socos, chutes,
  bloqueios, esquivas, passos), **100STYLE** (pacote `100style`, 1,5 GB, CC BY 4.0) e o que a pessoa
  trouxer (Mixamo, CMU, própria) em `Motion/<fonte>/`; etiquetas em português; catálogo guardado.
  `apply_motion`: retarget **por pose** (a fonte é posta na pose de descanso do alvo osso por osso; BVH de
  descanso esquisito é calibrado pelo quadro mais parecido com o descanso do alvo — acabou o pescoço
  torcido 180° do ACCAD), começa de frente e no centro, `ciclo` acha o laço numa tomada longa, `no_lugar`,
  recorte e velocidade; depois confere e corrige. Provado: chute circular, soco e corrida do ACCAD no
  templário, aprovados, com vídeo.
- Licenças conferidas nas páginas: ACCAD CC BY 3.0 (crédito "Open Motion Project by ACCAD/The Ohio State
  University"), 100STYLE CC BY 4.0 (crédito "The 100STYLE Dataset - Ian Mason"); créditos voltam no
  resultado do `apply_motion`. **Mixamo:** o criador autorizou em 25/11 ("Mixamo pode usar"); a página da
  Adobe recusou a leitura automática, então entra como `captura-mixamo` com aceite da pessoa pela janela
  (regra do CLAUDE.md), arquivos trazidos com a conta Adobe dela (`import_motion`).
- **Tronco (25/11, achado pelo criador no vídeo da corrida):** a corrida do ACCAD saía com o peito
  girado e a barriga torcida e a régua tinha aprovado (ela não media o tronco). Causas: (1) o quadril era
  alinhado pela direção quadril→coluna, que no MakeHuman já é inclinada 24°: todo personagem saía com o
  quadril girado (Quaternius também); agora é pela vertical; (2) o BVH era calibrado por um quadro do
  próprio clipe (o corredor inclinado virava o "normal"); agora pela pose em pé da mesma sessão de
  captura (ACCAD `Male2_A1_Stand`). A conferência ganhou a medida do tronco (giro do peito em relação ao
  quadril até 55°, dobra até 75°): a corrida foi de 86° de dobra para 17°. **Regra:** "aprovado" quer
  dizer que a régua não achou o que ela mede; não quer dizer pronto. Pronto só depois de olhar o vídeo
  (e, no fim, o teste do criador).
- **Esqueleto editado pela IA** (`fc_esqueleto.py`, MCP `show_skeleton`, `edit_skeleton`): imagem
  (frente, lado, cima) com a malha clara e os ossos coloridos e numerados, lista com avisos (osso que não
  mexe nada, longe do corpo, lados diferentes); mudanças mover/criar/apagar/renomear/pai/espelhar pelo
  nome ou número; pesos refeitos só perto do que mudou. Ossos `mola_<grupo>_1..N` viram mola na
  Godot/Erethea (`movimento.gd`), com rigidez por grupo (cabelo, cauda, asa).
- **Roupa por cima** (`fc_vestir.py`, MCP `dress_character`): a roupa/armadura recebe os pesos do corpo
  que já se mexe; peça pequena de um osso só fica rígida nesse osso (teste: placa do peito no `Chest`,
  braçadeira no `LeftLowerArm`), pano grande dobra; a conferência roda com a roupa.
- **Estação Movimento na janela**: conferir e corrigir, ver o esqueleto, banco com etiquetas/licenças e
  "Pôr no personagem", vestir.
- **Visual novo da janela (25/11, pedido do criador):** clássico/premium — Cormorant Garamond (OFL, dentro
  do app) nos títulos e números, versalete nos rótulos, latão nos filetes, brasa só na ação principal;
  temas Forja (escuro), Pergaminho (claro) e **Preto e branco** (escuro ou claro pelo sistema), em
  Ajustes → Visual. Só aparência: os ids e o app.js são os mesmos.
- **Erethea é a engine padrão** dos projetos novos (decisão do criador); sem ela instalada, a Fornalha usa
  a Godot e avisa. O CI da Fornalha ainda testa na Godot 4.6.1; a Erethea (fork da 4.8 beta) está sendo
  compilada aqui para rodar o mesmo teste nela.
- **Provado na Erethea (25/11):** a Erethea do `main` (commit c4993bf, base Godot 4.8-beta4) foi compilada
  aqui (Linux, editor, sem placa: `erethea.linuxbsd.editor.x86_64`, "Erethea Engine v4.8.beta"). Com
  `FORNALHA_TESTE_ERETHEA`, os testes de engine da Fornalha passam nela (6 de 6) e o templário realista
  (MakeHuman, captura, IK dos pés, olhar, golpe andando) roda: andou 7,77 m, pés parados ≤ 1,3 cm, 0 erros
  e 0 avisos da engine. O `run_test` na Erethea agora roda os dois testes (o `--agent-test` dela, com
  desempenho e avisos, e o da Fornalha, com o jogador andando e o inimigo reagindo) e junta. O aviso da
  4.8 sobre ponto do BlendSpace sem nome foi corrigido (`_ponto_no_blend`, que continua valendo na 4.6).
  O CI da Fornalha continua na Godot 4.6.1 (sem build da Erethea para baixar): a prova na Erethea é daqui.
Falta na Etapa 1: o CI das gerações verde no Windows e no Linux, e o teste no PC do criador.

### Etapa 2 — começo (25/11)
- **Cabelo médio e comprido:** experimento com o caminho fio a fio + cards (opção `cabelo_em_cards` na
  ficha; o padrão continua o cabelo do pacote MakeHuman). Feito: assentamento dos fios que pendem
  (gravidade, comprimento preservado, liso, colisão com cabeça/pescoço/ombros por campo de distância).
  **Ainda feio** (render conferido): os fios longos andam colados no crânio até o queixo (parece puxado
  para trás), poucos caem pela nuca, cards soltos espetados na silhueta, linha da testa serrilhada e uma
  mancha clara no alto. Próximo: raiz descolando com volume, queda começando na coroa, orientação dos
  cards pela superfície do cabelo (não da cabeça), máscara da testa em resolução maior, e as medidas da
  bancada (couro aparecendo, fio atravessando) antes de virar padrão.

## Situação (21/11/2026, fim da tarde)
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
- **Armadura, segunda passada** (commit d9165a5): contorno das placas alisado e **borda virada**;
  placas "moldadas" (forma lisa de metal batido, sem anatomia); **elmo armet** (viseira em bico,
  fenda, respiros, pivôs) e **elmo de barril**; a armadura vira **uma malha com atlas** e o desgaste
  (quinas polidas, fuligem, ferrugem, oclusão entre placas) é **assado** em cor, rugosidade e normal,
  então o glb e a engine recebem o mesmo que o render. Estilo **templário** (cota inteira, sobreveste
  longa com cruz pátea costurada, cintos com fivelas de latão, placas nos membros, manto). Câmera por
  cima do ombro. Provado aqui: o templário criado pelo MCP rodou na Godot (passou, 0 erros).
- **Avaliação honesta do criador (21/11):** ainda está **muito abaixo** das referências AAA (templário
  branco, rosto Snappers, velho). Código sozinho no Blender não chega lá; o caminho combinado é:
  1. **por etapas**, cada parte levada ao máximo e comparada lado a lado com a referência antes da
     próxima: rosto → corpo e pele → cabelo → armadura peça por peça → objetos → cenário/castelo;
  2. peças e texturas de alta qualidade **com licença comercial** (o criador autorizou baixar; sem conta
     no Sketchfab, então só fontes sem login);
  3. IA de 3D local quando houver placa que rode (hoje o criador tem RX 580; a NVIDIA ainda não foi
     comprada; também vai testar numa RX 6600 e pensa numa RX 9060 XT 16 GB). Regra do criador:
     "quanto mais forte a máquina, melhor funciona", mas tem de funcionar para todo mundo.

Falta para chegar nas referências (próximas rodadas):
1. **Cenário**: já tem terreno com relevo (colisão acompanha), árvores (pinheiros e folhosas com casca),
   pedras, casas medievais (térreo de pedra, enxaimel, empena, telhado de telha, chaminé, janelas) e tudo
   em PBR com grama, terra, pedra, reboco, vigas e telha. Falta: castelo/muralha, interiores, objetos de
   rua (carroças, bancas), grama em tufos, água e uma vila com ruas em vez do anel atual.
2. **Armadura**: feito na segunda passada (borda virada, moldagem, elmos, atlas com desgaste). Falta o
   nível das referências: gravações, couro e costuras, ombreira de verdade (hoje parece "inflada"),
   manoplas articuladas, sobreveste com caimento de pano de verdade e capuz.
3. **Rosto** (etapa 1 do plano por etapas): detalhe de pele (poros, rugas por idade) assado em mapa
   normal 4K, pele com variação de cor, olhos, barba rala; cabelo melhor.
4. **Mais movimento**: a base saiu na etapa 1.6 (veja "Movimento base" abaixo). Falta: 100STYLE
   (CC BY 4.0, 100 estilos de andar) e CMU (lutas), importar Mixamo baixado pela pessoa, root motion,
   strafe (BlendSpace2D), travamento do pé pela curva de contato.
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

## Pesquisa de modelos e bibliotecas (21/11/2026)
Feita por um agente lendo as páginas de licença (nada baixado nem executado). Pontos que valem:
- **Corrigido:** o pipeline.json oficial do TRELLIS.2 pede o removedor de fundo **RMBG-2.0 (CC BY-NC,
  não comercial)**; o worker agora força o **BiRefNet (MIT)** e recusa o outro (commit 181708b).
  O DINOv3 que o TRELLIS.2 usa permite uso comercial, mas pede aceite da própria pessoa no Hugging
  Face e o crédito "Built with DINOv3".
- **3D local (só CUDA hoje):** TRELLIS.2 e Pixal3D (MIT, até 1536³ com PBR 4K; oficial pede 24 GB);
  Direct3D-S2, Hi3DGen e TripoSG (MIT, só forma); Hunyuan3D-2.1 (Tencent: não vale na UE, Reino Unido
  e Coreia do Sul); Step1X-3D e MV-Adapter pedem nvdiffrast. Nenhum aberto chega ao Meshy "Flagship".
- **Rig e movimento:** SkinTokens (MIT, 14 GB), Puppeteer (Apache 2.0); **Kimodo-SOMA-RP** da NVIDIA
  (licença aberta comercial, cobre combate, < 3 GB com o texto no processador; falta conferir o
  codificador de texto).
- **Captura de movimento comercial:** CMU, 100STYLE (CC BY 4.0), **ACCAD** (CC BY 3.0, artes marciais),
  Mesh2Motion (CC0), Quaternius (CC0). **Não podem:** Bandai Namco, LAFAN1, ZEGGS, Motorica, BONES-SEED.
- **Bibliotecas:** Poly Haven (CC0; API liberada para uso comercial com crédito "Powered by Poly Haven"
  e User-Agent próprio), ambientCG (CC0), Megascans no Fab (grátis de novo desde 05/11/2026, usável
  fora da Unreal, mas sem redistribuir e pela conta da pessoa).
- **Rosto e corpo:** MHR da Meta (Apache 2.0, 72 expressões FACS), FLAME 2023 Open (CC BY 4.0), ICT
  FaceKit light (MIT), Anny (Apache 2.0), cabeça escaneada Lee Perry-Smith (CC BY 3.0).
- **Nuvem:** Meshy 7.1 (API a partir de US$ 20/mês; no pago o modelo é do cliente), Rodin Gen-2.5
  (até 10M de faces; texto da licença tem um campo vazio). Depende da decisão abaixo.

## Plano em 2 etapas (22/11/2026)
Tudo o que falta (Plano 1, as 3 etapas antigas, a bíblia técnica, o complemento técnico de corpo/
rosto/cabelo/criaturas/teste bruto e os pedidos da Erethea) está em
[docs/PLANO_2_ETAPAS.md](docs/PLANO_2_ETAPAS.md) — a seção "Onde estamos" diz o que está feito, o que
está em andamento e a ordem. Régua técnica: [docs/BIBLIA_TECNICA_AAA.md](docs/BIBLIA_TECNICA_AAA.md).
- **Etapa 1** — Fornalha 3D completa e pronta para o Teste de Fogo na RX 580 (Windows). Em andamento.
  Feito: look-dev/QA, pele 4K, cabelo curto em cards, pano simulado, movimento base (juntado do
  agente), ComfyUI (conector, instalador pela placa, teste real no processador do CI), pedidos 1–7 da
  Erethea, dragão com esqueleto próprio, suíte de Teste Bruto (MCP `run_brute_test`, CLI
  `teste-bruto`, botão Máquina → Teste de Fogo), reserva da placa no Ignis antes do ComfyUI/workers.
  Também: Teste Bruto verde no CI (Windows e Linux), folha de modelo pelo motor de imagem, pano com
  desgaste assado (lama na barra, pingos, sujeira nas dobras, bainha), cabelo mais denso.
  **RX 580 pelo Vulkan (22/11):** o ComfyUI tirou o DirectML em 11/11/2026 (commit c5751c8, "o último
  PyTorch com DirectML é o 2.5") e o teste do CI acusou ("unrecognized arguments: --directml"). A RX 580
  e as outras AMD/Intel sem CUDA nem ROCm agora geram imagem pelo **stable-diffusion.cpp** (MIT) com
  Vulkan, com os mesmos arquivos GGUF do Z-Image Turbo: Máquina → Motor de imagem → Instalar baixa o
  executável (versão fixa master-1045-6225bf8, 30 MB, conferida pelo SHA-256) e os modelos; a Fornalha
  chama o `sd-cli` na hora de gerar (com a placa reservada no Ignis e VAE em blocos em 8 GB). Provado:
  teste com executável falso (argumentos, recibo `z-image-turbo-gguf-vulkan`, folha larga) e o
  executável de verdade no CI Linux (instalado pelo instalador da Fornalha, gerou o templário em 256 px
  em 101 s — no processador: o sd.cpp não usa o Vulkan por software do Mesa) e no CI Windows com o
  mesmo executável que vai para a RX 580 (sem placa, no processador): templário, dragão, castelo e
  folha de modelo de 3 vistas em 512 px, ~14–16 min cada (metade disso lendo os 6 GB de modelo do
  disco a cada imagem — próximo ganho: deixar o `sd-server` aberto entre as imagens). Falta provar: o
  Vulkan numa placa de verdade, a RX 580 (TESTE_DO_CRIADOR 0b).
  **Preparar a máquina (22/11):** Máquina → Programas → Baixar traz o Blender 5.2.4 e a Godot 4.6.1
  para `<dados>/ferramentas` (curl e tar do sistema — no Windows os de System32 —, soma publicada
  conferida: SHA-256 do Blender, SHA-512 da Godot), `fornalha-cli baixar-programa`, e o CI de gerações
  passou a usar esse botão em vez do script. Sem Python no sistema, os downloads de pacotes e do motor
  Vulkan usam o Python que vem dentro do Blender. Provado aqui: download real dos dois no Linux.
  **Zumbi realista (22/11):** tipo próprio "zumbi" (antes virava o esqueleto da Forja) no caminho do
  humano MakeHuman: pele de morto assada (pálida e acinzentada puxando para o verde, veias só em
  algumas regiões, manchas de decomposição e hematomas, olheiras fundas, lábios roxos, sangue
  escorrendo do canto da boca em fios verticais e mordidas abertas com relevo), olhos leitosos com
  vestígio de íris, túnica de linho encardida até a coxa (mais folgada, sem marcar o peito) e calça
  escura com lama subindo, encardido e sangue seco, botas alisadas (antes copiavam os dedos), e as
  animações de zumbi da biblioteca CC0 no lugar de parado/andar/atacar. Entrou como 3º caso do Teste
  Bruto (agora 4 casos), que também passou a conferir que a tela do jogo mostra a cena (variação de
  brilho das capturas). Provado aqui: caso zumbi de ponta a ponta com o jogo na Godot.
  **Mudança de rumo (22/11, pedido do criador):** o 3D feito só no Blender (dragão, personagens)
  ficou abaixo das referências; as imagens do motor de IA estão no nível certo. O 3D passa a sair da
  IA: TRELLIS.2 nos nós nativos do ComfyUI (PyTorch puro, roda até no processador), a partir da
  imagem do conceito e da folha de modelo, por partes (cabeça em close, depois o corpo), e o Blender
  fica com rig, animação e malha de jogo. **O criador aceitou a licença do DINOv3 (Meta) para os
  testes no CI em 22/11/2026** (pela pergunta no chat); no PC dele o aceite é pela janela. A
  Fornalha converte os fluxos oficiais do ComfyUI (formato da interface) para o formato da API com a
  lista de nós do próprio ComfyUI (`comfyui_ui.rs`). Página ao vivo do que falta:
  https://claude.ai/artifact/MGUnTUeKzEvVzYp5TJDLFY.
  **Provado (23/11):** o TRELLIS.2 no processador do CI gerou o templário (200 mil triângulos com
  textura) em 2,5 h, muito parecido com o conceito; a malha recebe o esqueleto de jogo (`fc_rig_ia`:
  juntas pelas proporções medidas na malha, pernas pelos pés, pesos por regiões — mão só no braço,
  capa e saia no quadril com mistura gradual) e a mesma captura de movimento do humano (o criador
  aprovou o vídeo de movimento). create_character usa esse caminho quando o 3D pela IA está
  instalado e aceito (ou a API da Meshy ligada). Olhos e pálpebras do rig do MakeHuman no humano
  (piscar e olhar testados no render) e o modificador "Rosto" na Godot (piscar, olhadas, boca pela
  curva da fala). API da Meshy pronta (desligada por padrão; chave e liga/desliga na janela; teste com
  servidor falso). **Provado (23/11, CI no processador):** o templário da referência do criador
  (conceito pelo motor de imagem → TRELLIS.2 em 3,4 h: elmo, cota, cruz preta na frente e na barra,
  cintos vermelhos, ombreiras, capa longa, espada na bainha) e o dragão (1,4 h: serpe vermelha de asas
  abertas, chifres, cauda enrolada). Os dois ganharam esqueleto e vídeo aqui (enviados ao criador): o templário com o
  esqueleto de jogo e a captura do humano; o dragão com `fc_rig_criatura` (pés pela fatia do chão,
  raiz da asa onde a membrana encosta no corpo, pulso no topo da asa, dedos nos picos mais longe do
  pulso, focinho, topo do crânio, cauda pelas fatias de baixo; serpe ou quadrúpede detectado pelos
  pés; pesos por regiões) e as animações do dragão da Fornalha (bater de asas centrado na pose da
  malha). create_character faz o dragão pela IA quando o 3D pela IA está pronto; senão, a Forja de
  criaturas. Tripo e Rodin prontas como a Meshy. O download do Blender tenta os espelhos oficiais
  (Berkeley, NLUUG) quando o site principal recusa a máquina de nuvem (403 no CI de 23/11); a soma
  SHA-256 é conferida igual.
  **Por partes (23/11):** a cabeça é recortada do conceito do corpo (`partes.rs`: figura pelo fundo
  liso, fundo de cada linha pelas bordas), refinada em close pelo Z-Image (imagem → imagem, denoise
  0,5: mesmo desenho, mais detalhe), vira malha própria no TRELLIS.2 e entra no lugar da cabeça do
  corpo antes do esqueleto (`fc_partes`: escala pela altura do recorte, posição pelo alto da cabeça,
  corte no pescoço). Testado aqui com uma cabeça de escala trocada (a troca acerta sozinha). No CI
  (processador): o recorte e o refino saíram certos (mesmo elmo, mais detalhe no metal, 54 min), mas a
  malha da cabeça estourou as 5h50 do CI (a textura leva ~29 min por passo com a grade cheia). Por isso
  create_character só faz a cabeça por partes com placa (CUDA/ROCm), nos níveis Qualidade e Máximo.
  O pedido com "capuz por cima do elmo" foi reforçado e o motor de imagem ainda põe o capuz caído
  atrás (limite do Z-Image com esse pedido). A arma na malha da IA gira em volta do eixo da mão para a lâmina
  apontar para a frente no parado e no andar.
  **Mais (23/11):** saia pela malha (a barra é achada onde o pano liga as pernas na frente; entre a
  barra e o quadril o pano fica no quadril e a parte de baixo segue as coxas/canelas aos poucos); o
  alisamento dos pesos agora roda (antes falhava calado: o operador pede o modo de pintura de pesos);
  mapa de normais da malha alta assado na leve (malha de jogo); capa com três ossos e mola na Godot
  (SpringBoneSimulator3D com colisão nas pernas, testado sem tela: parada mexe 8 mm, andando fica até
  43 cm para trás e volta); janela com o conceito de corpo inteiro para aceitar ou refazer antes do 3D
  (create_character parar_no_conceito / refazer_conceito); escudo erguido no parado de quem tem escudo.
  Duas mãos no cabo ficou de fora: a captura CC0 só tem golpes de uma mão (precisa de captura própria).
  **Mapa (23/11):** a grama do chão saía branca no jogo (a 1ª cor da paleta do projeto, o creme das
  paredes, tingia a grama): agora a grama e as folhas só pegam da paleta uma cor que seja verde, e
  chão/rocha/casca guardam a cor da foto (tom leve). Chão com cor por vértice (terra batida nos
  caminhos e no largo, grama seca em manchas, baixadas mais escuras) e tufos de grama com vento ao abrir
  o jogo (MultiMesh por blocos de 18 m, some a 48 m). Testado na Godot 4.6.1 (capturas).
  **Movimento para qualquer personagem (24/11, pedido do criador: "tem que funcionar para todos"):**
  o personagem humanoide da IA agora usa o MESMO esqueleto do humano do vídeo aprovado (com dedos):
  `fc_molde` encaixa um corpo-molde do MakeHuman nas juntas medidas na malha e passa os pesos pela
  superfície (com regras de região: manopla justa, capa e saia fora dos braços e pernas, elmo inteiro na
  cabeça). Achado e corrigido: a mão da malha da IA caía na regra da saia (ficava presa no quadril e a
  espada "andava sozinha"). Criaturas de qualquer corpo (`fc_rig_generico`): patas achadas pelos pés e
  seguidas na malha, passada com IK e fases pelo número de patas, coluna e cauda em onda, bote, dano e
  morte; o dragão da IA anda com a mesma passada. create_character aceita `imagem` (PNG pronto, do
  Gemini ou de onde for; vira o 3D sem ser refeito) e `corpo` (auto, humanoide, alado, quadrupede,
  aranha, inseto, serpente). Em prova no CI: fera de quatro patas e aranha gigante pela IA.
  **Braço pelo volume da malha (`fc_eixo`, 24/11):** a malha da IA vem partida nas costuras de textura
  e com normais trocadas; agora ela vira voxels pela paridade dos raios (sem depender de normal), com
  campo de distância até a superfície. O braço é seguido pelo cume desse campo do ombro à ponta da mão
  (antes uma linha reta até a "ponta" das fatias, que no cavaleiro de referência caía na bainha
  pendurada: o osso da mão ficava 10 cm atrás da manopla e o pano ia junto). O volume é dividido entre
  os ossos por divisor de águas (a manopla e a sobreveste encostadas se separam no vale entre elas) e o
  braço fica rígido por segmento, com transição curta no cotovelo e no pulso. Saia: a faixa abaixo da
  barra (que seguia a canela e virava um "lençol" na corrida) entrou na saia, e um osso "saia" gravado em
  cada ação segue o quadril mas fica de pé. **Fera de quatro patas pela IA** (CI, 4,7 h no processador):
  esqueleto achado sozinho, anda, corre e morde (vídeo enviado). O TRELLIS marcou a fera toda como metal
  (o pelo saía prata) e clareou o pelo: o mapa de metal todo em 1 é descartado e a luminância da textura
  é casada com a do conceito (só quando destoa; cores fortes ficam). A aranha passou do tempo do CI no
  processador (só com placa). Falta: projetar o conceito na malha (os tufos da juba ainda saem claros),
  mola da saia na Godot, qualidade da passada da fera.
  Próximo: vídeos do cavaleiro, da fera, da aranha e do dragão; mapa; cabelo; luta.
- **Etapa 2** — depois do Teste de Fogo: mundo, combate, todos os estilos, placas fortes.
Decisões do criador em 22/11: teto RE4 Remake / Elden Ring / Tales of Fantasy (pode levar horas);
foco no Windows; o trabalho segue sozinho entre um limite de uso e outro.

## Pedidos da Erethea para a Fornalha (22/11/2026)
1–7 feitos (commit "Pedidos da Erethea"): `<situacao>.musica.json`; `Sons.tocar_musica(situacao)` com o
grupo `erethea_musica`; `boca.json` com `personagem` e `texto` e `Sons.falar(personagem, arquivo)`;
mandíbula `jaw` e `"boca": {"osso": "jaw", "eixo_modelo": [1,0,0], "graus_aberta": 20}` no
`<id>.forja.json`; campo opcional `acustica` na área; WebSocket `/fornalha/ponte/ws` (e `websocket` no
GET da ponte; com `monta_cenas` a Fornalha não roda o montar.gd); `--agent-test` no run_test (saída 2
cai no teste da Fornalha). Falta o 8 (prévia LibGodot na Galeria), quando a Erethea tiver.
Personagens da Forja simples (não MakeHuman) ainda saem sem mandíbula.

## Movimento base (etapa 1.6, 22/11/2026)
Código novo em `crates/fornalha-core/godot/movimento.gd` (entra no projeto pela lista de scripts e é
usado pelo jogador e pelo inimigo; o caminho antigo por nome fica para modelo sem esqueleto conhecido).
- **Locomoção por AnimationTree feito em código:** BlendSpace1D pela velocidade real (parado → andar →
  correr → pique). A velocidade natural de cada ciclo é **medida nos pés** da própria animação (o ponto
  da sola que está no chão corre para trás na velocidade do corpo): no templário, andar 1,17 m/s,
  correr 6,35 m/s, pique 9,79 m/s; no low-poly da Forja, andar 1,23 e correr 3,02. Os ciclos ficam na
  mesma fase (linha do tempo normalizada, começando com o pé esquerdo na frente) e o ritmo é velocidade
  ÷ distância do ciclo, então a passada não patina. O som de passo sai do ciclo. O corpo ganhou
  aceleração e frenagem (inércia).
- **Camadas:** golpes e defesa da cintura para cima (filtro de ossos a partir da coluna), com as pernas
  seguindo o golpe só quando parado (atacar andando funciona); ações de corpo inteiro (pular, esquivar,
  dano, aterrissar) por cima, com fade; sem ragdoll, a morte fica no estado "morto".
- **Pés no chão:** TwoBoneIK3D (classe da Godot 4.6) por perna, entre dois SkeletonModifier3D próprios:
  raios no calcanhar e na ponta, rampa × degrau (a diferença de altura que a inclinação não explica é
  degrau), tornozelo girado para a normal, pelve descendo pela diferença; liga parado ou andando devagar
  e desliga suave no ar, na esquiva e na morte.
- **Olhar:** LookAtModifier3D na cabeça (o pescoço só entra se o eixo dele for vertical; o do MakeHuman é
  inclinado e entortava a cabeça), seguindo a câmera no jogador e o jogador no inimigo, limite de ±65°,
  volta para a frente quando o alvo fica atrás do corpo.
- **Erethea:** IK e olhar são criados pelo nome (ClassDB); numa engine sem essas classes o jogo roda com a
  locomoção e as camadas, sem IK nem olhar (não provado: falta a Erethea de verdade).
- **Provado aqui** (Linux, Godot 4.6.1, renderizador de compatibilidade, sem placa):
  - banco de testes com o templário realista: chão plano, rampa de 20° subindo e de lado, degrau de 21 cm:
    pés a ≤ 0,02 cm do chão com IK (sem IK: −9/+8 cm na rampa subindo, −7,6/+7,5 cm de lado, 21 cm no
    degrau, ~1 cm no plano); pelve desceu 11 cm na rampa e 21 cm no degrau; cabeça virou 57° com a câmera
    a 70° e 0° com a câmera atrás;
  - `cargo test --test engine` (herói e orc low-poly da Forja): 5 de 5, 0 erros, andou 7,83 m, 1 de 6
    inimigos derrotado, árvore + IK + olhar + golpe andando conferidos, pés parados a no máximo 0,07 cm
    em 17 quadros (sem IK: 0,58 cm);
  - teste realista (templário e inimigo criados pelo MCP, `personagem_realista`): passou, 0 erros, andou
    7,78 m, 1 de 4 inimigos derrotado, conferências do movimento todas verdes, pés parados a no máximo
    1,25 cm (média 0,09 cm) em 208 quadros, contra até 1,24 cm (média 1,06 cm) sem IK; o pior quadro é
    logo depois de parar, com a mistura ainda assentando. A rodada com janela e vídeo passou do tempo-limite
    de 228 s (renderização por software a ~1 quadro/s nesta máquina carregada) e o teste refez sem janela,
    como já previsto no código; só a lógica custa ~0,7 ms a mais por quadro para os 5 personagens;
  - `cargo test --workspace` (198 testes), clippy, fmt e o teste do MCP (`testes/mcp-e2e`) verdes.
    Falta o CI no Windows e no Linux (sem push nesta rodada).
- **Achado (para a frente da física):** os ossos do ragdoll (PhysicalBone3D) ficam na camada do mundo
  enquanto seguem a animação. O CharacterBody3D do inimigo usava o braço do jogador no meio do golpe como
  "plataforma", herdava ~120 m/s e voava para longe (por isso os golpes não acertavam). O `movimento.gd`
  faz os corpos ignorarem os ossos físicos dos outros personagens, e os raios dos pés também (o pé não pisa
  no corpo caído). O certo é o `fisica.gd` pôr esses ossos numa camada própria enquanto não simulam.
- **Falta:** a sola é tirada dos ossos (pose de descanso), não da malha: o QA da Forja acusou o ponto mais
  baixo das peças do templário 2,7 cm abaixo da origem, e isso aparece igual com ou sem IK (correção no
  gerador); root motion (as capturas são no lugar), BlendSpace2D/strafe com orientation warping,
  travamento do pé pela curva de contato, IK também correndo, inércia (inertialization) nas trocas,
  bibliotecas 100STYLE/CMU/ACCAD, ragdoll misturado em golpes; o criador sentir na mão
  (TESTE_DO_CRIADOR.md, parte 6).

## Decisões que são do criador
- **APIs de geração (decidido em 21/11):** o criador autorizou APIs (Gemini imagem, Rodin, Meshy,
  Tripo e outras do plano). Entram como opção desligada por padrão, com a chave digitada na janela,
  preço e licença mostrados antes de cada geração e recibo. Continua sem telemetria.
- **App do primo:** o criador quer que a Fornalha aproveite o que o app do primo faz melhor (sem
  copiar). O zip no Drive tem 575 MB e não passa pela ferramenta do Drive: falta um zip só com o
  código-fonte ou um repositório. Código só entra com a permissão do primo.
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
4. **Imagem guiada pela forma (para texturizar o 3D da Fornalha):** gerar imagem condicionada a mapa de
   profundidade ou de normais (ControlNet ou equivalente com licença comercial) e com máscara
   (inpainting), local. A Fornalha manda a vista do modelo 3D e projeta a imagem de volta na textura.
   É o que mais aproxima o detalhe das referências em placas sem CUDA.
5. **Textura PBR que repete sem emenda:** gerar textura "seamless" por texto (pedra, couro, tecido
   bordado, metal gravado) e tirar dela os mapas de normal e rugosidade, local e com licença comercial
   (a pesquisa achou FLUX.2 klein Apache 2.0 e Marigold OpenRAIL++, conferir no Ignis).
6. **Placas AMD:** rodar a imagem (Z-Image ou a do pedido 4) na RX 580 e na RX 6600 por Vulkan, e na
   RX 9060 XT 16 GB pelo que for mais rápido, com o mesmo endpoint.

## Pedidos para a Erethea Engine (o criador leva para o chat da Erethea)
Conferido no `HANDOFF.md` da Erethea em 25/11/2026 (main de 23/11, commit c4993bf).
Já feitos na Erethea:
- **Upscalers** AMD FSR 3.1/4, XeSS e DLSS (`modules/erethea_upscale/`), presets de qualidade e
  pós-processo (LUT, lens flare, motion blur, grão).
- **Raios de luz** (`EretheaLightShafts`, PR #32). A névoa de altura é a do `Environment` da Godot
  (`fog_enabled` + `fog_height_density`), sem código novo.
- Ponte com a Fornalha (importa o `game.project.json`, elo ao vivo, `--agent-test`), MCP do editor
  (cena, `take_screenshot`, `run_test`, `get_errors`, `build_fornalha_scenes`) e som (WAV da
  dublagem, eco por área, música no fim do compasso).

Ainda na fila da Erethea (Fase 4 e 5 dela, não começados em 23/11):
1. **Cabelo fio a fio nativo** (fitas viradas para a câmera ou curvas, com alfa por hash e brilho
   anisotrópico), para a bancada de cabelo da Fornalha mandar o penteado direto (Fase 4, item 5).
2. **SSS de pele melhor** (perfil de espalhamento por canal e mapa de espessura) e sombra de contato
   (Fase 4, item 5).
3. **Terreno nativo** compatível com Terrain3D (clipmap, 32 materiais, detiling, triplanar) e
   **vegetação** com LOD, impostores e vento (Fase 4, itens 6 e 7).
4. **Geometria virtual / LOD contínuo** (estilo Nanite) para cenário denso (Fase 5).
5. Prévia com LibGodot dentro da Fornalha (pedido 8; PR #31 da Erethea, quase pronto em 23/11).
Divisão combinada em 25/11 (veja o PLANO_3_ETAPAS.md): o que roda no jogo é da Erethea; as bancadas
que a IA usa para criar (movimento, roupa, cabelo, plano do mapa) são da Fornalha. O retarget e a
locomoção previstos no item 8 da Fase 4 da Erethea podem usar o banco e o esqueleto da Fornalha.
A Fornalha usa o que a Erethea tiver e cai para o caminho da Godot quando não houver.

## Notas para a Erethea Engine
A Fornalha trata a Erethea como a Godot: procura `erethea.console.exe`/`erethea.exe` em
`%LOCALAPPDATA%\Erethea` (ou o caminho escolhido em Máquina, ou `FORNALHA_ERETHEA`) e usa
`--headless --import`, `--script`, `--write-movie` e o plugin de ponte do editor. Se a Erethea mudar
algum desses, avise aqui.

## Próximo passo
0. Etapa 1 do [PLANO_3_ETAPAS.md](docs/PLANO_3_ETAPAS.md): estação Movimento, banco ligado,
   esqueleto montado pela IA, conferência que reprova e roupa por cima.
1. Criador: rodar o TESTE_DO_CRIADOR.md no Windows (e, se quiser, no Linux).
2. Com a placa NVIDIA nova: instalar os modelos de placa em Máquina e rodar a parte 9 do teste.
3. Fase 5 só quando o criador pedir.
