# Tasks 011

- [ ] T1 — `query_routes.py`: import `passage_provenance`, `build_passage_links` from
  `lightrag.sidecar.passage_links`; add `ChunkProvenance` model; add `include_chunk_provenance` flag
  (+ exclude from `to_query_params`); add `chunks` field to `QueryResponse` + `StreamChunkResponse`.
- [ ] T2 — `_build_chunk_provenance(rag, chunks)` helper (shared `blocks_cache`, best-effort).
- [ ] T3 — wire into `/query` handler (populate `chunks` when `include_references && include_chunk_provenance`).
- [ ] T4 — wire into `/query/stream` handler (first NDJSON line).
- [ ] T5 — unit tests: flag-on enriches with page/section/crop_url; flag-off omits `chunks`; no-sidecar chunk
  degrades to null provenance; shape matches `build_passage_links`.
- [ ] T6 — run offline query + guidelines test suites green; caveman-review the diff.
