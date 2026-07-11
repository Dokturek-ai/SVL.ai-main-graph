"""Unit tests for extract-time concept_ref grounding (lightrag.grounding, spec 008).

The live LLM (``llm_func``) and HTTP (``api``) calls are injected — these cover the pure core:
node.type routing (the poisoning-class guard), candidate parsing, in-set-only selection (no
hallucination), abstain, and the empty-candidate short-circuit. No LLM, no network.
"""

import pytest

from lightrag.grounding import (
    ATC_SYSTEM,
    MKN10_SYSTEM,
    _BROWSER_UA,
    build_grounding_prompt,
    ground_entity,
    neural_search_candidates,
    parse_concept_ref,
    route_domain,
)


@pytest.mark.offline
@pytest.mark.parametrize(
    "node_type,expected",
    [
        ("drug", "drug"),
        ("Drug", "drug"),
        ("MEDICATION", "drug"),
        ("medication", "drug"),
        ("condition", "mkn10"),
        ("diagnosis", "mkn10"),
        ("symptom", "mkn10"),
        ("procedure", "mkn10"),
        ("", "mkn10"),
        (None, "mkn10"),
    ],
)
def test_route_domain(node_type, expected):
    assert route_domain(node_type) == expected


def _canned_api(payload, calls):
    async def api(url, headers):
        calls.append((url, headers))
        return payload

    return api


@pytest.mark.offline
async def test_neural_search_candidates_parses_and_sets_ua_and_query():
    calls = []
    payload = {
        "results": [
            {"code": "F320", "name_cs": "Lehká depresivní fáze", "score_fused": 0.04},
            {"code": "X320", "name_cs": "sluneční záření", "score_fused": 0.05},
        ]
    }
    cands = await neural_search_candidates(
        "deprese",
        "mkn10",
        base_url="https://mkn10.example/",
        api=_canned_api(payload, calls),
    )
    assert cands == [
        {
            "code": "F320",
            "display": "Lehká depresivní fáze",
            "score": 0.04,
            "system": MKN10_SYSTEM,
        },
        {
            "code": "X320",
            "display": "sluneční záření",
            "score": 0.05,
            "system": MKN10_SYSTEM,
        },
    ]
    url, headers = calls[0]
    assert "q=deprese" in url and "domain=mkn10" in url and "limit=4" in url
    assert headers["User-Agent"] == _BROWSER_UA


@pytest.mark.offline
async def test_neural_search_drug_domain_uses_atc_system_and_atc5_fallback():
    payload = {
        "results": [{"atc5": "C08CA01", "inn": "AMLODIPIN", "score_fused": 0.03}]
    }
    cands = await neural_search_candidates(
        "amlodipin",
        "drug",
        base_url="https://mkn10.example",
        api=_canned_api(payload, []),
    )
    assert cands == [
        {"code": "C08CA01", "display": "AMLODIPIN", "score": 0.03, "system": ATC_SYSTEM}
    ]


@pytest.mark.offline
def test_parse_concept_ref_accepts_only_in_set_code():
    candidates = [
        {"code": "X320", "display": "sluneční záření", "system": MKN10_SYSTEM},
        {"code": "F320", "display": "Lehká depresivní fáze", "system": MKN10_SYSTEM},
    ]
    # LLM picks the contextually-correct code (not top-1)
    assert parse_concept_ref("F320", candidates) == [
        {"system": MKN10_SYSTEM, "code": "F320", "display": "Lehká depresivní fáze"}
    ]


@pytest.mark.offline
def test_parse_concept_ref_rejects_hallucinated_code():
    candidates = [{"code": "F320", "display": "d", "system": MKN10_SYSTEM}]
    assert parse_concept_ref("I10", candidates) == []


@pytest.mark.offline
def test_parse_concept_ref_none_abstains():
    candidates = [{"code": "F320", "display": "d", "system": MKN10_SYSTEM}]
    assert parse_concept_ref("NONE", candidates) == []


@pytest.mark.offline
def test_parse_concept_ref_prefers_longer_code_over_prefix():
    candidates = [
        {"code": "F32", "display": "depresivní fáze", "system": MKN10_SYSTEM},
        {"code": "F32.0", "display": "lehká depresivní fáze", "system": MKN10_SYSTEM},
    ]
    # a bare "F32" must NOT match inside "F32.0"; the full code wins
    got = parse_concept_ref("Odpovídá F32.0", candidates)
    assert got == [
        {"system": MKN10_SYSTEM, "code": "F32.0", "display": "lehká depresivní fáze"}
    ]


@pytest.mark.offline
async def test_ground_entity_empty_candidates_abstains_without_llm():
    async def api(url, headers):
        return {"results": []}

    async def llm_func(prompt):  # pragma: no cover - must not be called
        raise AssertionError("llm_func called despite no candidates")

    got = await ground_entity(
        {"name": "NICE", "type": "concept"},
        "kontext",
        llm_func=llm_func,
        neural_base="https://mkn10.example",
        api=api,
    )
    assert got == []


@pytest.mark.offline
async def test_ground_entity_routes_drug_and_returns_llm_pick():
    seen_domain = {}

    async def api(url, headers):
        seen_domain["domain"] = "domain=drug" in url
        return {
            "results": [{"atc5": "C08CA01", "inn": "AMLODIPIN", "score_fused": 0.03}]
        }

    async def llm_func(prompt):
        assert "AMLODIPIN" in prompt  # candidate surfaced to the LLM
        return "C08CA01"

    got = await ground_entity(
        {
            "entity_name": "amlodipin",
            "entity_type": "drug",
            "description": "blokátor Ca",
        },
        "léčba hypertenze",
        llm_func=llm_func,
        neural_base="https://mkn10.example",
        api=api,
    )
    assert (
        seen_domain["domain"] is True
    )  # routed to domain=drug (poisoning-class guard)
    assert got == [{"system": ATC_SYSTEM, "code": "C08CA01", "display": "AMLODIPIN"}]


@pytest.mark.offline
def test_build_grounding_prompt_lists_candidates_and_asks_for_none():
    prompt = build_grounding_prompt(
        "deprese",
        "condition",
        "porucha nálady",
        [{"code": "F320", "display": "Lehká depresivní fáze", "system": MKN10_SYSTEM}],
        "pacient s depresí",
    )
    assert "F320" in prompt and "Lehká depresivní fáze" in prompt
    assert "NONE" in prompt and "deprese" in prompt
