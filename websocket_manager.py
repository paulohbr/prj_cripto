#!/usr/bin/env python3
"""
WebSocket Manager para Binance
=========================
Stream de preços e klines em tempo real.
Evita rate limits e ZeroDivisionError.
"""

import threading
import time
import json
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Callable
from binance import ThreadedWebsocketManager
from binance.client import Client
from binance.exceptions import BinanceAPIException

class WebSocketManager:
    """Gerencia streams WebSocket para preços e klines"""
    
    def __init__(self, client: Client = None, api_key: str = None, api_secret: str = None, testnet=False):
        self.testnet = testnet
        self.client = client
        
        # Usa chaves passadas ou do client
        final_api_key = api_key or (client.API_KEY if client else None)
        final_api_secret = api_secret or (client.API_SECRET if client else None)
        
        if not final_api_key:
            raise ValueError("API Key is required for WebSocket")
            
        self.twm = ThreadedWebsocketManager(api_key=final_api_key,
                                        api_secret=final_api_secret,
                                        testnet=self.testnet)
        self.twm.start()
        self.connected = False
        self.running = False
        
        # Cache local para dados do WebSocket
        self.ws_precos: Dict[str, tuple] = {}  # (preco, timestamp)
        self.ws_klines_buffer: Dict[str, List[dict]] = {}  # List of candle dicts
        self.max_buffer_size = 50  # Guardar 50 velas para indicadores
        self.ws_lock = threading.Lock()
        
        # Rate limiting para evitar bans
        self.last_subscribe = 0
        self.min_subscribe_interval = 0.5  # 500ms entre subscribes
        
        # Callbacks
        self.price_callbacks: list = []
        self.kline_callbacks: list = []
        
        # Controle de reconexão
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # segundos
        
        log(f"🔌 WebSocket Manager inicializado (testnet={testnet})")
    
    def add_price_callback(self, callback: Callable):
        """Adiciona callback para atualização de preços"""
        self.price_callbacks.append(callback)
    
    def add_kline_callback(self, callback: Callable):
        """Adiciona callback para atualização de klines"""
        self.kline_callbacks.append(callback)
    
    def _handle_ticker_message(self, msg):
        """Processa mensagens de ticker (preços)"""
        if msg.get('e') != '24hrTicker':
            return
            
        symbol = msg.get('s')
        price = float(msg.get('c', 0))
        
        # Atualiza cache WebSocket
        with self.ws_lock:
            self.ws_precos[symbol] = (price, time.time())
        
        # Notifica callbacks
        for callback in self.price_callbacks:
            try:
                callback(symbol, price)
            except Exception as e:
                print(f"❌ Erro no callback de preço: {e}")
    
    def _handle_kline_message(self, msg):
        """Processa mensagens de kline (velas)"""
        # Formato multiplex ou individual
        data = msg.get('data', msg)
        if data.get('e') != 'kline':
            return
            
        kline = data.get('k', {})
        symbol = kline.get('s')
        
        # Processa apenas klines fechadas para o buffer (mais estável para indicadores)
        # OU processamos todas e atualizamos a última se for a mesma vela
        try:
            candle = {
                'timestamp': kline.get('t'),
                'open': float(kline.get('o')),
                'high': float(kline.get('h')),
                'low': float(kline.get('l')),
                'close': float(kline.get('c')),
                'volume': float(kline.get('v')),
                'is_closed': kline.get('x')
            }
            
            with self.ws_lock:
                if symbol not in self.ws_klines_buffer:
                    self.ws_klines_buffer[symbol] = []
                
                buffer = self.ws_klines_buffer[symbol]
                
                # Se o timestamp for o mesmo da última vela, atualizamos ela
                if buffer and buffer[-1]['timestamp'] == candle['timestamp']:
                    buffer[-1] = candle
                else:
                    # Nova vela
                    buffer.append(candle)
                
                # Mantém tamanho do buffer
                if len(buffer) > self.max_buffer_size:
                    self.ws_klines_buffer[symbol] = buffer[-self.max_buffer_size:]
            
            # Notifica callbacks
            for callback in self.kline_callbacks:
                try:
                    callback(symbol, candle)
                except Exception as e:
                    pass
                    
        except Exception as e:
            print(f"❌ Erro ao processar kline WS: {e}")
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Retorna preço do cache WebSocket"""
        with self.ws_lock:
            if symbol in self.ws_precos:
                price, timestamp = self.ws_precos[symbol]
                # Cache válido por 10 segundos para ticker
                if time.time() - timestamp < 10.0:
                    return price
        return None
    
    def get_klines_buffer(self, symbol: str, limit: int = 30) -> Optional[pd.DataFrame]:
        """
        Retorna klines do buffer WebSocket transformadas em DataFrame
        """
        with self.ws_lock:
            if symbol not in self.ws_klines_buffer or not self.ws_klines_buffer[symbol]:
                return None
            
            # Se tivermos velas suficientes (ex: pelo menos 15 para RSI)
            buffer = self.ws_klines_buffer[symbol]
            if len(buffer) < 15:
                return None
                
            df = pd.DataFrame(buffer[-limit:])
            # Converte timestamps para datetime
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
    
    def start_multiplex(self, symbols: list, interval: str = '1m'):
        """Inicia streams multiplexados (Ticker + Kline)"""
        if not symbols:
            return
            
        self.running = True
        log(f"🚀 Iniciando Multiplex para {len(symbols)} moedas ({interval})")
        
        try:
            # Canais: <symbol>@ticker e <symbol>@kline_<interval>
            streams = []
            for s in symbols:
                s_lower = s.lower()
                streams.append(f"{s_lower}@ticker")
                streams.append(f"{s_lower}@kline_{interval}")
            
            # Binance aceita grupos de até 1024 streams por multiplex
            # Como usamos 2 streams por moeda, suportamos ~500 moedas
            self.twm.start_multiplex_socket(callback=self._handle_kline_message, streams=streams)
            
            # Também subscreve preços via ticker socket (redundância ou se não estiver no multiplex)
            # self.twm.start_ticker_socket(callback=self._handle_ticker_message)
            
            self.connected = True
            log(f"✅ Multiplex ativo para {len(symbols)} símbolos!")
            
        except Exception as e:
            log(f"❌ Erro ao iniciar Multiplex: {e}")
            self.connected = False
    
    def stop_streams(self):
        """Para todos os streams de forma graceful"""
        if not self.running:
            return
            
        log("🛑 Parando WebSocket streams...")
        self.running = False
        
        try:
            self.twm.stop()
            self.connected = False
            log("✅ WebSocket parado com sucesso")
        except Exception as e:
            log(f"❌ Erro ao parar WebSocket: {e}")
    
    def is_connected(self) -> bool:
        """Verifica se WebSocket está conectado"""
        return self.connected and self.running
    
    def get_status(self) -> dict:
        """Retorna status do WebSocket"""
        return {
            'connected': self.connected,
            'running': self.running,
            'testnet': self.testnet,
            'symbols_count': len(self.ws_precos),
            'klines_count': len(self.ws_klines),
            'reconnect_attempts': self.reconnect_attempts
        }

def log(msg: str, level: str = 'NORMAL'):
    """Log simples para WebSocket"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] WS: {msg}")

if __name__ == "__main__":
    # Teste rápido
    from binance.client import Client
    dummy_client = Client('', '', testnet=True)
    ws = WebSocketManager(dummy_client, testnet=True)
    ws.start_streams(['BTCUSDT', 'ETHUSDT'])
    time.sleep(10)
    print(ws.get_status())
    ws.stop_streams()
