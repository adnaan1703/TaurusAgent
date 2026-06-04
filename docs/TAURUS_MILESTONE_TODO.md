# Taurus Milestone TODO

Last updated: 2026-06-04

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
- `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md`: planned M44-M50 next-open
  AMO-style paper settlement work.
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
- Execution routes only through local `PaperBroker` simulation.
- `make paper-loop-kite` is the canonical real-data profile. It runs
  full-universe analysis, graph-aware ranking, run-level allocation,
  risk/final decisions for analyzed symbols, and allocated-only paper routing.
- React is the primary local dashboard. Streamlit remains a fallback dashboard.
- Alerts default to mock delivery until Telegram is verified with local
  credentials.
- Graph and graph risk are disabled by config default but enabled by
  `make paper-loop-kite` after readiness checks. Neo4j remains optional and
  disposable.

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
| M36-M43 | Done | Full-universe ranking, decomposed paper loop, run-level dynamic allocation, all-symbol risk/final decisions, allocation observability, replay/backtest/command alignment, and default full-universe Kite paper loop enablement. |
| M44-M50 plan document | Done | Created the flat next-open AMO-style paper settlement plan covering baseline tests, pending order schema, pending EOD order creation, settlement, EOD loop integration, dashboard/replay/metrics polish, and final cleanup. Implementation milestones remain planned, not complete. |
| M44 | Done | Added xfail-free baseline unit tests for next-open AMO-style paper settlement. The new target tests intentionally fail against the existing immediate after-close fill behavior; implementation remains planned for later milestones. |

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

## Planned Next-Open AMO Settlement Sequence

Execute these milestones in order. Each row should be run separately with fresh
context, then documented with the standard completion summary before moving on.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 26 | M44 | Done | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Add baseline tests and tracker setup for next-open AMO-style paper settlement. |
| 27 | M45 | Planned | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Add pending next-open order schema, repository support, API status handling, and UI status support. |
| 28 | M46 | Planned | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Change after-close paper decisions to create `PENDING_NEXT_OPEN` orders while preserving immediate market-hours monitor routing. |
| 29 | M47 | Planned | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Settle pending orders at the first newer daily candle open and calculate fills, cash, positions, and P&L. |
| 30 | M48 | Planned | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Integrate settlement into the manual EOD paper loop before new analysis and allocation. |
| 31 | M49 | Planned | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Polish dashboard, replay, metrics, alerts, and operator docs for pending and settled orders. |
| 32 | M50 | Planned | `docs/TAURUS_NEXT_OPEN_AMO_SETTLEMENT_PLAN.md` | Run end-to-end regression, verify operator workflow, and close the milestone sequence. |

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
