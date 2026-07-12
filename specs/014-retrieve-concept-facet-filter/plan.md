# Plan 014 — retrieve v2 filtering

## Pure module `lightrag/guidelines/retrieve_filter.py` (unit-tested, no I/O)

- `dotnorm(code) -> str` — `code.replace(".", "").upper()`.
- `code_matches(entity_code, request_code) -> bool` — dot-normalize both, then **bidirectional startswith**
  (`I10`↔`I10.9`, `E11.9`↔`E11`): `a.startswith(b) or b.startswith(a)` on dot-normalized ≥3-char codes.
  Respects the family (won't match `I10`/`I11`).
- `build_code_index(entities) -> dict[str, set[str]]` — pure. `entities = [(concept_ref_list, [chunk_id,…])]`
  (from node `concept_ref` + `source_id` split on `<SEP>`). Returns `dotnorm_code -> {chunk_ids}` (MKN-10
  codes only; skip drug `c_…`).
- `chunks_for_code(index, request_code) -> set[str]` — union of `index[c]` for every `c` with
  `code_matches(c, request_code)`.
- `classify_facet(section_heading) -> str | None` — CZ keyword → enum, checked in precedence
  **contraindication → dosing → followup → diagnosis → treatment** (first hit wins; `None` if no keyword):
  `kontraindik`→contraindication; `dávkov|dávka`→dosing; `sledován|dispenzar|kontrol|monitor`→followup;
  `diagnos|diagnóz|kritéri|vyšetřen`→diagnosis; `léčb|terap|farmakoterap|management`→treatment.

## Endpoint wiring (`guidelines_routes.py`, thin)

**Cached index.** Module-level `_code_index = {"at": ts, "map": {...}}` + an `asyncio.Lock`. `get_code_index()`
rebuilds via `rag.get_knowledge_graph(node_label="*", max_nodes=1_000_000)` when missing or older than
`RETRIEVE_INDEX_TTL` (default 600 s). Cold-start cost = one graph pull (~s), then O(1)/request.

**In `guidelines_retrieve`:**
1. `code = request.concept_ref and request.concept_ref.mkn10_code`.
2. If `code`: `allow = chunks_for_code(await get_code_index(), code)`. Retrieve a **wider pool** —
   `QueryParam(chunk_top_k = max(top_k * POOL_FACTOR, POOL_FLOOR))` (e.g. ×6, floor 60) — then keep only
   passages whose `chunk_id ∈ allow`. If `allow` empty OR the filter leaves 0 → fall back (see 5).
3. `facet` derived per passage via `classify_facet(prov.section)`; set `passage.facet`. If `request.facet`
   set, keep only matches (again, empty-after-filter → keep the code-filtered set rather than 0, log).
4. Trim to `top_k`. `filtered = True` iff a concept_ref filter was actually applied and non-empty.
5. **Fallback** (no concept_ref, unresolvable code, or empty filter): exactly today's v1 path,
   `filtered=False` — no regression.

`passage.concept_ref` (v2 per-chunk): best-effort — the requested ref echoed onto kept passages (the chunk
is in that code's set). Keep simple; full per-chunk multi-ref is out.

## Tests (`tests/guidelines/test_retrieve_filter.py`, offline)
- `code_matches`: dotted/dotless, category⊃specific both directions, family boundary (`I10`≠`I11`), drug skip.
- `build_code_index` + `chunks_for_code`: union across matching codes; MKN-only.
- `classify_facet`: each enum from a representative CZ heading; precedence (a heading with both
  "léčba" and "dávkování" → dosing); no-keyword → None.
- Endpoint-level (monkeypatch rag.aquery_data + the index): concept_ref narrows to the allow-set;
  facet filters; unresolvable code → fallback (filtered=False, v1 result); empty-filter → fallback.

## Rollout
Land code+tests (offline) → PR → merge (staging). Live-verify (a real code-scoped query returns a focused
in-scope subset) is a gated post-merge step; the cached index warms on first hit.
