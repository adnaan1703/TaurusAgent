# Taurus Graph Provenance Plan

Last updated: 2026-06-22

This document is the implementation plan for migrating TaurusAgent graph
relationship handling to the TaurusData V2 `provenance_type` contract and for
removing edge-level `confidence` from graph behavior. Each milestone below is a
standalone milestone intended to be executed in a separate Codex thread. Stop
after completing and documenting the current milestone; do not automatically
continue to the next milestone.

## Milestone Sizing Decision

This work should be split into M62-M65 rather than implemented as one broad
milestone. The change crosses several independently risky layers: persisted
schema and CSV import, promotion lifecycle and settings, graph scoring and
backtests, and final docs/regression against the bundled TaurusData outputs.
Keeping these as separate flat milestones lets each layer be migrated,
verified, documented, and stopped cleanly before the next layer begins.

## Target Behavior

TaurusAgent should consume the current TaurusData V2 edge-like outputs without
requiring edge-level `inferred`:

- `configs/taurus_data/company_edges.csv`
- `configs/taurus_data/edge_candidates.csv`
- `configs/taurus_data/company_dependencies.csv`

Every row imported into `graph_edges` should carry mandatory
`provenance_type`, with allowed values:

- `deterministic`: direct structured relationship fact from an authoritative
  API/table with no interpretation. Use this strictly.
- `derived`: deterministic rule output from deterministic inputs, such as same
  NSE classification equality.
- `inferred`: LLM, agent, analyst, annual-report interpretation, profile
  overlap, heuristic value-chain mapping, ambiguous historical rows, or any
  relationship extracted or normalized through LLM/agent curation.

Graph status should follow provenance for new or unreviewed edges:

- `deterministic` and `derived` edges become `active`.
- `inferred` edges become `candidate`.
- Manual/API/auto review status remains authoritative on later imports.

Edge `confidence` remains stored and exposed as descriptive audit/UI metadata
only. It must not control active/candidate status, promotion eligibility,
auto-promotion, graph analyst contribution weight, or graph backtest
contribution weight.

Candidate edges do not affect graph analyst, graph-aware backtests, or graph
risk calculations until promoted. Manual promotion is allowed for any candidate
edge. Auto-promotion remains opt-in and statistical, but no longer uses edge
confidence thresholds.

TaurusAgent does not import edge-like objects from `company_profiles.jsonl`
into graph tables today. Profile JSON provenance validation remains a
TaurusData responsibility; TaurusAgent docs should mention the profile contract
but the graph importer should not fail on profile JSON.

## Existing Foundation

- `docs/MILESTONE.md` is the active milestone tracker and routing source. It
  requires flat milestone IDs, one milestone at a time, completion summaries
  with assumptions/mocks, and React updates in the same milestone as API or
  artifact changes.
- `configs/taurus_data/V2_CSV_Data_Dictionary.md` already documents the new
  TaurusData V2 distinction between `confidence`, non-edge `inferred`, and
  edge-like `provenance_type`.
- `configs/taurus_data/company_edges.csv`,
  `configs/taurus_data/edge_candidates.csv`, and
  `configs/taurus_data/company_dependencies.csv` already contain
  `provenance_type` instead of edge-level `inferred`.
- `configs/taurus_data/company_segments.csv` and
  `configs/taurus_data/company_products.csv` still use non-edge `inferred` and
  must keep that file contract.
- M62 replaced `GraphEdgeModel.inferred` with required
  `GraphEdgeModel.provenance_type` and added shared validation for
  `deterministic`, `derived`, and `inferred`.
- M62 updated `GraphRepository.upsert_edge()` to accept validated
  `provenance_type` and preserve reviewed edge status during re-import.
- `scripts/migrate.py` uses SQLAlchemy metadata plus small idempotent migration
  helpers; Taurus does not use Alembic.
- `packages/taurus_core/graph/importer.py` imports all TaurusData graph CSVs,
  stores CSV confidence in `graph_edges.confidence`, requires
  `provenance_type` for edge-like relationship rows, and still maps
  segment/product `inferred` booleans into graph edge provenance.
- `packages/taurus_core/graph/stats.py` computes stats for active and candidate
  edges and currently gates auto-promotion on
  `TAURUS_GRAPH_MIN_EDGE_CONFIDENCE`.
- `packages/taurus_core/agents/graph_analyst.py` uses only active edges, but
  currently multiplies contribution weight by `edge.confidence`.
- `packages/taurus_core/backtesting/graph.py` currently multiplies backtest
  contribution scores and contribution confidence by `edge.confidence`.
- `packages/taurus_core/risk/graph_concentration.py` uses active graph edges
  for graph concentration checks.
- `apps/api/routes_graph.py`, `apps/web/src/api/types.ts`, and
  `apps/web/src/features/GraphPages.tsx` expose/display edge
  `provenance_type`.
- `packages/taurus_core/graph/neo4j_projection.py` projects
  `provenance_type` to Neo4j.
- The working tree may already contain regenerated `configs/taurus_data/*`
  outputs from TaurusData. Do not revert or regenerate those files unless the
  user explicitly asks.

## Global Rules For M62-M65

- Keep Taurus paper-only. Do not add live Kite/broker order routing.
- Keep `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` as defaults.
- Keep Kite support data-only; execution continues through local `PaperBroker`.
- Use flat milestone IDs. Do not create submilestones.
- Use `uv` for Python commands. Do not use global `pip install`.
- Update `docs/MILESTONE.md` whenever starting or completing a milestone.
- Preserve the TaurusData file contract: `company_segments.csv` and
  `company_products.csv` keep non-edge `inferred`; edge-like CSVs use
  `provenance_type`.
- Use `provenance_type` as the authoritative graph edge provenance field. Do
  not keep edge-level `inferred` as an ORM/API/UI compatibility field.
- Keep edge `confidence` as audit metadata only. Do not use it for graph
  status, promotion, graph analyst scoring, graph backtest scoring, or graph
  risk eligibility.
- Preserve reviewed statuses across re-imports. A new import may initialize
  unreviewed edge status from provenance, but must not silently undo manual or
  auto reviews stored in edge metadata.
- Candidate edges must remain visible, reviewable, and statistically testable,
  but they must not influence graph analyst, graph-aware backtests, or graph
  risk until promoted.
- Any API payload or dashboard-visible graph behavior change must include
  matching FastAPI schemas, React types/components/tests, and relevant docs in
  the same milestone.
- At milestone completion, run the stated verification commands and include a
  completion summary with assumptions made, mocks created, and mocks used. Use
  `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the repo's global approval cleanup rule from `docs/MILESTONE.md`.
- When a user asks to execute a specific milestone, implement only that
  milestone. After the requested milestone is complete, verified, cleaned up,
  and documented, stop. Do not start the next milestone, prepare unrelated code
  for the next milestone, or jump ahead automatically.

## M62 - Graph Provenance Data Contract

Purpose: make `provenance_type` the persisted and API-visible graph edge
contract while preserving current TaurusData CSV ingestion.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/db/models.py`
  - `packages/taurus_core/db/repositories.py`
  - `scripts/migrate.py`
  - `packages/taurus_core/graph/importer.py`
  - `apps/api/routes_graph.py`
  - `apps/web/src/api/types.ts`
  - `apps/web/src/features/GraphPages.tsx`
  - `packages/taurus_core/graph/neo4j_projection.py`
  - graph tests under `tests/unit/` and React graph tests
- Add a shared allowed-value contract for graph edge provenance:
  `deterministic`, `derived`, and `inferred`.
- Replace `GraphEdgeModel.inferred` with non-null
  `GraphEdgeModel.provenance_type`. Add a check constraint where supported by
  the existing SQLAlchemy/migration pattern.
- Add an idempotent migration that:
  - adds `provenance_type` to existing `graph_edges`
  - backfills from existing data conservatively when no raw provenance exists
    (`inferred=true` to `inferred`, `inferred=false` to `deterministic`)
  - physically drops `graph_edges.inferred` after backfill
- Update `GraphRepository.upsert_edge()` to accept `provenance_type`, validate
  it, and no longer accept or persist `inferred`.
- Teach the importer to require valid `provenance_type` on
  `company_edges.csv`, `edge_candidates.csv`, and `company_dependencies.csv`.
  Missing or invalid values must raise `TaurusGraphImportError`.
- Preserve non-edge CSV behavior:
  - `company_segments.csv` and `company_products.csv` still read their
    existing `inferred` boolean.
  - Those booleans map to graph edge provenance only:
    `true` becomes `inferred`, `false` becomes `deterministic`.
- Assign provenance to internal graph edges:
  - industry classification edges: `deterministic`
  - source evidence edges: `deterministic`
  - risk edges: `inferred`
- Initialize status from provenance for new or unreviewed edges:
  - `deterministic` and `derived` to `active`
  - `inferred` to `candidate`
  - existing reviewed status from `latest_review` or review history remains
    authoritative on re-import
- Update FastAPI graph responses, React graph types, graph table/detail UI, and
  React tests to expose/display `provenance_type` instead of `inferred`.
  Confidence may remain visible as metadata.
- Update Neo4j projection to project `provenance_type` and stop projecting
  `inferred`.

Expected code shape:

- Keep provenance validation close to graph model/repository/importer code, not
  duplicated ad hoc in API and UI layers.
- Do not add profile JSON ingestion or validation in TaurusAgent.
- Do not remove edge `confidence` storage or API exposure in this milestone.
- Do not change graph analyst/backtest scoring in this milestone.

Acceptance criteria:

- Current TaurusData edge-like CSVs import without requiring `inferred`.
- Import fails on missing or invalid `provenance_type` for
  `company_edges.csv`, `edge_candidates.csv`, and `company_dependencies.csv`.
- `company_segments.csv` and `company_products.csv` still parse their
  non-edge `inferred` columns.
- `graph_edges` persists `provenance_type` and no longer has an `inferred`
  column in the ORM or migrated Postgres schema.
- API, React graph UI, and Neo4j projection expose `provenance_type`.
- Re-import does not undo reviewed promoted/rejected edge statuses.

Verification:

```bash
uv run pytest tests/unit/test_migrations.py tests/unit/test_graph_importer.py tests/unit/test_graph_repository.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py -q
make test-ui
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

### M62 Completion Summary

- Assumptions made: `provenance_type` should be required for
  `company_edges.csv`, `edge_candidates.csv`, and `company_dependencies.csv`;
  `deterministic` and `derived` edges should initialize as `active` and
  `inferred` edges as `candidate`; reviewed status from `latest_review` or
  review history should survive re-import; segment/product `inferred` remains a
  source-file boolean and maps only into edge provenance; confidence remains
  stored and exposed as audit metadata until later milestones remove behavioral
  confidence use.
- Mocks created: None.
- Mocks used: Existing Postgres test databases, FastAPI `TestClient`, React
  fetch stubs, fake Neo4j driver, and deterministic graph CSV fixtures.

## M63 - Promotion Lifecycle And Confidence Setting Cleanup

Purpose: remove confidence thresholds from graph promotion while keeping manual
review and opt-in statistical auto-promotion safe.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/config.py`
  - `packages/taurus_core/graph/stats.py`
  - `apps/api/routes_graph.py`
  - `docs/TAURUS_COMMANDS.md`
  - tests covering config, graph stats, graph API, and observability
- Remove `TAURUS_GRAPH_MIN_EDGE_CONFIDENCE` from settings, tests, and docs.
- Update graph auto-promotion so it no longer checks `edge.confidence`.
- Keep these auto-promotion guards:
  - `TAURUS_GRAPH_AUTO_PROMOTE_EDGES=true`
  - edge status is `candidate`
  - minimum sample size passes
  - stability threshold passes
  - residual-correlation or lead-lag threshold passes
- Keep manual API/UI promotion allowed for any candidate edge, regardless of
  confidence and regardless of whether stats exist.
- Ensure promotion updates only edge status/review metadata. It must not
  rewrite `provenance_type`.
- Ensure all candidate edges are eligible for review and possible promotion;
  there must be no confidence eligibility prefilter.
- Update metrics or progress payload tests only if their expected promotion
  summaries change.

Expected code shape:

- `confidence` can remain in promotion response payloads as metadata, but no
  branch in promotion code should compare it to a threshold.
- Auto-promotion review notes should mention statistical validation, not
  confidence.
- Leave graph analyst/backtest score formulas for M64.

Acceptance criteria:

- Low-confidence inferred candidate fixtures can auto-promote when statistical
  thresholds pass and auto-promotion is enabled.
- Low-confidence inferred candidate fixtures can be manually promoted without
  stats.
- `TAURUS_GRAPH_MIN_EDGE_CONFIDENCE` is absent from config, config tests, and
  operator docs.
- Existing default remains safe: auto-promotion is still disabled unless
  explicitly enabled.

Verification:

```bash
uv run pytest tests/unit/test_config.py tests/unit/test_graph_stats.py tests/unit/test_graph_api.py tests/unit/test_graph_observability.py -q
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M64 - Graph Scoring Without Edge Confidence

Purpose: make graph analyst and graph backtest scoring depend on relationship
strength and statistical validation, not TaurusData edge confidence.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/agents/graph_analyst.py`
  - `packages/taurus_core/backtesting/graph.py`
  - `packages/taurus_core/risk/graph_concentration.py`
  - `packages/taurus_core/strategies/graph_aware.py`
  - graph analyst, graph backtest, graph risk, and paper-run tests
- Remove `edge.confidence` from graph analyst contribution weights.
- Remove `edge.confidence` from graph backtest contribution score and
  contribution confidence formulas.
- Use relationship strength plus graph-stat validation for weighting:
  - strength continues to come from `relationship_strength` when available
  - stats weight continues to come from correlation, lead-lag, and stability
  - evidence weight can remain part of backtest scoring where it already exists
- Keep graph signal/report `confidence` as an output confidence concept. It may
  depend on contribution count and post-change contribution weights, but not on
  edge CSV confidence.
- Include `provenance_type` and raw edge confidence metadata in contribution
  metadata for auditability, clearly labeled as metadata rather than behavior.
- Add regression tests proving two otherwise identical active edges with
  different CSV confidence values produce the same score contribution.
- Add regression tests proving inferred candidate edges do not affect graph
  analyst, graph backtests, or graph risk until promoted.
- Update graph strategy tests only if expected graph signal confidence changes
  because of the new weighting.

Expected code shape:

- Do not introduce provenance multipliers. The selected policy is strength plus
  stats, with provenance stored for interpretation.
- Do not reintroduce candidate status weights in production analyst/risk paths;
  candidates should be ignored until promoted.
- Keep non-graph confidence concepts untouched, such as analyst confidence,
  trader confidence, source-evidence confidence, and sentiment/news confidence.

Acceptance criteria:

- Edge confidence cannot alter graph analyst score contributions.
- Edge confidence cannot alter graph backtest contribution scores.
- Candidate edges remain excluded from production graph analyst, backtest, and
  risk calculations until promoted.
- Promoted inferred edges can contribute like other active edges, using
  strength and stats.

Verification:

```bash
uv run pytest tests/unit/test_graph_analyst.py tests/unit/test_graph_backtesting.py tests/unit/test_graph_risk.py tests/unit/test_paper_runs.py -q
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M65 - Regression, Documentation, And Operator Closeout

Purpose: prove the whole provenance migration against bundled TaurusData
outputs and refresh operator/developer documentation.

Instructions:

- Read these source areas before editing:
  - `docs/MILESTONE.md`
  - `docs/TAURUS_GRAPH_ANALYST_AGENT_DEEP_DIVE.md`
  - `docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md`
  - `docs/TAURUS_DATABASE_TABLES.md`
  - `docs/TAURUS_COMMANDS.md`
  - `docs/TAURUS_USAGE_GUIDE.md`
  - `configs/taurus_data/V2_CSV_Data_Dictionary.md`
- Refresh docs so they distinguish:
  - `provenance_type`: deterministic/derived/inferred relationship provenance
  - `confidence`: descriptive metadata and non-graph output confidence,
    not graph edge eligibility
  - `evidence_type`: evidence/source basis
  - `status`: active/candidate/rejected review lifecycle
- Remove stale docs that say candidate promotion depends on
  `TAURUS_GRAPH_MIN_EDGE_CONFIDENCE` or imported edge confidence.
- Document that `company_profiles.jsonl` edge-like objects are a TaurusData
  provenance contract, but TaurusAgent imports the flattened CSVs rather than
  profile arrays.
- Run an import smoke against `configs/taurus_data` using local Postgres. If
  Postgres is not running, start the local stack with `make dev-up` before the
  smoke, and stop only if the user asks.
- Verify the current bundled CSV headers:
  - edge-like CSVs have `provenance_type`
  - segment/product CSVs still have `inferred`
- Run the full Python and React regression suites.
- Inspect `/Users/adnaan/.codex/rules/default.rules` during cleanup and move
  accidental Taurus-specific approvals into `.codex/rules/default.rules` if
  any are found after the user's custom marker.
- Update `docs/MILESTONE.md` to close M65 and the M62-M65 sequence.

Expected code shape:

- Documentation updates should describe the final behavior, not the interim
  migration path.
- Do not regenerate TaurusData outputs unless the user explicitly asks.
- Do not create a commit unless the user explicitly asks.

Acceptance criteria:

- `make import-taurus-graph DATA_DIR=configs/taurus_data` succeeds against the
  current bundled TaurusData V2 files.
- No edge-like consumer still requires edge-level `inferred`.
- Segment/product `inferred` file contracts are documented as intentionally
  preserved.
- Docs no longer describe confidence as a promotion gate or graph-scoring
  input.
- M62-M65 are all documented with completion summaries in `docs/MILESTONE.md`.

Verification:

```bash
make migrate
make import-taurus-graph DATA_DIR=configs/taurus_data
make test
make test-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used
