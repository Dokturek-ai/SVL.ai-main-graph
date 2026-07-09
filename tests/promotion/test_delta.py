import copy

import pytest

from lightrag.promotion.delta import diff
from lightrag.promotion.promote import promote


@pytest.mark.offline
def test_identical_snapshot_has_empty_delta(snapshot):
    d = diff(promote(snapshot), promote(snapshot))
    assert d["nodes"] == {"added": [], "removed": [], "changed": []}
    assert d["edges"] == {"added": [], "removed": [], "changed": []}


@pytest.mark.offline
def test_removed_node_shows_in_delta(snapshot):
    prev = promote(snapshot)
    trimmed = copy.deepcopy(snapshot)
    trimmed["nodes"] = [n for n in trimmed["nodes"] if n["name"] != "Ramipril"]
    trimmed["edges"] = [e for e in trimmed["edges"] if "Ramipril" not in (e["head"], e["tail"])]
    curr = promote(trimmed)
    d = diff(prev, curr)
    assert d["nodes"]["removed"] and not d["nodes"]["added"]


@pytest.mark.offline
def test_changed_node_shows_as_changed(snapshot):
    prev = promote(snapshot)
    edited = copy.deepcopy(snapshot)
    for n in edited["nodes"]:
        if n["name"] == "Betablokátory":
            n["description"] = "Změněný popis."
    curr = promote(edited)
    d = diff(prev, curr)
    assert len(d["nodes"]["changed"]) == 1
    assert not d["nodes"]["added"] and not d["nodes"]["removed"]
