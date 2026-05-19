.PHONY: setup dev-up dev-down api migrate seed-mock backtest-mock import-mock-news run-analysts-mock debate-mock trader-proposal-mock risk-review-mock final-approval-mock paper-once-mock paper-loop-once paper-loop-start llm-smoke test lint

UV ?= uv
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY
ROUNDS ?= 2
PAPER_LOOP_ITERATIONS ?= 1
PAPER_LOOP_INTERVAL_SECONDS ?= 60

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

debate-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" ROUNDS="$(ROUNDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_research_debate.py

trader-proposal-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" ROUNDS="$(ROUNDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_trader_proposal.py

risk-review-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_risk_review.py

final-approval-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_final_approval.py

paper-once-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_once.py

paper-loop-once:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" PAPER_LOOP_ITERATIONS=1 PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

paper-loop-start:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOL="$(SYMBOL)" PAPER_LOOP_ITERATIONS="$(PAPER_LOOP_ITERATIONS)" PAPER_LOOP_INTERVAL_SECONDS="$(PAPER_LOOP_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

llm-smoke:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/llm_smoke.py

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps packages tests
