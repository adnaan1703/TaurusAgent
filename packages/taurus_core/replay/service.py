from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    CompanyEventModel,
    DebateReportModel,
    FinalDecisionModel,
    PaperFillModel,
    PaperOrderModel,
    RiskReviewModel,
    TraderProposalModel,
)
from taurus_core.replay.schemas import DecisionReplay, ReplayStage


class DecisionReplayService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replay(self, *, decision_id: str) -> DecisionReplay:
        anchor = self._find_anchor(decision_id)
        if anchor is None:
            raise ValueError(f"Decision {decision_id} was not found.")
        run_id, symbol, status = anchor

        stages = [
            self._analyst_stage(run_id=run_id, symbol=symbol),
            self._company_events_stage(symbol=symbol),
            self._debate_stage(run_id=run_id, symbol=symbol),
            self._trader_stage(run_id=run_id, symbol=symbol),
            self._risk_stage(decision_id=decision_id),
            self._final_stage(decision_id=decision_id),
            self._paper_order_stage(decision_id=decision_id),
            self._paper_fill_stage(decision_id=decision_id),
            self._audit_stage(decision_id=decision_id, run_id=run_id, symbol=symbol),
        ]
        return DecisionReplay(
            decision_id=decision_id,
            run_id=run_id,
            symbol=symbol,
            status=status,
            note="Replay is reconstructed from stored Taurus artifacts; it does not rerun agents.",
            stages=stages,
        )

    def _find_anchor(self, decision_id: str) -> tuple[str, str, str] | None:
        final_decision = self.session.scalar(
            select(FinalDecisionModel)
            .where(FinalDecisionModel.decision_id == decision_id)
            .order_by(FinalDecisionModel.as_of.desc())
            .limit(1)
        )
        if final_decision is not None:
            return final_decision.run_id, final_decision.symbol, final_decision.status

        risk_review = self.session.scalar(
            select(RiskReviewModel)
            .where(RiskReviewModel.decision_id == decision_id)
            .order_by(RiskReviewModel.as_of.desc())
            .limit(1)
        )
        if risk_review is not None:
            return risk_review.run_id, risk_review.symbol, risk_review.status

        order = self.session.scalar(
            select(PaperOrderModel)
            .where(PaperOrderModel.decision_id == decision_id)
            .order_by(PaperOrderModel.submitted_at.desc())
            .limit(1)
        )
        if order is not None:
            return order.run_id, order.symbol, order.status

        report = self.session.scalar(
            select(AnalystReportModel)
            .where(AnalystReportModel.decision_id == decision_id)
            .order_by(AnalystReportModel.as_of.desc())
            .limit(1)
        )
        if report is not None:
            return report.run_id, report.symbol, "ANALYST_REPORTS_ONLY"
        return None

    def _analyst_stage(self, *, run_id: str, symbol: str) -> ReplayStage:
        rows = list(
            self.session.scalars(
                select(AnalystReportModel)
                .where(
                    AnalystReportModel.run_id == run_id,
                    AnalystReportModel.symbol == symbol.upper(),
                )
                .order_by(AnalystReportModel.agent_name)
            )
        )
        return _stage("analyst_reports", [_payload(row) for row in rows])

    def _company_events_stage(self, *, symbol: str) -> ReplayStage:
        rows = list(
            self.session.scalars(
                select(CompanyEventModel)
                .where(CompanyEventModel.symbol == symbol.upper())
                .order_by(CompanyEventModel.event_time.desc())
                .limit(20)
            )
        )
        return _stage(
            "company_events",
            [
                {
                    "event_id": row.event_id,
                    "document_id": row.document_id,
                    "symbol": row.symbol,
                    "event_type": row.event_type,
                    "event_time": row.event_time,
                    "headline": row.headline,
                    "severity": row.severity,
                    "horizon": row.horizon,
                    "source_confidence": row.source_confidence,
                }
                for row in rows
            ],
        )

    def _debate_stage(self, *, run_id: str, symbol: str) -> ReplayStage:
        row = self.session.scalar(
            select(DebateReportModel)
            .where(
                DebateReportModel.run_id == run_id,
                DebateReportModel.symbol == symbol.upper(),
            )
            .order_by(DebateReportModel.as_of.desc())
            .limit(1)
        )
        return _stage("debate_report", [_payload(row)] if row is not None else [])

    def _trader_stage(self, *, run_id: str, symbol: str) -> ReplayStage:
        row = self.session.scalar(
            select(TraderProposalModel)
            .where(
                TraderProposalModel.run_id == run_id,
                TraderProposalModel.symbol == symbol.upper(),
            )
            .order_by(TraderProposalModel.as_of.desc())
            .limit(1)
        )
        return _stage("trader_proposal", [_payload(row)] if row is not None else [])

    def _risk_stage(self, *, decision_id: str) -> ReplayStage:
        rows = list(
            self.session.scalars(
                select(RiskReviewModel)
                .where(RiskReviewModel.decision_id == decision_id)
                .order_by(RiskReviewModel.as_of.desc())
            )
        )
        return _stage("risk_review", [_payload(row) for row in rows])

    def _final_stage(self, *, decision_id: str) -> ReplayStage:
        rows = list(
            self.session.scalars(
                select(FinalDecisionModel)
                .where(FinalDecisionModel.decision_id == decision_id)
                .order_by(FinalDecisionModel.as_of.desc())
            )
        )
        return _stage("final_decision", [_payload(row) for row in rows])

    def _paper_order_stage(self, *, decision_id: str) -> ReplayStage:
        rows = list(
            self.session.scalars(
                select(PaperOrderModel)
                .where(PaperOrderModel.decision_id == decision_id)
                .order_by(PaperOrderModel.submitted_at.desc())
            )
        )
        return _stage("paper_order", [_payload(row) for row in rows])

    def _paper_fill_stage(self, *, decision_id: str) -> ReplayStage:
        order_ids = list(
            self.session.scalars(
                select(PaperOrderModel.order_id).where(PaperOrderModel.decision_id == decision_id)
            )
        )
        if not order_ids:
            return _stage("paper_fills", [])
        rows = list(
            self.session.scalars(
                select(PaperFillModel)
                .where(PaperFillModel.order_id.in_(order_ids))
                .order_by(PaperFillModel.filled_at, PaperFillModel.fill_sequence)
            )
        )
        return _stage("paper_fills", [_payload(row) for row in rows])

    def _audit_stage(self, *, decision_id: str, run_id: str, symbol: str) -> ReplayStage:
        rows = list(
            self.session.scalars(
                select(AuditLogModel)
                .where(
                    (
                        AuditLogModel.payload["decision_id"].as_string() == decision_id
                    )
                    | (AuditLogModel.payload["run_id"].as_string() == run_id)
                    | (AuditLogModel.payload["symbol"].as_string() == symbol.upper())
                )
                .order_by(AuditLogModel.created_at, AuditLogModel.id)
                .limit(100)
            )
        )
        return _stage(
            "audit_log",
            [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "actor": row.actor,
                    "payload": row.payload,
                    "note": row.note,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
        )


def _stage(name: str, artifacts: list[dict[str, object]]) -> ReplayStage:
    safe_artifacts = [_json_safe(artifact) for artifact in artifacts]
    return ReplayStage(
        name=name,
        artifact_count=len(safe_artifacts),
        artifacts=safe_artifacts,
    )


def _payload(row) -> dict[str, object]:
    return dict(row.payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
