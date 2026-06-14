from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.reporting import client_section_builder as csb
from backend.reporting.client_report_view_model import TableData


def _full_table() -> TableData:
    periods = ["2022A", "2023A", "2024A", "2025A", "2026F", "2027F", "2028F", "2029F", "2030F"]
    return TableData(title="TÓM TẮT TÀI CHÍNH", periods=periods, rows=[("Doanh thu thuần", list(range(9)))])


def test_main_financial_table_preserves_full_period_and_af_markers() -> None:
    html = csb._render_main_table(_full_table(), "financial-model-table full-financial-table")
    for period in _full_table().periods:
        assert period in html


def test_profit_bridge_marks_comment_as_wrappable_prose() -> None:
    table = TableData(
        title="MÔ HÌNH ĐỊNH GIÁ",
        periods=["2025A", "2026F"],
        rows=[("Doanh thu thuần", [100.0, 110.0])],
    )
    html = csb._render_profit_bridge(table)
    assert 'class="bridge-comment"' in html
    assert 'class="bridge-comment-col"' in html

    css = Path("backend/reporting/templates/report.css").read_text(encoding="utf-8")
    assert ".profit-bridge-table td.bridge-comment" in css
    assert "overflow-wrap: break-word !important" in css


def test_client_final_hides_internal_limitations() -> None:
    vm = SimpleNamespace(
        mode="client_final",
        missing_required_fields=["forecast_debt", "debt_schedule_publishable"],
    )
    assert csb._render_disclosed_limitations(vm) == ""


def test_analyst_draft_deduplicates_forward_debt_limitation() -> None:
    vm = SimpleNamespace(
        mode="analyst_draft",
        missing_required_fields=["forecast_debt", "debt_schedule_publishable"],
    )
    html = csb._render_disclosed_limitations(vm)
    assert html.count("lịch dự phóng nợ vay") == 1
