# app/config.py  —  Design tokens, constants, paths
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────
ROOT          = Path(__file__).parent.parent
EXCEL_PATH    = ROOT / "SP500_Analysis.xlsx"
USER_DATA     = ROOT / "user_data.json"

# ── Palette ───────────────────────────────────────────────────
BG        = "#060810"
SURFACE   = "#0D1219"
SURFACE2  = "#111827"
BORDER    = "#1A2332"
BORDER2   = "#243146"

GREEN     = "#86E3B0"
GREEN_DIM = "#5BC287"
GREEN_BG  = "#0A1F14"

GOLD      = "#F5D585"
GOLD_DIM  = "#C9A95A"
GOLD_BG   = "#1F1A0A"

RED       = "#F39A9A"
RED_DIM   = "#C97070"
RED_BG    = "#1F0E0E"

BLUE      = "#A8C8F5"
PURPLE    = "#C9B0FF"
TEAL      = "#9EE0D2"

TEXT      = "#E2E8F0"
TEXT2     = "#94A3B8"
TEXT3     = "#475569"
TEXT4     = "#2D3748"

# ── Typography ────────────────────────────────────────────────
MONO = "'JetBrains Mono', 'Courier New', monospace"
SANS = "'Inter', 'Segoe UI', system-ui, sans-serif"

# ── Tier system ───────────────────────────────────────────────
TIER = {
    "T1": {"color": GREEN,   "bg": GREEN_BG,  "dim": GREEN_DIM,  "text": "#A7F3C8"},
    "T2": {"color": GOLD,    "bg": GOLD_BG,   "dim": GOLD_DIM,   "text": "#FDE68A"},
    "T3": {"color": "#FF8C42","bg": "#180B00", "dim": "#CC6010",  "text": "#FDBA74"},
}

# ── Verdict system ────────────────────────────────────────────
VERDICT = {
    "BUY":       {"color": GREEN,  "bg": GREEN_BG},
    "CORE HOLD": {"color": BLUE,   "bg": "#051226"},
    "HOLD":      {"color": BLUE,   "bg": "#051226"},
    "WATCHLIST": {"color": PURPLE, "bg": "#0D0526"},
    "WAIT":      {"color": GOLD,   "bg": GOLD_BG},
}

# ── Upside thresholds ─────────────────────────────────────────
def upside_color(u):
    if u is None: return TEXT3
    if u >= 25:   return GREEN
    if u >= 15:   return "#5EE896"
    if u >= 5:    return GOLD
    if u >= 0:    return "#FF9B3D"
    return RED

# ── Navigation pages ─────────────────────────────────────────
PAGES = [
    ("🏠", "Dashboard"),
    ("🔬", "Analyzer"),
    ("📋", "Stocks to Watch"),
    ("💰", "Entry Tracker"),
    ("🔍", "Screener"),
    ("📡", "Live Prices"),
    ("🔔", "Watchlist"),
    ("🗺️", "Heat Map"),
    ("💼", "Portfolio"),
    ("🏭", "Sectors"),
    ("🏆", "Top 10"),
    ("❌", "Rejected"),
    ("📰", "Market Pulse"),
]
