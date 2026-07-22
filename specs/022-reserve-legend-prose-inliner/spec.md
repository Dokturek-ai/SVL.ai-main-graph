# Spec 022 — reserve-legend inliner emits grounded prose (no bracket sentinel, no bare marker)

## Problem

The reserve-footnote inliner (`_apply_reserve_legends`, `lightrag/operate.py`) folds a `**`/`***`
footnote legend onto its drug marker before answer synthesis. It currently **keeps the raw stars and
appends a bracketed sentinel**: `azitromycin**` → `azitromycin** [podmínka: <cond>]`.

That relies on the synthesis LLM to reword the bracket into prose. **Concise mode does; verbose mode does
not** — it parrots the sentinel verbatim. Live staging probe 2026-07-22 (`answer_mode=verbose`, forced
cache-miss, `scratch/probe_em_verbose_loadingdose.py` + full-answer pull):

- `eritema`: `**azitromycin** **[podmínka: pouze pacientům, kteří nemohou užívat …]**` — bracket echoed
  verbatim, even bolded.
- `erithema`: `**azitromycin [**]** 1× 500 mg …` plus an LLM-invented `Poznámka k označení [**]:` section.

The condition text survives (content is safe), but the answer shows an ugly `[podmínka: …]` / `[**]`
token. PR #60 (neutral `[podmínka:]` label) only fixed **concise**; verbose was never probed. Residual 2
of brief `2026-07-20-guidelines-em-verbose-loading-dose-and-marker-leak` is therefore **not fully
resolved**.

Root cause: the inliner injects a **bracketed sentinel** and trusts a probabilistic component (the LLM)
to be the last writer that turns it into prose. That violates the Verifiable-AI Standard ("the
probabilistic component is never the last writer of load-bearing content").

(Note: Residual 1 — the azithromycin partial-dose hazard — did **not** reproduce in the same 3 verbose
runs: the dose is stated whole with `první den dvojnásobná dávka` or omitted entirely, never a bare
`500 mg`. The line-512 prompt rule holds it. Residual 1 stays open/latent; it is out of scope here.)

## Goal

The inlined reserve condition reads as correct grounded prose **in both concise and verbose modes**, with
no `[]` bracket token and no bare `**`/`***` surviving into the answer — regardless of whether the LLM
rewords it or copies it verbatim.

## Approach

Change `_apply_reserve_legends._repl` from **append-bracket-keep-stars** to **replace-marker-with-prose**:

- The `_RESERVE_USE_RE` match is the stars only (`m.group(0)` = `**`, drug name is a lookbehind). Instead
  of returning `"{stars} [podmínka: {cond}]"`, return a parenthetical of the verbatim legend:
  `" ({cond})"` → `azitromycin (Pouze pacientům, kteří nemohou užívat doxycyklin, amoxicilin, cefuroxim
  axetil či penicilin.)`.
- This **consumes the raw stars** (no `**` left to be re-typeset as `[**]`) and uses **no brackets** (a
  verbatim LLM copy is already correct prose). The legend text is inserted verbatim (grounded, no
  paraphrase) — the LLM is no longer the last writer of the safety condition.
- Length-agnostic: `**` (reserve condition) and `***` (allergy/indication) both carry their meaning in
  `cond`; the parenthetical needs no label.

Everything else is unchanged: cross-chunk legend collection (`_collect_reserve_legends`), the abstain path
(no legend retrieved → marker left untouched), the single-`*` pediatric exclusion, the markdown-bold
skip, and dose/loading-dose text (which is never inside the matched marker).

The "pure insertion, never alters existing characters" invariant is deliberately relaxed to "removes only
the footnote marker, never dose text" — the stars are not load-bearing clinical content; doses are, and
they are untouched.

## Acceptance

- Offline `tests/test_reserve_footnote_inline.py` (updated): after transform, `azitromycin (<reserve
  cond>)` and `klaritromycin (<reserve cond>)` appear; the `***` drug carries its own (allergy) legend; no
  `[` bracket, no bare `**`/`***` after a drug name; dose tokens (`první den dvojnásobná dávka`,
  `500 mg p. o.`, `200–400 mg denně`) preserved verbatim; abstain / pediatric-`*` / markdown-bold cases
  unchanged.
- Live (post-deploy): `answer_mode=verbose` AND `concise` EM answers show the reserve condition as prose,
  with **no** `[podmínka:`, `[**]`, `[***]`, or bare `**` token on azitromycin/klaritromycin, and the
  loading dose still present when a dose is stated.

## Non-goals

- Residual 1 (partial-dose whole-or-none prompt tightening) — separate, currently latent.
- Any change to legend collection, retrieval, rerank, or ingest.
- Restyling the raw table `**` markers at ingest time (this is a query-side context transform only).
