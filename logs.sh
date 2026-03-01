#!/bin/bash

# Script para visualizar logs
# Uso: ./logs.sh [bot|dashboard|all] [linhas]

# Diretório do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TYPE=${1:-all}
LINES=${2:-50}

BOT_LOG="$SCRIPT_DIR/logs/bot.log"
DASHBOARD_LOG="$SCRIPT_DIR/logs/dashboard.log"

case $TYPE in
    bot)
        echo "=========================================="
        echo "🤖 Bot Log (últimas $LINES linhas)"
        echo "=========================================="
        if [ -f "$BOT_LOG" ]; then
            tail -n $LINES "$BOT_LOG"
            echo ""
            echo "📊 Para acompanhar em tempo real:"
            echo "   tail -f $BOT_LOG"
        else
            echo "❌ Log do bot não encontrado"
        fi
        ;;
    
    dashboard)
        echo "=========================================="
        echo "📊 Dashboard Log (últimas $LINES linhas)"
        echo "=========================================="
        if [ -f "$DASHBOARD_LOG" ]; then
            tail -n $LINES "$DASHBOARD_LOG"
            echo ""
            echo "📊 Para acompanhar em tempo real:"
            echo "   tail -f $DASHBOARD_LOG"
        else
            echo "❌ Log do dashboard não encontrado"
        fi
        ;;
    
    all|*)
        echo "=========================================="
        echo "🤖 Bot Log (últimas $LINES linhas)"
        echo "=========================================="
        if [ -f "$BOT_LOG" ]; then
            tail -n $LINES "$BOT_LOG"
        else
            echo "❌ Log do bot não encontrado"
        fi
        
        echo ""
        echo "=========================================="
        echo "📊 Dashboard Log (últimas $LINES linhas)"
        echo "=========================================="
        if [ -f "$DASHBOARD_LOG" ]; then
            tail -n $LINES "$DASHBOARD_LOG"
        else
            echo "❌ Log do dashboard não encontrado"
        fi
        
        echo ""
        echo "📊 Para acompanhar logs em tempo real:"
        echo "   Bot:       tail -f $BOT_LOG"
        echo "   Dashboard: tail -f $DASHBOARD_LOG"
        ;;
esac

echo ""

