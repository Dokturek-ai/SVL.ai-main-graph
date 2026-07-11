"""Tests for the focused guideline retrieve endpoint (spec 002).

Pure/offline: `aquery_data` is stubbed, no LLM/DB/network. Exercises the router's
shaping, the top_k cap, citation formatting, concept_ref echo, and the resilient
empty-result path.
"""

import importlib
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the router under a clean argv: importing the api routers pulls in
# lightrag.api.{auth,config}, which parse_args() at import time and would choke
# on pytest's argv (see tests/api/routes/test_document_routes_paginated.py).
_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
_guidelines_routes = importlib.import_module("lightrag.api.routers.guidelines_routes")
sys.argv = _original_argv

create_guidelines_routes = _guidelines_routes.create_guidelines_routes
_edition_from_filename = _guidelines_routes._edition_from_filename
_passage_provenance = _guidelines_routes._passage_provenance

pytestmark = pytest.mark.offline

# --- section-crop provenance fixtures (spec 004 R2) ---
_BLOCK = {
    "type": "content", "blockid": "b1", "content": "x", "heading": "Léčba",
    "parent_headings": ["Arteriální hypertenze"],
    "positions": [{"type": "bbox", "anchor": "13", "range": [75.0, 481.0, 443.0, 500.0]}],
}
_BLOCKS_BY_ID = {"b1": _BLOCK}
_SIDECAR = {"type": "block", "id": "b1", "refs": [{"type": "block", "id": "b1"}]}


class _TextChunks:
    def __init__(self, rec):
        self.rec = rec

    async def get_by_id(self, chunk_id):
        return self.rec


class StubRag:
    """Minimal rag whose aquery_data returns canned chunks (no retrieval).

    ``chunk_record`` (optional) is what ``text_chunks.get_by_id`` returns — set it to exercise the
    section-crop provenance path; omit it to leave `text_chunks` absent (degrade path)."""

    def __init__(self, chunks, chunk_record=None):
        self._chunks = chunks
        self.calls = []
        if chunk_record is not None:
            self.text_chunks = _TextChunks(chunk_record)

    async def aquery_data(self, query, param):
        self.calls.append((query, param))
        return {"status": "success", "data": {"chunks": self._chunks}, "metadata": {}}


def _chunk(content, file_path, chunk_id, score=None):
    c = {"content": content, "file_path": file_path, "chunk_id": chunk_id, "reference_id": "1"}
    if score is not None:
        c["score"] = score
    return c


def make_client(chunks):
    app = FastAPI()
    app.include_router(create_guidelines_routes(StubRag(chunks), api_key=None))
    return TestClient(app)


def _post(client, **body):
    body.setdefault("query", "diagnostická kritéria arteriální hypertenze")
    return client.post("/v1/guidelines:retrieve", json=body)


def test_edition_from_filename():
    assert _edition_from_filename("Arteriální hypertenze_2024.md") == "2024"
    assert _edition_from_filename("Foo_unknown.md") == "unknown"
    assert _edition_from_filename("Bar.md") == "unknown"
    assert _edition_from_filename("") == "unknown"
    # bounded by a separator: path form + trailing underscore resolve; longer digit runs do not
    assert _edition_from_filename("guidelines/Arteriální hypertenze_2024/chunk.md") == "2024"
    assert _edition_from_filename("Foo_2024_v2.md") == "2024"
    assert _edition_from_filename("Foo_20241.md") == "unknown"
    assert _edition_from_filename("Foo_20240101.md") == "unknown"


def test_caps_to_top_k():
    chunks = [_chunk(f"span {i}", "Arteriální hypertenze_2024.md", f"c{i}") for i in range(8)]
    client = make_client(chunks)
    r = _post(client, top_k=3)
    assert r.status_code == 200
    assert len(r.json()["passages"]) == 3


def test_passage_shape_and_citation():
    chunks = [_chunk("Cílový TK < 140/90.", "Arteriální hypertenze_2024.md", "cabc", score=0.83)]
    client = make_client(chunks)
    p = _post(client, top_k=5).json()["passages"][0]
    assert p["text"] == "Cílový TK < 140/90."
    assert p["citation"] == "Arteriální hypertenze_2024.md#chunk=cabc@2024"
    assert p["score"] == 0.83
    assert p["facet"] is None and p["concept_ref"] is None


def test_citation_unknown_edition():
    chunks = [_chunk("x", "Nezname.md", "c1")]
    p = _post(make_client(chunks), top_k=1).json()["passages"][0]
    assert p["citation"].endswith("@unknown")


def test_score_absent_is_null():
    chunks = [_chunk("x", "Foo_2020.md", "c1")]  # no score key
    p = _post(make_client(chunks), top_k=1).json()["passages"][0]
    assert p["score"] is None


def test_concept_ref_echoed_and_not_filtered():
    chunks = [_chunk("x", "Foo_2020.md", "c1")]
    body = {"top_k": 1, "concept_ref": {"mkn10_code": "I10"}, "facet": "diagnosis"}
    data = _post(make_client(chunks), **body).json()
    assert data["concept_ref"] == {"mkn10_code": "I10", "cui": None}
    assert data["filtered"] is False


def test_empty_retrieval_returns_empty_not_error():
    client = make_client([])
    r = _post(client, top_k=5)
    assert r.status_code == 200
    assert r.json()["passages"] == []


def test_facet_and_concept_ref_are_noop_v1():
    """Supplying filters must not change results vs not supplying them (v1 no-op)."""
    chunks = [_chunk(f"span {i}", "Foo_2021.md", f"c{i}") for i in range(4)]
    plain = _post(make_client(chunks), top_k=4).json()["passages"]
    filtered = _post(
        make_client(chunks), top_k=4, facet="dosing", concept_ref={"cui": "C0020538"}
    ).json()["passages"]
    assert plain == filtered


def test_content_missing_chunk_skipped():
    chunks = [{"file_path": "Foo_2021.md", "chunk_id": "c1", "reference_id": "1"}]  # no content
    r = _post(make_client(chunks), top_k=5)
    assert r.status_code == 200
    assert r.json()["passages"] == []


# --- section-crop provenance (spec 004 R2) ---


class _Rag:
    def __init__(self, rec):
        self.text_chunks = _TextChunks(rec)


async def test_passage_provenance_resolves_page_section_bbox():
    got = await _passage_provenance(
        _Rag({"sidecar": _SIDECAR}), "c1", "Arteriální hypertenze_2008.pdf", {},
        load_blocks=lambda _fp: _BLOCKS_BY_ID,
    )
    assert got["page"] == "13"
    assert got["section"] == "Arteriální hypertenze › Léčba"
    assert got["bbox"] == [75.0, 481.0, 443.0, 500.0]


async def test_passage_provenance_no_sidecar_is_none():
    got = await _passage_provenance(
        _Rag({"content": "x"}), "c1", "f", {}, load_blocks=lambda _fp: _BLOCKS_BY_ID
    )
    assert got is None


async def test_passage_provenance_no_blocks_is_none():
    got = await _passage_provenance(
        _Rag({"sidecar": _SIDECAR}), "c1", "f", {}, load_blocks=lambda _fp: None
    )
    assert got is None


def test_retrieve_populates_provenance(monkeypatch):
    monkeypatch.setattr(_guidelines_routes, "_load_blocks_for_doc", lambda _fp: _BLOCKS_BY_ID)
    rag = StubRag(
        [_chunk("span", "Arteriální hypertenze_2008.pdf", "c1")],
        chunk_record={"sidecar": _SIDECAR},
    )
    app = FastAPI()
    app.include_router(create_guidelines_routes(rag, api_key=None))
    p = TestClient(app).post(
        "/v1/guidelines:retrieve", json={"query": "léčba hypertenze", "top_k": 1}
    ).json()["passages"][0]
    assert p["page"] == "13"
    assert p["section"] == "Arteriální hypertenze › Léčba"
    assert p["bbox"] == [75.0, 481.0, 443.0, 500.0]
    assert p["crop_url"] is None and p["pdf_url"] is None  # gated on PDF upload


def test_retrieve_provenance_degrades_when_no_substrate():
    # StubRag with no text_chunks store → provenance fields null, citation unchanged
    p = _post(make_client([_chunk("x", "Foo_2021.md", "c1")]), top_k=1).json()["passages"][0]
    assert p["page"] is None and p["section"] is None and p["bbox"] is None
