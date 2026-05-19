from __future__ import annotations

import json

from taurus_core.config import get_settings
from taurus_core.llm import build_llm_provider


if __name__ == "__main__":
    settings = get_settings()
    provider = build_llm_provider(settings)
    output = provider.complete_analyst_report(
        agent_name="LLMSmokeAgent",
        symbol="INFY",
        context={
            "score": "0.10",
            "confidence": "0.50",
            "horizon": "short",
            "key_points": ["Smoke prompt for Taurus LLM provider."],
            "risks": ["Smoke output only; no trading action."],
        },
    )
    print(json.dumps(output.model_dump(mode="json"), sort_keys=True))
