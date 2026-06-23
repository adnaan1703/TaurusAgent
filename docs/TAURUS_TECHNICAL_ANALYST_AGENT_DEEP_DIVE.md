# TechnicalAnalystAgent Deep Dive

This document explains the current implementation of `TechnicalAnalystAgent`:
what it reads, how it builds its technical view, what it writes, and what
operators should inspect when debugging a paper run.

For the broader pipeline, see `docs/TAURUS_AGENT_ARCHITECTURE.md`. For table
definitions, see `docs/TAURUS_DATABASE_TABLES.md`.

## Role in the Decision Pipeline

`TechnicalAnalystAgent` is an evidence-producing analyst. It does not place
orders, size positions, approve risk, or decide final buy/sell actions.

Its responsibility is to convert market-derived technical evidence into an
`AnalystReport` that downstream agents can debate.

```text
daily_candles / feature_values / backtest_signals
  -> TechnicalAnalystAgent
  -> analyst_reports
  -> BullResearcherAgent / BearResearcherAgent
  -> ResearchManagerAgent
  -> TraderAgent
  -> Allocation
  -> Risk
  -> PortfolioManagerAgent
  -> ExecutionRouter
```

Main implementation files:

| Area | File |
|---|---|
| Agent implementation | `packages/taurus_core/agents/technical_analyst.py` |
| Analyst suite runner | `packages/taurus_core/agents/runner.py` |
| Feature construction | `packages/taurus_core/features/store.py` |
| Official context construction | `packages/taurus_core/features/official_context.py` |
| Indicator math | `packages/taurus_core/features/technical.py` |
| Shared technical scoring | `packages/taurus_core/features/technical_signal.py` |
| Analyst report schema | `packages/taurus_core/agents/schemas.py` |
| Persistence models | `packages/taurus_core/db/models.py` |
| Persistence repository | `packages/taurus_core/db/repositories.py` |
| Paper-run orchestration | `packages/taurus_core/paper_trading/service.py` |

## Runtime Entry Point

During a paper run, `PaperRunService` calls `run_analyst_suite()` for each
symbol selected for analysis.

`run_analyst_suite()` validates the instrument, builds the configured analyst
roster, runs each analyst, and persists the resulting reports with
`AnalystReportRepository.replace_for_run_symbol()`.

For `make paper-loop-kite`, the usual enabled analyst roster is:

```text
technical,graph
```

That means each analyzed symbol normally gets one `TechnicalAnalystAgent`
report and one `GraphAnalystAgent` report.

## Inputs

The default direct method call is:

```python
TechnicalAnalystAgent.run(symbol=symbol, run_id=run_id)
```

M79 added optional profile-gated inputs for v2A:

```python
TechnicalAnalystAgent.run(
    symbol=symbol,
    run_id=run_id,
    technical_profile="technical_ohlcv_v2",
    feature_snapshot=snapshot,
    universe_technical_context=context,
)
```

M85 added optional profile-gated inputs for v2B:

```python
TechnicalAnalystAgent.run(
    symbol=symbol,
    run_id=run_id,
    technical_profile="technical_official_v2b",
    feature_snapshot=snapshot,
    universe_technical_context=context,
    official_technical_context=official_context,
)
```

If those optional arguments are omitted, the analyst keeps the legacy
`technical_rule_v1` behavior.

The agent also receives these constructor dependencies:

| Input | Source | Purpose |
|---|---|---|
| `session` | SQLAlchemy session | Reads market, feature, and signal tables. |
| `llm_provider` | `build_llm_provider(settings)` | Produces the final structured analyst report JSON. |
| `symbol` | Paper run / analyst suite | Stock being analyzed. |
| `run_id` | Paper run | Durable lineage for the generated analyst report. |
| `technical_profile` | Analyst runner / paper strategy profile | Defaults to `technical_rule_v1`; opt-in `technical_ohlcv_v2` selects v2A scoring, while opt-in `technical_official_v2b` selects official-data v2B scoring. |
| `feature_snapshot` | Paper strategy stage or direct caller | Optional in-memory v2A snapshot so the analyst can reuse strategy-built features. |
| `universe_technical_context` | Paper strategy stage or direct caller | Optional DB-free cross-sectional context for v2A scoring. |
| `official_technical_context` | Paper strategy stage or direct caller | Optional as-of official-data context required for v2B scoring. |

## Database Tables Read

Taurus uses one application Postgres database. The technical-analysis path uses
several tables inside it.

| Table | Read by | Purpose |
|---|---|---|
| `instruments` | `run_analyst_suite()` | Confirms the symbol exists before analysts run. |
| `feature_values` | `TechnicalAnalystAgent._persisted_feature_snapshot()` | Optional precomputed technical feature snapshots. |
| `daily_candles` | `TechnicalAnalystAgent._latest_feature_snapshot()` | Source OHLCV history when no persisted feature snapshot is available. |
| `backtest_signals` | `TechnicalAnalystAgent._latest_signal()` | Optional latest strategy signal that can override v1 scoring; v2 stores it only as audit metadata. |
| `official_index_candles` | `build_official_technical_context()` for v2B | Stores official benchmark, sector-index, and India VIX history for v2B market-relative, sector-relative, and regime features. |
| `official_security_microstructure` | `build_official_technical_context()` for v2B | Stores official delivery, circuit/price-band, and tradability rows for v2B microstructure features. |

Important nuance: both `feature_values` and `backtest_signals` lookups are
symbol-based. The current `TechnicalAnalystAgent` does not filter these lookups
by the current `paper_runs.run_id`.

## Feature Snapshot Selection

The agent first tries to load a persisted feature snapshot:

```text
feature_values
  -> latest snapshot_id for symbol
  -> all rows for that snapshot_id
  -> FeatureSnapshot(values={feature_name: feature_value})
```

The latest persisted snapshot is selected by:

1. Matching `FeatureValueModel.symbol`.
2. Ordering by `feature_time DESC`.
3. Breaking ties with `created_at DESC`.
4. Taking one `snapshot_id`.

If no persisted feature snapshot exists, the agent falls back to raw candles:

```text
daily_candles
  -> DailyCandle history
  -> TechnicalFeatureService.build_snapshot()
  -> in-memory FeatureSnapshot
```

This fallback snapshot is not automatically persisted to `feature_values` by
`TechnicalAnalystAgent`.

## Indicators Built

`TechnicalFeatureService` currently builds the following default features:

| Feature family | Defaults |
|---|---|
| Simple moving averages | `sma_5`, `sma_10`, `sma_20`, `sma_30`, `sma_50` |
| Exponential moving averages | `ema_12`, `ema_26` |
| Returns | `return_1d`, `return_5d`, `return_20d` |
| RSI | `rsi_14` |
| ATR | `atr_14` |
| Volatility | `volatility_20` |
| Volume z-score | `volume_z_score_20` |

`TechnicalFeatureService.from_strategy_parameters()` can add SMA windows from
strategy parameters named `fast_window` and `slow_window`. It also supports an
opt-in `technical_ohlcv_v2` feature suite when strategy parameters set:

```yaml
technical_feature_version: technical_ohlcv_v2
```

The opt-in suite adds the M75 OHLCV primitives needed for later v2A work:
MACD, ADX/+DI/-DI, Bollinger bands, 20/50/252-day breakout distances,
52-week-high distance, ATR percent, traded value, average traded value,
turnover z-score, and 63/126/252-day volatility-adjusted returns. The canonical
`graph_aware_score_v1` strategy does not set this parameter, so current paper
loop behavior remains on the v1 feature set. The opt-in
`graph_aware_score_v2` strategy sets both `technical_feature_version:
technical_ohlcv_v2`, `technical_profile: technical_ohlcv_v2`, and
`technical_analyst_profile: technical_ohlcv_v2`, which wires both the strategy
ranking path and the technical analyst path into v2A when that strategy config
is explicitly selected.

## Score Calculation

The deterministic technical score is computed before the LLM report is created.
For the default `technical_rule_v1` profile, `TechnicalAnalystAgent` owns the
database reads and snapshot selection, then passes a `FeatureSnapshot | None`
plus an optional `TechnicalBacktestSignal` to
`TechnicalSignalService.score_analyst_rule()`.

`TechnicalSignalService` returns a DB-free `TechnicalSignalResult` containing
the raw score, bounded report score, confidence, score source, key points,
source IDs, component values, missing features, and metadata. The agent copies
that result into the LLM context and into `AnalystReport.score_metadata`.

The bounded report score remains clamped to `[-1, 1]` and quantized to
`0.0001`.

### If a Backtest Signal Exists

If `_latest_signal()` finds a `backtest_signals` row, the agent converts it to
a `TechnicalBacktestSignal`, and the shared service lets that signal drive the
score:

```python
signed = latest_signal.score if latest_signal.action == "BUY" else -latest_signal.score
score = clamp(signed, -1, 1)
```

So a latest `BUY` signal contributes positively. Any other action is treated as
negative for score purposes.

### If No Backtest Signal Exists

If there is no latest backtest signal, the shared service computes the score
from feature values:

```text
score =
  return_20d * 1.8
+ return_5d * 0.8
+ ema_trend * 1.2
+ ((rsi_14 - 50) / 50) * 0.30
- volatility_20 * 0.75
```

Where:

```text
ema_trend = (ema_12 / ema_26) - 1
```

This rewards:

| Signal | Effect |
|---|---|
| Positive 20-day return | Bullish |
| Positive 5-day return | Bullish |
| `ema_12` above `ema_26` | Bullish trend |
| RSI above 50 | Positive momentum |
| Lower volatility | Less penalty |

It penalizes:

| Signal | Effect |
|---|---|
| Negative returns | Bearish |
| `ema_12` below `ema_26` | Bearish trend |
| RSI below 50 | Weak momentum |
| Higher volatility | Larger penalty |

### If The V2A Profile Is Selected

If the analyst profile is `technical_ohlcv_v2`, the agent calls:

```python
TechnicalSignalService.score_ohlcv_v2(
    snapshot,
    universe_context=universe_technical_context,
    symbol=symbol,
)
```

The returned deterministic composite score and confidence become the stored
`AnalystReport.score`, `AnalystReport.confidence`, and stance. The LLM still
receives deterministic context and can write narrative `key_points` and
`risks`, but its numeric score and confidence are overwritten before the report
is stored.

The v2 report metadata is additive:

```text
AnalystScoreMetadata.technical_v2
  profile_name
  alpha_score
  risk_score
  tradability_score
  confidence
  composite_score
  coverage
  components
  top_contributors
  missing_features
  metadata
```

When the paper strategy stage has already built full-universe v2 snapshots, it
passes those snapshots plus `UniverseTechnicalContext` into the analyst runner.
Manual or symbol-local v2 calls still work without universe context; in that
case the v2 scorer falls back to raw symbol features, records
`universe_context_available=false`, and emits lower confidence.

Latest `backtest_signals` do not override v2 score or confidence. If present,
the latest signal is stored only under
`technical_v2.latest_backtest_signal_audit` with
`score_override_applied=false`.

After M80, the same `score_metadata.technical_v2` payload is visible in
operator debugging surfaces without changing report scoring: `/agent-reports`
returns `score_metadata`, the decision trail includes v2 analyst metadata in
its analyst-report stage, and React renders a compact v2 panel with profile,
composite score, confidence, alpha/risk/tradability, top contributors, and
missing-feature warnings when the payload exists.

M83 added official index/VIX storage and readiness checks, M84 added official
delivery, circuit/price-band, and tradability storage/readiness checks, and M85
wired those as opt-in v2B scoring inputs. `technical_ohlcv_v2` remains
OHLCV-only. `technical_official_v2b` reuses the v2A OHLCV feature snapshot and
adds official market-relative return, configured sector-relative return,
market/sector regime, India VIX level/change/regime, delivery participation,
circuit-band penalty, and implementability/impact-cost evidence.

M86 kept both v2 analyst profiles opt-in. The standard validation run
`techval-748ec624a9fe1297` deferred promotion because local common candle
coverage was 282 of 1009 required candles, so comparable predictive and
full-system evidence was not available. The default analyst call still uses
`technical_rule_v1`; v2A or v2B scoring is used only when the caller explicitly
passes the matching profile.

## Key Points and Risks

`TechnicalSignalService.score_analyst_rule()` builds evidence strings from the
signal and available features. The agent passes those strings to the LLM
context and to the final report.

Possible key points include:

| Evidence | Example |
|---|---|
| Latest strategy signal | `Latest strategy signal for TCS was BUY with score 0.25.` |
| 20-day return | `20-day return feature is -0.0534.` |
| RSI | `RSI-14 feature is 43.30.` |
| Volatility | `20-day volatility feature is 0.0258.` |

If no features are available, it emits a neutral fallback key point:

```text
No persisted technical features were available for SYMBOL; neutral fallback used.
```

The default risks are:

```text
Technical signals can reverse quickly when volatility rises.
Mock technical analysis is not an execution instruction.
```

Some final reports can contain different wording because the configured LLM
provider returns the final structured report text.

## LLM Boundary

`TechnicalAnalystAgent` builds deterministic context from the
`TechnicalSignalResult` first:

```python
{
    "score": str(score),
    "confidence": "0.68" if values else "0.35",
    "horizon": "medium",
    "key_points": key_points,
    "risks": risks,
    "source_ids": source_ids,
}
```

Then `BaseAnalystAgent._build_report()` calls:

```python
llm_provider.complete_analyst_report(
    agent_name="TechnicalAnalystAgent",
    symbol=symbol,
    context=context,
)
```

The LLM provider must return JSON that validates as `LLMAnalystOutput`:

| Field | Constraint |
|---|---|
| `score` | Decimal from `-1` to `1` |
| `confidence` | Decimal from `0` to `1` |
| `stance` | `bullish`, `bearish`, or `neutral` |
| `horizon` | `intraday`, `short`, `medium`, or `long` |
| `key_points` | Non-empty string list |
| `risks` | Non-empty string list |
| `model_version` | Non-empty string |

Implementation note: the current code builds a `fallback` object, but
`BaseAnalystAgent._build_report()` does not currently use that fallback if the
LLM provider fails. Provider failure raises `LLMProviderError`, and the analyst
suite stores no partial report for that run/symbol.

For `technical_ohlcv_v2` and `technical_official_v2b`, the agent calls
`_build_report()` for narrative generation and then resets stored score,
confidence, stance, model version, and score metadata to the deterministic
service result.

## Output Shape

The output is an `AnalystReport` with this shape:

| Field | Meaning |
|---|---|
| `report_id` | Stable report id derived from run, symbol, agent, time, and sources. |
| `run_id` | Paper run id. |
| `portfolio_id` | Paper profile id stored as portfolio lineage. |
| `decision_id` | Optional downstream decision id. Usually empty at analyst stage. |
| `symbol` | Uppercase symbol. |
| `agent_name` | `TechnicalAnalystAgent`. |
| `as_of` | Feature snapshot as-of timestamp or current UTC fallback. |
| `score` | Technical score from `-1` to `1`. |
| `confidence` | Confidence from `0` to `1`. |
| `stance` | `bullish`, `bearish`, or `neutral`. |
| `horizon` | Report horizon. Usually `medium`. |
| `key_points` | Evidence bullets. |
| `risks` | Risk bullets. |
| `source_ids` | Feature snapshot id and optional signal id. |
| `model_version` | LLM/model version or rule-model version. |
| `score_metadata` | Additive deterministic score evidence. For v2A and v2B reports, `score_metadata.technical_v2` contains alpha/risk/tradability/confidence/composite metadata plus profile-specific coverage and contributor details. |

## Artifacts Created

| Artifact | Storage | Created by | Notes |
|---|---|---|---|
| `FeatureSnapshot` | In memory | `TechnicalFeatureService.build_snapshot()` | Contains computed indicator values. Not automatically persisted by `TechnicalAnalystAgent`. |
| `FeatureValue` rows | In memory from feature service; persisted by backtesting paths | `TechnicalFeatureService.build_snapshot()` plus caller | Backtests persist these into `feature_values`; paper analyst fallback does not. |
| `TechnicalSignalResult` | In memory | `TechnicalSignalService.score_analyst_rule()` | DB-free deterministic v1 score, confidence, key-point, source, and metadata contract copied into the report. |
| `TechnicalOhlcvSignalResult` | In memory | `TechnicalSignalService.score_ohlcv_v2()` | DB-free deterministic v2 alpha/risk/tradability/confidence/composite contract copied into `score_metadata.technical_v2`. |
| `OfficialTechnicalContext` | In memory | `build_official_technical_context()` plus `official_context_with_snapshot_returns()` | As-of official benchmark, sector-index, India VIX, delivery, circuit, and implementability context required by `technical_official_v2b`. |
| `TechnicalOhlcvSignalResult` for v2B | In memory | `TechnicalSignalService.score_official_v2b()` | DB-free deterministic official-data v2B score copied into `score_metadata.technical_v2` with official coverage, source IDs, missing features, and contributors. |
| Technical analyst report | `analyst_reports` table | `AnalystReportRepository.replace_for_run_symbol()` | Durable per-run, per-symbol agent output. |
| Full report payload | `analyst_reports.payload` JSON | Repository conversion | Stores the full serialized `AnalystReport`, including additive `score_metadata.technical_v2` when a v2 profile is selected. |
| Per-symbol analysis artifact | `paper_runs.artifacts["analysis"][symbol]` | `PaperRunService` | Stores report ids, analyst roster, debate id, proposal id, proposal action, and finalization status. |
| Strategy summary artifact | `paper_runs.artifacts["strategy"]` | `PaperRunService._generate_strategy_summary()` | Stores feature snapshot count, ranked candidates, targets, strategy scores, and signals. |
| Agent run metrics/logs | Observability pipeline | `run_analyst_suite()` | Emits `agent.report.created` logs and agent runtime metrics. |

## Tables Written

| Table | Written by | What is written |
|---|---|---|
| `analyst_reports` | `AnalystReportRepository.replace_for_run_symbol()` | The technical report row for the run and symbol. |
| `paper_runs` | `PaperRunService` | Run-level JSON artifacts including strategy and per-symbol analysis summaries. |
| `feature_values` | Backtesting engine, not the paper analyst fallback | Persisted feature rows when the caller explicitly stores them. |

`replace_for_run_symbol()` deletes existing analyst reports for the same
`run_id` and `symbol`, then inserts the current analyst reports for that symbol.

## What It Does Not Create

`TechnicalAnalystAgent` does not create:

| Not created | Created later by |
|---|---|
| `debate_reports` | `ResearchDebateService` / research agents |
| `trader_proposals` | `TraderAgent` |
| Allocation ledger | Run allocation stage |
| `risk_reviews` | `RiskReviewService` |
| `final_decisions` | `PortfolioManagerAgent` |
| `paper_orders` | `ExecutionRouter` / `PaperBroker` |
| `paper_fills` | `PaperBroker` settlement/fill paths |

## Debugging a Run

For a run like `pr-3c26aa5b2dc650a5`, the useful inspection order is:

1. Check `paper_runs.artifacts["strategy"]` for strategy feature counts,
   ranked candidates, targets, and strategy scores.
2. Check `analyst_reports` for `agent_name = "TechnicalAnalystAgent"`.
3. Inspect each technical report's `source_ids`.
4. If a source id starts with `fs-`, it is a feature snapshot id. Check whether
   that snapshot exists in `feature_values`.
5. If a source id starts with `signal:`, inspect the matching
   `backtest_signals.id`.
6. Compare the technical report against the graph report and debate output.

Useful SQL shape:

```sql
select
  symbol,
  score,
  confidence,
  stance,
  horizon,
  source_ids,
  key_points,
  risks,
  model_version
from analyst_reports
where run_id = 'pr-3c26aa5b2dc650a5'
  and agent_name = 'TechnicalAnalystAgent'
order by symbol;
```

To check whether a feature snapshot id was persisted:

```sql
select snapshot_id, symbol, feature_name, feature_value, feature_time
from feature_values
where snapshot_id = 'fs-example'
order by feature_name;
```

## Observed Notes for `pr-3c26aa5b2dc650a5`

This run generated:

| Item | Count |
|---|---:|
| Technical analyst reports | 17 |
| Graph analyst reports | 17 |
| Technical feature snapshot source ids | 17 |
| Technical signal source ids | 0 |
| Persisted `feature_values` rows for those snapshot ids | 0 |

The run-level strategy artifact reported:

| Strategy artifact field | Value |
|---|---:|
| `strategy_name` | `graph_aware_score_v1` |
| `strategy_type` | `graph_aware_score` |
| `feature_snapshot_count` | 17 |
| `ranked_candidates` | 17 |
| `strategy_score_by_symbol` | 17 |
| `ranked_symbol_count` | 11 |
| `targets` | 8 |
| `signals` | 8 |

Interpretation: in this run, technical reports were built from candle-derived
feature snapshots, but those snapshot rows were not persisted in `feature_values`
under the referenced `fs-...` ids. The durable technical-analysis output for
the run is therefore the `analyst_reports` table plus the run-level JSON
artifacts in `paper_runs.artifacts`.

## Current Limitations

| Limitation | Impact |
|---|---|
| V2A analyst visibility is additive | M80 exposes v2A metadata in API, decision-trail, replay, and React debugging views only when present; legacy v1 runs omit those fields cleanly. |
| Shared analyst-rule scoring uses a fixed formula | Extra computed indicators are ignored unless a future `TechnicalSignalService` profile consumes them. |
| Only the core wired paths use `TechnicalSignalService` | `TechnicalAnalystAgent` and `GraphAwareScoreStrategy` are migrated; `BlendedScoreStrategy` and `MovingAverageCrossoverStrategy` remain deferred. |
| V2 profiles remain opt-in after M86 | The M86 validation gate deferred promotion because local history was insufficient for comparable evidence. |
| `feature_values` lookup is symbol-latest, not paper-run scoped | A persisted feature snapshot from another context can be selected if it is the latest for that symbol. V2 analyst calls filter persisted snapshots to `technical_ohlcv_v2` and otherwise rebuild from candles or use the caller-provided snapshot. |
| `backtest_signals` lookup is symbol-latest, not paper-run scoped | A latest backtest signal can still override default v1 scoring regardless of current paper run lineage. V2 keeps the latest signal only as audit metadata. |
| Fallback report is not used on LLM provider failure | Provider failure aborts the analyst suite for the symbol instead of storing a deterministic fallback report. |

## Shared Technical Signal Service

The M66-M69 sequence introduced a behavior-preserving
`TechnicalSignalService` so the technical analyst score and graph-aware
strategy technical score share one deterministic scoring contract without
changing trading behavior.

The implemented scopes are:

- `score_analyst_rule()` reproduces the current technical analyst formula,
  latest-signal override, bounded report score, confidence fallback, key
  points, source IDs, and score source.
- `score_sma_spread()` reproduces the graph-aware SMA-spread score used by
  `GraphAwareScoreStrategy._technical_score()`.
- `score_ohlcv_v2()` adds the opt-in OHLCV-only v2A scoring profile with
  alpha, risk, tradability, confidence, composite score, coverage,
  top-contributor, missing-feature, source, and metadata outputs. It is called
  by the opt-in `graph_aware_score_v2` strategy and, after M79, by
  `TechnicalAnalystAgent` when `technical_profile="technical_ohlcv_v2"`.

Future technical experiments should add or select profiles in
`TechnicalSignalService` instead of embedding new scoring formulas directly in
analyst or strategy classes.

## Future Extension: Indicator Suites

A clean future design would split:

1. Indicator suite: which features to compute.
2. Technical scoring profile: how `TechnicalSignalService` turns those
   features into a `-1..1` score.
3. Strategy profile: how technical and graph scores produce targets.

Example suite shape:

```yaml
suite_name: momentum_v1
feature_version: technical_momentum_v1

indicators:
  sma: [10, 20, 50, 100]
  ema: [8, 21]
  returns: [1, 5, 20, 60]
  rsi: [14]
  atr: [14]
  volatility: [20]
  volume_z_score: [20]

analyst_score:
  formula: momentum_v1
```

This would let operators select a technical lens per strategy or per run
without changing Python code for every indicator set.
