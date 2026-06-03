from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from taurus_core.alerts.service import AlertService
from taurus_core.alerts.templates import scheduled_job_failure_event
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.roster import MIN_ANALYST_REPORTS, skipped_analysts
from taurus_core.agents.runner import run_analyst_suite
from taurus_core.agents.schemas import AnalystReport
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
    ResearchRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import DailyCandle
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import PaperOrder
from taurus_core.features.store import TechnicalFeatureService
from taurus_core.graph.preflight import assert_graph_ready_for_paper
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm import LLMProvider, build_llm_provider
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.ops.progress import ProgressEventCallback, emit_progress
from taurus_core.paper_trading.schemas import (
    PaperRun,
    PaperRunError,
    PaperRunUniverse,
    paper_run_id,
)
from taurus_core.portfolio import (
    ALLOCATABLE_SLEEVE_IDS,
    ActiveAllocationInput,
    ActiveAllocationPosition,
    CoreBasketPosition,
    CoreBasketReviewInput,
    CoreShariahBasketStrategy,
    FallbackAllocationPolicy,
    MoneyManagementPolicy,
    PortfolioAllocationService,
    RunAllocationInput,
    RunAllocationResult,
    RunLevelAllocationService,
    SleeveAllocationSnapshot,
    load_money_management_policy_for_settings,
    severe_negative_symbols,
)
from taurus_core.portfolio.run_allocation import SELECTED_LEDGER_STATUSES
from taurus_core.research.debate_service import DEFAULT_DEBATE_ROUNDS, ResearchDebateService
from taurus_core.research.schemas import DebateReport, TraderProposal
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.risk.schemas import FinalDecision, RiskReview
from taurus_core.strategies import DEFAULT_STRATEGY_CONFIG_PATH, load_strategy_config
from taurus_core.strategies.factory import build_strategy


ANALYSIS_STAGE_NAMES = (
    "analyst_suite",
    "research_debate",
    "trader_proposal",
)
FINALIZATION_STAGE_NAMES = (
    "allocation",
    "risk_review",
    "portfolio_manager_final_decision",
    "execution_routing",
)


@dataclass(frozen=True, slots=True)
class PaperSymbolAnalysis:
    symbol: str
    enabled_analysts: list[str]
    reports: list[AnalystReport]
    debate: DebateReport
    proposal: TraderProposal


@dataclass(frozen=True, slots=True)
class PaperSymbolFinalization:
    symbol: str
    proposal: TraderProposal
    proposal_source: str
    risk_review: RiskReview
    final_decision: FinalDecision
    order: PaperOrder | None
    account: Any | None


@dataclass(frozen=True, slots=True)
class PaperRunSymbolScope:
    analysis_scope: str
    execution_scope: str
    effective_execution_scope: str
    requested_symbols: list[str]
    requested_universe_symbols: list[str]
    manual_symbols: list[str]
    analyzed_symbols: list[str]
    finalization_symbols: list[str]
    strategy_selected_symbols: list[str]
    strategy_ranked_symbols: list[str]
    graph_selected_symbols: list[str]
    open_position_symbols: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "analysis_scope": self.analysis_scope,
            "execution_scope": self.execution_scope,
            "effective_execution_scope": self.effective_execution_scope,
            "requested_symbols": list(self.requested_symbols),
            "requested_universe_symbols": list(self.requested_universe_symbols),
            "manual_symbols": list(self.manual_symbols),
            "analyzed_symbols": list(self.analyzed_symbols),
            "analyzed_symbol_count": len(self.analyzed_symbols),
            "finalization_symbols": list(self.finalization_symbols),
            "finalization_symbol_count": len(self.finalization_symbols),
            "strategy_selected_symbols": list(self.strategy_selected_symbols),
            "strategy_ranked_symbols": list(self.strategy_ranked_symbols),
            "graph_selected_symbols": list(self.graph_selected_symbols),
            "open_position_symbols": list(self.open_position_symbols),
        }


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
        progress: ProgressEventCallback | None = None,
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
        self.progress = progress
        self._progress_iteration = 1
        self._progress_iterations = 1
        self._progress_symbol_count = 1

    def configure_progress_context(
        self,
        *,
        iteration: int,
        iterations: int,
        symbol_count: int,
    ) -> None:
        self._progress_iteration = iteration
        self._progress_iterations = iterations
        self._progress_symbol_count = max(symbol_count, 1)

    def _emit_progress(self, event: str, **payload: object) -> None:
        emit_progress(
            self.progress,
            event,
            iteration=self._progress_iteration,
            iterations=self._progress_iterations,
            symbol_count=self._progress_symbol_count,
            **payload,
        )

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

        self._progress_symbol_count = max(len(requested_symbols), 1)
        self._emit_progress(
            "paper.run.setup_started",
            stage="migrations",
            symbols=requested_symbols,
        )
        run_migrations(self.settings)
        self._emit_progress(
            "paper.run.setup_completed",
            stage="migrations",
            symbols=requested_symbols,
        )
        self._emit_progress(
            "paper.run.setup_started",
            stage="open_positions",
            symbols=requested_symbols,
        )
        open_position_symbols = sorted(self._open_position_symbols())
        input_symbols = _normalize_symbols([*requested_symbols, *open_position_symbols])
        analysis_symbols = list(input_symbols)
        finalization_symbols = list(input_symbols)
        self._progress_symbol_count = max(len(input_symbols), 1)
        self._emit_progress(
            "paper.run.setup_completed",
            stage="open_positions",
            symbols=input_symbols,
        )
        started_at = _utc_now()
        run = PaperRun(
            run_id=paper_run_id(
                started_at=started_at,
                symbols=input_symbols,
                schedule_name=self.schedule_name,
            ),
            schedule_name=self.schedule_name,
            status="RUNNING",
            started_at=started_at,
            symbols=input_symbols,
            timezone=self.timezone_name,
            run_after_market_close=self.run_after_market_close,
            universe=universe or _manual_universe(
                provider=self.settings.taurus_market_data_provider,
                symbols=requested_symbols,
            ),
        )
        self._emit_progress(
            "paper.run.started",
            run_id=run.run_id,
            stage="run_created",
            symbols=input_symbols,
        )
        self._store_run(run, audit_event="paper_run.started")

        try:
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="market_data",
                symbols=input_symbols,
            )
            market_data_summary = self._load_latest_inputs()
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="market_data",
                symbols=input_symbols,
            )
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="strategy",
                symbols=input_symbols,
            )
            strategy_summary = self._generate_strategy_summary(
                symbols=requested_symbols,
                universe=run.universe,
                strategy_config_path=strategy_config_path,
            )
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="strategy",
                symbols=input_symbols,
            )
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="money_management",
                symbols=input_symbols,
            )
            money_management_summary = self._generate_money_management_summary()
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="money_management",
                symbols=input_symbols,
            )
            core_basket_symbols = _core_basket_symbols_from_summary(money_management_summary)
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="symbol_selection",
                symbols=input_symbols,
            )
            symbol_scope = _symbol_scope_for_run(
                settings=self.settings,
                requested_symbols=requested_symbols,
                universe=run.universe,
                strategy_summary=strategy_summary,
            )
            strategy_summary = _strategy_summary_with_symbol_scope(
                strategy_summary,
                symbol_scope=symbol_scope,
            )
            analysis_symbols = list(symbol_scope.analyzed_symbols)
            finalization_symbols = list(symbol_scope.finalization_symbols)
            self._progress_symbol_count = max(len(analysis_symbols), 1)
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="symbol_selection",
                symbols=analysis_symbols,
                finalization_symbols=finalization_symbols,
            )
            run = _run_with_selected_symbols(run, analysis_symbols)
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
                    "failed_symbols": analysis_symbols,
                    "errors": [error],
                }
            )
            self._log_failure(failed.run_id, error)
            self._emit_progress(
                "paper.run.failed",
                run_id=failed.run_id,
                stage=error.stage,
                symbols=analysis_symbols,
                error_type=error.error_type,
                message=error.message,
            )
            return self._store_run(failed, audit_event="paper_run.failed")

        artifacts: dict[str, Any] = {
            "strategy": strategy_summary,
            "symbol_scope": symbol_scope.to_dict(),
            "analysis": {},
            "symbols": {},
        }
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

        finalization_symbol_set = set(finalization_symbols)
        analysis_by_symbol: dict[str, PaperSymbolAnalysis] = {}
        pending_finalization_symbols: list[str] = []
        llm_provider = build_llm_provider(self.settings)
        for symbol_index, symbol in enumerate(analysis_symbols, start=1):
            finalization_required = symbol in finalization_symbol_set
            abort_run = False
            try:
                analysis = self.analyze_symbol(
                    symbol=symbol,
                    run_id=run.run_id,
                    symbol_index=symbol_index,
                    succeeded_count=len(succeeded_symbols),
                    failed_count=len(failed_symbols),
                    llm_provider=llm_provider,
                )
                analysis_by_symbol[symbol] = analysis
                artifacts["analysis"][symbol] = _analysis_artifact_from_result(
                    analysis,
                    finalization_required=finalization_required,
                    finalization_status="pending" if finalization_required else "not_selected",
                )
                if finalization_required:
                    pending_finalization_symbols.append(symbol)
                else:
                    succeeded_symbols.append(symbol)
                    with bound_trace_context(
                        run_id=run.run_id,
                        debate_id=analysis.debate.debate_id,
                        proposal_id=analysis.proposal.proposal_id,
                    ):
                        self.logger.info(
                            "paper_run.symbol.analysis_completed",
                            **artifacts["analysis"][symbol],
                        )
                self._emit_progress(
                    "paper.symbol.completed",
                    run_id=run.run_id,
                    symbols=analysis_symbols,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    stage="symbol_analysis",
                    phase="analysis",
                    finalization_required=finalization_required,
                    succeeded_count=len(succeeded_symbols),
                    failed_count=len(failed_symbols),
                )
            except Exception as exc:
                analysis_artifact = artifacts["analysis"].get(symbol)
                if isinstance(analysis_artifact, dict) and finalization_required:
                    analysis_artifact["finalization_status"] = "failed"
                error = PaperRunError(
                    symbol=symbol,
                    stage="symbol_pipeline" if finalization_required else "symbol_analysis",
                    message=str(exc),
                    error_type=exc.__class__.__name__,
                )
                failed_symbols.append(symbol)
                errors.append(error)
                self._log_failure(run.run_id, error)
                self._emit_progress(
                    "paper.symbol.failed",
                    run_id=run.run_id,
                    symbols=analysis_symbols,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    stage=error.stage,
                    finalization_required=finalization_required,
                    succeeded_count=len(succeeded_symbols),
                    failed_count=len(failed_symbols),
                    error_type=error.error_type,
                    message=error.message,
                )
                abort_run = _should_abort_paper_run(exc)
                if abort_run:
                    self._emit_progress(
                        "paper.run.failed",
                        run_id=run.run_id,
                        stage=error.stage,
                        symbols=analysis_symbols,
                        error_type=error.error_type,
                        message=error.message,
                    )
            finally:
                partial_status = "FAILED" if abort_run else _status_for(
                    succeeded_symbols,
                    failed_symbols,
                )
                run = run.model_copy(
                    update={
                        "status": partial_status,
                        "completed_at": _utc_now() if abort_run else run.completed_at,
                        "succeeded_symbols": list(succeeded_symbols),
                        "failed_symbols": list(failed_symbols),
                        "errors": list(errors),
                        "artifacts": artifacts,
                    }
                )
                self._store_run(
                    run,
                    audit_event="paper_run.failed" if abort_run else None,
                )
            if abort_run:
                return run

        allocation_result: RunAllocationResult | None = None
        if analysis_by_symbol:
            try:
                self._emit_progress(
                    "paper.run.setup_started",
                    run_id=run.run_id,
                    stage="run_allocation",
                    symbols=sorted(analysis_by_symbol),
                )
                allocation_result = self._allocate_run_proposals(
                    run_id=run.run_id,
                    strategy_summary=strategy_summary,
                    core_basket_symbols=core_basket_symbols,
                    proposals=tuple(
                        analysis.proposal for analysis in analysis_by_symbol.values()
                    ),
                )
                artifacts["allocation"] = _allocation_artifact_from_result(allocation_result)
                allocation_status_by_symbol = {
                    entry.symbol: entry.status for entry in allocation_result.ledger
                }
                for symbol, status in allocation_status_by_symbol.items():
                    analysis_artifact = artifacts["analysis"].get(symbol)
                    if isinstance(analysis_artifact, dict):
                        analysis_artifact["allocation_status"] = status
                self._emit_progress(
                    "paper.run.setup_completed",
                    run_id=run.run_id,
                    stage="run_allocation",
                    symbols=sorted(analysis_by_symbol),
                    selected_count=allocation_result.summary["selected_count"],
                    not_selected_count=allocation_result.summary["not_selected_count"],
                    allocation_rejected_count=allocation_result.summary[
                        "allocation_rejected_count"
                    ],
                )
                run = run.model_copy(update={"artifacts": artifacts})
                self._store_run(run)
            except Exception as exc:
                error = PaperRunError(
                    symbol="*",
                    stage="run_allocation",
                    message=str(exc),
                    error_type=exc.__class__.__name__,
                )
                failed_symbols.extend(
                    symbol
                    for symbol in pending_finalization_symbols
                    if symbol not in failed_symbols
                )
                errors.append(error)
                self._log_failure(run.run_id, error)
                run = run.model_copy(
                    update={
                        "status": _status_for(succeeded_symbols, failed_symbols),
                        "failed_symbols": list(failed_symbols),
                        "errors": list(errors),
                        "artifacts": artifacts,
                    }
                )
                self._store_run(run)
                if _should_abort_paper_run(exc):
                    failed = run.model_copy(
                        update={
                            "status": "FAILED",
                            "completed_at": _utc_now(),
                            "succeeded_symbols": list(succeeded_symbols),
                            "failed_symbols": list(failed_symbols),
                            "errors": list(errors),
                            "artifacts": artifacts,
                        }
                    )
                    self._emit_progress(
                        "paper.run.failed",
                        run_id=failed.run_id,
                        stage=error.stage,
                        symbols=analysis_symbols,
                        error_type=error.error_type,
                        message=error.message,
                    )
                    return self._store_run(failed, audit_event="paper_run.failed")

        allocated_proposals = (
            allocation_result.proposal_by_symbol() if allocation_result is not None else {}
        )
        finalizations_by_symbol: dict[str, PaperSymbolFinalization] = {}
        for symbol in pending_finalization_symbols:
            if symbol in failed_symbols:
                continue
            analysis = analysis_by_symbol[symbol]
            symbol_index = analysis_symbols.index(symbol) + 1
            abort_run = False
            try:
                finalization = self.finalize_symbol(
                    symbol=symbol,
                    run_id=run.run_id,
                    strategy_summary=strategy_summary,
                    core_basket_symbols=core_basket_symbols,
                    proposal=allocated_proposals.get(symbol, analysis.proposal),
                    symbol_index=symbol_index,
                    succeeded_count=len(succeeded_symbols),
                    failed_count=len(failed_symbols),
                    llm_provider=llm_provider,
                    apply_allocation=False,
                    route_execution=False,
                )
                finalizations_by_symbol[symbol] = finalization
                result = _symbol_artifact_from_results(analysis, finalization)
                artifacts["symbols"][symbol] = result
                artifacts["analysis"][symbol]["finalization_status"] = "completed"
                artifacts["final_decisions"] = _final_decision_artifact(
                    finalizations_by_symbol
                )
                succeeded_symbols.append(symbol)
                with bound_trace_context(
                    run_id=run.run_id,
                    debate_id=analysis.debate.debate_id,
                    proposal_id=finalization.proposal.proposal_id,
                    risk_check_id=finalization.risk_review.risk_check_id,
                    final_decision_id=finalization.final_decision.final_decision_id,
                    order_id=finalization.order.order_id
                    if finalization.order is not None
                    else None,
                ):
                    self.logger.info("paper_run.symbol.completed", **result)
                self._emit_progress(
                    "paper.symbol.completed",
                    run_id=run.run_id,
                    symbols=analysis_symbols,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    stage="symbol_pipeline",
                    phase="finalization",
                    finalization_required=True,
                    succeeded_count=len(succeeded_symbols),
                    failed_count=len(failed_symbols),
                )
            except Exception as exc:
                artifacts["analysis"][symbol]["finalization_status"] = "failed"
                error = PaperRunError(
                    symbol=symbol,
                    stage="symbol_pipeline",
                    message=str(exc),
                    error_type=exc.__class__.__name__,
                )
                failed_symbols.append(symbol)
                errors.append(error)
                self._log_failure(run.run_id, error)
                self._emit_progress(
                    "paper.symbol.failed",
                    run_id=run.run_id,
                    symbols=analysis_symbols,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    stage=error.stage,
                    finalization_required=True,
                    succeeded_count=len(succeeded_symbols),
                    failed_count=len(failed_symbols),
                    error_type=error.error_type,
                    message=error.message,
                )
                abort_run = _should_abort_paper_run(exc)
                if abort_run:
                    self._emit_progress(
                        "paper.run.failed",
                        run_id=run.run_id,
                        stage=error.stage,
                        symbols=analysis_symbols,
                        error_type=error.error_type,
                        message=error.message,
                    )
            finally:
                partial_status = "FAILED" if abort_run else _status_for(
                    succeeded_symbols,
                    failed_symbols,
                )
                artifacts["final_decisions"] = _final_decision_artifact(
                    finalizations_by_symbol
                )
                run = run.model_copy(
                    update={
                        "status": partial_status,
                        "completed_at": _utc_now() if abort_run else run.completed_at,
                        "succeeded_symbols": list(succeeded_symbols),
                        "failed_symbols": list(failed_symbols),
                        "errors": list(errors),
                        "artifacts": artifacts,
                    }
                )
                self._store_run(
                    run,
                    audit_event="paper_run.failed" if abort_run else None,
                )
            if abort_run:
                return run

        if allocation_result is not None and finalizations_by_symbol:
            execution_artifact, execution_errors = self._route_run_execution(
                run_id=run.run_id,
                analysis_symbols=analysis_symbols,
                finalizations_by_symbol=finalizations_by_symbol,
                allocation_result=allocation_result,
                artifacts=artifacts,
                succeeded_count=len(succeeded_symbols),
                failed_count=len(failed_symbols),
            )
            artifacts["execution"] = execution_artifact
            for error in execution_errors:
                if error.symbol not in failed_symbols:
                    failed_symbols.append(error.symbol)
                errors.append(error)
            run = run.model_copy(
                update={
                    "status": _status_for(succeeded_symbols, failed_symbols),
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

    def _run_symbol(
        self,
        *,
        symbol: str,
        run_id: str,
        strategy_summary: dict[str, object],
        core_basket_symbols: set[str],
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> dict[str, object]:
        llm_provider = build_llm_provider(self.settings)
        analysis = self.analyze_symbol(
            symbol=symbol,
            run_id=run_id,
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            llm_provider=llm_provider,
        )
        finalization = self.finalize_symbol(
            symbol=symbol,
            run_id=run_id,
            strategy_summary=strategy_summary,
            core_basket_symbols=core_basket_symbols,
            proposal=analysis.proposal,
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            llm_provider=llm_provider,
        )
        result = _symbol_artifact_from_results(analysis, finalization)
        with bound_trace_context(
            run_id=run_id,
            debate_id=analysis.debate.debate_id,
            proposal_id=finalization.proposal.proposal_id,
            risk_check_id=finalization.risk_review.risk_check_id,
            final_decision_id=finalization.final_decision.final_decision_id,
            order_id=finalization.order.order_id if finalization.order is not None else None,
        ):
            self.logger.info("paper_run.symbol.completed", **result)
        return result

    def analyze_symbol(
        self,
        *,
        symbol: str,
        run_id: str,
        symbol_index: int = 1,
        succeeded_count: int = 0,
        failed_count: int = 0,
        llm_provider: LLMProvider | None = None,
    ) -> PaperSymbolAnalysis:
        symbol = symbol.upper()
        with bound_trace_context(run_id=run_id):
            self.logger.info("paper_run.symbol.started", symbol=symbol)

        enabled_analysts = self.settings.enabled_analyst_keys
        llm_provider = llm_provider or build_llm_provider(self.settings)
        reports = self._run_symbol_analyst_suite(
            symbol=symbol,
            run_id=run_id,
            enabled_analysts=enabled_analysts,
            llm_provider=llm_provider,
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        debate = self._run_symbol_research_debate(
            symbol=symbol,
            run_id=run_id,
            llm_provider=llm_provider,
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        proposal = self._run_symbol_trader_proposal(
            symbol=symbol,
            run_id=run_id,
            debate=debate,
            llm_provider=llm_provider,
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        return PaperSymbolAnalysis(
            symbol=symbol,
            enabled_analysts=list(enabled_analysts),
            reports=reports,
            debate=debate,
            proposal=proposal,
        )

    def finalize_symbol(
        self,
        *,
        symbol: str,
        run_id: str,
        strategy_summary: dict[str, object],
        core_basket_symbols: set[str],
        proposal: TraderProposal | None = None,
        symbol_index: int = 1,
        succeeded_count: int = 0,
        failed_count: int = 0,
        llm_provider: LLMProvider | None = None,
        apply_allocation: bool = True,
        route_execution: bool = True,
    ) -> PaperSymbolFinalization:
        symbol = symbol.upper()
        proposal_source = "in_memory" if proposal is not None else "stored"
        proposal = proposal or self._load_symbol_proposal(symbol=symbol, run_id=run_id)
        self._validate_symbol_proposal(symbol=symbol, run_id=run_id, proposal=proposal)
        if apply_allocation:
            proposal = self._allocate_symbol_proposal(
                symbol=symbol,
                proposal=proposal,
                strategy_summary=strategy_summary,
                core_basket_symbols=core_basket_symbols,
                symbol_index=symbol_index,
                succeeded_count=succeeded_count,
                failed_count=failed_count,
            )
        else:
            proposal = self._use_run_level_allocation(
                symbol=symbol,
                proposal=proposal,
                symbol_index=symbol_index,
                succeeded_count=succeeded_count,
                failed_count=failed_count,
            )
        review = self._run_symbol_risk_review(
            symbol=symbol,
            run_id=run_id,
            proposal=proposal,
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        decision = self._run_symbol_portfolio_manager_final_decision(
            symbol=symbol,
            run_id=run_id,
            review=review,
            llm_provider=llm_provider or build_llm_provider(self.settings),
            symbol_index=symbol_index,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        order = None
        account = None
        if route_execution:
            order, account = self._route_symbol_execution(
                decision=decision,
                run_id=run_id,
                symbol=symbol,
                symbol_index=symbol_index,
                succeeded_count=succeeded_count,
                failed_count=failed_count,
            )
        return PaperSymbolFinalization(
            symbol=symbol,
            proposal=proposal,
            proposal_source=proposal_source,
            risk_review=review,
            final_decision=decision,
            order=order,
            account=account,
        )

    def _run_symbol_analyst_suite(
        self,
        *,
        symbol: str,
        run_id: str,
        enabled_analysts: list[str],
        llm_provider: LLMProvider,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> list[AnalystReport]:
        self._emit_symbol_stage_started(
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="analyst_suite",
            terminal_stage="analysts",
            phase="analysis",
            method="run_analyst_suite",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        with self.session_factory() as session:
            return run_analyst_suite(
                session,
                symbol=symbol,
                run_id=run_id,
                llm_provider=llm_provider,
                enabled_analysts=enabled_analysts,
            )

    def _run_symbol_research_debate(
        self,
        *,
        symbol: str,
        run_id: str,
        llm_provider: LLMProvider,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> DebateReport:
        self._emit_symbol_stage_started(
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="research_debate",
            terminal_stage="debate",
            phase="analysis",
            method="ResearchDebateService.run",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        with self.session_factory() as session:
            return ResearchDebateService(
                session,
                settings=self.settings,
                llm_provider=llm_provider,
            ).run(
                symbol=symbol,
                run_id=run_id,
                rounds_requested=self.rounds_requested,
            )

    def _run_symbol_trader_proposal(
        self,
        *,
        symbol: str,
        run_id: str,
        debate: DebateReport,
        llm_provider: LLMProvider,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> TraderProposal:
        self._emit_symbol_stage_started(
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="trader_proposal",
            terminal_stage="trader",
            phase="analysis",
            method="TraderAgent.run",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        with self.session_factory() as session:
            return TraderAgent(
                session,
                self.settings,
                llm_provider=llm_provider,
            ).run(symbol=symbol, run_id=run_id, debate=debate)

    def _allocate_symbol_proposal(
        self,
        *,
        symbol: str,
        proposal: TraderProposal,
        strategy_summary: dict[str, object],
        core_basket_symbols: set[str],
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> TraderProposal:
        self._emit_symbol_stage_started(
            run_id=proposal.run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="allocation",
            terminal_stage="allocation",
            phase="finalization",
            method="PaperRunService._apply_active_allocation",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        return self._apply_active_allocation(
            symbol=symbol,
            proposal=proposal,
            strategy_summary=strategy_summary,
            core_basket_symbols=core_basket_symbols,
        )

    def _use_run_level_allocation(
        self,
        *,
        symbol: str,
        proposal: TraderProposal,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> TraderProposal:
        self._emit_symbol_stage_started(
            run_id=proposal.run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="allocation",
            terminal_stage="allocation",
            phase="finalization",
            method="PaperRunService._use_run_level_allocation",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        return proposal

    def _run_symbol_risk_review(
        self,
        *,
        symbol: str,
        run_id: str,
        proposal: TraderProposal,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> RiskReview:
        self._emit_symbol_stage_started(
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="risk_review",
            terminal_stage="risk",
            phase="finalization",
            method="RiskReviewService.run",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
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
            return review

    def _run_symbol_portfolio_manager_final_decision(
        self,
        *,
        symbol: str,
        run_id: str,
        review: RiskReview,
        llm_provider: LLMProvider,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> FinalDecision:
        self._emit_symbol_stage_started(
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="portfolio_manager_final_decision",
            terminal_stage="portfolio_manager",
            phase="finalization",
            method="PortfolioManagerAgent.run",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        with self.session_factory() as session:
            return PortfolioManagerAgent(
                session,
                self.settings,
                llm_provider=llm_provider,
            ).run(
                symbol=symbol,
                run_id=run_id,
                risk_review=review,
            )

    def _route_symbol_execution(
        self,
        *,
        decision: FinalDecision,
        run_id: str,
        symbol: str,
        symbol_index: int,
        succeeded_count: int,
        failed_count: int,
    ) -> tuple[PaperOrder | None, Any | None]:
        self._emit_symbol_stage_started(
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage="execution_routing",
            terminal_stage="execution",
            phase="finalization",
            method="ExecutionRouter.route_decision",
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )
        with self.session_factory() as session:
            order = ExecutionRouter(session, self.settings).route_decision(decision)
            repo = ExecutionRepository(session)
            account = repo.latest_account(run_id=run_id)
            return order, account

    def _route_run_execution(
        self,
        *,
        run_id: str,
        analysis_symbols: list[str],
        finalizations_by_symbol: dict[str, PaperSymbolFinalization],
        allocation_result: RunAllocationResult,
        artifacts: dict[str, Any],
        succeeded_count: int,
        failed_count: int,
    ) -> tuple[dict[str, object], list[PaperRunError]]:
        execution_entries = _allocation_execution_entries(allocation_result)
        ledger_by_symbol = _allocation_ledger_by_symbol(allocation_result)
        execution_set: list[dict[str, object]] = []
        routed_orders: list[dict[str, object]] = []
        skipped_symbols: list[dict[str, object]] = []
        errors: list[PaperRunError] = []

        for symbol, finalization in finalizations_by_symbol.items():
            entry = ledger_by_symbol.get(symbol)
            execution_entry = execution_entries.get(symbol)
            if execution_entry is None:
                skipped_symbols.append(
                    _execution_skip_artifact(
                        symbol=symbol,
                        entry=entry,
                        decision=finalization.final_decision,
                    )
                )
                continue

            execution_set.append(
                _execution_set_artifact(
                    entry=execution_entry,
                    decision=finalization.final_decision,
                )
            )
            symbol_index = analysis_symbols.index(symbol) + 1
            try:
                order, account = self._route_symbol_execution(
                    decision=finalization.final_decision,
                    run_id=run_id,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    succeeded_count=succeeded_count,
                    failed_count=failed_count,
                )
                symbol_artifact = artifacts.get("symbols", {}).get(symbol)
                if isinstance(symbol_artifact, dict):
                    symbol_artifact["order_id"] = order.order_id if order is not None else None
                    symbol_artifact["order_status"] = order.status if order is not None else None
                    symbol_artifact["account_id"] = (
                        account.account_id if account is not None else None
                    )
                if order is None:
                    skipped_symbols.append(
                        _execution_skip_artifact(
                            symbol=symbol,
                            entry=entry,
                            decision=finalization.final_decision,
                            reason=_final_decision_not_routed_reason(
                                finalization.final_decision
                            ),
                        )
                    )
                    continue
                routed_orders.append(
                    {
                        "symbol": symbol,
                        "order_id": order.order_id,
                        "order_status": order.status,
                        "final_decision_id": order.final_decision_id,
                        "allocation_status": execution_entry.status,
                    }
                )
            except Exception as exc:
                error = PaperRunError(
                    symbol=symbol,
                    stage="execution_routing",
                    message=str(exc),
                    error_type=exc.__class__.__name__,
                )
                errors.append(error)
                skipped_symbols.append(
                    _execution_skip_artifact(
                        symbol=symbol,
                        entry=entry,
                        decision=finalization.final_decision,
                        reason=f"execution_routing_failed:{error.error_type}",
                    )
                )
                self._log_failure(run_id, error)
                self._emit_progress(
                    "paper.symbol.failed",
                    run_id=run_id,
                    symbols=analysis_symbols,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    stage=error.stage,
                    finalization_required=True,
                    succeeded_count=succeeded_count,
                    failed_count=failed_count + len(errors),
                    error_type=error.error_type,
                    message=error.message,
                )

        return (
            {
                "execution_set": execution_set,
                "execution_set_count": len(execution_set),
                "routed_orders": routed_orders,
                "routed_order_count": len(routed_orders),
                "skipped_symbols": skipped_symbols,
                "skipped_symbol_count": len(skipped_symbols),
            },
            errors,
        )

    def _load_symbol_proposal(self, *, symbol: str, run_id: str) -> TraderProposal:
        with self.session_factory() as session:
            model = ResearchRepository(session).latest_trader_proposal(
                run_id=run_id,
                symbol=symbol,
            )
            if model is None:
                raise ValueError(
                    f"No trader proposal found for {symbol.upper()} run_id={run_id}. "
                    "Run symbol analysis before finalization."
                )
            return TraderProposal.model_validate(model.payload)

    def _validate_symbol_proposal(
        self,
        *,
        symbol: str,
        run_id: str,
        proposal: TraderProposal,
    ) -> None:
        if proposal.symbol != symbol.upper():
            raise ValueError("Trader proposal symbol does not match finalization symbol.")
        if proposal.run_id != run_id:
            raise ValueError("Trader proposal run_id does not match finalization run_id.")

    def _emit_symbol_stage_started(
        self,
        *,
        run_id: str,
        symbol: str,
        symbol_index: int,
        stage: str,
        terminal_stage: str,
        phase: str,
        method: str,
        succeeded_count: int,
        failed_count: int,
    ) -> None:
        self._emit_progress(
            "paper.symbol.stage_started",
            run_id=run_id,
            symbol=symbol,
            symbol_index=symbol_index,
            stage=stage,
            terminal_stage=terminal_stage,
            phase=phase,
            method=method,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )

    def _apply_active_allocation(
        self,
        *,
        symbol: str,
        proposal,
        strategy_summary: dict[str, object],
        core_basket_symbols: set[str],
    ):
        if not self.settings.taurus_money_management_enabled:
            return proposal

        policy = load_money_management_policy_for_settings(self.settings)
        strategy_name = str(strategy_summary.get("strategy_name") or "")
        signal = _strategy_signal_for_symbol(strategy_summary, symbol)
        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            account = execution_repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            nav_inr = (
                account.equity_inr
                if account is not None
                else Decimal(str(self.settings.taurus_initial_capital_inr))
            )
            available_cash = (
                account.available_cash_inr
                if account is not None
                else Decimal(str(self.settings.taurus_initial_capital_inr))
            )
            open_positions = tuple(
                ActiveAllocationPosition(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    market_value_inr=position.market_value_inr,
                )
                for position in execution_repo.latest_open_positions_by_portfolio(
                    portfolio_id=self.settings.taurus_paper_portfolio_id,
                )
            )
            history = tuple(_daily_candle_history(session, symbol))
            concentration_symbols = {symbol.upper()} | {
                position.symbol.upper() for position in open_positions
            }
            sector_by_symbol, graph_cluster_by_symbol = _core_concentration_groups(
                session,
                symbols=concentration_symbols,
            )
            sleeve_by_symbol = _latest_allocation_sleeves_by_symbol(session, settings=self.settings)

            allocated = PortfolioAllocationService(policy).allocate(
                ActiveAllocationInput(
                    proposal=proposal,
                    strategy_name=strategy_name,
                    nav_inr=nav_inr,
                    available_cash_inr=available_cash,
                    portfolio_starting_nav_estimate_inr=Decimal(
                        str(self.settings.taurus_initial_capital_inr)
                    ),
                    current_positions=open_positions,
                    sleeve_snapshots=_sleeve_snapshots_for_allocation(
                        policy=policy,
                        nav_inr=nav_inr,
                        positions=open_positions,
                        core_basket_symbols=core_basket_symbols,
                        sleeve_by_symbol=sleeve_by_symbol,
                    ),
                    core_basket_symbols=tuple(sorted(core_basket_symbols)),
                    history=history,
                    strategy_score=signal["score"] if signal is not None else None,
                    sector_by_symbol=sector_by_symbol,
                    graph_cluster_by_symbol=graph_cluster_by_symbol,
                )
            )
            ResearchRepository(session).replace_trader_proposal_for_run_symbol(allocated)
            session.commit()
            return allocated

    def _allocate_run_proposals(
        self,
        *,
        run_id: str,
        strategy_summary: dict[str, object],
        core_basket_symbols: set[str],
        proposals: tuple[TraderProposal, ...],
    ) -> RunAllocationResult:
        strategy_name = str(strategy_summary.get("strategy_name") or "")
        strategy_rank_by_symbol, strategy_score_by_symbol = _strategy_ranking_maps(
            strategy_summary
        )
        policy = (
            load_money_management_policy_for_settings(self.settings)
            if self.settings.taurus_money_management_enabled
            else None
        )
        fallback_policy = (
            None if policy is not None else FallbackAllocationPolicy.from_settings(self.settings)
        )
        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            account = execution_repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            nav_inr = (
                account.equity_inr
                if account is not None
                else Decimal(str(self.settings.taurus_initial_capital_inr))
            )
            available_cash = (
                account.available_cash_inr
                if account is not None
                else Decimal(str(self.settings.taurus_initial_capital_inr))
            )
            open_positions = tuple(
                ActiveAllocationPosition(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    market_value_inr=position.market_value_inr,
                )
                for position in execution_repo.latest_open_positions_by_portfolio(
                    portfolio_id=self.settings.taurus_paper_portfolio_id,
                )
            )
            proposal_symbols = {proposal.symbol.upper() for proposal in proposals}
            concentration_symbols = proposal_symbols | {
                position.symbol.upper() for position in open_positions
            }
            histories_by_symbol = {
                symbol: tuple(_daily_candle_history(session, symbol))
                for symbol in sorted(proposal_symbols)
            }
            sector_by_symbol, graph_cluster_by_symbol = _core_concentration_groups(
                session,
                symbols=concentration_symbols,
            )
            sleeve_by_symbol = (
                _latest_allocation_sleeves_by_symbol(session, settings=self.settings)
                if policy is not None
                else {}
            )
            sleeve_snapshots = (
                _sleeve_snapshots_for_allocation(
                    policy=policy,
                    nav_inr=nav_inr,
                    positions=open_positions,
                    core_basket_symbols=core_basket_symbols,
                    sleeve_by_symbol=sleeve_by_symbol,
                )
                if policy is not None
                else tuple()
            )
            result = RunLevelAllocationService().allocate(
                RunAllocationInput(
                    run_id=run_id,
                    strategy_name=strategy_name,
                    proposals=proposals,
                    nav_inr=nav_inr,
                    available_cash_inr=available_cash,
                    portfolio_starting_nav_estimate_inr=Decimal(
                        str(self.settings.taurus_initial_capital_inr)
                    ),
                    current_positions=open_positions,
                    sleeve_snapshots=sleeve_snapshots,
                    histories_by_symbol=histories_by_symbol,
                    core_basket_symbols=tuple(sorted(core_basket_symbols)),
                    strategy_rank_by_symbol=strategy_rank_by_symbol,
                    strategy_score_by_symbol=strategy_score_by_symbol,
                    sector_by_symbol=sector_by_symbol,
                    graph_cluster_by_symbol=graph_cluster_by_symbol,
                    money_management_policy=policy,
                    fallback_policy=fallback_policy,
                )
            )
            research_repo = ResearchRepository(session)
            for updated in result.proposals:
                research_repo.replace_trader_proposal_for_run_symbol(updated)
            session.commit()
            return result

    def _load_latest_inputs(self) -> dict[str, object]:
        provider = build_market_data_provider(self.settings)
        with self.session_factory() as session:
            assert_kite_runtime_preflight(session, include_paper_runs=True)
        with self.session_factory() as session:
            market_summary = import_market_data(session, provider, progress=self.progress)
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
        current_positions = self._open_position_symbols()
        strategy_input_symbols = _normalize_symbols([*symbols, *current_positions])
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
                    symbols=strategy_input_symbols,
                ).to_dict()
        feature_service = TechnicalFeatureService.from_strategy_parameters(
            strategy_config.parameters
        )
        strategy_input_symbol_set = set(strategy_input_symbols)
        with self.session_factory() as session:
            instruments = InstrumentRepository(session).list(active_only=True)
            snapshots = {}
            for instrument in instruments:
                symbol = instrument.symbol.upper()
                if symbol not in strategy_input_symbol_set:
                    continue
                history = _daily_candle_history(session, instrument.symbol)
                if len(history) < max(strategy_config.lookback_days, 1):
                    continue
                snapshot = feature_service.build_snapshot(
                    symbol=symbol,
                    as_of_date=history[-1].trade_date + timedelta(days=1),
                    history=history,
                )
                if snapshot is not None:
                    snapshots[symbol] = snapshot

        trade_dates = [snapshot.as_of_date for snapshot in snapshots.values()]
        if not trade_dates:
            return {
                "strategy_name": strategy_config.strategy_name,
                "strategy_config_path": str(strategy_config.source_path),
                "strategy_type": strategy_config.strategy_type,
                "legacy_target_limit": strategy_config.target_positions
                or self.settings.taurus_max_open_positions,
                "targets": [],
                "signals": [],
                "ranked_candidates": [],
                "eligible_symbol_count": 0,
                "ranked_symbol_count": 0,
                "strategy_ranked_symbols": [],
                "strategy_score_by_symbol": {},
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
                ).load_by_as_of_date(
                    as_of_date=trade_date,
                    symbols=strategy_input_symbols,
                )

        select_targets_with_graph = getattr(strategy, "select_targets_with_graph", None)
        select_targets_with_graph_called = graph_profile_enabled and callable(
            select_targets_with_graph
        )
        legacy_target_limit = (
            strategy_config.target_positions or self.settings.taurus_max_open_positions
        )
        rankings = strategy.rank_universe(
            trade_date=trade_date,
            features_by_symbol=snapshots,
            current_positions=current_positions,
            graph_signals_by_symbol=graph_signals_by_symbol,
        )
        if select_targets_with_graph_called:
            targets, signals = select_targets_with_graph(
                trade_date=trade_date,
                features_by_symbol=snapshots,
                current_positions=current_positions,
                graph_signals_by_symbol=graph_signals_by_symbol,
                target_limit=legacy_target_limit,
            )
        else:
            targets, signals = strategy.select_targets(
                trade_date=trade_date,
                features_by_symbol=snapshots,
                current_positions=current_positions,
                target_limit=legacy_target_limit,
            )
        requested = set(symbols)
        selected_symbols = sorted(targets)
        ranked_candidates = [ranking.to_dict() for ranking in rankings]
        strategy_ranked_symbols = [
            ranking.symbol for ranking in rankings if ranking.rank is not None
        ]
        strategy_score_by_symbol = {
            ranking.symbol: str(ranking.raw_strategy_score)
            for ranking in rankings
            if ranking.raw_strategy_score is not None
        }
        return {
            "strategy_name": strategy_config.strategy_name,
            "strategy_config_path": str(strategy_config.source_path),
            "strategy_type": strategy_config.strategy_type,
            "legacy_target_limit": legacy_target_limit,
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
            "ranked_candidates": ranked_candidates,
            "eligible_symbol_count": sum(1 for ranking in rankings if ranking.is_eligible),
            "ranked_symbol_count": sum(1 for ranking in rankings if ranking.rank is not None),
            "strategy_ranked_symbols": strategy_ranked_symbols,
            "strategy_score_by_symbol": strategy_score_by_symbol,
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
        progress: ProgressEventCallback | None = None,
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
        self.progress = progress

    def run(self) -> list[PaperRun]:
        runs: list[PaperRun] = []
        emit_progress(
            self.progress,
            "paper.loop.started",
            iterations=self.iterations,
            symbol_count=max(len(self.symbols), 1),
            symbols=self.symbols,
        )
        for index in range(self.iterations):
            iteration = index + 1
            self.service.configure_progress_context(
                iteration=iteration,
                iterations=self.iterations,
                symbol_count=max(len(self.symbols), 1),
            )
            emit_progress(
                self.progress,
                "paper.iteration.started",
                iteration=iteration,
                iterations=self.iterations,
                symbol_count=max(len(self.symbols), 1),
                symbols=self.symbols,
            )
            run = self.service.run_once(
                symbols=self.symbols,
                universe=self.universe,
                strategy_config_path=self.strategy_config_path,
            )
            runs.append(run)
            emit_progress(
                self.progress,
                "paper.iteration.completed",
                iteration=iteration,
                iterations=self.iterations,
                symbol_count=max(len(run.symbols), 1),
                symbols=list(run.symbols),
                run_id=run.run_id,
                status=run.status,
                succeeded_count=len(run.succeeded_symbols),
                failed_count=len(run.failed_symbols),
            )
            if index < self.iterations - 1 and self.interval_seconds > 0:
                time.sleep(self.interval_seconds)
        emit_progress(
            self.progress,
            "paper.loop.completed",
            iterations=self.iterations,
            symbol_count=max(len(runs[-1].symbols) if runs else len(self.symbols), 1),
            symbols=list(runs[-1].symbols) if runs else self.symbols,
        )
        return runs


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    normalized = []
    for value in symbols:
        for symbol in str(value).split(","):
            cleaned = symbol.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
    return normalized


def _symbol_artifact_from_results(
    analysis: PaperSymbolAnalysis,
    finalization: PaperSymbolFinalization,
) -> dict[str, object]:
    proposal = finalization.proposal
    review = finalization.risk_review
    decision = finalization.final_decision
    order = finalization.order
    account = finalization.account
    result = {
        "symbol": analysis.symbol,
        "report_ids": [report.report_id for report in analysis.reports],
        "analyst_roster": _analyst_roster_dict(
            enabled_analysts=analysis.enabled_analysts,
            report_count=len(analysis.reports),
        ),
        "debate_id": analysis.debate.debate_id,
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
    if proposal.allocation_decision is not None:
        result["allocation_decision"] = proposal.allocation_decision.model_dump(mode="json")
    return result


def _allocation_artifact_from_result(
    allocation_result: RunAllocationResult,
) -> dict[str, object]:
    artifact = allocation_result.to_artifact()
    artifact["ledger_count"] = len(allocation_result.ledger)
    artifact["ledger_counts"] = dict(
        sorted(Counter(entry.status for entry in allocation_result.ledger).items())
    )
    return artifact


def _final_decision_artifact(
    finalizations_by_symbol: dict[str, PaperSymbolFinalization],
) -> dict[str, object]:
    decisions = [finalization.final_decision for finalization in finalizations_by_symbol.values()]
    return {
        "total_count": len(decisions),
        "symbols": sorted(finalizations_by_symbol),
        "by_status": dict(sorted(Counter(decision.status for decision in decisions).items())),
        "by_action": dict(
            sorted(Counter(decision.final_action for decision in decisions).items())
        ),
    }


def _allocation_ledger_by_symbol(allocation_result: RunAllocationResult) -> dict[str, Any]:
    return {entry.symbol.upper(): entry for entry in allocation_result.ledger}


def _allocation_execution_entries(allocation_result: RunAllocationResult) -> dict[str, Any]:
    execution_entries: dict[str, Any] = {}
    for entry in allocation_result.ledger:
        symbol = entry.symbol.upper()
        if entry.status in SELECTED_LEDGER_STATUSES and entry.approved_quantity > 0:
            execution_entries[symbol] = entry
        elif entry.status == "open_position_management" and entry.action in {"REDUCE", "EXIT"}:
            execution_entries[symbol] = entry
    return execution_entries


def _execution_set_artifact(*, entry: Any, decision: FinalDecision) -> dict[str, object]:
    reason = (
        "open_position_lifecycle"
        if entry.status == "open_position_management"
        else "selected_by_run_allocation"
    )
    return {
        "symbol": entry.symbol,
        "proposal_id": entry.proposal_id,
        "final_decision_id": decision.final_decision_id,
        "allocation_status": entry.status,
        "final_status": decision.status,
        "final_action": decision.final_action,
        "reason": reason,
    }


def _execution_skip_artifact(
    *,
    symbol: str,
    entry: Any | None,
    decision: FinalDecision,
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "proposal_id": entry.proposal_id if entry is not None else decision.proposal_id,
        "final_decision_id": decision.final_decision_id,
        "allocation_status": entry.status if entry is not None else None,
        "binding_constraint": entry.binding_constraint if entry is not None else None,
        "final_status": decision.status,
        "final_action": decision.final_action,
        "reason": reason or _execution_skip_reason(entry=entry, decision=decision),
    }


def _execution_skip_reason(*, entry: Any | None, decision: FinalDecision) -> str:
    if entry is None:
        return "missing_allocation_ledger_entry"
    if entry.status == "not_selected":
        return "not_selected_by_run_allocation"
    if entry.status == "allocation_rejected":
        binding = entry.binding_constraint or "none"
        return f"allocation_rejected_by_run_allocation:{binding}"
    if decision.final_action in {"HOLD", "NO_TRADE"}:
        return f"{decision.final_action.lower()}_no_paper_order_expected"
    return f"not_in_allocation_execution_set:{entry.status}"


def _final_decision_not_routed_reason(decision: FinalDecision) -> str:
    if decision.status != "APPROVED_FOR_PAPER":
        return f"final_decision_not_broker_routable:{decision.status.lower()}"
    if decision.can_send_to_broker is not True:
        return "final_decision_not_broker_routable:can_send_to_broker_false"
    if decision.approved_quantity <= 0:
        return "final_decision_not_broker_routable:zero_approved_quantity"
    return "execution_router_returned_no_order"


def _analysis_artifact_from_result(
    analysis: PaperSymbolAnalysis,
    *,
    finalization_required: bool,
    finalization_status: str,
) -> dict[str, object]:
    proposal = analysis.proposal
    return {
        "symbol": analysis.symbol,
        "analysis_status": "completed",
        "report_ids": [report.report_id for report in analysis.reports],
        "analyst_roster": _analyst_roster_dict(
            enabled_analysts=analysis.enabled_analysts,
            report_count=len(analysis.reports),
        ),
        "debate_id": analysis.debate.debate_id,
        "proposal_id": proposal.proposal_id,
        "proposal_action": proposal.action,
        "portfolio_id": proposal.portfolio_id,
        "lifecycle_trigger": proposal.lifecycle_trigger,
        "evaluation_mode": proposal.evaluation_mode,
        "current_position_quantity": proposal.current_position_quantity,
        "current_position_pct_nav": str(proposal.current_position_pct_nav),
        "target_position_pct_nav": str(proposal.target_position_pct_nav),
        "position_management_summary": proposal.position_management_summary,
        "finalization_required": finalization_required,
        "finalization_status": finalization_status,
    }


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


def _symbol_scope_for_run(
    *,
    settings: Settings,
    requested_symbols: list[str],
    universe: PaperRunUniverse | None,
    strategy_summary: dict[str, object],
) -> PaperRunSymbolScope:
    requested = _normalize_symbols(requested_symbols)
    open_positions = _normalize_symbols(
        [str(symbol) for symbol in strategy_summary.get("open_position_symbols", [])]
    )
    strategy_selected = _normalize_symbols(
        [str(symbol) for symbol in strategy_summary.get("targets", [])]
    )
    graph_selected = _normalize_symbols(
        [str(symbol) for symbol in strategy_summary.get("graph_selected_symbols", [])]
    )
    strategy_ranked = _normalize_symbols(
        [str(symbol) for symbol in strategy_summary.get("strategy_ranked_symbols", [])]
    )
    universe_mode = universe.source if universe is not None else "manual_symbols"
    requested_universe_symbols = requested if universe_mode == "market_data_universe" else []
    manual_symbols = requested if universe_mode == "manual_symbols" else []

    if settings.taurus_paper_analysis_scope == "full_universe":
        if universe_mode == "market_data_universe":
            analyzed = _normalize_symbols([*requested, *open_positions])
            finalization = list(analyzed)
        else:
            analyzed = _normalize_symbols([*requested, *open_positions])
            finalization = list(analyzed)
    else:
        finalization = _symbols_for_pipeline(
            requested_symbols=requested,
            universe=universe,
            strategy_summary=strategy_summary,
        )
        analyzed = list(finalization)

    analyzed = _normalize_symbols([*analyzed, *finalization])
    effective_execution_scope = settings.taurus_paper_execution_scope
    return PaperRunSymbolScope(
        analysis_scope=settings.taurus_paper_analysis_scope,
        execution_scope=settings.taurus_paper_execution_scope,
        effective_execution_scope=effective_execution_scope,
        requested_symbols=requested,
        requested_universe_symbols=requested_universe_symbols,
        manual_symbols=manual_symbols,
        analyzed_symbols=analyzed,
        finalization_symbols=finalization,
        strategy_selected_symbols=strategy_selected,
        strategy_ranked_symbols=strategy_ranked,
        graph_selected_symbols=graph_selected,
        open_position_symbols=open_positions,
    )


def _strategy_summary_with_symbol_scope(
    strategy_summary: dict[str, object],
    *,
    symbol_scope: PaperRunSymbolScope,
) -> dict[str, object]:
    scoped = dict(strategy_summary)
    scope_payload = symbol_scope.to_dict()
    scoped["symbol_scope"] = scope_payload
    scoped["analysis_scope"] = symbol_scope.analysis_scope
    scoped["execution_scope"] = symbol_scope.execution_scope
    scoped["effective_execution_scope"] = symbol_scope.effective_execution_scope
    scoped["requested_symbols"] = list(symbol_scope.requested_symbols)
    scoped["requested_universe_symbols"] = list(symbol_scope.requested_universe_symbols)
    scoped["manual_symbols"] = list(symbol_scope.manual_symbols)
    scoped["analyzed_symbols"] = list(symbol_scope.analyzed_symbols)
    scoped["finalization_symbols"] = list(symbol_scope.finalization_symbols)
    scoped["strategy_selected_symbols"] = list(symbol_scope.strategy_selected_symbols)
    scoped["strategy_ranked_symbols"] = list(symbol_scope.strategy_ranked_symbols)
    scoped["graph_selected_symbols"] = list(symbol_scope.graph_selected_symbols)
    scoped["open_position_symbols"] = list(symbol_scope.open_position_symbols)
    return scoped


def _symbols_for_pipeline(
    *,
    requested_symbols: list[str],
    universe: PaperRunUniverse | None,
    strategy_summary: dict[str, object],
) -> list[str]:
    if universe is not None and universe.source == "market_data_universe":
        strategy_key = "graph_selected_symbols" if (
            strategy_summary.get("select_targets_with_graph_called") is True
        ) else "targets"
        selected = [
            *[str(symbol) for symbol in strategy_summary.get(strategy_key, [])],
            *[str(symbol) for symbol in strategy_summary.get("open_position_symbols", [])],
        ]
        normalized = _normalize_symbols(selected)
        if not normalized:
            raise ValueError(
                "Strategy-selected paper target selection produced no target or open-position "
                "symbols for the market-data universe."
            )
        return normalized
    return _normalize_symbols(
        [
            *requested_symbols,
            *[str(symbol) for symbol in strategy_summary.get("open_position_symbols", [])],
        ]
    )


def _strategy_signal_for_symbol(
    strategy_summary: dict[str, object],
    symbol: str,
) -> dict[str, object] | None:
    normalized = symbol.upper()
    signals = strategy_summary.get("signals")
    if not isinstance(signals, list):
        return None
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        if str(signal.get("symbol") or "").upper() != normalized:
            continue
        raw_score = signal.get("score")
        try:
            score = Decimal(str(raw_score))
        except Exception:
            score = None
        return {
            **signal,
            "score": score,
        }
    score_by_symbol = strategy_summary.get("strategy_score_by_symbol")
    if isinstance(score_by_symbol, dict):
        raw_score = score_by_symbol.get(normalized)
        try:
            score = Decimal(str(raw_score))
        except Exception:
            score = None
        if score is not None:
            return {
                "symbol": normalized,
                "score": score,
                "source": "strategy_score_by_symbol",
            }
    return None


def _strategy_ranking_maps(
    strategy_summary: dict[str, object],
) -> tuple[dict[str, int], dict[str, Decimal]]:
    rank_by_symbol: dict[str, int] = {}
    score_by_symbol: dict[str, Decimal] = {}
    ranked_candidates = strategy_summary.get("ranked_candidates")
    if isinstance(ranked_candidates, list):
        for item in ranked_candidates:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            raw_rank = item.get("rank")
            if raw_rank is not None:
                try:
                    rank_by_symbol[symbol] = int(raw_rank)
                except (TypeError, ValueError):
                    pass
            raw_score = item.get("raw_strategy_score")
            if raw_score is None:
                raw_score = item.get("normalized_score")
            if raw_score is not None:
                try:
                    score_by_symbol[symbol] = Decimal(str(raw_score))
                except Exception:
                    pass

    score_payload = strategy_summary.get("strategy_score_by_symbol")
    if isinstance(score_payload, dict):
        for raw_symbol, raw_score in score_payload.items():
            symbol = str(raw_symbol).strip().upper()
            if not symbol:
                continue
            try:
                score_by_symbol.setdefault(symbol, Decimal(str(raw_score)))
            except Exception:
                continue
    return rank_by_symbol, score_by_symbol


def _core_basket_symbols_from_summary(
    money_management_summary: dict[str, object] | None,
) -> set[str]:
    if not isinstance(money_management_summary, dict):
        return set()
    core = money_management_summary.get("core_shariah_basket")
    if not isinstance(core, dict):
        return set()
    target_weights = core.get("target_weights")
    if not isinstance(target_weights, dict):
        return set()
    return {
        str(symbol).strip().upper()
        for symbol in target_weights
        if str(symbol).strip()
    }


def _latest_allocation_sleeves_by_symbol(
    session: Session,
    *,
    settings: Settings,
) -> dict[str, str]:
    sleeves_by_symbol: dict[str, str] = {}
    for proposal in ResearchRepository(session).list_trader_proposals(
        portfolio_id=settings.taurus_paper_portfolio_id,
        limit=500,
    ):
        payload = proposal.payload or {}
        allocation_decision = payload.get("allocation_decision")
        if not isinstance(allocation_decision, dict):
            continue
        symbol = str(allocation_decision.get("symbol") or proposal.symbol).strip().upper()
        sleeve_id = str(allocation_decision.get("sleeve_id") or "").strip().lower()
        if not symbol or sleeve_id not in ALLOCATABLE_SLEEVE_IDS:
            continue
        sleeves_by_symbol.setdefault(symbol, sleeve_id)
    return sleeves_by_symbol


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


def _should_abort_paper_run(exc: Exception) -> bool:
    return isinstance(exc, SQLAlchemyError)


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


def _sleeve_snapshots_for_allocation(
    *,
    policy: MoneyManagementPolicy,
    nav_inr: Decimal,
    positions: tuple[ActiveAllocationPosition, ...],
    core_basket_symbols: set[str],
    sleeve_by_symbol: dict[str, str] | None = None,
) -> tuple[SleeveAllocationSnapshot, ...]:
    core_symbols = {symbol.upper() for symbol in core_basket_symbols}
    runtime_sleeve_by_symbol = {
        symbol.strip().upper(): sleeve_id.strip().lower()
        for symbol, sleeve_id in (sleeve_by_symbol or {}).items()
        if symbol.strip() and sleeve_id.strip()
    }
    snapshots: list[SleeveAllocationSnapshot] = []
    for sleeve in policy.sleeves:
        starting_nav = (nav_inr * sleeve.target_weight_pct / Decimal("100")).quantize(
            Decimal("0.01")
        )
        if sleeve.sleeve_id == "core_shariah":
            sleeve_positions = [
                position
                for position in positions
                if position.symbol.upper() in core_symbols
            ]
        elif sleeve.sleeve_id in ALLOCATABLE_SLEEVE_IDS:
            sleeve_positions = [
                position
                for position in positions
                if position.symbol.upper() not in core_symbols
                and runtime_sleeve_by_symbol.get(
                    position.symbol.upper(),
                    "active_strategy",
                )
                == sleeve.sleeve_id
            ]
        else:
            sleeve_positions = []
        exposure = sum(
            (position.market_value_inr for position in sleeve_positions),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        open_trade_risk = (exposure * Decimal("6.0000") / Decimal("100")).quantize(
            Decimal("0.01")
        )
        snapshots.append(
            SleeveAllocationSnapshot(
                sleeve_id=sleeve.sleeve_id,
                starting_nav_estimate_inr=starting_nav,
                current_exposure_inr=exposure,
                open_position_count=len(sleeve_positions),
                open_trade_risk_inr=open_trade_risk,
            )
        )
    return tuple(snapshots)


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
