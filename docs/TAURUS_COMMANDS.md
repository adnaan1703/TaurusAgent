# Taurus Command Reference

Last updated: 2026-06-04

This file lists active Taurus commands and project-local Codex approval policy.
Historical milestone command logs were removed during docs cleanup; use Git
history if old command transcripts are needed.

Taurus uses Docker Postgres as the canonical database. Command examples should
use the default Postgres URL or an explicit Postgres `DATABASE_URL`, not SQLite.
Runtime market data is Kite-only; current workflows use Kite commands and
`make import-market-data`.

## Terminal Progress Controls

Long-running terminal commands show progress on stderr. The plain fallback
redraws one terminal line instead of printing a line for every progress event:

- `make import-kite-candles`: current symbol, imported candles, cumulative
  candle count, percent, elapsed time, and ETA.
- `make compute-graph-stats`: current edge/window, source and target symbols,
  validated/insufficient/promoted counts, percent, elapsed time, and ETA.
- `make paper-loop-kite`: iteration, run ID, setup stage, analyzed symbols,
  current symbol pipeline stage, succeeded/failed counts, elapsed time, and
  approximate ETA.

`TAURUS_PROGRESS=auto` is the default. Interactive terminals use Rich progress;
CI and non-TTY streams use the plain redraw fallback. Set
`TAURUS_PROGRESS=false` to disable terminal progress:

```bash
TAURUS_PROGRESS=false make compute-graph-stats
```

`make paper-loop-kite` suppresses the final machine-readable JSON by default so
the terminal output remains readable. Use `PAPER_LOOP_KITE_JSON=true` to print
the JSON summary for automation:

```bash
make paper-loop-kite PAPER_LOOP_KITE_JSON=true
```

`make paper-loop-kite` also defaults to `TAURUS_LOG_LEVEL=WARNING` so routine
structured INFO logs do not interrupt the terminal progress display. Use
`PAPER_LOOP_KITE_LOG_LEVEL=INFO` when debugging and you want the per-event JSON
logs in the terminal:

```bash
make paper-loop-kite PAPER_LOOP_KITE_LOG_LEVEL=INFO
```

## Current Make Targets

Setup and checks:

```bash
make setup
make setup-ui
make test
make lint
make test-ui
make build-ui
make taurus-smoke
make llm-smoke
```

Local services:

```bash
make dev-up
make dev-down
make api
make ui
make dashboard
```

Database and data:

```bash
make migrate
make import-market-data
make import-screener CSV=/path/to/screener.csv
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=YYYY-MM-DD
make project-neo4j-graph
make sync-halal-stocks
```

Kite:

```bash
make kite-login-url
make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
```

Paper workflow:

```bash
make backtest-mock
make import-mock-news
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make paper-loop-once SYMBOLS=INFY,TCS
make paper-loop-start PAPER_LOOP_ITERATIONS=5
make paper-loop-kite
make paper-loop-dashboard
make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1
```

Manual EOD paper loop commands, including `make paper-loop-kite`, first import
the latest daily candles, settle any previous `PENDING_NEXT_OPEN` orders at the
first imported candle open after each order's signal trade date, and then run
new after-close analysis/allocation/risk/final approval. Orders created by the
same EOD run remain queued for the next available open and do not mutate cash or
positions during that run. If an operator skips a trading day, settlement still
uses the first available newer daily candle after the original signal date.
Inspect queued and settled orders in the React overview/run detail/portfolio
pages, or in the Streamlit Orders fallback. Replay shows queued orders with no
paper-fill stage until settlement; settled replays show the original status
history and final simulated fill. `/metrics` exposes paper-order status labels,
including `PENDING_NEXT_OPEN`. Queued orders do not send fill alerts; terminal
simulated settlement fills and rejections send one alert each. Kite remains
data-only.

Replay, alerts, and backup:

```bash
make alert-smoke
make alert-test-telegram
make replay-decision DECISION_ID=sample
make backup-local
make backup-db
make restore-local BACKUP=/path/to/backup RESTORE_CONFIRM=I_UNDERSTAND
```

Several command names still include `mock` for historical compatibility. In the
current runtime they use Postgres, Kite-imported candles, and the configured
real LLM provider where the workflow calls an LLM.

## API Smoke Checks

Health and observability:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

Data and workflow:

```bash
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
curl http://localhost:8000/events
curl "http://localhost:8000/agent-reports?symbol=INFY"
curl http://localhost:8000/debates
curl http://localhost:8000/trader-proposals
curl http://localhost:8000/risk-reviews
curl http://localhost:8000/final-decisions
curl http://localhost:8000/paper/orders
curl http://localhost:8000/paper/fills
curl http://localhost:8000/paper/positions
curl http://localhost:8000/paper/account
curl http://localhost:8000/runs
```

React aggregate API:

```bash
curl http://localhost:8000/ui/overview
curl http://localhost:8000/ui/history
curl http://localhost:8000/ui/risk
curl http://localhost:8000/ui/portfolio
curl http://localhost:8000/ui/shariah
curl http://localhost:8000/ui/runs/{run_id}
curl http://localhost:8000/ui/runs/{run_id}/symbols/INFY/decision-trail
curl http://localhost:8000/ui/replay/{decision_id}
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
curl -X POST http://localhost:8000/graph/edges/{edge_key}/promote
curl -X POST http://localhost:8000/graph/edges/{edge_key}/reject
```

Candidate edge review requires `TAURUS_GRAPH_ENABLED=true`.

## Codex Project-Local Prefix Allowlist

Taurus command approvals are stored in:

```text
.codex/rules/default.rules
```

Codex loads project-local rules only when the project is trusted. This repo is
trusted in the local user config:

```toml
[projects."/Users/adnaan/Workbench/TaurusAgent"]
trust_level = "trusted"
```

The rules file uses this format:

```text
prefix_rule(pattern=["make", "test"], decision="allow")
```

Keep the project-local allowlist aligned with active Make targets and stable
local smoke checks only. The allowlist should cover:

- Active `make` targets listed in this file.
- `uv run` for project-local Python commands.
- `docker info`, `docker compose`, and `open -a Docker` for local service
  management.
- Narrow `pkill -f` rules for the local Uvicorn and Streamlit commands.
- Stable `curl` smoke endpoints only.

Do not allow nonexistent Make targets, one-off run IDs, temporary output files,
unconstrained shell commands, bare `curl`, bare `uv`, `rm`, or broad Python
commands. If a grouped API check is needed, prefer adding a project `make`
target in a future milestone and approving that target.

## Milestone Cleanup Rule

At the end of every milestone, inspect the global Codex rules file:

```text
/Users/adnaan/.codex/rules/default.rules
```

Only entries after the user's `# END MY CUSTOM ADDITION` marker should be
treated as accidental approvals from Taurus work. Move any Taurus-specific
allow prefixes from that section into `.codex/rules/default.rules` if they are
missing, document them in this file, and remove them from the global rules file.
Do not move unrelated global approvals into this project.
