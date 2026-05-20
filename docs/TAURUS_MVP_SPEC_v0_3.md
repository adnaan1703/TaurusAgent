# Project Taurus - MVP Specification v0.3

Version: 0.3 draft  
Date: 2026-05-18  
Project name: Taurus  
Default mode: paper trading and backtesting only  
Live trading default: disabled  
Initial market: Indian listed cash equities, NSE first  
Initial universe: NIFTY 100  
Initial runtime: local MacBook Pro  

---

## 1. Purpose

Taurus is an observable, paper-trading-first autonomous algo trading system for Indian cash equities.

The system must allow us to:

1. Backtest strategies on mock and later real historical data.
2. Paper trade with deterministic and observable behavior.
3. Ingest technical, fundamental, news, filings, and sentiment information.
4. Use a TradingAgents-inspired multi-agent research workflow.
5. Keep LLMs in the research and explanation layer, not the direct execution layer.
6. Provide dashboards, metrics, logs, alerts, decision replay, and audit trails.
7. Keep real-money trading disabled until a later live-readiness gate is explicitly approved.

The MVP must be usable milestone by milestone. Each milestone must be independently testable, observable, and reviewable before proceeding.

---

## 2. Locked project decisions

```text
Project name: Taurus
Initial universe: NIFTY 100
Initial timeframe: Daily candles first
Later timeframe: 15-minute candles after daily version is stable
Initial strategy style: Blended technical momentum + risk filters
Initial paper capital: INR 10,00,000
Max position size: 5 percent of paper capital per stock
Max open positions: 8
Initial broker mode: Internal PaperBroker
Broker integration: Deferred until after paper-trading MVP release
Fundamentals source for MVP: Screener CSV export, explicitly requested from user in M9
News/sentiment: Included in first MVP, not deferred
TradingAgents-style debate: Explicitly included from M5 onward
Alerting: Telegram
Initial deployment: Local machine
Local machine: MacBook Pro, Apple Silicon, 1 TB SSD, 64 GB unified memory
LLM options: mock provider, LM Studio local server, or OpenAI API
Dashboard: Streamlit trading dashboard + Grafana/Prometheus system dashboard
Live trading: disabled by default
```

---

## 3. TradingAgents methodology adopted in Taurus

The uploaded paper proposes a simulated trading-firm workflow with specialized analyst agents, bull/bear researchers, a trader, risk managers, and fund-manager approval. Taurus v0.3 explicitly incorporates this methodology, adapted for a safer paper-trading-first Indian equities MVP.

### 3.1 Paper concept to Taurus implementation map

| Paper concept | Taurus implementation | Milestone |
|---|---|---|
| Fundamentals Analyst | `FundamentalsAnalystAgent`, initially mock/Screener CSV based | M4, M9 |
| Sentiment Analyst | `SentimentAnalystAgent`, using mock news first, then real sources | M4 |
| News Analyst | `NewsAnalystAgent`, classifies filings/news/events | M4 |
| Technical Analyst | `TechnicalAnalystAgent`, reads indicator features from strategy engine | M4 |
| Bull Researcher | `BullResearcherAgent`, argues strongest positive thesis | M5 |
| Bear Researcher | `BearResearcherAgent`, argues strongest negative thesis | M5 |
| Research debate | `ResearchDebateService`, runs fixed-round debate and stores transcript | M5 |
| Trader | `TraderAgent`, creates structured trade proposal only | M5 |
| Risk managers | `RiskyRiskAgent`, `NeutralRiskAgent`, `SafeRiskAgent`, plus deterministic `RiskEngine` | M6 |
| Fund Manager | `PortfolioManagerAgent`, final paper approval gate | M6 |
| Structured communication | Pydantic schemas and database records, not long chat history | M4-M6 |
| Shared environment state | `DecisionContext`, `FeatureSnapshot`, `AgentRun`, `AuditLog` | M4-M6 |
| Explainability | Every decision stores analyst reports, debate, proposal, risk review, final reason | M5-M8 |

### 3.2 Key adaptation for safety

Taurus does not let an LLM place broker orders. The LLM agents can produce reports and proposals. A deterministic risk engine and broker adapter must still approve and execute.

```text
Data -> Analyst reports -> Bull/Bear debate -> Trader proposal
     -> Risk committee review -> Deterministic risk checks
     -> Portfolio manager approval -> PaperBroker order
```

No active MVP milestone may contain a real-money order path.

---

## 4. Agent workflow

### 4.1 Analyst team

The analyst team creates independent structured reports for a symbol and date.

Required agents:

```text
TechnicalAnalystAgent
NewsAnalystAgent
SentimentAnalystAgent
FundamentalsAnalystAgent
```

Each analyst must return an `AnalystReport`.

```json
{
  "report_id": "ar_...",
  "decision_id": "dec_...",
  "symbol": "INFY",
  "agent_name": "TechnicalAnalystAgent",
  "as_of": "2026-05-18T15:30:00+05:30",
  "score": 0.62,
  "confidence": 0.70,
  "stance": "bullish",
  "horizon": "3-10 trading days",
  "key_points": ["close above 20D SMA", "volume above 20D average"],
  "risks": ["near resistance zone"],
  "source_ids": ["feature_snapshot_123"],
  "model_version": "mock_v1"
}
```

Rules:

1. Analysts do not create orders.
2. Analysts do not see each other's full chain of reasoning.
3. Analysts write structured reports into the database.
4. Reports must be schema-validated.
5. Reports must contain source references.

### 4.2 Bull/Bear researcher debate

The research team reads analyst reports and creates a balanced debate.

Required agents:

```text
BullResearcherAgent
BearResearcherAgent
ResearchManagerAgent
```

The bull researcher must argue the strongest case for a long/hold decision. The bear researcher must argue the strongest case for no-trade/reduce/avoid. The research manager summarizes the debate and highlights unresolved uncertainty.

Required output:

```json
{
  "debate_id": "deb_...",
  "decision_id": "dec_...",
  "symbol": "INFY",
  "rounds": 2,
  "bull_score": 0.66,
  "bear_score": 0.41,
  "consensus": "mild_bullish",
  "open_questions": ["sentiment improvement may be short-lived"],
  "bull_thesis": ["momentum improving", "positive sector trend"],
  "bear_thesis": ["valuation not cheap", "global IT demand risk"],
  "research_manager_summary": "Long setup is acceptable only with tight risk cap and no severe negative news."
}
```

Rules:

1. Debate rounds must be configurable, default 2.
2. Debate output must be saved and visible in the dashboard.
3. Debate must be deterministic in mock mode.
4. Debate must not approve trades by itself.

### 4.3 Trader proposal

The trader reads analyst reports and the debate summary and proposes a trade intent.

Required output:

```json
{
  "proposal_id": "tp_...",
  "decision_id": "dec_...",
  "symbol": "INFY",
  "action": "BUY",
  "confidence": 0.61,
  "horizon": "3-10 trading days",
  "requested_position_pct_nav": 3.0,
  "order_type": "LIMIT",
  "entry_rule": "next_open_or_better_limit",
  "stop_loss_pct": 2.0,
  "take_profit_pct": 4.0,
  "reason_summary": "Technical momentum and mild positive sentiment support a small long position.",
  "invalid_if": ["fresh severe negative event", "spread above threshold", "price below 20D SMA"]
}
```

Rules:

1. Trader creates proposal only.
2. Trader cannot create a broker order.
3. Requested position may be reduced or rejected by risk.
4. All proposals must reference analyst reports and debate IDs.

### 4.4 Risk committee and deterministic risk engine

Risk review has two layers.

First, LLM/rule-assisted risk reviewers provide perspectives:

```text
RiskyRiskAgent: argues what could be allowed if reward justifies risk
NeutralRiskAgent: balanced risk assessment
SafeRiskAgent: conservative risk assessment
```

Second, deterministic `RiskEngine` enforces hard rules.

Hard rules override all LLM outputs.

Examples:

```text
- live trading disabled
- max position 5 percent NAV
- max open positions 8
- max daily loss threshold
- no stale data
- no severe negative event long entry
- no order during kill switch
- no unsupported instrument
- no order without decision_id, proposal_id, and risk_check_id
```

Required output:

```json
{
  "risk_check_id": "risk_...",
  "decision_id": "dec_...",
  "proposal_id": "tp_...",
  "status": "APPROVED_WITH_REDUCTION",
  "approved_position_pct_nav": 2.0,
  "hard_rule_results": [
    {"rule": "max_position_pct", "status": "reduced", "details": "3.0 reduced to 2.0"},
    {"rule": "severe_event_block", "status": "passed"}
  ],
  "risk_committee_summary": "Allowed only as small paper position."
}
```

### 4.5 Portfolio manager approval

The final paper approval gate creates a `FinalDecision`.

Required output:

```json
{
  "final_decision_id": "fd_...",
  "decision_id": "dec_...",
  "symbol": "INFY",
  "final_action": "BUY",
  "status": "APPROVED_FOR_PAPER",
  "approved_quantity": 10,
  "approved_position_pct_nav": 2.0,
  "reason": "Approved after debate and hard risk checks."
}
```

Only after this record exists may PaperBroker receive an order.

---

## 5. Observability requirements for agent workflow

Taurus must make the agent process visible, not hidden.

Dashboard panels required from M8 onward:

```text
Latest decisions
Analyst report table
Bull vs Bear debate table
Trader proposals
Risk committee reviews
Hard risk rule results
Final decision status
Paper orders and fills
Backtest vs paper performance
News/event timeline
LLM status and failures
```

Every decision must be traceable:

```text
decision_id
run_id
symbol
strategy_id
model_version
feature_snapshot_id
analyst_report_ids
debate_id
proposal_id
risk_check_id
final_decision_id
order_id
fill_id
```

---

## 6. Core architecture

```text
                            +--------------------------+
                            | Streamlit Dashboard      |
                            | Grafana Dashboards       |
                            +-------------+------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Observability: Prometheus metrics, JSON logs, OpenTelemetry-style trace IDs       |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Taurus API / Control Plane: health, configs, kill switch, reports, replay         |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Data Layer: prices, features, fundamentals, news, filings, sentiment              |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Analyst Team: technical, fundamental, news, sentiment                             |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Research Team: bull researcher, bear researcher, research manager                 |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Trader Proposal: structured trade intent only                                     |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Risk Committee + Deterministic Risk Engine                                        |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Portfolio Manager Approval                                                       |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| Execution Router: PaperBroker first, broker sandbox later                         |
+-----------------------------------------------------------------------------------+
```

---

## 7. Required local setup

Required before M0:

```text
git
python3
node/npm already installed but not required for early Streamlit MVP
Docker Desktop
Homebrew
uv
make
jq
```

Optional later:

```text
LM Studio
OpenAI API key
Telegram bot token/chat ID
Upstox Sandbox credentials are optional post-MVP only
Screener CSV export
```

---

## 8. Configuration defaults

`.env.example` must include safe defaults.

```bash
TAURUS_ENV=local
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
TAURUS_UNIVERSE=NIFTY_100
TAURUS_TIMEFRAME=1d
TAURUS_INITIAL_CAPITAL_INR=1000000
TAURUS_MAX_POSITION_PCT=5
TAURUS_MAX_OPEN_POSITIONS=8
TAURUS_LLM_PROVIDER=mock
TAURUS_LLM_BASE_URL=
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
BROKER_PROVIDER=paper
```

Secrets must never be committed.

---

## 9. Milestone overview

| Milestone | Name | Main outcome | Requires user input? | API keys? |
|---|---|---|---|---|
| M0 | Project foundation | Repo, config, Docker, health, metrics | No | No |
| M1 | Mock data and database | Instruments, candles, deterministic seed data | No | No |
| M2 | Backtesting skeleton | First deterministic mock backtest | No | No |
| M3 | Strategy and indicators | Technical features and blended score strategy | No | No |
| M4 | Intelligence and analyst reports | News/sentiment/LLM foundation + analyst agents | Optional sample news | Optional |
| M5 | Bull/Bear debate and trader proposal | Research debate + structured trade proposal | No | Optional LLM |
| M6 | Risk committee and fund manager | Risk personas, hard risk checks, final approval | No | No |
| M7 | PaperBroker | Simulated orders, fills, costs, slippage | No | No |
| M8 | Dashboard and observability v1 | Agent workflow, P&L, risk, metrics dashboard | No | No |
| M9 | Screener fundamentals import | User-provided fundamentals and scoring | Screener CSV required | No |
| M10 | Real market data provider | Real/user-supplied OHLCV provider interface | Price source decision | Maybe |
| M11 | Continuous paper trading | Scheduled paper loop using latest data | Risk/date settings | Maybe |
| M12 | Telegram alerts and replay | Alerts, decision replay, backup, hardening | Telegram token/chat ID | Optional |
| M13 | Paper-trading MVP release | Stable observable paper-trading MVP | Optional real CSV/data source | No |
| M14 | Upstox sandbox adapter | Deferred post-MVP sandbox payload validation | Sandbox access token | Yes |
| M15 | Upstox production readiness | Deferred production safety gate | Broker/compliance details | Yes, no live orders |

---

# M0 - Project foundation

## Objective

Create repository scaffold, local development environment, configuration, health endpoints, metrics endpoint, logging, and tests.

## How to build

1. Create repository structure.
2. Add `pyproject.toml`, `README.md`, `.env.example`, `Makefile`.
3. Add FastAPI app with `/health`, `/ready`, `/metrics`.
4. Add Docker Compose for Postgres, Redis, Prometheus, and Grafana.
5. Add JSON logging.
6. Add pytest setup.
7. Ensure live trading is impossible.

## Code changes

```text
README.md
pyproject.toml
Makefile
.env.example
docker-compose.yml
apps/api/main.py
apps/api/routes_health.py
packages/taurus_core/config.py
packages/taurus_core/logging.py
packages/taurus_core/observability/metrics.py
infra/prometheus/prometheus.yml
tests/unit/test_health.py
```

## Information required from user

None.

## Verification

```text
make setup
make dev-up
make test
make api
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

## Acceptance criteria

1. Tests pass.
2. API responds to health endpoints.
3. Metrics endpoint exists.
4. Docker Compose starts core services.
5. No API keys are required.
6. Live trading is disabled and cannot be accidentally enabled.

---

# M1 - Mock data and database foundation

## Objective

Create domain models, database schema, repositories, and deterministic mock OHLCV data.

## How to build

1. Add SQLAlchemy/SQLModel models.
2. Add migrations.
3. Implement instruments, candles, portfolio snapshots, and audit tables.
4. Add deterministic mock market data provider.
5. Add seed script.
6. Add API endpoints to inspect instruments and candles.

## Code changes

```text
packages/taurus_core/domain/instruments.py
packages/taurus_core/domain/market_data.py
packages/taurus_core/db/session.py
packages/taurus_core/db/models.py
packages/taurus_core/db/repositories.py
packages/taurus_core/data/providers/mock_market_data.py
scripts/seed_mock_data.py
tests/unit/test_mock_market_data.py
```

## Information required from user

None.

## Verification

```text
make dev-up
make migrate
make seed-mock
make test
curl http://localhost:8000/data/instruments
```

## Acceptance criteria

1. At least 10 mock instruments exist.
2. Each instrument has at least 252 daily candles.
3. Mock data is deterministic from the same seed.
4. API returns instruments and candles.

---

# M2 - Backtesting skeleton

## Objective

Run the first deterministic mock backtest and store signals, orders, fills, positions, portfolio snapshots, and metrics.

## How to build

1. Add event-driven backtest loop.
2. Add simple mock momentum strategy.
3. Add cost/slippage model.
4. Store backtest run objects.
5. Compute basic metrics.

## Code changes

```text
packages/taurus_core/backtesting/engine.py
packages/taurus_core/backtesting/context.py
packages/taurus_core/backtesting/metrics.py
packages/taurus_core/strategies/mock_momentum.py
scripts/run_backtest.py
tests/unit/test_backtest_engine.py
```

## Information required from user

None.

## Verification

```text
make backtest-mock
make test
```

## Acceptance criteria

1. Backtest prints a `run_id`.
2. Metrics JSON is generated.
3. Equity curve is stored.
4. Signals/orders/fills/positions are stored.
5. Same seed gives same result.

---

# M3 - Strategy engine and technical indicators

## Objective

Implement reusable technical indicators, feature store, and configurable technical strategies.

## How to build

1. Implement SMA, EMA, RSI, ATR, returns, volatility, volume z-score.
2. Add feature computation pipeline.
3. Add moving-average crossover strategy.
4. Add blended-score strategy.
5. Store feature values with `data_available_time`.
6. Add signal explanations.

## Code changes

```text
packages/taurus_core/features/technical.py
packages/taurus_core/features/store.py
packages/taurus_core/strategies/base.py
packages/taurus_core/strategies/moving_average_crossover.py
packages/taurus_core/strategies/blended_score.py
configs/strategies/moving_average_crossover_v1.yaml
configs/strategies/blended_score_v1.yaml
tests/unit/test_technical_indicators.py
```

## Information required from user

None.

## Verification

```text
make test
make backtest-mock STRATEGY=configs/strategies/moving_average_crossover_v1.yaml
make backtest-mock STRATEGY=configs/strategies/blended_score_v1.yaml
```

## Acceptance criteria

1. Indicator tests pass on fixed data.
2. Strategies produce explained signals.
3. Feature rows include `data_available_time`.
4. No look-ahead data is used.

---

# M4 - Intelligence foundation and analyst reports

## Objective

Implement news, filing, sentiment, LLM provider abstraction, and the four analyst agents.

## How to build

1. Add document/news provider interfaces.
2. Add `MockNewsProvider`.
3. Add raw document, event, sentiment, and analyst report tables.
4. Add entity resolver for symbols/company names.
5. Add deterministic rule-based fallback event scoring.
6. Add LLM provider interface with mock, LM Studio, and OpenAI implementations.
7. Add Pydantic schemas for LLM outputs.
8. Implement analyst agents:
   - `TechnicalAnalystAgent`
   - `NewsAnalystAgent`
   - `SentimentAnalystAgent`
   - `FundamentalsAnalystAgent`
9. Store `AnalystReport` records.

## Code changes

```text
packages/taurus_core/intelligence/documents.py
packages/taurus_core/intelligence/news_provider.py
packages/taurus_core/intelligence/mock_news_provider.py
packages/taurus_core/intelligence/entity_resolver.py
packages/taurus_core/intelligence/event_scoring.py
packages/taurus_core/llm/base.py
packages/taurus_core/llm/mock_provider.py
packages/taurus_core/llm/lmstudio_provider.py
packages/taurus_core/llm/openai_provider.py
packages/taurus_core/agents/schemas.py
packages/taurus_core/agents/technical_analyst.py
packages/taurus_core/agents/news_analyst.py
packages/taurus_core/agents/sentiment_analyst.py
packages/taurus_core/agents/fundamentals_analyst.py
scripts/import_mock_news.py
scripts/run_analysts.py
tests/unit/test_llm_provider.py
tests/unit/test_analyst_agents.py
```

## Information required from user

Optional:

```text
Sample news/events CSV or JSON
LM Studio model name if testing local LLM
OpenAI API key if testing OpenAI provider
Allowed real news/source list for later
```

Default implementation must work without any of these.

## Verification

```text
make import-mock-news
make run-analysts-mock SYMBOL=INFY
make test
curl http://localhost:8000/events
curl http://localhost:8000/agent-reports
```

Optional LM Studio smoke test:

```text
TAURUS_LLM_PROVIDER=lmstudio TAURUS_LLM_BASE_URL=http://localhost:1234/v1 make llm-smoke
```

## Acceptance criteria

1. Mock news imports successfully.
2. Events map to symbols.
3. Sentiment/event scores are stored.
4. Analyst reports are created for at least one mock symbol.
5. LLM output is schema-validated.
6. LLM failures do not crash the pipeline.
7. No analyst can create or approve an order.

---

# M5 - Bull/Bear research debate and trader proposal

## Objective

Implement the TradingAgents-style bull/bear research debate and structured trader proposal stage.

## How to build

1. Add `BullResearcherAgent`.
2. Add `BearResearcherAgent`.
3. Add `ResearchManagerAgent`.
4. Add `ResearchDebateService`.
5. Add configurable debate rounds, default 2.
6. Add `TraderAgent`.
7. Store debate transcript, debate summary, and trader proposal.
8. Ensure trader proposal is not an order.
9. Add tests for deterministic mock-mode debate.

## Code changes

```text
packages/taurus_core/agents/bull_researcher.py
packages/taurus_core/agents/bear_researcher.py
packages/taurus_core/agents/research_manager.py
packages/taurus_core/agents/trader_agent.py
packages/taurus_core/research/debate_service.py
packages/taurus_core/research/schemas.py
scripts/run_research_debate.py
scripts/run_trader_proposal.py
tests/unit/test_research_debate.py
tests/unit/test_trader_agent.py
```

## Information required from user

None required. Optional LLM configuration may be used, but mock provider must work.

## Verification

```text
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make test
curl http://localhost:8000/debates
curl http://localhost:8000/trader-proposals
```

## Acceptance criteria

1. Bull and bear reports are produced.
2. Research manager summary is produced.
3. Trader proposal is produced as structured JSON.
4. Proposal contains action, confidence, horizon, requested position, stop, take-profit, invalidation rules.
5. Proposal references analyst report IDs and debate ID.
6. No broker order is created in this milestone.
7. Mock mode is deterministic.

---

# M6 - Risk committee, deterministic risk engine, and fund manager approval

## Objective

Implement risk personas, deterministic hard risk checks, audit trail, and final paper approval gate.

## How to build

1. Add risk review agents:
   - `RiskyRiskAgent`
   - `NeutralRiskAgent`
   - `SafeRiskAgent`
2. Add deterministic `RiskEngine`.
3. Add hard risk rules.
4. Add event-risk block for severe negative news.
5. Add `PortfolioManagerAgent` final paper approval gate.
6. Add audit log for every pass/reject/reduce decision.
7. Ensure no order can be created without final approval.

## Code changes

```text
packages/taurus_core/agents/risky_risk_agent.py
packages/taurus_core/agents/neutral_risk_agent.py
packages/taurus_core/agents/safe_risk_agent.py
packages/taurus_core/agents/portfolio_manager_agent.py
packages/taurus_core/risk/engine.py
packages/taurus_core/risk/rules.py
packages/taurus_core/risk/schemas.py
packages/taurus_core/audit/audit_log.py
scripts/run_risk_review.py
scripts/run_final_approval.py
tests/unit/test_risk_engine.py
tests/unit/test_portfolio_manager.py
```

## Information required from user

None.

## Verification

```text
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make test
```

## Acceptance criteria

1. Risk committee review exists.
2. Hard risk rules are evaluated and stored.
3. Oversized position requests are reduced or rejected.
4. Kill switch blocks orders.
5. Severe negative event can block a new long entry.
6. Final decision status is stored.
7. No order can bypass final approval.

---

# M7 - PaperBroker execution simulator

## Objective

Implement simulated broker execution with orders, fills, positions, cash, costs, and slippage.

## How to build

1. Define `BrokerAdapter` interface.
2. Implement `PaperBroker`.
3. Add order lifecycle states.
4. Add partial fills.
5. Add costs and slippage model.
6. Add paper-once and paper-loop scripts.
7. Only accept final approved decisions.

## Code changes

```text
packages/taurus_core/brokers/base.py
packages/taurus_core/brokers/paper_broker.py
packages/taurus_core/execution/order_router.py
packages/taurus_core/execution/slippage.py
packages/taurus_core/execution/costs.py
scripts/run_paper_once.py
scripts/run_paper_loop.py
tests/unit/test_paper_broker.py
```

## Information required from user

None.

## Verification

```text
make paper-once-mock SYMBOL=INFY
make test
```

## Acceptance criteria

1. PaperBroker receives only risk-approved final decisions.
2. Cash and positions update correctly.
3. Costs and slippage are stored.
4. Paper run is deterministic from same seed.
5. Event-risk blocks apply in paper mode.

---

# M8 - Dashboard and observability v1

## Objective

Build the first dashboard and observability layer for trading performance, agent workflow, system health, and data freshness.

## How to build

1. Add Streamlit dashboard.
2. Add pages for portfolio, backtests, paper trading, orders, positions, news/events, analyst reports, debate, risk, and final decisions.
3. Add Prometheus metrics.
4. Add Grafana dashboards.
5. Add JSON logs with trace IDs.
6. Add metrics for LLM failures and agent latency.

## Code changes

```text
apps/dashboard/main.py
apps/dashboard/pages/portfolio.py
apps/dashboard/pages/backtests.py
apps/dashboard/pages/paper_trading.py
apps/dashboard/pages/orders.py
apps/dashboard/pages/events.py
apps/dashboard/pages/agent_workflow.py
apps/dashboard/pages/risk.py
packages/taurus_core/observability/metrics.py
packages/taurus_core/observability/tracing.py
infra/grafana/dashboards/taurus-system.json
infra/grafana/dashboards/taurus-trading.json
```

## Information required from user

None.

## Verification

```text
make dev-up
make dashboard
make backtest-mock
make paper-once-mock SYMBOL=INFY
```

Open:

```text
http://localhost:8501
http://localhost:3000
```

## Acceptance criteria

1. Dashboard shows portfolio/equity curve.
2. Dashboard shows latest decisions.
3. Dashboard shows analyst reports.
4. Dashboard shows bull vs bear debate.
5. Dashboard shows trader proposal.
6. Dashboard shows risk rule results.
7. Dashboard shows paper orders/fills.
8. Grafana shows service health metrics.

---

# M9 - Screener fundamentals import

## Objective

Import user-provided Screener CSV fundamentals and add fundamental scoring.

## How to build

1. Add CSV import command.
2. Validate required columns.
3. Map company names/symbols to Taurus instruments.
4. Store fundamental snapshots with `data_available_time`.
5. Implement fundamental quality/valuation score.
6. Upgrade `FundamentalsAnalystAgent` to read Screener-derived features.

## Information required from user

At this milestone, explicitly ask the user to provide a Screener CSV export.

Requested columns if available:

```text
Symbol
Company Name
Market Cap
Current Price
Stock P/E
Book Value
Dividend Yield
ROCE
ROE
Debt to Equity
EPS
Sales growth
Profit growth
Promoter holding
FII holding
DII holding
Pledged percentage
```

The importer must accept partial data and clearly report missing fields.

## Verification

```text
make import-screener CSV=/path/to/screener.csv
make run-analysts-mock SYMBOL=INFY
make test
```

## Acceptance criteria

1. Screener CSV imports without committing the file.
2. Missing columns are reported clearly.
3. Fundamentals are mapped to instruments.
4. Fundamental score is stored.
5. Fundamentals analyst uses imported data.

---

# M10 - Real market data provider

## Objective

Add a provider interface for real/user-supplied historical OHLCV data while preserving mock data support.

## Information required from user

One of:

```text
CSV historical price files
Broker/data-provider credentials
Decision to use a specific market data vendor
```

## Acceptance criteria

1. Mock provider still works.
2. CSV provider works.
3. Real provider is optional and disabled without credentials.
4. Provider records source and `data_available_time`.

---

# M11 - Continuous paper trading

## Objective

Run scheduled paper trading with latest available data and store decisions continuously.

## Information required from user

```text
Paper trading schedule
Allowed market hours assumptions
Whether to run only after market close initially
```

Default: run after market close on daily candles.

## Acceptance criteria

1. Scheduler triggers data update, features, analysts, debate, trader proposal, risk, final decision, and PaperBroker.
2. Each run has a `run_id`.
3. Dashboard updates after each run.
4. Failures are logged and do not corrupt state.

---

# M12 - Telegram alerts, replay, backup, and hardening

## Objective

Add Telegram alerts, decision replay, backup commands, and operational runbooks.

## Information required from user

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## Acceptance criteria

1. Telegram smoke test works.
2. Alerts fire for paper fills, kill switch, severe events, job failures, and stale data.
3. Any decision can be replayed by `decision_id`.
4. Backups can be created and restored locally.

---

# M13 - Paper-trading MVP release

## Objective

Release the end-to-end observable paper-trading MVP. Broker sandbox and live broker work are deferred.

## Information required from user

```text
Optional real OHLCV CSV files or data-provider decision
Optional real Screener CSV export
Optional Telegram token/chat ID for real alert smoke testing
```

## Final verification checklist

```text
make setup
make dev-up
make migrate
make seed-mock
make import-mock-news
make backtest-mock
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make paper-loop-mock
make replay-decision DECISION_ID=sample
make backup-local
make taurus-smoke
make dashboard
make test
```

## Acceptance criteria

1. Taurus can run end-to-end with mock data.
2. Taurus can backtest.
3. Taurus can generate analyst reports.
4. Taurus can run bull/bear debate.
5. Taurus can generate trader proposal.
6. Taurus can run risk review and final approval.
7. Taurus can paper trade.
8. Taurus dashboard shows performance, decisions, debate, risk, orders, events, and health.
9. Decision replay and backup work.
10. Live trading is still disabled.
11. Broker sandbox integration is not required for MVP completion.

---

# M14 - Upstox sandbox adapter

## Objective

Deferred post-MVP milestone to validate Taurus order-payload mapping against Upstox Sandbox without enabling live trading.

## Acceptance criteria

1. `UPSTOX_SANDBOX_ACCESS_TOKEN` is loaded only from local env.
2. Mocked adapter tests pass without external credentials.
3. Sandbox smoke can place/cancel a simulated/test order where supported.
4. Live trading remains disabled.
5. PaperBroker remains default.
6. Details are tracked in `docs/UPSTOX_INTEGRATION_PLAN.md`.

---

# M15 - Upstox production readiness

## Objective

Deferred post-MVP milestone for production broker readiness. This milestone still must not place live orders.

## Acceptance criteria

1. `LIVE_TRADING_ENABLED=false` remains default.
2. Production broker mode requires explicit env flag, preflight pass, and manual sign-off.
3. Preflight checks broker config, risk config, order tags, kill switch, audit, reconciliation, dashboard health, and alerting.
4. No production orders are placed.
5. Details are tracked in `docs/UPSTOX_INTEGRATION_PLAN.md`.

---

## 10. Definition of done for every milestone

A milestone is complete only when:

1. Code is implemented.
2. Unit tests pass.
3. Verification commands were run and documented.
4. Logs and metrics exist for the new path.
5. No secrets are committed.
6. User-required inputs are explicitly listed.
7. Dashboard/API visibility exists where relevant.
8. Failure behavior is tested.
9. Live trading remains disabled unless the milestone is specifically about live-readiness, and even there no live orders are sent.

---

## 11. First Codex instruction

```text
You are implementing Project Taurus, an observable, paper-trading-first algo trading MVP for Indian cash equities. Use Taurus MVP Specification v0.3. Start with Milestone M0 only. Do not implement broker live trading. Do not add real API keys. Implement local Docker Compose, FastAPI health endpoints, config loading, JSON logging, pytest setup, Makefile commands, and Prometheus metrics endpoint. Stop after M0 acceptance criteria pass and provide a summary of files changed and verification commands run.
```

---

## 12. Important implementation rule

Do not ask Codex to build all milestones in one run. Implement and verify one milestone at a time.
