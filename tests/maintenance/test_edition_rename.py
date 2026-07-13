import pytest

from lightrag.maintenance.edition_rename import RENAMES, plan_rename
from lightrag.promotion.edition import parse_edition

pytestmark = pytest.mark.offline

# the two multi-edition works whose `_unknown` doc is actually the newest edition
HEPATITIDA_UNKNOWN = "Virová hepatitida C_unknown.pdf"
ONKO_UNKNOWN = "Vybraná onkologická onemocnění_unknown.pdf"


def test_all_six_unknown_map_to_a_real_year():
    assert len(RENAMES) == 6
    for old, new in RENAMES.items():
        assert old.endswith("_unknown.pdf")
        # the new name parses to a 4-digit edition year via the same regex the pass uses
        _work, year = parse_edition(new)
        assert year.isdigit() and len(year) == 4


def test_hepatitida_resolves_to_title_page_year_not_creationdate():
    # title page says NOVELIZACE 2023; the PDF CreationDate (2025) postdates the content and must NOT win
    assert RENAMES[HEPATITIDA_UNKNOWN] == "Virová hepatitida C_2023.pdf"


def test_plan_renames_present_unknown_docs():
    live = [HEPATITIDA_UNKNOWN, ONKO_UNKNOWN, "Arteriální hypertenze_2024.pdf"]
    plan = plan_rename(live)
    assert plan.count == 2
    pairs = dict(plan.to_rename)
    assert pairs[HEPATITIDA_UNKNOWN] == "Virová hepatitida C_2023.pdf"
    assert pairs[ONKO_UNKNOWN] == "Vybraná onkologická onemocnění_2023.pdf"
    assert plan.absent == [] or all(a.endswith("_unknown.pdf") for a in plan.absent)


def test_idempotent_already_renamed_is_noop():
    # store already carries the corrected names → nothing to rename
    live = list(RENAMES.values())
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
    # before: _unknown sorts earliest, so _2015 wrongly wins latest over the 2023 novelizace
    from lightrag.promotion.edition import edition_sort_key

    _, unknown_year = parse_edition(HEPATITIDA_UNKNOWN)  # ""
    _, y2015 = parse_edition("Virová hepatitida C_2015.pdf")
    assert edition_sort_key(unknown_year) < edition_sort_key(y2015)  # the bug: newest demoted

    # after rename: 2023 correctly sorts above 2015
    _, y2023 = parse_edition(RENAMES[HEPATITIDA_UNKNOWN])
    assert edition_sort_key(y2023) > edition_sort_key(y2015)
