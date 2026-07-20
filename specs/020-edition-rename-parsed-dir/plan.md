# Plan — spec 020

## Files

- `lightrag/maintenance/edition_rename.py` — add the **pure planner** `parsed_artifact_renames(parsed_root)`.
  Keeps the filesystem-path logic testable offline (tmp_path) and beside the existing `plan_rename`.
- `lightrag/api/routers/graph_routes.py` — in `_run_rename`, after the DB sweep loop, call the planner and
  perform the `os.rename` + `LIGHTRAG_DOC_FULL.sidecar_location` update.
- `tests/maintenance/test_edition_parsed_dir.py` — new offline tests for the planner.

## `parsed_artifact_renames(parsed_root: Path) -> list[tuple[Path, Path]]`

```
_RENAME_SIBLING_SUFFIXES = ("", ".parsed", ".mineru_raw")

for old_nfc, year in EDITION_YEARS.items():
    new_nfc = _new_name(old_nfc, year)
    for norm in ("NFC", "NFD"):
        old_base = normalize(norm, old_nfc); new_base = normalize(norm, new_nfc)
        for suffix in _RENAME_SIBLING_SUFFIXES:
            old_p = parsed_root / f"{old_base}{suffix}"; new_p = parsed_root / f"{new_base}{suffix}"
            if old_p already yielded: continue
            if old_p.exists() and not new_p.exists(): yield (old_p, new_p)
```

- `EDITION_YEARS` keys end `_unknown.pdf`; `_new_name` gives `_<year>.pdf`. Suffix `""` = the archived source
  PDF `<name>.pdf`; `.parsed` = the sidecar dir; `.mineru_raw` = the raw MinerU dir.
- NFC/NFD: only the spelling that physically exists on the volume yields, so the derived URI later matches the
  stored (NFD) `sidecar_location`. A `seen` set dedupes the identical ASCII case.
- Pure w.r.t. mutation (reads the fs, never writes); the runner owns `os.rename` + the SQL.

## Runner step in `_run_rename` (after the `for old, new in work:` loop)

```
from lightrag.utils_pipeline import parsed_dir, sidecar_uri_for
for old_p, new_p in parsed_artifact_renames(parsed_dir()):
    is_parsed = new_p.name.endswith(".parsed")
    old_uri, new_uri = (sidecar_uri_for(old_p), sidecar_uri_for(new_p)) if is_parsed else (None, None)
    try:
        os.rename(old_p, new_p)                              # in-container, volume mounted
        if is_parsed:
            await db.execute(
                "UPDATE LIGHTRAG_DOC_FULL SET sidecar_location=$2 "
                "WHERE sidecar_location=$1 AND workspace=$3",
                {"old": old_uri, "new": new_uri, "ws": ws})
    except Exception as e:
        logger.warning(f"rename-edition: parsed-artifact {old_p} -> {new_p} failed: {e}")
```

- Compute URIs **before** `os.rename` (old_p still exists → correct resolve).
- Best-effort, idempotent; wrapped so the step never aborts the DB rename that already succeeded.

## Verify

- Offline: `.venv/bin/python -m pytest tests/maintenance tests/sidecar tests/api tests/guidelines -q` green.
- Live: deploy → `POST /graph:rename-edition?apply=true` → poll status done → rerun
  `scratch/probe_nopage_chunk.py` (Akutní průjem chunk-010 now has a page) + `ls __parsed__` shows 0 `_unknown`.
