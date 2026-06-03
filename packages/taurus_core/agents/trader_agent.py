from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.agents.schemas import AnalystReport, ReportHorizon
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import (
    AnalystReportRepository,
    CandleRepository,
    ExecutionRepository,
    ResearchRepository,
)
from taurus_core.execution.schemas import PaperAccount, PaperPosition
from taurus_core.llm import LLMProvider, LLMProviderError
from taurus_core.llm.base import LLMTraderOutput, normalize_llm_model_version
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.research.schemas import (
    DebateReport,
    LifecycleTrigger,
    TraderAction,
    TraderOrderType,
    TraderProposal,
    trader_proposal_id,
)

SCORE_QUANT = Decimal("0.0001")
STOP_LOSS_PCT = Decimal("6.0000")
TAKE_PROFIT_PCT = Decimal("12.0000")


@dataclass(slots=True, frozen=True)
class _PortfolioContext:
    portfolio_id: str
    account: PaperAccount | None
    position: PaperPosition | None
    latest_close_inr: Decimal
    current_quantity: int
    average_cost_inr: Decimal
    market_value_inr: Decimal
    current_position_pct_nav: Decimal
    unrealized_pnl_inr: Decimal


@dataclass(slots=True, frozen=True)
class _ProposalDecision:
    action: TraderAction
    confidence: Decimal
    target_position_pct_nav: Decimal
    lifecycle_trigger: LifecycleTrigger
    reason_summary: str
    invalid_if: list[str]
    position_management_summary: str
    model_version: str


class TraderAgent:
    agent_name = "TraderAgent"
    model_version = "trader_position_lifecycle_v1"

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        llm_provider: LLMProvider | None = None,
        max_requested_position_pct_nav: Decimal = Decimal("5.0"),
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.llm_provider = llm_provider
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

        portfolio = self._portfolio_context(symbol=symbol)
        fallback = self._deterministic_decision(
            reports=reports,
            debate=debate,
            portfolio=portfolio,
        )
        allowed_actions = self._allowed_actions(
            trigger=fallback.lifecycle_trigger,
            debate=debate,
            portfolio=portfolio,
        )
        decision = self._advisory_llm_decision(
            reports=reports,
            debate=debate,
            portfolio=portfolio,
            allowed_actions=allowed_actions,
            fallback=fallback,
        )
        order_type = self._order_type(decision.action)
        source_report_ids = sorted(report.report_id for report in reports)
        proposal = TraderProposal(
            proposal_id=trader_proposal_id(
                run_id=run_id,
                symbol=symbol,
                debate_id=debate.debate_id,
                source_report_ids=source_report_ids,
            ),
            run_id=run_id,
            portfolio_id=portfolio.portfolio_id,
            symbol=symbol,
            debate_id=debate.debate_id,
            as_of=debate.as_of,
            action=decision.action,
            confidence=decision.confidence,
            horizon=self._horizon(reports),
            requested_position_pct_nav=decision.target_position_pct_nav,
            current_position_quantity=portfolio.current_quantity,
            current_position_pct_nav=portfolio.current_position_pct_nav,
            target_position_pct_nav=decision.target_position_pct_nav,
            lifecycle_trigger=decision.lifecycle_trigger,
            evaluation_mode="after_close",
            order_type=order_type,
            entry_rule=self._entry_rule(decision.action, order_type),
            stop_loss_pct=STOP_LOSS_PCT,
            take_profit_pct=TAKE_PROFIT_PCT,
            reason_summary=decision.reason_summary,
            invalid_if=decision.invalid_if,
            position_management_summary=decision.position_management_summary,
            source_report_ids=source_report_ids,
            is_order=False,
            requires_risk_approval=True,
            model_version=decision.model_version,
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
                portfolio_id=proposal.portfolio_id,
                action=proposal.action,
                lifecycle_trigger=proposal.lifecycle_trigger,
                current_position_quantity=proposal.current_position_quantity,
                target_position_pct_nav=str(proposal.target_position_pct_nav),
                is_order=proposal.is_order,
            )
        return proposal

    def run_market_hours_trigger(
        self,
        *,
        symbol: str,
        run_id: str,
        base_proposal: TraderProposal,
        latest_price_inr: Decimal,
        stop_loss_price_inr: Decimal,
        take_profit_price_inr: Decimal,
        trigger: LifecycleTrigger,
        trigger_threshold_price_inr: Decimal,
        market_session_date: str,
        quote_snapshot_id: int | None,
        quote_snapshot: dict[str, object],
        as_of: datetime | None = None,
    ) -> TraderProposal:
        symbol = symbol.upper()
        if trigger not in {"stop_loss", "take_profit"}:
            raise ValueError("Market-hours monitor supports only stop_loss or take_profit triggers.")
        if base_proposal.symbol != symbol:
            raise ValueError("Base proposal symbol does not match market-hours trigger symbol.")

        reports = self._load_reports(symbol=symbol, run_id=base_proposal.run_id)
        debate = self._load_debate_by_id(base_proposal.debate_id)
        portfolio = self._portfolio_context(symbol=symbol, latest_price_inr=latest_price_inr)
        action = "EXIT" if trigger == "stop_loss" else "REDUCE"
        target = self._target_for_action(action=action, debate=debate, portfolio=portfolio)
        fallback = _ProposalDecision(
            action=action,
            confidence=base_proposal.confidence,
            target_position_pct_nav=target,
            lifecycle_trigger=trigger,
            reason_summary=(
                f"Market-hours monitor detected {trigger.replace('_', ' ')} for {symbol}: "
                f"latest quote {latest_price_inr} crossed threshold "
                f"{trigger_threshold_price_inr}."
            ),
            invalid_if=[
                "Risk committee rejects or resizes the market-hours lifecycle proposal.",
                "Paper-safe broker settings change before execution.",
                "Quote snapshot is superseded before final approval.",
            ],
            position_management_summary=(
                f"Market-hours threshold monitor selected {action} for {trigger}; "
                f"latest quote {latest_price_inr}, stop-loss {stop_loss_price_inr}, "
                f"take-profit {take_profit_price_inr}, current exposure "
                f"{portfolio.current_position_pct_nav}% NAV, target {target}% NAV."
            ),
            model_version=f"{self.model_version}:market_hours_deterministic",
        )
        allowed_actions = self._allowed_actions(
            trigger=trigger,
            debate=debate,
            portfolio=portfolio,
        )
        decision = self._advisory_llm_decision(
            reports=reports,
            debate=debate,
            portfolio=portfolio,
            allowed_actions=allowed_actions,
            fallback=fallback,
            evaluation_mode="market_hours",
            market_hours_context={
                "market_session_date": market_session_date,
                "quote_snapshot_id": quote_snapshot_id,
                "quote_snapshot": quote_snapshot,
                "latest_price_inr": str(latest_price_inr),
                "stop_loss_price_inr": str(stop_loss_price_inr),
                "take_profit_price_inr": str(take_profit_price_inr),
                "trigger_threshold_price_inr": str(trigger_threshold_price_inr),
            },
        )
        source_report_ids = list(base_proposal.source_report_ids)
        order_type = self._order_type(decision.action)
        proposal = TraderProposal(
            proposal_id=trader_proposal_id(
                run_id=run_id,
                symbol=symbol,
                debate_id=base_proposal.debate_id,
                source_report_ids=source_report_ids,
            ),
            run_id=run_id,
            portfolio_id=portfolio.portfolio_id,
            symbol=symbol,
            debate_id=base_proposal.debate_id,
            as_of=as_of or debate.as_of,
            action=decision.action,
            confidence=decision.confidence,
            horizon=base_proposal.horizon,
            requested_position_pct_nav=decision.target_position_pct_nav,
            current_position_quantity=portfolio.current_quantity,
            current_position_pct_nav=portfolio.current_position_pct_nav,
            target_position_pct_nav=decision.target_position_pct_nav,
            lifecycle_trigger=decision.lifecycle_trigger,
            evaluation_mode="market_hours",
            market_session_date=market_session_date,
            quote_snapshot_id=quote_snapshot_id,
            quote_snapshot=quote_snapshot,
            latest_price_inr=latest_price_inr,
            stop_loss_price_inr=stop_loss_price_inr,
            take_profit_price_inr=take_profit_price_inr,
            trigger_threshold_price_inr=trigger_threshold_price_inr,
            trigger_evidence={
                "trigger": trigger,
                "latest_price_inr": str(latest_price_inr),
                "threshold_price_inr": str(trigger_threshold_price_inr),
                "market_session_date": market_session_date,
            },
            order_type=order_type,
            entry_rule=self._entry_rule(decision.action, order_type),
            stop_loss_pct=base_proposal.stop_loss_pct,
            take_profit_pct=base_proposal.take_profit_pct,
            reason_summary=decision.reason_summary,
            invalid_if=decision.invalid_if,
            position_management_summary=decision.position_management_summary,
            source_report_ids=source_report_ids,
            is_order=False,
            requires_risk_approval=True,
            model_version=decision.model_version,
        )
        ResearchRepository(self.session).replace_trader_proposal_for_run_symbol(proposal)
        self.session.commit()
        with bound_trace_context(
            run_id=run_id,
            debate_id=base_proposal.debate_id,
            proposal_id=proposal.proposal_id,
        ):
            get_logger(__name__).info(
                "trader.market_hours_proposal.created",
                symbol=symbol,
                portfolio_id=proposal.portfolio_id,
                action=proposal.action,
                lifecycle_trigger=proposal.lifecycle_trigger,
                latest_price_inr=str(latest_price_inr),
                trigger_threshold_price_inr=str(trigger_threshold_price_inr),
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
                "Run analyst reports before trader proposal."
            )
        return [AnalystReport.model_validate(row.payload) for row in rows]

    def _load_debate(self, *, symbol: str, run_id: str) -> DebateReport:
        model = ResearchRepository(self.session).latest_debate(symbol=symbol, run_id=run_id)
        if model is None:
            raise ValueError(
                f"No debate found for {symbol} run_id={run_id}. Run debate before trader proposal."
            )
        return DebateReport.model_validate(model.payload)

    def _load_debate_by_id(self, debate_id: str) -> DebateReport:
        model = ResearchRepository(self.session).get_debate(debate_id)
        if model is None:
            raise ValueError(f"No debate found for debate_id={debate_id}.")
        return DebateReport.model_validate(model.payload)

    def _portfolio_context(
        self,
        *,
        symbol: str,
        latest_price_inr: Decimal | None = None,
    ) -> _PortfolioContext:
        portfolio_id = self.settings.taurus_paper_portfolio_id
        execution_repo = ExecutionRepository(self.session)
        account_model = execution_repo.latest_account_by_portfolio(portfolio_id=portfolio_id)
        account = PaperAccount.model_validate(account_model.payload) if account_model else None
        position_model = execution_repo.latest_open_position_by_portfolio_symbol(
            portfolio_id=portfolio_id,
            symbol=symbol,
        )
        position = PaperPosition.model_validate(position_model.payload) if position_model else None
        latest_close = (
            latest_price_inr.quantize(SCORE_QUANT)
            if latest_price_inr is not None
            else self._latest_close(symbol=symbol)
        )
        quantity = position.quantity if position is not None else 0
        market_value = (
            _quantize_money(latest_close * Decimal(quantity))
            if quantity > 0 and latest_close > 0
            else Decimal("0.0000")
        )
        current_pct = Decimal("0.0000")
        equity = account.equity_inr if account is not None else Decimal("0")
        if equity > 0 and market_value > 0:
            current_pct = ((market_value / equity) * Decimal("100")).quantize(SCORE_QUANT)
        average_cost = position.average_cost_inr if position is not None else Decimal("0.0000")
        unrealized = (
            _quantize_money((latest_close - average_cost) * Decimal(quantity))
            if quantity > 0 and latest_close > 0 and average_cost > 0
            else Decimal("0.0000")
        )
        return _PortfolioContext(
            portfolio_id=portfolio_id,
            account=account,
            position=position,
            latest_close_inr=latest_close,
            current_quantity=quantity,
            average_cost_inr=average_cost,
            market_value_inr=market_value,
            current_position_pct_nav=current_pct,
            unrealized_pnl_inr=unrealized,
        )

    def _latest_close(self, *, symbol: str) -> Decimal:
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(symbol=symbol)
        if not candles:
            return Decimal("0.0000")
        return candles[-1].close.quantize(SCORE_QUANT)

    def _deterministic_decision(
        self,
        *,
        reports: list[AnalystReport],
        debate: DebateReport,
        portfolio: _PortfolioContext,
    ) -> _ProposalDecision:
        trigger = self._lifecycle_trigger(debate=debate, portfolio=portfolio)
        action = self._deterministic_action(trigger=trigger, debate=debate, portfolio=portfolio)
        target = self._target_for_action(action=action, debate=debate, portfolio=portfolio)
        confidence = self._confidence(reports, debate)
        reason_summary = self._reason_summary(debate=debate, action=action, trigger=trigger)
        invalid_if = self._invalid_if(debate)
        return _ProposalDecision(
            action=action,
            confidence=confidence,
            target_position_pct_nav=target,
            lifecycle_trigger=trigger,
            reason_summary=reason_summary,
            invalid_if=invalid_if,
            position_management_summary=(
                f"Deterministic lifecycle baseline selected {action} for {trigger}; "
                f"current exposure {portfolio.current_position_pct_nav}% NAV, "
                f"target exposure {target}% NAV."
            ),
            model_version=f"{self.model_version}:deterministic",
        )

    def _lifecycle_trigger(
        self,
        *,
        debate: DebateReport,
        portfolio: _PortfolioContext,
    ) -> LifecycleTrigger:
        if portfolio.current_quantity <= 0:
            return "new_entry"
        if portfolio.average_cost_inr > 0 and portfolio.latest_close_inr > 0:
            pnl_pct = (
                (portfolio.latest_close_inr - portfolio.average_cost_inr)
                / portfolio.average_cost_inr
                * Decimal("100")
            )
            if pnl_pct <= -STOP_LOSS_PCT:
                return "stop_loss"
            if pnl_pct >= TAKE_PROFIT_PCT:
                return "take_profit"
        label = debate.manager_summary.consensus_label
        if label == "bearish":
            return "thesis_invalidated"
        if label == "mild_bearish":
            return "thesis_weakened"
        return "hold_review"

    def _deterministic_action(
        self,
        *,
        trigger: LifecycleTrigger,
        debate: DebateReport,
        portfolio: _PortfolioContext,
    ) -> TraderAction:
        if trigger == "new_entry":
            return self._new_entry_action(debate)
        if trigger == "stop_loss":
            return "EXIT"
        if trigger == "take_profit":
            return "REDUCE"
        if trigger == "thesis_invalidated":
            return "EXIT"
        if trigger == "thesis_weakened":
            return "REDUCE"

        desired = self._new_entry_target(debate)
        if (
            debate.manager_summary.consensus_label in {"bullish", "mild_bullish"}
            and debate.manager_summary.consensus_score >= Decimal("0.15")
            and desired > portfolio.current_position_pct_nav
        ):
            return "BUY"
        return "HOLD"

    def _new_entry_action(self, debate: DebateReport) -> TraderAction:
        label = debate.manager_summary.consensus_label
        score = debate.manager_summary.consensus_score
        if label in {"bullish", "mild_bullish"} and score >= Decimal("0.15"):
            return "BUY"
        return "NO_TRADE"

    def _target_for_action(
        self,
        *,
        action: TraderAction,
        debate: DebateReport,
        portfolio: _PortfolioContext,
    ) -> Decimal:
        if action == "BUY":
            return max(portfolio.current_position_pct_nav, self._new_entry_target(debate))
        if action == "HOLD":
            return portfolio.current_position_pct_nav.quantize(SCORE_QUANT)
        if action == "REDUCE":
            return _reduced_target(portfolio.current_position_pct_nav)
        return Decimal("0.0000")

    def _new_entry_target(self, debate: DebateReport) -> Decimal:
        raw_position = max(
            Decimal("1.0000"),
            abs(debate.manager_summary.consensus_score) * Decimal("10"),
        )
        return min(self.max_requested_position_pct_nav, raw_position).quantize(SCORE_QUANT)

    def _allowed_actions(
        self,
        *,
        trigger: LifecycleTrigger,
        debate: DebateReport,
        portfolio: _PortfolioContext,
    ) -> tuple[TraderAction, ...]:
        if trigger == "stop_loss":
            return ("EXIT",)
        if trigger == "take_profit":
            return ("REDUCE", "EXIT")
        if portfolio.current_quantity <= 0:
            return ("BUY", "NO_TRADE")
        if trigger in {"thesis_weakened", "thesis_invalidated"}:
            return ("REDUCE", "EXIT")
        if debate.manager_summary.consensus_label == "neutral":
            return ("HOLD", "REDUCE", "EXIT")
        if debate.manager_summary.consensus_label in {"bullish", "mild_bullish"}:
            return ("HOLD", "BUY")
        return ("HOLD", "REDUCE", "EXIT")

    def _advisory_llm_decision(
        self,
        *,
        reports: list[AnalystReport],
        debate: DebateReport,
        portfolio: _PortfolioContext,
        allowed_actions: tuple[TraderAction, ...],
        fallback: _ProposalDecision,
        evaluation_mode: str = "after_close",
        market_hours_context: dict[str, object] | None = None,
    ) -> _ProposalDecision:
        if self.llm_provider is None:
            return self._fallback_decision(
                fallback,
                "No LLM provider was supplied; deterministic lifecycle fallback used.",
            )
        try:
            output = self.llm_provider.complete_trader_proposal(
                agent_name=self.agent_name,
                symbol=debate.symbol,
                context=self._llm_context(
                    reports=reports,
                    debate=debate,
                    portfolio=portfolio,
                    allowed_actions=allowed_actions,
                    fallback=fallback,
                    evaluation_mode=evaluation_mode,
                    market_hours_context=market_hours_context,
                ),
            )
        except (LLMProviderError, ValueError) as exc:
            return self._fallback_decision(
                fallback,
                f"LLM trader output unavailable or invalid; deterministic fallback used: {exc}.",
            )
        return self._validated_llm_decision(
            output=output,
            allowed_actions=allowed_actions,
            portfolio=portfolio,
            fallback=fallback,
        )

    def _validated_llm_decision(
        self,
        *,
        output: LLMTraderOutput,
        allowed_actions: tuple[TraderAction, ...],
        portfolio: _PortfolioContext,
        fallback: _ProposalDecision,
    ) -> _ProposalDecision:
        action = cast(TraderAction, output.action)
        if action not in allowed_actions:
            return self._fallback_decision(
                fallback,
                f"LLM recommended {action}, outside allowed actions {list(allowed_actions)}.",
            )
        target = output.target_position_pct_nav.quantize(SCORE_QUANT)
        if not self._target_is_valid(action=action, target=target, portfolio=portfolio):
            return self._fallback_decision(
                fallback,
                f"LLM target {target}% NAV is invalid for {action}; deterministic fallback used.",
            )
        target = self._clamped_target(action=action, target=target, portfolio=portfolio)
        if action == "BUY" and target <= portfolio.current_position_pct_nav:
            return self._fallback_decision(
                fallback,
                f"LLM target clamps to {target}% NAV, which would not increase exposure.",
            )
        output_model_version = normalize_llm_model_version(
            output.model_version,
            fallback_model_version=getattr(
                self.llm_provider,
                "model_version",
                output.model_version,
            ),
        )
        return _ProposalDecision(
            action=action,
            confidence=output.confidence.quantize(SCORE_QUANT),
            target_position_pct_nav=target,
            lifecycle_trigger=fallback.lifecycle_trigger,
            reason_summary=_bounded_text(output.reason_summary, fallback.reason_summary),
            invalid_if=self._validated_invalid_if(output.invalid_if, fallback.invalid_if),
            position_management_summary=(
                "LLM advisory accepted within deterministic lifecycle envelope. "
                + _bounded_text(
                    output.position_management_summary,
                    fallback.position_management_summary,
                )
            ),
            model_version=f"{self.model_version}:{output_model_version}",
        )

    def _target_is_valid(
        self,
        *,
        action: TraderAction,
        target: Decimal,
        portfolio: _PortfolioContext,
    ) -> bool:
        current = portfolio.current_position_pct_nav
        if action == "BUY":
            return target > current and target > Decimal("0")
        if action == "REDUCE":
            return portfolio.current_quantity > 0 and Decimal("0") < target < current
        if action == "EXIT":
            return portfolio.current_quantity > 0 and target == Decimal("0.0000")
        if action == "HOLD":
            return portfolio.current_quantity > 0
        if action == "NO_TRADE":
            return portfolio.current_quantity == 0
        return False

    def _clamped_target(
        self,
        *,
        action: TraderAction,
        target: Decimal,
        portfolio: _PortfolioContext,
    ) -> Decimal:
        if action == "BUY":
            return min(self.max_requested_position_pct_nav, target).quantize(SCORE_QUANT)
        if action == "HOLD":
            return portfolio.current_position_pct_nav.quantize(SCORE_QUANT)
        if action == "EXIT":
            return Decimal("0.0000")
        if action == "NO_TRADE":
            return Decimal("0.0000")
        return min(target, _reduced_target(portfolio.current_position_pct_nav)).quantize(
            SCORE_QUANT
        )

    def _fallback_decision(self, fallback: _ProposalDecision, reason: str) -> _ProposalDecision:
        return _ProposalDecision(
            action=fallback.action,
            confidence=fallback.confidence,
            target_position_pct_nav=fallback.target_position_pct_nav,
            lifecycle_trigger=fallback.lifecycle_trigger,
            reason_summary=fallback.reason_summary,
            invalid_if=fallback.invalid_if,
            position_management_summary=(
                f"{fallback.position_management_summary} Fallback note: {reason}"
            ),
            model_version=f"{self.model_version}:deterministic_fallback",
        )

    def _llm_context(
        self,
        *,
        reports: list[AnalystReport],
        debate: DebateReport,
        portfolio: _PortfolioContext,
        allowed_actions: tuple[TraderAction, ...],
        fallback: _ProposalDecision,
        evaluation_mode: str = "after_close",
        market_hours_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        context: dict[str, Any] = {
            "portfolio_id": portfolio.portfolio_id,
            "evaluation_mode": evaluation_mode,
            "lifecycle_trigger": fallback.lifecycle_trigger,
            "allowed_actions": list(allowed_actions),
            "target_position_bounds": {
                "min_pct_nav": "0.0000",
                "max_pct_nav": str(self.max_requested_position_pct_nav),
            },
            "paper_portfolio_context": {
                "latest_equity_inr": str(portfolio.account.equity_inr)
                if portfolio.account is not None
                else None,
                "latest_close_inr": str(portfolio.latest_close_inr),
                "current_quantity": portfolio.current_quantity,
                "average_cost_inr": str(portfolio.average_cost_inr),
                "market_value_inr": str(portfolio.market_value_inr),
                "current_position_pct_nav": str(portfolio.current_position_pct_nav),
                "unrealized_pnl_inr": str(portfolio.unrealized_pnl_inr),
            },
            "risk_defaults": {
                "stop_loss_pct": str(STOP_LOSS_PCT),
                "take_profit_pct": str(TAKE_PROFIT_PCT),
            },
            "research_consensus": debate.manager_summary.model_dump(mode="json"),
            "debate": debate.model_dump(mode="json"),
            "analyst_reports": [report.model_dump(mode="json") for report in reports],
            "deterministic_fallback": {
                "action": fallback.action,
                "confidence": str(fallback.confidence),
                "target_position_pct_nav": str(fallback.target_position_pct_nav),
                "stop_loss_pct": str(STOP_LOSS_PCT),
                "take_profit_pct": str(TAKE_PROFIT_PCT),
                "reason_summary": fallback.reason_summary,
                "invalid_if": list(fallback.invalid_if),
                "position_management_summary": fallback.position_management_summary,
            },
        }
        if market_hours_context is not None:
            context["market_hours_trigger"] = market_hours_context
        return context

    def _order_type(self, action: TraderAction) -> TraderOrderType:
        if action in {"BUY", "SELL", "REDUCE", "EXIT"}:
            return "LIMIT"
        return "NONE"

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
        if action in {"HOLD", "NO_TRADE"}:
            return "No paper order expected for approved no-action lifecycle decision."
        if action in {"REDUCE", "EXIT"}:
            return (
                f"Paper sell-side {order_type} intent only after deterministic risk "
                "approval and final portfolio-manager approval."
            )
        return (
            f"Paper {order_type} buy intent only after deterministic risk approval "
            "and final portfolio-manager approval."
        )

    def _reason_summary(
        self,
        *,
        debate: DebateReport,
        action: TraderAction,
        trigger: LifecycleTrigger,
    ) -> str:
        summary = debate.manager_summary
        return (
            f"Trader lifecycle proposal {action} follows {trigger} after "
            f"{summary.consensus_label.replace('_', ' ')} research consensus "
            f"with score {summary.consensus_score}: {summary.summary}"
        )

    def _invalid_if(self, debate: DebateReport) -> list[str]:
        invalidation = [
            "Risk committee rejects or resizes the proposal.",
            "Live trading flag or broker provider is changed away from paper-safe defaults.",
            "New severe negative event arrives before final approval.",
        ]
        invalidation.extend(debate.manager_summary.unresolved_uncertainties[:2])
        return invalidation[:5]

    def _validated_invalid_if(self, llm_items: list[str], fallback_items: list[str]) -> list[str]:
        cleaned = [item.strip() for item in llm_items if item.strip()]
        merged = [*cleaned[:3], *fallback_items]
        deduped: list[str] = []
        for item in merged:
            if item not in deduped:
                deduped.append(item)
        return deduped[:5] or fallback_items


def _reduced_target(current_pct_nav: Decimal) -> Decimal:
    if current_pct_nav <= Decimal("0"):
        return Decimal("0.0000")
    return (current_pct_nav / Decimal("2")).quantize(SCORE_QUANT)


def _bounded_text(value: str, fallback: str, *, max_length: int = 900) -> str:
    cleaned = " ".join(str(value).split())
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_length]


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(SCORE_QUANT)
