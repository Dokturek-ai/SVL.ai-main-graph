# Spec 013 — entity-name casing/whitespace dedup (prevent-new + migrate)

**Status:** specify.
**Source:** brief `guidelines-entity-name-casing-dedup` (open, `to: dokturek-guidelines`) + live probe
`scratch/probe_casing_dedup_live.py`. Scope = **full (prevent + migrate)**, owner decision 2026-07-12.

## Problem

The entity **name is the primary key** of a graph node across every store (Neo4j node id, PGVector entity
id, PGKV). Extraction normalizes HTML/quotes/whitespace (`normalize_extracted_info`) but **never casefolds**,
and the in-doc merge groups on the exact name (`merge_nodes_and_edges` → `all_nodes[entity_name]`). So the
same concept extracted with different casing/spacing becomes **distinct nodes**.

Measured on the live staging graph (39 873 nodes, `probe_casing_dedup_live.py`, key = `entity_id`):

- **5 712 casing/whitespace dup clusters**, 11 633 nodes, **5 921 collapsible = 14.85 % of the graph**.
- **658 clusters are grounded-INCONSISTENT** — one variant carries `concept_ref`, its casing-twin does not
  (`oGTT`○/`OGTT`✓/`Ogtt`○; `Diabetes Mellitus 2. Typu`✓/`…2. typu`○; `Laboratorní Vyšetření`✓/`laboratorní
  vyšetření`○).
- Textbook clusters: `eGFR`/`EGFR`/`EgfR`/`Egfr`; `TSH`/`Tsh`/`TsH`; `ACEI`/`ACEi`/`Acei`; `EKG`/`Ekg`/`EkG`.

**Cost (why it's not cosmetics):** each variant holds its own embedding + a *subset* of the concept's edges
and anchors → (1) **retrieval fragmentation** at query time (a query hits one casing-variant, sees only its
edges/chunks, misses the twins'; near-identical variants pollute top-k), (2) **split `concept_ref` join** —
a query/harvest landing on the ungrounded twin misses the code that sits on the grounded one. The promotion
pass already casefold-canonicalizes the **bundle** (bundle = 0 dups), so mkn10's join is unaffected — but
**query-time retrieval hits the live graph, where the split is real.**

## Decision

Entity identity is **case- and whitespace-insensitive**. Two parts, both shipped:

1. **Prevent-new (core).** An entity resolves to a node by a **normalized key** (casefold + whitespace-
   collapse), not the raw surface form. First-seen surface form is kept as the node's **display**; later
   casing/whitespace variants resolve to and merge into it. Dedup is guaranteed regardless of which casing
   wins; the display stays human-correct (`eGFR`, not `egfr`). Fix point + mechanism (in-batch grouping key
   vs storage-layer normalized resolution vs reuse of the promotion canonicalizer) → `plan.md`.

2. **Migrate existing (one-shot).** Collapse the 5 921 existing dups via the first-class
   `amerge_entities` API (handles graph + entity-vdb + relation-vdb + KV; default strategy
   description=concatenate / entity_type=keep_first / source_id+file_path=join_unique). **Survivor per
   cluster:** the single grounded node if exactly one is grounded, else the highest-degree node, else
   lexicographically-first (determinism). `concept_ref` reconciliation: survivor inherits the grounded
   ref; a cluster with *conflicting* codes across variants (should be ~0 for casing-only) is logged and
   left for manual review, never auto-merged blind.

### Non-goals (explicitly OUT)

- **Word-order / qualifier / synonym merge** (`Rýma Alergická` ≡ `Alergická Rýma`, `Sezonní Alergická
  Rýma`→J30.2 vs `Alergická Rýma`→J30.4). Those can carry **distinct codes** → a different, riskier merge.
  This spec is casing+whitespace ONLY (identical letters ⇒ identical concept ⇒ safe).
- Changing a display beyond casing/whitespace; touching the promotion canonicalizer (bundle already clean).
- Re-ingesting the corpus (migrate in place; embed is the bottleneck — see `guidelines-ingest-embedding-setup`).

## What ships

- **Code (prevent-new):** case-insensitive entity resolution + unit tests (casing/whitespace variants
  collapse to one node, display preserved, no regression in existing extraction tests).
- **Migration script** (`scratch/` or a `--dedup` maintenance entrypoint) using `amerge_entities`, with a
  dry-run that prints the cluster/survivor plan before mutating.
- **Live migration RUN is GATED** (production-staging graph write) — like the promote: land code+script+tests
  in the PR, run the migration against staging on explicit owner go, then re-probe.

## Acceptance

- `probe_casing_dedup_live.py` after migration: casing/whitespace dup clusters **→ ~0**; grounded-
  inconsistency clusters → 0.
- A prevent-new unit test: ingesting `eGFR` then `EGFR` yields ONE node (display `eGFR`), union of edges.
- Existing extraction/offline suite green (no regression).
- Spot-check: a merged concept's surviving node carries the **union** of its variants' edges + the
  `concept_ref` (retrieval no longer fragmented).
