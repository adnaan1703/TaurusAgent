from __future__ import annotations

from collections.abc import Sequence

ANALYST_KEYS: tuple[str, ...] = ("technical", "news", "sentiment", "fundamentals")
DEFAULT_ENABLED_ANALYSTS = "technical"
MIN_ANALYST_REPORTS = 1


def parse_enabled_analysts(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = value

    enabled: list[str] = []
    for item in raw_items:
        key = str(item).strip().lower()
        if key and key not in enabled:
            enabled.append(key)

    if not enabled:
        raise ValueError("TAURUS_ENABLED_ANALYSTS must include at least one analyst.")

    unknown = sorted(set(enabled) - set(ANALYST_KEYS))
    if unknown:
        allowed = ", ".join(ANALYST_KEYS)
        invalid = ", ".join(unknown)
        raise ValueError(
            f"Unsupported analyst key(s): {invalid}. "
            f"TAURUS_ENABLED_ANALYSTS supports: {allowed}."
        )

    return tuple(enabled)


def skipped_analysts(enabled: str | Sequence[str]) -> tuple[str, ...]:
    enabled_set = set(parse_enabled_analysts(enabled))
    return tuple(key for key in ANALYST_KEYS if key not in enabled_set)
