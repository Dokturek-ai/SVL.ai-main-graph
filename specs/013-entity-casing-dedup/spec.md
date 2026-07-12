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

1. **Prevent-new.** An entity resolves to a node by a **canonical key**, not the raw surface form. The key
   is the **existing, proven `lightrag/promotion/canonicalize.py:merge_key`** (casefold + strip diacritics +
   strip punct + collapse whitespace + alias-table) — the SAME function promotion already uses to
   canonicalize the bundle. Reusing it (vs a new narrow casing+ws key) gives **live↔bundle consistency by
   construction** and is proven. A false-merge probe (`scratch/probe_mergekey_falsemerge.py`) confirms it is
   safe: `merge_key` collapses 6 484 nodes (16.26 %) vs the narrow key's 5 921, and adds only accent-typo
   catches (`Migréna`≡`Migrena`, `Dyslipidémie`≡`Dyslipidemie`) — **no new false merges** (the ~47 clusters
   whose members carry different codes exist under BOTH keys and are a grounding-consistency artifact, not an
   over-merge). Display = the deterministic min of the group's variants (mirrors `promote.py`). Fix point +
   mechanism → `plan.md`.

2. **Migrate existing (one-shot).** Collapse the 5 921 existing dups via the first-class
   `amerge_entities` API (handles graph + entity-vdb + relation-vdb + KV; default strategy
   description=concatenate / entity_type=keep_first / source_id+file_path=join_unique). **Survivor per
   cluster:** the single grounded node if exactly one is grounded, else the highest-degree node, else
   lexicographically-first (determinism). `concept_ref` reconciliation (measured, `probe_true_conflicts.py`):
   normalize codes first — **dot-normalize** (`N48.4`≡`N484`, 16 fake conflicts gone) and treat
   **category⊃specific of the same 3-char family** as compatible (`N18`⊃`N18.9`, `I50`⊃`I50.9` — 28
   clusters, keep the most-specific). That leaves only **7 genuinely-different-family conflicts** (I21 vs
   I25.2, E11.2 vs E14.2, M00.9 vs M01.8, N18.9 vs N28.9, H53.9 vs H58.1, **I10 vs O10.0**, **E10 vs O24.0**)
   → **logged, left unmerged**, never auto-merged. Two of the seven (I10/E10 vs the pregnancy-context
   O-codes O10.0/O24.0) are real grounding ERRORS (a pregnancy-chapter poison the `clinical_only` filter
   doesn't catch) → a follow-up grounding brief, not a dedup concern.

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
