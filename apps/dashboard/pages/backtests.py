from __future__ import annotations

import streamlit as st

from apps.dashboard.data import list_backtest_equity, list_backtest_runs
from apps.dashboard.ui import configure_page, load_data, render_equity_curve, render_table, sidebar_filters


configure_page("Backtests")
settings, _symbol, limit = sidebar_filters()
runs, equity = load_data(
    settings,
    lambda session: (
        list_backtest_runs(session, limit=limit),
        list_backtest_equity(session),
    ),
    ([], []),
)

st.subheader("Runs")
render_table(runs)

st.subheader("Latest Equity Curve")
render_equity_curve(equity)
