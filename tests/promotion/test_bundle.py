import json

import pytest

from promotion.bundle import build_manifest, write_bundle
from promotion.promote import promote


@pytest.mark.offline
def test_manifest_hash_is_deterministic(snapshot):
    m1 = build_manifest(promote(snapshot), snapshot)
    m2 = build_manifest(promote(snapshot), snapshot)
    assert m1.content_hash == m2.content_hash
    assert m1.content_hash  # non-empty


@pytest.mark.offline
def test_counts_surface_completeness(snapshot):
    b = promote(snapshot)
    m = build_manifest(b, snapshot)
    c = m.counts
    assert c["anchor_coverage"] == 1.0
    assert c["doc_coverage"] == 1.0
    assert c["quarantined"] == 3  # 2 entities + 1 edge
    # orphan_rate matches an independent recount (stable across later phases)
    degree = {n.node_id: 0 for n in b.nodes}
    for e in b.edges:
        degree[e.head_id] = degree.get(e.head_id, 0) + 1
        degree[e.tail_id] = degree.get(e.tail_id, 0) + 1
    orphans = sum(1 for n in b.nodes if degree.get(n.node_id, 0) == 0)
    assert c["orphan_rate"] == round(orphans / len(b.nodes), 4)


@pytest.mark.offline
def test_write_bundle_produces_four_files(tmp_path, snapshot):
    b = promote(snapshot)
    m = build_manifest(b, snapshot)
    write_bundle(b, m, tmp_path)
    for name in ("nodes.jsonl", "edges.jsonl", "quarantine.jsonl", "manifest.json"):
        assert (tmp_path / name).exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_hash"] == m.content_hash
    assert len(manifest["corpus"]) == 2  # two editions/docs
