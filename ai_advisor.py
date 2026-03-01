"""
AI Advisor v5.0 — OLLAMA LOCAL + OpenRouter Fallback
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Principal: Ollama local (qwen3.5:cloud) — sem rate limits, sem custo, ~1.4s
Fallback:  OpenRouter (Arcee Trinity, Gemini) — caso Ollama não responda
"""

import requests
import json
import time
import threading

# ── Cache ──────────────────────────────────────────────────────
_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 90  # 1.5min por moeda

# ── Ollama (local) ─────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3.5:cloud"
OLLAMA_TIMEOUT = 25  # segundos

# ── OpenRouter (fallback) ───────────────────────────────────────
OPENROUTER_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    "arcee-ai/trinity-large-preview:free",  # 1.3s — free
    "arcee-ai/trinity-mini:free",           # 1.0s — free
    "google/gemini-2.0-flash-001",          # 1.1s — pago, garantido
]
OPENROUTER_TIMEOUT = 22

# ── System Prompt ultra-compacto ──────────────────────────────
SYSTEM_PROMPT = """Gestor de risco cripto. Dado sinais técnicos, rejeite se: RSI>65, velas_verdes>=4, candle_atual>0.5%, BB>0.80, dist_resist<0.5%, vol_ratio<1.2, ema21_dist>2%. Caso contrário aprove. Responda APENAS: {"d":"C" ou "N","c":0-100,"m":"motivo curto"}"""


def consultar_ia(symbol: str, dados: dict) -> dict:
    """Tenta Ollama local primeiro, depois OpenRouter como fallback."""

    # Cache
    with _cache_lock:
        if symbol in _cache:
            cached = _cache[symbol]
            if time.time() - cached['timestamp'] < _CACHE_TTL:
                return cached['resultado']

    prompt = _montar_prompt(symbol, dados)

    # 1. Tenta Ollama local
    resultado = _consultar_ollama(prompt)

    # 2. Fallback OpenRouter se Ollama falhou
    if resultado['erro']:
        resultado = _consultar_openrouter(prompt)

    # Salva cache se não deu erro
    if not resultado['erro']:
        with _cache_lock:
            _cache[symbol] = {'timestamp': time.time(), 'resultado': resultado}

    return resultado


def _consultar_ollama(prompt: str) -> dict:
    """Consulta Ollama local."""
    try:
        r = requests.post(OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'messages': [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user',   'content': prompt}
                ],
                'stream':  False,
                'think':   False,
                'options': {'temperature': 0.1, 'num_predict': 40}
            },
            timeout=OLLAMA_TIMEOUT)

        if r.status_code == 200:
            content = r.json().get('message', {}).get('content', '')
            return _parse(content)

        return _erro(f"Ollama HTTP {r.status_code}")

    except requests.exceptions.ConnectionError:
        return _erro("Ollama offline")
    except requests.exceptions.Timeout:
        return _erro("Ollama timeout")
    except Exception as e:
        return _erro(f"Ollama: {str(e)[:40]}")


def _consultar_openrouter(prompt: str) -> dict:
    """Fallback: consulta OpenRouter."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://trading-bot.local"
    }
    for model in OPENROUTER_MODELS:
        try:
            r = requests.post(OPENROUTER_URL, headers=headers,
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user',   'content': prompt}
                    ],
                    'temperature': 0.1,
                    'max_tokens':  200
                },
                timeout=OPENROUTER_TIMEOUT)

            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content']
                return _parse(content)

        except requests.exceptions.Timeout:
            continue
        except Exception:
            continue

    return _erro("Todos os modelos falharam")


def _montar_prompt(symbol: str, d: dict) -> str:
    """Prompt ultra-compacto — mínimo de tokens."""
    # Formato: SYM|rsi|bb|vol|dist_r|ema21|verdes|candle_chg|macd_cross|sinais
    sinais = ','.join(d.get('sinais', []) or ['?'])
    return (f"{symbol} "
            f"rsi={d.get('rsi',50):.0f}({'↑' if d.get('rsi_subindo') else '↓'}) "
            f"bb={d.get('bb_posicao',0.5):.0%} "
            f"vol={d.get('vol_ratio',1):.1f}x({'↑' if d.get('vol_crescente') else '↓'}) "
            f"dist_r={d.get('dist_resistencia',99):.1f}% "
            f"ema21={d.get('dist_ema21',0):+.1f}% "
            f"verdes={d.get('verdes_fechados',0)} "
            f"candle={d.get('ganho_candle_atual',0):.2f}% "
            f"macd_cross={'S' if d.get('macd_cruzou_agora') else 'N'} "
            f"sinais=[{sinais}]")


def _parse(content: str) -> dict:
    """Extrai JSON — suporta formato compacto {d,c,m} e normal {decisao,confianca,motivo}."""
    try:
        import re
        content = content.strip()
        # Remove thinking
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        # Remove markdown
        if '```' in content:
            for part in content.split('```'):
                part = part.strip().lstrip('json').strip()
                if part.startswith('{'):
                    content = part; break

        start = content.find('{')
        end   = content.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            dec_raw = str(data.get('d') or data.get('decisao') or 'N').upper()
            # Fix: não usar `or` com 0 (falsy) — checar None explicitamente
            c_val = data.get('c')
            conf_val = data.get('confianca')
            conf = int(c_val if c_val is not None else (conf_val if conf_val is not None else 50))
            motivo  = str(data.get('m') or data.get('motivo') or '')[:80]
            decisao = 'COMPRAR' if dec_raw.startswith('C') else 'NAO_COMPRAR'
            return {'decisao': decisao, 'confianca': min(100, max(0, conf)), 'motivo': motivo, 'erro': False}

        return {'decisao': 'NAO_COMPRAR', 'confianca': 50, 'motivo': content[:60], 'erro': False}
    except Exception as e:
        return _erro(f"Parse:{str(e)[:30]}")


def _erro(msg: str) -> dict:
    return {'decisao': 'ERRO', 'confianca': 0, 'motivo': msg, 'erro': True}


def limpar_cache():
    with _cache_lock:
        agora = time.time()
        expirados = [k for k, v in _cache.items() if agora - v['timestamp'] > _CACHE_TTL]
        for k in expirados:
            del _cache[k]


# ──────────────────────────────────────────────────────────────────
# 🚪 AI DE SAÍDA — analisa posições abertas e decide manter/sair
# ──────────────────────────────────────────────────────────────────

_EXIT_SYSTEM = """Gestor de posições abertas em scalping cripto.
Analise se deve MANTER ou SAIR da posição agora.
SAIR se: pct<-0.3% e momentum negativo, OU pct>0.4% e momentum revertendo, OU pct<0% e tempo>8min.
MANTER se: momentum ainda positivo e não atingiu alvo.
Responda APENAS: {"d":"M" ou "S","c":0-100,"m":"motivo curto"}"""

def consultar_saida_ia(symbol: str, pct: float, pct_max: float, tempo_min: float,
                        rsi: float, rsi_delta: float, vol_ratio: float,
                        macd_hist: float, macd_prev: float) -> dict:
    """
    IA decide se deve MANTER (M) ou SAIR (S) de uma posição aberta.
    Sem cache — sempre decisão fresca.
    """
    # Prompt ultra-compacto para saída
    momentum_str = "↑" if macd_hist > macd_prev else "↓"
    prompt = (f"{symbol} pos={pct:+.2f}%(max={pct_max:+.2f}%) "
              f"tempo={tempo_min:.1f}min "
              f"rsi={rsi:.0f}({'+' if rsi_delta>0 else ''}{rsi_delta:.1f}) "
              f"vol={vol_ratio:.1f}x "
              f"macd={momentum_str}({'pos' if macd_hist>0 else 'neg'}) "
              f"MANTER ou SAIR?")

    resultado = _consultar_ollama_saida(prompt)
    if resultado['erro']:
        resultado = _consultar_openrouter_saida(prompt)
    return resultado


def _consultar_ollama_saida(prompt: str) -> dict:
    try:
        r = requests.post(OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'messages': [
                    {'role': 'system', 'content': _EXIT_SYSTEM},
                    {'role': 'user',   'content': prompt}
                ],
                'stream': False, 'think': False,
                'options': {'temperature': 0.1, 'num_predict': 60}
            }, timeout=15)
        if r.status_code == 200:
            content = r.json().get('message', {}).get('content', '')
            return _parse_saida(content)
        return _erro_saida(f"Ollama HTTP {r.status_code}")
    except requests.exceptions.ConnectionError:
        return _erro_saida("Ollama offline")
    except Exception as e:
        return _erro_saida(str(e)[:30])


def _consultar_openrouter_saida(prompt: str) -> dict:
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    for model in OPENROUTER_MODELS:
        try:
            r = requests.post(OPENROUTER_URL, headers=headers,
                json={'model': model,
                      'messages': [{'role':'system','content':_EXIT_SYSTEM},
                                   {'role':'user','content':prompt}],
                      'temperature': 0.1, 'max_tokens': 40},
                timeout=12)
            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content']
                return _parse_saida(content)
        except: continue
    return _erro_saida("Todos falharam")


def _parse_saida(content: str) -> dict:
    try:
        import re
        content = re.sub(r'<think>.*?</think>', '', content.strip(), flags=re.DOTALL).strip()
        if '```' in content:
            for p in content.split('```'):
                p = p.strip().lstrip('json').strip()
                if p.startswith('{'): content = p; break
        s = content.find('{'); e = content.rfind('}') + 1
        if s >= 0 and e > s:
            data = json.loads(content[s:e])
            dec = str(data.get('d') or data.get('decisao') or 'M').upper().strip('"\'')
            conf = min(100, max(0, int(data.get('c') or data.get('confianca') or 50)))
            motivo = str(data.get('m') or data.get('motivo') or '')[:60]
            # S=Sair, N=Não manter (= Sair), M=Manter
            acao = 'SAIR' if dec.startswith('S') or dec == 'N' else 'MANTER'
            return {'acao': acao, 'confianca': conf, 'motivo': motivo, 'erro': False}
        return {'acao': 'MANTER', 'confianca': 50, 'motivo': content[:40], 'erro': False}
    except Exception as e:
        return _erro_saida(f"Parse:{str(e)[:20]}")


def _erro_saida(msg: str) -> dict:
    return {'acao': 'MANTER', 'confianca': 0, 'motivo': msg, 'erro': True}

