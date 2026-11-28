# Teste noturno no PC do criador (roteiro para o agente, sem a pessoa por perto)

Máquina: Windows 11, AMD Radeon RX 580 2048SP (8 GB), Ryzen 5 5500, Smart App Control ligado.
Quem roda: uma sessão nova do Claude Code no computador do criador, enquanto ele dorme. Ele lê o relatório
de manhã e leva a parte da Fornalha para o chat da Fornalha e a parte da Erethea para o chat da Erethea. As
duas vão ser atualizadas depois deste teste: o relatório é a lista do que corrigir e do que falta.

## Regras (do CLAUDE.md do projeto; valem a noite toda)
- **Português do Brasil** em tudo (relatório, mensagens).
- **Não aceite licença no lugar da pessoa** e **não ponha chave de API**: isso é só pela janela, pela pessoa.
  Se faltar um aceite (DINOv3 do 3D pela IA) ou a chave (cérebro por API), pule o teste e anote no relatório.
- **Não desligue** o Smart App Control, o antivírus nem nenhuma proteção. Se o Windows barrar um executável,
  anote qual e siga (os binários do `cargo test` são barrados; o `fornalha-cli` e o app rodam).
- **Não apague** nada fora das pastas de teste criadas nesta noite (os projetos do criador ficam como estão).
- **Não publique** versão, não troque a licença do repositório e **não faça push**: esta sessão só lê o
  repositório. Correção de código fica para as sessões da Fornalha e da Erethea, com o relatório.
- **Não diga que funciona sem prova**: cada item do relatório diz o que rodou, o tempo e onde está a prova
  (arquivo, imagem, registro). O que não deu para rodar fica como "não testado" com o motivo.
- Se uma etapa falhar, **anote e siga para a próxima** (não pare a noite por causa de um item); tente de novo
  uma vez só se o erro parecer passageiro (rede, arquivo em uso).
- O PC fica ligado a noite toda: anote o valor de `powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE`, use
  `powercfg /change standby-timeout-ac 0` durante o teste e volte o valor anterior no fim.

## 0. Preparar (≈ 10 min)
1. **O que o criador já deixou feito** (confira e anote o que faltar, sem fazer por ele):
   - a variável de usuário `FORNALHA_HOME=C:\Fornalha` (confira com
     `[Environment]::GetEnvironmentVariable('FORNALHA_HOME','User')`); se o terminal desta sessão ainda não
     tiver a variável, defina nele (`$env:FORNALHA_HOME='C:\Fornalha'`) antes de qualquer `fornalha-cli`;
   - o zip **fornalha-windows** em `Downloads` (ou a Fornalha nova já instalada);
   - o aceite da licença do **DINOv3** na janela (Licenças) — libera o 3D pela IA;
   - o **Ignis** aberto (com ou sem modelos preparados);
   - opcional: a chave do Claude ou do Gemini em Agentes → Cérebro por API, ligada.
2. **Pastas:** com `FORNALHA_HOME`, a configuração fica em `C:\Fornalha\config`, os programas, motores,
   pacotes e registros em `C:\Fornalha\dados` (ferramentas: Blender, Godot, Erethea; comfyui; pacotes) e os
   projetos em `C:\Fornalha\dados\projetos`. Clone o repositório em `C:\Fornalha\codigo` e grave o relatório e
   as provas em `C:\Fornalha\Teste noturno`. A Fornalha da bandeja precisa ter sido aberta **depois** do
   `setx` (senão usa as pastas antigas): feche (bandeja → Sair) e abra de novo depois de instalar (passo 1.2).
3. **Repositório:** `git clone https://github.com/kaikyolf29-hub/Fornalha C:\Fornalha\codigo` (ou `git pull`) e
   `git checkout claude/eloquent-brahmagupta-75ilfh`. Leia o `CLAUDE.md`, o `ESTADO.md` (rodadas de 27 e
   28/11), o `TESTE_DO_CRIADOR.md` (seções 0, 0b, 9f e 9g) e este arquivo.
4. **Máquina:** anote a versão do Windows, o driver da AMD, a RAM livre e o disco livre (precisa de ~40 GB).

## 1. Atualizar a Fornalha
1. O instalador: o zip **fornalha-windows** que o criador deixou em `Downloads` (da execução mais recente com
   ✓ do workflow **Instaladores** no ramo acima). Sem ele, tente `gh run download -R kaikyolf29-hub/Fornalha
   -n fornalha-windows` (se o `gh` estiver logado); sem os dois, siga com o `fornalha-cli` do passo 1.3 e anote
   que a janela não foi atualizada.
2. Feche a Fornalha aberta (bandeja → Sair, ou `taskkill /IM fornalha.exe`), extraia o zip, rode o
   `Fornalha_0.1.0_x64-setup.exe /S` (sem perguntar, por usuário, sem administrador) e abra
   `%LOCALAPPDATA%\Fornalha\fornalha.exe`. Confira: a data do `fornalha.exe` mudou e
   `http://127.0.0.1:11480/fornalha/ferramentas` lista `get_engine_contract` (ferramenta nova desta rodada).
3. `fornalha-cli`: em `C:\Fornalha\codigo`, `cargo build --release -p fornalha-cli` (sem Rust, instale pelo
   `rustup`; o criador já usou nesta máquina em 25/11). Use `target\release\fornalha-cli.exe` daqui em diante.
   Ele usa a mesma pasta de dados do app.

## 2. Ferramentas (os mesmos botões da janela, pela linha de comando)
1. `fornalha-cli detectar` → anote a placa, o caminho escolhido (esperado: **vulkan** na RX 580) e o nível sugerido.
2. `fornalha-cli baixar-programa blender` e `... erethea` (pula o que já estiver achado). **Não baixe a Godot:**
   o criador usa a Erethea, que é a engine de todo projeto da Fornalha; a Godot só entraria como reserva sem a
   Erethea. Se a Erethea do criador (em `C:\Fornalha\Erethea`) for a 1.0.3, use ela; se for mais antiga,
   instale a 1.0.3 pelo botão. A Erethea vem pelo instalador público
   **1.0.3**, com a soma conferida (corrige o cabelo fio a fio escuro na coroa e o mapa de normais no
   renderizador de compatibilidade); o MCP dela liga sozinho na porta 11481 em projetos com
   `game.project.json`. Se houver outra Erethea neste PC (noutra pasta), anote o caminho e a versão, mas
   use a 1.0.3. Na janela, a barra lateral (Oficina) tem de mostrar **Erethea Engine** com a versão: tire um
   print.
3. `fornalha-cli baixar-pacote makehuman`, `... animacoes`, `... materiais`, `... accad` (o `100style` tem
   1,5 GB: só se sobrar tempo).
4. Motor de imagem: `fornalha-cli comfyui instalar` (esperado: motor Vulkan com os modelos gguf, ~6 GB). Teste:
   `fornalha-cli comfyui gerar "templário medieval, sobreveste branca com cruz vermelha" --lado 1024 --saida templario.png`
   e anote o tempo.
5. 3D pela IA no processador: **só se o aceite do DINOv3 estiver em Licenças** (confira em `get_status`).
   Ele precisa de um **Python 3.10+ do sistema** (o do Blender não cria o ambiente do ComfyUI). Sem
   `python --version` respondendo 3.10 ou mais, instale o 3.12 só para este usuário:
   `winget install -e --id Python.Python.3.12 --scope user` (ou o instalador de python.org com "Add python.exe
   to PATH"); depois abra um terminal novo (ou ponha a pasta do Python no `PATH` deste) e feche e abra a
   Fornalha da bandeja, para os dois enxergarem o Python. Com o aceite e o Python:
   `fornalha-cli comfyui instalar --3d` (~8,5 GB). Sem o aceite: pule os testes 3.5 e 3.6 e
   anote "falta o aceite do DINOv3 pela janela".
6. Ignis: se ele aparecer como "aberto, sem modelos preparados", o cérebro, a voz e a imagem dele não entram:
   anote e siga (a Fornalha usa as regras e o motor de imagem dela). Não prepare modelo que peça aceite.

## 3. Testes (nesta ordem; anote o tempo de cada um)
Chame as ferramentas com `fornalha-cli chamar <ferramenta> "<json>"` (ou pelo MCP em
`http://127.0.0.1:11480/mcp`). Guarde cada prova em `C:\Fornalha\Teste noturno\<número do teste>\`.
1. **Uso do processador:** com a Fornalha gerando (teste 3.3), `Get-Process blender | Select-Object Name,
   PriorityClass` → esperado **BelowNormal**; o PC continua respondendo.
2. **Teste Bruto na Erethea:** `fornalha-cli teste-bruto --nivel qualidade` e depois `--nivel maximo`.
   Esperado: os 4 casos (protagonista, inimigo armado, zumbi, dragão) com `"passou": true`, o jogo rodando na
   Erethea e "pode vender". Guarde o `teste_bruto.json` de cada um.
3. **Personagem Máximo com cabelo comprido, na Erethea:** projeto novo (`create_project`), nível `maximo`
   (`update_project`), `create_character` humano de cabelo comprido, `import_to_engine` e `run_test`.
   Esperado: o cabelo fio a fio aparece na Erethea (os cards somem) e a coroa perto da risca **não** fica
   escura (corrigido na 1.0.3). Guarde as capturas.
4. **Regras do corpo e contrato:** no mesmo projeto, `check_motion` com `corrigir: true` → esperado
   `regras_do_corpo` no resultado, `dedos_por_mao: 5` e as 15 animações aprovadas (ou corrigidas);
   `get_engine_contract` → esperado `ai/contrato_da_engine.json` com o personagem em `personagens_no_disco` e
   o esqueleto `fornalha-jogo-1`.
5. **Item pelo caminho grátis** (só com o 3D pela IA): `generate_3d` com
   `{"pedido": "baú de madeira com ferragens de ferro", "tipo": "objeto", "altura_m": 0.7}` no nível Máximo.
   Leva horas. Anote o tempo de cada etapa (conceito, malha, quatro vistas, limpeza) e guarde o conceito, as
   folhas antes/depois e o item. Enquanto ele roda, siga com o 3.7 (o 3D usa o processador; a Erethea abre).
6. **Quatro vistas num personagem** (só se sobrar noite depois do 3.5): `create_character` com o 3D pela IA
   no Máximo. Anote o tempo total e guarde a pasta `<id>_vistas/`.
7. **Os dois juntos (Fornalha + Erethea),** com o projeto do 3.3:
   a. abra o editor da Erethea com o projeto (`erethea.exe --editor --path <projeto>`);
   b. o MCP da Erethea em `http://127.0.0.1:11481/mcp` responde (JSON-RPC por HTTP: `initialize`,
      `tools/list`): anote a lista inteira das ferramentas dela e se já existem `run_script` e alguma de gerar
      animação por texto;
   c. `take_screenshot` da cena e, com o arquivo da captura, `check_style` da Fornalha (quanto está na paleta);
   d. confira os critérios de `conferencia_da_cena` do contrato que dá para medir (personagens presentes,
      animações com os nomes certos, esqueleto, objetos, estilo, sem erros) e anote cada um;
   e. `run_test` da Fornalha com o `--agent-test=<pasta>` da Erethea;
   f. se o projeto tiver `World/mapa/mapa.json` (crie um com `generate_map` se não tiver), o `montar.gd`
      montou o mapa (captura de cima). Feche o editor no fim.
8. **Anime:** num projeto com `guia_visual.render = "anime"`, um personagem de cabelo comprido montado na
   Erethea → esperado: contorno e luz em faixas pelo script da Fornalha, e os cards do cabelo (sem os fios).
9. **Cérebro por API** (só se o criador ligou o Claude ou o Gemini, com a chave): com o Ignis fechado,
   `plan_request` com `{"pedido": "um ferreiro que martela na bigorna e a música da vila", "executar": "nao"}`
   → esperado `origem: "cerebro"` e `cerebro: "api:<modelo>"`. Custa centavos. Não mexa na chave.

## 4. Relatório (no fim, mesmo que algo tenha falhado)
Grave `C:\Fornalha\Teste noturno\RELATORIO.md` e mostre o texto inteiro no chat. Comece por uma tabela de
tempos (cada instalação e cada teste) e depois três partes:

**Para a Fornalha** (o criador leva ao chat da Fornalha), em quatro listas:
- *Funcionou*: item, tempo, prova (caminho).
- *Falhou*: item, a mensagem de erro inteira, o final do registro (`C:\Fornalha\dados\registros\*.log` ou o
  log da tarefa) e o que você acha que causou.
- *Não testado*: item e o motivo (faltou aceite, chave, tempo, programa).
- *Precisa* (para a próxima versão): o que faltou, confundiu ou demorou demais, com prioridade (alta, média,
  baixa) — por exemplo, um passo que só dá pela janela, um erro sem explicação, um tempo grande demais.

**Para a Erethea** (o criador leva ao chat da Erethea), nas mesmas quatro listas: abrir o projeto da
Fornalha, a importação, a ponte, o `montar.gd`, o `--agent-test`, o cabelo fio a fio e a coroa, o anime, o MCP
dela (a lista de ferramentas e o que faltou para o pacote de IA: `run_script`, animação por texto, cena
conferida), com as capturas. Diga também o que a Erethea precisaria ler do `ai/contrato_da_engine.json` que
não está lá.

**Para o criador**: o que só ele pode fazer ou olhar (aceites, chaves, conferir as imagens com os próprios
olhos e dar uma nota de 0 a 100 ao personagem e ao baú comparando com o conceito, abrir o jogo e jogar).

No fim, volte o tempo de suspensão do Windows ao valor anotado e diga no chat onde está o relatório.
