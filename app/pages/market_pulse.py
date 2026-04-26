# app/pages/market_pulse.py
import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from app import config as C
from app.styles import section_title, progress_bar
from app.utils import fmt_price, fmt_pct, fmt_mktcap
from app.price_engine import fetch_single_macro, fetch_earnings


MACRO_TICKERS = ("SPY", "QQQ", "DIA", "IWM", "VIX", "TLT", "GLD", "BTC-USD")

MACRO_META = {
    "SPY":     {"label": "S&P 500",   "emoji": "📈", "color": C.GREEN},
    "QQQ":     {"label": "NASDAQ",    "emoji": "💻", "color": C.BLUE},
    "DIA":     {"label": "DOW",       "emoji": "🏛️", "color": C.GOLD},
    "IWM":     {"label": "Russell 2K","emoji": "📊", "color": C.TEAL},
    "VIX":     {"label": "VIX Fear",  "emoji": "😱", "color": C.RED},
    "TLT":     {"label": "20Y Bond",  "emoji": "💵", "color": "#94A3B8"},
    "GLD":     {"label": "Gold",      "emoji": "🥇", "color": C.GOLD},
    "BTC-USD": {"label": "Bitcoin",   "emoji": "₿",  "color": "#F7931A"},
}

SECTOR_ETFS = {
    "XLK":  "Tech",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLY":  "Cons Disc",
    "XLP":  "Cons Staples",
    "XLE":  "Energy",
    "XLI":  "Industrials",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLU":  "Utilities",
    "XLC":  "Comm Svcs",
}


def _macro_card(tk: str, data: dict) -> str:
    meta = MACRO_META.get(tk, {"label": tk, "emoji": "📊", "color": C.TEXT3})
    pd_d = data.get(tk) or {}
    price  = pd_d.get("price")
    chg    = pd_d.get("change_pct")

    if chg is None:
        chg_col  = C.TEXT3
        chg_str  = "—"
        arrow    = ""
    elif chg >= 0:
        chg_col = C.GREEN
        chg_str = f"+{chg:.2f}%"
        arrow   = "▲"
    else:
        chg_col = C.RED
        chg_str = f"{chg:.2f}%"
        arrow   = "▼"

    price_str = fmt_price(price) if price else "—"
    col       = meta["color"]

    # VIX special: invert color logic
    if tk == "VIX" and chg is not None:
        chg_col = C.RED if chg >= 0 else C.GREEN

    return (
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-top:3px solid {col};border-radius:10px;padding:16px 18px;'
        f'text-align:center">'
        f'<div style="font-size:1.3rem;margin-bottom:4px">{meta["emoji"]}</div>'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.5px;margin-bottom:6px">{meta["label"]}</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.1rem;'
        f'font-weight:700;color:{C.TEXT};margin-bottom:4px">{price_str}</div>'
        f'<div style="font-size:0.78rem;color:{chg_col};font-weight:600">'
        f'{arrow} {chg_str}</div>'
        f'</div>'
    )


def _sector_bar(sector_data: dict) -> go.Figure:
    """Horizontal bar chart — sector ETF daily change %."""
    labels, values, colors = [], [], []
    for tk, name in SECTOR_ETFS.items():
        pd_d = sector_data.get(tk) or {}
        chg  = pd_d.get("change_pct")
        if chg is None:
            continue
        labels.append(name)
        values.append(chg)
        colors.append(C.GREEN if chg >= 0 else C.RED)

    if not labels:
        return go.Figure()

    order  = sorted(range(len(values)), key=lambda i: values[i])
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    colors = [colors[i] for i in order]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in values],
        textposition="outside",
        textfont=dict(size=10, family="JetBrains Mono"),
    ))
    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=360,
        margin=dict(l=10, r=60, t=20, b=10),
        xaxis=dict(gridcolor=C.BORDER, zeroline=True,
                   zerolinecolor=C.BORDER2, zerolinewidth=1.5),
        yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10)),
        showlegend=False,
    )
    return fig


def _quality_distribution(df_main: pd.DataFrame) -> go.Figure:
    """Donut chart — T1/T2/T3 breakdown."""
    tier_counts = df_main["Tier"].value_counts().reset_index()
    tier_counts.columns = ["Tier", "Count"]
    col_map = {"T1": C.GREEN, "T2": C.GOLD, "T3": "#FF8C42"}
    fig = go.Figure(go.Pie(
        labels=tier_counts["Tier"],
        values=tier_counts["Count"],
        hole=0.55,
        marker=dict(colors=[col_map.get(t, C.TEXT3) for t in tier_counts["Tier"]],
                    line=dict(color=C.BG, width=2)),
        textfont=dict(size=11, family="JetBrains Mono"),
        hovertemplate="<b>%{label}</b><br>%{value} stocks<br>%{percent}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=C.BG, font_color=C.TEXT2, height=240,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
        annotations=[dict(text="Tier<br>Mix", x=0.5, y=0.5, font_size=11,
                          font_color=C.TEXT2, showarrow=False)],
    )
    return fig


def _verdict_distribution(df_main: pd.DataFrame) -> go.Figure:
    """Horizontal bar — verdict tag counts."""
    from app.utils import verdict_tag
    df_main = df_main.copy()
    df_main["_tag"] = df_main["Verdict"].apply(verdict_tag)
    vc = df_main["_tag"].value_counts()

    col_map = {
        "BUY":       C.GREEN,
        "CORE HOLD": C.BLUE,
        "HOLD":      C.BLUE,
        "WATCHLIST": C.PURPLE,
        "WAIT":      C.GOLD,
        "—":         C.TEXT3,
    }
    colors = [col_map.get(t, C.TEXT3) for t in vc.index]

    fig = go.Figure(go.Bar(
        x=list(vc.values), y=list(vc.index), orientation="h",
        marker_color=colors,
        text=[str(v) for v in vc.values],
        textposition="outside",
        textfont=dict(size=11, color=C.TEXT2, family="JetBrains Mono"),
    ))
    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=240,
        margin=dict(l=10, r=40, t=10, b=10),
        xaxis=dict(gridcolor=C.BORDER, zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
        showlegend=False,
    )
    return fig


def _earnings_table(tickers: list) -> None:
    bucket = int(time.time() // 3600)
    rows   = fetch_earnings(tuple(sorted(set(tickers))), )  # no _bucket arg needed — uses cache TTL
    if not rows:
        st.markdown(
            f'<div style="color:{C.TEXT3};font-size:0.8rem;padding:12px">'
            f'No upcoming earnings data available.</div>',
            unsafe_allow_html=True,
        )
        return

    df_e = pd.DataFrame(rows).sort_values("Date")
    st.dataframe(
        df_e.style.set_properties(**{
            "background-color": C.SURFACE,
            "color": C.TEXT,
            "font-family": "JetBrains Mono, monospace",
            "font-size": "0.8rem",
        }),
        use_container_width=True, hide_index=True,
    )


def _fear_greed_gauge(spy_chg: float | None, vix: float | None) -> str:
    """Simple synthetic Fear & Greed score (0-100) from SPY momentum + VIX."""
    score = 50  # neutral default
    if spy_chg is not None:
        score += min(30, max(-30, spy_chg * 5))
    if vix is not None:
        if vix < 15:
            score += 15
        elif vix < 20:
            score += 5
        elif vix > 30:
            score -= 20
        elif vix > 25:
            score -= 10
    score = max(0, min(100, int(score)))

    if score >= 75:
        label, col = "EXTREME GREED", C.GREEN
    elif score >= 55:
        label, col = "GREED", "#5EE896"
    elif score >= 45:
        label, col = "NEUTRAL", C.GOLD
    elif score >= 25:
        label, col = "FEAR", "#FF9B3D"
    else:
        label, col = "EXTREME FEAR", C.RED

    bar_html = progress_bar(score, col, height=8)

    return (
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:10px;padding:16px 18px">'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.5px;margin-bottom:10px">Market Sentiment Gauge</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'margin-bottom:6px">'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.8rem;'
        f'font-weight:700;color:{col}">{score}</span>'
        f'<span style="font-size:0.7rem;font-weight:700;color:{col};'
        f'letter-spacing:1px">{label}</span>'
        f'</div>'
        + bar_html
        + f'<div style="display:flex;justify-content:space-between;'
        f'font-size:0.6rem;color:{C.TEXT3};margin-top:2px">'
        f'<span>0 — Extreme Fear</span><span>100 — Extreme Greed</span>'
        f'</div>'
        f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:8px">'
        f'Based on SPY momentum + VIX level. Indicative only.</div>'
        f'</div>'
    )


def render(df_main: pd.DataFrame):
    st.markdown(section_title("📰  Market Pulse — Macro & Sentiment"), unsafe_allow_html=True)

    # ── Fetch macro prices ──────────────────────────────────────
    bucket      = int(time.time() // 300)
    macro_data  = fetch_single_macro(MACRO_TICKERS, bucket)
    sector_tks  = tuple(sorted(SECTOR_ETFS.keys()))
    sector_data = fetch_single_macro(sector_tks, bucket)

    # ── Row 1: macro KPI strip ─────────────────────────────────
    st.markdown(
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.5px;margin-bottom:10px">Live Market Indices</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(MACRO_TICKERS))
    for col, tk in zip(cols, MACRO_TICKERS):
        col.markdown(_macro_card(tk, macro_data), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Row 2: Fear & Greed + Sector Rotation ─────────────────
    c1, c2 = st.columns([1, 2])

    with c1:
        spy_chg = (macro_data.get("SPY") or {}).get("change_pct")
        vix_val = (macro_data.get("VIX") or {}).get("price")
        st.markdown(_fear_greed_gauge(spy_chg, vix_val), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Quick stats box
        buy_ct  = sum(1 for _, r in df_main.iterrows()
                      if "BUY" in str(r.get("Verdict", "")).upper())
        t1_ct   = (df_main["Tier"] == "T1").sum()
        avg_roic = df_main["ROIC %"].mean()
        avg_fcf  = df_main["FCF Margin %"].mean()

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:10px;padding:16px 18px">'
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:12px">Universe Stats</div>'
            + "".join([
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:5px 0;border-bottom:1px solid {C.BORDER};font-size:0.8rem">'
                f'<span style="color:{C.TEXT3}">{l}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace;'
                f'font-weight:700;color:{c}">{v}</span></div>'
                for l, v, c in [
                    ("Total Stocks",    str(len(df_main)),         C.TEXT),
                    ("T1 Core",         str(int(t1_ct)),           C.GREEN),
                    ("BUY Signals",     str(buy_ct),               C.GREEN),
                    ("Avg ROIC",        f"{avg_roic:.1f}%",        C.GREEN),
                    ("Avg FCF Margin",  f"{avg_fcf:.1f}%",         C.TEAL),
                ]
            ])
            + f'</div>',
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:6px">Sector ETF Daily Performance</div>',
            unsafe_allow_html=True,
        )
        fig_sec = _sector_bar(sector_data)
        if fig_sec.data:
            st.plotly_chart(fig_sec, use_container_width=True)
        else:
            st.markdown(
                f'<div style="color:{C.TEXT3};font-size:0.8rem;padding:20px;'
                f'text-align:center">Sector data unavailable</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # ── Row 3: Quality distribution charts ────────────────────
    st.markdown(section_title("📊  Universe Quality Distribution"), unsafe_allow_html=True)
    d1, d2 = st.columns(2)

    with d1:
        st.markdown(
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:4px">Tier Breakdown</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(_quality_distribution(df_main), use_container_width=True)

    with d2:
        st.markdown(
            f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:4px">Verdict Distribution</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(_verdict_distribution(df_main), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # ── Row 4: ROIC ranking chart ──────────────────────────────
    st.markdown(section_title("🏆  ROIC Ranking — Top 20 Quality Companies"), unsafe_allow_html=True)

    df_roic = df_main.copy()
    df_roic["ROIC %"] = pd.to_numeric(df_roic["ROIC %"], errors="coerce")
    df_roic = df_roic.dropna(subset=["ROIC %"]).sort_values("ROIC %", ascending=False).head(20)

    tier_col_map = {"T1": C.GREEN, "T2": C.GOLD, "T3": "#FF8C42"}
    bar_colors   = [tier_col_map.get(t, C.TEXT3) for t in df_roic["Tier"]]

    fig_roic = go.Figure(go.Bar(
        x=df_roic["Ticker"], y=df_roic["ROIC %"],
        marker_color=bar_colors,
        text=[f"{v:.0f}%" for v in df_roic["ROIC %"]],
        textposition="outside",
        textfont=dict(size=9, color=C.TEXT2, family="JetBrains Mono"),
        hovertemplate="<b>%{x}</b><br>ROIC: %{y:.1f}%<extra></extra>",
    ))
    fig_roic.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=320,
        margin=dict(l=10, r=10, t=20, b=60),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER, tickfont=dict(size=9)),
        yaxis=dict(title="ROIC %", gridcolor=C.BORDER),
        showlegend=False,
    )
    st.plotly_chart(fig_roic, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # ── Row 5: Upcoming earnings ──────────────────────────────
    st.markdown(section_title("📅  Upcoming Earnings Calendar"), unsafe_allow_html=True)
    tickers = df_main["Ticker"].tolist()

    with st.spinner("Loading earnings calendar…"):
        _earnings_table(tickers)

    # ── Footnote ─────────────────────────────────────────────
    st.markdown(
        f'<div style="font-size:0.68rem;color:{C.TEXT3};margin-top:16px;'
        f'padding:10px 14px;background:{C.SURFACE};border-radius:6px;'
        f'border:1px solid {C.BORDER}">'
        f'⚡ Macro prices refresh every 5 minutes via yfinance. '
        f'Sentiment gauge is indicative only — not financial advice. '
        f'Earnings calendar sourced from yfinance; dates may shift.</div>',
        unsafe_allow_html=True,
    )
