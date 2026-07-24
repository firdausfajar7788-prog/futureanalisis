import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
import json
import os
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="🚀 Crypto Dashboard All-in-One",
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
        transition: all 0.3s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0,255,255,0.1);
    }
    [data-testid="stMetricLabel"] { color: #94a3b8; font-size: 13px; }
    [data-testid="stMetricValue"] { color: #f1f5f9; font-size: 24px; font-weight: 700; }
    .profit { color: #00ff88; font-weight: 700; }
    .loss { color: #ff3b5c; font-weight: 700; }
    .neutral { color: #ffaa00; font-weight: 700; }
    .signal-buy { background: #00ff88; color: #000; font-weight: 700; padding: 2px 12px; border-radius: 6px; }
    .signal-sell { background: #ff3b5c; color: #fff; font-weight: 700; padding: 2px 12px; border-radius: 6px; }
    .signal-hold { background: #ffaa00; color: #000; font-weight: 700; padding: 2px 12px; border-radius: 6px; }
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
    .position-card {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 16px;
        margin: 8px 0;
        transition: all 0.3s ease;
    }
    .position-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0,255,255,0.1);
    }
    .pending-signal {
        background: linear-gradient(135deg, rgba(255,170,0,0.15), rgba(255,170,0,0.05));
        border: 1px solid #ffaa00;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ffaa00;
        font-weight: 600;
        font-size: 16px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
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
# SESSION STATE
# =========================================================
if "positions" not in st.session_state:
    st.session_state.positions = []
if "pending_signal" not in st.session_state:
    st.session_state.pending_signal = {}
if "last_alert" not in st.session_state:
    st.session_state.last_alert = {}
if "signal_history" not in st.session_state:
    st.session_state.signal_history = []
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["BTC", "ETH", "SOL", "ADA", "XRP", "DOGE"]
if "selected_coin" not in st.session_state:
    st.session_state.selected_coin = "BTC"
if "performance_stats" not in st.session_state:
    st.session_state.performance_stats = {"total_signals": 0, "wins": 0, "losses": 0, "total_profit": 0}
if "last_update" not in st.session_state:
    st.session_state.last_update = datetime.now()
if "prev_data" not in st.session_state:
    st.session_state.prev_data = {}

# =========================================================
# FUNGSI SIMPAN & LOAD POSISI (JSON)
# =========================================================
POSITION_FILE = "positions.json"

def load_positions():
    try:
        if os.path.exists(POSITION_FILE):
            with open(POSITION_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return []

def save_positions(positions):
    try:
        with open(POSITION_FILE, 'w') as f:
            json.dump(positions, f, indent=2, default=str)
        return True
    except:
        return False

def save_pending_signals(pending):
    try:
        with open("pending_signals.json", 'w') as f:
            json.dump(pending, f, indent=2, default=str)
    except:
        pass

def load_pending_signals():
    try:
        if os.path.exists("pending_signals.json"):
            with open("pending_signals.json", 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

# Load data
if not st.session_state.positions:
    st.session_state.positions = load_positions()
if not st.session_state.pending_signal:
    loaded = load_pending_signals()
    if loaded:
        st.session_state.pending_signal = loaded

# =========================================================
# TELEGRAM FUNCTIONS
# =========================================================
def send_telegram(message):
    try:
        BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "8819178689:AAHBU4dTqoIUfGvkarKRZLI6wbfKJh6g0RU")
        CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "999556266")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except:
        pass

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
# FUNGSI ANALISIS TREND
# =========================================================
def analyze_trend(df, timeframe_name):
    if df is None or len(df) < 20:
        return "⚠️ Insufficient Data"
    df = df.copy()
    df["EMA20"] = EMA(df, 20)
    df["EMA50"] = EMA(df, 50)
    df["ADX"] = ADX(df)
    last = df.iloc[-1]
    price = last["Close"]
    ema20 = last["EMA20"] if not pd.isna(last["EMA20"]) else price
    ema50 = last["EMA50"] if not pd.isna(last["EMA50"]) else price
    adx = last["ADX"] if not pd.isna(last["ADX"]) else 0
    if price > ema20 > ema50 and adx > 25:
        return "🟢 BULLISH (Strong)"
    elif price > ema20 > ema50:
        return "🟢 BULLISH"
    elif price < ema20 < ema50 and adx > 25:
        return "🔴 BEARISH (Strong)"
    elif price < ema20 < ema50:
        return "🔴 BEARISH"
    else:
        return "🟡 SIDEWAYS"

# =========================================================
# RISK MANAGEMENT - RR 3:7
# =========================================================
def calculate_risk_management_advanced(df_5m, entry_signal, entry_price, rr_sl=3.0, rr_tp=7.0, use_trailing=True):
    atr = ATR(df_5m, period=20)
    atr_value = atr.iloc[-1] if len(atr) > 0 and not pd.isna(atr.iloc[-1]) else 0.01
    min_atr = entry_price * 0.005
    atr_value = max(atr_value, min_atr)
    if entry_signal and "BUY" in entry_signal:
        stop_loss = entry_price - atr_value * rr_sl
        take_profit = entry_price + atr_value * rr_tp
        if use_trailing and len(df_5m) > 5:
            highest_high = df_5m["High"].tail(5).max()
            new_sl = max(highest_high - atr_value * 0.5, stop_loss)
            stop_loss = max(new_sl, stop_loss)
    elif entry_signal and "SELL" in entry_signal:
        stop_loss = entry_price + atr_value * rr_sl
        take_profit = entry_price - atr_value * rr_tp
        if use_trailing and len(df_5m) > 5:
            lowest_low = df_5m["Low"].tail(5).min()
            new_sl = min(lowest_low + atr_value * 0.5, stop_loss)
            stop_loss = min(new_sl, stop_loss)
    else:
        stop_loss = take_profit = None
    if stop_loss and take_profit:
        if abs(stop_loss - entry_price) / entry_price < 0.01:
            stop_loss = entry_price * 0.99 if entry_signal and "BUY" in entry_signal else entry_price * 1.01
    return stop_loss, take_profit, atr_value

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

def format_percentage(value):
    if pd.isna(value) or value is None:
        return "-"
    return f"{value:.1f}%"

# =========================================================
# ANALISIS MULTI TIMEFRAME
# =========================================================
def analyze_mtf(symbol, buffer_pct=0.5, confirmation_candles=3, rr_sl=3.0, rr_tp=7.0, use_trailing=True, min_confirmations=2):
    df_1h = get_data_safe(symbol, "1h", min_candles=30)
    if df_1h is None:
        return None
    df_15m = get_data_safe(symbol, "15m", min_candles=50)
    if df_15m is None:
        df_15m = df_1h.copy()
    df_5m = get_data_safe(symbol, "5m", min_candles=20)
    if df_5m is None:
        df_5m = df_15m.copy()
    
    trend_1h = analyze_trend(df_1h, "1H")
    trend_15m = analyze_trend(df_15m, "15M")
    trend_5m = analyze_trend(df_5m, "5M")
    
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
    
    period = 20
    recent_high = df_15m["High"].tail(period).max()
    recent_low = df_15m["Low"].tail(period).min()
    pivot = (df_15m["High"].tail(period).max() + df_15m["Low"].tail(period).min() + df_15m["Close"].tail(period).mean()) / 3
    r1 = 2 * pivot - recent_low
    s1 = 2 * pivot - recent_high
    support = s1
    resistance = r1
    
    support_buffer = support * (1 - buffer_pct / 100)
    resistance_buffer = resistance * (1 + buffer_pct / 100)
    support_confirmed = sum(df_5m["Close"].tail(confirmation_candles) > support_buffer) >= confirmation_candles
    resistance_confirmed = sum(df_5m["Close"].tail(confirmation_candles) > resistance_buffer) >= confirmation_candles
    
    bb_score = 0
    bb_reasons = []
    if rsi_15m < 30 and price_15m < bb_lower:
        bb_score += 25
        bb_reasons.append("RSI Oversold + BB Bottom")
    elif rsi_15m > 70 and price_15m > bb_upper:
        bb_score -= 25
        bb_reasons.append("RSI Overbought + BB Top")
    if macd_hist > 0 and macd_line > macd_signal and price_15m > bb_middle:
        bb_score += 30
        bb_reasons.append("MACD Bullish + BB Middle")
    elif macd_hist < 0 and macd_line < macd_signal and price_15m < bb_middle:
        bb_score -= 30
        bb_reasons.append("MACD Bearish + BB Middle")
    if stoch_k < 20 and stoch_d < 20 and price_15m < bb_lower:
        bb_score += 20
        bb_reasons.append("Stoch Oversold + BB Bottom")
    elif stoch_k > 80 and stoch_d > 80 and price_15m > bb_upper:
        bb_score -= 20
        bb_reasons.append("Stoch Overbought + BB Top")
    
    df_5m["RSI"] = RSI(df_5m, 14)
    df_5m["Volume_MA"] = df_5m["Volume"].rolling(5).mean()
    last_5m = df_5m.iloc[-1]
    price_5m = last_5m["Close"]
    rsi_5m = last_5m["RSI"] if not pd.isna(last_5m["RSI"]) else 50
    
    vol = df_5m["Volume"].iloc[-1]
    vol_ma = df_5m["Volume_MA"].iloc[-1] if not pd.isna(df_5m["Volume_MA"].iloc[-1]) else vol
    vol_spike = vol > vol_ma * 1.5 if vol_ma > 0 else False
    if len(df_5m) > 1:
        vol_prev = df_5m["Volume"].iloc[-2]
        vol_ma_prev = df_5m["Volume_MA"].iloc[-2] if not pd.isna(df_5m["Volume_MA"].iloc[-2]) else vol_prev
        vol_spike_prev = vol_prev > vol_ma_prev * 1.5 if vol_ma_prev > 0 else False
        vol_spike_confirmed = vol_spike or vol_spike_prev
    else:
        vol_spike_confirmed = vol_spike
    
    confirmations = sum([support_confirmed, resistance_confirmed, vol_spike_confirmed])
    
    entry_signal = None
    is_bullish = "BULLISH" in trend_1h
    is_bearish = "BEARISH" in trend_1h
    
    if confirmations >= min_confirmations:
        if is_bullish:
            if support_confirmed and rsi_5m < 45 and bb_score >= 30:
                entry_signal = "🟢 STRONG BUY (Pullback + BB Confirmed)"
            elif support_confirmed and rsi_5m < 45:
                entry_signal = "🟢 BUY (Pullback Confirmed)"
            elif resistance_confirmed and vol_spike_confirmed and bb_score >= 20:
                entry_signal = "🟢 STRONG BUY (Breakout Confirmed)"
            elif resistance_confirmed and vol_spike_confirmed:
                entry_signal = "🟢 BUY (Breakout Confirmed)"
        elif is_bearish:
            if support_confirmed and rsi_5m > 55 and bb_score <= -30:
                entry_signal = "🔴 STRONG SELL (Breakdown Confirmed)"
            elif support_confirmed and rsi_5m > 55:
                entry_signal = "🔴 SELL (Breakdown Confirmed)"
            elif resistance_confirmed and vol_spike_confirmed and bb_score <= -20:
                entry_signal = "🔴 STRONG SELL (Pullback Confirmed)"
            elif resistance_confirmed and vol_spike_confirmed:
                entry_signal = "🔴 SELL (Pullback Confirmed)"
        else:
            if resistance_confirmed and vol_spike_confirmed and bb_score >= 20:
                entry_signal = "🟢 BUY (Breakout Confirmed)"
            elif resistance_confirmed and vol_spike_confirmed:
                entry_signal = "🟢 BUY (Breakout Confirmed)"
            elif support_confirmed and vol_spike_confirmed and bb_score <= -20:
                entry_signal = "🔴 SELL (Breakdown Confirmed)"
            elif support_confirmed and vol_spike_confirmed:
                entry_signal = "🔴 SELL (Breakdown Confirmed)"
    
    if entry_signal:
        entry_price = df_5m["Close"].iloc[-1]
        stop_loss, take_profit, atr_value = calculate_risk_management_advanced(
            df_5m, entry_signal, entry_price, rr_sl, rr_tp, use_trailing
        )
    else:
        entry_price = stop_loss = take_profit = None
        atr_value = 0.01
    
    return {
        "symbol": symbol,
        "trend_1h": trend_1h,
        "trend_15m": trend_15m,
        "trend_5m": trend_5m,
        "support": support,
        "resistance": resistance,
        "support_confirmed": support_confirmed,
        "resistance_confirmed": resistance_confirmed,
        "vol_spike_confirmed": vol_spike_confirmed,
        "confirmations": confirmations,
        "entry_signal": entry_signal,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rsi_5m": rsi_5m,
        "rsi_15m": rsi_15m,
        "price": price_5m,
        "atr": atr_value,
        "bb_score": bb_score,
        "bb_reasons": bb_reasons,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "df_1h": df_1h.tail(50),
        "df_15m": df_15m.tail(50),
        "df_5m": df_5m.tail(30)
    }

# =========================================================
# CREATE CHART
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
    
    fig.add_trace(go.Candlestick(
        x=df["Time"], open=df["Open"]*currency_rate, high=df["High"]*currency_rate,
        low=df["Low"]*currency_rate, close=df["Close"]*currency_rate,
        increasing_line_color="#00ff88", decreasing_line_color="#ff3b5c", name="Price (5M)"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=df["Close"].ewm(span=20).mean()*currency_rate,
                             line=dict(color="#00a2ff", width=1.5), name="EMA20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=df["Close"].ewm(span=50).mean()*currency_rate,
                             line=dict(color="#ffaa00", width=1.5, dash="dash"), name="EMA50"), row=1, col=1)
    
    fig.add_hline(y=result["support"]*currency_rate, line_dash="dot", line_color="green",
                  annotation_text=f"S {format_price(result['support']*currency_rate)}", row=1, col=1)
    fig.add_hline(y=result["resistance"]*currency_rate, line_dash="dot", line_color="red",
                  annotation_text=f"R {format_price(result['resistance']*currency_rate)}", row=1, col=1)
    
    if result["entry_signal"] and result["entry_price"]:
        fig.add_hline(y=result["entry_price"]*currency_rate, line_dash="solid", line_color="#00ff88",
                      annotation_text="ENTRY", row=1, col=1)
        if result["stop_loss"]:
            fig.add_hline(y=result["stop_loss"]*currency_rate, line_dash="dash", line_color="#ff0000",
                          annotation_text=f"SL {format_price(result['stop_loss']*currency_rate)}", row=1, col=1)
        if result["take_profit"]:
            fig.add_hline(y=result["take_profit"]*currency_rate, line_dash="dash", line_color="#00ff00",
                          annotation_text=f"TP {format_price(result['take_profit']*currency_rate)}", row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df_15m["Time"], y=df_15m["RSI"], line=dict(color="#a855f7", width=2), name="RSI (15M)"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    macd, signal, hist = MACD(df_15m)
    fig.add_trace(go.Scatter(x=df_15m["Time"], y=macd, line=dict(color="#00a2ff", width=1.5), name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_15m["Time"], y=signal, line=dict(color="#ff00ff", width=1.5), name="Signal"), row=3, col=1)
    colors_macd = ["#00ff88" if h >= 0 else "#ff3b5c" for h in hist]
    fig.add_trace(go.Bar(x=df_15m["Time"], y=hist, marker_color=colors_macd, opacity=0.4, name="Histogram"), row=3, col=1)
    
    fig.add_trace(go.Scatter(x=df_15m["Time"], y=df_15m["STOCH_K"], line=dict(color="#ffaa00", width=1.5), name="Stoch K"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df_15m["Time"], y=df_15m["STOCH_D"], line=dict(color="#ff00ff", width=1.5), name="Stoch D"), row=4, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=4, col=1)
    
    colors_vol = ["#00ff88" if c >= o else "#ff3b5c" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df["Time"], y=df["Volume"], marker_color=colors_vol, opacity=0.5, name="Volume"), row=5, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=df["Volume"].rolling(5).mean(), line=dict(color="rgba(255,255,255,0.3)", width=1), name="Volume MA"), row=5, col=1)
    
    fig.update_layout(template="plotly_dark", height=1100,
                      title=dict(text=f"<b>{symbol} - Multi Timeframe Analysis (RR 3:7)</b>",
                                font=dict(color="#f1f5f9", size=22), x=0.5, xanchor="center"),
                      hovermode="x unified", dragmode="pan", xaxis_rangeslider_visible=False,
                      paper_bgcolor="#0a0a1a", plot_bgcolor="#0a0a1a", font=dict(color="#94a3b8"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
                      margin=dict(l=10, r=10, t=50, b=10))
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
    return fig

# =========================================================
# FUNGSI AMBIL POSISI AKTIF DARI SCANNER (YANG SUDAH DIAMBIL)
# =========================================================
def get_position_status(symbol):
    """Cek apakah symbol sudah punya posisi aktif"""
    for pos in st.session_state.positions:
        if pos["symbol"] == symbol:
            return pos
    return None

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ Settings")
    
    st.subheader("📊 Trading Settings")
    refresh = st.slider("🔄 Refresh (detik)", 5, 60, 10)
    currency = st.selectbox("💱 Currency", ["USD", "IDR"])
    
    st.divider()
    
    # === RISK MANAGEMENT SETTINGS ===
    st.subheader("🎯 Risk Management (RR 3:7)")
    rr_sl = st.slider("Stop Loss (ATR)", 1.0, 5.0, 3.0, 0.5)
    rr_tp = st.slider("Take Profit (ATR)", 3.0, 12.0, 7.0, 0.5)
    use_trailing = st.toggle("🚀 Use Trailing Stop", value=True)
    min_confirmations = st.slider("Minimal Konfirmasi", 1, 3, 2)
    
    st.divider()
    
    st.subheader("🛡️ Signal Stability")
    hold_minutes = st.slider("Hold Signal (menit)", 5, 30, 15)
    buffer_pct = st.slider("Buffer Level (%)", 0.1, 1.0, 0.5, 0.1)
    confirmation_candles = st.slider("Konfirmasi Candle", 1, 5, 3)
    
    st.divider()
    
    st.subheader("📱 Telegram Alert")
    if st.button("🚀 Test Telegram", use_container_width=True):
        send_telegram("🚀 Dashboard Aktif!")
        st.success("✅ Pesan test terkirim!")
    
    st.divider()
    
    st.subheader("📊 Status")
    st.metric("Total Positions", len(st.session_state.positions))
    st.metric("Pending Signals", len(st.session_state.pending_signal))
    win_rate = st.session_state.performance_stats['wins'] / max(1, st.session_state.performance_stats['total_signals']) * 100
    st.metric("Win Rate", f"{win_rate:.1f}%")

# =========================================================
# AUTO REFRESH
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# MAIN TITLE
# =========================================================
st.title("🚀 Crypto Dashboard All-in-One")
st.caption(f"🕐 Last Update: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

# =========================================================
# GET USD/IDR
# =========================================================
usd_to_idr = get_usd_idr()
currency_rate = usd_to_idr if currency == "IDR" else 1

# =========================================================
# TAB 1: SCANNER | TAB 2: POSITIONS
# =========================================================
tab1, tab2 = st.tabs(["📊 Scanner & Signals", "📈 My Positions"])

# =========================================================
# TAB 1: SCANNER
# =========================================================
with tab1:
    # --- CLEANUP PENDING SIGNALS (EXPIRED) ---
    current_time = datetime.now()
    expired_signals = []
    for symbol, data in st.session_state.pending_signal.items():
        elapsed = (current_time - data["time"]).seconds / 60
        if elapsed > hold_minutes:
            expired_signals.append(symbol)
    for symbol in expired_signals:
        del st.session_state.pending_signal[symbol]
        save_pending_signals(st.session_state.pending_signal)
    
    # --- SIGNAL SUMMARY ---
    st.subheader("📊 Signal Summary")
    
    all_signals = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    watchlist = ["BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "AVAX", "LINK", "MATIC", "UNI"]
    
    for idx, symbol in enumerate(watchlist):
        progress_bar.progress((idx + 1) / len(watchlist))
        status_text.text(f"🔄 Scanning {symbol}...")
        
        result = analyze_mtf(symbol, buffer_pct, confirmation_candles, rr_sl, rr_tp, use_trailing, min_confirmations)
        
        if result:
            # Cek apakah ada pending signal
            pending = st.session_state.pending_signal.get(symbol)
            if pending:
                entry_display = pending["signal"]
                is_pending = True
                is_taken = pending.get("taken", False)
            else:
                entry_display = result["entry_signal"] if result["entry_signal"] else "⏳ WAIT"
                is_pending = False
                is_taken = False
            
            # Cek apakah sudah punya posisi
            existing_pos = get_position_status(symbol)
            has_position = existing_pos is not None
            
            # Simpan signal baru ke pending jika ada
            if result["entry_signal"] and symbol not in st.session_state.pending_signal:
                st.session_state.pending_signal[symbol] = {
                    "signal": result["entry_signal"],
                    "time": datetime.now(),
                    "entry": result["entry_price"],
                    "sl": result["stop_loss"],
                    "tp": result["take_profit"],
                    "taken": False
                }
                save_pending_signals(st.session_state.pending_signal)
                
                # Kirim Telegram
                if result["entry_signal"]:
                    rr_ratio = ((result["take_profit"] / result["entry_price"] - 1) / 
                               (result["stop_loss"] / result["entry_price"] - 1)) if result["stop_loss"] else 0
                    message = f"""⚡ NEW SIGNAL! (RR 3:7)

Coin : {symbol}
Signal : {result['entry_signal']}
Trend 1H : {result['trend_1h']}
Trend 15M : {result['trend_15m']}
Trend 5M : {result['trend_5m']}
BB Score : {result['bb_score']}
Confirmations : {result['confirmations']}/3

Entry : ${result['entry_price']:.4f}
SL : ${result['stop_loss']:.4f} ({format_percentage((result['stop_loss']/result['entry_price'] - 1)*100)})
TP : ${result['take_profit']:.4f} ({format_percentage((result['take_profit']/result['entry_price'] - 1)*100)})
RR Ratio : {rr_ratio:.2f}

Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                    send_telegram(message)
                    st.session_state.performance_stats["total_signals"] += 1
            
            # Tampilkan di tabel
            all_signals.append({
                "Coin": symbol,
                "Trend 1H": result["trend_1h"],
                "Trend 15M": result["trend_15m"],
                "Trend 5M": result["trend_5m"],
                "Signal": "🔵 TAKEN" if is_taken else "🟡 PENDING" if is_pending else entry_display,
                "BB Score": result["bb_score"],
                "RSI 5M": f"{result['rsi_5m']:.1f}",
                "RSI 15M": f"{result['rsi_15m']:.1f}",
                "Entry": format_price(result["entry_price"] * currency_rate) if result["entry_price"] else "-",
                "SL": format_price(result["stop_loss"] * currency_rate) if result["stop_loss"] else "-",
                "TP": format_price(result["take_profit"] * currency_rate) if result["take_profit"] else "-",
                "Confirm": f"{result['confirmations']}/3",
                "Position": "✅ Active" if has_position else "❌ No"
            })
    
    progress_bar.empty()
    status_text.empty()
    
    if all_signals:
        df_signals = pd.DataFrame(all_signals)
        st.dataframe(df_signals, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Tidak ada data")
    
    # =========================================================
    # PENDING SIGNALS DISPLAY
    # =========================================================
    if st.session_state.pending_signal:
        st.divider()
        st.subheader("⏳ Pending Signals (Aktif)")
        st.caption(f"Sinyal akan bertahan selama {hold_minutes} menit | RR 3:7")
        
        cols = st.columns(min(len(st.session_state.pending_signal), 4))
        for idx, (symbol, data) in enumerate(st.session_state.pending_signal.items()):
            col_idx = idx % len(cols)
            with cols[col_idx]:
                elapsed = (datetime.now() - data["time"]).seconds / 60
                remaining = max(0, hold_minutes - elapsed)
                rr = ((data["tp"] / data["entry"] - 1) / (data["sl"] / data["entry"] - 1)) if data["sl"] else 0
                
                # Cek apakah sudah diambil
                is_taken = data.get("taken", False)
                taken_text = "✅ TAKEN" if is_taken else "⏳ Available"
                
                st.markdown(f"""
                <div class="pending-signal">
                    <b>{symbol}</b> - {taken_text}<br>
                    {data['signal']}<br>
                    Entry: {format_price(data['entry'] * currency_rate)}<br>
                    SL: {format_price(data['sl'] * currency_rate)}<br>
                    TP: {format_price(data['tp'] * currency_rate)}<br>
                    RR: {rr:.2f}<br>
                    ⏱️ {remaining:.0f}m remaining
                </div>
                """, unsafe_allow_html=True)
                
                # Tombol "Take This Trade" jika belum diambil
                if not is_taken and remaining > 0:
                    if st.button(f"✅ Take {symbol}", key=f"take_{symbol}"):
                        # Tambahkan ke positions
                        new_position = {
                            "symbol": symbol,
                            "entry_price": data["entry"],
                            "quantity": 0.01,  # Default quantity
                            "entry_date": datetime.now().strftime("%Y-%m-%d"),
                            "signal": data["signal"],
                            "sl": data["sl"],
                            "tp": data["tp"],
                            "created_at": datetime.now().isoformat()
                        }
                        st.session_state.positions.append(new_position)
                        save_positions(st.session_state.positions)
                        
                        # Tandai sebagai taken
                        st.session_state.pending_signal[symbol]["taken"] = True
                        save_pending_signals(st.session_state.pending_signal)
                        
                        # Kirim Telegram
                        send_telegram(f"✅ POSITION TAKEN: {symbol} at ${data['entry']:.4f}")
                        
                        st.success(f"✅ {symbol} position added!")
                        st.rerun()
    
    # =========================================================
    # COIN DETAIL
    # =========================================================
    st.divider()
    st.subheader("📈 Coin Detail")
    
    selected_coin = st.selectbox("Select Coin", watchlist)
    
    result = analyze_mtf(selected_coin, buffer_pct, confirmation_candles, rr_sl, rr_tp, use_trailing, min_confirmations)
    
    if result:
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Trend 1H", result["trend_1h"])
        col2.metric("Trend 15M", result["trend_15m"])
        col3.metric("Trend 5M", result["trend_5m"])
        col4.metric("Support", format_price(result["support"] * currency_rate))
        col5.metric("Resistance", format_price(result["resistance"] * currency_rate))
        col6.metric("BB Score", f"{result['bb_score']}/100")
        
        pending = st.session_state.pending_signal.get(selected_coin)
        
        if pending and not pending.get("taken", False):
            rr = ((pending["tp"] / pending["entry"] - 1) / (pending["sl"] / pending["entry"] - 1)) if pending["sl"] else 0
            st.markdown(f"""
            <div class="pending-signal">
                ⏳ PENDING SIGNAL: {pending['signal']}<br>
                Entry: {format_price(pending['entry'] * currency_rate)} | 
                SL: {format_price(pending['sl'] * currency_rate)} | 
                TP: {format_price(pending['tp'] * currency_rate)}<br>
                RR: {rr:.2f}
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"✅ Take This Trade ({selected_coin})"):
                new_position = {
                    "symbol": selected_coin,
                    "entry_price": pending["entry"],
                    "quantity": 0.01,
                    "entry_date": datetime.now().strftime("%Y-%m-%d"),
                    "signal": pending["signal"],
                    "sl": pending["sl"],
                    "tp": pending["tp"],
                    "created_at": datetime.now().isoformat()
                }
                st.session_state.positions.append(new_position)
                save_positions(st.session_state.positions)
                st.session_state.pending_signal[selected_coin]["taken"] = True
                save_pending_signals(st.session_state.pending_signal)
                send_telegram(f"✅ POSITION TAKEN: {selected_coin} at ${pending['entry']:.4f}")
                st.success(f"✅ {selected_coin} position added!")
                st.rerun()
        elif result["entry_signal"]:
            if "BUY" in result["entry_signal"]:
                st.markdown(f'<div class="signal-buy">🚀 {result["entry_signal"]}</div>', unsafe_allow_html=True)
            elif "SELL" in result["entry_signal"]:
                st.markdown(f'<div class="signal-sell">🔻 {result["entry_signal"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="signal-hold">⏳ WAIT - No Signal</div>', unsafe_allow_html=True)
        
        fig = create_chart(result, selected_coin, currency_rate)
        st.plotly_chart(fig, use_container_width=True)

# =========================================================
# TAB 2: MY POSITIONS
# =========================================================
with tab2:
    st.subheader("📈 My Positions")
    
    # Summary
    total_value = 0
    total_pnl = 0
    winning_positions = 0
    
    for pos in st.session_state.positions:
        try:
            df = get_data(pos["symbol"], "1h", "1d")
            if df is not None and not df.empty:
                current_price = df["Close"].iloc[-1]
                value = current_price * pos["quantity"]
                invested = pos["entry_price"] * pos["quantity"]
                pnl = value - invested
                total_value += value
                total_pnl += pnl
                if pnl > 0:
                    winning_positions += 1
        except:
            pass
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Total Value", f"${total_value:,.2f}")
    c2.metric("📈 Total P&L", f"${total_pnl:,.2f}", delta=f"{total_pnl:+.2f}", delta_color="normal")
    c3.metric("🎯 Win Rate", f"{winning_positions / max(1, len(st.session_state.positions)) * 100:.0f}%")
    c4.metric("📊 Positions", len(st.session_state.positions))
    
    st.divider()
    
    # Position Cards
    if st.session_state.positions:
        for idx, pos in enumerate(st.session_state.positions):
            symbol = pos["symbol"]
            entry_price = pos["entry_price"]
            quantity = pos["quantity"]
            entry_date = pos.get("entry_date", "N/A")
            signal = pos.get("signal", "Unknown")
            
            # Get current price
            df = get_data(symbol, "1h", "1d")
            if df is not None and not df.empty:
                current_price = df["Close"].iloc[-1]
                pnl = (current_price - entry_price) * quantity
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                
                with st.container():
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        st.markdown(f"### {symbol}")
                        st.caption(f"Entry: {entry_date}")
                        if pnl > 0:
                            st.markdown(f'<span class="profit">💰 ${pnl:,.2f} ({pnl_pct:+.2f}%)</span>', unsafe_allow_html=True)
                        elif pnl < 0:
                            st.markdown(f'<span class="loss">📉 ${pnl:,.2f} ({pnl_pct:+.2f}%)</span>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<span class="neutral">➖ ${pnl:,.2f} (0.00%)</span>', unsafe_allow_html=True)
                        st.caption(f"Entry: ${entry_price:,.2f} | Current: ${current_price:,.2f}")
                    
                    with col2:
                        st.metric("Quantity", f"{quantity:.4f}")
                        st.metric("Value", f"${current_price * quantity:,.2f}")
                        st.caption(f"Signal: {signal}")
                    
                    with col3:
                        st.markdown("#### Actions")
                        if st.button(f"📈 Chart", key=f"chart_pos_{idx}"):
                            st.session_state[f"show_chart_pos_{idx}"] = not st.session_state.get(f"show_chart_pos_{idx}", False)
                        if st.button(f"❌ Close", key=f"close_pos_{idx}"):
                            # Log close
                            st.session_state.signal_history.append({
                                "symbol": symbol,
                                "entry_price": entry_price,
                                "exit_price": current_price,
                                "quantity": quantity,
                                "pnl": pnl,
                                "exit_date": datetime.now().isoformat()
                            })
                            # Update performance
                            if pnl > 0:
                                st.session_state.performance_stats["wins"] += 1
                            else:
                                st.session_state.performance_stats["losses"] += 1
                            st.session_state.performance_stats["total_profit"] += pnl
                            
                            del st.session_state.positions[idx]
                            save_positions(st.session_state.positions)
                            st.rerun()
                        
                        if st.session_state.get(f"show_chart_pos_{idx}", False):
                            # Simple chart untuk posisi
                            st.caption("📊 Price Chart")
                            fig = make_subplots(rows=1, cols=1)
                            fig.add_trace(go.Scatter(
                                x=df["Time"].tail(30),
                                y=df["Close"].tail(30),
                                mode="lines",
                                line=dict(color="#00a2ff", width=2),
                                name="Price"
                            ))
                            fig.add_hline(y=entry_price, line_dash="solid", line_color="#ff00ff",
                                         annotation_text=f"Entry: ${entry_price:.2f}")
                            fig.update_layout(template="plotly_dark", height=200, margin=dict(l=10, r=10, t=20, b=20),
                                             paper_bgcolor="#0a0a1a", plot_bgcolor="#0a0a1a")
                            st.plotly_chart(fig, use_container_width=True)
                    
                    st.divider()
            else:
                st.warning(f"⚠️ No data for {symbol}")
    else:
        st.info("📭 No positions yet. Take a signal from the Scanner tab!")

# =========================================================
# TRADE HISTORY
# =========================================================
if st.session_state.signal_history:
    st.divider()
    st.subheader("📜 Trade History")
    df_history = pd.DataFrame(st.session_state.signal_history)
    st.dataframe(df_history, use_container_width=True, hide_index=True)

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"""
🔄 Data dari Yahoo Finance | Multi Timeframe: 1H, 15M, 5M  
💱 Currency: {currency} | 🔄 Auto Refresh: {refresh} detik  
📊 Total Coins: {len(watchlist)} | 📈 Positions: {len(st.session_state.positions)}
🎯 RR Strategy: 3:7 | 🛡️ Signal Hold: {hold_minutes}m  
🚀 Trailing Stop: {'Active' if use_trailing else 'Inactive'}
""")
