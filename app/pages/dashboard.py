# app/pages/dashboard.py  —  Home dashboard
import datetime
import streamlit as st
import pandas as pd
import plotly.express as px

from app import config as C
from app.utils import (fmt_price, fmt_mktcap, fmt_pct, compute_upside,
                       pct52, verdict_tag, verdict_reason, upside_color)
from app.styles import progress_bar, badge, section_title, label, mono
from app.data_loader import save_user_data


def _kpi(col, lbl: str, val: str, delta: str = "", delta_color: str = C.TEXT3):
    col.markdown(
        f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
        f'border-radius:10px;padding:16px 18px;height:100%">'
        f'<div style="font-size:0.6rem;color:{C.TEXT3};text-transform:uppercase;'
        f'letter-spacing:1.5px;font-weight:600;margin-bottom:6px">{lbl}</div>'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.45rem;'
        f'font-weight:700;color:{C.TEXT};line-height:1.1">{val}</div>'
        f'<div style="font-size:0.75rem;color:{delta_color};margin-top:4px">{delta}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render(df_main: pd.DataFrame, df_top10: pd.DataFrame, prices: dict):
    ud   = st.session_state.user_data
    port = ud.get("portfolio", {})
    watch= ud.get("watchlist", {})

    # ── Portfolio P&L ────────────────────────────────────────
    port_val = sum(
        (prices.get(tk) or {}).get("price", 0) * pos.get("shares", 0)
        for tk, pos in port.items()
        if (prices.get(tk) or {}).get("price")
    )
    port_cost = sum(
        pos.get("entry_price", 0) * pos.get("shares", 0)
        for pos in port.values()
    )
    port_pnl  = port_val - port_cost
    port_pnl_p= (port_pnl / port_cost * 100) if port_cost else 0.0
    alerts    = sum(
        1 for tk, w in watch.items()
        if (prices.get(tk) or {}).get("price") and
           (prices.get(tk) or {}).get("price") <= w.get("target_price", 0)
    )
    t1 = df_main[df_main["Tier"] == "T1"]
    avg_roic = df_main["ROIC %"].mean()

    # ── KPI strip ────────────────────────────────────────────
    st.markdown(section_title("📊  Portfolio Intelligence Dashboard"), unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    pnl_col = C.GREEN if port_pnl >= 0 else C.RED
    _kpi(k1, "Portfolio Value",    f"${port_val:,.0f}",
         f"{'▲' if port_pnl>=0 else '▼'} ${abs(port_pnl):,.0f}  ({port_pnl_p:+.1f}%)", pnl_col)
    _kpi(k2, "Stocks Tracked",    str(len(df_main)), f"T1:{len(t1)}  T2:{len(df_main[df_main['Tier']=='T2'])}  T3:{len(df_main[df_main['Tier']=='T3'])}", C.TEXT3)
    _kpi(k3, "Watchlist",         str(len(watch)),   f"{alerts} alert{'s' if alerts!=1 else ''} firing", C.GREEN if alerts else C.TEXT3)
    _kpi(k4, "Open Positions",    str(len(port)),    "Portfolio Simulator", C.TEXT3)
    _kpi(k5, "Universe Avg ROIC", f"{avg_roic:.1f}%","Quality compounder score", C.GREEN)

    # ── Analyzer CTA ─────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    cta1, cta2 = st.columns([4, 1])
    cta1.markdown(
        f'<div style="background:linear-gradient(90deg,{C.GREEN_BG} 0%,{C.SURFACE} 60%);'
        f'border:1px solid {C.GREEN}55;border-left:4px solid {C.GREEN};'
        f'border-radius:10px;padding:18px 22px;display:flex;align-items:center;'
        f'justify-content:space-between;height:100%">'
        f'<div>'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
        f'<span style="font-size:1.4rem">🔬</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
        f'font-weight:700;color:{C.GREEN};letter-spacing:1px">'
        f'STOCK ANALYZER — INSTANT DEEP DIVE</span></div>'
        f'<div style="font-size:0.8rem;color:{C.TEXT2};line-height:1.5">'
        f'Type <b style="color:{C.GREEN}">any S&P 500 ticker</b> and get live price, ROIC, '
        f'FCF margins, fair value, analyst targets and a quality verdict — '
        f'auto-calculated in seconds.</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    if cta2.button("🔬  Open Analyzer", use_container_width=True, key="cta_analyzer",
                    type="primary"):
        st.session_state.page = "Analyzer"
        st.rerun()

    # ── Active alerts ────────────────────────────────────────
    if alerts:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(section_title("🚨  Active Buy Alerts"), unsafe_allow_html=True)
        acols = st.columns(min(alerts, 4))
        ai = 0
        for tk, w in watch.items():
            p   = (prices.get(tk) or {}).get("price")
            tgt = w.get("target_price", 0)
            if p and p <= tgt:
                company = df_main[df_main["Ticker"] == tk]["Company"].values
                co = company[0] if len(company) else tk
                dist = (tgt - p) / tgt * 100
                acols[ai % len(acols)].markdown(
                    f'<div style="background:{C.GREEN_BG};border:1px solid {C.GREEN};'
                    f'border-radius:10px;padding:16px 18px">'
                    f'<div style="font-size:0.62rem;color:{C.GREEN};text-transform:uppercase;'
                    f'letter-spacing:1.5px;font-weight:700;margin-bottom:6px">🔔 BUY ALERT</div>'
                    f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.2rem;'
                    f'font-weight:700;color:{C.GREEN}">{tk}</div>'
                    f'<div style="font-size:0.78rem;color:{C.TEXT2};margin:2px 0">{co}</div>'
                    f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.4rem;'
                    f'font-weight:700;color:{C.TEXT}">{fmt_price(p)}</div>'
                    f'<div style="font-size:0.75rem;color:{C.GREEN};margin-top:4px">'
                    f'Target: {fmt_price(tgt)} · {dist:.1f}% below target</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                ai += 1

    st.markdown("<br>", unsafe_allow_html=True)

    # ── T1 Holdings grid ─────────────────────────────────────
    st.markdown(section_title("⭐  Tier 1 — Core Holdings"), unsafe_allow_html=True)
    cols = st.columns(3)
    fv_map = ud.get("fair_values", {})
    ep_map = ud.get("entry_prices", {})

    for idx, (_, row) in enumerate(t1.iterrows()):
        tk    = row["Ticker"]
        pd_d  = prices.get(tk) or {}
        price = pd_d.get("price")
        chg   = pd_d.get("change_pct")
        h52   = pd_d.get("high52")
        l52   = pd_d.get("low52")
        mc    = pd_d.get("mktcap")

        # Pre-compute everything before HTML
        chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
        chg_str = fmt_pct(chg)

        pos52   = pct52(price, l52, h52)
        rng_w   = max(0, min(int(pos52), 100)) if pos52 is not None else 0
        rng_col = (C.GREEN if rng_w < 30 else (C.RED if rng_w > 70 else C.GOLD))
        rng_lbl = ("🟢 Near 52wk Low" if rng_w < 30
                   else ("🔴 Near 52wk High" if rng_w > 70 else "🟡 Mid-Range"))
        card_left = (C.GREEN if rng_w < 30 else (C.RED if rng_w > 70 else C.GOLD))

        # Target + upside
        ep_tgt    = ep_map.get(tk, {}).get("target")
        upside, auto_tgt = compute_upside(row, price, fv_map.get(tk))
        tgt_price = ep_tgt or fv_map.get(tk) or auto_tgt
        tgt_src   = ("Your Entry Target" if ep_tgt
                     else ("Your Fair Value" if fv_map.get(tk) else "Auto (Fwd PE × EPS)"))
        uc        = upside_color(upside)
        ustr      = fmt_pct(upside) if upside is not None else "—"

        tgt_w = max(0, min(int(price / tgt_price * 100), 100)) if (price and tgt_price and tgt_price > 0) else 0
        tgt_col_bar = C.GREEN if (tgt_price or 0) >= (price or 0) else C.RED

        # Verdict snippet
        vtag   = verdict_tag(row["Verdict"])
        vreason= verdict_reason(row["Verdict"])
        vcol   = C.VERDICT.get(vtag, {}).get("color", C.TEXT3)

        col = cols[idx % 3]
        col.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {card_left};border-radius:12px;'
            f'padding:18px 20px;margin-bottom:10px">'

            # Header
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:start;margin-bottom:4px">'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.15rem;'
            f'font-weight:700;color:{C.GREEN}">{tk}</span>'
            f'<span style="background:{C.GREEN_BG};color:{C.GREEN};padding:2px 8px;'
            f'border-radius:4px;font-size:0.62rem;font-weight:700;'
            f'font-family:\'JetBrains Mono\',monospace">T1</span>'
            f'</div>'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
            f'color:{chg_col};font-weight:600">{chg_str}</span>'
            f'</div>'
            f'<div style="font-size:0.72rem;color:{C.TEXT3};margin-bottom:10px">'
            f'{row["Company"]} · {row["Sector"]} · {fmt_mktcap(mc)}</div>'

            # Live price
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.9rem;'
            f'font-weight:700;color:{C.TEXT};margin-bottom:10px">{fmt_price(price)}</div>'

            # Upside block
            f'<div style="background:{C.SURFACE2};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:12px 14px;margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:8px">'
            f'<div>'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:2px">UPSIDE · {tgt_src}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.5rem;'
            f'font-weight:700;color:{uc};line-height:1">{ustr}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:2px">TARGET PRICE</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.15rem;'
            f'font-weight:600;color:{C.GOLD}">{fmt_price(tgt_price)}</div>'
            f'</div>'
            f'</div>'
            # Price-to-target progress
            f'<div style="display:flex;justify-content:space-between;font-size:0.6rem;'
            f'color:{C.TEXT3};margin-bottom:3px">'
            f'<span>Current: {fmt_price(price)}</span>'
            f'<span style="color:{uc}">{tgt_w}% of target</span>'
            f'<span>Target: {fmt_price(tgt_price)}</span>'
            f'</div>'
            + progress_bar(tgt_w, tgt_col_bar, height=6)
            + f'</div>'

            # 52wk range
            f'<div style="margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.6rem;'
            f'color:{C.TEXT3};margin-bottom:3px">'
            f'<span>52wk L: {fmt_price(l52)}</span>'
            f'<span>{rng_lbl}</span>'
            f'<span>H: {fmt_price(h52)}</span>'
            f'</div>'
            + progress_bar(rng_w, rng_col, height=4)
            + f'</div>'

            # Metrics
            f'<div style="display:flex;gap:14px;font-size:0.72rem;color:{C.TEXT3};'
            f'border-top:1px solid {C.BORDER};padding-top:8px;margin-bottom:8px">'
            f'<span>ROIC <b style="color:{C.GREEN}">{row["ROIC %"]}%</b></span>'
            f'<span>FCF <b style="color:{C.GREEN}">{row["FCF Margin %"]}%</b></span>'
            f'<span>Fwd PE <b style="color:{C.TEXT}">{row["Fwd PE"]}x</b></span>'
            f'<span>GM <b style="color:{C.TEXT}">{row["Gross Margin %"]}%</b></span>'
            f'</div>'

            # Verdict
            f'<div style="font-size:0.68rem;border-top:1px solid {C.BORDER};'
            f'padding-top:8px">'
            f'<span style="background:{C.VERDICT.get(vtag,{}).get("bg",C.SURFACE)};'
            f'color:{vcol};padding:2px 8px;border-radius:4px;font-size:0.62rem;'
            f'font-weight:700;margin-right:6px">{vtag}</span>'
            f'<span style="color:{C.TEXT3};line-height:1.5">{vreason[:80]}…</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Sector ROIC bar ──────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(section_title("🏭  Sector Quality Snapshot"), unsafe_allow_html=True)
    sec = df_main.groupby("Sector")["ROIC %"].mean().sort_values(ascending=True)
    fig = px.bar(
        x=sec.values, y=sec.index, orientation="h",
        text=[f"{v:.1f}%" for v in sec.values],
        color=sec.values, color_continuous_scale=["#FF4545", "#F0B72F", "#00D26A"],
    )
    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=300,
        margin=dict(l=0, r=30, t=10, b=10),
        showlegend=False, coloraxis_showscale=False,
        xaxis=dict(title="Avg ROIC %", gridcolor=C.BORDER, zeroline=False),
        yaxis=dict(title="", gridcolor=C.BORDER),
    )
    fig.update_traces(textposition="outside", textfont_size=10)
    st.plotly_chart(fig, use_container_width=True)
