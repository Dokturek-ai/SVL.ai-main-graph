"""Spec 018 — `section-crop` `&page=N` override for a multi-page chunk.

Offline route tests: `_load_blocks_for_doc`, `_render_section_crop`, and `configured_input_dir` are
stubbed, so no PDF / PyMuPDF / DB. Asserts the page the handler asks the renderer to draw and whether the
bbox highlight is passed (primary page only).
"""

import importlib
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the router under a clean argv (parse_args at import time chokes on pytest argv).
_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
_guidelines_routes = importlib.import_module("lightrag.api.routers.guidelines_routes")
sys.argv = _original_argv

create_guidelines_routes = _guidelines_routes.create_guidelines_routes

pytestmark = pytest.mark.offline

_FILE = "Arteriální hypertenze_2008.pdf"
_BBOX = [75.0, 481.0, 443.0, 500.0]
# chunk spans a page break: b1 on page 12 (primary, has the box), b2 on page 13 (continuation).
_BLOCKS = {
    "b1": {
        "type": "content", "blockid": "b1", "content": "x", "heading": "Léčba",
        "parent_headings": ["Arteriální hypertenze"],
        "positions": [{"type": "bbox", "anchor": "12", "range": _BBOX}],
    },
    "b2": {
        "type": "content", "blockid": "b2", "content": "y", "heading": "Léčba",
        "parent_headings": ["Arteriální hypertenze"],
        "positions": [{"type": "bbox", "anchor": "13", "range": [10.0, 20.0, 30.0, 40.0]}],
    },
}
_SIDECAR = {"type": "block", "id": "b1", "refs": [{"type": "block", "id": "b1"}, {"type": "block", "id": "b2"}]}


class _TextChunks:
    def __init__(self, rec):
        self.rec = rec

    async def get_by_id(self, _chunk_id):
        return self.rec


class _Rag:
    def __init__(self, rec):
        self.text_chunks = _TextChunks(rec)


def _client(monkeypatch, tmp_path, calls, *, sidecar=_SIDECAR, file_path=_FILE):
    monkeypatch.setattr(_guidelines_routes, "_load_blocks_for_doc", lambda _fp: _BLOCKS)
    monkeypatch.setattr("lightrag.utils_pipeline.configured_input_dir", lambda: str(tmp_path))

    def _fake_render(pdf_path, page_number, bbox, *, scale=2.0):
        calls.append({"page": int(page_number), "bbox": bbox})
        return b"PNG-stub"

    monkeypatch.setattr(_guidelines_routes, "_render_section_crop", _fake_render)
    (tmp_path / file_path).write_bytes(b"%PDF-1.4 stub")
    rag = _Rag({"sidecar": sidecar, "file_path": file_path})
    app = FastAPI()
    app.include_router(create_guidelines_routes(rag, api_key=None))
    return TestClient(app)


def test_no_page_param_renders_primary_with_bbox(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/section-crop", params={"chunk_id": "c1"}
    )
    assert r.status_code == 200
    assert calls == [{"page": 12, "bbox": _BBOX}]


def test_page_equal_primary_keeps_bbox(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/section-crop", params={"chunk_id": "c1", "page": 12}
    )
    assert r.status_code == 200
    assert calls == [{"page": 12, "bbox": _BBOX}]


def test_secondary_page_renders_clean_no_bbox(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/section-crop", params={"chunk_id": "c1", "page": 13}
    )
    assert r.status_code == 200
    assert calls == [{"page": 13, "bbox": None}]


def test_page_not_in_chunk_pages_404(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/section-crop", params={"chunk_id": "c1", "page": 99}
    )
    assert r.status_code == 404
    assert calls == []  # never rendered


def test_no_sidecar_still_404(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls, sidecar=None).get(
        "/v1/guidelines/section-crop", params={"chunk_id": "c1", "page": 12}
    )
    assert r.status_code == 404
    assert calls == []
