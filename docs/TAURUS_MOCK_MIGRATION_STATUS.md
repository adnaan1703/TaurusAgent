# Taurus Mock Migration Status

Last reviewed: 2026-06-04

This document tracks which Taurus components are still mocked or simulated, which
agents depend on them, and what remains to migrate toward a real-data paper
workflow. Taurus remains paper-trading-first: live trading is disabled and real
broker order routing is not part of the current roadmap.

## Current Effective Defaults

```text
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
TAURUS_MARKET_DATA_PROVIDER=kite
TAURUS_LLM_PROVIDER=lmstudio
TAURUS_ALERT_PROVIDER=mock
TAURUS_PAPER_PORTFOLIO_ID=local-paper
TAURUS_ENABLED_ANALYSTS=technical
TAURUS_GRAPH_ENABLED=false
TAURUS_GRAPH_RISK_ENABLED=false
TAURUS_NEO4J_ENABLED=false
```

The canonical `make paper-loop-kite` real-data profile now overrides the graph
defaults for that command only:

```text
TAURUS_ENABLED_ANALYSTS=technical,graph
TAURUS_GRAPH_ENABLED=true
TAURUS_GRAPH_RISK_ENABLED=true
STRATEGY=configs/strategies/graph_aware_score_v1.yaml
```

## Mocked Components

| Component | Current state | Has agent? | Requires LLM provider? | Migration required |
|---|---:|---:|---:|---|
| Trading mode | `paper` | No | No | None for paper MVP. Live trading remains intentionally blocked. |
| Broker | `paper` | No | No | Real broker order routing would require a new approved milestone. |
| Market data | `kite` | No | No | Runtime provider is Kite-only; legacy mock candles fail Kite preflight. |
| News data | Mock | Feeds `NewsAnalystAgent` / `SentimentAnalystAgent` | Yes, if those analysts are enabled | Add real news provider or explicit no-news mode. |
| LLM provider | `lmstudio` default; `openai`/`gemini` opt-in | Used by analyst agents | Yes | Keep LM Studio running locally or configure hosted API keys/models. |
| Alerts | `mock` | No | No | Use `telegram`; verify delivery with local credentials. |
| Fundamentals | Mock unless Screener CSV imported | `FundamentalsAnalystAgent` | Yes, if enabled | Import and validate real Screener CSV exports. |
| Graph analyst | Enabled for `make paper-loop-kite`; disabled by config default elsewhere | `GraphAnalystAgent` | No | Keep readiness checks and active-edge-only evidence for graph-enabled paper runs. |
| Graph risk | Enabled for `make paper-loop-kite`; disabled by config default elsewhere | No separate analyst | No | Keep graph concentration in deterministic `RiskEngine` BUY hard-rule results. |
| Neo4j | Disabled | No | No | Optional only; rebuild projection from Postgres if needed. |
| Paper fills/costs/slippage | Simulated | No | No | Replace placeholder bps/fill assumptions with broker-calibrated assumptions. |

## Analyst Roster

| Analyst key | Agent class | Enabled now? | Uses LLM provider? | Mock dependency risk |
|---|---|---:|---:|---|
| `technical` | `TechnicalAnalystAgent` | Yes | Yes | Uses candles/features/signals, then calls configured real LLM provider. |
| `news` | `NewsAnalystAgent` | No | Yes | Depends on stored news/events; currently mock news unless a real provider is added. |
| `sentiment` | `SentimentAnalystAgent` | No | Yes | Depends on stored sentiment from events; currently mock event source. |
| `fundamentals` | `FundamentalsAnalystAgent` | No | Yes | Uses real imported Screener scores when present; otherwise mock fallback. |
| `graph` | `GraphAnalystAgent` | Yes on `make paper-loop-kite`; no by config default | No | Deterministic graph rules; no LLM override; active edges only. |

Current enabled analyst roster:

```text
TAURUS_ENABLED_ANALYSTS=technical
```

This means only `TechnicalAnalystAgent` runs by default. It calls the configured
real LLM provider; runtime mock LLM support has been removed. Test-only fake LLM
providers may still be used inside unit tests.

## Non-Analyst Agents And Services

These are "agents" in code structure. Debate synthesis and trader proposals now
use the configured real LLM provider with deterministic guardrails; risk, final
approval, and paper execution remain rule-based consumers of stored artifacts.
Final approval may now call the configured real LLM provider only to explain the
already-fixed deterministic outcome.

| Workflow | Agents/services | Requires LLM provider? | Current mock exposure |
|---|---|---:|---|
| Debate | `BullResearcherAgent`, `BearResearcherAgent`, `ResearchManagerAgent` | Yes | Bull, bear, and manager synthesis use the configured real LLM provider with deterministic score/confidence guardrails. |
| Trader proposal | `TraderAgent` | Yes | Uses the configured real LLM provider for after-close lifecycle reasoning, then deterministic guardrails validate action, target exposure, and summaries. |
| Position monitor | `PositionMonitorService`, `TraderAgent`, `RiskReviewService`, `PortfolioManagerAgent`, `PaperBroker` | Yes for triggered TraderAgent/final explanations | Uses Kite quote snapshots only; tests may inject local fake quote clients. Runtime mock quote providers are not configured. |
| Risk review | `RiskyRiskAgent`, `NeutralRiskAgent`, `SafeRiskAgent`, `RiskEngine` | No | Can be influenced by mock news/events in the DB. |
| Final approval | `PortfolioManagerAgent` | Optional | Uses the configured real LLM provider only to enrich `FinalDecision.reason` and bounded model metadata after deterministic status/action/sizing/routing fields are fixed. |
| Paper execution | `ExecutionRouter`, `PaperBroker` | No | Simulated fills/costs/slippage only. |

## LLM Usage By Agent

| Component | Current implementation | Uses LLM today? | Proposed LLM provider requirement | Priority | Proposed LLM role |
|---|---|---:|---|---:|---|
| `TechnicalAnalystAgent` | Builds rule/context fallback, then calls `llm_provider.complete_analyst_report()` | Yes | Optional | Medium | Explain deterministic technical evidence; signal math should remain rule-based. |
| `NewsAnalystAgent` | Builds event context, then calls LLM provider | Yes | MUST when enabled for real-data runs | High | Classify, summarize, and reason over real unstructured news. |
| `SentimentAnalystAgent` | Builds sentiment context, then calls LLM provider | Yes | Optional | Medium | Explain event tone; numeric sentiment should remain model/rule-backed. |
| `FundamentalsAnalystAgent` | Builds fundamentals context, then calls LLM provider | Yes | MUST when enabled for real-data runs | High | Interpret Screener/financial metrics and surface business risks. |
| `GraphAnalystAgent` | Fully deterministic graph scoring | No | Optional | Low | Explain graph evidence; scoring should remain deterministic. |
| `BullResearcherAgent` | Builds an LLM-assisted bull thesis from analyst evidence with deterministic guardrails | Yes | MUST | High | Completed in M25; keep downstream trader/risk/final/PaperBroker safeguards authoritative. |
| `BearResearcherAgent` | Builds an LLM-assisted bear thesis from analyst evidence with deterministic guardrails | Yes | MUST | High | Completed in M26; challenge assumptions, surface downside, and identify invalidation risks without overriding downstream safeguards. |
| `ResearchManagerAgent` | Builds LLM-assisted debate synthesis from analyst evidence plus bull/bear theses with deterministic guardrails | Yes | MUST | High | Completed in M27; synthesize bull/bear debate into consensus, confidence, and unresolved uncertainties without overriding downstream safeguards. |
| `TraderAgent` | Builds position-aware lifecycle proposals with deterministic guardrails around advisory LLM output | Yes | MUST | High | Completed in M28; convert research consensus plus paper portfolio context into after-close BUY/HOLD/NO_TRADE/REDUCE/EXIT proposals. |
| `PositionMonitorService` | Polls open long paper positions against stop-loss/take-profit thresholds using persisted Kite quote snapshots | Yes for triggered TraderAgent/final explanation flow | MUST | High | Completed in M30; create auditable `market_hours` EXIT/REDUCE lifecycle proposals without broker-native stop-loss/OCO/live routing. |
| `RiskyRiskAgent` / `NeutralRiskAgent` / `SafeRiskAgent` | Risk persona rules | No | Optional | Medium | Provide advisory committee-style risk reasoning; hard risk rules remain authoritative. |
| `RiskEngine` | Hard risk rules | No | Never | N/A | Keep deterministic: kill switch, caps, stale data, severe event block, graph concentration gates. |
| `PortfolioManagerAgent` | Final approval rules plus optional LLM explanation | Optional | Optional | Low | Completed in M29; explain final approval/rejection/no-action while deterministic approval gates remain authoritative. |
| `ExecutionRouter` / `PaperBroker` | Order routing and paper execution | No | Never | N/A | Keep deterministic and auditable. |

Current distinction:

```text
Analyst, debate, trader proposal, and final explanation agents = can call LLM provider
Risk engine / execution agents = rule-based consumers of stored outputs
```

The selected functional-MVP sequence now tracks separate migrations for
LLM-backed debate, trader proposal, and final-decision explanation in
`docs/TAURUS_MILESTONE_TODO.md`. Risk persona LLM support remains deferred.

The minimum high-value LLM migration target is:

```text
BullResearcherAgent
BearResearcherAgent
ResearchManagerAgent
TraderAgent
PortfolioManagerAgent explanation
```

The advisory risk personas can be upgraded after that. `RiskEngine`,
`ExecutionRouter`, and `PaperBroker` should not use LLMs.

## Mock Migration Checklist

- [x] Complete the ordered functional-MVP sequence in
      `docs/TAURUS_MILESTONE_TODO.md`.
- [x] Switch market data defaults and runtime path from `mock` to `kite` for
      real-data paper runs.
- [x] Prevent mixed mock/Kite data in the same database, or make provider-scoped
      universe handling explicit.
- [ ] Remove unconditional `MockNewsProvider` import from paper runs, or add an
      explicit no-news mode.
- [ ] Add a real news provider before enabling news/sentiment analysts in a
      real-data workflow.
- [ ] Add a rule-only technical analyst path if no LLM should be required for
      technical-only paper runs.
- [x] Configure and test `TAURUS_LLM_PROVIDER=lmstudio`, with `openai` and
      `gemini` as explicit hosted-provider opt-ins.
- [x] Add LLM-backed `BullResearcherAgent` debate output with LM Studio as the
      default runtime provider and deterministic score/confidence guardrails.
- [x] Add LLM-backed `BearResearcherAgent` debate output with LM Studio as the
      default runtime provider and deterministic score/confidence guardrails.
- [x] Add LLM-backed `ResearchManagerAgent` debate synthesis with LM Studio as
      the default runtime provider and deterministic score/confidence guardrails.
- [x] Add position-aware `TraderAgent` proposals with LM Studio as the default
      runtime provider.
- [x] Add optional LLM explanation to `PortfolioManagerAgent`; deterministic
      final approval gates remain authoritative.
- [x] Add market-hours paper position monitoring for stop-loss/take-profit
      lifecycle review using Kite latest quote snapshots and existing paper
      decision flow.
- [ ] Validate real Screener CSV exports and confirm they map cleanly to Taurus
      instruments before enabling fundamentals in production-like paper runs.
- [ ] Review and calibrate paper brokerage, charges, slippage, and fill
      assumptions.
- [x] Add true portfolio continuity across paper runs.
- [ ] Verify Telegram alerts with local-only credentials before relying on alert
      delivery.
- [x] Enable graph analyst for the Kite real-data paper path after graph
      readiness validates reviewed active edges and latest stats.
- [x] Enable graph-aware risk for the Kite real-data paper path through
      deterministic `RiskEngine` BUY hard-rule structures.

## Bottom Line

Taurus is a local paper-trading simulator with a complete decision workflow. The
market-data default is now Kite-only; remaining mocks are non-market components:

```text
paper mode
paper broker simulator
Kite market data
real LLM provider defaulting to LM Studio
mock alerts
technical analyst by config default; technical plus graph on paper-loop-kite
graph disabled by config default; enabled on paper-loop-kite after preflight
graph risk disabled by config default; enabled on paper-loop-kite after preflight
Neo4j disabled
```

The completed migration/allocation path is summarized in
`docs/TAURUS_MILESTONE_TODO.md`. Docker Postgres-only persistence, real LLM
providers, Kite-only runtime market data, graph-enabled Kite paper loops,
market-hours position monitoring, money management, and full-universe dynamic
allocation are implemented through M43. Remaining work is deferred outside that
completed sequence.

**The target workflow should become:**

Analysts produce evidence
Bull/Bear/Manager produce research view
TraderAgent produces after-close entry/hold/reduce/exit proposal
PositionMonitorService produces market-hours stop-loss/take-profit proposals
RiskEngine applies hard gates
PortfolioManagerAgent gives final approval
PaperBroker executes simulated BUY/SELL
Position monitor checks stop-loss/take-profit between runs
