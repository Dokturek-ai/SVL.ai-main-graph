# Spec 002 — Focused guideline retrieve endpoint (concept-groundable, top_k cited spans)

- **Briefs (merged — dedup #2):**
  - `dokturek/docs/briefs/2026-07-01-agent-to-guidelines-retrieve-endpoint-contract.md` (`open`) — the wire contract `POST /v1/guidelines:retrieve`, **unblocks the parked `agent-guidelines-grounding`**.
  - `dokturek/docs/briefs/2026-06-25-platform-to-guidelines-query-time-concept-grounding.md` (`open`) — the "B engine": resolve query → concept-aware retrieval → dual-source response.
  - These two are ~80% the same feature (one is the behaviour, the other its wire form). This spec is the single merged scope; both briefs point here.
- **Process:** brief-driven → speckit-fast → implement → caveman-review, **no brainstorm, no squash**, per-phase commits.
- **Landing-plan context:** `dokturek/docs/briefs/2026-07-08-guidelines-reingest-landing-plan.md` (this is the chosen next step over the re-ingest; re-ingest is deferred, capacity decided).

## Problem

An agent (and the FE) asking the guidelines KG for a diagnosis today gets **the whole DP back** — a
data dump, not the section it needs. `agent-guidelines-grounding` is **blocked**: guidelines exposes
`/query` (answer generation) but no focused, machine-consumable **retrieve** that returns the top-k
cited passage spans for a task, with the guidelines side doing the retrieval + ranking (the agent must
not pull everything and rank it itself). Separately, the platform wants query answers **grounded to the
right diagnosis** and the response to carry the resolved `concept_ref` so the caller can also pull mkn10
facts for the same code (the "dual-source" link) — the same endpoint, seen from the platform side.

## Dependency reality (measured 2026-07-08)

- **Chunks are NOT tagged** with `concept_ref` or `facet` yet — those come from the open
  `chunk-concept-ref-tagging` + `chunk-facet-section-tag` briefs (not done). Live chunk metadata today =
  `{content, created_at, file_path, source_type, chunk_id, reference_id}` (RESULTS.md / code map).
- **No page anchors** on the live corpus (`parse_engine: legacy`; page/bbox waits on the deferred
  re-ingest). `source_url` waits on the `source-url-reference` brief.
- **mkn10 `codes:resolve`** (server-side query→concept) is a cross-repo dependency
  (`mention-concept-resolve-contract`), not guaranteed live.

⇒ The endpoint must ship **useful now** without any of those, and grow into concept/facet filtering when
the tags land — a **v1 (plain) / v2 (concept-filtered)** split, exactly the "plain fallback" both briefs
already require.

## Goals

Add **`POST /v1/guidelines:retrieve`** — a focused, resilient retrieve that returns **≤ top_k cited
passage spans** (never a full-DP dump), with the guidelines side owning retrieval + ranking, and a
`concept_ref` echoed on the response so the caller can dual-source against mkn10.

- **G1 focused retrieve (v1, no deps):** `{query, facet?, concept_ref?, top_k, locale?}` → top_k cited
  spans via the **existing pure-retrieval path** (`aquery_data`, no LLM answer). The `query` ranks; the
  response is spans, not a document. This alone unblocks the agent's core ask.
- **G2 dual-source key (v1):** echo the request `concept_ref` (and, in v2, the server-resolved one) on
  the response so the caller pulls mkn10 facts for the same code. The link is the shared `concept_ref` —
  **no graph merge**, mkn10 stays the hub (guidelines calls mkn10, never the reverse).
- **G3 resilient (v1):** any query returns spans (plain retrieval); an unresolved/untagged filter
  degrades to plain, never errors, never regresses today's behaviour.
- **G4 honest citation (v1):** each span carries the provenance available **now** —
  `citation = "<file_path>#chunk=<chunk_id>@<edition>"` (edition from the filename). `page`/`bbox` and
  `source_url` are **absent in v1** (added when the re-ingest + source-url brief land) — labelled, not faked.
- **G5 concept/facet filtering (v2, deferred):** when chunks carry `concept_ref`/`facet` tags, the
  `concept_ref` **filters** the corpus and `facet` selects the section; optional server-side
  query→concept resolve via mkn10 `codes:resolve`. v2 is out of this spec's implementation — the params
  are **accepted + documented as no-op filters in v1** so the wire contract is stable across v1→v2.

## Key decisions

1. **Thin router, zero vendored-core delta.** A new fork-added file
   `lightrag/api/routers/guidelines_routes.py` that calls the **existing** `rag.aquery_data(...)` +
   `QueryParam`, and shapes the result into cited spans. **No edits to `lightrag/operate.py`,
   `lightrag/base.py`, or the existing query router** — mirrors spec 001's off-vendored-lib discipline
   (clean upstream rebase) **and avoids conflict with PR #1** (`feat/query-contextualization`, which
   edits `operate.py`).
2. **Reuse `aquery_data` (pure retrieval), not `/query`.** `aquery_data` stops before LLM generation —
   exactly a retrieve. Wrap it; do not reimplement retrieval.
3. **v1 accepts `facet`/`concept_ref` but does not filter** (chunks untagged). Documented as forward
   contract, no-op today, so v2 adds filtering without a wire change. This is the honest "plain fallback".
4. **Mode default = `mix`** (graph+vector, LightRAG default), `mode` overridable; `naive` is fastest for
   pure-passage use. Rerank follows the deployment default (a separate latency decision, not this spec).
5. **Cap to `top_k`.** The whole point is "not a data dump" — the response is hard-capped at `top_k`
   spans (default 5).

## Response contract (v1)

```jsonc
POST /v1/guidelines:retrieve
{ "query": "diagnostická kritéria arteriální hypertenze",
  "facet": "diagnosis",              // accepted; no-op filter in v1 (chunks untagged)
  "concept_ref": {"mkn10_code": "I10"}, // optional; echoed for dual-source; no-op filter in v1
  "top_k": 5, "locale": "cs" }
→
{ "passages": [
    { "text": "…span…",
      "citation": "Arteriální hypertenze_2024.md#chunk=<id>@2024",
      "score": 0.83,
      "facet": null,               // v2
      "concept_ref": null }        // v2 (per-chunk)
  ],
  "concept_ref": {"mkn10_code": "I10"},  // echoed (or v2 server-resolved) — dual-source key
  "mode": "focused",                     // or "plain-fallback"
  "disclaimer": "Čerpáno výhradně z SVL doporučených postupů." }
```

## Acceptance criteria (v1)

1. `POST /v1/guidelines:retrieve {query, facet?, top_k}` returns **≤ top_k** cited passage spans, **not
   a full-document dump**; each span carries a `citation` (`file_path#chunk=id@edition`) + `score`.
2. The focus is real: a diagnosis query returns a handful of on-topic spans, not the whole DP.
3. **Resilient:** any query returns spans (plain retrieval); a provided `facet`/`concept_ref` never
   errors and never regresses today's retrieval (v1 = no-op filters).
4. The response echoes the request `concept_ref` (dual-source key present when the caller supplies it).
5. **Zero edits to `lightrag/operate.py` / `base.py` / existing query router** — a new router file only;
   clean rebase; no conflict with PR #1.
6. Tests: shape + `≤ top_k` cap + plain fallback on an empty/whitespace query + `concept_ref` echo,
   without a live LLM answer (retrieve-only path).

## Out of scope (→ v2 / other briefs)

- **Actual `concept_ref`/`facet` filtering** — needs `chunk-concept-ref-tagging` + `chunk-facet-section-tag`.
- **Server-side query→concept resolve** — needs mkn10 `codes:resolve` live (`mention-concept-resolve-contract`).
- **`page`/`bbox` + `source_url` in the citation** — need the deferred PDF re-ingest + `source-url-reference`.
- **Rerank on/off latency tuning** — separate (landing-plan / reranker-eval).
- **The agent-side consumption** (`agent-guidelines-grounding`, A4) — consumer repo, unblocked by this contract.
