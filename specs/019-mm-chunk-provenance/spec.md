# Spec 019 — page/section provenance for multimodal (table/drawing/equation) chunks

**Status:** specify
**Source:** brief `docs/briefs/2026-07-20-guidelines-mineru-block-coverage-for-page-citation.md`
(`from: dokturek-guidelines`, P3). Builds on spec 004 (provenance resolver) and spec 011 (chat `chunks[].page`).

## Problem

~25% of retrieved chunks resolve **no page** (`page: null`), degrading their citation to title-only on every
path (`:retrieve`, chat `references[].chunks[]`, and the visible `### References` block, spec 017). The
block-coverage diagnosis (brief, 2026-07-21, server-authorized) pinned the bucket precisely:

- The no-page bucket is **~87% multimodal** — `mm-table` (74.4%) and `mm-drawing` (12.8%) chunks; prose chunks
  resolve **95.9%** (they are the healthy path). This is the high-stakes case: a dosing **table** chunk that
  can't point at the page its dose lives on.
- **Root cause is a deliberate v1 read-path exclusion, not a data gap.** A multimodal chunk's stored sidecar is
  `{"type": "table"|"drawing"|"equation", "id": "tb-…"|"im-…"|"eq-…", "refs":[{...same id}]}`
  (`pipeline.py:_build_mm_chunks_from_sidecars`, line ~5127). The id is the **table/drawing/equation id**, not a
  `blockid`. `sidecar/provenance.py:_block_ids` rejects any non-content sidecar outright:
  ```python
  if sidecar.get("type") not in (None, "block"):
      return []
  ```
  So every mm-chunk resolves `page=None` by design.
- **The positions already exist.** Confirmed on the staging volume: **680/680 mm entries across all 51 docs**
  carry a `blockid` in `tables.json`/`drawings.json`/`equations.json`, that blockid is a **content** row in
  `blocks.jsonl`, and that block has a bbox position with a page anchor (100% chain). blocks.jsonl is complete
  (2756/2756 content blocks positioned) — **no re-parse, no re-extract, no ingest needed.**

## Approach (owner cost gate): pure read-path `mm sidecar id → blockid → blocks.jsonl` hop

Teach the resolver one indirection. The mm sidecar `id` (dict key in `tables.json` etc.) maps to that entry's
`blockid`, which is an existing positioned content block — resolve **that** block with the shipped path.

- Add a per-doc loader for the `{mm_id → blockid}` map, built from `*.tables.json` / `*.drawings.json` /
  `*.equations.json` in the same `<doc>.parsed/` dir the read path already reads `blocks.jsonl` from.
- Extend `resolve_provenance` to accept that map: when a sidecar is multimodal, translate its id(s) to
  blockid(s), then run the **unchanged** covered-block → page/section/bbox logic.
- Content-block chunks are untouched (map absent/empty ⇒ today's behaviour, byte-for-byte).

**Cost:** $0 LLM, no re-chunk, no re-parse, no ingest — effective immediately on the current store. Impact:
**75% → ~97%** per-chunk page resolution (all mm chunks resolve, verified 680/680), **table chunks prioritized**
— clears the brief's >90% target.

## Requirements

- **R1 — mm-id→blockid loader.** A pure I/O helper loads `{str(mm_id): str(blockid)}` from a doc's
  `*.tables.json` / `*.drawings.json` / `*.equations.json` (root keys `tables`/`drawings`/`equations`; each entry
  carries `blockid`). Missing files / malformed rows / entries without `blockid` are skipped (best-effort, like
  `load_blocks_by_id`). Returns `{}` when nothing loads.
- **R2 — resolver translates mm ids.** `resolve_provenance(sidecar, blocks_by_id, mm_id_to_blockid=None)`. When
  the sidecar `type` is `table`/`drawing`/`equation`, map each of its ids (the `id` + `refs[].id`) through
  `mm_id_to_blockid` to blockids and resolve those against `blocks_by_id` via the **existing** covered-block
  logic. A content-block sidecar (`type` None/`"block"`) is unaffected.
- **R3 — deterministic + backward compatible.** `mm_id_to_blockid` absent/empty ⇒ **identical** output to today
  for every sidecar (a mm sidecar still returns `None`; a content sidecar is byte-for-byte unchanged). No change
  to the `{page, pages, section, bbox, block_ids}` shape.
- **R4 — wired into both surfaces.** `passage_provenance` (shared by `:retrieve` and the chat references) loads
  the mm map per-doc (same per-request cache pattern as `blocks_cache`) and passes it to `resolve_provenance`, so
  a mm-chunk now carries `page`/`pages`/`section`/`bbox`/`crop_url` on **every** consuming path.
- **R5 — pure read path, cost gate.** No ingest / re-parse / re-extract / re-chunk. `resolve_provenance` stays
  I/O-free (the caller loads the map, mirroring `blocks_by_id`).

## Non-goals

- **`section-crop` bbox highlight for mm chunks.** The resolved block's bbox is the *containing content block*
  (e.g. the table's positioned region) — good enough for page + a region highlight, reusing spec 004/018 as-is.
  No mm-specific crop geometry.
- **The 5 no-page prose chunks** (12.8% of the bucket) — a separate residual, out of scope here; this spec closes
  the multimodal ~87%.
- **MANUÁL KÓDŮ hygiene** (6 no-page chunks are out-of-domain) — tracked on brief
  `guidelines-016-edition-rename-residue-and-landing` §B, not this spec.
- Any ingest-time change to how mm sidecars are written (storing `blockid` in the sidecar at ingest is a
  possible future simplification, but needs a re-ingest — avoided; the read-path map is $0).

## Acceptance

- `resolve_provenance(mm_sidecar, blocks, mm_map)` returns the containing block's `page`/`section`/`bbox` for a
  table/drawing/equation chunk; returns `None` when the map is absent (backward compatible).
- `resolve_provenance(content_sidecar, blocks)` output is byte-for-byte unchanged (map ignored for content).
- Offline unit tests cover: mm-table resolves via map, mm sidecar without map → None, content sidecar unaffected,
  refs-based + id-only mm sidecars, missing/partial sidecar json.
- Live-verify on staging after deploy: a mm-table chunk (e.g. `Arteriální hypertenze_2024 …-mm-table-…`) now
  returns a non-null `page` on `:retrieve` (loose end → brief if not run here).
- Staging has no CI gate → the offline suite is the gate; run it locally green before merge.
