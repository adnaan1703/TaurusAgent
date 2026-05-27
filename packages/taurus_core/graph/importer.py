from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from taurus_core.db.models import GraphEdgeModel, GraphNodeModel
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.domain.instruments import Instrument
from taurus_core.intelligence.documents import stable_id

TAURUS_GRAPH_CSV_FILES: tuple[str, ...] = (
    "company_industry_classifications.csv",
    "company_segments.csv",
    "company_products.csv",
    "company_dependencies.csv",
    "company_edges.csv",
    "edge_candidates.csv",
    "company_risks.csv",
    "source_evidence.csv",
)

STRENGTH_SCORES: dict[str, Decimal] = {
    "very_high": Decimal("0.90"),
    "high": Decimal("0.80"),
    "medium": Decimal("0.50"),
    "low": Decimal("0.25"),
    "very_low": Decimal("0.10"),
}


class TaurusGraphImportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TaurusGraphImportSummary:
    data_dir: str
    files_imported: tuple[str, ...]
    files_missing: tuple[str, ...]
    rows_seen: dict[str, int]
    rows_imported: dict[str, int]
    nodes_upserted: int
    edges_upserted: int
    active_edges_upserted: int
    candidate_edges_upserted: int
    evidence_upserted: int
    warnings: tuple[str, ...]
    overview_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "data_dir": self.data_dir,
            "files_imported": list(self.files_imported),
            "files_missing": list(self.files_missing),
            "rows_seen": dict(self.rows_seen),
            "rows_imported": dict(self.rows_imported),
            "nodes_upserted": self.nodes_upserted,
            "edges_upserted": self.edges_upserted,
            "active_edges_upserted": self.active_edges_upserted,
            "candidate_edges_upserted": self.candidate_edges_upserted,
            "evidence_upserted": self.evidence_upserted,
            "warnings": list(self.warnings),
            "overview_counts": dict(self.overview_counts),
        }


def import_taurus_graph_csvs(
    session: Session,
    data_dir: str | Path = "configs/taurus_data",
) -> TaurusGraphImportSummary:
    importer = _TaurusGraphCSVImporter(session=session, data_dir=Path(data_dir).expanduser())
    return importer.import_all()


class _TaurusGraphCSVImporter:
    def __init__(self, *, session: Session, data_dir: Path) -> None:
        self.session = session
        self.data_dir = data_dir
        self.graph_repo = GraphRepository(session)
        self.instrument_repo = InstrumentRepository(session)
        self.files_imported: list[str] = []
        self.files_missing: list[str] = []
        self.warnings: list[str] = []
        self.rows_seen: dict[str, int] = {}
        self.rows_imported: dict[str, int] = {}
        self.nodes_upserted = 0
        self.edges_upserted = 0
        self.active_edges_upserted = 0
        self.candidate_edges_upserted = 0
        self.evidence_upserted = 0

    def import_all(self) -> TaurusGraphImportSummary:
        if not self.data_dir.exists():
            raise TaurusGraphImportError(f"TaurusData graph directory not found: {self.data_dir}")
        if not self.data_dir.is_dir():
            raise TaurusGraphImportError(f"TaurusData graph path is not a directory: {self.data_dir}")

        importers: dict[str, Callable[[dict[str, str], str, str], bool]] = {
            "company_industry_classifications.csv": self._import_industry_classification,
            "company_segments.csv": self._import_company_segment,
            "company_products.csv": self._import_company_product,
            "company_dependencies.csv": self._import_company_dependency,
            "company_edges.csv": self._import_company_edge,
            "edge_candidates.csv": self._import_edge_candidate,
            "company_risks.csv": self._import_company_risk,
            "source_evidence.csv": self._import_source_evidence,
        }
        for filename in TAURUS_GRAPH_CSV_FILES:
            self._import_file(filename, importers[filename])

        self.session.commit()
        return TaurusGraphImportSummary(
            data_dir=str(self.data_dir),
            files_imported=tuple(self.files_imported),
            files_missing=tuple(self.files_missing),
            rows_seen=dict(self.rows_seen),
            rows_imported=dict(self.rows_imported),
            nodes_upserted=self.nodes_upserted,
            edges_upserted=self.edges_upserted,
            active_edges_upserted=self.active_edges_upserted,
            candidate_edges_upserted=self.candidate_edges_upserted,
            evidence_upserted=self.evidence_upserted,
            warnings=tuple(self.warnings),
            overview_counts=self.graph_repo.overview_counts(),
        )

    def _import_file(
        self,
        filename: str,
        row_importer: Callable[[dict[str, str], str, str], bool],
    ) -> None:
        path = self.data_dir / filename
        if not path.exists():
            self.files_missing.append(filename)
            self.warnings.append(f"Optional TaurusData graph CSV missing: {filename}")
            self.rows_seen[filename] = 0
            self.rows_imported[filename] = 0
            return
        if not path.is_file():
            raise TaurusGraphImportError(f"TaurusData graph CSV path is not a file: {path}")

        seen = 0
        imported = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                seen += 1
                row_hash = _source_row_hash(filename, row)
                if row_importer(row, filename, row_hash):
                    imported += 1

        self.files_imported.append(filename)
        self.rows_seen[filename] = seen
        self.rows_imported[filename] = imported

    def _import_industry_classification(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        symbol = _first_value(row, "nse_symbol", "input_symbol")
        if not symbol:
            self._warn_skipped(source_file, row_hash, "missing company symbol")
            return False

        company = self._upsert_company_node(
            symbol=symbol,
            name=_first_value(row, "nse_issuer_name", "input_company_name", fallback=symbol),
            isin=_value(row, "isin") or None,
            metadata={
                "industry_classification": _metadata_payload(row, source_file, row_hash),
                "batch_id": _value(row, "batch_id"),
            },
        )

        classification_fields = (
            ("industry_macro", "nse_macro", "classified_as_macro"),
            ("industry_sector", "nse_sector", "classified_as_sector"),
            ("industry", "nse_industry", "classified_as_industry"),
            ("basic_industry", "nse_basic_industry", "classified_as_basic_industry"),
            ("market_index", "index", "member_of_index"),
            ("sector_index", "pd_sector_index", "member_of_sector_index"),
        )
        imported_any = False
        for node_type, column, edge_type in classification_fields:
            display_name = _value(row, column)
            if not display_name or display_name == "-":
                continue
            target = self._upsert_node(
                node_key=_node_key(node_type, display_name),
                node_type=node_type,
                display_name=display_name,
                metadata={"source": "taurus_data", "field": column},
            )
            self._upsert_edge(
                namespace="industry",
                source_node_key=company.node_key,
                target_node_key=target.node_key,
                edge_type=edge_type,
                expected_sign="unknown",
                strength=_decimal_or_none(_value(row, "confidence")),
                evidence_type="classification",
                confidence=_decimal_or_default(_value(row, "confidence")),
                inferred=False,
                mechanism=f"NSE classification maps {company.display_name} to {display_name}.",
                tradability_relevance="context",
                status="active",
                source_file=source_file,
                source_row_hash=row_hash,
                metadata={
                    "classification_field": column,
                    "classification_value": display_name,
                    "batch_id": _value(row, "batch_id"),
                    "source": _value(row, "source"),
                    "raw": _clean_row(row),
                },
            )
            imported_any = True

        return imported_any or company is not None

    def _import_company_segment(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        symbol = _value(row, "input_symbol")
        segment_name = _value(row, "segment_name")
        if not symbol or not segment_name:
            self._warn_skipped(source_file, row_hash, "missing company symbol or segment name")
            return False

        company = self._upsert_company_node(
            symbol=symbol,
            name=_first_value(row, "input_company_name", fallback=symbol),
        )
        segment = self._upsert_node(
            node_key=_node_key("segment", symbol, segment_name),
            node_type="segment",
            display_name=segment_name,
            metadata={
                "financial_year": _value(row, "financial_year"),
                "products_services": _value(row, "products_services"),
            },
        )
        self._upsert_edge(
            namespace="segment",
            source_node_key=company.node_key,
            target_node_key=segment.node_key,
            edge_type="has_segment",
            expected_sign="unknown",
            strength=_decimal_or_none(_value(row, "confidence")),
            evidence_type="segment_mapping",
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=_parse_bool(_value(row, "inferred")),
            mechanism=f"{company.display_name} has business segment {segment_name}.",
            tradability_relevance="context",
            status="active",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "financial_year": _value(row, "financial_year"),
                "revenue": _value(row, "revenue"),
                "revenue_share_percent": _value(row, "revenue_share_percent"),
                "profit_or_ebit": _value(row, "profit_or_ebit"),
                "profit_share_percent": _value(row, "profit_share_percent"),
                "products_services": _value(row, "products_services"),
                "source_document": _value(row, "source_document"),
                "source_section_or_page": _value(row, "source_section_or_page"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        return True

    def _import_company_product(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        symbol = _value(row, "input_symbol")
        product_name = _first_value(row, "normalized_product_group", "product_or_service")
        if not symbol or not product_name:
            self._warn_skipped(source_file, row_hash, "missing company symbol or product")
            return False

        company = self._upsert_company_node(
            symbol=symbol,
            name=_first_value(row, "input_company_name", fallback=symbol),
        )
        product = self._upsert_node(
            node_key=_node_key("product_group", product_name),
            node_type="product_group",
            display_name=product_name,
            metadata={
                "product_or_service": _value(row, "product_or_service"),
                "product_type": _value(row, "product_type"),
                "economics_type": _value(row, "economics_type"),
            },
        )
        self._upsert_edge(
            namespace="product",
            source_node_key=company.node_key,
            target_node_key=product.node_key,
            edge_type="offers_product",
            expected_sign="unknown",
            strength=_decimal_or_none(_value(row, "confidence")),
            evidence_type="product_mapping",
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=_parse_bool(_value(row, "inferred")),
            mechanism=f"{company.display_name} offers {product_name}.",
            tradability_relevance="context",
            status="active",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "product_or_service": _value(row, "product_or_service"),
                "normalized_product_group": _value(row, "normalized_product_group"),
                "business_segment": _value(row, "business_segment"),
                "customer_industry": _value(row, "customer_industry"),
                "product_type": _value(row, "product_type"),
                "economics_type": _value(row, "economics_type"),
                "source": _value(row, "source"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        return True

    def _import_company_dependency(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        symbol = _value(row, "input_symbol")
        dependency_name = _first_value(
            row,
            "dependency_name",
            "related_commodity_or_macro_factor",
            "related_industry",
        )
        if not symbol or not dependency_name:
            self._warn_skipped(source_file, row_hash, "missing company symbol or dependency")
            return False

        company = self._upsert_company_node(
            symbol=symbol,
            name=_first_value(row, "input_company_name", fallback=symbol),
        )
        dependency_type = _value(row, "dependency_type") or "dependency"
        dependency = self._upsert_node(
            node_key=_node_key("dependency", dependency_type, dependency_name),
            node_type="dependency",
            display_name=dependency_name,
            metadata={
                "dependency_type": dependency_type,
                "related_industry": _value(row, "related_industry"),
                "related_commodity_or_macro_factor": _value(
                    row,
                    "related_commodity_or_macro_factor",
                ),
            },
        )
        upstream_or_downstream = _value(row, "upstream_or_downstream").lower()
        if upstream_or_downstream == "upstream":
            source_node_key = dependency.node_key
            target_node_key = company.node_key
        else:
            source_node_key = company.node_key
            target_node_key = dependency.node_key

        relationship_strength = _value(row, "importance")
        self._upsert_edge(
            namespace="dependency",
            source_node_key=source_node_key,
            target_node_key=target_node_key,
            edge_type=dependency_type,
            direction="directed",
            expected_sign=_value(row, "expected_sign") or "unknown",
            strength=_strength_score(relationship_strength, _value(row, "confidence")),
            evidence_type=_value(row, "evidence_type"),
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=_parse_bool(_value(row, "inferred")),
            mechanism=_value(row, "mechanism"),
            tradability_relevance="dependency",
            status="active",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "relationship_strength": relationship_strength,
                "expected_lag_days_min": _int_or_none(_value(row, "expected_lag_days_min")),
                "expected_lag_days_max": _int_or_none(_value(row, "expected_lag_days_max")),
                "upstream_or_downstream": upstream_or_downstream,
                "related_industry": _value(row, "related_industry"),
                "related_commodity_or_macro_factor": _value(
                    row,
                    "related_commodity_or_macro_factor",
                ),
                "source": _value(row, "source"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        return True

    def _import_company_edge(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        source_symbol = _value(row, "source_symbol")
        target_symbol = _value(row, "target_symbol")
        if not source_symbol or not target_symbol:
            self._warn_skipped(source_file, row_hash, "missing source or target symbol")
            return False

        source_node = self._upsert_company_node(
            symbol=source_symbol,
            name=_first_value(row, "source_name", fallback=source_symbol),
        )
        target_node = self._upsert_company_node(
            symbol=target_symbol,
            name=_first_value(row, "target_name", fallback=target_symbol),
        )
        relationship_strength = _value(row, "relationship_strength")
        self._upsert_edge(
            namespace="company_edge",
            source_node_key=_value(row, "source_node_id") or source_node.node_key,
            target_node_key=_value(row, "target_node_id") or target_node.node_key,
            edge_type=_value(row, "edge_type") or "company_relationship",
            direction=_value(row, "direction") or "directed",
            expected_sign=_value(row, "expected_sign") or "unknown",
            strength=_strength_score(relationship_strength, _value(row, "confidence")),
            evidence_type=_value(row, "evidence_type"),
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=_parse_bool(_value(row, "inferred")),
            mechanism=_value(row, "mechanism"),
            tradability_relevance=_value(row, "tradability_relevance"),
            status="active",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "relationship_strength": relationship_strength,
                "expected_lag_days_min": _int_or_none(_value(row, "expected_lag_days_min")),
                "expected_lag_days_max": _int_or_none(_value(row, "expected_lag_days_max")),
                "source": _value(row, "source"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        return True

    def _import_edge_candidate(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        source_symbol = _value(row, "source_symbol")
        target_symbol = _value(row, "target_symbol")
        if not source_symbol or not target_symbol:
            self._warn_skipped(source_file, row_hash, "missing source or target symbol")
            return False

        source_node = self._upsert_company_node(
            symbol=source_symbol,
            name=_first_value(row, "source_name", fallback=source_symbol),
        )
        target_node = self._upsert_company_node(
            symbol=target_symbol,
            name=_first_value(row, "target_name", fallback=target_symbol),
        )
        relationship_strength = _value(row, "relationship_strength")
        self._upsert_edge(
            namespace="edge_candidate",
            source_node_key=source_node.node_key,
            target_node_key=target_node.node_key,
            edge_type=_value(row, "candidate_edge_type") or "candidate_relationship",
            direction="directed",
            expected_sign=_value(row, "expected_sign") or "unknown",
            strength=_strength_score(relationship_strength, _value(row, "confidence")),
            evidence_type=_value(row, "evidence_type"),
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=_parse_bool(_value(row, "inferred")),
            mechanism=_value(row, "basis"),
            tradability_relevance="candidate_review",
            status="candidate",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "relationship_strength": relationship_strength,
                "basis": _value(row, "basis"),
                "notes": _value(row, "notes"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        return True

    def _import_company_risk(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        symbol = _value(row, "input_symbol")
        risk_name = _value(row, "risk_name")
        if not symbol or not risk_name:
            self._warn_skipped(source_file, row_hash, "missing company symbol or risk")
            return False

        company = self._upsert_company_node(
            symbol=symbol,
            name=_first_value(row, "input_company_name", fallback=symbol),
        )
        risk = self._upsert_node(
            node_key=_node_key("risk", _value(row, "risk_category"), risk_name),
            node_type="risk",
            display_name=risk_name,
            metadata={
                "risk_category": _value(row, "risk_category"),
                "time_horizon": _value(row, "time_horizon"),
            },
        )
        self._upsert_edge(
            namespace="risk",
            source_node_key=risk.node_key,
            target_node_key=company.node_key,
            edge_type="exposed_to_risk",
            direction="directed",
            expected_sign=_value(row, "expected_impact_direction") or "unknown",
            strength=_decimal_or_none(_value(row, "confidence")),
            evidence_type="risk_mapping",
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=True,
            mechanism=f"{risk_name} can affect {company.display_name}.",
            tradability_relevance="risk_context",
            status="active",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "risk_category": _value(row, "risk_category"),
                "affected_segment": _value(row, "affected_segment"),
                "time_horizon": _value(row, "time_horizon"),
                "peer_or_company_specific": _value(row, "peer_or_company_specific"),
                "source": _value(row, "source"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        return True

    def _import_source_evidence(
        self,
        row: dict[str, str],
        source_file: str,
        row_hash: str,
    ) -> bool:
        evidence_id = _value(row, "evidence_id")
        symbol = _value(row, "input_symbol")
        if not evidence_id or not symbol:
            self._warn_skipped(source_file, row_hash, "missing evidence id or company symbol")
            return False

        company = self._upsert_company_node(
            symbol=symbol,
            name=_first_value(row, "input_company_name", fallback=symbol),
        )
        source = self._upsert_node(
            node_key=_node_key("source", evidence_id),
            node_type="source",
            display_name=_first_value(row, "source_title", fallback=evidence_id),
            metadata={
                "source_type": _value(row, "source_type"),
                "source_date": _value(row, "source_date"),
                "source_url_or_reference": _value(row, "source_url_or_reference"),
            },
        )
        edge = self._upsert_edge(
            namespace="source_evidence",
            source_node_key=company.node_key,
            target_node_key=source.node_key,
            edge_type="has_source_evidence",
            direction="directed",
            expected_sign="unknown",
            strength=_decimal_or_none(_value(row, "confidence")),
            evidence_type=_value(row, "source_type"),
            confidence=_decimal_or_default(_value(row, "confidence")),
            inferred=False,
            mechanism=_value(row, "claim_summary"),
            tradability_relevance="evidence",
            status="active",
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={
                "claim_type": _value(row, "claim_type"),
                "claim_summary": _value(row, "claim_summary"),
                "source_title": _value(row, "source_title"),
                "source_type": _value(row, "source_type"),
                "source_date_raw": _value(row, "source_date"),
                "source_url_or_reference": _value(row, "source_url_or_reference"),
                "page_or_section": _value(row, "page_or_section"),
                "batch_id": _value(row, "batch_id"),
                "raw": _clean_row(row),
            },
        )
        self.graph_repo.upsert_edge_evidence(
            edge_key=edge.edge_key,
            evidence_id=_evidence_key(evidence_id),
            claim_type=_value(row, "claim_type"),
            claim_summary=_value(row, "claim_summary"),
            source_title=_value(row, "source_title"),
            source_type=_value(row, "source_type"),
            source_date=_parse_date(_value(row, "source_date")),
            source_url_or_reference=_value(row, "source_url_or_reference"),
            page_or_section=_value(row, "page_or_section"),
            verbatim_excerpt_short=_value(row, "verbatim_excerpt_short"),
            confidence=_decimal_or_default(_value(row, "confidence")),
            source_file=source_file,
            source_row_hash=row_hash,
            metadata={"original_evidence_id": evidence_id, "raw": _clean_row(row)},
        )
        self.evidence_upserted += 1
        return True

    def _upsert_company_node(
        self,
        *,
        symbol: str,
        name: str,
        isin: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> GraphNodeModel:
        normalized_symbol = _normalize_symbol(symbol)
        display_name = name.strip() if name else normalized_symbol
        self.instrument_repo.upsert(Instrument(symbol=normalized_symbol, name=display_name))

        node_key = _company_node_key(normalized_symbol)
        existing = self.graph_repo.get_node_by_key(node_key)
        merged_metadata = dict(existing.node_metadata) if existing is not None else {}
        if metadata:
            merged_metadata.update(metadata)
        return self._upsert_node(
            node_key=node_key,
            node_type="company",
            display_name=existing.display_name if existing is not None else display_name,
            symbol=normalized_symbol,
            isin=isin or (existing.isin if existing is not None else None),
            metadata=merged_metadata,
        )

    def _upsert_node(
        self,
        *,
        node_key: str,
        node_type: str,
        display_name: str,
        symbol: str | None = None,
        isin: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> GraphNodeModel:
        node = self.graph_repo.upsert_node(
            node_key=node_key,
            node_type=node_type,
            display_name=display_name,
            symbol=symbol,
            isin=isin,
            metadata=metadata,
        )
        self.nodes_upserted += 1
        return node

    def _upsert_edge(
        self,
        *,
        namespace: str,
        source_node_key: str,
        target_node_key: str,
        edge_type: str,
        direction: str = "directed",
        expected_sign: str = "unknown",
        strength: Decimal | None = None,
        evidence_type: str = "",
        confidence: Decimal = Decimal("0"),
        inferred: bool = False,
        mechanism: str = "",
        tradability_relevance: str = "",
        status: str = "candidate",
        source_file: str = "",
        source_row_hash: str = "",
        metadata: dict[str, object] | None = None,
    ) -> GraphEdgeModel:
        edge = self.graph_repo.upsert_edge(
            edge_key=_edge_key(namespace, source_node_key, target_node_key, edge_type, direction),
            source_node_key=source_node_key,
            target_node_key=target_node_key,
            edge_type=edge_type,
            direction=direction,
            expected_sign=expected_sign,
            strength=strength,
            evidence_type=evidence_type,
            confidence=confidence,
            inferred=inferred,
            mechanism=mechanism,
            tradability_relevance=tradability_relevance,
            status=status,
            source_file=source_file,
            source_row_hash=source_row_hash,
            metadata=metadata,
        )
        self.edges_upserted += 1
        if edge.status == "candidate":
            self.candidate_edges_upserted += 1
        elif edge.status == "active":
            self.active_edges_upserted += 1
        return edge

    def _warn_skipped(self, source_file: str, row_hash: str, reason: str) -> None:
        self.warnings.append(f"Skipped {source_file} row {row_hash}: {reason}.")


def _company_node_key(symbol: str) -> str:
    return f"company:{_normalize_symbol(symbol)}"


def _edge_key(
    namespace: str,
    source_node_key: str,
    target_node_key: str,
    edge_type: str,
    direction: str,
) -> str:
    return stable_id(
        f"ge-{_slug(namespace)}",
        source_node_key,
        target_node_key,
        edge_type.strip().lower(),
        direction.strip().lower(),
    )


def _node_key(prefix: str, *parts: str) -> str:
    cleaned_parts = [part for part in (_slug(value) for value in parts) if part]
    readable = ":".join([_slug(prefix), *cleaned_parts])
    if len(readable) <= 120:
        return readable
    return stable_id(f"gn-{_slug(prefix)}", *parts)


def _evidence_key(evidence_id: str) -> str:
    cleaned = evidence_id.strip()
    if cleaned and len(cleaned) <= 120:
        return cleaned
    return stable_id("gev", cleaned)


def _source_row_hash(source_file: str, row: dict[str, str]) -> str:
    payload = json.dumps(
        {"source_file": source_file, "row": _clean_row(row)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _metadata_payload(row: dict[str, str], source_file: str, row_hash: str) -> dict[str, object]:
    return {"source_file": source_file, "source_row_hash": row_hash, "raw": _clean_row(row)}


def _clean_row(row: dict[str, str]) -> dict[str, str]:
    return {str(key): _clean_text(value) for key, value in row.items() if key is not None}


def _value(row: dict[str, str], key: str) -> str:
    return _clean_text(row.get(key, ""))


def _first_value(row: dict[str, str], *keys: str, fallback: str = "") -> str:
    for key in keys:
        value = _value(row, key)
        if value:
            return value
    return fallback


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_symbol(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip().upper())
    if not normalized:
        raise TaurusGraphImportError("Company symbol must not be empty.")
    return normalized


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "unknown"


def _decimal_or_default(value: str, default: Decimal = Decimal("0")) -> Decimal:
    parsed = _decimal_or_none(value)
    return parsed if parsed is not None else default


def _decimal_or_none(value: str) -> Decimal | None:
    cleaned = value.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _int_or_none(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(Decimal(cleaned))
    except InvalidOperation:
        return None


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _strength_score(relationship_strength: str, confidence: str) -> Decimal | None:
    normalized = _slug(relationship_strength)
    if normalized in STRENGTH_SCORES:
        return STRENGTH_SCORES[normalized]
    return _decimal_or_none(confidence)


def _parse_date(value: str) -> date | None:
    cleaned = value.strip()
    if not cleaned or cleaned == "-":
        return None
    for date_format in ("%Y-%m-%d", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    return None
