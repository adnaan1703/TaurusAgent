# Taurus Milestone TODO

Source of truth:

- `docs/TAURUS_MVP_SPEC_v0_3.md`
- `docs/TAURUS_CODEX_TASKS_v0_3.yaml`
- `docs/UPSTOX_INTEGRATION_PLAN.md` for deferred broker integration
- `docs/TAURUS_REACT_DASHBOARD_PLAN.md` for M16 React dashboard work
- `docs/KITE_INTEGRATION_PLAN.md` for M17 Kite market data integration
- `docs/HALAL_STCK_COMPLIANCE_PLAN.md` for M18 halal stock compliance universe

Last updated: 2026-05-24 21:09 IST

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
| M13 | Done | Paper-trading MVP release | Optional real CSV/data source skipped; mock data used | No |
| M14 | Deferred | Upstox sandbox adapter | Sandbox token required | Yes |
| M15 | Deferred | Upstox production readiness | Broker/compliance approval required | Yes |
| M16 | Done | React run-loop observability dashboard | No | No |
| M17 | Done | Kite Connect market data provider | Kite access token required for real smoke | Yes |
| M18 | Done | Halal stock compliance universe | No | No |

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

## M13 - Paper-Trading MVP Release

Status: Done

Objective: End-to-end observable paper-trading MVP, with Upstox/broker integration deferred.

User input required:

- [x] Optional real OHLCV CSV path or data-provider decision for extended paper trading. Not provided; deterministic mock market data used.
- [x] Optional real Screener CSV path for fundamentals validation. Not provided; fundamentals remain mock/fixture-backed until post-MVP validation.
- [x] Optional Telegram credentials for real alert smoke testing. Not provided; mock alert adapter used.

Verification:

- [x] `make setup`
- [x] `make dev-up`
- [x] `make migrate`
- [x] `make seed-mock`
- [x] `make import-mock-news`
- [x] `make backtest-mock`
- [x] `make run-analysts-mock SYMBOL=INFY`
- [x] `make debate-mock SYMBOL=INFY`
- [x] `make trader-proposal-mock SYMBOL=INFY`
- [x] `make risk-review-mock SYMBOL=INFY`
- [x] `make final-approval-mock SYMBOL=INFY`
- [x] `make paper-once-mock SYMBOL=INFY`
- [x] `make paper-loop-mock`
- [x] `make replay-decision DECISION_ID=sample`
- [x] `make backup-local`
- [x] `make taurus-smoke`
- [x] `make dashboard`
- [x] `make test`

Acceptance:

- [x] Taurus runs end-to-end with mock data.
- [x] Taurus can backtest.
- [x] Taurus generates analyst reports.
- [x] Taurus runs bull/bear debate.
- [x] Taurus generates trader proposal.
- [x] Taurus runs risk review and final approval.
- [x] Taurus paper trades only.
- [x] Dashboard shows performance, decisions, debate, risk, orders, events, and health.
- [x] Decision replay and backup work.
- [x] Live trading is disabled.
- [x] Broker sandbox and live broker work are not required for MVP completion.

Notes:

- Added `make taurus-smoke`, backed by `scripts/taurus_smoke.py`, to run the paper MVP chain and assert persisted artifacts, replay, backup, API endpoints, mock alerts, metrics, and paper-only safety settings.
- Added M13 release docs at `docs/TAURUS_MVP_RELEASE.md` and refreshed README, operations runbook, command reference, and script reference.
- Added a Docker Compose fallback for Postgres backups when local `pg_dump`/`pg_restore` are unavailable.
- `make setup` completed with dependencies already synced.
- Initial `make dev-up` failed because Docker Desktop was not running. Docker Desktop was started with `open -a Docker`; rerun `make dev-up` built the API image and started API, Postgres, Redis, Prometheus, and Grafana.
- `make seed-mock` seeded `10` instruments and `2520` daily candles.
- `make import-mock-news` imported `10` raw documents, `10` events, and `10` sentiment scores.
- `make backtest-mock` produced `run_id=bt-f1cb6aed6c20e80d`.
- `make run-analysts-mock SYMBOL=INFY` produced four analyst reports.
- `make debate-mock SYMBOL=INFY` produced `debate_id=deb-ce27cc42ed3d7bbb` with mild-bullish consensus.
- `make trader-proposal-mock SYMBOL=INFY` produced `proposal_id=tp-3e517c22c165b90e`, `action=BUY`, `is_order=false`, and `requires_risk_approval=true`.
- `make risk-review-mock SYMBOL=INFY` produced `risk_check_id=risk-5878c1185be2244d`, `status=APPROVED`, and `10` hard-rule results.
- `make final-approval-mock SYMBOL=INFY` produced `final_decision_id=fd-9c3160ad94937529`, `status=APPROVED_FOR_PAPER`, and `approved_quantity=89`.
- `make paper-once-mock SYMBOL=INFY` produced `order_id=po-4b91cac3077afaf7`, `status=FILLED`, and two paper fills.
- `make paper-loop-mock` produced `run_id=pr-921cf7c224f293c6`, `status=COMPLETED`, `final_status=APPROVED_FOR_PAPER`, and `order_status=FILLED`.
- `make replay-decision DECISION_ID=sample` replayed latest stored decision `dec-5238aa1731c2a758`.
- `make backup-local` produced Postgres backup `backups/taurus-20260520T161629865378Z`.
- `make taurus-smoke` passed with `paper_loop_run_id=pr-156107aec03ad5cb`, `paper_order_id=po-4b91cac3077afaf7`, mock alert delivery, all API smoke statuses `200`, and backup `backups/taurus-20260520T161642229863Z`.
- `make dashboard` started on `http://localhost:8501`; `curl http://127.0.0.1:8501/_stcore/health` returned `ok`; the dashboard process was stopped after verification.
- `curl http://localhost:8000/health` returned paper mode with `live_trading_enabled=false`.
- `curl http://localhost:8000/metrics` included `taurus_live_trading_enabled 0.0`, `taurus_observability_db_available 1.0`, row counts, workflow artifacts, and paper account metrics.
- `curl http://127.0.0.1:3000/api/health` returned Grafana database `ok`.
- `docker compose ps` showed API, Postgres, Redis, Prometheus, and Grafana running.
- Verified `57 passed`.
- `make lint` compile-checks pass.
- Global Codex rules were inspected. There were no entries after `# END MY CUSTOM ADDITION`, so no Taurus-specific approvals needed to be moved.
- Generated local backup artifacts are ignored through `.gitignore`.

Completion summary:

- Assumptions made: M13 release can complete without real OHLCV CSVs, a real Screener export, or Telegram credentials because those inputs are explicitly optional. The final MVP remains local-first, daily-candle based, and paper-only. Docker Compose Postgres is the supported local Postgres backup fallback when `pg_dump` is not installed on the host.
- Mocks created: M13 end-to-end smoke test fixture using a temporary SQLite database; Docker Compose `pg_dump` fallback unit-test double.
- Mocks used: Deterministic mock market data, mock news provider, mock LLM analyst outputs, mock alert adapter, mock/fixture-backed fundamentals path, internal PaperBroker, FastAPI TestClient API smoke, local Docker Compose Postgres verification database, and Postgres backups under `backups/taurus-20260520T161629865378Z` and `backups/taurus-20260520T161642229863Z`.

## M14 - Upstox Sandbox Adapter

Status: Deferred until after the paper-trading MVP release.

Objective: Validate Taurus order-payload mapping against Upstox Sandbox without enabling live trading.

Notes:

- Tracked separately in `docs/UPSTOX_INTEGRATION_PLAN.md`.
- Current Upstox sandbox runtime should use `UPSTOX_SANDBOX_ACCESS_TOKEN`; OAuth app fields are portal/setup concerns unless Upstox changes the flow.
- PaperBroker remains the default even after this adapter exists.

## M15 - Upstox Production Readiness

Status: Deferred until after Upstox Sandbox validation and explicit manual approval.

Objective: Production-readiness and compliance gate for future broker integration; no live orders during this milestone.

Notes:

- Tracked separately in `docs/UPSTOX_INTEGRATION_PLAN.md`.
- Requires broker/compliance details, manual release approval, kill switch, reconciliation, audit, and observability checks.
- `LIVE_TRADING_ENABLED=false` remains the default.

## M16 - React Run-Loop Observability Dashboard

Status: Done

Objective: Build a read-only React web app that makes each Taurus paper run understandable as a stitched flow from run to symbol to decision trail to paper execution.

Detailed plan:

- `docs/TAURUS_REACT_DASHBOARD_PLAN.md`
- Stitch metadata and download URLs: `docs/stitch/paper-trade-event-monitor/STITCH_MANIFEST.md`

Operating rule:

- Treat each M16 submilestone like a main milestone. Complete its checklist, acceptance criteria, verification, cleanup, command-approval hygiene, tracker updates, and completion summary; then stop and report the result to the user. Do not automatically start the next M16 submilestone unless the user explicitly asks to proceed.

Submilestones:

- [x] M16.1 Reference and planning assets.
- [x] M16.2 Backend aggregate APIs.
- [x] M16.3 React app foundation.
- [x] M16.4 Core observability screens.
- [x] M16.5 Verification and polish.

Acceptance:

- [x] React dashboard uses real FastAPI data and remains read-only.
- [x] User can navigate from run overview to run detail to symbol decision trail.
- [x] Risk gates, missing artifacts, final decisions, paper orders, and fills are visually connected.
- [x] Streamlit remains available as a fallback diagnostic dashboard.
- [x] No live-trading or broker-control capability is introduced.

Notes:

- M16.1 downloaded 7 Stitch reference screenshots and 7 generated HTML files under `docs/stitch/paper-trade-event-monitor/assets/`.
- `docs/stitch/paper-trade-event-monitor/README.md` now documents the Stitch project ID, design-system asset ID, screen IDs, local filenames, visual tokens, Taurus route mapping, and read-only scope rule.
- The generated Stitch HTML is documented as reference-only and must not be ported directly into React production components.

M16.1 completion summary:

- Assumptions made: The downloaded Stitch assets are reference material only; production React implementation will use clean components and real FastAPI aggregate data. V1 remains read-only even if visual references imply run-control actions.
- Mocks created: None
- Mocks used: None

M16.2 notes:

- Added read-only aggregate UI endpoints under `/ui`: overview, run detail, symbol decision trail, replay, risk, portfolio, and history.
- Added local Vite CORS origins only: `http://localhost:5173` and `http://127.0.0.1:5173`.
- Added run-scoped repository filters for UI joins and audit-row lookup without changing existing raw endpoints.
- Added `tests/unit/test_ui_aggregate_api.py` for completed runs, partial failures, unknown IDs, run scoping, empty migrated database state, and CORS.
- Verified `62 passed` and compile-check lint passed.
- `DATABASE_URL=sqlite:////private/tmp/taurus-m16-api-20260521.db make paper-loop-mock` produced `run_id=pr-75fdbb0381152d57`, `decision_id=dec-1d59184394a64b42`, final status `APPROVED_FOR_PAPER`, and order status `FILLED`.
- API smoke checks returned `200` for `/ui/overview`, `/ui/history`, `/ui/runs/pr-75fdbb0381152d57`, `/ui/runs/pr-75fdbb0381152d57/symbols/INFY/decision-trail`, `/ui/replay/dec-1d59184394a64b42`, `/ui/risk`, and `/ui/portfolio`.
- Global Codex approvals added during verification were copied into `.codex/rules/default.rules`, documented in `docs/TAURUS_COMMANDS.md`, and removed from `/Users/adnaan/.codex/rules/default.rules` after the user's marker.

M16.2 completion summary:

- Assumptions made: UI aggregate APIs may return presentation-oriented payloads that wrap existing raw artifact payloads without changing the raw endpoints. Audit rows are run-scoped and symbol-filtered when the audit payload has symbol information; run-level audit rows are included for symbol trails. Empty database behavior assumes migrations have created the tables.
- Mocks created: Unit-test temporary SQLite databases, including completed paper runs, partial-failure runs, repeated-symbol run-scope checks, and migrated empty database state.
- Mocks used: Deterministic mock market data, mock news provider, mock LLM analyst outputs, mock alert provider, internal PaperBroker, and SQLite verification database at `/private/tmp/taurus-m16-api-20260521.db`.

M16.3 notes:

- Added `apps/web` as a Vite React TypeScript app using `pnpm`.
- Added Tailwind with Taurus/Stitch dark observability tokens and a responsive read-only app shell.
- Added typed aggregate API client, React Router route skeletons, TanStack Query provider, and `VITE_TAURUS_API_BASE_URL` defaulting to `http://localhost:8000`.
- Added shared primitives for later screens: status badge, metric card, data panel, table, JSON drawer, empty state, refresh button, loading/error states, and route error presentation.
- Added initial Vitest/Testing Library tests for app shell, status badges, and empty states.
- Added `make setup-ui`, `make ui`, `make build-ui`, and `make test-ui`.
- Added project-local pnpm `allowBuilds.esbuild=true` so `make setup-ui` succeeds with pnpm 11 without broadening global settings.
- Adjusted `make lint` to compile-check Python-owned paths only and avoid traversing `apps/web/node_modules`.
- `make setup-ui` completed successfully after adding the local esbuild build allowlist.
- `make test-ui` verified `11 passed`.
- `make build-ui` produced a production Vite build.
- `make ui` started Vite on `http://localhost:5173/`; `curl -sS -o /private/tmp/taurus-m16-ui-vite.html -w '%{http_code}' http://127.0.0.1:5173/` returned `200`; the dev server was stopped after verification.
- `make test` verified `62 passed`.
- `make lint` compile-checks passed.
- Global Codex rules were inspected. There were no entries after `# END MY CUSTOM ADDITION`, so no Taurus-specific approvals needed to be moved.

M16.3 completion summary:

- Assumptions made: M16.3 uses the already documented stack and scope defaults: Vite + React + TypeScript, `pnpm`, Tailwind, TanStack Query, Recharts dependency, and read-only route shells only. `esbuild` is the only frontend dependency build script allowed because Vite requires it locally.
- Mocks created: Frontend test overview, run, decision-trail, replay, risk, portfolio, and history payloads for app-shell and route-skeleton rendering.
- Mocks used: Mocked browser `fetch` response in Vitest for `/ui/overview`; no backend fixture data was used for M16.3 frontend verification.

M16.4 notes:

- Started M16.4 core observability screens on 2026-05-21.
- Implemented Overview, Run Detail, Symbol Decision Trail, Decision Replay, Risk Engine, Portfolio & Account, and Run History using real `/ui/*` aggregate data.
- Added shared frontend formatting helpers plus reusable safety, warning, and key-value display components.
- Added read-only polling/manual refresh behavior: overview and history poll every 15 seconds; running run detail and decision trail poll every 5 seconds; completed run/trail views stop aggressive polling.
- Added searchable/filterable run history and a replay `decision_id` input.
- Added a narrow additive `/ui` run-summary update for `timezone` and `run_after_market_close` so run detail can show the required schedule context.
- Added frontend screen-state coverage for loading, empty, API-unavailable, populated decision trail, risk blocked/reduced states, portfolio execution tables, and history filtering.
- Verified `make test-ui`: `18 passed`.
- Verified `make build-ui`: Vite production build succeeded.
- Verified `make test`: `62 passed`.
- Verified `make lint`: Python compile-checks passed.
- Smoke dataset: `DATABASE_URL=sqlite:////private/tmp/taurus-m16-ui-20260521.db make paper-loop-mock` produced `run_id=pr-03c57d458f851eaf`, `decision_id=dec-e81e1bde3ecffdf5`, final status `APPROVED_FOR_PAPER`, and paper order status `FILLED`.
- Local smoke: API and Vite started on ports `8000` and `5173`; `curl` returned `200` for `/ui/overview`, `/ui/runs/pr-03c57d458f851eaf`, `/ui/runs/pr-03c57d458f851eaf/symbols/INFY/decision-trail`, and `http://127.0.0.1:5173/`.
- API and Vite smoke processes were stopped after verification; ports `8000` and `5173` were clear.
- Browser visual verification was not run because the Browser plugin's required Node control tool was not exposed in this session.
- Global Codex rules were inspected. There were no entries after `# END MY CUSTOM ADDITION`, so no Taurus-specific approvals needed to be moved.
- `.gitignore` covers frontend dependency folders, build outputs, and coverage artifacts through `node_modules/`, `dist`, `dist/`, `coverage`, and `.coverage*` entries.

M16.4 completion summary:

- Assumptions made: The `/ui` run summary can safely expose `timezone` and `run_after_market_close` as additive aggregate fields because run-detail screens need schedule context and existing raw endpoints remain unchanged. Generic artifact rendering can show the first common payload fields while preserving full raw JSON for debugging. The Browser plugin's required Node control tool was not exposed in this session, so local visual verification was limited to served-page HTTP smoke plus automated frontend tests.
- Mocks created: Frontend screen-state fixtures for overview, run detail, decision trail, replay, risk, portfolio, and history, including missing debate artifacts, approved-with-reduction risk, blocked risk, filled order, fill, and searchable history states.
- Mocks used: Mocked browser `fetch` responses in Vitest; deterministic mock market data, mock news, mock LLM outputs, mock alert provider, internal PaperBroker, and SQLite smoke database at `/private/tmp/taurus-m16-ui-20260521.db`.

M16.5 notes:

- Completed final verification and polish on 2026-05-21.
- Reran full M16.5 verification on 2026-05-22 after permission issues were resolved.
- Fixed `make api` to pass `DATABASE_URL="$(DATABASE_URL)"` to Uvicorn. The retest exposed that direct local API serving otherwise used the config default SQLite database while smoke data was in Postgres.
- Post-fix retest verified `make test`: `62 passed`.
- Post-fix retest verified `make lint`: Python compile-checks passed.
- Post-fix retest verified `make test-ui`: `18 passed`.
- Post-fix retest verified `make build-ui`: Vite production build succeeded.
- Post-fix retest verified default Postgres `make taurus-smoke`: `status=passed`, `paper_loop_run_id=pr-e65310164943cf50`, `decision_id=dec-9d0a05ac264c1ddd`, `paper_order_id=po-4b91cac3077afaf7`, backup `backups/taurus-20260522T050955533184Z`, and all API smoke statuses `200`.
- Post-fix local React/API smoke returned `200` for `/ui/overview`, `/ui/runs/pr-e65310164943cf50`, `/ui/runs/pr-e65310164943cf50/symbols/INFY/decision-trail`, and `http://127.0.0.1:5173/`.
- Captured fresh headless Chrome screenshots for overview and decision trail at desktop `1440x1000` and mobile `390x844`; desktop and mobile layouts remained readable.
- Inspected `/Users/adnaan/.codex/rules/default.rules` after the retest. A broad accidental `curl -sS` global approval was removed and no entries remained after `# END MY CUSTOM ADDITION`.
- Stopped the API, Vite dev server, and Docker Compose services after the retest; ports `8000` and `5173` were clear and `docker compose ps` showed no running services.
- Updated `README.md` and `docs/TAURUS_USAGE_GUIDE.md` so the React dashboard on `http://localhost:5173` is documented as the primary local run-loop observability UI.
- Streamlit remains documented as the fallback diagnostic dashboard on `http://localhost:8501`.
- Updated `docs/TAURUS_COMMANDS.md` with M16.5 verification commands.
- Verified `make test`: `62 passed`.
- Verified `make lint`: Python compile-checks passed.
- Verified `make test-ui`: `18 passed`.
- Verified `make build-ui`: Vite production build succeeded.
- Initial `make taurus-smoke` failed because local Postgres on port `5432` was not running. Initial `make dev-up` did not create services before it was stopped.
- Started the required database services with `docker compose up -d postgres redis`.
- Verified default Postgres `make taurus-smoke`: `status=passed`, `paper_loop_run_id=pr-a9ff400716c11825`, `decision_id=dec-9d0a05ac264c1ddd`, `paper_order_id=po-4b91cac3077afaf7`, backup `backups/taurus-20260521T173336981385Z`, and all API smoke statuses `200`.
- Verified an isolated SQLite smoke fallback: `DATABASE_URL=sqlite:////private/tmp/taurus-m16-final-smoke-20260521.db BACKUP_DIR=/private/tmp/taurus-m16-final-backups make taurus-smoke` returned `status=passed`.
- Verified local React smoke against API on port `8000` and Vite on port `5173`; `/ui/overview`, `/ui/runs/pr-16216828cc03acfe`, `/ui/runs/pr-16216828cc03acfe/symbols/INFY/decision-trail`, and `http://127.0.0.1:5173/` returned `200`.
- Captured headless Chrome screenshots for overview and decision trail at desktop `1440x1000` and mobile `390x844`; layout checks found no page-level horizontal overflow on desktop or the decision-trail mobile route.
- Compared the React layout to the Stitch dark overview reference for visual direction: deep navy background, bordered dark surfaces, cyan/green status accents, fixed desktop side navigation, and compact observability-first panels.
- Confirmed `.gitignore` covers frontend dependency folders, build outputs, test coverage, local backups, local env files, and Python caches.
- Scanned changed files for obvious secrets, API keys, tokens, and private-key material; no real secrets were found.
- Inspected `/Users/adnaan/.codex/rules/default.rules`; there were no entries after `# END MY CUSTOM ADDITION`, so no Taurus-specific approvals needed to be moved.
- Stopped the API, Vite dev server, and Docker Compose services after verification; ports `8000` and `5173` were clear and `docker compose ps` showed no running services.

M16.5 completion summary:

- Assumptions made: Headless Chrome screenshots and DOM layout checks are sufficient for local M16.5 visual verification because the in-app Browser control tool was not exposed in this session. Starting only Postgres and Redis is sufficient for the default `make taurus-smoke` verification because the smoke script runs locally and does not require the API container. React can be documented as the primary local observability UI while Streamlit remains a fallback diagnostic surface.
- Mocks created: None
- Mocks used: Deterministic mock market data, mock news provider, mock LLM outputs, mock alert provider, internal PaperBroker, Docker Compose Postgres verification database, and isolated SQLite smoke database at `/private/tmp/taurus-m16-final-smoke-20260521.db`.

M16 completion summary:

- Assumptions made: React dashboard v1 remains read-only and local-first, using backend aggregate `/ui/*` endpoints instead of client-side artifact joins. Streamlit remains available as a fallback diagnostic dashboard and is not removed.
- Mocks created: None during M16.5; earlier M16 submilestones created frontend screen-state fixtures for UI test coverage.
- Mocks used: Deterministic mock market data, mock news provider, mock LLM outputs, mock alert provider, internal PaperBroker, Docker Compose Postgres verification database, and SQLite smoke/test databases documented in M16.2-M16.5 notes.

## M17 - Kite Connect Market Data Provider

Status: Done

Objective: Integrate Zerodha Kite Connect as a data-only market data provider while preserving paper-only execution and safe mock defaults.

Detailed plan:

- `docs/KITE_INTEGRATION_PLAN.md`

User input required:

- [x] `KITE_API_KEY` saved locally in ignored `.env`.
- [x] `KITE_API_SECRET` saved locally in ignored `.env`.
- [!] `KITE_ACCESS_TOKEN` still required for real Kite sync/import/smoke commands.

Tasks:

- [x] Add safe configuration and provider-neutral Kite universe.
- [x] Add quote domain types and latest snapshot persistence.
- [x] Add Kite market data provider with instrument sync, historical candles, and quote snapshots.
- [x] Add Kite scripts and Make targets.
- [x] Add persisted latest quote API endpoint.
- [x] Add automated tests that do not require real Kite credentials.
- [x] Update docs and command references.
- [x] Run verification and Codex rules cleanup.

Verification:

- [x] `uv run pytest tests/unit/test_kite_market_data.py`
- [x] `uv run pytest tests/unit/test_kite_auth.py`
- [x] `make kite-login-url`
- [x] `make test`
- [x] `make lint`
- [x] `DATABASE_URL=sqlite:////private/tmp/taurus-kite-plan-smoke.db make paper-loop-mock`
- [x] Manual real Kite smoke: `make kite-sync-instruments`, `make import-kite-candles`, and `make kite-ltp-smoke` after `KITE_ACCESS_TOKEN` was generated locally.

Acceptance:

- [x] Mock and CSV market data paths still pass tests.
- [x] Kite provider is selected only when explicitly configured.
- [x] Missing Kite credentials do not break default test runs.
- [x] Kite instrument sync resolves enabled YAML symbols in automated fake-client tests.
- [x] Kite candle import maps daily candles with provider source metadata in automated fake-client tests.
- [x] Kite LTP/OHLC smoke path persists snapshots in automated fake-client tests.
- [x] Real Kite instrument sync, candle import, and quote snapshot smoke succeeded with the generated local access token.
- [x] `/data/quotes/latest` serves persisted snapshots without making live Kite calls.
- [x] Paper trading remains paper-only.
- [x] No real secrets are committed or logged.

Notes:

- Added `kiteconnect>=5,<6` and `pyyaml>=6,<7` through `uv add`.
- Added `configs/market_data/kite_nse_cash.yaml` as the provider-neutral universe file for enabled Kite-backed symbols.
- Added `MarketPriceSnapshot`, `MarketQuoteProvider`, `instrument_provider_mappings`, and `market_price_snapshots`.
- Added `KiteMarketDataProvider` with credential checks, universe resolution, instrument-master caching, historical daily candle mapping, OHLC/LTP snapshot mapping, conservative pacing, bounded retry, and token-expiry error translation.
- Added latest quote snapshots for mock and CSV providers from their latest daily candles.
- Added `scripts/sync_kite_instruments.py`, `scripts/import_kite_candles.py`, `scripts/kite_ltp_smoke.py`, and Make targets `kite-sync-instruments`, `import-kite-candles`, and `kite-ltp-smoke`.
- Added `scripts/kite_auth.py` and Make targets `kite-login-url` and `kite-exchange-token` for the manual Kite login/request-token/access-token flow.
- Added the local-only FastAPI root callback for Kite redirects, so `http://127.0.0.1:8000/?request_token=...` exchanges and stores `KITE_ACCESS_TOKEN` automatically when `make api` is running.
- Added `GET /data/quotes/latest?symbol=INFY`, which reads only persisted snapshots.
- `make kite-login-url` generated the Kite Connect login URL for the configured local API key and the URL was opened in the default browser on 2026-05-24.
- `make kite-exchange-token REQUEST_TOKEN=...` exchanged the Kite request token for an access token and stored it in ignored `.env` without printing the token.
- Default Postgres Kite sync failed while local Postgres was stopped; the real Kite smoke was rerun against isolated SQLite at `/private/tmp/taurus-kite-real-smoke.db`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-kite-real-smoke.db make kite-sync-instruments` synced `2` Kite mappings: `INFY`, `TCS`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-kite-real-smoke.db make import-kite-candles` imported `542` Kite daily candles for `2` instruments, dates `2025-04-21..2026-05-22`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-kite-real-smoke.db make kite-ltp-smoke` stored `2` Kite quote snapshots for `INFY`, `TCS`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-kite-plan-smoke.db make paper-loop-mock` completed with `run_id=pr-d96f32b86d4d1c87`, `status=COMPLETED`, `final_status=APPROVED_FOR_PAPER`, and `order_status=FILLED`.
- `KITE_API_KEY`, `KITE_API_SECRET`, and generated `KITE_ACCESS_TOKEN` are saved only in ignored, permission-restricted `.env`.
- Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries existed after `# END MY CUSTOM ADDITION`, so no global approvals needed to be moved.

Completion summary:

- Assumptions made: Kite access tokens are short-lived manual login artifacts and must remain local; SQLite is acceptable for real Kite smoke validation when local Postgres is stopped. The provided API secret is stored locally for the manual token workflow but is not required by the data provider after `KITE_ACCESS_TOKEN` is generated.
- Mocks created: Fake Kite client, fake transient network exception, fake token-expiry exception, temporary universe YAML files, and SQLite quote/sync/paper-loop test databases.
- Mocks used: Fake Kite client for instrument master, historical candle, OHLC/LTP snapshot, retry, and token-expiry tests; deterministic mock market data, mock news provider, mock LLM outputs, mock alert provider, internal PaperBroker, SQLite verification database at `/private/tmp/taurus-kite-plan-smoke.db`, and real Kite smoke SQLite database at `/private/tmp/taurus-kite-real-smoke.db`.

## M18 - Halal Stock Compliance Universe

Status: Done

Objective: Scrape HalalStock.in compliance rows, store BSE/NSE compliance data in the DB, and generate an NSE-only halal market-data universe for Kite/paper-trading flows.

Detailed plan:

- `docs/HALAL_STCK_COMPLIANCE_PLAN.md`

Tasks:

- [x] Add HalalStock fetcher with browser-like headers, timeout, checksum, and no cookies.
- [x] Add parser for the first `tablepress-24` table only.
- [x] Map `hs-yes.jpg` to `halal` and `hs-no.jpg` to `haram`.
- [x] Hard-fail on unknown icon URLs before DB writes.
- [x] Dedupe by normalized name, BSE code, NSE code, and details URL; fail conflicting duplicates.
- [x] Add `halal_stock_imports` and `halal_stock_compliance` DB models/repository.
- [x] Upsert compliance rows and mark missing prior rows inactive.
- [x] Export `configs/market_data/halal_nse_cash.yaml` deterministically from active halal NSE rows.
- [x] Validate generated YAML with `load_market_data_universe`.
- [x] Add `scripts/sync_halal_stocks.py` and `make sync-halal-stocks`.
- [x] Add settings/env defaults.
- [x] Add parser, DB/service, and export tests.
- [x] Update docs and command references.
- [x] Run verification and Codex rules cleanup.

Verification:

- [x] `uv run pytest tests/unit/test_halal_stock_compliance.py`
- [x] `make test`
- [x] `make lint`
- [x] `DATABASE_URL=sqlite:////private/tmp/taurus-halal.db make sync-halal-stocks`
- [x] `uv run python - <<'PY' ... load_market_data_universe('configs/market_data/halal_nse_cash.yaml') ... PY`

Acceptance:

- [x] Parser maps yes/no icons correctly.
- [x] Parser ignores duplicate responsive/secondary tables by selecting the first exact `tablepress-24` table.
- [x] Parser rejects unknown status icons and missing/renamed required columns.
- [x] Exact duplicate rows are deduped; conflicting duplicates fail.
- [x] Import metadata is stored.
- [x] Compliance rows are upserted and missing old rows are marked inactive.
- [x] `status_changed_at` updates only when compliance status changes.
- [x] Export excludes haram rows and rows without `NSECode`.
- [x] Export fails on duplicate NSE symbol conflicts.
- [x] Generated YAML loads through the existing market-data universe loader.
- [x] No new HTTP API or automatic trading loop was added.

Notes:

- Added dependency `beautifulsoup4>=4,<5` for tolerant parsing of the source page's real-world HTML.
- Added `packages/taurus_core/compliance/halal_stocks.py` with fetch, parse, import, export, and sync helpers.
- Added `TAURUS_HALAL_STOCK_SOURCE_URL`, `TAURUS_HALAL_STOCK_TABLE_ID`, `TAURUS_HALAL_STOCK_UNIVERSE_PATH`, and `TAURUS_HALAL_STOCK_MIN_ROWS`.
- Live sync on 2026-05-24 fetched source checksum `445f5ded2e931370e7b26553539f1cc9c2b5daae32a4b926111ba9f0571d00de`.
- `DATABASE_URL=sqlite:////private/tmp/taurus-halal.db make sync-halal-stocks` produced `import_id=hsi-f5efd9e21016f020`, `rows_seen=5312`, `rows_imported=5310`, `duplicate_count=2`, `halal_count=2726`, `haram_count=2586`, `unknown_count=0`, and `active_count=5310`.
- The two duplicate source rows were exact halal duplicates; after dedupe, active halal DB rows are `2724`.
- Generated `configs/market_data/halal_nse_cash.yaml` with `1711` active halal NSE symbols.
- `make test` verified `93 passed`.
- `make lint` compile-checks pass.
- Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries existed after `# END MY CUSTOM ADDITION`, so no global approvals needed to be moved.

Completion summary:

- Assumptions made: HalalStock.in is stored as source-provided compliance data, not independently certified by Taurus. M18 exports NSE-only halal symbols because the current Kite universe flow is NSE-first. The generated halal universe is an allowed universe, not an instruction to trade every symbol.
- Mocks created: Synthetic HalalStock HTML table fixtures, unknown-icon fixture, renamed-column fixture, duplicate-NSE fixture, injected fetch-result fixture, and SQLite compliance DBs for tests.
- Mocks used: Synthetic HalalStock HTML fixtures, injected fetch-result fixture, temporary YAML export paths, SQLite test DBs, and SQLite live-sync verification database at `/private/tmp/taurus-halal.db`.

## M19 - Shariah Dashboard And Run Universe Provenance

Status: Done

Objective: Add a read-only React Shariah compliance dashboard backed by active `halal_stock_compliance` rows, and persist the symbol universe provenance used by paper loop runs.

Detailed plan:

- Add `/ui/shariah` with server-side search, compliance status filtering, pagination, active counts, latest import metadata, and halal NSE universe export metadata.
- Add a React `/shariah` page with summary cards, search/filter controls, a paginated compliance table, source/detail links, and empty-state guidance for `make sync-halal-stocks`.
- Add Shariah navigation to desktop and mobile React shells.
- Store paper run universe provenance in the existing run payload JSON without a DB migration.
- Display paper run universe provenance in Overview, History, and Run Detail.
- Add focused backend and frontend tests.

Tasks:

- [x] Add Shariah aggregate API and repository readers.
- [x] Add paper run universe provenance schemas and run-loop resolver.
- [x] Add React Shariah page, nav item, and universe displays.
- [x] Add backend and frontend tests.
- [x] Run verification and Codex rules cleanup.

Verification:

- [x] `uv run pytest tests/unit/test_halal_stock_compliance.py tests/unit/test_ui_aggregate_api.py tests/unit/test_kite_market_data.py tests/unit/test_paper_runs.py`
- [x] `make test`
- [x] `make lint`
- [x] `cd apps/web && pnpm test`
- [x] `cd apps/web && pnpm build`

Acceptance:

- [x] `/ui/shariah` returns active halal and haram rows from the DB, not the YAML export.
- [x] Shariah search matches company name, NSE symbol, and BSE code.
- [x] Shariah status filtering and pagination return correct totals.
- [x] Empty compliance DBs return an empty Shariah payload without error.
- [x] Paper loop runs record market-data universe provenance when symbols are loaded from a universe YAML.
- [x] Manual symbol runs record manual symbol provenance.
- [x] Overview, History, and Run Detail display universe provenance, with older runs shown as not recorded.
- [x] React Shariah page and navigation are covered by Vitest.

Notes:

- Added `GET /ui/shariah` backed by active `halal_stock_compliance` rows with `query`, `status`, `page`, and `page_size` parameters.
- Added Shariah response metadata for active counts, latest HalalStock import details, and configured halal NSE universe YAML export status.
- Added `/shariah` to the React dashboard with summary metrics, search, status filtering, pagination, active-row table, detail/source links, latest import metadata, exported universe metadata, and empty-state guidance for `make sync-halal-stocks`.
- Added run universe provenance to `PaperRun` payloads. Market-data universe runs record provider, universe name, YAML path, available symbol count, selected symbol count, and selected symbols. Manual runs record `manual_symbols`.
- Preserved `_symbols_from_env()` as the compatibility wrapper and added richer environment resolution for paper loop provenance.
- Added universe provenance displays in Overview, History, and Run Detail. Historical rows without payload metadata render as `Not recorded`.
- Focused backend verification reported `31 passed`.
- `make test` reported `97 passed`.
- `make lint` compile-checks passed.
- `cd apps/web && pnpm test` reported `21 passed`.
- `cd apps/web && pnpm build` completed successfully.
- Local smoke with API on `8000` and Vite on `5173` returned `200` for `/ui/shariah?page=1&page_size=5` and `http://127.0.0.1:5173/shariah`.
- Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries existed after `# END MY CUSTOM ADDITION`, so no global approvals needed to be moved.

Completion summary:

- Assumptions made: "All stocks" means active rows imported from the HalalStock source, including halal and haram statuses, not every Kite/NSE-listed stock. The halal NSE YAML remains an export/trading universe and is not the source for the Shariah dashboard table. Existing historical paper runs without universe payload metadata should remain readable and display `Not recorded`.
- Mocks created: Synthetic Shariah compliance HTML table fixtures, temporary missing halal YAML paths for API metadata coverage, frontend Shariah response fixtures, and env-resolved paper loop provenance fixtures.
- Mocks used: Synthetic Shariah HTML fixtures, fake Kite universe YAML fixtures from existing Kite tests, mock market data, mock news provider, mock LLM outputs, mock alert provider, internal PaperBroker, mocked browser `fetch` responses in Vitest, and SQLite test databases.

## Post-MVP Follow-Ups

These tasks are intentionally deferred until after the M13 paper-trading MVP release.

- [ ] Validate a real Screener CSV export after the user creates a Screener account/subscription and provides a local CSV path.
- [ ] Run `make import-screener CSV=/path/to/user_screener_export.csv` against the real file without committing the CSV.
- [ ] Confirm imported rows map to Taurus instruments and document any unmapped symbols/company names.
- [ ] Confirm `FundamentalsAnalystAgent`, `/fundamentals`, and the dashboard use the real imported data correctly.
- [ ] Decide whether extra column aliases, normalization, or scoring adjustments are needed for the real Screener export format.
- [ ] Select the external historical market data provider after MVP completion, then provide provider name, sandbox/API documentation, required env var names, and credentials through local `.env` only.
- [ ] Validate the external market data provider adapter in sandbox/paper mode without committing credentials or enabling live trading.
- [ ] Follow `docs/UPSTOX_INTEGRATION_PLAN.md` for deferred Upstox sandbox validation and later production-readiness planning.
- [ ] Provide `UPSTOX_SANDBOX_ACCESS_TOKEN` locally only when the post-MVP sandbox milestone starts.
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
