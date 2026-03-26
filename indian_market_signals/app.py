import streamlit as st
import yfinance as yf
import numpy as np
import requests
from datetime import datetime, timedelta
import pytz
import pandas as pd

st.set_page_config(layout="wide")

# ---------- TIME ----------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.now(ist)
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

# ---------- FUNCTIONS ----------

def get_live_change(ticker):
    """Get session % change vs previous close"""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info

        last_price = info.get("lastPrice")
        prev_close = info.get("previousClose")

        if not last_price or not prev_close:
            return None

        return round(((last_price - prev_close) / prev_close) * 100, 2)
    except:
        return None

def fetch_nse_pre_market():
    """
    Fetch NSE pre-market data and return:
    - df: DataFrame with symbols and changes
    - data_date: actual date of NSE pre-market data downloaded
    """
    try:
        url = "https://www.nseindia.com/api/market-data-pre-open?key=NIFTY"
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        response = session.get(url, headers=headers)
        if response.status_code != 200:
            return None, None

        payload = response.json()
        data = payload.get("data", []) if isinstance(payload, dict) else []
        records = []
        for item in data:
            meta = item.get("metadata", {})
            price = meta.get("lastPrice", 0)
            prev = meta.get("previousClose", 0)
            symbol = meta.get("symbol", "")
            if prev == 0:
                continue
            change = ((price - prev) / prev) * 100
            records.append({"symbol": symbol, "change": change})

        df = pd.DataFrame(records)

        # Determine actual data date from NSE payload / metadata (preferred)
        data_date = None
        # check common top-level fields
        if isinstance(payload, dict):
            for key in ("tradingDate", "date", "timeStamp", "timestamp", "lastUpdate", "updatedOn"):
                v = payload.get(key)
                if v:
                    try:
                        dt = pd.to_datetime(v, errors="coerce")
                        if pd.notna(dt):
                            data_date = dt.strftime("%Y-%m-%d")
                            break
                    except Exception:
                        continue

        # if not found, check per-item metadata for a date field and pick the latest
        if data_date is None and not df.empty:
            candidates = []
            for item in data:
                meta = item.get("metadata", {}) or {}
                for k in ("date", "tradingDate", "timeStamp", "timestamp", "ltpDate", "lastUpdate", "updatedOn"):
                    v = meta.get(k)
                    if v:
                        try:
                            dt = pd.to_datetime(v, errors="coerce")
                            if pd.notna(dt):
                                candidates.append(dt)
                        except Exception:
                            continue
            if candidates:
                data_date = max(candidates).strftime("%Y-%m-%d")

        # Fallback: if we still don't have a data_date, fall back to previous day when df empty,
        # otherwise assume today's date (best-effort)
        if data_date is None:
            if df.empty:
                data_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                data_date = now.strftime("%Y-%m-%d")

        return df, data_date
    except:
        return None, None

def signal(val):
    if val > 0.4:
        return "BUY"
    elif val < -0.4:
        return "SELL"
    return "NEUTRAL"

def color(val):
    if val is None:
        return "NA"
    if val > 0:
        return f"<span style='color:green'>{val:.2f}%</span>"
    elif val < 0:
        return f"<span style='color:red'>{val:.2f}%</span>"
    return f"{val:.2f}%"

# ---------- FETCH GLOBAL DATA ----------
dow = get_live_change("^DJI") or 0
sp = get_live_change("^GSPC") or 0
nasdaq = get_live_change("^IXIC") or 0
vix = get_live_change("^VIX") or 0
gift = get_live_change("^NSEI") or 0

global_score = round(
    dow*0.2 + sp*0.4 + nasdaq*0.3 - vix*0.1 + gift*0.2,
    2
)
stage1_signal = signal(global_score)

# ---------- FETCH NSE PRE-MARKET ----------
df, data_date = fetch_nse_pre_market()
pre_market_pred = None
confidence = 0

if df is not None and not df.empty:
    # Approx Nifty weights
    weights = {
        "RELIANCE": 0.10,
        "HDFCBANK": 0.09,
        "ICICIBANK": 0.08,
        "INFY": 0.06,
        "TCS": 0.05,
        "LT": 0.04,
        "SBIN": 0.03
    }
    df["weight"] = df["symbol"].map(weights).fillna(0.01)
    df["weighted"] = df["change"] * df["weight"]
    pre_market_pred = round(df["weighted"].sum(), 2)

    # Confidence score (breadth + magnitude + alignment)
    positive = (df["change"] > 0).sum()
    negative = (df["change"] < 0).sum()
    total = len(df)
    breadth = max(positive, negative) / total
    magnitude = min(abs(pre_market_pred) / 1.0, 1)
    alignment = 1 if signal(pre_market_pred) == stage1_signal else 0.5
    confidence = round((breadth * 0.4 + magnitude * 0.4 + alignment * 0.2) * 100, 1)

# ---------- FINAL PREDICTION ----------
if pre_market_pred is not None:
    final_pred = round((global_score*0.5 + pre_market_pred*0.5), 2)
else:
    final_pred = global_score
final_signal = signal(final_pred)

# ---------- UI ----------
st.title("📊 Nifty Open Prediction Engine")
st.markdown(f"Last updated: {timestamp}")

# Global indicators
c1, c2, c3, c4, c5 = st.columns(5)
c1.markdown(f"Dow<br>{color(dow)}", unsafe_allow_html=True)
c2.markdown(f"S&P 500<br>{color(sp)}", unsafe_allow_html=True)
c3.markdown(f"Nasdaq<br>{color(nasdaq)}", unsafe_allow_html=True)
c4.markdown(f"VIX<br>{color(vix)}", unsafe_allow_html=True)
c5.markdown(f"GIFT Proxy<br>{color(gift)}", unsafe_allow_html=True)

st.markdown("---")
st.subheader("🌍 Stage 1: Global")
st.markdown(f"Prediction: {color(global_score)}", unsafe_allow_html=True)
st.markdown(f"Signal: {stage1_signal}")

st.markdown("---")
st.subheader(f"🇮🇳 Stage 2: Pre-Market (Data from: {data_date})")

if pre_market_pred is not None:
    st.markdown(f"Prediction: {color(pre_market_pred)}", unsafe_allow_html=True)
    st.markdown(f"Confidence: **{confidence}%**")

    st.markdown("### Top Movers")
    top_pos = df.sort_values("change", ascending=False).head(5)
    top_neg = df.sort_values("change").head(5)
    st.write("Top Gainers", top_pos[["symbol", "change"]])
    st.write("Top Losers", top_neg[["symbol", "change"]])
else:
    st.warning("Pre-market data not available yet")

st.markdown("---")
st.subheader("🎯 Final Prediction")
st.markdown(f"{color(final_pred)}", unsafe_allow_html=True)
st.markdown(f"### 🚦 {final_signal}")