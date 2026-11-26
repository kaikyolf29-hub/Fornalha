#!/usr/bin/env bash
# Instala pacotes do Ubuntu no CI com tempo limite e 3 tentativas.
# Se o espelho padrão do GitHub não responder, troca para outro espelho oficial.
set -u
export DEBIAN_FRONTEND=noninteractive
APT=(-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o DPkg::Lock::Timeout=120)
ESPELHO="http://mirrors.edge.kernel.org/ubuntu/"

trocar_espelho() {
  echo "Trocando o espelho do Ubuntu para $ESPELHO"
  for f in /etc/apt/apt-mirrors.txt /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do
    [ -f "$f" ] || continue
    sudo sed -i -E "s#https?://(azure\.)?archive\.ubuntu\.com/ubuntu/?#${ESPELHO}#g; s#https?://security\.ubuntu\.com/ubuntu/?#${ESPELHO}#g" "$f"
  done
}

# repositórios de fora do Ubuntu que vêm na máquina do GitHub (Microsoft, etc.): a Fornalha não usa nenhum,
# e quando um deles cai (o da Microsoft passou a responder 403 em 26/11) o "apt-get update" inteiro falha
desligar_repositorios_de_fora() {
  for f in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    [ -f "$f" ] || continue
    if grep -qE "packages\.microsoft\.com|ppa\.launchpadcontent\.net|apt\.postgresql\.org|dl\.google\.com" "$f"; then
      echo "Desligando $f (repositório de fora, não usado aqui)"
      sudo mv "$f" "$f.desligado"
    fi
  done
}
desligar_repositorios_de_fora

for t in 1 2 3; do
  [ "$t" -ge 2 ] && trocar_espelho
  sudo dpkg --configure -a || true
  if sudo -E timeout 300 apt-get "${APT[@]}" update && sudo -E timeout 900 apt-get "${APT[@]}" install -y "$@"; then
    exit 0
  fi
  echo "apt travou ou falhou (tentativa $t)"
  sleep 15
done
exit 1
