# app/pages/top10.py
import re
import streamlit as st
import pandas as pd
from app import config as C
from app.utils import (fmt_price, fmt_pct, compute_upside, upside_color,
                       parse_entry_zone, zone_status)
from app.styles import progress_bar, section_title


def render(df_top10: pd.DataFrame, df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("🏆  Top 10 Conviction Picks"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:{C.GREEN_BG};border:1px solid {C.GREEN}33;'
        f'border-radius:8px;padding:12px 16px;font-size:0.8rem;'
        f'color:{C.TEXT2};margin-bottom:20px;line-height:1.6">'
        f'Highest-conviction ideas ranked by moat durability, risk/reward and current valuation '
        f'vs 5-year average. Entry zones sourced directly from JJ Research Excel. '
        f'Green = at or below zone. Live prices from yfinance.</div>',
        unsafe_allow_html=True,
    )

    ud  = st.session_state.user_data
    fv  = ud.get("fair_values", {})
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    for _, row in df_top10.iterrows():
        rank   = int(row["Rank"])
        tk     = row["Ticker"]
        thesis = str(row["Thesis (BLUF)"])
        zone   = str(row["Entry Zone"])
        risk   = str(row["Risk"])

        mr = df_main[df_main["Ticker"] == tk]
        tier    = mr["Tier"].values[0]     if len(mr) else "T1"
        roic    = mr["ROIC %"].values[0]   if len(mr) else "—"
        fcf     = mr["FCF Margin %"].values[0] if len(mr) else "—"
        fwdpe   = mr["Fwd PE"].values[0]   if len(mr) else "—"
        verdict = mr["Verdict"].values[0]  if len(mr) else ""

        pd_d  = prices.get(tk) or {}
        cur   = pd_d.get("price")
        chg   = pd_d.get("change_pct")
        upside, auto_tgt = compute_upside(mr.iloc[0] if len(mr) else pd.Series(), cur, fv.get(tk))
        uc    = upside_color(upside)

        zlo, zhi = parse_entry_zone(zone)
        zst      = zone_status(cur, zlo, zhi)
        chg_col  = C.GREEN if (chg or 0) >= 0 else C.RED
        tc       = C.TIER.get(tier, {})
        medal    = medals[rank - 1] if rank <= 10 else str(rank)

        zone_badge = {
            "in":    (f'<span style="background:{C.GREEN};color:#000;padding:2px 10px;'
                      f'border-radius:10px;font-size:0.65rem;font-weight:800">✅ IN ENTRY ZONE</span>'),
            "below": (f'<span style="background:{C.GREEN_BG};color:{C.GREEN};padding:2px 10px;'
                      f'border-radius:10px;font-size:0.65rem;font-weight:700;'
                      f'border:1px solid {C.GREEN}">🟢 BELOW ZONE — OPPORTUNITY</span>'),
            "above": (f'<span style="background:#051226;color:{C.BLUE};padding:2px 10px;'
                      f'border-radius:10px;font-size:0.65rem;font-weight:700">⬆ ABOVE ENTRY ZONE</span>'),
        }.get(zst, "")

        tgt_w = max(0, min(int(cur / auto_tgt * 100), 100)) if (cur and auto_tgt and auto_tgt > 0) else 0

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:5px solid {uc};border-radius:12px;'
            f'padding:20px 22px;margin-bottom:12px">'

            # Header row
            f'<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:10px">'
            f'<div style="display:flex;align-items:center;gap:12px">'
            f'<span style="font-size:1.5rem">{medal}</span>'
            f'<div>'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.2rem;'
            f'font-weight:700;color:{C.GREEN}">{tk}</span>'
            f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
            f'padding:2px 8px;border-radius:4px;font-size:0.65rem;font-weight:700">{tier}</span>'
            f'{zone_badge}'
            f'</div>'
            f'<div style="font-size:0.8rem;color:{C.TEXT3}">'
            f'{mr["Company"].values[0] if len(mr) else tk}</div>'
            f'</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.6rem;'
            f'font-weight:700;color:{C.TEXT}">{fmt_price(cur)}</div>'
            f'<div style="font-size:0.78rem;color:{chg_col};font-weight:600">'
            f'{fmt_pct(chg)} today</div>'
            f'<div style="margin-top:4px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.1rem;'
            f'font-weight:700;color:{uc}">{fmt_pct(upside)}</span>'
            f'<span style="font-size:0.68rem;color:{C.TEXT3};margin-left:4px">upside</span>'
            f'</div>'
            f'</div></div>'

            # Thesis
            f'<div style="background:{C.SURFACE2};border-radius:8px;'
            f'padding:12px 14px;margin-bottom:12px;'
            f'font-size:0.83rem;color:{C.TEXT};line-height:1.7">{thesis}</div>'

            # 3-col detail grid
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">'

            # Col 1: entry zone
            f'<div style="background:{C.SURFACE2};border-radius:8px;padding:12px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.2px;margin-bottom:4px">ENTRY ZONE</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;color:{C.GOLD};'
            f'font-size:0.88rem;font-weight:600;margin-bottom:4px">{zone}</div>'
            f'<div style="font-size:0.68rem;color:{C.TEXT3}">Current: {fmt_price(cur)}</div>'
            + (
                f'<div style="margin-top:6px;font-size:0.58rem;color:{C.TEXT3};'
                f'margin-bottom:2px">Price vs target ({fmt_pct(upside)})</div>'
                + progress_bar(tgt_w, uc, height=5)
                if cur and auto_tgt else ""
            )
            + f'</div>'

            # Col 2: metrics
            f'<div style="background:{C.SURFACE2};border-radius:8px;padding:12px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.2px;margin-bottom:8px">KEY METRICS</div>'
            + "".join([
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:4px 0;border-bottom:1px solid {C.BORDER};'
                f'font-size:0.78rem">'
                f'<span style="color:{C.TEXT3}">{l}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace;'
                f'color:{c};font-weight:600">{v}</span>'
                f'</div>'
                for l, v, c in [
                    ("ROIC %",    f"{roic}%",   C.GREEN),
                    ("FCF %",     f"{fcf}%",    C.GREEN),
                    ("Fwd PE",    f"{fwdpe}x",  C.TEXT),
                    ("Target",    fmt_price(auto_tgt), C.GOLD),
                ]
            ])
            + f'</div>'

            # Col 3: risk
            f'<div style="background:{C.RED_BG};border:1px solid {C.RED}33;'
            f'border-radius:8px;padding:12px">'
            f'<div style="font-size:0.58rem;color:{C.RED};text-transform:uppercase;'
            f'letter-spacing:1.2px;font-weight:700;margin-bottom:6px">⚠️ KEY RISK</div>'
            f'<div style="font-size:0.78rem;color:{C.TEXT2};line-height:1.5">{risk}</div>'
            f'</div>'
            f'</div>'  # end grid
            f'</div>',  # end card
            unsafe_allow_html=True,
        )
