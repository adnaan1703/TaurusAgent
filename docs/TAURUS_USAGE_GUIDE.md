# Taurus Usage Guide

Last verified: 2026-06-11.

## Current State

- Backend focused M55/profile regression tests:
  `uv run pytest tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py tests/unit/test_paper_broker.py tests/unit/test_taurus_smoke.py -q`
  -> `69 passed`.
- Backend full suite: `make test` -> `320 passed, 1 skipped`.
- Frontend tests: `make test-ui` -> `28 passed`.
- Compile check: `make lint` -> passed.
- Frontend build: `make build-ui` -> passed.
- Docker Postgres is the canonical Taurus database. Runtime, scripts, and tests
  reject SQLite database URLs.
- Docker Compose persists Postgres and Grafana data in named volumes:
  `taurusagent_postgres_data` and `taurusagent_grafana_data`.
- Runtime market data is Kite-only. Legacy mock/CSV market-data providers are
  rejected by config and preflight checks.
- Runtime LLM providers are real providers only: `lmstudio` by default, with
  `openai` and `gemini` as explicit opt-ins.
- Execution remains local paper simulation through `PaperBroker`; Taurus does
  not route live broker orders.

## What Taurus Can Do Today

Taurus is a local, observable paper-trading simulator for Indian cash equities. It can:

- Sync Zerodha Kite instruments and import Kite historical daily candles.
- Persist latest Kite OHLC/LTP quote snapshots for visibility and position
  monitor trigger evidence.
- Compute technical indicators, strategy signals, and graph-aware target
  selection.
- Run backtests against existing imported daily candles using moving-average,
  blended-score, or graph-aware strategy YAMLs.
- Run configurable analyst reports. The config default is `technical`; the
  canonical `make paper-loop-kite` profile runs `technical,graph`.
- Run LLM-backed bull/bear research, debate synthesis, trader proposals, and
  optional final-decision explanations through the configured provider.
- Run deterministic risk review and final approval gates before paper routing.
- Simulate orders, fills, positions, cash, costs, and slippage through
  `PaperBroker`.
- Manage multiple logical paper profiles with isolated corpus, runs, orders,
  fills, positions, accounts, and P&L. `TAURUS_PROFILE_ID=local-paper` is the
  default selected profile; `TAURUS_PAPER_PORTFOLIO_ID` remains a legacy alias.
- Run scheduled after-close paper loops and an opt-in market-hours position
  monitor for stop-loss/take-profit lifecycle decisions.
- Expose FastAPI endpoints, a primary React dashboard, and a Streamlit fallback
  dashboard.
- Provide replay, backup/restore, mock or Telegram alerts, Prometheus metrics,
  and Grafana dashboards.
- Sync HalalStock compliance data and generate halal NSE universe YAML.
- Import TaurusData graph CSVs, compute graph edge statistics, review graph
  candidate edges, expose graph APIs, and browse graph data in React.
- Optionally rebuild a disposable Neo4j read-model projection from Postgres
  graph tables.

Key limitation: Taurus is not connected to a real broker paper account. Kite is
data-only. Broker order routing is outside the current roadmap unless a future
approved milestone changes that.

## Safety Defaults

```bash
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
TAURUS_MARKET_DATA_PROVIDER=kite
TAURUS_LLM_PROVIDER=lmstudio
TAURUS_ALERT_PROVIDER=mock
TAURUS_ENABLED_ANALYSTS=technical
TAURUS_GRAPH_ENABLED=false
TAURUS_GRAPH_RISK_ENABLED=false
TAURUS_NEO4J_ENABLED=false
TAURUS_POSITION_MONITOR_ENABLED=false
```

Do not commit real API keys, broker credentials, Telegram tokens, Kite tokens,
or user CSV exports. Safe defaults live in `.env.example`; local secrets belong
in ignored `.env`.

## Main Commands

### Setup And Checks

- `make setup`: install Python deps with `uv`.
- `make setup-ui`: install React deps with `pnpm`.
- `make test`: backend pytest suite.
- `make test-ui`: frontend Vitest suite.
- `make lint`: Python compile check.
- `make build-ui`: production React build.

### Local Stack

- `make dev-up`: starts API, Postgres, Redis, Prometheus, and Grafana.
  Neo4j is excluded unless the explicit Compose `neo4j` profile is used.
- `make dev-down`: stops the stack without deleting named volumes.
- `make api`: runs FastAPI locally on port `8000`.
- `make ui`: runs the React dashboard on port `5173`.
- `make dashboard`: runs the Streamlit fallback dashboard on port `8501`.

### Database And Data

- `make migrate`: creates/updates the Postgres schema.
- `make import-market-data`: alias for Kite daily candle import.
- `make import-screener CSV=/path/file.csv`: imports Screener fundamentals.
- `make sync-halal-stocks`: fetches HalalStock data and exports halal NSE YAML.
- `make import-taurus-graph DATA_DIR=configs/taurus_data`: imports TaurusData
  graph CSVs.
- `make compute-graph-stats AS_OF=YYYY-MM-DD`: computes graph edge statistics
  from existing daily candles. `AS_OF` is optional.
- `make project-neo4j-graph`: rebuilds the optional Neo4j projection when
  `TAURUS_NEO4J_ENABLED=true`; otherwise it prints a skipped summary.

### Kite

- `make kite-login-url`: prints the Kite login URL.
- `make kite-exchange-token REQUEST_TOKEN=...`: exchanges a request token into
  local `.env`.
- `make kite-sync-instruments`: syncs Kite instrument mappings.
- `make import-kite-candles`: imports Kite daily candles.
- `make kite-ltp-smoke`: stores latest Kite quote snapshots.

`make import-kite-candles`, `make compute-graph-stats`, and
`make paper-loop-kite` show terminal progress on stderr. The default
`TAURUS_PROGRESS=auto` uses Rich in interactive terminals and a plain single-line
redraw fallback in CI/non-TTY streams. Use `TAURUS_PROGRESS=false` to disable
terminal progress. After paper-loop progress completes, Taurus always prints a
human-readable LLM usage summary with compact token counts. `make paper-loop-kite`
suppresses the final JSON summary by default; run
`make paper-loop-kite PAPER_LOOP_KITE_JSON=true` when automation needs the
machine-readable payload.

### Paper Workflow

Several command names still include `mock` for historical compatibility. In the
current runtime they use Postgres, Kite-imported candles, and the configured
real LLM provider where the workflow calls an LLM.

- `make backtest-mock`: runs a backtest against existing imported daily candles.
- `make run-analysts-mock SYMBOL=INFY`: runs the configured analyst roster.
- `make debate-mock SYMBOL=INFY`: runs bull/bear/manager research debate.
- `make trader-proposal-mock SYMBOL=INFY`: creates a position-aware proposal.
- `make risk-review-mock SYMBOL=INFY`: runs deterministic risk review.
- `make final-approval-mock SYMBOL=INFY`: runs final approval with optional LLM
  explanation.
- `make paper-once-mock SYMBOL=INFY`: routes one approved decision through
  local `PaperBroker`.
- `make paper-loop-once SYMBOLS=INFY,TCS`: runs one scheduled loop for explicit
  symbols.
- `make paper-loop-start PAPER_LOOP_ITERATIONS=5`: runs repeated local loops.
- `make paper-loop-kite`: runs the canonical Kite-backed, graph-enabled paper
  loop. It sets `TAURUS_ENABLED_ANALYSTS=technical,graph`,
  `TAURUS_GRAPH_ENABLED=true`, `TAURUS_GRAPH_RISK_ENABLED=true`,
  `TAURUS_PAPER_ANALYSIS_SCOPE=full_universe`,
  `TAURUS_PAPER_EXECUTION_SCOPE=allocated_only`, and
  `STRATEGY=configs/strategies/graph_aware_score_v1.yaml`. It defaults to
  `TAURUS_PROFILE_ID=local-paper`; run
  `PROFILE_ID=client-a make paper-loop-kite` for another active profile.
- `make paper-loop-dashboard`: starts the stack, imports market data, graph
  prerequisites, and mock news, runs one Kite paper loop, then starts the React
  dashboard.
- `make taurus-smoke`: full MVP smoke test using existing Kite-imported market
  data and remaining non-market mocks. It also creates or reuses
  `smoke-profile`, runs one bounded paper loop for that profile, and checks
  profile-scoped API/dashboard reads.
- `make llm-smoke`: checks the configured real LLM provider.

The React dashboard has a read-only profile selector in the app shell. It uses
the `profile_id` URL query parameter, persists the last selected profile in
local storage, and scopes Overview, History, Risk, Portfolio, run detail, and
decision-trail pages to the selected active profile. Shariah and Graph pages
remain shared platform-level views.

### Multi-Profile Workflow

Create profiles before running paper loops for them:

```bash
make migrate
make profile-create PROFILE_ID=client-a PROFILE_DISPLAY_NAME="Client A" PROFILE_CORPUS_INR=250000
PROFILE_ID=client-a make paper-loop-kite
```

Profile-scoped reads accept `profile_id` and reject missing, archived, or
mismatched run/profile combinations instead of falling back to all data:

```bash
curl 'http://localhost:8000/paper/account?profile_id=client-a'
curl 'http://localhost:8000/paper/orders?profile_id=client-a'
curl 'http://localhost:8000/paper/fills?profile_id=client-a'
curl 'http://localhost:8000/ui/overview?profile_id=client-a'
curl 'http://localhost:8000/ui/history?profile_id=client-a'
curl 'http://localhost:8000/ui/portfolio?profile_id=client-a'
```

Each profile owns paper runs, orders, fills, account snapshots, positions, and
P&L. Starting corpus can be edited only before trading activity exists. Market
data, Shariah/compliance data, graph data, Kite credentials, LLM provider
settings, alert configuration, and the React app remain shared platform data in
this logical-isolation release. Separate databases/stacks, per-profile
credentials, deposits/withdrawals, dashboard profile CRUD, and automatic
all-profile batch scheduling remain deferred.

Manual EOD paper loop commands import the latest daily candles, settle previous
`PENDING_NEXT_OPEN` paper orders at the first newer candle open, and only then
analyze the new after-close state. The same run can create new pending orders
for the next trading day, but those queued orders do not change cash, exposure,
or positions until a later settlement run. If an EOD run is skipped, settlement
uses the first available daily candle after the original signal date rather than
requiring the very next calendar day.

After each run, use the React dashboard to check queued and settled orders:
the overview and run detail pages show settlement counts/details, the portfolio
page shows order `signal_trade_date`, `scheduled_fill_session`, and
`filled_trade_date`, and decision replay distinguishes queued orders from
missing fills. The Streamlit Orders fallback shows the same pending status/date
fields. Prometheus metrics expose paper-order status labels including
`PENDING_NEXT_OPEN`. Queued orders do not send fill alerts; terminal simulated
settlement fills and rejections send one alert per final outcome. Kite remains
data-only.

### Position Monitor

- `make position-monitor`: exits without polling because the monitor is disabled
  by default.
- `make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1`:
  polls open long paper positions during market hours with Kite latest quote
  snapshots, checks stored stop-loss/take-profit thresholds, and creates
  paper-only `market_hours` `EXIT` or `REDUCE` lifecycle decisions when a
  threshold is crossed.

The monitor does not create broker-native stop-losses, OCO orders, or live
broker orders.

### Replay And Ops

- `make replay-decision DECISION_ID=...`
- `make backup-local`
- `make restore-local BACKUP=... RESTORE_CONFIRM=I_UNDERSTAND`
- `make alert-smoke`
- `make alert-test-telegram`

Replay is an audit view over stored artifacts. Pending next-open orders appear
in the paper-order stage with no paper fills yet. Once settlement runs, replay
keeps the original order status history and shows the final simulated fill or
terminal rejection.

## How To Start Real-Data Paper Trading

Use this when "actual paper trading" means real Kite market data plus local
simulated paper execution.

1. Start infrastructure and create the schema:

```bash
make dev-up
make migrate
```

2. Run the API for the Kite callback in one terminal:

```bash
make api
```

3. In another terminal, generate a Kite token:

```bash
make kite-login-url
```

Complete Kite login. If callback works, Taurus stores `KITE_ACCESS_TOKEN` in
ignored `.env`. If the callback was not running, exchange manually:

```bash
make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>
```

4. Import real Kite data:

```bash
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
```

5. Prepare graph data for the canonical real-data paper profile:

```bash
make import-taurus-graph
make compute-graph-stats
```

Graph readiness requires company nodes, reviewed active edges, latest edge
stats, usable validated graph signals, and valid graph risk limits. If any are
missing, `make paper-loop-kite` fails before analyst/debate/trader/risk/final
approval/PaperBroker routing and points back to the import/stat commands.

6. Start an LLM provider.

Default local setup:

```bash
TAURUS_LLM_PROVIDER=lmstudio
TAURUS_LLM_BASE_URL=http://localhost:1234/v1
```

Start a compatible LM Studio server. Hosted alternatives require explicit API
keys and billing:

```bash
TAURUS_LLM_PROVIDER=openai OPENAI_API_KEY=...
TAURUS_LLM_PROVIDER=gemini GEMINI_API_KEY=...
```

7. Run one graph-enabled Kite paper loop:

```bash
make paper-loop-kite
```

The canonical loop is Shariah-only when `SYMBOL` and `SYMBOLS` are omitted,
because it analyzes `TAURUS_MARKET_DATA_UNIVERSE_PATH`, which defaults to
`configs/market_data/nifty_500_shariah.yaml`. It now performs full-universe
analysis, run-level allocation, risk/final decisions for analyzed symbols, and
deferred execution routing for allocated, risk-approved paper decisions. Before
that analysis begins, it imports fresh daily candles and settles any previous
pending next-open orders for the portfolio, so position-aware analysis sees
settled cash, exposure, and open quantities. Expect longer runtime and higher
LLM/API usage than a manual subset; the terminal progress output shows where
the run is spending time, and the post-progress LLM usage summary shows
provider-reported token counts and throughput.

For a manual graph-enabled subset:

```bash
make paper-loop-kite SYMBOLS=INFY,TCS
```

Manual subsets remain bounded to the explicit symbols plus any open paper
positions and pending next-open order symbols, so use them for debugging,
prompt checks, or targeted graph/risk reviews before running the full universe.

For an explicit technical-only manual loop:

```bash
TAURUS_ENABLED_ANALYSTS=technical SYMBOLS=INFY make paper-loop-start
```

8. Enable money management for the same paper-only flow:

```bash
TAURUS_MONEY_MANAGEMENT_ENABLED=true make paper-loop-kite
```

By default this loads
`TAURUS_MONEY_MANAGEMENT_CONFIG_PATH=configs/portfolio/money_management_v1.yaml`.
It adds core Shariah basket review artifacts, strategy-sleeve allocation
decisions, cash-buffer checks, open-risk usage, and drawdown-governor context.
It still routes only through local `PaperBroker`; live broker execution remains
disabled.

There is no manual core-symbol allowlist in the money-management policy. The
`core_shariah` sleeve defines the target allocation, `core_shariah_basket_v1`
selects the runtime basket, and
`money_management.core_shariah_basket.target_weights` is the authoritative
source for current core membership, allocation attribution, and UI labels. The
cash target is the `cash_buffer` sleeve target. When money management is
enabled, position and open-position caps come from policy `limits` rather than
the fallback `TAURUS_MAX_POSITION_PCT` and `TAURUS_MAX_OPEN_POSITIONS` env
settings.

9. Observe in React:

```bash
make ui
```

Open:

```text
http://localhost:5173/
http://localhost:5173/risk
http://localhost:5173/portfolio
http://localhost:5173/runs/{run_id}/symbols/{symbol}
```

Use Overview for the sleeve allocation summary, latest allocation decisions,
cash buffer, undeployed capacity, open risk used versus limit, drawdown
governors, and latest core basket composition/drift. Use Risk to inspect
allocation reductions or rejections beside risk-review rows; the
`Binding constraint` column identifies the cap that controlled sizing, such as
`cash_buffer`, `sleeve_capacity`, `total_open_trade_risk`,
`portfolio_drawdown_freeze`, or `strategy_unmapped`. Use Portfolio to see
per-position sleeve and strategy labels plus current sleeve utilization.

To inspect rejected candidates, open the latest run detail or Overview core
basket section and read `Core Basket Composition` -> rejected candidates. The
raw API equivalent is:

```bash
curl http://localhost:8000/ui/overview
curl http://localhost:8000/ui/risk
curl http://localhost:8000/ui/portfolio
curl http://localhost:8000/ui/runs/{run_id}/symbols/{symbol}/decision-trail
```

10. Optionally enable market-hours monitoring:

```bash
make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1
```

End-of-day paper trading does not require this step.

Do not mix old mock-market-data rows with Kite runs. Kite imports and Kite-backed
paper loops fail fast if `daily_candles.source = "mock_market_data"` or old
mock-backed paper-run summaries are present.

## FastAPI Surface

Health and observability:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

Data:

```bash
curl http://localhost:8000/data/instruments
curl http://localhost:8000/data/instruments/INFY
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
```

Workflow artifacts:

```bash
curl http://localhost:8000/events
curl "http://localhost:8000/agent-reports?symbol=INFY"
curl http://localhost:8000/fundamentals
curl http://localhost:8000/fundamentals/imports
curl http://localhost:8000/debates
curl http://localhost:8000/debates/{debate_id}
curl http://localhost:8000/trader-proposals
curl http://localhost:8000/risk-reviews
curl http://localhost:8000/risk-reviews/{risk_check_id}
curl http://localhost:8000/final-decisions
curl http://localhost:8000/final-decisions/{final_decision_id}
curl http://localhost:8000/paper/orders
curl http://localhost:8000/paper/fills
curl http://localhost:8000/paper/positions
curl http://localhost:8000/paper/account
curl http://localhost:8000/runs
curl http://localhost:8000/runs/{run_id}
curl http://localhost:8000/replay/{decision_id}
```

Alerts:

```bash
curl -X POST http://localhost:8000/alerts/test
```

React aggregate API:

```bash
curl http://localhost:8000/ui/overview
curl http://localhost:8000/ui/runs/{run_id}
curl http://localhost:8000/ui/runs/{run_id}/symbols/INFY/decision-trail
curl http://localhost:8000/ui/replay/{decision_id}
curl http://localhost:8000/ui/risk
curl http://localhost:8000/ui/portfolio
curl http://localhost:8000/ui/history
curl http://localhost:8000/ui/shariah
```

Graph API:

```bash
curl http://localhost:8000/graph/overview
curl http://localhost:8000/graph/company/INFY
curl http://localhost:8000/graph/candidate-edges
curl http://localhost:8000/graph/signals
curl http://localhost:8000/graph/bullish-candidates
curl http://localhost:8000/graph/edges/{edge_key}
curl http://localhost:8000/graph/edges/{edge_key}/evidence
```

Candidate edge review requires `TAURUS_GRAPH_ENABLED=true`:

```bash
curl -X POST http://localhost:8000/graph/edges/{edge_key}/promote
curl -X POST http://localhost:8000/graph/edges/{edge_key}/reject
```

## React Dashboard

Primary routes:

```text
http://localhost:5173/
http://localhost:5173/runs/{run_id}
http://localhost:5173/runs/{run_id}/symbols/{symbol}
http://localhost:5173/replay/{decision_id}
http://localhost:5173/risk
http://localhost:5173/portfolio
http://localhost:5173/shariah
http://localhost:5173/graph
http://localhost:5173/graph/company/{symbol}
http://localhost:5173/graph/edges/review
http://localhost:5173/graph/signals
http://localhost:5173/history
```

The run-loop views are read-only. The graph edge review route mutates graph edge
review status only when the API is started with `TAURUS_GRAPH_ENABLED=true`; it
does not route orders or bypass risk/final approval.

When money management is enabled, Overview, Risk, Portfolio, and the symbol
decision trail expose the same allocation context: sleeve utilization, core
basket drift, cash buffer, undeployed capacity, open risk used versus limit,
drawdown-governor state, latest allocation decisions with binding constraints,
and per-position sleeve/strategy labels.

Core basket membership shown in these views comes from the latest money
management run artifact's target weights. If the runtime core basket changes,
the labels and active capacity attribution follow that latest artifact rather
than any static policy symbol list.

## Graph Intelligence

Postgres is the canonical graph store. Neo4j is optional and disposable.

Graph stats use Postgres graph edges and existing `daily_candles`. The job
computes close-to-close return correlations across configured windows, market
residual correlation, lead-lag score, stability score, sample size, and
insufficient-data reasons.

```bash
make migrate
make import-market-data
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=2024-12-17
```

Default windows are controlled by:

```bash
TAURUS_GRAPH_STATS_WINDOWS=60,120,252
```

Automatic graph candidate promotion remains disabled by default:

```bash
TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false
```

Graph concentration risk is disabled by config default but enabled by
`make paper-loop-kite`. It can warn, reduce approved paper size, or reject a
proposed long entry. It cannot route orders or bypass final approval.

Default graph risk limits:

```bash
TAURUS_GRAPH_MAX_BASIC_INDUSTRY_EXPOSURE_PCT=25.0
TAURUS_GRAPH_MAX_PRODUCT_GROUP_EXPOSURE_PCT=30.0
TAURUS_GRAPH_MAX_CUSTOMER_INDUSTRY_EXPOSURE_PCT=30.0
TAURUS_GRAPH_MAX_DEPENDENCY_EXPOSURE_PCT=30.0
TAURUS_GRAPH_MAX_RISK_CATEGORY_EXPOSURE_PCT=25.0
TAURUS_GRAPH_MAX_CORRELATED_CLUSTER_EXPOSURE_PCT=35.0
TAURUS_GRAPH_CONCENTRATION_WARNING_FRACTION=0.80
```

Optional Neo4j projection:

```bash
docker compose --profile neo4j up -d neo4j
TAURUS_NEO4J_ENABLED=true make project-neo4j-graph
```

## Mocks And Simulations Still Used

For the maintained component-by-component tracker, see
`docs/TAURUS_MOCK_MIGRATION_STATUS.md`.

- Market data defaults to `kite`; runtime `mock`, `csv`, and placeholder
  `external` providers are rejected.
- LLM defaults to the real local `lmstudio` provider. Runtime mock LLM support
  has been removed, though tests use fakes.
- `PaperRunService` imports `MockNewsProvider` on every paper run, even with
  technical/graph analysts only.
- Alerts default to `MockAlertAdapter`; `/alerts/test` always uses mock alert
  delivery.
- Fundamentals use a mock fallback if the fundamentals analyst is enabled and
  no Screener data exists.
- `PaperBroker` is the intended simulator. It is paper execution, not a real
  broker paper account.
- Paper costs, slippage, and fill assumptions are placeholder bps settings.
- Paper fills use daily-candle prices, not live order book or Kite LTP
  execution. The position monitor uses Kite LTP only as trigger evidence.
- After-close EOD paper orders are queued as AMO-style `PENDING_NEXT_OPEN`
  orders. The next manual EOD run settles them against the first newer daily
  candle open before it creates new pending orders.
- React, Streamlit, replay, alerts, and Prometheus metrics all report queued
  next-open orders separately from filled, partially filled, and rejected
  simulated paper orders.

## Technical-Only Flow

With `TAURUS_ENABLED_ANALYSTS=technical`:

- Only `TechnicalAnalystAgent` runs.
- It computes technical score from candles/features/signals.
- It still calls the configured real LLM provider for bounded explanation.
- Debate and paper-run workflows still call the configured real LLM provider
  through bull/bear/manager/trader/final explanation components.
- Mock news is still imported into the DB during paper runs, and severe stored
  events can still affect deterministic risk blocks.
- News, sentiment, fundamentals, and graph analyst reports are skipped.

## Data Storage

Docker-backed:

- Postgres data lives in Docker named volume `taurusagent_postgres_data`.
- Grafana data lives in Docker named volume `taurusagent_grafana_data`.
- These persist after `make dev-down`.
- Remove them only with a volume-removing command such as
  `docker compose down -v`.

Local repo/filesystem:

- `.env` is local and ignored.
- `backups/` is local and ignored.
- Imported user CSVs, generated YAMLs, docs, and fixtures are local files.
- Redis has no persistent volume in `docker-compose.yml`.

Direct `uv run ...` commands use the same Postgres default as `make` targets.
Use `TAURUS_TEST_DATABASE_URL` only for isolated Postgres test databases.

## Main Gaps

1. Remove mock news from real paper runs, or add a real/no-news mode.
2. Add a rule-only technical analyst path if no LLM should be required for
   technical-only paper runs.
3. Rename historical `*-mock` command/function names where they now operate on
   Kite data and real LLM providers.
4. Replace placeholder cost/slippage/fill assumptions with broker-calibrated
   paper execution assumptions.
5. Add a real news provider before enabling news/sentiment in production-like
   paper runs.
6. Validate real Screener CSV exports before relying on fundamentals.
7. Verify Telegram alerts with local-only credentials.
8. Add dashboard/API auth before use beyond a trusted local machine.
9. Implement broker order routing only after an explicit approved milestone.

## Bottom Line

Taurus is usable today for local, observable, real-Kite-data paper simulation
with graph intelligence on the canonical `paper-loop-kite` path when Kite data,
graph import/stats, and a configured real LLM provider are available. It remains
paper-only, local, and intentionally guarded against live broker execution.
