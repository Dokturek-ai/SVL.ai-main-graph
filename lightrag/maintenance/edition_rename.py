"""`_unknown` → real-edition-year rename planner (spec 016).

Six docs entered the store with a `_unknown` suffix because the corpus-prep step didn't fall back to
the PDF's year when the filename lacked one. `parse_edition` maps no-year → `edition_date=""`, which
`edition_sort_key` sorts EARLIEST — so where the `_unknown` doc is actually the *newest* edition of a
multi-edition work (Virová hepatitida C 2023 vs `_2015`; Vybraná onkologická 2023 vs `_2018`) the pass
inverts the order and marks the newest clinical guideline `superseded_by_edition`. This module is the
PURE planner: it intersects the frozen, human-verified rename map with what is actually in the store and
classifies each entry (renamable / already-done / absent). The (impure) runner executes the whole-value
UPDATE + `<SEP>`-substring REPLACE across the storages.

The year is a JUDGEMENT, not re-derived at runtime: for hepatitida the title page says "NOVELIZACE 2023"
while the PDF `CreationDate` is 2025 (a re-export postdating the content), so the map is hard-coded to the
title-page year. The durable ingest resolver (`resolve_edition_year`) encodes the same priority for future
docs; this map fixes the 6 already in the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# old file_path (as stored, exact) -> new file_path with the verified edition year.
RENAMES: dict[str, str] = {
    "Akutní průjem_unknown.pdf": "Akutní průjem_2023.pdf",
    "Bolesti hlavy_unknown.pdf": "Bolesti hlavy_2023.pdf",
    "Chronická tromboembolická plicní nemoc CTEPD chronická tromboembolická plicní hypertenze CTEPH_unknown.pdf": "Chronická tromboembolická plicní nemoc CTEPD chronická tromboembolická plicní hypertenze CTEPH_2024.pdf",
    "Včasný záchyt chronických jaterních chorob_unknown.pdf": "Včasný záchyt chronických jaterních chorob_2025.pdf",
    "Virová hepatitida C_unknown.pdf": "Virová hepatitida C_2023.pdf",  # title page: NOVELIZACE 2023 (CreationDate 2025 = re-export)
    "Vybraná onkologická onemocnění_unknown.pdf": "Vybraná onkologická onemocnění_2023.pdf",
}


@dataclass
class RenamePlan:
    to_rename: list[tuple[str, str]] = field(default_factory=list)  # (old, new) — `_unknown` present in store
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
    """Classify each frozen rename against the file_paths actually in the store. Idempotent: once a doc
    carries its `_year` name, it lands in ``already_done`` and the runner skips it."""
    live = set(live_file_paths)
    plan = RenamePlan()
    for old, new in RENAMES.items():
        if old in live:
            plan.to_rename.append((old, new))
        elif new in live:
            plan.already_done.append(new)
        else:
            plan.absent.append(old)
    return plan
