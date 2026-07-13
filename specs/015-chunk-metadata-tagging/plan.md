# Plan 015 — chunk metadata tagging

## Storage: a sidecar ARTIFACT, not a live-store mutation

Emit `chunk-tags.jsonl` (`{chunk_id, concept_ref}`) to the data volume (`CHUNK_TAGS_DIR`, default
`/app/data/chunk-tags`) — the same immutable-artifact-on-the-volume pattern as the promotion bundle.
Rationale: the brief says "sidecar metadata, don't mutate the raw text"; mutating the `text_chunks` KV
(the content store) risks record corruption; an artifact is safe + trivially rebuildable + read by both
retrieve and the A-harvest. (concept_ref is the load-bearing join key; facet in the artifact is a follow-on
— retrieve keeps its heading-classified facet, which already works.)

## T2 — backfill endpoint (server-side; the store is internal-only)

`lightrag/api/routers/guidelines_routes.py`: `POST /v1/guidelines:tag-chunks` (mirror the dedup/promote
background-task + file-status pattern).
- Pull the graph (`get_knowledge_graph`, once, on a QUIET graph — safe now), project entities to
  `(concept_ref, source_id)`, `build_chunk_tags(entities)` (spec-015 T1, pure).
- Write `chunk-tags.jsonl` (one `{chunk_id, concept_ref}` per tagged chunk) + a manifest
  (`{built_at_hash, chunk_count, code_count}`); `apply=false` returns counts (dry-run), `apply=true` writes.
- `GET /v1/guidelines/tag-chunks/status`.

## T3 — retrieve reads the artifact (removes the per-request `get_knowledge_graph`)

Replace the retrieve v2 code→chunks index build (`_get_code_index` via `get_knowledge_graph`) with a
TTL-cached **load of `chunk-tags.jsonl`** → the same `code→chunks` map (via `chunk_has_code` / invert). This
kills the cold-start + the mutation-contention 500 (seen during the dedup) — a file read, not a graph read.
**Fallback preserved:** if the artifact is missing (backfill not yet run), fall back to the current
`get_knowledge_graph` index build, so retrieve never regresses.

## Tests
- `build_chunk_tags` (done, spec-015 T1).
- artifact loader → `code→chunks` map (round-trip a small jsonl).
- retrieve reads the artifact index (monkeypatch the loader): concept_ref filters from the artifact;
  artifact-missing → falls back to the graph index (existing spec-014 tests still pass).

## Rollout
Land T2+T3 + tests → cavecrew-review → PR → merge (staging now open). Run `POST /v1/guidelines:tag-chunks?apply=true`
on the quiet graph → re-verify a code-scoped retrieve reads the artifact (`filtered:true`, no get_knowledge_graph).
Facet-in-artifact + resolve-at-ingest = follow-on. A-harvest consumes the artifact (brief A).
