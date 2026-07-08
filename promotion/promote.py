"""The pure promotion spine: snapshot -> Bundle (grounded records + quarantine).

The repo is the last writer here. A node/edge enters the bundle only if G1
locates its surface form(s) in the chunk its ``source_id`` points to; the found
offsets become the anchor. Ungrounded -> quarantine (machine-readable reason),
never admitted-with-a-marker, never silently dropped (emitted-surface-forms +
quarantined covers every input). Grounded nodes are then merged by their
canonical key (G5), stamped with edition/supersession, and cross-edition
conflicts flagged (G3).
"""

from __future__ import annotations

from collections import defaultdict

from .canonicalize import load_aliases, load_type_enum, merge_key, validate_type
from .edition import (
    edition_sort_key,
    flag_conflicts,
    latest_edition,
    mark_supersession,
    work_latest_editions,
)
from .hashing import sha1_hex
from .locate import locate
from .registry import build_registry
from .types import Anchor, Bundle, GroundedEdge, GroundedNode, Quarantine


def _node_id(merge_key_: str, type_: str) -> str:
    # Keyed on the canonical merge key (not the display name) so case/diacritic
    # variants share an id and the id is stable across re-emits.
    return sha1_hex(merge_key_, type_)


def _edge_id(head_id: str, rel_type: str, tail_id: str, work_id: str, edition_date: str) -> str:
    return sha1_hex(head_id, rel_type, tail_id, work_id, edition_date)


def promote(snapshot: dict[str, list[dict]], overrides=None) -> Bundle:
    registry = build_registry(snapshot["chunks"], snapshot["docs"], overrides)
    type_enum = load_type_enum()
    aliases = load_aliases()

    quarantine: list[Quarantine] = []

    # Phase A — ground each input node (locate-or-quarantine).
    grounded: list[dict] = []
    for n in snapshot["nodes"]:
        anchors: list[Anchor] = []
        editions: list[str] = []
        works: list[str] = []
        chunk_missing = False
        for sid in n.get("source_ids", []):
            chunk = registry.get(sid)
            if chunk is None:
                chunk_missing = True
                continue
            a = locate(n["name"], chunk.content, sid)
            if a:
                anchors.append(a)
                editions.append(chunk.edition_date)
                works.append(chunk.work_id)
        if not anchors:
            reason = "chunk-unresolved" if chunk_missing else "entity-not-found"
            quarantine.append(Quarantine("entity", n["name"], reason, n.get("source_ids", [])))
            continue
        grounded.append(
            {
                "name": n["name"],
                "type": validate_type(n.get("type", "Other"), type_enum),
                "anchors": anchors,
                "editions": editions,
                "works": works,
                "source_ids": n.get("source_ids", []),
                "concept_ref": n.get("concept_ref"),
                "description": n.get("description", ""),
            }
        )

    # Phase B — merge grounded nodes sharing a canonical key + type.
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for g in grounded:
        groups[(merge_key(g["name"], aliases), g["type"])].append(g)

    nodes: list[GroundedNode] = []
    by_name: dict[str, GroundedNode] = {}
    for (mkey, type_), members in groups.items():
        names = sorted({m["name"] for m in members})
        editions = [e for m in members for e in m["editions"]]
        works = [w for m in members for w in m["works"]]
        edition = latest_edition(editions)
        node = GroundedNode(
            node_id=_node_id(mkey, type_),
            canonical_name=names[0],  # deterministic display among variants
            type=type_,
            surface_forms=names,
            as_of=edition,
            work_id=works[0] if works else "",
            edition_date=edition,
            anchors=[a for m in members for a in m["anchors"]],
            source_ids=sorted({s for m in members for s in m["source_ids"]}),
            description=next((m["description"] for m in members if m["description"]), ""),
            concept_ref=next((m["concept_ref"] for m in members if m["concept_ref"]), None),
        )
        nodes.append(node)
        for m in members:
            by_name[m["name"]] = node

    # Phase C — edges: both endpoints admitted AND locatable in the edge's chunk.
    edges: list[GroundedEdge] = []
    for e in snapshot["edges"]:
        head, tail = by_name.get(e["head"]), by_name.get(e["tail"])
        if head is None or tail is None:
            quarantine.append(
                Quarantine("edge", f'{e["head"]} -> {e["tail"]}', "endpoint-missing", e.get("source_ids", []))
            )
            continue
        candidates: list[tuple] = []
        for sid in e.get("source_ids", []):
            chunk = registry.get(sid)
            if chunk is None:
                continue
            ha, ta = locate(e["head"], chunk.content, sid), locate(e["tail"], chunk.content, sid)
            if ha and ta:
                candidates.append((chunk, ha))
        if not candidates:
            quarantine.append(
                Quarantine("edge", f'{e["head"]} -> {e["tail"]}', "endpoint-missing", e.get("source_ids", []))
            )
            continue
        # An edge asserted across editions is stamped with its LATEST (current)
        # assertion; older-only edges fall out as superseded below.
        chunk, anchor = max(candidates, key=lambda c: edition_sort_key(c[0].edition_date))
        edition, work = chunk.edition_date, chunk.work_id
        rel_type = e.get("rel_type") or "related"
        edges.append(
            GroundedEdge(
                edge_id=_edge_id(head.node_id, rel_type, tail.node_id, work, edition),
                head_id=head.node_id,
                tail_id=tail.node_id,
                rel_type=rel_type,
                keywords=e.get("keywords", ""),
                description=e.get("description", ""),
                as_of=edition,
                work_id=work,
                edition_date=edition,
                anchor=anchor,
            )
        )

    # Phase D — edition supersession (older-only facts) + cross-edition conflicts.
    work_latest = work_latest_editions(registry)
    mark_supersession(nodes + edges, work_latest)
    flag_conflicts(edges)

    return Bundle(nodes=nodes, edges=edges, quarantine=quarantine)
