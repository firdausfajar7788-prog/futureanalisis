import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
from datetime import datetime, timedelta
import warnings
import os
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from supabase import create_client, Client

load_dotenv()
warnings.filterwarnings('ignore')

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="📊 Volume Monitor - Crypto",
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
    .volume-spike {
        background: linear-gradient(135deg, rgba(0,255,136,0.2), rgba(0,255,136,0.05));
        border: 1px solid #00ff88;
        border-radius: 12px;
        padding: 12px 20px;
        color: #00ff88;
        font-weight: 600;
        animation: pulse 1.5s infinite;
    }
    .volume-low {
        background: linear-gradient(135deg, rgba(255,59,92,0.2), rgba(255,59,92,0.05));
        border: 1px solid #ff3b5c;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ff3b5c;
        font-weight: 600;
    }
    .volume-normal {
        background: linear-gradient(135deg, rgba(255,170,0,0.2), rgba(255,170,0,0.05));
        border: 1px solid #ffaa00;
        border-radius: 12px;
        padding: 12px 20px;
        color: #ffaa00;
        font-weight: 600;
    }
    @keyframes pulse {
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
# DATABASE FUNCTIONS (Watchlist)
# =========================================================
def get_watchlist():
    supabase = get_supabase()
    try:
        res = supabase.table("watchlist").select("symbol").order("added_at").execute()
        return [row["symbol"] for row in res.data] if res.data else ["BTC", "ETH", "BNB", "SOL", "XRP"]
    except:
        return ["BTC", "ETH", "BNB", "SOL", "XRP"]

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

# =========================================================
# DATABASE FUNCTIONS (Volume Alerts)
# =========================================================
def save_volume_alert(data):
    supabase = get_supabase()
    try:
        # Cek duplikat 5 menit
        five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        check = supabase.table("volume_alerts")\
            .select("id")\
            .eq("symbol", data["symbol"])\
            .gte("timestamp", five_min_ago)\
            .execute()
        if len(check.data) > 0:
            return False
        
        data["timestamp"] = datetime.now().isoformat()
        supabase.table("volume_alerts").insert(data).execute()
        return True
    except:
        return False

def get_volume_alerts(limit=100):
    supabase = get_supabase()
    try:
        res = supabase.table("volume_alerts")\
            .select("*")\
            .order("timestamp", desc=True)\
            .limit(limit)\
            .execute()
        return res.data if res.data else []
    except:
        return []

def update_stats(stats):
    supabase = get_supabase()
    try:
        supabase.table("performance").upsert(
            {"key": "volume_stats", "value": stats, "updated_at": datetime.now().isoformat()},
            on_conflict="key"
        ).execute()
        return True
    except:
        return False

def get_stats():
    supabase = get_supabase()
    default = {"total_alerts": 0, "today_alerts": 0, "avg_ratio": 0}
    try:
        res = supabase.table("performance").select("value").eq("key", "volume_stats").execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["value"]
        return default
    except:
        return default

# =========================================================
# SESSION STATE
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()
if "last_update" not in st.session_state:
    st.session_state.last_update = datetime.now()
if "volume_alerts_sent" not in st.session_state:
    st.session_state.volume_alerts_sent = {}

# =========================================================
# HEADER
# =========================================================
st.title("📊 Volume Monitor - Crypto")
st.caption("Monitoring volume per jam | Deteksi lonjakan volume | Supabase + Telegram")
col_time, _ = st.columns([2, 3])
with col_time:
    st.caption(f"🕐 Last updated: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("📋 Watchlist")
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
    
    st.subheader("📊 Settings")
    refresh = st.slider("🔄 Refresh (detik)", 10, 120, 30)
    volume_threshold = st.slider("🚨 Alert Threshold (x avg)", 1.5, 5.0, 2.5, 0.5)
    lookback_hours = st.slider("📊 Lookback (jam)", 12, 72, 24)
    
    st.divider()
    
    st.subheader("📱 Telegram Alert")
    bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
    
    if bot_token and chat_id:
        st.success("✅ Telegram Connected")
        if st.button("🚀 Test Telegram", use_container_width=True):
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                r = requests.post(url, json={"chat_id": chat_id, "text": "📊 Volume Monitor Aktif!"}, timeout=10)
                if r.status_code == 200:
                    st.success("✅ Pesan test terkirim!")
                else:
                    st.error(f"❌ Error: {r.status_code}")
            except Exception as e:
                st.error(f"❌ Error: {e}")
    else:
        st.warning("⚠️ Bot Token & Chat ID tidak ditemukan")
    
    st.divider()
    
    st.subheader("📊 Stats")
    stats = get_stats()
    st.metric("Total Alerts", stats.get("total_alerts", 0))
    st.metric("Today Alerts", stats.get("today_alerts", 0))
    st.metric("Avg Ratio", f"{stats.get('avg_ratio', 0):.2f}x")
    
    st.caption("📊 **Volume Level:**")
    st.caption("🟢 High (> 2x avg) - Potensi breakout")
    st.caption("🟡 Normal (0.5x - 2x avg)")
    st.caption("🔴 Low (< 0.5x avg) - Sepi")

# =========================================================
# FUNGSI AMBIL DATA
# =========================================================
@st.cache_data(ttl=30, show_spinner=False)
def get_volume_data(symbol, period="7d", interval="1h"):
    try:
        ticker = f"{symbol}-USD"
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df.rename(columns={df.columns[0]: "Time"}, inplace=True)
        df["Time"] = pd.to_datetime(df["Time"])
        df["Volume"] = df["Volume"].fillna(0)
        return df
    except:
        return None

@st.cache_data(ttl=30, show_spinner=False)
def get_all_volume_data(symbols, interval="1h", hours=24):
    results = {}
    for symbol in symbols:
        df = get_volume_data(symbol, period="7d", interval=interval)
        if df is not None and not df.empty:
            df_24h = df.tail(hours)
            if len(df_24h) >= 12:
                results[symbol] = {
                    "df": df,
                    "df_24h": df_24h,
                    "last_volume": df_24h["Volume"].iloc[-1],
                    "avg_volume": df_24h["Volume"].mean(),
                    "max_volume": df_24h["Volume"].max(),
                    "min_volume": df_24h["Volume"].min(),
                    "volume_ratio": df_24h["Volume"].iloc[-1] / df_24h["Volume"].mean() if df_24h["Volume"].mean() > 0 else 1,
                    "last_price": df_24h["Close"].iloc[-1],
                    "price_change": ((df_24h["Close"].iloc[-1] - df_24h["Close"].iloc[0]) / df_24h["Close"].iloc[0]) * 100
                }
    return results

# =========================================================
# TELEGRAM ALERT
# =========================================================
def send_telegram_alert(symbol, volume_ratio, volume, avg_volume, price, price_change):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            return False
        
        emoji = "🚀🚀🚀" if volume_ratio > 3 else "🚀🚀" if volume_ratio > 2.5 else "🚀"
        msg = f"""{emoji} <b>VOLUME SPIKE!</b>

<b>Coin:</b> {symbol}
<b>Volume:</b> {volume:,.0f}
<b>Avg 24h:</b> {avg_volume:,.0f}
<b>Ratio:</b> <b>{volume_ratio:.2f}x</b>
<b>Price:</b> ${price:.4f}
<b>24h Change:</b> {price_change:.2f}%
🕐 {datetime.now().strftime('%H:%M:%S')}"""
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except:
        return False

# =========================================================
# FORMAT VOLUME
# =========================================================
def format_volume(value):
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value/1_000:.2f}K"
    else:
        return f"{value:.0f}"

# =========================================================
# LIQUIDITY ZONES DETECTION
# =========================================================
def find_pivots(df, length=7):
    """
    Mencari pivot high dan low
    Sama seperti ta.pivothigh() dan ta.pivotlow() di Pine Script
    """
    highs = df['High']
    lows = df['Low']
    
    pivot_high_idx = []
    pivot_high_val = []
    pivot_low_idx = []
    pivot_low_val = []
    
    for i in range(length, len(df) - length):
        # Pivot High
        is_high = True
        for j in range(1, length + 1):
            if highs.iloc[i] <= highs.iloc[i - j] or highs.iloc[i] <= highs.iloc[i + j]:
                is_high = False
                break
        if is_high:
            pivot_high_idx.append(i)
            pivot_high_val.append(highs.iloc[i])
        
        # Pivot Low
        is_low = True
        for j in range(1, length + 1):
            if lows.iloc[i] >= lows.iloc[i - j] or lows.iloc[i] >= lows.iloc[i + j]:
                is_low = False
                break
        if is_low:
            pivot_low_idx.append(i)
            pivot_low_val.append(lows.iloc[i])
    
    return pivot_high_idx, pivot_high_val, pivot_low_idx, pivot_low_val

def detect_liquidity_zones(df, length=7, margin=2.3):
    """
    Deteksi zona likuiditas berdasarkan pivot yang berkelompok
    """
    if df is None or len(df) < 30:
        return [], []
    
    pivot_high_idx, pivot_high_val, pivot_low_idx, pivot_low_val = find_pivots(df, length)
    
    # Hitung ATR
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    if pd.isna(atr) or atr == 0:
        atr = (df['High'] - df['Low']).mean() * 0.5
    
    buy_zones = []
    sell_zones = []
    
    # Cari buyside liquidity (pivot high berkelompok)
    i = 0
    while i < len(pivot_high_idx):
        group_idx = [pivot_high_idx[i]]
        group_val = [pivot_high_val[i]]
        j = i + 1
        while j < len(pivot_high_idx):
            if abs(pivot_high_val[j] - pivot_high_val[i]) < atr / margin:
                group_idx.append(pivot_high_idx[j])
                group_val.append(pivot_high_val[j])
                j += 1
            else:
                break
        
        if len(group_idx) >= 3:
            avg_price = sum(group_val) / len(group_val)
            buy_zones.append({
                'start_idx': group_idx[0],
                'end_idx': group_idx[-1],
                'price': avg_price,
                'high': avg_price + (atr / margin),
                'low': avg_price - (atr / margin)
            })
        i = j if j > i else i + 1
    
    # Cari sellside liquidity (pivot low berkelompok)
    i = 0
    while i < len(pivot_low_idx):
        group_idx = [pivot_low_idx[i]]
        group_val = [pivot_low_val[i]]
        j = i + 1
        while j < len(pivot_low_idx):
            if abs(pivot_low_val[j] - pivot_low_val[i]) < atr / margin:
                group_idx.append(pivot_low_idx[j])
                group_val.append(pivot_low_val[j])
                j += 1
            else:
                break
        
        if len(group_idx) >= 3:
            avg_price = sum(group_val) / len(group_val)
            sell_zones.append({
                'start_idx': group_idx[0],
                'end_idx': group_idx[-1],
                'price': avg_price,
                'high': avg_price + (atr / margin),
                'low': avg_price - (atr / margin)
            })
        i = j if j > i else i + 1
    
    return buy_zones, sell_zones

def add_liquidity_zones_to_fig(fig, df, buy_zones, sell_zones):
    """
    Tambahkan zona likuiditas ke chart yang sudah ada
    """
    # Buyside Liquidity (Hijau)
    for zone in buy_zones:
        if zone['start_idx'] < len(df) and zone['end_idx'] < len(df):
            fig.add_hrect(
                y0=zone['low'],
                y1=zone['high'],
                fillcolor='rgba(0,255,136,0.15)',
                line=dict(color='rgba(0,255,136,0.6)', width=1, dash='dash'),
                annotation_text=f"🟢 Buyside {zone['price']:,.0f}",
                annotation_position="bottom left",
                annotation_font=dict(color='#00ff88', size=10)
            )
            fig.add_hline(
                y=zone['price'],
                line=dict(color='rgba(0,255,136,0.3)', width=1, dash='dot')
            )
    
    # Sellside Liquidity (Merah)
    for zone in sell_zones:
        if zone['start_idx'] < len(df) and zone['end_idx'] < len(df):
            fig.add_hrect(
                y0=zone['low'],
                y1=zone['high'],
                fillcolor='rgba(255,59,92,0.15)',
                line=dict(color='rgba(255,59,92,0.6)', width=1, dash='dash'),
                annotation_text=f"🔴 Sellside {zone['price']:,.0f}",
                annotation_position="top left",
                annotation_font=dict(color='#ff3b5c', size=10)
            )
            fig.add_hline(
                y=zone['price'],
                line=dict(color='rgba(255,59,92,0.3)', width=1, dash='dot')
            )
    
    return fig

# =========================================================
# MAIN
# =========================================================
st_autorefresh(interval=refresh * 1000, key="refresh")

with st.spinner("📊 Mengambil data volume..."):
    data = get_all_volume_data(st.session_state.watchlist, interval="1h", hours=lookback_hours)

if not data:
    st.warning("⚠️ Tidak ada data yang bisa ditampilkan")
    st.stop()

st.session_state.last_update = datetime.now()

# =========================================================
# METRICS
# =========================================================
total_volume = sum([d["last_volume"] for d in data.values()])
high_volume = len([d for d in data.values() if d["volume_ratio"] > 2])
low_volume = len([d for d in data.values() if d["volume_ratio"] < 0.5])
avg_ratio = sum([d["volume_ratio"] for d in data.values()]) / len(data) if data else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🪙 Coins", len(data))
c2.metric("📊 Total 1H Volume", format_volume(total_volume))
c3.metric("🟢 High (>2x)", high_volume)
c4.metric("🔴 Low (<0.5x)", low_volume)
c5.metric("📈 Avg Ratio", f"{avg_ratio:.2f}x")

# =========================================================
# VOLUME ALERTS
# =========================================================
alerts = []
stats = get_stats()

for symbol, d in data.items():
    if d["volume_ratio"] > volume_threshold:
        alerts.append({
            "Coin": symbol,
            "Ratio": f"{d['volume_ratio']:.2f}x",
            "Volume": format_volume(d["last_volume"]),
            "Avg 24h": format_volume(d["avg_volume"]),
            "Price": f"${d['last_price']:.4f}",
            "24h Change": f"{d['price_change']:.2f}%"
        })
        
        now = datetime.now()
        if symbol not in st.session_state.volume_alerts_sent or \
           (now - st.session_state.volume_alerts_sent[symbol]).seconds > 1800:
            if send_telegram_alert(symbol, d["volume_ratio"], d["last_volume"], d["avg_volume"], d["last_price"], d["price_change"]):
                st.session_state.volume_alerts_sent[symbol] = now
                alert_data = {
                    "symbol": symbol,
                    "volume": d["last_volume"],
                    "avg_volume": d["avg_volume"],
                    "ratio": d["volume_ratio"],
                    "price": d["last_price"],
                    "price_change": d["price_change"],
                    "threshold": volume_threshold
                }
                if save_volume_alert(alert_data):
                    stats["total_alerts"] = stats.get("total_alerts", 0) + 1
                    stats["today_alerts"] = stats.get("today_alerts", 0) + 1
                    old_avg = stats.get("avg_ratio", 0)
                    old_count = stats.get("total_alerts", 0) - 1
                    if old_count > 0:
                        stats["avg_ratio"] = ((old_avg * old_count) + d["volume_ratio"]) / (old_count + 1)
                    else:
                        stats["avg_ratio"] = d["volume_ratio"]
                    update_stats(stats)

# =========================================================
# ALERT SECTION
# =========================================================
if alerts:
    st.subheader("🚨 Volume Spikes Detected!")
    st.caption(f"Threshold: {volume_threshold}x | Total spikes: {len(alerts)}")
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
else:
    st.info("✅ Tidak ada lonjakan volume")

# =========================================================
# VOLUME TABLE
# =========================================================
st.subheader("📊 Volume per Coin")

table_data = []
for symbol, d in data.items():
    status = "🟢 HIGH" if d["volume_ratio"] > 2 else "🔴 LOW" if d["volume_ratio"] < 0.5 else "🟡 NORMAL"
    table_data.append({
        "Coin": symbol,
        "Volume": format_volume(d["last_volume"]),
        "Avg 24h": format_volume(d["avg_volume"]),
        "Ratio": f"{d['volume_ratio']:.2f}x",
        "Price": f"${d['last_price']:.4f}",
        "24h Change": f"{d['price_change']:.2f}%",
        "Status": status
    })

df_table = pd.DataFrame(table_data).sort_values("Ratio", ascending=False)

# Top 4 Cards
st.subheader("🔥 Top Coins by Volume Ratio")
cols = st.columns(min(len(data), 4))
for idx, (symbol, d) in enumerate(data.items()):
    if idx >= 4:
        break
    with cols[idx]:
        ratio = d["volume_ratio"]
        border = "#00ff88" if ratio > 2 else "#ff3b5c" if ratio < 0.5 else "#ffaa00"
        label = "🚀 HIGH" if ratio > 2 else "🔽 LOW" if ratio < 0.5 else "➡️ NORMAL"
        st.markdown(f"""
        <div style="background:rgba(17,24,39,0.8); border:1px solid {border}; border-radius:12px; padding:15px; margin:5px;">
            <h3 style="margin:0; color:#f1f5f9;">{symbol}</h3>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#94a3b8;">Volume</span>
                <span style="color:#f1f5f9; font-weight:700;">{format_volume(d['last_volume'])}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#94a3b8;">Ratio</span>
                <span style="color:{border}; font-weight:700;">{d['volume_ratio']:.2f}x</span>
            </div>
            <div style="margin-top:8px; text-align:center; color:{border}; font-weight:600;">{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.dataframe(df_table, use_container_width=True, hide_index=True)

# =========================================================
# CHART DENGAN LIQUIDITY ZONES
# =========================================================
st.divider()
st.subheader("📈 Volume Chart with Liquidity Zones")

selected_coin = st.selectbox("Select Coin", st.session_state.watchlist, key="liquidity_chart")

if selected_coin in data:
    d = data[selected_coin]
    df = d["df"]
    if df is not None and not df.empty:
        # Deteksi zona likuiditas
        with st.spinner("🔍 Mendeteksi Liquidity Zones..."):
            buy_zones, sell_zones = detect_liquidity_zones(df, length=7, margin=2.3)
        
        # Tampilkan jumlah zona
        col1, col2 = st.columns(2)
        col1.metric("🟢 Buyside Zones", len(buy_zones))
        col2.metric("🔴 Sellside Zones", len(sell_zones))
        
        # Buat chart
        df_chart = df.tail(168)
        
        fig = make_subplots(
            rows=3, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.05,
            row_heights=[0.5, 0.3, 0.2],
            subplot_titles=(
                f"{selected_coin} - Price & Liquidity Zones",
                "Volume per Hour",
                "Volume Ratio"
            )
        )
        
        # Row 1: Price + Liquidity Zones
        fig.add_trace(go.Candlestick(
            x=df_chart["Time"],
            open=df_chart["Open"],
            high=df_chart["High"],
            low=df_chart["Low"],
            close=df_chart["Close"],
            name="Price",
            increasing_line_color="#00ff88",
            decreasing_line_color="#ff3b5c"
        ), row=1, col=1)
        
        # Tambahkan zona likuiditas ke chart
        fig = add_liquidity_zones_to_fig(fig, df_chart, buy_zones, sell_zones)
        
        # Row 2: Volume
        avg_volume = d["avg_volume"]
        colors = ["#00ff88" if v > avg_volume * 2 else "#ff3b5c" if v < avg_volume * 0.5 else "#ffaa00" 
                  for v in df_chart["Volume"]]
        
        fig.add_trace(go.Bar(
            x=df_chart["Time"], 
            y=df_chart["Volume"], 
            marker_color=colors, 
            name="Volume"
        ), row=2, col=1)
        fig.add_hline(
            y=avg_volume, 
            line_dash="dash", 
            line_color="#ffaa00", 
            annotation_text="Avg Volume", 
            row=2, col=1
        )
        
        # Row 3: Volume Ratio
        volume_ratio = df_chart["Volume"] / avg_volume
        ratio_colors = ["#00ff88" if r > 2 else "#ff3b5c" if r < 0.5 else "#ffaa00" for r in volume_ratio]
        
        fig.add_trace(go.Bar(
            x=df_chart["Time"],
            y=volume_ratio,
            marker_color=ratio_colors,
            name="Volume Ratio"
        ), row=3, col=1)
        fig.add_hline(y=2, line_dash="dash", line_color="#00ff88", annotation_text="High (2x)", row=3, col=1)
        fig.add_hline(y=0.5, line_dash="dash", line_color="#ff3b5c", annotation_text="Low (0.5x)", row=3, col=1)
        
        # Layout
        fig.update_layout(
            template="plotly_dark",
            height=800,
            showlegend=False,
            plot_bgcolor="#0a0a1a",
            paper_bgcolor="#0a0a1a",
            font=dict(color="#94a3b8")
        )
        fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Statistik
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Last Volume", format_volume(d["last_volume"]))
        col2.metric("Avg 24h", format_volume(d["avg_volume"]))
        col3.metric("Max 24h", format_volume(d["max_volume"]))
        col4.metric("Ratio", f"{d['volume_ratio']:.2f}x")
        col5.metric("Price", f"${d['last_price']:.2f}")
        
        # Tampilkan zona dalam tabel
        if buy_zones or sell_zones:
            with st.expander("📋 Detail Liquidity Zones"):
                if buy_zones:
                    st.write("🟢 **Buyside Liquidity Zones**")
                    df_buy = pd.DataFrame(buy_zones)
                    st.dataframe(df_buy[['price', 'high', 'low']], use_container_width=True)
                
                if sell_zones:
                    st.write("🔴 **Sellside Liquidity Zones**")
                    df_sell = pd.DataFrame(sell_zones)
                    st.dataframe(df_sell[['price', 'high', 'low']], use_container_width=True)
    else:
        st.warning("Data tidak tersedia")
else:
    st.warning(f"Data untuk {selected_coin} tidak ditemukan")
# =========================================================
# ALERT HISTORY
# =========================================================
with st.expander("📜 Alert History"):
    history = get_volume_alerts(limit=50)
    if history:
        df_history = pd.DataFrame(history)
        if 'id' in df_history.columns:
            df_history = df_history.drop('id', axis=1)
        st.dataframe(df_history, use_container_width=True, hide_index=True)
        csv = df_history.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", csv, f"alerts_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")
    else:
        st.info("Belum ada alert")

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"🔄 Updated: {st.session_state.last_update.strftime('%H:%M:%S')} | {len(data)} coins | Threshold: {volume_threshold}x")
