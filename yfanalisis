import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="gas", layout="wide")

# =========================================================
# CSS KUSTOM
# =========================================================
st.markdown("""
<style>
    .stButton > button {
        width: 100%;
        background: linear-gradient(145deg, #00ff88, #00cc66);
        color: black;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 0 20px rgba(0,255,136,0.3);
    }
    .coin-badge {
        display: inline-block;
        background: rgba(0,255,136,0.1);
        border: 1px solid rgba(0,255,136,0.3);
        border-radius: 20px;
        padding: 4px 14px;
        margin: 3px;
        font-size: 14px;
        color: #00ff88;
    }
    .delete-btn {
        background: rgba(255,59,92,0.15) !important;
        border: 1px solid rgba(255,59,92,0.3) !important;
        color: #ff3b5c !important;
        padding: 2px 12px !important;
        font-size: 12px !important;
        border-radius: 12px !important;
        cursor: pointer;
    }
    .delete-btn:hover {
        background: rgba(255,59,92,0.3) !important;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# GOOGLE SHEETS (DENGAN FALLBACK KE SESSION STATE)
# =========================================================
@st.cache_resource
def load_sheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        return client.open("CryptoWatchlist").sheet1
    except:
        return None

# Inisialisasi session state untuk watchlist
if "watchlist" not in st.session_state:
    sheet = load_sheet()
    if sheet:
        try:
            symbols = sheet.col_values(1)
            st.session_state.watchlist = [x.strip().upper() for x in symbols if x.strip()]
        except:
            st.session_state.watchlist = ["BTC"]
    else:
        st.session_state.watchlist = ["BTC"]

# =========================================================
# FUNGSI MANAJEMEN WATCHLIST
# =========================================================
def add_coin_to_watchlist(coin):
    """Tambah coin ke watchlist"""
    coin = coin.upper().strip()
    if coin and coin not in st.session_state.watchlist:
        st.session_state.watchlist.append(coin)
        
        # Simpan ke Google Sheets jika tersedia
        sheet = load_sheet()
        if sheet:
            try:
                sheet.append_row([coin])
            except:
                pass
        return True
    return False

def remove_coin_from_watchlist(coin):
    """Hapus coin dari watchlist"""
    if coin in st.session_state.watchlist:
        st.session_state.watchlist.remove(coin)
        
        # Hapus dari Google Sheets jika tersedia
        sheet = load_sheet()
        if sheet:
            try:
                cell = sheet.find(coin)
                if cell:
                    sheet.delete_rows(cell.row)
            except:
                pass
        return True
    return False

def reset_watchlist():
    """Reset watchlist ke default"""
    default = ["BTC"]
    st.session_state.watchlist = default.copy()
    
    # Update Google Sheets
    sheet = load_sheet()
    if sheet:
        try:
            sheet.clear()
            for coin in default:
                sheet.append_row([coin])
        except:
            pass

# =========================================================
# TITLE
# =========================================================
st.title("gas")
st.caption("1H Trend | 15M S/R | 5M Entry")

# =========================================================
# DASHBOARD: MANAJEMEN WATCHLIST
# =========================================================
with st.expander("📋 Manage Watchlist", expanded=True):
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        # Form untuk tambah coin
        with st.form(key="add_coin_form", clear_on_submit=True):
            input_col1, input_col2 = st.columns([3, 1])
            with input_col1:
                new_coin_input = st.text_input(
                    "Tambah Coin",
                    placeholder="Contoh: PEPE, DOT, MATIC",
                    label_visibility="collapsed"
                )
            with input_col2:
                submit_button = st.form_submit_button("➕ Add Coin", use_container_width=True)
            
            if submit_button and new_coin_input:
                if add_coin_to_watchlist(new_coin_input):
                    st.success(f"✅ {new_coin_input.upper()} added to watchlist!")
                    st.rerun()
                else:
                    st.warning(f"⚠️ {new_coin_input.upper()} already in watchlist or invalid")
    
    with col2:
        # Tombol reset
        if st.button("🔄 Reset to Default", use_container_width=True):
            reset_watchlist()
            st.rerun()
    
    with col3:
        # Tombol refresh data
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # Tampilkan watchlist saat ini dengan badge
    st.markdown("---")
    st.markdown("**📌 Watchlist Saat Ini:**")
    
    if st.session_state.watchlist:
        # Tampilkan coin dalam baris
        cols = st.columns(min(len(st.session_state.watchlist), 6))
        for idx, coin in enumerate(st.session_state.watchlist):
            col_idx = idx % len(cols)
            with cols[col_idx]:
                # Tampilkan badge dengan tombol delete
                col_coin, col_del = st.columns([4, 1])
                with col_coin:
                    st.markdown(f'<span class="coin-badge">💎 {coin}</span>', unsafe_allow_html=True)
                with col_del:
                    if st.button("✕", key=f"del_{coin}", help=f"Hapus {coin}"):
                        remove_coin_from_watchlist(coin)
                        st.rerun()
    else:
        st.info("Watchlist kosong. Tambahkan coin di atas!")

# =========================================================
# SIDEBAR SETTINGS
# =========================================================
st.sidebar.header("⚙️ Settings")

# === SETTINGS ===
refresh = st.sidebar.slider("Refresh (detik)", 5, 60, 10)
currency = st.sidebar.selectbox("Currency", ["USD", "IDR"])
leverage = st.sidebar.slider("Leverage", 1, 125, 10)
position_size = st.sidebar.number_input("Position Size (USD)", 10, 100000, 100)

# === TELEGRAM ===
st.sidebar.subheader("📱 Telegram Alert")
BOT_TOKEN = "8819178689:AAHBU4dTqoIUfGvkarKRZLI6wbfKJh6g0RU"
CHAT_ID = "999556266"

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except:
        pass

if st.sidebar.button("🚀 Test Telegram", use_container_width=True):
    send_telegram("🚀 Telegram Connected!")
    st.sidebar.success("✅ Pesan test terkirim!")

# === STATUS ===
st.sidebar.subheader("📊 Status")
st.sidebar.write(f"**Total Coins:** {len(st.session_state.watchlist)}")
st.sidebar.write(f"**Auto Refresh:** {refresh} detik")

# =========================================================
# AUTO REFRESH
# =========================================================
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=refresh*1000, key="refresh")

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
def format_price(value, symbol):
    if symbol == "Rp":
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
# FUNGSI AMBIL DATA
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
def EMA(df, col="Close", period=20):
    return df[col].ewm(span=period, adjust=False).mean()

def RSI(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

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

# =========================================================
# ANALISIS MULTI TIMEFRAME
# =========================================================
def analyze_mtf(symbol):
    # --- 1H TREND ---
    df_1h = get_data_safe(symbol, "1h", min_candles=30)
    if df_1h is None:
        return None
    
    # --- 15M S/R ---
    df_15m = get_data_safe(symbol, "15m", min_candles=50)
    if df_15m is None:
        df_15m = df_1h.copy()
    
    # --- 5M ENTRY ---
    df_5m = get_data_safe(symbol, "5m", min_candles=20)
    if df_5m is None:
        df_5m = df_15m.copy()
    
    # --- 1H TREND ---
    df_1h["EMA20"] = EMA(df_1h)
    df_1h["EMA50"] = EMA(df_1h, period=50)
    df_1h["ADX"] = ADX(df_1h)
    
    last = df_1h.iloc[-1]
    price_1h = last["Close"]
    ema20 = last["EMA20"] if not pd.isna(last["EMA20"]) else price_1h
    ema50 = last["EMA50"] if not pd.isna(last["EMA50"]) else price_1h
    adx = last["ADX"] if not pd.isna(last["ADX"]) else 0
    
    if price_1h > ema20 > ema50 and adx > 25:
        trend = "🟢 BULLISH (Strong)"
    elif price_1h > ema20 > ema50:
        trend = "🟢 BULLISH"
    elif price_1h < ema20 < ema50 and adx > 25:
        trend = "🔴 BEARISH (Strong)"
    elif price_1h < ema20 < ema50:
        trend = "🔴 BEARISH"
    else:
        trend = "🟡 SIDEWAYS"
    
    # --- 15M SUPPORT/RESISTANCE ---
    period = 20
    recent_high = df_15m["High"].tail(period).max()
    recent_low = df_15m["Low"].tail(period).min()
    pivot = (df_15m["High"].tail(period).max() + df_15m["Low"].tail(period).min() + df_15m["Close"].tail(period).mean()) / 3
    r1 = 2 * pivot - recent_low
    s1 = 2 * pivot - recent_high
    
    support = s1
    resistance = r1
    
    # --- 5M ENTRY SIGNAL ---
    df_5m["RSI"] = RSI(df_5m, period=14)
    df_5m["EMA10"] = EMA(df_5m, period=10)
    df_5m["Volume_MA"] = df_5m["Volume"].rolling(5).mean()
    
    last_5m = df_5m.iloc[-1]
    price_5m = last_5m["Close"]
    rsi_5m = last_5m["RSI"] if not pd.isna(last_5m["RSI"]) else 50
    vol = last_5m["Volume"]
    vol_ma = last_5m["Volume_MA"] if not pd.isna(last_5m["Volume_MA"]) else vol
    vol_spike = vol > vol_ma * 1.5 if vol_ma > 0 else False
    
    entry_signal = None
    is_bullish = "BULLISH" in trend
    is_bearish = "BEARISH" in trend
    
    if is_bullish:
        if price_5m > support and rsi_5m < 45:
            entry_signal = "🟢 BUY (Pullback to Support)"
        elif price_5m > resistance and vol_spike:
            entry_signal = "🟢 BUY (Breakout)"
    elif is_bearish:
        if price_5m < resistance and rsi_5m > 55:
            entry_signal = "🔴 SELL (Pullback to Resistance)"
        elif price_5m < support and vol_spike:
            entry_signal = "🔴 SELL (Breakdown)"
    else:
        if price_5m > resistance and vol_spike:
            entry_signal = "🟢 BUY (Breakout)"
        elif price_5m < support and vol_spike:
            entry_signal = "🔴 SELL (Breakdown)"
    
    atr_5m = ATR(df_5m, period=14).iloc[-1] if len(df_5m) > 14 else (df_5m["High"].iloc[-1] - df_5m["Low"].iloc[-1])
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
        "adx_1h": adx,
        "price": price_5m,
        "df_1h": df_1h.tail(50),
        "df_15m": df_15m.tail(50),
        "df_5m": df_5m.tail(30)
    }

# =========================================================
# MAIN LOOP - TAMPILKAN SEMUA COIN
# =========================================================
if "last_alert" not in st.session_state:
    st.session_state.last_alert = {}

# Cek apakah watchlist kosong
if not st.session_state.watchlist:
    st.warning("⚠️ Watchlist kosong! Tambahkan coin di bagian 'Manage Watchlist'")
    st.stop()

# Progress bar untuk loading
progress_bar = st.progress(0)
status_text = st.empty()

for idx, sym in enumerate(st.session_state.watchlist):
    # Update progress
    progress_bar.progress((idx + 1) / len(st.session_state.watchlist))
    status_text.text(f"🔄 Menganalisis {sym}...")
    
    with st.container():
        st.divider()
        st.subheader(f"📈 {sym}")
        
        result = analyze_mtf(sym)
        if result is None:
            st.warning(f"⚠️ Data {sym} tidak mencukupi (coba lagi nanti)")
            continue
        
        # Tampilkan metrik
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Trend (1H)", result["trend"])
        col2.metric("Support (15M)", format_price(result["support"] * currency_rate, currency_symbol))
        col3.metric("Resistance (15M)", format_price(result["resistance"] * currency_rate, currency_symbol))
        col4.metric("RSI (5M)", f"{result['rsi_5m']:.1f}")
        
        # Entry Signal
        if result["entry_signal"]:
            st.success(f"🚀 **{result['entry_signal']}**")
            
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Entry", format_price(result["entry_price"] * currency_rate, currency_symbol))
            col_b.metric("Stop Loss", format_price(result["stop_loss"] * currency_rate, currency_symbol), 
                        delta=f"-{(result['stop_loss']/result['entry_price'] - 1)*100:.1f}%")
            col_c.metric("Take Profit", format_price(result["take_profit"] * currency_rate, currency_symbol),
                        delta=f"{(result['take_profit']/result['entry_price'] - 1)*100:.1f}%")
            
            # Telegram Alert
            if sym not in st.session_state.last_alert or st.session_state.last_alert[sym] != result["entry_signal"]:
                message = f"""⚡ MTF SIGNAL

Coin : {sym}
Signal : {result['entry_signal']}
Trend : {result['trend']}

Entry : ${result['entry_price']:.4f}
SL : ${result['stop_loss']:.4f}
TP : ${result['take_profit']:.4f}

Leverage : {leverage}x
Position : ${position_size * leverage:,.0f}

Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                send_telegram(message)
                st.session_state.last_alert[sym] = result["entry_signal"]
        
        # 3 Chart dalam Tabs
        tab1, tab2, tab3 = st.tabs(["📊 1H Trend", "📊 15M S/R", "📊 5M Entry"])
        
        with tab1:
            fig1 = go.Figure()
            fig1.add_trace(go.Candlestick(
                x=result["df_1h"]["Time"],
                open=result["df_1h"]["Open"],
                high=result["df_1h"]["High"],
                low=result["df_1h"]["Low"],
                close=result["df_1h"]["Close"],
                name="1H"
            ))
            fig1.add_trace(go.Scatter(
                x=result["df_1h"]["Time"],
                y=result["df_1h"]["EMA20"],
                line=dict(color="cyan", width=1.5), name="EMA20"
            ))
            fig1.add_trace(go.Scatter(
                x=result["df_1h"]["Time"],
                y=result["df_1h"]["EMA50"],
                line=dict(color="orange", width=1.5), name="EMA50"
            ))
            fig1.update_layout(
                height=350,
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                paper_bgcolor="#050816",
                plot_bgcolor="#0a0a1a"
            )
            st.plotly_chart(fig1, use_container_width=True)
        
        with tab2:
            fig2 = go.Figure()
            fig2.add_trace(go.Candlestick(
                x=result["df_15m"]["Time"],
                open=result["df_15m"]["Open"],
                high=result["df_15m"]["High"],
                low=result["df_15m"]["Low"],
                close=result["df_15m"]["Close"],
                name="15M"
            ))
            fig2.add_hline(y=result["support"], line_dash="dot", line_color="green", 
                          annotation_text=f"S {format_price(result['support']*currency_rate, currency_symbol)}")
            fig2.add_hline(y=result["resistance"], line_dash="dot", line_color="red",
                          annotation_text=f"R {format_price(result['resistance']*currency_rate, currency_symbol)}")
            fig2.update_layout(
                height=350,
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                paper_bgcolor="#050816",
                plot_bgcolor="#0a0a1a"
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        with tab3:
            fig3 = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                row_heights=[0.65, 0.35])
            
            # Candlestick
            fig3.add_trace(go.Candlestick(
                x=result["df_5m"]["Time"],
                open=result["df_5m"]["Open"],
                high=result["df_5m"]["High"],
                low=result["df_5m"]["Low"],
                close=result["df_5m"]["Close"],
                name="5M"
            ), row=1, col=1)
            
            # RSI
            fig3.add_trace(go.Scatter(
                x=result["df_5m"]["Time"],
                y=result["df_5m"]["RSI"],
                line=dict(color="purple", width=1.5), name="RSI"
            ), row=2, col=1)
            fig3.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig3.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
            fig3.add_hline(y=50, line_dash="dash", line_color="gray", row=2, col=1)
            
            fig3.update_layout(
                height=400,
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                paper_bgcolor="#050816",
                plot_bgcolor="#0a0a1a"
            )
            st.plotly_chart(fig3, use_container_width=True)

# Clear progress
progress_bar.empty()
status_text.empty()

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"""
🔄 Data dari Yahoo Finance | Multi Time Frame: 1H, 15M, 5M  
💱 Currency: {currency} | 🔄 Auto Refresh: {refresh} detik  
📊 Total Coins: {len(st.session_state.watchlist)} | ⚡ Leverage: {leverage}x
""")
