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


_MM_TYPES = ("table", "drawing", "equation")


def _raw_ids(sidecar: dict) -> list[str]:
    """Ordered, deduped ids from a sidecar's ``refs[].id`` (else its own ``id``)."""
    ids: list[str] = []
    seen: set[str] = set()
    for ref in sidecar.get("refs") or []:
        if isinstance(ref, dict) and ref.get("id"):
            rid = str(ref["id"])
            if rid not in seen:
                seen.add(rid)
                ids.append(rid)
    if not ids and sidecar.get("id"):
        ids = [str(sidecar["id"])]
    return ids


def _block_ids(sidecar: Any, mm_id_to_blockid: dict[str, str] | None = None) -> list[str]:
    """Ordered, deduped blockids referenced by a chunk's ``sidecar`` field.

    A content-block sidecar's ids **are** blockids. A multimodal chunk's sidecar is
    ``type:"table"``/``"drawing"``/``"equation"`` and its id is a ``tb-``/``im-``/``eq-``
    id that points at ``tables.json``/``drawings.json``/``equations.json``, not
    ``blocks.jsonl`` — translate it to the entry's ``blockid`` (a positioned content
    block) via ``mm_id_to_blockid`` (spec 019). Without a map a multimodal sidecar is
    unresolvable → ``[]`` → the caller degrades to today's title-only citation.
    """
    if not isinstance(sidecar, dict):
        return []
    stype = sidecar.get("type")
    raw = _raw_ids(sidecar)
    if stype in (None, "block"):
        return raw
    if stype in _MM_TYPES and mm_id_to_blockid:
        ids: list[str] = []
        seen: set[str] = set()
        for rid in raw:
            bid = mm_id_to_blockid.get(rid)
            if bid:
                bid = str(bid)
                if bid not in seen:
                    seen.add(bid)
                    ids.append(bid)
        return ids
    return []


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


def resolve_provenance(
    sidecar: Any,
    blocks_by_id: dict[str, dict],
    mm_id_to_blockid: dict[str, str] | None = None,
) -> dict | None:
    """Resolve a chunk's ``sidecar`` against ``blockid -> block row`` to
    ``{page, pages, section, bbox, block_ids}``.

    Uses the FIRST covered block (the chunk's start) for ``page``/``section``;
    ``bbox`` is the union of the covered blocks on that primary page (frames the
    whole chunk, not just its first block); ``pages`` lists every page the chunk's
    blocks touch (a chunk can span a page break). Returns ``None`` when the chunk
    has no resolvable
    provenance (no sidecar, or none of its blockids are present) — the caller
    then omits the fields and degrades to today's citation.

    ``mm_id_to_blockid`` (spec 019) lets a multimodal chunk (table/drawing/equation)
    resolve too: its sidecar id is mapped to the containing content block's blockid.
    Absent/empty ⇒ byte-for-byte identical to the content-only behaviour.
    """
    ids = _block_ids(sidecar, mm_id_to_blockid)
    covered = [blocks_by_id[bid] for bid in ids if bid in blocks_by_id]
    if not covered:
        return None

    primary = covered[0]
    pos = _bbox_position(primary)
    page = pos.get("anchor") if pos else None
    rng = pos.get("range") if pos else None
    bbox = list(rng) if isinstance(rng, list) and len(rng) == 4 else None

    # Union the boxes of every covered block on the primary page, so the highlight frames the whole
    # chunk, not just its first block. Confined to the primary page — a bbox can't span a page break;
    # skip when the primary page is unknown (else blocks of unknown page would merge in).
    if bbox is not None and page is not None:
        for b in covered[1:]:
            bp = _bbox_position(b)
            if bp is None or str(bp.get("anchor")) != str(page):
                continue
            r = bp.get("range")
            if isinstance(r, list) and len(r) == 4:
                bbox = [
                    min(bbox[0], r[0]),
                    min(bbox[1], r[1]),
                    max(bbox[2], r[2]),
                    max(bbox[3], r[3]),
                ]

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


def load_mm_id_to_blockid(json_paths: Any) -> dict[str, str]:
    """Load ``mm_id -> blockid`` from a doc's multimodal sidecars (spec 019).

    ``json_paths`` = the doc's ``*.tables.json`` / ``*.drawings.json`` /
    ``*.equations.json`` (root keys ``tables``/``drawings``/``equations``; each
    entry keyed by its ``tb-``/``im-``/``eq-`` id carries a ``blockid`` pointing at a
    positioned content block in ``blocks.jsonl``). Best-effort: unreadable file /
    non-dict root / entry without ``blockid`` skipped. Impure helper for the endpoint
    layer; keep :func:`resolve_provenance` I/O-free for testing.
    """
    out: dict[str, str] = {}
    for path in json_paths or []:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for root in ("tables", "drawings", "equations"):
            items = payload.get(root)
            if not isinstance(items, dict):
                continue
            for mm_id, item in items.items():
                if isinstance(item, dict) and item.get("blockid"):
                    out[str(mm_id)] = str(item["blockid"])
    return out
