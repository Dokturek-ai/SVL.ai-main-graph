import pytest

from promotion.promote import promote


@pytest.mark.offline
def test_every_emitted_record_is_anchored(snapshot):
    b = promote(snapshot)
    assert b.nodes and b.edges
    assert all(n.anchors for n in b.nodes)  # anchor coverage 100% by construction
    assert all(e.anchor for e in b.edges)


@pytest.mark.offline
def test_nothing_is_silently_dropped(snapshot):
    b = promote(snapshot)
    entity_q = [q for q in b.quarantine if q.kind == "entity"]
    edge_q = [q for q in b.quarantine if q.kind == "edge"]
    # every input node is either quarantined or a surface form of an emitted node
    # (merged case-variants share one node, so count surface forms, not nodes)
    emitted_surface_forms = sum(len(n.surface_forms) for n in b.nodes)
    assert emitted_surface_forms + len(entity_q) == len(snapshot["nodes"])  # 10
    assert len(b.edges) + len(edge_q) == len(snapshot["edges"])  # 5


@pytest.mark.offline
def test_quarantine_reasons(snapshot):
    b = promote(snapshot)
    reasons = {q.name: q.reason for q in b.quarantine}
    assert reasons["Komorbidity"] == "entity-not-found"
    assert reasons["Ghost"] == "chunk-unresolved"
    assert reasons["Arteriální hypertenze -> Komorbidity"] == "endpoint-missing"


@pytest.mark.offline
def test_admitted_counts_and_stemmed_anchor(snapshot):
    b = promote(snapshot)
    assert len(b.nodes) == 7  # 8 grounded, 2 Praktický variants merge into 1
    assert len(b.edges) == 4
    srdecni = next(n for n in b.nodes if n.canonical_name == "Srdeční selhání")
    assert any(a.match == "stemmed" for a in srdecni.anchors)


@pytest.mark.offline
def test_concept_ref_propagated_never_resolved(snapshot):
    b = promote(snapshot)
    by = {n.canonical_name: n for n in b.nodes}
    assert by["Arteriální hypertenze"].concept_ref == {"mkn10_code": "I10"}
    assert by["Ramipril"].concept_ref == {"cui": "C0072973"}
    assert by["Betablokátory"].concept_ref is None  # untagged -> null, mkn10 resolves
