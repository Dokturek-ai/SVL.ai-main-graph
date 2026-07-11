"""Promote-side edge `subject` → `subject_id` resolution (spec 007).

Uses the two-edition snapshot fixture (conftest). A harvested edge's `subject` name resolves to one of
its endpoints' node_ids; an edge with no subject carries `subject_id = None`.
"""

import copy

import pytest

from lightrag.promotion.promote import promote


@pytest.mark.offline
def test_edge_subject_id_resolves_to_endpoint(snapshot):
    snap = copy.deepcopy(snapshot)
    for e in snap["edges"]:
        if e.get("rel_type") == "lék_volby":
            e["subject"] = e["head"]  # the fact is about the head entity
    b = promote(snap)
    lek = [e for e in b.edges if e.rel_type == "lék_volby"]
    assert lek  # the edge is admitted
    for e in lek:
        assert e.subject_id == e.head_id  # subject name resolved to the head endpoint's node_id


@pytest.mark.offline
def test_edge_without_subject_has_none(snapshot):
    b = promote(snapshot)  # fixture edges carry no subject property
    assert all(e.subject_id is None for e in b.edges)
    # and to_dict surfaces the field
    assert all("subject_id" in e.to_dict() for e in b.edges)
