# app/utils.py  —  Pure helper functions, no Streamlit imports
import re
import pandas as pd
from app.config import VERDICT, TIER, upside_color   # noqa: F401  (re-export)


# ── Formatters ────────────────────────────────────────────────
def fmt_price(p, currency: str = "$") -> str:
    if p is None: return "—"
    try:
        v = float(p)
        if v >= 10_000: return f"{currency}{v:,.0f}"
        if v >= 1_000:  return f"{currency}{v:,.1f}"
        return f"{currency}{v:,.2f}"
    except Exception:
        return "—"


def fmt_mktcap(mc) -> str:
    if mc is None: return "—"
    try:
        v = float(mc)
        if v >= 1e12: return f"${v/1e12:.2f}T"
        if v >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"
    except Exception:
        return "—"


def fmt_pct(v, decimals: int = 2, sign: bool = True) -> str:
    if v is None: return "—"
    try:
        s = f"{float(v):+.{decimals}f}%" if sign else f"{float(v):.{decimals}f}%"
        return s
    except Exception:
        return "—"


# ── Verdict helpers ───────────────────────────────────────────
def verdict_tag(s: str) -> str:
    if not isinstance(s, str): return "—"
    su = s.upper()
    for kw in ("CORE HOLD", "BUY", "WATCHLIST", "HOLD", "WAIT"):
        if kw in su: return kw
    return s[:12]


def verdict_reason(s: str) -> str:
    if not isinstance(s, str): return ""
    parts = s.split(" - ", 1)
    return parts[1].strip() if len(parts) > 1 else s


def verdict_style(s: str) -> dict:
    tag = verdict_tag(s)
    return VERDICT.get(tag, {"color": "#475569", "bg": "#0D1219"})


# ── Upside calc ───────────────────────────────────────────────
def compute_upside(row: pd.Series, cur: float | None,
                   user_fv: float | None = None) -> tuple[float | None, float | None]:
    """Return (upside_pct, target_price).
    Method: TTM EPS × (1 + EPS_growth%) × Fwd_PE
    Gives a 12-month fair value assuming both earnings growth and
    multiple re-rating from TTM to forward multiple occur.
    User fair value always takes priority.
    """
    if cur is None or cur <= 0:
        return None, None
    if user_fv and user_fv > 0:
        return round((user_fv - cur) / cur * 100, 1), float(user_fv)
    try:
        pe  = float(row["PE (TTM)"])
        fpe = float(row["Fwd PE"])
        eg  = float(row["EPS Growth %"])
        if pe <= 0 or fpe <= 0: return None, None
        tgt = round((cur / pe) * (1 + eg / 100) * fpe, 2)
        return round((tgt - cur) / cur * 100, 1), tgt
    except Exception:
        return None, None


# ── 52-week position ─────────────────────────────────────────
def pct52(price, l52, h52) -> float | None:
    try:
        return (float(price) - float(l52)) / (float(h52) - float(l52)) * 100
    except Exception:
        return None


# ── Entry-zone parser ─────────────────────────────────────────
def parse_entry_zone(s: str) -> tuple[float | None, float | None]:
    if not s or not isinstance(s, str): return None, None
    nums = [float(n.replace(",", "")) for n in re.findall(r"[\d,]+(?:\.[\d]+)?", s)]
    # filter out PE multiples (usually < 100) only when we have stock prices (>50)
    prices = [n for n in nums if n > 50]
    if len(prices) >= 2: return prices[0], prices[1]
    if len(prices) == 1: return prices[0], prices[0]
    # fallback: first two numbers
    if len(nums) >= 2: return nums[0], nums[1]
    return None, None


# ── Zone status ───────────────────────────────────────────────
def zone_status(cur: float | None, zlo, zhi) -> str:
    """Returns 'below', 'in', 'above', or 'unknown'."""
    if cur is None or zlo is None: return "unknown"
    if cur < zlo:  return "below"
    if cur <= zhi: return "in"
    return "above"
