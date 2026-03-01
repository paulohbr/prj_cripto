#!/bin/bash
# Inicia todos os serviços de trading

cd "$(dirname "$0")"

echo "========================================"
echo "🚀 Iniciando Sistema de Trading"
echo "========================================"

# Verifica se serviços systemd estão instalados
if [ -f /etc/systemd/system/trading-api.service ]; then
    echo "Usando systemd..."
    systemctl start trading-api.service
    sleep 2
    systemctl start trading-dashboard.service
    sleep 2
    
    echo ""
    echo "📊 Status:"
    systemctl is-active trading-api.service && echo "   ✅ API rodando" || echo "   ❌ API falhou"
    systemctl is-active trading-dashboard.service && echo "   ✅ Dashboard rodando" || echo "   ❌ Dashboard falhou"
else
    echo "Serviços não instalados. Execute: ./install_services.sh"
    exit 1
fi

echo ""
echo "========================================"
echo "✅ Sistema iniciado!"
echo ""
echo "   📊 Dashboard: http://84.247.189.244:8501"
echo "   🔌 API:       http://84.247.189.244:5000/api/health"
echo ""
echo "   Logs:"
echo "   - journalctl -u trading-api -f"
echo "   - journalctl -u trading-dashboard -f"
echo "========================================"
