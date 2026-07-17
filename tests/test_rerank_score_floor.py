"""Unit tests for the rerank score floor in process_chunks_unified (utils.py).

Guards the fix from docs/briefs/2026-07-17-guidelines-rerank-reference-precision.md:
with MIN_RERANK_SCORE > 0, a reranked chunk scoring below the floor is dropped from
BOTH the returned context and the derived citation list — that is what removes the
off-topic ("migréna") citation from an "erythema migrans" answer.

A score-less chunk is deliberately KEPT (default 1.0): apply_rerank_if_enabled returns
the full, unscored chunk set on a rerank outage (empty result / exception / no model),
so failing closed there would drop ALL context and break the answer. The floor is a
quality filter on a working reranker, not an outage kill-switch.

The rerank call itself is bypassed by passing an empty query (process_chunks_unified
skips reranking when ``query`` is falsy), so no LLM / network is touched — the test
exercises the floor filter against pre-set ``rerank_score`` values only.
"""

from lightrag.base import QueryParam
from lightrag.utils import (
    generate_reference_list_from_chunks,
    process_chunks_unified,
)


def _chunks():
    return [
        {"content": "borrelia abx", "file_path": "borelioza.pdf", "rerank_score": 0.62},
        {"content": "migraine tx", "file_path": "migrena.pdf", "rerank_score": 0.32},
        {"content": "no score", "file_path": "unscored.pdf"},  # rerank-outage chunk
    ]


async def test_floor_drops_below_threshold_scored_chunk_from_context_and_refs():
    query_param = QueryParam(enable_rerank=True, chunk_top_k=None)
    global_config = {"min_rerank_score": 0.4}

    kept = await process_chunks_unified(
        query="",  # falsy -> skip rerank, exercise only the floor filter
        unique_chunks=_chunks(),
        query_param=query_param,
        global_config=global_config,
    )

    kept_paths = [c["file_path"] for c in kept]
    # scored-below-floor dropped; scored-above kept; score-less kept (graceful degrade)
    assert kept_paths == ["borelioza.pdf", "unscored.pdf"]
    assert "migrena.pdf" not in kept_paths

    references, _ = generate_reference_list_from_chunks(kept)
    ref_paths = [r["file_path"] for r in references]
    assert "migrena.pdf" not in ref_paths  # off-topic citation gone
    assert "borelioza.pdf" in ref_paths


async def test_floor_zero_disables_filter():
    query_param = QueryParam(enable_rerank=True, chunk_top_k=None)
    global_config = {"min_rerank_score": 0.0}

    kept = await process_chunks_unified(
        query="",
        unique_chunks=_chunks(),
        query_param=query_param,
        global_config=global_config,
    )

    assert len(kept) == 3  # floor disabled -> every chunk survives
