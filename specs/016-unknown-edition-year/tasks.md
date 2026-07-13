# Tasks 016 — `_unknown` edition-year resolution

## Phase A — pure rename module + tests
- [ ] A1. `lightrag/maintenance/edition_rename.py`: `RENAMES` (6 frozen old→new), `RenamePlan` dataclass,
      `plan_rename(live_file_paths)` (intersect with store, count renamable / already-done / absent).
- [ ] A2. `tests/maintenance/test_edition_rename.py`: 6 map correctly; idempotent (already `_year` → no-op);
      unknown path untouched; empty store → empty plan. → verify: `pytest tests/maintenance/test_edition_rename.py`.

## Phase B — endpoint + runner
- [ ] B1. `graph_routes.py`: `POST /graph:rename-edition?apply=` + `/graph:rename-edition/status`, mirror
      `_run_dedup` (dry-run summary, pipeline-busy guard, background apply, stale-heartbeat status file).
- [ ] B2. Runner IO: PG whole-value UPDATE (doc_status/doc_chunks/vdb_chunks, workspace-scoped) + substring
      REPLACE (vdb_entity/vdb_relation) via the shared `db` pool; Neo4j `replace(file_path,...)` on nodes+rels.
- [ ] B3. verify: offline import/smoke of the route module (`pytest tests/api` if present, else import check).

## Phase C — durable ingest resolver + tests
- [ ] C1. `resolve_edition_year(pdf_path)` (filename-year > title `NOVELIZACE 20YY`/title `20YY` > CreationDate
      > None). Place near ingest filename handling (reuse `_EDITION_RE` from `promotion/edition.py`).
- [ ] C2. Hook it in `document_routes.py` (~:1864) — PDF + no filename year → rewrite stored stem to
      `<work>_<year>.pdf`; log resolution source. Non-PDF/unresolvable unchanged.
- [ ] C3. `tests/.../test_resolve_edition_year.py` on mocked `fitz` meta+text: filename wins; title 2023 beats
      CreationDate 2025 (hepatitida); CreationDate fallback; None. → verify: pytest.

## Phase D — review + land
- [ ] D1. caveman-review the diff; fix real findings.
- [ ] D2. deploy staging (Railway RAILPACK, `lightrag-server`); wait SUCCESS.
- [ ] D3. live: `POST /graph:rename-edition?apply=false` → 6 planned → `apply=true` → status done.
- [ ] D4. verify: re-probe → 0 `_unknown` remain; hepatitida/onkologická newest edition wins latest (chat +
      bundle). Brief acceptance met.
- [ ] D5. brief → done (central log commit); loose ends (bundle rebuild run) → follow-up brief.

## Gate
Offline suite green locally (staging has no CI gate — memory `staging-no-ci-gate`): `pytest tests/maintenance
tests/promotion -q`.
