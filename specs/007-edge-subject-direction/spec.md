# Spec 007 — edge subject (directional edges for the promotion bundle)

**Status:** design approved; implementation DEFERRED (folds into the combined Phase 0+1+2 extraction change / one full-corpus run).
**Source:** brief `mkn10-to-guidelines-typed-oriented-edges-contract`, field #3 (edge subject/object role + direction). Brainstormed 2026-07-10..11.

## Problem

mkn10 attaches each guideline edge to a disease concept, but cannot tell which endpoint the fact is
ABOUT (the subject) vs the other (the object). It measured `head`/`tail` in the bundle = a **63%
coin-flip**, so it has **blocked the directional fields** (`etiology_note` 62% wrong, `complication`
44%, plus `comorbidity` / `differential_diagnosis`). The direction lives in the prose; a deterministic
downstream can't recover it — it must be emitted at extraction, where the LLM reads the sentence.

## Root-cause finding (why head/tail is a coin-flip)

LightRAG's graph is **undirected by design**. Edges are merged/keyed with `tuple(sorted([src, tgt]))`
(operate.py:2898 merge, :3193 promotion storage key, :3039 lock) and the **Neo4j prod store** both
creates (`MERGE (s)-[r]-(t)`, neo4j_impl.py:1228) and reads (`MATCH (a)-[r]-(b)` + DISTINCT, :1802)
with **undirected Cypher** — so the extraction's source→target order is normalized away before
promotion ever sees it. The LLM's original order IS still present in `edge_data` at operate.py:2770
(before the sort), but nothing carries it downstream.

## Decision

- **Subject only (A), not subject+direction (B).** A probe of 64 real causal relations showed:
  `rel_type` + a known subject **determines** the object's causal role (`etiology_note` → object is the
  cause of the subject; `complication` → object is the effect; `comorbidity`/`differential` are
  symmetric). A separate `direction` field is redundant. (If a future rel_type is genuinely
  bidirectional, revisit — YAGNI for now.)
- **Explicit LLM subject tag, NOT a "source = subject" convention.** The same probe showed the LLM's
  natural source→target order is **inconsistent** — cause→effect for interventions ("X vede k Y"),
  but inverted for etiology ("Deprese ← vyvolána stresem", source=Deprese). A convention fights the
  model; an explicit tag does not.
- **Carry the subject as explicit edge DATA (a property), do NOT make the graph directed.** Making
  LightRAG directed touches 6 KG backends + core merge/lock/retrieval and heavily conflicts with the
  HKUDS upstream fork — rejected. An additive `subject` property survives the undirected merge and is
  low-conflict.

## Architecture — the signal + its pipeline path

**Signal:** relation extraction gains an explicit **`subject`** = the entity name (which MUST be the
`source` or the `target`) the fact is about. The LLM keeps its natural source/target ordering; `subject`
is tagged separately. Representation: a 6th delimited relation field (keep delimited extraction; a
JSON-mode switch is a bigger config change, out of scope), with a graceful default `subject = source`
when absent/invalid.

**Threading (each step additive):**
1. **Extract** (`operate.py` extraction-result parsing): parse `subject`; validate `subject ∈ {source, target}`; default to `source` otherwise.
2. **Edge data** (`operate.py:2770`, before the sort): add `subject` (the subject entity name) to `edge_data`. It is data, not order, so it survives the sorted-key merge.
3. **Merge reconciliation** (`_merge_edges_then_upsert`, when A→B and B→A collapse on the sorted key): keep the subject that is most frequent across the merged fragments; tie-break deterministically (first-seen). Record it as the edge's `subject`.
4. **Store** (`neo4j_impl.py` edge upsert): persist `subject` as an edge property. Additive — the undirected `MERGE`/query and the sorted lock keys are unchanged.
5. **Harvest** (`promotion/harvest.py:70`): read `subject` from the edge properties into the edge dict.
6. **Promote** (`promotion/types.py` GroundedEdge + `promote.py`): resolve the `subject` name → its `node_id`; add `subject_id` to `GroundedEdge`; the bundle edge carries `subject_id`. `object_id` is implicit (the other of head/tail).

**mkn10 consumes:** attach the directional fact to `subject_id`; the object is the other endpoint; the
cause/effect role follows from `rel_type`. Re-enables the blocked directional fields.

## Verification (probe-first, per the incremental loop)

Extend the single-doc re-extract probe (spec 006) to override the **relation** instruction (today it
overrides `entity_types_guidance` only). On a few DPs, measure:
- the LLM emits `subject` for (near) every relation, and it is `∈ {source, target}`;
- on `etiology_note` / `complication` edges, `subject` = the correct disease-of-record (spot-check
  against the sentence);
- the merge reconciliation keeps a stable subject when A→B / B→A collide.
Only after the probe clears → the subject tag joins the combined Phase 0+1+2 prompt for the one
full-corpus run; mkn10 re-judges the directional fields (target ≤ ~15% hard-wrong, from 40–62%).

## Non-goals

- A separate `direction` / cause→effect field (rel_type + subject suffices).
- Making the LightRAG graph directed (rejected — upstream-fork cost).
- Switching extraction to JSON mode.
- Implementing now — this folds into the ONE combined extraction change + full-corpus run (gated on the
  Phase-1 mkn10 spine export + the probe clearing).

## Acceptance (of the eventual implementation)

- A promotion bundle edge carries `subject_id` for directional relations; it resolves to a real node;
  the object is the other endpoint.
- Probe shows the LLM tags subject reliably (`∈ {source,target}`) and correctly on a sample.
- mkn10's directional fields drop to serve-worthy (≤ ~15% hard-wrong) on a judged slice.
