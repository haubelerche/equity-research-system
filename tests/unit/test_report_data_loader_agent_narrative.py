"""Unit tests: agent narrative artifact gets injected into ReportContext."""
import json
from pathlib import Path


def test_agent_narrative_injected_into_report_context(monkeypatch):
    """When agent_narrative dict is passed, its fields appear in ReportContext."""
    from backend.reporting import report_data_loader

    narrative = {
        "financial_narrative": "DHG duy trì tăng trưởng doanh thu ổn định 2022-2025.",
        "investment_thesis": "DHG là cổ phiếu chất lượng với biên gộp vững.",
        "risk_narrative": "Rủi ro chính: áp lực giá thầu ETC.",
    }

    # Stub out all external dependencies so the test is self-contained
    monkeypatch.setattr(report_data_loader, "_latest_valuation", lambda ticker: {
        "blend_dcf": {"target_price_dcf_vnd": 75000, "current_price_vnd": 94400, "upside_pct": -0.2},
        "multiples": {"shares_mn": 135.0, "pe_ratio": 15.0, "pb_ratio": 2.5, "eps_vnd": 6300},
        "ratios": {},
        "fcff": {"wacc": 0.10, "terminal_growth": 0.03, "fcff_table": []},
        "forecast": {"drivers": {}},
        "sensitivity": {},
        "fy_periods": ["2022FY", "2023FY", "2024FY", "2025FY"],
    })
    monkeypatch.setattr(report_data_loader, "_latest_valuation_result", lambda ticker: {})

    ctx = report_data_loader.load_report_context(
        "DHG",
        allow_latest_artifacts=True,
        agent_narrative=narrative,
    )

    assert "ổn định" in ctx.financial_narrative, "Vietnamese narrative not injected"
    assert "chất lượng" in ctx.investment_thesis, "Investment thesis not injected"
    assert "ETC" in ctx.risk_narrative, "Risk narrative not injected"

    # Fields not in narrative dict should still have hardcoded defaults (not empty string)
    assert ctx.forecast_narrative  # Should not be empty — has a default


def test_missing_agent_narrative_does_not_crash(monkeypatch):
    """When no agent narrative is provided, load_report_context returns a valid ReportContext."""
    from backend.reporting import report_data_loader

    monkeypatch.setattr(report_data_loader, "_latest_valuation", lambda ticker: {})
    monkeypatch.setattr(report_data_loader, "_latest_valuation_result", lambda ticker: {})

    ctx = report_data_loader.load_report_context("IMP", allow_latest_artifacts=True)
    assert isinstance(ctx.financial_narrative, str)
    assert isinstance(ctx.investment_thesis, str)


def test_load_agent_narrative_from_manifest_missing_returns_empty(tmp_path):
    """_load_agent_narrative_from_manifest returns {} when no manifest exists."""
    from backend.reporting.report_data_loader import _load_agent_narrative_from_manifest

    result = _load_agent_narrative_from_manifest("RUN_NONEXISTENT_999", base_dir=tmp_path)
    assert result == {}


def test_load_agent_narrative_from_manifest_reads_payload(tmp_path):
    """_load_agent_narrative_from_manifest reads narrative payload from a manifest + artifact file."""
    from backend.reporting.report_data_loader import _load_agent_narrative_from_manifest

    run_id = "RUN_TEST_001"

    # Write the narrative payload to an artifact JSON file
    artifact_dir = tmp_path / "financial_analysis"
    artifact_dir.mkdir(parents=True)
    artifact_path = artifact_dir / f"{run_id}_financial_analysis.json"
    payload = {
        "financial_narrative": "Phân tích tài chính DHG.",
        "investment_thesis": "Luận điểm đầu tư.",
        "risk_narrative": "Rủi ro chính.",
    }
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    # _read_manifest_or_raise(run_id, base_dir=tmp_path) resolves to
    # read_manifest(run_id, base_dir=tmp_path/"artifacts")
    # which looks for: tmp_path/artifacts/manifests/<run_id>_manifest.json
    manifests_dir = tmp_path / "artifacts" / "manifests"
    manifests_dir.mkdir(parents=True)
    manifest_data = {
        "schema_version": 1,
        "run_id": run_id,
        "ticker": "DHG",
        "created_at": "2026-06-03T00:00:00",
        "artifacts": {
            "financial_analysis": {
                "path": str(artifact_path),
                "producer": "FinancialAnalystAgent",
            }
        }
    }
    manifest_path = manifests_dir / f"{run_id}_manifest.json"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    result = _load_agent_narrative_from_manifest(run_id, base_dir=tmp_path)
    assert result.get("financial_narrative") == "Phân tích tài chính DHG."
    assert result.get("investment_thesis") == "Luận điểm đầu tư."
    assert result.get("risk_narrative") == "Rủi ro chính."


def test_load_agent_narrative_from_manifest_reads_wrapped_payload(tmp_path):
    """_load_agent_narrative_from_manifest handles payload wrapped under 'payload' key."""
    from backend.reporting.report_data_loader import _load_agent_narrative_from_manifest

    run_id = "RUN_TEST_002"
    manifest_dir = tmp_path / "runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # Write artifact file with nested payload key
    artifact_data = {
        "payload": {
            "financial_narrative": "DHG với payload lồng.",
            "investment_thesis": "Luận điểm.",
        }
    }
    artifact_path = tmp_path / "runs" / f"{run_id}_financial_analysis.json"
    artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

    manifest_data = {
        "schema_version": 1,
        "run_id": run_id,
        "ticker": "DHG",
        "created_at": "2026-06-03T00:00:00",
        "artifacts": {
            "financial_analysis": {
                "artifact_type": "agent_output_json",
                "path": str(artifact_path),
            }
        }
    }
    # _read_manifest_or_raise uses base_dir / "artifacts" / "manifests"
    manifests_dir = tmp_path / "artifacts" / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"{run_id}_manifest.json"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    result = _load_agent_narrative_from_manifest(run_id, base_dir=tmp_path)
    assert result.get("financial_narrative") == "DHG với payload lồng."
    assert result.get("investment_thesis") == "Luận điểm."
