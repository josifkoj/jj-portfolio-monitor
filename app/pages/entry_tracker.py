# app/pages/entry_tracker.py
import streamlit as st
import pandas as pd
from app import config as C
from app.utils import fmt_price, fmt_pct, compute_upside, upside_color
from app.styles import progress_bar, section_title
from app.data_loader import save_user_data


def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("💰  Entry Price Tracker"), unsafe_allow_html=True)
    ud  = st.session_state.user_data
    eps = ud.setdefault("entry_prices", {})

    with st.expander("➕  Add / Edit Position", expanded=not eps):
        tks = sorted(df_main["Ticker"].tolist())
        c1, c2, c3, c4 = st.columns(4)
        sel = c1.selectbox("Ticker", tks, key="ep_tk")
        ent = c2.number_input("Entry Price ($)", min_value=0.01,
            value=float(eps.get(sel, {}).get("price", 100.0)), step=0.01, key="ep_price")
        sh  = c3.number_input("Shares", min_value=0.0,
            value=float(eps.get(sel, {}).get("shares", 10.0)), step=1.0, key="ep_shares")
        tgt = c4.number_input("Your Target Price ($)", min_value=0.01,
            value=float(eps.get(sel, {}).get("target", ent * 1.25)), step=0.01, key="ep_target")
        a, b = st.columns(2)
        if a.button("💾  Save", use_container_width=True):
            eps[sel] = {"price": ent, "shares": sh, "target": tgt}
            ud["entry_prices"] = eps; save_user_data(ud)
            st.success(f"Saved {sel}."); st.rerun()
        if sel in eps and b.button(f"🗑️  Remove {sel}", use_container_width=True):
            del eps[sel]; ud["entry_prices"] = eps; save_user_data(ud); st.rerun()

    if not eps:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:20px;text-align:center;color:{C.TEXT3}">'
            f'No positions yet. Add your first above.</div>', unsafe_allow_html=True)
        return

    st.markdown("---")
    for tk, pos in eps.items():
        row_df  = df_main[df_main["Ticker"] == tk]
        company = row_df["Company"].values[0] if len(row_df) else tk
        tier    = row_df["Tier"].values[0] if len(row_df) else "—"
        roic    = row_df["ROIC %"].values[0] if len(row_df) else "—"

        pd_d    = prices.get(tk) or {}
        cur     = pd_d.get("price")
        chg     = pd_d.get("change_pct")

        ep_p    = pos["price"]
        sh_n    = pos["shares"]
        ep_tgt  = pos["target"]

        chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
        tc      = C.TIER.get(tier, {})

        if cur:
            dist    = (cur - ep_p) / ep_p * 100
            pnl_d   = (cur - ep_p) * sh_n
            is_up   = cur >= ep_p
            dc      = C.GREEN if is_up else C.RED
            prog    = (cur - ep_p) / (ep_tgt - ep_p) * 100 if ep_tgt != ep_p else 0
            prog_c  = max(0, min(int(prog), 100))
            prog_color = C.GREEN if prog >= 0 else C.RED
        else:
            dist = pnl_d = 0; is_up = False; dc = C.TEXT3
            prog_c = 0; prog_color = C.TEXT3

        auto_up, auto_tgt = compute_upside(row_df.iloc[0] if len(row_df) else pd.Series(), cur) if len(row_df) else (None, None)
        uc = upside_color(auto_up)

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {dc};border-radius:12px;padding:18px 20px;margin-bottom:12px">'

            # Header
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.1rem;'
            f'font-weight:700;color:{C.GREEN}">{tk}</span>'
            f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
            f'padding:2px 8px;border-radius:4px;font-size:0.62rem;font-weight:700">{tier}</span>'
            f'<span style="font-size:0.8rem;color:{C.TEXT3}">{company}</span>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.3rem;'
            f'font-weight:700;color:{C.TEXT}">{fmt_price(cur)}</span>'
            f'<span style="font-size:0.78rem;color:{chg_col};margin-left:8px">{fmt_pct(chg)}</span>'
            f'</div></div>'

            # 5-column grid
            f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:12px">'
            + "".join([
                f'<div style="background:{C.SURFACE2};border-radius:6px;padding:10px">'
                f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;letter-spacing:1.2px;margin-bottom:4px">{l}</div>'
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-weight:600;color:{c};font-size:0.95rem">{v}</div>'
                f'</div>'
                for l, v, c in [
                    ("Entry Price",   fmt_price(ep_p),              C.TEXT),
                    ("Shares",        f"{sh_n:,.0f}",               C.TEXT),
                    ("Distance",      fmt_pct(dist if cur else None),dc),
                    ("P&L",           fmt_price(pnl_d) if cur else "—", dc),
                    ("Target",        fmt_price(ep_tgt),            C.GOLD),
                ]
            ])
            + f'</div>'

            # Progress to target
            f'<div style="margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.62rem;'
            f'color:{C.TEXT3};margin-bottom:3px">'
            f'<span>Entry: {fmt_price(ep_p)}</span>'
            f'<span style="color:{prog_color}">{prog_c}% to target'
            f'{"  ✅ TARGET REACHED" if prog_c >= 100 else ""}</span>'
            f'<span>Target: {fmt_price(ep_tgt)}</span>'
            f'</div>'
            + progress_bar(prog_c, prog_color, height=8)
            + f'</div>'

            # Auto-upside note
            f'<div style="font-size:0.68rem;color:{C.TEXT3}">'
            f'ROIC: <b style="color:{C.GREEN}">{roic}%</b> · '
            f'Auto fair value upside: <b style="color:{uc}">{fmt_pct(auto_up)}</b>'
            f' (target {fmt_price(auto_tgt)})</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
