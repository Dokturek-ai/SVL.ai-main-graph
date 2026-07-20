"""Section-crop provenance links for a cited chunk (spec 004).

Single source of truth shared by the two endpoints that surface a passage's PDF
location:

* ``POST /v1/guidelines:retrieve`` → ``RetrievedPassage`` (guidelines_routes)
* the chat path ``POST /query/stream`` (and ``/query``) → ``ReferenceItem.chunks``
  (query_routes)

Keeping the resolver *and* the ``crop_url`` / ``pdf_url`` string shape here stops
the two endpoints from drifting — if the crop/pdf route changes, both follow.

All best-effort: a chunk whose sidecar/blocks can't resolve degrades to text-only
(``page``/``crop_url`` null) instead of erroring the query.
"""

import urllib.parse
from pathlib import Path
from typing import Optional

from lightrag.sidecar.provenance import (
    load_blocks_by_id,
    load_mm_id_to_blockid,
    resolve_provenance,
)
from lightrag.utils import logger
from lightrag.utils_pipeline import parsed_artifact_dir_for

_MM_SIDECAR_SUFFIXES = (".tables.json", ".drawings.json", ".equations.json")


def load_blocks_for_doc(file_path: str) -> Optional[dict]:
    """Locate + load ``<doc>.parsed/*.blocks.jsonl`` for a chunk's ``file_path``; ``None`` if absent.

    I/O helper — kept off :func:`resolve_provenance` (pure). Best-effort: any failure ⇒ ``None`` so the
    passage degrades to today's citation instead of erroring the query.
    """
    try:
        parsed = parsed_artifact_dir_for(file_path)
        if not parsed.exists():
            return None
        # Prefer the exact ``<stem>.blocks.jsonl`` (the writer's name) so a collision-suffixed sibling
        # dir can't have us resolve against a different doc's blocks; glob only as a fallback.
        exact = parsed / f"{Path(file_path).stem}.blocks.jsonl"
        target = exact if exact.exists() else next(iter(sorted(parsed.glob("*.blocks.jsonl"))), None)
        return load_blocks_by_id(str(target)) if target else None
    except Exception as e:
        logger.debug("section-crop: blocks load failed for %s: %s", file_path, e)
        return None


def load_mm_map_for_doc(file_path: str) -> dict:
    """Locate + load ``<doc>.parsed/*.{tables,drawings,equations}.json`` → ``{mm_id: blockid}`` (spec 019).

    Mirrors :func:`load_blocks_for_doc`: prefer the exact ``<stem>.<suffix>`` (the writer's name) so a
    collision-suffixed sibling dir can't resolve against a different doc, glob only as a fallback. Best-effort:
    any failure / no mm sidecars ⇒ ``{}`` (mm chunks then degrade to today's title-only citation)."""
    try:
        parsed = parsed_artifact_dir_for(file_path)
        if not parsed.exists():
            return {}
        stem = Path(file_path).stem
        paths: list = []
        for suffix in _MM_SIDECAR_SUFFIXES:
            exact = parsed / f"{stem}{suffix}"
            if exact.exists():
                paths.append(exact)
            else:
                paths.extend(sorted(parsed.glob(f"*{suffix}")))
        return load_mm_id_to_blockid(paths)
    except Exception as e:
        logger.debug("section-crop: mm-map load failed for %s: %s", file_path, e)
        return {}


async def passage_provenance(
    rag, chunk_id, file_path, blocks_cache, mm_cache=None, *, load_blocks=None, load_mm_map=None
):
    """Resolve ``{page, pages, section, bbox}`` for a cited chunk, or ``None``.

    Fetches the chunk's ``sidecar`` from the store (the ``aquery_data`` projection drops it) and joins it
    against the doc's ``blocks.jsonl`` via the shipped resolver. ``blocks_cache`` (and ``mm_cache``, spec 019 —
    the ``{mm_id: blockid}`` map for multimodal chunks) are per-request so a doc's sidecars load once across its
    chunks. ``load_blocks`` / ``load_mm_map`` are injectable for tests; they default to the module-level loaders
    looked up at call time (so they stay monkeypatch-able). All best-effort: error ⇒ ``None``."""
    loader = load_blocks if load_blocks is not None else load_blocks_for_doc
    mm_loader = load_mm_map if load_mm_map is not None else load_mm_map_for_doc
    try:
        rec = await rag.text_chunks.get_by_id(chunk_id)
    except Exception as e:
        logger.debug("section-crop: text_chunks.get_by_id(%s) failed: %s", chunk_id, e)
        return None
    sidecar = (rec or {}).get("sidecar")
    if not sidecar:
        return None
    if not file_path:
        return None  # no doc to resolve blocks against; skip the pointless loader("") + cache slot
    if file_path not in blocks_cache:
        blocks_cache[file_path] = loader(file_path)
    blocks = blocks_cache[file_path]
    if not blocks:
        return None
    if mm_cache is None:
        mm_cache = {}  # correctness without a per-request cache (reloads per chunk); callers pass one to cache
    if file_path not in mm_cache:
        mm_cache[file_path] = mm_loader(file_path)
    try:
        return resolve_provenance(sidecar, blocks, mm_cache[file_path])
    except Exception as e:
        logger.debug("section-crop: resolve_provenance failed for %s: %s", chunk_id, e)
        return None


def crop_url_for(chunk_id: str, prov: Optional[dict]) -> Optional[str]:
    """The R3 highlighted-page-region PNG endpoint for a chunk, or ``None`` when no page resolved."""
    has_page = bool(prov) and prov.get("page") is not None
    if chunk_id and has_page:
        return "/v1/guidelines/section-crop?" + urllib.parse.urlencode({"chunk_id": chunk_id})
    return None


def pdf_url_for(file_path: str) -> Optional[str]:
    """The R4 full-PDF serve endpoint for a chunk's source doc, or ``None`` when the file is unknown."""
    pdf_name = Path(file_path).name if file_path else ""
    if pdf_name and file_path != "unknown_source":
        return "/v1/guidelines/pdf?" + urllib.parse.urlencode({"doc": pdf_name})
    return None


def build_passage_links(chunk_id: str, file_path: str, prov: Optional[dict]) -> dict:
    """``{page, pages, section, bbox, crop_url, pdf_url}`` for a cited chunk.

    The exact projection ``:retrieve`` serves, so the chat references carry identical provenance.
    ``prov`` is the resolved :func:`passage_provenance` dict (or ``{}``/``None`` when it didn't resolve).
    """
    prov = prov or {}
    return {
        "page": prov.get("page"),
        "pages": prov.get("pages"),
        "section": prov.get("section"),
        "bbox": prov.get("bbox"),
        "crop_url": crop_url_for(chunk_id, prov),
        "pdf_url": pdf_url_for(file_path),
    }
