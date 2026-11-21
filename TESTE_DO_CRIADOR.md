# Teste do criador (Fase 0)

Coisas que **só a sua máquina prova**. Tudo o que dava para testar sem placa e sem a sua tela já foi
testado (veja ESTADO.md). Cada passo diz o que fazer e o que deve acontecer. Se algo der diferente,
tire um print e me conte o passo.

## 0. Instalar (Windows 10 ou 11)
1. Abra **https://github.com/kaikyolf29-hub/Fornalha/actions/workflows/instaladores.yml** (logado no GitHub).
2. Clique na execução mais recente com ✓ verde e, em *Artifacts*, baixe **fornalha-windows**.
3. Extraia o zip e rode o `Fornalha_0.1.0_x64-setup.exe`.
   - Se aparecer "O Windows protegeu o computador": **Mais informações → Executar assim mesmo** (ainda sem assinatura digital).
   - **Esperado:** não pede administrador; ao terminar, a Fornalha abre.

## 1. Janela e bandeja
- **Sem a barra cinza do sistema:** o topo é da própria Fornalha, com minimizar, maximizar e fechar no estilo do Windows 11.
- Arrastar pelo topo move a janela; duplo clique maximiza e restaura; o X fica vermelho com o mouse em cima; bordas e cantos redimensionam; arrastar até a borda da tela encaixa (Aero Snap).
1. Feche no X. **Esperado:** a janela some e o ícone da fornalha continua perto do relógio.
2. Clique no ícone. **Esperado:** a janela volta.
3. Botão direito no ícone. **Esperado:** menu com **Abrir Fornalha**, "API e MCP em 127.0.0.1:11480" (cinza) e **Sair**.
4. Abra a Fornalha de novo pelo menu Iniciar com ela já aberta. **Esperado:** não abre outra; traz a janela que existe.

## 2. Placa e níveis
Abra **Placa e níveis**.
- **RX 580 8 GB:** "Sugerido: Leve", CUDA: não, ROCm: não, Vulkan.
- **RTX 4060 Ti 16 GB / 5060 Ti 16 GB:** "Sugerido: Qualidade", com CUDA.
- A tabela mostra os 4 níveis com o modelo de cada função; o nível em uso fica destacado.
- **Esperado também:** a linha "3D com textura" com traço (—). Passe o mouse no traço: explica que o TRELLIS.2 usa o nvdiffrast (só pesquisa). É o achado do ESTADO.md.

Se o nome da placa ou a memória vierem errados, me mande um print dessa tela.

## 3. Criar um projeto pela janela
1. Em **Projetos**, preencha o nome (ex.: "Reino de Cinzas"), gênero e câmera, e clique **Criar projeto**.
2. **Esperado:** aviso "Projeto criado em …", o cartão "Projeto aberto" e o projeto nos recentes.
3. Clique **Abrir a pasta**. **Esperado:** o Explorador abre a pasta com `GameDesign`, `World`, `Characters`… e o `game.project.json`.

## 4. O teste de pronto: o Claude Code cria um projeto pelo MCP
Com a Fornalha aberta:
1. No terminal: `claude mcp add --transport http fornalha http://127.0.0.1:11480/mcp`
2. `claude mcp list`. **Esperado:** `fornalha … ✓ Connected`.
3. Abra o Claude Code e peça: *"Crie um projeto novo na Fornalha chamado Teste do Claude, um action RPG em terceira pessoa."*
   - **Esperado:** o Claude Code chama `create_project` e responde com a pasta.
4. Volte à janela, em **Projetos**. **Esperado:** "Teste do Claude" aparece como projeto aberto.
5. Peça também: *"Qual modelo a Fornalha usa para o cérebro e para a música no meu nível?"* — ele deve chamar `choose_model`.

Variante com o app fechado: **Agentes → Claude Code (mesmo com o app fechado) → Copiar**, rode o
comando no terminal e repita o passo 3 com a Fornalha fechada (Sair no ícone).

## 5. Licenças
1. Em **Licenças**, ligue **Aceito** na licença da Tencent.
2. Volte em **Placa e níveis**. **Esperado:** a Animação no Equilibrado, Qualidade e Máximo passa de "Biblioteca própria" para HY-Motion.
3. No projeto criado, a seção "Antes de vender" diz "Tudo certo" (ainda não há assets).

## 6. Leve em repouso
Feche a janela (fica só o ícone), espere 1 minuto e veja no Gerenciador de Tarefas a memória do
`fornalha.exe`. Meta de referência (a do Ignis): perto de 60 MB e processador perto de 0%. Me diga o número.

## 7. Linux (opcional)
No artifact **fornalha-linux** há `.deb`, `.rpm` e `.AppImage`. No Fedora: `sudo dnf install ./Fornalha-*.rpm`.
O GNOME precisa da extensão AppIndicator para mostrar o ícone perto do relógio.
