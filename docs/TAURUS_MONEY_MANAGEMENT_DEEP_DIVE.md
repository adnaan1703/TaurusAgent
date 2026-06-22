# Taurus Money Management Deep Dive

Intent: the money-management system converts one loop's strategy, TraderAgent proposals, and executable core portfolio-plan candidates into portfolio-aware paper allocation decisions, including sleeve routing, risk budgets, approved share quantity, planner linkage, and skip reasons.

This document explains the current paper money-management path: inputs, outputs,
environment variables, strategy mappings, internal calculations, and a worked TCS
example using both INR 10,000 and INR 1,00,000 corpus assumptions.

For the broader run pipeline, see `docs/TAURUS_AGENT_ARCHITECTURE.md`. For
TraderAgent intent generation, see `docs/TAURUS_TRADER_AGENT_DEEP_DIVE.md`.

## Executive Summary

Money management sits after TraderAgent and before risk review.

```text
Strategy summary
  -> analyst/debate/trader proposals
  -> portfolio plan
  -> planner-backed BUY allocation
  -> per-proposal active allocation
  -> risk review
  -> portfolio manager final decision
  -> execution router
```

It does not decide whether a stock is fundamentally good. It decides how much
new risk, if any, the paper portfolio may take after considering:

- the configured strategy for this loop
- the sleeve mapped to that strategy
- NAV and cash
- open positions
- stock, sector, graph-cluster, sleeve, cash, and total-risk caps
- candidate score and score band
- latest close and stop-loss distance
- whole-share rounding
- portfolio and sleeve drawdown governors

The most important operational rule is:

```text
BUY intent is not an order.
BUY intent must survive allocation, risk review, final approval, and routing.
```

Allocation is batch-aware and planner-backed. With
`TAURUS_PORTFOLIO_PLAN_ALLOCATION_ENABLED=true`, the default path sees active
trader BUY proposals, executable core Shariah BUY candidates, and
threshold-worthy REDUCE/EXIT candidates from the portfolio plan. It queues
sell-side lifecycle proposals first, scores BUY candidates by priority, and
then allocates BUYs sequentially while updating simulated cash, positions,
sleeve exposure, and open risk after each approved allocation. The legacy
run-level allocator remains available by setting
`TAURUS_PORTFOLIO_PLAN_ALLOCATION_ENABLED=false`. M61 retained that flag for
operator troubleshooting and regression comparison; normal money-managed paper
loops should leave the planner-backed default enabled.

## Main Files

| Area | File |
|---|---|
| Policy YAML | `configs/portfolio/money_management_v1.yaml` |
| Policy schema and validation | `packages/taurus_core/portfolio/money_management.py` |
| Planner-backed and legacy batch allocators | `packages/taurus_core/portfolio/run_allocation.py` |
| Single-proposal active allocator | `packages/taurus_core/portfolio/active_allocation.py` |
| Allocation output schema | `packages/taurus_core/allocation_schemas.py` |
| Strategy configs | `configs/strategies/*.yaml` |
| Strategy factory | `packages/taurus_core/strategies/factory.py` |
| Strategy implementations | `packages/taurus_core/strategies/` |
| Paper-run orchestration | `packages/taurus_core/paper_trading/service.py` |
| Core Shariah basket | `packages/taurus_core/portfolio/core_shariah_basket.py` |

## One Strategy Per Loop

The paper loop executes one configured strategy per loop.

The loop receives one strategy config path, usually through the `STRATEGY`
environment variable. The canonical Kite paper loop currently resolves to:

```text
STRATEGY=configs/strategies/graph_aware_score_v1.yaml
```

`PaperRunService._generate_strategy_summary()` loads that one config, builds one
strategy object, and emits one strategy summary with one `strategy_name`.

The money-management policy may list many strategy mappings, but that does not
mean all strategies run together. The mappings are a routing table so whichever
one strategy is active in this loop can be assigned to the correct sleeve.

Example:

```text
Current loop strategy: graph_aware_score_v1
Mapped sleeve: active_strategy
```

If the next loop is run with:

```text
STRATEGY=configs/strategies/blended_score_v1.yaml
```

then that loop's proposals would map to `diversifying_strategy`.

## Environment Variables

These variables directly affect strategy and money-management behavior.

| Variable | Default / common value | Role |
|---|---|---|
| `STRATEGY` | `configs/strategies/graph_aware_score_v1.yaml` in `make paper-loop-kite` | Selects the one strategy config used for this loop. |
| `TAURUS_MONEY_MANAGEMENT_ENABLED` | `false` default, commonly `true` in the full paper loop | Enables full policy-driven money management. |
| `TAURUS_MONEY_MANAGEMENT_CONFIG_PATH` | `configs/portfolio/money_management_v1.yaml` | Selects the money-management YAML policy. |
| `TAURUS_MAX_POSITION_PCT` | `5` | Used by fallback allocation and risk position limits when money management is disabled. |
| `TAURUS_MAX_OPEN_POSITIONS` | `8` | Used by fallback allocation and as strategy target cap when no explicit strategy target is set. |
| `TAURUS_INITIAL_CAPITAL_INR` | `10000` | Starting corpus when no paper account row exists yet. |
| `TAURUS_PAPER_ANALYSIS_SCOPE` | `strategy_selected` by default, `full_universe` in canonical Kite loop | Decides whether analysis covers only selected strategy names or the full configured universe. |
| `TAURUS_PAPER_EXECUTION_SCOPE` | `allocated_only` | Execution is restricted to allocation-selected final decisions. |
| `TAURUS_GRAPH_ENABLED` | `false` default, `true` in graph profile | Enables graph profile readiness and graph signal loading. |
| `TAURUS_GRAPH_RISK_ENABLED` | `false` default, `true` in graph profile | Enables graph concentration risk surfaces and graph profile behavior. |
| `TAURUS_PROFILE_ID` | profile-specific | Selects the operational profile. |
| `TAURUS_PAPER_PORTFOLIO_ID` | profile-specific or empty fallback | Selects the paper account/positions used for NAV and cash. |
| `DATABASE_URL` | local Postgres default | Source of account, positions, candles, graph signals, and persisted run artifacts. |

When `TAURUS_MONEY_MANAGEMENT_ENABLED=false`, the full YAML policy is not used
for active allocation. Taurus falls back to a simpler path based on:

```text
TAURUS_MAX_POSITION_PCT
TAURUS_MAX_OPEN_POSITIONS
available cash
strategy score
trader confidence
```

## Policy YAML Structure

The policy YAML combines four concerns:

1. Strategic sleeve targets.
2. Active BUY allocation and risk sizing.
3. Core Shariah basket review and rebalance.
4. Dashboard metadata and position-limit defaults.

### Top-Level Fields

| Field | Meaning | Main use |
|---|---|---|
| `policy_version` | Human-readable policy version. | Stored and shown in metadata. |
| `shariah_universe_path` | Universe file for the core Shariah basket. | Used by `CoreShariahBasketStrategy`. |
| `sleeves` | Portfolio buckets and target weights. | Active allocation, core basket, dashboard. |
| `strategy_mappings` | Maps strategy names to sleeves. | Active allocation sleeve routing. |
| `limits` | Exposure and concentration caps. | Active allocation, core basket, risk limits. |
| `trade_risk` | Per-trade and total trade-risk budgets. | Active BUY sizing. |
| `allocation_scoring` | Candidate-score weights and thresholds. | Active BUY ranking and score bands. |
| `drawdown_governors` | Portfolio-level risk brakes. | Active allocation before new BUYs. |
| `rebalance` | Core basket rebalance thresholds. | Core Shariah basket path. |

The policy validator enforces:

- at least one sleeve exists
- sleeve IDs are unique
- all sleeve target weights sum to 100%
- a `cash_buffer` sleeve exists
- every strategy mapping points to a known sleeve
- score weights sum to 1.00
- score bands satisfy `reject_below < half_normal_below < normal_below`
- hard stock cap is at least the normal stock cap

## Sleeves

Current sleeves:

| Sleeve | Target | Purpose |
|---|---:|---|
| `core_shariah` | 40% | Conservative diversified core equity basket. |
| `active_strategy` | 35% | Main active strategy sleeve, currently used by graph-aware and moving-average strategies. |
| `diversifying_strategy` | 15% | Secondary strategy sleeve after validation. |
| `experimental_models` | 5% | Small-risk sleeve for new models. |
| `cash_buffer` | 5% | Protected cash reserve. |

Important sleeve fields:

| Field | Meaning | Used by |
|---|---|---|
| `sleeve_id` | Machine identifier. | Mapping, allocation, dashboard. |
| `name` | Display name. | Dashboard and artifacts. |
| `target_weight_pct` | Sleeve target as percent of NAV. | Sleeve capacity, core target, dashboard drift. |
| `role` | Human description. | Dashboard and documentation. |
| `drawdown_reduce_threshold_pct` | Sleeve drawdown level where new position sizes are reduced. | Active allocation governors. |
| `drawdown_freeze_threshold_pct` | Sleeve drawdown level where new BUYs are frozen. | Active allocation governors. |
| `new_entry_risk_cap_pct_nav` | Optional extra per-entry risk cap for that sleeve. | Active allocation sleeve-trade-risk cap. |

The `cash_buffer` sleeve is special. Its `target_weight_pct` becomes protected
cash. Active allocation computes:

```text
protected_cash = NAV * cash_buffer_target_pct / 100
cash_room = available_cash - protected_cash
```

If cash room is small, `cash_buffer` can become the binding constraint.

## Rebalance Capacity Rules

`rebalance_capacity` makes portfolio-plan capacity explicit for BUY allocation:

```yaml
rebalance_capacity:
  hard_cash_reserve_pct_nav: 5.0
  same_run_proceeds_haircut_pct: 80.0
  buy_price_buffer_pct: 5.0
  soft_borrowing_enabled: true
  borrowable_sleeve_ids:
    - diversifying_strategy
    - experimental_models
    - core_shariah
  borrower_sleeve_ids:
    - active_strategy
  max_borrowed_capacity_pct_nav: 20.0
```

The hard cash reserve is separate from soft sleeve capacity. `cash_buffer` is
never borrowable, and the default policy keeps 5% NAV protected. Same-run sell
proceeds are forecast from planned REDUCE/EXIT rows after estimated paper costs;
only the configured 80% haircut share is spendable by same-run BUY sizing. BUY
quantity sizing uses the configured 5% price-buffer metadata in the
planner-backed allocation path.

In the portfolio plan, a non-cash sleeve has idle room only when it is
below target and has no deployable same-sleeve BUY candidate in the plan. Idle
room is protected, not borrowable, when soft borrowing is disabled, the sleeve
is not listed as borrowable, the sleeve is itself a borrower, or the sleeve is
frozen by its drawdown threshold. Otherwise the row exposes borrowable capacity.

When `active_strategy` has planned exposure above its own target, the plan can
show borrowed capacity from idle eligible non-cash sleeves up to the configured
borrow guard. `PortfolioPlanAllocationService` passes that borrowed capacity
and the spendable same-run proceeds pool into executable BUY sizing, then
records `capacity_source`, borrowed sleeve IDs, `funding_source`, existing cash
used, same-run proceeds used, available proceeds, reserve, and price-buffer
metadata on allocation decisions and ledger rows.

The M61 end-to-end regression covers this full path with seeded cash/positions,
active BUY candidates, a core BUY, a threshold EXIT, same-run proceeds
haircutting, protected cash-buffer capacity, soft non-cash borrowing, sell-first
next-open queueing, API/replay/dashboard visibility, and next-run settlement.

## Strategy Mappings

Current policy:

```yaml
strategy_mappings:
  - strategy_name: core_shariah_basket_v1
    sleeve_id: core_shariah
  - strategy_name: graph_aware_score_v1
    sleeve_id: active_strategy
  - strategy_name: moving_average_crossover_v1
    sleeve_id: active_strategy
  - strategy_name: blended_score_v1
    sleeve_id: diversifying_strategy
  - strategy_name: experimental_score_v1
    sleeve_id: experimental_models
```

These mappings answer:

```text
If this loop's strategy produced a BUY intent, which capital sleeve owns it?
```

They affect:

- sleeve capacity
- sleeve drawdown reduce/freeze rules
- sleeve-specific risk caps
- dashboard sleeve attribution
- run-level simulation of pending allocations

They do not cause all strategies to execute in the same loop.

## Strategy Deep Dive

### `graph_aware_score_v1`

Config: `configs/strategies/graph_aware_score_v1.yaml`

Implementation: `GraphAwareScoreStrategy`

This is the canonical Kite paper-loop strategy today.

Current config:

```text
fast_window = 10
slow_window = 30
technical_weight = 1.0
graph_weight = 0.35
min_combined_score = -0.10
min_return_20d = -1
min_graph_confidence = 0
require_graph_signal = false
```

Technical score:

```text
technical_score = (SMA_10 / SMA_30) - 1
```

`GraphAwareScoreStrategy` computes that value through
`TechnicalSignalService.score_sma_spread()`, preserving the existing SMA-spread
formula and `technical_score` payload key while keeping richer technical
profiles deferred.

Combined score:

```text
combined_score =
  technical_score * technical_weight
+ graph_score     * graph_weight
```

If no graph signal exists and `require_graph_signal=false`, graph score is 0
and the strategy can still rank the symbol using technical score alone.

Eligibility:

```text
combined_score > min_combined_score
return_20d >= min_return_20d
```

Output:

- ranked candidates
- selected target symbols
- per-symbol strategy scores
- BUY/HOLD/SELL strategy signals
- graph metadata where present

Allocation impact:

- maps to `active_strategy`
- raw strategy score contributes 30% of allocation candidate score
- rank is used as a tie-breaker after allocation candidate score

### `moving_average_crossover_v1`

Config: `configs/strategies/moving_average_crossover_v1.yaml`

Implementation: `MovingAverageCrossoverStrategy`

This is a simpler technical momentum strategy.

Current config:

```text
fast_window = 10
slow_window = 30
min_spread = 0
min_return_20d = -1
```

Score:

```text
score = (SMA_10 / SMA_30) - 1
```

Eligibility:

```text
score > min_spread
return_20d >= min_return_20d
```

Output:

- ranks symbols by highest fast-vs-slow SMA spread
- emits BUY for selected targets not already held
- emits SELL for held symbols no longer selected

Allocation impact:

- maps to `active_strategy`
- uses the same sleeve and risk policy as `graph_aware_score_v1`
- useful as a simpler baseline strategy

### `blended_score_v1`

Config: `configs/strategies/blended_score_v1.yaml`

Implementation: `BlendedScoreStrategy`

This is a multi-factor technical strategy.

Current weights:

```text
return_20d: 2.0
return_5d: 1.0
ema_trend: 1.5
rsi: 0.5
volatility_penalty: 1.0
volume_confirmation: 0.1
```

Derived components:

```text
ema_trend = (EMA_12 / EMA_26) - 1
rsi_component = (RSI_14 - 50) / 50
volume_component = clamp(volume_z_score_20, -3, 3) / 10
```

Score:

```text
score =
  return_20d          * 2.0
+ return_5d           * 1.0
+ ema_trend           * 1.5
+ rsi_component       * 0.5
- volatility_20       * 1.0
+ volume_component    * 0.1
```

Eligibility:

```text
score > -0.10
return_20d >= -1
35 <= RSI_14 <= 75
```

Allocation impact:

- maps to `diversifying_strategy`
- therefore uses the diversifying sleeve's 15% target and sleeve drawdown rules
- separates this secondary style from the main active sleeve

### `core_shariah_basket_v1`

Implementation: `CoreShariahBasketStrategy`

This is not a TraderAgent active signal strategy. It is the core basket review
and rebalance model.

It uses:

- `shariah_universe_path`
- `core_shariah` sleeve target
- normal stock cap
- hard stock cap
- sector cap
- graph-cluster cap
- rebalance thresholds

It emits core basket target weights and rebalance decisions.

### `experimental_score_v1`

This appears in the money-management mapping but does not currently have a
matching strategy config or factory implementation in the repo.

It is best read as a reserved policy hook. If implemented later, it would map to
`experimental_models`, which has:

- 5% sleeve target
- stricter sleeve drawdown thresholds
- `new_entry_risk_cap_pct_nav: 0.25`

## Inputs

### Static Config Inputs

| Input | Source | Purpose |
|---|---|---|
| Strategy config | `STRATEGY` path or default strategy config | Selects the one strategy used for this loop. |
| Money-management config | `TAURUS_MONEY_MANAGEMENT_CONFIG_PATH` | Defines sleeves, caps, score bands, and risk budgets. |
| Settings | `.env` / process env / defaults | Enables money management, graph profile, analysis scope, profile id, and fallback caps. |

### Runtime Data Inputs

| Input | Source | Purpose |
|---|---|---|
| Trader proposals | `TraderAgent` / `trader_proposals` | BUY/HOLD/REDUCE/EXIT intent, confidence, target %, stop %. |
| NAV | latest paper account equity or starting corpus | Converts percentage caps into INR. |
| Available cash | latest paper account cash or starting corpus | Applies cash buffer and cash room. |
| Open positions | latest paper positions | Applies position count, exposure, concentration, sleeve usage. |
| Daily candles | `daily_candles` | Latest close, liquidity score, realized volatility. |
| Strategy score/rank | strategy summary artifact | Feeds allocation candidate score and run-level ordering. |
| Sector groups | graph/classification data | Applies sector concentration cap. |
| Graph clusters | graph data | Applies graph concentration cap. |
| Core basket symbols | core basket review | Separates core positions from active sleeve exposure. |

## Outputs

### Run-Level Allocation Artifact

The run stores an `artifacts["allocation"]` payload with:

- `model_version`
- `policy_source`
- summary counts
- binding constraint counts
- per-symbol ledger entries

Ledger fields include:

- `symbol`
- `proposal_id`
- `action`
- `status`
- `selected`
- `strategy_rank`
- `strategy_score`
- `planner_source`
- `planner_rank`
- `portfolio_plan_trade_id`
- `capacity_source`
- `trader_confidence`
- `candidate_score`
- `score_band`
- `requested_position_pct_nav`
- `approved_position_pct_nav`
- `requested_notional_inr`
- `approved_notional_inr`
- `approved_quantity`
- `binding_constraint`
- `rationale`

### Proposal-Level Allocation Decision

Each proposal gets a nested `allocation_decision`.

Important fields:

| Field | Meaning |
|---|---|
| `status` | Allocation status before final risk/PM approval. |
| `candidate_score` | 0-100 allocation score. |
| `score_band` | `reject`, `half_normal`, `normal`, or `strong`. |
| `requested_position_pct_nav` | Trader's requested position size. |
| `approved_position_pct_nav` | Allocation-approved target after sizing. |
| `requested_notional_inr` | Requested increase in INR. |
| `approved_notional_inr` | Approved increase in INR after caps and whole-share rounding. |
| `approved_quantity` | Approved whole shares. |
| `allowed_risk_inr` | Risk budget after band, volatility, and governors. |
| `estimated_risk_inr` | Approved shares times risk per share. |
| `volatility_used` | Realized volatility used for dampening. |
| `governor_scale_factor` | Drawdown scaling applied to new risk. |
| `binding_constraint` | Smallest cap that determined the approved size. |
| `portfolio_plan_id` / `portfolio_plan_trade_id` | Links the allocation decision back to the stored portfolio plan and trade row. |
| `planner_source` / `planner_rank` | Shows whether the candidate came from active trader analysis or the core basket and where it ranked. |
| `capacity_source` | Shows own-sleeve capacity versus explicit soft borrowed non-cash capacity. |
| `funding_source` | Shows whether a BUY used existing cash, same-run sell proceeds, borrowed sleeve capacity, or a combination. |
| `existing_cash_used_inr` / `same_run_proceeds_used_inr` | Shows how much approved BUY notional came from existing cash versus the haircut proceeds pool. |
| `same_run_proceeds_available_inr` / `same_run_proceeds_haircut_pct` | Shows the same-run proceeds pool and haircut visible to BUY sizing. |
| `hard_cash_reserve_inr` / `buy_price_buffer_pct` | Shows the hard cash reserve and buffered BUY reference price policy used by planner-backed sizing. |
| `rationale` | Human-readable calculation notes. |

If allocation approves zero shares for a new BUY, the proposal is normalized to:

```text
action = NO_TRADE
target_position_pct_nav = 0
order_type = NONE
```

For an existing position, a zero incremental BUY becomes `HOLD`.

## Internal Working

### Step 1: Generate Strategy Summary

For each paper loop:

1. Load one strategy config.
2. Build one strategy object.
3. Build technical feature snapshots from candle history.
4. Load graph signals if graph profile is enabled.
5. Rank the universe.
6. Select targets using the strategy target cap.
7. Store ranked candidates, targets, signals, scores, and metadata.

This produces the strategy context used later by allocation:

```text
strategy_name
ranked_candidates
strategy_ranked_symbols
strategy_score_by_symbol
targets
signals
```

### Step 2: Run Analysts, Debate, and TraderAgent

The run analyzes symbols and creates one `TraderProposal` per symbol.

TraderAgent may want `BUY`, but that is still only an intent:

```text
symbol = TCS
action = BUY
requested_position_pct_nav = 1.5680
stop_loss_pct = 6.0
confidence = ...
```

### Step 3: Run-Level Allocation Loop

The run-level allocator handles all proposals together. This is important:
allocation is not isolated stock-by-stock, but it is also not a full optimizer
that searches for the best combination of all proposed trades.

The current model is:

```text
batch scoring -> priority ordering -> sequential allocation with simulated updates
```

1. Non-BUY lifecycle actions are preserved first.
2. BUY candidates are scored.
3. BUY candidates are sorted by:
   - higher candidate score
   - better strategy rank
   - higher trader confidence
   - symbol
   - proposal id
4. Candidates are allocated one by one.
5. After a candidate is selected, simulated cash, positions, and sleeve exposure
   are updated before the next candidate is evaluated.

This prevents the run from pretending each stock has access to the full
portfolio independently.

Example:

```text
TraderAgent proposals:
  A -> BUY 3.0% NAV
  B -> BUY 2.0% NAV
  C -> BUY 1.5% NAV

Run-level allocation ranking:
  1. B
  2. A
  3. C
```

The allocator sizes `B` first. If `B` consumes cash, sleeve capacity, stock
exposure, or open-risk budget, then `A` and `C` are evaluated against the
reduced simulated portfolio. If `A` is then approved, `C` sees the portfolio
after both `B` and `A`.

What the allocator does not currently do:

```text
Find the globally best combination of A/B/C.
Intentionally shrink B so that A and C both fit.
Maximize expected return for the whole proposed basket.
Solve a mean-variance or portfolio-optimization problem.
```

So the precise mental model is:

```text
Portfolio-aware: yes.
Proposal-set-aware: yes.
Global optimizer: no.
Greedy sequential allocator: yes.
```

### Step 4: Single-Proposal Active Allocation

For each BUY candidate, the active allocator performs these checks.

#### 4.1 Strategy-to-sleeve mapping

```text
strategy_name -> sleeve_id
```

If no sleeve is mapped, the proposal cannot be allocated.

#### 4.2 Lifecycle bypass

Only `BUY` actions create new risk. Other lifecycle actions receive an
allocation decision with:

```text
binding_constraint = lifecycle_action_not_new_risk
```

They continue to risk review and final approval.

#### 4.3 Drawdown governors

The allocator computes:

```text
portfolio_drawdown_pct
sleeve_drawdown_pct
```

Portfolio governors:

| Governor | Threshold | Action |
|---|---:|---|
| `portfolio_caution` | 3% | scale new position sizes to 75% |
| `portfolio_defensive` | 5% | scale new position sizes to 50% |
| `experimental_freeze` | 8% | freeze experimental new entries |
| `portfolio_freeze` | 10% | freeze all new BUYs |

Sleeve governors:

- if sleeve drawdown exceeds `drawdown_reduce_threshold_pct`, scale new sizes
- if sleeve drawdown exceeds `drawdown_freeze_threshold_pct`, freeze new BUYs
  for that sleeve

#### 4.4 Latest price and stop risk

Allocation needs a valid latest close and stop-loss distance.

```text
risk_per_share = latest_close * stop_loss_pct / 100
```

If either latest price or stop risk is zero, the BUY is rejected before sizing.

#### 4.5 Candidate score

Candidate score is a 0-100 weighted score:

```text
candidate_score =
  strategy_score_component      * 0.30
+ trader_confidence_component   * 0.25
+ liquidity_score               * 0.15
+ volatility_score              * 0.15
+ diversification_score         * 0.10
+ recent_sleeve_performance     * 0.05
```

Components:

| Component | Calculation |
|---|---|
| `strategy_score_component` | If raw score missing, 50. If raw >= 0, `60 + raw * 400`. If raw < 0, `60 + raw * 600`. Clamped 0-100. |
| `trader_confidence_component` | `TraderAgent confidence * 100`. |
| `liquidity_score` | Last 20-day average `close * volume`, mapped from 20 to 100. |
| `volatility_score` | Annualized 60-day realized volatility, where lower volatility scores better. |
| `diversification_score` | Starts at 100, penalized for same-sector and same-graph-cluster holdings. |
| `recent_sleeve_performance` | Currently defaults to 75 if not supplied. |

#### 4.6 Score band

Current policy:

| Candidate score | Band | Base risk |
|---:|---|---:|
| `< 60` | `reject` | 0 |
| `60 to <75` | `half_normal` | 0.25% NAV |
| `75 to <85` | `normal` | 0.50% NAV |
| `>=85` | `strong` | 0.75% NAV |

The `reject_below: 60.0` field is an entry floor. A score under 60 means no new
BUY risk, independent of the trader's requested target.

#### 4.7 Volatility dampening

The score band gives a base risk budget. High realized volatility can shrink it.

```text
if realized_volatility <= 0.1800:
    volatility_factor = 1.0000
else:
    volatility_factor = clamp(0.1800 / realized_volatility, 0.3500, 1.0000)
```

Allowed risk:

```text
base_allowed_risk_inr = NAV * band_risk_pct / 100
allowed_risk_inr =
  base_allowed_risk_inr
  * volatility_factor
  * governor_scale_factor
```

#### 4.8 Convert risk budget to notional

Risk budget is converted into whole shares:

```text
risk_quantity = floor(allowed_risk_inr / risk_per_share)
trade_risk_notional = risk_quantity * latest_close
```

This is where a valid BUY can become zero shares.

If:

```text
allowed_risk_inr < risk_per_share
```

then:

```text
floor(allowed_risk_inr / risk_per_share) = 0
```

#### 4.9 Compute all caps and choose the smallest

The allocator computes these rooms:

| Constraint | Meaning |
|---|---|
| `requested_notional` | Do not exceed the TraderAgent requested target increase. |
| `trade_risk` | Do not exceed the stop-loss risk budget. |
| `sleeve_trade_risk_cap` | Do not exceed sleeve-specific new-entry risk cap. |
| `stock_exposure` | Do not exceed max stock % of NAV. |
| `sleeve_capacity` | Do not exceed mapped sleeve target capacity. |
| `cash_buffer` | Preserve protected cash buffer. |
| `total_open_trade_risk` | Do not exceed total open risk cap. |
| `open_positions` | Do not exceed max open position count. |
| `sector_concentration` | Do not exceed sector exposure cap. |
| `graph_concentration` | Do not exceed graph-cluster exposure cap. |

The smallest room becomes `binding_constraint`.

Approved quantity:

```text
approved_quantity = floor(approved_notional_room / latest_close)
approved_notional_inr = approved_quantity * latest_close
estimated_risk_inr = approved_quantity * risk_per_share
```

## Fallback Allocation

If full money management is disabled, the run uses fallback allocation.

Fallback inputs:

- `TAURUS_MAX_POSITION_PCT`
- `TAURUS_MAX_OPEN_POSITIONS`
- available cash
- trader confidence
- strategy score
- latest close

Fallback candidate score:

```text
fallback_score =
  strategy_score_component * 0.60
+ trader_confidence        * 100 * 0.40
```

Fallback caps:

```text
requested_notional
stock_exposure
available_cash
open_positions
```

This path is simpler and does not use sleeves, trade-risk score bands, cash
buffer, sleeve drawdown governors, or graph/sector concentration caps.

## Worked Example: TCS

This example is based on run `pr-3c26aa5b2dc650a5`.

Observed TCS facts:

| Field | Value |
|---|---:|
| Latest close | INR 2,203.00 |
| Trader original intent | BUY |
| Requested position | 1.5680% NAV |
| Stop loss | 6.0% |
| Candidate score | 87.8672 |
| Score band | `strong` |
| Band risk | 0.75% NAV |
| Volatility factor implied by run | about 0.5464 |
| Governor scale | 1.0000 |

Risk per share:

```text
risk_per_share = 2203.00 * 6.0 / 100
               = 132.18
```

### Corpus INR 10,000

Requested notional:

```text
requested_notional = 10,000 * 1.5680 / 100
                   = 156.80
```

Base risk:

```text
base_allowed_risk = 10,000 * 0.75 / 100
                  = 75.00
```

Volatility-adjusted risk:

```text
allowed_risk = 75.00 * 0.5464 * 1.0000
             = about 40.98
```

Risk quantity:

```text
risk_quantity = floor(40.98 / 132.18)
              = 0
```

Trade-risk notional:

```text
trade_risk_notional = 0 * 2203.00
                    = 0
```

Result:

```text
approved_quantity = 0
approved_notional = 0
binding_constraint = trade_risk
final action after allocation/risk/PM = NO_TRADE / NO_ACTION
```

At INR 10,000 corpus, TCS could not buy even one share because the allowed
risk budget was smaller than one-share risk.

### Corpus INR 1,00,000 With Same Trader Request

This keeps the same TCS facts and same TraderAgent requested position of
1.5680% NAV.

Requested notional:

```text
requested_notional = 1,00,000 * 1.5680 / 100
                   = 1,568.00
```

Base risk:

```text
base_allowed_risk = 1,00,000 * 0.75 / 100
                  = 750.00
```

Volatility-adjusted risk:

```text
allowed_risk = 750.00 * 0.5464 * 1.0000
             = about 409.80
```

Risk quantity:

```text
risk_quantity = floor(409.80 / 132.18)
              = 3
```

Trade-risk notional:

```text
trade_risk_notional = 3 * 2203.00
                    = 6,609.00
```

Stock exposure room:

```text
max_stock_room = 1,00,000 * 5.0 / 100
               = 5,000.00
```

But the trader only requested INR 1,568.00 of TCS:

```text
approved_room = min(
  requested_notional 1,568.00,
  trade_risk_notional 6,609.00,
  stock_exposure_room 5,000.00,
  other rooms...
)
= 1,568.00
```

Whole-share approval:

```text
approved_quantity = floor(1,568.00 / 2,203.00)
                  = 0
```

Result:

```text
approved_quantity = 0
binding_constraint = requested_notional
```

At INR 1,00,000 corpus, the trade-risk budget would allow TCS shares, but the
TraderAgent requested position of 1.5680% NAV is still below the price of one
TCS share.

### What Corpus Would Be Needed For One TCS Share?

There are three relevant minimums.

Risk budget minimum:

```text
required_nav_for_risk =
  risk_per_share / (0.75% * volatility_factor)

= 132.18 / (0.0075 * 0.5464)
= about 32,254
```

Stock cap minimum:

```text
required_nav_for_stock_cap =
  latest_close / 5%

= 2,203.00 / 0.05
= 44,060
```

Trader requested target minimum:

```text
required_nav_for_requested_target =
  latest_close / 1.5680%

= 2,203.00 / 0.01568
= about 1,40,497
```

With the actual TCS requested target, the requested-notional minimum is the
largest. That means TCS needs roughly INR 1,40,500 NAV before the same 1.5680%
request can buy one whole share.

### INR 1,00,000 If Trader Requested The 5% Cap

TraderAgent has a constructor cap of 5% requested position. If TCS had requested
5% NAV at INR 1,00,000, then:

```text
requested_notional = 5,000.00
stock_exposure_room = 5,000.00
trade_risk_notional = 6,609.00
```

Approved quantity:

```text
approved_quantity = floor(5,000.00 / 2,203.00)
                  = 2

approved_notional = 2 * 2,203.00
                  = 4,406.00

estimated_risk = 2 * 132.18
               = 264.36
```

So with INR 1,00,000 corpus, TCS could have been buyable only if the requested
target were large enough. The actual requested target was not.

## Status Meanings

| Status | Meaning |
|---|---|
| `selected` | Fully selected at requested notional. |
| `allocation_reduced` | Approved, but smaller than requested due to a cap. |
| `not_selected` | Not selected because a portfolio resource constraint reduced quantity to zero. |
| `allocation_rejected` | Rejected by allocation logic outside normal resource competition, such as score floor or invalid data. |
| `unchanged_lifecycle` | No new risk because the proposal was not a new BUY. |
| `open_position_management` | Existing position lifecycle action preserved. |

In the final decision layer, even an allocation status is not enough to route an
order. The order router requires a final decision that is broker-sendable with
positive quantity and a routable action.

## Practical Debug Checklist

For a skipped BUY, inspect these fields in order:

1. `strategy_name`: which one strategy ran this loop?
2. `strategy_score_by_symbol[symbol]`: what raw strategy score entered allocation?
3. `allocation_decision.candidate_score`: did it pass the 60 entry floor?
4. `allocation_decision.score_band`: what risk band was assigned?
5. `allocation_decision.allowed_risk_inr`: how much INR risk was allowed?
6. Latest close from `daily_candles`: what is one share price?
7. `stop_loss_pct`: what is one-share risk?
8. `requested_position_pct_nav`: did TraderAgent request enough notional for one share?
9. `binding_constraint`: which cap actually decided the result?
10. `approved_quantity`: did whole-share rounding reduce the trade to zero?

The most common zero-share pattern in small paper accounts is:

```text
allowed_risk_inr < latest_close * stop_loss_pct / 100
```

The second common pattern for high-priced stocks is:

```text
NAV * requested_position_pct_nav / 100 < latest_close
```
