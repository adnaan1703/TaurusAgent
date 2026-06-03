# Taurus Milestone TODO

Last updated: 2026-06-03

This is the active tracker for Taurus milestone work. Keep it concise. Detailed
implementation instructions belong in the linked plan docs.

## Active Sources

- `docs/TAURUS_MOCK_MIGRATION_STATUS.md`: current mock/runtime status.
- `docs/agent_improvement_plans/`: selected functional-MVP migration plans.
- `docs/agent_improvement_plans/LLM_AGENT_SYSTEM_PROMPTS_BACKLOG.md`: deferred
  system prompts for existing LLM-backed analysts not in the selected sequence.
- `docs/TAURUS_USAGE_GUIDE.md`: operator workflow.
- `docs/TAURUS_COMMANDS.md`: command reference and project-local approvals.
- `docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md`: completed M20 graph reference.
- `docs/agent_improvement_plans/PAPER_MONEY_MANAGEMENT_SYSTEM.md`: planned
  Shariah-only paper portfolio money-management sequence.
- `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md`: planned
  full-universe analysis and dynamic run-level allocation sequence.
- `docs/stitch/paper-trade-event-monitor/`: React dashboard visual reference
  assets.

## Standing Safety Rules

- Taurus remains paper-trading-first.
- `LIVE_TRADING_ENABLED=false` remains the default.
- `BROKER_PROVIDER=paper` remains the default.
- Kite support is data-only; execution continues through `PaperBroker`.
- Do not add live broker order routing without a new explicit approved
  milestone.
- Do not commit API keys, broker credentials, Telegram tokens, Kite tokens, or
  user CSV exports.
- Runtime LLM-backed components must use `build_llm_provider(settings)` and the
  default provider must be LM Studio unless an explicit hosted provider is
  configured.
- Money-management and portfolio-construction work must remain long-only,
  equity-only, and restricted to enabled symbols in
  `configs/market_data/nifty_500_shariah.yaml` unless a later explicit
  milestone changes the universe policy.
- Any plan that changes API payloads or decision artifacts must include matching
  React dashboard updates in the same milestone.

## Completed Baseline

| Scope | Status | Result |
|---|---|---|
| M0-M13 | Done | Core FastAPI, database, backtesting, analyst reports, debate, trader proposal, risk, final approval, paper broker, alerts, replay, backup/restore, and paper-trading MVP. |
| M16 | Done | React run-loop observability dashboard became the primary local UI. |
| M17 | Done | Zerodha Kite market-data provider, data-only. |
| M18-M19 | Done | HalalStock compliance sync, halal NSE universe export, Shariah dashboard, and paper-run universe provenance. |
| M20.0-M20.10 | Done | Graph intelligence foundation, importer, API, React views, optional Neo4j projection, graph stats, graph analyst, graph risk, graph metrics, and graph-aware backtesting. |

## Current Baseline Before MVP Migrations

- Runtime is still paper-only with simulated broker execution.
- Default market data, LLM, and alerts are still mock-backed until the selected
  migration sequence changes them.
- Technical analyst is the only default analyst.
- Graph analyst, graph risk, and Neo4j remain opt-in.
- React dashboard is the primary UI; Streamlit is fallback only.
- `docs/TAURUS_MOCK_MIGRATION_STATUS.md` is the detailed status reference.

## Functional MVP Migration Sequence

Execute these migrations in order. Each row is intended to be run separately
with fresh context. After one migration is implemented, verified, cleaned up,
and documented with its completion summary, stop and report the result. Do not
start the next migration unless the user explicitly asks.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 1 | M21 | Done | `docs/agent_improvement_plans/DOCKER_ONLY_DATABASE_MIGRATION.md` | Made Docker Postgres canonical and removed SQLite runtime/test paths. |
| 2 | M22 | Done | `docs/agent_improvement_plans/REAL_LLM_PROVIDER_MIGRATION.md` | Removed runtime mock LLM and defaulted the real provider to LM Studio, with OpenAI/Gemini opt-ins. |
| 3 | M23 | Done | `docs/agent_improvement_plans/KITE_ONLY_MARKET_DATA_MIGRATION.md` | Removed runtime market-data mocks/CSV provider paths and made Kite the only runtime market-data provider. |
| 4 | M24 | Done | `docs/agent_improvement_plans/GRAPH_ENABLED_REAL_DATA_PAPER_LOOP.md` | Enabled graph analyst, graph-aware strategy, and graph risk for the Kite real-data paper path. |
| 5 | M25 | Done | `docs/agent_improvement_plans/LLM_BULL_RESEARCHER_AGENT.md` | Added LLM-backed bullish research with deterministic guardrails and dedicated prompt. |
| 6 | M26 | Done | `docs/agent_improvement_plans/LLM_BEAR_RESEARCHER_AGENT.md` | Added LLM-backed bearish research with deterministic guardrails and dedicated prompt. |
| 7 | M27 | Done | `docs/agent_improvement_plans/LLM_RESEARCH_MANAGER_AGENT.md` | Added LLM-backed debate synthesis and consensus management with dedicated prompt. |
| 8 | M28 | Done | `docs/agent_improvement_plans/PHASE_1_POSITION_AWARE_TRADER_AGENT.md` | Added cross-run portfolio continuity and after-close BUY/HOLD/NO_TRADE/REDUCE/EXIT lifecycle proposals. |
| 9 | M29 | Done | `docs/agent_improvement_plans/LLM_PORTFOLIO_MANAGER_AGENT.md` | Added optional LLM explanations to deterministic final approval/rejection/no-action decisions. |
| 10 | M30 | Done | `docs/agent_improvement_plans/PHASE_2_MARKET_HOURS_POSITION_MONITOR.md` | Added market-hours stop-loss/take-profit monitoring for open long paper positions. |

## Planned Paper Money Management Sequence

Execute these milestones in order. Each row should be run separately with fresh
context, then documented with the standard completion summary before moving on.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 11 | M31 | Done | `docs/agent_improvement_plans/PAPER_MONEY_MANAGEMENT_SYSTEM.md` | Added money-management policy/config/state foundation without changing sizing behavior. |
| 12 | M32 | Done | `docs/agent_improvement_plans/PAPER_MONEY_MANAGEMENT_SYSTEM.md` | Deployed the 40% core sleeve as conservative Shariah basket decisions and artifacts. |
| 13 | M33 | Done | `docs/agent_improvement_plans/PAPER_MONEY_MANAGEMENT_SYSTEM.md` | Added active-sleeve risk-budgeted, volatility-adjusted allocation. |
| 14 | M34 | Done | `docs/agent_improvement_plans/PAPER_MONEY_MANAGEMENT_SYSTEM.md` | Added diversifying/experimental sleeve governors and strategy-level allocation. |
| 15 | M35 | Done | `docs/agent_improvement_plans/PAPER_MONEY_MANAGEMENT_SYSTEM.md` | Added allocation dashboard surfaces and operator workflow docs. |
| 16 | M35.1 | Done | User-provided money-management policy cleanup plan | Removed static core-symbol/cash/drift policy shortcuts; runtime core basket target weights are authoritative for attribution and labels. |
| 17 | Ops progress UI | Done | User-provided Rich Progress UI plan | Added Rich/plain stderr terminal progress for Kite candle import, graph stats computation, and the graph-enabled Kite paper loop. |

## Planned Full-Universe Dynamic Allocation Sequence

Execute these milestones in order. Each row should be run separately with fresh
context, then documented with the standard completion summary before moving on.

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 18 | M36 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Replaced fixed strategy target counts with full-universe ranking artifacts. |
| 19 | M37 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Decompose the paper loop into analysis, allocation, finalization, and execution phases without changing default behavior. |
| 20 | M38 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Add full-universe analysis mode through trader proposals while preserving safe execution behavior. |
| 21 | M39 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Added run-level dynamic allocation across all proposals, using money-management policy or settings fallback constraints. |
| 22 | M40 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Run risk/final decisions for every analyzed symbol and defer execution until allocated approved decisions are known. |
| 23 | M41 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Added API and React observability for full-universe counts, selection ledger, and allocation reasons. |
| 24 | M42 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Aligned backtests, replay, commands, and position-monitor boundaries with ranking/allocation separation. |
| 25 | M43 | Done | `docs/agent_improvement_plans/FULL_UNIVERSE_DYNAMIC_ALLOCATION.md` | Made full-universe analysis the canonical Kite paper-loop behavior after verification. |

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
approvals. Move Taurus-specific approved prefixes into `.codex/rules/default.rules`
if missing, document them in `docs/TAURUS_COMMANDS.md`, and remove them from the
global file. Do not copy unrelated global approvals.

## Maintenance Rules

- Update this file when a migration starts, completes, or is intentionally
  deferred.
- Keep detailed implementation text in the linked migration plan, not here.
- Keep command changes in `docs/TAURUS_COMMANDS.md`.
- Keep operator workflow changes in `docs/TAURUS_USAGE_GUIDE.md`.
