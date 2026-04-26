# app/pages/portfolio.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from app import config as C
from app.utils import fmt_price, fmt_pct
from app.styles import progress_bar, section_title
from app.data_loader import save_user_data


def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("💼  Portfolio Simulator"), unsafe_allow_html=True)
    ud   = st.session_state.user_data
    port = ud.setdefault("portfolio", {})

    with st.expander("➕  Add / Edit Position", expanded=not port):
        tks = sorted(df_main["Ticker"].tolist())
        c1, c2, c3 = st.columns(3)
        p_tk = c1.selectbox("Ticker", tks, key="port_tk")
        p_sh = c2.number_input("Shares", min_value=0.0,
                                value=float(port.get(p_tk, {}).get("shares", 10.0)),
                                step=1.0, key="port_sh")
        p_ep = c3.number_input("Entry Price ($)", min_value=0.01,
                                value=float(port.get(p_tk, {}).get("entry_price", 100.0)),
                                step=0.01, key="port_ep")
        a, b = st.columns(2)
        if a.button("💾  Save", use_container_width=True):
            port[p_tk] = {"shares": p_sh, "entry_price": p_ep}
            ud["portfolio"] = port; save_user_data(ud)
            st.success(f"Saved {p_tk}."); st.rerun()
        if p_tk in port and b.button(f"🗑️  Remove {p_tk}", use_container_width=True):
            del port[p_tk]; ud["portfolio"] = port; save_user_data(ud); st.rerun()

    if not port:
        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:8px;padding:20px;text-align:center;color:{C.TEXT3}">'
            f'No positions yet.</div>', unsafe_allow_html=True)
        return

    # ── Build DataFrame ──────────────────────────────────────
    rows = []
    for tk, pos in port.items():
        row_df  = df_main[df_main["Ticker"] == tk]
        company = row_df["Company"].values[0] if len(row_df) else tk
        sector  = row_df["Sector"].values[0]  if len(row_df) else "Unknown"
        tier    = row_df["Tier"].values[0]    if len(row_df) else "T3"
        roic    = float(row_df["ROIC %"].values[0]) if len(row_df) else 0.0

        cur   = (prices.get(tk) or {}).get("price")
        sh    = pos["shares"]
        ep    = pos["entry_price"]
        cost  = ep * sh
        mval  = cur * sh if cur else None
        pnl   = (mval - cost) if mval else None
        pnlp  = (pnl / cost * 100) if (pnl is not None and cost) else None
        rows.append({
            "Ticker": tk, "Company": company, "Sector": sector,
            "Tier": tier, "ROIC %": roic, "Shares": sh,
            "Entry": ep, "Price": cur or 0, "Cost": cost,
            "MVal": mval or 0, "PnL": pnl or 0, "PnLp": pnlp or 0,
        })

    df_p = pd.DataFrame(rows)
    tot_cost = df_p["Cost"].sum()
    tot_mval = df_p["MVal"].sum()
    tot_pnl  = df_p["PnL"].sum()
    tot_pnlp = tot_pnl / tot_cost * 100 if tot_cost else 0
    df_p["Wt"] = df_p["MVal"] / tot_mval * 100 if tot_mval else 0
    roic_score = (df_p["ROIC %"] * df_p["Wt"]).sum() / 100

    # ── KPI row ──────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    pc = C.GREEN if tot_pnl >= 0 else C.RED
    for col, lbl, val, d, dc in [
        (k1, "Total Cost Basis",  f"${tot_cost:,.0f}", "",                       C.TEXT3),
        (k2, "Market Value",      f"${tot_mval:,.0f}", f"{len(df_p)} positions", C.TEXT3),
        (k3, "Total P&L",         f"${tot_pnl:+,.0f}", fmt_pct(tot_pnlp),       pc),
        (k4, "ROIC Quality Score",f"{roic_score:.1f}%","Wt avg ROIC of holdings",C.GREEN),
        (k5, "Largest Position",
         df_p.loc[df_p["Wt"].idxmax(), "Ticker"] if not df_p.empty else "—",
         f'{df_p["Wt"].max():.1f}% of portfolio' if not df_p.empty else "", C.GOLD),
    ]:
        col.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-radius:10px;padding:14px 16px">'
            f'<div style="font-size:0.58rem;color:{C.TEXT3};text-transform:uppercase;'
            f'letter-spacing:1.4px;margin-bottom:6px">{lbl}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.35rem;'
            f'font-weight:700;color:{C.TEXT}">{val}</div>'
            f'<div style="font-size:0.75rem;color:{dc};margin-top:3px">{d}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(section_title("Holdings Detail"), unsafe_allow_html=True)

    for _, r in df_p.sort_values("Wt", ascending=False).iterrows():
        dc  = C.GREEN if r["PnL"] >= 0 else C.RED
        tc  = C.TIER.get(r["Tier"], {})
        wt_w= int(r["Wt"])

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {dc};border-radius:10px;'
            f'padding:14px 18px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;'
            f'font-weight:700;color:{C.GREEN}">{r["Ticker"]}</span>'
            f'<span style="background:{tc.get("bg",C.SURFACE)};color:{tc.get("color",C.TEXT)};'
            f'padding:1px 7px;border-radius:3px;font-size:0.6rem;font-weight:700">{r["Tier"]}</span>'
            f'<span style="font-size:0.78rem;color:{C.TEXT3}">{r["Company"]} · {r["Sector"]}</span>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.15rem;'
            f'font-weight:700;color:{C.TEXT}">{fmt_price(r["Price"])}</span>'
            f'</div></div>'
            f'<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:8px">'
            + "".join([
                f'<div style="background:{C.SURFACE2};border-radius:5px;padding:8px">'
                f'<div style="font-size:0.55rem;color:{C.TEXT3};text-transform:uppercase;'
                f'letter-spacing:1px;margin-bottom:3px">{l}</div>'
                f'<div style="font-family:\'JetBrains Mono\',monospace;color:{c};'
                f'font-size:0.85rem;font-weight:600">{v}</div>'
                f'</div>'
                for l, v, c in [
                    ("Shares",    f"{r['Shares']:,.0f}",       C.TEXT),
                    ("Avg Cost",  fmt_price(r["Entry"]),       C.TEXT),
                    ("Mkt Value", f"${r['MVal']:,.0f}",        C.TEXT),
                    ("P&L $",     f"${r['PnL']:+,.0f}",        dc),
                    ("P&L %",     fmt_pct(r["PnLp"]),          dc),
                    ("Weight",    f"{r['Wt']:.1f}%",           C.GOLD),
                ]
            ])
            + f'</div>'
            + progress_bar(wt_w, C.GOLD, height=4)
            + f'<div style="font-size:0.6rem;color:{C.TEXT3};margin-top:2px">'
            f'Portfolio weight: {r["Wt"]:.1f}% · ROIC: {r["ROIC %"]}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Charts ───────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(section_title("Allocation Charts"), unsafe_allow_html=True)
    ch1, ch2, ch3 = st.columns(3)

    def _pie(data, names, title, col):
        fig = px.pie(data, values="MVal", names=names, hole=0.45, title=title,
                     color_discrete_sequence=[C.GREEN, C.GOLD, "#FF8C42", C.BLUE,
                                              C.PURPLE, C.TEAL, "#FF6B6B","#A8E063"])
        fig.update_layout(paper_bgcolor=C.BG, font_color=C.TEXT2, height=280,
                          margin=dict(l=10,r=10,t=40,b=10),
                          title_font=dict(size=11,color=C.GREEN),
                          showlegend=True, legend=dict(font=dict(size=8)))
        fig.update_traces(textfont_size=9)
        col.plotly_chart(fig, use_container_width=True)

    sec_df  = df_p.groupby("Sector")["MVal"].sum().reset_index()
    tier_df = df_p.groupby("Tier")["MVal"].sum().reset_index()
    _pie(sec_df,  "Sector", "By Sector", ch1)
    _pie(tier_df, "Tier",   "By Tier",   ch2)

    pnl_s = df_p.sort_values("PnLp")
    fig3 = px.bar(pnl_s, x="PnLp", y="Ticker", orientation="h",
                   color="PnLp", title="P&L % by Position",
                   color_continuous_scale=["#FF4545","#1A2332","#00D26A"],
                   color_continuous_midpoint=0,
                   text=pnl_s["PnLp"].apply(lambda x: f"{x:+.1f}%"))
    fig3.update_layout(paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE, font_color=C.TEXT2,
                       height=280, margin=dict(l=10,r=20,t=40,b=10),
                       title_font=dict(size=11,color=C.GREEN),
                       coloraxis_showscale=False,
                       xaxis=dict(gridcolor=C.BORDER, zeroline=True,
                                  zerolinecolor=C.GREEN, zerolinewidth=1),
                       yaxis=dict(gridcolor=C.BORDER))
    fig3.update_traces(textposition="outside", textfont_size=9)
    ch3.plotly_chart(fig3, use_container_width=True)
