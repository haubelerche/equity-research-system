from __future__ import annotations

from pathlib import Path

from backend.harness.state import ResearchGraphState
from backend.runtime_store import REQUIRED_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_migration_035_adds_auto_exported_and_keeps_approved():
    sql = (ROOT / "backend/database/migrations/035_runs_status_auto_exported.sql").read_text(encoding="utf-8")
    assert "auto_exported" in sql
    # Backward compatibility: existing rows using 'approved' must stay valid.
    assert "'approved'" in sql
    assert "runs_status_check" in sql


def test_required_schema_version_points_at_035():
    assert REQUIRED_SCHEMA_VERSION == "035_runs_status_auto_exported"


def test_run_state_accepts_auto_exported():
    state = ResearchGraphState(run_id="r1", ticker="DHG", objective="t", status="auto_exported")
    assert state.status == "auto_exported"
