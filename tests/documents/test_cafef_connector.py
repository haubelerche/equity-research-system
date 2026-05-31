"""Tests for CafeF Tier 2 structured financial data connector."""
from __future__ import annotations

import json

import pytest

from backend.documents.connectors.cafef_connector import (
    CAFEF_METRIC_MAP,
    CafeFinanceConnector,
)
from backend.documents.connectors.base import StructuredFinancialRow

# ---------------------------------------------------------------------------
# Synthetic mock payloads (realistic DHG-scale numbers)
# ---------------------------------------------------------------------------

_INCOME_RESPONSE = {
    "Data": [{
        "Ticker": "DHG", "YearPeriod": "2024/4",
        "DoanhThuThuanBanHangVaCungCapDichVu": 4_500_000_000_000.0,
        "LoiNhuanGop": 2_000_000_000_000.0,
        "LoiNhuanSauThue": 850_000_000_000.0,
        "LaiCoSoBanToanBo": 6300.0,  # VND/share — must NOT be divided
    }]
}

_BALANCE_RESPONSE = {
    "Data": [{
        "Ticker": "DHG", "YearPeriod": "2024/4",
        "TongTaiSan": 5_000_000_000_000.0,
        "VonChuSoHuu": 4_100_000_000_000.0,
    }]
}

_CASHFLOW_RESPONSE = {
    "Data": [{
        "Ticker": "DHG", "YearPeriod": "2024/4",
        "LuuChuyenTienThuanTuHoatDongKinhDoanh": 900_000_000_000.0,
        "MuaSamTaiSanCoDinh": -300_000_000_000.0,
    }]
}


def _mock_http(response_map: dict):
    """Return a mock http_get function that routes by URL substring."""
    def get(url, **kwargs):
        for key, val in response_map.items():
            if key in url:
                return json.dumps(val)
        return json.dumps({"Data": []})
    return get


_ALL_MOCKS = {
    "type=1": _INCOME_RESPONSE,
    "type=2": _BALANCE_RESPONSE,
    "type=3": _CASHFLOW_RESPONSE,
}


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestCafeFinanceConnector:

    def _fetch_all(self, fiscal_year: int = 2024) -> list[StructuredFinancialRow]:
        connector = CafeFinanceConnector()
        return connector.fetch("DHG", fiscal_year, http_get=_mock_http(_ALL_MOCKS))

    # 1. Basic shape
    def test_fetch_returns_list_of_structured_rows(self):
        rows = self._fetch_all()
        assert isinstance(rows, list)
        assert len(rows) > 0
        assert all(isinstance(r, StructuredFinancialRow) for r in rows)

    # 2. VND → tỷ VND conversion
    def test_revenue_value_converted_to_vnd_bn(self):
        rows = self._fetch_all()
        revenue_rows = [r for r in rows if r.metric_id == "revenue.net"]
        assert revenue_rows, "Expected at least one revenue.net row"
        r = revenue_rows[0]
        assert abs(r.value - 4500.0) < 0.01, f"Expected ~4500.0, got {r.value}"
        assert r.unit == "vnd_bn"

    # 3. EPS must NOT be divided
    def test_eps_value_not_divided(self):
        rows = self._fetch_all()
        eps_rows = [r for r in rows if r.metric_id == "eps.basic"]
        assert eps_rows, "Expected at least one eps.basic row"
        r = eps_rows[0]
        assert abs(r.value - 6300.0) < 0.01, f"Expected ~6300.0, got {r.value}"
        assert r.unit == "vnd"

    # 4. Tier check
    def test_source_tier_is_2(self):
        rows = self._fetch_all()
        assert all(r.source_tier == 2 for r in rows)

    # 5. api_url must be populated and contain cafef.vn
    def test_api_url_populated(self):
        rows = self._fetch_all()
        for r in rows:
            assert r.api_url, f"api_url is empty for row {r.metric_id}"
            assert "cafef.vn" in r.api_url, f"api_url does not contain 'cafef.vn': {r.api_url}"

    # 6. Wrong YearPeriod must be skipped
    def test_wrong_year_period_skipped(self):
        # Inject a 2023/4 record alongside 2024/4 for income statement
        income_with_old = {
            "Data": [
                {
                    "Ticker": "DHG", "YearPeriod": "2023/4",
                    "DoanhThuThuanBanHangVaCungCapDichVu": 9_999_999_999_999.0,
                },
                {
                    "Ticker": "DHG", "YearPeriod": "2024/4",
                    "DoanhThuThuanBanHangVaCungCapDichVu": 4_500_000_000_000.0,
                },
            ]
        }
        mock = _mock_http({"type=1": income_with_old, "type=2": _BALANCE_RESPONSE, "type=3": _CASHFLOW_RESPONSE})
        connector = CafeFinanceConnector()
        rows = connector.fetch("DHG", 2024, http_get=mock)
        revenue_rows = [r for r in rows if r.metric_id == "revenue.net"]
        # Only the 2024 row should appear
        assert len(revenue_rows) == 1, f"Expected 1 revenue row, got {len(revenue_rows)}"
        assert abs(revenue_rows[0].value - 4500.0) < 0.01

    # 7. Empty data returns empty list
    def test_empty_data_returns_empty_list(self):
        connector = CafeFinanceConnector()
        empty_http = _mock_http({})  # all routes return {"Data": []}
        rows = connector.fetch("DHG", 2024, http_get=empty_http)
        assert rows == []

    # 8. HTTP failure returns empty list (no exception)
    def test_http_failure_returns_empty_list(self):
        def failing_http(url, **kwargs):
            raise ConnectionError("network down")

        connector = CafeFinanceConnector()
        rows = connector.fetch("DHG", 2024, http_get=failing_http)
        assert rows == []

    # 9. CAFEF_METRIC_MAP covers required metrics
    def test_cafef_metric_map_covers_required_metrics(self):
        required = {
            "revenue.net",
            "gross_profit.total",
            "net_income.parent",
            "total_assets.ending",
            "equity.parent",
            "operating_cash_flow.total",
        }
        actual = set(CAFEF_METRIC_MAP.values())
        assert required.issubset(actual), f"Missing from map: {required - actual}"

    # 10. source_name class attribute
    def test_source_name_is_cafef(self):
        assert CafeFinanceConnector.source_name == "cafef"
