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

from lightrag.sidecar.provenance import load_blocks_by_id, resolve_provenance
from lightrag.utils import logger
from lightrag.utils_pipeline import parsed_artifact_dir_for


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


async def passage_provenance(rag, chunk_id, file_path, blocks_cache, *, load_blocks=None):
    """Resolve ``{page, pages, section, bbox}`` for a cited chunk, or ``None``.

    Fetches the chunk's ``sidecar`` from the store (the ``aquery_data`` projection drops it) and joins it
    against the doc's ``blocks.jsonl`` via the shipped resolver. ``blocks_cache`` is per-request so a doc's
    blocks load once across its chunks. ``load_blocks`` is injectable for tests; it defaults to the
    module-level loader looked up at call time (so it stays monkeypatch-able). All best-effort: error ⇒
    ``None``."""
    loader = load_blocks if load_blocks is not None else load_blocks_for_doc
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
    try:
        return resolve_provenance(sidecar, blocks)
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
