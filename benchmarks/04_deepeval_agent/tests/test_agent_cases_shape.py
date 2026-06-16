from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def test_agent_cases_include_seeded_failures_and_roles():
    path = ROOT / "04_deepeval_agent" / "deepeval_cases" / "agent_cases.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    roles = {r["agent_role"] for r in rows}
    assert "SeniorCriticAgent" in roles
    assert any(r.get("input", {}).get("seeded_issue") for r in rows)
    assert all("deepeval_metrics" in r for r in rows)
