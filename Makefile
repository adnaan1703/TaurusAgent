.PHONY: setup setup-ui dev-up dev-down api ui build-ui test-ui dashboard migrate seed-mock backtest-mock backtest-real-data import-mock-news import-screener import-price-csv run-analysts-mock debate-mock trader-proposal-mock risk-review-mock final-approval-mock paper-once-mock paper-loop-mock paper-loop-once paper-loop-start alert-smoke alert-test-telegram replay-decision backup-local backup-db restore-local taurus-smoke llm-smoke test lint

UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY
SYMBOLS ?= $(SYMBOL)
ROUNDS ?= 2
PAPER_LOOP_ITERATIONS ?= 1
PAPER_LOOP_INTERVAL_SECONDS ?= 60
PRICE_CSV ?= mock/market_data/prices_sample.csv
REAL_DATA_STRATEGY ?= configs/strategies/csv_market_data_smoke_v1.yaml
DECISION_ID ?= sample
BACKUP_DIR ?= backups

setup:
	$(UV) sync --dev

setup-ui:
	cd apps/web && $(PNPM) install

dev-up:
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

api:
	PYTHONPATH=packages:. $(UV) run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	cd apps/web && $(PNPM) dev

build-ui:
	cd apps/web && $(PNPM) build

test-ui:
	cd apps/web && $(PNPM) test

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

alert-smoke:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_ALERT_PROVIDER=mock PYTHONPATH=packages:. $(UV) run python scripts/alert_smoke.py

alert-test-telegram:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_ALERT_PROVIDER=telegram PYTHONPATH=packages:. $(UV) run python scripts/alert_smoke.py

replay-decision:
	DATABASE_URL="$(DATABASE_URL)" DECISION_ID="$(DECISION_ID)" SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/replay_decision.py

backup-local:
	DATABASE_URL="$(DATABASE_URL)" BACKUP_DIR="$(BACKUP_DIR)" PYTHONPATH=packages:. $(UV) run python scripts/backup_local.py

backup-db: backup-local

restore-local:
	DATABASE_URL="$(DATABASE_URL)" BACKUP="$(BACKUP)" RESTORE_CONFIRM="$(RESTORE_CONFIRM)" PYTHONPATH=packages:. $(UV) run python scripts/restore_local.py

taurus-smoke:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock TAURUS_ALERT_PROVIDER=mock SYMBOL="$(SYMBOL)" BACKUP_DIR="$(BACKUP_DIR)" PYTHONPATH=packages:. $(UV) run python scripts/taurus_smoke.py

llm-smoke:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/llm_smoke.py

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps/__init__.py apps/api apps/dashboard packages scripts tests
