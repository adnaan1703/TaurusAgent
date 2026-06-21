from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.agents.schemas import (
    AnalystReport,
    AnalystScoreMetadata,
    LLMAnalystOutput,
    analyst_report_id,
    stance_from_score,
)
from taurus_core.llm.base import LLMProvider, LLMProviderError
from taurus_core.observability.metrics import record_llm_failure

REPORT_QUANT = Decimal("0.0001")


class BaseAnalystAgent:
    agent_name = "BaseAnalystAgent"

    def __init__(self, session: Session, llm_provider: LLMProvider) -> None:
        self.session = session
        self.llm_provider = llm_provider

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        raise NotImplementedError

    def _build_report(
        self,
        *,
        symbol: str,
        run_id: str,
        as_of: datetime,
        fallback: LLMAnalystOutput,
        context: dict[str, object],
        source_ids: list[str],
        score_metadata: AnalystScoreMetadata | None = None,
    ) -> AnalystReport:
        try:
            draft = self.llm_provider.complete_analyst_report(
                agent_name=self.agent_name,
                symbol=symbol,
                context=context,
            )
        except Exception as exc:
            record_llm_failure(
                provider=_provider_label(self.llm_provider),
                agent_name=self.agent_name,
                symbol=symbol,
                error_type=exc.__class__.__name__,
            )
            raise LLMProviderError(
                f"{self.agent_name} LLM provider failed for {symbol.upper()}: {exc}"
            ) from exc

        report_id = analyst_report_id(
            run_id=run_id,
            symbol=symbol,
            agent_name=self.agent_name,
            as_of=as_of,
            source_ids=source_ids,
        )
        score = _report_decimal(draft.score)
        metadata = _score_metadata_with_bounded_score(score_metadata, score)
        return AnalystReport(
            report_id=report_id,
            run_id=run_id,
            symbol=symbol,
            agent_name=self.agent_name,
            as_of=as_of,
            score=score,
            confidence=_report_decimal(draft.confidence),
            stance=draft.stance,
            horizon=draft.horizon,
            key_points=draft.key_points,
            risks=draft.risks,
            source_ids=source_ids,
            model_version=draft.model_version,
            score_metadata=metadata,
        )


def fallback_output(
    *,
    score: Decimal,
    confidence: Decimal,
    horizon: str,
    key_points: list[str],
    risks: list[str],
    model_version: str,
) -> LLMAnalystOutput:
    score = _report_decimal(score)
    return LLMAnalystOutput(
        score=score,
        confidence=_report_decimal(confidence),
        stance=stance_from_score(score),
        horizon=horizon,  # type: ignore[arg-type]
        key_points=key_points,
        risks=risks,
        model_version=model_version,
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _report_decimal(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value)).quantize(REPORT_QUANT)


def _score_metadata_with_bounded_score(
    metadata: AnalystScoreMetadata | None,
    bounded_report_score: Decimal,
) -> AnalystScoreMetadata | None:
    if metadata is None:
        return None
    return metadata.model_copy(update={"bounded_report_score": bounded_report_score})


def _provider_label(provider: LLMProvider) -> str:
    model_version = getattr(provider, "model_version", provider.__class__.__name__)
    return str(model_version).split(":", maxsplit=1)[0]
