# Tasks 007 — edge subject

- [ ] T1 `operate.py` `_handle_single_relationship_extraction`: accept 6th `subject` field (5 or 6 parts), validate ∈{source,target} else default source; fix the weight-from-last quirk; add `subject` to the dict. → verify: unit tests (6-field parse, 5-field default, invalid subject → source).
- [ ] T2 `operate.py` `_process_json_extraction_result` + `_normalize_text_extraction_record_attributes`: same subject read/validate/default; allow 6-field recovery. → verify: json parse test.
- [ ] T3 `operate.py` `_merge_edges_then_upsert`: reconcile subject (most-frequent, tie-break first-seen, validate ∈{src,tgt} else src); add to upsert payload + returned edge_data. → verify: merge reconciliation unit test.
- [ ] T4 `promotion/harvest.py`: read `subject` into the edge dict. → verify: harvest test (edge with/without subject property).
- [ ] T5 `promotion/types.py` `GroundedEdge`: add `subject_id` (+ to_dict). `promotion/promote.py`: resolve subject name → subject_id (None if unresolved). → verify: promote test (subject resolves to head/tail node_id; absent → None).
- [ ] T6 `prompt.py` + `prompts/entity_type/clinical_cs.yml`: 6th `subject` field in the format spec, instruction, record-count, and the relation rows of the text + json examples. → verify: a smoke test that the format string + examples mention `subject`; offline extraction-stability tests still pass.
- [ ] T7 Run offline suite (grounding/extraction/promotion/pipeline) — the staging gate.
- [ ] T8 caveman-review → fix.
- [ ] T9 Land PR → staging. Raise the live probe-emission + combined-run brief.
