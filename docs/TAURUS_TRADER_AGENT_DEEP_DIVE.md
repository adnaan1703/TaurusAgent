# TraderAgent Deep Dive

Intent: `TraderAgent` turns research consensus plus current paper-portfolio state into a bounded paper-trading lifecycle proposal, not an order.

This document explains the current implementation of `TraderAgent`: what it
reads, what it writes, how its deterministic and LLM-assisted paths work, which
database tables and environment variables matter, how NAV/equity context is
used, and why the agent caps requested exposure at 5% NAV.

For the broader decision pipeline, see `docs/TAURUS_AGENT_ARCHITECTURE.md`. For
table definitions, see `docs/TAURUS_DATABASE_TABLES.md`.

## Role in the Decision Pipeline

`TraderAgent` is the first component that turns research into an explicit
trading intent such as `BUY`, `NO_TRADE`, `HOLD`, `REDUCE`, or `EXIT`.

It does not approve risk, allocate capital, compute final approved share
quantity, place paper orders, or route to a broker. Those responsibilities sit
after TraderAgent.

```text
analyst_reports
  -> BullResearcherAgent / BearResearcherAgent
  -> ResearchManagerAgent
  -> debate_reports
  -> TraderAgent
  -> trader_proposals
  -> Run-level allocation / active allocation
  -> RiskReviewService / RiskEngine
  -> PortfolioManagerAgent
  -> ExecutionRouter / PaperBroker
```

The important operational distinction is:

```text
TraderAgent = idea + lifecycle target
Allocation = capital/risk sizing
Risk review = hard safety approval
Portfolio manager = final decision
Execution router = paper order creation only if final decision is routable
```

## Main Implementation Files

| Area | File |
|---|---|
| Agent implementation | `packages/taurus_core/agents/trader_agent.py` |
| Research and trader schemas | `packages/taurus_core/research/schemas.py` |
| LLM prompts and trader output schema | `packages/taurus_core/llm/base.py` |
| LLM provider factory | `packages/taurus_core/llm/__init__.py` |
| LM Studio provider | `packages/taurus_core/llm/lmstudio_provider.py` |
| OpenAI provider | `packages/taurus_core/llm/openai_provider.py` |
| Gemini provider | `packages/taurus_core/llm/gemini_provider.py` |
| Paper-run orchestration | `packages/taurus_core/paper_trading/service.py` |
| Run-level allocation mutation | `packages/taurus_core/portfolio/run_allocation.py` |
| Active allocation mutation | `packages/taurus_core/portfolio/active_allocation.py` |
| DB models | `packages/taurus_core/db/models.py` |
| DB repositories | `packages/taurus_core/db/repositories.py` |
| Standalone CLI | `scripts/run_trader_proposal.py` |

## Runtime Entry Points

During a paper run, `PaperRunService.analyze_symbol()` runs:

```python
TraderAgent(
    session,
    settings,
    llm_provider=llm_provider,
).run(symbol=symbol, run_id=run_id, debate=debate)
```

The normal after-close path is `TraderAgent.run()`. It produces one
`TraderProposal` for the run and symbol.

There is also a market-hours lifecycle path:

```python
TraderAgent(...).run_market_hours_trigger(...)
```

That path is used by the position monitor when an already-open paper position
crosses a stop-loss or take-profit threshold. It can create a new lifecycle
proposal for `EXIT` or `REDUCE`, but it still requires risk review and final
approval before execution.

## Constructor Inputs

```python
TraderAgent(
    session: Session,
    settings: Settings | None = None,
    *,
    llm_provider: LLMProvider | None = None,
    max_requested_position_pct_nav: Decimal = Decimal("5.0"),
)
```

| Input | Source | Purpose |
|---|---|---|
| `session` | SQLAlchemy session | Reads analyst reports, debate reports, candles, account state, and positions; writes trader proposals. |
| `settings` | `Settings()` | Supplies the effective paper portfolio/profile id. |
| `llm_provider` | Usually `build_llm_provider(settings)` from `PaperRunService` | Optional advisory layer. If absent or invalid, deterministic fallback is used. |
| `max_requested_position_pct_nav` | Constructor parameter, default `5.0` | Caps TraderAgent's requested target exposure for `BUY` actions. |

## After-Close Run Inputs

The direct after-close method call is:

```python
TraderAgent.run(
    symbol=symbol,
    run_id=run_id,
    debate=debate,
)
```

| Input | Source | Used For |
|---|---|---|
| `symbol` | Paper run symbol loop | Normalized to uppercase and used to load symbol-specific data. |
| `run_id` | Current paper run | Ensures analyst reports, debate reports, and proposal lineage match the same run. |
| `debate` | `ResearchDebateService` output, or loaded from DB | Supplies consensus label, score, confidence, summary, and uncertainties. |
| `analyst_reports` | `analyst_reports` table | Supplies evidence, confidence, and horizon. Must exist before TraderAgent runs. |
| Paper account | Latest `paper_accounts` row for the effective portfolio | Supplies equity/NAV context. |
| Open paper position | Latest open `paper_positions` row for the portfolio and symbol | Supplies current quantity, average cost, market value, and current exposure. |
| Latest close price | Latest `daily_candles.close` for the symbol | Values the current position and evaluates stop-loss/take-profit triggers. |
| LLM provider | Configured provider | May provide an advisory proposal inside deterministic guardrails. |

If analyst reports or a debate report are missing, TraderAgent raises a
`ValueError`. It does not invent upstream evidence.

## Market-Hours Trigger Inputs

The market-hours path is only for current open-position management. It receives:

| Input | Meaning |
|---|---|
| `base_proposal` | Prior after-close proposal that established lifecycle defaults. |
| `latest_price_inr` | Current quote from the position monitor. |
| `stop_loss_price_inr` | Price threshold for stop-loss. |
| `take_profit_price_inr` | Price threshold for take-profit. |
| `trigger` | Either `stop_loss` or `take_profit`. |
| `trigger_threshold_price_inr` | The threshold crossed by the latest quote. |
| `market_session_date` | Session date for audit. |
| `quote_snapshot_id` / `quote_snapshot` | Quote evidence attached to the proposal. |

This path deterministically maps:

| Trigger | Baseline Action |
|---|---|
| `stop_loss` | `EXIT` |
| `take_profit` | `REDUCE` |

The LLM can still advise only inside the allowed action envelope. For
`stop_loss`, the only allowed action is `EXIT`. For `take_profit`, the allowed
actions are `REDUCE` or `EXIT`.

## Database Tables Read

TraderAgent directly reads these tables through repository classes:

| Table | Reader | Purpose |
|---|---|---|
| `analyst_reports` | `AnalystReportRepository.list_for_run_symbol()` | Loads all analyst reports for the symbol/run. |
| `debate_reports` | `ResearchRepository.latest_debate()` / `get_debate()` | Loads research consensus when not passed directly, or reloads the debate for market-hours proposals. |
| `paper_accounts` | `ExecutionRepository.latest_account_by_portfolio()` | Loads latest account equity/NAV for the effective portfolio. |
| `paper_positions` | `ExecutionRepository.latest_open_position_by_portfolio_symbol()` | Loads current open position for this symbol, if any. |
| `daily_candles` | `CandleRepository.get_by_symbol_and_date_range()` | Loads latest close price for after-close valuation. |

It does not directly read allocation, risk, final-decision, or order tables.
Those are downstream stages.

## Database Tables Written

TraderAgent directly writes:

| Table | Writer | Purpose |
|---|---|---|
| `trader_proposals` | `ResearchRepository.replace_trader_proposal_for_run_symbol()` | Stores the structured paper-trading lifecycle proposal. |

The `trader_proposals` table has a unique constraint on `(run_id, symbol)`.
Re-running the agent for the same run and symbol replaces the prior row.

Important: later allocation stages can update the same `trader_proposals` row.
For example, a TraderAgent `BUY` proposal can become stored as `NO_TRADE` if
allocation approves zero quantity. The original intent remains visible in
`requested_position_pct_nav` and the nested `allocation_decision`.

## Environment Variables Used

TraderAgent itself does not call `os.environ`. It receives a `Settings` object
and an optional LLM provider. The following environment variables affect its
runtime behavior through those dependencies.

| Environment Variable | Used By | Effect |
|---|---|---|
| `DATABASE_URL` | DB session factory before TraderAgent is constructed | Selects the database containing reports, debates, account state, positions, candles, and persisted proposals. |
| `TAURUS_PROFILE_ID` | `Settings` | Preferred effective profile/portfolio id. |
| `TAURUS_PAPER_PORTFOLIO_ID` | `Settings` | Legacy alias for profile/portfolio id; must match `TAURUS_PROFILE_ID` if both are set. |
| `TAURUS_LLM_PROVIDER` | `build_llm_provider()` | Chooses `lmstudio`, `openai`, or `gemini`. |
| `TAURUS_LLM_BASE_URL` | LLM provider factory | Overrides provider endpoint. |
| `TAURUS_LLM_MODEL` | LLM provider factory | Overrides provider model. |
| `TAURUS_LLM_TIMEOUT_SECONDS` | LLM provider factory | Bounds LLM completion calls. |
| `OPENAI_API_KEY` | `OpenAIProvider` | Required when `TAURUS_LLM_PROVIDER=openai`. |
| `GEMINI_API_KEY` | `GeminiProvider` | Required when `TAURUS_LLM_PROVIDER=gemini`. |
| `TAURUS_POSITION_MONITOR_ENABLED` | Position monitor, not TraderAgent directly | Enables market-hours proposal creation for stop-loss/take-profit triggers. |

Related variables that are not TraderAgent inputs but matter downstream:

| Environment Variable | Downstream Use |
|---|---|
| `TAURUS_MONEY_MANAGEMENT_ENABLED` | Enables money-management allocation after TraderAgent. |
| `TAURUS_MONEY_MANAGEMENT_CONFIG_PATH` | Selects the allocation policy YAML. |
| `TAURUS_MAX_POSITION_PCT` | Used by fallback allocation/risk paths, not by TraderAgent's 5% constructor cap. |
| `TAURUS_MAX_OPEN_POSITIONS` | Used by allocation/risk paths. |
| `TAURUS_INITIAL_CAPITAL_INR` | Used by paper account/corpus setup outside TraderAgent; indirectly affects NAV/equity rows TraderAgent later reads. |
| `TAURUS_ENABLED_ANALYSTS` | Controls upstream analyst reports; indirectly affects TraderAgent inputs. |
| `TAURUS_KILL_SWITCH_ENABLED` | Used by risk review. |
| `TAURUS_MAX_DAILY_LOSS_PCT` | Used by risk review. |
| `LIVE_TRADING_ENABLED` | Used by safety/risk/execution guardrails. |
| `BROKER_PROVIDER` | Used by safety/risk/execution guardrails. |

## Output Schema

TraderAgent writes a `TraderProposal` with these important fields:

| Field | Meaning |
|---|---|
| `proposal_id` | Stable id derived from run id, symbol, debate id, and source report ids. |
| `run_id` | Paper run lineage. |
| `portfolio_id` | Effective profile/portfolio id. |
| `symbol` | Uppercase stock symbol. |
| `debate_id` | Debate report used by the proposal. |
| `as_of` | Debate timestamp, or market-hours trigger timestamp. |
| `action` | Proposed lifecycle action: `BUY`, `NO_TRADE`, `HOLD`, `REDUCE`, or `EXIT`. |
| `confidence` | Trader confidence after bounding analyst and debate confidence. |
| `horizon` | Confidence-weighted dominant horizon from analyst reports. |
| `requested_position_pct_nav` | Exposure requested by TraderAgent before allocation. |
| `current_position_quantity` | Current open paper quantity for this symbol. |
| `current_position_pct_nav` | Current symbol exposure as a percent of NAV/equity. |
| `target_position_pct_nav` | Target exposure after the proposal; later allocation may overwrite this. |
| `lifecycle_trigger` | Reason for action: `new_entry`, `hold_review`, `stop_loss`, `take_profit`, `thesis_weakened`, or `thesis_invalidated`. |
| `evaluation_mode` | `after_close` or `market_hours`. |
| `order_type` | `LIMIT` for buy/sell-side lifecycle intents, `NONE` for no-action proposals. |
| `entry_rule` | Human-readable execution precondition. |
| `stop_loss_pct` | Default stop-loss percent, currently `6.0000`. |
| `take_profit_pct` | Default take-profit percent, currently `12.0000`. |
| `reason_summary` | Evidence-bound action rationale. |
| `invalid_if` | Conditions that invalidate or require resizing/rejection. |
| `position_management_summary` | Lifecycle and portfolio-management rationale. |
| `source_report_ids` | Analyst reports used by the debate/proposal. |
| `is_order` | Always `false` at TraderAgent stage. |
| `requires_risk_approval` | Always `true`. |
| `allocation_decision` | `None` when TraderAgent writes the row; may be added later by allocation. |
| `model_version` | Deterministic, fallback, LLM, and later allocation version lineage. |

## Internal Execution Flow

The after-close path performs this sequence:

1. Uppercase the symbol.
2. Load analyst reports for the exact run and symbol.
3. Use the supplied debate or load the latest debate for the run and symbol.
4. Validate that the debate symbol matches the requested symbol.
5. Build current portfolio context.
6. Compute a deterministic lifecycle fallback.
7. Compute allowed actions for the lifecycle state.
8. Ask the LLM provider for an advisory decision if a provider exists.
9. Validate the LLM output against deterministic guardrails.
10. Fall back to deterministic output if the LLM is missing, invalid, or outside the allowed envelope.
11. Build a `TraderProposal`.
12. Persist it to `trader_proposals`.

## Portfolio Context

TraderAgent builds a private `_PortfolioContext`:

| Field | Calculation / Source |
|---|---|
| `portfolio_id` | `settings.taurus_paper_portfolio_id`, normalized from `TAURUS_PROFILE_ID` or `TAURUS_PAPER_PORTFOLIO_ID`. |
| `account` | Latest paper account for the portfolio. |
| `position` | Latest open paper position for the portfolio and symbol. |
| `latest_close_inr` | Latest daily close, or supplied market-hours quote. |
| `current_quantity` | Open position quantity, or `0`. |
| `average_cost_inr` | Open position average cost, or `0`. |
| `market_value_inr` | `latest_close_inr * current_quantity`. |
| `current_position_pct_nav` | `(market_value_inr / account.equity_inr) * 100`, if equity and market value are positive. |
| `unrealized_pnl_inr` | `(latest_close_inr - average_cost_inr) * current_quantity`. |

## NAV / Equity Context

NAV means net asset value. In this paper system, TraderAgent uses the latest
paper account `equity_inr` as NAV.

Conceptually:

```text
NAV / equity = available cash + reserved cash + current market value of open positions
               + realized/unrealized P&L effects reflected in the account state
```

TraderAgent does not recalculate full account NAV from scratch. It trusts the
latest persisted `paper_accounts.equity_inr` produced by the paper execution
and account-state machinery.

For a stock, current exposure percent is:

```text
market_value_inr = latest_close_inr * current_quantity
current_position_pct_nav = (market_value_inr / equity_inr) * 100
```

Example:

```text
equity_inr = 100000
current_quantity = 10
latest_close_inr = 250
market_value_inr = 2500
current_position_pct_nav = 2500 / 100000 * 100 = 2.5%
```

TraderAgent uses this percent to decide whether a proposed `BUY` would increase
exposure, whether an existing position should be `HOLD`, and what target should
remain after `REDUCE` or `EXIT`.

For a new position where there is no current quantity:

```text
current_position_pct_nav = 0
```

If there is no paper account row yet, equity is treated as zero for the purpose
of current exposure calculation, so current exposure stays at `0.0000%`. Later
allocation and risk stages use their own NAV/account inputs to size and approve
actual shares.

## Deterministic Lifecycle Logic

TraderAgent first computes a deterministic baseline before any LLM advisory
output is considered.

### Lifecycle Trigger

| Condition | Trigger |
|---|---|
| No current position | `new_entry` |
| Existing position has P&L <= `-6%` from average cost | `stop_loss` |
| Existing position has P&L >= `+12%` from average cost | `take_profit` |
| Existing position and debate consensus is `bearish` | `thesis_invalidated` |
| Existing position and debate consensus is `mild_bearish` | `thesis_weakened` |
| Existing position and none of the above applies | `hold_review` |

The P&L percent check is:

```text
pnl_pct = (latest_close_inr - average_cost_inr) / average_cost_inr * 100
```

### Baseline Action

| Trigger / State | Baseline Action |
|---|---|
| `new_entry` with `bullish` or `mild_bullish` consensus and score >= `0.15` | `BUY` |
| `new_entry` with weak, neutral, or bearish consensus | `NO_TRADE` |
| `stop_loss` | `EXIT` |
| `take_profit` | `REDUCE` |
| `thesis_invalidated` | `EXIT` |
| `thesis_weakened` | `REDUCE` |
| `hold_review` with bullish/mild bullish score >= `0.15` and desired target above current exposure | `BUY` |
| Other `hold_review` cases | `HOLD` |

### Baseline Target

For `BUY`, the target is:

```text
raw_position_pct_nav = max(1.0000, abs(consensus_score) * 10)
target_position_pct_nav = min(5.0000, raw_position_pct_nav)
```

Examples:

| Consensus Score | Raw Target | Capped Target |
|---:|---:|---:|
| `0.1568` | `1.5680%` | `1.5680%` |
| `0.2041` | `2.0410%` | `2.0410%` |
| `0.7500` | `7.5000%` | `5.0000%` |

For non-BUY actions:

| Action | Target |
|---|---|
| `HOLD` | Current position percent. |
| `REDUCE` | Half of current position percent. |
| `EXIT` | `0.0000%`. |
| `NO_TRADE` | `0.0000%`. |

### Confidence

Trader confidence is:

```text
average_report_confidence = average(confidence across analyst reports)
confidence = min(average_report_confidence, debate.manager_summary.confidence)
```

This keeps TraderAgent from assigning higher conviction than either the analyst
evidence or the research manager consensus supports.

### Horizon

The proposal horizon is the analyst-report horizon with the highest confidence
weight. TraderAgent uses a counter weighted by each report's confidence.

## LLM Boundary

The LLM is advisory. It cannot expand the deterministic action envelope.

The system prompt instructs the LLM to:

- operate only as a paper-trading lifecycle proposal agent;
- avoid live trading, leverage, shorts, options, futures, and intraday speculation;
- use only supplied evidence;
- respect lifecycle trigger, evaluation mode, current position, target exposure bounds, stop-loss, take-profit, and allowed actions;
- return schema-valid JSON only.

The LLM receives a context containing:

| Context Key | Contents |
|---|---|
| `portfolio_id` | Effective profile/portfolio id. |
| `evaluation_mode` | `after_close` or `market_hours`. |
| `lifecycle_trigger` | Deterministic trigger. |
| `allowed_actions` | Deterministic allowed actions. |
| `target_position_bounds` | `0.0000` to `max_requested_position_pct_nav`. |
| `paper_portfolio_context` | Equity, latest close, current quantity, average cost, market value, current exposure, unrealized P&L. |
| `risk_defaults` | Stop-loss `6%`, take-profit `12%`. |
| `research_consensus` | Research manager summary. |
| `debate` | Full debate report. |
| `analyst_reports` | Full analyst evidence. |
| `deterministic_fallback` | Baseline action, confidence, target, stop/take-profit, reason, invalidation list, and lifecycle summary. |
| `market_hours_trigger` | Only present for market-hours stop-loss/take-profit proposals. |

The expected LLM JSON fields are:

| Field | Constraint |
|---|---|
| `action` | `BUY`, `HOLD`, `NO_TRADE`, `REDUCE`, or `EXIT`. |
| `confidence` | Number from `0` to `1`. |
| `target_position_pct_nav` | Number from `0` to `100`; later clamped by TraderAgent. |
| `stop_loss_pct` | Number from `0` to `100`. |
| `take_profit_pct` | Number from `0` to `100`. |
| `reason_summary` | Non-empty evidence-bound string. |
| `invalid_if` | Non-empty string array. |
| `position_management_summary` | Non-empty lifecycle rationale. |
| `model_version` | Provider/model identifier. |

## LLM Validation and Fallback

TraderAgent accepts LLM output only if all guardrails pass.

| Validation | Failure Result |
|---|---|
| LLM provider missing | Use deterministic fallback. |
| LLM call raises provider/schema error | Use deterministic fallback. |
| LLM action is outside allowed actions | Use deterministic fallback. |
| `BUY` target does not increase exposure | Use deterministic fallback. |
| `REDUCE` target is not between zero and current exposure | Use deterministic fallback. |
| `EXIT` target is not zero | Use deterministic fallback. |
| `HOLD` is proposed with no open position | Use deterministic fallback. |
| `NO_TRADE` is proposed while already holding a position | Use deterministic fallback. |

If accepted, the LLM's action, confidence, target, reason, invalidation list, and
position-management summary are used. The lifecycle trigger remains the
deterministic trigger.

If rejected, the proposal is marked with a deterministic fallback model version
and the fallback note is appended to `position_management_summary`.

## Allowed Action Envelope

| State | Allowed Actions |
|---|---|
| `stop_loss` trigger | `EXIT` |
| `take_profit` trigger | `REDUCE`, `EXIT` |
| No current position | `BUY`, `NO_TRADE` |
| Thesis weakened or invalidated | `REDUCE`, `EXIT` |
| Existing position with neutral consensus | `HOLD`, `REDUCE`, `EXIT` |
| Existing position with bullish/mild bullish consensus | `HOLD`, `BUY` |
| Existing position with bearish/mild bearish consensus | `HOLD`, `REDUCE`, `EXIT` |

This is why the LLM cannot turn a no-position bearish setup into `EXIT`, and it
cannot turn a stop-loss event into `HOLD`.

## Order Semantics

TraderAgent proposals are not orders.

```text
is_order = false
requires_risk_approval = true
```

Order type is only intent metadata:

| Action | `order_type` |
|---|---|
| `BUY` | `LIMIT` |
| `REDUCE` | `LIMIT` |
| `EXIT` | `LIMIT` |
| `HOLD` | `NONE` |
| `NO_TRADE` | `NONE` |

The execution router only sees a proposal after allocation, risk review, and
portfolio-manager final approval.

## Sell-Side Semantics

Taurus is currently long-only at the TraderAgent lifecycle layer. Although the
broader `TraderAction` type still includes a legacy `SELL` literal, the current
deterministic path and LLM trader schema use:

| Lifecycle Action | Meaning |
|---|---|
| `REDUCE` | Sell part of an existing long paper position. |
| `EXIT` | Sell the full existing long paper position. |

So when operators ask "why did it sell?", the rows to inspect are usually
`REDUCE` or `EXIT`, not `SELL`.

## The 5% NAV Cap

TraderAgent's constructor defaults `max_requested_position_pct_nav` to `5.0`.
This is a hard cap inside TraderAgent's target calculation and LLM target
clamping.

This cap is separate from `TAURUS_MAX_POSITION_PCT`. The environment variable is
used by fallback allocation/risk paths. TraderAgent's own default is currently a
constructor parameter in `trader_agent.py`.

### Why 5%

The 5% cap is a conservative single-name intent cap for a paper-trading MVP. It
keeps the idea-generation layer from asking for overly concentrated exposure
before allocation and risk review run.

This rationale is inferred from the implementation and the paper-first
architecture. There is no separate ADR in the repo that explains the original
choice of exactly 5%.

The intent is:

- prevent one research consensus from dominating the portfolio;
- leave room for allocation to compare multiple BUY candidates in the same run;
- make early paper results easier to debug because each requested position is small;
- ensure that even strong consensus must still pass allocation and risk gates;
- align with a diversified portfolio shape where roughly 20 fully-sized names would equal 100% gross long exposure.

### How It Works

For a BUY:

```text
raw_target = max(1%, abs(consensus_score) * 10)
requested_target = min(5%, raw_target)
```

This means:

- weak but tradable bullish consensus starts at a minimum 1% request;
- a `0.20` score requests about 2%;
- a `0.50` score requests 5%;
- anything above `0.50` is still capped at 5%.

### Pros

| Pro | Why It Helps |
|---|---|
| Limits concentration | A single symbol cannot request a very large position directly from TraderAgent. |
| Keeps TraderAgent advisory | Allocation and risk remain authoritative for final sizing. |
| Improves run comparability | BUY ideas are expressed on a similar bounded scale. |
| Reduces blast radius of weak LLM advice | Even accepted LLM output cannot request more than 5%. |
| Encourages diversification | The portfolio can hold multiple independent ideas instead of one oversized bet. |

### Cons

| Con | Tradeoff |
|---|---|
| May under-size exceptional opportunities | Very strong consensus cannot request more than 5% at TraderAgent stage. |
| Not portfolio-regime aware | The cap does not adjust for market regime, liquidity, volatility, or existing cash by itself. |
| Can be too small for high-priced stocks in small NAV accounts | Later allocation may approve zero whole shares if the risk budget is smaller than one-share risk. |
| Duplicates downstream constraints conceptually | Allocation and risk also enforce sizing limits, so the cap is an early guardrail rather than the final sizing truth. |
| Constructor-only default | Operators cannot tune this exact TraderAgent cap via a dedicated environment variable today. |

## NAV Percent Examples

### New BUY Request

```text
consensus_label = mild_bullish
consensus_score = 0.2041
current_position_pct_nav = 0

raw_target = max(1, 0.2041 * 10) = 2.0410
requested_position_pct_nav = min(5, 2.0410) = 2.0410
target_position_pct_nav = 2.0410
```

TraderAgent can request the position, but allocation may still reject it or
approve zero shares.

### Existing Position HOLD

```text
equity_inr = 100000
latest_close_inr = 500
quantity = 4
market_value_inr = 2000
current_position_pct_nav = 2000 / 100000 * 100 = 2.0000
```

If the lifecycle action is `HOLD`, target exposure stays:

```text
target_position_pct_nav = 2.0000
order_type = NONE
```

### Existing Position REDUCE

```text
current_position_pct_nav = 4.0000
```

For `REDUCE`, TraderAgent halves the target:

```text
target_position_pct_nav = 2.0000
order_type = LIMIT
```

### Existing Position EXIT

For `EXIT`:

```text
target_position_pct_nav = 0.0000
order_type = LIMIT
```

## Allocation Mutation Caveat

The stored `trader_proposals` row is not immutable. Run-level allocation or
active allocation can attach `allocation_decision` and modify these fields:

| Field | Possible Post-Trader Change |
|---|---|
| `action` | A `BUY` can become `NO_TRADE` for no current position, or `HOLD` for existing position, if allocation approves zero quantity. |
| `target_position_pct_nav` | Can be changed to approved exposure or reset to current exposure/zero. |
| `order_type` | Can become `NONE` if allocation rejects or does not select the BUY. |
| `entry_rule` | Can be replaced with an allocation rejection/not-selected reason. |
| `position_management_summary` | Allocation result and binding constraint are appended. |
| `allocation_decision` | Added with candidate score, score band, requested/approved notional, approved quantity, and binding constraint. |
| `model_version` | Allocation version suffix is appended. |

That means dashboards and diagnostics must distinguish:

```text
requested_position_pct_nav = TraderAgent's original requested exposure
target_position_pct_nav = current target after downstream mutation
allocation_decision.approved_quantity = allocation's approved share count
final_decisions.approved_quantity = portfolio manager's final approved share count
```

For example, a row can show:

```text
requested_position_pct_nav = 1.5680
action = NO_TRADE
target_position_pct_nav = 0.0000
allocation_decision.approved_quantity = 0
```

That means TraderAgent wanted exposure, but allocation later reduced it to no
trade.

## Debugging Checklist

When investigating a symbol's TraderAgent output, inspect in this order:

1. `analyst_reports` for the run and symbol.
2. `debate_reports.manager_summary` for consensus label, score, confidence, summary, and uncertainties.
3. Latest `paper_accounts.equity_inr` for the effective portfolio.
4. Latest open `paper_positions` row for the symbol.
5. Latest `daily_candles.close`.
6. `trader_proposals.requested_position_pct_nav` for original Trader intent.
7. `trader_proposals.allocation_decision` for post-Trader allocation sizing.
8. `risk_reviews` and `final_decisions` for final approval and broker-routing outcome.

The most common source of confusion is reading only the top-level
`trader_proposals.action` after allocation has already rewritten it. For
TraderAgent intent, check `requested_position_pct_nav`, `reason_summary`, and
the early part of `position_management_summary`.

## Current Limitations

| Limitation | Impact |
|---|---|
| TraderAgent's 5% cap is constructor-configured, not environment-configured. | Changing it requires code-level wiring or explicit constructor override. |
| Stop-loss and take-profit defaults are constants: `6%` and `12%`. | They are not symbol-, volatility-, or regime-adaptive at TraderAgent stage. |
| NAV/equity is trusted from latest persisted account state. | Stale or missing account rows can make current exposure appear as zero. |
| Whole-share affordability is not handled here. | Allocation may approve zero shares for high-priced stocks in small-NAV portfolios. |
| TraderAgent does not place orders. | A `BUY` proposal is not evidence that an order should exist. |
| Stored proposals can be mutated by allocation. | Diagnostics must separate original Trader intent from post-allocation state. |
