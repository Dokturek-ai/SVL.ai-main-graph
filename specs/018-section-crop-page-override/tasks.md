# Tasks 018 — `section-crop` `&page=N` override

- [ ] T1 — Add `page: Optional[int] = Query(None, …)` to `guidelines_section_crop` (guidelines_routes.py).
- [ ] T2 — Rename local `page_num` → `primary_page`; branch on `page`: absent ⇒ primary + bbox; present ⇒
  membership gate (int-coerced `prov["pages"]`, 404 if not a member) + `render_page = page`, bbox only when
  `page == primary_page`.
- [ ] T3 — Route tests `tests/guidelines/test_section_crop_page_override.py` (render stubbed, `rag` fake):
  - no `page` → renders primary, bbox passed.
  - `page = primary` → renders primary, bbox passed.
  - `page = secondary ∈ pages` → renders that page, bbox `None`.
  - `page ∉ pages` → 404.
  - existing 404s still hold (no sidecar / no resolvable page).
- [ ] T4 — Offline suite green; caveman-review; fix findings.
- [ ] T5 — PR to `staging`, merge (home repo, gates satisfied). Live-verify brief if not run.
