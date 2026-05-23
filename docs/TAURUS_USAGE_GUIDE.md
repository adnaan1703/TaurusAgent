# Taurus Usage Guide

Taurus is currently an observable, paper-trading-first MVP. It is designed to let you run a local end-of-day paper trading workflow, inspect every decision artifact, and confirm that no real-money path is active.

The current release uses deterministic mock market data, mock news, mock LLM outputs, and the internal `PaperBroker` by default. Broker sandbox and live trading integrations are deferred.

## Safety Model

The expected local defaults are:

```text
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
TAURUS_LLM_PROVIDER=mock
TAURUS_ALERT_PROVIDER=mock
```

The system rejects live trading mode in the current MVP. Analyst reports, debates, trader proposals, and risk reviews are decision artifacts only. A paper order can be routed only after a final decision is marked `APPROVED_FOR_PAPER`, and the only execution adapter is `PaperBroker`.

## Local Services

When the local stack is running, use these URLs:

- Taurus API: `http://localhost:8000`
- React dashboard: `http://localhost:5173`
- Streamlit fallback dashboard: `http://localhost:8501`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## First-Time Setup

Install dependencies:

```bash
make setup
make setup-ui
```

All Python dependency changes in Taurus should go through `uv` so they stay scoped to the project virtual environment. If a third-party integration guide uses `pip install`, interpret that as "install the package into Taurus's `.venv`" and use the corresponding `uv` command instead.

Start the local stack:

```bash
make dev-up
```

Create database tables and seed the default mock inputs:

```bash
make migrate
make seed-mock
make import-mock-news
```

Run the API and React dashboard:

```bash
make api
make ui
```

Open `http://localhost:5173`.

## Fast Health Checks

Use these checks to confirm the app is alive and still in paper mode:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

Useful signals:

- `/health` shows the service mode and `live_trading_enabled`.
- `/ready` confirms config readiness and broker provider.
- `/metrics` includes runtime, database, data freshness, and paper trading metrics.

## Running One Paper Loop

The most realistic single paper-trading simulation is:

```bash
make paper-loop-once SYMBOLS=INFY
```

For multiple symbols:

```bash
make paper-loop-once SYMBOLS=INFY,RELIANCE,TCS
```

This is an end-of-day batch workflow. It is not a live intraday stream. It uses the latest available daily candles and local inputs, then stores all outputs for inspection.

## What Happens In One Loop

One loop executes this sequence:

1. Migrations run so required tables exist.
2. A `paper_run` record is created with status `RUNNING`.
3. Market data is loaded from the configured provider.
4. Mock news/events are imported.
5. Technical features and strategy signals are computed.
6. Analyst reports are generated for each symbol.
7. A bull/bear research debate is created.
8. A trader proposal is created.
9. The risk review runs, including hard rule checks.
10. The portfolio manager creates the final decision.
11. If approved for paper trading, the decision is routed to `PaperBroker`.
12. Paper orders, fills, positions, and account state are stored.
13. The `paper_run` record is updated to `COMPLETED`, `PARTIAL_FAILED`, or `FAILED`.

The output printed by the command includes the run ID, status, symbols, market data summary, strategy summary, and per-symbol artifact IDs.

## Key Artifacts Created By A Loop

For each symbol, a successful loop can create:

- Analyst reports from technical, news, sentiment, and fundamentals agents.
- A debate report with bull thesis, bear thesis, and manager summary.
- A trader proposal with action, confidence, requested position, stop loss, take profit, and invalidation rules.
- A risk review with risk personas and deterministic hard rule results.
- A final decision with approval status and final action.
- A paper order if the final decision is `APPROVED_FOR_PAPER`.
- Paper fills, including simulated slippage and costs.
- Paper position and account records.
- A replayable decision trail.

## How To Observe A Loop In The React Dashboard

For the normal one-command mock run and dashboard startup:

```bash
make paper-loop-dashboard
```

This starts the Docker stack, runs migrations, seeds mock market data, imports mock news, executes one mock paper loop, and starts the React dashboard on `http://localhost:5173`. The final `make ui` step stays in the foreground; stop it with `Ctrl+C` when finished, then run `make dev-down` to stop Docker services.

For manual API and React dashboard startup:

```bash
make api
make ui
```

Open `http://localhost:5173`.

Use the React dashboard as the primary local observability UI. It is read-only and uses the FastAPI `/ui/*` aggregate endpoints, so it does not start loops, place orders, enable live trading, or mutate Taurus state.

Recommended flow:

1. `Overview`: confirm paper mode, live trading disabled, latest run, latest final decision, latest order, warnings, and active positions.
2. `Run Detail`: inspect run status, schedule, market-data summary, strategy summary, symbol success/failure status, and pipeline progress.
3. `Decision Trail`: inspect one `run_id + symbol` from inputs through analyst reports, debate, trader proposal, risk review, final decision, paper order, fills, and audit log.
4. `Replay`: open a stored `decision_id` to reconstruct the evidence chain.
5. `Risk`: scan hard rules, persona reviews, final decisions, reductions, rejections, and blocks.
6. `Portfolio`: inspect paper account, positions, orders, fills, slippage, costs, and P&L.
7. `History`: search and filter previous paper runs.

If the app has no data yet, run:

```bash
make migrate
make seed-mock
make import-mock-news
make paper-loop-mock
```

If the React app reports that the API is unavailable, run:

```bash
make api
```

## Streamlit Fallback Dashboard

Start the fallback dashboard:

```bash
make dashboard
```

Open `http://localhost:8501`. Use this fallback when you want the older diagnostic tables, direct database views, or a secondary check against the React UI. Use the sidebar `Symbol` filter to select the stock you ran, such as `INFY`.

### Main Dashboard

The main page gives the fastest overview:

- Paper Equity
- Paper Cash
- Paper Run status
- Final Status
- Latest Order status
- Backtest Return
- Scheduled Runs table
- Portfolio table
- Agent Workflow tabs
- Risk And Execution tabs
- News And Freshness tabs

Use this first to confirm whether the latest loop completed and whether an order was routed.

### Agent Workflow

Use this to inspect the reasoning artifacts:

- `Analyst Reports`: per-agent score, confidence, stance, key points, risks, and source IDs.
- `Bull Bear Debate`: bull thesis, bear thesis, consensus, open questions, and manager summary.
- `Trader Proposals`: proposed action, requested position, confidence, stop loss, take profit, and whether risk approval is required.
- `Fundamental Scores`: imported or mock fundamental scoring.
- `Fundamental Metrics`: underlying metric snapshots when available.

### Risk

Use this to inspect the approval gate:

- `Reviews`: overall risk review output.
- `Hard Rules`: deterministic checks such as live-trading guard, kill switch, position cap, open-position cap, stale data, severe event block, and supported instrument.
- `Final Decisions`: final paper approval status and final action.

### Paper Trading

Use this to inspect the paper execution result:

- Account metrics: equity, cash, exposure, realized P&L.
- `Runs`: paper run lifecycle and status.
- `Decisions`: final decisions.
- `Positions`: current paper holdings.
- `Orders`: simulated paper orders.
- `Fills`: simulated fills, costs, and slippage.

### Orders

Use this for a focused execution view:

- `Orders`: order ID, symbol, action, quantity, status, and timestamps.
- `Fills`: fill-level execution details.

### Events

Use this to inspect external-style inputs:

- `Events`: imported news/events, event type, severity, sentiment score, and decayed score.
- `Freshness`: latest available candle, feature, and fundamental timestamps.
- `Ingestion`: news/document ingestion summary.

### Portfolio

Use this to inspect current account and holdings:

- Paper equity
- Cash
- Exposure
- Unrealized P&L
- Positions
- Latest backtest equity curve

## How To Observe A Loop With API Calls

After a loop, use this sequence.

Check run lifecycle:

```bash
curl http://localhost:8000/runs
curl http://localhost:8000/runs/<run_id>
```

Check input data and events:

```bash
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
curl "http://localhost:8000/events?symbol=INFY"
```

Check analyst and research outputs:

```bash
curl "http://localhost:8000/agent-reports?symbol=INFY"
curl "http://localhost:8000/debates?symbol=INFY"
curl "http://localhost:8000/trader-proposals?symbol=INFY"
```

Check risk and approval:

```bash
curl "http://localhost:8000/risk-checks?symbol=INFY"
curl "http://localhost:8000/final-decisions?symbol=INFY"
```

Check paper execution:

```bash
curl "http://localhost:8000/paper/orders?symbol=INFY"
curl "http://localhost:8000/paper/fills?symbol=INFY"
curl "http://localhost:8000/paper/positions?symbol=INFY"
curl http://localhost:8000/paper/account
```

Replay a stored decision:

```bash
curl http://localhost:8000/replay/<decision_id>
```

Replay is the best endpoint when you want to reconstruct why a decision happened. It includes the stored reports, events, debate, proposal, risk review, final decision, paper order/fills, and relevant audit rows when available.

## Running A Full Release Smoke Check

Use this when you want to validate the whole MVP rather than only one paper loop:

```bash
make taurus-smoke
```

This runs the local paper MVP through seeding, mock news, backtest, analyst reports, debate, trader proposal, risk review, final approval, paper execution, paper loop, replay, backup, API checks, and safety checks.

## Backtesting

Run the default deterministic mock backtest:

```bash
make backtest-mock
```

Run with a specific strategy config:

```bash
make backtest-mock STRATEGY=configs/strategies/moving_average_crossover_v1.yaml
make backtest-mock STRATEGY=configs/strategies/blended_score_v1.yaml
```

Run with CSV-backed market data:

```bash
make import-price-csv CSV=mock/market_data/prices_sample.csv
make backtest-real-data
```

Backtest results are visible in the dashboard `Backtests` page and through the main dashboard equity curve.

## Optional Real Local Inputs

The MVP can use local files without external credentials:

Import OHLCV CSV:

```bash
make import-price-csv CSV=/path/to/prices.csv
```

Import Screener fundamentals CSV:

```bash
make import-screener CSV=/path/to/screener.csv
```

Do not commit user CSV exports.

## Alerts

Default alerting is mock-only:

```bash
make alert-smoke
```

Optional Telegram smoke testing requires local uncommitted values:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Then run:

```bash
make alert-test-telegram
```

Alerts are intended for paper fills, paper order rejections, kill-switch blocks, severe-event blocks, stale-data blocks, risk rejections/blocks, and scheduled run failures.

## Backup And Restore

Create a local backup:

```bash
make backup-local
```

Restore from a backup:

```bash
make restore-local BACKUP=backups/taurus-<timestamp>
```

For Postgres restore, explicit confirmation is required:

```bash
RESTORE_CONFIRM=I_UNDERSTAND make restore-local BACKUP=backups/taurus-<timestamp>
```

## Common Operating Patterns

Fresh local run:

```bash
make dev-up
make migrate
make seed-mock
make import-mock-news
make paper-loop-once SYMBOLS=INFY
make api
make ui
```

Inspect latest paper state:

```bash
curl http://localhost:8000/runs
curl http://localhost:8000/paper/orders
curl http://localhost:8000/paper/fills
curl http://localhost:8000/paper/positions
curl http://localhost:8000/paper/account
```

Repeat a batch-style simulation:

```bash
make paper-loop-start SYMBOLS=INFY PAPER_LOOP_ITERATIONS=5 PAPER_LOOP_INTERVAL_SECONDS=60
```

Stop the local stack:

```bash
make dev-down
```

## Current Limitations

- No live broker adapter exists in the MVP.
- No Upstox sandbox adapter is included yet.
- No real-money orders are placed.
- No live intraday or tick-stream evaluation is included.
- The paper loop is a simple local scheduler, not a distributed job system.
- Mock data can look old in freshness views because the fixtures are deterministic historical data.
- The React dashboard is local and unauthenticated; use it only on a trusted development machine/network.
- Streamlit remains available as a fallback diagnostic dashboard.

## Where To Go Next

Use these documents for deeper operational detail:

- `docs/TAURUS_MVP_RELEASE.md`: release assumptions and known limitations.
- `docs/TAURUS_OPERATIONS_RUNBOOK.md`: alerts, replay, backup, and restore procedures.
- `docs/TAURUS_COMMANDS.md`: full command reference.
- `docs/UPSTOX_INTEGRATION_PLAN.md`: deferred broker integration plan.
