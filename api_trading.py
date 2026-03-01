#!/usr/bin/env python3
"""
API de Trading
==============
Servidor Flask que expõe endpoints para bot e dashboard.
Usa trading_core.py para todos os cálculos.

Porta: 5000
"""

from flask import Flask, jsonify, request
import sqlite3
import os
from datetime import datetime, timedelta

# Timezone do Brasil
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

# Importa funções do core
from trading_core import (
    get_binance_client,
    get_preco_atual,
    calcular_lucro,
    formatar_tempo,
    TAXA_BINANCE
)

app = Flask(__name__)

# CORS manual
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# ============================================
# CONFIGURAÇÕES
# ============================================
DB_PATH = 'trading_data.db'


# ============================================
# ENDPOINTS
# ============================================

@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'db_exists': os.path.exists(DB_PATH),
        'taxa_binance': TAXA_BINANCE
    })

@app.route('/api/connection', methods=['GET'])
def connection_status():
    """Retorna tipo de conexão atual (WebSocket/REST)."""
    status_path = os.path.join('status', 'connection.json')
    if not os.path.exists(status_path):
        return jsonify({'type': 'REST', 'connected': False}), 200
    try:
        import json
        with open(status_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preco/<symbol>', methods=['GET'])
def get_preco(symbol):
    """Retorna preço atual de uma moeda"""
    price = get_preco_atual(symbol)
    
    if price is None:
        return jsonify({'error': f'Não foi possível obter preço de {symbol}'}), 404
    
    return jsonify({
        'symbol': symbol.upper(),
        'price': price,
        'timestamp': datetime.now().isoformat()
    })


def _buscar_dados_mercado():
    """Busca dados de 24h de TODOS os pares (preço + volume)"""
    try:
        client = get_binance_client()
        tickers = client.get_ticker()  # Retorna lista com stats de 24h de todos
        dados = {}
        for t in tickers:
            dados[t['symbol']] = {
                'price': float(t['lastPrice']),
                'vol_24h': float(t['quoteVolume'])  # Volume em USDT
            }
        return dados
    except Exception as e:
        print(f"Erro ao buscar dados mercado: {e}")
        return {}


@app.route('/api/posicoes', methods=['GET'])
def get_posicoes():
    """Retorna posições abertas com lucro calculado em tempo real"""
    if not os.path.exists(DB_PATH):
        return jsonify({'error': 'Banco de dados não encontrado'}), 404
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT par, preco_compra, quantidade_compra, valor_compra, 
                   data_compra, ordem_id_compra, preco_alvo, estrategia
            FROM operacoes 
            WHERE data_venda IS NULL
            ORDER BY data_compra DESC
        ''')
        operacoes = cursor.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({'error': f'Erro ao acessar banco: {e}'}), 500
    
    if not operacoes:
        return jsonify({
            'posicoes': [],
            'resumo': {
                'total_posicoes': 0,
                'lucro_potencial': 0,
                'percentual_geral': 0
            },
            'timestamp': datetime.now().isoformat()
        })
    
    # Busca dados de mercado (Preço + Vol 24h)
    dados_mercado = _buscar_dados_mercado()
    client = get_binance_client()  # Para buscar candles individuais
    
    if not dados_mercado:
        return jsonify({'error': 'Não foi possível buscar dados da Binance'}), 500
    
    posicoes = []
    total_lucro = 0
    total_investido = 0
    
    for op in operacoes:
        par, preco_compra, quantidade, valor_compra, data_compra, ordem_id, preco_alvo, estrategia = op
        
        if not par or not preco_compra or not quantidade:
            continue
        
        # Usa dados do mercado
        mercado = dados_mercado.get(par)
        
        if mercado is None:
            continue
            
        preco_atual = mercado['price']
        vol_24h = mercado['vol_24h']
        
        # Busca volume atual (última vela 15m)
        vol_atual = 0
        try:
            klines = client.get_klines(symbol=par, interval='15m', limit=1)
            if klines:
                # kline[5] é o volume em quantidade, kline[7] é quote asset volume (USDT)
                # Vamos usar Quote Volume que é em $
                vol_atual = float(klines[0][7])
        except:
            vol_atual = 0
        
        # Usa valor_compra do banco
        valor_compra_real = float(valor_compra) if valor_compra else float(preco_compra) * float(quantidade)
        
        # Calcula lucro usando função do CORE
        lucro_info = calcular_lucro(valor_compra_real, preco_atual, float(quantidade))
        
        # Calcula tempo aberto (usando timezone do Brasil)
        tempo_segundos = 0
        try:
            # Remove timezone info para comparação simples
            data_str = str(data_compra).replace('Z', '').split('+')[0].split('-03:00')[0]
            dt_compra = datetime.fromisoformat(data_str)
            
            agora = agora_brasil()
            if hasattr(agora, 'tzinfo') and agora.tzinfo:
                agora = agora.replace(tzinfo=None)
            
            tempo_segundos = (agora - dt_compra).total_seconds()
            if tempo_segundos < 0:
                tempo_segundos = 0
        except Exception as e:
            print(f"Erro ao calcular tempo: {e}, data_compra: {data_compra}")
            tempo_segundos = 0
        
        posicao = {
            'par': par,
            'preco_compra': round(float(preco_compra), 10),
            'preco_atual': preco_atual,
            'quantidade': round(float(quantidade), 10),
            'valor_compra': lucro_info['valor_compra'],
            'valor_atual': lucro_info['valor_venda_estimado'],
            'taxa_compra': lucro_info['taxa_compra'],
            'taxa_venda': lucro_info['taxa_venda'],
            'lucro_bruto': lucro_info['lucro_bruto'],
            'lucro_liquido': lucro_info['lucro_liquido'],
            'percentual': lucro_info['percentual'],
            'preco_alvo': float(preco_alvo) if preco_alvo else None,
            'estrategia': estrategia,
            'tempo_segundos': int(tempo_segundos),
            'tempo_str': formatar_tempo(tempo_segundos),
            'vol_24h': vol_24h,
            'vol_atual': vol_atual,
            'data_compra': data_compra,
            'ordem_id': ordem_id
        }
        
        posicoes.append(posicao)
        total_lucro += lucro_info['lucro_liquido']
        total_investido += lucro_info['valor_compra']
    
    return jsonify({
        'posicoes': posicoes,
        'resumo': {
            'total_posicoes': len(posicoes),
            'valor_imobilizado': round(total_investido, 4),
            'lucro_potencial': round(total_lucro, 6),
            'percentual_geral': round((total_lucro / total_investido * 100), 4) if total_investido > 0 else 0
        },
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/vendas', methods=['GET'])
def get_vendas():
    """Retorna histórico de vendas realizadas"""
    if not os.path.exists(DB_PATH):
        return jsonify({'error': 'Banco de dados não encontrado'}), 404
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # ⚡⚡⚡ CRÍTICO: Remove LIMIT para retornar TODAS as vendas (inclui múltiplas operações da mesma moeda) ⚡⚡⚡
        cursor.execute('''
            SELECT o.par, o.preco_compra, o.preco_venda, o.quantidade_compra,
                   o.valor_compra, o.valor_venda, o.data_compra, o.data_venda,
                   r.lucro, r.percentual, o.estrategia, o.lucro as lucro_operacao,
                   o.ordem_id_compra, r.motivo_venda
            FROM operacoes o
            LEFT JOIN resultados r ON o.id = r.operacao_id
            WHERE o.data_venda IS NOT NULL
            ORDER BY o.data_venda DESC
        ''')
        vendas = cursor.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({'error': f'Erro: {e}'}), 500
    
    lista_vendas = []
    total_lucro = 0
    
    for v in vendas:
        # Desempacota incluindo motivo_venda
        if len(v) == 14:
            par, preco_compra, preco_venda, quantidade, valor_compra, valor_venda, data_compra, data_venda, lucro, percentual, estrategia, lucro_operacao, ordem_id_compra, motivo_venda = v
        elif len(v) == 13:
            par, preco_compra, preco_venda, quantidade, valor_compra, valor_venda, data_compra, data_venda, lucro, percentual, estrategia, lucro_operacao, ordem_id_compra = v
            motivo_venda = None
        else:
            # Fallback para compatibilidade com versões antigas
            par, preco_compra, preco_venda, quantidade, valor_compra, valor_venda, data_compra, data_venda, lucro, percentual, estrategia, lucro_operacao = v
            motivo_venda = None
            ordem_id_compra = None
        
        # Calcula duração da operação
        try:
            dt_compra = datetime.fromisoformat(str(data_compra).replace('Z', '+00:00'))
            dt_venda = datetime.fromisoformat(str(data_venda).replace('Z', '+00:00'))
            duracao = (dt_venda.replace(tzinfo=None) - dt_compra.replace(tzinfo=None)).total_seconds()
        except:
            duracao = 0
        
        # ⚡⚡⚡ CRÍTICO: Prioriza lucro da tabela resultados, se não tiver usa da tabela operacoes ⚡⚡⚡
        lucro_valor = round(float(lucro), 6) if lucro is not None else (round(float(lucro_operacao), 6) if lucro_operacao is not None else 0)
        
        # Calcula valores de compra e venda (com fallback se não estiverem no banco)
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
        taxa_compra = round(valor_compra_float * TAXA_BINANCE, 6)
        taxa_venda = round(valor_venda_float * TAXA_BINANCE, 6)
        
        lista_vendas.append({
            'par': par,
            'preco_compra': round(float(preco_compra), 10) if preco_compra else 0,
            'preco_venda': round(float(preco_venda), 10) if preco_venda else 0,
            'quantidade': round(float(quantidade), 10) if quantidade else 0,
            'valor_compra': valor_compra_float,
            'valor_venda': valor_venda_float,
            'taxa_compra': taxa_compra,
            'taxa_venda': taxa_venda,
            'lucro': lucro_valor,
            'percentual': round(float(percentual), 2) if percentual is not None else 0,
            'estrategia': estrategia or 'Normal',
            'motivo_venda': motivo_venda or 'N/A',
            'data_compra': data_compra,
            'data_venda': data_venda,
            'duracao_segundos': int(duracao),
            'duracao_str': formatar_tempo(duracao),
            'ordem_id_compra': ordem_id_compra
        })
        
        # Soma o lucro (pode ser None, então verifica antes)
        if lucro_valor:
            total_lucro += lucro_valor
    
    return jsonify({
        'vendas': lista_vendas,
        'total_vendas': len(lista_vendas),
        'lucro_total': round(total_lucro, 6),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/candles/<symbol>', methods=['GET'])
def get_candles(symbol):
    """Retorna dados de candles (velas) de uma moeda"""
    try:
        limit = int(request.args.get('limit', 50))
        interval = request.args.get('interval', '15m')
        
        client = get_binance_client()
        klines = client.get_klines(
            symbol=symbol.upper(),
            interval=interval,
            limit=limit
        )
        
        candles = []
        for k in klines:
            candles.append({
                'timestamp': int(k[0]),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'close_time': int(k[6]),
                'quote_volume': float(k[7]),
                'trades': int(k[8])
            })
        
        return jsonify({
            'symbol': symbol.upper(),
            'interval': interval,
            'candles': candles,
            'count': len(candles)
        })
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar candles: {e}'}), 500


@app.route('/api/estatisticas', methods=['GET'])
def get_estatisticas():
    """Retorna estatísticas gerais do bot"""
    if not os.path.exists(DB_PATH):
        return jsonify({'error': 'Banco de dados não encontrado'}), 404
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM operacoes')
        total_compras = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM operacoes WHERE data_venda IS NOT NULL')
        total_vendas = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(lucro), 0) FROM resultados')
        lucro_realizado = cursor.fetchone()[0] or 0
        
        # ⚡⚡⚡ CRÍTICO: Calcula lucros positivos (soma apenas lucros > 0) ⚡⚡⚡
        cursor.execute('SELECT COALESCE(SUM(lucro), 0) FROM resultados WHERE lucro > 0')
        lucros_positivos = cursor.fetchone()[0] or 0
        
        # Calcula prejuízo total (soma dos valores absolutos dos lucros negativos)
        cursor.execute('SELECT COALESCE(SUM(ABS(lucro)), 0) FROM resultados WHERE lucro < 0')
        prejuizo_total = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM resultados WHERE lucro > 0')
        ops_lucrativas = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM resultados WHERE lucro <= 0')
        ops_prejuizo = cursor.fetchone()[0]
        
        # Valor imobilizado = soma do valor_compra de todas as posições abertas
        # Calcula de forma mais robusta: soma valor_compra OU preco_compra * quantidade
        cursor.execute('''
            SELECT COALESCE(SUM(
                CASE 
                    WHEN valor_compra IS NOT NULL AND valor_compra > 0 THEN valor_compra
                    ELSE preco_compra * quantidade_compra
                END
            ), 0) 
            FROM operacoes 
            WHERE data_venda IS NULL
        ''')
        valor_imobilizado = cursor.fetchone()[0] or 0
        
        # Se ainda for zero mas há posições abertas, tenta calcular de outra forma
        if valor_imobilizado == 0 and total_compras > total_vendas:
            cursor.execute('''
                SELECT COALESCE(SUM(preco_compra * quantidade_compra), 0) 
                FROM operacoes 
                WHERE data_venda IS NULL
            ''')
            valor_calculado = cursor.fetchone()[0] or 0
            if valor_calculado > 0:
                valor_imobilizado = valor_calculado
        
        # Capital máximo (configuração do bot)
        CAPITAL_MAXIMO = 1000.0
        perc_imobilizado = (valor_imobilizado / CAPITAL_MAXIMO * 100) if CAPITAL_MAXIMO > 0 else 0
        
        cursor.execute('SELECT MIN(data_compra) FROM operacoes')
        primeira_op = cursor.fetchone()[0]
        
        taxa_sucesso = (ops_lucrativas / total_vendas * 100) if total_vendas > 0 else 0
        
        # Calcula tempo rodando (desde primeira operação - para estatísticas)
        tempo_rodando = 0
        if primeira_op:
            try:
                dt_primeira = datetime.fromisoformat(str(primeira_op).replace('Z', '+00:00'))
                tempo_rodando = (agora_brasil() - dt_primeira.replace(tzinfo=None)).total_seconds()
            except:
                tempo_rodando = 0
        
        # Busca data de inicialização ANTES das projeções (para usar no cálculo)
        # Tenta buscar de várias formas para garantir que encontre
        try:
            cursor.execute('SELECT data_inicio, criado_em FROM inicializacao WHERE id = 1 ORDER BY criado_em DESC LIMIT 1')
            row_inicio = cursor.fetchone()
            
            # Se não encontrou, tenta sem WHERE id = 1 (pode ter sido criado sem id)
            if not row_inicio:
                cursor.execute('SELECT data_inicio, criado_em FROM inicializacao ORDER BY criado_em DESC LIMIT 1')
                row_inicio = cursor.fetchone()
        except Exception as e:
            # Tabela pode não existir ainda
            print(f"⚠️ Tabela inicializacao não encontrada ou erro na query: {e}")
            row_inicio = None
        
        tempo_desde_inicio = 0
        data_inicio = None  # Inicializa para uso no JSON
        tempo_desde_inicio_str = '0s'
        
        if row_inicio and row_inicio[0]:
            try:
                data_inicio = row_inicio[0]
                # Parse da data de inicialização
                if isinstance(data_inicio, str):
                    data_str = str(data_inicio).replace('Z', '').split('+')[0].split('.')[0]
                    try:
                        dt_inicio = datetime.fromisoformat(data_str)
                    except:
                        try:
                            dt_inicio = datetime.strptime(data_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            dt_inicio = datetime.strptime(data_str, '%Y-%m-%dT%H:%M:%S')
                else:
                    dt_inicio = data_inicio
                
                if hasattr(dt_inicio, 'tzinfo') and dt_inicio.tzinfo:
                    dt_inicio = dt_inicio.replace(tzinfo=None)
                
                agora = agora_brasil()
                if hasattr(agora, 'tzinfo') and agora.tzinfo:
                    agora = agora.replace(tzinfo=None)
                
                tempo_desde_inicio = (agora - dt_inicio).total_seconds()
                
                # Formata tempo decorrido
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
                # Log do erro para debug
                import traceback
                print(f"⚠️ Erro ao processar data_inicio: {e}")
                print(f"   data_inicio recebida: {row_inicio[0] if row_inicio else 'None'}")
                print(traceback.format_exc())
                # Mantém data_inicio mesmo com erro no parse do tempo
                pass
        
        # ============================================
        # PROJEÇÕES DE LUCRO
        # ============================================
        # Usa tempo desde inicialização para projeções (mais preciso)
        # Se não tiver tempo desde início, usa tempo desde primeira operação
        tempo_para_projecao = tempo_desde_inicio if tempo_desde_inicio > 0 else tempo_rodando
        horas_rodando = tempo_para_projecao / 3600 if tempo_para_projecao > 0 else 0
        
        # Projeções baseadas APENAS no que já foi vendido (lucro realizado)
        # Não inclui posições abertas - apenas operações finalizadas
        lucro_realizado_vendido = lucro_realizado  # Já é a soma de todas as vendas (incluindo negativas)
        
        # Só calcula projeções se tiver tempo suficiente (mínimo 1 hora)
        # Evita extrapolações absurdas com pouco tempo de operação
        TEMPO_MINIMO_PROJECAO = 3600  # 1 hora em segundos
        
        if horas_rodando > 0 and tempo_para_projecao >= TEMPO_MINIMO_PROJECAO:
            # Lucro por hora baseado APENAS no que já foi vendido
            lucro_por_hora = lucro_realizado_vendido / horas_rodando
            
            # Projeções
            projecao_dia = lucro_por_hora * 24
            projecao_semana = lucro_por_hora * 24 * 7
            projecao_mes = lucro_por_hora * 24 * 30
        else:
            # Tempo insuficiente para projeções confiáveis
            lucro_por_hora = 0
            projecao_dia = 0
            projecao_semana = 0
            projecao_mes = 0
        
        # Média de lucro por operação
        lucro_medio_op = lucro_realizado / total_vendas if total_vendas > 0 else 0
        
        # Mediana de lucro por operação
        lucro_mediana_op = 0
        if total_vendas > 0:
            cursor.execute('SELECT lucro FROM resultados ORDER BY lucro')
            lucros = [row[0] for row in cursor.fetchall()]
            if lucros:
                import statistics
                lucro_mediana_op = statistics.median(lucros)
        
        # Operações por hora (usa tempo desde primeira operação, não desde inicialização)
        horas_ops = tempo_rodando / 3600 if tempo_rodando > 0 else 1
        ops_por_hora = total_vendas / horas_ops if horas_ops > 0 else 0
        
        # ⚡⚡⚡ CRÍTICO: Calcula lucro líquido (lucros positivos - prejuízos) ⚡⚡⚡
        lucro_liquido = lucros_positivos - prejuizo_total
        
        # Calcula valor total de operações (para calcular percentuais)
        cursor.execute('SELECT COALESCE(SUM(valor_compra), 0) FROM operacoes')
        valor_total_operacoes = cursor.fetchone()[0] or 0
        
        # Formata tempo desde inicialização (garante que sempre tenha valor)
        if 'tempo_desde_inicio_str' not in locals() or not tempo_desde_inicio_str:
            if tempo_desde_inicio > 0:
                tempo_desde_inicio_str = formatar_tempo(tempo_desde_inicio)
            else:
                tempo_desde_inicio_str = '0s'
        
        conn.close()
        
        res = {
            'total_compras': total_compras,
            'total_vendas': total_vendas,
            'posicoes_abertas': total_compras - total_vendas,
            'lucro_realizado': round(lucro_realizado, 6),
            'lucros_positivos': round(lucros_positivos, 6),
            'prejuizo_total': round(prejuizo_total, 6),
            'lucro_liquido': round(lucro_liquido, 6),
            'ops_lucrativas': ops_lucrativas,
            'ops_prejuizo': ops_prejuizo,
            'taxa_sucesso': round(taxa_sucesso, 2),
            'valor_em_aberto': round(valor_imobilizado, 4),
            'valor_imobilizado': round(valor_imobilizado, 4),
            'perc_imobilizado': round(perc_imobilizado, 2),
            'valor_total_operacoes': round(valor_total_operacoes, 4),
            'tempo_rodando_segundos': int(tempo_rodando),
            'tempo_rodando_str': formatar_tempo(tempo_rodando),
            'timestamp': agora_brasil().isoformat(),
            'lucro_por_hora': round(lucro_por_hora, 4),
            'projecao_dia': round(projecao_dia, 4),
            'projecao_semana': round(projecao_semana, 4),
            'projecao_mes': round(projecao_mes, 4),
            'lucro_medio_op': round(lucro_medio_op, 4),
            'lucro_mediana_op': round(lucro_mediana_op, 4),
            'ops_por_hora': round(ops_por_hora, 2),
            'horas_rodando': round(horas_rodando, 2),
            'data_inicio': data_inicio if data_inicio else None,
            'tempo_desde_inicio': int(tempo_desde_inicio),
            'tempo_desde_inicio_str': tempo_desde_inicio_str,
            'pares_scaneados': 0
        }
        
        try:
            stats_path = os.path.join('status', 'bot_stats.json')
            if os.path.exists(stats_path):
                import json
                with open(stats_path, 'r') as f:
                    bot_stats = json.load(f)
                    res['pares_scaneados'] = bot_stats.get('pares_scaneados', 0)
        except:
            pass
            
        return jsonify(res)
        
    except Exception as e:
        return jsonify({'error': f'Erro: {e}'}), 500


# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 API de Trading (com busca paralela)")
    print("=" * 60)
    print(f"   Banco: {DB_PATH}")
    print(f"   Taxa:  {TAXA_BINANCE * 100}%")
    print()
    print("   Endpoints:")
    print("   - GET /api/health")
    print("   - GET /api/preco/<symbol>")
    print("   - GET /api/posicoes")
    print("   - GET /api/candles/<symbol>?limit=50&interval=15m")
    print("   - GET /api/estatisticas")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
