import importlib
import sys

import pytest

# document_routes parses argv at import (server config); shield it from pytest's argv.
_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
_document_routes = importlib.import_module("lightrag.api.routers.document_routes")
sys.argv = _argv

pipeline_enqueue_file = _document_routes.pipeline_enqueue_file
PARSED_DIR_NAME = importlib.import_module("lightrag.constants").PARSED_DIR_NAME

pytestmark = pytest.mark.offline


class _FakeRag:
    """Records enqueue + error calls. The denylist guard returns before any other rag method."""

    def __init__(self):
        self.enqueued = []
        self.errors = []

    async def apipeline_enqueue_documents(self, *args, **kwargs):
        self.enqueued.append((args, kwargs))
        return kwargs.get("track_id")

    async def apipeline_enqueue_error_documents(self, error_files, track_id=None):
        self.errors.append((error_files, track_id))


async def test_denylisted_pdf_is_rejected_before_enqueue(tmp_path):
    file_path = tmp_path / "MANUÁL KÓDŮ PRO VPL_2026.pdf"
    file_path.write_bytes(b"%PDF-1.4 fake")
    rag = _FakeRag()

    success, track_id = await pipeline_enqueue_file(rag, file_path, "track-manual")

    assert success is False
    assert track_id == "track-manual"
    # never handed to the parse/extract pipeline -> no chunks/entities/relations
    assert rag.enqueued == []
    # rejection recorded as one error doc_status so a human sees why
    assert len(rag.errors) == 1
    error_files, err_track = rag.errors[0]
    assert err_track == "track-manual"
    assert len(error_files) == 1
    assert "Out-of-corpus document rejected" in error_files[0]["error_description"]
    assert "PRO VPL" in error_files[0]["original_error"]
    # source left untouched: not moved to the parsed dir, not renamed
    assert file_path.exists()
    assert not (tmp_path / PARSED_DIR_NAME).exists()


async def test_legit_pdf_is_not_rejected_by_denylist(tmp_path, monkeypatch):
    # A non-denylisted PDF must pass the guard. Stop right after by faking the edition
    # resolver to raise, so we assert the guard did NOT reject (no out-of-corpus error) without
    # invoking the real parser.
    monkeypatch.setattr(
        _document_routes,
        "_resolve_and_rename_edition",
        lambda p: (_ for _ in ()).throw(RuntimeError("stop-after-guard")),
    )
    file_path = tmp_path / "Akutní průjem_2023.pdf"
    file_path.write_bytes(b"%PDF-1.4 fake")
    rag = _FakeRag()

    success, _ = await pipeline_enqueue_file(rag, file_path, "track-ok")

    # guard passed -> the outer except records a generic error, NOT the out-of-corpus rejection
    assert success is False
    assert len(rag.errors) == 1
    error_files, _ = rag.errors[0]
    assert "Out-of-corpus document rejected" not in error_files[0]["error_description"]
