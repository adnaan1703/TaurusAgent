# V2A-SH Evidence Summary Note

Created: 2026-06-28

## Source Reports

- M101 cadence-only comparison:
  `docs/reports/parametric/v2a_cadence_only_comparison_20260628.md`
- M103 true v2A-SH profile comparison:
  `docs/reports/parametric/v2a_sh_profile_comparison_20260628.md`

## What Was Already Run

M101 tested current medium-horizon v2A scoring at faster rebalance cadence
without changing the scoring profile:

- Spec: `experiments/specs/v2a_cadence_only_comparison.yaml`
- Run:
  `/tmp/taurus-parametric-cadence-only-20260628/v2a_cadence_only_comparison-f347009b48b1`
- Shape: 2 variants, 3 yearly folds, 6 work units
- Status: complete

M103 tested the true M102 v2A-SH scoring profile at 5d and 10d cadence:

- Spec: `experiments/specs/v2a_sh_profile_comparison.yaml`
- Run:
  `/tmp/taurus-parametric-v2a-sh-20260628/v2a_sh_profile_comparison-9d7813dfa9be`
- Shape: 2 variants, 3 yearly folds, 6 work units
- Status: complete

## Main Readout

Do not promote v2A-SH from this evidence.

The cadence-only M101 run showed that faster rebalancing alone does not fix
current v2A's realized trade quality or short-horizon rank behavior. Current
v2A at 10d beats current v2A at 5d on aggregate return and Sharpe, but both
current-v2A cadence cases keep negative realized P&L, profit factor below 1.0,
and negative aggregate 5d/21d rank correlation.

The true-profile M103 run showed that v2A-SH 10d is more interesting than
v2A-SH 5d, but still not promotion-grade. v2A-SH 10d improves realized P&L and
profit factor versus cadence-matched current v2A, but gives up too much
aggregate return and Sharpe and still has negative 5d rank correlation.

## Key Aggregate Metrics

| Profile | Return | Sharpe | Profit Factor | Realized P&L | 5d Rank Corr |
|---|---:|---:|---:|---:|---:|
| current v2A 5d | 5.02% | 0.100 | 0.753 | -9,406 | -0.023 |
| v2A-SH 5d | -1.92% | -0.303 | 0.995 | -5,460 | -0.033 |
| current v2A 10d | 8.72% | 0.213 | 0.740 | -9,834 | -0.023 |
| v2A-SH 10d | 2.41% | -0.060 | 1.363 | -478 | -0.016 |

## Interpretation

- v2A-SH 5d is weaker overall and should not be pursued as-is.
- v2A-SH 10d improves closed-trade economics versus current v2A 10d, but its
  return, Sharpe, and rank behavior are not strong enough.
- Fold 1 carries the aggregate result again; both v2A-SH cases lose in folds 2
  and 3.
- Negative 5d rank correlation is the key blocker for calling this a good
  short-horizon signal.

## Decision

- Keep `graph_aware_score_v1` canonical.
- Keep `graph_aware_score_v2` opt-in.
- Keep `graph_aware_score_v2a_sh` opt-in and unpromoted.
- Do not change `make paper-loop-kite` defaults.
- Treat v2A-SH as a diagnostic branch for a future explicit tuning/research
  milestone, not as a promotion candidate.
