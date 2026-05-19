.PHONY: setup dev-up dev-down api migrate seed-mock backtest-mock test lint

UV ?= uv
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus

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

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps packages tests
