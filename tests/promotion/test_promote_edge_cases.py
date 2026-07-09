"""Regression tests for the caveman-review findings."""

import pytest

from lightrag.promotion.locate import locate
from lightrag.promotion.promote import promote


def _snap(nodes, edges, chunks):
    return {
        "docs": [{"doc_id": "d", "file_path": "Test_2020.md", "status": "processed", "chunks_count": len(chunks)}],
        "chunks": [
            {"chunk_id": cid, "doc_id": "d", "file_path": "Test_2020.md", "content": txt, "chunk_order_index": i}
            for i, (cid, txt) in enumerate(chunks)
        ],
        "nodes": nodes,
        "edges": edges,
    }


@pytest.mark.offline
def test_same_name_two_types_collapses_to_one_node():
    # LightRAG can emit one name under two types; it must not cause a name->node
    # collision (which would mis-route the entity's edges).
    snap = _snap(
        nodes=[
            {"name": "Ateroskleróza", "type": "Condition", "source_ids": ["c0"]},
            {"name": "Ateroskleróza", "type": "Concept", "source_ids": ["c0"]},
        ],
        edges=[],
        chunks=[("c0", "Ateroskleróza je rizikový faktor.")],
    )
    b = promote(snap)
    assert len(b.nodes) == 1
    assert b.nodes[0].surface_forms == ["Ateroskleróza"]


@pytest.mark.offline
def test_scattered_stemmed_tokens_do_not_produce_a_meaningless_anchor():
    chunk = "srdeční " + "x " * 60 + "selhání"
    assert locate("Srdeční selhání", chunk) is None


def _snap2docs(nodes, edges):
    # two isolated docs so endpoints can be made to never share a doc
    return {
        "docs": [
            {"doc_id": "d0", "file_path": "A_2020.md", "status": "processed", "chunks_count": 1},
            {"doc_id": "d1", "file_path": "B_2020.md", "status": "processed", "chunks_count": 1},
        ],
        "chunks": [
            {"chunk_id": "c0", "doc_id": "d0", "file_path": "A_2020.md", "content": "Alfa je pojem.", "chunk_order_index": 0},
            {"chunk_id": "c1", "doc_id": "d1", "file_path": "B_2020.md", "content": "Beta je pojem.", "chunk_order_index": 0},
        ],
        "nodes": nodes,
        "edges": edges,
    }


@pytest.mark.offline
def test_endpoints_not_co_locatable_when_no_shared_doc():
    # Alfa in doc d0, Beta in doc d1 — admitted (span) but they never share a doc,
    # so not even doc-level co-location can ground the edge.
    snap = _snap2docs(
        nodes=[
            {"name": "Alfa", "type": "Concept", "source_ids": ["c0"]},
            {"name": "Beta", "type": "Concept", "source_ids": ["c1"]},
        ],
        edges=[{"head": "Alfa", "tail": "Beta", "rel_type": "vztah", "source_ids": ["c0"]}],
    )
    b = promote(snap)
    assert len(b.nodes) == 2 and not b.edges
    reasons = [q.reason for q in b.quarantine if q.kind == "edge"]
    assert reasons == ["endpoints-not-co-locatable"]


@pytest.mark.offline
def test_doc_co_location_uses_grounding_docs_not_raw_source_ids():
    # Alfa's source_ids name c0 (doc d0, where it locates) AND c1 (doc d1, where it
    # does NOT). It is grounded only in d0. Beta is grounded in d1. The edge's chunk
    # is c1 (d1): co-location must fail — Alfa was never grounded in d1 — even though
    # Alfa's raw source_ids include a d1 chunk.
    snap = _snap2docs(
        nodes=[
            {"name": "Alfa", "type": "Concept", "source_ids": ["c0", "c1"]},
            {"name": "Beta", "type": "Concept", "source_ids": ["c1"]},
        ],
        edges=[{"head": "Alfa", "tail": "Beta", "rel_type": "vztah", "source_ids": ["c1"]}],
    )
    b = promote(snap)
    assert not b.edges
    assert [q.reason for q in b.quarantine if q.kind == "edge"] == ["endpoints-not-co-locatable"]


@pytest.mark.offline
def test_doc_level_co_location_recovers_edge_at_chunk_fidelity():
    # Both endpoints in the SAME doc but different chunks (never in one chunk): the
    # span gate would quarantine, hybrid recovers the edge at chunk fidelity.
    snap = _snap(
        nodes=[
            {"name": "Alfa", "type": "Concept", "source_ids": ["c0"]},
            {"name": "Beta", "type": "Concept", "source_ids": ["c1"]},
        ],
        edges=[{"head": "Alfa", "tail": "Beta", "rel_type": "vztah", "source_ids": ["c0"]}],
        chunks=[("c0", "Alfa je pojem."), ("c1", "Beta je pojem.")],
    )
    b = promote(snap)
    assert len(b.edges) == 1
    assert b.edges[0].fidelity == "chunk"
    assert b.edges[0].anchor.match == "chunk"
    assert not [q for q in b.quarantine if q.kind == "edge"]
