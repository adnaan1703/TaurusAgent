# Taurus Graph Explorer Plan

Last updated: 2026-06-22

This document is the implementation plan for replacing the current static
company relationship map with a full-page, Reagraph-powered stock graph
explorer. Each milestone below is a standalone milestone intended to be
executed in a separate Codex thread. Stop after completing and documenting the
current milestone; do not automatically continue to the next milestone.

Status: Planning is complete. Implementation is complete through M72. M73
remains planned.

## Target Behavior

The React dashboard graph view should become a usable stock-centered explorer:

- `/graph/company/:symbol` opens a full main-content graph workspace inside
  the Taurus shell, not a small static SVG inside a card.
- The initial view centers on `company:{SYMBOL}` and shows active plus
  candidate relationships by default. Rejected relationships are opt-in.
- Operators can pan, zoom, fit/reset the view, select nodes and edges, inspect
  edge evidence/stats, and explicitly expand any selected node to load its
  immediate neighborhood.
- Node expansion is one-hop and deliberate. Each expansion can load up to 1000
  connected edges and must clearly show when the returned neighborhood is
  truncated.
- The explorer is for local graph inspection and review support only. It must
  not change graph scoring, promotion rules, paper trading behavior, graph
  analyst behavior, graph risk, or Neo4j projection semantics.

## Existing Foundation

- `docs/MILESTONE.md` is the canonical tracker. It requires flat milestone IDs,
  one milestone at a time, completion summaries, and approval-rule cleanup at
  milestone closeout.
- `apps/api/routes_graph.py` already exposes graph overview, company subgraph,
  candidate edge, edge detail/evidence, review, graph signal, and bullish
  candidate endpoints.
- `GraphRepository.list_edges_for_node()` already supports fetching edges for
  any graph node key. The public API currently exposes this primarily through
  `/graph/company/{symbol}`.
- `apps/web/src/features/GraphPages.tsx` owns the graph overview, company,
  review, signals, current static `GraphCanvas`, edge tables, and edge detail
  drawer.
- The current company graph UI renders a fixed SVG ellipse inside `DataPanel`,
  slices visible nodes to 28, and has no real pan, zoom, layout, node
  expansion, or workspace-scale inspector.
- `apps/web/src/api/client.ts` and `apps/web/src/api/types.ts` already hold the
  graph API client/types.
- `tests/unit/test_graph_api.py`, `tests/unit/test_graph_repository.py`, and
  `apps/web/src/features/GraphPages.test.tsx` are the key regression surfaces.
- `apps/web` uses React 19, Vite, Tailwind, React Query, React Router, lucide
  icons, and pnpm. Reagraph 4.x is compatible with React through broad
  `react`/`react-dom` peer ranges and provides WebGL network rendering,
  layouts, node/edge events, selection, collapse, and camera controls.

## Global Rules For M70-M73

- Implement only the requested milestone. After that milestone is complete,
  verified, cleaned up, and documented, stop and report the result.
- Preserve paper-only and Kite-data-only safety boundaries. Do not add live
  broker routing, money movement, hosted service dependencies, secrets, or
  production side effects.
- Keep graph scoring, graph analyst, graph risk, graph provenance, candidate
  promotion, and Neo4j behavior unchanged unless explicitly required to support
  the read-only explorer contract.
- Use `uv` for Python commands and `pnpm` for React dependency commands. Do not
  use global `pip install`.
- Add API/client/UI/test changes together when public graph payloads or
  dashboard-visible behavior changes.
- Keep new graph API behavior additive and backward compatible. Do not break
  existing `/graph/company/{symbol}`, candidate review, edge detail, or signal
  routes.
- Use Reagraph as the visualization renderer unless implementation discovers a
  hard compatibility blocker. If blocked, document the blocker and propose a
  replacement before switching libraries.
- Use icons for toolbar controls and tooltips/labels for unfamiliar controls.
  Do not add explanatory in-app marketing copy.
- At completion of every milestone, update `docs/MILESTONE.md` with status and
  an explicit completion summary listing assumptions made, mocks created, and
  mocks used. Use `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the repo's global approval cleanup rule from `docs/MILESTONE.md`.

## M70 - Graph Neighborhood API Contract

Purpose: add the additive API/client contract needed for arbitrary node
expansion without changing the existing company graph route behavior.

Instructions:

- Read these source areas before editing:
  - `packages/taurus_core/db/repositories.py`
  - `apps/api/routes_graph.py`
  - `apps/web/src/api/types.ts`
  - `apps/web/src/api/client.ts`
  - `tests/unit/test_graph_api.py`
  - `tests/unit/test_graph_repository.py`
- Add repository support for a node neighborhood query that can:
  - resolve any `node_key`
  - filter by one or more statuses
  - return up to a caller-provided limit, capped at 1000
  - provide a total matching edge count so the API can report truncation
- Add a new response model, tentatively `GraphNeighborhoodResponse`, with:
  - `center_node`
  - `nodes`
  - `edges`
  - `counts`
  - `limit`
  - `total_edges`
  - `truncated`
- Add a new read-only route, tentatively:
  `GET /graph/neighborhood?node_key=company%3AINFY&status=active&status=candidate&limit=1000`.
- Default the route to active plus candidate when no status is supplied.
  Rejected edges must be returned only when explicitly requested.
- Keep `/graph/company/{symbol}` compatible. It may reuse the new response
  builder internally, but its existing payload shape and query behavior must
  remain valid for current clients.
- Add TypeScript types and a `taurusApi.graphNeighborhood(...)` client helper.
  Do not replace the UI in this milestone.
- Do not add Reagraph, new React graph state, or graph UI expansion behavior in
  this milestone.

Expected code shape:

- Shared API response construction should avoid duplicating node lookup and
  edge response mapping logic.
- Multi-status filtering should be explicit and test-covered; do not overload
  the existing single-status `GraphEdgeStatusFilter` in a way that breaks old
  requests.
- The API should return 404 for unknown node keys with a clear message.

Acceptance criteria:

- Existing graph API tests still pass.
- The new neighborhood endpoint can return active plus candidate edges for
  `company:INFY` and can opt into rejected edges.
- Unknown node keys return 404.
- Truncation metadata is deterministic when the edge count exceeds the limit.
- React client/types compile without any UI using the new helper yet.
- `docs/MILESTONE.md` marks M70 done and M71 planned.

Verification:

```bash
uv run pytest tests/unit/test_graph_api.py tests/unit/test_graph_repository.py -q
pnpm --dir apps/web build
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M71 - Reagraph Explorer Shell

Purpose: replace the cramped static SVG company map with a full main-content
Reagraph workspace for the initial stock graph.

Instructions:

- Read these source areas before editing:
  - `apps/web/package.json`
  - `apps/web/src/features/GraphPages.tsx`
  - `apps/web/src/api/client.ts`
  - `apps/web/src/api/types.ts`
  - `apps/web/src/components/AppShell.tsx`
  - `apps/web/src/features/PageScaffold.tsx`
  - `apps/web/src/features/GraphPages.test.tsx`
- Add Reagraph with pnpm and commit the generated lockfile changes when the
  milestone itself is committed later.
- Replace the current static SVG `GraphCanvas` with a Reagraph-backed explorer
  component for `/graph/company/:symbol`.
- Keep the Taurus sidebar/header. The graph route should fill the available
  main content area below the header, with stable viewport-height sizing.
- Remove the graph visualization from `DataPanel`; use a workspace layout:
  compact toolbar, graph canvas, and a side inspector.
- Toolbar controls should include:
  - symbol search
  - status chips defaulted to active plus candidate
  - rejected opt-in
  - edge-type filter if it can be applied client-side from loaded edges
  - fit view
  - zoom in
  - zoom out
  - reset view
  - refresh
- Map graph data to Reagraph shapes:
  - node `id` is `node_key`
  - node label is `symbol` or `display_name`
  - edge `id` is `edge_key`
  - edge source/target are source/target node keys
  - edge label is humanized `edge_type`
  - status/provenance/strength/confidence remain in `data`
- Style active, candidate, and rejected edges distinctly; rejected remains
  hidden by default.
- Single-click node selection opens the node inspector. Single-click edge
  selection opens the edge inspector and may reuse the existing edge detail
  query/drawer content.
- Do not implement incremental expansion yet. The explorer may render only the
  initial company neighborhood from M70.
- Do not change graph review mutations, signal pages, overview metrics, or
  paper-run behavior.

Expected code shape:

- Prefer extracting a focused graph explorer component rather than further
  growing the existing monolithic `GraphPages.tsx` if the file becomes hard to
  reason about.
- Use Reagraph camera refs for fit/zoom/reset controls.
- Mock Reagraph in Vitest/JSDOM rather than requiring WebGL in unit tests.

Acceptance criteria:

- `/graph/company/:symbol` renders a full main-content interactive graph
  workspace.
- The initial graph can be selected, inspected, fit, zoomed, refreshed, and
  status-filtered.
- Existing graph overview, review, and signals pages still render.
- `docs/MILESTONE.md` marks M71 done and M72 planned.

Verification:

```bash
pnpm --dir apps/web exec vitest run src/features/GraphPages.test.tsx
pnpm --dir apps/web build
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M72 - Incremental Node Expansion

Purpose: let operators explicitly expand any selected node and merge its
one-hop neighborhood into the visible graph.

Instructions:

- Read these source areas before editing:
  - `apps/web/src/features/GraphPages.tsx`
  - any extracted graph explorer component from M71
  - `apps/web/src/api/client.ts`
  - `apps/web/src/api/types.ts`
  - `apps/web/src/features/GraphPages.test.tsx`
- Add graph exploration state that tracks:
  - loaded nodes by `node_key`
  - loaded edges by `edge_key`
  - selected node or edge
  - expanded node keys
  - loading/error state per expanded node
  - truncation metadata per expanded node
- Add an explicit "expand neighborhood" action in the selected-node inspector.
  Node clicks inspect only; they must not automatically expand.
- On expansion, call the M70 neighborhood endpoint for the selected node with
  the current status filters and `limit=1000`.
- Merge returned nodes and edges by id without duplicating existing graph
  elements.
- After expansion, fit or center around the newly expanded node and its returned
  neighbors without disorienting the user.
- Display truncation state when `truncated=true`, including the returned count
  and total count.
- Add reset controls to return to the initial stock-centered neighborhood.
- Ensure filter changes are predictable:
  - changing status filters refreshes the initial stock neighborhood and clears
    expansion state unless implementation can safely re-query all expanded
    nodes
  - rejected edges remain opt-in
- Do not add graph mutation/promotion actions to the explorer unless they
  already exist in the review route and can be reused without scope creep.

Expected code shape:

- Keep API fetching through React Query or a small local expansion helper that
  follows existing app patterns.
- Keep the graph explorer resilient to partial expansion failures: one failed
  node expansion should not erase already loaded graph data.
- Use accessible labels for icon-only controls.

Acceptance criteria:

- The user can select a company, sector, industry, risk, product, or other graph
  node and explicitly expand its immediate neighborhood.
- Expanded neighborhoods merge into the graph and can be inspected.
- Duplicate nodes/edges do not appear after repeated expansions.
- Truncated high-degree expansions are visible to the operator.
- `docs/MILESTONE.md` marks M72 done and M73 planned.

Verification:

```bash
pnpm --dir apps/web exec vitest run src/features/GraphPages.test.tsx
pnpm --dir apps/web build
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M73 - Regression, Documentation, and Visual QA

Purpose: close the graph explorer sequence with full regression, operator docs,
and browser verification.

Instructions:

- Run focused API and React graph tests from M70-M72.
- Run broader React build verification.
- Run `make test` if runtime budget permits; otherwise document why the full
  unit suite was not run.
- Start the local API/UI only if needed for visual QA. Use the existing project
  commands and do not introduce new services.
- Verify in browser automation or manual browser QA that:
  - `/graph/company/INFY` fills the main dashboard content area
  - graph canvas is nonblank
  - pan/zoom/fit/reset work
  - node selection opens the node inspector
  - edge selection opens evidence/stats detail
  - node expansion loads and merges connected nodes/edges
  - rejected edges remain opt-in
  - mobile and desktop layouts avoid overlapping controls and unreadable text
- Update operator/developer docs that are stale after implementation:
  - `docs/TAURUS_USAGE_GUIDE.md` for graph explorer usage
  - `docs/TAURUS_COMMANDS.md` only if commands changed
  - `docs/TAURUS_AGENT_ARCHITECTURE.md` only if graph API/client architecture
    descriptions become inaccurate
- Update `docs/MILESTONE.md` to close M73 and the M70-M73 sequence.
- Inspect `/Users/adnaan/.codex/rules/default.rules` and perform the
  project-local approval cleanup if needed.
- Do not add new graph features during closeout unless required to fix a
  regression in the planned behavior.

Expected code shape:

- Closeout should focus on polish, docs, verification, and small bug fixes
  discovered by QA.
- No new API contracts should be introduced in M73 unless required by a
  discovered defect.

Acceptance criteria:

- M70-M73 behavior is implemented, documented, and verified.
- The graph explorer is usable for stock-centered relationship exploration.
- The tracker and handoff no longer imply implementation is pending unless
  deferred items remain.

Verification:

```bash
uv run pytest tests/unit/test_graph_api.py tests/unit/test_graph_repository.py -q
pnpm --dir apps/web exec vitest run src/features/GraphPages.test.tsx
pnpm --dir apps/web build
make test
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## Deferred Work

- Global all-market graph browsing across many stocks at once.
- Graph edit workflows outside the existing candidate review promote/reject
  route.
- Graph scoring, graph analyst, graph risk, or graph-aware strategy changes.
- Neo4j-backed live graph exploration.
- Persisted user graph layouts, saved workspaces, or collaboration features.
- Reagraph-to-image export unless operators later need graph snapshots.
