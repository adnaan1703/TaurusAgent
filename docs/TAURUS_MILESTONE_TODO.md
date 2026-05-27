# Taurus Milestone TODO

This file is the current project tracker for future agent work. Historical
milestone implementation prompts and completed implementation plans were removed
from active docs to avoid stale context.

Last updated: 2026-05-27

## Active Source Of Truth

- `README.md`: project overview, setup, and primary workflow.
- `docs/TAURUS_USAGE_GUIDE.md`: current operating guide and known gaps.
- `docs/TAURUS_COMMANDS.md`: command reference and project-local approval notes.
- `docs/stitch/paper-trade-event-monitor/`: preserved UI reference assets for future dashboard work.

## Safety Rules

- Taurus remains paper-trading-first.
- `LIVE_TRADING_ENABLED=false` must remain the default.
- `BROKER_PROVIDER=paper` must remain the default.
- Kite support is data-only; execution still routes through `PaperBroker`.
- Do not add real broker order routing without a new explicit approved milestone.
- Do not commit API keys, broker credentials, Telegram tokens, Kite tokens, or user CSV exports.

## Completion Reporting

Every completed milestone task summary must explicitly list:

- Assumptions made
- Mocks created
- Mocks used

If any category is empty, write `None`.

At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules`.
Entries after the user's `# END MY CUSTOM ADDITION` marker are accidental global
approvals. Move Taurus-specific approved prefixes into `.codex/rules/default.rules`
if missing, document them in `docs/TAURUS_COMMANDS.md`, and remove them from the
global file. Do not copy unrelated global approvals.

## Completed Milestones

| Milestone | Status | Current Result |
|---|---|---|
| M0 | Done | Project scaffold, FastAPI health/readiness/metrics, config, logging, tests, Docker Compose. |
| M1 | Done | Database foundation, deterministic mock instruments/candles, data APIs. |
| M2 | Done | Backtesting skeleton with metrics, orders, fills, positions, and reports. |
| M3 | Done | Technical indicators, feature store, and configurable strategies. |
| M4 | Done | News/sentiment/LLM foundation and analyst reports. |
| M5 | Done | Bull/bear debate, research manager summary, and trader proposal. |
| M6 | Done | Risk committee, deterministic risk engine, and final approval. |
| M7 | Done | Internal `PaperBroker` simulator with orders, fills, account, and positions. |
| M8 | Done | Streamlit/Grafana observability v1. Streamlit remains fallback only. |
| M9 | Done | Screener fundamentals import path and scoring. |
| M10 | Done | Market data provider abstraction and CSV import path. |
| M11 | Done | Continuous local paper loop. |
| M12 | Done | Alerts, replay, backup/restore, and hardening. |
| M13 | Done | Paper-trading MVP release. |
| M16 | Done | React run-loop observability dashboard, now primary local UI. |
| M17 | Done | Zerodha Kite market data provider, data-only. |
| M18 | Done | HalalStock compliance sync and halal NSE universe export. |
| M19 | Done | Shariah dashboard and paper-run universe provenance. |

## Current Capabilities

- Deterministic mock-data paper workflow.
- CSV-backed market data import.
- Kite-backed historical daily candle import and latest quote snapshot persistence.
- Technical analyst default flow.
- Optional mock/LM Studio/OpenAI LLM providers.
- Bull/bear debate, trader proposal, risk review, and final approval.
- Internal simulated paper execution through `PaperBroker`.
- Read-only React dashboard at `http://localhost:5173`.
- Streamlit fallback dashboard.
- Shariah compliance dashboard backed by imported HalalStock rows.
- Replay, backup/restore, alerts, Prometheus metrics, and Grafana dashboards.

## Active Follow-Ups

- [ ] Validate a real Screener CSV export when available.
- [ ] Confirm imported Screener rows map cleanly to Taurus instruments.
- [ ] Decide whether fundamentals scoring needs adjustment for the real Screener export format.
- [ ] Remove mock-news contamination from real-data paper runs, or add an explicit no-news mode.
- [ ] Add a rule-only technical analyst path that avoids mock LLM usage when desired.
- [ ] Add true portfolio continuity across paper runs.
- [ ] Avoid mixed mock/Kite data in the same database, or make provider-scoped universe handling explicit.
- [ ] Make Kite-backed backtesting first-class.
- [ ] Replace placeholder paper cost/slippage/fill assumptions with broker-calibrated assumptions.
- [ ] Add a real news/data provider if news or sentiment risk is enabled.
- [ ] Add dashboard/API auth before using Taurus beyond a trusted local machine.
- [ ] Verify real Telegram alert delivery with local-only credentials.

## Deprecated Direction

Previous broker sandbox and production-readiness plans have been removed. Taurus
does not currently track broker order routing as a planned milestone.

## Maintenance Rules

- Update this file when a new milestone starts, completes, or is intentionally deferred.
- Keep this tracker concise; avoid pasting full implementation prompts.
- Put detailed user-facing operation steps in `docs/TAURUS_USAGE_GUIDE.md`.
- Put command history or approval notes in `docs/TAURUS_COMMANDS.md`.
- Keep future UI visual references under `docs/stitch/paper-trade-event-monitor/`.
