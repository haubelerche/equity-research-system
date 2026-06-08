"""Test: _resolve_artifact raises ValueError without manifest (no glob fallback)."""
from __future__ import annotations

import pytest


def test_no_glob_in_production():
    """Spec §1.4: _resolve_artifact without manifest must raise ValueError."""
    from backend.reporting.report_data_loader import _resolve_artifact

    with pytest.raises(ValueError, match="run_id is required"):
        _resolve_artifact("valuation", "artifacts/valuation/*.json", manifest=None)


def test_resolve_with_allow_latest_still_works():
    """Dev scripts may pass allow_latest_artifacts=True — this should still use glob."""
    from backend.reporting.report_data_loader import _resolve_artifact

    # With allow_latest_artifacts=True and no matching files, should return {}
    result = _resolve_artifact(
        "valuation",
        "artifacts/nonexistent_dir_12345/*.json",
        manifest=None,
        allow_latest_artifacts=True,
    )
    assert result == {}
