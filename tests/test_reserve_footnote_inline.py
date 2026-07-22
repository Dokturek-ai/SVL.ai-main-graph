"""Unit tests for the reserve-footnote inliner in lightrag/operate.py.

Guards the query-side fix for docs/briefs/2026-07-20-guidelines-em-answer-dropped-dosing-qualifiers.md
(Defect 2, reserve-only hierarchy). In the SVL ATB tables the reserve marker USE ("azitromycin**")
and its LEGEND ("** Pouze pacientům, kteří nemohou užívat …") land in SEPARATE retrieved chunks
(HTML table vs. table footnotes), so the transform is cross-chunk. It REPLACES each marker use with a
parenthetical of its verbatim legend (spec 022) — abstain-safe (no legend retrieved -> untouched),
removing only the footnote marker and leaving dose / loading-dose text verbatim.

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
    # ** drugs: the raw marker is REPLACED by a parenthetical of the verbatim reserve condition.
    assert f"azitromycin ({RESERVE_COND})" in out
    assert f"klaritromycin ({RESERVE_COND})" in out
    # *** drug gets its own (allergy) legend, not the ** one — distinct condition, same prose form.
    assert "doxycyklin (" in out
    assert ALLERGY_COND_HEAD in out.split("doxycyklin (")[1]


def test_no_bracket_or_bare_marker_survives():
    # Regression guard for docs/briefs/2026-07-20-guidelines-em-verbose-loading-dose-and-marker-leak.md
    # residual 2 + spec 022: the earlier "[podmínka: …]" sentinel and the raw "**" both leaked verbatim
    # into VERBOSE synthesis ("azitromycin [podmínka: …]**" / "azitromycin [**]"). The transform must
    # leave NO "[" bracket and NO bare reserve marker — only grounded parenthetical prose.
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    # Non-vacuous: reverting _repl to the old sentinel would leave "**" (and "[podmínka:") in out.
    assert "**" not in out  # every "**"/"***" marker consumed (also kills the "[**]" echo source)
    assert "[podmínka:" not in out  # the old bracketed sentinel is gone
    assert RESERVE_COND in out


def test_marker_replacement_preserves_dose_text():
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    # Round-trip proof: swapping each inserted "(legend)" back to its "**"/"***" marker recovers the
    # original byte-for-byte — so the transform changed ONLY the markers, nothing in the dose text.
    restored = out.replace(f" ({legends[2]})", "**").replace(f" ({legends[3]})", "***")
    assert restored == CHUNK_TABLE
    # Spot-check the load-bearing dose tokens are still present verbatim.
    assert "první den dvojnásobná dávka" in out
    assert "500 mg p. o." in out
    assert "200–400 mg denně" in out


def test_pediatric_single_star_untouched():
    legends = _collect_reserve_legends([CHUNK_TABLE, CHUNK_FOOTNOTES])
    out = _apply_reserve_legends(CHUNK_TABLE, legends)
    # "(10 mg/kg a den*)" is a single-* pediatric use -> not a reserve marker, left verbatim (no
    # condition parenthetical glued onto it).
    assert "(10 mg/kg a den*)" in out
    assert "(7,5 mg/kg a den*)" in out


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
