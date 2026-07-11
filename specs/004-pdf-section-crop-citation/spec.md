# Spec 004 — PDF section-crop citation

**Status:** COMPLETE (BE) — R1 (resolver) ✅ + R2 (retrieve fields) ✅ + R3 (crop render) ✅ + R4 (PDF serve) ✅, all live-verified on staging (138 PDFs on the volume, pypdfium2 in the image). FE (`webpage`) is the only follow-up.
**Source:** brief `docs/briefs/2026-07-10-guidelines-pdf-section-crop-citation.md` (owner-decided 2026-07-10)

## Problem

Chat references show markdown chunks, not the source location. Clinicians want to see the **exact PDF
page region** a passage came from (cited section highlighted) and click to open the full PDF.

## Substrate (verified in code)

The MinerU-parsed corpus carries per-chunk provenance:
- `chunk["sidecar"] = {"type":"block","id":<blockid>,"refs":[{"type":"block","id":<blockid>}…]}`
  (`lightrag/sidecar/backfill.py`).
- `<doc>.parsed/blocks.jsonl` content rows (`lightrag/sidecar/writer.py`):
  `{type:"content", blockid, content, heading, parent_headings:[…], level, positions:[…]}`.
- `positions[i]` for PDF = `{type:"bbox", anchor:<page>, range:[x0,y0,x1,y1], origin?}` (`ir.py`).

So a cited chunk → its block(s) → **page** (`position.anchor`), **bbox** (`position.range`),
**section** (`parent_headings › heading`).

## Requirements

- **R1 — Provenance resolver (pure, this spec):** given a chunk's `sidecar` + the doc's parsed block
  rows, return `{page, section, bbox, block_ids, pages}` for the primary (first) covered block, or
  `None` when provenance is absent. Deterministic, no I/O, unit-tested against the writer schema.
- **R2 — Retrieve fields (gated):** `/v1/guidelines:retrieve` (and `/query/stream` references) gain
  per-cited-chunk `{page, section, crop_url?, pdf_url?}`, additive/optional; omitted when the chunk has
  no sidecar (degrades to today's behaviour).
- **R3 — Render endpoint (gated):** `GET /v1/guidelines/section-crop?doc&chunk` → rasterize PDF page N
  (pypdfium2), highlight the block bbox, return PNG. Render live from the current sidecar; never
  persist bbox downstream (stability).
- **R4 — PDF serving (gated):** `GET /v1/guidelines/pdf?doc` → the source PDF, so the click-through
  opens the full document.

## Gated on live substrate verification (cannot confirm offline)

Before R2–R4 ship, confirm on the deployment: (a) `chunk["sidecar"]` persists in the PG chunk store /
is returned by `aquery_data`; (b) `<doc>.parsed/blocks.jsonl` is on the `/app/data` volume; (c) the
source PDFs are on the volume (or upload them). Also: adding **pypdfium2** to the runtime image (RAILPACK).

## Non-goals
- Client-side PDF.js viewer / client coordinate transforms (server-side crop instead — lighter).
- Persisting bbox anywhere downstream (display-only, re-rendered from the current sidecar).
- FE work (dokturek-webpage follow-up, gated on R2–R4).

## Acceptance (this spec = R1)
- `resolve_provenance` returns correct page/section/bbox for a fixture built to the writer schema;
  degrades to `None` on missing sidecar/positions; unit-tested. R2–R4 tracked by the brief once
  substrate is verified.
