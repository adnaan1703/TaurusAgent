# Taurus Command Reference

Last updated: 2026-06-22

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
- `make import-taurus-graph`: current TaurusData CSV file, rows seen/imported,
  cumulative node/edge/evidence upserts, percent, elapsed time, and ETA.
- `make compute-graph-stats`: source and target symbols, stats window,
  percent, elapsed time, and ETA.
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

After the paper loop progress display completes, `make paper-loop-kite` always
prints a human-readable `LLM Usage Summary` on stderr. Token counts are compacted
for readability, for example `1.55M`, `842K`, and `12.4K`. This summary is not
controlled by a separate flag and does not replace the optional JSON payload.

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
make profile-list
make profile-create PROFILE_ID=client-a PROFILE_DISPLAY_NAME="Client A" PROFILE_CORPUS_INR=250000
make profile-archive PROFILE_ID=client-a
make profile-update-corpus PROFILE_ID=client-a PROFILE_CORPUS_INR=500000
make import-market-data
make import-screener CSV=/path/to/screener.csv
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=YYYY-MM-DD
make project-neo4j-graph
make sync-halal-stocks
```

Profile management uses `scripts/manage_profiles.py` behind the Make wrappers.
The preferred paper profile setting is `TAURUS_PROFILE_ID`; the existing
`TAURUS_PAPER_PORTFOLIO_ID` setting remains a legacy alias and must match if
both are set. `make migrate` creates `taurus_profiles` and seeds the
`local-paper` profile with display name `Local Paper`, INR 10,000 starting
corpus, currency `INR`, and status `ACTIVE`.

`make paper-loop-kite` defaults to `TAURUS_PROFILE_ID=local-paper`. Run
`PROFILE_ID=client-a make paper-loop-kite` to execute the same Kite-backed paper
loop for another active profile; the profile's `starting_corpus_inr` drives
paper cash, account snapshots, allocation fallbacks, and next-open settlement.
Direct script or shell runs should prefer `TAURUS_PROFILE_ID=client-a`.
`TAURUS_PAPER_PORTFOLIO_ID=client-a` remains supported for older local scripts
but is secondary to the preferred profile setting and must match it if both are
present.

Equivalent direct CLI commands:

```bash
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/manage_profiles.py list
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/manage_profiles.py create --profile-id client-a --display-name "Client A" --corpus-inr 250000
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/manage_profiles.py archive --profile-id client-a
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/manage_profiles.py update-corpus --profile-id client-a --corpus-inr 500000
```

Starting corpus can be changed only before trading activity exists for that
profile. Once fills, queued orders, nonzero positions, or non-initial account
snapshots exist, corpus changes are rejected until a later capital-events
milestone adds deposits and withdrawals.

`make taurus-smoke` also exercises multi-profile reads. It creates or reuses a
dedicated `smoke-profile`, runs one bounded paper loop for that profile, and
checks `/profiles`, `/paper/account`, `/paper/orders`, `/ui/overview`,
`/ui/history`, and `/ui/portfolio` with `profile_id`. Override the smoke profile
ID with `TAURUS_SMOKE_PROFILE_ID=...` when needed.

Profile APIs:

```bash
curl http://localhost:8000/profiles
curl http://localhost:8000/profiles/client-a
curl -X POST http://localhost:8000/profiles \
  -H 'Content-Type: application/json' \
  -d '{"profile_id":"client-a","display_name":"Client A","starting_corpus_inr":"250000"}'
curl -X PATCH http://localhost:8000/profiles/client-a \
  -H 'Content-Type: application/json' \
  -d '{"display_name":"Client Alpha"}'
curl -X POST http://localhost:8000/profiles/client-a/archive
```

Profile-scoped read APIs accept `profile_id` and default to the effective
settings profile when it is omitted:

```bash
curl 'http://localhost:8000/runs?profile_id=client-a'
curl 'http://localhost:8000/paper/orders?profile_id=client-a'
curl 'http://localhost:8000/paper/fills?profile_id=client-a'
curl 'http://localhost:8000/paper/account?profile_id=client-a'
curl 'http://localhost:8000/ui/overview?profile_id=client-a'
curl 'http://localhost:8000/ui/history?profile_id=client-a'
curl 'http://localhost:8000/ui/portfolio?profile_id=client-a'
curl 'http://localhost:8000/ui/risk?profile_id=client-a'
```

The React dashboard profile selector writes the same `profile_id` query
parameter, so copied dashboard links preserve the selected profile context.
Portfolio views list recent orders and fills for the selected profile, including
orders whose original run ID differs from the later settlement/account run.

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
PROFILE_ID=client-a make paper-loop-kite
make paper-loop-dashboard
make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1
```

For `make paper-loop-kite`, runtime environment values are resolved in this
order: explicit shell or `make VAR=value` overrides first, values from `.env`
second, and Makefile defaults last. For example,
`make paper-loop-kite TAURUS_TARGET_MARKET_UNIVERSE_PATH=configs/market_data/nifty_50_shariah.yaml`
overrides `.env`, while a plain `make paper-loop-kite` respects the `.env`
value before falling back to `configs/market_data/nifty_500_shariah.yaml`.

Manual EOD paper loop commands, including `make paper-loop-kite`, first import
the latest daily candles, settle any previous `PENDING_NEXT_OPEN` orders at the
first imported candle open after each order's signal trade date, and then run
new after-close analysis/allocation/risk/final approval. When money management
is enabled, `TAURUS_PORTFOLIO_PLAN_ALLOCATION_ENABLED=true` is the default:
active BUYs and executable core BUY candidates are allocated from the portfolio
plan, while `false` keeps the legacy run-level allocator for compatibility
checks. That compatibility flag is intentionally retained for operator
troubleshooting; the default path remains the holistic planner. Threshold
REDUCE/EXIT rows are queued before BUY rows, same-run proceeds are only
spendable after the configured haircut, and the hard cash reserve remains
protected. Orders created by the same EOD run remain queued for the next
available open and do not mutate cash or positions during that run. If an
operator skips a trading day, settlement still uses the first available newer
daily candle after the original signal date. Inspect queued and settled orders
in the React overview/run detail/portfolio pages, or in the Streamlit Orders
fallback. Replay shows queued orders with no paper-fill stage until settlement;
settled replays show the original status history and final simulated fill.
`/metrics` exposes paper-order status labels, including `PENDING_NEXT_OPEN`.
Queued orders do not send fill alerts; terminal simulated settlement fills and
rejections send one alert each. Kite remains data-only.

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
Graph edge payloads expose `provenance_type` (`deterministic`, `derived`, or
`inferred`) instead of edge-level `inferred`; `confidence` remains audit
metadata in the response and does not gate manual review or statistical
auto-promotion. Graph scoring uses active reviewed edges with relationship
strength and graph-stat validation; imported edge confidence is not a
score-weighting input. `evidence_type` describes the source/evidence basis, and
edge `status` records the active/candidate/rejected review lifecycle.

The bundled TaurusData V2 `company_profiles.jsonl` file may contain edge-like
relationship arrays for TaurusData provenance review. TaurusAgent imports the
flattened CSV outputs such as `company_edges.csv`, `edge_candidates.csv`, and
`company_dependencies.csv`; it does not import graph relationships directly
from profile arrays.

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
