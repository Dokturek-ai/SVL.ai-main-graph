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
