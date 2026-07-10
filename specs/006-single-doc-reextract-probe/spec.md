# Spec 006 — single-document re-extract probe

**Status:** implemented (offline plumbing tested; live LLM run pending — no LLM in build env)
**Source:** brief `mkn10-to-guidelines-typed-oriented-edges-contract` — the "Enabler (build FIRST)" section.

## Problem

The typed-edges contract's Phase 0 (clean the entity extraction) is iterated **one document at a
time** — strategic probes + tests, full-corpus re-extract only once the per-doc probe clears mkn10's
ruler (owner+mkn10 decision, 2026-07-10). That loop needs a way to **re-run entity extraction on a
single DP's already-stored chunks with a tightened prompt, cheaply, without re-parsing the PDF**. No
such path existed — extraction only ran inline during initial ingest.

## Requirements

- **R1 — `LightRAG.areextract_document(doc_id, entity_types_guidance=None)`.** Fetch the doc's chunk
  ids (`doc_status.chunks_list`) → `text_chunks.get_by_ids` → run `extract_entities` over them.
  Returns `{doc_id, chunks, entity_count, relation_count, entities[], relations[]}` for inspection.
  - **No PDF re-parse** — reads persisted chunks only.
  - **No graph mutation** — `merge_nodes_and_edges` is NOT called; nothing is reified into the KG.
    (Extraction may still write the LLM response cache + chunk cache-tracking; it never touches the
    graph, vector stores, or doc status.)
  - **Per-call prompt override** — when `entity_types_guidance` is given, inject a resolved prompt
    profile into a per-call COPY of `global_config` (`_entity_extraction_prompt_profile`); never
    mutate `self.addon_params` (that would race concurrent probes).
- **R2 — `POST /documents/{doc_id}/reextract`.** Body `{entity_types_guidance?}`; returns the R1
  result. `combined_auth`. Missing doc / no chunks → 404.

## Non-goals

- Persisting the re-extraction (a commit/merge path for mkn10 to harvest a slice) — deferred; the
  probe returns the extraction for direct inspection, which is what the contract's "inspect the
  LightRAG output directly" acceptance needs.
- The tightened clinical-only prompt itself (that is the Phase-0 content the probe helps iterate).
- Full-corpus re-extraction.

## Verification

- Offline unit tests (`tests/test_reextract_probe.py`, LLM monkeypatched): chunk fetch by doc_id, the
  guidance override reaching extraction via the injected profile, `addon_params` left unmutated,
  result serialization, not-found / no-chunks → `ValueError`.
- **Live run pending** (build env has no LLM): hit `POST /documents/{doc_id}/reextract` on staging for
  one DP, with and without a tightened guidance, and inspect the entity list — tracked as a brief.
