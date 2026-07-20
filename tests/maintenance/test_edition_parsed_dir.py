"""Spec 020 — `parsed_artifact_renames` reconciles on-volume parsed artifacts to a renamed edition.

A spec-016 edition rename is metadata-only; it leaves `<work>_unknown.pdf.parsed` on the volume so the
read-path resolver (derives the dir from the renamed `_<year>` file_path) can't load blocks.jsonl. The planner
returns the moves that fix it. Tests use the ASCII doc `Bolesti hlavy` (NFC == NFD) so the on-disk names are
unambiguous across the test host's filesystem.
"""
import pytest

from lightrag.maintenance.edition_rename import parsed_artifact_renames

pytestmark = pytest.mark.offline

OLD = "Bolesti hlavy_unknown.pdf"  # EDITION_YEARS -> 2023
NEW = "Bolesti hlavy_2023.pdf"


def _mk_siblings(root, base, *, pdf=True, parsed=True, mineru=True):
    if pdf:
        (root / base).write_text("x", encoding="utf-8")
    if parsed:
        (root / f"{base}.parsed").mkdir()
    if mineru:
        (root / f"{base}.mineru_raw").mkdir()


def test_yields_all_three_siblings_for_an_unknown_doc(tmp_path):
    _mk_siblings(tmp_path, OLD)
    pairs = {old.name: new.name for old, new in parsed_artifact_renames(tmp_path)}
    assert pairs == {
        OLD: NEW,
        f"{OLD}.parsed": f"{NEW}.parsed",
        f"{OLD}.mineru_raw": f"{NEW}.mineru_raw",
    }


def test_only_yields_the_siblings_that_exist(tmp_path):
    # only the .parsed dir is present (the archived pdf + mineru_raw were pruned)
    _mk_siblings(tmp_path, OLD, pdf=False, parsed=True, mineru=False)
    pairs = [(old.name, new.name) for old, new in parsed_artifact_renames(tmp_path)]
    assert pairs == [(f"{OLD}.parsed", f"{NEW}.parsed")]


def test_skips_a_sibling_whose_new_name_already_exists(tmp_path):
    # idempotent: old .parsed AND new .parsed both present ⇒ do not re-yield the .parsed move
    (tmp_path / f"{OLD}.parsed").mkdir()
    (tmp_path / f"{NEW}.parsed").mkdir()
    names = [old.name for old, _ in parsed_artifact_renames(tmp_path)]
    assert f"{OLD}.parsed" not in names


def test_empty_root_yields_nothing(tmp_path):
    assert parsed_artifact_renames(tmp_path) == []


def test_already_fully_renamed_yields_nothing(tmp_path):
    _mk_siblings(tmp_path, NEW)  # everything already carries the _2023 name
    assert parsed_artifact_renames(tmp_path) == []


def test_pairs_are_under_the_given_root(tmp_path):
    _mk_siblings(tmp_path, OLD)
    for old_p, new_p in parsed_artifact_renames(tmp_path):
        assert old_p.parent == tmp_path
        assert new_p.parent == tmp_path
