# Plan 013 — entity-name casing/whitespace dedup

## Canonical key (settled by probe)

Reuse `lightrag/promotion/canonicalize.py:merge_key` as the single canonicalization authority for BOTH the
live graph (this spec) and the bundle (promotion, already). No new key. Probe `probe_mergekey_falsemerge.py`:
merge_key collapses 6 484 nodes (16.26 %), adds only accent-typo catches over the narrow key, **0 new false
merges**. Display name = deterministic min of a cluster's variants (mirrors `promote.py` `canonical_name`).

## Part 2 first — MIGRATE (delivers the measured quality now; lower risk, reuses a public API)

One-shot maintenance routine (`scripts/dedup/` or a `lightrag-graph-dedup` entrypoint; ad-hoc probe already
in `scratch/`). Steps:

1. **Plan (pure, dry-run default).** Pull the live graph, cluster node names by `merge_key`. For each
   cluster >1 node compute: survivor (1 grounded → it; else highest-degree; else lexmin), sources = rest.
2. **Reconcile concept_ref.** Normalize codes first: **dot-normalize** (`N48.4`≡`N484`) and treat
   **category⊃specific of the same 3-char family** (`N18`⊃`N18.9`) as compatible → survivor keeps the
   most-specific verified ref. Measured (`probe_true_conflicts.py`): 51 raw → 35 dot-normalized → **28
   category/specific (compatible) + 7 genuinely-different-family**. Only those **7** (I21/I25.2, E11.2/E14.2,
   M00.9/M01.8, N18.9/N28.9, H53.9/H58.1, I10/O10.0, E10/O24.0) → **skip the cluster, log to
   `dedup-conflicts.jsonl`**; never auto-pick. 2 of the 7 (I10/E10 vs pregnancy O10.0/O24.0) are grounding
   errors → separate grounding brief. Side note: codes are stored inconsistently dotted/dotless in the graph
   (the consumer dot-strips, so harmless downstream) — a canonical-code-form normalization is a separate
   small cleanup, not this spec.
3. **Merge.** `rag.amerge_entities(source_entities=sources, target_entity=survivor)` per clean cluster
   (default strategy: description=concatenate, entity_type=keep_first, source_id/file_path=join_unique;
   handles graph + entity-vdb + relation-vdb + KV atomically under its own locks).
4. **Dry-run prints the full plan** (cluster → survivor, #sources, code-reconcile decision, skipped
   conflicts) BEFORE any mutation; `--apply` executes.

**Safety:** read-only plan is reviewable; `amerge_entities` is the framework's own tested merge (not a
hand-rolled Neo4j/PG migration); conflicts are skipped not guessed; idempotent (a second run finds ~0
clusters). The live RUN is **gated** (production-staging write — owner go, like the promote), then re-probe.

## Part 1 — PREVENT-NEW (stop re-accumulation on future ingests)

`merge_nodes_and_edges` (operate.py:2952) groups by raw `entity_name` (`all_nodes[entity_name]`, line 3008);
the entity name is the storage key across Neo4j + PGVector + KV, and `_handle_single_entity_extraction`
(operate.py:448) normalizes via `sanitize_and_normalize_extracted_text` which does NOT casefold. Two options
(the ONE open decision — flagged for the owner before implementing):

- **(A) Core ingestion change.** Canonicalize the entity name at the `merge_nodes_and_edges` choke point:
  group by `merge_key`, resolve to a canonical display via a persistent registry (KV: `merge_key →
  display`, first-seen or lexmin), so the canonical name is what reaches every store. True prevention.
  Cost: touches LightRAG core (fork divergence from upstream on rebase), a new KV, and concurrency care on
  the registry under parallel chunk processing.
- **(B) Dedup-maintenance pass.** No core change — run Part 2's routine as a **post-ingest maintenance
  step** (and on a schedule). Reuses the migration code, non-invasive, fork stays clean. Cost: a window
  where new dups exist between an ingest and the next pass (acceptable for a low-frequency, mostly-static
  corpus where ingest is a rare, embed-bottlenecked event).

**Recommendation: (B).** Simplicity (§2) + fork-divergence cost of core changes + the corpus is mostly
static and re-ingest is infrequent. (A) is the "correct" prevention but only pays off under frequent
incremental ingest, which is not the current regime; revisit if that changes. Escalating this fork to the
owner (it decides whether we mutate fork-core).

## Testing

- **Migration (pure units):** cluster-planning + survivor-selection + concept_ref reconcile (compatible vs
  conflict) on a fixture node set — no live graph. Conflict clusters are skipped+logged.
- **Prevent-new:** depends on the fork above. (B) → the maintenance routine's units cover it. (A) → an
  ingest unit: `eGFR` then `EGFR` → one node, display `eGFR`, union of edges.
- **Offline suite** stays green (no regression). Live verification (re-probe → clusters ~0) is a gated
  ops step post-merge, captured as a landing brief.

## Rollout

1. Land routine + tests in the PR (code only, no live mutation).
2. Dry-run against staging (read-only) → review the plan + conflict log.
3. Owner go → `--apply` on staging → re-probe (`probe_casing_dedup_live.py`) → clusters ~0.
4. The ~47 code-conflict clusters → a follow-up grounding-consistency brief (which code is right).
5. If prevent = (A): the core change ships in the same PR; if (B): the maintenance schedule is wired.
