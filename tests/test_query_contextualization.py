"""Unit tests for follow-up query contextualization in the retrieval path.

Retrieval (keyword extraction + vector search + rerank) ignores
``conversation_history`` by design, so ``_contextualize_query_with_history``
rewrites a bare follow-up ("a u mužů?") into a standalone query before
retrieval. The answer LLM still receives the original query + full history.
On any failure the original query is returned so retrieval is never worse.
"""

import pytest

from lightrag.base import QueryParam
from lightrag.operate import _contextualize_query_with_history


def _global_config(llm_func):
    return {
        "role_llm_funcs": {"keyword": llm_func},
        "addon_params": {"language": "Czech"},
        "_resolved_summary_language": "Czech",
    }


@pytest.mark.offline
async def test_no_history_returns_original_without_llm_call():
    calls = []

    async def llm(*args, **kwargs):
        calls.append(args)
        return "SHOULD NOT BE CALLED"

    param = QueryParam()  # conversation_history defaults to []
    out = await _contextualize_query_with_history(
        "Jaká je léčba akutní cystitidy?", param, _global_config(llm)
    )
    assert out == "Jaká je léčba akutní cystitidy?"
    assert calls == []  # no LLM call, no cost when there is no history


@pytest.mark.offline
async def test_history_present_returns_rewritten_query():
    async def llm(prompt, **kwargs):
        # LightRAG passes the prompt positionally; retrieval must not stream here.
        assert kwargs.get("stream") is False
        return "  Jaká je léčba akutní cystitidy u mužů?  "

    param = QueryParam(
        conversation_history=[
            {"role": "user", "content": "Jaká je léčba akutní cystitidy?"},
            {"role": "assistant", "content": "U žen se podává nitrofurantoin..."},
        ]
    )
    out = await _contextualize_query_with_history(
        "a u mužů?", param, _global_config(llm)
    )
    assert out == "Jaká je léčba akutní cystitidy u mužů?"


@pytest.mark.offline
async def test_long_history_messages_are_trimmed_in_prompt():
    captured = {}

    async def llm(prompt, **kwargs):
        captured["prompt"] = prompt
        return "standalone query"

    long_answer = "A" * 2000
    param = QueryParam(
        conversation_history=[
            {"role": "user", "content": "Jaká je léčba akutní cystitidy?"},
            {"role": "assistant", "content": long_answer},
        ]
    )
    await _contextualize_query_with_history("a u mužů?", param, _global_config(llm))
    # Each message is capped at 500 chars, so the full 2000-char answer never
    # reaches the rewrite prompt.
    assert long_answer not in captured["prompt"]
    assert "A" * 500 in captured["prompt"]
    assert "A" * 501 not in captured["prompt"]


@pytest.mark.offline
async def test_llm_failure_falls_back_to_original():
    async def llm(prompt, **kwargs):
        raise RuntimeError("LLM down")

    param = QueryParam(conversation_history=[{"role": "user", "content": "x"}])
    out = await _contextualize_query_with_history(
        "a u mužů?", param, _global_config(llm)
    )
    assert out == "a u mužů?"


@pytest.mark.offline
async def test_empty_rewrite_falls_back_to_original():
    async def llm(prompt, **kwargs):
        return "   "

    param = QueryParam(conversation_history=[{"role": "user", "content": "x"}])
    out = await _contextualize_query_with_history(
        "a u mužů?", param, _global_config(llm)
    )
    assert out == "a u mužů?"
