"""Unit tests for the prefer-latest-edition read-path filter (utils.select_latest_editions).

Guards the fix from docs/briefs/2026-07-17-guidelines-edition-aware-live-retrieval.md:
dated editions of one guideline (Arteriální hypertenze 2008/2014/2024) otherwise reach
the narrator with equal standing, so a superseded clinical value can be cited as current.

Policy (owner-chosen: prefer-latest + fallback):
- a chunk is dropped when a NEWER edition of the same work is also in the retrieved set;
- a chunk that is the newest retrieved for its work is kept (best available — never empties
  context when the latest edition simply did not surface).

Filtering runs inside process_chunks_unified, so the derived citation list (built from the
returned chunks) excludes superseded editions automatically.
"""

import pytest

from lightrag.base import QueryParam
from lightrag.utils import (
    generate_reference_list_from_chunks,
    process_chunks_unified,
    select_latest_editions,
)

WORK = "Arteriální hypertenze"


def _chunk(year: str, work: str = WORK, content: str = "target BP"):
    suffix = f"_{year}" if year else ""
    return {"content": content, "file_path": f"{work}{suffix}.pdf"}


def test_newer_edition_present_drops_older():
    kept = select_latest_editions(
        [_chunk("2008"), _chunk("2014"), _chunk("2024")]
    )
    paths = [c["file_path"] for c in kept]
    assert paths == [f"{WORK}_2024.pdf"]  # only the latest survives


def test_only_old_edition_is_kept_as_best_available():
    kept = select_latest_editions([_chunk("2008")])
    assert [c["file_path"] for c in kept] == [f"{WORK}_2008.pdf"]


def test_distinct_works_are_independent():
    kept = select_latest_editions(
        [_chunk("2024"), _chunk("2010", work="Diabetes"), _chunk("2008")]
    )
    paths = {c["file_path"] for c in kept}
    # hypertension keeps 2024 (drops 2008); the unrelated diabetes work keeps its only edition
    assert paths == {f"{WORK}_2024.pdf", "Diabetes_2010.pdf"}


def test_nfc_nfd_path_variants_group_as_one_work():
    import unicodedata

    nfc = unicodedata.normalize("NFC", WORK)
    nfd = unicodedata.normalize("NFD", WORK)
    if nfc == nfd:
        pytest.skip("work_id normalizes identically under NFC/NFD here — test vacuous")
    kept = select_latest_editions(
        [_chunk("2008", work=nfd), _chunk("2024", work=nfc)]
    )
    assert len(kept) == 1  # grouped as one work despite NFC/NFD -> older dropped
    assert "2024" in kept[0]["file_path"]


def test_none_or_missing_file_path_does_not_crash():
    # a chunk may carry file_path=None (no COALESCE on the PG read path); it must
    # not raise and must survive (its own unnamed work, best available)
    kept = select_latest_editions(
        [{"content": "x", "file_path": None}, _chunk("2024")]
    )
    assert len(kept) == 2


async def test_filter_applied_in_process_chunks_unified_context_and_refs():
    query_param = QueryParam(enable_rerank=False, chunk_top_k=None)
    kept = await process_chunks_unified(
        query="cílový krevní tlak",
        unique_chunks=[_chunk("2008"), _chunk("2024")],
        query_param=query_param,
        global_config={},
    )
    kept_paths = [c["file_path"] for c in kept]
    assert kept_paths == [f"{WORK}_2024.pdf"]

    references, _ = generate_reference_list_from_chunks(kept)
    ref_paths = [r["file_path"] for r in references]
    assert ref_paths == [f"{WORK}_2024.pdf"]  # superseded edition not cited
