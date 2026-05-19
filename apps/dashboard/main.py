from __future__ import annotations

import streamlit as st

from apps.dashboard.data import (
    list_analyst_reports,
    list_backtest_equity,
    list_debates,
    list_events,
    list_final_decisions,
    list_paper_fills,
    list_paper_orders,
    list_paper_positions,
    list_risk_reviews,
    list_trader_proposals,
    overview_snapshot,
)
from apps.dashboard.ui import (
    configure_page,
    format_inr,
    load_data,
    metric_columns,
    render_equity_curve,
    render_table,
    sidebar_filters,
)


def main() -> None:
    configure_page("Taurus Dashboard")
    settings, symbol, limit = sidebar_filters()
    snapshot = load_data(
        settings,
        lambda session: overview_snapshot(session, symbol=symbol),
        {
            "counts": {},
            "freshness": [],
            "latest_account": None,
            "latest_final_decision": None,
            "latest_order": None,
            "latest_backtest": None,
        },
    )

    account = snapshot["latest_account"] or {}
    decision = snapshot["latest_final_decision"] or {}
    order = snapshot["latest_order"] or {}
    backtest = snapshot["latest_backtest"] or {}
    metric_columns(
        [
            ("Paper Equity", format_inr(account.get("equity_inr"))),
            ("Paper Cash", format_inr(account.get("cash_inr"))),
            ("Final Status", str(decision.get("status", "-"))),
            ("Latest Order", str(order.get("status", "-"))),
            ("Backtest Return", _return_label(backtest.get("total_return_pct"))),
        ]
    )

    st.subheader("Portfolio")
    positions = load_data(
        settings,
        lambda session: list_paper_positions(session, symbol=symbol),
        [],
    )
    render_table(positions)

    st.subheader("Backtest Equity")
    equity = load_data(settings, lambda session: list_backtest_equity(session), [])
    render_equity_curve(equity)

    st.subheader("Agent Workflow")
    reports, debates, proposals = load_data(
        settings,
        lambda session: (
            list_analyst_reports(session, symbol=symbol, limit=limit),
            list_debates(session, symbol=symbol, limit=limit),
            list_trader_proposals(session, symbol=symbol, limit=limit),
        ),
        ([], [], []),
    )
    tabs = st.tabs(["Analysts", "Debate", "Proposal"])
    with tabs[0]:
        render_table(reports)
    with tabs[1]:
        render_table(debates)
    with tabs[2]:
        render_table(proposals)

    st.subheader("Risk And Execution")
    risk_reviews, final_decisions, orders, fills = load_data(
        settings,
        lambda session: (
            list_risk_reviews(session, symbol=symbol, limit=limit),
            list_final_decisions(session, symbol=symbol, limit=limit),
            list_paper_orders(session, symbol=symbol, limit=limit),
            list_paper_fills(session, symbol=symbol, limit=limit),
        ),
        ([], [], [], []),
    )
    tabs = st.tabs(["Risk", "Final", "Orders", "Fills"])
    with tabs[0]:
        render_table(risk_reviews)
    with tabs[1]:
        render_table(final_decisions)
    with tabs[2]:
        render_table(orders)
    with tabs[3]:
        render_table(fills)

    st.subheader("News And Freshness")
    events = load_data(settings, lambda session: list_events(session, symbol=symbol, limit=limit), [])
    tabs = st.tabs(["Events", "Freshness"])
    with tabs[0]:
        render_table(events)
    with tabs[1]:
        render_table(snapshot["freshness"])


def _return_label(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


if __name__ == "__main__":
    main()
