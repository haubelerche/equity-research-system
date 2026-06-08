from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.harness.state import ArtifactRef, EvidenceRef, ServiceNodeResult, stable_hash

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025


def _official_facts_ready(results: list[Any]) -> bool:
    """Require a ready status backed by at least one promoted official fact."""
    promoted = sum(int(getattr(result, "promoted", 0) or 0) for result in results)
    statuses = {
        getattr(
            getattr(result, "ingest_status", ""),
            "value",
            str(getattr(result, "ingest_status", "")),
        )
        for result in results
    }
    return promoted > 0 and bool(statuses & {"OFFICIAL_FACTS_READY", "OCR_PROMOTED"})


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
        cafef_rows = sum(r.cafef_rows for r in results)
        pdf_rows = sum(r.pdf_rows for r in results)
        ocr_candidates = sum(getattr(r, "ocr_candidates", 0) for r in results)
        ocr_promoted = sum(getattr(r, "ocr_promoted", 0) for r in results)
        statuses = [
            getattr(getattr(r, "ingest_status", ""), "value", str(getattr(r, "ingest_status", "")))
            for r in results
        ]
        official_ready = _official_facts_ready(results)
        summary: dict = {
            "ticker": ticker,
            "promoted": promoted,
            "channels_run": len(results),
            "status": "completed",
            "web_ingest_attempted": True,
            "cafef_rows": cafef_rows,
            "pdf_rows": pdf_rows,
            "ocr_candidates": ocr_candidates,
            "ocr_promoted": ocr_promoted,
            "year_statuses": statuses,
            "official_ready": official_ready,
            "continued_with_tier2_or_tier3_fallback": not official_ready,
        }
        node_status = "completed"
    except Exception as exc:  # noqa: BLE001
        summary = {
            "ticker": ticker,
            "promoted": 0,
            "status": "warn",
            "web_ingest_attempted": True,
            "cafef_rows": 0,
            "pdf_rows": 0,
            "ocr_candidates": 0,
            "ocr_promoted": 0,
            "year_statuses": [],
            "official_ready": False,
            "continued_with_tier2_or_tier3_fallback": True,
            "warning": f"auto_ingest skipped: {str(exc)[:200]}",
        }
        node_status = "completed"
        _logger.warning(
            "auto_ingest_tool failed for %s — pipeline continues with Tier-3 facts only: %s",
            ticker, exc,
        )
    return _result("AUTO_INGEST", node_status, summary)


def build_index_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR, run_id: str | None = None) -> ServiceNodeResult:
    from scripts.build_index import build_index

    summary = build_index(ticker=ticker, years=list(range(from_year, to_year + 1)))
    if run_id:
        out_dir = Path.cwd() / "artifacts" / "runs" / run_id
    else:
        out_dir = Path.cwd() / "artifacts" / "index"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    artifact_path = out_dir / f"{ticker.upper()}_{ts}_index_summary.json"
    artifact_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    summary["artifact_path"] = str(artifact_path)
    return _result(
        "BUILD_INDEX",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_index_summary",
                artifact_type="source_manifest_json",
                section_key="index",
                storage_path=str(artifact_path),
                producer="BUILD_INDEX",
            )
        ],
        evidence_refs=[
            EvidenceRef(evidence_type="document_chunk", metadata={"indexed_chunks": summary.get("chunks_inserted", 0)})
        ],
    )


def run_valuation_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR) -> ServiceNodeResult:
    from scripts.run_valuation import run_valuation

    artifact = run_valuation(ticker=ticker, from_year=from_year, to_year=to_year)
    artifact_path = artifact.get("artifact_path", "")
    formula_traces = artifact.get("formula_traces") or []
    summary = {
        "ticker": ticker,
        "snapshot_id": artifact.get("snapshot_id"),
        "artifact_path": artifact_path,
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
        "formula_trace_status": "present" if formula_traces else "missing",
        "formula_trace_count": len(formula_traces),
        "missing_formula_trace_count": 0 if formula_traces else 1,
        "formula_traces": formula_traces,
    }
    refs = [
        ArtifactRef(
            artifact_id=f"{ticker}_valuation",
            artifact_type="valuation_result_json",
            section_key="valuation",
            is_locked=False,
            storage_path=artifact_path if artifact_path else None,
            producer="VALUATION_RUN",
        )
    ]
    for key in ("forecast", "fcff", "fcfe", "blend_dcf"):
        payload = artifact.get(key)
        if not isinstance(payload, dict):
            continue
        nested_path = payload.get("artifact_path")
        if nested_path:
            refs.append(
                ArtifactRef(
                    artifact_id=f"{ticker}_{key}",
                    artifact_type="valuation_component_json",
                    section_key="blend" if key == "blend_dcf" else key,
                    is_locked=False,
                    storage_path=nested_path,
                    producer="VALUATION_RUN",
                )
            )
    return _result(
        "VALUATION_DRAFT",
        "completed",
        summary,
        artifact_refs=refs,
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
        "artifact_path": artifact.get("report_path"),
        "snapshot_id": artifact.get("snapshot_id"),
        "export_blocked": artifact.get("export_blocked", False),
        "source_tier_gate": artifact.get("source_tier_gate", {}),
        "claims_count": len(artifact.get("claims", [])),
        "citation_count": len(artifact.get("citation_map", {})),
        "valuation_result_path": artifact.get("valuation_result_path"),
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
                producer="REPORT_GENERATION",
            )
        ] + [
            ArtifactRef(
                artifact_id=f"{ticker}_{key}_{mode}",
                artifact_type="run_log_json",
                section_key=key,
                storage_path=artifact.get(path_key),
                is_locked=False,
                producer="REPORT_GENERATION",
            )
            for key, path_key in (
                ("forecast", "forecast_path"),
                ("fcff", "fcff_path"),
                ("fcfe", "fcfe_path"),
                ("blend", "blend_path"),
                ("citation", "citation_path"),
                ("valuation_result", "valuation_result_path"),
            )
            if artifact.get(path_key)
        ],
    )


def read_valuation_artifact_tool(artifact_path: str | None) -> ServiceNodeResult:
    if not artifact_path:
        return _result(
            "READ_VALUATION_ARTIFACT",
            "failed",
            {"artifact_path": artifact_path, "blocking_reason": "valuation_artifact_path_missing"},
            blocking_reason="valuation_artifact_path_missing",
        )
    path = Path(artifact_path)
    if not path.exists():
        return _result(
            "READ_VALUATION_ARTIFACT",
            "failed",
            {"artifact_path": artifact_path, "blocking_reason": "valuation_artifact_not_found"},
            blocking_reason="valuation_artifact_not_found",
        )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    traces = artifact.get("formula_traces") or []
    summary = {
        "artifact_path": str(path),
        "ticker": artifact.get("ticker"),
        "snapshot_id": artifact.get("snapshot_id"),
        "valuation_methods": artifact.get("valuation_methods", []),
        "formula_trace_status": "present" if traces else "missing",
        "formula_trace_count": len(traces),
        "formula_traces": traces[:50],
    }
    return _result(
        "READ_VALUATION_ARTIFACT",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{artifact.get('ticker', 'ticker')}_valuation_read",
                artifact_type="valuation_result_json",
                section_key="valuation_read",
                storage_path=str(path),
                producer="READ_VALUATION_ARTIFACT",
            )
        ],
    )


def read_snapshot_tool(ticker: str, snapshot_id: str | None) -> ServiceNodeResult:
    if not snapshot_id:
        return _result(
            "READ_SNAPSHOT",
            "failed",
            {"ticker": ticker, "snapshot_id": snapshot_id, "blocking_reason": "snapshot_id_missing"},
            blocking_reason="snapshot_id_missing",
        )
    from backend.dataops.snapshot import load_snapshot_facts

    try:
        facts = load_snapshot_facts(snapshot_id)
    except Exception as exc:  # noqa: BLE001
        return _result(
            "READ_SNAPSHOT",
            "failed",
            {"ticker": ticker, "snapshot_id": snapshot_id, "blocking_reason": f"snapshot_read_failed:{exc}"},
            blocking_reason="snapshot_read_failed",
        )
    periods = sorted({f"{row.get('fiscal_year')}FY" for row in facts if row.get("fiscal_year")})
    metric_ids = sorted({str(row.get("line_item_code")) for row in facts if row.get("line_item_code")})
    source_tiers = sorted({
        int(row.get("source_tier"))
        for row in facts
        if row.get("source_tier") is not None
    })
    summary = {
        "ticker": ticker,
        "snapshot_id": snapshot_id,
        "facts_count": len(facts),
        "periods": periods,
        "metric_ids": metric_ids[:100],
        "source_tiers": source_tiers,
        "sample_facts": facts[:20],
    }
    return _result(
        "READ_SNAPSHOT",
        "completed",
        summary,
        evidence_refs=[
            EvidenceRef(
                evidence_type="financial_fact",
                evidence_id=snapshot_id,
                metadata={"facts_count": len(facts), "periods": periods, "metric_count": len(metric_ids)},
            )
        ],
    )


def read_ratio_artifact_tool(ticker: str, snapshot_id: str | None, run_id: str | None = None) -> ServiceNodeResult:
    if not snapshot_id:
        return _result(
            "READ_RATIO_ARTIFACT",
            "failed",
            {"ticker": ticker, "snapshot_id": snapshot_id, "blocking_reason": "snapshot_id_missing"},
            blocking_reason="snapshot_id_missing",
        )
    from backend.analytics.ratios import compute_ratios
    from backend.dataops.snapshot import load_snapshot_facts
    from backend.facts.normalizer import build_fact_table, compute_derived, periods_sorted

    try:
        raw_facts = load_snapshot_facts(snapshot_id)
    except Exception as exc:  # noqa: BLE001
        return _result(
            "READ_RATIO_ARTIFACT",
            "failed",
            {"ticker": ticker, "snapshot_id": snapshot_id, "blocking_reason": f"ratio_snapshot_read_failed:{exc}"},
            blocking_reason="ratio_snapshot_read_failed",
        )
    fact_table = compute_derived(build_fact_table(raw_facts))
    periods = sorted(p for p in periods_sorted(fact_table) if str(p).endswith("FY"))
    ratios = compute_ratios(fact_table)
    ratio_payload = {
        "ticker": ticker,
        "snapshot_id": snapshot_id,
        "periods": periods,
        "ratios": {metric: dict(values) for metric, values in ratios.items()},
        "metric_ids": sorted(ratios.keys()),
        "unit": "ratio",
    }
    if run_id:
        out_dir = Path.cwd() / "artifacts" / "runs" / run_id
    else:
        out_dir = Path.cwd() / "artifacts" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    artifact_path = out_dir / f"{ticker.upper()}_{ts}_ratio_artifact.json"
    artifact_path.write_text(json.dumps(ratio_payload, indent=2, default=str), encoding="utf-8")
    return _result(
        "READ_RATIO_ARTIFACT",
        "completed",
        {**ratio_payload, "artifact_path": str(artifact_path)},
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_ratio_artifact",
                artifact_type="ratio_artifact_json",
                section_key="ratios",
                storage_path=str(artifact_path),
                producer="READ_RATIO_ARTIFACT",
            )
        ],
    )


def evaluate_quality_tool(
    ticker: str,
    report_path: str | None = None,
    valuation_path: str | None = None,
) -> ServiceNodeResult:
    from scripts.evaluate_report_quality import run_quality_gate
    from scripts.evaluate_report_quality import _load_json

    valuation_artifact = _load_json(Path(valuation_path)) if valuation_path else None
    if valuation_artifact:
        forecast = valuation_artifact.get("forecast")
        fcff = valuation_artifact.get("fcff")
        fcfe = valuation_artifact.get("fcfe")
        multiples = valuation_artifact.get("multiples")
        gate = valuation_artifact.get("assumption_gate") or valuation_artifact.get("gate")
        confidence = valuation_artifact.get("valuation_confidence")
    else:
        return _result(
            "QUALITY_EVALUATION",
            "failed",
            {"ticker": ticker, "overall_status": "FAIL", "blocking_reason": "run_scoped_valuation_artifact_missing"},
            blocking_reason="run_scoped_valuation_artifact_missing",
        )

    report_md = None
    if report_path and Path(report_path).exists():
        report_md = Path(report_path).read_text(encoding="utf-8")

    summary = run_quality_gate(
        ticker=ticker,
        forecast=forecast,
        fcff=fcff,
        fcfe=fcfe,
        multiples=multiples,
        gate=gate,
        confidence=confidence,
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
