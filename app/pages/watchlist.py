# app/pages/watchlist.py
import streamlit as st
import pandas as pd
from app import config as C
from app.utils import fmt_price, fmt_pct
from app.styles import section_title
from app.data_loader import save_user_data


def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("🔔  Watchlist & Buy Alerts"), unsafe_allow_html=True)
    ud    = st.session_state.user_data
    watch = ud.setdefault("watchlist", {})

    with st.expander("➕  Add Stock to Watchlist", expanded=not watch):
        tks = sorted(df_main["Ticker"].tolist())
        c1, c2, c3 = st.columns(3)
        w_tk   = c1.selectbox("Ticker", tks, key="wl_tk")
        w_tgt  = c2.number_input("Target Buy Price ($)", min_value=0.01,
                                  value=float(watch.get(w_tk, {}).get("target_price", 100.0)),
                                  step=1.0, key="wl_tgt")
        w_note = c3.text_input("Note", value=watch.get(w_tk, {}).get("note", ""), key="wl_note")
        if st.button("💾  Add to Watchlist", use_container_width=True):
            watch[w_tk] = {"target_price": w_tgt, "note": w_note}
            ud["watchlist"] = watch; save_user_data(ud)
            st.success(f"Added {w_tk}."); st.rerun()

    if not watch:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};border-radius:8px;'
            f'padding:20px;text-align:center;color:{C.TEXT3}">Watchlist is empty.</div>',
            unsafe_allow_html=True)
        return

    st.markdown("---")
    alerts_fired = 0

    for tk, w in list(watch.items()):
        row_df  = df_main[df_main["Ticker"] == tk]
        company = row_df["Company"].values[0] if len(row_df) else tk
        tier    = row_df["Tier"].values[0]    if len(row_df) else "—"
        tc      = C.TIER.get(tier, {})

        pd_d = prices.get(tk) or {}
        cur  = pd_d.get("price")
        chg  = pd_d.get("change_pct")
        tgt  = w["target_price"]
        note = w.get("note", "")

        if cur:
            dist  = (cur - tgt) / tgt * 100
            fired = cur <= tgt
            close = not fired and dist <= 5
        else:
            dist  = None; fired = False; close = False

        if fired:
            alerts_fired += 1
            border = C.GREEN; bg = C.GREEN_BG
        elif close:
            border = C.GOLD;  bg = C.GOLD_BG
        else:
            border = C.BORDER; bg = C.SURFACE

        chg_col = C.GREEN if (chg or 0) >= 0 else C.RED
        dc      = C.GREEN if (dist or 0) < 0 else C.TEXT3

        alert_html = ""
        if fired:
            alert_html = (f'<span style="background:{C.GREEN};color:#000;padding:3px 10px;'
                          f'border-radius:20px;font-size:0.65rem;font-weight:800;'
                          f'letter-spacing:1px;margin-left:8px">🔔 BUY ALERT</span>')
        elif close:
            alert_html = (f'<span style="background:{C.GOLD_BG};color:{C.GOLD};padding:2px 8px;'
                          f'border-radius:10px;font-size:0.65rem;font-weight:700;'
                          f'margin-left:8px">⚡ CLOSE</span>')

        c1, c2 = st.columns([9, 1])
        c1.markdown(
            f'<div style="background:{bg};border:1px solid {border};'
            f'border-left:4px solid {border};border-radius:12px;'
            f'padding:16px 20px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:8px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.05rem;'
            f'font-weight:700;color:{C.GREEN}">{tk}</span>'
            f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
            f'padding:1px 7px;border-radius:3px;font-size:0.62rem;font-weight:700">{tier}</span>'
            f'<span style="font-size:0.8rem;color:{C.TEXT3}">{company}</span>'
            f'{alert_html}'
            f'</div>'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.35rem;'
            f'color:{C.GREEN if fired else C.TEXT};font-weight:700">{fmt_price(cur)}</span>'
            f'</div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">'
            + "".join([
                f'<div style="background:{C.SURFACE2};border-radius:6px;padding:10px">'
                f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
                f'letter-spacing:1.2px;margin-bottom:4px">{l}</div>'
                f'<div style="font-family:\'JetBrains Mono\',monospace;color:{c};'
                f'font-weight:600;font-size:0.9rem">{v}</div>'
                f'</div>'
                for l, v, c in [
                    ("Current Price", fmt_price(cur),  C.GREEN if fired else C.TEXT),
                    ("Target Price",  fmt_price(tgt),  C.GOLD),
                    ("Distance",
                     f"{dist:+.1f}% from target" if dist is not None else "—", dc),
                    ("Today",         fmt_pct(chg),    chg_col),
                ]
            ])
            + f'</div>'
            + (f'<div style="font-size:0.75rem;color:{C.TEXT3};margin-top:8px">📝 {note}</div>' if note else "")
            + f'</div>',
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"wl_del_{tk}", help=f"Remove {tk}"):
            del watch[tk]; ud["watchlist"] = watch; save_user_data(ud); st.rerun()

    if alerts_fired:
        st.balloons()
