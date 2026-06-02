# Paper Money Management System Plan

Last reviewed: 2026-06-01

Execution order: starts after M30. Run each milestone in this document in a
fresh context. After a milestone is implemented, verified, cleaned up, and
documented with its completion summary, stop and report the result. Do not
automatically start the next milestone unless the user explicitly asks.

## Summary

Add a deterministic money-management system for the paper portfolio so Taurus
allocates capital by risk-adjusted opportunity instead of treating every
approved buy signal equally.

The system remains paper-trading-first, long-only, equity-only, and restricted
to the Shariah-compliant NSE equity universe from:

```text
configs/market_data/nifty_500_shariah.yaml
```

No ETFs, non-Shariah symbols, leverage, shorting, derivatives, or live broker
order routing are in scope.

The desired steady-state portfolio structure is:

| Sleeve | Target | Role |
|---|---:|---|
| Core Shariah equity basket | 40% | Conservative diversified equity anchor from the Shariah universe |
| Active strategy | 35% | Main alpha sleeve, initially graph-aware strategy |
| Diversifying strategy | 15% | Secondary style, initially after backtest validation |
| Experimental models | 5% | Small-risk sleeve for new model candidates |
| Cash/risk buffer | 5% | Operational buffer, gap/drawdown protection, new opportunity reserve |

## Strategy Map

Current repo strategies:

- `graph_aware_score_v1`: canonical Kite paper-loop strategy via
  `make paper-loop-kite`; use as the initial active sleeve.
- `blended_score_v1`: technical/factor ranker using return momentum, EMA trend,
  RSI, volatility penalty, and volume confirmation; use as the first
  diversifying candidate after backtest validation.
- `moving_average_crossover_v1`: simple trend baseline and default fallback;
  keep for regression/backtest comparison, not primary allocation.

New strategy capability to add:

- `core_shariah_basket_v1`: conservative basket constructor from
  `nifty_500_shariah.yaml`, selecting 12-20 liquid, lower-volatility,
  diversified Shariah-compliant equities and weighting them by inverse
  volatility with concentration caps.

## Hard Invariants

- Every deployable symbol must be enabled in
  `configs/market_data/nifty_500_shariah.yaml`.
- Runtime market data remains Kite data-only.
- Execution remains `PaperBroker`; no live broker routing.
- `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` remain defaults.
- Risk-reducing `REDUCE` and `EXIT` lifecycle actions must not be blocked by
  new allocation rules unless paper-safe settings fail.
- Deterministic risk and allocation rules are authoritative. LLM output may
  explain or propose within guardrails only.

## M31: Money Management Policy And State Foundation

### Goal

Introduce the policy/config/state layer without changing order sizing behavior.
This gives later milestones stable APIs and observability.

### Implementation Changes

- Add a portfolio policy config, for example
  `configs/portfolio/money_management_v1.yaml`, with:
  - Shariah universe path
  - sleeve targets
  - strategy-to-sleeve mapping
  - cash buffer target
  - max stock, sector, graph-cluster, and open-position limits
  - trade-risk defaults
  - drawdown governor thresholds
  - rebalance thresholds
- Add settings:
  - `TAURUS_MONEY_MANAGEMENT_ENABLED=false` initially
  - `TAURUS_MONEY_MANAGEMENT_CONFIG_PATH=configs/portfolio/money_management_v1.yaml`
- Add Pydantic schemas for:
  - portfolio policy
  - sleeve policy
  - strategy mapping
  - allocation decision
  - sleeve snapshot
- Add deterministic validation:
  - sleeve weights must sum to 100%
  - cash buffer must be non-negative
  - max stock hard cap must be greater than or equal to normal cap
  - every configured core symbol, if any, must exist in the Shariah universe
- Add database support for allocation/sleeve snapshots only if needed for
  durable history. Prefer JSON payloads and existing artifact patterns unless a
  dedicated table materially improves querying.
- Surface policy state in `/ui/portfolio` and `/ui/risk` payloads as read-only
  metadata.

### Test Plan

- Unit-test config load/validation failures.
- Unit-test Shariah universe membership enforcement.
- Unit-test disabled mode preserves existing paper-run behavior exactly.
- API/UI aggregate tests confirm policy metadata appears when enabled.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add a section to this document listing assumptions made, mocks
created, and mocks used.

### M31 Completion Summary

- Status: Completed on 2026-06-01.
- Implemented `configs/portfolio/money_management_v1.yaml` with Shariah
  universe, sleeve targets, strategy mappings, cash buffer, concentration
  limits, trade-risk defaults, drawdown governors, and rebalance thresholds.
- Added disabled-by-default settings:
  `TAURUS_MONEY_MANAGEMENT_ENABLED=false` and
  `TAURUS_MONEY_MANAGEMENT_CONFIG_PATH=configs/portfolio/money_management_v1.yaml`.
- Added Pydantic policy/state schemas and deterministic validation for sleeve
  weights, cash buffer, stock caps, strategy sleeve references, and configured
  core symbol membership in the Shariah universe.
- Surfaced read-only money-management metadata in `/ui/risk` and
  `/ui/portfolio`; no database table was added because M31 only needs current
  config/state metadata and snapshot schemas, not durable historical querying.
- Verified disabled mode does not add paper-run artifacts or change existing
  paper execution behavior.
- Assumptions made: M31 should include the 5% cash buffer as an explicit sleeve
  so configured sleeve weights sum to 100%; durable allocation/sleeve snapshot
  tables are deferred until later milestones need historical queries.
- Mocks created: None.
- Mocks used: Existing unit-test fake LLM and fake Kite market-data providers.

## M32: Core Shariah Equity Basket

### Goal

Deploy the formerly unused 40% core sleeve into a conservative Shariah-compliant
equity basket.

### Implementation Changes

- Add `CoreShariahBasketStrategy` or equivalent basket-builder service.
- Candidate universe is only enabled NSE equity symbols from
  `configs/market_data/nifty_500_shariah.yaml`.
- Selection rules:
  - require sufficient daily candle history
  - rank by lower realized volatility, liquidity, medium-term trend quality,
    and diversification score
  - exclude symbols blocked by stale data, unsupported instruments, severe
    negative events, or Shariah-universe mismatch
  - prefer 12-20 names when enough candidates exist
- Weighting rules:
  - inverse-volatility target weights
  - normal single-stock cap 5% NAV
  - hard single-stock cap 7.5% NAV
  - sector/graph concentration caps reused where data exists
  - no position smaller than the configured minimum rebalance notional
- Rebalance behavior:
  - review daily after close
  - generate core rebalance decisions at most monthly unless drift exceeds
    20% of sleeve target or INR 5,000
  - avoid tiny rebalance trades
- Add core artifacts:
  - selected symbols
  - rejected candidates and reasons
  - target weights
  - current weights
  - drift
  - rebalance/not-rebalance rationale

### Test Plan

- Unit-test basket selection respects Shariah universe membership.
- Unit-test inverse-volatility weights and caps.
- Unit-test monthly/drift rebalance gates.
- Integration-test a paper run with core enabled creates only Shariah NSE equity
  core decisions.
- Run `make test` and `make lint`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### Completion Summary

- Status: Completed on 2026-06-02.
- Added `CoreShariahBasketStrategy` to build a conservative long-only core
  basket exclusively from enabled NSE equity symbols in
  `configs/market_data/nifty_500_shariah.yaml`.
- Added selection artifacts for selected symbols, rejected candidates and
  reasons, score inputs, target/current weights, sleeve drift, rebalance gates,
  and per-symbol core decisions.
- Added inverse-volatility target weighting with configured normal/hard
  single-stock caps, minimum rebalance notional filtering, and optional
  sector/graph concentration caps when graph metadata exists.
- Wired money-management-enabled paper runs to create read-only core basket
  artifacts without routing core orders or changing live-trading defaults.
- Added a React run-detail surface for core basket status, drift, selected
  symbols, and decision rows.
- Added unit coverage for Shariah membership, inverse-volatility caps, and
  monthly/drift gates; added a paper-run integration test for Shariah NSE equity
  core decisions.
- Assumptions made: Core basket decisions are generated as paper-run artifacts
  in M32 and are not broker-routed orders; if fewer than 12 eligible candidates
  have fresh candle history, the basket remains smaller rather than violating
  caps or minimum notional rules; prior monthly rebalance state can be inferred
  from prior paper-run artifacts until a later durable allocation table exists.
- Mocks created: None.
- Mocks used: Existing unit-test fake LLM provider and fake Kite market-data
  provider for the paper-run integration test.

## M33: Active Sleeve Risk-Budgeted Allocation

### Goal

Add the portfolio manager brain between candidate signals and final executable
quantity for active paper trades.

### Implementation Changes

- Add `MoneyManager` or `PortfolioAllocationService` used by the paper run after
  strategy target selection and before final broker routing.
- Active sleeve initially maps:
  - `graph_aware_score_v1` -> active
  - `moving_average_crossover_v1` -> active fallback/baseline
- Sizing basis for BUY/increase decisions:
  - start from proposal stop-loss distance
  - calculate allowed trade risk
  - dampen or cap by realized volatility
  - cap by stock exposure, sleeve capacity, cash buffer, total open trade risk,
    open positions, sector, and graph concentration
  - floor final quantity to whole shares
- Candidate score:
  - strategy score
  - TraderAgent confidence
  - liquidity score
  - volatility score
  - sector/graph diversification score
  - recent sleeve performance when available
- Score bands:
  - below 60: reject new entry
  - 60-75: half normal risk
  - 75-85: normal risk
  - 85+: strong risk, capped at 0.75% NAV
- Trade-risk defaults on INR 10,00,000 NAV:
  - normal active trade: 0.50% NAV
  - strong active trade: 0.75% NAV
  - absolute max single-trade risk: 1.00% NAV
  - total open trade risk: 5.00% NAV
- Persist allocation rationale in decision payloads:
  - requested notional
  - approved notional
  - approved quantity
  - allowed risk INR
  - estimated risk INR
  - volatility used
  - binding constraint
  - sleeve and strategy name

### Test Plan

- Unit-test each sizing cap independently.
- Unit-test stop-loss missing or invalid price rejects new BUY but does not
  block `REDUCE` or `EXIT`.
- Unit-test volatile stocks receive smaller size than lower-volatility stocks
  with equal signal score.
- Integration-test graph-aware paper run produces allocation metadata and
  reduced sizes when caps bind.
- Run `make test`, `make lint`, and targeted paper-run tests.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### Completion Summary

- Status: Completed on 2026-06-02.
- Added `PortfolioAllocationService` for active-sleeve paper BUY/increase
  proposals mapped from `graph_aware_score_v1` and
  `moving_average_crossover_v1`.
- Added active candidate scoring from strategy score, TraderAgent confidence,
  liquidity, realized volatility, sector/graph diversification, and neutral
  recent sleeve performance when no durable sleeve history exists.
- Added score-band risk budgets, stop-loss-distance sizing, volatility
  damping, whole-share flooring, and caps for stock exposure, sleeve capacity,
  cash buffer, total open trade risk, open positions, sector, and graph
  concentration.
- Wired money-management-enabled paper runs to resize or reject active BUY
  proposals before risk review while leaving HOLD, REDUCE, and EXIT lifecycle
  actions broker-safe and unblocked by new-risk sizing.
- Persisted allocation rationale through trader proposal, risk review, final
  decision, and per-symbol paper-run artifacts, including requested/approved
  notional, approved quantity, allowed/estimated risk, volatility, binding
  constraint, sleeve, and strategy.
- Added focused unit coverage for each active sizing cap, invalid stop-loss
  behavior, and volatile-vs-lower-volatility sizing; added graph-aware paper-run
  integration coverage for allocation metadata and cap-driven size reduction.
- Assumptions made: After-close active proposals expose stop-loss distance as
  `stop_loss_pct`, so M33 sizes from percentage distance rather than a separate
  stop-loss price; existing open paper positions without durable allocation
  records are treated as active unless they are configured core symbols; legacy
  open-position risk is estimated with the existing 6% stop-risk default; recent
  sleeve performance is neutral until a later milestone adds durable sleeve
  performance history.
- Mocks created: None.
- Mocks used: Existing unit-test fake LLM provider and fake Kite market-data
  provider for paper-run integration tests.

## M34: Diversifying And Experimental Sleeves

### Goal

Introduce strategy-level capital allocation and drawdown governors across
active, diversifying, and experimental sleeves.

### Implementation Changes

- Map strategies through config, not hard-coded names.
- Candidate initial mapping:
  - `graph_aware_score_v1` -> active
  - `blended_score_v1` -> diversifying after backtest validation
  - explicit experimental configs -> experimental
- Track per-sleeve:
  - starting NAV estimate
  - current exposure
  - realized/unrealized PnL
  - drawdown
  - open positions
  - open trade risk
  - turnover
- Governors:
  - portfolio drawdown over 3%: reduce new position sizes by 25%
  - portfolio drawdown over 5%: reduce new position sizes by 50%
  - portfolio drawdown over 8%: stop experimental new entries
  - portfolio drawdown over 10%: freeze new BUY decisions; allow exits only
  - sleeve drawdown over configured limit: reduce or freeze new entries for
    that sleeve
- Do not implement Kelly sizing yet. Add placeholders and metrics needed for a
  later fractional-Kelly milestone after enough paper-trade history exists.

### Test Plan

- Unit-test strategy-to-sleeve mapping.
- Unit-test sleeve drawdown and portfolio drawdown governors.
- Unit-test experimental sleeve risk cap.
- Unit-test exits remain routable during freezes.
- API/UI tests verify sleeve status and governor reasons.
- Run `make test`, `make lint`, and `make test-ui`.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### Completion Summary

- Status: Completed on 2026-06-02.
- Reworked `PortfolioAllocationService` from hard-coded active strategy names
  to config-driven strategy-to-sleeve routing for active, diversifying, and
  experimental allocation sleeves.
- Added sleeve runtime snapshots carrying starting NAV estimate, current
  exposure, realized/unrealized PnL, drawdown, open positions, open trade risk,
  and turnover, with paper runs feeding best-effort current exposure snapshots.
- Added portfolio drawdown governors: 3% caution reduces new BUY sizing by
  25%, 5% defensive reduces by 50%, 8% stops experimental new entries, and
  10% freezes new BUY decisions while leaving lifecycle exits routable.
- Added configurable sleeve drawdown reduce/freeze thresholds and an
  experimental new-entry trade-risk cap; allocation decisions now include
  governor scale, portfolio/sleeve drawdown, and governor reasons.
- Expanded money-management API metadata with initial sleeve status,
  governor reason placeholders, and deferred fractional-Kelly readiness fields
  without adding Kelly sizing.
- Added focused unit/API coverage for strategy mapping, portfolio and sleeve
  drawdown governors, experimental risk caps, exit routing during freezes, and
  UI aggregate money-management governor metadata.
- Assumptions made: Durable sleeve PnL/turnover history is not available yet,
  so paper runs estimate sleeve starting NAV from current NAV and configured
  target weights; existing non-core open positions are attributed to the active
  sleeve until durable allocation records can label each position by sleeve;
  experimental strategies are identified by explicit policy mappings into the
  `experimental_models` sleeve.
- Mocks created: None.
- Mocks used: Existing FastAPI/TestClient temporary database fixtures and
  existing unit-test paper allocation fixtures.

## M35: Allocation Dashboard And Operator Workflow

### Goal

Make allocation decisions understandable in the primary React dashboard and
operator docs.

### Implementation Changes

- Update `/ui/overview`, `/ui/risk`, `/ui/portfolio`, and decision trail payloads
  with allocation fields.
- React dashboard additions:
  - sleeve allocation summary
  - core basket composition and drift
  - cash buffer and undeployed capacity
  - open risk used vs limit
  - latest allocation decisions with binding constraints
  - drawdown governor state
  - per-position sleeve/strategy labels
- Update `docs/TAURUS_USAGE_GUIDE.md` with:
  - how to run Shariah-only paper loop
  - how to enable money management
  - how to read sleeve utilization and allocation reductions
  - how to inspect rejected candidates
- Update `docs/TAURUS_COMMANDS.md` with new commands or env vars.

### Test Plan

- UI unit tests for allocation panels and empty states.
- API aggregate tests for allocation payloads.
- `make test`
- `make test-ui`
- `make build-ui`
- Optional local API/UI smoke if implementation starts servers.

### Completion Summary Requirements

At completion, add assumptions made, mocks created, and mocks used.

### Completion Summary

- Status: Completed on 2026-06-02.
- Added read-only allocation payloads to `/ui/overview`, `/ui/risk`,
  `/ui/portfolio`, and symbol decision trails, including sleeve utilization,
  core basket drift, cash buffer, undeployed capacity, open risk used versus
  limit, latest allocation decisions, and drawdown-governor state.
- Added React allocation panels for Overview, Risk, Portfolio, and decision
  trails, plus per-position sleeve/strategy labels and binding-constraint
  visibility for allocation reductions or rejections.
- Updated operator docs with the Shariah-only `paper-loop-kite` path, the
  `TAURUS_MONEY_MANAGEMENT_ENABLED=true` workflow, and dashboard/API inspection
  steps for sleeve utilization, allocation reductions, and rejected candidates.
- Added focused API and UI coverage for enabled/disabled allocation payloads,
  decision trail allocation decisions, allocation panels, and empty states.
- Assumptions made: Position sleeve/strategy labels can be derived from the
  latest stored allocation decision for a symbol, with a core Shariah fallback
  for configured core symbols, until durable per-position sleeve attribution is
  persisted; open-risk usage is a read-only dashboard estimate from recent
  stored allocation decisions, not a new risk engine source of truth.
- Mocks created: None.
- Mocks used: Existing FastAPI/TestClient temporary database fixtures, existing
  fake LLM provider, existing fake Kite market-data provider, and existing
  React fetch fixtures in unit tests.

## Deferred Follow-Ups

- Fractional Kelly sizing after at least 300-500 clean trades per strategy.
- Correlation-aware optimizer beyond current graph concentration checks.
- Tax-lot-aware selling and cost-aware rebalance optimization.
- Live broker execution. This requires a separate approved milestone and a
  fresh compliance review.

## References

- CFA Institute, Active Equity Investing: Portfolio Construction:
  https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/active-equity-investing-portfolio-construction
- Investor.gov, Asset Allocation and Diversification:
  https://www.investor.gov/introduction-investing/getting-started/asset-allocation
- Busseti, Ryu, Boyd, Risk-Constrained Kelly Gambling:
  https://arxiv.org/abs/1603.06183
- SEBI, Safer participation of retail investors in Algorithmic trading,
  February 04, 2025:
  https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
- SEBI, extension of implementation timeline, September 30, 2025:
  https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html
