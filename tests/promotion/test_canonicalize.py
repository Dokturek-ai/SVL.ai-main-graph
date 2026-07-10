import pytest

from lightrag.promotion.canonicalize import load_type_enum, merge_key, validate_type
from lightrag.promotion.promote import promote


@pytest.mark.offline
def test_merge_key_folds_case_and_diacritics():
    assert merge_key("Praktický lékař") == merge_key("Praktický Lékář")
    assert merge_key("Hypertenze") == merge_key("hypertenze")
    assert merge_key("Krevní tlak.") == merge_key("krevní  tlak")  # punct + whitespace


@pytest.mark.offline
def test_alias_maps_variant_to_canonical():
    aliases = {"BB": "Betablokátory"}
    assert merge_key("BB", aliases) == merge_key("Betablokátory")


@pytest.mark.offline
def test_validate_type_maps_unknown_to_other():
    enum = load_type_enum()
    assert "Condition" in enum and "Medication" in enum and "Diagnosis" in enum
    assert validate_type("Condition", enum) == "Condition"
    assert validate_type("Organism", enum) == "Other"


def test_validate_type_is_case_insensitive_and_returns_canonical():
    # The extraction emits lowercase types; they must map to the canonical enum
    # casing, not collapse to "Other" (the bug that made node.type 100% "Other").
    enum = load_type_enum()
    assert validate_type("condition", enum) == "Condition"
    assert validate_type("medication", enum) == "Medication"
    assert validate_type("drug", enum) == "Drug"
    assert validate_type("labtest", enum) == "LabTest"
    assert validate_type("concept", enum) == "Concept"
    # genuine non-clinical / layout noise still maps to Other
    assert validate_type("table", enum) == "Other"
    assert validate_type("", enum) == "Other"


@pytest.mark.offline
def test_case_variants_merge_into_one_node(snapshot):
    b = promote(snapshot)
    prakticky = [n for n in b.nodes if n.type == "Person"]
    assert len(prakticky) == 1
    assert set(prakticky[0].surface_forms) == {"Praktický lékař", "Praktický Lékář"}
