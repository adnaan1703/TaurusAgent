from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from scripts.migrate import run_migrations
from taurus_core.agents.graph_analyst import GraphAnalystAgent
from taurus_core.agents.runner import run_analyst_suite
from taurus_core.config import Settings
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.graph.importer import TaurusGraphImportError, import_taurus_graph_csvs
from taurus_core.llm.mock_provider import MockLLMProvider
from taurus_core.observability.metrics import metrics_response_body


def test_metrics_endpoint_exposes_graph_observability(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    _seed_graph_observability_fixture(settings)

    response = TestClient(create_app(settings)).get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "taurus_app_info" in body
    assert 'taurus_db_table_rows{table="graph_nodes"} 2.0' in body
    _assert_metric_sample(
        body,
        "taurus_graph_nodes_total",
        {"node_type": "company"},
        "2.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_edges_total",
        {"status": "active", "edge_type": "peer_momentum"},
        "1.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_candidates_total",
        {"edge_type": "candidate_peer"},
        "1.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_edge_evidence_total",
        {"claim_type": "relationship", "source_type": "fixture"},
        "1.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_edge_stats_total",
        {"model_version": "graph_stats_v1", "window": "20d", "result": "validated"},
        "1.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_edge_stats_total",
        {"model_version": "graph_stats_v1", "window": "20d", "result": "insufficient"},
        "1.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_signals_total",
        {
            "source_agent": "GraphAnalystAgent",
            "symbol": "AAA",
            "horizon": "medium",
            "direction": "bullish",
        },
        "1.0",
    )
    _assert_metric_sample(
        body,
        "taurus_graph_signal_contributions_total",
        {"contribution_type": "peer_momentum", "direction": "bullish"},
        "1.0",
    )


def test_graph_failure_counters_are_observable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        InstrumentRepository(session).upsert(
            Instrument(symbol="FAILM209", name="Failure Fixture Limited")
        )
        session.commit()

    def fail_graph_agent(
        self: GraphAnalystAgent,
        *,
        symbol: str,
        run_id: str,
    ) -> object:
        raise RuntimeError("simulated graph analyst failure")

    monkeypatch.setattr(GraphAnalystAgent, "run", fail_graph_agent)

    with session_factory() as session:
        with pytest.raises(RuntimeError, match="simulated graph analyst failure"):
            run_analyst_suite(
                session,
                symbol="FAILM209",
                run_id="graph-observability-failure",
                llm_provider=MockLLMProvider(),
                enabled_analysts=("graph",),
            )
        with pytest.raises(TaurusGraphImportError):
            import_taurus_graph_csvs(session, data_dir=tmp_path / "missing_graph_dir")

    body = metrics_response_body().decode("utf-8")
    _assert_metric_sample_at_least(
        body,
        "taurus_graph_agent_failures_total",
        {
            "agent_name": "GraphAnalystAgent",
            "symbol": "FAILM209",
            "error_type": "RuntimeError",
        },
        minimum=1.0,
    )
    _assert_metric_sample_at_least(
        body,
        "taurus_graph_job_failures_total",
        {"job": "import", "error_type": "TaurusGraphImportError"},
        minimum=1.0,
    )


def _seed_graph_observability_fixture(settings: Settings) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        instrument_repo.upsert(Instrument(symbol="AAA", name="AAA Limited"))
        instrument_repo.upsert(Instrument(symbol="BBB", name="BBB Limited"))

        graph_repo = GraphRepository(session)
        graph_repo.upsert_node(
            node_key="company:AAA",
            node_type="company",
            display_name="AAA Limited",
            symbol="AAA",
        )
        graph_repo.upsert_node(
            node_key="company:BBB",
            node_type="company",
            display_name="BBB Limited",
            symbol="BBB",
        )
        graph_repo.upsert_edge(
            edge_key="peer:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="peer_momentum",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.80"),
            confidence=Decimal("0.90"),
            evidence_type="fixture",
            mechanism="Synthetic graph observability fixture.",
            tradability_relevance="signal",
            status="active",
        )
        graph_repo.upsert_edge(
            edge_key="candidate:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="candidate_peer",
            direction="directed",
            expected_sign="unknown",
            strength=Decimal("0.40"),
            confidence=Decimal("0.50"),
            evidence_type="fixture",
            mechanism="Synthetic candidate observability fixture.",
            tradability_relevance="candidate_review",
            status="candidate",
        )
        graph_repo.upsert_edge_evidence(
            edge_key="peer:AAA:BBB",
            evidence_id="evidence:aaa:bbb",
            claim_type="relationship",
            claim_summary="AAA and BBB share a synthetic peer relationship.",
            source_title="Fixture",
            source_type="fixture",
            confidence=Decimal("0.80"),
            source_file="fixture.csv",
            source_row_hash="row-1",
        )
        graph_repo.upsert_edge_stats(
            edge_key="peer:AAA:BBB",
            window="20d",
            as_of_date=datetime(2026, 5, 28, tzinfo=timezone.utc).date(),
            sample_size=20,
            raw_correlation=Decimal("0.81"),
            residual_correlation=Decimal("0.70"),
            lead_lag_score=Decimal("0.20"),
            stability_score=Decimal("0.85"),
        )
        graph_repo.upsert_edge_stats(
            edge_key="candidate:AAA:BBB",
            window="20d",
            as_of_date=datetime(2026, 5, 28, tzinfo=timezone.utc).date(),
            sample_size=0,
            insufficient_data_reason="missing_candles:BBB",
        )
        signal = graph_repo.upsert_signal(
            signal_id="signal:aaa:graph-observability",
            symbol="AAA",
            as_of=datetime(2026, 5, 28, tzinfo=timezone.utc),
            score=Decimal("0.2500"),
            confidence=Decimal("0.6500"),
            horizon="medium",
            explanation="Synthetic bullish graph signal.",
            source_agent="GraphAnalystAgent",
        )
        graph_repo.upsert_signal_contribution(
            contribution_id="contribution:aaa:graph-observability",
            signal_id=signal.signal_id,
            edge_key="peer:AAA:BBB",
            contribution_type="peer_momentum",
            direction="bullish",
            score_contribution=Decimal("0.2500"),
            weight=Decimal("0.7000"),
            explanation="Synthetic bullish contribution.",
        )
        session.commit()


def _assert_metric_sample(
    body: str,
    metric_name: str,
    labels: dict[str, str],
    value: str,
) -> None:
    expected_labels = [f'{key}="{label_value}"' for key, label_value in labels.items()]
    for line in body.splitlines():
        if not line.startswith(f"{metric_name}{{"):
            continue
        if all(label in line for label in expected_labels) and line.endswith(f" {value}"):
            return
    raise AssertionError(f"Metric sample not found: {metric_name} {labels} {value}")


def _assert_metric_sample_at_least(
    body: str,
    metric_name: str,
    labels: dict[str, str],
    *,
    minimum: float,
) -> None:
    expected_labels = [f'{key}="{label_value}"' for key, label_value in labels.items()]
    for line in body.splitlines():
        if not line.startswith(f"{metric_name}{{"):
            continue
        if all(label in line for label in expected_labels):
            value = float(line.rsplit(" ", maxsplit=1)[1])
            if value >= minimum:
                return
    raise AssertionError(f"Metric sample not found above {minimum}: {metric_name} {labels}")
