#!/usr/bin/env python3
"""
Bot de Trading - HYBRID STRATEGY v12.0
========================================================================
🎯 META: $100/dia combinando SCALPING + EXPLOSÕES

📊 MODO SCALPING (mercado normal):
✅ Volume 1.5x+ da média
✅ RSI 25-55 subindo
✅ Lucro alvo: 0.5% ($25 × 0.5% = $0.125)
✅ Meta: 40 trades/dia = $5/dia (mínimo garantido)

💥 MODO EXPLOSÃO (pump detectado):
✅ Volume 5x+ da média
✅ Momentum +0.5%+
✅ Capital 2x ($50)
✅ Lucro alvo: 2%+ ($50 × 2% = $1)
✅ Meta: 10 trades/dia = $10/dia

MODO: SIMULAÇÃO
"""
import sys
import os

# Força stdout sem buffer
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except:
        pass
os.environ['PYTHONUNBUFFERED'] = '1'

import os
import sys
import hashlib
import json
import sqlite3
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import warnings

# Tenta importar WebSocket manager
try:
    from websocket_manager import WebSocketManager
    WEBSOCKET_DISPONIVEL = True
except ImportError:
    WEBSOCKET_DISPONIVEL = False
    print("⚠️ WebSocket não disponível, usando REST API")

from strategy_reversion import analisar_reversion # ESTRATÉGIA MEAN REVERSION (BOLLINGER + RSI)
from strategy_launchpad import analisar_launchpad # ESTRATÉGIA MOEDAS NOVAS (ATH BREAKOUT)
from strategy_solana import analisar_solana       # ESTRATÉGIA ONDA VERDE (SÓ SUBINDO)

# ML removido - usando apenas indicadores técnicos

# Importa funções de verificação de indicadores
try:
    from trading_bot_indicators import (
        verificar_ichimoku,
        verificar_bollinger_bounce,
        verificar_medias_moveis,
        verificar_rsi_otimo,
        verificar_volume_forte,
        verificar_padrao_velas
    )
    INDICADORES_DISPONIVEL = True
except ImportError as e:
    INDICADORES_DISPONIVEL = False
    print(f"⚠️ Módulo de indicadores não disponível: {e}")
    print("⚠️ ML Model não disponível - execute ml_data_collector.py e ml_model.py --train")

# Importa estratégia Bottom Fishing
try:
    from bottom_fishing import detectar_fundo_confirmado, verificar_suporte_adicional
    BOTTOM_FISHING_DISPONIVEL = True
    print("✅ Bottom Fishing strategy loaded")
except ImportError as e:
    BOTTOM_FISHING_DISPONIVEL = False
    print(f"⚠️ Bottom Fishing não disponível: {e}")

# Tenta importar trading_core
try:
    from trading_core import calcular_lucro
except ImportError:
    # Fallback se não tiver trading_core
    def calcular_lucro(valor_investido, preco_atual, quantidade):
        valor_atual = preco_atual * quantidade
        lucro_bruto = valor_atual - valor_investido
        taxa = valor_investido * 0.001 + valor_atual * 0.001  # 0.1% cada lado
        lucro_liquido = lucro_bruto - taxa
        return {
            'lucro_bruto': lucro_bruto,
            'lucro_liquido': lucro_liquido,
            'taxa': taxa,
            'valor_atual': valor_atual
        }

warnings.filterwarnings('ignore')

# Timezone do Brasil
try:
    from zoneinfo import ZoneInfo
    TZ_BRASIL = ZoneInfo('America/Sao_Paulo')
except ImportError:
    try:
        import pytz
        TZ_BRASIL = pytz.timezone('America/Sao_Paulo')
    except ImportError:
        TZ_BRASIL = None

def agora_brasil():
    """Retorna datetime atual no timezone do Brasil"""
    if TZ_BRASIL:
        return datetime.now(TZ_BRASIL)
    else:
        return datetime.now() - timedelta(hours=3)


# ============================================
# CONFIGURAÇÕES GLOBAIS
# ============================================
LOG_LEVEL = 'VERBOSE'  # 'MINIMAL', 'NORMAL', 'VERBOSE' - NORMAL mostra compras/vendas

# 🎮 MODO SIMULAÇÃO FORÇADO - Não executa ordens reais
MODO_SIMULACAO_FORCADO = True  # ⚠️ SEMPRE SIMULAÇÃO - mude para False para operar de verdade


# ============================================
# CONFIGURAÇÕES v9.0 - EXPLOSIVE SCALPING
# ============================================
class Config:
    """
    Configuração: Multi-Indicator Strategy v15.0
    Meta: $100/dia líquido | $100/trade | 3-5% lucro
    """
    print("🚀 BOT INICIANDO... (FORCE PRINT)", flush=True)
    MIN_VOLUME_24H = 5000000         # $5M volume mínimo (SÓ MOEDAS LÍQUIDAS!)
    MIN_PRECO = 0.0001
    MAX_PRECO = 50000
    
    # === 💵 CAPITAL (META: $5/HORA = $120/DIA) ===
    CAPITAL_POR_OPERACAO = 150.0
    CAPITAL_POR_OP = 150.0           # Alias crítico
    CAPITAL_EXPLOSAO = 75.0         
    CAPITAL_ML = 75.0               
    CAPITAL_MAXIMO = 1500.0
    MAX_POSICOES = 8
    
    # === 🛡️ GESTÃO DE RISCO (STOP LOSS ATIVADO!) ===
    STOP_LOSS_PCT = 0.02            # 2% Stop Loss (Estanca sangramento!)
    VENDER_COM_PREJUIZO = True      # Permite vender no Stop Loss
    TIMEOUT_NEGATIVO = 3600         # 1 hora (se ficar negativo 1h, analisa saída)
    
    # === 📊 CRITÉRIOS DE ENTRADA (MAIS RIGOROSOS) ===
    VELAS_VERDES_MIN = 3
    RSI_SUBINDO_MIN = 3.0           # Exige força na recuperação
    RSI_MAX_ENTRADA = 55
    RSI_MIN_ENTRADA = 25            # RSI < 25 para fundo (era 30)
    MOMENTUM_MIN = 0.008            # 0.8% momentum
    
    # Anti-Ban Configs
    SPREAD_MAX = 0.002              # 0.2% spread (moedas líquidas tem spread baixo)
    
    # === ⭐ SCORE E CONFIRMAÇÕES ===
    SCORE_MINIMO = 50               # Padrão — ajustado dinamicamente pelo regime
    CONFIRMACOES_MINIMAS = 5        # 5 de 6 indicadores
    VERIFICAR_TREND_5MIN = True     # Usa Ichimoku (Tendência de Alta Obrigatória)
    MAX_POSITION_IN_RANGE = 0.5     # Máx 50% range
    
    # === 🎯 LUCRO E STOP (CONFIGURAÇÃO OTIMIZADA FORENSE) ===
    # Valores agora definidos no bloco principal abaixo para evitar duplicidade.
    VENDER_COM_PREJUIZO = True
    PAUSAR_ENTRADAS = False          # True = BEAR_CRASH: não abre novas posições

    # === 🛑 CIRCUIT BREAKER (protecção de capital) ===
    PERDA_MAXIMA_DIA     = 5.0       # Para de comprar se perder mais de $5 no dia
    HORARIO_ATIVO_INICIO = 9         # Hora de início (horário Brasília)
    HORARIO_ATIVO_FIM    = 23        # Hora de fim (horário Brasília)
    CIRCUIT_BREAKER_ATIVO = True     # Activar/desactivar a protecção
    
    # === 💥 MODO EXPLOSÃO (RASPA LUCRO) ===
    # === 🎯 MODO APOCALIPSE (CRASH SCALPING) ===
    # Mercado em Queda Livre (ADX > 60). Só opera repiques extremos.
    BOTTOM_FISHING_ATIVO = True       
    EXPLOSAO_ATIVO = False            # Não há explosão em crash
    
    BOTTOM_SCORE_MINIMO = 50          
    BOTTOM_BB_DIST_MAX = 0.20         # 20% longe da BB (Pânico)
    BOTTOM_RSI_MIN = 0                # Aceita zero
    BOTTOM_RSI_MAX = 20               # SÓ COMPRA SE RSI < 20 (Sobrevenda Extrema)
    BOTTOM_ANTI_FALL_MIN = 2          
    BOTTOM_CANDLE_GAIN_MIN = 0.001    
    BOTTOM_DUMP_MIN = 0.010           # Dump forte (>1%)
    BOTTOM_RSI_DELTA_MIN = 0.1        
    BOTTOM_VOL_RATIO_MIN = 1.0        # Exige volume pelo menos igual a média
    BOTTOM_EMA_FILTER_PCT = -10.0     # IGNORA TENDÊNCIA (Contra-tendência pura)
    BOTTOM_LUCRO_ALVO = 0.010         # 1.0% Alvo
    TIMEOUT_MAXIMO = 1800             # 30 min (Giro rápido)
    
    # === 📊 RSI ===
    RSI_ENTRADA_MIN = 1             
    RSI_ENTRADA_MAX = 25            
    RSI_OVERBOUGHT = 50             
    RSI_OVERSOLD = 20
    
    # === OUTROS - LIQUIDEZ (VARREDURA TOTAL) ===
    VOLUME_24H_MIN = 300000         # $300k (Baixado para pegar mid-caps)
    # === BLACKLIST: Stablecoins e Major Coins ===
    EXCLUIR_MOEDAS = [
        # Major coins (muito líquidas, volatilidade baixa)
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT',
        # Stablecoins (NUNCA tradear!)
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 'USDN',
        'USDC1', 'USD1USDT', 'USDCUSDT', 'DAIUSDT', 'BUSDUSDT', 'TUSDUSDT', 'USDPUSDT',
        'FDUSD', 'FDUSDUSDT', 'EURUSDT', 'GBPUSDT',
        # Wrapped tokens stable
        'WBTCUSDT', 'WETHUSDT',
        # MOEDAS MORTAS - Histórico comprovado de ficar paradas 10+ horas
        'COCOSUSDT', 'CAKEUSDT', 'BTTUSDT',
        'ERNUSDT', 'PLAUSDT', 'DARUSDT', # Bloqueadas a pedido (Moedas Mortas)
        'FRONTUSDT', 'OMGUSDT', 'LITUSDT', 'POLYUSDT', 'TOMOUSDT', 
        'FTMUSDT', 'NEBLUSDT', 'FXSUSDT' # Zumbis detectados como Launchpad erroneamente
    ]
    SPREAD_MAX = 0.002              # 0.2% spread (Mantido seguro)
    COOLDOWN_MOEDA_TEMPO = 120      # 2min cooldown (rotação rápida)
    INTERVALO_ANALISE = 5.0         # 5s: Scan agressivo
    JITTER_ANALISE = 0.1            # 0.1s
    INTERVALO_VERIFICACAO = 1.0     
    TIMEFRAME = '5m'                # 5 minutos - menos ruído, sinais mais confiáveis
    NUM_CANDLES_ANALISE = 200
    TAXA = 0.001
    MAX_WORKERS = 15                # 15 Threads: Processamento Massivo e Rápido
    PARES_POR_CICLO = 50            # Analisa blocos de 50 moedas
    
    # === SCANNER GLOBAL: Busca oportunidades em TODAS as moedas ===
    WHITELIST_PAIRS = None
    
    # Filtro de Atividade Mínima
    VOLUME_MIN_24H = 2000000         # $2M mínimo (moedas com boa liquidez)
    
    # === PARAMETROS CORE ===
    LUCRO_MINIMO_PCT = 0.008        # 0.8% Alvo
    LUCRO_MINIMO_ABS = 0.80         
    VOLUME_RATIO_MIN = 1.2          
    
    MIN_CANDLE_VOLUME_USDT = 0  
    
    TAKE_PROFIT_PCT = 0.008         # 0.8% Alvo (R:R 2:1 com stop 0.4%)
    STOP_LOSS_PCT = 0.004           # 0.4% Stop (corta rápido)
    SCORE_MINIMO = 65               
    MAX_POSICOES = 8                # 8 posições para mais rotação
    TEMPO_MAXIMO_AGUARDAR = 2700    # 45 minutos max
    STOP_LOSS_TIMEOUT = -0.008
    MOMENTUM_ACELERADO = 1.5
    
    # === 📊 SCORE INDICADORES ===
    SCORE_RSI_OVERSOLD = 0.0
    SCORE_RSI_SUBINDO = 0.40       # Peso total na SUBIDA
    SCORE_RSI_REVERSAO = 0.0

    
    # === 📊 SCORE BONIFICAÇÕES ===
    # RSI em zona de reversão
    SCORE_RSI_OVERSOLD = 0.25      # +25% se RSI < 25
    SCORE_RSI_SUBINDO = 0.30       # +30% se RSI subindo forte
    SCORE_RSI_REVERSAO = 0.35      # +35% se reversão confirmada
    
    # Volume
    SCORE_VOLUME_ALTO = 0.20       # +20% se volume > 1.5x
    SCORE_VOLUME_EXPLOSAO = 0.30   # +30% se volume > 2.5x
    
    # Padrões de reversão
    SCORE_HAMMER = 0.25            # +25% por hammer
    SCORE_BULLISH_ENGULFING = 0.30 # +30% por engulfing
    SCORE_REVERSAO_FUNDO = 0.35    # +35% por reversão de fundo

    # Ichimoku
    SCORE_ICHIMOKU_CLOUD = 0.30    # +30% se Preço > Nuvem
    SCORE_ICHIMOKU_TK_CROSS = 0.20 # +20% se Tenkan > Kijun
    
    # Momentum
    SCORE_MOMENTUM_FORTE = 0.20    # +20% por momentum forte
    SCORE_VELAS_VERDES = 0.15      # +15% por velas verdes
    
    # === 📉 PENALIZAÇÕES ===
    PENALIZACAO_RSI_CAINDO = 0.50      # -50% se RSI caindo
    PENALIZACAO_VELA_VERMELHA = 0.40   # -40% se última vela vermelha
    PENALIZACAO_VOLUME_BAIXO = 0.35    # -35% se volume baixo
    PENALIZACAO_TOPO = 0.60            # -60% se perto de topo
    
    # === EMA ===
    EMA_RAPIDA = 9
    EMA_LENTA = 21



# Variável global para controlar o log
_log_file_initialized = False
_log_file = None

def _close_log_file():
    global _log_file, _log_file_initialized
    if _log_file:
        try:
            _log_file.close()
        except:
            pass
        _log_file = None
        _log_file_initialized = False

def _init_log_file():
    global _log_file_initialized, _log_file
    
    if _log_file_initialized:
        return
        
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_path = os.path.join(log_dir, 'bot.log')
    _log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
    _log_file_initialized = True

def log(msg: str, level: str = 'VERBOSE'):
    global _log_file
    
    # Filtro simplificado: Se LOG_LEVEL é VERBOSE, mostra tudo.
    if LOG_LEVEL == 'MINIMAL' and level != 'MINIMAL':
        return
    if LOG_LEVEL == 'NORMAL' and level == 'VERBOSE':
        return
    
    if not _log_file_initialized:
        _init_log_file()
    
    ts = agora_brasil().strftime('%H:%M:%S')
    log_msg = f"[{ts}] {msg}"
    
    print(log_msg, flush=True)
    
    if _log_file:
        try:
            _log_file.write(log_msg + '\n')
            _log_file.flush()
        except:
            pass

def log_symbol(symbol: str, msg: str, level: str = 'NORMAL'):
    global _log_file
    
    if LOG_LEVEL == 'MINIMAL' and level != 'MINIMAL':
        return
    elif LOG_LEVEL == 'NORMAL' and level == 'VERBOSE':
        return
    
    if not _log_file_initialized:
        _init_log_file()
    
    ts = agora_brasil().strftime('%H:%M:%S')
    log_msg = f"[{ts}] {symbol} | {msg}"
    
    print(log_msg, flush=True)
    
    if _log_file:
        try:
            _log_file.write(log_msg + '\n')
            _log_file.flush()
        except:
            pass


class TradingBot:
    """
    ╔════════════════════════════════════════════════════════════════╗
    ║  EXPLOSIVE SCALPING v9.0                                        ║
    ║                                                                 ║
    ║  🎯 Estratégia: Explosões + Reversões (RSI oversold + Volume)   ║
    ║  🛡️ Proteção: NUNCA vende com prejuízo                         ║
    ║  💰 Meta: $100/dia | 1%+ por operação                          ║
    ╚════════════════════════════════════════════════════════════════╝
    """
    
    def __init__(self, api_key, api_secret, cfg: Config = None, testnet=False, modo_simulacao=None):
        self.testnet = testnet
        self.api_key = api_key
        self.api_secret = api_secret
        self.cfg = cfg or Config()
        
        log("═" * 60, 'MINIMAL')
        log("🚀 Bot de Trading - EXPLOSIVE SCALPING v9.0", 'MINIMAL')
        log("═" * 60, 'MINIMAL')
        log(f"💰 Capital por operação: ${self.cfg.CAPITAL_POR_OP}", 'MINIMAL')
        log(f"🎯 Lucro mínimo: {self.cfg.LUCRO_MINIMO_PCT*100:.1f}% (${self.cfg.LUCRO_MINIMO_ABS:.2f}) - NUNCA MENOS!", 'MINIMAL')
        log(f"📊 RSI Entrada: {self.cfg.RSI_ENTRADA_MIN}-{self.cfg.RSI_ENTRADA_MAX} (oversold + subindo +{self.cfg.RSI_SUBINDO_MIN})", 'MINIMAL')
        log(f"📈 Volume mínimo: {self.cfg.VOLUME_RATIO_MIN}x da média (só explosões!)", 'MINIMAL')
        log(f"⏱️ Timeframe: {self.cfg.TIMEFRAME} | Timeout: {self.cfg.TEMPO_MAXIMO_AGUARDAR//60}min", 'MINIMAL')
        log("═" * 60, 'MINIMAL')
        
        # 🎮 FORÇA MODO SIMULAÇÃO
        if MODO_SIMULACAO_FORCADO:
            modo_simulacao = True
            log("🎮 MODO SIMULAÇÃO FORÇADO (não executa ordens reais)", 'MINIMAL')
        
        # Conecta à Binance REST (para klines e dados)
        self.client = None
        try:
            self.client = Client(api_key, api_secret, testnet=testnet)
            # Tenta ping mas não mata o bot se falhar (pode ser ban temporário de REST)
            try:
                self.client.ping()
                log("✅ Conectado à Binance REST API", 'MINIMAL')
            except Exception as e:
                log(f"⚠️ Aviso: Ping falhou (possível BAN), mas Client inicializado: {e}", 'MINIMAL')
        except Exception as e:
            log(f"⚠️ Erro FATAL ao criar Client: {e}", 'MINIMAL')
        
        # 🔌 WebSocket para preços em tempo real
        self.ws_manager = None
        if WEBSOCKET_DISPONIVEL:
            try:
                # Passa as chaves diretamente em vez do client (que pode estar banido)
                self.ws_manager = WebSocketManager(None, api_key=api_key, api_secret=api_secret, testnet=testnet)
                log("✅ WebSocket Manager inicializado", 'MINIMAL')
            except Exception as e:
                log(f"⚠️ Erro ao iniciar WebSocket: {e}", 'MINIMAL')
                self.ws_manager = None
        
        # Modo de operação - SEMPRE SIMULAÇÃO se MODO_SIMULACAO_FORCADO
        self.trading_enabled = False  # 🎮 SIMULAÇÃO
        log("🎮 MODO SIMULAÇÃO ATIVADO (grava no banco, não executa ordens)", 'MINIMAL')
        
        # Estruturas de dados
        self.posicoes = {}
        self.posicoes_lock = threading.RLock()
        self.cooldown_moedas = {}
        self.last_buy_time = 0  # CRÍTICO: Throttle Global (Evita metralhadora)
        self.running = False
        
        # Cache
        self.precos_cache = {}
        self.klines_cache = {}
        self.cache_lock = threading.RLock()
        
        # Banco de dados
        self.db_path = os.path.join(os.path.dirname(__file__), 'trading_data.db')
        self._init_database()
        self._sincronizar_posicoes()
        
        # 💾 Carrega klines do disco (Anti-Ban)
        self._carregar_cache_klines()
    
        # 💾 Carrega klines do disco (Anti-Ban)
        self._carregar_cache_klines()
        
        # 🧠 INICIALIZA CÉREBRO ADAPTATIVO
        self.market_regime = "UNKNOWN"
        self.last_regime_update = 0
        self.update_market_regime() # Roda primeira vez
    
    def update_market_regime(self):
        """
        🧠 CÉREBRO ADAPTATIVO: Analisa o mercado e ajusta a estratégia DINAMICAMENTE.
        Não depende mais de config manual. Se o mercado muda, o bot muda.
        """
        try:
            if time.time() - self.last_regime_update < 300: # 5 min cache
                return

            log("🧠 Analisando Clima do Mercado (Amostragem Top 25 moedas)...", 'MINIMAL')
            
            # Amostragem diversificada para entender o mercado como um todo
            top_coins = [
                'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 
                'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'MATICUSDT',
                'DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'WIFUSDT', # Memes
                'FETUSDT', 'RENDERUSDT', # AI
                'UNIUSDT', 'AAVEUSDT', 'LDOUSDT', # DeFi
                'NEARUSDT', 'ATOMUSDT', 'LTCUSDT', 'FILUSDT', 'ICPUSDT', 'IMXUSDT'
            ]
            trends_up = 0
            adx_sum = 0
            count = 0
            
            for symbol in top_coins:
                df = self.get_klines(symbol, limit=60, interval='1h') # 60h de análise (Macro)
                if df is not None and not df.empty:
                    # EMA 50 Trends
                    ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
                    close = df['close'].iloc[-1]
                    if close > ema50:
                        trends_up += 1
                    
                    # ADX Simplificado (Volatilidade/Força)
                    try:
                        high = df['high']
                        low = df['low']
                        close_series = df['close']
                        # Usando Panda TA se disponivel ou calculo manual simplificado de range
                        tr = high - low
                        atr = tr.rolling(14).mean().iloc[-1]
                        price_range_pct = (atr / close) * 100
                        adx_sum += price_range_pct # Usando % range como proxy de volatilidade por simplicidade
                    except:
                        pass
                    count += 1
            
            if count == 0: return

            bull_ratio = trends_up / count
            volatility_avg = adx_sum / count
            
            # 🔄 MÁQUINA DE ESTADOS
            novo_regime = "SIDEWAYS"
            if bull_ratio > 0.7:
                novo_regime = "BULL_RALLY"
            elif bull_ratio < 0.3:
                novo_regime = "BEAR_CRASH" if volatility_avg > 0.8 else "BEAR_SLOW"
            else:
                novo_regime = "SIDEWAYS"

            self.market_regime = novo_regime
            self.last_regime_update = time.time()
            
            # 🎛️ APLICAÇÃO DOS PARÂMETROS
            log(f"🧠 DIAGNÓSTICO: {novo_regime} (Bulls: {bull_ratio*100:.0f}% | Vol: {volatility_avg:.2f}%)", 'MINIMAL')
            
            if novo_regime == "BULL_RALLY":
                self.cfg.SCORE_MINIMO = 45
                self.cfg.MAX_POSICOES = 8
                self.cfg.PAUSAR_ENTRADAS = False
                self.cfg.TAKE_PROFIT_PCT = 0.008   # 0.8%
                self.cfg.TEMPO_MAXIMO_AGUARDAR = 20 * 60  # 20 min
                log("🚀 MODO ATAQUE: Mercado em Alta! Comprando agressivamente.", 'MINIMAL')

            elif novo_regime == "BEAR_CRASH":
                self.cfg.SCORE_MINIMO = 48
                self.cfg.MAX_POSICOES = 4
                self.cfg.PAUSAR_ENTRADAS = False
                self.cfg.TAKE_PROFIT_PCT = 0.004   # 0.4% — sai rápido
                self.cfg.TEMPO_MAXIMO_AGUARDAR = 4 * 60   # 4 min — rotação rápida
                log("⚡ MICRO-SCALP: Bear market. Target 0.4%, saída em 4min.", 'MINIMAL')

            elif novo_regime == "BEAR_SLOW":
                self.cfg.SCORE_MINIMO = 50
                self.cfg.MAX_POSICOES = 5
                self.cfg.PAUSAR_ENTRADAS = False
                self.cfg.TAKE_PROFIT_PCT = 0.006   # 0.6%
                self.cfg.TEMPO_MAXIMO_AGUARDAR = 10 * 60  # 10 min
                log("🐻 MODO URSO: Baixa Lenta. Target 0.6%, 10min.", 'MINIMAL')

            else: # SIDEWAYS
                self.cfg.SCORE_MINIMO = 48
                self.cfg.MAX_POSICOES = 8
                self.cfg.PAUSAR_ENTRADAS = False
                self.cfg.TAKE_PROFIT_PCT = 0.007   # 0.7%
                self.cfg.TEMPO_MAXIMO_AGUARDAR = 15 * 60  # 15 min
                log("🦀 MODO CARANGUEJO: Mercado lateral. Target 0.7%, 15min.", 'MINIMAL')

        except Exception as e:
            log(f"🧠 Erro no Auto-Adapt: {e}", 'VERBOSE')

    def _salvar_cache_klines(self):
        """Salva o cache de klines para persistência (Disco)"""
        cache_path = os.path.join(os.path.dirname(__file__), 'status', 'klines_data.json')
        try:
            with self.cache_lock:
                data_para_salvar = {}
                for key, val in self.klines_cache.items():
                    if 'data' in val and isinstance(val['data'], pd.DataFrame):
                        df = val['data']
                        essential_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                        available_cols = [c for c in essential_cols if c in df.columns]
                        # Salva apenas registros numéricos para compactação
                        data_para_salvar[key] = {
                            'data': df[available_cols].to_dict('records'),
                            'timestamp': val['timestamp']
                        }
                
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'w') as f:
                    json.dump(data_para_salvar, f)
        except:
            pass

    def _carregar_cache_klines(self):
        """Carrega o cache de klines do disco"""
        cache_path = os.path.join(os.path.dirname(__file__), 'status', 'klines_data.json')
        if not os.path.exists(cache_path):
            return
            
        try:
            with open(cache_path, 'r') as f:
                data_carregada = json.load(f)
                
            with self.cache_lock:
                for key, val in data_carregada.items():
                    df = pd.DataFrame(val['data'])
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    if 'timestamp' in df.columns:
                        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                    self.klines_cache[key] = {'data': df, 'timestamp': val['timestamp']}
            log(f"💾 Carregados {len(data_carregada)} gráficos do cache em disco", 'NORMAL')
        except Exception as e:
            log(f"⚠️ Erro ao carregar cache de klines: {e} | Arquivo corrompido, deletando...", 'VERBOSE')
            try:
                os.remove(cache_path)
            except:
                pass

    def _init_database(self):
        """Inicializa banco de dados"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de operações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                par TEXT NOT NULL,
                preco_compra REAL NOT NULL,
                quantidade_compra REAL NOT NULL,
                valor_compra REAL NOT NULL,
                data_compra TEXT NOT NULL,
                ordem_id_compra TEXT UNIQUE NOT NULL,
                preco_alvo REAL,
                estrategia TEXT,
                modo_operacao TEXT,
                preco_venda REAL,
                quantidade_venda REAL,
                valor_venda REAL,
                data_venda TEXT,
                ordem_id_venda TEXT,
                preco_venda_real REAL,
                lucro REAL,
                percentual_lucro REAL,
                tempo_operacao REAL
            )
        ''')
        
        # Tabela de resultados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operacao_id INTEGER,
                ordem_id_compra TEXT,
                par TEXT NOT NULL,
                preco_compra REAL NOT NULL,
                preco_venda REAL NOT NULL,
                quantidade REAL NOT NULL,
                lucro REAL NOT NULL,
                percentual REAL NOT NULL,
                tempo_operacao REAL,
                preco_alvo REAL,
                timestamp_compra TEXT,
                timestamp_venda TEXT,
                preco_venda_real REAL,
                modo_operacao TEXT,
                estrategia_usada TEXT,
                motivo_venda TEXT,
                FOREIGN KEY (operacao_id) REFERENCES operacoes(id)
            )
        ''')
        
        # Tabela de inicialização
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inicializacao (
                id INTEGER PRIMARY KEY,
                data_inicio TEXT NOT NULL,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Registra inicialização
        cursor.execute('SELECT id FROM inicializacao WHERE id = 1')
        if not cursor.fetchone():
            cursor.execute(
                'INSERT INTO inicializacao (id, data_inicio) VALUES (1, ?)',
                (agora_brasil().isoformat(),)
            )
        
        # ═══════════════════════════════════════════════════════════════
        # MIGRAÇÃO: Adiciona colunas faltantes na tabela resultados
        # ═══════════════════════════════════════════════════════════════
        try:
            cursor.execute("PRAGMA table_info(resultados)")
            colunas_existentes = [col[1] for col in cursor.fetchall()]
            
            if 'ordem_id_compra' not in colunas_existentes:
                cursor.execute('ALTER TABLE resultados ADD COLUMN ordem_id_compra TEXT')
                log("✅ Migração: Adicionada coluna ordem_id_compra em resultados", 'MINIMAL')
            
            if 'motivo_venda' not in colunas_existentes:
                cursor.execute('ALTER TABLE resultados ADD COLUMN motivo_venda TEXT')
                log("✅ Migração: Adicionada coluna motivo_venda em resultados", 'MINIMAL')
        except Exception as e:
            log(f"⚠️ Erro na migração: {e}", 'MINIMAL')
        
        conn.commit()
        conn.close()
        log("✅ Banco de dados inicializado", 'VERBOSE')
    
    def _sincronizar_posicoes(self):
        """Sincroniza posições do banco"""
        log("🔄 Sincronizando posições...", 'VERBOSE')
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT par, preco_compra, quantidade_compra, valor_compra, 
                       data_compra, ordem_id_compra, preco_alvo, estrategia
                FROM operacoes
                WHERE data_venda IS NULL
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                log(f"📦 {len(rows)} posições abertas no banco", 'MINIMAL')
                
                for row in rows:
                    par, preco, qty, valor, data, ordem_id, alvo, estrategia = row
                    
                    try:
                        ts = datetime.fromisoformat(data) if isinstance(data, str) else agora_brasil()
                        if TZ_BRASIL and ts.tzinfo is None:
                            ts = TZ_BRASIL.localize(ts) if hasattr(TZ_BRASIL, 'localize') else ts.replace(tzinfo=TZ_BRASIL)
                    except:
                        ts = agora_brasil()
                    
                    posicao = {
                        'symbol': par,
                        'preco_compra': preco,
                        'quantidade': qty,
                        'valor': valor,
                        'timestamp': ts,
                        'stop_loss': 0,  # 🛡️ ZERO - nunca vende com prejuízo
                        'take_profit': alvo or preco * (1 + self.cfg.TAKE_PROFIT_PCT),
                        'ordem_id': ordem_id,
                        'estrategia': estrategia or 'SINCRONIZADO',
                        'max_preco': preco,
                        'trailing_ativo': False
                    }
                    
                    with self.posicoes_lock:
                        self.posicoes[ordem_id] = posicao
                    
                    log(f"   ✅ {par}: ${valor:.2f} @ ${preco:.6f}", 'VERBOSE')
                
                log(f"✅ {len(self.posicoes)} posições carregadas", 'MINIMAL')
            else:
                log("📭 Nenhuma posição aberta", 'MINIMAL')
                
        except Exception as e:
            log(f"⚠️ Erro ao sincronizar: {e}", 'MINIMAL')
    
    def _salvar_stats(self, **kwargs):
        """Salva estatísticas do bot para compartilhamento de estado"""
        try:
            stats_path = os.path.join('status', 'bot_stats.json')
            os.makedirs('status', exist_ok=True)
            
            data = {}
            if os.path.exists(stats_path):
                try:
                    with open(stats_path, 'r') as f:
                        data = json.load(f)
                except:
                    pass
            
            data.update(kwargs)
            data['last_update'] = datetime.now().isoformat()
            
            with open(stats_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log(f"⚠️ Erro ao salvar stats: {e}", 'VERBOSE')

    def get_preco(self, symbol: str, force: bool = False) -> Optional[float]:
        """Obtém preço atual - usa WebSocket se disponível, senão REST"""
        now = time.time()
        
        # 1️⃣ Tenta WebSocket primeiro (mais rápido)
        if self.ws_manager:
            try:
                preco_ws = self.ws_manager.get_price(symbol)
                if preco_ws and preco_ws > 0:
                    # Atualiza cache
                    with self.cache_lock:
                        self.precos_cache[symbol] = {'price': preco_ws, 'timestamp': now}
                    return preco_ws
            except:
                pass
        
        # 1️⃣ Tenta WebSocket primeiro (Gratuito e Instantâneo)
        if self.ws_manager and self.ws_manager.is_connected():
            preco_ws = self.ws_manager.get_price(symbol)
            if preco_ws is not None:
                return preco_ws

        # 2️⃣ Verifica cache REST
        with self.cache_lock:
            if symbol in self.precos_cache and not force:
                cached = self.precos_cache[symbol]
                if now - cached['timestamp'] < 1.0:  # 1s TTL (WS é melhor)
                    return cached['price']
        
        # 3️⃣ Fallback para REST API
        if self.client:
            try:
                ticker = self.client.get_symbol_ticker(symbol=symbol)
                preco = float(ticker['price'])
                
                with self.cache_lock:
                    self.precos_cache[symbol] = {'price': preco, 'timestamp': now}
                
                return preco
            except Exception as e:
                # Se for erro 1003 (IP Ban), silenciamos se tivermos WS
                if "1003" in str(e) and self.ws_manager and self.ws_manager.is_connected():
                    return None
                log_symbol(symbol, f"⚠️ Erro ao obter preço REST: {e}", 'VERBOSE')
        
        return None
    
    def get_klines(self, symbol: str, limit: int = 30, interval: str = None) -> Optional[pd.DataFrame]:
        """Obtém candles - Prioriza o Buffer do WebSocket (Anti-Ban) se Timeframe bater"""
        now = time.time()
        tf = interval or self.cfg.TIMEFRAME
        
        # 🟢 1. PRIORIDADE TOTAL: WebSocket Buffer (Gratuito e Instantâneo)
        # Só usa WebSocket se o timeframe pedido for o mesmo do bot
        use_websocket = (tf == self.cfg.TIMEFRAME)
        
        if use_websocket and self.ws_manager and self.ws_manager.is_connected():
            df_ws = self.ws_manager.get_klines_buffer(symbol, limit)
            if df_ws is not None:
                # Transforma colunas para float
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df_ws.columns:
                        df_ws[col] = pd.to_numeric(df_ws[col], errors='coerce')
                return df_ws

        # 🟡 2. SEGUNDA OPÇÃO: Cache REST (2 segundos de vida)
        key = f"{symbol}_{tf}_{limit}"
        with self.cache_lock:
            if key in self.klines_cache:
                cached = self.klines_cache[key]
                if now - cached['timestamp'] < 2.0:  # 2s TTL
                    return cached['data']
        
        # 🔴 3. ÚLTIMA OPÇÃO: REST API (Custa Peso e pode causar Ban)
        if not self.client:
            return None
            
        try:
            klines = self.client.get_klines(
                symbol=symbol,
                interval=tf,
                limit=limit
            )
            
            if not klines:
                return None
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Converte timestamps para datetime no DataFrame
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Salva no cache
            with self.cache_lock:
                self.klines_cache[key] = {'data': df, 'timestamp': now}
                
            return df
        except Exception as e:
            if "1003" in str(e):
                 log_symbol(symbol, "🚫 IP Bloqueado em get_klines. Use WebSocket!", 'MINIMAL')
            return None
    
    def calcular_rsi(self, df: pd.DataFrame, period: int = 14) -> Tuple[float, float]:
        """
        Calcula RSI atual e anterior
        Retorna: (rsi_atual, rsi_anterior)
        """
        if df is None:
            log(f"⚠️ RSI: DataFrame é None", 'VERBOSE')
            return 50.0, 50.0
            
        num_candles = len(df)
        if num_candles < period + 2:
            log(f"⚠️ RSI: Dados insuficientes ({num_candles} candles, precisa {period + 2})", 'VERBOSE')
            return 50.0, 50.0
        
        try:
            closes = df['close'].values.astype(float)
            
            # Debug: mostra últimos preços
            
            deltas = np.diff(closes)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            # RSI atual (últimos 14 períodos)
            avg_gain = np.mean(gains[-period:])
            avg_loss = np.mean(losses[-period:])
            
            
            if avg_loss == 0:
                rsi_atual = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                rsi_atual = 100.0 - (100.0 / (1.0 + rs))
            
            # RSI anterior (1 período atrás)
            avg_gain_ant = np.mean(gains[-(period+1):-1])
            avg_loss_ant = np.mean(losses[-(period+1):-1])
            
            if avg_loss_ant == 0:
                rsi_anterior = 100.0 if avg_gain_ant > 0 else 50.0
            else:
                rs_ant = avg_gain_ant / avg_loss_ant
                rsi_anterior = 100.0 - (100.0 / (1.0 + rs_ant))
            
            
            return rsi_atual, rsi_anterior
            
        except Exception as e:
            log(f"⚠️ RSI: Erro no cálculo: {type(e).__name__}: {e}", 'VERBOSE')
            import traceback
            log(f"   {traceback.format_exc()}", 'VERBOSE')
            return 50.0, 50.0
    
    def calcular_volume_ratio(self, df):
        try:
            vols = df["volume"].values.astype(float)
            if len(vols) < 10:
                return 0.0
            vol_atual, vol_media = vols[-1], vols[-10:-1].mean()
            return vol_atual / vol_media if vol_media > 0 else 0.0
        except:
            return 0.0

    
    def calcular_score_oportunidade(self, df: pd.DataFrame, rsi_atual: float, vol_ratio: float, 
                                     momentum: float, velas_verdes: int) -> int:
        """
        Calcula score de qualidade da oportunidade (0-100)
        Só compra se score >= 70
        """
        score = 0
        
        # 1. Volume (0-25 pontos) - quanto mais volume, melhor
        if vol_ratio >= 10:
            score += 25
        elif vol_ratio >= 7:
            score += 20
    
        elif vol_ratio >= 3:
            score += 10
        
        # 2. RSI ideal 35-45 (0-25 pontos) - espaço para subir
        if 35 <= rsi_atual <= 45:
            score += 25  # IDEAL!
        elif 30 <= rsi_atual <= 50:
            score += 15
        elif 45 <= rsi_atual <= 55:
            score += 10
        elif 25 <= rsi_atual <= 30:
            score += 5
        
        # 3. Momentum (0-20 pontos) - força da vela
        if momentum >= 0.01:  # 1%+
            score += 20
        elif momentum >= 0.007:  # 0.7%+
            score += 15
        elif momentum >= 0.005:  # 0.5%+
            score += 10
        elif momentum >= 0.003:
            score += 5
        
        # 4. Velas verdes (0-15 pontos) - tendência
        score += min(velas_verdes * 3, 15)
        
        # 5. Posição no range (0-15 pontos) - não compra no topo!
        try:
            min_price = df['low'].tail(10).min()
            max_price = df['high'].tail(10).max()
            current = df['close'].iloc[-1]
            
            if max_price > min_price:
                position_in_range = (current - min_price) / (max_price - min_price)
                
                if position_in_range < 0.3:  # Início do movimento
                    score += 15
                elif position_in_range < 0.5:  # Meio do range
                    score += 10
                elif position_in_range < 0.7:  # Já subiu bastante
                    score += 5
                # Se >= 0.7 (perto do topo), não ganha pontos
        except:
            pass  # Se falhar, não adiciona pontos
        
        # 6. Bollinger Bands Bounce (0-15 pontos) - perto da lower band!
        try:
            # Calcula BB lower (20 períodos, 2 std)
            closes_series = pd.Series(df['close'].values)
            bb_sma = closes_series.rolling(window=20).mean()
            bb_std = closes_series.rolling(window=20).std()
            bb_lower = bb_sma - (bb_std * 2)
            
            # Distância até lower band
            current_price = df['close'].iloc[-1]
            lower_value = bb_lower.iloc[-1]
            
            if not pd.isna(lower_value) and lower_value > 0:
                distancia_lower = (current_price - lower_value) / current_price
                
                # Quanto mais perto da lower, mais pontos
                if distancia_lower < 0.005:  # < 0.5% da lower
                    score += 15  # Muito perto! Grande oportunidade
                elif distancia_lower < 0.015:  # < 1.5% da lower
                    score += 10  # Perto, boa oportunidade
                elif distancia_lower < 0.03:  # < 3% da lower
                    score += 5   # Próximo, oportunidade moderada
        except:
            pass  # Se falhar, não adiciona pontos
        
        return score
    
    def verificar_tendencia_5min(self, symbol: str) -> bool:
        """
        Verifica se tendência em 5min também é positiva
        Retorna True se últimas 2-3 velas de 5min são verdes E RSI subindo
        """
        try:
            candles_5m = self.binance.get_candles(symbol, '5m', 10)
            if not candles_5m or len(candles_5m) < 3:
                return False
            
            # Conta velas verdes nas últimas 3 de 5min
            velas_verdes_5m = sum(1 for c in candles_5m[-3:] if float(c['close']) > float(c['open']))
            
            # Calcula RSI em 5min
            df_5m = pd.DataFrame(candles_5m)
            df_5m['close'] = df_5m['close'].astype(float)
            df_5m['open'] = df_5m['open'].astype(float)
            
            rsi_5m_atual, rsi_5m_ant = self.calcular_rsi(df_5m)
            
            # Tendência OK se: 2+ velas verdes E RSI subindo
            return velas_verdes_5m >= 2 and rsi_5m_atual > rsi_5m_ant
            
        except Exception as e:
            log(f"⚠️ Erro ao verificar tendência 5min: {e}", 'VERBOSE')
            return False
    
    def detectar_padrao_reversao(self, df: pd.DataFrame) -> dict:
        """
        Detecta padrões de reversão de alta (hammer, engulfing, etc)
        """
        resultado = {
            'hammer': False,
            'bullish_engulfing': False,
            'reversao_fundo': False,
            'forca': 0.0
        }
        
        if df is None or len(df) < 3:
            return resultado
        
        # Última vela
        open_atual = df['open'].iloc[-1]
        close_atual = df['close'].iloc[-1]
        high_atual = df['high'].iloc[-1]
        low_atual = df['low'].iloc[-1]
        
        # Penúltima vela
        open_ant = df['open'].iloc[-2]
        close_ant = df['close'].iloc[-2]
        
        corpo_atual = abs(close_atual - open_atual)
        range_atual = high_atual - low_atual
        
        if range_atual == 0:
            return resultado
        
        # Sombras
        sombra_superior = high_atual - max(open_atual, close_atual)
        sombra_inferior = min(open_atual, close_atual) - low_atual
        
        # 🔨 HAMMER: Sombra inferior longa, corpo pequeno no topo
        if close_atual > open_atual:  # Vela verde
            if sombra_inferior > corpo_atual * 2 and sombra_superior < corpo_atual * 0.3:
                resultado['hammer'] = True
                resultado['forca'] += 0.3
        
        # 📈 BULLISH ENGULFING: Vela verde engole a vermelha anterior
        if close_atual > open_atual and close_ant < open_ant:  # Verde após vermelha
            corpo_ant = abs(close_ant - open_ant)
            if corpo_atual > corpo_ant * 1.2:  # Corpo atual 20% maior
                if close_atual > open_ant and open_atual < close_ant:
                    resultado['bullish_engulfing'] = True
                    resultado['forca'] += 0.4
        
        # 📊 REVERSÃO DE FUNDO: 2+ velas vermelhas seguidas de verde forte
        if len(df) >= 4:
            velas_vermelhas_antes = sum(1 for i in range(-4, -1) if df['close'].iloc[i] < df['open'].iloc[i])
            ultima_verde = close_atual > open_atual
            variacao_atual = (close_atual - open_atual) / open_atual
            
            if velas_vermelhas_antes >= 2 and ultima_verde and variacao_atual > 0.005:
                resultado['reversao_fundo'] = True
                resultado['forca'] += 0.5
        
        return resultado
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📊 INDICADORES PROFISSIONAIS v10.0
    # ═══════════════════════════════════════════════════════════════════════
    
    def calcular_macd(self, df: pd.DataFrame) -> dict:
        """
        MACD - Moving Average Convergence Divergence
        Sinal de compra: MACD cruza acima da Signal Line
        """
        resultado = {
            'macd': 0, 'signal': 0, 'histogram': 0,
            'bullish_crossover': False, 'bearish_crossover': False,
            'above_zero': False, 'histogram_growing': False
        }
        
        if df is None or len(df) < 26:
            return resultado
        
        closes = df['close'].values.astype(float)
        
        # EMAs
        ema12 = pd.Series(closes).ewm(span=12, adjust=False).mean().values
        ema26 = pd.Series(closes).ewm(span=26, adjust=False).mean().values
        
        # MACD Line
        macd_line = ema12 - ema26
        
        # Signal Line (EMA9 do MACD)
        signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values
        
        # Histogram
        histogram = macd_line - signal_line
        
        resultado['macd'] = macd_line[-1]
        resultado['signal'] = signal_line[-1]
        resultado['histogram'] = histogram[-1]
        resultado['above_zero'] = macd_line[-1] > 0
        
        # Bullish crossover: MACD cruza acima da Signal
        if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
            resultado['bullish_crossover'] = True
        
        # Bearish crossover
        if macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
            resultado['bearish_crossover'] = True
        
        # Histogram crescendo
        if len(histogram) >= 3:
            resultado['histogram_growing'] = histogram[-1] > histogram[-2] > histogram[-3]
        
        return resultado
    
    def calcular_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> dict:
        """
        Bollinger Bands - Volatilidade e Mean Reversion
        """
        resultado = {
            'upper': 0, 'middle': 0, 'lower': 0, 'bandwidth': 0,
            'percent_b': 0.5,  # Posição do preço nas bandas (0 = lower, 1 = upper)
            'squeeze': False, 'breakout_up': False, 'breakout_down': False,
            'touch_lower': False, 'touch_upper': False
        }
        
        if df is None or len(df) < period:
            return resultado
        
        closes = df['close'].values.astype(float)
        
        # Média móvel (banda do meio)
        sma = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        
        resultado['middle'] = sma
        resultado['upper'] = sma + (std * std_dev)
        resultado['lower'] = sma - (std * std_dev)
        
        # Bandwidth (volatilidade)
        if sma > 0:
            resultado['bandwidth'] = (resultado['upper'] - resultado['lower']) / sma
        
        # Percent B (posição do preço)
        band_range = resultado['upper'] - resultado['lower']
        if band_range > 0:
            resultado['percent_b'] = (closes[-1] - resultado['lower']) / band_range
        
        # Squeeze: bandas muito apertadas (baixa volatilidade)
        if resultado['bandwidth'] < 0.02:  # < 2%
            resultado['squeeze'] = True
        
        # Touch lower band (potencial compra)
        if closes[-1] <= resultado['lower'] * 1.001:
            resultado['touch_lower'] = True
        
        # Touch upper band
        if closes[-1] >= resultado['upper'] * 0.999:
            resultado['touch_upper'] = True
        
        # Breakout
        if closes[-1] > resultado['upper'] and closes[-2] <= resultado['upper']:
            resultado['breakout_up'] = True
        if closes[-1] < resultado['lower'] and closes[-2] >= resultado['lower']:
            resultado['breakout_down'] = True
        
        return resultado
    
    def calcular_vwap(self, df: pd.DataFrame) -> dict:
        """
        VWAP - Volume Weighted Average Price
        Preço médio ponderado por volume (institucional)
        """
        resultado = {
            'vwap': 0, 'price_vs_vwap': 0,
            'above_vwap': False, 'crossing_up': False, 'crossing_down': False
        }
        
        if df is None or len(df) < 5:
            return resultado
        
        # Typical price = (High + Low + Close) / 3
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        volume = df['volume']
        
        # VWAP = Σ(Typical Price × Volume) / Σ(Volume)
        cumulative_tp_vol = (typical_price * volume).cumsum()
        cumulative_vol = volume.cumsum()
        
        vwap = cumulative_tp_vol / cumulative_vol
        resultado['vwap'] = vwap.iloc[-1]
        
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        
        # Relação preço vs VWAP
        if resultado['vwap'] > 0:
            resultado['price_vs_vwap'] = (current_price - resultado['vwap']) / resultado['vwap']
        
        resultado['above_vwap'] = current_price > resultado['vwap']
        
        # Crossing up (preço cruza acima do VWAP)
        if current_price > resultado['vwap'] and prev_price <= vwap.iloc[-2]:
            resultado['crossing_up'] = True
        
        # Crossing down
        if current_price < resultado['vwap'] and prev_price >= vwap.iloc[-2]:
            resultado['crossing_down'] = True
        
        return resultado
    
    def detectar_rsi_divergence(self, df: pd.DataFrame) -> dict:
        """
        RSI Divergence - Sinal poderoso de reversão
        Bullish: Preço faz lower low, RSI faz higher low
        """
        resultado = {
            'bullish_divergence': False,
            'bearish_divergence': False,
            'strength': 0
        }
        
        if df is None or len(df) < 20:
            return resultado
        
        closes = df['close'].values.astype(float)
        
        # Calcula RSI para todo o período
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        rsi_values = []
        for i in range(14, len(deltas) + 1):
            avg_gain = np.mean(gains[i-14:i])
            avg_loss = np.mean(losses[i-14:i])
            if avg_loss == 0:
                rsi = 100 if avg_gain > 0 else 50
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)
        
        if len(rsi_values) < 5:
            return resultado
        
        # Compara últimos 10 candles para divergência
        price_recent = closes[-5:]
        price_older = closes[-10:-5]
        rsi_recent = rsi_values[-5:]
        rsi_older = rsi_values[-10:-5] if len(rsi_values) >= 10 else rsi_values[:5]
        
        # Bullish divergence: preço lower low, RSI higher low
        if min(price_recent) < min(price_older) and min(rsi_recent) > min(rsi_older):
            resultado['bullish_divergence'] = True
            resultado['strength'] = min(rsi_older) - min(rsi_recent)
        
        # Bearish divergence: preço higher high, RSI lower high
        if max(price_recent) > max(price_older) and max(rsi_recent) < max(rsi_older):
            resultado['bearish_divergence'] = True
            resultado['strength'] = max(rsi_older) - max(rsi_recent)
        
        return resultado
    
    def analisar_moeda(self, symbol: str) -> Optional[dict]:
        """
        ╔════════════════════════════════════════════════════════════════╗
        ║  ANÁLISE v10.0 - EWO DRIVE (CLEAN REBOOT)                      ║
        ╚════════════════════════════════════════════════════════════════╝
        """
        # (Try removido para evitar erro de indentação. Exceções sobem para o loop principal)
        if symbol not in self.klines_cache: return None
        k_data = self.klines_cache[symbol]
        df = k_data['data']
        if df is None or len(df) < 50: return None
        
        # 0. Dados Recentes
        preco = df['close'].iloc[-1]
        
        
        # 0. Dados Recentes
        preco = df['close'].iloc[-1]
        
        # 1. ESTRATÉGIA CALIBRAÇÃO SOLANA
        from strategy_solana import analisar_solana
        
        sinal_compra, score, motivo = analisar_solana(df, symbol=symbol)

        # ── Log 1 linha por moeda (só moedas que passaram filtros rápidos) ──
        if score > 0 or sinal_compra:
            _motivo_curto = (motivo or '').strip()[:60]
            if sinal_compra:
                log_symbol(symbol, f"📊 S:{score:02d} ✅ {_motivo_curto}", 'MINIMAL')
            else:
                log_symbol(symbol, f"📊 S:{score:02d} ❌ {_motivo_curto}", 'MINIMAL')

        # Score mínimo (Dinâmico do Config/AutoAudit)
        if not sinal_compra or score < self.cfg.SCORE_MINIMO:
            return None
             
        # 2. Verificações de Gestão (Capital, Posições Máximas, etc)
        # (Copiadas da lógica anterior para manter segurança)
        
        data_venda_recente = self.ler_ultima_venda_db(symbol)
        agora = agora_brasil()
        if data_venda_recente:
            delta_t = (agora - data_venda_recente).total_seconds()
            if delta_t < self.cfg.COOLDOWN_MOEDA_TEMPO:
                 return None

        # Bloqueio de Capital e Posições (Simplificado)
        with self.posicoes_lock:
             if len(self.posicoes) >= self.cfg.MAX_POSICOES:
                  return None
             if symbol in [p['symbol'] for p in self.posicoes.values()]:
                  return None

        # ✅ SINAL APROVADO
        log_symbol(symbol, f"✅ EWO SIGNAL: {motivo} | Score {score}", 'NORMAL')
        
        # Define modo específico baseado no motivo
        modo_operacao = 'EWO_DRIVE'
        if 'Reversion' in motivo: modo_operacao = 'EWO_REVERSION'
        elif 'Trend' in motivo: modo_operacao = 'EWO_TREND'

        return {
            'symbol': symbol,
            'preco': preco,
            'score': score,
            'rsi': 50, # Dummy para compatibilidade
            'motivos': [motivo],
            'modo': modo_operacao,
            'capital': self.cfg.CAPITAL_POR_OP,
            'take_profit': preco * (1 + self.cfg.TAKE_PROFIT_PCT),
            'stop_loss': preco * (1 - self.cfg.STOP_LOSS_PCT)
        }
    
    def calcular_ichimoku(self, df):
        """
        Calcula Ichimoku Cloud (Tenkan, Kijun, Span A, Span B)
        Retorna (tenkan, kijun, span_a, span_b) da ÚLTIMA vela.
        """
        # Tenkan-sen (Conversion Line): (9-period high + low) / 2
        nine_period_high = df['high'].rolling(window=9).max()
        nine_period_low = df['low'].rolling(window=9).min()
        tenkan_sen = (nine_period_high + nine_period_low) / 2

        # Kijun-sen (Base Line): (26-period high + low) / 2
        twenty_six_period_high = df['high'].rolling(window=26).max()
        twenty_six_period_low = df['low'].rolling(window=26).min()
        kijun_sen = (twenty_six_period_high + twenty_six_period_low) / 2

        # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26) # Plotado 26 períodos a frente

        # Senkou Span B (Leading Span B): (52-period high + low) / 2
        fifty_two_period_high = df['high'].rolling(window=52).max()
        fifty_two_period_low = df['low'].rolling(window=52).min()
        senkou_span_b = ((fifty_two_period_high + fifty_two_period_low) / 2).shift(26) # Plotado 26 períodos a frente

        return tenkan_sen.iloc[-1], kijun_sen.iloc[-1], senkou_span_a.iloc[-1], senkou_span_b.iloc[-1]

    def analisar_moeda_com_stats(self, symbol: str, stats: dict) -> Optional[dict]:
        """
        Análise SIMPLIFICADA (Nostalgia Only).
        Removeu todas as regras antigas. Foca apenas em Dips Estatísticos.
        """
        try:
            # ── PAUSA: Mercado em crash — não abre novas posições ───────
            if getattr(self.cfg, 'PAUSAR_ENTRADAS', False):
                return None

            # ── CIRCUIT BREAKER: Horário e perda diária ──────────────────
            if getattr(self.cfg, 'CIRCUIT_BREAKER_ATIVO', True):
                hora_brasil = agora_brasil().hour
                h_ini = getattr(self.cfg, 'HORARIO_ATIVO_INICIO', 9)
                h_fim = getattr(self.cfg, 'HORARIO_ATIVO_FIM', 23)
                if not (h_ini <= hora_brasil < h_fim):
                    return None  # Fora do horário activo — silencioso

                # Verifica perda acumulada hoje na BD
                try:
                    conn_cb = sqlite3.connect(self.db_path)
                    hoje = agora_brasil().strftime('%Y-%m-%d')
                    row = conn_cb.execute(
                        "SELECT COALESCE(SUM(lucro),0) FROM operacoes WHERE data_venda IS NOT NULL AND date(data_venda) = ?",
                        (hoje,)
                    ).fetchone()
                    conn_cb.close()
                    perda_dia = float(row[0]) if row else 0.0
                    limite = getattr(self.cfg, 'PERDA_MAXIMA_DIA', 5.0)
                    if perda_dia < -limite:
                        # Log apenas uma vez por minuto para não spammar
                        if not hasattr(self, '_cb_log_time') or time.time() - self._cb_log_time > 60:
                            log(f"🛑 CIRCUIT BREAKER: Perda do dia ${perda_dia:.2f} > -${limite:.0f}. Entradas bloqueadas.", 'MINIMAL')
                            self._cb_log_time = time.time()
                        return None
                except Exception:
                    pass  # BD indisponível — continua normalmente

            # Nostalgia precisa de EMA200, então precisamos de histórico longo
            df = self.get_klines(symbol, limit=250) 
            
            # Validação RIGOROSA de Dados (210 candles = 3.5h em 1m)
            # Evita moedas zumbis que têm gaps no histórico.
            if df is None or df.empty or len(df) < 210:
                stats['sem_dados'] += 1
                return None
                
            preco_atual = float(df['close'].iloc[-1])
            
            # Verifica Volume Mínimo Instantâneo
            vol_atual = float(df['volume'].iloc[-1]) * preco_atual 
            ultimos_vols = (df['volume'].tail(3) * preco_atual).values
            
            # Filtro Global de Liquidez (Rigoroso)
            if any(v < 1000 for v in ultimos_vols): 
                 return None
            
            # ==========================================================
            # 🟢 MODO ONDA VERDE (SÓ COMPRA SUBINDO!)
            # ==========================================================
            
            sinal_compra, s_score, s_reason = analisar_solana(df, symbol=symbol)

            # Modo derivado dos sinais reais (aparece na BD e no dashboard)
            r = s_reason or ''
            if   'MACD_CROSS'    in r: s_modo = 'MACD_CROSS'
            elif 'RSI_CROSS50'   in r: s_modo = 'RSI_BREAK50'
            elif 'BREAKOUT_MAX5' in r: s_modo = 'BREAKOUT'
            elif 'SQUEEZE_BREAK' in r: s_modo = 'SQUEEZE'
            elif 'VOL_'          in r: s_modo = 'VOL_SPIKE'
            elif 'IA('           in r: s_modo = 'IA_APPROVED'
            else:                      s_modo = 'MOMENTUM'

            # Log 1 linha por moeda
            if s_score > 0 or sinal_compra:
                _m = r.strip()[:62]
                _icon = '✅' if sinal_compra else '❌'
                log_symbol(symbol, f"📊 S:{s_score:02d} {_icon} {_m}", 'MINIMAL')

            if sinal_compra:
                return {
                    'symbol':         symbol,
                    'preco':          preco_atual,
                    'modo':           s_modo,
                    'capital':        getattr(self.cfg, 'CAPITAL_POR_OP', 75.0),
                    'lucro_alvo':     0.005,
                    'timeout':        600,
                    'score':          s_score,
                    'rsi':            0,
                    'vol_ratio':      1.0,
                    'momentum':       0,
                    'velas_verdes':   0,
                    'motivos':        [r],
                    'motivo_entrada': r,
                }
            
            return None
            
        except Exception as e:
            log(f"Erro analisando {symbol}: {e}", 'VERBOSE')
            return None
        
    
    # -----------------------------------------------------------------------------------
    # FIM DA ANÁLISE (Nostalgia Only)
    # -----------------------------------------------------------------------------------

    
    def executar_compra(self, sinal: dict) -> bool:
        """Executa compra"""
        symbol = sinal['symbol']
        preco = sinal['preco']
        score = sinal.get('score', 0)
        
        # ═══════════════════════════════════════════════════════════════
        # ⚡ VERIFICAÇÕES ATÔMICAS - TUDO DENTRO DO LOCK!
        # ═══════════════════════════════════════════════════════════════
        with self.posicoes_lock:
            # 1. Verifica se já tem posição aberta para esta moeda
            posicoes_mesma_moeda = sum(1 for p in self.posicoes.values() if p['symbol'] == symbol)
            if posicoes_mesma_moeda > 0:
                log_symbol(symbol, f"⏸️ JÁ TEM POSIÇÃO ABERTA - Aguarde finalizar!", 'VERBOSE')
                return False
            
            # 1.1. Verifica TAMBÉM no banco de dados (segurança extra contra duplicidade)
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM operacoes WHERE par = ? AND data_venda IS NULL', (symbol,))
                row = cursor.fetchone()
                db_duplicado = row[0] if row else 0
                
                # Aproveita conexão para pegar capital total
                cursor.execute('SELECT SUM(valor_compra) FROM operacoes WHERE data_venda IS NULL')
                row = cursor.fetchone()
                valor_aberto_db = row[0] if row[0] else 0
                conn.close()
                
                if db_duplicado > 0:
                    log_symbol(symbol, f"⏸️ JÁ TEM POSIÇÃO ABERTA (detectado no DB) - Bloqueando!", 'VERBOSE')
                    return False
            except Exception as e:
                log(f"⚠️ Erro ao consultar DB (duplicidade/capital): {e}", 'MINIMAL')
                valor_aberto_db = 0
            
            # Valor em memória
            valor_aberto_memoria = sum(p['valor'] for p in self.posicoes.values())
            
            # Usa o maior valor entre banco e memória
            valor_aberto = max(valor_aberto_db, valor_aberto_memoria)
            
            # Usa capital do modo
            capital_op = sinal.get('capital', self.cfg.CAPITAL_POR_OP)
            modo = sinal.get('modo', 'SCALPING')
            
            # Verifica se ultrapassaria o limite
            if valor_aberto + capital_op > self.cfg.CAPITAL_MAXIMO:
                log_symbol(symbol, f"⏸️ CAPITAL MÁXIMO atingido: ${valor_aberto:.2f} + ${capital_op:.2f} > ${self.cfg.CAPITAL_MAXIMO} (limite)", 'NORMAL')
                return False
            
            # 3. Verifica número de posições
            num_posicoes = len(self.posicoes)
            if num_posicoes >= self.cfg.MAX_POSICOES:
                log_symbol(symbol, f"⏸️ MAX POSIÇÕES atingido: {num_posicoes}/{self.cfg.MAX_POSICOES}", 'NORMAL')
                return False
            
            # (Removido: stop loss + timeout cuidam de posições presas agora)
        
        # Verifica cooldown (fora do lock - não precisa ser atômico)
        if symbol in self.cooldown_moedas:
            tempo_cooldown = (agora_brasil() - self.cooldown_moedas[symbol]).total_seconds()
            if tempo_cooldown < self.cfg.COOLDOWN_MOEDA_TEMPO:
                log_symbol(symbol, f"⏸️ COOLDOWN: {self.cfg.COOLDOWN_MOEDA_TEMPO - tempo_cooldown:.0f}s restantes", 'VERBOSE')
                return False

        
        log_symbol(symbol, f"", 'MINIMAL')
        log_symbol(symbol, f"═══════════════════════════════════════════════", 'MINIMAL')
        log_symbol(symbol, f"🛒 COMPRANDO >>> {symbol} <<<", 'MINIMAL')
        log_symbol(symbol, f"═══════════════════════════════════════════════", 'MINIMAL')

        # ⚡ 0. VERIFICA SPREAD (CRÍTICO)
        if self.client:
            try:
                book = self.client.get_orderbook_ticker(symbol=symbol)
                bid = float(book['bidPrice'])
                ask = float(book['askPrice'])
                if bid > 0:
                    spread = (ask - bid) / bid
                    if spread > self.cfg.SPREAD_MAX:
                        log_symbol(symbol, f"❌ SPREAD ALTO: {spread*100:.3f}% > {self.cfg.SPREAD_MAX*100:.3f}% | CANCELANDO", 'MINIMAL')
                        self.cooldown_moedas[symbol] = agora_brasil()  # cooldown para não tentar de novo
                        return False
                    log_symbol(symbol, f"✅ Spread: {spread*100:.3f}%", 'VERBOSE')
            except Exception as e:
                log_symbol(symbol, f"⚠️ Erro ao verificar spread: {e}", 'VERBOSE')
        
        # Preço atual (REAL-TIME)
        preco_atual = self.get_preco(symbol, force=True)
        if preco_atual is None:
            log_symbol(symbol, f"❌ Não conseguiu preço atual", 'MINIMAL')
            return False
        
        # ═══════════════════════════════════════════════════════════════
        # 🛡️ VALIDAÇÃO DE PREÇO: Evita comprar se preço mudou muito!
        # ═══════════════════════════════════════════════════════════════
        preco_sinal = sinal.get('preco', preco_atual)
        desvio_pct = (preco_atual - preco_sinal) / preco_sinal if preco_sinal > 0 else 0

        if desvio_pct < -0.003:  # Preço caiu >0.3% desde o sinal → reversal, cancelar
            log_symbol(symbol, f"❌ PREÇO CAIU {desvio_pct*100:.2f}% desde sinal | CANCELADO", 'MINIMAL')
            return False

        if desvio_pct > 0.005:  # Preço subiu >0.5% → movimento já foi, cancelar
            log_symbol(symbol, f"❌ TARDE DEMAIS: subiu {desvio_pct*100:.2f}% | CANCELADO", 'MINIMAL')
            return False

        if desvio_pct > 0:
            log_symbol(symbol, f"📊 SLIP+{desvio_pct*100:.2f}% | OK, entrando", 'NORMAL')

        preco = preco_atual

        valor = self.cfg.CAPITAL_POR_OP
        quantidade = valor / preco
        
        # 🛡️ ZERO STOP LOSS - nunca vende com prejuízo
        stop_loss = 0  # ZERO!
        take_profit = preco * (1 + self.cfg.TAKE_PROFIT_PCT)
        
        ordem_id = f"v7_{symbol}_{int(time.time()*1000)}"
        
        if self.trading_enabled:
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quoteOrderQty=valor
                )
                ordem_id = str(order['orderId'])
                fills = order.get('fills', [])
                if fills:
                    preco = float(fills[0]['price'])
                    quantidade = sum(float(f['qty']) for f in fills)
                log_symbol(symbol, f"✅ Ordem executada: {ordem_id}", 'MINIMAL')
                self.last_buy_time = time.time()  # Atualiza Throttle
            except Exception as e:
                log_symbol(symbol, f"❌ Erro na compra: {e}", 'MINIMAL')
                return False
        else:
            log_symbol(symbol, f"🎮 SIMULAÇÃO: {ordem_id}", 'MINIMAL')
            self.last_buy_time = time.time()  # Atualiza Throttle na simulação também
        
        # Registra posição
        posicao = {
            'symbol':          symbol,
            'preco_compra':    preco,
            'quantidade':      quantidade,
            'valor':           valor,
            'timestamp':       agora_brasil(),
            'stop_loss':       stop_loss,
            'take_profit':     take_profit,
            'ordem_id':        ordem_id,
            'estrategia':      modo,   # MACD_CROSS | RSI_BREAK50 | BREAKOUT | etc.
            'modo':            modo,
            'motivo_entrada':  sinal.get('motivo_entrada', ''),
            'timeout':         sinal.get('timeout', self.cfg.TEMPO_MAXIMO_AGUARDAR),
            'lucro_alvo':      sinal.get('lucro_alvo', self.cfg.LUCRO_MINIMO_PCT),
            'max_preco':       preco,
            'max_lucro':       0,
            'trailing_ativo':  False,
            'rsi_entrada':     sinal.get('rsi', 50),
            'score_entrada':   score
        }
        
        # ⚡ SALVA NO BANCO PRIMEIRO
        if not self._salvar_compra(posicao):
             log_symbol(symbol, f"❌ ERRO CRÍTICO: FALHA AO SALVAR NO DB! Cancelando memória.", 'MINIMAL')
             return False

        with self.posicoes_lock:
            self.posicoes[ordem_id] = posicao
        
        # Atualiza cooldown
        self.cooldown_moedas[symbol] = agora_brasil()
        
        log_symbol(symbol, f"💰 Compra: ${valor:.2f} @ ${preco:.6f} | Modo: {modo}", 'MINIMAL')
        log_symbol(symbol, f"🎯 Target: ${take_profit:.6f} (+{self.cfg.TAKE_PROFIT_PCT*100:.0f}%) | Stop: -0.5%", 'MINIMAL')
        motivo_e = posicao.get('motivo_entrada', '')
        if motivo_e:
            log_symbol(symbol, f"📋 Motivo: {motivo_e[:80]}", 'MINIMAL')
        
        return True
    
    def verificar_posicoes(self):
        """
        VERIFICAÇÃO DE POSIÇÕES v10.0
        Regras de Saída Atualizadas: Stop Técnico, EWO Gain.
        """
        
        with self.posicoes_lock:
            posicoes_copia = dict(self.posicoes)
            num_posicoes = len(posicoes_copia)
        
        if num_posicoes == 0:
            return
        
        for ordem_id, pos in posicoes_copia.items():
            try:
                # ⚡ FAST CHECK (Via WebSocket Cache - Ultra Low Latency)
                preco = self.get_preco(pos['symbol'], force=False)
                if preco is None:
                    log_symbol(pos['symbol'], f"⚠️ Não conseguiu preço!", 'NORMAL')
                    continue
                
                # Calcula lucro
                lucro_info = calcular_lucro(pos['valor'], preco, pos['quantidade'])
                lucro = lucro_info['lucro_bruto']
                pct = (preco - pos['preco_compra']) / pos['preco_compra'] * 100
                tempo = (agora_brasil() - pos['timestamp']).total_seconds()
                
                # Atualiza preço máximo atingido
                max_preco = pos.get('max_preco', pos['preco_compra'])
                max_lucro = pos.get('max_lucro', 0)
                if preco > max_preco:
                    max_preco = preco
                    max_lucro = lucro
                    with self.posicoes_lock:
                        if ordem_id in self.posicoes:
                            self.posicoes[ordem_id]['max_preco'] = preco
                            self.posicoes[ordem_id]['max_lucro'] = lucro
                
                # ═══════════════════════════════════════════════════════════
                # 🎯 GESTÃO DE SAÍDA v5.0 — Dinâmica por Regime
                # ═══════════════════════════════════════════════════════════
                modo = pos.get('modo', 'MOMENTUM')
                tempo_min = tempo / 60

                pct_max = (max_preco - pos['preco_compra']) / pos['preco_compra'] * 100
                drop_from_max = pct_max - pct

                # Parâmetros dinâmicos do regime actual
                target_pct   = self.cfg.TAKE_PROFIT_PCT * 100   # ex: 0.4 ou 0.8
                micro_scalp  = (target_pct <= 0.5)              # BEAR_CRASH mode
                stop_pct     = -0.35 if micro_scalp else -0.50

                # ── 1. 🛑 STOP LOSS (dinâmico) ────────────────────────
                if pct <= stop_pct:
                    log_symbol(pos['symbol'], f"🛑 STOP {pct:.2f}% (limite={stop_pct}%) | Cortando!", 'MINIMAL')
                    self.executar_venda(ordem_id, f"STOP_LOSS_{pct:.2f}%")
                    continue

                # ── 2. 🎯 TAKE PROFIT (lê do cfg — muda por regime) ───
                if pct >= target_pct:
                    log_symbol(pos['symbol'], f"🎯 TARGET {pct:.2f}% (alvo={target_pct:.1f}%) +${lucro:.2f}", 'MINIMAL')
                    self.executar_venda(ordem_id, f"TARGET_{pct:.2f}%")
                    continue

                # ── 3. 🚀 SUPER PUMP (sempre) ─────────────────────────
                if pct >= 2.5:
                    log_symbol(pos['symbol'], f"🚀 PUMP {pct:.2f}% | Lucro excepcional!", 'MINIMAL')
                    self.executar_venda(ordem_id, f"TARGET_{pct:.2f}%")
                    continue

                # ── 4. 📉 TRAILING (adaptado ao target) ───────────────
                trail_trigger = target_pct * 0.60  # 60% do target atingido
                trail_drop    = 0.12 if micro_scalp else 0.20

                if pct_max >= trail_trigger and drop_from_max >= trail_drop:
                    log_symbol(pos['symbol'], f"📉 TRAIL: Max {pct_max:.2f}% → {pct:.2f}% | Protegendo", 'MINIMAL')
                    self.executar_venda(ordem_id, f"TARGET_{pct:.2f}%")
                    continue

                # ── 5. 🤖 IA DE SAÍDA (só em modo normal, não micro-scalp) ─
                if not micro_scalp:
                    ultimo_check_ia = pos.get('ultimo_check_ia_saida', 0)
                    agora_ts = time.time()
                    if agora_ts - ultimo_check_ia >= 30:
                        with self.posicoes_lock:
                            if ordem_id in self.posicoes:
                                self.posicoes[ordem_id]['ultimo_check_ia_saida'] = agora_ts
                        try:
                            from ai_advisor import consultar_saida_ia
                            df_pos = self.get_klines(pos['symbol'], limit=20)
                            if df_pos is not None and len(df_pos) >= 5:
                                closes = df_pos['close']
                                volumes = df_pos['volume']
                                delta = closes.diff()
                                gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
                                loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
                                rsi_live = float(100 - (100 / (1 + gain.iloc[-1] / max(loss.iloc[-1], 0.0001))))
                                rsi_p    = float(100 - (100 / (1 + gain.iloc[-2] / max(loss.iloc[-2], 0.0001))))
                                vol_r    = float(volumes.iloc[-1] / max(volumes.rolling(20).mean().iloc[-1], 1))
                                exp12    = closes.ewm(span=12, adjust=False).mean()
                                exp26    = closes.ewm(span=26, adjust=False).mean()
                                macd_h   = float((exp12-exp26).iloc[-1] - (exp12-exp26).ewm(span=9,adjust=False).mean().iloc[-1])
                                macd_p   = float((exp12-exp26).iloc[-2] - (exp12-exp26).ewm(span=9,adjust=False).mean().iloc[-2])
                            else:
                                rsi_live, rsi_p, vol_r, macd_h, macd_p = 50, 50, 1.0, 0, 0
                            ia = consultar_saida_ia(pos['symbol'], pct, pct_max, tempo_min, rsi_live, rsi_live-rsi_p, vol_r, macd_h, macd_p)
                            if not ia['erro']:
                                log_symbol(pos['symbol'], f"🤖 SAÍDA-IA: {ia['acao']}({ia['confianca']}%) {ia['motivo'][:30]} | {pct:+.2f}%", 'MINIMAL')
                                if ia['acao'] == 'SAIR' and ia['confianca'] >= 82 and (pct > 0.10 or tempo_min >= 5):
                                    self.executar_venda(ordem_id, f"IA_SAIDA_{pct:.2f}%")
                                    continue
                        except Exception:
                            pass

                # ── 6. ⏰ TIME STOP (dinâmico por regime) ─────────────
                timeout_min = self.cfg.TEMPO_MAXIMO_AGUARDAR / 60
                if tempo_min >= timeout_min:
                    log_symbol(pos['symbol'], f"⏰ TIMEOUT {timeout_min:.0f}m: {pct:.2f}% | Rotando capital", 'MINIMAL')
                    self.executar_venda(ordem_id, f"TIMEOUT_LOSS_{pct:.2f}%" if pct < 0 else f"TIMEOUT_{pct:.2f}%")
                    continue

                # Log de monitoramento
                if pct > 0.1:
                    log_symbol(pos['symbol'], f"💰 {pct:+.2f}% (max:{pct_max:+.2f}%) | {tempo_min:.0f}/{timeout_min:.0f}min", 'NORMAL')
                
            except Exception as e:
                log_symbol(pos.get('symbol', '?'), f"❌ Erro ao verificar: {e}", 'VERBOSE')
    
    def executar_venda(self, ordem_id: str, motivo: str) -> float:
        """Executa venda - SEMPRE registra no banco, mesmo em simulação!"""
        with self.posicoes_lock:
            if ordem_id not in self.posicoes:
                log(f"⚠️ Ordem {ordem_id} não encontrada nas posições", 'MINIMAL')
                return 0
            pos = self.posicoes.pop(ordem_id)
        
        preco = self.get_preco(pos['symbol'], force=True)
        if preco is None:
            preco = pos['preco_compra']
        
        lucro_info = calcular_lucro(pos['valor'], preco, pos['quantidade'])
        lucro = lucro_info['lucro_bruto']
        pct = (preco - pos['preco_compra']) / pos['preco_compra'] * 100
        tempo = (agora_brasil() - pos['timestamp']).total_seconds()
        
        # 🛡️ ÚLTIMA VERIFICAÇÃO: Não vende com prejuízo (exceto se for STOP LOSS/TIMEOUT)
        eh_stop_loss = "STOP_LOSS" in motivo or "TIMEOUT" in motivo or "PANIC" in motivo or "TRAIL" in motivo
        if not self.cfg.VENDER_COM_PREJUIZO and lucro < 0 and not eh_stop_loss:
            log_symbol(pos['symbol'], f"🛡️ BLOQUEADO: Tentativa de venda com prejuízo ${lucro:.4f}", 'MINIMAL')
            with self.posicoes_lock:
                self.posicoes[ordem_id] = pos  # Devolve posição
            return 0
        
        # Executa ordem real ou simula
        if self.trading_enabled:
            try:
                order = self.client.create_order(
                    symbol=pos['symbol'],
                    side='SELL',
                    type='MARKET',
                    quantity=pos['quantidade']
                )
                log_symbol(pos['symbol'], f"✅ Venda executada: {order['orderId']}", 'MINIMAL')
            except Exception as e:
                log_symbol(pos['symbol'], f"❌ Erro na venda: {e}", 'MINIMAL')
                with self.posicoes_lock:
                    self.posicoes[ordem_id] = pos
                return 0
        else:
            # ⚡ SIMULAÇÃO - Log em MINIMAL para aparecer!
            log_symbol(pos['symbol'], f"🎮 SIMULAÇÃO VENDA EXECUTADA!", 'MINIMAL')
        
        # Log da venda
        log_symbol(pos['symbol'], f"", 'MINIMAL')
        log_symbol(pos['symbol'], f"💰 VENDA {'SIMULADA' if not self.trading_enabled else 'REALIZADA'}", 'MINIMAL')
        log_symbol(pos['symbol'], f"   💵 Lucro: ${lucro:.4f} ({pct:+.2f}%)", 'MINIMAL')
        log_symbol(pos['symbol'], f"   ⏱️ Tempo: {tempo:.1f}s", 'MINIMAL')
        log_symbol(pos['symbol'], f"   📋 Motivo: {motivo}", 'MINIMAL')
        
        # ⚡ SEMPRE salva no banco - simulação ou real!
        self._salvar_venda(pos, preco, lucro, pct, tempo, motivo)
        
        return lucro
    
    def _salvar_compra(self, posicao: dict) -> bool:
        """Salva compra no banco"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Garante que o ID é string e sem espaços
            ordem_id = str(posicao['ordem_id']).strip()
            
            cursor.execute('SELECT ordem_id_compra FROM operacoes WHERE ordem_id_compra = ?', (ordem_id,))
            if cursor.fetchone():
                conn.close()
                return True
            
            cursor.execute('''
                INSERT INTO operacoes 
                (par, preco_compra, quantidade_compra, valor_compra, data_compra, 
                 ordem_id_compra, preco_alvo, estrategia, modo_operacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                posicao['symbol'],
                posicao['preco_compra'],
                posicao['quantidade'],
                posicao['valor'],
                posicao['timestamp'].isoformat(),
                ordem_id,
                posicao['take_profit'],
                posicao['estrategia'],
                'REAL' if self.trading_enabled else 'SIMULAÇÃO'
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            log(f"❌ Erro ao salvar compra: {e}", 'MINIMAL')
            return False
    
    def _salvar_venda(self, posicao: dict, preco_venda: float, lucro: float, 
                      pct: float, tempo: float, motivo: str):
        """Salva venda no banco"""
        ordem_id = str(posicao['ordem_id']).strip()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            log(f"💾 Tentando salvar VENDA para ordem: {ordem_id}", 'VERBOSE')
            
            # ═══════════════════════════════════════════════════════════════
            # PASSO 1: Atualiza tabela operacoes (CRÍTICO - sempre deve funcionar)
            # ═══════════════════════════════════════════════════════════════
            cursor.execute('''
                UPDATE operacoes SET
                    preco_venda = ?,
                    quantidade_venda = ?,
                    valor_venda = ?,
                    data_venda = ?,
                    ordem_id_venda = ?,
                    preco_venda_real = ?,
                    lucro = ?,
                    percentual_lucro = ?,
                    tempo_operacao = ?
                WHERE ordem_id_compra = ?
            ''', (
                preco_venda,
                posicao['quantidade'],
                preco_venda * posicao['quantidade'],
                agora_brasil().isoformat(),
                f"VENDA_{posicao['ordem_id']}",
                preco_venda,
                lucro,
                pct,
                tempo,
                ordem_id
            ))
            
            if cursor.rowcount == 0:
                log(f"⚠️ AVISO: Venda não encontrou compra {ordem_id}. Criando registro novo...", 'NORMAL')
                # Fallback: Se não achou a compra, CRIA o registro completo
                cursor.execute('''
                    INSERT INTO operacoes 
                    (par, preco_compra, quantidade_compra, valor_compra, data_compra, 
                     ordem_id_compra, preco_alvo, estrategia, modo_operacao,
                     preco_venda, quantidade_venda, valor_venda, data_venda, 
                     ordem_id_venda, preco_venda_real, lucro, percentual_lucro, tempo_operacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    posicao['symbol'],
                    posicao['preco_compra'],
                    posicao['quantidade'],
                    posicao['valor'],
                    posicao['timestamp'].isoformat(),
                    ordem_id,
                    posicao['take_profit'],
                    posicao['estrategia'],
                    'REAL' if self.trading_enabled else 'SIMULAÇÃO',
                    preco_venda,
                    posicao['quantidade'],
                    preco_venda * posicao['quantidade'],
                    agora_brasil().isoformat(),
                    f"VENDA_{posicao['ordem_id']}",
                    preco_venda,
                    lucro,
                    pct,
                    tempo
                ))
            else:
                log(f"   ✅ Tabela 'operacoes' atualizada ({cursor.rowcount} linhas)", 'VERBOSE')
            
            # ⚡ COMMIT IMEDIATO da tabela operacoes - CRÍTICO!
            conn.commit()
            log_symbol(posicao['symbol'], f"💾 Venda salva no banco: ${lucro:.4f} ({pct:+.2f}%)", 'MINIMAL')
            
            # ═══════════════════════════════════════════════════════════════
            # PASSO 2: Tenta inserir em resultados (opcional, não bloqueia)
            # ═══════════════════════════════════════════════════════════════
            try:
                cursor.execute('SELECT id FROM operacoes WHERE ordem_id_compra = ?', (ordem_id,))
                row = cursor.fetchone()
                
                if row:
                    operacao_id = row[0]
                    cursor.execute('''
                        INSERT INTO resultados 
                        (operacao_id, ordem_id_compra, par, preco_compra, preco_venda, quantidade, 
                         lucro, percentual, tempo_operacao, preco_alvo, timestamp_compra, 
                         timestamp_venda, preco_venda_real, modo_operacao, estrategia_usada, motivo_venda)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        operacao_id,
                        ordem_id,
                        posicao['symbol'],
                        posicao['preco_compra'],
                        preco_venda,
                        posicao['quantidade'],
                        lucro,
                        pct,
                        tempo,
                        posicao['take_profit'],
                        posicao['timestamp'].isoformat(),
                        agora_brasil().isoformat(),
                        preco_venda,
                        'REAL' if self.trading_enabled else 'SIMULAÇÃO',
                        posicao['estrategia'],
                        motivo
                    ))
                    conn.commit()
                    log(f"   ✅ Resultado salvo em 'resultados'", 'VERBOSE')
            except Exception as e:
                log(f"⚠️ Erro ao salvar em resultados (venda JÁ foi salva em operacoes): {e}", 'NORMAL')
            
            conn.close()
            
        except Exception as e:
            log(f"❌ Erro ao salvar venda: {e}", 'MINIMAL')
            import traceback
            log(f"   {traceback.format_exc()}", 'VERBOSE')
    
    def get_pares_validos(self) -> List[str]:
        """Obtém lista de pares válidos para trading - Com Cache Persistente"""
        # 0. Verifica Whitelist (CALIBRAÇÃO)
        whitelist = getattr(self.cfg, 'WHITELIST_PAIRS', [])
        if whitelist and len(whitelist) > 0:
            log(f"📋 Usando Whitelist ({len(whitelist)} pares): {whitelist}", 'NORMAL')
            return whitelist
            
        log("🔍 Buscando pares válidos...", 'VERBOSE')
        cache_path = os.path.join(os.path.dirname(__file__), 'status', 'pares_cache.json')
        
        try:
            # 1. Tenta carregar do cache local primeiro se o IP estiver banido ou client for None
            if self.client is None:
                if os.path.exists(cache_path):
                    with open(cache_path, 'r') as f:
                        cache = json.load(f)
                        pares_cached = cache.get('pares', [])
                        if pares_cached:
                            log(f"💾 Client offline - Carregadas {len(pares_cached)} moedas do cache persistente", 'NORMAL')
                            self._salvar_stats(pares_scaneados=len(pares_cached))
                            return pares_cached
                
                log("❌ Client não disponível e cache vazio - usando lista fallback", 'MINIMAL')
                return self._get_pares_fallback()

            # 2. Tenta obter da Binance
            log("   📊 Obtendo tickers 24h da Binance...", 'VERBOSE')
            try:
                tickers = self.client.get_ticker()
            except Exception as e:
                # Se falhar (IP Ban), tenta o cache antes do fallback
                if os.path.exists(cache_path):
                    with open(cache_path, 'r') as f:
                        cache = json.load(f)
                        pares_cached = cache.get('pares', [])
                        if pares_cached:
                            log(f"⚠️ Erro API (BAN?) - Usando {len(pares_cached)} moedas do cache", 'NORMAL')
                            return pares_cached
                raise e

            # 3. Processa tickers COM FILTROS RIGOROSOS
            pares_validos = []
            for ticker in tickers:
                symbol = ticker.get('symbol', '')
                if not symbol.endswith('USDT'): continue
                
                # Exclusões
                excluir = getattr(self.cfg, 'EXCLUIR_MOEDAS', [])
                if symbol in excluir: continue
                
                # Filtro stable/leveraged
                if any(x in symbol for x in ['UPUSDT', 'DOWNUSDT', 'BULLUSDT', 'BEARUSDT', 
                                             'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'EURUSDT',
                                             'GBPUSDT', 'AUDUSDT', 'FDUSDUSDT']):
                    continue
                
                try:
                    # ═══════════════════════════════════════════════════════════
                    # 🔥 FILTROS ESTRITOS - SÓ MOEDAS ATIVAS!
                    # ═══════════════════════════════════════════════════════════
                    volume_24h = float(ticker.get('quoteVolume', 0))
                    price_change_pct = float(ticker.get('priceChangePercent', 0))
                    last_price = float(ticker.get('lastPrice', 0))
                    
                    # Filtro 1: Volume mínimo 24h = $500k (moedas ATIVAS)
                    if volume_24h < 500000:
                        continue
                    
                    # Filtro 2: Preço válido
                    if last_price <= 0:
                        continue
                    
                    # Filtro 3: Tem que ter alguma movimentação (não pode estar parada)
                    # Aceita tanto alta quanto baixa, mas não pode estar zerada
                    if abs(price_change_pct) < 0.1:  # Menos de 0.1% em 24h = moeda morta
                        continue
                    
                    pares_validos.append({
                        'symbol': symbol,
                        'volume': volume_24h,
                        'change': abs(price_change_pct)  # Usa valor absoluto para ordenar
                    })
                except:
                    continue

            # 4. Ordena por volume (maior primeiro) e pega moedas conforme configuração
            limit_pares = getattr(self.cfg, 'PARES_POR_CICLO', 300)
            pares_validos.sort(key=lambda x: x['volume'], reverse=True)
            pares_final = [p['symbol'] for p in pares_validos[:limit_pares]]  # Ampliado!
            
            log(f"🔍 Scaneando TOP {len(pares_final)} moedas mais ativas (Volume 24h > $500k)...", 'MINIMAL')
            
            # 5. Salva no cache para uso futuro (Anti-Ban)
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'w') as f:
                    json.dump({'pares': pares_final, 'timestamp': time.time()}, f)
            except:
                pass

            log(f"✅ {len(pares_final)} moedas ATIVAS selecionadas", 'NORMAL')
            
            # Mostra TOP 30 moedas por volume
            if pares_final:
                log("📋 TOP 30 moedas por volume:", 'NORMAL')
                for i in range(0, min(30, len(pares_final)), 15):
                    chunk = pares_final[i:i+15]
                    log(f"   🔹 {', '.join(chunk)}", 'NORMAL')
            
            # Salva quantidade para o dashboard
            self._salvar_stats(pares_scaneados=len(pares_final))
            return pares_final
            
        except Exception as e:
            log(f"❌ Erro em get_pares_validos: {e}", 'MINIMAL')
            return self._get_pares_fallback()
    
    def _get_pares_fallback(self) -> List[str]:
        """Lista de pares fallback caso a API falhe"""
        log("⚠️ Usando lista de pares fallback", 'MINIMAL')
        pares = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT',
            'DOGEUSDT', 'SOLUSDT', 'DOTUSDT', 'MATICUSDT', 'SHIBUSDT',
            'LTCUSDT', 'AVAXUSDT', 'LINKUSDT', 'ATOMUSDT', 'UNIUSDT',
            'ETCUSDT', 'XLMUSDT', 'NEARUSDT', 'ALGOUSDT', 'FTMUSDT',
            'SANDUSDT', 'MANAUSDT', 'AXSUSDT', 'GALAUSDT', 'APEUSDT',
            'TRXUSDT', 'EOSUSDT', 'AAVEUSDT', 'GRTUSDT', 'FILUSDT'
        ]
        return pares
    
    def check_btc_sentiment(self) -> dict:
        """Verifica se o BTC está seguro para compras"""
        try:
            # Pega última vela de 1h
            klines = self.client.get_klines(symbol='BTCUSDT', interval='1h', limit=1)
            if not klines: return {'safe': True}
            
            k = klines[0]
            open_price = float(k[1])
            close_price = float(k[4])
            percent = (close_price - open_price) / open_price
            
            # Se cair mais de 1.50% em 1h = PERIGO (Crash Real)
            limit_dump = -0.015 
            
            if percent < limit_dump:
                return {'safe': False, 'msg': f"BTC DUMPING: {percent*100:.2f}% (1h)"}
            
            return {'safe': True, 'msg': f"BTC Normal ({percent*100:.2f}%)"}
        except:
            return {'safe': True, 'msg': "Erro BTC"}

    def trading_loop(self):
        """Loop principal de trading"""
        log("", 'MINIMAL')
        log("🚀 INICIANDO LOOP DE TRADING", 'MINIMAL')
        log("═" * 60, 'MINIMAL')
        
        # Busca pares válidos (Já usa o cache interno se estiver banido!)
        pares_validos = self.get_pares_validos()
        
        # Consolida pares para o WebSocket: Escaneamento + Posições Abertas
        with self.posicoes_lock:
            moedas_abertas = list(self.posicoes.keys())
            
        pares_ws = list(set(pares_validos + moedas_abertas))
        
        if not pares_ws:
            log("❌ NENHUM PAR PARA MONITORAR! Verifique conexão com Binance.", 'MINIMAL')
            return
            
        # Inicializa WebSocket Multiplex se disponível
        if self.ws_manager:
            try:
                # Subscreve TODAS as moedas (Scan + Posse)
                log(f"🔌 Iniciando WebSocket Multiplex para {len(pares_ws)} moedas ({len(moedas_abertas)} abertas)...", 'NORMAL')
                self.ws_manager.start_multiplex(pares_ws, interval=self.cfg.TIMEFRAME)
            except Exception as e:
                log(f"⚠️ Erro ao iniciar WebSocket Multiplex: {e}", 'MINIMAL')
        
        log(f"✅ {len(pares_validos)} pares válidos para trading", 'MINIMAL')
        
        ciclo = 0
        ultima_analise = 0
        ultimo_status = 0
        ultima_atualizacao_pares = time.time()
        
        # Estatísticas de bloqueio
        stats_bloqueio = {
            'rsi_caindo': 0,
            'rsi_fora_zona': 0,
            'vela_vermelha': 0,
            'volume_baixo': 0,
            'momentum_negativo': 0,
            'rsi_overbought': 0,
            'score_baixo': 0,
            'confirmacoes': 0,
            'sem_dados': 0,
            'total': 0
        }
        
        while self.running:
            try:
                ciclo += 1
                
                # 🧠 AUTO-ADAPT: Atualiza regime de mercado (BULL/BEAR)
                # Se o mercado mudar, o bot muda a estratégia automaticamente.
                self.update_market_regime()
                
                # Atualiza lista de pares a cada 30 minutos
                if time.time() - ultima_atualizacao_pares > 1800:
                    log("🔄 Atualizando lista de pares...", 'NORMAL')
                    pares_validos = self.get_pares_validos()
                    ultima_atualizacao_pares = time.time()
                    # Salva cache de klines periodicamente (Disco)
                    self._salvar_cache_klines()
                    
                    # Atualiza WebSocket para incluir novas posições ou mudar scan
                    if self.ws_manager:
                        with self.posicoes_lock:
                            moedas_abertas = list(self.posicoes.keys())
                        pares_ws = list(set(pares_validos + moedas_abertas))
                        self.ws_manager.start_multiplex(pares_ws, interval=self.cfg.TIMEFRAME)
                
                # Verifica posições abertas
                self.verificar_posicoes()
                
                # Análise de novos sinais
                if time.time() - ultima_analise >= self.cfg.INTERVALO_ANALISE:
                    ultima_analise = time.time()
                    
                    # 🟢 Tentativa de reconectar WebSocket se estiver offline (Anti-Ban)
                    if self.ws_manager and not self.ws_manager.is_connected():
                        try:
                            self.ws_manager.start_multiplex(pares_validos, interval=self.cfg.TIMEFRAME)
                        except:
                            pass # Silencioso em caso de erro, tentará no próximo ciclo
                    
                    # 🛡️ GLOBAL FILTER: BTC SENTIMENT
                    # Se BTC estiver caindo forte, PAUSA compras!
                    btc_sentiment = self.check_btc_sentiment()
                    if not btc_sentiment['safe']:
                        log(f"⛔ PAUSA: {btc_sentiment['msg']} | Aguardando mercado acalmar...", 'NORMAL')
                        time.sleep(10) # Aguarda um pouco
                        continue # Pula ciclo de compras
                    
                    with self.posicoes_lock:
                        num_posicoes = len(self.posicoes)
                    
                    if num_posicoes < self.cfg.MAX_POSICOES:
                        oportunidades = 0
                        
                        # Analisa em paralelo
                        with ThreadPoolExecutor(max_workers=self.cfg.MAX_WORKERS) as executor:
                            futures = {
                                executor.submit(self.analisar_moeda_com_stats, par, stats_bloqueio): par 
                                for par in pares_validos
                            }
                            
                            for future in as_completed(futures):
                                symbol = futures[future]
                                try:
                                    sinal = future.result()
                                    if sinal:
                                        oportunidades += 1
                                        resultado = self.executar_compra(sinal)
                                        
                                        # Verifica se atingiu máximo
                                        with self.posicoes_lock:
                                            if len(self.posicoes) >= self.cfg.MAX_POSICOES:
                                                log("⚠️ Máximo de posições atingido", 'NORMAL')
                                                break
                                except Exception as e:
                                    log(f"❌ Erro ao analisar {symbol}: {e}", 'VERBOSE')
                        
                        if oportunidades > 0:
                            log(f"📊 Ciclo {ciclo}: {oportunidades} oportunidades | Posições: {num_posicoes}/{self.cfg.MAX_POSICOES}", 'NORMAL')
                        elif ciclo % 10 == 0:  # Log resumido a cada 10 ciclos
                            log(f"🔍 Ciclo {ciclo}: Nenhuma oportunidade | Pos: {num_posicoes}/{self.cfg.MAX_POSICOES}", 'NORMAL')
                            # Mostra estatísticas de bloqueio
                            if stats_bloqueio['total'] > 0:
                                log(f"   📊 Bloqueios: RSI↓={stats_bloqueio['rsi_caindo']} RSI∉zona={stats_bloqueio['rsi_fora_zona']} Vela🔴={stats_bloqueio['vela_vermelha']} Vol↓={stats_bloqueio['volume_baixo']} Mom-={stats_bloqueio['momentum_negativo']}", 'NORMAL')
                    else:
                        if ciclo % 60 == 0:
                            log(f"⏸️ Máximo de posições ({num_posicoes}/{self.cfg.MAX_POSICOES}) - aguardando vendas", 'NORMAL')
                    
                    ultima_analise = time.time()
                
                # Status periódico (a cada 60s)
                if time.time() - ultimo_status > 60:
                    self.print_status()
                    # Reseta estatísticas de bloqueio
                    for key in stats_bloqueio:
                        stats_bloqueio[key] = 0
                    ultimo_status = time.time()
                
                time.sleep(self.cfg.INTERVALO_VERIFICACAO)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                log(f"❌ ERRO no loop: {type(e).__name__}: {e}", 'MINIMAL')
                import traceback
                log(f"   {traceback.format_exc()}", 'VERBOSE')
                time.sleep(5)
        
        self.print_status()
        log("🛑 Bot finalizado", 'MINIMAL')
    
    def print_status(self):
        """Imprime status atual com GRID de posições"""
        with self.posicoes_lock:
            num_posicoes = len(self.posicoes)
            valor_total = sum(p['valor'] for p in self.posicoes.values())
            
            posicoes_info = []
            lucro_total = 0
            for ordem_id, p in self.posicoes.items():
                preco = self.get_preco(p['symbol'])
                if preco:
                    lucro_info = calcular_lucro(p['valor'], preco, p['quantidade'])
                    lucro = lucro_info['lucro_bruto']
                    pct = (preco - p['preco_compra']) / p['preco_compra'] * 100
                    tempo = (agora_brasil() - p['timestamp']).total_seconds() / 60  # em minutos
                    lucro_total += lucro
                    
                    posicoes_info.append({
                        'symbol': p['symbol'],
                        'modo': p.get('modo', 'N/A')[:4],  # Primeiras 4 letras
                        'lucro': lucro,
                        'pct': pct,
                        'tempo': tempo
                    })
        
        log("", 'MINIMAL')
        log("═" * 60, 'MINIMAL')
        log(f"📊 STATUS | {agora_brasil().strftime('%H:%M:%S')}", 'MINIMAL')
        log(f"   💼 Posições: {num_posicoes}/{self.cfg.MAX_POSICOES}", 'MINIMAL')
        log(f"   💰 Capital ativo: ${valor_total:.2f}", 'MINIMAL')
        log(f"   📈 Lucro em aberto: ${lucro_total:.2f}", 'MINIMAL')
        
        # GRID de posições abertas
        if posicoes_info:
            log("", 'MINIMAL')
            log("┌─────────────┬──────┬─────────┬────────┬────────┐", 'MINIMAL')
            log("│   MOEDA     │ MODO │  LUCRO  │   %    │  TEMPO │", 'MINIMAL')
            log("├─────────────┼──────┼─────────┼────────┼────────┤", 'MINIMAL')
            
            for pos in sorted(posicoes_info, key=lambda x: x['pct'], reverse=True):
                emoji = "🟢" if pos['pct'] > 0 else "🔴" if pos['pct'] < 0 else "⚪"
                moeda = pos['symbol'][:11].ljust(11)
                modo = pos['modo'].ljust(4)
                lucro = f"${pos['lucro']:+.2f}".rjust(7)
                pct = f"{pos['pct']:+.2f}%".rjust(6)
                tempo = f"{int(pos['tempo'])}m".rjust(6)
                
                log(f"│ {emoji} {moeda} │ {modo} │ {lucro} │ {pct} │ {tempo} │", 'MINIMAL')
            
            log("└─────────────┴──────┴─────────┴────────┴────────┘", 'MINIMAL')
        
        # GRID de últimas vendas (Ajustado)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Usa COALESCE para garantir que a estratégia de entrada apareça
            cursor.execute('''
                SELECT par, COALESCE(estrategia_usada, modo_operacao, 'N/A'), motivo_venda, percentual_lucro 
                FROM resultados ORDER BY id DESC LIMIT 5
            ''')
            vendas = cursor.fetchall()
            conn.close()
            
            if vendas:
                log("", 'MINIMAL')
                log("┌─────────────┬──────────┬──────────────────────┬────────┐", 'MINIMAL')
                log("│ ULTIMAS 5   │ ENTRADA  │ SAIDA (MOTIVO)       │ RESULT │", 'MINIMAL')
                log("├─────────────┼──────────┼──────────────────────┼────────┤", 'MINIMAL')
                for v in vendas:
                    par, modo, motivo, pct = v
                    pct_val = pct if pct is not None else 0.0
                    emoji = "✅" if pct_val > 0 else "❌"
                    moeda = par[:11].ljust(11)
                    
                    # Formatação mais limpa
                    modo_str = str(modo)[:8].ljust(8)  # Expandido para 8 chars (ex: EXPLOSAO)
                    
                    motivo_raw = str(motivo if motivo else 'MANUAL')
                    motivo_str = motivo_raw.replace('STOP_LOSS', 'STOP').replace('TAKE_PROFIT', 'TAKE')[:20].ljust(20)
                    
                    pct_str = f"{pct_val:+.2f}%".rjust(6)
                    
                    log(f"│ {emoji} {moeda} │ {modo_str} │ {motivo_str} │ {pct_str} │", 'MINIMAL')
                log("└─────────────┴──────────┴──────────────────────┴────────┘", 'MINIMAL')
                
        except Exception as e:
            log(f"⚠️ Erro grid vendas: {e}", 'VERBOSE')
            
        log("═" * 60, 'MINIMAL')
    
    def _staggered_klines_fetch(self, pares: List[str]):
        """Background thread: Busca klines históricos de forma gradual (Anti-Ban)"""
        if not pares: return
        
        log(f"🕯️ Iniciando carga gradual de histórico para {len(pares)} moedas (5/min)...", 'NORMAL')
        for i, symbol in enumerate(pares):
            if not self.running: break
            
            # Só busca se NÃO estiver no cache (para economizar API)
            key = f"{symbol}_{self.cfg.TIMEFRAME}_30"
            if key not in self.klines_cache:
                # get_klines já prioriza WS, então se cair aqui é porque precisa do REST inicial
                self.get_klines(symbol, limit=30)
                # Espera 12s para manter o peso da API baixo (5 moedas/min = ~1200 weight/hora folgado)
                time.sleep(12)
            
            if (i+1) % 10 == 0:
                log(f"🕯️ Carga gradual: {i+1}/{len(pares)} moedas carregadas", 'VERBOSE')
                self._salvar_cache_klines() # Salva progresso no disco
        
        log("✅ Carga gradual de histórico finalizada!", 'NORMAL')

    def start(self):
        """Inicia o bot"""
        if self.running:
            log("⚠️ Bot já está rodando!", 'MINIMAL')
            return
        
        self.running = True
        
        # 1. Thread principal de trading
        thread = threading.Thread(target=self.trading_loop, daemon=True)
        thread.start()
        
        # 2. Thread de carga gradual de histórico (Anti-Ban)
        # Carrega a lista de moedas do cache persistente para saber o que buscar
        pares_para_carregar = []
        cache_path = os.path.join(os.path.dirname(__file__), 'status', 'pares_cache.json')
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache = json.load(f)
                    pares_para_carregar = cache.get('pares', [])
            except:
                pass
        
        if pares_para_carregar:
            threading.Thread(target=self._staggered_klines_fetch, args=(pares_para_carregar,), daemon=True).start()
            
        log("✅ Bot iniciado (Modo Hiper-Confiável)", 'MINIMAL')
    
    def stop(self):
        """Para o bot"""
        self.running = False
        log("🛑 Parando bot...", 'MINIMAL')
        _close_log_file()


# ============================================
# EXECUÇÃO
# ============================================

if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='Bot de Trading - MICRO-SCALPING v8.1 (FILTROS RIGOROSOS + VENDA RÁPIDA)')
    parser.add_argument('--api-key', type=str, help='API Key')
    parser.add_argument('--api-secret', type=str, help='API Secret')
    parser.add_argument('--testnet', action='store_true', help='Usar testnet')
    parser.add_argument('--simulacao', action='store_true', help='Modo simulação')
    parser.add_argument('--real', action='store_true', help='Modo real')
    parser.add_argument('--clear-db', action='store_true', help='Limpar banco')
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv('BINANCE_API_KEY', '')
    api_secret = args.api_secret or os.getenv('BINANCE_API_SECRET', '')
    
    if not api_key or not api_secret:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('BINANCE_API_KEY='):
                        api_key = line.split('=', 1)[1].strip().strip('"\'')
                    elif line.startswith('BINANCE_API_SECRET='):
                        api_secret = line.split('=', 1)[1].strip().strip('"\'')
    
    if not api_key or not api_secret:
        print("❌ Configure BINANCE_API_KEY e BINANCE_API_SECRET")
        sys.exit(1)
    
    if args.clear_db:
        if os.path.exists('trading_data.db'):
            os.remove('trading_data.db')
            print("🗑️ Banco limpo!")
        
        _close_log_file()
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        log_path = os.path.join(log_dir, 'bot.log')
        if os.path.exists(log_path):
            os.remove(log_path)
            print("🗑️ Log limpo!")
    
    modo = None
    if args.simulacao:
        modo = True
    elif args.real:
        modo = False
    
    bot = TradingBot(api_key, api_secret, testnet=args.testnet, modo_simulacao=modo)
    bot.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()
    finally:
        _close_log_file()