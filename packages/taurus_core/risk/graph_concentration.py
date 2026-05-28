from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.config import Settings
from taurus_core.db.models import GraphEdgeModel, GraphEdgeStatsModel, GraphNodeModel
from taurus_core.db.repositories import GraphRepository
from taurus_core.risk.schemas import HardRuleResult, RiskRuleStatus

SCORE_QUANT = Decimal("0.0001")
ZERO = Decimal("0")
GRAPH_RISK_MODEL_VERSION = "graph_risk_v1"


@dataclass(frozen=True, slots=True)
class _GraphExposurePolicy:
    category: str
    rule: str
    label: str
    limit_pct_nav: Decimal


@dataclass(frozen=True, slots=True)
class _ExposureValue:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class _ExposureGroup:
    key: str
    label: str
    matched_symbols: tuple[str, ...]
    source_detail: str


@dataclass(frozen=True, slots=True)
class _ExposureDecision:
    group: _ExposureGroup
    status: RiskRuleStatus
    existing_exposure_pct_nav: Decimal
    projected_exposure_pct_nav: Decimal
    warning_threshold_pct_nav: Decimal
    approved_position_pct_nav: Decimal


def evaluate_graph_concentration(
    session: Session,
    *,
    settings: Settings,
    symbol: str,
    approved_position_pct_nav: Decimal,
    current_position_exposures_pct_nav: Mapping[str, Decimal | int | float | str] | None,
) -> tuple[Decimal, list[HardRuleResult]]:
    """Evaluate optional graph-aware concentration checks for a proposed long entry."""

    if not settings.taurus_graph_risk_enabled:
        return approved_position_pct_nav.quantize(SCORE_QUANT), []

    normalized_symbol = symbol.upper()
    approved_position = _risk_decimal(approved_position_pct_nav)
    exposures = _normalize_exposures(current_position_exposures_pct_nav or {})
    graph_repo = GraphRepository(session)
    center_node = _company_node(graph_repo, normalized_symbol)
    value_cache: dict[tuple[str, str], tuple[_ExposureValue, ...]] = {}
    results: list[HardRuleResult] = []

    for policy in _policies(settings):
        if policy.category == "correlated_cluster":
            groups = _correlated_cluster_groups(
                graph_repo,
                center_node=center_node,
                proposed_symbol=normalized_symbol,
                exposures=exposures,
                settings=settings,
            )
        else:
            groups = _static_exposure_groups(
                graph_repo,
                center_node=center_node,
                proposed_symbol=normalized_symbol,
                category=policy.category,
                exposures=exposures,
                value_cache=value_cache,
            )

        if not groups:
            metadata_detail = (
                "statistically validated correlated exposure"
                if policy.category == "correlated_cluster"
                else "exposure metadata"
            )
            results.append(
                HardRuleResult(
                    rule=policy.rule,
                    status="passed",
                    details=(
                        f"No graph {policy.label} {metadata_detail} was "
                        f"found for {normalized_symbol}; {GRAPH_RISK_MODEL_VERSION} passed."
                    ),
                )
            )
            continue

        decision = _decide_exposure(
            policy=policy,
            groups=groups,
            exposures=exposures,
            proposed_position_pct_nav=approved_position,
            warning_fraction=settings.taurus_graph_concentration_warning_fraction,
        )
        approved_position = decision.approved_position_pct_nav
        results.append(_hard_rule_result(policy, decision))

    return approved_position.quantize(SCORE_QUANT), results


def _policies(settings: Settings) -> tuple[_GraphExposurePolicy, ...]:
    return (
        _GraphExposurePolicy(
            category="basic_industry",
            rule="graph_basic_industry_concentration",
            label="basic industry",
            limit_pct_nav=_risk_decimal(settings.taurus_graph_max_basic_industry_exposure_pct),
        ),
        _GraphExposurePolicy(
            category="product_group",
            rule="graph_product_group_concentration",
            label="product group",
            limit_pct_nav=_risk_decimal(settings.taurus_graph_max_product_group_exposure_pct),
        ),
        _GraphExposurePolicy(
            category="customer_industry",
            rule="graph_customer_industry_concentration",
            label="customer industry",
            limit_pct_nav=_risk_decimal(settings.taurus_graph_max_customer_industry_exposure_pct),
        ),
        _GraphExposurePolicy(
            category="dependency",
            rule="graph_dependency_concentration",
            label="raw material/dependency",
            limit_pct_nav=_risk_decimal(settings.taurus_graph_max_dependency_exposure_pct),
        ),
        _GraphExposurePolicy(
            category="risk_category",
            rule="graph_risk_category_concentration",
            label="risk category",
            limit_pct_nav=_risk_decimal(settings.taurus_graph_max_risk_category_exposure_pct),
        ),
        _GraphExposurePolicy(
            category="correlated_cluster",
            rule="graph_correlated_cluster_concentration",
            label="correlated graph cluster",
            limit_pct_nav=_risk_decimal(settings.taurus_graph_max_correlated_cluster_exposure_pct),
        ),
    )


def _static_exposure_groups(
    graph_repo: GraphRepository,
    *,
    center_node: GraphNodeModel | None,
    proposed_symbol: str,
    category: str,
    exposures: Mapping[str, Decimal],
    value_cache: dict[tuple[str, str], tuple[_ExposureValue, ...]],
) -> tuple[_ExposureGroup, ...]:
    proposed_values = _values_for_symbol(
        graph_repo,
        symbol=proposed_symbol,
        category=category,
        value_cache=value_cache,
        center_node=center_node,
    )
    if not proposed_values:
        return ()

    groups: list[_ExposureGroup] = []
    for value in proposed_values:
        matched_symbols = tuple(
            sorted(
                exposure_symbol
                for exposure_symbol in exposures
                if value.key
                in {
                    item.key
                    for item in _values_for_symbol(
                        graph_repo,
                        symbol=exposure_symbol,
                        category=category,
                        value_cache=value_cache,
                    )
                }
            )
        )
        groups.append(
            _ExposureGroup(
                key=value.key,
                label=value.label,
                matched_symbols=matched_symbols,
                source_detail=f"graph {category} node {value.key}",
            )
        )
    return tuple(groups)


def _values_for_symbol(
    graph_repo: GraphRepository,
    *,
    symbol: str,
    category: str,
    value_cache: dict[tuple[str, str], tuple[_ExposureValue, ...]],
    center_node: GraphNodeModel | None = None,
) -> tuple[_ExposureValue, ...]:
    cache_key = (symbol.upper(), category)
    cached = value_cache.get(cache_key)
    if cached is not None:
        return cached

    node = center_node if center_node is not None and center_node.symbol == symbol.upper() else None
    node = node or _company_node(graph_repo, symbol)
    if node is None:
        value_cache[cache_key] = ()
        return ()

    values: list[_ExposureValue] = []
    for edge in graph_repo.list_edges_for_node(node_key=node.node_key, status="active", limit=None):
        source_node = graph_repo.get_node_by_id(edge.source_node_id)
        target_node = graph_repo.get_node_by_id(edge.target_node_id)
        related_node = target_node if edge.source_node_id == node.id else source_node
        if related_node is None:
            continue
        value = _value_from_edge(
            category=category,
            center_node=node,
            related_node=related_node,
            edge=edge,
        )
        if value is not None:
            values.append(value)

    value_cache[cache_key] = _dedupe_values(values)
    return value_cache[cache_key]


def _value_from_edge(
    *,
    category: str,
    center_node: GraphNodeModel,
    related_node: GraphNodeModel,
    edge: GraphEdgeModel,
) -> _ExposureValue | None:
    if category == "basic_industry":
        if edge.source_node_id == center_node.id and related_node.node_type == "basic_industry":
            return _ExposureValue(key=related_node.node_key, label=related_node.display_name)
        return None

    if category == "product_group":
        if edge.source_node_id == center_node.id and related_node.node_type == "product_group":
            return _ExposureValue(key=related_node.node_key, label=related_node.display_name)
        return None

    if category in {"customer_industry", "dependency"}:
        if related_node.node_type != "dependency":
            return None
        dependency_type = str(
            related_node.node_metadata.get("dependency_type") or edge.edge_type
        ).strip().lower()
        is_customer = dependency_type == "customer_industry" or edge.edge_type == "customer_industry"
        if category == "customer_industry" and is_customer:
            return _ExposureValue(key=related_node.node_key, label=related_node.display_name)
        if category == "dependency" and not is_customer:
            return _ExposureValue(key=related_node.node_key, label=related_node.display_name)
        return None

    if category == "risk_category":
        if related_node.node_type != "risk" and edge.edge_type != "exposed_to_risk":
            return None
        edge_metadata = edge.edge_metadata or {}
        risk_category = str(
            related_node.node_metadata.get("risk_category")
            or edge_metadata.get("risk_category")
            or related_node.display_name
        ).strip()
        if not risk_category:
            return None
        return _ExposureValue(
            key=f"risk_category:{_normalize_key_part(risk_category)}",
            label=risk_category,
        )

    return None


def _correlated_cluster_groups(
    graph_repo: GraphRepository,
    *,
    center_node: GraphNodeModel | None,
    proposed_symbol: str,
    exposures: Mapping[str, Decimal],
    settings: Settings,
) -> tuple[_ExposureGroup, ...]:
    if center_node is None:
        return ()

    related_edges: list[tuple[str, GraphEdgeModel, GraphEdgeStatsModel, Decimal]] = []
    for edge in graph_repo.list_edges_for_node(node_key=center_node.node_key, limit=250):
        if edge.status not in {"active", "candidate"}:
            continue
        related_node_id = (
            edge.target_node_id
            if edge.source_node_id == center_node.id
            else edge.source_node_id
        )
        related_node = graph_repo.get_node_by_id(related_node_id)
        if related_node is None or related_node.node_type != "company" or not related_node.symbol:
            continue
        stat = _latest_correlated_stat(graph_repo, edge=edge, settings=settings)
        if stat is None:
            continue
        related_edges.append(
            (
                related_node.symbol.upper(),
                edge,
                stat,
                _validation_score(stat),
            )
        )

    if not related_edges:
        return ()

    related_symbols = tuple(sorted({item[0] for item in related_edges}))
    matched_symbols = tuple(symbol for symbol in related_symbols if symbol in exposures)
    top_symbol, top_edge, top_stat, _ = sorted(
        related_edges,
        key=lambda item: (item[3], item[1].edge_key),
        reverse=True,
    )[0]
    label = f"{proposed_symbol} correlated cluster: {', '.join(related_symbols[:8])}"
    if len(related_symbols) > 8:
        label = f"{label}, +{len(related_symbols) - 8} more"
    source_detail = (
        f"edge {top_edge.edge_key} to {top_symbol} with {top_stat.stat_window} stats "
        f"as of {top_stat.as_of_date.isoformat()}"
    )
    return (
        _ExposureGroup(
            key=f"correlated_cluster:{proposed_symbol}",
            label=label,
            matched_symbols=matched_symbols,
            source_detail=source_detail,
        ),
    )


def _latest_correlated_stat(
    graph_repo: GraphRepository,
    *,
    edge: GraphEdgeModel,
    settings: Settings,
) -> GraphEdgeStatsModel | None:
    stats = [
        stat
        for stat in graph_repo.list_edge_stats(edge_key=edge.edge_key, limit=None)
        if not stat.insufficient_data_reason and _stat_is_correlated(stat, settings)
    ]
    if not stats:
        return None
    return sorted(
        stats,
        key=lambda item: (item.as_of_date, item.sample_size, item.stat_window),
        reverse=True,
    )[0]


def _stat_is_correlated(stat: GraphEdgeStatsModel, settings: Settings) -> bool:
    correlation_values = [
        abs(value)
        for value in (stat.residual_correlation, stat.raw_correlation)
        if value is not None
    ]
    correlation_passes = bool(
        correlation_values and max(correlation_values) >= settings.taurus_graph_min_residual_corr
    )
    lead_lag_passes = (
        stat.lead_lag_score is not None
        and abs(stat.lead_lag_score) >= settings.taurus_graph_min_lead_lag_score
    )
    return correlation_passes or lead_lag_passes


def _validation_score(stat: GraphEdgeStatsModel) -> Decimal:
    values = [
        abs(value)
        for value in (stat.residual_correlation, stat.raw_correlation, stat.lead_lag_score)
        if value is not None
    ]
    return max(values) if values else ZERO


def _decide_exposure(
    *,
    policy: _GraphExposurePolicy,
    groups: tuple[_ExposureGroup, ...],
    exposures: Mapping[str, Decimal],
    proposed_position_pct_nav: Decimal,
    warning_fraction: Decimal,
) -> _ExposureDecision:
    decisions = [
        _decision_for_group(
            policy=policy,
            group=group,
            exposures=exposures,
            proposed_position_pct_nav=proposed_position_pct_nav,
            warning_fraction=warning_fraction,
        )
        for group in groups
    ]
    return sorted(
        decisions,
        key=lambda item: (
            _status_severity(item.status),
            item.projected_exposure_pct_nav,
            item.existing_exposure_pct_nav,
            item.group.label,
        ),
        reverse=True,
    )[0]


def _decision_for_group(
    *,
    policy: _GraphExposurePolicy,
    group: _ExposureGroup,
    exposures: Mapping[str, Decimal],
    proposed_position_pct_nav: Decimal,
    warning_fraction: Decimal,
) -> _ExposureDecision:
    existing = _risk_decimal(sum((exposures[symbol] for symbol in group.matched_symbols), ZERO))
    projected = _risk_decimal(existing + proposed_position_pct_nav)
    limit = policy.limit_pct_nav
    warning_threshold = _risk_decimal(limit * warning_fraction)

    if proposed_position_pct_nav <= ZERO:
        status: RiskRuleStatus = "passed"
        approved = proposed_position_pct_nav
    elif existing >= limit:
        status = "rejected"
        approved = ZERO
    elif projected > limit:
        remaining_capacity = _risk_decimal(limit - existing)
        if remaining_capacity <= ZERO:
            status = "rejected"
            approved = ZERO
        else:
            status = "reduced"
            approved = min(proposed_position_pct_nav, remaining_capacity)
    elif projected >= warning_threshold:
        status = "warn"
        approved = proposed_position_pct_nav
    else:
        status = "passed"
        approved = proposed_position_pct_nav

    return _ExposureDecision(
        group=group,
        status=status,
        existing_exposure_pct_nav=existing,
        projected_exposure_pct_nav=projected,
        warning_threshold_pct_nav=warning_threshold,
        approved_position_pct_nav=_risk_decimal(approved),
    )


def _hard_rule_result(
    policy: _GraphExposurePolicy,
    decision: _ExposureDecision,
) -> HardRuleResult:
    exposure_name = f"Graph {policy.label} exposure '{decision.group.label}'"
    matching_positions = _matched_symbols_text(decision.group.matched_symbols)
    if decision.status == "rejected":
        details = (
            f"{exposure_name} is already {decision.existing_exposure_pct_nav}% NAV, "
            f"at or above limit {policy.limit_pct_nav}%; rejecting new BUY exposure. "
            f"Matching positions: {matching_positions}. Source: {decision.group.source_detail}."
        )
    elif decision.status == "reduced":
        details = (
            f"{exposure_name} would rise from {decision.existing_exposure_pct_nav}% "
            f"to {decision.projected_exposure_pct_nav}% NAV, above limit "
            f"{policy.limit_pct_nav}%; reduced approved position to "
            f"{decision.approved_position_pct_nav}% NAV. Matching positions: "
            f"{matching_positions}. Source: {decision.group.source_detail}."
        )
    elif decision.status == "warn":
        details = (
            f"{exposure_name} would rise from {decision.existing_exposure_pct_nav}% "
            f"to {decision.projected_exposure_pct_nav}% NAV, near limit "
            f"{policy.limit_pct_nav}% and warning threshold "
            f"{decision.warning_threshold_pct_nav}%. Matching positions: "
            f"{matching_positions}. Source: {decision.group.source_detail}."
        )
    else:
        details = (
            f"{exposure_name} would be {decision.projected_exposure_pct_nav}% NAV, "
            f"within limit {policy.limit_pct_nav}%. Matching positions: "
            f"{matching_positions}. Source: {decision.group.source_detail}."
        )

    return HardRuleResult(
        rule=policy.rule,
        status=decision.status,
        details=details,
    )


def _company_node(graph_repo: GraphRepository, symbol: str) -> GraphNodeModel | None:
    normalized_symbol = symbol.upper()
    node = graph_repo.get_node_by_key(f"company:{normalized_symbol}")
    if node is not None:
        return node
    nodes = graph_repo.list_nodes(node_type="company", symbol=normalized_symbol, limit=1)
    return nodes[0] if nodes else None


def _dedupe_values(values: list[_ExposureValue]) -> tuple[_ExposureValue, ...]:
    values_by_key: dict[str, _ExposureValue] = {}
    for value in values:
        if value.key not in values_by_key:
            values_by_key[value.key] = value
    return tuple(sorted(values_by_key.values(), key=lambda item: item.key))


def _normalize_exposures(
    exposures: Mapping[str, Decimal | int | float | str],
) -> dict[str, Decimal]:
    normalized: dict[str, Decimal] = {}
    for symbol, exposure in exposures.items():
        value = _risk_decimal(exposure)
        if value > ZERO:
            normalized[symbol.upper()] = value
    return normalized


def _risk_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(SCORE_QUANT)


def _status_severity(status: RiskRuleStatus) -> int:
    return {
        "passed": 0,
        "warn": 1,
        "reduced": 2,
        "rejected": 3,
        "blocked": 4,
    }[status]


def _matched_symbols_text(symbols: tuple[str, ...]) -> str:
    if not symbols:
        return "none"
    return ", ".join(symbols)


def _normalize_key_part(value: str) -> str:
    return "_".join(value.strip().lower().split())
