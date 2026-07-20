# Spec 020 — edition rename reconciles the on-volume parsed sidecar dir

## Problem

Spec 016's `POST /graph:rename-edition` renames a doc's `file_path` from `<work>_unknown.pdf` to
`<work>_<year>.pdf` across every store that holds it (DOC_STATUS, DOC_CHUNKS/VDB_CHUNKS, VDB entity/relation,
Neo4j). It is a **metadata-only** rename — it never touches the doc's **parsed artifacts on the volume**
(`<input>/__parsed__/<work>_unknown.pdf.parsed/`, plus the sibling `.mineru_raw` dir and the archived source
PDF).

The read-path provenance resolver derives the sidecar dir from the *renamed* `file_path`
(`passage_links.load_blocks_for_doc` → `utils_pipeline.parsed_artifact_dir_for`, whose
`canonicalize_parser_hinted_basename` strips only parser hints, **not** the `_<edition>` suffix). So after a
rename it looks for `<work>_<year>.pdf.parsed`, which does not exist — only `<work>_unknown.pdf.parsed` does.
`blocks.jsonl` never loads and **`page`/`section`/`bbox` resolve `None` for every chunk of a renamed doc**.

Confirmed live on staging 2026-07-21: all **6** spec-016-renamed docs still have `_unknown.pdf.parsed` dirs; a
`:retrieve` returns `Akutní průjem_2023.pdf#chunk=…-chunk-010@2023` with `page=section=bbox=None` (the lone
no-page prose residual after spec 019, which fixed multimodal 0→100%). This is brief
`guidelines-016-edition-rename-residue-and-landing` **residue E**.

## Goal

The edition rename becomes complete: renaming a doc's edition also renames its on-volume parsed artifacts to the
new edition name, so the read path resolves a page/section for the renamed doc's chunks. Fixes the existing 6 and
prevents recurrence on any future rename.

## Approach ($0 — no reingest, no re-parse, no LLM)

Extend `graph:rename-edition`'s background runner (`_run_rename`) with a filesystem reconcile step, run after
the DB sweep:

1. For each `(<work>_unknown.pdf → <work>_<year>.pdf)` in the frozen `EDITION_YEARS` map, and for each on-volume
   sibling suffix `("", ".parsed", ".mineru_raw")`, rename `<old><suffix>` → `<new><suffix>` when the old exists
   and the new does not. Try both NFC and NFD spellings (the Linux volume is normalization-sensitive; ingest
   wrote NFD).
2. When the renamed sibling is the `.parsed` dir, update `LIGHTRAG_DOC_FULL.sidecar_location` from the old URI to
   the new one (whole-value), so the stored sidecar pointer stays valid.

Idempotent (an already-renamed sibling — new present / old absent — is skipped) and best-effort per item (one
failure logs and continues, never aborts the pass). The endpoint already runs inside the API container with the
data volume mounted, so the rename happens in-process on the next `apply=true` run — no separate ops step.

## Acceptance

- New offline unit tests: the pure planner yields `_unknown→_year` pairs for existing siblings, skips
  already-renamed and absent ones, over a `tmp_path` root.
- The scoped offline suite (`tests/{sidecar,api,guidelines,parser,maintenance}`) stays green (staging has no CI
  gate).
- Live (post-deploy, after an `apply=true` run): `:retrieve` for `Akutní průjem_2023.pdf` chunk-010 resolves a
  non-null `page` (was `None`); the 6 `_unknown.pdf.parsed` dirs are gone, replaced by `_<year>.pdf.parsed`.

## Non-goals

- Renaming `LIGHTRAG_DOC_FULL.file_path`/`doc_name` (out of scope; the doc listing already shows 0 `_unknown`
  via DOC_STATUS — brief 016 §head). This spec only reconciles the on-volume artifacts + the sidecar pointer.
- The other open brief-016 residues (A hepatitida chip, B/MANUÁL KÓDŮ, D durable-resolver live test).
