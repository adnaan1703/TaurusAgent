from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.engine import RiskEngine, RiskEngineResult
from taurus_core.risk.schemas import HardRuleResult, decision_id_for_proposal, risk_review_id


@pytest.mark.parametrize(
    ("limit_setting", "rule_name", "exposure_label"),
    [
        (
            "taurus_graph_max_basic_industry_exposure_pct",
            "graph_basic_industry_concentration",
            "Software Services",
        ),
        (
            "taurus_graph_max_product_group_exposure_pct",
            "graph_product_group_concentration",
            "Cloud Services",
        ),
        (
            "taurus_graph_max_customer_industry_exposure_pct",
            "graph_customer_industry_concentration",
            "Enterprise IT",
        ),
        (
            "taurus_graph_max_dependency_exposure_pct",
            "graph_dependency_concentration",
            "Skilled Technology Labor",
        ),
        (
            "taurus_graph_max_risk_category_exposure_pct",
            "graph_risk_category_concentration",
            "Demand Cyclicality",
        ),
    ],
)
def test_graph_risk_reduces_each_static_exposure_category(
    tmp_path: Path,
    limit_setting: str,
    rule_name: str,
    exposure_label: str,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        **{limit_setting: Decimal("7.0000")},
    )
    run_migrations(settings)
    _seed_static_graph_fixture(settings)

    result = _evaluate(settings, current_exposures={"BBB": Decimal("5.0000")})
    rule = _rule(result, rule_name)

    assert result.status == "APPROVED_WITH_REDUCTION"
    assert result.approved_position_pct_nav == Decimal("2.0000")
    assert rule.status == "reduced"
    assert exposure_label in rule.details
    assert "BBB" in rule.details


def test_graph_risk_rejects_when_existing_exposure_has_no_capacity(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        taurus_graph_max_basic_industry_exposure_pct=Decimal("4.0000"),
    )
    run_migrations(settings)
    _seed_static_graph_fixture(settings)

    result = _evaluate(settings, current_exposures={"BBB": Decimal("4.5000")})
    rule = _rule(result, "graph_basic_industry_concentration")

    assert result.status == "REJECTED"
    assert result.approved_position_pct_nav == Decimal("0.0000")
    assert rule.status == "rejected"
    assert "Software Services" in rule.details
    assert "rejecting new BUY exposure" in rule.details


def test_graph_risk_warns_near_limit_without_reducing(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        taurus_graph_max_customer_industry_exposure_pct=Decimal("10.0000"),
    )
    run_migrations(settings)
    _seed_static_graph_fixture(settings)

    result = _evaluate(settings, current_exposures={"BBB": Decimal("3.0000")})
    rule = _rule(result, "graph_customer_industry_concentration")

    assert result.status == "APPROVED"
    assert result.approved_position_pct_nav == Decimal("5.0000")
    assert rule.status == "warn"
    assert "Enterprise IT" in rule.details
    assert "near limit" in rule.details


def test_graph_risk_reduces_correlated_cluster_only_when_stats_exist(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        taurus_graph_max_correlated_cluster_exposure_pct=Decimal("7.0000"),
    )
    run_migrations(settings)
    _seed_correlated_cluster_fixture(settings, include_stats=False)

    without_stats = _evaluate(settings, current_exposures={"BBB": Decimal("5.0000")})
    without_stats_rule = _rule(without_stats, "graph_correlated_cluster_concentration")

    _seed_correlated_cluster_stats(settings)
    with_stats = _evaluate(settings, current_exposures={"BBB": Decimal("5.0000")})
    with_stats_rule = _rule(with_stats, "graph_correlated_cluster_concentration")

    assert without_stats.status == "APPROVED"
    assert without_stats.approved_position_pct_nav == Decimal("5.0000")
    assert without_stats_rule.status == "passed"
    assert with_stats.status == "APPROVED_WITH_REDUCTION"
    assert with_stats.approved_position_pct_nav == Decimal("2.0000")
    assert with_stats_rule.status == "reduced"
    assert "AAA correlated cluster: BBB" in with_stats_rule.details
    assert "edge peer:AAA:BBB" in with_stats_rule.details


def _settings_for_temp_db(tmp_path: Path, **overrides: object) -> Settings:
    values = {
        "database_url": f"sqlite:///{tmp_path / 'taurus.db'}",
        "taurus_graph_risk_enabled": True,
        **overrides,
    }
    return Settings(**values)


def _evaluate(
    settings: Settings,
    *,
    current_exposures: dict[str, Decimal],
    requested_position_pct_nav: Decimal = Decimal("5.0000"),
) -> RiskEngineResult:
    proposal = _proposal(requested_position_pct_nav=requested_position_pct_nav)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        return RiskEngine(
            session,
            settings,
            current_position_exposures_pct_nav=current_exposures,
        ).evaluate(
            proposal=proposal,
            decision_id=decision_id_for_proposal(
                run_id=proposal.run_id,
                symbol=proposal.symbol,
                proposal_id=proposal.proposal_id,
            ),
            risk_check_id=risk_review_id(
                run_id=proposal.run_id,
                symbol=proposal.symbol,
                proposal_id=proposal.proposal_id,
                source_report_ids=proposal.source_report_ids,
            ),
        )


def _proposal(*, requested_position_pct_nav: Decimal) -> TraderProposal:
    return TraderProposal(
        proposal_id="prop-graph-risk",
        run_id="run-graph-risk",
        symbol="AAA",
        debate_id="deb-graph-risk",
        as_of=datetime.now(timezone.utc),
        action="BUY",
        confidence=Decimal("0.8000"),
        horizon="short",
        requested_position_pct_nav=requested_position_pct_nav,
        order_type="MARKET",
        entry_rule="Synthetic graph risk test entry.",
        stop_loss_pct=Decimal("3.0000"),
        take_profit_pct=Decimal("6.0000"),
        reason_summary="Synthetic graph risk test proposal.",
        invalid_if=["Synthetic fixture invalidates."],
        source_report_ids=["report-graph-risk"],
        model_version="test_trader_v1",
    )


def _seed_static_graph_fixture(settings: Settings) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        _seed_instruments(session)
        graph_repo = GraphRepository(session)
        for symbol in ("AAA", "BBB"):
            graph_repo.upsert_node(
                node_key=f"company:{symbol}",
                node_type="company",
                display_name=f"{symbol} Limited",
                symbol=symbol,
            )
        graph_repo.upsert_node(
            node_key="basic_industry:software_services",
            node_type="basic_industry",
            display_name="Software Services",
        )
        graph_repo.upsert_node(
            node_key="product_group:cloud_services",
            node_type="product_group",
            display_name="Cloud Services",
        )
        graph_repo.upsert_node(
            node_key="dependency:customer_industry:enterprise_it",
            node_type="dependency",
            display_name="Enterprise IT",
            metadata={"dependency_type": "customer_industry"},
        )
        graph_repo.upsert_node(
            node_key="dependency:labour:skilled_technology_labor",
            node_type="dependency",
            display_name="Skilled Technology Labor",
            metadata={"dependency_type": "labour"},
        )
        graph_repo.upsert_node(
            node_key="risk:demand_cyclicality:it_budget_slowdown",
            node_type="risk",
            display_name="IT Budget Slowdown",
            metadata={"risk_category": "Demand Cyclicality"},
        )
        for symbol in ("AAA", "BBB"):
            graph_repo.upsert_edge(
                edge_key=f"industry:{symbol}:software_services",
                source_node_key=f"company:{symbol}",
                target_node_key="basic_industry:software_services",
                edge_type="classified_as_basic_industry",
                confidence=Decimal("0.9000"),
                status="active",
            )
            graph_repo.upsert_edge(
                edge_key=f"product:{symbol}:cloud_services",
                source_node_key=f"company:{symbol}",
                target_node_key="product_group:cloud_services",
                edge_type="offers_product",
                confidence=Decimal("0.9000"),
                status="active",
            )
            graph_repo.upsert_edge(
                edge_key=f"customer:{symbol}:enterprise_it",
                source_node_key=f"company:{symbol}",
                target_node_key="dependency:customer_industry:enterprise_it",
                edge_type="customer_industry",
                direction="directed",
                expected_sign="positive",
                confidence=Decimal("0.9000"),
                status="active",
            )
            graph_repo.upsert_edge(
                edge_key=f"dependency:{symbol}:skilled_technology_labor",
                source_node_key="dependency:labour:skilled_technology_labor",
                target_node_key=f"company:{symbol}",
                edge_type="labour",
                direction="directed",
                expected_sign="negative",
                confidence=Decimal("0.9000"),
                status="active",
            )
            graph_repo.upsert_edge(
                edge_key=f"risk:{symbol}:demand_cyclicality",
                source_node_key="risk:demand_cyclicality:it_budget_slowdown",
                target_node_key=f"company:{symbol}",
                edge_type="exposed_to_risk",
                direction="directed",
                expected_sign="negative",
                confidence=Decimal("0.9000"),
                status="active",
                metadata={"risk_category": "Demand Cyclicality"},
            )
        session.commit()


def _seed_correlated_cluster_fixture(settings: Settings, *, include_stats: bool) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        _seed_instruments(session)
        graph_repo = GraphRepository(session)
        for symbol in ("AAA", "BBB"):
            graph_repo.upsert_node(
                node_key=f"company:{symbol}",
                node_type="company",
                display_name=f"{symbol} Limited",
                symbol=symbol,
            )
        graph_repo.upsert_edge(
            edge_key="peer:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="peer_momentum",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.8000"),
            confidence=Decimal("0.9000"),
            status="active",
        )
        if include_stats:
            graph_repo.upsert_edge_stats(
                edge_key="peer:AAA:BBB",
                window="20d",
                as_of_date=date(2024, 2, 1),
                sample_size=20,
                raw_correlation=Decimal("0.8200"),
                residual_correlation=Decimal("0.7600"),
                lead_lag_score=Decimal("0.4200"),
                stability_score=Decimal("0.9000"),
            )
        session.commit()


def _seed_correlated_cluster_stats(settings: Settings) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        GraphRepository(session).upsert_edge_stats(
            edge_key="peer:AAA:BBB",
            window="20d",
            as_of_date=date(2024, 2, 1),
            sample_size=20,
            raw_correlation=Decimal("0.8200"),
            residual_correlation=Decimal("0.7600"),
            lead_lag_score=Decimal("0.4200"),
            stability_score=Decimal("0.9000"),
        )
        session.commit()


def _seed_instruments(session) -> None:
    instrument_repo = InstrumentRepository(session)
    for symbol in ("AAA", "BBB"):
        instrument_repo.upsert(Instrument(symbol=symbol, name=f"{symbol} Limited"))


def _rule(result: RiskEngineResult, rule_name: str) -> HardRuleResult:
    for rule in result.hard_rule_results:
        if rule.rule == rule_name:
            return rule
    raise AssertionError(f"Missing hard rule: {rule_name}")
