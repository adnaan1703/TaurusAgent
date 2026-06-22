# Taurus Graph Explorer Handoff

Last updated: 2026-06-22

## Current Status

- Current milestone: None.
- Last completed milestone: M73 Regression, Documentation, and Visual QA.
- Planning completed: M70-M73 graph explorer sequence.
- Implementation state: M70 added the additive `/graph/neighborhood`
  API/client contract, counted arbitrary-node repository support,
  active/candidate defaults, rejected-edge opt-in, and truncation metadata.
  M71 replaced the static company SVG with a full main-content Reagraph
  explorer shell at `/graph/company/:symbol`, using the neighborhood client
  helper, active plus candidate defaults, rejected opt-in, client-side edge-type
  filtering, camera controls, refresh, node selection, and edge evidence/stats
  inspection. M72 added explicit selected-node one-hop expansion through the
  node inspector, duplicate-free local graph-state merging, per-node
  loading/error/truncation state, and reset behavior for refreshed initial
  neighborhoods. M73 ran focused graph API/repository tests, React graph tests,
  React production build, full backend regression, and browser QA against the
  local API/UI. During visual QA, M73 fixed a Reagraph focus regression where
  high-degree expansion could ask the canvas to fit a node that was not
  currently rendered.
- Next recommended milestone: None for the M70-M73 graph explorer sequence.

## M73 Verification

- `uv run pytest tests/unit/test_graph_api.py tests/unit/test_graph_repository.py -q`
  -> 8 passed.
- `pnpm --dir apps/web exec vitest run src/features/GraphPages.test.tsx`
  -> 5 passed.
- `pnpm --dir apps/web build` -> passed with the existing Vite large-chunk
  warning.
- `make test` -> 397 passed, 1 skipped.
- Browser QA verified `/graph/company/INFY` on desktop and mobile, nonblank
  Reagraph canvas rendering, fit/zoom/reset toolbar controls, live canvas node
  and edge selection, edge evidence/stats inspection, explicit node expansion,
  rejected-edge opt-in, and no post-fix Reagraph console errors during
  expansion.

## Required Reading

- `docs/TAURUS_GRAPH_EXPLORER_PLAN.md`
- `docs/MILESTONE.md`
- `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md`
- `docs/TAURUS_GRAPH_ANALYST_AGENT_DEEP_DIVE.md`
- `apps/api/routes_graph.py`
- `packages/taurus_core/db/repositories.py`
- `apps/web/src/features/GraphPages.tsx`
- `apps/web/src/features/GraphExplorer.tsx`
- `apps/web/src/api/client.ts`
- `apps/web/src/api/types.ts`
- `apps/web/src/features/GraphPages.test.tsx`
- `tests/unit/test_graph_api.py`
- `tests/unit/test_graph_repository.py`

## Boundaries

- Implement one milestone only, then stop after verification and documentation.
- Preserve paper-only execution and Kite data-only runtime behavior.
- Do not change graph scoring, graph analyst behavior, graph risk, promotion
  rules, Neo4j projection, or paper trading decisions.
- Rejected edges stay hidden by default in the explorer and must be opt-in.
- Node expansion is one-hop and explicit; clicking a node inspects it, while
  the inspector action expands it.
- Per-expansion limit is 1000 edges with truncation metadata.
- Use Reagraph unless implementation discovers a hard compatibility blocker.

## Update Rules

- When starting a milestone, mark it `In Progress` in `docs/MILESTONE.md`.
- When completing a milestone, update the tracker row, add a completion summary
  with assumptions made, mocks created, and mocks used, and inspect
  `/Users/adnaan/.codex/rules/default.rules` for Taurus approval cleanup.
- If implementation changes public graph payloads or dashboard-visible behavior,
  update API types, React client/UI, tests, and relevant docs in the same
  milestone.
- If M70-M73 scope changes materially, update
  `docs/TAURUS_GRAPH_EXPLORER_PLAN.md`, this handoff, and the tracker together.
