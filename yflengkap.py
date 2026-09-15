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
from ta.volatility import AverageTrueRange

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
# CSS KUSTOM
# =========================================================
st.markdown("""
<style>
    .stApp { background: #0a0a1a; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 16px;
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
    @keyframes blink {
        0%,100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    .plan-card {
        background: linear-gradient(145deg, #0d1425, #070b14);
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 12px;
    }
    .plan-header {
        font-size: 22px; font-weight: 800;
        color: #00ff88; margin-bottom: 8px;
    }
    .plan-confidence {
        display: inline-block;
        background: rgba(0,255,136,0.1);
        border: 1px solid #00ff88;
        border-radius: 12px;
        padding: 4px 12px;
        color: #00ff88;
        font-weight: 700;
        font-size: 14px;
    }
    .level-box {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 14px;
        text-align: center;
    }
    .level-label {
        color: #64748b; font-size: 12px;
        text-transform: uppercase; letter-spacing: 1px;
    }
    .level-value {
        font-size: 20px; font-weight: 800;
        color: #f1f5f9; margin: 6px 0;
    }
    .level-pct { font-size: 12px; font-weight: 600; }
    .level-pct.pos { color: #00ff88; }
    .level-pct.neg { color: #ff3b5c; }
    .reason-item {
        padding: 6px 0; color: #cbd5e1; font-size: 14px;
    }
    .stButton > button {
        background: linear-gradient(145deg, #00ff88, #00cc66);
        color: #000; font-weight: 700; border: none;
        border-radius: 10px; padding: 10px 24px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: scale(1.03);
        box-shadow: 0 0 30px rgba(0,255,255,0.3);
    }
    .setup-badge {
        display: inline-block; padding: 6px 16px;
        border-radius: 20px; font-weight: 700; font-size: 15px;
    }
    .setup-dip { background: rgba(0,255,136,.15); color:#00ff88; border:1px solid #00ff88; }
    .setup-breakout { background: rgba(0,200,255,.15); color:#00c8ff; border:1px solid #00c8ff; }
    .setup-liq { background: rgba(168,85,247,.15); color:#a855f7; border:1px solid #a855f7; }
    .setup-wait { background: rgba(251,191,36,.15); color:#fbbf24; border:1px solid #fbbf24; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# SUPABASE CONNECTION
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

# =========================================================
# DATABASE FUNCTIONS
# =========================================================
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

def is_duplicate_trade(symbol, trade_type, minutes=5):
    supabase = get_supabase()
    try:
        five_min_ago = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        res = supabase.table("trades")\
            .select("id").eq("symbol", symbol).eq("type", trade_type)\
            .gte("entry_time", five_min_ago).execute()
        return len(res.data) > 0
    except:
        return False

def save_signal(data):
    supabase = get_supabase()
    try:
        symbol = data.get("symbol")
        signal = data.get("signal")
        if is_duplicate_signal(symbol, signal, minutes=5):
            return False
        data["timestamp"] = datetime.now().isoformat()
        supabase.table("signal_history").insert(data).execute()
        return True
    except:
        return False

def save_trade(data):
    supabase = get_supabase()
    try:
        symbol = data.get("symbol")
        trade_type = data.get("type")
        if is_duplicate_trade(symbol, trade_type, minutes=5):
            return False
        data["entry_time"] = datetime.now().isoformat()
        data["status"] = "OPEN"
        supabase.table("trades").insert(data).execute()
        return True
    except:
        return False

def save_trade_plan(plan):
    """Simpan trade plan ke Supabase (tabel trade_plans)."""
    supabase = get_supabase()
    try:
        data = {
            "symbol": plan["symbol"],
            "timeframe": plan["timeframe"],
            "setup_type": plan["setup_type"],
            "confidence": plan["confidence"],
            "entry": float(plan["entry"]),
            "stop_loss": float(plan["stop_loss"]),
            "tp1": float(plan["tp1"]),
            "tp2": float(plan["tp2"]),
            "tp3": float(plan["tp3"]),
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
# TELEGRAM FUNCTIONS
# =========================================================
if "sent_signals" not in st.session_state:
    st.session_state.sent_signals = {}
if "last_telegram_time" not in st.session_state:
    st.session_state.last_telegram_time = {}

def send_telegram_once(symbol, signal, result):
    now = datetime.now()
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
        if bot_token and chat_id:
            msg = f"⚡ SIGNAL ALERT!\n\nCoin: {symbol}\nSignal: {signal}\nTime: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            for tf in ["15m", "1h", "4h"]:
                if tf in result.get("timeframes", {}):
                    res = result["timeframes"][tf]
                    msg += f"\n{tf.upper()}:\n"
                    msg += f"  Action: {res.get('action', '')}\n"
                    msg += f"  MACD: {res['macd']['dif']:.4f}\n"
                    msg += f"  Hist: {res['macd']['histogram']:.4f}\n"
                    msg += f"  Stoch K: {res['stoch']['k']:.1f}\n"
                    msg += f"  RSI: {res['rsi']:.1f}\n"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            response = requests.post(url, json={"chat_id": chat_id, "text": msg}, timeout=10)
            if response.status_code == 200:
                st.session_state.sent_signals[signal_key] = True
                st.session_state.last_telegram_time[symbol] = now
                return True
    except Exception as e:
        print(f"Telegram error: {e}")
    return False

def send_telegram_plan(plan_text):
    """Kirim trade plan ke Telegram."""
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            r = requests.post(url, json={"chat_id": chat_id, "text": plan_text, "parse_mode": "HTML"}, timeout=10)
            return r.status_code == 200
    except:
        pass
    return False

def send_telegram_test(message):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
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
    if value >= 1000:
        return f"$ {value:,.2f}"
    elif value >= 100:
        return f"$ {value:,.3f}"
    elif value >= 1:
        return f"$ {value:,.4f}"
    elif value >= 0.01:
        return f"$ {value:,.6f}"
    else:
        return f"$ {value:,.8f}"

# =========================================================
# GET DATA (YAHOO FINANCE)
# =========================================================
@st.cache_data(ttl=30, show_spinner=False)
def get_data(symbol, interval, period):
    try:
        ticker = f"{symbol}-USD"
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df.empty:
            df = yf.download(symbol, interval=interval, period=period, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df.rename(columns={df.columns[0]: "Time"}, inplace=True)
        df["Time"] = pd.to_datetime(df["Time"])
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
# INDIKATOR TEKNIKAL
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
    """ATR sederhana tanpa pandas_ta."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# =========================================================
# PIVOTS / LIQUIDITY / S&R / FIBONACCI
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
    """Support di bawah harga, Resistance di atas harga."""
    buy_side, sell_side = get_liquidity_zones(df, lookback)
    supports = sorted(sell_side, reverse=True)   # terdekat di bawah dulu
    resistances = sorted(buy_side)               # terdekat di atas dulu
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
# ALGORITMA TRADING - MACD + STOCHASTIC RSI
# =========================================================
def analyze_macd_stoch(df, timeframe=""):
    if df is None or len(df) < 30:
        return None
    macd_line, signal_line, histogram = MACD(df)
    stoch_k, stoch_d, rsi = StochasticRSI(df)
    ema20 = EMA(df, 20)
    ema50 = EMA(df, 50)

    last = df.iloc[-1]
    price = last["Close"]
    volume = last["Volume"]
    vol_ma = df["Volume"].rolling(10).mean().iloc[-1]
    volume_ratio = volume / vol_ma if vol_ma > 0 else 1

    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    hist_val = histogram.iloc[-1]
    hist_prev = histogram.iloc[-2] if len(histogram) > 1 else hist_val
    macd_prev = macd_line.iloc[-2] if len(macd_line) > 1 else macd_val
    signal_prev = signal_line.iloc[-2] if len(signal_line) > 1 else signal_val

    stoch_k_val = stoch_k.iloc[-1]
    stoch_d_val = stoch_d.iloc[-1]
    stoch_k_prev = stoch_k.iloc[-2] if len(stoch_k) > 1 else stoch_k_val
    stoch_d_prev = stoch_d.iloc[-2] if len(stoch_d) > 1 else stoch_d_val
    rsi_val = rsi.iloc[-1]
    ema20_val = ema20.iloc[-1]
    ema50_val = ema50.iloc[-1]

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

    buy_score = 0
    sell_score = 0
    reasons = []

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

    action = "⏳ WAIT"
    signal_type = "HOLD"
    signal_strength = 0

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
        reasons = ["Stoch >85", "Histogram mulai mengecil"]
    else:
        if macd_val > signal_val and 20 <= stoch_k_val <= 80:
            signal_type = "🟡 HOLD"; action = "🟡 HOLD"
        elif macd_val > signal_val and stoch_k_val < 20:
            signal_type = "🟡 WAIT (Stoch oversold)"; action = "⏳ WAIT"
        elif macd_val < signal_val and stoch_k_val > 80:
            signal_type = "🟡 WAIT (Stoch overbought)"; action = "⏳ WAIT"
        else:
            signal_type = "🟡 HOLD / WAIT"; action = "⏳ WAIT"

    return {
        "symbol": None, "timeframe": timeframe,
        "action": action, "signal_type": signal_type, "signal_strength": signal_strength,
        "score": {"buy": buy_score, "sell": sell_score},
        "reasons": reasons if action in ["BUY", "STRONG BUY"] else [],
        "macd": {
            "dif": macd_val, "dea": signal_val, "histogram": hist_val,
            "histogram_prev": hist_prev, "golden_cross": macd_golden_cross,
            "death_cross": macd_death_cross, "hist_increasing": hist_increasing,
            "hist_decreasing": hist_decreasing, "hist_positive": hist_positive,
            "hist_negative": hist_negative
        },
        "stoch": {
            "k": stoch_k_val, "d": stoch_d_val,
            "golden_cross": stoch_golden_cross, "death_cross": stoch_death_cross,
            "k_prev": stoch_k_prev, "d_prev": stoch_d_prev
        },
        "rsi": rsi_val, "ema20": ema20_val, "ema50": ema50_val,
        "price": price, "volume_ratio": volume_ratio,
        "bullish_trend": bullish_trend, "bearish_trend": bearish_trend
    }

# =========================================================
# MULTI TIMEFRAME
# =========================================================
def analyze_mtf_macd_stoch(symbol, timeframes=["15m", "1h", "4h"]):
    results = {}
    for tf in timeframes:
        df = get_data_safe(symbol, tf, min_candles=50)
        if df is not None:
            result = analyze_macd_stoch(df, tf)
            if result:
                result["symbol"] = symbol
                results[tf] = result
    if not results:
        return None

    combined = {"symbol": symbol, "timeframes": results}
    buy_count = sell_count = hold_count = 0
    for tf in ["4h", "1h", "15m"]:
        if tf in results:
            res = results[tf]
            if "BUY" in res["action"]: buy_count += 1
            elif "SELL" in res["action"]: sell_count += 1
            else: hold_count += 1

    main_signal = "⏳ WAIT"; main_strength = 0; total_score = 50
    if buy_count >= 2:
        main_signal = "🟢 STRONG BUY (Multi TF)"; main_strength = 3; total_score = 75 + (buy_count * 5)
    elif buy_count == 1 and hold_count >= 1:
        main_signal = "🟢 BUY"; main_strength = 2; total_score = 65
    elif sell_count >= 2:
        main_signal = "🔴 STRONG SELL (Multi TF)"; main_strength = 3; total_score = 75 + (sell_count * 5)
    elif sell_count == 1 and hold_count >= 1:
        main_signal = "🔴 SELL"; main_strength = 2; total_score = 65
    else:
        main_signal = "🟡 HOLD / WAIT"; main_strength = 1; total_score = 50

    combined.update({
        "main_signal": main_signal, "main_strength": main_strength,
        "buy_count": buy_count, "sell_count": sell_count, "hold_count": hold_count,
        "total_score": total_score, "confirmations": buy_count + sell_count,
        "smart_money": {"score": 50},
        "trend_1h": results.get("1h", {}).get("action", "⏳ WAIT"),
        "trend_15m": results.get("15m", {}).get("action", "⏳ WAIT"),
    })
    return combined

# =========================================================
# ⭐ AUTO TRADE PLAN GENERATOR (FITUR BARU)
# =========================================================
def generate_trade_plan(df, symbol, timeframe, account_balance=1000.0, risk_pct=2.0):
    """
    Generate otomatis Entry / SL / TP / RR / Confidence / 3 skenario.
    Return dict atau None jika tidak ada setup.
    """
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

    # Level kunci
    fib_236 = fib.get(0.236); fib_382 = fib.get(0.382); fib_5 = fib.get(0.5)
    fib_618 = fib.get(0.618); fib_786 = fib.get(0.786)
    swing_high = fib.get("Swing High"); swing_low = fib.get("Swing Low")

    nearest_ssl = min([s for s in sell_side if s < price], key=lambda x: abs(price - x), default=None)
    nearest_bsl = min([b for b in buy_side if b > price], key=lambda x: abs(price - x), default=None)
    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None

    # ---------- Deteksi Setup ----------
    setup_type = "WAIT"; setup_label = "⏳ WAIT (no clear setup)"; setup_class = "setup-wait"
    entry = sl = tp1 = tp2 = tp3 = None
    reasons = []
    invalidations = []

    # Helper toleransi
    near = lambda a, b, pct=1.5: a is not None and b is not None and abs(a - b) / b * 100 < pct

    # Setup A: BUY THE DIP (dekat Fib 0.5/0.618)
    dip_level = None
    if fib_618 and abs(price - fib_618) / fib_618 * 100 < 5:
        dip_level = fib_618
    elif fib_5 and abs(price - fib_5) / fib_5 * 100 < 3:
        dip_level = fib_5

    # Setup B: BREAKOUT (harga tembus resistance)
    breakout_level = None
    if nearest_resistance and price > nearest_resistance * 0.998:
        breakout_level = nearest_resistance
    elif swing_high and price > swing_high * 0.998:
        breakout_level = swing_high

    # Setup C: LIQUIDITY GRAB (harga dekat SSL)
    liq_level = None
    if nearest_ssl and abs(price - nearest_ssl) / nearest_ssl * 100 < 2:
        liq_level = nearest_ssl

    # Priority: dip > breakout > liq grab
    if dip_level:
        setup_type = "BUY_THE_DIP"
        setup_label = "🅰️ BUY THE DIP (Fib Retracement)"
        setup_class = "setup-dip"
        entry = dip_level
        sl = min(fib_786, nearest_ssl) if fib_786 and nearest_ssl else (fib_786 or price - 2*atr)
        sl = sl * 0.997  # buffer
        risk = entry - sl
        tp1 = fib_382 if fib_382 else entry + risk * 1.5
        tp2 = fib_236 if fib_236 else entry + risk * 2.5
        tp3 = swing_high if swing_high else entry + risk * 4.0
        reasons.append(f"✅ Harga dekat Fib retracement (${dip_level:.6f})")
        if nearest_ssl and near(sl, nearest_ssl, 3):
            reasons.append(f"✅ SL di bawah SSL (${nearest_ssl:.6f})")
        if nearest_support:
            reasons.append(f"✅ Support terdekat: ${nearest_support:.6f}")

    elif breakout_level:
        setup_type = "BREAKOUT"
        setup_label = "🅱️ BREAKOUT BUY"
        setup_class = "setup-breakout"
        entry = breakout_level * 1.002
        sl = max(entry - 2*atr, fib_236 if fib_236 else entry - 2*atr)
        risk = entry - sl
        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 4.0
        reasons.append(f"✅ Breakout di atas resistance (${breakout_level:.6f})")
        if nearest_bsl:
            reasons.append(f"🎯 Target BSL berikutnya: ${nearest_bsl:.6f}")

    elif liq_level:
        setup_type = "LIQUIDITY_GRAB"
        setup_label = "🅲 LIQUIDITY GRAB (SSL Sweep)"
        setup_class = "setup-liq"
        entry = liq_level * 1.001
        sl = (sell_side[1] * 0.998) if len(sell_side) > 1 else (entry - 2*atr)
        risk = entry - sl
        tp1 = fib_5 if fib_5 else entry + risk * 1.5
        tp2 = fib_382 if fib_382 else entry + risk * 2.5
        tp3 = fib_236 if fib_236 else entry + risk * 4.0
        reasons.append(f"✅ Harga sweep SSL (${liq_level:.6f})")
        reasons.append(f"🎯 Target bounce: Fib 0.5 (${fib_5:.6f})" if fib_5 else "")

    else:
        return {
            "symbol": symbol, "timeframe": timeframe,
            "setup_type": "WAIT", "setup_label": setup_label, "setup_class": setup_class,
            "confidence": 0, "entry": price, "stop_loss": price, "tp1": price,
            "tp2": price, "tp3": price, "rr": 0,
            "reasons": ["⚠️ Tidak ada setup jelas — harga di tengah range",
                        f"Harga: ${price:.6f}",
                        f"Tunggu pullback ke ${fib_618:.6f}" if fib_618 else "",
                        f"Atau breakout di atas ${nearest_resistance:.6f}" if nearest_resistance else ""],
            "invalidations": ["Tidak ada setup = tidak entry"],
            "atr": atr, "price": price,
            "dip_level": fib_618, "breakout_level": nearest_resistance,
            "liq_level": nearest_ssl,
            "alternatives": []
        }

    if not entry or not sl:
        return None

    # ---------- Risk/Reward ----------
    risk = entry - sl
    if risk <= 0:
        return None
    rr = (tp2 - entry) / risk if risk > 0 else 0

    # ---------- Confidence Score ----------
    confidence = 0
    analysis = analyze_macd_stoch(df, timeframe)
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

    # Konfluensi level
    if nearest_ssl and near(entry, nearest_ssl, 2):
        confidence += 1; reasons.append(f"✅ Entry konfluen dengan SSL (${nearest_ssl:.6f})")
    if fib_618 and near(entry, fib_618, 2):
        confidence += 0.5; reasons.append("✅ Entry di Fib 0.618 (golden ratio)")

    confidence_int = min(5, int(round(confidence)))

    # ---------- Invalidations ----------
    invalidations.append(f"❌ Batal jika harga close < ${sl:.6f} ({timeframe})")
    if analysis:
        invalidations.append(f"❌ Batal jika MACD death cross di {timeframe}")
        invalidations.append(f"❌ Batal jika Stoch K > 80 tanpa momentum")

    # ---------- Skenario Alternatif ----------
    alternatives = []

    # Alt 1: Limit Buy (kalau entry kita bukan dip)
    if setup_type != "BUY_THE_DIP" and fib_618 and fib_618 < price:
        alt_sl = (fib_786 * 0.997) if fib_786 else (fib_618 - 2*atr)
        alt_risk = fib_618 - alt_sl
        if alt_risk > 0:
            alternatives.append({
                "name": "🅰️ LIMIT BUY (tunggu pullback)",
                "entry": fib_618, "sl": alt_sl,
                "tp": fib_382 if fib_382 else fib_618 + alt_risk * 2,
                "rr": ((fib_382 - fib_618) / alt_risk) if fib_382 else 2.0,
                "note": f"Tunggu harga turun ke Fib 0.618 (${fib_618:.6f})"
            })

    # Alt 2: Breakout
    if setup_type != "BREAKOUT" and nearest_resistance and nearest_resistance > price:
        bo_entry = nearest_resistance * 1.002
        bo_sl = max(bo_entry - 2*atr, fib_236 if fib_236 else bo_entry - 2*atr)
        bo_risk = bo_entry - bo_sl
        if bo_risk > 0:
            alternatives.append({
                "name": "🅱️ BREAKOUT BUY",
                "entry": bo_entry, "sl": bo_sl,
                "tp": bo_entry + bo_risk * 2.5,
                "rr": 2.5,
                "note": f"Tunggu tembus resistance ${nearest_resistance:.6f} dengan volume"
            })

    # Alt 3: Scalp di SSL
    if nearest_ssl and nearest_ssl < price:
        sc_entry = nearest_ssl * 1.001
        sc_sl = (sell_side[1] * 0.998) if len(sell_side) > 1 else (sc_entry - 1.5*atr)
        sc_risk = sc_entry - sc_sl
        if sc_risk > 0 and fib_5:
            alternatives.append({
                "name": "🅲 SCALP BUY (di SSL)",
                "entry": sc_entry, "sl": sc_sl,
                "tp": fib_5,
                "rr": (fib_5 - sc_entry) / sc_risk if sc_risk > 0 else 1.5,
                "note": f"Entry di SSL ${nearest_ssl:.6f}, target Fib 0.5 ${fib_5:.6f}"
            })

    # ---------- Position Sizing ----------
    max_loss_usd = account_balance * (risk_pct / 100)
    risk_per_unit = entry - sl
    units = max_loss_usd / risk_per_unit if risk_per_unit > 0 else 0
    position_usd = units * entry
    profit_tp2_usd = units * (tp2 - entry)

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
        "dip_level": fib_618, "breakout_level": nearest_resistance,
        "liq_level": nearest_ssl,
        "alternatives": alternatives,
        # Position sizing
        "account_balance": account_balance,
        "risk_pct": risk_pct,
        "max_loss_usd": max_loss_usd,
        "units": units,
        "position_usd": position_usd,
        "profit_tp2_usd": profit_tp2_usd,
        # Fib / levels for reference
        "fib": fib,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance
    }

# =========================================================
# FORMAT PLAN UNTUK TELEGRAM
# =========================================================
def format_plan_for_telegram(plan):
    txt = f"🎯 <b>AUTO TRADE PLAN</b>\n\n"
    txt += f"<b>{plan['symbol']} · {plan['timeframe']}</b>\n"
    txt += f"{plan['setup_label']}\n"
    txt += f"Confidence: {'⭐' * plan['confidence']} ({plan['confidence']}/5)\n\n"
    txt += f"📈 <b>Entry:</b> ${plan['entry']:.6f}\n"
    txt += f"🛑 <b>SL:</b> ${plan['stop_loss']:.6f} ({(plan['stop_loss']/plan['entry']-1)*100:+.2f}%)\n"
    txt += f"🎯 <b>TP1:</b> ${plan['tp1']:.6f} ({(plan['tp1']/plan['entry']-1)*100:+.2f}%)\n"
    txt += f"🎯 <b>TP2:</b> ${plan['tp2']:.6f} ({(plan['tp2']/plan['entry']-1)*100:+.2f}%)\n"
    txt += f"🎯 <b>TP3:</b> ${plan['tp3']:.6f} ({(plan['tp3']/plan['entry']-1)*100:+.2f}%)\n"
    txt += f"📊 <b>R:R:</b> 1 : {plan['rr']:.2f}\n\n"
    txt += f"💰 <b>Position Sizing</b>\n"
    txt += f"Modal: ${plan['account_balance']:.2f}\n"
    txt += f"Risk: {plan['risk_pct']:.1f}% (${plan['max_loss_usd']:.2f})\n"
    txt += f"Position: ${plan['position_usd']:.2f} ({plan['units']:.4f} unit)\n"
    txt += f"Potensi profit TP2: ${plan['profit_tp2_usd']:.2f}\n\n"
    txt += f"🧠 <b>Alasan:</b>\n"
    for r in plan['reasons'][:6]:
        txt += f"{r}\n"
    txt += f"\n⚠️ <b>Invalidasi:</b>\n"
    for i in plan['invalidations'][:3]:
        txt += f"{i}\n"
    txt += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return txt

# =========================================================
# CREATE CHART (dengan Fib + Liquidity + S/R + Plan)
# =========================================================
def create_chart(df, symbol, timeframe, plan=None,
                 show_fib=True, show_liquidity=True, show_sr=True, show_plan=True):
    if df is None or len(df) < 30:
        return None

    macd_line, signal_line, histogram = MACD(df)
    stoch_k, stoch_d, rsi = StochasticRSI(df)
    ema20 = EMA(df, 20)
    ema50 = EMA(df, 50)

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

    # Fibonacci
    if show_fib and fib:
        fib_colors = {
            0.236: "rgba(255,255,255,0.35)",
            0.382: "rgba(255,215,0,0.55)",
            0.5:   "rgba(255,140,0,0.55)",
            0.618: "rgba(0,200,255,0.65)",
            0.786: "rgba(168,85,247,0.65)",
        }
        for level, price_lvl in fib.items():
            if isinstance(level, str):
                fig.add_hline(y=price_lvl, line_dash="dot",
                    line_color="rgba(148,163,184,0.5)", line_width=1,
                    annotation_text=f"  Fib {level}",
                    annotation_position="right",
                    annotation_font=dict(size=9, color="#94a3b8"),
                    row=1, col=1)
            else:
                color = fib_colors.get(level, "rgba(255,255,255,0.3)")
                fig.add_hline(y=price_lvl, line_dash="dash",
                    line_color=color, line_width=1,
                    annotation_text=f"  Fib {level:.3f}",
                    annotation_position="right",
                    annotation_font=dict(size=9, color=color),
                    row=1, col=1)

    # Liquidity
    if show_liquidity:
        for lvl in buy_side[:3]:
            fig.add_hline(y=lvl, line_dash="solid",
                line_color="rgba(0,255,136,0.35)", line_width=1,
                annotation_text="  💧 BSL", annotation_position="left",
                annotation_font=dict(size=9, color="#00ff88"),
                row=1, col=1)
            fig.add_hrect(y0=lvl*0.998, y1=lvl*1.002,
                fillcolor="rgba(0,255,136,0.06)", line_width=0, row=1, col=1)
        for lvl in sell_side[:3]:
            fig.add_hline(y=lvl, line_dash="solid",
                line_color="rgba(255,59,92,0.35)", line_width=1,
                annotation_text="  💧 SSL", annotation_position="left",
                annotation_font=dict(size=9, color="#ff3b5c"),
                row=1, col=1)
            fig.add_hrect(y0=lvl*0.998, y1=lvl*1.002,
                fillcolor="rgba(255,59,92,0.06)", line_width=0, row=1, col=1)

    # S/R
    if show_sr:
        for lvl in sr_resistance[:2]:
            fig.add_hline(y=lvl, line_dash="longdash",
                line_color="rgba(255,100,100,0.45)", line_width=1.2,
                annotation_text=f"  R {format_price(lvl)}",
                annotation_position="right",
                annotation_font=dict(size=9, color="#ff6464"),
                row=1, col=1)
        for lvl in sr_support[:2]:
            fig.add_hline(y=lvl, line_dash="longdash",
                line_color="rgba(100,255,100,0.45)", line_width=1.2,
                annotation_text=f"  S {format_price(lvl)}",
                annotation_position="right",
                annotation_font=dict(size=9, color="#64ff64"),
                row=1, col=1)

    # ===== TRADE PLAN OVERLAY =====
    if show_plan and plan and plan.get("setup_type") not in [None, "WAIT"]:
        entry = plan["entry"]; sl = plan["stop_loss"]
        tp1 = plan["tp1"]; tp2 = plan["tp2"]; tp3 = plan["tp3"]

        fig.add_hline(y=entry, line_dash="solid", line_color="#00c8ff", line_width=2,
            annotation_text=f"  🎯 ENTRY ${entry:.6f}",
            annotation_position="left",
            annotation_font=dict(size=11, color="#00c8ff"),
            row=1, col=1)
        fig.add_hline(y=sl, line_dash="solid", line_color="#ff3b5c", line_width=2,
            annotation_text=f"  🛑 SL ${sl:.6f}",
            annotation_position="left",
            annotation_font=dict(size=11, color="#ff3b5c"),
            row=1, col=1)
        for tp, label, col in [(tp1, "TP1", "#00ff88"), (tp2, "TP2", "#00ff88"), (tp3, "TP3", "#00ff88")]:
            fig.add_hline(y=tp, line_dash="dot", line_color=col, line_width=1.5,
                annotation_text=f"  🎯 {label} ${tp:.6f}",
                annotation_position="left",
                annotation_font=dict(size=10, color=col),
                row=1, col=1)

        # Shaded risk & reward zone
        fig.add_hrect(y0=min(entry, sl), y1=max(entry, sl),
            fillcolor="rgba(255,59,92,0.08)", line_width=0, row=1, col=1)
        fig.add_hrect(y0=min(entry, tp2), y1=max(entry, tp2),
            fillcolor="rgba(0,255,136,0.06)", line_width=0, row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df["Time"], y=rsi,
        line=dict(color="#a855f7", width=2), name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD
    fig.add_trace(go.Scatter(x=df["Time"], y=macd_line,
        line=dict(color="#00a2ff", width=1.5), name="DIF (MACD)"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=signal_line,
        line=dict(color="#ff00ff", width=1.5), name="DEA (Signal)"), row=3, col=1)
    colors = ["#00ff88" if h >= 0 else "#ff3b5c" for h in histogram]
    fig.add_trace(go.Bar(x=df["Time"], y=histogram,
        marker_color=colors, opacity=0.5, name="Histogram"), row=3, col=1)
    fig.add_hline(y=0, line_dash="solid",
        line_color="rgba(255,255,255,0.2)", row=3, col=1)

    # Stoch
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
# BACKTEST TRADE PLAN
# =========================================================
def backtest_trade_plan(df, symbol, lookback=20, horizon=20, min_conf=2):
    """
    Backtest rule Auto Trade Plan pada historical data.
    Untuk setiap candle, generate plan → tunggu apakah TP1/SL kena dalam horizon.
    """
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

        entry = plan["entry"]
        sl = plan["stop_loss"]
        tp1 = plan["tp1"]
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
            "RR": plan["rr"],
            "Outcome": outcome,
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
# INITIALIZATION
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()
if "pending_signal" not in st.session_state:
    st.session_state.pending_signal = {}
if "signal_history" not in st.session_state:
    st.session_state.signal_history = get_signal_history()
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
                    else:
                        st.error("❌ Gagal tambah coin!")

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
    hold_minutes = st.slider("Hold Signal (menit)", 5, 30, 15, key="hold_minutes")

    st.divider()
    st.subheader("📱 Telegram Alert")
    if st.button("🚀 Test Telegram", use_container_width=True):
        send_telegram_test("🚀 Telegram Connected! Scanner PRO Aktif.")
        st.success("✅ Pesan test terkirim!")

    st.divider()
    st.subheader("📊 Status")
    st.metric("Total Coins", len(st.session_state.watchlist))
    stats = get_performance()
    st.metric("Total Signals", stats.get('total_signals', 0))
    st.caption(f"🔄 Auto Refresh: {refresh} detik")

# =========================================================
# AUTO REFRESH
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# MAIN TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Scanner", "📈 Chart + Plan", "🧪 Backtest", "📋 History", "📊 Performance"
])

# ==================== TAB 1: SCANNER ====================
with tab1:
    st.subheader("📊 Signal Scanner - MACD + Stochastic RSI")
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

    for idx, symbol in enumerate(st.session_state.watchlist[:50]):
        progress_bar.progress((idx + 1) / len(st.session_state.watchlist[:50]))
        status_text.text(f"🔄 Scanning {symbol}...")
        result = analyze_mtf_macd_stoch(symbol, ["15m", "1h", "4h"])

        if result:
            signal_data = {
                "Coin": symbol,
                "Signal": result["main_signal"],
                "Strength": "⭐" * result.get("main_strength", 1),
                "Conf": f"{result.get('total_score', 50):.0f}",
            }
            for tf in ["15m", "1h", "4h"]:
                if tf in result["timeframes"]:
                    res = result["timeframes"][tf]
                    signal_data[f"{tf.upper()}"] = res["action"]
                    signal_data[f"{tf.upper()} RSI"] = f"{res['rsi']:.1f}"
                    signal_data[f"{tf.upper()} K"] = f"{res['stoch']['k']:.1f}"
            all_signals.append(signal_data)

            if result["main_strength"] >= 2 and ("BUY" in result["main_signal"] or "SELL" in result["main_signal"]):
                df_5m = get_data_safe(symbol, "5m", min_candles=20)
                if df_5m is not None:
                    price = df_5m["Close"].iloc[-1]
                    atr = get_atr(df_5m, 14).iloc[-1]
                    if pd.isna(atr) or atr == 0:
                        atr = price * 0.01

                    if "BUY" in result["main_signal"]:
                        entry = price
                        sl = entry - atr * 3
                        tp = entry + atr * 7
                    else:
                        entry = price
                        sl = entry + atr * 3
                        tp = entry - atr * 7

                    if symbol not in st.session_state.pending_signal:
                        st.session_state.pending_signal[symbol] = {
                            "signal": result["main_signal"],
                            "time": datetime.now(),
                            "entry": entry, "sl": sl, "tp": tp,
                            "timeframe": "5m"
                        }
                        sent = send_telegram_once(symbol, result["main_signal"], result)
                        if sent:
                            save_signal({
                                'symbol': symbol,
                                'signal': result["main_signal"],
                                'entry_price': entry, 'stop_loss': sl, 'take_profit': tp,
                                'trend_1h': result.get("trend_1h", "⏳ WAIT"),
                                'trend_15m': result.get("trend_15m", "⏳ WAIT"),
                                'score': result.get("total_score", 50),
                                'confidence': (result.get("confirmations", 0) / 3) * 100,
                                'smart_money_score': 50,
                            })

    progress_bar.empty()
    status_text.empty()

    if all_signals:
        df_signals = pd.DataFrame(all_signals)
        st.dataframe(df_signals, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Tidak ada data")

    if st.session_state.pending_signal:
        st.divider()
        st.subheader("⏳ Pending Signals")
        pending_data = []
        for symbol, data in st.session_state.pending_signal.items():
            elapsed = (datetime.now() - data["time"]).seconds / 60
            remaining = max(0, hold_minutes - elapsed)
            entry = data["entry"]; sl = data["sl"]; tp = data["tp"]
            rr = (tp - entry) / (entry - sl) if "BUY" in data["signal"] and (entry-sl) != 0 else 0
            pending_data.append({
                "Coin": symbol, "Signal": data["signal"],
                "Entry": format_price(entry), "TP": format_price(tp),
                "SL": format_price(sl), "RR": f"{rr:.2f}",
                "Time Left": f"{remaining:.0f}m"
            })
        if pending_data:
            st.dataframe(pd.DataFrame(pending_data), use_container_width=True, hide_index=True)

# ==================== TAB 2: CHART + AUTO PLAN ====================
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

            # ===== GENERATE AUTO TRADE PLAN =====
            plan = generate_trade_plan(df, chart_coin, chart_tf,
                                        account_balance=account_balance,
                                        risk_pct=risk_pct)

            # ===== CHART =====
            fig = create_chart(df, chart_coin, chart_tf, plan=plan,
                               show_fib=show_fib, show_liquidity=show_liq,
                               show_sr=show_sr, show_plan=show_plan_overlay)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

            # ===== SIGNAL BADGE =====
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

            # ===== AUTO TRADE PLAN CARD =====
            st.divider()
            if plan:
                render_trade_plan(plan, df, chart_coin, chart_tf,
                                  account_balance, risk_pct)
        else:
            st.error(f"❌ Tidak bisa mendapatkan data untuk {chart_coin}")

# ==================== TAB 3: BACKTEST ====================
with tab3:
    st.subheader("🧪 Backtest Auto Trade Plan")
    st.caption("Menguji performa rule Auto Trade Plan pada data historis")

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
                bt, stats = backtest_trade_plan(df_bt, bt_coin, horizon=bt_horizon, min_conf=bt_min_conf)
                if bt.empty:
                    st.warning("Tidak ada sinyal dalam sample ini. Coba turunkan confidence atau ganti coin.")
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

                    if stats["signals"] < 20:
                        st.warning("⚠️ Sample kecil (<20). Interpretasi hati-hati.")
            else:
                st.error("Data tidak cukup untuk backtest.")

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
        st.download_button(label="📥 Download CSV", data=csv,
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
    **🅰️ BUY THE DIP** — Entry di Fib 0.5 / 0.618 dengan konfirmasi MACD/Stoch
    - Best in: sideways / uptrend market
    - Konfirmasi: MACD bullish + Stoch oversold + volume

    **🅱️ BREAKOUT BUY** — Entry setelah tembus resistance / swing high
    - Best in: trending market dengan momentum kuat
    - Konfirmasi: volume spike (RVOL > 1.5x)

    **🅲 LIQUIDITY GRAB** — Entry setelah sweep SSL
    - Best in: ranging / bearish reversal
    - Konfirmasi: candle reversal + MACD divergence

    **⚠️ WAIT** — Tidak ada setup jelas → tidak entry
    """)

# =========================================================
# RENDER TRADE PLAN (komponen visual)
# =========================================================
def render_trade_plan(plan, df, symbol, timeframe, account_balance, risk_pct):
    """Render trade plan card dengan semua info."""

    # Header
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

    # Setup WAIT — tampilkan pesan saja
    if plan["setup_type"] == "WAIT":
        st.warning("⏳ Tidak ada setup entry saat ini. " + " | ".join(plan["reasons"]))
        if plan.get("dip_level"):
            st.info(f"💡 Tunggu pullback ke **${plan['dip_level']:.6f}** "
                    f"atau breakout di atas **${plan.get('breakout_level') or 0:.6f}**")
        return

    # Level boxes
    entry = plan["entry"]; sl = plan["stop_loss"]
    tp1 = plan["tp1"]; tp2 = plan["tp2"]; tp3 = plan["tp3"]

    def pct(a, b): return (a / b - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">📈 Entry</div>
            <div class="level-value">${entry:.6f}</div>
            <div class="level-pct">Limit / Market</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">🛑 Stop Loss</div>
            <div class="level-value">${sl:.6f}</div>
            <div class="level-pct neg">{pct(sl, entry):+.2f}%</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">🎯 TP1</div>
            <div class="level-value">${tp1:.6f}</div>
            <div class="level-pct pos">{pct(tp1, entry):+.2f}%</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">🎯 TP2</div>
            <div class="level-value">${tp2:.6f}</div>
            <div class="level-pct pos">{pct(tp2, entry):+.2f}%</div>
        </div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">🎯 TP3</div>
            <div class="level-value">${tp3:.6f}</div>
            <div class="level-pct pos">{pct(tp3, entry):+.2f}%</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">📊 Risk/Reward</div>
            <div class="level-value">1 : {plan['rr']:.2f}</div>
            <div class="level-pct">{'✅ GOOD' if plan['rr'] >= 2 else '⚠️ LOW' if plan['rr'] >= 1.5 else '❌ BAD'}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">💰 Position Size</div>
            <div class="level-value">${plan['position_usd']:.2f}</div>
            <div class="level-pct">{plan['units']:.4f} unit</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="level-box">
            <div class="level-label">💵 Max Loss</div>
            <div class="level-value">${plan['max_loss_usd']:.2f}</div>
            <div class="level-pct neg">{plan['risk_pct']:.1f}% modal</div>
        </div>""", unsafe_allow_html=True)

    # Alasan + Invalidasi
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### 🧠 Alasan (Why this setup)")
        for r in plan["reasons"]:
            st.markdown(f"<div class='reason-item'>{r}</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown("##### ⚠️ Invalidasi (Batal jika)")
        for i in plan["invalidations"]:
            st.markdown(f"<div class='reason-item'>{i}</div>", unsafe_allow_html=True)

    # Alternatif
    if plan.get("alternatives"):
        st.markdown("##### 📋 Skenario Alternatif")
        for alt in plan["alternatives"]:
            with st.expander(f"{alt['name']} — R:R 1:{alt['rr']:.2f}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Entry", f"${alt['entry']:.6f}")
                c2.metric("SL", f"${alt['sl']:.6f}")
                c3.metric("TP", f"${alt['tp']:.6f}")
                st.caption(alt["note"])

    # Action buttons
    st.markdown("---")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("📱 Kirim Plan ke Telegram", use_container_width=True, key="btn_tg_plan"):
            msg = format_plan_for_telegram(plan)
            if send_telegram_plan(msg):
                st.success("✅ Plan terkirim ke Telegram!")
            else:
                st.error("❌ Gagal kirim. Cek token/chat ID.")
    with b2:
        if st.button("💾 Simpan ke Database", use_container_width=True, key="btn_save_plan"):
            if save_trade_plan(plan):
                st.success("✅ Plan tersimpan!")
            else:
                st.error("❌ Gagal simpan. Pastikan tabel 'trade_plans' sudah dibuat.")
    with b3:
        plan_txt = format_plan_for_telegram(plan).replace("<b>", "").replace("</b>", "")
        st.download_button("📋 Download Plan (TXT)", plan_txt,
                           file_name=f"plan_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                           mime="text/plain", use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption("""
🔄 Data dari Yahoo Finance | Timeframes: 15M, 1H, 4H  
📊 Indikator: MACD + Stochastic RSI + EMA20 + EMA50 + Volume  
📐 Overlay: Fibonacci + Liquidity Zones + Support/Resistance + Auto Trade Plan  
💾 Database: Supabase PostgreSQL
""")
