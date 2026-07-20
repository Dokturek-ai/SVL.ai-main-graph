# Tasks — spec 020

- [ ] T1 `edition_rename.py`: add `_RENAME_SIBLING_SUFFIXES` + pure `parsed_artifact_renames(parsed_root)`
      (NFC/NFD sweep, existing-old / free-new guard, `seen` dedupe).
- [ ] T2 `graph_routes.py` `_run_rename`: after the DB sweep, iterate `parsed_artifact_renames(parsed_dir())`,
      `os.rename` each pair, and update `LIGHTRAG_DOC_FULL.sidecar_location` for the `.parsed` dir; best-effort,
      log a count. Import `parsed_dir`, `sidecar_uri_for`, `parsed_artifact_renames`.
- [ ] T3 `tests/maintenance/test_edition_parsed_dir.py`: offline tests — yields for existing siblings, skips
      already-renamed (new exists) and absent, over `tmp_path`.
- [ ] T4 Run scoped offline suite (`tests/{maintenance,sidecar,api,guidelines,parser}`) as the staging gate.
- [ ] T5 caveman-review (cavecrew-reviewer subagent), fix real findings.
- [ ] T6 PR to `staging`, merge after gate (merge commit, no squash).
- [ ] T7 Live: trigger `apply=true`, verify Akutní průjem chunk-010 resolves a page + 0 `_unknown.pdf.parsed`.
