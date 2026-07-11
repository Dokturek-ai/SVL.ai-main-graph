# Spec 011 — section-crop provenance on chat references (`/query/stream` + `/query`)

**Status:** implemented (as-built below; found a complete uncommitted implementation + tests, committed here)
**Source:** brief `docs/briefs/2026-07-11-webpage-to-guidelines-query-stream-crop-provenance.md`
(demand-signal from dokturek-webpage — the FE chat SourceDialog needs the crops on the chat path)

## Problem

Section-crop (spec 004, R1–R4) ships per-chunk provenance on **`RetrievedPassage`** (`/v1/guidelines:retrieve`).
But the webpage guidelines **chat** consumes **`/query/stream`**, whose references are **`ReferenceItem`** —
file-grouped (`reference_id`, `file_path`, `content: string[]`), carrying **no** provenance. So the FE chat has
nothing to render a crop from; correlating against a second `:retrieve` call by text-matching is fragile.

## Approach (as-built, owner-chosen 2026-07-11): enrich `ReferenceItem`, gated on `include_chunk_content`

Additive per-chunk provenance nested on the existing chat references — **not** a new endpoint. `ReferenceItem`
gains a `chunks` list; each entry is a `PassageLink` carrying `{text, page, pages, section, bbox, crop_url,
pdf_url}` — the same projection `:retrieve` serves. The resolver + `crop_url`/`pdf_url` shape live in the shared
`lightrag.sidecar.passage_links` (`passage_provenance`, `build_passage_links`), so `:retrieve` and the chat path
can't drift (no router→router import). The provenance rides the existing `include_chunk_content` flag (if you
ask for chunk text you get its provenance) — no new request flag.

## Requirements (as-built)

- **R1 — models.** `PassageLink(BaseModel)` = `text` + optional `page/pages/section/bbox/crop_url/pdf_url`.
  `ReferenceItem` gains `chunks: Optional[List[PassageLink]] = None` (additive; `content` unchanged for
  back-compat). This declares the field on the OpenAPI schema and makes `/query` (non-stream, via
  `QueryResponse`) serialize it — not only the raw-dict `/query/stream` path.
- **R2 — enrichment.** `_enrich_references_with_chunks(rag, references, chunks)` groups `content` per file
  (back-compat) AND attaches per-chunk `chunks` via `passage_provenance` + `build_passage_links`
  (`blocks_cache` per request so a doc's `blocks.jsonl` loads once). Guards the empty `chunk_id` (a blank id
  must not hit `get_by_id` and mis-attach a page). Wired into both `/query` and `/query/stream`, replacing
  the old inline content-only enrichment.
- **R3 — degrade / opt-in.** Present only when `include_references and include_chunk_content`; a chunk with no
  sidecar/PDF keeps `text` with null `page/crop_url`; never errors the query.

## Non-goals

- No new endpoint; no new request flag (rides `include_chunk_content`).
- No behaviour change when `include_chunk_content` is off (payload identical to today).
- FE work (dokturek-webpage `webpage-guidelines-section-crop-source-dialog`) — separate; consumes
  `ReferenceItem.chunks` on the same endpoint (no endpoint migration).

## Acceptance

- `/query/stream` + `/query` with `include_references=true, include_chunk_content=true` return
  `references[].chunks[]` carrying `text`/`page`/`section`/`crop_url`/`pdf_url` for a known SVL doc; the flag
  off returns today's payload. **Live-verify after deploy** (the impl was uncommitted ⇒ not yet deployed;
  `scratch/probe_chat_provenance.py` showed `has_chunks=False` against the un-deployed service).
- Unit tests (`tests/api/routes/test_query_stream_provenance.py`, 5 cases): enrich, multi-span, degrade,
  empty-chunk_id guard, off-omits. Shared resolver — no duplicate resolution logic.
