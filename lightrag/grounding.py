"""Extract-time ``concept_ref`` grounding — context-LLM disambiguation over mkn10 neural-search.

Phase 1 of the typed-edges contract (spec 008). mkn10 owns the vocabulary; the guidelines
ingest LLM owns the document context. Per **clinical** entity:

1. route by ``node.type`` — ``drug``/``medication`` search mkn10 ``domain=drug`` (a drug searched
   in ``domain=mkn10`` returns the ``Otrava léčivy – X`` poisoning code — routing kills that class);
2. pull top-K candidates from mkn10 neural-search (the answer is in top-K but often not #1);
3. the ingest LLM picks the candidate ``code`` that fits THIS document, or abstains (``[]``).
   Selection is constrained to the offered candidate set — the LLM cannot emit a code it was not
   shown (no hallucination). ``score_fused`` is NOT a usable confidence, so it is not thresholded.

The live LLM (``llm_func``) and HTTP (``api``) calls are injected, so the core is unit-testable
without an LLM or a live mkn10. Wiring this into the real ``extract_entities`` path (+ writing
``concept_ref`` onto graph nodes + ``resolve_cache.jsonl``) is deferred to the combined Phase 0+1+2
full-corpus run; here it is exercised probe-first (``scratch/probe_phase1_grounding.py``).
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode

# Canonical coding-system URIs (authoritative: docs/research/fhir-identity-coding-standard-2026-06.md;
# mkn10 uses the ÚZIS terminology URI, NOT the HL7 `.../sid/icd-10`).
MKN10_SYSTEM = "https://uzis.cz/terminology/CodeSystem/mkn-10"
ATC_SYSTEM = "http://www.whocc.no/atc"

_DRUG_TYPES = {"drug", "medication"}
_SYSTEM_BY_DOMAIN = {"mkn10": MKN10_SYSTEM, "drug": ATC_SYSTEM}

# neural-search sits behind Cloudflare, which 1010-blocks the default urllib User-Agent.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# api: (url, headers) -> parsed JSON dict. Injected so tests need no network.
HttpGetJson = Callable[[str, dict], Awaitable[dict]]
# llm_func: (prompt) -> completion text. Injected so tests need no LLM.
LlmFunc = Callable[[str], Awaitable[str]]


async def _default_http_get_json(url: str, headers: dict) -> dict:
    """Blocking urllib GET off the event loop; returns parsed JSON."""

    def _do() -> dict:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed base_url)
            return json.load(resp)

    return await asyncio.to_thread(_do)


def route_domain(node_type: Optional[str]) -> str:
    """``drug``/``medication`` (case-insensitive) → ``"drug"``; everything else → ``"mkn10"``.

    Load-bearing: routing a drug to ``domain=drug`` avoids the poisoning-code class that a drug
    name resolves to in ``domain=mkn10``.
    """
    return "drug" if (node_type or "").strip().lower() in _DRUG_TYPES else "mkn10"


async def neural_search_candidates(
    name: str,
    domain: str,
    *,
    base_url: str,
    api: HttpGetJson = _default_http_get_json,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """mkn10 ``GET /v1/codes/neural-search`` → a list of ``{code, display, score, system}``.

    ``api`` is the injected HTTP fetch. The candidate ``system`` is derived from ``domain`` so a
    downstream ``concept_ref`` is already system-tagged.
    """
    url = (
        base_url.rstrip("/")
        + "/v1/codes/neural-search?"
        + urlencode({"q": name, "domain": domain, "limit": limit})
    )
    payload = await api(url, {"User-Agent": _BROWSER_UA, "Accept": "application/json"})
    system = _SYSTEM_BY_DOMAIN.get(domain, MKN10_SYSTEM)
    out: list[dict[str, Any]] = []
    for c in payload.get("results", []) or []:
        code = c.get("code") or c.get("atc5")
        if not code:
            continue
        out.append(
            {
                "code": code,
                "display": c.get("name_cs") or c.get("inn") or c.get("display") or "",
                "score": c.get("score_fused"),
                "system": system,
            }
        )
    return out


def build_grounding_prompt(
    name: str,
    node_type: str,
    description: str,
    candidates: list[dict[str, Any]],
    doc_context: str,
) -> str:
    """The disambiguation prompt: pick the one candidate code that fits THIS document, or NONE."""
    listed = "\n".join(
        f"{i + 1}. {c['code']} — {c.get('display', '')}"
        for i, c in enumerate(candidates)
    )
    return (
        "Jsi klinický kodér. Z nabídnutých kandidátů vyber JEDEN kód, který přesně odpovídá "
        "této entitě v kontextu dokumentu.\n\n"
        f'Entita: "{name}" (typ: {node_type})\n'
        f"Popis: {description}\n\n"
        f"Kontext dokumentu:\n{doc_context}\n\n"
        f"Kandidáti:\n{listed}\n\n"
        'Odpověz POUZE kódem právě jednoho kandidáta ze seznamu (např. "I10"). Pokud žádný '
        'kandidát entitě v tomto kontextu neodpovídá, odpověz "NONE". Nevymýšlej kódy mimo seznam.'
    )


def parse_concept_ref(
    llm_text: str, candidates: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Parse the LLM's choice into a ``concept_ref`` list, accepting ONLY an offered code.

    Returns the first candidate whose ``code`` appears as a standalone token in the response
    (longest codes first, so ``F32.0`` wins over a bare ``F32``); ``NONE``/no match → ``[]``.
    """
    text = llm_text or ""
    for c in sorted(candidates, key=lambda x: len(x.get("code", "")), reverse=True):
        code = c.get("code")
        if not code:
            continue
        # standalone token — a '.' or word char on either side is part of a longer code
        if re.search(rf"(?<![\w.]){re.escape(code)}(?![\w.])", text, re.IGNORECASE):
            return [
                {"system": c["system"], "code": code, "display": c.get("display", "")}
            ]
    return []


async def ground_entity(
    entity: dict[str, Any],
    doc_context: str,
    *,
    llm_func: LlmFunc,
    neural_base: str,
    api: HttpGetJson = _default_http_get_json,
    limit: int = 4,
) -> list[dict[str, str]]:
    """Ground one entity → a ``concept_ref`` list (or ``[]`` on abstain / no candidates).

    ``entity`` accepts either extraction (``entity_name``/``entity_type``) or graph
    (``name``/``type``) field names.
    """
    name = entity.get("name") or entity.get("entity_name") or ""
    node_type = entity.get("type") or entity.get("entity_type") or ""
    description = entity.get("description") or ""

    domain = route_domain(node_type)
    candidates = await neural_search_candidates(
        name, domain, base_url=neural_base, api=api, limit=limit
    )
    if not candidates:
        return []  # nothing to pick from — abstain without spending an LLM call
    prompt = build_grounding_prompt(
        name, node_type, description, candidates, doc_context
    )
    resp = await llm_func(prompt)
    return parse_concept_ref(resp, candidates)
