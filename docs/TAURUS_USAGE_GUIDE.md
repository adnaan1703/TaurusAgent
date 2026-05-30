# Taurus Usage Guide

## Current State

- Backend tests: `make test` -> `181 passed, 1 skipped` during M28.
- Frontend tests: `make test-ui` -> `25 passed` during M28.
- Compile check: `make lint` -> passed during M28.
- Frontend build: `make build-ui` -> passed during M28.
- Docker Postgres is the canonical Taurus database. Runtime, scripts, and tests
  reject SQLite database URLs.
- Docker Compose volumes exist for canonical Postgres data:
  `taurusagent_postgres_data` and `taurusagent_grafana_data`.
- Local SQLite database files were removed during M21 after Docker Postgres data
  verification passed.
- Local `.env` exists and contains only Kite keys. It does not set `DATABASE_URL`, `TAURUS_MARKET_DATA_PROVIDER`, or analyst settings.

## What Taurus Can Do Today

Taurus is a local, observable paper-trading simulator for Indian cash equities. It can:

- Import runtime market data from Zerodha Kite daily candles.
- Sync Kite instruments and import Kite historical daily candles.
- Store latest Kite OHLC/LTP snapshots, but those snapshots are currently for visibility, not paper fills.
- Compute technical indicators and strategy signals.
- Run analyst reports with configurable analyst roster. Default is technical only.
- Run bull/bear research debate, position-aware trader proposal, risk review,
  and final approval.
- Simulate orders, fills, positions, cash, costs, and slippage through `PaperBroker`.
- Preserve one local paper portfolio across run IDs with
  `TAURUS_PAPER_PORTFOLIO_ID=local-paper`, while keeping `run_id` on artifacts
  for audit.
- Track paper runs with audit artifacts.
- Expose FastAPI endpoints and React dashboard.
- Provide replay, backup/restore, alerts, Prometheus metrics, and Grafana dashboards.
- Sync HalalStock compliance data and generate a halal NSE universe YAML.
- Import TaurusData graph CSVs, expose Postgres-backed graph API endpoints, and
  browse/review graph data in the React dashboard.
- Optionally rebuild a disposable Neo4j read-model projection from Postgres
  graph tables.
- Compute graph edge validation statistics from daily candle data and persist
  raw correlation, market-residual correlation, lead-lag score, stability score,
  sample size, and insufficient-data reasons.
- Run the canonical Kite paper loop with technical plus graph analysts,
  graph-aware target selection, graph readiness preflight, and graph
  concentration risk. Candidate edges remain review-only and do not influence
  paper decisions until promoted to active.

**Key files:**

- `Makefile`
- `packages/taurus_core/config.py`
- `packages/taurus_core/paper_trading/service.py`
- `packages/taurus_core/brokers/paper_broker.py`
- `packages/taurus_core/data/providers/kite_market_data.py`
- `docs/TAURUS_USAGE_GUIDE.md`

**Important limitation:** This is not connected to a real broker paper account. It is a local paper simulator. Kite is data-only. Broker order routing is not part of the current roadmap.

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
  Neo4j is excluded by default and uses the explicit Compose `neo4j` profile.
- `make dev-down`: stops stack.
- `make api`: runs FastAPI locally on port `8000`.
- `make ui`: runs React dashboard on port `5173`.
- `make dashboard`: runs the Streamlit fallback dashboard.

### Database And Data

- `make migrate`: creates/updates DB schema.
- `make import-market-data`: imports Kite daily candles.
- `make import-screener CSV=/path/file.csv`: imports Screener fundamentals.
- `make import-taurus-graph DATA_DIR=configs/taurus_data`: imports TaurusData graph CSVs.
- `make compute-graph-stats AS_OF=YYYY-MM-DD`: computes graph edge statistics
  from existing daily candles. `AS_OF` is optional and defaults to the latest
  candle date.
- `make project-neo4j-graph`: rebuilds the optional Neo4j graph projection
  when `TAURUS_NEO4J_ENABLED=true`; otherwise exits with a skipped summary.
- `make sync-halal-stocks`: fetches HalalStock data and exports halal NSE universe YAML.

### Kite

- `make kite-login-url`: prints Kite login URL.
- `make kite-exchange-token REQUEST_TOKEN=...`: exchanges request token into local `.env`.
- `make kite-sync-instruments`: syncs Kite instrument mappings.
- `make import-kite-candles`: imports Kite daily candles.
- `make kite-ltp-smoke`: stores latest Kite quote snapshots.

### Paper Workflow

- `make paper-loop-kite`: Kite-backed data import plus graph-enabled local
  `PaperBroker` simulation. This target sets `TAURUS_ENABLED_ANALYSTS=technical,graph`,
  `TAURUS_GRAPH_ENABLED=true`, `TAURUS_GRAPH_RISK_ENABLED=true`, and
  `STRATEGY=configs/strategies/graph_aware_score_v1.yaml`. Open positions from
  the configured paper portfolio are automatically included for after-close
  lifecycle review.
- `make paper-loop-start PAPER_LOOP_ITERATIONS=5`: repeated local loop.
- `make paper-loop-dashboard`: Kite-backed run plus React dashboard.
- `make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1`:
  later opt-in for polling open paper positions with Kite latest quote snapshots
  and creating paper-only
  `market_hours` stop-loss/take-profit lifecycle decisions when thresholds are
  crossed.
- `make taurus-smoke`: full MVP smoke test using existing Kite-imported market data and remaining non-market mocks.

### Replay And Ops

- `make replay-decision DECISION_ID=...`
- `make backup-local`
- `make restore-local BACKUP=...`
- `make alert-smoke`
- `make alert-test-telegram`

## How To Start Real-Data Paper Trading

Use this if "actual paper trading" means real Kite market data plus local simulated paper execution.

1. **Start infrastructure:**

```bash
make dev-up
make migrate
```

2. **Run API for Kite callback in one terminal:**

```bash
make api
```

3. **In another terminal, generate Kite token:**

```bash
make kite-login-url
```

Complete Kite login. If callback works, Taurus stores `KITE_ACCESS_TOKEN` in ignored `.env`. If not:

```bash
make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>
```

4. **Import real Kite data:**

```bash
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
```

5. **Prepare graph data for the real-data paper profile:**

```bash
make import-taurus-graph
make compute-graph-stats
```

Graph readiness checks require company nodes, active edges, latest edge stats,
usable validated graph signals, and valid graph risk limits. If any are missing,
`make paper-loop-kite` fails before the analyst/debate/trader/risk/final/PaperBroker
pipeline and points back to the import/stat commands.

6. **Run one graph-enabled Kite paper loop:**

```bash
make paper-loop-kite
```

7. **Observe:**

```bash
make ui
```

Open `http://localhost:5173`.

8. **Later opt-in market-hours monitor:**

```bash
make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1
```

End-of-day trading does not require this step. The monitor is disabled by
default with `TAURUS_POSITION_MONITOR_ENABLED=false`; the Make target keeps that
posture unless `POSITION_MONITOR_ENABLED=true` is passed explicitly. The monitor
is paper-only. It requires open positions in
`TAURUS_PAPER_PORTFOLIO_ID`, persists Kite quote snapshots before evaluation,
and routes triggered `EXIT`/`REDUCE` proposals through the same TraderAgent,
RiskReview, PortfolioManagerAgent, and PaperBroker decision trail. It does not
create broker-native stop-loss, OCO, or live broker orders.

Do not mix old mock-market-data rows with Kite runs. Kite imports and Kite-backed paper loops fail fast if `daily_candles.source = "mock_market_data"` or old mock-backed paper-run summaries are present.

For an explicit technical-only manual run, use the generic loop target instead
of the canonical graph-enabled Kite profile:

```bash
TAURUS_ENABLED_ANALYSTS=technical SYMBOLS=INFY make paper-loop-start
```

For an explicit graph-enabled Kite subset, keep the canonical target and pass
symbols on the make command line:

```bash
make paper-loop-kite SYMBOLS=INFY,TCS
```

## Mocks Still Used

Yes.

For the maintained component-by-component tracker, see
`docs/TAURUS_MOCK_MIGRATION_STATUS.md`.

**Runtime mocks/defaults still present:**

- Market data defaults to `kite`; runtime `mock`, `csv`, and placeholder `external` providers are rejected.
- LLM defaults to the real local `lmstudio` provider; LM Studio must be running
  before LLM-backed analyst, research-debate, trader-proposal, final-approval,
  and paper-run workflows unless `openai` or `gemini` is explicitly configured.
- `PaperRunService` imports `MockNewsProvider` on every paper run, even with technical-only analysts.
- Alerts default to `MockAlertAdapter`.
- `/alerts/test` always uses mock alert delivery.
- Fundamentals use a mock fallback if the fundamentals analyst is enabled and no Screener data exists.
- `PaperBroker` is a simulator. It is expected paper execution, but not a real broker paper account.
- Paper costs are placeholder bps settings.
- Paper fills use latest daily candle open/close, not live order book or Kite LTP execution. The position monitor uses Kite LTP only as auditable trigger evidence.

## Technical-Only Flow

With `TAURUS_ENABLED_ANALYSTS=technical`:

- Only `TechnicalAnalystAgent` runs.
- It computes technical score from candles/features/signals.
- It still calls the configured real LLM provider. The default is LM Studio;
  `openai` and `gemini` are explicit hosted-provider opt-ins.
- If you continue into debate or paper-run workflows, `BullResearcherAgent`,
  `BearResearcherAgent`, `ResearchManagerAgent`, and `TraderAgent` also call
  the configured real LLM provider and clamp their output to deterministic
  scoring and lifecycle guardrails.
- `PortfolioManagerAgent` may call the configured real LLM provider only after
  deterministic final approval fields are fixed, and only to enrich
  `FinalDecision.reason` plus bounded model metadata.
- OpenAI uses API billing through `OPENAI_API_KEY`; ChatGPT subscriptions are
  not supported for Taurus backend inference.
- Mock news is still imported into the DB.
- Risk engine still checks severe events in the DB, so mock news can still influence risk blocks if matching active instruments.
- News, sentiment, fundamentals, and graph analyst reports are skipped.

So: technical-only does reduce the analyst roster, but it does not fully eliminate mocks.

## DB And Data Storage

Your assumption is only partly true.

**Docker-backed:**

- Postgres data lives in Docker named volume `taurusagent_postgres_data`.
- Taurus runtime, scripts, and tests use Postgres by default through
  `postgresql+psycopg://taurus:taurus@localhost:5432/taurus`.
- Grafana data lives in Docker named volume `taurusagent_grafana_data`.
- These persist after `make dev-down`.
- They are removed only if you remove volumes, e.g. `docker compose down -v`.

**Local repo/filesystem:**

- `.env` is local and ignored.
- `backups/` exists locally and is ignored.
- CSV imports, generated YAMLs, docs, and fixture files are local files.
- Redis has no persistent volume in `docker-compose.yml`.

Direct `uv run ...` commands now use the same Postgres default as `make`
targets. Use `TAURUS_TEST_DATABASE_URL` only for isolated Postgres test
databases; SQLite URLs are rejected.

## Graph Intelligence API

M20 graph APIs read from the Postgres/SQLAlchemy graph tables. Neo4j is not
required for the current API/dashboard slice.

Useful local endpoints after `make import-taurus-graph` and `make api`:

```bash
curl http://localhost:8000/graph/overview
curl http://localhost:8000/graph/company/INFY
curl http://localhost:8000/graph/candidate-edges
curl http://localhost:8000/graph/signals
curl http://localhost:8000/graph/bullish-candidates
```

Edge detail and evidence endpoints use the stable `edge_key` returned by graph
responses:

```bash
curl http://localhost:8000/graph/edges/{edge_key}
curl http://localhost:8000/graph/edges/{edge_key}/evidence
```

Candidate edge review endpoints are local-dashboard oriented and require
`TAURUS_GRAPH_ENABLED=true`:

```bash
curl -X POST http://localhost:8000/graph/edges/{edge_key}/promote
curl -X POST http://localhost:8000/graph/edges/{edge_key}/reject
```

## React Graph Dashboard

After importing graph data and starting the API/UI, open:

```text
http://localhost:5173/graph
http://localhost:5173/graph/company/INFY
http://localhost:5173/graph/edges/review
http://localhost:5173/graph/signals
```

The review route can promote or reject graph candidate edges only when the API
is started with `TAURUS_GRAPH_ENABLED=true`. This mutates graph edge status
metadata only; it does not route orders or bypass the existing paper-trading
risk/final-approval flow.

## Optional Neo4j Projection

Neo4j is a disposable read model. It is disabled by default, excluded from
`make dev-up`, and can always be rebuilt from Postgres graph tables. Taurus
does not write Neo4j data back into Postgres.

Start only the optional service:

```bash
docker compose --profile neo4j up -d neo4j
```

Prepare source data and rebuild the projection:

```bash
make migrate
make import-taurus-graph DATA_DIR=configs/taurus_data
TAURUS_NEO4J_ENABLED=true make project-neo4j-graph
```

Running `make project-neo4j-graph` without `TAURUS_NEO4J_ENABLED=true` is a
safe no-op that prints a skipped JSON summary.

## Graph Statistical Validation

Graph stats use Postgres graph edges and existing `daily_candles`. The job
computes close-to-close return correlations across configured windows, using an
equal-weight market proxy from available daily candle returns for residual
correlation.

```bash
make migrate
make import-market-data
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=2024-12-17
```

Default windows are controlled by `TAURUS_GRAPH_STATS_WINDOWS=60,120,252`.
Candidate auto-promotion remains disabled by default through
`TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false`; enabling it only updates graph edge
review status metadata and still does not route orders.

## Optional Graph Risk Checks

Graph-aware concentration checks remain disabled by config default through
`TAURUS_GRAPH_RISK_ENABLED=false`, but the canonical `make paper-loop-kite`
target enables them for the real-data Kite paper path after readiness passes.
When enabled, the risk engine adds hard-rule results for basic industry, product group, customer industry,
raw material/dependency, risk category, and statistically validated correlated
graph clusters. A graph concentration can warn, reduce the approved paper size,
or reject the proposed long entry; it still cannot route orders or bypass final
approval.

The default maximum exposures are controlled by:

```bash
TAURUS_GRAPH_MAX_BASIC_INDUSTRY_EXPOSURE_PCT=25.0
TAURUS_GRAPH_MAX_PRODUCT_GROUP_EXPOSURE_PCT=30.0
TAURUS_GRAPH_MAX_CUSTOMER_INDUSTRY_EXPOSURE_PCT=30.0
TAURUS_GRAPH_MAX_DEPENDENCY_EXPOSURE_PCT=30.0
TAURUS_GRAPH_MAX_RISK_CATEGORY_EXPOSURE_PCT=25.0
TAURUS_GRAPH_MAX_CORRELATED_CLUSTER_EXPOSURE_PCT=35.0
TAURUS_GRAPH_CONCENTRATION_WARNING_FRACTION=0.80
```

## Main Gaps Before It Is "Super Ready"

1. Remove mock news from real paper runs, or add a real/no-news mode. Right now mock news can affect risk even with technical/graph paper runs.
2. Add a rule-only technical analyst path if no LLM should be required for
   technical-only paper runs. Runtime mock LLM has been removed.
3. Use a clean DB if legacy `mock_market_data` candles or old mock-backed paper-run summaries exist; Kite runs fail clearly rather than mixing sources.
4. Make Kite-backed backtesting first-class. Current backtest script uses existing daily candles and no longer imports mock or CSV candles.
5. Replace placeholder cost/slippage/fill assumptions with broker-calibrated paper execution assumptions.
6. Add a real news/data provider if news/sentiment risk is enabled.
7. Validate real Screener CSV if fundamentals will be used.
8. Add dashboard/API auth before using beyond a trusted local machine.
9. Implement broker order routing only after an explicit approved milestone; Kite execution is not implemented.

## Bottom Line

Taurus is usable today for local, observable, real-Kite-data paper simulation
with graph intelligence on the canonical `paper-loop-kite` path when LM Studio
or an explicit hosted LLM provider is configured and graph import/stats
readiness passes. Final approval remains deterministic, with optional LLM
explanations flowing through existing final-decision reason/model metadata.
Market-hours stop-loss/take-profit monitoring now creates auditable paper-only
`market_hours` lifecycle decisions for open long positions. It
is not yet clean of mocks, and it is not broker-level paper trading. The biggest
remaining mock contamination is mock news imported into risk context.
