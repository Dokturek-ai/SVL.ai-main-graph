"""Impure harvest: the deployed LightRAG store -> a raw snapshot of files.

This is the ONLY module that touches a DB. It is deliberately dumb — it reads
the store and writes normalized JSONL; all trust/verification logic lives in the
pure pass that consumes the snapshot. Not covered by the offline golden suite
(no DB in CI); exercised by the opt-in live smoke (spec task T010). The exact
store field names are confirmed on the first live run.

Snapshot schema written (consumed by registry/promote):
  docs.jsonl   {doc_id, file_path, status, chunks_count}
  chunks.jsonl {chunk_id, content, doc_id, file_path, chunk_order_index}
  nodes.jsonl  {name, type, description, source_ids[], file_paths[], concept_ref?}
  edges.jsonl  {head, tail, rel_type, keywords, description, source_ids[], file_paths[]}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .jsonl import write_jsonl

try:  # separator LightRAG uses to join multi-valued source_id / file_path
    from lightrag.utils import GRAPH_FIELD_SEP
except Exception:  # pragma: no cover - fallback if the constant moves
    GRAPH_FIELD_SEP = "<SEP>"


def _split(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [p for p in str(value).split(GRAPH_FIELD_SEP) if p]


def _prop(record: dict, key: str, default: Any = "") -> Any:
    """LightRAG storage rows expose fields either flat or under 'properties'."""
    if key in record:
        return record[key]
    props = record.get("properties")
    if isinstance(props, dict) and key in props:
        return props[key]
    return default


async def harvest(rag: Any, out_dir: str | Path) -> dict[str, int]:
    """Dump the deployed store to ``out_dir`` as four JSONL files.

    ``rag`` is an initialized ``LightRAG``. Returns per-file counts.
    """
    out = Path(out_dir)
    graph = rag.chunk_entity_relation_graph

    raw_nodes = await graph.get_all_nodes()
    raw_edges = await graph.get_all_edges()

    nodes = [
        {
            "name": _prop(n, "entity_id") or _prop(n, "name") or (n.get("labels") or [""])[0],
            "type": _prop(n, "entity_type", "Other"),
            "description": _prop(n, "description"),
            "source_ids": _split(_prop(n, "source_id")),
            "file_paths": _split(_prop(n, "file_path")),
        }
        for n in raw_nodes
    ]
    edges = [
        {
            "head": _prop(e, "source") or _prop(e, "src_id"),
            "tail": _prop(e, "target") or _prop(e, "tgt_id"),
            "rel_type": (_prop(e, "keywords") or "related").split(",")[0].strip(),
            "keywords": _prop(e, "keywords"),
            "description": _prop(e, "description"),
            "source_ids": _split(_prop(e, "source_id")),
            "file_paths": _split(_prop(e, "file_path")),
        }
        for e in raw_edges
    ]

    # Chunks: read the text_chunks KV store. get_all() is the batch read; if a
    # backend lacks it the live smoke reports it (confirmed on first run).
    chunk_store = rag.text_chunks
    raw_chunks = await chunk_store.get_all()
    chunks = [
        {
            "chunk_id": cid,
            "content": c.get("content", ""),
            "doc_id": c.get("full_doc_id", ""),
            "file_path": c.get("file_path", ""),
            "chunk_order_index": c.get("chunk_order_index", 0),
        }
        for cid, c in (raw_chunks or {}).items()
    ]

    doc_status = await rag.get_docs_by_status("processed")
    docs = [
        {
            "doc_id": doc_id,
            "file_path": getattr(d, "file_path", "") or "",
            "status": "processed",
            "chunks_count": getattr(d, "chunks_count", 0) or 0,
        }
        for doc_id, d in (doc_status or {}).items()
    ]

    write_jsonl(out / "docs.jsonl", docs)
    write_jsonl(out / "chunks.jsonl", chunks)
    write_jsonl(out / "nodes.jsonl", nodes)
    write_jsonl(out / "edges.jsonl", edges)
    return {"docs": len(docs), "chunks": len(chunks), "nodes": len(nodes), "edges": len(edges)}
