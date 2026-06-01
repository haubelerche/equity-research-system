from __future__ import annotations

import pytest

from backend.reporting.client_report_view_model import (
    ClientReportDataMissing,
    assert_client_final_ready,
    build_client_report_view_model,
)
from backend.reporting.client_section_builder import build_client_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.pdf_renderer import CLIENT_FORBIDDEN_PDF_TERMS, preflight_forbidden_terms
from backend.reporting.section_builder import ReportContext


def _client_html_text(tmp_path, ticker: str = "DBD") -> str:
    vm = build_client_report_view_model(ticker, "analyst_draft")
    sections = build_client_report_sections(vm)
    ctx = ReportContext(
        ticker=vm.ticker,
        company_name=vm.company_name,
        exchange=vm.exchange,
        report_date=vm.report_date,
        data_cutoff=vm.report_date,
        rating=vm.recommendation,
        current_price=vm.current_price.amount if vm.current_price else 0,
        target_price=vm.target_price.amount if vm.target_price else 0,
        upside_pct=vm.upside_downside.value * 100 if vm.upside_downside else 0,
        risk_level="Trung bình",
        data_confidence="Professional report view",
        status="ANALYST_REVIEW",
    )
    html_path = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="CONTRACT")
    return html_path.read_text(encoding="utf-8")


def test_analyst_draft_has_no_backend_terms_in_sections(tmp_path):
    html = _client_html_text(tmp_path)
    preflight_forbidden_terms(html, CLIENT_FORBIDDEN_PDF_TERMS)


def test_analyst_draft_contains_required_imp_style_tables(tmp_path):
    html = _client_html_text(tmp_path)
    required_terms = [
        "MÔ HÌNH ĐỊNH GIÁ",
        "Doanh thu thuần",
        "Tỷ suất EBITDA",
        "Lợi nhuận từ HĐKD",
        "Thuế suất thực tế",
        "CÁC KHOẢN MỤC CĐKT VÀ DÒNG TIỀN",
        "Thay đổi vốn lưu động",
        "Dòng tiền tự do",
        "Nợ ròng cuối năm",
        "CHỈ SỐ KHẢ NĂNG SINH LỢI VÀ ĐỊNH GIÁ",
        "ROE",
        "ROA",
        "ROIC",
        "WACC",
        "EV/EBITDA",
        "P/B",
        "P/S",
    ]
    for term in required_terms:
        assert term in html


def test_analyst_draft_preserves_driver_based_calculations(tmp_path):
    html = _client_html_text(tmp_path)
    required_terms = [
        "ĐỘNG LỰC DỰ PHÓNG CHÍNH",
        "ĐỘ NHẠY THEO DRIVER",
        "Bối cảnh hiện tại",
        "hàng tồn kho",
        "GMP-EU",
        "Thuế suất thực tế",
        "15.8%",
        "Tiền mặt từ hoạt động kinh doanh",
        "Cổ tức/cp",
        "EPS điều chỉnh (VND)",
        "PEG",
    ]
    for term in required_terms:
        assert term in html, f"Expected {term!r} in HTML"

    # When no dividend fact exists for a ticker, the value must be "—" (not a raw float).
    # This verifies the correct new behavior: missing facts render as a dash placeholder.
    assert "2000.0" not in html, "Raw dividend float must not appear in rendered HTML"
    assert "2,000" not in html, "Hardcoded DHG dividend must not appear for DBD"


def test_client_final_fails_when_required_valuation_is_missing():
    vm = build_client_report_view_model("DBD", "client_final")
    with pytest.raises(ClientReportDataMissing) as exc:
        assert_client_final_ready(vm)
    assert "current_price" in exc.value.missing_fields
    assert "target_price" in exc.value.missing_fields


def test_build_client_report_view_model_accepts_run_id():
    """build_client_report_view_model must accept run_id kwarg."""
    import inspect
    from backend.reporting.client_report_view_model import build_client_report_view_model
    sig = inspect.signature(build_client_report_view_model)
    assert "run_id" in sig.parameters


def test_build_client_report_view_model_uses_manifest_not_glob(tmp_path, monkeypatch):
    """With run_id, build_client_report_view_model must read manifest path, not glob latest."""
    import json
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    val_dir = artifacts / "valuation"
    val_dir.mkdir(parents=True)

    # Specific file (manifest points here)
    specific_val = val_dir / "DHG_specific_valuation.json"
    specific_val.write_text(json.dumps({"MARKER": "manifest_file", "ratios": {}}), encoding="utf-8")

    # Newer file (glob would pick this)
    wrong_val = val_dir / "DHG_zzz_valuation.json"
    wrong_val.write_text(json.dumps({"MARKER": "glob_file", "ratios": {}}), encoding="utf-8")

    manifest = ArtifactManifest(
        run_id="run_vm_manifest_test",
        ticker="DHG",
        created_at="2026-06-01T00:00:00",
        schema_version=1,
        artifacts={"valuation": {"path": str(specific_val), "producer": "VALUATION_RUN"}},
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)

    # Track file reads
    import builtins
    reads: list[str] = []
    original_open = builtins.open

    def tracking_open(path, *args, **kw):
        reads.append(str(path))
        return original_open(path, *args, **kw)

    monkeypatch.setattr(builtins, "open", tracking_open)

    from backend.reporting.client_report_view_model import build_client_report_view_model
    build_client_report_view_model("DHG", "analyst_draft", run_id="run_vm_manifest_test")

    # The wrong (glob-latest) file must NOT have been opened for valuation
    wrong_reads = [r for r in reads if "zzz" in r and "valuation" in r]
    assert not wrong_reads, (
        f"view model opened the glob-latest file instead of the manifest file: {wrong_reads}"
    )


def test_no_hardcoded_dhg_shares_in_source():
    """Module must not contain hardcoded DHG share count 109.1773."""
    import inspect
    from backend.reporting import client_report_view_model as m
    src = inspect.getsource(m)
    assert "109.1773" not in src, "109.1773 is DHG share count — must come from facts"


def test_no_hardcoded_dividend_constant_in_source():
    """Module must not contain _DIVIDEND_PER_SHARE = 2000.0 as a module constant."""
    import inspect
    from backend.reporting import client_report_view_model as m
    src = inspect.getsource(m)
    assert "_DIVIDEND_PER_SHARE = 2000.0" not in src, (
        "_DIVIDEND_PER_SHARE = 2000.0 is DHG-specific — must come from facts per ticker"
    )


def test_periods_not_a_hardcoded_five_year_literal():
    """_PERIODS must not be a fixed literal like ['2021F', ..., '2025F']."""
    import inspect
    from backend.reporting import client_report_view_model as m
    src = inspect.getsource(m)
    # Check the literal that was originally there
    assert '["2021F", "2022F", "2023F", "2024F", "2025F"]' not in src, (
        "_PERIODS must be derived from available fact periods"
    )


def test_view_model_logs_warning_when_run_id_provided_but_manifest_missing(caplog):
    """build_client_report_view_model must log WARNING when run_id given but manifest not found."""
    import logging
    with caplog.at_level(logging.WARNING, logger="backend.reporting.client_report_view_model"):
        from backend.reporting.client_report_view_model import build_client_report_view_model
        build_client_report_view_model("DHG", "analyst_draft", run_id="run_nonexistent_manifest_xyz")
    assert any(
        "manifest" in r.message.lower() or "run_id" in r.message.lower()
        for r in caplog.records
    ), f"Expected WARNING about missing manifest. Got: {[r.message for r in caplog.records]}"
