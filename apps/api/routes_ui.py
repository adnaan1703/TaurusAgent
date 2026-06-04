from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    CompanyEventModel,
    DebateReportModel,
    FinalDecisionModel,
    HalalStockComplianceModel,
    HalalStockImportModel,
    MarketPriceSnapshotModel,
    PaperFillModel,
    PaperOrderModel,
    PaperRunModel,
    RiskReviewModel,
    TraderProposalModel,
)
from taurus_core.db.repositories import (
    AnalystReportRepository,
    AuditLogRepository,
    ExecutionRepository,
    HalalStockComplianceRepository,
    InstrumentRepository,
    IntelligenceRepository,
    PaperRunRepository,
    ResearchRepository,
    RiskRepository,
)
from taurus_core.data.universe import load_market_data_universe
from taurus_core.observability.metrics import current_llm_failure_count
from taurus_core.portfolio import money_management_metadata
from taurus_core.replay.service import DecisionReplayService

router = APIRouter(prefix="/ui", tags=["ui"])

RunStatus = Literal["RUNNING", "COMPLETED", "PARTIAL_FAILED", "FAILED"]
StageStatus = Literal[
    "complete",
    "running",
    "blocked",
    "rejected",
    "failed",
    "missing",
    "skipped",
]
WarningSeverity = Literal["info", "warning", "critical"]
MetricTone = Literal["neutral", "success", "caution", "failure"]
ShariahStatusFilter = Literal["all", "halal", "haram"]


class UiSafetyStatus(BaseModel):
    taurus_mode: str
    broker_provider: str
    live_trading_enabled: bool
    llm_provider: str
    llm_model_version: str
    llm_failure_count: int
    alert_provider: str | None = None


class UiWarning(BaseModel):
    id: str
    severity: WarningSeverity
    title: str
    message: str
    run_id: str | None = None
    symbol: str | None = None
    created_at: datetime | None = None


class UiMetric(BaseModel):
    label: str
    value: str | int | float | bool | None
    unit: str | None = None
    tone: MetricTone = "neutral"


class UiArtifactRef(BaseModel):
    kind: str
    id: str
    label: str | None = None


class UiRunUniverse(BaseModel):
    source: str
    provider: str | None = None
    universe_name: str | None = None
    yaml_path: str | None = None
    available_symbol_count: int | None = None
    selected_symbol_count: int | None = None
    symbols: list[str] = Field(default_factory=list)


class UiRunSelectionRow(BaseModel):
    symbol: str
    proposal_id: str | None = None
    final_decision_id: str | None = None
    decision_id: str | None = None
    order_id: str | None = None
    rank: int | None = None
    strategy_score: int | float | None = None
    trader_action: str | None = None
    proposal_confidence: int | float | None = None
    allocation_status: str | None = None
    final_status: str | None = None
    final_action: str | None = None
    execution_status: str | None = None
    selected: bool = False
    binding_constraint: str | None = None
    reason: str | None = None


class UiRunSummary(BaseModel):
    run_id: str
    status: RunStatus
    schedule_name: str
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    timezone: str
    run_after_market_close: bool
    symbols: list[str]
    succeeded_symbols: list[str]
    failed_symbols: list[str]
    error_count: int
    market_provider: str | None
    universe: UiRunUniverse | None = None
    universe_count: int = 0
    analyzed_count: int = 0
    ranked_count: int = 0
    proposal_count: int = 0
    selected_count: int = 0
    not_selected_count: int = 0
    allocation_rejected_count: int = 0
    risk_rejected_count: int = 0
    executed_count: int = 0
    selection_preview: list[UiRunSelectionRow] = Field(default_factory=list)
    final_status_counts: dict[str, int] = Field(default_factory=dict)
    order_status_counts: dict[str, int] = Field(default_factory=dict)
    settlement_summary: dict[str, Any] = Field(default_factory=dict)
    graph_enabled_profile: bool = False
    graph_risk_enabled: bool = False
    graph_signal_count: int | None = None
    graph_selected_symbols: list[str] = Field(default_factory=list)


class UiStageSummary(BaseModel):
    id: str
    label: str
    status: StageStatus
    summary: str
    timestamp: datetime | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class UiAnalystRoster(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    report_count: int = 0
    min_required: int = 1
    status: str = "unknown"


class UiSymbolPipelineRow(BaseModel):
    symbol: str
    run_id: str
    pipeline_status: StageStatus
    final_status: str | None
    final_action: str | None
    order_status: str | None
    decision_id: str | None
    analyst_roster: UiAnalystRoster | None = None
    stages: list[UiStageSummary]
    errors: list[str] = Field(default_factory=list)


class UiTimelineStage(BaseModel):
    id: str
    label: str
    status: StageStatus
    timestamp: datetime | None = None
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] | list[dict[str, Any]] | None = None


class UiOverviewResponse(BaseModel):
    safety: UiSafetyStatus
    monitor_status: dict[str, Any]
    allocation: dict[str, Any]
    latest_account: dict[str, Any] | None
    latest_run: UiRunSummary | None
    latest_trader_proposal: dict[str, Any] | None
    latest_final_decision: dict[str, Any] | None
    latest_order: dict[str, Any] | None
    recent_runs: list[UiRunSummary]
    positions: list[dict[str, Any]]
    warnings: list[UiWarning]


class UiRunDetailResponse(BaseModel):
    safety: UiSafetyStatus
    run: UiRunSummary
    symbols: list[UiSymbolPipelineRow]
    market_data_summary: dict[str, Any]
    strategy_summary: dict[str, Any]
    selection_ledger: list[UiRunSelectionRow] = Field(default_factory=list)
    errors: list[dict[str, Any]]
    artifacts: dict[str, Any]
    warnings: list[UiWarning]


class UiDecisionTrailResponse(BaseModel):
    run: UiRunSummary
    symbol: str
    company_name: str | None = None
    decision_id: str | None
    final_status: str | None
    final_action: str | None
    can_send_to_broker: bool | None
    allocation_decision: dict[str, Any] | None = None
    selection_decision: UiRunSelectionRow | None = None
    decision_reason: str | None = None
    analyst_roster: UiAnalystRoster | None = None
    selected_stage_id: str
    stages: list[UiTimelineStage]
    warnings: list[UiWarning] = Field(default_factory=list)


class UiReplayResponse(BaseModel):
    decision_id: str
    run_id: str
    symbol: str
    status: str
    generated_at: datetime
    note: str
    stages: list[UiTimelineStage]


class UiRiskResponse(BaseModel):
    safety: UiSafetyStatus
    money_management: dict[str, Any]
    allocation: dict[str, Any]
    latest_risk_reviews: list[dict[str, Any]]
    hard_rule_results: list[dict[str, Any]]
    persona_reviews: list[dict[str, Any]]
    latest_final_decisions: list[dict[str, Any]]
    status_counts: dict[str, int]


class UiPortfolioResponse(BaseModel):
    safety: UiSafetyStatus
    money_management: dict[str, Any]
    allocation: dict[str, Any]
    monitor_status: dict[str, Any]
    latest_account: dict[str, Any] | None
    positions: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    summary_metrics: list[UiMetric]


class UiHistoryResponse(BaseModel):
    runs: list[UiRunSummary]
    status_counts: dict[str, int]
    filters_metadata: dict[str, Any]


class UiPagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class UiShariahRow(BaseModel):
    name: str
    nse_code: str
    bse_code: str
    industry: str
    compliance_status: str
    active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    status_changed_at: datetime
    details_url: str
    source_url: str


class UiShariahCounts(BaseModel):
    active_total: int = 0
    halal: int = 0
    haram: int = 0


class UiHalalStockLatestImport(BaseModel):
    import_id: str
    source_url: str
    source_checksum: str
    fetched_at: datetime
    imported_at: datetime
    rows_seen: int
    rows_imported: int
    halal_count: int
    haram_count: int
    unknown_count: int
    duplicate_count: int
    generated_yaml_path: str
    status: str


class UiHalalUniverseExport(BaseModel):
    yaml_path: str | None = None
    universe_name: str | None = None
    exported_symbol_count: int = 0
    loaded: bool = False
    error: str | None = None


class UiShariahResponse(BaseModel):
    rows: list[UiShariahRow]
    pagination: UiPagination
    counts: UiShariahCounts
    latest_import: UiHalalStockLatestImport | None
    halal_universe_export: UiHalalUniverseExport


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/overview", response_model=UiOverviewResponse)
def get_overview(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> UiOverviewResponse:
    settings: Settings = request.app.state.settings
    run_repo = PaperRunRepository(session)
    research_repo = ResearchRepository(session)
    risk_repo = RiskRepository(session)
    execution_repo = ExecutionRepository(session)

    run_rows = run_repo.list(limit=limit)
    recent_runs = [
        _run_summary(row, research_repo, risk_repo, execution_repo)
        for row in run_rows
    ]
    latest_run = recent_runs[0] if recent_runs else None
    latest_account = execution_repo.latest_account_by_portfolio(
        portfolio_id=settings.taurus_paper_portfolio_id,
    )
    latest_account_payload = _payload(latest_account) if latest_account is not None else None
    latest_proposal = research_repo.list_trader_proposals(
        portfolio_id=settings.taurus_paper_portfolio_id,
        limit=1,
    )
    latest_final = risk_repo.list_final_decisions(limit=1)
    latest_orders = execution_repo.list_orders(
        portfolio_id=settings.taurus_paper_portfolio_id,
        limit=1,
    )
    positions = _monitor_enriched_positions(
        session,
        settings=settings,
        positions=execution_repo.latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        ),
    )

    warnings = _overview_warnings(
        run_rows=run_rows,
        latest_account=latest_account_payload,
        latest_final=latest_final[0] if latest_final else None,
    )
    return UiOverviewResponse(
        safety=_safety(settings),
        monitor_status=_monitor_status(session, settings),
        allocation=_allocation_dashboard_payload(
            session=session,
            settings=settings,
            account=latest_account_payload,
            positions=positions,
            latest_run=run_rows[0] if run_rows else None,
        ),
        latest_account=latest_account_payload,
        latest_run=latest_run,
        latest_trader_proposal=_payload(latest_proposal[0]) if latest_proposal else None,
        latest_final_decision=_payload(latest_final[0]) if latest_final else None,
        latest_order=_payload(latest_orders[0]) if latest_orders else None,
        recent_runs=recent_runs,
        positions=positions,
        warnings=warnings,
    )


@router.get("/runs/{run_id}", response_model=UiRunDetailResponse)
def get_ui_run(
    run_id: str,
    request: Request,
    session: Session = Depends(get_db_session),
) -> UiRunDetailResponse:
    settings: Settings = request.app.state.settings
    run = _require_run(session, run_id)
    risk_repo = RiskRepository(session)
    execution_repo = ExecutionRepository(session)
    research_repo = ResearchRepository(session)
    final_decisions = risk_repo.list_final_decisions(run_id=run.run_id, limit=None)
    orders = execution_repo.list_orders(run_id=run.run_id, limit=None)
    proposals = research_repo.list_trader_proposals(run_id=run.run_id, limit=None)
    run_summary = _run_summary(
        run,
        research_repo,
        risk_repo,
        execution_repo,
        proposals=proposals,
        final_decisions=final_decisions,
        orders=orders,
    )
    symbols = [
        _symbol_pipeline_row(session=session, run=run, symbol=symbol)
        for symbol in run.symbols
    ]
    return UiRunDetailResponse(
        safety=_safety(settings),
        run=run_summary,
        symbols=symbols,
        market_data_summary=_json_safe(run.market_data_summary),
        strategy_summary=_strategy_summary(run),
        selection_ledger=_selection_rows(
            run=run,
            proposals=proposals,
            final_decisions=final_decisions,
            orders=orders,
            limit=None,
        ),
        errors=_json_safe(run.errors),
        artifacts=_json_safe(run.artifacts),
        warnings=_run_warnings(run),
    )


@router.get(
    "/runs/{run_id}/symbols/{symbol}/decision-trail",
    response_model=UiDecisionTrailResponse,
)
def get_decision_trail(
    run_id: str,
    symbol: str,
    session: Session = Depends(get_db_session),
) -> UiDecisionTrailResponse:
    run = _require_run(session, run_id)
    normalized_symbol = symbol.upper()
    if normalized_symbol not in set(run.symbols):
        raise HTTPException(status_code=404, detail="Symbol was not part of this paper run.")

    context = _symbol_context(session=session, run=run, symbol=normalized_symbol)
    stages = _timeline_stages(run=run, symbol=normalized_symbol, context=context)
    final_decision = context["final_decision"]
    instrument = context["instrument"]
    selection_decision = _selection_row_for_symbol(
        run=run,
        symbol=normalized_symbol,
        context=context,
    )
    return UiDecisionTrailResponse(
        run=_run_summary(
            run,
            ResearchRepository(session),
            RiskRepository(session),
            ExecutionRepository(session),
        ),
        symbol=normalized_symbol,
        company_name=instrument.name if instrument is not None else None,
        decision_id=final_decision.decision_id if final_decision is not None else None,
        final_status=final_decision.status if final_decision is not None else None,
        final_action=final_decision.final_action if final_decision is not None else None,
        can_send_to_broker=final_decision.can_send_to_broker
        if final_decision is not None
        else None,
        allocation_decision=_latest_allocation_decision(context),
        selection_decision=selection_decision,
        decision_reason=selection_decision.reason
        if selection_decision is not None
        else _legacy_decision_reason(context),
        analyst_roster=_analyst_roster(run=run, symbol=normalized_symbol),
        selected_stage_id=stages[0].id,
        stages=stages,
        warnings=_decision_warnings(run=run, symbol=normalized_symbol, context=context),
    )


@router.get("/replay/{decision_id}", response_model=UiReplayResponse)
def get_ui_replay(
    decision_id: str,
    session: Session = Depends(get_db_session),
) -> UiReplayResponse:
    try:
        replay = DecisionReplayService(session).replay(decision_id=decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    order_artifacts: list[dict[str, object]] = []
    for stage in replay.stages:
        if stage.name == "paper_order":
            order_artifacts = stage.artifacts
            break
    stages = [_replay_timeline_stage(stage, order_artifacts=order_artifacts) for stage in replay.stages]
    return UiReplayResponse(
        decision_id=replay.decision_id,
        run_id=replay.run_id,
        symbol=replay.symbol,
        status=replay.status,
        generated_at=replay.generated_at,
        note=replay.note,
        stages=stages,
    )


@router.get("/risk", response_model=UiRiskResponse)
def get_ui_risk(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> UiRiskResponse:
    settings: Settings = request.app.state.settings
    risk_repo = RiskRepository(session)
    reviews = risk_repo.list_risk_reviews(limit=limit)
    decisions = risk_repo.list_final_decisions(limit=limit)
    hard_rules: list[dict[str, Any]] = []
    persona_reviews: list[dict[str, Any]] = []
    for review in reviews:
        for rule in review.hard_rule_results:
            hard_rules.append(
                _json_safe(
                    {
                        "risk_check_id": review.risk_check_id,
                        "decision_id": review.decision_id,
                        "run_id": review.run_id,
                        "symbol": review.symbol,
                        **dict(rule),
                    }
                )
            )
        for persona in review.persona_reviews:
            persona_reviews.append(
                _json_safe(
                    {
                        "risk_check_id": review.risk_check_id,
                        "decision_id": review.decision_id,
                        "run_id": review.run_id,
                        "symbol": review.symbol,
                        **dict(persona),
                    }
                )
            )
    return UiRiskResponse(
        safety=_safety(settings),
        money_management=money_management_metadata(settings),
        allocation=_allocation_dashboard_payload(session=session, settings=settings),
        latest_risk_reviews=[_risk_review_payload(session, review) for review in reviews],
        hard_rule_results=hard_rules,
        persona_reviews=persona_reviews,
        latest_final_decisions=[_payload(decision) for decision in decisions],
        status_counts=dict(Counter(review.status for review in reviews)),
    )


@router.get("/portfolio", response_model=UiPortfolioResponse)
def get_ui_portfolio(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> UiPortfolioResponse:
    settings: Settings = request.app.state.settings
    execution_repo = ExecutionRepository(session)
    latest_run_rows = PaperRunRepository(session).list(limit=1)
    account = execution_repo.latest_account_by_portfolio(
        portfolio_id=settings.taurus_paper_portfolio_id,
    )
    account_payload = _payload(account) if account is not None else None
    run_id = account.run_id if account is not None else None
    positions = _monitor_enriched_positions(
        session,
        settings=settings,
        positions=execution_repo.latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        ),
    )
    orders = [
        _payload(row)
        for row in execution_repo.list_orders(
            run_id=run_id,
            portfolio_id=settings.taurus_paper_portfolio_id,
            limit=limit,
        )
    ]
    fills = [
        _payload(row)
        for row in execution_repo.list_fills(
            run_id=run_id,
            portfolio_id=settings.taurus_paper_portfolio_id,
            limit=limit,
        )
    ]
    return UiPortfolioResponse(
        safety=_safety(settings),
        money_management=money_management_metadata(settings),
        allocation=_allocation_dashboard_payload(
            session=session,
            settings=settings,
            account=account_payload,
            positions=positions,
            latest_run=latest_run_rows[0] if latest_run_rows else None,
        ),
        monitor_status=_monitor_status(session, settings),
        latest_account=account_payload,
        positions=positions,
        orders=orders,
        fills=fills,
        summary_metrics=_portfolio_metrics(account_payload, positions, orders, fills),
    )


@router.get("/history", response_model=UiHistoryResponse)
def get_ui_history(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> UiHistoryResponse:
    risk_repo = RiskRepository(session)
    execution_repo = ExecutionRepository(session)
    rows = PaperRunRepository(session).list(limit=limit)
    research_repo = ResearchRepository(session)
    runs = [_run_summary(row, research_repo, risk_repo, execution_repo) for row in rows]
    symbols = sorted({symbol for row in rows for symbol in row.symbols})
    started_values = [row.started_at for row in rows]
    return UiHistoryResponse(
        runs=runs,
        status_counts=dict(Counter(row.status for row in rows)),
        filters_metadata={
            "statuses": sorted({row.status for row in rows}),
            "symbols": symbols,
            "date_range": {
                "start": min(started_values).isoformat() if started_values else None,
                "end": max(started_values).isoformat() if started_values else None,
            },
        },
    )


@router.get("/shariah", response_model=UiShariahResponse)
def get_ui_shariah(
    request: Request,
    query: str = Query(default="", max_length=100),
    status: ShariahStatusFilter = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> UiShariahResponse:
    settings: Settings = request.app.state.settings
    repo = HalalStockComplianceRepository(session)
    compliance_status = None if status == "all" else status
    rows, total = repo.search_active(
        query=query,
        compliance_status=compliance_status,
        page=page,
        page_size=page_size,
    )
    latest_import = repo.latest_import()
    return UiShariahResponse(
        rows=[_shariah_row(row) for row in rows],
        pagination=UiPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
        counts=UiShariahCounts.model_validate(repo.active_status_counts()),
        latest_import=_latest_halal_import(latest_import),
        halal_universe_export=_halal_universe_export(
            settings=settings,
            latest_import=latest_import,
        ),
    )


def _safety(settings: Settings) -> UiSafetyStatus:
    return UiSafetyStatus(
        taurus_mode=settings.taurus_mode,
        broker_provider=settings.broker_provider,
        live_trading_enabled=settings.live_trading_enabled,
        llm_provider=settings.taurus_llm_provider,
        llm_model_version=settings.configured_llm_model_version,
        llm_failure_count=current_llm_failure_count(),
        alert_provider=settings.taurus_alert_provider,
    )


def _shariah_row(row: HalalStockComplianceModel) -> UiShariahRow:
    return UiShariahRow(
        name=row.name,
        nse_code=row.nse_code,
        bse_code=row.bse_code,
        industry=row.industry,
        compliance_status=row.compliance_status,
        active=row.active,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        status_changed_at=row.status_changed_at,
        details_url=row.details_url,
        source_url=row.source_url,
    )


def _latest_halal_import(
    import_row: HalalStockImportModel | None,
) -> UiHalalStockLatestImport | None:
    if import_row is None:
        return None
    return UiHalalStockLatestImport(
        import_id=import_row.import_id,
        source_url=import_row.source_url,
        source_checksum=import_row.source_checksum,
        fetched_at=import_row.fetched_at,
        imported_at=import_row.imported_at,
        rows_seen=import_row.rows_seen,
        rows_imported=import_row.rows_imported,
        halal_count=import_row.halal_count,
        haram_count=import_row.haram_count,
        unknown_count=import_row.unknown_count,
        duplicate_count=import_row.duplicate_count,
        generated_yaml_path=import_row.generated_yaml_path,
        status=import_row.status,
    )


def _halal_universe_export(
    *,
    settings: Settings,
    latest_import: HalalStockImportModel | None,
) -> UiHalalUniverseExport:
    raw_path = (
        latest_import.generated_yaml_path
        if latest_import is not None and latest_import.generated_yaml_path
        else settings.taurus_halal_stock_universe_path
    )
    if not raw_path:
        return UiHalalUniverseExport(error="No halal universe YAML path is configured.")

    path = Path(raw_path).expanduser()
    try:
        universe = load_market_data_universe(path)
    except Exception as exc:
        return UiHalalUniverseExport(
            yaml_path=str(path),
            error=str(exc),
        )

    return UiHalalUniverseExport(
        yaml_path=str(path),
        universe_name=universe.universe_name,
        exported_symbol_count=len(universe.enabled_symbols()),
        loaded=True,
    )


def _require_run(session: Session, run_id: str) -> PaperRunModel:
    run = PaperRunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Paper run not found.")
    return run


def _run_summary(
    run: PaperRunModel,
    research_repo: ResearchRepository,
    risk_repo: RiskRepository,
    execution_repo: ExecutionRepository,
    *,
    proposals: list[TraderProposalModel] | None = None,
    risk_reviews: list[RiskReviewModel] | None = None,
    final_decisions: list[FinalDecisionModel] | None = None,
    orders: list[PaperOrderModel] | None = None,
) -> UiRunSummary:
    proposals = proposals if proposals is not None else research_repo.list_trader_proposals(
        run_id=run.run_id,
        limit=None,
    )
    risk_reviews = risk_reviews if risk_reviews is not None else risk_repo.list_risk_reviews(
        run_id=run.run_id,
        limit=None,
    )
    final_decisions = final_decisions if final_decisions is not None else risk_repo.list_final_decisions(
        run_id=run.run_id,
        limit=None,
    )
    orders = orders if orders is not None else execution_repo.list_orders(
        run_id=run.run_id,
        limit=None,
    )
    strategy = _strategy_summary(run)
    count_payload = _run_count_payload(
        run=run,
        proposals=proposals,
        risk_reviews=risk_reviews,
        final_decisions=final_decisions,
        orders=orders,
    )
    return UiRunSummary(
        run_id=run.run_id,
        status=run.status,  # type: ignore[arg-type]
        schedule_name=run.schedule_name,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=_duration_seconds(run.started_at, run.completed_at),
        timezone=run.timezone,
        run_after_market_close=run.run_after_market_close,
        symbols=list(run.symbols),
        succeeded_symbols=list(run.succeeded_symbols),
        failed_symbols=list(run.failed_symbols),
        error_count=len(run.errors),
        market_provider=_market_provider(run),
        universe=_run_universe(run),
        selection_preview=_selection_rows(
            run=run,
            proposals=proposals,
            final_decisions=final_decisions,
            orders=orders,
            limit=8,
        ),
        final_status_counts=dict(Counter(row.status for row in final_decisions)),
        order_status_counts=dict(Counter(row.status for row in orders)),
        settlement_summary=_run_settlement_summary(run),
        graph_enabled_profile=bool(strategy.get("graph_enabled_profile", False)),
        graph_risk_enabled=bool(strategy.get("graph_risk_enabled", False)),
        graph_signal_count=_optional_int(strategy.get("graph_signal_count")),
        graph_selected_symbols=[
            str(symbol).upper()
            for symbol in strategy.get("graph_selected_symbols", [])
            if str(symbol).strip()
        ],
        **count_payload,
    )


SELECTED_ALLOCATION_STATUSES = frozenset({"selected", "allocation_reduced"})
RISK_REJECTED_STATUSES = frozenset({"REJECTED", "BLOCKED"})


def _run_count_payload(
    *,
    run: PaperRunModel,
    proposals: list[TraderProposalModel],
    risk_reviews: list[RiskReviewModel],
    final_decisions: list[FinalDecisionModel],
    orders: list[PaperOrderModel],
) -> dict[str, int]:
    strategy = _strategy_summary(run)
    scope = _symbol_scope_artifact(run)
    allocation = _allocation_artifact(run)
    allocation_summary = (
        allocation.get("summary") if isinstance(allocation.get("summary"), dict) else {}
    )
    ledger_counts = (
        allocation.get("ledger_counts")
        if isinstance(allocation.get("ledger_counts"), dict)
        else {}
    )
    final_artifact = _run_artifact(run, "final_decisions")
    execution_artifact = _run_artifact(run, "execution")
    ledger = _allocation_ledger(run)
    universe = _run_universe(run)

    universe_count = (
        (universe.available_symbol_count if universe is not None else None)
        or _list_count(scope.get("requested_universe_symbols"))
        or (universe.selected_symbol_count if universe is not None else None)
        or len(run.symbols)
    )
    analyzed_count = (
        _optional_int(scope.get("analyzed_symbol_count"))
        or _list_count(scope.get("analyzed_symbols"))
        or len(run.symbols)
    )
    ranked_count = (
        _optional_int(strategy.get("ranked_symbol_count"))
        or _list_count(scope.get("strategy_ranked_symbols"))
        or _list_count(strategy.get("strategy_ranked_symbols"))
    )
    proposal_count = (
        _optional_int(allocation_summary.get("proposal_count"))
        or _optional_int(allocation.get("ledger_count"))
        or len(proposals)
    )
    selected_count = (
        _optional_int(allocation_summary.get("selected_count"))
        or _ledger_status_count(ledger, SELECTED_ALLOCATION_STATUSES)
        or sum(1 for decision in final_decisions if decision.status == "APPROVED_FOR_PAPER")
    )
    not_selected_count = (
        _optional_int(allocation_summary.get("not_selected_count"))
        or _optional_int(ledger_counts.get("not_selected"))
        or max(
            sum(1 for decision in final_decisions if decision.status == "NO_ACTION")
            - _optional_int(allocation_summary.get("allocation_rejected_count") or 0),
            0,
        )
    )
    allocation_rejected_count = (
        _optional_int(allocation_summary.get("allocation_rejected_count"))
        or _optional_int(ledger_counts.get("allocation_rejected"))
        or _ledger_status_count(ledger, {"allocation_rejected"})
    )
    risk_rejected_count = sum(
        1 for review in risk_reviews if review.status in RISK_REJECTED_STATUSES
    ) or _artifact_status_count(final_artifact, RISK_REJECTED_STATUSES)
    executed_count = (
        _optional_int(execution_artifact.get("routed_order_count"))
        or sum(1 for order in orders if order.status != "REJECTED")
    )
    return {
        "universe_count": int(universe_count),
        "analyzed_count": int(analyzed_count),
        "ranked_count": int(ranked_count),
        "proposal_count": int(proposal_count),
        "selected_count": int(selected_count),
        "not_selected_count": int(not_selected_count),
        "allocation_rejected_count": int(allocation_rejected_count),
        "risk_rejected_count": int(risk_rejected_count),
        "executed_count": int(executed_count),
    }


def _run_settlement_summary(run: PaperRunModel) -> dict[str, Any]:
    artifacts = run.artifacts if isinstance(run.artifacts, dict) else {}
    settlement = artifacts.get("settlement")
    if not isinstance(settlement, dict):
        return {}

    raw_details = settlement.get("details", [])
    detail_items = raw_details if isinstance(raw_details, list) else []
    details = [
        dict(item)
        for item in detail_items
        if isinstance(item, dict)
    ]
    status_counts = Counter(str(detail.get("status") or "UNKNOWN") for detail in details)
    raw_pending_symbols = settlement.get("pending_next_open_order_symbols", [])
    pending_symbol_items = raw_pending_symbols if isinstance(raw_pending_symbols, list) else []
    pending_symbols = [
        str(symbol).upper()
        for symbol in pending_symbol_items
        if str(symbol).strip()
    ]
    counts = {
        "settled": _optional_int(settlement.get("settled")) or 0,
        "rejected": _optional_int(settlement.get("rejected")) or 0,
        "still_pending": _optional_int(settlement.get("still_pending")) or 0,
        "skipped": _optional_int(settlement.get("skipped")) or 0,
    }
    return _json_safe(
        {
            **counts,
            "detail_count": len(details),
            "status_counts": dict(status_counts),
            "still_pending_order_count": (
                _optional_int(settlement.get("still_pending_order_count"))
                or counts["still_pending"]
            ),
            "pending_next_open_order_symbols": pending_symbols,
            "has_activity": bool(any(counts.values()) or details or pending_symbols),
        }
    )


def _selection_rows(
    *,
    run: PaperRunModel,
    proposals: list[TraderProposalModel],
    final_decisions: list[FinalDecisionModel],
    orders: list[PaperOrderModel],
    limit: int | None,
) -> list[UiRunSelectionRow]:
    ledger = _allocation_ledger(run)
    if not ledger:
        return []

    proposals_by_symbol = {proposal.symbol.upper(): proposal for proposal in proposals}
    final_by_symbol = {decision.symbol.upper(): decision for decision in final_decisions}
    order_by_symbol = {order.symbol.upper(): order for order in orders}
    execution_by_symbol = _execution_artifacts_by_symbol(run)

    rows: list[UiRunSelectionRow] = []
    for raw_entry in ledger:
        if not isinstance(raw_entry, dict):
            continue
        symbol = str(raw_entry.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        row = _selection_row_from_entry(
            raw_entry,
            proposal=proposals_by_symbol.get(symbol),
            final_decision=final_by_symbol.get(symbol),
            order=order_by_symbol.get(symbol),
            execution_artifact=execution_by_symbol.get(symbol),
        )
        rows.append(row)

    rows.sort(key=_selection_sort_key)
    return rows if limit is None else rows[:limit]


def _selection_row_for_symbol(
    *,
    run: PaperRunModel,
    symbol: str,
    context: dict[str, Any],
) -> UiRunSelectionRow | None:
    normalized = symbol.upper()
    for raw_entry in _allocation_ledger(run):
        if not isinstance(raw_entry, dict):
            continue
        if str(raw_entry.get("symbol") or "").strip().upper() != normalized:
            continue
        orders: list[PaperOrderModel] = context["orders"]
        return _selection_row_from_entry(
            raw_entry,
            proposal=context["trader_proposal"],
            final_decision=context["final_decision"],
            order=orders[0] if orders else None,
            execution_artifact=_execution_artifacts_by_symbol(run).get(normalized),
        )
    return None


def _selection_row_from_entry(
    entry: dict[str, Any],
    *,
    proposal: TraderProposalModel | None,
    final_decision: FinalDecisionModel | None,
    order: PaperOrderModel | None,
    execution_artifact: dict[str, Any] | None,
) -> UiRunSelectionRow:
    symbol = str(entry.get("symbol") or "").strip().upper()
    allocation_status = _optional_string(entry.get("status"))
    proposal_payload = _payload(proposal) if proposal is not None else {}
    allocation_decision = _allocation_decision_from_payload(proposal_payload)
    binding_constraint = (
        _optional_string(entry.get("binding_constraint"))
        or (
            _optional_string(allocation_decision.get("binding_constraint"))
            if allocation_decision
            else None
        )
    )
    proposal_id = _optional_string(entry.get("proposal_id")) or (
        proposal.proposal_id if proposal is not None else None
    )
    selected = bool(entry.get("selected")) or allocation_status in SELECTED_ALLOCATION_STATUSES
    return UiRunSelectionRow(
        symbol=symbol,
        proposal_id=proposal_id,
        final_decision_id=final_decision.final_decision_id
        if final_decision is not None
        else _optional_string(execution_artifact.get("final_decision_id"))
        if execution_artifact
        else None,
        decision_id=final_decision.decision_id if final_decision is not None else None,
        order_id=order.order_id if order is not None else None,
        rank=_optional_int(entry.get("strategy_rank")),
        strategy_score=_number_or_none(entry.get("strategy_score")),
        trader_action=_optional_string(entry.get("action"))
        or (proposal.action if proposal is not None else None),
        proposal_confidence=_number_or_none(
            entry.get("trader_confidence")
            if entry.get("trader_confidence") is not None
            else proposal.confidence
            if proposal is not None
            else None
        ),
        allocation_status=allocation_status,
        final_status=final_decision.status if final_decision is not None else None,
        final_action=final_decision.final_action if final_decision is not None else None,
        execution_status=order.status
        if order is not None
        else "skipped"
        if execution_artifact is not None
        else None,
        selected=selected,
        binding_constraint=binding_constraint,
        reason=_selection_reason(
            entry=entry,
            final_decision=final_decision,
            order=order,
            execution_artifact=execution_artifact,
            allocation_status=allocation_status,
            binding_constraint=binding_constraint,
        ),
    )


def _selection_reason(
    *,
    entry: dict[str, Any],
    final_decision: FinalDecisionModel | None,
    order: PaperOrderModel | None,
    execution_artifact: dict[str, Any] | None,
    allocation_status: str | None,
    binding_constraint: str | None,
) -> str | None:
    if order is not None:
        if order.status == "REJECTED":
            return order.rejection_reason or "execution_rejected_by_paper_broker"
        if order.status in {"FILLED", "PARTIALLY_FILLED"}:
            return f"executed_by_paper_order:{order.status.lower()}"
        return f"paper_order_status:{order.status.lower()}"

    execution_reason = (
        _optional_string(execution_artifact.get("reason"))
        if execution_artifact is not None
        else None
    )
    if execution_reason:
        return execution_reason

    if final_decision is not None:
        if final_decision.status in RISK_REJECTED_STATUSES:
            return final_decision.reason or f"risk_rejected:{final_decision.status.lower()}"
        if final_decision.status == "NO_ACTION":
            return final_decision.reason or "no_action"

    rationale = _first_string(entry.get("rationale"))
    if rationale:
        return rationale

    if allocation_status in SELECTED_ALLOCATION_STATUSES:
        return "selected_by_run_allocation"
    if allocation_status == "not_selected":
        return f"not_selected_by_run_allocation:{binding_constraint or 'none'}"
    if allocation_status == "allocation_rejected":
        return f"allocation_rejected_by_run_allocation:{binding_constraint or 'none'}"
    if allocation_status == "open_position_management":
        return "open_position_lifecycle"
    if allocation_status in {"unchanged", "unchanged_lifecycle"}:
        return "no_action_unchanged_lifecycle"
    return None


def _legacy_decision_reason(context: dict[str, Any]) -> str | None:
    orders: list[PaperOrderModel] = context["orders"]
    final_decision: FinalDecisionModel | None = context["final_decision"]
    allocation_decision = _latest_allocation_decision(context)
    entry = {
        "status": allocation_decision.get("status") if allocation_decision else None,
        "binding_constraint": allocation_decision.get("binding_constraint")
        if allocation_decision
        else None,
        "rationale": allocation_decision.get("rationale") if allocation_decision else None,
    }
    return _selection_reason(
        entry=entry,
        final_decision=final_decision,
        order=orders[0] if orders else None,
        execution_artifact=None,
        allocation_status=_optional_string(entry.get("status")),
        binding_constraint=_optional_string(entry.get("binding_constraint")),
    )


def _selection_sort_key(row: UiRunSelectionRow) -> tuple[int, int, str]:
    status_priority = 0 if row.selected else 1
    rank = row.rank if row.rank is not None else 1_000_000
    return status_priority, rank, row.symbol


def _allocation_ledger(run: PaperRunModel) -> list[dict[str, Any]]:
    allocation = _allocation_artifact(run)
    ledger = allocation.get("ledger")
    if not isinstance(ledger, list):
        return []
    return [entry for entry in ledger if isinstance(entry, dict)]


def _allocation_artifact(run: PaperRunModel) -> dict[str, Any]:
    return _run_artifact(run, "allocation")


def _symbol_scope_artifact(run: PaperRunModel) -> dict[str, Any]:
    scope = _run_artifact(run, "symbol_scope")
    if scope:
        return scope
    strategy = _strategy_summary(run)
    strategy_scope = strategy.get("symbol_scope")
    return strategy_scope if isinstance(strategy_scope, dict) else {}


def _run_artifact(run: PaperRunModel, key: str) -> dict[str, Any]:
    artifacts = run.artifacts or {}
    raw = artifacts.get(key)
    return raw if isinstance(raw, dict) else {}


def _execution_artifacts_by_symbol(run: PaperRunModel) -> dict[str, dict[str, Any]]:
    execution = _run_artifact(run, "execution")
    by_symbol: dict[str, dict[str, Any]] = {}
    for key in ("execution_set", "skipped_symbols"):
        rows = execution.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol:
                by_symbol[symbol] = row
    return by_symbol


def _ledger_status_count(
    ledger: list[dict[str, Any]],
    statuses: frozenset[str] | set[str],
) -> int:
    return sum(
        1
        for entry in ledger
        if isinstance(entry, dict) and str(entry.get("status") or "") in statuses
    )


def _artifact_status_count(
    artifact: dict[str, Any],
    statuses: frozenset[str] | set[str],
) -> int:
    by_status = artifact.get("by_status")
    if not isinstance(by_status, dict):
        return 0
    total = 0
    for status in statuses:
        total += _optional_int(by_status.get(status)) or 0
    return total


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _number_or_none(value: Any) -> int | float | None:
    decimal_value = _decimal_or_none(value)
    if decimal_value is None:
        return None
    return _decimal_to_number(decimal_value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_string(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _optional_string(item)
            if text:
                return text
        return None
    return _optional_string(value)


def _symbol_context(
    *,
    session: Session,
    run: PaperRunModel,
    symbol: str,
) -> dict[str, Any]:
    research_repo = ResearchRepository(session)
    risk_repo = RiskRepository(session)
    execution_repo = ExecutionRepository(session)
    events = IntelligenceRepository(session).list_events(symbol=symbol, limit=20)
    return {
        "instrument": InstrumentRepository(session).get(symbol),
        "events": events,
        "analyst_reports": AnalystReportRepository(session).list_for_run_symbol(
            run_id=run.run_id,
            symbol=symbol,
        ),
        "debate": research_repo.latest_debate(run_id=run.run_id, symbol=symbol),
        "trader_proposal": research_repo.latest_trader_proposal(
            run_id=run.run_id,
            symbol=symbol,
        ),
        "risk_review": risk_repo.latest_risk_review(run_id=run.run_id, symbol=symbol),
        "final_decision": risk_repo.latest_final_decision(run_id=run.run_id, symbol=symbol),
        "orders": execution_repo.list_orders(run_id=run.run_id, symbol=symbol, limit=None),
        "fills": sorted(
            execution_repo.list_fills(run_id=run.run_id, symbol=symbol, limit=None),
            key=lambda fill: (fill.filled_at, fill.fill_sequence),
        ),
        "positions": execution_repo.list_positions(run_id=run.run_id, symbol=symbol),
        "account": execution_repo.latest_account(run_id=run.run_id),
        "audit_rows": AuditLogRepository(session).list_for_run_symbol(
            run_id=run.run_id,
            symbol=symbol,
            limit=100,
        ),
    }


def _symbol_pipeline_row(
    *,
    session: Session,
    run: PaperRunModel,
    symbol: str,
) -> UiSymbolPipelineRow:
    context = _symbol_context(session=session, run=run, symbol=symbol)
    stages = [
        _stage_summary(stage)
        for stage in _timeline_stages(run=run, symbol=symbol, context=context)
    ]
    errors = _symbol_errors(run, symbol)
    final_decision = context["final_decision"]
    orders = context["orders"]
    return UiSymbolPipelineRow(
        symbol=symbol,
        run_id=run.run_id,
        pipeline_status=_pipeline_status(
            run=run,
            stages=stages,
            final_decision=final_decision,
            errors=errors,
        ),
        final_status=final_decision.status if final_decision is not None else None,
        final_action=final_decision.final_action if final_decision is not None else None,
        order_status=orders[0].status if orders else None,
        decision_id=final_decision.decision_id if final_decision is not None else None,
        analyst_roster=_analyst_roster(run=run, symbol=symbol),
        stages=stages,
        errors=errors,
    )


def _timeline_stages(
    *,
    run: PaperRunModel,
    symbol: str,
    context: dict[str, Any],
) -> list[UiTimelineStage]:
    reports: list[AnalystReportModel] = context["analyst_reports"]
    debate: DebateReportModel | None = context["debate"]
    proposal: TraderProposalModel | None = context["trader_proposal"]
    risk_review: RiskReviewModel | None = context["risk_review"]
    final_decision: FinalDecisionModel | None = context["final_decision"]
    orders: list[PaperOrderModel] = context["orders"]
    fills: list[PaperFillModel] = context["fills"]
    audit_rows: list[AuditLogModel] = context["audit_rows"]
    events: list[CompanyEventModel] = context["events"]

    input_stage = _input_stage(run=run, symbol=symbol, events=events)
    analyst_stage = _stage(
        id="analyst_reports",
        label="Analyst Reports",
        status="complete" if reports else "missing",
        summary=_analyst_summary(reports),
        timestamp=max((report.as_of for report in reports), default=None),
        artifact_ids=[report.report_id for report in reports],
        artifacts=[_payload(report) for report in reports],
        metrics={"report_count": len(reports)},
    )
    debate_stage = _single_artifact_stage(
        id="debate_report",
        label="Debate",
        row=debate,
        artifact_id_attr="debate_id",
        timestamp_attr="as_of",
        status="complete" if debate is not None else "missing",
        missing_summary="No debate report is stored for this run and symbol.",
        summary=_debate_summary(debate),
        metrics=_debate_metrics(debate),
    )
    proposal_stage = _single_artifact_stage(
        id="trader_proposal",
        label="Trader Proposal",
        row=proposal,
        artifact_id_attr="proposal_id",
        timestamp_attr="as_of",
        status="complete" if proposal is not None else "missing",
        missing_summary="No trader proposal is stored for this run and symbol.",
        summary=_proposal_summary(proposal),
        metrics=_proposal_metrics(proposal),
    )
    risk_stage = _single_artifact_stage(
        id="risk_review",
        label="Risk Review",
        row=risk_review,
        artifact_id_attr="risk_check_id",
        timestamp_attr="as_of",
        status=_risk_status(risk_review),
        missing_summary="No risk review is stored for this run and symbol.",
        summary=_risk_summary(risk_review),
        metrics=_risk_metrics(risk_review),
    )
    final_stage = _single_artifact_stage(
        id="final_decision",
        label="Final Decision",
        row=final_decision,
        artifact_id_attr="final_decision_id",
        timestamp_attr="as_of",
        status=_final_status(final_decision),
        missing_summary="No final decision is stored for this run and symbol.",
        summary=_final_summary(final_decision),
        metrics=_final_metrics(final_decision),
    )
    order_stage = _order_stage(orders=orders, final_decision=final_decision)
    fill_stage = _fill_stage(fills=fills, orders=orders, final_decision=final_decision)
    audit_stage = _stage(
        id="audit_log",
        label="Audit Log",
        status="complete" if audit_rows else "missing",
        summary=f"{len(audit_rows)} audit event(s) linked to this run and symbol."
        if audit_rows
        else "No audit rows are linked to this run and symbol.",
        timestamp=max((row.created_at for row in audit_rows), default=None),
        artifact_ids=[str(row.id) for row in audit_rows],
        artifacts=[_audit_payload(row) for row in audit_rows],
        metrics={"event_count": len(audit_rows)},
    )
    return [
        input_stage,
        analyst_stage,
        debate_stage,
        proposal_stage,
        risk_stage,
        final_stage,
        order_stage,
        fill_stage,
        audit_stage,
    ]


def _input_stage(
    *,
    run: PaperRunModel,
    symbol: str,
    events: list[CompanyEventModel],
) -> UiTimelineStage:
    market_summary = _json_safe(run.market_data_summary)
    strategy = _strategy_summary(run)
    symbol_artifacts = _symbol_artifacts(run, symbol)
    status: StageStatus = "complete" if market_summary or strategy else "missing"
    event_payloads = [_event_payload(event) for event in events]
    provider = _market_provider(run) or "unknown"
    candle_count = market_summary.get("candle_count") if isinstance(market_summary, dict) else None
    return _stage(
        id="inputs",
        label="Inputs",
        status=status,
        summary=f"Market provider {provider}; {candle_count or 0} candle(s); {len(events)} event(s).",
        timestamp=run.started_at,
        artifact_ids=[run.run_id, *[event.event_id for event in events]],
        artifacts=[
            {
                "run_id": run.run_id,
                "market_data_summary": market_summary,
                "strategy_summary": strategy,
                "symbol_artifacts": symbol_artifacts,
                "events": event_payloads,
            }
        ],
        metrics={
            "market_provider": provider,
            "candle_count": candle_count,
            "event_count": len(events),
            "feature_snapshot_count": strategy.get("feature_snapshot_count"),
        },
        raw={
            "market_data_summary": market_summary,
            "strategy_summary": strategy,
            "symbol_artifacts": symbol_artifacts,
            "events": event_payloads,
        },
    )


def _single_artifact_stage(
    *,
    id: str,
    label: str,
    row: Any | None,
    artifact_id_attr: str,
    timestamp_attr: str,
    status: StageStatus,
    missing_summary: str,
    summary: str,
    metrics: dict[str, Any],
) -> UiTimelineStage:
    if row is None:
        return _stage(
            id=id,
            label=label,
            status=status,
            summary=missing_summary,
            metrics=metrics,
        )
    return _stage(
        id=id,
        label=label,
        status=status,
        summary=summary,
        timestamp=getattr(row, timestamp_attr),
        artifact_ids=[str(getattr(row, artifact_id_attr))],
        artifacts=[_payload(row)],
        metrics=metrics,
    )


def _order_stage(
    *,
    orders: list[PaperOrderModel],
    final_decision: FinalDecisionModel | None,
) -> UiTimelineStage:
    if not orders:
        if final_decision is None:
            return _stage(
                id="paper_order",
                label="Paper Order",
                status="skipped",
                summary="No final decision is available, so broker routing did not run.",
            )
        if final_decision.status != "APPROVED_FOR_PAPER":
            if final_decision.status == "NO_ACTION":
                return _stage(
                    id="paper_order",
                    label="Paper Order",
                    status="skipped",
                    summary="No paper order expected for approved HOLD/NO_TRADE lifecycle decision.",
                )
            return _stage(
                id="paper_order",
                label="Paper Order",
                status="skipped",
                summary=f"Paper order skipped because final decision is {final_decision.status}.",
            )
        return _stage(
            id="paper_order",
            label="Paper Order",
            status="missing",
            summary="Final decision is approved for paper but no paper order was stored.",
        )
    order = orders[0]
    return _stage(
        id="paper_order",
        label="Paper Order",
        status=_order_status(order),
        summary=_order_summary(order),
        timestamp=order.submitted_at,
        artifact_ids=[order.order_id],
        artifacts=[_payload(row) for row in orders],
        metrics={
            "order_count": len(orders),
            "status": order.status,
            "filled_quantity": order.filled_quantity,
            "average_fill_price_inr": _decimal_to_number(order.average_fill_price_inr),
            "total_cost_inr": _decimal_to_number(order.total_cost_inr),
            "slippage_bps": _decimal_to_number(order.slippage_bps),
        },
    )


def _fill_stage(
    *,
    fills: list[PaperFillModel],
    orders: list[PaperOrderModel],
    final_decision: FinalDecisionModel | None,
) -> UiTimelineStage:
    if not fills:
        if not orders:
            if final_decision is not None and final_decision.status == "NO_ACTION":
                return _stage(
                    id="paper_fills",
                    label="Paper Fills",
                    status="skipped",
                    summary="No paper order expected, so no fills were generated.",
                )
            return _stage(
                id="paper_fills",
                label="Paper Fills",
                status="skipped",
                summary="No paper order exists, so no fills were generated.",
            )
        if orders[0].status == "REJECTED":
            return _stage(
                id="paper_fills",
                label="Paper Fills",
                status="skipped",
                summary="Paper order was rejected, so no fills were generated.",
            )
        if orders[0].status == "PENDING_NEXT_OPEN":
            return _stage(
                id="paper_fills",
                label="Paper Fills",
                status="running",
                summary="Paper order is queued for next-open settlement; no fills are expected yet.",
                timestamp=orders[0].submitted_at,
                artifact_ids=[orders[0].order_id],
                metrics={
                    "order_count": len(orders),
                    "status": orders[0].status,
                    "filled_quantity": orders[0].filled_quantity,
                },
            )
        if final_decision is not None and final_decision.status != "APPROVED_FOR_PAPER":
            return _stage(
                id="paper_fills",
                label="Paper Fills",
                status="skipped",
                summary=f"Fills skipped because final decision is {final_decision.status}.",
            )
        return _stage(
            id="paper_fills",
            label="Paper Fills",
            status="missing",
            summary="Paper order exists but no fill rows are stored.",
        )
    return _stage(
        id="paper_fills",
        label="Paper Fills",
        status="complete",
        summary=f"{len(fills)} fill(s) stored for paper execution.",
        timestamp=max(fill.filled_at for fill in fills),
        artifact_ids=[fill.fill_id for fill in fills],
        artifacts=[_payload(fill) for fill in fills],
        metrics={
            "fill_count": len(fills),
            "filled_quantity": sum(fill.quantity for fill in fills),
            "total_cost_inr": sum(
                (_decimal_to_number(fill.cost_inr) or 0) for fill in fills
            ),
            "total_slippage_inr": sum(
                (_decimal_to_number(fill.slippage_inr) or 0) for fill in fills
            ),
        },
    )


def _stage(
    *,
    id: str,
    label: str,
    status: StageStatus,
    summary: str,
    timestamp: datetime | None = None,
    metrics: dict[str, Any] | None = None,
    artifact_ids: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    raw: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> UiTimelineStage:
    safe_artifacts = _json_safe(artifacts or [])
    return UiTimelineStage(
        id=id,
        label=label,
        status=status,
        timestamp=timestamp,
        summary=summary,
        metrics=_json_safe(metrics or {}),
        artifact_ids=artifact_ids or [],
        artifacts=safe_artifacts,
        raw=_json_safe(raw if raw is not None else safe_artifacts),
    )


def _stage_summary(stage: UiTimelineStage) -> UiStageSummary:
    return UiStageSummary(
        id=stage.id,
        label=stage.label,
        status=stage.status,
        summary=stage.summary,
        timestamp=stage.timestamp,
        artifact_ids=stage.artifact_ids,
    )


def _pipeline_status(
    *,
    run: PaperRunModel,
    stages: list[UiStageSummary],
    final_decision: FinalDecisionModel | None,
    errors: list[str],
) -> StageStatus:
    if errors:
        return "failed"
    if any(stage.status == "running" for stage in stages):
        return "running"
    if final_decision is not None:
        return _final_status(final_decision)
    if run.status == "RUNNING":
        return "running"
    if any(stage.status == "missing" for stage in stages):
        return "missing"
    return "complete"


def _risk_status(review: RiskReviewModel | None) -> StageStatus:
    if review is None:
        return "missing"
    if review.status == "BLOCKED":
        return "blocked"
    if review.status == "REJECTED":
        return "rejected"
    return "complete"


def _final_status(decision: FinalDecisionModel | None) -> StageStatus:
    if decision is None:
        return "missing"
    if decision.status == "BLOCKED":
        return "blocked"
    if decision.status == "REJECTED":
        return "rejected"
    return "complete"


def _order_status(order: PaperOrderModel) -> StageStatus:
    if order.status == "REJECTED":
        return "rejected"
    if order.status == "CANCELLED":
        return "blocked"
    if order.status in {"CREATED", "ACCEPTED", "PENDING_NEXT_OPEN", "PARTIALLY_FILLED"}:
        return "running"
    return "complete"


def _payload(row: Any) -> dict[str, Any]:
    return _json_safe(dict(row.payload or {}))


def _monitor_status(session: Session, settings: Settings) -> dict[str, Any]:
    latest = session.scalar(
        select(AuditLogModel)
        .where(AuditLogModel.event_type.like("position_monitor.%"))
        .order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
        .limit(1)
    )
    today = datetime.now(timezone.utc).astimezone(
        _timezone(settings.taurus_paper_timezone)
    ).date().isoformat()
    trigger_count = int(
        session.scalar(
            select(func.count())
            .select_from(AuditLogModel)
            .where(
                AuditLogModel.event_type == "position_monitor.trigger_detected",
                AuditLogModel.payload["market_session_date"].as_string() == today,
            )
        )
        or 0
    )
    return _json_safe(
        {
            "enabled": settings.taurus_position_monitor_enabled,
            "provider": settings.taurus_position_monitor_provider,
            "market_hours_only": settings.taurus_position_monitor_market_hours_only,
            "interval_seconds": settings.taurus_position_monitor_interval_seconds,
            "max_iterations": settings.taurus_position_monitor_max_iterations,
            "latest_event_type": latest.event_type if latest is not None else None,
            "latest_note": latest.note if latest is not None else None,
            "last_iteration_time": latest.created_at if latest is not None else None,
            "trigger_count_today": trigger_count,
        }
    )


def _monitor_enriched_positions(
    session: Session,
    *,
    settings: Settings,
    positions: list[Any],
) -> list[dict[str, Any]]:
    research_repo = ResearchRepository(session)
    allocation_by_symbol = _latest_allocation_decisions_by_symbol(session, settings)
    metadata = money_management_metadata(settings)
    policy = metadata.get("policy") if isinstance(metadata.get("policy"), dict) else {}
    latest_runs = PaperRunRepository(session).list(limit=1)
    core_sleeve = _core_sleeve_metadata(
        policy=policy,
        latest_run=latest_runs[0] if latest_runs else None,
    )
    enriched: list[dict[str, Any]] = []
    for position in positions:
        payload = _payload(position)
        payload.update(
            _position_allocation_labels(
                symbol=position.symbol,
                allocation_decision=allocation_by_symbol.get(position.symbol.upper()),
                core_sleeve=core_sleeve,
            )
        )
        latest_snapshot = session.scalar(
            select(MarketPriceSnapshotModel)
            .where(
                MarketPriceSnapshotModel.provider == settings.taurus_position_monitor_provider,
                MarketPriceSnapshotModel.symbol == position.symbol,
            )
            .order_by(
                MarketPriceSnapshotModel.fetched_at.desc(),
                MarketPriceSnapshotModel.id.desc(),
            )
            .limit(1)
        )
        proposals = research_repo.list_trader_proposals(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol=position.symbol,
            limit=20,
        )
        base_payload = None
        for proposal in proposals:
            candidate = _payload(proposal)
            if candidate.get("evaluation_mode") != "market_hours":
                base_payload = candidate
                break
        stop_loss_pct = _decimal_or_none(
            base_payload.get("stop_loss_pct") if base_payload else None
        )
        take_profit_pct = _decimal_or_none(
            base_payload.get("take_profit_pct") if base_payload else None
        )
        average_cost = _decimal_or_none(payload.get("average_cost_inr"))
        latest_price = (
            latest_snapshot.last_price
            if latest_snapshot is not None
            else _decimal_or_none(payload.get("last_price_inr"))
        )
        monitor_payload: dict[str, Any] = {
            "latest_quote_id": latest_snapshot.id if latest_snapshot is not None else None,
            "latest_quote_ltp_inr": latest_price,
            "latest_quote_fetched_at": latest_snapshot.fetched_at
            if latest_snapshot is not None
            else None,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
        }
        if average_cost is not None and stop_loss_pct is not None and take_profit_pct is not None:
            stop_loss_price = average_cost * (Decimal("1") - stop_loss_pct / Decimal("100"))
            take_profit_price = average_cost * (Decimal("1") + take_profit_pct / Decimal("100"))
            monitor_payload.update(
                {
                    "stop_loss_price_inr": stop_loss_price,
                    "take_profit_price_inr": take_profit_price,
                    "distance_to_stop_loss_inr": latest_price - stop_loss_price
                    if latest_price is not None
                    else None,
                    "distance_to_take_profit_inr": take_profit_price - latest_price
                    if latest_price is not None
                    else None,
                }
            )
        payload.update(_json_safe(monitor_payload))
        enriched.append(payload)
    return enriched


def _allocation_dashboard_payload(
    *,
    session: Session,
    settings: Settings,
    account: dict[str, Any] | None = None,
    positions: list[dict[str, Any]] | None = None,
    latest_run: PaperRunModel | None = None,
) -> dict[str, Any]:
    metadata = money_management_metadata(settings)
    if not metadata.get("enabled"):
        return {
            "enabled": False,
            "config_path": metadata.get("config_path"),
            "summary_metrics": [],
            "sleeves": [],
            "core_basket": _empty_core_basket(),
            "cash": {},
            "open_risk": {},
            "latest_decisions": [],
            "drawdown_governors": {},
        }

    execution_repo = ExecutionRepository(session)
    account_payload = account
    if account_payload is None:
        account_row = execution_repo.latest_account_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )
        account_payload = _payload(account_row) if account_row is not None else None

    if latest_run is None:
        latest_runs = PaperRunRepository(session).list(limit=1)
        latest_run = latest_runs[0] if latest_runs else None

    policy = metadata.get("policy") if isinstance(metadata.get("policy"), dict) else {}
    position_payloads = positions
    if position_payloads is None:
        allocation_by_symbol = _latest_allocation_decisions_by_symbol(session, settings)
        core_sleeve = _core_sleeve_metadata(policy=policy, latest_run=latest_run)
        position_payloads = []
        for row in execution_repo.latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        ):
            payload = _payload(row)
            payload.update(
                _position_allocation_labels(
                    symbol=row.symbol,
                    allocation_decision=allocation_by_symbol.get(row.symbol.upper()),
                    core_sleeve=core_sleeve,
                )
            )
            position_payloads.append(payload)

    nav_inr = _decimal_or_none(
        account_payload.get("equity_inr") if account_payload else None
    ) or Decimal(str(settings.taurus_initial_capital_inr))
    available_cash = _decimal_or_none(
        account_payload.get("available_cash_inr") if account_payload else None
    ) or nav_inr
    allocation_decisions = _latest_allocation_decisions(session, settings, limit=25)
    sleeves = _sleeve_allocation_rows(
        policy=policy,
        nav_inr=nav_inr,
        positions=position_payloads,
        allocation_decisions=allocation_decisions,
    )
    cash = _cash_allocation_payload(
        policy=policy,
        nav_inr=nav_inr,
        available_cash=available_cash,
    )
    open_risk = _open_risk_payload(
        policy=policy,
        nav_inr=nav_inr,
        allocation_decisions=allocation_decisions,
    )
    core_basket = _core_basket_payload(latest_run, nav_inr=nav_inr)
    drawdown_governors = _drawdown_governor_payload(
        metadata=metadata,
        allocation_decisions=allocation_decisions,
    )
    return _json_safe(
        {
            "enabled": True,
            "config_path": metadata.get("config_path"),
            "policy_version": policy.get("policy_version"),
            "summary_metrics": [
                {
                    "label": "Sleeves",
                    "value": len(sleeves),
                    "tone": "neutral",
                },
                {
                    "label": "Cash buffer",
                    "value": cash.get("current_cash_pct_nav"),
                    "unit": "%",
                    "tone": "success"
                    if _decimal_or_none(cash.get("cash_surplus_inr")) is not None
                    and _decimal_or_none(cash.get("cash_surplus_inr")) >= 0
                    else "caution",
                },
                {
                    "label": "Undeployed capacity",
                    "value": cash.get("undeployed_capacity_inr"),
                    "unit": "INR",
                    "tone": "neutral",
                },
                {
                    "label": "Open risk used",
                    "value": open_risk.get("used_pct_limit"),
                    "unit": "%",
                    "tone": "caution"
                    if (_decimal_or_none(open_risk.get("used_pct_limit")) or Decimal("0"))
                    > Decimal("80")
                    else "neutral",
                },
            ],
            "sleeves": sleeves,
            "core_basket": core_basket,
            "cash": cash,
            "open_risk": open_risk,
            "latest_decisions": allocation_decisions[:10],
            "drawdown_governors": drawdown_governors,
        }
    )


def _latest_allocation_decision(context: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("final_decision", "risk_review", "trader_proposal"):
        row = context.get(key)
        if row is None:
            continue
        decision = _allocation_decision_from_payload(_payload(row))
        if decision is not None:
            return decision
    return None


def _latest_allocation_decisions_by_symbol(
    session: Session,
    settings: Settings,
) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for decision in _latest_allocation_decisions(session, settings, limit=200):
        symbol = str(decision.get("symbol") or "").upper()
        if symbol and symbol not in decisions:
            decisions[symbol] = decision
    return decisions


def _latest_allocation_decisions(
    session: Session,
    settings: Settings,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    research_repo = ResearchRepository(session)
    risk_repo = RiskRepository(session)
    execution_repo = ExecutionRepository(session)

    for run in PaperRunRepository(session).list(limit=25):
        ledger = _allocation_ledger(run)
        if not ledger:
            continue
        proposals = research_repo.list_trader_proposals(run_id=run.run_id, limit=None)
        final_decisions = risk_repo.list_final_decisions(run_id=run.run_id, limit=None)
        orders = execution_repo.list_orders(run_id=run.run_id, limit=None)
        proposals_by_symbol = {proposal.symbol.upper(): proposal for proposal in proposals}
        final_by_symbol = {decision.symbol.upper(): decision for decision in final_decisions}
        order_by_symbol = {order.symbol.upper(): order for order in orders}
        execution_by_symbol = _execution_artifacts_by_symbol(run)

        for entry in ledger:
            symbol = str(entry.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            proposal = proposals_by_symbol.get(symbol)
            proposal_payload = _payload(proposal) if proposal is not None else {}
            decision = _allocation_decision_from_payload(proposal_payload) or {}
            selection = _selection_row_from_entry(
                entry,
                proposal=proposal,
                final_decision=final_by_symbol.get(symbol),
                order=order_by_symbol.get(symbol),
                execution_artifact=execution_by_symbol.get(symbol),
            )
            decisions.append(
                _json_safe(
                    {
                        **decision,
                        **entry,
                        "status": selection.allocation_status,
                        "run_id": run.run_id,
                        "proposal_id": selection.proposal_id,
                        "as_of": proposal.as_of if proposal is not None else run.started_at,
                        "lifecycle_trigger": proposal.lifecycle_trigger
                        if proposal is not None
                        else None,
                        "evaluation_mode": proposal.evaluation_mode
                        if proposal is not None
                        else None,
                        "rank": selection.rank,
                        "strategy_score": selection.strategy_score,
                        "trader_action": selection.trader_action,
                        "proposal_confidence": selection.proposal_confidence,
                        "allocation_status": selection.allocation_status,
                        "final_status": selection.final_status,
                        "final_action": selection.final_action,
                        "execution_status": selection.execution_status,
                        "reason": selection.reason,
                    }
                )
            )
            if len(decisions) >= limit:
                return decisions

    if decisions:
        return decisions[:limit]

    for proposal in ResearchRepository(session).list_trader_proposals(
        portfolio_id=settings.taurus_paper_portfolio_id,
        limit=limit,
    ):
        payload = _payload(proposal)
        decision = _allocation_decision_from_payload(payload)
        if decision is None:
            continue
        decisions.append(
            _json_safe(
                {
                    **decision,
                    "run_id": proposal.run_id,
                    "proposal_id": proposal.proposal_id,
                    "as_of": proposal.as_of,
                    "lifecycle_trigger": proposal.lifecycle_trigger,
                    "evaluation_mode": proposal.evaluation_mode,
                }
            )
        )
    return decisions


def _allocation_decision_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("allocation_decision")
    if not isinstance(raw, dict):
        return None
    return _json_safe(raw)


def _core_sleeve_metadata(
    *,
    policy: dict[str, Any],
    latest_run: PaperRunModel | None,
) -> dict[str, Any] | None:
    runtime_symbols = _core_basket_target_symbols(latest_run)
    for sleeve in policy.get("sleeves", []):
        if isinstance(sleeve, dict) and sleeve.get("sleeve_id") == "core_shariah":
            return {
                "sleeve_id": "core_shariah",
                "sleeve_name": sleeve.get("name"),
                "strategy_name": "core_shariah_basket_v1",
                "runtime_symbols": runtime_symbols,
            }
    return None


def _position_allocation_labels(
    *,
    symbol: str,
    allocation_decision: dict[str, Any] | None,
    core_sleeve: dict[str, Any] | None,
) -> dict[str, Any]:
    if allocation_decision is not None:
        return {
            "sleeve_id": allocation_decision.get("sleeve_id"),
            "sleeve_name": allocation_decision.get("sleeve_name"),
            "strategy_name": allocation_decision.get("strategy_name"),
            "allocation_status": allocation_decision.get("status"),
            "binding_constraint": allocation_decision.get("binding_constraint"),
        }
    if core_sleeve is not None and symbol.upper() in core_sleeve.get("runtime_symbols", set()):
        return {
            "sleeve_id": core_sleeve.get("sleeve_id"),
            "sleeve_name": core_sleeve.get("sleeve_name"),
            "strategy_name": core_sleeve.get("strategy_name"),
            "allocation_status": "core_position",
            "binding_constraint": None,
        }
    return {
        "sleeve_id": None,
        "sleeve_name": None,
        "strategy_name": None,
        "allocation_status": "unassigned",
        "binding_constraint": None,
    }


def _sleeve_allocation_rows(
    *,
    policy: dict[str, Any],
    nav_inr: Decimal,
    positions: list[dict[str, Any]],
    allocation_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sleeves = [sleeve for sleeve in policy.get("sleeves", []) if isinstance(sleeve, dict)]
    estimated_risk_by_sleeve: dict[str, Decimal] = {}
    for decision in allocation_decisions:
        sleeve_id = str(decision.get("sleeve_id") or "")
        if not sleeve_id:
            continue
        estimated_risk_by_sleeve[sleeve_id] = estimated_risk_by_sleeve.get(
            sleeve_id,
            Decimal("0"),
        ) + (_decimal_or_none(decision.get("estimated_risk_inr")) or Decimal("0"))

    for sleeve in sleeves:
        sleeve_id = str(sleeve.get("sleeve_id") or "")
        target_pct = _decimal_or_none(sleeve.get("target_weight_pct")) or Decimal("0")
        sleeve_positions = [
            position
            for position in positions
            if str(position.get("sleeve_id") or "") == sleeve_id
        ]
        current_exposure = sum(
            (
                _decimal_or_none(position.get("market_value_inr")) or Decimal("0")
                for position in sleeve_positions
            ),
            Decimal("0"),
        )
        current_pct = _pct_of_nav(current_exposure, nav_inr)
        target_notional = _pct_to_nav(target_pct, nav_inr)
        drift_pct = (current_pct - target_pct).quantize(Decimal("0.0001"))
        rows.append(
            {
                "sleeve_id": sleeve_id,
                "sleeve_name": sleeve.get("name"),
                "role": sleeve.get("role"),
                "target_weight_pct": target_pct,
                "target_notional_inr": target_notional,
                "current_weight_pct": current_pct,
                "current_exposure_inr": current_exposure,
                "drift_pct_nav": drift_pct,
                "drift_notional_inr": current_exposure - target_notional,
                "open_position_count": len(sleeve_positions),
                "symbols": sorted(
                    str(position.get("symbol") or "").upper()
                    for position in sleeve_positions
                    if position.get("symbol")
                ),
                "open_trade_risk_inr": estimated_risk_by_sleeve.get(sleeve_id, Decimal("0")),
                "new_entry_risk_cap_pct_nav": sleeve.get("new_entry_risk_cap_pct_nav"),
            }
        )
    return rows


def _cash_allocation_payload(
    *,
    policy: dict[str, Any],
    nav_inr: Decimal,
    available_cash: Decimal,
) -> dict[str, Any]:
    target_pct = _sleeve_target_pct(policy, "cash_buffer")
    target_cash = _pct_to_nav(target_pct, nav_inr)
    surplus = available_cash - target_cash
    return {
        "target_cash_pct_nav": target_pct,
        "target_cash_inr": target_cash,
        "available_cash_inr": available_cash,
        "current_cash_pct_nav": _pct_of_nav(available_cash, nav_inr),
        "cash_surplus_inr": surplus,
        "undeployed_capacity_inr": max(surplus, Decimal("0")),
    }


def _open_risk_payload(
    *,
    policy: dict[str, Any],
    nav_inr: Decimal,
    allocation_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    trade_risk = policy.get("trade_risk") if isinstance(policy.get("trade_risk"), dict) else {}
    limit_pct = _decimal_or_none(
        trade_risk.get("max_total_open_trade_risk_pct_nav")
    ) or Decimal("0")
    limit_inr = _pct_to_nav(limit_pct, nav_inr)
    used_inr = sum(
        (
            _decimal_or_none(decision.get("estimated_risk_inr")) or Decimal("0")
            for decision in allocation_decisions
            if decision.get("status") != "rejected"
        ),
        Decimal("0"),
    )
    return {
        "used_risk_inr": used_inr,
        "limit_risk_inr": limit_inr,
        "limit_pct_nav": limit_pct,
        "remaining_risk_inr": max(limit_inr - used_inr, Decimal("0")),
        "used_pct_limit": (used_inr * Decimal("100") / limit_inr).quantize(Decimal("0.0001"))
        if limit_inr > 0
        else Decimal("0"),
    }


def _core_basket_payload(
    latest_run: PaperRunModel | None,
    *,
    nav_inr: Decimal,
) -> dict[str, Any]:
    if latest_run is None:
        return _empty_core_basket()
    artifacts = latest_run.artifacts or {}
    money_management = artifacts.get("money_management")
    if not isinstance(money_management, dict):
        return _empty_core_basket()
    core = money_management.get("core_shariah_basket")
    if not isinstance(core, dict):
        return _empty_core_basket()
    target_weights = core.get("target_weights") if isinstance(core.get("target_weights"), dict) else {}
    current_weights = core.get("current_weights") if isinstance(core.get("current_weights"), dict) else {}
    target_weights_by_symbol = {
        str(symbol).upper(): value
        for symbol, value in target_weights.items()
        if str(symbol).strip()
    }
    current_weights_by_symbol = {
        str(symbol).upper(): value
        for symbol, value in current_weights.items()
        if str(symbol).strip()
    }
    symbols = sorted(target_weights_by_symbol)
    composition = []
    for symbol in symbols:
        target_pct = _decimal_or_none(target_weights_by_symbol.get(symbol)) or Decimal("0")
        current_pct = _decimal_or_none(current_weights_by_symbol.get(symbol)) or Decimal("0")
        composition.append(
            {
                "symbol": symbol,
                "target_weight_pct_nav": target_pct,
                "current_weight_pct_nav": current_pct,
                "drift_pct_nav": (current_pct - target_pct).quantize(Decimal("0.0001")),
                "target_notional_inr": _pct_to_nav(target_pct, nav_inr),
                "current_notional_inr": _pct_to_nav(current_pct, nav_inr),
            }
        )
    return _json_safe(
        {
            "available": True,
            "run_id": latest_run.run_id,
            "strategy_name": core.get("strategy_name"),
            "sleeve_id": core.get("sleeve_id"),
            "as_of_date": core.get("as_of_date"),
            "symbols": symbols,
            "selected_symbols": core.get("selected_symbols", []),
            "candidate_count": core.get("candidate_count"),
            "drift": core.get("drift", {}),
            "rebalance": core.get("rebalance", {}),
            "composition": composition,
            "rejected_candidates": core.get("rejected_candidates", []),
        }
    )


def _empty_core_basket() -> dict[str, Any]:
    return {
        "available": False,
        "symbols": [],
        "selected_symbols": [],
        "composition": [],
        "rejected_candidates": [],
        "drift": {},
        "rebalance": {},
    }


def _core_basket_target_symbols(latest_run: PaperRunModel | None) -> set[str]:
    if latest_run is None:
        return set()
    artifacts = latest_run.artifacts or {}
    money_management = artifacts.get("money_management")
    if not isinstance(money_management, dict):
        return set()
    core = money_management.get("core_shariah_basket")
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


def _sleeve_target_pct(policy: dict[str, Any], sleeve_id: str) -> Decimal:
    for sleeve in policy.get("sleeves", []):
        if not isinstance(sleeve, dict):
            continue
        if str(sleeve.get("sleeve_id") or "").strip().lower() != sleeve_id:
            continue
        return _decimal_or_none(sleeve.get("target_weight_pct")) or Decimal("0")
    return Decimal("0")


def _drawdown_governor_payload(
    *,
    metadata: dict[str, Any],
    allocation_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    state = metadata.get("state") if isinstance(metadata.get("state"), dict) else {}
    policy = metadata.get("policy") if isinstance(metadata.get("policy"), dict) else {}
    latest_reasons: list[str] = []
    for decision in allocation_decisions:
        raw_reasons = decision.get("governor_reasons")
        if isinstance(raw_reasons, list):
            latest_reasons.extend(str(reason) for reason in raw_reasons)
    return {
        "portfolio_drawdown_pct": state.get("portfolio_drawdown_pct"),
        "portfolio_governor_reasons": state.get("portfolio_governor_reasons", []),
        "policy_thresholds": policy.get("drawdown_governors", []),
        "sleeve_statuses": state.get("sleeve_statuses", []),
        "latest_decision_governor_reasons": sorted(set(latest_reasons)),
        "fractional_kelly": state.get("fractional_kelly", {}),
    }


def _pct_to_nav(percent: Decimal, nav_inr: Decimal) -> Decimal:
    return (nav_inr * percent / Decimal("100")).quantize(Decimal("0.01"))


def _pct_of_nav(notional_inr: Decimal, nav_inr: Decimal) -> Decimal:
    if nav_inr <= 0:
        return Decimal("0.0000")
    return (notional_inr * Decimal("100") / nav_inr).quantize(Decimal("0.0001"))


def _risk_review_payload(session: Session, review: RiskReviewModel) -> dict[str, Any]:
    payload = _payload(review)
    proposal = ResearchRepository(session).get_trader_proposal(review.proposal_id)
    if proposal is not None:
        proposal_payload = _payload(proposal)
        payload.update(
            {
                "proposal_action": proposal_payload.get("action"),
                "lifecycle_trigger": proposal_payload.get("lifecycle_trigger"),
                "evaluation_mode": proposal_payload.get("evaluation_mode"),
                "current_position_quantity": proposal_payload.get("current_position_quantity"),
                "current_position_pct_nav": proposal_payload.get("current_position_pct_nav"),
                "target_position_pct_nav": proposal_payload.get("target_position_pct_nav"),
                "latest_price_inr": proposal_payload.get("latest_price_inr"),
                "trigger_threshold_price_inr": proposal_payload.get(
                    "trigger_threshold_price_inr"
                ),
                "market_session_date": proposal_payload.get("market_session_date"),
                "position_management_summary": proposal_payload.get(
                    "position_management_summary"
                ),
            }
        )
        allocation_decision = _allocation_decision_from_payload(proposal_payload)
        if allocation_decision is not None:
            payload.update(
                {
                    "allocation_decision": allocation_decision,
                    "sleeve_id": allocation_decision.get("sleeve_id"),
                    "sleeve_name": allocation_decision.get("sleeve_name"),
                    "strategy_name": allocation_decision.get("strategy_name"),
                    "allocation_status": allocation_decision.get("status"),
                    "binding_constraint": allocation_decision.get("binding_constraint"),
                    "estimated_risk_inr": allocation_decision.get("estimated_risk_inr"),
                    "allowed_risk_inr": allocation_decision.get("allowed_risk_inr"),
                    "governor_scale_factor": allocation_decision.get(
                        "governor_scale_factor"
                    ),
                }
            )
    return payload


def _audit_payload(row: AuditLogModel) -> dict[str, Any]:
    return _json_safe(
        {
            "id": row.id,
            "event_type": row.event_type,
            "actor": row.actor,
            "payload": row.payload,
            "note": row.note,
            "created_at": row.created_at,
        }
    )


def _event_payload(row: CompanyEventModel) -> dict[str, Any]:
    return _json_safe(
        {
            "event_id": row.event_id,
            "document_id": row.document_id,
            "symbol": row.symbol,
            "event_type": row.event_type,
            "event_time": row.event_time,
            "headline": row.headline,
            "summary": row.summary,
            "severity": row.severity,
            "horizon": row.horizon,
            "source_confidence": row.source_confidence,
        }
    )


def _strategy_summary(run: PaperRunModel) -> dict[str, Any]:
    artifacts = run.artifacts or {}
    strategy = artifacts.get("strategy", {})
    return _json_safe(strategy if isinstance(strategy, dict) else {})


def _symbol_artifacts(run: PaperRunModel, symbol: str) -> dict[str, Any]:
    artifacts = run.artifacts or {}
    symbols = artifacts.get("symbols", {})
    if not isinstance(symbols, dict):
        return {}
    value = symbols.get(symbol.upper(), {})
    return _json_safe(value if isinstance(value, dict) else {})


def _analyst_roster(run: PaperRunModel, symbol: str) -> UiAnalystRoster | None:
    artifacts = _symbol_artifacts(run, symbol)
    roster = artifacts.get("analyst_roster")
    if not isinstance(roster, dict):
        return None
    return UiAnalystRoster.model_validate(_json_safe(roster))


def _market_provider(run: PaperRunModel) -> str | None:
    summary = run.market_data_summary or {}
    provider = summary.get("provider_name") or summary.get("provider")
    return str(provider) if provider is not None else None


def _run_universe(run: PaperRunModel) -> UiRunUniverse | None:
    payload = run.payload or {}
    raw_universe = payload.get("universe")
    if not isinstance(raw_universe, dict):
        return None
    safe_universe = _json_safe(raw_universe)
    if not isinstance(safe_universe, dict) or not safe_universe.get("source"):
        return None
    return UiRunUniverse.model_validate(safe_universe)


def _duration_seconds(
    started_at: datetime,
    completed_at: datetime | None,
) -> float | None:
    if completed_at is None:
        return None
    return max((completed_at - started_at).total_seconds(), 0.0)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _symbol_errors(run: PaperRunModel, symbol: str) -> list[str]:
    normalized_symbol = symbol.upper()
    errors = []
    for error in run.errors:
        if str(error.get("symbol", "")).upper() in {normalized_symbol, "*"}:
            message = str(error.get("message", "Unknown symbol error."))
            stage = str(error.get("stage", "unknown"))
            errors.append(f"{stage}: {message}")
    return errors


def _overview_warnings(
    *,
    run_rows: list[PaperRunModel],
    latest_account: dict[str, Any] | None,
    latest_final: FinalDecisionModel | None,
) -> list[UiWarning]:
    warnings: list[UiWarning] = []
    if latest_account is None:
        warnings.append(
            UiWarning(
                id="missing-paper-account",
                severity="info",
                title="No paper account state",
                message="No paper account has been stored yet.",
            )
        )
    for run in run_rows[:5]:
        if run.status in {"PARTIAL_FAILED", "FAILED"}:
            warnings.append(
                UiWarning(
                    id=f"run-{run.run_id}-{run.status.lower()}",
                    severity="critical" if run.status == "FAILED" else "warning",
                    title=f"Paper run {run.status.lower()}",
                    message=f"{run.run_id} recorded {len(run.errors)} error(s).",
                    run_id=run.run_id,
                    created_at=run.completed_at or run.started_at,
                )
            )
    if latest_final is not None and latest_final.status in {"REJECTED", "BLOCKED"}:
        warnings.append(
            UiWarning(
                id=f"final-{latest_final.final_decision_id}-{latest_final.status.lower()}",
                severity="warning",
                title=f"Latest final decision {latest_final.status.lower()}",
                message=f"{latest_final.symbol} ended with {latest_final.status}.",
                run_id=latest_final.run_id,
                symbol=latest_final.symbol,
                created_at=latest_final.as_of,
            )
        )
    return warnings


def _run_warnings(run: PaperRunModel) -> list[UiWarning]:
    return [
        UiWarning(
            id=f"{run.run_id}-{index}",
            severity="critical" if run.status == "FAILED" else "warning",
            title="Paper run error",
            message=str(error.get("message", "Unknown error.")),
            run_id=run.run_id,
            symbol=str(error.get("symbol")) if error.get("symbol") else None,
            created_at=run.completed_at or run.started_at,
        )
        for index, error in enumerate(run.errors)
    ]


def _decision_warnings(
    *,
    run: PaperRunModel,
    symbol: str,
    context: dict[str, Any],
) -> list[UiWarning]:
    warnings: list[UiWarning] = [
        UiWarning(
            id=f"{run.run_id}-{symbol}-error-{index}",
            severity="critical",
            title="Symbol pipeline failed",
            message=message,
            run_id=run.run_id,
            symbol=symbol,
            created_at=run.completed_at or run.started_at,
        )
        for index, message in enumerate(_symbol_errors(run, symbol))
    ]
    risk_review: RiskReviewModel | None = context["risk_review"]
    final_decision: FinalDecisionModel | None = context["final_decision"]
    orders: list[PaperOrderModel] = context["orders"]
    if risk_review is not None and risk_review.status in {
        "APPROVED_WITH_REDUCTION",
        "REJECTED",
        "BLOCKED",
    }:
        warnings.append(
            UiWarning(
                id=f"{risk_review.risk_check_id}-{risk_review.status.lower()}",
                severity="warning" if risk_review.status == "APPROVED_WITH_REDUCTION" else "critical",
                title=f"Risk review {risk_review.status.lower()}",
                message=risk_review.risk_committee_summary,
                run_id=run.run_id,
                symbol=symbol,
                created_at=risk_review.as_of,
            )
        )
    if final_decision is not None and final_decision.status in {"REJECTED", "BLOCKED"}:
        warnings.append(
            UiWarning(
                id=f"{final_decision.final_decision_id}-{final_decision.status.lower()}",
                severity="critical",
                title=f"Final decision {final_decision.status.lower()}",
                message=final_decision.reason,
                run_id=run.run_id,
                symbol=symbol,
                created_at=final_decision.as_of,
            )
        )
    if orders and orders[0].status == "REJECTED":
        warnings.append(
            UiWarning(
                id=f"{orders[0].order_id}-rejected",
                severity="critical",
                title="Paper order rejected",
                message=orders[0].rejection_reason or "PaperBroker rejected the order.",
                run_id=run.run_id,
                symbol=symbol,
                created_at=orders[0].submitted_at,
            )
        )
    return warnings


def _portfolio_metrics(
    account: dict[str, Any] | None,
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> list[UiMetric]:
    if account is None:
        return [
            UiMetric(label="Equity", value=None, unit="INR"),
            UiMetric(label="Cash", value=None, unit="INR"),
            UiMetric(label="Exposure", value=0, unit="INR"),
            UiMetric(label="Open positions", value=0),
        ]
    return [
        UiMetric(label="Equity", value=account.get("equity_inr"), unit="INR"),
        UiMetric(label="Cash", value=account.get("available_cash_inr"), unit="INR"),
        UiMetric(label="Exposure", value=account.get("gross_exposure_inr"), unit="INR"),
        UiMetric(label="Realized P&L", value=account.get("realized_pnl_inr"), unit="INR"),
        UiMetric(label="Unrealized P&L", value=account.get("unrealized_pnl_inr"), unit="INR"),
        UiMetric(label="Positions", value=len(positions)),
        UiMetric(label="Orders", value=len(orders)),
        UiMetric(label="Fills", value=len(fills)),
    ]


def _analyst_summary(reports: list[AnalystReportModel]) -> str:
    if not reports:
        return "No analyst reports are stored for this run and symbol."
    names = ", ".join(report.agent_name for report in reports)
    return f"{len(reports)} analyst report(s): {names}."


def _debate_summary(debate: DebateReportModel | None) -> str:
    if debate is None:
        return "No debate report is stored for this run and symbol."
    manager_summary = debate.manager_summary or {}
    summary = manager_summary.get("summary") if isinstance(manager_summary, dict) else None
    return str(summary or f"Consensus {debate.consensus_label} with score {debate.consensus_score}.")


def _debate_metrics(debate: DebateReportModel | None) -> dict[str, Any]:
    if debate is None:
        return {}
    return {
        "consensus_label": debate.consensus_label,
        "consensus_score": _decimal_to_number(debate.consensus_score),
        "confidence": _decimal_to_number(debate.confidence),
        "rounds_requested": debate.rounds_requested,
    }


def _proposal_summary(proposal: TraderProposalModel | None) -> str:
    if proposal is None:
        return "No trader proposal is stored for this run and symbol."
    return (
        f"{proposal.action} {proposal.evaluation_mode} proposal for "
        f"{proposal.lifecycle_trigger}; current {proposal.current_position_pct_nav}% NAV, "
        f"target {proposal.target_position_pct_nav}% NAV."
    )


def _proposal_metrics(proposal: TraderProposalModel | None) -> dict[str, Any]:
    if proposal is None:
        return {}
    payload = _payload(proposal)
    allocation_decision = _allocation_decision_from_payload(payload)
    return {
        "action": proposal.action,
        "portfolio_id": proposal.portfolio_id,
        "lifecycle_trigger": proposal.lifecycle_trigger,
        "evaluation_mode": proposal.evaluation_mode,
        "confidence": _decimal_to_number(proposal.confidence),
        "requested_position_pct_nav": _decimal_to_number(proposal.requested_position_pct_nav),
        "current_position_quantity": proposal.current_position_quantity,
        "current_position_pct_nav": _decimal_to_number(proposal.current_position_pct_nav),
        "target_position_pct_nav": _decimal_to_number(proposal.target_position_pct_nav),
        "order_type": proposal.order_type,
        "stop_loss_pct": _decimal_to_number(proposal.stop_loss_pct),
        "take_profit_pct": _decimal_to_number(proposal.take_profit_pct),
        "latest_price_inr": payload.get("latest_price_inr"),
        "stop_loss_price_inr": payload.get("stop_loss_price_inr"),
        "take_profit_price_inr": payload.get("take_profit_price_inr"),
        "trigger_threshold_price_inr": payload.get("trigger_threshold_price_inr"),
        "market_session_date": payload.get("market_session_date"),
        "quote_snapshot_id": payload.get("quote_snapshot_id"),
        "position_management_summary": proposal.position_management_summary,
        "allocation_status": allocation_decision.get("status")
        if allocation_decision
        else None,
        "sleeve_id": allocation_decision.get("sleeve_id") if allocation_decision else None,
        "strategy_name": allocation_decision.get("strategy_name")
        if allocation_decision
        else None,
        "binding_constraint": allocation_decision.get("binding_constraint")
        if allocation_decision
        else None,
        "estimated_risk_inr": allocation_decision.get("estimated_risk_inr")
        if allocation_decision
        else None,
    }


def _risk_summary(review: RiskReviewModel | None) -> str:
    if review is None:
        return "No risk review is stored for this run and symbol."
    return (
        f"Risk status {review.status}; requested {review.requested_position_pct_nav}% NAV, "
        f"approved {review.approved_position_pct_nav}% NAV."
    )


def _risk_metrics(review: RiskReviewModel | None) -> dict[str, Any]:
    if review is None:
        return {}
    allocation_decision = _allocation_decision_from_payload(_payload(review))
    return {
        "status": review.status,
        "requested_position_pct_nav": _decimal_to_number(review.requested_position_pct_nav),
        "approved_position_pct_nav": _decimal_to_number(review.approved_position_pct_nav),
        "hard_rule_count": len(review.hard_rule_results),
        "persona_review_count": len(review.persona_reviews),
        "can_send_to_broker": review.can_send_to_broker,
        "allocation_status": allocation_decision.get("status")
        if allocation_decision
        else None,
        "sleeve_id": allocation_decision.get("sleeve_id") if allocation_decision else None,
        "binding_constraint": allocation_decision.get("binding_constraint")
        if allocation_decision
        else None,
        "estimated_risk_inr": allocation_decision.get("estimated_risk_inr")
        if allocation_decision
        else None,
    }


def _final_summary(decision: FinalDecisionModel | None) -> str:
    if decision is None:
        return "No final decision is stored for this run and symbol."
    return (
        f"Final decision {decision.status}; action {decision.final_action}; "
        f"approved quantity {decision.approved_quantity}."
    )


def _final_metrics(decision: FinalDecisionModel | None) -> dict[str, Any]:
    if decision is None:
        return {}
    allocation_decision = _allocation_decision_from_payload(_payload(decision))
    return {
        "status": decision.status,
        "final_action": decision.final_action,
        "approved_quantity": decision.approved_quantity,
        "approved_position_pct_nav": _decimal_to_number(decision.approved_position_pct_nav),
        "can_send_to_broker": decision.can_send_to_broker,
        "allocation_status": allocation_decision.get("status")
        if allocation_decision
        else None,
        "sleeve_id": allocation_decision.get("sleeve_id") if allocation_decision else None,
        "binding_constraint": allocation_decision.get("binding_constraint")
        if allocation_decision
        else None,
    }


def _order_summary(order: PaperOrderModel) -> str:
    if order.status == "REJECTED":
        return order.rejection_reason or "Paper order was rejected."
    if order.status == "PENDING_NEXT_OPEN":
        return (
            f"Paper order queued for next-open settlement; {order.filled_quantity}/"
            f"{order.quantity} {order.side} filled."
        )
    return (
        f"Paper order {order.status}; {order.filled_quantity}/{order.quantity} "
        f"{order.side} filled."
    )


def _replay_timeline_stage(
    stage,
    *,
    order_artifacts: list[dict[str, object]],
) -> UiTimelineStage:
    status: StageStatus = "complete" if stage.artifact_count else "missing"
    summary = _replay_stage_summary(stage.name, stage.artifact_count)
    metrics: dict[str, Any] = {"artifact_count": stage.artifact_count}
    artifact_ids = _artifact_ids_for_replay_stage(stage.name, stage.artifacts)

    if stage.name == "paper_order" and stage.artifacts:
        order = stage.artifacts[0]
        order_status = str(order.get("status") or "")
        status = _replay_order_stage_status(order_status)
        summary = _replay_order_summary(order)
        metrics.update(
            {
                "status": order_status,
                "filled_quantity": order.get("filled_quantity"),
                "remaining_quantity": order.get("remaining_quantity"),
                "signal_trade_date": order.get("signal_trade_date"),
                "filled_trade_date": order.get("filled_trade_date"),
            }
        )
    elif stage.name == "paper_fills":
        pending_order = _first_pending_replay_order(order_artifacts)
        if stage.artifact_count == 0 and pending_order is not None:
            status = "running"
            summary = (
                "Paper order is queued for next-open settlement; no paper fills "
                "are expected until settlement."
            )
            order_id = pending_order.get("order_id")
            artifact_ids = [str(order_id)] if order_id else []
            metrics.update(
                {
                    "status": pending_order.get("status"),
                    "filled_quantity": pending_order.get("filled_quantity"),
                    "signal_trade_date": pending_order.get("signal_trade_date"),
                    "scheduled_fill_session": pending_order.get("scheduled_fill_session"),
                }
            )
        elif stage.artifact_count:
            metrics.update({"fill_count": stage.artifact_count})

    return UiTimelineStage(
        id=stage.name,
        label=_stage_label(stage.name),
        status=status,
        summary=summary,
        metrics=_json_safe(metrics),
        artifact_ids=artifact_ids,
        artifacts=_json_safe(stage.artifacts),
        raw=_json_safe(stage.artifacts),
    )


def _replay_order_stage_status(order_status: str) -> StageStatus:
    if order_status == "REJECTED":
        return "rejected"
    if order_status == "CANCELLED":
        return "blocked"
    if order_status in {"CREATED", "ACCEPTED", "PENDING_NEXT_OPEN", "PARTIALLY_FILLED"}:
        return "running"
    return "complete"


def _replay_order_summary(order: dict[str, object]) -> str:
    status = str(order.get("status") or "UNKNOWN")
    filled = order.get("filled_quantity")
    quantity = order.get("quantity")
    side = order.get("side")
    history = order.get("status_history")
    history_text = " -> ".join(str(item) for item in history) if isinstance(history, list) else ""
    signal_date = order.get("signal_trade_date")
    filled_date = order.get("filled_trade_date")
    date_text = []
    if signal_date:
        date_text.append(f"signal date {signal_date}")
    if filled_date:
        date_text.append(f"filled trade date {filled_date}")
    suffix_parts = []
    if history_text:
        suffix_parts.append(f"history {history_text}")
    if date_text:
        suffix_parts.append(", ".join(date_text))
    suffix = f" ({'; '.join(suffix_parts)})." if suffix_parts else "."
    return f"Paper order {status}; {filled}/{quantity} {side} filled{suffix}"


def _first_pending_replay_order(
    order_artifacts: list[dict[str, object]],
) -> dict[str, object] | None:
    for order in order_artifacts:
        if order.get("status") == "PENDING_NEXT_OPEN":
            return order
    return None


def _stage_label(stage_name: str) -> str:
    labels = {
        "inputs": "Inputs",
        "analyst_reports": "Analyst Reports",
        "company_events": "Company Events",
        "debate_report": "Debate",
        "trader_proposal": "Trader Proposal",
        "risk_review": "Risk Review",
        "final_decision": "Final Decision",
        "paper_order": "Paper Order",
        "paper_fills": "Paper Fills",
        "audit_log": "Audit Log",
    }
    return labels.get(stage_name, stage_name.replace("_", " ").title())


def _replay_stage_summary(stage_name: str, artifact_count: int) -> str:
    if artifact_count == 0:
        return f"No {_stage_label(stage_name).lower()} artifacts found in replay."
    return f"{artifact_count} {_stage_label(stage_name).lower()} artifact(s) found in replay."


def _artifact_ids_for_replay_stage(
    stage_name: str,
    artifacts: list[dict[str, object]],
) -> list[str]:
    keys_by_stage = {
        "analyst_reports": "report_id",
        "company_events": "event_id",
        "debate_report": "debate_id",
        "trader_proposal": "proposal_id",
        "risk_review": "risk_check_id",
        "final_decision": "final_decision_id",
        "paper_order": "order_id",
        "paper_fills": "fill_id",
        "audit_log": "id",
    }
    key = keys_by_stage.get(stage_name)
    if key is None:
        return []
    return [str(item[key]) for item in artifacts if key in item]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_to_number(value)
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


def _decimal_to_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)
