# Spec 011 — section-crop provenance on chat references (`/query/stream`)

**Status:** specify
**Source:** brief `docs/briefs/2026-07-11-webpage-to-guidelines-query-stream-crop-provenance.md`
(demand-signal from dokturek-webpage — the FE chat SourceDialog needs the crops on the chat path)

## Problem

The section-crop work (spec 004, R1–R4) ships per-chunk provenance
(`page`/`pages`/`section`/`bbox`/`crop_url`/`pdf_url`) on **`RetrievedPassage`**, returned by
**`/v1/guidelines:retrieve`**. But the webpage guidelines **chat** consumes **`/query/stream`**, whose
references are **`ReferenceItem`** — **file-grouped** (`reference_id`, `file_path`, `content: string[]`),
carrying **no** provenance and **no per-chunk id**. So the FE chat path has nothing to render a crop from.
Correlating chat references against a second `:retrieve` call by matching chunk text is fragile (different
top-k / ranking / exact-text drift) — the clean fix is to carry the provenance on the chat references.

## Approach (owner-chosen 2026-07-11): enrich `/query/stream` + `/query`, opt-in

Additive, opt-in per-chunk provenance on the existing chat endpoints — **not** a new endpoint, **not** a
change to `ReferenceItem` (which stays file-grouped for back-compat). The per-chunk provenance resolver +
`crop_url`/`pdf_url` shape already live in the shared `lightrag.sidecar.passage_links`
(`passage_provenance`, `build_passage_links`) — refactored there precisely so this chat path reuses the
exact same projection `:retrieve` serves (no drift, no router→router import).

The `/query` and `/query/stream` handlers already hold `data["chunks"]` (each with `chunk_id`,
`reference_id`, `file_path`, `content`) at reference-build time — the same source `:retrieve` iterates.

## Requirements

- **R1 — opt-in flag.** `QueryRequest` gains `include_chunk_provenance: bool = False` (mirrors
  `include_chunk_content`; excluded from `to_query_params`). Default off ⇒ **upstream behaviour unchanged**
  (zero cost, zero payload delta) — important for fork-sync.
- **R2 — per-chunk provenance field.** When `include_references and include_chunk_provenance`, the response
  gains a top-level `chunks: list[ChunkProvenance]`, one per cited chunk, each =
  `{chunk_id, reference_id, file_path, text, page, pages, section, bbox, crop_url, pdf_url}` — i.e. the
  `:retrieve` `RetrievedPassage` projection plus the `chunk_id`/`reference_id` join keys, so the entry is
  self-contained for the FE. Resolved best-effort via `passage_provenance` + `build_passage_links` (a doc's
  `blocks.jsonl` loads once per request via a shared `blocks_cache`). Both `/query` (on `QueryResponse`) and
  `/query/stream` (in the first NDJSON line, alongside `references`).
- **R3 — degrade cleanly.** `crop_url`/`pdf_url`/`page` stay null where the chunk has no MinerU sidecar or
  the PDF is absent (as on `:retrieve`); the field is omitted entirely when the flag is off. Never errors the
  query — a resolver failure drops to text-only.

## Non-goals

- No change to `ReferenceItem` (stays file-grouped; the FE reads the new `chunks` field, joins via
  `reference_id`).
- No new endpoint; no upstream behaviour change when the flag is off.
- FE work (dokturek-webpage `webpage-guidelines-section-crop-source-dialog`) — separate; it consumes the new
  field on the same endpoint (no endpoint migration).

## Acceptance

- `/query/stream` (and `/query`) with `include_references=true, include_chunk_provenance=true` returns
  `chunks[]` carrying `page`/`section`/`crop_url`/`pdf_url` for a known SVL doc; the flag off (or absent)
  returns today's payload byte-for-byte.
- Unit tests: the chat path enriches when the flag is on, omits when off, and degrades to null provenance
  when a chunk has no sidecar. Reuses the `passage_links` resolver (no duplicate resolution logic).
