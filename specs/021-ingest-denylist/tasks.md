# Tasks 021 — ingest denylist

- [ ] T1 — `lightrag/promotion/ingest_denylist.py`: `INGEST_DENYLIST` tuple + `denylisted_reason()`.
- [ ] T2 — `document_routes.py`: import `denylisted_reason`; add the reject guard at the top of
      `pipeline_enqueue_file`'s try-block (before `_resolve_and_rename_edition`).
- [ ] T3 — `tests/promotion/test_ingest_denylist.py`: pure matcher matrix (match forms + non-match
      guidelines).
- [ ] T4 — `tests/api/routes/test_document_routes_denylist.py`: enqueue reject path (False, 0 enqueued,
      1 error, source untouched).
- [ ] T5 — run the two new test files + the scoped offline regression; then caveman-review the diff and
      fix findings.
