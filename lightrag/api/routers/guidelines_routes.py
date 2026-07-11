"""
Focused guideline retrieve endpoint (spec 002).

`POST /v1/guidelines:retrieve` returns the top_k cited passage spans for a
clinical query — retrieval only, no LLM answer — so a caller (the agent, the FE)
gets a handful of on-topic spans instead of a whole doporučený-postup dump.

Thin router over the existing `rag.aquery_data` pure-retrieval path: no edits to
`operate.py` / `base.py` / `query_routes.py` (clean upstream rebase; no conflict
with the query-contextualization PR). v1 accepts `facet` / `concept_ref` as a
stable forward contract but does not filter by them yet (chunks are untagged);
`concept_ref` is echoed on the response as the dual-source key against mkn10.
"""

import asyncio
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from lightrag.base import QueryParam
from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.sidecar.passage_links import (
    build_passage_links,
    load_blocks_for_doc,
    passage_provenance,
)
from lightrag.sidecar.provenance import resolve_provenance
from lightrag.utils import logger

# Where the promotion pass writes the immutable bundle (data volume so it survives a redeploy).
_BUNDLE_DIR = os.getenv("PROMOTION_BUNDLE_DIR", "/app/data/promotion/bundle")

# Corpus filenames encode the edition as `Work_YEAR.md` (e.g. `Arteriální hypertenze_2024.md`).
# The year is bounded by a separator (`.`/`_`/path `/`) or end-of-string so a longer digit run
# (`_20241`, `_20240101`) is not mistaken for a 4-digit edition, and path-form names resolve too.
_EDITION_RE = re.compile(r"_(\d{4})(?=[._/]|$)")


def _edition_from_filename(file_path: str) -> str:
    """Extract the 4-digit edition year from a corpus filename, or 'unknown'."""
    if not file_path:
        return "unknown"
    match = _EDITION_RE.search(file_path)
    return match.group(1) if match else "unknown"


class ConceptRef(BaseModel):
    mkn10_code: Optional[str] = None
    cui: Optional[str] = None


class GuidelineRetrieveRequest(BaseModel):
    query: str = Field(min_length=3, description="Clinical query to retrieve passages for.")
    facet: Optional[str] = Field(
        default=None,
        description="Section focus (diagnosis/treatment/dosing/…). Accepted; not applied in v1 (chunks untagged).",
    )
    concept_ref: Optional[ConceptRef] = Field(
        default=None,
        description="Diagnosis/drug key. Echoed for dual-source against mkn10; not applied as a filter in v1.",
    )
    top_k: int = Field(default=5, ge=1, le=50, description="Max passages to return (hard cap).")
    locale: str = Field(default="cs", description="Query locale.")
    mode: Literal["mix", "naive", "local", "global", "hybrid"] = Field(
        default="mix", description="Underlying retrieval mode ('naive' is the fastest pure-chunk path)."
    )


class RetrievedPassage(BaseModel):
    text: str
    citation: str  # "<file_path>#chunk=<chunk_id>@<edition>"
    score: Optional[float] = None
    facet: Optional[str] = None  # v2
    concept_ref: Optional[ConceptRef] = None  # v2 (per-chunk)
    # section-crop provenance (spec 004 R2): the source PDF location of this passage.
    # Resolved live from the current sidecar; `page`/`section` are the stable keys, `bbox` is
    # display-only. Null when the chunk carries no MinerU sidecar (degrades to today's citation).
    page: Optional[str] = None
    pages: Optional[List[str]] = None  # every page the passage's blocks touch (can span a break)
    section: Optional[str] = None  # heading path "parent › … › heading"
    bbox: Optional[List[float]] = None  # [x0,y0,x1,y1] of the primary block (display-only)
    crop_url: Optional[str] = None  # R3 (gated on the PDF upload) — highlighted page-region PNG
    pdf_url: Optional[str] = None  # R4 (gated) — the full source PDF


# The section-crop provenance resolver moved to ``lightrag.sidecar.passage_links`` so the chat path
# (``/query/stream`` → ``ReferenceItem.chunks``) reuses the same resolver + crop/pdf URL shape as this
# ``:retrieve`` path. These module-level aliases keep the private names the section-crop endpoint and the
# existing spec-004 tests reference (tests monkeypatch ``_load_blocks_for_doc``; the retrieve endpoint
# passes it explicitly so the patch takes effect).
_load_blocks_for_doc = load_blocks_for_doc
_passage_provenance = passage_provenance


def _bbox_to_px(bbox, w: int, h: int, max_coord: float = 1000.0):
    """MinerU bbox (normalized 0..``max_coord``, LEFTTOP origin) → pixel box on a ``w``×``h`` image.

    MinerU's PDF coordinate convention is ``{"origin":"LEFTTOP","max":1000}`` — the range is a fraction
    of the page in [0, max] with a top-left origin, so it maps to image pixels with no y-flip.
    """
    x0, y0, x1, y1 = (float(v) for v in bbox)
    return (x0 / max_coord * w, y0 / max_coord * h, x1 / max_coord * w, y1 / max_coord * h)


def _render_section_crop(pdf_path, page_number, bbox, *, scale: float = 2.0) -> bytes:
    """Rasterize page ``page_number`` (the 1-based MinerU anchor) of the PDF, highlight the block
    ``bbox``, return PNG bytes. Raises on a missing/out-of-range page. Imports pypdfium2/PIL lazily
    (only when a crop is actually rendered)."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = bitmap = None
    try:
        page_index = int(page_number) - 1  # anchor is a 1-based page NUMBER
        if page_index < 0 or page_index >= len(pdf):
            raise ValueError(f"page {page_number} out of range (pdf has {len(pdf)} pages)")
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil().convert("RGBA")
        if bbox and len(bbox) == 4:
            px = _bbox_to_px(bbox, pil.width, pil.height)
            overlay = Image.new("RGBA", pil.size, (0, 0, 0, 0))
            ImageDraw.Draw(overlay).rectangle(
                px, fill=(255, 235, 0, 64), outline=(220, 0, 0, 255), width=3
            )
            pil = Image.alpha_composite(pil, overlay)
        buf = io.BytesIO()
        pil.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    finally:
        # release native pdfium handles explicitly (pdf.close() doesn't close open child pages)
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        pdf.close()


class GuidelineRetrieveResponse(BaseModel):
    passages: List[RetrievedPassage]
    concept_ref: Optional[ConceptRef] = None  # echo of the request — dual-source key
    filtered: bool = False  # v1 ALWAYS false: no concept/facet filter applied
    disclaimer: str = "Čerpáno výhradně z SVL doporučených postupů."


def create_guidelines_routes(rag, api_key: Optional[str] = None):
    # Fresh router per call (see create_query_routes — avoids duplicate-route
    # warnings when the factory runs more than once in a process, e.g. tests).
    router = APIRouter(tags=["guidelines"])

    combined_auth = get_combined_auth_dependency(api_key)

    @router.post(
        "/v1/guidelines:retrieve",
        response_model=GuidelineRetrieveResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def guidelines_retrieve(request: GuidelineRetrieveRequest):
        """Return up to top_k cited passage spans for the query (retrieval only, no LLM)."""
        try:
            param = QueryParam(
                mode=request.mode,
                top_k=request.top_k,
                chunk_top_k=request.top_k,
                only_need_context=True,
            )
            result = await rag.aquery_data(request.query, param)
            chunks = (result or {}).get("data", {}).get("chunks", []) or []

            passages: List[RetrievedPassage] = []
            blocks_cache: dict = {}  # per-request: a doc's blocks.jsonl loads once across its chunks
            for chunk in chunks[: request.top_k]:
                content = chunk.get("content")
                if not content:
                    continue
                file_path = chunk.get("file_path", "unknown_source")
                chunk_id = chunk.get("chunk_id", "")
                edition = _edition_from_filename(file_path)
                # Pass the loader explicitly so a test monkeypatching this module's
                # ``_load_blocks_for_doc`` still drives resolution (the alias points at passage_links).
                prov = (
                    await passage_provenance(
                        rag, chunk_id, file_path, blocks_cache, load_blocks=_load_blocks_for_doc
                    )
                    or {}
                )
                passages.append(
                    RetrievedPassage(
                        text=content,
                        citation=f"{file_path}#chunk={chunk_id}@{edition}",
                        score=chunk.get("score"),
                        **build_passage_links(chunk_id, file_path, prov),
                    )
                )

            return GuidelineRetrieveResponse(
                passages=passages,
                concept_ref=request.concept_ref,
                filtered=False,
            )
        except Exception as e:
            logger.error(f"Error in guidelines:retrieve: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def _run_promotion(out_dir: Path):
        """Harvest the live store → pure G1–G5 promote → write the immutable bundle.

        Runs in the background so the emit is not bound by the HTTP/edge request timeout
        (harvest over a large store + per-anchor locate can exceed ~300 s). Writes a
        status.json (running/done/failed) next to the bundle for polling.
        """
        import asyncio
        import json as _json

        from lightrag.promotion import jsonl
        from lightrag.promotion.bundle import build_manifest, write_bundle
        from lightrag.promotion.harvest import harvest
        from lightrag.promotion.promote import promote

        out_dir.mkdir(parents=True, exist_ok=True)
        status_path = out_dir / "status.json"
        status_path.write_text(_json.dumps({"state": "running"}), encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                snap_dir = Path(tmp) / "snapshot"
                await harvest(rag, snap_dir)

                # promote()/build_manifest() iterate the whole graph and run the locate
                # regex per anchor — CPU-bound. Run off the event loop.
                def _emit():
                    snapshot = {
                        name: jsonl.read_jsonl(snap_dir / f"{name}.jsonl")
                        for name in ("docs", "chunks", "nodes", "edges")
                    }
                    bundle = promote(snapshot)
                    manifest = build_manifest(bundle, snapshot)
                    write_bundle(bundle, manifest, out_dir)
                    return manifest

                manifest = await asyncio.get_running_loop().run_in_executor(None, _emit)
            status_path.write_text(
                _json.dumps(
                    {"state": "done", "content_hash": manifest.content_hash, "counts": manifest.counts}
                ),
                encoding="utf-8",
            )
            logger.info(
                f"guidelines:promote done — hash={manifest.content_hash[:12]} counts={manifest.counts}"
            )
        except Exception as e:  # noqa: BLE001
            status_path.write_text(
                _json.dumps({"state": "failed", "error": str(e)}), encoding="utf-8"
            )
            logger.error(f"guidelines:promote background run failed: {str(e)}", exc_info=True)

    @router.post("/v1/guidelines:promote", dependencies=[Depends(combined_auth)])
    async def guidelines_promote(background_tasks: BackgroundTasks):
        """Kick off the deterministic promotion pass in the background (spec 001).

        harvest (impure: reads the deployed PG+Neo4j store) → pure G1–G5 promote →
        immutable bundle on the data volume. Returns immediately; poll
        GET /v1/guidelines/promote/status, then GET /v1/guidelines/bundle to download.
        """
        background_tasks.add_task(_run_promotion, Path(_BUNDLE_DIR))
        return {
            "status": "started",
            "status_url": "/v1/guidelines/promote/status",
            "bundle_url": "/v1/guidelines/bundle",
        }

    @router.get("/v1/guidelines/promote/status", dependencies=[Depends(combined_auth)])
    async def guidelines_promote_status():
        """Report the state of the latest background promotion run (none/running/done/failed)."""
        import json as _json

        p = Path(_BUNDLE_DIR) / "status.json"
        if not p.exists():
            return {"state": "none"}
        try:
            return _json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"state": "unknown"}

    @router.get("/v1/guidelines/bundle", dependencies=[Depends(combined_auth)])
    async def guidelines_bundle_download():
        """Download the latest promotion bundle (nodes/edges/quarantine.jsonl + manifest.json) as a zip."""
        out_dir = Path(_BUNDLE_DIR)
        if not (out_dir / "manifest.json").exists():
            raise HTTPException(status_code=404, detail="No bundle yet; POST /v1/guidelines:promote first.")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("nodes.jsonl", "edges.jsonl", "quarantine.jsonl", "manifest.json"):
                p = out_dir / name
                if p.exists():
                    zf.write(p, arcname=name)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=guidelines-bundle.zip"},
        )

    @router.get("/v1/guidelines/section-crop", dependencies=[Depends(combined_auth)])
    async def guidelines_section_crop(
        chunk_id: str = Query(..., description="Cited chunk id (from the retrieve citation)."),
    ):
        """R3: the source PDF page region a cited passage came from — page N rasterized with the cited
        block highlighted, as a PNG. Rendered live from the current sidecar (bbox never persisted)."""
        from lightrag.utils_pipeline import configured_input_dir

        chunk = await rag.text_chunks.get_by_id(chunk_id)
        sidecar = (chunk or {}).get("sidecar")
        if not sidecar:
            raise HTTPException(status_code=404, detail="chunk has no provenance sidecar")
        file_path = chunk.get("file_path", "")
        blocks = _load_blocks_for_doc(file_path)
        prov = resolve_provenance(sidecar, blocks) if blocks else None
        try:
            page_num = int(prov["page"]) if prov and prov.get("page") is not None else None
        except (TypeError, ValueError):
            page_num = None
        if page_num is None:
            raise HTTPException(status_code=404, detail="chunk has no resolvable page/bbox")
        pdf_path = Path(configured_input_dir()) / Path(file_path).name
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="source PDF not available")
        try:
            # CPU-bound rasterization off the event loop
            png = await asyncio.to_thread(
                _render_section_crop, pdf_path, page_num, prov.get("bbox")
            )
        except Exception as e:
            logger.warning("section-crop render failed for %s: %s", chunk_id, e)
            raise HTTPException(status_code=500, detail="crop render failed")
        return Response(content=png, media_type="image/png")

    @router.get("/v1/guidelines/pdf", dependencies=[Depends(combined_auth)])
    async def guidelines_pdf(
        doc: str = Query(..., description="Source document file_path / name."),
    ):
        """R4: serve the full source PDF (so the crop click-through opens the document)."""
        from lightrag.utils_pipeline import configured_input_dir

        name = Path(doc).name  # basename only — no path traversal
        pdf_path = Path(configured_input_dir()) / name
        if not name.lower().endswith(".pdf") or not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF not found")
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=name)

    return router
