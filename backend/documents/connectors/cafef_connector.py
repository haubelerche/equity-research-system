"""CafeF Tier 2 structured financial data connector — Source-Provenance Rebuild.

Fetches Vietnamese BCTC (báo cáo tài chính) data from cafef.vn, which aggregates
official HOSE/HNX exchange filings in machine-readable JSON. This eliminates manual
PDF reading for most numeric extraction use cases.

Endpoint:
    GET https://s.cafef.vn/Ajax/PageNew/DataHistory/FinancialInfo.ashx
        ?Symbol={ticker}&type={1|2|3}&year={yyyy}&Quy=4

    type=1 → KQKD (income statement)
    type=2 → CĐKT (balance sheet)
    type=3 → LCTT (cash flow statement)
    Quy=4  → full-year cumulative (Q4)

Raw values are in đồng. Divide by 1_000_000_000 to get tỷ VND,
EXCEPT per-share metrics (EPS) which are already in VND/share.
"""
from __future__ import annotations

import json
import urllib.request

from backend.documents.connectors.base import StructuredDataConnector, StructuredFinancialRow

_BASE_URL = "https://s.cafef.vn/Ajax/PageNew/DataHistory/FinancialInfo.ashx"

# ---------------------------------------------------------------------------
# Metric mapping: CafeF JSON field → canonical metric_id
# ---------------------------------------------------------------------------

CAFEF_METRIC_MAP: dict[str, str] = {
    # Income statement (type=1)
    "DoanhThuThuanBanHangVaCungCapDichVu": "revenue.net",
    "LoiNhuanGop": "gross_profit.total",
    "LoiNhuanThuanTuHoatDongKinhDoanh": "operating_profit.total",
    "LoiNhuanTruocThue": "profit_before_tax.total",
    "LoiNhuanSauThue": "net_income.parent",
    "LaiCoSoBanToanBo": "eps.basic",
    # Balance sheet (type=2)
    "TongTaiSan": "total_assets.ending",
    "VonChuSoHuu": "equity.parent",
    "VayNganHan": "short_term_debt.ending",
    "VayDaiHan": "long_term_debt.ending",
    "TienVaTuongDuongTien": "cash_and_equivalents.ending",
    # Cash flow statement (type=3)
    "LuuChuyenTienThuanTuHoatDongKinhDoanh": "operating_cash_flow.total",
    "MuaSamTaiSanCoDinh": "capex.total",
    "LuuChuyenTienThuanTuHoatDongDauTu": "investing_cash_flow.total",
    "LuuChuyenTienThuanTuHoatDongTaiChinh": "financing_cash_flow.total",
}

# Metrics that are per-share (VND/share) — must NOT be divided by 1e9
_VND_PER_SHARE_METRICS: frozenset[str] = frozenset({"eps.basic"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _default_http_get(url: str, timeout: int = 20) -> str:
    """Fetch URL with TLS verification ON and a descriptive User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": "maer-cafef/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (TLS verified)
        return resp.read().decode("utf-8", "replace")


def _parse_rows(
    data: list[dict],
    ticker: str,
    fiscal_year: int,
    source_name: str,
) -> list[StructuredFinancialRow]:
    """Parse a list of CafeF data records into StructuredFinancialRow objects.

    Only records whose YearPeriod matches f"{fiscal_year}/4" (full-year) are kept.
    The caller is responsible for setting api_url on each returned row.
    """
    expected_period = f"{fiscal_year}/4"
    rows: list[StructuredFinancialRow] = []

    for record in data:
        if record.get("YearPeriod") != expected_period:
            continue

        for field, metric_id in CAFEF_METRIC_MAP.items():
            raw = record.get(field)
            if raw is None:
                continue

            value = float(raw)

            if metric_id in _VND_PER_SHARE_METRICS:
                unit = "vnd"
            else:
                value = round(value / 1_000_000_000.0, 3)
                unit = "vnd_bn"

            rows.append(StructuredFinancialRow(
                ticker=ticker,
                fiscal_year=fiscal_year,
                metric_id=metric_id,
                value=value,
                unit=unit,
                source_name=source_name,
                source_tier=2,
                raw_label=field,
                api_url="",  # caller fills this in
            ))

    return rows


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class CafeFinanceConnector(StructuredDataConnector):
    """Fetches structured BCTC data from cafef.vn for a given ticker + fiscal year."""

    source_name = "cafef"
    source_tier = 2

    def fetch(
        self,
        ticker: str,
        fiscal_year: int,
        http_get=None,
    ) -> list[StructuredFinancialRow]:
        """Fetch income statement, balance sheet, and cash flow for one ticker/year.

        Args:
            ticker: HOSE/HNX ticker symbol (e.g. "DHG").
            fiscal_year: Four-digit year (e.g. 2024).
            http_get: Optional injectable HTTP getter for testing. If None, uses
                _default_http_get (real network, TLS verified).

        Returns:
            List of StructuredFinancialRow. Empty list on any HTTP failure.
        """
        get = http_get or _default_http_get
        results: list[StructuredFinancialRow] = []

        for stmt_type in (1, 2, 3):
            url = (
                f"{_BASE_URL}"
                f"?Symbol={ticker}&type={stmt_type}&year={fiscal_year}&Quy=4"
            )
            try:
                raw = get(url)
                payload = json.loads(raw)
                data = payload.get("Data") or []
            except Exception:  # noqa: BLE001 — any network/parse error → skip statement
                continue

            rows = _parse_rows(data, ticker, fiscal_year, self.source_name)
            for r in rows:
                r.api_url = url
            results.extend(rows)

        return results
