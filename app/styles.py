# app/styles.py  —  Global CSS injected once at startup
from app.config import BG, SURFACE, SURFACE2, BORDER, BORDER2, GREEN, GOLD, RED, TEXT, TEXT2, TEXT3

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Reset & base ── */
html, body, [class*="css"] {{
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.stApp {{ background-color: {BG}; }}
.block-container {{ padding: 0.5rem 1.5rem 2rem 1.5rem !important; }}
#MainMenu, footer, header {{ visibility: hidden; }}

/* ── Scrollbar ── */
::-webkit-scrollbar {{ width:5px; height:5px; }}
::-webkit-scrollbar-track {{ background:{BG}; }}
::-webkit-scrollbar-thumb {{ background:{BORDER2}; border-radius:3px; }}
::-webkit-scrollbar-thumb:hover {{ background:{GREEN}; }}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #050709 0%, #090D16 100%);
  border-right: 1px solid {BORDER};
}}

/* ── Streamlit radio & select overrides ── */
[data-testid="stRadio"] > div {{ gap: 8px; }}
.stButton > button {{
  background: {SURFACE2} !important;
  border: 1px solid {BORDER2} !important;
  color: {TEXT2} !important;
  font-family: 'Inter', sans-serif !important;
  border-radius: 6px !important;
  font-size: 0.82rem !important;
  transition: all 0.15s !important;
}}
.stButton > button:hover {{
  border-color: {GREEN} !important;
  color: {GREEN} !important;
  background: {SURFACE} !important;
}}
.stSelectbox > div > div,
.stMultiSelect > div > div,
.stNumberInput > div > div > input,
.stTextInput > div > div > input {{
  background: {SURFACE2} !important;
  border-color: {BORDER2} !important;
  color: {TEXT} !important;
  border-radius: 6px !important;
}}
.stSlider [data-baseweb="slider"] {{
  margin-top: 0.2rem;
}}
[data-baseweb="tab-list"] {{ background: {SURFACE} !important; border-radius: 8px; }}
[data-baseweb="tab"] {{ color: {TEXT2} !important; }}
[aria-selected="true"] {{ color: {GREEN} !important; }}

/* ── Expander ── */
[data-testid="stExpander"] {{
  background: {SURFACE} !important;
  border: 1px solid {BORDER} !important;
  border-radius: 8px !important;
}}

/* ── Live dot ── */
@keyframes blink {{ 0%,100%{{opacity:1;transform:scale(1)}} 50%{{opacity:.4;transform:scale(1.4)}} }}
.live-dot {{
  width:8px; height:8px; border-radius:50%; background:{GREEN};
  box-shadow:0 0 10px {GREEN}; display:inline-block; margin-right:6px;
  animation:blink 2s ease-in-out infinite;
}}

/* ── Plotly overrides ── */
.js-plotly-plot .plotly {{ background: transparent !important; }}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER} !important; border-radius: 8px; }}
</style>
"""

# ── Reusable inline-style HTML helpers ───────────────────────

def progress_bar(pct: float, color: str, height: int = 7,
                 bg: str = "#1A2332") -> str:
    """100% inline-style progress bar — safe inside any st.markdown()."""
    w = max(0, min(int(pct), 100))
    return (
        f'<div style="background:{bg};border-radius:3px;height:{height}px;'
        f'width:100%;overflow:hidden;margin:4px 0">'
        f'<div style="height:{height}px;border-radius:3px;width:{w}%;'
        f'background:linear-gradient(90deg,{color}88,{color});'
        f'transition:width 0.4s ease"></div></div>'
    )


def badge(text: str, color: str, bg: str, size: str = "0.65rem") -> str:
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'padding:2px 9px;border-radius:4px;font-size:{size};'
        f'font-weight:700;font-family:\'JetBrains Mono\',monospace;'
        f'letter-spacing:0.5px">{text}</span>'
    )


def card(content: str, border_left: str = "#1A2332",
         bg: str = "#0D1219", extra_style: str = "") -> str:
    return (
        f'<div style="background:{bg};border:1px solid #1A2332;'
        f'border-left:4px solid {border_left};border-radius:10px;'
        f'padding:16px 18px;margin-bottom:10px;{extra_style}">'
        f'{content}</div>'
    )


def label(text: str) -> str:
    return (
        f'<div style="font-size:0.6rem;color:#475569;text-transform:uppercase;'
        f'letter-spacing:1.5px;font-weight:600;margin-bottom:3px">{text}</div>'
    )


def mono(text: str, color: str = "#E2E8F0", size: str = "1rem",
         weight: str = "600") -> str:
    return (
        f'<span style="font-family:\'JetBrains Mono\',monospace;'
        f'color:{color};font-size:{size};font-weight:{weight}">{text}</span>'
    )


def section_title(text: str) -> str:
    return (
        f'<div style="font-family:\'JetBrains Mono\',monospace;'
        f'font-size:0.72rem;font-weight:700;color:#00D26A;'
        f'text-transform:uppercase;letter-spacing:2.5px;'
        f'border-bottom:1px solid #1A2332;padding-bottom:8px;'
        f'margin-bottom:16px;margin-top:4px">{text}</div>'
    )
