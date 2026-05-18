# Repository Guidelines

## Project Structure & Module Organization

Taurus is a Python monorepo for an observable, paper-trading-first algo trading MVP. Keep milestone work scoped to `docs/TAURUS_MILESTONE_TODO.md`.

- `apps/api/`: FastAPI app and route modules.
- `apps/dashboard/`: Streamlit dashboard placeholder; dashboard work starts in later milestones.
- `packages/taurus_core/`: shared core package for config, logging, observability, and future trading domains.
- `tests/unit/`: pytest unit tests.
- `infra/prometheus/` and `infra/grafana/`: observability config and dashboard assets.
- `scripts/`: operational scripts added by later milestones.
- `docs/`: specs, milestone prompts, command reference, and tracker.

## Build, Test, and Development Commands

- `make setup`: install dependencies with `uv sync --dev`.
- `make test`: run the pytest suite.
- `make lint`: compile-check Python files.
- `make api`: run the FastAPI dev server on port `8000`.
- `make dev-up`: start API, Postgres, Redis, Prometheus, and Grafana with Docker Compose.
- `make dev-down`: stop the local Docker Compose stack.

Smoke checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

## Coding Style & Naming Conventions

Use Python 3.11+ and type annotations for new code. Prefer small modules with explicit names such as `routes_health.py`, `config.py`, and `metrics.py`. Use four-space indentation, snake_case for functions/modules, PascalCase for classes, and UPPER_SNAKE_CASE only for constants. Keep comments sparse and useful. Do not add trading, broker, LLM, or data features before their milestone.

## Testing Guidelines

Tests use `pytest` and live under `tests/unit/`. Name files `test_<behavior>.py` and tests `test_<expected_behavior>()`. Add tests for every meaningful behavior, especially config safety, deterministic output, and API responses. Run `make test` before marking a milestone task complete.

## Commit & Pull Request Guidelines

Git history is minimal (`Initial commit`, `init with plans`), so no strict convention exists yet. Use concise imperative commit messages, for example `Add M0 FastAPI foundation`. PRs should include scope, milestone ID, verification commands run, test results, and any user inputs or secrets required. Link related docs or issues when available.

## Security & Configuration

Never commit real API keys, broker credentials, Telegram tokens, or user CSV exports. Safe defaults belong in `.env.example`; local secrets belong in `.env`, which is ignored. `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` must remain defaults until a later approved milestone.

## Agent-Specific Instructions

Implement one milestone at a time. Update `docs/TAURUS_MILESTONE_TODO.md` whenever task status changes. Keep Codex command approvals project-local in `.codex/rules/default.rules`; do not broaden global approvals for this repo.

At milestone completion and cleanup, inspect `/Users/adnaan/.codex/rules/default.rules`. Treat entries after the user's `# END MY CUSTOM ADDITION` marker as accidental global approvals. Any Taurus-specific approved prefixes found after that marker must be copied into `.codex/rules/default.rules` if missing, documented in `docs/TAURUS_COMMANDS.md`, and removed from the global rules file. Do not copy unrelated global approvals, such as `npx clasp`, into this project.
