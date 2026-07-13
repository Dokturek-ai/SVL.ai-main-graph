import pytest

from lightrag.guidelines.chunk_tags import (
    build_chunk_tags,
    chunk_has_code,
    load_code_index,
    write_chunk_tags,
)

pytestmark = pytest.mark.offline

MKN = "https://uzis.cz/terminology/CodeSystem/mkn-10"


def _mkn(code):
    return {"code": code, "system": MKN}


def test_propagates_entity_refs_to_its_source_chunks():
    entities = [
        ([_mkn("I10")], "c1<SEP>c2"),
        ([_mkn("E11")], "c2"),
    ]
    tags = build_chunk_tags(entities)
    assert {r["code"] for r in tags["c1"]["concept_ref"]} == {"I10"}
    assert {r["code"] for r in tags["c2"]["concept_ref"]} == {"I10", "E11"}  # union across entities


def test_dedupes_by_code_and_system():
    entities = [([_mkn("I10")], "c1"), ([_mkn("I10")], "c1")]  # same code twice on same chunk
    tags = build_chunk_tags(entities)
    assert len(tags["c1"]["concept_ref"]) == 1


def test_keeps_both_mkn_and_drug_refs():
    entities = [([_mkn("I10"), {"code": "c_abc", "system": "http://www.whocc.no/atc"}], "c1")]
    tags = build_chunk_tags(entities)
    assert {r["code"] for r in tags["c1"]["concept_ref"]} == {"I10", "c_abc"}


def test_facet_from_section_and_refless_section_chunk():
    entities = [([_mkn("I10")], "c1")]
    sections = {"c1": "Léčba", "c9": "Diagnostika"}  # c9 has a section but no grounded entity
    tags = build_chunk_tags(entities, sections)
    assert tags["c1"]["facet"] == "treatment"
    assert tags["c9"]["facet"] == "diagnosis" and tags["c9"]["concept_ref"] is None  # section-only chunk


def test_chunk_with_no_refs_and_no_section_is_absent():
    entities = [([], "c1"), ([_mkn("I10")], "")]  # no refs / no chunk
    assert build_chunk_tags(entities) == {}


def test_empty_input():
    assert build_chunk_tags([]) == {}


def test_chunk_has_code_family_match():
    tag = {"concept_ref": [_mkn("I10.9"), {"code": "c_x", "system": "http://www.whocc.no/atc"}]}
    assert chunk_has_code(tag, "I10")  # family match on the dotted/dotless MKN code
    assert not chunk_has_code(tag, "I11")
    assert not chunk_has_code({"concept_ref": None}, "I10")


def test_write_then_load_code_index_round_trip(tmp_path):
    entities = [([_mkn("I10")], "c1<SEP>c2"), ([_mkn("E11.9")], "c2"), ([], "c3")]
    tags = build_chunk_tags(entities)
    manifest = write_chunk_tags(tags, tmp_path)
    assert manifest["chunk_count"] == 2  # c1, c2 (c3 had no ref)
    idx = load_code_index(tmp_path)  # dot-normalized code -> {chunk_id}
    assert idx["I10"] == {"c1", "c2"}
    assert idx["E119"] == {"c2"}
