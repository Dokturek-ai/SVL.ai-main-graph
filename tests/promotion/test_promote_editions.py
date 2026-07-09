import pytest

from lightrag.promotion.edition import latest_view
from lightrag.promotion.promote import promote


@pytest.mark.offline
def test_older_only_facts_are_superseded(snapshot):
    b = promote(snapshot)
    by = {n.canonical_name: n for n in b.nodes}
    # 140/90 exists only in the 2014 edition; 2024 is the latest -> superseded
    assert by["140/90 mmHg"].superseded_by_edition == "2024"
    assert by["130/80 mmHg"].superseded_by_edition is None
    # a concept present in the latest edition is current
    assert by["Arteriální hypertenze"].superseded_by_edition is None


@pytest.mark.offline
def test_latest_default_view_drops_superseded(snapshot):
    b = promote(snapshot)
    nodes, _ = latest_view(b)
    names = {n.canonical_name for n in nodes}
    assert "130/80 mmHg" in names
    assert "140/90 mmHg" not in names


@pytest.mark.offline
def test_changed_target_across_editions_is_a_conflict(snapshot):
    b = promote(snapshot)
    tlak = [e for e in b.edges if e.rel_type == "cílový_tlak"]
    assert tlak and all(e.conflict for e in tlak)
    info = tlak[0].conflict
    assert set(info["tails_by_edition"]) == {"2014", "2024"}


@pytest.mark.offline
def test_restated_fact_is_not_a_conflict(snapshot):
    b = promote(snapshot)
    lek = [e for e in b.edges if e.rel_type == "lék_volby"]
    assert lek and all(e.conflict is None for e in lek)
    assert lek[0].edition_date == "2024"  # stamped with its latest assertion
    assert lek[0].superseded_by_edition is None
