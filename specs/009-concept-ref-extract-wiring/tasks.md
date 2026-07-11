# Tasks 009 — concept_ref extract-path wiring

- [ ] T1 `grounding.py`: `resolve_cache_key(name, type, description)` — sha256 over normalized `name|type|description`. → verify: unit test (stable, order/whitespace-normalized, distinct inputs distinct keys).
- [ ] T2 `grounding.py`: `load_resolve_cache(path)` / `append_resolve_cache(path, key, refs)` — JSONL, missing ⇒ `{}`, corrupt line skipped. → verify: unit test (missing path, round-trip, corrupt line non-fatal).
- [ ] T3 `grounding.py`: `ground_entity_cached(...)` — cache-first wrapper over `ground_entity`. → verify: unit test — HIT calls neither `llm_func` nor `api`; MISS grounds + appends + subsequent same-key HIT.
- [ ] T4 `lightrag.py` `__post_init__`: resolve `_concept_ref_grounding` config into `global_config` (enabled/neural_base/cache_path/cache). → verify: default env ⇒ `enabled=False`.
- [ ] T5 `operate.py` `_merge_nodes_then_upsert`: the guarded hook + `_extract_llm_adapter`; clinical-type gate; best-effort try/except; attach `node_data["concept_ref"]`. → verify: mocked operate-level test — enabled+clinical ⇒ upsert gets `concept_ref`; disabled ⇒ none + not called; non-clinical ⇒ skipped.
- [ ] T6 Run offline suite (`tests/test_grounding.py` + `tests/promotion/` + the new operate test) — the staging gate.
- [ ] T7 caveman-review the diff → fix findings.
- [ ] T8 Land PR → staging. Raise the LIVE re-extract verification brief.
