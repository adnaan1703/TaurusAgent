from __future__ import annotations

import streamlit as st

from apps.dashboard.data import latest_paper_account, list_backtest_equity, list_paper_positions
from apps.dashboard.ui import (
    configure_page,
    format_inr,
    load_data,
    metric_columns,
    render_equity_curve,
    render_table,
    sidebar_filters,
)


configure_page("Portfolio")
settings, symbol, _limit = sidebar_filters()
account, positions, equity = load_data(
    settings,
    lambda session: (
        latest_paper_account(session),
        list_paper_positions(session, symbol=symbol),
        list_backtest_equity(session),
    ),
    (None, [], []),
)

account = account or {}
metric_columns(
    [
        ("Equity", format_inr(account.get("equity_inr"))),
        ("Cash", format_inr(account.get("cash_inr"))),
        ("Exposure", format_inr(account.get("gross_exposure_inr"))),
        ("Unrealized P&L", format_inr(account.get("unrealized_pnl_inr"))),
    ]
)

st.subheader("Positions")
render_table(positions)

st.subheader("Backtest Equity Curve")
render_equity_curve(equity)
