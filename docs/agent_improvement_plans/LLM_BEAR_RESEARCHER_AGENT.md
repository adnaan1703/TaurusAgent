# LLM BearResearcherAgent Plan

Last reviewed: 2026-05-30

Execution order: 6 of 10. Run this after the real LLM provider migration and
after `LLM_BULL_RESEARCHER_AGENT.md`. It should preserve the same provider,
schema, and dashboard conventions used by the bull migration.

## Summary

Migrate `BearResearcherAgent` from a fully deterministic downside thesis builder
into an LLM-assisted bearish research agent. The agent should receive an LLM
provider by default through the debate workflow, with LM Studio as the intended
default provider going forward.

The constructor may allow provider injection for tests, but runtime debate
services must always provide an `LLMProvider` from `build_llm_provider(settings)`.
With the planned provider migration, that defaults to LM Studio. Deterministic
rules remain the scoring anchor and test fallback, but production debate should
not silently run without a real provider.

## Target State

- `ResearchDebateService` constructs `BearResearcherAgent` with an
  `LLMProvider` from `build_llm_provider(settings)`.
- The broader real-provider migration must already be complete. Default provider
  path:
  - `TAURUS_LLM_PROVIDER=lmstudio`
  - `TAURUS_LLM_BASE_URL=http://localhost:1234/v1`
  - `TAURUS_LLM_MODEL` optional, falling back to `local-model`
- `BearResearcherAgent.run(...)` keeps the existing public return type:
  `BearThesis`.
- No database or API response shape changes are required.
- `DebateReport.model_version` identifies the real LLM provider/model used; do
  not add per-agent model fields to `BearThesis`.

## Implementation Changes

### Agent Wiring

- Add `llm_provider: LLMProvider | None = None` to `BearResearcherAgent`.
- Extract the current deterministic implementation into a private
  `_run_rules(symbol, reports)` helper.
- Keep `run(symbol, reports)` as the public entrypoint:
  - validate reports as today;
  - build deterministic baseline with `_run_rules`;
  - call the LLM path with the provider supplied by the service;
  - on missing provider in runtime wiring, fail fast with a clear configuration
    error;
  - on LLM failure, record the failure. For production debate workflows, fail
    the workflow instead of silently returning a rules-only thesis. Tests may
    assert rule fallback behavior through explicit helper calls.

### LLM Contract

- Add a bear-research output schema, for example `LLMBearThesisOutput`, with:
  - `score: Decimal` in `[-1, 1]`
  - `confidence: Decimal` in `[0, 1]`
  - `key_points: list[str]`
  - `risk_flags: list[str]`
  - `model_version: str`
- Add `complete_bear_thesis(...) -> LLMBearThesisOutput` to the provider layer
  if no shared research completion API already exists.
- Implement the method for all real runtime providers:
  - `LMStudioProvider`
  - `OpenAIProvider`
  - `GeminiProvider`
- Use strict JSON-only prompting and temperature `0`.
- Use test-local fake providers for unit tests. Do not reintroduce or depend on
  a runtime mock LLM provider.

## Prompt And Guardrails

- Build a compact evidence pack from analyst reports:
  - `agent_name`, `score`, `confidence`, `stance`, `horizon`
  - first few `key_points` and all high-priority `risks`
  - `source_ids`, `report_id`, and `model_version`
- Prompt the model to challenge the investment case, identify downside risks,
  and call out assumptions in bullish evidence. It must not invent data, source
  IDs, broker actions, or order instructions.
- Taurus injects `symbol` and `source_report_ids`; the model output must not be
  trusted for those fields.
- Keep deterministic scoring as the anchor:
  - compute the current rule score and confidence first;
  - require final bear scores to remain `<= 0.0000`;
  - allow the LLM score and confidence to adjust the rule values by at most
    `0.1000` in either direction;
  - clamp and quantize final values exactly like the existing rule output.
- Prefer LLM `key_points` and `risk_flags` when valid; fall back to rule text if
  the LLM returns empty, repetitive, or non-evidence-bound text.
- Always preserve at least one explicit risk flag. If the LLM omits risks, use
  deterministic `_risk_flags(reports)`.

### BearResearcherAgent System Prompt

```text
You are Taurus BearResearcherAgent, the skeptical research voice in a local
paper-trading decision workflow. Your job is to build the strongest
evidence-led bear case for the symbol from the supplied analyst reports.

Hard rules:
- Use only provided analyst evidence, scores, risks, source IDs, and report IDs.
- Challenge bullish assumptions and identify downside, invalidation, liquidity,
  data-quality, and concentration risks where the supplied evidence supports
  them.
- Do not invent facts, prices, filings, news, source IDs, broker actions, or
  order instructions.
- Do not decide trades or position sizes. TraderAgent and deterministic risk
  gates handle that later.
- Keep bearish score non-positive after Taurus guardrails and keep confidence
  grounded in evidence quality.
- Return valid JSON matching the requested schema and no prose outside JSON.
```

## Observability

- Reuse `taurus_llm_failures_total` for provider errors and schema failures.
- Include provider/model information in logs for successful LLM bear research.
- Surface LLM usage through debate-level `model_version`, for example:
  - `research_debate_llm_one_shot_v1:lmstudio:<model>`
  - `research_debate_llm_one_shot_v1:openai:<model>`
  - `research_debate_llm_one_shot_v1:gemini:<model>`

### API And React Dashboard

- No database or API response-shape change is required for the bear thesis.
- Existing Debate and Decision Trail surfaces should continue to render:
  - bear key points
  - risk flags
  - source report IDs
  - debate `model_version`
- If the dashboard displays model/provider metadata, ensure the LLM-backed
  debate version is visible without treating it as a new schema variant.

## Test Plan

- Unit test successful LLM bear output with a fake provider.
- Unit test runtime missing-provider wiring raises a clear configuration error.
- Unit test provider failure records the LLM failure metric and raises a clear
  workflow error.
- Unit test invalid LLM schema records the LLM failure metric and raises a clear
  workflow error.
- Unit test deterministic `_run_rules` still returns the exact baseline for
  guardrail comparison and isolated rule tests.
- Unit test LLM score cannot make the bear thesis bullish.
- Unit test LLM score cannot move the rule score by more than `0.1000`.
- Unit test Taurus-owned fields are preserved:
  - uppercase `symbol`
  - sorted `source_report_ids`
- Integration test `ResearchDebateService` passes a provider into
  `BearResearcherAgent` and still returns a valid `/debates` payload.
- React dashboard regression for existing Debate and Decision Trail surfaces.
- Run:
  - `make test`
  - `make lint`

## Assumptions And Defaults

- LM Studio is the intended default LLM provider for local paper workflows.
- The first implementation is one-shot bear thesis generation, not multi-round
  bull/bear dialogue.
- Deterministic bear scoring remains the safety anchor for clamping and tests,
  but production debate should use a real provider.
- Mocks created: test-only fake LLM provider outputs.
- Mocks used: test-only fake LLM provider outputs only.
