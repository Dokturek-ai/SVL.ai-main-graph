# Plan 009 — concept_ref extract-path wiring

## Approach

Two edits, both additive and default-off:

1. **`lightrag/grounding.py`** (pure, offline-testable): add the resolve cache — `resolve_cache_key`, `load_resolve_cache`, `append_resolve_cache`, `ground_entity_cached`. No new deps; reuses the existing `ground_entity` + injected `api`.

2. **`lightrag/operate.py` + `lightrag/lightrag.py`**: resolve grounding config once in `LightRAG.__post_init__` → `global_config["_concept_ref_grounding"]`; consume it in `_merge_nodes_then_upsert` right before `node_data` is built.

## Key files / anchors

- `lightrag/grounding.py:151` — `ground_entity` (wrap with the cache).
- `lightrag/operate.py:2206` — `node_data = dict(...)` in `_merge_nodes_then_upsert`; hook is immediately above; `entity_type` + merged `description` + `global_config` all in scope.
- `lightrag/operate.py:1928` — `_merge_nodes_then_upsert(..., global_config, ...)` signature (config is already threaded in).
- `lightrag/operate.py:3259` — `global_config["role_llm_funcs"]["extract"]` — the EXTRACT-role LLM (the adapter target).
- `lightrag/lightrag.py` `__post_init__` — where `_resolved_summary_language` / `_entity_extraction_prompt_profile` are cached into `global_config`; add `_concept_ref_grounding` beside them.

## Config (env, Railway source-of-truth)

- `CONCEPT_REF_GROUNDING_ENABLED` — bool, **default false**. The master gate.
- `MKN10_NEURAL_BASE_URL` — default `https://mkn10.dokturek.ai`.
- `cache_path` = `<working_dir>/resolve_cache.jsonl` (not env; derived).

Resolved value: `global_config["_concept_ref_grounding"] = {"enabled": bool, "neural_base": str, "cache_path": str, "cache": dict}` (`cache` is the in-run dict, lazily loaded from `cache_path` on first use).

## Hook logic (operate.py, guarded)

```
g = global_config.get("_concept_ref_grounding")
if g and g["enabled"] and route_domain(entity_type) in ("drug", "mkn10-clinical…"):
    refs = await ground_entity_cached(
        {"name": entity_name, "type": entity_type, "description": description},
        description,                      # doc_context = merged cross-chunk desc
        cache=g["cache"], cache_path=g["cache_path"],
        llm_func=_extract_llm_adapter(global_config), neural_base=g["neural_base"],
    )
    if refs:
        node_data["concept_ref"] = json.dumps(refs, ensure_ascii=False)
```

Only clinical `route_domain` results ground. `route_domain` returns `"drug"` or `"mkn10"`; to skip truly non-clinical types (person/organization/other/table/drawing/…) we gate on an explicit clinical-type set, NOT on `route_domain` (which maps everything-not-drug to `"mkn10"`). Reuse the probe's `CLINICAL = {drug, medication, condition, diagnosis, symptom, procedure, labtest}` (case-insensitive).

Failure isolation: a grounding exception (mkn10 down, LLM error) is caught + logged; the node upserts WITHOUT `concept_ref` (grounding is best-effort enrichment, never blocks ingest).

## Risks / mitigations

- **Hot-path latency** — grounding adds an LLM+HTTP round-trip per clinical entity at merge. Mitigated by default-off + cache; only the grounding run pays it.
- **`concept_ref` field shape** — persisted as a JSON string (graph stores are string-valued for custom fields). Harvest/promote will read + json-decode it (Phase-2/promotion concern, not this PR).
- **Core-file blast radius** — the entire hook is inside `if enabled`; disabled = the original code path byte-for-byte.

## Verify

- Offline unit tests (cache + a mocked operate-level hook test) — the build-env gate.
- Live re-extract on staging (concept_ref onto real nodes) → **deferred to a brief**.
