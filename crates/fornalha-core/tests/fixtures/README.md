# Fixtures de detecção

Saídas de `vulkaninfo --summary`, `rocminfo`, `nvidia-smi --query-gpu=...` e
leituras do `/sys` (em JSON) para as placas do briefing.

**Importante:** estas saídas foram montadas no formato exato das ferramentas
(vulkaninfo 1.4, rocminfo do ROCm 6/7, nvidia-smi 580), com os IDs PCI e nomes
reais de cada placa, mas **não foram capturadas numa máquina com a placa**.
O TESTE_DO_CRIADOR.md pede para salvar as saídas reais
(`vulkaninfo --summary > vulkaninfo.txt`, etc.) e substituir aqui.

Fixtures acrescentadas na Fornalha (também montadas, não capturadas):
`rtx4060ti16-windows` (RTX 4060 Ti 16 GB no Windows, DXGI + nvidia-smi), a
placa planejada para o nível Qualidade.
