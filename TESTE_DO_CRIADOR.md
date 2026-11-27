# Teste do criador (Fases 0 a 4)

Coisas que **só a sua máquina prova**. O que dava para testar sem placa e sem a sua tela já foi
testado, inclusive as gerações de verdade no Windows e no Linux do GitHub (veja ESTADO.md). Cada
passo diz o que fazer e o que deve acontecer. Se algo der diferente, tire um print e me conte o passo.

## 0. Instalar (Windows 10 ou 11)
1. Abra **https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/instaladores.yml** (logado no GitHub).
2. Clique na execução mais recente com ✓ verde e, em *Artifacts*, baixe **fornalha-windows**.
3. Extraia o zip e rode o `Fornalha_0.1.0_x64-setup.exe`.
   - Se aparecer "O Windows protegeu o computador": **Mais informações → Executar assim mesmo** (ainda sem assinatura digital).
   - **Windows 11 com o Controle Inteligente de Aplicativos (Smart App Control) ligado** (teste de 25/11 na
     RX 580): ele não tem o botão "Executar assim mesmo"; decide arquivo por arquivo se o programa sem
     assinatura pode rodar. O instalador, a Fornalha, o `fornalha-cli` e o motor de imagem rodaram, mas os
     binários de teste do `cargo test` foram barrados (`os error 4551`). Não desligue a proteção por causa
     da Fornalha: a assinatura digital dos executáveis está prevista para a Fase 5. Para testar o jogo com a
     placa sem o `cargo test`, use `fornalha-cli chamar run_test` (ou o botão Testar da janela).
   - **Esperado:** não pede administrador; ao terminar, a Fornalha abre.
4. Para gerar 3D e testar o jogo, a Fornalha usa programas de fora (grátis): o **Blender** e a **Godot**
   (ou a sua **Erethea Engine**). Em **Máquina → Programas**, clique em **Baixar 5.3.0 (≈ 430 MB)** no
   Blender e **Baixar 4.6.1 (≈ 70 MB)** na Godot. **Esperado:** "Baixando… N MB" e, no fim, o caminho
   em `…\Fornalha\dados\ferramentas\…` com a versão. A Fornalha confere a soma publicada pelo Blender
   e pela Godot antes de usar. Se você já tem os dois instalados, ela acha sozinha; se não achar,
   **Escolher** e aponte o executável (na Godot, o `_console.exe`).
5. Para ficha, imagem de conceito, voz e pedido livre: o **Ignis 0.4.0** aberto (porta 11470).

## 0b. Teste de Fogo na RX 580 (o roteiro curto)
Depois de instalar (passo 0), com o Blender e a Godot (ou a Erethea) achados em **Máquina**:
1. **Máquina → Motor de imagem → Instalar.** Esperado: o caminho escolhido é "vulkan" (stable-diffusion.cpp
   pelo Vulkan, que funciona na RX 580 com o driver da AMD) com modelos "gguf" e pouca VRAM; baixa ~6 GB
   (o programa tem 30 MB, o resto são os modelos) e mostra o progresso. Não precisa instalar Python nem
   Git: com o Blender baixado no passo 0, a Fornalha usa o Python que vem dentro dele. No fim aparece "Motor Vulkan pronto — AMD Radeon
   RX 580 Series". Se aparecer só "CPU", o Vulkan não achou a placa: atualize o driver da AMD e me conte.
   (O ComfyUI tirou o DirectML em 11/11/2026, por isso a RX 580 vai pelo Vulkan.)
   Teste rápido: com um projeto aberto, **Forjar → Conceito** com "templário medieval". A imagem sai em
   1024 px; me mande a imagem e quanto tempo levou (o recibo dela, em **Licenças**, diz
   "z-image-turbo-gguf-vulkan" e guarda os segundos).
2. **Máquina → Nível desta máquina → Qualidade** (e depois repita com **Máximo**). Numa placa de 8 GB
   isso funciona: a Fornalha pede ao Ignis para soltar a placa antes do motor de imagem (um modelo por
   vez) e o motor Vulkan decodifica em blocos e põe na RAM o que não couber.
3. **Máquina → Teste de Fogo → Rodar o Teste Bruto** (nível Qualidade; depois Máximo). Também dá para
   pedir ao Claude Code: "rode o run_brute_test no nível qualidade".
   Esperado: em alguns minutos, os 4 casos (protagonista completo, inimigo armado, zumbi, dragão) com
   `"passou": true`, o jogo rodando na engine e "pode vender". O relatório fica em
   `Documentos\Fornalha\Teste Bruto …\testes\teste_bruto.json` — me mande esse arquivo.
4. Abra o projeto "Teste Bruto …" na Godot/Erethea e jogue: o dragão aparece como inimigo.

## 1. Janela e bandeja
- O visual é o da Fornalha (grafite, cobre e brasa), com a barra de título dela e os botões no estilo do Windows 11.
- Arrastar pelo topo move; duplo clique maximiza; bordas redimensionam; arrastar até a borda encaixa (Aero Snap).
1. Feche no X. **Esperado:** a janela some e o ícone continua perto do relógio.
2. Clique no ícone. **Esperado:** a janela volta. Botão direito: **Abrir Fornalha**, "API e MCP em 127.0.0.1:11480" e **Sair**.
3. Abra de novo pelo menu Iniciar. **Esperado:** não abre outra; traz a que existe.

## 2. Máquina
- **RX 580 8 GB:** "Sugerido: Leve", CUDA: não. **Placa NVIDIA 16 GB:** "Sugerido: Qualidade", com CUDA.
- **Programas:** Blender e Godot (ou Erethea) com a versão e o caminho.
- **Modelos de placa:** com a RX 580, os três aparecem com "Precisa de placa NVIDIA (CUDA)". Normal.
- Tabela dos 4 níveis com o modelo de cada função; passe o mouse no traço para ver o motivo.

## 3. Projeto
1. Em **Projeto**, crie "Reino de Cinzas" (action RPG, terceira pessoa).
2. Ainda em **Projeto**, no editor da bíblia, escolha 3 ou 4 cores na **paleta**, as áreas do mundo (vila, floresta, arena) e a engine (**Godot** ou **Erethea**). Salve. A coluna da esquerda passa a mostrar o resumo.
3. **Abrir a pasta**: `GameDesign`, `World`, `Characters`… e o `game.project.json`.

## 4. Forjar
1. Molde **Personagem**: nome "Aren", "ferreiro com machado". **Esperado:** em 1 a 3 minutos aparece a prévia, a folha de modelo e (com o Ignis aberto) a imagem de conceito e a fala dublada.
2. Molde **Inimigo**: "orc grandalhão com martelo", marque **testar na engine**. **Esperado:** o inimigo é feito, a engine monta as cenas e roda o teste sozinha; o resultado diz "passou".
3. Molde **Arma** (espada), **Objeto** (barril), **Mundo**, **Música** (vila) e **Efeitos**.
4. **Pedido livre:** escreva *"um goblin inimigo, uma lança e a música da masmorra"* e clique **Fazer agora**. **Esperado:** aparece o plano (do cérebro, se o Ignis estiver aberto) e as tarefas rodam uma por vez na **Fila**.
5. Repita com **Deixar para a noite**. **Esperado:** as tarefas ficam "Esperando" e rodam no horário da noite (muda em Ajustes).

## 5. Galeria e guia visual
1. **Galeria:** cada asset com a prévia, o modelo que fez e "Pode vender".
2. **Conferir o guia visual.** **Esperado:** "X de Y dentro da paleta" e, se houver, os que fogem dela com o selo "Fora do guia".

## 6. Testar (o jogo)
1. **Montar na engine** e depois **Rodar teste**.
2. **Esperado:** o jogo abre (Godot ou Erethea), o herói anda, pula e ataca sozinho, o inimigo persegue; no fim, "passou", 0 erros, capturas e vídeo.
3. Abra a pasta do projeto na engine (Godot/Erethea → Importar → `project.godot`) e aperte F5 para jogar você mesmo (WASD, espaço, clique para atacar).
4. **Movimento (sentir na mão):** ande, solte as teclas e corra com Shift. **Esperado:** sai andando e para com um pouco de inércia, os pés não patinam no chão, a troca entre andar e correr é suave. Ataque andando (**esperado:** golpeia da cintura para cima sem parar as pernas). Pare numa rampa ou num degrau (**esperado:** os dois pés apoiados, um mais alto que o outro, o quadril desce). Gire a câmera com o mouse (**esperado:** a cabeça acompanha até uns 60° e volta para a frente quando a câmera vai para trás). Na Erethea, se ela for mais antiga que a Godot 4.6, o jogo roda sem o IK dos pés e sem o olhar (o resto igual).

## 7. O Claude Code usa tudo pelo MCP
Com a Fornalha aberta:
1. No terminal: `claude mcp add --transport http fornalha http://127.0.0.1:11480/mcp` e `claude mcp list` (**Esperado:** `fornalha … ✓ Connected`).
2. Peça: *"Na Fornalha, crie um inimigo novo, um esqueleto com espada, e teste no jogo."* **Esperado:** ele chama `create_character` com `testar_na_engine` e responde que o teste passou.
3. Peça: *"Deixe para a noite: a floresta com dois orcs e a música de combate."* **Esperado:** `plan_request` com `executar: noite`; as tarefas aparecem na Fila da janela.
4. Peça: *"Confira se os assets estão no guia visual."* (`check_style`).

## 8. Licenças
1. Em **Licenças**, ligue **Aceito** na licença da Tencent (só a pessoa pode, pela janela).
2. Com a RX 580 nada muda (o HY-Motion precisa de CUDA). Com a NVIDIA, a Animação passa a mostrar o HY-Motion.
3. No projeto, "Antes de vender" diz "Tudo certo".

## 9. Modelos de placa (quando a placa NVIDIA chegar)
Precisa do Git, do Python 3.10+ e, para o TRELLIS.2, do CUDA Toolkit 12.4.
1. **Máquina → Modelos de placa → Instalar** no TRELLIS.2. São vários GB; a linha de baixo mostra o andamento.
2. No fim, a Fornalha faz uma geração de teste. **Esperado:** "Pronto e verificado sem o nvdiffrast".
3. Crie um personagem com o Ignis aberto. **Esperado:** "modelo_3d" do TRELLIS.2, com textura (não a Forja).
4. Instale o UniRig e crie o esqueleto de uma criatura (`create_skeleton` com `criatura: true`).
5. Com o aceite da Tencent, instale o HY-Motion e peça *"uma animação dele acenando"*.
Isso ainda **não foi provado** numa placa de verdade: se der erro, me mande o `instalacao.log` da pasta do modelo.

## 9b. 3D pela IA, por partes (novo em 23/11)
Provado no CI (no processador, horas) e com vídeos aqui; falta provar no seu PC.
1. **Licenças:** aceite a licença do DINOv3 (Meta). **Máquina → Motor de imagem → Instalar o 3D pela IA.**
   Na RX 580 (sem CUDA nem ROCm) ele instala no processador e avisa que cada malha leva horas.
2. **Forjar → Personagem**, deixe ligado "Ver o conceito antes do 3D". **Esperado:** aparece a imagem de
   corpo inteiro com **Aceitar e fazer o 3D** e **Refazer**. Refazer gera outra; Aceitar faz a malha dessa.
3. No fim: o personagem com esqueleto de jogo, a mesma captura de movimento do vídeo que você aprovou,
   a espada no punho (lâmina para a frente no andar) e, se tiver escudo, o parado de escudo erguido.
   Numa placa com CUDA/ROCm, nos níveis Qualidade e Máximo, a cabeça sai por partes: recortada do
   conceito, refinada em close e encaixada no corpo (no processador ela passaria de 6 h, então fica de fora).
4. **Dragão:** Personagem com tipo **dragao**. Com o 3D pela IA instalado, ele sai pela IA com o esqueleto
   medido na malha (anda, voa, ruge, dá o bote); sem, sai da Forja de criaturas como antes.
5. **Monstro de qualquer corpo pela sua imagem (24/11):** num chat (Claude Code, Codex, ChatGPT) com o MCP
   da Fornalha, mande a imagem que você fez (do Gemini, por exemplo) e peça o personagem com `imagem` (o
   caminho do PNG) e `corpo: "auto"`. **Esperado:** a malha sai da sua imagem sem ser refeita, o esqueleto
   é achado sozinho (humanoide, alado ou de patas) e ele anda, corre e ataca. Provado no CI com uma
   fera-lobo de quatro patas (4,7 h no processador); na RX 580 conte horas por malha. Me diga se a cor
   ficou parecida com a sua imagem (a correção casa a textura com ela) e se alguma pata dobra errado.
6. **APIs pagas (opcional):** Máquina → APIs de 3D: Meshy, Tripo ou Rodin, com a sua chave e o liga/desliga.
   Só plano pago tem uso comercial. Ligada, o Personagem sai por ela em minutos.

## 9c. No jogo (novo em 23/11)
1. **Grama:** o chão do mundo é verde (antes saía branco), com terra batida nos caminhos e tufos de grama
   balançando ao vento. Me diga se os tufos pesam na RX 580 (FPS antes e depois de ir para o campo).
2. **Capa com mola:** no templário feito pela IA, ande e pare: a capa fica para trás e volta, sem
   atravessar as pernas.
3. **Cavaleiro da IA correndo e atacando (24/11):** os braços se movem como armadura (sem pano preso na
   manopla), a espada fica no punho nos golpes e a barra da sobreveste fica de pé na corrida (antes abria
   um "lençol" quando o joelho subia). Me diga se alguma placa do braço esquerdo, o da bainha, se solta.

## 9d. Referência, cabelo, barba e montagem por peças (novo em 26/11)
Num chat com o MCP da Fornalha (Claude Code, Codex, Gemini, Cursor…), mande a imagem de referência e peça:
1. *"Faça este personagem"* (ex.: a foto do Joel). **Esperado:** a IA chama `create_character` com
   `referencia`, `cabelo` (penteado, cor, volume, ondulação), `barba` (tipo, cor, comprimento), `idade`;
   a resposta traz a `comparacao` (imagem lado a lado em `ai/comparacoes/`). Ela ajusta e gera de novo.
   **Olhe:** o cabelo não parece capacete nem cola (mechas, volume, fios na ponta), a testa sem mancha
   clara, a barba saindo da pele (não colada). Dê a sua nota de 0 a 100 e o que falta.
2. *"Faça esta espada"* (uma imagem de arma). **Esperado:** `generate_3d` com `pecas` (lâmina com gume,
   guarda, cabo, pomo) e `referencia`; a comparação volta junto. A lâmina tem fio (afina na borda).
3. *"Faça uma casa como esta e use na vila do mapa."* **Esperado:** `generate_3d` (objeto, `pecas`) e
   `generate_map` com `regioes[].casas`; na foto da vila no `run_test` aparecem as casas montadas.
4. No jogo (Forward+, na placa): o cabelo com TAA (sem granulado) e a barba. **Me diga:** granulado, fios
   piscando, o cabelo atravessando a cabeça ao andar.
5. **Jogo de prova** (opcional, ~30 min): `node testes/mcp-e2e/jogo_de_prova.mjs <fornalha-cli>` faz um jogo
   pequeno inteiro só pelo MCP (herói com barba, três inimigos, espada e casa por peças, mapa com vila,
   floresta e cripta, música, efeitos, cena curta) e testa na engine. **Esperado:** "Jogo de prova completo".

## 9e. Estúdio 3D, roupa no manequim e soco (novo na noite de 26/11)
1. **Estúdio 3D** (janela → Movimento → *Abrir o personagem no estúdio*). **Esperado:** o personagem gira com
   o mouse, *Tocar* anima, a régua do tempo anda quadro a quadro (← →), as bolinhas dos ossos aparecem (as
   reprovadas em vermelho depois de *Conferir esta animação*), o rastro colorido da mão e do pé e da ponta
   da arma, chão em quadrados. Escolha um osso, gire (arrastando ou nos botões de 5°), *Gravar como nova*.
   **Me diga:** se ficou leve na RX 580 (girar e tocar sem engasgar), se o giro gravado bate com o que você
   viu, e o que falta para você ajustar um movimento sozinho.
2. *"Faça um manequim e, em cima dele, a armadura do templário desta imagem; vista e ponha um soco."* (com a
   referência). **Esperado:** `create_character` (roupa `manequim`) → `create_garment` (partes, imagens
   sozinha e no manequim de barro) → `dress_character` → `check_motion` → `apply_motion` (soco do ACCAD,
   punho fechado) → `show_motion` (quadros grandes). **Olhe:** pele furando a roupa, placa esticando no
   cotovelo, cruz descolando da saia, mão aberta no soco. **Nota de 0 a 100** para a armadura e para o soco.
3. *"Mostre o soco em anime."* **Esperado:** `show_motion` com `estilo: "anime"` (dois tons e contorno).
4. **3D pela IA no processador** (Máquina → Motor de imagem → *Instalar o 3D pela IA (no processador)*, depois
   do aceite do DINOv3 em Licenças). **Esperado:** o motor de imagem pelo Vulkan continua (a imagem segue
   rápida na RX 580) e aparece a linha "3D pela IA no processador: instalado". Peça um personagem no nível
   **Máximo** na fila da noite. **Me diga:** quanto tempo levou no Ryzen 5 5500 e como ficou a malha.

## 9f. Caminho grátis no Máximo: quatro vistas, cabelo fio a fio e Erethea (novo em 27/11)
1. **Personagem pelo 3D da IA no processador, nível Máximo** (fila da noite; sem placa NVIDIA e sem API).
   **Esperado:** depois da malha do TRELLIS.2, a Fornalha faz as **quatro vistas**: a malha vista de frente,
   dos lados e de costas, a frente pelo próprio conceito, os lados e as costas refinados pelo Z-Image (no
   processador) e o **rosto em close**; tudo volta na textura (4096 no Máximo). Na pasta do personagem fica
   `<id>_vistas/` com as imagens. **Olhe:** o rosto (olhos e boca no lugar, não manchas), o tecido e o couro
   parecidos com o conceito, sem remendo nem linha clara na roupa, os pés sem o chão do estúdio. **Me
   diga:** quanto tempo as vistas levaram no Ryzen 5 5500 e uma nota de 0 a 100 comparando com o conceito.
2. **Qualquer item do jogo pelo processador** (*"faça um baú de madeira com ferragens de ferro, 0,7 m"*, ou
   com uma imagem sua; nível Máximo, na fila da noite). **Esperado:** `generate_3d` com `pedido` faz o
   conceito, o 3D pela IA no processador, as quatro vistas e o item limpo em Items/ (ou Weapons/). **Me
   diga:** o tempo no Ryzen 5 5500 e uma nota de 0 a 100 comparando com o conceito.
3. **Cabelo fio a fio na Erethea** (personagem humano de cabelo comprido no nível Máximo, montado na
   Erethea 1.0.2 ou mais nova). **Esperado:** na Erethea o cabelo aparece fio a fio (os cards somem); na
   Godot comum, os cards de sempre. **Olhe:** a coroa perto da risca (aqui, sem placa, ela saiu escura: me
   diga se na RX 580 também sai).
4. **Erethea pelo botão** (Máquina → Programas → Erethea → *Baixar*). **Esperado:** baixa o instalador
   1.0.2, confere a soma e instala sem perguntar dentro da pasta da Fornalha.

## 9g. Uso do processador, cérebro por API, regras do corpo e o teste dos dois juntos (novo na noite de 27/11)
1. **Trabalhar enquanto a Fornalha gera** (Ajustes → Uso do processador → *Metade dos núcleos*; peça um item
   no Máximo). **Esperado:** o Gerenciador de Tarefas mostra o Blender/Python em prioridade *Abaixo do normal*
   e o PC continua usável (navegador, editor). **Me diga:** se travou alguma coisa e quanto a geração demorou
   a mais com metade dos núcleos.
2. **Cérebro por API (Agentes → Cérebro por API)**: cole a chave da Anthropic (Console → API Keys), deixe o
   *Claude Haiku 5.5 — econômico*, clique em *Atualizar lista* e ligue. Em **Pedir à IA**, com teto US$ 0,50:
   *"olhe o estado da Fornalha e me diga o que falta instalar"*. **Esperado:** o passo a passo aparece
   (chamou get_status, resultado, resposta) e o gasto fica em centavos. Depois: *"faça um plano para um
   ferreiro que martela na bigorna, aplique o movimento e confira"*. **Me diga:** o gasto mostrado, se bate
   com o Console da Anthropic, e se a resposta fez sentido. (O Gemini é igual, com a chave do AI Studio; no
   plano grátis o Google lê o que você manda.)
3. **Plano sem o Ignis:** com o Ignis fechado e o Claude ligado, `plan_request` pelo Claude Code.
   **Esperado:** `origem: "cerebro"` e `cerebro: "api:claude-haiku-5-5"` no resultado.
4. **Regras do corpo:** num personagem com dedos (humano realista), `check_motion` com `corrigir`.
   **Esperado:** no resultado, `regras_do_corpo` e, em cada clipe, `dedos_por_mao: 5`; captura do ACCAD que
   tremia sai suavizada. **Olhe** no Estúdio 3D as mãos no soco e no "pegar": dedo nenhum dobrado para trás.
5. **Os dois juntos (Fornalha + Erethea):** com a Erethea 1.0.2 ou mais nova instalada pelo botão,
   (a) crie um projeto pequeno na Fornalha (um personagem humano Máximo com cabelo comprido, um baú e a vila
   de blockout); (b) `import_to_engine` e `run_test` com a Erethea escolhida; (c) abra o projeto no editor da
   Erethea: o personagem anda, o cabelo aparece fio a fio, o mapa monta sozinho (`montar.gd`); (d) ligue os
   dois MCP no Claude Code (`claude mcp add` da Fornalha, em Agentes, e o da Erethea) e peça *"mude a cor da
   capa do personagem na Fornalha e mostre na Erethea"*. **Me diga:** o que abriu, o que não abriu, e as
   imagens do `take_screenshot` da Erethea.

## 10. Leve em repouso
Feche a janela, espere 1 minuto e veja no Gerenciador de Tarefas a memória do `fornalha.exe`.
Meta de referência (a do Ignis): perto de 60 MB e processador perto de 0%. Me diga o número.

## 11. Linux (opcional)
No artifact **fornalha-linux** há `.deb`, `.rpm` e `.AppImage`. No Fedora: `sudo dnf install ./Fornalha-*.rpm`.
O GNOME precisa da extensão AppIndicator para mostrar o ícone perto do relógio.
