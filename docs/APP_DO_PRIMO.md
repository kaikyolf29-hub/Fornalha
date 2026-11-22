# App do primo (Tilemap 3D) — o que entra na Fornalha 3D

> O criador recebeu o código do primo com permissão para juntar as duas ferramentas (21/11/2026).
> Analisado o código-fonte (C# .NET 8 + WebView2 + three.js, MCP, geradores de personagem em JS).
> O código fica fora do repositório público; aqui só o que vamos trazer e onde.

## O que ele faz melhor
| Área | O que tem | Onde entra na Fornalha |
|---|---|---|
| **Fidelidade à referência** | Mede a silhueta da imagem de referência (frente em T-pose) linha a linha e coluna a coluna: largura do tronco por altura, braços, contorno do cabelo; tira escala, centro e chão da imagem; folha "referência × modelo" sobreposta | Etapa 1.1/1.7: a concept art (Ignis, ComfyUI ou API) passa a **ajustar o corpo e as roupas** (proporções do MakeHuman, largura de peças) e o look-dev mostra a sobreposição com a referência |
| **Rig** (`rig.js`) | Limites de rotação anatômicos (tabelas clínicas, perfis rígido/normal/atleta), IK de 2 ossos com polo, olhar, IK em corrente (cauda, cobra), **corpo sólido** (cápsulas por osso que impedem a malha de atravessar ela mesma), física de ossos determinística gravada nos quadros do GLB | Etapa 1.6: depois do retarget de captura, aplicar limites + corpo sólido (o braço com armadura não atravessa o tronco) e gravar a física de capa/cabelo/cauda; IK em corrente para criaturas (Etapa 2.2) |
| **Animações próprias** | Biblioteca de espada e escudo e de personagens (golpes, defesa) feita por quadros-chave com IK | Etapa 1.6/2.3: completar o que falta na Quaternius (escudo, golpes pesados), convertendo para o esqueleto da Fornalha |
| **Estilos não realistas** | Personagens nível PS2/anime (5–8 mil triângulos), malha anel a anel com nariz e mãos modelados, textura pintada por funções (músculos, sarja, malha canelada, costuras em pesponto, vincos, sombra por raios), **expressões por UV** (quadros de olhos e boca, troca deslocando o UV) | Etapa 1.9 (estilos): caminho "pintado à mão / cel-shaded / PS2 / low poly" e expressões para personagens estilizados |
| **Mapa** | Tiles com atlas, paisagem esculpível (elevar, suavizar, nivelar, ruído, pintar só encosta ou só plano), geradores (terreno, sala, masmorra), objetos de jogo com propriedades em JSON, teste em primeira pessoa, GLB com `-colonly` e objetos como nós vazios com `extras` | Etapa 2.1: gerador de masmorra e salas, pintura por inclinação no terreno, e a Fornalha passa a **ler mapas do Tilemap 3D** (objetos de jogo viram cenas na Godot/Erethea) |
| **MCP e segurança** | Cada edição de agente = um Ctrl+Z; modo "só ver"; agentes só gravam tipos de arquivo conhecidos; painel do que cada agente fez; ponte stdio que só abre o app na 1ª ferramenta | Etapa 1.7: modo "só ver", histórico por agente e desfazer por edição na janela da Fornalha |
| **Conferência** | Antes de entregar: faixa de polígonos, objeto único, GLB (malhas, materiais, ossos), fotos frente/perfil/costas no enquadramento da referência | Já coberto pelo QA da bíblia (Etapa 1.1); a sobreposição com a referência é o que falta |

## O que a Fornalha leva para ele
Humanos realistas (MakeHuman, pele 4K, cabelo AAA), armaduras PBR com desgaste assado, captura de
movimento com retarget, licenças e recibos, Godot/Erethea com teste automático, Ignis (cérebro,
imagem, voz). Os dois falam MCP: um agente pode usar os dois na mesma tarefa.
