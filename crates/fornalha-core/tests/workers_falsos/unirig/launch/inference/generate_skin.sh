#!/usr/bin/env bash
# UniRig de mentira: mesmos argumentos dos scripts oficiais; só copia o arquivo.
while [ $# -gt 0 ]; do
  case "$1" in
    --input|--source) ENTRADA="$2"; shift 2 ;;
    --target) ALVO="$2"; shift 2 ;;
    --output) SAIDA="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cp "${ALVO:-$ENTRADA}" "$SAIDA"
