from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from taurus_core.alerts.schemas import AlertEvent, alert_event_id
from taurus_core.execution.schemas import PaperOrder
from taurus_core.paper_trading.schemas import PaperRunError
from taurus_core.risk.schemas import HardRuleResult, RiskReview


def alert_smoke_test_event(*, run_id: str = "alert-smoke") -> AlertEvent:
    return AlertEvent(
        event_id=alert_event_id(event_type="alert_smoke_test", run_id=run_id),
        event_type="alert_smoke_test",
        severity="info",
        message="Taurus alert smoke test.",
        run_id=run_id,
        source_id="alert_smoke",
        created_at=datetime.now(timezone.utc),
    )


def paper_fill_event(order: PaperOrder, *, fill_ids: Iterable[str]) -> AlertEvent:
    fill_id_list = list(fill_ids)
    return AlertEvent(
        event_id=alert_event_id(
            event_type="paper_fill",
            run_id=order.run_id,
            decision_id=order.decision_id,
            symbol=order.symbol,
            source_id=order.order_id,
        ),
        event_type="paper_fill",
        severity="info",
        message=(
            f"Paper order {order.order_id} filled {order.filled_quantity}/"
            f"{order.quantity} {order.symbol}."
        ),
        run_id=order.run_id,
        decision_id=order.decision_id,
        symbol=order.symbol,
        source_id=order.order_id,
        created_at=order.updated_at,
        payload={
            "order_id": order.order_id,
            "final_decision_id": order.final_decision_id,
            "status": order.status,
            "filled_quantity": order.filled_quantity,
            "remaining_quantity": order.remaining_quantity,
            "fill_ids": fill_id_list,
        },
    )


def order_rejection_event(order: PaperOrder) -> AlertEvent:
    return AlertEvent(
        event_id=alert_event_id(
            event_type="order_rejection",
            run_id=order.run_id,
            decision_id=order.decision_id,
            symbol=order.symbol,
            source_id=order.order_id,
        ),
        event_type="order_rejection",
        severity="warning",
        message=f"Paper order {order.order_id} rejected: {order.rejection_reason}",
        run_id=order.run_id,
        decision_id=order.decision_id,
        symbol=order.symbol,
        source_id=order.order_id,
        created_at=order.updated_at,
        payload={
            "order_id": order.order_id,
            "final_decision_id": order.final_decision_id,
            "reason": order.rejection_reason,
            "status": order.status,
        },
    )


def risk_review_events(review: RiskReview) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    for result in review.hard_rule_results:
        event = _risk_rule_event(review, result)
        if event is not None:
            events.append(event)

    if review.status in {"REJECTED", "BLOCKED"}:
        events.append(
            AlertEvent(
                event_id=alert_event_id(
                    event_type="risk_rejection_spike",
                    run_id=review.run_id,
                    decision_id=review.decision_id,
                    symbol=review.symbol,
                    source_id=review.risk_check_id,
                ),
                event_type="risk_rejection_spike",
                severity="warning",
                message=f"Risk review {review.risk_check_id} ended with {review.status}.",
                run_id=review.run_id,
                decision_id=review.decision_id,
                symbol=review.symbol,
                source_id=review.risk_check_id,
                created_at=review.as_of,
                payload={
                    "risk_check_id": review.risk_check_id,
                    "status": review.status,
                    "proposal_id": review.proposal_id,
                },
            )
        )
    return events


def scheduled_job_failure_event(*, run_id: str, error: PaperRunError) -> AlertEvent:
    return AlertEvent(
        event_id=alert_event_id(
            event_type="scheduled_job_failure",
            run_id=run_id,
            symbol=error.symbol if error.symbol != "*" else None,
            source_id=f"{error.symbol}:{error.stage}",
        ),
        event_type="scheduled_job_failure",
        severity="critical" if error.symbol == "*" else "warning",
        message=f"Paper scheduled job failed at {error.stage} for {error.symbol}: {error.message}",
        run_id=run_id,
        symbol=error.symbol if error.symbol != "*" else None,
        source_id=f"{error.symbol}:{error.stage}",
        created_at=datetime.now(timezone.utc),
        payload=error.model_dump(mode="json"),
    )


def _risk_rule_event(review: RiskReview, result: HardRuleResult) -> AlertEvent | None:
    if result.rule == "kill_switch" and result.status == "blocked":
        return _rule_alert(
            review,
            result,
            event_type="kill_switch_activation",
            severity="critical",
            message=f"Kill switch blocked {review.symbol}: {result.details}",
        )
    if result.rule == "severe_event_block" and result.status == "blocked":
        return _rule_alert(
            review,
            result,
            event_type="severe_event_detected",
            severity="critical",
            message=f"Severe event blocked {review.symbol}: {result.details}",
        )
    if result.rule == "stale_data" and result.status in {"rejected", "blocked"}:
        return _rule_alert(
            review,
            result,
            event_type="stale_data_event",
            severity="warning",
            message=f"Stale data blocked {review.symbol}: {result.details}",
        )
    return None


def _rule_alert(
    review: RiskReview,
    result: HardRuleResult,
    *,
    event_type,
    severity,
    message: str,
) -> AlertEvent:
    return AlertEvent(
        event_id=alert_event_id(
            event_type=event_type,
            run_id=review.run_id,
            decision_id=review.decision_id,
            symbol=review.symbol,
            source_id=f"{review.risk_check_id}:{result.rule}",
        ),
        event_type=event_type,
        severity=severity,
        message=message,
        run_id=review.run_id,
        decision_id=review.decision_id,
        symbol=review.symbol,
        source_id=f"{review.risk_check_id}:{result.rule}",
        created_at=review.as_of,
        payload={
            "risk_check_id": review.risk_check_id,
            "proposal_id": review.proposal_id,
            "rule": result.rule,
            "rule_status": result.status,
            "details": result.details,
        },
    )
