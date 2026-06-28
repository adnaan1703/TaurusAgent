# V2A Cadence-Only Operator Rerun Note

Created: 2026-06-28

## Source Artifacts

This note captures the operator rerun analysis for the M101 cadence-only
comparison.

- Run directory:
  `/tmp/taurus-parametric-cadence-only/v2a_cadence_only_comparison-f347009b48b1`
- Manifest:
  `/tmp/taurus-parametric-cadence-only/v2a_cadence_only_comparison-f347009b48b1/manifest.json`
- Comparison CSV:
  `/tmp/taurus-parametric-cadence-only/v2a_cadence_only_comparison-f347009b48b1/comparison.csv`
- Spec:
  `experiments/specs/v2a_cadence_only_comparison.yaml`

The run completed with `status=complete`, 2 variants, 3 folds, 6 work units, and
20 comparison rows. All rows had `validation_status=complete`; fold-level
promotion decisions were `keep_opt_in`.

## Summary

Cadence alone is not enough to justify promotion or to stand in for a true
`v2A-SH` profile. The 10d current-v2A cadence improves aggregate return and
Sharpe versus the 5d current-v2A cadence, but both current-v2A cadence cases
still fail the trade-quality and short-horizon rank checks that matter for the
next design step.

| Profile | Return | Sharpe | Profit Factor | Realized P&L | 5d Rank Corr | 21d Rank Corr |
|---|---:|---:|---:|---:|---:|---:|
| v1 5d | 0.62% | -0.059 | 1.063 | -4,751 | -0.002 | -0.008 |
| current v2A 5d | 5.02% | 0.100 | 0.753 | -9,406 | -0.023 | -0.052 |
| v1 10d | 5.05% | 0.229 | 1.305 | -834 | 0.031 | 0.010 |
| current v2A 10d | 8.72% | 0.213 | 0.740 | -9,834 | -0.023 | -0.035 |

## Readout

- Current v2A 10d beats current v2A 5d on aggregate return: `8.72%` versus
  `5.02%`.
- Current v2A 10d has lower turnover than current v2A 5d: `16.22` versus
  `23.37`.
- Current v2A 10d still has worse realized P&L than current v2A 5d:
  `-9,834` versus `-9,406`.
- Both current-v2A cadence cases have profit factor below `1.0`.
- Both current-v2A cadence cases have negative aggregate 5d and 21d rank
  correlation.
- v1 10d is healthier on trade quality than current v2A 10d, with better
  realized P&L, win rate, profit factor, and 5d/21d rank behavior.

The `variant_aggregate` rows correctly show `delta_vs_current_v2a = 0.0`
because the generated variants are cadence-only current-v2A profiles compared
against cadence-matched current-v2A baselines.

## Recommendation

- Do not promote any cadence-only result.
- Keep `graph_aware_score_v1` canonical.
- Keep current `graph_aware_score_v2` opt-in.
- Keep `v2A-SH` design-only until M102 explicitly implements a separate opt-in
  scoring profile and strategy config.
- Proceed to M102 only if the objective is to build a true short-horizon profile
  that targets positive realized P&L, profit factor above `1.0`, improved win
  rate, positive 5d rank behavior, and acceptable drawdown/turnover.
