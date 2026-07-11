# Plan 012

## Files

- `lightrag/lightrag.py` — add `areextract_document_commit(doc_id)` right after `areextract_document`.
  Reuses that method's chunk-fetch (doc_status → chunks_list → `text_chunks.get_by_ids`). Then:
  - acquire `pipeline_status` / `pipeline_status_lock` via `get_namespace_data`/`get_namespace_lock`
    (workspace-scoped); if `pipeline_status.get("busy")` → raise `RuntimeError("pipeline busy")`; else set
    `busy=True` + job metadata (mirror `adelete_by_doc_id`); release in `finally`.
  - `chunk_results = await extract_entities(chunks, global_config=self._build_global_config(),
    llm_response_cache=self.llm_response_cache, text_chunks_storage=self.text_chunks)` (same call areextract
    makes).
  - `await merge_nodes_and_edges(chunk_results=…, knowledge_graph_inst=self.chunk_entity_relation_graph,
    entity_vdb=self.entities_vdb, relationships_vdb=self.relationships_vdb, global_config=…,
    full_entities_storage=self.full_entities, full_relations_storage=self.full_relations, doc_id=…,
    pipeline_status=…, pipeline_status_lock=…, llm_response_cache=self.llm_response_cache,
    entity_chunks_storage=self.entity_chunks, relation_chunks_storage=self.relation_chunks,
    current_file_number=1, total_files=1, file_path=…)` — the exact call `pipeline.py:2490` makes.
  - `await self._insert_done()` to flush all storages (graph + vdbs).
  - Return `{doc_id, file_path, chunks, entity_count, relation_count, committed: True}` (counts from
    `chunk_results`).

- `lightrag/api/routers/document_routes.py` — `POST /documents/{doc_id}/reextract-commit`:
  `await rag.areextract_document_commit(doc_id)`; `ValueError` → 404; `RuntimeError` (busy) → 409; else 500.

- `tests/` — offline unit test with a fake rag (stub `doc_status`, `text_chunks`, storages,
  monkeypatched `extract_entities`/`merge_nodes_and_edges`/`_insert_done`): asserts the commit path calls
  extract + merge + flush with the doc's chunks, and raises when `busy`.

## Key decisions

- **Reuse, don't reinvent** — same `extract_entities` + `merge_nodes_and_edges` the pipeline uses, so
  grounding + persistence behave identically (the grounding hook is inside merge).
- **No delete-first** — merge upserts by name/(src,tgt) → overlays onto existing nodes, no duplication.
  Confirmed by the 1-doc test.
- **Busy-guard** — never merge concurrently with the pipeline (keyed-lock + shared flush buffer).
- **Foreground** — bounded (one doc, no re-parse); the caller (a run harness) loops over doc ids.

## Verify

- Offline unit test green.
- Live 1-doc test (`scratch/`): `POST /documents/{id}/reextract-commit` on one processed DP → committed
  counts; then a graph/query read shows that doc's clinical nodes carry `concept_ref`; entity count not
  doubled. Measure wall-time → extrapolate the 51-doc run cost.
