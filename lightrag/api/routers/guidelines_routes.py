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

import io
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from lightrag.base import QueryParam
from lightrag.api.utils_api import get_combined_auth_dependency
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
            for chunk in chunks[: request.top_k]:
                content = chunk.get("content")
                if not content:
                    continue
                file_path = chunk.get("file_path", "unknown_source")
                chunk_id = chunk.get("chunk_id", "")
                edition = _edition_from_filename(file_path)
                passages.append(
                    RetrievedPassage(
                        text=content,
                        citation=f"{file_path}#chunk={chunk_id}@{edition}",
                        score=chunk.get("score"),
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

    @router.get("/v1/guidelines/_debug/section-crop", dependencies=[Depends(combined_auth)])
    async def _debug_section_crop(chunk_id: str = Query(...)):
        """TEMPORARY (guidelines-section-crop-substrate-verify): confirm the crop substrate on the
        deployment — (1) chunk `sidecar` persists in the store, (2) `<doc>.parsed/blocks.jsonl` is on
        the volume + resolves via resolve_provenance, (3) the source PDF path exists. Remove after
        recording findings."""
        from pathlib import Path as _P

        from lightrag.sidecar.provenance import load_blocks_by_id, resolve_provenance
        from lightrag.utils_pipeline import (
            configured_input_dir,
            parsed_artifact_dir_for,
        )

        chunk = await rag.text_chunks.get_by_id(chunk_id)
        if not chunk:
            raise HTTPException(status_code=404, detail=f"chunk not found: {chunk_id}")
        sidecar = chunk.get("sidecar")
        file_path = chunk.get("file_path", "")

        parsed_dir = parsed_artifact_dir_for(file_path)
        blocks_files = (
            sorted(str(p) for p in parsed_dir.glob("*.blocks.jsonl"))
            if parsed_dir.exists()
            else []
        )
        provenance = None
        blocks_count = 0
        if blocks_files and sidecar:
            try:
                bbid = load_blocks_by_id(blocks_files[0])
                blocks_count = len(bbid)
                provenance = resolve_provenance(sidecar, bbid)
            except Exception as e:  # pragma: no cover - debug endpoint
                provenance = {"error": str(e)}

        input_dir = _P(configured_input_dir())
        stem = _P(file_path).stem
        pdf_candidates = [
            {"path": str(c), "exists": c.exists()}
            for c in (input_dir / _P(file_path).name, input_dir / f"{stem}.pdf")
        ]
        input_listing = (
            sorted(p.name for p in input_dir.iterdir())[:40]
            if input_dir.exists()
            else []
        )

        return {
            "chunk_id": chunk_id,
            "file_path": file_path,
            "has_sidecar": sidecar is not None,
            "sidecar": sidecar,
            "parsed_dir": str(parsed_dir),
            "parsed_dir_exists": parsed_dir.exists(),
            "blocks_files": blocks_files,
            "blocks_count": blocks_count,
            "provenance": provenance,
            "input_dir": str(input_dir),
            "input_dir_exists": input_dir.exists(),
            "input_listing_sample": input_listing,
            "pdf_candidates": pdf_candidates,
        }

    return router
