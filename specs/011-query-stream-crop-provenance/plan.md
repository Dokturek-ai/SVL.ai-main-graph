# Plan 011 — implementation

## Files

- `lightrag/api/routers/query_routes.py` — the only source change:
  1. `QueryRequest`: add `include_chunk_provenance: Optional[bool] = Field(default=False, …)`. It is already
     excluded from `to_query_params` iff we add it to the `exclude={…}` set (alongside `include_chunk_content`).
  2. New model `ChunkProvenance(BaseModel)`: `chunk_id, reference_id, file_path, text` +
     `page, pages, section, bbox, crop_url, pdf_url` (all Optional; the last six mirror `RetrievedPassage`).
  3. `QueryResponse`: add `chunks: Optional[List[ChunkProvenance]] = None`.
  4. `StreamChunkResponse`: add `chunks: Optional[List[Dict[str, Any]]] = None` (NDJSON first line).
  5. A module-level async helper `_build_chunk_provenance(rag, chunks)` that iterates the cited chunks,
     calls `passage_provenance(rag, chunk_id, file_path, blocks_cache)` (shared `blocks_cache` dict per call),
     and returns `[{chunk_id, reference_id, file_path, text, **build_passage_links(chunk_id, file_path, prov)}]`.
     Best-effort: a per-chunk resolver failure yields null links (build_passage_links already handles `{}`).
  6. `/query` handler: after references are assembled, `if request.include_references and
     request.include_chunk_provenance:` set `chunks = await _build_chunk_provenance(rag, data.get("chunks", []))`
     and pass to `QueryResponse(chunks=chunks)`.
  7. `/query/stream` handler: same, injected into the first NDJSON line next to `references`.

- Import: `from lightrag.sidecar.passage_links import passage_provenance, build_passage_links` — a shared lib
  module (NOT the guidelines router), so query_routes stays free of a router→router dependency.

- `tests/api/routes/test_query_*.py` (or a new `test_query_chunk_provenance.py`): unit tests with an injected
  fake `rag` (chunks + a fake `text_chunks.get_by_id` sidecar) + monkeypatched `load_blocks_for_doc`.

## Key decisions

- **Opt-in default off** → the response is byte-identical to today unless asked; keeps the upstream fork delta
  inert for non-guidelines deployments and rebases clean.
- **Reuse `passage_links`, don't re-resolve** — single source of truth for the crop/pdf URL shape (spec 004
  already put it there for exactly this consumer).
- **`chunks` is a sibling of `references`, not nested in `ReferenceItem`** — provenance is per-chunk,
  `ReferenceItem` is per-file; nesting would force a breaking reshape. Self-contained per-chunk entries let the
  FE render directly and still join to `references` via `reference_id`.

## Verify

- Offline: new unit tests green; existing `query_routes` + `guidelines_retrieve` tests unaffected.
- Shape parity: a chunk's `page/section/crop_url/pdf_url` on `/query/stream` equals what `:retrieve` returns
  for the same `chunk_id` (both call `build_passage_links`).
