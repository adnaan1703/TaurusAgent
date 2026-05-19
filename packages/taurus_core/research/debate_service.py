from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from taurus_core.agents.bear_researcher import BearResearcherAgent
from taurus_core.agents.bull_researcher import BullResearcherAgent
from taurus_core.agents.research_manager import ResearchManagerAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.agents.schemas import AnalystReport
from taurus_core.db.repositories import (
    AnalystReportRepository,
    InstrumentRepository,
    ResearchRepository,
)
from taurus_core.research.schemas import (
    DebateReport,
    DebateRound,
    debate_report_id,
)

DEFAULT_DEBATE_ROUNDS = 2


class ResearchDebateService:
    model_version = "research_debate_rules_v1"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.bull_researcher = BullResearcherAgent()
        self.bear_researcher = BearResearcherAgent()
        self.research_manager = ResearchManagerAgent()

    def run(
        self,
        *,
        symbol: str,
        run_id: str = DEFAULT_ANALYST_RUN_ID,
        rounds_requested: int = DEFAULT_DEBATE_ROUNDS,
    ) -> DebateReport:
        if rounds_requested < 1 or rounds_requested > 10:
            raise ValueError("Debate rounds must be between 1 and 10.")

        symbol = symbol.upper()
        if InstrumentRepository(self.session).get(symbol) is None:
            raise ValueError(f"Instrument {symbol} is not available. Run make seed-mock first.")

        reports = self._load_reports(symbol=symbol, run_id=run_id)
        bull_thesis = self.bull_researcher.run(symbol=symbol, reports=reports)
        bear_thesis = self.bear_researcher.run(symbol=symbol, reports=reports)
        rounds = self._build_rounds(
            symbol=symbol,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            rounds_requested=rounds_requested,
        )
        manager_summary = self.research_manager.run(
            symbol=symbol,
            reports=reports,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            rounds=rounds,
        )
        source_report_ids = sorted(report.report_id for report in reports)
        debate = DebateReport(
            debate_id=debate_report_id(
                run_id=run_id,
                symbol=symbol,
                rounds_requested=rounds_requested,
                source_report_ids=source_report_ids,
            ),
            run_id=run_id,
            symbol=symbol,
            as_of=_latest_as_of(reports),
            rounds_requested=rounds_requested,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            rounds=rounds,
            manager_summary=manager_summary,
            source_report_ids=source_report_ids,
            model_version=self.model_version,
        )
        ResearchRepository(self.session).replace_debate_for_run_symbol(debate)
        self.session.commit()
        return debate

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

    def _build_rounds(
        self,
        *,
        symbol: str,
        bull_thesis,
        bear_thesis,
        rounds_requested: int,
    ) -> list[DebateRound]:
        rounds: list[DebateRound] = []
        for round_number in range(1, rounds_requested + 1):
            bull_point = bull_thesis.key_points[(round_number - 1) % len(bull_thesis.key_points)]
            bear_point = bear_thesis.key_points[(round_number - 1) % len(bear_thesis.key_points)]
            condition = bull_thesis.conditions[(round_number - 1) % len(bull_thesis.conditions)]
            risk_flag = bear_thesis.risk_flags[(round_number - 1) % len(bear_thesis.risk_flags)]
            rounds.append(
                DebateRound(
                    round_number=round_number,
                    bull_argument=f"{symbol} bull case round {round_number}: {bull_point} Condition: {condition}",
                    bear_argument=f"{symbol} bear case round {round_number}: {bear_point} Risk flag: {risk_flag}",
                    manager_note=(
                        "Manager note: weigh upside evidence against risk flags; "
                        "this transcript is research only and cannot create orders."
                    ),
                )
            )
        return rounds


def _latest_as_of(reports: list[AnalystReport]) -> datetime:
    return max((_as_utc(report.as_of) for report in reports))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
