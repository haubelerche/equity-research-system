"""ArtifactManifest: write, read, and resolve per-run artifact paths."""
import json
from pathlib import Path
import pytest
from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest, read_manifest


def test_write_and_read_round_trip(tmp_path):
    val_path = str(tmp_path / "DHG_val.json")
    manifest = ArtifactManifest(
        run_id="run_dhg_test_001",
        ticker="DHG",
        created_at="2026-06-01T00:00:00",
        schema_version=1,
        artifacts={
            "valuation": {"path": val_path, "producer": "VALUATION_RUN"},
            "facts": {"path": str(tmp_path / "DHG_facts.json"), "producer": "BUILD_FACTS"},
        },
    )
    write_manifest(manifest, base_dir=tmp_path)
    loaded = read_manifest("run_dhg_test_001", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.run_id == "run_dhg_test_001"
    assert loaded.schema_version == 1
    assert loaded.resolve("valuation") == val_path


def test_read_missing_returns_none(tmp_path):
    assert read_manifest("run_nonexistent", base_dir=tmp_path) is None


def test_resolve_missing_key_returns_none(tmp_path):
    m = ArtifactManifest(
        run_id="r", ticker="DHG", created_at="x", schema_version=1,
        artifacts={"valuation": {"path": "/p.json", "producer": "V"}},
    )
    assert m.resolve("nonexistent") is None
    assert m.resolve("valuation") == "/p.json"


def test_load_json_logs_on_missing_file(tmp_path, caplog):
    import logging
    m = ArtifactManifest(
        run_id="r", ticker="DHG", created_at="x", schema_version=1,
        artifacts={"valuation": {"path": str(tmp_path / "missing.json"), "producer": "V"}},
    )
    with caplog.at_level(logging.WARNING, logger="backend.reporting.artifact_manifest"):
        result = m.load_json("valuation")
    assert result == {}
    assert any("missing.json" in r.message or "valuation" in r.message for r in caplog.records)


def test_build_manifest_from_artifact_refs(tmp_path):
    from backend.reporting.artifact_manifest import build_manifest_from_artifact_refs
    refs = [
        {"key": "valuation", "path": "/artifacts/val.json", "producer": "VALUATION_RUN"},
        {"key": "facts", "path": "/artifacts/facts.json", "producer": "BUILD_FACTS"},
        {"key": "", "path": "/artifacts/bad.json", "producer": "X"},  # empty key — should be skipped
    ]
    manifest = build_manifest_from_artifact_refs(
        run_id="run_test", ticker="DHG",
        created_at="2026-06-01T00:00:00",
        artifact_refs=refs,
    )
    assert manifest.resolve("valuation") == "/artifacts/val.json"
    assert manifest.resolve("facts") == "/artifacts/facts.json"
    assert manifest.resolve("") is None  # empty key skipped
    assert len(manifest.artifacts) == 2  # only 2 valid entries
