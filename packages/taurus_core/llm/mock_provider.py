from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import LLMAnalystOutput, stance_from_score


class MockLLMProvider:
    def __init__(self, *, model_version: str = "mock-llm-v1") -> None:
        self._model_version = model_version

    @property
    def model_version(self) -> str:
        return self._model_version

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        score = _decimal_context(context, "score", Decimal("0"))
        confidence = _decimal_context(context, "confidence", Decimal("0.55"))
        horizon = str(context.get("horizon") or "short")
        key_points = _list_context(
            context,
            "key_points",
            [f"{agent_name} mock analysis completed for {symbol.upper()}."],
        )
        risks = _list_context(
            context,
            "risks",
            ["Mock-mode output should be replaced with real evidence before live use."],
        )
        return LLMAnalystOutput(
            score=max(Decimal("-1"), min(Decimal("1"), score)),
            confidence=max(Decimal("0"), min(Decimal("1"), confidence)),
            stance=stance_from_score(score),
            horizon=horizon,  # type: ignore[arg-type]
            key_points=key_points,
            risks=risks,
            model_version=self.model_version,
        )


def _decimal_context(context: dict[str, object], key: str, default: Decimal) -> Decimal:
    value = context.get(key)
    if value is None:
        return default
    return Decimal(str(value))


def _list_context(
    context: dict[str, object],
    key: str,
    default: list[str],
) -> list[str]:
    value = context.get(key)
    if not isinstance(value, list):
        return default
    cleaned = [str(item) for item in value if str(item).strip()]
    return cleaned or default
