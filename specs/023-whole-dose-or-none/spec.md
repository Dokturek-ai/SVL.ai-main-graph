# Spec 023 — dose is whole-or-none (no base dose stripped of its loading modifier)

## Problem

Residual 1 of brief `2026-07-20-guidelines-em-verbose-loading-dose-and-marker-leak`: the EM answer can state
a drug's **base dose without its loading modifier**. Source (SVL Tab 3.1):
`azitromycin** 1× 500 mg p. o. …, první den dvojnásobná dávka` (day-1 = 1000 mg). The synthesis LLM
sometimes emits `azitromycin … 1× 500 mg p.o.` **alone** — a stated-but-partial dose = day-1 underdose for
exactly the reserve patient who lands on azithromycin.

Intermittent / synthesis variance. Live re-probe 2026-07-23 (spec 022, 5 generations, forced cache-miss):
the modifier dropped **1×** — concise `erythema` `top_k=71` (`azitromycin … 1× 500 mg p.o.` alone) — and was
present in the other 4 (concise `top_k=72/75`, verbose `top_k=73`). It is **no longer verbose-only**: the
spec-022 prose inliner makes concise emit the full dose line more often, so the earlier "concise is safe
(drops the mg entirely)" premise no longer holds; the drop now happens in either mode.

Root cause: the grounding rule (prompt.py:512 / :569) says *preserve every qualifier EXACTLY* but does not
make dose-completeness an **atomic whole-or-none** obligation — so under length pressure the LLM keeps the
base dose and drops the modifier, treating them as severable. The probabilistic component is the last writer
of a load-bearing dose (Verifiable-AI Standard).

## Goal

A drug's dose is **atomic**: if a loading / first-day / tapering modifier for that drug IS in the Context,
the answer states the dose WHOLE (base + modifier) or omits the drug's dose entirely — it NEVER emits the
base dose stripped of the modifier. Holds in **both** concise and verbose modes.

## Approach

Add one **whole-or-none** clause to the shared "Content & Grounding" dose-qualifier bullet, in BOTH answer
templates (identical text at `rag_response` prompt.py:512 and `naive_rag_response` :569). The bullet already
says "preserve every management-relevant qualifier EXACTLY"; the new clause makes dose completeness atomic
and gives the concrete azithromycin example as the forbidden pattern.

Because concise vs verbose is only the `{answer_style}` slot injected into these same templates, editing the
shared grounding bullet covers **both** modes without touching `answer_style_concise` / `answer_style_verbose`.

Prompt-only. No ingest, retrieval, rerank, or inliner change (spec 022 stands).

## Acceptance

- Offline: the whole-or-none clause is present in both prompt.py:512 and :569 (identical); offline suite
  stays green (no test asserts the old wording).
- Live (post-deploy): a multi-generation re-probe (≈10 runs, concise+verbose × `erythema`/`erithema`,
  forced cache-miss) shows **no** generation that states `azitromycin … 500 mg` without its
  `první den dvojnásobná dávka` (or `1000 mg` / whole-dose) modifier. A drug may omit its dose, but never
  states a partial one.

## Non-goals

- Any change to spec 022's prose inliner, legend collection, retrieval, rerank, or ingest.
- Broadening beyond dose atomicity (line/rank tagging already handled by the existing bullet).
