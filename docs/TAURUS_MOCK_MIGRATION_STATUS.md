# Taurus Mock Migration Status

Last reviewed: 2026-05-30

This document tracks which Taurus components are still mocked or simulated, which
agents depend on them, and what remains to migrate toward a real-data paper
workflow. Taurus remains paper-trading-first: live trading is disabled and real
broker order routing is not part of the current roadmap.

## Current Effective Defaults

```text
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
TAURUS_MARKET_DATA_PROVIDER=mock
TAURUS_LLM_PROVIDER=mock
TAURUS_ALERT_PROVIDER=mock
TAURUS_ENABLED_ANALYSTS=technical
TAURUS_GRAPH_ENABLED=false
TAURUS_GRAPH_RISK_ENABLED=false
TAURUS_NEO4J_ENABLED=false
```

## Mocked Components

| Component | Current state | Has agent? | Requires LLM provider? | Migration required |
|---|---:|---:|---:|---|
| Trading mode | `paper` | No | No | None for paper MVP. Live trading remains intentionally blocked. |
| Broker | `paper` | No | No | Real broker order routing would require a new approved milestone. |
| Market data | `mock` | No | No | Use `csv` or `kite`; avoid mixing mock/Kite data in the same DB. |
| News data | Mock | Feeds `NewsAnalystAgent` / `SentimentAnalystAgent` | Yes, if those analysts are enabled | Add real news provider or explicit no-news mode. |
| LLM provider | `mock` | Used by analyst agents | Yes | Configure `lmstudio` or `openai`; validate model output quality. |
| Alerts | `mock` | No | No | Use `telegram`; verify delivery with local credentials. |
| Fundamentals | Mock unless Screener CSV imported | `FundamentalsAnalystAgent` | Yes, if enabled | Import and validate real Screener CSV exports. |
| Graph analyst | Disabled | `GraphAnalystAgent` | No | Enable via `TAURUS_ENABLED_ANALYSTS=...,graph` after graph data/stats are imported. |
| Graph risk | Disabled | No separate analyst | No | Enable `TAURUS_GRAPH_RISK_ENABLED=true` after concentration limits are reviewed. |
| Neo4j | Disabled | No | No | Optional only; rebuild projection from Postgres if needed. |
| Paper fills/costs/slippage | Simulated | No | No | Replace placeholder bps/fill assumptions with broker-calibrated assumptions. |

## Analyst Roster

| Analyst key | Agent class | Enabled now? | Uses LLM provider? | Mock dependency risk |
|---|---|---:|---:|---|
| `technical` | `TechnicalAnalystAgent` | Yes | Yes | Uses candles/features/signals, then calls configured LLM provider; currently mock LLM. |
| `news` | `NewsAnalystAgent` | No | Yes | Depends on stored news/events; currently mock news unless a real provider is added. |
| `sentiment` | `SentimentAnalystAgent` | No | Yes | Depends on stored sentiment from events; currently mock event source. |
| `fundamentals` | `FundamentalsAnalystAgent` | No | Yes | Uses real imported Screener scores when present; otherwise mock fallback. |
| `graph` | `GraphAnalystAgent` | No | No | Deterministic graph rules; no LLM override. |

Current enabled analyst roster:

```text
TAURUS_ENABLED_ANALYSTS=technical
```

This means only `TechnicalAnalystAgent` runs by default. Because
`TAURUS_LLM_PROVIDER=mock`, the active analyst report path currently uses
`MockLLMProvider`.

## Non-Analyst Agents And Services

These are "agents" in code structure, but they are not currently LLM agents.
Today, they are deterministic rule agents that consume analyst reports and other
stored artifacts.

| Workflow | Agents/services | Requires LLM provider? | Current mock exposure |
|---|---|---:|---|
| Debate | `BullResearcherAgent`, `BearResearcherAgent`, `ResearchManagerAgent` | No | Consumes analyst reports; if reports are mock-LLM-backed, debate inherits that limitation. |
| Trader proposal | `TraderAgent` | No | Consumes debate output; inherits upstream analyst/data limitations. |
| Risk review | `RiskyRiskAgent`, `NeutralRiskAgent`, `SafeRiskAgent`, `RiskEngine` | No | Can be influenced by mock news/events in the DB. |
| Final approval | `PortfolioManagerAgent` | No | Consumes risk review; no direct LLM use. |
| Paper execution | `ExecutionRouter`, `PaperBroker` | No | Simulated fills/costs/slippage only. |

## LLM Usage By Agent

| Component | Current implementation | Uses LLM today? | Proposed LLM provider requirement | Priority | Proposed LLM role |
|---|---|---:|---|---:|---|
| `TechnicalAnalystAgent` | Builds rule/context fallback, then calls `llm_provider.complete_analyst_report()` | Yes | Optional | Medium | Explain deterministic technical evidence; signal math should remain rule-based. |
| `NewsAnalystAgent` | Builds event context, then calls LLM provider | Yes | MUST when enabled for real-data runs | High | Classify, summarize, and reason over real unstructured news. |
| `SentimentAnalystAgent` | Builds sentiment context, then calls LLM provider | Yes | Optional | Medium | Explain event tone; numeric sentiment should remain model/rule-backed. |
| `FundamentalsAnalystAgent` | Builds fundamentals context, then calls LLM provider | Yes | MUST when enabled for real-data runs | High | Interpret Screener/financial metrics and surface business risks. |
| `GraphAnalystAgent` | Fully deterministic graph scoring | No | Optional | Low | Explain graph evidence; scoring should remain deterministic. |
| `BullResearcherAgent` | Computes bull thesis from analyst reports using rules | No | MUST | High | Build bullish thesis from analyst evidence. |
| `BearResearcherAgent` | Computes bear thesis from analyst reports using rules | No | MUST | High | Challenge assumptions, surface downside, and identify invalidation risks. |
| `ResearchManagerAgent` | Computes consensus from reports plus bull/bear theses | No | MUST | High | Synthesize bull/bear debate into consensus, confidence, and unresolved uncertainties. |
| `TraderAgent` | Converts consensus into proposal using rules | No | MUST | High | Convert research consensus into trade thesis, entry logic, stop-loss, take-profit, hold/reduce/exit rationale. |
| `RiskyRiskAgent` / `NeutralRiskAgent` / `SafeRiskAgent` | Risk persona rules | No | Optional | Medium | Provide advisory committee-style risk reasoning; hard risk rules remain authoritative. |
| `RiskEngine` | Hard risk rules | No | Never | N/A | Keep deterministic: kill switch, caps, stale data, severe event block, graph concentration gates. |
| `PortfolioManagerAgent` | Final approval rules | No | Optional | Low | Explain final approval/rejection; deterministic approval gates remain authoritative. |
| `ExecutionRouter` / `PaperBroker` | Order routing and paper execution | No | Never | N/A | Keep deterministic and auditable. |

Current distinction:

```text
Analyst agents = can call LLM provider
Debate / trader / risk / portfolio agents = currently rule-based consumers of analyst outputs
```

If Taurus should support true LLM-backed debate, trader proposal, or risk
committee reasoning, that requires a separate migration task. It is not present
in the current implementation.

The minimum high-value LLM migration target is:

```text
BullResearcherAgent
BearResearcherAgent
ResearchManagerAgent
TraderAgent
```

The advisory risk personas can be upgraded after that. `RiskEngine`,
`ExecutionRouter`, and `PaperBroker` should not use LLMs.

## Mock Migration Checklist

- [ ] Switch market data defaults or run path from `mock` to `kite` or `csv` for
      real-data paper runs.
- [ ] Prevent mixed mock/Kite data in the same database, or make provider-scoped
      universe handling explicit.
- [ ] Remove unconditional `MockNewsProvider` import from paper runs, or add an
      explicit no-news mode.
- [ ] Add a real news provider before enabling news/sentiment analysts in a
      real-data workflow.
- [ ] Add a rule-only technical analyst path that does not call the mock LLM
      provider when no LLM is desired.
- [ ] Configure and test `TAURUS_LLM_PROVIDER=lmstudio` or `openai` if LLM-backed
      analyst reports should be real model outputs.
- [ ] Add optional LLM-backed debate, trader proposal, and risk committee agents
      if the intended architecture requires those workflows to call an LLM
      directly.
- [ ] Validate real Screener CSV exports and confirm they map cleanly to Taurus
      instruments before enabling fundamentals in production-like paper runs.
- [ ] Review and calibrate paper brokerage, charges, slippage, and fill
      assumptions.
- [ ] Add true portfolio continuity across paper runs.
- [ ] Verify Telegram alerts with local-only credentials before relying on alert
      delivery.
- [ ] Enable graph analyst only after graph data, graph stats, and desired
      analyst roster behavior are validated.
- [ ] Enable graph-aware risk only after concentration thresholds are reviewed.

## Bottom Line

Taurus is a local paper-trading simulator with a complete decision workflow, but
it is still mock-default. The active default path is:

```text
paper mode
paper broker simulator
mock market data
mock LLM
mock alerts
technical analyst only
graph disabled
graph risk disabled
Neo4j disabled
```

The first practical migration target is a technical-only real-data paper run:

```bash
TAURUS_ENABLED_ANALYSTS=technical make paper-loop-kite
```

That still uses mock LLM and mock news today, so it is not yet fully mock-free.

**The target workflow should become:**

Analysts produce evidence
Bull/Bear/Manager produce research view
TraderAgent produces entry/hold/reduce/exit proposal
RiskEngine applies hard gates
PortfolioManagerAgent gives final approval
PaperBroker executes simulated BUY/SELL
Position monitor checks stop-loss/take-profit between runs
