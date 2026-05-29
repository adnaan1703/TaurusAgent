# LLM ResearchManagerAgent Plan

Last reviewed: 2026-05-30

Execution order: 7 of 10. Run this after the real LLM provider migration and
after both `LLM_BULL_RESEARCHER_AGENT.md` and
`LLM_BEAR_RESEARCHER_AGENT.md`.

## Summary

Migrate `ResearchManagerAgent` from a fully deterministic consensus summarizer
into an LLM-assisted debate facilitator and synthesis agent. The agent should
receive an LLM provider by default through the debate workflow, with LM Studio
as the intended default provider going forward.

This plan keeps v1 as a one-shot synthesis flow: Bull and Bear provide their
theses, then the Manager synthesizes consensus, confidence, and unresolved
uncertainties. Full multi-round dialogue remains a later extension, even though
the TradingAgents paper uses facilitator-controlled natural-language debate.

## Target State

- `ResearchDebateService` constructs `ResearchManagerAgent` with an
  `LLMProvider` from `build_llm_provider(settings)`.
- The broader real-provider migration must already be complete. Default provider
  path:
  - `TAURUS_LLM_PROVIDER=lmstudio`
  - `TAURUS_LLM_BASE_URL=http://localhost:1234/v1`
  - `TAURUS_LLM_MODEL` optional, falling back to `local-model`
- `ResearchManagerAgent.run(...)` keeps the existing public return type:
  `ResearchManagerSummary`.
- Existing `DebateReport`, `/debates`, dashboard, and `TraderAgent` consumers
  remain schema-compatible.
- `ResearchManagerAgent` becomes the future control point for dialogue mode,
  but v1 does not add extra LLM calls per `rounds_requested`.

## Implementation Changes

### Agent Wiring

- Add `llm_provider: LLMProvider | None = None` to `ResearchManagerAgent`.
- Extract the current deterministic implementation into a private
  `_run_rules(symbol, reports, bull_thesis, bear_thesis, rounds)` helper.
- Keep `run(...)` as the public entrypoint:
  - validate reports and rounds as today;
  - build deterministic baseline with `_run_rules`;
  - call the LLM path with the provider supplied by the service;
  - on missing provider in runtime wiring, fail fast with a clear configuration
    error;
  - on LLM failure, record the failure. For production debate workflows, fail
    the workflow instead of silently returning a rules-only summary. Tests may
    assert rule fallback behavior through explicit helper calls.

### LLM Contract

- Add a manager output schema, for example `LLMResearchManagerOutput`, with:
  - `consensus_label: ConsensusLabel`
  - `consensus_score: Decimal` in `[-1, 1]`
  - `confidence: Decimal` in `[0, 1]`
  - `summary: str`
  - `unresolved_uncertainties: list[str]`
  - `model_version: str`
- Add `complete_research_manager_summary(...) -> LLMResearchManagerOutput` to
  the provider layer if no shared research completion API already exists.
- Implement the method for all real runtime providers:
  - `LMStudioProvider`
  - `OpenAIProvider`
  - `GeminiProvider`
- Use strict JSON-only prompting and temperature `0`.
- Use test-local fake providers for unit tests. Do not reintroduce or depend on
  a runtime mock LLM provider.

### Prompt And Guardrails

- Build a compact manager context from:
  - analyst report names, scores, confidence, stances, key points, and risks;
  - final `BullThesis`;
  - final `BearThesis`;
  - existing generated `DebateRound` transcript view;
  - deterministic baseline manager summary.
- Prompt the model to synthesize, not trade:
  - identify the stronger side of the research argument;
  - explain the consensus in plain language;
  - list unresolved uncertainties;
  - avoid broker actions, order sizing, and invented evidence.
- Keep deterministic consensus as the anchor:
  - compute the current rule consensus score and confidence first;
  - allow the LLM consensus score and confidence to adjust the rule values by
    at most `0.1000` in either direction;
  - recompute `consensus_label` from the final adjusted score using the
    existing `_label_from_score` thresholds;
  - ignore any LLM label that conflicts with the recomputed label;
  - clamp and quantize final values exactly like the existing rule output.
- Prefer LLM `summary` and `unresolved_uncertainties` when valid; fall back to
  rule text if the LLM returns empty, repetitive, or non-evidence-bound text.
- Preserve data-quality warnings when any analyst report risk mentions legacy
  mock-mode inputs or incomplete real-data coverage.

### ResearchManagerAgent System Prompt

```text
You are Taurus ResearchManagerAgent, the debate facilitator and synthesis agent
for a local paper-trading research workflow. Your job is to synthesize analyst
reports plus bull and bear theses into one evidence-bound consensus summary.

Hard rules:
- Synthesize research only. Do not place trades, size positions, route orders,
  or override deterministic risk controls.
- Use only supplied analyst reports, bull thesis, bear thesis, source IDs,
  scores, confidence, risks, and the deterministic baseline.
- Preserve material disagreement and unresolved uncertainty instead of forcing
  false consensus.
- Do not invent facts, source IDs, prices, filings, news, broker actions, or
  order instructions.
- Taurus recomputes the final consensus label from the final score; your label
  must be consistent with the evidence.
- Return valid JSON matching the requested schema and no prose outside JSON.
```

### Debate Rounds

- Keep `rounds_requested` validation at `1..10`.
- In v1, do not make additional LLM calls per round.
- Continue storing `DebateRound` entries as a transcript-style compatibility
  view generated from the final bull thesis, bear thesis, and manager note.
- Leave the later dialogue extension explicit:
  - `ResearchManagerAgent` chooses number of rounds;
  - Bull and Bear alternate responses;
  - Manager summarizes history and records final structured consensus.

### Observability

- Reuse `taurus_llm_failures_total` for provider errors and schema failures.
- Include provider/model information in logs for successful manager synthesis.
- Set debate-level `model_version` to distinguish the real provider used, for
  example:
  - `research_debate_llm_one_shot_v1:lmstudio:<model>`
  - `research_debate_llm_one_shot_v1:openai:<model>`
  - `research_debate_llm_one_shot_v1:gemini:<model>`

### API And React Dashboard

- Existing `DebateReport`, `/debates`, dashboard, and `TraderAgent` consumers
  should remain schema-compatible.
- Debate and Decision Trail surfaces should render:
  - manager summary
  - unresolved uncertainties
  - consensus label
  - consensus score and confidence
  - debate `model_version`
- No new dashboard page is required.

## Test Plan

- Unit test successful LLM manager synthesis with a fake provider.
- Unit test runtime missing-provider wiring raises a clear configuration error.
- Unit test provider failure records the LLM failure metric and raises a clear
  workflow error.
- Unit test invalid LLM schema records the LLM failure metric and raises a clear
  workflow error.
- Unit test deterministic `_run_rules` still returns the exact baseline for
  guardrail comparison and isolated rule tests.
- Unit test LLM score cannot move the rule consensus by more than `0.1000`.
- Unit test final `consensus_label` is recomputed from final score, not trusted
  from inconsistent LLM output.
- Unit test data-quality uncertainty is preserved when analyst report risks
  mention legacy mock inputs or incomplete real-data coverage.
- Integration test `ResearchDebateService` passes a provider into
  `ResearchManagerAgent` and still returns a valid `/debates` payload.
- Regression test `TraderAgent` can consume the LLM-backed debate unchanged.
- React dashboard regression for existing Debate and Decision Trail surfaces.
- Run:
  - `make test`
  - `make lint`

## Assumptions And Defaults

- LM Studio is the intended default LLM provider for local paper workflows.
- The first implementation is one-shot manager synthesis, not multi-round
  moderated dialogue.
- Deterministic consensus scoring remains the safety anchor for clamping and
  tests, but production debate should use a real provider.
- Mocks created: test-only fake LLM provider outputs.
- Mocks used: test-only fake LLM provider outputs only.
