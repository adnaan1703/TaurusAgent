# V2A-SH Profile Comparison Report

Created: 2026-06-28

## Source Artifacts

This note summarizes the completed M103 true v2A-SH 5d/10d comparison.

- Run directory:
  `/tmp/taurus-parametric-v2a-sh-20260628/v2a_sh_profile_comparison-9d7813dfa9be`
- Manifest:
  `/tmp/taurus-parametric-v2a-sh-20260628/v2a_sh_profile_comparison-9d7813dfa9be/manifest.json`
- Comparison CSV:
  `/tmp/taurus-parametric-v2a-sh-20260628/v2a_sh_profile_comparison-9d7813dfa9be/comparison.csv`
- Spec:
  `experiments/specs/v2a_sh_profile_comparison.yaml`
- Cadence-only context:
  `docs/reports/parametric/v2a_cadence_only_comparison_20260628.md`

The run completed cleanly with 2 variants, 3 yearly folds, and 6 total work
units. All comparison rows had `validation_status=complete`. The checked-in
spec evaluated the M102 `technical_ohlcv_v2a_sh` profile through the opt-in
`graph_aware_score_v2a_sh` strategy config at 5d and 10d cadence. Run-level
baseline rows kept cadence-matched v1 and current-v2A comparisons visible.

## Executive Summary

Do not promote `v2A-SH` from this evidence. The 10d v2A-SH case improves
realized trade quality versus cadence-matched current v2A, but it still gives
up too much aggregate return and Sharpe, keeps negative 5d rank correlation,
and does not beat v1 on rank behavior. The 5d v2A-SH case is weaker overall.

- v2A-SH 5d underperforms cadence-matched current v2A on aggregate return,
  Sharpe, drawdown, turnover, win rate, and 5d/21d rank behavior. It improves
  realized P&L and profit factor versus current v2A, but not enough to offset
  the broader regressions.
- v2A-SH 10d is the healthier of the two true short-horizon cases. It improves
  realized P&L by about INR 9,356 and profit factor by about 0.623 versus
  cadence-matched current v2A, but trails current v2A by about 6.31 percentage
  points of return and about 0.274 Sharpe.
- v2A-SH 10d still has negative aggregate 5d rank correlation (`-0.016`) and
  negative 21d rank correlation (`-0.045`). That is not promotion-grade
  short-horizon evidence.
- v1 remains the canonical paper-loop default. Current v2A and v2A-SH remain
  opt-in.

## Aggregate Results

Aggregate means across the three yearly folds:

| Cadence/Profile | Return | Sharpe | Max DD | Turnover | Win Rate | Profit Factor | Realized P&L | Unrealized P&L | 5d Rank Corr | 21d Rank Corr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 5d | 0.62% | -0.059 | -17.72% | 26.709 | 40.97% | 1.063 | -4,751 | +5,368 | -0.002 | -0.008 |
| current v2A 5d | 5.02% | 0.100 | -18.07% | 23.369 | 38.00% | 0.753 | -9,406 | +14,421 | -0.023 | -0.052 |
| v2A-SH 5d | -1.92% | -0.303 | -18.88% | 34.360 | 37.09% | 0.995 | -5,460 | +3,536 | -0.033 | -0.067 |
| v1 10d | 5.05% | 0.229 | -17.73% | 23.302 | 48.41% | 1.305 | -834 | +5,889 | 0.031 | 0.010 |
| current v2A 10d | 8.72% | 0.213 | -17.72% | 16.218 | 35.51% | 0.740 | -9,834 | +18,557 | -0.023 | -0.035 |
| v2A-SH 10d | 2.41% | -0.060 | -18.01% | 23.924 | 41.80% | 1.363 | -478 | +2,891 | -0.016 | -0.045 |

Interpretation:

- At 5d, v2A-SH trails current v2A by about 6.94 percentage points of return
  and about 0.403 Sharpe, increases turnover by about 10.99, and worsens
  aggregate 5d rank correlation by about 0.010. It improves realized P&L by
  about INR 3,946 and profit factor by about 0.241 versus current v2A.
- At 10d, v2A-SH trails current v2A by about 6.31 percentage points of return
  and about 0.274 Sharpe, but improves realized P&L by about INR 9,356, win
  rate by about 6.29 percentage points, and profit factor by about 0.623.
- Against v1 10d, v2A-SH 10d improves realized P&L by about INR 356 and profit
  factor by about 0.059, but loses about 2.64 percentage points of return,
  about 0.290 Sharpe, and about 0.047 of 5d rank correlation.

## Fold Behavior

Fold-level v2A-SH returns, realized P&L, profit factor, and 5d rank correlation:

| Case | Fold | Return | Realized P&L | Profit Factor | 5d Rank Corr |
|---|---|---:|---:|---:|---:|
| v2A-SH 5d | fold 1 | 33.86% | +26,136 | 2.005 | -0.022 |
| v2A-SH 5d | fold 2 | -18.95% | -19,148 | 0.490 | -0.050 |
| v2A-SH 5d | fold 3 | -20.68% | -23,367 | 0.489 | -0.027 |
| v2A-SH 10d | fold 1 | 44.11% | +37,510 | 3.128 | -0.000 |
| v2A-SH 10d | fold 2 | -18.86% | -18,253 | 0.517 | -0.033 |
| v2A-SH 10d | fold 3 | -18.01% | -20,692 | 0.446 | -0.014 |

Fold 1 again carries the aggregate result. Both v2A-SH cases lose in folds 2
and 3, and all aggregate 5d rank correlations remain negative.

## Recommendation

Use M103 as true-profile evidence, not as promotion evidence.

- Keep `graph_aware_score_v1` canonical.
- Keep current `graph_aware_score_v2` opt-in.
- Keep `graph_aware_score_v2a_sh` opt-in and unpromoted.
- Do not change `make paper-loop-kite` defaults.
- Treat the current v2A-SH profile as a useful diagnostic branch for later
  tuning only if a future explicit milestone is authorized.
