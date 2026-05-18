.PHONY: setup dev-up dev-down api test lint

UV ?= uv
COMPOSE ?= docker compose

setup:
	$(UV) sync --dev

dev-up:
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

api:
	PYTHONPATH=packages:. $(UV) run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps packages tests
