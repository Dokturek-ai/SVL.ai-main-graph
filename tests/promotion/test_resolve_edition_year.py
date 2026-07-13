import sys
from pathlib import Path

import pytest

from lightrag.promotion.edition_resolve import resolve_edition_year

pytestmark = pytest.mark.offline


class _FakePage:
    def __init__(self, text):
        self._text = text

    def get_text(self):
        return self._text


class _FakeDoc:
    def __init__(self, pages, metadata):
        self._pages = [_FakePage(p) for p in pages]
        self.metadata = metadata
        self.page_count = len(pages)

    def __getitem__(self, i):
        return self._pages[i]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeFitz:
    def __init__(self, doc):
        self._doc = doc

    def open(self, _path):
        return self._doc


def _patch_fitz(monkeypatch, pages, metadata):
    monkeypatch.setitem(sys.modules, "fitz", _FakeFitz(_FakeDoc(pages, metadata)))


def test_filename_year_wins_without_scanning(monkeypatch):
    # no fitz installed in sys.modules → if it tried to scan it would ImportError; it must not
    monkeypatch.setitem(sys.modules, "fitz", None)
    assert resolve_edition_year(Path("Arteriální hypertenze_2024.pdf")) == ("2024", "filename")


def test_title_novelizace_beats_creationdate(monkeypatch):
    # the hepatitida case: title says NOVELIZACE 2023, CreationDate is a 2025 re-export
    _patch_fitz(
        monkeypatch,
        pages=["VIROVÁ HEPATITIDA C\nNOVELIZACE 2023", "body"],
        metadata={"creationDate": "D:20251022174451+02'00'"},
    )
    assert resolve_edition_year(Path("Virová hepatitida C_unknown.pdf")) == ("2023", "title")


def test_creationdate_fallback_when_no_title_year(monkeypatch):
    _patch_fitz(
        monkeypatch,
        pages=["Akutní průjem\nDoporučený postup", "body"],
        metadata={"creationDate": "D:20231209144329+01'00'"},
    )
    assert resolve_edition_year(Path("Akutní průjem_unknown.pdf")) == ("2023", "creationdate")


def test_none_when_nothing_resolves(monkeypatch):
    _patch_fitz(monkeypatch, pages=["no year anywhere"], metadata={})
    assert resolve_edition_year(Path("Bolesti hlavy_unknown.pdf")) is None


def test_bare_citation_year_on_title_is_ignored(monkeypatch):
    # a title page citing "... 2019 ..." without NOVELIZACE must NOT be grabbed; fall to CreationDate
    _patch_fitz(
        monkeypatch,
        pages=["Odkaz na doporučení z roku 2019", "body"],
        metadata={"creationDate": "D:20240125142609+01'00'"},
    )
    assert resolve_edition_year(Path("CTEPD_unknown.pdf")) == ("2024", "creationdate")


def test_non_pdf_without_filename_year_returns_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "fitz", None)
    assert resolve_edition_year(Path("Nějaký soubor.txt")) is None
