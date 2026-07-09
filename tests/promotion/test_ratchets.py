import pytest

from lightrag.promotion.ratchets import check
from lightrag.promotion.types import Manifest


def _m(**counts) -> Manifest:
    base = {"quarantined": 3, "anchor_coverage": 1.0, "orphan_rate": 0.25, "doc_coverage": 1.0}
    base.update(counts)
    return Manifest(content_hash="x", corpus=[], pins={}, counts=base)


@pytest.mark.offline
def test_stable_manifest_holds_the_ratchets():
    assert check(_m(), _m()) == []


@pytest.mark.offline
def test_each_regression_trips_a_ratchet():
    prev = _m()
    assert any("quarantined" in v for v in check(prev, _m(quarantined=5)))
    assert any("orphan_rate" in v for v in check(prev, _m(orphan_rate=0.4)))
    assert any("doc_coverage" in v for v in check(prev, _m(doc_coverage=0.5)))
    assert any("anchor_coverage" in v for v in check(prev, _m(anchor_coverage=0.9)))


@pytest.mark.offline
def test_improvements_do_not_trip():
    prev = _m()
    assert check(prev, _m(quarantined=1, orphan_rate=0.1)) == []
