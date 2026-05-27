from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.models import (
    GraphEdgeEvidenceModel,
    GraphEdgeModel,
    GraphEdgeStatsModel,
    GraphNodeModel,
    GraphSignalContributionModel,
    GraphSignalModel,
)
from taurus_core.db.repositories import GraphRepository

router = APIRouter(prefix="/graph", tags=["graph"])

GraphEdgeStatusFilter = Literal["all", "active", "candidate", "rejected"]


class GraphNodeResponse(BaseModel):
    id: int
    node_key: str
    node_type: str
    display_name: str
    symbol: str | None
    isin: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GraphEdgeResponse(BaseModel):
    id: int
    edge_key: str
    source_node_id: int
    source_node_key: str
    source_display_name: str
    target_node_id: int
    target_node_key: str
    target_display_name: str
    edge_type: str
    direction: str
    expected_sign: str
    strength: Decimal | None
    evidence_type: str
    confidence: Decimal
    inferred: bool
    mechanism: str
    tradability_relevance: str
    status: str
    valid_from: date | None
    valid_to: date | None
    source_file: str
    source_row_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GraphEdgeEvidenceResponse(BaseModel):
    evidence_id: str
    edge_key: str
    claim_type: str
    claim_summary: str
    source_title: str
    source_type: str
    source_date: date | None
    source_url_or_reference: str
    page_or_section: str
    verbatim_excerpt_short: str
    confidence: Decimal
    source_file: str
    source_row_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GraphEdgeStatsResponse(BaseModel):
    id: int
    edge_key: str
    window: str
    as_of_date: date
    sample_size: int
    raw_correlation: Decimal | None
    residual_correlation: Decimal | None
    lead_lag_score: Decimal | None
    stability_score: Decimal | None
    p_value: Decimal | None
    insufficient_data_reason: str
    model_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GraphSignalContributionResponse(BaseModel):
    contribution_id: str
    signal_id: str
    edge_key: str | None
    node_key: str | None
    contribution_type: str
    direction: str
    score_contribution: Decimal
    weight: Decimal
    explanation: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GraphSignalResponse(BaseModel):
    signal_id: str
    symbol: str
    as_of: datetime
    score: Decimal
    confidence: Decimal
    horizon: str
    explanation: str
    source_agent: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    contributions: list[GraphSignalContributionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class GraphOverviewResponse(BaseModel):
    graph_enabled: bool
    graph_risk_enabled: bool
    graph_auto_promote_edges: bool
    neo4j_enabled: bool = False
    generated_at: datetime
    counts: dict[str, int]


class GraphCompanySubgraphResponse(BaseModel):
    symbol: str
    center_node: GraphNodeResponse
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    counts: dict[str, int]


class GraphEdgeDetailResponse(BaseModel):
    edge: GraphEdgeResponse
    source_node: GraphNodeResponse
    target_node: GraphNodeResponse
    evidence: list[GraphEdgeEvidenceResponse] = Field(default_factory=list)
    stats: list[GraphEdgeStatsResponse] = Field(default_factory=list)


class GraphEdgeListResponse(BaseModel):
    total_returned: int
    edges: list[GraphEdgeResponse]


class GraphSignalListResponse(BaseModel):
    total_returned: int
    signals: list[GraphSignalResponse]


class GraphBullishCandidateListResponse(BaseModel):
    total_returned: int
    candidates: list[GraphSignalResponse]


class GraphEdgeReviewRequest(BaseModel):
    reviewed_by: str = Field(default="api", max_length=64)
    note: str = Field(default="", max_length=1000)


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/overview", response_model=GraphOverviewResponse)
def graph_overview(request: Request, session: Session = Depends(get_db_session)) -> GraphOverviewResponse:
    settings = request.app.state.settings
    return GraphOverviewResponse(
        graph_enabled=settings.taurus_graph_enabled,
        graph_risk_enabled=settings.taurus_graph_risk_enabled,
        graph_auto_promote_edges=settings.taurus_graph_auto_promote_edges,
        generated_at=datetime.now(timezone.utc),
        counts=GraphRepository(session).overview_counts(),
    )


@router.get("/company/{symbol}", response_model=GraphCompanySubgraphResponse)
def company_subgraph(
    symbol: str,
    status: GraphEdgeStatusFilter = "all",
    limit: int = Query(default=250, ge=1, le=1000),
    session: Session = Depends(get_db_session),
) -> GraphCompanySubgraphResponse:
    graph_repo = GraphRepository(session)
    normalized_symbol = symbol.upper()
    center_node = graph_repo.get_node_by_key(f"company:{normalized_symbol}")
    if center_node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Graph company node for {normalized_symbol} not found",
        )

    edge_models = graph_repo.list_edges_for_node(
        node_key=center_node.node_key,
        status=_status_filter(status),
        limit=limit,
    )
    node_ids = {center_node.id}
    for edge in edge_models:
        node_ids.add(edge.source_node_id)
        node_ids.add(edge.target_node_id)
    node_models = graph_repo.list_nodes_by_ids(node_ids)
    node_lookup = {node.id: node for node in node_models}

    edges = [_edge_response(edge, node_lookup, graph_repo) for edge in edge_models]
    nodes = [_node_response(node) for node in node_models]
    return GraphCompanySubgraphResponse(
        symbol=normalized_symbol,
        center_node=_node_response(center_node),
        nodes=nodes,
        edges=edges,
        counts={
            "nodes": len(nodes),
            "edges": len(edges),
            "active_edges": sum(1 for edge in edges if edge.status == "active"),
            "candidate_edges": sum(1 for edge in edges if edge.status == "candidate"),
        },
    )


@router.get("/candidate-edges", response_model=GraphEdgeListResponse)
def candidate_edges(
    edge_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_db_session),
) -> GraphEdgeListResponse:
    graph_repo = GraphRepository(session)
    edge_models = graph_repo.list_edges(
        edge_type=edge_type,
        status="candidate",
        limit=limit,
    )
    node_lookup = _node_lookup_for_edges(graph_repo, edge_models)
    edges = [_edge_response(edge, node_lookup, graph_repo) for edge in edge_models]
    return GraphEdgeListResponse(total_returned=len(edges), edges=edges)


@router.get("/signals", response_model=GraphSignalListResponse)
def graph_signals(
    symbol: str | None = None,
    source_agent: str | None = None,
    include_contributions: bool = True,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_db_session),
) -> GraphSignalListResponse:
    graph_repo = GraphRepository(session)
    signals = graph_repo.list_signals(
        symbol=symbol,
        source_agent=source_agent,
        limit=limit,
    )
    responses = [
        _signal_response(graph_repo, signal, include_contributions=include_contributions)
        for signal in signals
    ]
    return GraphSignalListResponse(total_returned=len(responses), signals=responses)


@router.get("/bullish-candidates", response_model=GraphBullishCandidateListResponse)
def bullish_candidates(
    symbol: str | None = None,
    min_score: Decimal = Query(default=Decimal("0.01")),
    include_contributions: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> GraphBullishCandidateListResponse:
    graph_repo = GraphRepository(session)
    signals = graph_repo.list_bullish_signals(
        symbol=symbol,
        min_score=min_score,
        limit=limit,
    )
    candidates = [
        _signal_response(graph_repo, signal, include_contributions=include_contributions)
        for signal in signals
    ]
    return GraphBullishCandidateListResponse(
        total_returned=len(candidates),
        candidates=candidates,
    )


@router.get("/edges/{edge_key}", response_model=GraphEdgeDetailResponse)
def edge_detail(
    edge_key: str,
    session: Session = Depends(get_db_session),
) -> GraphEdgeDetailResponse:
    graph_repo = GraphRepository(session)
    edge = _get_edge_or_404(graph_repo, edge_key)
    return _edge_detail_response(graph_repo, edge)


@router.get("/edges/{edge_key}/evidence", response_model=list[GraphEdgeEvidenceResponse])
def edge_evidence(
    edge_key: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[GraphEdgeEvidenceResponse]:
    graph_repo = GraphRepository(session)
    edge = _get_edge_or_404(graph_repo, edge_key)
    evidence = graph_repo.list_edge_evidence(edge_key=edge.edge_key, limit=limit)
    return [_evidence_response(item, edge) for item in evidence]


@router.post("/edges/{edge_key}/promote", response_model=GraphEdgeDetailResponse)
def promote_edge(
    request: Request,
    edge_key: str,
    review: GraphEdgeReviewRequest | None = None,
    session: Session = Depends(get_db_session),
) -> GraphEdgeDetailResponse:
    _require_graph_mutations_enabled(request)
    review = review or GraphEdgeReviewRequest()
    return _review_edge(
        session=session,
        edge_key=edge_key,
        status="active",
        reviewed_by=review.reviewed_by,
        note=review.note,
    )


@router.post("/edges/{edge_key}/reject", response_model=GraphEdgeDetailResponse)
def reject_edge(
    request: Request,
    edge_key: str,
    review: GraphEdgeReviewRequest | None = None,
    session: Session = Depends(get_db_session),
) -> GraphEdgeDetailResponse:
    _require_graph_mutations_enabled(request)
    review = review or GraphEdgeReviewRequest()
    return _review_edge(
        session=session,
        edge_key=edge_key,
        status="rejected",
        reviewed_by=review.reviewed_by,
        note=review.note,
    )


def _review_edge(
    *,
    session: Session,
    edge_key: str,
    status: str,
    reviewed_by: str,
    note: str,
) -> GraphEdgeDetailResponse:
    graph_repo = GraphRepository(session)
    try:
        edge = graph_repo.update_edge_status(
            edge_key=edge_key,
            status=status,
            reviewed_by=reviewed_by,
            review_note=note,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if message.startswith("Unknown graph edge_key") else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    session.commit()
    return _edge_detail_response(graph_repo, edge)


def _status_filter(status: GraphEdgeStatusFilter) -> str | None:
    return None if status == "all" else status


def _require_graph_mutations_enabled(request: Request | None) -> None:
    if request is None:
        raise HTTPException(status_code=500, detail="Request context unavailable")
    settings = request.app.state.settings
    if not settings.taurus_graph_enabled:
        raise HTTPException(
            status_code=403,
            detail="Graph review endpoints require TAURUS_GRAPH_ENABLED=true",
        )


def _get_edge_or_404(graph_repo: GraphRepository, edge_key: str) -> GraphEdgeModel:
    edge = graph_repo.get_edge_by_key(edge_key)
    if edge is None:
        raise HTTPException(status_code=404, detail=f"Graph edge {edge_key} not found")
    return edge


def _edge_detail_response(
    graph_repo: GraphRepository,
    edge: GraphEdgeModel,
) -> GraphEdgeDetailResponse:
    source_node = _get_node_or_error(graph_repo, edge.source_node_id, edge.edge_key)
    target_node = _get_node_or_error(graph_repo, edge.target_node_id, edge.edge_key)
    node_lookup = {
        source_node.id: source_node,
        target_node.id: target_node,
    }
    evidence = graph_repo.list_edge_evidence(edge_key=edge.edge_key)
    stats = graph_repo.list_edge_stats(edge_key=edge.edge_key)
    return GraphEdgeDetailResponse(
        edge=_edge_response(edge, node_lookup, graph_repo),
        source_node=_node_response(source_node),
        target_node=_node_response(target_node),
        evidence=[_evidence_response(item, edge) for item in evidence],
        stats=[_stats_response(item, edge) for item in stats],
    )


def _node_lookup_for_edges(
    graph_repo: GraphRepository,
    edges: list[GraphEdgeModel],
) -> dict[int, GraphNodeModel]:
    node_ids: set[int] = set()
    for edge in edges:
        node_ids.add(edge.source_node_id)
        node_ids.add(edge.target_node_id)
    return {node.id: node for node in graph_repo.list_nodes_by_ids(node_ids)}


def _edge_response(
    edge: GraphEdgeModel,
    node_lookup: dict[int, GraphNodeModel],
    graph_repo: GraphRepository,
) -> GraphEdgeResponse:
    source_node = node_lookup.get(edge.source_node_id) or _get_node_or_error(
        graph_repo,
        edge.source_node_id,
        edge.edge_key,
    )
    target_node = node_lookup.get(edge.target_node_id) or _get_node_or_error(
        graph_repo,
        edge.target_node_id,
        edge.edge_key,
    )
    return GraphEdgeResponse(
        id=edge.id,
        edge_key=edge.edge_key,
        source_node_id=edge.source_node_id,
        source_node_key=source_node.node_key,
        source_display_name=source_node.display_name,
        target_node_id=edge.target_node_id,
        target_node_key=target_node.node_key,
        target_display_name=target_node.display_name,
        edge_type=edge.edge_type,
        direction=edge.direction,
        expected_sign=edge.expected_sign,
        strength=edge.strength,
        evidence_type=edge.evidence_type,
        confidence=edge.confidence,
        inferred=edge.inferred,
        mechanism=edge.mechanism,
        tradability_relevance=edge.tradability_relevance,
        status=edge.status,
        valid_from=edge.valid_from,
        valid_to=edge.valid_to,
        source_file=edge.source_file,
        source_row_hash=edge.source_row_hash,
        metadata=edge.edge_metadata or {},
        created_at=edge.created_at,
        updated_at=edge.updated_at,
    )


def _node_response(node: GraphNodeModel) -> GraphNodeResponse:
    return GraphNodeResponse(
        id=node.id,
        node_key=node.node_key,
        node_type=node.node_type,
        display_name=node.display_name,
        symbol=node.symbol,
        isin=node.isin,
        metadata=node.node_metadata or {},
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def _evidence_response(
    evidence: GraphEdgeEvidenceModel,
    edge: GraphEdgeModel,
) -> GraphEdgeEvidenceResponse:
    return GraphEdgeEvidenceResponse(
        evidence_id=evidence.evidence_id,
        edge_key=edge.edge_key,
        claim_type=evidence.claim_type,
        claim_summary=evidence.claim_summary,
        source_title=evidence.source_title,
        source_type=evidence.source_type,
        source_date=evidence.source_date,
        source_url_or_reference=evidence.source_url_or_reference,
        page_or_section=evidence.page_or_section,
        verbatim_excerpt_short=evidence.verbatim_excerpt_short,
        confidence=evidence.confidence,
        source_file=evidence.source_file,
        source_row_hash=evidence.source_row_hash,
        metadata=evidence.evidence_metadata or {},
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


def _stats_response(
    stats: GraphEdgeStatsModel,
    edge: GraphEdgeModel,
) -> GraphEdgeStatsResponse:
    return GraphEdgeStatsResponse(
        id=stats.id,
        edge_key=edge.edge_key,
        window=stats.stat_window,
        as_of_date=stats.as_of_date,
        sample_size=stats.sample_size,
        raw_correlation=stats.raw_correlation,
        residual_correlation=stats.residual_correlation,
        lead_lag_score=stats.lead_lag_score,
        stability_score=stats.stability_score,
        p_value=stats.p_value,
        insufficient_data_reason=stats.insufficient_data_reason,
        model_version=stats.model_version,
        metadata=stats.stats_metadata or {},
        created_at=stats.created_at,
        updated_at=stats.updated_at,
    )


def _signal_response(
    graph_repo: GraphRepository,
    signal: GraphSignalModel,
    *,
    include_contributions: bool,
) -> GraphSignalResponse:
    contributions = (
        graph_repo.list_signal_contributions(signal_id=signal.signal_id)
        if include_contributions
        else []
    )
    return GraphSignalResponse(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        as_of=signal.as_of,
        score=signal.score,
        confidence=signal.confidence,
        horizon=signal.horizon,
        explanation=signal.explanation,
        source_agent=signal.source_agent,
        metadata=signal.signal_metadata or {},
        contributions=[
            _contribution_response(graph_repo, contribution)
            for contribution in contributions
        ],
        created_at=signal.created_at,
        updated_at=signal.updated_at,
    )


def _contribution_response(
    graph_repo: GraphRepository,
    contribution: GraphSignalContributionModel,
) -> GraphSignalContributionResponse:
    edge = graph_repo.get_edge_by_id(contribution.edge_id) if contribution.edge_id else None
    node = graph_repo.get_node_by_id(contribution.node_id) if contribution.node_id else None
    return GraphSignalContributionResponse(
        contribution_id=contribution.contribution_id,
        signal_id=contribution.signal_id,
        edge_key=edge.edge_key if edge is not None else None,
        node_key=node.node_key if node is not None else None,
        contribution_type=contribution.contribution_type,
        direction=contribution.direction,
        score_contribution=contribution.score_contribution,
        weight=contribution.weight,
        explanation=contribution.explanation,
        metadata=contribution.contribution_metadata or {},
        created_at=contribution.created_at,
        updated_at=contribution.updated_at,
    )


def _get_node_or_error(
    graph_repo: GraphRepository,
    node_id: int,
    edge_key: str,
) -> GraphNodeModel:
    node = graph_repo.get_node_by_id(node_id)
    if node is None:
        raise HTTPException(
            status_code=500,
            detail=f"Graph edge {edge_key} references missing node {node_id}",
        )
    return node
