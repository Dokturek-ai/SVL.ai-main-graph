# Plan 017 — deterministic page/section in `### References`

## Where the code goes

- **Composer (pure):** new module `lightrag/sidecar/reference_block.py` (sidecar package already owns the
  provenance seam — `passage_links.py`, `provenance.py` — so the citation-render helper belongs there and stays
  importable by tests without pulling FastAPI).
  - `render_reference_block_with_pages(response: str, references: list[dict]) -> str`
  - Helpers: `_format_pages(pages: list[int]) -> str` (contiguous → `12–13`, gaps → `12, 15`),
    `_pages_for_ref(ref: dict) -> list[int]`, `_section_for_ref(ref: dict) -> str | None`.
- **Wiring:** `lightrag/api/routers/query_routes.py`, non-stream `/query` handler, right after
  `_enrich_references_with_chunks` (~L509–511): `response_content =
  render_reference_block_with_pages(response_content, references)`. Only inside the existing
  `if request.include_references and request.include_chunk_content:` guard.

## Composer algorithm

```
render_reference_block_with_pages(response, references):
    idx = last case-insensitive index of "### References" in response
    if idx == -1: return response                      # R1 no block → unchanged
    head, block = response[:idx], response[idx:]
    ref_by_id = { str(r["reference_id"]): r for r in references if r.get("reference_id") }
    lines_out = ["### References"]
    for id in ordered unique [n] ids parsed from block:  # preserve LLM relevance/order
        r = ref_by_id.get(id)
        if not r: keep the LLM's original line for that id   # defensive; shouldn't happen
        file = r["file_path"]
        pages = _pages_for_ref(r)                        # aggregate+dedupe+sort across chunks[]
        section = _section_for_ref(r)                    # only if single shared section
        suffix = ""
        if pages: suffix = f" — s. {_format_pages(pages)}" + (f" · {section}" if section else "")
        lines_out.append(f"- [{id}] {file}{suffix}")     # R4: no pages → no suffix
    if no line gained a suffix: return response          # R1 no page data → unchanged (no-op)
    return head + "\n".join(lines_out) + "\n"
```

- **Page source (R3/R5):** `_pages_for_ref` reads each `ref["chunks"][j]["page"]` and `["pages"]` (spec 011
  shape), casts to int, dedupes, sorts. Ints only so `_format_pages` can detect contiguous runs; a non-numeric
  page is dropped (honest — no fabrication).
- **Section (R3):** collect `chunks[j]["section"]`; if exactly one distinct non-empty value → use it, else
  `None`.
- **Id parse:** regex `\[(\d+)\]` over the block, first-seen order, unique. This is the LLM's editorial
  selection (which docs) — allowed; provenance (page) is still backend-only.

## Verifiable-AI (R5)

- `operate.py` `reference_list_str` (L5093 kg / L6034 naive) is **not touched** → page never enters the
  synthesis prompt → LLM cannot be the last writer of a page.
- The composer's page/section come only from `references[].chunks[]` (already resolved by
  `passage_provenance` against `blocks.jsonl`). Deterministic string assembly.

## Tests (`tests/sidecar/test_reference_block.py`)

Pure-function tests, no network/DB (compose over hand-built `references` dicts mirroring the enriched shape):

1. **rewrite_with_page** — block `- [1] doc.pdf` + ref chunks page=29 → `- [1] doc.pdf — s. 29`.
2. **section_appended_when_shared** — chunks all section "Léčba › EM" → `… — s. 29 · Léčba › EM`.
3. **section_omitted_when_divergent** — chunks with two sections → page only, no `·`.
4. **multipage_contiguous / gapped** — pages {12,13} → `s. 12–13`; {12,15} → `s. 12, 15`; dedupe {29,29}→`29`.
5. **coverage_gap_title_only** (R4) — ref with chunks but no resolved page → `- [1] doc.pdf` unchanged, no `s.`.
6. **no_references_block** (R1) — response without `### References` → returned verbatim.
7. **no_page_data_noop** (R1) — references without chunks/page → response verbatim.
8. **llm_not_last_writer** (R5) — a wrong page typed in the LLM's block text is overwritten by the payload page
   (asserts the rendered page = payload, not the response-text number).
9. **multi_ref_order_preserved** — `[2]` then `[1]` in block → output keeps `[2]`,`[1]` order.

## Commit phases (progressive, no-squash)

1. `spec(017)` — done.
2. `plan(017)` — this file + tasks.md.
3. `feat(017): deterministic page/section in ### References` — composer module + wiring.
4. `test(017)` — unit tests (may fold into 3 if small).
5. caveman-review fixes (if any).

## Out of scope (briefs)

- Streaming page-in-text → FE renders from first-sent `references[]` (brief to dokturek-webpage).
- ~20–30% no-page chunks → MinerU block-resolution coverage brief (ingest-side).
