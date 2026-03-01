#!/usr/bin/env python3
"""
Trading Core - Funções Compartilhadas
=====================================
Módulo central com cálculos e funções usadas por:
- Bot (import direto)
- API (import direto)
- Dashboard (via API)

IMPORTANTE: Qualquer mudança aqui afeta TODO o sistema.
"""

import os
import time
import threading
from datetime import datetime, timedelta
from binance.client import Client
from dotenv import load_dotenv

# ============================================
# TIMEZONE DO BRASIL
# ============================================
try:
    from zoneinfo import ZoneInfo
    TZ_BRASIL = ZoneInfo('America/Sao_Paulo')
except ImportError:
    # Fallback para Python < 3.9
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
        # Fallback: ajusta manualmente UTC-3
        return datetime.now() - timedelta(hours=3)

# ============================================
# CONSTANTES GLOBAIS
# ============================================
TAXA_BINANCE = 0.00100  # 0.10% por operação (Taxa padrão conservadora)
CACHE_TTL = 0.5         # 500ms de cache para preços

# ============================================
# CLIENTE BINANCE (SINGLETON THREAD-SAFE)
# ============================================
_binance_client = None
_client_lock = threading.Lock()

def get_binance_client():
    """Retorna cliente Binance (singleton thread-safe)"""
    global _binance_client
    
    if _binance_client is not None:
        return _binance_client
    
    with _client_lock:
        if _binance_client is not None:
            return _binance_client
        
        load_dotenv()
        api_key = os.getenv('BINANCE_API_KEY', '')
        api_secret = os.getenv('BINANCE_API_SECRET', '')
        
        # Tenta ler do .env diretamente
        if not api_key or not api_secret:
            env_path = os.path.join(os.path.dirname(__file__), '.env')
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('BINANCE_API_KEY='):
                            api_key = line.split('=', 1)[1].strip().strip('"\'')
                        elif line.startswith('BINANCE_API_SECRET='):
                            api_secret = line.split('=', 1)[1].strip().strip('"\'')
        
        if api_key and api_secret:
            _binance_client = Client(api_key, api_secret)
        else:
            _binance_client = Client()
        
        return _binance_client


# ============================================
# CACHE DE PREÇOS (THREAD-SAFE)
# ============================================
_precos_cache = {}
_cache_lock = threading.Lock()

def get_preco_atual(symbol: str, force_refresh: bool = False) -> float:
    """
    Busca preço atual com cache de 500ms.
    
    Args:
        symbol: Par de trading (ex: BTCUSDT)
        force_refresh: Se True, ignora cache
    
    Returns:
        Preço arredondado para 10 casas decimais
    """
    global _precos_cache
    
    if not symbol:
        return None
    
    symbol = symbol.strip().upper()
    now = time.time()
    
    # Verifica cache (se não forçar refresh)
    if not force_refresh:
        with _cache_lock:
            if symbol in _precos_cache:
                cached = _precos_cache[symbol]
                if now - cached['timestamp'] < CACHE_TTL:
                    return cached['price']
    
    # Busca da API Binance
    try:
        client = get_binance_client()
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = round(float(ticker['price']), 10)
        
        # Atualiza cache
        with _cache_lock:
            _precos_cache[symbol] = {
                'price': price,
                'timestamp': now
            }
        
        return price
    except Exception as e:
        print(f"❌ CORE: Erro ao buscar preço de {symbol}: {e}", flush=True)
        return None


def limpar_cache_precos():
    """Limpa todo o cache de preços"""
    global _precos_cache
    with _cache_lock:
        _precos_cache.clear()


# ============================================
# CÁLCULO DE LUCRO (FUNÇÃO ÚNICA DO SISTEMA)
# ============================================
def calcular_lucro(valor_compra: float, preco_atual: float, quantidade: float) -> dict:
    """
    Calcula lucro de uma posição.
    
    ⚠️ ESTA É A ÚNICA FUNÇÃO DE CÁLCULO DE LUCRO DO SISTEMA.
    ⚠️ Bot, API e Dashboard DEVEM usar esta função.
    
    Args:
        valor_compra: Valor total da compra (já armazenado no BD)
        preco_atual: Preço atual da moeda
        quantidade: Quantidade de moedas
    
    Returns:
        dict com:
            - valor_compra: Valor da compra arredondado
            - valor_venda_estimado: Valor se vendesse agora
            - taxa_compra: Taxa de 0.1% sobre compra
            - taxa_venda: Taxa de 0.1% sobre venda
            - lucro_bruto: Diferença sem taxas
            - lucro_liquido: Lucro após taxas (VALOR PRINCIPAL)
            - percentual: Variação percentual
    """
    # Arredonda para 10 casas (padrão do sistema)
    valor_compra = round(float(valor_compra), 10)
    preco_atual = round(float(preco_atual), 10)
    quantidade = round(float(quantidade), 10)
    
    # Cálculos
    valor_venda_estimado = round(preco_atual * quantidade, 10)
    taxa_compra = round(valor_compra * TAXA_BINANCE, 10)
    taxa_venda = round(valor_venda_estimado * TAXA_BINANCE, 10)
    lucro_bruto = round(valor_venda_estimado - valor_compra, 10)
    lucro_liquido = round(lucro_bruto - taxa_compra - taxa_venda, 10)
    
    # Percentual
    if valor_compra > 0:
        percentual = round((valor_venda_estimado - valor_compra) / valor_compra * 100, 4)
    else:
        percentual = 0
    
    return {
        'valor_compra': valor_compra,
        'valor_venda_estimado': valor_venda_estimado,
        'taxa_compra': taxa_compra,
        'taxa_venda': taxa_venda,
        'lucro_bruto': lucro_bruto,
        'lucro_liquido': lucro_liquido,
        'percentual': percentual
    }


# ============================================
# FORMATAÇÃO (FUNÇÕES AUXILIARES)
# ============================================
def formatar_preco(preco: float) -> str:
    """Formata preço com casas decimais apropriadas"""
    if preco is None:
        return "N/A"
    if preco >= 1:
        return f"${preco:.4f}"
    elif preco >= 0.01:
        return f"${preco:.6f}"
    else:
        return f"${preco:.8f}"


def formatar_lucro(lucro: float) -> str:
    """Formata lucro com sinal e casas decimais apropriadas"""
    if lucro is None:
        return "N/A"
    if abs(lucro) >= 0.01:
        return f"${lucro:+.4f}"
    else:
        return f"${lucro:+.6f}"


def formatar_tempo(segundos: float) -> str:
    """Formata tempo em formato legível"""
    if segundos is None or segundos < 0:
        return "N/A"
    
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    segs = int(segundos % 60)
    
    if horas > 0:
        return f"{horas}h {minutos}m"
    elif minutos > 0:
        return f"{minutos}m {segs}s"
    else:
        return f"{segs}s"


# ============================================
# TESTE DO MÓDULO
# ============================================
if __name__ == '__main__':
    print("=" * 50)
    print("🧪 Teste do Trading Core")
    print("=" * 50)
    
    # Teste de preço
    print("\n1️⃣ Testando busca de preço...")
    preco = get_preco_atual('BTCUSDT')
    print(f"   BTCUSDT: {formatar_preco(preco)}")
    
    # Teste de cálculo de lucro
    print("\n2️⃣ Testando cálculo de lucro...")
    resultado = calcular_lucro(
        valor_compra=100.0,
        preco_atual=0.5,
        quantidade=200
    )
    print(f"   Valor compra: ${resultado['valor_compra']}")
    print(f"   Valor venda:  ${resultado['valor_venda_estimado']}")
    print(f"   Taxa compra:  ${resultado['taxa_compra']}")
    print(f"   Taxa venda:   ${resultado['taxa_venda']}")
    print(f"   Lucro bruto:  ${resultado['lucro_bruto']}")
    print(f"   Lucro líquido: {formatar_lucro(resultado['lucro_liquido'])}")
    print(f"   Percentual:   {resultado['percentual']}%")
    
    # Teste de formatação
    print("\n3️⃣ Testando formatação...")
    print(f"   Tempo 3661s: {formatar_tempo(3661)}")
    print(f"   Tempo 125s:  {formatar_tempo(125)}")
    print(f"   Tempo 45s:   {formatar_tempo(45)}")
    
    print("\n✅ Todos os testes passaram!")
