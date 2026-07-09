from pathlib import Path

import pytest

from lightrag.promotion import jsonl

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "two-edition-corpus"


@pytest.fixture
def snapshot() -> dict[str, list[dict]]:
    return {
        "docs": jsonl.read_jsonl(FIXTURE_DIR / "docs.jsonl"),
        "chunks": jsonl.read_jsonl(FIXTURE_DIR / "chunks.jsonl"),
        "nodes": jsonl.read_jsonl(FIXTURE_DIR / "nodes.jsonl"),
        "edges": jsonl.read_jsonl(FIXTURE_DIR / "edges.jsonl"),
    }
