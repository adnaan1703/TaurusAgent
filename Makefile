.PHONY: setup setup-ui dev-up dev-down api ui build-ui test-ui dashboard migrate seed-mock backtest-mock backtest-real-data import-mock-news import-screener import-price-csv import-taurus-graph project-neo4j-graph sync-halal-stocks kite-login-url kite-exchange-token kite-sync-instruments import-kite-candles kite-ltp-smoke run-analysts-mock debate-mock trader-proposal-mock risk-review-mock final-approval-mock paper-once-mock paper-loop-mock paper-loop-once paper-loop-start paper-loop-kite paper-loop-dashboard alert-smoke alert-test-telegram replay-decision backup-local backup-db restore-local taurus-smoke llm-smoke test lint

UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY
SYMBOLS ?= $(SYMBOL)
ROUNDS ?= 2
PAPER_LOOP_ITERATIONS ?= 1
PAPER_LOOP_INTERVAL_SECONDS ?= 60
FULL_ANALYST_ROSTER ?= technical,news,sentiment,fundamentals
PRICE_CSV ?= mock/market_data/prices_sample.csv
DATA_DIR ?= configs/taurus_data
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
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	cd apps/web && $(PNPM) dev

paper-loop-dashboard:
	$(MAKE) dev-up
	$(MAKE) migrate
	$(MAKE) seed-mock
	$(MAKE) import-mock-news
	$(MAKE) paper-loop-mock
	$(MAKE) ui

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

import-taurus-graph:
	DATABASE_URL="$(DATABASE_URL)" DATA_DIR="$(DATA_DIR)" PYTHONPATH=packages:. $(UV) run python scripts/import_taurus_graph.py

project-neo4j-graph:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/project_neo4j_graph.py

sync-halal-stocks:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/sync_halal_stocks.py

kite-login-url:
	PYTHONPATH=packages:. $(UV) run python scripts/kite_auth.py login-url

kite-exchange-token:
	PYTHONPATH=packages:. $(UV) run python scripts/kite_auth.py exchange --request-token "$(REQUEST_TOKEN)"

kite-sync-instruments:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_MARKET_DATA_PROVIDER=kite PYTHONPATH=packages:. $(UV) run python scripts/sync_kite_instruments.py

import-kite-candles:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_MARKET_DATA_PROVIDER=kite PYTHONPATH=packages:. $(UV) run python scripts/import_kite_candles.py

kite-ltp-smoke:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_MARKET_DATA_PROVIDER=kite PYTHONPATH=packages:. $(UV) run python scripts/kite_ltp_smoke.py

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

paper-loop-kite:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_MARKET_DATA_PROVIDER=kite TAURUS_LLM_PROVIDER=mock SYMBOL="" SYMBOLS="" PAPER_LOOP_ITERATIONS="$(PAPER_LOOP_ITERATIONS)" PAPER_LOOP_INTERVAL_SECONDS="$(PAPER_LOOP_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

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
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LLM_PROVIDER=mock TAURUS_ALERT_PROVIDER=mock TAURUS_ENABLED_ANALYSTS="$(FULL_ANALYST_ROSTER)" SYMBOL="$(SYMBOL)" BACKUP_DIR="$(BACKUP_DIR)" PYTHONPATH=packages:. $(UV) run python scripts/taurus_smoke.py

llm-smoke:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/llm_smoke.py

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps/__init__.py apps/api apps/dashboard packages scripts tests
