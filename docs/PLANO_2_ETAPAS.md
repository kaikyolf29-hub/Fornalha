# Plano em 2 etapas — Fornalha 3D completa

> Pedido do criador (22/11/2026): juntar **tudo o que falta** — o Plano 1 original, o plano em 3
> etapas, a [Bíblia técnica AAA](BIBLIA_TECNICA_AAA.md), o complemento técnico (corpo, rosto, cabelo,
> criaturas e teste bruto) e os pedidos da Erethea Engine — em **duas etapas** para terminar a
> Fornalha 3D. O nome é Fornalha 3D, mas ela gera de tudo (2D também).
> **Teto de qualidade:** RE4 Remake (realista), Elden Ring e Tales of Fantasy (estilizado) — vale a
> geração levar horas se chegar lá. Estilos mais simples (PS2, PS1…) são escolha da pessoa.

## Onde estamos (atualizado a cada bloco de trabalho)
- **Etapa 1 em andamento.** Feito nesta etapa até agora: look-dev/QA, pele 4K, cabelo curto em cards,
  pano simulado (sobreveste e capa), movimento base, **ComfyUI** (conector, instalador pela placa, teste real no
  processador do GitHub no Windows e no Linux), **pedidos 1–7 da Erethea** (música por situação, fala
  presa ao personagem, mandíbula, acústica, ponte ao vivo por WebSocket, teste de agente).
- Movimento base juntado (árvore de animação, pés no chão, olhar). Próximos, nesta ordem: criaturas e dragão → suíte de
  Teste Bruto → modo Teste de Fogo (RX 580, Windows) → cabelo sem manchas → roupa/armadura → folha
  de modelo pelo ComfyUI → por partes na janela.

## Regras que valem nas 2 etapas
- **Termine o que está fazendo** antes de pegar o próximo item; nada de quebrar o que já funciona.
- **game.project.json é a fonte única da verdade**; referências do criador (RE4 Remake, Elden Ring,
  Tales of Fantasy, templários, cavaleiros, Joel/Arthur, dragões…) são a régua, com folha lado a lado.
- **Placa primeiro, grátis sempre**; **licença comercial obrigatória** (nada CC BY-NC/não comercial;
  todo modelo novo no manifest com licença conferida na página; aceite só pela janela).
- **Ignis:** um modelo por vez na VRAM (POST /motor/reservar), recibo de licença por asset.
- **Divisão:** a Fornalha gera, limpa, faz o rig e exporta glTF; a **Erethea** (fork da Godot 4.8)
  renderiza em tempo real e aplica os upscalers (FSR, XeSS, DLSS, TAA).
- **Um item por vez, por partes**, avaliado com look-dev e QA; nunca "ficou bom" sem comparação.
- Foco no **Windows** (instalador, testes, placa da pessoa); o Linux segue no CI.
- Não dizer que funciona numa placa sem prova nela (TESTE_DO_CRIADOR.md).

---

## Etapa 1 — Fornalha 3D completa, pronta para o Teste de Fogo na RX 580 (Windows)
Meta: o criador baixa a versão de desktop (ou abre uma sessão no terminal com acesso), instala no
Windows com a RX 580 8 GB e a suíte de Teste Bruto passa no nível Qualidade e no Máximo.

**1.1 Look-dev e QA** — ✅ estúdio fixo, câmeras, QA da bíblia (escala, faces, pesos, Non-Color,
albedo, pés no chão, cobertura do cabelo). Falta: mostrar na janela (1.13) e sobrepor a referência.

**1.2 Referência e folha de modelo (multi-view)** — ✅ ComfyUI gera referências (Z-Image Turbo).
Falta: folha frente/perfil/costas em pose neutra (A-pose, braços afastados, pernas levemente
separadas, mãos com dedos separados, simetria e proporções reais) pelo ComfyUI com o guia visual
(FLUX.2 klein entra quando a licença do VAE dele for confirmada na fonte); medir a silhueta da folha
(ideia do app do primo) e usar para ajustar o corpo do MakeHuman e a largura das roupas.

**1.3 Corpo, rosto e pele** — ✅ pele 4K por texel (poros, rugas pela idade, barba rala), olho
natural, mandíbula com pesos do MakeHuman. Falta: olho em 4 peças (córnea, menisco, sombra da
pálpebra), mapa de espessura (SSS no rosto, orelhas e mãos — sem "boneco de cera"), penugem, poros
em 2 frequências, expressões (FACS/ICT FaceKit MIT).

**1.4 Cabelo em camadas** — ✅ couro cabeludo (touca) com fade, cards em 3 camadas a partir de fios,
atlas, normais da casca, shader Kajiya-Kay com transparência pontilhada (roda na RX 580 e no
renderizador de compatibilidade) e brilho que quebra fio a fio. Falta: tirar as manchas dos lados e
da nuca; normal map do cabelo; mapa ORM empacotado (R oclusão, G deslocamento do brilho, B id do fio)
como no complemento; médio/comprido com gravidade e colisão nos ombros; barba e sobrancelha em cards;
molas (spring bones) na cabeça.

**1.5 Roupa e armadura** — ✅ pano simulado (sobreveste franzida, abas sobre as pernas, capa caindo,
estampa que acompanha as dobras), armadura PBR com desgaste assado, elmos modelados. Falta: camadas
separadas sem a pele atravessar (máscara em vez de apagar), costuras, sujeira/lama na barra, capuz,
o mesmo pano nas outras roupas (soldado, nobre, camponês), ombreira em lâminas, manopla articulada,
gravuras e rebites em normal, validador PBR (aço 0,55–0,78; rugosidade 0,22–0,45).

**1.6 Da imagem à malha de jogo (IA)** — ✅ workers TRELLIS.2/UniRig/HY-Motion prontos (NVIDIA).
Falta: imagem → 3D também pelo ComfyUI (Hunyuan3D 2.1 depois de conferir a licença: tem restrição de
território); retopologia (QuadriFlow) com mais polígonos nas dobras (rosto, ombros, cotovelos, mãos,
quadril, joelhos); bake de normal da malha alta na baixa; PBR completo (albedo, normal, rugosidade,
AO).

**1.7 Rig e movimento** — ✅ esqueleto único humanoide (nomes Unreal), retarget da captura
(Quaternius CC0, CMU), molas na capa, `movimento.gd` (AnimationTree por velocidade real com passada sem
patinar, camada de cima para atacar andando, pés no chão com TwoBoneIK3D, olhar com LookAtModifier3D).
Falta: root motion, BlendSpace2D/strafe com orientation warping, travamento do pé pela curva de contato,
IK também correndo, inertialization nas trocas, molas no cabelo e nas abas, mais bibliotecas comerciais
(100STYLE, ACCAD, Mesh2Motion, Mixamo da pessoa).

**1.8 Criaturas e dragões** — o rig não pode travar em humanos. Esqueletos próprios (quadrúpede;
dragão com coluna longa, pescoço articulado, cauda com vários ossos, asas com membrana e mandíbula;
aranha), malha procedural no Blender (dragão, lobo, golem) e, com placa, por IA; animações
procedurais (voo, bater de asas, rugido, bote, caminhada pesada) e IK em quatro patas.

**1.9 ComfyUI como motor geral e conexões** — ✅ conector (só 127.0.0.1), instalador pela placa
(CUDA, ROCm, DirectML para a RX 580, processador), Máquina → ComfyUI, CLI, teste real no CI. Falta:
fluxos de textura sem emenda e mapas (normal/rugosidade), concept de cenário, 3D (1.6) e movimento
(quando houver modelo comercial); APIs opcionais (Gemini, Rodin, Meshy, Tripo) desligadas por padrão;
pedidos do Ignis (imagem guiada pela forma, textura sem emenda, AMD por Vulkan).

**1.10 Erethea** — ✅ pedidos 1–7 (música .musica.json, Sons por situação e grupo erethea_musica,
fala presa ao personagem, boca no forja.json, acústica, WebSocket da ponte, --agent-test). Falta:
Godot 4.8 beta no CI ao lado da 4.6; pedido 8 (prévia da Erethea na Galeria pela LibGodot) quando a
Erethea tiver.

**1.11 Suíte de Teste Bruto** (comando na API, no MCP e na linha de comando, e no CI):
caso 1 protagonista completo (corpo, rosto, cabelo em camadas, roupa, rig + andar e combate);
caso 2 inimigo humanoide armado (encaixe da arma na mão, retarget); caso 3 dragão (malha grande,
asas, cauda, rig não humanoide, voo e ataque). Valida Blender sem janela, glTF, esquema do
game.project.json, recibos de licença comercial de tudo e o jogo rodando na engine.

**1.12 Modo Teste de Fogo (RX 580 8 GB, Windows)** — forçar Qualidade ou Máximo numa placa de 8 GB
(pouca VRAM, descarregar para a RAM, fila sequencial, um modelo por vez), Leve rápido para o dia a
dia; instalador do Windows com tudo; roteiro no TESTE_DO_CRIADOR.md; teste no computador do criador.

**1.13 Por partes na janela** — Forjar → Personagem por etapas (rosto → corpo → cabelo → roupa →
armadura → arma), cada parte com prévia de look-dev e "aceitar" ou "refazer com ajuste"; o MCP com
as mesmas etapas; modo "só ver" e desfazer por edição de agente (ideias do app do primo).

**1.14 Estilos base** — realista (RE4 Remake) e estilizado (Elden Ring / Tales of Fantasy) no mesmo
personagem, com materiais, shader e folha de modelo próprios.

## Etapa 2 — Depois do Teste de Fogo: mundo, combate, todos os estilos e placas fortes

**2.1 Terreno e cenário** (RE Village, Dark Souls 2/3, GTA) — erosão, máscaras, Terrain3D (MIT),
biomas por Poisson (árvores com impostor, grama em MultiMesh com vento), kits modulares com trim
sheets (castelo, muralha, catedral, vila, masmorra, interiores), presets de luz e atmosfera;
gerador de masmorra e leitura de mapas do Tilemap 3D (app do primo).

**2.2 Criaturas e chefes colossais** — dragão fotorrealista (escamas, membrana translúcida, fogo),
leão com pelo e juba, goblins, orcs, mortos-vivos, zumbis, golem, insetos gigantes, deus gigante e
Buda gigante andando com peso e física de verdade (passos que tremem o chão, colisão por parte).

**2.3 Combate AAA** — trava de alvo, estamina, combos com cancelamento, aparar, reações
direcionais, ragdoll misturado, IA de inimigo por estados, inertialization, motion matching opcional.

**2.4 Todos os estilos** — pintado à mão, cel-shaded (anime), low poly, PS1/PS2, voxel, miniatura,
cartoon, noir, aquarela, sci-fi — cada um no nível de um jogo grande daquele estilo.

**2.5 Placas fortes e IA de 3D** — NVIDIA (TRELLIS.2/Pixal3D, Kimodo, SkinTokens/Puppeteer), AMD
nova (ROCm, ZLUDA), RX 9060 XT 16 GB e RTX 5090; laço de crítica por visão até passar nos critérios.

**2.6 Erethea avançada** — cabelo fio a fio nativo, SSS por canal, geometria virtual (estilo
Nanite), terreno nativo, compositor (névoa de altura, raios de luz); a Fornalha usa o que existir e
cai para a Godot quando não houver.

**2.7 Fase 5** (venda e atualização privada) — só quando o criador pedir.

---

### Notas do complemento técnico (22/11)
- O shader de cabelo sugerido (alpha scissor + depth prepass) vira opção; o padrão continua a
  transparência pontilhada, que funciona também no renderizador de compatibilidade da RX 580. O mapa
  ORM com deslocamento do brilho entra no 1.4.
- FLUX.2 klein 4B: o modelo é Apache 2.0, mas o VAE vem do pacote do FLUX.2-dev (não comercial) até
  prova em contrário; fica de fora até a licença do VAE ser confirmada na fonte. Z-Image Turbo já
  cobre a folha de modelo.
- UniRig/Rigify: o humanoide segue no esqueleto único da Fornalha (MakeHuman, nomes Unreal); UniRig
  entra para criaturas quando houver NVIDIA.
