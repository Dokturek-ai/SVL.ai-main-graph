r"""Durable edition-year resolution at ingest (spec 016).

`edition.py` derives the edition purely from the filename and is deliberately content-blind. This module
is its ingest-side complement: when a document arrives WITHOUT a year in its filename, resolve the year
from the PDF so the stored `file_path` carries it and `_unknown` is never emitted when a year is
recoverable. Priority, most-trusted first:

1. **filename year** — human-assigned, trusted (handled by `parse_edition`; we only resolve when absent).
2. **title-page stated year** — the SVL "NOVELIZACE 20YY" declaration. Authoritative for the *content's*
   edition, and the reason this beats CreationDate: Virová hepatitida C is a 2023 novelizace whose PDF
   `CreationDate` is 2025 (a re-export postdating the content) — the title page says 2023, correctly.
3. **PDF CreationDate** — a good proxy when the title page states no year.
4. else None → keep `unknown` (a human names it).

A bare `20\d{2}` anywhere on the title page is intentionally NOT used: it grabs citation years (a doc citing
"… 2019 …" before its own edition) and mis-stamps. NOVELIZACE is the SVL title convention and an unambiguous
self-declaration; without it we fall to CreationDate.
"""

from __future__ import annotations

import re
from pathlib import Path

from lightrag.promotion.edition import parse_edition
from lightrag.utils import logger

_NOVELIZACE_RE = re.compile(r"NOVELIZACE\s+(20\d{2})", re.IGNORECASE)
_CREATIONDATE_RE = re.compile(r"D:(20\d{2})")


def resolve_edition_year(pdf_path: str | Path) -> tuple[str, str] | None:
    """Return ``(year, source)`` for a document's edition, or None if unresolvable.

    ``source`` ∈ {"filename", "title", "creationdate"} for logging/audit. Only PDFs are content-scanned;
    a non-PDF with no filename year returns None.
    """
    pdf_path = Path(pdf_path)
    _work, filename_year = parse_edition(pdf_path.stem)
    if filename_year:
        return filename_year, "filename"

    if pdf_path.suffix.lower() != ".pdf":
        return None

    try:
        import fitz  # lazy — pymupdf is a dep (guidelines_routes.py imports it the same way)

        with fitz.open(pdf_path) as doc:
            text = "\n".join(doc[i].get_text() for i in range(min(2, doc.page_count)))
            m = _NOVELIZACE_RE.search(text)
            if m:
                return m.group(1), "title"
            cdate = (doc.metadata or {}).get("creationDate", "") or ""
            m = _CREATIONDATE_RE.search(cdate)
            if m:
                return m.group(1), "creationdate"
    except Exception as e:  # noqa: BLE001 — a scan failure must never block ingest
        logger.warning(f"edition-resolve: could not scan {pdf_path.name}: {e}")
        return None
    return None
