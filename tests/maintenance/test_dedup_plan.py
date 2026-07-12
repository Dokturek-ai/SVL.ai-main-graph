import pytest

from lightrag.maintenance.dedup import NodeView, plan_dedup

pytestmark = pytest.mark.offline


def _mkn(code):
    return [{"code": code, "system": "https://uzis.cz/terminology/CodeSystem/mkn-10", "display": ""}]


def test_casing_whitespace_diacritic_variants_collapse_to_one_merge():
    nodes = [
        NodeView("eGFR", degree=5),
        NodeView("EGFR", degree=2),
        NodeView("Egfr", degree=1),
    ]
    plan = plan_dedup(nodes)
    assert len(plan.merges) == 1
    m = plan.merges[0]
    assert m.survivor == "eGFR"  # highest degree, none grounded
    assert m.sources == ["EGFR", "Egfr"]
    assert plan.collapsible == 2
    assert plan.conflicts == []


def test_diacritic_and_punct_fold_via_merge_key():
    # promotion merge_key folds diacritics + punct → Praktický lékař ≡ Praktický Lékář
    plan = plan_dedup([NodeView("Praktický lékař", degree=3), NodeView("Praktický Lékář", degree=1)])
    assert len(plan.merges) == 1
    assert plan.merges[0].survivor == "Praktický lékař"


def test_survivor_prefers_the_single_grounded_node_over_degree():
    nodes = [
        NodeView("Diabetes mellitus 2. typu", concept_ref=_mkn("E11.9"), degree=1),
        NodeView("Diabetes Mellitus 2. Typu", degree=99),  # higher degree but ungrounded
    ]
    plan = plan_dedup(nodes)
    assert len(plan.merges) == 1
    assert plan.merges[0].survivor == "Diabetes mellitus 2. typu"  # grounded wins
    assert plan.merges[0].ref == _mkn("E11.9")


def test_survivor_falls_back_to_degree_then_lexmin():
    # no grounded → highest degree
    plan = plan_dedup([NodeView("TSH", degree=1), NodeView("Tsh", degree=7)])
    assert plan.merges[0].survivor == "Tsh"
    # degree tie → lexicographically-first
    plan2 = plan_dedup([NodeView("PSA", degree=2), NodeView("Psa", degree=2)])
    assert plan2.merges[0].survivor == "PSA"


def test_dotted_dotless_is_not_a_conflict():
    # N48.4 ≡ N484 after dot-normalization → merge, survivor keeps the dotted (most-specific spelling tie)
    plan = plan_dedup([
        NodeView("Erektilní dysfunkce", concept_ref=_mkn("N48.4"), degree=3),
        NodeView("Erektilní Dysfunkce", concept_ref=_mkn("N484"), degree=1),
    ])
    assert plan.conflicts == []
    assert len(plan.merges) == 1


def test_category_and_specific_same_family_compatible_keeps_most_specific():
    # N18 (category) + N18.9 (specific) → same family → merge, ref = the specific one
    plan = plan_dedup([
        NodeView("Chronické onemocnění ledvin", concept_ref=_mkn("N18.9"), degree=2),
        NodeView("Chronické Onemocnění Ledvin", concept_ref=_mkn("N18"), degree=4),
    ])
    assert plan.conflicts == []
    assert len(plan.merges) == 1
    assert plan.merges[0].ref[0]["code"] == "N18.9"  # most-specific spelling


def test_genuinely_different_family_is_a_conflict_and_excluded():
    plan = plan_dedup([
        NodeView("Infarkt myokardu", concept_ref=_mkn("I21"), degree=3),
        NodeView("Infarkt Myokardu", concept_ref=_mkn("I25.2"), degree=1),
    ])
    assert plan.merges == []  # excluded — never auto-merged
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].codes == ["I21", "I252"]


def test_pregnancy_poison_pair_is_flagged_as_conflict():
    # I10 essential HT vs O10.0 pre-existing HT in pregnancy — different families → conflict (grounding error)
    plan = plan_dedup([
        NodeView("Esenciální hypertenze", concept_ref=_mkn("I10"), degree=5),
        NodeView("Esenciální Hypertenze", concept_ref=_mkn("O10.0"), degree=1),
    ])
    assert plan.merges == []
    assert plan.conflicts[0].codes == ["I10", "O100"]


def test_survivor_stays_grounded_even_when_an_ungrounded_twin_has_higher_degree():
    # a high-degree UNGROUNDED casing-twin must NOT win survivor — amerge_entities doesn't carry
    # concept_ref, so an ungrounded survivor would drop the code. Grounded (most-specific) wins.
    nodes = [
        NodeView("Chronické Onemocnění Ledvin", degree=99),  # ungrounded, highest degree
        NodeView("Chronické onemocnění ledvin", concept_ref=_mkn("N18"), degree=3),
        NodeView("chronické onemocnění ledvin", concept_ref=_mkn("N18.9"), degree=1),
    ]
    plan = plan_dedup(nodes)
    assert len(plan.merges) == 1
    assert plan.merges[0].survivor == "chronické onemocnění ledvin"  # grounded, most-specific N18.9
    assert "Chronické Onemocnění Ledvin" in plan.merges[0].sources


def _drug(code):
    return [{"code": code, "system": "http://www.whocc.no/atc"}]


def test_same_drug_concept_id_casing_twins_merge():
    ref = _drug("c_aaa")
    plan = plan_dedup([
        NodeView("Metipranolol", concept_ref=ref, degree=2),
        NodeView("METIPRANOLOL", concept_ref=ref, degree=1),
    ])
    assert plan.conflicts == []
    assert len(plan.merges) == 1
    assert plan.merges[0].ref == ref  # a drug ref is not read as an MKN family conflict


def test_different_drug_concept_ids_are_a_conflict():
    # casing-twins of one drug name grounded to DIFFERENT concept-ids = a grounding disagreement → skip
    plan = plan_dedup([
        NodeView("Metipranolol", concept_ref=_drug("c_aaa"), degree=2),
        NodeView("METIPRANOLOL", concept_ref=_drug("c_bbb"), degree=1),
    ])
    assert plan.merges == []
    assert len(plan.conflicts) == 1


def test_disease_and_drug_on_the_same_name_are_a_conflict():
    plan = plan_dedup([
        NodeView("Inzulin", concept_ref=_mkn("E10"), degree=2),
        NodeView("inzulin", concept_ref=_drug("c_xxx"), degree=1),
    ])
    assert plan.merges == []
    assert len(plan.conflicts) == 1


def test_single_node_carrying_two_families_is_a_conflict():
    # one node grounded to two different MKN families blocks the whole cluster (conservative, no bad merge)
    plan = plan_dedup([
        NodeView("Divný Node", concept_ref=_mkn("I21") + _mkn("N18"), degree=2),
        NodeView("divný node", concept_ref=_mkn("I21"), degree=1),
    ])
    assert plan.merges == []
    assert len(plan.conflicts) == 1


def test_singletons_and_identical_names_are_noops():
    assert plan_dedup([]).merges == []
    assert plan_dedup([NodeView("Hypertenze", degree=3)]).merges == []
    # same exact name twice (shouldn't happen from a graph, but be safe) → one distinct name → no-op
    assert plan_dedup([NodeView("Hypertenze"), NodeView("Hypertenze")]).merges == []
