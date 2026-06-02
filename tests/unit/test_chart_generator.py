"""Tests for backend/reporting/chart_generator.py — TDD, written before implementation."""
import pytest
from pathlib import Path
from backend.reporting.chart_generator import ChartGenerator, ChartSpec


def make_spec(tmp_path, chart_id="C2") -> ChartSpec:
    return ChartSpec(
        chart_id=chart_id,
        ticker="DHG",
        run_id="TEST",
        periods=["FY2021", "FY2022", "FY2023", "FY2024"],
        revenue_bn=[3.2, 3.5, 3.8, 4.1],
        ebitda_margin_pct=[15.0, 16.5, 17.2, 18.0],
        ebit_margin_pct=[12.0, 13.5, 14.2, 15.0],
        eps_vnd=[8500, 9200, 10100, 11000],
        pe_x=[14.0, 13.5, 12.8, 12.0],
        gross_margin_pct=[45.0, 46.0, 47.5, 48.0],
        net_margin_pct=[14.0, 15.0, 16.0, 17.0],
        roe_pct=[18.0, 19.5, 21.0, 22.0],
        forecast_revenue_bn=[4.5, 5.0, 5.5],
        forecast_profit_bn=[0.72, 0.85, 0.99],
        forecast_periods=["FY2025E", "FY2026E", "FY2027E"],
        price_series=[100.0, 105.0, 98.0, 112.0, 120.0],
        benchmark_series=[100.0, 102.0, 97.0, 108.0, 115.0],
        date_labels=["Jan", "Feb", "Mar", "Apr", "May"],
        bridge_items=[
            ("PV FCFF", 500.0),
            ("Terminal Value", 800.0),
            ("Less: Net Debt", -120.0),
            ("Equity Value", 1180.0),
        ],
    )


def test_c2_creates_png(tmp_path):
    spec = make_spec(tmp_path, chart_id="C2")
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c2_revenue_ebitda(spec)
    assert path.exists(), f"Expected PNG at {path}"
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000, "PNG file too small — likely empty"


def test_c3_creates_png(tmp_path):
    spec = make_spec(tmp_path, chart_id="C3")
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c3_eps_pe(spec)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_c4_creates_png(tmp_path):
    spec = make_spec(tmp_path, chart_id="C4")
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c4_margin_roe(spec)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_c5_creates_png(tmp_path):
    spec = make_spec(tmp_path, chart_id="C5")
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c5_forecast(spec)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_c7_sensitivity_heatmap(tmp_path):
    spec = make_spec(tmp_path, chart_id="C7")
    gen = ChartGenerator(output_dir=tmp_path)
    wacc_range = [9.0, 9.5, 10.0, 10.5, 11.0]
    tg_range = [1.5, 2.0, 2.5]
    # 3 rows x 5 cols matrix (tg_range x wacc_range)
    matrix = [
        [95000, 90000, 85000, 81000, 77000],
        [100000, 95000, 90000, 85000, 81000],
        [106000, 100000, 95000, 90000, 85000],
    ]
    path = gen.render_c7_sensitivity_heatmap(spec, wacc_range, tg_range, matrix)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_c6_dcf_bridge(tmp_path):
    spec = make_spec(tmp_path, chart_id="C6")
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c6_dcf_bridge(spec)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_c1_price_vs_vnindex(tmp_path):
    spec = make_spec(tmp_path, chart_id="C1")
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c1_price_vs_vnindex(spec)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_empty_data_does_not_crash(tmp_path):
    """Empty lists must render zero-filled chart without raising."""
    spec = ChartSpec(
        chart_id="C2",
        ticker="DHG",
        run_id="",
        periods=[],
    )
    gen = ChartGenerator(output_dir=tmp_path)
    # Must not raise
    path = gen.render_c2_revenue_ebitda(spec)
    assert path.exists()


def test_filename_with_run_id(tmp_path):
    spec = make_spec(tmp_path, chart_id="C2")
    spec.run_id = "RUN_20260601"
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c2_revenue_ebitda(spec)
    assert "RUN_20260601" in path.name
    assert "DHG" in path.name
    assert "C2" in path.name


def test_filename_without_run_id(tmp_path):
    spec = make_spec(tmp_path, chart_id="C4")
    spec.run_id = ""
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c4_margin_roe(spec)
    assert path.name.startswith("DHG_")
    assert "C4" in path.name


def test_c8_peer_comparison_renders(tmp_path):
    """C8 with peer_data list produces a PNG file."""
    spec = ChartSpec(
        chart_id="C8",
        ticker="DHG",
        run_id="TEST",
        peer_data=[
            {"ticker": "IMP", "pe": 12.8, "ev_ebitda": 9.5},
            {"ticker": "TRA", "pe": 14.1, "ev_ebitda": 10.2},
            {"ticker": "DMC", "pe": 13.5, "ev_ebitda": 10.0},
            {"ticker": "DHG", "pe": 16.5, "ev_ebitda": 12.0},
        ],
    )
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c8_peer_comparison(spec)
    assert path.exists(), f"Expected PNG at {path}"
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000, "PNG file too small — likely empty"


def test_c8_peer_comparison_empty_peer_data(tmp_path):
    """Empty peer_data produces a placeholder PNG without crashing."""
    spec = ChartSpec(
        chart_id="C8",
        ticker="DHG",
        run_id="TEST",
        peer_data=[],
    )
    gen = ChartGenerator(output_dir=tmp_path)
    path = gen.render_c8_peer_comparison(spec)
    assert path.exists(), f"Expected placeholder PNG at {path}"
    assert path.suffix == ".png"
    assert path.stat().st_size > 500, "Placeholder PNG too small"


def test_c8_chart_id_set_correctly(tmp_path):
    """render_c8_peer_comparison sets spec.chart_id == 'C8'."""
    spec = ChartSpec(
        chart_id="",
        ticker="DHG",
        run_id="TEST",
        peer_data=[
            {"ticker": "IMP", "pe": 12.8, "ev_ebitda": 9.5},
            {"ticker": "DHG", "pe": 16.5, "ev_ebitda": 12.0},
        ],
    )
    gen = ChartGenerator(output_dir=tmp_path)
    gen.render_c8_peer_comparison(spec)
    assert spec.chart_id == "C8"
