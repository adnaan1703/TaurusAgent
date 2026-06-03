# Full-Universe Dynamic Allocation Plan

Last reviewed: 2026-06-03

Execution order: starts after the completed paper money-management sequence and
terminal progress UI work. Run each milestone in this document in a fresh
context. After a milestone is implemented, verified, cleaned up, and documented
with its completion summary, stop and report the result. Do not automatically
start the next milestone unless the user explicitly asks.

## Summary

Refactor the Kite-backed paper loop so Taurus analyzes the full configured
Shariah universe instead of only a small strategy target set, then dynamically
allocates capital after all symbols have been reviewed.

Target steady-state flow:

```text
full universe
-> strategy ranking for every eligible symbol
-> analyst/debate/trader proposal for every symbol
-> run-level dynamic allocation across all proposals
-> risk review and final decision for every symbol
-> PaperBroker execution only for allocated, risk-approved decisions
```

This plan deliberately avoids hard-coded strategy position counts. Strategy
configs should score and rank opportunities. Portfolio breadth and sizing should
come from money-management policy when enabled, or from settings-derived
fallback constraints when disabled.

## Recent Baseline

Recent commits add important surfaces that this plan must preserve:

- `PaperRunService` now emits Rich/plain progress events for setup and
  per-symbol stages.
- Money management M31-M35 is complete: policy loading, core basket artifacts,
  active-sleeve allocation, sleeve governors, and React allocation panels exist.
- Current active allocation is still applied one proposal at a time inside the
  per-symbol pipeline.
- Current graph-aware market-universe runs still narrow symbols before analysis
  to graph-selected targets plus open positions.

The main architectural change is therefore not adding allocation from scratch.
It is converting existing per-symbol allocation and execution into a run-level
batch decision after full-universe analysis.

## Hard Invariants

- Taurus remains paper-trading-first.
- `LIVE_TRADING_ENABLED=false` remains the default.
- `BROKER_PROVIDER=paper` remains the default.
- No live broker order routing is in scope.
- Runtime market data remains Kite-only.
- The deployable universe remains enabled symbols from
  `configs/market_data/nifty_500_shariah.yaml` unless a later milestone changes
  the universe policy.
- Risk-reducing `REDUCE` and `EXIT` lifecycle actions for existing paper
  positions must not be blocked by new allocation rules.
- React dashboard updates must accompany any public API payload changes.
- New behavior must keep the progress UI meaningful for long full-universe
  runs.

## Target Concepts

Use these terms consistently across all milestones:

- **Analysis universe**: all symbols requested by the run. For canonical
  `make paper-loop-kite`, this is the enabled market-data universe.
- **Strategy ranking**: deterministic score/rank output for all eligible
  analysis-universe symbols.
- **Trader proposal universe**: all symbols that completed analysts, debate,
  and trader proposal generation.
- **Allocation ledger**: run-level record explaining which proposals were
  selected, not selected, unchanged, rejected by allocation, or reserved for
  lifecycle management.
- **Execution set**: final decisions that are allocated, risk-approved,
  paper-safe, and routable to `PaperBroker`.

## M36: Strategy Ranking Foundation

### Goal

Stop using strategy YAMLs as fixed position-count controls. Strategies should
rank the full eligible universe and provide enough metadata for later
allocation, backtesting, and UI audit.

### Implementation Changes

- Add a strategy ranking model, for example:
  - symbol
  - trade date
  - action intent
  - raw strategy score
  - normalized score if useful for cross-strategy allocation
  - rank
  - eligibility status
  - reasons
  - invalidation rules
  - feature snapshot id
  - strategy-specific metadata
- Add a strategy interface such as `rank_universe(...)`.
  - Inputs should mirror current `select_targets(...)` and
    `select_targets_with_graph(...)` inputs.
  - Graph-aware strategies should accept `graph_signals_by_symbol`.
  - Output should include every eligible scored symbol and rejected/ineligible
    symbols where the strategy can explain the rejection.
- Keep `select_targets(...)` and `select_targets_with_graph(...)` as legacy
  adapters during migration.
  - They may call `rank_universe(...)` and apply an explicit caller-provided cap.
  - They must not silently default to top 3.
- Update `StrategyConfig`.
  - `target_positions` becomes optional and deprecated.
  - Missing `target_positions` must not default to `3`.
  - Strategy YAMLs should keep scoring/filter parameters only.
- Update all current strategies:
  - moving average crossover
  - blended score
  - graph-aware score
  - mock/backtest-only momentum if still used in tests
- Update strategy artifacts to include ranking metadata:
  - `ranked_candidates`
  - `eligible_symbol_count`
  - `ranked_symbol_count`
  - `strategy_score_by_symbol`
  - legacy `targets` only where still needed for old callers

### Test Plan

- Unit-test every strategy ranks all eligible symbols instead of truncating to a
  fixed count.
- Unit-test missing `target_positions` does not become `3`.
- Unit-test legacy target selection only truncates when the caller explicitly
  provides a cap.
- Update existing graph-aware strategy tests to assert ranked candidates include
  non-selected symbols.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add a section to this document listing assumptions made, mocks
created, and mocks used.

### M36 Completion Summary

- Assumptions made:
  - Existing paper-run symbol selection still needs legacy `targets` until the
    later pipeline/allocation milestones remove that dependency.
  - When a strategy YAML omits deprecated `target_positions`, old target-based
    callers may use an explicit caller-owned fallback cap such as
    `taurus_max_open_positions`; the strategy itself must not provide a hidden
    top-3 default.
  - Backtest `target_positions` remains an execution/backtest breadth control
    until M42 aligns backtest summaries more deeply with ranking/allocation
    separation.
- Mocks created: None
- Mocks used:
  - Existing `MockMomentumStrategy` remains test/backtest-only and now exposes
    ranking plus explicit-cap legacy target selection.

## M37: Paper Pipeline Decomposition

### Goal

Split the paper loop into explicit analysis, allocation, risk/finalization, and
execution phases without changing default behavior yet. This creates a safe
foundation for full-universe runs.

### Implementation Changes

- Refactor `PaperRunService._run_symbol()` into smaller methods:
  - analyst suite
  - research debate
  - trader proposal
  - allocation
  - risk review
  - portfolio manager final decision
  - execution routing
- Add a symbol-analysis method that stops after trader proposal generation.
- Add a symbol-finalization method that starts from a stored or in-memory
  proposal and performs allocation, risk, portfolio manager, and execution.
- Keep current behavior for existing commands:
  - graph-aware market-universe mode may still narrow before the symbol loop in
    M37
  - allocation may still be per-symbol in M37
  - execution may still occur inside the symbol loop in M37
- Preserve current run artifacts and add only backward-compatible metadata.
- Update progress events to reflect the decomposed methods while preserving
  existing terminal progress behavior.

### Test Plan

- Existing paper-run tests should pass with no behavior changes.
- Add tests that the decomposed analysis and finalization methods produce the
  same artifacts as the old combined path.
- Add progress callback tests for the new stage names.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### Completion Summary

Completed on 2026-06-03.

- Assumptions made: M37 should preserve the current selected-symbol loop, per-symbol allocation, and in-loop paper execution behavior; run artifact keys should remain unchanged; progress callbacks may expose decomposed stage names while terminal progress keeps the existing stage labels.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, `FakeKiteMarketDataProvider`, and mock/default paper-trading test settings in pytest coverage.

## M38: Full-Universe Analysis Mode

### Goal

Enable Taurus to run analysts, debate, and trader proposal generation for the
entire configured universe while keeping allocation/execution behavior safe.

### Implementation Changes

- Add settings:
  - `TAURUS_PAPER_ANALYSIS_SCOPE`
    - values: `strategy_selected`, `full_universe`
    - default during M38: `strategy_selected`
  - `TAURUS_PAPER_EXECUTION_SCOPE`
    - values: `selected_only`, `allocated_only`
    - default during M38: current behavior equivalent
- In `full_universe` analysis scope:
  - use all requested market-data-universe symbols for analysis
  - include current open positions even if absent from requested symbols
  - do not let graph-aware `graph_selected_symbols` replace the analysis list
- Keep explicit manual `SYMBOL` or `SYMBOLS` runs limited to the explicit list
  plus open positions.
- Build run artifacts that distinguish:
  - requested universe symbols
  - analyzed symbols
  - strategy-ranked symbols
  - graph-selected symbols
  - open-position symbols
- Update progress context so the terminal progress count reflects the full
  analyzed symbol count.
- In M38, finalization may still operate only on the old selected subset unless
  M39/M40 are also complete. The key deliverable is full-universe analysis and
  durable proposal artifacts.

### Test Plan

- Unit-test `full_universe` mode preserves all enabled universe symbols through
  analyst/debate/trader proposal generation.
- Unit-test graph-aware strategy selection no longer narrows the analysis list
  in `full_universe` mode.
- Unit-test manual symbols remain explicit.
- Add an integration-style paper-run test with a small test universe to avoid
  long runtime.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### M38 Completion Summary

Completed on 2026-06-03.

- Assumptions made:
  - `TAURUS_PAPER_ANALYSIS_SCOPE=strategy_selected` must preserve pre-M38
    selected-symbol behavior, while `full_universe` is opt-in until M43.
  - In M38, `TAURUS_PAPER_EXECUTION_SCOPE=allocated_only` can be validated and
    recorded but the effective execution scope remains `selected_only` until
    M39/M40 add run-level allocation and full-symbol finalization.
  - Full-universe market-data runs should finalize only strategy-selected
    symbols plus open positions for M38 safety; manual `SYMBOL`/`SYMBOLS` runs
    remain limited to explicit symbols plus open positions.
  - New M38 symbol-scope and analysis records are run artifact additions, not a
    typed public API payload change requiring React dashboard updates.
- Mocks created: None.
- Mocks used:
  - Existing `FakeLLMProvider` and `FakeKiteMarketDataProvider` in focused
    pytest coverage for paper-run full-universe behavior.

## M39: Run-Level Dynamic Allocation Engine

### Goal

Replace one-symbol-at-a-time active allocation with a run-level batch allocator
that compares all trader proposals before selecting and sizing paper trades.

### Implementation Changes

- Add a run-level allocation service.
  - Inputs:
    - strategy ranking
    - all trader proposals
    - current account and open positions
    - daily candle history
    - core basket symbols
    - sector and graph cluster groups
    - money-management policy or fallback settings policy
  - Output:
    - allocation ledger for every proposal
    - updated proposals for selected, unchanged, and not-selected symbols
    - run-level summary counts and binding constraints
- Reuse existing `PortfolioAllocationService` scoring and sizing logic, but
  make it batch-safe.
  - Simulate pending approved allocations before paper orders execute.
  - Reduce available cash, sleeve capacity, open-position room, sector room,
    graph-cluster room, and total trade-risk room after each selected proposal.
  - Rank BUY/increase candidates by allocation candidate score, strategy rank,
    trader confidence, and deterministic tie-breakers.
- Move active-allocation score weights and score-band thresholds out of code and
  into `configs/portfolio/money_management_v1.yaml`.
  - Keep conservative defaults equivalent to the current code.
  - Validate the config deterministically.
- Add a fallback policy for disabled money management.
  - Use `TAURUS_MAX_OPEN_POSITIONS`, `TAURUS_MAX_POSITION_PCT`, available cash,
    current positions, proposal confidence, and strategy score.
  - This fallback must still be dynamic and must not hard-code a fixed selected
    count.
- Ledger statuses should include at least:
  - `selected`
  - `not_selected`
  - `unchanged_lifecycle`
  - `allocation_rejected`
  - `allocation_reduced`
  - `open_position_management`
- Existing open-position `HOLD`, `REDUCE`, and `EXIT` proposals should remain
  eligible for lifecycle handling even if they are not top-ranked new entries.

### Test Plan

- Unit-test money-management-enabled batch allocation consumes pending cash and
  capacity as candidates are selected.
- Unit-test fallback allocation derives selected count from settings and
  available constraints.
- Unit-test no fixed candidate count is needed to stop selection.
- Unit-test open positions remain in the ledger.
- Unit-test score-band and score-weight config validation.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### M39 Completion Summary

Completed on 2026-06-03.

- Assumptions made:
  - M39 should persist run-level allocation decisions and the allocation ledger
    before finalization, while M40 still owns finalizing every analyzed symbol
    and moving paper execution to a deferred run-level execution phase.
  - Existing selected-only finalization remains the effective execution
    boundary for M39; symbols outside that set keep analysis and allocation
    ledger records but do not yet receive risk/final decision records.
  - Normal whole-share rounding should not classify an otherwise fully selected
    proposal as `allocation_reduced`; reductions are tied to binding
    constraints other than requested notional.
- Mocks created: None
- Mocks used:
  - Existing `FakeLLMProvider` and `FakeKiteMarketDataProvider` in paper-run
    pytest coverage.

## M40: Full-Universe Risk, Final Decisions, And Deferred Execution

### Goal

Complete the requested full pipeline: every analyzed symbol gets risk review and
final decision records, while execution happens only after run-level allocation
has selected approved trades.

### Implementation Changes

- Move execution routing out of the per-symbol finalization loop.
- Finalize every trader proposal after the allocation ledger exists.
  - Selected BUY/increase proposals use the approved allocation target.
  - Not-selected BUY proposals become `NO_TRADE` with reason
    `not_selected_by_run_allocation`.
  - Allocation-rejected BUY proposals become `NO_TRADE` with the allocation
    binding constraint in the reason.
  - Existing-position `HOLD`, `REDUCE`, and `EXIT` proposals preserve lifecycle
    intent.
- Run `RiskReviewService` and `PortfolioManagerAgent` for every symbol in the
  analyzed universe.
- Route paper orders only after all final decisions have been stored.
  - Only decisions in the allocation execution set can route.
  - `ExecutionRouter` paper-safe checks remain authoritative.
- Update run artifacts:
  - final decision counts
  - allocation ledger counts
  - execution set
  - symbols skipped from execution and reasons
- Keep per-symbol error handling.
  - A failure for one symbol should not erase completed analysis or final
    decisions for other symbols.
  - Run status remains `PARTIAL_FAILED` when appropriate.

### Test Plan

- Unit-test every analyzed symbol receives a final decision.
- Unit-test not-selected symbols become `NO_ACTION` final decisions with a clear
  allocation reason.
- Unit-test execution happens only after all final decisions are created.
- Unit-test only allocated approved decisions route to `PaperBroker`.
- Regression-test `HOLD`, `NO_TRADE`, `REDUCE`, and `EXIT` behavior.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### M40 Completion Summary

Completed on 2026-06-03.

- Assumptions made:
  - M40 run-artifact additions for final-decision counts, allocation ledger
    counts, execution set, and skipped execution reasons do not require React
    dashboard changes in this milestone; M41 owns dedicated API/React
    observability surfaces.
  - `effective_execution_scope=allocated_only` now reflects actual M40 routing
    behavior, while the configured `TAURUS_PAPER_EXECUTION_SCOPE` value remains
    recorded for operator context.
  - Open-position `REDUCE` and `EXIT` lifecycle decisions belong in the
    allocation execution set because they manage existing paper exposure rather
    than adding new BUY risk; open-position `HOLD` and no-position `NO_TRADE`
    decisions remain stored final decisions that are skipped from execution.
- Mocks created: None.
- Mocks used:
  - Existing `FakeLLMProvider` and `FakeKiteMarketDataProvider` in paper-run
    pytest coverage.
  - Test-only monkeypatches for forced trader lifecycle actions and route/order
    call recording in focused M40 regression coverage.

## M41: API And React Full-Universe Observability

### Goal

Make full-universe analysis and dynamic allocation understandable in the
primary React dashboard.

### Implementation Changes

- Extend API run payloads with:
  - `universe_count`
  - `analyzed_count`
  - `ranked_count`
  - `proposal_count`
  - `selected_count`
  - `not_selected_count`
  - `allocation_rejected_count`
  - `risk_rejected_count`
  - `executed_count`
- Add or extend a run-level selection payload.
  - Include rank, strategy score, trader action, proposal confidence,
    allocation status, final status, execution status, and reason.
  - Keep payload bounded for overview pages; full details belong on run detail
    and decision trail endpoints.
- Update React surfaces:
  - Overview: full-universe run counts and selected/executed summary.
  - Run detail: searchable/scannable selection ledger.
  - Decision trail: explicit reason for selected, not selected, allocation
    rejected, risk rejected, no action, or executed.
  - Allocation panels: continue showing sleeve utilization and latest
    allocation decisions, now backed by run-level ledger data where available.
- Preserve existing allocation dashboard behavior for pre-M41 runs.

### Test Plan

- API aggregate tests for enabled and disabled money-management modes.
- API tests for legacy runs without a selection ledger.
- React tests for run-count summaries, ledger empty states, and decision-trail
  allocation reasons.
- Run `make test-ui`, `make build-ui`, `make test`, and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### M41 Completion Summary

- Status: Done.
- Completed: Added bounded run-level selection previews to overview run
  summaries, full selection ledgers to run detail payloads, explicit
  selection/no-action/allocation/execution reasons to decision trails, and
  React surfaces for full-universe counts, ledger scanning, decision reasons,
  and latest allocation decisions backed by run-level ledger data when
  available.
- Verification: `make test-ui`, `make build-ui`, `make test`, and `make lint`
  passed.
- Assumptions made: M40's persisted `allocation.ledger`, `allocation.summary`,
  `symbol_scope`, `final_decisions`, and `execution` run artifacts are the
  source of truth for M41 observability when present; overview selection
  previews should remain bounded to eight rows; legacy runs without allocation
  ledgers should keep empty selection-ledger payloads while retaining existing
  allocation dashboard fallbacks.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider` and `FakeKiteMarketDataProvider` test
  fixtures.

## M42: Backtest, Replay, And Command Alignment

### Goal

Align supporting tools with the new separation between strategy ranking and
portfolio allocation.

### Implementation Changes

- Update backtesting so portfolio breadth comes from backtest configuration or
  money-management policy, not strategy YAML `target_positions`.
- Store and display ranked candidates in backtest summaries where useful.
- Update replay tooling to understand:
  - strategy ranking
  - allocation ledger
  - not-selected final decisions
  - deferred execution
- Review position monitor behavior.
  - Market-hours monitoring should continue to operate only on open positions.
  - It should not attempt full-universe analysis during market hours.
- Update command docs with new settings and expected output.
- Ensure command approvals remain project-local if new commands are added.

### Test Plan

- Backtest tests prove no strategy YAML position count is required.
- Replay tests cover selected and not-selected decisions.
- Position monitor tests confirm market-hours behavior is unchanged.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

## M43: Default Enablement And Operator Hardening

### Goal

Make full-universe analysis the canonical Kite paper-loop behavior once the
preceding milestones are stable.

### Implementation Changes

- Change canonical `make paper-loop-kite` behavior to:
  - `TAURUS_PAPER_ANALYSIS_SCOPE=full_universe`
  - `TAURUS_PAPER_EXECUTION_SCOPE=allocated_only`
- Keep explicit manual runs bounded to `SYMBOL` or `SYMBOLS` plus open
  positions.
- Add operator guidance for runtime expectations.
  - Full-universe runs are longer and may use more LLM/API resources.
  - Progress output should show where time is spent.
  - Add guidance for narrowing manual runs during debugging.
- Add optional controlled concurrency only if M36-M42 show runtime needs it.
  - Default workers should remain `1`.
  - Concurrency must not corrupt shared run artifacts or allocation state.
- Update:
  - `README.md`
  - `docs/TAURUS_USAGE_GUIDE.md`
  - `docs/TAURUS_COMMANDS.md`
  - `docs/TAURUS_MILESTONE_TODO.md`
- Run a full local verification pass with a small test universe and document
  the expected checks for the real full universe.

### Test Plan

- Canonical command/profile tests assert full-universe analysis is enabled for
  `make paper-loop-kite`.
- Manual command tests assert explicit symbols remain bounded.
- End-to-end paper-run test with a small universe verifies ranking, proposal,
  allocation, final decisions, and execution counts.
- Run `make test`, `make lint`, `make test-ui`, and `make build-ui`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

## Deferred Follow-Ups

- Durable allocation ledger table if JSON artifacts become too large or hard to
  query.
- Parallel analyst/debate execution after single-threaded correctness is
  established.
- Hosted LLM cost controls for full-universe runs.
- Additional portfolio optimization beyond deterministic sleeve/risk-budgeted
  selection.
- New universe policies beyond Nifty 500 Shariah.
