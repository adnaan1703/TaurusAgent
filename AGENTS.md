# Repository Guidelines

## Project Structure & Module Organization

Taurus is a Python and React monorepo for an observable, paper-trading-first algo trading MVP. Keep milestone work scoped to `docs/MILESTONE.md`.

- `apps/api/`: FastAPI app and route modules.
- `apps/web/`: primary React run-loop observability dashboard.
- `apps/dashboard/`: Streamlit fallback dashboard.
- `packages/taurus_core/`: shared core package for config, logging, observability, database access, Kite market data, analysts, research, risk, execution, paper trading, graph intelligence, alerts, replay, and ops.
- `configs/`: strategy YAMLs, market-data universes, and Taurus graph data inputs.
- `tests/unit/`: pytest unit tests.
- `infra/prometheus/` and `infra/grafana/`: observability config and dashboard assets.
- `scripts/`: operational scripts for migration, Kite auth/data sync, graph import/stats/projection, backtests, analyst/research/risk/final approval, paper runs, position monitoring, alerts, replay, backup, and smoke checks.
- `docs/`: specs, milestone prompts, command reference, and tracker.

## Build, Test, and Development Commands

- Use `uv` for all Python dependency management in this repo. Do not use global `pip install` for project packages.
- If external service docs say to use `pip`, translate that step to the `uv` equivalent:
  - add or remove dependencies with `uv add`, `uv remove`, or `uv sync`
  - install one-off packages inside the project environment with `uv pip install` or `uv run python -m pip` only when a package doc requires `pip` syntax
- `make setup`: install dependencies with `uv sync --dev`.
- `make setup-ui`: install React dependencies with `pnpm`.
- `make test`: run the pytest suite.
- `make test-ui`: run the React Vitest suite.
- `make lint`: compile-check Python files.
- `make api`: run the FastAPI dev server on port `8000`.
- `make ui`: run the React dev server on port `5173`.
- `make build-ui`: build the React app.
- `make migrate`: create/update the Postgres schema.
- `make dev-up`: start API, Postgres, Redis, Prometheus, and Grafana with Docker Compose.
- `make dev-down`: stop the local Docker Compose stack.
- `make paper-loop-kite`: run the canonical Kite-backed, graph-enabled local paper loop.
- `make position-monitor POSITION_MONITOR_ENABLED=true`: opt in to market-hours paper position monitoring.

Smoke checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

## Coding Style & Naming Conventions

Use Python 3.11+ and type annotations for new code. Prefer small modules with explicit names such as `routes_health.py`, `config.py`, and `metrics.py`. Use four-space indentation, snake_case for functions/modules, PascalCase for classes, and UPPER_SNAKE_CASE only for constants. Keep comments sparse and useful. Do not add live broker order routing or broaden real-money execution without a new explicit approved milestone.

## Testing Guidelines

Tests use `pytest` and live under `tests/unit/`. Name files `test_<behavior>.py` and tests `test_<expected_behavior>()`. Add tests for every meaningful behavior, especially config safety, deterministic output, and API responses. Run `make test` before marking a milestone task complete.

## Commit & Pull Request Guidelines

Git history is minimal (`Initial commit`, `init with plans`), so no strict convention exists yet. Use concise imperative commit messages, for example `Add M0 FastAPI foundation`. PRs should include scope, milestone ID, verification commands run, test results, and any user inputs or secrets required. Link related docs or issues when available.

## Security & Configuration

Never commit real API keys, broker credentials, Telegram tokens, or user CSV exports. Safe defaults belong in `.env.example`; local secrets belong in `.env`, which is ignored. `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` must remain defaults until a later approved milestone.

## Agent-Specific Instructions

Implement one milestone at a time. Update `docs/MILESTONE.md` whenever task status changes. Keep Codex command approvals project-local in `.codex/rules/default.rules`; do not broaden global approvals for this repo.

When planning future milestone sequences, use flat milestone IDs such as `M44`, `M45`, and `M46`. Do not create new submilestone identifiers such as `M44.1` unless the user explicitly requests submilestones. If a plan splits work into multiple execution chunks, each chunk must be a proper milestone with its own row in `docs/MILESTONE.md`.

For every new milestone plan document, update `docs/MILESTONE.md` in the same planning task:

- Add the plan document to `Active Sources`.
- Add a completed summary row for the plan-document creation itself, clearly stating that implementation remains planned if no implementation work was done.
- Add an explicit completion summary for the planning task with assumptions made, mocks created, and mocks used.
- Add a planned milestone tracker table using the established format: `Order`, `Milestone`, `Status`, `Plan`, and `Purpose`.
- Use `Planned`, `In Progress`, `Done`, or `Deferred` status values consistently.
- Keep milestone instructions in the linked plan document and keep the tracker concise.

Treat React dashboard M16 submilestones exactly like main milestones. After a submilestone is complete, verified, cleaned up, and documented with its completion summary, stop and report what was achieved. Do not automatically begin the next M16 submilestone unless the user explicitly asks to proceed.

At the completion of every milestone task, include an explicit completion summary section that lists: assumptions made, mocks created, and mocks used. If any category is empty, state `None` rather than omitting it.

At milestone completion and cleanup, inspect `/Users/adnaan/.codex/rules/default.rules`. Treat entries after the user's `# END MY CUSTOM ADDITION` marker as accidental global approvals. Any Taurus-specific approved prefixes found after that marker must be copied into `.codex/rules/default.rules` if missing, documented in `docs/TAURUS_COMMANDS.md`, and removed from the global rules file. Do not copy unrelated global approvals, such as `npx clasp`, into this project.
