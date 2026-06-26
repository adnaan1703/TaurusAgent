# V2A Experiment Redesign Handoff

Last updated: 2026-06-26

## Current Status

- Current milestone: None.
- Last completed milestone: M97 Medium-Horizon Macro Sweep Spec.
- Planning completed:
  `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md`.
- Implementation state: M97 is complete. The parametric harness supports
  optional `variants.axes` grouped overrides crossed with existing
  `variants.matrix` combinations; selected axis metadata appears in dry-run
  rows, comparison CSV rows, and variant manifests. The checked-in
  `v2a_medium_macro_sweep.yaml` macro spec crosses five family-weight trios with
  three paired portfolio-size choices, expands to 15 variants and 45 default
  yearly work units, and requests realized/unrealized plus closed-trade
  economics diagnostics. v1 remains canonical and v2A remains opt-in.
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
- Next recommended milestone: M98 Medium-Horizon Sensitivity Sweep Spec.
- Canonical runtime state: `graph_aware_score_v1` remains the default
  `make paper-loop-kite` strategy. `graph_aware_score_v2` remains opt-in.
  `v2A-SH` is design-planned only and must not be treated as implemented.

## Required Reading For Every Worker Thread

- `docs/TAURUS_V2A_EXPERIMENT_REDESIGN_PLAN.md`
- `docs/MILESTONE.md`
- `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_PLAN.md`
- `docs/TAURUS_PARAMETRIC_EXPERIMENT_HARNESS_HANDOFF.md`
- `docs/TAURUS_COMMANDS.md`
- `docs/reports/parametric/v2a_full_feature_sweep_20260626.md`
- `docs/reports/parametric/v2a_medium_macro_sweep_20260626.md`
- `experiments/parametric/spec.py`
- `experiments/parametric/expansion.py`
- `experiments/parametric/adapters.py`
- `experiments/parametric/metrics.py`
- `experiments/parametric/technical_validation_v2a.py`
- `experiments/specs/v2a_medium_macro_sweep.yaml`
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
  diagnostics. Planned.
- M99: v2A-SH short-horizon design contract. Planned.
- M100: final regression, docs, and handoff closeout. Planned.

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
- The medium sensitivity sweep should be sensitivity-style, not a full factorial
  of all suggested feature values. It should make inert knobs and tied outcomes
  easy to prune from future sweeps.
- `portfolio_breadth` and `max_open_positions` remain separate production
  concepts, but experiments should pair them as equal portfolio-size controls.
- `v2A-SH` exact scoring weights and transform scales are deferred until its
  design contract or a later implementation sequence.
