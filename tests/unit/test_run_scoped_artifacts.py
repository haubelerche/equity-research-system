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
