from __future__ import annotations

from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.agents.schemas import AnalystReport, ReportHorizon
from taurus_core.db.repositories import AnalystReportRepository, ResearchRepository
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.research.schemas import (
    DebateReport,
    TraderAction,
    TraderOrderType,
    TraderProposal,
    trader_proposal_id,
)

SCORE_QUANT = Decimal("0.0001")


class TraderAgent:
    agent_name = "TraderAgent"
    model_version = "trader_proposal_rules_v1"

    def __init__(
        self,
        session: Session,
        *,
        max_requested_position_pct_nav: Decimal = Decimal("5.0"),
    ) -> None:
        self.session = session
        self.max_requested_position_pct_nav = max_requested_position_pct_nav

    def run(
        self,
        *,
        symbol: str,
        run_id: str = DEFAULT_ANALYST_RUN_ID,
        debate: DebateReport | None = None,
    ) -> TraderProposal:
        symbol = symbol.upper()
        reports = self._load_reports(symbol=symbol, run_id=run_id)
        debate = debate or self._load_debate(symbol=symbol, run_id=run_id)
        if debate.symbol != symbol:
            raise ValueError("Debate symbol does not match trader proposal symbol.")

        action = self._action(debate)
        order_type = self._order_type(action)
        requested_position = self._requested_position(action, debate)
        confidence = self._confidence(reports, debate)
        horizon = self._horizon(reports)
        stop_loss = Decimal("6.0000") if requested_position > 0 else Decimal("0.0000")
        take_profit = Decimal("12.0000") if requested_position > 0 else Decimal("0.0000")
        source_report_ids = sorted(report.report_id for report in reports)
        proposal = TraderProposal(
            proposal_id=trader_proposal_id(
                run_id=run_id,
                symbol=symbol,
                debate_id=debate.debate_id,
                source_report_ids=source_report_ids,
            ),
            run_id=run_id,
            symbol=symbol,
            debate_id=debate.debate_id,
            as_of=debate.as_of,
            action=action,
            confidence=confidence,
            horizon=horizon,
            requested_position_pct_nav=requested_position,
            order_type=order_type,
            entry_rule=self._entry_rule(action, order_type),
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            reason_summary=self._reason_summary(debate),
            invalid_if=self._invalid_if(debate),
            source_report_ids=source_report_ids,
            is_order=False,
            requires_risk_approval=True,
            model_version=self.model_version,
        )
        ResearchRepository(self.session).replace_trader_proposal_for_run_symbol(proposal)
        self.session.commit()
        with bound_trace_context(
            run_id=run_id,
            debate_id=debate.debate_id,
            proposal_id=proposal.proposal_id,
        ):
            get_logger(__name__).info(
                "trader.proposal.created",
                symbol=symbol,
                action=proposal.action,
                requested_position_pct_nav=str(proposal.requested_position_pct_nav),
                is_order=proposal.is_order,
            )
        return proposal

    def _load_reports(self, *, symbol: str, run_id: str) -> list[AnalystReport]:
        rows = AnalystReportRepository(self.session).list_for_run_symbol(
            symbol=symbol,
            run_id=run_id,
        )
        if not rows:
            raise ValueError(
                f"No analyst reports found for {symbol} run_id={run_id}. "
                "Run make run-analysts-mock first."
            )
        return [AnalystReport.model_validate(row.payload) for row in rows]

    def _load_debate(self, *, symbol: str, run_id: str) -> DebateReport:
        model = ResearchRepository(self.session).latest_debate(symbol=symbol, run_id=run_id)
        if model is None:
            raise ValueError(
                f"No debate found for {symbol} run_id={run_id}. Run make debate-mock first."
            )
        return DebateReport.model_validate(model.payload)

    def _action(self, debate: DebateReport) -> TraderAction:
        label = debate.manager_summary.consensus_label
        score = debate.manager_summary.consensus_score
        confidence = debate.manager_summary.confidence
        if label in {"bullish", "mild_bullish"} and score >= Decimal("0.15"):
            return "BUY"
        if label == "neutral" and confidence >= Decimal("0.65"):
            return "HOLD"
        if label in {"mild_bearish", "bearish"}:
            return "NO_TRADE"
        return "NO_TRADE"

    def _order_type(self, action: TraderAction) -> TraderOrderType:
        if action in {"BUY", "SELL", "REDUCE", "EXIT"}:
            return "LIMIT"
        return "NONE"

    def _requested_position(self, action: TraderAction, debate: DebateReport) -> Decimal:
        if action != "BUY":
            return Decimal("0.0000")
        raw_position = max(
            Decimal("1.0000"),
            abs(debate.manager_summary.consensus_score) * Decimal("10"),
        )
        return min(self.max_requested_position_pct_nav, raw_position).quantize(SCORE_QUANT)

    def _confidence(self, reports: list[AnalystReport], debate: DebateReport) -> Decimal:
        report_confidence = sum(
            (report.confidence for report in reports),
            Decimal("0"),
        ) / Decimal(len(reports))
        confidence = min(report_confidence, debate.manager_summary.confidence)
        return max(Decimal("0"), min(Decimal("1"), confidence)).quantize(SCORE_QUANT)

    def _horizon(self, reports: list[AnalystReport]) -> ReportHorizon:
        weighted: Counter[ReportHorizon] = Counter()
        for report in reports:
            weighted[report.horizon] += float(report.confidence)
        if not weighted:
            return "medium"
        return weighted.most_common(1)[0][0]

    def _entry_rule(self, action: TraderAction, order_type: TraderOrderType) -> str:
        if order_type == "NONE":
            return "No entry; wait for stronger research consensus and risk approval."
        return (
            f"Future {order_type} intent only after risk committee and final approval; "
            "do not route to a broker in M5."
        )

    def _reason_summary(self, debate: DebateReport) -> str:
        summary = debate.manager_summary
        return (
            f"Trader proposal follows {summary.consensus_label.replace('_', ' ')} "
            f"research consensus with score {summary.consensus_score}: {summary.summary}"
        )

    def _invalid_if(self, debate: DebateReport) -> list[str]:
        invalidation = [
            "Risk committee rejects or resizes the proposal.",
            "Live trading flag or broker provider is changed away from paper-safe defaults.",
            "New severe negative event arrives before final approval.",
        ]
        invalidation.extend(debate.manager_summary.unresolved_uncertainties[:2])
        return invalidation[:5]
