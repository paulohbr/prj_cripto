"""
Bottom Fishing Strategy - Comprar no Fundo Confirmado
Detectar fundos com alta probabilidade de reversão
"""
import pandas as pd
import numpy as np


def detectar_fundo_confirmado(df, rsi_atual, rsi_anterior, vol_ratio, cfg=None):
    """
    Detecta se é um fundo confirmado com reversão
    
    Critérios TODOS obrigatórios:
    1. Preço tocou ou está < 1.5% acima da BB lower
    2. RSI entre 25-35 (oversold mas não extremo)
    3. Últimas 2 velas verdes (reversão confirmada)
    4. RSI virando pra cima (delta > 0)
    5. Volume >= 3x média (interesse voltando)
    
    Retorna: (é_fundo: bool, score: int, razao: str)
    """
    try:
        closes = pd.Series(df['close'].values)
        opens = pd.Series(df['open'].values)
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)
        volumes = pd.Series(df['volume'].values)
        
        # Calcula Bollinger Bands
        bb_sma = closes.rolling(20).mean()
        bb_std = closes.rolling(20).std()
        bb_lower = bb_sma - (bb_std * 2)
        bb_mid = bb_sma
        
        preco_atual = closes.iloc[-1]
        lower_atual = bb_lower.iloc[-1]
        
        if pd.isna(lower_atual):
            return False, 0, "BB sem dados"
        
        # Calculate rsi_delta here, as it's used in debug_info and later checks
        rsi_delta = rsi_atual - rsi_anterior

        # Calculate dist_lower here, as it's used in debug_info and later checks
        dist_lower = (preco_atual - lower_atual) / lower_atual
        
        # ============================================
        # VERIFICAÇÕES OBRIGATÓRIAS
        # ============================================
        
        # Dados para debug
        debug_info = {
            'preco': preco_atual,
            'bb_lower': lower_atual,
            'dist_bb': dist_lower * 100,  # em %
            'rsi': rsi_atual,
            'rsi_delta': rsi_delta,
            'vol': vol_ratio
        }
        
        # 1. Deve estar perto da lower band - META $5/H: Muito relaxado
        # 1. Configuração do Modo
        rsi_max = getattr(cfg, 'BOTTOM_RSI_MAX', 40) if cfg else 40 
        is_bull_mode = rsi_max >= 55 # Se configurado para aceitar RSI alto, é Bull Market
        
        # 1. Deve estar perto da lower band - META $5/H: Muito relaxado
        bb_dist_max = getattr(cfg, 'BOTTOM_BB_DIST_MAX', 0.10) if cfg else 0.10  # 10% default
        
        # Em Bull Mode, aceita comprar mais longe da banda inferior (Pullback na média)
        if is_bull_mode: bb_dist_max = 0.40 # 40% (muito permissivo, foca no RSI)

        if dist_lower > bb_dist_max:
            return False, 0, f"Longe BB lower ({dist_lower*100:.1f}%)", debug_info
        
            # 1.1 FILTRO DE TENDÊNCIA (EMA 200)
            # Regra Geral: Só compra em tendência de alta (>-0.5% da EMA200)
            # EXCEÇÃO DE OURO: Se RSI < 25 (Pânico) e Volume > 1.5x (Exaustão), COMPRA O CRASH!
            ema_filter = getattr(cfg, 'BOTTOM_EMA_FILTER_PCT', -0.005) 
            is_panic_opportunity = rsi_atual < 25 and vol_ratio > 1.5
            
            if dist_ema200 < ema_filter and not is_panic_opportunity: 
                 return False, 0, f"Tendencia Baixa (EMA200 {dist_ema200*100:.1f}%)", debug_info

        # 1.2 FILTRO DE INTENSIDADE (DUMP MÍNIMO): META $5/H - Relaxado
        # Em Bull Mode, NÃO EXIGE DUMP. Compra correções leves.
        if not is_bull_mode:
            dump_min = getattr(cfg, 'BOTTOM_DUMP_MIN', 0.003) if cfg else 0.003  # 0.3% default
            max_recente = closes.tail(15).max()
            dump_recente = (max_recente - preco_atual) / max_recente
            if dump_recente < dump_min:
                return False, 0, f"Dump fraco ({dump_recente*100:.1f}% < {dump_min*100:.1f}%)", debug_info
        
        # 2. RSI em zona boa
        rsi_min = 0 # RSI no chão é o que queremos! (Era 20)
        rsi_max = getattr(cfg, 'BOTTOM_RSI_MAX', 40) if cfg else 40 
        if not (rsi_min <= rsi_atual <= rsi_max):
            return False, 0, f"RSI {rsi_atual:.0f} fora {rsi_min}-{rsi_max}", debug_info
        
        # 3. ANTI-FACA-CAINDO: Evita quedas muito longas sem respirar
        # Se as últimas 10 velas, 8 forem vermelhas, é perigoso
        velas_vermelhas = 0
        for i in range(-1, -11, -1):
            if i-1 >= -len(closes) and closes.iloc[i] < closes.iloc[i-1]:
                velas_vermelhas += 1
        
        if velas_vermelhas >= 8:
            return False, 0, f"Sequencia vermelha ({velas_vermelhas}/10)", debug_info
            
        # 3.1 FILTRO DE VOLUME (ANTI-ZUMBI)
        # Se não tem volume (0.0x), não tem compra.
        # Usa configuração dinâmica (padrão 0.8x para evitar Dead Cat Bounce sem volume)
        vol_min = getattr(cfg, 'BOTTOM_VOL_RATIO_MIN', 0.8)
        if vol_ratio < vol_min:
             return False, 0, f"Volume Morto ({vol_ratio:.1f}x < {vol_min}x)", debug_info
        
        # 4. REVERSÃO ESTRUTURAL E ANTI-FACA CAINDO (CRÍTICO)
        # O usuário reclamou que "continua comprando queda livre". RSI baixo não basta.
        
        # 4.1 Verifica Aceleração da Queda (Falling Knife)
        # Se as últimas 3 velas caíram muito (> 2% acumulado) e a atual é verde pequena, CUIDADO.
        queda_3_velas = (closes.iloc[-4] - closes.iloc[-1]) / closes.iloc[-4]
        if queda_3_velas > 0.02: # Caiu mais de 2% rápido
             # Exige reversão mais forte (pelo menos 0.3% de alta na vela atual)
             var_vela_atual = (closes.iloc[-1] - opens.iloc[-1]) / opens.iloc[-1]
             if var_vela_atual < 0.003:
                  return False, 0, f"Queda Livre ({queda_3_velas*100:.1f}%) sem força ({var_vela_atual*100:.1f}%)", debug_info
        
        # 4.2 Vela Verde Obrigatória (Simples)
        vela_1_verde = closes.iloc[-1] > opens.iloc[-1]
        
        # Apenas 1 vela verde obrigatória
        if not vela_1_verde:
            return False, 0, "Sem vela verde atual", debug_info
            
        # 4.1 Momentum 5min removido pois impedia V-Shape Recovery.
        # A proteção contra queda livre já é feita no bloco 'ANTI-FACA CAINDO' acima.
        
        # Vela atual deve ter ganho mínimo (mais rigoroso: 0.2%)
        vela_1_ganho = (closes.iloc[-1] - opens.iloc[-1]) / opens.iloc[-1] if opens.iloc[-1] > 0 else 0
        candle_gain_min = getattr(cfg, 'BOTTOM_CANDLE_GAIN_MIN', 0.002) if cfg else 0.002 # 0.2%
        if vela_1_ganho < candle_gain_min:
            return False, 0, f"Ganho vela fraco {vela_1_ganho*100:.2f}% < {candle_gain_min*100:.1f}%", debug_info
        
        # 5. RSI deve estar subindo - META $5/H: Relaxado
        rsi_delta_min = getattr(cfg, 'BOTTOM_RSI_DELTA_MIN', 0.3) if cfg else 0.3  # 0.3 default
        if rsi_delta <= rsi_delta_min:
            return False, 0, f"RSI fraco (+{rsi_delta:.1f} < +{rsi_delta_min})", debug_info
        
        # 6. Volume - Opcional (removido como bloqueador)
        vol_ratio_min = getattr(cfg, 'BOTTOM_VOL_RATIO_MIN', 0.5) if cfg else 0.5  # 0.5x default
        # Apenas penaliza score, não bloqueia
        vol_ok = vol_ratio >= vol_ratio_min
        
        # ============================================
        # SCORE (se passou em tudo)
        # ============================================
        score = 0
        razoes = []
        
        # Quanto mais perto da lower, melhor
        if dist_lower < 0.005:  # < 0.5%
            score += 30
            razoes.append(f"BB lower {dist_lower*100:.1f}%")
        elif dist_lower < 0.015:  # < 1.5%
            score += 25
            razoes.append(f"Perto BB {dist_lower*100:.1f}%")
        else:
            score += 20
            razoes.append(f"Proximo BB {dist_lower*100:.1f}%")
        
        # RSI ideal 28-32
        if 28 <= rsi_atual <= 32:
            score += 25
            razoes.append(f"RSI ideal {rsi_atual:.0f}")
        elif 25 <= rsi_atual <= 35:
            score += 20
            razoes.append(f"RSI bom {rsi_atual:.0f}")
        else:
            score += 15
            razoes.append(f"RSI {rsi_atual:.0f}")
        
        # RSI subindo forte
        if rsi_delta >= 2:
            score += 20
            razoes.append(f"RSI +{rsi_delta:.1f}")
        elif rsi_delta >= 1:
            score += 15
            razoes.append(f"RSI +{rsi_delta:.1f}")
        else:
            score += 10
            razoes.append(f"RSI +{rsi_delta:.1f}")
        
        # Volume alto
        if vol_ratio >= 7:
            score += 15
            razoes.append(f"Vol {vol_ratio:.1f}x")
        elif vol_ratio >= 5:
            score += 12
            razoes.append(f"Vol {vol_ratio:.1f}x")
        else:
            score += 10
            razoes.append(f"Vol {vol_ratio:.1f}x")
        
        # Força da reversão (tamanho das velas verdes)
        body_1 = abs(closes.iloc[-1] - opens.iloc[-1]) / opens.iloc[-1]
        body_2 = abs(closes.iloc[-2] - opens.iloc[-2]) / opens.iloc[-2]
        
        if body_1 > 0.01 and body_2 > 0.01:  # > 1% cada
            score += 10
            razoes.append("Reversao forte")
        
        return True, score, " | ".join(razoes), debug_info
        
    except Exception as e:
        return False, 0, f"Erro: {str(e)[:50]}", {}


def verificar_suporte_adicional(df):
    """
    Verificações adicionais de suporte técnico
    Retorna pontos de confiança extra
    """
    try:
        closes = pd.Series(df['close'].values)
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)
        
        # MA50 como suporte
        ma50 = closes.rolling(50).mean()
        if len(closes) >= 50 and not pd.isna(ma50.iloc[-1]):
            preco = closes.iloc[-1]
            if abs(preco - ma50.iloc[-1]) / preco < 0.02:  # < 2% da MA50
                return 10, "Perto MA50"
        
        # Mínima local (não fez novo low nas últimas 10 velas)
        minima_10 = lows.tail(10).min()
        if lows.iloc[-1] > minima_10:
            return 5, "Acima minima"
        
        return 0, ""
        
    except:
        return 0, ""
