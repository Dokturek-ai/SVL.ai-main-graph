# Plan 016 — `_unknown` edition-year resolution

**Status:** plan.

## Approach

Two deliverables, independent:
1. **One-off rename** (the safety fix) — a server-side maintenance pass renames the 6 `_unknown` docs'
   `file_path` to their verified year, mirroring the spec-013 dedup endpoint shape.
2. **Durable resolver** (prevent recurrence) — an ingest-time step resolves the year from the PDF and bakes
   it into the stored `file_path`, so `_unknown` is never emitted when a year is recoverable.

## 1. One-off rename

### Verified mapping (frozen from `scratch/extract_unknown_years.py` + title-page check)
```
Akutní průjem_unknown.pdf                                          -> _2023
Bolesti hlavy_unknown.pdf                                          -> _2023
Chronická tromboembolická plicní nemoc CTEPD ... CTEPH_unknown.pdf -> _2024
Včasný záchyt chronických jaterních chorob_unknown.pdf            -> _2025
Virová hepatitida C_unknown.pdf                                    -> _2023   # title page NOVELIZACE 2023
Vybraná onkologická onemocnění_unknown.pdf                        -> _2023
```

### Pure module `lightrag/maintenance/edition_rename.py`
- `RENAMES: dict[str, str]` — the 6 old→new `file_path` strings above (the frozen, human-verified mapping;
  NOT re-derived at runtime — the title-page catch for hepatitida is a judgement the code shouldn't redo).
- `plan_rename(live_file_paths: list[str]) -> RenamePlan` — intersect `RENAMES` with what's actually in the
  store; classify each into `load_bearing` (exact-match tables) and report which are already renamed (no-op /
  idempotent). Returns counts + the concrete `(old, new)` list. Pure, unit-tested.
- No SQL in the module (keeps it DB-agnostic + testable); the runner owns IO.

### Runner + endpoint (`graph_routes.py`, mirrors `_run_dedup`)
- `POST /graph:rename-edition?apply=` — `apply=false` dry-run returns the plan summary (which docs rename,
  which are already done); `apply=true` runs in the background, `check_pipeline_busy_or_raise` first, status
  at `/graph:rename-edition/status` (same stale-heartbeat guard as dedup).
- Production backends = PG + Neo4j; the runner executes directly against them (no new abstract storage
  method for a one-off — YAGNI):
  - **Load-bearing, whole-value UPDATE** (`= old`): `LIGHTRAG_DOC_STATUS`, `LIGHTRAG_DOC_CHUNKS`,
    `LIGHTRAG_VDB_CHUNKS` — via `rag.doc_status.db.execute(...)` (the PG storages share one `db` pool),
    scoped by `workspace`. This is what fixes edition ordering.
  - **Provenance, substring REPLACE** (`REPLACE(file_path, old, new)`): `LIGHTRAG_VDB_ENTITY`,
    `LIGHTRAG_VDB_RELATION` — the `<SEP>`-joined value; capped rows that dropped `_unknown` are silently
    fine (nothing to replace).
  - **Neo4j**: `MATCH (n) WHERE n.file_path CONTAINS $old SET n.file_path = replace(n.file_path,$old,$new)`
    for nodes; the same for relationships. `source_id` is NOT touched (it is chunk-ids, not file paths).
- Idempotent: a second apply matches 0 `_unknown` rows.

### Live run + verify (after deploy)
- `POST /graph:rename-edition?apply=false` → confirm 6 planned; `apply=true` → poll status done.
- Re-probe (extend `scratch/probe_unknown_editions_live.py`): 0 `_unknown` file_paths remain; re-ask the
  hepatitida edition query — the answer/bundle now treat 2023 as latest over 2015 (`superseded_by_edition`
  points the right way).

## 2. Durable resolver

### `resolve_edition_year(pdf_path) -> str | None` (new, near the ingest filename handling)
Priority (returns the 4-digit year, or None → keep `unknown`):
1. year already in the filename stem (`_EDITION_RE` from `edition.py`) → trust it, skip the scan.
2. **title-page stated year**: `fitz` open, first 1-2 pages text, regex `NOVELIZACE\s+(20\d{2})` then a
   bare `20\d{2}` on the title page → the content's edition (authoritative; hepatitida = 2023).
3. **PDF `CreationDate`**: `doc.metadata["creationDate"]` `D:(20\d{2})` → fallback proxy.
4. else None.

### Hook (`document_routes.py`, where the on-disk PDF name becomes the stored `file_path`, ~:1864)
When the incoming filename stem has no year and the file is a PDF, call `resolve_edition_year`; if it returns
a year, rewrite the stored `file_path`/doc name stem to `<work>_<year>.pdf` before the pipeline stores it.
Non-PDF / unresolvable → unchanged (`_unknown` or the bare stem, as today). Log the resolution + its source
(filename/title/creationdate) for auditability.

## Tests (offline, no LLM / no DB)
- `tests/maintenance/test_edition_rename.py` — `plan_rename`: the 6 map correctly; idempotency (already-`_year`
  paths → no-op); a path not in `RENAMES` is untouched; empty store → empty plan.
- `tests/promotion/` or `tests/parser/` `test_resolve_edition_year.py` — on tiny fixtures / mocked `fitz`
  metadata+text: filename-year wins; title `NOVELIZACE 2023` beats CreationDate 2025 (the hepatitida case);
  CreationDate used when no title year; None when nothing resolves.

## Risks / notes
- `file_path` has a composite index (`idx_lightrag_doc_status_workspace_file_path`); a whole-value UPDATE is
  fine (index maintained automatically). Confirm no FK/PK on `file_path` — audited: it's an attribute, keys
  are `id`/`doc_id`/`chunk_id`.
- The rename does NOT rebuild the promotion bundle; a bundle rebuild (`promote`) after the rename picks up the
  corrected editions — note as a follow-up run, not part of this endpoint.
- Provenance substring-replace incompleteness (truncated entity file_paths) is accepted (spec non-goal); the
  source chip may still read `_unknown` on a few heavily-shared entities. Edition ordering is unaffected.

## Order (per-phase commits)
plan → tasks → implement [pure module + tests → endpoint/runner → durable resolver + tests] → caveman-review
→ deploy staging → live rename + verify. No squash.
