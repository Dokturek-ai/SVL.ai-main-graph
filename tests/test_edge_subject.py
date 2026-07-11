"""Unit tests for edge `subject` extraction + merge reconciliation (spec 007).

Pure functions, no LLM / no graph: the text + JSON relation parsers accept a 6th `subject` field
(validated ∈ {source, target}, else default source; a legacy 5-field row defaults to source), and the
merge reconciliation picks one subject across fragments.
"""

import json

import pytest

from lightrag.operate import (
    _handle_single_relationship_extraction,
    _process_json_extraction_result,
    _reconcile_edge_subject,
)


def _rel(attrs):
    return _handle_single_relationship_extraction(attrs, "chunk-1", 123, "f.md")


@pytest.mark.offline
def test_6field_subject_equal_source():
    d = _rel(["relation", "Deprese", "Stres", "etiologie", "Deprese je vyvolána stresem.", "Deprese"])
    assert d["src_id"] == "Deprese" and d["tgt_id"] == "Stres"
    assert d["subject"] == "Deprese"


@pytest.mark.offline
def test_6field_subject_equal_target():
    # source→target order is Stres→Deprese, but the fact is ABOUT Deprese (the target)
    d = _rel(["relation", "Stres", "Deprese", "etiologie", "Deprese je vyvolána stresem.", "Deprese"])
    assert d["src_id"] == "Stres" and d["tgt_id"] == "Deprese"
    assert d["subject"] == "Deprese"


@pytest.mark.offline
def test_5field_legacy_defaults_subject_to_source():
    d = _rel(["relation", "Deprese", "Stres", "etiologie", "Deprese souvisí se stresem."])
    assert d["subject"] == "Deprese"


@pytest.mark.offline
def test_6field_invalid_subject_defaults_to_source():
    d = _rel(["relation", "Deprese", "Stres", "etiologie", "Nějaký popis.", "NesmyslnýSubjekt"])
    assert d["subject"] == "Deprese"  # subject ∉ {source, target} → default source


@pytest.mark.offline
def test_subject_field_does_not_break_weight():
    # weight is read from the description position, so a 6th field never masquerades as weight
    d = _rel(["relation", "A", "B", "kw", "popis.", "A"])
    assert d["weight"] == 1.0


@pytest.mark.offline
async def test_json_parser_reads_subject():
    result = json.dumps(
        {
            "entities": [
                {"name": "Deprese", "type": "Condition", "description": "x"},
                {"name": "Stres", "type": "Concept", "description": "y"},
            ],
            "relationships": [
                {
                    "source": "Stres",
                    "target": "Deprese",
                    "keywords": "etiologie",
                    "description": "Deprese je vyvolána stresem.",
                    "subject": "Deprese",
                }
            ],
        }
    )
    _, edges = await _process_json_extraction_result(result, "chunk-1", 123, "f.md")
    edge = next(iter(edges.values()))[0]
    assert edge["subject"] == "Deprese"  # the target, carried through


@pytest.mark.offline
async def test_json_parser_missing_subject_defaults_source():
    result = json.dumps(
        {
            "entities": [
                {"name": "Deprese", "type": "Condition", "description": "x"},
                {"name": "Stres", "type": "Concept", "description": "y"},
            ],
            "relationships": [
                {"source": "Deprese", "target": "Stres", "keywords": "kw", "description": "popis."}
            ],
        }
    )
    _, edges = await _process_json_extraction_result(result, "chunk-1", 123, "f.md")
    edge = next(iter(edges.values()))[0]
    assert edge["subject"] == "Deprese"  # default source


@pytest.mark.offline
def test_reconcile_most_frequent():
    edges = [{"subject": "A"}, {"subject": "B"}, {"subject": "A"}]
    assert _reconcile_edge_subject(edges, None, "A", "B") == "A"


@pytest.mark.offline
def test_reconcile_tie_break_first_seen():
    edges = [{"subject": "B"}, {"subject": "A"}]  # 1–1 tie → first-seen wins
    assert _reconcile_edge_subject(edges, None, "A", "B") == "B"


@pytest.mark.offline
def test_reconcile_validates_endpoint():
    edges = [{"subject": "Z"}]  # not an endpoint → default src
    assert _reconcile_edge_subject(edges, None, "A", "B") == "A"


@pytest.mark.offline
def test_reconcile_empty_defaults_src():
    assert _reconcile_edge_subject([], None, "A", "B") == "A"


@pytest.mark.offline
def test_reconcile_counts_existing_edge_vote():
    # fragment votes A, existing edge votes B → 1–1 tie, fragment (first-seen) wins
    assert _reconcile_edge_subject([{"subject": "A"}], {"subject": "B"}, "A", "B") == "A"
