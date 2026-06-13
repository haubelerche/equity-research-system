from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.reporting.client_chart_builder import build_client_report_charts
from backend.reporting.client_report_view_model import TableData


class _FakeGenerator:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _has_nonzero(values, min_count=1):
        return sum(bool(value) for value in values) >= min_count

    def _render(self, spec):
        path = self.output_dir / f"{spec.chart_id}.png"
        path.write_bytes(b"png")
        return path

    render_c2_revenue_ebitda = _render
    render_c4_margin_roe = _render
    render_c5_forecast = _render
    render_c1_price_vs_vnindex = _render


def test_builds_only_fpts_main_report_financial_charts(tmp_path):
    periods = ["2024FY", "2025FY", "2026F", "2027F"]
    financial = TableData(
        title="Tóm tắt",
        periods=periods,
        rows=[
            ("Doanh thu thuần", [100, 110, 120, 130]),
            ("LNST sau CĐKKS / LNST CĐ mẹ", [10, 11, 12, 13]),
        ],
    )
    model = TableData(
        title="Mô hình",
        periods=periods,
        rows=[
            ("Doanh thu thuần", [100, 110, 120, 130]),
            ("LNST sau CĐKKS / LNST CĐ mẹ", [10, 11, 12, 13]),
            ("Tỷ suất EBITDA", [0.2, 0.21, 0.22, 0.23]),
            ("Biên lợi nhuận HĐKD / EBIT margin", [0.16, 0.17, 0.18, 0.19]),
            ("Biên lợi nhuận gộp", [0.45, 0.46, 0.47, 0.48]),
            ("Biên lợi nhuận ròng", [0.1, 0.11, 0.12, 0.13]),
        ],
    )
    vm = SimpleNamespace(
        ticker="DHG",
        financial_summary_table=financial,
        valuation_model_table=model,
    )

    charts = build_client_report_charts(
        vm, tmp_path, run_id="run_1", generator_cls=_FakeGenerator
    )

    assert set(charts) == {"C2", "C4", "C5"}
    assert not {"C3", "C6", "C7", "C8"} & set(charts)
    assert all(Path(chart.path).exists() for chart in charts.values())


def test_builds_c1_from_canonical_stock_history_without_benchmark(tmp_path):
    vm = SimpleNamespace(
        ticker="DHG",
        financial_summary_table=TableData(title="", periods=[], rows=[]),
        valuation_model_table=TableData(title="", periods=[], rows=[]),
        market_data=SimpleNamespace(
            source="fact.price_history",
            primary_benchmark="VNINDEX",
            secondary_benchmark="VNINDEX",
            price_history=[
                {"trade_date": "2026-05-27", "close": 101.0},
                {"trade_date": "2026-05-28", "close": 103.0},
                {"trade_date": "2026-05-29", "close": 102.0},
            ],
            primary_benchmark_history=[],
            secondary_benchmark_history=[],
        ),
    )

    charts = build_client_report_charts(
        vm, tmp_path, run_id="run_1", generator_cls=_FakeGenerator
    )

    assert set(charts) == {"C1"}
    assert charts["C1"].title == "Diễn biến giá cổ phiếu"
    assert charts["C1"].caption == "Nguồn nhóm phân tích thu thập"
