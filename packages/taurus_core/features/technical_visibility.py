from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def technical_v2_from_metadata(metadata: Any) -> dict[str, Any] | None:
    if not isinstance(metadata, Mapping):
        return None
    technical_v2 = metadata.get("technical_v2")
    if not isinstance(technical_v2, Mapping):
        return None
    return dict(technical_v2)


def technical_v2_from_ranking(ranking: Any) -> dict[str, Any] | None:
    if not isinstance(ranking, Mapping):
        return None
    return technical_v2_from_metadata(ranking) or technical_v2_from_metadata(
        ranking.get("metadata")
    )


def technical_v2_from_strategy_signal(signal: Any) -> dict[str, Any] | None:
    if not isinstance(signal, Mapping):
        return None
    technical_v2 = technical_v2_from_metadata(signal)
    if technical_v2 is not None:
        return technical_v2

    explanation = signal.get("explanation")
    if not isinstance(explanation, Mapping):
        return None
    return technical_v2_from_metadata(explanation.get("metadata"))


def technical_v2_by_symbol_from_strategy_summary(
    strategy_summary: Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(strategy_summary, Mapping):
        return {}

    by_symbol: dict[str, dict[str, Any]] = {}
    raw_by_symbol = strategy_summary.get("technical_v2_by_symbol")
    if isinstance(raw_by_symbol, Mapping):
        for raw_symbol, raw_technical_v2 in raw_by_symbol.items():
            symbol = str(raw_symbol).strip().upper()
            if symbol and isinstance(raw_technical_v2, Mapping):
                by_symbol[symbol] = dict(raw_technical_v2)

    ranked_candidates = strategy_summary.get("ranked_candidates")
    if isinstance(ranked_candidates, list):
        for ranking in ranked_candidates:
            if not isinstance(ranking, Mapping):
                continue
            symbol = str(ranking.get("symbol") or "").strip().upper()
            technical_v2 = technical_v2_from_ranking(ranking)
            if symbol and technical_v2 is not None:
                by_symbol.setdefault(symbol, technical_v2)

    signals = strategy_summary.get("signals")
    if isinstance(signals, list):
        for signal in signals:
            if not isinstance(signal, Mapping):
                continue
            symbol = str(signal.get("symbol") or "").strip().upper()
            technical_v2 = technical_v2_from_strategy_signal(signal)
            if symbol and technical_v2 is not None:
                by_symbol.setdefault(symbol, technical_v2)

    return dict(sorted(by_symbol.items()))
