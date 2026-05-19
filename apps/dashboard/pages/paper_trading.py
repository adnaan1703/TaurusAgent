from __future__ import annotations

import streamlit as st

from apps.dashboard.data import (
    latest_paper_account,
    list_final_decisions,
    list_paper_fills,
    list_paper_orders,
    list_paper_positions,
)
from apps.dashboard.ui import (
    configure_page,
    format_inr,
    load_data,
    metric_columns,
    render_table,
    sidebar_filters,
)


configure_page("Paper Trading")
settings, symbol, limit = sidebar_filters()
account, decisions, positions, orders, fills = load_data(
    settings,
    lambda session: (
        latest_paper_account(session),
        list_final_decisions(session, symbol=symbol, limit=limit),
        list_paper_positions(session, symbol=symbol),
        list_paper_orders(session, symbol=symbol, limit=limit),
        list_paper_fills(session, symbol=symbol, limit=limit),
    ),
    (None, [], [], [], []),
)

account = account or {}
metric_columns(
    [
        ("Equity", format_inr(account.get("equity_inr"))),
        ("Cash", format_inr(account.get("cash_inr"))),
        ("Exposure", format_inr(account.get("gross_exposure_inr"))),
        ("Realized P&L", format_inr(account.get("realized_pnl_inr"))),
    ]
)

tabs = st.tabs(["Decisions", "Positions", "Orders", "Fills"])
with tabs[0]:
    render_table(decisions)
with tabs[1]:
    render_table(positions)
with tabs[2]:
    render_table(orders)
with tabs[3]:
    render_table(fills)
