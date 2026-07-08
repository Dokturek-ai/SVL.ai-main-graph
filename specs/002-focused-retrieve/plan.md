# Plan 002 — Focused guideline retrieve endpoint

Implements `spec.md` (v1). Architecture, module layout, shaping, testing.

## Architecture — one thin router over the existing pure-retrieval path

```
  POST /v1/guidelines:retrieve
        │
        ▼
  guidelines_routes.py  (NEW, fork-added — the only new code)
        │  build QueryParam(mode, top_k, chunk_top_k, enable_rerank)
        ▼
  rag.aquery_data(query, param)     ← EXISTING (lightrag.py:1997) — retrieval, no LLM
        │  returns {data:{chunks:[{content,file_path,chunk_id,reference_id}], ...}, metadata}
        ▼
  shape → cap top_k → passages[{text, citation, score?, facet:null, concept_ref:null}]
        + echo concept_ref + disclaimer
```

- **No edits to `operate.py` / `base.py` / `query_routes.py`.** `aquery_data` already exposes exactly the
  chunk shape we need (`content`, `file_path`, `chunk_id`, `reference_id`). We only add a router that
  calls it and reshapes. → clean upstream rebase; no conflict with PR #1 (`operate.py`).
- **One-line registration** in `lightrag/api/lightrag_server.py` (next to the query-routes include).

## Module layout

```
lightrag/api/routers/guidelines_routes.py    # NEW — create_guidelines_routes(rag, api_key, top_k)
lightrag/api/lightrag_server.py               # +1 line: app.include_router(create_guidelines_routes(...))
tests/test_guidelines_retrieve.py             # NEW — shaping/contract tests (aquery_data mocked)
```

Mirrors the `create_query_routes` factory pattern (query_routes.py:191): `APIRouter(tags=["guidelines"])`
+ `get_combined_auth_dependency(api_key)` + `@router.post(..., dependencies=[Depends(combined_auth)])`.

## Request / response models (Pydantic)

```python
class ConceptRef(BaseModel):        # optional, all fields optional
    mkn10_code: str | None = None
    cui: str | None = None

class GuidelineRetrieveRequest(BaseModel):
    query: str = Field(min_length=3)
    facet: Optional[str] = None                 # v1: accepted, not applied
    concept_ref: Optional[ConceptRef] = None    # v1: echoed, not applied
    top_k: int = Field(default=5, ge=1, le=50)
    locale: str = "cs"
    mode: Literal["mix","naive","local","global","hybrid"] = "mix"

class RetrievedPassage(BaseModel):
    text: str
    citation: str                  # "<file_path>#chunk=<chunk_id>@<edition>"
    score: Optional[float] = None  # only if the chunk carries one
    facet: Optional[str] = None    # v2
    concept_ref: Optional[ConceptRef] = None   # v2 (per-chunk)

class GuidelineRetrieveResponse(BaseModel):
    passages: list[RetrievedPassage]
    concept_ref: Optional[ConceptRef] = None    # echo of request — dual-source key
    filtered: bool = False         # v1 ALWAYS false (honest: no concept/facet filter applied)
    disclaimer: str = "Čerpáno výhradně z SVL doporučených postupů."
```

**Refinement over spec's response:** replace the `mode: "focused"|"plain-fallback"` field with a plain
**`filtered: bool`** — honest and unambiguous (v1: always `false`; v2 sets `true` when a concept/facet
filter is actually applied). The retrieval `mode` is a request knob, not a response signal.

## Shaping logic

1. `param = QueryParam(mode=req.mode, top_k=req.top_k, chunk_top_k=req.top_k, only_need_context=True)` —
   `enable_rerank` left to the deployment default.
2. `result = await rag.aquery_data(req.query, param)`; `chunks = result.get("data", {}).get("chunks", [])`.
3. Take the first `top_k` chunks; for each →
   - `text = chunk["content"]`
   - `citation = f"{file_path}#chunk={chunk_id}@{edition}"`, `edition = _edition_from_filename(file_path)`
     (regex `_(\d{4})` on the filename stem; `"unknown"` if absent — same convention as the corpus
     `Work_YEAR.md`).
   - `score = chunk.get("score")` (nullable — the documented chunk shape has none; include only if present).
4. `concept_ref` echoed from the request; `filtered=False`; `disclaimer` constant.
5. **Resilient:** if `aquery_data` returns no chunks (empty query result), return `passages: []` +
   `filtered: False` — never raise (except the auth + `min_length` validation the framework already does).

## Edition parse (local, tiny — no promotion/ import)

`promotion/` lives on the unmerged `feat/verifiable-ingest` branch; do **not** import it. A 3-line
`_edition_from_filename(path) -> str` (regex `_(\d{4})(?:\.|$)`) covers the `Work_YEAR.md` corpus.

## Phasing (each phase = one commit; no squash)

1. **P1 — router + models + registration** (`guidelines_routes.py`, +1 line in `lightrag_server.py`).
   Verify: server imports clean; `ruff` clean; endpoint present in the OpenAPI schema.
2. **P2 — shaping + edition + resilient fallback** (fill the handler body). Verify: unit tests below.
3. **P3 — tests** (`tests/test_guidelines_retrieve.py`, `aquery_data` mocked). Verify: green + ruff.

(P1–P3 may land as one implement commit given the small size; keep tests in their own commit if cleaner.)

## Testing (no live LLM/DB — mock `aquery_data`)

`tests/test_guidelines_retrieve.py` builds the router with a stub `rag` whose `aquery_data` returns a
canned `{"data":{"chunks":[…]}}`, drives it via FastAPI `TestClient`, and asserts:
- **≤ top_k** passages returned even when the stub yields more (the cap).
- Passage **shape**: `text` + `citation` matching `file#chunk=id@edition` (incl. `@2024` parsed, and
  `@unknown` for a yearless filename).
- **concept_ref echoed** when supplied; `filtered` is `False`.
- **Empty retrieval** (stub returns no chunks) → `passages: []`, HTTP 200, no raise.
- `facet`/`concept_ref` supplied → **no error**, results identical to without (v1 no-op).

Auth: the tests build the router with `api_key=None` (auth disabled) to exercise the handler directly.
```
pytest tests/test_guidelines_retrieve.py -q   # fast, no network
```

## Risks / notes

- **`score` absence.** The documented `aquery_data` chunk shape has no score; `score` stays nullable —
  not fabricated. If a mode attaches one at runtime, it rides through.
- **`mode` default `mix`** gives KG+vector chunks; `naive` is the fastest pure-chunk path. Exposed so the
  agent can pick; default stays `mix` for recall.
- **v2 (out of scope):** concept/facet filtering (needs chunk tags), server-side mkn10 resolve, page/bbox
  + source_url in the citation (needs the deferred re-ingest + source-url brief). The wire contract
  already carries the fields, so v2 is additive.
