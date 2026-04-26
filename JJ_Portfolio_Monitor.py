"""
JJ Portfolio Monitor — Main Entry Point
Bloomberg-terminal style investment dashboard powered by JJ Research Excel.

Run:  streamlit run JJ_Portfolio_Monitor.py
"""
import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────
st.set_page_config(
    page_title="JJ Portfolio Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Core imports ──────────────────────────────────────────────
import pandas as pd
from app import config as C
from app.styles import CSS
from app.data_loader import init_session, load_excel
from app.price_engine import get_prices

# ── Page modules ─────────────────────────────────────────────
from app.pages import (
    dashboard,
    stocks_watch,
    entry_tracker,
    screener,
    live_prices,
    watchlist,
    heatmap,
    portfolio,
    sectors,
    top10,
    rejected,
    market_pulse,
)


# ─────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)
init_session()

sheets   = load_excel()
df_main  = sheets.get("Executive Summary",     None)
df_rej   = sheets.get("Rejected S&P 500",      None)
df_sec   = sheets.get("Sector Verdict",        None)
df_top10 = sheets.get("Top 10 Conviction",     None)

if df_main is None:
    st.error("❌  Could not load SP500_Analysis.xlsx — place it in the project root.")
    st.stop()

# Cache df_top10 in session for use by stocks_watch
st.session_state["_df_top10"] = df_top10 if df_top10 is not None else pd.DataFrame()

# Live prices for all tickers in main sheet
tickers = df_main["Ticker"].dropna().tolist()
prices  = get_prices(tickers)


# ─────────────────────────────────────────────────────────────
# Sidebar navigation
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo / branding
    st.markdown(
        f'<div style="padding:20px 16px 14px;border-bottom:1px solid {C.BORDER};">'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.05rem;'
        f'font-weight:700;color:{C.GREEN};letter-spacing:1px">JJ PORTFOLIO</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
        f'color:{C.TEXT3};letter-spacing:2px;margin-top:2px">MONITOR v2.0</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Nav buttons
    for icon, name in C.PAGES:
        active = st.session_state.page == name
        if st.button(
            f"{icon}  {name}",
            key=f"nav_{name}",
            use_container_width=True,
        ):
            st.session_state.page = name
            st.session_state.selected_stock = None
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # Live status strip
    ud   = st.session_state.user_data
    port = ud.get("portfolio", {})
    wl   = ud.get("watchlist",  {})
    ep   = ud.get("entry_prices", {})

    st.markdown(
        f'<div style="padding:12px 8px">'
        f'<div style="display:flex;align-items:center;margin-bottom:12px">'
        f'<div class="live-dot"></div>'
        f'<span style="font-size:0.65rem;color:{C.GREEN};font-weight:600;'
        f'letter-spacing:1px">LIVE PRICES ON</span></div>'
        f'<div style="font-size:0.65rem;color:{C.TEXT3};line-height:2">'
        f'Universe: <b style="color:{C.TEXT}">{len(tickers)}</b> stocks<br>'
        f'Portfolio: <b style="color:{C.TEXT}">{len(port)}</b> positions<br>'
        f'Watchlist: <b style="color:{C.TEXT}">{len(wl)}</b> alerts<br>'
        f'Tracked: <b style="color:{C.TEXT}">{len(ep)}</b> entries'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:0.6rem;color:{C.TEXT3};padding:0 8px 16px;line-height:1.8">'
        f'Data: JJ Research Excel<br>'
        f'Prices: yfinance (5-min cache)<br>'
        f'© 2025 JJ Research</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Page routing
# ─────────────────────────────────────────────────────────────
page = st.session_state.page

if page == "Dashboard":
    dashboard.render(df_main, df_top10, prices)

elif page == "Stocks to Watch":
    stocks_watch.render(df_main, prices)

elif page == "Entry Tracker":
    entry_tracker.render(df_main, prices)

elif page == "Screener":
    screener.render(df_main, prices)

elif page == "Live Prices":
    live_prices.render(df_main, prices)

elif page == "Watchlist":
    watchlist.render(df_main, prices)

elif page == "Heat Map":
    heatmap.render(df_main, prices)

elif page == "Portfolio":
    portfolio.render(df_main, prices)

elif page == "Sectors":
    if df_sec is not None:
        sectors.render(df_sec)
    else:
        st.error("Sector Verdict sheet not found in Excel.")

elif page == "Top 10":
    if df_top10 is not None:
        top10.render(df_top10, df_main, prices)
    else:
        st.error("Top 10 Conviction sheet not found in Excel.")

elif page == "Rejected":
    if df_rej is not None:
        rejected.render(df_rej, prices)
    else:
        st.error("Rejected S&P 500 sheet not found in Excel.")

elif page == "Market Pulse":
    market_pulse.render(df_main)

else:
    st.error(f"Unknown page: {page}")
