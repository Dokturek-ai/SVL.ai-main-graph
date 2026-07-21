# Spec 021 — ingest denylist so out-of-corpus docs can't be re-pulled into the guidelines graph

## Problem

`MANUÁL KÓDŮ PRO VPL` is a **mako billing-code manual, not an SVL guideline** — it does not belong in the
doporučené-postupy graph (memory `manual-kodu-not-in-dp-corpus`; brief
`manual-kodu-not-in-dp-corpus`). It has now been removed from staging **twice** (2026-07-12 delete —
left orphan chunks/entities; 2026-07-21 surgical scrub — 0 rows, 0 citations, shared entities intact).
Between those removals a new `_2026` edition was **re-uploaded and re-ingested**.

Nothing stops that recurring: there is **no ingest denylist**. The upload/scan path accepts any PDF, so
the cleanup is not durable — the next re-upload of a mako doc silently re-poisons guideline retrieval
with out-of-domain content. This is a **correctness** issue (out-of-domain passages returned as
guidelines), not just provenance noise.

Source brief: `2026-07-21-guidelines-ingest-exclude-list-out-of-corpus-docs` (residue B prevention).

## Goal

A known out-of-corpus document is **rejected on the ingest path before it becomes chunks/entities**, so a
re-upload of `MANUÁL KÓDŮ PRO VPL_*.pdf` never produces chunks, entities, or relations, and a human sees
an explicit reason why the doc didn't land.

## Approach

The four design decisions the source brief left open, resolved per its own recommendations:

1. **Where to filter — the enqueue choke point.** Guard in `pipeline_enqueue_file`
   (`document_routes.py`), at the top of the ingest try-block, **before** `_resolve_and_rename_edition`
   and before any parse/read. This one function is reached by **both** the upload endpoint and the
   directory scan (`from_scan=True`), so a single guard covers both entry paths.

2. **Match key — a config-as-code substring denylist.** `lightrag/promotion/ingest_denylist.py` holds
   `INGEST_DENYLIST: tuple[str, ...]` of ASCII substrings matched **case-insensitively** against the
   upload filename. Seed = `("PRO VPL",)`. Pure-ASCII so NFC/NFD normalization can't split the match
   (the diacritics live in "MANUÁL KÓDŮ", which the key deliberately avoids). **Broader than the
   `PRO VPL_` DELETE-scrub key on purpose:** a filename guard must catch *every* edition — `_unknown`,
   `_2026`, `_<year>`, and a yearless `…PRO VPL.pdf` (the trailing `_` would miss the yearless form).
   Verified against the live 130-doc `svl_pdfs/` corpus: only MANUÁL KÓDŮ matches; no legitimate
   guideline contains "PRO VPL".

3. **Reject, not quarantine.** The guard records an error doc_status via
   `apipeline_enqueue_error_documents` (the same path used for filename-hint / read errors) with a clear
   `Out-of-corpus document rejected` description, logs a warning, and returns `(False, track_id)`. The
   doc never enters `apipeline_enqueue_documents`, so no chunks/entities/relations. An explicit rejection
   (vs a silent skip) is preferred so a human sees why in the doc-status error list.

4. **Scope — seed MANUÁL KÓDŮ, keep extensible.** `INGEST_DENYLIST` is a tuple; the next out-of-corpus
   mako/ÚZIS doc is a one-line addition.

## Acceptance

- A documented config-as-code denylist (`INGEST_DENYLIST`) is checked on the ingest path.
- Offline: `denylisted_reason` matches every MANUÁL KÓDŮ filename form (`_unknown`, `_2026`, yearless,
  NFD spelling, mixed case) and does **not** match any legitimate guideline filename.
- Offline: `pipeline_enqueue_file` on a denylisted PDF returns `(False, track_id)`, records one error
  doc_status, and never calls `apipeline_enqueue_documents` (0 enqueued).
- The scoped offline suite (`tests/{api,promotion,pipeline}`) stays green (staging has no CI gate).

## Non-goals

- Content-fingerprint matching (filename substring is sufficient for the known out-of-corpus docs).
- A management endpoint / UI to edit the denylist (config-as-code edit + deploy, per platform convention).
- Retroactive cleanup of already-ingested out-of-corpus docs (done for MANUÁL KÓDŮ in brief 016 §B; this
  spec is prevention only).
