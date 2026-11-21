# Workers de mentira (só para os testes)

Imitam a interface dos modelos de placa para o teste de ponta a ponta rodar sem
placa NVIDIA: o worker de verdade da Fornalha (`workers/*.py`) chama estes no
lugar do TRELLIS.2, do HY-Motion e do UniRig. O que eles devolvem tem o mesmo
formato dos modelos de verdade, com geometria e movimento simples.
