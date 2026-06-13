"""Fail-closed authorization for client-final report rendering."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class PublicationBlockedError(RuntimeError):
    """Raised when a run is not authorized for client-final rendering."""


@dataclass(frozen=True)
class ClientFinalAuthorization:
    run_id: str
    ticker: str
    snapshot_id: str
    fpts_score: float


@dataclass(frozen=True)
class PublicationReadiness:
    passed: bool
    blocking_reasons: tuple[str, ...]
    snapshot_id: str | None = None
    fpts_score: float | None = None


def _latest_by_section(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        section_key = artifact.get("section_key")
        if section_key:
            latest[str(section_key)] = artifact
    return latest


def _payload(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    payload = artifact.get("payload")
    return payload if isinstance(payload, dict) else {}


def evaluate_client_final_readiness(
    *,
    run: dict[str, Any] | None,
    artifacts: list[dict[str, Any]],
    final_approval: dict[str, Any] | None,
    ticker: str,
) -> PublicationReadiness:
    """Evaluate all governance conditions required for a client-final render."""
    reasons: list[str] = []
    expected_ticker = ticker.strip().upper()

    if not run:
        return PublicationReadiness(False, ("run_missing",))
    if str(run.get("ticker") or "").upper() != expected_ticker:
        reasons.append("run_ticker_mismatch")
    if run.get("status") != "approved":
        reasons.append(f"run_not_approved:{run.get('status') or 'missing'}")
    if not final_approval or final_approval.get("decision") != "approved":
        reasons.append("final_report_approval_missing")

    sections = _latest_by_section(artifacts)
    publishable = sections.get("publishable_final_report_model")
    if not publishable:
        reasons.append("publishable_final_report_model_missing")
    elif not publishable.get("is_locked"):
        reasons.append("publishable_final_report_model_not_locked")

    package = _payload(sections.get("quality_gate")).get("PACKAGE_VALIDATION_GATE") or {}
    if package.get("passed") is not True:
        reasons.append("package_validation_not_passed")

    fpts = _payload(sections.get("fpts_grade_evaluation"))
    fpts_score = fpts.get("score")
    if (
        fpts.get("passed") is not True
        or fpts.get("decision") != "allow_export"
        or not isinstance(fpts_score, (int, float))
        or float(fpts_score) < 85
    ):
        reasons.append("fpts_grade_not_publishable")

    publishable_payload = _payload(publishable)
    valuation_payload = _payload(sections.get("valuation"))
    publishable_snapshot = publishable_payload.get("snapshot_id")
    valuation_snapshot = valuation_payload.get("snapshot_id")
    if not publishable_snapshot or not valuation_snapshot:
        reasons.append("artifact_snapshot_id_missing")
    elif publishable_snapshot != valuation_snapshot:
        reasons.append("artifact_snapshot_mismatch")

    return PublicationReadiness(
        passed=not reasons,
        blocking_reasons=tuple(sorted(set(reasons))),
        snapshot_id=str(publishable_snapshot) if publishable_snapshot else None,
        fpts_score=float(fpts_score) if isinstance(fpts_score, (int, float)) else None,
    )


def authorize_client_final(
    *,
    run_id: str,
    ticker: str,
    store: Any | None = None,
) -> ClientFinalAuthorization:
    """Return a scoped authorization token or raise with exact blocking reasons."""
    if store is None:
        from backend.runtime_store import RuntimeStore

        store = RuntimeStore()

    readiness = evaluate_client_final_readiness(
        run=store.get_run(run_id),
        artifacts=store.list_artifacts(run_id),
        final_approval=store.get_latest_approval(run_id, "final_report"),
        ticker=ticker,
    )
    if not readiness.passed:
        raise PublicationBlockedError(
            "client_final_render_blocked:" + ",".join(readiness.blocking_reasons)
        )
    return ClientFinalAuthorization(
        run_id=run_id,
        ticker=ticker.strip().upper(),
        snapshot_id=str(readiness.snapshot_id),
        fpts_score=float(readiness.fpts_score),
    )


def assert_client_final_authorization(
    authorization: ClientFinalAuthorization | None,
    *,
    run_id: str,
    ticker: str,
) -> None:
    """Reject direct client-final renderer calls without a matching authorization."""
    if authorization is None:
        raise PublicationBlockedError("client_final_render_blocked:authorization_missing")
    if authorization.run_id != run_id:
        raise PublicationBlockedError("client_final_render_blocked:authorization_run_mismatch")
    if authorization.ticker != ticker.strip().upper():
        raise PublicationBlockedError("client_final_render_blocked:authorization_ticker_mismatch")
