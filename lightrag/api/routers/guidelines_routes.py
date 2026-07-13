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
import json
import os
import re
import tempfile
import time
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
from lightrag.guidelines.retrieve_filter import (
    build_code_index,
    chunks_for_code,
    classify_facet,
    facet_matches,
)
from lightrag.guidelines.chunk_tags import (
    build_chunk_tags,
    load_code_index,
    write_chunk_tags,
)
from lightrag.utils import logger

# Where the promotion pass writes the immutable bundle (data volume so it survives a redeploy).
_BUNDLE_DIR = os.getenv("PROMOTION_BUNDLE_DIR", "/app/data/promotion/bundle")
# Where the chunk-tag backfill writes chunk-tags.jsonl (spec 015) — retrieve reads it instead of the graph.
_CHUNK_TAGS_DIR = os.getenv("CHUNK_TAGS_DIR", "/app/data/chunk-tags")

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
    ``bbox``, return PNG bytes. Raises on a missing/out-of-range page. Imports PyMuPDF/PIL lazily.

    Uses PyMuPDF (fitz), NOT pypdfium2: fitz bundles its own fonts, so it renders correctly in the minimal
    deployment container where pypdfium2/PDFium falls back to (absent) system fonts and garbles Czech
    diacritics (č/ř/ě → blank, á→Æ, é→Ø)."""
    import fitz
    from PIL import Image, ImageDraw

    doc = fitz.open(str(pdf_path))
    try:
        page_index = int(page_number) - 1  # anchor is a 1-based page NUMBER
        if page_index < 0 or page_index >= len(doc):
            raise ValueError(f"page {page_number} out of range (pdf has {len(doc)} pages)")
        pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGBA")
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
        doc.close()


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

    # --- concept_ref → chunks index (spec 014/015): TTL-cached code→chunks map. Preferred source is the
    # persisted chunk-tags.jsonl artifact (spec 015 — a file read, no graph contention); falls back to
    # building from the live graph when the artifact is absent (backfill not yet run). ---
    _code_index: dict = {"at": 0.0, "map": {}}
    _index_lock = asyncio.Lock()
    _INDEX_TTL = float(os.getenv("RETRIEVE_INDEX_TTL", "600"))

    async def _build_index_from_graph() -> dict:
        kg = await rag.get_knowledge_graph(node_label="*", max_depth=1, max_nodes=1_000_000)
        entities = []
        for n in getattr(kg, "nodes", []) or []:
            p = getattr(n, "properties", None) or {}
            raw = p.get("concept_ref")
            if not raw:
                continue
            try:
                refs = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:  # noqa: BLE001
                continue
            entities.append((refs, p.get("source_id")))
        return build_code_index(entities)

    async def _get_code_index() -> dict:
        now = time.monotonic()
        if _code_index["map"] and now - _code_index["at"] < _INDEX_TTL:
            return _code_index["map"]
        async with _index_lock:
            now = time.monotonic()
            if _code_index["map"] and now - _code_index["at"] < _INDEX_TTL:
                return _code_index["map"]
            # spec 015: prefer the persisted artifact (no per-request graph read / mutation contention)
            if (Path(_CHUNK_TAGS_DIR) / "chunk-tags.jsonl").exists():
                try:
                    _code_index["map"] = load_code_index(_CHUNK_TAGS_DIR)
                except Exception as e:  # noqa: BLE001 — unreadable artifact ⇒ fall back to the graph
                    logger.warning(f"retrieve: chunk-tags artifact unreadable, falling back to graph: {e}")
                    _code_index["map"] = await _build_index_from_graph()
            else:
                _code_index["map"] = await _build_index_from_graph()
            _code_index["at"] = time.monotonic()
            return _code_index["map"]

    @router.post(
        "/v1/guidelines:retrieve",
        response_model=GuidelineRetrieveResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def guidelines_retrieve(request: GuidelineRetrieveRequest):
        """Return up to top_k cited passage spans for the query (retrieval only, no LLM).

        v2 (spec 014): ``concept_ref.mkn10_code`` scopes to the dg's chunks and ``facet`` focuses the
        section; both fall back to plain retrieval when unresolvable/empty (never worse than v1).
        """
        try:
            code = request.concept_ref.mkn10_code if request.concept_ref else None
            allow: Optional[set] = None
            code_active = False  # the concept_ref chunk filter is applied only when it resolves to ≥1 chunk
            if code:
                try:
                    hit = chunks_for_code(await _get_code_index(), code)
                    if hit:
                        allow, code_active = hit, True
                    else:
                        # code requested but no in-scope chunks (unknown code or ungrounded) → skip the
                        # code filter (resilience); facet may still apply.
                        logger.info(f"retrieve: concept_ref {code!r} resolved to 0 chunks; code filter skipped")
                except Exception as e:  # noqa: BLE001 — index unavailable ⇒ plain retrieval, no error
                    logger.warning(f"retrieve: concept_ref index unavailable, plain retrieval: {e}")

            facet_active = bool(request.facet)
            want_filter = code_active or facet_active
            # A code filter narrows a query-ranked pool; widen it so enough in-scope chunks survive the
            # post-filter. NOTE: a code with more in-scope chunks than the pool can still under-return if
            # the query ranks out-of-scope chunks above them (an id-level vector filter would be exact but
            # needs an engine change — out of scope). Tune via the multiplier/floor.
            pool = max(request.top_k * 8, 80) if want_filter else request.top_k
            param = QueryParam(
                mode=request.mode, top_k=pool, chunk_top_k=pool, only_need_context=True
            )
            result = await rag.aquery_data(request.query, param)
            chunks = (result or {}).get("data", {}).get("chunks", []) or []

            async def _build(apply_filter: bool) -> List[RetrievedPassage]:
                out: List[RetrievedPassage] = []
                blocks_cache: dict = {}  # per-build: a doc's blocks.jsonl loads once across its chunks
                for chunk in chunks:
                    content = chunk.get("content")
                    if not content:
                        continue
                    chunk_id = chunk.get("chunk_id", "")
                    if apply_filter and code_active and chunk_id not in allow:
                        continue
                    file_path = chunk.get("file_path", "unknown_source")
                    prov = (
                        await passage_provenance(
                            rag, chunk_id, file_path, blocks_cache, load_blocks=_load_blocks_for_doc
                        )
                        or {}
                    )
                    facet = classify_facet(prov.get("section"))
                    if apply_filter and facet_active and not facet_matches(facet, request.facet):
                        continue
                    out.append(
                        RetrievedPassage(
                            text=content,
                            citation=f"{file_path}#chunk={chunk_id}@{_edition_from_filename(file_path)}",
                            score=chunk.get("score"),
                            facet=facet,
                            # stamp the code ref only when the chunk actually passed the code gate
                            concept_ref=request.concept_ref if (apply_filter and code_active) else None,
                            **build_passage_links(chunk_id, file_path, prov),
                        )
                    )
                    if len(out) >= request.top_k:
                        break
                return out

            passages = await _build(apply_filter=want_filter)
            filtered = want_filter and bool(passages)  # honest: a filter dimension was active AND non-empty
            if want_filter and not passages:
                # focus emptied the result → graceful fallback to plain retrieval (no regression)
                passages = await _build(apply_filter=False)
                filtered = False

            return GuidelineRetrieveResponse(
                passages=passages,
                concept_ref=request.concept_ref,
                filtered=filtered,
            )
        except Exception as e:
            logger.error(f"Error in guidelines:retrieve: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # --- chunk-tag backfill (spec 015): propagate the grounded entity concept_ref onto chunks and emit
    # chunk-tags.jsonl (the durable code→chunk join layer retrieve + the A-harvest read). ---
    def _tag_status_path() -> Path:  # resolve _CHUNK_TAGS_DIR at call time (testable, env-override-safe)
        return Path(_CHUNK_TAGS_DIR) / "status.json"

    async def _chunk_tag_plan() -> dict:
        """Pull the (quiet) graph → propagate entity concept_ref onto chunks (pure build_chunk_tags)."""
        kg = await rag.get_knowledge_graph(node_label="*", max_depth=1, max_nodes=1_000_000)
        entities = []
        for n in getattr(kg, "nodes", []) or []:
            p = getattr(n, "properties", None) or {}
            raw = p.get("concept_ref")
            if not raw:
                continue
            try:
                refs = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:  # noqa: BLE001
                continue
            entities.append((refs, p.get("source_id")))
        return build_chunk_tags(entities)

    @router.post("/v1/guidelines:tag-chunks", dependencies=[Depends(combined_auth)])
    async def guidelines_tag_chunks(background_tasks: BackgroundTasks, apply: bool = Query(False)):
        """Backfill chunk concept_ref tags (spec 015). ``apply=false`` (default) = dry-run counts;
        ``apply=true`` writes ``chunk-tags.jsonl`` in the background. Run on a QUIET graph."""
        try:
            tags = await _chunk_tag_plan()
            tagged = {c: t for c, t in tags.items() if t.get("concept_ref")}
            summary = {
                "chunks_tagged": len(tagged),
                "total_chunks_seen": len(tags),
                "ref_total": sum(len(t["concept_ref"]) for t in tagged.values()),
            }
            if not apply:
                return {"dry_run": True, **summary}

            def _run():
                sp = _tag_status_path()
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(json.dumps({"state": "running"}), encoding="utf-8")
                try:
                    manifest = write_chunk_tags(tags, _CHUNK_TAGS_DIR)
                    _code_index["at"] = 0.0  # invalidate the cached retrieve index → next call reloads the artifact
                    sp.write_text(json.dumps({"state": "done", **manifest}), encoding="utf-8")
                    logger.info(f"guidelines:tag-chunks done — {manifest}")
                except Exception as e:  # noqa: BLE001
                    sp.write_text(json.dumps({"state": "failed", "error": str(e)}), encoding="utf-8")
                    logger.error(f"guidelines:tag-chunks failed: {e}", exc_info=True)

            background_tasks.add_task(_run)
            return {"status": "started", "status_url": "/v1/guidelines/tag-chunks/status", **summary}
        except Exception as e:  # noqa: BLE001
            logger.error(f"guidelines:tag-chunks error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/v1/guidelines/tag-chunks/status", dependencies=[Depends(combined_auth)])
    async def guidelines_tag_chunks_status():
        """State of the latest chunk-tag backfill (none/running/done/failed)."""
        sp = _tag_status_path()
        if not sp.exists():
            return {"state": "none"}
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"state": "unknown"}

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

    # PUBLIC (no combined_auth): the FE embeds these as a plain <img src>/<a href>, which cannot attach
    # the X-API-Key header, so an auth-gated endpoint 403s in the browser. The content is public SVL
    # guideline material (a rendered page crop / the source PDF), path-traversal-safe (basename only).
    @router.get("/v1/guidelines/section-crop")
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

    @router.get("/v1/guidelines/pdf")  # PUBLIC (see section-crop above): browser <a href> can't send the key
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
