from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument


def test_graph_api_vertical_slice_returns_postgres_backed_graph_data(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path, graph_enabled=True)
    keys = _seed_graph(settings)
    client = TestClient(create_app(settings))

    overview = client.get("/graph/overview")
    company = client.get("/graph/company/INFY")
    edge_detail = client.get(f"/graph/edges/{keys['candidate_edge']}")
    edge_evidence = client.get(f"/graph/edges/{keys['candidate_edge']}/evidence")
    candidate_edges = client.get("/graph/candidate-edges")
    graph_signals = client.get("/graph/signals?symbol=INFY")
    bullish_candidates = client.get("/graph/bullish-candidates?min_score=0.10")
    missing_company = client.get("/graph/company/MISSING")

    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["graph_enabled"] is True
    assert overview_payload["neo4j_enabled"] is False
    assert overview_payload["counts"]["nodes"] == 3
    assert overview_payload["counts"]["edges"] == 2
    assert overview_payload["counts"]["active_edges"] == 1
    assert overview_payload["counts"]["candidate_edges"] == 1

    assert company.status_code == 200
    company_payload = company.json()
    assert company_payload["center_node"]["node_key"] == "company:INFY"
    assert company_payload["counts"] == {
        "nodes": 3,
        "edges": 2,
        "active_edges": 1,
        "candidate_edges": 1,
    }
    assert {edge["edge_key"] for edge in company_payload["edges"]} == {
        keys["active_edge"],
        keys["candidate_edge"],
    }

    assert edge_detail.status_code == 200
    detail_payload = edge_detail.json()
    assert detail_payload["edge"]["edge_key"] == keys["candidate_edge"]
    assert detail_payload["edge"]["status"] == "candidate"
    assert detail_payload["source_node"]["node_key"] == "company:INFY"
    assert detail_payload["target_node"]["node_key"] == "company:TCS"
    assert detail_payload["evidence"][0]["evidence_id"] == "evidence:peer:infy:tcs"
    assert detail_payload["stats"][0]["sample_size"] == 90

    assert edge_evidence.status_code == 200
    assert edge_evidence.json()[0]["claim_type"] == "peer_mapping"

    assert candidate_edges.status_code == 200
    candidate_payload = candidate_edges.json()
    assert candidate_payload["total_returned"] == 1
    assert candidate_payload["edges"][0]["edge_key"] == keys["candidate_edge"]

    assert graph_signals.status_code == 200
    signal_payload = graph_signals.json()
    assert signal_payload["total_returned"] == 1
    assert signal_payload["signals"][0]["signal_id"] == "signal:INFY:2026-05-27"
    assert signal_payload["signals"][0]["contributions"][0]["edge_key"] == keys[
        "candidate_edge"
    ]

    assert bullish_candidates.status_code == 200
    bullish_payload = bullish_candidates.json()
    assert bullish_payload["total_returned"] == 1
    assert bullish_payload["candidates"][0]["symbol"] == "INFY"
    assert Decimal(str(bullish_payload["candidates"][0]["score"])) == Decimal("0.4200")

    assert missing_company.status_code == 404


def test_graph_edge_review_endpoints_update_status_and_allow_local_post_cors(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path, graph_enabled=True)
    keys = _seed_graph(settings)
    client = TestClient(create_app(settings))

    cors = client.options(
        f"/graph/edges/{keys['candidate_edge']}/promote",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    promote = client.post(
        f"/graph/edges/{keys['candidate_edge']}/promote",
        json={"reviewed_by": "dashboard", "note": "Evidence is strong enough."},
    )
    reject = client.post(
        f"/graph/edges/{keys['candidate_edge']}/reject",
        json={"reviewed_by": "dashboard", "note": "Reopened and rejected."},
    )
    candidate_edges = client.get("/graph/candidate-edges")

    assert cors.status_code == 200
    assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in cors.headers["access-control-allow-methods"]

    assert promote.status_code == 200
    promote_payload = promote.json()
    assert promote_payload["edge"]["status"] == "active"
    assert promote_payload["edge"]["metadata"]["latest_review"]["reviewed_by"] == "dashboard"
    assert promote_payload["edge"]["metadata"]["latest_review"]["note"] == (
        "Evidence is strong enough."
    )

    assert reject.status_code == 200
    reject_payload = reject.json()
    assert reject_payload["edge"]["status"] == "rejected"
    assert len(reject_payload["edge"]["metadata"]["reviews"]) == 2
    assert candidate_edges.json()["edges"] == []


def test_graph_edge_review_endpoints_require_graph_enabled(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path, graph_enabled=False)
    keys = _seed_graph(settings)
    client = TestClient(create_app(settings))

    overview = client.get("/graph/overview")
    promote = client.post(f"/graph/edges/{keys['candidate_edge']}/promote")

    assert overview.status_code == 200
    assert overview.json()["graph_enabled"] is False
    assert promote.status_code == 403
    assert promote.json()["detail"] == (
        "Graph review endpoints require TAURUS_GRAPH_ENABLED=true"
    )


def _settings_for_temp_db(tmp_path: Path, *, graph_enabled: bool) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_graph_enabled=graph_enabled,
    )


def _seed_graph(settings: Settings) -> dict[str, str]:
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        instrument_repo.upsert(Instrument(symbol="INFY", name="Infosys Limited"))
        instrument_repo.upsert(Instrument(symbol="TCS", name="Tata Consultancy Services"))

        graph_repo = GraphRepository(session)
        graph_repo.upsert_node(
            node_key="company:INFY",
            node_type="company",
            display_name="Infosys Limited",
            symbol="INFY",
            isin="INE009A01021",
            metadata={"fixture": True},
        )
        graph_repo.upsert_node(
            node_key="company:TCS",
            node_type="company",
            display_name="Tata Consultancy Services",
            symbol="TCS",
            isin="INE467B01029",
            metadata={"fixture": True},
        )
        graph_repo.upsert_node(
            node_key="industry:it-services",
            node_type="industry",
            display_name="IT Services",
            metadata={"fixture": True},
        )

        active_edge = graph_repo.upsert_edge(
            edge_key="ge-active-infy-it-services",
            source_node_key="company:INFY",
            target_node_key="industry:it-services",
            edge_type="classified_as_industry",
            expected_sign="unknown",
            strength=Decimal("0.90"),
            evidence_type="classification",
            confidence=Decimal("0.90"),
            inferred=False,
            mechanism="NSE classifies Infosys as IT Services.",
            tradability_relevance="context",
            status="active",
            source_file="fixture.csv",
            source_row_hash="row-active",
        )
        candidate_edge = graph_repo.upsert_edge(
            edge_key="ge-candidate-infy-tcs-peer",
            source_node_key="company:INFY",
            target_node_key="company:TCS",
            edge_type="peer_momentum",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.80"),
            evidence_type="curated_profile_overlap",
            confidence=Decimal("0.70"),
            inferred=True,
            mechanism="Indian IT services peers share demand drivers.",
            tradability_relevance="signal",
            status="candidate",
            source_file="fixture.csv",
            source_row_hash="row-candidate",
            metadata={"basis": "fixture"},
        )
        graph_repo.upsert_edge_evidence(
            edge_key=candidate_edge.edge_key,
            evidence_id="evidence:peer:infy:tcs",
            claim_type="peer_mapping",
            claim_summary="Both companies are IT services peers.",
            source_title="Fixture research",
            source_type="test_fixture",
            source_date=date(2026, 5, 27),
            confidence=Decimal("0.80"),
            source_file="source_evidence.csv",
            source_row_hash="row-evidence",
        )
        graph_repo.upsert_edge_stats(
            edge_key=candidate_edge.edge_key,
            window="90d",
            as_of_date=date(2026, 5, 27),
            sample_size=90,
            raw_correlation=Decimal("0.42"),
        )
        signal = graph_repo.upsert_signal(
            signal_id="signal:INFY:2026-05-27",
            symbol="INFY",
            as_of=datetime(2026, 5, 27, 9, 15, tzinfo=timezone.utc),
            score=Decimal("0.42"),
            confidence=Decimal("0.76"),
            horizon="swing",
            explanation="Peer graph signal is bullish for INFY.",
        )
        graph_repo.upsert_signal_contribution(
            contribution_id="contribution:signal:INFY:TCS",
            signal_id=signal.signal_id,
            edge_key=candidate_edge.edge_key,
            contribution_type="peer_momentum",
            direction="bullish",
            score_contribution=Decimal("0.42"),
            weight=Decimal("1.00"),
            explanation="TCS peer signal supports INFY.",
        )
        session.commit()
    return {
        "active_edge": active_edge.edge_key,
        "candidate_edge": candidate_edge.edge_key,
    }
