import pytest

from lightrag.promotion.edition import latest_edition, parse_edition
from lightrag.promotion.registry import build_registry


@pytest.mark.offline
def test_registry_resolves_all_source_ids_except_the_missing_one(snapshot):
    reg = build_registry(snapshot["chunks"], snapshot["docs"])
    assert set(reg) == {"hyp2014-c0", "hyp2014-c1", "hyp2024-c0", "hyp2024-c1"}
    all_src = {s for n in snapshot["nodes"] for s in n["source_ids"]}
    unresolved = {s for s in all_src if s not in reg}
    assert unresolved == {"missing-c9"}  # the one intentional chunk-unresolved case


@pytest.mark.offline
def test_registry_stamps_edition_and_content_hash(snapshot):
    reg = build_registry(snapshot["chunks"], snapshot["docs"])
    assert reg["hyp2014-c0"].work_id == "Arteriální hypertenze"
    assert reg["hyp2014-c0"].edition_date == "2014"
    assert reg["hyp2024-c0"].edition_date == "2024"
    assert reg["hyp2014-c0"].content_hash and reg["hyp2024-c0"].content_hash
    assert reg["hyp2014-c0"].content_hash != reg["hyp2024-c0"].content_hash


@pytest.mark.offline
def test_parse_edition_and_ordering():
    assert parse_edition("Arteriální hypertenze_2024.md") == ("Arteriální hypertenze", "2024")
    assert parse_edition("Deprese 2004.pdf") == ("Deprese", "2004")
    assert parse_edition("No year here.md") == ("No year here", "")
    assert latest_edition(["2004", "2024", "2014"]) == "2024"
    assert latest_edition(["", "2004"]) == "2004"
