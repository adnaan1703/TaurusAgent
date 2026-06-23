# Technical Layer Overhaul Handoff

Last updated: 2026-06-23

## Current Status

- Current milestone: None.
- Last completed milestone: M75 OHLCV Indicator Primitive Expansion.
- Planning completed: M74-M86 technical layer overhaul sequence.
- Implementation state: M74 and M75 are complete. The current runtime remains
  behavior-preserving: `TechnicalAnalystAgent` uses `technical_rule_v1`, and
  `GraphAwareScoreStrategy` uses the SMA-spread profile for
  `graph_aware_score_v1`. M75 added pure OHLCV indicator primitives and an
  opt-in `technical_ohlcv_v2` `TechnicalFeatureService` suite, but did not add
  cross-sectional context, v2 scoring, analyst wiring, strategy wiring, API/UI
  changes, validation commands, or official-data ingestion.
- Next recommended milestone: M76 Universe Technical Context And
  Cross-Sectional Normalization.
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
- `packages/taurus_core/features/store.py`
- `packages/taurus_core/features/technical.py`
- `packages/taurus_core/agents/technical_analyst.py`
- `packages/taurus_core/strategies/graph_aware.py`
- `packages/taurus_core/portfolio/score_semantics.py`
- `configs/strategies/graph_aware_score_v1.yaml`
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
- M76: universe technical context and cross-sectional normalization.
- M77: `TechnicalSignalService` v2A scoring profile.
- M78: opt-in `graph_aware_score_v2` strategy runtime profile.
- M79: `TechnicalAnalystAgent` v2A deterministic numeric wiring.
- M80: v2A artifact, API, replay, and React visibility.
- M81: historical validation command and data readiness.
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
  instruction changes it.
- v2A may use full OHLCV plus universe cross-sectional ranks, but must not use
  local market/sector proxies for official market-relative or sector-relative
  scoring.
- v2B official relative-strength/regime/microstructure features wait for M83
  and M84 ingestion.
- Validation must prove both technical-agent predictive quality and full-system
  historical backtest behavior before promotion.
