import unicodedata

import pytest

from lightrag.promotion.ingest_denylist import denylisted_reason

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "filename",
    [
        "MANUÁL KÓDŮ PRO VPL_unknown.pdf",
        "MANUÁL KÓDŮ PRO VPL_2026.pdf",
        "MANUÁL KÓDŮ PRO VPL.pdf",  # yearless — the `PRO VPL_` scrub key would miss this
        "manuál kódů pro vpl_2026.pdf",  # case-insensitive
        unicodedata.normalize("NFD", "MANUÁL KÓDŮ PRO VPL_2026.pdf"),  # NFD spelling
    ],
)
def test_manual_kodu_is_denylisted(filename):
    assert denylisted_reason(filename) == "PRO VPL"


@pytest.mark.parametrize(
    "filename",
    [
        "Akutní průjem_2023.pdf",
        "Arteriální hypertenze_2024.pdf",
        "Laboratorní metody_2023.pdf",
        "Virová hepatitida C_unknown.pdf",
        "Vybraná onkologická onemocnění_unknown.pdf",
    ],
)
def test_legit_guidelines_pass(filename):
    assert denylisted_reason(filename) is None
