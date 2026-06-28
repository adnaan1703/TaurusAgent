# V2A Cadence-Only Comparison Report

Created: 2026-06-28

## Source Artifacts

This note summarizes the completed M101 cadence-only 5d/10d comparison.

- Run directory:
  `/tmp/taurus-parametric-cadence-only-20260628/v2a_cadence_only_comparison-f347009b48b1`
- Manifest:
  `/tmp/taurus-parametric-cadence-only-20260628/v2a_cadence_only_comparison-f347009b48b1/manifest.json`
- Comparison CSV:
  `/tmp/taurus-parametric-cadence-only-20260628/v2a_cadence_only_comparison-f347009b48b1/comparison.csv`
- Spec:
  `experiments/specs/v2a_cadence_only_comparison.yaml`

The run completed cleanly with 2 variants, 3 yearly folds, and 6 total work
units. All comparison rows had `validation_status=complete`. The run-level CSV
kept baseline rows separated by backtest context so 5d and 10d cadence-matched
v1/current-v2A baselines are visible independently.

## Executive Summary

Do not treat faster cadence alone as a v2A-SH substitute. The cadence-only run
is useful prerequisite evidence, but it does not fix current v2A's realized
trade-quality or short-horizon rank behavior.

- Current v2A at 10d beats current v2A at 5d on aggregate return, Sharpe,
  drawdown, turnover, 21d rank correlation, and unrealized P&L.
- Neither current-v2A cadence has positive realized P&L, a profit factor above
  `1.0`, or positive aggregate 5d or 21d rank correlation.
- Current v2A beats cadence-matched v1 on total return at both 5d and 10d, but
  loses to v1 on realized P&L, win rate, profit factor, and 5d/21d rank
  correlation.
- v1 at 10d is materially healthier than v1 at 5d: it has higher return,
  positive Sharpe, a profit factor above `1.0`, less negative realized P&L, and
  positive aggregate 5d and 21d rank correlation.
- The next true v2A-SH work should remain opt-in and separate from current v2A.
  Cadence alone is not enough evidence to promote any short-horizon default.

## Aggregate Results

Aggregate means across the three yearly folds:

| Cadence/Profile | Return | Sharpe | Max DD | Turnover | Win Rate | Profit Factor | Realized P&L | Unrealized P&L | 5d Rank Corr | 21d Rank Corr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 5d | 0.62% | -0.059 | -17.72% | 26.709 | 40.97% | 1.063 | -4,751 | +5,368 | -0.002 | -0.008 |
| current v2A 5d | 5.02% | 0.100 | -18.07% | 23.369 | 38.00% | 0.753 | -9,406 | +14,421 | -0.023 | -0.052 |
| v1 10d | 5.05% | 0.229 | -17.73% | 23.302 | 48.41% | 1.305 | -834 | +5,889 | 0.031 | 0.010 |
| current v2A 10d | 8.72% | 0.213 | -17.72% | 16.218 | 35.51% | 0.740 | -9,834 | +18,557 | -0.023 | -0.035 |

Interpretation:

- Current v2A 10d improved current v2A 5d by about 3.71 percentage points of
  aggregate return and about 0.114 Sharpe, while cutting turnover by about 7.15.
- Current v2A 10d still worsened realized P&L by about INR 428 versus current
  v2A 5d and remained negative on 5d rank correlation.
- At 5d, current v2A beat cadence-matched v1 by about 4.40 percentage points of
  return but worsened realized P&L by about INR 4,655 and had worse 5d and 21d
  rank correlation.
- At 10d, current v2A beat cadence-matched v1 by about 3.67 percentage points of
  return but worsened realized P&L by about INR 8,999, profit factor by about
  0.565, win rate by about 12.89 percentage points, and 5d rank correlation by
  about 0.054.

## Fold Behavior

Fold-level returns and realized P&L:

| Profile | Fold 1 Return | Fold 2 Return | Fold 3 Return | Fold 1 Realized | Fold 2 Realized | Fold 3 Realized |
|---|---:|---:|---:|---:|---:|---:|
| v1 5d | 34.68% | -13.88% | -18.94% | +22,424 | -14,690 | -21,986 |
| current v2A 5d | 45.37% | -17.37% | -12.95% | +6,311 | -18,201 | -16,328 |
| v1 10d | 43.76% | -13.23% | -15.36% | +32,486 | -16,090 | -18,899 |
| current v2A 10d | 58.21% | -18.01% | -14.03% | +5,799 | -18,788 | -16,512 |

Fold 1 is again the main source of current-v2A aggregate return. Faster cadence
does not solve the later-fold weakness: both current-v2A cadence cases lose in
folds 2 and 3, and both keep negative aggregate realized P&L.

## Recommendation

Use M101 as cadence-isolation evidence only.

- Keep `graph_aware_score_v1` canonical.
- Keep current `graph_aware_score_v2` opt-in.
- Keep `v2A-SH` design-only until a separate milestone implements its opt-in
  scoring profile and strategy config.
- Do not promote or infer a short-horizon default from cadence alone.
- If M102 is later authorized, implement the true v2A-SH profile as a separate
  opt-in scoring design, then evaluate it against the cadence-matched M101
  baselines.
