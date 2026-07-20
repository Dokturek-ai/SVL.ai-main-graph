"""Spec 019 — page/section provenance for multimodal (table/drawing/equation) chunks.

A mm chunk's sidecar is ``{"type": "table"|"drawing"|"equation", "id": "tb-…"|"im-…"|"eq-…"}``; its id maps
(via ``tables.json``/``drawings.json``/``equations.json``) to a ``blockid`` = a positioned content block in
``blocks.jsonl``. The read-path resolver takes that hop when given the ``mm_id_to_blockid`` map.
"""
import json

import pytest

from lightrag.sidecar.provenance import load_mm_id_to_blockid, resolve_provenance


def _block(blockid, heading, parents, page, bbox):
    return {
        "type": "content",
        "blockid": blockid,
        "format": "plain_text",
        "content": f"text of {blockid}",
        "heading": heading,
        "parent_headings": parents,
        "level": 2,
        "positions": [{"type": "bbox", "anchor": page, "range": bbox}],
    }


BLOCKS = {
    "blk-7": _block("blk-7", "Dávkování", ["Antihypertenziva"], 12, [70.0, 100.0, 500.0, 400.0]),
    "blk-9": _block("blk-9", "Léčba", ["Antihypertenziva"], 13, [70.0, 90.0, 500.0, 300.0]),
}
MM_MAP = {"tb-abc-0001": "blk-7", "im-def-0002": "blk-9"}


@pytest.mark.offline
def test_mm_table_sidecar_resolves_containing_block():
    sidecar = {"type": "table", "id": "tb-abc-0001", "refs": [{"type": "table", "id": "tb-abc-0001"}]}
    prov = resolve_provenance(sidecar, BLOCKS, MM_MAP)
    assert prov["page"] == 12
    assert prov["section"] == "Antihypertenziva › Dávkování"
    assert prov["bbox"] == [70.0, 100.0, 500.0, 400.0]
    assert prov["block_ids"] == ["blk-7"]  # translated to the real blockid, not the tb- id


@pytest.mark.offline
def test_mm_drawing_sidecar_id_only_translates():
    # id-only sidecar (no refs) still translates
    prov = resolve_provenance({"type": "drawing", "id": "im-def-0002"}, BLOCKS, MM_MAP)
    assert prov["page"] == 13
    assert prov["block_ids"] == ["blk-9"]


@pytest.mark.offline
def test_mm_sidecar_without_map_or_unmapped_id_returns_none():
    sidecar = {"type": "table", "id": "tb-abc-0001", "refs": [{"id": "tb-abc-0001"}]}
    assert resolve_provenance(sidecar, BLOCKS) is None  # no map ⇒ unresolvable (backward compatible)
    assert resolve_provenance(sidecar, BLOCKS, {}) is None  # empty map ⇒ unresolvable
    # a mm id with no entry in the map ⇒ unresolvable, not a crash
    assert resolve_provenance({"type": "table", "id": "tb-ghost"}, BLOCKS, MM_MAP) is None


@pytest.mark.offline
def test_content_sidecar_unchanged_with_or_without_map():
    content = {"type": "block", "id": "blk-7", "refs": [{"id": "blk-7"}]}
    without = resolve_provenance(content, BLOCKS)
    with_map = resolve_provenance(content, BLOCKS, MM_MAP)
    assert without == with_map  # the map never touches a content sidecar
    assert with_map["page"] == 12


@pytest.mark.offline
def test_load_mm_id_to_blockid_merges_roots_and_skips_incomplete(tmp_path):
    tbl = tmp_path / "doc.tables.json"
    tbl.write_text(
        json.dumps(
            {
                "version": 1,
                "tables": {
                    "tb-1": {"blockid": "blk-a", "heading": "H"},
                    "tb-2": {"heading": "no blockid"},  # skipped
                },
            }
        ),
        encoding="utf-8",
    )
    drw = tmp_path / "doc.drawings.json"
    drw.write_text(json.dumps({"drawings": {"im-1": {"blockid": "blk-b"}}}), encoding="utf-8")
    out = load_mm_id_to_blockid([tbl, drw, tmp_path / "missing.equations.json"])
    assert out == {"tb-1": "blk-a", "im-1": "blk-b"}


@pytest.mark.offline
def test_load_mm_id_to_blockid_empty_on_no_paths():
    assert load_mm_id_to_blockid([]) == {}
    assert load_mm_id_to_blockid(None) == {}
