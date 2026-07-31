import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from datetime import datetime, timedelta
import time
import sqlite3
import json
import ta
import numpy as np
from streamlit_autorefresh import st_autorefresh
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import warnings
warnings.filterwarnings('ignore')

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="🤖",
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
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0,255,255,0.1);
    }
    .signal-buy {
        background: linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,255,136,0.05));
        border: 1px solid #00ff88;
        border-radius: 12px;
        padding: 12px 20px;
        color: #00ff88;
        font-weight: 600;
        font-size: 18px;
    }
    .signal-sell {
        background: linear-gradient(135deg, rgba(255,59,92,0.15), rgba(255,59,92,0.05));
        border: 1px solid #ff3b5c;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ff3b5c;
        font-weight: 600;
        font-size: 18px;
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
        box-shadow: 0 0 30px rgba(0,255,255,0.3);
    }
    .score-high { color: #00ff88; font-weight: 700; font-size: 24px; }
    .score-mid { color: #ffaa00; font-weight: 700; font-size: 24px; }
    .score-low { color: #ff3b5c; font-weight: 700; font-size: 24px; }
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
# DATABASE SQLITE
# =========================================================
DB_PATH = "crypto_bot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabel watchlist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE,
            added_at TIMESTAMP
        )
    ''')
    
    # Tabel coins
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            name TEXT,
            category TEXT,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    ''')
    
    # Tabel signal_history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            signal TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            trend_1h TEXT,
            trend_15m TEXT,
            score REAL,
            confidence REAL,
            ai_signal TEXT,
            smart_money_score REAL,
            timestamp TIMESTAMP
        )
    ''')
    
    # Tabel trades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            type TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            position_size REAL,
            leverage INTEGER,
            score REAL,
            confidence REAL,
            signal TEXT,
            status TEXT,
            profit_pct REAL,
            exit_price REAL,
            entry_time TIMESTAMP,
            exit_time TIMESTAMP,
            smart_money_score REAL,
            ai_score REAL
        )
    ''')
    
    # Tabel performance
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    # Tabel daily_stats - FIX: AUTOINCREMENT (bukan AUTOINLINE!)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            total_signals INTEGER,
            wins INTEGER,
            losses INTEGER,
            profit REAL,
            win_rate REAL
        )
    ''')
    
    # Tabel ml_predictions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ml_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            prediction INTEGER,
            confidence REAL,
            buy_prob REAL,
            sell_prob REAL,
            hold_prob REAL,
            timestamp TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def migrate_db():
    """Migrasi database untuk menambahkan kolom yang hilang"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Cek apakah kolom smart_money_score ada di tabel trades
    cursor.execute("PRAGMA table_info(trades)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'smart_money_score' not in columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN smart_money_score REAL")
        print("✅ Added smart_money_score to trades")
    
    if 'ai_score' not in columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN ai_score REAL")
        print("✅ Added ai_score to trades")
    
    if 'exit_price' not in columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN exit_price REAL")
        print("✅ Added exit_price to trades")
    
    conn.commit()
    conn.close()

# ==================== WATCHLIST ====================
def get_watchlist():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM watchlist ORDER BY added_at")
    rows = cursor.fetchall()
    conn.close()
    return [row['symbol'] for row in rows] if rows else ["BTC"]

def add_coin(symbol):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO watchlist (symbol, added_at) VALUES (?, ?)",
            (symbol.upper(), datetime.now())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def remove_coin(symbol):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def sync_watchlist_from_coins():
    """Sinkronisasi dari tabel coins ke watchlist"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM coins WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    
    for row in rows:
        add_coin(row['symbol'])
    return len(rows)

# ==================== COINS CRUD ====================
def create_coin(symbol, name=None, category=None, active=True):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO coins (symbol, name, category, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (symbol.upper(), name or symbol.upper(), category or "Crypto", 1 if active else 0, datetime.now(), datetime.now()))
        conn.commit()
        conn.close()
        return True, f"✅ {symbol.upper()} berhasil ditambahkan!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"⚠️ {symbol.upper()} sudah ada!"

def get_all_coins(active_only=False):
    conn = get_db()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM coins WHERE active = 1 ORDER BY symbol")
    else:
        cursor.execute("SELECT * FROM coins ORDER BY symbol")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_coin(symbol, updates):
    conn = get_db()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [datetime.now(), symbol.upper()]
    try:
        cursor.execute(f"UPDATE coins SET {set_clause}, updated_at = ? WHERE symbol = ?", values)
        conn.commit()
        conn.close()
        return True, f"✅ {symbol.upper()} berhasil diupdate!"
    except Exception as e:
        conn.close()
        return False, f"❌ Gagal: {e}"

def delete_coin(symbol):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM coins WHERE symbol = ?", (symbol.upper(),))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0, f"🗑️ {symbol.upper()} berhasil dihapus!"

# ==================== SIGNAL HISTORY ====================
def save_signal(signal_data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO signal_history (
            symbol, signal, entry_price, stop_loss, take_profit,
            trend_1h, trend_15m, score, confidence, ai_signal, smart_money_score, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        signal_data.get('symbol'),
        signal_data.get('signal'),
        signal_data.get('entry_price'),
        signal_data.get('stop_loss'),
        signal_data.get('take_profit'),
        signal_data.get('trend_1h'),
        signal_data.get('trend_15m'),
        signal_data.get('score', 0),
        signal_data.get('confidence', 0),
        signal_data.get('ai_signal'),
        signal_data.get('smart_money_score', 0),
        datetime.now()
    ))
    conn.commit()
    conn.close()
    return True

def get_signal_history(limit=100):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signal_history ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ==================== TRADES ====================
def save_trade(trade_data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (
            symbol, type, entry_price, stop_loss, take_profit,
            position_size, leverage, score, confidence, signal,
            status, entry_time, smart_money_score, ai_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        trade_data.get('symbol'),
        trade_data.get('type'),
        trade_data.get('entry_price'),
        trade_data.get('stop_loss'),
        trade_data.get('take_profit'),
        trade_data.get('position_size', 100),
        trade_data.get('leverage', 10),
        trade_data.get('score', 0),
        trade_data.get('confidence', 0),
        trade_data.get('signal'),
        trade_data.get('status', 'OPEN'),
        trade_data.get('entry_time', datetime.now()),
        trade_data.get('smart_money_score', 0),
        trade_data.get('ai_score', 0)
    ))
    conn.commit()
    conn.close()
    return True

def get_trades(limit=100):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_trade(trade_id, updates):
    conn = get_db()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [trade_id]
    cursor.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True

# ==================== PERFORMANCE ====================
def update_performance(stats):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO performance (key, value, updated_at) VALUES (?, ?, ?)",
        ("performance_stats", json.dumps(stats), datetime.now())
    )
    conn.commit()
    conn.close()
    return True

def get_performance():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM performance WHERE key = 'performance_stats'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row['value'])
    return {"total_signals": 0, "wins": 0, "losses": 0, "total_profit": 0, "win_rate": 0}

# ==================== DAILY STATS ====================
def save_daily_stats(stats):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO daily_stats (date, total_signals, wins, losses, profit, win_rate) VALUES (?, ?, ?, ?, ?, ?)",
        (stats['date'], stats['total_signals'], stats['wins'], stats['losses'], stats['profit'], stats['win_rate'])
    )
    conn.commit()
    conn.close()

# ==================== ML PREDICTIONS ====================
def save_prediction(pred_data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ml_predictions (symbol, prediction, confidence, buy_prob, sell_prob, hold_prob, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        pred_data.get('symbol'),
        pred_data.get('prediction'),
        pred_data.get('confidence'),
        pred_data.get('buy_prob', 0),
        pred_data.get('sell_prob', 0),
        pred_data.get('hold_prob', 0),
        datetime.now()
    ))
    conn.commit()
    conn.close()

def get_predictions(symbol=None, limit=50):
    conn = get_db()
    cursor = conn.cursor()
    if symbol:
        cursor.execute("SELECT * FROM ml_predictions WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?", (symbol, limit))
    else:
        cursor.execute("SELECT * FROM ml_predictions ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# =========================================================
# TELEGRAM FUNCTIONS
# =========================================================
def send_telegram(message):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
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
# GET DATA
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
# SMART MONEY CONCEPTS
# =========================================================
def find_order_blocks(df, lookback=20):
    blocks = []
    for i in range(lookback, len(df)-1):
        if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
            high = df['High'].iloc[i-1]
            low = df['Low'].iloc[i-1]
            if df['High'].iloc[i] > high:
                blocks.append({'type': 'BULLISH', 'high': float(high), 'low': float(low)})
        elif df['Close'].iloc[i] < df['Close'].iloc[i-1]:
            high = df['High'].iloc[i-1]
            low = df['Low'].iloc[i-1]
            if df['Low'].iloc[i] < low:
                blocks.append({'type': 'BEARISH', 'high': float(high), 'low': float(low)})
    return blocks[-3:] if len(blocks) > 3 else blocks

def find_fair_value_gaps(df, lookback=20):
    fvgs = []
    for i in range(2, len(df)-1):
        if df['Low'].iloc[i] > df['High'].iloc[i-2]:
            fvgs.append({'type': 'BULLISH', 'high': float(df['Low'].iloc[i]), 'low': float(df['High'].iloc[i-2])})
        elif df['High'].iloc[i] < df['Low'].iloc[i-2]:
            fvgs.append({'type': 'BEARISH', 'high': float(df['Low'].iloc[i-2]), 'low': float(df['High'].iloc[i])})
    return fvgs[-3:] if len(fvgs) > 3 else fvgs

def find_liquidity_sweeps(df, lookback=20, buffer=0.01):
    sweeps = []
    recent_high = df['High'].tail(lookback).max()
    recent_low = df['Low'].tail(lookback).min()
    if df['High'].iloc[-1] > recent_high * (1 + buffer):
        sweeps.append({'type': 'HIGH_SWEEP', 'level': float(recent_high), 'swept_at': float(df['High'].iloc[-1])})
    if df['Low'].iloc[-1] < recent_low * (1 - buffer):
        sweeps.append({'type': 'LOW_SWEEP', 'level': float(recent_low), 'swept_at': float(df['Low'].iloc[-1])})
    return sweeps

def detect_market_structure(df, lookback=10):
    structure = {'hh': False, 'hl': False, 'lh': False, 'll': False, 'bos': False, 'choch': False}
    if len(df) < lookback * 2:
        return structure
    highs = df['High'].tail(lookback).values
    lows = df['Low'].tail(lookback).values
    if highs[-1] > highs[-2] and highs[-2] > highs[-3]:
        structure['hh'] = True
    if lows[-1] > lows[-2] and lows[-2] > lows[-3]:
        structure['hl'] = True
    if highs[-1] < highs[-2] and highs[-2] < highs[-3]:
        structure['lh'] = True
    if lows[-1] < lows[-2] and lows[-2] < lows[-3]:
        structure['ll'] = True
    if structure['hh'] or structure['ll']:
        structure['bos'] = True
    if (structure['hh'] and lows[-1] > lows[-2]) or (structure['ll'] and highs[-1] < highs[-2]):
        structure['choch'] = True
    return structure

def calculate_smart_money_score(df, lookback=20):
    score = 50
    reasons = []
    obs = find_order_blocks(df, lookback)
    if obs:
        if obs[-1]['type'] == 'BULLISH':
            score += 15
            reasons.append("Bullish Order Block")
        else:
            score -= 15
            reasons.append("Bearish Order Block")
    fvgs = find_fair_value_gaps(df, lookback)
    if fvgs:
        if fvgs[-1]['type'] == 'BULLISH':
            score += 15
            reasons.append("Bullish FVG")
        else:
            score -= 15
            reasons.append("Bearish FVG")
    sweeps = find_liquidity_sweeps(df, lookback)
    for sweep in sweeps:
        if sweep['type'] == 'HIGH_SWEEP':
            score += 10
            reasons.append("Liquidity Sweep Up")
        else:
            score -= 10
            reasons.append("Liquidity Sweep Down")
    structure = detect_market_structure(df, lookback)
    if structure.get('hh') and structure.get('hl'):
        score += 10
        reasons.append("Bullish Structure (HH+HL)")
    elif structure.get('lh') and structure.get('ll'):
        score -= 10
        reasons.append("Bearish Structure (LH+LL)")
    if structure.get('choch'):
        score += 5 if score >= 50 else -5
        reasons.append("Change of Character")
    score = max(0, min(100, score))
    return {'score': score, 'reasons': reasons}

# =========================================================
# AI PREDICTOR (Simple ML)
# =========================================================
class AIPredictor:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.features = []
    
    def _extract_features(self, df):
        features = pd.DataFrame()
        features['close'] = df['Close']
        features['high'] = df['High']
        features['low'] = df['Low']
        features['volume'] = df['Volume']
        features['return_1'] = df['Close'].pct_change()
        features['return_5'] = df['Close'].pct_change(5)
        features['return_10'] = df['Close'].pct_change(10)
        features['rsi'] = RSI(df, 14)
        macd, signal, hist = MACD(df)
        features['macd'] = macd
        features['macd_signal'] = signal
        features['macd_hist'] = hist
        features['atr'] = ATR(df, 14)
        bb_upper, bb_mid, bb_lower = BollingerBands(df)
        features['bb_pct'] = (df['Close'] - bb_lower) / (bb_upper - bb_lower)
        features = features.dropna()
        self.features = features.columns.tolist()
        return features
    
    def train(self, df):
        if len(df) < 100:
            return False
        features = self._extract_features(df)
        future_return = df['Close'].shift(-5) / df['Close'] - 1
        target = pd.Series(index=df.index, dtype=int)
        target[future_return > 0.02] = 1
        target[future_return < -0.02] = 2
        target[future_return.abs() <= 0.02] = 0
        valid_idx = features.index.intersection(target.dropna().index)
        X = features.loc[valid_idx]
        y = target.loc[valid_idx]
        if len(X) < 50:
            return False
        X_scaled = self.scaler.fit_transform(X)
        X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
        self.model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
        self.model.fit(X_train, y_train)
        self.is_trained = True
        return True
    
    def predict(self, df):
        default = {'signal': 0, 'confidence': 0, 'buy_prob': 0, 'sell_prob': 0, 'hold_prob': 100}
        if not self.is_trained or len(df) < 50:
            return default
        features = self._extract_features(df)
        if features.empty:
            return default
        X = features.iloc[-1:]
        X_scaled = self.scaler.transform(X)
        pred = self.model.predict(X_scaled)[0]
        proba = self.model.predict_proba(X_scaled)[0]
        if len(proba) < 3:
            proba = list(proba) + [0] * (3 - len(proba))
        return {
            'signal': int(pred),
            'confidence': float(max(proba) * 100),
            'buy_prob': float(proba[1] * 100) if len(proba) > 1 else 0,
            'sell_prob': float(proba[2] * 100) if len(proba) > 2 else 0,
            'hold_prob': float(proba[0] * 100) if len(proba) > 0 else 0
        }

_predictor = None

def get_predictor():
    global _predictor
    if _predictor is None:
        _predictor = AIPredictor()
    return _predictor

def safe_ai_score(df):
    default = {'score': 50, 'signal_text': '🟡 HOLD', 'confidence': 0, 'buy_prob': 0, 'sell_prob': 0, 'hold_prob': 100}
    try:
        predictor = get_predictor()
        if not predictor.is_trained:
            predictor.train(df)
        pred = predictor.predict(df)
        if pred['signal'] == 1:
            score = 50 + pred['buy_prob'] * 0.5
            signal_text = "🟢 BUY"
        elif pred['signal'] == 2:
            score = 50 - pred['sell_prob'] * 0.5
            signal_text = "🔴 SELL"
        else:
            score = 50
            signal_text = "🟡 HOLD"
        score = max(0, min(100, score))
        return {
            'score': score,
            'signal_text': signal_text,
            'confidence': pred['confidence'],
            'buy_prob': pred['buy_prob'],
            'sell_prob': pred['sell_prob'],
            'hold_prob': pred['hold_prob']
        }
    except:
        return default

# =========================================================
# ANALISIS TREND
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
    
    # BB Analysis 15M
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
    
    # Support/Resistance
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
    
    # BB Scoring
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
    
    # 5M Entry
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
        atr_value = ATR(df_5m, period=20).iloc[-1] if len(ATR(df_5m, period=20)) > 0 else 0.01
        min_atr = entry_price * 0.005
        atr_value = max(atr_value, min_atr)
        if "BUY" in entry_signal:
            stop_loss = entry_price - atr_value * rr_sl
            take_profit = entry_price + atr_value * rr_tp
        elif "SELL" in entry_signal:
            stop_loss = entry_price + atr_value * rr_sl
            take_profit = entry_price - atr_value * rr_tp
        else:
            stop_loss = take_profit = None
    else:
        entry_price = stop_loss = take_profit = None
        atr_value = 0.01
    
    # Smart Money Score
    sm_data = calculate_smart_money_score(df_5m)
    
    # AI Score
    ai_data = safe_ai_score(df_5m)
    
    # Combined Score
    total_score = (sm_data['score'] * 0.4 + ai_data['score'] * 0.4 + (bb_score + 50) * 0.2)
    total_score = max(0, min(100, total_score))
    
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
        "smart_money": sm_data,
        "ai": ai_data,
        "total_score": total_score,
        "df_1h": df_1h.tail(50),
        "df_15m": df_15m.tail(50),
        "df_5m": df_5m.tail(30)
    }

# =========================================================
# CREATE CHART
# =========================================================
def create_chart(result, symbol):
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.35, 0.2, 0.15, 0.15, 0.15],
        subplot_titles=("Price & Indicators (5M)", "RSI + BB (15M)", "MACD (15M)", "Stochastic (15M)", "Volume")
    )
    
    df = result["df_5m"]
    df_15m = result["df_15m"]
    
    fig.add_trace(
        go.Candlestick(
            x=df["Time"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            increasing_line_color="#00ff88",
            decreasing_line_color="#ff3b5c",
            name="Price (5M)"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=df["Close"].ewm(span=20).mean(),
            line=dict(color="#00a2ff", width=1.5),
            name="EMA20"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=df["Close"].ewm(span=50).mean(),
            line=dict(color="#ffaa00", width=1.5, dash="dash"),
            name="EMA50"
        ),
        row=1, col=1
    )
    
    fig.add_hline(y=result["support"], line_dash="dot", line_color="green", row=1, col=1)
    fig.add_hline(y=result["resistance"], line_dash="dot", line_color="red", row=1, col=1)
    
    if result["entry_signal"] and result["entry_price"]:
        fig.add_hline(y=result["entry_price"], line_dash="solid", line_color="#00ff88", row=1, col=1)
        if result["stop_loss"]:
            fig.add_hline(y=result["stop_loss"], line_dash="dash", line_color="#ff0000", row=1, col=1)
        if result["take_profit"]:
            fig.add_hline(y=result["take_profit"], line_dash="dash", line_color="#00ff00", row=1, col=1)
    
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=df_15m["RSI"], line=dict(color="#a855f7", width=2), name="RSI (15M)"),
        row=2, col=1
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    macd, signal, hist = MACD(df_15m)
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=macd, line=dict(color="#00a2ff", width=1.5), name="MACD"),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=signal, line=dict(color="#ff00ff", width=1.5), name="Signal"),
        row=3, col=1
    )
    colors = ["#00ff88" if h >= 0 else "#ff3b5c" for h in hist]
    fig.add_trace(
        go.Bar(x=df_15m["Time"], y=hist, marker_color=colors, opacity=0.4, name="Histogram"),
        row=3, col=1
    )
    
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=df_15m["STOCH_K"], line=dict(color="#ffaa00", width=1.5), name="Stoch K"),
        row=4, col=1
    )
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=df_15m["STOCH_D"], line=dict(color="#ff00ff", width=1.5), name="Stoch D"),
        row=4, col=1
    )
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=4, col=1)
    
    colors_vol = ["#00ff88" if c >= o else "#ff3b5c" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(
        go.Bar(x=df["Time"], y=df["Volume"], marker_color=colors_vol, opacity=0.5, name="Volume"),
        row=5, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=df["Volume"].rolling(5).mean(),
            line=dict(color="rgba(255,255,255,0.3)", width=1),
            name="Volume MA"
        ),
        row=5, col=1
    )
    
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
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        margin=dict(l=10, r=10, t=50, b=10)
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
    return fig

# =========================================================
# EXECUTE TRADE
# =========================================================
def execute_trade(symbol, df, balance=10000, position_size=100, leverage=10):
    result = analyze_mtf(symbol)
    if not result or not result["entry_signal"]:
        return None
    
    entry_price = result["entry_price"]
    stop_loss = result["stop_loss"]
    take_profit = result["take_profit"]
    
    if not entry_price or not stop_loss or not take_profit:
        return None
    
    trade = {
        'symbol': symbol,
        'type': 'BUY' if 'BUY' in result["entry_signal"] else 'SELL',
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'position_size': position_size,
        'leverage': leverage,
        'score': result['total_score'],
        'confidence': result['confirmations'] / 3 * 100,
        'signal': result["entry_signal"],
        'status': 'OPEN',
        'entry_time': datetime.now(),
        'smart_money_score': result['smart_money']['score'],
        'ai_score': result['ai']['score']
    }
    
    save_trade(trade)
    return trade

def monitor_positions():
    trades = get_trades()
    open_trades = [t for t in trades if t.get('status') == 'OPEN']
    
    for trade in open_trades:
        symbol = trade['symbol']
        ticker = yf.Ticker(f"{symbol}-USD")
        df = ticker.history(period="1d", interval="5m")
        if df.empty:
            continue
        current_price = df['Close'].iloc[-1]
        
        entry = trade['entry_price']
        sl = trade['stop_loss']
        tp = trade['take_profit']
        
        if trade['type'] == 'BUY':
            if current_price <= sl:
                trade['status'] = 'CLOSED'
                trade['exit_price'] = current_price
                trade['profit_pct'] = (current_price / entry - 1) * 100
                trade['exit_time'] = datetime.now()
                update_trade(trade['id'], trade)
                send_telegram(f"❌ SL HIT: {symbol} - Loss {trade['profit_pct']:.2f}%")
            elif current_price >= tp:
                trade['status'] = 'CLOSED'
                trade['exit_price'] = current_price
                trade['profit_pct'] = (current_price / entry - 1) * 100
                trade['exit_time'] = datetime.now()
                update_trade(trade['id'], trade)
                send_telegram(f"✅ TP HIT: {symbol} - Profit {trade['profit_pct']:.2f}%")
        else:
            if current_price >= sl:
                trade['status'] = 'CLOSED'
                trade['exit_price'] = current_price
                trade['profit_pct'] = (entry / current_price - 1) * 100
                trade['exit_time'] = datetime.now()
                update_trade(trade['id'], trade)
                send_telegram(f"❌ SL HIT: {symbol} - Loss {trade['profit_pct']:.2f}%")
            elif current_price <= tp:
                trade['status'] = 'CLOSED'
                trade['exit_price'] = current_price
                trade['profit_pct'] = (entry / current_price - 1) * 100
                trade['exit_time'] = datetime.now()
                update_trade(trade['id'], trade)
                send_telegram(f"✅ TP HIT: {symbol} - Profit {trade['profit_pct']:.2f}%")

# =========================================================
# BACKTEST
# =========================================================
def run_backtest(symbol, period="1mo", interval="15m", rr_ratio=3.0, sl_atr=1.5):
    ticker = yf.Ticker(f"{symbol}-USD")
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        return None
    
    balance = 10000
    trades = []
    in_position = False
    entry_price = 0
    trade_type = None
    sl = 0
    tp = 0
    atr = ATR(df, 14)
    
    for i in range(50, len(df)-1):
        window = df.iloc[:i+1].copy()
        if len(window) < 50:
            continue
        
        # Get signal
        result = analyze_mtf(symbol)
        if not result:
            continue
        
        current_price = df['Close'].iloc[i]
        
        if not in_position:
            if result["entry_signal"]:
                in_position = True
                entry_price = current_price
                trade_type = 'BUY' if 'BUY' in result["entry_signal"] else 'SELL'
                atr_value = atr.iloc[i] if i < len(atr) else atr.iloc[-1]
                
                if trade_type == 'BUY':
                    sl = entry_price - atr_value * sl_atr
                    tp = entry_price + atr_value * sl_atr * rr_ratio
                else:
                    sl = entry_price + atr_value * sl_atr
                    tp = entry_price - atr_value * sl_atr * rr_ratio
                
                trades.append({
                    'entry_time': df.index[i],
                    'entry_price': entry_price,
                    'type': trade_type,
                    'sl': sl,
                    'tp': tp
                })
        else:
            if trade_type == 'BUY':
                if current_price <= sl:
                    exit_price = sl
                    profit_pct = (exit_price / entry_price - 1) * 100
                    balance *= (1 + profit_pct/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct})
                elif current_price >= tp:
                    exit_price = tp
                    profit_pct = (exit_price / entry_price - 1) * 100
                    balance *= (1 + profit_pct/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct})
            else:
                if current_price >= sl:
                    exit_price = sl
                    profit_pct = (entry_price / exit_price - 1) * 100
                    balance *= (1 + profit_pct/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct})
                elif current_price <= tp:
                    exit_price = tp
                    profit_pct = (entry_price / exit_price - 1) * 100
                    balance *= (1 + profit_pct/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct})
    
    wins = len([t for t in trades if t.get('profit_pct', 0) > 0])
    total_profit = sum([t.get('profit_pct', 0) for t in trades])
    
    return {
        'trades': trades,
        'total_trades': len(trades),
        'wins': wins,
        'losses': len(trades) - wins,
        'win_rate': (wins / max(1, len(trades)) * 100),
        'total_profit': total_profit,
        'final_balance': balance,
        'total_return': (balance / 10000 - 1) * 100
    }

# =========================================================
# INITIALIZATION
# =========================================================
init_db()

# Session State
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()

if "selected_coin" not in st.session_state:
    st.session_state.selected_coin = st.session_state.watchlist[0] if st.session_state.watchlist else "BTC"

if "pending_signal" not in st.session_state:
    st.session_state.pending_signal = {}

if "signal_history" not in st.session_state:
    st.session_state.signal_history = get_signal_history()

if "performance_stats" not in st.session_state:
    st.session_state.performance_stats = get_performance()

if "backtest_result" not in st.session_state:
    st.session_state.backtest_result = None

# =========================================================
# MAIN TITLE
# =========================================================
st.title("🤖")
st.caption("Multi Timeframe: 1H | 15M | 5M | Smart Money | AI Prediction | Auto Trading")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("📋 Watchlist")
    st.success("✅ SQLite Connected")
    
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
                else:
                    st.warning(f"⚠️ {coin} already exists!")
    
    st.markdown("**Your Coins:**")
    cols = st.columns(3)
    for idx, coin in enumerate(st.session_state.watchlist):
        col_idx = idx % 3
        with cols[col_idx]:
            if st.button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
                if remove_coin(coin):
                    st.session_state.watchlist.remove(coin)
                    st.rerun()
                else:
                    st.error(f"❌ Gagal hapus {coin}!")
    
    st.divider()
    
    st.subheader("📊 Trading Settings")
    refresh = st.slider("🔄 Refresh (detik)", 10, 60, 30)
    leverage = st.slider("⚡ Leverage", 1, 125, 10)
    position_size = st.number_input("💰 Position Size (USD)", 10, 100000, 100, step=10)
    
    rr_sl = st.slider("Stop Loss (ATR)", 1.0, 5.0, 3.0, 0.5)
    rr_tp = st.slider("Take Profit (ATR)", 3.0, 12.0, 7.0, 0.5)
    use_trailing = st.toggle("🚀 Use Trailing Stop", value=True)
    
    hold_minutes = st.slider("Hold Signal (menit)", 5, 30, 15)
    buffer_pct = st.slider("Buffer Level (%)", 0.1, 1.0, 0.5, 0.1)
    confirmation_candles = st.slider("Konfirmasi Candle", 1, 5, 3)
    min_confirmations = st.slider("Min Konfirmasi", 1, 3, 2)
    
    st.divider()
    
    st.subheader("📱 Telegram Alert")
    if st.button("🚀 Test Telegram", use_container_width=True):
        send_telegram("🚀 Telegram Connected! Scanner PRO Aktif.")
        st.success("✅ Pesan test terkirim!")
    
    st.divider()
    
    st.subheader("📊 Status")
    st.metric("Total Coins", len(st.session_state.watchlist))
    st.metric("Storage", "✅ SQLite")
    st.metric("Pending Signals", len(st.session_state.pending_signal))
    stats = get_performance()
    st.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")
    st.caption(f"🔄 Auto Refresh: {refresh} detik")

# =========================================================
# AUTO REFRESH
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# MAIN TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Scanner", "📈 Smart Money", "🤖 AI Signals", 
    "📋 Trades", "📜 History", "🔄 Backtest"
])

# ==================== TAB 1: SCANNER ====================
with tab1:
    st.subheader("📊 Signal Summary")
    
    current_time = datetime.now()
    expired_signals = []
    for symbol, data in st.session_state.pending_signal.items():
        elapsed = (current_time - data["time"]).seconds / 60
        if elapsed > hold_minutes:
            expired_signals.append(symbol)
    
    for symbol in expired_signals:
        del st.session_state.pending_signal[symbol]
    
    all_signals = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, symbol in enumerate(st.session_state.watchlist[:20]):
        progress_bar.progress((idx + 1) / len(st.session_state.watchlist[:20]))
        status_text.text(f"🔄 Scanning {symbol}...")
        
        result = analyze_mtf(symbol, buffer_pct, confirmation_candles, rr_sl, rr_tp, use_trailing, min_confirmations)
        
        if result:
            pending = st.session_state.pending_signal.get(symbol)
            if pending:
                entry_display = pending["signal"]
                is_pending = True
            else:
                entry_display = result["entry_signal"] if result["entry_signal"] else "⏳ WAIT"
                is_pending = False
            
            if result["entry_signal"] and symbol not in st.session_state.pending_signal:
                st.session_state.pending_signal[symbol] = {
                    "signal": result["entry_signal"],
                    "time": datetime.now(),
                    "entry": result["entry_price"],
                    "sl": result["stop_loss"],
                    "tp": result["take_profit"]
                }
                
                save_signal({
                    'symbol': symbol,
                    'signal': result["entry_signal"],
                    'entry_price': result["entry_price"],
                    'stop_loss': result["stop_loss"],
                    'take_profit': result["take_profit"],
                    'trend_1h': result["trend_1h"],
                    'trend_15m': result["trend_15m"],
                    'score': result['total_score'],
                    'confidence': result['confirmations'] / 3 * 100,
                    'ai_signal': result['ai']['signal_text'],
                    'smart_money_score': result['smart_money']['score']
                })
                
                stats = get_performance()
                stats['total_signals'] = stats.get('total_signals', 0) + 1
                update_performance(stats)
                
                if result["entry_signal"]:
                    rr = ((result["take_profit"] / result["entry_price"] - 1) / 
                          (result["stop_loss"] / result["entry_price"] - 1)) if result["stop_loss"] else 0
                    msg = f"⚡ NEW SIGNAL!\n\nCoin: {symbol}\nSignal: {result['entry_signal']}\nEntry: ${result['entry_price']:.4f}\nSL: ${result['stop_loss']:.4f}\nTP: ${result['take_profit']:.4f}\nRR Ratio: {rr:.2f}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    send_telegram(msg)
            
            all_signals.append({
                "Coin": symbol,
                "Trend 1H": result["trend_1h"],
                "Trend 15M": result["trend_15m"],
                "Trend 5M": result["trend_5m"],
                "Signal": "🟡 PENDING" if is_pending else entry_display,
                "Score": f"{result['total_score']:.0f}",
                "BB Score": result["bb_score"],
                "RSI 5M": f"{result['rsi_5m']:.1f}",
                "AI": result['ai']['signal_text'],
                "SM Score": result['smart_money']['score'],
                "Confirm": f"{result['confirmations']}/3"
            })
    
    progress_bar.empty()
    status_text.empty()
    
    if all_signals:
        df_signals = pd.DataFrame(all_signals)
        df_signals = df_signals.sort_values('Score', ascending=False)
        st.dataframe(df_signals, use_container_width=True, hide_index=True)
        
        best = df_signals.iloc[0]
        st.success(f"🏆 Best Coin: **{best['Coin']}** | Score: {best['Score']} | {best['Signal']}")
    else:
        st.info("ℹ️ Tidak ada data")
    
    # Pending Signals
    if st.session_state.pending_signal:
        st.divider()
        st.subheader("⏳ Pending Signals (Aktif)")
        st.caption(f"Sinyal akan bertahan selama {hold_minutes} menit")
        
        cols = st.columns(min(len(st.session_state.pending_signal), 4))
        for idx, (symbol, data) in enumerate(st.session_state.pending_signal.items()):
            col_idx = idx % len(cols)
            with cols[col_idx]:
                elapsed = (datetime.now() - data["time"]).seconds / 60
                remaining = max(0, hold_minutes - elapsed)
                rr = ((data["tp"] / data["entry"] - 1) / (data["sl"] / data["entry"] - 1)) if data["sl"] else 0
                st.markdown(f"""
                <div class="pending-signal">
                    <b>{symbol}</b><br>
                    {data['signal']}<br>
                    Entry: {format_price(data['entry'])}<br>
                    SL: {format_price(data['sl'])}<br>
                    TP: {format_price(data['tp'])}<br>
                    RR: {rr:.2f}<br>
                    ⏱️ {remaining:.0f}m remaining
                </div>
                """, unsafe_allow_html=True)

# ==================== TAB 2: SMART MONEY ====================
with tab2:
    st.subheader("📈 Smart Money Concepts Analysis")
    
    sm_coin = st.selectbox("Select Coin", st.session_state.watchlist, key="sm_select")
    
    if sm_coin:
        result = analyze_mtf(sm_coin, buffer_pct, confirmation_candles, rr_sl, rr_tp, use_trailing, min_confirmations)
        
        if result:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Smart Money Score", f"{result['smart_money']['score']:.0f}/100")
            col2.metric("Market Structure", 
                       "🟢 Bullish" if result['smart_money']['reasons'] else "🟡 Neutral")
            col3.metric("Order Blocks", len(result['smart_money']['reasons']))
            col4.metric("Total Confirmations", f"{result['confirmations']}/3")
            
            with st.expander("📋 Smart Money Details", expanded=True):
                for reason in result['smart_money']['reasons']:
                    st.write(f"• {reason}")
            
            # Chart
            fig = create_chart(result, sm_coin)
            st.plotly_chart(fig, use_container_width=True)

# ==================== TAB 3: AI SIGNALS ====================
with tab3:
    st.subheader("🤖 AI Signal Analysis")
    
    ai_coin = st.selectbox("Select Coin", st.session_state.watchlist, key="ai_select")
    
    if ai_coin:
        ticker = yf.Ticker(f"{ai_coin}-USD")
        df = ticker.history(period="7d", interval="15m")
        
        if not df.empty:
            predictor = get_predictor()
            if not predictor.is_trained:
                predictor.train(df)
                if predictor.is_trained:
                    st.success("✅ AI Model Trained!")
            
            result = analyze_mtf(ai_coin, buffer_pct, confirmation_candles, rr_sl, rr_tp, use_trailing, min_confirmations)
            
            if result:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("AI Score", f"{result['ai']['score']:.0f}/100")
                col2.metric("Signal", result['ai']['signal_text'])
                col3.metric("Confidence", f"{result['ai']['confidence']:.1f}%")
                col4.metric("Strength", "STRONG" if result['ai']['confidence'] > 70 else "WEAK")
                
                prob_df = pd.DataFrame({
                    'Signal': ['Buy', 'Sell', 'Hold'],
                    'Probability': [result['ai']['buy_prob'], result['ai']['sell_prob'], result['ai']['hold_prob']]
                })
                st.subheader("📊 Probability Distribution")
                st.bar_chart(prob_df.set_index('Signal'))

# ==================== TAB 4: TRADES ====================
with tab4:
    st.subheader("📋 Trade Management")
    
    auto_trade = st.toggle("🤖 Auto Trading", value=True)
    
    if auto_trade:
        st.info("🤖 Auto Trading AKTIF! Monitoring posisi...")
        
        monitor_positions()
        
        for symbol in st.session_state.watchlist[:5]:
            ticker = yf.Ticker(f"{symbol}-USD")
            df = ticker.history(period="7d", interval="15m")
            if not df.empty:
                trade = execute_trade(symbol, df, position_size=position_size, leverage=leverage)
                if trade:
                    st.success(f"🚀 {symbol}: {trade['signal']} at ${trade['entry_price']:.2f}")
                    send_telegram(f"🚀 NEW TRADE: {symbol} - {trade['signal']} at ${trade['entry_price']:.2f}")
    
    # Open positions
    st.subheader("📊 Open Positions")
    trades = get_trades()
    open_trades = [t for t in trades if t.get('status') == 'OPEN']
    
    if open_trades:
        df_open = pd.DataFrame(open_trades)
        cols = ['symbol', 'type', 'entry_price', 'stop_loss', 'take_profit', 'score', 'entry_time']
        available = [c for c in cols if c in df_open.columns]
        st.dataframe(df_open[available], use_container_width=True)
    else:
        st.info("No open positions")
    
    # Closed trades
    st.subheader("📊 Closed Trades")
    closed_trades = [t for t in trades if t.get('status') == 'CLOSED']
    
    if closed_trades:
        df_closed = pd.DataFrame(closed_trades)
        cols = ['symbol', 'type', 'entry_price', 'exit_price', 'profit_pct', 'exit_time']
        available = [c for c in cols if c in df_closed.columns]
        st.dataframe(df_closed[available], use_container_width=True)
        
        stats = get_performance()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", stats.get('total_signals', 0))
        col2.metric("Wins", stats.get('wins', 0))
        col3.metric("Losses", stats.get('losses', 0))
        col4.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")

# ==================== TAB 5: HISTORY ====================
with tab5:
    st.subheader("📜 Signal History")
    
    history = get_signal_history(limit=50)
    if history:
        df_history = pd.DataFrame(history)
        if 'id' in df_history.columns:
            df_history = df_history.drop('id', axis=1)
        st.dataframe(df_history, use_container_width=True, hide_index=True)
        
        csv = df_history.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"history_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("Belum ada sinyal")

# ==================== TAB 6: BACKTEST ====================
with tab6:
    st.subheader("🔄 Backtesting")
    
    col1, col2 = st.columns(2)
    with col1:
        bt_coin = st.selectbox("Coin", st.session_state.watchlist, key="bt_select")
        bt_period = st.selectbox("Period", ["1mo", "3mo", "6mo", "1y"], index=2)
    with col2:
        bt_interval = st.selectbox("Interval", ["15m", "30m", "1h"], index=1)
        bt_rr = st.slider("RR Ratio", 1.0, 5.0, 3.0, 0.5)
    
    if st.button("🚀 Run Backtest", use_container_width=True):
        with st.spinner(f"Running backtest on {bt_coin}..."):
            result = run_backtest(bt_coin, bt_period, bt_interval, bt_rr)
            
            if result:
                st.session_state.backtest_result = result
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Total Trades", result['total_trades'])
                col2.metric("Win Rate", f"{result['win_rate']:.1f}%")
                col3.metric("Total Profit", f"{result['total_profit']:.2f}%")
                col4.metric("Final Balance", f"${result['final_balance']:.2f}")
                col5.metric("Total Return", f"{result['total_return']:.1f}%")
                
                if result['trades']:
                    df_bt = pd.DataFrame(result['trades'])
                    st.dataframe(df_bt, use_container_width=True)

# =========================================================
# PERFORMANCE STATISTICS
# =========================================================
st.divider()
st.subheader("📊 Performance Statistics")

stats = get_performance()
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Signals", stats.get("total_signals", 0))
col2.metric("Wins", stats.get("wins", 0))
col3.metric("Losses", stats.get("losses", 0))
col4.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")
col5.metric("Total Profit", f"${stats.get('total_profit', 0):.2f}")

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"""
🔄 Data dari Yahoo Finance | Multi Timeframe: 1H, 15M, 5M  
📊 Total Coins: {len(st.session_state.watchlist)} | ⚡ Leverage: {leverage}x  
🎯 RR Strategy: 3:7 | 🛡️ Signal Hold: {hold_minutes}m  
💾 Database: SQLite | 🤖 AI: Random Forest
""")
