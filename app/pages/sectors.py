# app/pages/sectors.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app import config as C
from app.styles import section_title


def render(df_sectors: pd.DataFrame):
    st.markdown(section_title("🏭  Sector Allocation — JJ Research Verdicts"),
                unsafe_allow_html=True)

    def _verdict_meta(v: str):
        if not isinstance(v, str): return C.TEXT3, "—", C.SURFACE
        vu = v.upper()
        if "OVERWEIGHT" in vu:  return C.GREEN,  "OVERWEIGHT",  C.GREEN_BG
        if "SELECTIVE"  in vu:  return C.GOLD,   "SELECTIVE",   C.GOLD_BG
        if "UNDERWEIGHT"in vu:  return C.RED,    "UNDERWEIGHT", C.RED_BG
        if "ZERO"       in vu:  return "#CC2020", "ZERO",       "#1A0505"
        return C.TEXT3, "—", C.SURFACE

    df = df_sectors.copy()
    df["_color"], df["_tag"], df["_bg"] = zip(*df["Overall Verdict"].map(_verdict_meta))
    df["_margin"] = (
        df["Sector Net Margin 2025"]
        .astype(str).str.replace("%","",regex=False).str.strip()
        .apply(lambda x: float(x) if x not in ("nan","") else 0)
    )

    # Bar chart
    fig = go.Figure()
    for tag, col in [("OVERWEIGHT",C.GREEN),("SELECTIVE",C.GOLD),
                      ("UNDERWEIGHT",C.RED),("ZERO","#CC2020")]:
        sub = df[df["_tag"] == tag]
        if sub.empty: continue
        fig.add_trace(go.Bar(
            x=sub["Sector"], y=sub["_margin"], name=tag,
            marker_color=col,
            text=[f"{m:.1f}%" for m in sub["_margin"]],
            textposition="outside", textfont=dict(size=10, color=col),
        ))
    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
        font_color=C.TEXT2, height=380,
        margin=dict(l=10,r=10,t=20,b=100), barmode="group",
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title="Net Margin 2025 (%)", gridcolor=C.BORDER),
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown(section_title("Sector Verdicts"), unsafe_allow_html=True)

    for _, row in df.iterrows():
        col, tag, bg = row["_color"], row["_tag"], row["_bg"]
        verdict = str(row["Overall Verdict"]) if pd.notna(row["Overall Verdict"]) else "—"
        picks   = str(row["Best Picks"])      if pd.notna(row["Best Picks"])      else "—"
        quality = str(row["Quality Companies Found"]) if pd.notna(row["Quality Companies Found"]) else "—"

        st.markdown(
            f'<div style="background:{C.SURFACE};border:1px solid {C.BORDER};'
            f'border-left:4px solid {col};border-radius:10px;'
            f'padding:14px 18px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.95rem;'
            f'font-weight:700;color:{C.TEXT}">{row["Sector"]}</span>'
            f'<span style="background:{bg};color:{col};padding:2px 10px;border-radius:4px;'
            f'font-size:0.65rem;font-weight:700;letter-spacing:1px">{tag}</span>'
            f'</div>'
            f'<div style="font-size:0.72rem;color:{C.TEXT3};text-align:right">'
            f'Net Margin: <b style="color:{C.TEXT}">{row["Sector Net Margin 2025"]}</b> · '
            f'Asset-Light: <b style="color:{C.TEXT}">{row["Asset-Light Score"]}</b>'
            f'</div></div>'
            f'<div style="font-size:0.8rem;color:{C.TEXT};line-height:1.6;margin-bottom:6px">{verdict}</div>'
            f'<div style="font-size:0.73rem;color:{C.TEXT3}">'
            f'<b style="color:{C.GREEN}">Best picks:</b> {picks}<br>'
            f'<b style="color:{C.TEXT3}">In universe:</b> {quality}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
