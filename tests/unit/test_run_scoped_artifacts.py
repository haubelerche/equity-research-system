"""Test: tools write to artifacts/runs/{run_id}/ when run_id provided."""
from __future__ import annotations

from pathlib import Path


def test_build_index_tool_run_scoped(monkeypatch, tmp_path):
    """build_index_tool with run_id writes to artifacts/runs/{run_id}/."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.build_index.build_index", lambda **kw: {"chunks_inserted": 3})

    from backend.harness.tools import build_index_tool
    result = build_index_tool("DHG", 2021, 2025, run_id="run_test_001")

    refs = [ref for ref in result.artifact_refs if ref.section_key == "index"]
    assert refs and refs[0].storage_path
    assert "runs" in refs[0].storage_path and "run_test_001" in refs[0].storage_path


def test_build_index_tool_legacy_no_run_id(monkeypatch, tmp_path):
    """build_index_tool without run_id still writes to artifacts/index/ (legacy)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.build_index.build_index", lambda **kw: {"chunks_inserted": 3})

    from backend.harness.tools import build_index_tool
    result = build_index_tool("DHG", 2021, 2025)

    refs = [ref for ref in result.artifact_refs if ref.section_key == "index"]
    assert refs and refs[0].storage_path
    assert Path(refs[0].storage_path).exists()


def test_read_ratio_artifact_tool_run_scoped(monkeypatch, tmp_path):
    """read_ratio_artifact_tool with run_id writes to artifacts/runs/{run_id}/."""
    monkeypatch.chdir(tmp_path)

    # Mock the snapshot loading and ratio computation
    fake_facts = [
        {"fiscal_year": 2023, "line_item_code": "revenue.net", "value": 100.0, "source_tier": 0},
    ]
    monkeypatch.setattr("backend.dataops.snapshot.load_snapshot_facts", lambda sid: fake_facts)
    monkeypatch.setattr("backend.facts.normalizer.build_fact_table", lambda facts: {"revenue.net": {"2023FY": type("E", (), {"value": 100.0, "source_tier": 0})()}})
    monkeypatch.setattr("backend.facts.normalizer.compute_derived", lambda t: t)
    monkeypatch.setattr("backend.facts.normalizer.periods_sorted", lambda t: ["2023FY"])
    monkeypatch.setattr("backend.analytics.ratios.compute_ratios", lambda t: {})

    from backend.harness.tools import read_ratio_artifact_tool
    result = read_ratio_artifact_tool("DHG", "snap_001", run_id="run_test_001")

    refs = [ref for ref in result.artifact_refs if ref.section_key == "ratios"]
    assert refs and refs[0].storage_path
    assert "runs" in refs[0].storage_path and "run_test_001" in refs[0].storage_path


def test_run_valuation_tool_run_scoped(monkeypatch, tmp_path):
    """run_valuation_tool with run_id writes valuation.json to artifacts/runs/{run_id}/."""
    monkeypatch.chdir(tmp_path)
    fake_artifact = {
        "artifact_path": str(tmp_path / "legacy_valuation.json"),
        "ticker": "DHG",
        "snapshot_id": "snap_001",
        "forecast": {"years": [2024, 2025]},
        "fcff": {"base": {"ev": 1000}},
        "fcfe": {"table": []},
        "blend_dcf": {"target_price_dcf": 50000},
        "sensitivity": {"matrix": []},
        "assumptions": {"wacc": 0.12},
        "formula_traces": [{"step": "test"}],
        "valuation_methods": ["FCFF", "PE_Forward"],
        "currency": "VND",
        "unit_policy": "vnd_absolute",
    }
    monkeypatch.setattr("scripts.run_valuation.run_valuation", lambda **kw: fake_artifact)

    from backend.harness.tools import run_valuation_tool
    result = run_valuation_tool("DHG", 2021, 2025, run_id="run_test_002")

    # Check that valuation.json was written to the run dir
    run_dir = tmp_path / "artifacts" / "runs" / "run_test_002"
    val_path = run_dir / "valuation.json"
    assert val_path.exists(), f"Expected valuation.json at {val_path}"

    import json
    data = json.loads(val_path.read_text(encoding="utf-8"))
    assert data["ticker"] == "DHG"
    assert "forecast" in data
    assert "fcff" in data
    assert "blend" in data or "blend_dcf" in data
    assert "sensitivity" in data
    assert "assumptions" in data
    assert "formula_traces" in data
