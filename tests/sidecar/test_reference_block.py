"""Spec 017 — deterministic page/section suffix on the visible ``### References`` block.

Pure-function tests over hand-built ``references`` dicts mirroring the spec-011 enriched shape
(``references[].chunks[]`` with ``page``/``pages``/``section``). No store, no network.
"""

from lightrag.sidecar.reference_block import (
    _format_pages,
    render_reference_block_with_pages,
)


def _ref(reference_id, file_path, chunks):
    return {"reference_id": reference_id, "file_path": file_path, "chunks": chunks}


def _answer(block_lines):
    return "Léčba EM je doxycyklin.\n\n### References\n" + "\n".join(block_lines) + "\n"


def test_rewrite_with_page():
    resp = _answer(["- [1] borrelioza_2018.pdf"])
    refs = [_ref("1", "borrelioza_2018.pdf", [{"page": "29"}])]
    out = render_reference_block_with_pages(resp, refs)
    assert "- [1] borrelioza_2018.pdf — s. 29" in out
    assert out.startswith("Léčba EM je doxycyklin.")


def test_section_appended_when_shared():
    resp = _answer(["- [1] doc.pdf"])
    refs = [
        _ref("1", "doc.pdf", [
            {"page": "29", "section": "Léčba › EM"},
            {"page": "29", "section": "Léčba › EM"},
        ])
    ]
    out = render_reference_block_with_pages(resp, refs)
    assert "- [1] doc.pdf — s. 29 · Léčba › EM" in out


def test_section_omitted_when_divergent():
    resp = _answer(["- [1] doc.pdf"])
    refs = [
        _ref("1", "doc.pdf", [
            {"page": "29", "section": "Léčba › EM"},
            {"page": "30", "section": "Diagnostika"},
        ])
    ]
    out = render_reference_block_with_pages(resp, refs)
    assert "- [1] doc.pdf — s. 29–30" in out
    assert "·" not in out.split("### References")[1]


def test_multipage_contiguous_and_gapped_and_dedupe():
    assert _format_pages([12, 13]) == "12–13"
    assert _format_pages([12, 15]) == "12, 15"
    assert _format_pages([29]) == "29"
    assert _format_pages([12, 13, 15, 16, 17]) == "12–13, 15–17"
    resp = _answer(["- [1] doc.pdf"])
    refs = [_ref("1", "doc.pdf", [{"page": "29"}, {"pages": ["29", "30"]}])]
    out = render_reference_block_with_pages(resp, refs)
    assert "- [1] doc.pdf — s. 29–30" in out


def test_coverage_gap_title_only():
    # ref has chunks but none resolved a page -> title only, no fabricated "s."
    resp = _answer(["- [1] doc.pdf"])
    refs = [_ref("1", "doc.pdf", [{"page": None, "pages": None, "text": "…"}])]
    out = render_reference_block_with_pages(resp, refs)
    assert out == resp  # whole-block no-op when nothing resolved


def test_mixed_coverage_one_resolves():
    # [1] resolves a page, [2] does not -> [1] gets suffix, [2] stays title-only
    resp = _answer(["- [1] a.pdf", "- [2] b.pdf"])
    refs = [
        _ref("1", "a.pdf", [{"page": "5"}]),
        _ref("2", "b.pdf", [{"page": None}]),
    ]
    out = render_reference_block_with_pages(resp, refs)
    tail = out.split("### References")[1]
    assert "- [1] a.pdf — s. 5" in tail
    assert "- [2] b.pdf\n" in tail
    assert "s." not in tail.split("- [2]")[1]


def test_no_references_block():
    resp = "Odpověď bez sekce referencí."
    refs = [_ref("1", "doc.pdf", [{"page": "29"}])]
    assert render_reference_block_with_pages(resp, refs) == resp


def test_no_page_data_noop():
    resp = _answer(["- [1] doc.pdf"])
    refs = [{"reference_id": "1", "file_path": "doc.pdf"}]  # no chunks at all
    assert render_reference_block_with_pages(resp, refs) == resp


def test_llm_not_last_writer_page_from_payload():
    # LLM typed a WRONG page into its block text; payload page must win (backend is the writer).
    resp = _answer(["- [1] doc.pdf str. 999"])
    refs = [_ref("1", "doc.pdf", [{"page": "29"}])]
    out = render_reference_block_with_pages(resp, refs)
    tail = out.split("### References")[1]
    assert "s. 29" in tail
    assert "999" not in tail


def test_multi_ref_order_preserved():
    # block cites [2] before [1] -> output keeps LLM's order
    resp = _answer(["- [2] b.pdf", "- [1] a.pdf"])
    refs = [
        _ref("1", "a.pdf", [{"page": "3"}]),
        _ref("2", "b.pdf", [{"page": "8"}]),
    ]
    out = render_reference_block_with_pages(resp, refs)
    tail = out.split("### References")[1]
    assert tail.index("[2]") < tail.index("[1]")


def test_inline_heading_in_body_prose_not_split():
    # A "### References" quoted inside body prose must NOT be treated as the block; only the real,
    # line-anchored heading (last one) is rewritten. Guards against corrupting the answer body.
    resp = (
        "Doporučení viz ### References sekce originálu.\n\n"
        "Léčba je doxycyklin.\n\n"
        "### References\n- [1] doc.pdf\n"
    )
    refs = [_ref("1", "doc.pdf", [{"page": "29"}])]
    out = render_reference_block_with_pages(resp, refs)
    assert "Doporučení viz ### References sekce originálu." in out  # prose untouched
    assert out.count("### References") == 2  # the inline mention survives, real heading kept once
    assert "- [1] doc.pdf — s. 29" in out


def test_int_reference_id_matches():
    # enrichment contract is string ids, but pin int coercion so a future int id still joins the [n] token.
    resp = _answer(["- [1] doc.pdf"])
    refs = [{"reference_id": 1, "file_path": "doc.pdf", "chunks": [{"page": "29"}]}]
    out = render_reference_block_with_pages(resp, refs)
    assert "- [1] doc.pdf — s. 29" in out


def test_id_not_in_references_dropped():
    # LLM cites [3] which isn't in the resolved list -> dropped, not fabricated
    resp = _answer(["- [1] a.pdf", "- [3] ghost.pdf"])
    refs = [_ref("1", "a.pdf", [{"page": "3"}])]
    out = render_reference_block_with_pages(resp, refs)
    tail = out.split("### References")[1]
    assert "[1] a.pdf — s. 3" in tail
    assert "[3]" not in tail
    assert "ghost" not in tail
