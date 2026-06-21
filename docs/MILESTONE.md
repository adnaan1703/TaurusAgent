# Taurus Milestone Tracker

Last updated: 2026-06-22

This is the active tracker for Taurus milestone work. Keep it concise and keep
current operator detail in the usage and command docs.

## Active Sources

- `docs/TAURUS_USAGE_GUIDE.md`: current operator workflow and limitations.
- `docs/TAURUS_COMMANDS.md`: active command reference and project-local
  approval policy.
- `docs/TAURUS_MOCK_MIGRATION_STATUS.md`: current mock/simulation status.
- `docs/TAURUS_AGENT_ARCHITECTURE.md`: current agent pipeline and data flow.
- `docs/TAURUS_DATABASE_TABLES.md`: current Postgres table summary.
- `docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md`: completed M20 graph reference.
- `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md`: completed M44-M50 next-open
  AMO-style paper settlement work.
- `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md`: planned M56-M61 holistic
  portfolio rebalance, score precision, soft sleeve borrowing, executable core,
  proceeds netting, and regression work.
- `docs/agent_improvement_plans/LLM_AGENT_SYSTEM_PROMPTS_BACKLOG.md`: deferred
  prompt backlog for optional analyst upgrades.

Completed milestone implementation plans and Stitch UI reference assets were
removed during docs cleanup. Use Git history for detailed historical plans.

## Current State

- Taurus is paper-trading-first and local by default.
- Docker Postgres is the canonical database; runtime and tests reject SQLite
  URLs.
- Runtime market data is Kite-only.
- Runtime LLM providers are real providers only: LM Studio by default, with
  OpenAI and Gemini as explicit opt-ins.
- Paper loops record provider-reported LLM usage in run artifacts and always
  print a post-progress LLM usage summary with compact token counts.
- Execution routes only through local `PaperBroker` simulation.
- Manual EOD paper loops import latest daily candles, settle previous
  `PENDING_NEXT_OPEN` orders through the `PaperBroker` settlement engine, then
  analyze the new after-close state and queue new next-open paper orders.
- `make paper-loop-kite` is the canonical real-data profile. It runs
  full-universe analysis, graph-aware ranking, run-level allocation,
  risk/final decisions for analyzed symbols, and allocated-only paper routing.
- React is the primary local dashboard. Streamlit remains a fallback dashboard.
- Alerts default to mock delivery until Telegram is verified with local
  credentials.
- Graph and graph risk are disabled by config default but enabled by
  `make paper-loop-kite` after readiness checks. Neo4j remains optional and
  disposable.
- M51 first-class profile catalog work is complete: `taurus_profiles` stores
  profile records, `TAURUS_PROFILE_ID` is the preferred profile setting, and
  `TAURUS_PAPER_PORTFOLIO_ID` remains a legacy alias.
- M52 run/artifact lineage work is complete: `paper_runs`, analyst reports,
  debate reports, risk reviews, and final decisions now carry profile identity
  alongside the existing profile-aware trader proposals.
- M53 corpus-aware paper execution isolation is complete: selected profiles now
  drive paper starting cash, account/position/fill/settlement state, position
  monitoring scope, and operator paper-loop profile selection.
- M54 profile API and dashboard selection work is complete: profile CRUD APIs,
  profile-scoped read filters, active-profile UI response metadata, and the
  read-only React profile selector now scope dashboard views by selected active
  profile.
- M55 multi-profile regression and cleanup is complete: deterministic
  regression covers two-profile pending/fill/settlement/P&L isolation,
  profile-scoped API/dashboard payloads, stale profile filters, profile smoke
  checks, final operator docs, and approval-rules cleanup.
- M56 score semantics and allocation precision work is complete. M57 portfolio
  rebalance plan schema and dry-run artifact work is the next planned
  milestone.

## Standing Safety Rules

- `LIVE_TRADING_ENABLED=false` remains the default.
- `BROKER_PROVIDER=paper` remains the default.
- Kite support is data-only; execution continues through `PaperBroker`.
- Do not add live broker order routing without a new explicit approved
  milestone.
- Do not commit API keys, broker credentials, Telegram tokens, Kite tokens, or
  user CSV exports.
- Runtime LLM-backed components must use `build_llm_provider(settings)` and the
  default provider must remain LM Studio unless an explicit hosted provider is
  configured.
- Money-management and portfolio-construction work must remain long-only,
  equity-only, and restricted to enabled symbols in
  `configs/market_data/nifty_500_shariah.yaml` unless a later explicit
  milestone changes the universe policy.
- Any plan that changes API payloads or decision artifacts must include matching
  React dashboard updates in the same milestone.

## Completed Milestone Summary

| Scope | Status | Result |
|---|---|---|
| M0-M13 | Done | Core FastAPI, database, backtesting, analyst reports, debate, trader proposal, risk, final approval, paper broker, alerts, replay, backup/restore, and paper-trading MVP. |
| M16 | Done | React run-loop observability dashboard became the primary local UI. |
| M17 | Done | Zerodha Kite market-data provider, data-only. |
| M18-M19 | Done | HalalStock compliance sync, halal NSE universe export, Shariah dashboard, and paper-run universe provenance. |
| M20.0-M20.10 | Done | Graph intelligence foundation, importer, API, React views, optional Neo4j projection, graph stats, graph analyst, graph risk, graph metrics, and graph-aware backtesting. |
| M21-M30 | Done | Docker Postgres-only persistence, real LLM provider migration, Kite-only runtime market data, graph-enabled Kite paper loop, LLM-backed research/trader/final explanation flow, portfolio continuity, and market-hours position monitoring. |
| M31-M35.1 | Done | Paper money-management policy, core Shariah basket, active/diversifying/experimental sleeve allocation, allocation dashboard, and static policy shortcut cleanup. |
| Ops progress UI | Done | Rich/plain stderr progress for Kite candle import, graph stats computation, and graph-enabled Kite paper loops. |
| Ops LLM usage summary | Done | Added provider-reported LLM usage capture, paper-run artifacts, and mandatory post-progress paper-loop terminal summaries with compact token formatting. |
| M36-M43 | Done | Full-universe ranking, decomposed paper loop, run-level dynamic allocation, all-symbol risk/final decisions, allocation observability, replay/backtest/command alignment, and default full-universe Kite paper loop enablement. |
| M44-M50 plan document | Done | Created the flat next-open AMO-style paper settlement plan covering baseline tests, pending order schema, pending EOD order creation, settlement, EOD loop integration, dashboard/replay/metrics polish, and final cleanup. Implementation milestones are complete through M50. |
| M44 | Done | Added xfail-free baseline unit tests for next-open AMO-style paper settlement. The baseline tests defined target behavior later implemented across M45-M50. |
| M45 | Done | Added pending next-open paper order schema metadata, repository insert/list/replace helpers, API aggregate pending-stage handling, React queued status display, and operator docs. PaperBroker after-close pending creation followed in M46. |
| M46 | Done | After-close paper decisions now create `PENDING_NEXT_OPEN` orders with no fills or cash/position mutation, while market-hours monitor and explicit immediate routing continue to fill immediately. Settlement followed in M47. |
| M47 | Done | Added the standalone PaperBroker next-open settlement engine, summary artifacts, deterministic one-fill AMO settlement, cash/position/P&L rebuilding, partial fill/rejection handling, and focused tests. EOD loop integration followed in M48. |
| M48 | Done | Integrated next-open settlement into the manual EOD paper loop before strategy analysis/allocation, exposed top-level and symbol-level settlement artifacts, preserved terminal settlement state during same-run replacements, and documented operator semantics. Dashboard/replay/metrics polish followed in M49. |
| M49 | Done | Polished React and Streamlit order displays, run settlement summaries/details, decision replay pending/settled semantics, paper-order status metrics coverage, terminal settlement alert tests, and operator docs for queued and settled next-open paper orders. |
| M50 | Done | Completed the end-to-end regression and cleanup pass for the M44-M50 next-open AMO-style paper settlement sequence. The deterministic operator smoke path covers BUY queue, next-open BUY settlement, EXIT queue, following-open EXIT settlement, realized P&L, empty final positions, and API inspection for `/paper/orders`, `/paper/fills`, `/paper/positions`, `/paper/account`, `/ui/overview`, and `/ui/runs/{run_id}`. |
| M51-M55 plan document | Done | Created the flat multi-profile paper trading plan covering profile catalog/config, run and agent profile lineage, corpus-aware execution isolation, profile APIs/dashboard selector, and final regression/docs. Implementation milestones are complete through M55. |
| M51 | Done | Added the persistent Taurus profile catalog, default `local-paper` seed, preferred `TAURUS_PROFILE_ID` setting alias, legacy portfolio alias compatibility guard, profile lifecycle repository/service helpers, CLI/Make profile management commands, corpus update guard, docs, and focused tests. Runtime profile isolation remains deferred to M52-M55. |
| M52 | Done | Added profile lineage to paper runs, profile-aware run IDs, persisted analyst/debate/risk/final artifact profile identity, repository profile filters, idempotent lineage migrations, local-paper legacy defaults, and focused tests. Corpus-aware paper execution remains deferred to M53. |
| M53 | Done | Added runtime profile resolution for paper services, profile corpus-backed paper cash/account rebuilds, profile-scoped next-open settlement and position monitoring, profile-aware run/operator artifacts, Make command profile selection, docs, and focused regression tests. Dashboard profile selection remains deferred to M54. |
| M54 | Done | Added profile CRUD APIs, profile-scoped query parameters for run/paper/research/risk/UI read endpoints, active-profile UI metadata, a URL/local-storage-backed read-only React profile selector, profile-aware query keys/links, and focused API/UI tests. M55 final regression is complete. |
| M55 | Done | Added deterministic two-profile regression for pending orders, settled fills, realized/unrealized P&L, dashboard/API scoping, stale profile filters, and profile smoke checks; API/Vite local smoke returned 200, while visual browser automation was unavailable in this session; finalized operator docs and milestone cleanup for the M51-M55 sequence. |
| Ops LM Studio reasoning fallback | Done | Added a narrow LM Studio compatibility fallback that uses non-empty `message.reasoning_content` only when `message.content` is empty, while keeping existing parser and schema validation as the contract authority. |
| M56-M61 plan document | Done | Created the flat portfolio rebalance plan covering score semantics, dry-run portfolio-plan artifacts, soft sleeve borrowing, executable core routing, same-run proceeds netting, execution buffers, UI/replay observability, and final regression. Implementation is complete through M56; M57 remains planned. |
| M56 | Done | Added score metadata for analyst reports, raw technical/graph score lineage, shared calibrated allocation score semantics, trader target cap metadata, allocation candidate score visibility in API/UI selection rows, focused regressions, and architecture docs. Portfolio-level rebalance planning, executable core basket orders, sleeve borrowing, and same-run proceeds netting remain for M57-M61. |

### M56-M61 Plan Document Completion Summary

- Assumptions made: The portfolio rebalance upgrade should stay paper-only,
  long-only, equity-only, and restricted to the existing Shariah-enabled
  universe; raw, calibrated, bounded, and allocation scores should be separate
  concepts; active strategy may borrow configured idle non-cash sleeve capacity
  but not the hard 5% cash buffer; same-run REDUCE/EXIT proceeds should be
  spendable only after an 80% haircut; BUY sizing should reserve 5% cash and
  use a 5% price buffer; implementation should run as flat milestones M56
  through M61.
- Mocks created: None.
- Mocks used: None.

### M56 Completion Summary

- Assumptions made: M56 should preserve the bounded `AnalystReport.score`
  compatibility contract while adding optional score metadata; missing strategy
  scores should keep the neutral allocation component of `50.0000`; raw strategy
  score remains visible as `strategy_score` for legacy API/UI consumers while
  `candidate_score` is exposed as the calibrated allocation score; trader target
  sizing metadata should document caps without changing paper execution
  behavior; portfolio-level rebalance planning, executable core orders, sleeve
  borrowing, and same-run proceeds netting remain out of scope for M56.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, deterministic market-data fixtures,
  graph analyst fixtures, and existing React query/fetch test fixtures.

### M51-M55 Plan Document Completion Summary

- Assumptions made: Multi-profile v1 should use logical isolation inside the
  existing local Taurus Postgres/API/UI stack; `portfolio_id` remains the
  persisted storage boundary while new user-facing APIs use profile language;
  one profile runs per paper-loop invocation; physical database/stack isolation,
  dashboard CRUD, all-active-profile scheduling, and deposits/withdrawals remain
  deferred.
- Mocks created: None.
- Mocks used: None.

### M51 Completion Summary

- Assumptions made: M51 should preserve existing paper-loop behavior while
  adding the profile catalog and settings alias; the default profile remains
  `local-paper` with INR 10,000 starting corpus; queued orders, fills, nonzero
  positions, and non-initial account snapshots all count as trading activity
  that blocks starting-corpus edits until a later capital-events milestone.
- Mocks created: None.
- Mocks used: None.

### M52 Completion Summary

- Assumptions made: M52 should persist and filter profile lineage without
  changing `/runs` default breadth or introducing dashboard profile selection;
  `portfolio_id` remains the stored column name while repository filters expose
  `profile_id`; legacy rows without payload-level profile identity should load
  as `local-paper`.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing `FakeKiteMarketDataProvider`,
  deterministic test market-data fixtures, and existing paper-run integration
  fixtures.

### M53 Completion Summary

- assumptions made: Profile-backed paper execution should fail fast when the
  selected profile is missing or archived; `TAURUS_INITIAL_CAPITAL_INR` remains
  a legacy fallback only outside selected-profile paper execution; one selected
  profile runs per paper-loop/monitor invocation; display names should not be
  included in run, LLM usage, or operator summaries.
- mocks created: None.
- mocks used: Existing `FakeLLMProvider`, existing `FakeKiteMarketDataProvider`,
  deterministic market-data fixtures, existing mock final-approval helpers,
  focused manual daily-candle fixtures, and FastAPI `TestClient`.

### M54 Completion Summary

- assumptions made: Omitted profile filters should default to the effective
  settings profile; archived or missing profiles should fail clearly instead of
  falling back to all profiles; run-detail links should derive profile identity
  from the stored run while rejecting explicitly mismatched `profile_id`
  requests; Graph and Shariah views remain shared platform-level views.
- mocks created: None.
- mocks used: Existing `FakeLLMProvider`, existing `FakeKiteMarketDataProvider`,
  deterministic market-data fixtures, FastAPI `TestClient`, existing React
  fetch stubs, and legacy mock paper-once smoke helpers with explicitly updated
  test profile corpus.

### M55 Completion Summary

- Assumptions made: Multi-profile v1 remains logical isolation inside one local
  Postgres/API/UI stack; `portfolio_id` remains the persisted profile boundary;
  profile smoke can create or reuse a deterministic `smoke-profile`; the React
  selector remains read-only; physical database/stack isolation,
  per-profile credentials, dashboard CRUD, all-profile scheduling, and
  deposits/withdrawals remain deferred.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic market-data fixtures, forced
  trader-action monkeypatches in the M55 regression, FastAPI `TestClient`, and
  existing React fetch stubs.

### M44-M50 Plan Document Completion Summary

- Assumptions made: The next-open AMO settlement work should be executed as
  flat milestones M44 through M50, each in a separate thread; morning 9:15
  settlement remains deferred; Kite remains data-only.
- Mocks created: None.
- Mocks used: None.

### M44 Completion Summary

- Assumptions made: Default mock final approval creates after-close BUY
  decisions; existing `TraderProposal.evaluation_mode` is the future routing
  boundary between after-close and market-hours monitor decisions; M44 should
  not intentionally change runtime paper execution behavior.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, mock final approval helpers, and
  deterministic test market-data fixtures.

### M45 Completion Summary

- Assumptions made: Pending next-open metadata belongs in the existing
  `paper_orders.payload` JSON plus the string `status` column; M45 should not
  change `PaperBroker` or `ExecutionRouter` after-close routing behavior; the
  existing UI `running` stage status is the right in-progress representation for
  queued next-open orders.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing `FakeKiteMarketDataProvider`,
  mock final approval helpers, and deterministic test market-data fixtures.

### M46 Completion Summary

- Assumptions made: `TraderProposal.evaluation_mode` is the primary routing
  boundary for ad hoc decisions, `PaperRunService.run_after_market_close`
  should explicitly route EOD runs to `next_open`, and `run_after_market_close=False`
  remains the immediate-routing path for tests and non-EOD paper runs; pending
  orders should store a current account/position snapshot for the run without
  changing cash, positions, or fills.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing `FakeKiteMarketDataProvider`,
  mock final approval helpers, mock news provider fixtures, and deterministic
  test market-data fixtures.

### M47 Completion Summary

- Assumptions made: M47 should expose settlement as a standalone
  `PaperBroker` method and should not integrate it into the EOD paper loop;
  settled order rows should preserve their original order/run provenance while
  settlement fills and account snapshots use the supplied current run ID;
  pending orders with missing `signal_trade_date` should be skipped without
  alerts; orders with no newer candle should remain pending without repeat
  alerts.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, mock final approval helpers, existing
  deterministic market-data fixtures, and focused manual daily candle fixtures
  in unit tests.

### M48 Completion Summary

- Assumptions made: Manual EOD settlement should run after Kite daily-candle
  import and before any strategy, allocation, risk, final decision, or new
  pending-order creation; requested symbols, open-position symbols, and
  pending-order symbols all belong in the run scope; queued orders created by
  the current EOD run must not affect cash or positions until a later
  settlement; terminal settlement orders/fills/account state should survive
  same-run repository replacement cleanup.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures,
  forced-trader-action monkeypatches in paper-run integration tests, and
  existing broker settlement test fixtures.

### M49 Completion Summary

- Assumptions made: Settlement counts belong in the existing run summary/API
  payload rather than a new dashboard page; the existing
  `taurus_trading_artifacts_total` paper-order status gauge is the right
  Prometheus pattern for `PENDING_NEXT_OPEN`; no new settlement metric should
  be added until there is a broader settlement metrics pattern; React should
  tolerate older API payloads that do not yet include `settlement_summary`;
  Kite remains data-only and all fills remain simulated.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, and the
  existing `MockAlertAdapter`.

### M50 Completion Summary

- Assumptions made: Live Kite credentials are unavailable in milestone
  regression, so the operator-level smoke scenario should remain deterministic
  through the existing test database and fake Kite daily-candle provider; after
  a later settlement, `/ui/runs/{run_id}` symbol rows should show the current
  terminal order status while raw run artifacts preserve the status originally
  recorded during that run; no approval-rule migration is needed when the
  global rules file has no Taurus-specific entries after
  `# END MY CUSTOM ADDITION`.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, forced trader-action monkeypatches in the
  paper-run integration smoke test, deterministic daily-candle fixtures, and
  FastAPI `TestClient` API inspection against the test database.

### Ops LLM Usage Summary Completion Summary

- Assumptions made: Token counts should rely only on provider-returned usage
  metadata; unavailable token fields should remain `n/a`; the mandatory
  human-readable summary belongs after progress closes and should not break
  optional JSON automation output.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, extended with deterministic usage
  records for paper-run tests.

### Ops LM Studio Reasoning Fallback Completion Summary

- Assumptions made: The compatibility fallback applies only to LM Studio
  OpenAI-compatible responses; non-empty `message.content` remains authoritative;
  existing parser and schema validation functions remain the only contract
  authority for analyst, research, trader, and final-decision outputs.
- Mocks created: None.
- Mocks used: Monkeypatched LM Studio HTTP responses in
  `tests/unit/test_llm_provider.py`.

## Completed Next-Open AMO Settlement Sequence

These milestones were executed in order, each in separate milestone work, and
documented with the standard completion summary.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 26 | M44 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Add baseline tests and tracker setup for next-open AMO-style paper settlement. |
| 27 | M45 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Add pending next-open order schema, repository support, API status handling, and UI status support. |
| 28 | M46 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Change after-close paper decisions to create `PENDING_NEXT_OPEN` orders while preserving immediate market-hours monitor routing. |
| 29 | M47 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Settle pending orders at the first newer daily candle open and calculate fills, cash, positions, and P&L. |
| 30 | M48 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Integrate settlement into the manual EOD paper loop before new analysis and allocation. |
| 31 | M49 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Polish dashboard, replay, metrics, alerts, and operator docs for pending and settled orders. |
| 32 | M50 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Run end-to-end regression, verify operator workflow, and close the milestone sequence. |

## Completed Multi-Profile Paper Trading Sequence

These milestones were executed in order as separate milestone work and
documented with the standard completion summary.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 33 | M51 | Done | `docs/TAURUS_MULTI_PROFILE_PLAN.md` | Add the profile catalog, settings alias, default profile seed, and CLI/Make profile creation workflow. |
| 34 | M52 | Done | `docs/TAURUS_MULTI_PROFILE_PLAN.md` | Add profile lineage to paper runs and run-derived agent artifacts so history and decisions can be profile-scoped. |
| 35 | M53 | Done | `docs/TAURUS_MULTI_PROFILE_PLAN.md` | Make paper execution, settlement, position monitoring, and corpus/P&L state isolated by selected profile. |
| 36 | M54 | Done | `docs/TAURUS_MULTI_PROFILE_PLAN.md` | Add profile APIs, profile filters, and a read-only React profile selector for scoped dashboard views. |
| 37 | M55 | Done | `docs/TAURUS_MULTI_PROFILE_PLAN.md` | Complete multi-profile regression, browser/API smoke, operator docs, and milestone cleanup. |

## Planned Portfolio Rebalance Sequence

These milestones must be executed in order as separate milestone work. When a
future session starts one milestone, it must stop after that milestone is
implemented, verified, cleaned up, and documented.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 38 | M56 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add score semantics and allocation precision plumbing so raw, calibrated, bounded, and allocation scores remain distinct. |
| 39 | M57 | Planned | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add a dry-run portfolio rebalance plan artifact, API/UI/replay visibility, and legacy-safe serialization. |
| 40 | M58 | Planned | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add soft sleeve capacity rules and convert core Shariah basket decisions into executable rebalance candidates. |
| 41 | M59 | Planned | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Make holistic BUY allocation and executable core routing flow through planner-linked allocation, risk, final, and paper queueing. |
| 42 | M60 | Planned | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add threshold trims/exits, 80% same-run proceeds netting, 5% cash/price buffers, and sell-first next-open queueing. |
| 43 | M61 | Planned | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Run end-to-end regression, finalize operator docs, clean compatibility scaffolding, and close the sequence. |

## Deferred Work

- Real news provider and production-grade news/sentiment analysts.
- Fundamentals production hardening after real Screener CSV validation.
- Optional LLM-backed risk persona agents. `RiskEngine` must remain
  deterministic.
- Broker-calibrated charges, slippage, and fill assumptions.
- Telegram alert verification with local credentials.
- Dashboard/API auth before use beyond a trusted local machine.
- Live broker order routing. This remains out of scope.

## Completion Reporting

Every completed milestone summary must explicitly list:

- Assumptions made
- Mocks created
- Mocks used

If any category is empty, write `None`.

At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules`.
Entries after the user's `# END MY CUSTOM ADDITION` marker are accidental global
approvals. Move Taurus-specific approved prefixes into
`.codex/rules/default.rules` if missing, document them in
`docs/TAURUS_COMMANDS.md`, and remove them from the global file. Do not copy
unrelated global approvals.

## Milestone Planning Rules

- Use flat milestone IDs such as `M44`, `M45`, and `M46` for future planned
  work. Do not create new submilestone IDs such as `M44.1` unless the user
  explicitly requests submilestones.
- When a plan naturally has several execution chunks, make each chunk a proper
  milestone and add it to a tracker table in this file.
- Every new plan document must be listed in `Active Sources` while it is
  relevant.
- Planning work itself must be recorded in `Completed Milestone Summary` when a
  plan document is created, clearly distinguishing completed planning from
  planned implementation.
- The planning completion summary must list assumptions made, mocks created,
  and mocks used. Use `None` for empty categories.
- Planned milestone sequence tables must use the established tracker format:
  `Order`, `Milestone`, `Status`, `Plan`, and `Purpose`.
- Use `Planned`, `In Progress`, `Done`, or `Deferred` status values
  consistently.
- Keep the tracker concise. Detailed implementation instructions belong in the
  linked plan document.

## Maintenance Rules

- Update this file when a milestone starts, completes, or is intentionally
  deferred.
- Keep command changes in `docs/TAURUS_COMMANDS.md`.
- Keep operator workflow changes in `docs/TAURUS_USAGE_GUIDE.md`.
- Keep implementation plans out of active docs after their milestones complete;
  Git history is the archive.
