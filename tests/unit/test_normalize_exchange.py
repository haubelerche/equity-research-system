from __future__ import annotations

import pytest

from backend.database.fact_store import normalize_exchange


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("UPCoM", "UPCOM"),   # vnstock casing that violated companies_exchange_check
        ("upcom", "UPCOM"),
        ("UPCOM", "UPCOM"),
        ("HOSE", "HOSE"),
        ("hsx", "HOSE"),       # HOSE alias
        ("HNX", "HNX"),
        ("  hnx  ", "HNX"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_exchange(raw, expected):
    assert normalize_exchange(raw) == expected
