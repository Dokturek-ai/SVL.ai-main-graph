# Plan 023 — dose whole-or-none

## Files

- `lightrag/prompt.py` — the dose-qualifier bullet in "2. Content & Grounding", present **identically** in
  both `PROMPTS["rag_response"]` (line 512) and `PROMPTS["naive_rag_response"]` (line 569). One clause added
  to the end of that bullet, applied to both via a single `replace_all` edit (the strings are byte-identical).

No other change: `answer_style_concise` / `answer_style_verbose`, the inliner (spec 022), retrieval, rerank,
ingest all untouched. Editing the shared grounding bullet covers both answer modes because concise/verbose is
only the `{answer_style}` slot injected into these same two templates.

## Change detail

The bullet ends today with:

> … never render them as co-equal first-line bullets.

Append after it:

> A dose is WHOLE-OR-NONE: if a dose modifier (a loading / first-day / tapering dose) for a drug IS in the
> Context, you MUST state it together with that drug's base dose — treat base + modifier as one atomic value.
> NEVER emit the base dose stripped of it (e.g. `azitromycin 1× 500 mg` without its
> `první den dvojnásobná dávka` day-1 doubling is a partial dose = day-1 underdose, and is forbidden). Under
> length pressure, omit the drug's dose entirely rather than state a partial one.

## Test updates

None. The prompt is a template string; no offline test asserts its wording, and adding a brittle
"clause is present" string test buys little. Offline suite is run only to confirm nothing that greps the
prompt breaks.

## Verify

1. `.venv/bin/python -m pytest -q` (offline suite) → green (baseline: same as pre-change).
2. caveman-review the diff; fix real findings.
3. PR → staging, merge (home repo), deploy.
4. Live multi-generation re-probe (≈10 runs, concise+verbose × `erythema`/`erithema`, forced cache-miss):
   assert no generation states `azitromycin … 500 mg` without its loading modifier. A dose may be omitted,
   never partial.

## Risk

- Prompt-only nudge against a stochastic drop cannot be *proven* fixed in finite samples — a 1/5 base rate
  means ~10 clean generations lowers but does not eliminate residual risk. Acceptance is "no partial dose in
  ≈10 generations"; if one still slips, escalate to a deterministic post-synthesis dose-completeness guard
  (out of scope here — raise a child brief). The clause is the right first lever (cheap, no code path).
- Retrieval-gap residual (caveman-review): the clause fires only when the modifier "IS in the Context". If a
  modifier lived in a DIFFERENT chunk that retrieval did not return, the rule would not fire and the model
  could still state a bare base dose without violating it. Not fixed here, and **low applicability to this
  hazard**: the azithromycin loading modifier `první den dvojnásobná dávka` sits on the SAME source table row
  as the base dose (see `CHUNK_TABLE` in `tests/test_reserve_footnote_inline.py`), so if the base dose is in
  Context the modifier is too. Broadening the clause to abstain on any base dose whose completeness is
  unverifiable would over-fire (drop legit complete doses) — the true fix for a cross-chunk modifier is
  retrieval-side, out of scope. Acknowledged residual, not a blocker.
