# Plano em 3 etapas: a Fornalha 3D como bancada da IA

> Combinado com o criador em 25/11/2026. Este plano guia o trabalho a partir de agora; o
> [PLANO_2_ETAPAS.md](PLANO_2_ETAPAS.md) fica como histórico e lista do que já foi feito.
> Meta: menos de uma semana de trabalho (sem contar as pausas de limite de uso).

## Onde estamos (25/11/2026)
- **Etapa 1:** feita no código e provada aqui (Linux, sem placa) e na Erethea compilada aqui: conferência,
  correção automática, banco (Quaternius, ACCAD, 100STYLE, Mixamo/CMU trazidos), esqueleto editado pela
  IA, roupa por cima, estação Movimento. CI verde no Windows e Linux; teste no PC do criador (RX 580) feito
  e o que ele achou foi corrigido (ver ESTADO.md).
  Lembrete: "aprovado pela régua" não é "pronto"; pronto só depois do vídeo e do teste do criador.
- **Visual da janela:** refeito (clássico/premium) com tema preto e branco.
- **Etapa 2:** cabelo médio e comprido em **cards guiados** pelo cabelo do pacote (parece cabelo de verdade
  no render; falta ver no Forward+ com TAA e a aprovação do criador; barba ainda não). **Bancada
  de mapa feita** (`generate_map`: plano da IA → relevo com erosão, rio, lago, estradas com ponte, chão
  pintado, vegetação por regras, vila com ruas, medidas e fotos de cada região na engine); falta a prova
  numa placa de verdade e a masmorra por peças.
- **Etapa 3:** o guia para qualquer IA nasce em cada projeto (AGENTS.md + ponteiros para Claude, Gemini,
  Copilot, Cursor, Windsurf e os arquivos de MCP); a **cena curta** virou receita (`create_cutscene` +
  `CenasCurtas.tocar`). **26/11:** liberdade com referência (controles finos no `create_character`, roupa
  moderna, `compare_reference`, montagem livre por peças no `generate_3d`, casas da IA na vila do mapa,
  visual anime pela bíblia) e o roteiro do jogo de prova (`testes/mcp-e2e/jogo_de_prova.mjs`). Falta o
  teste do criador no PC e a aprovação dele (cabelo, barba, manequim do Joel).

## A ideia em uma frase
Quem faz o jogo é a **IA** (Claude Code, Codex, Gemini, Cursor, Copilot ou outra) junto com a **Erethea Engine** (a principal) e a
**Fornalha 3D** (a ajudante). A Fornalha não tem jogo, mapa ou monstro pronto: ela dá à IA
**mãos** (ferramentas), **olhos** (imagens de cada resultado) e **medidas** (números que dizem o que
está errado), para a IA fazer mais, mais rápido e com mais qualidade. O limite é a IA e a conta dela.

## O que a Fornalha já faz e continua fazendo (nada sai)
- Imagem de conceito e folha de modelo (Ignis, motor Vulkan, ComfyUI) e 3D pela IA (TRELLIS.2).
- APIs pagas (Meshy, Tripo, Rodin), desligadas por padrão, com preço e licença antes de gerar.
- Blender (Forja, rig, assar textura, malha de jogo) e Godot/Erethea (montar, testar, capturas).
- **Dublagem** pela voz do Ignis (o idioma vai no pedido: português e outras línguas), **boca
  mexendo com a fala**, **olhos que piscam e olham**, música por situação, efeitos sonoros.
- Projeto do jogo organizado (`game.project.json`), assets, armas, recibos e licenças para vender.
- MCP com as ferramentas, fila da noite, pedido livre, Teste Bruto.

## Quem faz o quê (Erethea × Fornalha)
| Erethea Engine (principal): o que roda no jogo | Fornalha 3D (ajudante): o que a IA usa para criar |
|---|---|
| Renderização, upscalers (FSR, XeSS, DLSS), pós-processo, ray tracing | Bancadas de movimento, roupa, cabelo e mapa |
| Física e ragdoll, molas de ossos (da base da Godot) | Banco de movimento com licenças conferidas |
| Terreno nativo, vegetação com LOD, cabelo fio a fio, pele (Fase 4 dela) | Plano do mapa, relevo, espalhamento, penteado, roupa por cima |
| MCP do editor: cena, `take_screenshot`, `run_test`, `get_errors` | MCP da Fornalha: gerar, conferir, medir, montar |
A Fornalha usa o que a Erethea tiver e cai para a Godot 4.6.1 enquanto a Erethea não está pronta
(o CI da Fornalha testa na Godot). Antes de fazer algo de engine na Fornalha, confira no repositório
da Erethea (`kaikyolf29-hub/-Erethea-Engine`, `HANDOFF.md`) se ela já faz ou vai fazer.

## Regra de toda bancada
Cada ferramenta devolve **imagens** (frente, perfil, costas, close; vídeo ou folha de quadros) e
**números** com aprovado/reprovado. A IA olha, mede, corrige e só entrega o que passou. A janela
mostra o mesmo para a pessoa, com aceitar ou refazer. Licença comercial sempre (regra do CLAUDE.md).

---

## Etapa 1: Movimento e roupa (a parte que mais dói) · 2 a 3 dias
Estação nova **Movimento** na janela (simples e bonita: manequim no centro, ossos marcados, banco à
direita, linha do tempo embaixo; a ideia vem de estúdios como o ActionForge, sem copiar nada) e as
mesmas ações no MCP.
1. **Banco de movimento ligado, com etiquetas** (andar, correr, espada de uma mão, duas mãos,
   pesado, zumbi, quatro patas…): Quaternius (CC0, já temos), **Mixamo baixado pela própria pessoa**
   (importar FBX; os termos da Adobe proíbem redistribuir os arquivos), **100STYLE** (CC BY 4.0) e
   **ACCAD** (CC BY 3.0), com crédito e licença conferidos na página antes de entrar no manifest.
2. **Esqueleto para qualquer corpo, montado pela IA:** a bancada sugere (patas pelos pés, coluna,
   cauda, asas, braço pelo volume: `fc_rig_generico`, `fc_eixo`) e mostra a malha com os ossos
   numerados; a IA confere na imagem e põe, tira ou move ossos. Nada de monstro pré-montado.
3. **Movimento de três fontes:** clipes do banco (retarget), passada calculada (patas pisam no chão
   pelo IK, qualquer número de patas) e física (molas em cauda, asa, cabelo, capa, saia; ragdoll).
4. **Conferência que reprova:** braço ou antebraço torcido além do limite (limites anatômicos por
   junta, ideia do app do primo), junta dobrando ao contrário, mão ou braço atravessando o tronco
   (corpo sólido por cápsulas), pé escorregando (cm), pata atravessando o chão, mão fora do cabo.
5. **Roupa por cima, depois do movimento aprovado:** a malha da IA vira roupa ou pele; armadura
   presa rígida por osso (elmo, ombreira, manopla), pano com os pesos do manequim e mola; nada de
   roupa grudando nem braço preso na capa.
6. Rosto (boca na fala, piscar, olhar) entra igual ao de hoje em todo personagem com cabeça.
**Pronto quando:** templário, zumbi e fera passam a conferência inteira em parado, andar, correr,
atacar, defender, dano e morte, com vídeo; uma criatura de corpo novo é montada pela IA do zero.

## Etapa 2: Cabelo e mapa · 2 dias
**Bancada de cabelo** (sem elmo ou boné como atalho):
1. A IA descreve o penteado (comprimento, volume, risca, franja, cacho, nuca) e pode olhar uma
   referência.
2. Fios-guia crescem no couro cabeludo (curvas de cabelo do Blender): entrada da testa natural, nuca
   com fios curtos, mechas agrupadas.
3. Faixas de cabelo (cards) a partir dos guias, com textura de fios gerada ali (cor, alfa, raiz e
   ponta), no `cabelo.gdshader` (brilho anisotrópico, alfa sem serrilhado com TAA); mola nas mechas.
4. Barba e sobrancelha pelo mesmo caminho.
5. Fotos em três luzes e medidas: couro aparecendo, buraco entre mechas, fio atravessando a cabeça.
O cabelo fio a fio é da Erethea (Fase 4, item 5); quando existir, a bancada manda o penteado direto.

**Bancada de mapa** (a IA projeta, as ferramentas deixam bonito):
1. A IA escreve o plano do mapa: regiões, relevo, rio, estradas, vila, ruína ou masmorra, clima e hora.
2. Relevo com erosão, chão pintado por inclinação e altura, espalhamento por regras (nada de árvore
   em barranco, mais densidade perto da água), vila e masmorra montadas por peças encaixadas.
3. Assets CC0 (Poly Haven, ambientCG, Quaternius, Kenney) e a IA gerando só o que for único.
4. Luz pronta por clima (céu, névoa de altura, hora dourada).
5. Fotos de vários pontos (pela Erethea, `take_screenshot`, ou pela Godot) e a IA ajusta.
Ferramentas abertas para avaliar (licença conferida na página antes de entrar): Terrain3D,
ProtonScatter, Spatial Gardener, Wave Function Collapse, geometry nodes do Blender. Do app do primo
(com a permissão dele, `docs/APP_DO_PRIMO.md`): paisagem esculpível, pintura por encosta,
geradores de sala e masmorra.
**Pronto quando:** cabelo curto, médio, comprido e barba aprovados pelo criador; um mapa pequeno
(~500 × 500 m, vila, floresta, estrada e masmorra curta) bonito e jogável.

## Etapa 3: Tudo ligado para a IA · 1 a 2 dias
1. **Guia para a IA dentro de cada projeto de jogo:** a Fornalha grava `CLAUDE.md` e `AGENTS.md`
   (Codex) no projeto do jogo, com a ligação Erethea + Fornalha, os dois MCP configurados, a ordem das
   receitas (conceito → movimento → roupa → cabelo → mapa → áudio e dublagem → cena curta → teste) e
   as regras de licença. Toda sessão nova do Claude Code ou do Codex já sabe como trabalhar.
2. **Projeto organizado:** assets, armas, sons e falas num lugar só, cada um com licença e recibo.
3. **Cena curta** (câmera, animação e fala com boca e olhos) como receita.
4. **Prova:** o Claude Code faz um jogo pequeno completo pelo prompt (herói, três inimigos, mapa da
   Etapa 2, luta sem braço quebrado, música, efeitos, dublagem, cena curta), rodando na Erethea
   quando ela estiver pronta e na Godot no CI. Depois, o teste do criador no PC (TESTE_DO_CRIADOR.md).

## Fica para depois
Retopologia de verdade, mapa grande por regiões, aranha e outros corpos que só geram malha com placa
(até lá: Forja ou API), captura de duas mãos própria, nível máximo das referências (RE4 Remake,
Elden Ring), que continua sendo o teto.
