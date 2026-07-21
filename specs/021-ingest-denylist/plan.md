# Plan 021 — ingest denylist

## Files

1. **`lightrag/promotion/ingest_denylist.py`** (new) — config + pure matcher.
   - `INGEST_DENYLIST: tuple[str, ...] = ("PRO VPL",)` with a comment tying each entry to its reason.
   - `denylisted_reason(filename: str) -> str | None` — return the matched pattern (for logging/audit)
     if any `pat.upper()` is a substring of `filename.upper()`, else `None`. Pure, no I/O.

2. **`lightrag/api/routers/document_routes.py`** (edit) — enqueue guard.
   - Import `denylisted_reason`.
   - At the **top of the `pipeline_enqueue_file` try-block** (before `_resolve_and_rename_edition`):
     if `denylisted_reason(file_path.name)` is truthy → build one `error_files` entry
     (`error_description="[File Extraction]Out-of-corpus document rejected"`, `original_error` naming the
     matched pattern + the brief), `await rag.apipeline_enqueue_error_documents(...)`, `logger.warning`,
     `return False, track_id`. No rename, no read, no enqueue.

## Tests (offline)

3. **`tests/promotion/test_ingest_denylist.py`** (new) — pure matcher matrix:
   - matches `MANUÁL KÓDŮ PRO VPL_unknown.pdf`, `_2026.pdf`, yearless `MANUÁL KÓDŮ PRO VPL.pdf`, an NFD
     spelling of the stem, and a lowercase variant;
   - returns `None` for legit guidelines (`Akutní průjem_2023.pdf`, `Arteriální hypertenze_2024.pdf`,
     `Laboratorní metody_2023.pdf`).

4. **`tests/api/routes/test_document_routes_denylist.py`** (new) — reject path via the existing
   `_FakeRag` harness pattern (records `.enqueued` / `.errors`):
   - `pipeline_enqueue_file(rag, <tmp>/MANUÁL KÓDŮ PRO VPL_2026.pdf, track_id)` → `(False, track_id)`;
   - `rag.enqueued == []` (never enqueued for parse/extract);
   - exactly one recorded error, description = out-of-corpus reject;
   - source file untouched (not moved to `__parsed__`, not renamed).

## Verification

- `.venv/bin/python -m pytest tests/promotion/test_ingest_denylist.py tests/api/routes/test_document_routes_denylist.py -q`
- Regression: `.venv/bin/python -m pytest tests/promotion tests/api tests/pipeline -q -m offline`
- caveman-review on the diff before declaring done.

## Risk / rollback

- Over-match would silently reject a legitimate guideline. Mitigated: key verified unique to MANUÁL
  across the live 130-doc corpus; rejection is logged + recorded as an error doc_status (visible), not a
  silent drop, so a false positive is diagnosable. Rollback = remove the entry from the tuple + redeploy.
- Best-effort: the guard is pure-string + returns early; it can't raise on normal input, so it cannot
  block ingest of a non-denylisted doc.
