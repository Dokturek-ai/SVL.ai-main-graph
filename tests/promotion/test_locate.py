import pytest

from promotion.locate import locate


@pytest.mark.offline
def test_exact_and_normalized_match():
    chunk = "Lékem první volby je ramipril."
    a = locate("ramipril", chunk)
    assert a and a.match == "exact" and chunk[a.start : a.end] == "ramipril"
    # case + diacritics normalized; span maps back to the raw casing
    b = locate("Ramipril", chunk)
    assert b and b.match == "normalized" and chunk[b.start : b.end] == "ramipril"


@pytest.mark.offline
def test_stemmed_match_handles_czech_inflection():
    chunk = "Betablokátory se podávají u srdečního selhání."
    a = locate("Srdeční selhání", chunk)
    assert a and a.match == "stemmed"
    assert "selhání" in chunk[a.start : a.end]


@pytest.mark.offline
def test_true_miss_returns_none():
    chunk = "Arteriální hypertenze: cílový krevní tlak je pod 140/90 mmHg."
    assert locate("Komorbidity", chunk) is None


@pytest.mark.offline
def test_multiword_and_punctuated_surface():
    chunk = "Arteriální hypertenze: cílový krevní tlak je pod 140/90 mmHg."
    assert locate("Arteriální hypertenze", chunk) is not None
    assert locate("140/90 mmHg", chunk) is not None
