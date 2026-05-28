from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from taurus_core.alerts.service import AlertService
from taurus_core.alerts.templates import scheduled_job_failure_event
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.roster import MIN_ANALYST_REPORTS, skipped_analysts
from taurus_core.agents.runner import run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings, get_settings
from taurus_core.data.importers import MarketDataImportSummary, import_market_data
from taurus_core.data.providers.factory import build_market_data_provider
from taurus_core.db.models import AuditLogModel
from taurus_core.db.repositories import (
    CandleRepository,
    ExecutionRepository,
    InstrumentRepository,
    PaperRunRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import DailyCandle
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.features.store import TechnicalFeatureService
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm import build_llm_provider
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.paper_trading.schemas import (
    PaperRun,
    PaperRunError,
    PaperRunUniverse,
    paper_run_id,
)
from taurus_core.research.debate_service import DEFAULT_DEBATE_ROUNDS, ResearchDebateService
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.strategies import DEFAULT_STRATEGY_CONFIG_PATH, load_strategy_config
from taurus_core.strategies.factory import build_strategy


class PaperRunService:
    """End-of-day paper pipeline with run-level status tracking."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        timezone_name: str | None = None,
        schedule_name: str = "daily_after_close",
        run_after_market_close: bool | None = None,
        rounds_requested: int = DEFAULT_DEBATE_ROUNDS,
    ) -> None:
        self.settings = settings or get_settings()
        self.timezone_name = timezone_name or self.settings.taurus_paper_timezone
        self.schedule_name = schedule_name
        self.run_after_market_close = (
            self.settings.taurus_paper_after_market_close
            if run_after_market_close is None
            else run_after_market_close
        )
        self.rounds_requested = rounds_requested
        self.session_factory = build_session_factory(self.settings)
        self.logger = get_logger(__name__)

    def run_once(
        self,
        *,
        symbols: Iterable[str],
        universe: PaperRunUniverse | None = None,
        csv_path: str | Path | None = None,
        directory: str | Path | None = None,
        strategy_config_path: str | Path | None = None,
    ) -> PaperRun:
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            raise ValueError("At least one symbol is required for a paper run.")

        run_migrations(self.settings)
        started_at = _utc_now()
        run = PaperRun(
            run_id=paper_run_id(
                started_at=started_at,
                symbols=normalized_symbols,
                schedule_name=self.schedule_name,
            ),
            schedule_name=self.schedule_name,
            status="RUNNING",
            started_at=started_at,
            symbols=normalized_symbols,
            timezone=self.timezone_name,
            run_after_market_close=self.run_after_market_close,
            universe=universe or _manual_universe(
                provider=self.settings.taurus_market_data_provider,
                symbols=normalized_symbols,
            ),
        )
        self._store_run(run, audit_event="paper_run.started")

        try:
            market_data_summary = self._load_latest_inputs(csv_path=csv_path, directory=directory)
            strategy_summary = self._generate_strategy_summary(
                symbols=normalized_symbols,
                strategy_config_path=strategy_config_path,
            )
        except Exception as exc:
            error = PaperRunError(
                symbol="*",
                stage="data_update",
                message=str(exc),
                error_type=exc.__class__.__name__,
            )
            failed = run.model_copy(
                update={
                    "status": "FAILED",
                    "completed_at": _utc_now(),
                    "failed_symbols": normalized_symbols,
                    "errors": [error],
                }
            )
            self._log_failure(failed.run_id, error)
            return self._store_run(failed, audit_event="paper_run.failed")

        artifacts: dict[str, Any] = {"strategy": strategy_summary, "symbols": {}}
        succeeded_symbols: list[str] = []
        failed_symbols: list[str] = []
        errors: list[PaperRunError] = []
        run = run.model_copy(
            update={
                "market_data_summary": market_data_summary,
                "artifacts": artifacts,
            }
        )
        self._store_run(run)

        for symbol in normalized_symbols:
            try:
                artifacts["symbols"][symbol] = self._run_symbol(symbol=symbol, run_id=run.run_id)
                succeeded_symbols.append(symbol)
            except Exception as exc:
                error = PaperRunError(
                    symbol=symbol,
                    stage="symbol_pipeline",
                    message=str(exc),
                    error_type=exc.__class__.__name__,
                )
                failed_symbols.append(symbol)
                errors.append(error)
                self._log_failure(run.run_id, error)
            finally:
                partial_status = _status_for(succeeded_symbols, failed_symbols)
                run = run.model_copy(
                    update={
                        "status": partial_status,
                        "succeeded_symbols": list(succeeded_symbols),
                        "failed_symbols": list(failed_symbols),
                        "errors": list(errors),
                        "artifacts": artifacts,
                    }
                )
                self._store_run(run)

        completed = run.model_copy(
            update={
                "status": _status_for(succeeded_symbols, failed_symbols),
                "completed_at": _utc_now(),
            }
        )
        return self._store_run(completed, audit_event=f"paper_run.{completed.status.lower()}")

    def _run_symbol(self, *, symbol: str, run_id: str) -> dict[str, object]:
        with bound_trace_context(run_id=run_id):
            self.logger.info("paper_run.symbol.started", symbol=symbol)

        enabled_analysts = self.settings.enabled_analyst_keys
        with self.session_factory() as session:
            reports = run_analyst_suite(
                session,
                symbol=symbol,
                run_id=run_id,
                llm_provider=build_llm_provider(self.settings),
                enabled_analysts=enabled_analysts,
            )

        with self.session_factory() as session:
            debate = ResearchDebateService(session).run(
                symbol=symbol,
                run_id=run_id,
                rounds_requested=self.rounds_requested,
            )

        with self.session_factory() as session:
            proposal = TraderAgent(session).run(symbol=symbol, run_id=run_id, debate=debate)

        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            open_positions = [
                position for position in execution_repo.list_positions() if position.quantity > 0
            ]
            account = execution_repo.latest_account()
            review = RiskReviewService(
                session,
                self.settings,
                current_open_positions=len(open_positions),
                current_position_exposures_pct_nav=_position_exposures_pct_nav(
                    positions=open_positions,
                    equity_inr=account.equity_inr if account is not None else None,
                ),
            ).run(symbol=symbol, run_id=run_id, proposal=proposal)

        with self.session_factory() as session:
            decision = PortfolioManagerAgent(session, self.settings).run(
                symbol=symbol,
                run_id=run_id,
                risk_review=review,
            )

        with self.session_factory() as session:
            order = ExecutionRouter(session, self.settings).route_decision(decision)
            repo = ExecutionRepository(session)
            account = repo.latest_account(run_id=run_id)

        result = {
            "symbol": symbol,
            "report_ids": [report.report_id for report in reports],
            "analyst_roster": _analyst_roster_dict(
                enabled_analysts=enabled_analysts,
                report_count=len(reports),
            ),
            "debate_id": debate.debate_id,
            "proposal_id": proposal.proposal_id,
            "risk_check_id": review.risk_check_id,
            "final_decision_id": decision.final_decision_id,
            "final_status": decision.status,
            "order_id": order.order_id if order is not None else None,
            "order_status": order.status if order is not None else None,
            "account_id": account.account_id if account is not None else None,
        }
        with bound_trace_context(
            run_id=run_id,
            debate_id=debate.debate_id,
            proposal_id=proposal.proposal_id,
            risk_check_id=review.risk_check_id,
            final_decision_id=decision.final_decision_id,
            order_id=order.order_id if order is not None else None,
        ):
            self.logger.info("paper_run.symbol.completed", **result)
        return result

    def _load_latest_inputs(
        self,
        *,
        csv_path: str | Path | None,
        directory: str | Path | None,
    ) -> dict[str, object]:
        provider = build_market_data_provider(
            self.settings,
            csv_path=csv_path,
            directory=directory,
        )
        with self.session_factory() as session:
            market_summary = import_market_data(session, provider)
        with self.session_factory() as session:
            import_mock_news(session, MockNewsProvider())
        return _market_summary_dict(market_summary)

    def _generate_strategy_summary(
        self,
        *,
        symbols: list[str],
        strategy_config_path: str | Path | None,
    ) -> dict[str, object]:
        path = strategy_config_path or DEFAULT_STRATEGY_CONFIG_PATH
        strategy_config = load_strategy_config(path)
        strategy = build_strategy(strategy_config)
        feature_service = TechnicalFeatureService.from_strategy_parameters(
            strategy_config.parameters
        )
        with self.session_factory() as session:
            instruments = InstrumentRepository(session).list(active_only=True)
            snapshots = {}
            for instrument in instruments:
                history = _daily_candle_history(session, instrument.symbol)
                if len(history) < max(strategy_config.lookback_days, 1):
                    continue
                snapshot = feature_service.build_snapshot(
                    symbol=instrument.symbol,
                    as_of_date=history[-1].trade_date + timedelta(days=1),
                    history=history,
                )
                if snapshot is not None:
                    snapshots[instrument.symbol] = snapshot

        trade_dates = [snapshot.as_of_date for snapshot in snapshots.values()]
        if not trade_dates:
            return {
                "strategy_name": strategy_config.strategy_name,
                "strategy_config_path": str(strategy_config.source_path),
                "targets": [],
                "signals": [],
                "feature_snapshot_count": 0,
            }

        targets, signals = strategy.select_targets(
            trade_date=max(trade_dates),
            features_by_symbol=snapshots,
            current_positions=set(),
        )
        requested = set(symbols)
        return {
            "strategy_name": strategy_config.strategy_name,
            "strategy_config_path": str(strategy_config.source_path),
            "targets": sorted(targets),
            "signals": [
                {
                    "trade_date": signal.trade_date.isoformat(),
                    "symbol": signal.symbol,
                    "action": signal.action,
                    "score": str(signal.score),
                    "reason": signal.reason,
                    "explanation": signal.explanation.to_dict(),
                }
                for signal in signals
                if signal.symbol in requested or signal.symbol in targets
            ],
            "feature_snapshot_count": len(snapshots),
        }

    def _store_run(self, run: PaperRun, *, audit_event: str | None = None) -> PaperRun:
        with self.session_factory() as session:
            repo = PaperRunRepository(session)
            repo.upsert(run)
            if audit_event is not None:
                session.add(
                    AuditLogModel(
                        event_type=audit_event,
                        actor="paper_run_service",
                        payload={
                            "run_id": run.run_id,
                            "status": run.status,
                            "symbols": list(run.symbols),
                            "succeeded_symbols": list(run.succeeded_symbols),
                            "failed_symbols": list(run.failed_symbols),
                            "errors": [error.model_dump(mode="json") for error in run.errors],
                        },
                        note=f"Paper run {run.run_id} status {run.status}.",
                    )
                )
            session.commit()
        with bound_trace_context(run_id=run.run_id):
            self.logger.info(
                "paper_run.status",
                status=run.status,
                symbols=run.symbols,
                succeeded_symbols=run.succeeded_symbols,
                failed_symbols=run.failed_symbols,
            )
        return run

    def _log_failure(self, run_id: str, error: PaperRunError) -> None:
        with self.session_factory() as session:
            session.add(
                AuditLogModel(
                    event_type="paper_run.symbol_failed",
                    actor="paper_run_service",
                    payload={
                        "run_id": run_id,
                        "symbol": error.symbol,
                        "stage": error.stage,
                        "message": error.message,
                        "error_type": error.error_type,
                    },
                    note="Paper run failure captured without aborting previously completed symbols.",
                )
            )
            session.commit()
            try:
                AlertService(session, self.settings).send(
                    scheduled_job_failure_event(run_id=run_id, error=error)
                )
            except Exception as exc:
                self.logger.warning(
                    "alert.paper_run_failure.failed",
                    run_id=run_id,
                    symbol=error.symbol,
                    stage=error.stage,
                    error=str(exc),
                )
        with bound_trace_context(run_id=run_id):
            self.logger.error(
                "paper_run.failure",
                symbol=error.symbol,
                stage=error.stage,
                error_type=error.error_type,
                message=error.message,
            )


class SimplePaperScheduler:
    """Documented scheduler used for M11 local paper loops."""

    def __init__(
        self,
        service: PaperRunService,
        *,
        symbols: Iterable[str],
        interval_seconds: float,
        iterations: int,
        universe: PaperRunUniverse | None = None,
        csv_path: str | Path | None = None,
        directory: str | Path | None = None,
        strategy_config_path: str | Path | None = None,
    ) -> None:
        if iterations < 1:
            raise ValueError("iterations must be at least 1")
        if interval_seconds < 0:
            raise ValueError("interval_seconds cannot be negative")
        self.service = service
        self.symbols = _normalize_symbols(symbols)
        self.interval_seconds = interval_seconds
        self.iterations = iterations
        self.universe = universe
        self.csv_path = csv_path
        self.directory = directory
        self.strategy_config_path = strategy_config_path

    def run(self) -> list[PaperRun]:
        runs: list[PaperRun] = []
        for index in range(self.iterations):
            runs.append(
                self.service.run_once(
                    symbols=self.symbols,
                    universe=self.universe,
                    csv_path=self.csv_path,
                    directory=self.directory,
                    strategy_config_path=self.strategy_config_path,
                )
            )
            if index < self.iterations - 1 and self.interval_seconds > 0:
                time.sleep(self.interval_seconds)
        return runs


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    normalized = []
    for value in symbols:
        for symbol in str(value).split(","):
            cleaned = symbol.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
    return normalized


def _analyst_roster_dict(
    *,
    enabled_analysts: Iterable[str],
    report_count: int,
) -> dict[str, object]:
    enabled = list(enabled_analysts)
    return {
        "enabled": enabled,
        "skipped": list(skipped_analysts(enabled)),
        "report_count": report_count,
        "min_required": MIN_ANALYST_REPORTS,
        "status": "enough_reports"
        if report_count >= MIN_ANALYST_REPORTS
        else "failed_no_reports",
    }


def _manual_universe(*, provider: str, symbols: list[str]) -> PaperRunUniverse:
    return PaperRunUniverse(
        source="manual_symbols",
        provider=provider,
        selected_symbol_count=len(symbols),
        symbols=list(symbols),
    )


def _status_for(succeeded_symbols: list[str], failed_symbols: list[str]) -> str:
    if failed_symbols and succeeded_symbols:
        return "PARTIAL_FAILED"
    if failed_symbols:
        return "FAILED"
    if succeeded_symbols:
        return "COMPLETED"
    return "RUNNING"


def _position_exposures_pct_nav(
    *,
    positions,
    equity_inr: Decimal | None,
) -> dict[str, Decimal]:
    if equity_inr is None or equity_inr <= 0:
        return {}
    return {
        position.symbol.upper(): ((position.market_value_inr / equity_inr) * Decimal("100"))
        .quantize(Decimal("0.0001"))
        for position in positions
        if position.market_value_inr > 0
    }


def _daily_candle_history(session: Session, symbol: str) -> list[DailyCandle]:
    return [
        DailyCandle(
            symbol=candle.symbol,
            trade_date=candle.trade_date,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            timeframe=candle.timeframe,
            source=candle.source,
            data_available_time=candle.data_available_time,
        )
        for candle in CandleRepository(session).get_by_symbol_and_date_range(symbol=symbol)
    ]


def _market_summary_dict(summary: MarketDataImportSummary) -> dict[str, object]:
    return {
        "provider_name": summary.provider_name,
        "source": summary.source,
        "instrument_count": summary.instrument_count,
        "candle_count": summary.candle_count,
        "candles_per_symbol": dict(summary.candles_per_symbol),
        "start_date": summary.start_date.isoformat() if summary.start_date is not None else None,
        "end_date": summary.end_date.isoformat() if summary.end_date is not None else None,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
