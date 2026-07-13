# Spec 016 — resolve `_unknown` doc editions to their real year (fix supersession-inversion)

**Status:** specify.
**Source:** brief `2026-07-10-guidelines-unknown-editions-are-real-editions` (open, `to: guidelines`).
Live probes: `scratch/probe_unknown_editions_live.py` (the 6 `_unknown` docs), `scratch/extract_unknown_years.py`
(the real years from PDF metadata + title-page text).

## Problem

`parse_edition` (`lightrag/promotion/edition.py`) derives edition purely from the filename: no 4-digit year
→ `edition_date=""`, which `edition_sort_key` sorts **earliest** (`(-1, "")`). The live staging store holds
**6 `_unknown` docs**, and for two of them the `_unknown` doc is actually the **newest** edition of a
multi-edition work — so the ordering inverts and the pass treats the **older** edition as latest, marking the
newest content `superseded_by_edition`:

- **Virová hepatitida C** `_unknown` (2023) has sibling `_2015` → 2015 wrongly wins latest.
- **Vybraná onkologická onemocnění** `_unknown` (2023) has sibling `_2018` → 2018 wrongly wins.

This corrupts both the promotion bundle's supersession/`latest_view` AND the live edition-aware chat answer
(spec-016 relates: `edition-aware-live-retrieval`). Demoting the newest clinical guideline as superseded is a
patient-safety-relevant defect, not a cosmetic source-chip label. The other 4 `_unknown` docs are
single-edition (no inversion) but still carry a wrong `as_of` = "".

### Verified editions (from PDF `CreationDate` + title-page text — brief table re-confirmed live)

| `_unknown` doc | real edition | source of year | sibling | inversion |
|---|---|---|---|---|
| Virová hepatitida C | **2023** | title page "NOVELIZACE 2023" (CreationDate 2025 = re-export, rejected) | `_2015` | 🔴 yes |
| Vybraná onkologická onemocnění | **2023** | CreationDate 2023-12 + text | `_2018` | 🔴 yes |
| Akutní průjem | **2023** | CreationDate 2023-12 + text | — | no |
| Bolesti hlavy | **2023** | CreationDate 2023-12 + text | — | no |
| CTEPD/CTEPH | **2024** | CreationDate 2024-01 + text | — | no |
| Včasný záchyt chron. jaterních chorob | **2025** | CreationDate 2025-07 + text | — | no |

**Hepatitida is the load-bearing catch:** its CreationDate (2025) postdates the content (a 2023 novelizace),
so a CreationDate-only resolver would mis-stamp it 2025. The title-page stated year is authoritative.

## Decision

**Metadata rename in the store (brief option 1), NOT re-ingest (option 2).** Edition is `f(file_path)`; the
parse/embeddings/entities do not change, so re-running extraction + re-embedding 6 docs would only perturb the
graph (retrieve degrades under mutation; delete-cascade rebuilds shared entities) to change a string that is
an attribute, never a key. Rename is surgical.

**Two tiers of `file_path` persistence (audited — `operate.py:1455`/`:1818`, `postgres_impl.py` DDL):**
- **Load-bearing / single-valued — the safety fix.** `LIGHTRAG_DOC_STATUS`, `LIGHTRAG_DOC_CHUNKS`,
  `LIGHTRAG_VDB_CHUNKS` each hold one `file_path` per row. A clean whole-value UPDATE
  (`WHERE file_path = '<work>_unknown.pdf'` → `'<work>_<year>.pdf'`) fixes edition ordering: the chunk
  registry (`work_latest_editions`) and the chat references both read chunk/doc `file_path`.
- **Provenance / `<SEP>`-joined — best-effort.** `LIGHTRAG_VDB_ENTITY`, `LIGHTRAG_VDB_RELATION`, and Neo4j
  node/edge `file_path` accumulate `GRAPH_FIELD_SEP.join(...)` across all source docs and are **capped**
  (`max_file_paths`, truncated with a placeholder), so a shared entity may not even contain the `_unknown`
  substring. A substring replace `_unknown.pdf → _<year>.pdf` cleans the source chips where present; it is
  display-only and its incompleteness (truncation) does not affect edition ordering.

**Durable (ingest resolver) — never emit `_unknown` when the year is recoverable.** Add an edition-resolution
step at ingest that bakes the year into the stored `file_path`, priority order (brief step 2+3, "Better"):
1. year already in the filename (trusted, current behaviour);
2. **title-page stated year** — first-page text scan for `NOVELIZACE 20YY` / `20YY` (authoritative for the
   *content's* edition; catches hepatitida correctly where CreationDate does not);
3. **PDF `CreationDate` year** — fallback proxy;
4. `unknown` only if all fail.

Internal-only DB (TCP proxies removed) → the rename runs **server-side**, mirroring the spec-013 dedup pattern
(`lightrag/maintenance/` module + a `graph_routes` endpoint, plan/apply, background task, status file,
pipeline-busy guard).

## What ships

- **Pure module** `lightrag/maintenance/edition_rename.py`: the verified `_unknown → year` mapping + a
  `plan_rename(docs)` (which stored file_paths change, load-bearing vs provenance) + `apply_rename` over the
  storages. Unit-tested offline (mapping, single-value UPDATE targets, SEP-substring replace, no-op when
  absent).
- **Endpoint** `POST /graph:rename-edition?apply=` in `graph_routes.py` (dry-run summary → apply; status at
  `/graph:rename-edition/status`; pipeline-busy guarded).
- **Durable resolver** in the ingest/upload path: `resolve_edition_year(pdf_path)` (title-scan → CreationDate
  → unknown) bakes the year into `file_path`; unit-tested on the 6 fixtures' extracted metadata.
- Live run of the rename on staging + a re-probe confirming hepatitida/onkologická resolve their newest
  edition as latest (bundle `superseded_by_edition` + the chat answer).

### Non-goals
- Full corpus reingest (rename in place; brief acceptance: "No full corpus reingest performed").
- Re-embedding or re-extraction of any doc (content unchanged).
- Fixing the entity/relation `<SEP>` truncation cap (orthogonal; provenance chips are best-effort).
- The FE edition badge (`edition-aware-live-retrieval` follow-up, separate).

## Acceptance
- The 6 docs carry their real edition year in `DOC_STATUS`/`DOC_CHUNKS`/`VDB_CHUNKS` `file_path` (no
  `_unknown`); a work whose newest edition was `_unknown` (hepatitida, onkologická) resolves that edition as
  latest in both the promotion bundle (`latest_view`) and the live edition-aware chat answer.
- Ingest no longer emits `_unknown` when a year is recoverable from the PDF title page or `CreationDate`;
  the resolver picks the title-page year over a postdating `CreationDate` (hepatitida → 2023, not 2025).
- Rename is idempotent (re-run = no-op) and performs no reingest.
