from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import IntelligenceRepository, InstrumentRepository
from taurus_core.intelligence.event_scoring import EVENT_SENTIMENT
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.schemas import (
    HardRuleResult,
    RiskReviewStatus,
)

SCORE_QUANT = Decimal("0.0001")
SEVERE_NEGATIVE_EVENT_THRESHOLD = Decimal("0.55")
STALE_DATA_MAX_AGE_DAYS = 730


class RiskEngineResult:
    def __init__(
        self,
        *,
        status: RiskReviewStatus,
        approved_position_pct_nav: Decimal,
        hard_rule_results: list[HardRuleResult],
    ) -> None:
        self.status = status
        self.approved_position_pct_nav = approved_position_pct_nav
        self.hard_rule_results = hard_rule_results


class RiskEngine:
    model_version = "risk_engine_rules_v1"

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        kill_switch_enabled: bool | None = None,
        current_open_positions: int = 0,
        daily_loss_pct: Decimal = Decimal("0"),
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.kill_switch_enabled = (
            self.settings.taurus_kill_switch_enabled
            if kill_switch_enabled is None
            else kill_switch_enabled
        )
        self.current_open_positions = current_open_positions
        self.daily_loss_pct = daily_loss_pct

    def evaluate(
        self,
        *,
        proposal: TraderProposal,
        decision_id: str,
        risk_check_id: str,
    ) -> RiskEngineResult:
        symbol = proposal.symbol.upper()
        approved_position = proposal.requested_position_pct_nav.quantize(SCORE_QUANT)
        results: list[HardRuleResult] = []

        live_safe = (
            self.settings.live_trading_enabled is False
            and self.settings.broker_provider == "paper"
            and self.settings.taurus_mode in {"paper", "backtest"}
        )
        results.append(
            HardRuleResult(
                rule="live_trading_disabled",
                status="passed" if live_safe else "blocked",
                details=(
                    "Live trading is disabled and broker provider is paper."
                    if live_safe
                    else "Live trading or broker settings are not paper-safe."
                ),
            )
        )

        kill_switch_clear = not self.kill_switch_enabled
        results.append(
            HardRuleResult(
                rule="kill_switch",
                status="passed" if kill_switch_clear else "blocked",
                details=(
                    "Kill switch is clear."
                    if kill_switch_clear
                    else "Kill switch is enabled; no order may be considered."
                ),
            )
        )

        instrument = InstrumentRepository(self.session).get(symbol)
        instrument_supported = instrument is not None and instrument.active
        results.append(
            HardRuleResult(
                rule="supported_instrument",
                status="passed" if instrument_supported else "rejected",
                details=(
                    f"{symbol} is an active instrument."
                    if instrument_supported
                    else f"{symbol} is not an active supported instrument."
                ),
            )
        )

        trace_ok = bool(decision_id and proposal.proposal_id and risk_check_id)
        results.append(
            HardRuleResult(
                rule="required_trace_ids",
                status="passed" if trace_ok else "rejected",
                details=(
                    "Decision, proposal, and risk check IDs are present."
                    if trace_ok
                    else "Decision, proposal, and risk check IDs are required before risk approval."
                ),
            )
        )

        max_position = Decimal(str(self.settings.taurus_max_position_pct)).quantize(SCORE_QUANT)
        if approved_position > max_position:
            results.append(
                HardRuleResult(
                    rule="max_position_pct",
                    status="reduced",
                    details=f"{approved_position} reduced to configured cap {max_position}.",
                )
            )
            approved_position = max_position
        else:
            results.append(
                HardRuleResult(
                    rule="max_position_pct",
                    status="passed",
                    details=f"{approved_position} is within configured cap {max_position}.",
                )
            )

        max_open_positions = self.settings.taurus_max_open_positions
        open_positions_ok = (
            proposal.action != "BUY"
            or approved_position == 0
            or self.current_open_positions < max_open_positions
        )
        results.append(
            HardRuleResult(
                rule="max_open_positions",
                status="passed" if open_positions_ok else "rejected",
                details=(
                    f"Open positions {self.current_open_positions} below cap {max_open_positions}."
                    if open_positions_ok
                    else f"Open positions {self.current_open_positions} at cap {max_open_positions}."
                ),
            )
        )

        max_daily_loss = self.settings.taurus_max_daily_loss_pct
        daily_loss_ok = self.daily_loss_pct < max_daily_loss
        results.append(
            HardRuleResult(
                rule="max_daily_loss_pct",
                status="passed" if daily_loss_ok else "blocked",
                details=(
                    f"Daily loss {self.daily_loss_pct} is below cap {max_daily_loss}."
                    if daily_loss_ok
                    else f"Daily loss {self.daily_loss_pct} breached cap {max_daily_loss}."
                ),
            )
        )

        stale_data_ok = self._data_is_fresh_enough(proposal)
        results.append(
            HardRuleResult(
                rule="stale_data",
                status="passed" if stale_data_ok else "rejected",
                details=(
                    "Proposal source data is within the mock-mode freshness window."
                    if stale_data_ok
                    else "Proposal source data is too old for approval."
                ),
            )
        )

        severe_event = self._severe_negative_event(symbol=symbol)
        severe_event_ok = proposal.action != "BUY" or severe_event is None
        results.append(
            HardRuleResult(
                rule="severe_event_block",
                status="passed" if severe_event_ok else "blocked",
                details=(
                    "No severe negative event blocks a long entry."
                    if severe_event_ok
                    else f"Blocked by {severe_event.event_type}: {severe_event.headline}"
                ),
            )
        )

        if proposal.action != "BUY":
            approved_position = Decimal("0.0000")
            results.append(
                HardRuleResult(
                    rule="action_requires_long_entry",
                    status="rejected",
                    details=f"Trader action {proposal.action} does not request a long entry.",
                )
            )
        else:
            results.append(
                HardRuleResult(
                    rule="action_requires_long_entry",
                    status="passed",
                    details="Trader action requests a paper long entry only after final approval.",
                )
            )

        hard_statuses = [result.status for result in results]
        if "blocked" in hard_statuses:
            return RiskEngineResult(
                status="BLOCKED",
                approved_position_pct_nav=Decimal("0.0000"),
                hard_rule_results=results,
            )
        if "rejected" in hard_statuses:
            return RiskEngineResult(
                status="REJECTED",
                approved_position_pct_nav=Decimal("0.0000"),
                hard_rule_results=results,
            )
        if "reduced" in hard_statuses:
            return RiskEngineResult(
                status="APPROVED_WITH_REDUCTION",
                approved_position_pct_nav=approved_position.quantize(SCORE_QUANT),
                hard_rule_results=results,
            )
        return RiskEngineResult(
            status="APPROVED",
            approved_position_pct_nav=approved_position.quantize(SCORE_QUANT),
            hard_rule_results=results,
        )

    def _data_is_fresh_enough(self, proposal: TraderProposal) -> bool:
        if not proposal.source_report_ids:
            return False
        as_of = proposal.as_of
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - as_of).days <= STALE_DATA_MAX_AGE_DAYS

    def _severe_negative_event(self, *, symbol: str):
        events = IntelligenceRepository(self.session).list_events(symbol=symbol, limit=20)
        severe_events = []
        for event in events:
            sentiment = EVENT_SENTIMENT.get(event.event_type, Decimal("0"))
            if sentiment < 0 and event.severity >= SEVERE_NEGATIVE_EVENT_THRESHOLD:
                severe_events.append(event)
        if not severe_events:
            return None
        return sorted(
            severe_events,
            key=lambda event: (event.event_time, event.severity, event.event_id),
            reverse=True,
        )[0]
