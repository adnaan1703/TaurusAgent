from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from structlog.contextvars import bind_contextvars, reset_contextvars

TRACE_KEYS = {
    "run_id",
    "decision_id",
    "order_id",
    "fill_id",
    "document_id",
    "debate_id",
    "proposal_id",
    "risk_check_id",
    "final_decision_id",
}


@contextmanager
def bound_trace_context(**context: Any) -> Iterator[None]:
    trace_context = {
        key: value
        for key, value in context.items()
        if key in TRACE_KEYS and value not in (None, "")
    }
    tokens = bind_contextvars(**trace_context)
    try:
        yield
    finally:
        reset_contextvars(**tokens)
