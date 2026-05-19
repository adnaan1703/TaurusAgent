# Taurus Milestone TODO

Source of truth:

- `docs/TAURUS_MVP_SPEC_v0_3.md`
- `docs/TAURUS_CODEX_TASKS_v0_3.yaml`

Last updated: 2026-05-19 13:50 IST

Status legend:

- `[x]` Done and verified
- `[ ]` Not started
- `[~]` In progress or partial
- `[!]` Blocked or needs user input

Milestone completion reporting:

- Every completed milestone task summary must explicitly list assumptions made, mocks created, and mocks used.
- If any category is empty, write `None` so omissions are visible.

## Summary

| Milestone | Status | Title | User input | External keys |
|---|---|---|---|---|
| M0 | Done | Project foundation | No | No |
| M1 | Done | Mock data and database foundation | No | No |
| M2 | Done | Backtesting skeleton | No | No |
| M3 | Done | Strategy engine and technical indicators | No | No |
| M4 | Done | Intelligence foundation and analyst reports | Optional | Optional |
| M5 | Done | Bull/Bear debate and trader proposal | No | Optional |
| M6 | Done | Risk committee and fund manager approval | No | No |
| M7 | Not started | PaperBroker execution simulator | No | No |
| M8 | Not started | Dashboard and observability v1 | No | No |
| M9 | Not started | Screener fundamentals import | Screener CSV required | No |
| M10 | Not started | Real market data provider | CSV/provider decision required | Maybe |
| M11 | Not started | Continuous paper trading | Schedule assumptions required | Maybe |
| M12 | Not started | Telegram alerts, replay, backup, hardening | Telegram details optional | Optional |
| M13 | Not started | Broker sandbox adapter | Sandbox details required | Yes |
| M14 | Not started | Live-readiness gate | Broker/compliance approval required | Yes |
| M15 | Not started | Taurus MVP release | Depends | Depends |

## M0 - Project Foundation

Status: Done

Objective: Repo scaffold, config, FastAPI health endpoints, Docker Compose, tests, and metrics endpoint.

Tasks:

- [x] Create repository structure from v0.3 spec.
- [x] Add `pyproject.toml`, `Makefile`, `.env.example`, `README.md`.
- [x] Add FastAPI app with `/health`, `/ready`, `/metrics`.
- [x] Add Docker Compose for Postgres, Redis, Prometheus, Grafana.
- [x] Add JSON logging and config loader.
- [x] Add pytest setup and health tests.
- [x] Ensure `LIVE_TRADING_ENABLED` defaults to false.
- [x] Add project-local Codex command approvals in `.codex/rules/default.rules`.
- [x] Add command reference in `docs/TAURUS_COMMANDS.md`.

Verification:

- [x] `make setup`
- [x] `make dev-up`
- [x] `make test`
- [x] `make lint`
- [x] `make api`
- [x] `curl http://localhost:8000/health`
- [x] `curl http://localhost:8000/ready`
- [x] `curl http://localhost:8000/metrics`
- [x] `make dev-down`

Acceptance:

- [x] Tests pass.
- [x] Health endpoints respond.
- [x] Metrics endpoint exists.
- [x] No API keys required.
- [x] No live trading code path enabled.

Notes:

- Verified `7 passed`.
- `/metrics` includes `taurus_live_trading_enabled 0.0`.
- Config rejects `LIVE_TRADING_ENABLED=true` and non-paper broker providers in M0.

## M1 - Mock Data And Database Foundation

Status: Done

Objective: Database schema, domain models, deterministic mock instruments and candles.

Tasks:

- [x] Add database models and repositories.
- [x] Add migrations.
- [x] Add deterministic mock market data provider.
- [x] Add `seed_mock_data` script.
- [x] Add data API endpoints.

Verification:

- [x] `make dev-up`
- [x] `make migrate`
- [x] `make seed-mock`
- [x] `make test`
- [x] `curl http://localhost:8000/data/instruments`

Acceptance:

- [x] At least 10 mock instruments exist.
- [x] At least 252 daily candles per instrument exist.
- [x] Mock data seeding is deterministic.
- [x] API returns instruments and candles.

## M2 - Backtesting Skeleton

Status: Done

Objective: First full mock backtest with metrics, orders, fills, positions, and reports.

Tasks:

- [x] Build event-driven backtest loop.
- [x] Implement mock momentum strategy.
- [x] Add cost and slippage model.
- [x] Store backtest run objects.
- [x] Compute total return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor.
- [x] Add `run_backtest` script.

Verification:

- [x] `make backtest-mock`
- [x] `make test`

Acceptance:

- [x] Backtest prints a `run_id`.
- [x] Metrics JSON is generated.
- [x] Equity curve is stored.
- [x] Signals, orders, fills, positions, and audit rows exist.
- [x] Re-running with the same seed gives the same output.

Notes:

- Verified `13 passed`.
- `make backtest-mock` prints `run_id=bt-819f036d1b8b16fe` and deterministic metrics JSON on repeat runs.
- M2 stores run-scoped signals, orders, fills, final positions, equity curve points, and two audit rows per run.

## M3 - Strategy Engine And Technical Indicators

Status: Done

Objective: Configurable technical strategies and feature store.

Tasks:

- [x] Implement SMA, EMA, RSI, ATR, returns, volatility, volume z-score.
- [x] Add moving average crossover strategy.
- [x] Add blended score strategy.
- [x] Add YAML strategy configs.
- [x] Store feature values with data availability timestamps.
- [x] Add signal explanations.

Verification:

- [x] `make test`
- [x] `make backtest-mock STRATEGY=configs/strategies/moving_average_crossover_v1.yaml`
- [x] `make backtest-mock STRATEGY=configs/strategies/blended_score_v1.yaml`

Acceptance:

- [x] Indicator tests pass on fixed data.
- [x] Strategies produce explained signals.
- [x] Feature store rows include `data_available_time`.
- [x] No look-ahead data is used.

Notes:

- Verified `17 passed`.
- `make lint` compile-checks pass.
- Moving-average config prints `run_id=bt-f1cb6aed6c20e80d`.
- Blended-score config prints `run_id=bt-68193c3c171f2206`.
- Feature snapshots are persisted in `feature_values`; signal rows include `feature_snapshot_id` and JSON explanations.

## M4 - Intelligence Foundation And Analyst Reports

Status: Done

Objective: Add news/sentiment/LLM foundation plus TradingAgents-style analyst agents.

User inputs:

- Optional sample news/events CSV or JSON.
- Optional LM Studio model name if testing local LLM.
- Optional OpenAI API key if testing OpenAI provider.
- Optional allowed source list for real news later.

Tasks:

- [x] Build `DocumentProvider` and `NewsProvider` interfaces.
- [x] Add `MockNewsProvider`.
- [x] Add `raw_documents`, `company_events`, `sentiment_scores`, `analyst_reports` tables.
- [x] Add ticker/entity resolver.
- [x] Add deterministic rule-based fallback sentiment scoring.
- [x] Add `LLMProvider` interface with mock, LM Studio, and OpenAI providers.
- [x] Add Pydantic schemas for LLM output.
- [x] Implement `TechnicalAnalystAgent`.
- [x] Implement `NewsAnalystAgent`.
- [x] Implement `SentimentAnalystAgent`.
- [x] Implement `FundamentalsAnalystAgent` with mock fundamentals initially.
- [x] Add time-decayed event features.
- [x] Add event and agent-report API endpoints.

Verification:

- [x] `make import-mock-news`
- [x] `make run-analysts-mock SYMBOL=INFY`
- [x] `make test`
- [x] `curl http://localhost:8000/events`
- [x] `curl http://localhost:8000/agent-reports?symbol=INFY`
- [ ] Optional: `TAURUS_LLM_PROVIDER=lmstudio TAURUS_LLM_BASE_URL=http://localhost:1234/v1 make llm-smoke`

Acceptance:

- [x] Mock news imports successfully.
- [x] Events map to symbols.
- [x] Sentiment/event scores are stored.
- [x] Analyst reports are stored for at least one symbol.
- [x] LLM output is schema-validated.
- [x] LLM failures do not crash the pipeline.
- [x] Analyst agents cannot create or approve orders.

## M5 - Bull/Bear Debate And Trader Proposal

Status: Done

Objective: Implement bull/bear researcher debate, research manager summary, and structured trader proposal.

Tasks:

- [x] Implement `BullResearcherAgent`.
- [x] Implement `BearResearcherAgent`.
- [x] Implement `ResearchManagerAgent`.
- [x] Implement `ResearchDebateService` with configurable debate rounds.
- [x] Implement `TraderAgent`.
- [x] Add `debate_reports` and `trader_proposals` tables.
- [x] Ensure trader proposal is not an order.
- [x] Add API endpoints for debates and proposals.
- [x] Add deterministic mock-mode tests.

Verification:

- [x] `make run-analysts-mock SYMBOL=INFY`
- [x] `make debate-mock SYMBOL=INFY`
- [x] `make trader-proposal-mock SYMBOL=INFY`
- [x] `make test`
- [x] `curl http://localhost:8000/debates`
- [x] `curl http://localhost:8000/trader-proposals`

Acceptance:

- [x] Bull thesis and bear thesis are produced.
- [x] Research manager summary is produced.
- [x] Trader proposal contains action, confidence, horizon, requested position, stop-loss, take-profit, invalidation rules.
- [x] Proposal references analyst report IDs and debate ID.
- [x] No broker order is created.
- [x] Mock mode is deterministic.

Notes:

- Verified `29 passed`.
- `make lint` compile-checks pass.
- `make debate-mock SYMBOL=INFY` produced `debate_id=deb-6bade5af5d85ba29` with a mild-bullish manager summary.
- `make trader-proposal-mock SYMBOL=INFY` produced `proposal_id=tp-14db74d8e66bf4da`, `action=BUY`, `is_order=false`, and `requires_risk_approval=true`.
- `/debates` and `/trader-proposals` returned the persisted M5 records.
- Local Postgres was initially down; `make dev-up` was run before command verification.

## M6 - Risk Committee And Fund Manager Approval

Status: Done

Objective: Add risk personas, deterministic hard risk checks, audit trail, and final approval gate.

Tasks:

- [x] Implement `RiskyRiskAgent`.
- [x] Implement `NeutralRiskAgent`.
- [x] Implement `SafeRiskAgent`.
- [x] Implement deterministic `RiskEngine` with hard rules.
- [x] Add event-risk block for severe negative events.
- [x] Implement `PortfolioManagerAgent`.
- [x] Add `risk_reviews` and `final_decisions` tables.
- [x] Ensure no order can bypass final approval.

Verification:

- [x] `make risk-review-mock SYMBOL=INFY`
- [x] `make final-approval-mock SYMBOL=INFY`
- [x] `make test`

Acceptance:

- [x] Risk committee review exists.
- [x] Hard risk rule results are stored.
- [x] Oversized positions are reduced or rejected.
- [x] Kill switch blocks orders.
- [x] Severe negative event can block a long entry.
- [x] Final paper decision is stored.
- [x] No order can bypass final approval.

Notes:

- Verified `34 passed`.
- `make lint` compile-checks pass.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m6.db make risk-review-mock SYMBOL=INFY` produced `risk_check_id=risk-f9403029962b48e1`, `status=APPROVED`, hard-rule results for live-trading guard, kill switch, supported instrument, trace IDs, position cap, open-position cap, daily loss, stale data, severe event block, and long-entry action.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m6.db make final-approval-mock SYMBOL=INFY` produced `final_decision_id=fd-fa072518d2f6941a`, `status=APPROVED_FOR_PAPER`, `final_action=BUY`, `approved_quantity=85`, and `is_order=false`.

Completion summary:

- Assumptions made: `run_id` remains the existing workflow trace ID; M6 adds a derived `decision_id` to risk/final artifacts without changing the M5 trader proposal table. Mock-mode freshness allows deterministic historical fixtures inside a bounded freshness window.
- Mocks created: Unit-test severe negative regulatory event fixture for validating long-entry event blocking.
- Mocks used: Deterministic mock market data, mock news, mock LLM analyst outputs, mock debate/trader proposal pipeline, and SQLite verification database at `/private/tmp/taurus-m6.db`.

## M7 - PaperBroker Execution Simulator

Status: Not started

Objective: Simulated orders, fills, positions, cash, slippage, and costs.

Tasks:

- [ ] Define `BrokerAdapter` interface.
- [ ] Implement `PaperBroker`.
- [ ] Add order lifecycle states.
- [ ] Add partial fills, slippage, costs.
- [ ] Add paper-once and paper-loop scripts.
- [ ] Accept only final approved decisions.

Verification:

- [ ] `make paper-once-mock SYMBOL=INFY`
- [ ] `make test`

Acceptance:

- [ ] PaperBroker receives only final approved paper decisions.
- [ ] Cash and positions update correctly.
- [ ] Costs and slippage are stored.
- [ ] Paper run is deterministic from same seed.
- [ ] Event-risk blocks apply in paper mode.

## M8 - Dashboard And Observability V1

Status: Not started

Objective: Streamlit trading dashboard, agent workflow dashboard, news/events dashboard, and Grafana system metrics.

Tasks:

- [ ] Build Streamlit dashboard pages.
- [ ] Add Prometheus metrics.
- [ ] Add Grafana dashboards.
- [ ] Add JSON logs with `run_id`, `decision_id`, `order_id`, `document_id`, `debate_id`.
- [ ] Add data freshness metrics.
- [ ] Add LLM/news ingestion metrics.
- [ ] Add analyst report, bull/bear debate, trader proposal, risk review, and final decision panels.

Verification:

- [ ] `make dev-up`
- [ ] `make dashboard`
- [ ] `make backtest-mock`
- [ ] `make paper-once-mock SYMBOL=INFY`

Acceptance:

- [ ] Dashboard shows portfolio and equity curve.
- [ ] Dashboard shows analyst reports.
- [ ] Dashboard shows bull vs bear debate.
- [ ] Dashboard shows trader proposal.
- [ ] Dashboard shows risk review and hard rule results.
- [ ] Dashboard shows orders and fills.
- [ ] Grafana shows service health metrics.

## M9 - Screener Fundamentals Import

Status: Not started

Objective: Import user-provided Screener CSV and upgrade fundamentals analyst.

User input required:

- [!] Screener CSV export must be explicitly requested from user at start of this milestone.

Tasks:

- [ ] Add CSV import command.
- [ ] Validate required/optional columns.
- [ ] Map symbols/company names to instruments.
- [ ] Store fundamental snapshots with `data_available_time`.
- [ ] Add quality/valuation score.
- [ ] Upgrade `FundamentalsAnalystAgent` to read imported data.

Verification:

- [ ] `make import-screener CSV=/path/to/screener.csv`
- [ ] `make run-analysts-mock SYMBOL=INFY`
- [ ] `make test`

Acceptance:

- [ ] Screener CSV imports without committing file.
- [ ] Missing columns are reported clearly.
- [ ] Fundamentals map to instruments.
- [ ] Fundamental score is stored.
- [ ] Fundamentals analyst uses imported data.

## M10 - Real Market Data Provider

Status: Not started

Objective: Add CSV/vendor/broker market data provider interface.

User input required:

- [!] CSV historical prices or selected data provider details.

Tasks:

- [ ] Add `MarketDataProvider` interface.
- [ ] Add `CSVMarketDataProvider`.
- [ ] Add optional real provider stub.
- [ ] Record source and `data_available_time`.

Verification:

- [ ] `make import-prices CSV=/path/to/prices.csv`
- [ ] `make backtest-real-data`
- [ ] `make test`

Acceptance:

- [ ] Mock provider still works.
- [ ] CSV provider works.
- [ ] Real provider disabled without credentials.
- [ ] Data source and availability timestamps are stored.

## M11 - Continuous Paper Trading

Status: Not started

Objective: Scheduled paper loop using latest available data.

User input required:

- [!] Paper trading schedule.
- [!] Market hours assumptions.
- [!] Confirmation to run after market close initially.

Tasks:

- [ ] Add scheduler.
- [ ] Add end-of-day paper run pipeline.
- [ ] Add run status tracking.
- [ ] Add failure recovery.

Verification:

- [ ] `make paper-loop-mock`
- [ ] `make test`

Acceptance:

- [ ] Scheduled loop executes data update, features, analysts, debate, trader, risk, final approval, PaperBroker.
- [ ] Each run has `run_id`.
- [ ] Dashboard updates.
- [ ] Failures are logged.

## M12 - Telegram Alerts, Replay, Backup, Hardening

Status: Not started

Objective: Alerts, replay, backups, and runbook.

User input optional:

- [ ] `TELEGRAM_BOT_TOKEN`
- [ ] `TELEGRAM_CHAT_ID`

Tasks:

- [ ] Add Telegram alert adapter.
- [ ] Add alert smoke command.
- [ ] Add decision replay by `decision_id`.
- [ ] Add backup and restore scripts.
- [ ] Add operations runbook.

Verification:

- [ ] `make alert-smoke`
- [ ] `make replay-decision DECISION_ID=sample`
- [ ] `make backup-db`
- [ ] `make test`

Acceptance:

- [ ] Telegram smoke test works when credentials are provided.
- [ ] Alerts fire for fills, kill switch, severe events, stale data, job failures.
- [ ] Decision replay works.
- [ ] Backup and restore commands exist.

## M13 - Broker Sandbox Adapter

Status: Not started

Objective: Upstox Sandbox/OpenAlgo smoke test without live trading.

User input required:

- [!] `UPSTOX_CLIENT_ID`
- [!] `UPSTOX_CLIENT_SECRET`
- [!] `UPSTOX_REDIRECT_URI`
- [!] Sandbox account setup details.

Tasks:

- [ ] Add sandbox broker adapter.
- [ ] Add credentials loading from env only.
- [ ] Add sandbox smoke test.
- [ ] Keep PaperBroker default.

Verification:

- [ ] `make broker-sandbox-smoke`
- [ ] `make test`

Acceptance:

- [ ] Sandbox adapter conforms to `BrokerAdapter`.
- [ ] Credentials are not committed.
- [ ] Sandbox smoke test passes where supported.
- [ ] Live trading remains disabled.

## M14 - Live-Readiness Gate

Status: Not started

Objective: Safety and compliance gate only; no live orders.

User input required:

- [!] Broker/compliance details.
- [!] Manual release approval.

Tasks:

- [ ] Add live preflight check.
- [ ] Add explicit manual sign-off requirement.
- [ ] Add order tagging placeholders.
- [ ] Add compliance checklist.

Verification:

- [ ] `make live-preflight-check`
- [ ] `make test`

Acceptance:

- [ ] `LIVE_TRADING_ENABLED=false` remains default.
- [ ] Live mode requires explicit config and preflight pass.
- [ ] Manual sign-off is required.
- [ ] No live orders are placed.

## M15 - Taurus MVP Release

Status: Not started

Objective: End-to-end observable paper-trading MVP.

Verification:

- [ ] `make setup`
- [ ] `make dev-up`
- [ ] `make migrate`
- [ ] `make seed-mock`
- [ ] `make import-mock-news`
- [ ] `make backtest-mock`
- [ ] `make run-analysts-mock SYMBOL=INFY`
- [ ] `make debate-mock SYMBOL=INFY`
- [ ] `make trader-proposal-mock SYMBOL=INFY`
- [ ] `make risk-review-mock SYMBOL=INFY`
- [ ] `make final-approval-mock SYMBOL=INFY`
- [ ] `make paper-once-mock SYMBOL=INFY`
- [ ] `make dashboard`
- [ ] `make test`

Acceptance:

- [ ] Taurus runs end-to-end with mock data.
- [ ] Taurus can backtest.
- [ ] Taurus generates analyst reports.
- [ ] Taurus runs bull/bear debate.
- [ ] Taurus generates trader proposal.
- [ ] Taurus runs risk review and final approval.
- [ ] Taurus paper trades only.
- [ ] Dashboard shows performance, decisions, debate, risk, orders, events, and health.
- [ ] Live trading is disabled.

## Maintenance Rules

Update this file whenever a milestone task starts, completes, or is intentionally deferred.

For each completed milestone, record:

- status changes
- verification commands run
- test results
- user inputs provided or skipped
- safety notes, especially live-trading guardrails

Do not mark a milestone complete unless its acceptance criteria pass.
