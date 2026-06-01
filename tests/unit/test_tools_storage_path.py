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


def test_artifact_ref_has_storage_path_field():
    """ArtifactRef must have storage_path and producer fields."""
    from backend.harness.state import ArtifactRef
    import dataclasses
    # ArtifactRef is a Pydantic model — check model_fields
    field_names = set(ArtifactRef.model_fields.keys())
    assert "storage_path" in field_names, "ArtifactRef must have storage_path field"
    assert "producer" in field_names, "ArtifactRef must have producer field"
