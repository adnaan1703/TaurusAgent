# V2A Full-Feature Sweep Report

Created: 2026-06-26

## Source Artifacts

This note summarizes the completed broad overnight v2A full-feature sweep.

- Run directory:
  `/tmp/taurus-parametric-risk/v2a_full_feature_sweep-ff23bcf5745e`
- Manifest:
  `/tmp/taurus-parametric-risk/v2a_full_feature_sweep-ff23bcf5745e/manifest.json`
- Comparison CSV:
  `/tmp/taurus-parametric-risk/v2a_full_feature_sweep-ff23bcf5745e/comparison.csv`
- Spec:
  `experiments/specs/v2a_full_feature_sweep.yaml`

The run completed cleanly with 512 variants, 3 yearly folds, and 1536 total
variant work units. The comparison CSV contains 2054 data rows: 1542 fold rows
and 512 aggregate variant rows.

## Executive Summary

Do not promote any v2A full-feature candidate from this run. The sweep is useful
diagnostic evidence, but it did not produce a promotion-grade replacement for
canonical v1.

- The strongest candidate set improved aggregate return and Sharpe slightly
  versus current v2A.
- The top return and top Sharpe results were tied across 96 variants, which
  means the broad sweep exposed a plateau rather than a precise parameter
  winner.
- No variant fixed aggregate 21d rank correlation. The best aggregate 21d rank
  correlation remained negative at `-0.0178`.
- v1 still had better average closed-trade quality in the experiment readout:
  positive realized P&L and stronger win rate, while current v2A and the tied
  top candidates were carried by open mark-to-market gains and had negative
  realized P&L.
- The original full-feature CSV did not yet include the newer
  realized/unrealized and closed-trade economics columns; those diagnostics were
  added later for the M97/M98 sweep design.
- v1 remains canonical; v2A remains opt-in.

## Baselines And Top Aggregate Candidates

Aggregate means across the three yearly folds:

| Profile | Return | Sharpe | Max DD | Win Rate | 21d Rank Corr | 63d Rank Corr |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 10.20% | 0.646 | -13.67% | 54.79% | +0.0320 | +0.0033 |
| current v2A | 19.45% | 0.801 | -13.39% | 37.62% | -0.0198 | +0.0008 |
| tied top return/Sharpe variants | 20.49% | 0.877 | -12.76% | 35.07% | -0.0191 to -0.0200 | +0.0022 to +0.0030 |
| best 21d-rank variants | 19.53% | 0.803 | -13.72% | 35.07% | -0.0178 | +0.0044 |
| best 63d-rank variants | 19.60% | 0.804 | -13.72% | 37.04% | -0.0179 | +0.0056 |

Interpretation:

- The top return/Sharpe plateau beat current v2A by about 1.04 percentage points
  of aggregate return and about 0.077 Sharpe.
- That edge is not enough for promotion because 21d rank behavior stayed
  negative and the experiment readout showed weak realized trade quality.
- The best rank-correlation candidates were only marginally different from
  current v2A and still failed the non-negative 21d-rank bar.

## Fold Behavior

Representative aggregate top-return candidate rows had this fold profile:

| Profile | Fold 1 Return | Fold 2 Return | Fold 3 Return | Fold 1 21d Corr | Fold 2 21d Corr | Fold 3 21d Corr |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 37.50% | -5.47% | -1.42% | +0.1831 | -0.0130 | -0.0741 |
| current v2A | 71.60% | -6.76% | -6.49% | +0.0571 | -0.0638 | -0.0529 |
| top variant example | 71.39% | -5.35% | -4.57% | +0.0581 | -0.0626 | -0.0544 |

The top full-feature variants mostly improved current v2A by trimming losses in
folds 2 and 3, but fold 3 still trailed v1 materially. Fold 1 remained the
primary driver of v2A-style aggregate return.

## Recommendation

Use this run as broad negative-selection evidence, not as a promotion source.

- Keep `experiments/specs/v2a_full_feature_sweep.yaml` available as the
  deliberate overnight broad template.
- Do not promote current v2A or any generated candidate from this run.
- Treat the tied top variants as a return/Sharpe plateau, not as a meaningful
  winner.
- Continue M97/M98-style analysis with explicit realized/unrealized P&L,
  closed-trade economics, profit factor, fold consistency, and 21d rank
  behavior visible in the comparison output.
- Prefer focused medium-horizon sensitivity work over another broad full-feature
  sweep unless there is a specific new hypothesis to test.
