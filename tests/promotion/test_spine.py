"""Unit tests for the vendored spine loader + concept_ref validation (promotion.spine, spec 008).

Deterministic, no network: the hash guard on load, and the code∈spine drop on validate.
"""

import json
from pathlib import Path

import pytest

from lightrag.grounding import ATC_SYSTEM, MKN10_SYSTEM
from lightrag.promotion.spine import (
    load_spine,
    spine_hash,
    validate_concept_refs,
)

_VENDORED_SPINE = (
    Path(__file__).resolve().parents[2] / "lightrag/promotion/data/mkn10_spine.json"
)

_CODES = ["I10", "F320", "E11", "E11.2"]


def _snapshot(codes=_CODES, version="2024"):
    return {
        "version": version,
        "count": len(codes),
        "spine_hash": spine_hash(codes),
        "codes": codes,
    }


@pytest.mark.offline
def test_load_spine_from_dict_and_membership():
    spine = load_spine(_snapshot())
    assert spine.version == "2024"
    assert "I10" in spine and "E11.2" in spine
    assert "X999" not in spine


@pytest.mark.offline
def test_load_spine_from_json_string_and_path(tmp_path):
    snap = _snapshot()
    assert load_spine(json.dumps(snap)).spine_hash == snap["spine_hash"]
    p = tmp_path / "spine.json"
    p.write_text(json.dumps(snap))
    assert load_spine(str(p)).codes == frozenset(_CODES)


@pytest.mark.offline
def test_load_spine_hash_mismatch_raises():
    snap = _snapshot()
    snap["codes"] = snap["codes"] + ["Z99"]  # altered set, pinned hash now stale
    with pytest.raises(ValueError, match="spine_hash mismatch"):
        load_spine(snap)


@pytest.mark.offline
def test_spine_hash_is_order_and_dup_independent():
    assert spine_hash(["I10", "F320"]) == spine_hash(["F320", "I10", "I10"])


@pytest.mark.offline
def test_validate_drops_mkn10_code_not_in_spine():
    spine = load_spine(_snapshot())
    refs = [
        {"system": MKN10_SYSTEM, "code": "I10", "display": "hypertenze"},
        {"system": MKN10_SYSTEM, "code": "Z99", "display": "not-in-spine"},
    ]
    kept, dropped = validate_concept_refs(refs, spine)
    assert kept == [{"system": MKN10_SYSTEM, "code": "I10", "display": "hypertenze"}]
    assert dropped == [
        {"system": MKN10_SYSTEM, "code": "Z99", "display": "not-in-spine"}
    ]


@pytest.mark.offline
def test_validate_passes_non_mkn10_systems_through():
    spine = load_spine(_snapshot())
    refs = [{"system": ATC_SYSTEM, "code": "C08CA01", "display": "AMLODIPIN"}]
    kept, dropped = validate_concept_refs(refs, spine)
    assert kept == refs and dropped == []


@pytest.mark.offline
def test_validate_empty_is_noop():
    spine = load_spine(_snapshot())
    assert validate_concept_refs(None, spine) == ([], [])
    assert validate_concept_refs([], spine) == ([], [])


@pytest.mark.offline
def test_vendored_spine_loads_hash_verifies_and_has_real_codes():
    """CI guard on the shipped snapshot: it must load (hash re-derives — catches a
    truncated/corrupted commit), and carry the real ÚZIS 2025 code set."""
    spine = load_spine(str(_VENDORED_SPINE))
    assert spine.version == "2025"
    # known real MKN-10 codes the grounding probe emitted are present
    assert "I10" in spine and "F32.8" in spine and "E26.0" in spine
    # A well-formed but unassigned code is absent — proves the spine is a real allow-list,
    # not "everything code-shaped". A00 subdivides only into .0/.1/.9, so .5 is unassigned.
    # (If a future ÚZIS snapshot ever mints A00.5, swap this for another unassigned code —
    # the intent is a shaped-but-absent sentinel, not this specific code.)
    assert "A00.5" not in spine, "expected an unassigned, well-formed code to be absent"
