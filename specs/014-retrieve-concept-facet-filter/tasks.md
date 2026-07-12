# Tasks 014 — retrieve v2 filtering

## T1 — pure module + units
`lightrag/guidelines/retrieve_filter.py`: `dotnorm`, `code_matches`, `build_code_index`, `chunks_for_code`,
`classify_facet`. `tests/guidelines/test_retrieve_filter.py` (offline): code-match dotted/dotless + family
boundary + drug-skip; index/union; facet enum + precedence + no-keyword.

## T2 — endpoint wiring
`guidelines_routes.py`: TTL-cached `get_code_index()` (via `rag.get_knowledge_graph`, `asyncio.Lock`);
in `guidelines_retrieve` apply concept_ref post-filter over a wider pool, derive+filter facet, set
`filtered`/`passage.facet`/`passage.concept_ref`; unresolvable/empty → v1 fallback. Endpoint tests
(monkeypatch `rag.aquery_data` + index): narrows to allow-set, facet filters, fallback paths.

## T3 — gate + land
Offline suite (runnable subset) green → cavecrew-review → PR → merge staging. Live-verify (code-scoped
query returns focused in-scope subset) gated post-merge; note the agent field is `concept_ref.mkn10_code`.

## Verify
- units green; a concept_ref query returns only allow-set chunks (`filtered=true`); facet filters; an
  unresolvable code returns the v1 result (`filtered=false`), never errors.
