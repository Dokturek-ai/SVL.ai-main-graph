# Spec 015 — chunk metadata: persist concept_ref + facet tags (the durable layer)

**Status:** specify.
**Source:** briefs `2026-06-25-platform-to-guidelines-chunk-concept-ref-tagging` +
`2026-07-01-agent-to-guidelines-chunk-facet-section-tag` (both open, `to: guidelines`; same chunk-metadata
layer). Probe `scratch/probe_conceptref_chunks.py` + the offline propagation probe.

## Problem

Spec 014 (retrieve v2) applies `concept_ref`/`facet` at **query time**: it rebuilds an entity
`concept_ref`→chunk index per request (`get_knowledge_graph`) and classifies facet from the section heading.
That shipped B (concept-aware retrieve) and unblocked the agent, but it is:
- **not exact** — the code filter post-filters a query-ranked pool (pool-exhaustion limit);
- **not persistent** — the A-harvest (reify guideline facts onto mkn10 codes) can't reuse a query-time join;
- **fragile at runtime** — the per-request `get_knowledge_graph` is a large read that **500s under graph
  mutation** (observed during the spec-013 dedup → retrieve degraded to plain).

The fix is the layer both briefs asked for: **persist `concept_ref` + `facet` ON the chunk**.

## Decision

**Propagation, not fresh resolve.** Grounding already resolved `concept_ref` onto **entities** (3925 nodes,
mkn10-canonical, verified). A chunk inherits the `concept_ref`s of the entities whose `source_id` includes
it — the inverse of spec-014's `build_code_index`. No per-chunk mkn10 call; reuses the verified grounding.
Offline propagation probe: 3925 grounded entities → **1384 chunks tagged**, median 7 codes/chunk (a guideline
chunk mentions several dg). `facet` = `classify_facet(chunk.section)` from the sidecar provenance (already
resolved, spec 004) — one facet per chunk.

1. **Chunk tags.** Each chunk record gains `concept_ref: [{code, system}]` (the union over its grounded
   entities; empty when none ground) + `facet: <enum|null>` (from its section heading) + provenance kept.
2. **Backfill pass (one-time, idempotent, re-runnable).** Iterate the store's chunks; compute tags by
   propagation; upsert onto the chunk KV record. Re-run as grounding grows (null today → tagged later).
   Emits a coverage report (tagged / multi-code / facet distribution).
3. **Resolve-at-ingest (forward).** New DP chunks get tags in the ingest pipeline — deferred to a follow-up;
   the backfill is the immediate deliverable.
4. **retrieve v2 reads the persisted tag** instead of building the query-time index — kills the
   cold-start/contention + makes the code filter exact. A thin follow-on wiring (spec 014 stays the
   fallback when a chunk is untagged).

### Non-goals
- A-harvest itself (reify facts onto mkn10 codes) — this is its **enabler**, briefed separately.
- Re-ingesting the corpus (propagate in place). Mutating the raw guideline text (tags are metadata).
- `cui` (only the mkn10 `code` propagates; CUI stays mkn10's).

## What ships
- Pure propagation module (`chunk_tags.py`): `build_chunk_tags(entities, sections)` → `chunk_id →
  {concept_ref, facet}`. Unit-tested offline (invert, union, facet, empty).
- Backfill entrypoint (server-side, mirrors the dedup/promote pattern — the store is internal-only) with a
  dry-run coverage report + `apply`. **Live run gated** (post-dedup — the graph read contends during a mass
  mutation).

## Acceptance
- Every clinically-grounded chunk carries `concept_ref` (or explicit null) + `facet` + provenance; backfill
  is idempotent; a coverage report is emitted (≈1384 code-tagged chunks on the current grounding).
- (follow-on) retrieve v2 reads the chunk tag → exact code filter, no per-request `get_knowledge_graph`.
