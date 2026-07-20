# Tasks 019 — mm-chunk provenance

## T1 — resolver: mm-id translation (provenance.py)
- [ ] `_block_ids(sidecar, mm_id_to_blockid=None)`: keep content-block path; add mm-type translation via the map;
      mm-without-map → `[]`.
- [ ] `resolve_provenance(sidecar, blocks_by_id, mm_id_to_blockid=None)`: pass map to `_block_ids`; rest unchanged.
- [ ] `load_mm_id_to_blockid(json_paths)`: merge `{mm_id: blockid}` from tables/drawings/equations json.
- verify: unit tests T5 for the resolver + loader.

## T2 — loader + threading (passage_links.py)
- [ ] `load_mm_map_for_doc(file_path)` mirrors `load_blocks_for_doc` (locate 3 mm jsons, load map, `{}` on fail).
- [ ] `passage_provenance(..., blocks_cache, mm_cache=None, *, load_blocks=None, load_mm_map=None)`: load per-doc
      mm map into `mm_cache`, pass to `resolve_provenance`.
- verify: T5 covers passage_provenance returns a page for a mm sidecar with a stub mm loader.

## T3 — retrieve + section-crop (guidelines_routes.py)
- [ ] import `load_mm_map_for_doc`; add `_load_mm_map_for_doc` alias.
- [ ] retrieve `_build`: `mm_cache = {}`; pass `mm_cache, load_mm_map=_load_mm_map_for_doc`.
- [ ] section-crop handler: load mm map, `resolve_provenance(sidecar, blocks, mm_map)`.
- verify: existing section-crop route tests still green; mm-chunk crop resolves a page.

## T4 — enrichment loop (query_routes.py)
- [ ] `mm_cache = {}`; pass to `passage_provenance`.
- verify: existing spec-011 reference tests still green.

## T5 — tests (tests/guidelines/test_mm_chunk_provenance.py)
- [ ] mm-table sidecar + map → resolves the containing block's page/section/bbox.
- [ ] mm sidecar, map absent/empty → `None` (backward compatible).
- [ ] content-block sidecar → identical output with and without a map passed (byte-for-byte).
- [ ] `load_mm_id_to_blockid`: merges roots, skips entries without `blockid`, `{}` on missing files.
- [ ] refs-based + id-only mm sidecars both translate.
- verify: `.venv/bin/python -m pytest tests/guidelines/test_mm_chunk_provenance.py` green.

## T6 — gate + review
- [ ] full offline suite green (staging = no CI gate).
- [ ] caveman-review (cavecrew-reviewer) on the diff; fix real findings.
- [ ] PR → staging; merge after gates (home repo, no squash).
- [ ] live-verify on staging post-deploy: mm-table chunk `:retrieve` → non-null `page` (else → brief).
