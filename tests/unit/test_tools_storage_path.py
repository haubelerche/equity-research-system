"""Behavioral test: build_facts_tool must report storage_path in ArtifactRef."""
from pathlib import Path
import json
import pytest


def test_build_facts_tool_artifact_ref_has_storage_path(monkeypatch, tmp_path):
    """build_facts_tool must include the output file path in ArtifactRef.storage_path."""
    # Fake build_facts returning a dict that includes artifact_path
    fake_artifact_path = str(tmp_path / "DHG_facts.json")
    fake_artifact = {
        "validation": {"valuation_gate": "pass"},
        "snapshot_id": "snap_001",
        "artifact_path": fake_artifact_path,
    }
    monkeypatch.setattr("scripts.build_facts.build_facts", lambda **kw: fake_artifact)

    from backend.harness.tools import build_facts_tool
    result = build_facts_tool("DHG", 2021, 2025)

    paths = [ref.storage_path for ref in result.artifact_refs if ref.section_key == "facts"]
    assert any(p for p in paths), (
        f"build_facts_tool ArtifactRef must have storage_path, got: {[ref.storage_path for ref in result.artifact_refs]}"
    )
    assert fake_artifact_path in paths, (
        f"Expected {fake_artifact_path!r} in storage_path, got: {paths}"
    )


def test_run_valuation_tool_artifact_ref_has_storage_path(monkeypatch, tmp_path):
    """run_valuation_tool must include the valuation file path in ArtifactRef.storage_path."""
    fake_artifact_path = str(tmp_path / "DHG_valuation.json")
    fake_artifact = {
        "artifact_path": fake_artifact_path,
        "dcf": {"base": {"intrinsic_value_per_share_vnd": 50000}},
        "snapshot_id": "snap_002",
    }
    monkeypatch.setattr("scripts.run_valuation.run_valuation", lambda **kw: fake_artifact)

    from backend.harness.tools import run_valuation_tool
    result = run_valuation_tool("DHG", 2021, 2025)

    paths = [ref.storage_path for ref in result.artifact_refs if ref.section_key == "valuation"]
    assert any(p for p in paths), (
        f"run_valuation_tool ArtifactRef must have storage_path. Got: {[ref.storage_path for ref in result.artifact_refs]}"
    )


def test_build_index_tool_artifact_ref_has_storage_path(monkeypatch, tmp_path):
    """build_index_tool must write and expose an index summary path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.build_index.build_index", lambda **kw: {"chunks_inserted": 3})

    from backend.harness.tools import build_index_tool
    result = build_index_tool("DHG", 2021, 2025)

    refs = [ref for ref in result.artifact_refs if ref.section_key == "index"]
    assert refs and refs[0].storage_path
    assert Path(refs[0].storage_path).exists()


def test_generate_report_tool_reports_forecast_and_report_paths(monkeypatch, tmp_path):
    """generate_report_tool must expose report-side artifacts for the run manifest."""
    fake = {
        "report_path": str(tmp_path / "DHG_report.md"),
        "forecast_path": str(tmp_path / "DHG_forecast.json"),
        "fcff_path": str(tmp_path / "DHG_fcff.json"),
        "fcfe_path": str(tmp_path / "DHG_fcfe.json"),
        "blend_path": str(tmp_path / "DHG_blend.json"),
        "citation_path": str(tmp_path / "DHG_citation.json"),
        "valuation_result_path": str(tmp_path / "DHG_valuation_result.json"),
        "snapshot_id": "snap_001",
        "source_tier_gate": {},
        "claims": [],
        "citation_map": {},
    }
    monkeypatch.setattr("scripts.generate_report.generate_report", lambda **kw: fake)

    from backend.harness.tools import generate_report_tool
    result = generate_report_tool("DHG", "snap_001", 2021, 2025)

    refs = {ref.section_key: ref.storage_path for ref in result.artifact_refs}
    assert refs["forecast"] == fake["forecast_path"]
    assert refs["fcff"] == fake["fcff_path"]
    assert refs["blend"] == fake["blend_path"]
    assert refs["citation"] == fake["citation_path"]
    assert refs["valuation_result"] == fake["valuation_result_path"]


def test_evaluate_quality_tool_fails_without_run_scoped_valuation_path():
    from backend.harness.tools import evaluate_quality_tool

    result = evaluate_quality_tool("DHG", valuation_path=None)

    assert result.status == "failed"
    assert result.blocking_reason == "run_scoped_valuation_artifact_missing"


def test_artifact_ref_has_storage_path_field():
    """ArtifactRef must have storage_path and producer fields."""
    from backend.harness.state import ArtifactRef
    import dataclasses
    # ArtifactRef is a Pydantic model — check model_fields
    field_names = set(ArtifactRef.model_fields.keys())
    assert "storage_path" in field_names, "ArtifactRef must have storage_path field"
    assert "producer" in field_names, "ArtifactRef must have producer field"


def test_evaluate_quality_tool_prefers_run_valuation_path_over_latest_lookup(monkeypatch, tmp_path):
    """When valuation_path is provided, quality evaluation must not search latest artifacts."""
    valuation_path = tmp_path / "DHG_valuation.json"
    valuation_path.write_text(
        json.dumps({
            "forecast": {"tax_policy": {"effective_tax_rate": 0.2}},
            "fcff": {"wacc_breakdown": {"tax_rate": 0.2}, "warnings": ["TaxPolicy used"], "fcff_table": []},
            "fcfe": {"fcfe_table": []},
            "multiples": {},
            "assumption_gate": {},
            "valuation_confidence": {},
        }),
        encoding="utf-8",
    )

    def fail_latest(*args, **kwargs):
        raise AssertionError("latest artifact lookup should not run when valuation_path is provided")

    monkeypatch.setattr("scripts.evaluate_report_quality._latest_file", fail_latest)

    from backend.harness.tools import evaluate_quality_tool
    result = evaluate_quality_tool("DHG", valuation_path=str(valuation_path))

    assert result.node_name == "QUALITY_EVALUATION"
