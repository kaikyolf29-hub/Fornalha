# Teste do criador (Fases 0 a 4)

Coisas que **só a sua máquina prova**. O que dava para testar sem placa e sem a sua tela já foi
testado, inclusive as gerações de verdade no Windows e no Linux do GitHub (veja ESTADO.md). Cada
passo diz o que fazer e o que deve acontecer. Se algo der diferente, tire um print e me conte o passo.

## 0. Instalar (Windows 10 ou 11)
1. Abra **https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/instaladores.yml** (logado no GitHub).
2. Clique na execução mais recente com ✓ verde e, em *Artifacts*, baixe **fornalha-windows**.
3. Extraia o zip e rode o `Fornalha_0.1.0_x64-setup.exe`.
   - Se aparecer "O Windows protegeu o computador": **Mais informações → Executar assim mesmo** (ainda sem assinatura digital).
   - **Esperado:** não pede administrador; ao terminar, a Fornalha abre.
4. Para gerar 3D e testar o jogo, a Fornalha usa programas de fora (grátis): o **Blender** e a **Godot**
   (ou a sua **Erethea Engine**). Em **Máquina → Programas**, clique em **Baixar 5.2.4 (≈ 420 MB)** no
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
   Esperado: em alguns minutos, os 3 casos (protagonista completo, inimigo armado, dragão) com
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

## 10. Leve em repouso
Feche a janela, espere 1 minuto e veja no Gerenciador de Tarefas a memória do `fornalha.exe`.
Meta de referência (a do Ignis): perto de 60 MB e processador perto de 0%. Me diga o número.

## 11. Linux (opcional)
No artifact **fornalha-linux** há `.deb`, `.rpm` e `.AppImage`. No Fedora: `sudo dnf install ./Fornalha-*.rpm`.
O GNOME precisa da extensão AppIndicator para mostrar o ícone perto do relógio.
