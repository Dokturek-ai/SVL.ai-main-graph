# Plan 003 — Hybrid grounding

Pure change, confined to `lightrag.promotion`. No substrate, no I/O, no LLM.

## Files touched

| file | change |
|---|---|
| `lightrag/promotion/types.py` | `Anchor.match` doc + `"chunk"` variant; `fidelity` default `"verified"` → `"span"`; `Quarantine.reason` doc (drop `entity-not-found`) |
| `lightrag/promotion/promote.py` | rewrite Phase A (node three-way) + Phase C (edge two-way); set `fidelity`; module docstring |
| `lightrag/promotion/bundle.py` | `_counts` → add `nodes_span/nodes_chunk/edges_span/edges_chunk` |
| `tests/promotion/test_promote.py` | update quarantine-reason + admitted-count goldens; add node/edge chunk-path + fidelity-split tests |
| `tests/promotion/test_promote_edge_cases.py` | `endpoints-not-co-locatable` now needs a **two-doc** setup |
| `tests/promotion/test_bundle.py` | quarantined count `3 → 1`; assert per-fidelity counts present |
| `tests/promotion/fixtures/two-edition-corpus/README.md` | Komorbidity now `fidelity=chunk` (admitted), edge→Komorbidity now `fidelity=chunk` |

## Design

### Phase A (nodes) — `promote.py`

Per node, walk `source_ids`:
- collect span anchors where `locate()` hits (+ their edition/work), and remember the resolving
  chunks;
- `resolved_any` = at least one `source_id` maps to a chunk in the registry.
- **span** path (`span_anchors` non-empty): emit exactly today's anchors/editions/works,
  `fidelity="span"` — unchanged for every currently-admitted node.
- **chunk** path (resolved but no span): anchors = whole-chunk `Anchor(sid, 0, len(content), "chunk")`
  over the resolving chunks; editions/works from those chunks; `fidelity="chunk"`.
- **quarantine** path (`not resolved_any`): `Quarantine("entity", name, "chunk-unresolved", ...)`.

Merge (Phase B) unchanged except: `node.fidelity = "span" if any member is span else "chunk"`.

### Phase C (edges) — `promote.py`

Endpoints must both be admitted (`by_name`), else `endpoint-quarantined` (unchanged).
- **span** path: today's logic — a source chunk where both endpoints `locate()` → `fidelity="span"`,
  anchor = head span, pick max-edition candidate.
- **chunk** path (no span co-location): `head_docs`/`tail_docs` = docs of each endpoint's
  `source_ids`; among the **edge's own** source chunks, keep those whose `doc_id ∈ head_docs ∩
  tail_docs`; pick max-edition → whole-chunk anchor, `fidelity="chunk"`.
- **quarantine**: no such chunk → `endpoints-not-co-locatable`.

### Manifest — `bundle.py`

`_counts` gains four ints. `anchor_coverage` still hard-coded 1.0 (a chunk anchor is an anchor).

## Verify

- `.venv/bin/pytest tests/promotion -q -m offline` green.
- `_counts` shows `nodes_span + nodes_chunk == nodes`, same for edges.
- Fixture: `nodes=8, edges=5, quarantine=1` (Ghost `chunk-unresolved`); Komorbidity node +
  edge→Komorbidity carry `fidelity="chunk"`; all previously-span records stay `fidelity="span"`.
