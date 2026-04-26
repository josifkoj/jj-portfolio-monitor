# app/pages/analyzer.py  —  Enter any ticker → full auto analysis
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from app import config as C
from app.styles import section_title, progress_bar, badge
from app.utils import fmt_price, fmt_pct, fmt_mktcap, pct52


# ─────────────────────────────────────────────────────────────
# Data fetchers (cached)
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_info(ticker: str) -> dict:
    """Fast fetch: price + key stats from yfinance info dict."""
    try:
        info = yf.Ticker(ticker).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return {}
        return info
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fundamentals(ticker: str) -> dict:
    """Slower fetch: financial statements + price history."""
    out = {"fin": pd.DataFrame(), "bs": pd.DataFrame(),
           "cf": pd.DataFrame(), "hist": pd.DataFrame()}
    try:
        t = yf.Ticker(ticker)
        try:    out["fin"]  = t.financials
        except: pass
        try:    out["bs"]   = t.balance_sheet
        except: pass
        try:    out["cf"]   = t.cashflow
        except: pass
        try:    out["hist"] = t.history(period="1y", interval="1d")
        except: pass
    except Exception:
        pass
    return out


# ─────────────────────────────────────────────────────────────
# Calculation helpers
# ─────────────────────────────────────────────────────────────

def _safe_row(df: pd.DataFrame, *keys) -> float | None:
    """Try multiple row-name variants; return first non-null float."""
    for k in keys:
        if k in df.index:
            try:
                v = df.loc[k].dropna()
                if not v.empty:
                    return float(v.iloc[0])
            except Exception:
                pass
    return None


def _calc_roic(fin: pd.DataFrame, bs: pd.DataFrame) -> float | None:
    """ROIC = NOPAT / Invested Capital.  Returns % or None."""
    if fin.empty or bs.empty:
        return None
    try:
        ebit = _safe_row(fin, "EBIT", "Operating Income",
                         "Ebit", "OperatingIncome")
        if ebit is None:
            return None
        nopat = ebit * 0.79  # ~21% effective tax

        equity = _safe_row(bs, "Stockholders Equity",
                           "Common Stock Equity",
                           "Total Equity Gross Minority Interest",
                           "TotalEquityGrossMinorityInterest")
        debt   = _safe_row(bs, "Total Debt", "Long Term Debt",
                           "Total Long Term Debt", "LongTermDebt") or 0.0
        cash   = _safe_row(bs, "Cash And Cash Equivalents",
                           "Cash", "CashAndCashEquivalents",
                           "Cash Cash Equivalents And Short Term Investments") or 0.0
        if equity is None:
            return None
        ic = equity + debt - cash
        if ic <= 0:
            return None
        return round(nopat / ic * 100, 1)
    except Exception:
        return None


def _calc_fcf_margin(info: dict, cf: pd.DataFrame) -> float | None:
    """FCF Margin % = Free Cash Flow / Total Revenue × 100."""
    rev  = info.get("totalRevenue")
    fcf  = info.get("freeCashflow")
    if not fcf and not cf.empty:
        fcf = _safe_row(cf, "Free Cash Flow", "FreeCashFlow",
                        "Capital Expenditure")  # fallback
    if fcf and rev and rev > 0:
        return round(fcf / rev * 100, 1)
    return None


def _quality_score(roic, fcf_m, gross_m, rev_g, de) -> int:
    """Composite 0-100 quality score."""
    s = 0
    # ROIC (25 pts)
    if roic is not None:
        s += 25 if roic >= 25 else 18 if roic >= 15 else 10 if roic >= 8 else 4
    # FCF Margin (20 pts)
    if fcf_m is not None:
        s += 20 if fcf_m >= 25 else 14 if fcf_m >= 15 else 8 if fcf_m >= 8 else 3
    # Gross Margin (15 pts)
    if gross_m is not None:
        s += 15 if gross_m >= 60 else 10 if gross_m >= 40 else 6 if gross_m >= 25 else 2
    # Revenue Growth (15 pts)
    if rev_g is not None:
        s += 15 if rev_g >= 20 else 10 if rev_g >= 10 else 6 if rev_g >= 5 else 2
    # Debt (15 pts)
    if de is not None:
        s += 15 if de <= 0.3 else 10 if de <= 0.8 else 5 if de <= 1.5 else 1
    # Default points when data missing (avoid penalising)
    missing = sum(1 for x in [roic, fcf_m, gross_m, rev_g, de] if x is None)
    s += missing * 5
    return min(95, s)


def _auto_fv(fwd_eps, growth_pct) -> float | None:
    """PEG=1 fair value: Forward EPS × (growth_rate × 2), capped."""
    if not fwd_eps or fwd_eps <= 0:
        return None
    if growth_pct is None or growth_pct <= 0:
        multiple = 13.0
    elif growth_pct >= 30:
        multiple = min(growth_pct * 1.4, 50)
    elif growth_pct >= 15:
        multiple = growth_pct * 1.8
    else:
        multiple = max(growth_pct * 2.2, 12)
    return round(fwd_eps * multiple, 2)


def _verdict(score: int, upside) -> tuple[str, str, str]:
    """Returns (label, color, explanation)."""
    u = upside or 0
    if score >= 72 and u >= 20:
        return "STRONG BUY", C.GREEN, "Exceptional quality + significant upside to fair value."
    if score >= 60 and u >= 10:
        return "BUY CANDIDATE", C.GREEN, "High quality business trading at a meaningful discount."
    if score >= 55 and u >= 0:
        return "WATCHLIST", C.GOLD, "Good quality — monitor for a better entry point."
    if score >= 42:
        return "HOLD / MONITOR", C.BLUE, "Decent fundamentals but limited upside or high valuation."
    if score >= 28:
        return "WEAK — WAIT", "#FF9B3D", "Below-average quality. Wait for margin of safety or improvement."
    return "AVOID", C.RED, "Poor fundamentals. Fails JJ quality screen."


# ─────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────

def _price_chart(hist: pd.DataFrame, fv: float | None,
                 analyst_tgt: float | None) -> go.Figure:
    fig = go.Figure()

    # Volume bars (secondary)
    if "Volume" in hist.columns:
        fig.add_trace(go.Bar(
            x=hist.index, y=hist["Volume"],
            name="Volume", marker_color=f"{C.BORDER2}",
            opacity=0.4, yaxis="y2", showlegend=False,
        ))

    # Price line
    fig.add_trace(go.Scatter(
        x=hist.index, y=hist["Close"],
        name="Price", mode="lines",
        line=dict(color=C.GREEN, width=2),
        fill="tozeroy",
        fillcolor=f"{C.GREEN}12",
        hovertemplate="<b>%{x|%b %d %Y}</b><br>$%{y:.2f}<extra></extra>",
    ))

    # Reference lines
    if fv:
        fig.add_hline(y=fv, line_dash="dash",
                      line_color=C.GOLD, line_width=1,
                      annotation_text=f"  Auto FV ${fv:.0f}",
                      annotation_font_color=C.GOLD,
                      annotation_font_size=10)
    if analyst_tgt:
        fig.add_hline(y=analyst_tgt, line_dash="dot",
                      line_color=C.BLUE, line_width=1,
                      annotation_text=f"  Analyst ${analyst_tgt:.0f}",
                      annotation_font_color=C.BLUE,
                      annotation_font_size=10)

    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(gridcolor=C.BORDER, showspikes=True,
                   spikecolor=C.BORDER2),
        yaxis=dict(title="Price ($)", gridcolor=C.BORDER,
                   tickprefix="$", showspikes=True,
                   spikecolor=C.BORDER2),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    showticklabels=False, range=[0, hist["Volume"].max() * 6]
                    if "Volume" in hist.columns else [0, 1]),
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=C.SURFACE, bordercolor=C.GREEN,
                        font=dict(family="JetBrains Mono", size=11)),
    )
    return fig


def _gauge_chart(score: int, col: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        number={"font": {"color": col, "family": "JetBrains Mono",
                         "size": 32}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": C.TEXT3,
                     "tickfont": {"size": 9, "color": C.TEXT3}},
            "bar": {"color": col, "thickness": 0.25},
            "bgcolor": C.SURFACE2,
            "borderwidth": 0,
            "steps": [
                {"range": [0,  30], "color": f"{C.RED}22"},
                {"range": [30, 55], "color": f"{C.GOLD}22"},
                {"range": [55, 75], "color": f"{C.GREEN}22"},
                {"range": [75, 100], "color": f"{C.GREEN}44"},
            ],
            "threshold": {"line": {"color": col, "width": 2},
                          "thickness": 0.75, "value": score},
        }
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", font_color=C.TEXT2,
        height=180, margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


# ─────────────────────────────────────────────────────────────
# Metric row helper
# ─────────────────────────────────────────────────────────────

def _metric_row(label: str, value: str, color: str,
                bar_pct: int | None = None, bar_col: str | None = None) -> str:
    bar = progress_bar(bar_pct, bar_col or color, height=4) if bar_pct is not None else ""
    return (
        f'<div style="padding:7px 0;border-bottom:1px solid {C.BORDER}">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<span style="font-size:0.75rem;color:{C.TEXT3}">{label}</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;'
        f'font-weight:700;color:{color}">{value}</span>'
        f'</div>'
        f'{bar}'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────

def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("🔬  Stock Analyzer — Instant Deep Dive"),
                unsafe_allow_html=True)

    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:8px;padding:12px 16px;font-size:0.8rem;'
        f'color:{C.TEXT2};margin-bottom:20px;line-height:1.6">'
        f'Enter <b style="color:{C.GREEN}">any S&P 500 ticker</b> and the analyzer '
        f'automatically fetches live price, calculates ROIC, FCF margins, fair value, '
        f'quality score and generates a verdict — in seconds.</div>',
        unsafe_allow_html=True,
    )

    # ── Search bar ────────────────────────────────────────────
    sc1, sc2, sc3 = st.columns([3, 1, 2])
    raw = sc1.text_input("", placeholder="Enter ticker  e.g. AAPL  MSFT  NVDA  GOOGL",
                         key="analyzer_input", label_visibility="collapsed")
    go_btn = sc2.button("🔍  Analyze", use_container_width=True, key="analyzer_go")

    ticker = raw.strip().upper()

    # Preserve last analyzed ticker across reruns
    if go_btn and ticker:
        st.session_state["analyzer_tk"] = ticker
    if not ticker and "analyzer_tk" in st.session_state:
        ticker = st.session_state["analyzer_tk"]

    if not ticker:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:12px;padding:48px;text-align:center;margin-top:20px">'
            f'<div style="font-size:2.5rem;margin-bottom:12px">🔬</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
            f'color:{C.TEXT};font-weight:600;margin-bottom:8px">Stock Deep Dive</div>'
            f'<div style="font-size:0.82rem;color:{C.TEXT3};max-width:400px;'
            f'margin:0 auto;line-height:1.7">'
            f'Type any ticker above and press Analyze.<br>'
            f'Works on any publicly traded US stock — not just the JJ universe.'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        return

    # ── Fetch data ────────────────────────────────────────────
    with st.spinner(f"Fetching data for {ticker}…"):
        info = _fetch_info(ticker)

    if not info:
        st.error(f"❌  Could not fetch data for **{ticker}** — check the ticker symbol.")
        return

    with st.spinner("Computing fundamentals…"):
        fd = _fetch_fundamentals(ticker)

    fin  = fd.get("fin",  pd.DataFrame())
    bs   = fd.get("bs",   pd.DataFrame())
    cf   = fd.get("cf",   pd.DataFrame())
    hist = fd.get("hist", pd.DataFrame())

    # ── Extract key fields ────────────────────────────────────
    name        = info.get("shortName") or info.get("longName") or ticker
    sector      = info.get("sector",   "—")
    industry    = info.get("industry", "—")
    description = info.get("longBusinessSummary", "")

    cur         = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close  = info.get("previousClose") or info.get("regularMarketPreviousClose")
    chg_pct     = ((cur - prev_close) / prev_close * 100) if cur and prev_close else None
    high52      = info.get("fiftyTwoWeekHigh")
    low52       = info.get("fiftyTwoWeekLow")
    mktcap      = info.get("marketCap")
    beta        = info.get("beta")
    div_yield   = info.get("dividendYield")

    pe_ttm      = info.get("trailingPE")
    fwd_pe      = info.get("forwardPE")
    trailing_eps = info.get("trailingEps")
    fwd_eps     = info.get("forwardEps")
    pb          = info.get("priceToBook")
    ps          = info.get("priceToSalesTrailingTwelveMonths")

    gross_m_raw = info.get("grossMargins")
    op_m_raw    = info.get("operatingMargins")
    net_m_raw   = info.get("profitMargins")
    roe_raw     = info.get("returnOnEquity")
    roa_raw     = info.get("returnOnAssets")
    rev_g_raw   = info.get("revenueGrowth")
    eps_g_raw   = info.get("earningsGrowth")
    de_raw      = info.get("debtToEquity")
    current_ratio = info.get("currentRatio")
    total_rev   = info.get("totalRevenue")
    fcf_abs     = info.get("freeCashflow")

    analyst_tgt     = info.get("targetMeanPrice")
    analyst_high    = info.get("targetHighPrice")
    analyst_low     = info.get("targetLowPrice")
    analyst_n       = info.get("numberOfAnalystOpinions")
    analyst_rating  = info.get("recommendationKey", "").upper().replace("_", " ")

    # Convert to % where needed
    gross_m  = round(gross_m_raw  * 100, 1) if gross_m_raw  is not None else None
    op_m     = round(op_m_raw     * 100, 1) if op_m_raw     is not None else None
    net_m    = round(net_m_raw    * 100, 1) if net_m_raw    is not None else None
    roe      = round(roe_raw      * 100, 1) if roe_raw      is not None else None
    roa      = round(roa_raw      * 100, 1) if roa_raw      is not None else None
    rev_g    = round(rev_g_raw    * 100, 1) if rev_g_raw    is not None else None
    eps_g    = round(eps_g_raw    * 100, 1) if eps_g_raw    is not None else None
    de       = round(de_raw / 100, 2)       if de_raw       is not None else None

    # Calculated fields
    roic      = _calc_roic(fin, bs)
    fcf_m     = _calc_fcf_margin(info, cf)
    fcf_yield = (fcf_abs / mktcap * 100) if (fcf_abs and mktcap and mktcap > 0) else None

    growth_pct = eps_g or rev_g
    auto_fv    = _auto_fv(fwd_eps, growth_pct)
    upside     = round((auto_fv - cur) / cur * 100, 1) if (auto_fv and cur and cur > 0) else None
    analyst_upside = round((analyst_tgt - cur) / cur * 100, 1) if (analyst_tgt and cur) else None

    q_score    = _quality_score(roic, fcf_m, gross_m, rev_g, de)
    v_label, v_col, v_reason = _verdict(q_score, upside)

    chg_col   = C.GREEN if (chg_pct or 0) >= 0 else C.RED
    pos52     = pct52(cur, low52, high52)

    # ── Company header ────────────────────────────────────────
    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-top:3px solid {C.GREEN};border-radius:12px;'
        f'padding:20px 24px;margin-bottom:16px">'
        f'<div style="display:flex;justify-content:space-between;align-items:start">'
        f'<div>'
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.5rem;'
        f'font-weight:700;color:{C.GREEN}">{ticker}</span>'
        f'<span style="background:{C.SURFACE2};color:{C.TEXT};padding:3px 10px;'
        f'border-radius:4px;font-size:0.75rem">{sector}</span>'
        f'<span style="background:{C.SURFACE2};color:{C.TEXT3};padding:3px 10px;'
        f'border-radius:4px;font-size:0.72rem">{industry}</span>'
        f'</div>'
        f'<div style="font-size:0.88rem;color:{C.TEXT2};margin-bottom:4px">{name}</div>'
        f'<div style="font-size:0.7rem;color:{C.TEXT3}">Mkt Cap: '
        f'<b style="color:{C.TEXT}">{fmt_mktcap(mktcap)}</b>'
        f'{"  ·  Beta: <b style=\"color:"+C.TEXT+"\">"+str(round(beta,2))+"</b>" if beta else ""}'
        f'{"  ·  Yield: <b style=\"color:"+C.GOLD+"\">"+fmt_pct(div_yield*100 if div_yield else None,sign=False)+"</b>" if div_yield else ""}'
        f'</div>'
        f'</div>'
        f'<div style="text-align:right">'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2rem;'
        f'font-weight:700;color:{C.TEXT}">{fmt_price(cur)}</div>'
        f'<div style="font-size:0.82rem;color:{chg_col};font-weight:600">'
        f'{fmt_pct(chg_pct)} today</div>'
        f'<div style="margin-top:6px">'
        + badge(v_label, v_col, f"{v_col}18") +
        f'</div>'
        f'</div>'
        f'</div>'
        # 52wk range bar
        + (
            f'<div style="margin-top:14px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:0.65rem;color:{C.TEXT3};margin-bottom:4px">'
            f'<span>52wk Low {fmt_price(low52)}</span>'
            f'<span style="color:{C.TEXT2}">Current Position</span>'
            f'<span>52wk High {fmt_price(high52)}</span>'
            f'</div>'
            + progress_bar(pos52 or 0, C.GREEN, height=6)
            + f'</div>'
            if pos52 is not None else ""
        )
        + f'</div>',
        unsafe_allow_html=True,
    )

    # ── Main 3-column layout ───────────────────────────────────
    col_q, col_v, col_a = st.columns([1, 1, 1])

    # ── Col 1: Quality Metrics ────────────────────────────────
    with col_q:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:10px;padding:16px 18px;height:100%">'
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin-bottom:4px">Quality Metrics</div>'
            + _metric_row("ROIC %",
                          f"{roic:.1f}%" if roic is not None else "—",
                          C.GREEN if (roic or 0) >= 15 else C.GOLD if (roic or 0) >= 8 else C.RED,
                          min(int(roic or 0), 100), C.GREEN)
            + _metric_row("Gross Margin",
                          f"{gross_m:.1f}%" if gross_m is not None else "—",
                          C.GREEN if (gross_m or 0) >= 50 else C.GOLD if (gross_m or 0) >= 30 else C.TEXT3,
                          min(int(gross_m or 0), 100), C.GREEN)
            + _metric_row("Operating Margin",
                          f"{op_m:.1f}%" if op_m is not None else "—",
                          C.GREEN if (op_m or 0) >= 20 else C.GOLD if (op_m or 0) >= 10 else C.TEXT3,
                          min(int(op_m or 0), 100), C.GOLD)
            + _metric_row("Net Margin",
                          f"{net_m:.1f}%" if net_m is not None else "—",
                          C.GREEN if (net_m or 0) >= 15 else C.GOLD if (net_m or 0) >= 8 else C.TEXT3,
                          min(int(net_m or 0), 100), C.TEAL)
            + _metric_row("FCF Margin",
                          f"{fcf_m:.1f}%" if fcf_m is not None else "—",
                          C.GREEN if (fcf_m or 0) >= 15 else C.GOLD if (fcf_m or 0) >= 8 else C.TEXT3,
                          min(int(fcf_m or 0), 100), C.GREEN)
            + _metric_row("ROE %",
                          f"{roe:.1f}%" if roe is not None else "—",
                          C.GREEN if (roe or 0) >= 20 else C.TEXT3, None)
            + _metric_row("Revenue Growth",
                          fmt_pct(rev_g, sign=True) if rev_g is not None else "—",
                          C.GREEN if (rev_g or 0) >= 10 else C.GOLD if (rev_g or 0) >= 5 else C.RED,
                          None)
            + _metric_row("EPS Growth",
                          fmt_pct(eps_g, sign=True) if eps_g is not None else "—",
                          C.GREEN if (eps_g or 0) >= 10 else C.GOLD if (eps_g or 0) >= 5 else C.RED,
                          None)
            + _metric_row("Debt / Equity",
                          f"{de:.2f}x" if de is not None else "—",
                          C.GREEN if (de or 99) <= 0.5 else C.GOLD if (de or 99) <= 1.2 else C.RED,
                          None)
            + _metric_row("Current Ratio",
                          f"{current_ratio:.1f}x" if current_ratio else "—",
                          C.GREEN if (current_ratio or 0) >= 1.5 else C.GOLD, None)
            + f'</div>',
            unsafe_allow_html=True,
        )

    # ── Col 2: Valuation ──────────────────────────────────────
    with col_v:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:10px;padding:16px 18px;height:100%">'
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin-bottom:4px">Valuation</div>'
            + _metric_row("PE (TTM)",
                          f"{pe_ttm:.1f}x" if pe_ttm else "—",
                          C.GREEN if pe_ttm and pe_ttm < 20 else C.GOLD if pe_ttm and pe_ttm < 35 else C.RED,
                          None)
            + _metric_row("Forward PE",
                          f"{fwd_pe:.1f}x" if fwd_pe else "—",
                          C.GREEN if fwd_pe and fwd_pe < 20 else C.GOLD if fwd_pe and fwd_pe < 30 else C.RED,
                          None)
            + _metric_row("Price / Book",
                          f"{pb:.1f}x" if pb else "—",
                          C.GREEN if pb and pb < 3 else C.GOLD if pb and pb < 8 else C.TEXT3,
                          None)
            + _metric_row("Price / Sales",
                          f"{ps:.1f}x" if ps else "—",
                          C.GREEN if ps and ps < 5 else C.GOLD if ps and ps < 12 else C.TEXT3,
                          None)
            + _metric_row("EPS (TTM)",
                          fmt_price(trailing_eps) if trailing_eps else "—",
                          C.GREEN if (trailing_eps or 0) > 0 else C.RED, None)
            + _metric_row("EPS (Fwd)",
                          fmt_price(fwd_eps) if fwd_eps else "—",
                          C.GREEN if (fwd_eps or 0) > (trailing_eps or 0) else C.TEXT3,
                          None)
            + _metric_row("FCF Yield",
                          fmt_pct(fcf_yield, sign=False) if fcf_yield else "—",
                          C.GREEN if (fcf_yield or 0) >= 4 else C.GOLD,
                          None)
            + f'<div style="margin-top:16px;padding-top:12px;border-top:1px solid {C.BORDER2}">'
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin-bottom:8px">Fair Value Estimates</div>'
            + _metric_row("Auto FV (PEG)",
                          fmt_price(auto_fv) if auto_fv else "—",
                          C.GOLD, None)
            + _metric_row("Auto Upside",
                          fmt_pct(upside) if upside is not None else "—",
                          C.GREEN if (upside or 0) >= 15 else C.GOLD if (upside or 0) >= 5 else C.RED,
                          None)
            + _metric_row("Analyst Target",
                          fmt_price(analyst_tgt) if analyst_tgt else "—",
                          C.BLUE, None)
            + _metric_row("Analyst Upside",
                          fmt_pct(analyst_upside) if analyst_upside is not None else "—",
                          C.GREEN if (analyst_upside or 0) >= 10 else C.TEXT3, None)
            + _metric_row("Analyst High",
                          fmt_price(analyst_high) if analyst_high else "—",
                          C.TEXT3, None)
            + _metric_row("Analyst Low",
                          fmt_price(analyst_low) if analyst_low else "—",
                          C.TEXT3, None)
            + (f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:8px">'
               f'{analyst_n} analysts · consensus: '
               f'<b style="color:{C.BLUE}">{analyst_rating}</b></div>'
               if analyst_n else "")
            + f'</div></div>',
            unsafe_allow_html=True,
        )

    # ── Col 3: Quality score + verdict ────────────────────────
    with col_a:
        # Gauge chart
        st.plotly_chart(_gauge_chart(q_score, v_col),
                        use_container_width=True)

        # Score label
        st.markdown(
            f'<div style="text-align:center;margin-top:-8px;margin-bottom:12px">'
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px">Quality Score</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.4rem;'
            f'font-weight:700;color:{v_col}">{q_score}<span style="font-size:0.8rem;'
            f'color:{C.TEXT3}">/100</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Verdict box
        st.markdown(
            f'<div style="background:{v_col}12;border:1px solid {v_col}44;'
            f'border-radius:10px;padding:14px 16px">'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.75rem;'
            f'font-weight:700;color:{v_col};letter-spacing:1px;margin-bottom:8px">'
            f'⬡ {v_label}</div>'
            f'<div style="font-size:0.75rem;color:{C.TEXT2};line-height:1.6">'
            f'{v_reason}</div>'
            + (
                f'<div style="margin-top:10px;padding-top:8px;'
                f'border-top:1px solid {v_col}22;font-size:0.68rem;color:{C.TEXT3}">'
                f'Auto FV: <b style="color:{C.GOLD}">{fmt_price(auto_fv)}</b>'
                f'  ·  Upside: <b style="color:{v_col}">{fmt_pct(upside)}</b>'
                f'</div>'
                if auto_fv else ""
            )
            + f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Price chart ───────────────────────────────────────────
    st.markdown(section_title(f"📈  {ticker} — 1-Year Price Chart"),
                unsafe_allow_html=True)

    if not hist.empty:
        st.plotly_chart(
            _price_chart(hist, auto_fv, analyst_tgt),
            use_container_width=True,
        )
    else:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:20px;text-align:center;color:{C.TEXT3}">'
            f'Price history unavailable.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Business description ───────────────────────────────────
    if description:
        with st.expander("📋  Business Description", expanded=False):
            st.markdown(
                f'<div style="font-size:0.82rem;color:{C.TEXT2};line-height:1.8;'
                f'padding:8px 4px">{description}</div>',
                unsafe_allow_html=True,
            )

    # ── JJ Universe match ─────────────────────────────────────
    match = df_main[df_main["Ticker"] == ticker]
    if not match.empty:
        r = match.iloc[0]
        tier     = str(r.get("Tier", ""))
        verdict  = str(r.get("Verdict", ""))
        roic_jj  = r.get("ROIC %")
        fcf_jj   = r.get("FCF Margin %")
        fwdpe_jj = r.get("Fwd PE")
        epsg_jj  = r.get("EPS Growth %")
        tc       = C.TIER.get(tier, {})

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(section_title("🏅  JJ Research Data — This Stock Is in the Universe"),
                    unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.GREEN}33;'
            f'border-left:4px solid {C.GREEN};border-radius:10px;padding:18px 20px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
            f'<span style="background:{tc.get("bg",C.SURFACE2)};'
            f'color:{tc.get("color",C.TEXT)};padding:3px 10px;border-radius:4px;'
            f'font-size:0.7rem;font-weight:700">{tier}</span>'
            f'<span style="font-size:0.75rem;color:{C.TEXT2}">'
            f'JJ Research has this stock in the <b style="color:{C.GREEN}">approved universe</b>'
            f'</span>'
            f'</div>'
            f'<div style="font-size:0.8rem;color:{C.TEXT};line-height:1.7;'
            f'background:{C.SURFACE2};border-radius:6px;padding:10px 14px;margin-bottom:12px">'
            f'<b style="color:{C.GREEN}">Verdict:</b> {verdict}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">'
            + "".join([
                f'<div style="background:{C.SURFACE2};border-radius:6px;padding:10px">'
                f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
                f'letter-spacing:1px;margin-bottom:3px">{l}</div>'
                f'<div style="font-family:\'JetBrains Mono\',monospace;color:{C.GREEN};'
                f'font-size:0.88rem;font-weight:700">{v}</div>'
                f'</div>'
                for l, v in [
                    ("ROIC %",       f"{roic_jj}%" if roic_jj != "—" else "—"),
                    ("FCF Margin",   f"{fcf_jj}%"  if fcf_jj  != "—" else "—"),
                    ("Fwd PE",       f"{fwdpe_jj}x" if fwdpe_jj != "—" else "—"),
                    ("EPS Growth",   f"{epsg_jj}%"  if epsg_jj  != "—" else "—"),
                ]
            ])
            + f'</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="font-size:0.72rem;color:{C.TEXT3};margin-top:8px;'
            f'padding:10px 14px;background:{C.SURFACE};border-radius:6px;'
            f'border:1px solid {C.BORDER}">'
            f'ℹ️ <b>{ticker}</b> is not in the JJ Research universe. '
            f'Analysis above is calculated purely from market data.</div>',
            unsafe_allow_html=True,
        )

    # ── Disclaimer ────────────────────────────────────────────
    st.markdown(
        f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:20px;'
        f'padding:10px 14px;background:{C.SURFACE};border-radius:6px;'
        f'border:1px solid {C.BORDER}">'
        f'⚡ Data via yfinance · Price refreshes every 5 min · Fundamentals cached 1hr · '
        f'Auto FV uses PEG=1 model — not financial advice.</div>',
        unsafe_allow_html=True,
    )
