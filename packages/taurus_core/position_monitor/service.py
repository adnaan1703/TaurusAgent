from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.alerts.service import AlertService
from taurus_core.alerts.templates import position_monitor_trigger_event
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.factory import build_market_data_provider
from taurus_core.db.models import AuditLogModel
from taurus_core.db.repositories import (
    ExecutionRepository,
    MarketPriceSnapshotRepository,
    PaperRunRepository,
    ResearchRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import MarketDataProviderError, MarketPriceSnapshot
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import PaperAccount, PaperPosition
from taurus_core.llm import LLMProvider, build_llm_provider
from taurus_core.logging import get_logger
from taurus_core.observability.metrics import (
    record_position_monitor_iteration,
    record_position_monitor_paper_route,
    record_position_monitor_proposal,
    record_position_monitor_quote_failure,
    record_position_monitor_trigger,
)
from taurus_core.paper_trading.schemas import PaperRun, PaperRunUniverse, paper_run_id
from taurus_core.research.schemas import LifecycleTrigger, TraderProposal
from taurus_core.risk.review_service import RiskReviewService

SCORE_QUANT = Decimal("0.0001")
MONITOR_SCHEDULE_NAME = "market_hours_position_monitor"


@dataclass(slots=True)
class PositionMonitorIterationResult:
    run_id: str | None
    status: str
    symbols_seen: list[str] = field(default_factory=list)
    proposals_created: int = 0
    triggers_detected: int = 0
    quote_failures: int = 0
    skipped: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class PositionMonitorService:
    """Polls open paper positions for quote-driven stop-loss/take-profit triggers."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        quote_provider: Any | None = None,
        llm_provider: LLMProvider | None = None,
        sleep_func: Any = time.sleep,
        now_func: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.quote_provider = quote_provider
        self.llm_provider = llm_provider
        self.sleep_func = sleep_func
        self.now_func = now_func or (lambda: datetime.now(timezone.utc))
        self.session_factory = build_session_factory(self.settings)
        self.logger = get_logger(__name__)

    def run(self) -> list[PositionMonitorIterationResult]:
        if not self.settings.taurus_position_monitor_enabled:
            self.logger.info("position_monitor.disabled")
            return []
        max_iterations = self.settings.taurus_position_monitor_max_iterations
        results: list[PositionMonitorIterationResult] = []
        iteration = 0
        while max_iterations == 0 or iteration < max_iterations:
            iteration += 1
            results.append(self.run_once())
            if max_iterations and iteration >= max_iterations:
                break
            self.sleep_func(self.settings.taurus_position_monitor_interval_seconds)
        return results

    def run_once(self) -> PositionMonitorIterationResult:
        self._validate_runtime()
        now = _as_utc(self.now_func())
        market_session_date = _market_session_date(now, self.settings.taurus_paper_timezone)
        if (
            self.settings.taurus_position_monitor_market_hours_only
            and not _is_market_hours(now, self.settings.taurus_paper_timezone)
        ):
            with self.session_factory() as session:
                self._audit(
                    session,
                    "position_monitor.trigger_skipped",
                    payload={
                        "run_id": None,
                        "symbols": [],
                        "market_session_date": market_session_date,
                        "reason": "market_closed",
                    },
                    note="Position monitor skipped because market-hours-only mode is enabled.",
                )
                session.commit()
            record_position_monitor_iteration(status="market_closed")
            return PositionMonitorIterationResult(run_id=None, status="MARKET_CLOSED")

        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            positions = [
                PaperPosition.model_validate(row.payload)
                for row in execution_repo.latest_open_positions_by_portfolio(
                    portfolio_id=self.settings.taurus_paper_portfolio_id,
                )
            ]
            symbols = sorted({position.symbol for position in positions if position.quantity > 0})
            run = self._new_run(now=now, symbols=symbols)
            PaperRunRepository(session).upsert(run)
            self._audit(
                session,
                "position_monitor.iteration_started",
                payload={
                    "run_id": run.run_id,
                    "portfolio_id": run.portfolio_id,
                    "symbols": symbols,
                    "market_session_date": market_session_date,
                    "provider": self.settings.taurus_position_monitor_provider,
                },
                note="Market-hours position monitor iteration started.",
            )
            session.commit()

        if not positions:
            with self.session_factory() as session:
                self._complete_run(
                    session,
                    run=run,
                    status="COMPLETED",
                    succeeded_symbols=[],
                    failed_symbols=[],
                    artifacts={"symbols": {}, "skipped": {"*": "no_open_positions"}},
                )
            record_position_monitor_iteration(status="no_open_positions")
            return PositionMonitorIterationResult(
                run_id=run.run_id,
                status="NO_OPEN_POSITIONS",
                symbols_seen=[],
                skipped={"*": "no_open_positions"},
            )

        llm_provider = self.llm_provider or build_llm_provider(self.settings)
        result = PositionMonitorIterationResult(
            run_id=run.run_id,
            status="COMPLETED",
            symbols_seen=symbols,
        )
        artifacts: dict[str, Any] = {"symbols": {}}
        succeeded: list[str] = []
        failed: list[str] = []
        provider = self._quote_provider()

        for position in positions:
            symbol = position.symbol
            try:
                symbol_artifact = self._evaluate_symbol(
                    symbol=symbol,
                    position=position,
                    run_id=run.run_id,
                    now=now,
                    market_session_date=market_session_date,
                    quote_provider=provider,
                    llm_provider=llm_provider,
                )
                artifacts["symbols"][symbol] = symbol_artifact
                if symbol_artifact.get("trigger") in {"stop_loss", "take_profit"}:
                    result.triggers_detected += 1
                if symbol_artifact.get("proposal_id"):
                    result.proposals_created += 1
                if symbol_artifact.get("quote_failure"):
                    result.quote_failures += 1
                if symbol_artifact.get("skipped_reason"):
                    result.skipped[symbol] = str(symbol_artifact["skipped_reason"])
                succeeded.append(symbol)
            except Exception as exc:
                failed.append(symbol)
                result.errors[symbol] = str(exc)
                artifacts["symbols"][symbol] = {"error": str(exc)}
                with self.session_factory() as session:
                    self._audit(
                        session,
                        "position_monitor.error",
                        payload={
                            "run_id": run.run_id,
                            "symbol": symbol,
                            "market_session_date": market_session_date,
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                        },
                        note="Position monitor symbol evaluation failed.",
                    )
                    session.commit()

        status = "PARTIAL_FAILED" if failed and succeeded else "FAILED" if failed else "COMPLETED"
        result.status = status
        with self.session_factory() as session:
            self._complete_run(
                session,
                run=run,
                status=status,
                succeeded_symbols=succeeded,
                failed_symbols=failed,
                artifacts=artifacts,
            )
        record_position_monitor_iteration(status=status.lower())
        return result

    def _evaluate_symbol(
        self,
        *,
        symbol: str,
        position: PaperPosition,
        run_id: str,
        now: datetime,
        market_session_date: str,
        quote_provider: Any,
        llm_provider: LLMProvider,
    ) -> dict[str, Any]:
        snapshot_model = None
        try:
            snapshots = quote_provider.get_latest_snapshots([symbol])
            if not snapshots:
                raise MarketDataProviderError(f"No latest quote snapshot returned for {symbol}.")
            snapshot = snapshots[0]
            with self.session_factory() as session:
                models = MarketPriceSnapshotRepository(session).insert_many([snapshot])
                snapshot_model = models[0]
                session.commit()
                snapshot_payload = _snapshot_payload(snapshot_model)
                self._audit(
                    session,
                    "position_monitor.quote_snapshot_received",
                    payload={
                        "run_id": run_id,
                        "symbol": symbol,
                        "quote_snapshot_id": snapshot_model.id,
                        "latest_price_inr": str(snapshot_model.last_price),
                        "market_session_date": market_session_date,
                    },
                    note="Latest Kite quote snapshot persisted for monitor evaluation.",
                )
                session.commit()
        except Exception as exc:
            record_position_monitor_quote_failure(
                provider=self.settings.taurus_position_monitor_provider,
                symbol=symbol,
            )
            with self.session_factory() as session:
                self._audit(
                    session,
                    "position_monitor.quote_fetch_failed",
                    payload={
                        "run_id": run_id,
                        "symbol": symbol,
                        "provider": self.settings.taurus_position_monitor_provider,
                        "market_session_date": market_session_date,
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    },
                    note="Quote retrieval failed; symbol skipped for this iteration.",
                )
                session.commit()
            return {"quote_failure": True, "skipped_reason": "quote_fetch_failed"}

        base_proposal = self._latest_base_proposal(symbol)
        if base_proposal is None:
            self._audit_skip(
                run_id=run_id,
                symbol=symbol,
                market_session_date=market_session_date,
                reason="missing_active_trade_thesis",
            )
            return {"skipped_reason": "missing_active_trade_thesis", "quote": snapshot_payload}

        trigger_data = _trigger_data(
            position=position,
            proposal=base_proposal,
            snapshot=snapshot,
        )
        if trigger_data["trigger"] is None:
            self._audit_skip(
                run_id=run_id,
                symbol=symbol,
                market_session_date=market_session_date,
                reason="no_threshold_crossed",
                payload=trigger_data,
            )
            return {"skipped_reason": "no_threshold_crossed", **trigger_data}

        trigger = str(trigger_data["trigger"])
        threshold = _decimal(trigger_data["trigger_threshold_price_inr"])
        if self._duplicate_trigger(
            symbol=symbol,
            trigger=trigger,
            threshold_price=threshold,
            market_session_date=market_session_date,
        ):
            self._audit_skip(
                run_id=run_id,
                symbol=symbol,
                market_session_date=market_session_date,
                reason="duplicate_trigger_same_market_session",
                payload=trigger_data,
            )
            return {
                "skipped_reason": "duplicate_trigger_same_market_session",
                **trigger_data,
            }

        with self.session_factory() as session:
            self._audit(
                session,
                "position_monitor.trigger_detected",
                payload={
                    "run_id": run_id,
                    "symbol": symbol,
                    "trigger": trigger,
                    "market_session_date": market_session_date,
                    **trigger_data,
                },
                note="Market-hours stop-loss/take-profit threshold crossed.",
            )
            session.commit()
            AlertService(session, self.settings).send(
                position_monitor_trigger_event(
                    run_id=run_id,
                    symbol=symbol,
                    trigger=trigger,
                    latest_price_inr=str(trigger_data["latest_price_inr"]),
                    threshold_price_inr=str(trigger_data["trigger_threshold_price_inr"]),
                    source_id=f"{symbol}:{trigger}:{market_session_date}",
                    created_at=now,
                    payload={
                        "quote_snapshot_id": snapshot_model.id if snapshot_model else None,
                        "market_session_date": market_session_date,
                        **trigger_data,
                    },
                )
            )
        record_position_monitor_trigger(trigger=trigger, symbol=symbol)

        with self.session_factory() as session:
            proposal = TraderAgent(session, self.settings, llm_provider=llm_provider).run_market_hours_trigger(
                symbol=symbol,
                run_id=run_id,
                base_proposal=base_proposal,
                latest_price_inr=_decimal(trigger_data["latest_price_inr"]),
                stop_loss_price_inr=_decimal(trigger_data["stop_loss_price_inr"]),
                take_profit_price_inr=_decimal(trigger_data["take_profit_price_inr"]),
                trigger=trigger,  # type: ignore[arg-type]
                trigger_threshold_price_inr=threshold,
                market_session_date=market_session_date,
                quote_snapshot_id=snapshot_model.id if snapshot_model else None,
                quote_snapshot=snapshot_payload,
                as_of=now,
            )
            self._audit(
                session,
                "position_monitor.proposal_created",
                payload={
                    "run_id": run_id,
                    "symbol": symbol,
                    "proposal_id": proposal.proposal_id,
                    "action": proposal.action,
                    "trigger": trigger,
                    "market_session_date": market_session_date,
                },
                note="Monitor-created TraderAgent lifecycle proposal stored.",
            )
            session.commit()
        record_position_monitor_proposal(
            trigger=trigger,
            action=proposal.action,
            symbol=symbol,
        )

        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            open_positions = execution_repo.latest_open_positions_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            account_model = execution_repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            account = PaperAccount.model_validate(account_model.payload) if account_model else None
            review = RiskReviewService(
                session,
                self.settings,
                current_open_positions=len(open_positions),
                current_position_exposures_pct_nav=_position_exposures_pct_nav(
                    positions=[
                        PaperPosition.model_validate(row.payload) for row in open_positions
                    ],
                    equity_inr=account.equity_inr if account is not None else None,
                ),
            ).run(symbol=symbol, run_id=run_id, proposal=proposal)

        with self.session_factory() as session:
            decision = PortfolioManagerAgent(
                session,
                self.settings,
                llm_provider=llm_provider,
            ).run(symbol=symbol, run_id=run_id, risk_review=review)

        with self.session_factory() as session:
            order = ExecutionRouter(session, self.settings).route_decision(
                decision,
                execution_policy="immediate",
            )
            order_status = order.status if order is not None else "not_routed"
            if decision.final_action in {"EXIT", "REDUCE"}:
                record_position_monitor_paper_route(
                    action=decision.final_action,
                    symbol=symbol,
                    order_status=order_status,
                )
            self._audit(
                session,
                "position_monitor.paper_route_completed",
                payload={
                    "run_id": run_id,
                    "symbol": symbol,
                    "trigger": trigger,
                    "proposal_id": proposal.proposal_id,
                    "risk_check_id": review.risk_check_id,
                    "final_decision_id": decision.final_decision_id,
                    "final_action": decision.final_action,
                    "final_status": decision.status,
                    "order_id": order.order_id if order is not None else None,
                    "order_status": order_status,
                    "market_session_date": market_session_date,
                },
                note="Monitor-generated decision flow reached PaperBroker routing boundary.",
            )
            session.commit()

        return {
            **trigger_data,
            "quote": snapshot_payload,
            "proposal_id": proposal.proposal_id,
            "proposal_action": proposal.action,
            "risk_check_id": review.risk_check_id,
            "final_decision_id": decision.final_decision_id,
            "final_status": decision.status,
            "final_action": decision.final_action,
            "order_id": order.order_id if order is not None else None,
            "order_status": order.status if order is not None else None,
        }

    def _validate_runtime(self) -> None:
        if self.settings.live_trading_enabled:
            raise ValueError("Position monitor cannot run while live trading is enabled.")
        if self.settings.broker_provider != "paper":
            raise ValueError("Position monitor requires BROKER_PROVIDER=paper.")
        if self.settings.taurus_mode != "paper":
            raise ValueError("Position monitor runs only in Taurus paper mode.")
        if self.settings.taurus_position_monitor_provider != "kite":
            raise ValueError("Position monitor currently supports only provider=kite.")

    def _quote_provider(self) -> Any:
        provider = self.quote_provider or build_market_data_provider(self.settings)
        if not hasattr(provider, "get_latest_snapshots"):
            raise MarketDataProviderError("Configured provider does not support latest quote snapshots.")
        return provider

    def _latest_base_proposal(self, symbol: str) -> TraderProposal | None:
        with self.session_factory() as session:
            rows = ResearchRepository(session).list_trader_proposals(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
                symbol=symbol,
                limit=50,
            )
            for row in rows:
                proposal = TraderProposal.model_validate(row.payload)
                if proposal.evaluation_mode == "market_hours":
                    continue
                return proposal
        return None

    def _duplicate_trigger(
        self,
        *,
        symbol: str,
        trigger: str,
        threshold_price: Decimal,
        market_session_date: str,
    ) -> bool:
        with self.session_factory() as session:
            rows = ResearchRepository(session).list_trader_proposals(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
                symbol=symbol,
                limit=200,
            )
            for row in rows:
                payload = dict(row.payload or {})
                if payload.get("evaluation_mode") != "market_hours":
                    continue
                if payload.get("lifecycle_trigger") != trigger:
                    continue
                if payload.get("market_session_date") != market_session_date:
                    continue
                prior_threshold = payload.get("trigger_threshold_price_inr")
                if prior_threshold is None:
                    continue
                if _decimal(prior_threshold).quantize(SCORE_QUANT) == threshold_price.quantize(
                    SCORE_QUANT
                ):
                    return True
        return False

    def _audit_skip(
        self,
        *,
        run_id: str,
        symbol: str,
        market_session_date: str,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session_factory() as session:
            self._audit(
                session,
                "position_monitor.trigger_skipped",
                payload={
                    "run_id": run_id,
                    "symbol": symbol,
                    "market_session_date": market_session_date,
                    "reason": reason,
                    **(payload or {}),
                },
                note=f"Position monitor skipped {symbol}: {reason}.",
            )
            session.commit()

    def _new_run(self, *, now: datetime, symbols: list[str]) -> PaperRun:
        return PaperRun(
            run_id=paper_run_id(
                started_at=now,
                symbols=symbols,
                schedule_name=MONITOR_SCHEDULE_NAME,
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            ),
            portfolio_id=self.settings.taurus_paper_portfolio_id,
            schedule_name=MONITOR_SCHEDULE_NAME,
            status="RUNNING",
            started_at=now,
            symbols=symbols,
            timezone=self.settings.taurus_paper_timezone,
            run_after_market_close=False,
            universe=PaperRunUniverse(
                source="manual_symbols",
                provider=self.settings.taurus_position_monitor_provider,
                selected_symbol_count=len(symbols),
                symbols=symbols,
            ),
            market_data_summary={
                "provider": self.settings.taurus_position_monitor_provider,
                "source": "latest_quote_snapshots",
            },
        )

    def _complete_run(
        self,
        session: Session,
        *,
        run: PaperRun,
        status: str,
        succeeded_symbols: list[str],
        failed_symbols: list[str],
        artifacts: dict[str, Any],
    ) -> None:
        completed = run.model_copy(
            update={
                "status": status,
                "completed_at": _as_utc(self.now_func()),
                "succeeded_symbols": succeeded_symbols,
                "failed_symbols": failed_symbols,
                "artifacts": _json_safe(artifacts),
            }
        )
        PaperRunRepository(session).upsert(completed)
        self._audit(
            session,
            "position_monitor.iteration_completed",
            payload={
                "run_id": completed.run_id,
                "portfolio_id": completed.portfolio_id,
                "symbols": completed.symbols,
                "status": status,
                "succeeded_symbols": succeeded_symbols,
                "failed_symbols": failed_symbols,
            },
            note="Market-hours position monitor iteration completed.",
        )
        session.commit()

    def _audit(
        self,
        session: Session,
        event_type: str,
        *,
        payload: dict[str, Any],
        note: str,
    ) -> None:
        session.add(
            AuditLogModel(
                event_type=event_type,
                actor="PositionMonitorService",
                payload=_json_safe(payload),
                note=note,
            )
        )


def _trigger_data(
    *,
    position: PaperPosition,
    proposal: TraderProposal,
    snapshot: MarketPriceSnapshot,
) -> dict[str, Any]:
    average_cost = position.average_cost_inr.quantize(SCORE_QUANT)
    stop_loss_price = _money(
        average_cost * (Decimal("1") - (proposal.stop_loss_pct / Decimal("100")))
    )
    take_profit_price = _money(
        average_cost * (Decimal("1") + (proposal.take_profit_pct / Decimal("100")))
    )
    latest_price = snapshot.last_price.quantize(SCORE_QUANT)
    trigger: LifecycleTrigger | None = None
    threshold = Decimal("0.0000")
    if latest_price <= stop_loss_price:
        trigger = "stop_loss"
        threshold = stop_loss_price
    elif latest_price >= take_profit_price:
        trigger = "take_profit"
        threshold = take_profit_price
    return {
        "trigger": trigger,
        "latest_price_inr": latest_price,
        "average_cost_inr": average_cost,
        "quantity": position.quantity,
        "stop_loss_pct": proposal.stop_loss_pct,
        "take_profit_pct": proposal.take_profit_pct,
        "stop_loss_price_inr": stop_loss_price,
        "take_profit_price_inr": take_profit_price,
        "trigger_threshold_price_inr": threshold if trigger else None,
    }


def _position_exposures_pct_nav(
    *,
    positions: list[PaperPosition],
    equity_inr: Decimal | None,
) -> dict[str, Decimal]:
    if equity_inr is None or equity_inr <= 0:
        return {}
    return {
        position.symbol.upper(): ((position.market_value_inr / equity_inr) * Decimal("100")).quantize(
            SCORE_QUANT
        )
        for position in positions
        if position.market_value_inr > 0
    }


def _snapshot_payload(model) -> dict[str, Any]:
    return _json_safe(
        {
            "id": model.id,
            "provider": model.provider,
            "symbol": model.symbol,
            "exchange": model.exchange,
            "provider_symbol": model.provider_symbol,
            "instrument_token": model.instrument_token,
            "last_price": model.last_price,
            "open": model.open,
            "high": model.high,
            "low": model.low,
            "close": model.close,
            "volume": model.volume,
            "fetched_at": model.fetched_at,
            "source": model.source,
            "raw": model.raw,
        }
    )


def _is_market_hours(now: datetime, timezone_name: str) -> bool:
    local_now = _as_utc(now).astimezone(ZoneInfo(timezone_name))
    if local_now.weekday() >= 5:
        return False
    return dt_time(9, 15) <= local_now.time() <= dt_time(15, 30)


def _market_session_date(now: datetime, timezone_name: str) -> str:
    return _as_utc(now).astimezone(ZoneInfo(timezone_name)).date().isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(value: Decimal) -> Decimal:
    return value.quantize(SCORE_QUANT)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
