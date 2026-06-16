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


def test_client_final_readiness_passes_when_report_present() -> None:
    result = evaluate_client_final_readiness(
        run={"ticker": "DHG", "status": "approved"},
        artifacts=_artifacts(),
        final_approval={"decision": "approved"},
        ticker="DHG",
    )

    assert result.passed
    assert result.snapshot_id == "snap-1"
    assert result.report_quality_score == 90


def test_does_not_block_on_unapproved_run_quality_or_package() -> None:
    # Decision (2026-06-16): no human-in-the-loop approval gates. The PDF is for the
    # analyst to read and judge; the pipeline must publish the final report and disclose
    # quality, not block on run-approval / final-approval / quality-score / package.
    artifacts = _artifacts()
    # Make every governance gate "fail"/missing: still must publish.
    for a in artifacts:
        if a["section_key"] == "report_quality_evaluation":
            a["payload"] = {"passed": False, "decision": "block", "score": 10}
        if a["section_key"] == "quality_gate":
            a["payload"] = {"PACKAGE_VALIDATION_GATE": {"passed": False}}

    result = evaluate_client_final_readiness(
        run={"ticker": "DHG", "status": "auto_exported"},
        artifacts=artifacts,
        final_approval=None,
        ticker="DHG",
    )

    assert result.passed, result.blocking_reasons
    assert result.snapshot_id == "snap-1"


def test_still_blocks_on_snapshot_mismatch() -> None:
    # Snapshot consistency is correctness, not an approval gate: a report whose model
    # and valuation come from different snapshots has inconsistent numbers — still block.
    artifacts = _artifacts()
    artifacts[-1]["payload"]["snapshot_id"] = "snap-stale"
    result = evaluate_client_final_readiness(
        run={"ticker": "DHG", "status": "auto_exported"},
        artifacts=artifacts,
        final_approval=None,
        ticker="DHG",
    )
    assert not result.passed
    assert "artifact_snapshot_mismatch" in result.blocking_reasons
    # Approval gates must NOT appear anymore.
    assert not any("approv" in r for r in result.blocking_reasons)


def test_missing_snapshot_payload_does_not_block() -> None:
    # RuntimeStore.list_artifacts returns metadata without inline payloads, so the
    # snapshot ids read as absent. Absent (vs an actual mismatch) must NOT block —
    # otherwise every real run false-blocks on artifact_snapshot_id_missing.
    artifacts = _artifacts()
    for a in artifacts:
        if a["section_key"] == "valuation":
            a["payload"] = {}  # no snapshot_id available
    result = evaluate_client_final_readiness(
        run={"ticker": "DHG", "status": "auto_exported"},
        artifacts=artifacts,
        final_approval=None,
        ticker="DHG",
    )
    assert result.passed, result.blocking_reasons


def test_authorize_blocks_only_when_no_report_exists() -> None:
    class Store:
        def get_run(self, run_id):
            return {"ticker": "DHG", "status": "blocked"}

        def list_artifacts(self, run_id):
            return []  # no report model at all → nothing to publish

        def get_latest_approval(self, run_id, approval_stage):
            return None

    with pytest.raises(PublicationBlockedError, match="client_final_render_blocked"):
        authorize_client_final(run_id="run-1", ticker="DHG", store=Store())
