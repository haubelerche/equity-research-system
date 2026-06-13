from __future__ import annotations

from pathlib import Path

from backend.harness.state import ResearchGraphState
from backend.runtime_store import REQUIRED_SCHEMA_VERSION, to_db_status, to_public_status
from backend.schemas import RunStatus

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


def test_auto_exported_maps_to_published_draft():
    assert to_public_status("auto_exported") == "PUBLISHED_DRAFT"
    assert to_db_status("PUBLISHED_DRAFT") == "auto_exported"


def test_legacy_approved_still_maps_to_published():
    # Old rows persisted before migration 035 must still resolve.
    assert to_public_status("approved") == "PUBLISHED"


def test_published_draft_is_a_public_status_enum_member():
    assert RunStatus.PUBLISHED_DRAFT == "PUBLISHED_DRAFT"
