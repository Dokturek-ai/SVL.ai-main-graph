"""Deterministic page/section suffix on the visible ``### References`` block (spec 017).

The synthesis LLM writes a file-level ``### References`` block (``- [n] <file_path>``); the machine-readable
page/section provenance lives on the enriched ``references[].chunks[]`` (spec 011). This module rewrites that
block **deterministically from the resolved payload** so a clinician reading the answer text sees the page —
without the page number ever entering the LLM prompt (Verifiable-AI: the probabilistic layer is never the last
writer of a citation). The LLM keeps only its *relevance* choice — which references it cited, in what order.

Pure + I/O-free: it operates on the already-enriched ``references`` dicts, so it stays unit-testable without a
store. Best-effort: no ``### References`` block, or no page resolved for any cited reference, returns the response
unchanged (never worse than today's file-level block).
"""

import re

_REF_HEADING = "### References"
_HEADING_RE = re.compile(r"(?m)^###\s+References\s*$")
_ID_RE = re.compile(r"\[(\d+)\]")


def _ordered_unique_ids(block: str) -> list[str]:
    """Reference ids ``[n]`` the LLM listed in its block, first-seen order, deduped — its relevance selection."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _ID_RE.finditer(block):
        rid = m.group(1)
        if rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _pages_for_ref(ref: dict) -> list[int]:
    """Numeric pages across a reference's ``chunks[]`` (``page`` + ``pages``), deduped, ascending.

    Non-numeric / missing pages are dropped (no fabrication) — a reference whose chunks never resolved a page
    yields ``[]`` ⇒ the caller emits a title-only line."""
    pages: set[int] = set()
    for ch in ref.get("chunks") or []:
        if not isinstance(ch, dict):
            continue
        raw = list(ch.get("pages") or [])
        if ch.get("page") is not None:
            raw.append(ch.get("page"))
        for p in raw:
            try:
                pages.add(int(str(p).strip()))
            except (TypeError, ValueError):
                continue
    return sorted(pages)


def _section_for_ref(ref: dict) -> str | None:
    """The section heading-path shared by a reference's cited chunks, or ``None`` when they diverge/absent.

    A single label is only honest when every cited chunk sits under it; mixed sections ⇒ omit rather than pick a
    misleading one."""
    sections = {
        (ch.get("section") or "").strip()
        for ch in (ref.get("chunks") or [])
        if isinstance(ch, dict) and (ch.get("section") or "").strip()
    }
    return next(iter(sections)) if len(sections) == 1 else None


def _format_pages(pages: list[int]) -> str:
    """``[12,13] → "12–13"`` (contiguous run), ``[12,15] → "12, 15"``, ``[29] → "29"``. Assumes sorted+unique."""
    if not pages:
        return ""
    runs: list[list[int]] = [[pages[0]]]
    for p in pages[1:]:
        if p == runs[-1][-1] + 1:
            runs[-1].append(p)
        else:
            runs.append([p])
    parts = [str(r[0]) if len(r) == 1 else f"{r[0]}–{r[-1]}" for r in runs]
    return ", ".join(parts)


def render_reference_block_with_pages(response: str, references: list[dict]) -> str:
    """Rewrite the answer's ``### References`` block with backend-resolved ``s. <page> · <section>`` suffixes.

    Returns ``response`` unchanged when there is no ``### References`` block, or when no cited reference resolved a
    page (nothing to add). The page/section text is assembled solely from ``references[].chunks[]`` — never parsed
    from the response — so the LLM is not the last writer of any page number (spec 017 R5)."""
    if not response or not references:
        return response
    # Anchor on a heading that starts its own line (not an inline "### References" quoted in body prose);
    # take the LAST such heading — the prompt guarantees the real block is last ("nothing after references").
    heads = list(_HEADING_RE.finditer(response))
    if not heads:
        return response
    idx = heads[-1].start()

    # Rebuild only the reference lines from the cited ids; any stray prose the LLM emitted after the block is
    # intentionally normalized away (the synthesis prompt forbids content after the references section).
    head, block = response[:idx], response[idx:]
    ref_by_id = {str(r.get("reference_id")): r for r in references if r.get("reference_id")}

    lines = [_REF_HEADING]
    added_any_page = False
    for rid in _ordered_unique_ids(block):
        ref = ref_by_id.get(rid)
        if not ref:
            continue  # id the LLM cited isn't in the resolved list — drop rather than fabricate a line
        file_path = ref.get("file_path", "")
        pages = _pages_for_ref(ref)
        suffix = ""
        if pages:
            section = _section_for_ref(ref)
            suffix = f" — s. {_format_pages(pages)}" + (f" · {section}" if section else "")
            added_any_page = True
        lines.append(f"- [{rid}] {file_path}{suffix}")

    if not added_any_page:
        return response  # coverage gap across the board — leave today's block untouched
    return head + "\n".join(lines) + "\n"
