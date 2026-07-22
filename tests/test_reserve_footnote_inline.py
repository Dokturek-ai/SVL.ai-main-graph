"""Unit tests for the reserve-footnote inliner in lightrag/operate.py.

Guards the query-side fix for docs/briefs/2026-07-20-guidelines-em-answer-dropped-dosing-qualifiers.md
(Defect 2, reserve-only hierarchy). In the SVL ATB tables the reserve marker USE ("azitromycin**")
and its LEGEND ("** Pouze pacientům, kteří nemohou užívat …") land in SEPARATE retrieved chunks
(HTML table vs. table footnotes), so the transform is cross-chunk. It folds each marker's legend
back onto every use by pure insertion — abstain-safe (no legend retrieved -> untouched) and never
altering existing characters (doses / loading dose preserved verbatim).

Fragments below are verbatim from a staging /query/data probe (scratch/probe_em_raw_chunk.py):
uses are UNescaped ("azitromycin**"), legends are backslash-ESCAPED ("\\*\\* Pouze …") as MinerU
emits them in the "[Table Footnotes]" prose.
"""

from lightrag.operate import _apply_reserve_legends, _collect_reserve_legends

# Chunk A — the HTML dosing table: bare "**"/"***" marker USES, no legend.
CHUNK_TABLE = (
    "• azitromycin** 1× 500 mg p. o. (10 mg/kg a den*), první den dvojnásobná dávka"
    "• klaritromycin** 2× 500 mg p. o. (7,5 mg/kg a den*)"
    "• doxycyklin*** 200–400 mg denně p. o. (u dětí nad 12 let 4–8 mg/kg a den*)"
)
# Chunk B — the table footnotes: ESCAPED "\*"/"\*\*"/"\*\*\*" LEGENDS, no marker use.
CHUNK_FOOTNOTES = (
    "[Table Footnotes]Poznámky; \\* Dávky pro děti jsou uvedeny v závorkách, maximální "
    "dětské dávky se rovnají běžným dávkám doporučeným pro dospělé.; "
    "\\*\\* Pouze pacientům, kteří nemohou užívat doxycyklin, amoxicilin, cefuroxim axetil "
    "či penicilin.; \\*\\*\\* Zejména při alergii na beta-laktamová antibiotika nebo "
    "nevhodnosti nitrožilní aplikace. Také u periferní parézy n. facialis s normálním "
    "likvorovým nálezem.; Doxycyklin způsobuje fotosenzibilizaci."
)

RESERVE_COND = "Pouze pacientům, kteří nemohou užívat doxycyklin, amoxicilin, cefuroxim axetil či penicilin."
ALLERGY_COND_HEAD = "Zejména při alergii na beta-laktamová antibiotika"


def test_collect_maps_marker_length_to_legend():
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    assert legends[2] == RESERVE_COND
    assert legends[3].startswith(ALLERGY_COND_HEAD)
    # The ubiquitous single "*" (pediatric) is not a reserve marker -> never collected.
    assert 1 not in legends


def test_apply_inlines_reserve_legend_cross_chunk():
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    # ** drugs get the reserve condition inline right after the marker, under a neutral prose label.
    assert f"azitromycin** [podmínka: {RESERVE_COND}]" in out
    assert f"klaritromycin** [podmínka: {RESERVE_COND}]" in out
    # *** drug gets its own (allergy) legend, not the ** one — same neutral label, distinct condition.
    assert "doxycyklin*** [podmínka: " in out
    assert ALLERGY_COND_HEAD in out.split("doxycyklin***")[1]


def test_note_label_is_neutral_prose_not_raw_marker():
    # Regression guard for docs/briefs/2026-07-20-guidelines-em-verbose-loading-dose-and-marker-leak.md
    # residual 2: the raw "[**: …]" sentinel was echoed by the synthesis LLM as a bare "[]**" token
    # with the condition prose dropped ("hvězdičky tam jsou, ale vysvětlení jich ne"). The inserted
    # note must never reuse the raw "**"/"***" as its label.
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    assert "[**:" not in out
    assert "[***:" not in out
    assert "[podmínka:" in out


def test_insertion_only_preserves_dose_text():
    import re

    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    # Pure insertion: stripping the inserted "[podmínka: …]" notes yields the original byte for
    # byte — nothing was deleted or reworded (doses / loading dose provably intact).
    assert re.sub(r" \[podmínka: [^\]]*\]", "", out) == CHUNK_TABLE
    # The load-bearing dose tokens are still present as-is.
    assert "první den dvojnásobná dávka" in out
    assert "500 mg p. o." in out
    assert "200–400 mg denně" in out


def test_pediatric_single_star_untouched():
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    # "(10 mg/kg a den*)" is a single-* pediatric use -> no bracket inserted after it.
    assert "a den*) [" not in out
    assert "a den* [" not in out


def test_abstain_when_legend_not_retrieved():
    # Only the table chunk retrieved (no footnotes) -> no legend -> content unchanged.
    legends = _collect_reserve_legends([CHUNK_TABLE])
    assert legends == {}
    assert _apply_reserve_legends(CHUNK_TABLE, legends) == CHUNK_TABLE


def test_legend_condition_containing_star_keeps_correct_marker_length():
    # A "**" legend whose condition text cross-references a pediatric "4 mg/kg*" dose must stay
    # keyed under 2 (marker length), not be inflated to 3 by the "*" inside the condition.
    fn = "Poznámky; \\*\\* Pouze pokud nelze doxycyklin (u dětí 4 mg/kg a den*).; konec."
    legends = _collect_reserve_legends([fn])
    assert 2 in legends
    assert 3 not in legends
    assert legends[2].startswith("Pouze pokud nelze doxycyklin")


def test_markdown_bold_not_mistaken_for_marker_use():
    # A markdown-bold span must not receive a spurious insertion even when a ** legend exists.
    bold = "Text s **tučným** slovem a další text."
    legends = {2: RESERVE_COND}
    assert _apply_reserve_legends(bold, legends) == bold


def test_noop_without_any_markers():
    legends = _collect_reserve_legends(["doxycyklin 200 mg denně, žádné markery."])
    assert legends == {}
    plain = "amoxicilin 3× 500 mg p. o."
    assert _apply_reserve_legends(plain, {2: RESERVE_COND}) == plain
