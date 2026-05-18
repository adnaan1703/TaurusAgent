# Taurus

Taurus is an observable, paper-trading-first algo trading MVP for Indian cash equities.

M1 provides the project foundation plus deterministic mock market data: local configuration, JSON logging, FastAPI health/data endpoints, Prometheus metrics, Docker Compose services, SQLAlchemy database tables, repositories, and seeded Indian equity-like instruments/candles. It does not include strategies, broker integrations, LLM integrations, real market data ingestion, paper orders, or live trading.

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

Start the local stack:

```bash
make dev-up
```

Create the M1 schema and seed deterministic mock data:

```bash
make migrate
make seed-mock
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

## Local Services

- Taurus API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
