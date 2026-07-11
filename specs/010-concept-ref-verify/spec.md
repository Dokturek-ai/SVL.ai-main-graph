# Spec 010 — concept_ref verify-or-abstain (pick + verify symmetry)

**Status:** offline-built; the live verify probe DEFERRED to a brief (no LLM in build env — mirrors 006/008/009).
**Source:** brief `guidelines-concept-ref-verify-or-abstain` (human-authorized architectural decision). Extends spec 008/009.

## Problem

concept_ref grounding is probabilistic and empirically makes a large share of **valid-but-wrong-context**
picks the deterministic spine guard (existence-only) cannot catch: **class → specific drug** (Antihypertenziva
→ aprocitentan), **category confusion** (symptom → diagnosis; procedure/method → a real-but-wrong Z-code:
Spánková deprivace → T73.9), **labtest with no proper code**. A prototype judge dropped **29–69%** of grounds
on 2 DPs. Per the **Verifiable-AI Standard**, the grounding LLM must not be the last writer of load-bearing
content — it must verify-or-abstain within our boundary before the code is written.

## Decision (settled in the brief — do NOT re-litigate)

Spec 008 placed context-reasoning correctly: **mkn10 = context-free vocabulary authority (candidates);
guidelines = context owner (the pick)**. The **verify is the pick's mirror** — the same context question. So
complete grounding into a **pick + verify** symmetry, both context-LLM, on the guidelines side, verify-or-
abstain **before** the concept_ref is written:

```
candidate → pick → verify → keep / abstain     (all guidelines-side)
```

- **Recall-first pick, precision-first verify.** With a downstream verify, over-grounding is recoverable
  (verify drops junk) but over-abstaining is not (a missed code is gone). So the pick stays **gpt-5.4-mini**
  (recall-first, cheapest — settled by A/B); the **verify uses a stronger model** (`CONCEPT_REF_VERIFY_MODEL`,
  default gpt-5.1) — it is the safety check.
- **Verify-or-abstain default:** a DROP verdict OR any judge error ⇒ abstain (drop the ref). Uncertainty →
  abstain. Precision > recall for a load-bearing clinical graph.
- **Cache the verdict** with the concept_ref (re-runs skip pick AND verify).
- mkn10 does NOT re-gate concept_ref appropriateness (moot — we own it). See `mkn10-rejudge-readiness`.

## What ships (offline unit-tested)

### `lightrag/grounding.py` — the verify core (injectable, offline-testable)

- **`build_verify_prompt(name, node_type, description, ref, doc_context)`** — the judge prompt: given the
  entity + the picked `code — display`, decide whether the code correctly represents THIS entity in context
  (checks: right clinical meaning? not a valid-but-wrong-category/homonym? not a procedure/labtest that has
  no MKN-10 diagnosis code?). Answer `KEEP | reason` or `DROP | reason`.
- **`parse_verdict(llm_text) -> bool`** — `True` = KEEP, `False` = DROP; anything not clearly KEEP ⇒ DROP
  (abstain-on-uncertainty).
- **`async verify_concept_ref(entity, ref, doc_context, *, verify_llm_func) -> bool`** — one judge call.
- **`ground_entity` / `ground_entity_cached` gain an optional `verify_llm_func`:** after the pick, if a
  verifier is provided and a ref was picked, verify it; keep only on KEEP, else return `[]`. A judge
  exception is caught → DROP (abstain). The cache stores the **verified** result.

### `lightrag/lightrag.py` — build the verify LLM func

- `_resolve_grounding_config` builds `verify_llm` = a `(prompt) -> str` closure over
  `openai_complete_if_cache(CONCEPT_REF_VERIFY_MODEL, prompt, base_url=<LLM_BINDING_HOST>, api_key=<LLM_BINDING_API_KEY>)`
  — the same LLM binding as extract, a distinct (stronger) model. Added to `_concept_ref_grounding`.
  Verify is gated by the same `CONCEPT_REF_GROUNDING_ENABLED` flag (+ `CONCEPT_REF_VERIFY_MODEL`); when the
  model env is unset it defaults to gpt-5.1.

### `lightrag/operate.py` — thread the verifier

- `_maybe_ground_concept_ref` passes `verify_llm_func` from the grounding config into `ground_entity_cached`.
  Runs in the same best-effort try/except (a verify failure abstains, never blocks the upsert). The verify LLM
  call is a separate round-trip; it stays out of the merge lock's critical section as far as the existing
  structure allows (the grounding call already runs there — latency was flagged; not worsened structurally,
  the judge just adds one call on the grounded subset).

## Verification (offline, build-env safe)

`tests/test_grounding.py` additions, no LLM:
- `build_verify_prompt`: contains the code+display, the entity, and asks KEEP/DROP.
- `parse_verdict`: `KEEP | ...` → True; `DROP | ...` → False; garbage/empty → False (abstain-on-uncertainty).
- `verify_concept_ref`: a mocked KEEP verifier ⇒ True; DROP ⇒ False; a raising verifier ⇒ False (swallowed).
- `ground_entity_cached` with a verifier: pick returns a ref + verifier KEEP ⇒ ref kept; verifier DROP ⇒ `[]`;
  no verifier ⇒ ref kept unchanged (back-compat); the verdict is cached (second call makes zero LLM calls).

## Deferred / non-goals

- **Live verify probe** (does the wired verify drop the wrong-context class on real staging chunks) — needs
  LLM/mkn10/staging → a brief, mirroring 008/009. The prototype (`scratch/probe_judge_test.py`) already
  validated the concept on 2 DPs.
- A verify pass for the **subject** (spec 007) — same pick+verify symmetry could extend; out of scope here.
- Richer candidate semantics from mkn10 (a future contract enhancement to strengthen the judge) — not needed
  for v1 (the probe judged from the display string alone).

## Acceptance

- The verify core ships with passing offline tests; a KEEP keeps, a DROP/error abstains, the verdict caches.
- `ground_entity_cached` with a verifier drops a wrong ref and keeps a right one (mocked); without a verifier
  it is byte-for-byte the spec-009 behavior (back-compat).
- The concept_ref that leaves guidelines is verified → Verifiable-AI conformant. Live drop/keep behavior on
  real chunks captured as a brief. Built BEFORE the combined full-corpus run.
