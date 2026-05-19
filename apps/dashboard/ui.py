from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import pandas as pd
import streamlit as st

from apps.dashboard.data import DashboardDataError, list_symbols, read_dashboard_data
from taurus_core.config import Settings, get_settings

T = TypeVar("T")


def configure_page(title: str) -> None:
    st.set_page_config(page_title=f"Taurus | {title}", layout="wide")
    st.title(title)


@st.cache_resource
def dashboard_settings() -> Settings:
    return get_settings()


def sidebar_filters() -> tuple[Settings, str | None, int]:
    settings = dashboard_settings()
    st.sidebar.header("Filters")
    symbols = load_data(settings, lambda session: list_symbols(session), [])
    symbol_options = ["All", *symbols]
    selected = st.sidebar.selectbox("Symbol", symbol_options, index=0)
    limit = st.sidebar.slider("Rows", min_value=10, max_value=500, value=100, step=10)
    return settings, None if selected == "All" else selected, limit


def load_data(settings: Settings, reader: Callable[[Any], T], fallback: T) -> T:
    try:
        return read_dashboard_data(settings, reader)
    except DashboardDataError as exc:
        st.error(f"Dashboard data unavailable: {exc}")
        return fallback


def render_table(rows: list[dict[str, Any]], *, empty_label: str = "No records yet.") -> None:
    if not rows:
        st.info(empty_label)
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_equity_curve(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("No equity curve yet.")
        return
    frame = pd.DataFrame(rows)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    st.line_chart(frame.set_index("trade_date")[["total_equity_inr"]], height=320)


def format_inr(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"INR {float(value):,.2f}"


def metric_columns(metrics: list[tuple[str, str]]) -> None:
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics, strict=True):
        column.metric(label, value)
