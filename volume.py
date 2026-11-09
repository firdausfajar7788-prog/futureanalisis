"""
Volume Monitor v2
- Data OHLCV + quote volume + taker-buy dari Binance (fallback yfinance), cache thread-safe, fetch paralel
- Rasio volume dihitung dari candle 1H yang SUDAH CLOSE terhadap MEDIAN baseline (bukan mean, tanpa candle yang diukur)
- Opsi baseline "jam yang sama" (hindari bias sesi Asia/Eropa/AS) + filter volume minimum (USD)
- Arah PUMP/DUMP dari return candle + buy pressure (taker buy) bila tersedia
- Zona likuiditas: cluster nilai terurut, toleransi ketat (x ATR), zona yang sudah tersapu dibuang
- Alert: dedupe atomik per (coin, candle) via unique index di Supabase, insert dulu baru kirim Telegram
"""
import os
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from supabase import create_client

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("volmon")

st.set_page_config(page_title="📊 Volume Monitor - Crypto", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp { background:#0a0a1a; }
[data-testid="stMetric"] { background:linear-gradient(145deg,#111827,#0b1220); border:1px solid #1e293b;
  border-radius:16px; padding:16px; box-shadow:0 4px 20px rgba(0,255,255,.05); }
.stButton > button { background:linear-gradient(145deg,#00ff88,#00cc66); color:#000; font-weight:700;
  border:none; border-radius:10px; transition:all .3s ease; }
.stButton > button:hover { transform:scale(1.03); box-shadow:0 0 30px rgba(0,255,255,.3); }
</style>
""", unsafe_allow_html=True)

BINANCE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com", "https://api.binance.us"]
DIR_LABEL = {"PUMP": "🟢 PUMP", "DUMP": "🔴 DUMP", "NETRAL": "⚪ NETRAL"}
BASELINE_MODES = ["Median N jam terakhir", "Median jam yang sama (7 hari)"]


# =========================================================
# HELPER
# =========================================================
def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_secret(name, default=""):
    v = os.getenv(name)
    if v:
        return v.strip()
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nz(x):
    """NaN/inf -> None agar aman untuk JSON/Supabase."""
    try:
        return None if x is None or not np.isfinite(float(x)) else float(x)
    except Exception:
        return None


def format_usd(v):
    if v is None or pd.isna(v):
        return "-"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"${v / div:.2f}{suf}"
    return f"${v:,.0f}"


def fmt_price(v):
    if v is None or pd.isna(v):
        return "-"
    if v >= 1000: return f"${v:,.2f}"
    if v >= 100: return f"${v:,.3f}"
    if v >= 1: return f"${v:,.4f}"
    if v >= 0.01: return f"${v:,.6f}"
    return f"${v:,.8f}"


_CACHE, _LOCK = {}, threading.Lock()


def cached(key, ttl, fn):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _LOCK:
        if len(_CACHE) > 300:
            _CACHE.clear()
        _CACHE[key] = (now, val)
    return val


# =========================================================
# SUPABASE (opsional)
# =========================================================
@st.cache_resource
def get_supabase():
    url, key = get_secret("SUPABASE_URL"), get_secret("SUPABASE_KEY")
    if not url or not key:
        try:
            url, key = st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
        except Exception:
            return None
    try:
        return create_client(url, key)
    except Exception as e:
        log.error("Supabase init: %s", e)
        return None


DEFAULT_WATCHLIST = ["BTC", "ETH", "BNB", "SOL", "XRP"]


def get_watchlist():
    sb = get_supabase()
    if sb is None:
        return DEFAULT_WATCHLIST.copy()
    try:
        res = sb.table("watchlist").select("symbol").order("added_at").execute()
        return [r["symbol"] for r in res.data] if res.data else DEFAULT_WATCHLIST.copy()
    except Exception as e:
        log.warning("get_watchlist: %s", e)
        return DEFAULT_WATCHLIST.copy()


def add_coin(symbol):
    sb = get_supabase()
    if sb is None:
        return True
    try:
        sb.table("watchlist").insert({"symbol": symbol}).execute()
        return True
    except Exception as e:
        log.warning("add_coin: %s", e)
        return False


def remove_coin(symbol):
    sb = get_supabase()
    if sb is None:
        return True
    try:
        sb.table("watchlist").delete().eq("symbol", symbol).execute()
        return True
    except Exception as e:
        log.warning("remove_coin: %s", e)
        return False


def insert_alert(row):
    """Return (status, id). status: ok | dup | error | nodb. Unique index (symbol, candle_time) menjamin dedupe atomik."""
    sb = get_supabase()
    if sb is None:
        return "nodb", None
    try:
        res = sb.table("volume_alerts").insert(row).execute()
        return "ok", (res.data[0].get("id") if res.data else None)
    except Exception as e:
        msg = str(e)
        if "23505" in msg or "duplicate" in msg.lower():
            return "dup", None
        log.warning("insert_alert: %s", e)
        return "error", None


def delete_alert(alert_id):
    sb = get_supabase()
    if sb is None or alert_id is None:
        return
    try:
        sb.table("volume_alerts").delete().eq("id", alert_id).execute()
    except Exception as e:
        log.warning("delete_alert: %s", e)


def recent_alert_exists(symbol, minutes):
    sb = get_supabase()
    if sb is None:
        return False
    try:
        cutoff = (utcnow() - timedelta(minutes=minutes)).isoformat()
        res = (sb.table("volume_alerts").select("id").eq("symbol", symbol)
               .gte("timestamp", cutoff).limit(1).execute())
        return len(res.data) > 0
    except Exception as e:
        log.warning("recent_alert_exists: %s", e)
        return False


def get_volume_alerts(limit=100):
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("volume_alerts").select("*").order("timestamp", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        log.warning("get_volume_alerts: %s", e)
        return []


def get_alert_stats():
    """Statistik dihitung langsung dari tabel (bukan counter baca-ubah-tulis)."""
    def _load():
        d = {"total": 0, "today": 0, "avg_ratio": 0.0}
        sb = get_supabase()
        if sb is None:
            return d
        try:
            d["total"] = sb.table("volume_alerts").select("id", count="exact").limit(1).execute().count or 0
            today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            d["today"] = (sb.table("volume_alerts").select("id", count="exact")
                          .gte("timestamp", today).limit(1).execute().count or 0)
            rows = (sb.table("volume_alerts").select("ratio").order("timestamp", desc=True)
                    .limit(200).execute().data or [])
            vals = [r["ratio"] for r in rows if r.get("ratio") is not None]
            d["avg_ratio"] = float(np.mean(vals)) if vals else 0.0
        except Exception as e:
            log.warning("get_alert_stats: %s", e)
        return d
    return cached(("stats",), 30, _load)


# =========================================================
# TELEGRAM
# =========================================================
def send_telegram(text):
    token, chat = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi"
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=10)
        if r.status_code == 200:
            return True, ""
        try:
            return False, r.json().get("description", f"HTTP {r.status_code}")
        except Exception:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def telegram_configured():
    return bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))


def format_alert(sym, r, p):
    t = f"🚨 <b>VOLUME SPIKE</b> — <b>{esc(sym)}</b>\n"
    t += f"{DIR_LABEL[r['direction']]} ({r['ret']:+.2f}% candle 1H)\n\n"
    t += f"Volume: <b>{format_usd(r['vol_usd'])}</b> vs baseline {format_usd(r['baseline'])}\n"
    t += f"Ratio: <b>{r['ratio']:.2f}x</b>\n"
    if r["taker"] is not None and not pd.isna(r["taker"]):
        t += f"Buy pressure: {r['taker']:.0f}%\n"
    t += f"Harga: {fmt_price(r['price'])}\nPerubahan {p['lookback']}j: {r['change']:+.2f}%\n\n"
    t += f"🕐 candle {r['candle_time']:%Y-%m-%d %H:%M} UTC\n"
    t += "<i>Lonjakan volume bukan sinyal entry; cek chart dulu.</i>"
    return t


# =========================================================
# DATA
# =========================================================
def fetch_binance(symbol, limit=500):
    params = {"symbol": f"{symbol}USDT", "interval": "1h", "limit": limit}
    for host in BINANCE_HOSTS:
        try:
            r = requests.get(f"{host}/api/v3/klines", params=params, timeout=8)
            if r.status_code != 200:
                continue
            raw = r.json()
            if not raw:
                continue
            df = pd.DataFrame(raw, columns=["t", "Open", "High", "Low", "Close", "Vol", "ct",
                                            "VolUSD", "n", "tb", "TakerBuyUSD", "ig"])
            df["Time"] = pd.to_datetime(df["t"], unit="ms")
            for c in ["Open", "High", "Low", "Close", "VolUSD", "TakerBuyUSD"]:
                df[c] = df[c].astype(float)
            return df[["Time", "Open", "High", "Low", "Close", "VolUSD", "TakerBuyUSD"]]
        except Exception as e:
            log.warning("binance %s %s: %s", host, symbol, e)
    return None


def fetch_yf(symbol):
    try:
        df = yf.download(f"{symbol}-USD", interval="1h", period="30d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df = df.rename(columns={df.columns[0]: "Time"})
        t = pd.to_datetime(df["Time"])
        if t.dt.tz is not None:
            t = t.dt.tz_convert("UTC").dt.tz_localize(None)
        df["Time"] = t
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        df["VolUSD"] = df["Volume"] * df["Close"]
        df["TakerBuyUSD"] = np.nan
        return df[["Time", "Open", "High", "Low", "Close", "VolUSD", "TakerBuyUSD"]].reset_index(drop=True)
    except Exception as e:
        log.warning("yfinance %s: %s", symbol, e)
        return None


def get_data(symbol):
    def _load():
        df = fetch_binance(symbol)
        if df is None:
            df = fetch_yf(symbol)
        if df is None or len(df) < 40 or df["Close"].iloc[-1] <= 0:
            return None
        return df.reset_index(drop=True)
    return cached(("d", symbol), 30, _load)


def load_all(symbols):
    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(zip(symbols, ex.map(get_data, symbols)))


# =========================================================
# ANALISIS VOLUME
# =========================================================
def baseline_series(df, lookback, mode):
    """Median volume USD sebelum candle ini (candle yang diukur tidak ikut)."""
    v = df["VolUSD"]
    if mode == BASELINE_MODES[1]:
        return v.groupby(df["Time"].dt.hour).transform(
            lambda s: s.shift(1).rolling(7, min_periods=3).median())
    return v.shift(1).rolling(lookback, min_periods=max(6, lookback // 2)).median()


def analyze_volume(df, p):
    if df is None or len(df) < 40:
        return None
    now = utcnow()
    running = df["Time"].iloc[-1] + timedelta(hours=1) > now
    i = len(df) - 2 if running else len(df) - 1

    base = baseline_series(df, p["lookback"], p["mode"])
    ratio_s = df["VolUSD"] / base.replace(0, np.nan)
    ratio = ratio_s.iloc[i]
    if pd.isna(ratio):
        return None

    row = df.iloc[i]
    ret = (row["Close"] / row["Open"] - 1) * 100 if row["Open"] > 0 else 0.0
    taker = (row["TakerBuyUSD"] / row["VolUSD"] * 100
             if pd.notna(row["TakerBuyUSD"]) and row["VolUSD"] > 0 else None)

    live = None
    if running:
        elapsed = (now - df["Time"].iloc[-1]).total_seconds() / 3600
        b_live = base.iloc[-1]
        if elapsed >= 0.25 and pd.notna(b_live) and b_live > 0:
            live = float(df["VolUSD"].iloc[-1] / elapsed / b_live)  # proyeksi, tidak dipakai untuk alert

    price = float(df["Close"].iloc[-1])
    ref = float(df["Close"].iloc[max(0, len(df) - 1 - p["lookback"])])
    change = (price / ref - 1) * 100 if ref > 0 else 0.0

    direction = "PUMP" if ret >= p["move_thr"] else "DUMP" if ret <= -p["move_thr"] else "NETRAL"
    eligible = bool(ratio >= p["thr"] and row["VolUSD"] >= p["min_usd"])
    if eligible:
        status = "🚨 SPIKE"
    elif ratio >= 2:
        status = "🟢 HIGH"
    elif ratio < 0.5:
        status = "🔴 LOW"
    else:
        status = "🟡 NORMAL"

    return {
        "df": df, "base": base, "ratio_s": ratio_s, "running": bool(running),
        "ratio": float(ratio), "live": live, "vol_usd": float(row["VolUSD"]),
        "baseline": float(base.iloc[i]), "ret": float(ret), "taker": taker,
        "price": price, "change": float(change), "direction": direction,
        "dir_label": DIR_LABEL[direction], "eligible": eligible, "status": status,
        "candle_time": row["Time"].to_pydatetime(),
    }


# =========================================================
# LIQUIDITY ZONES
# =========================================================
def atr_last(d, period=14):
    pc = d["Close"].shift()
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().iloc[-1]
    return float(a) if pd.notna(a) and a > 0 else float(d["Close"].iloc[-1]) * 0.01


def detect_zones(df, length=5, margin=0.3, min_touches=2, show_swept=False):
    """
    Cluster pivot high (buy-side / equal highs) dan pivot low (sell-side / equal lows).
    Pivot hanya yang sudah terkonfirmasi (`length` candle terakhir tidak dihitung).
    Zona yang sudah tersapu (harga menembus setelah sentuhan terakhir) dibuang kecuali show_swept.
    """
    if df is None or len(df) < 2 * length + 30:
        return [], []
    d = df.reset_index(drop=True)
    w = 2 * length + 1
    ph = d["High"] == d["High"].rolling(w, center=True).max()
    pl = d["Low"] == d["Low"].rolling(w, center=True).min()
    atr = atr_last(d)
    tol, pad = atr * margin, atr * 0.1
    price = float(d["Close"].iloc[-1])

    def build(idxs, vals, side):
        if not idxs:
            return []
        pts = sorted(zip(vals, idxs))
        groups, cur = [], [pts[0]]
        for pt in pts[1:]:
            if pt[0] - cur[0][0] <= tol:
                cur.append(pt)
            else:
                groups.append(cur); cur = [pt]
        groups.append(cur)
        zones = []
        for g in groups:
            if len(g) < min_touches:
                continue
            gv, gi = [x[0] for x in g], [x[1] for x in g]
            z_low, z_high = min(gv) - pad, max(gv) + pad
            last = max(gi)
            after = d.iloc[last + 1:]
            swept = bool((after["High"] > z_high).any()) if side == "buy" else bool((after["Low"] < z_low).any())
            if swept and not show_swept:
                continue
            zones.append({"side": side, "price": float(np.mean(gv)), "low": float(z_low), "high": float(z_high),
                          "touches": len(g), "swept": swept, "first_time": d["Time"].iloc[min(gi)]})
        return zones

    buy = build(d.index[ph].tolist(), d.loc[ph, "High"].tolist(), "buy")
    sell = build(d.index[pl].tolist(), d.loc[pl, "Low"].tolist(), "sell")
    buy.sort(key=lambda z: abs(z["price"] - price))
    sell.sort(key=lambda z: abs(z["price"] - price))
    return buy, sell


# =========================================================
# STATE
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()
if "alert_seen" not in st.session_state:
    st.session_state.alert_seen = set()

st.title("📊 Volume Monitor - Crypto")
st.caption("Volume 1H dari candle yang sudah close · baseline median · arah pump/dump · zona likuiditas · Supabase + Telegram")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    st.success("☁️ Supabase terhubung") if get_supabase() else st.warning("⚠️ Supabase tidak terhubung — tanpa database")

    st.subheader("📋 Watchlist")
    ca, cb = st.columns([3, 1])
    new_coin = ca.text_input("Add Coin", placeholder="BTC", label_visibility="collapsed")
    if cb.button("➕", use_container_width=True) and new_coin:
        coin = "".join(ch for ch in new_coin.upper() if ch.isalnum())
        if not coin:
            st.error("❌ Simbol tidak valid")
        elif coin in st.session_state.watchlist:
            st.warning(f"⚠️ {coin} sudah ada")
        elif get_data(coin) is None:
            st.error(f"❌ Data {coin} tidak ditemukan (Binance/Yahoo)")
        elif add_coin(coin):
            st.session_state.watchlist.append(coin)
            st.rerun()
        else:
            st.error("❌ Gagal menambah coin")
    cols = st.columns(3)
    for idx, coin in enumerate(list(st.session_state.watchlist)):
        if cols[idx % 3].button(f"✕ {coin}", key=f"del_{coin}", use_container_width=True):
            if remove_coin(coin):
                st.session_state.watchlist.remove(coin)
                st.rerun()
            else:
                st.error(f"❌ Gagal hapus {coin}")

    st.divider()
    st.subheader("📊 Deteksi Volume")
    refresh = st.slider("🔄 Refresh (detik)", 30, 300, 60, 10)
    thr = st.slider("🚨 Threshold alert (x baseline)", 1.5, 6.0, 2.5, 0.5)
    mode = st.selectbox("Baseline", BASELINE_MODES)
    lookback = st.slider("Lookback baseline (jam)", 12, 168, 48, 6,
                         help="Dipakai untuk mode 'Median N jam' dan untuk perubahan harga.")
    min_usd = st.number_input("Volume minimum candle (USD)", 0.0, 1e9, 50000.0, 10000.0,
                              help="Spike di bawah nilai ini diabaikan (hindari koin sepi).")
    move_thr = st.slider("Gerakan minimum pump/dump (%)", 0.1, 3.0, 0.5, 0.1)
    cooldown = st.slider("Cooldown per coin (menit, 0 = nonaktif)", 0, 240, 0, 15)

    st.divider()
    st.subheader("🎯 Liquidity Zones")
    z_len = st.slider("Pivot length", 3, 10, 5)
    z_margin = st.slider("Toleransi (x ATR)", 0.1, 1.0, 0.3, 0.05,
                         help="Dua pivot dianggap 'sejajar' jika selisihnya < toleransi × ATR.")
    z_touch = st.slider("Min sentuhan", 2, 5, 2)
    z_swept = st.checkbox("Tampilkan zona yang sudah tersapu", value=False)

    st.divider()
    st.subheader("📱 Telegram")
    send_tg = st.toggle("Kirim alert otomatis", value=True)
    if telegram_configured():
        st.success("✅ Telegram terkonfigurasi")
        if st.button("🚀 Test Telegram", use_container_width=True):
            ok, err = send_telegram("📊 <b>Volume Monitor</b> aktif ✅")
            st.success("✅ Terkirim") if ok else st.error(f"❌ {err}")
    else:
        st.warning("⚠️ Bot token / chat ID belum diisi")

    st.divider()
    st.subheader("📊 Statistik Alert")
    stt = get_alert_stats()
    st.metric("Total", stt["total"])
    st.metric("Hari ini (UTC)", stt["today"])
    st.metric("Rata-rata ratio", f"{stt['avg_ratio']:.2f}x")

P = {"lookback": lookback, "mode": mode, "thr": thr, "min_usd": min_usd, "move_thr": move_thr}

st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# LOAD & ANALISIS
# =========================================================
with st.spinner("📊 Mengambil data volume..."):
    raw = load_all(st.session_state.watchlist)

results, failed = {}, []
for sym, df_ in raw.items():
    r = analyze_volume(df_, P)
    if r is None:
        failed.append(sym)
    else:
        results[sym] = r

if failed:
    st.warning(f"⚠️ Data tidak tersedia / kurang untuk: {', '.join(failed)}")
if not results:
    st.error("Tidak ada data yang bisa ditampilkan.")
    st.stop()

now_utc = utcnow()
st.caption(f"🕐 Update: {now_utc:%Y-%m-%d %H:%M:%S} UTC · rasio dihitung dari candle 1H yang sudah close")

# =========================================================
# METRIK
# =========================================================
ratios = [r["ratio"] for r in results.values()]
m = st.columns(5)
m[0].metric("🪙 Coins", len(results))
m[1].metric("📊 Volume 1H (close)", format_usd(sum(r["vol_usd"] for r in results.values())))
m[2].metric("🟢 High (≥2x)", sum(1 for x in ratios if x >= 2))
m[3].metric("🔴 Low (<0.5x)", sum(1 for x in ratios if x < 0.5))
m[4].metric("📈 Median ratio", f"{float(np.median(ratios)):.2f}x")


# =========================================================
# ALERT (insert dulu -> kirim; dedupe atomik per candle)
# =========================================================
def process_alerts():
    sent = 0
    for sym, r in results.items():
        if not r["eligible"]:
            continue
        key = (sym, r["candle_time"].isoformat())
        if key in st.session_state.alert_seen:
            continue
        if cooldown > 0 and recent_alert_exists(sym, cooldown):
            st.session_state.alert_seen.add(key)
            continue
        row = {
            "timestamp": utcnow().isoformat(), "candle_time": r["candle_time"].isoformat(),
            "symbol": sym, "direction": r["direction"], "ratio": nz(r["ratio"]),
            "volume": nz(r["vol_usd"]), "avg_volume": nz(r["baseline"]), "price": nz(r["price"]),
            "price_change": nz(r["change"]), "move_pct": nz(r["ret"]),
            "buy_pressure": nz(r["taker"]), "threshold": float(thr),
        }
        status, aid = insert_alert(row)
        if status == "dup":
            st.session_state.alert_seen.add(key)
            continue
        st.session_state.alert_seen.add(key)
        if send_tg and telegram_configured():
            ok, err = send_telegram(format_alert(sym, r, P))
            if ok:
                sent += 1
            else:
                log.warning("telegram %s: %s", sym, err)
                if status == "ok":          # batalkan agar dicoba lagi di refresh berikutnya
                    delete_alert(aid)
                st.session_state.alert_seen.discard(key)
    return sent


n_sent = process_alerts()
if n_sent:
    st.toast(f"📱 {n_sent} alert terkirim")

# =========================================================
# TABEL
# =========================================================
rows = [{
    "Coin": s, "Arah": r["dir_label"], "Ratio": r["ratio"], "Live": r["live"],
    "Vol USD": r["vol_usd"], "Baseline": r["baseline"], "Move 1j": r["ret"],
    "Buy": r["taker"], "Harga": r["price"], "Perubahan": r["change"], "Status": r["status"],
} for s, r in results.items()]
df_t = pd.DataFrame(rows).sort_values("Ratio", ascending=False).reset_index(drop=True)

spikes = df_t[df_t["Status"] == "🚨 SPIKE"]
if not spikes.empty:
    st.subheader("🚨 Volume Spike")
    st.caption(f"Threshold {thr}x · volume minimum {format_usd(min_usd)} · baseline: {mode}")
    st.dataframe(spikes[["Coin", "Arah", "Ratio", "Vol USD", "Move 1j", "Buy"]].assign(
        **{"Vol USD": spikes["Vol USD"].map(format_usd)}),
        use_container_width=True, hide_index=True,
        column_config={"Ratio": st.column_config.NumberColumn(format="%.2fx"),
                       "Move 1j": st.column_config.NumberColumn(format="%+.2f%%"),
                       "Buy": st.column_config.NumberColumn("Buy pressure", format="%.0f%%")})
else:
    st.info("✅ Tidak ada lonjakan volume yang memenuhi syarat")

st.subheader("🔥 Top Coins by Volume Ratio")
top = df_t.head(4)
cc = st.columns(len(top))
for col, (_, r) in zip(cc, top.iterrows()):
    border = "#00ff88" if r["Ratio"] >= 2 else "#ff3b5c" if r["Ratio"] < 0.5 else "#ffaa00"
    col.markdown(f"""
    <div style="background:rgba(17,24,39,.8);border:1px solid {border};border-radius:12px;padding:15px;">
      <h3 style="margin:0;color:#f1f5f9;">{esc(r['Coin'])}</h3>
      <div style="color:#94a3b8;">Ratio <span style="color:{border};font-weight:700;float:right;">{r['Ratio']:.2f}x</span></div>
      <div style="color:#94a3b8;">Volume <span style="color:#f1f5f9;font-weight:700;float:right;">{format_usd(r['Vol USD'])}</span></div>
      <div style="color:#94a3b8;">Candle <span style="color:#f1f5f9;float:right;">{r['Move 1j']:+.2f}%</span></div>
      <div style="margin-top:8px;text-align:center;color:{border};font-weight:600;">{r['Arah']} · {r['Status']}</div>
    </div>""", unsafe_allow_html=True)

st.subheader("📊 Volume per Coin")
disp = df_t.copy()
for c_ in ("Vol USD", "Baseline"):
    disp[c_] = disp[c_].map(format_usd)
disp["Harga"] = disp["Harga"].map(fmt_price)
st.dataframe(disp, use_container_width=True, hide_index=True, column_config={
    "Ratio": st.column_config.NumberColumn("Ratio (close)", format="%.2fx"),
    "Live": st.column_config.NumberColumn("Live (proyeksi)", format="%.2fx",
                                          help="Proyeksi candle berjalan; hanya informasi, tidak dipakai untuk alert."),
    "Move 1j": st.column_config.NumberColumn("Move candle", format="%+.2f%%"),
    "Buy": st.column_config.NumberColumn("Buy pressure", format="%.0f%%"),
    "Perubahan": st.column_config.NumberColumn(f"Δ {lookback}j", format="%+.2f%%"),
})

# =========================================================
# CHART + ZONA
# =========================================================
st.divider()
st.subheader("📈 Volume Chart + Liquidity Zones")
sel = st.selectbox("Pilih coin", list(results.keys()), key="chart_coin")
r = results[sel]
df = r["df"]
buy_z, sell_z = detect_zones(df, z_len, z_margin, z_touch, z_swept)

zc = st.columns(4)
zc[0].metric("🟢 Buy-side aktif", sum(1 for z in buy_z if not z["swept"]))
zc[1].metric("🔴 Sell-side aktif", sum(1 for z in sell_z if not z["swept"]))
zc[2].metric("Ratio (close)", f"{r['ratio']:.2f}x")
zc[3].metric("Harga", fmt_price(r["price"]))
if r["running"]:
    st.caption("Candle terakhir masih berjalan; ditandai terang jika sudah melewati threshold berdasarkan ratio-nya.")

dfc = df.assign(ratio=r["ratio_s"], base=r["base"]).tail(168).reset_index(drop=True)
x0 = dfc["Time"].iloc[0]
x1 = dfc["Time"].iloc[-1]

fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.55, 0.25, 0.2],
                    subplot_titles=(f"{sel} — Harga & Liquidity Zones", "Volume 1H (USD)", "Volume Ratio"))
fig.add_trace(go.Candlestick(x=dfc["Time"], open=dfc["Open"], high=dfc["High"], low=dfc["Low"], close=dfc["Close"],
                             increasing_line_color="#00ff88", decreasing_line_color="#ff3b5c", name="Price"), 1, 1)

for z in buy_z + sell_z:
    col = "0,255,136" if z["side"] == "buy" else "255,59,92"
    alpha = 0.06 if z["swept"] else 0.16
    fig.add_shape(type="rect", xref="x", yref="y", x0=max(z["first_time"], x0), x1=x1, y0=z["low"], y1=z["high"],
                  fillcolor=f"rgba({col},{alpha})", line=dict(color=f"rgba({col},0.6)", width=1, dash="dash"))
    tag = "BSL" if z["side"] == "buy" else "SSL"
    fig.add_annotation(x=x1, y=z["price"], xref="x", yref="y", xanchor="right", yshift=8, showarrow=False,
                       text=f"{tag} {fmt_price(z['price'])} ×{z['touches']}{' (tersapu)' if z['swept'] else ''}",
                       font=dict(size=10, color=f"rgb({col})"))

up = (dfc["Close"] >= dfc["Open"]).to_numpy()
colors = np.where(up, "#00ff88", "#ff3b5c")
opac = np.where(dfc["ratio"].fillna(0) >= thr, 1.0, 0.35)
fig.add_trace(go.Bar(x=dfc["Time"], y=dfc["VolUSD"], marker=dict(color=colors, opacity=opac), name="Volume"), 2, 1)
fig.add_trace(go.Scatter(x=dfc["Time"], y=dfc["base"], mode="lines", line=dict(color="#ffaa00", width=1.5, dash="dash"),
                         name="Baseline (median)"), 2, 1)
fig.add_trace(go.Bar(x=dfc["Time"], y=dfc["ratio"], marker=dict(color=colors, opacity=opac), name="Ratio"), 3, 1)
fig.add_hline(y=thr, line_dash="dash", line_color="#00ff88", annotation_text=f"Threshold {thr}x", row=3, col=1)
fig.add_hline(y=1, line_dash="dot", line_color="#94a3b8", row=3, col=1)
fig.update_layout(template="plotly_dark", height=820, showlegend=False, xaxis_rangeslider_visible=False,
                  plot_bgcolor="#0a0a1a", paper_bgcolor="#0a0a1a", font=dict(color="#94a3b8"),
                  margin=dict(l=10, r=10, t=50, b=10))
fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
st.plotly_chart(fig, use_container_width=True)

if buy_z or sell_z:
    with st.expander("📋 Detail Liquidity Zones"):
        zr = []
        for z in sorted(buy_z + sell_z, key=lambda z: abs(z["price"] - r["price"])):
            zr.append({"Tipe": "🟢 Buy-side (equal highs)" if z["side"] == "buy" else "🔴 Sell-side (equal lows)",
                       "Harga": fmt_price(z["price"]), "Batas bawah": fmt_price(z["low"]),
                       "Batas atas": fmt_price(z["high"]), "Sentuhan": z["touches"],
                       "Jarak": f"{(z['price'] / r['price'] - 1) * 100:+.2f}%",
                       "Status": "Tersapu" if z["swept"] else "Aktif"})
        st.dataframe(pd.DataFrame(zr), use_container_width=True, hide_index=True)
else:
    st.info("ℹ️ Tidak ada zona likuiditas yang memenuhi kriteria (tidak ada zona palsu yang ditambahkan).")

# =========================================================
# HISTORY
# =========================================================
with st.expander("📜 Alert History"):
    hist = get_volume_alerts(100)
    if hist:
        dfh = pd.DataFrame(hist).drop(columns=["id"], errors="ignore")
        st.dataframe(dfh, use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", dfh.to_csv(index=False).encode("utf-8"),
                           f"alerts_{utcnow():%Y%m%d_%H%M}.csv", "text/csv")
    else:
        st.info("Belum ada alert (atau database belum terhubung).")

st.divider()
st.caption(f"🔄 {len(results)} coin · threshold {thr}x · baseline: {mode} · sumber: Binance (fallback Yahoo) · "
           "⚠️ Volume spike bukan sinyal entry.")
