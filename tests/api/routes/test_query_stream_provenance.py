"""Section-crop provenance on the chat path (spec 004).

The webpage guidelines chat consumes ``/query/stream`` (``ReferenceItem``), not
``:retrieve`` (``RetrievedPassage``). These tests pin that the chat references now
carry the same per-chunk ``{text, page, section, crop_url, pdf_url}`` provenance the
retrieve path serves, and that a chunk with no substrate degrades to text only.

Pure/offline: ``aquery_llm`` + the chunk store are stubbed — no LLM/DB/network.
"""

import importlib
import json
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import under a clean argv: the api routers pull in lightrag.api.{auth,config},
# which parse_args() at import time and would choke on pytest's argv.
_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
_query_routes = importlib.import_module("lightrag.api.routers.query_routes")
_passage_links = importlib.import_module("lightrag.sidecar.passage_links")
sys.argv = _original_argv

create_query_routes = _query_routes.create_query_routes

pytestmark = pytest.mark.offline

# --- fixtures (mirror the spec-004 R2 retrieve fixtures) ---
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
    """Minimal rag whose ``aquery_llm`` returns canned references + chunks (no retrieval, no LLM).

    ``chunk_record`` (optional) is what ``text_chunks.get_by_id`` returns — set it to exercise the
    provenance path; omit it to leave ``text_chunks`` absent (degrade path)."""

    def __init__(self, references, chunks, *, chunk_record=None, response="answer"):
        self._references = references
        self._chunks = chunks
        self._response = response
        if chunk_record is not None:
            self.text_chunks = _TextChunks(chunk_record)

    async def aquery_llm(self, query, param):
        async def _iter():
            yield self._response

        return {
            "data": {"references": self._references, "chunks": self._chunks},
            "llm_response": {"is_streaming": True, "response_iterator": _iter()},
        }


def _client(rag):
    app = FastAPI()
    app.include_router(create_query_routes(rag, api_key=None))
    return TestClient(app)


def _stream(rag, **body):
    body.setdefault("query", "léčba arteriální hypertenze")
    body.setdefault("stream", True)
    body.setdefault("include_references", True)
    body.setdefault("include_chunk_content", True)
    r = _client(rag).post("/query/stream", json=body)
    assert r.status_code == 200
    lines = [json.loads(ln) for ln in r.text.splitlines() if ln.strip()]
    return lines


def _refs_line(lines):
    return next(ln for ln in lines if "references" in ln)["references"]


def test_chat_reference_carries_section_crop_provenance(monkeypatch):
    monkeypatch.setattr(_passage_links, "load_blocks_for_doc", lambda _fp: _BLOCKS_BY_ID)
    rag = StubRag(
        references=[{"reference_id": "1", "file_path": "Arteriální hypertenze_2008.pdf"}],
        chunks=[
            {
                "reference_id": "1",
                "content": "Cílový TK < 140/90.",
                "file_path": "Arteriální hypertenze_2008.pdf",
                "chunk_id": "c1",
            }
        ],
        chunk_record={"sidecar": _SIDECAR},
    )
    refs = _refs_line(_stream(rag))
    assert len(refs) == 1
    ref = refs[0]
    # content preserved for back-compat
    assert ref["content"] == ["Cílový TK < 140/90."]
    # new: per-chunk provenance
    chunks = ref["chunks"]
    assert len(chunks) == 1
    c = chunks[0]
    assert c["text"] == "Cílový TK < 140/90."
    assert c["page"] == "13"
    assert c["section"] == "Arteriální hypertenze › Léčba"
    assert c["bbox"] == [75.0, 481.0, 443.0, 500.0]
    assert c["crop_url"] == "/v1/guidelines/section-crop?chunk_id=c1"
    assert c["pdf_url"] == "/v1/guidelines/pdf?doc=Arteri%C3%A1ln%C3%AD+hypertenze_2008.pdf"


def test_multiple_spans_from_one_file_yield_multiple_chunks(monkeypatch):
    monkeypatch.setattr(_passage_links, "load_blocks_for_doc", lambda _fp: _BLOCKS_BY_ID)
    rag = StubRag(
        references=[{"reference_id": "1", "file_path": "Arteriální hypertenze_2008.pdf"}],
        chunks=[
            {"reference_id": "1", "content": "span A", "file_path": "Arteriální hypertenze_2008.pdf", "chunk_id": "c1"},
            {"reference_id": "1", "content": "span B", "file_path": "Arteriální hypertenze_2008.pdf", "chunk_id": "c2"},
        ],
        chunk_record={"sidecar": _SIDECAR},
    )
    ref = _refs_line(_stream(rag))[0]
    assert [c["text"] for c in ref["chunks"]] == ["span A", "span B"]
    assert [c["crop_url"] for c in ref["chunks"]] == [
        "/v1/guidelines/section-crop?chunk_id=c1",
        "/v1/guidelines/section-crop?chunk_id=c2",
    ]


def test_degrades_to_text_only_without_substrate():
    # No text_chunks store on the rag → provenance can't resolve → text kept, page/crop null.
    rag = StubRag(
        references=[{"reference_id": "1", "file_path": "Foo_2021.pdf"}],
        chunks=[{"reference_id": "1", "content": "span", "file_path": "Foo_2021.pdf", "chunk_id": "c1"}],
    )
    c = _refs_line(_stream(rag))[0]["chunks"][0]
    assert c["text"] == "span"
    assert c["page"] is None and c["section"] is None and c["bbox"] is None
    assert c["crop_url"] is None  # no page ⇒ no crop link
    assert c["pdf_url"] == "/v1/guidelines/pdf?doc=Foo_2021.pdf"  # PDF offered whenever file known


def test_missing_chunk_id_does_not_resolve_provenance(monkeypatch):
    # Store would resolve ANY id, but a chunk with no chunk_id must not hit it (no bogus page).
    monkeypatch.setattr(_passage_links, "load_blocks_for_doc", lambda _fp: _BLOCKS_BY_ID)
    rag = StubRag(
        references=[{"reference_id": "1", "file_path": "Foo_2021.pdf"}],
        chunks=[{"reference_id": "1", "content": "span", "file_path": "Foo_2021.pdf"}],  # no chunk_id
        chunk_record={"sidecar": _SIDECAR},
    )
    c = _refs_line(_stream(rag))[0]["chunks"][0]
    assert c["text"] == "span"
    assert c["page"] is None and c["crop_url"] is None


def test_query_nonstream_references_carry_provenance(monkeypatch):
    # The /query (non-stream) path serializes through QueryResponse/ReferenceItem (Pydantic model),
    # not the raw-dict stream path — pin that the nested chunks survive model coercion (a silent drop
    # here would give the FE content but no crops with no error).
    monkeypatch.setattr(_passage_links, "load_blocks_for_doc", lambda _fp: _BLOCKS_BY_ID)
    rag = StubRag(
        references=[{"reference_id": "1", "file_path": "Arteriální hypertenze_2008.pdf"}],
        chunks=[
            {
                "reference_id": "1",
                "content": "Cílový TK < 140/90.",
                "file_path": "Arteriální hypertenze_2008.pdf",
                "chunk_id": "c1",
            }
        ],
        chunk_record={"sidecar": _SIDECAR},
    )
    r = _client(rag).post(
        "/query",
        json={"query": "léčba arteriální hypertenze", "include_references": True,
              "include_chunk_content": True},
    )
    assert r.status_code == 200
    refs = r.json()["references"]
    assert len(refs) == 1
    chunks = refs[0]["chunks"]
    assert len(chunks) == 1
    c = chunks[0]
    assert c["text"] == "Cílový TK < 140/90."
    assert c["page"] == "13"
    assert c["section"] == "Arteriální hypertenze › Léčba"
    assert c["crop_url"] == "/v1/guidelines/section-crop?chunk_id=c1"


def test_no_chunks_field_when_chunk_content_not_requested():
    rag = StubRag(
        references=[{"reference_id": "1", "file_path": "Foo_2021.pdf"}],
        chunks=[{"reference_id": "1", "content": "span", "file_path": "Foo_2021.pdf", "chunk_id": "c1"}],
    )
    ref = _refs_line(_stream(rag, include_chunk_content=False))[0]
    assert ref.get("content") is None
    assert ref.get("chunks") is None
