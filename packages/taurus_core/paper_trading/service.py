from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
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
from taurus_core.brokers.paper_broker import PaperBroker
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
from taurus_core.execution.costs import IndiaPaperCostModel
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import NextOpenSettlementSummary, PaperAccount, PaperOrder
from taurus_core.features.store import TechnicalFeatureService
from taurus_core.graph.preflight import assert_graph_ready_for_paper
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm import LLMProvider, build_llm_provider
from taurus_core.llm.base import get_llm_usage_records, summarize_llm_usage
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
    PortfolioPlanAllocationService,
    PortfolioRebalancePlanInput,
    PortfolioRebalancePlanService,
    RunAllocationInput,
    RunAllocationResult,
    RunLevelAllocationService,
    SleeveAllocationSnapshot,
    load_money_management_policy_for_settings,
    severe_negative_symbols,
)
from taurus_core.portfolio.run_allocation import SELECTED_LEDGER_STATUSES
from taurus_core.profiles.runtime import RuntimeProfile, resolve_runtime_profile
from taurus_core.research.debate_service import DEFAULT_DEBATE_ROUNDS, ResearchDebateService
from taurus_core.research.schemas import (
    BearThesis,
    BullThesis,
    DebateReport,
    DebateRound,
    ResearchManagerSummary,
    TraderProposal,
)
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.risk.schemas import FinalDecision, RiskReview
from taurus_core.strategies import DEFAULT_STRATEGY_CONFIG_PATH, load_strategy_config
from taurus_core.strategies.factory import build_strategy


MONEY_QUANT = Decimal("0.01")
DEFAULT_SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT = Decimal("80.0000")

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
    pending_next_open_order_symbols: list[str]

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
            "pending_next_open_order_symbols": list(self.pending_next_open_order_symbols),
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
        self._runtime_profile: RuntimeProfile | None = None

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
            stage="profile",
            symbols=requested_symbols,
            profile_id=self.settings.effective_profile_id,
        )
        runtime_profile = self._resolve_runtime_profile()
        self._emit_progress(
            "paper.run.setup_completed",
            stage="profile",
            symbols=requested_symbols,
            profile_id=runtime_profile.profile_id,
            starting_corpus_inr=str(runtime_profile.starting_corpus_inr),
        )
        self._emit_progress(
            "paper.run.setup_started",
            stage="migrations",
            symbols=requested_symbols,
            profile_id=runtime_profile.profile_id,
            starting_corpus_inr=str(runtime_profile.starting_corpus_inr),
        )
        run_migrations(self.settings)
        self._emit_progress(
            "paper.run.setup_completed",
            stage="migrations",
            symbols=requested_symbols,
            profile_id=runtime_profile.profile_id,
            starting_corpus_inr=str(runtime_profile.starting_corpus_inr),
        )
        self._emit_progress(
            "paper.run.setup_started",
            stage="open_positions",
            symbols=requested_symbols,
        )
        open_position_symbols = sorted(self._open_position_symbols())
        self._emit_progress(
            "paper.run.setup_completed",
            stage="open_positions",
            symbols=_normalize_symbols([*requested_symbols, *open_position_symbols]),
            open_position_symbols=open_position_symbols,
        )
        self._emit_progress(
            "paper.run.setup_started",
            stage="pending_next_open_orders",
            symbols=requested_symbols,
        )
        pending_next_open_order_symbols = sorted(self._pending_next_open_order_symbols())
        input_symbols = _normalize_symbols(
            [
                *requested_symbols,
                *open_position_symbols,
                *pending_next_open_order_symbols,
            ]
        )
        analysis_symbols = list(input_symbols)
        finalization_symbols = list(input_symbols)
        self._progress_symbol_count = max(len(input_symbols), 1)
        self._emit_progress(
            "paper.run.setup_completed",
            stage="pending_next_open_orders",
            symbols=input_symbols,
            pending_next_open_order_symbols=pending_next_open_order_symbols,
        )
        started_at = _utc_now()
        run = PaperRun(
            run_id=paper_run_id(
                started_at=started_at,
                symbols=input_symbols,
                schedule_name=self.schedule_name,
                portfolio_id=runtime_profile.profile_id,
            ),
            portfolio_id=runtime_profile.profile_id,
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
            profile_id=runtime_profile.profile_id,
            starting_corpus_inr=str(runtime_profile.starting_corpus_inr),
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
                stage="settlement",
                symbols=input_symbols,
            )
            settlement_summary = self._settle_pending_next_open_orders(run_id=run.run_id)
            post_settlement_account = self._latest_paper_account()
            post_settlement_open_position_symbols = sorted(self._open_position_symbols())
            post_settlement_pending_order_symbols = sorted(
                self._pending_next_open_order_symbols()
            )
            settlement_artifact = _settlement_artifact_from_summary(
                settlement_summary,
                account=post_settlement_account,
                open_position_symbols=post_settlement_open_position_symbols,
                pending_next_open_order_symbols=post_settlement_pending_order_symbols,
            )
            strategy_scope_symbols = _normalize_symbols(
                [
                    *requested_symbols,
                    *post_settlement_open_position_symbols,
                    *pending_next_open_order_symbols,
                    *post_settlement_pending_order_symbols,
                ]
            )
            self._progress_symbol_count = max(len(strategy_scope_symbols), 1)
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="settlement",
                symbols=strategy_scope_symbols,
                settled_count=settlement_summary.settled,
                rejected_count=settlement_summary.rejected,
                still_pending_count=settlement_summary.still_pending,
                skipped_count=settlement_summary.skipped,
            )
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="strategy",
                symbols=strategy_scope_symbols,
            )
            strategy_summary = self._generate_strategy_summary(
                symbols=strategy_scope_symbols,
                requested_symbols=requested_symbols,
                pre_settlement_pending_order_symbols=pending_next_open_order_symbols,
                pending_next_open_order_symbols=post_settlement_pending_order_symbols,
                universe=run.universe,
                strategy_config_path=strategy_config_path,
            )
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="strategy",
                symbols=strategy_scope_symbols,
            )
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="money_management",
                symbols=strategy_scope_symbols,
            )
            money_management_summary = self._generate_money_management_summary()
            self._emit_progress(
                "paper.run.setup_completed",
                run_id=run.run_id,
                stage="money_management",
                symbols=strategy_scope_symbols,
            )
            core_basket_symbols = _core_basket_symbols_from_summary(money_management_summary)
            self._emit_progress(
                "paper.run.setup_started",
                run_id=run.run_id,
                stage="symbol_selection",
                symbols=strategy_scope_symbols,
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
                    "artifacts": {"profile": runtime_profile.to_artifact()},
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
            "profile": runtime_profile.to_artifact(),
            "settlement": settlement_artifact,
            "strategy": strategy_summary,
            "symbol_scope": symbol_scope.to_dict(),
            "analysis": {},
            "symbols": {},
        }
        if money_management_summary is not None:
            artifacts["money_management"] = money_management_summary
        settlement_by_symbol = settlement_artifact.get("by_symbol")
        if not isinstance(settlement_by_symbol, dict):
            settlement_by_symbol = {}
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
        self._refresh_llm_usage_artifact(artifacts, llm_provider)
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
                if symbol in settlement_by_symbol:
                    artifacts["analysis"][symbol]["settlement"] = settlement_by_symbol[symbol]
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
                self._refresh_llm_usage_artifact(artifacts, llm_provider)
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
                    stage="portfolio_plan",
                    symbols=sorted(analysis_by_symbol),
                )
                portfolio_plan = self._build_portfolio_rebalance_plan(
                    run_id=run.run_id,
                    strategy_summary=strategy_summary,
                    money_management_summary=money_management_summary,
                    core_basket_symbols=core_basket_symbols,
                    proposals=tuple(
                        analysis.proposal for analysis in analysis_by_symbol.values()
                    ),
                )
                artifacts["portfolio_plan"] = portfolio_plan.to_artifact()
                self._emit_progress(
                    "paper.run.setup_completed",
                    run_id=run.run_id,
                    stage="portfolio_plan",
                    symbols=sorted(analysis_by_symbol),
                    planned_trade_count=len(portfolio_plan.planned_trades),
                    candidate_count=len(portfolio_plan.candidates),
                )
                self._refresh_llm_usage_artifact(artifacts, llm_provider)
                run = run.model_copy(update={"artifacts": artifacts})
                self._store_run(run)

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
                    portfolio_plan=portfolio_plan,
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
                self._refresh_llm_usage_artifact(artifacts, llm_provider)
                run = run.model_copy(update={"artifacts": artifacts})
                self._store_run(run)
                generated_symbols = _planner_generated_symbols(allocation_result)
                for generated in allocation_result.proposals:
                    symbol = generated.symbol.upper()
                    if symbol not in generated_symbols or symbol in analysis_by_symbol:
                        continue
                    synthetic_analysis = _generated_core_analysis(generated)
                    analysis_by_symbol[symbol] = synthetic_analysis
                    artifacts["analysis"][symbol] = _analysis_artifact_from_result(
                        synthetic_analysis,
                        finalization_required=True,
                        finalization_status="pending",
                    )
                    pending_finalization_symbols.append(symbol)
                    finalization_symbol_set.add(symbol)
                if generated_symbols:
                    analysis_symbols = _unique_symbols(
                        [*analysis_symbols, *sorted(generated_symbols)]
                    )
                    self._progress_symbol_count = max(len(analysis_symbols), 1)
                    finalization_symbols = _unique_symbols(
                        [*finalization_symbols, *sorted(generated_symbols)]
                    )
                    symbol_scope = _symbol_scope_with_finalization_symbols(
                        symbol_scope,
                        finalization_symbols,
                    )
                    artifacts["symbol_scope"] = symbol_scope.to_dict()
                    run = _run_with_selected_symbols(
                        run,
                        analysis_symbols,
                    )
                    run = self._store_run(run.model_copy(update={"artifacts": artifacts}))
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
                self._refresh_llm_usage_artifact(artifacts, llm_provider)
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
                    self._refresh_llm_usage_artifact(artifacts, llm_provider)
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
            symbol_index = _symbol_progress_index(analysis_symbols, symbol)
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
                if symbol in settlement_by_symbol:
                    result["settlement"] = settlement_by_symbol[symbol]
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
                self._refresh_llm_usage_artifact(artifacts, llm_provider)
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
            self._refresh_llm_usage_artifact(artifacts, llm_provider)
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

        self._refresh_llm_usage_artifact(artifacts, llm_provider)
        completed = run.model_copy(
            update={
                "status": _status_for(succeeded_symbols, failed_symbols),
                "completed_at": _utc_now(),
                "artifacts": artifacts,
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
                portfolio_id=self.settings.taurus_paper_portfolio_id,
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
                profile_id=self.settings.taurus_paper_portfolio_id,
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
        submitted_at: datetime | None = None,
        pending_affordability_cash_inr: Decimal | None = None,
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
            execution_policy = "next_open" if self.run_after_market_close else "immediate"
            order = ExecutionRouter(session, self.settings).route_decision(
                decision,
                execution_policy=execution_policy,
                submitted_at=submitted_at,
                pending_affordability_cash_inr=pending_affordability_cash_inr,
            )
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
        pending_affordability_cash = (
            self._initial_pending_affordability_cash()
            if self.run_after_market_close
            else None
        )
        submitted_at_base = _utc_now()

        for sequence, symbol in enumerate(
            _execution_symbol_order(
                finalizations_by_symbol,
                allocation_result=allocation_result,
            ),
            start=1,
        ):
            finalization = finalizations_by_symbol[symbol]
            normalized_symbol = symbol.upper()
            entry = ledger_by_symbol.get(normalized_symbol)
            execution_entry = execution_entries.get(normalized_symbol)
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
            symbol_index = _symbol_progress_index(analysis_symbols, symbol)
            try:
                order, account = self._route_symbol_execution(
                    decision=finalization.final_decision,
                    run_id=run_id,
                    symbol=symbol,
                    symbol_index=symbol_index,
                    succeeded_count=succeeded_count,
                    failed_count=failed_count,
                    submitted_at=submitted_at_base + timedelta(seconds=sequence),
                    pending_affordability_cash_inr=(
                        pending_affordability_cash
                        if (
                            self.run_after_market_close
                            and finalization.final_decision.final_action == "BUY"
                        )
                        else None
                    ),
                )
                if self.run_after_market_close and order is not None:
                    if order.side == "SELL":
                        pending_affordability_cash = _add_optional_decimal(
                            pending_affordability_cash,
                            _same_run_sell_spendable_proceeds(
                                order=order,
                                entry=execution_entry,
                                settings=self.settings,
                            ),
                        )
                    elif order.side == "BUY":
                        pending_affordability_cash = _subtract_optional_decimal(
                            pending_affordability_cash,
                            _accepted_buy_debit(
                                order=order,
                                entry=execution_entry,
                                settings=self.settings,
                            ),
                        )
                symbol_artifact = artifacts.get("symbols", {}).get(symbol) or artifacts.get(
                    "symbols", {}
                ).get(normalized_symbol)
                if isinstance(symbol_artifact, dict):
                    symbol_artifact["order_id"] = order.order_id if order is not None else None
                    symbol_artifact["order_status"] = order.status if order is not None else None
                    symbol_artifact["order_reason"] = _order_artifact_reason(order)
                    symbol_artifact["account_id"] = (
                        account.account_id if account is not None else None
                    )
                    symbol_artifact["execution_funding"] = _execution_funding_artifact(
                        execution_entry
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
                        "reason": _order_artifact_reason(order),
                        "final_decision_id": order.final_decision_id,
                        "allocation_status": execution_entry.status,
                        **_execution_funding_artifact(execution_entry),
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
            starting_corpus = self._starting_corpus_inr(session)
            nav_inr = (
                account.equity_inr
                if account is not None
                else starting_corpus
            )
            available_cash = (
                account.available_cash_inr
                if account is not None
                else starting_corpus
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
                    portfolio_starting_nav_estimate_inr=starting_corpus,
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
        portfolio_plan: Any | None = None,
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
            starting_corpus = self._starting_corpus_inr(session)
            nav_inr = (
                account.equity_inr
                if account is not None
                else starting_corpus
            )
            available_cash = (
                account.available_cash_inr
                if account is not None
                else starting_corpus
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
            plan_trade_symbols = _portfolio_plan_trade_symbols(portfolio_plan)
            proposal_symbols = {proposal.symbol.upper() for proposal in proposals}
            concentration_symbols = proposal_symbols | {
                position.symbol.upper() for position in open_positions
            } | plan_trade_symbols
            histories_by_symbol = {
                symbol: tuple(_daily_candle_history(session, symbol))
                for symbol in sorted(proposal_symbols | plan_trade_symbols)
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
            allocation_input = RunAllocationInput(
                run_id=run_id,
                strategy_name=strategy_name,
                proposals=proposals,
                nav_inr=nav_inr,
                available_cash_inr=available_cash,
                portfolio_starting_nav_estimate_inr=starting_corpus,
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
            if (
                policy is not None
                and self.settings.taurus_portfolio_plan_allocation_enabled
                and portfolio_plan is not None
            ):
                result = PortfolioPlanAllocationService().allocate(
                    allocation_input,
                    portfolio_plan=portfolio_plan,
                )
            else:
                result = RunLevelAllocationService().allocate(allocation_input)
            research_repo = ResearchRepository(session)
            for updated in result.proposals:
                if _is_planner_generated_proposal(updated):
                    research_repo.replace_debate_for_run_symbol(
                        _synthetic_portfolio_rebalance_debate(updated)
                    )
                research_repo.replace_trader_proposal_for_run_symbol(updated)
            session.commit()
            return result

    def _build_portfolio_rebalance_plan(
        self,
        *,
        run_id: str,
        strategy_summary: dict[str, object],
        money_management_summary: dict[str, object] | None,
        core_basket_symbols: set[str],
        proposals: tuple[TraderProposal, ...],
    ):
        strategy_name = str(strategy_summary.get("strategy_name") or "")
        strategy_rank_by_symbol, strategy_score_by_symbol = _strategy_ranking_maps(
            strategy_summary
        )
        policy = (
            load_money_management_policy_for_settings(self.settings)
            if self.settings.taurus_money_management_enabled
            else None
        )
        core_basket_artifact = (
            money_management_summary.get("core_shariah_basket")
            if isinstance(money_management_summary, dict)
            and isinstance(money_management_summary.get("core_shariah_basket"), dict)
            else {}
        )
        core_target_weights = (
            core_basket_artifact.get("target_weights")
            if isinstance(core_basket_artifact, dict)
            and isinstance(core_basket_artifact.get("target_weights"), dict)
            else {}
        )
        with self.session_factory() as session:
            execution_repo = ExecutionRepository(session)
            account = execution_repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
            starting_corpus = self._starting_corpus_inr(session)
            nav_inr = (
                account.equity_inr
                if account is not None
                else starting_corpus
            )
            available_cash = (
                account.available_cash_inr
                if account is not None
                else starting_corpus
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
            history_symbols = proposal_symbols | {
                str(symbol).strip().upper()
                for symbol in core_basket_symbols
                if str(symbol).strip()
            } | {
                str(symbol).strip().upper()
                for symbol in core_target_weights
                if str(symbol).strip()
            } | {
                position.symbol.upper()
                for position in open_positions
            }
            histories_by_symbol = {
                symbol: tuple(_daily_candle_history(session, symbol))
                for symbol in sorted(history_symbols)
            }
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
        return PortfolioRebalancePlanService().build(
            PortfolioRebalancePlanInput(
                run_id=run_id,
                portfolio_id=self.settings.taurus_paper_portfolio_id,
                as_of=_utc_now(),
                strategy_name=strategy_name,
                proposals=proposals,
                nav_inr=nav_inr,
                current_cash_inr=available_cash,
                current_positions=open_positions,
                sleeve_snapshots=sleeve_snapshots,
                histories_by_symbol=histories_by_symbol,
                core_basket_artifact=core_basket_artifact,
                core_basket_symbols=tuple(sorted(core_basket_symbols)),
                strategy_rank_by_symbol=strategy_rank_by_symbol,
                strategy_score_by_symbol=strategy_score_by_symbol,
                money_management_policy=policy,
                fallback_policy_source="settings",
                sleeve_by_symbol=sleeve_by_symbol,
                paper_brokerage_bps=self.settings.taurus_paper_brokerage_bps,
                paper_exchange_txn_charge_bps=self.settings.taurus_paper_exchange_txn_charge_bps,
                paper_tax_levy_bps=self.settings.taurus_paper_tax_levy_bps,
            )
        )

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
        requested_symbols: list[str] | None = None,
        pre_settlement_pending_order_symbols: list[str] | None = None,
        pending_next_open_order_symbols: list[str] | None = None,
        universe: PaperRunUniverse | None,
        strategy_config_path: str | Path | None,
    ) -> dict[str, object]:
        path = strategy_config_path or DEFAULT_STRATEGY_CONFIG_PATH
        strategy_config = load_strategy_config(path)
        strategy = build_strategy(strategy_config)
        current_positions = self._open_position_symbols()
        run_scope_symbols = _normalize_symbols(symbols)
        requested_for_metadata = _normalize_symbols(requested_symbols or symbols)
        pre_settlement_pending_symbols = _normalize_symbols(
            pre_settlement_pending_order_symbols or []
        )
        pending_next_open_symbols = _normalize_symbols(pending_next_open_order_symbols or [])
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
                "run_scope_symbols": run_scope_symbols,
                "requested_symbols": requested_for_metadata,
                "pre_settlement_pending_next_open_order_symbols": pre_settlement_pending_symbols,
                "pending_next_open_order_symbols": pending_next_open_symbols,
                "open_position_symbols": sorted(current_positions),
                "symbol_selection": _symbol_selection_metadata(
                    requested_symbols=requested_for_metadata,
                    selected_symbols=[],
                    current_positions=current_positions,
                    pending_next_open_order_symbols=set(
                        [*pre_settlement_pending_symbols, *pending_next_open_symbols]
                    ),
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
            "run_scope_symbols": run_scope_symbols,
            "requested_symbols": requested_for_metadata,
            "pre_settlement_pending_next_open_order_symbols": pre_settlement_pending_symbols,
            "pending_next_open_order_symbols": pending_next_open_symbols,
            "open_position_symbols": sorted(current_positions),
            "symbol_selection": _symbol_selection_metadata(
                requested_symbols=requested_for_metadata,
                selected_symbols=selected_symbols,
                current_positions=current_positions,
                pending_next_open_order_symbols=set(
                    [*pre_settlement_pending_symbols, *pending_next_open_symbols]
                ),
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
                PaperRunRepository(session).list(
                    profile_id=self.settings.effective_profile_id,
                    limit=None,
                )
            )
            starting_corpus = self._starting_corpus_inr(session)

        nav_inr = (
            account.equity_inr
            if account is not None
            else starting_corpus
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

    def _pending_next_open_order_symbols(self) -> set[str]:
        with self.session_factory() as session:
            rows = ExecutionRepository(session).list_pending_next_open_orders(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
                limit=None,
            )
        return {row.symbol.upper() for row in rows}

    def _settle_pending_next_open_orders(self, *, run_id: str) -> NextOpenSettlementSummary:
        with self.session_factory() as session:
            return PaperBroker(session, self.settings).settle_pending_next_open_orders(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
                run_id=run_id,
                settled_at=_utc_now(),
            )

    def _latest_paper_account(self) -> PaperAccount | None:
        with self.session_factory() as session:
            row = ExecutionRepository(session).latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
        return PaperAccount.model_validate(row.payload) if row is not None else None

    def _initial_pending_affordability_cash(self) -> Decimal:
        account = self._latest_paper_account()
        if account is not None:
            return account.available_cash_inr
        with self.session_factory() as session:
            return resolve_runtime_profile(
                session,
                self.settings,
                profile_id=self.settings.effective_profile_id,
            ).starting_corpus_inr

    def _refresh_llm_usage_artifact(
        self,
        artifacts: dict[str, Any],
        llm_provider: LLMProvider | None,
    ) -> None:
        llm_usage = summarize_llm_usage(get_llm_usage_records(llm_provider))
        llm_usage["profile_id"] = self.settings.effective_profile_id
        artifacts["llm_usage"] = llm_usage

    def _resolve_runtime_profile(self) -> RuntimeProfile:
        with self.session_factory() as session:
            runtime_profile = resolve_runtime_profile(session, self.settings)
        self._runtime_profile = runtime_profile
        return runtime_profile

    def _starting_corpus_inr(self, session: Session) -> Decimal:
        if (
            self._runtime_profile is not None
            and self._runtime_profile.profile_id == self.settings.effective_profile_id
        ):
            return self._runtime_profile.starting_corpus_inr
        return resolve_runtime_profile(session, self.settings).starting_corpus_inr

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
                            "portfolio_id": run.portfolio_id,
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


def _unique_symbols(symbols: Iterable[str]) -> list[str]:
    unique: list[str] = []
    for symbol in symbols:
        cleaned = str(symbol).strip().upper()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return unique


def _symbol_progress_index(symbols: list[str], symbol: str) -> int:
    normalized = symbol.upper()
    if normalized in symbols:
        return symbols.index(normalized) + 1
    return len(symbols) + 1


def _symbol_scope_with_finalization_symbols(
    scope: PaperRunSymbolScope,
    finalization_symbols: list[str],
) -> PaperRunSymbolScope:
    return replace(
        scope,
        finalization_symbols=list(finalization_symbols),
    )


def _portfolio_plan_trade_symbols(portfolio_plan: Any | None) -> set[str]:
    trades = getattr(portfolio_plan, "planned_trades", ())
    symbols: set[str] = set()
    for trade in trades:
        if getattr(trade, "status", None) in {"missing_price", "no_trade"}:
            continue
        symbol = str(getattr(trade, "symbol", "")).strip().upper()
        if symbol:
            symbols.add(symbol)
    return symbols


def _planner_generated_symbols(allocation_result: RunAllocationResult) -> set[str]:
    return {
        proposal.symbol.upper()
        for proposal in allocation_result.proposals
        if _is_planner_generated_proposal(proposal)
    }


def _is_planner_generated_proposal(proposal: TraderProposal) -> bool:
    source = proposal.target_sizing_metadata.get("proposal_source")
    if source in {"portfolio_plan_core", "portfolio_plan_threshold"}:
        return True
    decision = proposal.allocation_decision
    return decision is not None and decision.proposal_source in {
        "portfolio_plan_core",
        "portfolio_plan_threshold",
    }


def _proposal_source(proposal: TraderProposal) -> str:
    raw = proposal.target_sizing_metadata.get("proposal_source")
    if raw:
        return str(raw)
    if proposal.allocation_decision is not None and proposal.allocation_decision.proposal_source:
        return proposal.allocation_decision.proposal_source
    return "trader_proposal"


def _generated_core_analysis(proposal: TraderProposal) -> PaperSymbolAnalysis:
    return PaperSymbolAnalysis(
        symbol=proposal.symbol,
        enabled_analysts=[],
        reports=[],
        debate=_synthetic_portfolio_rebalance_debate(proposal),
        proposal=proposal,
    )


def _synthetic_portfolio_rebalance_debate(proposal: TraderProposal) -> DebateReport:
    confidence = proposal.confidence.quantize(Decimal("0.0001"))
    score = min(Decimal("1.0000"), confidence).quantize(Decimal("0.0001"))
    source_report_ids = list(proposal.source_report_ids)
    action = proposal.action
    return DebateReport(
        debate_id=proposal.debate_id,
        run_id=proposal.run_id,
        portfolio_id=proposal.portfolio_id,
        symbol=proposal.symbol,
        as_of=proposal.as_of,
        rounds_requested=1,
        bull_thesis=BullThesis(
            symbol=proposal.symbol,
            score=score,
            confidence=confidence,
            key_points=[
                f"Portfolio rebalance planner selected this {action} candidate."
            ],
            conditions=[
                "Paper-only risk review and final approval must confirm the plan row."
            ],
            source_report_ids=source_report_ids,
        ),
        bear_thesis=BearThesis(
            symbol=proposal.symbol,
            score=Decimal("-0.1000"),
            confidence=Decimal("0.5000"),
            key_points=[
                "Planner-generated rebalance candidates remain subject to deterministic risk controls."
            ],
            risk_flags=[
                "Price movement, liquidity, concentration, or stale data can still block routing."
            ],
            source_report_ids=source_report_ids,
        ),
        rounds=[
            DebateRound(
                round_number=1,
                bull_argument=(
                    f"Portfolio rebalance target supports a paper {action} candidate."
                ),
                bear_argument="Risk and final approval remain authoritative before any order.",
                manager_note="Synthetic debate artifact created for portfolio-plan routing.",
            )
        ],
        manager_summary=ResearchManagerSummary(
            consensus_label="bullish",
            consensus_score=score,
            confidence=confidence,
            summary=(
                f"Portfolio rebalance planner generated this {action} for "
                "paper-only risk and final routing."
            ),
            unresolved_uncertainties=[
                "Final approval and next-open paper execution may still reject or trim the order."
            ],
        ),
        source_report_ids=source_report_ids,
        model_version="portfolio_rebalance_synthetic_debate_v1",
    )


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
        "proposal_source": _proposal_source(proposal),
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
        "order_reason": _order_artifact_reason(order),
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


def _settlement_artifact_from_summary(
    summary: NextOpenSettlementSummary,
    *,
    account: PaperAccount | None,
    open_position_symbols: list[str],
    pending_next_open_order_symbols: list[str],
) -> dict[str, object]:
    details = [detail.model_dump(mode="json") for detail in summary.details]
    still_pending_orders = [
        detail
        for detail in details
        if detail.get("status") == "PENDING_NEXT_OPEN"
        or detail.get("outcome_reason") == "waiting_for_next_candle"
    ]
    by_symbol: dict[str, dict[str, object]] = {}
    for detail in details:
        symbol = str(detail.get("symbol") or "").upper()
        if not symbol:
            continue
        symbol_artifact = by_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "settled": 0,
                "rejected": 0,
                "still_pending": 0,
                "skipped": 0,
                "details": [],
            },
        )
        if detail.get("status") in {"FILLED", "PARTIALLY_FILLED"}:
            symbol_artifact["settled"] = int(symbol_artifact["settled"]) + 1
        elif detail.get("status") == "REJECTED":
            symbol_artifact["rejected"] = int(symbol_artifact["rejected"]) + 1
        elif detail.get("status") == "PENDING_NEXT_OPEN":
            symbol_artifact["still_pending"] = int(symbol_artifact["still_pending"]) + 1
        else:
            symbol_artifact["skipped"] = int(symbol_artifact["skipped"]) + 1
        symbol_details = symbol_artifact["details"]
        if isinstance(symbol_details, list):
            symbol_details.append(detail)

    for symbol_artifact in by_symbol.values():
        symbol_details = symbol_artifact.get("details")
        symbol_artifact["detail_count"] = (
            len(symbol_details) if isinstance(symbol_details, list) else 0
        )

    return {
        "portfolio_id": summary.portfolio_id,
        "run_id": summary.run_id,
        "settled": summary.settled,
        "rejected": summary.rejected,
        "still_pending": summary.still_pending,
        "skipped": summary.skipped,
        "detail_count": len(details),
        "details": details,
        "still_pending_order_count": len(still_pending_orders),
        "still_pending_orders": still_pending_orders,
        "post_settlement_account": account.model_dump(mode="json")
        if account is not None
        else None,
        "post_settlement_open_position_symbols": list(open_position_symbols),
        "pending_next_open_order_symbols": list(pending_next_open_order_symbols),
        "by_symbol": dict(sorted(by_symbol.items())),
    }


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


def _execution_symbol_order(
    finalizations_by_symbol: dict[str, PaperSymbolFinalization],
    *,
    allocation_result: RunAllocationResult,
) -> list[str]:
    ledger_by_symbol = _allocation_ledger_by_symbol(allocation_result)
    execution_entries = _allocation_execution_entries(allocation_result)

    def sort_key(symbol: str) -> tuple[int, int, int, str, str]:
        normalized = symbol.upper()
        finalization = finalizations_by_symbol[symbol]
        entry = ledger_by_symbol.get(normalized)
        planner_rank = getattr(entry, "planner_rank", None)
        return (
            _execution_side_group(finalization.final_decision.final_action),
            0 if normalized in execution_entries else 1,
            planner_rank if planner_rank is not None else 1_000_000,
            normalized,
            finalization.final_decision.final_decision_id,
        )

    return sorted(finalizations_by_symbol, key=sort_key)


def _execution_side_group(final_action: str) -> int:
    if final_action in {"REDUCE", "EXIT", "SELL"}:
        return 0
    if final_action == "BUY":
        return 1
    return 2


def _execution_funding_artifact(entry: Any | None) -> dict[str, object]:
    return {
        "funding_source": getattr(entry, "funding_source", None) if entry is not None else None,
        "existing_cash_used_inr": _decimal_artifact(
            getattr(entry, "existing_cash_used_inr", None) if entry is not None else None
        ),
        "same_run_proceeds_used_inr": _decimal_artifact(
            getattr(entry, "same_run_proceeds_used_inr", None) if entry is not None else None
        ),
        "same_run_proceeds_available_inr": _decimal_artifact(
            getattr(entry, "same_run_proceeds_available_inr", None)
            if entry is not None
            else None
        ),
        "same_run_proceeds_haircut_pct": _decimal_artifact(
            getattr(entry, "same_run_proceeds_haircut_pct", None)
            if entry is not None
            else None
        ),
        "hard_cash_reserve_inr": _decimal_artifact(
            getattr(entry, "hard_cash_reserve_inr", None) if entry is not None else None
        ),
        "buy_price_buffer_pct": _decimal_artifact(
            getattr(entry, "buy_price_buffer_pct", None) if entry is not None else None
        ),
    }


def _same_run_sell_spendable_proceeds(
    *,
    order: PaperOrder,
    entry: Any,
    settings: Settings,
) -> Decimal:
    if order.side != "SELL" or order.status not in {
        "PENDING_NEXT_OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
    }:
        return Decimal("0.00")
    gross, costs = _accepted_order_notional_and_costs(
        order=order,
        entry=entry,
        settings=settings,
    )
    net = max(Decimal("0.00"), gross - costs)
    return _money(net * _haircut_pct_for_entry(entry) / Decimal("100"))


def _accepted_buy_debit(
    *,
    order: PaperOrder,
    entry: Any,
    settings: Settings,
) -> Decimal:
    if order.side != "BUY" or order.status not in {
        "PENDING_NEXT_OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
    }:
        return Decimal("0.00")
    gross, costs = _accepted_order_notional_and_costs(
        order=order,
        entry=entry,
        settings=settings,
    )
    return _money(gross + costs)


def _accepted_order_notional_and_costs(
    *,
    order: PaperOrder,
    entry: Any,
    settings: Settings,
) -> tuple[Decimal, Decimal]:
    if order.gross_value_inr > 0:
        return _money(order.gross_value_inr), _money(order.total_cost_inr)

    approved_quantity = Decimal(str(max(0, getattr(entry, "approved_quantity", 0))))
    accepted_quantity = Decimal(str(max(0, order.quantity)))
    approved_notional = Decimal(str(getattr(entry, "approved_notional_inr", Decimal("0"))))
    if approved_quantity <= 0 or accepted_quantity <= 0 or approved_notional <= 0:
        return Decimal("0.00"), Decimal("0.00")

    gross = _money(approved_notional * accepted_quantity / approved_quantity)
    costs = _cost_model_for_settings(settings).calculate(gross).total_inr
    return gross, _money(costs)


def _cost_model_for_settings(settings: Settings) -> IndiaPaperCostModel:
    return IndiaPaperCostModel(
        brokerage_bps=settings.taurus_paper_brokerage_bps,
        exchange_txn_charge_bps=settings.taurus_paper_exchange_txn_charge_bps,
        tax_levy_bps=settings.taurus_paper_tax_levy_bps,
    )


def _haircut_pct_for_entry(entry: Any) -> Decimal:
    value = getattr(entry, "same_run_proceeds_haircut_pct", None)
    if value is None:
        return DEFAULT_SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT
    return Decimal(str(value))


def _add_optional_decimal(value: Decimal | None, increment: Decimal) -> Decimal | None:
    if increment <= 0:
        return value
    return _money((value or Decimal("0.00")) + increment)


def _subtract_optional_decimal(value: Decimal | None, decrement: Decimal) -> Decimal | None:
    if value is None:
        return None
    if decrement <= 0:
        return value
    return _money(max(Decimal("0.00"), value - decrement))


def _decimal_artifact(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT)


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
        "portfolio_plan_id": getattr(entry, "portfolio_plan_id", None),
        "portfolio_plan_trade_id": getattr(entry, "portfolio_plan_trade_id", None),
        "planner_source": getattr(entry, "planner_source", None),
        "planner_rank": getattr(entry, "planner_rank", None),
        "capacity_source": getattr(entry, "capacity_source", None),
        "proposal_source": getattr(entry, "proposal_source", None),
        **_execution_funding_artifact(entry),
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
        "portfolio_plan_id": getattr(entry, "portfolio_plan_id", None)
        if entry is not None
        else None,
        "portfolio_plan_trade_id": getattr(entry, "portfolio_plan_trade_id", None)
        if entry is not None
        else None,
        "planner_source": getattr(entry, "planner_source", None) if entry is not None else None,
        "planner_rank": getattr(entry, "planner_rank", None) if entry is not None else None,
        "capacity_source": getattr(entry, "capacity_source", None) if entry is not None else None,
        "proposal_source": getattr(entry, "proposal_source", None) if entry is not None else None,
        **_execution_funding_artifact(entry),
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


def _order_artifact_reason(order: PaperOrder | None) -> str | None:
    if order is None:
        return None
    if order.status == "PENDING_NEXT_OPEN":
        return "queued_for_next_open_settlement"
    return f"executed_by_paper_order:{order.status.lower()}"


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
        "proposal_source": _proposal_source(proposal),
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
    if not enabled:
        return {
            "enabled": [],
            "skipped": [],
            "report_count": report_count,
            "min_required": MIN_ANALYST_REPORTS,
            "status": "planner_generated",
        }
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
    pending_next_open = _normalize_symbols(
        [
            *[
                str(symbol)
                for symbol in strategy_summary.get(
                    "pre_settlement_pending_next_open_order_symbols",
                    [],
                )
            ],
            *[
                str(symbol)
                for symbol in strategy_summary.get("pending_next_open_order_symbols", [])
            ],
        ]
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
            analyzed = _normalize_symbols([*requested, *open_positions, *pending_next_open])
            finalization = list(analyzed)
        else:
            analyzed = _normalize_symbols([*requested, *open_positions, *pending_next_open])
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
        pending_next_open_order_symbols=pending_next_open,
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
    scoped["pending_next_open_order_symbols"] = list(
        symbol_scope.pending_next_open_order_symbols
    )
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
        pending_next_open = [
            *[
                str(symbol)
                for symbol in strategy_summary.get(
                    "pre_settlement_pending_next_open_order_symbols",
                    [],
                )
            ],
            *[
                str(symbol)
                for symbol in strategy_summary.get("pending_next_open_order_symbols", [])
            ],
        ]
        selected = [
            *[str(symbol) for symbol in strategy_summary.get(strategy_key, [])],
            *[str(symbol) for symbol in strategy_summary.get("open_position_symbols", [])],
            *pending_next_open,
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
            *[
                str(symbol)
                for symbol in strategy_summary.get(
                    "pre_settlement_pending_next_open_order_symbols",
                    [],
                )
            ],
            *[
                str(symbol)
                for symbol in strategy_summary.get("pending_next_open_order_symbols", [])
            ],
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
    pending_next_open_order_symbols: set[str],
    graph_signals_by_symbol: dict[str, GraphBacktestSignal],
    universe: PaperRunUniverse | None,
    select_targets_with_graph_called: bool,
) -> dict[str, dict[str, object]]:
    requested = {symbol.upper() for symbol in requested_symbols}
    selected = {symbol.upper() for symbol in selected_symbols}
    pending_next_open = {symbol.upper() for symbol in pending_next_open_order_symbols}
    graph_signal_symbols = set(graph_signals_by_symbol)
    universe_mode = universe.source if universe is not None else "manual_symbols"
    output_symbols = sorted(
        requested | selected | current_positions | pending_next_open | graph_signal_symbols
    )
    return {
        symbol: {
            "selection_source": _selection_source(
                symbol=symbol,
                requested=requested,
                selected=selected,
                current_positions=current_positions,
                pending_next_open_order_symbols=pending_next_open,
                universe_mode=universe_mode,
                select_targets_with_graph_called=select_targets_with_graph_called,
            ),
            "requested_explicitly": symbol in requested and universe_mode == "manual_symbols",
            "selected_by_graph_strategy": (
                select_targets_with_graph_called and symbol in selected
            ),
            "included_from_open_position": symbol in current_positions,
            "included_from_pending_next_open_order": symbol in pending_next_open,
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
    pending_next_open_order_symbols: set[str],
    universe_mode: str,
    select_targets_with_graph_called: bool,
) -> str:
    if universe_mode == "manual_symbols" and symbol in requested:
        return "explicit_symbol"
    if select_targets_with_graph_called and symbol in selected:
        return "graph_aware_strategy"
    if symbol in current_positions:
        return "open_position"
    if symbol in pending_next_open_order_symbols:
        return "pending_next_open_order"
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
