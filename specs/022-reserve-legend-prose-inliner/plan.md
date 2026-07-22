# Plan 022 — reserve-legend prose inliner

## Files

- `lightrag/operate.py` — `_apply_reserve_legends._repl` (the only behavioural change) + the two comment
  blocks that describe the old "pure insertion / `[podmínka: …]`" behaviour (4905–4913, 4925–4930, and the
  `_repl` docstring/comment at 4960–4964).
- `tests/test_reserve_footnote_inline.py` — update the assertions that encode the `[podmínka: …]` sentinel
  and the byte-for-byte pure-insertion round-trip.

No other module changes: `_collect_reserve_legends`, the regexes, and both call sites
(`operate.py:5090`, `:6023`) are untouched — only the per-marker rendering changes.

## Change detail

`_repl` today:

```python
def _repl(m):
    stars = "*" * m.group(0).count("*")
    cond = legends.get(len(stars))
    if not cond:
        return m.group(0)
    return f"{m.group(0)} [podmínka: {cond}]"
```

becomes:

```python
def _repl(m):
    stars = "*" * m.group(0).count("*")
    cond = legends.get(len(stars))
    if not cond:
        return m.group(0)
    # Replace the marker with a parenthetical of the VERBATIM legend — do not keep the stars
    # and do not wrap in [] brackets. Verbose synthesis echoes both a bare "**" (rendered "[**]")
    # and a "[…]" sentinel verbatim; grounded prose is copy-safe. Marker consumed => no "[**]"
    # leak. Length carried by `cond`, so no label needed.
    return f" ({cond})"
```

`m.group(0)` is the stars only (drug name is a lookbehind), so returning `" ({cond})"` turns
`azitromycin**` into `azitromycin (…)` — one leading space, marker gone.

## Test updates

- `test_apply_inlines_reserve_legend_cross_chunk`: expect `f"azitromycin ({RESERVE_COND})"` and
  `f"klaritromycin ({RESERVE_COND})"`; `***` drug → `doxycyklin (` + `ALLERGY_COND_HEAD` in its segment.
- `test_note_label_is_neutral_prose_not_raw_marker` → rename intent to "no bracket, no bare marker":
  assert `"[" not in out`, `"**" not in out`, and `RESERVE_COND in out`.
- `test_insertion_only_preserves_dose_text`: the transform is no longer byte-preserving (stars removed),
  so drop the byte-for-byte equality; keep the dose-token presence assertions and add that no reserve
  marker (`**`/`***`) survives.
- `test_pediatric_single_star_untouched`, `test_markdown_bold_not_mistaken_for_marker_use`,
  `test_abstain_when_legend_not_retrieved`, `test_collect_*`, `test_legend_condition_containing_star_*`,
  `test_noop_without_any_markers`: unchanged (they assert collection or the abstain/skip paths).

## Verify

1. `.venv/bin/python -m pytest tests/test_reserve_footnote_inline.py -q` → green.
2. `.venv/bin/python -m pytest tests/test_query_contextualization.py -q` → still green (untouched).
3. caveman-review the diff; fix real findings.
4. PR → staging, merge, deploy, live re-probe verbose+concise (acceptance clause 2).

## Risk

- A parenthetical instead of a labelled sentinel could read as a softer signal to the LLM, letting a
  reserve drug slip back to a co-equal first-line bullet. Mitigated: the prompt rule (operate.py:512)
  still instructs inline reserve-tagging, and the condition prose itself ("pouze pacientům, kteří nemohou
  užívat …") is self-evidently a reserve condition. The live re-probe checks reserve framing is retained.
