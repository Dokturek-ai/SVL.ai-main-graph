# Spec 005 — Concise ↔ verbose answer toggle

**Status:** implemented
**Source:** owner request 2026-07-10 (per-request toggle, default concise, verbose = the pre-concise "comprehensive" prompt).

## Problem

Answer verbosity is hardcoded. Commit `0d92b092` baked a concise Goal into both clinical
prompts (`rag_response` + `naive_rag_response`); there is no way to ask for a fuller,
comprehensive answer per query. Clinicians want a fast concise answer by default but sometimes
a full write-up.

## Decision

- **Per-request** switch, no env override. Default = **concise** (keeps current shipped behaviour).
- **verbose** = the exact pre-`0d92b092` Goal ("Generate a comprehensive, well-structured answer
  to the user query.").

## Requirements

- **R1 — Prompt slot.** The concise Goal paragraph in `rag_response` and `naive_rag_response`
  (`lightrag/prompt.py`) is replaced by an `{answer_style}` placeholder. Two fragments supply the
  text: `PROMPTS["answer_style_concise"]` (the current concise wording, verbatim) and
  `PROMPTS["answer_style_verbose"]` (the pre-concise comprehensive line). One shared concise
  fragment for both templates (the wording was identical).
- **R2 — Param.** `QueryParam.answer_mode: Literal["concise","verbose"] = "concise"`
  (`lightrag/base.py`).
- **R3 — API.** `QueryRequest.answer_mode: Optional[Literal["concise","verbose"]] = None`
  (`lightrag/api/routers/query_routes.py`); `to_query_params` already `exclude_none`s, so an
  omitted field falls back to the `QueryParam` default (concise).
- **R4 — Wiring.** `lightrag/operate.py` selects the fragment from `answer_mode` and passes
  `answer_style=` at all four `.format()` sites that render these templates (kg final, kg
  token-overhead calc, naive token-overhead calc, naive final).

## Non-goals

- Env-var default (`ANSWER_MODE_DEFAULT`) — rejected; per-request only.
- A third mode / free-form length control — only concise|verbose.
- FE toggle (dokturek-webpage follow-up: send `answer_mode` on the query request).

## Acceptance

- `rag_response` and `naive_rag_response` format without `KeyError` for both modes.
- `answer_mode="verbose"` on a `QueryRequest` flows to `QueryParam.answer_mode="verbose"`; omitted
  → `"concise"`. The rendered Goal line differs accordingly (concise "Generate a concise…" vs
  verbose "Generate a comprehensive…"). Verified.
- API route suite green (`./scripts/test.sh tests/api/routes`).
