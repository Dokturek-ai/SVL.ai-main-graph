import pytest

from lightrag.promotion.promote import promote

_BLOCK_ID = "tb-4d277c9e95b6f2262179b08804271252-0001"


@pytest.mark.offline
def test_block_id_entities_dropped_before_gate(snapshot):
    """MinerU block-id pseudo-entities (and edges touching them) are filtered pre-gate —
    dropped entirely, NOT added to the quarantine sidecar."""
    base = promote(snapshot)

    # Inject a block-id pseudo-entity + an edge from a real node to it (copy first so
    # the shared fixture is not mutated for other tests).
    injected = {
        **snapshot,
        "nodes": snapshot["nodes"] + [{"name": _BLOCK_ID, "type": "Other", "source_ids": ["c1"]}],
        "edges": snapshot["edges"]
        + [{"head": "Arteriální hypertenze", "tail": _BLOCK_ID, "rel_type": "related", "source_ids": ["c1"]}],
    }
    b = promote(injected)

    # Neither the block-id node nor its edge reaches the bundle or the quarantine sidecar.
    q_names = {q.name for q in b.quarantine}
    assert not any(_BLOCK_ID in n for n in q_names)
    assert all(_BLOCK_ID not in sf for node in b.nodes for sf in node.surface_forms)
    # bundle is identical to baseline — the injected records were filtered, not processed.
    assert len(b.nodes) == len(base.nodes)
    assert len(b.edges) == len(base.edges)
    assert len(b.quarantine) == len(base.quarantine)


@pytest.mark.offline
def test_real_entities_named_like_block_id_prefix_survive(snapshot):
    """A real entity whose name merely starts with 'im'/'tb' but is not the hex-block-id
    shape must NOT be filtered (guard against an over-broad pattern)."""
    from lightrag.promotion.promote import _is_block_id

    assert _is_block_id(_BLOCK_ID)
    assert _is_block_id("im-4d277c9e95b6f2262179b08804271252-0002")
    assert not _is_block_id("Imunosuprese")
    assert not _is_block_id("tbc")  # tuberculosis shorthand, not a block id
    assert not _is_block_id("Tbc-pozitivní pacient")
    assert not _is_block_id("")
