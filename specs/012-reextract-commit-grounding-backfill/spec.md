# Spec 012 — re-extract-commit (grounding backfill on processed docs)

**Status:** specify
**Why:** the concept_ref grounding (specs 008–010) runs at the **merge** stage
(`merge_nodes_and_edges` → `_merge_nodes_then_upsert` → grounding hook). The staging corpus was ingested
**before** grounding was enabled, so its graph nodes carry no `concept_ref`. To produce the promotion bundle
for mkn10, the corpus must be re-extracted **with grounding, committed to the graph** — but there is no such
path today.

## The gap

- `areextract_document` re-extracts from stored chunks but is **inspection-only** — it calls
  `extract_entities` and NOT `merge_nodes_and_edges`, so it neither grounds nor persists.
- The grounding hook + persistence live in `merge_nodes_and_edges` (run by the pipeline for PENDING /
  PREPROCESSED docs).
- There is **no HTTP path** to re-run extract+merge on an already-PROCESSED doc: `reprocess_failed` only
  picks up FAILED/PENDING/PROCESSING; `reextract` doesn't commit. Only a full delete + re-ingest would
  re-merge — but that re-parses the PDF (MinerU CPU, slow, crash-risk) for all 51 docs.

## Requirements

- **R1 — `LightRAG.areextract_document_commit(doc_id)`.** Re-extract a doc's **already-stored chunks** (no PDF
  re-parse) and **commit**: `extract_entities` → `merge_nodes_and_edges` (which applies concept_ref grounding
  when `CONCEPT_REF_GROUNDING_ENABLED=true`) → `_insert_done` (flush all storages). Mirrors
  `areextract_document`'s chunk-fetch, then adds the merge the pipeline runs. Acquires the pipeline `busy`
  lock (refuse when the pipeline is already busy, like `adelete_by_doc_id`); releases it in `finally`.
  Returns `{doc_id, file_path, chunks, entity_count, relation_count, committed: true}`.
- **R2 — endpoint `POST /documents/{doc_id}/reextract-commit`** (auth-gated). 404 on missing doc / no stored
  chunks; 409 when the pipeline is busy; 500 otherwise. Foreground (bounded: no re-parse, one doc's chunks).

## Idempotency / clean-slate

`merge_nodes_and_edges` upserts nodes **by entity name** and edges **by (src, tgt)** — re-running over the
same chunks re-merges into the SAME graph nodes (updates them, adds `concept_ref`), it does not create
duplicate nodes. So no delete-first is needed; re-extract overlays grounding onto the existing graph. The
1-doc test (below) confirms no duplication + that `concept_ref` lands.

## Non-goals

- No PDF re-parse (reuses stored chunks). No status-machine changes. No batch/whole-corpus orchestration in
  this spec (a caller loops over doc ids; the harness/run is separate).
- Edge `subject` on the committed relations is out of scope here (separate stage-2 enabler).

## Acceptance

- On 1 processed DP: `reextract-commit` returns committed counts; afterwards the graph's clinical nodes for
  that doc carry `concept_ref` (verified via a query/graph read), with no duplicate entities vs before.
- Pipeline-busy → 409, not a corrupt partial merge.
- Offline unit test: the method calls `extract_entities` + `merge_nodes_and_edges` + `_insert_done` with the
  doc's chunks, and refuses when busy (injected fakes; no LLM/DB).
