# Taurus

Taurus is an observable, paper-trading-first algo trading MVP for Indian cash equities.

M13 is the current paper-trading MVP release. It can run the local mock-data flow end to end: market data seeding, news/events, backtests, analyst reports, bull/bear debate, trader proposal, risk review, final approval, PaperBroker execution, scheduled paper loop, replay, backup, API, dashboard, Prometheus metrics, and Grafana dashboards.

Broker sandbox and live broker integration are intentionally deferred. See `docs/UPSTOX_INTEGRATION_PLAN.md` for the post-MVP broker path.

## Safety Defaults

Live trading is disabled by default and rejected by the config loader.

```bash
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
```

Do not commit real API keys, broker credentials, or tokens. Use `.env` locally if needed later; it is ignored by Git.

## Local Setup

Prerequisites:

- Python 3.11+
- uv
- Docker Desktop
- make

Install dependencies:

```bash
make setup
```

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

Verify the API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
```

Stop the local stack:

```bash
make dev-down
```

Run the API directly without Docker:

```bash
make api
```

Run the dashboard:

```bash
make dashboard
```

Usage and one-loop observation guidance is documented in `docs/TAURUS_USAGE_GUIDE.md`. Release assumptions and known limitations are documented in `docs/TAURUS_MVP_RELEASE.md`. Operational commands and recovery steps are documented in `docs/TAURUS_OPERATIONS_RUNBOOK.md`.

## Local Services

- Taurus API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
