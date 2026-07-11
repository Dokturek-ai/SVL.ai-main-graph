# Spec 008 — `concept_ref` grounding at extract (context-LLM over mkn10 neural-search)

**Status:** mechanism shipped (offline-tested); live probe run + extract-path wiring DEFERRED (no LLM/mkn10 in build env; the wiring folds into the combined Phase 0+1+2 full-corpus run).
**Source:** brief `guidelines-phase1-extract-grounding-build` (the BUILD; design settled in `mkn10-to-guidelines-typed-oriented-edges-contract` Phase-1). Enabler = spec 006 single-doc re-extract probe.

## Problem

mkn10 cannot ground ~77% of guideline clinical entities by its deterministic name-resolver, and the
tail it *does* reach mis-resolves (a drug name → the `Otrava léčivy – X` poisoning code = the biggest
measured wrong-subject class, judged 100% wrong). The fix is to emit a `concept_ref` (ICD-10 / SNOMED
coding) **at extract**, where the full document context is available and the LLM can disambiguate a
homonym or abstain. The vocabulary lives in mkn10, the context lives in guidelines — so mkn10 supplies
candidates, the guidelines ingest LLM picks (or abstains) with context.

## Settled decisions (from the contract brief — do NOT re-litigate)

- **Route by `node.type`** (LOAD-BEARING): `drug`/`medication` → mkn10 neural-search `domain=drug`; else
  `domain=mkn10`. A drug searched in `domain=mkn10` returns the poisoning code — routing kills that class
  at the grounding step. `node.type` is already populated (PR #15).
- **Context-LLM pick, NOT top-1** — the answer is in top-K but often not #1 (`F320 Lehká depresivní fáze`
  ranks below the homonym `X320 sluneční záření`). The ingest LLM chooses using document context, or
  **abstains → `concept_ref = []`**. Do NOT threshold on `score_fused` (uniformly 0.02–0.05, not a
  confidence).
- **Narrow Constitution VI by phase, don't break it:** the *probabilistic* extract stage MAY call mkn10
  (cache-gated so re-runs are deterministic); the *deterministic* promotion stage does NO network — it
  only validates `code ∈ spine` against a pinned snapshot (verify-or-abstain); harvest is bundle-only.
- neural-search needs a **browser `User-Agent`** (Cloudflare 1010 blocks the default urllib UA).
- **Phase 0 (clinical-only) is a hard prerequisite** — don't ground non-clinical noise. Out of scope here.

## What ships now (in-repo, offline unit-tested)

The reusable, deterministic core + the deterministic promotion guard. The live LLM/HTTP calls are
injected (mockable) so everything is testable without an LLM or mkn10, mirroring spec 006.

### `lightrag/grounding.py` — the extract-time grounding core

- **`route_domain(node_type) -> "drug" | "mkn10"`** — the poisoning-class killer. `drug`/`medication`
  (case-insensitive) → `"drug"`, else `"mkn10"`.
- **`async neural_search_candidates(name, domain, *, base_url, api=..., limit=4) -> list[Candidate]`** —
  thin GET client to mkn10 `/v1/codes/neural-search?q=&domain=&limit=` with a browser `User-Agent`;
  returns `[{code, display, score, system}]`. `api` (the HTTP fetch) is injected for tests.
- **`build_grounding_messages(name, node_type, description, candidates, doc_context)`** — the LLM
  disambiguation prompt: "pick the candidate `code` that matches this entity in THIS document, or answer
  NONE". Candidates rendered as a numbered code+display list; context = the chunk/doc text.
- **`parse_concept_ref(llm_text, candidates) -> list[ConceptRef]`** — parse the LLM's choice; accept ONLY
  a code that was in the offered candidate set (no hallucinated codes); `NONE`/unparseable → `[]`.
- **`async ground_entity(entity, doc_context, *, llm_func, neural_base, api=...) -> list[ConceptRef]`** —
  orchestrator: route → search → (no candidates ⇒ `[]`) → prompt `llm_func` → parse. `llm_func` and `api`
  injected; fully mockable.

`ConceptRef` = `{"system": <uri>, "code": <str>, "display": <str>}`; MKN-10 system URI = the ÚZIS URI.

### `lightrag/promotion/spine.py` — deterministic promotion-side guard (no network)

- **`load_spine(path) -> Spine`** — read a vendored snapshot `{spine_hash, version, count, codes[]}`;
  recompute `spine_hash = sha256("\n".join(sorted(set(codes))))` and raise if it disagrees with the pinned
  value (tamper/format guard). mkn10 shipped the source (`GET /v1/codes/spine`, spec 138 / PR #239).
- **`validate_concept_refs(refs, spine) -> (kept, dropped)`** — drop any `concept_ref` whose MKN-10
  `code ∉ spine.codes` (verify-or-abstain). Non-MKN-10 systems (e.g. SNOMED) pass through unchanged
  (mkn10 crosswalks them). No network.

> The **vendored snapshot file** is fetched live (needs mkn10) and committed with the live probe run —
> deferred like spec 006's live step. Ships now: the loader + validator, tested against a small fixture.

## Verification (offline, build-env safe)

`tests/test_grounding.py` + `tests/test_promotion_spine.py`, no LLM / no network:
- `route_domain`: drug/medication (any case) → `"drug"`; condition/diagnosis/symptom/… → `"mkn10"`.
- `neural_search_candidates`: injected `api` returns a canned mkn10 payload → parsed `Candidate` list;
  the request URL carries `q`/`domain`/`limit` and a browser UA header.
- `parse_concept_ref`: a valid in-set code → one `ConceptRef`; a code NOT in the candidate set → `[]`
  (no hallucination); `NONE` → `[]`.
- `ground_entity`: drug entity routes to `domain=drug`; empty candidates ⇒ `[]` without calling the LLM;
  a mocked `llm_func` picking a candidate ⇒ that `ConceptRef`; the poisoning-name-in-drug-domain case
  returns the real drug candidate set (routing regression guard).
- `load_spine`: matching hash loads; a tampered `codes[]` (hash mismatch) raises.
- `validate_concept_refs`: `code ∈ spine` kept; `code ∉ spine` dropped; SNOMED passes through.

## Probe-first (scratch, live run DEFERRED → brief)

Extend `scratch/probe_phase1_grounding.py`: reextract a DP (spec 006) → for each **clinical** entity run
`ground_entity` live (real mkn10 neural-search + the ingest LLM) → print
`{name, type, chosen code, candidates, abstained?}`. Measure on a few DPs: grounding hit-rate on the
CLINICAL subset, **poisoning-class = 0** (via routing), a sane abstain-rate. Needs `LIGHTRAG_API_KEY`
(`railway run` staging) + live mkn10; build env has neither → the live run is tracked as a brief.

## Non-goals (deferred to the combined Phase 0+1+2 run)

- Wiring `ground_entity` into the real `extract_entities` path + writing `concept_ref` onto graph nodes.
- `resolve_cache.jsonl` persistence (cache-first re-runs) — lands with the extract-path wiring.
- Committing the vendored spine snapshot file (fetched with the live probe).
- Phase 0 (clinical-only prompt) and Phase 2 (edge subject, spec 007).
- A per-`concept_ref` confidence signal (the Certainty tier for the action-grade subset).

## Acceptance

- `grounding.py` + `promotion/spine.py` ship with passing offline tests (LLM + HTTP mocked).
- Routing provably returns `domain=drug` for drug/medication types (poisoning-class guard) and the LLM
  can only emit a code from the offered candidate set (no hallucination); abstain ⇒ `[]`.
- `validate_concept_refs` drops any `code ∉` the pinned spine, purely, with no network.
- Live probe (deferred brief): on a sample DP, clinical entities get a `concept_ref` or a justified `[]`,
  zero poisoning-code attaches, chosen codes validate against the vendored spine.
</invoke>
