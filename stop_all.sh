#!/bin/bash
# Para todos os serviços de trading

echo "🛑 Parando serviços..."

# Tenta parar via systemctl primeiro
if systemctl is-active --quiet trading-api.service 2>/dev/null; then
    systemctl stop trading-api.service
    echo "   ✅ API parada (systemd)"
fi

if systemctl is-active --quiet trading-dashboard.service 2>/dev/null; then
    systemctl stop trading-dashboard.service
    echo "   ✅ Dashboard parado (systemd)"
fi

# Fallback: mata processos diretamente
pkill -f "python3 api_trading.py" 2>/dev/null
pkill -f "streamlit run Dashboard" 2>/dev/null

echo "✅ Todos os serviços parados."
