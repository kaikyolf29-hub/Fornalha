# Teste noturno no PC do criador (roteiro para o agente, sem a pessoa por perto)

Máquina: Windows 11, AMD Radeon RX 580 2048SP (8 GB), Ryzen 5 5500, Smart App Control ligado.
Quem roda: uma sessão nova do Claude Code no computador do criador, enquanto ele dorme. Ele lê o relatório
de manhã e leva a parte da Fornalha para o chat da Fornalha e a parte da Erethea para o chat da Erethea.

## Regras (do CLAUDE.md do projeto; valem a noite toda)
- **Português do Brasil** em tudo (relatório, mensagens).
- **Não aceite licença no lugar da pessoa** e **não ponha chave de API**: isso é só pela janela, pela pessoa.
  Se faltar um aceite (DINOv3 do 3D pela IA) ou a chave (cérebro por API), pule o teste e anote no relatório.
- **Não desligue** o Smart App Control, o antivírus nem nenhuma proteção. Se o Windows barrar um executável,
  anote qual e siga (os binários do `cargo test` são barrados; o `fornalha-cli` e o app rodam).
- **Não apague** nada fora das pastas de teste criadas nesta noite (os projetos do criador ficam como estão).
- **Não publique** versão, não troque a licença do repositório, não faça push em `main`. Esta sessão só lê o
  repositório (não precisa fazer push).
- **Não diga que funciona sem prova**: cada item do relatório diz o que rodou, o tempo e onde está a prova
  (arquivo, imagem, registro). O que não deu para rodar fica como "não testado" com o motivo.
- O PC fica ligado a noite toda: se o Windows estiver para suspender, use `powercfg /change standby-timeout-ac 0`
  só durante o teste e volte o valor anterior no fim (anote o valor antes).

## 0. Preparar (≈ 10 min)
1. Repositório: `git clone https://github.com/kaikyolf29-hub/Fornalha` (ou `git pull` se já existir) e
   `git checkout claude/eloquent-brahmagupta-75ilfh`. Leia `ESTADO.md` (a rodada de 27/11), `TESTE_DO_CRIADOR.md`
   (seções 0, 0b, 9f e 9g) e este arquivo.
2. Anote: versão do Windows, driver da AMD, RAM livre, disco livre (precisa de ~40 GB livres para tudo).

## 1. Atualizar a Fornalha
1. O instalador novo: a execução mais recente com ✓ do workflow **Instaladores** no ramo acima, artefato
   **fornalha-windows** (`Fornalha_0.1.0_x64-setup.exe`). Se o criador deixou o zip em `Downloads`, use ele;
   senão baixe com `gh run download -R kaikyolf29-hub/Fornalha -n fornalha-windows` (precisa do `gh` logado).
   Sem o instalador, siga com o `fornalha-cli` do passo 2 e anote que o app (janela) não foi atualizado.
2. Feche a Fornalha aberta (bandeja → Sair, ou `taskkill /IM fornalha.exe`), rode o instalador com `/S`
   (sem perguntar, por usuário, sem administrador) e abra `%LOCALAPPDATA%\Fornalha\fornalha.exe`.
   Confira que a data do `fornalha.exe` mudou e que `http://127.0.0.1:11480/fornalha/ferramentas` lista
   `get_engine_contract` (ferramenta nova desta rodada).
3. `fornalha-cli`: no repositório, `cargo build --release -p fornalha-cli` (se não houver Rust, instale pelo
   `rustup` — o criador já usou nesta máquina em 25/11). Use `target\release\fornalha-cli.exe` daqui em diante.
   Ele usa a mesma pasta de dados do app.

## 2. Ferramentas (pelos mesmos botões da janela, pela linha de comando)
1. `fornalha-cli detectar` → anote placa, caminho escolhido (esperado: **vulkan** na RX 580) e nível sugerido.
2. `fornalha-cli baixar-programa blender`, `... godot` e `... erethea` (pula o que já estiver achado; a Erethea
   vem pelo instalador público 1.0.2 ou mais novo, com a soma conferida). **Erethea mais nova que a 1.0.2:**
   a Erethea estava preparando um instalador novo com correções (27/11). Veja
   https://github.com/kaikyolf29-hub/-Erethea-Engine/releases: se houver versão mais nova que a v1.0.2, baixe
   o `erethea-setup-x86_64.exe` dela, confira o SHA-256 com o "digest" da página da release (`Get-FileHash`)
   e instale no mesmo lugar do botão, sem perguntas:
   `erethea-setup-x86_64.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /NORESTART /DIR="<pasta de dados da Fornalha>\ferramentas\erethea"`
   (a pasta de dados aparece em `get_status` → `downloads_de_programas` ou no caminho do Blender baixado).
   Anote no relatório a versão usada e o SHA-256. Se não houver versão nova, use o botão (1.0.2). Se já houver outra Erethea neste PC
   (compilada pelo criador, noutra pasta), anote o caminho e a versão dela no relatório, mas teste com a
   instalada pelo botão. Na janela, a barra lateral (Oficina) tem de mostrar **Erethea Engine** com a versão
   (a Godot só aparece como "reserva"): tire um print.
3. `fornalha-cli baixar-pacote makehuman`, `... animacoes`, `... materiais`, `... accad` (o `100style` tem
   1,5 GB: só se sobrar tempo).
4. Motor de imagem: `fornalha-cli comfyui instalar` (esperado: motor Vulkan com os modelos gguf). Teste:
   `fornalha-cli comfyui gerar "templário medieval, sobreveste branca com cruz vermelha" --lado 1024 --saida templario.png`
   e anote o tempo.
5. 3D pela IA no processador: **só se o aceite do DINOv3 já estiver em Licenças** (confira em `get_status` →
   o estúdio / licenças aceitas). Com o aceite: `fornalha-cli comfyui instalar --3d` (~8,5 GB). Sem o aceite:
   pule os testes 3.5 e 3.6 e anote "falta o aceite do DINOv3 pela janela".

6. Ignis: o criador deixa o Ignis aberto (versão mais nova). Se ele aparecer como "aberto, sem modelos
   preparados", o cérebro, a voz e a imagem dele não entram: anote e siga (a Fornalha usa as regras e o motor
   de imagem dela). Não prepare modelo que peça aceite de licença.

## 3. Testes (em ordem; anote o tempo de cada um)
Use uma pasta de teste nova (por exemplo `Documentos\Fornalha\Noite 27-11`) e chame as ferramentas com
`fornalha-cli chamar <ferramenta> "<json>"` (ou pelo MCP em `http://127.0.0.1:11480/mcp`).
1. **Uso do processador:** `fornalha-cli chamar get_status "{}"` funciona; com a Fornalha gerando (teste 3.3),
   veja `Get-Process blender | Select-Object Name, PriorityClass` → esperado **BelowNormal**. Anote também o
   número de threads do Blender com a opção "Metade dos núcleos" (Ajustes) — se não der para mudar sem a
   janela, teste só a prioridade.
2. **Teste Bruto** na Erethea: `fornalha-cli teste-bruto --nivel qualidade` e depois `--nivel maximo`.
   Esperado: os 4 casos com `"passou": true`, o jogo rodando na engine e "pode vender". Guarde o
   `teste_bruto.json` de cada um.
3. **Personagem Máximo com cabelo comprido, montado na Erethea:** projeto novo (`create_project`), nível
   `maximo` (`update_project`), `create_character` humano de cabelo comprido, `import_to_engine` e `run_test`
   com a Erethea. Esperado: o cabelo fio a fio aparece na Erethea (os cards somem). Guarde as capturas e
   anote se a coroa perto da risca sai escura (pedido 7 da Erethea).
4. **Regras do corpo e contrato:** no mesmo projeto, `check_motion` com `corrigir: true` no personagem →
   esperado `regras_do_corpo` no resultado e `dedos_por_mao: 5`; `get_engine_contract` → esperado
   `ai/contrato_da_engine.json` com o personagem em `personagens_no_disco` e o esqueleto `fornalha-jogo-1`.
5. **Item pelo caminho grátis** (só com o 3D pela IA instalado): `generate_3d` com
   `{"pedido": "baú de madeira com ferragens de ferro", "tipo": "objeto", "altura_m": 0.7}` no nível Máximo.
   Leva horas (no CI de 4 núcleos o baú passou de 3 h; agora tem menos passos). Anote o tempo de cada etapa
   (conceito, malha, quatro vistas, limpeza) e guarde o conceito, as folhas antes/depois e o item.
6. **Quatro vistas num personagem** (só se sobrar noite depois do 3.5): `create_character` com o 3D pela IA
   no Máximo. Anote o tempo total e guarde a pasta `<id>_vistas/`.
7. **Os dois juntos (Fornalha + Erethea):** com o projeto do 3.3: (a) abra o editor da Erethea com o projeto
   (`erethea.exe --editor --path <projeto>`); (b) o MCP da Erethea em `http://127.0.0.1:11481/mcp` responde
   (JSON-RPC por HTTP: `initialize`, `tools/list`) — anote as ferramentas dela (procure `run_script`,
   `take_screenshot`, `get_errors`); (c) `take_screenshot` da cena e, com o arquivo da captura,
   `check_style` da Fornalha; (d) `run_test` da Fornalha com o `--agent-test` da Erethea; (e) o `montar.gd`
   montou o mapa (se o projeto tiver `World/mapa/mapa.json`). Feche o editor no fim.
8. **Cérebro por API** (só se o criador ligou o Claude ou o Gemini na janela, com a chave): com o Ignis
   fechado, `plan_request` com `{"pedido": "um ferreiro que martela na bigorna e a música da vila", "executar": "nao"}`
   → esperado `origem: "cerebro"` e `cerebro: "api:<modelo>"`. Custa centavos. Não mexa na chave.

## 4. Relatório (no fim, mesmo que algo tenha falhado)
Grave `Documentos\Fornalha\Noite 27-11\RELATORIO.md` e mostre o texto inteiro no chat, em duas partes:
- **Para a Fornalha:** cada item do 1 ao 3 com passou/falhou/não testado, o tempo, a prova (caminho do
  arquivo) e, se falhou, a mensagem de erro inteira e o final do registro (`dados\...\*.log`).
- **Para a Erethea:** o que é dela (abrir o projeto, a ponte, `montar.gd`, `--agent-test`, cabelo fio a fio
  e a coroa escura, as ferramentas do MCP dela e se `run_script` já existe), com as capturas.
No fim, volte o tempo de suspensão do Windows ao valor anotado.
