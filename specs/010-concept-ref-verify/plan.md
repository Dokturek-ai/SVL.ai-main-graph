# Plan 010 — concept_ref verify-or-abstain

## Approach

Additive to spec 009. The verify CORE is pure + injectable (grounding.py) → fully offline-testable. Only the
LLM-func construction (verify model via the binding) lives in lightrag.py. Back-compatible: no `verify_llm_func`
⇒ spec-009 behavior unchanged.

## Anchors / edits

- `lightrag/grounding.py`
  - `build_verify_prompt(name, node_type, description, ref, doc_context)` — the judge prompt (Czech; mirrors
    `scratch/probe_judge_test.py` JUDGE_PROMPT, which is validated).
  - `parse_verdict(text) -> bool` — KEEP→True, else False (abstain-on-uncertainty).
  - `verify_concept_ref(entity, ref, doc_context, *, verify_llm_func) -> bool`.
  - `ground_entity(..., verify_llm_func=None)` — after `parse_concept_ref`, if a verifier + a ref, verify;
    keep on True else `[]`. Catch judge exceptions → False (abstain).
  - `ground_entity_cached(..., verify_llm_func=None)` — pass through; cache the verified result.
- `lightrag/lightrag.py` `_resolve_grounding_config`
  - build `verify_llm`: `async (prompt) -> str` = `openai_complete_if_cache(_VERIFY_MODEL, prompt,
    base_url=get_env_value("LLM_BINDING_HOST", ...), api_key=get_env_value("LLM_BINDING_API_KEY", ...))`.
    `_VERIFY_MODEL = CONCEPT_REF_VERIFY_MODEL` (default `gpt-5.1-2025-11-13`). Add to `_concept_ref_grounding`.
- `lightrag/operate.py` `_maybe_ground_concept_ref`
  - pull `verify_llm_func = grounding_cfg.get("verify_llm")`; pass to `ground_entity_cached`. Same best-effort
    try/except (verify failure ⇒ abstain, never blocks upsert).

## Config

- `CONCEPT_REF_GROUNDING_ENABLED` (existing) gates the whole thing; verify is on whenever grounding is on.
- `CONCEPT_REF_VERIFY_MODEL` — default `gpt-5.1-2025-11-13`. The stronger judge model (pick stays mini).

## Risks / mitigations

- **Latency** — verify adds one LLM call per GROUNDED entity (abstains skip it). Cache halves re-run cost;
  the wired grounding already runs in the merge path — verify doesn't change that structure, just adds a call
  on the grounded subset. Acceptable for the one-time run; watch at scale.
- **Judge model plumbing** — isolated to `_resolve_grounding_config`; grounding.py stays binding-agnostic
  (injectable), so all logic is offline-tested regardless.
- **Over-drop** — verify defaults to abstain on uncertainty. Intended (precision > recall). The pick is
  recall-first (mini) so real codes are offered; verify prunes. Net measured by the live probe + mkn10.

## Verify

- Offline unit tests (build_verify_prompt / parse_verdict / verify_concept_ref / ground_entity_cached+verifier).
- Live verify probe on staging → deferred to a brief.
