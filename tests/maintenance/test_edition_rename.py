import unicodedata

import pytest

from lightrag.maintenance.edition_rename import EDITION_YEARS, _new_name, plan_rename
from lightrag.promotion.edition import parse_edition

pytestmark = pytest.mark.offline

# the two multi-edition works whose `_unknown` doc is actually the newest edition
HEPATITIDA_UNKNOWN = "Virová hepatitida C_unknown.pdf"
ONKO_UNKNOWN = "Vybraná onkologická onemocnění_unknown.pdf"


def test_all_six_unknown_map_to_a_real_year():
    assert len(EDITION_YEARS) == 6
    for old, year in EDITION_YEARS.items():
        assert old.endswith("_unknown.pdf")
        assert year.isdigit() and len(year) == 4
        # the derived new name parses to that 4-digit year via the same regex the pass uses
        _work, parsed = parse_edition(_new_name(old, year))
        assert parsed == year


def test_hepatitida_resolves_to_title_page_year_not_creationdate():
    # title page says NOVELIZACE 2023; the PDF CreationDate (2025) postdates the content and must NOT win
    assert EDITION_YEARS[HEPATITIDA_UNKNOWN] == "2023"
    assert _new_name(HEPATITIDA_UNKNOWN, "2023") == "Virová hepatitida C_2023.pdf"


def test_plan_renames_present_unknown_docs():
    live = [HEPATITIDA_UNKNOWN, ONKO_UNKNOWN, "Arteriální hypertenze_2024.pdf"]
    plan = plan_rename(live)
    assert plan.count == 2
    pairs = dict(plan.to_rename)
    assert pairs[HEPATITIDA_UNKNOWN] == "Virová hepatitida C_2023.pdf"
    assert pairs[ONKO_UNKNOWN] == "Vybraná onkologická onemocnění_2023.pdf"


def test_nfd_stored_path_still_matches_and_keeps_stored_spelling():
    # the live bug: macOS stores file_path as NFD; the map is NFC. Match must succeed AND the plan must
    # carry the stored (NFD) spelling so the SQL WHERE file_path=$old hits the stored bytes.
    nfd = unicodedata.normalize("NFD", ONKO_UNKNOWN)
    assert nfd != ONKO_UNKNOWN  # decomposed differs byte-wise
    plan = plan_rename([nfd])
    assert plan.count == 1
    stored_old, new = plan.to_rename[0]
    assert stored_old == nfd  # carries the stored NFD form, not the NFC literal
    assert unicodedata.normalize("NFC", new) == "Vybraná onkologická onemocnění_2023.pdf"


def test_idempotent_already_renamed_is_noop():
    live = [_new_name(old, year) for old, year in EDITION_YEARS.items()]
    plan = plan_rename(live)
    assert plan.count == 0
    assert len(plan.already_done) == 6
    assert plan.absent == []


def test_unlisted_path_is_untouched():
    plan = plan_rename(["Nějaký jiný dokument_2024.pdf"])
    assert plan.count == 0
    assert plan.already_done == []
    assert len(plan.absent) == 6  # all six frozen renames absent from this store


def test_empty_store_empty_plan():
    plan = plan_rename([])
    assert plan.count == 0
    assert plan.already_done == []
    assert len(plan.absent) == 6


def test_supersession_inversion_is_fixed_by_the_new_year():
    from lightrag.promotion.edition import edition_sort_key

    _, unknown_year = parse_edition(HEPATITIDA_UNKNOWN)  # ""
    _, y2015 = parse_edition("Virová hepatitida C_2015.pdf")
    assert edition_sort_key(unknown_year) < edition_sort_key(y2015)  # the bug: newest demoted

    _, y2023 = parse_edition(_new_name(HEPATITIDA_UNKNOWN, EDITION_YEARS[HEPATITIDA_UNKNOWN]))
    assert edition_sort_key(y2023) > edition_sort_key(y2015)  # after rename: 2023 wins
