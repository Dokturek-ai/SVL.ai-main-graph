# Tasks 002 — Focused guideline retrieve endpoint

Implements `plan.md` (v1). One phase = one commit (no squash). `[ ]` = todo.

## P1 — router + models + registration
- [ ] T001 `lightrag/api/routers/guidelines_routes.py`: Pydantic models (`ConceptRef`,
  `GuidelineRetrieveRequest`, `RetrievedPassage`, `GuidelineRetrieveResponse`) + `create_guidelines_routes(rag, api_key, top_k)` factory mirroring `create_query_routes` (APIRouter tags=["guidelines"], `combined_auth`). Endpoint `POST /v1/guidelines:retrieve` (handler body in P2). → verify: `ruff` clean; module imports.
- [ ] T002 Register in `lightrag/api/lightrag_server.py` (one line after the query-routes include). → verify: server module imports clean; route appears in the OpenAPI schema.

## P2 — shaping + edition + resilient fallback
- [ ] T010 `_edition_from_filename(path)` (regex `_(\d{4})(?:\.|$)` → year or `"unknown"`). → verify: unit assert `Arteriální hypertenze_2024.md → "2024"`, `Foo_unknown.md → "unknown"`, `Bar.md → "unknown"`.
- [ ] T011 Handler body: build `QueryParam(mode, top_k, chunk_top_k=top_k, only_need_context=True)` → `await rag.aquery_data(query, param)` → take first `top_k` `data.chunks` → shape `RetrievedPassage` (text, `file#chunk=id@edition` citation, nullable score) → echo `concept_ref`, `filtered=False`, disclaimer. Empty chunks → `passages: []`, never raise. → verify: tests in P3.

## P3 — tests
- [ ] T020 `tests/test_guidelines_retrieve.py` (FastAPI `TestClient`, stub `rag.aquery_data`, `api_key=None`): ≤ top_k cap; passage shape + citation `@2024`/`@unknown`; `concept_ref` echo + `filtered=False`; empty retrieval → `[]` + HTTP 200; `facet`/`concept_ref` supplied → no error, identical results. → verify: `pytest tests/test_guidelines_retrieve.py -q` green; `ruff` clean.

## Close-out
- [ ] T030 Full `pytest tests/test_guidelines_retrieve.py -q` green + `ruff check` clean.
- [ ] T031 **caveman-review** the diff (spawn `cavecrew-reviewer`); triage + fix real findings.
- [ ] T032 Home-repo lifecycle: PR `feat/guidelines-retrieve → main`; do NOT merge (lands in main repo for review, per owner). Loose-end brief: v2 (concept/facet filtering) tracked by the existing tagging + `query-time-concept-grounding` briefs; note the merge (dedup #2) in the central log.

## Notes
- v2 (concept/facet filtering, mkn10 resolve, page/source_url citation) → out of scope; wire contract already carries the fields (additive).
- Zero edits to `operate.py`/`base.py`/`query_routes.py` — no PR #1 conflict, clean rebase.
