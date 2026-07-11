# Plan 011 — as-built

## Files

- `lightrag/api/routers/query_routes.py`:
  - `PassageLink(BaseModel)` — `text` + optional `page/pages/section/bbox/crop_url/pdf_url`.
  - `ReferenceItem.chunks: Optional[List[PassageLink]] = None` (additive; documents the schema, makes
    `/query` non-stream serialize it, not only the raw-dict stream path).
  - `_enrich_references_with_chunks(rag, references, chunks)` — per-file `content` group (back-compat) +
    per-chunk `chunks` via `passage_provenance` + `build_passage_links`; `blocks_cache` per request;
    empty-`chunk_id` guard.
  - Wired into `/query` and `/query/stream`, replacing the two inline content-only enrichment blocks.
  - Import from the shared lib `lightrag.sidecar.passage_links` (NOT the guidelines router).

- `lightrag/sidecar/passage_links.py` (new, shared) — `passage_provenance` (resolve chunk sidecar → blocks),
  `build_passage_links` (→ `{page,pages,section,bbox,crop_url,pdf_url}`), `load_blocks_for_doc`, and the
  `crop_url`/`pdf_url` string shape. Single source of truth for both `:retrieve` and the chat path.

- `lightrag/api/routers/guidelines_routes.py` — `:retrieve` refactored to reuse `passage_links`
  (`_load_blocks_for_doc`/`_passage_provenance` aliases retained so the section-crop render endpoint + the
  spec-004 tests that monkeypatch them still work).

- `tests/api/routes/test_query_stream_provenance.py` (new) — 5 cases, offline (stubbed `aquery_llm` + chunk
  store, monkeypatched `load_blocks_for_doc`).

## Note

This spec documents a complete implementation found **uncommitted** in the working tree (prior-session work,
never committed → never deployed, which is why the live chat still showed `has_chunks=False`). Verified
correct (scoped gate green) and committed here as the implement phase.

## Verify

- Scoped gate green (205 passed: api/routes + grounding). Shape parity with `:retrieve` (both call
  `build_passage_links`).
- Post-deploy: `scratch/probe_chat_provenance.py` → `has_chunks=True` with page/section/crop_url on staging.
