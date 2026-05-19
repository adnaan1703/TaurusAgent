from __future__ import annotations

import streamlit as st

from apps.dashboard.data import data_freshness, list_events, news_ingestion_summary
from apps.dashboard.ui import configure_page, load_data, render_table, sidebar_filters


configure_page("Events")
settings, symbol, limit = sidebar_filters()
events, freshness, ingestion = load_data(
    settings,
    lambda session: (
        list_events(session, symbol=symbol, limit=limit),
        data_freshness(session, symbol=symbol),
        news_ingestion_summary(session),
    ),
    ([], [], []),
)

tabs = st.tabs(["Events", "Freshness", "Ingestion"])
with tabs[0]:
    render_table(events)
with tabs[1]:
    render_table(freshness)
with tabs[2]:
    render_table(ingestion)
