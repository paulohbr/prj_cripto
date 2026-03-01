#!/usr/bin/env python3
"""
Dashboard de Trading - Visual Moderno
=====================================
Fontes: Inter, Poppins, JetBrains Mono
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from trading_core import TAXA_BINANCE, formatar_tempo
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import os

# ============================================
# CONFIGURAÇÃO
# ============================================
API_URL = os.getenv('API_URL', 'http://localhost:5000')
REFRESH_INTERVAL = 2  # segundos (Aumentado para evitar travamento UI)

# ---- Streamlit page config (must be first Streamlit call) ----
st.set_page_config(
    page_title="Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === CONEXÃO (REST x WEBSOCKET) ===
@st.cache_data(ttl=1.5)
def fetch_connection():
    """Retorna status de conexão do bot (WebSocket/REST)."""
    try:
        r = requests.get(f"{API_URL}/api/connection", timeout=3)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {'type': 'REST', 'connected': False}

_conn = fetch_connection()
BAR_COLOR = '#059669' if _conn.get('connected') else '#b91c1c'
BAR_TEXT = f"{_conn.get('type')} | {'Online' if _conn.get('connected') else 'Offline'} | {'Testnet' if _conn.get('testnet') else 'Mainnet'}"

st.markdown(
    f"""
    <div style='position:fixed; top:0; left:0; right:0; height:32px; background:{BAR_COLOR}; color:#f0fdfa; display:flex; align-items:center; padding-left:12px; font-size:14px; z-index:1000'>
        🔌 Conexão: {BAR_TEXT}
    </div>
    <div style='margin-top:38px'></div>
    """,
    unsafe_allow_html=True
)



# ============================================
# FUNÇÕES DE API
# ============================================
@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_posicoes():
    try:
        response = requests.get(f"{API_URL}/api/posicoes", timeout=60)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return {'error': 'db_not_found'}
        return None
    except Exception as e:
        return {'error': str(e)}

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_estatisticas():
    try:
        response = requests.get(f"{API_URL}/api/estatisticas", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_vendas():
    try:
        response = requests.get(f"{API_URL}/api/vendas", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

@st.cache_data(ttl=REFRESH_INTERVAL * 1.5)
def fetch_candles(symbol, limit=50, interval='5m'):
    """Busca candles de uma moeda"""
    try:
        response = requests.get(
            f"{API_URL}/api/candles/{symbol}",
            params={'limit': limit, 'interval': interval},
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def calcular_rsi(closes, period=14):
    """Calcula RSI (Relative Strength Index)"""
    if len(closes) < period + 1:
        return [50] * len(closes)  # Retorna RSI neutro se não tiver dados suficientes
    
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    rsi_values = []
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    # Primeiro RSI
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    rsi_values.append(rsi)
    
    # RSI subsequentes (média móvel exponencial)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(rsi)
    
    # Adiciona valores iniciais (50 para os primeiros period candles)
    return [50] * period + rsi_values

def criar_grafico_candlestick(candles_data, symbol, preco_compra=None, timeframe='15m'):
    """Cria gráfico de candlestick com volume e RSI no formato Binance"""
    if not candles_data or not candles_data.get('candles'):
        return None
    
    candles = candles_data['candles']
    
    # Prepara dados
    times = [datetime.fromtimestamp(c['timestamp'] / 1000) for c in candles]
    opens = [c['open'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]
    closes = [c['close'] for c in candles]
    volumes = [c['volume'] for c in candles]
    
    # Calcula RSI
    rsi_values = calcular_rsi(closes, period=14)
    
    # Cria subplots: 3 linhas (candlestick, volume, RSI)
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.5, 0.25, 0.25],  # Candlestick maior, volume e RSI menores
        subplot_titles=(f"{symbol} - Candlestick Chart ({timeframe})", "Volume", "RSI"),
        specs=[[{"secondary_y": False}],
               [{"secondary_y": False}],
               [{"secondary_y": False}]]
    )
    
    # 1. Gráfico de Candlestick (linha 1)
    fig.add_trace(
        go.Candlestick(
            x=times,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            increasing_line_color='#26a69a',  # Verde para alta (igual Binance)
            decreasing_line_color='#ef5350',  # Vermelho para baixa (igual Binance)
            increasing_fillcolor='#26a69a',
            decreasing_fillcolor='#ef5350',
            line=dict(width=1),
            whiskerwidth=0.8,
            showlegend=False,
            name="Price"
        ),
        row=1, col=1
    )
    
    # Calcula Médias Móveis e Bandas de Bollinger
    closes_series = pd.Series(closes)
    ma20 = closes_series.rolling(window=20).mean()
    ma50 = closes_series.rolling(window=50).mean()
    
    # Bandas de Bollinger (20 períodos, 2 desvios)
    bb_sma = closes_series.rolling(window=20).mean()
    bb_std = closes_series.rolling(window=20).std()
    bb_upper = bb_sma + (bb_std * 2)
    bb_lower = bb_sma - (bb_std * 2)
    
    # Adiciona MA20 (laranja)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=ma20,
            mode='lines',
            line=dict(color='#f97316', width=1.5),
            name='MA20',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Adiciona MA50 (azul)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=ma50,
            mode='lines',
            line=dict(color='#3b82f6', width=1.5),
            name='MA50',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Banda Superior de Bollinger
    fig.add_trace(
        go.Scatter(
            x=times,
            y=bb_upper,
            mode='lines',
            line=dict(color='rgba(147, 51, 234, 0.5)', width=1, dash='dot'),
            name='BB Superior',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Banda Inferior de Bollinger (com fill)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=bb_lower,
            mode='lines',
            line=dict(color='rgba(147, 51, 234, 0.5)', width=1, dash='dot'),
            name='BB Inferior',
            showlegend=True,
            fill='tonexty',
            fillcolor='rgba(147, 51, 234, 0.1)'
        ),
        row=1, col=1
    )
    
    # Calcula Ichimoku Cloud
    # Tenkan-sen (Conversion Line): (9-period high + 9-period low)/2
    period9_high = pd.Series(highs).rolling(window=9).max()
    period9_low = pd.Series(lows).rolling(window=9).min()
    tenkan = (period9_high + period9_low) / 2
    
    # Kijun-sen (Base Line): (26-period high + 26-period low)/2
    period26_high = pd.Series(highs).rolling(window=26).max()
    period26_low = pd.Series(lows).rolling(window=26).min()
    kijun = (period26_high + period26_low) / 2
    
    # Senkou Span A (Leading Span A): (Conversion + Base)/2, plotted 26 periods ahead
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    
    # Senkou Span B (Leading Span B): (52-period high + 52-period low)/2, plotted 26 periods ahead
    period52_high = pd.Series(highs).rolling(window=52).max()
    period52_low = pd.Series(lows).rolling(window=52).min()
    senkou_b = ((period52_high + period52_low) / 2).shift(26)
    
    # Chikou Span (Lagging Span): Close plotted 26 periods back
    chikou = pd.Series(closes).shift(-26)
    
    # Adiciona Tenkan-sen (vermelho)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=tenkan,
            mode='lines',
            line=dict(color='#ef4444', width=1),
            name='Tenkan',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Adiciona Kijun-sen (azul escuro)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=kijun,
            mode='lines',
            line=dict(color='#1e40af', width=1),
            name='Kijun',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Adiciona Senkou Span A (verde claro)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=senkou_a,
            mode='lines',
            line=dict(color='rgba(34, 197, 94, 0.3)', width=0.5),
            name='Senkou A',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Adiciona Senkou Span B com nuvem (vermelho claro)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=senkou_b,
            mode='lines',
            line=dict(color='rgba(239, 68, 68, 0.3)', width=0.5),
            name='Senkou B',
            showlegend=True,
            fill='tonexty',
            fillcolor='rgba(100, 200, 100, 0.15)'  # Nuvem verde clara
        ),
        row=1, col=1
    )
    
    # Adiciona Chikou Span (roxo)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=chikou,
            mode='lines',
            line=dict(color='rgba(168, 85, 247, 0.6)', width=1, dash='dot'),
            name='Chikou',
            showlegend=True
        ),
        row=1, col=1
    )
        
    # Adiciona linha de preço de compra se fornecido
    if preco_compra:
        fig.add_hline(
            y=preco_compra,
            line_dash="dash",
            line_color="#fbbf24",
            annotation_text=f"Compra: ${preco_compra:.6f}",
            annotation_position="right",
            annotation_font=dict(size=9, color='#fbbf24'),
            row=1, col=1
        )
    # 2. Gráfico de Volume (linha 2)
    # Cores baseadas em alta/baixa
    colors_volume = ['#26a69a' if closes[i] >= opens[i] else '#ef5350' for i in range(len(closes))]
    fig.add_trace(
        go.Bar(
            x=times,
            y=volumes,
            marker_color=colors_volume,
            showlegend=False,
            name="Volume"
        ),
        row=2, col=1
    )
    
    # 3. Gráfico de RSI (linha 3)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=rsi_values,
            mode='lines',
            line=dict(color='#8b5cf6', width=2),
            showlegend=False,
            name="RSI"
        ),
        row=3, col=1
    )
    
    # Linhas de referência RSI (30 e 70)
    fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="rgba(255,255,255,0.3)", row=3, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.2)", row=3, col=1)
    
    # Layout estilo Binance (compactado)
    fig.update_layout(
        title=dict(
            text=f"{symbol} - Candlestick Chart ({timeframe})",
            font=dict(size=12, color="#e2e8f0")
        ),
        height=600,  # Aumentado para acomodar 3 gráficos
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis_rangeslider_visible=False  # Remove slider inferior
    )

    # Atualiza eixos X (compartilhados) - aplica no último subplot (os outros compartilham)
    fig.update_xaxes(
        type="date",
        showgrid=True,
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickfont=dict(size=8, color="#94a3b8"),
        row=3, col=1
    )

    # Atualiza eixo Y do candlestick
    fig.update_yaxes(
        title="Preço",
        showgrid=True,
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickfont=dict(size=8, color="#94a3b8"),
        row=1, col=1
    )

    # Atualiza eixo Y do volume
    fig.update_yaxes(
        title="Volume",
        showgrid=True,
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickfont=dict(size=8, color="#94a3b8"),
        row=2, col=1
    )

    # Atualiza eixo Y do RSI
    fig.update_yaxes(
        title="RSI",
        showgrid=True,
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickfont=dict(size=8, color="#94a3b8"),
        range=[0, 100],  # RSI sempre entre 0 e 100
        row=3, col=1
    )

    return fig


def read_trading_log(lines=100):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    log_paths = [
        '/home/user/projetos/prj_criptos/logs/bot.log',
        os.path.join(script_dir, 'logs', 'bot.log'),
        'logs/bot.log',
    ]

    for log_path in log_paths:
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()

                    if not all_lines:
                        return "📄 Log vazio."

                    return ''.join(all_lines[-lines:])
            except Exception:
                pass

    return "⚠️ Log não encontrado."


def check_api_health():
    try:
        response = requests.get(f"{API_URL}/api/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


# ============================================
# CSS MODERNO
# ============================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
    
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }
    
    .stApp { 
        background: linear-gradient(145deg, #0a0f1a 0%, #111827 50%, #0f172a 100%);
    }
    
    /* Títulos */
    h1 {
        font-family: 'Poppins', sans-serif !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        letter-spacing: -0.5px !important;
        background: none !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    h2, h3 {
        font-family: 'Poppins', sans-serif !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: #e2e8f0 !important;
        margin: 0.5rem 0 !important;
        padding: 10px 14px !important;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(139, 92, 246, 0.08) 100%) !important;
        border-radius: 8px !important;
        border-left: 3px solid #6366f1 !important;
    }
    
    /* Métricas - Tamanho maior para KPIs principais */
    [data-testid="stMetricValue"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        color: #f1f5f9 !important;
        letter-spacing: -0.2px !important;
        line-height: 1.2 !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.6rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.4px !important;
        margin-bottom: 2px !important;
    }
    
    [data-testid="stMetricDelta"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.65rem !important;
        font-weight: 600 !important;
    }
    
    /* Container de métricas - ultra compactado */
    [data-testid="stMetricContainer"] {
        padding: 2px 8px !important;
        margin-bottom: -0.5rem !important;
    }
    
    /* Reduz espaçamento entre colunas de métricas */
    [data-testid="column"] {
        padding: 0 4px !important;
        margin-bottom: -0.5rem !important;
    }
    
    /* Tabelas */
    .stDataFrame th {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.7rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%) !important;
        color: #e2e8f0 !important;
        padding: 10px 12px !important;
    }
    
    .stDataFrame td {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        color: #f1f5f9 !important;
        padding: 8px 12px !important;
    }
    
    /* Sidebar - Fundo azul escuro para destacar imagem e texto */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%) !important;
    }
    
    [data-testid="stSidebar"] h3 {
        font-size: 0.95rem !important;
        background: none !important;
        border: none !important;
        padding: 0 !important;
        color: #e2e8f0 !important;
    }
    
    /* Texto da sidebar para contraste com fundo escuro */
    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: #e2e8f0 !important;
    }
    
    /* Botões */
    .stButton > button {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        border: none !important;
        border-radius: 8px !important;
        color: #fff !important;
        padding: 8px 16px !important;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4) !important;
    }
    
    /* Checkbox */
    .stCheckbox label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        color: #1e293b !important;
    }
    
    /* Checkbox na sidebar */
    [data-testid="stSidebar"] .stCheckbox label {
        color: #e2e8f0 !important;
    }
    
    /* Caption */
    .stCaption {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.7rem !important;
        color: #64748b !important;
    }
    
    /* Code/Log */
    .stCodeBlock, code, pre {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.75rem !important;
        line-height: 1.5 !important;
    }
    
    /* Divisor */
    hr {
        border: none !important;
        height: 1px !important;
        background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.25), transparent) !important;
        margin: 1rem 0 !important;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #6366f1; border-radius: 3px; }
    
    /* Espaçamento - Ultra Compactado */
    .element-container { margin-bottom: 0.05rem !important; }
    .stMarkdown { margin-bottom: 0.05rem !important; }
    h2, h3 { margin: 0.1rem 0 !important; padding: 4px 8px !important; }
    
    /* Sidebar - Compactação máxima na vertical */
    [data-testid="stSidebar"] .stMarkdown { margin-bottom: 0.2rem !important; }
    [data-testid="stSidebar"] hr { margin: 0.4rem 0 !important; }
    [data-testid="stSidebar"] h3 { margin: 0.3rem 0 0.2rem 0 !important; padding: 1px 0 !important; font-size: 0.95rem !important; }
    [data-testid="stSidebar"] .element-container { margin-bottom: 0.2rem !important; }
    [data-testid="stSidebar"] p { margin: 0.1rem 0 !important; line-height: 1.2 !important; }
    
    /* Colunas - reduzir espaçamento drasticamente */
    [data-testid="column"] {
        padding: 0 4px !important;
        margin-bottom: -1rem !important;
    }
    
    /* Reduz espaço após métricas (mas não esconde) */
    [data-testid="stMetricContainer"] {
        margin-bottom: -0.5rem !important;
        padding-bottom: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# JAVASCRIPT PARA PRESERVAR SCROLL DURANTE REFRESH
# ============================================
import streamlit.components.v1 as components

# Usa components.html para injetar JavaScript (st.markdown não executa scripts)
components.html("""
<script>
    // Função que preserva scroll durante refresh do Streamlit
    (function() {
        // Referência ao elemento principal do Streamlit
        const mainElement = window.parent.document.querySelector('section.main');
        
        // Restaura posição de scroll salva (se existir)
        const scrollPos = sessionStorage.getItem('streamlit_scroll_pos');
        if (scrollPos && mainElement) {
            // Aguarda o DOM carregar, depois restaura scroll
            setTimeout(function() {
                mainElement.scrollTop = parseInt(scrollPos);
            }, 50);
        }
        
        // Salva posição de scroll a cada 300ms
        if (mainElement) {
            setInterval(function() {
                sessionStorage.setItem('streamlit_scroll_pos', mainElement.scrollTop.toString());
            }, 300);
        }
    })();
</script>
""", height=0)

# ============================================
# HEADER
# ============================================
st.markdown("# 📈 Trading Bot Dashboard")
st.markdown("<br>", unsafe_allow_html=True)  # Espaço pequeno entre título e KPIs

api_ok = check_api_health()
if not api_ok:
    st.error("❌ API offline! Execute: python3 api_trading.py")
    st.stop()

stats = fetch_estatisticas()

# ============================================
# SIDEBAR
# ============================================
# Imagem no topo da sidebar (tamanho reduzido e centralizada)
try:
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.join(script_dir, 'FinalTransparente.png')
    
    if os.path.exists(image_path):
        # Centraliza usando colunas vazias nas laterais
        col1, col2, col3 = st.sidebar.columns([1, 2, 1])
        with col2:
            st.image(image_path, width=150, output_format='PNG')
    else:
        # Tenta caminho alternativo
        alt_path = '/home/user/projetos/prj_criptos/FinalTransparente.png'
        if os.path.exists(alt_path):
            col1, col2, col3 = st.sidebar.columns([1, 2, 1])
            with col2:
                st.image(alt_path, width=150, output_format='PNG')
except Exception as e:
    pass  # Se não encontrar a imagem, continua normalmente

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Atualizar", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.checkbox(f"Auto-refresh ({REFRESH_INTERVAL}s)", value=True)

# Seletor de Timeframe (Default 5m para dar match com Nostalgia)
selected_timeframe = st.sidebar.selectbox(
    "Timeframe do Gráfico",
    ['1m', '5m', '15m', '1h', '4h'],
    index=1  # 5m por padrão
)

# Adiciona tempo desde inicialização e projeções na sidebar
st.sidebar.markdown("---")

# Tempo desde última inicialização - SEMPRE calcula, mesmo se stats for None
tempo_desde_inicio_str = '0s'
data_inicio = None
projecao_semana = 0
projecao_mes = 0
projecao_semana_bruto = 0
projecao_mes_bruto = 0
tempo_desde_inicio = 0
ops_lucrativas = 0
ops_prejuizo = 0
lucro_total_sidebar = 0

# Se stats existe e não tem erro, usa os dados (mas pode ser sobrescrito pelas vendas)
if stats and not stats.get('error'):
    tempo_desde_inicio_str = stats.get('tempo_desde_inicio_str', '0s')
    data_inicio = stats.get('data_inicio', None)
    # ⚡⚡⚡ CRÍTICO: Usa projeções da API se disponíveis (mais confiável) ⚡⚡⚡
    projecao_semana = stats.get('projecao_semana', 0)
    projecao_mes = stats.get('projecao_mes', 0)
    tempo_desde_inicio = stats.get('tempo_desde_inicio', 0)
    ops_lucrativas = stats.get('ops_lucrativas', 0)
    ops_prejuizo = stats.get('ops_prejuizo', 0)
    lucro_total_sidebar = stats.get('lucro_realizado', 0)

# FALLBACK: Se não conseguiu data da API, busca diretamente do banco
if not data_inicio or tempo_desde_inicio == 0:
    try:
        import sqlite3
        from trading_core import agora_brasil
        db_path = os.path.join(os.path.dirname(__file__), 'trading_data.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # Tenta buscar data de inicialização
            cursor.execute('SELECT data_inicio FROM inicializacao WHERE id = 1 ORDER BY criado_em DESC LIMIT 1')
            row = cursor.fetchone()
            if not row:
                cursor.execute('SELECT data_inicio FROM inicializacao ORDER BY criado_em DESC LIMIT 1')
                row = cursor.fetchone()
            
            if row and row[0]:
                data_inicio = row[0]
                # Calcula tempo decorrido
                try:
                    if isinstance(data_inicio, str):
                        data_str = str(data_inicio).replace('Z', '').split('+')[0].split('.')[0]
                        try:
                            dt_inicio = datetime.fromisoformat(data_str)
                        except:
                            dt_inicio = datetime.strptime(data_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        dt_inicio = data_inicio
                    
                    if hasattr(dt_inicio, 'tzinfo') and dt_inicio.tzinfo:
                        dt_inicio = dt_inicio.replace(tzinfo=None)
                    
                    agora = agora_brasil()
                    if hasattr(agora, 'tzinfo') and agora.tzinfo:
                        agora = agora.replace(tzinfo=None)
                    
                    tempo_desde_inicio = (agora - dt_inicio).total_seconds()
                    
                    # Formata tempo
                    if tempo_desde_inicio > 0:
                        horas = int(tempo_desde_inicio / 3600)
                        minutos = int((tempo_desde_inicio % 3600) / 60)
                        segundos = int(tempo_desde_inicio % 60)
                        if horas > 0:
                            tempo_desde_inicio_str = f"{horas}h {minutos}m"
                        elif minutos > 0:
                            tempo_desde_inicio_str = f"{minutos}m {segundos}s"
                        else:
                            tempo_desde_inicio_str = f"{segundos}s"
                except Exception as e:
                    pass
            conn.close()
    except Exception as e:
        pass  # Silencia erro do fallback

# ⚡⚡⚡ CRÍTICO: SEMPRE usa valores da API para ops_lucrativas e ops_prejuizo (mais confiável) ⚡⚡⚡
# SEMPRE busca vendas para calcular projeções, mesmo se stats estiver disponível
vendas_data_sidebar = fetch_vendas()
if vendas_data_sidebar and vendas_data_sidebar.get('vendas'):
    vendas_sidebar = vendas_data_sidebar['vendas']
    
    # ⚡⚡⚡ CRÍTICO: Só atualiza se stats não tiver esses valores (fallback apenas) ⚡⚡⚡
    # Prioriza sempre os valores da API que vêm da tabela resultados (mais preciso)
    if (ops_lucrativas == 0 and ops_prejuizo == 0) or not stats or stats.get('error'):
        # Fallback: calcula das vendas apenas se API não tiver os dados
        ops_lucrativas = sum(1 for v in vendas_sidebar if v.get('lucro', 0) > 0)
        ops_prejuizo = sum(1 for v in vendas_sidebar if v.get('lucro', 0) <= 0)
    
    # ⚡⚡⚡ CRÍTICO: Calcula lucro total das vendas (soma TODOS, incluindo negativos) para projeções ⚡⚡⚡
    lucro_total_vendas = sum(v.get('lucro', 0) for v in vendas_sidebar)
    
    # Calcula taxas totais para lucro bruto
    total_taxas = sum(float(v.get('taxa_compra', 0)) + float(v.get('taxa_venda', 0)) for v in vendas_sidebar)
    lucro_bruto_total = lucro_total_vendas + total_taxas

    # Só atualiza lucro_total_sidebar se ainda estiver zerado (prioriza stats da API)
    if lucro_total_sidebar == 0:
        lucro_total_sidebar = lucro_total_vendas  # Atualiza lucro total
    
    # Estima tempo baseado na primeira venda até AGORA (não entre primeira e última)
    if len(vendas_sidebar) > 0:
        try:
            from datetime import datetime
            from trading_core import agora_brasil
            
            primeira_venda = vendas_sidebar[-1].get('data_venda')  # Última na lista = mais antiga
            
            # Define data_inicio como a primeira venda se não estiver disponível
            if not data_inicio and primeira_venda:
                data_inicio = primeira_venda
            
            if primeira_venda:
                dt_primeira = datetime.fromisoformat(str(primeira_venda).replace('Z', '+00:00'))
                if hasattr(dt_primeira, 'tzinfo') and dt_primeira.tzinfo:
                    dt_primeira = dt_primeira.replace(tzinfo=None)
                
                # Calcula tempo desde a primeira venda até AGORA
                agora = agora_brasil()
                if hasattr(agora, 'tzinfo') and agora.tzinfo:
                    agora = agora.replace(tzinfo=None)
                
                tempo_desde_primeira = (agora - dt_primeira).total_seconds()
                
                # Se tempo_desde_inicio ainda for zero, usa tempo desde primeira venda
                if tempo_desde_inicio == 0 and tempo_desde_primeira > 0:
                    tempo_desde_inicio = tempo_desde_primeira
                    # Formata tempo de forma mais legível
                    horas = int(tempo_desde_primeira / 3600)
                    minutos = int((tempo_desde_primeira % 3600) / 60)
                    segundos = int(tempo_desde_primeira % 60)
                    if horas > 0:
                        tempo_desde_inicio_str = f"{horas}h {minutos}m"
                    elif minutos > 0:
                        tempo_desde_inicio_str = f"{minutos}m {segundos}s"
                    else:
                        tempo_desde_inicio_str = f"{segundos}s"
                
                # ⚡⚡⚡ CRÍTICO: Só recalcula projeções se API não forneceu (prioriza API) ⚡⚡⚡
                if (projecao_semana == 0 and projecao_mes == 0) and tempo_desde_inicio > 0 and lucro_total_vendas > 0:
                    horas_vendas = tempo_desde_inicio / 3600
                    # Calcula projeções mesmo com menos de 1 hora (mas com aviso)
                    if horas_vendas > 0:
                        lucro_por_hora = lucro_total_vendas / horas_vendas
                        projecao_semana = lucro_por_hora * 24 * 7
                        projecao_mes = lucro_por_hora * 24 * 30
                        
                        # Bruto (com taxas) - SEMPRE calcula!
                        if lucro_bruto_total > 0:
                            lucro_bruto_por_hora = lucro_bruto_total / horas_vendas
                        else:
                            lucro_bruto_por_hora = lucro_por_hora * 1.15  # Fallback: estima 15% de taxas
                        projecao_semana_bruto = lucro_bruto_por_hora * 24 * 7
                        projecao_mes_bruto = lucro_bruto_por_hora * 24 * 30

                        
                    # Se tempo for muito curto (menos de 1 hora), usa estimativa baseada em minutos
                    elif tempo_desde_inicio > 60:  # Pelo menos 1 minuto
                        # Estima baseado em minutos
                        minutos_vendas = tempo_desde_inicio / 60
                        lucro_por_minuto = lucro_total_vendas / minutos_vendas
                        lucro_por_hora = lucro_por_minuto * 60
                        projecao_semana = lucro_por_hora * 24 * 7
                        projecao_mes = lucro_por_hora * 24 * 30
                        
                        # Bruto
                        lucro_bruto_por_minuto = lucro_bruto_total / minutos_vendas
                        lucro_bruto_por_hora = lucro_bruto_por_minuto * 60
                        projecao_semana_bruto = lucro_bruto_por_hora * 24 * 7
                        projecao_mes_bruto = lucro_bruto_por_hora * 24 * 30
                        
                    # Se tempo for muito curto (menos de 1 minuto), ainda calcula (estimativa inicial)
                    elif tempo_desde_inicio > 0:
                        # Estima baseado em segundos (muito inicial, mas mostra algo)
                        segundos_vendas = tempo_desde_inicio
                        lucro_por_segundo = lucro_total_vendas / segundos_vendas
                        lucro_por_hora = lucro_por_segundo * 3600
                        projecao_semana = lucro_por_hora * 24 * 7
                        projecao_mes = lucro_por_hora * 24 * 30
                        
                        # Bruto
                        lucro_bruto_por_segundo = lucro_bruto_total / segundos_vendas
                        lucro_bruto_por_hora = lucro_bruto_por_segundo * 3600
                        projecao_semana_bruto = lucro_bruto_por_hora * 24 * 7
                        projecao_mes_bruto = lucro_bruto_por_hora * 24 * 30
        except Exception as e:
            import traceback
            pass  # Silencia erro mas permite debug se necessário
else:
    vendas_data_sidebar = None

# Formata data_inicio se disponível
data_formatada = None
if data_inicio:
    try:
        from datetime import datetime
        # Tenta diferentes formatos de data
        if isinstance(data_inicio, str):
            data_str = str(data_inicio).replace('Z', '').split('+')[0].split('.')[0]
            try:
                dt_inicio = datetime.fromisoformat(data_str)
            except:
                try:
                    dt_inicio = datetime.strptime(data_str, '%Y-%m-%d %H:%M:%S')
                except:
                    dt_inicio = None
        else:
            dt_inicio = data_inicio
        
        if dt_inicio:
            if hasattr(dt_inicio, 'tzinfo') and dt_inicio.tzinfo:
                dt_inicio = dt_inicio.replace(tzinfo=None)
            data_formatada = dt_inicio.strftime('%d/%m/%Y %H:%M')
        else:
            data_formatada = str(data_inicio)
    except:
        data_formatada = str(data_inicio) if data_inicio else None

# st.sidebar.markdown("### ⏱️ Inicialização")
# (Seção ocultada para compactar menu)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Projeções")

total_ops = ops_lucrativas + ops_prejuizo
perc_wins = (ops_lucrativas / total_ops * 100) if total_ops > 0 else 0

# Mostra projeções se tiver tempo e lucro positivo
TEMPO_MINIMO_PROJECAO = 3600  # 1 hora em segundos (ideal, mas não obrigatório)
tem_tempo_suficiente = tempo_desde_inicio >= TEMPO_MINIMO_PROJECAO
tem_lucro_positivo = lucro_total_sidebar > 0 or (vendas_data_sidebar and sum(v.get('lucro', 0) for v in vendas_data_sidebar.get('vendas', [])) > 0)
# ⚡⚡⚡ CRÍTICO: Mostra projeções se tiver tempo (mesmo que seja menos de 1h) E lucro positivo ⚡⚡⚡
# Não exige que projeções sejam > 0, apenas que estejam calculadas (podem ser negativas)
mostrar_projecoes = tempo_desde_inicio > 0 and tem_lucro_positivo

# Card Semana
st.sidebar.markdown("""
<div style="
    background: rgba(16, 185, 129, 0.1);
    border-left: 3px solid #10b981;
    border-radius: 4px;
    padding: 6px;
    margin-bottom: 3px;
    line-height: 1.2;
">
""", unsafe_allow_html=True)

# FALLBACK: Se bruto está zerado mas net tem valor, calcula bruto como net + 15%
if projecao_semana_bruto == 0 and projecao_semana > 0:
    projecao_semana_bruto = projecao_semana * 1.15
if projecao_mes_bruto == 0 and projecao_mes > 0:
    projecao_mes_bruto = projecao_mes * 1.15

# Cálculo Projeção Dia
projecao_dia = projecao_semana / 7 if projecao_semana else 0
projecao_dia_bruto = projecao_semana_bruto / 7 if projecao_semana_bruto else 0

# === PROJEÇÕES SUPER COMPACT (3 Cols na mesma linha) ===
c_dia, c_sem, c_mes = st.sidebar.columns(3)

style_val = "line-height:1.1; text-align:center"

# Card Dia
with c_dia:
    st.markdown("<div style='text-align:center; font-size:0.85em; margin-bottom:2px'><b>Dia</b></div>", unsafe_allow_html=True)
    if mostrar_projecoes and projecao_dia != 0:
        st.markdown(f"""
        <div style='{style_val}'>
            <span style='font-size:0.7em; color:#94a3b8'>\${projecao_dia_bruto:.0f}</span><br>
            <span style='font-size:0.9em; font-weight:700; color:#4ade80'>\${projecao_dia:.0f}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='{style_val}; color:#64748b'>-</div>", unsafe_allow_html=True)

# Card Semana
with c_sem:
    st.markdown("<div style='text-align:center; font-size:0.85em; margin-bottom:2px'><b>Semana</b></div>", unsafe_allow_html=True)
    if mostrar_projecoes and projecao_semana != 0:
        st.markdown(f"""
        <div style='{style_val}'>
            <span style='font-size:0.7em; color:#94a3b8'>\${projecao_semana_bruto:.0f}</span><br>
            <span style='font-size:0.9em; font-weight:700; color:#4ade80'>\${projecao_semana:.0f}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='{style_val}; color:#64748b'>-</div>", unsafe_allow_html=True)

# Card Mês
with c_mes:
    st.markdown("<div style='text-align:center; font-size:0.85em; margin-bottom:2px'><b>Mês</b></div>", unsafe_allow_html=True)
    if mostrar_projecoes and projecao_mes != 0:
        st.markdown(f"""
        <div style='{style_val}'>
            <span style='font-size:0.7em; color:#94a3b8'>\${projecao_mes_bruto:.0f}</span><br>
            <span style='font-size:0.9em; font-weight:700; color:#4ade80'>\${projecao_mes:.0f}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='{style_val}; color:#64748b'>-</div>", unsafe_allow_html=True)

st.sidebar.markdown("---")

# Lucro / Prejuízo (Nativo Clean)
c1, c2 = st.sidebar.columns(2)
c1.metric("✅ Wins", f"{ops_lucrativas}", delta=f"{perc_wins:.0f}%")
c2.metric("❌ Loss", f"{ops_prejuizo}")

st.sidebar.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.65rem; padding-top: 10px; margin-top: 5px;">
    v2.1 • khzan tecnologia © 2026
</div>
""", unsafe_allow_html=True)

# ============================================
# KPIs PRINCIPAIS - REORGANIZADOS PARA CLAREZA
# ============================================
# Inicializa valores padrão
lucros_positivos = 0
prejuizo_total = 0
lucro_liquido = 0
valor_investido_total = 0.0
valor_imobilizado = 0.0
quantidade_moedas_abertas = 0
total_vendas = 0
tempo_rodando_str = '0s'

# Se stats existe e não tem erro, usa os dados
if stats and not stats.get('error'):
    lucros_positivos = stats.get('lucros_positivos', 0)
    prejuizo_total = stats.get('prejuizo_total', 0)
    lucro_liquido = stats.get('lucro_liquido', 0)
    # ⚡⚡⚡ CRÍTICO: NÃO usa valor_imobilizado da API - será recalculado apenas das posições abertas ⚡⚡⚡
    valor_imobilizado = 0.0  # Sempre recalcula apenas das posições abertas
    quantidade_moedas_abertas = stats.get('posicoes_abertas', 0)
    total_vendas = stats.get('total_vendas', 0)
    # ⚡⚡⚡ CRÍTICO: Usa tempo_desde_inicio_str se disponível (mais preciso), senão usa tempo_rodando_str ⚡⚡⚡
    tempo_rodando_str = stats.get('tempo_desde_inicio_str') or stats.get('tempo_rodando_str', '0s')

# ⚡⚡⚡ CRÍTICO: Busca posições abertas (sempre, mesmo se stats for None) ⚡⚡⚡
# Capital Imobilizado = APENAS posições abertas (não vendidas)
posicoes_data = fetch_posicoes()
if posicoes_data and posicoes_data.get('posicoes'):
    quantidade_moedas_abertas = len(posicoes_data['posicoes'])
    # ⚡⚡⚡ CRÍTICO: Calcula valor imobilizado APENAS das posições abertas ⚡⚡⚡
    valor_imobilizado = 0.0  # Zera para recalcular apenas das posições abertas
    for p in posicoes_data['posicoes']:
        # Calcula valor imobilizado somando valor_compra das posições abertas
        valor_compra = p.get('valor_compra', 0)
        if valor_compra > 0:
            valor_imobilizado += valor_compra

# Fallback: usa resumo das posições se disponível (mas só se não tiver calculado acima)
if posicoes_data and posicoes_data.get('resumo'):
    if quantidade_moedas_abertas == 0:
        quantidade_moedas_abertas = posicoes_data['resumo'].get('total_posicoes', 0)
    # ⚡⚡⚡ CRÍTICO: Só usa fallback se valor_imobilizado ainda estiver zerado ⚡⚡⚡
    if valor_imobilizado == 0:
        valor_imobilizado = posicoes_data['resumo'].get('valor_imobilizado', 0)

# ⚡⚡⚡ SEMPRE busca vendas para garantir cálculo correto ⚡⚡⚡
vendas_data = fetch_vendas()
if vendas_data and vendas_data.get('vendas'):
    # Calcula lucro total das vendas (soma TODOS os lucros positivos)
    lucro_total_vendas = sum(v.get('lucro', 0) for v in vendas_data['vendas'] if v.get('lucro', 0) > 0)
    
    # Calcula prejuízo total (soma valores absolutos dos lucros negativos)
    prejuizo_total_vendas = sum(abs(v.get('lucro', 0)) for v in vendas_data['vendas'] if v.get('lucro', 0) < 0)
    
    # Calcula total de taxas (taxa_compra + taxa_venda de todas as vendas)
    total_taxas = sum(v.get('taxa_compra', 0) + v.get('taxa_venda', 0) for v in vendas_data['vendas'])
    
    # ⚡⚡⚡ CRÍTICO: Sempre usa o lucro calculado das vendas (mais confiável) ⚡⚡⚡
    if lucro_total_vendas > 0:
        lucros_positivos = lucro_total_vendas
    if prejuizo_total_vendas > 0:
        prejuizo_total = prejuizo_total_vendas
    
    # Calcula lucro líquido = (lucro bruto - prejuízo) - taxas
    lucro_liquido = (lucros_positivos - prejuizo_total) - total_taxas
    
    # Contagem de vendas
    total_vendas = len(vendas_data['vendas'])
    
    # Calcula valor total investido das vendas
    valor_investido_vendas = sum(v.get('valor_compra', 0) for v in vendas_data['vendas'])
    if valor_investido_vendas > 0:
        # ⚡ TOTAL INVESTIDO = vendas realizadas + posições abertas
        valor_investido_total = valor_investido_vendas + valor_imobilizado

# Fallback: se não teve vendas, usa posições abertas
if valor_investido_total == 0:
    valor_investido_total = valor_imobilizado

# Fallback para valor investido via stats
if valor_investido_total == 0 and stats and not stats.get('error'):
    valor_investido_total = stats.get('valor_total_operacoes', 0)

# Exibe mensagem de aviso se stats não estiver disponível
if not stats or stats.get('error'):
    if stats and stats.get('error'):
        st.warning(f"⚠️ Erro ao acessar banco: {stats.get('error', 'Erro desconhecido')}")
    elif not stats:
        import os
        if os.path.exists('trading_data.db'):
            st.info("⏳ Aguardando dados do servidor...")
        else:
            st.warning("⚠️ Banco não encontrado. Execute: ./restart.sh --clear-db")

# ============================================
# KPIs PRINCIPAIS - EXIBIÇÃO CLARA E DIRETA
# ============================================
# Calcula percentuais para exibição
perc_lucro_liquido = (lucro_liquido / valor_investido_total * 100) if valor_investido_total > 0 else 0
perc_imobilizado = (valor_imobilizado / 1000.0 * 100) if valor_imobilizado > 0 else 0

# Organiza KPIs em 2 linhas para melhor visualização
# Linha 1: Valores principais (Investido, Lucro, Prejuízo, Lucro Líquido, Win Rate, Lucro/Hora)
# Calcula KPIs adicionais
vendas_list = vendas_data_sidebar.get('vendas', []) if vendas_data_sidebar else []
total_vendas_kpi = len(vendas_list)
wins_kpi = sum(1 for v in vendas_list if v.get('lucro', 0) > 0)
win_rate = (wins_kpi / total_vendas_kpi * 100) if total_vendas_kpi > 0 else 0
lucro_por_hora = (lucro_liquido / (tempo_desde_inicio / 3600)) if tempo_desde_inicio > 0 else 0

# CÁLCULO DE WIN RATE FINANCEIRO (PROFIT SCORE) - Pedido do Usuário
# Considera o volume financeiro ganho vs perdido, não só a quantidade de trades.
total_financeiro_absoluto = lucros_positivos + abs(prejuizo_total)
win_rate_financeiro = (lucros_positivos / total_financeiro_absoluto * 100) if total_financeiro_absoluto > 0 else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("💵 Investido", f"${valor_investido_total:.2f}")
c2.metric("✅ Bruto", f"${lucros_positivos:.2f}")
c3.metric("❌ Prejuízo", f"${prejuizo_total:.2f}")
c4.metric("💰 Líquido", f"${lucro_liquido:.2f} ({perc_lucro_liquido:+.2f}%)")
# Exibe Win Rate Financeiro em vez de Quantitativo
c5.metric("🎯 Win R. ($)", f"{win_rate_financeiro:.1f}%")
c6.metric("💸 Lucro/Hora", f"${lucro_por_hora:.2f}/h")

# Linha 2: Status operacional + KPIs detalhados
trades_por_hora = (total_vendas_kpi / (tempo_desde_inicio / 3600)) if tempo_desde_inicio > 0 else 0
melhor_trade = max((v.get('lucro', 0) for v in vendas_list), default=0)
pior_trade = min((v.get('lucro', 0) for v in vendas_list), default=0)
tempos = [v.get('tempo_operacao', 0) for v in vendas_list if v.get('tempo_operacao')]
tempo_medio = sum(tempos) / len(tempos) if tempos else 0
tempo_medio_str = formatar_tempo(tempo_medio) if tempo_medio > 0 else "N/A"

pares_scaneados = stats.get('pares_scaneados', 0) if stats and not stats.get('error') else 0

c7, c8, c9, c10, c11, c12 = st.columns(6)
c7.metric("🪙 Abertas", f"{quantidade_moedas_abertas}")
c8.metric("✅ Vendidas", f"{total_vendas}")
c9.metric("🔒 Imobilizado", f"${valor_imobilizado:.2f} ({perc_imobilizado:.1f}%)")
c10.metric("⚡ Trades/Hora", f"{trades_por_hora:.1f}/h")
c11.metric("🔍 Scaneando", f"{pares_scaneados}")
c12.metric("⏱️ Rodando", tempo_rodando_str)


# ============================================
# VENDAS REALIZADAS
# ============================================
# Só busca vendas se ainda não foi buscado (fallback above)
if 'vendas_data' not in locals() or vendas_data is None:
    vendas_data = fetch_vendas()

if vendas_data and vendas_data.get('vendas'):
    vendas = vendas_data['vendas']
    if vendas:
        st.markdown("---")
        st.markdown("### 💰 Vendas Realizadas")
        
        # ⚡⚡⚡ CRÍTICO: Calcula lucro total somando TODAS as vendas com lucro positivo ⚡⚡⚡
        lucro_total = sum(v.get('lucro', 0) for v in vendas if v.get('lucro', 0) > 0)
        percentual_medio = sum(v.get('percentual', 0) for v in vendas) / len(vendas) if vendas else 0
        capital_por_op = 55.0
        
        # Lucro médio
        lucro_medio_vendas = lucro_total / len(vendas) if vendas else 0
        perc_medio_vendas = (lucro_medio_vendas / capital_por_op * 100) if capital_por_op > 0 else 0
        
        # Mediana do lucro
        lucros_lista = [v.get('lucro', 0) for v in vendas]
        lucro_mediana_vendas = pd.Series(lucros_lista).median() if lucros_lista else 0
        perc_mediana_vendas = (lucro_mediana_vendas / capital_por_op * 100) if capital_por_op > 0 else 0
        
        wins = sum(1 for v in vendas if v.get('lucro', 0) > 0)
        perc_wins_vendas = (wins / len(vendas) * 100) if vendas else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📊 Total", len(vendas))
        c2.metric("💵 Médio/Op", f"${lucro_medio_vendas:.4f} ({perc_medio_vendas:+.2f}%)")
        c3.metric("📊 Mediana/Op", f"${lucro_mediana_vendas:.4f} ({perc_mediana_vendas:+.2f}%)")
        c4.metric("📈 Win/Loss", f"{wins}/{len(vendas)-wins} ({perc_wins_vendas:.1f}%)")
        
        # ⚡⚡⚡ CRÍTICO: Agrupa vendas por moeda para somar corretamente múltiplas operações ⚡⚡⚡
        # Cria dicionário para agrupar por moeda
        vendas_por_moeda = {}
        for v in vendas:
            moeda = v['par']
            if moeda not in vendas_por_moeda:
                vendas_por_moeda[moeda] = {
                    'vendas': [],
                    'lucro_total': 0,
                    'quantidade_total': 0
                }
            
            # Adiciona venda ao grupo da moeda
            vendas_por_moeda[moeda]['vendas'].append(v)
            vendas_por_moeda[moeda]['lucro_total'] += v.get('lucro', 0)
            vendas_por_moeda[moeda]['quantidade_total'] += v.get('quantidade', 0)
        
        # Converte para lista ordenada por lucro total (maior lucro primeiro)
        vendas_ordenadas = sorted(vendas_por_moeda.items(), key=lambda x: x[1]['lucro_total'], reverse=True)
        
        # Prepara lista final com todas as vendas individuais
        lista_vendas = []
        total_lucro = 0
        
        for moeda, dados in vendas_ordenadas:
            # Adiciona todas as vendas individuais da moeda
            for v in dados['vendas']:
                # v já é dict vindo da API; extrai campos com segurança
                par = v.get('par')
                preco_compra = v.get('preco_compra')
                preco_venda = v.get('preco_venda')
                quantidade = v.get('quantidade')
                valor_compra = v.get('valor_compra')
                valor_venda = v.get('valor_venda')
                data_compra = v.get('data_compra')
                data_venda = v.get('data_venda')
                lucro = v.get('lucro')
                percentual = v.get('percentual')
                estrategia = v.get('estrategia')
                motivo_venda = v.get('motivo_venda', 'N/A')
                ordem_id_compra = v.get('ordem_id_compra')
                
                # Calcula duração da operação
                try:
                    dt_compra = datetime.fromisoformat(str(data_compra).replace('Z', '+00:00'))
                    dt_venda = datetime.fromisoformat(str(data_venda).replace('Z', '+00:00'))
                    duracao = (dt_venda.replace(tzinfo=None) - dt_compra.replace(tzinfo=None)).total_seconds()
                except:
                    duracao = 0
                
                # Calcula valores de compra e venda
                preco_compra_float = float(preco_compra) if preco_compra else 0
                preco_venda_float = float(preco_venda) if preco_venda else 0
                quantidade_float = float(quantidade) if quantidade else 0
                
                # Se valor_compra não estiver no banco, calcula: preço * quantidade
                if valor_compra:
                    valor_compra_float = round(float(valor_compra), 4)
                else:
                    valor_compra_float = round(preco_compra_float * quantidade_float, 4)
                
                # Se valor_venda não estiver no banco, calcula: preço * quantidade
                if valor_venda:
                    valor_venda_float = round(float(valor_venda), 4)
                else:
                    valor_venda_float = round(preco_venda_float * quantidade_float, 4)
                
                # Calcula taxas (0.1% da Binance)
                taxa_compra = round(valor_compra_float * TAXA_BINANCE, 4)
                taxa_venda = round(valor_venda_float * TAXA_BINANCE, 4)
                
                lista_vendas.append({
                    'par': par,
                    'preco_compra': round(preco_compra_float, 10) if preco_compra else 0,
                    'preco_venda': round(preco_venda_float, 10) if preco_venda else 0,
                    'quantidade': round(quantidade_float, 10) if quantidade else 0,
                    'valor_compra': valor_compra_float,
                    'valor_venda': valor_venda_float,
                    'lucro': round(lucro, 6) if lucro is not None else 0,
                    'percentual': round(float(percentual), 2) if percentual is not None else 0,
                    'estrategia': estrategia or 'Normal',
                    'data_compra': data_compra,
                    'data_venda': data_venda,
                    'duracao_segundos': int(duracao),
                    'duracao_str': formatar_tempo(duracao),
                    'ordem_id_compra': ordem_id_compra,
                    'taxa_compra': taxa_compra,
                    'taxa_venda': taxa_venda,
                    'lucro_liquido': round(lucro - taxa_compra - taxa_venda, 6) if lucro else 0,
                    'motivo_venda': motivo_venda
                })
                # Calcula lucro total
                if lucro:
                    total_lucro += lucro
        
        # ⚡⚡⚡ CRÍTICO: Agrega por moeda para somar TODAS as vendas do mesmo par ⚡⚡⚡
        # Não agrega! Mostra vendas individuais
        dados_v = []
        # Ordena por data (mais recente primeiro) se tiver data
        lista_vendas.sort(key=lambda x: str(x.get('data_venda', '')), reverse=True)

        for a in lista_vendas:
            preco = a.get('preco_venda', 0) or a.get('preco_compra', 0) or 0
            quantidade = a.get('quantidade', 0) or 0
            lucro = a.get('lucro', 0) or 0
            # Recalcula liquido se não vier (mas geralmente vem)
            taxa_compra = a.get('taxa_compra', 0) or 0
            taxa_venda = a.get('taxa_venda', 0) or 0
            lucro_liquido = a.get('lucro_liquido', 0) or (lucro - taxa_compra - taxa_venda)
            percentual_venda = a.get('percentual', 0) or 0
            
            # Formatação de ID
            id_compra = a.get('ordem_id_compra', 'N/A')
            id_fmt = id_compra[-6:] if id_compra and id_compra != 'N/A' else 'N/A'
            
            # Formatação condicional de decimais
            fmt = ".2f"
            if preco < 1: fmt = ".4f"
            if preco < 0.01: fmt = ".6f"
            if preco < 0.0001: fmt = ".8f"
            
            if quantidade >= 1:
                qty_fmt = f"{quantidade:.4f}"
            elif quantidade >= 0.01:
                qty_fmt = f"{quantidade:.6f}"
            else:
                qty_fmt = f"{quantidade:.8f}"

            # Formata motivo de venda
            motivo = a.get('motivo_venda', 'N/A') or 'N/A'
            if motivo == 'LUCRO_EXPLOSAO':
                motivo_fmt = '🎯 Lucro'
            elif motivo == 'LUCRO_ML':
                motivo_fmt = '🤖 ML'
            elif motivo == 'TRAILING':
                motivo_fmt = '📉 Trailing'
            elif motivo == 'PROTECAO_LUCRO':
                motivo_fmt = '🔒 Proteção'
            elif motivo == 'TIMEOUT':
                motivo_fmt = '⏰ Timeout'
            else:
                motivo_fmt = motivo
            
            # Formata Data da Venda
            dt_fmt = "N/A"
            raw_dt = a.get('data_venda')
            if raw_dt:
                try:
                    # Tenta converter se for string, ou usa direto se for datetime
                    ts = pd.to_datetime(raw_dt)
                    dt_fmt = ts.strftime('%d/%m %H:%M:%S')
                except:
                    dt_fmt = str(raw_dt)

            dados_v.append({
                "🆔 ID": id_fmt,
                "📅 Data": dt_fmt, # Nova Coluna Solicitada
                "⚙️ Entrada": str(a.get('estrategia', 'N/A'))[:12],
                "📈 Moeda": a.get('par', 'N/A'),
                "🚪 Saída": motivo_fmt,
                "💵 Preço": preco,
                "🧮 Qtd": quantidade,
                "💸 Taxas": taxa_compra + taxa_venda,
                "💰 Lucro Bruto": lucro,
                "✅ Lucro Líquido": lucro_liquido,
                "📊 %": percentual_venda,
                "⏱️ Tempo": a.get('duracao_str', 'N/A')
            })
            

        
        # ⚡⚡⚡ CRÍTICO: Altura dinâmica baseada no número de vendas (máximo 600px para scroll) ⚡⚡⚡
        altura_tabela = min(len(dados_v) * 35 + 38, 600)  # Aumentado de 250 para 600px

        # Cria DataFrame e aplica estilo
        df_vendas = pd.DataFrame(dados_v)
        
        if not df_vendas.empty:
            def highlight_profit(val):
                color = 'red' if val < 0 else '#2ecc71' if val > 0 else 'white'
                return f'color: {color}; font-weight: bold'

            styled_df = df_vendas.style.format({
                "💵 Preço": "${:.6f}",
                "🧮 Qtd": "{:.4f}",
                "💸 Taxas": "${:.4f}",
                "💰 Lucro Bruto": "${:+.4f}",
                "✅ Lucro Líquido": "${:+.4f}",
                "📊 %": "{:+.2f}%"
            }).map(highlight_profit, subset=["💰 Lucro Bruto", "✅ Lucro Líquido", "📊 %"])
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=altura_tabela)
        else:
             st.info("Nenhuma venda registrada ainda.")

# ============================================
# MOEDAS E GRÁFICOS
# ============================================
data = fetch_posicoes()
if data and data.get('posicoes'):
    posicoes = data['posicoes']
    resumo = data.get('resumo', {})
    timestamp = data.get('timestamp', '')
    
    st.markdown("---")
    st.markdown("### 🪙 Moedas Monitoradas")
    
    # Usa hora atual do Brasil
    from trading_core import agora_brasil
    agora = agora_brasil()
    st.caption(f"🔄 {agora.strftime('%H:%M:%S')} | {len(posicoes)} moedas")
    
    # ============================================
    # GRÁFICO DE BARRAS E GRID (PRIMEIRO - Visão Geral)
    # ============================================
    if posicoes:
        # ⚡⚡⚡ USA LUCRO BRUTO (sem descontar taxas) para não ter prejuízo na exibição ⚡⚡⚡
        lucros = [p.get('lucro_bruto', p.get('lucro_liquido', 0)) for p in posicoes]
        pares = [p.get('par', '').replace('USDT', '') for p in posicoes]
        cores = ['#10b981' if l > 0 else '#ef4444' for l in lucros]
        
        # Calcula limites do eixo Y com MUITO mais espaço para valores positivos
        lucro_min = min(lucros) if lucros else 0
        lucro_max = max(lucros) if lucros else 0
        
        if lucro_max > 0 and lucro_min >= 0:
            y_max = lucro_max * 2.0
            y_min = -lucro_max * 0.1
        elif lucro_max > 0 and lucro_min < 0:
            y_max = lucro_max * 2.0
            y_min = lucro_min * 1.1
        elif lucro_max <= 0 and lucro_min < 0:
            y_max = abs(lucro_min) * 0.1
            y_min = lucro_min * 1.1
        else:
            y_max = 0.1
            y_min = -0.1
        
        # Textos com percentual e valor juntos acima das barras
        textos = []
        percentuais = [p.get('percentual', 0) for p in posicoes]
        for i, l in enumerate(lucros):
            perc = percentuais[i] if i < len(percentuais) else 0
            textos.append(f"{perc:+.1f}% | ${l:.2f}")
        
        import plotly.graph_objects as go
        fig = go.Figure(go.Bar(
            x=pares, 
            y=lucros, 
            marker_color=cores,
            text=textos,
            textposition='outside',
            textfont=dict(size=10, color='#ffffff'),
            cliponaxis=False
        ))
        
        fig.update_layout(
            title=dict(text="Distribuição de Lucros", font=dict(size=10, color='#e2e8f0')),
            height=180,
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False, 
            margin=dict(l=50, r=15, t=30, b=60),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, color='#ffffff'), showgrid=False, title=dict(text="Moedas")),
            yaxis=dict(tickfont=dict(size=9, color='#94a3b8'), range=[y_min, y_max], zeroline=True, zerolinecolor='rgba(255, 255, 255, 0.3)', title=dict(text="Lucro (USDT)"))
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # ============================================
    # GRID DE POSIÇÕES (SEGUNDO)
    # ============================================
    dados = []
    for p in posicoes:
        preco = p['preco_atual']
        quantidade = p['quantidade']
        lucro = p.get('lucro_bruto', p.get('lucro_liquido', 0))
        perc = p.get('percentual', 0)
        
        fmt = ".2f" if preco >= 1 else (".4f" if preco >= 0.01 else ".6f")
        qty_fmt = f"{quantidade:.4f}" if quantidade >= 1 else (f"{quantidade:.6f}" if quantidade >= 0.01 else f"{quantidade:.8f}")
        
        # Modo de entrada (da operação)
        modo = p.get('modo', p.get('estrategia', 'Normal'))
        if modo == 'EXPLOSAO':
            modo_icon = '💥 Explosão'
        elif modo == 'ML':
            modo_icon = '🤖 ML'
        elif modo == 'BOTTOM_FISHING':
            modo_icon = '🎯 Fundo'
        elif modo == 'MACD':
            modo_icon = '🌊 MACD'
        elif modo == 'Grid Trading':
            modo_icon = '📊 Grid'
        else:
            # Exibe o próprio nome se não mapeado, em vez de "Normal" fixo
            modo_icon = f"🚀 {modo}" if modo and modo != 'Normal' else '📈 Normal'
        
        # Formatação de Volume
        vol24 = p.get('vol_24h', 0)
        volcurr = p.get('vol_atual', 0)
        
        def fmt_vol(v):
            if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
            if v >= 1_000: return f"{v/1_000:.1f}K"
            return f"{v:.0f}"

        dados.append({
            'ID': p.get('ordem_id', 'N/A')[-6:] if p.get('ordem_id') else 'N/A', # Últimos 6 digitos
            'Par': p['par'],
            'Modo': modo_icon,
            'Quantidade': qty_fmt,
            'Investido': f"${p.get('valor_compra', 0):.2f}",
            'Compra': f"${p['preco_compra']:{fmt}}",
            'Atual': f"${preco:{fmt}}",
            'Vol 24h': fmt_vol(vol24),
            'Vol Atual': fmt_vol(volcurr),
            'Var%': f"{'⬆️' if perc > 0 else '⬇️' if perc < 0 else '➡️'} {perc:+.2f}%",
            'Lucro': f"{'🟢' if lucro > 0 else '🔴' if lucro < 0 else '🟡'} ${lucro:+.4f}",
            'Tempo': p.get('tempo_str', 'N/A')
        })
    
    if dados:
        altura_tabela = min(len(dados) * 30 + 38, 400)
        st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True, height=altura_tabela)
    
    # ============================================
    # GRÁFICOS DE CANDLESTICK (TERCEIRO - Detalhes)
    # Remove duplicatas de moedas (mesmo par - mantém apenas a primeira ocorrência)
    posicoes_unicas = []
    pares_vistos = set()
    for p in posicoes:
        par = p['par']
        if par not in pares_vistos:
            posicoes_unicas.append(p)
            pares_vistos.add(par)
    
    # Mostra TODAS as moedas em aberto (sem limite)
    moedas_para_grafico = posicoes_unicas
    
    if moedas_para_grafico:
        st.markdown("#### 📊 Gráficos de Velas (Candlestick)")
        # Cria tabs para cada moeda
        tabs = st.tabs([p['par'].replace('USDT', '') for p in moedas_para_grafico])
        
        for idx, (tab, posicao) in enumerate(zip(tabs, moedas_para_grafico)):
            with tab:
                symbol = posicao['par']
                preco_compra = posicao['preco_compra']
                preco_atual = posicao['preco_atual']
                # ⚡⚡⚡ USA LUCRO BRUTO (sem descontar taxas) para não ter prejuízo na exibição ⚡⚡⚡
                lucro_bruto = posicao.get('lucro_bruto', posicao.get('lucro_liquido', 0))
                perc_bruto = ((preco_atual - preco_compra) / preco_compra * 100) if preco_compra > 0 else posicao.get('percentual', 0)
                
                # Busca candles com o timeframe selecionado no sidebar
                candles_data = fetch_candles(symbol, limit=50, interval=selected_timeframe)
                
                if candles_data and candles_data.get('candles'):
                    # Cria gráfico
                    fig = criar_grafico_candlestick(candles_data, symbol, preco_compra, timeframe=selected_timeframe)
                    
                    if fig:
                        # Altura já está definida na função (600px para 3 gráficos: candlestick, volume, RSI)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Informações da posição (compactado)
                    lucro = lucro_bruto
                    perc = perc_bruto
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Compra", f"${preco_compra:.6f}")
                    with col2:
                        st.metric("Atual", f"${preco_atual:.6f}")
                    with col3:
                        st.metric("Lucro", f"${lucro_bruto:.4f} ({perc_bruto:+.2f}%)")
                    with col4:
                        st.metric("Tempo", posicao['tempo_str'])
                else:
                    st.info(f"⏳ Carregando candles de {symbol}...")
else:
    if data and data.get('error'):
        st.error(f"❌ {data.get('error')}")
    else:
        st.info("📭 Nenhuma moeda.")

# ============================================
# LOG
# ============================================
st.markdown("---")
st.markdown("### 📋 Log")

num_lines = st.slider("Linhas", 50, 300, 100, 50)
log = read_trading_log(num_lines)

if log.startswith("⚠️"):
    st.warning(log)
else:
    st.code(log, language='text')

# ============================================
# FOOTER
# ============================================
st.markdown("---")
st.markdown(f"""
<div style="text-align: center; color: #475569; font-size: 0.75rem; padding: 15px;">
    <strong style="color: #94a3b8;">Trading Bot</strong> • 
    Refresh: {REFRESH_INTERVAL}s • Taxa: 0.1%
</div>
""", unsafe_allow_html=True)

# ============================================
# AUTO-REFRESH SUAVE: Não limpa cache (deixa Streamlit gerenciar) para refresh mais suave
# ============================================
if auto_refresh:
    time.sleep(REFRESH_INTERVAL)  # Não limpa cache - deixa Streamlit usar TTL para gerenciar automaticamente
    # Isso torna o refresh mais suave, atualizando apenas o que mudou
    st.rerun()