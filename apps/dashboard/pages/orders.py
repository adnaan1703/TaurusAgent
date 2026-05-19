from __future__ import annotations

import streamlit as st

from apps.dashboard.data import list_paper_fills, list_paper_orders
from apps.dashboard.ui import configure_page, load_data, render_table, sidebar_filters


configure_page("Orders")
settings, symbol, limit = sidebar_filters()
orders, fills = load_data(
    settings,
    lambda session: (
        list_paper_orders(session, symbol=symbol, limit=limit),
        list_paper_fills(session, symbol=symbol, limit=limit),
    ),
    ([], []),
)

tabs = st.tabs(["Orders", "Fills"])
with tabs[0]:
    render_table(orders)
with tabs[1]:
    render_table(fills)
