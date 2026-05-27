Below is a **Codex CLI–ready execution plan** for implementing the Taurus graph intelligence system using:

```text
Postgres = canonical source of truth
Neo4j = derived graph read model
React dashboard = graph visualization and review UI
GraphAnalystAgent = relationship/dependency analyst
PaperBroker = still the only execution path
```

Codex CLI is a good fit for this because it can inspect, edit, and run code inside the selected local repo, and it supports both interactive and one-shot prompt workflows from the terminal. ([OpenAI Developers][1]) Neo4j also fits your chosen approach because it has an official Docker image and an official Python driver. ([Graph Database & Analytics][2])

---

# Taurus Graph Intelligence Implementation Plan

## Final architecture decision

```text
TaurusData CSVs
   ↓
Postgres canonical graph tables
   ↓
Neo4j projection / read model
   ↓
FastAPI graph APIs
   ↓
React graph dashboard
   ↓
GraphAnalystAgent
   ↓
Bull/Bear debate
   ↓
Risk committee
   ↓
PaperBroker only
```

Core rule:

```text
Postgres owns truth.
Neo4j is disposable/rebuildable.
No live-money execution.
No graph signal can bypass the risk committee.
```

---

# 0. How to run this with Codex CLI

Use one milestone per Codex run. Do **not** ask Codex to implement the whole system in one pass.
Use this master instruction at the top of every Codex prompt:

```text
You are working in the TaurusAgent repository.

Hard constraints:
- Keep Taurus paper-trading-first.
- Do not enable or introduce live broker execution.
- Use uv for Python dependency management.
- Preserve FastAPI + taurus_core + React dashboard architecture.
- Prefer deterministic/heuristic logic by default.
- LLM usage must remain optional, schema-bound, and mock-provider-compatible.
- Do not introduce unrelated rewrites.
- Inspect the existing project structure, migration style, config style, tests, and naming conventions before editing.
- Add or update tests for every new backend module.
- Keep Neo4j as a derived read model; Postgres remains canonical.
- All graph signals must be explainable and must not bypass existing risk approval.
```

---

# 1. Milestone 0 — Repository discovery and design document

## Goal

Make Codex inspect your real repo before implementation. This prevents it from inventing paths, migration patterns, config styles, or test conventions.

## Codex prompt

```text
Using the master constraints above, inspect the TaurusAgent repository and produce an implementation design note for Taurus Graph Intelligence.

Do not edit source code yet except for adding a planning document.

Tasks:
1. Identify existing backend package layout, especially packages/taurus_core.
2. Identify existing FastAPI route registration style.
3. Identify existing SQLAlchemy model and migration pattern.
4. Identify existing config/settings pattern.
5. Identify existing pytest layout and fixtures.
6. Identify existing React dashboard structure.
7. Identify existing analyst agent base classes and analyst registration pattern.
8. Identify existing risk committee flow.
9. Identify existing Docker Compose services.
10. Create docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md with:
   - confirmed repo-specific file locations
   - implementation milestones
   - schema plan
   - API plan
   - UI plan
   - test plan
   - open questions
11. Update docs/TAURUS_MILESTONE_TODO.md only if it already exists and has an obvious place for this milestone.

Acceptance criteria:
- No runtime behavior changes.
- New planning doc exists.
- The plan references actual repo paths discovered from the codebase.
- No live trading behavior is introduced.
```

## Expected output

```text
docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
```

Do not skip this milestone.

---

# 2. Milestone 1 — Add graph configuration and Neo4j Docker service

## Goal

Add Neo4j as infrastructure, but do not depend on it for app startup yet.

Neo4j should be optional:

```text
TAURUS_GRAPH_ENABLED=false by default
TAURUS_NEO4J_ENABLED=false by default
```

## Target behavior

```text
Postgres app works even if Neo4j is not running.
Neo4j service can be started through Docker Compose.
FastAPI readiness does not fail when Neo4j is disabled.
```

## Suggested config

```env
TAURUS_GRAPH_ENABLED=false
TAURUS_NEO4J_ENABLED=false
TAURUS_NEO4J_URI=bolt://neo4j:7687
TAURUS_NEO4J_USER=neo4j
TAURUS_NEO4J_PASSWORD=taurus_dev_neo4j_password
TAURUS_NEO4J_DATABASE=neo4j
```

Use Neo4j Community Edition for development unless your repo already has a policy requiring exact image pinning. DockerHub hosts an official Neo4j image, and the official operations docs describe Neo4j Docker setup. ([Graph Database & Analytics][2])

## Codex prompt

```text
Using the master constraints above, implement Milestone 1: optional Neo4j infrastructure configuration.

Tasks:
1. Inspect existing settings/config style.
2. Add graph-related settings with safe defaults:
   - TAURUS_GRAPH_ENABLED=false
   - TAURUS_NEO4J_ENABLED=false
   - TAURUS_NEO4J_URI
   - TAURUS_NEO4J_USER
   - TAURUS_NEO4J_PASSWORD
   - TAURUS_NEO4J_DATABASE
3. Add a Neo4j service to Docker Compose in a way consistent with the existing compose file.
4. Do not make the app require Neo4j at startup.
5. Add a small Neo4j connection helper only if it fits existing dependency style.
6. If adding the neo4j Python package is needed, use uv and update the appropriate lock/project files.
7. Add tests for settings defaults.
8. Update docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md with the actual implementation notes.

Acceptance criteria:
- Existing tests still pass.
- App starts with Neo4j disabled.
- Docker Compose contains an optional Neo4j service.
- No graph behavior is enabled by default.
- No live trading behavior is introduced.
```

## Likely dependency

```bash
uv add neo4j
```

The official Neo4j Python driver is the supported Python library for connecting to Neo4j from Python apps. ([Graph Database & Analytics][3])

---

# 3. Milestone 2 — Postgres canonical graph schema

## Goal

Create canonical graph tables in Postgres.

Postgres should store:

```text
nodes
edges
evidence links
edge statistics
graph signals
graph signal contributions
```

## Required tables

Use existing naming conventions, but conceptually:

```text
graph_nodes
graph_edges
graph_edge_evidence
graph_edge_stats
graph_signals
graph_signal_contributions
```

## Conceptual schema

### `graph_nodes`

```text
id
node_key              unique stable key, e.g. company:NSE:TCS
node_type             company, industry, product, segment, commodity, macro_factor, risk, index, evidence
display_name
symbol
isin
metadata_json
created_at
updated_at
```

### `graph_edges`

```text
id
source_node_id
target_node_id
edge_key              unique stable key
edge_type             classified_as, has_segment, depends_on, peer_candidate, etc.
direction             source_to_target, bidirectional, unknown
expected_sign         positive, negative, mixed, unknown
relationship_strength high, medium, low, unknown
evidence_type         disclosed, nse_classification, inferred_from_industry, curated_profile_overlap
confidence
inferred
mechanism
tradability_relevance
status                candidate, active, rejected, archived
valid_from
valid_to
source_file
source_row_hash
metadata_json
created_at
updated_at
```

### `graph_edge_evidence`

```text
id
edge_id
evidence_id
source_title
source_type
source_date
source_url_or_reference
page_or_section
claim_summary
confidence
created_at
```

### `graph_edge_stats`

```text
id
edge_id
as_of_date
window_days
raw_corr
residual_corr
partial_corr
beta_source_to_target
beta_target_to_source
lead_lag_days
lead_lag_score
cointegration_pvalue
spread_halflife_days
stability_score
sample_size
created_at
updated_at
```

### `graph_signals`

```text
id
symbol
as_of_date
signal_type
direction             bullish, bearish, neutral
raw_score
normalized_score
confidence
horizon_min_days
horizon_max_days
explanation
created_by_agent
metadata_json
created_at
```

### `graph_signal_contributions`

```text
id
signal_id
source_node_id
target_node_id
edge_id
contribution_type
score_contribution
explanation
metadata_json
created_at
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 2: canonical Postgres graph schema.

Tasks:
1. Inspect existing SQLAlchemy model and migration pattern.
2. Add graph models using existing conventions.
3. Add migrations or schema initialization using the repo's existing pattern.
4. Add repository interfaces/classes for:
   - upsert_node
   - upsert_edge
   - get_company_graph
   - list_edges_for_symbol
   - get_edge_evidence
   - insert_edge_stats
   - insert_graph_signal
5. Add Pydantic schemas if the repo uses separate API schemas.
6. Add unit tests for model creation and repository upsert behavior.
7. Ensure edge uniqueness is deterministic through edge_key or equivalent.
8. Keep all graph features disabled unless explicitly called.
9. Update docs.

Acceptance criteria:
- Postgres graph tables can be created through the existing migration/init process.
- Repository tests pass.
- Upserting the same node/edge twice is idempotent.
- No Neo4j dependency is required for Postgres graph tests.
- No live trading behavior is introduced.
```

---

# 4. Milestone 3 — TaurusData CSV graph importer

## Goal

Import your existing TaurusData V2 CSVs into Postgres graph tables.

## Input files

```text
company_industry_classifications.csv
company_segments.csv
company_products.csv
company_dependencies.csv
company_edges.csv
edge_candidates.csv
company_risks.csv
source_evidence.csv
```

## Mapping rules

### `company_industry_classifications.csv`

Create nodes:

```text
Company
NSE Macro
NSE Sector
NSE Industry
NSE Basic Industry
Index
```

Create edges:

```text
Company -> CLASSIFIED_AS -> NSE Basic Industry
NSE Basic Industry -> PART_OF -> NSE Industry
NSE Industry -> PART_OF -> NSE Sector
NSE Sector -> PART_OF -> NSE Macro
Company -> MEMBER_OF -> Index
```

### `company_segments.csv`

Create edges:

```text
Company -> HAS_SEGMENT -> Segment
Segment -> OFFERS_PRODUCT_OR_SERVICE -> Product/Service
```

Revenue share should become `metadata_json.materiality`.

### `company_products.csv`

Create edges:

```text
Company -> OFFERS_PRODUCT -> Product
Product -> BELONGS_TO_PRODUCT_GROUP -> Normalized Product Group
Product -> SERVES_CUSTOMER_INDUSTRY -> Customer Industry
```

### `company_dependencies.csv`

Create edges:

```text
Company -> DEPENDS_ON -> Dependency Node
Company -> SERVES -> Customer Industry
Company -> USES_INPUT -> Raw Material / Commodity
```

Preserve:

```text
importance
expected_sign
lag range
mechanism
evidence_type
confidence
inferred
```

### `company_edges.csv`

Import as:

```text
status = active
```

unless confidence is very low, then:

```text
status = candidate
```

### `edge_candidates.csv`

Import as:

```text
status = candidate
tradable = false
```

### `company_risks.csv`

Create edges:

```text
Company -> EXPOSED_TO_RISK -> Risk
Risk -> AFFECTS_SEGMENT -> Segment
```

### `source_evidence.csv`

Create evidence records and attach them when possible.

## Codex prompt

```text
Using the master constraints above, implement Milestone 3: TaurusData CSV importer into canonical Postgres graph tables.

Tasks:
1. Create a graph importer module under the existing taurus_core package structure.
2. Implement import support for:
   - company_industry_classifications.csv
   - company_segments.csv
   - company_products.csv
   - company_dependencies.csv
   - company_edges.csv
   - edge_candidates.csv
   - company_risks.csv
   - source_evidence.csv
3. Preserve source_file and source_row_hash for every imported edge.
4. Make imports idempotent.
5. Add a CLI/management command consistent with the repo's existing command style, for example:
   uv run python -m taurus_core.graph.import_taurus_data --input-dir batch_outputs/v2
6. Do not require all CSVs to exist. Missing optional files should produce warnings, not crashes.
7. Add fixtures with tiny sample CSVs.
8. Add tests for:
   - node creation
   - edge creation
   - idempotency
   - confidence/status mapping
   - source evidence import
9. Update docs with importer usage.

Acceptance criteria:
- A sample TaurusData directory imports successfully.
- Running the importer twice does not duplicate nodes or edges.
- Candidate edges remain candidate edges.
- Active curated edges remain distinguishable from candidates.
- Missing CSVs are handled gracefully.
```

---

# 5. Milestone 4 — Neo4j projection / read model

## Goal

Project the Postgres graph into Neo4j.

Neo4j should be rebuildable:

```text
Postgres -> Neo4j
```

Never:

```text
Neo4j -> Postgres truth
```

## Neo4j node labels

```text
Company
Industry
Product
ProductGroup
Segment
Commodity
MacroFactor
Risk
Index
Evidence
GenericNode
```

## Neo4j relationship types

```text
CLASSIFIED_AS
PART_OF
MEMBER_OF
HAS_SEGMENT
OFFERS_PRODUCT
BELONGS_TO_PRODUCT_GROUP
SERVES_CUSTOMER_INDUSTRY
DEPENDS_ON
USES_INPUT
SERVES
EXPOSED_TO_RISK
RELATED_TO
SUPPORTED_BY
```

## Projection behavior

```text
MERGE nodes by node_key
MERGE relationships by edge_key
Set all properties from Postgres
Optionally delete or mark stale relationships not present in latest projection
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 4: Neo4j graph projection.

Tasks:
1. Add a Neo4j graph repository/projection module using the official neo4j Python driver.
2. Keep Neo4j optional and disabled by default.
3. Implement:
   - connect/check health
   - create constraints/indexes if supported by the selected Neo4j version
   - project_nodes_from_postgres
   - project_edges_from_postgres
   - rebuild_projection
   - project_company_subgraph
4. Use deterministic node_key and edge_key.
5. Do not write source-of-truth data back from Neo4j to Postgres.
6. Add integration-test scaffolding but skip Neo4j tests automatically if Neo4j is unavailable.
7. Add a CLI/management command:
   uv run python -m taurus_core.graph.project_neo4j --rebuild
8. Update Docker Compose docs.
9. Update docs with rebuild instructions.

Acceptance criteria:
- App still starts with Neo4j disabled.
- Neo4j projection can be rebuilt from Postgres.
- Projection is idempotent.
- Tests do not fail when Neo4j is absent.
- No live trading behavior is introduced.
```

---

# 6. Milestone 5 — FastAPI graph APIs

## Goal

Expose graph data to the React dashboard and analyst system.

## Required endpoints

Use your existing API route conventions, but conceptually:

```http
GET /api/graph/overview
GET /api/graph/company/{symbol}?depth=1&status=active,candidate
GET /api/graph/edges/{edge_id}
GET /api/graph/edges/{edge_id}/evidence
GET /api/graph/edges/candidates
POST /api/graph/edges/{edge_id}/promote
POST /api/graph/edges/{edge_id}/reject
GET /api/graph/signals/{symbol}
GET /api/graph/signals/bullish-candidates
```

## Response shape for graph visualization

```json
{
  "center_symbol": "ABC",
  "nodes": [
    {
      "id": "company:NSE:ABC",
      "type": "company",
      "label": "ABC Ltd",
      "symbol": "ABC",
      "metadata": {}
    }
  ],
  "edges": [
    {
      "id": "edge:...",
      "source": "company:NSE:ABC",
      "target": "industry:nse_basic:pharmaceuticals",
      "type": "CLASSIFIED_AS",
      "confidence": 0.95,
      "status": "active",
      "expected_sign": "mixed",
      "inferred": false,
      "metadata": {}
    }
  ]
}
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 5: FastAPI graph APIs.

Tasks:
1. Inspect existing API route registration and dependency injection style.
2. Add graph routes following existing conventions.
3. Implement endpoints:
   - graph overview
   - company subgraph
   - edge details
   - edge evidence
   - candidate edge list
   - promote edge
   - reject edge
   - graph signal for symbol
   - bullish graph candidates
4. Use Postgres as the primary API source.
5. Optionally allow Neo4j-backed reads only behind TAURUS_NEO4J_ENABLED, but default to Postgres reads.
6. Add Pydantic response schemas.
7. Add API tests.
8. Add Prometheus metrics if existing route metrics pattern makes this straightforward.
9. Update docs.

Acceptance criteria:
- API tests pass.
- Graph overview returns counts.
- Company subgraph returns nodes and edges.
- Candidate edge promotion/rejection updates status in Postgres.
- APIs work without Neo4j.
- No live trading behavior is introduced.
```

---

# 7. Milestone 6 — React graph dashboard

## Goal

Add graph visualization to the existing React dashboard.

## UI pages

```text
/graph
/graph/company/:symbol
/graph/edges/review
/graph/signals
```

## Required dashboard panels

### Graph overview

Show:

```text
node count
edge count
active edge count
candidate edge count
rejected edge count
latest graph rebuild time
latest Neo4j projection time
```

### Company graph page

User selects a symbol and sees:

```text
company node
1-hop relationships
optional 2-hop expansion
edge confidence
edge status
edge type
expected sign
inferred/disclosed marker
```

### Edge detail drawer

On edge click, show:

```text
mechanism
tradability relevance
confidence
expected sign
relationship strength
evidence type
source
latest stats if available
promote/reject buttons if candidate
```

### Candidate edge review

A review table:

```text
source symbol
target symbol
candidate edge type
basis
confidence
inferred
measured correlation if available
promote
reject
```

### Graph signal panel

For each stock:

```text
graph score
direction
confidence
positive contributors
negative contributors
risk warnings
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 6: React graph dashboard.

Tasks:
1. Inspect existing React app structure, routing, API client, React Query usage, Tailwind patterns, and charting conventions.
2. Add graph dashboard routes/pages:
   - GraphOverviewPage
   - CompanyGraphPage
   - EdgeReviewPage
   - GraphSignalsPage
3. Add API client functions for the graph endpoints.
4. Add a graph visualization component.
5. Prefer a maintained graph visualization library only if the project does not already have one.
6. Keep the first version simple:
   - pan/zoom
   - click node
   - click edge
   - edge detail drawer
   - confidence/status filters
7. Add tests with Vitest/Testing Library where practical.
8. Do not disturb existing dashboard routes.
9. Update docs with UI usage.

Acceptance criteria:
- Existing UI tests pass.
- New graph pages compile.
- Company graph page can render API nodes/edges.
- Edge review page can promote/reject candidate edges.
- Dashboard remains usable if graph API returns empty data.
```

---

# 8. Milestone 7 — Statistical validation engine

## Goal

Compute whether graph relationships are statistically useful.

Start with:

```text
raw rolling correlation
market-adjusted residual correlation
sector-adjusted residual correlation if sector index data exists
lead-lag correlation
correlation stability
```

Add cointegration later, after the base engine is stable.

## Required calculations

For each company-company edge or candidate pair:

```text
window_days = 60, 120, 252
raw_corr
residual_corr
lead_lag_days
lead_lag_score
stability_score
sample_size
```

## Residual return logic

```text
stock_return
minus market_beta * market_return
minus sector_beta * sector_return, if available
```

If sector index return is not available, skip sector residualization gracefully.

## Promotion logic

Candidate edges should be promotable if:

```text
confidence >= threshold
sample_size >= threshold
abs(residual_corr) >= threshold
stability_score >= threshold
or lead_lag_score >= threshold
```

But automatic promotion should initially be disabled.

Use:

```text
TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 7: graph statistical validation engine.

Tasks:
1. Inspect existing price/feature storage and backtesting data access patterns.
2. Add graph stats modules:
   - return calculator
   - market residualizer
   - rolling correlation calculator
   - lead-lag calculator
   - edge stat calculator
3. Store results in graph_edge_stats.
4. Add config thresholds:
   - TAURUS_GRAPH_STATS_WINDOWS=60,120,252
   - TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false
   - TAURUS_GRAPH_MIN_EDGE_SAMPLE_SIZE
   - TAURUS_GRAPH_MIN_RESIDUAL_CORR
   - TAURUS_GRAPH_MIN_STABILITY_SCORE
5. Add a CLI/management command:
   uv run python -m taurus_core.graph.compute_edge_stats --as-of YYYY-MM-DD
6. Do not require perfect market data; skip edges with insufficient data and record reason.
7. Add tests with tiny synthetic price fixtures.
8. Update docs.

Acceptance criteria:
- Stats engine computes rolling correlation for sample edges.
- Insufficient data does not crash the job.
- Edge stats are written to Postgres.
- No candidate is auto-promoted unless explicitly enabled.
- No live trading behavior is introduced.
```

---

# 9. Milestone 8 — GraphAnalystAgent

## Goal

Add a new deterministic graph-aware analyst.

Do **not** overload `TechnicalAnalystAgent`.

New agent:

```text
GraphAnalystAgent
```

or:

```text
RelationshipAnalystAgent
```

Recommended name:

```text
GraphAnalystAgent
```

## Agent input

```text
symbol
as_of_date
latest graph edges
latest edge stats
related company abnormal moves
dependency edges
candidate/active relationship scores
current portfolio exposure if available
```

## Agent output

Fit your existing `LLMAnalystOutput` style.

Conceptual output:

```json
{
  "agent": "graph",
  "symbol": "ABC",
  "direction": "bullish",
  "score": 0.64,
  "confidence": 0.72,
  "horizon_days_min": 1,
  "horizon_days_max": 5,
  "summary": "Bullish graph signal from peer momentum and customer industry exposure.",
  "positive_contributors": [],
  "negative_contributors": [],
  "risk_warnings": []
}
```

## Deterministic scoring formula

```text
graph_score =
    peer_momentum_score
  + dependency_momentum_score
  + customer_industry_score
  + supplier_input_score
  + pair_spread_score
  - weak_evidence_penalty
  - unstable_relationship_penalty
  - concentration_penalty
```

Each contribution should be stored in:

```text
graph_signal_contributions
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 8: GraphAnalystAgent.

Tasks:
1. Inspect existing analyst base class, output schemas, registration mechanism, and TAURUS_ENABLED_ANALYSTS behavior.
2. Add GraphAnalystAgent using existing agent conventions.
3. Keep the agent deterministic by default.
4. Add graph scoring modules:
   - peer_momentum_scorer
   - dependency_signal_scorer
   - graph_risk_scorer
   - graph_signal_scorer
5. Use graph_edges and graph_edge_stats from Postgres.
6. Produce structured output compatible with the existing analyst workflow.
7. Store graph_signals and graph_signal_contributions.
8. Add config:
   - TAURUS_ENABLED_ANALYSTS can include graph
   - graph analyst disabled unless enabled
9. LLM provider may format the report, but must not invent edges or override deterministic score.
10. Add tests:
   - neutral output when no graph data exists
   - bullish output from synthetic positive peer momentum
   - bearish output from synthetic negative dependency signal
   - fallback behavior when LLM provider fails
11. Update docs.

Acceptance criteria:
- Existing analyst tests pass.
- GraphAnalystAgent can be enabled via TAURUS_ENABLED_ANALYSTS.
- GraphAnalystAgent returns neutral if no graph evidence exists.
- Graph signal is explainable through contributions.
- No graph signal bypasses bull/bear debate or risk committee.
- No live trading behavior is introduced.
```

---

# 10. Milestone 9 — Graph-aware risk committee

## Goal

Use the graph to prevent hidden concentration.

This is especially important because your universe is around 200 Shariah-compliant NSE stocks, so concentration can sneak in through:

```text
same basic industry
same customer industry
same raw material
same macro factor
same risk category
same graph cluster
```

## Risk checks

Add configurable limits:

```yaml
graph_risk:
  max_same_basic_industry_exposure_pct: 25
  max_same_customer_industry_exposure_pct: 30
  max_same_raw_material_exposure_pct: 30
  max_same_risk_category_exposure_pct: 25
  max_same_graph_cluster_exposure_pct: 35
```

## Risk output example

```text
Rejected or reduced:
  Proposed long ABC
Reason:
  Portfolio already has high exposure to same customer-industry cluster.
  Adding ABC would raise cluster exposure from 32% to 41%.
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 9: graph-aware risk committee checks.

Tasks:
1. Inspect existing risk committee and paper trade proposal flow.
2. Add graph exposure checks without breaking existing risk checks.
3. Check proposed trades against:
   - same NSE basic industry
   - same product group
   - same customer industry
   - same dependency/raw material
   - same risk category
   - highly correlated graph cluster if stats exist
4. Make limits configurable.
5. Risk committee may:
   - approve
   - reject
   - reduce suggested size
   - attach warning
6. Add explanation strings to risk decisions.
7. Add tests with synthetic portfolio exposure.
8. Ensure paper broker remains the only execution path.
9. Update docs.

Acceptance criteria:
- Existing risk tests pass.
- Proposed trade can be rejected due to graph concentration.
- Proposed trade can be size-reduced due to graph concentration.
- Risk decision explains which graph exposure caused the action.
- No live trading behavior is introduced.
```

---

# 11. Milestone 10 — Observability

## Goal

Add Prometheus/Grafana visibility for graph health.

## Suggested metrics

```text
taurus_graph_nodes_total
taurus_graph_edges_total
taurus_graph_candidate_edges_total
taurus_graph_active_edges_total
taurus_graph_rejected_edges_total
taurus_graph_import_duration_seconds
taurus_graph_projection_duration_seconds
taurus_graph_projection_failures_total
taurus_graph_edge_stats_total
taurus_graph_edge_stats_stale_total
taurus_graph_signals_total
taurus_graph_bullish_signals_total
taurus_graph_bearish_signals_total
taurus_graph_signal_confidence_avg
taurus_graph_evidence_missing_total
taurus_graph_agent_failures_total
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 10: graph observability.

Tasks:
1. Inspect existing Prometheus metrics pattern.
2. Add graph import/projection/stat/signal metrics.
3. Add metrics to:
   - TaurusData import job
   - Neo4j projection job
   - edge stats job
   - GraphAnalystAgent
   - graph APIs if appropriate
4. Add or update Grafana dashboard JSON only if existing dashboard JSON files are present.
5. Add tests where metrics are testable.
6. Update docs.

Acceptance criteria:
- Existing metrics still work.
- Graph metrics are exposed.
- Graph job failures are observable.
- No live trading behavior is introduced.
```

---

# 12. Milestone 11 — Backtesting graph signals

## Goal

Backtest graph signals without look-ahead bias.

## Strict rules

```text
Do not use an edge before its source was available.
Do not use annual report data before disseminationDateTime.
Do not use future edge stats.
Do not use current classifications for old dates unless no historical alternative exists and the backtest marks this limitation.
Do not allow candidate promotion based on future performance.
```

## Codex prompt

```text
Using the master constraints above, implement Milestone 11: graph signal backtesting support.

Tasks:
1. Inspect existing backtesting engine.
2. Add graph signal feature loading by as_of_date.
3. Ensure graph_edges have available_to_model_at or equivalent.
4. Ensure graph_edge_stats are loaded only if as_of_date <= backtest date.
5. Add a graph-aware strategy config that can combine:
   - technical score
   - graph score
   - optional fundamentals/news/sentiment scores if available
6. Add tests for look-ahead prevention.
7. Add backtest summary fields:
   - graph_signal_hit_rate
   - graph_signal_avg_return
   - graph_signal_drawdown
   - performance_by_edge_type
8. Update docs.

Acceptance criteria:
- Backtest can run with graph signals.
- Look-ahead test fails if future graph stats are used.
- Performance can be grouped by edge type.
- No live trading behavior is introduced.
```

---

# 13. Recommended implementation order

Use this exact order:

```text
M0  Repo discovery and plan doc
M1  Config + optional Neo4j Docker service
M2  Postgres graph schema
M3  TaurusData CSV importer
M4  Neo4j projection
M5  FastAPI graph APIs
M6  React graph dashboard
M7  Statistical validation engine
M8  GraphAnalystAgent
M9  Graph-aware risk committee
M10 Observability
M11 Backtesting graph signals
```

Do not start with the agent. The agent needs the graph schema, imported data, and stats first.

---

# 14. First vertical slice

The first usable vertical slice should be:

```text
TaurusData CSVs
   ↓
Postgres graph tables
   ↓
Neo4j projection
   ↓
FastAPI /api/graph/company/{symbol}
   ↓
React company graph page
```

This gives you immediate value before any trading logic.

The second vertical slice should be:

```text
edge_candidates.csv
   ↓
edge stats calculation
   ↓
candidate edge review UI
   ↓
promote/reject edge
```

The third vertical slice should be:

```text
active graph edges
   ↓
GraphAnalystAgent
   ↓
bull/bear debate
   ↓
risk committee
   ↓
paper trade proposal
```

---

# 15. Codex prompt bundle

You can paste this as the master implementation ticket into Codex first:

```text
Implement Taurus Graph Intelligence in phased milestones.

Architecture:
- Postgres is canonical source of truth.
- Neo4j is a derived read model/projection.
- React dashboard visualizes graph relationships.
- GraphAnalystAgent produces deterministic graph-aware analyst output.
- Graph signals feed existing bull/bear debate and risk committee.
- PaperBroker remains the only execution path.
- Live trading must remain disabled.

Data sources:
- TaurusData V2 CSVs:
  - company_industry_classifications.csv
  - company_segments.csv
  - company_products.csv
  - company_dependencies.csv
  - company_edges.csv
  - edge_candidates.csv
  - company_risks.csv
  - source_evidence.csv

Core implementation:
1. Add graph config and optional Neo4j Docker service.
2. Add Postgres graph schema.
3. Add idempotent TaurusData CSV importer.
4. Add Neo4j projection from Postgres.
5. Add FastAPI graph endpoints.
6. Add React graph dashboard.
7. Add graph statistical validation.
8. Add GraphAnalystAgent.
9. Add graph-aware risk committee checks.
10. Add graph observability.
11. Add graph-aware backtesting.

Hard constraints:
- Use uv only for Python dependencies.
- Follow existing SQLAlchemy, FastAPI, Pydantic, React, pytest, and Vitest conventions.
- Inspect repo structure before editing.
- Do not introduce live broker execution.
- Do not let graph signals bypass risk approval.
- Keep LLM usage optional, schema-bound, and mock-provider-compatible.
- Add tests and docs for each milestone.

Start only with Milestone 0:
- Inspect the repo.
- Create docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md.
- Do not implement source changes yet.
```

Then run each milestone separately.

---

# 16. What the final system should achieve

When complete, TaurusAgent should be able to say:

```text
ABC is a bullish paper-trade candidate because:
1. Two active graph peers moved positively on residual basis.
2. ABC historically follows this peer basket with a 1-3 day lag.
3. The relationship is supported by same-basic-industry and product-group edges.
4. The edge has stable 120-day residual correlation.
5. Technical trend is not contradictory.
6. Portfolio graph concentration remains within risk limits.
```

And it should also be able to say:

```text
Reject or reduce this trade because:
1. The portfolio already has too much exposure to the same customer industry.
2. The proposed stock shares the same raw-material dependency as existing holdings.
3. The graph signal is based on inferred candidate edges, not active validated edges.
```

That is the target: **relationship-aware prediction plus relationship-aware risk control**, still fully inside your paper-trading-first Taurus architecture.

[1]: https://developers.openai.com/codex/cli?utm_source=chatgpt.com "CLI – Codex | OpenAI Developers"
[2]: https://neo4j.com/docs/operations-manual/current/docker/introduction/?utm_source=chatgpt.com "Getting started with Neo4j in Docker - Operations Manual"
[3]: https://neo4j.com/docs/python-manual/current/?utm_source=chatgpt.com "Build applications with Neo4j and Python - Neo4j Python Driver Manual"


