# V2A Experiment Redesign Plan

Last updated: 2026-06-28

This document is the implementation plan for the next v2A experiment redesign
sequence. Each milestone below is a standalone milestone intended to be executed
in a separate Codex thread. Stop after completing and documenting the current
milestone; do not automatically continue to the next milestone.

## Target Behavior

Taurus should support a staged, interpretable experiment program for opt-in
technical-profile tuning:

- Keep `graph_aware_score_v1` canonical and keep current v2A opt-in.
- Preserve the existing full-feature v2A sweep as an overnight broad template.
- Add first-class grouped experiment axes so valid override bundles can be
  expressed without invalid Cartesian combinations.
- Add a medium-horizon macro sweep for family-weight trios and paired portfolio
  sizes.
- Add a medium-horizon focused sensitivity sweep that tests compact, attributable
  feature-weight and transform-scale cases.
- Evaluate candidates with trade-quality diagnostics, not aggregate return alone:
  realized versus unrealized P&L, closed-trade win/loss economics, profit factor,
  fold consistency, and 21d rank behavior must stay visible in macro and
  sensitivity outputs.
- Plan `v2A-SH` as a separate short-horizon technical profile design track, not
  as a mutation of current medium-horizon v2A.

## Existing Foundation

- `experiments/parametric/spec.py` defines the strict Pydantic experiment spec.
  `variants.matrix` remains a non-empty mapping of override paths to value
  lists, and M96 added optional `variants.axes` grouped override choices.
- `experiments/parametric/expansion.py` expands the matrix as a Cartesian
  product crossed with one selected value from each optional grouped axis,
  validates family-weight sums and portfolio-size constraints after defaults
  and overrides, creates stable variant fingerprints, and builds fold-aware
  output paths.
- `experiments/parametric/adapters.py` allowlists v2A scoring, guardrail, and
  backtest override paths, including `backtest.portfolio_breadth` and
  `backtest.max_open_positions`.
- `experiments/parametric/metrics.py` supports 5d, 21d, and 63d rank metrics
  plus system metrics. M99 exposed the 5d IDs needed by future short-horizon
  specs by reusing validation report data already emitted for 5d horizons.
- `experiments/specs/v2a_full_feature_sweep.yaml` is the current deliberate
  overnight full-feature template with 512 variants and 3 yearly folds.
- `experiments/specs/v2a_cadence_only_comparison.yaml` is the M101
  cadence-only comparison for current medium-horizon v2A scoring at 5d and 10d
  rebalance cadence. Its completed evidence note is
  `docs/reports/parametric/v2a_cadence_only_comparison_20260628.md`.
- A non-dry-run full-feature sweep was executed under
  `/tmp/taurus-parametric-risk/v2a_full_feature_sweep-ff23bcf5745e` after this
  plan was first created. The sweep completed 512 variants across three yearly
  folds. The strongest tied candidates improved aggregate return and Sharpe
  slightly versus current v2A, but no candidate fixed negative aggregate 21d
  rank correlation. v1 had better closed-trade quality and positive realized
  P&L, while current v2A and the top candidates were carried by open
  mark-to-market gains and had negative realized P&L. This evidence reinforces
  that v1 remains canonical and that M97/M98 must emphasize trade-quality and
  rank diagnostics, not just `system.total_return`.
- `scripts/validate_technical_v2.py` computes prediction checks for 5d, 21d, and
  63d horizons, and the parametric metric registry exposes the 5d, 21d, and 63d
  rank metric IDs needed by current medium-horizon regression checks and future
  short-horizon specs.
- `packages/taurus_core/features/technical_params.py` defines current v2A
  defaults: family weights `0.65 / 0.20 / 0.15`, feature weights, transform
  scales, confidence weights, guardrails, and score compression.
- `packages/taurus_core/features/technical_signal.py` implements current
  `technical_ohlcv_v2` scoring. It is medium-horizon biased and does not include
  short-horizon alpha contributors such as `return_20d` or
  `vol_adjusted_return_63d`.
- `packages/taurus_core/strategies/graph_aware.py` supports
  `technical_ohlcv_v2` and `technical_official_v2b`; a future `v2A-SH` profile
  requires explicit strategy/profile wiring.
- `docs/MILESTONE.md` is the active milestone tracker. New plans must be listed
  in Active Sources, planning work must be recorded in Completed Milestone
  Summary, and future milestone IDs must be flat.

## Global Rules For M96-M100

- Execute one milestone at a time. When a user asks to execute a specific
  milestone, implement only that milestone, complete verification and docs for
  that milestone, then stop.
- Do not start, scaffold, or partially implement later milestones unless the
  current milestone explicitly requires a compatibility seam for its own
  acceptance criteria.
- Preserve current specs and v1/current-v2A behavior unless a milestone names a
  specific additive change.
- Do not promote v2A or any generated candidate from the full-feature sweep.
  Treat that run as diagnostic evidence until a later, explicit promotion
  milestone shows fold-consistent return, acceptable drawdown, non-collapsing
  realized trade quality, and non-negative rank evidence.
- Keep the experiment harness declarative. Do not add Python callbacks, Python
  expression execution, or arbitrary code execution from YAML specs.
- Keep generated experiment outputs under ignored `experiments/runs/` or an
  explicit `PARAMETRIC_OUTPUT_ROOT`.
- Keep `LIVE_TRADING_ENABLED=false`, `BROKER_PROVIDER=paper`, and all v2A/v2A-SH
  work opt-in. Do not add live broker routing.
- Use flat milestone IDs `M96` through `M100`.
- If a milestone changes commands, public operator workflow, spec syntax, result
  artifacts, progress behavior, or known checked-in specs, update
  `docs/TAURUS_COMMANDS.md` and this plan in the same milestone.
- At milestone completion, update `docs/MILESTONE.md`, update
  `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_HANDOFF.md`, and include a completion
  summary with assumptions made, mocks created, and mocks used. Use `None` for
  empty categories.
- At cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` for accidental
  Taurus-specific approvals after the user's `# END MY CUSTOM ADDITION` marker.
  Move any Taurus-specific approvals into `.codex/rules/default.rules`, document
  them in `docs/TAURUS_COMMANDS.md`, and remove them from the global rules file.

## M96 - Grouped Experiment Axes

Purpose: add first-class grouped override axes so the harness can express paired
family-weight trios and paired portfolio-size controls without invalid Cartesian
combinations.

Instructions:

- Inspect `experiments/parametric/spec.py`,
  `experiments/parametric/expansion.py`,
  `experiments/parametric/loader.py`,
  `experiments/parametric/adapters.py`, and
  `tests/unit/test_parametric_experiments.py` before editing.
- Extend the spec model so `variants` supports the existing `matrix` field and a
  new optional `axes` list.
- Keep `variants.matrix` backward-compatible for all existing checked-in specs.
- Define each axis as a named list of values. Each value must have a stable `id`
  and an `overrides` mapping.
- Expand by crossing the matrix combinations with one selected value from each
  axis.
- Reject duplicate override paths across matrix and axes unless the normalized
  values are identical.
- Validate merged overrides with the existing adapter normalization and
  validation rules, including family-weight sum validation and
  `max_open_positions >= portfolio_breadth`.
- Include axis names and selected value IDs in dry-run output and per-variant
  metadata so operators can identify why a variant exists.
- Do not add new v2A specs in this milestone except for a minimal fixture needed
  by focused tests.
- Do not implement short-horizon scoring or v2A-SH in this milestone.

Expected code shape:

- Existing specs using only `variants.matrix` continue to parse and expand
  identically.
- `VariantPlan` or adjacent metadata carries selected axes in a deterministic,
  JSON-serializable shape.
- Variant fingerprints include the merged override payload and remain stable
  under YAML ordering changes.

Acceptance criteria:

- Existing smoke, risk-calibration, and full-feature specs dry-run with the same
  variant and work-unit counts as before.
- A new grouped-axis fixture can express family-weight trios and portfolio-size
  pairs without creating invalid combinations.
- Invalid duplicate override paths and invalid family-weight totals fail with
  clear `ExperimentSpecError` messages.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_full_feature_sweep.yaml
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

Implementation closeout:

- Status: Done on 2026-06-26.
- Summary: Added optional `variants.axes` parsing, grouped-axis expansion,
  duplicate override conflict checks after adapter normalization, merged
  family-weight and portfolio-size validation, selected-axis metadata in
  dry-run rows, and `axis_values` metadata in comparison CSV rows and variant
  manifests.
- Verification: `uv run pytest tests/unit/test_parametric_experiments.py`;
  `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml`;
  `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml`;
  `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_full_feature_sweep.yaml`; `make lint`.
- Assumptions made: `variants.matrix` remains required and backward-compatible;
  grouped axes are additive and declarative; M96 does not add checked-in v2A
  sweep specs or implement v2A-SH.
- Mocks created: None.
- Mocks used: None.

## M97 - Medium-Horizon Macro Sweep Spec

Purpose: add a compact medium-horizon macro experiment that tests family-weight
allocation, paired portfolio-size concentration, and trade-quality diagnostics
before deeper feature tuning.

Instructions:

- Inspect `experiments/specs/v2a_full_feature_sweep.yaml`,
  `experiments/specs/v2a_risk_calibration.yaml`,
  `experiments/parametric/metrics.py`, and the grouped-axis implementation from
  M96 before editing.
- Add `experiments/specs/v2a_medium_macro_sweep.yaml`.
- Add or verify parametric extraction for the diagnostic fields needed to avoid
  over-reading aggregate return: realized P&L, unrealized P&L, closed-trade
  count, closed win/loss counts, gross profit, gross loss, average win, and
  average loss. Keep the fields additive in validation reports and comparison
  CSVs.
- Prefer explicit metric IDs such as `system.realized_pnl_inr`,
  `system.unrealized_pnl_inr`, `system.closed_trade_count`,
  `system.closed_win_count`, `system.closed_loss_count`,
  `system.gross_profit_inr`, `system.gross_loss_inr`,
  `system.average_closed_win_inr`, and `system.average_closed_loss_inr` unless
  a better repo-local naming pattern exists when M97 is implemented.
- Keep base request aligned with current v2A medium-horizon behavior:
  `mode: standard`, `validation_years: 3`, `warmup_days: 252`,
  `rebalance_every_days: 21`, `cost_bps: "10"`, `slippage_bps: "5"`, and the
  existing Shariah universe.
- Add a family-weight axis with these values:

| ID | Alpha | Risk | Tradability |
|---|---:|---:|---:|
| `current` | `0.65` | `0.20` | `0.15` |
| `risk_tilted` | `0.60` | `0.25` | `0.15` |
| `defensive` | `0.55` | `0.30` | `0.15` |
| `tradability_tilted` | `0.60` | `0.20` | `0.20` |
| `aggressive_alpha` | `0.70` | `0.15` | `0.15` |

- Add a portfolio-size axis with these paired values:

| ID | `portfolio_breadth` | `max_open_positions` |
|---|---:|---:|
| `size_5` | `5` | `5` |
| `size_8` | `8` | `8` |
| `size_10` | `10` | `10` |

- Include expanded diagnostic metrics: `system.win_rate`,
  `system.profit_factor`, the realized/unrealized and closed-trade economics
  fields above, `system.rejected_candidate_count`,
  `system.trimmed_candidate_count`, `rank.21d.hit_rate`, and
  `rank.63d.hit_rate`, alongside the existing full-feature metrics.
- Set `execution.max_variants` to the expected expanded count and keep comments
  clear that this is a macro sweep, not the full feature sweep.
- Update `docs/TAURUS_COMMANDS.md` with a dry-run command for the macro sweep.
- Do not change `v2a_full_feature_sweep.yaml` in this milestone.
- Do not add `rank.5d.*` metrics or v2A-SH work in this milestone.

Expected code shape:

- The macro spec expands to 15 variants and 45 work units under default
  `v2a_yearly` folds.
- Axis IDs appear in dry-run output and generated manifests.

Acceptance criteria:

- Operators can dry-run the macro sweep and see each family/portfolio pair
  clearly.
- Existing current-v2A and v1 baselines remain included.
- No invalid portfolio target/cap combinations are generated.
- The macro comparison output can separate candidates driven by realized
  closed-trade quality from candidates driven mainly by open mark-to-market
  gains.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_macro_sweep.yaml
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M98 - Medium-Horizon Sensitivity Sweep Spec

Purpose: add an interpretable sensitivity-style feature sweep that tests compact,
targeted feature-weight and transform-scale changes without a large factorial
explosion, while preserving the M97 trade-quality diagnostics.

Instructions:

- Inspect the M96 grouped-axis support, the M97 macro spec, current v2A defaults
  in `packages/taurus_core/features/technical_params.py`, and
  `experiments/specs/v2a_full_feature_sweep.yaml` before editing.
- Add `experiments/specs/v2a_medium_sensitivity_sweep.yaml`.
- Keep macro settings fixed at current medium-horizon defaults:
  family weights `0.65 / 0.20 / 0.15`, `portfolio_breadth: 5`,
  `max_open_positions: 5`, and `rebalance_every_days: 21`.
- Express sensitivity cases as grouped axis values where each case is one
  explicit override bundle. Do not cross the cases with each other.
- Include these compact cases:

| Case ID | Override |
|---|---|
| `alpha_var126_weight_low` | `alpha_weights.vol_adjusted_return_126d = 0.14` |
| `alpha_var126_scale_low` | `alpha_transforms.vol_adjusted_return_126d.scale = 3.5` |
| `alpha_var126_scale_high` | `alpha_transforms.vol_adjusted_return_126d.scale = 4.5` |
| `alpha_var252_weight_low` | `alpha_weights.vol_adjusted_return_252d = 0.12` |
| `alpha_var252_weight_high` | `alpha_weights.vol_adjusted_return_252d = 0.16` |
| `alpha_return126_weight_low` | `alpha_weights.return_126d = 0.09` |
| `alpha_return126_weight_high` | `alpha_weights.return_126d = 0.13` |
| `alpha_return63_weight_low` | `alpha_weights.return_63d = 0.08` |
| `alpha_return63_scale_high` | `alpha_transforms.return_63d.scale = 0.24` |
| `risk_atr_weight_high` | `risk_weights.atr_percent_14 = 0.20` |
| `risk_atr_scale_low` | `risk_transforms.atr_percent_14.scale = 0.040` |
| `risk_vol20_weight_high` | `risk_weights.volatility_20 = 0.18` |
| `risk_vol20_scale_low` | `risk_transforms.volatility_20.scale = 0.040` |
| `risk_vol63_weight_low` | `risk_weights.volatility_63 = 0.12` |
| `risk_return20_instability_harsh` | `risk_transforms.return_20d_instability.scale = 0.14` |
| `trad_turnover_weight_high` | `tradability_weights.turnover = 0.26` |
| `trad_avg_value20_weight_low` | `tradability_weights.avg_traded_value_20 = 0.22` |
| `trad_turnover_z_scale_low` | `tradability_transforms.turnover_z_score_20.scale = 2.5` |
| `trad_volume_z_weight_high` | `tradability_weights.volume_z_score_20 = 0.17` |

- Include the same expanded diagnostic metrics as M97. Rank candidates by a
  balanced read of return, Sharpe, drawdown, profit factor, realized/unrealized
  split, and 21d rank behavior; do not treat a small aggregate-return edge as
  enough evidence.
- Update `docs/TAURUS_COMMANDS.md` with a dry-run command for the sensitivity
  sweep.
- Do not include portfolio-size or family-weight axes in this spec.
- Do not alter current v2A defaults or the existing full-feature sweep.

Expected code shape:

- The sensitivity spec reads as a case list with direct one-case-at-a-time
  attribution.
- The spec expands to the case count times 3 yearly folds, not to a factorial of
  all feature values.

Acceptance criteria:

- Operators can dry-run the sensitivity sweep and inspect each case by ID.
- Existing current-v2A and v1 baselines remain included.
- Results can be attributed to one intended override bundle per variant.
- Sensitivity results make inert knobs and tied outcomes obvious enough to
  prune future sweeps.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_sensitivity_sweep.yaml
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

Implementation closeout:

- Status: Done on 2026-06-26.
- Summary: Added `experiments/specs/v2a_medium_sensitivity_sweep.yaml` as a
  compact 19-case medium-horizon sensitivity spec. The spec keeps current v2A
  family weights, `portfolio_breadth=5`, `max_open_positions=5`, and 21-day
  rebalancing fixed; represents each feature-weight or transform-scale
  sensitivity as one `sensitivity_case` grouped-axis value; includes v1 and
  current-v2A baselines; and requests the same realized/unrealized P&L,
  closed-trade economics, return/risk, and 21d/63d rank diagnostics as M97.
- Verification: `uv run pytest tests/unit/test_parametric_experiments.py`;
  `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_medium_sensitivity_sweep.yaml`;
  `make lint`; `make test`.
- Assumptions made: M98 should add only the medium-horizon sensitivity sweep
  spec and focused expansion coverage; the current spec schema still requires a
  non-empty matrix, so the sensitivity spec pins `backtest.cost_bps: ["10"]`
  there and keeps all feature/transform sensitivity choices in one grouped
  axis; current v2A defaults, the existing full-feature sweep, rank 5d metrics,
  and v2A-SH work remain unchanged.
- Mocks created: None.
- Mocks used: None.
- Cleanup: Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries
  existed after the user's `# END MY CUSTOM ADDITION` marker, so no
  Taurus-specific approval migration was needed.

## M99 - V2A-SH Short-Horizon Design Contract

Purpose: define the future short-horizon technical profile contract without
mixing quick-trading assumptions into current medium-horizon v2A.

Instructions:

- Inspect `packages/taurus_core/features/technical_signal.py`,
  `packages/taurus_core/features/technical_params.py`,
  `packages/taurus_core/features/store.py`,
  `packages/taurus_core/strategies/graph_aware.py`,
  `configs/strategies/graph_aware_score_v2.yaml`,
  `scripts/validate_technical_v2.py`, and the M96-M98 outputs before editing.
- Extend this plan or add a focused design section that defines the future
  `v2A-SH` implementation contract.
- Use `technical_ohlcv_v2a_sh` as the planned technical profile name and
  `graph_aware_score_v2a_sh` as the planned strategy config name unless a better
  repo-local naming conflict is discovered.
- Treat `rebalance_every_days: 5` and `rebalance_every_days: 10` as separate
  short-horizon experiment cases. Do not choose one canonical default in this
  milestone.
- Define the candidate short-horizon feature families:
  `return_20d`, `return_63d`, `vol_adjusted_return_63d`, MACD, EMA spread, RSI,
  20d and 50d breakout, ATR, 20d volatility, turnover, traded value, and
  volume/turnover z-scores.
- Add `rank.5d.rank_correlation`, `rank.5d.top_bottom_decile_spread`, and
  `rank.5d.hit_rate` to the parametric metric registry if the design contract
  decides these are required before the first v2A-SH spec.
- State the non-goal clearly: exact v2A-SH feature weights, transform scales, and
  promotion decisions are deferred to a later implementation sequence after the
  design contract is accepted.
- Do not implement the scoring profile, strategy config, or v2A-SH experiment
  spec in this milestone unless the user explicitly broadens scope.

Expected code shape:

- If metric registry changes are included, they should reuse existing validation
  report data already produced for 5d horizons.
- The design contract should make clear that v2A-SH is a separate opt-in profile,
  not current v2A with only faster rebalancing.

Acceptance criteria:

- The repo has a documented, implementation-ready v2A-SH contract for a later
  milestone sequence.
- Current v2A defaults and checked-in medium-horizon specs remain unchanged.
- Short-horizon questions are no longer hidden inside the medium-horizon v2A
  experiment specs.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

Design contract:

- `v2A-SH` is a separate opt-in short-horizon technical-profile design, not
  current medium-horizon v2A with only `rebalance_every_days` changed. It must
  get its own profile identity, strategy config, validation report labeling,
  experiment specs, and promotion evidence.
- Planned technical profile name: `technical_ohlcv_v2a_sh`.
- Planned strategy name and checked-in strategy config path:
  `graph_aware_score_v2a_sh` and
  `configs/strategies/graph_aware_score_v2a_sh.yaml`.
- Planned strategy parameters should keep the graph-aware strategy type and
  paper-only execution path, set `technical_profile` to
  `technical_ohlcv_v2a_sh`, and keep `technical_feature_version` as
  `technical_ohlcv_v2` unless the implementation milestone proves a new
  persisted feature version is needed. Current `technical_ohlcv_v2` feature
  snapshots already include the candidate short-horizon families below.
- Planned experiment cases must keep 5d and 10d horizons separate:

| Case ID | Profile | Strategy | `rebalance_every_days` | Purpose |
|---|---|---|---:|---|
| `cadence_only_current_v2a_5d` | `technical_ohlcv_v2` | `graph_aware_score_v2` | 5 | Isolate whether faster rebalancing alone helps current v2A. |
| `cadence_only_current_v2a_10d` | `technical_ohlcv_v2` | `graph_aware_score_v2` | 10 | Isolate whether a half-month cadence helps current v2A. |
| `v2a_sh_profile_5d` | `technical_ohlcv_v2a_sh` | `graph_aware_score_v2a_sh` | 5 | Evaluate true short-horizon scoring at weekly cadence. |
| `v2a_sh_profile_10d` | `technical_ohlcv_v2a_sh` | `graph_aware_score_v2a_sh` | 10 | Evaluate true short-horizon scoring at two-week cadence. |

- The cadence-only cases must be completed and reported before the true
  `v2A-SH` scoring profile is implemented, so any later result can separate
  cadence effects from scoring-design effects.
- Candidate short-horizon alpha features: `return_20d`, `return_63d`,
  `vol_adjusted_return_63d`, MACD, EMA spread, RSI, `20d` breakout, and `50d`
  breakout.
- Candidate short-horizon risk features: ATR and 20d volatility, represented by
  existing feature names such as `atr_percent_14` and `volatility_20`.
- Candidate short-horizon tradability features: turnover, traded value,
  `avg_traded_value_20`, `avg_traded_value_63`, `volume_z_score_20`, and
  `turnover_z_score_20`.
- Comparison protocol:
  - Use the same universe, initial capital, cost, slippage, warm-up, and yearly
    fold conventions as M97/M98 unless a later milestone states a narrow reason
    to change them.
  - Report each 5d and 10d case against canonical v1, current medium-horizon
    v2A, and cadence-matched v1/current-v2A baselines so faster turnover is not
    mistaken for a better short-horizon score.
  - Rank candidates with return, CAGR, Sharpe, Sortino, max drawdown, turnover,
    realized and unrealized P&L, closed win/loss economics, win rate, profit
    factor, rejected/trimmed/sizing-failure counts, and fold stability.
  - Require `rank.5d.rank_correlation`,
    `rank.5d.top_bottom_decile_spread`, and `rank.5d.hit_rate` in the first
    short-horizon specs. Keep `rank.21d.*` and `rank.63d.*` visible as
    regression diagnostics, not as the primary short-horizon objective.
  - Do not promote `v2A-SH` unless evidence improves realized trade quality and
    5d rank behavior versus cadence-matched current v2A without unacceptable
    drawdown, turnover, or sizing regressions versus canonical v1 and current
    medium-horizon v2A.
- Rank metric registry requirement: M99 exposes
  `rank.5d.rank_correlation`, `rank.5d.top_bottom_decile_spread`, and
  `rank.5d.hit_rate` through the parametric metric registry. The adapter
  already extracts `rank.<horizon>d.<field>` values from validation checks, and
  `scripts/validate_technical_v2.py` already emits 5d prediction checks.
- Non-goals for M99: exact `v2A-SH` feature weights, transform scales,
  eligibility gates, confidence weights, checked-in `v2A-SH` strategy config,
  checked-in short-horizon experiment specs, analyst/runtime wiring, UI
  visibility, operator commands for `v2A-SH`, and any promotion decision.
- Planned follow-up flat milestones after M100 closeout:

| Order | Milestone | Status | Plan | Purpose |
|---:|---|---|---|---|
| 101 | M101 | Done | `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md` | Add and run a cadence-only 5d/10d comparison for v1 and current medium-horizon v2A before implementing true v2A-SH scoring. |
| 102 | M102 | Planned | `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md` | Implement the opt-in `technical_ohlcv_v2a_sh` profile and `graph_aware_score_v2a_sh` strategy config without promotion. |
| 103 | M103 | Planned | `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md` | Add the true v2A-SH 5d/10d experiment spec and evidence report using 5d rank metrics and trade-quality diagnostics. |

Implementation closeout:

- Status: Done on 2026-06-26.
- Summary: Defined the `v2A-SH` contract as a separate opt-in
  short-horizon track with planned names `technical_ohlcv_v2a_sh` and
  `graph_aware_score_v2a_sh`, explicit 5d and 10d cadence-only and true-profile
  cases, short-horizon feature families, comparison protocol against v1,
  current medium-horizon v2A, and cadence-matched baselines, and planned M101
  cadence-only work before true profile implementation. Added
  `rank.5d.rank_correlation`, `rank.5d.top_bottom_decile_spread`, and
  `rank.5d.hit_rate` to the parametric metric registry without implementing the
  scoring profile, strategy config, or short-horizon specs.
- Verification: `uv run pytest tests/unit/test_parametric_experiments.py`;
  `make lint`; `make test`.
- Assumptions made: `technical_ohlcv_v2a_sh` and
  `graph_aware_score_v2a_sh` have no repo-local naming conflict; the existing
  `technical_ohlcv_v2` persisted feature suite is sufficient for the planned
  short-horizon feature families unless M102 proves otherwise; cadence-only
  5d/10d evidence should precede true `v2A-SH` implementation to avoid
  misattributing rebalancing effects to scoring changes; M99 should expose 5d
  rank metrics because validation already emits 5d prediction checks.
- Mocks created: None.
- Mocks used: None.
- Cleanup: Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries
  existed after the user's `# END MY CUSTOM ADDITION` marker, so no
  Taurus-specific approval migration was needed.

## M100 - Final Regression, Docs, And Handoff Closeout

Purpose: verify the redesigned experiment planning and specs end to end, refresh
operator docs, and close the M96-M100 sequence without promoting v2A or v2A-SH.

Instructions:

- Run focused regression for the parametric harness, metric registry, technical
  signal service, strategy ranking, graph backtesting, and progress surfaces
  touched by M96-M99.
- Dry-run every checked-in parametric spec:
  `v2a_smoke.yaml`, `v2a_risk_calibration.yaml`,
  `v2a_full_feature_sweep.yaml`, `v2a_medium_macro_sweep.yaml`, and
  `v2a_medium_sensitivity_sweep.yaml`.
- Update `docs/TAURUS_COMMANDS.md` with final operator guidance for staged
  dry-runs and non-dry-run execution.
- Update this plan, `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_HANDOFF.md`, and
  `docs/MILESTONE.md` with closeout status.
- Confirm generated `experiments/runs/` outputs remain ignored.
- Inspect approval cleanup according to the global rules.
- Do not run large non-dry-run macro or sensitivity experiments unless the user
  explicitly asks. A small smoke non-dry-run may be used only if needed to verify
  output compatibility.
- Do not promote v2A, make v2A-SH canonical, or change `make paper-loop-kite`
  defaults.

Expected code shape:

- Operators have clear commands and spec descriptions for staged medium-horizon
  exploration.
- The handoff names the next recommended action after closeout.

Acceptance criteria:

- Focused regression and dry-run verification pass.
- Tracker and handoff accurately reflect completed M96-M100 work.
- No generated run artifacts are tracked.
- v1 remains canonical, v2A remains opt-in, and v2A-SH remains planned/design-only
  unless separately implemented later.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py tests/unit/test_technical_signal_service.py tests/unit/test_strategy_ranking.py tests/unit/test_graph_backtesting.py tests/unit/test_progress.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_full_feature_sweep.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_macro_sweep.yaml
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_sensitivity_sweep.yaml
git check-ignore -v experiments/runs experiments/runs/example
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

Implementation closeout:

- Status: Done on 2026-06-28.
- Summary: Ran final focused regression and dry-run verification for every
  checked-in parametric spec, refreshed operator command guidance and
  handoff/tracker docs, confirmed generated run outputs remain ignored, and
  closed M96-M100 with v1 canonical, current v2A opt-in, and v2A-SH
  design-only.
- Verification: `uv run pytest tests/unit/test_parametric_experiments.py
  tests/unit/test_technical_signal_service.py tests/unit/test_strategy_ranking.py
  tests/unit/test_graph_backtesting.py tests/unit/test_progress.py` (75 passed);
  `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_smoke.yaml` (2 variants, 1 fold, 2 work
  units); `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_risk_calibration.yaml` (256 variants, 3
  folds, 768 work units); `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_full_feature_sweep.yaml` (512 variants,
  3 folds, 1536 work units); `PARAMETRIC_DRY_RUN=true make
  parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_medium_macro_sweep.yaml`
  (15 variants, 3 folds, 45 work units); `PARAMETRIC_DRY_RUN=true make
  parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_medium_sensitivity_sweep.yaml` (19
  variants, 3 folds, 57 work units); `git check-ignore -v experiments/runs/
  experiments/runs/example`.
- Assumptions made: M100 should remain verification/docs-only and should not run
  large non-dry-run experiments; dry-run expansion is sufficient to verify the
  checked-in spec shapes; v1 remains canonical, current v2A remains opt-in, and
  M101 should evaluate cadence-only 5d/10d behavior before any true v2A-SH
  implementation.
- Mocks created: None.
- Mocks used: None.
- Cleanup: Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries
  existed after the user's `# END MY CUSTOM ADDITION` marker, so no
  Taurus-specific approval migration was needed.

## M101 - Cadence-Only 5d/10d Comparison

Purpose: add and run a cadence-only comparison for canonical v1 and current
medium-horizon v2A at 5d and 10d rebalance cadence before implementing any true
`v2A-SH` scoring profile.

Instructions:

- Add a checked-in parametric spec for the cadence-only 5d and 10d cases using
  current `technical_ohlcv_v2` scoring and `graph_aware_score_v2` strategy
  wiring.
- Keep v1 canonical, current v2A opt-in, and `v2A-SH` design-only.
- Do not implement `technical_ohlcv_v2a_sh`,
  `graph_aware_score_v2a_sh`, M102, or M103.
- Include 5d rank metrics in the comparison and keep the existing 21d/63d rank
  metrics visible as regression diagnostics.
- Run a dry-run and a non-dry-run evidence pass with `PARAMETRIC_OUTPUT_ROOT`
  under `/tmp`.
- Write a durable report note with the cadence-only evidence.

Expected code shape:

- A small additive spec under `experiments/specs/` with two variants:
  `cadence_only_current_v2a_5d` and `cadence_only_current_v2a_10d`.
- Run-level comparison output keeps cadence-matched v1/current-v2A baselines
  distinguishable by backtest context.

Acceptance criteria:

- The checked-in spec expands to 2 variants, 3 yearly folds, and 6 work units.
- Non-dry-run evidence completes and reports the cadence-matched baselines.
- The evidence note states whether cadence alone improves current v2A enough to
  justify later true `v2A-SH` work.
- Current v1/v2A defaults and paper-loop behavior remain unchanged.

Verification:

```bash
uv run pytest tests/unit/test_parametric_experiments.py
PARAMETRIC_DRY_RUN=true make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_cadence_only_comparison.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-cadence-only-dryrun-20260628
PARAMETRIC_DRY_RUN=false make parametric-experiment EXPERIMENT_SPEC=experiments/specs/v2a_cadence_only_comparison.yaml PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-cadence-only-20260628
make lint
make test
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

Implementation closeout:

- Status: Done on 2026-06-28.
- Summary: Added `experiments/specs/v2a_cadence_only_comparison.yaml`, kept
  current v2A scoring unchanged, preserved v1/current-v2A defaults, separated
  run-level baseline rows by backtest context so 5d and 10d cadence-matched
  baselines remain visible, ran dry-run and non-dry-run cadence evidence, and
  wrote `docs/reports/parametric/v2a_cadence_only_comparison_20260628.md`.
  The evidence shows 10d current v2A beats 5d current v2A on aggregate return
  and Sharpe, but cadence alone does not fix negative realized P&L, profit
  factor below `1.0`, or negative 5d/21d rank behavior.
- Verification: `uv run pytest tests/unit/test_parametric_experiments.py` (23
  passed); `PARAMETRIC_DRY_RUN=true make parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_cadence_only_comparison.yaml
  PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-cadence-only-dryrun-20260628`
  (2 variants, 3 folds, 6 work units); `PARAMETRIC_DRY_RUN=false make
  parametric-experiment
  EXPERIMENT_SPEC=experiments/specs/v2a_cadence_only_comparison.yaml
  PARAMETRIC_OUTPUT_ROOT=/tmp/taurus-parametric-cadence-only-20260628`
  (`status=complete`, 2 variants, 6 work units, run
  `/tmp/taurus-parametric-cadence-only-20260628/v2a_cadence_only_comparison-f347009b48b1`);
  `make lint`; `make test` (480 passed, 1 skipped).
- Assumptions made: M101 should compare current medium-horizon v2A scoring at
  5d and 10d cadence only; generated variant rows intentionally duplicate
  current v2A scoring under cadence overrides; a run-level baseline de-dupe fix
  is necessary so backtest-context changes do not collapse cadence-matched
  baselines; M102/M103 remain unstarted unless explicitly authorized later.
- Mocks created: None.
- Mocks used: None.
- Cleanup: Inspected `/Users/adnaan/.codex/rules/default.rules`; no entries
  existed after the user's `# END MY CUSTOM ADDITION` marker, so no
  Taurus-specific approval migration was needed.

## Deferred Items

- Exact v2A-SH scoring weights and transform scales.
- v2A-SH implementation, strategy config, analyst wiring, UI visibility, and
  operator commands.
- Any promotion decision that changes canonical paper-loop defaults.
- ML-ready dataset export, feature-label storage, or training workflow.
