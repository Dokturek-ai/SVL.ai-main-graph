# Plan 018 — `section-crop` `&page=N` override

## Touch surface

- `lightrag/api/routers/guidelines_routes.py` — `guidelines_section_crop` handler only. Add the `page` Query
  param + membership/bbox logic. `_render_section_crop` is **unchanged** (already takes `page_number` + nullable
  `bbox`).
- `tests/guidelines/test_section_crop_page_override.py` — new route tests (FastAPI `TestClient`, `rag`
  monkeypatched; render stubbed so no PyMuPDF/PDF needed).

Nothing else. No provenance/enrichment/prompt change.

## Handler change (guidelines_routes.py)

Current handler resolves `prov` then renders `prov["page"]` with `prov.get("bbox")`. New logic, after `page_num`
(rename → `primary_page`) is resolved and non-None:

```python
if page is None:
    render_page, bbox = primary_page, prov.get("bbox")
else:
    chunk_pages = []
    for p in prov.get("pages") or []:
        try:
            chunk_pages.append(int(p))
        except (TypeError, ValueError):
            pass
    if page not in chunk_pages:
        raise HTTPException(status_code=404, detail="requested page is not one of the chunk's pages")
    render_page = page
    bbox = prov.get("bbox") if page == primary_page else None
png = await asyncio.to_thread(_render_section_crop, pdf_path, render_page, bbox)
```

Param: `page: Optional[int] = Query(None, description="Optional page override; must be one of the chunk's pages. Absent → primary page + bbox highlight.")`.

Notes:
- `primary_page` is already `int(prov["page"])`, so `page == primary_page` is an int/int compare.
- Membership list coerces anchors to int defensively (anchors are ints today, but the resolver doesn't
  guarantee type) so `?page=13` matches `pages=[12,13]`.
- Keeps the existing 404s (no sidecar / no resolvable page / PDF missing) and the 500 render-fail wrap.

## Verify

1. Offline route tests (below) green — `.venv/bin/python -m pytest tests/guidelines/test_section_crop_page_override.py`.
2. Full offline suite green (staging = no CI gate).
3. caveman-review (cavecrew-reviewer) on the diff; fix real findings.
4. Live-verify on staging after merge+deploy against a real multi-page chunk (else → brief).
