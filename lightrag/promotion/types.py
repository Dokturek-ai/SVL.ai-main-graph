"""Data model for the promotion pass (spec 001, plan §Data model).

All records are plain dataclasses that round-trip to JSON via ``to_dict``.
``ChunkRecord``/``Anchor`` are frozen (hashable, used as keys/values in the
pure pass); the grounded records are mutable so a later phase can stamp
``as_of`` / ``superseded_by_edition`` / ``concept_ref``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    file_path: str
    content: str
    content_hash: str
    work_id: str
    edition_date: str  # string (e.g. "2024") to keep hashing deterministic
    chunk_order_index: int = 0


@dataclass(frozen=True)
class Anchor:
    chunk_id: str
    start: int
    end: int
    match: str  # "exact" | "normalized" | "stemmed" | "chunk"
    page: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundedNode:
    node_id: str
    canonical_name: str
    type: str
    surface_forms: list[str]
    as_of: str
    work_id: str
    edition_date: str
    anchors: list[Anchor]
    source_ids: list[str]
    description: str = ""
    fidelity: str = "span"  # "span" (verbatim/inflected anchor) | "chunk" (chunk-attributed)
    superseded_by_edition: Optional[str] = None
    concept_ref: Optional[dict[str, str]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "canonical_name": self.canonical_name,
            "type": self.type,
            "surface_forms": sorted(self.surface_forms),
            "as_of": self.as_of,
            "work_id": self.work_id,
            "edition_date": self.edition_date,
            "anchors": [a.to_dict() for a in self.anchors],
            "source_ids": sorted(self.source_ids),
            "description": self.description,
            "fidelity": self.fidelity,
            "superseded_by_edition": self.superseded_by_edition,
            "concept_ref": self.concept_ref,
        }


@dataclass
class GroundedEdge:
    edge_id: str
    head_id: str
    tail_id: str
    rel_type: str
    keywords: str
    description: str
    as_of: str
    work_id: str
    edition_date: str
    anchor: Anchor
    fidelity: str = "span"  # "span" (endpoints co-locate in one chunk) | "chunk" (doc-level)
    superseded_by_edition: Optional[str] = None
    conflict: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "head_id": self.head_id,
            "tail_id": self.tail_id,
            "rel_type": self.rel_type,
            "keywords": self.keywords,
            "description": self.description,
            "as_of": self.as_of,
            "work_id": self.work_id,
            "edition_date": self.edition_date,
            "anchor": self.anchor.to_dict(),
            "fidelity": self.fidelity,
            "superseded_by_edition": self.superseded_by_edition,
            "conflict": self.conflict,
        }


@dataclass
class Quarantine:
    kind: str  # "entity" | "edge"
    name: str
    # entity: "chunk-unresolved" (no source_id resolves — genuinely ungrounded)
    # edge: "endpoint-quarantined" | "endpoints-not-co-locatable"
    reason: str
    source_ids: list[str] = field(default_factory=list)
    work_id: str = ""
    edition_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Bundle:
    nodes: list[GroundedNode]
    edges: list[GroundedEdge]
    quarantine: list[Quarantine]


@dataclass
class Manifest:
    content_hash: str
    corpus: list[dict[str, Any]]
    pins: dict[str, Any]
    counts: dict[str, Any]
