import pytest

from lightrag.promotion.promote import promote


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
def test_only_genuinely_ungrounded_is_quarantined(snapshot):
    b = promote(snapshot)
    reasons = {q.name: q.reason for q in b.quarantine}
    # Hybrid: Komorbidity (resolves but no span) is now admitted at chunk fidelity,
    # and its edge co-locates at doc level. Only Ghost — whose source_id points to a
    # missing chunk — is genuinely ungrounded.
    assert reasons == {"Ghost": "chunk-unresolved"}


@pytest.mark.offline
def test_admitted_counts_and_stemmed_anchor(snapshot):
    b = promote(snapshot)
    assert len(b.nodes) == 8  # 9 grounded (Komorbidity now chunk), 2 Praktický merge into 1
    assert len(b.edges) == 5
    srdecni = next(n for n in b.nodes if n.canonical_name == "Srdeční selhání")
    assert any(a.match == "stemmed" for a in srdecni.anchors)


@pytest.mark.offline
def test_span_locatable_records_stay_span(snapshot):
    b = promote(snapshot)
    by = {n.canonical_name: n for n in b.nodes}
    # every entity present as a (inflected) span keeps the gold fidelity + real anchors
    assert by["Arteriální hypertenze"].fidelity == "span"
    assert by["Srdeční selhání"].fidelity == "span"
    assert all(a.match != "chunk" for a in by["Arteriální hypertenze"].anchors)
    ah_edges = [e for e in b.edges if e.head_id == by["Arteriální hypertenze"].node_id]
    assert any(e.rel_type == "lék_volby" and e.fidelity == "span" for e in ah_edges)


@pytest.mark.offline
def test_node_chunk_fidelity_when_resolves_but_no_span(snapshot):
    b = promote(snapshot)
    komorbidity = next(n for n in b.nodes if n.canonical_name == "Komorbidity")
    assert komorbidity.fidelity == "chunk"
    assert komorbidity.anchors and all(a.match == "chunk" for a in komorbidity.anchors)
    # whole-chunk anchor spans the full chunk it is attributed to
    a = komorbidity.anchors[0]
    assert a.start == 0 and a.end > 0


@pytest.mark.offline
def test_edge_chunk_fidelity_by_doc_level_co_location(snapshot):
    b = promote(snapshot)
    by = {n.canonical_name: n for n in b.nodes}
    komorbidity = by["Komorbidity"].node_id
    edge = next(e for e in b.edges if e.tail_id == komorbidity)
    # head (span) + tail (chunk) share a doc; the edge is admitted at chunk fidelity
    assert edge.fidelity == "chunk"
    assert edge.anchor.match == "chunk"


@pytest.mark.offline
def test_concept_ref_propagated_never_resolved(snapshot):
    b = promote(snapshot)
    by = {n.canonical_name: n for n in b.nodes}
    assert by["Arteriální hypertenze"].concept_ref == {"mkn10_code": "I10"}
    assert by["Ramipril"].concept_ref == {"cui": "C0072973"}
    assert by["Betablokátory"].concept_ref is None  # untagged -> null, mkn10 resolves
