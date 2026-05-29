# LLM BearResearcherAgent Plan

Last reviewed: 2026-05-30

## Summary

Migrate `BearResearcherAgent` from a fully deterministic downside thesis builder
into an LLM-assisted bearish research agent. The agent should receive an LLM
provider by default through the debate workflow, with LM Studio as the intended
default provider going forward.

LLM usage remains optional by design: the agent attempts LLM-backed analysis
first, but deterministic rule output remains the fallback whenever the provider
is unavailable, returns invalid JSON, or fails schema validation.

## Target State

- `ResearchDebateService` constructs `BearResearcherAgent` with an
  `LLMProvider` from `build_llm_provider(settings)`.
- If the broader real-provider migration is not already complete, set the
  forward default provider path to:
  - `TAURUS_LLM_PROVIDER=lmstudio`
  - `TAURUS_LLM_BASE_URL=http://localhost:1234/v1`
  - `TAURUS_LLM_MODEL` optional, falling back to `local-model`
- `BearResearcherAgent.run(...)` keeps the existing public return type:
  `BearThesis`.
- No database or API response shape changes are required.
- `DebateReport.model_version` identifies whether the debate used LLM research
  or deterministic fallback; do not add per-agent model fields to `BearThesis`.

## Implementation Changes

### Agent Wiring

- Add `llm_provider: LLMProvider | None = None` to `BearResearcherAgent`.
- Extract the current deterministic implementation into a private
  `_run_rules(symbol, reports)` helper.
- Keep `run(symbol, reports)` as the public entrypoint:
  - validate reports as today;
  - build deterministic baseline with `_run_rules`;
  - if `llm_provider` is present, call the LLM path;
  - on LLM failure, record the failure and return the deterministic baseline.

### LLM Contract

- Add a bear-research output schema, for example `LLMBearThesisOutput`, with:
  - `score: Decimal` in `[-1, 1]`
  - `confidence: Decimal` in `[0, 1]`
  - `key_points: list[str]`
  - `risk_flags: list[str]`
  - `model_version: str`
- Add `complete_bear_thesis(...) -> LLMBearThesisOutput` to the provider layer
  if no shared research completion API already exists.
- Implement the method for LM Studio/OpenAI-compatible providers with strict
  JSON-only prompting and temperature `0`.
- Update the mock/test provider path only as needed for local tests and current
  mock-mode compatibility.

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

## Observability

- Reuse `taurus_llm_failures_total` for provider errors and schema failures.
- Include provider/model information in logs for successful LLM bear research.
- Surface fallback through debate-level `model_version`, for example:
  - `research_debate_llm_one_shot_v1:lmstudio:<model>`
  - `research_debate_rules_v1+llm_fallback`

## Test Plan

- Unit test successful LLM bear output with a fake provider.
- Unit test provider failure returns the exact deterministic bear fallback.
- Unit test invalid LLM schema returns deterministic fallback.
- Unit test LLM score cannot make the bear thesis bullish.
- Unit test LLM score cannot move the rule score by more than `0.1000`.
- Unit test Taurus-owned fields are preserved:
  - uppercase `symbol`
  - sorted `source_report_ids`
- Integration test `ResearchDebateService` passes a provider into
  `BearResearcherAgent` and still returns a valid `/debates` payload.
- Run:
  - `make test`
  - `make lint`

## Assumptions And Defaults

- LM Studio is the intended default LLM provider for local paper workflows.
- The first implementation is one-shot bear thesis generation, not multi-round
  bull/bear dialogue.
- Deterministic bear scoring remains the safety anchor and fallback.
- Mocks created: test-only fake LLM provider outputs.
- Mocks used: existing mock/test provider only for local tests and fallback
  verification.

