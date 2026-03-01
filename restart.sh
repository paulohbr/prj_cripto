#!/bin/bash
# Inicia serviços de trading em background (silencioso)
# Uso: ./restart.sh [--clear-db]

cd /home/user/projetos/prj_criptos >/dev/null 2>&1

# Detecta se precisa de sudo
[ "$EUID" -eq 0 ] && SUDO="" || SUDO="sudo"

# Limpa banco se solicitado
[ "$1" == "--clear-db" ] && rm -f trading_data.db logs/bot.log >/dev/null 2>&1

# Cria banco se não existir
[ ! -f "trading_data.db" ] && python3 criar_banco.py >/dev/null 2>&1

# Instala serviços se não existirem
[ ! -f "/etc/systemd/system/trading-api.service" ] && {
    $SUDO cp trading-api.service /etc/systemd/system/ >/dev/null 2>&1
    $SUDO systemctl daemon-reload >/dev/null 2>&1
    $SUDO systemctl enable trading-api.service >/dev/null 2>&1
}

[ ! -f "/etc/systemd/system/trading-dashboard.service" ] && {
    $SUDO cp trading-dashboard.service /etc/systemd/system/ >/dev/null 2>&1
    $SUDO systemctl daemon-reload >/dev/null 2>&1
    $SUDO systemctl enable trading-dashboard.service >/dev/null 2>&1
}

[ ! -f "/etc/systemd/system/trading-bot.service" ] && {
    $SUDO cp trading-bot.service /etc/systemd/system/ >/dev/null 2>&1
    $SUDO systemctl daemon-reload >/dev/null 2>&1
    $SUDO systemctl enable trading-bot.service >/dev/null 2>&1
}

# Inicia serviços (silencioso, retorna imediatamente)
$SUDO systemctl daemon-reload >/dev/null 2>&1
$SUDO systemctl stop trading-api trading-dashboard trading-bot >/dev/null 2>&1
$SUDO systemctl start trading-api trading-dashboard trading-bot >/dev/null 2>&1

exit 0
