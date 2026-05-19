from __future__ import annotations

import streamlit as st

from apps.dashboard.data import list_analyst_reports, list_debates, list_trader_proposals
from apps.dashboard.ui import configure_page, load_data, render_table, sidebar_filters


configure_page("Agent Workflow")
settings, symbol, limit = sidebar_filters()
reports, debates, proposals = load_data(
    settings,
    lambda session: (
        list_analyst_reports(session, symbol=symbol, limit=limit),
        list_debates(session, symbol=symbol, limit=limit),
        list_trader_proposals(session, symbol=symbol, limit=limit),
    ),
    ([], [], []),
)

tabs = st.tabs(["Analyst Reports", "Bull Bear Debate", "Trader Proposals"])
with tabs[0]:
    render_table(reports)
with tabs[1]:
    render_table(debates)
with tabs[2]:
    render_table(proposals)
