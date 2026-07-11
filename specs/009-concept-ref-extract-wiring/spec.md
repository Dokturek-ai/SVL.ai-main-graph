# Spec 009 — wire `concept_ref` grounding into the extract path (+ resolve cache)

**Status:** offline-built; the LIVE re-extract write (concept_ref onto real staging nodes) is DEFERRED to a brief (no LLM/mkn10 in build env — mirrors specs 006/008).
**Source:** brief `guidelines-phase1-extract-grounding-build`, remaining scope. Mechanism = spec 008 (`lightrag/grounding.py` + vendored spine). This increment wires it into `extract_entities` and adds the cache. Phase-0 (clinical-only prompt, `prompts/entity_type/clinical_cs.yml`) is already shipped; Phase 2 (edge subject, spec 007) lands separately.

## Problem

Spec 008 shipped the grounding **mechanism** (`ground_entity`: route by `node.type` → mkn10 neural-search → context-LLM pick / abstain) + the deterministic promotion-side spine guard, both offline-tested. Nothing calls `ground_entity` in the real pipeline yet — extracted graph nodes carry no `concept_ref`. This increment does the wiring, cache-gated and behind a default-off flag, so:

- a normal ingest is **unchanged** unless grounding is explicitly enabled (Constitution VI: the probabilistic extract stage MAY call mkn10, opt-in);
- when enabled, each **clinical** merged entity gets a `concept_ref` (or a justified `[]`) written onto its graph node, cache-first so re-runs are deterministic and skip the network.

## Settled decisions (from the brief — do NOT re-litigate)

- **Hook at merge, once per unique entity, not per-chunk.** `_merge_nodes_then_upsert` runs once per entity-name under its lock, has `global_config` (→ the EXTRACT-role LLM + addon_params) and the merged `description` (cross-chunk context). Grounding per-chunk would call the LLM/mkn10 N× per entity for no gain; merge-time is 1×/entity and mirrors what the spec-008 probe validated (per-unique-entity, description context).
- **Default OFF.** Gated on `CONCEPT_REF_GROUNDING_ENABLED` (env, default false). Off ⇒ zero new behavior, zero network. This is the opt-in the Constitution-VI narrowing requires.
- **Route by `node.type`** (the poisoning-class killer) — already in `ground_entity` via `route_domain`. Only clinical types are grounded (drug/medication → `domain=drug`; condition/diagnosis/symptom/procedure/labtest → `domain=mkn10`); anything else is skipped (no grounding, `concept_ref` absent).
- **Cache-first, key = name|type|description-hash.** `resolve_cache.jsonl` in the working dir: a hit returns the cached `concept_ref` with NO LLM/mkn10 call; a miss grounds then appends. Makes re-runs deterministic + free. (The existing Postgres LLM-response cache also dedups the LLM call cross-run; the resolve cache additionally skips the neural-search HTTP.)
- **No spine check at extract.** Promotion validates `code ∈ spine` (spec 008, vendored snapshot). Extract writes the candidate-set code as-is; the deterministic promotion guard drops any non-spine MKN-10 code. Keep the phase separation.

## What ships now (offline unit-tested)

### `lightrag/grounding.py` — add the resolve cache (deterministic, no network)

- **`resolve_cache_key(name, node_type, description) -> str`** — `sha256` over `name|type|description` (normalized), the cache key.
- **`load_resolve_cache(path) -> dict[str, list[ConceptRef]]`** — read a JSONL cache (`{key, concept_ref}` per line); missing file ⇒ `{}`; a corrupt line is skipped (best-effort, never fatal).
- **`append_resolve_cache(path, key, refs) -> None`** — append one `{key, concept_ref}` line.
- **`async ground_entity_cached(entity, doc_context, *, cache, cache_path, llm_func, neural_base, api=...) -> list[ConceptRef]`** — cache lookup by `resolve_cache_key`; hit ⇒ return cached (no calls); miss ⇒ `ground_entity(...)`, update the in-memory `cache` + append to `cache_path`, return. `cache` is the in-run dict (dedup within a run); `cache_path` persists it.

### `lightrag/operate.py` — the merge-time hook

- In `_merge_nodes_then_upsert`, just before building `node_data` (line ~2206): if grounding is enabled and `route_domain(entity_type)` is clinical, call `ground_entity_cached(...)` with `doc_context = description` (the merged cross-chunk description) and attach the result as `node_data["concept_ref"]` (a JSON-encoded list, matching how the graph store persists structured node fields). Absent/`[]` ⇒ no `concept_ref` key (don't write empty noise).
- Grounding config resolved once (not per entity) into `global_config["_concept_ref_grounding"]` in `LightRAG.__post_init__`: `{enabled, neural_base, cache_path, cache}` — mirrors the existing `_resolved_summary_language` / `_entity_extraction_prompt_profile` resolution pattern. `neural_base` from `MKN10_NEURAL_BASE_URL` (default `https://mkn10.dokturek.ai`); `cache_path` = `<working_dir>/resolve_cache.jsonl`.
- The EXTRACT-role LLM (`global_config["role_llm_funcs"]["extract"]`) is adapted to `ground_entity`'s `llm_func(prompt) -> str` shape (a thin `async` wrapper).

## Verification (offline, build-env safe)

`tests/test_grounding.py` / `tests/promotion/` additions, no LLM / no network:
- `resolve_cache_key`: stable + order/whitespace-normalized; different name/type/desc ⇒ different key.
- `load_resolve_cache`: missing path ⇒ `{}`; a good JSONL loads; a corrupt line is skipped, not fatal.
- `ground_entity_cached`: a cache HIT returns the cached refs and calls NEITHER `llm_func` NOR `api` (assert both un-called); a MISS calls `ground_entity`, appends to the file, and a subsequent call with the same key hits.
- A focused operate-level test (mocked graph store + mocked `ground_entity_cached`): enabled + clinical entity ⇒ `upsert_node` receives `concept_ref`; disabled ⇒ no `concept_ref` and grounding not called; non-clinical type ⇒ skipped.

## Non-goals / deferred

- **The LIVE re-extract run** (writing `concept_ref` onto real staging nodes + measuring on a DP) — needs LLM + mkn10 + staging; build env has none → tracked as a brief (mirrors 006/008).
- Phase 2 (edge subject, spec 007) — separate PR; the ONE combined full-corpus re-ingest happens after both land.
- A per-`concept_ref` Certainty tier (the action-grade subset signal).
- Query-time surfacing of `concept_ref` (retrieve/answer path).

## Acceptance

- `ground_entity_cached` + the cache helpers ship with passing offline tests; a cache hit provably makes zero LLM/HTTP calls.
- The operate hook writes `concept_ref` onto a clinical node's `node_data` when enabled, skips non-clinical, and is a no-op when disabled (default) — proven by a mocked operate-level test.
- Default-off means a normal ingest is byte-for-byte unchanged (no `concept_ref`, no network).
- Live re-extract verification is captured as a brief.
