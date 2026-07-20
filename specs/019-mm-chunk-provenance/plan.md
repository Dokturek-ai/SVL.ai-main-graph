# Plan 019 — mm-chunk page/section provenance (read-path id→blockid hop)

## Touch surface

- `lightrag/sidecar/provenance.py` — extend `_block_ids` + `resolve_provenance` to translate mm ids; add the
  `load_mm_id_to_blockid` loader (impure, mirrors `load_blocks_by_id`).
- `lightrag/sidecar/passage_links.py` — add `load_mm_map_for_doc` (locate + load the 3 mm jsons); thread an
  `mm_cache` + mm map through `passage_provenance`.
- `lightrag/api/routers/guidelines_routes.py` — retrieve loop: pass `mm_cache` + the mm loader to
  `passage_provenance`; section-crop handler: load the mm map + pass to `resolve_provenance`. Add the
  `_load_mm_map_for_doc` alias (test monkeypatch parity with `_load_blocks_for_doc`).
- `lightrag/api/routers/query_routes.py` — enrichment loop: create + pass `mm_cache` to `passage_provenance`
  (default mm loader).
- `tests/guidelines/test_mm_chunk_provenance.py` — new unit tests (pure resolver + loader; no server/PDF).

No ingest / pipeline / prompt / enrichment-shape change. `resolve_provenance` stays I/O-free.

## provenance.py

`_block_ids(sidecar, mm_id_to_blockid=None)` — collect the sidecar's raw ids (`refs[].id`, else `id`) exactly as
today (ordered, deduped). Then:
- `type` in `(None, "block")` → return the raw ids (blockids) — **unchanged behaviour**.
- `type` in `("table","drawing","equation")` **and** a non-empty `mm_id_to_blockid` → translate each raw id
  (tb-/im-/eq-) through the map to a blockid, drop unmapped, return the blockids.
- otherwise (mm type, no map) → `[]` → resolver returns `None` (today's graceful degrade preserved).

`resolve_provenance(sidecar, blocks_by_id, mm_id_to_blockid=None)` — pass the map to `_block_ids`; the covered
→ `{page, pages, section, bbox, block_ids}` logic is **unchanged**. Default `None` ⇒ byte-for-byte identical to
today for every sidecar.

`load_mm_id_to_blockid(json_paths)` — merge `{str(mm_id): str(blockid)}` from each `*.tables.json` /
`*.drawings.json` / `*.equations.json` (root keys `tables`/`drawings`/`equations`; entry field `blockid`).
Best-effort: unreadable file / non-dict root / entry without `blockid` skipped. Returns `{}` when empty.

## passage_links.py

`load_mm_map_for_doc(file_path)` — mirror `load_blocks_for_doc`: `parsed_artifact_dir_for(file_path)`, prefer
`<stem>.<suffix>` else glob `*<suffix>` for each of the 3 suffixes, call `load_mm_id_to_blockid`. Any failure
⇒ `{}`.

`passage_provenance(rag, chunk_id, file_path, blocks_cache, mm_cache=None, *, load_blocks=None, load_mm_map=None)`
— after blocks load, load the per-doc mm map into `mm_cache` (lazily create a local dict when the caller passes
`None`, so it stays correct if a caller forgets it) and pass it to `resolve_provenance`. `load_mm_map` injectable
for tests (defaults to the module loader looked up at call time, like `load_blocks`).

## guidelines_routes.py

- Import `load_mm_map_for_doc`; add `_load_mm_map_for_doc = load_mm_map_for_doc` alias next to
  `_load_blocks_for_doc`.
- Retrieve `_build`: add `mm_cache: dict = {}` beside `blocks_cache`; pass
  `mm_cache, load_mm_map=_load_mm_map_for_doc` to `passage_provenance`.
- `guidelines_section_crop`: `mm_map = _load_mm_map_for_doc(file_path)` then
  `resolve_provenance(sidecar, blocks, mm_map)` — so a mm-chunk crop now resolves a page (the containing content
  block's page + region). Everything downstream (page/pages/bbox 018 logic) unchanged.

## query_routes.py

Enrichment loop: add `mm_cache: dict = {}` beside `blocks_cache`; pass `mm_cache` to `passage_provenance`
(default mm loader — no extra import).

## Verify

1. New unit tests green — `.venv/bin/python -m pytest tests/guidelines/test_mm_chunk_provenance.py`.
2. Full offline suite green (staging = no CI gate → offline suite is the gate). Re-run the spec-004/011/018
   provenance + section-crop tests to prove content-block behaviour is unchanged.
3. caveman-review (cavecrew-reviewer) on the diff; fix real findings.
4. Live-verify on staging after merge+deploy: a mm-table chunk on `:retrieve` returns non-null `page`
   (`scratch/probe_mm_blockid_chain.py` already proved the data chain; verify the wired read path) — else → brief.
