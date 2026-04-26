# app/pages/rejected.py
import streamlit as st
import pandas as pd
from app import config as C
from app.utils import fmt_price, fmt_pct
from app.styles import section_title


def render(df_rej: pd.DataFrame, prices: dict):
    st.markdown(section_title("❌  Rejected Stocks Explorer"), unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:{C.RED_BG};border:1px solid {C.RED}33;'
        f'border-radius:8px;padding:12px 16px;font-size:0.8rem;'
        f'color:{C.TEXT2};margin-bottom:20px">'
        f'These stocks failed the JJ quality screen. Primary failure modes: '
        f'commodity exposure, low/negative margins, capital intensity, no pricing power, '
        f'or regulatory risk without moat protection.</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([3, 1])
    search  = c1.text_input("🔍 Search ticker, company, or rejection keyword",
                             placeholder="e.g. TSLA  or  capital intensive", key="rej_q")
    sec_f   = c2.selectbox("Sector",
                            ["All"] + sorted(df_rej["Sector"].unique().tolist()),
                            key="rej_sec")

    df = df_rej.copy()
    if search:
        m = (df["Ticker"].str.contains(search, case=False, na=False) |
             df["Company"].str.contains(search, case=False, na=False) |
             df["Rejection Reason"].str.contains(search, case=False, na=False))
        df = df[m]
    if sec_f != "All":
        df = df[df["Sector"] == sec_f]

    st.markdown(
        f'<div style="font-size:0.78rem;color:{C.TEXT3};margin-bottom:12px">'
        f'{len(df)} of {len(df_rej)} rejected stocks</div>',
        unsafe_allow_html=True,
    )

    BAD_TERMS = ["REJECT", "capital intensive", "no moat", "cyclical",
                 "commodity", "low margin", "regulatory", "no pricing power",
                 "debt", "dilution", "capex"]

    for _, row in df.iterrows():
        tk   = row["Ticker"]
        pd_d = prices.get(tk) or {}
        cur  = pd_d.get("price")
        chg  = pd_d.get("change_pct")
        chg_col = C.GREEN if (chg or 0) >= 0 else C.RED

        reason = str(row["Rejection Reason"])
        for term in BAD_TERMS:
            reason = reason.replace(
                term,
                f'<span style="color:{C.RED};font-weight:600">{term}</span>'
            )

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {C.RED};border-radius:10px;'
            f'padding:14px 18px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:6px">'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
            f'font-weight:700;color:{C.RED}">✗ {tk}</span>'
            f'<span style="font-size:0.8rem;color:{C.TEXT3}">{row["Company"]}</span>'
            f'<span style="background:{C.RED_BG};color:{C.RED}88;padding:1px 8px;'
            f'border-radius:3px;font-size:0.65rem;font-weight:600">{row["Sector"]}</span>'
            f'</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.85rem;'
            f'color:{C.TEXT3};text-align:right">'
            f'{fmt_price(cur)}'
            f'<span style="color:{chg_col};margin-left:8px">'
            f'{fmt_pct(chg) if chg is not None else ""}</span>'
            f'</div></div>'
            f'<div style="font-size:0.8rem;color:{C.TEXT2};line-height:1.6">{reason}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
