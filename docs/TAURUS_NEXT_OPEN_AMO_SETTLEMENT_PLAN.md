# Taurus Next-Open AMO Settlement Plan

Last updated: 2026-06-04

This document is the implementation plan for fixing Taurus paper execution so
after-close paper decisions behave like AMO-style next-open orders. Each
milestone below is a standalone milestone intended to be executed in a separate
Codex thread. Stop after completing and documenting the current milestone; do
not automatically continue to the next milestone.

## Current Problem

The current `PaperBroker` immediately fills approved after-close decisions
against the latest stored daily candle. For large orders, the first simulated
fill uses that candle's open and the second fill uses that candle's close. This
creates look-ahead bias for an end-of-day workflow because an after-close
decision cannot realistically receive the same day's opening price.

The target behavior is:

```text
Day N after close:
  Analyze Day N daily candle.
  Create BUY, REDUCE, or EXIT paper order as PENDING_NEXT_OPEN.
  Do not create fills, do not debit cash, and do not realize P&L yet.

Day N+1 after latest candles are imported:
  Settle pending Day N orders using Day N+1 daily candle open.
  Apply slippage and paper costs.
  Rebuild cash, positions, realized P&L, and unrealized P&L.
  Mark remaining positions using the latest available daily candle close.
  Run new after-close analysis and create the next pending orders.
```

## Global Rules For M44-M50

- Keep Taurus paper-only. Do not add live Kite/broker order routing.
- Keep `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` as defaults.
- Use Kite daily candles as the trading calendar for this work. Do not add a
  separate NSE holiday calendar.
- Preserve the market-hours position monitor as a separate immediate-routing
  simulation unless the current milestone explicitly changes it.
- Use existing SQLAlchemy metadata migration patterns in `scripts/migrate.py`;
  Taurus does not use Alembic.
- Update `docs/TAURUS_MILESTONE_TODO.md` whenever starting or completing a
  milestone.
- If API payloads, artifacts, or statuses change, update React dashboard tests
  and UI rendering in the same milestone.
- At milestone completion, run the stated verification commands and include a
  completion summary with assumptions made, mocks created, and mocks used. Use
  `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the repo's global approval cleanup rule from
  `docs/TAURUS_MILESTONE_TODO.md`.

## M44 - Baseline Tests And Tracker Setup

Purpose: record the next-open settlement work as active milestone work and add
failing/xfail-free tests that prove the existing behavior is wrong.

Instructions:

- Read the current execution path before editing:
  - `packages/taurus_core/brokers/paper_broker.py`
  - `packages/taurus_core/execution/order_router.py`
  - `packages/taurus_core/execution/schemas.py`
  - `packages/taurus_core/paper_trading/service.py`
  - `tests/unit/test_paper_broker.py`
  - `tests/unit/test_paper_runs.py`
- Update `docs/TAURUS_MILESTONE_TODO.md` with an active M44 entry that points to
  this plan and says M44 is in progress.
- Add tests for the intended behavior, even though they fail before M45/M46:
  - An after-close BUY decision should create an order with no fills and no cash
    debit.
  - The order status should represent waiting for next open.
  - The same-day candle open must not be used as a fill for an after-close
    order.
  - Existing immediate-routing behavior should remain available for
    market-hours monitor decisions.
- Prefer focused unit tests in `tests/unit/test_paper_broker.py`. If a paper run
  integration test is necessary, keep it small and deterministic.
- Do not implement the new behavior in this milestone beyond any minimal schema
  scaffolding needed for tests to import.

Expected code shape:

- If the tests need a new order status literal, add only the minimal status
  constant or type extension required for test compilation.
- Do not introduce new repository settlement methods yet.

Acceptance criteria:

- `docs/TAURUS_MILESTONE_TODO.md` records M44 status.
- Tests clearly document the target behavior and fail against the old immediate
  EOD fill path before implementation.
- No runtime behavior is intentionally changed.

Verification:

```bash
uv run pytest tests/unit/test_paper_broker.py -q
```

Completion summary requirements:

- State that this milestone intentionally introduced failing tests if full
  `make test` is not expected to pass yet.
- Assumptions made
- Mocks created
- Mocks used

## M45 - Pending Next-Open Order Schema And Repository Support

Purpose: make pending AMO-style paper orders first-class in schemas,
repositories, API payloads, and observability without changing full run
settlement yet.

Instructions:

- Update execution schemas:
  - Add `PENDING_NEXT_OPEN` to `OrderStatus`.
  - Add optional fields to `PaperOrder` payloads:
    - `execution_policy`: `"immediate"` or `"next_open"`, default
      `"immediate"` for backward compatibility.
    - `signal_trade_date`: optional date for the candle date that informed the
      after-close decision.
    - `scheduled_fill_session`: optional string, use `"next_open"` for pending
      AMO-style orders.
    - `filled_trade_date`: optional date, set when settlement creates fills.
  - Keep existing persisted historical payloads valid.
- Update repository helpers in `ExecutionRepository`:
  - Add a list method for pending next-open orders by portfolio, optionally
    filtered by symbol.
  - Ensure `list_orders`, `get_order`, and payload validation continue to work
    for old orders.
  - Add an update/replace method that can turn one pending order into a filled,
    partially filled, or rejected order while preserving the original order ID.
- Update UI/API status handling:
  - `/paper/orders` should return pending orders through the existing response
    model.
  - UI aggregate endpoints should count and stage pending orders as in-progress,
    not failed.
  - React status mapping should display a pending/queued label for
    `PENDING_NEXT_OPEN`.
- Update docs:
  - `docs/TAURUS_DATABASE_TABLES.md` should mention pending AMO-style paper
    orders in the `paper_orders` description.
  - `docs/TAURUS_USAGE_GUIDE.md` should mention that EOD orders can be queued
    for next-open settlement once later milestones enable it.

Expected code shape:

- No new SQL columns are required in this milestone unless an implementer proves
  JSON payload metadata is insufficient. The existing `status` column is a
  string, and detailed order data already lives in `payload`.
- `PaperOrderModel.status` can store `PENDING_NEXT_OPEN` without schema
  migration.
- The repository should not settle orders yet; it only needs to find and update
  them safely.

Acceptance criteria:

- Existing historical order payloads still validate.
- Pending orders can be inserted, listed, returned by the API, and displayed by
  the UI.
- Pending order status does not inflate filled-order metrics.
- M44 schema-related tests pass; behavior tests that require settlement may
  still fail if not part of this milestone.

Verification:

```bash
uv run pytest tests/unit/test_paper_broker.py tests/unit/test_ui_aggregate_api.py -q
make test-ui
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M46 - PaperBroker Pending Order Creation

Purpose: make after-close approved final decisions create pending next-open
orders instead of immediate fills, while preserving immediate paper fills for
market-hours monitor decisions.

Instructions:

- Add an execution policy boundary:
  - EOD/after-close decisions should route with `execution_policy="next_open"`.
  - Market-hours monitor decisions should route with `execution_policy="immediate"`.
  - Avoid relying only on wall-clock time. Use existing run/proposal context
    where available, especially `evaluation_mode` and `run_after_market_close`.
- Update `ExecutionRouter` and/or `PaperBroker.place_order` so callers can
  choose the policy without duplicating broker logic.
- For `next_open` orders:
  - Rebuild portfolio state from historical fills before sizing.
  - Use the latest available daily candle only to determine the
    `signal_trade_date`, reduce sizing reference, and account mark.
  - Validate that BUY, REDUCE, and EXIT are executable.
  - Store a `PENDING_NEXT_OPEN` `PaperOrder` with:
    - zero `filled_quantity`
    - full `remaining_quantity`
    - zero gross value, costs, slippage, and average fill
    - `submitted_at` from the final decision timestamp
    - `signal_trade_date` equal to the latest candle's `trade_date`
    - `scheduled_fill_session="next_open"`
    - `status_history=["CREATED", "ACCEPTED", "PENDING_NEXT_OPEN"]`
  - Do not create `PaperFill` rows.
  - Do not change cash or positions beyond storing the current account snapshot
    for the run.
- For `immediate` orders:
  - Preserve current fill behavior for market-hours monitor flows unless a
    later explicit milestone changes it.
  - Existing immediate tests should continue to pass after updating expected
    call paths.
- Update run artifacts so an EOD symbol with a queued order records status
  `PENDING_NEXT_OPEN` and a clear reason such as
  `queued_for_next_open_settlement`.

Expected code shape:

- Keep the existing cost and slippage models.
- Keep immediate fill helpers reusable; they will be used by settlement in M47.
- Do not settle previous pending orders in this milestone except where tests
  explicitly exercise immediate routing.

Acceptance criteria:

- EOD BUY/REDUCE/EXIT final decisions create pending orders with no fills.
- Account cash and open positions are not changed by queuing an EOD order.
- Immediate market-hours monitor routing still produces fills.
- Dashboard/API run detail shows queued orders without pretending they are
  filled.

Verification:

```bash
uv run pytest tests/unit/test_paper_broker.py tests/unit/test_paper_runs.py tests/unit/test_position_monitor.py -q
make test-ui
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M47 - Next-Open Settlement Engine

Purpose: settle pending next-open paper orders at the first newer daily candle's
open and calculate cash, positions, realized P&L, unrealized P&L, costs, and
slippage correctly.

Instructions:

- Add a settlement service or broker method, preferably inside
  `PaperBroker`/execution code so fill logic stays centralized.
- Settlement input:
  - portfolio ID
  - current run ID
  - optional symbol filter
  - settlement timestamp
- Settlement process:
  - Load all `PENDING_NEXT_OPEN` orders for the portfolio in submitted order.
  - For each pending order, find the first daily candle for the order symbol
    with `trade_date > order.signal_trade_date`.
  - If no newer candle exists, leave the order pending and record
    `waiting_for_next_candle`.
  - Use that first newer candle's `open` as `reference_price_inr`.
  - Apply slippage:
    - BUY fill price = open adjusted upward by configured slippage.
    - SELL fill price = open adjusted downward by configured slippage.
  - Create exactly one fill per settled pending order. Do not split AMO
    settlement across open and close.
  - Apply existing brokerage, exchange transaction charge, tax levy, and
    slippage calculations.
  - Rebuild account state from all fills in chronological order before each
    settlement batch.
  - For BUY, cap quantity by available cash if needed and reject if zero
    quantity is affordable.
  - For SELL/EXIT/REDUCE, cap quantity by holdings and reject if no holdings
    remain.
  - Mark the settled order `FILLED`, `PARTIALLY_FILLED`, or `REJECTED`.
  - Set `filled_trade_date` to the execution candle date.
  - Store fill `trade_date` as the execution candle date and `filled_at` as the
    current settlement timestamp plus a deterministic sequence offset.
  - After all settlements, mark open positions to the latest available daily
    close for each open symbol.
- Settlement artifacts:
  - Return a summary with settled, rejected, still-pending, and skipped counts.
  - Include per-order details: order ID, symbol, side, signal trade date,
    execution trade date, reference open, fill price, quantity, status, and
    rejection reason if any.
- Alerts:
  - Send fill alerts only when settlement creates a fill.
  - Send rejection alerts only when settlement rejects a pending order.
  - Do not resend alerts for orders still pending.

Expected code shape:

- Reuse existing `_apply_fill`, `_account_and_positions`, cost model, and
  slippage model where possible.
- Add repository methods for pending-order lookup and order/fill/account-state
  replacement rather than duplicating SQL in the service.
- Preserve deterministic IDs as much as possible. If fill ID generation needs to
  include execution date or reference price, update tests accordingly.

Acceptance criteria:

- Pending BUY settles at next candle open, not same-day open or close.
- Pending SELL/EXIT realizes P&L using next candle open minus costs.
- Missed manual runs settle using the first candle after signal date, not the
  latest imported candle.
- Orders remain pending when no newer candle exists.
- Rejections and partial fills are deterministic and visible.

Verification:

```bash
uv run pytest tests/unit/test_paper_broker.py -q
uv run pytest tests/unit/test_paper_runs.py -q
make test
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M48 - Integrate Settlement Into Manual EOD Paper Loop

Purpose: make `make paper-loop-kite` and related manual EOD loop commands
settle old pending orders before analyzing the new after-close state.

Instructions:

- Update `PaperRunService.run_once` setup order:
  - Normalize requested symbols.
  - Run migrations.
  - Gather current open position symbols.
  - Gather pending next-open order symbols.
  - Merge requested, open-position, and pending-order symbols into the run
    symbol scope.
  - Import latest Kite daily candles.
  - Settle pending next-open orders for the portfolio.
  - Re-read open positions/account after settlement.
  - Continue strategy generation, analysis, allocation, risk, final decision,
    and EOD pending order creation.
- Make settlement visible in run artifacts:
  - Add a top-level `settlement` artifact with summary counts and per-order
    details.
  - Add symbol-level settlement info where useful for dashboard drilldowns.
  - Record pending orders still waiting for a newer candle.
- Update allocation/risk inputs:
  - The post-settlement account and positions must be used for current NAV,
    current position quantities, exposure checks, and lifecycle decisions.
  - Queued orders from the current run must not affect cash/position state until
    the next settlement.
- Update command/operator docs:
  - Explain that a manual EOD run first settles previous pending orders using
    the newly imported daily candle open, then creates new pending orders for
    the next trading day.
  - Mention that if a run is skipped, settlement uses the first available
    candle after the signal date.
- Update tests:
  - Paper loop integration should cover a two-run or three-run sequence:
    - first run queues BUY
    - second run settles BUY and can queue EXIT
    - third run settles EXIT and realizes P&L
  - Existing tests expecting immediate EOD fills should be rewritten to pending
    or settlement expectations.

Expected code shape:

- Keep settlement at the start of the run, after market data import and before
  analysis.
- Do not introduce a scheduler or morning job in this milestone.
- Do not route pending orders through live Kite.

Acceptance criteria:

- `make paper-loop-kite` semantics match the manual EOD workflow.
- Dashboard and API run details expose the settlement phase.
- Position-aware analysis sees settled positions and cash from prior orders.
- New EOD decisions from the same run are queued for next open.

Verification:

```bash
uv run pytest tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py -q
make test
make test-ui
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M49 - Dashboard, Replay, Metrics, And Operator Polish

Purpose: make pending and settled next-open orders understandable across the
React dashboard, Streamlit fallback, replay, alerts, and metrics.

Instructions:

- React dashboard:
  - Show pending next-open orders as queued or pending, not incomplete failure.
  - Show settlement artifacts on run overview/detail pages.
  - Show fill trade date and signal trade date where order/fill details are
    displayed.
  - Ensure long text fits in compact tables and stage cards.
- Streamlit fallback:
  - Add pending status display where order tables are shown.
  - Include signal date, scheduled fill session, and filled trade date if
    present.
- Replay:
  - Include pending order payloads in decision replay.
  - For pending orders, show no paper fills rather than a failed fill stage.
  - For settled orders, show original order status history and final fill.
- Metrics:
  - Ensure paper order status metrics include `PENDING_NEXT_OPEN`.
  - Add a settlement counter or artifact-derived metric only if it fits existing
    metrics patterns.
- Alerts:
  - Confirm queued orders do not trigger fill alerts.
  - Confirm settlement fills/rejections produce one alert per final outcome.
- Documentation:
  - Update `docs/TAURUS_AGENT_ARCHITECTURE.md`,
    `docs/TAURUS_USAGE_GUIDE.md`, `docs/TAURUS_COMMANDS.md`, and
    `docs/TAURUS_DATABASE_TABLES.md` as needed.
  - Keep wording clear that Kite remains data-only and all fills are simulated.

Expected code shape:

- Prefer using existing status helpers and table components.
- Avoid adding a new dashboard page unless existing pages cannot reasonably show
  the settlement information.
- Keep UI dense and operational; this is not a marketing or hero-page change.

Acceptance criteria:

- UI clearly distinguishes queued, filled, partially filled, and rejected paper
  orders.
- Replay and metrics do not misclassify pending orders.
- Operator docs describe the manual daily process without ambiguity.

Verification:

```bash
make test
make test-ui
make build-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M50 - End-To-End Regression And Cleanup

Purpose: verify the complete M44-M50 workflow end to end, close the milestone
sequence, and clean up docs and command approvals.

Instructions:

- Run the full backend and frontend verification suite:
  - `make test`
  - `make test-ui`
  - `make build-ui`
  - `make lint`
- Run or document an operator-level smoke scenario. Prefer a deterministic test
  database workflow if live Kite credentials are unavailable:
  - Create/import at least two daily candles for a symbol.
  - Run an EOD BUY that queues.
  - Add/import the next daily candle.
  - Run the next EOD loop and verify BUY settlement at next open.
  - Queue an EXIT.
  - Add/import the following daily candle.
  - Run again and verify realized P&L from the following open.
- Inspect relevant API responses:
  - `/paper/orders`
  - `/paper/fills`
  - `/paper/positions`
  - `/paper/account`
  - `/ui/overview`
  - `/ui/runs/{run_id}` if available.
- Verify no live broker routing was added and safety defaults remain paper-only.
- Update `docs/TAURUS_MILESTONE_TODO.md`:
  - Mark M44-M50 complete.
  - Summarize the final behavior.
  - Remove or archive transient active-plan wording if appropriate.
- Inspect `/Users/adnaan/.codex/rules/default.rules`:
  - Treat entries after `# END MY CUSTOM ADDITION` as accidental global
    approvals.
  - Copy missing Taurus-specific prefixes into `.codex/rules/default.rules`.
  - Document copied prefixes in `docs/TAURUS_COMMANDS.md`.
  - Remove only Taurus-specific accidental global approvals.
  - Do not copy unrelated global approvals, such as `npx clasp`.

Acceptance criteria:

- Full test and build verification passes, or failures are documented with
  exact causes.
- Manual EOD semantics are documented and tested.
- `docs/TAURUS_MILESTONE_TODO.md` accurately reflects M44-M50 completion.
- Completion summary includes assumptions made, mocks created, and mocks used.

Verification:

```bash
make test
make test-ui
make build-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## Deferred Follow-Up

Morning settlement remains deferred. A later milestone may add a 9:15 or 9:16
manual command/job that uses Kite quote/OHLC snapshots to settle pending orders
earlier in the day. That future work must still remain paper-only unless a new
explicit live-broker milestone is approved.
