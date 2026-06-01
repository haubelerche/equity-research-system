from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.harness.state import ArtifactRef, EvidenceRef, ServiceNodeResult, stable_hash

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025


def _result(node_name: str, status: str, summary: dict[str, Any], **kwargs) -> ServiceNodeResult:
    return ServiceNodeResult(
        node_name=node_name,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        output_hash=stable_hash(summary),
        **kwargs,
    )


def build_facts_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR) -> ServiceNodeResult:
    from scripts.build_facts import build_facts

    artifact = build_facts(ticker=ticker, from_year=from_year, to_year=to_year, strict_completeness=False)
    validation = artifact.get("validation", {})
    snapshot_id = artifact.get("snapshot_id")
    artifact_path = artifact.get("artifact_path", "")
    summary = {
        "ticker": ticker,
        "snapshot_id": snapshot_id,
        "artifact_path": artifact_path,
        "valuation_gate": validation.get("valuation_gate"),
        "valuation_ready": validation.get("valuation_ready"),
        "source_tier_coverage_status": validation.get("source_tier_coverage_status"),
        "reconciliation_status": validation.get("reconciliation_status"),
        "coverage_gate": validation.get("coverage_gate"),
        "core_keys_gate": validation.get("core_keys_gate"),
        "source_validation_gate": validation.get("source_validation_gate"),
        "blocking_reasons": validation.get("blocking_reasons", []),
        "periods_available": artifact.get("periods_available", []),
    }
    return _result(
        "BUILD_FACTS",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_fact_report",
                artifact_type="fact_report_json",
                section_key="facts",
                is_locked=False,
                storage_path=artifact_path if artifact_path else None,
                producer="BUILD_FACTS",
            )
        ],
    )


def auto_ingest_tool(
    ticker: str,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    ocr: bool = False,
) -> ServiceNodeResult:
    """Run auto-ingestion of official documents (web + PDF) for *ticker*.

    Non-blocking: if ingestion fails, returns status='completed' with warn info
    in the summary and the pipeline continues with Tier-3-only facts. The warning
    is recorded in state.artifacts.
    """
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from scripts.auto_ingest_official_documents import AutoIngestConfig, run_pipeline as _run
        cfg = AutoIngestConfig(
            ticker=ticker,
            from_year=from_year,
            to_year=to_year,
            dry_run=False,
            channels=["cafef", "pdf"],
            ocr=ocr,
        )
        results = _run(cfg)
        promoted = sum(r.promoted for r in results)
        summary: dict = {
            "ticker": ticker,
            "promoted": promoted,
            "channels_run": len(results),
            "status": "completed",
        }
        node_status = "completed"
    except Exception as exc:  # noqa: BLE001
        summary = {
            "ticker": ticker,
            "promoted": 0,
            "status": "warn",
            "warning": f"auto_ingest skipped: {str(exc)[:200]}",
        }
        node_status = "completed"
        _logger.warning(
            "auto_ingest_tool failed for %s — pipeline continues with Tier-3 facts only: %s",
            ticker, exc,
        )
    return _result("AUTO_INGEST", node_status, summary)


def build_index_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR) -> ServiceNodeResult:
    from scripts.build_index import build_index

    summary = build_index(ticker=ticker, years=list(range(from_year, to_year + 1)))
    return _result(
        "BUILD_INDEX",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(artifact_id=f"{ticker}_index_summary", artifact_type="source_manifest_json", section_key="index")
        ],
        evidence_refs=[
            EvidenceRef(evidence_type="document_chunk", metadata={"indexed_chunks": summary.get("chunks_inserted", 0)})
        ],
    )


def run_valuation_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR) -> ServiceNodeResult:
    from scripts.run_valuation import run_valuation

    artifact = run_valuation(ticker=ticker, from_year=from_year, to_year=to_year)
    summary = {
        "ticker": ticker,
        "snapshot_id": artifact.get("snapshot_id"),
        "formula_version": artifact.get("formula_version"),
        "assumption_version": artifact.get("assumption_version"),
        "unit_policy": artifact.get("unit_policy"),
        "currency": artifact.get("currency"),
        "period_scope": artifact.get("period_scope"),
        "valuation_methods": artifact.get("valuation_methods", []),
        "has_fcff": bool(artifact.get("fcff")),
        "has_fcfe": bool(artifact.get("fcfe")),
        "has_blend": bool(artifact.get("blend_dcf")),
        "has_sensitivity": bool(artifact.get("sensitivity")),
        "sensitivity_summary": artifact.get("sensitivity", {}),
        "assumptions": artifact.get("assumptions", {}),
        "assumption_gate": artifact.get("assumption_gate", {}),
        "valuation_confidence": artifact.get("valuation_confidence", {}),
    }
    return _result(
        "VALUATION_DRAFT",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_valuation",
                artifact_type="valuation_result_json",
                section_key="valuation_draft",
                is_locked=False,
            )
        ],
    )


def generate_report_tool(
    ticker: str,
    snapshot_id: str | None,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    mode: str = "draft",
) -> ServiceNodeResult:
    from scripts.generate_report import generate_report

    artifact = generate_report(
        ticker=ticker,
        from_year=from_year,
        to_year=to_year,
        report_type="full_report",
        snapshot_id=snapshot_id,
        mode=mode,
    )
    summary = {
        "ticker": ticker,
        "report_path": artifact.get("report_path"),
        "snapshot_id": artifact.get("snapshot_id"),
        "export_blocked": artifact.get("export_blocked", False),
        "source_tier_gate": artifact.get("source_tier_gate", {}),
        "claims_count": len(artifact.get("claims", [])),
        "citation_count": len(artifact.get("citation_map", {})),
    }
    return _result(
        "REPORT_GENERATION",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_report_{mode}",
                artifact_type="report_md",
                section_key=f"full_report_{mode}",
                storage_path=artifact.get("report_path"),
                is_locked=False,
            )
        ],
    )


def evaluate_quality_tool(ticker: str, report_path: str | None = None) -> ServiceNodeResult:
    from scripts.evaluate_report_quality import run_quality_gate
    from scripts.evaluate_report_quality import _latest_file, _load_json

    root = Path.cwd()
    artifacts = root / "artifacts"
    forecast_dir = artifacts / "forecast"
    valuation_dir = artifacts / "valuation"

    forecast_path = _latest_file(forecast_dir, ticker, "forecast")
    fcff_path = _latest_file(forecast_dir, ticker, "fcff")
    fcfe_path = _latest_file(forecast_dir, ticker, "fcfe")
    multiples_path = _latest_file(valuation_dir, ticker, "multiples")
    gate_path = _latest_file(valuation_dir, ticker, "gate")
    confidence_path = _latest_file(valuation_dir, ticker, "confidence")

    report_md = None
    if report_path and Path(report_path).exists():
        report_md = Path(report_path).read_text(encoding="utf-8")

    summary = run_quality_gate(
        ticker=ticker,
        forecast=_load_json(forecast_path) if forecast_path else None,
        fcff=_load_json(fcff_path) if fcff_path else None,
        fcfe=_load_json(fcfe_path) if fcfe_path else None,
        multiples=_load_json(multiples_path) if multiples_path else None,
        gate=_load_json(gate_path) if gate_path else None,
        confidence=_load_json(confidence_path) if confidence_path else None,
        report_md=report_md,
    )
    status = "failed" if summary.get("overall_status") == "FAIL" else "completed"
    return _result(
        "QUALITY_EVALUATION",
        status,
        summary,
        blocking_reason="quality_gate_failed" if status == "failed" else None,
        artifact_refs=[
            ArtifactRef(artifact_id=f"{ticker}_quality_gate", artifact_type="eval_result_json", section_key="quality")
        ],
    )
