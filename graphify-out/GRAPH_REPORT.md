# Graph Report - .  (2026-05-19)

## Corpus Check
- Corpus is ~49,209 words - fits in a single context window. You may not need a graph.

## Summary
- 809 nodes · 2017 edges · 55 communities (41 shown, 14 thin omitted)
- Extraction: 55% EXTRACTED · 45% INFERRED · 0% AMBIGUOUS · INFERRED: 910 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `InstrumentRepository` - 59 edges
2. `CandleRepository` - 59 edges
3. `ExecutionRepository` - 55 edges
4. `RiskRepository` - 52 edges
5. `IntelligenceRepository` - 50 edges
6. `ResearchRepository` - 48 edges
7. `AnalystReportRepository` - 45 edges
8. `BacktestRepository` - 40 edges
9. `Settings` - 39 edges
10. `BacktestEngine` - 32 edges

## Surprising Connections (you probably didn't know these)
- `test_mock_llm_provider_returns_schema_valid_output()` --calls--> `MockLLMProvider`  [INFERRED]
  tests/unit/test_llm_provider.py → packages/taurus_core/llm/mock_provider.py
- `list_instruments()` --calls--> `InstrumentRepository`  [INFERRED]
  apps/api/routes_data.py → packages/taurus_core/db/repositories.py
- `get_instrument()` --calls--> `InstrumentRepository`  [INFERRED]
  apps/api/routes_data.py → packages/taurus_core/db/repositories.py
- `list_agent_reports()` --calls--> `AnalystReportRepository`  [INFERRED]
  apps/api/routes_intelligence.py → packages/taurus_core/db/repositories.py
- `list_debates()` --calls--> `ResearchRepository`  [INFERRED]
  apps/api/routes_research.py → packages/taurus_core/db/repositories.py

## Communities (55 total, 14 thin omitted)

### Community 0 - "Trading Strategies"
Cohesion: 0.07
Nodes (51): read_dashboard_data(), build_session_factory(), create_engine_from_url(), create_session_factory(), session_scope(), _clamp(), _decay_factor(), _decimal_metadata() (+43 more)

### Community 1 - "API Endpoints"
Cohesion: 0.06
Nodes (33): NeutralRiskAgent, PortfolioManagerAgent, RiskyRiskAgent, SafeRiskAgent, document_checksum(), stable_id(), _document_from_spec(), MockNewsSpec (+25 more)

### Community 2 - "Data Models"
Cohesion: 0.06
Nodes (32): _provider_label(), run_analyst_suite(), TraderAgent, create_app(), BaseSettings, MockLLMProvider, configure_runtime_metrics(), record_agent_run() (+24 more)

### Community 3 - "LLM Integration"
Cohesion: 0.07
Nodes (23): ABC, BrokerAdapter, BrokerAdapter, _AccountState, _as_utc(), _money(), PaperBroker, _PositionState (+15 more)

### Community 4 - "Backtesting Engine"
Cohesion: 0.08
Nodes (22): BearResearcherAgent, _clamp(), _clamp_unit(), BullResearcherAgent, _clamp(), _clamp_unit(), _clamp(), _clamp_unit() (+14 more)

### Community 5 - "Risk Management"
Cohesion: 0.19
Nodes (33): list_candles(), DashboardDataError, Raised when dashboard data cannot be loaded., AnalystReportModel, BacktestEquityPointModel, BacktestRunModel, Base, CompanyEventModel (+25 more)

### Community 6 - "Dashboard Components"
Cohesion: 0.12
Nodes (36): _as_utc_datetime(), data_freshness(), _display_time(), _join_items(), latest_backtest_run_id(), latest_paper_account(), list_analyst_reports(), list_backtest_equity() (+28 more)

### Community 7 - "Database Models"
Cohesion: 0.07
Nodes (15): BaseAnalystAgent, fallback_output(), _provider_label(), _report_decimal(), FundamentalsAnalystAgent, NewsAnalystAgent, analyst_report_id(), AnalystReport (+7 more)

### Community 8 - "Agent Architecture"
Cohesion: 0.07
Nodes (13): _analyst_report_to_model(), _base_select(), _debate_report_to_model(), _delete_paper_artifacts_for_run_symbol(), _event_to_model(), _final_decision_to_model(), _instrument_to_model(), _paper_account_to_model() (+5 more)

### Community 9 - "Observability"
Cohesion: 0.07
Nodes (16): MarketDataProvider, DocumentProvider, NewsProvider, LLMProvider, LLMProviderError, parse_llm_output(), LMStudioProvider, _openai_compatible_completion() (+8 more)

### Community 10 - "Brokers"
Cohesion: 0.13
Nodes (22): TechnicalAnalystAgent, _add_latest(), FeatureSnapshot, from_strategy_parameters(), _snapshot_id(), TechnicalFeatureService, average_true_range(), daily_returns() (+14 more)

### Community 11 - "Features & Indicators"
Cohesion: 0.17
Nodes (16): BacktestConfig, BacktestResult, BacktestEngine, _feature_model(), _fill_model(), _json_safe(), _money(), _order_model() (+8 more)

### Community 12 - "Research Tools"
Cohesion: 0.12
Nodes (7): decimal_param(), int_param(), SignalExplanation, StrategySignal, BlendedScoreStrategy, build_strategy(), MovingAverageCrossoverStrategy

### Community 13 - "Execution Engine"
Cohesion: 0.09
Nodes (22): annotations, list, editable, fiscalYearStartMonth, graphTooltip, id, links, panels (+14 more)

### Community 14 - "Configuration"
Cohesion: 0.09
Nodes (22): annotations, list, editable, fiscalYearStartMonth, graphTooltip, id, links, panels (+14 more)

### Community 15 - "Core Services"
Cohesion: 0.15
Nodes (14): CandleResponse, get_instrument(), InstrumentResponse, list_instruments(), health(), HealthResponse, ReadinessResponse, ready() (+6 more)

### Community 16 - "Market Data"
Cohesion: 0.14
Nodes (6): get_final_decision(), get_risk_review(), list_final_decisions(), list_risk_reviews(), RiskRepository, _sentiment_to_model()

### Community 17 - "Intelligence"
Cohesion: 0.21
Nodes (11): ExecutionRouter, Routes only approved final paper decisions to the PaperBroker., run_mock_final_approval(), _build_trader_proposal(), _insert_severe_negative_event(), _latest_final_decision(), _settings_for_temp_db(), test_event_risk_blocked_final_decision_does_not_create_paper_order() (+3 more)

### Community 18 - "Prometheus Metrics"
Cohesion: 0.23
Nodes (15): metrics(), _as_utc_datetime(), _clear_database_gauges(), metrics_response_body(), metrics_response_type(), _refresh_agent_metrics(), _refresh_data_freshness(), refresh_database_metrics() (+7 more)

### Community 19 - "Grafana Dashboards"
Cohesion: 0.23
Nodes (7): get_paper_account(), list_paper_fills(), list_paper_orders(), list_paper_positions(), AuditLogModel, ExecutionRepository, _paper_order_to_model()

### Community 20 - "Testing Framework"
Cohesion: 0.24
Nodes (7): _candle_to_model(), CandleRepository, Instrument, DailyCandle, _increasing_candles(), test_backtest_engine_aligns_candles_by_common_trade_date(), test_feature_snapshots_are_persisted_without_lookahead()

### Community 21 - "Scripts & Utilities"
Cohesion: 0.47
Nodes (4): _aliases(), EntityResolver, _normalize(), ResolvedEntity

### Community 22 - "Documentation"
Cohesion: 0.40
Nodes (3): get_debate(), list_debates(), list_trader_proposals()

### Community 23 - "Agent Workflows"
Cohesion: 0.70
Nodes (4): load_strategy_config(), _positive_int(), _required_str(), StrategyConfig

### Community 25 - "Order Management"
Cohesion: 1.00
Nodes (3): calculate_backtest_metrics(), _mean(), _sample_std()

## Knowledge Gaps
- **41 isolated node(s):** `list`, `editable`, `fiscalYearStartMonth`, `graphTooltip`, `id` (+36 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DailyCandle` connect `Testing Framework` to `Trading Strategies`, `Risk Management`, `Observability`, `Brokers`, `Features & Indicators`, `Market Data`, `Grafana Dashboards`, `Paper Trading`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Why does `Settings` connect `Data Models` to `Trading Strategies`, `API Endpoints`, `LLM Integration`, `Risk Management`, `Dashboard Components`, `Core Services`, `Intelligence`, `Testing Framework`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `InstrumentRepository` connect `Risk Management` to `Trading Strategies`, `API Endpoints`, `Data Models`, `Backtesting Engine`, `Database Models`, `Agent Architecture`, `Features & Indicators`, `Core Services`, `Market Data`, `Grafana Dashboards`, `Testing Framework`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Are the 53 inferred relationships involving `InstrumentRepository` (e.g. with `SeedSummary` and `MockNewsImportSummary`) actually correct?**
  _`InstrumentRepository` has 53 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `CandleRepository` (e.g. with `SeedSummary` and `_PositionState`) actually correct?**
  _`CandleRepository` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `ExecutionRepository` (e.g. with `_PositionState` and `_AccountState`) actually correct?**
  _`ExecutionRepository` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 42 inferred relationships involving `RiskRepository` (e.g. with `PortfolioManagerAgent` and `ExecutionRouter`) actually correct?**
  _`RiskRepository` has 42 INFERRED edges - model-reasoned connections that need verification._