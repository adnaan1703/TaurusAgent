from __future__ import annotations

import streamlit as st

from apps.dashboard.data import list_final_decisions, list_hard_rule_results, list_risk_reviews
from apps.dashboard.ui import configure_page, load_data, render_table, sidebar_filters


configure_page("Risk")
settings, symbol, limit = sidebar_filters()
reviews, hard_rules, decisions = load_data(
    settings,
    lambda session: (
        list_risk_reviews(session, symbol=symbol, limit=limit),
        list_hard_rule_results(session, symbol=symbol, limit=limit),
        list_final_decisions(session, symbol=symbol, limit=limit),
    ),
    ([], [], []),
)

tabs = st.tabs(["Reviews", "Hard Rules", "Final Decisions"])
with tabs[0]:
    render_table(reviews)
with tabs[1]:
    render_table(hard_rules)
with tabs[2]:
    render_table(decisions)
