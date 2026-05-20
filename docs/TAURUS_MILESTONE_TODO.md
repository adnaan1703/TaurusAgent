# Taurus Milestone TODO

Source of truth:

- `docs/TAURUS_MVP_SPEC_v0_3.md`
- `docs/TAURUS_CODEX_TASKS_v0_3.yaml`

Last updated: 2026-05-20 17:13 IST

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
| M7 | Done | PaperBroker execution simulator | No | No |
| M8 | Done | Dashboard and observability v1 | No | No |
| M9 | Done | Screener fundamentals import | Screener CSV requested; fixture used | No |
| M10 | Done | Real market data provider | Synthetic CSV fixture approved | No |
| M11 | Done | Continuous paper trading | Default after-close schedule assumed | No |
| M12 | Done | Telegram alerts, replay, backup, hardening | Telegram details optional; mock used | Optional |
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

Status: Done

Objective: Simulated orders, fills, positions, cash, slippage, and costs.

Tasks:

- [x] Define `BrokerAdapter` interface.
- [x] Implement `PaperBroker`.
- [x] Add order lifecycle states.
- [x] Add partial fills, slippage, costs.
- [x] Add paper-once and paper-loop scripts.
- [x] Accept only final approved decisions.

Verification:

- [x] `make paper-once-mock SYMBOL=INFY`
- [x] `make test`
- [x] `make lint`
- [x] `curl http://127.0.0.1:8000/paper/orders`
- [x] `curl http://127.0.0.1:8000/paper/fills`
- [x] `curl http://127.0.0.1:8000/paper/positions`
- [x] `curl http://127.0.0.1:8000/paper/account`

Acceptance:

- [x] PaperBroker receives only final approved paper decisions.
- [x] Cash and positions update correctly.
- [x] Costs and slippage are stored.
- [x] Paper run is deterministic from same seed.
- [x] Event-risk blocks apply in paper mode.

Notes:

- Verified `38 passed`.
- `make lint` compile-checks pass.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m7-deterministic-20260519.db make paper-once-mock SYMBOL=INFY` produced `order_id=po-98310d7a4a1e6985`, `status=FILLED`, `filled_quantity=85`, two partial fills, `total_cost_inr=11.8703`, `total_slippage_inr=13.6357`, deterministic `as_of=2024-12-18T00:00:00Z`, and a paper account with `available_cash_inr=972700.3740`.
- `/paper/orders`, `/paper/fills`, `/paper/positions`, and `/paper/account` returned persisted paper execution state from the M7 verification database.

Completion summary:

- Assumptions made: PaperBroker fills approved paper decisions from the latest available daily candle, using the candle open for the first fill and close for the second partial fill. India cash-equity costs are simulation placeholders configurable with `TAURUS_PAPER_*` settings. The M7 paper loop is a finite mock loop; continuous scheduling remains M11 scope.
- Mocks created: Unit-test severe negative regulatory event fixture for validating paper-route blocking; forced low partial-fill threshold in M7 tests to exercise partial fills deterministically.
- Mocks used: Deterministic mock market data, mock news, mock LLM analyst outputs, mock debate/trader/risk/final-approval pipeline, and SQLite verification databases at `/private/tmp/taurus-m7-deterministic-20260519.db` and `/private/tmp/taurus-m7-verify-20260519.db`.

## M8 - Dashboard And Observability V1

Status: Done

Objective: Streamlit trading dashboard, agent workflow dashboard, news/events dashboard, and Grafana system metrics.

Tasks:

- [x] Build Streamlit dashboard pages.
- [x] Add Prometheus metrics.
- [x] Add Grafana dashboards.
- [x] Add JSON logs with `run_id`, `decision_id`, `order_id`, `document_id`, `debate_id`.
- [x] Add data freshness metrics.
- [x] Add LLM/news ingestion metrics.
- [x] Add analyst report, bull/bear debate, trader proposal, risk review, and final decision panels.

Verification:

- [x] `make dev-up`
- [x] `make dashboard`
- [x] `make backtest-mock`
- [x] `make paper-once-mock SYMBOL=INFY`

Acceptance:

- [x] Dashboard shows portfolio and equity curve.
- [x] Dashboard shows analyst reports.
- [x] Dashboard shows bull vs bear debate.
- [x] Dashboard shows trader proposal.
- [x] Dashboard shows risk review and hard rule results.
- [x] Dashboard shows orders and fills.
- [x] Grafana shows service health metrics.

Notes:

- Verified `40 passed`.
- `make lint` compile-checks pass.
- `make dev-up` starts API, Postgres, Redis, Prometheus, and Grafana with provisioned Prometheus datasource and Taurus system/trading dashboards.
- `make backtest-mock` produced `run_id=bt-f1cb6aed6c20e80d`.
- `make paper-once-mock SYMBOL=INFY` produced `order_id=po-60bb9f4e5644d8e2`, `status=FILLED`, two fills, and `final_decision_id=fd-ea9abfbddf6f35bd`.
- `/metrics` includes `taurus_observability_db_available 1.0`, `taurus_data_freshness_seconds`, `taurus_news_documents_total`, `taurus_agent_reports_total`, `taurus_trading_artifacts_total`, and `taurus_paper_account_equity_inr`.
- `make dashboard` starts non-interactively on `http://localhost:8501`; health endpoint returned `ok`.
- Grafana health returned database `ok` on `http://localhost:3000/api/health`.

Completion summary:

- Assumptions made: Streamlit reads the local Taurus database directly through `DATABASE_URL` instead of proxying through the API. Grafana uses a provisioned Prometheus datasource with UID `prometheus`. Data freshness for mock daily candles is measured from fixture trade dates, so mock freshness can appear old by wall-clock time.
- Mocks created: Temporary SQLite integration-test database for dashboard and observability assertions.
- Mocks used: Deterministic mock market data, mock news provider, mock LLM analyst outputs, mock debate/trader/risk/final-approval pipeline, internal PaperBroker, and Docker Compose Postgres verification database.

## M9 - Screener Fundamentals Import

Status: Done

Objective: Import user-provided Screener CSV and upgrade fundamentals analyst.

User input required:

- [x] Screener CSV export must be explicitly requested from user at start of this milestone.

Tasks:

- [x] Add CSV import command.
- [x] Validate required/optional columns.
- [x] Map symbols/company names to instruments.
- [x] Store fundamental snapshots with `data_available_time`.
- [x] Add quality/valuation score.
- [x] Upgrade `FundamentalsAnalystAgent` to read imported data.

Verification:

- [x] `make import-screener CSV=/path/to/screener.csv`
- [x] `make run-analysts-mock SYMBOL=INFY`
- [x] `make test`

Acceptance:

- [x] Screener CSV imports without committing file.
- [x] Missing columns are reported clearly.
- [x] Fundamentals map to instruments.
- [x] Fundamental score is stored.
- [x] Fundamentals analyst uses imported data.

Notes:

- Explicitly requested a real Screener CSV export at M9 start; no real CSV path was provided during this pass, so verification used `tests/fixtures/screener_sample.csv`.
- Added `make import-screener CSV=...`, `GET /fundamentals?symbol=INFY`, and `GET /fundamentals/imports`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m9-verify-20260519.db make import-screener CSV=tests/fixtures/screener_sample.csv` produced `import_id=fi-7b0fbaead039b3df`, `rows_seen=4`, `rows_imported=3`, `rows_unmapped=1`, `metrics_imported=45`, and `scores_imported=3`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m9-verify-20260519.db make run-analysts-mock SYMBOL=INFY` produced a `FundamentalsAnalystAgent` report using `fundamental_score:fs-1ce392dffce9d25c` with `score=0.3667`.
- `curl "http://localhost:8000/fundamentals?symbol=INFY"` returned the imported INFY metrics and composite score.
- `curl http://localhost:8000/fundamentals/imports` returned the import summary.
- Verified `44 passed`.
- `make lint` compile-checks pass.
- Global Codex approvals added during verification were copied into `.codex/rules/default.rules`, documented in `docs/TAURUS_COMMANDS.md`, and removed from `/Users/adnaan/.codex/rules/default.rules` after the user's marker.

Completion summary:

- Assumptions made: Screener CSV imports map only to existing active Taurus instruments; unmatched CSV rows are reported as unmapped rather than creating instruments. Scoring is deterministic and uses partial data when available. No real user Screener CSV path was provided, so real-data verification remains pending.
- Mocks created: Synthetic Screener fixture at `tests/fixtures/screener_sample.csv` and unit-test bad CSV inputs for validation errors.
- Mocks used: Synthetic Screener fixture, deterministic mock market data, mock LLM analyst provider, mock news pipeline during analyst verification, and SQLite verification database at `/private/tmp/taurus-m9-verify-20260519.db`.

## M10 - Real Market Data Provider

Status: Done

Objective: Add CSV/vendor/broker market data provider interface.

User input required:

- [x] Synthetic historical price CSV approved for implementation and automated verification.

Tasks:

- [x] Add `MarketDataProvider` interface.
- [x] Add `CSVMarketDataProvider`.
- [x] Add optional real provider stub.
- [x] Record source and `data_available_time`.

Verification:

- [x] `make import-price-csv CSV=/path/to/prices.csv`
- [x] `make backtest-real-data`
- [x] `make test`
- [x] `make lint`
- [x] `make backtest-mock`
- [x] `curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"`

Acceptance:

- [x] Mock provider still works.
- [x] CSV provider works.
- [x] Real provider disabled without credentials.
- [x] Data source and availability timestamps are stored.

Notes:

- Added synthetic OHLCV fixture at `mock/market_data/prices_sample.csv` with INFY, RELIANCE, and TCS daily candles.
- Added `CSVMarketDataProvider`, provider metadata, `get_historical_candles`, `get_latest_candle`, and disabled external provider stub.
- Added `make import-price-csv` and `make backtest-real-data`, with CSV smoke strategy `configs/strategies/csv_market_data_smoke_v1.yaml`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make import-price-csv` imported `36` candles for `3` instruments, dates `2024-01-01..2024-01-16`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make backtest-real-data` produced `run_id=bt-2b3c3ce4675784dc`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m10-mock-verify-20260519.db make backtest-mock` produced `run_id=bt-f1cb6aed6c20e80d`.
- `/data/candles?symbol=INFY&timeframe=1d` returns candle `source` as `csv_market_data:prices_sample.csv` and `data_available_time` values.
- Verified `49 passed`.
- `make lint` compile-checks pass.
- No external market data provider was previously selected in the committed docs. M10 keeps external provider integration disabled without credentials; broker/data-provider sandbox credentials remain later milestone scope.
- Global Codex approvals added during verification were copied into `.codex/rules/default.rules`, documented in `docs/TAURUS_COMMANDS.md`, and removed from `/Users/adnaan/.codex/rules/default.rules` after the user's marker.

Completion summary:

- Assumptions made: The synthetic CSV is acceptable for M10 implementation and automated verification. CSV candle provenance should record provider plus file name instead of full local user paths. External market data remains a disabled stub until a provider is selected and credentials are explicitly provided.
- Mocks created: Synthetic OHLCV price CSV at `mock/market_data/prices_sample.csv` and CSV smoke strategy at `configs/strategies/csv_market_data_smoke_v1.yaml`.
- Mocks used: Synthetic OHLCV price CSV, deterministic mock market data for regression, and SQLite verification databases at `/private/tmp/taurus-m10-verify-20260519.db` and `/private/tmp/taurus-m10-mock-verify-20260519.db`.

## M11 - Continuous Paper Trading

Status: Done

Objective: Scheduled paper loop using latest available data.

User input required:

- [x] Paper trading schedule. Defaulted to one daily after-close run.
- [x] Market hours assumptions. Defaulted to Asia/Kolkata daily candles.
- [x] Confirmation to run after market close initially. Defaulted to yes per v0.3 spec.

Tasks:

- [x] Add scheduler.
- [x] Add end-of-day paper run pipeline.
- [x] Add run status tracking.
- [x] Add failure recovery.

Verification:

- [x] `make paper-loop-mock`
- [x] `make test`
- [x] `make lint`
- [x] `curl http://localhost:8000/runs`
- [x] `curl http://localhost:8000/runs/{run_id}`
- [x] Dashboard health check.

Acceptance:

- [x] Scheduled loop executes data update, features, analysts, debate, trader, risk, final approval, PaperBroker.
- [x] Each run has `run_id`.
- [x] Dashboard updates.
- [x] Failures are logged.

Notes:

- Added `PaperRunService` and `SimplePaperScheduler` for a documented local scheduler without adding a runtime dependency.
- Added `paper_runs` status tracking with `run_id`, timestamps, status, symbols, errors, market-data summary, and artifact IDs.
- Added `GET /runs` and `GET /runs/{run_id}`.
- Added dashboard scheduled-runs tables on the main and paper trading pages.
- Added `make paper-loop-mock`; `paper-loop-once` and `paper-loop-start` now use the M11 run service and accept `SYMBOLS`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make paper-loop-mock` produced `run_id=pr-edecbedf6614c240`, `status=COMPLETED`, `symbols=[INFY]`, `final_status=APPROVED_FOR_PAPER`, `order_status=FILLED`, and a strategy summary with `feature_snapshot_count=10`.
- `/runs` and `/runs/pr-edecbedf6614c240` returned the persisted run record.
- `curl http://127.0.0.1:8501/_stcore/health` returned `ok` with the dashboard pointed at the M11 verification database.
- Verified `51 passed`.
- `make lint` compile-checks pass.
- Global Codex approvals added during verification were copied into `.codex/rules/default.rules`, documented in `docs/TAURUS_COMMANDS.md`, and removed from `/Users/adnaan/.codex/rules/default.rules` after the user's marker.

Completion summary:

- Assumptions made: M11 uses the v0.3 default schedule: daily candles, Asia/Kolkata timezone, and after-market-close operation. The scheduler is a simple local loop with configurable iterations and interval rather than APScheduler/Celery/Prefect, keeping the MVP dependency surface small. Real vendor data remains optional; mock market data is used when no CSV or external provider is configured.
- Mocks created: Unit-test partial-failure scheduled run using symbols `INFY,MISSING` to verify one-symbol failure handling and audit logging.
- Mocks used: Deterministic mock market data, mock news provider, mock LLM analyst outputs, mock debate/trader/risk/final-approval pipeline, internal PaperBroker, and SQLite verification database at `/private/tmp/taurus-m11-verify-20260520.db`.

## M12 - Telegram Alerts, Replay, Backup, Hardening

Status: Done

Objective: Alerts, replay, backups, and runbook.

User input optional:

- [ ] `TELEGRAM_BOT_TOKEN`
- [ ] `TELEGRAM_CHAT_ID`

Tasks:

- [x] Add Telegram alert adapter.
- [x] Add alert smoke command.
- [x] Add decision replay by `decision_id`.
- [x] Add backup and restore scripts.
- [x] Add operations runbook.

Verification:

- [x] `make alert-smoke`
- [x] `make replay-decision DECISION_ID=sample`
- [x] `make backup-db`
- [x] `make test`
- [x] `make lint`
- [x] `make backup-local`
- [x] `make restore-local BACKUP=...`

Acceptance:

- [x] Telegram adapter and mock smoke test work without credentials.
- [x] Alerts fire for fills, kill switch, severe events, stale data, job failures.
- [x] Decision replay works.
- [x] Backup and restore commands exist.
- [ ] Real Telegram end-to-end smoke test is deferred to Post-MVP Follow-Ups.

Notes:

- Added `AlertAdapter`, `TelegramAlertAdapter`, `MockAlertAdapter`, alert templates, and `AlertService`.
- Default `TAURUS_ALERT_PROVIDER=mock` keeps local/test runs independent of Telegram credentials. Real Telegram smoke is available with `make alert-test-telegram` after setting `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` locally.
- Alerts are emitted for paper fills, order rejections, kill-switch blocks, severe-event blocks, stale-data blocks, risk rejections/blocks, and scheduled paper-run failures.
- Added safe mock API endpoint `POST /alerts/test` and replay endpoint `GET /replay/{decision_id}`.
- Added `make replay-decision DECISION_ID=sample`; the `sample` smoke path replays the latest stored final decision or creates a deterministic mock paper decision when none exists.
- Added SQLite/Postgres-aware `make backup-local`, `make backup-db`, and `make restore-local BACKUP=...`.
- Added operations runbook at `docs/TAURUS_OPERATIONS_RUNBOOK.md`.
- Verified `55 passed`.
- `make lint` compile-checks pass.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db make alert-smoke` delivered a mock alert `alert-ebda1ad9cd8d0b6a`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db make replay-decision DECISION_ID=sample` replayed `decision_id=dec-005a68246fd41a40` with analyst reports, company event, debate, trader proposal, risk review, final decision, paper order, two fills, and audit rows.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db BACKUP_DIR=/private/tmp/taurus-m12-backups make backup-db` created a SQLite backup under `/private/tmp/taurus-m12-backups`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db BACKUP=/private/tmp/taurus-m12-backups/taurus-20260520T105647138364Z make restore-local` restored the SQLite database and created a pre-restore copy.

Completion summary:

- Assumptions made: Telegram credentials are optional for M12 implementation and were not provided during verification, so real Telegram delivery remains an environment-dependent smoke check. `DECISION_ID=sample` is treated as a smoke alias, not a real decision ID. Postgres backup/restore depends on local `pg_dump`/`pg_restore`; SQLite backup/restore is verified automatically.
- Mocks created: Mock alert adapter, API mock alert test endpoint, risk alert template fixture, scheduled job failure fixture, and SQLite backup/restore test database.
- Mocks used: Mock alert adapter, deterministic mock market data, mock news provider, mock LLM analyst outputs, mock debate/trader/risk/final-approval pipeline, internal PaperBroker, and SQLite verification database at `/private/tmp/taurus-m12-verify-20260520.db`.

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

## Post-MVP Follow-Ups

These tasks are intentionally deferred until all milestones are achieved.

- [ ] Validate a real Screener CSV export after the user creates a Screener account/subscription and provides a local CSV path.
- [ ] Run `make import-screener CSV=/path/to/user_screener_export.csv` against the real file without committing the CSV.
- [ ] Confirm imported rows map to Taurus instruments and document any unmapped symbols/company names.
- [ ] Confirm `FundamentalsAnalystAgent`, `/fundamentals`, and the dashboard use the real imported data correctly.
- [ ] Decide whether extra column aliases, normalization, or scoring adjustments are needed for the real Screener export format.
- [ ] Select the external historical market data provider after MVP completion, then provide provider name, sandbox/API documentation, required env var names, and credentials through local `.env` only.
- [ ] Validate the external market data provider adapter in sandbox/paper mode without committing credentials or enabling live trading.
- [ ] Verify real Telegram alert delivery after all milestones are complete by receiving `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` through local `.env` or shell environment only.
- [ ] Run `make alert-test-telegram` and confirm the Taurus smoke alert is received in the configured Telegram chat.
- [ ] Run `TAURUS_ALERT_PROVIDER=telegram make paper-once-mock SYMBOL=INFY` and confirm a paper-fill alert is received in Telegram.
- [ ] Document the real Telegram smoke result without committing credentials or logging token/chat secrets.

## Maintenance Rules

Update this file whenever a milestone task starts, completes, or is intentionally deferred.

For each completed milestone, record:

- status changes
- verification commands run
- test results
- user inputs provided or skipped
- safety notes, especially live-trading guardrails

Do not mark a milestone complete unless its acceptance criteria pass.
