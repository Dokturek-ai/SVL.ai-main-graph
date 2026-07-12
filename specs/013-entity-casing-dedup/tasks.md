# Tasks 013 — entity-name casing/whitespace dedup (mechanism = B, maintenance pass)

Owner decisions: scope = full (prevent + migrate); prevent-new = **B, dedup-maintenance pass** (no LightRAG
core change — the migration routine IS the prevention, re-run post-ingest). Canonical key = promotion
`merge_key`. Staging DBs are internal-only → the merge runs **server-side** (API background task, mirrors
`guidelines:promote`), never from a local rag.

## T1 — pure planner (the logic, fully unit-testable, no I/O)

`lightrag/maintenance/dedup.py`:
- `plan_dedup(nodes: list[NodeView]) -> DedupPlan` where `NodeView = {name, concept_ref, degree}`.
  - cluster by `merge_key(name)` (import from `lightrag.promotion.canonicalize`).
  - per cluster >1 distinct name: **survivor** = the sole grounded node → else highest `degree` → else
    `min(names)` (lexmin, deterministic).
  - **concept_ref reconcile:** dot-normalize codes; treat `category ⊃ specific` (shared 3-char prefix) as
    compatible → survivor keeps the most-specific verified ref. If ≥2 different 3-char families remain →
    **conflict**: exclude the cluster from merges, record in `plan.conflicts`.
  - returns `merges: [{survivor, sources, ref}]` + `conflicts: [{key, names, codes}]` + counts.
- **T1 tests** (`tests/maintenance/test_dedup_plan.py`): casing/whitespace/diacritic variants cluster;
  survivor precedence (grounded > degree > lexmin); dot-normalize collapses N48.4≡N484; category⊃specific
  compatible; genuinely-different family → conflict (excluded); empty/singleton → no-op. No live graph.

## T2 — server-side runner (mirror `guidelines:promote`)

`lightrag/api/routers/graph_routes.py` (or the guidelines router): `POST /v1/graph:dedup`
- pulls the live graph (names + concept_ref + degree), calls `plan_dedup`.
- `apply=false` (default): return the plan + conflict list (dry-run, no mutation).
- `apply=true`: background task → `rag.amerge_entities(sources, survivor)` per clean merge; write a report
  (`merged`, `skipped_conflicts`, before/after cluster count) + `dedup-conflicts.jsonl`; status endpoint
  like the promote (`running`/`done`/`failed`).
- idempotent: a second apply finds ~0 clusters.

## T3 — prevent-new wiring (mechanism B)

- Document + wire the post-ingest invocation (the maintenance pass): call `POST /v1/graph:dedup?apply=true`
  after an ingest completes (a schedule or a post-pipeline hook). Keep it a thin call to T2 — no new logic.

## T4 — gated live migration + verify (ops, not in the code PR)

- Merge the PR (code + tests) after caveman-review + offline suite green.
- Dry-run `POST /v1/graph:dedup?apply=false` on staging → review plan + the 7-cluster conflict log.
- Owner go → `apply=true` → re-probe `scratch/probe_casing_dedup_live.py` → clusters ~0.
- Follow-up brief: the 7 code-conflict clusters (grounding-consistency; incl. the 2 pregnancy-O poison
  errors I10→O10.0 / E10→O24.0).

## Verify (acceptance)

- T1 tests green; offline suite green (no regression).
- Dry-run plan on staging shows ~5 700 clusters, ~5 900 collapsible, 7 conflicts skipped.
- Post-apply re-probe: casing/whitespace dup clusters → ~0.
