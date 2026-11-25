# Regras do criador para a Fornalha (vale para toda sessão de IA)

- **Sempre em português do Brasil**, com o criador e nos textos do app.
- Toda retomada começa pelo **ESTADO.md**. O trabalho atual segue o `docs/PLANO_3_ETAPAS.md` (25/11/2026); o plano original é o "Plano 1 · Fornalha" (resumo no README), o histórico de qualidade está em `docs/PLANO_2_ETAPAS.md` e a régua técnica em `docs/BIBLIA_TECNICA_AAA.md`.
- **A Erethea Engine é a principal; a Fornalha 3D é a ajudante da IA.** A Fornalha não traz jogo, mapa ou monstro pronto: dá à IA ferramentas, imagens e medidas. Antes de fazer algo de engine aqui, confira no repositório da Erethea (`kaikyolf29-hub/-Erethea-Engine`, `HANDOFF.md`) se ela já faz ou vai fazer.
- Siga o **padrão dos apps do criador** (`docs/` do Ignis: barra de título integrada, leve em repouso, instalação por sistema, sem telemetria). A casca do app veio do Ignis.
- **Licença é regra do app:** nenhum modelo sem licença comercial entra num projeto comercial. Todo modelo novo entra em `crates/fornalha-core/manifest/modelos.json` com licença, link e uso comercial conferidos na página dele.
- **Agente não aceita licença no lugar da pessoa:** aceite de licença e receita do estúdio só pela janela.
- **Teste antes de entregar:** `cargo fmt`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` e o teste do MCP (`testes/mcp-e2e`) verdes, e o CI verde no Windows e no Linux.
- **Não diga que algo funciona numa placa ou máquina real sem prova nela.** Separe o que foi provado (testes, CI) do que falta provar (TESTE_DO_CRIADOR.md).
- **Não publique** versão oficial: a venda e a atualização privada são da Fase 5 e só saem quando o criador pedir.
- O repositório é público **sem licença aberta** (todos os direitos reservados). Não troque a licença.
- Sem telemetria. A Fornalha só fala com 127.0.0.1 (a própria API e o Ignis) e, só quando a pessoa liga e põe a chave na janela, com as APIs de geração escolhidas (decisão do criador em 21/11/2026; desligadas por padrão, com preço e licença antes de gerar).
- Pedidos que dependem do Ignis entram na lista "Pedidos para o Ignis" do ESTADO.md; o criador leva para o chat do Ignis.
