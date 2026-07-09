"""G4 — the immutable emit: nodes.jsonl + edges.jsonl + quarantine.jsonl +
manifest.json. The manifest carries a content hash over the canonicalized sorted
records (a silent break is undetectable without it — ship it first), the corpus
list, pipeline pins, and completeness counts (anchor coverage is 100% by
construction; orphan rate + doc coverage are surfaced, not hidden).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .hashing import sha1_hex
from .jsonl import write_jsonl
from .registry import build_registry
from .types import Bundle, Manifest


def _content_hash(bundle: Bundle) -> str:
    nodes = sorted((n.to_dict() for n in bundle.nodes), key=lambda d: d["node_id"])
    edges = sorted((e.to_dict() for e in bundle.edges), key=lambda d: d["edge_id"])
    blob = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, ensure_ascii=False)
    return sha1_hex(blob)


def _corpus(registry) -> list[dict[str, Any]]:
    by_doc: dict[str, list] = defaultdict(list)
    for ch in registry.values():
        by_doc[ch.doc_id].append(ch)
    out = []
    for doc_id, chunks in sorted(by_doc.items()):
        chunks.sort(key=lambda c: c.chunk_id)
        out.append(
            {
                "doc_id": doc_id,
                "work_id": chunks[0].work_id,
                "edition_date": chunks[0].edition_date,
                "content_hash": sha1_hex(*[c.content_hash for c in chunks]),
            }
        )
    return out


def _counts(bundle: Bundle, registry) -> dict[str, Any]:
    n = len(bundle.nodes)
    degree = {node.node_id: 0 for node in bundle.nodes}
    for e in bundle.edges:
        if e.head_id in degree:
            degree[e.head_id] += 1
        if e.tail_id in degree:
            degree[e.tail_id] += 1
    orphans = sum(1 for d in degree.values() if d == 0)
    emitted_docs = {
        registry[a.chunk_id].doc_id
        for node in bundle.nodes
        for a in node.anchors
        if a.chunk_id in registry
    }
    total_docs = {ch.doc_id for ch in registry.values()}
    return {
        "nodes": n,
        "nodes_span": sum(1 for node in bundle.nodes if node.fidelity == "span"),
        "nodes_chunk": sum(1 for node in bundle.nodes if node.fidelity == "chunk"),
        "edges": len(bundle.edges),
        "edges_span": sum(1 for e in bundle.edges if e.fidelity == "span"),
        "edges_chunk": sum(1 for e in bundle.edges if e.fidelity == "chunk"),
        "quarantined": len(bundle.quarantine),
        "anchor_coverage": 1.0,  # by construction — nothing enters without an anchor
        "doc_coverage": round(len(emitted_docs) / len(total_docs), 4) if total_docs else 0.0,
        "orphan_rate": round(orphans / n, 4) if n else 0.0,
        "edge_node_ratio": round(len(bundle.edges) / n, 4) if n else 0.0,
    }


def build_manifest(
    bundle: Bundle, snapshot: dict[str, list[dict]], pins: dict | None = None, overrides=None
) -> Manifest:
    # overrides must match promote()'s so the manifest's corpus/edition audit
    # fields describe the same records that were promoted.
    registry = build_registry(snapshot["chunks"], snapshot["docs"], overrides)
    return Manifest(
        content_hash=_content_hash(bundle),
        corpus=_corpus(registry),
        pins=pins or {},
        counts=_counts(bundle, registry),
    )


def write_bundle(bundle: Bundle, manifest: Manifest, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "nodes.jsonl", [n.to_dict() for n in sorted(bundle.nodes, key=lambda x: x.node_id)])
    write_jsonl(out / "edges.jsonl", [e.to_dict() for e in sorted(bundle.edges, key=lambda x: x.edge_id)])
    write_jsonl(out / "quarantine.jsonl", [q.to_dict() for q in bundle.quarantine])
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "content_hash": manifest.content_hash,
                "corpus": manifest.corpus,
                "pins": manifest.pins,
                "counts": manifest.counts,
            },
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
