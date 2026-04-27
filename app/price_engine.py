# app/price_engine.py  —  yfinance with 5-min cache + graceful fallback
import time
import streamlit as st
import yfinance as yf
from app.data_loader import save_user_data


def _normalize(tk: str) -> str:
    """Yahoo Finance uses dashes not dots (e.g. BRK.B → BRK-B)."""
    return tk.replace(".", "-")


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_batch(tickers_tuple: tuple, _bucket: int) -> dict:
    """Download 1-day 1-min bars for all tickers in one call."""
    tickers = list(tickers_tuple)
    results: dict = {}
    try:
        raw = yf.download(
            tickers, period="1d", interval="1m",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True,
        )
        for tk in tickers:
            try:
                df = raw if len(tickers) == 1 else raw[tk]
                if df is None or df.empty:
                    raise ValueError
                last  = float(df["Close"].dropna().iloc[-1])
                open_ = float(df["Open"].dropna().iloc[0])
                chg   = (last - open_) / open_ * 100 if open_ else 0.0
                results[tk] = {"price": round(last, 2), "change_pct": round(chg, 2),
                                "ts": time.time()}
            except Exception:
                results[tk] = None
    except Exception:
        for tk in tickers:
            results[tk] = None

    # Enrich with 52wk range + market cap
    for tk in tickers:
        try:
            fi = yf.Ticker(tk).fast_info
            if results.get(tk):
                results[tk]["high52"]  = getattr(fi, "year_high", None)
                results[tk]["low52"]   = getattr(fi, "year_low",  None)
                results[tk]["mktcap"]  = getattr(fi, "market_cap", None)
        except Exception:
            pass
    return results


def get_prices(tickers: list) -> dict:
    """Return price dict; merges fresh fetch with session cache fallback.
    Normalises tickers for Yahoo Finance (dots → dashes) and re-maps back.
    """
    bucket  = int(time.time() // 300)
    # Build normalised → original mapping
    mapping = {_normalize(t): t for t in tickers}
    norm_tks = tuple(sorted(set(mapping.keys())))

    fresh_norm = _fetch_batch(norm_tks, bucket)
    # Re-map Yahoo-style keys back to original tickers
    fresh = {mapping.get(k, k): v for k, v in fresh_norm.items()}

    cache = st.session_state.price_cache
    for tk, val in fresh.items():
        if val:
            cache[tk] = val
        elif tk not in cache:
            cache[tk] = None
    st.session_state.price_cache = cache
    st.session_state.user_data["price_cache"] = cache
    save_user_data(st.session_state.user_data)
    return cache


@st.cache_data(ttl=300, show_spinner=False)
def fetch_single_macro(tickers_tuple: tuple, _bucket: int) -> dict:
    results = {}
    for tk in tickers_tuple:
        try:
            hist = yf.Ticker(tk).history(period="2d", interval="1d")
            if not hist.empty and len(hist) >= 2:
                last = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                results[tk] = {"price": round(float(last), 2),
                                "change_pct": round((last - prev) / prev * 100, 2)}
            elif not hist.empty:
                results[tk] = {"price": round(float(hist["Close"].iloc[-1]), 2),
                                "change_pct": 0.0}
            else:
                results[tk] = None
        except Exception:
            results[tk] = None
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_earnings(tickers_tuple: tuple) -> list[dict]:
    rows = []
    for tk in tickers_tuple:
        try:
            cal = yf.Ticker(tk).calendar
            if cal is not None and not cal.empty:
                for d in cal.columns.tolist()[:1]:
                    rows.append({"Ticker": tk, "Date": str(d)[:10]})
        except Exception:
            pass
    return rows
