"""`_unknown` → real-edition-year rename planner (spec 016).

Six docs entered the store with a `_unknown` suffix because the corpus-prep step didn't fall back to
the PDF's year when the filename lacked one. `parse_edition` maps no-year → `edition_date=""`, which
`edition_sort_key` sorts EARLIEST — so where the `_unknown` doc is actually the *newest* edition of a
multi-edition work (Virová hepatitida C 2023 vs `_2015`; Vybraná onkologická 2023 vs `_2018`) the pass
inverts the order and marks the newest clinical guideline `superseded_by_edition`. This module is the
PURE planner: it intersects the frozen, human-verified year map with what is actually in the store and
classifies each entry (renamable / already-done / absent). The (impure) runner executes the whole-value
UPDATE + `<SEP>`-substring REPLACE across the storages.

The year is a JUDGEMENT, not re-derived at runtime: for hepatitida the title page says "NOVELIZACE 2023"
while the PDF `CreationDate` is 2025 (a re-export postdating the content), so the map is hard-coded to the
title-page year. The durable ingest resolver (`resolve_edition_year`) encodes the same priority for future
docs; this map fixes the 6 already in the store.

Unicode: the map is authored in NFC, but stored file_paths are NFD (the macOS filesystem decomposes
diacritics at ingest — only the ASCII `Bolesti hlavy` matched a naive NFC compare). Matching normalizes
both sides to NFC, while the plan carries the ACTUAL stored spelling so the SQL/Cypher `WHERE file_path`
matches the stored bytes, and derives the new name from that stored spelling (preserving its normalization).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

_UNKNOWN_SUFFIX = "_unknown.pdf"

# old file_path (NFC, as authored) -> verified edition year.
EDITION_YEARS: dict[str, str] = {
    "Akutní průjem_unknown.pdf": "2023",
    "Bolesti hlavy_unknown.pdf": "2023",
    "Chronická tromboembolická plicní nemoc CTEPD chronická tromboembolická plicní hypertenze CTEPH_unknown.pdf": "2024",
    "Včasný záchyt chronických jaterních chorob_unknown.pdf": "2025",
    "Virová hepatitida C_unknown.pdf": "2023",  # title page: NOVELIZACE 2023 (CreationDate 2025 = re-export)
    "Vybraná onkologická onemocnění_unknown.pdf": "2023",
}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _new_name(old: str, year: str) -> str:
    """`<work>_unknown.pdf` -> `<work>_<year>.pdf`, preserving ``old``'s unicode normalization
    (the suffix is ASCII, so slicing is normalization-safe)."""
    return old[: -len(_UNKNOWN_SUFFIX)] + f"_{year}.pdf"


@dataclass
class RenamePlan:
    to_rename: list[tuple[str, str]] = field(default_factory=list)  # (stored_old, new) — present in store
    already_done: list[str] = field(default_factory=list)  # new name already present (idempotent re-run)
    absent: list[str] = field(default_factory=list)  # neither old nor new in store (nothing to do)

    @property
    def count(self) -> int:
        return len(self.to_rename)

    def summary(self) -> dict:
        return {
            "to_rename": [{"old": o, "new": n} for o, n in self.to_rename],
            "renamable": len(self.to_rename),
            "already_done": len(self.already_done),
            "absent": len(self.absent),
        }


def plan_rename(live_file_paths: list[str]) -> RenamePlan:
    """Classify each frozen rename against the file_paths actually in the store, matching by NFC so an
    NFD-stored diacritic path still matches. The plan carries the stored spelling (for the SQL WHERE) and
    the new name derived from it. Idempotent: once a doc carries its `_<year>` name it lands in
    ``already_done`` and the runner skips it."""
    live_by_nfc: dict[str, str] = {}
    for fp in live_file_paths:
        live_by_nfc.setdefault(_nfc(fp), fp)  # keep the actual stored spelling per NFC key

    plan = RenamePlan()
    for old, year in EDITION_YEARS.items():
        old_key = _nfc(old)
        new_key = _nfc(_new_name(old_key, year))
        if old_key in live_by_nfc:
            stored_old = live_by_nfc[old_key]
            plan.to_rename.append((stored_old, _new_name(stored_old, year)))
        elif new_key in live_by_nfc:
            plan.already_done.append(live_by_nfc[new_key])
        else:
            plan.absent.append(old)
    return plan
