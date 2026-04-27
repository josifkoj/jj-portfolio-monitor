# app/pages/analyzer.py — Stock Research Tool
# Comprehensive deep-dive: hero header → verdict banner → valuation strip
# → 6 tabs (Overview · Valuation · Quality · Chart · Methods · Business)
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

from app import config as C
from app.styles import section_title, progress_bar, badge
from app.utils import fmt_price, fmt_pct, fmt_mktcap, pct52


# ═════════════════════════════════════════════════════════════
# DATA FETCHERS
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


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fundamentals(ticker: str) -> dict:
    out = {"fin": pd.DataFrame(), "bs": pd.DataFrame(),
           "cf": pd.DataFrame(), "hist": pd.DataFrame()}
    try:
        t = yf.Ticker(ticker)
        for k, fn in [("fin", lambda: t.financials),
                      ("bs",  lambda: t.balance_sheet),
                      ("cf",  lambda: t.cashflow),
                      ("hist", lambda: t.history(period="1y", interval="1d"))]:
            try: out[k] = fn()
            except Exception: pass
    except Exception:
        pass
    return out


# ═════════════════════════════════════════════════════════════
# CALCULATION HELPERS
# ═════════════════════════════════════════════════════════════

def _safe_row(df: pd.DataFrame, *keys) -> float | None:
    for k in keys:
        if k in df.index:
            try:
                v = df.loc[k].dropna()
                if not v.empty:
                    return float(v.iloc[0])
            except Exception:
                pass
    return None


def _calc_roic(fin, bs) -> float | None:
    if fin.empty or bs.empty:
        return None
    try:
        ebit = _safe_row(fin, "EBIT", "Operating Income", "Ebit", "OperatingIncome")
        if ebit is None: return None
        nopat = ebit * 0.79
        equity = _safe_row(bs, "Stockholders Equity", "Common Stock Equity",
                           "Total Equity Gross Minority Interest")
        debt   = _safe_row(bs, "Total Debt", "Long Term Debt") or 0.0
        cash   = _safe_row(bs, "Cash And Cash Equivalents",
                           "Cash Cash Equivalents And Short Term Investments") or 0.0
        if equity is None: return None
        ic = equity + debt - cash
        if ic <= 0: return None
        return round(nopat / ic * 100, 1)
    except Exception:
        return None


def _calc_fcf_margin(info, cf) -> float | None:
    rev = info.get("totalRevenue")
    fcf = info.get("freeCashflow")
    if not fcf and not cf.empty:
        fcf = _safe_row(cf, "Free Cash Flow", "FreeCashFlow")
    if fcf and rev and rev > 0:
        return round(fcf / rev * 100, 1)
    return None


def _intrinsic_value(fwd_eps, growth_pct):
    """PEG-anchored fair value with banded multiples."""
    if not fwd_eps or fwd_eps <= 0:
        return None, None
    if growth_pct is None or growth_pct <= 0:
        mult = 13.0
    elif growth_pct >= 30:
        mult = min(growth_pct * 1.4, 50)
    elif growth_pct >= 15:
        mult = growth_pct * 1.8
    else:
        mult = max(growth_pct * 2.2, 12)
    return round(fwd_eps * mult, 2), round(mult, 1)


def _quality_score(roic, fcf_m, gross_m, rev_g, de) -> int:
    s = 0
    if roic is not None:
        s += 25 if roic >= 25 else 18 if roic >= 15 else 10 if roic >= 8 else 4
    if fcf_m is not None:
        s += 20 if fcf_m >= 25 else 14 if fcf_m >= 15 else 8 if fcf_m >= 8 else 3
    if gross_m is not None:
        s += 15 if gross_m >= 60 else 10 if gross_m >= 40 else 6 if gross_m >= 25 else 2
    if rev_g is not None:
        s += 15 if rev_g >= 20 else 10 if rev_g >= 10 else 6 if rev_g >= 5 else 2
    if de is not None:
        s += 15 if de <= 0.3 else 10 if de <= 0.8 else 5 if de <= 1.5 else 1
    missing = sum(1 for x in (roic, fcf_m, gross_m, rev_g, de) if x is None)
    s += missing * 5
    return min(95, s)


def _verdict(score, upside) -> tuple[str, str, str]:
    u = upside or 0
    if score >= 72 and u >= 20:
        return "STRONG BUY",   C.GREEN, "Exceptional quality + significant upside to fair value."
    if score >= 60 and u >= 10:
        return "BUY",          C.GREEN, "High-quality business trading at a meaningful discount."
    if score >= 55 and u >= 0:
        return "WATCH",        C.GOLD,  "Good quality — wait for a better entry point."
    if score >= 42:
        return "HOLD",         C.BLUE,  "Decent fundamentals, limited upside or rich valuation."
    if score >= 28:
        return "WAIT",         "#FFB870", "Below-average quality. Need margin of safety."
    return "AVOID",            C.RED,   "Poor fundamentals — fails the JJ quality screen."


def _auto_tier(score) -> str:
    if score >= 70: return "T1"
    if score >= 50: return "T2"
    if score >= 30: return "T3"
    return "—"


def _hex_alpha(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ═════════════════════════════════════════════════════════════
# CHART HELPERS
# ═════════════════════════════════════════════════════════════

def _price_chart(hist, fv, analyst_tgt, cur):
    fig = go.Figure()
    if hist.empty:
        return fig

    # Volume on secondary axis
    if "Volume" in hist.columns:
        fig.add_trace(go.Bar(
            x=hist.index, y=hist["Volume"],
            marker_color=C.BORDER2, opacity=0.35,
            yaxis="y2", showlegend=False, name="Volume",
        ))

    # 50-day MA
    if len(hist) >= 50:
        ma50 = hist["Close"].rolling(50).mean()
        fig.add_trace(go.Scatter(
            x=hist.index, y=ma50, mode="lines",
            line=dict(color=C.PURPLE, width=1, dash="dot"),
            name="MA50", hoverinfo="skip",
        ))

    # 200-day MA
    if len(hist) >= 200:
        ma200 = hist["Close"].rolling(200).mean()
        fig.add_trace(go.Scatter(
            x=hist.index, y=ma200, mode="lines",
            line=dict(color=C.BLUE, width=1, dash="dot"),
            name="MA200", hoverinfo="skip",
        ))

    # Price
    fig.add_trace(go.Scatter(
        x=hist.index, y=hist["Close"], mode="lines",
        line=dict(color=C.GREEN, width=2.2),
        fill="tozeroy", fillcolor=_hex_alpha(C.GREEN, 0.07),
        name="Price",
        hovertemplate="<b>%{x|%b %d %Y}</b><br>$%{y:.2f}<extra></extra>",
    ))

    if fv:
        fig.add_hline(y=fv, line_dash="dash", line_color=C.GOLD, line_width=1.2,
                      annotation_text=f"  Intrinsic ${fv:.0f}",
                      annotation_font_color=C.GOLD, annotation_font_size=10)
    if analyst_tgt:
        fig.add_hline(y=analyst_tgt, line_dash="dot", line_color=C.BLUE, line_width=1.2,
                      annotation_text=f"  Analyst ${analyst_tgt:.0f}",
                      annotation_font_color=C.BLUE, annotation_font_size=10)

    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=420,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(gridcolor=C.BORDER, showspikes=True, spikecolor=C.BORDER2),
        yaxis=dict(title="Price ($)", gridcolor=C.BORDER, tickprefix="$",
                   showspikes=True, spikecolor=C.BORDER2),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    showticklabels=False,
                    range=[0, hist["Volume"].max() * 6] if "Volume" in hist.columns else [0, 1]),
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=C.SURFACE, bordercolor=C.GREEN,
                        font=dict(family="JetBrains Mono", size=11)),
    )
    return fig


def _gauge(score, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        number={"font": {"color": color, "family": "JetBrains Mono", "size": 36}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": C.TEXT3,
                     "tickfont": {"size": 9, "color": C.TEXT3}},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": C.SURFACE2, "borderwidth": 0,
            "steps": [
                {"range": [0,  30], "color": _hex_alpha(C.RED,   0.13)},
                {"range": [30, 55], "color": _hex_alpha(C.GOLD,  0.13)},
                {"range": [55, 75], "color": _hex_alpha(C.GREEN, 0.13)},
                {"range": [75, 100],"color": _hex_alpha(C.GREEN, 0.26)},
            ],
            "threshold": {"line": {"color": color, "width": 3},
                          "thickness": 0.78, "value": score},
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", font_color=C.TEXT2,
        height=200, margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


# ═════════════════════════════════════════════════════════════
# UI BUILDING BLOCKS
# ═════════════════════════════════════════════════════════════

def _kpi_card(label, value, color=None, sub=""):
    color = color or C.TEXT
    sub_html = (f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:3px">{sub}</div>'
                if sub else "")
    return (
        f'<div style="background:{C.SURFACE2};border:1px solid {C.BORDER};'
        f'border-radius:10px;padding:14px 16px">'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.4px;font-weight:600;margin-bottom:6px">{label}</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;color:{color};'
        f'font-size:1.15rem;font-weight:700">{value}</div>'
        f'{sub_html}</div>'
    )


def _metric_row(label, value, color, bar_pct=None, bar_col=None):
    bar = progress_bar(bar_pct, bar_col or color, height=4) if bar_pct is not None else ""
    return (
        f'<div style="padding:8px 0;border-bottom:1px solid {C.BORDER}">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<span style="font-size:0.76rem;color:{C.TEXT3}">{label}</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.84rem;'
        f'font-weight:700;color:{color}">{value}</span>'
        f'</div>{bar}</div>'
    )


def _scorecard_row(label, value, passed, threshold_text):
    if passed is True:
        icon, col = "✓", C.GREEN
    elif passed is False:
        icon, col = "✗", C.RED
    else:
        icon, col = "—", C.TEXT3
    return (
        f'<div style="display:flex;align-items:center;padding:10px 14px;'
        f'border-bottom:1px solid {C.BORDER}">'
        f'<span style="font-size:1rem;color:{col};width:24px;font-weight:700">{icon}</span>'
        f'<span style="flex:1;font-size:0.78rem;color:{C.TEXT}">{label}</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;'
        f'font-weight:700;color:{col};margin-right:14px">{value}</span>'
        f'<span style="font-size:0.68rem;color:{C.TEXT3};min-width:90px;'
        f'text-align:right">{threshold_text}</span>'
        f'</div>'
    )


def _section_card(title, body_html, accent=C.GREEN, icon=""):
    return (
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-left:3px solid {accent};border-radius:10px;'
        f'padding:16px 18px;margin-bottom:14px">'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.7rem;'
        f'font-weight:700;color:{accent};text-transform:uppercase;letter-spacing:1.5px;'
        f'margin-bottom:10px">{icon} {title}</div>'
        f'{body_html}</div>'
    )


# ═════════════════════════════════════════════════════════════
# MAIN RENDER
# ═════════════════════════════════════════════════════════════

def render(df_main: pd.DataFrame, prices: dict):
    # ── Header & search ──────────────────────────────────────
    st.markdown(section_title("🔬  Stock Research"), unsafe_allow_html=True)

    sc1, sc2 = st.columns([5, 1])
    raw = sc1.text_input("", placeholder="Enter any S&P 500 ticker  ·  e.g. AAPL  MSFT  NVDA  GOOGL  BRK-B",
                         key="research_input", label_visibility="collapsed")
    go_btn = sc2.button("🔍  Research", use_container_width=True, key="research_go",
                        type="primary")

    ticker = raw.strip().upper()
    if go_btn and ticker:
        st.session_state["research_tk"] = ticker
    if not ticker and "research_tk" in st.session_state:
        ticker = st.session_state["research_tk"]

    if not ticker:
        _empty_state()
        return

    # ── Fetch ────────────────────────────────────────────────
    with st.spinner(f"Fetching data for {ticker}…"):
        info = _fetch_info(ticker)
    if not info:
        st.error(f"❌  Could not fetch data for **{ticker}** — check the symbol.")
        return
    with st.spinner("Computing fundamentals…"):
        fd = _fetch_fundamentals(ticker)

    fin, bs, cf, hist = fd["fin"], fd["bs"], fd["cf"], fd["hist"]

    # ── Extract & compute everything ─────────────────────────
    ctx = _build_context(ticker, info, fin, bs, cf, hist, df_main)

    # ── HERO ─────────────────────────────────────────────────
    _render_hero(ctx)

    # ── VERDICT BANNER ───────────────────────────────────────
    _render_verdict_banner(ctx)

    # ── VALUATION SNAPSHOT STRIP ─────────────────────────────
    _render_valuation_strip(ctx)

    # ── TABS ─────────────────────────────────────────────────
    t_overview, t_val, t_quality, t_chart, t_methods, t_biz = st.tabs([
        "📊  Overview", "💰  Valuation", "🏆  Quality",
        "📈  Chart", "🧮  Methods", "🏢  Business",
    ])
    with t_overview: _tab_overview(ctx)
    with t_val:      _tab_valuation(ctx)
    with t_quality:  _tab_quality(ctx)
    with t_chart:    _tab_chart(ctx)
    with t_methods:  _tab_methods(ctx)
    with t_biz:      _tab_business(ctx)

    # ── Footer disclaimer ────────────────────────────────────
    st.markdown(
        f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:24px;'
        f'padding:10px 14px;background:{C.SURFACE};border-radius:6px;'
        f'border:1px solid {C.BORDER}">'
        f'⚡ Live price refresh 5 min · Fundamentals cached 1 hr · '
        f'PEG-banded intrinsic value model · '
        f'<b>Educational use only — not financial advice.</b></div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# CONTEXT BUILDER — computes everything once
# ═════════════════════════════════════════════════════════════

def _build_context(ticker, info, fin, bs, cf, hist, df_main):
    cur        = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    chg_pct    = ((cur - prev_close) / prev_close * 100) if cur and prev_close else None

    # Margins to %
    pct = lambda x: round(x * 100, 1) if x is not None else None

    gross_m = pct(info.get("grossMargins"))
    op_m    = pct(info.get("operatingMargins"))
    net_m   = pct(info.get("profitMargins"))
    roe     = pct(info.get("returnOnEquity"))
    roa     = pct(info.get("returnOnAssets"))
    rev_g   = pct(info.get("revenueGrowth"))
    eps_g   = pct(info.get("earningsGrowth"))
    de_raw  = info.get("debtToEquity")
    de      = round(de_raw / 100, 2) if de_raw is not None else None

    roic    = _calc_roic(fin, bs)
    fcf_m   = _calc_fcf_margin(info, cf)
    fcf_yld = (info.get("freeCashflow") / info.get("marketCap") * 100
               if info.get("freeCashflow") and info.get("marketCap") else None)

    fwd_eps = info.get("forwardEps")
    growth  = eps_g or rev_g
    intrinsic, multiple_used = _intrinsic_value(fwd_eps, growth)
    upside  = round((intrinsic - cur) / cur * 100, 1) if (intrinsic and cur) else None

    analyst_tgt = info.get("targetMeanPrice")
    analyst_up  = round((analyst_tgt - cur) / cur * 100, 1) if (analyst_tgt and cur) else None

    # Combined upside (avg of model + analyst)
    if upside is not None and analyst_up is not None:
        combined = round((upside + analyst_up) / 2, 1)
    else:
        combined = upside if upside is not None else analyst_up

    score = _quality_score(roic, fcf_m, gross_m, rev_g, de)
    v_label, v_col, v_reason = _verdict(score, upside)

    in_universe = False
    jj = {}
    if df_main is not None:
        match = df_main[df_main["Ticker"] == ticker]
        if not match.empty:
            in_universe = True
            r = match.iloc[0]
            jj = {
                "tier":    str(r.get("Tier", "")),
                "verdict": str(r.get("Verdict", "")),
                "moat":    str(r.get("Moat Type", "")),
                "roic":    r.get("ROIC %"),
                "fcf":     r.get("FCF Margin %"),
                "gross":   r.get("Gross Margin %"),
                "fwd_pe":  r.get("Fwd PE"),
                "eps_g":   r.get("EPS Growth %"),
                "pricing_power":     r.get("Pricing Power"),
                "capital_allocation":r.get("Capital Allocation"),
                "sector":  r.get("Sector"),
            }

    return {
        "ticker": ticker, "info": info, "hist": hist,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "sector":   info.get("sector", "—"),
        "industry": info.get("industry", "—"),
        "description": info.get("longBusinessSummary", ""),
        "cur": cur, "prev_close": prev_close, "chg_pct": chg_pct,
        "high52": info.get("fiftyTwoWeekHigh"), "low52": info.get("fiftyTwoWeekLow"),
        "mktcap": info.get("marketCap"), "beta": info.get("beta"),
        "div_yield": info.get("dividendYield"),
        "pe_ttm": info.get("trailingPE"), "fwd_pe": info.get("forwardPE"),
        "trailing_eps": info.get("trailingEps"), "fwd_eps": fwd_eps,
        "pb": info.get("priceToBook"), "ps": info.get("priceToSalesTrailingTwelveMonths"),
        "ev_rev":   info.get("enterpriseToRevenue"),
        "ev_ebitda":info.get("enterpriseToEbitda"),
        "gross_m": gross_m, "op_m": op_m, "net_m": net_m,
        "roic": roic, "roe": roe, "roa": roa,
        "rev_g": rev_g, "eps_g": eps_g, "growth_used": growth,
        "fcf_m": fcf_m, "fcf_yld": fcf_yld,
        "de": de, "current_ratio": info.get("currentRatio"),
        "quick_ratio":   info.get("quickRatio"),
        "intrinsic": intrinsic, "intrinsic_multiple": multiple_used,
        "upside_model": upside,
        "analyst_tgt": analyst_tgt, "analyst_up": analyst_up,
        "analyst_high": info.get("targetHighPrice"),
        "analyst_low":  info.get("targetLowPrice"),
        "analyst_n":    info.get("numberOfAnalystOpinions"),
        "analyst_rating": info.get("recommendationKey", "").upper().replace("_", " "),
        "combined_upside": combined,
        "score": score, "v_label": v_label, "v_col": v_col, "v_reason": v_reason,
        "tier_auto": _auto_tier(score),
        "in_universe": in_universe, "jj": jj,
        "insider_pct":      info.get("heldPercentInsiders"),
        "institution_pct":  info.get("heldPercentInstitutions"),
        "short_ratio":      info.get("shortRatio"),
        "shares_short_pct": info.get("shortPercentOfFloat"),
        "pos52": pct52(cur, info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")),
    }


# ═════════════════════════════════════════════════════════════
# HERO HEADER
# ═════════════════════════════════════════════════════════════

def _render_hero(c):
    chg_col = C.GREEN if (c["chg_pct"] or 0) >= 0 else C.RED
    badges = []
    if c["beta"]:
        badges.append(f"β <b style='color:{C.TEXT}'>{c['beta']:.2f}</b>")
    if c["div_yield"]:
        badges.append(
            f"Yield <b style='color:{C.GOLD}'>{c['div_yield']*100:.2f}%</b>"
        )
    extras = "  ·  ".join(badges)

    pos52_html = ""
    if c["pos52"] is not None:
        pos52_html = (
            f'<div style="margin-top:14px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:0.65rem;color:{C.TEXT3};margin-bottom:4px">'
            f'<span>52wk Low {fmt_price(c["low52"])}</span>'
            f'<span style="color:{C.TEXT2}">{c["pos52"]:.0f}% of range</span>'
            f'<span>52wk High {fmt_price(c["high52"])}</span>'
            f'</div>'
            + progress_bar(c["pos52"], C.GREEN, height=6)
            + f'</div>'
        )

    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-top:3px solid {C.GREEN};border-radius:12px;'
        f'padding:20px 24px;margin-top:14px;margin-bottom:14px">'
        f'<div style="display:flex;justify-content:space-between;align-items:start;gap:20px">'
        # left
        f'<div style="flex:1">'
        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.7rem;'
        f'font-weight:700;color:{C.GREEN}">{c["ticker"]}</span>'
        f'<span style="background:{C.SURFACE2};color:{C.TEXT};padding:3px 10px;'
        f'border-radius:4px;font-size:0.72rem">{c["sector"]}</span>'
        f'<span style="background:{C.SURFACE2};color:{C.TEXT3};padding:3px 10px;'
        f'border-radius:4px;font-size:0.7rem">{c["industry"]}</span>'
        f'</div>'
        f'<div style="font-size:0.92rem;color:{C.TEXT2};margin-bottom:4px">{c["name"]}</div>'
        f'<div style="font-size:0.7rem;color:{C.TEXT3}">'
        f'Mkt Cap <b style="color:{C.TEXT}">{fmt_mktcap(c["mktcap"])}</b>'
        + (f"  ·  {extras}" if extras else "")
        + f'</div></div>'
        # right (price)
        f'<div style="text-align:right">'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2.1rem;'
        f'font-weight:700;color:{C.TEXT};line-height:1.1">{fmt_price(c["cur"])}</div>'
        f'<div style="font-size:0.85rem;color:{chg_col};font-weight:600;margin-top:2px">'
        f'{fmt_pct(c["chg_pct"])} today</div></div>'
        f'</div>'
        + pos52_html
        + f'</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# VERDICT BANNER
# ═════════════════════════════════════════════════════════════

def _render_verdict_banner(c):
    # Choose direction icon
    arrow = "↑" if (c["combined_upside"] or 0) >= 0 else "↓"
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{c["v_col"]}1A,{C.SURFACE} 60%);'
        f'border:1px solid {c["v_col"]}55;border-left:4px solid {c["v_col"]};'
        f'border-radius:12px;padding:18px 22px;margin-bottom:14px;'
        f'display:flex;align-items:center;gap:24px;flex-wrap:wrap">'
        f'<div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.4rem;'
        f'font-weight:800;color:{c["v_col"]};letter-spacing:1.5px">'
        f'⬡ {c["v_label"]}</div>'
        f'<div style="font-size:0.78rem;color:{C.TEXT2};margin-top:4px">{c["v_reason"]}</div>'
        f'</div>'
        f'<div style="margin-left:auto;display:flex;gap:14px;flex-wrap:wrap">'
        f'<div style="text-align:center;padding:0 14px;border-left:1px solid {C.BORDER}">'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.4px">Quality</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.4rem;'
        f'font-weight:700;color:{c["v_col"]}">{c["score"]}<span style="font-size:0.7rem;'
        f'color:{C.TEXT3}">/100</span></div></div>'
        f'<div style="text-align:center;padding:0 14px;border-left:1px solid {C.BORDER}">'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.4px">Tier</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.4rem;'
        f'font-weight:700;color:{C.TEXT}">{c["jj"].get("tier") or c["tier_auto"]}</div></div>'
        + (f'<div style="text-align:center;padding:0 14px;border-left:1px solid {C.BORDER}">'
           f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
           f'letter-spacing:1.4px">Combined Upside</div>'
           f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.4rem;'
           f'font-weight:700;color:'
           f'{C.GREEN if c["combined_upside"] >= 0 else C.RED}">'
           f'{arrow} {abs(c["combined_upside"]):.1f}%</div></div>'
           if c["combined_upside"] is not None else "")
        + f'</div></div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# VALUATION STRIP
# ═════════════════════════════════════════════════════════════

def _render_valuation_strip(c):
    cu = c["combined_upside"]
    if cu is None:
        up_col, up_text, up_status = C.TEXT3, "—", "N/A"
    elif cu >= 0:
        up_col, up_text, up_status = C.GREEN, f"+{cu:.1f}%", "UNDERVALUED"
    else:
        up_col, up_text, up_status = C.RED, f"{cu:.1f}%", "OVERVALUED"

    def cell(label, value, color, sub=""):
        return (
            f'<div style="flex:1;padding:14px 18px;border-right:1px solid {C.BORDER}">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin-bottom:6px">{label}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.35rem;'
            f'font-weight:700;color:{color}">{value}</div>'
            + (f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:3px">{sub}</div>'
               if sub else "")
            + f'</div>'
        )

    chg_col = C.GREEN if (c["chg_pct"] or 0) >= 0 else C.RED

    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:12px;margin-bottom:18px;display:flex;overflow:hidden">'
        + cell("Current Price", fmt_price(c["cur"]), C.TEXT,
               f'<span style="color:{chg_col}">{fmt_pct(c["chg_pct"])} today</span>'
               if c["chg_pct"] is not None else "")
        + cell("Intrinsic Value",
               fmt_price(c["intrinsic"]) if c["intrinsic"] else "—",
               C.GOLD, f"PEG model · {c['intrinsic_multiple']}× fwd EPS"
               if c["intrinsic"] else "Need fwd EPS")
        + cell("Analyst Target",
               fmt_price(c["analyst_tgt"]) if c["analyst_tgt"] else "—",
               C.BLUE,
               f"{c['analyst_n']} analysts · {c['analyst_rating']}"
               if c["analyst_n"] else "")
        + f'<div style="flex:1;padding:14px 18px;background:{up_col}14">'
          f'<div style="font-size:0.58rem;color:{up_col};text-transform:uppercase;'
          f'letter-spacing:1.5px;font-weight:700;margin-bottom:6px">'
          f'Upside · {up_status}</div>'
          f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.35rem;'
          f'font-weight:700;color:{up_col}">{up_text}</div>'
          f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:3px">'
          + ("Model " + fmt_pct(c["upside_model"]) if c["upside_model"] is not None else "")
          + (" · Analyst " + fmt_pct(c["analyst_up"]) if c["analyst_up"] is not None else "")
          + f'</div></div>'
        + f'</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# TAB · OVERVIEW (profile + bull/bear + scorecard + gauge)
# ═════════════════════════════════════════════════════════════

def _bull_bear(c):
    bull, bear = [], []
    if c["roic"] is not None:
        (bull if c["roic"] >= 15 else bear).append(
            f"ROIC of <b>{c['roic']:.1f}%</b> "
            f"({'strong moat' if c['roic'] >= 15 else 'capital-inefficient'})"
        )
    if c["fcf_m"] is not None:
        (bull if c["fcf_m"] >= 15 else bear).append(
            f"FCF margin <b>{c['fcf_m']:.1f}%</b> "
            f"({'high cash conversion' if c['fcf_m'] >= 15 else 'weak cash generation'})"
        )
    if c["gross_m"] is not None:
        (bull if c["gross_m"] >= 50 else bear).append(
            f"Gross margin <b>{c['gross_m']:.1f}%</b> "
            f"({'pricing power' if c['gross_m'] >= 50 else 'commodity-like economics'})"
        )
    if c["rev_g"] is not None:
        (bull if c["rev_g"] >= 10 else bear).append(
            f"Revenue growth <b>{fmt_pct(c['rev_g'], sign=True)}</b>"
        )
    if c["de"] is not None:
        (bull if c["de"] <= 0.8 else bear).append(
            f"Debt/Equity <b>{c['de']:.2f}x</b> "
            f"({'healthy balance sheet' if c['de'] <= 0.8 else 'leveraged'})"
        )
    if c["upside_model"] is not None:
        (bull if c["upside_model"] >= 10 else bear).append(
            f"Intrinsic value upside <b>{fmt_pct(c['upside_model'])}</b>"
        )
    if c["analyst_up"] is not None:
        (bull if c["analyst_up"] >= 5 else bear).append(
            f"Analyst consensus upside <b>{fmt_pct(c['analyst_up'])}</b>"
        )
    if c["fwd_pe"]:
        (bull if c["fwd_pe"] < 25 else bear).append(
            f"Forward PE <b>{c['fwd_pe']:.1f}x</b> "
            f"({'reasonable' if c['fwd_pe'] < 25 else 'rich'})"
        )
    return bull, bear


def _tab_overview(c):
    # Stock Profile (universal)
    src_col   = C.GREEN if c["in_universe"] else C.BLUE
    src_label = "JJ RESEARCH UNIVERSE" if c["in_universe"] else "AUTO-COMPUTED"
    src_note  = ("Curated by JJ Research." if c["in_universe"]
                 else "Computed from yfinance fundamentals.")

    if c["in_universe"]:
        tier    = c["jj"]["tier"] or c["tier_auto"]
        verdict = c["jj"]["verdict"] or c["v_reason"]
        roic_v  = c["jj"]["roic"]
        fcf_v   = c["jj"]["fcf"]
        fpe_v   = c["jj"]["fwd_pe"]
        epsg_v  = c["jj"]["eps_g"]
    else:
        tier    = c["tier_auto"]
        verdict = c["v_reason"]
        roic_v  = f"{c['roic']:.1f}" if c["roic"] is not None else "—"
        fcf_v   = f"{c['fcf_m']:.1f}" if c["fcf_m"] is not None else "—"
        fpe_v   = f"{c['fwd_pe']:.1f}" if c["fwd_pe"] else "—"
        epsg_v  = f"{c['eps_g']:.1f}" if c["eps_g"] is not None else "—"

    tc = C.TIER.get(tier, {"color": C.TEXT, "bg": C.SURFACE2})

    def kpi(lbl, val, col):
        return (
            f'<div style="background:{C.SURFACE2};border-radius:8px;padding:12px 14px;'
            f'border:1px solid {C.BORDER}">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.2px;font-weight:600;margin-bottom:4px">{lbl}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;color:{col};'
            f'font-size:1.1rem;font-weight:700">{val}</div></div>'
        )

    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {src_col}33;'
        f'border-left:4px solid {src_col};border-radius:12px;padding:18px 22px;'
        f'margin-bottom:16px">'
        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px">'
        f'<span style="background:{tc.get("bg",C.SURFACE2)};color:{tc.get("color",C.TEXT)};'
        f'padding:4px 12px;border-radius:5px;font-size:0.72rem;font-weight:700">TIER {tier}</span>'
        f'<span style="background:{c["v_col"]}18;color:{c["v_col"]};padding:4px 12px;'
        f'border-radius:5px;font-size:0.72rem;font-weight:700">⬡ {c["v_label"]}</span>'
        f'<span style="background:{src_col}14;color:{src_col};padding:4px 12px;'
        f'border-radius:5px;font-size:0.65rem;font-weight:700;letter-spacing:1px">{src_label}</span>'
        f'<span style="font-size:0.7rem;color:{C.TEXT3};margin-left:auto">{src_note}</span>'
        f'</div>'
        f'<div style="font-size:0.82rem;color:{C.TEXT};line-height:1.7;'
        f'background:{C.SURFACE2};border-radius:8px;padding:12px 16px;margin-bottom:14px;'
        f'border-left:3px solid {c["v_col"]}">'
        f'<b style="color:{c["v_col"]}">Verdict:</b> {verdict}</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">'
        + kpi("ROIC %",     f"{roic_v}%" if roic_v not in ("—", None) else "—", C.GREEN)
        + kpi("FCF Margin", f"{fcf_v}%"  if fcf_v  not in ("—", None) else "—", C.TEAL)
        + kpi("Fwd PE",     f"{fpe_v}x"  if fpe_v  not in ("—", None) else "—", C.GOLD)
        + kpi("EPS Growth", f"{epsg_v}%" if epsg_v not in ("—", None) else "—", C.BLUE)
        + f'</div></div>',
        unsafe_allow_html=True,
    )

    # Bull / Bear case
    bull, bear = _bull_bear(c)
    col_bull, col_bear = st.columns(2)
    with col_bull:
        body = ("<ul style='margin:0;padding-left:20px;line-height:1.9;font-size:0.82rem;"
                f"color:{C.TEXT2}'>"
                + "".join(f"<li>{b}</li>" for b in bull or ["—"])
                + "</ul>")
        st.markdown(_section_card("Bull Case", body, C.GREEN, "🟢"),
                    unsafe_allow_html=True)
    with col_bear:
        body = ("<ul style='margin:0;padding-left:20px;line-height:1.9;font-size:0.82rem;"
                f"color:{C.TEXT2}'>"
                + "".join(f"<li>{b}</li>" for b in bear or ["—"])
                + "</ul>")
        st.markdown(_section_card("Bear Case", body, C.RED, "🔴"),
                    unsafe_allow_html=True)

    # Quality gauge + scorecard
    col_g, col_s = st.columns([1, 2])
    with col_g:
        st.plotly_chart(_gauge(c["score"], c["v_col"]), use_container_width=True)
        st.markdown(
            f'<div style="text-align:center;margin-top:-12px">'
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.4px">Quality Score</div></div>',
            unsafe_allow_html=True,
        )
    with col_s:
        rows = [
            ("ROIC ≥ 15%",       f"{c['roic']:.1f}%" if c['roic'] is not None else "—",
             None if c['roic'] is None else c['roic'] >= 15, "Threshold 15%"),
            ("FCF Margin ≥ 15%", f"{c['fcf_m']:.1f}%" if c['fcf_m'] is not None else "—",
             None if c['fcf_m'] is None else c['fcf_m'] >= 15, "Threshold 15%"),
            ("Gross Margin ≥ 40%", f"{c['gross_m']:.1f}%" if c['gross_m'] is not None else "—",
             None if c['gross_m'] is None else c['gross_m'] >= 40, "Threshold 40%"),
            ("Revenue Growth ≥ 10%", fmt_pct(c['rev_g']) if c['rev_g'] is not None else "—",
             None if c['rev_g'] is None else c['rev_g'] >= 10, "Threshold 10%"),
            ("Debt / Equity ≤ 0.8", f"{c['de']:.2f}x" if c['de'] is not None else "—",
             None if c['de'] is None else c['de'] <= 0.8, "Threshold 0.8x"),
            ("Forward PE < 25",  f"{c['fwd_pe']:.1f}x" if c['fwd_pe'] else "—",
             None if not c['fwd_pe'] else c['fwd_pe'] < 25, "Threshold 25x"),
            ("Combined Upside ≥ 10%",
             fmt_pct(c['combined_upside']) if c['combined_upside'] is not None else "—",
             None if c['combined_upside'] is None else c['combined_upside'] >= 10,
             "Threshold +10%"),
        ]
        body = "".join(_scorecard_row(*r) for r in rows)
        st.markdown(
            _section_card("Investment Scorecard",
                          f'<div style="margin:-4px -2px">{body}</div>',
                          C.GOLD, "📋"),
            unsafe_allow_html=True,
        )


# ═════════════════════════════════════════════════════════════
# TAB · VALUATION
# ═════════════════════════════════════════════════════════════

def _tab_valuation(c):
    c1, c2 = st.columns([1, 1])
    with c1:
        body = (
            _metric_row("PE (TTM)",       f"{c['pe_ttm']:.1f}x" if c['pe_ttm'] else "—",
                        C.GREEN if c['pe_ttm'] and c['pe_ttm'] < 20 else C.GOLD if c['pe_ttm'] and c['pe_ttm'] < 35 else C.RED)
            + _metric_row("Forward PE",   f"{c['fwd_pe']:.1f}x" if c['fwd_pe'] else "—",
                        C.GREEN if c['fwd_pe'] and c['fwd_pe'] < 20 else C.GOLD if c['fwd_pe'] and c['fwd_pe'] < 30 else C.RED)
            + _metric_row("Price / Book", f"{c['pb']:.1f}x" if c['pb'] else "—",
                        C.GREEN if c['pb'] and c['pb'] < 3 else C.GOLD if c['pb'] and c['pb'] < 8 else C.TEXT3)
            + _metric_row("Price / Sales", f"{c['ps']:.1f}x" if c['ps'] else "—",
                        C.GREEN if c['ps'] and c['ps'] < 5 else C.GOLD if c['ps'] and c['ps'] < 12 else C.TEXT3)
            + _metric_row("EV / Revenue", f"{c['ev_rev']:.1f}x" if c['ev_rev'] else "—",
                        C.GREEN if c['ev_rev'] and c['ev_rev'] < 5 else C.GOLD)
            + _metric_row("EV / EBITDA",  f"{c['ev_ebitda']:.1f}x" if c['ev_ebitda'] else "—",
                        C.GREEN if c['ev_ebitda'] and c['ev_ebitda'] < 15 else C.GOLD)
            + _metric_row("FCF Yield",    fmt_pct(c['fcf_yld'], sign=False) if c['fcf_yld'] else "—",
                        C.GREEN if (c['fcf_yld'] or 0) >= 4 else C.GOLD)
            + _metric_row("EPS (TTM)",    fmt_price(c['trailing_eps']) if c['trailing_eps'] else "—",
                        C.GREEN if (c['trailing_eps'] or 0) > 0 else C.RED)
            + _metric_row("EPS (Fwd)",    fmt_price(c['fwd_eps']) if c['fwd_eps'] else "—",
                        C.GREEN if (c['fwd_eps'] or 0) > (c['trailing_eps'] or 0) else C.TEXT3)
        )
        st.markdown(_section_card("Multiples", body, C.GOLD, "💰"),
                    unsafe_allow_html=True)

    with c2:
        # Fair Value walkthrough
        iv_str = fmt_price(c['intrinsic']) if c['intrinsic'] else "—"
        body = (
            f"<div style='font-size:0.78rem;color:{C.TEXT2};line-height:1.7;margin-bottom:10px'>"
            f"PEG-anchored fair value model with growth-banded multiples and a 50× cap to "
            f"avoid bubble valuations.</div>"
            f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px'>"
            + _kpi_card("Forward EPS", fmt_price(c['fwd_eps']) if c['fwd_eps'] else "—", C.TEXT)
            + _kpi_card("Growth Used", fmt_pct(c['growth_used']) if c['growth_used'] is not None else "—", C.BLUE)
            + _kpi_card("Multiple", f"{c['intrinsic_multiple']}×" if c['intrinsic_multiple'] else "—", C.PURPLE)
            + _kpi_card("Intrinsic Value", iv_str, C.GOLD)
            + f'</div>'
            + _metric_row("Current Price", fmt_price(c['cur']), C.TEXT)
            + _metric_row("Model Upside", fmt_pct(c['upside_model']) if c['upside_model'] is not None else "—",
                          C.GREEN if (c['upside_model'] or 0) >= 10 else
                          C.GOLD  if (c['upside_model'] or 0) >= 0  else C.RED)
        )
        st.markdown(_section_card("Intrinsic Value", body, C.GOLD, "🎯"),
                    unsafe_allow_html=True)

        # Analyst section
        body = (
            _metric_row("Analyst Mean", fmt_price(c['analyst_tgt']) if c['analyst_tgt'] else "—", C.BLUE)
            + _metric_row("Analyst High", fmt_price(c['analyst_high']) if c['analyst_high'] else "—", C.GREEN)
            + _metric_row("Analyst Low", fmt_price(c['analyst_low']) if c['analyst_low'] else "—", C.RED)
            + _metric_row("Analyst Upside",
                          fmt_pct(c['analyst_up']) if c['analyst_up'] is not None else "—",
                          C.GREEN if (c['analyst_up'] or 0) >= 10 else C.GOLD)
            + (f'<div style="font-size:0.7rem;color:{C.TEXT3};margin-top:8px">'
               f"<b style='color:{C.TEXT2}'>{c['analyst_n']}</b> analysts · consensus "
               f"<b style='color:{C.BLUE}'>{c['analyst_rating']}</b></div>"
               if c['analyst_n'] else "")
        )
        st.markdown(_section_card("Analyst Targets", body, C.BLUE, "📊"),
                    unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · QUALITY
# ═════════════════════════════════════════════════════════════

def _tab_quality(c):
    c1, c2 = st.columns([1, 1])
    with c1:
        body = (
            _metric_row("ROIC %", f"{c['roic']:.1f}%" if c['roic'] is not None else "—",
                        C.GREEN if (c['roic'] or 0) >= 15 else C.GOLD if (c['roic'] or 0) >= 8 else C.RED,
                        min(int(c['roic'] or 0), 100), C.GREEN)
            + _metric_row("ROE %", f"{c['roe']:.1f}%" if c['roe'] is not None else "—",
                          C.GREEN if (c['roe'] or 0) >= 20 else C.GOLD if (c['roe'] or 0) >= 10 else C.TEXT3,
                          min(int(c['roe'] or 0), 100), C.GREEN)
            + _metric_row("ROA %", f"{c['roa']:.1f}%" if c['roa'] is not None else "—",
                          C.GREEN if (c['roa'] or 0) >= 8 else C.GOLD if (c['roa'] or 0) >= 4 else C.TEXT3,
                          min(int(c['roa'] or 0) * 5, 100), C.GREEN)
            + _metric_row("Gross Margin", f"{c['gross_m']:.1f}%" if c['gross_m'] is not None else "—",
                          C.GREEN if (c['gross_m'] or 0) >= 50 else C.GOLD,
                          min(int(c['gross_m'] or 0), 100), C.GREEN)
            + _metric_row("Operating Margin", f"{c['op_m']:.1f}%" if c['op_m'] is not None else "—",
                          C.GREEN if (c['op_m'] or 0) >= 20 else C.GOLD,
                          min(int(c['op_m'] or 0), 100), C.GOLD)
            + _metric_row("Net Margin", f"{c['net_m']:.1f}%" if c['net_m'] is not None else "—",
                          C.GREEN if (c['net_m'] or 0) >= 15 else C.GOLD,
                          min(int(c['net_m'] or 0), 100), C.TEAL)
            + _metric_row("FCF Margin", f"{c['fcf_m']:.1f}%" if c['fcf_m'] is not None else "—",
                          C.GREEN if (c['fcf_m'] or 0) >= 15 else C.GOLD,
                          min(int(c['fcf_m'] or 0), 100), C.GREEN)
        )
        st.markdown(_section_card("Profitability", body, C.GREEN, "💎"),
                    unsafe_allow_html=True)

    with c2:
        body = (
            _metric_row("Revenue Growth", fmt_pct(c['rev_g']) if c['rev_g'] is not None else "—",
                        C.GREEN if (c['rev_g'] or 0) >= 10 else C.GOLD if (c['rev_g'] or 0) >= 5 else C.RED)
            + _metric_row("EPS Growth", fmt_pct(c['eps_g']) if c['eps_g'] is not None else "—",
                          C.GREEN if (c['eps_g'] or 0) >= 10 else C.GOLD if (c['eps_g'] or 0) >= 5 else C.RED)
            + _metric_row("Debt / Equity", f"{c['de']:.2f}x" if c['de'] is not None else "—",
                          C.GREEN if (c['de'] or 99) <= 0.5 else C.GOLD if (c['de'] or 99) <= 1.2 else C.RED)
            + _metric_row("Current Ratio", f"{c['current_ratio']:.2f}x" if c['current_ratio'] else "—",
                          C.GREEN if (c['current_ratio'] or 0) >= 1.5 else C.GOLD if (c['current_ratio'] or 0) >= 1 else C.RED)
            + _metric_row("Quick Ratio", f"{c['quick_ratio']:.2f}x" if c['quick_ratio'] else "—",
                          C.GREEN if (c['quick_ratio'] or 0) >= 1 else C.GOLD)
            + _metric_row("Beta",
                          f"{c['beta']:.2f}" if c['beta'] else "—",
                          C.GREEN if c['beta'] and 0.7 <= c['beta'] <= 1.2 else C.GOLD)
        )
        st.markdown(_section_card("Growth & Balance Sheet", body, C.BLUE, "📈"),
                    unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · CHART
# ═════════════════════════════════════════════════════════════

def _tab_chart(c):
    if c["hist"].empty:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:30px;text-align:center;color:{C.TEXT3}">'
            f'Price history unavailable.</div>',
            unsafe_allow_html=True,
        )
        return
    st.plotly_chart(
        _price_chart(c["hist"], c["intrinsic"], c["analyst_tgt"], c["cur"]),
        use_container_width=True,
    )
    # Mini-stats below
    hi = c["hist"]["Close"].max()
    lo = c["hist"]["Close"].min()
    avg_vol = c["hist"]["Volume"].mean() if "Volume" in c["hist"].columns else None
    perf_1y = ((c["hist"]["Close"].iloc[-1] / c["hist"]["Close"].iloc[0]) - 1) * 100 \
              if len(c["hist"]) else None

    cols = st.columns(4)
    cols[0].markdown(_kpi_card("1-Year High", fmt_price(hi), C.GREEN),
                     unsafe_allow_html=True)
    cols[1].markdown(_kpi_card("1-Year Low",  fmt_price(lo), C.RED),
                     unsafe_allow_html=True)
    cols[2].markdown(_kpi_card("1Y Performance",
                               fmt_pct(perf_1y) if perf_1y is not None else "—",
                               C.GREEN if (perf_1y or 0) >= 0 else C.RED),
                     unsafe_allow_html=True)
    cols[3].markdown(_kpi_card("Avg Daily Volume",
                               f"{avg_vol/1e6:.1f}M" if avg_vol else "—",
                               C.BLUE),
                     unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · METHODS
# ═════════════════════════════════════════════════════════════

def _formula(text):
    return (
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
        f'background:{C.SURFACE2};color:{C.TEXT};padding:8px 12px;border-radius:6px;'
        f'border:1px solid {C.BORDER};margin:6px 0;display:inline-block">{text}</div>'
    )


def _your_box(label, content, accent):
    return (
        f'<div style="margin-top:10px;padding:10px 12px;background:{C.SURFACE2};'
        f'border-radius:6px;font-size:0.78rem;border-left:3px solid {accent}">'
        f'<b style="color:{accent}">{label}:</b> {content}</div>'
    )


def _tab_methods(c):
    # Intrinsic Value
    body = (
        f"The intrinsic value model multiplies forward EPS by a growth-banded PEG multiple, "
        f"with a 50× cap to keep extreme growth from producing bubble valuations."
        + _formula("Intrinsic Value = Forward EPS × Growth-Banded Multiple")
        + "<ul style='margin:6px 0;padding-left:22px;line-height:1.85;font-size:0.8rem'>"
          "<li>Growth ≥ 30% → multiple = min(growth × 1.4, 50)</li>"
          "<li>Growth 15–30% → multiple = growth × 1.8</li>"
          "<li>Growth &lt; 15% → multiple = max(growth × 2.2, 12)</li>"
          "<li>Growth ≤ 0 or missing → multiple = 13 (defensive)</li>"
          "</ul>"
        + _your_box(
            f"This stock",
            f"Forward EPS = {fmt_price(c['fwd_eps']) if c['fwd_eps'] else '—'} · "
            f"Growth = {fmt_pct(c['growth_used']) if c['growth_used'] is not None else '—'} · "
            f"Multiple = {c['intrinsic_multiple']}× → "
            f"<b style='color:{C.GOLD}'>Intrinsic = {fmt_price(c['intrinsic']) if c['intrinsic'] else '—'}</b>",
            C.GOLD,
        )
    )
    st.markdown(_section_card("Intrinsic Value (PEG Fair Value)", body, C.GOLD, "🎯"),
                unsafe_allow_html=True)

    # Upside
    cu = c["combined_upside"]
    if cu is None:
        v_color, v_word = C.TEXT3, "Insufficient data"
    elif cu >= 0:
        v_color, v_word = C.GREEN, "UNDERVALUED — green"
    else:
        v_color, v_word = C.RED, "OVERVALUED — red"
    body = (
        f"Upside compares current price to a balanced fair-value reference. We average "
        f"the model upside and the analyst-consensus upside (when both exist):"
        + _formula("Upside % = (Fair Value − Current Price) / Current Price × 100")
        + f"<div style='font-size:0.8rem;color:{C.TEXT2};margin-top:8px'>"
          f"<b style='color:{C.GREEN}'>Positive</b> → undervalued (green) · "
          f"<b style='color:{C.RED}'>negative</b> → overvalued (red).</div>"
        + _your_box(
            "This stock",
            f"Model = {fmt_pct(c['upside_model']) if c['upside_model'] is not None else '—'} · "
            f"Analyst = {fmt_pct(c['analyst_up']) if c['analyst_up'] is not None else '—'} → "
            f"<b style='color:{v_color}'>Combined = "
            f"{fmt_pct(cu) if cu is not None else '—'} ({v_word})</b>",
            v_color,
        )
    )
    st.markdown(_section_card("Upside · Over- / Under-valued", body, v_color, "📊"),
                unsafe_allow_html=True)

    # ROIC
    roic_q = "—"
    if c["roic"] is not None:
        roic_q = ("excellent" if c["roic"] >= 25 else "strong" if c["roic"] >= 15
                  else "decent" if c["roic"] >= 8 else "weak")
    body = (
        f"ROIC measures profit per dollar of capital deployed. Higher = stronger moat."
        + _formula("ROIC = (EBIT × (1 − tax)) / (Equity + Debt − Cash)")
        + f"<div style='font-size:0.8rem;color:{C.TEXT2};margin-top:6px'>"
          f"21% effective tax → NOPAT ≈ EBIT × 0.79.</div>"
        + _your_box("This stock",
                    f"ROIC = {f'{c['roic']:.1f}%' if c['roic'] is not None else '—'} ({roic_q})",
                    C.GREEN)
    )
    st.markdown(_section_card("Return on Invested Capital", body, C.GREEN, "⚖️"),
                unsafe_allow_html=True)

    # Quality Score
    body = (
        "Composite 0–100 score weighting five fundamental pillars. Missing inputs receive a "
        "small neutral allowance so unknowns don't unfairly tank the score."
        + "<table style='width:100%;border-collapse:collapse;margin-top:8px;font-size:0.78rem'>"
        + f"<tr style='border-bottom:1px solid {C.BORDER}'>"
          f"<th style='text-align:left;padding:6px;color:{C.TEXT3};font-weight:600'>Pillar</th>"
          f"<th style='text-align:left;padding:6px;color:{C.TEXT3};font-weight:600'>Tiers</th>"
          f"<th style='text-align:right;padding:6px;color:{C.TEXT3};font-weight:600'>Weight</th></tr>"
        + "<tr><td style='padding:6px'>ROIC</td><td style='padding:6px'>≥25% → 25 · ≥15% → 18 · ≥8% → 10 · else 4</td><td style='text-align:right;padding:6px'>25 pts</td></tr>"
        + "<tr><td style='padding:6px'>FCF Margin</td><td style='padding:6px'>≥25% → 20 · ≥15% → 14 · ≥8% → 8 · else 3</td><td style='text-align:right;padding:6px'>20 pts</td></tr>"
        + "<tr><td style='padding:6px'>Gross Margin</td><td style='padding:6px'>≥60% → 15 · ≥40% → 10 · ≥25% → 6 · else 2</td><td style='text-align:right;padding:6px'>15 pts</td></tr>"
        + "<tr><td style='padding:6px'>Revenue Growth</td><td style='padding:6px'>≥20% → 15 · ≥10% → 10 · ≥5% → 6 · else 2</td><td style='text-align:right;padding:6px'>15 pts</td></tr>"
        + "<tr><td style='padding:6px'>Debt / Equity</td><td style='padding:6px'>≤0.3 → 15 · ≤0.8 → 10 · ≤1.5 → 5 · else 1</td><td style='text-align:right;padding:6px'>15 pts</td></tr>"
        + "</table>"
        + _your_box("This stock",
                    f"Score <b>{c['score']}/100</b> → Verdict <b>{c['v_label']}</b> · {c['v_reason']}",
                    c["v_col"])
    )
    st.markdown(_section_card("Quality Score", body, C.GREEN, "🎯"),
                unsafe_allow_html=True)

    # Verdict thresholds
    body = (
        "The verdict combines quality score and intrinsic-value upside:"
        + "<ul style='margin:8px 0;padding-left:22px;line-height:1.9;font-size:0.82rem'>"
        + f"<li><b style='color:{C.GREEN}'>STRONG BUY</b> — score ≥ 72 AND upside ≥ 20%</li>"
        + f"<li><b style='color:{C.GREEN}'>BUY</b> — score ≥ 60 AND upside ≥ 10%</li>"
        + f"<li><b style='color:{C.GOLD}'>WATCH</b> — score ≥ 55 AND upside ≥ 0%</li>"
        + f"<li><b style='color:{C.BLUE}'>HOLD</b> — score ≥ 42</li>"
        + f"<li><b style='color:#FFB870'>WAIT</b> — score ≥ 28</li>"
        + f"<li><b style='color:{C.RED}'>AVOID</b> — score &lt; 28</li>"
        + "</ul>"
    )
    st.markdown(_section_card("Verdict Thresholds", body, C.BLUE, "⬡"),
                unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# TAB · BUSINESS
# ═════════════════════════════════════════════════════════════

def _tab_business(c):
    # Description
    if c["description"]:
        st.markdown(
            _section_card(
                "Business Description",
                f'<div style="font-size:0.85rem;color:{C.TEXT2};line-height:1.8">'
                f'{c["description"]}</div>',
                C.PURPLE, "📋",
            ),
            unsafe_allow_html=True,
        )

    # Ownership / float
    cols = st.columns(4)
    cols[0].markdown(
        _kpi_card("Insider Holdings",
                  fmt_pct(c["insider_pct"]*100, sign=False) if c["insider_pct"] else "—",
                  C.GREEN, "% held by insiders"),
        unsafe_allow_html=True,
    )
    cols[1].markdown(
        _kpi_card("Institutional",
                  fmt_pct(c["institution_pct"]*100, sign=False) if c["institution_pct"] else "—",
                  C.BLUE, "% held by institutions"),
        unsafe_allow_html=True,
    )
    cols[2].markdown(
        _kpi_card("Short Interest",
                  fmt_pct(c["shares_short_pct"]*100, sign=False) if c["shares_short_pct"] else "—",
                  C.RED if (c["shares_short_pct"] or 0) >= 0.05 else C.TEXT,
                  "% of float shorted"),
        unsafe_allow_html=True,
    )
    cols[3].markdown(
        _kpi_card("Short Ratio",
                  f"{c['short_ratio']:.1f}d" if c['short_ratio'] else "—",
                  C.GOLD, "days to cover"),
        unsafe_allow_html=True,
    )

    # JJ Research data (if in universe — show extra detail)
    if c["in_universe"]:
        jj = c["jj"]
        body = (
            f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;'
            f'margin-bottom:12px">'
            + _kpi_card("Moat Type",            jj["moat"]    or "—", C.GREEN)
            + _kpi_card("Pricing Power",        jj["pricing_power"]      or "—", C.GOLD)
            + _kpi_card("Capital Allocation",   jj["capital_allocation"] or "—", C.BLUE)
            + _kpi_card("Sector",               jj["sector"]  or "—", C.TEXT)
            + f'</div>'
            + f'<div style="font-size:0.82rem;color:{C.TEXT};line-height:1.7;'
              f'background:{C.SURFACE2};border-radius:8px;padding:12px 16px;'
              f'border-left:3px solid {C.GREEN}">'
              f'<b style="color:{C.GREEN}">JJ Research Verdict:</b> {jj["verdict"]}</div>'
        )
        st.markdown(_section_card("🏅  JJ Research Notes", body, C.GREEN, ""),
                    unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# Empty state
# ═════════════════════════════════════════════════════════════

def _empty_state():
    examples = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "BRK-B", "V", "JNJ"]
    chips = "".join(
        f'<span style="background:{C.SURFACE2};color:{C.TEXT2};'
        f'padding:4px 12px;border-radius:14px;font-size:0.7rem;'
        f'font-family:\'JetBrains Mono\',monospace;border:1px solid {C.BORDER}">'
        f'{t}</span>'
        for t in examples
    )
    st.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:14px;padding:48px;text-align:center;margin-top:24px">'
        f'<div style="font-size:3rem;margin-bottom:12px">🔬</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.1rem;'
        f'color:{C.TEXT};font-weight:700;margin-bottom:8px;letter-spacing:1px">'
        f'STOCK RESEARCH</div>'
        f'<div style="font-size:0.85rem;color:{C.TEXT3};max-width:480px;'
        f'margin:0 auto 20px;line-height:1.7">'
        f'Enter any S&P 500 ticker above and get a complete deep-dive: '
        f'intrinsic value, analyst targets, quality scoring, bull/bear case, '
        f'fundamentals scorecard, and a full price chart with fair-value overlays.'
        f'</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;'
        f'max-width:520px;margin:0 auto">{chips}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
