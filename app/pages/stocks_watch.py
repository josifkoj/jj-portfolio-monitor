# app/pages/stocks_watch.py  —  Stocks to Watch: what to buy and why
import streamlit as st
import pandas as pd

from app import config as C
from app.utils import (fmt_price, fmt_pct, compute_upside, upside_color,
                       verdict_tag, verdict_reason, parse_entry_zone, zone_status)
from app.styles import progress_bar, section_title
from app.data_loader import save_user_data


def render(df_main: pd.DataFrame, df_top10: pd.DataFrame, prices: dict):
    st.markdown(section_title("📋  Stocks to Watch — What to Buy and Why"),
                unsafe_allow_html=True)

    ud  = st.session_state.user_data
    fv  = ud.get("fair_values", {})

    # ── Sidebar filters ──────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C.GREEN};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin:16px 0 8px">WATCH FILTERS</div>',
            unsafe_allow_html=True,
        )
        f_action  = st.multiselect("Action",
            ["BUY", "CORE HOLD", "WATCHLIST", "HOLD", "WAIT"],
            default=["BUY", "CORE HOLD", "WATCHLIST"], key="wtw_action")
        f_tier    = st.multiselect("Tier", ["T1", "T2", "T3"],
            default=["T1", "T2", "T3"], key="wtw_tier")
        f_upside  = st.slider("Min Upside %", -20, 60, 0, key="wtw_upside")
        f_zone    = st.checkbox("Only at/below entry zone", key="wtw_zone")
        f_top10   = st.checkbox("Only Top 10 picks", key="wtw_top10")
        sort_w    = st.selectbox("Sort by",
            ["Most Upside %", "Highest ROIC", "Best FCF", "Tier → Upside"],
            key="wtw_sort")

    # ── Build enriched rows ──────────────────────────────────
    rows = []
    for _, row in df_main.iterrows():
        tk     = row["Ticker"]
        vtag   = verdict_tag(row["Verdict"])
        reason = verdict_reason(row["Verdict"])
        cur    = (prices.get(tk) or {}).get("price")
        chg    = (prices.get(tk) or {}).get("change_pct")
        upside, tgt = compute_upside(row, cur, fv.get(tk))

        tz_row   = df_top10[df_top10["Ticker"] == tk] if not df_top10.empty else pd.DataFrame()
        zone_str = str(tz_row.iloc[0]["Entry Zone"]) if not tz_row.empty else None
        thesis   = str(tz_row.iloc[0]["Thesis (BLUF)"]) if not tz_row.empty else None
        top_rank = int(tz_row.iloc[0]["Rank"]) if not tz_row.empty else None
        zlo, zhi = parse_entry_zone(zone_str) if zone_str else (None, None)
        zst      = zone_status(cur, zlo, zhi)

        rows.append({
            "_row": row, "_vtag": vtag, "_reason": reason,
            "Ticker": tk, "Company": row["Company"], "Tier": row["Tier"],
            "Sector": row["Sector"], "ROIC %": row["ROIC %"],
            "FCF %": row["FCF Margin %"], "Fwd PE": row["Fwd PE"],
            "PP": row["Pricing Power"],
            "Live": cur, "Target": tgt, "Upside": upside, "Chg": chg,
            "Zone": zone_str, "ZSt": zst, "Rank": top_rank,
            "Thesis": thesis,
        })

    df = pd.DataFrame(rows)

    # ── Apply filters ────────────────────────────────────────
    if f_action: df = df[df["_vtag"].isin(f_action)]
    if f_tier:   df = df[df["Tier"].isin(f_tier)]
    df = df[df["Upside"].fillna(-999) >= f_upside]
    if f_zone:   df = df[df["ZSt"].isin(["in", "below"])]
    if f_top10:  df = df[df["Rank"].notna()]

    if sort_w == "Most Upside %":
        df = df.sort_values("Upside", ascending=False, na_position="last")
    elif sort_w == "Highest ROIC":
        df = df.sort_values("ROIC %", ascending=False)
    elif sort_w == "Best FCF":
        df = df.sort_values("FCF %", ascending=False)
    elif sort_w == "Tier → Upside":
        df["_ts"] = df["Tier"].map({"T1": 0, "T2": 1, "T3": 2})
        df = df.sort_values(["_ts", "Upside"], ascending=[True, False])

    st.markdown(
        f'<div style="font-size:0.8rem;color:{C.TEXT3};margin-bottom:16px">'
        f'<b style="color:{C.TEXT2}">{len(df)}</b> stocks · sorted by {sort_w}</div>',
        unsafe_allow_html=True,
    )

    for _, r in df.iterrows():
        tk     = r["Ticker"]
        vtag   = r["_vtag"]
        upside = r["Upside"]
        cur    = r["Live"]
        chg    = r["Chg"]
        tgt    = r["Target"]
        tier   = r["Tier"]
        zst    = r["ZSt"]

        uc      = upside_color(upside)
        chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
        vcol    = C.VERDICT.get(vtag, {}).get("color", C.TEXT3)
        vbg     = C.VERDICT.get(vtag, {}).get("bg", C.SURFACE)
        tc      = C.TIER.get(tier, {})

        # Zone badge (inline styles only)
        if zst == "in":
            zone_html = (f'<span style="background:{C.GREEN_BG};color:{C.GREEN};'
                         f'padding:2px 9px;border-radius:4px;font-size:0.62rem;font-weight:700;'
                         f'font-family:\'JetBrains Mono\',monospace">✅ IN ENTRY ZONE</span>')
        elif zst == "below":
            zone_html = (f'<span style="background:{C.GREEN_BG};color:{C.GREEN};'
                         f'padding:2px 9px;border-radius:4px;font-size:0.62rem;font-weight:700;'
                         f'font-family:\'JetBrains Mono\',monospace">🟢 BELOW ZONE — BUY</span>')
        elif r["Zone"]:
            zone_html = (f'<span style="font-size:0.68rem;color:{C.TEXT3}">Zone: {r["Zone"]}</span>')
        else:
            zone_html = ""

        top_html = ""
        if r["Rank"]:
            top_html = (f'<span style="background:{C.GREEN_BG};color:{C.GREEN};'
                        f'padding:2px 9px;border-radius:4px;font-size:0.62rem;font-weight:700;'
                        f'font-family:\'JetBrains Mono\',monospace">⭐ TOP {int(r["Rank"])}</span>')

        tgt_w = max(0, min(int(cur / tgt * 100), 100)) if (cur and tgt and tgt > 0) else 0

        thesis_html = ""
        if r["Thesis"]:
            thesis_html = (
                f'<div style="font-size:0.75rem;color:{C.TEXT2};line-height:1.6;'
                f'border-left:2px solid {C.GREEN};padding-left:10px;margin-top:6px;'
                f'font-style:italic">{str(r["Thesis"])[:200]}…</div>'
            )

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {uc};border-radius:12px;'
            f'padding:18px 20px;margin-bottom:10px">'

            # Row: left info + right upside
            f'<div style="display:flex;justify-content:space-between;align-items:start">'
            f'<div style="flex:1;margin-right:20px">'

            # Badges row
            f'<div style="display:flex;align-items:center;gap:8px;'
            f'flex-wrap:wrap;margin-bottom:6px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.05rem;'
            f'font-weight:700;color:{C.GREEN}">{tk}</span>'
            f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
            f'padding:2px 7px;border-radius:4px;font-size:0.62rem;font-weight:700">{tier}</span>'
            f'<span style="background:{vbg};color:{vcol};padding:2px 9px;border-radius:4px;'
            f'font-size:0.62rem;font-weight:700">{vtag}</span>'
            f'{top_html}'
            f'{zone_html}'
            f'</div>'

            # Company / sector
            f'<div style="font-size:0.75rem;color:{C.TEXT3};margin-bottom:8px">'
            f'{r["Company"]} · {r["Sector"]} · PP: {r["PP"]}</div>'

            # Reason from Excel (the "why")
            f'<div style="font-size:0.83rem;color:{C.TEXT};line-height:1.6;'
            f'background:{C.SURFACE2};border-radius:6px;padding:10px 12px;'
            f'border-left:2px solid {vcol}">'
            f'{r["_reason"]}'
            f'</div>'

            # Thesis if top10
            f'{thesis_html}'

            # Metrics strip
            f'<div style="display:flex;gap:14px;margin-top:10px;font-size:0.73rem;'
            f'color:{C.TEXT3}">'
            f'<span>ROIC <b style="color:{C.GREEN}">{r["ROIC %"]}%</b></span>'
            f'<span>FCF <b style="color:{C.GREEN}">{r["FCF %"]}%</b></span>'
            f'<span>Fwd PE <b style="color:{C.TEXT}">{r["Fwd PE"]}x</b></span>'
            f'</div>'
            f'</div>'  # end left

            # Right: big upside
            f'<div style="text-align:right;min-width:140px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:3px">UPSIDE TO TARGET</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2rem;'
            f'font-weight:700;color:{uc};line-height:1">'
            f'{fmt_pct(upside) if upside is not None else "—"}</div>'
            f'<div style="font-size:0.68rem;color:{C.TEXT3};margin-top:2px">to target</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
            f'color:{C.TEXT};font-weight:600;margin-top:6px">{fmt_price(cur)}</div>'
            f'<div style="font-size:0.72rem;color:{chg_col}">'
            f'{fmt_pct(chg)} today</div>'
            f'<div style="font-size:0.68rem;color:{C.GOLD};margin-top:3px">'
            f'Target: {fmt_price(tgt)}</div>'
            f'</div>'
            f'</div>'  # end flex row

            # Progress bar
            + (
                f'<div style="margin-top:12px">'
                f'<div style="display:flex;justify-content:space-between;font-size:0.6rem;'
                f'color:{C.TEXT3};margin-bottom:3px">'
                f'<span>Current: {fmt_price(cur)}</span>'
                f'<span style="color:{uc}">{tgt_w}% of target reached</span>'
                f'<span>Target: {fmt_price(tgt)}</span>'
                f'</div>'
                + progress_bar(tgt_w, uc, height=6)
                + f'</div>'
                if cur and tgt else ""
            )
            + f'</div>',  # end card
            unsafe_allow_html=True,
        )

        # Detail button
        if st.button(f"🔍  Full Detail: {tk}", key=f"wtw_det_{tk}",
                     use_container_width=False):
            st.session_state.selected_stock = tk
            st.session_state.page = "Screener"
            st.rerun()

    if df.empty:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:20px;text-align:center;color:{C.TEXT3}">'
            f'No stocks match your current filters.</div>',
            unsafe_allow_html=True,
        )
