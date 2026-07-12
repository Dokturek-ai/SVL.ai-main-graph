import pytest

from lightrag.guidelines.retrieve_filter import (
    build_code_index,
    chunks_for_code,
    classify_facet,
    code_matches,
    facet_matches,
)

pytestmark = pytest.mark.offline

MKN = "https://uzis.cz/terminology/CodeSystem/mkn-10"


def _mkn(code):
    return {"code": code, "system": MKN}


def test_code_matches_dotted_dotless_and_family():
    assert code_matches("I10.9", "I109")  # dotted ≡ dotless
    assert code_matches("I10", "I10.9")  # category pulls specific
    assert code_matches("E11.9", "E11")  # specific pulls category
    assert not code_matches("I10", "I11")  # different 3-char family
    assert not code_matches("E11", "E14")
    assert code_matches("N18", "N18")


def test_code_matches_short_codes_exact_only():
    assert code_matches("I1", "I1")
    assert not code_matches("I1", "I10")  # too short to prefix-match


def test_code_matches_multi_level_depth_and_boundary():
    # a request deeper than the entity by >1 level still pulls the category (category ⊃ specific)
    assert code_matches("I10", "I10.90")  # entity I10, request I10.90 → same family
    assert code_matches("E11.9", "E11.92")  # both under E11
    # but never across the 3-char family boundary
    assert not code_matches("I10", "I209")
    assert not code_matches("T36", "T50")


def test_build_index_splits_source_ids_and_skips_drugs():
    entities = [
        ([_mkn("I10")], "c1<SEP>c2"),
        ([_mkn("I10.9")], "c3"),
        ([{"code": "c_abc", "system": "http://www.whocc.no/atc"}], "c4"),  # drug → skipped
        ([_mkn("E11")], ""),  # no chunk → skipped
    ]
    idx = build_code_index(entities)
    assert idx["I10"] == {"c1", "c2"}
    assert idx["I109"] == {"c3"}
    assert "C_ABC" not in idx and "c_abc" not in idx
    assert "E11" not in idx  # had no chunk


def test_chunks_for_code_unions_the_family():
    entities = [([_mkn("I10")], "c1"), ([_mkn("I10.9")], "c2"), ([_mkn("I11")], "c3")]
    idx = build_code_index(entities)
    got = chunks_for_code(idx, "I10")  # pulls I10 + I10.9, NOT I11
    assert got == {"c1", "c2"}
    assert chunks_for_code(idx, "I11") == {"c3"}
    assert chunks_for_code(idx, "") == set()


def test_classify_facet_each_enum():
    assert classify_facet("Diagnostika › Kritéria") == "diagnosis"
    assert classify_facet("Léčba arteriální hypertenze") == "treatment"
    assert classify_facet("Dávkování") == "dosing"
    assert classify_facet("Dispenzarizace a sledování") == "followup"
    assert classify_facet("Kontraindikace") == "contraindication"
    assert classify_facet("Úvod a epidemiologie") is None
    assert classify_facet(None) is None


def test_classify_facet_precedence_dosing_over_treatment():
    # a heading naming both farmakoterapie and dávkování resolves to the more-specific dosing
    assert classify_facet("Farmakoterapie a dávkování") == "dosing"


def test_facet_matches():
    assert facet_matches("treatment", None)  # no request → everything
    assert facet_matches("treatment", "treatment")
    assert not facet_matches("diagnosis", "treatment")
    assert not facet_matches(None, "treatment")
