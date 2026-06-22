# Taurus Risk Review and Risk Engine Deep Dive

Intent: the risk review system validates each post-allocation trading proposal against deterministic paper-safety, lifecycle, position-limit, event-risk, and graph-concentration rules before final portfolio-manager approval.

This document explains the current implementation of `RiskReviewService`,
`RiskEngine`, and the three risk persona agents. It covers runtime role,
inputs, outputs, internal calculations, environment variables, and the important
boundary between advisory persona output and authoritative hard rules.

For the broader decision pipeline, see `docs/TAURUS_AGENT_ARCHITECTURE.md`.
For upstream trading intent, see `docs/TAURUS_TRADER_AGENT_DEEP_DIVE.md`.
For allocation and trade-risk sizing, see
`docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md`.

## Executive Summary

Risk review sits after TraderAgent and allocation, and before final
portfolio-manager approval.

```text
analyst/debate evidence
  -> TraderAgent
  -> trader_proposals
  -> run-level allocation / active allocation
  -> RiskReviewService
  -> RiskEngine + risk personas
  -> risk_reviews
  -> PortfolioManagerAgent
  -> final_decisions
  -> ExecutionRouter / PaperBroker
```

The most important operational distinctions are:

- `TraderAgent` proposes the lifecycle action: `BUY`, `NO_TRADE`, `HOLD`,
  `REDUCE`, or `EXIT`.
- Allocation can mutate a proposed `BUY` into executable `NO_TRADE` when the
  approved quantity is zero or the candidate is rejected by allocation.
- `RiskEngine` does not choose which stock to buy. It validates whether the
  post-allocation proposal is allowed under hard rules.
- Risk personas always run as advisory reviewers, but they do not override
  `RiskEngine`.
- `RiskReviewService` never routes an order. It persists a risk review with
  `is_order=false` and `can_send_to_broker=false`.
- `PortfolioManagerAgent` later converts risk-approved NAV percentage into
  final action, approved share quantity, and broker-sendable status.

## Main Files

| Area | File |
|---|---|
| Risk-review coordinator | `packages/taurus_core/risk/review_service.py` |
| Deterministic hard-rule engine | `packages/taurus_core/risk/engine.py` |
| Risk output schemas | `packages/taurus_core/risk/schemas.py` |
| Reward-seeking persona | `packages/taurus_core/agents/risky_risk.py` |
| Balanced persona | `packages/taurus_core/agents/neutral_risk.py` |
| Conservative persona | `packages/taurus_core/agents/safe_risk.py` |
| Graph concentration checks | `packages/taurus_core/risk/graph_concentration.py` |
| Position-limit policy loading | `packages/taurus_core/portfolio/money_management.py` |
| Money-management policy YAML | `configs/portfolio/money_management_v1.yaml` |
| Paper-run orchestration | `packages/taurus_core/paper_trading/service.py` |
| Final decision conversion | `packages/taurus_core/agents/portfolio_manager.py` |
| DB models | `packages/taurus_core/db/models.py` |
| DB repositories | `packages/taurus_core/db/repositories.py` |
| Standalone CLI | `scripts/run_risk_review.py` |

## Runtime Entry Points

During a paper run, `PaperRunService._run_symbol_risk_review()` calls:

```python
RiskReviewService(
    session,
    settings,
    current_open_positions=len(open_positions),
    current_position_exposures_pct_nav=_position_exposures_pct_nav(...),
).run(symbol=symbol, run_id=run_id, proposal=proposal)
```

The service receives the post-allocation `TraderProposal`. That detail matters:
if allocation approved zero shares, the stored proposal can have:

```text
requested_position_pct_nav = original requested BUY size
action = NO_TRADE
target_position_pct_nav = 0.0000
allocation_decision.action = BUY
allocation_decision.approved_quantity = 0
```

In that case risk review is approving the lifecycle state `NO_TRADE`, not the
original unallocated BUY idea.

## RiskReviewService Inputs

Constructor inputs:

| Input | Source | Purpose |
|---|---|---|
| `session` | SQLAlchemy session | Reads proposals, instruments, events, graph metadata, and writes risk reviews. |
| `settings` | `Settings()` | Supplies paper-safety flags, risk limits, money-management config, and graph-risk config. |
| `kill_switch_enabled` | Optional override or `settings.taurus_kill_switch_enabled` | Allows tests or callers to force kill-switch behavior. |
| `current_open_positions` | `PaperRunService` from latest paper positions | Used by the `max_open_positions` hard rule. |
| `current_position_exposures_pct_nav` | `PaperRunService` from latest paper positions and account equity | Used by graph concentration checks. |
| `daily_loss_pct` | Caller, default `0` | Used by `max_daily_loss_pct`. |

Run method inputs:

| Input | Source | Purpose |
|---|---|---|
| `symbol` | Current symbol in run loop | Normalized to uppercase and checked against proposal symbol. |
| `run_id` | Current paper run | Used to load a proposal when one is not passed directly. |
| `proposal` | Post-allocation `TraderProposal` | Main risk-review input. |

If `proposal` is omitted, `RiskReviewService` loads the latest matching
proposal for `symbol` and `run_id` from `trader_proposals`.

## TraderProposal Fields Used by Risk Review

The main proposal fields used by risk review are:

| Field | Used By | Meaning |
|---|---|---|
| `proposal_id` | `RiskReviewService`, `RiskEngine` | Traceability and deterministic IDs. |
| `run_id` | `RiskReviewService` | Run lineage. |
| `portfolio_id` | `RiskReviewService` | Portfolio/profile lineage. |
| `symbol` | All risk stages | Instrument and graph/event lookup key. |
| `debate_id` | `RiskReviewService` | Upstream lineage. |
| `as_of` | `RiskEngine` | Freshness check. |
| `action` | Personas, `RiskEngine` | Lifecycle action to validate. |
| `confidence` | Personas | Persona scoring. |
| `requested_position_pct_nav` | Personas, review payload | Original requested size for audit and persona reasoning. |
| `current_position_quantity` | `RiskEngine`, final decision | Determines whether an existing position exists. |
| `current_position_pct_nav` | `RiskEngine` | Current exposure baseline. |
| `target_position_pct_nav` | `RiskEngine` | Requested post-trade exposure after allocation. |
| `source_report_ids` | `RiskReviewService`, `RiskEngine` | ID generation and stale-data validation. |
| `allocation_decision` | Risk review payload, final decision | Carries allocation status, approved quantity, and skip reason. |

## RiskReviewService Internal Flow

For each symbol:

1. Normalize the symbol.
2. Load or accept the post-allocation `TraderProposal`.
3. Verify `proposal.symbol` matches the requested symbol.
4. Create deterministic IDs:
   - `decision_id = stable_id("dec", run_id, symbol, proposal_id)`
   - `risk_check_id = stable_id("risk", run_id, symbol, proposal_id, sorted_source_report_ids)`
5. Run all three persona agents:
   - `RiskyRiskAgent`
   - `NeutralRiskAgent`
   - `SafeRiskAgent`
6. Run `RiskEngine.evaluate(...)`.
7. Build a `RiskReview` object from engine output plus persona output.
8. Replace the existing risk review for `(run_id, symbol)` in `risk_reviews`.
9. Commit the DB transaction.
10. Emit risk-review alerts, if configured alert events exist.
11. Log `risk.review.created`.

The generated `risk_committee_summary` is intentionally explicit:

```text
Risk committee status <status>; hard rules are authoritative.
Persona recommendations: RiskyRiskAgent=<...>, NeutralRiskAgent=<...>, SafeRiskAgent=<...>.
```

## RiskReviewService Output

`RiskReviewService` writes one `risk_reviews` row per `(run_id, symbol)`.

Important fields:

| Field | Meaning |
|---|---|
| `risk_check_id` | Deterministic risk-review ID. |
| `decision_id` | Shared decision lineage ID used by final approval. |
| `run_id` | Paper run lineage. |
| `portfolio_id` | Portfolio/profile lineage. |
| `symbol` | Reviewed stock. |
| `proposal_id` | Source trader proposal. |
| `debate_id` | Source debate report. |
| `as_of` | Proposal timestamp. |
| `status` | `APPROVED`, `APPROVED_WITH_REDUCTION`, `REJECTED`, or `BLOCKED`. |
| `requested_position_pct_nav` | Proposal requested size, retained for audit. |
| `approved_position_pct_nav` | Risk-approved target exposure after hard rules. |
| `hard_rule_results` | Ordered list of deterministic rule results. |
| `persona_reviews` | Three advisory persona outputs. |
| `risk_committee_summary` | Short summary combining hard status and persona recommendations. |
| `source_report_ids` | Upstream source report lineage. |
| `is_order` | Always `false` at risk-review stage. |
| `can_send_to_broker` | Always `false` at risk-review stage. |
| `allocation_decision` | Nested allocation decision from the proposal, if present. |
| `model_version` | `risk_committee_rules_v1`. |

## RiskEngine Role

`RiskEngine` is the deterministic authority inside risk review.

It does not:

- score the business quality of the stock
- decide which stock should be bought
- run debate
- allocate capital by trade-risk budget
- calculate final share quantity
- place orders

It does:

- validate that the proposed lifecycle action is internally consistent
- enforce paper-only safety constraints
- enforce kill-switch behavior
- enforce instrument support
- enforce traceability
- cap target exposure
- enforce open-position count
- enforce daily-loss block
- reject stale proposals
- block severe negative event risk
- optionally reduce/reject graph-concentrated BUY exposure

## RiskEngine Inputs

Constructor inputs:

| Input | Source | Purpose |
|---|---|---|
| `session` | SQLAlchemy session | Reads instruments, events, graph data, and graph stats. |
| `settings` | `Settings()` | Supplies safety config and limits. |
| `kill_switch_enabled` | Optional override or settings | Controls kill-switch hard rule. |
| `current_open_positions` | Runtime portfolio state | Used by open-position cap. |
| `current_position_exposures_pct_nav` | Runtime portfolio state | Used by graph concentration. |
| `daily_loss_pct` | Runtime portfolio state | Used by daily-loss cap. |

Evaluation inputs:

| Input | Purpose |
|---|---|
| `proposal` | Lifecycle action and target exposure to validate. |
| `decision_id` | Required audit lineage. |
| `risk_check_id` | Required audit lineage. |

## RiskEngine Pre-Calculation

At the start of evaluation, the engine derives:

```text
symbol = proposal.symbol.upper()
action = proposal.action
current_position = quantize(proposal.current_position_pct_nav, 0.0001)
target_position = quantize(proposal.target_position_pct_nav, 0.0001)
approved_position = target_position
has_existing_position = proposal.current_position_quantity > 0
position_limits = position_limits_for_settings(settings)
```

`position_limits_for_settings(settings)` selects limits as follows:

| Condition | Limit Source |
|---|---|
| `TAURUS_MONEY_MANAGEMENT_ENABLED=true` | `configs/portfolio/money_management_v1.yaml` |
| `TAURUS_MONEY_MANAGEMENT_ENABLED=false` | `TAURUS_MAX_POSITION_PCT` and `TAURUS_MAX_OPEN_POSITIONS` |

The default YAML policy currently contains:

```text
max_stock_pct_nav = 5.0
max_open_positions = 20
```

The fallback settings defaults are:

```text
TAURUS_MAX_POSITION_PCT = 5
TAURUS_MAX_OPEN_POSITIONS = 8
```

## Hard Rule Result Statuses

Each hard rule returns a `HardRuleResult`:

```text
rule: string
status: passed | warn | reduced | rejected | blocked
details: string
```

Status meaning:

| Status | Meaning | Final Impact |
|---|---|---|
| `passed` | Rule is satisfied. | No negative impact. |
| `warn` | Rule is near a threshold but still allowed. | Does not block or reduce by itself. |
| `reduced` | Rule allows the proposal only at a lower approved position. | Final risk status becomes `APPROVED_WITH_REDUCTION` if no rejection/block exists. |
| `rejected` | Proposal is invalid under risk policy. | Final risk status becomes `REJECTED`. |
| `blocked` | System/safety-level stop. | Final risk status becomes `BLOCKED`. |

Final aggregation order:

```text
if any hard rule is blocked:
    status = BLOCKED
    approved_position_pct_nav = 0.0000
elif any hard rule is rejected:
    status = REJECTED
    approved_position_pct_nav = 0.0000
elif any hard rule is reduced:
    status = APPROVED_WITH_REDUCTION
    approved_position_pct_nav = reduced approved position
else:
    status = APPROVED
    approved_position_pct_nav = approved position
```

`blocked` takes precedence over `rejected`, and `rejected` takes precedence over
`reduced`.

## Hard Rules in Execution Order

### 1. `live_trading_disabled`

Purpose: enforce that the system remains paper/backtest only.

Calculation:

```text
live_safe =
  settings.live_trading_enabled is False
  and settings.broker_provider == "paper"
  and settings.taurus_mode in {"paper", "backtest"}
```

Result:

| Condition | Status |
|---|---|
| `live_safe=true` | `passed` |
| otherwise | `blocked` |

This rule protects against accidental live trading.

### 2. `kill_switch`

Purpose: stop all paper decisions when the Taurus kill switch is enabled.

Calculation:

```text
kill_switch_clear = not self.kill_switch_enabled
```

Result:

| Condition | Status |
|---|---|
| kill switch clear | `passed` |
| kill switch enabled | `blocked` |

### 3. `supported_instrument`

Purpose: reject symbols that are not active supported instruments.

Calculation:

```text
instrument = InstrumentRepository(session).get(symbol)
instrument_supported = instrument is not None and instrument.active
```

Result:

| Condition | Status |
|---|---|
| active instrument found | `passed` |
| missing or inactive instrument | `rejected` |

### 4. `required_trace_ids`

Purpose: require durable lineage before risk approval.

Calculation:

```text
trace_ok = bool(decision_id and proposal.proposal_id and risk_check_id)
```

Result:

| Condition | Status |
|---|---|
| all IDs present | `passed` |
| any required ID missing | `rejected` |

### 5. `lifecycle_action_valid`

Purpose: verify that the proposed action makes sense against the current
holding and target exposure.

Rules:

| Action | Required Condition |
|---|---|
| `BUY` | `target_position > current_position` and `target_position > 0` |
| `REDUCE` | Existing position exists and `0 < target_position < current_position` |
| `EXIT` | Existing position exists and `target_position == 0.0000` |
| `HOLD` | Existing position exists and `target_position == current_position` |
| `NO_TRADE` | No existing position and `target_position == 0.0000` |
| any other action | invalid |

Result:

| Condition | Status |
|---|---|
| lifecycle condition satisfied | `passed` |
| lifecycle condition violated | `rejected` |

Examples:

```text
current = 0%, target = 2%, action = BUY
-> passed

current = 2%, target = 1%, action = BUY
-> rejected, because BUY does not increase exposure

current = 2%, target = 1%, action = REDUCE
-> passed

current = 0%, target = 0%, action = EXIT
-> rejected, because there is no existing position to exit

current = 0%, target = 0%, action = NO_TRADE
-> passed
```

### 6. `max_position_pct`

Purpose: cap a BUY target to the maximum allowed stock-level NAV exposure.

Calculation:

```text
max_position = position_limits.max_stock_pct_nav

if action == "BUY" and approved_position > max_position:
    approved_position = max_position
    status = reduced
else:
    status = passed
```

Example:

```text
target_position = 8.0000%
max_position = 5.0000%
approved_position becomes 5.0000%
rule status = reduced
```

For `HOLD`, `NO_TRADE`, `REDUCE`, and `EXIT`, this cap does not block the
lifecycle action.

### 7. `buy_increases_exposure`

Purpose: reject BUY actions that do not actually increase exposure.

Calculation:

```text
if action == "BUY" and approved_position <= current_position:
    status = rejected
else:
    status = passed
```

This catches cases where the action says BUY but the target is flat or lower
than the current holding.

### 8. `max_open_positions`

Purpose: reject a new BUY when the portfolio is already at the configured open
position cap.

Calculation:

```text
open_positions_ok =
  action != "BUY"
  or has_existing_position
  or approved_position == 0
  or current_open_positions < max_open_positions
```

Result:

| Condition | Status |
|---|---|
| open positions below cap, not a new BUY, existing position, or zero approved position | `passed` |
| new BUY and open positions already at cap | `rejected` |

Important nuance: this rule does not reject lifecycle management of an existing
position. It is aimed at new long entries.

### 9. `max_daily_loss_pct`

Purpose: block new BUY exposure when the portfolio has already breached the
daily loss cap.

Calculation:

```text
daily_loss_ok = action != "BUY" or daily_loss_pct < settings.taurus_max_daily_loss_pct
```

Result:

| Condition | Status |
|---|---|
| not a BUY, or daily loss below cap | `passed` |
| BUY and daily loss at/above cap | `blocked` |

Default cap:

```text
TAURUS_MAX_DAILY_LOSS_PCT = 3.0
```

### 10. `stale_data`

Purpose: prevent approval when the proposal has no source evidence or is too
old.

Calculation:

```text
source_report_ids must be non-empty
proposal.as_of must be no older than 730 days
```

The max age is currently a code constant:

```text
STALE_DATA_MAX_AGE_DAYS = 730
```

Result:

| Condition | Status |
|---|---|
| source reports exist and age <= 730 days | `passed` |
| no source reports or too old | `rejected` |

### 11. `severe_event_block`

Purpose: block new BUY exposure when recent intelligence events contain a severe
negative event for the symbol.

Calculation:

```text
events = IntelligenceRepository(session).list_events(symbol=symbol, limit=20)
severe negative event =
  EVENT_SENTIMENT[event.event_type] < 0
  and event.severity >= 0.55

severe_event_ok = action != "BUY" or severe_event is None
```

The severe threshold is currently:

```text
SEVERE_NEGATIVE_EVENT_THRESHOLD = 0.55
```

Result:

| Condition | Status |
|---|---|
| not a BUY, or no severe negative event | `passed` |
| BUY with severe negative event | `blocked` |

If multiple severe negative events exist, the engine selects the latest/highest
severity event by sorting on event time, severity, and event id.

### 12. Graph Concentration Rules

Purpose: reduce or reject new BUY exposure when the proposed position would
over-concentrate the paper portfolio in graph-related exposure groups.

These checks run only when:

```text
action == "BUY"
and approved_position > current_position
and TAURUS_GRAPH_RISK_ENABLED=true
```

If graph risk is disabled, graph concentration returns no hard-rule results for
BUYs. If the lifecycle action is not an increasing BUY, the engine appends
`graph_risk_lifecycle_scope` with `passed`.

Graph categories:

| Rule | Category | Limit Setting |
|---|---|---|
| `graph_basic_industry_concentration` | basic industry | `TAURUS_GRAPH_MAX_BASIC_INDUSTRY_EXPOSURE_PCT` |
| `graph_product_group_concentration` | product group | `TAURUS_GRAPH_MAX_PRODUCT_GROUP_EXPOSURE_PCT` |
| `graph_customer_industry_concentration` | customer industry | `TAURUS_GRAPH_MAX_CUSTOMER_INDUSTRY_EXPOSURE_PCT` |
| `graph_dependency_concentration` | raw material/dependency | `TAURUS_GRAPH_MAX_DEPENDENCY_EXPOSURE_PCT` |
| `graph_risk_category_concentration` | risk category | `TAURUS_GRAPH_MAX_RISK_CATEGORY_EXPOSURE_PCT` |
| `graph_correlated_cluster_concentration` | correlated graph cluster | `TAURUS_GRAPH_MAX_CORRELATED_CLUSTER_EXPOSURE_PCT` |

Internal calculation:

```text
existing_exposure = sum(current_position_exposures_pct_nav for matching symbols)
projected_exposure = existing_exposure + proposed_position_pct_nav
warning_threshold = limit_pct_nav * TAURUS_GRAPH_CONCENTRATION_WARNING_FRACTION
```

Decision logic:

```text
if proposed_position_pct_nav <= 0:
    passed
elif existing_exposure >= limit:
    rejected, approved position = 0
elif projected_exposure > limit:
    reduced to remaining capacity
elif projected_exposure >= warning_threshold:
    warn, approved position unchanged
else:
    passed
```

The correlated-cluster rule uses active company graph edges and the latest edge
stats where either:

```text
abs(residual_correlation or raw_correlation) >= TAURUS_GRAPH_MIN_RESIDUAL_CORR
or abs(lead_lag_score) >= TAURUS_GRAPH_MIN_LEAD_LAG_SCORE
```

## Risk Personas

All three personas run for every risk review. The system does not choose one
persona. They are a fixed advisory committee:

```text
RiskyRiskAgent
NeutralRiskAgent
SafeRiskAgent
```

Their outputs are stored in `risk_reviews.persona_reviews`. They do not modify
`approved_position_pct_nav`, do not create orders, and do not override hard
rules.

Persona output schema:

| Field | Meaning |
|---|---|
| `agent_name` | Persona class name. |
| `recommendation` | `allow`, `reduce`, `reject`, or `block`. |
| `score` | Decimal from `-1` to `1`. |
| `confidence` | Decimal from `0` to `1`. |
| `key_points` | Human-readable reasoning points. |
| `required_conditions` | Conditions the persona expects before execution. |
| `model_version` | Persona rules version. |

### RiskyRiskAgent

Model version:

```text
risk_persona_risky_rules_v1
```

Responsibility: reward-seeking advisory reviewer.

Logic:

| Proposal | Recommendation | Score |
|---|---|---|
| `BUY` with requested position > 0 | `allow` | `min(1, proposal.confidence + requested_position_pct_nav / 100)` |
| `HOLD`, `NO_TRADE`, `REDUCE`, `EXIT` | `allow` | `0.1000` for `REDUCE`/`EXIT`, else `0` |
| otherwise | `reject` | `-0.2500` |

Persona confidence is fixed at:

```text
0.6500
```

### NeutralRiskAgent

Model version:

```text
risk_persona_neutral_rules_v1
```

Responsibility: balanced/default risk reviewer.

Logic:

| Proposal | Recommendation | Score |
|---|---|---|
| `HOLD`, `NO_TRADE`, `REDUCE`, `EXIT` | `allow` | `0.0500` |
| not `BUY`, or requested position is zero | `reject` | `-0.2000` |
| `BUY` requested position > max position cap | `reduce` | `0.1500` |
| `BUY` within max position cap | `allow` | `min(0.6500, proposal.confidence)` |

Persona confidence is fixed at:

```text
0.7200
```

### SafeRiskAgent

Model version:

```text
risk_persona_safe_rules_v1
```

Responsibility: conservative capital-protection reviewer.

Pre-calculation:

```text
max_position = position_limits_for_settings(settings).max_stock_pct_nav
half_cap = max_position / 2
```

If the normal stock cap is `5.0000%`, the safe half-cap is `2.5000%`.

Logic:

| Proposal | Recommendation | Score |
|---|---|---|
| `HOLD`, `NO_TRADE`, `REDUCE`, `EXIT` | `allow` | `0.1000` for `REDUCE`/`EXIT`, else `0` |
| not `BUY`, or requested position is zero | `reject` | `-0.3000` |
| `BUY` with confidence < `0.5500` | `reduce` | `0.0500` |
| `BUY` with requested position > half-cap | `reduce` | `0.2500` |
| `BUY` with requested position <= half-cap | `allow` | `0.2500` |

Persona confidence is fixed at:

```text
0.8000
```

## How Persona Output Affects the Decision

Persona output is persisted and summarized, but it is not currently used as an
authoritative reducer or blocker.

Example:

```text
SafeRiskAgent recommendation = reduce
RiskEngine hard rules = APPROVED
```

The final `RiskReview.status` remains `APPROVED` because `RiskEngine` is
authoritative.

A persona recommendation becomes practically important as an audit and operator
review signal. It does not change the approved NAV percentage unless the
deterministic hard rules also produce `reduced`, `rejected`, or `blocked`.

## Environment Variables

Risk review uses a `Settings` object. The code does not call `os.environ`
directly inside `RiskReviewService` or `RiskEngine`, but these environment
variables populate the settings that risk review consumes.

### Core Runtime and Safety

| Variable | Default / Common Value | Used By | Effect |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://taurus:taurus@localhost:5432/taurus` | DB session before risk service is constructed | Selects instruments, proposals, events, graph data, positions, and persisted risk reviews. |
| `TAURUS_MODE` | `paper` | `live_trading_disabled` | Must be `paper` or `backtest`. |
| `LIVE_TRADING_ENABLED` | `false` | `live_trading_disabled` and settings validation | Must remain false. |
| `BROKER_PROVIDER` | `paper` | `live_trading_disabled` and settings validation | Must remain `paper`. |
| `TAURUS_KILL_SWITCH_ENABLED` | `false` | `kill_switch` | Blocks all decisions when true. |
| `TAURUS_MAX_DAILY_LOSS_PCT` | `3.0` | `max_daily_loss_pct` | Blocks new BUY exposure when daily loss breaches the cap. |

### Position Limits and Money Management

| Variable | Default / Common Value | Used By | Effect |
|---|---|---|---|
| `TAURUS_MONEY_MANAGEMENT_ENABLED` | `false` default, often `true` in canonical full paper loop | `position_limits_for_settings()` | Selects whether risk position caps come from YAML policy or fallback settings. |
| `TAURUS_MONEY_MANAGEMENT_CONFIG_PATH` | `configs/portfolio/money_management_v1.yaml` | `position_limits_for_settings()` | YAML file used when money management is enabled. |
| `TAURUS_MAX_POSITION_PCT` | `5` | fallback `position_limits_for_settings()` | Max stock NAV percent when money management is disabled. |
| `TAURUS_MAX_OPEN_POSITIONS` | `8` | fallback `position_limits_for_settings()` | Max open positions when money management is disabled. |

Current YAML values used when money management is enabled:

```text
configs/portfolio/money_management_v1.yaml
  limits.max_stock_pct_nav = 5.0
  limits.max_open_positions = 20
```

### Graph Concentration Risk

| Variable | Default | Used By | Effect |
|---|---|---|---|
| `TAURUS_GRAPH_RISK_ENABLED` | `false` | graph concentration stage | Enables graph concentration hard rules for increasing BUYs. |
| `TAURUS_GRAPH_MAX_BASIC_INDUSTRY_EXPOSURE_PCT` | `25.0` | basic-industry concentration | Exposure limit for same basic industry. |
| `TAURUS_GRAPH_MAX_PRODUCT_GROUP_EXPOSURE_PCT` | `30.0` | product-group concentration | Exposure limit for same product group. |
| `TAURUS_GRAPH_MAX_CUSTOMER_INDUSTRY_EXPOSURE_PCT` | `30.0` | customer-industry concentration | Exposure limit for shared customer-industry dependency. |
| `TAURUS_GRAPH_MAX_DEPENDENCY_EXPOSURE_PCT` | `30.0` | dependency concentration | Exposure limit for shared raw material/dependency. |
| `TAURUS_GRAPH_MAX_RISK_CATEGORY_EXPOSURE_PCT` | `25.0` | risk-category concentration | Exposure limit for shared risk category. |
| `TAURUS_GRAPH_MAX_CORRELATED_CLUSTER_EXPOSURE_PCT` | `35.0` | correlated-cluster concentration | Exposure limit for statistically correlated company cluster. |
| `TAURUS_GRAPH_CONCENTRATION_WARNING_FRACTION` | `0.80` | all graph concentration rules | Emits warning when projected exposure reaches limit * warning fraction. |
| `TAURUS_GRAPH_MIN_RESIDUAL_CORR` | `0.35` | correlated-cluster evidence | Minimum absolute residual/raw correlation to treat an edge as correlated. |
| `TAURUS_GRAPH_MIN_LEAD_LAG_SCORE` | `0.35` | correlated-cluster evidence | Minimum absolute lead-lag score to treat an edge as correlated. |

Related graph variables such as `TAURUS_GRAPH_STATS_WINDOWS`,
`TAURUS_GRAPH_MIN_EDGE_SAMPLE_SIZE`, `TAURUS_GRAPH_MIN_STABILITY_SCORE`,
and `TAURUS_GRAPH_LEAD_LAG_MAX_DAYS`
primarily affect graph data/stat generation upstream. The risk concentration
stage consumes the persisted graph nodes, edges, and edge stats.

### Portfolio/Profile Context

| Variable | Default / Common Value | Used By | Effect |
|---|---|---|---|
| `TAURUS_PROFILE_ID` | `local-paper` | Runtime profile resolution and portfolio/account lookup paths | Identifies the operational profile. |
| `TAURUS_PAPER_PORTFOLIO_ID` | `local-paper` | `PaperRunService` and final decision paths | Selects the paper account and open positions used for risk-review context. |

`RiskReviewService` itself receives open-position count and exposure map as
constructor inputs. In the normal paper loop, `PaperRunService` builds those
inputs using the effective paper portfolio/profile.

## Database Tables Read

| Table | Reader | Purpose |
|---|---|---|
| `trader_proposals` | `RiskReviewService._load_proposal()` when proposal is omitted | Loads source proposal by symbol/run. |
| `instruments` | `RiskEngine` | Checks active supported instrument. |
| `company_events` | `RiskEngine` through `IntelligenceRepository` | Finds severe negative events. |
| `graph_nodes` | graph concentration | Resolves company, industry, product, dependency, and risk nodes. |
| `graph_edges` | graph concentration | Finds graph exposure relationships. |
| `graph_edge_stats` | graph concentration | Finds correlated company cluster evidence. |
| `paper_positions` | `PaperRunService` before constructing `RiskReviewService` | Supplies open-position count and exposure map. |
| `paper_accounts` | `PaperRunService` before constructing `RiskReviewService` | Supplies equity for exposure percentage calculations. |

## Database Tables Written

| Table | Writer | Purpose |
|---|---|---|
| `risk_reviews` | `RiskRepository.replace_risk_review_for_run_symbol()` | Stores one risk review per run and symbol. |

The risk stage does not write `paper_orders`, `paper_fills`, or
`final_decisions`.

## Downstream Final Decision Interaction

`PortfolioManagerAgent` consumes the `RiskReview`.

If risk status is:

| Risk Status | Portfolio Manager Behavior |
|---|---|
| `BLOCKED` | Final status `BLOCKED`; no broker send. |
| `REJECTED` | Final status `REJECTED`; no broker send. |
| `APPROVED` or `APPROVED_WITH_REDUCTION` | Convert approved NAV percent into action/quantity. |

Quantity conversion:

```text
target_notional = equity_inr * approved_position_pct_nav / 100
target_quantity = floor(target_notional / latest_close)

BUY quantity = max(0, target_quantity - current_quantity)
REDUCE quantity = max(0, current_quantity - target_quantity)
EXIT quantity = current_quantity
HOLD / NO_TRADE quantity = 0
```

Final decision becomes broker-sendable only when:

```text
approved_quantity > 0
and final action is routable
and paper-safe config is still true
```

This is why a risk review can be `APPROVED` but the final decision can still be
`NO_ACTION`.

## Common Debugging Patterns

### Risk Approved but No Order Was Placed

Check:

```text
risk_reviews.status
risk_reviews.approved_position_pct_nav
final_decisions.status
final_decisions.approved_quantity
trader_proposals.payload.allocation_decision
```

Common causes:

- allocation already changed the action to `NO_TRADE`
- approved NAV percent produced zero whole shares
- lifecycle action was `HOLD` or `NO_TRADE`
- final decision was not broker-sendable

### Persona Recommended Reduce but Trade Was Not Reduced

This is expected in the current implementation.

Check:

```text
risk_reviews.persona_reviews
risk_reviews.hard_rule_results
```

Only hard-rule results with `status="reduced"` change
`approved_position_pct_nav`.

### Risk Status Approved With Zero Approved Position

This usually means the reviewed lifecycle action was `NO_TRADE` with target
exposure `0.0000`. That state is valid when there is no existing position.

Check:

```text
trader_proposals.payload.action
trader_proposals.payload.target_position_pct_nav
trader_proposals.payload.requested_position_pct_nav
trader_proposals.payload.allocation_decision
```

If `allocation_decision.action=BUY` but proposal `action=NO_TRADE`, allocation
rejected or skipped the original buy intent before risk review.

### Trade Was Blocked

Check hard rules for `status="blocked"`:

```text
live_trading_disabled
kill_switch
max_daily_loss_pct
severe_event_block
```

Blocked status takes precedence over rejected/reduced results.

### Trade Was Rejected

Check hard rules for `status="rejected"`:

```text
supported_instrument
required_trace_ids
lifecycle_action_valid
buy_increases_exposure
max_open_positions
stale_data
graph_*_concentration
```

Rejected status zeroes out the approved position unless a blocked rule also
exists, in which case the final risk status is `BLOCKED`.

## Operator Query Checklist

For a single symbol/run, inspect these fields in order:

```text
trader_proposals.payload.action
trader_proposals.payload.requested_position_pct_nav
trader_proposals.payload.current_position_quantity
trader_proposals.payload.current_position_pct_nav
trader_proposals.payload.target_position_pct_nav
trader_proposals.payload.allocation_decision
risk_reviews.status
risk_reviews.approved_position_pct_nav
risk_reviews.hard_rule_results
risk_reviews.persona_reviews
final_decisions.final_action
final_decisions.status
final_decisions.approved_quantity
final_decisions.can_send_to_broker
```

The fastest mental model is:

```text
TraderProposal says what the lifecycle action should be.
Allocation decides whether the idea gets capital and shares.
RiskEngine validates the post-allocation lifecycle action under hard rules.
Risk personas explain advisory opinions.
PortfolioManagerAgent converts risk approval into a final executable decision.
ExecutionRouter routes only positive-quantity broker-sendable decisions.
```
