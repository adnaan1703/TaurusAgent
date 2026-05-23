from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    CompanyEventModel,
    DebateReportModel,
    FinalDecisionModel,
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
    InstrumentRepository,
    IntelligenceRepository,
    PaperRunRepository,
    ResearchRepository,
    RiskRepository,
)
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


class UiSafetyStatus(BaseModel):
    taurus_mode: str
    broker_provider: str
    live_trading_enabled: bool
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
    final_status_counts: dict[str, int] = Field(default_factory=dict)
    order_status_counts: dict[str, int] = Field(default_factory=dict)


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
    latest_account: dict[str, Any] | None
    latest_run: UiRunSummary | None
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
    latest_risk_reviews: list[dict[str, Any]]
    hard_rule_results: list[dict[str, Any]]
    persona_reviews: list[dict[str, Any]]
    latest_final_decisions: list[dict[str, Any]]
    status_counts: dict[str, int]


class UiPortfolioResponse(BaseModel):
    safety: UiSafetyStatus
    latest_account: dict[str, Any] | None
    positions: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    summary_metrics: list[UiMetric]


class UiHistoryResponse(BaseModel):
    runs: list[UiRunSummary]
    status_counts: dict[str, int]
    filters_metadata: dict[str, Any]


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
    risk_repo = RiskRepository(session)
    execution_repo = ExecutionRepository(session)

    run_rows = run_repo.list(limit=limit)
    recent_runs = [_run_summary(row, risk_repo, execution_repo) for row in run_rows]
    latest_run = recent_runs[0] if recent_runs else None
    latest_account = execution_repo.latest_account()
    latest_account_payload = _payload(latest_account) if latest_account is not None else None
    latest_final = risk_repo.list_final_decisions(limit=1)
    latest_orders = execution_repo.list_orders(limit=1)
    position_run_id = latest_account.run_id if latest_account is not None else None
    positions = [
        _payload(position)
        for position in execution_repo.list_positions(run_id=position_run_id)
    ]

    warnings = _overview_warnings(
        run_rows=run_rows,
        latest_account=latest_account_payload,
        latest_final=latest_final[0] if latest_final else None,
    )
    return UiOverviewResponse(
        safety=_safety(settings),
        latest_account=latest_account_payload,
        latest_run=latest_run,
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
    run_summary = _run_summary(run, risk_repo, execution_repo)
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
    return UiDecisionTrailResponse(
        run=_run_summary(run, RiskRepository(session), ExecutionRepository(session)),
        symbol=normalized_symbol,
        company_name=instrument.name if instrument is not None else None,
        decision_id=final_decision.decision_id if final_decision is not None else None,
        final_status=final_decision.status if final_decision is not None else None,
        final_action=final_decision.final_action if final_decision is not None else None,
        can_send_to_broker=final_decision.can_send_to_broker
        if final_decision is not None
        else None,
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

    stages = [
        UiTimelineStage(
            id=stage.name,
            label=_stage_label(stage.name),
            status="complete" if stage.artifact_count else "missing",
            summary=_replay_stage_summary(stage.name, stage.artifact_count),
            metrics={"artifact_count": stage.artifact_count},
            artifact_ids=_artifact_ids_for_replay_stage(stage.name, stage.artifacts),
            artifacts=_json_safe(stage.artifacts),
            raw=_json_safe(stage.artifacts),
        )
        for stage in replay.stages
    ]
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
        latest_risk_reviews=[_payload(review) for review in reviews],
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
    account = execution_repo.latest_account()
    account_payload = _payload(account) if account is not None else None
    run_id = account.run_id if account is not None else None
    positions = [_payload(row) for row in execution_repo.list_positions(run_id=run_id)]
    orders = [_payload(row) for row in execution_repo.list_orders(run_id=run_id, limit=limit)]
    fills = [_payload(row) for row in execution_repo.list_fills(run_id=run_id, limit=limit)]
    return UiPortfolioResponse(
        safety=_safety(settings),
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
    runs = [_run_summary(row, risk_repo, execution_repo) for row in rows]
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


def _safety(settings: Settings) -> UiSafetyStatus:
    return UiSafetyStatus(
        taurus_mode=settings.taurus_mode,
        broker_provider=settings.broker_provider,
        live_trading_enabled=settings.live_trading_enabled,
        alert_provider=settings.taurus_alert_provider,
    )


def _require_run(session: Session, run_id: str) -> PaperRunModel:
    run = PaperRunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Paper run not found.")
    return run


def _run_summary(
    run: PaperRunModel,
    risk_repo: RiskRepository,
    execution_repo: ExecutionRepository,
) -> UiRunSummary:
    final_decisions = risk_repo.list_final_decisions(run_id=run.run_id, limit=None)
    orders = execution_repo.list_orders(run_id=run.run_id, limit=None)
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
        final_status_counts=dict(Counter(row.status for row in final_decisions)),
        order_status_counts=dict(Counter(row.status for row in orders)),
    )


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
    if order.status in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED"}:
        return "running"
    return "complete"


def _payload(row: Any) -> dict[str, Any]:
    return _json_safe(dict(row.payload or {}))


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


def _duration_seconds(
    started_at: datetime,
    completed_at: datetime | None,
) -> float | None:
    if completed_at is None:
        return None
    return max((completed_at - started_at).total_seconds(), 0.0)


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
        f"{proposal.action} proposal for {proposal.requested_position_pct_nav}% NAV "
        f"with {proposal.confidence} confidence."
    )


def _proposal_metrics(proposal: TraderProposalModel | None) -> dict[str, Any]:
    if proposal is None:
        return {}
    return {
        "action": proposal.action,
        "confidence": _decimal_to_number(proposal.confidence),
        "requested_position_pct_nav": _decimal_to_number(proposal.requested_position_pct_nav),
        "order_type": proposal.order_type,
        "stop_loss_pct": _decimal_to_number(proposal.stop_loss_pct),
        "take_profit_pct": _decimal_to_number(proposal.take_profit_pct),
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
    return {
        "status": review.status,
        "requested_position_pct_nav": _decimal_to_number(review.requested_position_pct_nav),
        "approved_position_pct_nav": _decimal_to_number(review.approved_position_pct_nav),
        "hard_rule_count": len(review.hard_rule_results),
        "persona_review_count": len(review.persona_reviews),
        "can_send_to_broker": review.can_send_to_broker,
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
    return {
        "status": decision.status,
        "final_action": decision.final_action,
        "approved_quantity": decision.approved_quantity,
        "approved_position_pct_nav": _decimal_to_number(decision.approved_position_pct_nav),
        "can_send_to_broker": decision.can_send_to_broker,
    }


def _order_summary(order: PaperOrderModel) -> str:
    if order.status == "REJECTED":
        return order.rejection_reason or "Paper order was rejected."
    return (
        f"Paper order {order.status}; {order.filled_quantity}/{order.quantity} "
        f"{order.side} filled."
    )


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
