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
    append_resolve_cache,
    build_grounding_prompt,
    build_verify_prompt,
    ground_entity,
    ground_entity_cached,
    is_clinical_type,
    load_resolve_cache,
    neural_search_candidates,
    parse_concept_ref,
    parse_verdict,
    resolve_cache_key,
    route_domain,
    verify_concept_ref,
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
def test_parse_concept_ref_matches_code_before_sentence_period():
    # the LLM commonly ends with a period — the trailing '.' is NOT a code continuation
    candidates = [
        {"code": "F32.0", "display": "lehká depresivní fáze", "system": MKN10_SYSTEM}
    ]
    assert parse_concept_ref("Kód je F32.0.", candidates) == [
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


# --- resolve cache + wiring helpers (spec 009) ------------------------------------------------


@pytest.mark.offline
@pytest.mark.parametrize(
    "node_type,expected",
    [
        ("drug", True),
        ("Medication", True),
        ("CONDITION", True),
        ("diagnosis", True),
        ("symptom", True),
        ("procedure", True),
        ("labtest", True),
        ("person", False),
        ("organization", False),
        ("concept", False),
        ("other", False),
        ("table", False),
        ("", False),
        (None, False),
    ],
)
def test_is_clinical_type(node_type, expected):
    assert is_clinical_type(node_type) is expected


@pytest.mark.offline
def test_resolve_cache_key_normalizes_and_distinguishes():
    base = resolve_cache_key("Deprese", "condition", "porucha nálady")
    # case + surrounding/collapsed whitespace do not change the key
    assert base == resolve_cache_key("  deprese ", "Condition", "porucha   nálady")
    # any material field change does
    assert base != resolve_cache_key("Deprese", "condition", "jiný popis")
    assert base != resolve_cache_key("Úzkost", "condition", "porucha nálady")
    assert base != resolve_cache_key("Deprese", "symptom", "porucha nálady")


@pytest.mark.offline
def test_load_resolve_cache_missing_is_empty(tmp_path):
    assert load_resolve_cache(str(tmp_path / "nope.jsonl")) == {}


@pytest.mark.offline
def test_resolve_cache_roundtrip_and_skips_corrupt_line(tmp_path):
    path = str(tmp_path / "resolve_cache.jsonl")
    ref = [{"system": MKN10_SYSTEM, "code": "F32.0", "display": "d"}]
    append_resolve_cache(path, "k1", ref)
    append_resolve_cache(path, "k2", [])
    # a hand-corrupted / partial line must not abort the load
    with open(path, "a", encoding="utf-8") as f:
        f.write("{not json\n")
    cache = load_resolve_cache(path)
    assert cache == {"k1": ref, "k2": []}


@pytest.mark.offline
async def test_ground_entity_cached_hit_calls_nothing(tmp_path):
    entity = {"name": "amlodipin", "type": "drug", "description": "blokátor Ca"}
    key = resolve_cache_key("amlodipin", "drug", "blokátor Ca")
    cached = [{"system": ATC_SYSTEM, "code": "C08CA01", "display": "AMLODIPIN"}]
    cache = {key: cached}

    async def api(url, headers):  # pragma: no cover - must not be called
        raise AssertionError("neural-search called on a cache hit")

    async def llm_func(prompt):  # pragma: no cover - must not be called
        raise AssertionError("llm_func called on a cache hit")

    got = await ground_entity_cached(
        entity,
        "kontext",
        cache=cache,
        cache_path=str(tmp_path / "c.jsonl"),
        llm_func=llm_func,
        neural_base="https://mkn10.example",
        api=api,
    )
    assert got == cached


@pytest.mark.offline
async def test_ground_entity_cached_miss_grounds_appends_then_hits(tmp_path):
    path = str(tmp_path / "c.jsonl")
    cache: dict = {}
    calls = {"api": 0, "llm": 0}

    async def api(url, headers):
        calls["api"] += 1
        return {"results": [{"atc5": "C08CA01", "inn": "AMLODIPIN", "score_fused": 0.03}]}

    async def llm_func(prompt):
        calls["llm"] += 1
        return "C08CA01"

    entity = {"name": "amlodipin", "type": "drug", "description": "blokátor Ca"}
    args = dict(
        cache=cache,
        cache_path=path,
        llm_func=llm_func,
        neural_base="https://mkn10.example",
        api=api,
    )

    first = await ground_entity_cached(entity, "kontext", **args)
    assert first == [{"system": ATC_SYSTEM, "code": "C08CA01", "display": "AMLODIPIN"}]
    assert calls == {"api": 1, "llm": 1}
    # persisted to the file AND held in the in-run cache
    assert load_resolve_cache(path) == {
        resolve_cache_key("amlodipin", "drug", "blokátor Ca"): first
    }

    second = await ground_entity_cached(entity, "kontext", **args)
    assert second == first
    assert calls == {"api": 1, "llm": 1}  # no new calls on the hit


# --- verify-or-abstain (spec 010) ------------------------------------------------------------


@pytest.mark.offline
def test_build_verify_prompt_carries_code_and_asks_keep_drop():
    prompt = build_verify_prompt(
        "Spánková deprivace", "procedure", "léčebná metoda",
        {"code": "T73.9", "display": "Účinky strádání NS"}, "léčba deprese",
    )
    assert "T73.9" in prompt and "Účinky strádání NS" in prompt
    assert "Spánková deprivace" in prompt
    assert "KEEP" in prompt and "DROP" in prompt


@pytest.mark.offline
@pytest.mark.parametrize(
    "text,expected",
    [
        ("KEEP | kód sedí", True),
        ("keep", True),
        ("DROP | špatná kategorie", False),
        ("Nejasné", False),   # not clearly KEEP → abstain
        ("", False),
        (None, False),
    ],
)
def test_parse_verdict(text, expected):
    assert parse_verdict(text) is expected


@pytest.mark.offline
async def test_verify_concept_ref_keep_and_drop():
    ref = {"system": MKN10_SYSTEM, "code": "F32.8", "display": "d"}

    async def keeper(prompt):
        return "KEEP | ok"

    async def dropper(prompt):
        return "DROP | ne"

    assert await verify_concept_ref({"name": "Deprese", "type": "condition"}, ref, "ctx", verify_llm_func=keeper) is True
    assert await verify_concept_ref({"name": "Deprese", "type": "condition"}, ref, "ctx", verify_llm_func=dropper) is False


@pytest.mark.offline
async def test_ground_entity_verify_keeps_and_drops_and_swallows_error():
    async def api(url, headers):
        return {"results": [{"code": "F32.8", "name_cs": "Jiné dep. fáze", "score_fused": 0.03}]}

    async def pick(prompt):
        return "F32.8"

    base = dict(llm_func=pick, neural_base="https://mkn10.example", api=api)
    entity = {"name": "Deprese", "type": "condition", "description": "porucha nálady"}

    # no verifier → back-compat: the picked ref is kept
    assert await ground_entity(entity, "ctx", **base) == [
        {"system": MKN10_SYSTEM, "code": "F32.8", "display": "Jiné dep. fáze"}
    ]

    async def keep(_):
        return "KEEP | ok"

    async def drop(_):
        return "DROP | ne"

    async def boom(_):
        raise RuntimeError("judge down")

    got = await ground_entity(entity, "ctx", **base, verify_llm_func=keep)
    assert got and got[0]["code"] == "F32.8"                     # KEEP → kept
    assert await ground_entity(entity, "ctx", **base, verify_llm_func=drop) == []   # DROP → abstain
    assert await ground_entity(entity, "ctx", **base, verify_llm_func=boom) == []   # error → abstain


@pytest.mark.offline
async def test_ground_entity_cached_caches_verified_result(tmp_path):
    calls = {"api": 0, "pick": 0, "verify": 0}

    async def api(url, headers):
        calls["api"] += 1
        return {"results": [{"code": "F32.8", "name_cs": "d", "score_fused": 0.03}]}

    async def pick(_):
        calls["pick"] += 1
        return "F32.8"

    async def drop(_):
        calls["verify"] += 1
        return "DROP | ne"

    entity = {"name": "Deprese", "type": "condition", "description": "d"}
    cache: dict = {}
    args = dict(cache=cache, cache_path=str(tmp_path / "c.jsonl"),
                llm_func=pick, neural_base="https://mkn10.example", api=api, verify_llm_func=drop)

    first = await ground_entity_cached(entity, "ctx", **args)
    assert first == []                                  # dropped by the judge → abstain, cached
    assert calls == {"api": 1, "pick": 1, "verify": 1}
    second = await ground_entity_cached(entity, "ctx", **args)
    assert second == []
    assert calls == {"api": 1, "pick": 1, "verify": 1}  # cache hit — no new pick/verify
