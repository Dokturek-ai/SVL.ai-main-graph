"""G3 — edition lineage, derived deterministically from the corpus manifest.

Edition (`work_id`, `edition_date`) is read from the document filename
(`Arteriální hypertenze_2024.md` -> work "Arteriální hypertenze", edition
"2024"), never mined from content. An optional override manifest handles
filenames that don't follow the pattern.

Supersession + conflict detection over the promoted records live here too
(they operate on edition order); wired into ``promote`` in P3.
"""

from __future__ import annotations

import re
from pathlib import Path

_EDITION_RE = re.compile(r"^(?P<work>.+?)[ _-](?P<year>\d{4})$")


def parse_edition(
    file_path: str, overrides: dict[str, tuple[str, str]] | None = None
) -> tuple[str, str]:
    """Return ``(work_id, edition_date)`` for a document path.

    ``edition_date`` is "" when no 4-digit year is present in the stem (the
    document still promotes; it just sorts as the earliest / unknown edition).
    """
    if overrides and file_path in overrides:
        return overrides[file_path]
    stem = Path(file_path).stem
    m = _EDITION_RE.match(stem)
    if m:
        return m.group("work").strip(), m.group("year")
    return stem.strip(), ""


def edition_sort_key(edition_date: str) -> tuple[int, str]:
    """Total order over editions of a work; unknown ("") sorts earliest."""
    return (int(edition_date) if edition_date.isdigit() else -1, edition_date)


def latest_edition(edition_dates: list[str]) -> str:
    """The most recent edition among a work's editions."""
    return max(edition_dates, key=edition_sort_key)


def work_latest_editions(registry) -> dict[str, str]:
    """``work_id -> latest edition_date`` across the whole corpus (all editions
    of a work that were ingested), from the chunk registry."""
    latest: dict[str, str] = {}
    for ch in registry.values():
        cur = latest.get(ch.work_id)
        if cur is None or edition_sort_key(ch.edition_date) > edition_sort_key(cur):
            latest[ch.work_id] = ch.edition_date
    return latest


def mark_supersession(records, work_latest: dict[str, str]) -> None:
    """A fact asserted only by an edition older than its work's latest edition is
    a stale candidate: stamp ``superseded_by_edition`` (out of the default view)."""
    for rec in records:
        wl = work_latest.get(rec.work_id)
        if wl and edition_sort_key(rec.edition_date) < edition_sort_key(wl):
            rec.superseded_by_edition = wl


def flag_conflicts(edges) -> None:
    """Same ``(head, rel_type)`` asserting different tails across editions is a
    conflict candidate — a review artifact, not an auto-resolution. Adjudication
    is mkn10's job; here we only flag."""
    from collections import defaultdict

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for e in edges:
        groups[(e.head_id, e.rel_type)].append(e)
    for (_, rel_type), group in groups.items():
        tails_by_edition: dict[str, set[str]] = defaultdict(set)
        for e in group:
            tails_by_edition[e.edition_date].add(e.tail_id)
        if len(tails_by_edition) >= 2 and len({frozenset(v) for v in tails_by_edition.values()}) > 1:
            info = {
                "rel_type": rel_type,
                "tails_by_edition": {ed: sorted(tails_by_edition[ed]) for ed in sorted(tails_by_edition)},
            }
            for e in group:
                e.conflict = info


def latest_view(bundle):
    """The default emitted view: records not superseded by a newer edition."""
    return (
        [n for n in bundle.nodes if n.superseded_by_edition is None],
        [e for e in bundle.edges if e.superseded_by_edition is None],
    )
