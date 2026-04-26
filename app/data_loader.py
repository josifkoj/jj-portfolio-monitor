# app/data_loader.py  —  Excel sheets + JSON user-data persistence
import json
import streamlit as st
import pandas as pd
from app.config import EXCEL_PATH, USER_DATA


@st.cache_data(ttl=600, show_spinner=False)
def load_excel(path: str | None = None) -> dict[str, pd.DataFrame]:
    p = path or str(EXCEL_PATH)
    xl = pd.ExcelFile(p)
    return {sheet: pd.read_excel(p, sheet_name=sheet) for sheet in xl.sheet_names}


def load_user_data() -> dict:
    if USER_DATA.exists():
        try:
            with open(USER_DATA) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "entry_prices": {},   # tk -> {price, shares, target}
        "watchlist":    {},   # tk -> {target_price, note}
        "portfolio":    {},   # tk -> {shares, entry_price}
        "fair_values":  {},   # tk -> float
        "price_cache":  {},   # tk -> {price, change_pct, high52, low52, mktcap, ts}
    }


def save_user_data(data: dict) -> None:
    with open(USER_DATA, "w") as f:
        json.dump(data, f, indent=2, default=str)


def init_session() -> None:
    if "user_data" not in st.session_state:
        st.session_state.user_data = load_user_data()
    if "price_cache" not in st.session_state:
        st.session_state.price_cache = st.session_state.user_data.get("price_cache", {})
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"
    if "selected_stock" not in st.session_state:
        st.session_state.selected_stock = None
    if "_df_top10" not in st.session_state:
        st.session_state["_df_top10"] = pd.DataFrame()
