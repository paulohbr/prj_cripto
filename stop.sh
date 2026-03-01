#!/bin/bash
# Para serviços de trading
# Uso: ./stop.sh

cd /home/user/projetos/prj_criptos >/dev/null 2>&1

# Detecta se precisa de sudo
[ "$EUID" -eq 0 ] && SUDO="" || SUDO="sudo"

# Para serviços systemd (silencioso)
$SUDO systemctl stop trading-bot trading-api trading-dashboard >/dev/null 2>&1

exit 0

