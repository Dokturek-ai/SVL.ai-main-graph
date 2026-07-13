# Tasks 015 — chunk metadata tagging

## T1 — pure propagation (DONE)
`chunk_tags.py` `build_chunk_tags`/`chunk_has_code` + 7 units. ✓

## T2 — backfill endpoint → chunk-tags.jsonl artifact
`guidelines_routes.py`: `POST /v1/guidelines:tag-chunks` (dry-run/apply, background, file status, mirrors
dedup/promote) — pull graph → `build_chunk_tags` → write `chunk-tags.jsonl` + manifest to `CHUNK_TAGS_DIR`.
`GET /v1/guidelines/tag-chunks/status`.

## T3 — retrieve reads the artifact
`retrieve_filter.py` (or a loader): parse `chunk-tags.jsonl` → `code→chunks` map. Wire `guidelines_retrieve`
to load the artifact (TTL-cached) instead of `get_knowledge_graph`; artifact missing → fall back to the graph
index (no regression). Units: loader round-trip; retrieve filters from artifact; fallback path.

## T4 — gated run + verify (ops)
Merge → `POST /v1/guidelines:tag-chunks?apply=true` on the quiet graph → re-verify a code-scoped retrieve
(`filtered:true`, served from the artifact, no per-request get_knowledge_graph).

## Verify
- units green (T1 + loader + retrieve-from-artifact + fallback); offline suite subset green.
- artifact has ~1384 tagged chunks; a scoped retrieve reads it; artifact-missing → graph-index fallback.
