# Technical Layer Overhaul Plan

Last updated: 2026-06-23

This document is the implementation plan for overhauling the Taurus technical
indicator and technical scoring layer. Each milestone below is a standalone
milestone intended to be executed in a separate Codex thread. Stop after
completing and documenting the current milestone; do not automatically continue
to the next milestone.

Status: Planning is complete. M74-M76 implementation are complete. M77-M86
remain planned. The intended execution model is one fresh Codex thread per milestone,
using GPT 5.5 with xhigh thinking, unless the user explicitly changes that
instruction in the worker thread.

## Target Behavior

Taurus should evolve from a narrow technical layer into an auditable technical
state and scoring system that can improve both:

- `TechnicalAnalystAgent`: better deterministic score, confidence, technical
  diagnosis, feature contributors, missing-data visibility, and future-return
  validation.
- `graph_aware_score_v1` successor strategy: better quantity-driving technical
  scores for money management, while preserving the current v1 behavior until a
  conservative validation gate supports promotion.

The target design separates technical evidence into:

- `alpha_score`: directional technical attractiveness.
- `risk_score`: volatility, extension, drawdown, and instability penalties.
- `tradability_score`: turnover, liquidity, and later official
  microstructure/tradability inputs.
- `confidence`: reliability plus indicator-family agreement, not simply signal
  strength.
- `composite_score`: the bounded/ranked score used by strategy ranking and, via
  existing score calibration, money-management quantity selection.

The first runtime profile is `technical_ohlcv_v2` and should use OHLCV-only
data plus cross-sectional universe ranks. It must not pretend to have official
market-relative, sector-relative, delivery, circuit, India VIX, or impact-cost
features before those data sources are actually ingested.

Later `technical_official_v2b` work adds official index, sector, India VIX,
delivery, circuit, and implementability features after the ingestion contract is
in place.

## Existing Foundation

- `TechnicalFeatureService` in `packages/taurus_core/features/store.py`
  currently builds `FeatureSnapshot` values from `daily_candles`; default
  indicators are SMA `5/10/20/30/50`, EMA `12/26`, returns `1/5/20d`, RSI 14,
  ATR 14, volatility 20, and volume z-score 20.
- `TechnicalSignalService` in `packages/taurus_core/features/technical_signal.py`
  currently owns behavior-preserving profiles:
  - `technical_rule_v1` for `TechnicalAnalystAgent`
  - `sma_spread` for `GraphAwareScoreStrategy`
- `TechnicalAnalystAgent` still runs as a symbol-local agent by default. It can
  derive a feature snapshot from `daily_candles`, but it does not currently
  receive universe context for cross-sectional scoring.
- `GraphAwareScoreStrategy` currently computes the technical score as
  `SMA_10 / SMA_30 - 1`, combines it with graph score, and exposes
  `technical_score`, `raw_strategy_score`, and ranked candidates for downstream
  allocation.
- `configs/strategies/graph_aware_score_v1.yaml` is the canonical Kite paper
  loop strategy config today.
- `configs/portfolio/money_management_v1.yaml` maps `graph_aware_score_v1` to
  the `active_strategy` sleeve. Raw strategy score contributes to allocation
  candidate scoring through `packages/taurus_core/portfolio/score_semantics.py`
  and active allocation.
- `scripts/run_backtest.py` and `BacktestEngine` can already run a strategy
  against existing imported `daily_candles`, persist feature values, signals,
  fills, positions, and backtest metrics, and print a metrics JSON payload.
- `make paper-loop-kite` remains the canonical real-data paper-loop path.
- `docs/MILESTONE.md` requires flat milestone IDs, tracker updates, explicit
  completion summaries, and approval-rule cleanup at milestone closeout.

## Research And Validation Inputs

Use these inputs when designing or validating the implementation:

- Local research report:
  `/Users/adnaan/Downloads/deep-research-report.md`
- Nifty200 Momentum 30 methodology concept: 6-month and 12-month return
  adjusted for volatility and converted into cross-sectional scores.
- NSE security-wise archives: delivery and price-volume data are official data
  sources, but they are not present in TaurusAgent yet.
- India VIX: official expected-volatility regime input, but not present in
  TaurusAgent yet.
- NSE impact-cost methodology: official implementability concept, but not
  present in TaurusAgent yet.
- Momentum and trend literature supports trend/momentum as features, while
  backtest-overfitting literature requires strict walk-forward validation.

## Global Rules For M74-M86

- Implement only the requested milestone. After that milestone is complete,
  verified, cleaned up, and documented, stop and report the result.
- Do not start, partially implement, scaffold, or prepare later milestones
  unless the user explicitly asks to proceed.
- Preserve paper-only execution. Do not add live broker order routing, real
  money movement, irreversible external side effects, or secrets.
- Preserve v1 runtime behavior until an explicit promotion milestone. The
  current `graph_aware_score_v1` strategy and `technical_rule_v1` profile must
  remain compatibility baselines.
- Add v2 behavior as opt-in configs/profiles first. Do not silently switch
  `make paper-loop-kite` to v2 before the promotion gate passes.
- Keep technical score concepts separate:
  - raw feature values
  - cross-sectional ranks/z-scores
  - alpha/risk/tradability sub-scores
  - confidence/reliability
  - strategy raw score
  - calibrated allocation component
  - final money-management candidate score
- V2 `TechnicalAnalystAgent` numeric score and confidence must be deterministic
  outputs from `TechnicalSignalService`; the LLM may explain but must not own
  the stored numeric truth for v2.
- V2 must not use `backtest_signals` as a score override. Prior strategy
  signals may appear as context/audit evidence only.
- If any public artifact, API payload, or React-visible state changes, include
  the matching API/UI/test work in the same milestone or create a dedicated
  follow-up milestone with an explicit contract.
- Do not use local market or sector proxies for official market-relative or
  sector-relative scoring. Use cross-sectional universe ranks in v2A, and defer
  official market/sector relative strength to v2B after official data ingestion.
- Validation must include both:
  - technical-agent predictive evidence
  - full-system historical backtest evidence
- At completion of every milestone, update `docs/MILESTONE.md` with status and
  an explicit completion summary listing assumptions made, mocks created, and
  mocks used. Use `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the project-local approval cleanup rule in `docs/MILESTONE.md`.

## M74 - Baseline, Evidence Contract, And Validation Design

Purpose: pin current technical, analyst, strategy, and money-management scoring
behavior before adding richer v2 features.

Instructions:

- Inspect current paths:
  - `packages/taurus_core/features/technical_signal.py`
  - `packages/taurus_core/features/store.py`
  - `packages/taurus_core/features/technical.py`
  - `packages/taurus_core/agents/technical_analyst.py`
  - `packages/taurus_core/strategies/graph_aware.py`
  - `packages/taurus_core/portfolio/score_semantics.py`
  - `packages/taurus_core/portfolio/active_allocation.py`
  - `scripts/run_backtest.py`
  - `packages/taurus_core/backtesting/*`
  - `configs/strategies/graph_aware_score_v1.yaml`
  - `configs/portfolio/money_management_v1.yaml`
- Add or tighten characterization tests for:
  - `technical_rule_v1` raw score, bounded score, confidence, metadata, and
    latest-signal override.
  - `sma_spread` score availability and quantization.
  - `graph_aware_score_v1` combined score, ranked-candidate payload, and
    strategy-score propagation to allocation score calibration.
  - Current LLM numeric ownership in `BaseAnalystAgent._build_report()`, so the
    later v2 deterministic ownership change is explicit and test-backed.
- Draft the validation output contract in docs before implementation:
  - technical-agent predictive report sections
  - system backtest report sections
  - profile comparison matrix
  - promotion gate inputs
  - expected artifact paths
- Correct stale docs only when the current code demonstrably differs from the
  docs and the correction is needed for this sequence.
- Do not add new indicators, new strategy configs, new commands, new API/UI
  fields, or official-data ingestion in this milestone.

Expected code shape:

- Mostly tests and docs.
- Production code changes should be limited to harmless exposure needed for
  characterization, and only if tests cannot otherwise observe current behavior.

Acceptance criteria:

- The current v1 technical layer is pinned by focused tests.
- The validation contract is documented clearly enough for later milestones.
- No runtime behavior changes.
- `docs/MILESTONE.md` marks M74 done and M75 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_analyst_agents.py tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py tests/unit/test_active_allocation.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

### M74 Validation Output Contract

This contract is the design target for M81 and M82. M74 does not add new
commands, generated artifacts, API fields, strategy profiles, or runtime
behavior.

Validation artifacts should be written under an operator-selected output root,
defaulting to:

```text
artifacts/technical_validation/<profile_name>/<run_id>/
```

Expected files:

- `technical_agent_predictive_report.json`
- `technical_agent_predictive_report.md`
- `system_backtest_report.json`
- `system_backtest_report.md`
- `profile_comparison_matrix.csv`
- `promotion_gate.json`

The technical-agent predictive report must include:

- profile name, feature version, strategy config path, code commit, run id, and
  generated-at timestamp.
- input universe, excluded symbols, minimum data window, missing-data counts,
  and data-readiness warnings.
- prediction label definition, holding horizon, scoring date, outcome date, and
  whether labels are forward-return, decile, or binary hit-rate labels.
- score distribution by date, symbol count by date, missing-score count, and
  confidence distribution.
- rank evidence: decile or quintile forward returns, monotonicity checks,
  top-minus-bottom spread, hit rate, rank correlation, and coverage.
- stability evidence across rolling or walk-forward windows, including periods
  that fail minimum sample thresholds.
- feature family contribution summaries for alpha, risk, tradability, and
  confidence when those vectors exist; v1 reports should explicitly state that
  only the current `technical_rule_v1` scalar score exists.
- failure and caveat section covering data gaps, survivorship risk, corporate
  action assumptions, stale feature snapshots, and out-of-sample limitations.

The full-system backtest report must include:

- profile name, strategy name, strategy config path, money-management config,
  universe path, graph-enabled flag, paper-only execution statement, code
  commit, run id, and generated-at timestamp.
- date range, rebalance cadence, lookback days, starting capital, target
  positions, cost bps, slippage bps, and portfolio breadth source.
- headline metrics: final equity, total return, annualized return when
  meaningful, Sharpe or risk-adjusted proxy, max drawdown, turnover, hit rate,
  win/loss asymmetry, trade count, fill count, and open-position count.
- rank and allocation evidence: ranked-candidate count, eligible-candidate
  count, preview of ranked candidates, raw strategy score distribution,
  calibrated allocation score distribution, rejected allocation reasons, and
  binding constraints.
- cost and implementability evidence: estimated costs, slippage assumptions,
  quantity rounding effects, liquidity/tradability warnings when available, and
  capacity warnings.
- regression comparison against the v1 compatibility baseline, with no silent
  promotion if any required comparison is missing.

The profile comparison matrix must be machine-readable and include one row per
profile and evaluation slice. Required columns:

| Column | Meaning |
|---|---|
| `profile_name` | Technical profile under evaluation, for example `technical_rule_v1` or `technical_ohlcv_v2`. |
| `strategy_name` | Strategy config using the profile. |
| `slice_name` | Overall, walk-forward fold, market regime, or data-quality slice. |
| `start_date` | Inclusive evaluation start date. |
| `end_date` | Inclusive evaluation end date. |
| `symbol_count` | Symbols with enough data for the slice. |
| `trade_count` | Executed full-system backtest trades, if applicable. |
| `coverage_pct` | Share of eligible symbols with usable technical scores. |
| `rank_ic` | Rank correlation between score and future return, if computed. |
| `top_bottom_spread` | Top bucket minus bottom bucket forward return. |
| `hit_rate` | Directional or trade hit rate using the report's label definition. |
| `total_return` | Full-system total return, if applicable. |
| `max_drawdown` | Full-system max drawdown, if applicable. |
| `turnover` | Full-system or rank turnover. |
| `status` | `pass`, `warn`, `fail`, or `not_applicable`. |
| `notes` | Short reason for warnings, failures, or missing metrics. |

The promotion gate must be conservative and explicit. Required inputs:

- v1 baseline report paths and v2 candidate report paths.
- technical-agent evidence status for rank monotonicity, coverage, stability,
  and missing-data thresholds.
- full-system evidence status for total return, drawdown, turnover, trade count,
  cost assumptions, and regression-vs-baseline comparison.
- data-readiness status for OHLCV coverage, corporate-action assumptions,
  official-data availability, and any mocked or unavailable source.
- operational safety status proving `graph_aware_score_v1` and
  `technical_rule_v1` remain unchanged unless the promotion milestone explicitly
  switches them.
- final decision: `promote`, `keep_opt_in`, or `defer`, with blocking reasons.

Minimum promotion rule:

```text
Promote only when technical-agent evidence and full-system evidence both pass,
data readiness has no blocking failure, no safety regression is present, and
the comparison includes the current v1 baseline.
```

## M75 - OHLCV Indicator Primitive Expansion

Purpose: add the full OHLCV indicator primitives and feature snapshot support
needed by the first v2A technical profile.

Instructions:

- Extend `packages/taurus_core/features/technical.py` with deterministic
  indicator primitives:
  - MACD line, signal, and histogram.
  - ADX, +DI, and -DI.
  - Bollinger moving average, upper/lower bands, percent B, and bandwidth.
  - rolling high/low breakout distance for 20/50/252 trading days.
  - distance from 52-week high.
  - ATR percent.
  - turnover and rolling average traded value.
  - turnover z-score.
  - volatility-adjusted returns for 63/126/252 trading days.
- Extend `TechnicalFeatureService` to support opt-in windows and indicator
  families for `technical_ohlcv_v2` without changing the v1 default feature
  set.
- Add strategy-parameter parsing for the new feature suite:
  - default v1 strategy parameters still create today feature windows.
  - v2 strategy parameters request the full OHLCV suite and a longer lookback.
- Keep feature values quantized consistently with existing feature storage.
- Add unit tests for each primitive and feature-snapshot output, including
  insufficient-history behavior.
- Do not add cross-sectional ranks, scoring formulas, analyst wiring, strategy
  wiring, API/UI changes, validation command, or official-data ingestion in this
  milestone.

Expected code shape:

- Indicator functions remain pure and DB-free.
- `TechnicalFeatureService` remains the owner of per-symbol candle-derived
  snapshots.
- The v2 feature set is opt-in through parameters or feature version, not a
  silent replacement of `technical_v1`.

Acceptance criteria:

- New OHLCV features can be generated from daily candles.
- Existing v1 feature snapshots and tests remain unchanged.
- Feature names are stable and documented in tests or docs.
- `docs/MILESTONE.md` marks M75 done and M76 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_technical_indicators.py tests/unit/test_technical_signal_service.py tests/unit/test_graph_backtesting.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M76 - Universe Technical Context And Cross-Sectional Normalization

Purpose: build the DB-free universe context that lets v2A rank stocks against
the analyzed universe without using unofficial market/sector proxies.

Instructions:

- Add a shared technical context type, likely under
  `packages/taurus_core/features/technical_context.py` or alongside
  `technical_signal.py`, that accepts `features_by_symbol`.
- Compute cross-sectional ranks, percentiles, z-scores, availability counts,
  and missing-feature maps for selected v2 feature names.
- Include universe-level metadata:
  - universe size
  - eligible symbol count per feature
  - rank direction per feature
  - as-of date
  - feature version/profile name
- Handle missing values deterministically. Missing values should reduce
  confidence/coverage later, not silently become bullish or bearish evidence.
- Expose context lookups by symbol for later strategy and analyst wiring.
- Do not compute market-relative or sector-relative returns here. Those wait
  for official Nifty/sector index ingestion.
- Do not add the final v2 scoring formula, strategy config, API/UI changes, or
  validation command in this milestone.

Expected code shape:

- The context builder is pure and DB-free.
- It should be usable by `GraphAwareScoreStrategy`, `TechnicalAnalystAgent`,
  validation tooling, and tests.
- Decimal handling and JSON-friendly metadata should match the style of
  `TechnicalSignalResult`.

Acceptance criteria:

- Cross-sectional ranks/z-scores are stable and deterministic.
- Missing/insufficient universe data is visible in metadata.
- Ties and small-universe behavior are deterministic and covered.
- Existing v1 behavior remains unchanged.
- `docs/MILESTONE.md` marks M76 done and M77 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_strategy_ranking.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M77 - TechnicalSignalService V2A Scoring Profile

Purpose: add the deterministic `technical_ohlcv_v2` scoring profile that turns
OHLCV features and universe context into alpha, risk, tradability, confidence,
and composite scores.

Instructions:

- Extend `TechnicalSignalResult` or add a typed v2 result that exposes:
  - `alpha_score`
  - `risk_score`
  - `tradability_score`
  - `confidence`
  - `composite_score`
  - `top_contributors`
  - `missing_features`
  - `coverage`
  - `score_source`
  - JSON-friendly metadata
- Add `TechnicalSignalService.score_ohlcv_v2(...)`.
- Use the v2A full OHLCV suite only:
  - multi-horizon momentum and volatility-adjusted momentum
  - trend confirmation
  - trend strength
  - breakout/extension state
  - turnover/tradability proxies from OHLCV
  - cross-sectional universe ranks/z-scores from M76
- Define confidence as reliability plus agreement:
  - enough lookback
  - feature coverage
  - universe breadth
  - agreement across feature families
  - tradability feature quality
- Keep score ranges explicit:
  - raw sub-scores should be inspectable.
  - final strategy-compatible score should be bounded/quantized.
  - allocation calibration remains owned by the portfolio layer.
- Keep v1 methods intact and behavior-preserving.
- Do not wire the profile into runtime analyst or strategy paths yet.
- Do not add official market/sector/delivery/circuit/VIX inputs yet.

Expected code shape:

- Scoring logic lives in `TechnicalSignalService`, not in the analyst or
  strategy class.
- Scoring weights should be named constants or profile parameters with clear
  defaults and metadata.
- Top contributors should explain direction and magnitude without requiring the
  LLM.

Acceptance criteria:

- Unit tests prove v2 scoring, confidence, missing-feature behavior, and top
  contributors.
- V1 technical profiles still pass all parity tests.
- No runtime behavior changes until later wiring milestones.
- `docs/MILESTONE.md` marks M77 done and M78 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_technical_indicators.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M78 - Opt-In GraphAwareScoreStrategy V2A Runtime Profile

Purpose: add `graph_aware_score_v2` as an opt-in strategy that uses the v2A
technical profile while leaving `graph_aware_score_v1` unchanged.

Instructions:

- Add a new strategy config:
  - `configs/strategies/graph_aware_score_v2.yaml`
  - longer lookback appropriate for 252-day indicators, with 3-year validation
    compatibility later.
  - `technical_profile: technical_ohlcv_v2`
  - graph behavior initially equivalent to v1 unless explicitly documented.
- Extend `GraphAwareScoreStrategy` to select the technical profile by config:
  - default profile remains `sma_spread`.
  - v2 profile calls the M76 context builder and
    `TechnicalSignalService.score_ohlcv_v2`.
- Preserve existing public keys for compatibility:
  - `technical_score`
  - `strategy_score_by_symbol`
  - `raw_strategy_score`
  - `ranked_candidates`
- Add nested v2 metadata:
  - technical profile name
  - alpha/risk/tradability/confidence/composite
  - top contributors
  - missing features
  - score coverage
- Add `graph_aware_score_v2` to money-management strategy mappings under
  `active_strategy`, but do not make it canonical.
- Do not change `make paper-loop-kite` default strategy unless the user
  explicitly sets `STRATEGY=configs/strategies/graph_aware_score_v2.yaml`.
- Do not change `TechnicalAnalystAgent` in this milestone.

Expected code shape:

- `GraphAwareScoreStrategy.rank_universe()` should build or receive the universe
  technical context once per ranking call, not recompute it per symbol.
- v2 ranking metadata should be sufficient for allocation and UI debugging.
- v1 tests should not need expected-value changes except where new optional
  metadata is deliberately present.

Acceptance criteria:

- v1 strategy behavior remains unchanged.
- v2 strategy can rank symbols with the full OHLCV technical vector.
- v2 raw strategy score reaches allocation candidate scoring through existing
  `strategy_score_by_symbol` and `raw_strategy_score` paths.
- `docs/MILESTONE.md` marks M78 done and M79 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py tests/unit/test_active_allocation.py tests/unit/test_money_management.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M79 - TechnicalAnalystAgent V2A Deterministic Numeric Wiring

Purpose: let `TechnicalAnalystAgent` use the same v2A technical profile as the
strategy, with optional universe context and deterministic numeric ownership.

Instructions:

- Add a config/profile switch for the technical analyst:
  - v1 default remains `technical_rule_v1`.
  - v2 opt-in uses `technical_ohlcv_v2`.
- Extend the analyst runner/paper-loop path so `TechnicalAnalystAgent` can
  receive optional universe feature context when the strategy stage already has
  full-universe snapshots.
- Preserve manual/symbol-local runs by falling back to a symbol-local v2 result
  that clearly reports missing universe context and lower confidence.
- For v2 only:
  - the stored `AnalystReport.score` must come from deterministic
    `TechnicalSignalService`.
  - the stored `AnalystReport.confidence` must come from deterministic v2
    confidence.
  - the LLM may produce narrative, key points, and risks, but must not override
    score/confidence.
  - latest `backtest_signals` must not override v2 score; prior signals may be
    context/audit metadata only.
- Extend `AnalystScoreMetadata` additively or use structured metadata to expose
  alpha/risk/tradability/confidence/top contributors.
- Keep v1 analyst behavior unchanged.
- Do not add React/UI surfacing yet unless the existing API already exposes the
  new metadata automatically and tests need only serialization coverage.

Expected code shape:

- The deterministic score override should be narrow and profile-gated.
- Existing LLM provider failure behavior should not be broadened unless this
  milestone explicitly documents and tests a deterministic fallback path.
- Universe context should be optional and explicit, not hidden global state.

Acceptance criteria:

- v2 analyst reports have deterministic score/confidence.
- v1 analyst reports continue to match current behavior.
- v2 report metadata explains score source, coverage, contributors, and missing
  context.
- `docs/MILESTONE.md` marks M79 done and M80 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_analyst_agents.py tests/unit/test_technical_signal_service.py tests/unit/test_paper_runs.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M80 - V2A Artifact, API, Replay, And React Visibility

Purpose: make v2A technical evidence visible wherever operators debug agent,
strategy, and money-management decisions.

Instructions:

- Inspect current API/replay/UI surfaces:
  - `apps/api/routes_ui.py`
  - `apps/api/routes_intelligence.py`
  - `packages/taurus_core/replay/service.py`
  - `apps/web/src/features/*`
  - existing UI aggregate tests and screen-state tests.
- Ensure v2 technical vector is visible in:
  - analyst report detail or decision trail payloads.
  - strategy ranked candidates.
  - strategy signals.
  - allocation selection rows where strategy score is used.
  - replay output for historical debugging.
- Keep payload changes additive.
- Use compact UI presentation:
  - show profile, composite score, confidence, alpha/risk/tradability.
  - show top contributors and missing-feature warnings.
  - do not create a marketing-style page.
- Add API and React tests for v2 metadata visibility.
- Do not change scoring formulas or validation logic in this milestone.

Expected code shape:

- API serializers should pass through typed/nested metadata without losing
  numeric strings or contributor labels.
- React should show the v2 vector only when present; legacy v1 runs must remain
  clean and readable.

Acceptance criteria:

- Operators can trace v2 score from analyst report through strategy ranking and
  allocation inputs.
- Legacy v1 runs render unchanged or gracefully omit v2-only fields.
- `docs/MILESTONE.md` marks M80 done and M81 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_ui_aggregate_api.py tests/unit/test_paper_runs.py tests/unit/test_replay.py
pnpm --dir apps/web test -- --run
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M81 - Historical Validation Command And Data Readiness

Purpose: add a project-local command that pulls or verifies enough historical
data and runs comparable v1/v2 validation profiles.

Instructions:

- Add a command such as `make validate-technical-v2`.
- Add a script such as `scripts/validate_technical_v2.py`.
- The command must:
  - accept or default a validation universe.
  - verify local `daily_candles` coverage.
  - request or document the required deeper historical import when coverage is
    insufficient.
  - default to a 3-year validation window.
  - support a 5-year stronger validation mode.
  - account for 252-day indicator warm-up before scoring the evaluation period.
- Run these profiles on the same dates, symbols, costs, slippage, graph
  settings, NAV assumptions, and position limits:
  - existing `graph_aware_score_v1`
  - existing v1 technical without graph contribution where practical
  - `graph_aware_score_v2`
  - v2A technical without graph contribution where practical
- Reuse `BacktestEngine` where possible. If the current engine cannot compute a
  needed metric, add the minimum extension rather than writing a parallel
  backtester.
- Persist machine-readable artifacts under a deterministic local artifact path,
  for example `artifacts/technical_validation/<run_id>/`.
- Do not promote v2 or change canonical paper-loop defaults in this milestone.

Expected code shape:

- The validation script is deterministic and repeatable.
- Backtest inputs and output paths are printed in the terminal.
- Insufficient-data failures should be actionable and name the missing
  date/symbol coverage.

Acceptance criteria:

- A user can run one command to produce v1/v2 comparable validation artifacts.
- The command does not mutate strategy defaults or live paper state.
- The command can be used before official-data v2B exists.
- `docs/MILESTONE.md` marks M81 done and M82 planned when completed.

Verification:

```bash
make validate-technical-v2
uv run pytest tests/unit/test_config.py tests/unit/test_graph_backtesting.py tests/unit/test_paper_runs.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M82 - Technical Validation Reports And Conservative Gate

Purpose: turn validation artifacts into human-readable evidence for whether the
technical layer and full system improved.

Instructions:

- Extend the validation command to produce:
  - terminal summary
  - Markdown report under `docs/reports/technical_validation/`
  - JSON/CSV artifacts under `artifacts/technical_validation/<run_id>/`
- Technical-agent evidence must include:
  - future-return prediction checks for 5d, 21d, and 63d horizons.
  - information coefficient or rank correlation.
  - top-vs-bottom decile spread.
  - high-confidence vs low-confidence hit-rate/calibration.
  - missing-feature and coverage diagnostics.
  - explanation quality summary based on vector presence and contributors.
- Full-system evidence must include:
  - total return / CAGR.
  - Sharpe / Sortino.
  - max drawdown.
  - turnover.
  - win rate / profit factor.
  - selected symbol counts.
  - cash utilization.
  - allocation candidate-score behavior.
  - rejected or trimmed candidate counts.
  - equity curve summary.
- Add a conservative promotion gate:
  - v2A must beat or tie v1 after costs.
  - v2A must not worsen max drawdown materially.
  - v2A must keep turnover controlled.
  - v2A must show positive rank/decile monotonicity.
  - v2A must not degrade allocation utilization or create unexplained sizing
    failures.
- The report should conclude with `promote`, `keep_opt_in`, or `defer`.
- Do not actually promote v2 in this milestone.

Expected code shape:

- Report generation should be deterministic from validation artifacts.
- Markdown should be operator-readable and should link or name machine-readable
  artifacts.
- JSON/CSV should support later comparison across runs.

Acceptance criteria:

- The user can see whether the technical agent got better and whether the whole
  Taurus system got better.
- The promotion recommendation is evidence-backed and reproducible.
- `docs/MILESTONE.md` marks M82 done and M83 planned when completed.

Verification:

```bash
make validate-technical-v2
uv run pytest tests/unit/test_backtesting.py tests/unit/test_graph_backtesting.py tests/unit/test_paper_runs.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M83 - Official Index, Sector, And India VIX Data Ingestion

Purpose: add official market and regime data needed for v2B market-relative and
sector-relative technical features.

Instructions:

- Design and implement data contracts for:
  - broad index history, especially Nifty benchmark history.
  - sector index history where available.
  - India VIX history.
- Prefer existing repository/provider patterns for market data and migrations.
- Add idempotent migrations if new tables are needed.
- Add import scripts and Make commands only as needed.
- Track source, data availability time, symbol/index identifier, and timeframe.
- Add preflight/readiness checks for v2B validation.
- Do not use unofficial local market/sector proxies as substitutes.
- Do not wire official data into scoring until M85.
- Do not change v2A behavior.

Expected code shape:

- Official data should be queryable by as-of date without lookahead.
- Missing index/VIX data should produce explicit readiness failures for v2B,
  not silent neutral values.

Acceptance criteria:

- Official benchmark, sector index, and VIX histories can be imported or
  verified locally.
- Tests cover schema/repository/import behavior and no-lookahead access.
- `docs/MILESTONE.md` marks M83 done and M84 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_config.py tests/unit/test_dashboard_observability.py
make migrate
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M84 - Official Delivery, Circuit, And Tradability Data Ingestion

Purpose: add official or explicitly documented microstructure/tradability inputs
for v2B.

Instructions:

- Design and implement data contracts for:
  - security-wise delivery percentage or delivery quantity.
  - price-band/circuit status or circuit-hit history where available.
  - impact-cost data when available, or an explicitly named proxy when not
    available.
  - average trade value and turnover fields if official data differs from OHLCV
    derived proxies.
- Use source metadata and data availability times.
- Add import scripts/commands and readiness checks.
- Keep v2A OHLCV tradability behavior unchanged.
- Do not wire these features into scoring until M85.

Expected code shape:

- Delivery and circuit data should be symbol/date keyed.
- Readiness failures should name the missing official-data family.
- Impact-cost fallback must be labeled as a proxy if official impact-cost data
  is unavailable.

Acceptance criteria:

- Official delivery/circuit/tradability inputs are locally available for v2B
  validation.
- Tests cover import, query, missing data, and no-lookahead behavior.
- `docs/MILESTONE.md` marks M84 done and M85 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_config.py tests/unit/test_dashboard_observability.py
make migrate
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M85 - V2B Official-Data Technical Profile

Purpose: add `technical_official_v2b`, which extends v2A with official
market-relative, sector-relative, regime, delivery, circuit, and tradability
features.

Instructions:

- Extend feature/context services to join as-of official data from M83/M84.
- Add official-data features:
  - market-relative returns vs Nifty benchmark.
  - sector-relative returns vs official sector index where mapped.
  - market and sector regime state.
  - India VIX level/change/regime.
  - delivery percentage/z-score or delivery participation state.
  - circuit-hit and near-band penalties.
  - impact-cost or labeled implementability proxy.
- Add `TechnicalSignalService.score_official_v2b(...)` or a profile parameter
  path that reuses `score_ohlcv_v2` with official-data extensions.
- Add `graph_aware_score_v2b.yaml` as opt-in only.
- Update validation profiles so v2B compares against v1 and v2A.
- Do not promote v2B as canonical in this milestone.

Expected code shape:

- Official-data fields must be included in metadata with source coverage.
- Missing official data should lower confidence or mark profile unavailable
  according to the documented contract.
- v2A tests must continue to pass without official data present.

Acceptance criteria:

- v2B can rank and explain symbols using official market/sector/regime and
  microstructure inputs.
- v2B validation can run in opt-in mode.
- `docs/MILESTONE.md` marks M85 done and M86 planned when completed.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py tests/unit/test_paper_runs.py
make validate-technical-v2
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M86 - Promotion Decision, Regression, Docs, And Cleanup

Purpose: close the sequence by either promoting the best validated technical
profile or explicitly keeping it opt-in with documented evidence.

Instructions:

- Run the validation command in the chosen default mode:
  - 3-year default if available.
  - 5-year stronger mode if local/Kite history supports it.
- Compare v1, v2A, and v2B if v2B exists and is ready.
- Apply the conservative promotion gate from M82.
- If promotion passes:
  - update canonical strategy config or paper-loop docs according to the chosen
    profile.
  - ensure money-management mapping and allocation docs are accurate.
  - update command docs and usage guide.
  - update React/API docs if operator behavior changes.
- If promotion does not pass:
  - keep v2 profiles opt-in.
  - document why promotion was deferred and what evidence is missing.
- Run focused and broad regression.
- Inspect `/Users/adnaan/.codex/rules/default.rules` and clean Taurus-specific
  approvals if needed.
- Do not commit unless the user explicitly asks.

Expected code shape:

- Promotion should be a small config/docs change backed by prior validation
  artifacts, not another scoring refactor.
- The final docs should distinguish implemented behavior, opt-in profiles,
  validation evidence, and deferred work.

Acceptance criteria:

- The sequence ends with an explicit promotion or keep-opt-in decision.
- Operator docs and architecture docs match actual behavior.
- The tracker records sequence closeout and no next milestone is implied unless
  the user asks for a follow-up plan.

Verification:

```bash
make validate-technical-v2
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_analyst_agents.py tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py
pnpm --dir apps/web test -- --run
make test
make test-ui
make build-ui
make -n paper-loop-kite
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## Deferred Work

- Intraday technical profiles.
- Options-derived signals beyond India VIX.
- Production live-trading use. Taurus remains paper-only.
- ML model training on technical features.
- Automated strategy promotion without explicit user approval.
- Broker-calibrated charges, taxes, and impact-cost execution modeling beyond
  the documented validation assumptions.
