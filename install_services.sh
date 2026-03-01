#!/bin/bash
# Instala serviços systemd para API e Dashboard

cd "$(dirname "$0")"

echo "========================================"
echo "🔧 Instalando Serviços de Trading"
echo "========================================"

# Para processos antigos
echo "1️⃣  Parando processos antigos..."
pkill -f "python3 api_trading.py" 2>/dev/null
pkill -f "streamlit" 2>/dev/null
sleep 2

# Copia arquivos de serviço
echo "2️⃣  Instalando serviços systemd..."
cp trading-api.service /etc/systemd/system/
cp trading-dashboard.service /etc/systemd/system/

# Recarrega systemd
systemctl daemon-reload

# Habilita serviços para iniciar no boot
echo "3️⃣  Habilitando serviços..."
systemctl enable trading-api.service
systemctl enable trading-dashboard.service

# Inicia serviços
echo "4️⃣  Iniciando serviços..."
systemctl start trading-api.service
sleep 3
systemctl start trading-dashboard.service
sleep 2

# Verifica status
echo ""
echo "========================================"
echo "📊 Status dos Serviços"
echo "========================================"
echo ""
echo "🔌 API:"
systemctl status trading-api.service --no-pager | head -5
echo ""
echo "📊 Dashboard:"
systemctl status trading-dashboard.service --no-pager | head -5

echo ""
echo "========================================"
echo "✅ Instalação concluída!"
echo ""
echo "   URLs:"
echo "   - Dashboard: http://$(hostname -I | awk '{print $1}'):8501"
echo "   - API:       http://$(hostname -I | awk '{print $1}'):5000/api/health"
echo ""
echo "   Comandos úteis:"
echo "   - systemctl status trading-api"
echo "   - systemctl status trading-dashboard"
echo "   - journalctl -u trading-api -f"
echo "   - journalctl -u trading-dashboard -f"
echo "========================================"
