.PHONY: setup setup-ui dev-up dev-down api ui build-ui test-ui dashboard migrate profile-list profile-create profile-archive profile-update-corpus backtest-mock import-mock-news import-screener import-market-data import-taurus-graph compute-graph-stats project-neo4j-graph sync-halal-stocks kite-login-url kite-exchange-token kite-sync-instruments import-kite-candles kite-ltp-smoke run-analysts-mock debate-mock trader-proposal-mock risk-review-mock final-approval-mock paper-once-mock paper-loop-once paper-loop-start paper-loop-kite position-monitor paper-loop-dashboard alert-smoke alert-test-telegram replay-decision backup-local backup-db restore-local taurus-smoke llm-smoke test lint

UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose
DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY
SYMBOLS ?= $(SYMBOL)
PAPER_LOOP_KITE_SYMBOL = $(if $(filter command line,$(origin SYMBOL)),$(SYMBOL),)
PAPER_LOOP_KITE_SYMBOLS = $(if $(filter command line,$(origin SYMBOLS)),$(SYMBOLS),)
ROUNDS ?= 2
PAPER_LOOP_ITERATIONS ?= 1
PAPER_LOOP_INTERVAL_SECONDS ?= 60
PAPER_LOOP_KITE_JSON ?= false
PAPER_LOOP_KITE_LOG_LEVEL ?= WARNING
POSITION_MONITOR_ENABLED ?= false
POSITION_MONITOR_ITERATIONS ?= 0
POSITION_MONITOR_INTERVAL_SECONDS ?= 30
FULL_ANALYST_ROSTER ?= technical,news,sentiment,fundamentals,graph
DATA_DIR ?= configs/taurus_data
AS_OF ?=
DECISION_ID ?= sample
BACKUP_DIR ?= backups
PROFILE_ID ?= client-a
PROFILE_DISPLAY_NAME ?= Client A
PROFILE_CORPUS_INR ?= 250000
PROFILE_CURRENCY ?= INR

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
	$(MAKE) import-market-data
	$(MAKE) import-taurus-graph
	$(MAKE) compute-graph-stats
	$(MAKE) import-mock-news
	$(MAKE) paper-loop-kite
	$(MAKE) ui

build-ui:
	cd apps/web && $(PNPM) build

test-ui:
	cd apps/web && $(PNPM) test

dashboard:
	DATABASE_URL="$(DATABASE_URL)" STREAMLIT_BROWSER_GATHER_USAGE_STATS=false PYTHONPATH=packages:. $(UV) run streamlit run apps/dashboard/main.py --server.port 8501 --server.headless true --browser.gatherUsageStats false

migrate:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/migrate.py

profile-list:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py list

profile-create:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py create --profile-id "$(PROFILE_ID)" --display-name "$(PROFILE_DISPLAY_NAME)" --corpus-inr "$(PROFILE_CORPUS_INR)" --currency "$(PROFILE_CURRENCY)"

profile-archive:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py archive --profile-id "$(PROFILE_ID)"

profile-update-corpus:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py update-corpus --profile-id "$(PROFILE_ID)" --corpus-inr "$(PROFILE_CORPUS_INR)"

backtest-mock:
	DATABASE_URL="$(DATABASE_URL)" STRATEGY="$(STRATEGY)" PYTHONPATH=packages:. $(UV) run python scripts/run_backtest.py

import-mock-news:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/import_mock_news.py

import-screener:
	DATABASE_URL="$(DATABASE_URL)" CSV="$(CSV)" PYTHONPATH=packages:. $(UV) run python scripts/import_screener.py

import-market-data: import-kite-candles

import-taurus-graph:
	DATABASE_URL="$(DATABASE_URL)" DATA_DIR="$(DATA_DIR)" PYTHONPATH=packages:. $(UV) run python scripts/import_taurus_graph.py

compute-graph-stats:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python -m taurus_core.graph.compute_edge_stats $(if $(AS_OF),--as-of "$(AS_OF)",)

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
	DATABASE_URL="$(DATABASE_URL)" SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_analysts.py

debate-mock:
	DATABASE_URL="$(DATABASE_URL)" SYMBOL="$(SYMBOL)" ROUNDS="$(ROUNDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_research_debate.py

trader-proposal-mock:
	DATABASE_URL="$(DATABASE_URL)" SYMBOL="$(SYMBOL)" ROUNDS="$(ROUNDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_trader_proposal.py

risk-review-mock:
	DATABASE_URL="$(DATABASE_URL)" SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_risk_review.py

final-approval-mock:
	DATABASE_URL="$(DATABASE_URL)" SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_final_approval.py

paper-once-mock:
	DATABASE_URL="$(DATABASE_URL)" SYMBOL="$(SYMBOL)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_once.py

paper-loop-once:
	DATABASE_URL="$(DATABASE_URL)" SYMBOLS="$(SYMBOLS)" PAPER_LOOP_ITERATIONS=1 PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

paper-loop-start:
	DATABASE_URL="$(DATABASE_URL)" SYMBOLS="$(SYMBOLS)" PAPER_LOOP_ITERATIONS="$(PAPER_LOOP_ITERATIONS)" PAPER_LOOP_INTERVAL_SECONDS="$(PAPER_LOOP_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

paper-loop-kite:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_LOG_LEVEL="$(PAPER_LOOP_KITE_LOG_LEVEL)" TAURUS_MARKET_DATA_PROVIDER=kite TAURUS_ENABLED_ANALYSTS=technical,graph TAURUS_GRAPH_ENABLED=true TAURUS_GRAPH_RISK_ENABLED=true TAURUS_PAPER_ANALYSIS_SCOPE=full_universe TAURUS_PAPER_EXECUTION_SCOPE=allocated_only TAURUS_PAPER_LOOP_JSON="$(PAPER_LOOP_KITE_JSON)" STRATEGY=configs/strategies/graph_aware_score_v1.yaml SYMBOL="$(PAPER_LOOP_KITE_SYMBOL)" SYMBOLS="$(PAPER_LOOP_KITE_SYMBOLS)" PAPER_LOOP_ITERATIONS="$(PAPER_LOOP_ITERATIONS)" PAPER_LOOP_INTERVAL_SECONDS="$(PAPER_LOOP_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

position-monitor:
	DATABASE_URL="$(DATABASE_URL)" TAURUS_POSITION_MONITOR_ENABLED="$(POSITION_MONITOR_ENABLED)" TAURUS_POSITION_MONITOR_PROVIDER=kite TAURUS_POSITION_MONITOR_MAX_ITERATIONS="$(POSITION_MONITOR_ITERATIONS)" TAURUS_POSITION_MONITOR_INTERVAL_SECONDS="$(POSITION_MONITOR_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_position_monitor.py

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
	DATABASE_URL="$(DATABASE_URL)" TAURUS_ALERT_PROVIDER=mock TAURUS_ENABLED_ANALYSTS="$(FULL_ANALYST_ROSTER)" SYMBOL="$(SYMBOL)" BACKUP_DIR="$(BACKUP_DIR)" PYTHONPATH=packages:. $(UV) run python scripts/taurus_smoke.py

llm-smoke:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/llm_smoke.py

test:
	$(UV) run pytest

lint:
	$(UV) run python -m compileall apps/__init__.py apps/api apps/dashboard packages scripts tests
