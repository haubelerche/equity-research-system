from __future__ import annotations

import pytest

from backend.reporting.publication_readiness import (
    PublicationBlockedError,
    authorize_client_final,
    evaluate_client_final_readiness,
)


def _artifacts(snapshot_id: str = "snap-1") -> list[dict]:
    return [
        {"section_key": "company_research_pack", "payload": {"schema_version": "2.0"}},
        {"section_key": "analyst_insight_pack", "payload": {"schema_version": "2.0"}},
        {
            "section_key": "valuation",
            "payload": {"snapshot_id": snapshot_id},
            "is_locked": True,
        },
        {
            "section_key": "report_quality_evaluation",
            "payload": {"passed": True, "decision": "allow_export", "score": 90},
            "is_locked": False,
        },
        {
            "section_key": "quality_gate",
            "payload": {"PACKAGE_VALIDATION_GATE": {"passed": True}},
            "is_locked": False,
        },
        {
            "section_key": "publishable_final_report_model",
            "payload": {"snapshot_id": snapshot_id},
            "is_locked": True,
        },
    ]


def test_client_final_readiness_requires_all_governance_evidence() -> None:
    result = evaluate_client_final_readiness(
        run={"ticker": "DHG", "status": "approved"},
        artifacts=_artifacts(),
        final_approval={"decision": "approved"},
        ticker="DHG",
    )

    assert result.passed
    assert result.snapshot_id == "snap-1"
    assert result.report_quality_score == 90


def test_client_final_readiness_blocks_snapshot_mismatch_and_unapproved_run() -> None:
    artifacts = _artifacts()
    artifacts[-1]["payload"]["snapshot_id"] = "snap-stale"

    result = evaluate_client_final_readiness(
        run={"ticker": "DHG", "status": "auto_exported"},
        artifacts=artifacts,
        final_approval=None,
        ticker="DHG",
    )

    assert not result.passed
    assert set(result.blocking_reasons) >= {
        "artifact_snapshot_mismatch",
        "final_report_approval_missing",
        "run_not_approved:auto_exported",
    }


def test_authorize_client_final_fails_closed() -> None:
    class Store:
        def get_run(self, run_id):
            return {"ticker": "DHG", "status": "blocked"}

        def list_artifacts(self, run_id):
            return []

        def get_latest_approval(self, run_id, approval_stage):
            return None

    with pytest.raises(PublicationBlockedError, match="client_final_render_blocked"):
        authorize_client_final(run_id="run-1", ticker="DHG", store=Store())
