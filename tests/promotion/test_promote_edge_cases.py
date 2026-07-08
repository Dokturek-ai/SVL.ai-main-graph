"""Regression tests for the caveman-review findings."""

import pytest

from promotion.locate import locate
from promotion.promote import promote


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


@pytest.mark.offline
def test_endpoints_not_co_locatable_is_a_distinct_reason():
    snap = _snap(
        nodes=[
            {"name": "Alfa", "type": "Concept", "source_ids": ["c0"]},
            {"name": "Beta", "type": "Concept", "source_ids": ["c1"]},
        ],
        edges=[{"head": "Alfa", "tail": "Beta", "rel_type": "vztah", "source_ids": ["c0"]}],
        chunks=[("c0", "Alfa je pojem."), ("c1", "Beta je pojem.")],
    )
    b = promote(snap)
    assert not b.edges
    reasons = [q.reason for q in b.quarantine if q.kind == "edge"]
    assert reasons == ["endpoints-not-co-locatable"]
