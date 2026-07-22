# Tasks 023 — dose whole-or-none

- [x] T1 — `prompt.py`: append the WHOLE-OR-NONE clause to the dose-qualifier bullet in BOTH `rag_response`
      (:512) and `naive_rag_response` (:569) via one `replace_all` edit (identical strings). → verify: both
      lines carry the clause (grep=2); templates still format (import + `.format`-safety checked).
- [x] T2 — ran `pytest tests/test_reserve_footnote_inline.py tests/test_query_contextualization.py -q`
      → 14 passed (prompt change can't break these; import OK).
- [x] T3 — caveman-review the diff; 1 🟡 retrieval-gap residual triaged as low-applicability (modifier
      co-located on same source row), recorded in plan.md. No correctness fix needed.
- [x] T4 — PR #62 → staging, merged (775d477e), deploy SUCCESS.
- [x] T5 — live re-probe 10 generations (concise+verbose × `erythema`/`erithema`, `top_k=80–89` cache-miss).
      → PASS: **0 partial-dose hazards** (was 1/5 pre-fix). 9 state `500 mg` WITH `první den dvojnásobná
      dávka`; 1 omits the mg entirely (safe). Brief Residual 1 marked resolved.
