#!/usr/bin/env python3
"""
Criador de Banco de Dados - Trading Bot
========================================
Cria o banco trading_data.db com todas as tabelas necessárias
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = 'trading_data.db'

def criar_banco():
    """Cria o banco de dados com todas as tabelas"""
    
    print("=" * 60)
    print("📦 CRIANDO BANCO DE DADOS")
    print("=" * 60)
    
    # Remove banco antigo se existir
    if os.path.exists(DB_PATH):
        print(f"   🗑️ Removendo banco antigo...")
        os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ============================================
    # TABELA: operacoes (principal)
    # ============================================
    print("   📋 Criando tabela 'operacoes'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT NOT NULL,
            preco_compra REAL NOT NULL,
            quantidade_compra REAL NOT NULL,
            valor_compra REAL NOT NULL,
            data_compra DATETIME NOT NULL,
            ordem_id_compra TEXT NOT NULL,
            preco_alvo REAL,
            estrategia TEXT,
            preco_venda REAL,
            quantidade_venda REAL,
            valor_venda REAL,
            data_venda DATETIME,
            ordem_id_venda TEXT,
            preco_venda_real REAL,
            lucro REAL,
            percentual_lucro REAL,
            tempo_operacao REAL,
            modo_operacao TEXT,
            UNIQUE(ordem_id_compra)
        )
    ''')
    
    # Índices para operacoes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_operacoes_par_venda 
        ON operacoes(par, data_venda)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_operacoes_ordem_compra 
        ON operacoes(ordem_id_compra)
    ''')
    
    # ============================================
    # TABELA: transacoes (compatibilidade)
    # ============================================
    print("   📋 Criando tabela 'transacoes'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT NOT NULL,
            tipo TEXT NOT NULL,
            preco REAL NOT NULL,
            quantidade REAL NOT NULL,
            valor_total REAL NOT NULL,
            timestamp DATETIME NOT NULL,
            ordem_id TEXT,
            preco_alvo REAL
        )
    ''')
    
    # ============================================
    # TABELA: resultados
    # ============================================
    print("   📋 Criando tabela 'resultados'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operacao_id INTEGER,
            par TEXT NOT NULL,
            preco_compra REAL,
            preco_venda REAL,
            quantidade REAL,
            lucro REAL NOT NULL,
            percentual REAL,
            percentual_lucro REAL,
            tempo_operacao REAL,
            preco_alvo REAL,
            timestamp_compra DATETIME,
            timestamp_venda DATETIME,
            preco_alvo_previsto REAL,
            preco_venda_real REAL,
            diferenca_preco REAL,
            modo_operacao TEXT,
            precisao_previsao REAL,
            estrategia_usada TEXT,
            data DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ============================================
    # TABELA: estatisticas
    # ============================================
    print("   📋 Criando tabela 'estatisticas'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estatisticas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            preco_atual REAL NOT NULL,
            previsao REAL,
            preco_alvo REAL,
            sinal TEXT,
            confianca REAL,
            quantidade REAL,
            valor_investido REAL,
            lucro_esperado REAL,
            percentual_esperado REAL,
            features TEXT,
            estrategia TEXT
        )
    ''')
    
    # ============================================
    # TABELA: configuracao
    # ============================================
    print("   📋 Criando tabela 'configuracao'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracao (
            chave TEXT PRIMARY KEY,
            valor REAL NOT NULL,
            descricao TEXT,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insere configurações padrão
    print("   ⚙️ Inserindo configurações padrão...")
    configuracoes = [
        ('capital_maximo_imobilizado', 500.0, 'Capital máximo que pode estar investido simultaneamente'),
        ('max_posicoes_abertas', 8, 'Número máximo de posições abertas'),
        ('max_posicoes_por_par', 1, 'Máximo de posições simultâneas no mesmo par'),
        ('valor_minimo', 30.0, 'Valor mínimo de investimento por operação'),
        ('valor_medio', 40.0, 'Valor médio de investimento por operação'),
        ('valor_maximo', 60.0, 'Valor máximo de investimento por operação'),
        ('meta_lucro', 0.30, 'Meta de lucro por operação em dólares'),
        ('lucro_minimo_garantido', 0.10, 'Lucro mínimo em dólares para vender'),
        ('timeout_operacao', 600, 'Timeout em segundos para atingir meta (10 min)'),
        ('timeout_prejuizo', 300, 'Timeout em segundos para posição com prejuízo (5 min)'),
        ('confianca_minima_base', 0.65, 'Confiança mínima base para comprar (65%)'),
        ('score_venda_rapida_minimo', 0.50, 'Score mínimo de venda rápida (50%)'),
        ('stop_loss_percentual', 0.005, 'Stop loss percentual (-0.5%)'),
        ('take_profit_percentual', 0.008, 'Take profit percentual (+0.8%)'),
        ('volume_minimo_24h', 5000000, 'Volume mínimo 24h em USDT'),
        ('rsi_minimo', 35, 'RSI mínimo para comprar'),
        ('rsi_maximo', 65, 'RSI máximo para comprar'),
        ('momentum_minimo', 0.003, 'Momentum mínimo (+0.3%)'),
        ('volume_ratio_minimo', 1.2, 'Volume ratio mínimo (1.2x)'),
        ('velas_verdes_minimo', 2, 'Velas verdes mínimo'),
        ('timeframe', 5, 'Timeframe em minutos'),
    ]
    
    cursor.executemany('''
        INSERT OR REPLACE INTO configuracao (chave, valor, descricao) VALUES (?, ?, ?)
    ''', configuracoes)
    
    # ============================================
    # TABELA: bot_status (para API)
    # ============================================
    print("   📋 Criando tabela 'bot_status'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            status TEXT DEFAULT 'stopped',
            inicio DATETIME,
            ultima_atividade DATETIME,
            lucro_sessao REAL DEFAULT 0,
            operacoes_sessao INTEGER DEFAULT 0,
            wins_sessao INTEGER DEFAULT 0,
            losses_sessao INTEGER DEFAULT 0
        )
    ''')
    
    # Insere status inicial
    cursor.execute('''
        INSERT OR REPLACE INTO bot_status (id, status, inicio, ultima_atividade)
        VALUES (1, 'stopped', NULL, NULL)
    ''')
    
    conn.commit()
    conn.close()
    
    print("")
    print("=" * 60)
    print("✅ BANCO DE DADOS CRIADO COM SUCESSO!")
    print("=" * 60)
    print(f"   📁 Arquivo: {os.path.abspath(DB_PATH)}")
    print(f"   📊 Tabelas: operacoes, transacoes, resultados, estatisticas, configuracao, bot_status")
    print("")


if __name__ == '__main__':
    criar_banco()
