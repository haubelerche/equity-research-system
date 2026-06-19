from __future__ import annotations

from scripts.validate_report_display_fields import (
    _headline_target_reasonableness_failures,
    _normalize,
    _field_has_value,
    REQUIRED_FIELDS,
    PERCENT_RE,
)


def _has(label: str, text: str) -> bool:
    fields = dict(REQUIRED_FIELDS)
    return _field_has_value(_normalize(text), label, fields[label])


def test_required_snapshot_fields_accept_numeric_values():
    text = """
    Gia muc tieu (VND) 95,486
    Gia hien tai (VND) 93,700
    Ty le tang/giam +1.9%
    Tong ty suat loi nhuan +6.7%
    Gia dong cua 93,700
    Gia cao/thap 52 tuan 91,860 / 104,600
    Von hoa 12,251
    So luong co phieu 131
    KLGD binh quan 30 phien 16,413
    """

    assert all(_has(label, text) for label, _pattern in REQUIRED_FIELDS)


def test_required_snapshot_fields_reject_dash_before_value():
    text = "Gia muc tieu — VND | Gia muc tieu (VND/co phieu) 10,949 | Tiem nang tang/giam — | Gia hien tai 3,800"

    assert not _has("gia muc tieu", text)
    assert not _field_has_value(_normalize(text), "tiem nang tang/giam", PERCENT_RE)


def test_headline_target_reasonableness_accepts_market_near_target():
    text = _normalize("Gia muc tieu 95,000 VND | Gia hien tai 93,400 VND")

    assert _headline_target_reasonableness_failures(text) == ()


def test_headline_target_reasonableness_rejects_extreme_downside():
    text = _normalize("Gia muc tieu 30 VND | Gia hien tai 1,500 VND")

    assert _headline_target_reasonableness_failures(text) == (
        "headline_target_below_market_band",
    )


def test_headline_target_reasonableness_rejects_extreme_upside():
    text = _normalize("Gia muc tieu 321,000 VND | Gia hien tai 100,000 VND")

    assert _headline_target_reasonableness_failures(text) == (
        "headline_target_above_market_band",
    )
