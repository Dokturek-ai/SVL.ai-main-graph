# Tasks 023 — dose whole-or-none

- [ ] T1 — `prompt.py`: append the WHOLE-OR-NONE clause to the dose-qualifier bullet in BOTH `rag_response`
      (:512) and `naive_rag_response` (:569) via one `replace_all` edit (identical strings). → verify: both
      lines carry the clause; templates still format (no stray `{}`).
- [ ] T2 — run `.venv/bin/python -m pytest -q`. → verify: offline suite green (unchanged from baseline).
- [ ] T3 — caveman-review the diff; fix real findings. → verify: no unaddressed correctness finding.
- [ ] T4 — PR → staging, merge (home repo), wait deploy. → verify: staging deploy SUCCESS.
- [ ] T5 — live re-probe ≈10 generations (concise+verbose × `erythema`/`erithema`, forced cache-miss).
      → verify: no generation emits azitromycin `500 mg` without its `první den dvojnásobná dávka` / whole-dose
      modifier; update brief Residual 1 (resolved, or still latent with the residual-risk guard as follow-up).
