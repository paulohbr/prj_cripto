#!/usr/bin/env python3
"""
Script para verificar posições que deveriam ter sido vendidas
"""
import sqlite3
from datetime import datetime, timedelta

DB_PATH = 'trading_data.db'

def verificar_vendas_pendentes():
    """Verifica posições abertas que deveriam ter sido vendidas"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Busca posições abertas
    cursor.execute('''
        SELECT par, preco_compra, quantidade_compra, valor_compra, 
               data_compra, ordem_id_compra, preco_alvo, estrategia
        FROM operacoes
        WHERE data_venda IS NULL
        ORDER BY data_compra ASC
    ''')
    
    posicoes = cursor.fetchall()
    conn.close()
    
    if not posicoes:
        print("📭 Nenhuma posição aberta encontrada.")
        return
    
    print(f"\n{'='*90}")
    print(f"🔍 ANÁLISE DE VENDAS PENDENTES ({len(posicoes)} posições abertas)")
    print(f"{'='*90}\n")
    
    # Simula verificação de cada posição
    from binance.client import Client
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.getenv('BINANCE_API_KEY', '')
    api_secret = os.getenv('BINANCE_API_SECRET', '')
    
    if api_key and api_secret:
        client = Client(api_key, api_secret)
    else:
        client = Client()
    
    vendas_pendentes = []
    
    for pos in posicoes:
        par, preco_compra, qty, valor_compra, data_compra, ordem_id, preco_alvo, estrategia = pos
        
        try:
            # Busca preço atual
            ticker = client.get_symbol_ticker(symbol=par)
            preco_atual = float(ticker['price'])
            
            # Calcula lucro
            valor_atual = preco_atual * qty
            taxa_compra = valor_compra * 0.001
            taxa_venda = valor_atual * 0.001
            lucro = valor_atual - valor_compra - taxa_compra - taxa_venda
            percentual = ((preco_atual - preco_compra) / preco_compra) * 100
            
            # Calcula tempo aberto
            try:
                dt_compra = datetime.fromisoformat(data_compra.replace('Z', '+00:00'))
                tempo_segundos = (datetime.now() - dt_compra.replace(tzinfo=None)).total_seconds()
                tempo_minutos = tempo_segundos / 60
            except:
                tempo_segundos = 0
                tempo_minutos = 0
            
            # Verifica regras de venda
            deveria_vender = False
            motivo = []
            
            # REGRA 1: Lucro >= $1.00
            if lucro >= 1.00:
                deveria_vender = True
                motivo.append("💰💰💰 Lucro >= $1.00")
            
            # REGRA 2: Preço >= Compra + Lucro > 0
            elif preco_atual >= preco_compra and lucro > 0:
                deveria_vender = True
                motivo.append("✅ Preço >= Compra + Lucro > 0")
            
            # REGRA 3: Preço >= Alvo
            elif preco_alvo and preco_atual >= preco_alvo and lucro >= 0:
                deveria_vender = True
                motivo.append("🎯 Preço >= Alvo")
            
            # REGRA 4: 1 minuto+ com lucro >= $0.001
            elif tempo_segundos >= 60 and lucro >= 0.001:
                deveria_vender = True
                motivo.append(f"⏰ 1min+ com lucro >= $0.001")
            
            # REGRA 5: 5 minutos+ mesmo com prejuízo até -$0.30
            elif tempo_segundos >= 300 and lucro >= -0.30:
                deveria_vender = True
                motivo.append(f"⏰ 5min+ (timeout)")
            
            # REGRA 6: 8 minutos+ com prejuízo
            elif tempo_segundos >= 480 and lucro < 0:
                deveria_vender = True
                motivo.append(f"🛑 8min+ com prejuízo (corte)")
            
            # REGRA 7: 10 minutos+ qualquer situação
            elif tempo_segundos >= 600:
                deveria_vender = True
                motivo.append(f"⏰ 10min+ (timeout absoluto)")
            
            # REGRA 8: Stop Loss -1.5%
            elif percentual <= -1.5:
                deveria_vender = True
                motivo.append(f"🛑 Stop Loss -1.5%")
            
            # REGRA 9: Scalping - Lucro >= $0.01 em <5s
            elif lucro >= 0.01 and tempo_segundos < 5:
                deveria_vender = True
                motivo.append(f"⚡ Scalping instantâneo")
            
            # REGRA 10: Lucro >= $0.05 em <2min
            elif lucro >= 0.05 and tempo_segundos < 120:
                deveria_vender = True
                motivo.append(f"💰 Lucro >= $0.05 em <2min")
            
            # REGRA 11: Lucro >= $0.25 (meta)
            elif lucro >= 0.25:
                deveria_vender = True
                motivo.append(f"🎯 Meta $0.25 atingida")
            
            # REGRA 12: Lucro >= $0.03 após 1min
            elif tempo_segundos >= 60 and lucro >= 0.03:
                deveria_vender = True
                motivo.append(f"🔄 1min+ com lucro >= $0.03")
            
            # REGRA 13: Lucro >= $0.01 após 2min
            elif tempo_segundos >= 120 and lucro >= 0.01:
                deveria_vender = True
                motivo.append(f"🔄 2min+ com lucro >= $0.01")
            
            if deveria_vender:
                vendas_pendentes.append({
                    'par': par,
                    'preco_compra': preco_compra,
                    'preco_atual': preco_atual,
                    'lucro': lucro,
                    'percentual': percentual,
                    'tempo': tempo_segundos,
                    'tempo_str': f"{int(tempo_minutos)}min {int(tempo_segundos % 60)}s",
                    'motivo': ' | '.join(motivo)
                })
        
        except Exception as e:
            print(f"⚠️  Erro ao verificar {par}: {e}")
            continue
    
    if vendas_pendentes:
        print(f"❌ {len(vendas_pendentes)} POSIÇÕES QUE DEVERIAM TER SIDO VENDIDAS:\n")
        print(f"{'Par':<12} {'Compra':<12} {'Atual':<12} {'Lucro':<12} {'%':<10} {'Tempo':<15} {'Motivo'}")
        print("-" * 90)
        
        for v in vendas_pendentes:
            cor = "🟢" if v['lucro'] > 0 else "🔴"
            print(f"{v['par']:<12} ${v['preco_compra']:<11.6f} ${v['preco_atual']:<11.6f} "
                  f"{cor} ${v['lucro']:<10.4f} {v['percentual']:+.2f}% {v['tempo_str']:<15} {v['motivo']}")
        
        print(f"\n{'='*90}")
        print(f"⚠️  ATENÇÃO: {len(vendas_pendentes)} posições atendem critérios de venda mas ainda estão abertas!")
        print(f"💡 Verifique se o bot está rodando: systemctl status trading-bot")
        print(f"💡 Verifique os logs: tail -f logs/bot.log | grep VENDA")
    else:
        print("✅ Todas as posições estão dentro dos critérios (não deveriam ser vendidas ainda)")
    
    print()

if __name__ == '__main__':
    try:
        verificar_vendas_pendentes()
    except FileNotFoundError:
        print(f"❌ Banco de dados não encontrado: {DB_PATH}")
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()






