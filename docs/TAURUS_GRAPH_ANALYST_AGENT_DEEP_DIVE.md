# GraphAnalystAgent Deep Dive

This document explains the current implementation of `GraphAnalystAgent`: what
it reads, how it scores graph evidence, what it writes, which database tables
and artifacts are involved, and which environment variables control graph
analysis and graph-stat promotion.

For the broader decision pipeline, see `docs/TAURUS_AGENT_ARCHITECTURE.md`. For
table definitions, see `docs/TAURUS_DATABASE_TABLES.md`.

## Role in the Decision Pipeline

`GraphAnalystAgent` is an evidence-producing analyst. It does not place orders,
size positions, approve risk, or decide final buy/sell actions.

Its responsibility is to convert company-relationship graph evidence plus
related-stock momentum into an `AnalystReport` that downstream research and
trading agents can debate.

```text
graph_nodes / graph_edges / graph_edge_stats / related daily_candles
  -> GraphAnalystAgent
  -> graph_signals
  -> graph_signal_contributions
  -> analyst_reports
  -> BullResearcherAgent / BearResearcherAgent
  -> ResearchManagerAgent
  -> TraderAgent
  -> Allocation
  -> Risk
  -> PortfolioManagerAgent
  -> ExecutionRouter
```

The agent is deterministic:

- model version: `graph_rule_v1`
- no LLM override is used
- the LLM provider is passed through the analyst suite infrastructure, but this
  agent does not call it
- graph output cannot bypass debate, allocation, risk, final approval, or paper
  execution checks

## Main Implementation Files

| Area | File |
|---|---|
| Agent implementation | `packages/taurus_core/agents/graph_analyst.py` |
| Analyst suite runner | `packages/taurus_core/agents/runner.py` |
| Analyst report schema | `packages/taurus_core/agents/schemas.py` |
| Graph stat calculation | `packages/taurus_core/graph/stats.py` |
| Graph stats CLI entry point | `packages/taurus_core/graph/compute_edge_stats.py` |
| Graph import path | `packages/taurus_core/graph/importer.py` |
| Graph API review endpoints | `apps/api/routes_graph.py` |
| DB models | `packages/taurus_core/db/models.py` |
| DB repository | `packages/taurus_core/db/repositories.py` |
| Paper-run orchestration | `packages/taurus_core/paper_trading/service.py` |

## Runtime Entry Point

During a paper run, `PaperRunService` calls `run_analyst_suite()` for each
symbol selected for analysis. `run_analyst_suite()` validates that the symbol
exists in `instruments`, builds the configured analyst roster, runs each
analyst, and persists all resulting reports with
`AnalystReportRepository.replace_for_run_symbol()`.

The direct graph-agent method call is:

```python
GraphAnalystAgent.run(symbol=symbol, run_id=run_id)
```

The graph analyst runs only if `graph` is included in
`TAURUS_ENABLED_ANALYSTS`. The config default is `technical`, while the
canonical Kite paper loop uses `technical,graph`.

## Inputs

The direct method inputs are small:

| Input | Source | Purpose |
|---|---|---|
| `symbol` | Paper run / analyst suite | Stock being analyzed. |
| `run_id` | Paper run | Durable lineage for graph signal and analyst report IDs. |
| SQLAlchemy `session` | Agent constructor | Reads graph/candle tables and writes graph artifacts. |
| `llm_provider` | Agent constructor | Present for interface consistency; not used by this deterministic agent. |

The agent then reads graph and candle state from Postgres.

## Database Tables Read

| Table | Read By | Purpose |
|---|---|---|
| `instruments` | `run_analyst_suite()` | Confirms the symbol exists before analysts run. |
| `graph_nodes` | `GraphAnalystAgent._company_node()` and `_related_node()` | Finds the center company and related company nodes. |
| `graph_edges` | `GraphAnalystAgent._contributions()` | Loads active relationships connected to the company. |
| `graph_edge_stats` | `GraphAnalystAgent._latest_valid_stat()` | Loads statistical validation rows for each edge. |
| `daily_candles` | `GraphAnalystAgent._related_momentum()` | Computes the related symbol's 20-day momentum. |

`graph_edge_evidence` exists as supporting evidence for graph relationships, but
the current graph analyst does not read it directly. Evidence enters indirectly
through `graph_edges` metadata, confidence, mechanism, and source fields.

## Database Tables Written

| Table | Written By | Purpose |
|---|---|---|
| `graph_signals` | `GraphRepository.upsert_signal()` | Stores one aggregate graph score for the symbol/run. |
| `graph_signal_contributions` | `GraphRepository.upsert_signal_contribution()` | Stores each edge-level contribution to the aggregate graph signal. |
| `analyst_reports` | `AnalystReportRepository.replace_for_run_symbol()` | Stores the normalized analyst report consumed by research debate. |

The graph stats job also writes `graph_edge_stats`, and may update
`graph_edges.status` from `candidate` to `active` if auto-promotion is enabled
and all thresholds pass.

## Output Artifacts

### `graph_signals`

One row per graph signal. Important fields:

| Field | Meaning |
|---|---|
| `signal_id` | Stable deterministic graph signal ID. |
| `symbol` | Target symbol being analyzed. |
| `as_of` | Latest graph-stat date used, or latest candle date when neutral. |
| `score` | Aggregate graph score, clamped to `[-1, 1]`. |
| `confidence` | Aggregate graph confidence, clamped to `[0, 0.90]`. |
| `horizon` | Always `medium`. |
| `explanation` | Human-readable signal summary. |
| `source_agent` | `GraphAnalystAgent`. |
| `metadata` | Includes run ID, model version, contribution count, lookback days, deterministic flag, and `llm_override_allowed=false`. |

### `graph_signal_contributions`

One row per edge that contributed a non-zero directional score. Important
fields:

| Field | Meaning |
|---|---|
| `contribution_id` | Stable contribution ID. |
| `signal_id` | Parent graph signal. |
| `edge_id` / `edge_key` | Source graph edge. |
| `contribution_type` | Usually the edge type, for example `direct_competitor`. |
| `direction` | `bullish`, `bearish`, or `neutral`. |
| `score_contribution` | Numeric score contribution from this relationship. |
| `weight` | Edge/stat weight before applying related momentum and sign. |
| `explanation` | Human-readable contribution explanation. |
| `metadata` | Related symbol, related 20-day momentum, stat window, correlations, stability, confidence, strength, and model version. |

### `analyst_reports`

The final `AnalystReport` has this shape:

| Field | Meaning |
|---|---|
| `report_id` | Stable deterministic report ID. |
| `run_id` | Parent paper run. |
| `portfolio_id` | Profile/portfolio ID assigned by the analyst suite runner. |
| `symbol` | Target symbol. |
| `agent_name` | `GraphAnalystAgent`. |
| `as_of` | Same effective as-of time as the graph signal. |
| `score` | Aggregate graph score. |
| `confidence` | Aggregate graph confidence. |
| `stance` | `bullish`, `neutral`, or `bearish` from score thresholds. |
| `horizon` | `medium`. |
| `key_points` | Top contribution explanations and audit note. |
| `risks` | Explicit warnings that graph output cannot create orders and still needs downstream review. |
| `source_ids` | Graph signal, edge, and edge-stat identifiers. |
| `model_version` | `graph_rule_v1`. |

Stance thresholds come from `stance_from_score()`:

```text
score >=  0.10 -> bullish
score <= -0.10 -> bearish
otherwise      -> neutral
```

## Internal Working

### 1. Resolve the Company Node

The agent normalizes the symbol to uppercase and tries to find:

```text
company:{SYMBOL}
```

If that exact node key is absent, it falls back to the first `graph_nodes` row
with `node_type="company"` and the same symbol.

If no company node is found, the agent produces a neutral graph signal.

### 2. Load Eligible Edges

The current implementation loads only active edges:

```text
graph_repo.list_edges_for_node(node_key=center_node.node_key, status="active", limit=250)
```

This is important:

- `candidate` edges are ignored by `GraphAnalystAgent`
- `rejected` edges are ignored
- active edges to non-company nodes are usually ignored later because the agent
  needs a related stock symbol

The agent can use any active company-company edge type. It is not hardcoded to
`direct_competitor`. For a given pair such as TCS-INFY, only the active edge rows
are eligible.

### 3. Resolve the Related Node

For each active edge, the agent identifies the other side of the relationship.

Directed-edge rule:

```text
if edge.direction == "directed" and edge.target_node_id != center_node.id:
    skip
```

That means a directed edge only contributes when the analyzed company is the
target. Bidirectional edges can contribute from either side.

The related node must have a tradable `symbol`. Edges to sectors, products,
risks, dependencies, or sources do not directly contribute to this agent.

### 4. Pick the Latest Valid Edge Stat

For each eligible edge, the agent loads all `graph_edge_stats` rows and keeps
only valid rows:

```text
insufficient_data_reason is empty
and at least one of:
  residual_correlation
  raw_correlation
  lead_lag_score
exists
```

It then sorts valid rows by:

```text
as_of_date, sample_size, stat_window
```

descending, and picks the first row. With the default windows, this normally
picks the latest `252d` row because it has the largest sample size.

### 5. Compute Related 20-Day Momentum

The agent reads `daily_candles` for the related symbol up to the selected stat's
`as_of_date`.

The hard-coded lookback is:

```text
GRAPH_MOMENTUM_LOOKBACK_DAYS = 20
```

Formula:

```text
related_momentum_20d = latest_close / close_20_trading_days_ago - 1
```

If there are fewer than two candles or the start close is zero, the edge is
skipped.

### 6. Determine Relationship Sign

The relationship sign decides whether related momentum is bullish or bearish for
the analyzed symbol.

| `expected_sign` | Relation Sign | Meaning |
|---|---:|---|
| `positive` | `+1` | Related stock up is bullish for target. |
| `negative` | `-1` | Related stock down is bullish for target. |
| anything else, including `mixed` or `unknown` | correlation fallback | Use residual correlation if available, else raw correlation. |

If the fallback correlation is positive, relation sign is `+1`. If it is
negative, relation sign is `-1`. If no correlation exists, the edge is skipped.

### 7. Score Each Contribution

The graph contribution formula is:

```text
momentum_signal = clamp(related_momentum_20d / 0.10, -1, 1)

stats_weight =
  clamp(
    0.35
    + 0.45 * max(abs(residual_or_raw_correlation), abs(lead_lag_score))
    + 0.20 * stability_score,
    0.20,
    1.00
  )

weight =
  edge_confidence
  * edge_strength
  * status_weight
  * stats_weight

score_contribution =
  clamp(relation_sign * momentum_signal * weight, -1, 1)
```

Notes:

- `edge_confidence` comes from upstream TaurusData CSVs and is stored in
  `graph_edges.confidence`.
- `edge_strength` is converted during graph import from qualitative
  `relationship_strength`.
- `status_weight` is `1.00` for active edges and `0.65` for candidate edges,
  but the current agent filters to active edges before scoring, so candidate
  edges do not reach this formula.
- The contribution is quantized to four decimals.

Strength mapping in the importer:

| Relationship Strength | Numeric Strength |
|---|---:|
| `very_high` | 0.90 |
| `high` | 0.80 |
| `medium` | 0.50 |
| `low` | 0.25 |
| `very_low` | 0.10 |

If the qualitative strength is unknown, the importer falls back to the
confidence value.

### 8. Select Top Contributions

The agent sorts contributions by absolute contribution magnitude, then edge key,
descending:

```text
sort key = (abs(score_contribution), edge_key)
```

It keeps at most:

```text
GRAPH_MAX_CONTRIBUTIONS = 10
```

### 9. Aggregate Score and Confidence

Aggregate score:

```text
score = clamp(sum(score_contribution), -1, 1)
```

Aggregate confidence:

```text
if no contributions:
    confidence = 0.2500
else:
    average_weight = sum(contribution.weight) / contribution_count
    count_bonus = min(0.15, contribution_count * 0.025)
    confidence = clamp(0.35 + average_weight + count_bonus, 0, 0.90)
```

### 10. Persist Artifacts

The agent writes:

1. a `graph_signals` row
2. one `graph_signal_contributions` row per contribution
3. an `AnalystReport`, later persisted to `analyst_reports` by the suite runner

If there are no valid contributions, the agent still writes a neutral
`graph_signals` row and an `AnalystReport` with `graph:none` in `source_ids`.

## Edge Data Governance

### Active vs Candidate

The active/candidate status belongs to the specific edge row, not to the edge
type globally.

```text
edge_type = what kind of relationship is this?
edge_key  = specific relationship instance
status    = whether this specific instance is trusted/eligible
```

Current import rules:

| Source File | Imported Status | Meaning |
|---|---|---|
| `company_edges.csv` | `active` | Curated/higher-value graph edges. |
| `edge_candidates.csv` | `candidate` | Lower-threshold discovery edges requiring review. |

Candidate edges can later become active by:

- manual/API promotion: `POST /graph/edges/{edge_key}/promote`
- auto-promotion during `make compute-graph-stats`, if explicitly enabled and
  all thresholds pass

Candidate edge review requires graph mutations to be enabled through the API
runtime configuration. The review route changes only graph edge status; it does
not route orders or bypass risk/final approval.

### Edge Confidence

`graph_edges.confidence` is imported from upstream TaurusData CSVs. It is not
computed by `GraphAnalystAgent`.

For `company_edges.csv`, TaurusAgent reads the CSV `confidence` column and
stores it in `graph_edges.confidence`.

For `edge_candidates.csv`, TaurusAgent also reads the CSV `confidence` column,
but imports the row with `status="candidate"`.

TaurusData defines this field as confidence in the relationship mapping or
candidate usefulness. It is not measured statistical confidence and is not a
correlation.

For current candidate generation, TaurusData uses fixed heuristic confidence
values for several candidate types:

| Candidate Type | Confidence |
|---|---:|
| `same_macro` | 0.28 |
| `same_sector` | 0.32 |
| `same_industry` | 0.36 |
| `same_basic_industry` | 0.40 |
| `common_raw_material_exposure` | 0.38 |
| `common_customer_industry` | 0.38 |

This imported confidence is now audit metadata only. It does not block manual
candidate review or opt-in statistical auto-promotion.

## Graph Edge Stats

Graph edge stats are calculated separately from the analyst, through:

```bash
make compute-graph-stats
```

The implementation reads `graph_edges`, `graph_nodes`, and `daily_candles`, then
writes `graph_edge_stats`.

By default, the stats job computes rows for both active and candidate edges.
That is different from `GraphAnalystAgent`, which consumes only active edges.
Candidate edges need stats so they can be reviewed or auto-promoted later.

### Windows

Default windows:

```text
60d, 120d, 252d
```

Each edge gets one stat row per configured window and as-of date.

Current local DB snapshot from the discussion:

| Window | Total Rows | Validated | Insufficient |
|---|---:|---:|---:|
| `60d` | 145,024 | 125,704 | 19,320 |
| `120d` | 145,024 | 125,704 | 19,320 |
| `252d` | 145,024 | 125,704 | 19,320 |

### Return Series

The stats job computes close-to-close daily returns from `daily_candles`:

```text
daily_return[t] = close[t] / close[t-1] - 1
```

It then aligns source and target returns on common dates and takes the most
recent `window` observations.

If fewer than `TAURUS_GRAPH_MIN_EDGE_SAMPLE_SIZE` overlapping observations are
available, the row is written with an insufficient-data reason such as:

```text
insufficient_overlap:required=30,found=3
```

### Raw Correlation

`raw_correlation` is the Pearson correlation of source and target close-to-close
returns over the selected window.

High positive raw correlation means both stocks tended to move together over the
window. High negative raw correlation means they tended to move opposite each
other.

### Residual Correlation

`residual_correlation` removes broad market-proxy movement from both stocks and
then correlates the residuals.

The market proxy is not a hard-coded NIFTY index. It is the average daily return
across all available symbols in the local candle set.

Process:

```text
market_return[t] = average return across available symbols on date t
source_beta = beta(source_returns, market_returns)
target_beta = beta(target_returns, market_returns)
source_residual[t] = source_return[t] - source_beta * market_return[t]
target_residual[t] = target_return[t] - target_beta * market_return[t]
residual_correlation = pearson(source_residuals, target_residuals)
```

Residual correlation is useful because it asks whether the pair still moves
together after broad market movement is stripped out.

### Lead-Lag Score

`lead_lag_score` checks whether the source stock tends to lead the target stock
by 1 to `TAURUS_GRAPH_LEAD_LAG_MAX_DAYS` days.

Default max lag:

```text
5 days
```

For each lag, it correlates:

```text
source_return[t] with target_return[t + lag]
```

It keeps the lag with the largest absolute correlation. Direction matters,
therefore `TCS -> INFY` and `INFY -> TCS` can have different lead-lag scores
even though raw correlation is symmetric.

### Stability Score

`stability_score` tests whether the relationship is directionally stable across
the first and second halves of the window.

The job computes Pearson correlation on the first half and second half:

- if either half cannot be computed, stability is null
- if the sign flips between halves, stability is `0.0`
- otherwise, stability is close to `1.0` when the two half-window correlations
  are similar

Formula:

```text
stability = clamp(1 - min(abs(first_half_corr - second_half_corr) / 2, 1), 0, 1)
```

### Valid Edge Stat For The Analyst

`GraphAnalystAgent` considers an edge stat valid if:

```text
insufficient_data_reason is empty
and one of residual_correlation, raw_correlation, or lead_lag_score exists
```

The stat job may write rows that are not valid for analysis. Those rows remain
useful for audit because they explain why an edge could not be statistically
validated.

## Auto-Promotion

Auto-promotion is disabled by default.

If enabled, it runs inside `compute_graph_edge_stats()` after each valid stat is
computed. It can promote a specific edge row from:

```text
candidate -> active
```

The promotion records:

```text
reviewed_by = graph_stats_job
review_note = Auto-promoted from graph stats {window} as of {date}.
```

All of these requirements must pass:

| Requirement | Default |
|---|---:|
| `TAURUS_GRAPH_AUTO_PROMOTE_EDGES=true` | default `false` |
| edge status is `candidate` | required |
| stat sample size >= `TAURUS_GRAPH_MIN_EDGE_SAMPLE_SIZE` | 30 |
| stability score exists | required |
| stability score >= `TAURUS_GRAPH_MIN_STABILITY_SCORE` | 0.50 |
| abs residual correlation >= `TAURUS_GRAPH_MIN_RESIDUAL_CORR` OR abs lead-lag >= `TAURUS_GRAPH_MIN_LEAD_LAG_SCORE` | 0.35 / 0.35 |

Current local DB observation from the discussion:

```text
candidate_edges = 92,549
promotion_candidates_require_statistical_validation = true
```

Auto-promotion remains disabled by default. Enabling it can allow broad
candidate relationships into active graph analysis only if they pass the
statistical filters.

## Environment Variables And Defaults

| Variable | Default | Used By | Effect |
|---|---:|---|---|
| `TAURUS_ENABLED_ANALYSTS` | `technical` | Analyst suite | Must include `graph` for `GraphAnalystAgent` to run. |
| `TAURUS_GRAPH_ENABLED` | `false` | Graph profile/API/preflight paths | Enables graph-aware runtime surfaces. The analyst itself is controlled by `TAURUS_ENABLED_ANALYSTS`. |
| `TAURUS_GRAPH_RISK_ENABLED` | `false` | Risk layer | Enables downstream graph concentration risk checks. Not used by `GraphAnalystAgent` scoring. |
| `TAURUS_GRAPH_AUTO_PROMOTE_EDGES` | `false` | Graph stats job | Allows candidate edges to become active if thresholds pass. |
| `TAURUS_GRAPH_STATS_WINDOWS` | `60,120,252` | Graph stats job | Controls stat windows written to `graph_edge_stats`. |
| `TAURUS_GRAPH_MIN_EDGE_SAMPLE_SIZE` | `30` | Graph stats and auto-promotion | Minimum overlapping return observations. |
| `TAURUS_GRAPH_MIN_RESIDUAL_CORR` | `0.35` | Auto-promotion | Minimum absolute residual correlation threshold. |
| `TAURUS_GRAPH_MIN_LEAD_LAG_SCORE` | `0.35` | Auto-promotion | Minimum absolute lead-lag score threshold. |
| `TAURUS_GRAPH_MIN_STABILITY_SCORE` | `0.50` | Auto-promotion | Minimum stability score threshold. |
| `TAURUS_GRAPH_LEAD_LAG_MAX_DAYS` | `5` | Graph stats job | Maximum lag tested for lead-lag score. |

`make paper-loop-kite` overrides some defaults operationally:

```text
TAURUS_ENABLED_ANALYSTS=technical,graph
TAURUS_GRAPH_ENABLED=true
TAURUS_GRAPH_RISK_ENABLED=true
TAURUS_PAPER_ANALYSIS_SCOPE=full_universe
TAURUS_PAPER_EXECUTION_SCOPE=allocated_only
STRATEGY=configs/strategies/graph_aware_score_v1.yaml
```

Hard-coded graph analyst constants:

| Constant | Value | Meaning |
|---|---:|---|
| `GRAPH_ANALYST_MODEL_VERSION` | `graph_rule_v1` | Version in reports/signals. |
| `GRAPH_MOMENTUM_LOOKBACK_DAYS` | `20` | Related-symbol momentum lookback. |
| `GRAPH_MAX_CONTRIBUTIONS` | `10` | Maximum edge contributions used in aggregate score. |
| `REPORT_QUANT` | `0.0001` | Decimal quantization for report values. |

## Current Examples From Discussion

### TCS-INFY Edge Rows

Current direct TCS-INFY graph rows:

| Edge Type | Status | Sign | Direction | Used By GraphAnalystAgent |
|---|---|---|---|---|
| `direct_competitor` | `active` | `negative` | `TCS -> INFY`, bidirectional | yes |
| `common_customer_industry` | `candidate` | `mixed` | `INFY -> TCS` | no |
| `common_raw_material_exposure` | `candidate` | `mixed` | `INFY -> TCS` | no |
| `same_basic_industry` | `candidate` | `mixed` | `INFY -> TCS` | no |
| `same_industry` | `candidate` | `mixed` | `INFY -> TCS` | no |
| `same_macro` | `candidate` | `mixed` | `INFY -> TCS` | no |
| `same_sector` | `candidate` | `mixed` | `INFY -> TCS` | no |

The active edge:

```text
edge_key: ge-company_edge-55797fd8231fa226
type: direct_competitor
expected_sign: negative
confidence: 0.7400
strength: 0.8000
mechanism: Both compete for global enterprise IT services and large outsourcing contracts.
```

Latest valid stat used by the agent:

| Window | As Of | Sample | Raw Corr | Residual Corr | Lead-Lag | Stability |
|---|---|---:|---:|---:|---:|---:|
| `252d` | `2026-06-18` | 252 | 0.7648 | 0.7476 | -0.0599 | 0.9471 |

In run `pr-3c26aa5b2dc650a5`, TCS received graph score `0.2255`,
confidence `0.9000`, stance `bullish`.

Why:

```text
INFY 20-day momentum was negative.
HCLTECH 20-day momentum was negative.
Both were active direct_competitor edges with expected_sign=negative.
Competitor weakness became bullish graph evidence for TCS.
```

### CIPLA Example

In run `pr-3c26aa5b2dc650a5`, CIPLA received graph score `0.2862`,
confidence `0.8178`, stance `bullish`.

Contributors:

| Related Symbol | Edge Type | Expected Sign | Related 20-Day Momentum | Contribution |
|---|---|---|---:|---:|
| `DRREDDY` | `direct_competitor` | `negative` | -3.9262% | 0.1735 |
| `SUNPHARMA` | `direct_competitor` | `negative` | -2.8612% | 0.1127 |

Again, competitor weakness was interpreted as bullish because the edge sign was
`negative`.

## Practical Debugging Checklist

When a graph signal looks surprising, inspect these in order:

1. Confirm `graph` is enabled in `TAURUS_ENABLED_ANALYSTS`.
2. Confirm the target company has a `graph_nodes` row such as `company:TCS`.
3. List active edges for the company; candidate edges are ignored.
4. Confirm the related node has a tradable symbol.
5. Confirm each edge has a valid `graph_edge_stats` row.
6. Check which window the agent picked; usually latest `252d`.
7. Check related-symbol 20-day momentum.
8. Check `expected_sign`; `negative` reverses the related momentum interpretation.
9. Check imported `edge.confidence` and numeric `edge.strength`.
10. Check `stats_weight`, contribution metadata, and final `graph_signals` score.

Useful tables to inspect:

```sql
select * from graph_nodes where symbol = 'TCS';
select * from graph_edges where source_node_id = ... or target_node_id = ...;
select * from graph_edge_stats where edge_id = ... order by as_of_date desc, sample_size desc;
select * from graph_signals where symbol = 'TCS' order by as_of desc;
select * from graph_signal_contributions where signal_id = ...;
select * from analyst_reports where run_id = '...' and symbol = 'TCS' and agent_name = 'GraphAnalystAgent';
```

## Main Points From The Discussion

- The graph analyst is deterministic and does not use the LLM provider.
- It produces evidence, not trade decisions.
- It uses only active graph edges; candidate edges are ignored.
- Active/candidate is a property of each edge row, not the edge type globally.
- `company_edges.csv` imports as active; `edge_candidates.csv` imports as candidate.
- The same company pair can have multiple edge rows with different edge types.
- For TCS-INFY, only the active `direct_competitor` edge is currently used.
- `expected_sign=negative` means related-stock weakness is bullish for the target.
- Edge confidence comes from upstream TaurusData CSVs; it is not computed by
  `GraphAnalystAgent`.
- Edge confidence is relationship-mapping confidence, not statistical
  correlation.
- Statistical validation lives in `graph_edge_stats`.
- Auto-promotion is disabled by default and, with current default thresholds,
  would promote zero current candidates because their imported confidence values
  are below `0.65`.
