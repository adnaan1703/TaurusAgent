# Technical Layer Overhaul Handoff

Last updated: 2026-06-23

## Current Status

- Current milestone: None.
- Last completed milestone: M81 Historical Validation Command And Data
  Readiness.
- Planning completed: M74-M86 technical layer overhaul sequence.
- Implementation state: M74, M75, M76, M77, M78, M79, M80, and M81 are complete. The
  canonical/default runtime remains behavior-preserving:
  `TechnicalAnalystAgent` uses `technical_rule_v1` unless the analyst runner is
  explicitly passed `technical_ohlcv_v2`, and `GraphAwareScoreStrategy` uses the
  SMA-spread profile for `graph_aware_score_v1`. M75 added pure OHLCV indicator primitives and an
  opt-in `technical_ohlcv_v2` `TechnicalFeatureService` suite. M76 added the
  pure DB-free `build_universe_technical_context()` path for cross-sectional
  ranks, percentiles, z-scores, missing-feature visibility, availability
  counts, and universe metadata. M77 added the pure DB-free
  `TechnicalSignalService.score_ohlcv_v2()` profile and typed
  `TechnicalOhlcvSignalResult` with alpha/risk/tradability/confidence,
  composite score, coverage, top contributors, missing-feature visibility, and
  JSON-friendly metadata. It did not add analyst wiring, strategy wiring,
  API/UI changes, validation commands, or official-data ingestion.
  M78 added the opt-in `graph_aware_score_v2` strategy config and profile-gated
  `GraphAwareScoreStrategy` wiring, including once-per-ranking-call universe
  technical context, v2 composite scoring, nested v2 metadata on ranking/signal
  payloads, and the `active_strategy` money-management mapping. It did not
  change `graph_aware_score_v1`, `make paper-loop-kite` defaults,
  `TechnicalAnalystAgent`, API/UI surfaces, validation commands, or
  official-data ingestion. M79 added the profile-gated technical analyst v2A
  path: `configs/strategies/graph_aware_score_v2.yaml` sets
  `technical_analyst_profile: technical_ohlcv_v2`, `PaperRunService` passes the
  strategy stage's in-memory v2 `FeatureSnapshot` objects and optional
  `UniverseTechnicalContext` into `run_analyst_suite()`, and
  `TechnicalAnalystAgent` stores deterministic v2 score/confidence/stance from
  `TechnicalSignalService.score_ohlcv_v2()` while preserving LLM narrative
  generation. Latest `backtest_signals` no longer override v2 analyst score;
  they are retained only as audit metadata. M80 added additive v2A visibility
  across strategy ranked candidates, strategy signals, selection/allocation
  rows, analyst-report API payloads, decision-trail input stages, replay stages,
  and compact React debugging panels. It did not change scoring formulas,
  validation logic, official-data ingestion, or promotion. M81 added
  `make validate-technical-v2` and `scripts/validate_technical_v2.py`; the
  command verifies local `daily_candles` common coverage for the selected
  validation universe, defaults to a 3-year evaluation window after a
  252-trading-day warm-up, supports a 5-year strong mode, writes deterministic
  artifacts under `artifacts/technical_validation/<run_id>/`, and runs the
  comparable v1/v2 graph-aware plus technical-only backtest profiles when local
  coverage is sufficient. It reports actionable deeper Kite import guidance
  when coverage is short and does not promote v2 or change canonical paper-loop
  defaults.
- Next recommended milestone: M82 technical validation reports and conservative
  gate.
- Thread model requirement from the user: each milestone worker thread should
  use GPT 5.5 with xhigh thinking.
- Commit policy from the user: do not commit anything unless explicitly asked.

## Required Reading For Every Worker Thread

- `docs/TAURUS_TECHNICAL_LAYER_OVERHAUL_PLAN.md`
- `docs/MILESTONE.md`
- `docs/TAURUS_AGENT_ARCHITECTURE.md`
- `docs/TAURUS_TECHNICAL_ANALYST_AGENT_DEEP_DIVE.md`
- `docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md`
- `/Users/adnaan/Downloads/deep-research-report.md`
- `packages/taurus_core/features/technical_signal.py`
- `packages/taurus_core/features/technical_context.py`
- `packages/taurus_core/features/store.py`
- `packages/taurus_core/features/technical.py`
- `packages/taurus_core/agents/technical_analyst.py`
- `packages/taurus_core/strategies/graph_aware.py`
- `packages/taurus_core/portfolio/score_semantics.py`
- `configs/strategies/graph_aware_score_v1.yaml`
- `configs/strategies/graph_aware_score_v2.yaml`
- `configs/portfolio/money_management_v1.yaml`

## Worker Thread Instructions

- Start by reading the milestone section for the assigned milestone in
  `docs/TAURUS_TECHNICAL_LAYER_OVERHAUL_PLAN.md`.
- Generate or refine an extreme-depth implementation plan for that one
  milestone before editing code.
- Implement only the assigned milestone if the user asks that worker thread to
  execute. If the user only asks for milestone-specific planning, do not edit
  files.
- Do not begin later milestones, do not scaffold future milestones, and do not
  make compatibility changes for later milestones unless the current milestone
  explicitly requires them.
- Preserve v1 behavior until the promotion milestone explicitly changes it.
- Keep all technical-score semantics auditable: raw features, sub-scores,
  confidence, strategy raw score, calibrated allocation score, and final
  candidate score must stay distinct.
- Keep Taurus paper-only and Kite-data-only. Do not add live broker routing or
  real-money behavior.
- Do not commit unless the user explicitly asks.

## Milestone Status

The source of truth is the tracker table in `docs/MILESTONE.md`. The planned
sequence is:

- M74: baseline, evidence contract, and validation design. Done.
- M75: OHLCV indicator primitive expansion. Done.
- M76: universe technical context and cross-sectional normalization. Done.
- M77: `TechnicalSignalService` v2A scoring profile. Done.
- M78: opt-in `graph_aware_score_v2` strategy runtime profile. Done.
- M79: `TechnicalAnalystAgent` v2A deterministic numeric wiring. Done.
- M80: v2A artifact, API, replay, and React visibility. Done.
- M81: historical validation command and data readiness. Done.
- M82: technical validation reports and conservative gate.
- M83: official index, sector, and India VIX data ingestion.
- M84: official delivery, circuit, and tradability data ingestion.
- M85: v2B official-data technical profile.
- M86: promotion decision, regression, docs, and cleanup.

## Update Rules

- When starting a milestone, mark it `In Progress` in `docs/MILESTONE.md`.
- When completing a milestone, mark it `Done`, update any sequence table rows,
  and add a completion summary listing assumptions made, mocks created, and
  mocks used. Use `None` for empty categories.
- If implementation changes public artifacts, API payloads, React-visible
  fields, commands, validation outputs, or operator behavior, update the
  relevant docs in the same milestone.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` for
  accidental Taurus-specific global approvals after the user's
  `# END MY CUSTOM ADDITION` marker. Move Taurus-specific approvals into
  `.codex/rules/default.rules`, document them in `docs/TAURUS_COMMANDS.md`, and
  remove them from global rules when needed.

## Known Boundaries

- `graph_aware_score_v1` remains canonical until M86 or a later explicit user
  instruction changes it. `graph_aware_score_v2` is opt-in only via
  `STRATEGY=configs/strategies/graph_aware_score_v2.yaml`.
- v2A may use full OHLCV plus universe cross-sectional ranks, but must not use
  local market/sector proxies for official market-relative or sector-relative
  scoring.
- v2A technical analyst score/confidence are deterministic when the analyst
  profile is `technical_ohlcv_v2`; LLM output may provide narrative, key
  points, and risks but must not own stored v2 score/confidence.
- M80 visibility is additive only: v2A metadata may be absent on legacy v1 runs,
  and API/UI/replay consumers must omit it cleanly instead of treating it as
  required.
- v2B official relative-strength/regime/microstructure features wait for M83
  and M84 ingestion.
- Validation must prove both technical-agent predictive quality and full-system
  historical backtest behavior before promotion.
