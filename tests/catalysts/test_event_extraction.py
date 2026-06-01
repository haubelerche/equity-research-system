"""Phase 5 — catalyst event extraction & validation rules."""
from __future__ import annotations

from backend.catalysts.event_extractor import (
    CatalystEvent,
    extract_events,
    validate_event,
)
from backend.catalysts.ticker_mapper import map_event_to_ticker


def _good_event(**over) -> CatalystEvent:
    base = dict(
        event_title="DHG công bố KQKD Q4/2025",
        event_type="earnings_explanation",
        source_document_id=10,
        published_date="2026-01-20",
        evidence_quote="Doanh thu Q4 đạt ...",
        ticker="DHG",
        ticker_mapping_level="explicit",
    )
    base.update(over)
    return CatalystEvent(**base)


def test_valid_event_passes():
    assert validate_event(_good_event()).valid


# 4. Catalyst event requires source_document_id
def test_event_requires_source_document_id():
    out = validate_event(_good_event(source_document_id=None))
    assert not out.valid
    assert any("source_document_id" in r for r in out.reasons)


# 5. Catalyst event without evidence_quote/evidence_span is invalid
def test_event_requires_evidence():
    out = validate_event(_good_event(evidence_quote=None, evidence_span=None))
    assert not out.valid
    assert any("evidence" in r for r in out.reasons)


# 6. Unknown event_type is rejected
def test_unknown_event_type_rejected():
    out = validate_event(_good_event(event_type="random_made_up_type"))
    assert not out.valid
    assert any("event_type" in r for r in out.reasons)


# 7. Ticker mapping must be explicit or marked sector-level
def test_ticker_mapping_required():
    # explicit but no ticker → invalid
    out = validate_event(_good_event(ticker=None, ticker_mapping_level="explicit"))
    assert not out.valid
    # sector_level with no ticker → valid
    out2 = validate_event(_good_event(ticker=None, ticker_mapping_level="sector_level"))
    assert out2.valid


def test_extract_events_splits_valid_and_rejected():
    candidates = [
        _good_event().to_dict(),
        _good_event(event_type="bogus").to_dict(),
        _good_event(source_document_id=None).to_dict(),
    ]
    valid, rejected = extract_events(candidates)
    assert len(valid) == 1
    assert len(rejected) == 2
    assert all("reasons" in r for r in rejected)


def test_ticker_mapper_explicit_and_sector():
    m1 = map_event_to_ticker("Dược Hậu Giang khánh thành nhà máy", explicit_ticker=None)
    assert m1.ticker == "DHG" and m1.level == "explicit"
    m2 = map_event_to_ticker("Chính sách BHYT mới của ngành dược", explicit_ticker=None)
    assert m2.ticker is None and m2.level == "sector_level"
    m3 = map_event_to_ticker("anything", explicit_ticker="IMP")
    assert m3.ticker == "IMP" and m3.level == "explicit"
