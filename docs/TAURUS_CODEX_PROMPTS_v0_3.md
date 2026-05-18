# Project Taurus - Codex Milestone Prompts v0.3

Version: 0.3  
Date: 2026-05-18  
Project: Taurus  
Companion specs:

- `TAURUS_MVP_SPEC_v0_3.md`
- `TAURUS_CODEX_TASKS_v0_3.yaml`

Use these prompts one milestone at a time. Do not ask Codex to implement multiple milestones in one run unless the previous milestone has already been accepted, committed, and tested.

---

## Recommended repo setup before M0

Before starting M0, place these files in your local project folder if possible:

```text
docs/TAURUS_MVP_SPEC_v0_3.md
docs/TAURUS_CODEX_TASKS_v0_3.yaml
docs/TAURUS_CODEX_PROMPTS_v0_3.md
```

If the repo does not exist yet, M0 should create the structure and add these files under `docs/`.

---

## Universal instructions to include with every Codex prompt

You may paste this block at the top of every milestone prompt.

```text
You are implementing Project Taurus, an observable, paper-trading-first algo trading MVP for Indian cash equities.

Read the project specification before editing code:
- docs/TAURUS_MVP_SPEC_v0_3.md
- docs/TAURUS_CODEX_TASKS_v0_3.yaml, if present

Non-negotiable rules:
1. Implement only the milestone named in this prompt.
2. Do not implement later milestones unless required to make this milestone testable.
3. Do not add real API keys, tokens, broker credentials, or secrets.
4. Do not enable live trading.
5. Keep `LIVE_TRADING_ENABLED=false` by default.
6. Broker provider must remain `paper` unless the milestone explicitly concerns sandbox integration.
7. All outputs that affect trading decisions must be structured, schema-validated where appropriate, logged, and testable.
8. Add or update tests for every meaningful behavior.
9. Prefer deterministic mock data and deterministic mock LLM outputs unless this milestone explicitly requests external integration.
10. At completion, provide:
   - files changed
   - commands run
   - test results
   - any assumptions made
   - any follow-up tasks or known limitations

Stop condition:
Stop after the milestone acceptance criteria pass. Do not continue to the next milestone.
```

---

# M0 Prompt - Project foundation

```text
You are implementing Project Taurus. Start with Milestone M0 only: Project foundation.

Goal:
Create the initial repository scaffold, local development environment, FastAPI app, safe configuration, JSON logging, Prometheus metrics endpoint, Docker Compose services, Makefile commands, and pytest setup.

Context:
Taurus is paper-trading-first. Live trading must be impossible at this stage. No broker integration is allowed in M0.

Implement:
1. Repository structure suitable for a Python monorepo:
   - apps/api
   - apps/dashboard, placeholder only if useful
   - packages/taurus_core
   - infra/prometheus
   - infra/grafana
   - scripts
   - tests/unit
   - docs
2. `pyproject.toml` with Python dependencies for FastAPI, uvicorn, pydantic, pydantic-settings, pytest, prometheus-client, structlog or equivalent JSON logging.
3. `.env.example` with safe defaults:
   - TAURUS_ENV=local
   - TAURUS_MODE=paper
   - LIVE_TRADING_ENABLED=false
   - BROKER_PROVIDER=paper
   - TAURUS_LLM_PROVIDER=mock
   - TAURUS_INITIAL_CAPITAL_INR=1000000
   - TAURUS_MAX_POSITION_PCT=5
   - TAURUS_MAX_OPEN_POSITIONS=8
4. Config loader in `packages/taurus_core/config.py`.
5. JSON logging setup in `packages/taurus_core/logging.py`.
6. FastAPI app with endpoints:
   - `GET /health`
   - `GET /ready`
   - `GET /metrics`
7. Docker Compose with at least:
   - Taurus API service if practical
   - Postgres or Timescale-compatible Postgres
   - Redis
   - Prometheus
   - Grafana
8. Prometheus config that scrapes the API `/metrics` endpoint.
9. Makefile commands:
   - `make setup`
   - `make dev-up`
   - `make dev-down`
   - `make api`
   - `make test`
   - `make lint`, even if minimal
10. Unit tests for config loading and health endpoint.
11. README with local setup and verification commands.
12. Add the project spec files under `docs/` if they are available in the current working directory.

Non-goals:
- No database schema beyond what is necessary for service startup.
- No trading strategy.
- No broker integration.
- No LLM integration.
- No dashboard beyond placeholder documentation.

Verification commands to run:
- `make setup`
- `make test`
- `make dev-up`
- `curl http://localhost:8000/health`
- `curl http://localhost:8000/ready`
- `curl http://localhost:8000/metrics`
- `make dev-down`

Acceptance criteria:
1. Tests pass.
2. API returns healthy status.
3. Metrics endpoint returns Prometheus text format.
4. Docker Compose starts core services.
5. No secrets are committed.
6. Live trading remains disabled by default and cannot be enabled accidentally through missing config.

Stop after M0 acceptance criteria pass and summarize exactly what changed.
```

---

# M1 Prompt - Mock data and database foundation

```text
You are implementing Project Taurus. Start with Milestone M1 only: Mock data and database foundation.

Prerequisite:
M0 must already be complete and tests must pass.

Goal:
Add the first database schema, repositories, deterministic mock instruments, and deterministic mock daily OHLCV candle data.

Implement:
1. Database session/connection utilities.
2. Migration support using Alembic or a clearly documented equivalent.
3. Domain models and DB tables for:
   - instruments
   - daily candles
   - portfolio snapshots, minimal placeholder allowed
   - audit log, minimal placeholder allowed
4. Repository methods for:
   - create/list/get instruments
   - insert/list candles
   - get candles by symbol and date range
5. Deterministic `MockMarketDataProvider`.
6. Seed script that creates at least 10 mock Indian equity-like instruments and at least 252 daily candles per instrument.
7. API endpoints:
   - `GET /data/instruments`
   - `GET /data/instruments/{symbol}`
   - `GET /data/candles?symbol=INFY&timeframe=1d`
8. Makefile commands:
   - `make migrate`
   - `make seed-mock`
9. Tests for deterministic seed behavior and repository reads.

Mock symbols may include:
RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, LT, SBIN, BHARTIARTL, ITC, HINDUNILVR.

Non-goals:
- No real market data.
- No strategy.
- No backtesting engine.
- No paper orders.

Verification commands to run:
- `make dev-up`
- `make migrate`
- `make seed-mock`
- `make test`
- `curl http://localhost:8000/data/instruments`
- `curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"`

Acceptance criteria:
1. At least 10 mock instruments exist.
2. Each instrument has at least 252 daily candles.
3. Running seed twice with the same seed is deterministic and does not create duplicate broken records.
4. API returns instruments and candles.
5. Tests pass.
6. Live trading remains disabled.

Stop after M1 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M2 Prompt - Backtesting skeleton

```text
You are implementing Project Taurus. Start with Milestone M2 only: Backtesting skeleton.

Prerequisite:
M1 must already be complete with seeded mock market data.

Goal:
Create the first deterministic backtesting engine using mock daily data. The engine should store a backtest run, signals, simulated orders/fills, positions, portfolio snapshots, and basic performance metrics.

Implement:
1. Backtesting domain models/tables if not already present:
   - backtest_runs
   - signals
   - simulated_orders
   - simulated_fills
   - positions
   - portfolio_snapshots
   - backtest_metrics
2. A simple event-driven backtest loop over daily candles.
3. A minimal deterministic mock momentum strategy, for example:
   - buy if close is above a short moving average and momentum is positive
   - exit if close falls below the moving average
4. Simple position sizing using the configured capital and max position percent.
5. Cost/slippage model with configurable defaults.
6. Metrics calculation:
   - total return
   - CAGR if date range supports it
   - max drawdown
   - daily volatility
   - Sharpe ratio, basic placeholder acceptable if documented
   - number of trades
7. Script:
   - `scripts/run_backtest.py`
8. Makefile command:
   - `make backtest-mock`
9. API endpoint to retrieve backtest runs and metrics, if practical:
   - `GET /backtests`
   - `GET /backtests/{run_id}`
10. Tests for deterministic backtest output with fixed mock data.

Non-goals:
- No advanced strategy framework yet.
- No LLM agents.
- No bull/bear debate.
- No paper broker.
- No real market data.

Verification commands to run:
- `make dev-up`
- `make migrate`
- `make seed-mock`
- `make backtest-mock`
- `make test`
- `curl http://localhost:8000/backtests`, if implemented

Acceptance criteria:
1. `make backtest-mock` prints or stores a `run_id`.
2. Metrics JSON or DB record is generated.
3. Equity curve/portfolio snapshots are stored.
4. Signals, simulated orders, fills, and positions are stored.
5. Same seed and same config produce same result.
6. Tests pass.
7. Live trading remains disabled.

Stop after M2 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M3 Prompt - Strategy engine and technical indicators

```text
You are implementing Project Taurus. Start with Milestone M3 only: Strategy engine and technical indicators.

Prerequisite:
M2 must already be complete and the mock backtest must run.

Goal:
Create reusable technical indicators, a feature computation pipeline, and configurable technical strategies. Backtests should use strategy configs instead of hard-coded strategy logic.

Implement:
1. Technical indicator functions:
   - SMA
   - EMA
   - RSI
   - ATR
   - daily returns
   - rolling volatility
   - volume z-score
2. Feature store schema/table if needed:
   - symbol
   - feature_name
   - feature_value
   - feature_time
   - data_available_time
   - source
   - model_version or feature_version
3. Feature computation service that avoids look-ahead bias.
4. Strategy base interface.
5. Moving-average crossover strategy.
6. Blended-score strategy using a small set of technical features.
7. YAML config support for strategies:
   - `configs/strategies/moving_average_crossover_v1.yaml`
   - `configs/strategies/blended_score_v1.yaml`
8. Signal explanation field, for example:
   - reasons
   - invalidation rules
   - feature snapshot ID
9. Update the backtest runner so it can accept:
   - `STRATEGY=configs/strategies/...`
10. Unit tests for indicators on fixed data.
11. Unit/integration tests that confirm features use only available past data.

Non-goals:
- No LLM analyst agents yet.
- No news or sentiment yet.
- No broker/paper execution.

Verification commands to run:
- `make test`
- `make backtest-mock STRATEGY=configs/strategies/moving_average_crossover_v1.yaml`
- `make backtest-mock STRATEGY=configs/strategies/blended_score_v1.yaml`

Acceptance criteria:
1. Indicator tests pass on fixed input data.
2. Feature rows include `data_available_time`.
3. Strategy outputs explained signals.
4. No look-ahead data is used.
5. Both strategy configs can run through the backtester.
6. Live trading remains disabled.

Stop after M3 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M4 Prompt - Intelligence foundation and analyst reports

```text
You are implementing Project Taurus. Start with Milestone M4 only: Intelligence foundation and analyst reports.

Prerequisite:
M3 must already be complete with strategy features and explained signals.

Goal:
Add the first TradingAgents-inspired analyst layer. Implement mock news/events, sentiment/event scoring, LLM provider abstraction, and four structured analyst agents:
- TechnicalAnalystAgent
- NewsAnalystAgent
- SentimentAnalystAgent
- FundamentalsAnalystAgent

Important:
The default implementation must work with `TAURUS_LLM_PROVIDER=mock`. Do not require OpenAI, LM Studio, API keys, or real news feeds.

Implement:
1. Document/news domain schemas:
   - raw_document
   - news_event
   - sentiment_score
   - analyst_report
2. MockNewsProvider with deterministic mock events mapped to known mock symbols.
3. Basic entity resolver that maps company names and symbols to instruments.
4. Rule-based event scoring fallback:
   - event type
   - sentiment score
   - severity
   - horizon
   - source confidence
5. LLM provider interface:
   - MockLLMProvider
   - LMStudioProvider, optional smoke path only
   - OpenAIProvider, optional smoke path only
6. Pydantic schemas for all LLM/agent outputs.
7. AnalystReport schema with fields similar to:
   - report_id
   - decision_id or run_id
   - symbol
   - agent_name
   - as_of
   - score
   - confidence
   - stance
   - horizon
   - key_points
   - risks
   - source_ids
   - model_version
8. Implement agents:
   - TechnicalAnalystAgent reads technical features/signals.
   - NewsAnalystAgent reads mock news/events.
   - SentimentAnalystAgent reads event/sentiment scores.
   - FundamentalsAnalystAgent returns a mock/neutral report until Screener import is available in M9.
9. Scripts:
   - `make import-mock-news`
   - `make run-analysts-mock SYMBOL=INFY`
   - optional `make llm-smoke`
10. API endpoints:
   - `GET /events`
   - `GET /agent-reports`
   - `GET /agent-reports?symbol=INFY`
11. Tests for:
   - mock news import
   - entity resolution
   - event scoring
   - mock LLM schema validation
   - analyst agent output
   - LLM failure fallback

Non-goals:
- No bull/bear debate yet.
- No trader proposal yet.
- No risk approval.
- No order or paper execution.
- No real web scraping.

Verification commands to run:
- `make import-mock-news`
- `make run-analysts-mock SYMBOL=INFY`
- `make test`
- `curl http://localhost:8000/events`
- `curl http://localhost:8000/agent-reports?symbol=INFY`

Optional only if local LM Studio is running:
- `TAURUS_LLM_PROVIDER=lmstudio TAURUS_LLM_BASE_URL=http://host.docker.internal:1234/v1 make llm-smoke`

Acceptance criteria:
1. Mock news imports successfully.
2. Events map to symbols.
3. Sentiment/event scores are stored.
4. All four analyst agents create valid AnalystReport records for at least one mock symbol.
5. LLM output is schema-validated.
6. LLM failures do not crash the pipeline.
7. No analyst can create or approve an order.
8. Live trading remains disabled.

Stop after M4 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M5 Prompt - Bull/Bear debate and trader proposal

```text
You are implementing Project Taurus. Start with Milestone M5 only: Bull/Bear research debate and trader proposal.

Prerequisite:
M4 must already be complete. Analyst reports must exist for at least one mock symbol.

Goal:
Implement the TradingAgents-style research workflow:
- BullResearcherAgent
- BearResearcherAgent
- ResearchManagerAgent
- ResearchDebateService
- TraderAgent

Important:
The trader creates only a structured proposal. It must not create an order. It must not call a broker. It must not bypass risk.

Implement:
1. Research schemas:
   - Bull thesis
   - Bear thesis
   - Debate round
   - Debate transcript
   - Research manager summary
   - Trader proposal
2. Database tables or persisted records for:
   - debates
   - debate_rounds or transcript entries
   - trader_proposals
3. BullResearcherAgent:
   - reads analyst reports
   - argues strongest positive thesis
   - produces score, confidence, key bullish points, conditions
4. BearResearcherAgent:
   - reads analyst reports
   - argues strongest negative/no-trade thesis
   - produces score, confidence, key bearish points, risk flags
5. ResearchManagerAgent:
   - summarizes bull and bear arguments
   - identifies unresolved uncertainty
   - produces consensus label such as bullish, mild_bullish, neutral, mild_bearish, bearish
6. ResearchDebateService:
   - runs configurable debate rounds, default 2
   - stores transcript and summary
   - deterministic under mock LLM provider
7. TraderAgent:
   - reads analyst reports and debate summary
   - creates structured TraderProposal with:
     - action: BUY, SELL, HOLD, NO_TRADE, REDUCE, EXIT as appropriate
     - confidence
     - horizon
     - requested_position_pct_nav
     - order_type, normally LIMIT for future execution
     - entry_rule
     - stop_loss_pct
     - take_profit_pct
     - reason_summary
     - invalid_if
     - source report IDs and debate ID
8. Scripts:
   - `make debate-mock SYMBOL=INFY`
   - `make trader-proposal-mock SYMBOL=INFY`
9. API endpoints:
   - `GET /debates`
   - `GET /debates/{debate_id}`
   - `GET /trader-proposals`
10. Tests for deterministic mock debate and proposal schema.

Non-goals:
- No risk approval yet.
- No final decision yet.
- No broker or PaperBroker execution.
- No real money path.

Verification commands to run:
- `make run-analysts-mock SYMBOL=INFY`
- `make debate-mock SYMBOL=INFY`
- `make trader-proposal-mock SYMBOL=INFY`
- `make test`
- `curl http://localhost:8000/debates`
- `curl http://localhost:8000/trader-proposals`

Acceptance criteria:
1. Bull thesis is produced.
2. Bear thesis is produced.
3. Research manager summary is produced.
4. Trader proposal is valid structured JSON and persisted.
5. Proposal references analyst report IDs and debate ID.
6. No broker order is created.
7. Mock mode is deterministic.
8. Live trading remains disabled.

Stop after M5 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M6 Prompt - Risk committee, deterministic risk engine, and fund manager approval

```text
You are implementing Project Taurus. Start with Milestone M6 only: Risk committee, deterministic risk engine, and fund manager approval.

Prerequisite:
M5 must already be complete. Trader proposals must exist for at least one mock symbol.

Goal:
Implement risk-review personas, deterministic hard risk checks, audit logs, and final paper approval gate.

Important:
Hard risk rules override all LLM or agent outputs. No order can be created without final approval. Live trading remains disabled.

Implement:
1. Risk schemas:
   - risk_review
   - hard_rule_result
   - risk_check
   - final_decision
2. Risk persona agents:
   - RiskyRiskAgent: argues what could be allowed if reward justifies risk.
   - NeutralRiskAgent: balanced view.
   - SafeRiskAgent: conservative risk view.
3. Deterministic RiskEngine with hard rules:
   - live trading disabled
   - max position percent, default 5 percent NAV
   - max open positions, default 8
   - kill switch blocks all new orders
   - stale data blocks decision
   - severe negative event blocks new long entry
   - unsupported instrument blocks decision
   - missing decision_id/proposal_id blocks decision
4. RiskEngine should be able to:
   - approve
   - reject
   - approve with reduction
5. PortfolioManagerAgent final paper approval gate:
   - reads trader proposal and risk check
   - creates FinalDecision only when allowed
6. Audit log entries for every:
   - risk review
   - hard rule pass/fail/reduction
   - final approval/rejection
7. Scripts:
   - `make risk-review-mock SYMBOL=INFY`
   - `make final-approval-mock SYMBOL=INFY`
8. API endpoints:
   - `GET /risk-checks`
   - `GET /final-decisions`
   - `GET /audit-log`
9. Tests for:
   - oversized position reduction
   - kill switch blocking
   - severe negative event blocking
   - missing proposal blocking
   - final approval only after successful risk check

Non-goals:
- No PaperBroker execution yet.
- No real broker.
- No live trading.

Verification commands to run:
- `make run-analysts-mock SYMBOL=INFY`
- `make debate-mock SYMBOL=INFY`
- `make trader-proposal-mock SYMBOL=INFY`
- `make risk-review-mock SYMBOL=INFY`
- `make final-approval-mock SYMBOL=INFY`
- `make test`
- `curl http://localhost:8000/risk-checks`
- `curl http://localhost:8000/final-decisions`

Acceptance criteria:
1. Risk committee review exists.
2. Hard risk rules are evaluated and persisted.
3. Oversized position requests are reduced or rejected.
4. Kill switch blocks decisions.
5. Severe negative event can block a new long entry.
6. Final decision status is stored.
7. No order can bypass final approval.
8. Live trading remains disabled.

Stop after M6 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M7 Prompt - PaperBroker execution simulator

```text
You are implementing Project Taurus. Start with Milestone M7 only: PaperBroker execution simulator.

Prerequisite:
M6 must already be complete. Final paper decisions must exist and be inspectable.

Goal:
Implement simulated broker execution with orders, fills, positions, cash, costs, and slippage. PaperBroker must accept only approved final decisions.

Implement:
1. BrokerAdapter interface with methods such as:
   - place_order
   - cancel_order
   - get_order
   - list_orders
   - positions
   - cash/margins, paper version only
2. PaperBroker implementation.
3. Order lifecycle states:
   - CREATED
   - ACCEPTED
   - PARTIALLY_FILLED
   - FILLED
   - CANCELLED
   - REJECTED
4. Simulated fill model using available mock/latest candle data.
5. Configurable slippage model.
6. India-cost placeholder model with configurable values:
   - brokerage placeholder
   - exchange/transaction charge placeholder
   - tax/levy placeholder
   - slippage
   Keep values configurable and clearly marked as simulation assumptions.
7. Paper account state:
   - starting cash
   - available cash
   - positions
   - realized P&L
   - unrealized P&L
8. Execution router that receives FinalDecision and sends only approved decisions to PaperBroker.
9. Scripts:
   - `make paper-once-mock SYMBOL=INFY`
10. API endpoints:
   - `GET /paper/orders`
   - `GET /paper/fills`
   - `GET /paper/positions`
   - `GET /paper/account`
11. Tests for:
   - approved decision creates paper order
   - rejected decision does not create order
   - cash updates
   - position updates
   - costs and slippage stored
   - deterministic fill behavior under mock data

Non-goals:
- No external broker integration.
- No Upstox/Zerodha/Dhan/FYERS/OpenAlgo.
- No live trading.

Verification commands to run:
- `make paper-once-mock SYMBOL=INFY`
- `make test`
- `curl http://localhost:8000/paper/orders`
- `curl http://localhost:8000/paper/fills`
- `curl http://localhost:8000/paper/positions`

Acceptance criteria:
1. PaperBroker receives only risk-approved final decisions.
2. Cash and positions update correctly.
3. Costs and slippage are stored.
4. Paper run is deterministic from same seed.
5. Event-risk blocks still apply.
6. Live trading remains disabled.

Stop after M7 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M8 Prompt - Dashboard and observability v1

```text
You are implementing Project Taurus. Start with Milestone M8 only: Dashboard and observability v1.

Prerequisite:
M7 must already be complete. Paper orders, fills, positions, and agent workflow records must exist.

Goal:
Build the first user-visible dashboard and operational observability layer for trading performance, agent workflow, risk, system health, and data freshness.

Implement:
1. Streamlit dashboard app under `apps/dashboard`.
2. Dashboard pages or sections:
   - Overview
   - Portfolio and equity curve
   - Backtests
   - Paper trading orders/fills/positions
   - News/events
   - Analyst reports
   - Bull vs Bear debate
   - Trader proposals
   - Risk checks and hard rule results
   - Final decisions
   - Audit log
   - System health/data freshness
3. Prometheus metrics additions:
   - request count/latency
   - backtest runs
   - analyst report count
   - debate count
   - trader proposal count
   - risk rejection count
   - paper orders/fills count
   - LLM failures
   - agent latency
   - stale data events
4. Grafana dashboard JSONs:
   - Taurus system health
   - Taurus trading overview, basic version acceptable
5. Trace/correlation IDs in logs:
   - run_id
   - decision_id
   - symbol
   - strategy_id
6. Makefile commands:
   - `make dashboard`
7. Update README with dashboard URLs and screenshots instructions if useful.

Non-goals:
- No React dashboard yet.
- No real market data.
- No broker sandbox.
- No live trading.

Verification commands to run:
- `make dev-up`
- `make seed-mock`
- `make import-mock-news`
- `make backtest-mock`
- `make run-analysts-mock SYMBOL=INFY`
- `make debate-mock SYMBOL=INFY`
- `make trader-proposal-mock SYMBOL=INFY`
- `make risk-review-mock SYMBOL=INFY`
- `make final-approval-mock SYMBOL=INFY`
- `make paper-once-mock SYMBOL=INFY`
- `make dashboard`
- `make test`

Manual checks:
- Open Streamlit at `http://localhost:8501`.
- Open Grafana at `http://localhost:3000`.
- Confirm Prometheus metrics are visible.

Acceptance criteria:
1. Dashboard shows portfolio/equity curve.
2. Dashboard shows latest decisions.
3. Dashboard shows analyst reports.
4. Dashboard shows bull vs bear debate.
5. Dashboard shows trader proposal.
6. Dashboard shows risk rule results.
7. Dashboard shows paper orders and fills.
8. Grafana shows service health metrics.
9. JSON logs include correlation IDs.
10. Live trading remains disabled.

Stop after M8 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M9 Prompt - Screener fundamentals import

```text
You are implementing Project Taurus. Start with Milestone M9 only: Screener fundamentals import.

Prerequisite:
M8 must already be complete. Dashboard and analyst workflow must be working with mock fundamentals.

Goal:
Add user-provided Screener CSV import and fundamental scoring. Upgrade FundamentalsAnalystAgent to use imported Screener-derived data when available.

Important user input required:
Before implementation or testing with real data, ask the user to provide a Screener CSV export. Do not scrape Screener. Do not assume Screener has an API. The importer must also work with a small synthetic CSV fixture for automated tests.

Requested Screener columns, if available:
- Symbol
- Company Name
- Market Cap
- Current Price
- Stock P/E
- Book Value
- Dividend Yield
- ROCE
- ROE
- Debt to Equity
- EPS
- Sales growth
- Profit growth
- Promoter holding
- FII holding
- DII holding
- Pledged percentage

Implement:
1. CSV import service for Screener exports.
2. Column mapping layer tolerant of column-name variations.
3. Validation and missing-column report.
4. Fundamental snapshot table:
   - symbol
   - company_name
   - metric_name
   - metric_value
   - reporting_date or import_date
   - data_available_time
   - source_file_hash
5. Fundamental scoring service:
   - quality score
   - valuation score
   - leverage/risk score
   - ownership score, if data exists
6. Upgrade FundamentalsAnalystAgent:
   - uses imported data when available
   - returns neutral/mock report when unavailable
   - clearly states missing data
7. Script and Makefile command:
   - `make import-screener CSV=/path/to/screener.csv`
8. API endpoints:
   - `GET /fundamentals?symbol=INFY`
   - `GET /fundamentals/imports`
9. Dashboard section for fundamentals.
10. Tests using a small fixture CSV with partial fields.

Non-goals:
- No automated Screener scraping.
- No paid data vendor integration.
- No real broker.
- No live trading.

Verification commands to run:
- `make import-screener CSV=tests/fixtures/screener_sample.csv`
- `make run-analysts-mock SYMBOL=INFY`
- `make test`
- `curl "http://localhost:8000/fundamentals?symbol=INFY"`

If the user has provided a real Screener CSV, also test:
- `make import-screener CSV=/absolute/path/to/user_screener_export.csv`

Acceptance criteria:
1. Screener CSV imports without committing the CSV file.
2. Missing columns are reported clearly.
3. Fundamentals map to Taurus instruments.
4. Fundamental scores are stored.
5. FundamentalsAnalystAgent uses imported data when present.
6. Dashboard shows imported fundamentals.
7. Live trading remains disabled.

Stop after M9 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M10 Prompt - Real market data provider

```text
You are implementing Project Taurus. Start with Milestone M10 only: Real market data provider interface.

Prerequisite:
M9 must already be complete. Taurus can run end-to-end with mock data and imported fundamentals.

Goal:
Add a provider interface for real or user-supplied historical OHLCV data while preserving the deterministic mock provider.

Important:
Do not scrape NSE/BSE or any website. Do not require paid credentials. Implement CSV provider first. External vendor/broker providers should be interface stubs or optional adapters only if credentials are available.

User input that may be required:
Ask the user which source they want to use for historical prices. Accept one of:
- CSV historical price files
- broker/data-provider credentials, later
- continue with mock data only

Implement:
1. MarketDataProvider base interface:
   - list_instruments
   - get_historical_candles
   - get_latest_candle or latest quote placeholder
   - provider_name/source metadata
2. CSVMarketDataProvider:
   - reads OHLCV CSVs
   - validates columns
   - maps symbols to instruments
   - records source and data_available_time
3. Provider factory based on config:
   - mock
   - csv
   - future external provider placeholder
4. Import command:
   - `make import-price-csv CSV=/path/to/prices.csv`
   or folder-based import if easier:
   - `make import-price-csv DIR=/path/to/price_csvs`
5. Update backtest runner to select provider/config.
6. Tests with a small price CSV fixture.
7. Dashboard/API displays data source for candles.

Expected CSV columns, flexible names allowed:
- symbol
- date
- open
- high
- low
- close
- volume

Non-goals:
- No live market data streaming.
- No broker sandbox.
- No scraping.
- No live trading.

Verification commands to run:
- `make import-price-csv CSV=tests/fixtures/prices_sample.csv`
- `make backtest-mock`
- `make test`
- `curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"`

Acceptance criteria:
1. Mock provider still works.
2. CSV provider works with fixture data.
3. Real/external provider remains optional and disabled without credentials.
4. Provider records source and `data_available_time`.
5. Backtests can run after CSV import.
6. Live trading remains disabled.

Stop after M10 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M11 Prompt - Continuous paper trading

```text
You are implementing Project Taurus. Start with Milestone M11 only: Continuous paper trading.

Prerequisite:
M10 must already be complete. Taurus can run full one-shot paper trading flow.

Goal:
Run scheduled paper trading using the latest available data. The scheduled loop should execute the full Taurus decision chain and update the dashboard.

Default operating mode:
Daily-candle, after-market-close simulation. Do not implement intraday trading yet unless needed as a placeholder. Use mock or CSV data provider.

User input that may be required:
Ask the user to confirm or override:
- paper trading schedule
- timezone, default Asia/Kolkata
- whether to run only after market close initially, default yes

Implement:
1. Scheduler service using APScheduler, Celery beat, Prefect, or a simple documented scheduler.
2. A single scheduled job that runs:
   - data update or latest data load
   - feature computation
   - strategy signal generation
   - analyst reports
   - bull/bear debate
   - trader proposal
   - risk review
   - final approval
   - PaperBroker execution
   - portfolio snapshot
   - metrics update
3. Run-level records:
   - run_id
   - started_at
   - completed_at
   - status
   - symbols processed
   - errors
4. Makefile commands:
   - `make paper-loop-start`
   - `make paper-loop-once`
5. API endpoints:
   - `GET /runs`
   - `GET /runs/{run_id}`
6. Dashboard page/section for scheduled runs.
7. Tests for one scheduled run using mock data.
8. Failure handling:
   - one symbol failure should not corrupt entire state
   - errors are logged with run_id

Non-goals:
- No Telegram yet.
- No broker sandbox.
- No live trading.
- No intraday/high-frequency loop.

Verification commands to run:
- `make paper-loop-once`
- `make test`
- `curl http://localhost:8000/runs`
- Open dashboard and confirm latest run appears.

Acceptance criteria:
1. Scheduler can trigger full Taurus decision chain.
2. Each run has a `run_id`.
3. Dashboard updates after a run.
4. Failures are logged and do not corrupt existing state.
5. The system remains paper-only.
6. Live trading remains disabled.

Stop after M11 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M12 Prompt - Telegram alerts, replay, backup, and hardening

```text
You are implementing Project Taurus. Start with Milestone M12 only: Telegram alerts, decision replay, backup, and hardening.

Prerequisite:
M11 must already be complete. Continuous paper trading must run locally.

Goal:
Add operational alerting, decision replay, local backups, restore, and hardening checks.

User input required for real Telegram test:
Ask the user to provide these locally in `.env` or `.env.local`, never committed:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Default implementation must still pass tests without real Telegram credentials using a mock Telegram client.

Implement:
1. Alert adapter interface.
2. TelegramAlertAdapter using Telegram Bot API over HTTPS.
3. MockAlertAdapter for tests.
4. Alert events for:
   - paper fill
   - order rejection
   - kill switch activation
   - severe event detected
   - scheduled job failure
   - stale data event
   - risk rejection spike
5. Alert templates with concise messages and IDs:
   - run_id
   - decision_id
   - symbol
   - severity
6. Decision replay command:
   - `make replay-decision DECISION_ID=...`
   It should reconstruct the decision path from stored inputs as much as possible.
7. Backup command:
   - `make backup-local`
8. Restore command or documented restore procedure:
   - `make restore-local BACKUP=...`
9. API endpoints:
   - `POST /alerts/test`, safe mock/test only
   - `GET /replay/{decision_id}`
10. Tests for mock alerts and replay on a known decision.

Non-goals:
- No live trading.
- No broker sandbox unless already done later.
- No secrets committed.

Verification commands to run:
- `make test`
- `make replay-decision DECISION_ID=<known_decision_id>`
- `make backup-local`
- Optional with real credentials only: `make alert-test-telegram`

Acceptance criteria:
1. Mock Telegram alert tests pass without credentials.
2. Real Telegram smoke test works when credentials are provided.
3. Alerts fire for the required event types.
4. Decision replay works for a stored mock decision.
5. Backup can be created locally.
6. Restore procedure is documented or implemented.
7. Live trading remains disabled.

Stop after M12 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M13 Prompt - Broker sandbox adapter

```text
You are implementing Project Taurus. Start with Milestone M13 only: Broker sandbox adapter.

Prerequisite:
M12 must already be complete. Taurus must be stable in paper mode with alerts and replay.

Goal:
Add the first external broker sandbox adapter without enabling live trading. Recommended first target is Upstox Sandbox. OpenAlgo may be supported later or as an optional adapter if the user chooses it.

User input required:
Ask the user to provide sandbox credentials locally in `.env` or `.env.local`, never committed:
- UPSTOX_CLIENT_ID
- UPSTOX_CLIENT_SECRET
- UPSTOX_REDIRECT_URI
- any sandbox access token or OAuth setup details required by the current Upstox flow

Important:
1. PaperBroker remains the default.
2. Live trading remains disabled.
3. Sandbox adapter must be clearly separated from live broker adapter.
4. No real-money orders.
5. If sandbox credentials are missing, tests must still pass by using mocks.

Implement:
1. BrokerAdapter-compatible UpstoxSandboxBroker.
2. Credential loading from environment only.
3. Safe sandbox smoke test command:
   - `make broker-sandbox-smoke`
4. Mapping from Taurus order schema to sandbox order payload.
5. Sandbox-only order lifecycle handling where supported.
6. Error handling and structured logs for broker API responses.
7. Tests using mocked HTTP responses.
8. Documentation explaining:
   - how to configure sandbox credentials
   - how to run smoke test
   - why live trading is still disabled

Non-goals:
- No live broker adapter.
- No real-money order placement.
- No automatic switch from paper to sandbox.
- No high-frequency trading.

Verification commands to run:
- `make test`
- If credentials are available: `make broker-sandbox-smoke`
- Confirm `.env` is not committed.

Acceptance criteria:
1. Sandbox credentials are loaded only from local environment.
2. Mocked sandbox adapter tests pass without credentials.
3. Sandbox smoke test works when credentials are available and supported.
4. Broker adapter conforms to BrokerAdapter interface.
5. PaperBroker remains default.
6. Live trading remains disabled.

Stop after M13 acceptance criteria pass and summarize files changed, commands run, test results, and any manual sandbox steps.
```

---

# M14 Prompt - Live-readiness gate

```text
You are implementing Project Taurus. Start with Milestone M14 only: Live-readiness gate.

Prerequisite:
M13 must already be complete if broker sandbox testing is desired. Paper mode must remain stable.

Goal:
Prepare safety, compliance, and operational gates for future live trading. This milestone still must not place live orders.

Important:
Do not enable live trading. Do not implement a live broker order path that can be accidentally used. The goal is readiness checks and guardrails only.

Implement:
1. Live readiness checklist module.
2. Preflight checks for:
   - LIVE_TRADING_ENABLED flag
   - broker provider
   - broker credentials presence
   - order tagging config placeholder
   - risk config completeness
   - kill switch availability
   - audit logging availability
   - dashboard/observability availability
   - account/position reconciliation placeholder
   - max order rate config placeholder
   - max position size
   - max daily loss
3. Manual sign-off gate:
   - require a local uncommitted sign-off file or explicit runtime flag before any future live mode could proceed
   - document that this is not sufficient by itself for real trading
4. Safety tests proving:
   - default config blocks live trading
   - missing sign-off blocks live trading
   - failed preflight blocks live trading
   - PaperBroker remains default
5. API endpoint or CLI command:
   - `make live-readiness-check`
   - `GET /live-readiness`
6. Documentation:
   - safety model
   - what remains before live trading
   - broker/compliance notes placeholder

Non-goals:
- No live orders.
- No automatic activation of live mode.
- No legal/compliance guarantee.
- No financial advice claims.

Verification commands to run:
- `make live-readiness-check`
- `make test`
- `curl http://localhost:8000/live-readiness`, if implemented

Acceptance criteria:
1. `LIVE_TRADING_ENABLED=false` remains default.
2. Live mode requires explicit config and manual sign-off.
3. Failed preflight blocks live path.
4. Tests prove live trading cannot happen by default.
5. No live orders are placed.
6. Paper trading remains unaffected.

Stop after M14 acceptance criteria pass and summarize files changed, commands run, and test results.
```

---

# M15 Prompt - Taurus MVP release

```text
You are implementing Project Taurus. Start with Milestone M15 only: Taurus MVP release hardening and final verification.

Prerequisite:
M0 through M14 must be complete or explicitly marked not applicable. Taurus must run end-to-end in paper mode.

Goal:
Finalize the observable paper-trading MVP. This is not a new-feature milestone unless small fixes are needed. It is a release-hardening, verification, documentation, and cleanup milestone.

Implement:
1. End-to-end smoke command, for example:
   - `make taurus-smoke`
2. Final local runbook:
   - setup
   - start services
   - seed mock data
   - import mock news
   - run backtest
   - run analyst workflow
   - run debate
   - run trader proposal
   - run risk review
   - run final approval
   - run paper order
   - open dashboards
   - backup
   - replay decision
3. Documentation of config and secrets.
4. Documentation of known limitations.
5. Documentation of current paper-trading assumptions:
   - costs
   - slippage
   - fills
   - timing
   - data freshness
6. Ensure all Makefile commands are consistent.
7. Clean up dead code and TODOs where safe.
8. Add final tests for the end-to-end paper flow if not already covered.
9. Export a sample report or dashboard screenshot instructions, if practical.

Non-goals:
- No new broker live integration.
- No real-money trading.
- No large refactor that risks destabilizing the MVP unless required by failing tests.

Final verification checklist to run:
- `make setup`
- `make dev-up`
- `make migrate`
- `make seed-mock`
- `make import-mock-news`
- `make backtest-mock`
- `make run-analysts-mock SYMBOL=INFY`
- `make debate-mock SYMBOL=INFY`
- `make trader-proposal-mock SYMBOL=INFY`
- `make risk-review-mock SYMBOL=INFY`
- `make final-approval-mock SYMBOL=INFY`
- `make paper-once-mock SYMBOL=INFY`
- `make taurus-smoke`
- `make test`
- `make dashboard`

Acceptance criteria:
1. Taurus can run end-to-end with mock data.
2. Taurus can backtest.
3. Taurus can generate analyst reports.
4. Taurus can run bull/bear debate.
5. Taurus can generate trader proposal.
6. Taurus can run risk review and final approval.
7. Taurus can paper trade.
8. Dashboard shows performance, decisions, debate, risk, orders, events, and health.
9. Decision replay works for at least one stored decision.
10. Backup works.
11. Live trading remains disabled.
12. README and runbook are up to date.

Stop after M15 acceptance criteria pass and provide a release summary:
- final capabilities
- how to run locally
- what is still mock-only
- what inputs are needed for extended paper trading
- next recommended milestones after MVP
```

---

# Optional follow-up prompt after each milestone: review and cleanup

Use this only after Codex says the milestone is complete.

```text
Review the milestone you just implemented for Project Taurus.

Tasks:
1. Re-read the milestone acceptance criteria from docs/TAURUS_MVP_SPEC_v0_3.md.
2. Run the documented verification commands again if possible.
3. Check for secrets or accidental credentials.
4. Check that live trading remains disabled.
5. Check for missing tests around failure cases.
6. Check whether any files from later milestones were implemented prematurely.
7. Produce a concise review report:
   - acceptance criteria status
   - failing or skipped checks
   - risks
   - recommended fixes before moving to next milestone

Do not start the next milestone.
```

---

# Optional prompt when tests fail

```text
The previous Taurus milestone has failing tests or failing verification commands. Do not implement new features.

Fix only the failures related to the current milestone.

Steps:
1. Inspect the failing command output.
2. Identify the smallest safe fix.
3. Apply the fix.
4. Re-run the failing tests/commands.
5. Summarize root cause and files changed.

Do not proceed to the next milestone.
Do not enable live trading.
```

---

# Optional prompt to create/update AGENTS.md

Use this once near the beginning of the repo.

```text
Create or update AGENTS.md for Project Taurus.

The file should give durable instructions for coding agents working in this repository:
1. Project purpose: observable, paper-trading-first algo trading MVP for Indian cash equities.
2. Live trading disabled by default.
3. Never commit secrets.
4. Implement one milestone at a time.
5. Add tests for meaningful behavior.
6. Use deterministic mock data by default.
7. LLM agents may analyze and propose but must never directly place orders.
8. PaperBroker remains default until explicitly changed in a future approved milestone.
9. Run verification commands before claiming completion.
10. Summarize files changed, commands run, and assumptions.

Do not implement feature code in this prompt unless required to update AGENTS.md references.
```
