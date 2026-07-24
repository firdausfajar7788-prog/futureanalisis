import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from pymongo import MongoClient
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import time

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Crypto Scanner PRO - MongoDB",
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
    
    .metric-green {
        color: #00ff88 !important;
        font-weight: 700;
    }
    .metric-red {
        color: #ff3b5c !important;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# MONGODB CONNECTION
# =========================================================
@st.cache_resource
def get_mongo_client():
    """Mendapatkan koneksi ke MongoDB Atlas"""
    try:
        connection_string = st.secrets["mongodb"]["connection_string"]
        client = MongoClient(connection_string)
        # Test koneksi
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"❌ Gagal konek ke MongoDB: {e}")
        return None

@st.cache_resource
def get_mongo_db():
    """Mendapatkan database MongoDB"""
    client = get_mongo_client()
    if client:
        db_name = st.secrets["mongodb"]["database_name"]
        return client[db_name]
    return None

# =========================================================
# FUNGSI MANAJEMEN WATCHLIST (MONGODB VERSION)
# =========================================================
def get_watchlist():
    """Ambil daftar coin dari MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["watchlist_collection"]]
            # Ambil semua coin, urutkan berdasarkan waktu tambah
            docs = collection.find({}).sort("added_at", 1)
            watchlist = [doc["symbol"] for doc in docs if "symbol" in doc]
            if watchlist:
                return watchlist
        except Exception as e:
            st.error(f"❌ Gagal ambil watchlist: {e}")
    
    # Default jika tidak ada data
    return ["BTC"]

def add_coin_to_watchlist(coin):
    """Tambah coin ke watchlist MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["watchlist_collection"]]
            # Cek apakah coin sudah ada
            existing = collection.find_one({"symbol": coin.upper().strip()})
            if existing:
                return False
            
            # Tambah coin baru
            collection.insert_one({
                "symbol": coin.upper().strip(),
                "added_at": datetime.now()
            })
            return True
        except Exception as e:
            st.error(f"❌ Gagal tambah coin: {e}")
            return False
    return False

def remove_coin_from_watchlist(coin):
    """Hapus coin dari watchlist MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["watchlist_collection"]]
            result = collection.delete_one({"symbol": coin.upper().strip()})
            return result.deleted_count > 0
        except Exception as e:
            st.error(f"❌ Gagal hapus coin: {e}")
            return False
    return False

def save_signal_history(symbol, signal_data):
    """Simpan riwayat sinyal ke MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["signal_history_collection"]]
            doc = {
                "symbol": symbol,
                "signal": signal_data.get("signal"),
                "entry_price": signal_data.get("entry"),
                "stop_loss": signal_data.get("sl"),
                "take_profit": signal_data.get("tp"),
                "trend_1h": signal_data.get("trend_1h"),
                "trend_15m": signal_data.get("trend_15m"),
                "timestamp": datetime.now()
            }
            collection.insert_one(doc)
            return True
        except Exception as e:
            st.error(f"❌ Gagal simpan signal history: {e}")
            return False
    return False

def get_signal_history(limit=100):
    """Ambil riwayat sinyal dari MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["signal_history_collection"]]
            docs = collection.find({}).sort("timestamp", -1).limit(limit)
            return list(docs)
        except Exception as e:
            st.error(f"❌ Gagal ambil signal history: {e}")
            return []
    return []

def save_performance_stats(stats):
    """Simpan statistik performa ke MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["performance_collection"]]
            # Update atau insert
            collection.update_one(
                {"_id": "performance_stats"},
                {"$set": {
                    **stats,
                    "updated_at": datetime.now()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            st.error(f"❌ Gagal simpan performance stats: {e}")
            return False
    return False

def get_performance_stats():
    """Ambil statistik performa dari MongoDB"""
    db = get_mongo_db()
    if db:
        try:
            collection = db[st.secrets["mongodb"]["performance_collection"]]
            doc = collection.find_one({"_id": "performance_stats"})
            if doc:
                # Hapus _id agar bisa di-load ke session state
                doc.pop("_id", None)
                doc.pop("updated_at", None)
                return doc
        except Exception as e:
            st.error(f"❌ Gagal ambil performance stats: {e}")
            return None
    return None

# =========================================================
# INISIALISASI SESSION STATE
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()

if "last_alert" not in st.session_state:
    st.session_state.last_alert = {}

if "selected_coin" not in st.session_state:
    st.session_state.selected_coin = st.session_state.watchlist[0] if st.session_state.watchlist else "BTC"

if "pending_signal" not in st.session_state:
    st.session_state.pending_signal = {}

if "signal_history" not in st.session_state:
    st.session_state.signal_history = get_signal_history()

if "performance_stats" not in st.session_state:
    stats = get_performance_stats()
    if stats:
        st.session_state.performance_stats = stats
    else:
        st.session_state.performance_stats = {
            "total_signals": 0,
            "wins": 0,
            "losses": 0,
            "total_profit": 0
        }

# =========================================================
# TELEGRAM FUNCTIONS (DENGAN ST.SECRETS)
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
# TITLE
# =========================================================
st.title("🚀 Crypto Scanner PRO - MongoDB")
st.caption("Multi Timeframe Analysis: 1H Trend | 15M Trend + BB | 5M Entry (Optimized RR 3:7)")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("📋 Watchlist")
    
    db = get_mongo_db()
    if db:
        st.success("✅ MongoDB Connected")
    else:
        st.error("❌ MongoDB Error")
    
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_coin = st.text_input("Add Coin", placeholder="PEPE", label_visibility="collapsed")
    with col_add2:
        if st.button("➕", use_container_width=True):
            if new_coin:
                coin = new_coin.upper().strip()
                if coin not in st.session_state.watchlist:
                    if add_coin_to_watchlist(coin):
                        st.session_state.watchlist.append(coin)
                        st.rerun()
                    else:
                        st.error("❌ Gagal tambah coin!")
                else:
                    st.warning(f"⚠️ {coin} already exists!")
    
    st.markdown("**Your Coins:**")
    cols = st.columns(3)
    for idx, coin in enumerate(st.session_state.watchlist):
        col_idx = idx % 3
        with cols[col_idx]:
            if st.button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
                if remove_coin_from_watchlist(coin):
                    st.session_state.watchlist.remove(coin)
                    st.rerun()
                else:
                    st.error(f"❌ Gagal hapus {coin}!")
    
    st.divider()
    
    st.subheader("📊 Trading Settings")
    refresh = st.slider("🔄 Refresh (detik)", 5, 60, 10)
    currency = st.selectbox("💱 Currency", ["USD", "IDR"])
    leverage = st.slider("⚡ Leverage", 1, 125, 10)
    position_size = st.number_input("💰 Position Size (USD)", 10, 100000, 100, step=10)
    
    # === RISK MANAGEMENT SETTINGS ===
    st.subheader("🎯 Risk Management (RR 3:7)")
    
    rr_sl = st.slider(
        "Stop Loss (ATR)",
        min_value=1.0,
        max_value=5.0,
        value=3.0,
        step=0.5,
        help="Semakin besar ATR, SL semakin longgar (kurang kena SL)"
    )
    
    rr_tp = st.slider(
        "Take Profit (ATR)",
        min_value=3.0,
        max_value=12.0,
        value=7.0,
        step=0.5,
        help="Semakin besar ATR, profit potensial semakin besar"
    )
    
    use_trailing = st.toggle(
        "🚀 Use Trailing Stop",
        value=True,
        help="Trailing stop mengunci profit saat harga bergerak sesuai arah"
    )
    
    min_confirmations = st.slider(
        "Minimal Konfirmasi",
        min_value=1,
        max_value=3,
        value=2,
        help="Berapa banyak konfirmasi yang dibutuhkan sebelum entry (Support/Resistance/Volume)"
    )
    
    # === STABILITAS SETTINGS ===
    st.subheader("🛡️ Signal Stability")
    hold_minutes = st.slider("Hold Signal (menit)", 5, 30, 15, help="Berapa lama sinyal bertahan meskipun kondisi berubah")
    buffer_pct = st.slider("Buffer Level (%)", 0.1, 1.0, 0.5, 0.1, help="Buffer untuk support/resistance")
    confirmation_candles = st.slider("Konfirmasi Candle", 1, 5, 3, help="Minimal candle untuk konfirmasi")
    
    st.divider()
    
    st.subheader("📱 Telegram Alert")
    if st.button("🚀 Test Telegram", use_container_width=True):
        send_telegram("🚀 Telegram Connected! Scanner PRO Aktif dengan RR 3:7.")
        st.success("✅ Pesan test terkirim!")
    
    st.divider()
    
    st.subheader("📊 Status")
    st.metric("Total Coins", len(st.session_state.watchlist))
    st.metric("Storage", "✅ MongoDB Atlas")
    st.metric("Pending Signals", len(st.session_state.pending_signal))
    st.metric("Win Rate", f"{st.session_state.performance_stats['wins'] / max(1, st.session_state.performance_stats['total_signals']) * 100:.1f}%")
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
    if pd.isna(value) or value is None:
        return "-"
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

def format_percentage(value):
    if pd.isna(value) or value is None:
        return "-"
    return f"{value:.1f}%"

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
# RISK MANAGEMENT - RR 3:7 DENGAN TRAILING STOP
# =========================================================
def calculate_risk_management_advanced(df_5m, entry_signal, entry_price, rr_sl=3.0, rr_tp=7.0, use_trailing=True):
    """
    Advanced Risk Management dengan:
    - SL = rr_sl x ATR
    - TP = rr_tp x ATR
    - Trailing Stop otomatis
    - Dynamic adjustment berdasarkan volatilitas
    """
    
    # ATR periode 20 untuk stabilitas
    atr = ATR(df_5m, period=20)
    atr_value = atr.iloc[-1] if len(atr) > 0 and not pd.isna(atr.iloc[-1]) else 0.01
    
    # Minimal ATR 0.5% dari harga
    min_atr = entry_price * 0.005
    atr_value = max(atr_value, min_atr)
    
    # === HITUNG SL & TP ===
    if entry_signal and "BUY" in entry_signal:
        stop_loss = entry_price - atr_value * rr_sl
        take_profit = entry_price + atr_value * rr_tp
        
        # === TRAILING STOP UNTUK BUY ===
        if use_trailing and len(df_5m) > 5:
            highest_high = df_5m["High"].tail(5).max()
            # Naikkan SL ke 0.5 ATR di bawah highest high
            new_sl = max(highest_high - atr_value * 0.5, stop_loss)
            stop_loss = max(new_sl, stop_loss)  # SL tidak pernah turun
        
    elif entry_signal and "SELL" in entry_signal:
        stop_loss = entry_price + atr_value * rr_sl
        take_profit = entry_price - atr_value * rr_tp
        
        # === TRAILING STOP UNTUK SELL ===
        if use_trailing and len(df_5m) > 5:
            lowest_low = df_5m["Low"].tail(5).min()
            new_sl = min(lowest_low + atr_value * 0.5, stop_loss)
            stop_loss = min(new_sl, stop_loss)  # SL tidak pernah naik
    
    else:
        stop_loss = take_profit = None
    
    # === VALIDASI ===
    if stop_loss and take_profit:
        # SL tidak boleh terlalu dekat (minimal 1%)
        if abs(stop_loss - entry_price) / entry_price < 0.01:
            stop_loss = entry_price * 0.99 if entry_signal and "BUY" in entry_signal else entry_price * 1.01
    
    return stop_loss, take_profit, atr_value

# =========================================================
# ANALISIS MULTI TIMEFRAME (DENGAN STABILITAS & RR 3:7)
# =========================================================
def analyze_mtf(symbol, buffer_pct=0.5, confirmation_candles=3, rr_sl=3.0, rr_tp=7.0, use_trailing=True, min_confirmations=2):
    # --- 1H ---
    df_1h = get_data_safe(symbol, "1h", min_candles=30)
    if df_1h is None:
        return None
    
    # --- 15M ---
    df_15m = get_data_safe(symbol, "15m", min_candles=50)
    if df_15m is None:
        df_15m = df_1h.copy()
    
    # --- 5M ---
    df_5m = get_data_safe(symbol, "5m", min_candles=20)
    if df_5m is None:
        df_5m = df_15m.copy()
    
    # --- TREND ANALYSIS ---
    trend_1h = analyze_trend(df_1h, "1H")
    trend_15m = analyze_trend(df_15m, "15M")
    trend_5m = analyze_trend(df_5m, "5M")
    
    # --- 15M BB Analysis ---
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
    
    # --- SUPPORT/RESISTANCE 15M ---
    period = 20
    recent_high = df_15m["High"].tail(period).max()
    recent_low = df_15m["Low"].tail(period).min()
    pivot = (df_15m["High"].tail(period).max() + df_15m["Low"].tail(period).min() + df_15m["Close"].tail(period).mean()) / 3
    r1 = 2 * pivot - recent_low
    s1 = 2 * pivot - recent_high
    
    support = s1
    resistance = r1
    
    # --- BUFFER LEVEL (STABILITAS) ---
    support_buffer = support * (1 - buffer_pct / 100)
    resistance_buffer = resistance * (1 + buffer_pct / 100)
    
    # --- KONFIRMASI CANDLE (STABILITAS) ---
    support_confirmed = sum(df_5m["Close"].tail(confirmation_candles) > support_buffer) >= confirmation_candles
    resistance_confirmed = sum(df_5m["Close"].tail(confirmation_candles) > resistance_buffer) >= confirmation_candles
    
    # --- BB SCORING ---
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
    
    # --- 5M ENTRY SIGNAL (DENGAN STABILITAS) ---
    df_5m["RSI"] = RSI(df_5m, 14)
    df_5m["Volume_MA"] = df_5m["Volume"].rolling(5).mean()
    
    last_5m = df_5m.iloc[-1]
    price_5m = last_5m["Close"]
    rsi_5m = last_5m["RSI"] if not pd.isna(last_5m["RSI"]) else 50
    
    # --- VOLUME SPIKE KONSISTEN (2 CANDLE TERAKHIR) ---
    vol = df_5m["Volume"].iloc[-1]
    vol_ma = df_5m["Volume_MA"].iloc[-1] if not pd.isna(df_5m["Volume_MA"].iloc[-1]) else vol
    vol_spike = vol > vol_ma * 1.5 if vol_ma > 0 else False
    
    if len(df_5m) > 1:
        vol_prev = df_5m["Volume"].iloc[-2]
        vol_ma_prev = df_5m["Volume_MA"].iloc[-2] if not pd.isna(df_5m["Volume_MA"].iloc[-2]) else vol_prev
        vol_spike_prev = vol_prev > vol_ma_
