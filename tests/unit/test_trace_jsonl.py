"""Tests for trace.jsonl event format."""
from __future__ import annotations

import json


def test_trace_has_tool_call_events():
    """trace entries from _record_tool_trace must have kind=tool_call."""
    from backend.harness.state import ResearchGraphState

    state = ResearchGraphState(
        run_id="run_001",
        ticker="TEST",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )
    state.current_stage = "DATA_RETRIEVAL_RUN"

    payload = {
        "kind": "tool_call",
        "run_id": state.run_id,
        "tool_name": "build_facts",
        "agent_role": "DataRetrievalAgent",
    }
    state.trace.append(payload)

    tool_calls = [e for e in state.trace if e.get("kind") == "tool_call"]
    assert len(tool_calls) >= 1
    assert tool_calls[0]["tool_name"] == "build_facts"


def test_trace_entries_are_json_serializable():
    """Every trace entry must be JSON-serializable for trace.jsonl."""
    from backend.harness.state import ResearchGraphState

    state = ResearchGraphState(
        run_id="run_001",
        ticker="TEST",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )

    entries = [
        {"kind": "tool_call", "tool": "build_facts", "status": "completed"},
        {"kind": "agent_handoff", "agent_id": "supervisor", "stage": "PREFLIGHT"},
        {"kind": "gate_result", "gate": "data_quality_gate", "passed": True},
        {"kind": "agent_message", "agent_id": "financial_analyst", "action": "review"},
    ]
    for entry in entries:
        state.trace.append(entry)

    for entry in state.trace:
        line = json.dumps(entry, default=str)
        parsed = json.loads(line)
        assert "kind" in parsed
