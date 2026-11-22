# Avisos de terceiros

## Ignis (licença MIT)

Estes arquivos vieram do Ignis (https://github.com/kaikydev1-jpg/Ignis) e
continuam sob a licença MIT abaixo:

- `crates/fornalha-core/src/gpu/` (detecção da placa de vídeo)
- `crates/fornalha-core/src/distro.rs` (reconhecer o sistema Linux)
- `crates/fornalha-core/src/janela.rs` (estilo dos botões da janela)
- `crates/fornalha-core/src/util.rs` (parte das utilidades)
- `crates/fornalha-core/tests/fixtures/`, `tests/comum/` e `tests/deteccao.rs`
- a casca do aplicativo em `app/src-tauri` (bandeja, janela em processo
  separado e a lógica da barra de título integrada); o visual da janela
  (`app/ui`) é próprio da Fornalha

```
MIT License

Copyright (c) 2026 Os autores do Ignis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Fonte Archivo

`app/ui/fontes/archivo.woff2` — The Archivo Project Authors, SIL Open Font
License 1.1 (texto em `app/ui/fontes/OFL-Archivo.txt`).

## Programas e modelos que a Fornalha usa, mas não leva dentro dela

- **Blender** (GPL) e **Godot** (MIT) / **Erethea Engine**: rodam como programas
  separados, por linha de comando. Os arquivos que eles geram são do estúdio. O Blender 5.2.4 e a
  Godot 4.6.1 podem ser baixados pela janela (Máquina → Programas → Baixar), dos sites oficiais, com a
  soma publicada conferida; ficam na pasta de dados da Fornalha, sem mudar nada no sistema.
- **Modelos de placa** (TRELLIS.2 e UniRig, MIT; HY-Motion, licença comunitária
  da Tencent): baixados dos repositórios oficiais para a pasta de dados da
  Fornalha, só quando a pessoa instala pela janela. O nvdiffrast (licença só de
  pesquisa) não é instalado nem carregado.
- **Ignis**: programa separado, falado só por 127.0.0.1.
- **Motor de imagem** (instalado só quando a pessoa clica em Máquina → Motor de imagem → Instalar):
  o **ComfyUI** (GPL-3.0) com o nó ComfyUI-GGUF (Apache 2.0), processo à parte falado só por
  127.0.0.1; ou o **stable-diffusion.cpp** (MIT, github.com/leejet/stable-diffusion.cpp, versão
  fixa master-1045-6225bf8 conferida pelo SHA-256, com ggml MIT, libwebp e libwebm BSD), chamado
  pela linha de comando nas placas sem CUDA nem ROCm. Os modelos (Z-Image Turbo, Qwen3-4B e o VAE
  ae, Apache 2.0) estão em `manifest/modelos.json`.
- **3D pela IA no ComfyUI** (opcional, depois do aceite): TRELLIS.2 (MIT, arquivos de Comfy-Org/TRELLIS.2),
  codificador DINOv3 (DINOv3 License da Meta — uso comercial permitido; proibido para fins militares,
  armas reais, espionagem e para quem está sob sanções; o aceite é da pessoa, pela janela) e BiRefNet
  (MIT). O fluxo `crates/fornalha-core/comfyui/trellis2_imagem_para_malha.json` é o modelo oficial do
  ComfyUI (Comfy-Org/workflow_templates, licença MIT, Copyright (c) 2023-present Comfy Org).

## Visualizador 3D da janela

`app/ui/vendor/model-viewer.min.js` — Google `<model-viewer>` 4.0.0 (Apache 2.0),
que inclui three.js (MIT) e Lit (BSD-3-Clause). Fica dentro do app; não acessa a internet.

## Pacotes de conteúdo (baixados só quando a pessoa pede)

- **MakeHuman** (malha base, formas, esqueletos, pesos, pele, olhos, cabelo, roupas): CC0.
  A Fornalha lê só os dados; o código do MPFB (GPL) não é usado.
- **Quaternius Universal Animation Library 1 e 2**: CC0.
- **ambientCG** (texturas PBR e céus HDRI): CC0.
