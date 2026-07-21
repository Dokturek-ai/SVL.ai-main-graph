import json

import pytest

from lightrag.sidecar.provenance import (
    load_blocks_by_id,
    resolve_provenance,
)


def _block(blockid, heading, parents, page, bbox, ptype="bbox"):
    """A blocks.jsonl content row shaped exactly like lightrag/sidecar/writer.py.

    Mirrors IRPosition.to_jsonable: omit ``anchor``/``range`` when None (a real
    heading/absolute position row has no bbox keys at all).
    """
    pos = {"type": ptype}
    if page is not None:
        pos["anchor"] = page
    if bbox is not None:
        pos["range"] = bbox
    return {
        "type": "content",
        "blockid": blockid,
        "format": "plain_text",
        "content": f"text of {blockid}",
        "heading": heading,
        "parent_headings": parents,
        "level": 2,
        "session_type": "body",
        "table_slice": "none",
        "positions": [pos],
    }


BLOCKS = {
    "b1": _block("b1", "Diagnostika", ["Akutní cystitida"], 3, [72.0, 120.0, 520.0, 180.0]),
    "b2": _block("b2", "Léčba", ["Akutní cystitida"], 4, [72.0, 90.0, 520.0, 300.0]),
}


@pytest.mark.offline
def test_resolves_page_section_bbox_from_primary_block():
    sidecar = {"type": "block", "id": "b1", "refs": [{"type": "block", "id": "b1"}]}
    prov = resolve_provenance(sidecar, BLOCKS)
    assert prov["page"] == 3
    assert prov["section"] == "Akutní cystitida › Diagnostika"
    assert prov["bbox"] == [72.0, 120.0, 520.0, 180.0]
    assert prov["block_ids"] == ["b1"]


@pytest.mark.offline
def test_bbox_is_union_of_same_page_blocks():
    # two blocks on the SAME page → bbox frames the whole chunk (min x0/y0, max x1/y1).
    blocks = {
        "b1": _block("b1", "Diagnostika", ["Akutní cystitida"], 3, [72.0, 120.0, 400.0, 180.0]),
        "b2": _block("b2", "Diagnostika", ["Akutní cystitida"], 3, [80.0, 90.0, 520.0, 160.0]),
    }
    sidecar = {"id": "b1", "refs": [{"id": "b1"}, {"id": "b2"}]}
    prov = resolve_provenance(sidecar, blocks)
    assert prov["page"] == 3
    assert prov["pages"] == [3]
    assert prov["bbox"] == [72.0, 90.0, 520.0, 180.0]


@pytest.mark.offline
def test_bbox_union_excludes_other_page_blocks():
    # cross-page chunk: only the primary-page block contributes (a box can't span a page break).
    sidecar = {"id": "b1", "refs": [{"id": "b1"}, {"id": "b2"}]}
    prov = resolve_provenance(sidecar, BLOCKS)  # b1 p3, b2 p4
    assert prov["bbox"] == [72.0, 120.0, 520.0, 180.0]  # == b1 alone, b2 (p4) excluded


@pytest.mark.offline
def test_bbox_union_abstains_when_primary_page_unknown():
    # primary block has a range but NO anchor (unknown page) → union must not merge other blocks in.
    blocks = {
        "b1": _block("b1", "X", ["Y"], None, [72.0, 120.0, 400.0, 180.0]),
        "b2": _block("b2", "X", ["Y"], None, [10.0, 10.0, 520.0, 520.0]),
    }
    prov = resolve_provenance({"id": "b1", "refs": [{"id": "b1"}, {"id": "b2"}]}, blocks)
    assert prov["page"] is None
    assert prov["bbox"] == [72.0, 120.0, 400.0, 180.0]  # primary box unchanged, b2 not merged


@pytest.mark.offline
def test_multi_block_chunk_lists_all_pages_primary_first():
    # a chunk spanning a page break covers b1 (p3) then b2 (p4)
    sidecar = {"id": "b1", "refs": [{"id": "b1"}, {"id": "b2"}]}
    prov = resolve_provenance(sidecar, BLOCKS)
    assert prov["page"] == 3  # primary = first covered
    assert prov["pages"] == [3, 4]
    assert prov["section"] == "Akutní cystitida › Diagnostika"


@pytest.mark.offline
def test_missing_sidecar_or_unknown_block_returns_none():
    assert resolve_provenance(None, BLOCKS) is None
    assert resolve_provenance({}, BLOCKS) is None
    assert resolve_provenance({"refs": [{"id": "ghost"}]}, BLOCKS) is None


@pytest.mark.offline
def test_multimodal_sidecar_without_mm_map_returns_none():
    # a table/drawing sidecar id is a tb-/im- id (not a blockid); without the
    # mm_id_to_blockid map (spec 019) it stays unresolvable → title-only citation
    assert resolve_provenance({"type": "table", "id": "tb-x", "refs": [{"id": "tb-x"}]}, BLOCKS) is None


@pytest.mark.offline
def test_non_pdf_position_yields_no_page_but_keeps_section():
    # a markdown/heading-anchored block (no bbox) still resolves a section
    md = {"b3": _block("b3", "Dávkování", ["Léčba"], None, None, ptype="heading")}
    prov = resolve_provenance({"id": "b3", "refs": [{"id": "b3"}]}, md)
    assert prov["page"] is None
    assert prov["bbox"] is None
    assert prov["section"] == "Léčba › Dávkování"


@pytest.mark.offline
def test_load_blocks_by_id_skips_meta_and_malformed(tmp_path):
    p = tmp_path / "doc.blocks.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"type": "meta", "doc_id": "d"}),
                json.dumps(BLOCKS["b1"]),
                "not json",
                json.dumps({"type": "content", "content": "no blockid"}),
                json.dumps(BLOCKS["b2"]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_blocks_by_id(p)
    assert set(loaded) == {"b1", "b2"}
    assert resolve_provenance({"id": "b2", "refs": [{"id": "b2"}]}, loaded)["page"] == 4
