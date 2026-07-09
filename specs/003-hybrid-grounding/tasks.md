# Tasks 003 — Hybrid grounding

- [x] T1 — `types.py`: add `"chunk"` to `Anchor.match` doc; `fidelity` default `"verified"` → `"span"`;
  update `Quarantine.reason` doc (entity reason is only `chunk-unresolved`).
- [x] T2 — `promote.py` Phase A: node three-way (span / whole-chunk / `chunk-unresolved`); set
  `fidelity`. Retire `entity-not-found`.
- [x] T3 — `promote.py` Phase B: merged `node.fidelity = span if any member span else chunk`.
- [x] T4 — `promote.py` Phase C: edge two-way (span co-location / doc-level co-location); set
  `fidelity`. Keep `endpoint-quarantined` + `endpoints-not-co-locatable`.
- [x] T5 — `promote.py` module docstring: reflect hybrid.
- [x] T6 — `bundle.py` `_counts`: `nodes_span/nodes_chunk/edges_span/edges_chunk`.
- [x] T7 — tests: update `test_promote.py` (reasons, counts), `test_promote_edge_cases.py`
  (two-doc not-co-locatable), `test_bundle.py` (quarantined 1, fidelity counts); add hybrid golden
  tests (node chunk path, edge chunk path, fidelity split).
- [x] T8 — fixture `README.md`: Komorbidity + edge→Komorbidity now `fidelity=chunk`.
- [x] T9 — run `pytest tests/promotion -q -m offline`; green (38 passed).
- [ ] T10 — caveman-review the diff; fix findings.
- [ ] T11 — verification brief (fresh live bundle re-run + record span/chunk split) → `docs/briefs`.
