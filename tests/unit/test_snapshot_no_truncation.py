"""The cover (snapshot) page must not truncate narrative content.

Previously the investment thesis / business update / growth drivers were cut to
fixed character budgets (1050/900/700) to squeeze the report into a page budget.
The report has no page limit, so the full narrative must render.
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.reporting.client_report_view_model import TableData
from backend.reporting import client_section_builder as csb


_LONG_THESIS = (
    "Mở đầu luận điểm. "
    + ("Câu phân tích chi tiết về triển vọng doanh nghiệp. " * 60)
    + "KẾT-LUẬN-DUY-NHẤT-CUỐI-CÙNG."
)


def _vm() -> SimpleNamespace:
    empty_table = TableData(title="", periods=[], rows=[])
    return SimpleNamespace(
        ticker="DHG",
        company_name="Dược Hậu Giang",
        exchange="HOSE",
        sector="Dược phẩm",
        report_date="2026-06-13",
        recommendation="NẮM GIỮ",
        target_price=SimpleNamespace(amount=106_752.0),
        current_price=SimpleNamespace(amount=93_700.0),
        upside_downside=SimpleNamespace(value=0.139),
        total_return=SimpleNamespace(value=0.139),
        market_statistics={},
        trading_performance_table=empty_table,
        charts={},
        investment_thesis=_LONG_THESIS,
        latest_business_update=_LONG_THESIS,
        key_growth_drivers=_LONG_THESIS,
    )


def test_snapshot_renders_full_investment_thesis_without_truncation() -> None:
    html = csb._snapshot_page(_vm())

    assert "KẾT-LUẬN-DUY-NHẤT-CUỐI-CÙNG." in html
