"""G1 — deterministic verify-and-anchor: find a surface form's span in a chunk.

Finding the span *is* the verification, and the found ``(start, end)`` offsets
*become* the anchor (one function closes G1 + G2). Two-stage, tolerant to Czech
inflection (the measured 80.2% exact-locate ceiling was inflection-limited):

1. **normalized substring** — NFD-decompose, drop combining marks, casefold both
   sides; a normalized match maps back to raw offsets via a per-char index map.
2. **stemmed token window** — on miss, match surface tokens to chunk tokens by
   prefix (``srdeční`` ⊂ ``srdečního``); if enough tokens match, the span is the
   window they cover.

No LLM, no semantic judgement — this guarantees *dereferenceability*, not clinical
truth. Below threshold -> ``None`` -> the caller quarantines.
"""

from __future__ import annotations

import re
import unicodedata

from .types import Anchor

_WORD = re.compile(r"\w+", re.UNICODE)
_MIN_PREFIX = 4  # shortest token prefix that may count as a stem match


def _norm_char(ch: str) -> str:
    d = unicodedata.normalize("NFD", ch)
    d = "".join(c for c in d if not unicodedata.combining(c))
    return d.casefold()


def _normalize(text: str) -> str:
    return "".join(_norm_char(c) for c in text)


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized string + ``idx[i]`` = original index of normalized char ``i``."""
    norm: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        for nc in _norm_char(ch):
            norm.append(nc)
            idx.append(i)
    return "".join(norm), idx


def _token_match(a: str, b: str) -> bool:
    if a == b:
        return True
    lo, hi = sorted((a, b), key=len)
    return len(lo) >= _MIN_PREFIX and hi.startswith(lo)


def locate(surface: str, chunk_text: str, chunk_id: str = "", threshold: float = 0.8) -> Anchor | None:
    surface = surface.strip()
    if not surface:
        return None

    # 1. normalized substring
    nmap_str, nmap_idx = _normalize_with_map(chunk_text)
    nsurf = _normalize(surface)
    pos = nmap_str.find(nsurf)
    if pos >= 0 and nsurf:
        start = nmap_idx[pos]
        end = nmap_idx[pos + len(nsurf) - 1] + 1
        match = "exact" if chunk_text[start:end] == surface else "normalized"
        return Anchor(chunk_id=chunk_id, start=start, end=end, match=match)

    # 2. stemmed token window
    surf_tokens = [_normalize(m.group()) for m in _WORD.finditer(surface)]
    surf_tokens = [t for t in surf_tokens if t]
    if not surf_tokens:
        return None
    chunk_tokens = [(_normalize(m.group()), m.start(), m.end()) for m in _WORD.finditer(chunk_text)]

    spans: list[tuple[int, int]] = []
    for st in surf_tokens:
        hit = next(((s, e) for nt, s, e in chunk_tokens if _token_match(st, nt)), None)
        if hit:
            spans.append(hit)
    if spans and len(spans) / len(surf_tokens) >= threshold:
        return Anchor(
            chunk_id=chunk_id,
            start=min(s for s, _ in spans),
            end=max(e for _, e in spans),
            match="stemmed",
        )
    return None
