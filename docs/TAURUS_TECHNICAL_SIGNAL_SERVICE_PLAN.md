# Shared TechnicalSignalService Plan

Last updated: 2026-06-22

This document is the implementation plan for introducing a shared technical
signal scoring layer. Each milestone below is a standalone milestone intended
to be executed in a separate Codex thread. Stop after completing and
documenting the current milestone; do not automatically continue to the next
milestone.

## Target Behavior

Taurus should have one shared, deterministic technical scoring contract that can
be reused by analyst reports and strategy rankings without changing current
trading behavior during the first implementation sequence.

The first implementation sequence is intentionally behavior-preserving:

- `TechnicalAnalystAgent` should keep its existing report score, confidence,
  source IDs, model version, score metadata source, LLM context shape, and
  key-point behavior.
- `GraphAwareScoreStrategy` should keep its existing strategy scores,
  eligibility filters, target selection, ranked-candidate payloads, and
  allocation downstream behavior.
- The new service should make future technical-indicator experiments easier
  without forcing each strategy or analyst to reimplement feature scoring.

## Existing Foundation

- `TechnicalFeatureService` in `packages/taurus_core/features/store.py` already
  builds reusable `FeatureSnapshot` objects from persisted `feature_values` or
  candle-derived history.
- `TechnicalAnalystAgent` currently loads persisted/candle-derived feature
  snapshots, optionally loads the latest `backtest_signals` row, then computes
  a deterministic technical score in `packages/taurus_core/agents/technical_analyst.py`.
- `GraphAwareScoreStrategy` currently computes a separate SMA spread technical
  score inside `packages/taurus_core/strategies/graph_aware.py`.
- `BlendedScoreStrategy` and `MovingAverageCrossoverStrategy` also contain
  technical formulas, but they are not in the first wiring scope.
- The canonical `make paper-loop-kite` path enables `technical,graph` analysts
  and uses `configs/strategies/graph_aware_score_v1.yaml`, making the analyst
  and graph-aware strategy surfaces the current high-priority disconnect.
- `docs/MILESTONE.md` requires flat milestone IDs, one milestone at a time,
  completion summaries, and approval-rule cleanup at milestone closeout.

## Global Rules For M66-M69

- Implement only the requested milestone. After that milestone is complete,
  verified, cleaned up, and documented, stop and report the result.
- Preserve paper-only and Kite-data-only safety boundaries. Do not add live
  broker routing, new money movement, hosted service dependencies, or secrets.
- Keep this sequence behavior-preserving until M69 explicitly confirms parity.
  Richer technical profiles, configurable indicator suites, and strategy
  retuning are deferred.
- Do not introduce database migrations, API contract changes, or React changes
  unless implementation evidence proves an existing public payload must change.
- If any public artifact metadata is added, keep it additive and preserve
  existing keys such as `technical_score`, `score`, `strategy_score_by_symbol`,
  `source_ids`, and `score_metadata.score_source`.
- Keep docs honest: architecture/deep-dive docs must distinguish current code
  from planned or newly implemented behavior.
- At completion of every milestone, update `docs/MILESTONE.md` with status and
  an explicit completion summary listing assumptions made, mocks created, and
  mocks used. Use `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the project-local approval cleanup rule in `docs/MILESTONE.md`.

## M66 - Baseline Technical Signal Characterization

Purpose: lock today output behavior before introducing the shared service.

Instructions:

- Inspect `TechnicalAnalystAgent`, `GraphAwareScoreStrategy`,
  `tests/unit/test_analyst_agents.py`, `tests/unit/test_graph_backtesting.py`,
  and `tests/unit/test_strategy_ranking.py`.
- Add characterization tests for the current technical analyst rule behavior:
  backtest signal override, feature-formula score, bounded report score,
  confidence fallback, key points, and source IDs.
- Add characterization tests for the graph-aware SMA spread behavior:
  missing fast/slow SMA returns no technical score, valid fast/slow SMA returns
  the same quantized spread, and graph-aware combined scores remain unchanged.
- Keep production code changes minimal and only add test helpers when needed.
- Do not create `TechnicalSignalService` in this milestone.
- Do not modify strategy formulas, thresholds, ranking sort order, LLM prompts,
  or allocation behavior.

Expected code shape:

- Tests should pin observable behavior instead of copying large implementation
  blocks.
- Test fixture helpers may construct `FeatureSnapshot` instances and minimal
  backtest-signal-like values, but should avoid database setup unless the
  existing tested path requires it.

Acceptance criteria:

- Current technical analyst and graph-aware strategy behavior is covered by
  focused tests.
- Existing tests continue to pass without production behavior changes.
- `docs/MILESTONE.md` marks M66 done and M67 planned.

Verification:

```bash
uv run pytest tests/unit/test_analyst_agents.py tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M67 - TechnicalSignalService Foundation

Purpose: introduce the shared technical scoring service without wiring runtime
consumers yet.

Instructions:

- Create `packages/taurus_core/features/technical_signal.py`.
- Add immutable, DB-free result/input types:
  - `TechnicalBacktestSignal`: minimal projection of a signal id, action, and
    score.
  - `TechnicalSignalResult`: profile name, availability, raw score, bounded or
    quantized score, confidence, score source, components, missing features,
    key points, source IDs, and metadata.
- Add `TechnicalSignalService` with behavior-preserving profile methods:
  - `score_analyst_rule(snapshot, latest_signal)` for the current
    `TechnicalAnalystAgent` formula and backtest-signal override.
  - `score_sma_spread(snapshot, fast_window, slow_window)` for the current
    graph-aware SMA spread formula.
- Use the same quantization semantics as the existing consumers:
  - Analyst bounded report score uses `0.0001` precision and clamps to
    `[-1, 1]`.
  - SMA spread uses `0.00000001` precision and returns unavailable when the
    required SMA features are missing or invalid.
- Export the new types/service from `packages/taurus_core/features/__init__.py`.
- Add `tests/unit/test_technical_signal_service.py` proving parity with the M66
  characterization expectations.
- Do not refactor `TechnicalAnalystAgent` or `GraphAwareScoreStrategy` yet.

Expected code shape:

- The service must not import SQLAlchemy models, repositories, settings, LLM
  providers, strategy classes, or agent classes.
- The service should consume `FeatureSnapshot | None` and plain input values so
  strategies, agents, and future backtests can call it without database access.
- Metadata should be structured and JSON-friendly, with `Decimal` values left
  as `Decimal` until existing serializers convert them.

Acceptance criteria:

- New unit tests prove the service reproduces old technical analyst and
  graph-aware technical scores.
- No runtime consumer uses the service yet, so existing paper-run behavior is
  unchanged.
- `docs/MILESTONE.md` marks M67 done and M68 planned.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_analyst_agents.py tests/unit/test_graph_backtesting.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M68 - Core Consumer Wiring

Purpose: route the canonical technical analyst and graph-aware strategy paths
through `TechnicalSignalService`.

Instructions:

- Refactor `TechnicalAnalystAgent` so it still owns database lookups, feature
  snapshot selection, and LLM report construction, but delegates deterministic
  scoring, confidence selection, source IDs, and key-point generation to
  `TechnicalSignalService.score_analyst_rule()`.
- Convert `BacktestSignalModel` rows into `TechnicalBacktestSignal` before
  calling the service.
- Preserve the current analyst public contract:
  - `model_version="technical_rule_v1"`
  - `score_metadata.score_source=="technical_rule_v1"`
  - `source_ids` include snapshot id and optional `signal:<id>`
  - fallback `technical:none` source remains when no source exists
  - LLM context keeps current top-level keys and value meanings.
- Refactor `GraphAwareScoreStrategy` so its technical score delegates to
  `TechnicalSignalService.score_sma_spread()`.
- Preserve existing graph-aware ranking and signal payload keys. Add only
  optional nested audit metadata such as `technical_signal` if useful.
- Do not migrate `BlendedScoreStrategy` or `MovingAverageCrossoverStrategy`.
- Do not change `configs/strategies/graph_aware_score_v1.yaml` thresholds,
  weights, or target behavior.

Expected code shape:

- `TechnicalAnalystAgent` should no longer contain its own raw scoring formula
  except possibly thin compatibility wrappers used by tests.
- `GraphAwareScoreStrategy` should keep its private `_technical_score()` public
  behavior for local callers/tests, but its implementation should call the
  shared service.
- Any added metadata should make the scoring profile visible without changing
  existing downstream allocation inputs.

Acceptance criteria:

- Existing analyst and graph-aware tests pass with no expected-value drift.
- Paper-run strategy summaries still expose `technical_score` and
  `strategy_score_by_symbol`.
- Allocation, risk, and final-decision tests do not need behavioral updates.
- `docs/MILESTONE.md` marks M68 done and M69 planned.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_analyst_agents.py tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py tests/unit/test_paper_runs.py
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M69 - Regression, Documentation, and Cleanup

Purpose: close the sequence with full regression confidence and refreshed
operator/developer documentation.

Instructions:

- Run the focused tests from M68 and `make test` if runtime budget permits.
- Update `docs/TAURUS_AGENT_ARCHITECTURE.md` so the current architecture shows
  `TechnicalFeatureService` building features and `TechnicalSignalService`
  producing deterministic technical scores for the wired consumers.
- Update `docs/TAURUS_TECHNICAL_ANALYST_AGENT_DEEP_DIVE.md` so the deep dive
  describes the actual post-refactor call path and points future technical
  experiments at `TechnicalSignalService`.
- Update any additional docs that mention technical score ownership if they
  become inaccurate during implementation, especially
  `docs/TAURUS_MONEY_MANAGEMENT_DEEP_DIVE.md` or `docs/TAURUS_USAGE_GUIDE.md`.
- Update `docs/MILESTONE.md` to mark M69 and the M66-M69 sequence complete.
- Inspect `/Users/adnaan/.codex/rules/default.rules` and perform the
  project-local approval cleanup if needed.
- Do not add new technical profiles or migrate deferred strategies during this
  closeout milestone.

Expected code shape:

- No new production feature should be introduced in M69 unless needed to fix a
  regression found by tests.
- Documentation should describe implemented behavior, not future speculation.

Acceptance criteria:

- M66-M69 implementation is fully documented and verified.
- Architecture and deep-dive docs no longer describe duplicated score ownership
  for the wired core paths.
- Deferred items are explicitly named rather than silently implied.

Verification:

```bash
uv run pytest tests/unit/test_technical_signal_service.py tests/unit/test_analyst_agents.py tests/unit/test_graph_backtesting.py tests/unit/test_strategy_ranking.py tests/unit/test_paper_runs.py
make test
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## Deferred Work

- Add opt-in richer technical scoring profiles for research and comparison.
- Make technical profiles configurable by strategy/run/profile.
- Migrate `BlendedScoreStrategy` and `MovingAverageCrossoverStrategy` to the
  shared service after the core graph-aware path proves stable.
- Persist technical-signal audit artifacts separately from analyst reports or
  strategy summaries if operational debugging requires it.
- Revisit symbol/run scoping for `feature_values` and `backtest_signals`; this
  sequence preserves current symbol-latest lookup behavior.
