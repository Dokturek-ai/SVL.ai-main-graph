"""G2 — the chunk registry: ``chunk_id -> ChunkRecord``.

Built once from the snapshot's chunks + docs. Every promoted node/edge joins
its ``source_id`` to this registry to (a) confirm the chunk exists and (b) get
the text the locate pass searches + the edition the fact inherits. This is the
join that replaces LightRAG's ``unknown_source`` / read-time fuzzy recovery.
"""

from __future__ import annotations

from .edition import parse_edition
from .hashing import sha1_hex
from .types import ChunkRecord


def build_registry(
    chunks: list[dict],
    docs: list[dict],
    overrides: dict[str, tuple[str, str]] | None = None,
) -> dict[str, ChunkRecord]:
    doc_fp = {d["doc_id"]: d.get("file_path", "") for d in docs}
    registry: dict[str, ChunkRecord] = {}
    for c in chunks:
        file_path = c.get("file_path") or doc_fp.get(c.get("doc_id", ""), "")
        work_id, edition_date = parse_edition(file_path, overrides)
        content = c.get("content", "")
        registry[c["chunk_id"]] = ChunkRecord(
            chunk_id=c["chunk_id"],
            doc_id=c.get("doc_id", ""),
            file_path=file_path,
            content=content,
            content_hash=sha1_hex(content),
            work_id=work_id,
            edition_date=edition_date,
            chunk_order_index=c.get("chunk_order_index", 0),
        )
    return registry
