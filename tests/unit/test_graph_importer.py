from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.repositories import GraphRepository
from taurus_core.db.session import build_session_factory
from taurus_core.graph.importer import TAURUS_GRAPH_CSV_FILES, import_taurus_graph_csvs


def test_taurus_graph_importer_is_idempotent_and_preserves_edge_metadata(
    tmp_path: Path,
) -> None:
    data_dir = _write_graph_fixture(tmp_path / "taurus_data")
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        first_summary = import_taurus_graph_csvs(session, data_dir=data_dir)
    with session_factory() as session:
        second_summary = import_taurus_graph_csvs(session, data_dir=data_dir)
        graph_repo = GraphRepository(session)
        active_edges = graph_repo.list_edges(status="active", limit=None)
        candidate_edges = graph_repo.list_edges(status="candidate", limit=None)
        company_edge = next(edge for edge in active_edges if edge.edge_type == "direct_competitor")
        candidate_edge = next(
            edge
            for edge in candidate_edges
            if edge.edge_type == "common_raw_material_exposure"
        )
        evidence_edge = next(edge for edge in active_edges if edge.edge_type == "has_source_evidence")
        evidence = graph_repo.list_edge_evidence(edge_key=evidence_edge.edge_key)

    assert first_summary.files_missing == ()
    assert second_summary.overview_counts == first_summary.overview_counts
    assert second_summary.overview_counts["candidate_edges"] == 1
    assert second_summary.overview_counts["active_edges"] > second_summary.overview_counts[
        "candidate_edges"
    ]

    assert company_edge.status == "active"
    assert company_edge.source_file == "company_edges.csv"
    assert company_edge.source_row_hash
    assert company_edge.confidence == Decimal("0.7200")
    assert company_edge.inferred is True
    assert company_edge.expected_sign == "negative"
    assert company_edge.mechanism == "Shared IT services demand drivers."
    assert company_edge.edge_metadata["relationship_strength"] == "high"
    assert company_edge.edge_metadata["expected_lag_days_min"] == 0
    assert company_edge.edge_metadata["expected_lag_days_max"] == 180

    assert candidate_edge.status == "candidate"
    assert candidate_edge.source_file == "edge_candidates.csv"
    assert candidate_edge.edge_metadata["relationship_strength"] == "low"
    assert candidate_edge.edge_metadata["basis"] == "Cloud migration exposure"
    assert candidate_edge.edge_metadata["notes"] == "Review before promoting."

    assert len(evidence) == 1
    assert evidence[0].evidence_id == "INFY-NSE-CLASSIFICATION"
    assert evidence[0].source_file == "source_evidence.csv"


def test_taurus_graph_importer_warns_for_missing_optional_csvs(tmp_path: Path) -> None:
    data_dir = tmp_path / "taurus_data"
    data_dir.mkdir()
    _write_csv(
        data_dir / "company_edges.csv",
        """batch_id,source_node_id,source_node_type,source_symbol,source_name,target_node_id,target_node_type,target_symbol,target_name,edge_type,direction,expected_sign,expected_lag_days_min,expected_lag_days_max,relationship_strength,evidence_type,mechanism,tradability_relevance,source,confidence,inferred
test,company:INFY,company,INFY,Infosys Limited,company:TCS,company,TCS,Tata Consultancy Services,direct_competitor,bidirectional,negative,0,180,high,inferred_from_filings,Shared IT services demand drivers.,peer testing,fixture,0.72,True
""",
    )
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        summary = import_taurus_graph_csvs(session, data_dir=data_dir)

    assert summary.files_imported == ("company_edges.csv",)
    assert set(summary.files_missing) == set(TAURUS_GRAPH_CSV_FILES) - {"company_edges.csv"}
    assert len(summary.warnings) == len(summary.files_missing)
    assert summary.overview_counts["edges"] == 1
    assert summary.overview_counts["active_edges"] == 1
    assert summary.overview_counts["candidate_edges"] == 0


def _write_graph_fixture(data_dir: Path) -> Path:
    data_dir.mkdir()
    _write_csv(
        data_dir / "company_industry_classifications.csv",
        """batch_id,input_symbol,input_company_name,nse_symbol,nse_issuer_name,symbol_match_status,isin,listing_status,nse_macro,nse_sector,nse_industry,nse_basic_industry,index,index_list,pd_sector_index,source,confidence,notes
test,INFY,Infosys Ltd.,INFY,Infosys Limited,exact_symbol_match,INE009A01021,Listed,Information Technology,Information Technology,IT Services,Computers - Software,Nifty 50,NIFTY 50,NIFTY IT,NSE quote API secInfo,0.90,
""",
    )
    _write_csv(
        data_dir / "company_segments.csv",
        """batch_id,input_symbol,input_company_name,financial_year,segment_name,revenue,revenue_share_percent,profit_or_ebit,profit_share_percent,products_services,source_document,source_section_or_page,confidence,inferred
test,INFY,Infosys Ltd.,2024-2025,Digital Services,,,,,Cloud transformation,annual report,business review,0.64,True
""",
    )
    _write_csv(
        data_dir / "company_products.csv",
        """batch_id,input_symbol,input_company_name,product_or_service,normalized_product_group,business_segment,customer_industry,product_type,economics_type,source,confidence,inferred
test,INFY,Infosys Ltd.,Cloud migration services,cloud services,Digital Services,enterprise customers,service,recurring,annual report,0.62,True
""",
    )
    _write_csv(
        data_dir / "company_dependencies.csv",
        """batch_id,input_symbol,input_company_name,dependency_name,dependency_type,upstream_or_downstream,related_industry,related_commodity_or_macro_factor,importance,expected_sign,expected_lag_days_min,expected_lag_days_max,mechanism,evidence_type,source,confidence,inferred
test,INFY,Infosys Ltd.,enterprise technology budgets,customer_industry,downstream,enterprise IT,,high,positive,0,90,Technology budget expansion can lift demand.,inferred_from_industry,annual report,0.60,True
""",
    )
    _write_csv(
        data_dir / "company_edges.csv",
        """batch_id,source_node_id,source_node_type,source_symbol,source_name,target_node_id,target_node_type,target_symbol,target_name,edge_type,direction,expected_sign,expected_lag_days_min,expected_lag_days_max,relationship_strength,evidence_type,mechanism,tradability_relevance,source,confidence,inferred
test,company:INFY,company,INFY,Infosys Limited,company:TCS,company,TCS,Tata Consultancy Services,direct_competitor,bidirectional,negative,0,180,high,inferred_from_filings,Shared IT services demand drivers.,peer testing,fixture,0.72,True
""",
    )
    _write_csv(
        data_dir / "edge_candidates.csv",
        """batch_id,source_symbol,source_name,target_symbol,target_name,candidate_edge_type,basis,relationship_strength,evidence_type,expected_sign,confidence,inferred,notes
test,INFY,Infosys Limited,TCS,Tata Consultancy Services,common_raw_material_exposure,Cloud migration exposure,low,curated_profile_overlap,mixed,0.38,True,Review before promoting.
""",
    )
    _write_csv(
        data_dir / "company_risks.csv",
        """batch_id,input_symbol,input_company_name,risk_name,risk_category,affected_segment,expected_impact_direction,time_horizon,peer_or_company_specific,source,confidence
test,INFY,Infosys Ltd.,technology spending slowdown,demand cyclicality,Digital Services,negative,near_term,peer,annual report,0.58
""",
    )
    _write_csv(
        data_dir / "source_evidence.csv",
        """evidence_id,batch_id,input_symbol,input_company_name,claim_type,claim_summary,source_title,source_type,source_date,source_url_or_reference,page_or_section,verbatim_excerpt_short,confidence
INFY-NSE-CLASSIFICATION,test,INFY,Infosys Ltd.,industry_classification,NSE classifies INFY as IT Services.,NSE quote API,exchange_api,2026-05-27,https://example.test/infy,secInfo,,0.90
""",
    )
    return data_dir


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
