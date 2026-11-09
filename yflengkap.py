"""
Crypto Signal Pro v2
- Data: Binance public API (4h native) + fallback yfinance
- Indikator: Wilder RSI, StochRSI aman, ATR, ADX, MACD, EMA
- Strategi: Dip (Fib) / Breakout / Liquidity Grab + filter tren TF lebih besar
- Backtest realistis: fill entry, urutan SL/TP per candle, fee+slippage, partial TP, expectancy, PF, drawdown
- Paper trading: sinyal disimpan ke Supabase & dilacak otomatis (WIN/LOSS) -> Performance nyata
- Telegram: cooldown persisten (DB), notifikasi hasil TP/SL
"""
import os
import re
import json
import time
import logging
import threading
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
log = logging.getLogger("csp")

st.set_page_config(page_title="🤖 Crypto Signal Pro", layout="wide", initial_sidebar_state="expanded")

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
.stApp { background:#0a0a1a; }
[data-testid="stMetric"] { background:linear-gradient(145deg,#111827,#0b1220); border:1px solid #1e293b;
  border-radius:16px; padding:16px; box-shadow:0 4px 20px rgba(0,255,255,.05); }
.sig { border-radius:12px; padding:12px 20px; font-weight:600; font-size:18px; }
.signal-buy { background:rgba(0,255,136,.12); border:1px solid #00ff88; color:#00ff88; }
.signal-sell { background:rgba(255,59,92,.12); border:1px solid #ff3b5c; color:#ff3b5c; }
.signal-hold { background:rgba(255,170,0,.12); border:1px solid #ffaa00; color:#ffaa00; }
.signal-take-profit { background:rgba(0,150,255,.12); border:1px solid #0096ff; color:#0096ff; }
.plan-card { background:linear-gradient(145deg,#0d1425,#070b14); border:1px solid #1e293b;
  border-radius:16px; padding:20px; margin-bottom:12px; }
.plan-header { font-size:22px; font-weight:800; color:#00ff88; margin-bottom:8px; }
.plan-confidence { display:inline-block; background:rgba(0,255,136,.1); border:1px solid #00ff88;
  border-radius:12px; padding:4px 12px; color:#00ff88; font-weight:700; font-size:14px; }
.level-box { background:linear-gradient(145deg,#111827,#0b1220); border:1px solid #1e293b;
  border-radius:12px; padding:14px; text-align:center; margin-bottom:8px; }
.level-label { color:#64748b; font-size:12px; text-transform:uppercase; letter-spacing:1px; }
.level-value { font-size:20px; font-weight:800; color:#f1f5f9; margin:6px 0; }
.level-pct { font-size:12px; font-weight:600; color:#94a3b8; }
.level-pct.pos { color:#00ff88; } .level-pct.neg { color:#ff3b5c; }
.reason-item { padding:5px 0; color:#cbd5e1; font-size:14px; }
.stButton > button { background:linear-gradient(145deg,#00ff88,#00cc66); color:#000; font-weight:700;
  border:none; border-radius:10px; transition:all .3s ease; }
.stButton > button:hover { transform:scale(1.03); box-shadow:0 0 30px rgba(0,255,255,.3); }
.setup-badge { display:inline-block; padding:6px 16px; border-radius:20px; font-weight:700; font-size:15px; }
.setup-dip { background:rgba(0,255,136,.15); color:#00ff88; border:1px solid #00ff88; }
.setup-breakout { background:rgba(0,200,255,.15); color:#00c8ff; border:1px solid #00c8ff; }
.setup-liq { background:rgba(168,85,247,.15); color:#a855f7; border:1px solid #a855f7; }
.setup-wait { background:rgba(251,191,36,.15); color:#fbbf24; border:1px solid #fbbf24; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# CONFIG
# =========================================================
DEFAULT_CFG = dict(
    min_conf=3,        # confidence minimum (1-5) untuk alert
    min_rr=1.5,        # RR minimum ke TP2
    max_sl_pct=8.0,    # jarak SL maksimum (%)
    min_vol=0.5,       # RVOL minimum
    use_htf=True,      # filter tren TF lebih besar
    fee_pct=0.2,       # fee + slippage round-trip (%)
    cooldown_min=30,   # cooldown alert per coin+setup (menit)
)
TIMEFRAMES = ["15m", "1h", "4h"]
HTF_OF = {"15m": "1h", "1h": "4h", "4h": None}
RESAMPLE_RULE = {"1h": "60min", "4h": "240min", "1d": "1D"}
HTF_RULE_FOR_BACKTEST = {"15m": "60min", "1h": "240min"}
SETUP_SHORT = {"BUY_THE_DIP": "🅰️ DIP", "BREAKOUT": "🅱️ BO", "LIQUIDITY_GRAB": "🅲 LIQ", "WAIT": "⏳ WAIT"}
VALID_SETUPS = ("BUY_THE_DIP", "BREAKOUT", "LIQUIDITY_GRAB")


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


# =========================================================
# SUPABASE (opsional — app tetap jalan tanpa DB)
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
        log.error("Supabase init error: %s", e)
        return None


def db_ok():
    return get_supabase() is not None


def get_watchlist():
    sb = get_supabase()
    if sb is None:
        return ["BTC", "ETH", "SOL"]
    try:
        res = sb.table("watchlist").select("symbol").order("added_at").execute()
        return [r["symbol"] for r in res.data] if res.data else ["BTC"]
    except Exception as e:
        log.warning("get_watchlist: %s", e)
        return ["BTC"]


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


def plan_to_row(plan, source="auto"):
    return {
        "timestamp": utcnow().isoformat(),
        "symbol": plan["symbol"], "timeframe": plan["timeframe"],
        "setup_type": plan["setup_type"], "signal": plan["setup_label"],
        "confidence": int(plan["confidence"]), "order_type": plan.get("order_type", "-"),
        "entry": float(plan["entry"]), "sl": float(plan["stop_loss"]),
        "tp1": float(plan["tp1"]), "tp2": float(plan["tp2"]), "tp3": float(plan["tp3"]),
        "rr": float(plan["rr"]),
        "reasons": json.dumps(plan["reasons"], ensure_ascii=False),
        "status": "OPEN", "source": source,
    }


def save_signal(row):
    sb = get_supabase()
    if sb is None:
        return False
    try:
        sb.table("signal_history").insert(row).execute()
        return True
    except Exception as e:
        log.warning("save_signal: %s", e)
        return False


def already_alerted(symbol, setup_type, minutes):
    """Cooldown persisten: cek session + database."""
    key = (symbol, setup_type)
    last = st.session_state.alert_times.get(key)
    if last and (utcnow() - last).total_seconds() < minutes * 60:
        return True
    sb = get_supabase()
    if sb is None:
        return False
    try:
        cutoff = (utcnow() - timedelta(minutes=minutes)).isoformat()
        res = (sb.table("signal_history").select("id").eq("symbol", symbol)
               .eq("setup_type", setup_type).gte("timestamp", cutoff).limit(1).execute())
        return len(res.data) > 0
    except Exception as e:
        log.warning("already_alerted: %s", e)
        return False


def get_active_signals():
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("signal_history").select("*").in_("status", ["OPEN", "FILLED"]).execute()
        return res.data or []
    except Exception as e:
        log.warning("get_active_signals: %s", e)
        return []


def update_signal(sig_id, fields):
    sb = get_supabase()
    if sb is None:
        return False
    try:
        sb.table("signal_history").update(fields).eq("id", sig_id).execute()
        return True
    except Exception as e:
        log.warning("update_signal: %s", e)
        return False


def get_signal_history(limit=300):
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("signal_history").select("*").order("timestamp", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        log.warning("get_signal_history: %s", e)
        return []


# =========================================================
# TELEGRAM
# =========================================================
def send_telegram(text):
    token, chat = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi"
    if len(text) > 4000:
        text = text[:3900] + "\n[...dipotong...]"
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=10)
        if r.status_code == 200:
            return True, ""
        try:
            return False, r.json().get("description", f"HTTP {r.status_code}")
        except Exception:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_price(v):
    if v is None or pd.isna(v):
        return "-"
    if v >= 1000: return f"$ {v:,.2f}"
    if v >= 100: return f"$ {v:,.3f}"
    if v >= 1: return f"$ {v:,.4f}"
    if v >= 0.01: return f"$ {v:,.6f}"
    return f"$ {v:,.8f}"


def format_plan_for_telegram(plan):
    e, sl = plan["entry"], plan["stop_loss"]
    pct = lambda x: (x / e - 1) * 100
    t = f"🎯 <b>AUTO TRADE PLAN</b>\n<b>{esc(plan['symbol'])}</b> · {esc(plan['timeframe'])}\n"
    t += f"{esc(plan['setup_label'])}\nConfidence: {'⭐' * plan['confidence']} ({plan['confidence']}/5)\n"
    t += f"Order: {esc(plan.get('order_type', '-'))}\n\n"
    st_ = plan["setup_type"]
    if st_ == "BUY_THE_DIP" and plan.get("fib"):
        f = plan["fib"]
        t += f"📐 <b>FIB</b> High {f['high']:.6f} · Low {f['low']:.6f}\n\n"
    elif st_ == "LIQUIDITY_GRAB":
        t += f"💧 SSL sweep: <b>{plan.get('liq_level') or 0:.6f}</b>\n\n"
    elif st_ == "BREAKOUT":
        t += f"🚀 Resistance: <b>{plan.get('breakout_level') or 0:.6f}</b>\n\n"
    t += "📊 <b>LEVEL</b>\n"
    t += f"🎯 Entry: <b>{e:.6f}</b>\n🛑 SL: <b>{sl:.6f}</b> ({pct(sl):+.2f}%)\n"
    t += f"🥇 TP1: <b>{plan['tp1']:.6f}</b> ({pct(plan['tp1']):+.2f}%)\n"
    t += f"🥈 TP2: <b>{plan['tp2']:.6f}</b> ({pct(plan['tp2']):+.2f}%)\n"
    t += f"🥉 TP3: <b>{plan['tp3']:.6f}</b> ({pct(plan['tp3']):+.2f}%)\n"
    t += f"📊 R:R 1 : {plan['rr']:.2f}\n\n"
    t += (f"💰 <b>SIZING</b>\nModal ${plan['account_balance']:.2f} · Risk {plan['risk_pct']:.1f}% "
          f"= ${plan['max_loss_usd']:.2f}\nPosisi <b>${plan['position_usd']:.2f}</b> · "
          f"Unit <b>{plan['units']:.6f}</b>\n\n")
    t += "🧠 <b>ALASAN</b>\n" + "\n".join(esc(r) for r in plan["reasons"][:6]) + "\n\n"
    t += "⚠️ <b>INVALIDASI</b>\n" + "\n".join(esc(i) for i in plan["invalidations"][:3]) + "\n\n"
    for alt in plan.get("alternatives", [])[:2]:
        t += f"• {esc(alt['name'])}: entry {alt['entry']:.6f} · SL {alt['sl']:.6f} · TP {alt['tp']:.6f}\n"
    t += f"\n🕐 {utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n<i>Bukan saran finansial.</i>"
    return t


# =========================================================
# DATA (Binance + fallback yfinance, cache thread-safe)
# =========================================================
_CACHE, _LOCK = {}, threading.Lock()
BINANCE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com", "https://api.binance.us"]


def _cached(key, ttl, fn):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _LOCK:
        if len(_CACHE) > 400:
            _CACHE.clear()
        _CACHE[key] = (now, val)
    return val


def resample_ohlc(df, rule):
    out = (df.set_index("Time").resample(rule)
           .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
           .dropna().reset_index())
    return out


def _fetch_binance(symbol, interval, limit):
    params = {"symbol": f"{symbol}USDT", "interval": interval, "limit": limit}
    for host in BINANCE_HOSTS:
        try:
            r = requests.get(f"{host}/api/v3/klines", params=params, timeout=8)
            if r.status_code != 200:
                continue
            raw = r.json()
            if not raw:
                continue
            df = pd.DataFrame(raw, columns=["t", "Open", "High", "Low", "Close", "Volume",
                                            "ct", "qv", "n", "tb", "tq", "ig"])
            df["Time"] = pd.to_datetime(df["t"], unit="ms")
            for c in ["Open", "High", "Low", "Close", "Volume"]:
                df[c] = df[c].astype(float)
            return df[["Time", "Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            log.warning("binance %s: %s", host, e)
    return None


def _fetch_yf(symbol, interval, limit):
    yf_int = {"15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"}.get(interval)
    period = {"15m": "30d", "1h": "90d", "4h": "180d", "1d": "1y"}.get(interval)
    if not yf_int:
        return None
    try:
        df = yf.download(f"{symbol}-USD", interval=yf_int, period=period, progress=False, auto_adjust=False)
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
        df = df[["Time", "Open", "High", "Low", "Close", "Volume"]].dropna()
        if interval == "4h":
            df = resample_ohlc(df, RESAMPLE_RULE["4h"])
        return df.tail(limit).reset_index(drop=True)
    except Exception as e:
        log.warning("yfinance %s: %s", symbol, e)
        return None


def get_data(symbol, interval, limit=500):
    def _load():
        df = _fetch_binance(symbol, interval, limit)
        if df is None:
            df = _fetch_yf(symbol, interval, limit)
        if df is None or df.empty or df["Close"].iloc[-1] <= 0:
            return None
        return df.reset_index(drop=True)
    return _cached(("d", symbol, interval, limit), 30, _load)


# =========================================================
# INDIKATOR
# =========================================================
def EMA(s, p):
    return s.ewm(span=p, adjust=False).mean()


def RSI(close, period=14):
    d = close.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rsi = 100 - 100 / (1 + ag / al.replace(0, np.nan))
    return rsi.where(al != 0, 100.0)


def MACD(close, fast=12, slow=26, sig=9):
    line = EMA(close, fast) - EMA(close, slow)
    signal = line.ewm(span=sig, adjust=False).mean()
    return line, signal, line - signal


def StochRSI(close, period=14, smooth_k=3, smooth_d=3):
    rsi = RSI(close, period)
    lo, hi = rsi.rolling(period).min(), rsi.rolling(period).max()
    st_ = ((rsi - lo) / (hi - lo).replace(0, np.nan) * 100).fillna(50)
    k = st_.rolling(smooth_k).mean()
    return k, k.rolling(smooth_d).mean(), rsi


def ATR(df, period=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def ADX(df, period=14):
    h, l = df["High"], df["Low"]
    up, dn = h.diff(), -l.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr = ATR(df, period)
    pdi = 100 * plus.ewm(alpha=1 / period, adjust=False).mean() / atr
    mdi = 100 * minus.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


# =========================================================
# LEVEL: pivot, liquidity, S/R, fibonacci
# =========================================================
def get_pivots(df, left=3, right=3):
    w = left + right + 1
    ph = (df["High"] == df["High"].rolling(w, center=True).max()).fillna(False)
    pl = (df["Low"] == df["Low"].rolling(w, center=True).min()).fillna(False)
    return ph, pl  # `right` candle terakhir otomatis False (belum terkonfirmasi)


def get_liquidity_zones(df, lookback=100, tol_pct=0.5, left=3, right=3):
    """Return (buy_side di atas harga, urut terdekat dulu), (sell_side di bawah harga, terdekat dulu)."""
    if df is None or len(df) < 30:
        return [], []
    recent = df.tail(lookback)
    ph, pl = get_pivots(recent, left, right)
    price = float(df["Close"].iloc[-1])
    tol = price * tol_pct / 100

    def cluster(levels):
        if not levels:
            return []
        levels, zones, cur = sorted(levels), [], []
        cur = [levels[0]]
        for v in levels[1:]:
            if v - cur[-1] <= tol:
                cur.append(v)
            else:
                zones.append(sum(cur) / len(cur)); cur = [v]
        zones.append(sum(cur) / len(cur))
        return zones

    buy_side = sorted(z for z in cluster(recent.loc[ph, "High"].tolist()) if z > price)
    sell_side = sorted((z for z in cluster(recent.loc[pl, "Low"].tolist()) if z < price), reverse=True)
    return buy_side, sell_side


def get_support_resistance(df):
    """S/R struktur lebih besar (pivot 5/5, 200 candle, toleransi 0.8%). Return (supports, resistances)."""
    res, sup = get_liquidity_zones(df, 200, 0.8, 5, 5)
    return sup, res


def get_fibonacci(df, lookback=100):
    """Arah ditentukan dari urutan swing: low lebih dulu -> uptrend (retracement dari high)."""
    if df is None or len(df) < 30:
        return None
    r = df.tail(lookback).reset_index(drop=True)
    hi_i, lo_i = int(r["High"].idxmax()), int(r["Low"].idxmin())
    hi, lo = float(r["High"].iloc[hi_i]), float(r["Low"].iloc[lo_i])
    diff = hi - lo
    if diff <= 0:
        return None
    trend = "up" if lo_i < hi_i else "down"
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = {x: hi - diff * x for x in ratios} if trend == "up" else {x: lo + diff * x for x in ratios}
    return {"trend": trend, "high": hi, "low": lo, "range": diff, "levels": levels}


# =========================================================
# ANALISIS MOMENTUM
# =========================================================
def analyze_macd_stoch(df, timeframe=""):
    if df is None or len(df) < 60:
        return None
    close = df["Close"]
    macd_l, macd_s, hist = MACD(close)
    k, d, rsi = StochRSI(close)
    ema20, ema50 = EMA(close, 20), EMA(close, 50)
    adx = ADX(df)

    price = float(close.iloc[-1])
    # RVOL pakai candle yang sudah close (candle terakhir masih berjalan)
    vol_ma = float(df["Volume"].iloc[-22:-2].mean())
    vol_ratio = float(df["Volume"].iloc[-2]) / vol_ma if vol_ma > 0 else 1.0

    g = lambda s, i=-1: float(s.iloc[i])
    dif, dea, h0, h1 = g(macd_l), g(macd_s), g(hist), g(hist, -2)
    dif_p, dea_p = g(macd_l, -2), g(macd_s, -2)
    k0, d0, k1, d1 = g(k), g(d), g(k, -2), g(d, -2)
    e20, e50, rsi0 = g(ema20), g(ema50), g(rsi)

    m_gc, m_dc = dif_p < dea_p and dif > dea, dif_p > dea_p and dif < dea
    s_gc, s_dc = k1 < d1 and k0 > d0, k1 > d1 and k0 < d0
    hist_up = h0 > h1

    buy = (dif > dea) + (h0 > 0) + 2 * m_gc + (hist_up and h0 > 0)
    buy += 2 if (k0 < 20 and d0 < 20) else (1 if (20 <= k0 <= 40 and k0 > d0) else 0)
    buy += 2 * (s_gc and k0 < 40) + 0.5 * (k0 > d0) + (1 if price > e20 > e50 else 0.5 * (price > e20))
    buy += 0.5 * (vol_ratio > 1.2) + 0.5 * (rsi0 < 70)
    sell = (dif < dea) + (h0 < 0) + 2 * m_dc + ((not hist_up) and h0 > 0)
    sell += 2 if (k0 > 80 and d0 > 80) else (1 if 80 <= k0 <= 95 else 0)
    sell += 2 * (s_dc and k0 > 80) + 0.5 * (k0 < d0) + (1 if price < e20 < e50 else 0.5 * (price < e20))
    sell += 0.5 * (rsi0 > 30)

    if buy >= 5:
        action = "🟢 STRONG BUY" if (buy >= 7 and s_gc and m_gc) else "🟢 BUY"
    elif sell >= 5:
        action = "🔴 STRONG SELL" if (sell >= 7 and s_dc and m_dc) else "🔴 SELL"
    elif k0 > 85 and (not hist_up) and h0 > 0:
        action = "💰 TAKE PROFIT"
    elif dif > dea and 20 <= k0 <= 80:
        action = "🟡 HOLD"
    else:
        action = "⏳ WAIT"

    return {
        "timeframe": timeframe, "action": action, "price": price,
        "macd": {"dif": dif, "dea": dea, "hist": h0, "hist_up": hist_up, "golden": m_gc, "death": m_dc},
        "stoch": {"k": k0, "d": d0, "golden": s_gc, "death": s_dc},
        "rsi": rsi0, "ema20": e20, "ema50": e50, "adx": float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0.0,
        "volume_ratio": vol_ratio, "ema_bull": e20 > e50, "bearish_trend": price < e20 < e50,
        "buy_score": float(buy), "sell_score": float(sell),
    }


# =========================================================
# AUTO TRADE PLAN (long-only)
# =========================================================
def _targets(entry, risk, cands):
    """TP1..TP3 dari level kandidat (min 1R dari entry), fallback kelipatan R."""
    cands = sorted(x for x in cands if x is not None and x >= entry + risk)
    tps = []
    for k, mult in enumerate((1.5, 2.5, 4.0)):
        tps.append(cands[k] if k < len(cands) else entry + risk * mult)
    for k in (1, 2):
        if tps[k] <= tps[k - 1]:
            tps[k] = tps[k - 1] + risk * 0.75
    return tps


def generate_trade_plan(df, symbol, tf, balance=1000.0, risk_pct=2.0, cfg=None, htf_ok=True, analysis=None):
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    if df is None or len(df) < 60:
        return None
    price = float(df["Close"].iloc[-1])
    atr_s = ATR(df)
    atr = float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) and atr_s.iloc[-1] > 0 else price * 0.02
    fib = get_fibonacci(df, 100)
    analysis = analysis or analyze_macd_stoch(df, tf)
    if fib is None or analysis is None:
        return None

    lv = fib["levels"]
    f236, f382, f5, f618, f786 = (lv[x] for x in (0.236, 0.382, 0.5, 0.618, 0.786))
    sh, slow = fib["high"], fib["low"]
    buy_side, sell_side = get_liquidity_zones(df, 100, 0.5, 3, 3)
    sup, res = get_support_resistance(df)
    res_all = sorted(set(res + buy_side))
    nearest_res = res_all[0] if res_all else None
    ssl = sell_side[0] if sell_side else None
    macd, stoch = analysis["macd"], analysis["stoch"]
    macd_bear = macd["dif"] < macd["dea"] and not macd["hist_up"]

    base = {
        "symbol": symbol, "timeframe": tf, "price": price, "atr": atr, "fib": fib, "analysis": analysis,
        "account_balance": balance, "risk_pct": risk_pct,
        "nearest_support": sup[0] if sup else None, "nearest_resistance": nearest_res,
        "dip_level": f618 if fib["trend"] == "up" else None, "breakout_level": nearest_res,
        "liq_level": ssl, "swing_high": sh, "swing_low": slow,
    }

    def wait(reason):
        return {**base, "setup_type": "WAIT", "setup_label": f"⏳ WAIT — {reason}", "setup_class": "setup-wait",
                "confidence": 0, "entry": price, "stop_loss": price, "tp1": price, "tp2": price, "tp3": price,
                "rr": 0.0, "reasons": [f"⚠️ {reason}"], "invalidations": ["Tidak ada setup valid = tidak entry"],
                "alternatives": [], "max_loss_usd": 0, "units": 0, "position_usd": 0, "profit_tp2_usd": 0,
                "order_type": "-", "signal_type": "WAIT", "signal_strength": 0}

    if cfg["use_htf"] and not htf_ok:
        return wait("Tren TF lebih besar bearish (filter HTF)")
    if analysis["volume_ratio"] < cfg["min_vol"]:
        return wait(f"Volume terlalu rendah ({analysis['volume_ratio']:.2f}x)")

    dip = None
    if fib["trend"] == "up":
        if f618 * 0.99 <= price <= f618 * 1.05:
            dip = ("0.618", f618)
        elif f5 * 0.99 <= price <= f5 * 1.03:
            dip = ("0.500", f5)
    bo = None
    if nearest_res and price >= nearest_res * 0.995:
        bo = nearest_res
    elif price >= sh * 0.995:
        bo = sh
    liq = ssl if (ssl and price <= ssl * 1.02) else None

    reasons, setup = [], None
    if dip:
        if macd_bear:
            return wait("Harga di zona Fib tapi MACD masih bearish")
        name, lvl = dip
        setup, label, cls = "BUY_THE_DIP", f"🅰️ BUY THE DIP (Fib {name})", "setup-dip"
        entry = min(lvl, price)
        base_sl = f786 if f786 < entry else entry - 2 * atr
        sl = min(base_sl * 0.997, entry - 1.2 * atr)
        risk = entry - sl
        tp1, tp2, tp3 = _targets(entry, risk, [f382, f236, sh])
        reasons += [f"✅ Harga dekat Fib {name} ({lvl:.6f}) pada uptrend swing",
                    f"📐 Range swing: {sh:.6f} − {slow:.6f}"]
    elif bo:
        if macd_bear or analysis["volume_ratio"] < 1.0:
            return wait("Dekat resistance tapi belum ada konfirmasi MACD/volume")
        setup, label, cls = "BREAKOUT", f"🅱️ BREAKOUT BUY (R {bo:.6f})", "setup-breakout"
        entry = bo * 1.002
        sl = entry - 1.5 * atr
        risk = entry - sl
        tp1, tp2, tp3 = entry + risk * 1.5, entry + risk * 2.5, entry + risk * 4.0
        reasons.append(f"✅ Buy-stop di atas resistance ({bo:.6f}) dengan konfirmasi volume")
    elif liq:
        if macd_bear or stoch["k"] > 60:
            return wait("Dekat SSL tapi momentum belum mendukung")
        setup, label, cls = "LIQUIDITY_GRAB", f"🅲 LIQUIDITY GRAB (SSL {liq:.6f})", "setup-liq"
        entry = min(liq * 1.003, price)
        sl = liq - 1.0 * atr
        risk = entry - sl
        tp1, tp2, tp3 = _targets(entry, risk, list(lv.values()) + [sh])
        reasons.append(f"✅ Harga di zona SSL ({liq:.6f}), potensi sweep & bounce")
    else:
        return wait("Tidak ada setup — harga di tengah range")

    if sl >= entry or (entry - sl) <= 0:
        return wait("Setup tidak valid (SL >= entry)")
    sl_pct = (entry - sl) / entry * 100
    if sl_pct > cfg["max_sl_pct"]:
        return wait(f"SL terlalu jauh ({sl_pct:.1f}%)")
    rr = (tp2 - entry) / (entry - sl)
    if rr < cfg["min_rr"]:
        return wait(f"RR terlalu rendah (1:{rr:.2f}, minimal 1:{cfg['min_rr']})")

    # ---- confidence ----
    conf = 0.0
    if macd["dif"] > macd["dea"]:
        conf += 1; reasons.append("✅ MACD bullish (DIF > DEA)")
    elif macd["hist_up"]:
        conf += 0.5; reasons.append("🟡 Histogram MACD mulai naik")
    if stoch["k"] < 30 and stoch["k"] > stoch["d"]:
        conf += 1; reasons.append(f"✅ StochRSI oversold + cross up (K={stoch['k']:.1f})")
    elif stoch["k"] < 50 and stoch["k"] > stoch["d"]:
        conf += 0.5; reasons.append(f"🟡 StochRSI bullish (K={stoch['k']:.1f})")
    if analysis["volume_ratio"] > 1.2:
        conf += 1; reasons.append(f"✅ Volume konfirmasi (RVOL {analysis['volume_ratio']:.2f}x)")
    else:
        reasons.append(f"⚠️ Volume biasa (RVOL {analysis['volume_ratio']:.2f}x)")
    if ssl and abs(entry - ssl) / ssl * 100 < 2:
        conf += 1; reasons.append(f"✅ Entry konfluen dengan SSL ({ssl:.6f})")
    if abs(entry - f618) / f618 * 100 < 2:
        conf += 0.5; reasons.append("✅ Entry di Fib 0.618 (golden ratio)")
    if htf_ok and HTF_OF.get(tf):
        conf += 0.5; reasons.append(f"✅ Searah tren {HTF_OF[tf]} (EMA20 > EMA50)")
    reasons.append(f"ℹ️ ADX {analysis['adx']:.1f} ({'trending' if analysis['adx'] >= 20 else 'sideways/lemah'})")
    conf_i = min(5, int(conf + 0.5))

    invalidations = [f"❌ Batal jika candle {tf} close < {sl:.6f}",
                     f"❌ Batal jika MACD death cross di {tf}",
                     "❌ Batal jika entry belum terisi dalam ±8 candle"]

    # ---- skenario alternatif ----
    alts = []
    if setup != "BUY_THE_DIP" and fib["trend"] == "up" and f618 < price:
        a_sl = min(f786 * 0.997, f618 - 1.2 * atr)
        a_risk = f618 - a_sl
        if a_risk > 0:
            a_tp = f382 if f382 > f618 + a_risk else f618 + a_risk * 2
            alts.append({"name": "🅰️ LIMIT BUY (tunggu pullback)", "entry": f618, "sl": a_sl, "tp": a_tp,
                         "rr": (a_tp - f618) / a_risk, "note": f"Tunggu harga turun ke Fib 0.618 ({f618:.6f})"})
    if setup != "BREAKOUT" and nearest_res and nearest_res > price:
        b_entry = nearest_res * 1.002
        b_risk = 1.5 * atr
        alts.append({"name": "🅱️ BREAKOUT BUY", "entry": b_entry, "sl": b_entry - b_risk,
                     "tp": b_entry + b_risk * 2.5, "rr": 2.5,
                     "note": f"Tunggu tembus resistance {nearest_res:.6f} dengan volume"})

    max_loss = balance * risk_pct / 100
    units = max_loss / (entry - sl)
    order_type = "MARKET" if abs(entry - price) / price < 0.002 else ("LIMIT" if entry < price else "STOP")
    signal_type = "STRONG BUY" if conf_i >= 4 else ("BUY" if conf_i >= 3 else "WEAK BUY")

    return {
        **base, "setup_type": setup, "setup_label": label, "setup_class": cls, "confidence": conf_i,
        "entry": float(entry), "stop_loss": float(sl), "tp1": float(tp1), "tp2": float(tp2), "tp3": float(tp3),
        "rr": float(rr), "reasons": reasons, "invalidations": invalidations, "alternatives": alts,
        "max_loss_usd": max_loss, "units": units, "position_usd": units * entry,
        "profit_tp2_usd": units * (tp2 - entry), "order_type": order_type,
        "signal_type": signal_type, "signal_strength": 3 if conf_i >= 4 else (2 if conf_i >= 3 else 1),
    }


def is_valid_plan(plan, cfg):
    return bool(plan and plan["setup_type"] in VALID_SETUPS and plan["confidence"] >= cfg["min_conf"]
                and plan["rr"] >= cfg["min_rr"])


# =========================================================
# MULTI TIMEFRAME
# =========================================================
def analyze_mtf(symbol, cfg, balance, risk_pct):
    def _run():
        data = {}
        for tf in TIMEFRAMES:
            df = get_data(symbol, tf, 500)
            if df is None or len(df) < 80:
                continue
            a = analyze_macd_stoch(df, tf)
            if a:
                data[tf] = (df, a)
        if not data:
            return None
        results = {}
        for tf, (df, a) in data.items():
            h = HTF_OF.get(tf)
            htf_ok = True if (h is None or h not in data) else bool(data[h][1]["ema_bull"])
            plan = generate_trade_plan(df, symbol, tf, balance, risk_pct, cfg, htf_ok, a)
            if plan:
                results[tf] = {"plan": plan, "analysis": a}
        if not results:
            return None

        valid = [tf for tf in ("4h", "1h", "15m") if tf in results and is_valid_plan(results[tf]["plan"], cfg)]
        best, best_c = None, -1
        for tf in valid:  # 4h, 1h, 15m: tie-break ke TF lebih besar
            if results[tf]["plan"]["confidence"] > best_c:
                best_c, best = results[tf]["plan"]["confidence"], results[tf]["plan"]
        if len(valid) >= 2:
            main, strength = "🟢 STRONG BUY (Multi TF)", 3
        elif len(valid) == 1:
            main, strength = "🟢 BUY", 2
        elif all(r["analysis"]["bearish_trend"] for r in results.values()):
            main, strength = "🔴 BEARISH (hindari long)", 1
        else:
            main, strength = "🟡 WAIT", 1
        return {"symbol": symbol, "timeframes": results, "main_signal": main, "main_strength": strength,
                "buy_count": len(valid), "best_plan": best}

    key = ("mtf", symbol, json.dumps(cfg, sort_keys=True), balance, risk_pct)
    return _cached(key, 60, _run)


# =========================================================
# SIMULASI TRADE (dipakai backtest & tracker live)
# Model: entry terisi saat harga menyentuh entry; 50% keluar di TP1 lalu SL geser ke BE;
# sisa 50% ke TP2. Dalam satu candle, SL dianggap kena lebih dulu (konservatif).
# =========================================================
def simulate_trade(fut, entry, sl, tp1, tp2, fill_window=None, max_hold=None, fee_pct=0.2, force_close=False):
    risk = entry - sl
    if risk <= 0 or len(fut) == 0:
        return {"status": "INVALID", "r": 0.0, "filled": False, "bars": 0}
    cost = entry * fee_pct / 100 / risk
    H, L, C = fut["High"].to_numpy(), fut["Low"].to_numpy(), fut["Close"].to_numpy()
    r1, r2 = (tp1 - entry) / risk, (tp2 - entry) / risk
    filled, fill_i, stage, locked, timed_out = False, 0, 1, 0.0, False
    last = len(H) - 1
    for i in range(len(H)):
        last = i
        if not filled:
            if fill_window is not None and i >= fill_window:
                return {"status": "NOT_FILLED", "r": 0.0, "filled": False, "bars": i}
            if L[i] <= entry <= H[i]:
                filled, fill_i = True, i
                if L[i] <= sl:
                    return {"status": "LOSS", "r": -1 - cost, "filled": True, "bars": i + 1}
            continue
        if max_hold is not None and i - fill_i > max_hold:
            timed_out = True
            break
        if stage == 1:
            if L[i] <= sl:
                return {"status": "LOSS", "r": -1 - cost, "filled": True, "bars": i + 1}
            if H[i] >= tp1:
                stage, locked = 2, 0.5 * r1
        else:
            if L[i] <= entry:
                return {"status": "WIN", "r": locked - cost, "filled": True, "bars": i + 1}
            if H[i] >= tp2:
                return {"status": "WIN", "r": locked + 0.5 * r2 - cost, "filled": True, "bars": i + 1}
    if not filled:
        if force_close:
            return {"status": "NOT_FILLED", "r": 0.0, "filled": False, "bars": len(H)}
        return {"status": "PENDING", "r": 0.0, "filled": False, "bars": len(H)}
    mtm = (C[last] - entry) / risk
    r = locked + (0.5 if stage == 2 else 1.0) * mtm - cost
    return {"status": "TIMEOUT" if (force_close or timed_out) else "RUNNING", "r": r, "filled": True, "bars": last + 1}


def perf_stats(rs):
    rs = pd.Series(rs, dtype=float).dropna()
    if rs.empty:
        return dict(n=0, wins=0, losses=0, win_rate=0.0, avg_r=0.0, pf=0.0, total_r=0.0, max_dd=0.0)
    wins, losses = rs[rs > 0], rs[rs <= 0]
    gl = abs(losses.sum())
    pf = wins.sum() / gl if gl > 0 else (float("inf") if wins.sum() > 0 else 0.0)
    cum = rs.cumsum()
    dd = float((cum - np.maximum(cum.cummax(), 0)).min())
    return dict(n=len(rs), wins=len(wins), losses=len(losses), win_rate=len(wins) / len(rs) * 100,
                avg_r=float(rs.mean()), pf=float(pf), total_r=float(rs.sum()), max_dd=dd)


def fmt_pf(pf):
    return "∞" if pf == float("inf") else f"{pf:.2f}"


# =========================================================
# BACKTEST
# =========================================================
def backtest_trade_plan(df, symbol, tf, cfg, horizon=24, fill_window=8, step=2, min_conf=3):
    if df is None or len(df) < 300:
        return pd.DataFrame(), {}
    rows, i, n = [], 150, len(df)
    while i < n - 3:
        window = df.iloc[:i + 1]
        htf_ok = True
        rule = HTF_RULE_FOR_BACKTEST.get(tf)
        if cfg["use_htf"] and rule:
            h = resample_ohlc(window, rule)
            if len(h) >= 55:
                htf_ok = bool(EMA(h["Close"], 20).iloc[-1] > EMA(h["Close"], 50).iloc[-1])
        try:
            plan = generate_trade_plan(window, symbol, tf, cfg=cfg, htf_ok=htf_ok)
        except Exception as e:
            log.warning("bt plan: %s", e)
            plan = None
        if plan and plan["setup_type"] in VALID_SETUPS and plan["confidence"] >= min_conf and plan["rr"] >= cfg["min_rr"]:
            fut = df.iloc[i + 1:i + 1 + fill_window + horizon]
            if len(fut) < 2:
                break
            sim = simulate_trade(fut, plan["entry"], plan["stop_loss"], plan["tp1"], plan["tp2"],
                                 fill_window, horizon, cfg["fee_pct"], force_close=True)
            rows.append({"Date": df["Time"].iloc[i], "Setup": plan["setup_type"], "Conf": plan["confidence"],
                         "Order": plan["order_type"], "Entry": plan["entry"], "SL": plan["stop_loss"],
                         "TP1": plan["tp1"], "TP2": plan["tp2"], "RR": plan["rr"],
                         "Status": sim["status"], "R": sim["r"], "Filled": sim["filled"]})
            i += max(step, sim["bars"] + 1)
        else:
            i += step
    bt = pd.DataFrame(rows)
    if bt.empty:
        return bt, {}
    filled = bt[bt["Filled"]]
    stats = perf_stats(filled["R"].tolist())
    stats["signals"] = len(bt)
    stats["fill_rate"] = len(filled) / len(bt) * 100
    return bt, stats


# =========================================================
# TRACKER (paper trading) — update status sinyal aktif
# =========================================================
def update_active_signals(send_tg=False):
    changed = 0
    for row in get_active_signals():
        try:
            ts = pd.to_datetime(row["timestamp"])
            df = get_data(row["symbol"], "15m", 1000)
            if df is None:
                continue
            fut = df[df["Time"] > ts]
            if fut.empty:
                continue
            sim = simulate_trade(fut, row["entry"], row["sl"], row["tp1"], row["tp2"],
                                 fill_window=192, max_hold=672, fee_pct=DEFAULT_CFG["fee_pct"])
            new = {"PENDING": "OPEN", "RUNNING": "FILLED", "NOT_FILLED": "EXPIRED"}.get(sim["status"], sim["status"])
            if new == row.get("status"):
                continue
            fields = {"status": new}
            if new in ("WIN", "LOSS", "TIMEOUT", "EXPIRED"):
                fields.update({"result_r": round(float(sim["r"]), 3), "closed_at": utcnow().isoformat()})
            if update_signal(row["id"], fields):
                changed += 1
                if send_tg and new in ("WIN", "LOSS", "TIMEOUT"):
                    icon = {"WIN": "✅", "LOSS": "🛑", "TIMEOUT": "⌛"}[new]
                    send_telegram(f"{icon} <b>{esc(row['symbol'])}</b> {esc(row.get('timeframe', ''))} "
                                  f"{esc(row.get('signal', ''))}\nHasil: <b>{new}</b> ({sim['r']:+.2f}R)")
        except Exception as e:
            log.warning("update_active_signals: %s", e)
    return changed


def process_alerts(results, cfg, send_tg):
    sent = 0
    for sym, res in results.items():
        bp = res.get("best_plan") if res else None
        if not bp or not is_valid_plan(bp, cfg):
            continue
        if already_alerted(sym, bp["setup_type"], cfg["cooldown_min"]):
            continue
        save_signal(plan_to_row(bp))
        st.session_state.alert_times[(sym, bp["setup_type"])] = utcnow()
        if send_tg:
            ok, err = send_telegram(format_plan_for_telegram(bp))
            if not ok:
                log.warning("telegram: %s", err)
        sent += 1
    return sent


# =========================================================
# CHART
# =========================================================
def create_chart(df, symbol, tf, plan=None, show_fib=True, show_liq=True, show_sr=True, show_plan=True):
    if df is None or len(df) < 30:
        return None
    close = df["Close"]
    macd_l, macd_s, hist = MACD(close)
    k, d, rsi = StochRSI(close)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.4, 0.15, 0.25, 0.2],
                        subplot_titles=(f"{symbol} {tf}", "RSI", "MACD", "Stochastic RSI"))
    fig.add_trace(go.Candlestick(x=df["Time"], open=df["Open"], high=df["High"], low=df["Low"], close=close,
                                 increasing_line_color="#00ff88", decreasing_line_color="#ff3b5c", name="Price"), 1, 1)
    fig.add_trace(go.Scatter(x=df["Time"], y=EMA(close, 20), line=dict(color="#00a2ff", width=1.5), name="EMA20"), 1, 1)
    fig.add_trace(go.Scatter(x=df["Time"], y=EMA(close, 50), line=dict(color="#ffaa00", width=1.5, dash="dash"),
                             name="EMA50"), 1, 1)

    def hline(y, color, dash, width, text, pos="right", size=9):
        fig.add_hline(y=y, line_dash=dash, line_color=color, line_width=width, annotation_text=f"  {text}",
                      annotation_position=pos, annotation_font=dict(size=size, color=color), row=1, col=1)

    if show_fib:
        fib = get_fibonacci(df, 100)
        if fib:
            for r_, p_ in fib["levels"].items():
                hline(p_, "rgba(0,200,255,0.55)", "dash", 1, f"Fib {r_}")
            hline(fib["high"], "rgba(148,163,184,0.6)", "dot", 1, "Swing High")
            hline(fib["low"], "rgba(148,163,184,0.6)", "dot", 1, "Swing Low")
    if show_liq:
        bs, ss = get_liquidity_zones(df, 100)
        for lv_ in bs[:3]:
            hline(lv_, "rgba(0,255,136,0.4)", "solid", 1, "💧 BSL", "left")
        for lv_ in ss[:3]:
            hline(lv_, "rgba(255,59,92,0.4)", "solid", 1, "💧 SSL", "left")
    if show_sr:
        sup, res = get_support_resistance(df)
        for lv_ in res[:2]:
            hline(lv_, "rgba(255,100,100,0.5)", "longdash", 1.2, f"R {format_price(lv_)}")
        for lv_ in sup[:2]:
            hline(lv_, "rgba(100,255,100,0.5)", "longdash", 1.2, f"S {format_price(lv_)}")
    if show_plan and plan and plan.get("setup_type") in VALID_SETUPS:
        e, sl = plan["entry"], plan["stop_loss"]
        hline(e, "#00c8ff", "solid", 2, f"🎯 ENTRY {e:.6f}", "left", 11)
        hline(sl, "#ff3b5c", "solid", 2, f"🛑 SL {sl:.6f}", "left", 11)
        for key in ("tp1", "tp2", "tp3"):
            hline(plan[key], "#00ff88", "dot", 1.5, f"{key.upper()} {plan[key]:.6f}", "left", 10)
        fig.add_hrect(y0=sl, y1=e, fillcolor="rgba(255,59,92,0.08)", line_width=0, row=1, col=1)
        fig.add_hrect(y0=e, y1=plan["tp2"], fillcolor="rgba(0,255,136,0.06)", line_width=0, row=1, col=1)

    fig.add_trace(go.Scatter(x=df["Time"], y=rsi, line=dict(color="#a855f7", width=2), name="RSI"), 2, 1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    fig.add_trace(go.Scatter(x=df["Time"], y=macd_l, line=dict(color="#00a2ff", width=1.5), name="DIF"), 3, 1)
    fig.add_trace(go.Scatter(x=df["Time"], y=macd_s, line=dict(color="#ff00ff", width=1.5), name="DEA"), 3, 1)
    fig.add_trace(go.Bar(x=df["Time"], y=hist, marker_color=["#00ff88" if h >= 0 else "#ff3b5c" for h in hist],
                         opacity=0.5, name="Hist"), 3, 1)
    fig.add_trace(go.Scatter(x=df["Time"], y=k, line=dict(color="#ffaa00", width=1.5), name="K"), 4, 1)
    fig.add_trace(go.Scatter(x=df["Time"], y=d, line=dict(color="#ff00ff", width=1.5, dash="dash"), name="D"), 4, 1)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=4, col=1)
    fig.update_layout(template="plotly_dark", height=900, hovermode="x unified", dragmode="pan",
                      xaxis_rangeslider_visible=False, paper_bgcolor="#0a0a1a", plot_bgcolor="#0a0a1a",
                      font=dict(color="#94a3b8"), margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.03)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.03)")
    return fig


def equity_chart(rs, title):
    cum = pd.Series(rs, dtype=float).cumsum()
    fig = go.Figure(go.Scatter(y=cum, mode="lines", line=dict(color="#00ff88", width=2), fill="tozeroy",
                               fillcolor="rgba(0,255,136,0.08)"))
    fig.update_layout(template="plotly_dark", height=300, title=title, paper_bgcolor="#0a0a1a",
                      plot_bgcolor="#0a0a1a", margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Kumulatif R")
    return fig


# =========================================================
# RENDER PLAN
# =========================================================
def level_box(col, label, value, sub="", cls=""):
    col.markdown(f'<div class="level-box"><div class="level-label">{label}</div>'
                 f'<div class="level-value">{value}</div><div class="level-pct {cls}">{sub}</div></div>',
                 unsafe_allow_html=True)


def render_trade_plan(plan, symbol, tf):
    st.markdown(f"""
    <div class="plan-card">
      <div class="plan-header">🎯 AUTO TRADE PLAN — {symbol} · {tf}</div>
      <div style="color:#64748b;font-size:13px;margin-bottom:12px;">Generated: {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
      <span class="setup-badge {plan['setup_class']}">{plan['setup_label']}</span>
      <span class="plan-confidence" style="margin-left:10px;">{'⭐' * plan['confidence']} ({plan['confidence']}/5)</span>
    </div>""", unsafe_allow_html=True)

    if plan["setup_type"] == "WAIT":
        st.warning("⏳ " + " | ".join(plan["reasons"]))
        if plan.get("dip_level"):
            st.info(f"💡 Tunggu pullback ke **{plan['dip_level']:.6f}** atau breakout di atas "
                    f"**{plan.get('breakout_level') or 0:.6f}**")
        return

    e = plan["entry"]
    pct = lambda x: f"{(x / e - 1) * 100:+.2f}%"
    c = st.columns(4)
    level_box(c[0], "📈 Entry", f"${e:.6f}", plan["order_type"])
    level_box(c[1], "🛑 Stop Loss", f"${plan['stop_loss']:.6f}", pct(plan["stop_loss"]), "neg")
    level_box(c[2], "🎯 TP1", f"${plan['tp1']:.6f}", pct(plan["tp1"]), "pos")
    level_box(c[3], "🎯 TP2", f"${plan['tp2']:.6f}", pct(plan["tp2"]), "pos")
    c = st.columns(4)
    level_box(c[0], "🎯 TP3", f"${plan['tp3']:.6f}", pct(plan["tp3"]), "pos")
    rr = plan["rr"]
    level_box(c[1], "📊 Risk/Reward", f"1 : {rr:.2f}", "✅ GOOD" if rr >= 2 else "⚠️ OK")
    level_box(c[2], "💰 Position", f"${plan['position_usd']:.2f}", f"{plan['units']:.4f} unit")
    level_box(c[3], "💵 Max Loss", f"${plan['max_loss_usd']:.2f}", f"{plan['risk_pct']:.1f}% modal", "neg")

    a, b = st.columns(2)
    with a:
        st.markdown("##### 🧠 Alasan")
        for r in plan["reasons"]:
            st.markdown(f"<div class='reason-item'>{r}</div>", unsafe_allow_html=True)
    with b:
        st.markdown("##### ⚠️ Invalidasi")
        for i in plan["invalidations"]:
            st.markdown(f"<div class='reason-item'>{i}</div>", unsafe_allow_html=True)

    for alt in plan.get("alternatives", []):
        with st.expander(f"{alt['name']} — R:R 1:{alt['rr']:.2f}"):
            m = st.columns(3)
            m[0].metric("Entry", f"${alt['entry']:.6f}")
            m[1].metric("SL", f"${alt['sl']:.6f}")
            m[2].metric("TP", f"${alt['tp']:.6f}")
            st.caption(alt["note"])

    st.markdown("---")
    b1, b2, b3 = st.columns(3)
    if b1.button("📱 Kirim ke Telegram", width="stretch", key="btn_tg_plan"):
        ok, err = send_telegram(format_plan_for_telegram(plan))
        st.success("✅ Terkirim") if ok else st.error(f"❌ {err}")
    if b2.button("📝 Lacak sebagai paper trade", width="stretch", key="btn_track"):
        if save_signal(plan_to_row(plan, source="manual")):
            st.success("✅ Disimpan & akan dilacak otomatis")
        else:
            st.error("❌ Gagal simpan (cek Supabase)")
    txt = re.sub(r"</?[bi]>", "", format_plan_for_telegram(plan))
    b3.download_button("📋 Download TXT", txt, mime="text/plain", width="stretch",
                       file_name=f"plan_{symbol}_{tf}_{utcnow().strftime('%Y%m%d_%H%M')}.txt")


# =========================================================
# STATE
# =========================================================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = get_watchlist()
if "alert_times" not in st.session_state:
    st.session_state.alert_times = {}

st.title("🤖 Crypto Signal Pro")
st.caption("Multi TF + MACD + StochRSI + Fibonacci + Liquidity + Auto Trade Plan + Paper Trading Tracker")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Settings")
    st.success("☁️ Supabase terhubung") if db_ok() else st.warning("⚠️ Supabase tidak terhubung — mode tanpa database")

    st.subheader("📋 Watchlist")
    ca, cb = st.columns([3, 1])
    new_coin = ca.text_input("Add Coin", placeholder="BTC", label_visibility="collapsed")
    if cb.button("➕", width="stretch") and new_coin:
        coin = re.sub(r"[^A-Z0-9]", "", new_coin.upper())
        if coin and coin not in st.session_state.watchlist and add_coin(coin):
            st.session_state.watchlist.append(coin)
            st.rerun()
    cols = st.columns(3)
    for idx, coin in enumerate(list(st.session_state.watchlist)):
        if cols[idx % 3].button(f"✕ {coin}", key=f"del_{coin}", width="stretch"):
            if remove_coin(coin):
                st.session_state.watchlist.remove(coin)
                st.rerun()

    st.divider()
    st.subheader("💰 Position Sizing")
    account_balance = st.number_input("Modal ($)", min_value=10.0, value=1000.0, step=100.0)
    risk_pct = st.slider("Risk per trade (%)", 0.5, 5.0, 2.0, 0.5)
    st.caption(f"Max loss per trade: **${account_balance * risk_pct / 100:.2f}**")

    st.divider()
    st.subheader("🧪 Strategi")
    cfg = dict(DEFAULT_CFG)
    cfg["min_conf"] = st.slider("Min confidence alert", 1, 5, DEFAULT_CFG["min_conf"])
    cfg["min_rr"] = st.slider("Min RR (ke TP2)", 1.0, 4.0, DEFAULT_CFG["min_rr"], 0.1)
    cfg["max_sl_pct"] = st.slider("Max jarak SL (%)", 1.0, 15.0, DEFAULT_CFG["max_sl_pct"], 0.5)
    cfg["min_vol"] = st.slider("Min RVOL", 0.1, 2.0, DEFAULT_CFG["min_vol"], 0.1)
    cfg["use_htf"] = st.toggle("Filter tren TF lebih besar", value=True)
    cfg["fee_pct"] = st.number_input("Fee+slippage round-trip (%)", 0.0, 2.0, DEFAULT_CFG["fee_pct"], 0.05)
    cfg["cooldown_min"] = st.slider("Cooldown alert (menit)", 5, 240, DEFAULT_CFG["cooldown_min"], 5)

    st.divider()
    st.subheader("🔄 Scanner")
    auto_on = st.toggle("Auto scan & refresh", value=False)
    refresh = st.slider("Interval (detik)", 30, 300, 60, 10)

    st.divider()
    st.subheader("📱 Telegram")
    send_tg = st.toggle("Kirim alert otomatis", value=True)
    if st.button("🚀 Test Telegram", width="stretch"):
        ok, err = send_telegram("🤖 <b>Crypto Signal Pro</b>\n✅ Koneksi berhasil!\n"
                                f"🕐 {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        st.success("✅ Test terkirim!") if ok else st.error(f"❌ {err}")

if auto_on:
    st_autorefresh(interval=refresh * 1000, key="refresh")

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Scanner", "📈 Chart + Plan", "🧪 Backtest", "📋 History", "📊 Performance"])


def run_scan(symbols):
    def one(s):
        try:
            return s, analyze_mtf(s, cfg, account_balance, risk_pct)
        except Exception as e:
            log.warning("scan %s: %s", s, e)
            return s, None
    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(ex.map(one, symbols))


# ==================== TAB 1: SCANNER ====================
with tab1:
    st.subheader("📊 Signal Scanner")
    st.caption("Sinyal memakai Auto Trade Plan yang sama dengan tab Chart. Alert hanya untuk setup valid "
               "(confidence & RR sesuai pengaturan) dan tidak duplikat selama cooldown.")
    scan_now = st.button("🔍 Scan sekarang")
    first = "scan_results" not in st.session_state
    due_auto = auto_on and (time.time() - st.session_state.get("scan_ts", 0)) >= refresh - 2
    if scan_now or first or due_auto:
        with st.spinner("Scanning watchlist..."):
            st.session_state.scan_results = run_scan(st.session_state.watchlist[:50])
            st.session_state.scan_ts = time.time()
            n_alert = process_alerts(st.session_state.scan_results, cfg, send_tg)
            n_upd = update_active_signals(send_tg)
        if n_alert:
            st.toast(f"🔔 {n_alert} sinyal baru")
        if n_upd:
            st.toast(f"📌 {n_upd} sinyal aktif berubah status")

    results = {k: v for k, v in st.session_state.scan_results.items() if v}
    if results:
        st.caption(f"Terakhir scan: {datetime.fromtimestamp(st.session_state.scan_ts).strftime('%H:%M:%S')}")
        table = []
        for sym, res in results.items():
            bp = res["best_plan"]
            row = {"Coin": sym, "Signal": res["main_signal"], "Strength": "⭐" * res["main_strength"],
                   "RR": f"1:{bp['rr']:.2f}" if bp else "-"}
            for tf in TIMEFRAMES:
                if tf in res["timeframes"]:
                    p, a = res["timeframes"][tf]["plan"], res["timeframes"][tf]["analysis"]
                    row[tf.upper()] = f"{SETUP_SHORT[p['setup_type']]} ({p['confidence']}⭐)"
                    row[f"{tf.upper()} RSI"] = f"{a['rsi']:.1f}"
                    row[f"{tf.upper()} K"] = f"{a['stoch']['k']:.1f}"
            table.append(row)
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
        nb = sum(1 for r in results.values() if r["best_plan"])
        if nb:
            st.success(f"🏆 {nb} coin dengan setup valid")
    else:
        st.info("ℹ️ Belum ada data (cek koneksi / watchlist).")

    st.divider()
    st.subheader("⏳ Sinyal Aktif (paper trade)")
    active = get_active_signals()
    if active:
        rows = []
        for s in sorted(active, key=lambda x: x["timestamp"], reverse=True):
            d15 = get_data(s["symbol"], "15m", 100)
            cur = float(d15["Close"].iloc[-1]) if d15 is not None else None
            rows.append({"Waktu (UTC)": str(s["timestamp"])[:16].replace("T", " "), "Coin": s["symbol"],
                         "TF": s.get("timeframe"), "Setup": s.get("signal"), "Status": s.get("status"),
                         "Conf": f"{s.get('confidence', 0)}⭐", "Order": s.get("order_type"),
                         "Current": format_price(cur), "Entry": format_price(s["entry"]),
                         "Jarak": f"{(s['entry'] / cur - 1) * 100:+.2f}%" if cur else "-",
                         "SL": format_price(s["sl"]), "TP1": format_price(s["tp1"]),
                         "TP2": format_price(s["tp2"]), "RR": f"1:{s['rr']:.2f}"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("Belum ada sinyal aktif.")

# ==================== TAB 2: CHART ====================
with tab2:
    st.subheader("📈 Chart + 🎯 Auto Trade Plan")
    cc1, cc2 = st.columns(2)
    chart_coin = cc1.selectbox("Coin", st.session_state.watchlist, key="chart_select")
    chart_tf = cc2.selectbox("Timeframe", TIMEFRAMES, index=1, key="chart_tf")
    t1, t2, t3, t4 = st.columns(4)
    show_fib = t1.toggle("📐 Fibonacci", True, key="tog_fib")
    show_liq = t2.toggle("💧 Liquidity", True, key="tog_liq")
    show_sr = t3.toggle("📏 S/R", True, key="tog_sr")
    show_plan = t4.toggle("🎯 Plan", True, key="tog_plan")

    if chart_coin:
        df = get_data(chart_coin, chart_tf, 500)
        if df is not None and len(df) >= 80:
            mtf = analyze_mtf(chart_coin, cfg, account_balance, risk_pct)
            tfres = mtf["timeframes"].get(chart_tf) if mtf else None
            plan = tfres["plan"] if tfres else generate_trade_plan(df, chart_coin, chart_tf, account_balance, risk_pct, cfg)
            result = tfres["analysis"] if tfres else analyze_macd_stoch(df, chart_tf)

            fig = create_chart(df, chart_coin, chart_tf, plan, show_fib, show_liq, show_sr, show_plan)
            if fig:
                st.plotly_chart(fig, width="stretch")
            if result:
                m = st.columns(5)
                act = result["action"]
                css = ("signal-buy" if "BUY" in act else "signal-sell" if "SELL" in act
                       else "signal-take-profit" if "TAKE" in act else "signal-hold")
                m[0].markdown(f'<div class="sig {css}">{act}</div>', unsafe_allow_html=True)
                m[1].metric("MACD DIF", f"{result['macd']['dif']:.6f}")
                m[2].metric("RSI (Wilder)", f"{result['rsi']:.1f}")
                m[3].metric("RVOL", f"{result['volume_ratio']:.2f}x")
                m[4].metric("ADX", f"{result['adx']:.1f}")
            st.divider()
            if plan:
                render_trade_plan(plan, chart_coin, chart_tf)
        else:
            st.error(f"❌ Tidak bisa mengambil data {chart_coin}")

# ==================== TAB 3: BACKTEST ====================
with tab3:
    st.subheader("🧪 Backtest Auto Trade Plan")
    st.caption("Entry harus tersentuh (limit/stop), SL dicek lebih dulu dalam satu candle, partial TP 50% di TP1 "
               "lalu SL ke breakeven, fee+slippage dihitung, tidak ada trade tumpang tindih. Hasil dalam R.")
    q = st.columns(3)
    bt_coin = q[0].selectbox("Coin", st.session_state.watchlist, key="bt_coin")
    bt_tf = q[1].selectbox("Timeframe", ["15m", "1h", "4h"], index=1, key="bt_tf")
    bt_conf = q[2].slider("Min Confidence", 1, 5, 3, key="bt_conf")
    q = st.columns(4)
    bt_hold = q[0].slider("Max hold (candle)", 5, 100, 24)
    bt_fill = q[1].slider("Validitas order (candle)", 2, 30, 8)
    bt_step = q[2].slider("Step scan (candle)", 1, 6, 2)
    run_bt = q[3].button("▶️ Run Backtest", width="stretch")

    if run_bt:
        with st.spinner("Running backtest (±1000 candle)..."):
            df_bt = get_data(bt_coin, bt_tf, 1000)
            if df_bt is None or len(df_bt) < 300:
                st.error("Data tidak cukup.")
            else:
                bt, s = backtest_trade_plan(df_bt, bt_coin, bt_tf, cfg, bt_hold, bt_fill, bt_step, bt_conf)
                if bt.empty or not s:
                    st.warning("Tidak ada sinyal yang terisi pada sampel ini.")
                else:
                    m = st.columns(5)
                    m[0].metric("Sinyal / Terisi", f"{s['signals']} / {s['n']}")
                    m[1].metric("Win Rate", f"{s['win_rate']:.1f}%")
                    m[2].metric("Expectancy", f"{s['avg_r']:+.2f}R")
                    m[3].metric("Profit Factor", fmt_pf(s["pf"]))
                    m[4].metric("Max Drawdown", f"{s['max_dd']:.2f}R")
                    m = st.columns(3)
                    m[0].metric("Total R", f"{s['total_r']:+.2f}R")
                    m[1].metric("Fill rate", f"{s['fill_rate']:.0f}%")
                    m[2].metric("Win / Loss", f"{s['wins']} / {s['losses']}")
                    filled = bt[bt["Filled"]].sort_values("Date")
                    st.plotly_chart(equity_chart(filled["R"].tolist(), "Equity curve (R)"), width="stretch")
                    by = (filled.groupby("Setup")["R"].agg(["count", "mean", "sum"])
                          .rename(columns={"count": "Trades", "mean": "Avg R", "sum": "Total R"}).round(2))
                    st.markdown("**Per setup**")
                    st.dataframe(by, width="stretch")
                    st.dataframe(bt.sort_values("Date", ascending=False), width="stretch", hide_index=True)
                    if s["n"] < 30:
                        st.warning("⚠️ Sampel < 30 trade — hasil belum signifikan secara statistik.")

# ==================== TAB 4: HISTORY ====================
with tab4:
    st.subheader("📜 Signal History")
    hist = get_signal_history(300)
    if hist:
        dfh = pd.DataFrame(hist).drop(columns=["id"], errors="ignore")
        st.dataframe(dfh, width="stretch", hide_index=True)
        st.download_button("📥 Download CSV", dfh.to_csv(index=False), mime="text/csv",
                           file_name=f"history_{utcnow().strftime('%Y%m%d')}.csv")
    else:
        st.info("Belum ada sinyal (atau database belum terhubung).")

# ==================== TAB 5: PERFORMANCE ====================
with tab5:
    st.subheader("📊 Performance Nyata (paper trade)")
    st.caption("Dihitung dari sinyal yang benar-benar dikirim & dilacak, bukan hasil backtest.")
    hist_all = get_signal_history(1000)
    closed = [h for h in hist_all if h.get("status") in ("WIN", "LOSS", "TIMEOUT") and h.get("result_r") is not None]
    closed.sort(key=lambda x: x["timestamp"])
    s = perf_stats([h["result_r"] for h in closed])
    m = st.columns(5)
    m[0].metric("Trade selesai", s["n"])
    m[1].metric("Win Rate", f"{s['win_rate']:.1f}%")
    m[2].metric("Expectancy", f"{s['avg_r']:+.2f}R")
    m[3].metric("Profit Factor", fmt_pf(s["pf"]))
    m[4].metric("Max Drawdown", f"{s['max_dd']:.2f}R")
    n_exp = sum(1 for h in hist_all if h.get("status") == "EXPIRED")
    n_act = sum(1 for h in hist_all if h.get("status") in ("OPEN", "FILLED"))
    st.caption(f"Aktif: {n_act} · Expired (entry tidak terisi): {n_exp} · Total R: {s['total_r']:+.2f}R")
    if closed:
        st.plotly_chart(equity_chart([h["result_r"] for h in closed], "Equity curve live (R)"), width="stretch")
        dfc = pd.DataFrame(closed)
        by = (dfc.groupby("setup_type")["result_r"].agg(["count", "mean", "sum"])
              .rename(columns={"count": "Trades", "mean": "Avg R", "sum": "Total R"}).round(2))
        st.dataframe(by, width="stretch")
    st.divider()
    st.markdown("""
**Aturan setup (long-only)**
- 🅰️ **BUY THE DIP** — uptrend swing, harga di Fib 0.618/0.5, MACD tidak bearish
- 🅱️ **BREAKOUT** — buy-stop di atas resistance, wajib MACD tidak bearish & RVOL ≥ 1
- 🅲 **LIQUIDITY GRAB** — harga di zona SSL, StochRSI K ≤ 60, MACD tidak bearish
- ⏳ **WAIT** — volume rendah, RR < minimum, SL terlalu jauh, tren TF besar bearish, atau tidak ada setup

Model eksekusi: 50% keluar di TP1, SL geser ke breakeven, sisa ke TP2. Fee+slippage dihitung.
""")

st.divider()
st.caption("🔄 Binance (fallback Yahoo Finance) · 15M/1H/4H · MACD + StochRSI + EMA + ADX · Fib + Liquidity + S/R · "
           "💾 Supabase · ⚠️ Alat bantu analisis, bukan saran finansial.")
