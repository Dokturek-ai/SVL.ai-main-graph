"""Three-edition supersession/conflict — mirrors the real corpus, where
`Arteriální hypertenze` ships as `_2004`, `_2008`, and `_2014`. The G3 model is
general over N editions (latest = max, everything older is superseded, a
(head, rel_type) with differing tails across ANY editions is a conflict); these
tests pin that it holds for three, not just the two-edition golden fixture.
"""

import pytest

from lightrag.promotion.edition import latest_view
from lightrag.promotion.promote import promote


def _three_edition_snap():
    # One work, three editions; the target BP tightens each edition.
    chunks = [
        ("hyp2004-c0", "Arteriální hypertenze_2004.md", "Arteriální hypertenze: cílový krevní tlak je pod 160/95 mmHg."),
        ("hyp2008-c0", "Arteriální hypertenze_2008.md", "Arteriální hypertenze: cílový krevní tlak je pod 150/90 mmHg."),
        ("hyp2014-c0", "Arteriální hypertenze_2014.md", "Arteriální hypertenze: cílový krevní tlak je pod 140/90 mmHg."),
    ]
    docs = [
        {"doc_id": cid.split("-")[0], "file_path": fp, "status": "processed", "chunks_count": 1}
        for cid, fp, _ in chunks
    ]
    return {
        "docs": docs,
        "chunks": [
            {"chunk_id": cid, "doc_id": cid.split("-")[0], "file_path": fp, "content": txt, "chunk_order_index": 0}
            for cid, fp, txt in chunks
        ],
        "nodes": [
            {"name": "Arteriální hypertenze", "type": "Condition", "source_ids": ["hyp2004-c0", "hyp2008-c0", "hyp2014-c0"]},
            {"name": "160/95 mmHg", "type": "Concept", "source_ids": ["hyp2004-c0"]},
            {"name": "150/90 mmHg", "type": "Concept", "source_ids": ["hyp2008-c0"]},
            {"name": "140/90 mmHg", "type": "Concept", "source_ids": ["hyp2014-c0"]},
        ],
        "edges": [
            {"head": "Arteriální hypertenze", "tail": "160/95 mmHg", "rel_type": "cílový_tlak", "source_ids": ["hyp2004-c0"]},
            {"head": "Arteriální hypertenze", "tail": "150/90 mmHg", "rel_type": "cílový_tlak", "source_ids": ["hyp2008-c0"]},
            {"head": "Arteriální hypertenze", "tail": "140/90 mmHg", "rel_type": "cílový_tlak", "source_ids": ["hyp2014-c0"]},
        ],
    }


@pytest.mark.offline
def test_latest_of_three_is_current_older_two_superseded():
    b = promote(_three_edition_snap())
    by = {n.canonical_name: n for n in b.nodes}
    # 2014 is the latest of {2004, 2008, 2014} -> both older targets superseded by it
    assert by["160/95 mmHg"].superseded_by_edition == "2014"
    assert by["150/90 mmHg"].superseded_by_edition == "2014"
    assert by["140/90 mmHg"].superseded_by_edition is None
    # the work itself is asserted in the latest edition -> current
    assert by["Arteriální hypertenze"].superseded_by_edition is None


@pytest.mark.offline
def test_latest_view_keeps_only_the_2014_target():
    b = promote(_three_edition_snap())
    nodes, _ = latest_view(b)
    names = {n.canonical_name for n in nodes}
    assert "140/90 mmHg" in names
    assert "160/95 mmHg" not in names and "150/90 mmHg" not in names


@pytest.mark.offline
def test_three_way_target_change_is_one_conflict_over_all_editions():
    b = promote(_three_edition_snap())
    tlak = [e for e in b.edges if e.rel_type == "cílový_tlak"]
    assert tlak and all(e.conflict for e in tlak)
    # the conflict record spans all three editions, not just a pair
    assert set(tlak[0].conflict["tails_by_edition"]) == {"2004", "2008", "2014"}
