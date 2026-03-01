#!/bin/bash

# Script para verificar status do sistema
# Uso: ./status.sh

echo "=========================================="
echo "📊 Status do Sistema"
echo "=========================================="

# Diretório do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BOT_PID_FILE="$SCRIPT_DIR/bot.pid"
DASHBOARD_PID_FILE="$SCRIPT_DIR/dashboard.pid"

echo ""
echo "🤖 Bot de Trading:"
echo "-------------------"
if [ -f "$BOT_PID_FILE" ]; then
    BOT_PID=$(cat "$BOT_PID_FILE")
    if ps -p "$BOT_PID" > /dev/null 2>&1; then
        echo "   Status: ✅ Rodando"
        echo "   PID: $BOT_PID"
        echo "   Uptime: $(ps -p $BOT_PID -o etime= | xargs)"
        echo "   CPU: $(ps -p $BOT_PID -o %cpu= | xargs)%"
        echo "   Memória: $(ps -p $BOT_PID -o %mem= | xargs)%"
    else
        echo "   Status: ❌ Parado (PID file existe mas processo não)"
    fi
else
    echo "   Status: ❌ Parado"
fi

echo ""
echo "📊 Dashboard:"
echo "-------------------"
if [ -f "$DASHBOARD_PID_FILE" ]; then
    DASHBOARD_PID=$(cat "$DASHBOARD_PID_FILE")
    if ps -p "$DASHBOARD_PID" > /dev/null 2>&1; then
        echo "   Status: ✅ Rodando"
        echo "   PID: $DASHBOARD_PID"
        echo "   Uptime: $(ps -p $DASHBOARD_PID -o etime= | xargs)"
        echo "   CPU: $(ps -p $DASHBOARD_PID -o %cpu= | xargs)%"
        echo "   Memória: $(ps -p $DASHBOARD_PID -o %mem= | xargs)%"
        
        # Tenta detectar a porta
        PORT=$(lsof -Pan -p $DASHBOARD_PID -i 2>/dev/null | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -1)
        if [ -n "$PORT" ]; then
            echo "   URL: http://localhost:$PORT"
        fi
    else
        echo "   Status: ❌ Parado (PID file existe mas processo não)"
    fi
else
    echo "   Status: ❌ Parado"
fi

echo ""
echo "💾 Banco de Dados:"
echo "-------------------"
if [ -f "$SCRIPT_DIR/trading_data.db" ]; then
    DB_SIZE=$(du -h "$SCRIPT_DIR/trading_data.db" | cut -f1)
    echo "   Status: ✅ Presente"
    echo "   Tamanho: $DB_SIZE"
    
    # Conta registros (se sqlite3 estiver instalado)
    if command -v sqlite3 &> /dev/null; then
        TRANSACOES=$(sqlite3 "$SCRIPT_DIR/trading_data.db" "SELECT COUNT(*) FROM transacoes" 2>/dev/null || echo "N/A")
        RESULTADOS=$(sqlite3 "$SCRIPT_DIR/trading_data.db" "SELECT COUNT(*) FROM resultados" 2>/dev/null || echo "N/A")
        echo "   Transações: $TRANSACOES"
        echo "   Resultados: $RESULTADOS"
    fi
else
    echo "   Status: ❌ Não encontrado"
fi

echo ""
echo "📋 Logs:"
echo "-------------------"
if [ -f "$SCRIPT_DIR/logs/bot.log" ]; then
    BOT_LOG_SIZE=$(du -h "$SCRIPT_DIR/logs/bot.log" | cut -f1)
    BOT_LOG_LINES=$(wc -l < "$SCRIPT_DIR/logs/bot.log")
    echo "   Bot Log: $BOT_LOG_SIZE ($BOT_LOG_LINES linhas)"
fi
if [ -f "$SCRIPT_DIR/logs/dashboard.log" ]; then
    DASH_LOG_SIZE=$(du -h "$SCRIPT_DIR/logs/dashboard.log" | cut -f1)
    DASH_LOG_LINES=$(wc -l < "$SCRIPT_DIR/logs/dashboard.log")
    echo "   Dashboard Log: $DASH_LOG_SIZE ($DASH_LOG_LINES linhas)"
fi

echo ""

