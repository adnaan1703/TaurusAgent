# Taurus

Taurus is an observable, paper-trading-first algo trading MVP for Indian cash equities.

The paper-trading MVP and the M21-M30 functional migration sequence are complete. The React run-loop observability dashboard is the primary local UI. Runtime market data is Kite-only: Taurus can sync Kite instruments, import Kite daily candles, persist latest OHLC/LTP quote snapshots, run graph-aware backtests, analyst reports, bull/bear debate, position-aware trader proposals, deterministic risk review, final approval with optional LLM explanations, PaperBroker execution, scheduled paper loops, opt-in market-hours position monitoring, replay, backup/restore, API, React dashboard, Streamlit fallback dashboard, Prometheus metrics, and Grafana dashboards.

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

Do not commit real API keys, broker credentials, Telegram tokens, Kite tokens,
or user CSV exports. Use `.env` locally if needed later; it is ignored by Git.

Kite credentials, when used, also stay local:

```bash
KITE_API_KEY=
KITE_API_SECRET=
KITE_ACCESS_TOKEN=
```

The access token is a short-lived manual Kite Connect login artifact. If Kite
commands fail with an expired-token message, generate a fresh token locally and
update `.env`; do not put credentials in tracked files or command references.

LLM-backed analyst, research-debate, trader proposal, and final-decision
explanation workflows use real providers only. The default is LM Studio:

```bash
TAURUS_LLM_PROVIDER=lmstudio
TAURUS_LLM_BASE_URL=http://localhost:1234/v1
TAURUS_LLM_MODEL=
TAURUS_LLM_TIMEOUT_SECONDS=20
```

Start a compatible LM Studio local server before running analyst, debate,
trader-proposal, final-approval, or paper-loop workflows. Hosted providers are
explicit opt-ins: `openai` requires `OPENAI_API_KEY` API billing, and `gemini`
requires `GEMINI_API_KEY`. Taurus does not use ChatGPT subscriptions, browser
sessions, cookies, or OAuth workarounds for backend inference.

If `TAURUS_LLM_MODEL` is blank, Taurus uses the provider default from
`packages/taurus_core/config.py`.

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

Taurus uses Docker Postgres as its canonical database. The default database URL
is `postgresql+psycopg://taurus:taurus@localhost:5432/taurus`; SQLite URLs are
rejected in runtime and tests.

Create the schema and import Kite market data:

```bash
make migrate
make import-market-data
make import-mock-news
```

Run the paper MVP workflow. Several command names still include `mock` for
historical compatibility, but they now use Postgres, Kite-imported candles, and
the configured real LLM provider where the workflow calls an LLM:

```bash
make backtest-mock
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make paper-loop-kite
make replay-decision DECISION_ID=sample
make backup-local
```

These analyst, debate, trader-proposal, final-approval, and paper-loop commands call the
configured real LLM provider. `BullResearcherAgent` uses the provider for
evidence-bound bullish research, `BearResearcherAgent` uses it for
evidence-bound bearish research, `ResearchManagerAgent` uses it for bounded
debate synthesis, and `TraderAgent` uses it for after-close lifecycle proposal
reasoning. `PortfolioManagerAgent` uses it only to enrich the final-decision
reason and model metadata after deterministic approval, rejection, or no-action
fields are fixed. Deterministic trader guardrails, risk, final approval, and
paper-broker safeguards remain authoritative. For local no-cost paper runs, keep
LM Studio running or explicitly configure a hosted provider and model.

Run data-only Kite market-data commands after adding a valid local
`KITE_ACCESS_TOKEN`:

```bash
make kite-sync-instruments
make import-kite-candles
make import-market-data
make kite-ltp-smoke
make import-taurus-graph
make compute-graph-stats
make paper-loop-kite
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
```

`configs/market_data/nifty_500_shariah.yaml` defines the default Kite-backed paper universe
when `TAURUS_MARKET_DATA_PROVIDER=kite`. `make paper-loop-kite` is the canonical
real-data paper profile: it analyzes the full configured universe, applies
run-level allocation, routes only allocated/risk-approved paper decisions, and
keeps execution inside the local `PaperBroker` simulation. The profile enables
the technical and graph analysts, graph readiness preflight, graph-aware
strategy ranking, graph concentration risk, and position-aware after-close
lifecycle reviews. Full-universe runs are longer and can use more LLM/API
resources; progress output shows setup, per-symbol analysis, allocation, risk,
final-decision, and execution routing stages. During debugging, pass
`SYMBOL=INFY` or `SYMBOLS=INFY,TCS` to keep the run bounded to those explicit
symbols plus any open paper positions. Paper account state persists by
`TAURUS_PAPER_PORTFOLIO_ID` across run IDs.

Market-hours monitoring is disabled by default. `make position-monitor` respects
that default and exits without polling unless you opt in with
`POSITION_MONITOR_ENABLED=true`. When enabled, it polls open paper
positions during market hours using Kite OHLC/LTP snapshots, persists the quote
snapshot, checks stored stop-loss and take-profit percentages from the active
trade thesis, and creates `market_hours` `EXIT` or `REDUCE` lifecycle proposals
through the same TraderAgent, RiskReview, PortfolioManagerAgent, and PaperBroker
trail. It does not place real broker orders, broker-native stop-losses, or OCO
orders.

Analysts are enabled with `TAURUS_ENABLED_ANALYSTS`. The config default is
`technical`; add `news`, `sentiment`, `fundamentals`, and `graph` explicitly
when you want those reports. The canonical `make paper-loop-kite` target
overrides the roster to `technical,graph` and fails fast if reviewed active graph
edges, latest graph stats, or usable graph signals are missing. Candidate graph
edges stay review-only until promoted to active.

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

Run the API with the Docker Postgres service available:

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

Neo4j is optional and disabled by default. To rebuild the disposable read-model
projection from Postgres graph tables, start the Compose profile and enable the
projection command explicitly:

```bash
docker compose --profile neo4j up -d neo4j
TAURUS_NEO4J_ENABLED=true make project-neo4j-graph
```

Compute graph edge validation stats from existing daily candles:

```bash
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=2024-12-17
```

Automatic graph candidate promotion remains disabled by default with
`TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false`.

Run the Kite-backed graph paper loop and open the React dashboard in one command:

```bash
make paper-loop-dashboard
```

This target starts the Docker stack, imports market data and graph prerequisites,
imports mock news for the current risk/news context, runs one paper loop, then
starts the React dev server in the foreground.

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
- Neo4j, optional profile only: browser `http://localhost:7474`, Bolt `localhost:7687`
