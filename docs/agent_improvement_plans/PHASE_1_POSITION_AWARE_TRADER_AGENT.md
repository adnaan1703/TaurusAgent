# Phase 1: Position-Aware TraderAgent

Last reviewed: 2026-05-30

## Summary

Promote `TraderAgent` from a new-entry proposal generator into an after-close
position lifecycle agent. This phase keeps Taurus paper-trading-first and uses
the existing paper loop cadence. It does not add market-hours quote monitoring,
broker-native stop-loss orders, OCO orders, or live broker routing.

Core behavior:

- No current position: propose `BUY` or `NO_TRADE`.
- Existing position: propose `HOLD`, `BUY`, `REDUCE`, or `EXIT`.
- Stop-loss breach: force `EXIT`; LLM can explain but cannot override.
- Take-profit breach: require at least `REDUCE`; validated LLM output may
  recommend stricter `EXIT`.
- Normal reviews: LLM may recommend only within deterministic guardrails.

## Implementation Changes

### TraderAgent

- Change `TraderAgent` to accept `settings` and `llm_provider`.
- Load current portfolio context before proposing:
  - portfolio id
  - latest account equity
  - latest open position for symbol
  - latest close/reference price
  - current quantity
  - average cost
  - current market value
  - current position percent of NAV
  - unrealized PnL
- Treat `requested_position_pct_nav` as the target exposure percent for all
  lifecycle actions.
- Add these `TraderProposal` fields and DB columns:
  - `portfolio_id: str`
  - `current_position_quantity: int`
  - `current_position_pct_nav: Decimal`
  - `target_position_pct_nav: Decimal`
  - `lifecycle_trigger: str`
  - `evaluation_mode: str`
  - `position_management_summary: str`
- Use these lifecycle trigger values:
  - `new_entry`
  - `hold_review`
  - `stop_loss`
  - `take_profit`
  - `thesis_weakened`
  - `thesis_invalidated`
- Use `evaluation_mode="after_close"` in Phase 1.
- Keep default stop-loss and take-profit proposal ratios:
  - `stop_loss_pct=6.0000`
  - `take_profit_pct=12.0000`
- Deterministic action envelope:
  - Stop-loss breach allows only `EXIT`.
  - Take-profit breach allows `REDUCE` or `EXIT`.
  - No position allows `BUY` or `NO_TRADE`.
  - Existing position with bearish thesis allows `REDUCE` or `EXIT`.
  - Existing position with neutral/stable thesis allows `HOLD`, `REDUCE`, or
    `EXIT`.
  - Existing position with stronger bullish thesis allows `HOLD` or `BUY`.
- If LLM output is invalid, unavailable, or recommends outside the allowed
  envelope, fall back to deterministic action and record the fallback in
  `position_management_summary`.

### LLM Provider

- Add `LLMTraderOutput` schema with:
  - `action`
  - `confidence`
  - `target_position_pct_nav`
  - `stop_loss_pct`
  - `take_profit_pct`
  - `reason_summary`
  - `invalid_if`
  - `position_management_summary`
  - `model_version`
- Add `complete_trader_proposal(...)` to the `LLMProvider` protocol.
- Implement trader completion in:
  - `MockLLMProvider`
  - `LMStudioProvider`
  - `OpenAIProvider`
- Use temperature `0` for OpenAI-compatible trader output.
- The LLM output is advisory. `TraderAgent` must validate and clamp action,
  target exposure, and risk text against deterministic guardrails before
  storing the proposal.

### Portfolio Continuity

- Add `TAURUS_PAPER_PORTFOLIO_ID=local-paper` to settings and `.env.example`.
- Add `portfolio_id` to:
  - `PaperAccount`
  - `PaperOrder`
  - `PaperFill`
  - `PaperPosition`
  - corresponding SQLAlchemy models
- Add migrations for Postgres and SQLite-compatible local migration flow.
- Update `ExecutionRepository` with:
  - latest account by `portfolio_id`
  - latest open positions by `portfolio_id`
  - latest open position by `portfolio_id` and symbol
  - list fills by `portfolio_id`
- Update `PaperBroker` state reconstruction to use all prior fills for the
  configured portfolio, not only the current `run_id`.
- Preserve `run_id` on every artifact for auditability, but do not use `run_id`
  as the portfolio boundary.

### Risk And Final Approval

- Update `RiskEngine` so lifecycle actions are valid:
  - `BUY`: enforce max position, max open positions, daily loss, stale data,
    severe event block, and graph risk if enabled.
  - `REDUCE`: require an existing long position and target exposure below
    current exposure.
  - `EXIT`: require an existing long position and target exposure equal to zero.
  - `HOLD` and `NO_TRADE`: approve as no-action decisions when safety checks
    pass.
- Severe negative events should block new/increased `BUY` exposure, but should
  not block `REDUCE` or `EXIT`.
- Update `PortfolioManagerAgent` so it preserves approved lifecycle action:
  - `BUY`: approved quantity is target quantity minus current quantity.
  - `REDUCE`: approved quantity is current quantity minus target quantity.
  - `EXIT`: approved quantity is current quantity.
  - `HOLD` / `NO_TRADE`: approved quantity is zero.
- Add `NO_ACTION` to final decision status for approved `HOLD` and `NO_TRADE`.
- `ExecutionRouter` should route only `APPROVED_FOR_PAPER` decisions with
  executable action and positive quantity.

### PaperBroker

- Continue mapping:
  - `BUY` -> buy-side paper fill
  - `REDUCE` / `EXIT` -> sell-side paper fill
- Reject sell-side actions if no position exists.
- Cap sell quantity to held quantity.
- For `EXIT`, sell the full current quantity.
- For `REDUCE`, sell down toward approved target exposure.
- Keep fills, costs, slippage, cash, realized PnL, unrealized PnL, and open
  positions deterministic.
- Do not add real broker orders or broker-native stop-loss/OCO behavior.

### Paper Run Orchestration

- Update `PaperRunService` to include currently open portfolio symbols in every
  after-close run.
- Preserve requested symbols, but union them with open-position symbols.
- Store run artifacts that identify which symbols came from manual selection and
  which were included because they were open positions.

### API And React Dashboard

- Extend existing API payloads rather than creating a new page.
- Update Overview, Portfolio, Risk, and Decision Trail surfaces to show:
  - action
  - lifecycle trigger
  - evaluation mode
  - current quantity
  - current position percent of NAV
  - target position percent of NAV
  - stop-loss percent
  - take-profit percent
  - position management summary
  - final order versus no-action status
- For `HOLD` and `NO_TRADE`, show "No paper order expected" instead of treating
  missing paper orders as suspicious.

## Test Plan

- `TraderAgent`:
  - no position plus bullish consensus proposes `BUY`
  - no position plus weak/neutral/bearish consensus proposes `NO_TRADE`
  - existing position plus stable thesis proposes `HOLD`
  - existing position plus stop-loss breach forces `EXIT`
  - existing position plus take-profit breach proposes at least `REDUCE`
  - invalid LLM output falls back to deterministic proposal
  - LLM cannot recommend outside deterministic action envelope
- `RiskEngine` and `PortfolioManagerAgent`:
  - `REDUCE` and `EXIT` require an existing position
  - sell quantity never exceeds held quantity
  - severe negative events block new `BUY` but not `EXIT`
  - `HOLD` and `NO_TRADE` produce `NO_ACTION` and no broker route
- `PaperBroker`:
  - positions persist across multiple run IDs under one `portfolio_id`
  - later run can reduce or exit a position opened in an earlier run
  - cash, realized PnL, unrealized PnL, and open positions update after sell
    fills
- Paper loop and UI:
  - open-position symbols are included automatically in later runs
  - decision trail shows lifecycle trigger and position context
  - dashboard clearly distinguishes executable orders from no-action decisions

## Acceptance Criteria

- A paper position opened in one run can be reviewed, held, reduced, or exited in
  a later run.
- Stop-loss and take-profit thresholds affect TraderAgent proposals in the
  after-close loop.
- LLM trader reasoning is present, but deterministic guardrails remain
  authoritative.
- `HOLD` and `NO_TRADE` decisions do not produce paper orders and are displayed
  as expected no-action outcomes.
- Existing paper BUY behavior remains backwards compatible for no-position
  symbols.

## Assumptions

- Taurus remains long-only.
- Taurus remains paper-trading-first.
- Live broker routing remains disabled.
- Stop-loss and take-profit are proposal triggers, not automatic broker-native
  orders.
- Phase 1 uses latest available after-close data only.
- Market-hours quote monitoring is intentionally deferred to Phase 2.
