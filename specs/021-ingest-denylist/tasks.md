# Tasks 021 — ingest denylist

- [x] T1 — `lightrag/promotion/ingest_denylist.py`: `INGEST_DENYLIST` tuple + `denylisted_reason()`.
- [x] T2 — `document_routes.py`: import `denylisted_reason`; add the reject guard at the top of
      `pipeline_enqueue_file`'s try-block (before `_resolve_and_rename_edition`).
- [x] T3 — `tests/promotion/test_ingest_denylist.py`: pure matcher matrix (match forms + non-match
      guidelines).
- [x] T4 — `tests/api/routes/test_document_routes_denylist.py`: enqueue reject path (False, 0 enqueued,
      1 error, source untouched).
- [x] T5 — ran the two new test files (12 passed) + scoped offline regression
      (`tests/{promotion,api,pipeline}` 448 passed, 0 failed); caveman-review next.
