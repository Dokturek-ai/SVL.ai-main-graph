# Spec 018 — `section-crop` `&page=N` override for a multi-page chunk

**Status:** specify
**Source:** brief `docs/briefs/2026-07-20-guidelines-section-crop-page-override-for-multipage.md`
(`from: webpage`, demand-signal from the FE source viewer, spec 162). Builds on spec 004 (section-crop render)
and spec 011 (`chunks[].pages`).

## Problem

`GET /v1/guidelines/section-crop?chunk_id=<id>` renders the chunk's **primary** page only. The primary page +
bbox come from `resolve_provenance` (`provenance.py`): `page` = anchor of the FIRST covered block, `bbox` = that
block's box. `pages` lists **every** page the chunk's blocks touch — a chunk that crosses a page break carries
e.g. `pages: [12, 13]`.

The webpage source viewer (SourceDialog + inline preview/lightbox, spec 162) wants to render **every** page a
chunk touches, not just the primary. Today page 13 (the continuation) is unreachable: the endpoint has no page
selector, so the FE can only ever show page 12.

## Approach (owner-chosen): additive `page` query param, backward compatible

`_render_section_crop(pdf_path, page_number, bbox)` already takes an explicit page + a **nullable** bbox, so this
is route wiring, not new render code. Add an optional `page` param:

- `page` **absent** → today's behaviour (primary page + bbox highlight), byte-for-byte unchanged.
- `page=<N>` present and `N ∈` the chunk's resolved `pages` → render page N. Highlight the bbox **only** on the
  primary page (the one the resolved block sits on); a secondary page renders **clean** (bbox `None`) — we have
  no block box for it, so no fabricated highlight.
- `page=<N>` **not** in the chunk's `pages` (or unresolvable) → **404**, same shape as an unresolved crop today.

## Requirements

- **R1 — optional param.** `page: Optional[int] = Query(None, …)` on `guidelines_section_crop`. Absent ⇒
  identical output + identical code path as before (primary page, bbox highlight).
- **R2 — membership gate.** When `page` is present it MUST be one of the chunk's resolved `pages` (int-compared,
  coercing the anchor list to int). Not a member ⇒ `404` (`"requested page is not one of the chunk's pages"`).
  This bounds the param to real, provenance-backed pages — never an arbitrary page of the PDF.
- **R3 — bbox only on the primary page.** Pass `prov["bbox"]` to the renderer **only** when the requested page
  equals the primary `page`; otherwise pass `None`. `resolve_provenance` only stores the primary block's box, so
  a secondary page has no legitimate highlight — render it clean rather than draw the primary box on the wrong
  page.
- **R4 — no new render code / no provenance change.** Reuse `_render_section_crop` and the existing
  `resolve_provenance` output. No re-parse, no re-extract, ingest untouched (pure read path).

## Non-goals

- **`chunks[].crop_urls` map** (`{page → url}`). The brief lists it as *optional* — the FE can string-build
  `&page=N` from `pages[]` + `chunk_id`. Keep the change minimal (one param); the enrichment payload is
  unchanged.
- **FE** consumption (spec 162, dokturek-webpage) — out of scope, separate repo.
- Any change to `/query`, `/query/stream`, `:retrieve`, or the enrichment shape.

## Acceptance

- `GET …/section-crop?chunk_id=<multipage-chunk>` (no `page`) → 200, same PNG as before (primary page, bbox).
- `…&page=<primary>` → 200 with the bbox highlight (identical to no-param).
- `…&page=<secondary ∈ pages>` → 200, clean page (no highlight box).
- `…&page=<not in pages>` → 404.
- Route/unit tests green in the offline suite (staging has no CI gate → offline suite is the gate).
- Live-verify on staging after deploy against a real multi-page chunk (loose end → brief if not run here).
