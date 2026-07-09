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

from fastapi import APIRouter, Depends, HTTPException
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

    @router.post("/v1/guidelines:promote", dependencies=[Depends(combined_auth)])
    async def guidelines_promote():
        """Run the deterministic promotion pass over the live store → versioned grounded bundle (spec 001).

        harvest (impure: reads the deployed PG+Neo4j store) → promote (pure G1–G5) →
        immutable bundle written to PROMOTION_BUNDLE_DIR on the data volume. Returns the
        manifest (content hash + completeness counts). Long-running on a large store.
        The promotion module is imported lazily so a packaging gap degrades this one
        endpoint to a 500 instead of crashing the server at startup.
        """
        try:
            import asyncio

            from promotion import jsonl
            from promotion.bundle import build_manifest, write_bundle
            from promotion.harvest import harvest
            from promotion.promote import promote

            out_dir = Path(_BUNDLE_DIR)
            with tempfile.TemporaryDirectory() as tmp:
                snap_dir = Path(tmp) / "snapshot"
                harvest_counts = await harvest(rag, snap_dir)

                # promote()/build_manifest() iterate the whole graph and run the
                # locate regex per anchor — CPU-bound. Run off the event loop so a
                # large-corpus emit does not block health probes / concurrent requests.
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
            return {
                "harvest_counts": harvest_counts,
                "content_hash": manifest.content_hash,
                "counts": manifest.counts,
                "corpus_size": len(manifest.corpus),
                "bundle_dir": str(out_dir),
            }
        except Exception as e:
            logger.error(f"Error in guidelines:promote: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

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

    return router
