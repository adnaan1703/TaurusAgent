# Taurus

Taurus is an observable, paper-trading-first algo trading MVP for Indian cash equities.

The paper-trading MVP is complete, and the React run-loop observability dashboard is the primary local UI. Taurus can run the local mock-data flow end to end: market data seeding, news/events, backtests, analyst reports, bull/bear debate, trader proposal, risk review, final approval, PaperBroker execution, scheduled paper loop, replay, backup, API, React dashboard, Streamlit fallback dashboard, Prometheus metrics, and Grafana dashboards.

Broker order routing is not part of the current roadmap. Taurus remains a local paper simulator unless a future milestone explicitly changes that direction.
Kite Connect support is data-only: it can sync instruments, import historical
daily candles, and store latest OHLC/LTP snapshots, but all execution still
routes through `PaperBroker`.

## Safety Defaults

Live trading is disabled by default and rejected by the config loader.

```bash
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
```

Do not commit real API keys, broker credentials, or tokens. Use `.env` locally if needed later; it is ignored by Git.

Kite credentials, when used, also stay local:

```bash
KITE_API_KEY=
KITE_API_SECRET=
KITE_ACCESS_TOKEN=
```

The access token is a short-lived manual Kite Connect login artifact. If Kite
commands fail with an expired-token message, generate a fresh token locally and
update `.env`; do not put credentials in tracked files or command references.

Generate and store the access token locally:

```bash
make api
make kite-login-url
```

Open the printed URL while the API is running. Kite redirects back to
`http://127.0.0.1:8000/`, and Taurus exchanges the `request_token` into
`KITE_ACCESS_TOKEN` automatically. If the API was not running during login, use
`make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>` as a
manual fallback.

## Local Setup

Prerequisites:

- Python 3.11+
- uv
- pnpm
- Docker Desktop
- make

Install dependencies:

```bash
make setup
make setup-ui
```

Dependency management for this repo is always done through `uv`. If a vendor guide or service integration doc says `pip install`, treat that as the conceptual instruction and execute it with the `uv` workflow instead so the project stays isolated in `.venv`.

Run tests:

```bash
make test
```

Run the release smoke check:

```bash
make taurus-smoke
```

Start the local stack:

```bash
make dev-up
```

Create the schema and seed deterministic mock data:

```bash
make migrate
make seed-mock
make import-mock-news
```

Run the paper MVP workflow:

```bash
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
```

Run data-only Kite market-data commands after adding a valid local
`KITE_ACCESS_TOKEN`:

```bash
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
make paper-loop-kite
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
```

`configs/market_data/kite_nse_cash.yaml` defines the Kite-backed paper universe
when `TAURUS_MARKET_DATA_PROVIDER=kite`. Use `make paper-loop-kite` to run that
Kite-backed universe without overriding it through `SYMBOLS`.

Analysts are enabled with `TAURUS_ENABLED_ANALYSTS`. The default is
`technical`; add `news`, `sentiment`, and `fundamentals` explicitly when you
want those reports.

Verify the API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
```

Stop the local stack:

```bash
make dev-down
```

Run the API directly without Docker:

```bash
make api
```

Run the React dashboard:

```bash
make ui
```

Open `http://localhost:5173`. The React app reads the local FastAPI `/ui/*`
and `/graph/*` endpoints. The run-loop views remain read-only; the graph edge
review route can promote or reject graph candidate edges only when
`TAURUS_GRAPH_ENABLED=true`.

Run a full mock paper loop and open the React dashboard in one command:

```bash
make paper-loop-dashboard
```

This target starts the Docker stack, prepares mock data, runs one paper loop, then starts the React dev server in the foreground.

Run the Streamlit fallback dashboard:

```bash
make dashboard
```

Usage, one-loop observation guidance, known limitations, and operational notes are documented in `docs/TAURUS_USAGE_GUIDE.md`.

## Local Services

- Taurus API: `http://localhost:8000`
- React dashboard: `http://localhost:5173`
- Streamlit fallback dashboard: `http://localhost:8501`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
