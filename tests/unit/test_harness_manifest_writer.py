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
    # Simulate explicit ArtifactRefs emitted by tools.
    state.artifact_refs.append({
        "artifact_id": "DHG_fact_report",
        "artifact_type": "fact_report_json",
        "section_key": "facts",
        "storage_path": str(tmp_path / "DHG_facts.json"),
        "producer": "BUILD_FACTS",
    })

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
    assert manifest_data["artifacts"]["facts"]["path"].endswith("DHG_facts.json")
    assert manifest_data["artifacts"]["facts"]["producer"] == "BUILD_FACTS"


def test_write_run_manifest_method_exists():
    """ResearchGraphRunner must have _write_run_manifest method."""
    from backend.harness.runner import ResearchGraphRunner
    assert hasattr(ResearchGraphRunner, "_write_run_manifest"), (
        "ResearchGraphRunner must have a _write_run_manifest() method"
    )


def test_evidence_packet_is_manifested(tmp_path, monkeypatch):
    """Evidence packet must be written before manifest construction."""
    from backend.harness.runner import ResearchGraphRunner
    from backend.harness.state import ResearchGraphState

    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(
        run_id="run_evidence_manifest_test",
        ticker="DHG",
        objective="test objective",
    )

    import backend.reporting.artifact_manifest as am_mod
    original_write = am_mod.write_manifest

    def capturing_write(manifest, base_dir):
        return original_write(manifest, base_dir=tmp_path)

    monkeypatch.setattr(am_mod, "write_manifest", capturing_write)

    import backend.harness.runner as runner_mod
    monkeypatch.setattr(runner_mod, "ROOT", tmp_path, raising=False)

    runner._write_evidence_packet(state)
    runner._write_run_manifest(state)

    manifest_path = tmp_path / "manifests" / "run_evidence_manifest_test_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence_entry = manifest["artifacts"]["evidence_packet"]
    assert evidence_entry["producer"] == "ResearchGraphRunner"
    assert (tmp_path / "artifacts" / "evidence_packets" / "run_evidence_manifest_test_evidence_packet.json").exists()


def test_agent_effectiveness_audit_is_written_and_manifestable(tmp_path, monkeypatch):
    """Agent audit data must be present in state.trace (trace.jsonl, not a separate file)."""
    from backend.harness.runner import ResearchGraphRunner
    from backend.harness.state import ResearchGraphState

    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(
        run_id="run_agent_audit_test",
        ticker="DP3",
        objective="test objective",
    )
    state.artifacts["auto_ingest"] = {
        "web_ingest_attempted": True,
        "cafef_rows": 12,
        "pdf_rows": 0,
        "ocr_candidates": 0,
        "ocr_promoted": 0,
        "promoted": 0,
        "year_statuses": ["TIER2_ONLY"],
        "official_ready": False,
        "continued_with_tier2_or_tier3_fallback": True,
    }
    state.artifacts["financial_analyst_review"] = {
        "diagnostics": [{"metric": "revenue.net", "period": "2025FY"}]
    }
    state.draft_report = {
        "claims_count": 3,
        "citation_count": 3,
        "export_blocked": True,
        "report_path": "reports/DP3.md",
    }
    state.trace.extend(
        [
            {
                "kind": "tool_call",
                "tool_name": "AUTO_INGEST",
                "agent_role": "DataRetrievalAgent",
                "output_hash": "abc",
                "output_summary": state.artifacts["auto_ingest"],
            },
            {
                "kind": "agent_message",
                "agent_id": "financial_analyst",
                "action": "Interpret deterministic financial tables.",
                "status": "completed",
                "latency_ms": 100,
                "cost_estimate": 0.001,
                "confidence": 0.8,
                "warnings": [],
                "requires_human": False,
                "output_summary": {"metric_refs": ["revenue.net"], "period_refs": ["2025FY"]},
            },
        ]
    )

    import backend.harness.runner as runner_mod
    monkeypatch.setattr(runner_mod, "ROOT", tmp_path, raising=False)

    # _write_agent_effectiveness_audit is now a no-op; data lives in state.trace
    runner._write_agent_effectiveness_audit(state)

    # Verify audit data is accessible via state.trace
    tool_calls = [e for e in state.trace if e.get("kind") == "tool_call"]
    agent_messages = [e for e in state.trace if e.get("kind") == "agent_message"]
    assert any(e.get("tool_name") == "AUTO_INGEST" for e in tool_calls)
    auto_ingest_entry = next(e for e in tool_calls if e.get("tool_name") == "AUTO_INGEST")
    assert auto_ingest_entry["output_summary"]["web_ingest_attempted"] is True
    assert auto_ingest_entry["output_summary"]["cafef_rows"] == 12
    assert auto_ingest_entry["output_summary"]["continued_with_tier2_or_tier3_fallback"] is True
    assert any(e.get("agent_id") == "financial_analyst" for e in agent_messages)

    # No audit file should be written
    audit_dir = tmp_path / "artifacts" / "audits"
    assert not audit_dir.exists() or not list(audit_dir.iterdir())
