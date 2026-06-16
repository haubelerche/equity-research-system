"""Regression tests for chart commentary generated from report data."""
from __future__ import annotations

from types import SimpleNamespace

from backend.reporting import client_section_builder as csb
from backend.reporting.client_report_view_model import TableData


def test_chart_takeaway_is_computed_from_period_data_not_static_copy() -> None:
    vm = SimpleNamespace(
        valuation_model_table=TableData(
            title="Mô hình định giá",
            periods=["2024A", "2025A", "2026F"],
            rows=[
                ("Doanh thu thuần", [4_885.0, 5_267.0, 5_700.0]),
                ("Tỷ suất EBITDA", [0.235, 0.218, 0.220]),
                ("Biên lợi nhuận HĐKD / EBIT", [0.205, 0.193, 0.196]),
                ("Biên lợi nhuận gộp", [0.438, 0.466, 0.470]),
                ("Biên lợi nhuận ròng", [0.158, 0.161, 0.165]),
            ],
        ),
        profitability_valuation_table=TableData(
            title="Khả năng sinh lợi",
            periods=["2024A", "2025A", "2026F"],
            rows=[("ROE", [0.190, 0.207, 0.225])],
        ),
    )

    takeaway = csb._chart_takeaway(vm, "C2")

    assert "2025A" in takeaway
    assert "5,267" in takeaway
    assert "+7.8%" in takeaway
    assert "biên EBITDA" in takeaway


def test_chart_takeaway_discloses_insufficient_data_instead_of_fabricating() -> None:
    vm = SimpleNamespace(
        valuation_model_table=TableData(
            title="Mô hình định giá",
            periods=["2025A"],
            rows=[("Doanh thu thuần", [5_267.0])],
        ),
        profitability_valuation_table=TableData(title="Khả năng sinh lợi", periods=[], rows=[]),
    )

    takeaway = csb._chart_takeaway(vm, "C2")

    assert "Chưa đủ" in takeaway
    assert "biên EBITDA" in takeaway
