#!/bin/bash

# Script para iniciar o Dashboard Streamlit em background
# Uso: ./start_dashboard.sh [porta]

echo "=========================================="
echo "📊 Iniciando Dashboard Streamlit"
echo "=========================================="

# Diretório do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Porta do dashboard (padrão: 8501)
PORT=${1:-8501}

# Arquivos de configuração e logs
PID_FILE="$SCRIPT_DIR/dashboard.pid"
LOG_FILE="$SCRIPT_DIR/logs/dashboard.log"

# Cria diretório de logs se não existir
mkdir -p "$SCRIPT_DIR/logs"

# Verifica se o dashboard já está rodando
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "❌ Dashboard já está rodando (PID: $OLD_PID)"
        echo "   Use ./stop_dashboard.sh para parar primeiro"
        exit 1
    else
        echo "⚠️  Arquivo PID encontrado mas processo não está rodando. Limpando..."
        rm "$PID_FILE"
    fi
fi

# Ativa virtual environment se existir
if [ -d "/home/user/projetos/venv_binance" ]; then
    echo "🐍 Ativando virtual environment (venv_binance)..."
    source "/home/user/projetos/venv_binance/bin/activate"
elif [ -d "$SCRIPT_DIR/venv_dashboards" ]; then
    echo "🐍 Ativando virtual environment..."
    source "$SCRIPT_DIR/venv_dashboards/bin/activate"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    echo "🐍 Ativando virtual environment..."
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Verifica se streamlit está instalado
if ! command -v streamlit &> /dev/null; then
    echo "❌ Streamlit não está instalado"
    echo "   Instale com: pip install streamlit"
    exit 1
fi

echo "🚀 Iniciando dashboard na porta $PORT..."
echo ""

# Executa o dashboard em background
nohup streamlit run Dashboard_API.py \
    --server.port=$PORT \
    --server.headless=true \
    --server.address=0.0.0.0 \
    --browser.gatherUsageStats=false \
    >> "$LOG_FILE" 2>&1 &

DASHBOARD_PID=$!

# Salva PID
echo $DASHBOARD_PID > "$PID_FILE"

# Aguarda um momento para verificar se iniciou
sleep 3

if ps -p "$DASHBOARD_PID" > /dev/null 2>&1; then
    echo "✅ Dashboard iniciado com sucesso!"
    echo "   PID: $DASHBOARD_PID"
    echo "   URL: http://localhost:$PORT"
    echo "   Log: $LOG_FILE"
    echo ""
    echo "🌐 Para acessar remotamente:"
    echo "   http://$(hostname -I | awk '{print $1}'):$PORT"
    echo ""
    echo "📊 Para ver logs em tempo real:"
    echo "   tail -f $LOG_FILE"
    echo ""
    echo "⏹️  Para parar o dashboard:"
    echo "   ./stop_dashboard.sh"
else
    echo "❌ Erro ao iniciar dashboard. Verifique o log:"
    echo "   tail -50 $LOG_FILE"
    rm "$PID_FILE"
    exit 1
fi

