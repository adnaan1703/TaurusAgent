# Taurus Graph Intelligence Plan

Last updated: 2026-05-27

This is the repo-specific implementation plan for adding graph-based trading
intelligence to Taurus. `docs/TAURUS_DATA_INTEGRATION.md` is treated as outside
source material and reference context, not as direct implementation authority.
When the outside plan conflicts with Taurus conventions, this document and
`docs/TAURUS_MILESTONE_TODO.md` take precedence.

## Current Repo Fit

- Backend package: `packages/taurus_core/`.
- FastAPI app: `apps/api/main.py`, with route modules registered explicitly and
  existing paths such as `/data`, `/paper`, `/runs`, and `/ui`.
- Database: SQLAlchemy models in `packages/taurus_core/db/models.py`,
  repositories in `packages/taurus_core/db/repositories.py`, and metadata-based
  migration in `scripts/migrate.py`. Taurus does not currently use Alembic.
- Config: `packages/taurus_core/config.py` with Pydantic settings and strict
  paper-trading safety validation.
- Tests: backend unit tests in `tests/unit/`; React tests under `apps/web`.
- Dashboard: React/Vite app in `apps/web`, using React Router, React Query,
  Tailwind, and API client code in `apps/web/src/api/client.ts`.
- Analyst flow: `packages/taurus_core/agents/runner.py` registers analysts from
  `packages/taurus_core/agents/roster.py`; `technical` is the default analyst.
- Risk flow: `packages/taurus_core/risk/engine.py` produces hard rule results,
  then portfolio approval still routes only to the internal `PaperBroker`.
- Existing graph source files: `configs/taurus_data/` already contains
  classifications, segments, products, dependencies, curated edges, candidate
  edges, risks, and source evidence CSVs.

## Architecture

Postgres remains the canonical source of truth. Neo4j, when added, is only a
derived read model that can be rebuilt from Postgres. Graph signals must be
explainable, disabled by default until explicitly enabled, and unable to bypass
the existing analyst, debate, trader proposal, risk review, final approval, and
paper execution path.

The intended flow is:

```text
configs/taurus_data CSVs
  -> Postgres graph tables
  -> FastAPI graph APIs
  -> React graph dashboard
  -> optional Neo4j projection
  -> graph stats
  -> GraphAnalystAgent
  -> existing debate/risk/portfolio flow
  -> PaperBroker only
```

## Milestones

Each `M20.x` milestone must be implemented in a fresh context and must stop
after its own acceptance criteria are met. Do not continue to the next
submilestone automatically.

### M20.0 - Repo-Specific Plan And Tracker

- Create this plan from the outside integration reference and real repo shape.
- Update `docs/TAURUS_MILESTONE_TODO.md` with graph milestone tracking.
- Confirm no runtime behavior changes.

Acceptance criteria:

- This document exists and references actual Taurus paths.
- `docs/TAURUS_MILESTONE_TODO.md` tracks the `M20.x` milestones.
- `docs/TAURUS_DATA_INTEGRATION.md` is documented as reference-only source
  material.
- `make test` and `make lint` pass, or failures are recorded.

### M20.1 - Postgres Graph Foundation

- Add safe graph settings in `Settings`, all disabled by default:
  `TAURUS_GRAPH_ENABLED=false`, `TAURUS_GRAPH_RISK_ENABLED=false`, and
  `TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false`.
- Add SQLAlchemy models for graph nodes, edges, evidence, edge stats, graph
  signals, and graph signal contributions.
- Add repository methods for idempotent upserts and read paths needed by the
  importer/API.
- Extend `scripts/migrate.py` using the existing metadata/create-all pattern.

Acceptance criteria:

- Migrations create graph tables on SQLite and Postgres-compatible metadata.
- Node and edge upserts are idempotent.
- No Neo4j dependency is needed.
- Existing tests pass and no trading behavior changes.

### M20.2 - TaurusData CSV Graph Importer

- Import from `configs/taurus_data/`:
  `company_industry_classifications.csv`, `company_segments.csv`,
  `company_products.csv`, `company_dependencies.csv`, `company_edges.csv`,
  `edge_candidates.csv`, `company_risks.csv`, and `source_evidence.csv`.
- Preserve source file, source row hash, confidence, inferred flag, mechanism,
  expected sign, lag range, relationship strength, and candidate/active status.
- Add a script and Make target, for example
  `make import-taurus-graph DATA_DIR=configs/taurus_data`.

Acceptance criteria:

- Sample import succeeds.
- Running the importer twice creates no duplicate nodes or edges.
- Missing optional CSVs warn without crashing.
- Candidate and active edges stay distinguishable.

### M20.3 - Graph API Vertical Slice

- Add FastAPI graph routes using current route conventions, likely under
  `/graph`.
- Implement overview, company subgraph, edge detail, edge evidence, candidate
  edges, graph signals, and bullish candidates.
- Add promote/reject endpoints only with safe local CORS handling for the
  dashboard.
- Use Postgres as the primary source.

Acceptance criteria:

- API tests pass.
- Graph overview returns counts.
- Company graph returns nodes and edges.
- APIs work with graph enabled but Neo4j absent.

### M20.4 - React Graph Dashboard Vertical Slice

- Add routes for `/graph`, `/graph/company/:symbol`, `/graph/edges/review`,
  and `/graph/signals`.
- Add API types/client methods and simple graph pages matching existing dashboard
  style.
- Include empty states, filters, edge detail drawer, and candidate review.

Acceptance criteria:

- `pnpm test` and `pnpm build` pass in `apps/web`.
- New pages compile and render empty graph data cleanly.
- Candidate review can call the approved API shape.

### M20.5 - Optional Neo4j Projection

- Add the official Neo4j Python driver and Docker Compose service only in this
  milestone.
- Project Postgres graph data into Neo4j with deterministic node and edge keys.
- Keep Neo4j disabled by default and disposable.

Acceptance criteria:

- App starts with Neo4j disabled.
- Projection rebuild is idempotent when Neo4j is available.
- Neo4j tests skip cleanly when the service is absent.
- Neo4j never writes source-of-truth data back to Postgres.

### M20.6 - Graph Statistical Validation

- Compute raw correlation, residual correlation, lead-lag score, stability
  score, and sample size from existing daily candle data.
- Store results in graph edge stats.
- Record insufficient-data reasons without crashing.
- Keep automatic candidate promotion disabled by default.

Acceptance criteria:

- Synthetic tests prove stats calculation.
- Insufficient data is skipped gracefully.
- Edge stats persist to Postgres.
- No candidate auto-promotes unless explicitly enabled.

### M20.7 - GraphAnalystAgent

- Add a deterministic `GraphAnalystAgent` and `graph` analyst key.
- Use graph edges, edge stats, and related momentum to produce explainable
  analyst output compatible with the current analyst workflow.
- Store graph signals and contributions.

Acceptance criteria:

- Graph analyst is disabled by default.
- It returns neutral output when no graph evidence exists.
- Synthetic bullish and bearish graph cases are explainable.
- Graph output cannot bypass debate, risk, or final approval.

### M20.8 - Graph-Aware Risk Checks

- Add optional graph concentration checks for basic industry, product group,
  customer industry, raw material/dependency, risk category, and correlated
  graph cluster where stats exist.
- Allow reject, reduce, or warn through existing risk result structures.

Acceptance criteria:

- Existing risk tests pass.
- Synthetic exposure can trigger reject/reduce/warn.
- Risk explanations name the graph exposure that caused the decision.

### M20.9 - Graph Observability

- Add Prometheus metrics for graph nodes, edges, candidates, imports,
  projections, stats, signals, and graph agent failures.
- Add Grafana panels only if they fit the existing JSON dashboard pattern.

Acceptance criteria:

- Existing metrics still work.
- Graph metrics are exposed on `/metrics`.
- Graph job failures are observable.

### M20.10 - Graph-Aware Backtesting

- Add graph signal loading by `as_of_date`.
- Prevent look-ahead by using only edges, evidence, and stats available on or
  before the backtest date.
- Add graph-aware strategy config combining technical and graph scores.
- Summarize graph hit rate, average return, drawdown, and performance by edge
  type.

Acceptance criteria:

- Graph-aware backtest runs.
- Tests fail if future graph data is used.
- Performance can be grouped by edge type.

## Schema Plan

Use SQLAlchemy models consistent with existing naming and timestamp patterns.
The conceptual tables are:

- `graph_nodes`: stable `node_key`, `node_type`, display name, optional symbol,
  optional ISIN, metadata, timestamps.
- `graph_edges`: stable `edge_key`, source/target node IDs, type, direction,
  expected sign, strength, evidence type, confidence, inferred flag, mechanism,
  tradability relevance, status, validity window, source file, source row hash,
  metadata, timestamps.
- `graph_edge_evidence`: evidence records attached to edges with claim/source
  metadata and confidence.
- `graph_edge_stats`: point-in-time edge statistics by window and as-of date.
- `graph_signals`: symbol-level graph signals with score, confidence, horizon,
  explanation, source agent, metadata, timestamps.
- `graph_signal_contributions`: per-edge/per-node contribution details for each
  graph signal.

Implementation should choose exact column names that fit local model style, but
must keep stable keys and idempotent upsert behavior.

## API And UI Plan

Graph API routes should follow Taurus’s existing no-`/api` route style. Use
Postgres reads by default. Neo4j-backed reads can be considered later behind
explicit settings, but must not be required for the first API or UI slice.

React dashboard pages should fit the operational UI already in `apps/web`, not
a marketing-style graph landing page. First usable UI should prioritize a
company graph view, candidate review, clear empty states, and evidence detail.

## Test Plan

- Backend: add focused `tests/unit/test_graph_*.py` files for settings,
  repositories, importer, APIs, stats, graph analyst, graph risk, and backtest
  look-ahead prevention as each milestone lands.
- UI: add Vitest/Testing Library coverage for route rendering, empty states, API
  error states, and candidate review interactions.
- Validation per backend milestone: run focused pytest, `make test`, and
  `make lint`.
- Validation per UI milestone: run `cd apps/web && pnpm test` and
  `cd apps/web && pnpm build`, plus backend checks if API contracts changed.

## Open Questions

- Whether Neo4j adds enough value for local graph browsing after Postgres-backed
  APIs are available.
- Whether candidate promote/reject should be a local-only API action or require
  a future auth layer before broader use.
- How graph backtesting should mark limitations for current classifications when
  historical classifications are unavailable.
- Whether graph risk limits should be percentages of latest paper equity,
  proposed position size, or a future portfolio-continuity model.
