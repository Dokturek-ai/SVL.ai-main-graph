"""Unit tests for LightRAG.areextract_document_commit (spec 012) — the grounding-backfill commit path.

Calls the method UNBOUND on a minimal fake ``self`` so no real LightRAG/storage/LLM is constructed; the
module-level ``extract_entities`` / ``merge_nodes_and_edges`` / namespace helpers are monkeypatched. Covers:
the happy path calls extract → merge → flush with the doc's chunks, and a busy pipeline is refused.
"""

import asyncio

import pytest

from lightrag.lightrag import LightRAG


class _AsyncKV:
    def __init__(self, by_id=None, by_ids=None):
        self._by_id = by_id or {}
        self._by_ids = by_ids or {}

    async def get_by_id(self, k):
        return self._by_id.get(k)

    async def get_by_ids(self, ks):
        return [self._by_ids.get(k) for k in ks]


def _fake_self():
    """A stand-in with just the attributes areextract_document_commit touches."""
    ns = type("NS", (), {})()
    ns.workspace = "ws"
    ns.doc_status = _AsyncKV(by_id={"d1": {"file_path": "Deprese_2023.pdf", "chunks_list": ["c1", "c2"]}})
    ns.text_chunks = _AsyncKV(by_ids={"c1": {"content": "a"}, "c2": {"content": "b"}})
    for attr in ("chunk_entity_relation_graph", "entities_vdb", "relationships_vdb",
                 "full_entities", "full_relations", "entity_chunks", "relation_chunks",
                 "llm_response_cache"):
        setattr(ns, attr, object())
    ns._build_global_config = lambda: {}
    ns._insert_done_calls = []

    async def _insert_done():
        ns._insert_done_calls.append(True)

    ns._insert_done = _insert_done
    return ns


def _patch(monkeypatch, *, busy=False, calls=None):
    calls = calls if calls is not None else {}
    status = {"busy": busy, "job_name": "ingest" if busy else None, "history_messages": []}

    async def _get_ns(name, workspace=None):
        return status

    # the method does `from lightrag.kg.shared_storage import …` at call time → patch the source module
    monkeypatch.setattr("lightrag.kg.shared_storage.get_namespace_data", _get_ns, raising=False)
    monkeypatch.setattr("lightrag.kg.shared_storage.get_namespace_lock",
                        lambda name, workspace=None: asyncio.Lock(), raising=False)

    async def _extract(chunks, **kw):
        calls["extract"] = list(chunks.keys())
        # one node + one edge across the "chunks"
        return [({"Deprese": [{"entity_type": "diagnosis"}]}, {("Deprese", "SSRI"): [{}]})]

    async def _merge(**kw):
        calls["merge"] = kw

    monkeypatch.setattr("lightrag.operate.extract_entities", _extract, raising=False)
    monkeypatch.setattr("lightrag.operate.merge_nodes_and_edges", _merge, raising=False)
    return calls, status


@pytest.mark.offline
async def test_commit_runs_extract_merge_flush(monkeypatch):
    calls, status = _patch(monkeypatch)
    me = _fake_self()
    out = await LightRAG.areextract_document_commit(me, "d1")

    assert calls["extract"] == ["c1", "c2"]  # extracted the doc's stored chunks
    assert "merge" in calls  # merge (grounds + persists) ran
    assert calls["merge"]["doc_id"] == "d1"
    assert calls["merge"]["knowledge_graph_inst"] is me.chunk_entity_relation_graph
    assert me._insert_done_calls == [True]  # flushed
    assert out == {"doc_id": "d1", "file_path": "Deprese_2023.pdf", "chunks": 2,
                   "entity_count": 1, "relation_count": 1, "committed": True}
    assert status["busy"] is False  # released


@pytest.mark.offline
async def test_commit_refuses_when_pipeline_busy(monkeypatch):
    calls, _ = _patch(monkeypatch, busy=True)
    me = _fake_self()
    with pytest.raises(RuntimeError, match="busy"):
        await LightRAG.areextract_document_commit(me, "d1")
    assert "extract" not in calls and "merge" not in calls  # never touched the graph


@pytest.mark.offline
async def test_commit_404s_on_missing_doc(monkeypatch):
    _patch(monkeypatch)
    me = _fake_self()
    with pytest.raises(ValueError, match="not found"):
        await LightRAG.areextract_document_commit(me, "nope")
