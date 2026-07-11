# Tasks 011 (as-built)

- [x] T1 — `query_routes.py`: `PassageLink` model; `ReferenceItem.chunks: Optional[List[PassageLink]]`.
- [x] T2 — `_enrich_references_with_chunks(rag, references, chunks)` (shared `passage_links`, `blocks_cache`,
  empty-chunk_id guard); replaces the inline content-only enrichment.
- [x] T3 — wired into `/query` (non-stream) handler.
- [x] T4 — wired into `/query/stream` handler.
- [x] T5 — shared resolver extracted to `lightrag/sidecar/passage_links.py`; `guidelines_routes.py`
  `:retrieve` refactored to reuse it (aliases kept for the section-crop endpoint + spec-004 tests).
- [x] T6 — unit tests `tests/api/routes/test_query_stream_provenance.py` (5 cases). Scoped gate green
  (205 passed: api/routes + grounding).
- [ ] T7 — caveman-review the diff; PR → merge → deploy → live-verify `has_chunks=True` on staging.
