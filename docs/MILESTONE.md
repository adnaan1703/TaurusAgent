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
- `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md`: completed M56-M61 holistic
  portfolio rebalance, score precision, soft sleeve borrowing, executable core,
  proceeds netting, and regression work.
- `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md`: completed M62-M65 graph provenance,
  promotion, confidence-weighting, API/UI, and regression work.
- `docs/TAURUS_TECHNICAL_SIGNAL_SERVICE_PLAN.md`: planned M66-M69 shared
  `TechnicalSignalService` refactor and regression sequence.
- `docs/TAURUS_TECHNICAL_SIGNAL_SERVICE_HANDOFF.md`: next-session handoff for
  the planned M66-M69 technical signal service sequence.
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
- M56 score semantics and allocation precision work is complete.
- M57 portfolio rebalance plan schema and dry-run artifact work is complete.
- M58 soft sleeve capacity and executable core candidate modeling is complete.
- M59 portfolio-plan-backed BUY allocation and executable core routing is
  complete; the planner remains default-on when money management is enabled,
  with `TAURUS_PORTFOLIO_PLAN_ALLOCATION_ENABLED=false` retained as an operator
  compatibility fallback.
- M60 threshold trims, same-run proceeds netting, and execution buffer is
  complete.
- M61 final end-to-end regression, operator-doc closeout, compatibility review,
  and cleanup is complete. The completed M56-M61 path keeps Taurus paper-only
  and Kite data-only while proving planner-linked active BUYs, core BUYs,
  threshold EXIT/REDUCE rows, 80% same-run proceeds haircut, 5% cash reserve,
  5% BUY buffer, protected cash-buffer capacity, soft non-cash sleeve borrowing,
  sell-first next-open queueing, API/replay/dashboard visibility, and next-run
  settlement compatibility.
- M62 graph provenance data-contract work is complete: `graph_edges` now stores
  required `provenance_type`, TaurusData edge-like CSV imports require that
  field, reviewed statuses survive re-import, and API/React/Neo4j graph edge
  surfaces expose provenance instead of edge-level `inferred`.
- M63 promotion lifecycle cleanup is complete: the legacy min-edge-confidence
  setting has been removed from config, `.env.example`, tests, and docs;
  auto-promotion is gated by the opt-in flag plus statistical thresholds only;
  low-confidence inferred candidate fixtures can auto-promote when stats pass
  and can be manually promoted without stats.
- M64 confidence-free graph scoring is complete: graph analyst and graph
  backtest contribution weights no longer use imported edge confidence or
  candidate status multipliers; contribution metadata now keeps
  `provenance_type` and raw edge confidence for audit only; active edges with
  different CSV confidence values score identically; inferred candidates remain
  excluded from graph analyst, graph backtest, and graph risk until promoted.
  M65 final regression/docs closeout is complete: the bundled TaurusData V2
  edge-like CSVs import with `provenance_type`, segment/product CSVs preserve
  their non-edge `inferred` columns, operator/developer docs distinguish
  provenance, confidence metadata, evidence basis, and review status, and stale
  confidence-gate/scoring language has been removed.
- M66 baseline technical signal characterization is complete: focused tests
  now pin current `TechnicalAnalystAgent` backtest-signal override,
  feature-formula scoring, report clamping, confidence fallback, key points,
  and source IDs, plus current `GraphAwareScoreStrategy` SMA spread and
  weighted graph-aware combined score behavior.
- M67 `TechnicalSignalService` foundation is complete: the new DB-free service
  exposes immutable input/result types, behavior-preserving analyst-rule and
  SMA-spread scoring profiles, package exports, and focused parity tests
  without wiring runtime consumers yet.

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
| M56-M61 plan document | Done | Created and completed the flat portfolio rebalance plan covering score semantics, dry-run portfolio-plan artifacts, soft sleeve borrowing, executable core routing, same-run proceeds netting, execution buffers, UI/replay observability, and final regression. |
| M56 | Done | Added score metadata for analyst reports, raw technical/graph score lineage, shared calibrated allocation score semantics, trader target cap metadata, allocation candidate score visibility in API/UI selection rows, focused regressions, and architecture docs. Portfolio-level rebalance planning, executable core basket orders, sleeve borrowing, and same-run proceeds netting remain for M57-M61. |
| M57 | Done | Added a typed dry-run portfolio rebalance plan artifact with position, candidate, planned-trade, cash-budget, sleeve-budget, and constraint rows; persisted it on paper runs; exposed it through replay, API aggregate payloads, and React allocation/run-detail panels; preserved legacy runs without plan artifacts; and kept executable allocation/order behavior unchanged. Soft sleeve borrowing, executable core routing, and same-run proceeds netting remain for M58-M61. |
| M58 | Done | Added explicit rebalance-capacity policy rules, soft sleeve borrowing visibility in the dry-run plan, protected/borrowable/borrowed sleeve budget rows, typed core Shariah basket plan candidates with score/rejection evidence, API/UI/replay visibility, focused regressions, and money-management/architecture docs. Executable core routing, holistic BUY allocation, and same-run proceeds netting remain for M59-M61. |
| M59 | Done | Added default-on portfolio-plan-backed BUY allocation with a settings-controlled legacy allocator path, planner-linked allocation decisions and ledger rows, executable core BUY proposal/debate generation, soft-borrow capacity handoff into sizing, API/UI/replay visibility for planner source/rank/capacity, focused regressions, and operator/architecture docs. Threshold REDUCE/EXIT generation, same-run proceeds netting, and sell-first queueing remain for M60-M61. |
| M60 | Done | Added threshold-driven REDUCE/EXIT plan candidates and generated sell-side proposals, net same-run sell proceeds with the configured 80% haircut before BUY sizing, preserved the 5% NAV cash reserve and 5% BUY price buffer, routed accepted sell-side paper orders before BUYs with pending affordability credit, exposed funding/proceeds metadata in API/UI/replay artifacts, and updated operator/architecture docs. |
| M61 | Done | Added deterministic end-to-end portfolio rebalance regression covering seeded account state, raw-score ordering, core BUY routing, threshold EXIT routing, 80% same-run proceeds haircut, 5% cash reserve, 5% BUY buffer, protected cash-buffer capacity, soft sleeve borrowing, API/replay/dashboard visibility, sell-first pending queueing, and next-run settlement compatibility; refreshed operator/current-state docs and retained the M59 legacy allocator flag as an explicit troubleshooting fallback. |
| M62-M65 plan document | Done | Created the flat graph provenance plan covering TaurusData V2 `provenance_type` ingestion, graph edge status/promotion, removal of confidence from graph behavior, API/UI/docs updates, and final regression. Implementation is complete through M65. |
| M62 | Done | Replaced edge-level `inferred` with required `provenance_type` across the graph edge ORM, idempotent migration, repository contract, TaurusData CSV importer, FastAPI graph responses, React graph UI/types/tests, and Neo4j projection; edge-like CSVs now require valid provenance, segment/product CSVs still map non-edge `inferred` booleans into provenance, and reviewed edge statuses remain authoritative on re-import. Confidence remains stored/exposed as audit metadata; graph scoring changes remain for M64. |
| M63 | Done | Removed the legacy min-edge-confidence setting from runtime config, `.env.example`, tests, and docs; graph auto-promotion now ignores imported edge confidence and relies on the opt-in flag plus sample-size, stability, residual-correlation, or lead-lag thresholds; manual graph review can promote low-confidence inferred candidates without stats while preserving provenance metadata. |
| M64 | Done | Removed raw edge confidence and candidate status multipliers from graph analyst and graph backtest contribution scoring, retained raw edge confidence/provenance as contribution audit metadata only, and added regressions proving active-edge score invariance across CSV confidence values plus candidate exclusion from graph analyst, graph backtests, and graph risk until promotion. |
| M65 | Done | Ran final graph provenance closeout against the bundled TaurusData V2 outputs, verified edge-like CSV headers and populated strength/provenance fields, refreshed operator/developer docs to distinguish `provenance_type`, confidence metadata, `evidence_type`, and review `status`, documented the profile-JSON-versus-flattened-CSV contract, and closed the M62-M65 sequence. |
| M66-M69 plan document | Done | Created the flat shared `TechnicalSignalService` plan covering baseline parity tests, service foundation, core analyst/graph-aware wiring, and final regression/docs. Implementation is complete through M67; M68-M69 remain planned. |
| M66 | Done | Added baseline characterization tests for current technical analyst and graph-aware strategy scoring, covering backtest signal override, feature formula output, report score clamping, confidence fallback, key points, source IDs, missing/valid SMA technical scores, and weighted graph-aware combined scoring. |
| M67 | Done | Added `TechnicalSignalService`, `TechnicalBacktestSignal`, and `TechnicalSignalResult` as DB-free shared technical-scoring foundations, exported them from `taurus_core.features`, and added focused parity tests for analyst-rule and SMA-spread behavior without runtime consumer wiring. |

## Planned Milestone Tracker

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 66 | M66 | Done | `docs/TAURUS_TECHNICAL_SIGNAL_SERVICE_PLAN.md` | Add baseline characterization tests for current technical analyst and graph-aware strategy scoring. |
| 67 | M67 | Done | `docs/TAURUS_TECHNICAL_SIGNAL_SERVICE_PLAN.md` | Add the DB-free shared `TechnicalSignalService` foundation without runtime wiring. |
| 68 | M68 | Planned | `docs/TAURUS_TECHNICAL_SIGNAL_SERVICE_PLAN.md` | Route `TechnicalAnalystAgent` and `GraphAwareScoreStrategy` through the shared service without behavior drift. |
| 69 | M69 | Planned | `docs/TAURUS_TECHNICAL_SIGNAL_SERVICE_PLAN.md` | Run final regression, refresh architecture/deep-dive docs for implemented behavior, and close the sequence. |

### M67 Completion Summary

- Assumptions made: M67 should introduce the shared service and exports only;
  `TechnicalAnalystAgent`, `GraphAwareScoreStrategy`, runtime artifact
  payloads, database schema, API contracts, React UI, strategy thresholds, and
  paper-run behavior remain unchanged until M68 wiring; the analyst-rule
  service accepts an optional symbol for the no-snapshot fallback wording
  because `FeatureSnapshot | None` alone cannot preserve the current symbolized
  fallback message.
- Mocks created: None.
- Mocks used: None.

### M66 Completion Summary

- Assumptions made: M66 should add characterization coverage only; production
  code, strategy formulas, ranking sort order, LLM prompts, allocation behavior,
  database schema, API contracts, and React UI remain unchanged; direct
  `_technical_score()` coverage is acceptable because the M68 plan requires
  that compatibility surface to remain stable for local callers and tests.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider` for deterministic analyst report
  output; migration-backed test database rows for feature snapshots and latest
  backtest signals; existing graph backtest signal fixtures.

### M66-M69 Plan Document Completion Summary

- Assumptions made: The first implementation sequence should preserve current
  trading behavior; M66-M69 should use flat milestone IDs; the first wiring
  scope should be limited to `TechnicalAnalystAgent` and
  `GraphAwareScoreStrategy`; richer technical profiles, strategy configurability,
  and migration of `BlendedScoreStrategy` and `MovingAverageCrossoverStrategy`
  should remain deferred; no implementation work was done in this planning task.
- Mocks created: None.
- Mocks used: None.

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

### M57 Completion Summary

- Assumptions made: M57 should persist a first-class portfolio-level dry-run
  plan for observability only; `RunLevelAllocationService` remains the source
  of executable sizing; fallback settings allocation can store a plan with a
  zero hard cash reserve because there is no money-management cash-buffer
  policy; core basket rows remain advisory-only until M58; same-run sell
  proceeds are forecast with the current 80% haircut for visibility but are not
  used by allocation in this milestone.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, and
  FastAPI `TestClient`.

### M58 Completion Summary

- Assumptions made: M58 should enrich the dry-run plan without changing
  risk/final/paper routing; `cash_buffer` must remain hard and non-borrowable;
  active soft borrowing should be visible only when planned active exposure
  exceeds its own target and eligible non-cash sleeves are idle; frozen sleeves
  should expose protected, not borrowable, idle capacity; core basket decisions
  should become typed plan candidates but not trader-proposal-compatible
  records until M59.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, and
  FastAPI `TestClient`.

### M59 Completion Summary

- Assumptions made: M59 should make the portfolio plan the default source for
  executable BUY allocation only; `TAURUS_PORTFOLIO_PLAN_ALLOCATION_ENABLED=false`
  should retain the legacy run-level allocator for compatibility; existing
  trader proposals should win same-symbol conflicts against core candidates;
  generated core BUYs can use deterministic synthetic debate artifacts because
  risk/final approval remains authoritative; REDUCE/EXIT generation, same-run
  proceeds netting, and sell-first queueing remain out of scope for M60.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, and
  FastAPI `TestClient`.

### M60 Completion Summary

- Assumptions made: M60 should keep the rebalance loop long-only and paper-only;
  threshold trims/exits should come from policy-backed drift, notional, score,
  hard-cap, core-removal, and stale-sleeve rules; same-run BUY sizing may use
  only the configured 80% spendable share of forecast net sell proceeds while
  preserving the 5% NAV hard reserve and 5% BUY price buffer; routing should
  grant pending BUY affordability credit only after sell-side paper orders are
  accepted or filled; M61 remains out of scope.
- Mocks created: None.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, mock final
  approval helpers, FastAPI `TestClient`, and existing React fetch stubs.

### M61 Completion Summary

- Assumptions made: M61 should prove the full M56-M60 rebalance chain without
  broadening live-trading behavior; the M59
  `TAURUS_PORTFOLIO_PLAN_ALLOCATION_ENABLED=false` compatibility flag should
  remain as an operator troubleshooting fallback rather than be removed;
  deterministic seeded paper fills are the narrowest way to give both the
  planner and paper broker the same opening TCS/RELIANCE account state; no
  schema or command-approval changes are required.
- Mocks created: A deterministic M61 paper-run regression fixture that seeds
  opening account/order/fill lineage and advances fake Kite candles for
  next-run settlement, plus a React `portfolioPlan` screen-state fixture
  covering reserve, proceeds, buffer, borrowing, core, and threshold rows.
- Mocks used: Existing `FakeLLMProvider`, existing
  `FakeKiteMarketDataProvider`, deterministic daily-candle fixtures, FastAPI
  `TestClient`, existing React fetch stubs, and local paper-only broker
  simulation.

### M62-M65 Plan Document Completion Summary

- Assumptions made: The graph provenance overhaul is too broad for a single
  milestone because it crosses persisted schema, CSV import, API/UI surfaces,
  promotion lifecycle, graph scoring/backtesting, and final regression/docs;
  it should run as flat milestones M62 through M65. Edge `confidence` should
  remain stored/exposed as audit metadata only, while `provenance_type` drives
  new/unreviewed active/candidate status. TaurusAgent should document but not
  validate `company_profiles.jsonl` edge-like objects because it consumes the
  flattened CSVs.
- Mocks created: None.
- Mocks used: None.

### M62 Completion Summary

- Assumptions made: `provenance_type` should be required for TaurusData
  edge-like CSV imports and validated through a shared repository/import
  contract; `deterministic` and `derived` edges should initialize as `active`
  while `inferred` edges initialize as `candidate`; existing manual/API review
  history should preserve edge status during re-import; non-edge segment and
  product `inferred` booleans remain valid source-file contracts but only map
  into graph edge provenance; `confidence` remains audit metadata and should
  not be removed or reweighted in M62.
- Mocks created: None.
- Mocks used: Existing Postgres test databases, FastAPI `TestClient`, React
  fetch stubs, fake Neo4j driver, and deterministic graph CSV fixtures.

### M63 Completion Summary

- Assumptions made: Imported edge `confidence` should remain stored and
  exposed as audit metadata only; removing the legacy confidence gate should
  not weaken the default because `TAURUS_GRAPH_AUTO_PROMOTE_EDGES` remains
  false unless explicitly enabled; manual review should continue to update only
  status/review metadata and should not rewrite `provenance_type`.
- Mocks created: None.
- Mocks used: Existing Postgres test databases, FastAPI `TestClient`, and
  deterministic graph stats/API fixtures.

### M64 Completion Summary

- Assumptions made: Graph scoring should use relationship strength plus
  statistical validation, with existing backtest evidence weighting preserved;
  imported edge confidence should remain visible only as clearly named raw
  metadata; candidate statuses should remain eligibility state rather than
  score weights, so inferred candidates contribute only after promotion to
  active.
- Mocks created: None.
- Mocks used: Existing Postgres test databases, `FakeLLMProvider`, deterministic
  graph analyst/backtest/risk fixtures, and existing paper-run fake market-data
  providers.

### M65 Completion Summary

- Assumptions made: M65 should remain a regression and documentation closeout
  without regenerating TaurusData outputs; current bundled edge-like CSVs should
  prove the `provenance_type` contract while segment/product CSVs intentionally
  retain non-edge `inferred`; `company_profiles.jsonl` edge-like arrays are a
  TaurusData provenance contract, while TaurusAgent imports flattened CSVs;
  confidence should be documented as descriptive audit metadata or non-graph
  output confidence, not graph edge eligibility, promotion, or scoring input.
- Mocks created: None.
- Mocks used: None.

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

## Completed Portfolio Rebalance Sequence

These milestones were executed in order as separate milestone work and
documented with the standard completion summary.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 38 | M56 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add score semantics and allocation precision plumbing so raw, calibrated, bounded, and allocation scores remain distinct. |
| 39 | M57 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add a dry-run portfolio rebalance plan artifact, API/UI/replay visibility, and legacy-safe serialization. |
| 40 | M58 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Add soft sleeve capacity rules and convert core Shariah basket decisions into executable rebalance candidates. |
| 41 | M59 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Make holistic BUY allocation and executable core routing flow through planner-linked allocation, risk, final, and paper queueing. |
| 42 | M60 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Added threshold trims/exits, 80% same-run proceeds netting, 5% cash/price buffers, and sell-first next-open queueing. |
| 43 | M61 | Done | `docs/TAURUS_PORTFOLIO_REBALANCE_PLAN.md` | Run end-to-end regression, finalize operator docs, clean compatibility scaffolding, and close the sequence. |

## Planned Graph Provenance Sequence

This completed sequence was executed in order as separate milestone work. Stop
after each milestone is complete, verified, cleaned up, and documented; do not
automatically begin later scope.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 44 | M62 | Done | `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md` | Replace graph edge `inferred` with required `provenance_type` across DB, import, API, React graph UI, and Neo4j projection. |
| 45 | M63 | Done | `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md` | Removed confidence thresholds from graph promotion and deleted the legacy min-edge-confidence setting while preserving opt-in statistical auto-promotion. |
| 46 | M64 | Done | `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md` | Remove edge confidence from graph analyst and graph backtest scoring while keeping confidence as audit metadata. |
| 47 | M65 | Done | `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md` | Ran full regression against bundled TaurusData V2 outputs and refreshed graph provenance docs and tracker closeout. |

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
