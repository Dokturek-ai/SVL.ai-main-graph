# Tasks 001 — Verifiable ingest

Implements `plan.md`. One phase = one commit (no squash). `[ ]` = todo. Each task names its **verify**.

## P0 — scaffold + fixture (prereq for all golden tests)
- [ ] T001 Create `promotion/` package + `promotion/types.py` (dataclasses: `ChunkRecord`, `Anchor`, `GroundedNode`, `GroundedEdge`, `Quarantine`, `Manifest`). → verify: `import promotion.types` clean; `ruff` clean.
- [ ] T002 Author the golden fixture `tests/promotion/fixtures/two-edition-corpus/{chunks,nodes,edges,docs}.jsonl` — two editions of one work, containing: a restated fact (overlap), a changed fact (conflict), an ungroundable entity (quarantine), an inflected surface form (stemmed match), a case-variant name pair. → verify: fixture loads; documented in a fixture README.

## P1 — G2 chunk registry + harvest
- [ ] T010 `promotion/harvest.py` (impure): read `get_all_nodes`/`get_all_edges` + chunk KV + `get_docs_by_status`, write verbatim `snapshot/{nodes,edges,chunks,docs}.jsonl`. No transform. → verify: opt-in smoke against live deployment yields a well-formed snapshot (network-gated, not in CI).
- [ ] T011 `promotion/registry.py`: build `chunk_id → ChunkRecord` from `snapshot/chunks.jsonl` (+ `content_hash`). → verify: `test_registry` — 100% of fixture `source_id`s resolve.
- [ ] **Commit** `feat(001): G2 chunk registry + store harvest`.

## P2 — G1 verify-or-quarantine promotion spine
- [ ] T020 `promotion/locate.py`: `locate(surface_form, chunk_text)` — normalized-substring → stemmed-window fallback (threshold) → `Anchor | None`. Pure, table-driven Czech suffix stripping (no heavy dep). → verify: `test_locate` covers exact, diacritic, case, inflected ("krevního tlaku"), and a true miss.
- [ ] T021 `promotion/promote.py` (pure spine): join nodes/edges → registry; entity admitted iff locatable; edge admitted iff both endpoints locatable in the chunk; else quarantine with reason (`entity-not-found`/`endpoint-missing`/`chunk-unresolved`). Emit `GroundedNode/Edge` with `fidelity="verified"` + anchor; write `quarantine.jsonl`. → verify: `test_promote` — every emitted record has an anchor (coverage 100% by construction); each quarantine reason exercised; nothing silently dropped (emitted + quarantined = input).
- [ ] **Commit** `feat(001): G1 verify-or-quarantine + anchor spine`.

## P3 — G3 edition lineage + supersession + conflict flags
- [ ] T030 `promotion/edition.py`: `(work_id, edition_date)` from filename (`Work_YEAR.md`) + override manifest; total-order editions per work. → verify: `test_edition` parses corpus-style names + an override.
- [ ] T031 Wire into `promote.py`: stamp `as_of = edition_date` on every fact; default view = latest edition; older-only fact → `superseded_by_edition`; fact-key `(canonical_head, rel_type, canonical_tail/attr)` same-value across editions = overlap, different-value = **conflict flag** (review artifact, not resolved). → verify: `test_promote_editions` on the 2-edition fixture — latest-default, one supersession, one conflict flag.
- [ ] **Commit** `feat(001): G3 edition as_of + supersession + conflict flags`.

## P4 — G4 versioned bundle (hash first), then delta + ratchets
- [ ] T040 `promotion/bundle.py`: canonical-sort records; stable ids (`node_id=sha1(name,type)`, `edge_id=sha1(head,rel,tail,work,edition)`); write `nodes.jsonl + edges.jsonl + manifest.json`; manifest = content hash over sorted records + corpus (per-doc hash + edition) + pins (library version, prompt hash, code SHA) + counts (incl. `anchor_coverage=1.0`, `doc_coverage`). → verify: `test_bundle` — re-emit of identical snapshot → **byte-identical** manifest hash; determinism holds across runs.
- [ ] T041 `promotion/delta.py`: bundle vs previous → added/removed/changed by stable id. → verify: `test_delta` — a changed fixture yields the expected add/remove/change set; a removal with no corpus change is flagged.
- [ ] T042 `promotion/ratchets.py`: quarantine-rate non-increasing, anchor-coverage 100%, doc-coverage non-decreasing, **orphan-rate non-increasing** vs the previous manifest; manifest counts include `orphan_rate` + `edge_node_ratio`. → verify: `test_ratchets` — a regression trips each ratchet incl. an orphan-rate spike.
- [ ] T043 `promotion/cli.py`: `python -m promotion harvest|promote|delta`. → verify: `--help` + a fixture end-to-end run.
- [ ] **Commit** `feat(001): G4 snapshot bundle + manifest hash + delta + ratchets`.

## P5 — G5 typing + canonicalization
- [ ] T050 `promotion/enums/entity_types.yaml` (~5–15 controlled kinds) + `promotion/canonicalize.py`: name normalization (case/diacritics/whitespace/punct) + versioned `aliases.yaml`; validate type ∈ enum at promotion (else `other` or quarantine). → verify: `test_canonicalize` — `Praktický lékář`/`Praktický Lékář` merge; alias applied; off-enum type handled.
- [ ] T051 Confirm the entity-type enum is injected into extraction via LightRAG `entity_types` config (the deployment already has `default_entity_types_guidance`/`{entity_types_guidance}` scaffolding) — document the config wiring; validate at promotion regardless. → verify: note in spec/plan; no live re-ingest required here.
- [ ] **Commit** `feat(001): G5 entity-type enum + name canonicalization + alias table`.

## Close-out
- [ ] T060 Full `tests/promotion/` green (`pytest -m offline`), `ruff` clean. → verify: CI-equivalent local run.
- [ ] T061 **caveman-review** the diff (spawn `cavecrew-reviewer`); triage + fix real findings.
- [ ] T062 Home-repo lifecycle: PR against `main`; merge (merge-commit/rebase, **no squash**) once review clean.
- [ ] T063 Loose-end briefs (central `docs/briefs/`): landing/verification for a **live promotion run** (harvest real store → bundle) since CI only covers the pure part; confirm the two child briefs (`guidelines-pdf-reingest-for-anchors`, `guidelines-edition-conflict-live-test`) still stand; feedback stub back to `verifiable-ingest-design`.

## Notes
- **STOP GATE:** implementation (P0→P5) begins only on explicit owner OK (this deliverable is spec+plan+tasks).
- Page/bbox anchors, live edition-conflict test, mkn10 consumption, semantic dedup, §5/CORS nits → out of scope (see `spec.md`).
