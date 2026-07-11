# Tasks 010 — concept_ref verify-or-abstain

- [ ] T1 `grounding.py`: `build_verify_prompt` + `parse_verdict` (KEEP→True, else→False). → verify: unit tests.
- [ ] T2 `grounding.py`: `verify_concept_ref(entity, ref, doc_context, *, verify_llm_func)`. → verify: KEEP/DROP/raise mocked.
- [ ] T3 `grounding.py`: `ground_entity` + `ground_entity_cached` gain `verify_llm_func=None`; verify after pick, keep-or-abstain, cache verified. → verify: with-verifier keep/drop; no-verifier back-compat; verdict cached.
- [ ] T4 `lightrag.py` `_resolve_grounding_config`: build `verify_llm` (openai_complete_if_cache + CONCEPT_REF_VERIFY_MODEL + binding env); add to config. → verify: default model resolves; enabled=false ⇒ absent.
- [ ] T5 `operate.py` `_maybe_ground_concept_ref`: thread `verify_llm_func` into `ground_entity_cached` (best-effort). → verify: mocked operate test still passes; concept_ref present only when kept.
- [ ] T6 Run offline suite (grounding + wiring + extraction + promotion) — staging gate.
- [ ] T7 caveman-review → fix.
- [ ] T8 Land PR → staging. Raise the live verify probe brief.
