# app/pages/heatmap.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app import config as C
from app.utils import fmt_price
from app.styles import section_title


def render(df_main: pd.DataFrame, prices: dict):
    st.markdown(section_title("🗺️  Conviction Heat Map — ROIC vs Valuation"),
                unsafe_allow_html=True)

    df = df_main.copy()
    df["Live"] = df["Ticker"].map(lambda t: (prices.get(t) or {}).get("price"))

    c1, c2 = st.columns([3, 1])
    with c2:
        x_ax  = st.selectbox("X Axis",    ["PE (TTM)", "Fwd PE", "Net Debt/EBITDA"], key="hm_x")
        y_ax  = st.selectbox("Y Axis",    ["ROIC %", "FCF Margin %", "Gross Margin %"], key="hm_y")
        sz_by = st.selectbox("Bubble Size",["FCF Margin %","ROIC %","EPS Growth %"], key="hm_sz")
        labels= st.checkbox("Show Labels", value=True, key="hm_lbl")
        st.markdown("---")
        st.markdown(
            f'<div style="font-size:0.72rem;color:{C.TEXT3};line-height:2">'
            f'<span style="color:{C.GREEN}">●</span> T1 Core<br>'
            f'<span style="color:{C.GOLD}">●</span> T2 Quality<br>'
            f'<span style="color:#FF8C42">●</span> T3 Watch<br>'
            f'Bubble = {sz_by}<br>Lines = median</div>',
            unsafe_allow_html=True,
        )

    with c1:
        fig = go.Figure()
        tier_cols = {"T1": C.GREEN, "T2": C.GOLD, "T3": "#FF8C42"}

        for tier, col in tier_cols.items():
            sub = df[df["Tier"] == tier]
            fig.add_trace(go.Scatter(
                x=sub[x_ax], y=sub[y_ax],
                mode="markers+text" if labels else "markers",
                name=tier,
                text=sub["Ticker"],
                textposition="top center",
                textfont=dict(size=9, color=col, family="JetBrains Mono"),
                marker=dict(
                    size=sub[sz_by].fillna(5) * 1.1,
                    color=col, opacity=0.88, sizemin=7,
                    line=dict(width=1.5, color=C.BG),
                ),
                hovertemplate=(
                    f"<b>%{{text}}</b><br>{x_ax}: %{{x}}<br>"
                    f"{y_ax}: %{{y}}%<br>{sz_by}: %{{marker.size:.0f}}%<extra></extra>"
                ),
            ))

        # Quadrant lines
        for val, ref in [(df[x_ax].median(), "x"), (df[y_ax].median(), "y")]:
            fig.add_shape(type="line",
                xref=("x" if ref == "x" else "paper"),
                yref=("paper" if ref == "x" else "y"),
                x0=(val if ref == "x" else 0), x1=(val if ref == "x" else 1),
                y0=(0  if ref == "x" else val), y1=(1  if ref == "x" else val),
                line=dict(color=C.BORDER2, width=1, dash="dot"))

        # Quadrant labels
        for txt, xx, yy, col in [
            ("⭐ Sweet Spot",        df[x_ax].min()*1.05, df[y_ax].max()*0.95, C.GREEN),
            ("🏆 Quality Premium",   df[x_ax].max()*0.90, df[y_ax].max()*0.95, C.GOLD),
            ("⚠️ Value Trap",        df[x_ax].min()*1.05, df[y_ax].min()*1.10, C.RED),
            ("📉 Cheap Low Quality", df[x_ax].max()*0.90, df[y_ax].min()*1.10, C.TEXT3),
        ]:
            fig.add_annotation(x=xx, y=yy, text=txt, showarrow=False,
                               font=dict(size=9, color=col))

        fig.update_layout(
            paper_bgcolor=C.BG, plot_bgcolor=C.SURFACE,
            font_color=C.TEXT2, height=580,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
            xaxis=dict(title=x_ax, gridcolor=C.BORDER, zeroline=False),
            yaxis=dict(title=y_ax, gridcolor=C.BORDER, zeroline=False),
            hoverlabel=dict(bgcolor=C.SURFACE, bordercolor=C.GREEN,
                            font=dict(family="JetBrains Mono")),
        )
        st.plotly_chart(fig, use_container_width=True)
