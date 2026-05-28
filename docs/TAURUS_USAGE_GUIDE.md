# Taurus Usage Guide

## Current State

- Backend tests: `make test` -> `112 passed, 1 skipped` after M20.6.
- Frontend tests: not rerun in M20.6; latest `make test-ui` was `25 passed` after M20.4.
- Compile check: `make lint` -> passed after M20.6.
- Frontend build: not rerun in M20.6; latest `make build-ui` passed after M20.4.
- Git worktree contains M20.6 implementation changes until committed.
- Docker Compose services are not currently running, but Docker volumes exist: `taurusagent_postgres_data`, `taurusagent_grafana_data`.
- A local ignored SQLite file exists: `taurus.db`, containing `10` instruments and `2520` daily candles. This means not all local state is only in Docker.
- Local `.env` exists and contains only Kite keys. It does not set `DATABASE_URL`, `TAURUS_MARKET_DATA_PROVIDER`, or analyst settings.

## What Taurus Can Do Today

Taurus is a local, observable paper-trading simulator for Indian cash equities. It can:

- Import market data from deterministic mock data, CSV files, or Zerodha Kite daily candles.
- Sync Kite instruments and import Kite historical daily candles.
- Store latest Kite OHLC/LTP snapshots, but those snapshots are currently for visibility, not paper fills.
- Compute technical indicators and strategy signals.
- Run analyst reports with configurable analyst roster. Default is technical only.
- Run bull/bear research debate, trader proposal, risk review, and final approval.
- Simulate orders, fills, positions, cash, costs, and slippage through `PaperBroker`.
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
- `make seed-mock`: seeds deterministic mock instruments/candles.
- `make import-price-csv CSV=/path/file.csv`: imports user OHLCV CSV.
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

- `make paper-loop-mock`: mock-data paper loop.
- `make paper-loop-kite`: Kite-backed data import plus local `PaperBroker` simulation.
- `make paper-loop-start PAPER_LOOP_ITERATIONS=5`: repeated local loop.
- `make paper-loop-dashboard`: mock run plus React dashboard.
- `make taurus-smoke`: full MVP smoke test using mocks.

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

5. **Run one technical-only paper loop:**

```bash
TAURUS_ENABLED_ANALYSTS=technical make paper-loop-kite
```

6. **Observe:**

```bash
make ui
```

Open `http://localhost:5173`.

Do not run `make seed-mock` for a real-data paper DB unless you intentionally want mock instruments mixed into the database.

## Mocks Still Used

Yes.

**Runtime mocks/defaults still present:**

- Market data defaults to `mock` unless Kite/CSV is explicitly selected.
- `make paper-loop-kite` uses real Kite market data, but still forces `TAURUS_LLM_PROVIDER=mock`.
- `PaperRunService` imports `MockNewsProvider` on every paper run, even with technical-only analysts.
- Alerts default to `MockAlertAdapter`.
- `/alerts/test` always uses mock alert delivery.
- Fundamentals use a mock fallback if the fundamentals analyst is enabled and no Screener data exists.
- `PaperBroker` is a simulator. It is expected paper execution, but not a real broker paper account.
- Paper costs are placeholder bps settings.
- Paper fills use latest daily candle open/close, not live order book or Kite LTP execution.

## Technical-Only Flow

With `TAURUS_ENABLED_ANALYSTS=technical`:

- Only `TechnicalAnalystAgent` runs.
- It computes technical score from candles/features/signals.
- It still calls the configured LLM provider. Default/make target is mock LLM.
- Mock news is still imported into the DB.
- Risk engine still checks severe events in the DB, so mock news can still influence risk blocks if matching active instruments.
- News, sentiment, and fundamentals analyst reports are skipped.

So: technical-only does reduce the analyst roster, but it does not fully eliminate mocks.

## DB And Data Storage

Your assumption is only partly true.

**Docker-backed:**

- Postgres data lives in Docker named volume `taurusagent_postgres_data`.
- Grafana data lives in Docker named volume `taurusagent_grafana_data`.
- These persist after `make dev-down`.
- They are removed only if you remove volumes, e.g. `docker compose down -v`.

**Local repo/filesystem:**

- `.env` is local and ignored.
- `taurus.db` exists locally and is ignored.
- `backups/` exists locally and is ignored.
- CSV imports, generated YAMLs, docs, and fixture files are local files.
- Redis has no persistent volume in `docker-compose.yml`.

> Important nuance: `make` targets default to Postgres at `localhost:5432`, but direct `uv run ...` without `DATABASE_URL` uses the code default SQLite database `sqlite:///./taurus.db`.

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
make seed-mock
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=2024-12-17
```

Default windows are controlled by `TAURUS_GRAPH_STATS_WINDOWS=60,120,252`.
Candidate auto-promotion remains disabled by default through
`TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false`; enabling it only updates graph edge
review status metadata and still does not route orders.

## Main Gaps Before It Is "Super Ready"

1. Remove mock news from real paper runs, or add a real/no-news mode. Right now mock news can affect risk even with technical-only analysts.
2. Stop forcing mock LLM in `paper-loop-kite`, or add a rule-only technical analyst path that does not call any LLM.
3. Add true portfolio continuity across paper runs. Current paper account state is run-scoped; it does not behave like one persistent paper account across days.
4. Avoid mixed mock/Kite data in the same DB. Active mock instruments can remain after `seed-mock`; real paper runs should use a clean DB or provider-scoped universe handling.
5. Make Kite-backed backtesting first-class. Current backtest script supports `mock`/`csv`/`external`, not Kite directly.
6. Replace placeholder cost/slippage/fill assumptions with broker-calibrated paper execution assumptions.
7. Add a real news/data provider if news/sentiment risk is enabled.
8. Validate real Screener CSV if fundamentals will be used.
9. Add dashboard/API auth before using beyond a trusted local machine.
10. Implement broker order routing only after an explicit approved milestone; Kite execution is not implemented.

## Bottom Line

Taurus is green and usable today for local, observable, real-Kite-data paper simulation with technical-only analysis. It is not yet clean of mocks, and it is not broker-level paper trading. For your current technical-only setup, the biggest mock contamination is mock LLM plus mock news imported into risk context.
