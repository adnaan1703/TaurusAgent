# Parametric Experiment Harness Plan

Last updated: 2026-06-24

This document is the implementation plan for a reusable parametric experiment
harness, starting with opt-in v2A technical-profile tuning. Each milestone
below is a standalone milestone intended to be executed in a separate Codex
thread. Stop after completing and documenting the current milestone; do not
automatically continue to the next milestone.

Status: M90 implementation is complete; M91-M95 remain planned. The sequence
below uses flat milestone IDs M89-M95 and keeps `graph_aware_score_v1`
canonical. The harness is for offline paper/backtest experimentation only; it
must not promote v2A, change `make paper-loop-kite` defaults, or affect live
broker routing.

## Target Behavior

Taurus should have an adapter-first parametric experiment harness that can:

- Read a YAML experiment matrix.
- Validate allowlisted parameter overrides before execution.
- Expand Cartesian variant combinations with explicit max-variant guardrails.
- Run comparable baseline and variant evaluations through the existing Taurus
  technical validation/backtest stack.
- Emit human-comparable CSV output plus a detailed JSON manifest with exact
  provenance.
- Show Taurus-style Rich/plain progress for long sweeps.
- Support small smoke specs, bounded risk-calibration sweeps, and an
  overnight-capable full-feature v2A sweep.

The first adapter is `technical_validation_v2a`. The generic runner and result
contracts should be reusable for later experiment families, but no arbitrary
Python callback runner or ML dataset exporter belongs in this sequence.

## Existing Foundation

- `scripts/validate_technical_v2.py` already builds `ValidationProfile`
  objects, computes data readiness, runs comparable `BacktestEngine` profiles,
  writes technical predictive reports, system backtest reports, CSV summaries,
  and `promotion_gate.json`.
- `packages/taurus_core/backtesting/engine.py` already produces deterministic
  backtest run IDs from strategy config, symbols, date window, and parameters.
- `packages/taurus_core/features/technical_signal.py` owns current v2A scoring:
  family weights, alpha/risk/tradability contributors, transform constants,
  confidence components, and top-contributor metadata.
- `packages/taurus_core/strategies/graph_aware.py` owns current graph-aware
  strategy eligibility gates such as `min_combined_score` and `min_return_20d`.
- `packages/taurus_core/portfolio/score_semantics.py` owns the existing raw
  strategy score to allocation-score calibration.
- `packages/taurus_core/ops/progress.py` provides the shared
  `TAURUS_PROGRESS=auto/plain/false` Rich/plain progress system already used by
  long-running commands.
- `pyproject.toml` already includes `pyyaml`, `pydantic`, `rich`, and `pytest`.
- `docs/MILESTONE.md` requires flat milestone IDs, tracker updates, completion
  summaries, and approval-rule cleanup.

## Parameter Schema Contract

M90-M92 must define a stable domain schema for experiment overrides. Specs must
not reference private helper names such as `_alpha_contributors()`.

Required v2A parameter areas:

- Family weights: `family_weights.alpha`, `family_weights.risk`,
  `family_weights.tradability`; strict validation requires the sum to equal
  `1`.
- Alpha feature weights and transforms:
  `vol_adjusted_return_126d`, `vol_adjusted_return_252d`, `return_126d`,
  `return_63d`, `return_252d`, `macd_histogram_12_26_9`,
  `ema_spread_12_26`, `adx_directional_strength_14`,
  `breakout_high_distance_50d`, `distance_from_52w_high`, and `rsi_14`.
- Risk feature weights and transforms:
  `atr_percent_14`, `volatility_20`, `volatility_63`, `volatility_126`,
  `volatility_252`, `bollinger_bandwidth_20`, `minus_di_14`,
  `bollinger_percent_b_extension`, and `return_20d_instability`.
- Tradability feature weights and transforms:
  `turnover`, `avg_traded_value_20`, `avg_traded_value_63`,
  `turnover_z_score_20`, and `volume_z_score_20`.
- Context scoring weights: z-score component and percentile component used when
  universe context is available.
- Confidence weights: coverage, lookback quality, universe breadth, context
  coverage, family agreement, and tradability quality.
- Eligibility and guardrail params: minimum risk score for new buys, negative
  risk penalty, minimum candidate-breadth multiple, score compression mode, and
  score compression bounds.
- Backtest params: portfolio breadth, max open positions, rebalance cadence,
  cost bps, slippage bps, validation mode, symbols/universe, and fold settings.

Every exposed parameter must have a default equal to the current v2A behavior.
When no experiment params are supplied, v1 and current v2A tests must remain
behavior-compatible.

## Experiment Spec Shape Contract

M89 pins the declarative spec shape that M90-M92 must implement. The first
adapter is `technical_validation_v2a`, and specs must stay YAML-only with
allowlisted override paths. They must not contain Python callback names, Python
expressions, raw SQL, raw JSON-path metric extraction, or private helper names
from the scoring implementation.

Top-level shape:

```yaml
schema_version: 1
experiment_id: v2a_smoke
adapter: technical_validation_v2a
description: Small smoke sweep for opt-in v2A technical scoring.
base_request:
  mode: standard
  symbols: [INFY, TCS]
  validation_years: 3
  warmup_days: 252
  rebalance_every_days: 21
  portfolio_breadth: 5
  max_open_positions: 5
  cost_bps: "10"
  slippage_bps: "5"
baselines:
  include_v1: true
  include_current_v2a: true
variants:
  matrix:
    family_weights.alpha: ["0.65"]
    family_weights.risk: ["0.20"]
    family_weights.tradability: ["0.15"]
folds:
  mode: single_window
metrics:
  - system.total_return
  - system.max_drawdown
  - rank.21d.rank_correlation
execution:
  jobs: 1
  max_variants: 500
output:
  root: experiments/runs
```

Required stable sections:

- `base_request` maps to the existing `ValidationRequest` domain: universe or
  symbols, mode, validation/evaluation window, warmup, timeframe, initial
  capital, portfolio breadth, max open positions, rebalance cadence, costs,
  slippage, artifact/report roots, and explicit v2B exclusion for this sequence.
- `baselines` controls automatic v1 and current-v2A comparison rows. The first
  adapter must include both by default so variants have stable deltas.
- `variants.matrix` is a Cartesian matrix of allowlisted override paths from the
  Parameter Schema Contract above. Strict validation rejects unknown paths,
  invalid values, and family-weight sums other than `1`.
- `folds` starts with `single_window` in M90-M92. M93 adds walk-forward folds
  without changing existing single-window specs.
- `metrics` contains named metric IDs only. Initial namespaces are `system.*`
  for full-system backtest/profile metrics and `rank.<horizon>d.*` for
  technical-agent predictive checks.
- `execution` owns runner controls such as `jobs` and `max_variants`. Defaults
  are `jobs: 1` and `max_variants: 500`.
- `output.root` defaults to `experiments/runs`, whose generated contents remain
  ignored.

## Global Rules For M89-M95

- Implement only the requested milestone. After that milestone is complete,
  verified, cleaned up, and documented, stop and report the result.
- Do not start, partially implement, scaffold, or prepare later milestones
  unless the user explicitly asks to proceed.
- Keep `graph_aware_score_v1` and `technical_rule_v1` canonical. v2A remains
  opt-in and experimental.
- Keep v2B out of scope. Do not require official-data readiness or
  `TECHNICAL_VALIDATION_INCLUDE_V2B=true`.
- Generated experiment outputs belong under `experiments/runs/` and must be
  ignored; source specs and harness code are tracked.
- The first adapter must reuse the existing validation/report machinery rather
  than shelling out once per variant or duplicating report logic.
- YAML specs must be declarative and allowlisted. No arbitrary Python callbacks,
  Python expressions, or raw JSON-path metrics in v1.
- Metric selection uses named metric IDs such as `system.total_return` and
  `rank.21d.rank_correlation`. Output includes raw requested metrics plus
  numeric deltas versus v1 and current v2A where applicable.
- Full-feature sweeps are supported, but the first checked-in production-sized
  spec should be the bounded risk-calibration grid. The full-feature sweep is
  for deliberate overnight use after dry-run inspection.
- At completion of every milestone, update `docs/MILESTONE.md` with status and
  an explicit completion summary listing assumptions made, mocks created, and
  mocks used. Use `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the project-local approval cleanup rule in `docs/MILESTONE.md`.

## M89 - Harness Contract And Baseline Characterization

Purpose: pin the current validation/profile/metric behavior and define the
experiment contracts before implementation.

Instructions:

- Inspect current sources:
  - `scripts/validate_technical_v2.py`
  - `packages/taurus_core/features/technical_signal.py`
  - `packages/taurus_core/strategies/graph_aware.py`
  - `packages/taurus_core/portfolio/score_semantics.py`
  - `packages/taurus_core/backtesting/engine.py`
  - `packages/taurus_core/ops/progress.py`
  - `configs/strategies/graph_aware_score_v1.yaml`
  - `configs/strategies/graph_aware_score_v2.yaml`
- Add characterization tests for:
  - Current v2A default family weights and contributor outputs.
  - Current validation profile list for v1, v1 technical-only, v2A, and v2A
    technical-only.
  - Current metric field names emitted by validation summary CSVs.
  - Current progress reporter behavior that the new CLI must reuse.
- Document the stable experiment spec shape in the plan or a small companion
  schema reference if needed.
- Do not add the runner, CLI, Make target, configurable scoring params, or new
  generated outputs in this milestone.

Expected code shape:

- Mostly tests and documentation clarifying contracts.
- Production changes should be limited to harmless test seams if current
  behavior cannot otherwise be observed.

Acceptance criteria:

- Current validation and v2A scoring behavior is pinned before adding parameter
  injection.
- A future implementer has a clear schema contract for M90-M92.
- Runtime behavior remains unchanged.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_graph_backtesting.py tests/unit/test_progress.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M90 - Generic Parametric Runner Core

Status: Done.

Purpose: add the reusable experiment runner, YAML matrix parsing, strict
validation, dry-run expansion, and output shell without touching v2A scoring.

Instructions:

- Add `experiments/parametric/` with:
  - Pydantic spec models.
  - YAML loader using `pyyaml`.
  - Adapter registry with no side effects at import time.
  - Cartesian matrix expansion.
  - Stable variant fingerprinting from adapter, base request, overrides,
    fold, and metric set.
  - Default max expanded variants of `500`; require explicit override to
    exceed it.
  - Named metric registry scaffolding.
- Add `scripts/run_parametric_experiment.py` with:
  - `--spec`
  - `--dry-run`
  - `--jobs`
  - `--max-variants`
  - `--output-root`
  - clear non-zero failures for invalid specs.
- Add `make parametric-experiment` with `EXPERIMENT_SPEC`, `PARAMETRIC_JOBS`,
  `PARAMETRIC_MAX_VARIANTS`, `PARAMETRIC_OUTPUT_ROOT`, and
  `PARAMETRIC_DRY_RUN` variables.
- Add ignore rules so generated `experiments/runs/` content is ignored while
  source specs and harness code remain tracked.
- Add `experiments/specs/v2a_smoke.yaml` as the minimal checked-in dry-run spec:
  a tiny symbol set or fixture-friendly setup, single-window mode, one or two
  variants, and a short metric set. It does not need to run a real backtest
  until M92.
- Do not run backtests or call `scripts/validate_technical_v2.py` yet.

Expected code shape:

- Runner code should be independent from Taurus technical specifics except for
  adapter registration.
- Dry-run output should list expanded variants, fold count, total work units,
  metric IDs, and planned output paths.

Acceptance criteria:

- Invalid YAML, unknown adapters, unknown metric IDs, unknown override keys,
  and oversized matrices fail before execution.
- Dry-run mode performs no database writes and creates no run outputs.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M91 - Config-Driven v2A Scoring Parameters

Purpose: make v2A scoring tunable through validated optional params while
preserving current defaults.

Instructions:

- Add typed v2A parameter objects under `packages/taurus_core/features/`.
- Teach `TechnicalSignalService.score_ohlcv_v2()` to accept optional v2A params
  through explicit arguments, not global monkeypatching.
- Thread optional params from `GraphAwareScoreStrategy` strategy parameters
  only when `technical_profile: technical_ohlcv_v2`.
- Expose every current family weight, feature weight, and transform constant
  named in the Parameter Schema Contract.
- Add guardrail and score-compression hooks but keep defaults neutral:
  - no negative-risk hard block unless configured
  - no candidate-breadth block unless configured
  - no score compression unless configured
- Preserve `TechnicalAnalystAgent` default behavior and v1 behavior.
- Do not add the experiment runner adapter execution in this milestone.

Expected code shape:

- Default v2A params should be a serializable object used by both tests and
  runtime code.
- The current hard-coded constants should either move into the default param
  object or be read through a compatibility wrapper that returns the same
  values.
- Components/top-contributors should still report effective weights and scores.

Acceptance criteria:

- With no params, v2A scores, components, confidence, and metadata match the
  current behavior.
- With params, focused tests show family weights, selected transform scales,
  risk gates, and score compression affect only opt-in v2A.
- Unknown parameter names fail validation before scoring.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_strategy_ranking.py tests/unit/test_graph_backtesting.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M92 - Technical Validation Adapter And Result Artifacts

Purpose: connect generated variants to the existing validation/report stack and
emit comparable CSV/JSON experiment outputs.

Instructions:

- Refactor `scripts/validate_technical_v2.py` so `run_validation()` can accept
  an explicit tuple of `ValidationProfile` objects while preserving the current
  default profile behavior.
- Implement the `technical_validation_v2a` adapter:
  - automatically include canonical v1 and current v2A baselines
  - build generated v2A `ValidationProfile` variants from declarative overrides
  - run one validation batch per fold/window
  - extract spec-declared metrics through the named metric registry
  - compute numeric deltas versus v1 and current v2A
  - write comparison CSV and manifest JSON under `experiments/runs/<run_id>/`
- Keep `promotion_gate.json` report-only. Do not promote v2A or change defaults.
- Do not add walk-forward fold orchestration or parallel execution yet beyond a
  single-window adapter path.

Expected code shape:

- Reuse validation report builders rather than reimplementing technical-agent
  predictive checks or full-system summaries.
- Experiment manifests should include spec hash, git commit, adapter name,
  metric IDs, output paths, baseline profile names, variant params, validation
  artifact pointers, and status.

Acceptance criteria:

- A tiny v2A smoke spec can execute end-to-end and produce CSV/JSON outputs.
- Current `make validate-technical-v2` still produces the same default profile
  set when no injected profiles are supplied.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py tests/unit/test_graph_backtesting.py
PARAMETRIC_DRY_RUN=false make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-smoke
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M93 - Walk-Forward Folds, Progress, And Bounded Parallelism

Purpose: make larger sweeps scientifically safer and operationally visible.

Instructions:

- Add fold support to the spec model:
  - single-window mode for smoke/debug
  - default v2A mode with three chronological yearly folds across the current
    standard three-year validation window
- Add aggregate CSV rows that summarize per-variant stability across folds.
- Add bounded parallel execution with `--jobs N`, defaulting to `1`.
- Reuse `taurus_core.ops.progress`:
  - CLI wraps execution in `create_progress_reporter("parametric-experiment")`
  - progress respects `TAURUS_PROGRESS=auto/plain/false`
  - main progress unit is fold x variant
  - emit stage labels for spec loading, expansion, readiness, backtests,
    metric extraction, and result writing
- Ensure errors stop the run with enough context to identify the variant/fold.
- Do not add new experiment specs beyond what is needed to test folds/progress.

Expected code shape:

- Parallelism must be explicit and bounded. Do not auto-detect CPU count.
- Progress events should be easy to test without requiring a TTY.
- Fold metadata should appear in both CSV and JSON manifest outputs.

Acceptance criteria:

- Dry-run reports total fold x variant work units.
- Plain progress output includes current fold, variant label, counts, percent,
  elapsed time, and ETA.
- `TAURUS_PROGRESS=false` suppresses terminal progress.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py tests/unit/test_progress.py
TAURUS_PROGRESS=plain PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M94 - Checked-In v2A Specs And Operator Docs

Purpose: provide practical starting specs for smoke, bounded
risk-calibration, and overnight full-feature experimentation.

Instructions:

- Refine `experiments/specs/v2a_smoke.yaml` if needed so it remains suitable
  for quick CLI, progress, and output verification after M92-M93 execution
  support exists.
- Add `experiments/specs/v2a_risk_calibration.yaml`:
  - three yearly folds
  - bounded grid over family weights, negative-risk gates, score compression,
    candidate-breadth guard, and key volatility/momentum transform scales
  - spec-declared metrics covering return, CAGR, Sharpe, Sortino, max
    drawdown, turnover, win rate, cash utilization, sizing failures,
    candidate breadth, 21d rank IC, 63d rank IC, and top-bottom spreads
- Add `experiments/specs/v2a_full_feature_sweep.yaml`:
  - all tunable v2A feature weights and transform constants
  - clear comments that it is intended for deliberate overnight use after
    dry-run inspection
  - require explicit `--max-variants` override if it exceeds the default cap
- Update `docs/TAURUS_COMMANDS.md` with the implemented Make/CLI workflow,
  progress controls, dry-run guidance, and output locations.
- Update this plan, the handoff, and `docs/MILESTONE.md` with current status.

Expected code shape:

- Specs should be readable by humans and diff-friendly.
- Comments should explain intent, not duplicate every schema rule.
- Do not add ML dataset export.

Acceptance criteria:

- Smoke spec is suitable for tests and quick local verification.
- Risk-calibration spec is the recommended first real sweep.
- Full-feature spec exists but is clearly marked as overnight/broad.

Verification:

```bash
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_full_feature_sweep.yaml
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M95 - Final Regression, Cleanup, And Fresh-Context Closeout

Purpose: close the parametric harness sequence with focused regression,
operator documentation, and cleanup.

Instructions:

- Run focused backend tests for:
  - parametric runner
  - v2A parameterized scoring
  - strategy ranking
  - validation adapter
  - progress formatting
- Run a smoke dry-run and one tiny smoke execution.
- Run broader regression only if prior milestones touched shared technical,
  validation, or backtest behavior broadly enough to justify it.
- Confirm generated `experiments/runs/` outputs are ignored and no large run
  artifacts are staged.
- Refresh this plan, the handoff, command docs, and `docs/MILESTONE.md` to
  describe implemented behavior.
- Inspect `/Users/adnaan/.codex/rules/default.rules` for accidental
  Taurus-specific global approvals and follow the cleanup rule if needed.
- Do not run the full-feature overnight sweep as part of closeout unless the
  user explicitly asks.

Expected code shape:

- No new feature work unless required to fix regressions discovered during
  closeout.
- Documentation should clearly distinguish smoke, risk-calibration, and
  full-feature specs.

Acceptance criteria:

- The sequence is documented as complete.
- v1 remains canonical and v2A remains opt-in.
- The first real recommended operator action is a dry-run of
  `v2a_risk_calibration.yaml`.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py tests/unit/test_technical_signal_service.py tests/unit/test_strategy_ranking.py tests/unit/test_graph_backtesting.py tests/unit/test_progress.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml
PARAMETRIC_DRY_RUN=false make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-smoke
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used
