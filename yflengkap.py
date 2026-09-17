import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from datetime import datetime, timedelta
import warnings
import os
import json
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from supabase import create_client, Client

load_dotenv()
warnings.filterwarnings('ignore')

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="🤖 Crypto Signal Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
    .stApp { background: #0a0a1a; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b;
        border-radius: 16px; padding: 16px;
        box-shadow: 0 4px 20px rgba(0,255,255,0.05);
    }
    .signal-buy {
        background: linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,255,136,0.05));
        border: 1px solid #00ff88; border-radius: 12px;
        padding: 12px 20px; color: #00ff88; font-weight: 600; font-size: 18px;
    }
    .signal-sell {
        background: linear-gradient(135deg, rgba(255,59,92,0.15), rgba(255,59,92,0.05));
        border: 1px solid #ff3b5c; border-radius: 12px;
        padding: 12px 20px; color: #ff3b5c; font-weight: 600; font-size: 18px;
    }
    .signal-hold {
        background: linear-gradient(135deg, rgba(255,170,0,0.15), rgba(255,170,0,0.05));
        border: 1px solid #ffaa00; border-radius: 12px;
        padding: 12px 20px; color: #ffaa00; font-weight: 600; font-size: 18px;
    }
    .signal-take-profit {
        background: linear-gradient(135deg, rgba(0,150,255,0.15), rgba(0,150,255,0.05));
        border: 1px solid #0096ff; border-radius: 12px;
        padding: 12px 20px; color: #0096ff; font-weight: 600; font-size: 18px;
    }
    .pending-signal {
        background: linear-gradient(135deg, rgba(255,170,0,0.15), rgba(255,170,0,0.05));
        border: 1px solid #ffaa00; border-radius: 12px;
        padding: 12px 20px; color: #ffaa00; font-weight: 600; font-size: 16px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
    .plan-card {
        background: linear-gradient(145deg, #0d1425, #070b14);
        border: 1px solid #1e293b; border-radius: 16px;
        padding: 20px; margin-bottom: 12px;
    }
    .plan-header { font-size: 22px; font-weight: 800; color: #00ff88; margin-bottom: 8px; }
    .plan-confidence {
        display: inline-block; background: rgba(0,255,136,0.1);
        border: 1px solid #00ff88; border-radius: 12px;
        padding: 4px 12px; color: #00ff88; font-weight: 700; font-size: 14px;
    }
    .level-box {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b; border-radius: 12px;
        padding: 14px; text-align: center;
    }
    .level-label { color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
    .level-value { font-size: 20px; font-weight: 800; color: #f1f5f9; margin: 6px 0; }
    .level-pct { font-size: 12px; font-weight: 600; }
    .level-pct.pos { color: #00ff88; }
    .level-pct.neg { color: #ff3b5c; }
    .reason-item { padding: 6px 0; color: #cbd5e1; font-size: 14px; }
    .stButton > button {
        background: linear-gradient(145deg, #00ff88, #00cc66);
        color: #000; font-weight: 700; border: none;
        border-radius: 10px; padding: 10px 24px; transition: all 0.3s ease;
    }
    .stButton > button:hover { transform: scale(1.03); box-shadow: 0 0 30px rgba(0,255,255,0.3); }
    .setup-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 15px; }
    .setup-dip { background: rgba(0,255,136,.15); color:#00ff88; border:1px solid #00ff88; }
    .setup-breakout { background: rgba(0,200,255,.15); color:#00c8ff; border:1px solid #00c8ff; }
    .setup-liq { background: rgba(168,85,247,.15); color:#a855f7; border:1px solid #a855f7; }
    .setup-wait { background: rgba(251,191,36,.15); color:#fbbf24; border:1px solid #fbbf24; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# SUPABASE
# =========================================================
@st.cache_resource
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        try:
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
        except:
            st.error("❌ SUPABASE_URL atau SUPABASE_KEY tidak ditemukan")
            st.stop()
    return create_client(url, key)

def get_watchlist():
    supabase = get_supabase()
    try:
        res = supabase.table("watchlist").select("symbol").order("added_at").execute()
        return [row["symbol"] for row in res.data] if res.data else ["BTC"]
    except:
        return ["BTC"]

def add_coin(symbol):
    supabase = get_supabase()
    try:
        supabase.table("watchlist").insert({"symbol": symbol.upper()}).execute()
        return True
    except:
        return False

def remove_coin(symbol):
    supabase = get_supabase()
    try:
        res = supabase.table("watchlist").delete().eq("symbol", symbol.upper()).execute()
        return len(res.data) > 0
    except:
        return False

def is_duplicate_signal(symbol, signal, minutes=5):
    supabase = get_supabase()
    try:
        five_min_ago = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        res = supabase.table("signal_history")\
            .select("id").eq("symbol", symbol).eq("signal", signal)\
            .gte("timestamp", five_min_ago).execute()
        return len(res.data) > 0
    except:
        return False

def save_signal(data):
    supabase = get_supabase()
    try:
        symbol = data.get("symbol"); signal = data.get("signal")
        if is_duplicate_signal(symbol, signal, minutes=5):
            return False
        data["timestamp"] = datetime.now().isoformat()
        supabase.table("signal_history").insert(data).execute()
        return True
    except:
        return False

def save_trade_plan(plan):
    supabase = get_supabase()
    try:
        data = {
            "symbol": plan["symbol"], "timeframe": plan["timeframe"],
            "setup_type": plan["setup_type"], "confidence": plan["confidence"],
            "entry": float(plan["entry"]), "stop_loss": float(plan["stop_loss"]),
            "tp1": float(plan["tp1"]), "tp2": float(plan["tp2"]), "tp3": float(plan["tp3"]),
            "rr": float(plan["rr"]),
            "reasons": json.dumps(plan["reasons"]),
            "created_at": datetime.now().isoformat()
        }
        supabase.table("trade_plans").insert(data).execute()
        return True
    except Exception as e:
        print(f"Save plan error: {e}")
        return False

def get_signal_history(limit=100):
    supabase = get_supabase()
    try:
        res = supabase.table("signal_history").select("*").order("timestamp", desc=True).limit(limit).execute()
        return res.data
    except:
        return []

def update_performance(stats):
    supabase = get_supabase()
    try:
        supabase.table("performance").upsert(
            {"key": "performance_stats", "value": stats, "updated_at": datetime.now().isoformat()},
            on_conflict="key"
        ).execute()
        return True
    except:
        return False

def get_performance():
    supabase = get_supabase()
    default = {"total_signals": 0, "wins": 0, "losses": 0, "total_profit": 0, "win_rate": 0}
    try:
        res = supabase.table("performance").select("value").eq("key", "performance_stats").execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["value"]
        return default
    except:
        return default

# =========================================================
# TELEGRAM
# =========================================================
if "sent_signals" not in st.session_state:
    st.session_state.sent_signals = {}
if "last_telegram_time" not in st.session_state:
    st.session_state.last_telegram_time = {}

def send_telegram_once(symbol, signal, result):
    """Kirim notifikasi signal scanner ke Telegram (versi detail)."""
    now = datetime.now()

    # Cooldown 10 menit per coin
    last_time = st.session_state.last_telegram_time.get(symbol)
    if last_time is not None:
        diff = (now - last_time).seconds / 60
        if diff < 10:
            return False

    signal_key = f"{symbol}_{signal}_{now.strftime('%Y%m%d_%H%M')}"
    if signal_key in st.session_state.sent_signals:
        return False

    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            return False

        # Kalau result adalah string, kirim simple
        if isinstance(result, str):
            msg = f"⚡ <b>SIGNAL ALERT</b>\n\n"
            msg += f"<b>{symbol}</b>\n"
            msg += f"{signal}\n"
            msg += f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML"
            }, timeout=10)
            if r.status_code == 200:
                st.session_state.sent_signals[signal_key] = True
                st.session_state.last_telegram_time[symbol] = now
                return True
            return False

        # Kalau result adalah dict (plan), kirim detail
        msg = format_plan_for_telegram(result)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)

        if r.status_code == 200:
            st.session_state.sent_signals[signal_key] = True
            st.session_state.last_telegram_time[symbol] = now
            return True

    except Exception as e:
        print(f"Telegram error: {e}")
    return False

def send_telegram_plan(plan_text):
    """Kirim pesan HTML ke Telegram (untuk plan card / test)."""
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": plan_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=10)
            return r.status_code == 200
    except:
        pass
    return False

def send_telegram_test(message):
    """Kirim test message ke Telegram."""
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)
            return True
    except:
        pass
    return False

# =========================================================
# FORMAT PRICE
# =========================================================
def format_price(value):
    if pd.isna(value) or value is None:
        return "-"
    if value >= 1000: return f"$ {value:,.2f}"
    elif value >= 100: return f"$ {value:,.3f}"
    elif value >= 1: return f"$ {value:,.4f}"
    elif value >= 0.01: return f"$ {value:,.6f}"
    else: return f"$ {value:,.8f}"

# =========================================================
# GET DATA
# =========================================================
@st.cache_data(ttl=30, show_spinner=False)
def get_data(symbol, interval, period):
    try:
        ticker = f"{symbol}-USD"
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df.rename(columns={df.columns[0]: "Time"}, inplace=True)
        df["Time"] = pd.to_datetime(df["Time"])
        if df["Close"].iloc[-1] <= 0:
            return None
        return df
    except:
        return None

def get_data_safe(symbol, interval, min_candles=20):
    periods = {
        "1m": ["1d", "5d", "7d"],
        "5m": ["2d", "5d", "7d", "14d"],
        "15m": ["5d", "7d", "14d", "30d"],
        "30m": ["7d", "14d", "30d"],
        "1h": ["7d", "14d", "30d", "60d"],
        "4h": ["14d", "30d", "60d", "90d"],
        "1d": ["30d", "60d", "90d", "1y"],
    }
    for period in periods.get(interval, ["7d", "14d", "30d"]):
        df = get_data(symbol, interval, period)
        if df is not None and len(df) >= min_candles:
            return df
    return None

# =========================================================
# INDIKATOR
# =========================================================
def EMA(df, period=20):
    return df["Close"].ewm(span=period, adjust=False).mean()

def MACD(df, fast=12, slow=26, signal=9):
    ema_fast = EMA(df, fast)
    ema_slow = EMA(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def StochasticRSI(df, period=14, smooth_k=3, smooth_d=3):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min()) * 100
    k = stoch_rsi.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d, rsi

def get_atr(df, period=14):
    high = df["High"]; low = df["Low"]; close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# =========================================================
# PIVOTS / LIQUIDITY / S&R / FIB
# =========================================================
def get_pivots(df, left=3, right=3):
    h = df["High"]; l = df["Low"]
    ph = (h == h.rolling(left + right + 1, center=True).max()).fillna(False)
    pl = (l == l.rolling(left + right + 1, center=True).min()).fillna(False)
    return ph, pl

def get_liquidity_zones(df, lookback=100, tolerance_pct=0.5):
    if df is None or len(df) < 30:
        return [], []
    recent = df.tail(lookback)
    ph, pl = get_pivots(recent)
    highs = recent.loc[ph, "High"].tolist()
    lows = recent.loc[pl, "Low"].tolist()
    price = float(df["Close"].iloc[-1])
    tol = price * (tolerance_pct / 100)

    def cluster(levels):
        if not levels: return []
        levels = sorted(levels)
        zones, cur = [], [levels[0]]
        for v in levels[1:]:
            if v - cur[-1] <= tol:
                cur.append(v)
            else:
                zones.append(sum(cur) / len(cur)); cur = [v]
        zones.append(sum(cur) / len(cur))
        return zones

    buy_side = [z for z in cluster(highs) if z > price]
    sell_side = [z for z in cluster(lows) if z < price]
    return buy_side, sell_side

def get_support_resistance(df, lookback=100):
    buy_side, sell_side = get_liquidity_zones(df, lookback)
    supports = sorted(sell_side, reverse=True)
    resistances = sorted(buy_side)
    return supports, resistances

def get_fibonacci(df, lookback=100):
    if df is None or len(df) < 30:
        return {}
    recent = df.tail(lookback)
    swing_high = float(recent["High"].max())
    swing_low = float(recent["Low"].min())
    diff = swing_high - swing_low
    if diff <= 0: return {}
    price = float(df["Close"].iloc[-1])
    levels = {}
    if price > (swing_low + swing_high) / 2:
        for r in [0.236, 0.382, 0.5, 0.618, 0.786]:
            levels[r] = swing_high - diff * r
        levels["Swing High"] = swing_high
        levels["Swing Low"] = swing_low
    else:
        for r in [0.236, 0.382, 0.5, 0.618, 0.786]:
            levels[r] = swing_low + diff * r
        levels["Swing Low"] = swing_low
        levels["Swing High"] = swing_high
    return levels

# =========================================================
# ANALISIS MACD + STOCH
# =========================================================
def analyze_macd_stoch(df, timeframe=""):
    if df is None or len(df) < 30:
        return None
    macd_line, signal_line, histogram = MACD(df)
    stoch_k, stoch_d, rsi = StochasticRSI(df)
    ema20 = EMA(df, 20); ema50 = EMA(df, 50)

    last = df.iloc[-1]
    price = float(last["Close"])
    volume = float(last["Volume"])
    vol_ma = float(df["Volume"].rolling(10).mean().iloc[-1])
    volume_ratio = volume / vol_ma if vol_ma > 0 else 1

    macd_val = float(macd_line.iloc[-1]); signal_val = float(signal_line.iloc[-1])
    hist_val = float(histogram.iloc[-1])
    hist_prev = float(histogram.iloc[-2]) if len(histogram) > 1 else hist_val
    macd_prev = float(macd_line.iloc[-2]) if len(macd_line) > 1 else macd_val
    signal_prev = float(signal_line.iloc[-2]) if len(signal_line) > 1 else signal_val

    stoch_k_val = float(stoch_k.iloc[-1]); stoch_d_val = float(stoch_d.iloc[-1])
    stoch_k_prev = float(stoch_k.iloc[-2]) if len(stoch_k) > 1 else stoch_k_val
    stoch_d_prev = float(stoch_d.iloc[-2]) if len(stoch_d) > 1 else stoch_d_val
    rsi_val = float(rsi.iloc[-1])
    ema20_val = float(ema20.iloc[-1]); ema50_val = float(ema50.iloc[-1])

    macd_golden_cross = (macd_prev < signal_prev) and (macd_val > signal_val)
    macd_death_cross = (macd_prev > signal_prev) and (macd_val < signal_val)
    stoch_golden_cross = (stoch_k_prev < stoch_d_prev) and (stoch_k_val > stoch_d_val)
    stoch_death_cross = (stoch_k_prev > stoch_d_prev) and (stoch_k_val < stoch_d_val)

    hist_increasing = hist_val > hist_prev
    hist_decreasing = hist_val < hist_prev
    hist_positive = hist_val > 0
    hist_negative = hist_val < 0

    bullish_trend = price > ema20_val > ema50_val
    bearish_trend = price < ema20_val < ema50_val
    volume_confirmed = volume_ratio > 1.2

    buy_score = 0; sell_score = 0
    if macd_val > signal_val: buy_score += 1
    if hist_positive: buy_score += 1
    if macd_golden_cross: buy_score += 2
    if hist_increasing and hist_positive: buy_score += 1
    if stoch_k_val < 20 and stoch_d_val < 20: buy_score += 2
    elif 20 <= stoch_k_val <= 40 and stoch_k_val > stoch_d_val: buy_score += 1
    if stoch_golden_cross and stoch_k_val < 40: buy_score += 2
    if stoch_k_val > stoch_d_val: buy_score += 0.5
    if bullish_trend: buy_score += 1
    elif price > ema20_val: buy_score += 0.5
    if volume_confirmed: buy_score += 0.5
    if rsi_val < 70: buy_score += 0.5

    if macd_val < signal_val: sell_score += 1
    if hist_negative: sell_score += 1
    if macd_death_cross: sell_score += 2
    if hist_decreasing and hist_positive: sell_score += 1
    if stoch_k_val > 80 and stoch_d_val > 80: sell_score += 2
    elif 80 <= stoch_k_val <= 95: sell_score += 1
    if stoch_death_cross and stoch_k_val > 80: sell_score += 2
    if stoch_k_val < stoch_d_val: sell_score += 0.5
    if bearish_trend: sell_score += 1
    elif price < ema20_val: sell_score += 0.5
    if rsi_val > 30: sell_score += 0.5

    action = "⏳ WAIT"; signal_type = "HOLD"; signal_strength = 0
    if buy_score >= 5:
        if buy_score >= 7 and stoch_golden_cross and macd_golden_cross:
            signal_type = "⭐⭐⭐ STRONG BUY"; signal_strength = 3; action = "🟢 STRONG BUY"
        elif buy_score >= 6 and (macd_golden_cross or stoch_golden_cross):
            signal_type = "⭐⭐ BUY"; signal_strength = 2; action = "🟢 BUY"
        else:
            signal_type = "⭐ BUY"; signal_strength = 1; action = "🟢 BUY"
    elif sell_score >= 5:
        if sell_score >= 7 and stoch_death_cross and macd_death_cross:
            signal_type = "⭐⭐⭐ STRONG SELL"; signal_strength = 3; action = "🔴 STRONG SELL"
        elif sell_score >= 6 and (macd_death_cross or stoch_death_cross):
            signal_type = "⭐⭐ SELL"; signal_strength = 2; action = "🔴 SELL"
        else:
            signal_type = "⭐ SELL"; signal_strength = 1; action = "🔴 SELL"
    elif stoch_k_val > 85 and hist_decreasing and hist_positive:
        signal_type = "💰 TAKE PROFIT"; signal_strength = 2; action = "💰 TAKE PROFIT"
    else:
        if macd_val > signal_val and 20 <= stoch_k_val <= 80:
            signal_type = "🟡 HOLD"; action = "🟡 HOLD"
        elif macd_val > signal_val and stoch_k_val < 20:
            signal_type = "🟡 WAIT"; action = "⏳ WAIT"
        elif macd_val < signal_val and stoch_k_val > 80:
            signal_type = "🟡 WAIT"; action = "⏳ WAIT"
        else:
            signal_type = "🟡 HOLD / WAIT"; action = "⏳ WAIT"

    return {
        "symbol": None, "timeframe": timeframe,
        "action": action, "signal_type": signal_type, "signal_strength": signal_strength,
        "score": {"buy": buy_score, "sell": sell_score},
        "macd": {
            "dif": macd_val, "dea": signal_val, "histogram": hist_val,
            "histogram_prev": hist_prev, "golden_cross": macd_golden_cross,
            "death_cross": macd_death_cross, "hist_increasing": hist_increasing,
            "hist_decreasing": hist_decreasing, "hist_positive": hist_positive,
            "hist_negative": hist_negative
        },
        "stoch": {
            "k": stoch_k_val, "d": stoch_d_val,
            "golden_cross": stoch_golden_cross, "death_cross": stoch_death_cross
        },
        "rsi": rsi_val, "ema20": ema20_val, "ema50": ema50_val,
        "price": price, "volume_ratio": volume_ratio,
        "bullish_trend": bullish_trend, "bearish_trend": bearish_trend,
        "buy_score": buy_score, "sell_score": sell_score
    }

# =========================================================
# AUTO TRADE PLAN
# =========================================================
def generate_trade_plan(df, symbol, timeframe, account_balance=1000.0, risk_pct=2.0):
    if df is None or len(df) < 50:
        return None

    price = float(df["Close"].iloc[-1])
    atr_series = get_atr(df, 14)
    atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else price * 0.02
    if atr <= 0:
        atr = price * 0.02

    fib = get_fibonacci(df, lookback=100)
    buy_side, sell_side = get_liquidity_zones(df, lookback=100)
    supports, resistances = get_support_resistance(df, lookback=100)

    if not fib:
        return None

    fib_236 = fib.get(0.236); fib_382 = fib.get(0.382); fib_5 = fib.get(0.5)
    fib_618 = fib.get(0.618); fib_786 = fib.get(0.786)
    swing_high = fib.get("Swing High"); swing_low = fib.get("Swing Low")

    nearest_ssl = min([s for s in sell_side if s < price], key=lambda x: abs(price - x), default=None)
    nearest_bsl = min([b for b in buy_side if b > price], key=lambda x: abs(price - x), default=None)
    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None

    analysis = analyze_macd_stoch(df, timeframe)
    vol_ratio = analysis["volume_ratio"] if analysis else 1.0

    def make_wait(reason_text):
        return {
            "symbol": symbol, "timeframe": timeframe,
            "setup_type": "WAIT", "setup_label": reason_text, "setup_class": "setup-wait",
            "confidence": 0, "entry": price, "stop_loss": price,
            "tp1": price, "tp2": price, "tp3": price, "rr": 0,
            "reasons": [f"⚠️ {reason_text}"],
            "invalidations": ["Tidak ada setup valid = tidak entry"],
            "atr": atr, "price": price,
            "dip_level": fib_618, "breakout_level": nearest_resistance,
            "liq_level": nearest_ssl, "alternatives": [],
            "account_balance": account_balance, "risk_pct": risk_pct,
            "max_loss_usd": 0, "units": 0, "position_usd": 0, "profit_tp2_usd": 0,
            "fib": fib, "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "signal_type": "WAIT", "signal_strength": 0
        }

    if vol_ratio < 0.5:
        return make_wait(f"WAIT — Volume terlalu rendah ({vol_ratio:.2f}x)")

    setup_type = "WAIT"; setup_label = "⏳ WAIT (no clear setup)"; setup_class = "setup-wait"
    entry = sl = tp1 = tp2 = tp3 = None
    reasons = []
    invalidations = []
    dip_fib_level = None

    near = lambda a, b, pct=1.5: a is not None and b is not None and abs(a - b) / b * 100 < pct

    # Setup A: BUY THE DIP
    dip_level = None
    if fib_618 and abs(price - fib_618) / fib_618 * 100 < 5:
        dip_level = fib_618
        dip_fib_level = "0.618"
    elif fib_5 and abs(price - fib_5) / fib_5 * 100 < 3:
        dip_level = fib_5
        dip_fib_level = "0.500"

    # Setup B: BREAKOUT
    breakout_level = None
    if nearest_resistance and price > nearest_resistance * 0.998:
        breakout_level = nearest_resistance
    elif swing_high and price > swing_high * 0.998:
        breakout_level = swing_high

    # Setup C: LIQUIDITY GRAB
    liq_level = None
    if nearest_ssl and abs(price - nearest_ssl) / nearest_ssl * 100 < 2:
        liq_level = nearest_ssl

    # PRIORITAS SETUP
    if dip_level:
        if analysis and analysis["macd"]["dif"] < analysis["macd"]["dea"] * 0.98:
            return make_wait("WAIT — Harga di Fib dip tapi MACD masih bearish")
        setup_type = "BUY_THE_DIP"
        setup_label = f"🅰️ BUY THE DIP (Fib {dip_fib_level})"
        setup_class = "setup-dip"
        entry = dip_level
        sl_candidate = min(fib_786, nearest_ssl) if fib_786 and nearest_ssl else (fib_786 or price - 2 * atr)
        sl = sl_candidate * 0.997
        risk = entry - sl
        tp1 = fib_382 if (fib_382 and fib_382 > entry * 1.005) else entry + risk * 1.5
        tp2 = fib_236 if (fib_236 and fib_236 > entry * 1.005) else entry + risk * 2.5
        tp3 = swing_high if (swing_high and swing_high > entry * 1.005) else entry + risk * 4.0
        reasons.append(f"✅ Harga dekat Fib retracement {dip_fib_level} (${dip_level:.6f})")
        if fib_618 and fib_5:
            reasons.append(f"📐 Range: ${swing_high:.6f} − ${swing_low:.6f}")
            reasons.append(f"📐 Fib 0.618 = ${fib_618:.6f} | Fib 0.5 = ${fib_5:.6f}")

    elif breakout_level:
        setup_type = "BREAKOUT"
        setup_label = f"🅱️ BREAKOUT BUY (R ${breakout_level:.6f})"
        setup_class = "setup-breakout"
        entry = breakout_level * 1.002
        sl = max(entry - 2 * atr, (fib_236 or entry - 2 * atr))
        if sl >= entry:
            return make_wait("WAIT — SL tidak valid untuk breakout")
        risk = entry - sl
        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 4.0
        reasons.append(f"✅ Breakout di atas resistance (${breakout_level:.6f})")

    elif liq_level:
        if analysis and analysis["macd"]["dif"] < analysis["macd"]["dea"]:
            return make_wait("WAIT — SSL sweep tapi MACD masih bearish")
        setup_type = "LIQUIDITY_GRAB"
        setup_label = f"🅲 LIQUIDITY GRAB (SSL ${liq_level:.6f})"
        setup_class = "setup-liq"
        entry = liq_level * 1.001
        sl = (sell_side[1] * 0.998) if len(sell_side) > 1 else (entry - 2 * atr)
        risk = entry - sl
        tp1 = fib_5 if (fib_5 and fib_5 > entry * 1.005) else entry + risk * 1.5
        tp2 = fib_382 if (fib_382 and fib_382 > entry * 1.005) else entry + risk * 2.5
        tp3 = fib_236 if (fib_236 and fib_236 > entry * 1.005) else entry + risk * 4.0
        reasons.append(f"✅ Harga sweep SSL (${liq_level:.6f})")

    else:
        return {
            "symbol": symbol, "timeframe": timeframe,
            "setup_type": "WAIT", "setup_label": setup_label, "setup_class": setup_class,
            "confidence": 0, "entry": price, "stop_loss": price,
            "tp1": price, "tp2": price, "tp3": price, "rr": 0,
            "reasons": ["⚠️ Tidak ada setup jelas — harga di tengah range",
                        f"Harga: ${price:.6f}",
                        f"Tunggu pullback ke ${fib_618:.6f}" if fib_618 else "",
                        f"Atau breakout di atas ${nearest_resistance:.6f}" if nearest_resistance else ""],
            "invalidations": ["Tidak ada setup = tidak entry"],
            "atr": atr, "price": price,
            "dip_level": fib_618, "breakout_level": nearest_resistance,
            "liq_level": nearest_ssl, "alternatives": [],
            "account_balance": account_balance, "risk_pct": risk_pct,
            "max_loss_usd": 0, "units": 0, "position_usd": 0, "profit_tp2_usd": 0,
            "fib": fib, "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "signal_type": "WAIT", "signal_strength": 0
        }

    if not entry or not sl or sl >= entry:
        return make_wait("WAIT — Setup tidak valid (SL >= entry)")

    sl_dist_pct = abs(entry - sl) / entry * 100
    if sl_dist_pct > 8:
        return make_wait(f"WAIT — SL terlalu jauh ({sl_dist_pct:.1f}%)")

    if tp1 <= entry or tp2 <= entry or tp3 <= entry:
        return make_wait("WAIT — TP tidak valid arah")

    risk = entry - sl
    if risk <= 0:
        return make_wait("WAIT — Risk <= 0")
    rr = (tp2 - entry) / risk

    if rr < 1.5:
        return make_wait(f"WAIT — RR terlalu rendah (1:{rr:.2f}, minimal 1:1.5)")

    confidence = 0
    if analysis:
        if analysis["macd"]["dif"] > analysis["macd"]["dea"]:
            confidence += 1; reasons.append("✅ MACD bullish (DIF > DEA)")
        elif analysis["macd"]["hist_increasing"]:
            confidence += 0.5; reasons.append("🟡 MACD histogram mulai naik")
        if analysis["stoch"]["k"] < 30 and analysis["stoch"]["k"] > analysis["stoch"]["d"]:
            confidence += 1; reasons.append(f"✅ Stoch oversold + cross up (K={analysis['stoch']['k']:.1f})")
        elif analysis["stoch"]["k"] < 50 and analysis["stoch"]["k"] > analysis["stoch"]["d"]:
            confidence += 0.5; reasons.append(f"🟡 Stoch bullish (K={analysis['stoch']['k']:.1f})")
        if analysis["volume_ratio"] > 1.2:
            confidence += 1; reasons.append(f"✅ Volume konfirmasi (RVOL {analysis['volume_ratio']:.2f}x)")
        else:
            reasons.append(f"⚠️ Volume rendah (RVOL {analysis['volume_ratio']:.2f}x)")

    if nearest_ssl and near(entry, nearest_ssl, 2):
        confidence += 1; reasons.append(f"✅ Entry konfluen dengan SSL (${nearest_ssl:.6f})")
    if fib_618 and near(entry, fib_618, 2):
        confidence += 0.5; reasons.append("✅ Entry di Fib 0.618 (golden ratio)")

    confidence_int = min(5, int(round(confidence)))

    invalidations.append(f"❌ Batal jika harga close < ${sl:.6f} ({timeframe})")
    if analysis:
        invalidations.append(f"❌ Batal jika MACD death cross di {timeframe}")
        invalidations.append(f"❌ Batal jika Stoch K > 80 tanpa momentum")

    # Alternatif
    alternatives = []
    if setup_type != "BUY_THE_DIP" and fib_618 and fib_618 < price:
        alt_sl = (fib_786 * 0.997) if fib_786 else (fib_618 - 2 * atr)
        alt_risk = fib_618 - alt_sl
        if alt_risk > 0:
            alternatives.append({
                "name": "🅰️ LIMIT BUY (tunggu pullback)",
                "entry": fib_618, "sl": alt_sl,
                "tp": fib_382 if (fib_382 and fib_382 > fib_618) else fib_618 + alt_risk * 2,
                "rr": ((fib_382 - fib_618) / alt_risk) if (fib_382 and fib_382 > fib_618) else 2.0,
                "note": f"Tunggu harga turun ke Fib 0.618 (${fib_618:.6f})"
            })

    if setup_type != "BREAKOUT" and nearest_resistance and nearest_resistance > price:
        bo_entry = nearest_resistance * 1.002
        bo_sl = max(bo_entry - 2 * atr, (fib_236 or bo_entry - 2 * atr))
        bo_risk = bo_entry - bo_sl
        if bo_risk > 0:
            alternatives.append({
                "name": "🅱️ BREAKOUT BUY",
                "entry": bo_entry, "sl": bo_sl,
                "tp": bo_entry + bo_risk * 2.5, "rr": 2.5,
                "note": f"Tunggu tembus resistance ${nearest_resistance:.6f} dengan volume"
            })

    if nearest_ssl and nearest_ssl < price:
        sc_entry = nearest_ssl * 1.001
        sc_sl = (sell_side[1] * 0.998) if len(sell_side) > 1 else (sc_entry - 1.5 * atr)
        sc_risk = sc_entry - sc_sl
        if sc_risk > 0 and fib_5 and fib_5 > sc_entry:
            alternatives.append({
                "name": "🅲 SCALP BUY (di SSL)",
                "entry": sc_entry, "sl": sc_sl, "tp": fib_5,
                "rr": (fib_5 - sc_entry) / sc_risk,
                "note": f"Entry di SSL ${nearest_ssl:.6f}, target Fib 0.5 ${fib_5:.6f}"
            })

    max_loss_usd = account_balance * (risk_pct / 100)
    risk_per_unit = entry - sl
    units = max_loss_usd / risk_per_unit if risk_per_unit > 0 else 0
    position_usd = units * entry
    profit_tp2_usd = units * (tp2 - entry)

    if setup_type in ["BUY_THE_DIP", "BREAKOUT", "LIQUIDITY_GRAB"]:
        if confidence_int >= 4:
            signal_type = "⭐ STRONG BUY"
            signal_strength = 3
        elif confidence_int >= 3:
            signal_type = "⭐⭐ BUY"
            signal_strength = 2
        else:
            signal_type = "⭐ WEAK BUY"
            signal_strength = 1

    return {
        "symbol": symbol, "timeframe": timeframe,
        "setup_type": setup_type, "setup_label": setup_label, "setup_class": setup_class,
        "confidence": confidence_int,
        "entry": float(entry), "stop_loss": float(sl),
        "tp1": float(tp1), "tp2": float(tp2), "tp3": float(tp3),
        "rr": float(rr),
        "reasons": [r for r in reasons if r],
        "invalidations": invalidations,
        "atr": atr, "price": price,
        "dip_level": dip_level if dip_level else fib_618,
        "dip_fib_level": dip_fib_level,
        "breakout_level": nearest_resistance,
        "liq_level": nearest_ssl,
        "alternatives": alternatives,
        "account_balance": account_balance, "risk_pct": risk_pct,
        "max_loss_usd": max_loss_usd, "units": units,
        "position_usd": position_usd, "profit_tp2_usd": profit_tp2_usd,
        "fib": fib, "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "signal_type": signal_type, "signal_strength": signal_strength,
        "swing_high": swing_high, "swing_low": swing_low,
    }

# =========================================================
# MTF SYNCED
# =========================================================
def analyze_mtf_synced(symbol, timeframes=["15m", "1h", "4h"]):
    results = {}
    for tf in timeframes:
        df = get_data_safe(symbol, tf, min_candles=80)
        if df is None:
            continue
        plan = generate_trade_plan(df, symbol, tf)
        analysis = analyze_macd_stoch(df, tf)
        if plan is None or analysis is None:
            continue
        results[tf] = {"plan": plan, "analysis": analysis, "df": df}

    if not results:
        return None

    combined = {"symbol": symbol, "timeframes": results}

    buy_count = 0; sell_count = 0; wait_count = 0
    for tf in ["4h", "1h", "15m"]:
        if tf in results:
            plan = results[tf]["plan"]
            st_type = plan["setup_type"]
            if st_type in ["BUY_THE_DIP", "BREAKOUT", "LIQUIDITY_GRAB"]:
                buy_count += 1
            elif st_type == "WAIT":
                wait_count += 1

    if buy_count >= 2:
        main_signal = "🟢 STRONG BUY (Multi TF)"
        main_strength = 3
    elif buy_count == 1 and wait_count >= 1:
        main_signal = "🟢 BUY"
        main_strength = 2
    elif sell_count >= 2:
        main_signal = "🔴 STRONG SELL (Multi TF)"
        main_strength = 3
    else:
        main_signal = "🟡 HOLD / WAIT"
        main_strength = 1

    best_plan = None
    best_conf = -1
    for tf in ["4h", "1h", "15m"]:
        if tf in results:
            p = results[tf]["plan"]
            if p["confidence"] > best_conf and p["setup_type"] != "WAIT":
                best_conf = p["confidence"]
                best_plan = p

    combined.update({
        "main_signal": main_signal, "main_strength": main_strength,
        "buy_count": buy_count, "sell_count": sell_count, "wait_count": wait_count,
        "best_plan": best_plan,
        "total_score": 50 + (buy_count * 12) if buy_count > 0 else 50,
        "confirmations": buy_count + sell_count,
    })
    return combined

# =========================================================
# FORMAT PLAN TELEGRAM — VERSI DETAIL
# =========================================================
def format_plan_for_telegram(plan):
    """Format Auto Trade Plan untuk Telegram — versi aman (escape HTML)."""
    def esc(s):
        return html.escape(str(s))

    entry = plan["entry"]
    sl = plan["stop_loss"]
    tp1 = plan["tp1"]; tp2 = plan["tp2"]; tp3 = plan["tp3"]
    setup_type = plan["setup_type"]

    sl_pct = (sl / entry - 1) * 100
    tp1_pct = (tp1 / entry - 1) * 100
    tp2_pct = (tp2 / entry - 1) * 100
    tp3_pct = (tp3 / entry - 1) * 100

    txt = f"🎯 <b>AUTO TRADE PLAN</b>\n"
    txt += f"━━━━━━━━━━━━━━━━━━━━━\n\n"
    txt += f"<b>{esc(plan['symbol'])}</b> · {esc(plan['timeframe'])}\n"
    txt += f"{esc(plan['setup_label'])}\n"
    txt += f"Confidence: {'⭐' * plan['confidence']} ({plan['confidence']}/5)\n\n"

    if setup_type == "BUY_THE_DIP":
        fib = plan.get("fib", {})
        fib_618 = fib.get(0.618, 0)
        fib_5 = fib.get(0.5, 0)
        swing_high = plan.get("swing_high", 0) or fib.get("Swing High", 0)
        swing_low = plan.get("swing_low", 0) or fib.get("Swing Low", 0)
        dip_lvl = plan.get("dip_fib_level", "0.618")

        txt += f"📐 <b>FIBONACCI SETUP</b>\n"
        txt += f"Swing High: ${swing_high:.6f}\n"
        txt += f"Swing Low:  ${swing_low:.6f}\n"
        txt += f"Fib 0.5:    ${fib_5:.6f}\n"
        txt += f"Fib 0.618:  ${fib_618:.6f}\n"
        txt += f"→ Entry di Fib {esc(dip_lvl)}: <b>${entry:.6f}</b>\n\n"

    elif setup_type == "LIQUIDITY_GRAB":
        ssl = plan.get("liq_level", 0)
        txt += f"💧 <b>LIQUIDITY GRAB (SSL Sweep)</b>\n"
        txt += f"SSL Level: <b>${ssl:.6f}</b>\n"
        txt += f"→ Harga sweep SSL, potensi bounce\n\n"

    elif setup_type == "BREAKOUT":
        res = plan.get("breakout_level", 0)
        txt += f"🚀 <b>BREAKOUT SETUP</b>\n"
        txt += f"Resistance: <b>${res:.6f}</b>\n"
        txt += f"→ Harga tembus resistance\n\n"

    txt += f"📊 <b>LEVEL TRADING</b>\n"
    txt += f"🎯 Entry: <b>${entry:.6f}</b>\n"
    txt += f"🛑 SL:    <b>${sl:.6f}</b> ({sl_pct:+.2f}%)\n"
    txt += f"🥇 TP1:   <b>${tp1:.6f}</b> ({tp1_pct:+.2f}%)\n"
    txt += f"🥈 TP2:   <b>${tp2:.6f}</b> ({tp2_pct:+.2f}%)\n"
    txt += f"🥉 TP3:   <b>${tp3:.6f}</b> ({tp3_pct:+.2f}%)\n"
    txt += f"📊 R:R:   1 : {plan['rr']:.2f}\n\n"

    txt += f"💰 <b>POSITION SIZING</b>\n"
    txt += f"Modal: ${plan['account_balance']:.2f}\n"
    txt += f"Risk: {plan['risk_pct']:.1f}% = ${plan['max_loss_usd']:.2f}\n"
    txt += f"Position: <b>${plan['position_usd']:.2f}</b>\n"
    txt += f"Units: <b>{plan['units']:.6f}</b>\n\n"

    txt += f"🧠 <b>ALASAN:</b>\n"
    for r in plan['reasons'][:6]:
        txt += f"{esc(r)}\n"
    txt += "\n"

    txt += f"⚠️ <b>INVALIDASI:</b>\n"
    for i in plan['invalidations'][:3]:
        txt += f"{esc(i)}\n"
    txt += "\n"

    if plan.get("alternatives"):
        txt += f"📋 <b>SKENARIO ALTERNATIF:</b>\n"
        for alt in plan['alternatives'][:2]:
            txt += f"• {esc(alt['name'])}\n"
            txt += f"  Entry: ${alt['entry']:.6f}\n"
            txt += f"  SL: ${alt['sl']:.6f} · TP: ${alt['tp']:.6f}\n"
            txt += f"  R:R 1:{alt['rr']:.2f}\n"
        txt += "\n"

    txt += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # Potong kalau terlalu panjang
    if len(txt) > 4000:
        txt = txt[:3900] + "\n\n[...dipotong...]"

    return txt

# =========================================================
# CHART
# =========================================================
def create_chart(df, symbol, timeframe, plan=None,
                 show_fib=True, show_liquidity=True, show_sr=True, show_plan=True):
    if df is None or len(df) < 30:
        return None

    macd_line, signal_line, histogram = MACD(df)
    stoch_k, stoch_d, rsi = StochasticRSI(df)
    ema20 = EMA(df, 20); ema50 = EMA(df, 50)

    fib = get_fibonacci(df, lookback=100) if show_fib else {}
    buy_side, sell_side = get_liquidity_zones(df, lookback=100) if show_liquidity else ([], [])
    sr_support, sr_resistance = get_support_resistance(df, lookback=100) if show_sr else ([], [])

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.35, 0.2, 0.25, 0.2],
        subplot_titles=(f"Price - {symbol} {timeframe}", "RSI", "MACD", "Stochastic RSI")
    )

    fig.add_trace(go.Candlestick(
        x=df["Time"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        increasing_line_color="#00ff88", decreasing_line_color="#ff3b5c", name="Price"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=ema20,
        line=dict(color="#00a2ff", width=1.5), name="EMA20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=ema50,
        line=dict(color="#ffaa00", width=1.5, dash="dash"), name="EMA50"), row=1, col=1)

    if show_fib and fib:
        fib_colors = {0.236: "rgba(255,255,255,0.35)", 0.382: "rgba(255,215,0,0.55)",
                      0.5: "rgba(255,140,0,0.55)", 0.618: "rgba(0,200,255,0.65)",
                      0.786: "rgba(168,85,247,0.65)"}
        for level, price_lvl in fib.items():
            if isinstance(level, str):
                fig.add_hline(y=price_lvl, line_dash="dot",
                    line_color="rgba(148,163,184,0.5)", line_width=1,
                    annotation_text=f"  Fib {level}", annotation_position="right",
                    annotation_font=dict(size=9, color="#94a3b8"), row=1, col=1)
            else:
                color = fib_colors.get(level, "rgba(255,255,255,0.3)")
                fig.add_hline(y=price_lvl, line_dash="dash", line_color=color, line_width=1,
                    annotation_text=f"  Fib {level:.3f}", annotation_position="right",
                    annotation_font=dict(size=9, color=color), row=1, col=1)

    if show_liquidity:
        for lvl in buy_side[:3]:
            fig.add_hline(y=lvl, line_dash="solid", line_color="rgba(0,255,136,0.35)", line_width=1,
                annotation_text="  💧 BSL", annotation_position="left",
                annotation_font=dict(size=9, color="#00ff88"), row=1, col=1)
            fig.add_hrect(y0=lvl*0.998, y1=lvl*1.002,
                fillcolor="rgba(0,255,136,0.06)", line_width=0, row=1, col=1)
        for lvl in sell_side[:3]:
            fig.add_hline(y=lvl, line_dash="solid", line_color="rgba(255,59,92,0.35)", line_width=1,
                annotation_text="  💧 SSL", annotation_position="left",
                annotation_font=dict(size=9, color="#ff3b5c"), row=1, col=1)
            fig.add_hrect(y0=lvl*0.998, y1=lvl*1.002,
                fillcolor="rgba(255,59,92,0.06)", line_width=0, row=1, col=1)

    if show_sr:
        for lvl in sr_resistance[:2]:
            fig.add_hline(y=lvl, line_dash="longdash", line_color="rgba(255,100,100,0.45)", line_width=1.2,
                annotation_text=f"  R {format_price(lvl)}", annotation_position="right",
                annotation_font=dict(size=9, color="#ff6464"), row=1, col=1)
        for lvl in sr_support[:2]:
            fig.add_hline(y=lvl, line_dash="longdash", line_color="rgba(100,255,100,0.45)", line_width=1.2,
                annotation_text=f"  S {format_price(lvl)}", annotation_position="right",
                annotation_font=dict(size=9, color="#64ff64"), row=1, col=1)

    if show_plan and plan and plan.get("setup_type") not in [None, "WAIT"]:
        entry = plan["entry"]; sl = plan["stop_loss"]
        tp1 = plan["tp1"]; tp2 = plan["tp2"]; tp3 = plan["tp3"]
        fig.add_hline(y=entry, line_dash="solid", line_color="#00c8ff", line_width=2,
            annotation_text=f"  🎯 ENTRY ${entry:.6f}", annotation_position="left",
            annotation_font=dict(size=11, color="#00c8ff"), row=1, col=1)
        fig.add_hline(y=sl, line_dash="solid", line_color="#ff3b5c", line_width=2,
            annotation_text=f"  🛑 SL ${sl:.6f}", annotation_position="left",
            annotation_font=dict(size=11, color="#ff3b5c"), row=1, col=1)
        for tp, label, col in [(tp1, "TP1", "#00ff88"), (tp2, "TP2", "#00ff88"), (tp3, "TP3", "#00ff88")]:
            fig.add_hline(y=tp, line_dash="dot", line_color=col, line_width=1.5,
                annotation_text=f"  🎯 {label} ${tp:.6f}", annotation_position="left",
                annotation_font=dict(size=10, color=col), row=1, col=1)
        fig.add_hrect(y0=min(entry, sl), y1=max(entry, sl),
            fillcolor="rgba(255,59,92,0.08)", line_width=0, row=1, col=1)
        fig.add_hrect(y0=min(entry, tp2), y1=max(entry, tp2),
            fillcolor="rgba(0,255,136,0.06)", line_width=0, row=1, col=1)

    fig.add_trace(go.Scatter(x=df["Time"], y=rsi,
        line=dict(color="#a855f7", width=2), name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.add_trace(go.Scatter(x=df["Time"], y=macd_line,
        line=dict(color="#00a2ff", width=1.5), name="DIF"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=signal_line,
        line=dict(color="#ff00ff", width=1.5), name="DEA"), row=3, col=1)
    colors = ["#00ff88" if h >= 0 else "#ff3b5c" for h in histogram]
    fig.add_trace(go.Bar(x=df["Time"], y=histogram,
        marker_color=colors, opacity=0.5, name="Histogram"), row=3, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.2)", row=3, col=1)

    fig.add_trace(go.Scatter(x=df["Time"], y=stoch_k,
        line=dict(color="#ffaa00", width=1.5), name="Stoch K"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=stoch_d,
        line=dict(color="#ff00ff", width=1.5, dash="dash"), name="Stoch D"), row=4, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=4, col=1)

    fig.update_layout(
        template="plotly_dark", height=900,
        title=dict(text=f"<b>{symbol} - {timeframe} Analysis</b>",
            font=dict(color="#f1f5f9", size=20), x=0.5, xanchor="center"),
        hovermode="x unified", dragmode="pan", xaxis_rangeslider_visible=False,
        paper_bgcolor="#0a0a1a", plot_bgcolor="#0a0a1a", font=dict(color="#94a3b8"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=10)),
        margin=dict(l=10, r=10, t=50, b=10)
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
    return fig

# =========================================================
# BACKTEST
# =========================================================
def backtest_trade_plan(df, symbol, horizon=20, min_conf=2):
    if df is None or len(df) < 250:
        return pd.DataFrame(), {}

    rows = []
    for i in range(150, len(df) - horizon - 1):
        window = df.iloc[:i+1]
        try:
            plan = generate_trade_plan(window, symbol, "backtest")
        except:
            continue
        if not plan or plan["setup_type"] == "WAIT" or plan["confidence"] < min_conf:
            continue
        entry = plan["entry"]; sl = plan["stop_loss"]; tp1 = plan["tp1"]
        future = df.iloc[i+1:i+1+horizon]
        if len(future) == 0:
            continue
        hit_tp1 = (future["High"] >= tp1).any()
        hit_sl = (future["Low"] <= sl).any()
        if hit_tp1 and hit_sl:
            outcome = "AMBIGUOUS"
        elif hit_tp1:
            outcome = "WIN"
        elif hit_sl:
            outcome = "LOSS"
        else:
            outcome = "OPEN"
        rows.append({
            "Date": df["Time"].iloc[i],
            "Setup": plan["setup_type"],
            "Conf": plan["confidence"],
            "Entry": entry, "SL": sl, "TP1": tp1,
            "RR": plan["rr"], "Outcome": outcome,
            "Max Gain %": (future["High"].max() / entry - 1) * 100,
            "Max DD %": (future["Low"].min() / entry - 1) * 100
        })

    bt = pd.DataFrame(rows)
    if bt.empty:
        return bt, {}
    valid = bt[bt.Outcome.isin(["WIN", "LOSS"])]
    stats = {
        "signals": len(bt),
        "wins": int((valid.Outcome == "WIN").sum()) if len(valid) else 0,
        "losses": int((valid.Outcome == "LOSS").sum()) if len(valid) else 0,
        "win_rate": float((valid.Outcome == "WIN").mean() * 100) if len(valid) else 0.0,
        "avg_gain": float(bt["Max Gain %"].mean()),
        "avg_dd": float(bt["Max DD %"].mean()),
    }
    return bt, stats

# =========================================================
# RENDER TRADE PLAN
# =========================================================
def render_trade_plan(plan, df, symbol, timeframe, account_balance, risk_pct):
    st.markdown(f"""
    <div class="plan-card">
        <div class="plan-header">🎯 AUTO TRADE PLAN — {symbol} · {timeframe}</div>
        <div style="color:#64748b;font-size:13px;margin-bottom:12px;">
            Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
        <span class="setup-badge {plan['setup_class']}">{plan['setup_label']}</span>
        <span class="plan-confidence" style="margin-left:10px;">
            {'⭐' * plan['confidence']} ({plan['confidence']}/5)
        </span>
    </div>
    """, unsafe_allow_html=True)

    if plan["setup_type"] == "WAIT":
        st.warning("⏳ " + " | ".join(plan["reasons"]))
        if plan.get("dip_level"):
            st.info(f"💡 Tunggu pullback ke **${plan['dip_level']:.6f}** "
                    f"atau breakout di atas **${plan.get('breakout_level') or 0:.6f}**")
        return

    entry = plan["entry"]; sl = plan["stop_loss"]
    tp1 = plan["tp1"]; tp2 = plan["tp2"]; tp3 = plan["tp3"]
    def pct(a, b): return (a / b - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">📈 Entry</div>
            <div class="level-value">${entry:.6f}</div>
            <div class="level-pct">Limit / Market</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">🛑 Stop Loss</div>
            <div class="level-value">${sl:.6f}</div>
            <div class="level-pct neg">{pct(sl, entry):+.2f}%</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">🎯 TP1</div>
            <div class="level-value">${tp1:.6f}</div>
            <div class="level-pct pos">{pct(tp1, entry):+.2f}%</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">🎯 TP2</div>
            <div class="level-value">${tp2:.6f}</div>
            <div class="level-pct pos">{pct(tp2, entry):+.2f}%</div></div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">🎯 TP3</div>
            <div class="level-value">${tp3:.6f}</div>
            <div class="level-pct pos">{pct(tp3, entry):+.2f}%</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">📊 Risk/Reward</div>
            <div class="level-value">1 : {plan['rr']:.2f}</div>
            <div class="level-pct">{'✅ GOOD' if plan['rr'] >= 2 else '⚠️ LOW' if plan['rr'] >= 1.5 else '❌ BAD'}</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">💰 Position Size</div>
            <div class="level-value">${plan['position_usd']:.2f}</div>
            <div class="level-pct">{plan['units']:.4f} unit</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="level-box">
            <div class="level-label">💵 Max Loss</div>
            <div class="level-value">${plan['max_loss_usd']:.2f}</div>
            <div class="level-pct neg">{plan['risk_pct']:.1f}% modal</div></div>""", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### 🧠 Alasan (Why this setup)")
        for r in plan["reasons"]:
            st.markdown(f"<div class='reason-item'>{r}</div>", unsafe_allow_html=True)
    with col_b:
        st.markdown("##### ⚠️ Invalidasi (Batal jika)")
        for i in plan["invalidations"]:
            st.markdown(f"<div class='reason-item'>{i}</div>", unsafe_allow_html=True)

    if plan.get("alternatives"):
        st.markdown("##### 📋 Skenario Alternatif")
        for alt in plan["alternatives"]:
            with st.expander(f"{alt['name']} — R:R 1:{alt['rr']:.2f}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Entry", f"${alt['entry']:.6f}")
                c2.metric("SL", f"${alt['sl']:.6f}")
                c3.metric("TP", f"${alt['tp']:.6f}")
                st.caption(alt["note"])

    st.markdown("---")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("📱 Kirim Plan ke Telegram", use_container_width=True, key="btn_tg_plan"):
            if send_telegram_plan(format_plan_for_telegram(plan)):
                st.success("✅ Plan terkirim!")
            else:
                st.error("❌ Gagal kirim.")
    with b2:
        if st.button("💾 Simpan ke Database", use_container_width=True, key="btn_save_plan"):
            if save_trade_plan(plan):
                st.success("✅ Plan tersimpan!")
            else:
                st.error("❌ Gagal simpan.")
    with b3:
        plan_txt = format_plan_for_telegram(plan).replace("<b>", "").replace("</b>", "")
        st.download_button("📋 Download Plan (TXT)", plan_txt,
                           file_name=f"plan_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                           mime="text/plain", use_container_width=True)

# =========================================================
# INITIALIZATION
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()
if "pending_signal" not in st.session_state:
    st.session_state.pending_signal = {}
else:
    # Auto-migrate: hapus struktur lama yang tidak lengkap
    for sym in list(st.session_state.pending_signal.keys()):
        d = st.session_state.pending_signal[sym]
        if not isinstance(d, dict) or "tp1" not in d or "tp2" not in d:
            del st.session_state.pending_signal[sym]
if "performance_stats" not in st.session_state:
    st.session_state.performance_stats = get_performance()

# =========================================================
# MAIN TITLE
# =========================================================
st.title("🤖 Crypto Signal Pro")
st.caption("Multi Timeframe + MACD + Stochastic RSI + Fibonacci + Liquidity + Auto Trade Plan")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    st.subheader("📋 Watchlist")
    st.success("☁️ Supabase Connected")

    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_coin = st.text_input("Add Coin", placeholder="BTC", label_visibility="collapsed")
    with col_add2:
        if st.button("➕", use_container_width=True):
            if new_coin:
                coin = new_coin.upper().strip()
                if coin not in st.session_state.watchlist:
                    if add_coin(coin):
                        st.session_state.watchlist.append(coin)
                        st.rerun()

    st.markdown("**Your Coins:**")
    cols = st.columns(3)
    for idx, coin in enumerate(st.session_state.watchlist):
        col_idx = idx % 3
        with cols[col_idx]:
            if st.button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
                if remove_coin(coin):
                    st.session_state.watchlist.remove(coin)
                    st.rerun()

    st.divider()
    st.subheader("💰 Position Sizing")
    account_balance = st.number_input("Modal ($)", min_value=10.0, value=1000.0, step=100.0)
    risk_pct = st.slider("Risk per trade (%)", 0.5, 5.0, 2.0, 0.5)
    st.caption(f"Max loss per trade: **${account_balance * risk_pct / 100:.2f}**")

    st.divider()
    st.subheader("📊 Trading Settings")
    refresh = st.slider("🔄 Refresh (detik)", 10, 60, 30)
    hold_minutes = st.slider("Hold Signal (menit)", 5, 30, 15)

    st.divider()
    st.subheader("📱 Telegram")
    if st.button("🚀 Test Telegram", use_container_width=True):
        test_msg = (
            "🤖 <b>Crypto Signal Pro</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ <b>Koneksi Berhasil!</b>\n\n"
            "Sistem siap mengirim notifikasi:\n"
            "• 🎯 Auto Trade Plan\n"
            "• 📊 Signal Multi-TF\n"
            "• 🚨 Alert Setup Valid\n\n"
            "📈 Format pesan:\n"
            "  - Setup detail (Fib/SSL/BO)\n"
            "  - Entry, SL, TP1-3\n"
            "  - RR & Position Sizing\n"
            "  - Alasan & Invalidasi\n"
            "  - Skenario Alternatif\n\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if send_telegram_plan(test_msg):
            st.success("✅ Test terkirim!")
        else:
            st.error("❌ Gagal. Cek token/chat ID.")

    st.divider()
    st.subheader("📊 Status")
    st.metric("Total Coins", len(st.session_state.watchlist))
    stats = get_performance()
    st.metric("Total Signals", stats.get('total_signals', 0))

# =========================================================
# AUTO REFRESH
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Scanner", "📈 Chart + Plan", "🧪 Backtest", "📋 History", "📊 Performance"
])

# ==================== TAB 1: SCANNER ====================
with tab1:
    st.subheader("📊 Signal Scanner — Synced with Chart")
    st.caption("Signal berdasarkan Auto Trade Plan yang sama dengan Tab Chart")

    all_signals = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    current_time = datetime.now()
    expired = []
    for symbol, data in st.session_state.pending_signal.items():
        elapsed = (current_time - data["time"]).seconds / 60
        if elapsed > hold_minutes:
            expired.append(symbol)
    for sym in expired:
        del st.session_state.pending_signal[sym]

    scan_list = st.session_state.watchlist[:50]

    for idx, symbol in enumerate(scan_list):
        progress_bar.progress((idx + 1) / len(scan_list))
        status_text.text(f"🔄 Scanning {symbol}...")

        result = analyze_mtf_synced(symbol, ["15m", "1h", "4h"])
        if not result:
            continue

        best_plan = result.get("best_plan")

        signal_data = {
            "Coin": symbol,
            "Signal": result["main_signal"],
            "Strength": "⭐" * result.get("main_strength", 1),
            "Conf": f"{result.get('total_score', 50):.0f}",
        }

        for tf in ["15m", "1h", "4h"]:
            if tf in result["timeframes"]:
                tf_plan = result["timeframes"][tf]["plan"]
                tf_analysis = result["timeframes"][tf]["analysis"]
                setup_short = {
                    "BUY_THE_DIP": "🅰️ DIP",
                    "BREAKOUT": "🅱️ BO",
                    "LIQUIDITY_GRAB": "🅲 LIQ",
                    "WAIT": "⏳ WAIT"
                }.get(tf_plan["setup_type"], "⏳ WAIT")
                signal_data[f"{tf.upper()}"] = f"{setup_short} ({tf_plan['confidence']}⭐)"
                signal_data[f"{tf.upper()} RSI"] = f"{tf_analysis['rsi']:.1f}"
                signal_data[f"{tf.upper()} K"] = f"{tf_analysis['stoch']['k']:.1f}"

        if best_plan and best_plan["setup_type"] != "WAIT":
            signal_data["RR"] = f"1:{best_plan['rr']:.2f}"
        else:
            signal_data["RR"] = "-"

        all_signals.append(signal_data)

        # Simpan ke pending — dengan detail
        if (best_plan and best_plan["setup_type"] != "WAIT"
            and best_plan["confidence"] >= 2
            and best_plan["rr"] >= 1.5
            and symbol not in st.session_state.pending_signal):

            fib_data = best_plan.get("fib", {})
            dip_fib_level = best_plan.get("dip_fib_level") or "0.618"
            dip_fib_price = best_plan.get("dip_level", best_plan["entry"])
            swing_high = best_plan.get("swing_high", 0) or fib_data.get("Swing High", 0)
            swing_low = best_plan.get("swing_low", 0) or fib_data.get("Swing Low", 0)
            fib_range = swing_high - swing_low if swing_high and swing_low else 0

            st.session_state.pending_signal[symbol] = {
                "signal": best_plan["setup_label"],
                "time": datetime.now(),
                "setup_type": best_plan["setup_type"],
                "entry": best_plan["entry"],
                "sl": best_plan["stop_loss"],
                "tp1": best_plan["tp1"],
                "tp2": best_plan["tp2"],
                "tp3": best_plan["tp3"],
                "rr": best_plan["rr"],
                "timeframe": best_plan["timeframe"],
                "confidence": best_plan["confidence"],
                "current_price": best_plan["price"],
                "reasons": best_plan["reasons"],
                "invalidations": best_plan["invalidations"],
                # Detail setup
                "dip_fib_level": dip_fib_level,
                "dip_fib_price": dip_fib_price,
                "swing_high": swing_high,
                "swing_low": swing_low,
                "fib_range": fib_range,
                "breakout_resistance": best_plan.get("breakout_level", 0) or 0,
                "liq_ssl_price": best_plan.get("liq_level", 0) or 0,
            }

            # Kirim Telegram dengan format detail
            send_telegram_once(symbol, best_plan["setup_label"], best_plan)

    progress_bar.empty()
    status_text.empty()

    if all_signals:
        df_signals = pd.DataFrame(all_signals)
        col_order = ["Coin", "Signal", "Strength", "Conf", "RR",
                     "15M", "15M RSI", "15M K",
                     "1H", "1H RSI", "1H K",
                     "4H", "4H RSI", "4H K"]
        col_order = [c for c in col_order if c in df_signals.columns]
        df_signals = df_signals[col_order]
        st.dataframe(df_signals, use_container_width=True, hide_index=True)

        buy_signals = [s for s in all_signals if "BUY" in s["Signal"]]
        if buy_signals:
            st.success(f"🏆 {len(buy_signals)} buy signals found")
    else:
        st.info("ℹ️ Tidak ada data")

    # ===== PENDING SIGNALS — versi detail dengan angka setup =====
    if st.session_state.pending_signal:
        st.divider()
        st.subheader("⏳ Pending Signals (Valid Setup)")
        st.caption("Detail level setup — angka Fib / SSL / Resistance yang jadi dasar entry")

        pending_data = []
        for symbol, data in st.session_state.pending_signal.items():
            elapsed = (datetime.now() - data["time"]).seconds / 60
            remaining = max(0, hold_minutes - elapsed)

            entry = data.get("entry", 0)
            sl = data.get("sl", 0)
            tp1 = data.get("tp1", 0)
            tp2 = data.get("tp2", 0)
            rr = data.get("rr", 0)
            setup_type = data.get("setup_type", "")
            setup_label = data.get("signal", "-")
            confidence = data.get("confidence", 0)
            tf = data.get("timeframe", "-")
            current_price = data.get("current_price", entry)

            dist_pct = (entry - current_price) / current_price * 100 if current_price else 0
            if abs(dist_pct) < 0.5:
                dist_str = "🎯 AT ENTRY"
            elif dist_pct > 0:
                dist_str = f"⏳ {dist_pct:+.2f}% (tunggu naik)"
            else:
                dist_str = f"✅ {dist_pct:+.2f}%"

            # Angka setup
            if setup_type == "BUY_THE_DIP":
                fib_level = data.get("dip_fib_level", "0.618")
                fib_price = data.get("dip_fib_price", entry)
                reason = f"📐 Fib {fib_level} = {format_price(fib_price)}"
                setup_angka = f"Fib {fib_level} = {format_price(fib_price)}"
            elif setup_type == "BREAKOUT":
                res_level = data.get("breakout_resistance", entry)
                reason = f"🚀 Tembus R {format_price(res_level)}"
                setup_angka = f"R = {format_price(res_level)}"
            elif setup_type == "LIQUIDITY_GRAB":
                ssl_level = data.get("liq_ssl_price", entry)
                reason = f"💧 SSL sweep {format_price(ssl_level)}"
                setup_angka = f"SSL = {format_price(ssl_level)}"
            else:
                reason = "-"
                setup_angka = "-"

            pending_data.append({
                "Coin": symbol,
                "Setup": setup_label,
                "Angka Setup": setup_angka,
                "TF": tf,
                "Conf": f"{confidence}⭐",
                "Current": format_price(current_price),
                "Entry": format_price(entry),
                "Jarak": dist_str,
                "SL": format_price(sl),
                "TP1": format_price(tp1),
                "TP2": format_price(tp2),
                "RR": f"1:{rr:.2f}",
                "Alasan": reason,
                "Left": f"{remaining:.0f}m"
            })

        if pending_data:
            df_pending = pd.DataFrame(pending_data)
            st.dataframe(df_pending, use_container_width=True, hide_index=True)

            # Detail expander per coin
            st.markdown("### 📋 Detail Setup per Coin")
            for symbol, data in st.session_state.pending_signal.items():
                setup_type = data.get("setup_type", "")
                setup_label = data.get("signal", "-")
                confidence = data.get("confidence", 0)
                tf = data.get("timeframe", "-")
                entry = data.get("entry", 0)
                sl = data.get("sl", 0)
                tp1 = data.get("tp1", 0)
                tp2 = data.get("tp2", 0)
                tp3 = data.get("tp3", 0)
                rr = data.get("rr", 0)
                current = data.get("current_price", entry)

                with st.expander(f"**{symbol}** — {setup_label} ({confidence}⭐, {tf})", expanded=False):

                    st.markdown("##### 🎯 Level Setup (Angka Referensi)")

                    if setup_type == "BUY_THE_DIP":
                        fib_level = data.get("dip_fib_level", "0.618")
                        fib_price = data.get("dip_fib_price", entry)
                        swing_high = data.get("swing_high", 0)
                        swing_low = data.get("swing_low", 0)
                        fib_range = data.get("fib_range", 0)

                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Fib Level", str(fib_level))
                        col2.metric("Fib Price", format_price(fib_price))
                        col3.metric("Swing High", format_price(swing_high))
                        col4.metric("Swing Low", format_price(swing_low))
                        st.caption(f"📐 **Perhitungan Fib {fib_level}:**")
                        st.caption(f"    Range: {format_price(swing_high)} − {format_price(swing_low)} = {format_price(fib_range)}")
                        try:
                            fib_num = float(fib_level)
                            st.caption(f"    Fib {fib_level}: {format_price(swing_high)} − ({format_price(fib_range)} × {fib_level}) = **{format_price(fib_price)}**")
                        except:
                            pass

                    elif setup_type == "BREAKOUT":
                        res_level = data.get("breakout_resistance", entry)
                        st.metric("Resistance Level", format_price(res_level))
                        st.caption(f"🚀 **Breakout:** Harga tembus resistance {format_price(res_level)}")

                    elif setup_type == "LIQUIDITY_GRAB":
                        ssl_price = data.get("liq_ssl_price", entry)
                        st.metric("SSL Level", format_price(ssl_price))
                        st.caption(f"💧 **Liquidity Grab:** Harga sweep SSL di {format_price(ssl_price)}")

                    st.markdown("##### 📊 Level Trading")
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    c1.metric("Current", format_price(current))
                    c2.metric("Entry", format_price(entry))
                    c3.metric("SL", format_price(sl), f"{(sl/entry-1)*100:+.2f}%")
                    c4.metric("TP1", format_price(tp1), f"{(tp1/entry-1)*100:+.2f}%")
                    c5.metric("TP2", format_price(tp2), f"{(tp2/entry-1)*100:+.2f}%")
                    c6.metric("TP3", format_price(tp3), f"{(tp3/entry-1)*100:+.2f}%")

                    st.markdown("##### 🧠 Alasan (Why this setup)")
                    reasons = data.get("reasons", [])
                    if reasons:
                        for r in reasons:
                            st.markdown(f"- {r}")

                    st.markdown("##### ⚠️ Invalidasi (Batal jika)")
                    invalidations = data.get("invalidations", [])
                    if invalidations:
                        for inv in invalidations:
                            st.markdown(f"- {inv}")
                    else:
                        st.markdown(f"- Harga close di bawah SL {format_price(sl)}")

# ==================== TAB 2: CHART + PLAN ====================
with tab2:
    st.subheader("📈 Chart Analysis + 🎯 Auto Trade Plan")
    chart_coin = st.selectbox("Select Coin", st.session_state.watchlist, key="chart_select")
    chart_tf = st.selectbox("Timeframe", ["15m", "1h", "4h"], index=1, key="chart_tf")

    tog1, tog2, tog3, tog4 = st.columns(4)
    with tog1: show_fib = st.toggle("📐 Fibonacci", value=True, key="tog_fib")
    with tog2: show_liq = st.toggle("💧 Liquidity", value=True, key="tog_liq")
    with tog3: show_sr = st.toggle("📏 S/R", value=True, key="tog_sr")
    with tog4: show_plan_overlay = st.toggle("🎯 Plan Overlay", value=True, key="tog_plan")

    if chart_coin:
        df = get_data_safe(chart_coin, chart_tf, min_candles=100)
        if df is not None:
            result = analyze_macd_stoch(df, chart_tf)
            plan = generate_trade_plan(df, chart_coin, chart_tf,
                                        account_balance=account_balance,
                                        risk_pct=risk_pct)

            fig = create_chart(df, chart_coin, chart_tf, plan=plan,
                               show_fib=show_fib, show_liquidity=show_liq,
                               show_sr=show_sr, show_plan=show_plan_overlay)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

            if result:
                col1, col2, col3, col4 = st.columns(4)
                if "BUY" in result["action"]:
                    html = f'<div class="signal-buy">{result["action"]}</div>'
                elif "SELL" in result["action"]:
                    html = f'<div class="signal-sell">{result["action"]}</div>'
                elif "TAKE PROFIT" in result["action"]:
                    html = f'<div class="signal-take-profit">{result["action"]}</div>'
                else:
                    html = f'<div class="signal-hold">{result["action"]}</div>'
                col1.markdown(html, unsafe_allow_html=True)
                col2.metric("MACD DIF", f"{result['macd']['dif']:.6f}")
                col3.metric("RSI", f"{result['rsi']:.1f}")
                col4.metric("Volume", f"{result['volume_ratio']:.2f}x")

            st.divider()
            if plan:
                render_trade_plan(plan, df, chart_coin, chart_tf,
                                  account_balance, risk_pct)
        else:
            st.error(f"❌ Tidak bisa mendapatkan data untuk {chart_coin}")

# ==================== TAB 3: BACKTEST ====================
with tab3:
    st.subheader("🧪 Backtest Auto Trade Plan")
    st.caption("Uji performa rule dengan data historis")

    bt_coin = st.selectbox("Coin", st.session_state.watchlist, key="bt_coin")
    bt_tf = st.selectbox("Timeframe", ["15m", "1h", "4h"], index=1, key="bt_tf")
    b1, b2, b3 = st.columns(3)
    bt_horizon = b1.slider("Horizon (candle)", 5, 50, 20)
    bt_min_conf = b2.slider("Min Confidence", 1, 5, 2)
    run_bt = b3.button("▶️ Run Backtest", use_container_width=True)

    if run_bt:
        with st.spinner("Running backtest..."):
            df_bt = get_data_safe(bt_coin, bt_tf, min_candles=300)
            if df_bt is not None:
                bt, stats = backtest_trade_plan(df_bt, bt_coin,
                                                horizon=bt_horizon, min_conf=bt_min_conf)
                if bt.empty:
                    st.warning("Tidak ada sinyal dalam sample ini.")
                else:
                    q1, q2, q3, q4 = st.columns(4)
                    q1.metric("Total Signals", stats["signals"])
                    q2.metric("Wins", stats["wins"])
                    q3.metric("Losses", stats["losses"])
                    q4.metric("Win Rate", f"{stats['win_rate']:.1f}%")
                    q1, q2 = st.columns(2)
                    q1.metric("Avg Max Gain", f"{stats['avg_gain']:.2f}%")
                    q2.metric("Avg Max DD", f"{stats['avg_dd']:.2f}%")
                    st.dataframe(bt.sort_values("Date", ascending=False),
                                 use_container_width=True, hide_index=True)
            else:
                st.error("Data tidak cukup.")

# ==================== TAB 4: HISTORY ====================
with tab4:
    st.subheader("📜 Signal History")
    history = get_signal_history(limit=100)
    if history:
        df_history = pd.DataFrame(history)
        if 'id' in df_history.columns:
            df_history = df_history.drop('id', axis=1)
        st.dataframe(df_history, use_container_width=True, hide_index=True)
        csv = df_history.to_csv(index=False)
        st.download_button("📥 Download CSV", csv,
                           file_name=f"history_{datetime.now().strftime('%Y%m%d')}.csv",
                           mime="text/csv")
    else:
        st.info("Belum ada sinyal")

# ==================== TAB 5: PERFORMANCE ====================
with tab5:
    st.subheader("📊 Performance Statistics")
    stats = get_performance()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Signals", stats.get("total_signals", 0))
    col2.metric("Wins", stats.get("wins", 0))
    col3.metric("Losses", stats.get("losses", 0))
    col4.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")

    st.divider()
    st.subheader("📈 Auto Trade Plan Rules")
    st.markdown("""
    **🅰️ BUY THE DIP** — Entry di Fib 0.5/0.618 + validasi MACD
    - RR minimum 1.5, SL max 8%, volume minimum 0.5x

    **🅱️ BREAKOUT BUY** — Entry setelah tembus resistance/swing high
    - Wajib RR ≥ 1.5, SL valid (SL < entry)

    **🅲 LIQUIDITY GRAB** — Entry setelah sweep SSL
    - MACD harus tidak bearish
    - TP harus di atas entry (arah valid)

    **⏳ WAIT** — Tidak ada setup valid → tidak entry
    - Volume < 0.5x, RR < 1.5, SL > 8%, TP arah salah, MACD melawan
    """)

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption("""
🔄 Yahoo Finance | Timeframes: 15M, 1H, 4H  
📊 MACD + Stochastic RSI + EMA20/50 + Volume  
📐 Fibonacci + Liquidity + S/R + Auto Trade Plan  
💾 Supabase PostgreSQL
""")
