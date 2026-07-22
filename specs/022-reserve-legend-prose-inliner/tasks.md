# Tasks 022 — reserve-legend prose inliner

- [ ] T1 — `operate.py`: rewrite `_apply_reserve_legends._repl` to return `" ({cond})"` (replace marker,
      verbatim legend, no brackets). → verify: function returns prose, no `[`/`**`.
- [ ] T2 — `operate.py`: update the inliner header comment (4905–4913) and the bold-skip comment
      (4925–4930) — "pure insertion / `[podmínka: …]`" no longer describes the behaviour. → verify: comments
      match code.
- [ ] T3 — `tests/test_reserve_footnote_inline.py`: update `test_apply_inlines_reserve_legend_cross_chunk`,
      `test_note_label_is_neutral_prose_not_raw_marker`, `test_insertion_only_preserves_dose_text` per
      plan. → verify: assertions encode the prose form + no bracket/marker + dose tokens intact.
- [ ] T4 — run `pytest tests/test_reserve_footnote_inline.py -q` and
      `pytest tests/test_query_contextualization.py -q`. → verify: both green.
- [ ] T5 — caveman-review the diff; fix real findings. → verify: no unaddressed correctness finding.
- [ ] T6 — PR → staging, merge (home repo), wait deploy, live re-probe verbose+concise. → verify:
      acceptance clause 2 (no `[podmínka:`/`[**]`/bare `**`; condition prose; loading dose kept).
