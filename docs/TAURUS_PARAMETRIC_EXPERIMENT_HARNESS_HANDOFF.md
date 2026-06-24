# Parametric Experiment Harness Handoff

Last updated: 2026-06-24

## Current Status

- Current milestone: None.
- Last completed milestone: M93 Walk-Forward Folds, Progress, And Bounded
  Parallelism.
- Planning completed: `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_PLAN.md`.
- Implementation state: M89, M90, M91, and M92 are complete. Current v2A scoring family
  weights, top-contributor output, validation profile list, validation CSV
  headers, and technical-validation progress behavior are pinned by
  characterization tests. M90 added the side-effect-free
  `experiments/parametric/` runner shell with Pydantic spec models, a PyYAML
  loader, adapter and metric registries, Cartesian matrix expansion, strict
  unknown-adapter/metric/override validation, family-weight sum validation,
  stable variant fingerprints, dry-run output planning, the
  `scripts/run_parametric_experiment.py` CLI, the `make parametric-experiment`
  wrapper, ignored `experiments/runs/` generated outputs, and the checked-in
  `experiments/specs/v2a_smoke.yaml` dry-run spec. Real validation execution
  and result artifact writing remain planned for M92. M91 added the typed
  `OhlcvV2ScoringParams` surface under `packages/taurus_core/features/`,
  moved current v2A family weights, feature weights, transform scales, context
  weights, confidence weights, guardrails, and score-compression defaults into
  that serializable object, and taught
  `TechnicalSignalService.score_ohlcv_v2()` to accept explicit optional
  scoring params. `GraphAwareScoreStrategy` now parses the nested
  `technical_ohlcv_v2_params` strategy parameter only for
  `technical_profile: technical_ohlcv_v2`; v1 and v2B defaults remain
  unchanged. The parametric allowlist uses the same v2A parameter names. M92
  added non-dry-run `technical_validation_v2a` execution: generated v2A
  profiles inject `technical_ohlcv_v2_params`, backtest overrides map onto
  `ValidationRequest`, each single-window variant runs through
  `run_validation()` with canonical v1/current-v2A baselines, and aggregate
  plus per-variant comparison CSV/manifest JSON artifacts are written under
  `experiments/runs/<run_id>/` or the selected `PARAMETRIC_OUTPUT_ROOT`. M93
  added fold-aware expansion with explicit `single_window` smoke/debug mode and
  default `v2a_yearly` mode for three chronological yearly folds across the
  standard three-year validation window. The adapter now runs each fold x
  variant work unit with explicit bounded `--jobs` parallelism, wraps CLI
  execution in `create_progress_reporter("parametric-experiment")`, translates
  validation readiness/backtest/report events into fold/variant progress
  stages, writes fold metadata into CSV/JSON outputs, and adds
  `variant_aggregate` stability rows for multi-fold CSVs.
- Next recommended milestone: M94 Checked-In v2A Specs And Operator Docs.
- Canonical runtime state: `graph_aware_score_v1` remains the default
  `make paper-loop-kite` strategy; `graph_aware_score_v2` remains opt-in; v2B
  is out of scope for this sequence.
- Commit policy from the user: the active `$ms-exec-chain` invocation
  authorizes one scoped commit per executed milestone.

## Required Reading For Every Worker Thread

- `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_PLAN.md`
- `docs/MILESTONE.md`
- `docs/TAURUS_TECHNICAL_LAYER_OVERHAUL_PLAN.md`
- `docs/TAURUS_TECHNICAL_LAYER_OVERHAUL_HANDOFF.md`
- `docs/TAURUS_COMMANDS.md`
- `packages/taurus_core/features/technical_signal.py`
- `packages/taurus_core/strategies/graph_aware.py`
- `packages/taurus_core/portfolio/score_semantics.py`
- `packages/taurus_core/backtesting/engine.py`
- `packages/taurus_core/ops/progress.py`
- `scripts/validate_technical_v2.py`
- `configs/strategies/graph_aware_score_v1.yaml`
- `configs/strategies/graph_aware_score_v2.yaml`
- `tests/unit/test_technical_validation_contracts.py`

## Worker Thread Instructions

- Start by reading the assigned milestone section in
  `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_PLAN.md`.
- Implement only the assigned milestone if the user asks that worker thread to
  execute. If the user only asks for milestone-specific planning, do not edit
  files.
- Do not begin later milestones, scaffold future milestones, or make
  compatibility changes for later milestones unless the current milestone
  explicitly requires them.
- Preserve v1 behavior and keep v2A opt-in.
- Keep v2B, ML training/export, and live broker routing out of scope.
- Use declarative, allowlisted experiment specs. Do not add arbitrary Python
  callbacks or Python expression execution in experiment rows.
- Keep generated run artifacts under `experiments/runs/` and ignored.
- Reuse the existing `taurus_core.ops.progress` reporter for progress UI.
- Do not commit unless the user explicitly asks.

## Milestone Status

The source of truth is the tracker table in `docs/MILESTONE.md`. The planned
sequence is:

- M89: harness contract and baseline characterization. Done.
- M90: generic parametric runner core and smoke dry-run spec. Done.
- M91: config-driven v2A scoring parameters. Done.
- M92: technical validation adapter and result artifacts. Done.
- M93: walk-forward folds, progress, and bounded parallelism. Done.
- M94: risk-calibration/full-feature v2A specs and operator docs. Planned.
- M95: final regression, cleanup, and fresh-context closeout. Planned.

## Update Rules

- When starting a milestone, mark it `In Progress` in `docs/MILESTONE.md`.
- When completing a milestone, mark it `Done`, update any sequence table rows,
  and add a completion summary listing assumptions made, mocks created, and
  mocks used. Use `None` for empty categories.
- If implementation changes public artifacts, commands, validation outputs,
  progress behavior, or operator workflow, update `docs/TAURUS_COMMANDS.md` in
  the same milestone.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` for
  accidental Taurus-specific global approvals after the user's
  `# END MY CUSTOM ADDITION` marker. Move Taurus-specific approvals into
  `.codex/rules/default.rules`, document them in `docs/TAURUS_COMMANDS.md`, and
  remove them from global rules when needed.

## Known Boundaries

- The harness is for offline paper/backtest experiments only.
- The full-feature v2A sweep should exist as an overnight-capable spec, but the
  bounded risk-calibration spec is the first recommended real sweep.
- The smoke spec is required for quick CLI/progress/output verification.
- Default max expanded variant count is 500.
- Default parallelism is `--jobs 1`.
- Progress main unit is fold x variant.
- Omitted `folds` default to `v2a_yearly`; explicit `folds.mode:
  single_window` remains the smoke/debug mode.
- No ML-ready feature/label dataset export belongs in this sequence; preserve
  provenance for a later ML-specific plan.
