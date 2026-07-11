# Tasks 012

- [ ] T1 — `LightRAG.areextract_document_commit(doc_id)` in `lightrag.py` (chunk-fetch → busy-guard →
  extract_entities → merge_nodes_and_edges → _insert_done → counts).
- [ ] T2 — endpoint `POST /documents/{doc_id}/reextract-commit` (404 missing/no-chunks, 409 busy, 500 else).
- [ ] T3 — offline unit test (fakes): calls extract+merge+flush with the doc's chunks; raises on busy.
- [ ] T4 — offline suite (grounding + api routes) green; caveman-review the diff.
- [ ] T5 — deploy staging; live 1-doc test → concept_refs land, no duplication, measure cost (→ full-run go/no).
