# Taurus Milestone TODO

This file is the current project tracker for future agent work. Historical
milestone implementation prompts and completed implementation plans were removed
from active docs to avoid stale context.

Last updated: 2026-05-28

## Active Source Of Truth

- `README.md`: project overview, setup, and primary workflow.
- `docs/TAURUS_USAGE_GUIDE.md`: current operating guide and known gaps.
- `docs/TAURUS_COMMANDS.md`: command reference and project-local approval notes.
- `docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md`: repo-specific M20 graph intelligence plan.
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

## Planned Graph Intelligence Milestones

`docs/TAURUS_DATA_INTEGRATION.md` is outside-source reference material only.
Use `docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md` and this tracker as the active
implementation source for M20 work.

Treat M20 submilestones exactly like main milestones. After one M20 submilestone
is complete, verified, cleaned up, and documented with its completion summary,
stop and report what was achieved. Do not automatically begin the next M20
submilestone unless the user explicitly asks to proceed.

| Milestone | Status | Current Result |
|---|---|---|
| M20.0 | Done | Created repo-specific graph intelligence plan and M20 milestone tracker; no runtime behavior changes. |
| M20.1 | Done | Postgres graph settings, graph tables, metadata migration path, and idempotent graph repository upserts/read paths. |
| M20.2 | Done | TaurusData CSV graph importer, CLI/Make target, idempotent active/candidate/evidence import from `configs/taurus_data/`. |
| M20.3 | Done | FastAPI graph API vertical slice backed by Postgres, with local-dashboard edge review endpoints. |
| M20.4 | Done | React graph dashboard routes for overview, company graph, candidate review, and graph signals. |
| M20.5 | Done | Optional Neo4j projection/read model, disabled by default and rebuildable from Postgres. |
| M20.6 | Done | Graph statistical validation engine persisted to Postgres edge stats. |
| M20.7 | Done | Deterministic `GraphAnalystAgent` registered behind the optional `graph` analyst key, with persisted graph signals and contributions. |
| M20.8 | Planned | Optional graph-aware risk checks. |
| M20.9 | Planned | Graph observability metrics and dashboards. |
| M20.10 | Planned | Graph-aware backtesting with look-ahead prevention. |

## Current Capabilities

- Deterministic mock-data paper workflow.
- CSV-backed market data import.
- Kite-backed historical daily candle import and latest quote snapshot persistence.
- Technical analyst default flow.
- Optional mock/LM Studio/OpenAI LLM providers.
- Bull/bear debate, trader proposal, risk review, and final approval.
- Internal simulated paper execution through `PaperBroker`.
- React dashboard at `http://localhost:5173`, including graph browsing and gated graph edge review.
- Streamlit fallback dashboard.
- Optional disposable Neo4j projection read model rebuilt one-way from Postgres graph tables.
- Graph edge statistical validation from daily candle data with persisted raw
  correlation, market-residual correlation, lead-lag score, stability score,
  sample size, and insufficient-data reasons.
- Optional deterministic `GraphAnalystAgent`, disabled by default and enabled
  only through `TAURUS_ENABLED_ANALYSTS=...,graph`, stores graph signals and
  per-edge contributions without bypassing the debate/risk/final approval path.
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
- [ ] Start M20.8 only after a fresh explicit request.

## Latest Completion Summary - M20.7

- Assumptions made: The graph analyst scores active and candidate company-to-company
  graph edges only when the edge has sufficient persisted edge stats and the
  related company has daily candles for 20-day momentum; directed edges influence
  only their target company; `positive` and `negative` expected signs define
  same-direction and inverse related-momentum effects, while mixed or unknown
  signs fall back to the latest stat correlation; neutral graph signals are
  still stored when no validated graph evidence exists; the graph analyst does
  not call the LLM provider, so graph scores and contributions remain
  deterministic.
- Mocks created: Synthetic `AAA` and `BBB` graph fixtures in
  `tests/unit/test_graph_analyst.py` for bullish peer momentum and bearish
  negative dependency cases; constant-return synthetic daily candles for related
  momentum; a `FailingLLMProvider` test double proving graph output is not
  overridden by LLM failure.
- Mocks used: `MockLLMProvider` for analyst workflow tests; deterministic mock
  market data, mock news, mock alerts, and the internal `PaperBroker` simulator
  through existing paper-run and smoke tests; no live broker, Kite, Neo4j, or
  external data service was required.
- Verification: `uv run pytest tests/unit/test_config.py tests/unit/test_graph_analyst.py tests/unit/test_analyst_agents.py`
  passed (21 passed); paper/dashboard/replay smoke-focused suite
  `uv run pytest tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py tests/unit/test_dashboard_observability.py tests/unit/test_alerts_replay_backup.py tests/unit/test_taurus_smoke.py`
  passed (20 passed); graph-focused suite
  `uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py tests/unit/test_graph_stats.py tests/unit/test_graph_analyst.py tests/unit/test_config.py`
  passed (29 passed, 1 skipped); `make test` passed (117 passed, 1 skipped);
  `make lint` passed; milestone cleanup inspected
  `/Users/adnaan/.codex/rules/default.rules` and found no accidental Taurus
  approvals after the user's marker, so no global-rule cleanup or project-local
  approval changes were required.

## Deprecated Direction

Previous broker sandbox and production-readiness plans have been removed. Taurus
does not currently track broker order routing as a planned milestone.

## Maintenance Rules

- Update this file when a new milestone starts, completes, or is intentionally deferred.
- Keep this tracker concise; avoid pasting full implementation prompts.
- Put detailed user-facing operation steps in `docs/TAURUS_USAGE_GUIDE.md`.
- Put command history or approval notes in `docs/TAURUS_COMMANDS.md`.
- Keep future UI visual references under `docs/stitch/paper-trade-event-monitor/`.
