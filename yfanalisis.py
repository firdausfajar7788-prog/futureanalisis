import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import json
import os

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="🚀 Crypto Futures Scanner",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# CSS KUSTOM
# =========================================================
st.markdown("""
<style>
    .stApp {
        background: #0a0a1a;
    }
    
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 4px 20px rgba(0,255,255,0.05);
        transition: all 0.3s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0,255,255,0.1);
    }
    [data-testid="stMetricLabel"] {
        color: #94a3b8;
        font-size: 13px;
        font-weight: 500;
    }
    [data-testid="stMetricValue"] {
        color: #f1f5f9;
        font-size: 24px;
        font-weight: 700;
    }
    
    .signal-buy {
        background: linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,255,136,0.05));
        border: 1px solid #00ff88;
        border-radius: 12px;
        padding: 12px 20px;
        color: #00ff88;
        font-weight: 600;
        font-size: 18px;
        box-shadow: 0 0 30px rgba(0,255,136,0.1);
    }
    .signal-sell {
        background: linear-gradient(135deg, rgba(255,59,92,0.15), rgba(255,59,92,0.05));
        border: 1px solid #ff3b5c;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ff3b5c;
        font-weight: 600;
        font-size: 18px;
        box-shadow: 0 0 30px rgba(255,59,92,0.1);
    }
    .signal-wait {
        background: linear-gradient(135deg, rgba(255,170,0,0.15), rgba(255,170,0,0.05));
        border: 1px solid #ffaa00;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ffaa00;
        font-weight: 600;
        font-size: 18px;
    }
    
    .coin-badge {
        display: inline-block;
        background: rgba(0,255,136,0.08);
        border: 1px solid rgba(0,255,136,0.2);
        border-radius: 20px;
        padding: 4px 16px;
        margin: 3px 4px;
        font-size: 14px;
        color: #00ff88;
        transition: all 0.2s ease;
    }
    .coin-badge:hover {
        background: rgba(0,255,136,0.15);
        border-color: #00ff88;
    }
    
    .stButton > button {
        background: linear-gradient(145deg, #00ff88, #00cc66);
        color: #000;
        font-weight: 700;
        border: none;
        border-radius: 10px;
        padding: 10px 24px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: scale(1.03);
        box-shadow: 0 0 30px rgba(0,255,136,0.3);
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,0.03);
        border-radius: 8px 8px 0 0;
        padding: 8px 20px;
        color: #94a3b8;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(0,255,136,0.08);
        color: #00ff88;
        border-bottom: 2px solid #00ff88;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# LOCAL STORAGE WATCHLIST
# =========================================================
WATCHLIST_FILE = "watchlist.json"

def save_watchlist_local(watchlist):
    try:
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump({
                'watchlist': watchlist,
                'updated': datetime.now().isoformat()
            }, f, indent=2)
        return True
    except:
        return False

def load_watchlist_local():
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                return data.get('watchlist', [])
    except:
        pass
    return None

# =========================================================
# INISIALISASI SESSION STATE
# =========================================================
if "watchlist" not in st.session_state:
    local = load_watchlist_local()
    if local:
        st.session_state.watchlist = local
    else:
        st.session_state.watchlist = ["BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "AVAX", "LINK"]
        save_watchlist_local(st.session_state.watchlist)

if "last_alert" not in st.session_state:
    st.session_state.last_alert = {}

if "selected_coin" not in st.session_state:
    st.session_state.selected_coin = st.session_state.watchlist[0] if st.session_state.watchlist else "BTC"

# =========================================================
# TITLE
# =========================================================
st.title("🚀 Crypto Futures Scanner")
st.caption("Multi Timeframe Analysis: 1H Trend | 15M S/R + BB | 5M Entry")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    
    # --- WATCHLIST MANAGEMENT ---
    st.subheader("📋 Watchlist")
    
    # Add Coin
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_coin = st.text_input("Add Coin", placeholder="PEPE", label_visibility="collapsed")
    with col_add2:
        if st.button("➕", use_container_width=True):
            if new_coin:
                coin = new_coin.upper().strip()
                if coin not in st.session_state.watchlist:
                    st.session_state.watchlist.append(coin)
                    save_watchlist_local(st.session_state.watchlist)
                    st.rerun()
    
    # Show Watchlist
    st.markdown("**Your Coins:**")
    cols = st.columns(3)
    for idx, coin in enumerate(st.session_state.watchlist):
        col_idx = idx % 3
        with cols[col_idx]:
            if st.button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
                if coin in st.session_state.watchlist:
                    st.session_state.watchlist.remove(coin)
                    save_watchlist_local(st.session_state.watchlist)
                    st.rerun()
    
    st.divider()
    
    # --- TRADING SETTINGS ---
    st.subheader("📊 Trading Settings")
    
    refresh = st.slider("🔄 Refresh (detik)", 5, 60, 10)
    currency = st.selectbox("💱 Currency", ["USD", "IDR"])
    leverage = st.slider("⚡ Leverage", 1, 125, 10)
    position_size = st.number_input("💰 Position Size (USD)", 10, 100000, 100, step=10)
    
    st.divider()
    
    # --- TELEGRAM ---
    st.subheader("📱 Telegram Alert")
    BOT_TOKEN = "8819178689:AAHBU4dTqoIUfGvkarKRZLI6wbfKJh6g0RU"
    CHAT_ID = "999556266"
    
    def send_telegram(message):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
        except:
            pass
    
    if st.button("🚀 Test Telegram", use_container_width=True):
        send_telegram("🚀 Telegram Connected! Scanner Aktif.")
        st.success("✅ Pesan test terkirim!")
    
    st.divider()
    
    # --- STATUS ---
    st.subheader("📊 Status")
    st.metric("Total Coins", len(st.session_state.watchlist))
    st.metric("Storage", "✅ Local" if load_watchlist_local() else "⚠️ No Save")
    st.caption(f"🔄 Auto Refresh: {refresh} detik")

# =========================================================
# AUTO REFRESH
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# USD TO IDR
# =========================================================
@st.cache_data(ttl=3600)
def get_usd_idr():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url, timeout=10)
        data = response.json()
        return data["rates"]["IDR"]
    except:
        return 16000

usd_to_idr = get_usd_idr()
currency_rate = usd_to_idr if currency == "IDR" else 1
currency_symbol = "Rp" if currency == "IDR" else "$"

# =========================================================
# FORMAT PRICE
# =========================================================
def format_price(value):
    if currency == "IDR":
        return f"Rp {value:,.0f}"
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
# GET DATA - MULTI TIMEFRAME
# =========================================================
@st.cache_data(ttl=30)
def get_data(symbol, interval, period):
    try:
        ticker = f"{symbol}-USD"
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df.empty:
            ticker = symbol
            df = yf.download(ticker, interval=interval, period=period, progress=False)
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
        "4h": ["14d", "30d", "60d"],
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

def RSI(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def MACD(df):
    ema12 = EMA(df, 12)
    ema26 = EMA(df, 26)
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist

def ATR(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = abs(df["High"] - df["Close"].shift())
    low_close = abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def ADX(df, period=14):
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.abs().rolling(period).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        return dx.rolling(period).mean()
    except:
        return pd.Series([0] * len(df))

def BollingerBands(df, period=20, std=2):
    sma = df["Close"].rolling(period).mean()
    rolling_std = df["Close"].rolling(period).std()
    upper = sma + (rolling_std * std)
    lower = sma - (rolling_std * std)
    return upper, sma, lower

def StochasticRSI(df, period=14, smooth_k=3, smooth_d=3):
    rsi = RSI(df, period)
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min()) * 100
    k = stoch_rsi.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d

# =========================================================
# ANALISIS MULTI TIMEFRAME + BOLLINGER BANDS
# =========================================================
def analyze_mtf(symbol):
    # --- 1H TREND ---
    df_1h = get_data_safe(symbol, "1h", min_candles=30)
    if df_1h is None:
        return None
    
    # --- 15M S/R + BB ---
    df_15m = get_data_safe(symbol, "15m", min_candles=50)
    if df_15m is None:
        df_15m = df_1h.copy()
    
    # --- 5M ENTRY ---
    df_5m = get_data_safe(symbol, "5m", min_candles=20)
    if df_5m is None:
        df_5m = df_15m.copy()
    
    # --- 1H TREND ---
    df_1h["EMA20"] = EMA(df_1h, 20)
    df_1h["EMA50"] = EMA(df_1h, 50)
    df_1h["ADX"] = ADX(df_1h)
    
    last_1h = df_1h.iloc[-1]
    price_1h = last_1h["Close"]
    ema20_1h = last_1h["EMA20"] if not pd.isna(last_1h["EMA20"]) else price_1h
    ema50_1h = last_1h["EMA50"] if not pd.isna(last_1h["EMA50"]) else price_1h
    adx_1h = last_1h["ADX"] if not pd.isna(last_1h["ADX"]) else 0
    
    if price_1h > ema20_1h > ema50_1h and adx_1h > 25:
        trend = "🟢 BULLISH (Strong)"
    elif price_1h > ema20_1h > ema50_1h:
        trend = "🟢 BULLISH"
    elif price_1h < ema20_1h < ema50_1h and adx_1h > 25:
        trend = "🔴 BEARISH (Strong)"
    elif price_1h < ema20_1h < ema50_1h:
        trend = "🔴 BEARISH"
    else:
        trend = "🟡 SIDEWAYS"
    
    # --- 15M SUPPORT/RESISTANCE + BB ---
    period = 20
    recent_high = df_15m["High"].tail(period).max()
    recent_low = df_15m["Low"].tail(period).min()
    pivot = (df_15m["High"].tail(period).max() + df_15m["Low"].tail(period).min() + df_15m["Close"].tail(period).mean()) / 3
    r1 = 2 * pivot - recent_low
    s1 = 2 * pivot - recent_high
    
    support = s1
    resistance = r1
    
    # 15M Indicators for BB Analysis
    df_15m["RSI"] = RSI(df_15m, 14)
    df_15m["MACD"], df_15m["MACD_SIGNAL"], df_15m["MACD_HIST"] = MACD(df_15m)
    df_15m["STOCH_K"], df_15m["STOCH_D"] = StochasticRSI(df_15m)
    df_15m["BB_UPPER"], df_15m["BB_MIDDLE"], df_15m["BB_LOWER"] = BollingerBands(df_15m)
    
    last_15m = df_15m.iloc[-1]
    price_15m = last_15m["Close"]
    rsi_15m = last_15m["RSI"] if not pd.isna(last_15m["RSI"]) else 50
    stoch_k = last_15m["STOCH_K"] if not pd.isna(last_15m["STOCH_K"]) else 50
    stoch_d = last_15m["STOCH_D"] if not pd.isna(last_15m["STOCH_D"]) else 50
    macd_hist = last_15m["MACD_HIST"] if not pd.isna(last_15m["MACD_HIST"]) else 0
    macd_line = last_15m["MACD"] if not pd.isna(last_15m["MACD"]) else 0
    macd_signal = last_15m["MACD_SIGNAL"] if not pd.isna(last_15m["MACD_SIGNAL"]) else 0
    
    bb_upper = last_15m["BB_UPPER"] if not pd.isna(last_15m["BB_UPPER"]) else price_15m * 1.05
    bb_lower = last_15m["BB_LOWER"] if not pd.isna(last_15m["BB_LOWER"]) else price_15m * 0.95
    bb_middle = last_15m["BB_MIDDLE"] if not pd.isna(last_15m["BB_MIDDLE"]) else price_15m
    
    # --- BOLLINGER BAND + INDIKATOR ANALYSIS (15M) ---
    bb_score = 0
    bb_reasons = []
    bb_signal = "📊 WAIT"
    
    # 1. RSI + BB
    if rsi_15m < 30 and price_15m < bb_lower:
        bb_score += 25
        bb_reasons.append("RSI Oversold + BB Bottom")
    elif rsi_15m > 70 and price_15m > bb_upper:
        bb_score -= 25
        bb_reasons.append("RSI Overbought + BB Top")
    
    # 2. MACD + BB
    if macd_hist > 0 and macd_line > macd_signal and price_15m > bb_middle:
        bb_score += 30
        bb_reasons.append("MACD Bullish + BB Middle")
    elif macd_hist < 0 and macd_line < macd_signal and price_15m < bb_middle:
        bb_score -= 30
        bb_reasons.append("MACD Bearish + BB Middle")
    
    # 3. Stochastic + BB
    if stoch_k < 20 and stoch_d < 20 and price_15m < bb_lower:
        bb_score += 20
        bb_reasons.append("Stoch Oversold + BB Bottom")
    elif stoch_k > 80 and stoch_d > 80 and price_15m > bb_upper:
        bb_score -= 20
        bb_reasons.append("Stoch Overbought + BB Top")
    
    # 4. BB Squeeze (Volatility contraction)
    bb_width = (bb_upper - bb_lower) / bb_middle
    prev_bb_width = ((df_15m["BB_UPPER"].iloc[-2] - df_15m["BB_LOWER"].iloc[-2]) / df_15m["BB_MIDDLE"].iloc[-2]) if len(df_15m) > 1 else bb_width
    
    if bb_width < 0.05 and bb_width > prev_bb_width * 0.8:
        bb_score += 10
        bb_reasons.append("BB Squeeze - Breakout Imminent")
    
    # 5. BB Reversal Pattern (Harga menyentuh BB lalu kembali ke middle)
    if price_15m < bb_lower and price_15m > df_15m["Close"].iloc[-2]:
        bb_score += 15
        bb_reasons.append("BB Bounce - Reversal Up")
    elif price_15m > bb_upper and price_15m < df_15m["Close"].iloc[-2]:
        bb_score -= 15
        bb_reasons.append("BB Bounce - Reversal Down")
    
    # --- 5M ENTRY SIGNAL ---
    df_5m["RSI"] = RSI(df_5m, 14)
    df_5m["Volume_MA"] = df_5m["Volume"].rolling(5).mean()
    df_5m["BB_UPPER"], _, df_5m["BB_LOWER"] = BollingerBands(df_5m)
    
    last_5m = df_5m.iloc[-1]
    price_5m = last_5m["Close"]
    rsi_5m = last_5m["RSI"] if not pd.isna(last_5m["RSI"]) else 50
    vol = last_5m["Volume"]
    vol_ma = last_5m["Volume_MA"] if not pd.isna(last_5m["Volume_MA"]) else vol
    vol_spike = vol > vol_ma * 1.5 if vol_ma > 0 else False
    
    entry_signal = None
    is_bullish = "BULLISH" in trend
    is_bearish = "BEARISH" in trend
    
    # Entry Logic with BB Confirmation
    if is_bullish:
        if price_5m > support and rsi_5m < 45 and bb_score >= 30:
            entry_signal = "🟢 STRONG BUY (Pullback + BB Confirm)"
        elif price_5m > support and rsi_5m < 45:
            entry_signal = "🟢 BUY (Pullback to Support)"
        elif price_5m > resistance and vol_spike and bb_score >= 20:
            entry_signal = "🟢 STRONG BUY (Breakout + BB Confirm)"
        elif price_5m > resistance and vol_spike:
            entry_signal = "🟢 BUY (Breakout)"
    elif is_bearish:
        if price_5m < resistance and rsi_5m > 55 and bb_score <= -30:
            entry_signal = "🔴 STRONG SELL (Pullback + BB Confirm)"
        elif price_5m < resistance and rsi_5m > 55:
            entry_signal = "🔴 SELL (Pullback to Resistance)"
        elif price_5m < support and vol_spike and bb_score <= -20:
            entry_signal = "🔴 STRONG SELL (Breakdown + BB Confirm)"
        elif price_5m < support and vol_spike:
            entry_signal = "🔴 SELL (Breakdown)"
    else:
        if price_5m > resistance and vol_spike and bb_score >= 20:
            entry_signal = "🟢 BUY (Breakout + BB Confirm)"
        elif price_5m > resistance and vol_spike:
            entry_signal = "🟢 BUY (Breakout)"
        elif price_5m < support and vol_spike and bb_score <= -20:
            entry_signal = "🔴 SELL (Breakdown + BB Confirm)"
        elif price_5m < support and vol_spike:
            entry_signal = "🔴 SELL (Breakdown)"
    
    # Determine final BB Signal
    if bb_score >= 60:
        bb_signal = "🟢 STRONG BUY (BB)"
    elif bb_score >= 30:
        bb_signal = "🟢 BUY (BB)"
    elif bb_score <= -60:
        bb_signal = "🔴 STRONG SELL (BB)"
    elif bb_score <= -30:
        bb_signal = "🔴 SELL (BB)"
    else:
        bb_signal = "📊 WAIT (BB)"
    
    # Risk Management
    atr_5m = ATR(df_5m, 14).iloc[-1] if len(df_5m) > 14 else (df_5m["High"].iloc[-1] - df_5m["Low"].iloc[-1])
    atr_5m = atr_5m if not pd.isna(atr_5m) else 0.01
    
    if entry_signal and "BUY" in entry_signal:
        entry_price = price_5m
        stop_loss = entry_price - atr_5m * 2
        take_profit = entry_price + atr_5m * 4
    elif entry_signal and "SELL" in entry_signal:
        entry_price = price_5m
        stop_loss = entry_price + atr_5m * 2
        take_profit = entry_price - atr_5m * 4
    else:
        entry_price = stop_loss = take_profit = None
    
    return {
        "symbol": symbol,
        "trend": trend,
        "support": support,
        "resistance": resistance,
        "entry_signal": entry_signal,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rsi_5m": rsi_5m,
        "rsi_15m": rsi_15m,
        "adx_1h": adx_1h,
        "price": price_5m,
        "atr": atr_5m,
        # BB Signals
        "bb_signal": bb_signal,
        "bb_score": bb_score,
        "bb_reasons": bb_reasons,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        # Dataframes
        "df_1h": df_1h.tail(50),
        "df_15m": df_15m.tail(50),
        "df_5m": df_5m.tail(30)
    }

# =========================================================
# CREATE CHART - PROFESSIONAL
# =========================================================
def create_chart(result, symbol, currency_rate):
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.35, 0.2, 0.15, 0.15, 0.15],
        subplot_titles=("Price & Indicators (5M)", "RSI + BB (15M)", "MACD (15M)", "Stochastic (15M)", "Volume")
    )
    
    df = result["df_5m"]
    df_15m = result["df_15m"]
    
    # === ROW 1: CANDLESTICK + INDICATORS (5M) ===
    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df["Time"],
            open=df["Open"] * currency_rate,
            high=df["High"] * currency_rate,
            low=df["Low"] * currency_rate,
            close=df["Close"] * currency_rate,
            increasing_line_color="#00ff88",
            decreasing_line_color="#ff3b5c",
            name="Price (5M)"
        ),
        row=1, col=1
    )
    
    # EMA
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=df["Close"].ewm(span=20).mean() * currency_rate,
            line=dict(color="#00a2ff", width=1.5),
            name="EMA20"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=df["Close"].ewm(span=50).mean() * currency_rate,
            line=dict(color="#ffaa00", width=1.5, dash="dash"),
            name="EMA50"
        ),
        row=1, col=1
    )
    
    # BB 5M
    bb_upper, bb_mid, bb_lower = BollingerBands(df)
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=bb_upper * currency_rate,
            line=dict(color="rgba(255,255,255,0.15)", width=1),
            name="BB Upper (5M)"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=bb_lower * currency_rate,
            line=dict(color="rgba(255,255,255,0.15)", width=1),
            name="BB Lower (5M)",
            fill='tonexty',
            fillcolor="rgba(255,255,255,0.02)"
        ),
        row=1, col=1
    )
    
    # S/R Lines
    fig.add_hline(
        y=result["support"] * currency_rate,
        line_dash="dot",
        line_color="green",
        annotation_text=f"S {format_price(result['support'] * currency_rate)}",
        annotation_position="bottom right",
        row=1, col=1
    )
    fig.add_hline(
        y=result["resistance"] * currency_rate,
        line_dash="dot",
        line_color="red",
        annotation_text=f"R {format_price(result['resistance'] * currency_rate)}",
        annotation_position="top right",
        row=1, col=1
    )
    
    # Entry, SL, TP
    if result["entry_signal"]:
        fig.add_hline(
            y=result["entry_price"] * currency_rate,
            line_dash="solid",
            line_color="#00ff88",
            annotation_text="ENTRY",
            annotation_position="top left",
            row=1, col=1
        )
        fig.add_hline(
            y=result["stop_loss"] * currency_rate,
            line_dash="dash",
            line_color="#ff0000",
            annotation_text="SL",
            annotation_position="bottom left",
            row=1, col=1
        )
        fig.add_hline(
            y=result["take_profit"] * currency_rate,
            line_dash="dash",
            line_color="#00ff00",
            annotation_text="TP",
            annotation_position="top right",
            row=1, col=1
        )
    
    # === ROW 2: RSI + BB (15M) ===
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=df_15m["RSI"],
            line=dict(color="#a855f7", width=2),
            name="RSI (15M)"
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=df_15m["BB_UPPER"] / df_15m["Close"].mean() * 100,
            line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dot"),
            name="BB Upper %"
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=df_15m["BB_LOWER"] / df_15m["Close"].mean() * 100,
            line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dot"),
            name="BB Lower %",
            fill='tonexty',
            fillcolor="rgba(255,255,255,0.02)"
        ),
        row=2, col=1
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    # === ROW 3: MACD (15M) ===
    macd, signal, hist = MACD(df_15m)
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=macd,
            line=dict(color="#00a2ff", width=1.5),
            name="MACD"
        ),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=signal,
            line=dict(color="#ff00ff", width=1.5),
            name="Signal"
        ),
        row=3, col=1
    )
    colors = ["#00ff88" if h >= 0 else "#ff3b5c" for h in hist]
    fig.add_trace(
        go.Bar(
            x=df_15m["Time"],
            y=hist,
            marker_color=colors,
            opacity=0.4,
            name="Histogram"
        ),
        row=3, col=1
    )
    
    # === ROW 4: Stochastic (15M) ===
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=df_15m["STOCH_K"],
            line=dict(color="#ffaa00", width=1.5),
            name="Stoch K"
        ),
        row=4, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df_15m["Time"],
            y=df_15m["STOCH_D"],
            line=dict(color="#ff00ff", width=1.5),
            name="Stoch D"
        ),
        row=4, col=1
    )
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=4, col=1)
    
    # === ROW 5: VOLUME ===
    colors_vol = ["#00ff88" if c >= o else "#ff3b5c" 
                  for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(
        go.Bar(
            x=df["Time"],
            y=df["Volume"],
            marker_color=colors_vol,
            opacity=0.5,
            name="Volume"
        ),
        row=5, col=1
    )
    
    # Volume MA
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=df["Volume"].rolling(5).mean(),
            line=dict(color="rgba(255,255,255,0.3)", width=1),
            name="Volume MA"
        ),
        row=5, col=1
    )
    
    # === LAYOUT ===
    fig.update_layout(
        template="plotly_dark",
        height=1100,
        title=dict(
            text=f"<b>{symbol} - Multi Timeframe Analysis</b>",
            font=dict(color="#f1f5f9", size=22),
            x=0.5,
            xanchor="center"
        ),
        hovermode="x unified",
        dragmode="pan",
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#0a0a1a",
        plot_bgcolor="#0a0a1a",
        font=dict(color="#94a3b8"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10)
        ),
        margin=dict(l=10, r=10, t=50, b=10)
    )
    
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
    
    return fig

# =========================================================
# MAIN LOOP
# =========================================================

# --- SIGNAL SUMMARY ---
st.subheader("📊 Signal Summary")

all_signals = []
progress_bar = st.progress(0)
status_text = st.empty()

for idx, symbol in enumerate(st.session_state.watchlist):
    progress_bar.progress((idx + 1) / len(st.session_state.watchlist))
    status_text.text(f"🔄 Scanning {symbol}...")
    
    result = analyze_mtf(symbol)
    if result:
        all_signals.append({
            "Coin": symbol,
            "Trend (1H)": result["trend"],
            "BB Signal (15M)": result["bb_signal"],
            "Entry Signal": result["entry_signal"] if result["entry_signal"] else "⏳ WAIT",
            "RSI 5M": f"{result['rsi_5m']:.1f}",
            "RSI 15M": f"{result['rsi_15m']:.1f}",
            "Entry": format_price(result["entry_price"] * currency_rate) if result["entry_price"] else "-",
            "SL": format_price(result["stop_loss"] * currency_rate) if result["stop_loss"] else "-",
            "TP": format_price(result["take_profit"] * currency_rate) if result["take_profit"] else "-"
        })

progress_bar.empty()
status_text.empty()

if all_signals:
    df_signals = pd.DataFrame(all_signals)
    st.dataframe(df_signals, use_container_width=True, hide_index=True)
else:
    st.info("ℹ️ Tidak ada data")

# =========================================================
# COIN DETAIL
# =========================================================
st.divider()
st.subheader("📈 Coin Detail")

selected_coin = st.selectbox(
    "Select Coin",
    st.session_state.watchlist,
    index=st.session_state.watchlist.index(st.session_state.selected_coin) 
    if st.session_state.selected_coin in st.session_state.watchlist else 0
)
st.session_state.selected_coin = selected_coin

result = analyze_mtf(selected_coin)

if result:
    # Metrics Row
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Trend (1H)", result["trend"])
    col2.metric("Support (15M)", format_price(result["support"] * currency_rate))
    col3.metric("Resistance (15M)", format_price(result["resistance"] * currency_rate))
    col4.metric("RSI (5M)", f"{result['rsi_5m']:.1f}")
    col5.metric("BB Score (15M)", f"{result['bb_score']}/100")
    
    # BB Reasons
    if result["bb_reasons"]:
        with st.expander("📋 BB Analysis Details", expanded=True):
            for reason in result["bb_reasons"]:
                st.write(f"• {reason}")
    
    # Entry Signal
    if result["entry_signal"]:
        if "BUY" in result["entry_signal"]:
            st.markdown(f'<div class="signal-buy">🚀 {result["entry_signal"]}</div>', unsafe_allow_html=True)
        elif "SELL" in result["entry_signal"]:
            st.markdown(f'<div class="signal-sell">🔻 {result["entry_signal"]}</div>', unsafe_allow_html=True)
        
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Entry Price", format_price(result["entry_price"] * currency_rate))
        col_b.metric("Stop Loss", format_price(result["stop_loss"] * currency_rate),
                    delta=f"{((result['stop_loss']/result['entry_price'] - 1)*100):.1f}%")
        col_c.metric("Take Profit", format_price(result["take_profit"] * currency_rate),
                    delta=f"{((result['take_profit']/result['entry_price'] - 1)*100):.1f}%")
        col_d.metric("Risk/Reward", f"{((result['take_profit']/result['entry_price'] - 1) / (result['stop_loss']/result['entry_price'] - 1)):.2f}")
        
        # Telegram Alert
        if selected_coin not in st.session_state.last_alert or st.session_state.last_alert[selected_coin] != result["entry_signal"]:
            message = f"""⚡ FUTURES SIGNAL

Coin : {selected_coin}
Signal : {result['entry_signal']}
Trend : {result['trend']}
BB Signal : {result['bb_signal']}
BB Score : {result['bb_score']}

Entry : ${result['entry_price']:.4f}
SL : ${result['stop_loss']:.4f}
TP : ${result['take_profit']:.4f}
ATR : ${result['atr']:.4f}

Leverage : {leverage}x
Position : ${position_size * leverage:,.0f}

Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            send_telegram(message)
            st.session_state.last_alert[selected_coin] = result["entry_signal"]
    else:
        st.markdown(f'<div class="signal-wait">⏳ {result["bb_signal"]}</div>', unsafe_allow_html=True)
    
    # Chart
    fig = create_chart(result, selected_coin, currency_rate)
    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"""
🔄 Data dari Yahoo Finance | Multi Timeframe: 1H, 15M, 5M  
💱 Currency: {currency} | 🔄 Auto Refresh: {refresh} detik  
📊 Total Coins: {len(st.session_state.watchlist)} | ⚡ Leverage: {leverage}x  
🎯 BB Analysis: RSI + MACD + Stochastic vs Bollinger Bands (15M)
""")
