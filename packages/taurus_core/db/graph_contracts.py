from __future__ import annotations

from typing import Literal

GraphEdgeProvenanceType = Literal["deterministic", "derived", "inferred"]

GRAPH_EDGE_PROVENANCE_TYPES: tuple[GraphEdgeProvenanceType, ...] = (
    "deterministic",
    "derived",
    "inferred",
)
GRAPH_EDGE_PROVENANCE_SQL_LIST = "'deterministic', 'derived', 'inferred'"


def normalize_graph_edge_provenance(value: str) -> GraphEdgeProvenanceType:
    normalized = value.strip().lower()
    if normalized not in GRAPH_EDGE_PROVENANCE_TYPES:
        allowed = ", ".join(GRAPH_EDGE_PROVENANCE_TYPES)
        raise ValueError(f"Graph edge provenance_type must be one of: {allowed}.")
    return normalized  # type: ignore[return-value]


def graph_edge_provenance_from_inferred(inferred: bool) -> GraphEdgeProvenanceType:
    return "inferred" if inferred else "deterministic"


def initial_graph_edge_status_for_provenance(
    provenance_type: GraphEdgeProvenanceType,
) -> str:
    return "candidate" if provenance_type == "inferred" else "active"
