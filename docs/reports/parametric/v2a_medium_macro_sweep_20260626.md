# V2A Medium Macro Sweep Report

Created: 2026-06-26

## Source Artifacts

This note summarizes the completed M97 medium-horizon macro sweep.

- Run directory:
  `/tmp/taurus-parametric-macro-20260626-170848/v2a_medium_macro_sweep-fc0a939b1d44`
- Manifest:
  `/tmp/taurus-parametric-macro-20260626-170848/v2a_medium_macro_sweep-fc0a939b1d44/manifest.json`
- Comparison CSV:
  `/tmp/taurus-parametric-macro-20260626-170848/v2a_medium_macro_sweep-fc0a939b1d44/comparison.csv`
- Spec:
  `experiments/specs/v2a_medium_macro_sweep.yaml`

The run completed cleanly with 15 variants, 3 folds, and 45 total work units.
All comparison rows had `validation_status=complete`.

## Executive Summary

Do not promote any v2A macro candidate from this run. The macro sweep gave a
clear diagnostic read, but no promotion-grade winner.

- `size_5` dominated `size_8` and `size_10` on return and Sharpe.
- Larger portfolio sizes diluted returns and introduced sizing failures.
- The best return candidate was `aggressive_alpha / size_5`, but it was carried
  by open unrealized gains and had worse realized P&L than current v2A.
- The best closed-trade quality candidate was `defensive / size_5`, but it gave
  up too much aggregate return.
- 21-day rank correlation stayed negative for every macro variant.
- v1 remains canonical; v2A remains opt-in.

## Baselines And Key Candidates

Aggregate means across the three folds:

| Profile | Return | Sharpe | Max DD | Win Rate | Profit Factor | Realized P&L | Unrealized P&L | 21d Rank Corr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | 10.20% | 0.646 | -13.67% | 54.79% | 1.323 | +3,090 | +7,111 | +0.0320 |
| current v2A | 19.45% | 0.801 | -13.39% | 37.62% | 0.713 | -5,605 | +25,056 | -0.0198 |
| aggressive_alpha / size_5 | 20.53% | 0.847 | -14.01% | 39.96% | 0.774 | -6,480 | +27,010 | -0.0197 |
| tradability_tilted / size_5 | 18.95% | 0.867 | -13.33% | 35.76% | 1.056 | -4,458 | +23,408 | -0.0316 |
| defensive / size_5 | 15.22% | 0.716 | -14.44% | 40.51% | 1.882 | +5,201 | +10,016 | -0.0270 |

Interpretation:

- `aggressive_alpha / size_5` is the top return row, but it is not a clean
  improvement. It beats current v2A by about 1.08 percentage points of return
  while worsening realized P&L.
- `tradability_tilted / size_5` has the best Sharpe, but lower return than
  current v2A and worse 21d rank correlation.
- `defensive / size_5` is the most useful diagnostic case because it flips
  realized P&L positive and improves closed-trade quality, but it sacrifices too
  much return.

## Portfolio Size Read

Aggregate means by paired `portfolio_breadth` / `max_open_positions` size:

| Size | Avg Return | Avg Sharpe | Avg Realized P&L | Avg Sizing Failures |
|---|---:|---:|---:|---:|
| size_5 | 18.39% | 0.804 | -2,841 | 0.00 |
| size_8 | 12.39% | 0.573 | -7,154 | 1.33 |
| size_10 | 11.06% | 0.591 | -6,574 | 4.93 |

Conclusion: keep `portfolio_breadth=5` and `max_open_positions=5` as the main
medium-horizon macro assumption. Do not spend M98 budget expanding `size_8` and
`size_10` unless there is a specific follow-up hypothesis.

## Fold Behavior

| Profile | Fold 1 Return | Fold 2 Return | Fold 3 Return |
|---|---:|---:|---:|
| v1 | 37.50% | -5.47% | -1.42% |
| current v2A | 71.60% | -6.76% | -6.49% |
| aggressive_alpha / size_5 | 73.70% | -4.61% | -7.51% |
| tradability_tilted / size_5 | 70.60% | -6.43% | -7.31% |
| defensive / size_5 | 58.77% | -3.87% | -9.24% |

Fold 1 strongly favors v2A-style variants, but Fold 3 still favors v1 by loss
control. None of the macro candidates fixed the recent-window weakness.

## Recommendation For M98

Proceed to M98, but shape it using this result:

- Keep `size_5` as the main portfolio-size setting.
- Carry `aggressive_alpha / size_5` as a return benchmark, not as a preferred
  candidate.
- Carry `defensive / size_5` as the trade-quality benchmark.
- Focus sensitivity work on knobs that may improve realized P&L, profit factor,
  average win/loss, and 21d rank behavior.
- Avoid optimizing for small aggregate-return edges without checking realized
  trade quality and fold stability.

Straight read: M97 did not find the candidate. It found the constraint. v2A
needs better realized trade quality and rank behavior, not broader portfolios
or a small extra alpha tilt.
