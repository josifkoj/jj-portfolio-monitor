# app/pages/analyzer.py — Market-standard stock research workspace
# Layout patterned after Yahoo Finance / Stock Analysis: stripped header,
# dense stats, period-selectable chart, and standard sub-tabs:
#     Summary · Statistics · Financials · Analysis · Holders · News
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timezone

from app import config as C
from app.styles import section_title


# ═════════════════════════════════════════════════════════════
# DATA LAYER (cached)
# ═════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        if not (info.get("currentPrice") or info.get("regularMarketPrice")):
            return {}
        return info
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_history(ticker: str, period: str) -> pd.DataFrame:
    try:
        return yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_financials(ticker: str) -> dict:
    out = {"is_y": pd.DataFrame(), "is_q": pd.DataFrame(),
           "bs_y": pd.DataFrame(), "bs_q": pd.DataFrame(),
           "cf_y": pd.DataFrame(), "cf_q": pd.DataFrame()}
    try:
        t = yf.Ticker(ticker)
        for k, fn in [
            ("is_y", lambda: t.financials),
            ("is_q", lambda: t.quarterly_financials),
            ("bs_y", lambda: t.balance_sheet),
            ("bs_q", lambda: t.quarterly_balance_sheet),
            ("cf_y", lambda: t.cashflow),
            ("cf_q", lambda: t.quarterly_cashflow),
        ]:
            try: out[k] = fn()
            except Exception: pass
    except Exception:
        pass
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_extras(ticker: str) -> dict:
    out = {"news": [], "recs": pd.DataFrame(),
           "earnings": pd.DataFrame(), "dividends": pd.Series(dtype=float),
           "major": pd.DataFrame(), "inst": pd.DataFrame()}
    try:
        t = yf.Ticker(ticker)
        try: out["news"]      = t.news or []
        except Exception: pass
        try: out["recs"]      = t.recommendations
        except Exception: pass
        try: out["earnings"]  = t.get_earnings_dates(limit=12)
        except Exception: pass
        try: out["dividends"] = t.dividends
        except Exception: pass
        try: out["major"]     = t.major_holders
        except Exception: pass
        try: out["inst"]      = t.institutional_holders
        except Exception: pass
    except Exception:
        pass
    return out


# ═════════════════════════════════════════════════════════════
# FORMATTING
# ═════════════════════════════════════════════════════════════

def _fmt_money(v):
    if v is None or pd.isna(v): return "—"
    try:
        v = float(v)
        sign = "-" if v < 0 else ""
        v = abs(v)
        if v >= 1e12: return f"{sign}${v/1e12:.2f}T"
        if v >= 1e9:  return f"{sign}${v/1e9:.2f}B"
        if v >= 1e6:  return f"{sign}${v/1e6:.1f}M"
        if v >= 1e3:  return f"{sign}${v/1e3:.1f}K"
        return f"{sign}${v:,.2f}"
    except Exception:
        return "—"


def _fmt_num(v, decimals=2, suffix=""):
    if v is None or pd.isna(v): return "—"
    try:
        return f"{float(v):,.{decimals}f}{suffix}"
    except Exception:
        return "—"


def _fmt_pct(v, decimals=2, sign=False):
    if v is None or pd.isna(v): return "—"
    try:
        v = float(v)
        return (f"{v:+.{decimals}f}%" if sign else f"{v:.{decimals}f}%")
    except Exception:
        return "—"


def _fmt_price(v):
    if v is None or pd.isna(v): return "—"
    try:
        v = float(v)
        if v >= 10_000: return f"${v:,.0f}"
        if v >= 1_000:  return f"${v:,.1f}"
        return f"${v:,.2f}"
    except Exception:
        return "—"


def _fmt_int(v):
    if v is None or pd.isna(v): return "—"
    try: return f"{int(v):,}"
    except Exception: return "—"


def _fmt_date(v):
    if v is None or pd.isna(v): return "—"
    try: return pd.to_datetime(v).strftime("%b %d, %Y")
    except Exception: return "—"


# ═════════════════════════════════════════════════════════════
# STYLING / TABLES
# ═════════════════════════════════════════════════════════════

def _stat_table(rows: list[tuple[str, str]]) -> str:
    """Two-column key/value table — the dominant layout pattern in
    market-standard research tools."""
    body = ""
    for label, value in rows:
        body += (
            f'<tr style="border-bottom:1px solid {C.BORDER}">'
            f'<td style="padding:9px 14px;font-size:0.78rem;color:{C.TEXT2};'
            f'width:60%">{label}</td>'
            f'<td style="padding:9px 14px;font-size:0.8rem;color:{C.TEXT};'
            f'font-family:\'JetBrains Mono\',monospace;font-weight:600;'
            f'text-align:right">{value}</td>'
            f'</tr>'
        )
    return (
        f'<table style="width:100%;border-collapse:collapse;'
        f'background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:8px;overflow:hidden">{body}</table>'
    )


def _section_label(text: str, accent: str = None) -> str:
    accent = accent or C.TEXT2
    return (
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.7rem;'
        f'font-weight:700;color:{accent};text-transform:uppercase;'
        f'letter-spacing:1.6px;margin:18px 0 10px">{text}</div>'
    )


def _financial_table(df: pd.DataFrame, rows: list[tuple[str, list[str]]],
                     n_periods: int = 4) -> str:
    """Render a financial-statement style table.
    rows = [(display_label, [yfinance_index_aliases]), ...]
    """
    if df is None or df.empty:
        return (f'<div style="padding:20px;text-align:center;color:{C.TEXT3};'
                f'background:{C.SURFACE};border:1px solid {C.BORDER};'
                f'border-radius:8px">No data available.</div>')

    cols = list(df.columns)[:n_periods]
    headers = "".join(
        f'<th style="padding:8px 12px;font-size:0.66rem;color:{C.TEXT3};'
        f'text-align:right;text-transform:uppercase;letter-spacing:1px;'
        f'font-weight:700;border-bottom:1px solid {C.BORDER2}">'
        f'{pd.to_datetime(c).strftime("%b %Y") if not pd.isna(c) else "—"}</th>'
        for c in cols
    )
    body = ""
    for label, aliases in rows:
        val = None
        for a in aliases:
            if a in df.index:
                val = df.loc[a]
                break
        if val is None:
            cells = "".join(
                f'<td style="padding:8px 12px;font-size:0.78rem;text-align:right;'
                f'color:{C.TEXT3};font-family:\'JetBrains Mono\',monospace">—</td>'
                for _ in cols
            )
        else:
            cells = ""
            for c in cols:
                v = val.get(c)
                cells += (
                    f'<td style="padding:8px 12px;font-size:0.78rem;text-align:right;'
                    f'color:{C.TEXT};font-family:\'JetBrains Mono\',monospace;'
                    f'font-weight:600">{_fmt_money(v)}</td>'
                )
        body += (
            f'<tr style="border-bottom:1px solid {C.BORDER}">'
            f'<td style="padding:8px 14px;font-size:0.78rem;color:{C.TEXT2}">{label}</td>'
            f'{cells}</tr>'
        )

    return (
        f'<table style="width:100%;border-collapse:collapse;'
        f'background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:8px;overflow:hidden">'
        f'<thead><tr><th style="padding:8px 14px;font-size:0.66rem;'
        f'color:{C.TEXT3};text-align:left;text-transform:uppercase;'
        f'letter-spacing:1px;font-weight:700;border-bottom:1px solid {C.BORDER2}">'
        f'Item</th>{headers}</tr></thead>'
        f'<tbody>{body}</tbody></table>'
    )


# ═════════════════════════════════════════════════════════════
# CHART
# ═════════════════════════════════════════════════════════════

PERIOD_MAP = {
    "1D": "1d", "5D": "5d", "1M": "1mo", "6M": "6mo",
    "YTD": "ytd", "1Y": "1y", "5Y": "5y", "Max": "max",
}


def _price_chart(hist: pd.DataFrame, period_label: str,
                 fv: float = None, analyst: float = None) -> go.Figure:
    fig = go.Figure()
    if hist is None or hist.empty:
        return fig

    open_p = hist["Close"].iloc[0]
    last_p = hist["Close"].iloc[-1]
    line_col = C.GREEN if last_p >= open_p else C.RED
    fill_alpha = 0.08

    # Volume
    if "Volume" in hist.columns and period_label not in ("1D",):
        fig.add_trace(go.Bar(
            x=hist.index, y=hist["Volume"],
            marker_color=C.BORDER2, opacity=0.4,
            yaxis="y2", showlegend=False, name="Volume",
            hoverinfo="skip",
        ))

    fig.add_trace(go.Scatter(
        x=hist.index, y=hist["Close"], mode="lines",
        line=dict(color=line_col, width=2),
        fill="tozeroy",
        fillcolor=f"rgba({int(line_col[1:3],16)},{int(line_col[3:5],16)},"
                  f"{int(line_col[5:7],16)},{fill_alpha})",
        name="Price",
        hovertemplate="<b>%{x|%b %d %Y · %H:%M}</b><br>$%{y:.2f}<extra></extra>",
    ))

    if fv and period_label in ("1Y", "5Y", "Max", "6M"):
        fig.add_hline(y=fv, line_dash="dash", line_color=C.GOLD, line_width=1.2,
                      annotation_text=f"  Intrinsic ${fv:.0f}",
                      annotation_font_color=C.GOLD, annotation_font_size=10)
    if analyst and period_label in ("1Y", "5Y", "Max", "6M"):
        fig.add_hline(y=analyst, line_dash="dot", line_color=C.BLUE, line_width=1.2,
                      annotation_text=f"  Analyst ${analyst:.0f}",
                      annotation_font_color=C.BLUE, annotation_font_size=10)

    y_min = hist["Close"].min() * 0.98
    y_max = hist["Close"].max() * 1.02
    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=380,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(gridcolor=C.BORDER, showspikes=True, spikecolor=C.BORDER2),
        yaxis=dict(title=None, gridcolor=C.BORDER, tickprefix="$",
                   showspikes=True, spikecolor=C.BORDER2,
                   range=[y_min, y_max]),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    showticklabels=False,
                    range=[0, hist["Volume"].max() * 6]
                    if "Volume" in hist.columns else [0, 1]),
        showlegend=False, hovermode="x unified",
        hoverlabel=dict(bgcolor=C.SURFACE, bordercolor=line_col,
                        font=dict(family="JetBrains Mono", size=11)),
    )
    return fig


# ═════════════════════════════════════════════════════════════
# INTRINSIC VALUE (kept lightweight, used in stats)
# ═════════════════════════════════════════════════════════════

def _intrinsic_value(fwd_eps, growth_pct):
    if not fwd_eps or fwd_eps <= 0:
        return None, None
    if growth_pct is None or growth_pct <= 0:
        m = 13.0
    elif growth_pct >= 30:
        m = min(growth_pct * 1.4, 50)
    elif growth_pct >= 15:
        m = growth_pct * 1.8
    else:
        m = max(growth_pct * 2.2, 12)
    return round(fwd_eps * m, 2), round(m, 1)


# ═════════════════════════════════════════════════════════════
# MAIN RENDER
# ═════════════════════════════════════════════════════════════

def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("🔬  Stock Research"), unsafe_allow_html=True)

    # ── Search ─────────────────────────────────────────────
    sc1, sc2 = st.columns([6, 1])
    raw = sc1.text_input(
        "", placeholder="Search ticker  ·  AAPL  MSFT  NVDA  GOOGL  BRK-B",
        key="research_input", label_visibility="collapsed",
    )
    go_btn = sc2.button("Search", use_container_width=True,
                        key="research_go", type="primary")

    ticker = raw.strip().upper()
    if go_btn and ticker:
        st.session_state["research_tk"] = ticker
    if not ticker and "research_tk" in st.session_state:
        ticker = st.session_state["research_tk"]

    if not ticker:
        _empty_state()
        return

    with st.spinner(f"Loading {ticker}…"):
        info = _fetch_info(ticker)
    if not info:
        st.error(f"❌  Could not fetch data for **{ticker}**.")
        return

    # ── HEADER STRIP (Yahoo-style) ─────────────────────────
    _render_header(ticker, info)

    # ── QUICK STATS RIBBON ─────────────────────────────────
    _render_quick_ribbon(info)

    # ── TABS ───────────────────────────────────────────────
    t_sum, t_stats, t_fin, t_anl, t_hold, t_news = st.tabs([
        "Summary", "Statistics", "Financials",
        "Analysis", "Holders", "News",
    ])

    with t_sum:    _tab_summary(ticker, info, df_main)
    with t_stats:  _tab_statistics(info)
    with t_fin:    _tab_financials(ticker)
    with t_anl:    _tab_analysis(ticker, info)
    with t_hold:   _tab_holders(ticker, info)
    with t_news:   _tab_news(ticker)


# ═════════════════════════════════════════════════════════════
# HEADER
# ═════════════════════════════════════════════════════════════

def _render_header(ticker, info):
    cur     = info.get("currentPrice") or info.get("regularMarketPrice")
    prev    = info.get("previousClose") or info.get("regularMarketPreviousClose")
    chg     = (cur - prev) if (cur and prev) else None
    chg_pct = (chg / prev * 100) if (chg is not None and prev) else None
    chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
    arrow   = "▲" if (chg or 0) >= 0 else "▼"
    name    = info.get("shortName") or info.get("longName") or ticker
    exch    = info.get("fullExchangeName") or info.get("exchange", "")
    cur_iso = info.get("currency", "USD")

    market_state = info.get("marketState", "")
    state_dot_col = C.GREEN if market_state == "REGULAR" else C.GOLD

    st.markdown(
        f'<div style="border-bottom:1px solid {C.BORDER};padding:14px 4px 18px;'
        f'margin-bottom:14px">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap">'
        # left: name & ticker
        f'<div>'
        f'<div style="font-size:0.7rem;color:{C.TEXT3};margin-bottom:4px;'
        f'letter-spacing:1px">{exch}</div>'
        f'<div style="font-size:1.35rem;font-weight:700;color:{C.TEXT};margin-bottom:2px">'
        f'{name} <span style="font-family:\'JetBrains Mono\',monospace;'
        f'color:{C.TEXT3};font-weight:500;font-size:1rem">({ticker})</span></div>'
        f'<div style="display:flex;align-items:center;gap:6px;font-size:0.7rem;color:{C.TEXT3}">'
        f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
        f'background:{state_dot_col};box-shadow:0 0 6px {state_dot_col}">'
        f'</span>{market_state or "—"}'
        f'  ·  Currency {cur_iso}'
        f'</div></div>'
        # right: price block
        f'<div style="text-align:right">'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2.4rem;'
        f'font-weight:700;color:{C.TEXT};line-height:1">'
        f'{_fmt_price(cur)}</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.95rem;'
        f'color:{chg_col};font-weight:600;margin-top:4px">'
        f'{arrow} {_fmt_num(abs(chg) if chg is not None else None)} '
        f'({_fmt_pct(chg_pct, 2, sign=True) if chg_pct is not None else "—"})</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# QUICK STATS RIBBON
# ═════════════════════════════════════════════════════════════

def _render_quick_ribbon(info):
    cur    = info.get("currentPrice") or info.get("regularMarketPrice")
    open_p = info.get("regularMarketOpen")
    day_lo = info.get("dayLow")
    day_hi = info.get("dayHigh")
    lo52   = info.get("fiftyTwoWeekLow")
    hi52   = info.get("fiftyTwoWeekHigh")
    vol    = info.get("regularMarketVolume") or info.get("volume")
    avg_vol = info.get("averageVolume")
    mc     = info.get("marketCap")
    pe     = info.get("trailingPE")
    eps    = info.get("trailingEps")
    div    = info.get("dividendYield")

    cells = [
        ("Open",        _fmt_price(open_p)),
        ("Day Range",   f"{_fmt_price(day_lo)} – {_fmt_price(day_hi)}" if day_lo and day_hi else "—"),
        ("52W Range",   f"{_fmt_price(lo52)} – {_fmt_price(hi52)}" if lo52 and hi52 else "—"),
        ("Volume",      f"{vol/1e6:.2f}M" if vol else "—"),
        ("Avg Volume",  f"{avg_vol/1e6:.2f}M" if avg_vol else "—"),
        ("Market Cap",  _fmt_money(mc)),
        ("P/E (TTM)",   _fmt_num(pe, 2)),
        ("EPS (TTM)",   _fmt_price(eps)),
        ("Div Yield",   _fmt_pct(div*100) if div else "—"),
    ]
    cell_html = "".join(
        f'<div style="flex:1;min-width:130px;padding:10px 14px;'
        f'border-right:1px solid {C.BORDER}">'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.2px;font-weight:600;margin-bottom:3px">{l}</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.85rem;'
        f'color:{C.TEXT};font-weight:600">{v}</div>'
        f'</div>'
        for l, v in cells
    )
    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:8px;display:flex;flex-wrap:wrap;overflow:hidden;'
        f'margin-bottom:18px">{cell_html}</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# TAB · SUMMARY
# ═════════════════════════════════════════════════════════════

def _tab_summary(ticker, info, df_main):
    # Period picker for chart
    periods = list(PERIOD_MAP.keys())
    if "summary_period" not in st.session_state:
        st.session_state.summary_period = "1Y"

    period_cols = st.columns(len(periods) + 1)
    for i, p in enumerate(periods):
        active = st.session_state.summary_period == p
        if period_cols[i].button(p, key=f"per_{p}",
                                 use_container_width=True,
                                 type="primary" if active else "secondary"):
            st.session_state.summary_period = p
            st.rerun()

    period = st.session_state.summary_period
    hist = _fetch_history(ticker, PERIOD_MAP[period])

    # Compute intrinsic for chart overlays
    cur     = info.get("currentPrice") or info.get("regularMarketPrice")
    fwd_eps = info.get("forwardEps")
    eps_g   = info.get("earningsGrowth")
    rev_g   = info.get("revenueGrowth")
    growth  = (eps_g or rev_g)
    growth_pct = round(growth*100, 1) if growth is not None else None
    intrinsic, _m = _intrinsic_value(fwd_eps, growth_pct)
    analyst_tgt = info.get("targetMeanPrice")

    st.plotly_chart(_price_chart(hist, period, intrinsic, analyst_tgt),
                    use_container_width=True)

    # Two-column layout — left: key stats; right: valuation snapshot
    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown(_section_label("Key Statistics"), unsafe_allow_html=True)
        rows = [
            ("Previous Close", _fmt_price(info.get("previousClose"))),
            ("Open",           _fmt_price(info.get("regularMarketOpen"))),
            ("Bid",            f"{_fmt_price(info.get('bid'))} × {_fmt_int(info.get('bidSize'))}"
                               if info.get("bid") else "—"),
            ("Ask",            f"{_fmt_price(info.get('ask'))} × {_fmt_int(info.get('askSize'))}"
                               if info.get("ask") else "—"),
            ("Day's Range",    f"{_fmt_price(info.get('dayLow'))} – {_fmt_price(info.get('dayHigh'))}"
                               if info.get("dayLow") else "—"),
            ("52 Week Range",  f"{_fmt_price(info.get('fiftyTwoWeekLow'))} – "
                               f"{_fmt_price(info.get('fiftyTwoWeekHigh'))}"
                               if info.get("fiftyTwoWeekLow") else "—"),
            ("Volume",         _fmt_int(info.get("regularMarketVolume") or info.get("volume"))),
            ("Avg. Volume",    _fmt_int(info.get("averageVolume"))),
            ("Beta (5Y)",      _fmt_num(info.get("beta"), 2)),
        ]
        st.markdown(_stat_table(rows), unsafe_allow_html=True)

    with col_r:
        st.markdown(_section_label("Valuation"), unsafe_allow_html=True)
        analyst_up = (round((analyst_tgt - cur) / cur * 100, 1)
                      if (analyst_tgt and cur) else None)
        upside_model = (round((intrinsic - cur) / cur * 100, 1)
                        if (intrinsic and cur) else None)
        if upside_model is not None and analyst_up is not None:
            combined = round((upside_model + analyst_up) / 2, 1)
        else:
            combined = upside_model if upside_model is not None else analyst_up

        if combined is None:
            up_str = "—"
        else:
            col = C.GREEN if combined >= 0 else C.RED
            label = "UNDERVALUED" if combined >= 0 else "OVERVALUED"
            sign = "+" if combined >= 0 else ""
            up_str = (f'<span style="color:{col};font-weight:700">'
                      f'{sign}{combined:.1f}% · {label}</span>')

        rows = [
            ("Market Cap",         _fmt_money(info.get("marketCap"))),
            ("Enterprise Value",   _fmt_money(info.get("enterpriseValue"))),
            ("Trailing P/E",       _fmt_num(info.get("trailingPE"), 2)),
            ("Forward P/E",        _fmt_num(info.get("forwardPE"), 2)),
            ("PEG Ratio",          _fmt_num(info.get("trailingPegRatio") or info.get("pegRatio"), 2)),
            ("Price / Sales",      _fmt_num(info.get("priceToSalesTrailingTwelveMonths"), 2)),
            ("Price / Book",       _fmt_num(info.get("priceToBook"), 2)),
            ("EV / Revenue",       _fmt_num(info.get("enterpriseToRevenue"), 2)),
            ("EV / EBITDA",        _fmt_num(info.get("enterpriseToEbitda"), 2)),
            ("Intrinsic Value",    _fmt_price(intrinsic)),
            ("Analyst Target",     _fmt_price(analyst_tgt)),
            ("Combined Upside",    up_str),
        ]
        st.markdown(_stat_table(rows), unsafe_allow_html=True)

    # Profile / description
    desc = info.get("longBusinessSummary")
    if desc:
        st.markdown(_section_label("About"), unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:14px 18px;font-size:0.83rem;'
            f'color:{C.TEXT2};line-height:1.75">{desc[:1200]}'
            + ("…" if len(desc) > 1200 else "")
            + f'</div>',
            unsafe_allow_html=True,
        )

    # Profile facts
    profile_rows = [
        ("Sector",           info.get("sector") or "—"),
        ("Industry",         info.get("industry") or "—"),
        ("Country",          info.get("country") or "—"),
        ("Full-Time Employees",
         _fmt_int(info.get("fullTimeEmployees")) if info.get("fullTimeEmployees") else "—"),
        ("Website",          info.get("website") or "—"),
    ]
    st.markdown(_stat_table(profile_rows), unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · STATISTICS
# ═════════════════════════════════════════════════════════════

def _tab_statistics(info):
    c1, c2 = st.columns(2)

    with c1:
        st.markdown(_section_label("Valuation Measures"),
                    unsafe_allow_html=True)
        st.markdown(_stat_table([
            ("Market Cap",            _fmt_money(info.get("marketCap"))),
            ("Enterprise Value",      _fmt_money(info.get("enterpriseValue"))),
            ("Trailing P/E",          _fmt_num(info.get("trailingPE"), 2)),
            ("Forward P/E",           _fmt_num(info.get("forwardPE"), 2)),
            ("PEG Ratio (5Y)",        _fmt_num(info.get("trailingPegRatio") or info.get("pegRatio"), 2)),
            ("Price / Sales (TTM)",   _fmt_num(info.get("priceToSalesTrailingTwelveMonths"), 2)),
            ("Price / Book",          _fmt_num(info.get("priceToBook"), 2)),
            ("EV / Revenue",          _fmt_num(info.get("enterpriseToRevenue"), 2)),
            ("EV / EBITDA",           _fmt_num(info.get("enterpriseToEbitda"), 2)),
        ]), unsafe_allow_html=True)

        st.markdown(_section_label("Profitability"), unsafe_allow_html=True)
        gm = info.get("grossMargins"); om = info.get("operatingMargins")
        nm = info.get("profitMargins")
        st.markdown(_stat_table([
            ("Gross Margin",      _fmt_pct(gm*100) if gm is not None else "—"),
            ("Operating Margin",  _fmt_pct(om*100) if om is not None else "—"),
            ("Profit Margin",     _fmt_pct(nm*100) if nm is not None else "—"),
            ("Return on Assets",  _fmt_pct((info.get("returnOnAssets") or 0)*100)
                                  if info.get("returnOnAssets") else "—"),
            ("Return on Equity",  _fmt_pct((info.get("returnOnEquity") or 0)*100)
                                  if info.get("returnOnEquity") else "—"),
        ]), unsafe_allow_html=True)

        st.markdown(_section_label("Income Statement"), unsafe_allow_html=True)
        st.markdown(_stat_table([
            ("Revenue (TTM)",       _fmt_money(info.get("totalRevenue"))),
            ("Revenue Per Share",   _fmt_price(info.get("revenuePerShare"))),
            ("Quarterly Rev Growth (YoY)",
             _fmt_pct((info.get("revenueGrowth") or 0)*100, sign=True)
             if info.get("revenueGrowth") is not None else "—"),
            ("Gross Profit (TTM)",  _fmt_money(info.get("grossProfits"))),
            ("EBITDA",              _fmt_money(info.get("ebitda"))),
            ("Net Income (TTM)",    _fmt_money(info.get("netIncomeToCommon"))),
            ("Diluted EPS (TTM)",   _fmt_price(info.get("trailingEps"))),
            ("Quarterly EPS Growth (YoY)",
             _fmt_pct((info.get("earningsGrowth") or 0)*100, sign=True)
             if info.get("earningsGrowth") is not None else "—"),
        ]), unsafe_allow_html=True)

    with c2:
        st.markdown(_section_label("Balance Sheet"), unsafe_allow_html=True)
        de = info.get("debtToEquity")
        st.markdown(_stat_table([
            ("Total Cash",            _fmt_money(info.get("totalCash"))),
            ("Total Cash Per Share",  _fmt_price(info.get("totalCashPerShare"))),
            ("Total Debt",            _fmt_money(info.get("totalDebt"))),
            ("Total Debt / Equity",   _fmt_num(de/100, 2) + "x" if de else "—"),
            ("Current Ratio",         _fmt_num(info.get("currentRatio"), 2) + "x"
                                      if info.get("currentRatio") else "—"),
            ("Quick Ratio",           _fmt_num(info.get("quickRatio"), 2) + "x"
                                      if info.get("quickRatio") else "—"),
            ("Book Value Per Share",  _fmt_price(info.get("bookValue"))),
        ]), unsafe_allow_html=True)

        st.markdown(_section_label("Cash Flow"), unsafe_allow_html=True)
        st.markdown(_stat_table([
            ("Operating Cash Flow (TTM)", _fmt_money(info.get("operatingCashflow"))),
            ("Levered Free Cash Flow",    _fmt_money(info.get("freeCashflow"))),
        ]), unsafe_allow_html=True)

        st.markdown(_section_label("Dividends & Splits"), unsafe_allow_html=True)
        dy   = info.get("dividendYield")
        dr   = info.get("dividendRate")
        pr   = info.get("payoutRatio")
        ex   = info.get("exDividendDate")
        st.markdown(_stat_table([
            ("Forward Dividend Rate",  _fmt_price(dr) if dr else "—"),
            ("Forward Yield",          _fmt_pct(dy*100) if dy else "—"),
            ("5Y Avg Dividend Yield",  _fmt_pct(info.get("fiveYearAvgDividendYield"))
                                       if info.get("fiveYearAvgDividendYield") else "—"),
            ("Payout Ratio",           _fmt_pct(pr*100) if pr else "—"),
            ("Ex-Dividend Date",
             pd.to_datetime(ex, unit="s").strftime("%b %d, %Y") if ex else "—"),
            ("Last Split",             info.get("lastSplitFactor") or "—"),
        ]), unsafe_allow_html=True)

        st.markdown(_section_label("Stock Price History"), unsafe_allow_html=True)
        beta = info.get("beta")
        s52  = info.get("52WeekChange")
        sp52 = info.get("SandP52WeekChange")
        st.markdown(_stat_table([
            ("Beta (5Y)",                _fmt_num(beta, 2)),
            ("52-Week Change",           _fmt_pct(s52*100, sign=True) if s52 else "—"),
            ("S&P 500 52-Week Change",   _fmt_pct(sp52*100, sign=True) if sp52 else "—"),
            ("52 Week High",             _fmt_price(info.get("fiftyTwoWeekHigh"))),
            ("52 Week Low",              _fmt_price(info.get("fiftyTwoWeekLow"))),
            ("50-Day Moving Avg",        _fmt_price(info.get("fiftyDayAverage"))),
            ("200-Day Moving Avg",       _fmt_price(info.get("twoHundredDayAverage"))),
        ]), unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · FINANCIALS
# ═════════════════════════════════════════════════════════════

INCOME_ROWS = [
    ("Total Revenue",            ["Total Revenue", "TotalRevenue"]),
    ("Cost of Revenue",          ["Cost Of Revenue", "Cost of Revenue", "CostOfRevenue"]),
    ("Gross Profit",             ["Gross Profit", "GrossProfit"]),
    ("Operating Expense",        ["Operating Expense", "Total Operating Expenses",
                                  "OperatingExpense"]),
    ("Operating Income",         ["Operating Income", "OperatingIncome", "EBIT", "Ebit"]),
    ("Pretax Income",            ["Pretax Income", "PretaxIncome", "Income Before Tax"]),
    ("Tax Provision",            ["Tax Provision", "Income Tax Expense", "TaxProvision"]),
    ("Net Income",               ["Net Income", "NetIncome",
                                  "Net Income Common Stockholders"]),
    ("EBITDA",                   ["EBITDA", "Normalized EBITDA"]),
    ("Diluted EPS",              ["Diluted EPS", "Basic EPS"]),
]

BALANCE_ROWS = [
    ("Total Assets",             ["Total Assets", "TotalAssets"]),
    ("Current Assets",           ["Current Assets", "CurrentAssets"]),
    ("Cash & Equivalents",       ["Cash And Cash Equivalents",
                                  "Cash Cash Equivalents And Short Term Investments"]),
    ("Total Liabilities",        ["Total Liabilities Net Minority Interest",
                                  "Total Liab", "TotalLiabilities"]),
    ("Current Liabilities",      ["Current Liabilities", "CurrentLiabilities"]),
    ("Total Debt",               ["Total Debt", "TotalDebt", "Long Term Debt"]),
    ("Stockholders Equity",      ["Stockholders Equity", "Common Stock Equity",
                                  "Total Equity Gross Minority Interest"]),
    ("Working Capital",          ["Working Capital", "WorkingCapital"]),
    ("Shares Issued",            ["Share Issued", "Ordinary Shares Number"]),
]

CASHFLOW_ROWS = [
    ("Operating Cash Flow",      ["Operating Cash Flow", "Total Cash From Operating Activities"]),
    ("Investing Cash Flow",      ["Investing Cash Flow", "Total Cashflows From Investing Activities"]),
    ("Financing Cash Flow",      ["Financing Cash Flow", "Total Cash From Financing Activities"]),
    ("Capital Expenditure",      ["Capital Expenditure", "Capital Expenditures"]),
    ("Free Cash Flow",           ["Free Cash Flow", "FreeCashFlow"]),
    ("Stock Repurchases",        ["Repurchase Of Capital Stock"]),
    ("Dividends Paid",           ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    ("Net Change in Cash",       ["Changes In Cash", "Net Change In Cash"]),
]


def _tab_financials(ticker):
    fin = _fetch_financials(ticker)
    period_choice = st.radio(
        "", ["Annual", "Quarterly"], horizontal=True,
        key="fin_period", label_visibility="collapsed",
    )
    suffix = "y" if period_choice == "Annual" else "q"

    st.markdown(_section_label("Income Statement"), unsafe_allow_html=True)
    st.markdown(_financial_table(fin[f"is_{suffix}"], INCOME_ROWS),
                unsafe_allow_html=True)

    st.markdown(_section_label("Balance Sheet"), unsafe_allow_html=True)
    st.markdown(_financial_table(fin[f"bs_{suffix}"], BALANCE_ROWS),
                unsafe_allow_html=True)

    st.markdown(_section_label("Cash Flow"), unsafe_allow_html=True)
    st.markdown(_financial_table(fin[f"cf_{suffix}"], CASHFLOW_ROWS),
                unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · ANALYSIS (estimates, earnings history, recommendation breakdown)
# ═════════════════════════════════════════════════════════════

def _tab_analysis(ticker, info):
    extras = _fetch_extras(ticker)

    # ── Price targets summary
    cur     = info.get("currentPrice") or info.get("regularMarketPrice")
    tgt_m   = info.get("targetMeanPrice")
    tgt_h   = info.get("targetHighPrice")
    tgt_l   = info.get("targetLowPrice")
    n_an    = info.get("numberOfAnalystOpinions")
    rec     = info.get("recommendationKey", "").upper().replace("_", " ")
    rec_mean= info.get("recommendationMean")

    upside_mean = ((tgt_m - cur) / cur * 100) if (tgt_m and cur) else None
    if upside_mean is None:
        up_html = "—"
    else:
        col = C.GREEN if upside_mean >= 0 else C.RED
        sign = "+" if upside_mean >= 0 else ""
        up_html = (f'<span style="color:{col};font-weight:700">'
                   f'{sign}{upside_mean:.1f}%</span>')

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(_section_label("Price Targets"), unsafe_allow_html=True)
        st.markdown(_stat_table([
            ("Current Price",        _fmt_price(cur)),
            ("Mean Target",          _fmt_price(tgt_m)),
            ("Mean Upside",          up_html),
            ("High Target",          _fmt_price(tgt_h)),
            ("Low Target",           _fmt_price(tgt_l)),
            ("# of Analysts",        _fmt_int(n_an)),
            ("Consensus",            f'<span style="color:{C.BLUE};font-weight:700">{rec}</span>'
                                     if rec else "—"),
            ("Recommendation Mean",  _fmt_num(rec_mean, 2) + " / 5" if rec_mean else "—"),
        ]), unsafe_allow_html=True)

    with c2:
        st.markdown(_section_label("Recommendation Trend"), unsafe_allow_html=True)
        recs = extras.get("recs")
        if isinstance(recs, pd.DataFrame) and not recs.empty:
            cols_to_show = [c for c in ["period","strongBuy","buy","hold","sell","strongSell"]
                            if c in recs.columns]
            if cols_to_show:
                df_disp = recs[cols_to_show].head(4)
                _rec_html = ""
                for _, r in df_disp.iterrows():
                    cells = "".join(
                        f'<td style="padding:8px 10px;font-size:0.78rem;text-align:right;'
                        f'font-family:\'JetBrains Mono\',monospace;color:{C.TEXT}">'
                        f'{int(r[c]) if pd.notna(r[c]) and c != "period" else r[c]}</td>'
                        for c in cols_to_show
                    )
                    _rec_html += (f'<tr style="border-bottom:1px solid {C.BORDER}">{cells}</tr>')
                headers_html = "".join(
                    f'<th style="padding:8px 10px;font-size:0.66rem;color:{C.TEXT3};'
                    f'text-align:right;text-transform:uppercase;letter-spacing:1px;'
                    f'font-weight:700;border-bottom:1px solid {C.BORDER2}">{c}</th>'
                    for c in cols_to_show
                )
                st.markdown(
                    f'<table style="width:100%;border-collapse:collapse;'
                    f'background:{C.SURFACE};border:1px solid {C.BORDER};'
                    f'border-radius:8px;overflow:hidden">'
                    f'<thead><tr>{headers_html}</tr></thead>'
                    f'<tbody>{_rec_html}</tbody></table>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f'<div style="color:{C.TEXT3};font-size:0.78rem">No data.</div>',
                            unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="color:{C.TEXT3};font-size:0.78rem">No data.</div>',
                        unsafe_allow_html=True)

    # ── Earnings history (beat/miss)
    st.markdown(_section_label("Earnings History"), unsafe_allow_html=True)
    edates = extras.get("earnings")
    if isinstance(edates, pd.DataFrame) and not edates.empty:
        df = edates.head(8).reset_index()
        # try common columns
        for col_d in ["Earnings Date", "earnings_date", "Earnings_Date"]:
            if col_d in df.columns:
                df["__date"] = df[col_d]; break
        if "__date" not in df.columns:
            df["__date"] = df.iloc[:, 0]
        cols_show = []
        for k, label in [("EPS Estimate","Est. EPS"),
                         ("Reported EPS","Reported EPS"),
                         ("Surprise(%)","Surprise %")]:
            if k in df.columns: cols_show.append((k, label))
        rows_html = ""
        for _, r in df.iterrows():
            d = pd.to_datetime(r["__date"]).strftime("%b %d, %Y") \
                if pd.notna(r["__date"]) else "—"
            cells = (f'<td style="padding:8px 12px;font-size:0.78rem;color:{C.TEXT2}">{d}</td>')
            for k, _ in cols_show:
                v = r.get(k)
                col = C.TEXT
                if k == "Surprise(%)" and pd.notna(v):
                    col = C.GREEN if v >= 0 else C.RED
                txt = _fmt_pct(v, 2, sign=True) if k == "Surprise(%)" \
                      else _fmt_num(v, 2)
                cells += (f'<td style="padding:8px 12px;font-size:0.78rem;'
                          f'text-align:right;color:{col};font-weight:600;'
                          f'font-family:\'JetBrains Mono\',monospace">{txt}</td>')
            rows_html += f'<tr style="border-bottom:1px solid {C.BORDER}">{cells}</tr>'
        headers_html = (f'<th style="padding:8px 12px;font-size:0.66rem;'
                        f'color:{C.TEXT3};text-align:left;text-transform:uppercase;'
                        f'letter-spacing:1px;font-weight:700;'
                        f'border-bottom:1px solid {C.BORDER2}">Date</th>'
                       + "".join(
                           f'<th style="padding:8px 12px;font-size:0.66rem;'
                           f'color:{C.TEXT3};text-align:right;text-transform:uppercase;'
                           f'letter-spacing:1px;font-weight:700;'
                           f'border-bottom:1px solid {C.BORDER2}">{lab}</th>'
                           for _, lab in cols_show))
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;'
            f'background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;overflow:hidden">'
            f'<thead><tr>{headers_html}</tr></thead>'
            f'<tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:14px;color:{C.TEXT3};font-size:0.8rem">'
            f'Earnings history unavailable.</div>',
            unsafe_allow_html=True,
        )

    # ── Forward estimates from info
    st.markdown(_section_label("Forward Estimates"), unsafe_allow_html=True)
    st.markdown(_stat_table([
        ("Forward EPS",          _fmt_price(info.get("forwardEps"))),
        ("Forward P/E",           _fmt_num(info.get("forwardPE"), 2)),
        ("Earnings Growth (YoY)", _fmt_pct((info.get("earningsGrowth") or 0)*100, sign=True)
                                  if info.get("earningsGrowth") is not None else "—"),
        ("Revenue Growth (YoY)",  _fmt_pct((info.get("revenueGrowth") or 0)*100, sign=True)
                                  if info.get("revenueGrowth") is not None else "—"),
        ("Earnings Quarterly Growth", _fmt_pct((info.get("earningsQuarterlyGrowth") or 0)*100, sign=True)
                                  if info.get("earningsQuarterlyGrowth") is not None else "—"),
    ]), unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · HOLDERS
# ═════════════════════════════════════════════════════════════

def _tab_holders(ticker, info):
    extras = _fetch_extras(ticker)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(_section_label("Ownership Breakdown"), unsafe_allow_html=True)
        ip = info.get("heldPercentInsiders")
        ti = info.get("heldPercentInstitutions")
        sp = info.get("shortPercentOfFloat")
        sr = info.get("shortRatio")
        ss = info.get("sharesShort")
        fs = info.get("floatShares")
        so = info.get("sharesOutstanding")
        st.markdown(_stat_table([
            ("% Held by Insiders",         _fmt_pct(ip*100) if ip else "—"),
            ("% Held by Institutions",     _fmt_pct(ti*100) if ti else "—"),
            ("Float Shares",               _fmt_int(fs)),
            ("Shares Outstanding",         _fmt_int(so)),
            ("Shares Short",               _fmt_int(ss)),
            ("Short % of Float",           _fmt_pct(sp*100) if sp else "—"),
            ("Short Ratio (days to cover)",_fmt_num(sr, 1) + " d" if sr else "—"),
        ]), unsafe_allow_html=True)

    with c2:
        st.markdown(_section_label("Major Holders"), unsafe_allow_html=True)
        major = extras.get("major")
        if isinstance(major, pd.DataFrame) and not major.empty:
            rows_html = ""
            for _, r in major.iterrows():
                vals = list(r.values)
                if len(vals) < 2: continue
                rows_html += (
                    f'<tr style="border-bottom:1px solid {C.BORDER}">'
                    f'<td style="padding:8px 14px;font-size:0.78rem;color:{C.TEXT2}">{vals[1]}</td>'
                    f'<td style="padding:8px 14px;font-size:0.8rem;color:{C.TEXT};'
                    f'font-family:\'JetBrains Mono\',monospace;font-weight:600;'
                    f'text-align:right">{vals[0]}</td></tr>'
                )
            st.markdown(
                f'<table style="width:100%;border-collapse:collapse;'
                f'background:{C.SURFACE};border:1px solid {C.BORDER};'
                f'border-radius:8px;overflow:hidden">{rows_html}</table>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'<div style="color:{C.TEXT3};font-size:0.78rem">No data.</div>',
                        unsafe_allow_html=True)

    # Top institutional holders
    st.markdown(_section_label("Top Institutional Holders"), unsafe_allow_html=True)
    inst = extras.get("inst")
    if isinstance(inst, pd.DataFrame) and not inst.empty:
        cols = list(inst.columns)
        wanted = [c for c in ["Holder", "Shares", "Date Reported",
                              "% Out", "Value", "pctHeld"] if c in cols]
        if not wanted: wanted = cols[:5]
        rows_html = ""
        for _, r in inst.head(10).iterrows():
            cells = ""
            for c in wanted:
                v = r[c]
                if isinstance(v, (int, float)) and not pd.isna(v):
                    if "Date" in c:
                        v = _fmt_date(v)
                    elif c in ("pctHeld", "% Out"):
                        v = _fmt_pct(float(v)*100) if float(v) < 1 else _fmt_pct(float(v))
                    elif "Value" in c:
                        v = _fmt_money(v)
                    elif "Shares" in c:
                        v = _fmt_int(v)
                    else:
                        v = _fmt_num(v, 2)
                cells += (f'<td style="padding:7px 12px;font-size:0.76rem;'
                          f'color:{C.TEXT};font-family:\'JetBrains Mono\',monospace">'
                          f'{v}</td>')
            rows_html += f'<tr style="border-bottom:1px solid {C.BORDER}">{cells}</tr>'
        headers_html = "".join(
            f'<th style="padding:8px 12px;font-size:0.66rem;color:{C.TEXT3};'
            f'text-align:left;text-transform:uppercase;letter-spacing:1px;'
            f'font-weight:700;border-bottom:1px solid {C.BORDER2}">{c}</th>'
            for c in wanted
        )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;'
            f'background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;overflow:hidden">'
            f'<thead><tr>{headers_html}</tr></thead>'
            f'<tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div style="color:{C.TEXT3};font-size:0.78rem">No data.</div>',
                    unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · NEWS
# ═════════════════════════════════════════════════════════════

def _tab_news(ticker):
    extras = _fetch_extras(ticker)
    items = extras.get("news") or []
    if not items:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:24px;text-align:center;color:{C.TEXT3}">'
            f'No recent news available.</div>',
            unsafe_allow_html=True,
        )
        return

    cards = []
    for it in items[:15]:
        # yfinance returns either flat dict or {"content": {...}}
        c = it.get("content") if isinstance(it.get("content"), dict) else it
        title = c.get("title") or "Untitled"
        pub   = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) \
                else c.get("publisher", "")
        ts    = c.get("pubDate") or c.get("providerPublishTime")
        if isinstance(ts, (int, float)):
            t = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
        elif isinstance(ts, str):
            try:    t = pd.to_datetime(ts).strftime("%b %d, %Y · %H:%M")
            except: t = ts
        else:
            t = "—"
        link = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) \
               else c.get("link", "#")
        summary = c.get("summary") or ""

        cards.append(
            f'<a href="{link}" target="_blank" style="text-decoration:none">'
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:3px solid {C.GREEN};border-radius:8px;padding:14px 18px;'
            f'margin-bottom:10px;transition:border-color 0.15s">'
            f'<div style="font-size:0.75rem;color:{C.TEXT3};margin-bottom:4px;'
            f'display:flex;justify-content:space-between">'
            f'<span style="color:{C.GREEN};font-weight:600">{pub}</span>'
            f'<span>{t}</span></div>'
            f'<div style="font-size:0.92rem;color:{C.TEXT};font-weight:600;'
            f'margin-bottom:4px;line-height:1.4">{title}</div>'
            + (f'<div style="font-size:0.78rem;color:{C.TEXT2};'
               f'line-height:1.6">{summary[:240]}'
               + ("…" if len(summary) > 240 else "")
               + f'</div>'
               if summary else "")
            + f'</div></a>'
        )
    st.markdown("".join(cards), unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# EMPTY STATE
# ═════════════════════════════════════════════════════════════

def _empty_state():
    examples = ["AAPL", "MSFT", "NVDA", "GOOGL", "META",
                "AMZN", "TSLA", "BRK-B", "JPM", "V", "JNJ", "WMT"]
    chips = "".join(
        f'<span style="background:{C.SURFACE2};color:{C.TEXT2};'
        f'padding:5px 14px;border-radius:14px;font-size:0.72rem;'
        f'font-family:\'JetBrains Mono\',monospace;border:1px solid {C.BORDER};'
        f'cursor:pointer">{t}</span>'
        for t in examples
    )
    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:14px;padding:54px 32px;text-align:center;margin-top:24px">'
        f'<div style="font-size:2.4rem;margin-bottom:14px">🔬</div>'
        f'<div style="font-size:1.05rem;color:{C.TEXT};font-weight:700;'
        f'margin-bottom:8px;letter-spacing:0.4px">Stock Research</div>'
        f'<div style="font-size:0.85rem;color:{C.TEXT3};max-width:520px;'
        f'margin:0 auto 20px;line-height:1.7">'
        f'Search any S&P 500 ticker. Get the standard breakdown: '
        f'price chart, statistics, multi-year financial statements, '
        f'analyst estimates, holders, and news.</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;'
        f'max-width:560px;margin:0 auto">{chips}</div></div>',
        unsafe_allow_html=True,
    )
