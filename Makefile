.PHONY: setup dev-up dev-down api dashboard migrate seed-mock backtest-mock backtest-real-data import-mock-news import-screener import-price-csv run-analysts-mock debate-mock trader-proposal-mock risk-review-mock final-approval-mock paper-once-mock paper-loop-mock paper-loop-once paper-loop-start llm-smoke test lint

UV ?= uv
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY
SYMBOLS ?= $(SYMBOL)
ROUNDS ?= 2
PAPER_LOOP_ITERATIONS ?= 1
PAPER_LOOP_INTERVAL_SECONDS ?= 60
PRICE_CSV ?= mock/market_data/prices_sample.csv
REAL_DATA_STRATEGY ?= configs/strategies/csv_market_data_smoke_v1.yaml

setup:
	$(UV) sync --dev

dev-up:
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

api:
	PYTHONPATH=packages:. $(UV) run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

dashboard:
	DATABASE_URL="$(DATABASE_URL)" STREAMLIT_BROWSER_GATHER_USAGE_STATS=false PYTHONPATH=packages:. $(UV) run streamlit run apps/dashboard/main.py --server.port 8501 --server.headless true --browser.gatherUsageStats false

migrate:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/migrate.py

seed-mock:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/seed_mock_data.py

backtest-mock:
	DATABASE_URL="$(DATABASE_URL)" STRATEGY="$(STRATEGY)" PYTHONPATH=packages:. $(UV) run python scripts/run_backtest.py

backtest-real-data:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_MARKET_DATA_PROVIDER=csv CSV="$(if $(CSV),$(CSV),$(PRICE_CSV))" STRATEGY="$(REAL_DATA_STRATEGY)" PYTHONPATH=packages:. $(UV) run python scripts/run_backtest.py

import-mock-news:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/import_mock_news.py

import-screener:
	DATABASE_URL="$(DATABASE_URL)" CSV="$(CSV)" PYTHONPATH=packages:. $(UV) run python scripts/import_screener.py

import-price-csv:
	DATABASE_URL="$(DATABASE_URL)" CSV="$(if $(CSV),$(CSV),$(PRICE_CSV))" DIR="$(DIR)" PYTHONPATH=packages:. $(UV) run python scripts/import_price_csv.py

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

paper-loop-mock:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOLS="$(SYMBOLS)" PAPER_LOOP_ITERATIONS=1 PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

paper-loop-once:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOLS="$(SYMBOLS)" PAPER_LOOP_ITERATIONS=1 PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

paper-loop-start:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock SYMBOLS="$(SYMBOLS)" PAPER_LOOP_ITERATIONS="$(PAPER_LOOP_ITERATIONS)" PAPER_LOOP_INTERVAL_SECONDS="$(PAPER_LOOP_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

llm-smoke:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/llm_smoke.py

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps packages tests
