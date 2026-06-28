# V2A Experiment Redesign Handoff

Last updated: 2026-06-28

## Current Status

- Current milestone: None. The user explicitly requested stopping the chain
  after M103.
- Last completed milestone: M103 True V2A-SH 5d/10d Experiment Spec And
  Evidence Report.
- Planning completed:
  `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md`.
- Implementation state: M99 is complete. The parametric harness supports
  optional `variants.axes` grouped overrides crossed with existing
  `variants.matrix` combinations; selected axis metadata appears in dry-run
  rows, comparison CSV rows, and variant manifests. The checked-in
  `v2a_medium_macro_sweep.yaml` macro spec crosses five family-weight trios with
  three paired portfolio-size choices, expands to 15 variants and 45 default
  yearly work units, and requests realized/unrealized plus closed-trade
  economics diagnostics. The checked-in
  `v2a_medium_sensitivity_sweep.yaml` sensitivity spec keeps current family
  weights, `portfolio_breadth=5`, `max_open_positions=5`, and 21-day
  rebalancing fixed, then runs 19 one-case `sensitivity_case` variants across
  57 default yearly work units with the same trade-quality and rank
  diagnostics. M99 defined `v2A-SH` as a separate opt-in short-horizon design
  track with planned names `technical_ohlcv_v2a_sh` and
  `graph_aware_score_v2a_sh`, separate 5d and 10d cases, a cadence-only
  comparison prerequisite, short-horizon feature families, and a comparison
  protocol against v1, current medium-horizon v2A, and cadence-matched
  baselines. The parametric metric registry now accepts
  `rank.5d.rank_correlation`, `rank.5d.top_bottom_decile_spread`, and
  `rank.5d.hit_rate` by reusing 5d prediction checks already emitted by
  validation reports. M100 closed the sequence by passing focused regression,
  dry-running all checked-in parametric specs, refreshing operator guidance and
  tracker/handoff docs, confirming `experiments/runs/` remains ignored, and
  completing approval cleanup. M101 added
  `experiments/specs/v2a_cadence_only_comparison.yaml`, separated run-level
  cadence-matched baseline rows by backtest context, completed the 5d/10d
  non-dry-run comparison under
  `/tmp/taurus-parametric-cadence-only-20260628/v2a_cadence_only_comparison-f347009b48b1`,
  and wrote
  `docs/reports/parametric/v2a_cadence_only_comparison_20260628.md`. The M101
  evidence showed 10d current v2A beats 5d current v2A on aggregate return and
  Sharpe, but cadence alone does not fix negative realized P&L, profit factor
  below `1.0`, or negative 5d/21d rank behavior. M102 then added the opt-in
  `technical_ohlcv_v2a_sh` scoring profile, `graph_aware_score_v2a_sh` strategy
  config, graph-aware strategy/analyst/validation/backtest/paper-run wiring,
  and active-sleeve mapping for explicit paper trials while reusing
  `technical_ohlcv_v2` feature snapshots. v1 remains canonical, current v2A
  remains opt-in, and v2A-SH remains unpromoted. M103 then added
  `experiments/specs/v2a_sh_profile_comparison.yaml`, extended the parametric
  adapter with a closed `strategy.profile` selector for `current_v2a` and
  `v2a_sh`, completed the true v2A-SH 5d/10d evidence run under
  `/tmp/taurus-parametric-v2a-sh-20260628/v2a_sh_profile_comparison-9d7813dfa9be`,
  and wrote
  `docs/reports/parametric/v2a_sh_profile_comparison_20260628.md`. The M103
  evidence is mixed but not promotion-grade: v2A-SH 10d improves realized P&L
  and profit factor versus cadence-matched current v2A, but trails current v2A
  on aggregate return and Sharpe and keeps negative 5d rank correlation.
- M97 macro sweep evidence is recorded in
  `docs/reports/parametric/v2a_medium_macro_sweep_20260626.md`. The completed
  run lives under
  `/tmp/taurus-parametric-macro-20260626-170848/v2a_medium_macro_sweep-fc0a939b1d44`.
  It found that `size_5` is the best portfolio-size setting, no macro candidate
  should be promoted, and M98 should focus on realized trade quality and 21d
  rank behavior rather than broadening portfolio size.
- Full-feature sweep evidence:
  `/tmp/taurus-parametric-risk/v2a_full_feature_sweep-ff23bcf5745e` completed
  512 variants across three yearly folds. The durable report note is
  `docs/reports/parametric/v2a_full_feature_sweep_20260626.md`. The tied top
  candidates improved aggregate return and Sharpe slightly versus current v2A,
  but did not fix negative aggregate 21d rank correlation. v1 kept better
  closed-trade quality and positive realized P&L; current v2A and the top
  candidates were driven by open mark-to-market gains and had negative realized
  P&L. Do not promote v2A or any candidate from that run.
- Latest M98 sensitivity evidence is recorded in
  `docs/reports/parametric/v2a_medium_sensitivity_sweep_20260626.md`. It found
  that no one-off medium-horizon feature-weight or transform-scale case fixed
  realized P&L, profit factor, or 21d rank behavior; do not promote current v2A
  or any M98 candidate.
- Next planned milestone: None in this chain. The user explicitly requested
  stopping after M103 and no successor thread should be created from this
  handoff.
- Canonical runtime state: `graph_aware_score_v1` remains the default
  `make paper-loop-kite` strategy. `graph_aware_score_v2` and
  `graph_aware_score_v2a_sh` remain opt-in. `v2A-SH` is implemented only as an
  unpromoted profile/config with completed M103 evidence that does not justify
  promotion.

## Required Reading For Every Worker Thread

- `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md`
- `docs/MILESTONE.md`
- `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_PLAN.md`
- `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_HANDOFF.md`
- `docs/TAURUS_COMMANDS.md`
- `docs/reports/parametric/v2a_full_feature_sweep_20260626.md`
- `docs/reports/parametric/v2a_medium_macro_sweep_20260626.md`
- `docs/reports/parametric/v2a_medium_sensitivity_sweep_20260626.md`
- `docs/reports/parametric/v2a_cadence_only_comparison_20260628.md`
- `docs/reports/parametric/v2a_sh_profile_comparison_20260628.md`
- `configs/strategies/graph_aware_score_v2a_sh.yaml`
- `experiments/parametric/spec.py`
- `experiments/parametric/expansion.py`
- `experiments/parametric/adapters.py`
- `experiments/parametric/metrics.py`
- `experiments/parametric/technical_validation_v2a.py`
- `experiments/specs/v2a_medium_macro_sweep.yaml`
- `experiments/specs/v2a_medium_sensitivity_sweep.yaml`
- `experiments/specs/v2a_cadence_only_comparison.yaml`
- `experiments/specs/v2a_sh_profile_comparison.yaml`
- `packages/taurus_core/features/technical_params.py`
- `packages/taurus_core/features/technical_signal.py`
- `packages/taurus_core/strategies/graph_aware.py`
- `scripts/validate_technical_v2.py`
- `tests/unit/test_parametric_experiments.py`
- `tests/unit/test_technical_validation_contracts.py`

## Worker Thread Instructions

- Start by reading the assigned milestone section in
  `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md`.
- Implement only the assigned milestone if the user asks that worker thread to
  execute. If the user only asks for milestone-specific planning, do not edit
  files.
- Do not begin later milestones, scaffold future milestones, or make
  compatibility changes for later milestones unless the current milestone
  explicitly requires them.
- Preserve all existing checked-in specs unless the assigned milestone names a
  specific additive or compatibility-preserving change.
- Keep current v1 behavior canonical and current v2A opt-in.
- Keep v2A-SH separate from current medium-horizon v2A. Do not make it canonical
  or implement its scoring before the assigned milestone requires it.
- Keep experiment specs declarative and allowlisted. Do not add arbitrary Python
  callbacks or expression execution from YAML.
- Do not run large non-dry-run experiments unless the user explicitly asks.
- Do not commit unless the user explicitly asks.

## Milestone Status

The source of truth is the tracker table in `docs/MILESTONE.md`. The planned
sequence is:

- M96: grouped experiment axes. Done.
- M97: medium-horizon macro sweep spec plus additive trade-quality diagnostics.
  Done.
- M98: medium-horizon sensitivity sweep spec using the same trade-quality
  diagnostics. Done.
- M99: v2A-SH short-horizon design contract. Done.
- M100: final regression, docs, and handoff closeout. Done.
- M101: cadence-only 5d/10d comparison before true v2A-SH implementation.
  Done.
- M102: opt-in v2A-SH scoring profile and strategy config implementation.
  Done.
- M103: true v2A-SH 5d/10d experiment spec and evidence report. Done.

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

- M96-M100 are planning and implementation for offline paper/backtest
  experimentation only.
- `v2a_full_feature_sweep.yaml` should remain available as the existing
  deliberate overnight template.
- The medium macro sweep should test five family-weight trios crossed with three
  paired portfolio sizes, and its outputs should distinguish realized
  closed-trade quality from open mark-to-market gains.
- The medium sensitivity sweep is checked in as a sensitivity-style case list,
  not a full factorial of all suggested feature values. It should make inert
  knobs and tied outcomes easy to prune from future sweeps after a deliberate
  non-dry-run execution.
- `portfolio_breadth` and `max_open_positions` remain separate production
  concepts, but experiments should pair them as equal portfolio-size controls.
- `v2A-SH` scoring weights and transform scales now exist only for the opt-in
  M102 profile. M103 evidence is complete and does not justify promotion.
- `v2A-SH` must not be treated as current v2A with only faster rebalancing.
  M101 completed the cadence-only 5d and 10d comparison; any true short-horizon
  follow-up tuning or promotion must be authorized in a separate later
  milestone.
