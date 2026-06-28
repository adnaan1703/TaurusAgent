# Taurus Command Reference

Last updated: 2026-06-28

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
- `make validate-technical-v2`: validation stage, current readiness symbol,
  compact backtest profile label, percent, elapsed time, and ETA.
- `make parametric-experiment`: spec loading, expansion, readiness, backtest,
  metric extraction, and result-writing stages with current fold, variant,
  fold x variant counts, percent, elapsed time, and ETA.
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
make validate-technical-v2
make parametric-experiment
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
make import-official-index-data OFFICIAL_INDEX_CSV=/path/to/index.csv
make check-official-index-readiness
make import-official-microstructure-data OFFICIAL_MICROSTRUCTURE_CSV=/path/to/security-wise.csv
make check-official-microstructure-readiness OFFICIAL_MICROSTRUCTURE_SYMBOLS=INFY,TCS
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

Official index and India VIX data:

```bash
make import-official-index-data OFFICIAL_INDEX_CSV=/path/to/nifty50.csv OFFICIAL_INDEX_SYMBOL=NIFTY_50 OFFICIAL_INDEX_NAME="Nifty 50" OFFICIAL_INDEX_FAMILY=benchmark
make import-official-index-data OFFICIAL_INDEX_CSV=/path/to/nifty-it.csv OFFICIAL_INDEX_SYMBOL=NIFTY_IT OFFICIAL_INDEX_NAME="Nifty IT" OFFICIAL_INDEX_FAMILY=sector
make import-official-index-data OFFICIAL_INDEX_CSV=/path/to/india-vix.csv OFFICIAL_INDEX_SYMBOL=INDIA_VIX OFFICIAL_INDEX_NAME="India VIX" OFFICIAL_INDEX_FAMILY=volatility
make check-official-index-readiness OFFICIAL_INDEX_SECTOR_SYMBOLS=NIFTY_IT
```

`make import-official-index-data` accepts CSV rows with columns such as
`index_symbol`, `index_name`, `index_family`, `trade_date`, `open`, `high`,
`low`, `close`, `source`, `source_url`, `timeframe`, and
`data_available_time`. If the symbol, name, family, source, or timeframe are
not present in the CSV, the `OFFICIAL_INDEX_*` Make variables provide them.
Rows are stored in `official_index_candles` with source-row metadata and
availability timestamps. The repository as-of accessors filter by
`data_available_time` so future official rows cannot leak into historical
validation.

`make check-official-index-readiness` writes
`artifacts/technical_validation/official_index_readiness.json` by default and
returns non-zero when required official benchmark, sector-index, or India VIX
history is missing. Defaults require `NIFTY_50` and `INDIA_VIX`; sector indexes
are required only when `OFFICIAL_INDEX_SECTOR_SYMBOLS` is set, for example
`OFFICIAL_INDEX_SECTOR_SYMBOLS=NIFTY_IT,NIFTY_BANK`.

Equivalent direct CLI commands:

```bash
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/import_official_index_data.py import --csv /path/to/nifty50.csv --index-symbol NIFTY_50 --index-name "Nifty 50" --index-family benchmark
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/import_official_index_data.py readiness --sector-symbols NIFTY_IT --output artifacts/technical_validation/official_index_readiness.json
```

Official delivery, circuit, and tradability data:

```bash
make import-official-microstructure-data OFFICIAL_MICROSTRUCTURE_CSV=/path/to/security-wise.csv
make import-official-microstructure-data OFFICIAL_MICROSTRUCTURE_CSV=/path/to/impact-proxy.csv OFFICIAL_MICROSTRUCTURE_IMPACT_COST_SOURCE_KIND=proxy OFFICIAL_MICROSTRUCTURE_IMPACT_COST_PROXY_NAME=avg_trade_value_proxy
make check-official-microstructure-readiness OFFICIAL_MICROSTRUCTURE_SYMBOLS=INFY,TCS
```

`make import-official-microstructure-data` accepts CSV rows with columns such
as `symbol`, `trade_date`, `delivery_quantity`, `delivery_percentage`,
`price_band_percent`, `upper_circuit_price`, `lower_circuit_price`,
`circuit_status`, `circuit_hit`, `impact_cost_bps`,
`impact_cost_source_kind`, `impact_cost_proxy_name`, `average_trade_value`,
`turnover`, `source`, `source_url`, `timeframe`, and
`data_available_time`. Impact-cost fallback rows must set
`impact_cost_source_kind=proxy` and name `impact_cost_proxy_name`; official
impact-cost rows should use `impact_cost_source_kind=official`. Rows are stored
in `official_security_microstructure` with source-row metadata and
availability timestamps. The repository as-of accessors filter by
`data_available_time` so future official microstructure rows cannot leak into
historical validation.

`make check-official-microstructure-readiness` writes
`artifacts/technical_validation/official_microstructure_readiness.json` by
default and returns non-zero when required delivery, circuit, or tradability
history is missing for the requested `OFFICIAL_MICROSTRUCTURE_SYMBOLS`.
Readiness defaults to all three families; narrow a check with
`OFFICIAL_MICROSTRUCTURE_REQUIRED_FAMILIES=delivery,circuit`.

Equivalent direct CLI commands:

```bash
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/import_official_microstructure_data.py import --csv /path/to/security-wise.csv
DATABASE_URL="$DATABASE_URL" PYTHONPATH=packages:. uv run python scripts/import_official_microstructure_data.py readiness --symbols INFY,TCS --output artifacts/technical_validation/official_microstructure_readiness.json
```

Technical validation:

```bash
make validate-technical-v2
make validate-technical-v2 TECHNICAL_VALIDATION_MODE=strong
make validate-technical-v2 TECHNICAL_VALIDATION_SYMBOLS=INFY,TCS
make validate-technical-v2 TECHNICAL_VALIDATION_INCLUDE_V2B=true
make validate-technical-v2 TECHNICAL_VALIDATION_REPORT_ROOT=/tmp/taurus-tech-reports
```

`make validate-technical-v2` writes deterministic machine-readable artifacts
under `artifacts/technical_validation/<run_id>/` and an operator-readable
Markdown report under `docs/reports/technical_validation/<run_id>.md` by
default. Generated report and artifact directories are ignored because they are
run output. Override the report directory with
`TECHNICAL_VALIDATION_REPORT_ROOT=...` when a durable external report location
is preferred.

The standard mode validates a 3-year evaluation window after a 252-trading-day
indicator warm-up. The strong mode uses a 5-year evaluation window with the
same warm-up. The command compares `graph_aware_score_v1`, v1 with graph
contribution weight set to zero, `graph_aware_score_v2`, and v2A with graph
contribution weight set to zero on the same symbols, dates, costs, slippage,
NAV, rebalance cadence, and position limits when local `daily_candles` coverage
is sufficient. v2B is excluded by default until official index and
microstructure data are ready. Re-enable v2B comparison explicitly with
`TECHNICAL_VALIDATION_INCLUDE_V2B=true make validate-technical-v2`; that adds
`graph_aware_score_v2b` and v2B with graph contribution weight set to zero.
This command does not promote v2B.

M82 report artifacts include:

- `technical_agent_predictive_report.json`, `.md`, and
  `technical_agent_prediction_checks.csv` with 5d, 21d, and 63d future-return
  checks, rank correlation, top-vs-bottom spread, confidence calibration,
  coverage/missing-feature diagnostics, and explanation quality.
- `system_backtest_report.json`, `.md`, and
  `system_backtest_profile_summary.csv` with return/CAGR, Sharpe/Sortino,
  drawdown, turnover, win rate/profit factor, selected symbols, cash
  utilization, backtest allocation-score proxy behavior, rejected/trimmed
  counts, inferred sizing failures, and equity curve summaries.
- `profile_comparison_matrix.csv` for cross-profile comparison.
- `promotion_gate.json` with a conservative recommendation of `promote`,
  `keep_opt_in`, or `defer`; the report marks v2B candidate validation as
  disabled unless `TECHNICAL_VALIDATION_INCLUDE_V2B=true` is set.

The promotion gate is report-only. It requires v2A to beat or tie v1 after
costs, avoid material drawdown worsening, keep turnover controlled, show
positive 21d rank/decile evidence, and avoid allocation utilization or sizing
failures. It does not switch `make paper-loop-kite`, `graph_aware_score_v1`, or
`technical_rule_v1` to v2, and it does not promote v2B.

If coverage is insufficient, the command still writes `data_readiness.json` and
`validation_manifest.json`, writes not-run technical/system reports plus a
`defer` promotion gate, prints the missing common-candle count, and names a
deeper Kite import command such as
`TAURUS_MARKET_DATA_LOOKBACK_DAYS=1434 make import-kite-candles`. Set
`TECHNICAL_VALIDATION_STRICT_INSUFFICIENT=true` when automation should treat
short coverage as a non-zero exit. Useful overrides include
`TECHNICAL_VALIDATION_UNIVERSE=configs/market_data/nifty_50_shariah.yaml`,
`TECHNICAL_VALIDATION_ARTIFACT_ROOT=...`,
`TECHNICAL_VALIDATION_REPORT_ROOT=...`,
`TECHNICAL_VALIDATION_INITIAL_CAPITAL_INR=...`,
`TECHNICAL_VALIDATION_MAX_OPEN_POSITIONS=...`,
`TECHNICAL_VALIDATION_PORTFOLIO_BREADTH=...`,
`TECHNICAL_VALIDATION_COST_BPS=...`, and
`TECHNICAL_VALIDATION_SLIPPAGE_BPS=...`. After importing official v2B data,
set `TECHNICAL_VALIDATION_INCLUDE_V2B=true` to include the official-data
candidate in validation output.

M86 used the standard validation mode and produced run
`techval-748ec624a9fe1297` with `status=insufficient_data` and
`promotion_decision=defer`: 282 common candles were available across the
configured 17-symbol validation universe, versus 1009 required. Until a future
complete validation passes the conservative gate, keep `graph_aware_score_v2`
and `graph_aware_score_v2b` opt-in and leave `make paper-loop-kite` on the
canonical v1 strategy. Current validation runs omit v2B by default until its
official-data inputs are populated.

Parametric experiments:

```bash
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_full_feature_sweep.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_macro_sweep.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_sensitivity_sweep.yaml
TAURUS_PROGRESS=plain PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-plan
PARAMETRIC_DRY_RUN=false make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-smoke
PARAMETRIC_DRY_RUN=false PARAMETRIC_JOBS=2 make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-risk
```

`make parametric-experiment` validates a declarative YAML experiment spec.
Dry-run mode prints the expanded variant count, fold count, total work units,
metric IDs, stable variant fingerprints, and planned output paths without
creating `experiments/runs/` or writing to the database. Progress uses
`TAURUS_PROGRESS=auto/plain/false`; the main progress unit is fold x variant.
Specs may use `variants.matrix` alone or add `variants.axes` for grouped
override choices. Each axis has a stable `name`, a list of values with stable
`id` fields, and each value has an `overrides` mapping. The harness crosses
matrix combinations with one selected value from each axis, rejects conflicting
duplicate override paths after adapter normalization, and validates merged
family weights plus the `backtest.max_open_positions` and
`backtest.portfolio_breadth` relationship. Axis-backed dry-run rows include
`axes=<axis>=<value_id>` so operators can see which grouped choices produced a
variant.
Non-dry-run execution supports the `technical_validation_v2a` adapter for
single-window smoke/debug specs and default `v2a_yearly` walk-forward specs. It
runs generated v2A validation profiles through the existing technical
validation/backtest stack, automatically includes canonical
`graph_aware_score_v1` and current `graph_aware_score_v2` baselines, extracts
the requested named metrics, and writes raw values plus numeric deltas versus
both baselines.
The metric registry includes `rank.5d.rank_correlation`,
`rank.5d.top_bottom_decile_spread`, and `rank.5d.hit_rate` for future
short-horizon specs, along with the existing 21d/63d rank metrics and system
metrics.

Specs with `folds.mode: single_window` run one validation window and are useful
for smoke checks. When `folds` is omitted, or when `folds.mode: v2a_yearly` is
set explicitly, the default v2A walk-forward mode runs three chronological
yearly folds across the current standard three-year validation window:
`fold_1` is the oldest year, `fold_2` the middle year, and `fold_3` the latest
year.

Checked-in specs:

- `experiments/specs/v2a_smoke.yaml`: two variants, one explicit
  `single_window` fold, and a tiny metric set for quick CLI, progress, and
  output verification.
- `experiments/specs/v2a_risk_calibration.yaml`: the recommended first real
  sweep. It runs 256 variants across three `v2a_yearly` folds with a bounded
  grid over risk-tilted family weights, negative-risk gates, candidate-breadth
  guardrails, score compression, momentum transform scales, volatility
  transform scales, and return/risk/candidate-breadth/rank-IC metrics.
- `experiments/specs/v2a_full_feature_sweep.yaml`: a deliberate overnight
  template. It declares every tunable v2A feature-weight and feature-transform
  path, widens a curated subset to 512 variants, and includes an explicit
  `execution.max_variants: 512` cap so the above-default expansion is
  intentional. Dry-run it before any non-dry-run execution; widen additional
  matrix lists only with an explicit `PARAMETRIC_MAX_VARIANTS` or
  `--max-variants` override.
- `experiments/specs/v2a_medium_macro_sweep.yaml`: a compact medium-horizon
  macro sweep. It crosses five family-weight trios with three paired
  `portfolio_breadth`/`max_open_positions` choices for 15 variants and 45
  default yearly work units, while adding realized/unrealized P&L and
  closed-trade win/loss economics to the requested comparison metrics.
- `experiments/specs/v2a_medium_sensitivity_sweep.yaml`: a compact
  medium-horizon sensitivity sweep. It keeps current family weights,
  `portfolio_breadth=5`, `max_open_positions=5`, and 21-day rebalancing fixed,
  then runs 19 one-case `sensitivity_case` variants across 57 default yearly
  work units with the same realized/unrealized P&L, closed-trade economics, and
  21d/63d rank diagnostics as the macro sweep.

For staged verification, dry-run specs from smallest to largest: smoke, risk
calibration, full feature, medium macro, then medium sensitivity. M100 closeout
verified all five dry-runs on 2026-06-28: smoke expanded 2 variants / 1 fold /
2 work units; risk calibration expanded 256 variants / 3 folds / 768 work
units; full feature expanded 512 variants / 3 folds / 1536 work units; medium
macro expanded 15 variants / 3 folds / 45 work units; and medium sensitivity
expanded 19 variants / 3 folds / 57 work units. Keep large non-dry-run
executions explicit with `PARAMETRIC_OUTPUT_ROOT` under `/tmp` or another
ignored location, and treat their outputs as evidence only. They do not promote
v2A, implement v2A-SH, or alter paper-loop defaults.

Use `EXPERIMENT_SPEC=...` to choose the YAML spec. Use `PARAMETRIC_JOBS`,
`PARAMETRIC_MAX_VARIANTS`, and `PARAMETRIC_OUTPUT_ROOT` to pass through the CLI
`--jobs`, `--max-variants`, and `--output-root` controls. Matrices default to a
maximum of 500 expanded variants; larger sweeps must explicitly raise
`PARAMETRIC_MAX_VARIANTS` or set `execution.max_variants` in the spec.
`PARAMETRIC_JOBS` is explicit bounded parallelism and defaults to `1`; Taurus
does not auto-detect CPU count for experiment workers. Non-dry-run multi-job
execution uses process workers so CPU-heavy validation/backtest work can run
across cores; each worker opens its own database sessions and writes its own
variant artifacts, so Postgres and disk throughput can still become the
practical limit. Use `TAURUS_PROGRESS=auto/plain/false` to select Rich/TTY
progress, plain stderr progress, or no terminal progress.

Generated run outputs belong under `experiments/runs/<run_id>/` by default,
which is ignored; checked-in specs live under `experiments/specs/` and harness
source lives under `experiments/parametric/`. Each non-dry-run execution writes
an aggregate `comparison.csv` and `manifest.json` at the run root plus
per-variant `comparison.csv`, `manifest.json`, technical validation artifacts,
and operator Markdown reports under `variants/<fingerprint>/<fold_id>/`.
Axis-backed variants include `axis_values` metadata in comparison CSV rows and
variant manifests as a list of `{axis, value_id}` selections. Matrix-only specs
leave that metadata empty while preserving their existing variant override
payloads and fingerprints.
Multi-fold aggregate CSVs include `variant_aggregate` rows with fold count,
mean metric/delta values, and fold min/max/mean/stddev stability columns for
generated variant rows. `promotion_gate.json` remains report-only and does not
promote v2A, v2B, or change canonical paper-loop defaults.

M91 allows the spec schema and the opt-in
`graph_aware_score_v2` strategy path to use the same v2A scoring override
names, including `family_weights.*`, `<family>_weights.<feature>`,
`<family>_transforms.<feature>.scale`, `context_weights.*`,
`confidence_weights.*`, `eligibility.*`, and `score_compression.*`.
Runtime strategy configs pass those overrides under
`technical_ohlcv_v2_params`, and they are parsed only when
`technical_profile: technical_ohlcv_v2` is selected. Empty/default params keep
current v2A scores unchanged, and v1 remains canonical.

The M89-M95 parametric harness sequence is closed. Final closeout verified the
focused backend regression suite, smoke dry-run, risk-calibration dry-run, and
a tiny smoke non-dry-run execution under `/tmp/taurus-parametric-smoke`. The
first recommended real operator action remains a dry-run of
`experiments/specs/v2a_risk_calibration.yaml`; the full-feature spec remains a
deliberate overnight template after dry-run inspection. The harness does not
promote v2A, enable v2B, or change canonical paper-loop defaults.

The M96-M100 v2A experiment redesign sequence is closed. Final closeout
verified focused regression plus dry-runs for smoke, risk calibration, full
feature, medium macro, and medium sensitivity specs. v1 remains canonical,
current v2A remains opt-in, and v2A-SH remains design-only. The next planned
action is M101 cadence-only 5d/10d comparison before any true v2A-SH scoring
profile implementation.

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
STRATEGY=configs/strategies/graph_aware_score_v2b.yaml make paper-loop-kite
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
curl 'http://localhost:8000/graph/neighborhood?node_key=company%3AINFY&status=active&status=candidate&limit=1000'
curl http://localhost:8000/graph/candidate-edges
curl http://localhost:8000/graph/signals
curl http://localhost:8000/graph/bullish-candidates
curl http://localhost:8000/graph/edges/{edge_key}
curl http://localhost:8000/graph/edges/{edge_key}/evidence
curl -X POST http://localhost:8000/graph/edges/{edge_key}/promote
curl -X POST http://localhost:8000/graph/edges/{edge_key}/reject
```

`/graph/neighborhood` accepts any stored `node_key`, repeated `status`
parameters, and a `limit` capped at 1000. When `status` is omitted, it returns
active plus candidate edges; rejected edges are opt-in.

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
