# Plano em 3 etapas — Fornalha 3D até o nível das referências

> Pedido do criador (21/11/2026): juntar em 3 etapas tudo o que já foi pedido, tudo o que falta da
> [Bíblia técnica AAA](BIBLIA_TECNICA_AAA.md) e o que veio depois (níveis GTA, Dark Souls 2/3,
> Resident Evil Village e RE4 Remake; ComfyUI; APIs; app do primo; placas AMD; Erethea).
> **Meta de saída:** chegar o mais perto possível das referências (templário branco, cavaleiro de
> placas com escudo, rosto Snappers, velho careca, templário de jogo com manto) **sem placa NVIDIA**.
> Ao chegar lá, a ferramenta fica parada até a NVIDIA; com ela, entra a IA de 3D.

Regras que valem nas 3 etapas:
- **Um item por vez, por partes:** rosto → corpo → cabelo → roupa → armadura → arma (ou: corpo da
  criatura → pele/pelo → chifres/asas → movimento). Cada parte só passa depois do look-dev e da
  aprovação; aí a próxima.
- **Avaliação objetiva:** look-dev padronizado + QA automático (seção 9 da bíblia). Nada de "ficou
  bom" sem comparação lado a lado com a referência.
- **Licença:** só o que permite uso comercial. Fora: LAFAN1, AMASS, HumanML3D, Bandai Namco, ZEGGS,
  Motorica, BONES-SEED, Digital Emily (não comerciais); Texturing.xyz e 3DScanStore (pagos, só se o
  criador comprar). Dentro: CMU, 100STYLE (crédito), ACCAD (crédito), Mesh2Motion, Quaternius,
  Mixamo (baixado pela pessoa), Poly Haven (crédito "Powered by Poly Haven"), ambientCG, MakeHuman
  (dados CC0), Megascans (pela conta da pessoa).
- **Quanto mais forte a máquina, melhor** — mas tudo funciona em qualquer uma (RX 580 inclusive).

---

## Etapa 1 — Personagem e item no nível da referência (qualquer placa)

**1.1 Look-dev e QA (base de tudo)**
- Estúdio fixo no Blender e na Godot: fundo cinza 18% (#4A4A4A), HDRI neutro + 3 pontos (chave 45°,
  preenchimento, recorte), esferas de calibração (cromo e cinza 18%), AgX.
- Câmeras: corpo inteiro (frente, 3/4, perfil, costas), close do rosto, linha do cabelo, coroa, nuca,
  e pose de estresse (braços a 120°, agachado, pescoço a 60°).
- QA em código antes de mostrar: escala/rotação zeradas, faces degeneradas, pesos somando 1, cabelo
  a < 2 mm do crânio e sem buracos (raios de fora para dentro), mapas de dados em Non-Color, albedo
  dentro da faixa física, normal OpenGL (+Y), pés no chão.
- Folha de comparação automática: nosso resultado ao lado da referência escolhida.

**1.2 Cabelo AAA** (em andamento)
- Feito: penteado fio a fio colado no crânio de verdade (campo de distância), cards em 3 camadas,
  atlas de mechas, couro cabeludo com fade, normais da casca, shader com hash e Kajiya-Kay na Godot.
- Falta: corrigir o couro cabeludo que sai branco na Godot e as falhas entre cards; perfil em "U"
  real; mais estilos (risca, comprido, coque, barba cheia, sobrancelha em cards); fios soltos na linha.

**1.3 Rosto e pele**
- Feito: pele 4K com poros, rugas por idade, barba rala, vermelhidão; olho natural.
- Falta (bíblia 3.3/3.4): olho em 4 peças (córnea com refração, menisco lacrimal, malha de sombra da
  pálpebra), mapa de espessura (SSS nas orelhas), penugem (sheen), detalhe de poros em 2 frequências,
  rugosidade dual-lobe; expressões (blendshapes FACS do MakeHuman/ICT FaceKit MIT).

**1.4 Corpo e roupa**
- Sem recorte serrilhado (máscara em vez de apagar faces), roupa com caimento de pano simulado no
  Blender e assado (sobreveste, manto, capuz), costuras, couro com grão, cintos com fivelas,
  sujeira/lama perto dos pés, barra rasgada; capuz do templário.

**1.5 Armadura no nível das referências**
- Peças modeladas (elmo armet/barril feitos; falta ombreira em lâminas de verdade, cotoveleira com
  asa, manopla articulada, sapato de placas), gravuras e rebites em normal, correias de couro,
  ORM empacotado, validador PBR (aço 0.55–0.78, rugosidade 0.22–0.45, ferrugem com metal 0).
- Escudo, espada e bainha no mesmo nível; ouro/latão envelhecido.

**1.6 Movimento base**
- Root motion, pés no chão (IK de duas juntas com raio no calcanhar e na ponta, travamento pelo
  contato), BlendSpace2D com ajuste de passada, camadas (pernas × braços), olhar (LookAtModifier3D).
- Bibliotecas comerciais: 100STYLE, CMU, ACCAD (artes marciais), Mesh2Motion, Mixamo da pessoa.
- Física: capa e abas da sobreveste por mola, ragdoll com mistura em golpes.

**1.7 Ferramenta "por partes" na janela**
- Forjar → Personagem por etapas: cada parte com prévia de look-dev, "aceitar" ou "refazer com
  ajuste"; o MCP ganha as mesmas etapas para o Claude Code e outros agentes.

**1.8 Conexões**
- **App do primo:** analisar e trazer o que for melhor (precisa do código-fonte num zip pequeno ou
  num repositório; usar ideias, e código só com a permissão dele).
- **ComfyUI** (processo à parte, local, pela API HTTP; NVIDIA, AMD por ROCm/DirectML/ZLUDA):
  texturas, imagens de referência e mapas (com modelos de licença comercial).
- **APIs opcionais** (decisão do criador, 21/11): Gemini (imagem), Rodin, Meshy, Tripo — desligadas
  por padrão, chave na janela, preço e licença antes de cada geração, recibo.
- **Ignis:** pedidos 4–6 do ESTADO (imagem guiada pela forma, textura sem emenda, AMD por Vulkan).

**1.9 Estilos de jogo** (pedido do criador: qualquer jogo, não só realista)
- Fotorrealista e fantasia sombria (o alvo das referências), pintado à mão, cel-shaded (anime),
  low poly moderno, retrô 3D (PS1), voxel e miniatura (toy) — e os outros estilos de jogo que
  existirem (estilizado tipo cartoon/Pixar, pixel art 2.5D, noir, aquarela, sci-fi limpo etc.).
  A régua continua a das referências: cada estilo tem de sair no nível de um jogo grande daquele estilo. O mesmo personagem sai em qualquer estilo:
  o estilo escolhe materiais (PBR calibrado, pintado, toon com contorno, cores chapadas), geometria
  (decimação, voxelização, malha tipo PS1 com vértice "tremido" e textura em baixa), shader na Godot
  e a folha de modelo (frente, perfil, costas) no look-dev.

## Etapa 2 — Mundo, criaturas e combate (nível Dark Souls / RE Village / RE4 Remake)

**2.1 Terreno e cenário**
- Heightmap com erosão hidráulica e térmica (numpy), máscaras de inclinação/fluxo/sedimento/altitude,
  integração com **Terrain3D** (MIT) na Godot e na Erethea, biomas por Poisson (árvores com impostor,
  rochas, arbustos, grama em MultiMesh com vento), decals e pintura de vértice.
- Kits modulares em grade (2/4/8 m) com trim sheets: castelo, muralha, catedral, vila medieval,
  masmorra, interiores (RE Village); presets de luz e atmosfera (SDFGI/VoxelGI/Lightmap, névoa
  volumétrica, SSR, sondas, sombras PSSM 4) por estilo: "Dark Souls", "RE Village", "GTA dia".

**2.2 Criaturas, inimigos e chefes** (no nível das referências, inclusive fotorrealista)
- Quadrúpedes (leão com pelo em shell + juba em cards, lobo, cavalo), dragão extremamente realista
  (escamas, membrana das asas translúcida, voo, fogo), goblins, orcs, mortos-vivos, golem de pedra,
  cavaleiro inimigo, insetos/aranhas gigantes, chefes colossais (deus gigante da mitologia, Buda
  gigante andando) com escala, peso e física de verdade (passos que tremem o chão, partes que caem,
  colisão por parte do corpo); esqueletos próprios por tipo de criatura e animação (procedural +
  captura comercial), com pés no chão e IK em quatro patas.

**2.3 Combate AAA**
- Trava de alvo, estamina, combos com cancelamento, defesa/aparar, reações de dano direcionais,
  ragdoll misturado, IA de inimigo por estados, inércia nas transições (inertialization).
- Motion matching opcional com dados comerciais.

## Etapa 3 — Máquinas fortes, IA de 3D e a Erethea

- **NVIDIA:** TRELLIS.2 / Pixal3D (blockout de peças únicas → retopologia → bake → PBR), Kimodo
  (texto → movimento, licença aberta comercial), SkinTokens/Puppeteer (rig).
- **AMD:** caminhos ROCm (Linux, RX 6600/9060 XT) e DirectML/ZLUDA (Windows) no ComfyUI e no Ignis.
- **Erethea Engine** (pedidos na lista do ESTADO): render de cabelo fio a fio nativo, SSS melhor,
  geometria virtual (estilo Nanite) para cenário denso, terreno nativo, upscaling (FSR), efeitos do
  compositor; a Fornalha usa o que existir na Erethea e cai para a Godot quando não houver.
- Laço de crítica por visão (modelo de visão do Ignis) até passar nos critérios.
- Fase 5 (venda e atualização privada) só quando o criador pedir.
