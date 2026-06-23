.PHONY: setup setup-ui dev-up dev-down api ui build-ui test-ui dashboard migrate profile-list profile-create profile-archive profile-update-corpus backtest-mock validate-technical-v2 import-mock-news import-screener import-market-data import-official-index-data check-official-index-readiness import-official-microstructure-data check-official-microstructure-readiness import-taurus-graph compute-graph-stats project-neo4j-graph sync-halal-stocks kite-login-url kite-exchange-token kite-sync-instruments import-kite-candles kite-ltp-smoke run-analysts-mock debate-mock trader-proposal-mock risk-review-mock final-approval-mock paper-once-mock paper-loop-once paper-loop-start paper-loop-kite position-monitor paper-loop-dashboard alert-smoke alert-test-telegram replay-decision backup-local backup-db restore-local taurus-smoke llm-smoke test lint

UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose

define DOTENV_VALUE
$(strip $(shell awk -F= '$$0 !~ /^[[:space:]]*(#|$$)/ && $$1 == "$(1)" {sub(/^[^=]*=/, ""); print; exit}' .env 2>/dev/null))
endef

define LOAD_DOTENV_IF_UNSET
ifeq ($(origin $(1)),undefined)
ifneq ($(call DOTENV_VALUE,$(1)),)
$(1) := $(call DOTENV_VALUE,$(1))
endif
endif
endef

$(eval $(call LOAD_DOTENV_IF_UNSET,DATABASE_URL))
$(eval $(call LOAD_DOTENV_IF_UNSET,PAPER_LOOP_ITERATIONS))
$(eval $(call LOAD_DOTENV_IF_UNSET,PAPER_LOOP_INTERVAL_SECONDS))
$(eval $(call LOAD_DOTENV_IF_UNSET,STRATEGY))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_ENABLED_ANALYSTS))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_GRAPH_ENABLED))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_GRAPH_RISK_ENABLED))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_LOG_LEVEL))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_MARKET_DATA_PROVIDER))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_PAPER_ANALYSIS_SCOPE))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_PAPER_EXECUTION_SCOPE))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_PAPER_LOOP_JSON))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_PROFILE_ID))
$(eval $(call LOAD_DOTENV_IF_UNSET,TAURUS_TARGET_MARKET_UNIVERSE_PATH))

DATABASE_URL ?= postgresql+psycopg://taurus:taurus@localhost:5432/taurus
SYMBOL ?= INFY
SYMBOLS ?= $(SYMBOL)
PAPER_LOOP_KITE_SYMBOL = $(if $(filter command line,$(origin SYMBOL)),$(SYMBOL),)
PAPER_LOOP_KITE_SYMBOLS = $(if $(filter command line,$(origin SYMBOLS)),$(SYMBOLS),)
ROUNDS ?= 2
PAPER_LOOP_ITERATIONS ?= 1
PAPER_LOOP_INTERVAL_SECONDS ?= 60
TAURUS_PAPER_LOOP_JSON ?= false
PAPER_LOOP_KITE_JSON ?= $(TAURUS_PAPER_LOOP_JSON)
TAURUS_LOG_LEVEL ?= WARNING
PAPER_LOOP_KITE_LOG_LEVEL ?= $(TAURUS_LOG_LEVEL)
POSITION_MONITOR_ENABLED ?= false
POSITION_MONITOR_ITERATIONS ?= 0
POSITION_MONITOR_INTERVAL_SECONDS ?= 30
FULL_ANALYST_ROSTER ?= technical,news,sentiment,fundamentals,graph
DATA_DIR ?= configs/taurus_data
TAURUS_MARKET_DATA_PROVIDER ?= kite
TAURUS_ENABLED_ANALYSTS ?= technical,graph
TAURUS_GRAPH_ENABLED ?= true
TAURUS_GRAPH_RISK_ENABLED ?= true
TAURUS_PAPER_ANALYSIS_SCOPE ?= full_universe
TAURUS_PAPER_EXECUTION_SCOPE ?= allocated_only
TAURUS_TARGET_MARKET_UNIVERSE_PATH ?= configs/market_data/nifty_500_shariah.yaml
STRATEGY ?= configs/strategies/graph_aware_score_v1.yaml
AS_OF ?=
DECISION_ID ?= sample
BACKUP_DIR ?= backups
PROFILE_ID ?=
PROFILE_COMMAND_ID ?= $(if $(PROFILE_ID),$(PROFILE_ID),client-a)
TAURUS_PROFILE_ID ?= local-paper
PAPER_PROFILE_ID ?= $(if $(PROFILE_ID),$(PROFILE_ID),$(TAURUS_PROFILE_ID))
PROFILE_DISPLAY_NAME ?= Client A
PROFILE_CORPUS_INR ?= 250000
PROFILE_CURRENCY ?= INR
TECHNICAL_VALIDATION_MODE ?= standard
TECHNICAL_VALIDATION_UNIVERSE ?= $(if $(TAURUS_TARGET_MARKET_UNIVERSE_PATH),$(TAURUS_TARGET_MARKET_UNIVERSE_PATH),$(TAURUS_MARKET_DATA_UNIVERSE_PATH))
TECHNICAL_VALIDATION_SYMBOLS ?=
TECHNICAL_VALIDATION_ARTIFACT_ROOT ?= artifacts/technical_validation
TECHNICAL_VALIDATION_REPORT_ROOT ?= docs/reports/technical_validation
TECHNICAL_VALIDATION_STRICT_INSUFFICIENT ?= false
TECHNICAL_VALIDATION_INITIAL_CAPITAL_INR ?= $(TAURUS_INITIAL_CAPITAL_INR)
TECHNICAL_VALIDATION_MAX_OPEN_POSITIONS ?= $(TAURUS_MAX_OPEN_POSITIONS)
TECHNICAL_VALIDATION_PORTFOLIO_BREADTH ?= $(TAURUS_BACKTEST_TARGET_POSITIONS)
TECHNICAL_VALIDATION_REBALANCE_EVERY_DAYS ?= 21
TECHNICAL_VALIDATION_COST_BPS ?= 10
TECHNICAL_VALIDATION_SLIPPAGE_BPS ?= $(TAURUS_PAPER_SLIPPAGE_BPS)
OFFICIAL_INDEX_CSV ?=
OFFICIAL_INDEX_SYMBOL ?=
OFFICIAL_INDEX_NAME ?=
OFFICIAL_INDEX_FAMILY ?=
OFFICIAL_INDEX_SOURCE ?= nse_official_index_csv
OFFICIAL_INDEX_SOURCE_URL ?=
OFFICIAL_INDEX_TIMEFRAME ?= 1d
OFFICIAL_INDEX_BENCHMARK_SYMBOLS ?= NIFTY_50
OFFICIAL_INDEX_SECTOR_SYMBOLS ?=
OFFICIAL_INDEX_VOLATILITY_SYMBOLS ?= INDIA_VIX
OFFICIAL_INDEX_START_DATE ?=
OFFICIAL_INDEX_END_DATE ?=
OFFICIAL_INDEX_READINESS_OUTPUT ?= artifacts/technical_validation/official_index_readiness.json
OFFICIAL_MICROSTRUCTURE_CSV ?=
OFFICIAL_MICROSTRUCTURE_SOURCE ?= nse_security_wise_csv
OFFICIAL_MICROSTRUCTURE_SOURCE_URL ?=
OFFICIAL_MICROSTRUCTURE_TIMEFRAME ?= 1d
OFFICIAL_MICROSTRUCTURE_IMPACT_COST_SOURCE_KIND ?= unavailable
OFFICIAL_MICROSTRUCTURE_IMPACT_COST_PROXY_NAME ?=
OFFICIAL_MICROSTRUCTURE_SYMBOLS ?=
OFFICIAL_MICROSTRUCTURE_REQUIRED_FAMILIES ?= delivery,circuit,tradability
OFFICIAL_MICROSTRUCTURE_START_DATE ?=
OFFICIAL_MICROSTRUCTURE_END_DATE ?=
OFFICIAL_MICROSTRUCTURE_READINESS_OUTPUT ?= artifacts/technical_validation/official_microstructure_readiness.json

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
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py create --profile-id "$(PROFILE_COMMAND_ID)" --display-name "$(PROFILE_DISPLAY_NAME)" --corpus-inr "$(PROFILE_CORPUS_INR)" --currency "$(PROFILE_CURRENCY)"

profile-archive:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py archive --profile-id "$(PROFILE_COMMAND_ID)"

profile-update-corpus:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/manage_profiles.py update-corpus --profile-id "$(PROFILE_COMMAND_ID)" --corpus-inr "$(PROFILE_CORPUS_INR)"

backtest-mock:
	DATABASE_URL="$(DATABASE_URL)" STRATEGY="$(STRATEGY)" PYTHONPATH=packages:. $(UV) run python scripts/run_backtest.py

validate-technical-v2:
	DATABASE_URL="$(DATABASE_URL)" TECHNICAL_VALIDATION_MODE="$(TECHNICAL_VALIDATION_MODE)" TECHNICAL_VALIDATION_UNIVERSE="$(TECHNICAL_VALIDATION_UNIVERSE)" TECHNICAL_VALIDATION_SYMBOLS="$(TECHNICAL_VALIDATION_SYMBOLS)" TECHNICAL_VALIDATION_ARTIFACT_ROOT="$(TECHNICAL_VALIDATION_ARTIFACT_ROOT)" TECHNICAL_VALIDATION_REPORT_ROOT="$(TECHNICAL_VALIDATION_REPORT_ROOT)" TECHNICAL_VALIDATION_INITIAL_CAPITAL_INR="$(TECHNICAL_VALIDATION_INITIAL_CAPITAL_INR)" TECHNICAL_VALIDATION_MAX_OPEN_POSITIONS="$(TECHNICAL_VALIDATION_MAX_OPEN_POSITIONS)" TECHNICAL_VALIDATION_PORTFOLIO_BREADTH="$(TECHNICAL_VALIDATION_PORTFOLIO_BREADTH)" TECHNICAL_VALIDATION_REBALANCE_EVERY_DAYS="$(TECHNICAL_VALIDATION_REBALANCE_EVERY_DAYS)" TECHNICAL_VALIDATION_COST_BPS="$(TECHNICAL_VALIDATION_COST_BPS)" TECHNICAL_VALIDATION_SLIPPAGE_BPS="$(TECHNICAL_VALIDATION_SLIPPAGE_BPS)" TECHNICAL_VALIDATION_STRICT_INSUFFICIENT="$(TECHNICAL_VALIDATION_STRICT_INSUFFICIENT)" PYTHONPATH=packages:. $(UV) run python scripts/validate_technical_v2.py

import-mock-news:
	DATABASE_URL="$(DATABASE_URL)" PYTHONPATH=packages:. $(UV) run python scripts/import_mock_news.py

import-screener:
	DATABASE_URL="$(DATABASE_URL)" CSV="$(CSV)" PYTHONPATH=packages:. $(UV) run python scripts/import_screener.py

import-market-data: import-kite-candles

import-official-index-data:
	DATABASE_URL="$(DATABASE_URL)" OFFICIAL_INDEX_CSV="$(OFFICIAL_INDEX_CSV)" OFFICIAL_INDEX_SYMBOL="$(OFFICIAL_INDEX_SYMBOL)" OFFICIAL_INDEX_NAME="$(OFFICIAL_INDEX_NAME)" OFFICIAL_INDEX_FAMILY="$(OFFICIAL_INDEX_FAMILY)" OFFICIAL_INDEX_SOURCE="$(OFFICIAL_INDEX_SOURCE)" OFFICIAL_INDEX_SOURCE_URL="$(OFFICIAL_INDEX_SOURCE_URL)" OFFICIAL_INDEX_TIMEFRAME="$(OFFICIAL_INDEX_TIMEFRAME)" PYTHONPATH=packages:. $(UV) run python scripts/import_official_index_data.py import

check-official-index-readiness:
	DATABASE_URL="$(DATABASE_URL)" OFFICIAL_INDEX_BENCHMARK_SYMBOLS="$(OFFICIAL_INDEX_BENCHMARK_SYMBOLS)" OFFICIAL_INDEX_SECTOR_SYMBOLS="$(OFFICIAL_INDEX_SECTOR_SYMBOLS)" OFFICIAL_INDEX_VOLATILITY_SYMBOLS="$(OFFICIAL_INDEX_VOLATILITY_SYMBOLS)" OFFICIAL_INDEX_START_DATE="$(OFFICIAL_INDEX_START_DATE)" OFFICIAL_INDEX_END_DATE="$(OFFICIAL_INDEX_END_DATE)" OFFICIAL_INDEX_TIMEFRAME="$(OFFICIAL_INDEX_TIMEFRAME)" OFFICIAL_INDEX_READINESS_OUTPUT="$(OFFICIAL_INDEX_READINESS_OUTPUT)" PYTHONPATH=packages:. $(UV) run python scripts/import_official_index_data.py readiness

import-official-microstructure-data:
	DATABASE_URL="$(DATABASE_URL)" OFFICIAL_MICROSTRUCTURE_CSV="$(OFFICIAL_MICROSTRUCTURE_CSV)" OFFICIAL_MICROSTRUCTURE_SOURCE="$(OFFICIAL_MICROSTRUCTURE_SOURCE)" OFFICIAL_MICROSTRUCTURE_SOURCE_URL="$(OFFICIAL_MICROSTRUCTURE_SOURCE_URL)" OFFICIAL_MICROSTRUCTURE_TIMEFRAME="$(OFFICIAL_MICROSTRUCTURE_TIMEFRAME)" OFFICIAL_MICROSTRUCTURE_IMPACT_COST_SOURCE_KIND="$(OFFICIAL_MICROSTRUCTURE_IMPACT_COST_SOURCE_KIND)" OFFICIAL_MICROSTRUCTURE_IMPACT_COST_PROXY_NAME="$(OFFICIAL_MICROSTRUCTURE_IMPACT_COST_PROXY_NAME)" PYTHONPATH=packages:. $(UV) run python scripts/import_official_microstructure_data.py import

check-official-microstructure-readiness:
	DATABASE_URL="$(DATABASE_URL)" OFFICIAL_MICROSTRUCTURE_SYMBOLS="$(OFFICIAL_MICROSTRUCTURE_SYMBOLS)" OFFICIAL_MICROSTRUCTURE_REQUIRED_FAMILIES="$(OFFICIAL_MICROSTRUCTURE_REQUIRED_FAMILIES)" OFFICIAL_MICROSTRUCTURE_START_DATE="$(OFFICIAL_MICROSTRUCTURE_START_DATE)" OFFICIAL_MICROSTRUCTURE_END_DATE="$(OFFICIAL_MICROSTRUCTURE_END_DATE)" OFFICIAL_MICROSTRUCTURE_TIMEFRAME="$(OFFICIAL_MICROSTRUCTURE_TIMEFRAME)" OFFICIAL_MICROSTRUCTURE_READINESS_OUTPUT="$(OFFICIAL_MICROSTRUCTURE_READINESS_OUTPUT)" PYTHONPATH=packages:. $(UV) run python scripts/import_official_microstructure_data.py readiness

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
	DATABASE_URL="$(DATABASE_URL)" TAURUS_TARGET_MARKET_UNIVERSE_PATH="$(TAURUS_TARGET_MARKET_UNIVERSE_PATH)" TAURUS_PROFILE_ID="$(PAPER_PROFILE_ID)" TAURUS_LOG_LEVEL="$(PAPER_LOOP_KITE_LOG_LEVEL)" TAURUS_MARKET_DATA_PROVIDER="$(TAURUS_MARKET_DATA_PROVIDER)" TAURUS_ENABLED_ANALYSTS="$(TAURUS_ENABLED_ANALYSTS)" TAURUS_GRAPH_ENABLED="$(TAURUS_GRAPH_ENABLED)" TAURUS_GRAPH_RISK_ENABLED="$(TAURUS_GRAPH_RISK_ENABLED)" TAURUS_PAPER_ANALYSIS_SCOPE="$(TAURUS_PAPER_ANALYSIS_SCOPE)" TAURUS_PAPER_EXECUTION_SCOPE="$(TAURUS_PAPER_EXECUTION_SCOPE)" TAURUS_PAPER_LOOP_JSON="$(PAPER_LOOP_KITE_JSON)" STRATEGY="$(STRATEGY)" SYMBOL="$(PAPER_LOOP_KITE_SYMBOL)" SYMBOLS="$(PAPER_LOOP_KITE_SYMBOLS)" PAPER_LOOP_ITERATIONS="$(PAPER_LOOP_ITERATIONS)" PAPER_LOOP_INTERVAL_SECONDS="$(PAPER_LOOP_INTERVAL_SECONDS)" PYTHONPATH=packages:. $(UV) run python scripts/run_paper_loop.py

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
