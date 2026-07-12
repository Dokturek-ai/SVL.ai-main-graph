# Spec 014 — retrieve v2: apply concept_ref + facet (the focus filter)

**Status:** specify.
**Source:** brief `2026-07-01-agent-to-guidelines-retrieve-endpoint-contract` (open, from dokturek-agent) +
probe `scratch/probe_conceptref_chunks.py`. Unblocks agent-guidelines-grounding (A4).

## Problem

`POST /v1/guidelines:retrieve` (spec 002) already accepts the agent's exact shape
`{query, facet, concept_ref{mkn10_code,cui}, top_k}` — but v1 **echoes `facet`/`concept_ref` without
applying them** (`filtered` is hard-coded `false`, "chunks untagged"). So a code-scoped focused query
still ranks over the whole corpus; the two focus levers the agent needs are inert.

The brief wants: **(1) the code FILTERS the corpus** to the dg's chunks, **(2) query+facet RANK** → return
`top_k` focused spans (not a DP dump), **(3) guidelines-side** focusing (agent doesn't pull-all-and-rerank),
**(4) resilient** — unresolvable → plain-retrieval fallback, no regression.

Now unblocked: the harvest/join fix populated `concept_ref` on graph **entity** nodes (3925), so a
code→chunks mapping exists where v1's "chunks untagged" assumed none. Probe: 2242 grounded codes;
`I10`→256 chunks, `E11`→124, `J45`→48 (median 2, 0 codes with no chunk). ⚠ dotted/dotless fragments the map
(`E11`→124 vs `E119`→2) → must dot-normalize + match the code family.

## Decision

Extend the endpoint (still a thin router — no `operate.py`/engine edits), v1 shape unchanged, v1 behaviour
preserved when the levers are absent.

1. **concept_ref filter (query-time, no chunk pre-tagging).** Resolve `mkn10_code` → the set of chunks
   grounded to it: entities whose `concept_ref` code matches (DOT-NORMALIZED, bidirectional 3-char-family
   prefix so `I10` pulls `I10.9` and `E11.9` pulls its `E11` category) → their `source_id` chunk ids. Build
   this `code→chunks` index once and **cache it** (TTL; the graph changes only on re-ground/dedup). At
   retrieve: pull a larger candidate pool (`chunk_top_k = max(top_k×N, floor)`), **post-filter** to the
   code's chunk-set, return the top `top_k`. Set `filtered=true` only when the filter was applied and left
   ≥1 passage.
2. **facet (derive from the section heading — no G2 tagging pass).** The passage already resolves its
   section-heading path (spec-004 provenance). Classify it to the enum
   (`diagnosis|treatment|dosing|followup|contraindication`) with a CZ keyword map; populate
   `passage.facet`. If `request.facet` is set, keep only matching passages (rank/filter).
3. **Resilience.** `concept_ref` unresolvable / code not in the index / filter empties the result → **fall
   back to plain retrieval** (`filtered=false`), never error, never worse than v1.

### Non-goals
- Pre-tagging chunks with `concept_ref`/facet at ingest (the `chunk-concept-ref-tagging` / G2 path) — a
  heavier, separate track; query-time resolution ships the contract now.
- A new retrieval mode / engine change; `cui` resolution (only `mkn10_code` is wired this spec).

## What ships
- v2 filter/rank in `guidelines_routes.py` + a small pure module for code-match + facet-classify (unit-tested
  offline). `filtered` reflects reality; `passage.facet`/`passage.concept_ref` populated.
- Live-verify (a code-scoped query returns a focused, in-scope subset) is a gated step post-merge.

## Acceptance (from the brief)
- `{concept_ref, query, facet, top_k}` → ≤`top_k` cited spans, not a data dump; the focus really narrows a
  whole DP to a handful of in-scope passages; unresolved code/facet → graceful plain-retrieval fallback.
