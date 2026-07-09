# Spec 003 — Hybrid grounding (span-or-chunk fidelity) in the promotion pass

**Status:** implementing
**Source:** brief `docs/briefs/2026-07-09-guidelines-promotion-grounding-strictness.md` (owner-decided 2026-07-09, hybrid)
**Relates:** spec 001 (verifiable-ingest / promotion), `guidelines-extraction-block-id-entities` (block-ID prefilter, already shipped)

## Problem

The first live promotion run over the re-ingested staging store quarantined **~53%** of the
extraction (80 280 of ~150k records). Root cause is architectural, not a bug: spec-001 requires
**span-grounding** — an entity enters only if its surface form is locatable as a verbatim/inflected
span in its source chunk — but `gpt-5.4-mini` extracts **semantic** entities (normalized, composed,
inferred labels: `Verapamil a Diltiazem`, `Blokátory AT1-Receptorů`) that never appear as a span.
Cascade: 9 884 `entity-not-found` entities → 58 568 `endpoint-quarantined` edges + 11 828
`endpoints-not-co-locatable` edges (chunk-level co-location requirement).

Losing ~half the relations may starve mkn10's downstream linkage; keeping strict span-grounding
maximizes citation defensibility. The recall/rigour trade **cannot be decided from the desk** — it
must be tested empirically by the consumer (owner ruling).

## Decision (owner, 2026-07-09) — hybrid, fidelity-flagged

Implement **Option 3**: span-anchor when locatable, else **chunk-attribute** with a `fidelity`
downgrade flag. One bundle carries both fidelities so mkn10 / the reranker-eval can compare
span-only vs span+chunk by **filtering on `fidelity`**, with no re-run. This is the only option that
*enables the empirical test* while satisfying the "the fact being in the chunk is enough" bar.

## Requirements

- **R1 — Node grounding (three-way).** For each input node:
  - a span is found in any source chunk → emit with those span anchors + `fidelity="span"`
    (current behaviour, byte-identical);
  - no span but ≥1 `source_id` resolves to a chunk → emit with a **whole-chunk anchor**
    (`Anchor.match="chunk"`, span = the full chunk) + `fidelity="chunk"`;
  - **no** `source_id` resolves at all → quarantine `chunk-unresolved` (genuinely ungrounded).
  - `entity-not-found` is **retired** as an entity quarantine reason.
- **R2 — Edge grounding (two-way).** For each input edge whose both endpoints are admitted:
  - both endpoints span-co-locate in one source chunk → `fidelity="span"` (current behaviour);
  - else both endpoints are attributable to the **same doc** as one of the edge's source chunks →
    **doc-level co-location**, whole-chunk anchor + `fidelity="chunk"`;
  - endpoint truly ungrounded (quarantined / never extracted) → `endpoint-quarantined`;
  - endpoints never share a doc → `endpoints-not-co-locatable`.
- **R3 — Schema.** Populate the existing `fidelity` field on `GroundedNode`/`GroundedEdge` with
  `"span"`/`"chunk"`. Add a `"chunk"` variant to `Anchor.match`. A merged node is `"span"` if **any**
  member grounded via span, else `"chunk"`.
- **R4 — Manifest.** Add per-fidelity counts `nodes_span` / `nodes_chunk` / `edges_span` /
  `edges_chunk` so the split is visible without opening the jsonl. `anchor_coverage` stays 1.0 (chunk
  anchors are anchors). Quarantine collapses to near-zero (only `chunk-unresolved` + genuine
  edge misses).
- **R5 — Tests.** Golden tests for the three node paths + the two edge paths + the fidelity split;
  the "nothing silently dropped" invariant (`emitted surface forms + quarantined == input`) must still
  hold; ratchets still hold (quarantine falls, does not rise).

## Non-goals

- No LightRAG substrate change — all work lives in `lightrag.promotion.promote` (pure, golden-testable).
- No re-extraction / no LLM. The deterministic gate stays the last writer (Verifiable-AI standard
  satisfied by any grounding unit).
- Noise filtering beyond the already-shipped block-ID prefilter (span-grounded ISBNs etc. are a
  separate concern; grounding ≠ value).

## Acceptance

- Hybrid emit lands with per-record `fidelity` (`span`/`chunk`); entity quarantine reflects only
  `chunk-unresolved`; edge quarantine only `endpoint-quarantined` / `endpoints-not-co-locatable`.
- Golden tests cover all node + edge paths and the fidelity split; `make test` (offline) green.
- Manifest reports the span-vs-chunk split.
- (Downstream, tracked elsewhere) a fresh live bundle re-run records the new counts + split — raised
  as a verification brief, not done here (build env has no store).
