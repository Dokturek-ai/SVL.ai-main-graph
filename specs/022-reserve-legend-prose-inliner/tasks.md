# Tasks 022 — reserve-legend prose inliner

- [x] T1 — `operate.py`: rewrite `_apply_reserve_legends._repl` to return `" ({cond})"` (replace marker,
      verbatim legend, no brackets). → verify: function returns prose, no `[`/`**`.
- [x] T2 — `operate.py`: update the inliner header comment (4905–4913) and the bold-skip comment
      (4925–4930) — "pure insertion / `[podmínka: …]`" no longer describes the behaviour. → verify: comments
      match code.
- [x] T3 — `tests/test_reserve_footnote_inline.py`: update `test_apply_inlines_reserve_legend_cross_chunk`,
      `test_no_bracket_or_bare_marker_survives`, `test_marker_replacement_preserves_dose_text` per
      plan. → verify: assertions encode the prose form + no bracket/marker + dose tokens intact.
- [x] T4 — ran `pytest tests/test_reserve_footnote_inline.py tests/test_query_contextualization.py -q`
      → 14 passed.
- [x] T5 — caveman-review the diff; fixed 2 real findings (vacuous assertion, weak dose proof), skipped
      1 false positive (double-space). → verify: no unaddressed correctness finding.
- [x] T6 — PR #61 → staging, merged (0a29ada8), deploy SUCCESS, live re-probed verbose+concise. → PASS:
      no `[podmínka:`/`[**]`/`[***]` sentinel in any of 5 generations; reserve condition rendered as
      grounded prose in BOTH modes; `**` are markdown bold (balanced), not raw markers; loading dose kept
      (present at top_k=72/73/75; dropped once at concise top_k=71 = Residual 1, out of scope, still latent).
