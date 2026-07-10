"""Query-time provenance: a cited chunk -> {page, section, bbox}.

A MinerU-parsed chunk carries ``chunk["sidecar"] = {"id": blockid, "refs":
[{"id": blockid}, ...]}`` (``lightrag/sidecar/backfill.py``). Each blockid is a
``type:"content"`` row in ``<doc>.parsed/blocks.jsonl``
(``lightrag/sidecar/writer.py``) with ``heading`` / ``parent_headings`` (the
section path) and ``positions`` (for PDF: ``{type:"bbox", anchor:<page>,
range:[x0,y0,x1,y1]}``, ``lightrag/sidecar/ir.py``). This joins the two so the FE
can show the exact page region a passage came from and open the PDF there.

Pure (no I/O in :func:`resolve_provenance` — the caller loads the block rows).
The bbox is **display-only**: re-derive it live from the current sidecar, never
persist it downstream (pixel coords shift on re-parse; ``page``/``section`` are
the stable keys).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SECTION_SEP = " › "


def _block_ids(sidecar: Any) -> list[str]:
    """Ordered, deduped blockids referenced by a chunk's ``sidecar`` field.

    v1 resolves **content-block** provenance only. A multimodal chunk's sidecar is
    ``type:"table"``/``"drawing"`` and points at ``tables.json``/``drawings.json``,
    not ``blocks.jsonl`` — reject it explicitly rather than let its id fail to
    resolve as a silent ``None``.
    """
    if not isinstance(sidecar, dict):
        return []
    if sidecar.get("type") not in (None, "block"):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for ref in sidecar.get("refs") or []:
        if isinstance(ref, dict) and ref.get("id"):
            bid = str(ref["id"])
            if bid not in seen:
                seen.add(bid)
                ids.append(bid)
    if not ids and sidecar.get("id"):
        ids = [str(sidecar["id"])]
    return ids


def _bbox_position(block: dict) -> dict | None:
    for p in block.get("positions") or []:
        if isinstance(p, dict) and p.get("type") == "bbox":
            return p
    return None


def _section(block: dict) -> str:
    parts = [str(h).strip() for h in (block.get("parent_headings") or []) if str(h).strip()]
    heading = str(block.get("heading") or "").strip()
    if heading:
        parts.append(heading)
    return _SECTION_SEP.join(parts)


def resolve_provenance(sidecar: Any, blocks_by_id: dict[str, dict]) -> dict | None:
    """Resolve a chunk's ``sidecar`` against ``blockid -> block row`` to
    ``{page, pages, section, bbox, block_ids}``.

    Uses the FIRST covered block (the chunk's start) for ``page``/``section``/
    ``bbox``; ``pages`` lists every page the chunk's blocks touch (a chunk can
    span a page break). Returns ``None`` when the chunk has no resolvable
    provenance (no sidecar, or none of its blockids are present) — the caller
    then omits the fields and degrades to today's citation.
    """
    ids = _block_ids(sidecar)
    covered = [blocks_by_id[bid] for bid in ids if bid in blocks_by_id]
    if not covered:
        return None

    primary = covered[0]
    pos = _bbox_position(primary)
    page = pos.get("anchor") if pos else None
    rng = pos.get("range") if pos else None
    bbox = list(rng) if isinstance(rng, list) else None

    pages: list = []
    for b in covered:
        bp = _bbox_position(b)
        if bp is not None and bp.get("anchor") is not None and bp["anchor"] not in pages:
            pages.append(bp["anchor"])

    section = _section(primary)
    return {
        "page": page,
        "pages": pages,
        "section": section or None,
        "bbox": bbox,
        "block_ids": ids,
    }


def load_blocks_by_id(blocks_jsonl_path: str | Path) -> dict[str, dict]:
    """Load ``blockid -> content row`` from a ``blocks.jsonl`` sidecar file.

    Skips the meta header and any non-``content`` / malformed rows. Impure helper
    for the endpoint layer; keep :func:`resolve_provenance` I/O-free for testing.
    """
    out: dict[str, dict] = {}
    with Path(blocks_jsonl_path).open("r", encoding="utf-8") as fh:
        for raw in fh:  # stream (matches backfill._load_content_blocks)
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("type") == "content" and row.get("blockid"):
                out[str(row["blockid"])] = row
    return out
