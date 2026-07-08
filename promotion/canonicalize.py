"""G5 — deterministic name canonicalization + controlled entity-type enum.

The canonicalization *key* (casefold + strip diacritics + strip punct + collapse
whitespace) is what merges surface variants — `Praktický lékař` and
`Praktický Lékář` share a key, so they become one node. The *display* name keeps
its original form (the deterministic min of the group's variants, or an explicit
alias-table canonical). Both are prerequisites for G3 conflict-keys and G4
stable ids. Vocabulary resolution (concept_ref) stays mkn10's — this only
normalizes surface strings.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

_ENUM_PATH = Path(__file__).parent / "enums" / "entity_types.yaml"
_ALIAS_PATH = Path(__file__).parent / "enums" / "aliases.yaml"
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def load_type_enum(path: str | Path = _ENUM_PATH) -> set[str]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return set(data.get("types", []))


def load_aliases(path: str | Path = _ALIAS_PATH) -> dict[str, str]:
    """Flatten the ``canonical -> [variants]`` table into ``variant -> canonical``."""
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for canonical, variants in (data.get("aliases") or {}).items():
        for v in variants or []:
            out[v] = canonical
    return out


def merge_key(name: str, aliases: dict[str, str] | None = None) -> str:
    if aliases and name in aliases:
        name = aliases[name]
    d = unicodedata.normalize("NFD", name)
    d = "".join(c for c in d if not unicodedata.combining(c)).casefold()
    return _WS.sub(" ", _PUNCT.sub(" ", d)).strip()


def validate_type(type_: str, enum: set[str]) -> str:
    return type_ if type_ in enum else "Other"
