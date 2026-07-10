"""Unit tests for the single-document re-extract probe (LightRAG.areextract_document).

The LLM extraction itself is monkeypatched — these cover the plumbing: chunk fetch by
doc_id, the per-call entity_types_guidance override + restore, result serialization, and
the not-found / no-chunks error paths. No store, no LLM.
"""

import types

import pytest

import lightrag.lightrag as lr_mod
from lightrag.addon_params import ObservableAddonParams
from lightrag.lightrag import LightRAG


class _KV:
    def __init__(self, data):
        self._d = data

    async def get_by_id(self, k):
        return self._d.get(k)

    async def get_by_ids(self, ids):
        return [self._d.get(i) for i in ids]


def _fake_rag(doc, chunks, addon=None):
    fake = types.SimpleNamespace()
    fake.doc_status = _KV({"d1": doc} if doc is not None else {})
    fake.text_chunks = _KV(chunks)
    fake.addon_params = ObservableAddonParams(addon or {}, on_change=lambda: None)
    fake.llm_response_cache = None
    fake._build_global_config = lambda: {"addon_params": dict(fake.addon_params)}
    return fake


@pytest.mark.offline
async def test_areextract_returns_entities_and_restores_override(monkeypatch):
    captured = {}

    async def fake_extract(chunks, global_config, **kw):
        profile = global_config.get("_entity_extraction_prompt_profile") or {}
        captured["guidance"] = profile.get("entity_types_guidance")
        captured["chunk_ids"] = list(chunks)
        return [
            (
                {"Hypertenze": [{"entity_type": "condition", "description": "desc"}]},
                {("Hypertenze", "Ramipril"): [{"keywords": "treats", "description": "d"}]},
            )
        ]

    monkeypatch.setattr(lr_mod, "extract_entities", fake_extract)
    fake = _fake_rag(
        {"chunks_list": ["c1", "c2"]},
        {"c1": {"content": "a"}, "c2": {"content": "b"}},
        addon={"entity_types_guidance": "ORIG"},
    )

    out = await LightRAG.areextract_document(fake, "d1", entity_types_guidance="TIGHT")

    assert out["doc_id"] == "d1"
    assert out["chunks"] == 2
    assert out["entity_count"] == 1 and out["relation_count"] == 1
    assert out["entities"][0] == {
        "name": "Hypertenze",
        "type": "condition",
        "description": "desc",
    }
    assert out["relations"][0]["source"] == "Hypertenze"
    # the override reached extraction via the injected prompt profile...
    assert captured["guidance"] == "TIGHT"
    assert captured["chunk_ids"] == ["c1", "c2"]
    # ...without ever mutating the shared addon_params (no concurrent-probe race)
    assert fake.addon_params["entity_types_guidance"] == "ORIG"


@pytest.mark.offline
async def test_areextract_no_override_leaves_addon_untouched(monkeypatch):
    async def fake_extract(chunks, global_config, **kw):
        return [({}, {})]

    monkeypatch.setattr(lr_mod, "extract_entities", fake_extract)
    fake = _fake_rag({"chunks_list": ["c1"]}, {"c1": {"content": "a"}}, addon={})

    out = await LightRAG.areextract_document(fake, "d1")

    assert out["entity_count"] == 0
    assert "entity_types_guidance" not in fake.addon_params


@pytest.mark.offline
async def test_areextract_missing_doc_raises():
    fake = _fake_rag(None, {})
    with pytest.raises(ValueError, match="document not found"):
        await LightRAG.areextract_document(fake, "nope")


@pytest.mark.offline
async def test_areextract_no_chunks_raises():
    fake = _fake_rag({"chunks_list": []}, {})
    with pytest.raises(ValueError, match="no stored chunks"):
        await LightRAG.areextract_document(fake, "d1")
