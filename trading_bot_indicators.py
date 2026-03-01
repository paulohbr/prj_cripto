"""
Indicadores Técnicos para Trading Bot
Funções de verificação individuais para cada indicador
"""
import pandas as pd
import numpy as np


def verificar_ichimoku(df):
    """Verifica Ichimoku Cloud para tendência bullish"""
    try:
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)
        closes = pd.Series(df['close'].values)
        
        # Calc Tenkan (9), Kijun (26)
        tenkan = ((highs.rolling(9).max() + lows.rolling(9).min()) / 2)
        kijun = ((highs.rolling(26).max() + lows.rolling(26).min()) / 2)
        
        # Senkou A e B
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((highs.rolling(52).max() + lows.rolling(52).min()) / 2).shift(26)
        
        preco = closes.iloc[-1]
        senkou_a_val = senkou_a.iloc[-1] if not pd.isna(senkou_a.iloc[-1]) else 0
        senkou_b_val = senkou_b.iloc[-1] if not pd.isna(senkou_b.iloc[-1]) else 0
        
        score = 0
        razoes = []
        
        # Preco acima nuvem
        if preco > max(senkou_a_val, senkou_b_val):
            score += 20
            razoes.append("Acima nuvem")
        else:
            return False, 0, "Abaixo nuvem"
        
        # Tenkan > Kijun
        if tenkan.iloc[-1] > kijun.iloc[-1]:
            score += 15
            razoes.append("TK bullish")
        
        # Nuvem verde
        if senkou_a_val > senkou_b_val:
            score += 10
            razoes.append("Nuvem verde")
        
        return True, score, " | ".join(razoes)
    except Exception as e:
        return False, 0, f"Erro Ichi: {str(e)[:30]}"


def verificar_bollinger_bounce(df):
    """Verifica proximidade da lower BB"""
    try:
        closes = pd.Series(df['close'].values)
        bb_sma = closes.rolling(20).mean()
        bb_std = closes.rolling(20).std()
        bb_lower = bb_sma - (bb_std * 2)
        
        preco = closes.iloc[-1]
        lower = bb_lower.iloc[-1]
        
        if pd.isna(lower):
            return False, 0, "BB sem dados"
        
        dist = (preco - lower) / preco
        score = 0
        
        if dist < 0.01:
            score = 20
            razao = "Muito perto BB"
        elif dist < 0.025:
            score = 15
            razao = "Perto BB"
        elif dist < 0.05:
            score = 10
            razao = "Proximo BB"
        else:
            return False, 0, "Longe BB"
        
        if df['close'].iloc[-1] > df['open'].iloc[-1]:
            score += 10
            razao += " + verde"
        
        return True, score, razao
    except Exception as e:
        return False, 0, f"Erro BB: {str(e)[:30]}"


def verificar_medias_moveis(df):
    """Verifica alinhamento MAs"""
    try:
        closes = pd.Series(df['close'].values)
        ma20 = closes.rolling(20).mean()
        ma50 = closes.rolling(50).mean()
        
        preco = closes.iloc[-1]
        ma20_val = ma20.iloc[-1]
        ma50_val = ma50.iloc[-1] if len(closes) >= 50 else None
        
        if pd.isna(ma20_val):
            return False, 0, "MA sem dados"
        
        score = 0
        razoes = []
        
        if preco > ma20_val:
            score += 15
            razoes.append("P>MA20")
        else:
            return False, 0, "P<MA20"
        
        if ma50_val and not pd.isna(ma50_val) and ma20_val > ma50_val:
            score += 10
            razoes.append("MA20>MA50")
        
        return True, score, " | ".join(razoes)
    except Exception as e:
        return False, 0, f"Erro MA: {str(e)[:30]}"


def verificar_rsi_otimo(df, rsi_atual, rsi_anterior):
    """Verifica RSI em faixa ideal"""
    try:
        if not (30 <= rsi_atual <= 60):
            return False, 0, f"RSI {rsi_atual:.0f} fora 30-60"
        
        score = 0
        razoes = []
        
        if 35 <= rsi_atual <= 50:
            score += 20
            razoes.append(f"RSI ideal {rsi_atual:.0f}")
        else:
            score += 10
            razoes.append(f"RSI {rsi_atual:.0f}")
        
        rsi_delta = rsi_atual - rsi_anterior
        if rsi_delta >= 2.0:
            score += 15
            razoes.append(f"+{rsi_delta:.1f}")
        elif rsi_delta >= 1.0:
            score += 10
            razoes.append(f"+{rsi_delta:.1f}")
        else:
            return False, 0, f"RSI nao subindo ({rsi_delta:+.1f})"
        
        return True, score, " | ".join(razoes)
    except Exception as e:
        return False, 0, f"Erro RSI: {str(e)[:30]}"


def verificar_volume_forte(vol_ratio):
    """Verifica volume forte"""
    try:
        if vol_ratio < 4.0:
            return False, 0, f"Vol {vol_ratio:.1f}x<4x"
        
        if vol_ratio >= 10:
            score, razao = 25, f"Vol {vol_ratio:.1f}x excelente"
        elif vol_ratio >= 7:
            score, razao = 20, f"Vol {vol_ratio:.1f}x otimo"
        elif vol_ratio >= 5:
            score, razao = 15, f"Vol {vol_ratio:.1f}x bom"
        else:
            score, razao = 10, f"Vol {vol_ratio:.1f}x"
        
        return True, score, razao
    except Exception as e:
        return False, 0, f"Erro Vol: {str(e)[:30]}"


def verificar_padrao_velas(df, velas_verdes_min=3):
    """Verifica padrão de velas verdes"""
    try:
        velas_verdes = 0
        for i in range(len(df) - 1, -1, -1):
            if df['close'].iloc[i] > df['open'].iloc[i]:
                velas_verdes += 1
            else:
                break
        
        if velas_verdes < velas_verdes_min:
            return False, 0, f"So {velas_verdes} verdes"
        
        score = min(velas_verdes * 3, 15)
        razao = f"{velas_verdes} verdes"
        
        return True, score, razao
    except Exception as e:
        return False, 0, f"Erro velas: {str(e)[:30]}"
