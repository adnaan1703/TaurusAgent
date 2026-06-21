# Research Debate Agents Deep Dive

This document explains the current implementation of `BullResearcherAgent`,
`BearResearcherAgent`, and `ResearchManagerAgent`: what they read, what they
write, how their deterministic baselines work, how the LLM output is
constrained, which environment variables matter, and which database tables are
involved.

For the broader decision pipeline, see `docs/TAURUS_AGENT_ARCHITECTURE.md`. For
table definitions, see `docs/TAURUS_DATABASE_TABLES.md`.

## Role in the Decision Pipeline

`BullResearcherAgent` and `BearResearcherAgent` are research thesis agents. They
do not place orders, size positions, approve risk, or decide final buy/sell
actions.

Their responsibility is to turn persisted analyst reports into two opposing,
evidence-bound theses. `ResearchManagerAgent` then synthesizes those theses into
the consensus that `TraderAgent` consumes.

```text
analyst_reports
  -> BullResearcherAgent
  -> BearResearcherAgent
  -> generated debate rounds
  -> ResearchManagerAgent
  -> debate_reports
  -> TraderAgent
  -> Allocation
  -> Risk
  -> PortfolioManagerAgent
  -> ExecutionRouter
```

Important nuance: the current implementation is not an iterative multi-turn
debate where bull and bear agents repeatedly respond to each other. It is a
one-shot bull thesis, a one-shot bear thesis, generated debate-round text, and a
one-shot manager synthesis.

## Main Implementation Files

| Area | File |
|---|---|
| Bull thesis agent | `packages/taurus_core/agents/bull_researcher.py` |
| Bear thesis agent | `packages/taurus_core/agents/bear_researcher.py` |
| Research synthesis agent | `packages/taurus_core/agents/research_manager.py` |
| Debate orchestration | `packages/taurus_core/research/debate_service.py` |
| Research schemas | `packages/taurus_core/research/schemas.py` |
| Analyst report schema | `packages/taurus_core/agents/schemas.py` |
| LLM provider factory | `packages/taurus_core/llm/__init__.py` |
| LLM prompts and output schemas | `packages/taurus_core/llm/base.py` |
| LM Studio provider | `packages/taurus_core/llm/lmstudio_provider.py` |
| OpenAI provider | `packages/taurus_core/llm/openai_provider.py` |
| Gemini provider | `packages/taurus_core/llm/gemini_provider.py` |
| DB models | `packages/taurus_core/db/models.py` |
| DB repositories | `packages/taurus_core/db/repositories.py` |
| Paper-run orchestration | `packages/taurus_core/paper_trading/service.py` |
| Standalone debate CLI | `scripts/run_research_debate.py` |

## Runtime Entry Points

During a paper run, `PaperRunService` runs the analyst suite first. After
`analyst_reports` exist for a symbol/run, it calls:

```python
ResearchDebateService(...).run(
    symbol=symbol,
    run_id=run_id,
    profile_id=settings.taurus_paper_portfolio_id,
    rounds_requested=self.rounds_requested,
)
```

`ResearchDebateService.run()` performs this sequence:

1. Validate `rounds_requested` is between `1` and `10`.
2. Uppercase the symbol.
3. Verify the symbol exists in `instruments`.
4. Load `analyst_reports` for the exact `run_id` and symbol.
5. Derive or validate the profile id from the reports.
6. Run `BullResearcherAgent`.
7. Run `BearResearcherAgent`.
8. Build generated debate rounds from thesis points.
9. Run `ResearchManagerAgent`.
10. Replace the prior `debate_reports` row for the same run/symbol and commit.

The standalone CLI path is:

```bash
make debate-mock SYMBOL=INFY ROUNDS=2
```

That target runs `scripts/run_research_debate.py`, which prepares inputs, runs
the analyst suite, and then runs `ResearchDebateService`.

## Inputs

The direct method call for both agents is:

```python
agent.run(symbol=symbol, reports=reports)
```

Both agents receive the same direct inputs:

| Input | Source | Purpose |
|---|---|---|
| `symbol` | Paper run or CLI | Stock being researched. Normalized to uppercase. |
| `reports` | `AnalystReportRepository.list_for_run_symbol()` | Analyst evidence for the exact run/symbol. |
| `llm_provider` | `build_llm_provider(settings)` | Produces schema-validated thesis JSON. |

Each `AnalystReport` includes:

| Field | Meaning |
|---|---|
| `report_id` | Stable analyst report id used as source lineage. |
| `run_id` | Paper run or analyst-run lineage. |
| `portfolio_id` | Profile/portfolio identity. |
| `symbol` | Stock symbol. |
| `agent_name` | Producing analyst, for example `TechnicalAnalystAgent` or `GraphAnalystAgent`. |
| `as_of` | Evidence timestamp. |
| `score` | Directional analyst score in `[-1, 1]`. |
| `confidence` | Analyst confidence in `[0, 1]`. |
| `stance` | `bullish`, `bearish`, or `neutral`. |
| `horizon` | `intraday`, `short`, `medium`, or `long`. |
| `key_points` | Analyst evidence points. |
| `risks` | Analyst risk points. |
| `source_ids` | Evidence source identifiers. |
| `model_version` | Producing model or rule version. |

## Environment Variables and Defaults

The research agents are controlled mostly by the shared settings and LLM
provider configuration. They do not have separate bull, bear, or manager-specific
environment variables.

| Variable | Code default | Makefile / `.env.example` default | Used By | Effect |
|---|---:|---:|---|---|
| `DATABASE_URL` | `postgresql+psycopg://taurus:taurus@localhost:5432/taurus` | Same | `Settings`, DB session factory | Selects the Postgres database that stores analyst and debate artifacts. SQLite is rejected. |
| `TAURUS_LLM_PROVIDER` | `lmstudio` | `lmstudio` | `build_llm_provider()` | Selects provider. Supported values are `lmstudio`, `openai`, and `gemini`. `mock` is no longer supported for runtime LLM flow. |
| `TAURUS_LLM_BASE_URL` | Empty string | `http://localhost:1234/v1` in `.env.example` | LLM providers | If empty, provider fallback is used: LM Studio `http://localhost:1234/v1`, OpenAI `https://api.openai.com/v1`, Gemini `https://generativelanguage.googleapis.com/v1beta`. |
| `TAURUS_LLM_MODEL` | Empty string | Empty string | `Settings.configured_llm_model` | If empty, effective defaults are LM Studio `local-model`, OpenAI `gpt-5-mini`, Gemini `gemini-2.5-flash`. |
| `TAURUS_LLM_TIMEOUT_SECONDS` | `20` | `20` | LLM providers | Request timeout for thesis and manager calls. |
| `OPENAI_API_KEY` | Empty string | Empty string | `OpenAIProvider` | Required only when `TAURUS_LLM_PROVIDER=openai`. |
| `GEMINI_API_KEY` | Empty string | Empty string | `GeminiProvider` | Required only when `TAURUS_LLM_PROVIDER=gemini`. |
| `TAURUS_ENABLED_ANALYSTS` | `technical` | `technical` in `.env.example`, `technical,graph` in `make paper-loop-kite` | Analyst suite | Controls which upstream analyst reports exist. The research agents consume whatever reports were persisted. |
| `TAURUS_PROFILE_ID` | Empty string, normalized to `local-paper` if no alias is set | `local-paper` | Paper run and debate service | Preferred profile id written to `debate_reports.portfolio_id`. |
| `TAURUS_PAPER_PORTFOLIO_ID` | Empty string, legacy alias | `local-paper` | Paper run and debate service | Legacy profile alias. If both aliases are set, they must match. |
| `ROUNDS` | `2` through `DEFAULT_DEBATE_ROUNDS` | `2` in Makefile | `scripts/run_research_debate.py` / `make debate-mock` | Number of generated debate rounds. This is a CLI/Make variable, not a `Settings` field. |
| `SYMBOL` | `INFY` in `run_research_debate.py` | `INFY` in Makefile | Standalone scripts | Symbol to run through the standalone debate path. |

## Database Tables Read

| Table | Read By | Purpose |
|---|---|---|
| `instruments` | `ResearchDebateService.run()` | Confirms the symbol exists before debate runs. |
| `analyst_reports` | `AnalystReportRepository.list_for_run_symbol()` | Loads the exact evidence pack for `run_id` and symbol. |

The agents themselves receive already-loaded `AnalystReport` objects. The
database read boundary is in `ResearchDebateService`, not inside the bull or bear
agent classes.

## Database Tables Written

| Table | Written By | Purpose |
|---|---|---|
| `debate_reports` | `ResearchRepository.replace_debate_for_run_symbol()` | Stores bull thesis, bear thesis, generated rounds, manager consensus, source report IDs, and full payload. |

`replace_debate_for_run_symbol()` also deletes downstream artifacts for the same
run/symbol before inserting the replacement debate:

| Downstream table cleaned | Why |
|---|---|
| `trader_proposals` | Trader proposal depends on the old debate. |
| `risk_reviews` | Risk review depends on the old trader proposal. |
| `final_decisions` | Final decision depends on old risk/proposal state. |
| Paper artifacts for the run/symbol | Removes stale paper orders, fills, positions, and paper audit events, while preserving protected next-open settlement artifacts. |

The bull and bear theses are not stored as separate top-level tables. They are
embedded JSON fields inside the `debate_reports` row.

## `debate_reports` Output Shape

Important persisted fields:

| Field | Meaning |
|---|---|
| `debate_id` | Stable debate id derived from run, symbol, rounds, and source reports. |
| `run_id` | Paper run or standalone analyst run id. |
| `portfolio_id` | Profile id. |
| `symbol` | Stock symbol. |
| `as_of` | Latest `as_of` timestamp from source analyst reports. |
| `rounds_requested` | Number of generated debate rounds. Default is `2`. |
| `consensus_label` | Manager consensus label. |
| `consensus_score` | Manager consensus score in `[-1, 1]`. |
| `confidence` | Manager confidence in `[0, 1]`. |
| `bull_thesis` | Full `BullThesis` JSON. |
| `bear_thesis` | Full `BearThesis` JSON. |
| `rounds` | Generated debate transcript rows. |
| `manager_summary` | Full manager synthesis JSON. |
| `source_report_ids` | Analyst report IDs used by the debate. |
| `model_version` | Debate model version prefix plus provider model version. |
| `payload` | Full serialized `DebateReport`. |

## BullResearcherAgent Output

`BullResearcherAgent` returns a `BullThesis`:

| Field | Meaning |
|---|---|
| `symbol` | Uppercase stock symbol. |
| `score` | Bull thesis score in `[-1, 1]`. |
| `confidence` | Bull thesis confidence in `[0, 1]`. |
| `key_points` | Up to three evidence-bound bullish points. |
| `conditions` | Conditions required for the positive thesis to remain valid. |
| `source_report_ids` | Sorted source analyst report IDs. |

Default deterministic conditions are:

```text
Positive thesis requires risk approval before any order can be considered.
Position size must remain within configured portfolio limits.
No new severe negative event should appear before execution review.
```

## BearResearcherAgent Output

`BearResearcherAgent` returns a `BearThesis`:

| Field | Meaning |
|---|---|
| `symbol` | Uppercase stock symbol. |
| `score` | Bear thesis score in `[-1, 1]`; final guarded value is always `<= 0`. |
| `confidence` | Bear thesis confidence in `[0, 1]`. |
| `key_points` | Up to three evidence-bound bearish points. |
| `risk_flags` | Explicit risk flags from bearish scores, low confidence, and analyst risks. |
| `source_report_ids` | Sorted source analyst report IDs. |

## Internal Working: Shared Flow

Both agents use the same high-level pattern:

1. Validate at least one analyst report exists.
2. Normalize the symbol to uppercase.
3. Build a deterministic rules baseline.
4. Build a compact evidence pack from analyst reports.
5. Ask the configured LLM provider for structured JSON.
6. Validate the LLM output schema.
7. Clamp LLM score/confidence movement against the rules baseline.
8. Filter LLM text so it must be tied to provided evidence terms.
9. Fall back to deterministic baseline text if LLM text is unsupported.
10. Return an immutable Pydantic thesis object.

If `llm_provider` is missing, the agent records an LLM failure metric and raises
`LLMProviderError`. The runtime debate workflow requires a real configured LLM
provider.

## Internal Working: Bull Score

The deterministic bull score is computed from analyst scores and confidences:

```text
weighted_positive = sum(max(report.score, 0) * report.confidence)
bearish_drag = sum(abs(min(report.score, 0)) * report.confidence)
confidence_total = sum(report.confidence)

score =
  (weighted_positive - bearish_drag * 0.35)
  / confidence_total
```

Then the score is clamped to `[-1, 1]` and quantized to four decimals.

Interpretation:

- Positive analyst scores support the bull case.
- Negative analyst scores reduce the bull case.
- The negative drag is only `35%` because the bull agent is intentionally trying
  to build the strongest defensible positive case while still acknowledging
  risks.
- If total confidence is zero, the bull score is `0.0000`.

Bull confidence is:

```text
average analyst confidence
+ directional support boost
+ conviction boost
```

Where:

- directional support boost is based on the share of reports with
  `score >= 0.05`, capped by the formula at `0.12` when all reports support the
  direction.
- conviction boost is `abs(score) * 0.20`.
- final confidence is clamped to `[0, 1]` and quantized to four decimals.

## Internal Working: Bull Key Points

The bull agent ranks reports by:

```text
(report.score, report.confidence, report.agent_name) descending
```

It then takes the first key point from the strongest reports, up to three items.
If a strongly bearish report appears after at least one point was already found,
it is skipped for bull-key-point construction.

If no positive evidence is available, the fallback text is:

```text
No positive analyst evidence was available for SYMBOL; bull case is minimal.
```

## Internal Working: Bear Score

The deterministic bear score is computed from negative analyst evidence, low
confidence, and risk density:

```text
weighted_negative = sum(abs(min(report.score, 0)) * report.confidence)
average_negative = weighted_negative / confidence_total
low_confidence_penalty = 0.05 for each report with confidence < 0.50
risk_density_penalty = min(0.20, total_number_of_risks * 0.015)

score =
  -(average_negative + low_confidence_penalty + risk_density_penalty)
```

Then the score is clamped to `[-1, 1]` and quantized to four decimals.

Interpretation:

- Negative analyst scores strengthen the bear case.
- Low-confidence analyst reports add a bearish penalty.
- More listed risks add a bearish penalty, capped at `0.20`.
- If total confidence is zero, the bear score is `0.0000`.

Bear confidence is:

```text
average analyst confidence
+ risk density boost
+ conviction boost
```

Where:

- risk density boost is `min(0.15, average_risk_count * 0.025)`.
- conviction boost is `abs(score) * 0.20`.
- final confidence is clamped to `[0, 1]` and quantized to four decimals.

## Internal Working: Bear Key Points and Risk Flags

The bear agent ranks reports by:

```text
(report.score, -report.confidence, report.agent_name) ascending
```

That pushes more negative scores earlier. It then takes the first risk from the
highest-priority reports, up to three items.

Risk flags are built in two passes:

1. Add a flag when a report has `score <= -0.10`.
2. Add a flag when a report has `confidence < 0.50`.
3. Add the first listed risk from each report, sorted by agent name.
4. Return at most four risk flags.

If no explicit risk flags exist, the fallback text is:

```text
No explicit bearish risk flags were produced by analyst reports.
```

## LLM Request Shape

Both agents pass two major objects to the provider:

| Object | Contents |
|---|---|
| `baseline` | Deterministic thesis fields plus a guardrail string. |
| `evidence_pack` | Compact analyst report list with IDs, agent names, scores, confidence, stance, horizon, first three key points, first three risks, source IDs, and model version. |

The LLM is asked for JSON only. Bull output must match:

```json
{
  "score": 0.0,
  "confidence": 0.0,
  "key_points": ["..."],
  "conditions": ["..."],
  "model_version": "..."
}
```

Bear output must match:

```json
{
  "score": 0.0,
  "confidence": 0.0,
  "key_points": ["..."],
  "risk_flags": ["..."],
  "model_version": "..."
}
```

## LLM Prompt Rules

The bull prompt tells the model to:

- build the strongest evidence-led bull case.
- use only supplied analyst evidence, scores, risks, source IDs, and report IDs.
- address material negative evidence directly.
- not invent facts, prices, filings, news, source IDs, broker actions, or order
  instructions.
- not decide trades or position sizes.
- return valid JSON only.

The bear prompt tells the model to:

- build the strongest evidence-led bear case.
- challenge bullish assumptions.
- identify downside, invalidation, liquidity, data-quality, and concentration
  risks where supported.
- not invent facts, prices, filings, news, source IDs, broker actions, or order
  instructions.
- not decide trades or position sizes.
- keep the bearish score non-positive after Taurus guardrails.
- return valid JSON only.

## LLM Guardrails

| Guardrail | Implementation |
|---|---|
| Schema validation | Provider output is validated as `LLMBullThesisOutput` or `LLMBearThesisOutput`. |
| Score range | Pydantic schema enforces score in `[-1, 1]`. |
| Confidence range | Pydantic schema enforces confidence in `[0, 1]`. |
| Max LLM adjustment | LLM score/confidence may move the deterministic baseline by at most `0.1000`. |
| Bull score clamp | Final bull score is clamped to `[-1, 1]`. |
| Bear score clamp | Final bear score is additionally clamped to `<= 0.0000`. |
| Evidence-bound text | LLM text must contain evidence terms derived from report IDs, agent names, source IDs, key points, or risks. |
| Max LLM text items | At most three accepted LLM key points/conditions/risk flags. |
| Fallback behavior | If LLM text is unsupported or duplicate, deterministic baseline text is used. |
| Failure behavior | Missing, failing, or schema-invalid providers record an LLM failure metric and raise `LLMProviderError`. |

## Evidence-Term Filtering

The text filter builds evidence terms from:

- `report_id`
- `agent_name`
- every `source_id`
- words of length at least five from analyst `key_points`
- words of length at least five from analyst `risks`

An LLM key point, condition, or risk flag is accepted only if it contains at
least one of those terms. This prevents generic unsupported text such as "this is
a great opportunity" from replacing the deterministic thesis.

## Generated Debate Rounds

`ResearchDebateService._build_rounds()` creates `DebateRound` entries from the
already-computed theses:

```text
bull_argument =
  "{SYMBOL} bull case round {n}: {bull_point} Condition: {condition}"

bear_argument =
  "{SYMBOL} bear case round {n}: {bear_point} Risk flag: {risk_flag}"

manager_note =
  "Manager note: weigh upside evidence against risk flags; this transcript is
  research only and cannot create orders."
```

The service cycles through thesis points with modulo indexing if more rounds are
requested than there are points.

Default rounds:

```text
DEFAULT_DEBATE_ROUNDS = 2
```

Allowed runtime range:

```text
1 <= rounds_requested <= 10
```

## Handoff to ResearchManagerAgent

After bull and bear theses are built, `ResearchManagerAgent` receives:

| Input | Meaning |
|---|---|
| `symbol` | Stock symbol. |
| `reports` | Original analyst reports. |
| `bull_thesis` | Bull thesis generated above. |
| `bear_thesis` | Bear thesis generated above. |
| `rounds` | Generated debate-round transcript. |

The manager writes the final consensus inside `debate_reports`:

| Manager field | Meaning |
|---|---|
| `consensus_label` | `bullish`, `mild_bullish`, `neutral`, `mild_bearish`, or `bearish`. |
| `consensus_score` | Final research score in `[-1, 1]`. |
| `confidence` | Manager confidence in `[0, 1]`. |
| `summary` | Evidence-bound synthesis text. |
| `unresolved_uncertainties` | Material unknowns or disagreements. |

`TraderAgent` consumes this manager consensus, not the bull thesis alone or the
bear thesis alone.

## ResearchManagerAgent Inputs

`ResearchManagerAgent.run()` is called after bull and bear theses and generated
debate rounds exist:

```python
manager.run(
    symbol=symbol,
    reports=reports,
    bull_thesis=bull_thesis,
    bear_thesis=bear_thesis,
    rounds=rounds,
)
```

Direct inputs:

| Input | Type | Meaning |
|---|---|---|
| `symbol` | `str` | Stock symbol, normalized to uppercase before LLM failure handling and output logging. |
| `reports` | `list[AnalystReport]` | Original persisted analyst evidence for the exact run/symbol. Must not be empty. |
| `bull_thesis` | `BullThesis` | Bull agent output, including score, confidence, key points, conditions, and source report IDs. |
| `bear_thesis` | `BearThesis` | Bear agent output, including score, confidence, key points, risk flags, and source report IDs. |
| `rounds` | `list[DebateRound]` | Generated debate transcript rows. Must not be empty. |
| `llm_provider` | `LLMProvider` | Required runtime provider used for final evidence-bound synthesis. |

If `reports` is empty, the manager raises:

```text
Research manager requires at least one analyst report.
```

If `rounds` is empty, the manager raises:

```text
Research manager requires at least one debate round.
```

If no LLM provider is configured, it records an LLM failure metric and raises
`LLMProviderError`. The deterministic rules are a baseline and guardrail, not a
standalone runtime substitute.

## ResearchManagerAgent Output

The manager returns `ResearchManagerSummary`:

| Field | Meaning |
|---|---|
| `consensus_label` | Final research label recomputed from the final guarded score. |
| `consensus_score` | Final research score in `[-1, 1]`. This is the score consumed downstream by `TraderAgent`. |
| `confidence` | Manager confidence in `[0, 1]`. |
| `summary` | Evidence-bound synthesis text. |
| `unresolved_uncertainties` | Evidence-bound uncertainties, risk flags, low-confidence warnings, or data-quality warnings. |

Persisted locations:

| `debate_reports` field | Value |
|---|---|
| `consensus_label` | `manager_summary.consensus_label` |
| `consensus_score` | `manager_summary.consensus_score` |
| `confidence` | `manager_summary.confidence` |
| `manager_summary` | Full `ResearchManagerSummary` JSON |
| `payload.manager_summary` | Full serialized copy inside the full debate payload |

## Internal Working: Manager Consensus Score

The manager first builds a deterministic baseline. The analyst portion is a
confidence-weighted average of upstream analyst scores:

```text
weighted_total = sum(report.score * report.confidence)
confidence_total = sum(report.confidence)

analyst_score =
  weighted_total / confidence_total
  if confidence_total > 0
  else 0
```

The baseline consensus score then blends analyst evidence, bull thesis, and bear
thesis:

```text
consensus_score =
  analyst_score * 0.60
  + bull_thesis.score * 0.25
  + bear_thesis.score * 0.15
```

Then it is clamped to `[-1, 1]` and quantized to four decimals.

Interpretation:

- Upstream analyst reports dominate the manager baseline at `60%`.
- The bull thesis contributes `25%`.
- The bear thesis contributes `15%`.
- The bear thesis score is normally non-positive, so it usually pulls the
  consensus lower.
- A strong bull thesis cannot fully override weak or negative analyst evidence
  because the original analyst score has the largest weight.

## Internal Working: Manager Consensus Label

The consensus label is derived from the final guarded score:

| Score range | Label |
|---:|---|
| `score >= 0.45` | `bullish` |
| `0.15 <= score < 0.45` | `mild_bullish` |
| `-0.15 < score < 0.15` | `neutral` |
| `-0.45 < score <= -0.15` | `mild_bearish` |
| `score <= -0.45` | `bearish` |

The LLM response includes a `consensus_label`, but Taurus does not trust that
label as the persisted final label. After applying score guardrails, Taurus calls
`_label_from_score(consensus_score)` and persists the recomputed label.

## Internal Working: Manager Confidence

Manager confidence is also built from a deterministic baseline:

```text
average_report_confidence =
  sum(report.confidence) / number_of_reports

disagreement_penalty =
  abs(bull_thesis.score - bear_thesis.score) * 0.08

conviction_boost =
  abs(consensus_score) * 0.12

confidence =
  average_report_confidence * 0.60
  + bull_thesis.confidence * 0.20
  + bear_thesis.confidence * 0.20
  + conviction_boost
  - disagreement_penalty
```

Then it is clamped to `[0, 1]` and quantized to four decimals.

Interpretation:

- Analyst report confidence is the largest input at `60%`.
- Bull and bear thesis confidence each contribute `20%`.
- Stronger directional conviction increases confidence.
- Wider disagreement between bull and bear scores reduces confidence.

## Internal Working: Manager Uncertainties

The deterministic uncertainty list is built in this order:

1. Start with the first three `bear_thesis.risk_flags`.
2. Add a mock-mode warning if any analyst report risk mentions `mock`.
3. Add an incomplete real-data warning if analyst risks mention incomplete real
   data or incomplete coverage.
4. Add a low-confidence warning listing analyst agents with confidence below
   `0.50`.
5. Return the first four items.
6. If no uncertainty exists, return:

```text
No unresolved uncertainty was identified beyond normal market risk.
```

This matters downstream because `TraderAgent` can use
`manager_summary.unresolved_uncertainties` as invalidation or caution context.

## ResearchManagerAgent LLM Request Shape

The manager passes one `context` object to
`llm_provider.complete_research_manager_summary()`:

| Context key | Contents |
|---|---|
| `analyst_reports` | Report IDs, agent names, scores, confidence, stance, horizon, first three key points, first three risks, source IDs, and model version. Reports are sorted by `report_id`. |
| `bull_thesis` | Bull score, confidence, key points, conditions, and source report IDs. |
| `bear_thesis` | Bear score, confidence, key points, risk flags, and source report IDs. |
| `debate_rounds` | Generated round number, bull argument, bear argument, and manager note, sorted by round number. |
| `deterministic_baseline` | Baseline label, score, confidence, summary, uncertainties, and guardrail text. |
| `guardrails` | Research-only instruction, max score adjustment, max confidence adjustment, and note that Taurus recomputes the label. |

The requested LLM JSON shape is:

```json
{
  "consensus_label": "bullish|mild_bullish|neutral|mild_bearish|bearish",
  "consensus_score": 0.0,
  "confidence": 0.0,
  "summary": "...",
  "unresolved_uncertainties": ["..."],
  "model_version": "..."
}
```

## ResearchManagerAgent LLM Prompt Rules

The manager prompt tells the model to:

- synthesize analyst reports plus bull and bear theses into one evidence-bound
  consensus summary.
- synthesize research only.
- not place trades, size positions, route orders, or override deterministic risk
  controls.
- use only supplied analyst reports, bull thesis, bear thesis, source IDs,
  scores, confidence, risks, and the deterministic baseline.
- preserve material disagreement and unresolved uncertainty instead of forcing
  false consensus.
- not invent facts, source IDs, prices, filings, news, broker actions, or order
  instructions.
- keep the label consistent with evidence, while Taurus recomputes the final
  label from the final score.
- return valid JSON only.

## ResearchManagerAgent Guardrails

| Guardrail | Implementation |
|---|---|
| Schema validation | Provider output is validated as `LLMResearchManagerOutput`. |
| Score range | Pydantic schema enforces `consensus_score` in `[-1, 1]`. |
| Confidence range | Pydantic schema enforces `confidence` in `[0, 1]`. |
| Max LLM score movement | LLM consensus score may move the deterministic baseline by at most `0.1000`. |
| Max LLM confidence movement | LLM confidence may move the deterministic baseline by at most `0.1000`. |
| Final label recomputation | Persisted label is recomputed from the final guarded score, not copied from the LLM label. |
| Evidence-bound summary | LLM summary must include evidence terms from analyst reports, bull thesis, or bear thesis. |
| Repetitive summary rejection | Summary text with at least eight words but three or fewer unique normalized words is rejected. |
| Evidence-bound uncertainties | LLM uncertainty items must be unique, non-repetitive, and tied to evidence terms. |
| Max LLM uncertainty items | At most four LLM uncertainty items are accepted before baseline data-quality warnings are preserved. |
| Fallback behavior | Unsupported summary or uncertainties fall back to the deterministic baseline. |
| Failure behavior | Missing, failing, or schema-invalid providers record an LLM failure metric and raise `LLMProviderError`. |

Manager evidence terms are built from:

- analyst `report_id`, `agent_name`, and `source_ids`.
- significant words from analyst key points and risks.
- significant words from bull key points and conditions.
- significant words from bear key points and risk flags.

The manager ignores common generic words such as `analyst`, `bullish`,
`bearish`, `consensus`, `evidence`, `research`, and `thesis` when building the
evidence-term set.

## Operational Debugging

Useful focused tests:

```bash
uv run pytest tests/unit/test_bull_researcher.py tests/unit/test_bear_researcher.py tests/unit/test_research_manager.py tests/unit/test_research_debate.py -q
```

Useful standalone command:

```bash
make debate-mock SYMBOL=INFY ROUNDS=2
```

Useful DB inspection targets:

```sql
select run_id, symbol, agent_name, score, confidence, stance, key_points, risks
from analyst_reports
where run_id = '<run_id>' and symbol = '<symbol>'
order by agent_name;

select run_id, symbol, rounds_requested, consensus_label, consensus_score,
       confidence, bull_thesis, bear_thesis, rounds, manager_summary
from debate_reports
where run_id = '<run_id>' and symbol = '<symbol>';
```

When debugging why a stock later became `BUY`, `NO_TRADE`, or was skipped, start
with `debate_reports.manager_summary`. Use `bull_thesis` and `bear_thesis` to
explain what evidence the manager was weighing, but remember that allocation,
risk review, and portfolio approval happen after this research layer.
