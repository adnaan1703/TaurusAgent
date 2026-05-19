.PHONY: setup dev-up dev-down api migrate seed-mock backtest-mock import-mock-news run-analysts-mock llm-smoke test lint

UV ?= uv
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY

setup:
	$(UV) sync --dev

dev-up:
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

api:
	PYTHONPATH=packages:. $(UV) run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

migrate:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/migrate.py

seed-mock:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/seed_mock_data.py

backtest-mock:
	DATABASE_URL="$(DATABASE_URL)" STRATEGY="$(STRATEGY)" PYTHONPATH=packages:. $(UV) run python scripts/run_backtest.py

import-mock-news:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/import_mock_news.py

run-analysts-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_analysts.py

llm-smoke:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/llm_smoke.py

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps packages tests
