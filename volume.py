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
# CHART
# =========================================================
st.divider()
st.subheader("📈 Volume Chart")

selected_coin = st.selectbox("Select Coin", st.session_state.watchlist)

if selected_coin in data:
    d = data[selected_coin]
    df = d["df"]
    if df is not None and not df.empty:
        df_chart = df.tail(168)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            row_heights=[0.6, 0.4],
                            subplot_titles=(f"{selected_coin} - Price", "Volume per Hour"))
        
        fig.add_trace(go.Scatter(x=df_chart["Time"], y=df_chart["Close"],
                                 line=dict(color="#00a2ff", width=2), name="Price"), row=1, col=1)
        
        avg_volume = d["avg_volume"]
        colors = ["#00ff88" if v > avg_volume * 2 else "#ff3b5c" if v < avg_volume * 0.5 else "#ffaa00" 
                  for v in df_chart["Volume"]]
        
        fig.add_trace(go.Bar(x=df_chart["Time"], y=df_chart["Volume"], marker_color=colors, name="Volume"), row=2, col=1)
        fig.add_hline(y=avg_volume, line_dash="dash", line_color="#ffaa00", 
                      annotation_text="Avg Volume", row=2, col=1)
        
        fig.update_layout(template="plotly_dark", height=600, showlegend=False,
                          plot_bgcolor="#0a0a1a", paper_bgcolor="#0a0a1a")
        fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
        
        st.plotly_chart(fig, use_container_width=True)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Last Volume", format_volume(d["last_volume"]))
        col2.metric("Avg 24h", format_volume(d["avg_volume"]))
        col3.metric("Max 24h", format_volume(d["max_volume"]))
        col4.metric("Ratio", f"{d['volume_ratio']:.2f}x")

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
