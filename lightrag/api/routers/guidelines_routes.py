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

import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lightrag.base import QueryParam
from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.utils import logger

# Corpus filenames encode the edition as `Work_YEAR.md` (e.g. `Arteriální hypertenze_2024.md`).
_EDITION_RE = re.compile(r"_(\d{4})(?:\.|$)")


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


def create_guidelines_routes(rag, api_key: Optional[str] = None, top_k: int = 5):
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

    return router
