"""`/v1/guidelines/pdf-page` — a plain rasterized page of a source PDF (no chunk, no highlight).

Offline route tests: `_render_section_crop` and `configured_input_dir` are stubbed, so no PDF /
PyMuPDF / DB. Asserts the page the handler asks the renderer to draw, that NO bbox is passed, and the
404 paths (non-pdf name, missing file, out-of-range page).
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


class _Rag:
    text_chunks = None  # pdf-page never touches chunks


def _client(monkeypatch, tmp_path, calls, *, render=None, write=_FILE):
    monkeypatch.setattr("lightrag.utils_pipeline.configured_input_dir", lambda: str(tmp_path))

    def _fake_render(pdf_path, page_number, bbox, *, scale=2.0):
        calls.append({"page": int(page_number), "bbox": bbox})
        if render is not None:
            return render(page_number)
        return b"PNG-stub"

    monkeypatch.setattr(_guidelines_routes, "_render_section_crop", _fake_render)
    if write:
        (tmp_path / write).write_bytes(b"%PDF-1.4 stub")
    app = FastAPI()
    app.include_router(create_guidelines_routes(_Rag(), api_key=None))
    return TestClient(app)


def test_default_page_renders_cover_no_bbox(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get("/v1/guidelines/pdf-page", params={"doc": _FILE})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert calls == [{"page": 1, "bbox": None}]  # page 1 = cover, never a highlight


def test_explicit_page_is_respected(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/pdf-page", params={"doc": _FILE, "page": 5}
    )
    assert r.status_code == 200
    assert calls == [{"page": 5, "bbox": None}]


def test_path_traversal_reduced_to_basename(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/pdf-page", params={"doc": f"../../{_FILE}"}
    )
    assert r.status_code == 200
    assert calls == [{"page": 1, "bbox": None}]


def test_non_pdf_name_404(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls, write="notes.txt").get(
        "/v1/guidelines/pdf-page", params={"doc": "notes.txt"}
    )
    assert r.status_code == 404
    assert calls == []


def test_missing_file_404(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls, write=None).get(
        "/v1/guidelines/pdf-page", params={"doc": _FILE}
    )
    assert r.status_code == 404
    assert calls == []


def test_page_out_of_range_404(tmp_path, monkeypatch):
    calls = []

    def _raise(_page):
        raise ValueError("page out of range")

    r = _client(monkeypatch, tmp_path, calls, render=_raise).get(
        "/v1/guidelines/pdf-page", params={"doc": _FILE, "page": 999}
    )
    assert r.status_code == 404
    assert calls == [{"page": 999, "bbox": None}]  # rendered, raised, mapped to 404


def test_page_zero_rejected_by_validation(tmp_path, monkeypatch):
    calls = []
    r = _client(monkeypatch, tmp_path, calls).get(
        "/v1/guidelines/pdf-page", params={"doc": _FILE, "page": 0}
    )
    assert r.status_code == 422  # ge=1 query validation
    assert calls == []
