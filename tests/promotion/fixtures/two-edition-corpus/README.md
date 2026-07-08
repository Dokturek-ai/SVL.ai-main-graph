# Golden fixture — two-edition corpus

A tiny hand-authored **snapshot** (the output of `promotion.harvest`) covering two
editions of one work — no PDFs, no LLM, no DB. Every promotion behaviour G1–G5 is
exercised by exactly one designed case so golden asserts are unambiguous.

Work: `Arteriální hypertenze`, editions **2014** and **2024** (edition parsed from filename).

| Case | Node/edge | Expected |
|---|---|---|
| exact locate | `Ramipril`, `Betablokátory`, `Arteriální hypertenze` | admitted, `match=exact`/`normalized` |
| stemmed locate | `Srdeční selhání` (chunk says "srdečního selhání") | admitted, `match=stemmed` |
| quarantine `entity-not-found` | `Komorbidity` (not in its chunk text) | quarantined |
| quarantine `chunk-unresolved` | `Ghost` (`source_id` → missing chunk) | quarantined |
| quarantine `endpoint-missing` (edge) | edge `Arteriální hypertenze→Komorbidity` | quarantined |
| overlap (restated) | edge `Arteriální hypertenze→Ramipril` (both editions) | one fact, not a conflict |
| conflict | edges `→140/90 mmHg` (2014) vs `→130/80 mmHg` (2024), same `(head, rel_type)` | conflict flag |
| supersession | `140/90 mmHg` + its edge (2014-only) | `superseded_by_edition="2024"`, out of latest-default view |
| case-variant merge | `Praktický lékař` + `Praktický Lékář` | one canonical node |
| concept_ref propagation | `Arteriální hypertenze` (`I10`), `Ramipril` (`C0072973`) tagged; rest null | carried, not resolved |
