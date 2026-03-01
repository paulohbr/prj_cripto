#!/bin/bash
# Instala e inicia o serviço do bot de trading

cd /home/user/projetos/prj_criptos

# Detecta se precisa de sudo (se não for root)
if [ "$EUID" -eq 0 ]; then
    SUDO_CMD=""
else
    SUDO_CMD="sudo"
fi

echo "📦 Instalando serviço do bot de trading..."

# Copia o arquivo de serviço
$SUDO_CMD cp trading-bot.service /etc/systemd/system/

# Recarrega systemd
$SUDO_CMD systemctl daemon-reload

# Habilita o serviço para iniciar automaticamente
$SUDO_CMD systemctl enable trading-bot.service

echo "✅ Serviço instalado!"
echo ""
echo "🚀 Iniciando o bot..."
$SUDO_CMD systemctl start trading-bot

sleep 2

echo ""
echo "📊 Status:"
$SUDO_CMD systemctl is-active trading-bot && echo "   ✅ Bot rodando" || echo "   ❌ Bot falhou ao iniciar"

echo ""
echo "📋 Para ver os logs:"
echo "   $SUDO_CMD journalctl -u trading-bot -f"
echo "   ou"
echo "   tail -f logs/bot.log"
echo ""
echo "🔄 Para reiniciar:"
echo "   $SUDO_CMD systemctl restart trading-bot"

