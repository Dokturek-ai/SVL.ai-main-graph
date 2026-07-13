"""Chunk metadata propagation (spec 015) — PURE, no I/O.

Grounding resolved ``concept_ref`` onto ENTITIES; a chunk inherits the concept_refs of the entities whose
``source_id`` includes it — the inverse of ``retrieve_filter.build_code_index``. ``facet`` comes from the
chunk's section heading (sidecar provenance). No fresh mkn10 resolve — reuse the verified grounding.

The persisted tag lets retrieve read ``chunk.concept_ref``/``chunk.facet`` directly (exact filter, no
per-request ``get_knowledge_graph``) and lets the A-harvest reify the refs into mkn10 facts.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from lightrag.constants import GRAPH_FIELD_SEP
from lightrag.guidelines.retrieve_filter import _is_drug, classify_facet, code_matches, dotnorm


def build_chunk_tags(
    entities: Iterable[tuple],
    sections: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Propagate entity concept_ref onto chunks + classify each chunk's facet.

    Args:
        entities: iterable of ``(concept_ref_list | None, source_id_str | None)`` — one per graph entity.
        sections: optional ``chunk_id -> section_heading`` (sidecar) for the facet tag.

    Returns:
        ``chunk_id -> {"concept_ref": [ {code, system, ...}, … ] | None, "facet": <enum> | None}``.
        A chunk's ``concept_ref`` is the deduped union (by ``(code, system)``) of its grounded entities'
        refs (drug + MKN kept as-is). Every chunk with either refs OR a section gets a record.
    """
    sections = sections or {}
    chunk_refs: dict[str, dict] = defaultdict(dict)  # chunk -> {(code, system): ref}
    for refs, source_id in entities:
        if not refs:
            continue
        chunks = [c for c in (source_id or "").replace(GRAPH_FIELD_SEP, "\n").split("\n") if c.strip()]
        if not chunks:
            continue
        for r in refs:
            code = r.get("code")
            if not code:
                continue
            key = (code, r.get("system"))
            for c in chunks:
                chunk_refs[c].setdefault(key, r)

    out: dict[str, dict] = {}
    for c in set(chunk_refs) | set(sections):
        refs = list(chunk_refs.get(c, {}).values())
        out[c] = {"concept_ref": refs or None, "facet": classify_facet(sections.get(c))}
    return out


def chunk_has_code(tag: dict, request_code: str) -> bool:
    """True if a chunk's persisted tag carries a concept_ref code in the requested code's family."""
    for r in (tag or {}).get("concept_ref") or []:
        if code_matches(r.get("code", ""), request_code):
            return True
    return False


def write_chunk_tags(tags: dict[str, dict], out_dir: str | Path) -> dict:
    """Write the ``chunk-tags.jsonl`` artifact (one ``{chunk_id, concept_ref}`` per code-tagged chunk) +
    a manifest. Only chunks WITH a concept_ref are written (the join layer); returns the manifest."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    n_chunks = codes = 0
    # write to a temp file then atomically rename, so a concurrent retrieve read never sees a torn file
    tmp = d / "chunk-tags.jsonl.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        for chunk_id, tag in sorted(tags.items()):
            refs = tag.get("concept_ref")
            if not refs:
                continue
            f.write(json.dumps({"chunk_id": chunk_id, "concept_ref": refs}, ensure_ascii=False) + "\n")
            n_chunks += 1
            codes += len(refs)
    tmp.replace(d / "chunk-tags.jsonl")  # atomic
    manifest = {"chunk_count": n_chunks, "ref_count": codes}
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def load_code_index(artifact_dir: str | Path) -> dict[str, set[str]]:
    """Load ``chunk-tags.jsonl`` and INVERT it into the ``dot-normalized code -> {chunk_id}`` map that
    ``retrieve_filter.chunks_for_code`` consumes (the same shape as ``build_code_index``, artifact-sourced)."""
    p = Path(artifact_dir) / "chunk-tags.jsonl"
    index: dict[str, set[str]] = defaultdict(set)
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            cid = rec.get("chunk_id")
            for r in rec.get("concept_ref") or []:
                if _is_drug(r):  # MKN-only index (mirror build_code_index) — drug refs stay in the artifact
                    continue
                code = dotnorm(r.get("code") or "")
                if cid and len(code) >= 3:
                    index[code].add(cid)
    return index
