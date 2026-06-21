# Taurus Portfolio Rebalance Plan

Last updated: 2026-06-22

This document is the implementation plan for upgrading Taurus from per-symbol
proposal sizing plus run-level BUY allocation into a holistic, paper-only
portfolio rebalance loop. Each milestone below is a standalone milestone
intended to be executed in a separate Codex thread. Stop after completing and
documenting the current milestone; do not automatically continue to the next
milestone.

## Target Behavior

Taurus should evaluate the whole profile portfolio on every manual EOD paper
run and produce one coherent rebalance plan before risk review, final approval,
and next-open paper execution:

```text
After latest daily candles are imported:
  1. Settle prior pending next-open paper orders.
  2. Build analyst, debate, trader, strategy-ranking, and core-basket evidence.
  3. Build one portfolio rebalance plan from:
       - current account cash and equity
       - current holdings and sleeve labels
       - existing pending orders, if any remain pending
       - all current trader proposals
       - executable core Shariah basket targets
       - risk, concentration, sleeve, and cash-buffer policy
       - score/rank evidence with raw and calibrated values
  4. Stack-rank candidates across the whole run.
  5. Allocate capital from available cash plus conservative same-run proceeds.
  6. Keep at least 5% NAV as hard cash reserve and size BUY orders using a 5%
     reference-price uplift before costs.
  7. Generate BUY, REDUCE, and EXIT proposal decisions that can be audited,
     risk-reviewed, finalized, and queued for next-open paper execution.
```

The upgraded system should answer the operator's concerns directly:

- Clamping remains only where it is a contract guardrail, not where precision is
  needed for ranking and allocation. Raw signal values, calibrated values, and
  bounded report scores must be visible as distinct concepts.
- `active_strategy` is no longer limited to 35% NAV when other non-cash sleeves
  are idle. Active can borrow configured idle capacity, while the 5% cash buffer
  remains hard and never borrowable.
- The core Shariah basket is executable, not only an artifact. Core targets can
  produce BUY, REDUCE, and EXIT proposals through the same risk/final/execution
  path as active strategy decisions.
- Allocation is portfolio-level. The run should consider all current holdings,
  all candidate buys, planned reductions/exits, sleeve targets, concentration
  caps, cash, and risk governors together.
- Same-run sell proceeds are forecast conservatively. Only 80% of approved
  REDUCE/EXIT proceeds are spendable by the same plan, and sell-side pending
  paper orders must be queued before buy-side pending paper orders.

## Existing Foundation

- `docs/MILESTONE.md` is the active milestone tracker and routing source. It
  requires flat milestone IDs, one milestone at a time, completion summaries
  with assumptions/mocks, and React updates in the same milestone as API or
  artifact changes.
- `make paper-loop-kite` is the canonical local Kite-backed, graph-enabled,
  paper-only EOD loop.
- `configs/portfolio/money_management_v1.yaml` defines the current sleeves:
  `core_shariah` 40%, `active_strategy` 35%, `diversifying_strategy` 15%,
  `experimental_models` 5%, and `cash_buffer` 5%.
- `packages/taurus_core/agents/schemas.py` stores analyst report `score` values
  in `[-1, 1]`, which is useful for stance and schema validation but not enough
  to preserve raw ranking precision.
- `packages/taurus_core/agents/technical_analyst.py` clamps computed technical
  scores into `[-1, 1]`.
- `packages/taurus_core/agents/graph_analyst.py` bounds per-edge contributions
  and the final graph analyst score into `[-1, 1]`.
- `packages/taurus_core/agents/research_manager.py` computes confidence-weighted
  consensus from bounded analyst, bull, and bear scores, then clamps the
  consensus into `[-1, 1]`.
- `packages/taurus_core/agents/trader_agent.py` converts consensus into a
  requested new-entry target capped by `max_requested_position_pct_nav`, which
  can flatten higher-conviction BUY requests before allocation.
- `packages/taurus_core/strategies/graph_aware.py` already has raw strategy
  ranking evidence through `raw_strategy_score`; strategy ranking preserves more
  precision than the later allocation score component.
- `packages/taurus_core/portfolio/active_allocation.py` computes candidate
  scores, but `_strategy_score_component()` currently maps raw positive scores
  with `60 + raw * 400`, saturating at 100 when raw score is `0.10` or higher.
  This can erase useful differences between stronger candidates.
- `packages/taurus_core/portfolio/run_allocation.py` batch-ranks BUY proposals
  using candidate score, strategy rank, proposal confidence, symbol, and
  proposal ID. It is partly holistic for BUY proposals, but non-BUY lifecycle
  proposals are preserved rather than optimized and their same-run proceeds do
  not deliberately fund later BUYs.
- `packages/taurus_core/portfolio/core_shariah_basket.py` creates core target
  weights, drift, and decisions, but today those decisions are run artifacts,
  not executable proposal inputs.
- `packages/taurus_core/paper_trading/service.py` settles pending next-open
  orders before analysis, generates strategy and money-management artifacts,
  allocates trader proposals, finalizes selected proposals, and routes
  allocated-only paper orders.
- `packages/taurus_core/brokers/paper_broker.py` can settle next-open orders and
  safely reject or trim unaffordable orders, but the allocator should not rely
  on broker-time trimming as the normal affordability mechanism.
- `packages/taurus_core/replay/service.py`, `apps/api/routes_ui.py`, and
  `apps/web/src/features/*` already expose strategy ranking, allocation
  ledgers, sleeve panels, core basket artifacts, and replay stages. They are
  the right observability surfaces to extend.

## Global Rules For M56-M61

- Keep Taurus paper-only. Do not add live Kite/broker order routing.
- Keep `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` as defaults.
- Keep Kite support data-only; execution continues through local `PaperBroker`.
- Keep the scope long-only, equity-only, and restricted to enabled symbols in
  `configs/market_data/nifty_500_shariah.yaml`.
- Use flat milestone IDs. Do not create submilestones.
- Use `uv` for Python commands. Do not use global `pip install`.
- Use existing SQLAlchemy metadata plus idempotent helpers in
  `scripts/migrate.py` if a schema migration is proven necessary. Prefer JSON
  run artifacts and payload extensions when normalized columns are not needed.
- Preserve backward compatibility for existing paper runs, trader proposals,
  risk reviews, final decisions, and allocation artifacts. Legacy runs should
  keep rendering in the API and React dashboard.
- Do not introduce fractional shares. Whole-share rounding remains part of the
  paper execution contract.
- Treat `requested_position_pct_nav` as the trader's original intent. Store
  portfolio-plan output separately and attach final approved sizing through
  allocation decisions rather than silently overwriting the reason for the
  original request.
- Distinguish score concepts:
  - raw signal score: natural-scale signal used for relative strength and rank
  - calibrated score: monotonic score suitable for cross-agent or cross-strategy
    comparison
  - bounded report score: `[-1, 1]` contract value used for analyst stance and
    compatibility
  - allocation candidate score: `0..100` portfolio-construction score that must
    avoid premature saturation
- Keep the 5% cash buffer as a hard reserve. Soft sleeve borrowing may use idle
  non-cash capacity, but must not borrow the cash buffer.
- For same-run REDUCE/EXIT proceeds, use only an 80% spendable haircut until a
  later milestone explicitly changes this rule.
- For BUY affordability, size against `latest_close * 1.05` plus estimated paper
  costs, and also enforce the hard 5% NAV cash reserve.
- Queue sell-side pending next-open paper orders before buy-side pending
  next-open paper orders so settlement has the best chance to release cash
  before buys are attempted.
- Any API payload, persisted artifact, allocation decision, replay stage, or
  dashboard-visible behavior change must include matching API schemas, React
  types/components/tests, and replay tests in the same milestone.
- At milestone completion, run the stated verification commands and include a
  completion summary with assumptions made, mocks created, and mocks used. Use
  `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the repo's global approval cleanup rule from `docs/MILESTONE.md`.
- When a user asks to execute a specific milestone, implement only that
  milestone. After the requested milestone is complete, verified, cleaned up,
  and documented, stop. Do not start the next milestone, prepare unrelated code
  for the next milestone, or jump ahead automatically.

## M56 - Score Semantics And Allocation Precision Foundation

Purpose: preserve ranking precision by separating raw, calibrated, bounded, and
allocation scores before changing portfolio construction.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/agents/schemas.py`
  - `packages/taurus_core/agents/technical_analyst.py`
  - `packages/taurus_core/agents/graph_analyst.py`
  - `packages/taurus_core/agents/research_manager.py`
  - `packages/taurus_core/agents/trader_agent.py`
  - `packages/taurus_core/strategies/base.py`
  - `packages/taurus_core/strategies/graph_aware.py`
  - `packages/taurus_core/portfolio/active_allocation.py`
  - `packages/taurus_core/portfolio/run_allocation.py`
  - existing tests under `tests/unit/` that cover analysts, strategy ranking,
    allocation, and paper runs
- Add characterization tests that prove current precision loss:
  - strategy scores above `0.10` currently collapse to the same strategy score
    component in allocation
  - trader requested targets above the configured cap are intentionally capped
    and must remain visible as capped, not confused with raw conviction
  - analyst `score` remains bounded and stance-compatible
- Add score metadata without changing trading behavior yet:
  - Extend analyst report payloads with optional score metadata, for example
    `score_metadata` or explicit fields that capture raw, calibrated, and
    bounded values.
  - Keep the normalized `score` column and Pydantic `score` field bounded in
    `[-1, 1]` for compatibility.
  - For deterministic technical and graph analysts, persist raw pre-bound values
    in payload metadata wherever available.
  - For LLM-backed analyst outputs, treat the LLM value as bounded report score
    unless a future prompt/schema change explicitly returns raw signal evidence.
- Add a monotonic calibration helper for allocation-facing scores:
  - It must preserve ordering across common raw score ranges.
  - It must avoid saturating positive raw scores at `0.10`.
  - It must be deterministic and unit-tested.
  - It should expose enough metadata to explain why one symbol outranked
    another.
- Update `PortfolioAllocationService.candidate_score()` and the fallback
  allocation score path to use the new calibrated/rank-aware strategy component
  while preserving old behavior for missing scores.
- Ensure strategy ranking still uses raw strategy scores and rank positions as
  tie-breakers.
- Update API/UI only where the new score metadata is visible:
  - If selection rows or decision trails expose score fields, show calibrated
    allocation score and raw strategy score with clear labels.
  - Do not add a broad dashboard redesign in this milestone.
- Update docs:
  - Add a concise score-semantics note to `docs/TAURUS_AGENT_ARCHITECTURE.md`
    or `docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md`.
  - Update `docs/MILESTONE.md` when the milestone starts and completes.

Expected code shape:

- `score` remains the bounded compatibility field.
- Raw/calibrated score metadata lives in payloads or small typed helper models,
  not in ad hoc string parsing.
- Allocation candidate scoring should be deterministic, monotonic for the same
  strategy family, and explainable through score parts.
- This milestone must not introduce portfolio-level rebalance planning,
  executable core basket orders, same-run proceeds netting, or sleeve borrowing.

Acceptance criteria:

- The system can explain score lineage for technical, graph, strategy, and
  allocation scores.
- BUY candidates that differ meaningfully above the old `0.10` saturation point
  can receive different allocation score components.
- Existing analyst, research, trader, risk, final, and paper execution contracts
  remain backward compatible for legacy payloads.
- React tests pass for any score field rendering that changed.

Verification:

```bash
uv run pytest tests/unit/test_active_allocation.py tests/unit/test_run_allocation.py -q
uv run pytest tests/unit/test_technical_analyst.py tests/unit/test_graph_analyst.py -q
uv run pytest tests/unit/test_paper_runs.py -q
make test-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M57 - Portfolio Rebalance Plan Schema And Dry-Run Artifact

Purpose: introduce a first-class portfolio rebalance plan artifact that observes
the whole portfolio without yet changing order routing.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/allocation_schemas.py`
  - `packages/taurus_core/portfolio/run_allocation.py`
  - `packages/taurus_core/portfolio/active_allocation.py`
  - `packages/taurus_core/portfolio/money_management.py`
  - `packages/taurus_core/portfolio/core_shariah_basket.py`
  - `packages/taurus_core/paper_trading/service.py`
  - `packages/taurus_core/replay/service.py`
  - `apps/api/routes_ui.py`
  - `apps/web/src/api/types.ts`
  - `apps/web/src/features/AllocationPanels.tsx`
  - `apps/web/src/features/RunDetailPage.tsx`
- Add typed schemas for a dry-run plan, preferably in a new portfolio module:
  - `PortfolioRebalancePlan`
  - `PortfolioPlanTrade`
  - `PortfolioPlanCandidate`
  - `PortfolioPlanSleeveBudget`
  - `PortfolioPlanCashBudget`
  - `PortfolioPlanConstraint`
- The dry-run plan must include at least:
  - `run_id`, `portfolio_id`, `model_version`, `policy_version`, `as_of`
  - current NAV, current cash, hard cash reserve, spendable cash before and
    after reserve
  - current positions with symbol, quantity, market value, current pct NAV,
    sleeve ID, and source of sleeve label
  - candidate proposals with action, raw/calibrated score evidence, confidence,
    requested pct NAV, current pct NAV, existing strategy rank, and source
  - core basket target weights and advisory decisions from the current artifact
  - planned trade rows with target pct NAV, delta pct NAV, estimated notional,
    estimated quantity, side, action, source, rank, constraints, and status
  - cash budget rows for existing cash, reserved cash, forecast sell proceeds,
    spendable same-run proceeds after haircut, and unallocated cash
  - sleeve budget rows for target, current, idle capacity, borrowed capacity,
    and projected exposure
- Persist the dry-run plan under the paper-run artifacts, for example:
  - `paper_runs.payload["artifacts"]["portfolio_plan"]`
  - keep the existing `allocation` artifact intact
- Add replay support:
  - Insert a `portfolio_plan` stage between strategy ranking and allocation
    ledger.
  - Legacy runs without a plan should show an empty stage rather than failing.
- Add API/UI support in the same milestone:
  - Expose the plan through existing `/ui/runs/{run_id}` artifacts and the
    allocation dashboard payload.
  - Add compact React panels for plan summary, cash budget, sleeve budget, and
    top planned trades.
  - Keep the UI operational and scan-friendly; do not create a landing page or
    broad redesign.
- Add unit tests proving:
  - legacy runs without `portfolio_plan` still render
  - dry-run plan serializes/deserializes deterministically
  - plan generation does not mutate trader proposals, risk reviews, final
    decisions, orders, fills, positions, or account state
  - replay includes the plan stage when the artifact exists
- Update docs:
  - Document the dry-run artifact in `docs/TAURUS_AGENT_ARCHITECTURE.md`.
  - Update `docs/MILESTONE.md` when the milestone starts and completes.

Expected code shape:

- The dry-run planner should be a separate service from
  `RunLevelAllocationService`, even if it reuses helper functions.
- Use typed Pydantic/dataclass models for plan rows and constraints.
- The dry-run service should consume the same run inputs as allocation but
  should not be the source of truth for order sizing yet.
- No runtime BUY, REDUCE, EXIT, risk, final, or broker behavior should change in
  this milestone.

Acceptance criteria:

- Every new paper run can store a portfolio-level dry-run plan artifact.
- Operators can inspect, via API/UI/replay, how the system would think about
  full-portfolio cash, sleeve, and candidate budgets before order routing
  changes.
- Existing allocation ledger behavior remains unchanged.

Verification:

```bash
uv run pytest tests/unit/test_portfolio_rebalance_plan.py -q
uv run pytest tests/unit/test_replay.py tests/unit/test_ui_aggregate_api.py -q
uv run pytest tests/unit/test_paper_runs.py -q
make test-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M58 - Soft Sleeve Capacity And Executable Core Candidate Model

Purpose: make portfolio capacity explicit by allowing configured soft borrowing
from idle non-cash sleeves and converting core basket decisions into executable
rebalance candidates.

Instructions:

- Read these source areas before editing:
  - `configs/portfolio/money_management_v1.yaml`
  - `packages/taurus_core/portfolio/money_management.py`
  - `packages/taurus_core/portfolio/core_shariah_basket.py`
  - `packages/taurus_core/portfolio/active_allocation.py`
  - `packages/taurus_core/portfolio/run_allocation.py`
  - `packages/taurus_core/paper_trading/service.py`
  - API/UI allocation panels and tests
- Extend the money-management policy with explicit rebalance-capacity rules:
  - hard cash reserve pct NAV, default `5.0`
  - same-run proceeds haircut pct, default `80.0`
  - buy price buffer pct, default `5.0`
  - soft borrowing enabled flag, default enabled for paper
  - borrowable sleeve IDs, excluding `cash_buffer`
  - borrower sleeve IDs, initially `active_strategy`
  - max borrowed capacity pct NAV or notional guard
  - repay/return priority metadata for future observability
- Preserve validation that sleeve targets sum to 100%.
- Keep `cash_buffer` hard and non-borrowable.
- Add sleeve budget calculations to the dry-run plan:
  - current exposure
  - target exposure
  - idle capacity
  - protected capacity
  - borrowable capacity
  - borrowed-by sleeve
  - projected exposure after plan
- Define when a non-cash sleeve is considered idle:
  - no executable candidate above threshold, or
  - sleeve cannot deploy its target because of universe, history, risk,
    concentration, drawdown freeze, or min-notional constraints
- Convert core basket artifact decisions into typed candidates:
  - source: `core_shariah_basket_v1`
  - sleeve: `core_shariah`
  - action: BUY, REDUCE, EXIT, or HOLD
  - target pct NAV from core target weights
  - rank and score evidence from core selection scores
  - rejection reasons from core candidate review
- Add tests for:
  - active strategy can see idle non-cash capacity when policy allows borrowing
  - active strategy cannot borrow the 5% cash buffer
  - inactive/frozen/invalid sleeves do not lend capacity incorrectly
  - core basket BUY/REDUCE/EXIT candidates are generated deterministically from
    the artifact
  - legacy policies without the new fields load with safe defaults
- Update API/UI in the same milestone:
  - show sleeve idle/borrowed/protected capacity in allocation panels
  - show core candidates as plan candidates, not only as passive artifact rows
- Update docs:
  - Explain soft sleeve borrowing in `docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md`.
  - Update `docs/TAURUS_COMMANDS.md` only if commands or env behavior change.
  - Update `docs/MILESTONE.md` when the milestone starts and completes.

Expected code shape:

- Policy defaults should keep old behavior understandable: hard cash buffer
  remains protected; borrowing is explicit in plan metadata.
- Core candidate generation should not bypass risk review, final approval, or
  paper execution. It only creates typed candidates for the planner at this
  stage.
- This milestone may enrich the dry-run plan but should not replace
  `RunLevelAllocationService` as the source of executable proposal sizing yet.

Acceptance criteria:

- The dry-run plan can show why active strategy can or cannot use idle capacity
  beyond its nominal 35% target.
- Core basket candidates are ready to become executable in the next milestone.
- Operators can see borrowed capacity and protected cash separately.

Verification:

```bash
uv run pytest tests/unit/test_money_management.py tests/unit/test_core_shariah_basket.py -q
uv run pytest tests/unit/test_portfolio_rebalance_plan.py -q
uv run pytest tests/unit/test_ui_aggregate_api.py -q
make test-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M59 - Holistic BUY Allocation And Executable Core Routing

Purpose: make the portfolio plan the source of BUY allocation across active and
core candidates while preserving deterministic risk/final/paper execution
handoffs.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/portfolio/run_allocation.py`
  - the new portfolio rebalance planner from M57-M58
  - `packages/taurus_core/agents/trader_agent.py`
  - `packages/taurus_core/risk/engine.py`
  - `packages/taurus_core/risk/review_service.py`
  - `packages/taurus_core/agents/portfolio_manager.py`
  - `packages/taurus_core/paper_trading/service.py`
  - `packages/taurus_core/db/repositories.py`
  - dashboard and replay code that consumes allocation decisions
- Add a feature flag or settings-controlled compatibility path so legacy
  run-level allocation can be retained until final cleanup, but make the new
  planner the default for `make paper-loop-kite` once tests pass.
- Let the planner allocate BUY notional across:
  - active trader BUY proposals
  - executable core BUY candidates
  - existing holdings that need top-up to target
- Stack-rank candidates using:
  - calibrated strategy or core score
  - strategy/core rank
  - trader confidence when present
  - liquidity and volatility
  - diversification and concentration impact
  - sleeve status and borrowed-capacity cost
  - existing position context
- Compute approved BUY notional and whole-share estimates using:
  - current available cash
  - hard 5% cash reserve
  - soft borrowed non-cash sleeve capacity
  - max stock pct NAV and hard cap
  - max open positions
  - max sector and graph-cluster caps
  - trade-risk budget and total open risk budget
  - latest-close reference price uplifted by 5% before estimated costs
- Convert planner-selected BUY rows into proposal/allocation decisions:
  - Existing trader proposals should keep original requested fields and receive
    planner-linked allocation decisions.
  - Core BUY candidates should become deterministic trader-proposal-compatible
    records with `proposal_source` or payload metadata marking them as planner
    generated.
  - Use a lifecycle trigger such as `portfolio_rebalance` for generated core
    or top-up proposals.
  - Keep one proposal per run and symbol; define deterministic conflict rules
    when a trader proposal and a core candidate target the same symbol.
- Persist plan linkage:
  - allocation decision should include `portfolio_plan_id` and
    `portfolio_plan_trade_id`
  - selection ledger should show planner rank and source
  - original requested pct and planner-approved pct should both remain visible
- Run every selected BUY through existing risk review, final decision, and
  `PaperBroker` next-open queueing.
- Update API/UI/replay:
  - selection ledger should show planner source, planner rank, and whether
    capacity was own-sleeve or borrowed
  - replay should connect portfolio plan trade -> allocation decision -> risk
    -> final -> pending order
  - dashboard should distinguish active vs core generated proposals
- Add tests for:
  - all BUY candidates are compared in one rank order
  - active BUY can consume idle non-cash capacity when policy allows it
  - cash buffer remains protected
  - core BUY candidates produce risk/final/pending-order records
  - whole-share rounding can reject tiny plan rows cleanly
  - legacy allocation path still works when the new planner is disabled
- Update docs:
  - Update `docs/TAURUS_AGENT_ARCHITECTURE.md` pipeline diagrams/text.
  - Update `docs/TAURUS_USAGE_GUIDE.md` with new operator semantics.
  - Update `docs/MILESTONE.md` when the milestone starts and completes.

Expected code shape:

- Prefer a new `PortfolioRebalanceService` or equivalent rather than expanding
  `RunLevelAllocationService` until it becomes unreadable.
- Keep risk review deterministic and downstream of planning. The planner should
  propose; risk/final should still approve, reduce, reject, or block.
- Planner-generated core proposals should be auditable and profile-scoped just
  like analyst-generated trader proposals.
- Do not add optimizer-generated REDUCE/EXIT sells or same-run proceeds netting
  in this milestone. That follows in M60.

Acceptance criteria:

- For BUYs, the run is allocated by a holistic plan rather than by per-symbol
  proposal sizing alone.
- Active can deploy beyond 35% NAV only through explicit, observable soft
  borrowing and only while preserving the hard cash buffer.
- Core BUYs can be executed through the same paper-only risk/final/next-open
  flow as active BUYs.

Verification:

```bash
uv run pytest tests/unit/test_portfolio_rebalance_plan.py tests/unit/test_run_allocation.py -q
uv run pytest tests/unit/test_paper_runs.py tests/unit/test_risk_engine.py -q
uv run pytest tests/unit/test_replay.py tests/unit/test_ui_aggregate_api.py -q
make test-ui
make lint
make -n paper-loop-kite
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M60 - Threshold Trims, Same-Run Proceeds Netting, And Execution Buffer

Status: Done.

Purpose: complete full rebalance behavior by allowing the planner to reduce or
exit existing positions, conservatively recycle part of forecast proceeds, and
queue sells before buys.

Instructions:

- Read these source areas before editing:
  - portfolio rebalance planner/service from M57-M59
  - `packages/taurus_core/agents/trader_agent.py`
  - `packages/taurus_core/risk/engine.py`
  - `packages/taurus_core/agents/portfolio_manager.py`
  - `packages/taurus_core/brokers/paper_broker.py`
  - `packages/taurus_core/execution/order_router.py`
  - `packages/taurus_core/db/repositories.py`
  - `packages/taurus_core/paper_trading/service.py`
  - pending next-open settlement tests from M44-M50
- Add planner thresholds for REDUCE/EXIT generation:
  - minimum drift pct NAV
  - minimum notional INR
  - thesis-invalidated or score-below-exit threshold
  - score-below-trim threshold
  - over-hard-cap trim rule
  - stale/unmapped sleeve cleanup rule
  - never sell solely to chase tiny rebalance differences below threshold
- Generate deterministic REDUCE/EXIT proposals for:
  - existing holdings that exceed hard caps
  - holdings no longer supported by active/core thesis beyond threshold
  - core symbols removed from target basket when drift exceeds threshold
  - active holdings whose calibrated score or trader/risk evidence falls below
    configured exit/trim thresholds
- Keep long-only semantics:
  - REDUCE quantity cannot exceed held quantity
  - EXIT quantity equals held quantity
  - No short positions
- Add same-run proceeds netting:
  - Forecast sell proceeds from planned REDUCE/EXIT using latest close minus
    estimated paper costs.
  - Only 80% of forecast sell proceeds are spendable in the same run.
  - Track gross forecast proceeds, haircut, spendable proceeds, and unspendable
    safety reserve in the plan cash budget.
  - If a sell is later rejected by risk/final, remove its proceeds before BUY
    sizing or re-run the planner in-process so BUYs do not depend on rejected
    sells.
- Add execution buffer:
  - Hard cash reserve remains 5% NAV.
  - BUY affordability uses `latest_close * 1.05` plus estimated costs.
  - Planner-approved quantity should already be affordable before broker-time
    settlement. Broker-time trimming remains a final safety fallback only.
- Ensure sell-first queueing:
  - When routing a run's final decisions to pending next-open paper orders,
    submit REDUCE/EXIT orders before BUY orders.
  - Preserve deterministic ordering inside side groups, such as planner rank,
    symbol, then decision ID.
  - Add or update repository/order tests if current pending-order listing order
    depends on submission time.
- Update API/UI/replay:
  - Show planned proceeds, 80% haircut, hard reserve, and price buffer.
  - Show whether a BUY was funded by existing cash, haircut proceeds, borrowed
    sleeve capacity, or a combination.
  - Replay should make sell-proceeds assumptions visible before allocation and
    show sell-side pending orders before buy-side pending orders.
- Update docs:
  - Update `docs/TAURUS_USAGE_GUIDE.md` with proceeds and buffer semantics.
  - Update `docs/TAURUS_AGENT_ARCHITECTURE.md` and
    `docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md`.
  - Update `docs/MILESTONE.md` when the milestone starts and completes.

Expected code shape:

- Thresholds should live in the money-management policy, not as magic numbers
  scattered through planner code.
- Same-run proceeds should be an explicit cash-budget source with haircut
  metadata.
- Route ordering should be deterministic and tested.
- Risk and final approval remain the gatekeepers before any pending paper order
  is created.

Acceptance criteria:

- The planner can rebalance the entire portfolio with BUY, REDUCE, EXIT, and
  HOLD decisions.
- Same-run proceeds are used conservatively and visibly.
- The system preserves at least 5% NAV cash reserve and uses a 5% price buffer
  for BUY affordability.
- Pending next-open sell orders are queued before buys in EOD paper routing.

Verification:

```bash
uv run pytest tests/unit/test_portfolio_rebalance_plan.py -q
uv run pytest tests/unit/test_paper_broker.py tests/unit/test_paper_runs.py -q
uv run pytest tests/unit/test_replay.py tests/unit/test_ui_aggregate_api.py -q
make test-ui
make lint
make -n paper-loop-kite
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

Completion summary:

- Assumptions made: M60 should keep the planner long-only and paper-only;
  threshold REDUCE/EXIT generation should be deterministic from configured
  drift/notional/score/hard-cap/stale-sleeve rules; same-run BUY sizing may use
  only the configured 80% spendable slice of forecast net sell proceeds while
  preserving the 5% NAV hard cash reserve and 5% BUY price buffer; final
  approval remains authoritative, so paper routing only grants BUY pending-cash
  credit after sell-side orders are accepted or filled; M61 remains a separate
  final regression and cleanup milestone.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, mock final
  approval helpers, FastAPI `TestClient`, and existing React fetch stubs.

## M61 - End-To-End Regression, Operator Docs, And Cleanup

Purpose: prove the M56-M60 rebalance upgrade works end to end, remove temporary
compatibility scaffolding where safe, and close the milestone sequence.

Instructions:

- Read the whole M56-M60 plan and current implementation before editing.
- Build an end-to-end deterministic regression that covers:
  - settled account state with cash, existing active position, existing core
    position, and unused non-cash sleeve capacity
  - strategy/trader BUY candidates with distinct raw/calibrated scores above
    the old saturation point
  - executable core BUY or top-up
  - optimizer REDUCE or EXIT for an over-cap or invalidated holding
  - 80% same-run proceeds haircut
  - 5% hard cash reserve
  - 5% BUY reference-price buffer
  - active borrowing idle non-cash capacity while cash buffer remains protected
  - risk/final approval and pending next-open order creation
  - sell-side pending orders queued before buy-side pending orders
  - next-run settlement behavior remains compatible with M44-M50 semantics
- Add API and React regression coverage:
  - `/ui/overview`
  - `/ui/runs/{run_id}`
  - `/ui/runs/{run_id}/symbols/{symbol}`
  - `/ui/replay/{decision_id}`
  - `/ui/portfolio`
  - allocation panels, run-detail selection ledger, decision trail, replay page,
    and portfolio page
- Add or update smoke tooling only if needed:
  - Prefer existing smoke script patterns.
  - Do not introduce external credentials or live broker dependencies.
- Audit docs:
  - `docs/MILESTONE.md`
  - `docs/TAURUS_USAGE_GUIDE.md`
  - `docs/TAURUS_COMMANDS.md`
  - `docs/TAURUS_AGENT_ARCHITECTURE.md`
  - `docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md`
  - `docs/TAURUS_DATABASE_TABLES.md` if schema changed
  - `docs/TAURUS_MOCK_MIGRATION_STATUS.md` if mocks changed
- Decide whether any compatibility flag from M59 should remain:
  - Keep it only if there is a clear operator fallback reason.
  - If kept, document it.
  - If removed, delete dead code and tests that only served the transition.
- Run cleanup:
  - `git status --short`
  - inspect `/Users/adnaan/.codex/rules/default.rules`
  - move Taurus-specific approvals after `# END MY CUSTOM ADDITION` into
    `.codex/rules/default.rules` if required by the repo rule
  - document any command approval changes in `docs/TAURUS_COMMANDS.md`
- Update `docs/MILESTONE.md`:
  - mark M61 complete
  - add completion summaries for M56-M61 if not already present
  - update Current State to describe the new rebalance behavior
  - move or describe the plan according to the repo's active-source convention

Expected code shape:

- The default `make paper-loop-kite` path should use the holistic portfolio
  rebalance planner in paper mode.
- Legacy run artifacts should still load in API/UI/replay.
- New artifacts should be stable, deterministic, and easy to inspect.
- No live-trading, fractional-share, non-equity, or out-of-universe behavior is
  introduced.

Acceptance criteria:

- M56-M60 behavior is covered by focused unit tests and at least one
  deterministic end-to-end paper-run regression.
- React and API tests cover the new portfolio plan, cash/proceeds/buffer, sleeve
  borrowing, core execution, and replay surfaces.
- Operator docs explain how to interpret the new plan and why orders may still
  be reduced or rejected.
- `docs/MILESTONE.md` is complete and accurate for the whole sequence.

Verification:

```bash
uv run pytest tests/unit/test_portfolio_rebalance_plan.py -q
uv run pytest tests/unit/test_paper_runs.py tests/unit/test_paper_broker.py -q
uv run pytest tests/unit/test_replay.py tests/unit/test_ui_aggregate_api.py -q
make test
make test-ui
make lint
make -n paper-loop-kite
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## Deferred Work

- Live broker routing or real Kite order placement.
- Fractional shares.
- Derivatives, intraday strategies, short selling, leverage, margin, or
  non-equity assets.
- Broker-calibrated production charges, tax lots, realized tax optimization, or
  lot-specific sell selection.
- Morning 9:15 automatic scheduling for settlement. Manual EOD settlement
  remains the current workflow unless a later milestone changes scheduling.
- Deposits, withdrawals, and capital event ledgers beyond existing profile
  corpus support.
- Machine-learned cross-strategy calibration. M56 should use deterministic
  monotonic calibration only.
- Multi-profile batch scheduling. One selected profile runs per paper-loop
  invocation.
