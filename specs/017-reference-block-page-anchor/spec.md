# Spec 017 — deterministic page/section in the visible `### References` block (`/query`)

**Status:** specify
**Source:** user request (citation granularity) + related brief
`docs/briefs/2026-07-01-agent-to-guidelines-span-citation-pdf-anchor.md` (open, demand-signal from agent + FE).
Builds directly on spec 011 (`references[].chunks[]` provenance) and spec 004 (section-crop).

## Problem

The machine-readable citation is already page/chunk-precise:

- `:retrieve` → `RetrievedPassage.{citation(file#chunk=id@edition), page, pages, section, bbox, crop_url,
  pdf_url, facet}` (guidelines_routes.py).
- `/query` chat → `references[].chunks[].{text, page, pages, section, bbox, crop_url, pdf_url}` when
  `include_chunk_content=true` (spec 011, query_routes.py `_enrich_references_with_chunks`).

But the **human-visible `### References` block inside the answer text** is **file/title-level only** — the LLM
writes it (`prompt.py` "References Section Format": `* [n] Document Title`), and `reference_list_str`
(operate.py:5093 kg / :6034 naive) hands the LLM only `[n] {file_path}`. So a clinician reading the answer sees
`- [1] borrelioza_2018.pdf` with no page, even though the backend already resolved page 29 for that span.

**Verifiable-AI constraint (why we don't just add page to `reference_list_str`):** feeding page numbers into the
LLM's context makes the probabilistic layer the **last writer of the citation** — it can transpose s.29↔30 or
mis-attribute a page to the wrong doc. Per the platform Verifiable-AI Standard the load-bearing citation must be
written **deterministically by the backend**, not the LLM.

## Approach (owner-chosen): deterministic post-synthesis rewrite of the `### References` block (non-stream `/query`)

After synthesis, the backend already holds both the `response` string (with the LLM's file-level `### References`
block) **and** the enriched `references[].chunks[]` (with resolved page/section). A pure composer:

1. Locates the `### References` block in `response` (last occurrence; prompt guarantees nothing follows it).
2. Reads the reference ids `[n]` the LLM cited there (preserves the LLM's *relevance selection* — which docs,
   in what order; that is editorial, not provenance).
3. Rebuilds each line **deterministically** from the enriched reference: `- [n] {file_path} — s. <pages>[ ·
   <section>]`, pages aggregated + deduped across that reference's chunks. Page/section come **only** from the
   resolved payload, never from the response text.
4. Replaces the block. Everything before `### References` is untouched.

The LLM still *chooses* which sources are relevant; the backend is the sole writer of the page/section suffix.

## Scope: non-stream `/query` only

Streaming (`/query/stream`) sends `references[]` (with page) **first**, then streams answer tokens live — a live
stream can't be post-processed without buffering the whole thing (defeats streaming). Streaming clients therefore
render the page-precise citation from the already-first `references[]` payload — that is the **FE** job
(option 2, briefed to dokturek-webpage), not this backend change. This spec deterministically fixes the
**self-contained `response` text** that batch / agent / export / copy-paste consumers read verbatim.

## Requirements

- **R1 — pure composer.** `render_reference_block_with_pages(response: str, references: list[dict]) -> str` in
  a testable module. Deterministic; no I/O (operates on the already-enriched `references`). Returns `response`
  unchanged when there is no `### References` block or no page data resolved.
- **R2 — wire into non-stream `/query`.** Call it in query_routes after `_enrich_references_with_chunks`
  (query_routes.py ~L509), before returning `QueryResponse`. Gated the same as enrichment
  (`include_references and include_chunk_content`) — without enriched chunks there is no page to add, so it is a
  no-op.
- **R3 — page/section aggregation.** For a reference cited as `[n]`, aggregate pages across its `chunks[]`
  (`page`/`pages`), dedupe, sort numerically → `s. 29` / `s. 12–13` (contiguous) / `s. 12, 15`. Append section
  (`chunks[].section` heading path) only when the cited chunks share a single section; omit when they diverge
  (avoid a misleading single label).
- **R4 — coverage-gap honesty.** A cited reference whose chunks resolved **no** page (the ~20–30% MinerU
  no-block bucket) renders `- [n] {file_path}` with **no** page suffix — never a fabricated or blank `s.`.
- **R5 — Verifiable-AI.** The page/section text is assembled solely from `references[].chunks[]`; the LLM is
  never the last writer of a page number. `reference_list_str` (operate.py) is **unchanged** — page does not
  enter the synthesis prompt.

## Non-goals

- **Streaming** page-in-text — FE renders from the first-sent `references[]` (brief to dokturek-webpage).
- **Coverage** of the ~20–30% no-page chunks — MinerU block-resolution, ingest-side, separate brief.
- No prompt change; no new request flag; no change when `include_chunk_content` is off.
- Not touching `:retrieve` (already page/chunk-precise).

## Acceptance

- Non-stream `/query` "jak se léčí erythema migrans" with `include_references=true,
  include_chunk_content=true` returns a `response` whose `### References` lines carry `s. <page>` (and section
  where unambiguous) for references whose chunks resolved a page; references with no resolved page stay
  title-only. **Live-verify on staging after deploy.**
- `reference_list_str` unchanged (page absent from the synthesis prompt) — confirm no diff at operate.py:5093/6034.
- Unit tests (below) green in the offline suite (staging has no CI gate → offline suite is the gate).
