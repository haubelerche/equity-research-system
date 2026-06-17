"""Tests for the CafeF current-price connector (no network — injected http_get)."""
from __future__ import annotations

import json

from backend.documents.connectors import cafef_market_connector as cm

# Representative CafeF PriceHistory.ashx payload (rows newest-first, prices in k VND).
_SAMPLE = json.dumps({
    "Data": {
        "TotalCount": 250,
        "Data": [
            {"Ngay": "25/12/2025", "GiaDongCua": 97.5, "GiaDieuChinh": 97.5, "KhoiLuongKhopLenh": 123456.0},
            {"Ngay": "24/12/2025", "GiaDongCua": 96.0, "GiaDieuChinh": 96.0, "KhoiLuongKhopLenh": 100000.0},
        ],
    }
})


def test_parse_quote_scales_thousand_vnd_and_parses_date():
    q = cm.parse_quote("DHG", _SAMPLE, "url")
    assert q.last_price == 97500.0          # 97.5k VND → 97,500 VND
    assert q.as_of_date == "2025-12-25"     # dd/mm/yyyy → ISO, newest row
    assert q.volume == 123456.0
    assert q.source == "cafef_price_history"


def test_fetch_uses_injected_http_get():
    q = cm.fetch_latest_price("DHG", http_get=lambda url: _SAMPLE)
    assert q.last_price == 97500.0


def test_fetch_never_raises_on_network_error():
    def _boom(url):
        raise OSError("network down")
    q = cm.fetch_latest_price("AGP", http_get=_boom)
    assert q.last_price is None and q.as_of_date is None


def test_parse_empty_or_garbage_returns_none():
    assert cm.parse_quote("X", "not json", "url").last_price is None
    assert cm.parse_quote("X", json.dumps({"Data": {"Data": []}}), "url").last_price is None


def test_adjusted_close_preferred_over_raw():
    payload = json.dumps({"Data": {"Data": [
        {"Ngay": "10/01/2026", "GiaDongCua": 50.0, "GiaDieuChinh": 48.2, "KhoiLuongKhopLenh": 1.0},
    ]}})
    q = cm.parse_quote("DHG", payload, "url")
    assert q.last_price == 48200.0


def test_build_url_contains_symbol():
    assert "Symbol=DHG" in cm.build_url("dhg")


def test_build_url_uses_live_du_lieu_host():
    # The legacy s.cafef.vn handler returns "symbol is null or empty"; the live
    # endpoint moved under cafef.vn/du-lieu/. Lock the working host.
    url = cm.build_url("DHG")
    assert url.startswith("https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx")
    assert "s.cafef.vn" not in url
