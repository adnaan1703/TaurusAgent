# Graph Report - TaurusAgent  (2026-05-19)

## Corpus Check
- 143 files · ~55,519 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1226 nodes · 2721 edges · 86 communities (67 shown, 19 thin omitted)
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 1128 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9b65d536`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Trading Strategies|Trading Strategies]]
- [[_COMMUNITY_API Endpoints|API Endpoints]]
- [[_COMMUNITY_Data Models|Data Models]]
- [[_COMMUNITY_LLM Integration|LLM Integration]]
- [[_COMMUNITY_Backtesting Engine|Backtesting Engine]]
- [[_COMMUNITY_Risk Management|Risk Management]]
- [[_COMMUNITY_Dashboard Components|Dashboard Components]]
- [[_COMMUNITY_Database Models|Database Models]]
- [[_COMMUNITY_Agent Architecture|Agent Architecture]]
- [[_COMMUNITY_Observability|Observability]]
- [[_COMMUNITY_Brokers|Brokers]]
- [[_COMMUNITY_Features & Indicators|Features & Indicators]]
- [[_COMMUNITY_Research Tools|Research Tools]]
- [[_COMMUNITY_Execution Engine|Execution Engine]]
- [[_COMMUNITY_Configuration|Configuration]]
- [[_COMMUNITY_Core Services|Core Services]]
- [[_COMMUNITY_Market Data|Market Data]]
- [[_COMMUNITY_Intelligence|Intelligence]]
- [[_COMMUNITY_Prometheus Metrics|Prometheus Metrics]]
- [[_COMMUNITY_Grafana Dashboards|Grafana Dashboards]]
- [[_COMMUNITY_Testing Framework|Testing Framework]]
- [[_COMMUNITY_Scripts & Utilities|Scripts & Utilities]]
- [[_COMMUNITY_Documentation|Documentation]]
- [[_COMMUNITY_Agent Workflows|Agent Workflows]]
- [[_COMMUNITY_Paper Trading|Paper Trading]]
- [[_COMMUNITY_Order Management|Order Management]]
- [[_COMMUNITY_Event Processing|Event Processing]]
- [[_COMMUNITY_News Integration|News Integration]]
- [[_COMMUNITY_Agent Communication|Agent Communication]]
- [[_COMMUNITY_Risk Review|Risk Review]]
- [[_COMMUNITY_Sentiment Analysis|Sentiment Analysis]]
- [[_COMMUNITY_Financial Instruments|Financial Instruments]]
- [[_COMMUNITY_Technical Indicators|Technical Indicators]]
- [[_COMMUNITY_Agent Schemas|Agent Schemas]]
- [[_COMMUNITY_Research Debate|Research Debate]]
- [[_COMMUNITY_Execution Costs|Execution Costs]]
- [[_COMMUNITY_Slippage Models|Slippage Models]]
- [[_COMMUNITY_Portfolio Management|Portfolio Management]]
- [[_COMMUNITY_Research Data|Research Data]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 89|Community 89]]

## God Nodes (most connected - your core abstractions)
1. `InstrumentRepository` - 68 edges
2. `CandleRepository` - 65 edges
3. `ExecutionRepository` - 58 edges
4. `RiskRepository` - 55 edges
5. `IntelligenceRepository` - 53 edges
6. `ResearchRepository` - 51 edges
7. `FundamentalsRepository` - 50 edges
8. `AnalystReportRepository` - 48 edges
9. `BacktestRepository` - 44 edges
10. `Settings` - 43 edges

## Surprising Connections (you probably didn't know these)
- `list_instruments()` --calls--> `InstrumentRepository`  [INFERRED]
  apps/api/routes_data.py → packages/taurus_core/db/repositories.py
- `get_instrument()` --calls--> `InstrumentRepository`  [INFERRED]
  apps/api/routes_data.py → packages/taurus_core/db/repositories.py
- `list_agent_reports()` --calls--> `AnalystReportRepository`  [INFERRED]
  apps/api/routes_intelligence.py → packages/taurus_core/db/repositories.py
- `list_fundamentals()` --calls--> `FundamentalsRepository`  [INFERRED]
  apps/api/routes_fundamentals.py → packages/taurus_core/db/repositories.py
- `list_fundamental_imports()` --calls--> `FundamentalsRepository`  [INFERRED]
  apps/api/routes_fundamentals.py → packages/taurus_core/db/repositories.py

## Communities (86 total, 19 thin omitted)

### Community 0 - "Trading Strategies"
Cohesion: 0.15
Nodes (12): MockMarketDataProvider, _money(), _stable_seed(), _trading_days(), run_import(), run_seed(), seed_mock_data(), SeedSummary (+4 more)

### Community 1 - "API Endpoints"
Cohesion: 0.07
Nodes (28): NeutralRiskAgent, PortfolioManagerAgent, RiskyRiskAgent, SafeRiskAgent, bound_trace_context(), RiskEngine, RiskEngineResult, RiskReviewService (+20 more)

### Community 2 - "Data Models"
Cohesion: 0.16
Nodes (15): create_app(), BaseSettings, configure_runtime_metrics(), Settings, configure_logging(), get_logger(), test_database_url_password_is_redacted(), test_default_settings_are_safe() (+7 more)

### Community 3 - "LLM Integration"
Cohesion: 0.07
Nodes (23): ABC, BrokerAdapter, BrokerAdapter, _AccountState, _as_utc(), _money(), PaperBroker, _PositionState (+15 more)

### Community 4 - "Backtesting Engine"
Cohesion: 0.05
Nodes (30): BearResearcherAgent, _clamp(), _clamp_unit(), BullResearcherAgent, _clamp(), _clamp_unit(), _clamp(), _clamp_unit() (+22 more)

### Community 5 - "Risk Management"
Cohesion: 0.20
Nodes (35): DashboardDataError, Raised when dashboard data cannot be loaded., AnalystReportModel, BacktestEquityPointModel, BacktestRunModel, Base, CompanyEventModel, DailyCandleModel (+27 more)

### Community 6 - "Dashboard Components"
Cohesion: 0.12
Nodes (39): _as_utc_datetime(), data_freshness(), _display_time(), _join_items(), latest_backtest_run_id(), latest_paper_account(), list_analyst_reports(), list_backtest_equity() (+31 more)

### Community 7 - "Database Models"
Cohesion: 0.07
Nodes (19): BaseAnalystAgent, fallback_output(), _provider_label(), _report_decimal(), _component_summary(), FundamentalsAnalystAgent, _join_metric_names(), NewsAnalystAgent (+11 more)

### Community 8 - "Agent Architecture"
Cohesion: 0.08
Nodes (11): get_debate(), list_debates(), list_trader_proposals(), _analyst_report_to_model(), _debate_report_to_model(), _delete_paper_artifacts_for_run_symbol(), _final_decision_to_model(), _raw_document_to_model() (+3 more)

### Community 9 - "Observability"
Cohesion: 0.10
Nodes (11): LLMProvider, LLMProviderError, parse_llm_output(), LMStudioProvider, _openai_compatible_completion(), OpenAI-compatible local provider used only for optional smoke checks., OpenAIProvider, Optional OpenAI-compatible provider; mock remains the default path. (+3 more)

### Community 10 - "Brokers"
Cohesion: 0.06
Nodes (30): TechnicalAnalystAgent, _add_latest(), FeatureSnapshot, from_strategy_parameters(), _snapshot_id(), TechnicalFeatureService, average_true_range(), daily_returns() (+22 more)

### Community 11 - "Features & Indicators"
Cohesion: 0.19
Nodes (16): BacktestResult, BacktestEngine, _feature_model(), _fill_model(), _json_safe(), _money(), _order_model(), PositionState (+8 more)

### Community 12 - "Research Tools"
Cohesion: 0.05
Nodes (43): code:text (docs/TAURUS_MVP_SPEC_v0_3.md), code:text (You are implementing Project Taurus. Start with Milestone M7), code:text (You are implementing Project Taurus. Start with Milestone M8), code:text (You are implementing Project Taurus. Start with Milestone M9), code:text (You are implementing Project Taurus. Start with Milestone M1), code:text (You are implementing Project Taurus. Start with Milestone M1), code:text (You are implementing Project Taurus. Start with Milestone M1), code:text (You are implementing Project Taurus. Start with Milestone M1) (+35 more)

### Community 13 - "Execution Engine"
Cohesion: 0.09
Nodes (22): annotations, list, editable, fiscalYearStartMonth, graphTooltip, id, links, panels (+14 more)

### Community 14 - "Configuration"
Cohesion: 0.09
Nodes (22): annotations, list, editable, fiscalYearStartMonth, graphTooltip, id, links, panels (+14 more)

### Community 15 - "Core Services"
Cohesion: 0.11
Nodes (18): CandleResponse, get_instrument(), InstrumentResponse, list_instruments(), FundamentalImportResponse, FundamentalScoreResponse, list_fundamental_imports(), list_fundamentals() (+10 more)

### Community 16 - "Market Data"
Cohesion: 0.08
Nodes (23): MarketDataProvider, MarketDataProviderError, Raised when a market data provider cannot serve the requested data., _build_column_mapping(), CSVColumnMapping, CSVMarketDataProvider, DisabledExternalMarketDataProvider, _normalize_column() (+15 more)

### Community 17 - "Intelligence"
Cohesion: 0.21
Nodes (11): ExecutionRouter, Routes only approved final paper decisions to the PaperBroker., run_mock_final_approval(), run_mock_paper_once(), _build_trader_proposal(), _latest_final_decision(), _settings_for_temp_db(), test_event_risk_blocked_final_decision_does_not_create_paper_order() (+3 more)

### Community 18 - "Prometheus Metrics"
Cohesion: 0.23
Nodes (15): metrics(), _as_utc_datetime(), _clear_database_gauges(), metrics_response_body(), metrics_response_type(), _refresh_agent_metrics(), _refresh_data_freshness(), refresh_database_metrics() (+7 more)

### Community 19 - "Grafana Dashboards"
Cohesion: 0.18
Nodes (10): get_paper_account(), list_paper_fills(), list_paper_orders(), list_paper_positions(), AuditLogModel, ExecutionRepository, _paper_account_to_model(), _paper_fill_to_model() (+2 more)

### Community 20 - "Testing Framework"
Cohesion: 0.23
Nodes (5): list_candles(), _base_select(), _candle_available_time(), _candle_to_model(), CandleRepository

### Community 21 - "Scripts & Utilities"
Cohesion: 0.10
Nodes (21): document_checksum(), NewsEvent, RawDocument, stable_id(), _aliases(), EntityResolver, _normalize(), ResolvedEntity (+13 more)

### Community 22 - "Documentation"
Cohesion: 0.15
Nodes (10): build_llm_provider(), LLM provider abstraction for schema-validated Taurus agent output., _prepare_mock_inputs(), run_mock_research_debate(), run_mock_risk_review(), _prepare_mock_inputs(), run_mock_trader_proposal(), enforce_trading_safety() (+2 more)

### Community 23 - "Agent Workflows"
Cohesion: 0.06
Nodes (34): 1. Purpose, 2. Locked project decisions, 3.1 Paper concept to Taurus implementation map, 3.2 Key adaptation for safety, 3. TradingAgents methodology adopted in Taurus, 4.1 Analyst team, 4.2 Bull/Bear researcher debate, 4.3 Trader proposal (+26 more)

### Community 25 - "Order Management"
Cohesion: 1.00
Nodes (3): calculate_backtest_metrics(), _mean(), _sample_std()

### Community 55 - "Community 55"
Cohesion: 0.07
Nodes (32): API Smoke Checks, code:bash (make setup), code:bash (make setup), code:bash (make migrate), code:bash (curl http://localhost:8000/health), code:text (.codex/rules/default.rules), code:toml ([projects."/Users/adnaan/Workbench/TaurusAgent"]), code:text (prefix_rule(pattern=["make", "test"], decision="allow")) (+24 more)

### Community 56 - "Community 56"
Cohesion: 0.13
Nodes (28): _average(), _eps_score(), FundamentalScoreComponents, _inverse_scale(), _price_to_book_score(), _quantize(), _scale(), score_fundamentals() (+20 more)

### Community 57 - "Community 57"
Cohesion: 0.20
Nodes (14): _provider_label(), run_analyst_suite(), MockLLMProvider, record_agent_run(), FailingLLMProvider, _prepare_intelligence_db(), _settings_for_temp_db(), test_analyst_suite_falls_back_when_llm_provider_fails() (+6 more)

### Community 58 - "Community 58"
Cohesion: 0.10
Nodes (20): M0 - Project Foundation, M10 - Real Market Data Provider, M11 - Continuous Paper Trading, M12 - Telegram Alerts, Replay, Backup, Hardening, M13 - Broker Sandbox Adapter, M14 - Live-Readiness Gate, M15 - Taurus MVP Release, M1 - Mock Data And Database Foundation (+12 more)

### Community 59 - "Community 59"
Cohesion: 0.15
Nodes (3): _event_to_model(), _instrument_to_model(), _sentiment_to_model()

### Community 60 - "Community 60"
Cohesion: 0.15
Nodes (12): code:bash (TAURUS_MODE=paper), code:bash (make setup), code:bash (make test), code:bash (make dev-up), code:bash (make migrate), code:bash (curl http://localhost:8000/health), code:bash (make dev-down), code:bash (make api) (+4 more)

### Community 61 - "Community 61"
Cohesion: 0.18
Nodes (10): Agent-Specific Instructions, Build, Test, and Development Commands, code:bash (curl http://localhost:8000/health), Coding Style & Naming Conventions, Commit & Pull Request Guidelines, graphify, Project Structure & Module Organization, Repository Guidelines (+2 more)

### Community 62 - "Community 62"
Cohesion: 0.14
Nodes (21): BacktestConfig, read_dashboard_data(), import_market_data(), MarketDataImportSummary, build_session_factory(), create_engine_from_url(), create_session_factory(), session_scope() (+13 more)

### Community 63 - "Community 63"
Cohesion: 0.18
Nodes (11): Acceptance criteria, Code changes, code:text (packages/taurus_core/intelligence/documents.py), code:text (Sample news/events CSV or JSON), code:text (make import-mock-news), code:text (TAURUS_LLM_PROVIDER=lmstudio TAURUS_LLM_BASE_URL=http://loca), How to build, Information required from user (+3 more)

### Community 64 - "Community 64"
Cohesion: 0.21
Nodes (6): get_final_decision(), get_risk_review(), list_final_decisions(), list_risk_reviews(), RiskRepository, Instrument

### Community 65 - "Community 65"
Cohesion: 0.20
Nodes (10): Acceptance criteria, Code changes, code:text (apps/dashboard/main.py), code:text (make dev-up), code:text (http://localhost:8501), How to build, Information required from user, M8 - Dashboard and observability v1 (+2 more)

### Community 66 - "Community 66"
Cohesion: 0.22
Nodes (9): 10. Definition of done for every milestone, 11. First Codex instruction, 12. Important implementation rule, Acceptance criteria, code:text (make setup), code:text (You are implementing Project Taurus, an observable, paper-tr), Final verification checklist, M15 - Taurus MVP release (+1 more)

### Community 67 - "Community 67"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (README.md), code:text (make setup), How to build, Information required from user, M0 - Project foundation, Objective (+1 more)

### Community 68 - "Community 68"
Cohesion: 0.22
Nodes (8): Acceptance criteria, Acceptance criteria, code:text (CSV historical price files), Information required from user, M10 - Real market data provider, M14 - Live-readiness gate, Objective, Objective

### Community 69 - "Community 69"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (packages/taurus_core/domain/instruments.py), code:text (make dev-up), How to build, Information required from user, M1 - Mock data and database foundation, Objective (+1 more)

### Community 70 - "Community 70"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (packages/taurus_core/backtesting/engine.py), code:text (make backtest-mock), How to build, Information required from user, M2 - Backtesting skeleton, Objective (+1 more)

### Community 71 - "Community 71"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (packages/taurus_core/features/technical.py), code:text (make test), How to build, Information required from user, M3 - Strategy engine and technical indicators, Objective (+1 more)

### Community 72 - "Community 72"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (packages/taurus_core/agents/bull_researcher.py), code:text (make run-analysts-mock SYMBOL=INFY), How to build, Information required from user, M5 - Bull/Bear research debate and trader proposal, Objective (+1 more)

### Community 73 - "Community 73"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (packages/taurus_core/agents/risky_risk_agent.py), code:text (make risk-review-mock SYMBOL=INFY), How to build, Information required from user, M6 - Risk committee, deterministic risk engine, and fund manager approval, Objective (+1 more)

### Community 74 - "Community 74"
Cohesion: 0.22
Nodes (9): Acceptance criteria, Code changes, code:text (packages/taurus_core/brokers/base.py), code:text (make paper-once-mock SYMBOL=INFY), How to build, Information required from user, M7 - PaperBroker execution simulator, Objective (+1 more)

### Community 75 - "Community 75"
Cohesion: 0.25
Nodes (8): Acceptance criteria, code:text (Symbol), code:text (make import-screener CSV=/path/to/screener.csv), How to build, Information required from user, M9 - Screener fundamentals import, Objective, Verification

### Community 76 - "Community 76"
Cohesion: 0.20
Nodes (11): MockNewsProvider, Deterministic in-memory news source for mock-mode Taurus runs., import_mock_news(), MockNewsImportSummary, run_import(), run_mock_analysts(), _settings_for_temp_db(), test_entity_resolver_maps_company_names_symbols_and_text() (+3 more)

### Community 77 - "Community 77"
Cohesion: 0.29
Nodes (7): Acceptance criteria, code:text (UPSTOX_CLIENT_ID), code:text (OpenAlgo endpoint), Information required from user, M13 - Broker sandbox adapter, Objective, Recommended first target

### Community 78 - "Community 78"
Cohesion: 0.40
Nodes (5): Acceptance criteria, code:text (Paper trading schedule), Information required from user, M11 - Continuous paper trading, Objective

### Community 79 - "Community 79"
Cohesion: 0.40
Nodes (5): Acceptance criteria, code:text (TELEGRAM_BOT_TOKEN), Information required from user, M12 - Telegram alerts, replay, backup, and hardening, Objective

### Community 89 - "Community 89"
Cohesion: 0.80
Nodes (4): _prepare_trader_db(), _settings_for_temp_db(), test_research_api_returns_trader_proposals(), test_trader_proposal_is_structured_deterministic_and_not_an_order()

## Knowledge Gaps
- **217 isolated node(s):** `code:bash (make setup)`, `code:bash (make setup)`, `code:bash (make dev-up)`, `code:bash (make test)`, `code:bash (make test)` (+212 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `InstrumentRepository` connect `Risk Management` to `Trading Strategies`, `Community 64`, `API Endpoints`, `Backtesting Engine`, `Database Models`, `Agent Architecture`, `Features & Indicators`, `Community 76`, `Core Services`, `Grafana Dashboards`, `Testing Framework`, `Scripts & Utilities`, `Community 56`, `Community 57`, `Community 59`, `Community 62`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `DailyCandle` connect `Features & Indicators` to `Trading Strategies`, `Community 64`, `Risk Management`, `Agent Architecture`, `Brokers`, `Market Data`, `Grafana Dashboards`, `Testing Framework`, `Paper Trading`, `Community 62`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `Settings` connect `Data Models` to `Community 89`, `API Endpoints`, `Trading Strategies`, `LLM Integration`, `Risk Management`, `Dashboard Components`, `Community 76`, `Core Services`, `Intelligence`, `Documentation`, `Community 56`, `Community 57`, `Community 62`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 62 inferred relationships involving `InstrumentRepository` (e.g. with `InstrumentResponse` and `CandleResponse`) actually correct?**
  _`InstrumentRepository` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 57 inferred relationships involving `CandleRepository` (e.g. with `InstrumentResponse` and `CandleResponse`) actually correct?**
  _`CandleRepository` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `ExecutionRepository` (e.g. with `AnalystReportModel` and `AuditLogModel`) actually correct?**
  _`ExecutionRepository` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 45 inferred relationships involving `RiskRepository` (e.g. with `AnalystReportModel` and `AuditLogModel`) actually correct?**
  _`RiskRepository` has 45 INFERRED edges - model-reasoned connections that need verification._