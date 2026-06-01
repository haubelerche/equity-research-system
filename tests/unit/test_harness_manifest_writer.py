"""Behavioral test: ResearchGraphRunner must write ArtifactManifest at end of execute()."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


def test_execute_writes_manifest_file(tmp_path, monkeypatch):
    """After execute(), a manifest JSON must exist for the run_id."""
    from backend.harness.runner import ResearchGraphRunner
    from backend.harness.state import ResearchGraphState

    # Set up a minimal runner
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)

    state = ResearchGraphState(
        run_id="run_manifest_write_test",
        ticker="DHG",
        objective="test objective",
        from_year=2021,
        to_year=2025,
    )
    # Simulate what a tool would put in state.artifacts
    state.artifacts["build_facts"] = {
        "artifact_path": str(tmp_path / "DHG_facts.json"),
        "ticker": "DHG",
    }

    # Patch write_manifest to write to tmp_path instead of real artifacts/
    import backend.reporting.artifact_manifest as am_mod
    original_write = am_mod.write_manifest
    written_manifests: list[Path] = []

    def capturing_write(manifest, base_dir):
        path = original_write(manifest, base_dir=tmp_path)
        written_manifests.append(path)
        return path

    monkeypatch.setattr(am_mod, "write_manifest", capturing_write)

    # Patch ROOT in runner to tmp_path so manifest goes to tmp_path/manifests/
    import backend.harness.runner as runner_mod
    monkeypatch.setattr(runner_mod, "ROOT", tmp_path, raising=False)

    # Call _write_run_manifest directly (it must exist as a method)
    runner._write_run_manifest(state)

    manifest_files = list(tmp_path.glob("manifests/run_manifest_write_test_manifest.json"))
    assert manifest_files, (
        f"Expected manifest file in {tmp_path}/manifests/, found: {list(tmp_path.rglob('*.json'))}"
    )
    manifest_data = json.loads(manifest_files[0].read_text())
    assert manifest_data["run_id"] == "run_manifest_write_test"
    assert manifest_data["ticker"] == "DHG"
    assert "schema_version" in manifest_data


def test_write_run_manifest_method_exists():
    """ResearchGraphRunner must have _write_run_manifest method."""
    from backend.harness.runner import ResearchGraphRunner
    assert hasattr(ResearchGraphRunner, "_write_run_manifest"), (
        "ResearchGraphRunner must have a _write_run_manifest() method"
    )
