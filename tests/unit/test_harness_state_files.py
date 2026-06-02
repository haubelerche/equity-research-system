from __future__ import annotations

import json
from pathlib import Path

import yaml

from backend.harness.gates import export_gate


ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = ROOT / "config" / "harness"


def test_harness_state_files_exist_and_are_machine_readable() -> None:
    required = [
        "export_gate_policy.yml",
        "task_registry.json",
        "known_failures.json",
        "run_state_schema.json",
        "tool_contracts.md",
        "agent_roles.md",
    ]
    for filename in required:
        assert (HARNESS_DIR / filename).exists(), f"missing harness contract: {filename}"

    policy = yaml.safe_load((HARNESS_DIR / "export_gate_policy.yml").read_text(encoding="utf-8"))
    task_registry = json.loads((HARNESS_DIR / "task_registry.json").read_text(encoding="utf-8"))
    known_failures = json.loads((HARNESS_DIR / "known_failures.json").read_text(encoding="utf-8"))
    run_schema = json.loads((HARNESS_DIR / "run_state_schema.json").read_text(encoding="utf-8"))

    assert "tier3_only_material_fact" in policy["block_on"]
    assert "missing_formula_trace" in policy["block_on"]
    assert task_registry["protected_paths"] == ["FinRobot/", "vnstock/"]
    assert known_failures["failures"][0]["failure_id"] == "ERR-KF-001"
    assert "gate_results" in run_schema["required"]


def test_gate_output_has_issue_contract_and_blocks_false_pass_inputs() -> None:
    result = export_gate(
        {
            "gate_results": {},
            "approvals": {"final_report": "approved"},
            "artifacts": {"valuation_lock": {"locked": True}},
            "valuation_outputs": {
                "snapshot_id": "snap1",
                "missing_formula_trace_count": 1,
                "debt_forecast_missing": True,
            },
            "draft_report": {
                "snapshot_id": "snap1",
                "tier3_only_material_count": 1,
                "generic_citation_count": 1,
            },
            "evaluation_results": {"llm_only_pass": True},
        },
        final_approval_required=True,
    )

    assert result["passed"] is False
    assert result["status"] == "fail"
    assert result["severity"] == "critical"
    assert result["issues"]
    assert all(issue["blocking"] for issue in result["issues"])
    assert "tier3_only_material_fact" in result["blocking_reasons"]
    assert "generic_citation_only" in result["blocking_reasons"]
