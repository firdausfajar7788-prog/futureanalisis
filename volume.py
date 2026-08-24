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
# SESSION STATE
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "MATIC", "LINK"]
if "last_update" not in st.session_state:
    st.session_state.last_update = datetime.now()
if "volume_alerts" not in st.session_state:
    st.session_state.volume_alerts = {}

# =========================================================
# HEADER
# =========================================================
st.title("📊 Volume Monitor - Crypto")
st.caption("Monitoring volume per jam | Deteksi lonjakan volume | Real-time dari Yahoo Finance")
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
                    st.session_state.watchlist.append(coin)
                    st.rerun()
                else:
                    st.warning(f"⚠️ {coin} already exists!")
    
    st.markdown("**Your Coins:**")
    cols = st.columns(3)
    for idx, coin in enumerate(st.session_state.watchlist):
        col_idx = idx % 3
        with cols[col_idx]:
            if st.button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
                st.session_state.watchlist.remove(coin)
                st.rerun()
    
    st.divider()
    
    st.subheader("📊 Settings")
    refresh = st.slider("🔄 Refresh (detik)", 10, 120, 30)
    volume_threshold = st.slider("🚨 Alert Threshold (x avg)", 1.5, 5.0, 2.5, 0.5)
    
    st.divider()
    st.subheader("📱 Telegram Alert")
    bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
    
    if st.button("🚀 Test Telegram", use_container_width=True):
        if bot_token and chat_id:
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
            st.warning("⚠️ Isi Bot Token dan Chat ID di secrets")
    
    st.divider()
    st.caption("📊 **Volume Level:**")
    st.caption("🟢 High (> 2x avg)")
    st.caption("🟡 Normal (0.5x - 2x avg)")
    st.caption("🔴 Low (< 0.5x avg)")

# =========================================================
# FUNGSI AMBIL DATA
# =========================================================
@st.cache_data(ttl=30, show_spinner=False)
def get_volume_data(symbol, period="7d", interval="1h"):
    """Ambil data volume per jam"""
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
        
        # Tambahkan kolom volume
        df["Volume"] = df["Volume"].fillna(0)
        
        return df
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

@st.cache_data(ttl=30, show_springer=False)
def get_all_volume_data(symbols, interval="1h", hours=24):
    """Ambil data volume untuk semua simbol"""
    results = {}
    for symbol in symbols:
        df = get_volume_data(symbol, period="7d", interval=interval)
        if df is not None and not df.empty:
            # Ambil 24 jam terakhir
            df_24h = df.tail(hours)
            if len(df_24h) >= 12:  # Minimal 12 jam data
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
# FUNGSI TELEGRAM ALERT
# =========================================================
def send_telegram_alert(symbol, volume_ratio, volume, avg_volume, price):
    """Kirim alert ke Telegram"""
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            return False
        
        msg = f"""🚨 <b>VOLUME SPIKE DETECTED!</b>

<b>Coin:</b> {symbol}
<b>Current Volume:</b> {volume:,.0f}
<b>Avg Volume (24h):</b> {avg_volume:,.0f}
<b>Ratio:</b> {volume_ratio:.2f}x
<b>Price:</b> ${price:.4f}
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
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

# Ambil data
with st.spinner("📊 Mengambil data volume..."):
    data = get_all_volume_data(st.session_state.watchlist, interval="1h", hours=24)

if not data:
    st.warning("⚠️ Tidak ada data yang bisa ditampilkan")
    st.stop()

# Update waktu
st.session_state.last_update = datetime.now()

# =========================================================
# METRICS
# =========================================================
total_volume = sum([d["last_volume"] for d in data.values()])
high_volume = len([d for d in data.values() if d["volume_ratio"] > 2])
low_volume = len([d for d in data.values() if d["volume_ratio"] < 0.5])

c1, c2, c3, c4 = st.columns(4)
c1.metric("🪙 Coins", len(data))
c2.metric("📊 Total 1H Volume", format_volume(total_volume))
c3.metric("🟢 High Volume (>2x)", high_volume)
c4.metric("🔴 Low Volume (<0.5x)", low_volume)

# =========================================================
# VOLUME ALERTS
# =========================================================
alerts = []
for symbol, d in data.items():
    if d["volume_ratio"] > volume_threshold:
        alerts.append({
            "Coin": symbol,
            "Volume Ratio": f"{d['volume_ratio']:.2f}x",
            "Current Volume": format_volume(d["last_volume"]),
            "Avg Volume (24h)": format_volume(d["avg_volume"]),
            "Price": f"${d['last_price']:.4f}",
            "24h Change": f"{d['price_change']:.2f}%"
        })
        
        # Kirim Telegram jika belum dikirim dalam 30 menit
        if symbol not in st.session_state.volume_alerts or \
           (datetime.now() - st.session_state.volume_alerts[symbol]).seconds > 1800:
            if send_telegram_alert(symbol, d["volume_ratio"], d["last_volume"], d["avg_volume"], d["last_price"]):
                st.session_state.volume_alerts[symbol] = datetime.now()

# =========================================================
# ALERT SECTION
# =========================================================
if alerts:
    st.subheader("🚨 Volume Spikes Detected!")
    st.caption(f"Threshold: {volume_threshold}x above average")
    df_alerts = pd.DataFrame(alerts)
    st.dataframe(df_alerts, use_container_width=True, hide_index=True)
else:
    st.info("✅ Tidak ada lonjakan volume yang terdeteksi")

# =========================================================
# VOLUME TABLE
# =========================================================
st.subheader("📊 Volume per Coin (Last 24 Hours)")

table_data = []
for symbol, d in data.items():
    # Tentukan status
    if d["volume_ratio"] > 2:
        status = "🟢 HIGH"
        status_class = "volume-spike"
    elif d["volume_ratio"] < 0.5:
        status = "🔴 LOW"
        status_class = "volume-low"
    else:
        status = "🟡 NORMAL"
        status_class = "volume-normal"
    
    table_data.append({
        "Coin": symbol,
        "Last Volume": format_volume(d["last_volume"]),
        "Avg Volume (24h)": format_volume(d["avg_volume"]),
        "Ratio": f"{d['volume_ratio']:.2f}x",
        "Price": f"${d['last_price']:.4f}",
        "24h Change": f"{d['price_change']:.2f}%",
        "Status": status
    })

df_table = pd.DataFrame(table_data)
df_table = df_table.sort_values("Ratio", ascending=False)

# Tampilkan sebagai metric cards
cols = st.columns(min(len(data), 4))
for idx, (symbol, d) in enumerate(data.items()):
    if idx >= 4:
        break
    col_idx = idx % len(cols)
    with cols[col_idx]:
        ratio = d["volume_ratio"]
        if ratio > 2:
            bg = "rgba(0,255,136,0.1)"
            border = "#00ff88"
            label = "🚀 HIGH"
        elif ratio < 0.5:
            bg = "rgba(255,59,92,0.1)"
            border = "#ff3b5c"
            label = "🔽 LOW"
        else:
            bg = "rgba(255,170,0,0.1)"
            border = "#ffaa00"
            label = "➡️ NORMAL"
        
        st.markdown(f"""
        <div style="background:{bg}; border:1px solid {border}; border-radius:12px; padding:15px; margin:5px;">
            <h3 style="margin:0; color:#f1f5f9;">{symbol}</h3>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#94a3b8;">Volume</span>
                <span style="color:#f1f5f9; font-weight:700;">{format_volume(d['last_volume'])}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#94a3b8;">Avg 24h</span>
                <span style="color:#f1f5f9;">{format_volume(d['avg_volume'])}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#94a3b8;">Ratio</span>
                <span style="color:{border}; font-weight:700;">{d['volume_ratio']:.2f}x</span>
            </div>
            <div style="margin-top:8px; text-align:center; color:{border}; font-weight:600;">
                {label}
            </div>
        </div>
        """, unsafe_allow_html=True)

# =========================================================
# FULL TABLE
# =========================================================
st.dataframe(df_table, use_container_width=True, hide_index=True)

# =========================================================
# CHART - Volume & Price
# =========================================================
st.divider()
st.subheader("📈 Volume Chart (Selected Coin)")

selected_coin = st.selectbox("Select Coin for Chart", st.session_state.watchlist)

if selected_coin in data:
    d = data[selected_coin]
    df = d["df"]
    
    if df is not None and not df.empty:
        # Filter 7 hari terakhir
        df_chart = df.tail(168)  # 7 hari x 24 jam
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.4],
            subplot_titles=(f"{selected_coin} - Price", "Volume per Hour")
        )
        
        # Price chart
        fig.add_trace(go.Scatter(
            x=df_chart["Time"],
            y=df_chart["Close"],
            line=dict(color="#00a2ff", width=2),
            name="Price"
        ), row=1, col=1)
        
        # Volume chart dengan warna berbeda
        avg_volume = d["avg_volume"]
        colors = []
        for vol in df_chart["Volume"]:
            if vol > avg_volume * 2:
                colors.append("#00ff88")  # High
            elif vol < avg_volume * 0.5:
                colors.append("#ff3b5c")  # Low
            else:
                colors.append("#ffaa00")  # Normal
        
        fig.add_trace(go.Bar(
            x=df_chart["Time"],
            y=df_chart["Volume"],
            marker_color=colors,
            name="Volume"
        ), row=2, col=1)
        
        # Garis rata-rata volume
        fig.add_hline(
            y=avg_volume,
            line_dash="dash",
            line_color="#ffaa00",
            annotation_text="Avg Volume",
            row=2, col=1
        )
        
        fig.update_layout(
            template="plotly_dark",
            height=600,
            showlegend=False,
            plot_bgcolor="#0a0a1a",
            paper_bgcolor="#0a0a1a",
            font=dict(color="#94a3b8")
        )
        fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Tampilkan statistik
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Last Volume", format_volume(d["last_volume"]))
        col2.metric("Avg Volume (24h)", format_volume(d["avg_volume"]))
        col3.metric("Max Volume (24h)", format_volume(d["max_volume"]))
        col4.metric("Volume Ratio", f"{d['volume_ratio']:.2f}x")
    else:
        st.warning("Data tidak tersedia")
else:
    st.warning(f"Data untuk {selected_coin} tidak ditemukan")

# =========================================================
# VOLUME HISTORY (per jam)
# =========================================================
with st.expander("📊 Volume History (Last 24 Hours)"):
    history_data = []
    for symbol, d in data.items():
        df_24h = d["df_24h"]
        if df_24h is not None and not df_24h.empty:
            for _, row in df_24h.iterrows():
                history_data.append({
                    "Time": row["Time"],
                    "Coin": symbol,
                    "Volume": row["Volume"],
                    "Price": row["Close"]
                })
    
    if history_data:
        df_history = pd.DataFrame(history_data)
        df_history = df_history.sort_values("Time", ascending=False)
        st.dataframe(df_history.head(100), use_container_width=True, hide_index=True)
        
        # Download CSV
        csv = df_history.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download CSV",
            csv,
            f"volume_history_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv"
        )

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(
    f"🔄 Last updated: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')} | "
    f"Total Coins: {len(data)} | "
    f"Data Source: Yahoo Finance | "
    f"Auto Refresh: {refresh}s"
)
