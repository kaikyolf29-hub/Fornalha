#!/usr/bin/env bash
# Baixa o Blender e a Godot para os testes de geração no CI (Linux e Windows/Git Bash)
# e grava os caminhos em FORNALHA_TESTE_BLENDER / FORNALHA_TESTE_GODOT.
set -euo pipefail
BLENDER_VERSAO="5.2.4"
GODOT_VERSAO="4.6.1"
DESTINO="${1:-$HOME/ferramentas}"
mkdir -p "$DESTINO"
cd "$DESTINO"
if [ "${RUNNER_OS:-Linux}" = "Windows" ]; then
  if [ ! -f blender/blender.exe ]; then
    curl -fsSL --retry 3 -o blender.zip "https://download.blender.org/release/Blender${BLENDER_VERSAO%.*}/blender-${BLENDER_VERSAO}-windows-x64.zip"
    7z x -y blender.zip > /dev/null && rm blender.zip && mv "blender-${BLENDER_VERSAO}-windows-x64" blender
  fi
  if [ ! -f godot/godot_console.exe ]; then
    curl -fsSL --retry 3 -o godot.zip "https://github.com/godotengine/godot/releases/download/${GODOT_VERSAO}-stable/Godot_v${GODOT_VERSAO}-stable_win64.exe.zip"
    mkdir -p godot && 7z x -y -ogodot godot.zip > /dev/null && rm godot.zip
    mv godot/Godot_v${GODOT_VERSAO}-stable_win64_console.exe godot/godot_console.exe
    mv godot/Godot_v${GODOT_VERSAO}-stable_win64.exe godot/godot.exe
  fi
  BLENDER="$(cygpath -w "$DESTINO/blender/blender.exe")"
  GODOT="$(cygpath -w "$DESTINO/godot/godot_console.exe")"
else
  if [ ! -x blender/blender ]; then
    curl -fsSL --retry 3 -o blender.tar.xz "https://download.blender.org/release/Blender${BLENDER_VERSAO%.*}/blender-${BLENDER_VERSAO}-linux-x64.tar.xz"
    tar -xf blender.tar.xz && rm blender.tar.xz && mv "blender-${BLENDER_VERSAO}-linux-x64" blender
  fi
  if [ ! -x godot/godot ]; then
    curl -fsSL --retry 3 -o godot.zip "https://github.com/godotengine/godot/releases/download/${GODOT_VERSAO}-stable/Godot_v${GODOT_VERSAO}-stable_linux.x86_64.zip"
    mkdir -p godot && unzip -oq godot.zip -d godot && rm godot.zip
    mv "godot/Godot_v${GODOT_VERSAO}-stable_linux.x86_64" godot/godot && chmod +x godot/godot
  fi
  BLENDER="$DESTINO/blender/blender"
  GODOT="$DESTINO/godot/godot"
fi
echo "Blender: $BLENDER"
echo "Godot: $GODOT"
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "FORNALHA_TESTE_BLENDER=$BLENDER" >> "$GITHUB_ENV"
  echo "FORNALHA_TESTE_GODOT=$GODOT" >> "$GITHUB_ENV"
fi
