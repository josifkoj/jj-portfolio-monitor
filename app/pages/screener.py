# app/pages/screener.py  —  Upside Screener + Stock Detail overlay
import streamlit as st
import pandas as pd

from app import config as C
from app.utils import (fmt_price, fmt_pct, fmt_mktcap, compute_upside, upside_color,
                       pct52, verdict_tag, verdict_reason, parse_entry_zone,
                       zone_status, VERDICT, TIER)
from app.styles import progress_bar, section_title
from app.data_loader import save_user_data


# ─────────────────────────────────────────────
#  STOCK DETAIL  (shown when selected_stock set)
# ─────────────────────────────────────────────
def _render_detail(tk: str, df_main: pd.DataFrame, df_top10: pd.DataFrame, prices: dict):
    ud   = st.session_state.user_data
    fv   = ud.get("fair_values", {})
    row_s= df_main[df_main["Ticker"] == tk]
    if row_s.empty:
        st.warning(f"No data for {tk}")
        return

    row   = row_s.iloc[0]
    pd_d  = prices.get(tk) or {}
    cur   = pd_d.get("price")
    chg   = pd_d.get("change_pct")
    h52   = pd_d.get("high52")
    l52   = pd_d.get("low52")
    mc    = pd_d.get("mktcap")
    tier  = row["Tier"]

    upside, auto_tgt = compute_upside(row, cur, fv.get(tk))
    tgt = fv.get(tk) or auto_tgt
    uc  = upside_color(upside)

    pos52 = pct52(cur, l52, h52)
    rng_w = max(0, min(int(pos52), 100)) if pos52 is not None else 0
    rng_c = C.GREEN if rng_w < 30 else (C.RED if rng_w > 70 else C.GOLD)
    rng_lbl = ("🟢 Near 52wk Low" if rng_w < 30
               else ("🔴 Near 52wk High" if rng_w > 70 else "🟡 Mid-Range"))

    chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
    tc      = TIER.get(tier, {})
    vtag    = verdict_tag(row["Verdict"])
    vreason = verdict_reason(row["Verdict"])
    vcol    = VERDICT.get(vtag, {}).get("color", C.TEXT3)
    vbg     = VERDICT.get(vtag, {}).get("bg", C.SURFACE)

    # ── Hero banner ──────────────────────────────────────────
    st.markdown(
        f'<div style="background:linear-gradient(135deg,{C.SURFACE2} 0%,{C.SURFACE} 100%);'
        f'border:1px solid {C.BORDER};border-left:5px solid {uc};'
        f'border-radius:12px;padding:22px 26px;margin-bottom:18px">'
        f'<div style="display:flex;justify-content:space-between;align-items:start">'

        # Left
        f'<div>'
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:2rem;'
        f'font-weight:700;color:{C.GREEN}">{tk}</span>'
        f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
        f'padding:3px 10px;border-radius:5px;font-size:0.72rem;font-weight:700">{tier}</span>'
        f'<span style="background:{vbg};color:{vcol};padding:3px 10px;border-radius:5px;'
        f'font-size:0.72rem;font-weight:700">{vtag}</span>'
        f'</div>'
        f'<div style="font-size:1rem;color:{C.TEXT2};font-weight:500;margin-bottom:2px">'
        f'{row["Company"]}</div>'
        f'<div style="font-size:0.78rem;color:{C.TEXT3}">'
        f'{row["Sector"]} · {row["Moat Type"]}</div>'
        f'</div>'

        # Right
        f'<div style="text-align:right">'
        f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2.2rem;'
        f'font-weight:700;color:{C.TEXT}">{fmt_price(cur)}</div>'
        f'<div style="font-size:0.85rem;color:{chg_col};font-weight:600">'
        f'{fmt_pct(chg)} today</div>'
        f'<div style="font-size:0.75rem;color:{C.TEXT3};margin-top:4px">'
        f'MCap: {fmt_mktcap(mc)}</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    left, mid, right = st.columns([1.1, 1.1, 1])

    # ── LEFT: Upside & ranges ────────────────────────────────
    with left:
        tgt_w = max(0, min(int(cur / tgt * 100), 100)) if (cur and tgt and tgt > 0) else 0
        fv_src = "User Fair Value" if fv.get(tk) else "Auto (Fwd PE × EPS)"

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {uc};border-radius:10px;padding:18px;margin-bottom:12px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:4px">UPSIDE TO TARGET</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2.8rem;'
            f'font-weight:700;color:{uc};line-height:1">'
            f'{fmt_pct(upside) if upside is not None else "—"}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.1rem;'
            f'color:{C.GOLD};font-weight:600;margin-top:6px">Target: {fmt_price(tgt)}</div>'
            f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-bottom:10px">'
            f'Source: {fv_src}</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:0.6rem;'
            f'color:{C.TEXT3};margin-bottom:3px">'
            f'<span>{fmt_price(cur)}</span>'
            f'<span style="color:{uc}">{tgt_w}%</span>'
            f'<span>{fmt_price(tgt)}</span>'
            f'</div>'
            + progress_bar(tgt_w, uc, height=8)
            + f'</div>',
            unsafe_allow_html=True,
        )

        # 52wk range
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:10px;padding:16px;margin-bottom:12px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:6px">52-WEEK RANGE — {rng_lbl}</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:0.65rem;'
            f'color:{C.TEXT3};margin-bottom:4px">'
            f'<span>Low: {fmt_price(l52)}</span>'
            f'<span style="color:{rng_c};font-weight:600">{rng_w:.0f}%</span>'
            f'<span>High: {fmt_price(h52)}</span>'
            f'</div>'
            + progress_bar(rng_w, rng_c, height=8)
            + f'</div>',
            unsafe_allow_html=True,
        )

        # FV setter
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-bottom:6px">'
            f'Set your own Fair Value to override auto target:</div>',
            unsafe_allow_html=True,
        )
        new_fv = st.number_input("Fair Value ($)", min_value=0.01,
                                  value=float(fv.get(tk, tgt or (cur or 100))),
                                  step=1.0, key=f"detail_fv_{tk}")
        if st.button("💾  Save Fair Value", key=f"save_fv_{tk}", use_container_width=True):
            ud["fair_values"][tk] = new_fv
            save_user_data(ud)
            st.success("Saved!"); st.rerun()

    # ── MID: Fundamentals table ──────────────────────────────
    with mid:
        def _mrow(lbl, val, col=C.TEXT):
            return (
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:7px 0;border-bottom:1px solid {C.BORDER}">'
                f'<span style="font-size:0.78rem;color:{C.TEXT3}">{lbl}</span>'
                f'<span style="font-family:\'JetBrains Mono\',monospace;font-weight:600;'
                f'color:{col};font-size:0.85rem">{val}</span>'
                f'</div>'
            )
        roic_c = C.GREEN if row["ROIC %"] >= 25 else (C.GOLD if row["ROIC %"] >= 15 else C.RED)
        fcf_c  = C.GREEN if row["FCF Margin %"] >= 20 else (C.GOLD if row["FCF Margin %"] >= 10 else C.RED)
        pe_c   = C.GREEN if row["PE (TTM)"] <= 30 else (C.GOLD if row["PE (TTM)"] <= 50 else C.RED)
        dbt_c  = C.GREEN if row["Net Debt/EBITDA"] <= 1.5 else (C.GOLD if row["Net Debt/EBITDA"] <= 3 else C.RED)
        pp_c   = C.GREEN if row["Pricing Power"] == "ABSOLUTE" else (C.GOLD if row["Pricing Power"] == "STRONG" else C.TEXT3)
        ca_c   = C.GREEN if row["Capital Allocation"] in ("ELITE","EXCELLENT") else (C.GOLD if row["Capital Allocation"] == "GOOD" else C.TEXT3)

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:10px;padding:16px 18px">'
            f'<div style="font-size:0.62rem;color:{C.GREEN};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin-bottom:10px">FUNDAMENTALS</div>'
            + _mrow("ROIC %",            f'{row["ROIC %"]}%',            roic_c)
            + _mrow("Gross Margin %",    f'{row["Gross Margin %"]}%',    C.GREEN)
            + _mrow("FCF Margin %",      f'{row["FCF Margin %"]}%',      fcf_c)
            + _mrow("EPS Growth %",      f'{row["EPS Growth %"]}%',      C.BLUE)
            + _mrow("PE (TTM)",          f'{row["PE (TTM)"]}x',          pe_c)
            + _mrow("Fwd PE",            f'{row["Fwd PE"]}x',            C.TEXT)
            + _mrow("Net Debt/EBITDA",   f'{row["Net Debt/EBITDA"]}x',   dbt_c)
            + _mrow("Pricing Power",     row["Pricing Power"],           pp_c)
            + _mrow("Capital Allocation",row["Capital Allocation"],      ca_c)
            + f'</div>',
            unsafe_allow_html=True,
        )

    # ── RIGHT: Verdict + Top10 + Position ───────────────────
    with right:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {vcol};border-radius:10px;padding:16px;margin-bottom:12px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:4px">VERDICT</div>'
            f'<span style="background:{vbg};color:{vcol};padding:3px 10px;border-radius:5px;'
            f'font-size:0.72rem;font-weight:700">{vtag}</span>'
            f'<div style="font-size:0.82rem;color:{C.TEXT};line-height:1.6;margin-top:8px">'
            f'{vreason}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Top10
        top_row = df_top10[df_top10["Ticker"] == tk] if not df_top10.empty else pd.DataFrame()
        if not top_row.empty:
            tr     = top_row.iloc[0]
            zone   = str(tr["Entry Zone"])
            zlo, zhi = parse_entry_zone(zone)
            zst    = zone_status(cur, zlo, zhi)
            zone_badge = {
                "in":      f'<span style="background:{C.GREEN_BG};color:{C.GREEN};padding:2px 8px;border-radius:4px;font-size:0.62rem;font-weight:700">✅ IN ZONE</span>',
                "below":   f'<span style="background:{C.GREEN_BG};color:{C.GREEN};padding:2px 8px;border-radius:4px;font-size:0.62rem;font-weight:700">🟢 BELOW — BUY</span>',
                "above":   f'<span style="background:#051226;color:{C.BLUE};padding:2px 8px;border-radius:4px;font-size:0.62rem;font-weight:700">⬆ ABOVE ZONE</span>',
            }.get(zst, "")

            st.markdown(
                f'<div style="background:{C.GREEN_BG};border:1px solid {C.GREEN}44;'
                f'border-radius:10px;padding:16px;margin-bottom:12px">'
                f'<div style="font-size:0.62rem;color:{C.GREEN};text-transform:uppercase;'
                f'letter-spacing:1.5px;font-weight:700;margin-bottom:6px">'
                f'TOP 10 — RANK #{int(tr["Rank"])}</div>'
                f'<div style="font-size:0.78rem;color:{C.TEXT};line-height:1.6;'
                f'margin-bottom:10px">{str(tr["Thesis (BLUF)"])[:200]}</div>'
                f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-bottom:2px">ENTRY ZONE</div>'
                f'<div style="font-family:\'JetBrains Mono\',monospace;color:{C.GOLD};'
                f'font-size:0.85rem;font-weight:600;margin-bottom:6px">{zone}</div>'
                f'{zone_badge}'
                f'<div style="margin-top:10px;background:{C.RED_BG};border:1px solid {C.RED}33;'
                f'border-radius:6px;padding:8px 10px">'
                f'<div style="font-size:0.58rem;color:{C.RED};text-transform:uppercase;'
                f'letter-spacing:1px;margin-bottom:3px">KEY RISK</div>'
                f'<div style="font-size:0.75rem;color:{C.TEXT2}">{str(tr["Risk"])[:120]}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Personal position
        ep = ud.get("entry_prices", {}).get(tk, {})
        if ep:
            ep_price = ep.get("price", 0)
            ep_tgt   = ep.get("target", 0)
            ep_sh    = ep.get("shares", 0)
            dist     = (cur - ep_price) / ep_price * 100 if (cur and ep_price) else None
            pnl      = (cur - ep_price) * ep_sh if (cur and ep_price) else None
            dcol     = C.GREEN if (dist or 0) >= 0 else C.RED
            prog_ep  = max(0, min(int((cur - ep_price) / (ep_tgt - ep_price) * 100), 100)) if (ep_tgt and ep_tgt != ep_price and cur) else 0

            st.markdown(
                f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
                f'border-left:4px solid {dcol};border-radius:10px;padding:16px">'
                f'<div style="font-size:0.62rem;color:{C.TEXT3};text-transform:uppercase;'
                f'letter-spacing:1.5px;margin-bottom:8px">YOUR POSITION</div>'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;'
                f'font-size:0.78rem;margin-bottom:8px">'
                f'<div>Entry<br><b style="font-family:\'JetBrains Mono\',monospace;'
                f'color:{C.TEXT}">{fmt_price(ep_price)}</b></div>'
                f'<div>Shares<br><b style="font-family:\'JetBrains Mono\',monospace;'
                f'color:{C.TEXT}">{ep_sh:,.0f}</b></div>'
                f'<div>Distance<br><b style="font-family:\'JetBrains Mono\',monospace;'
                f'color:{dcol}">{fmt_pct(dist)}</b></div>'
                f'<div>P&amp;L<br><b style="font-family:\'JetBrains Mono\',monospace;'
                f'color:{dcol}">{fmt_price(pnl)}</b></div>'
                f'</div>'
                + progress_bar(prog_ep, dcol, height=5)
                + f'<div style="font-size:0.62rem;color:{C.TEXT3};margin-top:3px">'
                f'{prog_ep}% to your target {fmt_price(ep_tgt)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────
#  SCREENER  (card grid + table view)
# ─────────────────────────────────────────────
def render(df_main: pd.DataFrame, df_top10: pd.DataFrame, prices: dict):
    # If detail selected → show detail view
    if st.session_state.selected_stock:
        sel = st.session_state.selected_stock
        if st.button("← Back to Screener", key="scr_back"):
            st.session_state.selected_stock = None
            st.rerun()
        st.markdown(
            section_title(f"🔍  Stock Detail — {sel}"),
            unsafe_allow_html=True,
        )
        _render_detail(sel, df_main, df_top10, prices)
        return

    st.markdown(section_title("🔍  Upside Screener — Distance from Target"),
                unsafe_allow_html=True)

    ud = st.session_state.user_data
    fv = ud.setdefault("fair_values", {})

    # ── Sidebar filters ──────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f'<div style="font-size:0.65rem;color:{C.GREEN};text-transform:uppercase;'
            f'letter-spacing:1.5px;font-weight:700;margin:16px 0 8px">SCREENER FILTERS</div>',
            unsafe_allow_html=True,
        )
        f_tier    = st.multiselect("Tier", ["T1","T2","T3"], default=["T1","T2","T3"], key="scr_tier")
        f_sector  = st.multiselect("Sector", sorted(df_main["Sector"].unique()), default=[], key="scr_sector")
        f_roic    = st.slider("Min ROIC %", 0, 60, 0, key="scr_roic")
        f_fcf     = st.slider("Min FCF Margin %", 0, 60, 0, key="scr_fcf")
        f_pe      = st.slider("Max PE (TTM)", 0, 100, 100, key="scr_pe")
        f_debt    = st.slider("Max Net Debt/EBITDA", 0.0, 10.0, 10.0, step=0.5, key="scr_debt")
        f_upside  = st.slider("Min Upside %", -30, 60, -30, key="scr_upside")
        f_pp      = st.multiselect("Pricing Power", ["ABSOLUTE","STRONG","MODERATE"], default=[], key="scr_pp")
        sort_by   = st.selectbox("Sort by",
            ["Most Upside %","Highest ROIC","Best FCF %","Lowest PE","Lowest Fwd PE"],
            key="scr_sort")
        view_mode = st.radio("View", ["Cards", "Table"], key="scr_view", horizontal=True)

    # FV editor
    with st.expander("🎯  Set Custom Fair Values"):
        fc1, fc2, fc3 = st.columns([2, 2, 1])
        fv_tk  = fc1.selectbox("Ticker", sorted(df_main["Ticker"]), key="fv_tk")
        fv_val = fc2.number_input("Fair Value ($)", min_value=0.01,
                                   value=float(fv.get(fv_tk, 100.0)), step=1.0, key="fv_val")
        if fc3.button("Save", use_container_width=True, key="fv_save"):
            fv[fv_tk] = fv_val
            ud["fair_values"] = fv
            save_user_data(ud)
            st.success(f"Saved {fmt_price(fv_val)} for {fv_tk}"); st.rerun()

    st.markdown("---")

    # ── Filter & compute ─────────────────────────────────────
    df = df_main.copy()
    if f_tier:   df = df[df["Tier"].isin(f_tier)]
    if f_sector: df = df[df["Sector"].isin(f_sector)]
    df = df[df["ROIC %"] >= f_roic]
    df = df[df["FCF Margin %"] >= f_fcf]
    df = df[df["PE (TTM)"] <= f_pe]
    df = df[df["Net Debt/EBITDA"] <= f_debt]
    if f_pp: df = df[df["Pricing Power"].isin(f_pp)]

    rows = []
    for _, row in df.iterrows():
        tk   = row["Ticker"]
        cur  = (prices.get(tk) or {}).get("price")
        chg  = (prices.get(tk) or {}).get("change_pct")
        up, tgt = compute_upside(row, cur, fv.get(tk))
        rows.append({
            "_row": row,
            "Tier": row["Tier"], "Ticker": tk, "Company": row["Company"],
            "Sector": row["Sector"], "ROIC": row["ROIC %"], "FCF": row["FCF Margin %"],
            "PE": row["PE (TTM)"], "FwdPE": row["Fwd PE"],
            "Price": cur, "Target": tgt, "Upside": up, "Chg": chg,
            "Verdict": verdict_tag(row["Verdict"]),
            "FV_src": "User" if fv.get(tk) else "Auto",
        })

    res = pd.DataFrame(rows)
    res = res[res["Upside"].fillna(-999) >= f_upside]

    if sort_by == "Most Upside %":    res = res.sort_values("Upside", ascending=False, na_position="last")
    elif sort_by == "Highest ROIC":   res = res.sort_values("ROIC", ascending=False)
    elif sort_by == "Best FCF %":     res = res.sort_values("FCF", ascending=False)
    elif sort_by == "Lowest PE":      res = res.sort_values("PE", ascending=True)
    elif sort_by == "Lowest Fwd PE":  res = res.sort_values("FwdPE", ascending=True)

    st.markdown(
        f'<div style="font-size:0.8rem;color:{C.TEXT3};margin-bottom:16px">'
        f'<b style="color:{C.TEXT2}">{len(res)}</b> stocks · sorted by {sort_by}</div>',
        unsafe_allow_html=True,
    )

    # ── CARDS ────────────────────────────────────────────────
    if view_mode == "Cards":
        cols = st.columns(3)
        for idx, (_, r) in enumerate(res.iterrows()):
            tk  = r["Ticker"]
            up  = r["Upside"]
            cur = r["Price"]
            tgt = r["Target"]
            chg = r["Chg"]
            tier= r["Tier"]
            uc  = upside_color(up)
            chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
            vtag= r["Verdict"]
            vcol= VERDICT.get(vtag, {}).get("color", C.TEXT3)
            vbg = VERDICT.get(vtag, {}).get("bg", C.SURFACE)
            tc  = TIER.get(tier, {})

            tgt_w = max(0, min(int(cur / tgt * 100), 100)) if (cur and tgt and tgt > 0) else 0

            col = cols[idx % 3]
            col.markdown(
                f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
                f'border-left:4px solid {uc};border-radius:12px;'
                f'padding:16px 18px;margin-bottom:10px">'

                # Header
                f'<div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:4px">'
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
                f'font-weight:700;color:{C.GREEN}">{tk}</span>'
                f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
                f'padding:1px 7px;border-radius:3px;font-size:0.6rem;font-weight:700">{tier}</span>'
                f'<span style="background:{vbg};color:{vcol};padding:1px 7px;border-radius:3px;'
                f'font-size:0.6rem;font-weight:700">{vtag}</span>'
                f'</div>'
                f'<div style="text-align:right">'
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.9rem;'
                f'color:{C.TEXT};font-weight:600">{fmt_price(cur)}</div>'
                f'<div style="font-size:0.7rem;color:{chg_col}">{fmt_pct(chg)}</div>'
                f'</div></div>'

                f'<div style="font-size:0.7rem;color:{C.TEXT3};margin-bottom:12px">'
                f'{r["Company"]} · {r["Sector"]}</div>'

                # Big upside
                f'<div style="text-align:center;background:{C.SURFACE2};border-radius:8px;'
                f'padding:12px 8px;margin-bottom:10px">'
                f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
                f'letter-spacing:1.5px;margin-bottom:4px">UPSIDE TO TARGET</div>'
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:2.1rem;'
                f'font-weight:700;color:{uc};line-height:1">'
                f'{fmt_pct(up) if up is not None else "—"}</div>'
                f'<div style="font-size:0.7rem;color:{C.GOLD};margin-top:4px">'
                f'Target: {fmt_price(tgt)}'
                f'<span style="color:{C.TEXT3};margin-left:4px">({r["FV_src"]})</span></div>'
                f'</div>'

                # Progress bar
                + (
                    f'<div style="display:flex;justify-content:space-between;font-size:0.58rem;'
                    f'color:{C.TEXT3};margin-bottom:3px">'
                    f'<span>{fmt_price(cur)}</span>'
                    f'<span style="color:{uc}">{tgt_w}% of target</span>'
                    f'<span>{fmt_price(tgt)}</span></div>'
                    + progress_bar(tgt_w, uc, height=6)
                    if cur and tgt else ""
                )

                # Metrics strip
                + f'<div style="display:flex;justify-content:space-between;'
                f'font-size:0.7rem;color:{C.TEXT3};margin-top:8px;'
                f'border-top:1px solid {C.BORDER};padding-top:8px">'
                f'<span>ROIC <b style="color:{C.GREEN}">{r["ROIC"]}%</b></span>'
                f'<span>FCF <b style="color:{C.GREEN}">{r["FCF"]}%</b></span>'
                f'<span>Fwd PE <b style="color:{C.TEXT}">{r["FwdPE"]}x</b></span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if col.button("🔍 View Detail", key=f"scr_det_{tk}_{idx}", use_container_width=True):
                st.session_state.selected_stock = tk
                st.rerun()

    # ── TABLE ────────────────────────────────────────────────
    else:
        rows_html = ""
        for _, r in res.iterrows():
            uc   = upside_color(r["Upside"])
            vcol = VERDICT.get(r["Verdict"], {}).get("color", C.TEXT3)
            tc   = TIER.get(r["Tier"], {})
            chg_c= C.GREEN if (r["Chg"] or 0) >= 0 else C.RED
            rows_html += (
                f'<tr style="border-bottom:1px solid {C.BORDER}">'
                f'<td style="padding:8px 6px">'
                f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
                f'padding:2px 7px;border-radius:3px;font-size:0.62rem;font-weight:700">{r["Tier"]}</span></td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;color:{C.GREEN};'
                f'font-weight:700;padding:8px 6px">{r["Ticker"]}</td>'
                f'<td style="color:{C.TEXT2};font-size:0.8rem;padding:8px 6px">{r["Company"]}</td>'
                f'<td style="color:{C.TEXT3};font-size:0.75rem;padding:8px 6px">{r["Sector"]}</td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;padding:8px 6px">{fmt_price(r["Price"])}</td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;color:{C.GOLD};padding:8px 6px">{fmt_price(r["Target"])}</td>'
                f'<td style="padding:8px 6px">'
                f'<span style="font-family:\'JetBrains Mono\',monospace;font-weight:700;'
                f'font-size:1rem;color:{uc}">'
                f'{fmt_pct(r["Upside"]) if r["Upside"] is not None else "—"}</span></td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;color:{chg_c};padding:8px 6px">'
                f'{fmt_pct(r["Chg"]) if r["Chg"] is not None else "—"}</td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;color:{C.GREEN};padding:8px 6px">{r["ROIC"]}%</td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;padding:8px 6px">{r["FCF"]}%</td>'
                f'<td style="font-family:\'JetBrains Mono\',monospace;padding:8px 6px">{r["FwdPE"]}x</td>'
                f'<td style="padding:8px 6px">'
                f'<span style="color:{vcol};font-weight:600;font-size:0.78rem">{r["Verdict"]}</span></td>'
                f'</tr>'
            )
        hdr = "".join(
            f'<th style="padding:9px 6px;text-align:left;color:{C.GREEN};'
            f'font-size:0.65rem;letter-spacing:1px;white-space:nowrap;'
            f'background:{C.SURFACE2};border-bottom:2px solid {C.GREEN}44">{h}</th>'
            for h in ["TIER","TICKER","COMPANY","SECTOR","PRICE","TARGET",
                       "UPSIDE","TODAY","ROIC%","FCF%","FWD PE","VERDICT"]
        )
        st.markdown(
            f'<div style="overflow-x:auto;border:1px solid {C.BORDER};'
            f'border-radius:10px;overflow:hidden">'
            f'<table style="width:100%;border-collapse:collapse;font-size:0.82rem">'
            f'<thead><tr>{hdr}</tr></thead>'
            f'<tbody>{rows_html}</tbody></table></div>'
            f'<div style="font-size:0.65rem;color:{C.TEXT3};margin-top:8px">'
            f'Auto target = TTM EPS × (1+EPS growth%) × Fwd PE. '
            f'Set custom Fair Value above to override. Switch to Cards for detail view.</div>',
            unsafe_allow_html=True,
        )
