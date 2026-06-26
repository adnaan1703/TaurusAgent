# V2A Medium Sensitivity Sweep Report

Created: 2026-06-26

## Source Artifacts

This note summarizes the completed M98 medium-horizon sensitivity sweep.

- Run directory:
  `/tmp/taurus-parametric-sensitivity/v2a_medium_sensitivity_sweep-4de7309fd8ac`
- Manifest:
  `/tmp/taurus-parametric-sensitivity/v2a_medium_sensitivity_sweep-4de7309fd8ac/manifest.json`
- Comparison CSV:
  `/tmp/taurus-parametric-sensitivity/v2a_medium_sensitivity_sweep-4de7309fd8ac/comparison.csv`
- Spec:
  `experiments/specs/v2a_medium_sensitivity_sweep.yaml`

The run completed cleanly with 19 variants, 3 yearly folds, and 57 total work
units. All comparison rows had `validation_status=complete`.

## Executive Summary

Do not promote any v2A sensitivity candidate from this run. The sweep was useful
diagnostic evidence, but it did not fix the core medium-horizon v2A failure
mode.

- Only 2 of 19 cases improved both aggregate return and Sharpe versus current
  v2A.
- No case improved realized P&L versus current v2A.
- No case had positive realized P&L.
- No case had profit factor above `1.0`.
- No case had positive aggregate 21d rank correlation.
- Most one-off feature-weight and transform-scale changes were effectively
  inert at the full-system level.
- v1 remains canonical; v2A remains opt-in.

## Baselines And Key Cases

Aggregate means across the three yearly folds:

| Profile | Return | Sharpe | Max DD | Win Rate | Profit Factor | Realized P&L | Unrealized P&L | 21d Rank Corr | 63d Rank Corr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | 10.20% | 0.646 | -13.67% | 54.79% | 1.323 | +3,090 | +7,111 | +0.0320 | +0.0033 |
| current v2A | 19.45% | 0.801 | -13.39% | 37.62% | 0.713 | -5,605 | +25,056 | -0.0198 | +0.0008 |
| `alpha_var252_weight_high` | 20.42% | 0.869 | -13.03% | 36.24% | 0.676 | -5,769 | +26,190 | -0.0194 | +0.0039 |
| `alpha_return63_weight_low` | 19.53% | 0.803 | -13.72% | 35.07% | 0.664 | -6,228 | +25,758 | -0.0178 | +0.0044 |
| current-equivalent plateau | 19.45% | 0.801 | -13.39% | 37.62% | 0.713 | -5,605 | +25,056 | about -0.0200 to -0.0187 | about +0.0003 to +0.0037 |

Interpretation:

- `alpha_var252_weight_high` is the best aggregate-return case. It improved
  current v2A by about 0.97 percentage points of return and about 0.069 Sharpe,
  with slightly better drawdown.
- That improvement is not a clean upgrade because realized P&L worsened by
  about INR 164 versus current v2A, profit factor fell, win rate fell, and 21d
  rank correlation stayed negative.
- `alpha_return63_weight_low` was the best aggregate 21d-rank case, but its
  21d rank correlation still remained negative. It also worsened realized P&L,
  profit factor, win rate, and drawdown versus current v2A.
- The v2A-style return edge is still carried by open mark-to-market gains, not
  by better closed-trade economics.

## Sensitivity Read

Counts across the 19 aggregate sensitivity cases:

| Test Versus Current v2A | Cases Passing |
|---|---:|
| Higher aggregate return | 2 / 19 |
| Higher Sharpe | 2 / 19 |
| Better max drawdown | 1 / 19 |
| Higher realized P&L | 0 / 19 |
| Positive realized P&L | 0 / 19 |
| Higher profit factor | 0 / 19 |
| Profit factor above 1.0 | 0 / 19 |
| Higher 21d rank correlation | 6 / 19 |
| Positive 21d rank correlation | 0 / 19 |

Case-level read:

- `alpha_weights.vol_adjusted_return_252d = 0.16` is the only meaningful
  aggregate-return improvement, but it does not improve trade quality.
- `alpha_weights.return_63d = 0.08` is the cleanest 21d-rank improvement, but it
  is too small and still negative.
- Lowering `alpha_weights.vol_adjusted_return_126d`,
  `alpha_weights.return_126d`, or `alpha_weights.vol_adjusted_return_252d`
  worsened aggregate return and Sharpe.
- Most transform-scale, risk-weight, and tradability changes produced identical
  full-system return, Sharpe, realized P&L, and profit factor to current v2A.
  Their only movement was tiny rank-metric drift.

## Fold Behavior

Representative fold-level returns:

| Profile | Fold 1 Return | Fold 2 Return | Fold 3 Return | Fold 1 21d Corr | Fold 2 21d Corr | Fold 3 21d Corr |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 37.50% | -5.47% | -1.42% | +0.1831 | -0.0130 | -0.0741 |
| current v2A | 71.60% | -6.76% | -6.49% | +0.0571 | -0.0638 | -0.0529 |
| `alpha_var252_weight_high` | 71.60% | -5.35% | -4.99% | +0.0573 | -0.0612 | -0.0544 |
| `alpha_return63_weight_low` | 71.39% | -5.35% | -7.45% | +0.0609 | -0.0613 | -0.0530 |

Fold 1 remains the main driver of v2A-style aggregate return. The best return
case trims losses in folds 2 and 3 versus current v2A, but fold 3 still loses
materially more than v1. None of the sensitivity cases turned the recent-window
weakness into a promotion-grade profile.

Fold-level `promotion_decision` should also not be overread: fold 1 showed
`promote` for generated variants, while folds 2 and 3 were `keep_opt_in`.
Aggregate rows do not carry a promotion decision, and the aggregate evidence
does not justify changing defaults.

## Recommendation

Use this run as negative-selection evidence for the current medium-horizon v2A
tuning path.

- Do not promote current v2A or any M98 candidate.
- Do not run another broad medium-horizon feature-weight sweep without a new
  hypothesis that specifically targets realized trade quality and rank behavior.
- Treat `alpha_var252_weight_high` as a return/Sharpe diagnostic case only, not
  a preferred candidate.
- Treat `alpha_return63_weight_low` as a weak rank-behavior diagnostic case only,
  not a rank fix.
- Keep v1 canonical and v2A opt-in.
- Proceed to the M99 short-horizon design contract before spending more effort
  on medium-horizon tuning.

Straight read: M98 says the medium-horizon v2A issue is structural enough that
one-off feature-weight and transform-scale tweaks are not solving it. The next
useful question is whether a separately designed short-horizon profile, plus a
cadence-only comparison, can address the realized trade-quality and rank-timing
problem.
