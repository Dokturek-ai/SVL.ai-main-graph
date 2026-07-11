# Plan 007 — edge subject (implementation)

Design = `spec.md` (approved). This plans the build. **Additive + backward-compatible:** the graph stays
undirected; `subject` is a new edge PROPERTY (an entity name ∈ {source, target}); a record without it
defaults `subject = source`, so a pre-existing 5-field extraction still parses. The prompt-emission
QUALITY (does the LLM tag subject reliably/correctly) is verified probe-first LIVE → deferred to a brief.

## Threading (each additive, file:line)

1. **Parse** — `operate.py:520 _handle_single_relationship_extraction`: accept a **6th** delimited field
   `subject`; length gate `!= 5` → `not in (5, 6)`; sanitize + validate `subject ∈ {source, target}` (after
   normalization), else default `source`; 5-field record ⇒ `subject = source`. Fix the legacy `weight`
   quirk (`record_attributes[-1]`) so it doesn't read `subject` as a weight. JSON: `operate.py:645
   _process_json_extraction_result` reads `rel_data["subject"]` with the same validate/default. Add
   `subject` to both returned edge dicts (`:584`, `:811`). Also `_normalize_text_extraction_record_attributes`
   (`:607`) — allow the 6-field row through its recovery.
2. **Merge reconcile** — `operate.py:2309 _merge_edges_then_upsert`: gather `subject` across `edges_data`
   fragments (+ `already_edge`), keep the **most frequent**, tie-break **first-seen**; validate the winner
   `∈ {src_id, tgt_id}` else default `src_id`. Add `subject` to the `upsert_edge` payload (`:2809`) and the
   returned `edge_data` (`:2827`). Survives the sorted-key merge because it is data, not order.
3. **Store** — `neo4j_impl.py:1202 upsert_edge` (`SET r += $properties`) is already additive — no change;
   the read path (`get_edge`, `get_all_edges`) returns all properties. (Verified like the Phase-1 node field.)
4. **Harvest** — `promotion/harvest.py:70`: add `"subject": _prop(e, "subject")` to the edge dict.
5. **Promote** — `promotion/types.py:73 GroundedEdge`: add `subject_id: Optional[str] = None` (+ in
   `to_dict`). `promotion/promote.py:192`: resolve `e["subject"]` via `by_name` → its node; set
   `subject_id = that node.node_id` (it is head or tail); leave `None` if unresolved. `object_id` stays
   implicit (the other endpoint).
6. **Prompt** — `prompt.py`: format spec (`:62`), the relation instruction (`:48`), the record-count note
   (`:56` "exactly 5" → "5 or 6"), and the relation rows in the default text + JSON examples gain a 6th
   `subject` field (= the entity the fact is ABOUT). Same for the Czech clinical examples in
   `prompts/entity_type/clinical_cs.yml` (text + json). Instruction: "subject = the entity name (which
   MUST be the source or the target) that the relationship is ABOUT; for X→Y causal/effect statements pick
   the disease-of-record."

## Backward compatibility

- A 5-field relation row (old prompt / gleaning / other profiles) parses with `subject = source` — no break.
- Existing stored edges have no `subject`; harvest `_prop` → `None` → `subject_id = None`. Fine (mkn10 treats
  a missing subject as today's behavior).
- neo4j/merge/lock/retrieval untouched (undirected).

## Verify

- Offline (build-env gate): parser (6-field parse, 5-field default-to-source, subject ∉ {src,tgt} → source),
  merge reconciliation (most-frequent + tie-break + validate), harvest reads subject, GroundedEdge carries
  `subject_id`, promote resolves subject→subject_id (and `None` when unresolved).
- **Deferred to a brief (needs a live LLM):** the probe measuring the LLM emits `subject ∈ {source,target}`
  for (near) every relation and correctly on `etiology_note`/`complication` — then the combined full-corpus
  run + mkn10 re-judge (directional fields ≤ ~15% hard-wrong).

## Risks

- **Prompt regressions** — adding a field can nudge extraction. Mitigate: keep the format change minimal,
  examples consistent, and gate the real judgement on the live probe before the full-corpus run.
- **Gleaning / continue prompt** must also allow 6 fields (same format spec covers it).
- **Blast radius** in `_merge_edges_then_upsert` — subject reconciliation is isolated + defaults safely.
