from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
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
from taurus_core.backtesting.graph import GraphBacktestSignal, GraphBacktestSignalLoader
from taurus_core.config import Settings, get_settings
from taurus_core.data.importers import MarketDataImportSummary, import_market_data
from taurus_core.data.preflight import assert_kite_runtime_preflight
from taurus_core.data.providers.factory import build_market_data_provider
from taurus_core.db.models import AuditLogModel
from taurus_core.db.repositories import (
    CandleRepository,
    ExecutionRepository,
    GraphRepository,
    IntelligenceRepository,
    InstrumentRepository,
    PaperRunRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import DailyCandle
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.features.store import TechnicalFeatureService
from taurus_core.graph.preflight import assert_graph_ready_for_paper
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
from taurus_core.portfolio import (
    CoreBasketPosition,
    CoreBasketReviewInput,
    CoreShariahBasketStrategy,
    load_money_management_policy_for_settings,
    severe_negative_symbols,
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
        strategy_config_path: str | Path | None = None,
    ) -> PaperRun:
        requested_symbols = _normalize_symbols(symbols)
        if not requested_symbols:
            raise ValueError("At least one symbol is required for a paper run.")

        run_migrations(self.settings)
        open_position_symbols = sorted(self._open_position_symbols())
        normalized_symbols = _normalize_symbols([*requested_symbols, *open_position_symbols])
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
                symbols=requested_symbols,
            ),
        )
        self._store_run(run, audit_event="paper_run.started")

        try:
            market_data_summary = self._load_latest_inputs()
            strategy_summary = self._generate_strategy_summary(
                symbols=requested_symbols,
                universe=run.universe,
                strategy_config_path=strategy_config_path,
            )
            money_management_summary = self._generate_money_management_summary()
            normalized_symbols = _symbols_for_pipeline(
                requested_symbols=requested_symbols,
                universe=run.universe,
                strategy_summary=strategy_summary,
            )
            run = _run_with_selected_symbols(run, normalized_symbols)
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
        if money_management_summary is not None:
            artifacts["money_management"] = money_management_summary
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
        llm_provider = build_llm_provider(self.settings)
        with self.session_factory() as session:
            reports = run_analyst_suite(
                session,
                symbol=symbol,
                run_id=run_id,
                llm_provider=llm_provider,
                enabled_analysts=enabled_analysts,
            )

        with self.session_factory() as session:
            debate = ResearchDebateService(
                session,
                settings=self.settings,
                llm_provider=llm_provider,
            ).run(
                symbol=symbol,
                run_id=run_id,
                rounds_requested=self.rounds_requested,
            )

        with self.session_factory() as session:
            proposal = TraderAgent(
                session,
                self.settings,
                llm_provider=llm_provider,
            ).run(symbol=symbol, run_id=run_id, debate=debate)

        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            open_positions = execution_repo.latest_open_positions_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            account = execution_repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
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
            decision = PortfolioManagerAgent(
                session,
                self.settings,
                llm_provider=llm_provider,
            ).run(
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
            "proposal_action": proposal.action,
            "portfolio_id": proposal.portfolio_id,
            "lifecycle_trigger": proposal.lifecycle_trigger,
            "evaluation_mode": proposal.evaluation_mode,
            "current_position_quantity": proposal.current_position_quantity,
            "current_position_pct_nav": str(proposal.current_position_pct_nav),
            "target_position_pct_nav": str(proposal.target_position_pct_nav),
            "position_management_summary": proposal.position_management_summary,
            "risk_check_id": review.risk_check_id,
            "final_decision_id": decision.final_decision_id,
            "final_status": decision.status,
            "final_action": decision.final_action,
            "no_paper_order_expected": decision.status == "NO_ACTION",
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

    def _load_latest_inputs(self) -> dict[str, object]:
        provider = build_market_data_provider(self.settings)
        with self.session_factory() as session:
            assert_kite_runtime_preflight(session, include_paper_runs=True)
        with self.session_factory() as session:
            market_summary = import_market_data(session, provider)
        with self.session_factory() as session:
            import_mock_news(session, MockNewsProvider())
        return _market_summary_dict(market_summary)

    def _generate_strategy_summary(
        self,
        *,
        symbols: list[str],
        universe: PaperRunUniverse | None,
        strategy_config_path: str | Path | None,
    ) -> dict[str, object]:
        path = strategy_config_path or DEFAULT_STRATEGY_CONFIG_PATH
        strategy_config = load_strategy_config(path)
        strategy = build_strategy(strategy_config)
        graph_profile_enabled = _graph_profile_enabled(
            settings=self.settings,
            strategy_type=strategy_config.strategy_type,
            strategy_parameters=strategy_config.parameters,
        )
        graph_readiness: dict[str, object] | None = None
        if graph_profile_enabled:
            with self.session_factory() as session:
                graph_readiness = assert_graph_ready_for_paper(
                    session,
                    settings=self.settings,
                    symbols=symbols,
                ).to_dict()
        feature_service = TechnicalFeatureService.from_strategy_parameters(
            strategy_config.parameters
        )
        current_positions = self._open_position_symbols()
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
                "strategy_type": strategy_config.strategy_type,
                "targets": [],
                "signals": [],
                "feature_snapshot_count": 0,
                "graph_enabled_profile": graph_profile_enabled,
                "graph_risk_enabled": self.settings.taurus_graph_risk_enabled,
                "graph_readiness": graph_readiness,
                "graph_signal_count": 0,
                "symbols_with_graph_signals": [],
                "graph_signals": {},
                "graph_selected_symbols": [],
                "graph_strategy_config_path": str(strategy_config.source_path)
                if graph_profile_enabled
                else None,
                "select_targets_with_graph_called": False,
                "open_position_symbols": sorted(current_positions),
                "symbol_selection": _symbol_selection_metadata(
                    requested_symbols=symbols,
                    selected_symbols=[],
                    current_positions=current_positions,
                    graph_signals_by_symbol={},
                    universe=universe,
                    select_targets_with_graph_called=False,
                ),
            }

        trade_date = max(trade_dates)
        graph_signals_by_symbol: dict[str, GraphBacktestSignal] = {}
        if graph_profile_enabled:
            with self.session_factory() as session:
                graph_signals_by_symbol = GraphBacktestSignalLoader(
                    session,
                    edge_statuses=("active",),
                ).load_by_as_of_date(as_of_date=trade_date, symbols=symbols)

        select_targets_with_graph = getattr(strategy, "select_targets_with_graph", None)
        select_targets_with_graph_called = graph_profile_enabled and callable(
            select_targets_with_graph
        )
        if select_targets_with_graph_called:
            targets, signals = select_targets_with_graph(
                trade_date=trade_date,
                features_by_symbol=snapshots,
                current_positions=current_positions,
                graph_signals_by_symbol=graph_signals_by_symbol,
            )
        else:
            targets, signals = strategy.select_targets(
                trade_date=trade_date,
                features_by_symbol=snapshots,
                current_positions=current_positions,
            )
        requested = set(symbols)
        selected_symbols = sorted(targets)
        return {
            "strategy_name": strategy_config.strategy_name,
            "strategy_config_path": str(strategy_config.source_path),
            "strategy_type": strategy_config.strategy_type,
            "targets": selected_symbols,
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
            "graph_enabled_profile": graph_profile_enabled,
            "graph_risk_enabled": self.settings.taurus_graph_risk_enabled,
            "graph_readiness": graph_readiness,
            "graph_signal_count": len(graph_signals_by_symbol),
            "symbols_with_graph_signals": sorted(graph_signals_by_symbol),
            "graph_signals": {
                symbol: signal.to_dict()
                for symbol, signal in sorted(graph_signals_by_symbol.items())
            },
            "graph_selected_symbols": selected_symbols if select_targets_with_graph_called else [],
            "graph_strategy_config_path": str(strategy_config.source_path)
            if graph_profile_enabled
            else None,
            "select_targets_with_graph_called": select_targets_with_graph_called,
            "open_position_symbols": sorted(current_positions),
            "symbol_selection": _symbol_selection_metadata(
                requested_symbols=symbols,
                selected_symbols=selected_symbols,
                current_positions=current_positions,
                graph_signals_by_symbol=graph_signals_by_symbol,
                universe=universe,
                select_targets_with_graph_called=select_targets_with_graph_called,
            ),
        }

    def _generate_money_management_summary(self) -> dict[str, object] | None:
        if not self.settings.taurus_money_management_enabled:
            return None

        policy = load_money_management_policy_for_settings(self.settings)
        strategy = CoreShariahBasketStrategy(policy)
        universe_symbols = set(strategy.universe_by_symbol)
        with self.session_factory() as session:
            histories_by_symbol = {
                symbol: _daily_candle_history(session, symbol)
                for symbol in sorted(universe_symbols)
            }
            execution_repo = ExecutionRepository(session)
            account = execution_repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            current_positions = tuple(
                CoreBasketPosition(
                    symbol=position.symbol,
                    market_value_inr=position.market_value_inr,
                )
                for position in execution_repo.latest_open_positions_by_portfolio(
                    portfolio_id=self.settings.taurus_paper_portfolio_id,
                )
                if position.symbol.upper() in universe_symbols
            )
            events_by_symbol: dict[str, list[object]] = {}
            for event in IntelligenceRepository(session).list_events(limit=None):
                if event.symbol.upper() in universe_symbols:
                    events_by_symbol.setdefault(event.symbol.upper(), []).append(event)
            sector_by_symbol, graph_cluster_by_symbol = _core_concentration_groups(
                session,
                symbols=universe_symbols,
            )
            last_core_rebalance_date = _last_core_rebalance_date(
                PaperRunRepository(session).list(limit=None)
            )

        nav_inr = (
            account.equity_inr
            if account is not None
            else Decimal(str(self.settings.taurus_initial_capital_inr))
        )
        return {
            "policy": policy.to_metadata(),
            "core_shariah_basket": strategy.review(
                CoreBasketReviewInput(
                    histories_by_symbol=histories_by_symbol,
                    nav_inr=nav_inr,
                    current_positions=current_positions,
                    last_core_rebalance_date=last_core_rebalance_date,
                    severe_negative_symbols=severe_negative_symbols(events_by_symbol),
                    sector_by_symbol=sector_by_symbol,
                    graph_cluster_by_symbol=graph_cluster_by_symbol,
                )
            ),
        }

    def _open_position_symbols(self) -> set[str]:
        with self.session_factory() as session:
            positions = ExecutionRepository(session).latest_open_positions_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
        return {position.symbol.upper() for position in positions if position.quantity > 0}

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
        self.strategy_config_path = strategy_config_path

    def run(self) -> list[PaperRun]:
        runs: list[PaperRun] = []
        for index in range(self.iterations):
            runs.append(
                self.service.run_once(
                    symbols=self.symbols,
                    universe=self.universe,
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


def _graph_profile_enabled(
    *,
    settings: Settings,
    strategy_type: str,
    strategy_parameters: dict[str, object],
) -> bool:
    return (
        settings.taurus_graph_enabled
        or settings.taurus_graph_risk_enabled
        or strategy_type == "graph_aware_score"
        or bool(strategy_parameters.get("graph_enabled", False))
    )


def _symbols_for_pipeline(
    *,
    requested_symbols: list[str],
    universe: PaperRunUniverse | None,
    strategy_summary: dict[str, object],
) -> list[str]:
    if (
        universe is not None
        and universe.source == "market_data_universe"
        and strategy_summary.get("select_targets_with_graph_called") is True
    ):
        selected = [
            *[str(symbol) for symbol in strategy_summary.get("graph_selected_symbols", [])],
            *[str(symbol) for symbol in strategy_summary.get("open_position_symbols", [])],
        ]
        normalized = _normalize_symbols(selected)
        if not normalized:
            raise ValueError(
                "Graph-aware paper target selection produced no target or open-position "
                "symbols for the market-data universe."
            )
        return normalized
    return _normalize_symbols(
        [
            *requested_symbols,
            *[str(symbol) for symbol in strategy_summary.get("open_position_symbols", [])],
        ]
    )


def _run_with_selected_symbols(run: PaperRun, symbols: list[str]) -> PaperRun:
    universe = run.universe
    if universe is not None:
        universe = universe.model_copy(
            update={
                "selected_symbol_count": len(symbols),
                "symbols": list(symbols),
            }
        )
    return run.model_copy(update={"symbols": list(symbols), "universe": universe})


def _symbol_selection_metadata(
    *,
    requested_symbols: list[str],
    selected_symbols: list[str],
    current_positions: set[str],
    graph_signals_by_symbol: dict[str, GraphBacktestSignal],
    universe: PaperRunUniverse | None,
    select_targets_with_graph_called: bool,
) -> dict[str, dict[str, object]]:
    requested = {symbol.upper() for symbol in requested_symbols}
    selected = {symbol.upper() for symbol in selected_symbols}
    graph_signal_symbols = set(graph_signals_by_symbol)
    universe_mode = universe.source if universe is not None else "manual_symbols"
    output_symbols = sorted(requested | selected | current_positions | graph_signal_symbols)
    return {
        symbol: {
            "selection_source": _selection_source(
                symbol=symbol,
                requested=requested,
                selected=selected,
                current_positions=current_positions,
                universe_mode=universe_mode,
                select_targets_with_graph_called=select_targets_with_graph_called,
            ),
            "requested_explicitly": symbol in requested and universe_mode == "manual_symbols",
            "selected_by_graph_strategy": (
                select_targets_with_graph_called and symbol in selected
            ),
            "included_from_open_position": symbol in current_positions,
            "has_graph_signal": symbol in graph_signal_symbols,
            "graph_signal": graph_signals_by_symbol[symbol].to_dict()
            if symbol in graph_signals_by_symbol
            else None,
        }
        for symbol in output_symbols
    }


def _last_core_rebalance_date(run_rows) -> date | None:
    for run in run_rows:
        artifacts = run.artifacts or {}
        if not isinstance(artifacts, dict):
            continue
        money_management = artifacts.get("money_management")
        if not isinstance(money_management, dict):
            continue
        core = money_management.get("core_shariah_basket")
        if not isinstance(core, dict):
            continue
        rebalance = core.get("rebalance")
        if not isinstance(rebalance, dict) or rebalance.get("should_rebalance") is not True:
            continue
        as_of_date = core.get("as_of_date")
        if not isinstance(as_of_date, str):
            continue
        try:
            return date.fromisoformat(as_of_date)
        except ValueError:
            continue
    return None


def _core_concentration_groups(
    session: Session,
    *,
    symbols: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    graph_repo = GraphRepository(session)
    sector_by_symbol: dict[str, str] = {}
    company_node_by_symbol = {
        symbol: graph_repo.get_node_by_key(f"company:{symbol}")
        for symbol in sorted(symbols)
    }
    for symbol, node in company_node_by_symbol.items():
        if node is None:
            continue
        for edge in graph_repo.list_edges_for_node(
            node_key=node.node_key,
            status="active",
            limit=None,
        ):
            if edge.edge_type not in {"classified_as_sector", "classified_as_basic_industry"}:
                continue
            related_node_id = (
                edge.target_node_id if edge.source_node_id == node.id else edge.source_node_id
            )
            related = graph_repo.get_node_by_id(related_node_id)
            if related is not None and related.node_type in {"industry_sector", "basic_industry"}:
                sector_by_symbol[symbol] = related.display_name
                break

    graph_cluster_by_symbol: dict[str, str] = {}
    active_company_edges = []
    for edge in graph_repo.list_edges(status="active", limit=None):
        source = graph_repo.get_node_by_id(edge.source_node_id)
        target = graph_repo.get_node_by_id(edge.target_node_id)
        if source is None or target is None:
            continue
        if source.symbol in symbols and target.symbol in symbols:
            active_company_edges.append((source.symbol, target.symbol))
    components = _connected_components(symbols, active_company_edges)
    for index, component in enumerate(components, start=1):
        if len(component) < 2:
            continue
        for symbol in component:
            graph_cluster_by_symbol[symbol] = f"graph_cluster_{index}"
    return sector_by_symbol, graph_cluster_by_symbol


def _connected_components(
    symbols: set[str],
    edges: list[tuple[str | None, str | None]],
) -> list[set[str]]:
    adjacency = {symbol: set() for symbol in symbols}
    for source, target in edges:
        if source is None or target is None:
            continue
        if source not in adjacency or target not in adjacency:
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)
    components: list[set[str]] = []
    seen: set[str] = set()
    for symbol in sorted(adjacency):
        if symbol in seen:
            continue
        stack = [symbol]
        component: set[str] = set()
        while stack:
            item = stack.pop()
            if item in seen:
                continue
            seen.add(item)
            component.add(item)
            stack.extend(sorted(adjacency[item] - seen))
        components.append(component)
    return components


def _selection_source(
    *,
    symbol: str,
    requested: set[str],
    selected: set[str],
    current_positions: set[str],
    universe_mode: str,
    select_targets_with_graph_called: bool,
) -> str:
    if universe_mode == "manual_symbols" and symbol in requested:
        return "explicit_symbol"
    if select_targets_with_graph_called and symbol in selected:
        return "graph_aware_strategy"
    if symbol in current_positions:
        return "open_position"
    if symbol in requested:
        return "configured_universe"
    return "graph_signal_only"


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
