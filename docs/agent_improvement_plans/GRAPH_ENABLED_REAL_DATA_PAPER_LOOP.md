# Graph-Enabled Real-Data Paper Loop Plan

Last reviewed: 2026-05-30

Execution order: 4 of 10. Run this after Docker/Postgres, real LLM provider,
and Kite-only market data migrations. It assumes the real-data paper command
uses Kite candles/quotes and that the technical analyst can use the default LM
Studio provider.

## Summary

Make Taurus graph intelligence part of the mainstream real-data paper-trading
loop while keeping the graph path mock-free.

The current graph implementation is not broken; it is intentionally disabled by
default:

- `TAURUS_ENABLED_ANALYSTS` defaults to `technical`, so `GraphAnalystAgent` runs
  only when the roster explicitly includes `graph`.
- `TAURUS_GRAPH_RISK_ENABLED=false` by default, so graph concentration checks are
  skipped unless enabled.
- M20 graph milestones required graph analyst and graph risk to remain opt-in
  until graph data, statistical validation, and concentration limits were
  reviewed.
- `configs/strategies/graph_aware_score_v1.yaml` exists, but the paper run path
  does not yet load graph signals into target selection the way graph-aware
  backtesting does.

Target enablement should be scoped to the real-data paper flow, not the mock
development loop.

## Target State

- The real-data paper path enables graph intelligence by default:
  - `TAURUS_ENABLED_ANALYSTS=technical,graph`
  - `TAURUS_GRAPH_ENABLED=true`
  - `TAURUS_GRAPH_RISK_ENABLED=true`
  - `STRATEGY=configs/strategies/graph_aware_score_v1.yaml`
- `GraphAnalystAgent` is part of the normal analyst report roster and feeds the
  existing debate, trader proposal, risk review, and final approval path.
- Graph-aware strategy scoring uses latest validated graph signals during paper
  target selection.
- Graph risk concentration checks participate in `RiskEngine` for BUY proposals
  and can pass, warn, reduce, reject, or block through existing risk result
  structures.
- Graph signals never bypass debate, trader proposal, risk review, final
  approval, or paper execution safeguards.
- Candidate graph edges do not affect default paper decisions. They must be
  promoted to active before influencing analyst, strategy, or risk behavior.

## Mock-Free Boundary

This plan applies to the graph path only.

No production mock provider, mock graph data generator, or mock graph analyst
should be created for:

- `GraphAnalystAgent`
- graph signal loading
- graph statistical validation
- graph-aware strategy scoring
- graph concentration risk
- graph readiness checks

Tests may use deterministic Docker Postgres test databases or test-only fakes,
but they must not add runtime graph mocks or temporary SQLite databases.

Existing non-graph mocks in Taurus are outside this plan. In particular, the
current paper loop still has separate mock concerns such as mock LLM defaults,
mock news import, mock alert delivery, and the paper broker simulator. Those
should be handled by their own migration plans.

## Implementation Changes

### Real-Data Paper Profile

- Update `make paper-loop-kite`, or add a dedicated real-data graph paper target,
  so the default real-data paper command enables:
  - `TAURUS_ENABLED_ANALYSTS=technical,graph`
  - `TAURUS_GRAPH_ENABLED=true`
  - `TAURUS_GRAPH_RISK_ENABLED=true`
  - `STRATEGY=configs/strategies/graph_aware_score_v1.yaml`
- Do not change the mock development loop to graph-enabled by default.
- Document the canonical command in `docs/TAURUS_COMMANDS.md`.

### Graph Readiness Preflight

Add a preflight that runs before graph-enabled paper execution and fails fast
with clear operator guidance when graph inputs are not ready.

The preflight should verify:

- Graph company nodes and active edges exist for the selected universe.
- Graph edge stats have been computed for the latest available real candle date.
- At least one selected symbol has validated graph evidence or a validated graph
  relationship available.
- Graph risk limits are configured and parse successfully.
- Graph-enabled paper runs are not silently using an empty graph database.

The preflight must not auto-create graph fixtures or seed mock graph data. If
data is missing, it should tell the operator to run the real graph import and
stats commands, for example:

```bash
make import-taurus-graph
make compute-graph-stats
```

### Paper Target Selection

Bring the paper loop in line with the graph-aware backtest pattern.

- Load latest graph signals for the paper universe before target selection.
- When the configured strategy exposes `select_targets_with_graph`, call it with
  `graph_signals_by_symbol`.
- For real-data universe mode, use graph-aware targets plus current open
  positions as the symbols that move through the analyst/debate/trader/risk
  pipeline.
- For explicit `SYMBOL` or `SYMBOLS` runs, honor the requested symbols but record
  whether each one was selected by the graph-aware strategy.
- Include graph strategy metadata in paper run artifacts:
  - graph signal count loaded
  - symbols with graph signals
  - symbols selected by graph-aware target selection
  - graph strategy config path

### Graph Analyst

- Keep `GraphAnalystAgent` deterministic and LLM-free.
- Use active graph edges by default for mainstream paper reports.
- Store graph signals and graph signal contributions for auditability.
- Include `GraphAnalystAgent` reports in the existing analyst report repository
  so bull/bear debate and research manager scoring naturally consume them.
- Preserve neutral output for manual runs where no validated graph evidence
  exists, but graph-enabled scheduled paper runs should fail readiness if the
  whole selected universe lacks usable graph evidence.

### Graph Risk

- Keep graph risk inside the existing `RiskEngine.evaluate()` BUY-proposal path.
- Enable `TAURUS_GRAPH_RISK_ENABLED=true` for real-data paper runs only after
  readiness passes.
- Use active graph edges for static exposure categories.
- Use statistically validated graph stats for correlated cluster exposure.
- Continue returning normal `HardRuleResult` rows so the dashboard and audit
  trail can explain any warn, reduce, reject, or block decision.

### API And React Dashboard

- Extend existing dashboard graph, overview, decision trail, and risk surfaces.
- Overview/run history should show whether a run used the graph-enabled
  real-data profile, graph signal count, graph-selected symbols, and graph risk
  enabled status.
- Decision Trail should show which symbols were selected by graph-aware target
  selection versus explicit/manual selection or open-position inclusion.
- Risk views should show graph concentration hard-rule rows with the same
  status vocabulary used by other risk checks.
- Graph pages should keep candidate-edge review separate from active graph
  evidence that can influence paper decisions.

## Reliability And Prediction Quality

Graph should improve prediction only when its evidence is measurable and
auditable.

- Treat graph as an additional research signal, not an order generator.
- Require statistical validation before graph relationships affect scoring.
- Keep edge contributions explainable at the signal and analyst-report level.
- Track graph performance by edge type in backtests before raising graph weights.
- Start with conservative graph strategy weights, such as the existing
  `graph_weight: 0.35`, and adjust only after backtest and paper-run review.
- Keep concentration risk conservative so graph can reduce correlated exposure
  even when graph analyst scoring is bullish.

## Test Plan

- Config/profile tests:
  - core defaults remain mock/dev friendly
  - real-data paper graph profile enables `technical,graph`
  - graph risk is enabled only in the real-data graph paper path
- Readiness tests:
  - passes with imported graph rows and computed stats
  - fails with no graph nodes
  - fails with no active edges for the selected universe
  - fails with no graph stats when graph-aware scoring is required
- Paper service tests:
  - graph signals are loaded before target selection
  - `select_targets_with_graph` is called when available
  - graph-selected targets flow through analyst, debate, trader, risk, final
    approval, and paper execution
  - paper run artifacts expose graph signal and target-selection metadata
- Analyst/risk tests:
  - `GraphAnalystAgent` appears in the roster for graph-enabled paper runs
  - graph risk emits graph concentration hard-rule results on BUY proposals
  - candidate edges do not affect default graph analyst, strategy, or risk
- Mock guard:
  - verify production graph modules do not import or create mock providers:

```bash
rg -n "mock|Mock" \
  packages/taurus_core/agents/graph_analyst.py \
  packages/taurus_core/risk/graph_concentration.py \
  packages/taurus_core/strategies/graph_aware.py \
  packages/taurus_core/graph
```

Recommended verification:

```bash
uv run pytest \
  tests/unit/test_graph_analyst.py \
  tests/unit/test_graph_risk.py \
  tests/unit/test_graph_stats.py \
  tests/unit/test_graph_backtesting.py

make test
make lint
```

## Assumptions

- Real-data graph enablement means the Kite-backed paper path, not all paper
  commands.
- The graph path must remain mock-free, but this plan does not remove unrelated
  runtime mocks from LLM, news, alerts, market data, or paper execution.
- Candidate graph edges remain review-only until promoted.
- Neo4j is not required for mainstream graph paper trading; Postgres graph
  tables remain the source of truth.
