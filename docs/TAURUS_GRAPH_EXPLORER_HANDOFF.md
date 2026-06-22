# Taurus Graph Explorer Handoff

Last updated: 2026-06-22

## Current Status

- Current milestone: M70 Graph Neighborhood API Contract.
- Last completed milestone: M69 Regression, Documentation, and Cleanup.
- Planning completed: M70-M73 graph explorer sequence.
- Implementation state: Planning only. No API, React, dependency, test, or
  runtime implementation has started for this sequence.
- Next recommended milestone: M70.

## Required Reading

- `docs/TAURUS_GRAPH_EXPLORER_PLAN.md`
- `docs/MILESTONE.md`
- `docs/TAURUS_GRAPH_PROVENANCE_PLAN.md`
- `docs/TAURUS_GRAPH_ANALYST_AGENT_DEEP_DIVE.md`
- `apps/api/routes_graph.py`
- `packages/taurus_core/db/repositories.py`
- `apps/web/src/features/GraphPages.tsx`
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
