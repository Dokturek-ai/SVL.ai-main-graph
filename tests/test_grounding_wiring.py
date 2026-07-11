"""Unit tests for the extract-path grounding hook (lightrag.operate._maybe_ground_concept_ref, spec 009).

Covers the gate (default-off), the clinical-type filter, the JSON-encode of a hit, the abstain
short-circuit, and the best-effort swallow of a grounding error. `ground_entity_cached` is
monkeypatched so no LLM / no network is touched.
"""

import pytest

from lightrag import operate
from lightrag.grounding import ATC_SYSTEM


def _config(enabled: bool):
    async def _extract_llm(prompt):  # never actually invoked (ground_entity_cached is mocked)
        return ""

    cfg = {"role_llm_funcs": {"extract": _extract_llm}}
    if enabled:
        cfg["_concept_ref_grounding"] = {
            "enabled": True,
            "neural_base": "https://mkn10.example",
            "cache_path": "/tmp/does-not-matter.jsonl",
            "cache": {},
        }
    else:
        cfg["_concept_ref_grounding"] = {"enabled": False}
    return cfg


def _patch_ground(monkeypatch, *, returns=None, raises=None, calls=None):
    async def fake(entity, doc_context, **kwargs):
        if calls is not None:
            calls.append({"entity": entity, "doc_context": doc_context, **kwargs})
        if raises is not None:
            raise raises
        return returns

    monkeypatch.setattr(operate, "ground_entity_cached", fake)


@pytest.mark.offline
async def test_disabled_returns_none_and_does_not_ground(monkeypatch):
    calls = []
    _patch_ground(monkeypatch, returns=[{"x": 1}], calls=calls)
    got = await operate._maybe_ground_concept_ref(
        "Deprese", "condition", "porucha nálady", _config(enabled=False)
    )
    assert got is None
    assert calls == []


@pytest.mark.offline
async def test_non_clinical_type_is_skipped(monkeypatch):
    calls = []
    _patch_ground(monkeypatch, returns=[{"x": 1}], calls=calls)
    got = await operate._maybe_ground_concept_ref(
        "ISBN 978-80", "other", "identifikátor", _config(enabled=True)
    )
    assert got is None
    assert calls == []


@pytest.mark.offline
async def test_clinical_hit_returns_json_and_passes_context(monkeypatch):
    calls = []
    refs = [{"system": ATC_SYSTEM, "code": "C08CA01", "display": "AMLODIPIN"}]
    _patch_ground(monkeypatch, returns=refs, calls=calls)
    cfg = _config(enabled=True)
    got = await operate._maybe_ground_concept_ref(
        "amlodipin", "drug", "blokátor Ca", cfg
    )
    import json

    assert json.loads(got) == refs
    # the merged description is passed as both the entity description AND the doc_context
    assert calls[0]["entity"] == {
        "name": "amlodipin",
        "type": "drug",
        "description": "blokátor Ca",
    }
    assert calls[0]["doc_context"] == "blokátor Ca"
    assert calls[0]["neural_base"] == "https://mkn10.example"
    assert calls[0]["cache"] is cfg["_concept_ref_grounding"]["cache"]


@pytest.mark.offline
async def test_clinical_abstain_returns_none(monkeypatch):
    _patch_ground(monkeypatch, returns=[])
    got = await operate._maybe_ground_concept_ref(
        "Nejasný pojem", "condition", "popis", _config(enabled=True)
    )
    assert got is None


@pytest.mark.offline
async def test_grounding_error_is_swallowed(monkeypatch):
    _patch_ground(monkeypatch, raises=RuntimeError("mkn10 down"))
    got = await operate._maybe_ground_concept_ref(
        "Deprese", "condition", "popis", _config(enabled=True)
    )
    assert got is None  # best-effort: a failure never blocks the upsert
