# Taurus React Dashboard Plan

Status: Planned

Owner: Taurus local development workflow

Last updated: 2026-05-21 16:48 IST

## Purpose

Build a read-only React web app that makes Taurus paper-run behavior easy to inspect.
The current Streamlit dashboard is useful for logs and tables, but it does not make the
run loop intuitive. The React dashboard should show a complete stitched trail:

```text
Paper Run -> Symbol -> Decision Trail -> Paper Execution
```

The first version is an observability UI, not a trading terminal. It must not start
paper loops, place orders, enable live trading, or mutate Taurus state.

## Start Here For Fresh Context

If implementation starts in a fresh Codex context, use this document as the primary
source of truth for M16. Do not rely on prior chat history.

Read these files in order:

1. `AGENTS.md`
2. `docs/TAURUS_MILESTONE_TODO.md`
3. `docs/TAURUS_REACT_DASHBOARD_PLAN.md`
4. `docs/TAURUS_UI_DESIGN_BRIEF.md`
5. `docs/stitch/paper-trade-event-monitor/STITCH_MANIFEST.md`
6. `docs/TAURUS_COMMANDS.md`

Before making changes:

1. Run `git status --short`.
2. Inspect the current relevant files for the milestone being implemented.
3. Preserve unrelated user changes.
4. Keep work scoped to the active M16 submilestone.
5. Update `docs/TAURUS_MILESTONE_TODO.md` when a submilestone starts or completes.

Default implementation choices are already decided:

| Decision | Chosen default |
|---|---|
| UI scope | Core run-loop observability screens |
| Mutability | Read-only v1 |
| Frontend stack | Vite + React + TypeScript |
| Package manager | `pnpm` |
| App location | `apps/web` |
| Styling | Tailwind with Stitch/Taurus tokens |
| Server state | TanStack Query |
| Charts | Recharts |
| Local serving | Vite on port `5173`, FastAPI on port `8000` |
| Data strategy | Backend aggregate `/ui/*` APIs |
| Refresh | Polling plus manual refresh |
| Demo data | No frontend fixture mode; show empty states and Taurus commands |
| Streamlit | Keep as fallback |

## Success Criteria

- A user can open the latest paper run, select a symbol, and understand what happened
  across inputs, analysts, debate, trader proposal, risk review, final decision, and
  paper execution.
- Run-level status and per-symbol status are visually distinct.
- Missing or skipped artifacts are explicit, not hidden.
- Risk gates and blocked/rejected decisions are prominent.
- Raw JSON remains available for debugging but is secondary to the visual trail.
- The app uses real FastAPI data only; empty data states explain which Taurus commands
  to run.
- Streamlit remains available as a fallback diagnostic dashboard.

## Non-Goals For V1

- No live-trading features.
- No run-start, run-stop, or loop-control buttons.
- No broker integration beyond existing `PaperBroker` observation.
- No frontend-only demo fixture mode.
- No replacement or deletion of Streamlit.
- No authentication or multi-user access model.

## Current Context

Existing useful backend surfaces:

- `GET /runs`
- `GET /runs/{run_id}`
- `GET /agent-reports?symbol=INFY`
- `GET /debates?symbol=INFY`
- `GET /trader-proposals?symbol=INFY`
- `GET /risk-checks?symbol=INFY`
- `GET /final-decisions?symbol=INFY`
- `GET /paper/orders?symbol=INFY`
- `GET /paper/fills?symbol=INFY`
- `GET /paper/positions?symbol=INFY`
- `GET /paper/account`
- `GET /replay/{decision_id}`

Important gap: many list endpoints only filter by `symbol`, not by `run_id`. A run-loop
UI should not stitch artifacts from different runs on the client. The backend should
provide aggregate, run-scoped `/ui/*` endpoints.

Existing design references:

- `docs/TAURUS_UI_DESIGN_BRIEF.md` defines the product and information architecture.
- `docs/stitch/paper-trade-event-monitor/STITCH_MANIFEST.md` preserves the Stitch project metadata and hosted download URLs for M16.1.
- Stitch project `16481042039965443151` defines the visual direction.
- Dark design system: `Deep Space Observability`, asset `5358cfbb776e4117a8e412e6740f0d0f`.

## Repository Map

The implementation should expect the following repo shape:

| Path | Purpose |
|---|---|
| `apps/api/main.py` | FastAPI app factory and router registration |
| `apps/api/routes_runs.py` | Existing paper run API |
| `apps/api/routes_replay.py` | Existing decision replay API |
| `apps/api/routes_paper.py` | Existing paper account/order/fill/position API |
| `apps/api/routes_risk.py` | Existing risk review and final decision API |
| `apps/api/routes_research.py` | Existing debate and trader proposal API |
| `apps/api/routes_intelligence.py` | Existing event and analyst report API |
| `apps/dashboard/` | Existing Streamlit dashboard; keep as fallback |
| `packages/taurus_core/db/models.py` | SQLAlchemy models and table names |
| `packages/taurus_core/db/repositories.py` | Existing repository methods; extend for run-scoped UI queries |
| `packages/taurus_core/paper_trading/service.py` | Paper run loop and artifact creation |
| `packages/taurus_core/paper_trading/schemas.py` | `PaperRun` schema |
| `packages/taurus_core/replay/service.py` | Stored decision replay reconstruction |
| `packages/taurus_core/replay/schemas.py` | Replay response schema |
| `packages/taurus_core/risk/schemas.py` | Risk and final decision schemas |
| `packages/taurus_core/execution/schemas.py` | Paper account/order/fill/position schemas |
| `tests/unit/` | Pytest suite |
| `docs/TAURUS_UI_DESIGN_BRIEF.md` | Product and IA context |
| `docs/stitch/paper-trade-event-monitor/STITCH_MANIFEST.md` | Stitch asset metadata and URLs |
| `Makefile` | Project command entrypoint |

Add new React files under `apps/web`; do not put React code under `apps/dashboard`.

## Domain Model For The UI

The UI is centered on one traceable object:

```text
run_id + symbol
```

Use `decision_id` as the replay anchor when available.

Artifact linkage:

```text
paper_runs.run_id
  -> analyst_reports.run_id + symbol
  -> debate_reports.run_id + symbol
  -> trader_proposals.run_id + symbol + debate_id
  -> risk_reviews.run_id + symbol + proposal_id + decision_id
  -> final_decisions.run_id + symbol + risk_check_id + decision_id
  -> paper_orders.final_decision_id + decision_id
  -> paper_fills.order_id
  -> paper_positions.run_id + symbol
  -> paper_accounts.run_id
  -> audit_log.payload.run_id / payload.symbol / payload.decision_id
```

Important behavior:

- A run can be `PARTIAL_FAILED`; successful and failed symbols must both be visible.
- A symbol can stop before paper execution; missing order/fill stages are valid and must be labeled.
- Risk and final decision artifacts are not orders.
- Only `APPROVED_FOR_PAPER` final decisions can route to `PaperBroker`.
- The UI must show `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` as persistent safety context.

## Product Shape

The dashboard is organized around these routes:

| Route | Purpose |
|---|---|
| `/` | Run overview, latest account state, recent runs, warnings, latest decisions |
| `/runs/:runId` | Run-level detail, symbol pipeline progress, market and strategy summary |
| `/runs/:runId/symbols/:symbol` | Main stitched decision trail for one symbol in one run |
| `/replay/:decisionId` | Decision replay stage accordion from stored artifacts |
| `/risk` | Risk engine summary, hard rules, persona reviews, final decisions |
| `/portfolio` | Paper account, positions, orders, fills, account metrics |
| `/history` | Searchable run history |

Primary interaction:

```text
Overview -> Run Detail -> Symbol Decision Trail -> Replay / Raw Artifact
```

## Architecture

### Frontend

- Location: `apps/web`
- Stack: Vite, React, TypeScript
- Package manager: `pnpm`
- Styling: Tailwind with Taurus/Stitch design tokens
- Routing: React Router
- Server state: TanStack Query
- Charts: Recharts
- Tests: Vitest and React Testing Library

### Backend

- Keep existing API routes intact.
- Add new UI aggregate routes under `/ui`.
- Add run-scoped repository query methods where existing repositories only filter by symbol.
- Add CORS for local Vite dev origins:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`

### Development Commands

Add Makefile targets:

```bash
make setup-ui
make ui
make build-ui
make test-ui
```

Expected behavior:

- `make setup-ui`: install frontend dependencies with `pnpm install`.
- `make ui`: run Vite dev server on port `5173`.
- `make build-ui`: type-check and build production assets.
- `make test-ui`: run frontend unit tests.

## API Plan

### `GET /ui/overview?limit=50`

Purpose: power the landing page without many client-side joins.

Response should include:

- safety status: `live_trading_enabled`, `broker_provider`, `taurus_mode`
- latest paper account summary
- latest run summary
- latest final decision
- latest paper order
- recent runs
- current positions
- warnings derived from failed runs, stale data, rejected/blocked decisions, and missing account state

### `GET /ui/runs/{run_id}`

Purpose: show what happened inside one run.

Response should include:

- run header: `run_id`, status, schedule, timezone, started/completed timestamps, duration
- symbol rows for every requested symbol
- per-symbol pipeline status for:
  - inputs
  - analyst reports
  - debate
  - trader proposal
  - risk review
  - final decision
  - paper order
  - paper fills
- market data summary
- strategy summary
- run errors
- artifact IDs from `paper_runs.artifacts.symbols`

### `GET /ui/runs/{run_id}/symbols/{symbol}/decision-trail`

Purpose: drive the main stitched timeline view.

Response should include:

- run context
- symbol context
- final outcome summary
- timeline stages in display order:
  - `inputs`
  - `analyst_reports`
  - `debate_report`
  - `trader_proposal`
  - `risk_review`
  - `final_decision`
  - `paper_order`
  - `paper_fills`
  - `audit_log`
- each stage should include:
  - `id`
  - `label`
  - `status`
  - `timestamp`
  - `summary`
  - `metrics`
  - `artifact_ids`
  - `artifacts`
  - `raw`
- missing stage representation:
  - `status=missing`
  - empty artifact list
  - plain-language reason when available

### `GET /ui/replay/{decision_id}`

Purpose: present stored replay data in a UI-friendly shape.

Implementation:

- Use existing `DecisionReplayService`.
- Normalize stage names and status labels for frontend display.
- Preserve raw artifacts for the debug drawer.

### `GET /ui/risk`

Purpose: power the Risk Engine screen.

Response should include:

- latest risk reviews
- hard-rule results flattened by risk check
- persona review summaries
- latest final decisions
- status counts

### `GET /ui/portfolio`

Purpose: power account and execution views.

Response should include:

- latest account
- positions
- orders
- fills
- latest run-linked account if a run is selected later
- summary metrics: cash, exposure, equity, realized P&L, unrealized P&L

### `GET /ui/history?limit=100`

Purpose: optimized run history screen.

Response should include:

- run rows
- status counts
- filters metadata: statuses, symbols, date range where possible

## Minimum API Response Contracts

These contracts are intentionally presentation-oriented. Backend implementation may use
Pydantic schemas with snake_case fields; the frontend may map them to camelCase at the
API-client boundary. Do not expose database models directly as UI contracts.

### Shared DTOs

```python
class UiSafetyStatus(BaseModel):
    taurus_mode: str
    broker_provider: str
    live_trading_enabled: bool
    alert_provider: str | None = None


class UiWarning(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    title: str
    message: str
    run_id: str | None = None
    symbol: str | None = None
    created_at: datetime | None = None


class UiMetric(BaseModel):
    label: str
    value: str | int | float | bool | None
    unit: str | None = None
    tone: Literal["neutral", "success", "caution", "failure"] = "neutral"


class UiArtifactRef(BaseModel):
    kind: str
    id: str
    label: str | None = None
```

### Run And Symbol DTOs

```python
class UiRunSummary(BaseModel):
    run_id: str
    status: Literal["RUNNING", "COMPLETED", "PARTIAL_FAILED", "FAILED"]
    schedule_name: str
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    symbols: list[str]
    succeeded_symbols: list[str]
    failed_symbols: list[str]
    error_count: int
    market_provider: str | None
    final_status_counts: dict[str, int] = {}
    order_status_counts: dict[str, int] = {}


class UiStageSummary(BaseModel):
    id: str
    label: str
    status: Literal["complete", "running", "blocked", "rejected", "failed", "missing", "skipped"]
    summary: str
    timestamp: datetime | None = None
    artifact_ids: list[str] = []


class UiSymbolPipelineRow(BaseModel):
    symbol: str
    run_id: str
    pipeline_status: Literal["complete", "running", "blocked", "rejected", "failed", "missing", "skipped"]
    final_status: str | None
    final_action: str | None
    order_status: str | None
    decision_id: str | None
    stages: list[UiStageSummary]
    errors: list[str] = []
```

### Decision Trail DTO

```python
class UiTimelineStage(BaseModel):
    id: str
    label: str
    status: Literal["complete", "running", "blocked", "rejected", "failed", "missing", "skipped"]
    timestamp: datetime | None = None
    summary: str
    metrics: dict[str, str | int | float | bool | None] = {}
    artifact_ids: list[str] = []
    artifacts: list[dict[str, object]] = []
    raw: dict[str, object] | list[dict[str, object]] | None = None


class UiDecisionTrailResponse(BaseModel):
    run: UiRunSummary
    symbol: str
    company_name: str | None = None
    decision_id: str | None = None
    final_status: str | None
    final_action: str | None
    can_send_to_broker: bool | None
    selected_stage_id: str
    stages: list[UiTimelineStage]
    warnings: list[UiWarning] = []
```

Stage order is fixed:

```text
inputs
analyst_reports
debate_report
trader_proposal
risk_review
final_decision
paper_order
paper_fills
audit_log
```

### Overview DTO

```python
class UiOverviewResponse(BaseModel):
    safety: UiSafetyStatus
    latest_account: dict[str, object] | None
    latest_run: UiRunSummary | None
    latest_final_decision: dict[str, object] | None
    latest_order: dict[str, object] | None
    recent_runs: list[UiRunSummary]
    positions: list[dict[str, object]]
    warnings: list[UiWarning]
```

### Error Semantics

- Unknown `run_id`: return `404`.
- Unknown `symbol` inside an existing run: return `404`.
- Unknown `decision_id`: return `404`.
- Existing run with missing artifacts: return `200` with explicit `missing` or `skipped` stages.
- Empty database: return `200` with empty lists and no fake records.
- API should never return credentials or unredacted secrets.

## Frontend Data Model

Use TypeScript types that mirror the aggregate API shape, not raw SQL models.

Core types:

```ts
type RunStatus = "RUNNING" | "COMPLETED" | "PARTIAL_FAILED" | "FAILED";
type StageStatus = "complete" | "running" | "blocked" | "rejected" | "failed" | "missing" | "skipped";

type TimelineStage = {
  id: string;
  label: string;
  status: StageStatus;
  timestamp?: string;
  summary: string;
  metrics: Record<string, string | number | boolean | null>;
  artifactIds: string[];
  artifacts: unknown[];
  raw: unknown;
};
```

Status mapping must be centralized so colors and labels are consistent across screens.

Required mappings:

- Run status: `RUNNING`, `COMPLETED`, `PARTIAL_FAILED`, `FAILED`
- Risk status: `APPROVED`, `APPROVED_WITH_REDUCTION`, `REJECTED`, `BLOCKED`
- Final decision status: `APPROVED_FOR_PAPER`, `REJECTED`, `BLOCKED`
- Order status: `CREATED`, `ACCEPTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`
- Analyst stance: bullish, neutral, bearish variants

## Visual Direction

Use the Stitch dark observability direction:

- Background: deep navy/slate
- Cards: tonal dark surfaces with low-contrast outlines
- Primary accent: sky blue
- Secondary accent: indigo
- Success: green
- Caution: amber
- Failure: red
- Typography: Inter for UI, JetBrains Mono or monospace for IDs and raw data
- Layout: fixed side navigation on desktop, top navigation on mobile

Important UI components:

- App shell with safety status
- Status badges
- Metric cards
- Run table
- Symbol pipeline table/grid
- Stitched decision timeline
- Sticky stage detail panel
- Analyst report cards
- Debate summary card
- Risk hard-rule matrix
- Persona review cards
- Final decision panel
- Order/fill tables
- Raw JSON drawer or collapsible footer
- Empty state panels

## Polling And Refresh

Use TanStack Query polling:

- Overview and history: every 15 seconds
- Selected running run detail: every 5 seconds
- Selected completed run detail: no automatic polling or slow polling at 60 seconds
- Manual refresh button on every page

No WebSocket or SSE in v1.

## Empty States

When no data exists, the UI should show commands instead of fake data:

```bash
make migrate
make seed-mock
make import-mock-news
make paper-loop-mock
```

For API unavailable state, show:

```bash
make api
```

For frontend local development, show:

```bash
make ui
```

## Milestone Operating Procedure

Each M16 submilestone must be implemented as a separate milestone-grade unit of work.
Do not automatically continue from one M16 submilestone to the next. After a submilestone
meets its implementation checklist, acceptance criteria, verification commands, cleanup,
and completion-summary requirements, stop work and report the achieved results to the user.
Only start the next M16 submilestone after the user explicitly asks to proceed.

At submilestone start:

- Set the relevant M16 submilestone in `docs/TAURUS_MILESTONE_TODO.md` to in progress if it is tracked there.
- Run `git status --short`.
- Read the files listed in that submilestone's responsibility section.
- Confirm no unrelated user changes need to be touched.

During implementation:

- Keep changes scoped to the active submilestone.
- Prefer small, named modules over large mixed-purpose files.
- Preserve existing public API behavior unless the submilestone explicitly changes it.
- Do not add trading, broker, or live-control functionality.
- Do not commit real secrets, broker credentials, Telegram tokens, or user data exports.
- Keep downloaded Stitch assets under `docs/stitch/paper-trade-event-monitor/` only.

At submilestone completion:

- Run the verification commands listed for that submilestone.
- Confirm every acceptance checkbox for that submilestone is satisfied, or document the exact blocker.
- Complete any submilestone-specific cleanup, including stopping local dev servers/processes started for verification.
- Inspect `/Users/adnaan/.codex/rules/default.rules`.
- Treat entries after the user's `# END MY CUSTOM ADDITION` marker as accidental global approvals.
- Copy Taurus-specific approved prefixes into `.codex/rules/default.rules` if missing.
- Document Taurus-specific commands in `docs/TAURUS_COMMANDS.md`.
- Remove Taurus-specific accidental approvals from the global rules file.
- Do not copy unrelated global approvals.
- Update checkboxes in this plan if the work is complete.
- Update `docs/TAURUS_MILESTONE_TODO.md`.
- Add a completion summary with:
  - Assumptions made
  - Mocks created
  - Mocks used
- If a category is empty, write `None`.
- Stop after reporting the submilestone completion. Do not mark the next M16 submilestone
  in progress and do not begin implementation for it unless the user gives a new proceed request.

At full M16 completion:

- Inspect `/Users/adnaan/.codex/rules/default.rules`.
- Treat entries after the user's `# END MY CUSTOM ADDITION` marker as accidental global approvals.
- Copy Taurus-specific approved prefixes into `.codex/rules/default.rules` if missing.
- Document Taurus-specific commands in `docs/TAURUS_COMMANDS.md`.
- Remove Taurus-specific accidental approvals from the global rules file.
- Do not copy unrelated global approvals.

## Milestones

## M16.1 - Reference And Planning Assets

Objective: collect the Stitch reference artifacts and freeze the implementation direction before any production React code is written.

Responsibility:

- Own the design reference package for the React dashboard.
- Convert the Stitch concept into implementation guidance, not production markup.
- Confirm the route map, screen priority, and design tokens that later milestones must follow.

Out of scope:

- No React app scaffolding.
- No backend API changes.
- No conversion of Stitch HTML directly into production components.

Implementation instructions:

- [x] Validate that `docs/stitch/paper-trade-event-monitor/STITCH_MANIFEST.md` is present and contains the requested screen URLs.
- [x] Create `docs/stitch/paper-trade-event-monitor/assets/`.
- [x] Download screenshots for each requested Stitch screen using the Stitch `screenshot.downloadUrl` values and `curl -L`.
- [x] Download generated HTML for each requested Stitch screen using the Stitch `htmlCode.downloadUrl` values and `curl -L`.
- [x] Store each file with a stable, readable name such as `01-run-overview-dark-v2.png` and `01-run-overview-dark-v2.html`.
- [x] Update `docs/stitch/paper-trade-event-monitor/README.md` with the files downloaded during M16.1.
- [x] In the Stitch README, document the project ID, asset ID, screen IDs, downloaded filenames, and when they were fetched.
- [x] In the Stitch README, state that these assets are references only and must not be treated as source code.
- [x] Extract the important visual tokens from the dark design system: background, card surfaces, outline, primary accent, success, caution, failure, typography, and spacing.
- [x] Add a short mapping from Stitch screens to Taurus routes:
  - Run Overview -> `/`
  - Run Detail -> `/runs/:runId`
  - Decision Trail -> `/runs/:runId/symbols/:symbol`
  - Decision Replay -> `/replay/:decisionId`
  - Risk Engine -> `/risk`
  - Portfolio & Account -> `/portfolio`
  - Run History -> `/history`
- [x] Confirm that v1 remains read-only and does not include run-control actions, even if Stitch mocks show a "Run Agent" button.
- [x] Update this plan if the reference extraction reveals screen behavior that needs to change.

Deliverables:

- `docs/stitch/paper-trade-event-monitor/STITCH_MANIFEST.md`
- `docs/stitch/paper-trade-event-monitor/README.md`
- Downloaded Stitch screenshots.
- Downloaded Stitch generated HTML.
- Confirmed route-to-screen mapping in this plan or the Stitch README.

Acceptance:

- [x] Reference screenshots and HTML are stored under `docs/stitch/paper-trade-event-monitor/`.
- [x] Every requested screen has either a downloaded screenshot or an explicit note explaining why it could not be downloaded.
- [x] The Stitch reference README lists project ID, asset ID, screen IDs, and local filenames.
- [x] The React implementation is explicitly based on clean components, not direct static HTML porting.
- [x] The route map is documented in this plan.
- [x] V1 read-only scope is restated and any Stitch control buttons are marked non-functional or deferred.

Verification:

```bash
git status --short
find docs/stitch/paper-trade-event-monitor -maxdepth 1 -type f | sort
```

Notes:

- Downloaded 7 screenshots and 7 generated HTML reference files under `docs/stitch/paper-trade-event-monitor/assets/`.
- The Stitch reference README now lists the project ID, design-system asset ID, screen IDs, local filenames, dark visual tokens, route mapping, and read-only scope rule.
- No route or screen behavior changes were needed after reference extraction.

Completion summary:

- Assumptions made: The downloaded Stitch screenshots and HTML are reference material only; M16 production React must be implemented as clean components using the aggregate API contracts. V1 remains read-only even if a visual reference suggests run-control UI.
- Mocks created: None
- Mocks used: None

## M16.2 - Backend Aggregate APIs

Objective: expose server-composed, run-scoped UI data so React does not perform brittle joins.

Responsibility:

- Own the API contract consumed by `apps/web`.
- Join Taurus run-loop artifacts on the server by `run_id`, `symbol`, and `decision_id`.
- Preserve existing raw API behavior for scripts, Streamlit, tests, and external callers.

Out of scope:

- No frontend implementation.
- No mutation endpoints.
- No run execution controls.
- No database schema changes unless a missing index or field is proven necessary.

Implementation instructions:

- [x] Add `apps/api/routes_ui.py`.
- [x] Include the UI router in `apps/api/main.py`.
- [x] Add CORS configuration for `http://localhost:5173` and `http://127.0.0.1:5173`.
- [x] Keep CORS local-development scoped; do not enable `*` unless there is a documented reason.
- [x] Add Pydantic response schemas for UI payloads. Keep these schemas separate from raw domain schemas if they are presentation-oriented.
- [x] Add repository methods that filter by `run_id` and `symbol` together for:
  - analyst reports
  - debates
  - trader proposals
  - risk reviews
  - final decisions
  - paper orders
  - paper fills
  - paper positions
  - paper accounts
  - audit rows
- [x] Ensure server-side joins use the strongest available keys:
  - `run_id + symbol` for run trail artifacts
  - `decision_id` for replay and order/fill linkage
  - artifact IDs from `paper_runs.artifacts.symbols` when present
- [x] Build a shared helper that normalizes stage status into a small frontend vocabulary: `complete`, `running`, `blocked`, `rejected`, `failed`, `missing`, `skipped`.
- [x] Build a shared helper that formats missing stages with a clear reason instead of returning `null`.
- [x] Implement `/ui/overview`.
- [x] Implement `/ui/runs/{run_id}`.
- [x] Implement `/ui/runs/{run_id}/symbols/{symbol}/decision-trail`.
- [x] Implement `/ui/replay/{decision_id}`.
- [x] Implement `/ui/risk`.
- [x] Implement `/ui/portfolio`.
- [x] Implement `/ui/history`.
- [x] Add tests with completed runs, partial failures, unknown run IDs, unknown symbols, rejected or missing order cases, and replay not found cases.
- [x] Confirm existing raw endpoints still pass their current tests.

Endpoint responsibilities:

| Endpoint | Must answer |
|---|---|
| `/ui/overview` | What is happening now and what was the latest paper outcome? |
| `/ui/runs/{run_id}` | What happened inside this run across all requested symbols? |
| `/ui/runs/{run_id}/symbols/{symbol}/decision-trail` | Why did Taurus approve, reject, block, or skip this symbol? |
| `/ui/replay/{decision_id}` | What stored evidence chain belongs to this decision? |
| `/ui/risk` | Did safety gates work, and what did they block or reduce? |
| `/ui/portfolio` | What is the current simulated account and execution state? |
| `/ui/history` | Which previous runs should the user inspect? |

Deliverables:

- `apps/api/routes_ui.py`
- UI response schemas, either in `apps/api/routes_ui.py` or a dedicated module.
- Repository methods or query helpers for run-scoped artifact lookup.
- Unit tests covering aggregate endpoints.

Acceptance:

- [x] UI endpoints return data for a completed paper run.
- [x] UI endpoints return correct missing-stage state for failed or skipped symbols.
- [x] UI endpoints do not mix artifacts from different runs.
- [x] `GET /ui/runs/{run_id}/symbols/{symbol}/decision-trail` returns stages in the required display order.
- [x] `GET /ui/replay/{decision_id}` preserves raw replay artifacts.
- [x] Unknown run IDs, symbols, and decision IDs return appropriate 404 responses.
- [x] CORS allows the Vite dev server and does not broaden production exposure unnecessarily.
- [x] Existing raw API endpoints remain backward compatible.

Verification:

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m16-api.db make paper-loop-mock
DATABASE_URL=sqlite:////private/tmp/taurus-m16-api.db make api
curl http://localhost:8000/ui/overview
curl http://localhost:8000/ui/history
curl http://localhost:8000/ui/runs/<run_id>
curl http://localhost:8000/ui/runs/<run_id>/symbols/INFY/decision-trail
```

Notes:

- Added `apps/api/routes_ui.py` with read-only aggregate endpoints for overview, run detail, symbol decision trail, replay, risk, portfolio, and history.
- Added local Vite CORS origins only: `http://localhost:5173` and `http://127.0.0.1:5173`.
- Added run-scoped repository filters for trader proposals, risk reviews, final decisions, paper orders, paper fills, paper positions, and audit rows.
- Added `tests/unit/test_ui_aggregate_api.py` covering completed runs, partial failures, 404s, run-scoped repeated symbols, empty migrated database state, and CORS.
- Verification run used `run_id=pr-75fdbb0381152d57` and `decision_id=dec-1d59184394a64b42`; all `/ui/*` smoke checks returned `200`.

Completion summary:

- Assumptions made: UI aggregate APIs may return presentation-oriented payloads that wrap existing raw artifact payloads without changing the raw endpoints. Audit rows are run-scoped and symbol-filtered when the audit payload has symbol information; run-level audit rows are included for symbol trails. Empty database behavior assumes migrations have created the tables.
- Mocks created: Unit-test temporary SQLite databases, including completed paper runs, partial-failure runs, repeated-symbol run-scope checks, and migrated empty database state.
- Mocks used: Deterministic mock market data, mock news provider, mock LLM analyst outputs, mock alert provider, internal PaperBroker, and SQLite verification database at `/private/tmp/taurus-m16-api-20260521.db`.

## M16.3 - React App Foundation

Objective: scaffold the frontend app and wire it to the aggregate API.

Responsibility:

- Own the maintainable React application shell and frontend infrastructure.
- Provide typed API access, route skeletons, shared visual primitives, and build/test commands.
- Make later screen implementation a component task, not a tooling task.

Out of scope:

- No complete production screen implementation beyond placeholders and smoke-ready route shells.
- No frontend demo fixture mode.
- No direct dependency on Streamlit.

Implementation instructions:

- [ ] Create `apps/web`.
- [ ] Add Vite React TypeScript config.
- [ ] Add `pnpm-lock.yaml` and frontend package metadata.
- [ ] Add Tailwind config using Taurus/Stitch dark design tokens.
- [ ] Configure TypeScript strictness appropriate for the app. Avoid suppressing API type uncertainty with broad `any`.
- [ ] Add a simple directory structure:
  - `src/app` for providers and router
  - `src/api` for API client and DTO types
  - `src/components` for shared UI primitives
  - `src/features` for route-level feature components
  - `src/styles` for global CSS and design tokens
  - `src/test` for test utilities
- [ ] Add root-level Makefile targets for UI setup, dev, build, and tests.
- [ ] Add API base URL config through `VITE_TAURUS_API_BASE_URL`, defaulting to `http://localhost:8000`.
- [ ] Add React Router route skeletons.
- [ ] Add TanStack Query provider and shared API client.
- [ ] Add app shell with navigation and safety status area.
- [ ] Add shared status badge, metric card, panel, table, JSON drawer, empty state, and loading/error components.
- [ ] Add a route-level error boundary or equivalent error presentation.
- [ ] Add a consistent empty-state component that can show Taurus commands.
- [ ] Ensure the app shell works on desktop and mobile at a structural level.
- [ ] Add initial frontend tests.

Required shared components:

| Component | Responsibility |
|---|---|
| `AppShell` | Side nav, top bar, page container, safety status placement |
| `StatusBadge` | Centralized label/color/icon treatment for run, risk, decision, and order states |
| `MetricCard` | Account and run summary metrics |
| `DataPanel` | Reusable bordered card surface |
| `DataTable` | Compact read-only tables |
| `JsonDrawer` | Raw artifact inspection |
| `EmptyState` | Actionable empty or unavailable data guidance |
| `RefreshButton` | Manual TanStack Query refresh affordance |

Deliverables:

- `apps/web/package.json`
- `apps/web/vite.config.ts`
- `apps/web/tsconfig*.json`
- `apps/web/src/*`
- Tailwind and CSS setup
- Makefile UI targets
- Initial Vitest setup and component tests

Acceptance:

- [ ] `make setup-ui` installs dependencies.
- [ ] `make ui` starts the Vite app on port `5173`.
- [ ] The app shell renders with no backend data.
- [ ] All v1 routes render placeholder content without crashing.
- [ ] The API client reads `VITE_TAURUS_API_BASE_URL`.
- [ ] API errors produce actionable empty/error states.
- [ ] Shared components have basic tests.
- [ ] `make build-ui` produces a production build.

Verification:

```bash
make setup-ui
make ui
make test-ui
make build-ui
```

Completion summary:

- Assumptions made: TBD
- Mocks created: TBD
- Mocks used: TBD

## M16.4 - Core Observability Screens

Objective: implement the v1 screen set using real aggregate API data.

Responsibility:

- Own the user-facing dashboard experience.
- Convert aggregate API payloads into intuitive, connected visual flows.
- Make the React dashboard useful for actual run-loop investigation.

Out of scope:

- No new backend contract changes unless a screen cannot be built safely from M16.2 data.
- No write actions.
- No visual redesign outside the Stitch/Taurus direction unless required for usability.

Implementation instructions:

- [ ] Implement Overview screen.
- [ ] Implement Run Detail screen.
- [ ] Implement Symbol Decision Trail screen.
- [ ] Implement Decision Replay screen.
- [ ] Implement Risk Engine screen.
- [ ] Implement Portfolio & Account screen.
- [ ] Implement Run History screen.
- [ ] Add polling behavior and manual refresh.
- [ ] Add responsive layout for desktop, tablet, and mobile.
- [ ] Add raw JSON drawer or collapsible raw artifact panels.
- [ ] Add screen-level tests for route rendering and key states.

Screen responsibilities:

| Screen | Required behavior |
|---|---|
| Overview | Show safety mode, latest account state, latest run, latest final decision, latest paper order, recent runs, active positions, warnings, and empty-state commands. |
| Run Detail | Show run status, duration, schedule, timezone, symbols, succeeded/failed counts, market data summary, strategy summary, errors, and per-symbol pipeline progress. |
| Decision Trail | Show selected `run_id + symbol`, final outcome, staged timeline, active stage detail panel, artifact IDs, key scores, risk outcome, execution outcome, and raw JSON. |
| Replay | Search or route by `decision_id`, show replay note, stage counts, stage accordions, and raw artifacts. |
| Risk Engine | Show recent risk reviews, status counts, hard-rule table, persona reviews, reductions, rejections, blocks, and linked final decisions. |
| Portfolio & Account | Show latest account, cash, exposure, equity, P&L, positions, orders, fills, and slippage/cost metrics. |
| Run History | Show searchable/filterable run list with statuses, symbols, timing, success/failure counts, and navigation to run detail. |

Decision Trail stage requirements:

| Stage | Summary must show |
|---|---|
| Inputs | Market provider, candle count, latest data date, relevant events, freshness warnings |
| Analyst Reports | Report count, agent names, stance, score, confidence, key points, risks |
| Debate | Consensus label, consensus score, bull thesis, bear thesis, manager summary, uncertainties |
| Trader Proposal | Action, requested position percent, confidence, order type, entry rule, stop loss, take profit, invalidation rules |
| Risk Review | Status, requested vs approved position, hard-rule results, persona reviews, broker eligibility |
| Final Decision | Final action, status, approved quantity, reason, `can_send_to_broker` |
| Paper Order | Order ID, side, quantity, status, average fill, costs, slippage, rejection reason if any |
| Paper Fills | Fill IDs, fill sequence, quantity, reference price, fill price, costs, slippage bps |
| Audit Log | Event type, actor, note, timestamp, payload summary |

Polling requirements:

- Overview and history poll every 15 seconds.
- Running run detail and decision trail poll every 5 seconds.
- Completed run detail and decision trail should not aggressively poll.
- Every page has manual refresh.

Deliverables:

- Route implementations under `apps/web/src/features`.
- Screen tests for loading, empty, error, and populated states.
- Shared formatter utilities for INR, percentages, timestamps, and IDs.
- Centralized status mapping used across every screen.

Acceptance:

- [ ] User can navigate from overview to run detail to symbol decision trail.
- [ ] Decision trail displays all available stages in order.
- [ ] Missing artifacts are visible and labeled.
- [ ] The decision trail never silently omits a known stage.
- [ ] The selected run and symbol remain visible while inspecting details.
- [ ] Replay can be opened by `decision_id`.
- [ ] Risk screen highlights blocked/rejected/reduced decisions.
- [ ] Portfolio screen shows account, positions, orders, and fills.
- [ ] History screen supports status scanning and run navigation.
- [ ] Empty backend state shows commands to seed and run mock data.
- [ ] API unavailable state shows `make api`.
- [ ] The UI remains readable on desktop and mobile widths.

Verification:

```bash
make test-ui
make build-ui
make test
```

Manual smoke:

```bash
make dev-up
make migrate
make seed-mock
make import-mock-news
make paper-loop-mock
make api
make ui
```

Completion summary:

- Assumptions made: TBD
- Mocks created: TBD
- Mocks used: TBD

## M16.5 - Verification And Polish

Objective: make the React dashboard reliable enough to become the primary local observability UI.

Responsibility:

- Own final quality gates, documentation, and milestone completion hygiene.
- Confirm the React dashboard can be used as the primary local run-loop observability UI.
- Preserve safety defaults and existing fallback workflows.

Out of scope:

- No new features unless they fix acceptance criteria failures.
- No broad refactors unrelated to M16.
- No removal of Streamlit.

Implementation instructions:

- [ ] Run full backend and frontend verification.
- [ ] Validate layout against Stitch reference screens.
- [ ] Check mobile and desktop breakpoints.
- [ ] Update README with React UI commands.
- [ ] Update `docs/TAURUS_COMMANDS.md`.
- [ ] Update `docs/TAURUS_USAGE_GUIDE.md` if appropriate.
- [ ] Document known limitations.
- [ ] Keep Streamlit documented as fallback.
- [ ] Inspect `/Users/adnaan/.codex/rules/default.rules` at milestone completion and move accidental Taurus-specific global approvals into `.codex/rules/default.rules` if needed.
- [ ] Confirm `.gitignore` covers frontend build outputs, test coverage, and dependency folders.
- [ ] Confirm no real secrets, tokens, exported CSVs, or downloaded user data were committed.
- [ ] Confirm any new command approvals are Taurus-specific and project-local when required.
- [ ] Add final M16 notes to `docs/TAURUS_MILESTONE_TODO.md`.
- [ ] Record verification command outputs in the milestone notes.

Quality checklist:

- [ ] No TypeScript build errors.
- [ ] No Python compile errors.
- [ ] Backend tests pass.
- [ ] Frontend tests pass.
- [ ] Vite production build passes.
- [ ] Main API and UI smoke path works locally.
- [ ] Read-only scope is preserved.
- [ ] Safety banner clearly shows paper mode and live trading disabled.
- [ ] Streamlit fallback command remains documented.

Deliverables:

- Updated README and command docs.
- Updated usage guide if user workflow changes.
- Final M16 tracker notes.
- Verified React dashboard build.
- Completed milestone summary.

Acceptance:

- [ ] React dashboard is documented as the primary run-loop observability UI.
- [ ] Streamlit remains available as a fallback.
- [ ] Full test suite and frontend build pass.
- [ ] No live-trading or broker-control capability is introduced.
- [ ] Milestone completion summary lists assumptions made, mocks created, and mocks used.
- [ ] `/Users/adnaan/.codex/rules/default.rules` inspection requirement is satisfied and documented.

Verification:

```bash
make test
make lint
make test-ui
make build-ui
make taurus-smoke
```

Completion summary:

- Assumptions made: TBD
- Mocks created: TBD
- Mocks used: TBD

## Implementation Order

1. Complete M16.1 first so the visual references and route map are stable.
2. Complete M16.2 before building data-heavy screens.
3. Complete M16.3 after the API contract is stable enough for the frontend client.
4. Complete M16.4 screen by screen, starting with Overview, Run Detail, and Decision Trail.
5. Complete M16.5 only after both backend and frontend verification pass.

## Risks And Mitigations

- Risk: client-side joins show stale or mismatched artifacts.
  Mitigation: add aggregate `/ui/*` endpoints and run-scoped repository methods.

- Risk: visual implementation copies unmaintainable Stitch HTML.
  Mitigation: treat Stitch as reference assets and implement clean React components.

- Risk: React app becomes a control plane too early.
  Mitigation: v1 is read-only and exposes no mutation APIs.

- Risk: frontend dependency setup adds friction.
  Mitigation: document `pnpm` requirement and expose Makefile targets.

- Risk: mock data appears stale by real-market standards.
  Mitigation: label mock provider and show freshness warnings as observability data, not trading advice.

## Open Future Work

- Add authenticated remote deployment only after local read-only UI is stable.
- Add SSE/WebSocket live event streaming if polling becomes insufficient.
- Add guarded run-control actions only after safety and audit requirements are explicitly approved.
- Add richer account history once multiple account snapshots per run are persisted.
- Add UI integration screenshots or Playwright tests after the first stable frontend is available.
