# Phase 2: Market-Hours Position Monitor

Last reviewed: 2026-05-30

## Summary

Add a market-hours position monitor that checks open paper positions against
stop-loss and take-profit thresholds using latest quote data. This phase builds
on Phase 1 position-aware `TraderAgent` and portfolio continuity.

The monitor does not place real broker orders and does not create broker-native
OCO orders. It creates lifecycle proposals that flow through the same Taurus
decision trail:

```text
quote update -> SL/TP trigger -> TraderProposal -> RiskReview -> FinalDecision -> PaperBroker
```

## Implementation Changes

### Runtime Service

- Add a market-hours monitor service, for example `PositionMonitorService`.
- Add a script and Make target:
  - `scripts/run_position_monitor.py`
  - `make position-monitor`
- The monitor runs only when Taurus is in paper mode and broker provider is
  `paper`.
- The monitor should be configurable with:
  - `TAURUS_POSITION_MONITOR_ENABLED=false`
  - `TAURUS_POSITION_MONITOR_INTERVAL_SECONDS=30`
  - `TAURUS_POSITION_MONITOR_PROVIDER=kite`
  - `TAURUS_POSITION_MONITOR_MARKET_HOURS_ONLY=true`
  - `TAURUS_POSITION_MONITOR_MAX_ITERATIONS=0`
- `MAX_ITERATIONS=0` means run continuously until stopped.
- For local/dev verification, allow a finite iteration count.

### Data Provider

- Reuse existing market data provider abstractions where possible.
- For Kite, use latest quote/LTP snapshot retrieval.
- For mock mode, provide deterministic quote snapshots so tests can trigger
  stop-loss and take-profit without external services.
- Persist latest quote snapshots before evaluating triggers so every monitor
  decision has auditable input data.
- If quote retrieval fails, log/audit the failure and skip that symbol for that
  iteration.

### Trigger Evaluation

- Load all open positions for `TAURUS_PAPER_PORTFOLIO_ID`.
- For each open position, load the latest active trade thesis/proposal metadata
  for that symbol:
  - stop-loss percent
  - take-profit percent
  - average cost
  - current quantity
  - latest target exposure
- Compute:
  - stop-loss price from average cost and `stop_loss_pct`
  - take-profit price from average cost and `take_profit_pct`
  - latest price from quote snapshot
- Trigger rules:
  - latest price <= stop-loss price -> create `EXIT` proposal
  - latest price >= take-profit price -> create `REDUCE` proposal by default
  - if no threshold is crossed -> no proposal
- Use `evaluation_mode="market_hours"`.
- Use lifecycle triggers:
  - `stop_loss`
  - `take_profit`
- Deduplicate repeated triggers:
  - Do not create another open trigger proposal for the same symbol, trigger,
    and threshold while a previous final decision/order for that trigger is
    already pending or completed in the same market session.

### Decision Flow

- The monitor should call the same TraderAgent/RiskReview/PortfolioManager flow
  used by paper runs.
- For hard stop-loss triggers, `TraderAgent` must force `EXIT` and LLM can only
  explain.
- For take-profit triggers, deterministic floor is `REDUCE`; LLM may recommend
  stricter `EXIT`.
- `RiskEngine` must not block exits due to severe negative events.
- `PaperBroker` executes only after final approval and remains deterministic.

### Observability And Alerts

- Add audit events for:
  - monitor iteration started
  - quote snapshot received
  - trigger detected
  - trigger skipped
  - proposal created
  - monitor error
- Add Prometheus metrics:
  - monitor iterations
  - quote fetch failures
  - stop-loss triggers
  - take-profit triggers
  - proposals created
  - paper exits/reductions routed from monitor
- Send alert events for stop-loss and take-profit triggers using the configured
  alert adapter.

### API And React Dashboard

- Extend existing dashboard surfaces, not a new page for v1.
- Overview:
  - show latest monitor status and last iteration time
  - show count of market-hours triggers today
- Portfolio:
  - show SL/TP prices next to each open position
  - show latest quote/LTP and distance to stop-loss/take-profit
- Decision Trail:
  - show `evaluation_mode=market_hours`
  - show quote snapshot used for trigger decision
  - show trigger type and threshold crossed
- Risk:
  - distinguish monitor-generated `EXIT` / `REDUCE` risk reviews from
    after-close proposals
- For monitor-generated no-order states, show why no order was expected or why a
  trigger was skipped.

## Test Plan

- Monitor service:
  - no open positions results in no proposals
  - quote fetch failure logs/audits and does not crash the loop
  - stop-loss breach creates one `EXIT` proposal
  - take-profit breach creates one `REDUCE` proposal
  - repeated quote breaches do not create duplicate trigger proposals for the
    same session
- Provider tests:
  - mock quote provider can force stop-loss and take-profit scenarios
  - Kite provider failures are handled without mutating position state
- Decision flow:
  - monitor-generated `EXIT` passes through risk/final approval and PaperBroker
    sell-side execution
  - monitor-generated `REDUCE` sells down toward target exposure
  - severe negative event does not block `EXIT`
- Dashboard/API:
  - portfolio rows show threshold prices and latest quote
  - decision trail shows market-hours evaluation mode and trigger evidence
  - overview shows monitor status and trigger counts

## Acceptance Criteria

- Running `make position-monitor` can detect a mock stop-loss breach and create
  an auditable `EXIT` paper decision.
- Running `make position-monitor` can detect a mock take-profit breach and create
  an auditable `REDUCE` paper decision.
- Kite quote failures do not crash the monitor.
- Duplicate trigger protection prevents repeated proposals for the same symbol
  and threshold in one market session.
- Dashboard clearly shows whether a lifecycle decision came from after-close
  review or market-hours monitoring.

## Assumptions

- Phase 1 has already added cross-run portfolio continuity and position-aware
  TraderAgent behavior.
- Taurus remains paper-only.
- No real broker order routing is added.
- No broker-native OCO order is added.
- The first market-hours implementation may use polling; true streaming can be
  added later if needed.
