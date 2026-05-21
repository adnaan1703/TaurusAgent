# Taurus UI Design Brief

Audience: UI/UX designer building the next Taurus dashboard.

Taurus is an observable, paper-trading-first agent system for Indian cash equities. It runs an end-of-day workflow for one or more stocks, generates research and risk artifacts, decides whether a paper trade is allowed, simulates execution through an internal PaperBroker, and stores the full trail for inspection.

The dashboard should make one thing easy: select a run, select a stock, and understand exactly what happened, why it happened, and what changed in the paper account.

## Product Summary

Taurus is not a live trading terminal in the current MVP. It is a decision-observability product for a local paper trading agent.

The product answers:

- Did the paper run start, complete, partially fail, or fail?
- Which stocks were processed in that run?
- For each stock, what did each analyst agent conclude?
- What did the bull/bear debate resolve?
- What trade did the trader agent propose?
- Which risk rules passed, reduced, rejected, or blocked the idea?
- What was the final portfolio-manager decision?
- Was a paper order created?
- If yes, how was it filled, what did it cost, and how did account/positions change?
- Can I replay the decision trail later without rerunning agents?

The system is intentionally safety-first:

- `LIVE_TRADING_ENABLED=false` by default.
- `BROKER_PROVIDER=paper` by default.
- Trader proposals and risk reviews are not broker orders.
- Only final decisions with `APPROVED_FOR_PAPER` can be routed.
- The current execution adapter is the simulated `PaperBroker`.

## Primary UX Object

Design the dashboard around this primary object:

```text
Paper Run -> Stock -> Decision Trail -> Paper Execution
```

The strongest detail-page key is:

```text
run_id + symbol
```

Most artifacts are linked by `run_id` and `symbol`. Later artifacts add more precise IDs:

```text
report_id -> debate_id -> proposal_id -> risk_check_id -> final_decision_id -> order_id -> fill_id
```

A single run can process many symbols. One symbol in that run can succeed while another fails, so the UI should support run-level status and per-symbol status separately.

## End-To-End Flow

One paper loop is an end-of-day batch workflow. It uses the latest available daily candles and local inputs, then stores outputs for observation.

1. Run starts
   - A `paper_runs` row is created with status `RUNNING`.
   - The run has a `run_id`, `schedule_name`, `started_at`, `symbols`, timezone, and after-market-close flag.

2. Inputs are refreshed
   - Migrations run so tables exist.
   - Market data is loaded from the configured provider.
   - Mock news/events are imported in the current MVP.
   - The run stores a `market_data_summary`.

3. Strategy context is generated
   - Technical snapshots are computed from daily candles.
   - Strategy targets and signals are summarized into `paper_runs.artifacts.strategy`.
   - In backtests, feature values, signals, orders, fills, positions, and equity points are persisted in dedicated backtest tables.

4. Per-stock analyst reports are created
   - Technical, news, sentiment, and fundamentals agents generate `analyst_reports`.
   - Each report includes score, confidence, stance, horizon, key points, risks, source IDs, and model version.

5. Bull/bear debate runs
   - A `debate_reports` row is created.
   - It includes bull thesis, bear thesis, debate rounds, consensus label, consensus score, manager summary, unresolved uncertainties, and source report IDs.

6. Trader proposal is created
   - A `trader_proposals` row is created.
   - It includes action, confidence, requested position percent of NAV, order type, entry rule, stop loss, take profit, reason summary, invalidation rules, and whether risk approval is required.

7. Risk review runs
   - A `risk_reviews` row is created.
   - It includes deterministic hard rules and persona reviews.
   - It can approve, reduce, reject, or block the proposal.
   - Important output fields are `status`, `approved_position_pct_nav`, `is_order`, and `can_send_to_broker`.

8. Final decision is created
   - A `final_decisions` row is created.
   - It includes final action, final status, approved quantity, approved position percent, reason, and broker-routing flags.
   - Only `APPROVED_FOR_PAPER` can proceed to paper execution.

9. PaperBroker execution is simulated
   - If approved, `paper_orders` and `paper_fills` are stored.
   - Paper account and positions are updated.
   - If rejected by the PaperBroker, a rejected paper order is still stored with a rejection reason.

10. Run completes
    - `paper_runs` is updated to `COMPLETED`, `PARTIAL_FAILED`, or `FAILED`.
    - Per-symbol artifact IDs are stored under `paper_runs.artifacts.symbols`.
    - Audit rows capture key lifecycle and execution events.

## Data Generated

Use this section as the designer's data dictionary.

| Area | Table/API Object | What It Represents | Important Fields |
|---|---|---|---|
| Run lifecycle | `paper_runs` | One scheduled or manual paper loop | `run_id`, `status`, `symbols`, `succeeded_symbols`, `failed_symbols`, `errors`, `market_data_summary`, `artifacts`, `started_at`, `completed_at` |
| Instruments | `instruments` | Tradable stock universe | `symbol`, `name`, `exchange`, `segment`, `currency`, `active` |
| Prices | `daily_candles` | OHLCV market data | `symbol`, `timeframe`, `trade_date`, `open`, `high`, `low`, `close`, `volume`, `source`, `data_available_time` |
| News source | `raw_documents` | Imported documents before event extraction | `document_id`, `source`, `title`, `published_at`, `symbols`, `entities` |
| Company events | `company_events` | Symbol-linked news/event item | `event_id`, `document_id`, `symbol`, `event_type`, `headline`, `summary`, `severity`, `horizon`, `source_confidence` |
| Sentiment | `sentiment_scores` | Scored event sentiment | `score_id`, `event_id`, `symbol`, `sentiment_score`, `event_score`, `decayed_score`, `confidence` |
| Fundamentals | `fundamental_imports` | Screener import batch | `import_id`, `source_filename`, `rows_imported`, `status`, `data_available_time` |
| Fundamentals | `fundamental_snapshots` | Raw imported metric values | `import_id`, `symbol`, `metric_name`, `metric_value`, `reporting_date`, `data_available_time` |
| Fundamentals | `fundamental_scores` | Normalized fundamental score | `score_id`, `import_id`, `symbol`, `quality_score`, `valuation_score`, `leverage_risk_score`, `ownership_score`, `composite_score` |
| Agent reports | `analyst_reports` | Individual analyst opinions | `report_id`, `run_id`, `symbol`, `agent_name`, `score`, `confidence`, `stance`, `key_points`, `risks`, `source_ids` |
| Debate | `debate_reports` | Bull/bear synthesis | `debate_id`, `run_id`, `symbol`, `consensus_label`, `consensus_score`, `bull_thesis`, `bear_thesis`, `rounds`, `manager_summary` |
| Trade proposal | `trader_proposals` | Proposed trading action | `proposal_id`, `run_id`, `symbol`, `debate_id`, `action`, `requested_position_pct_nav`, `stop_loss_pct`, `take_profit_pct`, `invalid_if` |
| Risk gate | `risk_reviews` | Approval/reduction/rejection layer | `risk_check_id`, `decision_id`, `proposal_id`, `status`, `hard_rule_results`, `persona_reviews`, `approved_position_pct_nav`, `can_send_to_broker` |
| Final decision | `final_decisions` | Portfolio manager decision | `final_decision_id`, `decision_id`, `risk_check_id`, `final_action`, `status`, `approved_quantity`, `reason`, `can_send_to_broker` |
| Paper order | `paper_orders` | Simulated broker order | `order_id`, `final_decision_id`, `decision_id`, `run_id`, `symbol`, `side`, `quantity`, `status`, `filled_quantity`, `average_fill_price_inr`, `total_cost_inr`, `total_slippage_inr`, `slippage_bps` |
| Paper fill | `paper_fills` | Simulated fill record | `fill_id`, `order_id`, `symbol`, `quantity`, `reference_price_inr`, `fill_price_inr`, `cost_inr`, `slippage_bps`, `filled_at` |
| Position | `paper_positions` | Paper holding after execution | `run_id`, `symbol`, `quantity`, `average_cost_inr`, `last_price_inr`, `market_value_inr`, `unrealized_pnl_inr` |
| Account | `paper_accounts` | Paper portfolio state | `account_id`, `run_id`, `available_cash_inr`, `gross_exposure_inr`, `equity_inr`, `realized_pnl_inr`, `unrealized_pnl_inr` |
| Audit | `audit_log` | Lifecycle and execution events | `event_type`, `actor`, `payload`, `note`, `created_at` |

## How The Data Is Linked

The designer should think of the data as a traceable chain.

```text
paper_runs.run_id
  -> analyst_reports.run_id + symbol
  -> debate_reports.run_id + symbol
  -> trader_proposals.run_id + symbol + debate_id
  -> risk_reviews.run_id + symbol + proposal_id + decision_id
  -> final_decisions.run_id + symbol + risk_check_id + decision_id
  -> paper_orders.final_decision_id + decision_id
  -> paper_fills.order_id
  -> paper_positions.run_id + symbol
  -> paper_accounts.run_id
```

Source evidence is linked separately:

```text
raw_documents.document_id
  -> company_events.document_id
  -> sentiment_scores.event_id
  -> analyst_reports.source_ids
  -> debate_reports.source_report_ids
  -> trader_proposals.source_report_ids
  -> risk_reviews.source_report_ids
```

The `decision_id` is the best replay anchor. It appears in risk reviews, final decisions, paper orders, and analyst reports when available. The replay endpoint reconstructs a staged trail from stored artifacts; it does not rerun agents.

## Recommended Dashboard Information Architecture

### 1. Run Overview

Purpose: answer "What happened in the latest runs?"

Recommended components:

- Run list with `run_id`, status, start time, completion time, symbols, succeeded count, failed count, error count.
- Status summary cards: latest run status, latest paper equity, latest final decision, latest order status.
- Per-run expandable symbol list.
- Clear visual distinction between `COMPLETED`, `PARTIAL_FAILED`, `FAILED`, and `RUNNING`.

Primary action: open Run Detail.

### 2. Run Detail

Purpose: answer "What happened inside this run?"

Recommended layout:

- Header: run status, duration, schedule, timezone, symbols processed.
- Symbol status table: symbol, pipeline status, final decision, order status, last artifact timestamp.
- Market data summary: provider, imported candles, latest data available time.
- Strategy summary: strategy name, selected targets, generated signals.
- Error panel for failed symbols.

Primary action: select a stock to open Stock Decision Detail.

### 3. Stock Decision Detail

Purpose: answer "For this stock, why did Taurus do what it did?"

This should be the main designer focus.

Recommended layout:

- Header: symbol, company name, run ID, final status, final action, approved quantity, can-send-to-broker flag.
- Horizontal timeline:
  - Inputs
  - Analyst reports
  - Debate
  - Trader proposal
  - Risk review
  - Final decision
  - Paper order
  - Paper fills
- Each timeline stage should show status, confidence/score where relevant, timestamp, and artifact ID.
- Detail panels below the timeline:
  - Price and freshness
  - Events and sentiment
  - Analyst report comparison
  - Debate summary
  - Proposal and sizing
  - Risk rules and reductions
  - Final decision reason
  - Execution and account impact

The UI should make missing artifacts obvious. Example: a stock may have analyst reports and a rejected final decision, but no paper order.

### 4. Decision Replay

Purpose: answer "Show me the complete evidence chain for this decision."

Recommended components:

- Search or deep link by `decision_id`.
- Stage accordion using replay stages:
  - `analyst_reports`
  - `company_events`
  - `debate_report`
  - `trader_proposal`
  - `risk_review`
  - `final_decision`
  - `paper_order`
  - `paper_fills`
  - `audit_log`
- Each stage should show artifact count, key fields, and raw JSON access for debugging.

### 5. Agent Workflow

Purpose: compare machine opinions before the trade proposal.

Recommended components:

- Agent report cards/table grouped by agent name.
- Score and confidence comparison.
- Stance badges: bullish, neutral, bearish.
- Key points and risks as scannable text.
- Source IDs available on demand.
- Debate panel showing bull thesis, bear thesis, manager summary, open uncertainties, and consensus score.

### 6. Risk And Controls

Purpose: prove that safety gates worked.

Recommended components:

- Risk review summary with requested vs approved position.
- Hard-rule results table with status colors:
  - `passed`
  - `reduced`
  - `rejected`
  - `blocked`
- Persona reviews with recommendation, score, confidence, key points, and required conditions.
- Final decision panel showing `APPROVED_FOR_PAPER`, `REJECTED`, or `BLOCKED`.
- Always show `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` somewhere in system status.

### 7. Paper Execution

Purpose: answer "What trade was simulated and what changed?"

Recommended components:

- Paper account summary: equity, cash, exposure, realized P&L, unrealized P&L.
- Orders table: side, quantity, status, fill quantity, average fill, cost, slippage.
- Fills table: fill price, reference price, quantity, costs, slippage bps, fill time.
- Positions table: quantity, average cost, last price, market value, unrealized P&L.
- Account impact panel comparing before/after if historical account snapshots become available.

### 8. Data Freshness And Inputs

Purpose: answer "Was the system acting on current enough data?"

Recommended components:

- Latest candle per symbol.
- Feature freshness where available.
- Fundamental data availability.
- News ingestion summary.
- Event list with severity, sentiment, decayed score, and source document.
- Warning treatment for stale or missing data.

## Status And Badge Language

Use direct labels. Avoid hiding operational states behind vague wording.

Run statuses:

- `RUNNING`: workflow is active.
- `COMPLETED`: all requested symbols succeeded.
- `PARTIAL_FAILED`: at least one symbol succeeded and at least one failed.
- `FAILED`: no requested symbol completed.

Risk review statuses:

- `APPROVED`: risk gate allowed the proposal.
- `APPROVED_WITH_REDUCTION`: risk gate reduced position size.
- `REJECTED`: risk gate rejected the proposal.
- `BLOCKED`: hard safety condition blocked the proposal.

Final decision statuses:

- `APPROVED_FOR_PAPER`: allowed to route to PaperBroker.
- `REJECTED`: not routed.
- `BLOCKED`: not routed due to safety condition.

Order statuses:

- `CREATED`, `ACCEPTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`.

## API Endpoints Useful For UI Design

Run lifecycle:

```text
GET /runs
GET /runs/{run_id}
```

Inputs:

```text
GET /data/instruments
GET /data/candles?symbol=INFY&timeframe=1d
GET /events?symbol=INFY
GET /fundamentals?symbol=INFY
GET /fundamentals/imports
```

Agent and research artifacts:

```text
GET /agent-reports?symbol=INFY
GET /debates?symbol=INFY
GET /debates/{debate_id}
GET /trader-proposals?symbol=INFY
```

Risk and decisions:

```text
GET /risk-checks?symbol=INFY
GET /risk-checks/{risk_check_id}
GET /final-decisions?symbol=INFY
GET /final-decisions/{final_decision_id}
```

Paper execution:

```text
GET /paper/orders?symbol=INFY
GET /paper/fills?symbol=INFY
GET /paper/positions?symbol=INFY
GET /paper/account
GET /paper/account?run_id=<run_id>
```

Replay:

```text
GET /replay/{decision_id}
```

## Current MVP Assumptions

- Taurus is paper-trading-first and local-first.
- Current market data can be deterministic mock data or imported CSV.
- Current news is mock news unless extended later.
- Current LLM output can be mock, LM Studio, or OpenAI depending on local settings, but mock is the default.
- Current broker is `PaperBroker`.
- The main schedule is `daily_after_close` in `Asia/Kolkata`.
- The system is not an intraday terminal.
- Freshness warnings may look old in mock mode because mock candles are historical fixtures.

## Design Priorities

The dashboard should prioritize observability over decoration.

Recommended priorities:

- Make the run and stock context persistent in the UI.
- Show the decision chain as a timeline, not only as separate tables.
- Surface status and blocking reasons before dense details.
- Show both scores and explanations.
- Make risk gates visually prominent.
- Treat paper execution as an outcome of a final decision, not as an independent order blotter.
- Include raw artifact access for debugging, but keep it secondary.
- Make missing or skipped stages explicit.
- Keep every artifact linkable by ID.

## Suggested First Screen

The first screen should not be a marketing landing page. It should be an operational dashboard:

- Left side: latest runs and status.
- Center: selected run timeline and symbol progress.
- Right side: latest account state, active warnings, and final decisions.
- Primary interaction: click a stock inside a run to open the full decision trail.

The product is successful when a user can answer, within a few clicks:

```text
For INFY in run pr-..., why did Taurus approve/reject/block the trade, and what exactly happened afterward?
```
