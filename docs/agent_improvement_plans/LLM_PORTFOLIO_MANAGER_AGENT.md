# LLM PortfolioManagerAgent Plan

Last reviewed: 2026-05-30

Execution order: 9 of 10. Run this after Phase 1 position-aware TraderAgent so
the final-decision explanation prompt can include lifecycle actions, position
context, and no-action statuses.

## Summary

Add optional LLM-assisted explanations to `PortfolioManagerAgent` while keeping
deterministic final approval gates authoritative. The LLM may only enrich
`FinalDecision.reason`; it must not change status, action, approved quantity,
approved exposure, order flags, broker routing, IDs, or persistence behavior.

The real LLM provider migration must already be complete. The implementation
should wire the agent to the default Taurus LLM provider factory, so local
runtime explanations use LM Studio unless a hosted provider is explicitly
configured.

## Target State

- `PortfolioManagerAgent` accepts an optional `LLMProvider`.
- If no provider is supplied and LLM explanation is enabled, production services
  build one with `build_llm_provider(settings)`.
- Constructor-level optionality is allowed for tests and for explicit
  `enable_llm_explanation=false` operation only. Runtime LLM explanation mode
  must not run without a real provider.
- Deterministic approval/rejection logic runs first and remains the source of
  truth.
- The LLM can explain the final approval, rejection, or block only after the
  deterministic decision fields have been fixed.
- Explanation is exposed through existing `FinalDecision.reason`; no database,
  API, or UI response-shape change is required.
- Provider failures, invalid JSON, schema errors, and timeouts fall back to the
  deterministic reason without failing final approval.

## Implementation Changes

### Agent Wiring

- Add constructor parameters to `PortfolioManagerAgent`:
  - `llm_provider: LLMProvider | None = None`
  - `enable_llm_explanation: bool = True`
- Keep `run(...) -> FinalDecision` as the public entrypoint.
- Extract the current rule-only decision construction into a private helper so
  the final decision fields are computed before any LLM call.
- After deterministic fields are computed, optionally call the LLM explanation
  path and use its validated text to enrich `reason`.
- Do not let the LLM alter:
  - `final_action`
  - `status`
  - `approved_quantity`
  - `approved_position_pct_nav`
  - `is_order`
  - `can_send_to_broker`
  - trace IDs and generated final decision IDs

### LLM Contract

- Add a final-decision explanation schema, for example
  `LLMFinalDecisionExplanation`, with:
  - `reason: str`
  - `model_version: str`
- Add `complete_final_decision_explanation(...)` to the `LLMProvider` protocol.
- Implement the method for:
  - `LMStudioProvider`
  - `OpenAIProvider`
  - `GeminiProvider`, if the Gemini provider was added by the real LLM
    migration
- Use a strict JSON-only prompt with temperature `0`.
- Provide a compact context pack:
  - symbol, run ID, proposal ID, risk check ID
  - deterministic final action, status, approved quantity, approved exposure
  - deterministic reason
  - risk review status and risk committee summary
  - hard rule names/statuses/details
  - persona recommendations and required conditions
  - safety config flags relevant to paper approval
- Prompt guardrail: the model must explain the deterministic decision and must
  not recommend a different action, quantity, exposure, or broker outcome.
- Tests should use test-local fake providers. Do not add or depend on a runtime
  mock LLM provider.

### PortfolioManagerAgent System Prompt

```text
You are Taurus PortfolioManagerAgent, the final paper-trading approval explainer.
The deterministic Taurus approval logic has already fixed the final status,
action, quantity, exposure, order flag, and broker-routing flag. Your only job
is to explain that fixed decision clearly.

Hard rules:
- Do not change or suggest changing final action, status, quantity, exposure,
  order flags, broker routing, portfolio IDs, run IDs, or trace IDs.
- Do not recommend live trading, real broker order placement, leverage, shorts,
  options, or futures.
- Explain the deterministic decision using only supplied proposal, risk review,
  hard-rule, persona, and safety-config context.
- If the final decision is HOLD, NO_TRADE, or NO_ACTION, make clear that no paper
  order is expected.
- Do not invent facts, prices, positions, source IDs, or external news.
- Return valid JSON matching the requested schema and no prose outside JSON.
```

### Fallback And Observability

- On any LLM exception or schema failure:
  - call `record_llm_failure(...)` with agent name `PortfolioManagerAgent`;
  - persist the deterministic rule reason unchanged;
  - continue storing the final decision normally.
- On successful explanation:
  - keep the deterministic reason as the anchor;
  - append or replace with a concise reason that preserves the deterministic
    outcome in plain language;
  - mark `model_version` with a bounded suffix such as
    `portfolio_manager_rules_v1+llm_explainer`.
- If explanation is disabled, do not build or call a provider.

### API And React Dashboard

- No database or API response-shape change is expected because the explanation
  is exposed through existing `FinalDecision.reason` and `model_version`.
- React dashboard updates:
  - show LLM-enriched final-decision reasons without layout overflow;
  - preserve deterministic status/action/quantity fields as the primary visual
    facts;
  - show model/version text where the existing decision detail view already
    renders model metadata;
  - clearly distinguish `NO_ACTION` final decisions from missing paper orders.

## Test Plan

- Unit test successful LLM explanation on an approved final decision.
  - Assert status, action, quantity, exposure, and broker flags are unchanged.
  - Assert persisted/API `reason` includes the LLM explanation.
- Unit test provider failure.
  - Assert no exception is raised.
  - Assert deterministic reason is unchanged.
  - Assert the final decision is persisted.
- Unit test disabled explanations.
  - Assert no provider is built or called.
- Unit test blocked and rejected paths.
  - Assert the LLM can explain the outcome but cannot change `BLOCKED` or
    `REJECTED` status.
- Run:
  - `make test`
  - `make lint`

## Assumptions And Defaults

- Factory default is used: `PortfolioManagerAgent` uses
  `build_llm_provider(settings)`, which defaults to LM Studio after the real LLM
  provider migration.
- Explanation is exposed through `FinalDecision.reason` only.
- No DB migration is required because final-decision payloads already persist
  `reason` and `model_version`.
- Mocks created: test-only fake LLM providers for success/failure assertions.
- Mocks used: test-only fake LLM providers only.
