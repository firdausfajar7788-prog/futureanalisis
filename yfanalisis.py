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
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import accuracy_score, classification_report
import warnings
warnings.filterwarnings('ignore')

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="🤖 Crypto Trading Bot PRO",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# ENHANCED CSS
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
        box-shadow: 0 8px 30px rgba(0,255,255,0.15);
    }
    .signal-buy {
        background: linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,255,136,0.05));
        border: 1px solid #00ff88;
        border-radius: 12px;
        padding: 12px 20px;
        color: #00ff88;
        font-weight: 600;
        font-size: 18px;
        animation: pulse-green 2s infinite;
    }
    .signal-sell {
        background: linear-gradient(135deg, rgba(255,59,92,0.15), rgba(255,59,92,0.05));
        border: 1px solid #ff3b5c;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ff3b5c;
        font-weight: 600;
        font-size: 18px;
        animation: pulse-red 2s infinite;
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
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(0,255,136,0.4); }
        70% { box-shadow: 0 0 0 10px rgba(0,255,136,0); }
        100% { box-shadow: 0 0 0 0 rgba(0,255,136,0); }
    }
    @keyframes pulse-red {
        0% { box-shadow: 0 0 0 0 rgba(255,59,92,0.4); }
        70% { box-shadow: 0 0 0 10px rgba(255,59,92,0); }
        100% { box-shadow: 0 0 0 0 rgba(255,59,92,0); }
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
    .metric-card {
        background: linear-gradient(145deg, #1a1a2e, #16213e);
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #2a2a4a;
    }
    .profit-positive { color: #00ff88; }
    .profit-negative { color: #ff3b5c; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# DATABASE
# =========================================================
DB_PATH = "crypto_bot_pro.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE,
            added_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            name TEXT,
            category TEXT,
            active INTEGER DEFAULT 1,
            volatility_score REAL DEFAULT 0.5,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    ''')
    
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
            adx_value REAL,
            volatility_pct REAL,
            volume_ratio REAL,
            timestamp TIMESTAMP
        )
    ''')
    
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
            ai_score REAL,
            max_profit REAL,
            min_profit REAL,
            holding_period INTEGER,
            rr_ratio REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            total_signals INTEGER,
            wins INTEGER,
            losses INTEGER,
            profit REAL,
            win_rate REAL,
            avg_holding_period REAL,
            max_drawdown REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ml_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            prediction INTEGER,
            confidence REAL,
            buy_prob REAL,
            sell_prob REAL,
            hold_prob REAL,
            model_version TEXT,
            timestamp TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pair_performance (
            symbol TEXT PRIMARY KEY,
            total_trades INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            total_profit REAL DEFAULT 0,
            avg_profit REAL DEFAULT 0,
            max_profit REAL DEFAULT 0,
            max_loss REAL DEFAULT 0,
            last_updated TIMESTAMP
        )
    ''')
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signal_history(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_time ON signal_history(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)")
    
    conn.commit()
    conn.close()

init_db()

# =========================================================
# DATA MANAGER
# =========================================================
class DataManager:
    def __init__(self):
        self.cache = {}
    
    def get_data(self, symbol, interval, period):
        cache_key = f"{symbol}_{interval}_{period}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            ticker = f"{symbol}-USD"
            df = yf.download(ticker, interval=interval, period=period, progress=False, timeout=15)
            if df.empty:
                ticker = symbol
                df = yf.download(ticker, interval=interval, period=period, progress=False, timeout=15)
            if df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.reset_index()
            df.rename(columns={df.columns[0]: "Time"}, inplace=True)
            df["Time"] = pd.to_datetime(df["Time"])
            self.cache[cache_key] = df
            return df
        except Exception as e:
            return None

data_manager = DataManager()

# =========================================================
# INDICATORS
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
# ENHANCED SMART MONEY
# =========================================================
def enhanced_smart_money_analysis(df, lookback=30):
    """Smart Money Concepts analysis"""
    
    def find_order_blocks(df, lookback):
        blocks = []
        for i in range(lookback, len(df)-1):
            if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
                high = df['High'].iloc[i-1]
                low = df['Low'].iloc[i-1]
                if df['High'].iloc[i] > high:
                    blocks.append({
                        'type': 'BULLISH',
                        'high': float(high),
                        'low': float(low),
                        'strength': df['Volume'].iloc[i] / df['Volume'].iloc[i-1] if df['Volume'].iloc[i-1] > 0 else 1
                    })
            elif df['Close'].iloc[i] < df['Close'].iloc[i-1]:
                high = df['High'].iloc[i-1]
                low = df['Low'].iloc[i-1]
                if df['Low'].iloc[i] < low:
                    blocks.append({
                        'type': 'BEARISH',
                        'high': float(high),
                        'low': float(low),
                        'strength': df['Volume'].iloc[i] / df['Volume'].iloc[i-1] if df['Volume'].iloc[i-1] > 0 else 1
                    })
        return blocks[-5:]
    
    def find_fair_value_gaps(df, lookback):
        fvgs = []
        for i in range(2, len(df)-1):
            if df['Low'].iloc[i] > df['High'].iloc[i-2]:
                fvgs.append({
                    'type': 'BULLISH',
                    'high': float(df['Low'].iloc[i]),
                    'low': float(df['High'].iloc[i-2]),
                    'size': (df['Low'].iloc[i] - df['High'].iloc[i-2]) / df['High'].iloc[i-2] * 100
                })
            elif df['High'].iloc[i] < df['Low'].iloc[i-2]:
                fvgs.append({
                    'type': 'BEARISH',
                    'high': float(df['Low'].iloc[i-2]),
                    'low': float(df['High'].iloc[i]),
                    'size': (df['Low'].iloc[i-2] - df['High'].iloc[i]) / df['High'].iloc[i] * 100
                })
        return fvgs[-5:]
    
    def detect_market_structure(df, lookback=10):
        structure = {'hh': False, 'hl': False, 'lh': False, 'll': False, 'bos': False, 'choch': False, 'trend': 'NEUTRAL'}
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
        if structure['hh'] and structure['hl']:
            structure['trend'] = 'BULLISH'
        elif structure['lh'] and structure['ll']:
            structure['trend'] = 'BEARISH'
        return structure
    
    def find_liquidity_sweeps(df, lookback=20):
        sweeps = []
        recent_high = df['High'].tail(lookback).max()
        recent_low = df['Low'].tail(lookback).min()
        buffer = 0.005
        if df['High'].iloc[-1] > recent_high * (1 + buffer):
            sweeps.append({'type': 'HIGH_SWEEP', 'level': float(recent_high), 'swept_at': float(df['High'].iloc[-1])})
        if df['Low'].iloc[-1] < recent_low * (1 - buffer):
            sweeps.append({'type': 'LOW_SWEEP', 'level': float(recent_low), 'swept_at': float(df['Low'].iloc[-1])})
        return sweeps
    
    order_blocks = find_order_blocks(df, lookback)
    fvgs = find_fair_value_gaps(df, lookback)
    structure = detect_market_structure(df, lookback)
    sweeps = find_liquidity_sweeps(df, lookback)
    
    score = 50
    reasons = []
    signals = []
    
    if order_blocks:
        last_block = order_blocks[-1]
        if last_block['type'] == 'BULLISH' and last_block['strength'] > 1.2:
            score += 15
            reasons.append("Strong Bullish Order Block")
            signals.append("BUY")
        elif last_block['type'] == 'BEARISH' and last_block['strength'] > 1.2:
            score -= 15
            reasons.append("Strong Bearish Order Block")
            signals.append("SELL")
    
    if fvgs:
        last_fvg = fvgs[-1]
        if last_fvg['type'] == 'BULLISH' and last_fvg['size'] > 2:
            score += 15
            reasons.append("Large Bullish FVG")
            signals.append("BUY")
        elif last_fvg['type'] == 'BEARISH' and last_fvg['size'] > 2:
            score -= 15
            reasons.append("Large Bearish FVG")
            signals.append("SELL")
    
    if structure['trend'] == 'BULLISH':
        score += 10
        reasons.append("Bullish Structure")
    elif structure['trend'] == 'BEARISH':
        score -= 10
        reasons.append("Bearish Structure")
    
    if structure['choch']:
        score += 5
        reasons.append("Change of Character")
    
    for sweep in sweeps:
        if sweep['type'] == 'HIGH_SWEEP':
            score += 10
            reasons.append("High Liquidity Sweep")
            signals.append("SELL")
        elif sweep['type'] == 'LOW_SWEEP':
            score -= 10
            reasons.append("Low Liquidity Sweep")
            signals.append("BUY")
    
    buy_signals = signals.count("BUY")
    sell_signals = signals.count("SELL")
    
    overall_signal = "BULLISH" if buy_signals > sell_signals else ("BEARISH" if sell_signals > buy_signals else "NEUTRAL")
    
    return {
        'score': max(0, min(100, score)),
        'reasons': reasons,
        'signal': overall_signal,
        'order_blocks': order_blocks,
        'fvgs': fvgs,
        'structure': structure,
        'sweeps': sweeps
    }

# =========================================================
# ENHANCED AI PREDICTOR WITH RANDOM FOREST
# =========================================================
class EnhancedAIPredictor:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_importance = None
        self.model_version = "RF_v2.0"
        self.min_training_samples = 100
        self.accuracy_history = []
        
    def _extract_features(self, df):
        """Extract comprehensive features"""
        features = pd.DataFrame()
        df = df.copy()
        
        # 1. Price features
        features['close'] = df['Close']
        features['open'] = df['Open']
        features['high'] = df['High']
        features['low'] = df['Low']
        
        # 2. Returns
        for period in [1, 2, 3, 5, 10, 20]:
            features[f'return_{period}'] = df['Close'].pct_change(period)
            features[f'return_abs_{period}'] = df['Close'].pct_change(period).abs()
        
        # 3. Price position
        features['price_position'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'] + 1e-6)
        features['high_low_ratio'] = df['High'] / (df['Low'] + 1e-6)
        
        # 4. Volume
        features['volume'] = df['Volume']
        features['volume_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()
        features['volume_trend'] = df['Volume'].rolling(5).mean() / df['Volume'].rolling(20).mean()
        features['volume_volatility'] = df['Volume'].pct_change().rolling(10).std()
        
        # 5. Moving Averages
        for period in [9, 20, 50, 200]:
            ma = df['Close'].rolling(period).mean()
            features[f'ma_{period}'] = ma
            features[f'price_ma_{period}'] = df['Close'] / ma - 1
        
        # 6. RSI
        features['rsi_14'] = RSI(df, 14)
        features['rsi_21'] = RSI(df, 21)
        
        # 7. MACD
        macd, signal, hist = MACD(df)
        features['macd'] = macd
        features['macd_signal'] = signal
        features['macd_hist'] = hist
        features['macd_divergence'] = macd - signal
        
        # 8. Bollinger Bands
        bb_upper, bb_mid, bb_lower = BollingerBands(df)
        features['bb_position'] = (df['Close'] - bb_lower) / (bb_upper - bb_lower + 1e-6)
        features['bb_width'] = (bb_upper - bb_lower) / bb_mid
        
        # 9. Volatility
        features['atr'] = ATR(df, 14)
        features['atr_pct'] = features['atr'] / df['Close']
        features['volatility_10'] = df['Close'].pct_change().rolling(10).std()
        features['volatility_20'] = df['Close'].pct_change().rolling(20).std()
        
        # 10. Stochastic
        stoch_k, stoch_d = StochasticRSI(df)
        features['stoch_k'] = stoch_k
        features['stoch_d'] = stoch_d
        
        # 11. ADX
        features['adx'] = ADX(df, 14)
        
        # 12. Support/Resistance distance
        features['support_distance'] = (df['Close'] - df['Low'].rolling(20).min()) / df['Close']
        features['resistance_distance'] = (df['High'].rolling(20).max() - df['Close']) / df['Close']
        
        # 13. Statistical features
        for window in [10, 20]:
            features[f'skew_{window}'] = df['Close'].rolling(window).skew()
            features[f'kurtosis_{window}'] = df['Close'].rolling(window).kurt()
        
        features = features.dropna()
        return features
    
    def train(self, df):
        """Train with hyperparameter tuning"""
        try:
            if len(df) < self.min_training_samples:
                return False
            
            features = self._extract_features(df)
            if len(features) < 50:
                return False
            
            # Create target: 1=BUY, 0=HOLD, 2=SELL
            future_returns = []
            for horizon in [3, 5, 10]:
                ret = df['Close'].shift(-horizon) / df['Close'] - 1
                future_returns.append(ret)
            
            future_returns = pd.concat(future_returns, axis=1).mean(axis=1)
            
            target = pd.Series(index=df.index, dtype=int)
            target[future_returns > 0.02] = 1  # BUY
            target[future_returns < -0.02] = 2  # SELL
            target[future_returns.abs() <= 0.02] = 0  # HOLD
            
            valid_idx = features.index.intersection(target.dropna().index)
            X = features.loc[valid_idx]
            y = target.loc[valid_idx]
            
            if len(X) < 50:
                return False
            
            X_scaled = self.scaler.fit_transform(X)
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # Hyperparameter tuning with GridSearch
            param_grid = {
                'n_estimators': [100, 200, 300],
                'max_depth': [10, 15, 20],
                'min_samples_split': [5, 10],
                'min_samples_leaf': [2, 4]
            }
            
            rf = RandomForestClassifier(random_state=42, n_jobs=-1)
            grid_search = GridSearchCV(
                rf, param_grid, cv=3, scoring='accuracy', n_jobs=-1, verbose=0
            )
            grid_search.fit(X_train, y_train)
            
            self.model = grid_search.best_estimator_
            y_pred = self.model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            
            self.feature_importance = dict(zip(features.columns, self.model.feature_importances_))
            self.accuracy_history.append(accuracy)
            self.is_trained = True
            
            return True
            
        except Exception as e:
            return False
    
    def predict(self, df):
        default = {
            'signal': 0,
            'confidence': 0,
            'buy_prob': 0,
            'sell_prob': 0,
            'hold_prob': 100,
            'model_version': self.model_version
        }
        
        if not self.is_trained or len(df) < 50:
            return default
        
        try:
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
                'buy_prob': float(proba[1]) * 100 if len(proba) > 1 else 0,
                'sell_prob': float(proba[2]) * 100 if len(proba) > 2 else 0,
                'hold_prob': float(proba[0]) * 100,
                'model_version': self.model_version
            }
            
        except Exception as e:
            return default

_predictor = None

def get_predictor():
    global _predictor
    if _predictor is None:
        _predictor = EnhancedAIPredictor()
    return _predictor

# =========================================================
# ENHANCED ANALYSIS
# =========================================================
def analyze_mtf_enhanced(symbol, buffer_pct=0.5, confirmation_candles=3, 
                        rr_sl=4.5, rr_tp=9.0, min_confirmations=2.5):
    """Enhanced multi-timeframe analysis"""
    try:
        df_1h = data_manager.get_data(symbol, "1h", "7d")
        if df_1h is None or len(df_1h) < 30:
            return None
        
        df_15m = data_manager.get_data(symbol, "15m", "5d")
        if df_15m is None or len(df_15m) < 50:
            df_15m = df_1h.copy()
        
        df_5m = data_manager.get_data(symbol, "5m", "2d")
        if df_5m is None or len(df_5m) < 20:
            df_5m = df_15m.copy()
        
        # Get latest values
        latest_1h = df_1h.iloc[-1]
        latest_15m = df_15m.iloc[-1]
        latest_5m = df_5m.iloc[-1]
        
        # 1. Trend Analysis
        def analyze_trend(df):
            if df is None or len(df) < 20:
                return "⚠️ Insufficient Data"
            latest = df.iloc[-1]
            price = latest['Close']
            ema20 = EMA(df, 20).iloc[-1]
            ema50 = EMA(df, 50).iloc[-1]
            adx = ADX(df, 14).iloc[-1] if not pd.isna(ADX(df, 14).iloc[-1]) else 0
            
            if price > ema20 > ema50 and adx > 25:
                return "🟢 BULLISH (Strong)"
            elif price > ema20 > ema50:
                return "🟢 BULLISH"
            elif price < ema20 < ema50 and adx > 25:
                return "🔴 BEARISH (Strong)"
            elif price < ema20 < ema50:
                return "🔴 BEARISH"
            elif adx < 20:
                return "🟡 SIDEWAYS (Weak Trend)"
            else:
                return "🟡 SIDEWAYS"
        
        trend_1h = analyze_trend(df_1h)
        trend_15m = analyze_trend(df_15m)
        trend_5m = analyze_trend(df_5m)
        
        # 2. Smart Money Analysis
        sm_5m = enhanced_smart_money_analysis(df_5m)
        
        # 3. Support/Resistance
        support_15m = latest_15m['Low'].rolling(20).min()
        resistance_15m = latest_15m['High'].rolling(20).max()
        
        # 4. Volume Analysis
        volume_ma = df_5m['Volume'].rolling(20).mean().iloc[-1]
        vol_ratio = latest_5m['Volume'] / volume_ma if volume_ma > 0 else 1
        vol_spike = vol_ratio > 1.5
        
        # 5. AI Prediction
        predictor = get_predictor()
        if not predictor.is_trained:
            predictor.train(df_1h)
        ai_pred = predictor.predict(df_5m)
        
        # 6. Entry Signal
        entry_signal = None
        confirmations = 0
        reasons = []
        
        price = latest_5m['Close']
        bullish = all('BULLISH' in t for t in [trend_1h, trend_15m, trend_5m])
        bearish = all('BEARISH' in t for t in [trend_1h, trend_15m, trend_5m])
        
        support_confirmed = price <= support_15m * (1 + buffer_pct/100)
        resistance_confirmed = price >= resistance_15m * (1 - buffer_pct/100)
        
        if support_confirmed:
            confirmations += 1
            reasons.append("Near Support")
        if resistance_confirmed:
            confirmations += 1
            reasons.append("Near Resistance")
        if vol_spike:
            confirmations += 1
            reasons.append("Volume Spike")
        if sm_5m['signal'] in ['BULLISH', 'BEARISH']:
            confirmations += 0.5
            reasons.append(f"Smart Money: {sm_5m['signal']}")
        if ai_pred['signal'] == 1:
            confirmations += 0.5
            reasons.append("AI: BUY")
        elif ai_pred['signal'] == 2:
            confirmations += 0.5
            reasons.append("AI: SELL")
        
        # ADX filter - skip jika trend lemah
        adx_value = ADX(df_1h, 14).iloc[-1] if not pd.isna(ADX(df_1h, 14).iloc[-1]) else 0
        if adx_value < 20 and (bullish or bearish):
            confirmations -= 0.5
            reasons.append("Weak Trend (ADX<20)")
        
        if confirmations >= min_confirmations:
            if bullish or (support_confirmed and sm_5m['signal'] == 'BULLISH'):
                entry_signal = "🟢 STRONG BUY" if confirmations >= 3 else "🟢 BUY"
            elif bearish or (resistance_confirmed and sm_5m['signal'] == 'BEARISH'):
                entry_signal = "🔴 STRONG SELL" if confirmations >= 3 else "🔴 SELL"
            elif support_confirmed and vol_spike:
                entry_signal = "🟢 BUY (Breakout)"
            elif resistance_confirmed and vol_spike:
                entry_signal = "🔴 SELL (Breakdown)"
        
        entry_price = price
        atr = ATR(df_5m, 14).iloc[-1] if not pd.isna(ATR(df_5m, 14).iloc[-1]) else price * 0.02
        volatility_pct = (atr / price) * 100
        
        # Dynamic SL based on volatility
        if volatility_pct > 5:
            sl_mult = rr_sl * 1.3
        elif volatility_pct < 2:
            sl_mult = rr_sl * 0.8
        else:
            sl_mult = rr_sl
        
        if entry_signal and 'BUY' in entry_signal:
            stop_loss = entry_price - atr * sl_mult
            take_profit = entry_price + atr * rr_tp
        elif entry_signal and 'SELL' in entry_signal:
            stop_loss = entry_price + atr * sl_mult
            take_profit = entry_price - atr * rr_tp
        else:
            stop_loss = None
            take_profit = None
        
        # Total score
        score_components = {
            'trend': 20 if bullish else (10 if not bullish and not bearish else 0),
            'smart_money': sm_5m['score'] * 0.3,
            'ai': ai_pred['confidence'] * 0.3,
            'volume': 10 if vol_spike else 0,
            'confirmations': confirmations * 10
        }
        total_score = sum(score_components.values())
        total_score = max(0, min(100, total_score))
        confidence = min(100, confirmations / 3 * 100)
        
        return {
            'symbol': symbol,
            'trend_1h': trend_1h,
            'trend_15m': trend_15m,
            'trend_5m': trend_5m,
            'support': support_15m,
            'resistance': resistance_15m,
            'support_confirmed': support_confirmed,
            'resistance_confirmed': resistance_confirmed,
            'vol_spike_confirmed': vol_spike,
            'confirmations': confirmations,
            'entry_signal': entry_signal,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'price': price,
            'atr': atr,
            'volatility_pct': volatility_pct,
            'smart_money': sm_5m,
            'ai': ai_pred,
            'total_score': total_score,
            'confidence': confidence,
            'reasons': reasons,
            'adx_value': adx_value,
            'volume_ratio': vol_ratio,
            'score_components': score_components,
            'df_1h': df_1h.tail(50),
            'df_15m': df_15m.tail(50),
            'df_5m': df_5m.tail(30)
        }
        
    except Exception as e:
        return None

# =========================================================
# TRADE EXECUTION
# =========================================================
def execute_trade_enhanced(symbol, balance=10000, position_size=100, leverage=10):
    result = analyze_mtf_enhanced(symbol)
    if not result or not result['entry_signal']:
        return None
    
    entry_price = result['entry_price']
    stop_loss = result['stop_loss']
    take_profit = result['take_profit']
    
    if not entry_price or not stop_loss or not take_profit:
        return None
    
    # Dynamic position sizing
    risk_amount = balance * 0.02
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit > 0:
        optimal_position = risk_amount / risk_per_unit
        position_size = min(optimal_position, position_size * 2)
    
    if 'BUY' in result['entry_signal']:
        rr_ratio = (take_profit - entry_price) / (entry_price - stop_loss)
    else:
        rr_ratio = (entry_price - take_profit) / (stop_loss - entry_price)
    
    trade = {
        'symbol': symbol,
        'type': 'BUY' if 'BUY' in result['entry_signal'] else 'SELL',
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'position_size': position_size,
        'leverage': leverage,
        'score': result['total_score'],
        'confidence': result['confidence'],
        'signal': result['entry_signal'],
        'status': 'OPEN',
        'entry_time': datetime.now(),
        'smart_money_score': result['smart_money']['score'],
        'ai_score': result['ai']['confidence'],
        'rr_ratio': rr_ratio,
        'max_profit': 0,
        'min_profit': 0
    }
    
    save_trade_enhanced(trade)
    return trade

def save_trade_enhanced(trade_data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (
            symbol, type, entry_price, stop_loss, take_profit,
            position_size, leverage, score, confidence, signal,
            status, entry_time, smart_money_score, ai_score,
            rr_ratio, max_profit, min_profit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        trade_data.get('ai_score', 0),
        trade_data.get('rr_ratio', 0),
        trade_data.get('max_profit', 0),
        trade_data.get('min_profit', 0)
    ))
    conn.commit()
    conn.close()
    return True

def get_trades_enhanced(limit=100):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_performance_enhanced():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM performance WHERE key = 'performance_stats'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row['value'])
    return {"total_signals": 0, "wins": 0, "losses": 0, "total_profit": 0, "win_rate": 0}

def update_performance_enhanced(stats):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO performance (key, value, updated_at) VALUES (?, ?, ?)",
        ("performance_stats", json.dumps(stats), datetime.now())
    )
    conn.commit()
    conn.close()
    return True

def monitor_positions_enhanced():
    trades = get_trades_enhanced()
    open_trades = [t for t in trades if t.get('status') == 'OPEN']
    
    for trade in open_trades:
        symbol = trade['symbol']
        df = data_manager.get_data(symbol, "5m", "1d")
        if df is None or df.empty:
            continue
        
        current_price = df['Close'].iloc[-1]
        entry = trade['entry_price']
        sl = trade['stop_loss']
        tp = trade['take_profit']
        
        if trade['type'] == 'BUY':
            profit_pct = (current_price / entry - 1) * 100
            if profit_pct > trade.get('max_profit', 0):
                trade['max_profit'] = profit_pct
            
            # Trailing stop
            if trade.get('max_profit', 0) > 5:
                new_sl = max(sl, entry * (1 + trade.get('max_profit', 0) / 100 * 0.5))
                if new_sl > sl:
                    update_trade_enhanced(trade['id'], {'stop_loss': new_sl})
                    sl = new_sl
            
            if current_price <= sl:
                close_trade_enhanced(trade['id'], current_price, profit_pct)
            elif current_price >= tp:
                close_trade_enhanced(trade['id'], current_price, profit_pct)
        else:
            profit_pct = (entry / current_price - 1) * 100
            if profit_pct > trade.get('max_profit', 0):
                trade['max_profit'] = profit_pct
            
            if trade.get('max_profit', 0) > 5:
                new_sl = min(sl, entry * (1 - trade.get('max_profit', 0) / 100 * 0.5))
                if new_sl < sl:
                    update_trade_enhanced(trade['id'], {'stop_loss': new_sl})
                    sl = new_sl
            
            if current_price >= sl:
                close_trade_enhanced(trade['id'], current_price, profit_pct)
            elif current_price <= tp:
                close_trade_enhanced(trade['id'], current_price, profit_pct)

def close_trade_enhanced(trade_id, exit_price, profit_pct):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT entry_time FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()
    holding_period = 0
    if row:
        entry_time = datetime.fromisoformat(row[0])
        holding_period = (datetime.now() - entry_time).seconds // 60
    
    cursor.execute('''
        UPDATE trades 
        SET status = 'CLOSED', exit_price = ?, profit_pct = ?,
            exit_time = ?, holding_period = ?
        WHERE id = ?
    ''', (exit_price, profit_pct, datetime.now(), holding_period, trade_id))
    conn.commit()
    conn.close()
    
    stats = get_performance_enhanced()
    stats['total_signals'] = stats.get('total_signals', 0) + 1
    if profit_pct > 0:
        stats['wins'] = stats.get('wins', 0) + 1
    else:
        stats['losses'] = stats.get('losses', 0) + 1
    stats['total_profit'] = stats.get('total_profit', 0) + profit_pct
    stats['win_rate'] = stats['wins'] / max(1, stats['total_signals']) * 100
    update_performance_enhanced(stats)

def update_trade_enhanced(trade_id, updates):
    conn = get_db()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [trade_id]
    cursor.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True

def save_signal_enhanced(signal_data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO signal_history (
            symbol, signal, entry_price, stop_loss, take_profit,
            trend_1h, trend_15m, score, confidence, ai_signal,
            smart_money_score, adx_value, volatility_pct, volume_ratio, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        signal_data.get('adx_value', 0),
        signal_data.get('volatility_pct', 0),
        signal_data.get('volume_ratio', 0),
        datetime.now()
    ))
    conn.commit()
    conn.close()
    return True

def get_signal_history_enhanced(limit=100):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signal_history ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_watchlist_enhanced():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM watchlist ORDER BY added_at")
    rows = cursor.fetchall()
    conn.close()
    return [row['symbol'] for row in rows] if rows else ["BTC"]

def add_coin_enhanced(symbol):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO watchlist (symbol, added_at) VALUES (?, ?)", (symbol.upper(), datetime.now()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def remove_coin_enhanced(symbol):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# =========================================================
# TELEGRAM
# =========================================================
def send_telegram_enhanced(message):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
    except:
        pass

# =========================================================
# FORMAT PRICE
# =========================================================
def format_price_enhanced(value):
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
# CREATE CHART
# =========================================================
def create_enhanced_chart(result, symbol):
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
            y=EMA(df, 20),
            line=dict(color="#00a2ff", width=1.5),
            name="EMA20"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df["Time"],
            y=EMA(df, 50),
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
        go.Scatter(x=df_15m["Time"], y=RSI(df_15m, 14), line=dict(color="#a855f7", width=2), name="RSI (15M)"),
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
    
    stoch_k, stoch_d = StochasticRSI(df_15m)
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=stoch_k, line=dict(color="#ffaa00", width=1.5), name="Stoch K"),
        row=4, col=1
    )
    fig.add_trace(
        go.Scatter(x=df_15m["Time"], y=stoch_d, line=dict(color="#ff00ff", width=1.5), name="Stoch D"),
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
            y=df["Volume"].rolling(20).mean(),
            line=dict(color="rgba(255,255,255,0.3)", width=1),
            name="Volume MA"
        ),
        row=5, col=1
    )
    
    fig.update_layout(
        template="plotly_dark",
        height=1100,
        title=dict(
            text=f"<b>{symbol} - Enhanced Multi-Timeframe Analysis</b>",
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
# BACKTEST
# =========================================================
def run_enhanced_backtest(symbol, period="3mo", interval="15m", rr_ratio=3.0, sl_atr=2.0):
    """Run enhanced backtest with realistic assumptions"""
    
    df = data_manager.get_data(symbol, interval, period)
    if df is None or df.empty:
        return None
    
    balance = 10000
    initial_balance = balance
    trades = []
    equity_curve = [balance]
    in_position = False
    entry_price = 0
    trade_type = None
    sl = 0
    tp = 0
    max_profit = 0
    
    commission = 0.001
    slippage = 0.0005
    spread = 0.0002
    
    for i in range(50, len(df)-1):
        window = df.iloc[:i+1].copy()
        if len(window) < 50:
            continue
        
        current_price = df['Close'].iloc[i]
        
        if not in_position:
            price = current_price
            ema20 = EMA(window, 20).iloc[-1]
            ema50 = EMA(window, 50).iloc[-1]
            rsi = RSI(window, 14).iloc[-1]
            volume_ratio = window['Volume'].iloc[-1] / window['Volume'].rolling(20).mean().iloc[-1] if window['Volume'].rolling(20).mean().iloc[-1] > 0 else 1
            
            if price > ema20 > ema50 and rsi < 60 and volume_ratio > 1.2:
                entry_signal = "BUY"
            elif price < ema20 < ema50 and rsi > 40 and volume_ratio > 1.2:
                entry_signal = "SELL"
            else:
                entry_signal = None
            
            if entry_signal:
                in_position = True
                entry_price = current_price * (1 + spread if entry_signal == "BUY" else 1 - spread)
                trade_type = entry_signal
                
                atr_value = ATR(df, 14).iloc[i] if i < len(df) else ATR(df, 14).iloc[-1]
                
                if trade_type == "BUY":
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
            actual_price = df['Close'].iloc[i]
            
            if trade_type == "BUY":
                profit_pct = (actual_price / entry_price - 1) * 100
                max_profit = max(max_profit, profit_pct)
                
                if actual_price <= sl * (1 - slippage):
                    exit_price = sl * (1 - slippage)
                    profit_pct = (exit_price / entry_price - 1) * 100
                    profit_pct_net = profit_pct * (1 - commission)
                    balance *= (1 + profit_pct_net/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct_net})
                elif actual_price >= tp * (1 + slippage):
                    exit_price = tp * (1 + slippage)
                    profit_pct = (exit_price / entry_price - 1) * 100
                    profit_pct_net = profit_pct * (1 - commission)
                    balance *= (1 + profit_pct_net/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct_net})
            else:
                profit_pct = (entry_price / actual_price - 1) * 100
                max_profit = max(max_profit, profit_pct)
                
                if actual_price >= sl * (1 + slippage):
                    exit_price = sl * (1 + slippage)
                    profit_pct = (entry_price / exit_price - 1) * 100
                    profit_pct_net = profit_pct * (1 - commission)
                    balance *= (1 + profit_pct_net/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct_net})
                elif actual_price <= tp * (1 - slippage):
                    exit_price = tp * (1 - slippage)
                    profit_pct = (entry_price / exit_price - 1) * 100
                    profit_pct_net = profit_pct * (1 - commission)
                    balance *= (1 + profit_pct_net/100)
                    in_position = False
                    trades[-1].update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_pct': profit_pct_net})
        
        equity_curve.append(balance)
    
    if trades:
        profits = [t.get('profit_pct', 0) for t in trades if 'profit_pct' in t]
        wins = len([p for p in profits if p > 0])
        losses = len([p for p in profits if p < 0])
        total_profit = sum(profits)
        
        equity_series = pd.Series(equity_curve)
        drawdown = (equity_series - equity_series.expanding().max()) / equity_series.expanding().max() * 100
        
        metrics = {
            'trades': trades,
            'total_trades': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / max(1, len(trades)) * 100,
            'total_profit': total_profit,
            'final_balance': balance,
            'total_return': (balance / initial_balance - 1) * 100,
            'max_drawdown': drawdown.min(),
            'sharpe_ratio': np.mean(profits) / (np.std(profits) + 1e-6) * np.sqrt(252) if profits else 0,
            'profit_factor': abs(sum([p for p in profits if p > 0]) / sum([abs(p) for p in profits if p < 0])) if any(p < 0 for p in profits) else 0
        }
        
        return metrics
    
    return None

# =========================================================
# MAIN APP
# =========================================================

# Session State
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist_enhanced()

if "selected_coin" not in st.session_state:
    st.session_state.selected_coin = st.session_state.watchlist[0] if st.session_state.watchlist else "BTC"

if "pending_signals" not in st.session_state:
    st.session_state.pending_signals = {}

if "performance_stats" not in st.session_state:
    st.session_state.performance_stats = get_performance_enhanced()

if "backtest_result" not in st.session_state:
    st.session_state.backtest_result = None

if "auto_trade" not in st.session_state:
    st.session_state.auto_trade = False

# =========================================================
# MAIN TITLE
# =========================================================
st.title("🤖 Crypto Trading Bot PRO")
st.caption("Enhanced Random Forest AI | Smart Money | Dynamic Risk Management | Multi-Timeframe")

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
                    if add_coin_enhanced(coin):
                        st.session_state.watchlist.append(coin)
                        st.rerun()
                    else:
                        st.error("❌ Failed to add coin!")
                else:
                    st.warning(f"⚠️ {coin} already exists!")
    
    st.markdown("**Your Coins:**")
    cols = st.columns(3)
    for idx, coin in enumerate(st.session_state.watchlist):
        col_idx = idx % 3
        with cols[col_idx]:
            if st.button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
                if remove_coin_enhanced(coin):
                    st.session_state.watchlist.remove(coin)
                    st.rerun()
                else:
                    st.error(f"❌ Failed to remove {coin}!")
    
    st.divider()
    
    st.subheader("📊 Trading Settings")
    refresh = st.slider("🔄 Refresh (detik)", 10, 60, 30)
    leverage = st.slider("⚡ Leverage", 1, 125, 5)
    position_size = st.number_input("💰 Position Size (USD)", 10, 100000, 100, step=10)
    
    st.subheader("🎯 Risk Management")
    risk_per_trade = st.slider("Risk per Trade (%)", 0.5, 5.0, 2.0, 0.5)
    rr_sl = st.slider("Stop Loss (ATR)", 2.0, 8.0, 4.5, 0.5)
    rr_tp = st.slider("Take Profit (ATR)", 4.0, 15.0, 9.0, 0.5)
    use_trailing = st.toggle("🚀 Trailing Stop", value=True)
    
    hold_minutes = st.slider("Hold Signal (menit)", 5, 30, 15)
    buffer_pct = st.slider("Buffer Level (%)", 0.1, 2.0, 0.8, 0.1)
    min_confirmations = st.slider("Min Konfirmasi", 1.0, 3.0, 2.5, 0.5)
    
    st.divider()
    
    st.subheader("📱 Telegram Alert")
    if st.button("🚀 Test Telegram", use_container_width=True):
        send_telegram_enhanced("🚀 Telegram Connected! Enhanced Bot PRO Aktif.")
        st.success("✅ Test message sent!")
    
    st.divider()
    
    st.subheader("📊 Status")
    st.metric("Total Coins", len(st.session_state.watchlist))
    st.metric("Storage", "✅ SQLite PRO")
    st.metric("Pending Signals", len(st.session_state.pending_signals))
    stats = get_performance_enhanced()
    st.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")
    st.metric("Total Profit", f"${stats.get('total_profit', 0):.2f}")
    
    st.caption(f"🔄 Auto Refresh: {refresh} detik")
    st.caption(f"🎯 Risk per Trade: {risk_per_trade}%")
    st.caption(f"📊 RR Ratio: 1:{rr_tp/rr_sl:.1f}")

# =========================================================
# AUTO REFRESH
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh_pro")

# =========================================================
# MAIN TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Scanner", "📈 Smart Money", "🤖 AI Signals",
    "📋 Trades", "📜 History", "🔄 Backtest"
])

# =========================================================
# TAB 1: SCANNER
# =========================================================
with tab1:
    st.subheader("📊 Enhanced Signal Scanner")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("⏰ Time", datetime.now().strftime("%H:%M:%S"))
    col2.metric("📊 Total Coins", len(st.session_state.watchlist))
    col3.metric("🎯 Active Signals", len(st.session_state.pending_signals))
    col4.metric("📈 Win Rate", f"{st.session_state.performance_stats.get('win_rate', 0):.1f}%")
    
    all_signals = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, symbol in enumerate(st.session_state.watchlist[:20]):
        progress_bar.progress((idx + 1) / len(st.session_state.watchlist[:20]))
        status_text.text(f"🔄 Scanning {symbol}...")
        
        result = analyze_mtf_enhanced(
            symbol,
            buffer_pct,
            confirmation_candles=3,
            rr_sl=rr_sl,
            rr_tp=rr_tp,
            min_confirmations=min_confirmations
        )
        
        if result:
            if result["entry_signal"] and symbol not in st.session_state.pending_signals:
                st.session_state.pending_signals[symbol] = {
                    "signal": result["entry_signal"],
                    "time": datetime.now(),
                    "entry": result["entry_price"],
                    "sl": result["stop_loss"],
                    "tp": result["take_profit"],
                    "score": result["total_score"],
                    "confidence": result["confidence"]
                }
                
                save_signal_enhanced({
                    'symbol': symbol,
                    'signal': result["entry_signal"],
                    'entry_price': result["entry_price"],
                    'stop_loss': result["stop_loss"],
                    'take_profit': result["take_profit"],
                    'trend_1h': result["trend_1h"],
                    'trend_15m': result["trend_15m"],
                    'score': result['total_score'],
                    'confidence': result['confidence'],
                    'ai_signal': result['ai']['signal_text'],
                    'smart_money_score': result['smart_money']['score'],
                    'adx_value': result.get('adx_value', 0),
                    'volatility_pct': result['volatility_pct'],
                    'volume_ratio': result.get('volume_ratio', 0)
                })
                
                stats = get_performance_enhanced()
                stats['total_signals'] = stats.get('total_signals', 0) + 1
                update_performance_enhanced(stats)
                
                msg = f"⚡ NEW SIGNAL!\n\nCoin: {symbol}\nSignal: {result['entry_signal']}\nEntry: ${result['entry_price']:.4f}\nSL: ${result['stop_loss']:.4f}\nTP: ${result['take_profit']:.4f}\nScore: {result['total_score']:.0f}\nConfidence: {result['confidence']:.1f}%"
                send_telegram_enhanced(msg)
                
                if st.session_state.auto_trade:
                    execute_trade_enhanced(symbol)
            
            pending = st.session_state.pending_signals.get(symbol)
            if pending:
                entry_display = pending["signal"]
                is_pending = True
            else:
                entry_display = result["entry_signal"] if result["entry_signal"] else "⏳ WAIT"
                is_pending = False
            
            all_signals.append({
                "Coin": symbol,
                "Trend 1H": result["trend_1h"],
                "Trend 15M": result["trend_15m"],
                "Trend 5M": result["trend_5m"],
                "Signal": "🟡 PENDING" if is_pending else entry_display,
                "Score": f"{result['total_score']:.0f}",
                "Confidence": f"{result['confidence']:.0f}%",
                "SM Score": result['smart_money']['score'],
                "AI": result['ai']['signal_text'],
                "Confirm": f"{result['confirmations']:.1f}/3",
                "Volatility": f"{result['volatility_pct']:.1f}%"
            })
    
    progress_bar.empty()
    status_text.empty()
    
    if all_signals:
        df_signals = pd.DataFrame(all_signals)
        df_signals = df_signals.sort_values('Score', ascending=False)
        st.dataframe(df_signals, use_container_width=True, hide_index=True)
        
        best = df_signals.iloc[0]
        st.success(f"🏆 Best Signal: **{best['Coin']}** | Score: {best['Score']} | {best['Signal']} | Confidence: {best['Confidence']}")
    else:
        st.info("ℹ️ No signals found")
    
    if st.session_state.pending_signals:
        st.divider()
        st.subheader("⏳ Pending Signals (Aktif)")
        st.caption(f"Sinyal akan bertahan selama {hold_minutes} menit")
        
        cols = st.columns(min(len(st.session_state.pending_signals), 4))
        for idx, (symbol, data) in enumerate(st.session_state.pending_signals.items()):
            col_idx = idx % len(cols)
            with cols[col_idx]:
                elapsed = (datetime.now() - data["time"]).seconds / 60
                remaining = max(0, hold_minutes - elapsed)
                rr = ((data["tp"] - data["entry"]) / (data["entry"] - data["sl"])) if data["sl"] and data["entry"] - data["sl"] != 0 else 0
                
                st.markdown(f"""
                <div class="pending-signal">
                    <b>{symbol}</b><br>
                    {data['signal']}<br>
                    Entry: {format_price_enhanced(data['entry'])}<br>
                    SL: {format_price_enhanced(data['sl'])}<br>
                    TP: {format_price_enhanced(data['tp'])}<br>
                    Score: {data['score']:.0f}<br>
                    RR: {rr:.2f}<br>
                    ⏱️ {remaining:.0f}m remaining
                </div>
                """, unsafe_allow_html=True)

# =========================================================
# TAB 2: SMART MONEY
# =========================================================
with tab2:
    st.subheader("📈 Enhanced Smart Money Analysis")
    
    sm_coin = st.selectbox("Select Coin", st.session_state.watchlist, key="sm_select_pro")
    
    if sm_coin:
        result = analyze_mtf_enhanced(
            sm_coin,
            buffer_pct,
            confirmation_candles=3,
            rr_sl=rr_sl,
            rr_tp=rr_tp,
            min_confirmations=min_confirmations
        )
        
        if result:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Smart Money Score", f"{result['smart_money']['score']:.0f}/100")
            col2.metric("Market Structure", result['smart_money']['signal'])
            col3.metric("Order Blocks", len(result['smart_money']['order_blocks']))
            col4.metric("FVG", len(result['smart_money']['fvgs']))
            
            with st.expander("📋 Smart Money Details", expanded=True):
                for reason in result['smart_money']['reasons']:
                    st.write(f"• {reason}")
                
                st.subheader("Order Blocks")
                for ob in result['smart_money']['order_blocks']:
                    st.write(f"• {ob['type']}: {format_price_enhanced(ob['low'])} - {format_price_enhanced(ob['high'])} (Strength: {ob['strength']:.2f})")
                
                st.subheader("Fair Value Gaps")
                for fvg in result['smart_money']['fvgs']:
                    st.write(f"• {fvg['type']}: {format_price_enhanced(fvg['low'])} - {format_price_enhanced(fvg['high'])} (Size: {fvg['size']:.2f}%)")
            
            fig = create_enhanced_chart(result, sm_coin)
            st.plotly_chart(fig, use_container_width=True)

# =========================================================
# TAB 3: AI SIGNALS
# =========================================================
with tab3:
    st.subheader("🤖 Enhanced AI Signal Analysis (Random Forest)")
    
    ai_coin = st.selectbox("Select Coin", st.session_state.watchlist, key="ai_select_pro")
    
    if ai_coin:
        df_train = data_manager.get_data(ai_coin, "15m", "7d")
        if df_train is not None and not df_train.empty:
            predictor = get_predictor()
            if not predictor.is_trained:
                with st.spinner("Training AI model with Random Forest..."):
                    predictor.train(df_train)
                    if predictor.is_trained:
                        st.success("✅ AI Model Trained Successfully!")
                    else:
                        st.warning("⚠️ Insufficient data for training")
        
        result = analyze_mtf_enhanced(
            ai_coin,
            buffer_pct,
            confirmation_candles=3,
            rr_sl=rr_sl,
            rr_tp=rr_tp,
            min_confirmations=min_confirmations
        )
        
        if result:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("AI Confidence", f"{result['ai']['confidence']:.0f}/100")
            col2.metric("Signal", result['ai']['signal_text'])
            col3.metric("Model", result['ai'].get('model_version', 'RF v2.0'))
            col4.metric("Strength", "STRONG" if result['ai']['confidence'] > 70 else "WEAK")
            
            prob_df = pd.DataFrame({
                'Signal': ['Buy', 'Sell', 'Hold'],
                'Probability': [
                    result['ai']['buy_prob'],
                    result['ai']['sell_prob'],
                    result['ai']['hold_prob']
                ]
            })
            st.subheader("📊 Probability Distribution")
            st.bar_chart(prob_df.set_index('Signal'))
            
            if predictor.is_trained and predictor.feature_importance:
                st.subheader("📊 Top 10 Feature Importance")
                imp_df = pd.DataFrame(
                    list(predictor.feature_importance.items()),
                    columns=['Feature', 'Importance']
                ).sort_values('Importance', ascending=False).head(10)
                st.dataframe(imp_df, use_container_width=True, hide_index=True)

# =========================================================
# TAB 4: TRADES
# =========================================================
with tab4:
    st.subheader("📋 Trade Management")
    
    auto_trade = st.toggle("🤖 Auto Trading", value=st.session_state.auto_trade)
    st.session_state.auto_trade = auto_trade
    
    if auto_trade:
        st.info("🤖 Auto Trading ACTIVE! Monitoring positions...")
        monitor_positions_enhanced()
        st_autorefresh(interval=60000, key="auto_trade_refresh")
    
    trades = get_trades_enhanced()
    open_trades = [t for t in trades if t.get('status') == 'OPEN']
    
    st.subheader("📊 Open Positions")
    if open_trades:
        df_open = pd.DataFrame(open_trades)
        display_cols = ['symbol', 'type', 'entry_price', 'stop_loss', 'take_profit', 
                       'score', 'confidence', 'rr_ratio', 'entry_time']
        available_cols = [c for c in display_cols if c in df_open.columns]
        st.dataframe(df_open[available_cols], use_container_width=True)
    else:
        st.info("No open positions")
    
    st.subheader("📊 Closed Trades")
    closed_trades = [t for t in trades if t.get('status') == 'CLOSED']
    
    if closed_trades:
        df_closed = pd.DataFrame(closed_trades)
        display_cols = ['symbol', 'type', 'entry_price', 'exit_price', 
                       'profit_pct', 'holding_period', 'exit_time']
        available_cols = [c for c in display_cols if c in df_closed.columns]
        st.dataframe(df_closed[available_cols], use_container_width=True)
        
        stats = get_performance_enhanced()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", stats.get('total_signals', 0))
        col2.metric("Wins", stats.get('wins', 0))
        col3.metric("Losses", stats.get('losses', 0))
        col4.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")

# =========================================================
# TAB 5: HISTORY
# =========================================================
with tab5:
    st.subheader("📜 Signal History")
    
    history = get_signal_history_enhanced(limit=100)
    if history:
        df_history = pd.DataFrame(history)
        if 'id' in df_history.columns:
            df_history = df_history.drop('id', axis=1)
        st.dataframe(df_history, use_container_width=True, hide_index=True)
        
        csv = df_history.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No signals yet")

# =========================================================
# TAB 6: BACKTEST
# =========================================================
with tab6:
    st.subheader("🔄 Enhanced Backtesting")
    
    col1, col2 = st.columns(2)
    with col1:
        bt_coin = st.selectbox("Coin", st.session_state.watchlist, key="bt_select_pro")
        bt_period = st.selectbox("Period", ["1mo", "3mo", "6mo", "1y"], index=1)
    with col2:
        bt_interval = st.selectbox("Interval", ["15m", "30m", "1h", "4h"], index=2)
        bt_rr = st.slider("RR Ratio", 1.0, 5.0, 3.0, 0.5)
    
    if st.button("🚀 Run Enhanced Backtest", use_container_width=True):
        with st.spinner(f"Running backtest on {bt_coin}..."):
            result = run_enhanced_backtest(bt_coin, bt_period, bt_interval, bt_rr)
            
            if result:
                st.session_state.backtest_result = result
                
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                col1.metric("Total Trades", result['total_trades'])
                col2.metric("Win Rate", f"{result['win_rate']:.1f}%")
                col3.metric("Total Profit", f"{result['total_profit']:.2f}%")
                col4.metric("Final Balance", f"${result['final_balance']:.2f}")
                col5.metric("Total Return", f"{result['total_return']:.1f}%")
                col6.metric("Max Drawdown", f"{result['max_drawdown']:.1f}%")
                
                if result['trades']:
                    df_bt = pd.DataFrame(result['trades'])
                    st.dataframe(df_bt, use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"""
🔄 Enhanced System | Multi-Timeframe: 1H, 15M, 5M
📊 Total Coins: {len(st.session_state.watchlist)} | ⚡ Leverage: {leverage}x
🎯 Dynamic Risk: {risk_per_trade}% | 📊 RR: 1:{rr_tp/rr_sl:.1f}
💾 Database: SQLite PRO | 🤖 AI: Random Forest v2.0
🛡️ Trailing Stop: {'ACTIVE' if use_trailing else 'INACTIVE'}
""")
