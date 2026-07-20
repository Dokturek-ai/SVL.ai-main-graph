# Tasks 017

- [ ] T1 — `lightrag/sidecar/reference_block.py`: `render_reference_block_with_pages` + `_format_pages`,
      `_pages_for_ref`, `_section_for_ref`. Pure, no I/O.
- [ ] T2 — wire into non-stream `/query` (query_routes.py, after `_enrich_references_with_chunks`, inside the
      `include_references and include_chunk_content` guard).
- [ ] T3 — `tests/sidecar/test_reference_block.py` (9 cases per plan). Run offline suite (staging = no CI gate).
- [ ] T4 — caveman-review (cavecrew-reviewer subagent) on the diff; fix real findings.
- [ ] T5 — PR into `staging`; merge after gates (home repo).
- [ ] T6 — brief to dokturek-webpage: FE renders page-precise reference list + lupa from `references[].chunks[]`
      (streaming path). Central `docs/briefs/`, commit to platform-master brief log.

## Verify gates

- `reference_list_str` (operate.py:5093/6034) shows **no diff** (page not in prompt).
- Composer is a no-op when `include_chunk_content` off or no page resolved.
- Live-verify EM answer on staging after deploy (page appears in `### References`).
