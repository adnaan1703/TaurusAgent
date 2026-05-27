# Taurus Usage Guide

## Current State

- Backend tests: `make test` -> `97 passed`.
- Frontend tests: `make test-ui` -> `21 passed`.
- Compile check: `make lint` -> passed.
- Git worktree is clean.
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
- Expose FastAPI endpoints and read-only React dashboard.
- Provide replay, backup/restore, alerts, Prometheus metrics, and Grafana dashboards.
- Sync HalalStock compliance data and generate a halal NSE universe YAML.

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
- `make dev-down`: stops stack.
- `make api`: runs FastAPI locally on port `8000`.
- `make ui`: runs React dashboard on port `5173`.
- `make dashboard`: runs the Streamlit fallback dashboard.

### Database And Data

- `make migrate`: creates/updates DB schema.
- `make seed-mock`: seeds deterministic mock instruments/candles.
- `make import-price-csv CSV=/path/file.csv`: imports user OHLCV CSV.
- `make import-screener CSV=/path/file.csv`: imports Screener fundamentals.
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
