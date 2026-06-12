"""Tests for the valuation_result.json writer (Phase 05-full, GOAL_OUTPUT §13)."""
from __future__ import annotations

import json

import pytest

from scripts.generate_report import _write_valuation_result


_FCFF = {
    "wacc": 0.138,
    "terminal_growth": 0.03,
    "sum_pv_fcff": 1500.0,
    "terminal_value": 4000.0,
    "pv_terminal_value": 1800.0,
    "enterprise_value": 3176.8,
    "net_debt": -202.8,
    "equity_value": 3379.6,
    "shares_mn": 94.5,
    "target_price_vnd": 35767.0,
}
_FCFE = {"cost_of_equity": 0.138, "terminal_growth": 0.03, "equity_value": 2113.0, "target_price_vnd": 22372.0}


def _blend(is_draft: bool) -> dict:
    return {
        "price_fcff_vnd": 35767.0,
        "price_fcfe_vnd": 22372.0,
        "fcff_weight": 0.6,
        "fcfe_weight": 0.4,
        "target_price_dcf_vnd": 30409.0,
        "current_price_vnd": 50200.0,
        "upside_pct": -0.3942,
        "tv_weight_fcff": 0.6234,
        "is_draft_only": is_draft,
        "formula": "Target Price_DCF = 0.60 × Price_FCFF + 0.40 × Price_FCFE",
    }


def _write(monkeypatch, tmp_path, *, is_draft: bool, export_blocked: bool):
    import scripts.generate_report as gr
    monkeypatch.setattr(gr, "VALUATION_RESULTS_DIR", tmp_path)
    path = _write_valuation_result(
        ticker="DBD",
        ts_str="20260603T000000",
        snapshot_id="snap_test",
        valuation_date="2026-06-03",
        base_year="2025",
        current_price=50200.0,
        rating="BÁN",
        export_blocked=export_blocked,
        blend_artifact=_blend(is_draft),
        fcff_artifact=_FCFF,
        fcfe_artifact=_FCFE,
        sensitivity={},
        assumptions=[],
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_valuation_result_schema_and_bridge(tmp_path, monkeypatch):
    doc = _write(monkeypatch, tmp_path, is_draft=True, export_blocked=True)

    assert doc["ticker"] == "DBD"
    assert doc["current_price"] == 50200.0
    assert doc["target_price"] == 30409.0
    assert doc["upside_downside"] == pytest.approx(-0.3942)
    # 60/40 blend identity
    assert doc["target_price"] == pytest.approx(0.6 * 35767.0 + 0.4 * 22372.0, abs=1.0)
    # EV→equity bridge present
    bridge = doc["fcff_dcf"]
    for key in ("enterprise_value", "net_debt", "equity_value", "shares_outstanding", "terminal_value_weight"):
        assert key in bridge
    assert doc["reproducibility_hash"].startswith("sha256:")


def test_is_publishable_false_when_draft(tmp_path, monkeypatch):
    doc = _write(monkeypatch, tmp_path, is_draft=True, export_blocked=False)
    assert doc["is_publishable"] is False


def test_is_publishable_false_when_export_blocked(tmp_path, monkeypatch):
    doc = _write(monkeypatch, tmp_path, is_draft=False, export_blocked=True)
    assert doc["is_publishable"] is False


def test_is_publishable_true_when_approved_and_unblocked(tmp_path, monkeypatch):
    doc = _write(monkeypatch, tmp_path, is_draft=False, export_blocked=False)
    assert doc["is_publishable"] is True


def test_generate_report_refuses_production_run_roots(monkeypatch):
    import scripts.generate_report as gr

    monkeypatch.setattr(gr, "VALUATION_RESULTS_DIR", gr.ROOT / "storage" / "runs" / "run_bad")

    with pytest.raises(RuntimeError, match="DEV-ONLY"):
        _write_valuation_result(
            ticker="DBD",
            ts_str="20260603T000000",
            snapshot_id="snap_test",
            valuation_date="2026-06-03",
            base_year="2025",
            current_price=50200.0,
            rating="BAN",
            export_blocked=True,
            blend_artifact=_blend(True),
            fcff_artifact=_FCFF,
            fcfe_artifact=_FCFE,
            sensitivity={},
            assumptions=[],
        )


def test_render_report_writes_only_dev_namespace(tmp_path, monkeypatch):
    from pathlib import Path

    import scripts.render_report as rr

    dev_root = tmp_path / "dev_report_runs"
    monkeypatch.setattr(rr, "DEV_REPORT_ROOT", dev_root)

    source = tmp_path / "draft.md"
    source.write_text("# Local Draft\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")

    result = rr.render_dev_markdown(source, "dev/manual", pdf=False)

    html_path = Path(result["html"])
    assert html_path.exists()
    assert html_path.is_relative_to(dev_root)


def test_render_report_refuses_production_input_path():
    import scripts.render_report as rr

    with pytest.raises(RuntimeError, match="DEV-ONLY"):
        rr.render_dev_markdown(rr.ROOT / "artifacts" / "runs" / "run_bad" / "draft.md", "dev", pdf=False)
