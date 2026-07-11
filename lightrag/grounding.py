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
without an LLM or a live mkn10. The extract-path wiring (spec 009) calls ``ground_entity_cached``
from ``_merge_nodes_then_upsert`` once per unique clinical entity, cache-first via
``resolve_cache.jsonl``; it is also exercised probe-first (``scratch/probe_phase1_grounding.py``).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Canonical coding-system URIs (authoritative: docs/research/fhir-identity-coding-standard-2026-06.md;
# mkn10 uses the ÚZIS terminology URI, NOT the HL7 `.../sid/icd-10`).
MKN10_SYSTEM = "https://uzis.cz/terminology/CodeSystem/mkn-10"
ATC_SYSTEM = "http://www.whocc.no/atc"

_DRUG_TYPES = {"drug", "medication"}
_SYSTEM_BY_DOMAIN = {"mkn10": MKN10_SYSTEM, "drug": ATC_SYSTEM}

# Only these entity types are grounded. route_domain maps everything-not-drug to "mkn10", so it
# CANNOT be used as the clinical gate (it would ground person/organization/other/table/… too).
_CLINICAL_TYPES = {
    "drug",
    "medication",
    "condition",
    "diagnosis",
    "symptom",
    "procedure",
    "labtest",
}


def is_clinical_type(node_type: Optional[str]) -> bool:
    """True for the entity types worth grounding (drugs + the mkn10-codeable clinical set)."""
    return (node_type or "").strip().lower() in _CLINICAL_TYPES

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
        # standalone token: a leading '.'/word char means we're inside a longer code, but a
        # TRAILING '.' is a sentence period ("Kód je F32.0.") — only a trailing word char
        # (e.g. "F32" inside "F320") is a real code continuation.
        if re.search(rf"(?<![\w.]){re.escape(code)}(?![\w])", text, re.IGNORECASE):
            return [
                {"system": c["system"], "code": code, "display": c.get("display", "")}
            ]
    return []


# --- verify-or-abstain (spec 010): the pick's mirror — a context judge keeps or drops the picked code.
# The spine guard is existence-only and cannot catch a VALID-but-wrong-context code (a drug class grounded
# to a specific drug, a symptom grounded to a diagnosis, a procedure grounded to a real-but-wrong Z-code).
# Verifiable-AI: the grounding LLM is not the last writer — verify before the concept_ref is written.


def build_verify_prompt(
    name: str,
    node_type: str,
    description: str,
    ref: dict[str, str],
    doc_context: str,
) -> str:
    """The judge prompt: does the picked code correctly represent THIS entity in context?"""
    return (
        "Jsi klinický kodér-auditor. Ověř, zda přiřazený kód SPRÁVNĚ reprezentuje entitu "
        "v kontextu klinického doporučeného postupu.\n\n"
        f'Entita: "{name}" (typ: {node_type})\n'
        f"Popis: {description}\n"
        f"Kontext: {doc_context}\n"
        f"Přiřazený kód: {ref.get('code', '')} — {ref.get('display', '')}\n\n"
        "Zvaž: Odpovídá kód klinickému významu entity? NENÍ to validní kód ze ŠPATNÉ kategorie "
        "(homonym / jiný koncept, který náhodou existuje)? NENÍ entita léčebná metoda / výkon / "
        "vyšetření, kterému MKN-10 diagnostický kód nepřísluší?\n\n"
        "Odpověz PŘESNĚ jedním řádkem: `KEEP | důvod`  nebo  `DROP | důvod`."
    )


def parse_verdict(llm_text: str) -> bool:
    """``True`` = KEEP, ``False`` = DROP. Scans for the first line starting KEEP/DROP (so a preamble
    line before the verdict doesn't misread); no clear verdict ⇒ ``False`` (abstain-on-uncertainty)."""
    for line in (llm_text or "").splitlines():
        s = line.strip().upper()
        if s.startswith("KEEP"):
            return True
        if s.startswith("DROP"):
            return False
    return False


async def verify_concept_ref(
    entity: dict[str, Any],
    ref: dict[str, str],
    doc_context: str,
    *,
    verify_llm_func: LlmFunc,
) -> bool:
    """One judge call for a picked ``concept_ref``. ``True`` = keep, ``False`` = drop."""
    name = entity.get("name") or entity.get("entity_name") or ""
    node_type = entity.get("type") or entity.get("entity_type") or ""
    description = entity.get("description") or ""
    prompt = build_verify_prompt(name, node_type, description, ref, doc_context)
    resp = await verify_llm_func(prompt)
    return parse_verdict(resp)


async def ground_entity(
    entity: dict[str, Any],
    doc_context: str,
    *,
    llm_func: LlmFunc,
    neural_base: str,
    api: HttpGetJson = _default_http_get_json,
    limit: int = 4,
    verify_llm_func: Optional[LlmFunc] = None,
) -> list[dict[str, str]]:
    """Ground one entity → a ``concept_ref`` list (or ``[]`` on abstain / no candidates).

    ``entity`` accepts either extraction (``entity_name``/``entity_type``) or graph
    (``name``/``type``) field names. When ``verify_llm_func`` is given, the picked code is judged
    (verify-or-abstain, spec 010) and dropped ⇒ ``[]`` unless it survives; a judge error also abstains.
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
    refs = parse_concept_ref(resp, candidates)

    if refs and verify_llm_func is not None:
        try:
            if not await verify_concept_ref(
                entity, refs[0], doc_context, verify_llm_func=verify_llm_func
            ):
                return []  # judge dropped it — abstain (verify-or-abstain)
        except Exception as e:
            # judge failure ⇒ abstain, never write an unverified code. Log it: a systematically
            # misconfigured judge (bad model/key) would otherwise silently zero-drop every code.
            logger.warning("concept_ref verify judge failed for '%s' (abstaining): %s", name, e)
            return []
    return refs


# --- resolve cache (spec 009): cache-first so re-runs skip the LLM + neural-search ------------


def resolve_cache_key(
    name: str, node_type: str, description: str, verified: bool = False
) -> str:
    """Stable key over ``name|type|description`` (whitespace-collapsed, lowercased), discriminated by
    whether the result was verified (spec 010). A pre-verify (spec 009) cache entry therefore has a
    DIFFERENT key than a verify-on lookup, so an unverified code can never be served past the judge."""
    norm = "|".join(
        " ".join((part or "").split()).lower()
        for part in (name, node_type, description)
    )
    if verified:
        norm += "|v"
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def load_resolve_cache(path: str) -> dict[str, list[dict[str, str]]]:
    """Read a JSONL ``{key, concept_ref}`` cache. Missing file ⇒ ``{}``; a corrupt line is skipped.

    Best-effort: the cache is an optimisation, never a correctness dependency — a malformed line
    (partial write, hand-edit) must not abort a grounding run.
    """
    cache: dict[str, list[dict[str, str]]] = {}
    p = Path(path)
    if not p.exists():
        return cache
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            cache[rec["key"]] = rec["concept_ref"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return cache


def append_resolve_cache(path: str, key: str, refs: list[dict[str, str]]) -> None:
    """Append one ``{key, concept_ref}`` line (creating parent dirs if needed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "concept_ref": refs}, ensure_ascii=False) + "\n")


async def ground_entity_cached(
    entity: dict[str, Any],
    doc_context: str,
    *,
    cache: dict[str, list[dict[str, str]]],
    cache_path: str,
    llm_func: LlmFunc,
    neural_base: str,
    api: HttpGetJson = _default_http_get_json,
    limit: int = 4,
    verify_llm_func: Optional[LlmFunc] = None,
) -> list[dict[str, str]]:
    """Cache-first ``ground_entity`` (pick + optional verify, spec 010). A hit returns the cached
    (verified) ``concept_ref`` with NO LLM/HTTP call; a miss grounds + verifies, updates the in-run
    ``cache`` dict, and appends to ``cache_path``. The cached value is the VERIFIED result.

    Abstains (``[]``) are cached too — an entity that failed to ground/verify once should not re-spend the
    LLM/mkn10 on the same ``(name, type, description)`` within/across runs.
    """
    name = entity.get("name") or entity.get("entity_name") or ""
    node_type = entity.get("type") or entity.get("entity_type") or ""
    description = entity.get("description") or ""
    key = resolve_cache_key(
        name, node_type, description, verified=verify_llm_func is not None
    )
    if key in cache:
        return cache[key]
    refs = await ground_entity(
        entity,
        doc_context,
        llm_func=llm_func,
        neural_base=neural_base,
        api=api,
        limit=limit,
        verify_llm_func=verify_llm_func,
    )
    cache[key] = refs
    # off the event loop — the write is small but the batch does thousands of them
    await asyncio.to_thread(append_resolve_cache, cache_path, key, refs)
    return refs
