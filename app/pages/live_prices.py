# app/pages/live_prices.py
import datetime
import streamlit as st
import pandas as pd
from app import config as C
from app.utils import fmt_price, fmt_pct, fmt_mktcap, pct52
from app.styles import progress_bar, section_title


def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("📡  Real-Time Price Panel"), unsafe_allow_html=True)

    c1, c2 = st.columns([3, 1])
    tier_f = c1.radio("Tier", ["All", "T1", "T2", "T3"], horizontal=True, key="lp_tier")
    sort_f = c2.selectbox("Sort", ["Tier", "Best Day", "Worst Day", "Near 52wk Low"], key="lp_sort")

    df = df_main if tier_f == "All" else df_main[df_main["Tier"] == tier_f]

    # Enrich with price data
    rows = []
    for _, row in df.iterrows():
        tk    = row["Ticker"]
        pd_d  = prices.get(tk) or {}
        price = pd_d.get("price")
        chg   = pd_d.get("change_pct")
        h52   = pd_d.get("high52")
        l52   = pd_d.get("low52")
        mc    = pd_d.get("mktcap")
        pos52 = pct52(price, l52, h52)
        rows.append({**row.to_dict(), "price": price, "chg": chg,
                     "h52": h52, "l52": l52, "mc": mc, "pos52": pos52})

    df_r = pd.DataFrame(rows)
    if sort_f == "Best Day":       df_r = df_r.sort_values("chg", ascending=False, na_position="last")
    elif sort_f == "Worst Day":    df_r = df_r.sort_values("chg", ascending=True,  na_position="last")
    elif sort_f == "Near 52wk Low":df_r = df_r.sort_values("pos52", ascending=True, na_position="last")

    st.markdown(
        f'<div style="font-size:0.75rem;color:{C.TEXT3};margin-bottom:12px">'
        f'{len(df_r)} stocks · last refreshed {datetime.datetime.now().strftime("%H:%M:%S")} '
        f'· cache TTL 5 min</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3)
    for idx, r in df_r.iterrows():
        tk    = r["Ticker"]
        price = r["price"]
        chg   = r["chg"]
        h52   = r["h52"]
        l52   = r["l52"]
        mc    = r["mc"]
        pos52 = r["pos52"]
        tier  = r["Tier"]

        chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
        rng_w   = max(0, min(int(pos52), 100)) if pos52 is not None else 0
        rng_c   = C.GREEN if rng_w < 30 else (C.RED if rng_w > 70 else C.GOLD)
        rng_lbl = ("🟢 Near Low" if rng_w < 30 else ("🔴 Near High" if rng_w > 70 else "🟡 Mid"))
        border  = rng_c
        tc      = C.TIER.get(tier, {})

        cols[list(df_r.index).index(idx) % 3].markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {border};border-radius:10px;'
            f'padding:14px 16px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:2px">'
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
            f'font-weight:700;color:{C.GREEN}">{tk}</span>'
            f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
            f'padding:1px 6px;border-radius:3px;font-size:0.58rem;font-weight:700">{tier}</span>'
            f'</div>'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;'
            f'color:{chg_col};font-weight:700">{fmt_pct(chg)}</span>'
            f'</div>'
            f'<div style="font-size:0.68rem;color:{C.TEXT3};margin-bottom:8px">{r["Company"]}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.6rem;'
            f'font-weight:700;color:{C.TEXT};margin-bottom:8px">{fmt_price(price)}</div>'
            f'<div style="display:flex;gap:12px;font-size:0.7rem;color:{C.TEXT3};margin-bottom:8px">'
            f'<span>MCap <b style="color:{C.TEXT2}">{fmt_mktcap(mc)}</b></span>'
            f'<span>ROIC <b style="color:{C.GREEN}">{r["ROIC %"]}%</b></span>'
            f'<span>FCF <b style="color:{C.GREEN}">{r["FCF Margin %"]}%</b></span>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:0.58rem;'
            f'color:{C.TEXT3};margin-bottom:3px">'
            f'<span>L: {fmt_price(l52)}</span>'
            f'<span style="color:{rng_c}">{rng_lbl} ({rng_w}%)</span>'
            f'<span>H: {fmt_price(h52)}</span>'
            f'</div>'
            + progress_bar(rng_w, rng_c, height=5)
            + f'</div>',
            unsafe_allow_html=True,
        )
