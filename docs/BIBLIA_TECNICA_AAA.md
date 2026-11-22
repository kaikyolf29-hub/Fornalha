# BÍBLIA TÉCNICA DE PRODUÇÃO 3D AAA & ARQUITETURA DE PIPELINE PARA IA

> **Finalidade deste documento:** Servir como especificação técnica mestra, base de referências visuais, dicionário de padrões da indústria e protocolo de controle de qualidade (QA) para um agente de IA engenheiro/artista técnico (ex.: Claude operando Blender Python `bpy`, Godot 4.x, geradores 3D e datasets de mocap).  
> **Padrão-alvo:** Qualidade de produção **AAA em tempo real** (fotorrealismo crível, PBR fisicamente calibrado, animação com peso físico e cenários coerentes em escala real).

---

## 1. DIAGNÓSTICO DE ANTI-PADRÕES (O QUE PARAR DE FAZER IMEDIATAMENTE)

Antes de construir novos módulos, a IA deve eliminar falhas estruturais clássicas de pipelines procedurais mal calibrados:

| Problema Observado / Anti-Padrão | Causa Técnica Real | Correção Obrigatória (Padrão AAA) |
| :--- | :--- | :--- |
| **Cabelo parecendo "tubos rígidos", "palha" ou "tufos com buracos"** | Uso de curvas/fitas procedurais cruas sem atlas de textura com transparência gradual, sem camadas hierárquicas e sem malha base no couro cabeludo. | Migrar obrigatoriamente para **Hair Cards em 4 camadas** + **Scalp Cap** com fade na hairline + mapas assados (`Alpha`, `Depth`, `Root`, `ID`, `Flow`, `AO`) + shader anisotrópico (**Marschner / Kajiya-Kay**). |
| **Peruca/Cabelo "flutuando" ou deslocado da cabeça ao exportar** | Transformações não aplicadas (`Location/Rotation/Scale`) no Blender, divergência de eixo ($Z$-up no Blender vs. $Y$-up no Godot) ou falta de transferência de pesos de osso (`Vertex Groups`) da cabeça para o cabelo. | Aplicar todas as transformações (`bpy.ops.object.transform_apply`), vincular o cabelo ao mesmo `Armature`, transferir pesos do osso `Head` com `Data Transfer` e validar a distância máxima couro-raiz ($< 2\text{ mm}$). |
| **Faixa escura suja na linha do cabelo (hairline)** | Projeção grosseira de textura no couro cabeludo ou *Ambient Occlusion* assado sem *Alpha Clip/Hash* adequado e sem transição de *baby hairs*. | Criar uma máscara de transição (*Hairline Blend Mask*) com fios finos irregulares (*flyaways* e *wisps*) e evitar pintar sombras pretas duras no *Albedo* da pele. |
| **Pele "estourada" (branca demais ou com brilho de plástico)** | Uso de *Tonemapper* linear/padrão sem `AgX`, luz direta intensa sem *Roughness Map* variado por zona facial, e ausência de *Subsurface Scattering* (SSS). | Ativar **AgX Tonemapper** + exposição controlada, usar **Cross-Polarized Albedo** (zero luz assada na textura), mapa de rugosidade zonal (*Dual-Lobe Specular*) e **Burley/Separable SSS** com mapa de espessura (*Thickness*). |
| **Recorte serrilhado/denteado na gola da roupa ou pescoço** | *Boolean* destrutivo ou exclusão de faces por distância para tentar esconder intersecção de malha sob a roupa (*mesh clipping*). | Nunca deletar polígonos de forma irregular em áreas visíveis. Usar malha limpa com *edge loops* na borda da gola ou *Mask Modifier* / *Opacity Mask* controlada em áreas 100% cobertas. |
| **Personagem "patinando" no chão (Foot Sliding) ou pés flutuando** | Animação *in-place* movida por código sem sincronia de velocidade, ou *retargeting* sem travamento de contato do pé e sem *Inverse Kinematics* (IK). | Implementar **Root Motion** real (osso `Root` no chão, $Y = 0$), **Two-Bone Foot IK** com *raycast* duplo (calcanhar + ponta) e **Foot Locking** baseado em curvas de contato. |
| **Modelos de IA Generativa 3D (ex.: TRELLIS) usados direto na engine** | Malha triangular densa/suja (*soup mesh*), UVs fragmentadas, textura com luz/sombra "queimada" no albedo e impossibilidade de deformação limpa em *rigging*. | Tratar modelos generativos **apenas como Blockout / High-Poly bruto**. Todo asset de jogo passa por: *Remesh/Retopologia* $\rightarrow$ *UV Unwrap* $\rightarrow$ *Cage Baking* $\rightarrow$ *De-lighting* $\rightarrow$ *Recalibração PBR*. |

---

## 2. BENCHMARKS VISUAIS & REFERÊNCIAS DA INDÚSTRIA AAA

A IA deve usar estes projetos, estúdios e pipelines como **régua de qualidade** para cada pilar do aplicativo:

### 2.1 Personagens, Rostos e Pele Digital
* **Snappers Systems (Facial Rig & Look-Dev):** Referência absoluta para micro-rugas dinâmicas (*wrinkle maps* acionados por *blendshapes*), simetria imperfeita, poros, barba rala (*stubble*) e realismo de olhos.
* **USC ICT Wikihuman Project (*Digital Emily 2* & *Digital Ira*):** Padrão científico aberto de escaneamento facial com separação física de *Diffuse Albedo*, *Specular*, *Single Scatter*, *Multi-Scatter* e *Micro-Displacement*.
* **3Lateral / Epic MetaHuman (Arquitetura FACS & RigLogic):** Referência estrutural de como separar cabeça, olhos, pálpebras, cílios, sobrancelhas, *peach fuzz* (penugem facial) e cabelo em camadas modulares e deformáveis.
* **Jogos-Referência de Rosto e Pele:** *Senua's Saga: Hellblade II*, *The Last of Us Part II*, *Baldur's Gate 3* (close-ups cinematográficos em tempo real), *Cyberpunk 2077* (materiais de pele e iluminação urbana).

### 2.2 Cabelos, Barbas e Pelagens em Tempo Real
* **Referências de Hair Cards AAA:** *The Last of Us Part II* (Naughty Dog), *God of War Ragnarök* (Santa Monica), *Horizon Forbidden West* (Guerrilla), *Red Dead Redemption 2* (Rockstar — referência também para pelos de animais e cavalos).
* **Artistas & Breakdowns Técnicos para Estudo de Arquitetura:**
  * **Jansen Turk** (estratificação de densidade de *hair cards* por camada).
  * **Maria Zatorska / Hazel Brown** (fluxo de *baking* de XGen/Blender para atlas de *hair cards* e criação de *hair caps*).
  * **SIGGRAPH 2003 — Marschner et al.** (*Light Scattering from Human Hair Fibers*) e **Kajiya-Kay (1989)** (modelos matemáticos de espalhamento anisotrópico de luz em fios).

### 2.3 Armaduras Medievais, Couros, Armas e Tecidos
* **Jogos-Referência:** *Kingdom Come: Deliverance II* (fidelidade histórica de aço, cota de malha, linho sujo e desgaste), *A Plague Tale: Requiem* (tecidos pesados, costura, camadas e sujeira orgânica), *Demon's Souls Remake* (Bluepoint — reflexos metálicos, gravuras, ferrugem e desgaste de bordas), *For Honor* (combate, rig de placas de armadura rígidas sem "esticar metal").
* **Regra de Ouro para Armaduras:** Placas de metal rígidas (**pauldron, cuirass, greaves, helmet**) **NUNCA** devem deformar como borracha. Elas recebem peso 100% em um único osso (ou ossos auxiliares de placa/ombreira com rotação amortecida), enquanto apenas a cota de malha (*chainmail*) e o gibão (*gambeson*) por baixo recebem *skinning* suave nas juntas.

### 2.4 Mapas, Biomas e Atmosfera
* **Jogos-Referência:** *Red Dead Redemption 2* (neblina volumétrica, biomas contínuos, transição lama/grama/pedra), *Ghost of Tsushima* (folhagem reativa ao vento, paleta atmosférica, composição de horizonte), *The Witcher 3 / Elden Ring* (silhueta arquitetônica, *landmarks* de navegação visual, contraste entre luz natural e ruínas).

---

## 3. ESPECIFICAÇÃO TÉCNICA DE PERSONAGENS AAA

### 3.1 Escala, Coordenadas e Orçamento de Geometria (Budgets)
* **Unidade Padrão:** Sistema métrico estrito ($1 \text{ unidade} = 1.0\text{ m}$). Humano adulto padrão: $1.75\text{ m} \text{ a } 1.85\text{ m}$.
* **Orientação no Export (`glTF 2.0` / `.glb`):** Personagem olhando para `+Z` (Godot forward via convenção glTF) ou `-Z` consistente em toda a pipeline, pés tocando exatamente $Y = 0.0$, origem do objeto/armature em $(0, 0, 0)$.
* **Orçamento de Triângulos (LOD0 — Herói / Personagem Principal):**
  * Cabeça + Corpo nu visível: $18.000 \text{ – } 35.000$ triângulos (concentrando densidade em rosto, mãos e articulações).
  * Armadura + Roupas + Equipamentos: $30.000 \text{ – } 65.000$ triângulos.
  * Cabelo + Barba + Sobrancelhas + Cílios (*Hair Cards*): $12.000 \text{ – } 30.000$ triângulos.
  * **LODs Obrigatórios:** LOD0 (100%), LOD1 (50% em $10\text{ m}$), LOD2 (25% em $25\text{ m}$), LOD3 (10% em $50\text{ m}$).
* **Densidade de Texel (*Texel Density*):**
  * Rosto/Cabeça: $20.48 \text{ px/cm}$ (mapa 4K dedicado à cabeça).
  * Corpo/Armadura: $10.24 \text{ px/cm}$ (mapas 2K–4K ou UDIMs organizados por conjunto: `Head`, `Body`, `Armor`, `Cloth`, `Hair`, `Eyes`).

### 3.2 Topologia Facial e Corporal (Deformação Limpa)
* **Somente Quads** em todas as áreas deformáveis (triângulos apenas em áreas planas ocultas ou na triangulação final da engine; **zero N-gons**).
* **Loops Faciais Obrigatórios (padrão FACS):**
  1. Loop orbital (ao redor dos olhos, estendendo-se como "máscara de herói").
  2. Loop oral (concêntrico ao redor dos lábios).
  3. Loop nasolabial (do nariz contornando o queixo).
  4. Densidade extra nas pálpebras (mínimo 3 loops de fechamento) e nos lábios (para fala/fonemas).
* **Articulações (Ombros, Cotovelos, Joelhos, Dedos):** Mínimo de 3 *edge loops* paralelos em cada junta dobrável para preservar volume durante a flexão.

### 3.3 Pipeline de Pele Hiper-Realista (Shader & Texturas)
A IA **nunca** deve gerar uma pele usando apenas uma cor sólida + ruído genérico. Um material de pele AAA exige:
1. **Cross-Polarized Albedo (`sRGB`):** Variação natural das 3 zonas cromáticas do rosto humano:
   * *Testa:* leve tom amarelado/dourado (osso próximo à superfície).
   * *Bochechas, nariz e orelhas:* tom avermelhado (alta vascularização/hemoglobina).
   * *Queixo e mandíbula (masculino):* leve subtom azulado/acinzentado (folículos pilosos sob a pele).
   * *Regra PBR:* Sem sombras pintadas, sem brilhos especulares pintados. Luminância do albedo de pele clara entre $0.35 \text{ – } 0.65$ (linear calibrado).
2. **Normal Map em 2 Frequências (Macro + Micro):**
   * *Macro/Meso Normal:* Assado do *High-Poly* (rugas estruturais, olheiras, cartilagens, veias).
   * *Micro Normal (Detail Normal):* Textura *tileable* de poros e linhas de pele repetida em escala alta ($15\times \text{ a } 30\times$), modulada por uma máscara por região (poros maiores no nariz/bochechas, linhas finas na testa, pele lisa nos lábios).
3. **Roughness Map (Linear) — Dual-Lobe Specular:**
   * Zona T (testa, nariz, queixo) e lábios: `Roughness` mais baixo ($0.32 \text{ – } 0.45$, maior oleosidade).
   * Bochechas, pescoço e orelhas: `Roughness` mais alto ($0.50 \text{ – } 0.65$).
   * Lábios úmidos / borda da pálpebra: $0.18 \text{ – } 0.30$.
4. **Cavity Map (Micro-oclusão):** Escurece suavemente o *Specular* dentro dos poros e rugas profundas para evitar que a pele pareça molhada dentro das fendas.
5. **Subsurface Scattering (SSS) + Thickness Map:**
   * Perfil de espalhamento avermelhado (luz atravessando hemoglobina).
   * *Thickness/Translucency Map* (assado com normais invertidas no Blender Cycles): branco nas orelhas, narinas e pontas dos dedos; escuro no crânio e bochechas densas.
6. **Peach Fuzz (Penugem Facial):** Efeito *Rim/Sheen* suave em ângulos rasantes (*Fresnel* com expoente $4 \text{ – } 6$) simulando micro-pelos iluminados contra a luz.

### 3.4 Olhos Fotorrealistas (Anatomia em Camadas)
Um olho AAA nunca é uma única esfera pintada. Ele é composto por **4 elementos**:
1. **Globo Ocular Interno (Esclera + Íris Côncava):** A íris é levemente afundada (côncava) com mapa de altura/normal detalhado e borda límbica (*limbal ring*) escura; a esclera tem micro-veias sutis nos cantos e gradiente rosado próximo às bordas.
2. **Córnea Externa (Malha Transparente):** Ligeiramente protuberante sobre a íris, `Roughness = 0.02`, `IOR = 1.376`, produzindo o brilho especular nítido (*catchlight*) e leve refração/paralaxe da íris.
3. **Menisco Lacrimal (*Tearline*):** Faixa fina de geometria acompanhando a pálpebra inferior, transparente e altamente reflexiva (`Roughness = 0.05`).
4. **Eye Occlusion Mesh (Sombra da Pálpebra):** Malha fina translúcida sobre o globo projetando uma sombra suave sob a pálpebra superior e nos cantos do olho. **Sem isso, o personagem sempre terá olhar artificial/estático.**

---

## 4. PIPELINE DEFINITIVO DE CABELO AAA (CORREÇÃO CRÍTICA)

Para superar definitivamente os problemas de "cabelo de palha/tubos soltos/peruca descolada", o aplicativo deve implementar o padrão da indústria de **Hair Cards Estratificados + Shader Anisotrópico**.

### 4.1 Arquitetura em 4 Camadas Obrigatórias
1. **Camada 0 — Scalp Cap (Couro Cabeludo):**
   * Malha duplicada diretamente da calota craniana, deslocada apenas $0.5\text{ mm}$ para fora.
   * Textura com gradiente suave na testa/têmporas/nuca (*Alpha Fade*) + micro-fios pintados (*baby hairs* e raiz raspada/curta).
   * **Função:** Eliminar buracos onde a luz atravessa o cabelo e remover completamente a "faixa escura artificial" na hairline.
2. **Camada 1 — Base / Blockout Cards (Volume Principal):**
   * Fitas largas e levemente curvadas em seção transversal (perfil em "U" ou "V" suave, nunca totalmente planas para evitar desaparecerem de perfil).
   * Atlas de textura de alta densidade (80%–95% de preenchimento).
   * Seguem o fluxo natural a partir do redemoinho (*crown whorl*) e da risca (*parting line*).
3. **Camada 2 — Secondary / Breakup Clumps (Quebra de Volume):**
   * Fitas médias (50%–70% de densidade), distribuídas sobre a Camada 1 com leve variação de ângulo e torção para criar silhueta orgânica.
4. **Camada 3 — Flyaways / Hairline Wisps (Acabamento AAA):**
   * Fitas finas e esparsas (15%–35% de densidade) concentradas na linha da testa, costeletas, nuca e topo da cabeça para capturar *rim light* (contra-luz) e quebrar a borda dura do penteado.

### 4.2 Mapas Obrigatórios do Atlas de Hair Cards (Baking em Blender Cycles)
O script Python do aplicativo deve gerar/assar (ou carregar de uma biblioteca pré-assada) um **Atlas 2K/4K** contendo 6 a 8 variações de mechas lado a lado (da mais densa à mais fina), com os seguintes canais:
* `Alpha (Opacity)`: Máscara precisa fio a fio (anti-aliased).
* `Depth / Height`: Profundidade relativa de cada fio dentro da mecha (cria volume 3D falso e auto-sombreamento).
* `Root-to-Tip Gradient`: $0.0$ na raiz (mais escuro/AO) até $1.0$ na ponta (mais claro/translúcido).
* `Unique Strand ID`: Tom de cinza aleatório por fio (permite variar cor, melanina e fios grisalhos no shader sem mudar a textura).
* `Flow / Direction Map`: Vetor tangente de cada fio para controlar o brilho anisotrópico.
* `Ambient Occlusion`: Oclusão entre fios da mesma mecha.

> **Empacotamento Otimizado (Channel Packing):** Para economizar VRAM e *texture fetches* na GPU, empacotar:  
> `Hair_Data_A (RGBA)` = `R: Alpha`, `G: Depth`, `B: Root`, `A: ID`  
> `Hair_Data_B (RGB)` = `R/G: Flow Tangent XY`, `B: AO`

### 4.3 Normal Transfer (O Segredo do Sombreamento Volumétrico)
* Hair cards com normais próprias individuais parecem "pedaços de papelão separados" sob a luz.
* **Solução Obrigatória no Blender (`bpy`):** Criar uma malha guia suavizada envolvendo o formato geral do penteado (*Groom Proxy Shell*) e aplicar o modificador **`DATA_TRANSFER`** (Modo: *Custom Normals*, *Nearest Face Interpolated*) transferindo as normais da casca suave para todas as *hair cards*. Resultado: a luz envolve o penteado como um volume unificado e macio.

### 4.4 Shader de Cabelo no Godot 4 (Marschner / Kajiya-Kay Simplificado)
* **Transparência:** Usar **`ALPHA_HASH`** (com TAA/MSAA ativo) ou *Alpha-to-Coverage* — **NUNCA** usar `ALPHA_BLEND` puro (causa erros graves de ordenação de profundidade onde a nuca aparece na frente da testa) e **NUNCA** usar `ALPHA_SCISSOR` seco sem dithering (cria serrilhado duro).
* **Brilho Duplo (Dual Specular Lobe):**
  * *Primary Specular ($R$):* Cor neutra/branca da luz, deslocado em direção à ponta pelo mapa de tangente/flow.
  * *Secondary Specular ($TRT$):* Tingido pela cor base do cabelo (melanina), mais largo e deslocado em direção à raiz.
* **Escurecimento de Raiz + Translucidez de Contra-luz:** Multiplicar o albedo por `mix(0.45, 1.0, root_mask)` e adicionar *Backlight / Wrap Diffuse* suave quando iluminado por trás.
* **Emparelhamento UV Estrito:** Todas as ilhas UV de *hair cards* devem estar orientadas na mesma direção vertical (Raiz no topo $V=0$ ou base $V=1$, consistente em 100% dos cards) sem espelhamento invertido que quebre a direção da anisotropia.

### 4.5 Pelagem Animal (Leão / Fauna AAA)
* **Corpo (Pelo curto):** Malha base com mapa de direção (*Flow/Comb Map*) + **Shell Texturing** (8 a 16 camadas extrudadas via shader/geometria com *noise* direcional e sombreamento crescente da raiz à ponta).
* **Juba / Cauda / Orelhas (Pelo longo):** Mesma arquitetura de **Hair Cards estratificados em 3–4 camadas** com *Normal Transfer* e shader anisotrópico, garantindo transição suave entre pelo curto e juba via *clump cards* intermediários.

---

## 5. MATERIAIS PBR FISICAMENTE CALIBRADOS (ARMADURAS, COUROS E TECIDOS)

A IA deve impor um **Validador de Calibração PBR** antes de aprovar qualquer material:

| Material | Albedo (sRGB Aprox.) | Metallic | Roughness | Regras Técnicas Específicas |
| :--- | :--- | :--- | :--- | :--- |
| **Aço Forjado / Armadura** | `0.55 – 0.78` (nunca $< 0.50$) | `1.0` | `0.22 – 0.45` | Micro-riscos anisotrópicos; *Edge Wear* guiado por mapa de *Curvature*; ferrugem e fuligem nas frestas (`Metallic` cai para `0.0` onde há sujeira/ferrugem!). |
| **Ouro / Latão Envelhecido** | `(0.85, 0.68, 0.32)` | `1.0` | `0.20 – 0.42` | Oxidação escura nas cavidades (*AO/Cavity Mask*). |
| **Cota de Malha (*Chainmail*)** | `0.45 – 0.65` | `0.9 – 1.0` | `0.35 – 0.55` | Textura *tileable* assada de anéis 3D reais (`Normal` + `Height` + `AO` + `Alpha` nas bordas) com alto contraste de cavidade. |
| **Couro Curtido / Cintos** | `0.08 – 0.28` | `0.0` | `0.42 – 0.72` | Micro-grão de pele animal; bordas desgastadas com *Roughness* mais alto e *Albedo* levemente mais claro; costuras em *Normal/Height*. |
| **Linho / Tabardo / Capa** | `0.15 – 0.75` (branco sujo max `0.78`) | `0.0` | `0.75 – 0.95` | Nunca usar branco puro `(1,1,1)`! Adicionar micro-trama (*weave normal*), desgaste/barra rasgada com *Alpha Mask*, lama gradual perto dos pés (*World-Z / UV-Y Dirt Gradient*) e efeito *Sheen/Velvet*. |
| **Pedra / Concreto / Terra** | `0.08 – 0.45` | `0.0` | `0.65 – 0.95` | Variação macro de umidade (poças baixam *Roughness* para `0.05 – 0.15` e escurecem *Albedo* por porosidade). |

> **Empacotamento ORM Obrigatório (glTF 2.0 / Godot 4):**  
> Combinar em uma única textura linear (`sRGB = OFF`):  
> `Red = Ambient Occlusion` | `Green = Roughness` | `Blue = Metallic`

---

## 6. MOVIMENTO, ANIMAÇÃO E LOCOMOÇÃO AAA

Para substituir animações robóticas e pés flutuando, o sistema de movimento do aplicativo deve seguir uma arquitetura em camadas:

### 6.1 Esqueleto e Rigging Padrão da Indústria
* **Padronização Obrigatória:** Mapear todo rig humano para o perfil **`SkeletonProfileHumanoid`** do Godot 4 (compatível com retargeting automático de Mixamo, CMU, 100STYLE, LAFAN1 e SMPL-X).
* **Ossos Críticos Adicionais:**
  * `Root` no solo $(0, 0, 0)$ para *Root Motion* limpo.
  * **Twist Bones** (`UpperArm_Twist`, `Forearm_Twist`, `Thigh_Twist`) recebendo 50% da rotação axial do pulso/ombro para eliminar o colapso de volume ("efeito bala torcida").
  * **Ossos de Equipamento e Física:** Cadeias de ossos dedicadas para capa, abas do tabardo, bainha da espada e bolsas controladas por *SpringBone* / *PhysicalBoneSimulator3D* (Godot Jolt).

### 6.2 Retargeting Limpo e Sistema "Pés no Chão" (Zero Foot Sliding)
1. **Extração de Root Motion:** Projetar a translação horizontal $(X, Z)$ e a rotação *Yaw* ($Y$) do osso `Hips` para o osso `Root`, mantendo a altura vertical natural (*bobbing*) no `Hips`.
2. **Foot Locking (Travamento de Apoio):**
   * Ao importar clipes de mocap (CMU / 100STYLE / LAFAN1), executar um script Python pré-processador que calcula a velocidade linear do tornozelo e ponta do pé: quando velocidade $< 0.08\text{ m/s}$ e altura $< 0.06\text{ m}$, gerar uma curva booleana `LeftFootLocked` / `RightFootLocked`.
   * Em tempo real, enquanto a curva está ativa, o alvo de IK do pé permanece travado na coordenada mundial onde tocou o solo.
3. **Two-Bone Analytical Foot IK + Pelvis Offset:**
   * Disparar dois *raycasts* por pé (calcanhar e metatarso) contra a geometria do terreno/escada.
   * Calcular o ponto de impacto e a normal da superfície para rotacionar o tornozelo perfeitamente alinhado à rampa.
   * **Regra da Pelve:** Deslocar o `Hips` para baixo pela diferença entre o pé mais baixo e a altura padrão do colisor — garantindo que a perna de apoio alcance o degrau sem hiperestender o joelho.

### 6.3 Locomoção Avançada (Estado da Arte)
* **BlendSpace2D + Stride Warping:** Ajustar dinamicamente a abertura da passada (*stride scale*) à velocidade real do personagem, evitando acelerar/desacelerar excessivamente a cadência da animação.
* **Orientation Warping:** Rotacionar progressivamente a parte inferior do corpo (pernas/quadril) na direção do movimento enquanto o tronco mira o alvo ou a câmera (*Strafe* realista).
* **Motion Matching + Inertialization (Nível AAA Avançado):**
  * Indexar um banco de poses (ex.: LAFAN1 + 100STYLE) em um vetor de características (*Feature Vector*): posição/velocidade dos pés, velocidade do quadril e trajetória futura em $+0.2\text{ s}, +0.4\text{ s}, +0.6\text{ s}$.
  * A cada $0.1\text{ s}$, buscar o frame de menor distância euclidiana ponderada e transicionar usando **Inertialization Blending** (interpolação polinomial de 5º grau baseada na velocidade angular atual dos ossos, sem o efeito fantasma do *crossfade* linear).
* **Layered Animation & Look-At IK:** Máscara de ossos separando membros inferiores (locomoção) de membros superiores (ataque, defesa, carregar arma) + `LookAtModifier3D` suave em pescoço/cabeça/olhos.

---

## 7. GERAÇÃO DE MAPAS, TERRENOS E CENÁRIOS AAA

Para que os cenários acompanhem o nível visual dos personagens, o aplicativo não deve gerar apenas "planos com Perlin Noise".

### 7.1 Terreno Realista com Erosão Física
* **Pipeline de Heightmap (16-bit ou 32-bit EXR):**
  1. **Macro-Forma:** Combinar *Simplex/Ridged Multifractal Noise* com perfis tectônicos ou importar dados reais de elevação (DEM — NASA SRTM / Copernicus).
  2. **Simulação de Erosão Hidráulica e Térmica (Python / NumPy / Taichi / Gaea / World Machine):** Simular gotas de água esculpindo ravinas, leitos de rios, depósitos de sedimentos e taludes rochosos. **A erosão é o fator nº 1 que diferencia um terreno amador de um mapa AAA.**
  3. **Exportação de Máscaras Derivadas (*Splatmaps*):** Gerar automaticamente máscaras em escala de cinza para:
     * `Slope` (inclinação $\rightarrow$ rocha viva em penhascos $> 35^\circ$).
     * `Flow` (fluxo d'água $\rightarrow$ cascalho, lama, leito de rio).
     * `Sediment / Concavity` (vales $\rightarrow$ terra fértil, grama densa, poças).
     * `Altitude` (picos $\rightarrow$ pedra seca, neve, vegetação rasteira).

### 7.2 Motor de Terreno e Iluminação no Godot 4
* **Terreno:** Integrar a extensão C++ **`Terrain3D` (TokisanGames)** — suporta *Clipmap* na GPU, até 32 materiais PBR, *detiling* estocástico (elimina o padrão quadriculado repetitivo visto de longe), *Triplanar Mapping* em encostas íngremes e instanciamento nativo de folhagem com LODs.
* **Iluminação e Pós-Processamento Obrigatórios (`WorldEnvironment`):**
  * **Tonemap:** `AgX` (preserva cores sob luz forte e elimina pele/brilho branco estourado).
  * **Global Illumination:** `SDFGI` (mundos abertos dinâmicos) ou `VoxelGI` / `LightmapGI` (interiores e arenas de alta fidelidade).
  * **Oclusão e Reflexos:** `SSAO` + `SSIL` (luz indireta em espaço de tela) + `SSR` (reflexos em água e armadura molhada) + `ReflectionProbes` locais.
  * **Atmosfera:** `PhysicalSkyMaterial` (ou HDRI 4K/8K de céu real) + `VolumetricFog` com densidade ligada à distância e altura (*aerial perspective* — separa primeiro plano, plano médio e fundo!).
  * **Sombras:** `DirectionalLight3D` com `PSSM 4 Splits`, `Shadow Bias` calibrado para evitar *peter-panning* (personagem parecendo flutuar acima da própria sombra) e `Contact Shadows` quando suportado.

### 7.3 Composição Modular, Biomas e Vegetação
* **Kits Arquitetônicos Modulares:** Construir muralhas, torres, pontes, ruas e casas em grid métrico rigoroso ($2\text{ m}, 4\text{ m}, 8\text{ m}$) usando **Trim Sheets** (uma única textura 4K contendo molduras, tijolos, vigas e metais reutilizável em dezenas de estruturas).
* **Scatter Hierárquico de Biomas (PCG):** Distribuir ativos em cascata com *Poisson Disk Sampling* + regras de declive/umidade:
  1. Árvores grandes (com raio de exclusão entre troncos + **Octahedral Impostors** a partir de $80\text{ m}$).
  2. Rochas estruturais e afloramentos (em áreas de alta inclinação).
  3. Arbustos e troncos caídos (próximos às raízes das árvores).
  4. Grama, flores e pedregulhos (via `MultiMeshInstance3D` agrupado por *chunks*, com *vertex wind shader* e *ground color blending* na base para fundir a grama ao solo).
* **Storytelling Ambiental:** Adicionar *Decals* (manchas de umidade, rachaduras, trilhas de carroça, folhas acumuladas nas quinas) e *Vertex Painting* para quebrar qualquer aparência "estéril ou recém-saída de fábrica".

---

## 8. CATÁLOGO DE BANCOS DE DADOS, DATASETS E FERRAMENTAS ABERTAS

A IA e o aplicativo devem conectar-se a fontes reais de dados calibrados em vez de tentar sintetizar tudo matematicamente do zero:

### 8.1 Captura de Movimento (Mocap & Animação)
| Dataset / Biblioteca | Conteúdo & Pontos Fortes | Uso Recomendado no Pipeline |
| :--- | :--- | :--- |
| **AMASS** *(Archive of Motion Capture as Surface Shapes)* | Mais de 40 horas de mocap unificados no padrão SMPL/SMPL-X (inclui CMU, BMLrub, ACCAD, Eyes Japan, etc.). | Base mestra de treino, biblioteca universal de locomoção e poses naturais. |
| **LAFAN1** *(Ubisoft)* | 4,6 horas de mocap de altíssima qualidade (77 sequências longas: corrida, salto, luta, combate, obstáculos, escalada). | Padrão-ouro para **Motion Matching** e transição de combate/ação. |
| **100STYLE** | 100 estilos diferentes de caminhada e corrida (BVH 60 fps: cansado, pesado/armadura, furtivo, orgulhoso, ferido). | Personalidade de NPCs e variação de peso (ex.: cavaleiro pesado vs. civil). |
| **Motion-X** | Mocap de corpo inteiro + mãos + expressões faciais + descrições textuais. | Sincronização de gestos de mãos, fala e expressões faciais. |
| **Mixamo** | Biblioteca pronta de animações de combate medieval, espada/escudo, arco e locomoção básica. | Prototipagem rápida e biblioteca inicial de ataques/defesas. |
| **HumanML3D** | Pares texto $\leftrightarrow$ movimento 3D anotados. | Busca semântica de animações por prompt no aplicativo. |

### 8.2 Anatomia, Pele, Scans e Materiais PBR
| Fonte / Dataset | Licença / Tipo | Uso Recomendado |
| :--- | :--- | :--- |
| **Poly Haven** (`polyhaven.com`) | **CC0** (100% livre, API pública) | HDRIs 4K/8K para Look-Dev e céus, texturas PBR escaneadas e props ambientais. |
| **AmbientCG** (`ambientcg.com`) | **CC0** (API pública) | Biblioteca massiva de PBR (pedra, metal, tecido, couro, solo, madeira, folhagem). |
| **USC ICT Wikihuman** (*Digital Emily 2*) | Pesquisa / Estudo aberto | Referência científica de calibração de shaders de pele, mapas *Specular/SSS/Micro-Displacement*. |
| **Texturing.xyz** & **3DScanStore** | Comercial + Amostras gratuitas | Padrão-ouro de mapas multi-canal de pele, poros, íris e scans de cabeça/corpo humano. |
| **MPFB2 (MakeHuman for Blender 4+)** | AGPL / CC0 (assets base) | Excelente para **malha base paramétrica e proporções corporais**, desde que substitua obrigatoriamente os materiais padrão, olhos e cabelos pelo pipeline AAA deste documento. |
| **OpenTopography / NASA SRTM / Copernicus DEM** | Dados públicos abertos | Heightmaps reais da superfície terrestre para gerar terrenos indiscutivelmente realistas. |
| **Material Maker** *(baseado em Godot)* | MIT (Open Source) | Alternativa livre ao Substance Designer para gerar materiais PBR procedurais e atlas de *hair cards* via grafos. |

### 8.3 Stack de Software Automatizável (CLI / Headless)
* **Modelagem, Grooming, Retopo e Baking:** Blender 4.x/5.x (`blender --background --python script.py`) + Geometry Nodes + Cycles Baker.
* **Engine & Renderização em Tempo Real:** Godot 4.x (Forward+ Vulkan) + `Terrain3D` + `Godot Jolt Physics`.
* **Geração 3D Auxiliar (IA $\rightarrow$ Blockout):** TRELLIS.2 / Hunyuan3D / Tripo / Rodin — usados exclusivamente para gerar *props*, peças ornamentais de armadura ou *base sculpts* que entram na esteira automática de retopologia e *baking*.
* **Geração de Texturas & De-lighting:** Modelos de difusão/PBR (ex.: Chord / Material-Diffusion / MatFuse) + scripts de remoção de iluminação assada (*Delighting*) e extração de mapas `Normal`, `Roughness`, `Height` e `AO`.

---

## 9. ARQUITETURA DO APLICATIVO & LOOP DE AUTO-MELHORIA DA IA

O motivo pelo qual agentes de IA "penam" criando sistemas 3D complexos é tentar resolver geometria, cabelo, shader, física e mapa de forma monolítica e sem **validação objetiva**. O aplicativo deve ser arquitetado como uma **Esteira Modular com Auditoria Visual e Geométrica Automática**.

### 9.1 Arquitetura Modular de Pipeline (Separação de Responsabilidades)
```text
[1. Specification & Seed] (Prompt / Blueprint JSON do Personagem ou Mapa)
         │
         ├──► [2. Character Forge (Blender Headless)]
         │      ├─ 2a. Base Body & Proportions (MPFB2 / Parametric Morphs)
         │      ├─ 2b. Armor & Clothing Generator (Hard-Surface + Cloth Sim + Retopo)
         │      ├─ 2c. Grooming Engine (Scalp Cap + 4-Layer Hair Cards + Normal Transfer)
         │      ├─ 2d. UV Packer + High-to-Low Cage Baker (Normal, AO, Curvature, Thickness)
         │      ├─ 2e. PBR Material Calibrator (ORM Packing + Skin Zones + Hair Atlas)
         │      └─ 2f. Rigging & Weight Transfer (Humanoid Skeleton + Rigid Armor Weights)
         │
         ├──► [3. Motion Forge (Python / Blender / Godot)]
         │      ├─ 3a. Dataset Indexer (LAFAN1 / 100STYLE / AMASS / Mixamo)
         │      ├─ 3b. Retargeting + Root Motion Extraction + Foot Contact Curves
         │      └─ 3c. Godot AnimationTree + Foot IK + Inertialization/Motion Matching
         │
         ├──► [4. World Forge (Python Erosion + Godot Terrain3D)]
         │      ├─ 4a. Heightmap + Hydraulic/Thermal Erosion + Splatmaps (EXR/PNG)
         │      ├─ 4b. Modular Architecture Assembler (Grid + Trim Sheets)
         │      └─ 4c. Biome Scatter (MultiMesh LODs + Impostors + Volumetric Atmosphere)
         │
         └──► [5. Automated Look-Dev & QA Validator (Loop Fechado)]
                ├─ 5a. Geometry & Rig Unit Tests (Python assertions)
                ├─ 5b. Standardized Turntable Render (Godot Headless / Cycles)
                └─ 5c. Vision Critique & Auto-Fix Loop (até passar todos os critérios)
```

### 9.2 Estúdio Padronizado de Look-Dev (Obrigatório para Testes da IA)
A IA **nunca** deve avaliar um personagem ou cabelo sob iluminação improvisada ou fundo preto absoluto sem luz de recorte. Toda iteração deve renderizar automaticamente em um **Look-Dev Rig fixo**:
* **Fundo:** Cinza neutro calibrado ($18\%$ reflectância / `#4A4A4A` sRGB), igual ao padrão de estúdio de VFX.
* **Iluminação:** HDRI de estúdio neutro + 3 pontos calibrados (*Key Light* $45^\circ$, *Fill Light* suave, *Rim Light* traseira para revelar silhueta e translucidez do cabelo/orelhas).
* **Esferas de Calibração no canto da cena:** 1 esfera cromada (`Metallic = 1, Roughness = 0`), 1 esfera cinza $18\%$ (`Metallic = 0, Roughness = 0.5`) e paleta *Macbeth ColorChecker* (garante instantaneamente se a exposição/tonemapper `AgX` está correta!).
* **Câmeras Automáticas de Inspeção:**
  1. Corpo inteiro (Frente, 3/4, Perfil, Costas).
  2. Close-up de rosto (olhos, poros, SSS nas orelhas).
  3. Close-up da linha do cabelo (*hairline*), topo (*crown*) e nuca (*nape*).
  4. Teste de estresse de pose (braços levantados $120^\circ$, agachamento profundo, rotação de pescoço $60^\circ$ — revela imediatamente descolamento de cabelo, *clipping* de armadura e deformação ruim!).

### 9.3 Checklist Automático de QA (Asserções em Código)
Antes de exibir qualquer resultado ao usuário ou considerá-lo pronto, o pipeline deve executar validações programáticas que bloqueiam exportações quebradas:

1. **Geometria & Transformações:**
   * `scale == (1.0, 1.0, 1.0)` e `rotation == (0.0, 0.0, 0.0)` em todos os objetos exportados.
   * Zero faces degeneradas, zero normais invertidas (teste de consistência de volume), zero N-gons em malhas com *Armature*.
2. **Validação Específica de Cabelo:**
   * Distância entre vértices da base do *Scalp Cap* e a malha da cabeça $< 0.002\text{ m}$ (detecta automaticamente "peruca flutuando"!).
   * 100% dos vértices das *Hair Cards* possuem peso somado $= 1.0$ vinculado ao osso `Head` (ou cadeia de ossos de cabelo filha de `Head`).
   * Cobertura angular do crânio verificada por projeção de *raycasts* de fora para dentro (detecta buracos carecas no topo/nuca).
3. **Validação PBR & Texturas:**
   * Nenhum mapa `Normal`, `Roughness`, `Metallic` ou `AO` configurado como `sRGB` (todos estritamente `Linear / Non-Color`).
   * Albedo de dielétricos dentro do intervalo físico ($0.04 \text{ – } 0.85$ sRGB — evita preto absoluto que mata sombras e branco estourado que quebra o *bloom*).
   * Normal maps no padrão **OpenGL (`+Y`)** exigido pelo Godot 4 e glTF 2.0 (se a fonte for DirectX `-Y`, inverter automaticamente o canal verde `G = 1.0 - G`).
4. **Validação de Animação:**
   * Posição $Y$ mínima dos pés na pose de repouso e nos frames de apoio dentro de $[-0.01\text{ m}, +0.02\text{ m}]$ do plano do chão.
   * Zero *NaN* ou *gimbal lock* nos *quaternions* das curvas de animação.

---

## 10. DIRETRIZ EXECUTIVA PARA O AGENTE DE IA (SYSTEM PROMPT / REGRAS DE CONDUTA)

> **Instrução direta para a IA construtora do aplicativo:**
> 1. **Proibido improvisar cabelo com tubos/geometria sólida crua.** Implemente um sistema real de *Hair Cards* com *Scalp Cap*, camadas hierárquicas, *Normal Transfer* de uma casca suave, atlas multi-canal (`Alpha`, `Depth`, `Root`, `ID`, `Flow`, `AO`) e shader anisotrópico (`Marschner/Kajiya-Kay`) com `ALPHA_HASH`.
> 2. **Proibido avaliar qualidade visual sem Look-Dev calibrado.** Configure `AgX` no Godot 4, iluminação HDRI + 3 pontos + fundo cinza neutro e rode testes de pose de estresse antes de iterar.
> 3. **Use dados reais da indústria.** Integre bibliotecas reais (`Poly Haven`, `AmbientCG`, `LAFAN1`, `100STYLE`, `AMASS`, `Terrain3D`, `Godot Jolt`) em vez de gerar texturas e movimentos simplistas por código puro.
> 4. **Separe malha de simulação, malha de renderização e pesos rígidos.** Metal não dobra como borracha; cabelo herda transformação da cabeça; terreno precisa de erosão hidráulica e *splatmaps*; pés precisam de *Root Motion* + *Foot IK* + *Foot Locking*.
> 5. **Valide matematicamente antes de renderizar.** Escreva testes automatizados em Python (`bpy`) e GDScript para garantir escala métrica, transformações zeradas, empacotamento ORM, orientação `+Y` das normais e aderência do cabelo ao crânio.