from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from datetime import date
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.harness.state import ArtifactRef, EvidenceRef, ServiceNodeResult, stable_hash
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR

MVP_FROM_YEAR = DEFAULT_FROM_YEAR
MVP_TO_YEAR = DEFAULT_TO_YEAR


def _persist_run_file(run_id: str, artifact_name: str, local_path: str) -> tuple[str, str, str]:
    from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

    adapter = SupabaseStorageAdapter()
    path = Path(local_path)
    key = run_artifact_key(run_id, artifact_name)
    checksum = adapter.checksum_file(path)
    if adapter.exists(RUNS_BUCKET, key):
        if not adapter.validate_checksum(RUNS_BUCKET, key, checksum):
            adapter.upload_file(RUNS_BUCKET, key, path, None, upsert=True)
    else:
        adapter.upload_file(RUNS_BUCKET, key, path, None)
    if not adapter.validate_checksum(RUNS_BUCKET, key, checksum):
        raise RuntimeError(f"Checksum validation failed: {RUNS_BUCKET}/{key}")
    path.unlink(missing_ok=True)
    return RUNS_BUCKET, key, checksum


def _persist_run_json(run_id: str, artifact_name: str, payload: dict[str, Any]) -> tuple[str, str]:
    from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

    key = run_artifact_key(run_id, artifact_name)
    adapter = SupabaseStorageAdapter()
    if adapter.exists(RUNS_BUCKET, key):
        existing = adapter.download_json(RUNS_BUCKET, key)
        if stable_hash(existing) != stable_hash(payload):
            raise FileExistsError(f"Refusing overwrite with different checksum: {RUNS_BUCKET}/{key}")
    else:
        adapter.upload_json(RUNS_BUCKET, key, payload)
    return RUNS_BUCKET, key


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _result(node_name: str, status: str, summary: dict[str, Any], **kwargs) -> ServiceNodeResult:
    safe_summary = _json_safe(summary)
    return ServiceNodeResult(
        node_name=node_name,
        status=status,  # type: ignore[arg-type]
        summary=safe_summary,
        output_hash=stable_hash(safe_summary),
        **kwargs,
    )


def build_facts_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR, run_id: str | None = None) -> ServiceNodeResult:
    from scripts.build_facts import build_facts

    artifact = build_facts(
        ticker=ticker,
        from_year=from_year,
        to_year=to_year,
        strict_completeness=False,
        run_id=run_id,
    )
    validation = artifact.get("validation", {})
    snapshot_id = artifact.get("snapshot_id")
    artifact_path = artifact.get("artifact_path", "")
    storage_bucket = storage_path = checksum = None
    if run_id and artifact_path:
        storage_bucket, storage_path, checksum = _persist_run_file(run_id, "facts_snapshot.json", artifact_path)
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
        "storage_bucket": storage_bucket,
        "storage_path": storage_path,
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
                storage_bucket=storage_bucket,
                storage_path=storage_path,
                checksum=checksum,
                producer="BUILD_FACTS",
            )
        ],
    )


def auto_ingest_tool(
    ticker: str,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    ocr: bool = False,
    progress_cb=None,
) -> ServiceNodeResult:
    """Run auto-ingestion of official documents (web + PDF) for *ticker*.

    Non-blocking: if ingestion fails, returns status='completed' with warn info
    in the summary and the pipeline continues with Tier-3-only facts. The warning
    is recorded in state.artifacts. ``progress_cb(substep, detail)`` is an
    optional hook for the live progress UI.
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
            progress_cb=progress_cb,
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
    storage_bucket = storage_path = None
    return _result(
        "BUILD_INDEX",
        "completed",
        summary,
        evidence_refs=[
            EvidenceRef(evidence_type="document_chunk", metadata={"indexed_chunks": summary.get("chunks_inserted", 0)})
        ],
    )


def run_valuation_tool(
    ticker: str,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    run_id: str | None = None,
    auto_approve_assumptions: bool = False,
) -> ServiceNodeResult:
    import os
    from scripts import run_valuation as valuation_module

    # Stage the run-scoped artifact in a temp dir, never inside the repo tree.
    # The harness uploads it to Supabase Storage and the staging dir is removed.
    staging_dir: str | None = None
    if run_id:
        os.environ["RUN_ID"] = run_id
        staging_dir = tempfile.mkdtemp(prefix=f"valuation-{run_id}-")
        valuation_module.VALUATION_DIR = Path(staging_dir)
    artifact = valuation_module.run_valuation(
        ticker=ticker,
        from_year=from_year,
        to_year=to_year,
        auto_approve_assumptions=auto_approve_assumptions,
    )
    artifact_path = artifact.get("artifact_path", "")
    storage_bucket = storage_path = checksum = None
    try:
        if run_id and artifact_path:
            storage_bucket, storage_path, checksum = _persist_run_file(run_id, "valuation.json", artifact_path)
    finally:
        if staging_dir:
            shutil.rmtree(staging_dir, ignore_errors=True)
    formula_traces = artifact.get("formula_traces") or []
    summary = dict(artifact)
    from backend.evaluation.report_quality import build_valuation_bridge

    valuation_bridge = build_valuation_bridge(artifact)
    artifact["valuation_bridge"] = valuation_bridge
    summary["valuation_bridge"] = valuation_bridge
    fcff = artifact.get("fcff") or {}
    fcfe = artifact.get("fcfe") or {}
    blend = artifact.get("blend_dcf") or {}
    net_debt = fcff.get("net_debt")
    cash = abs(net_debt) if isinstance(net_debt, (int, float)) and net_debt < 0 else 0
    debt = net_debt if isinstance(net_debt, (int, float)) and net_debt > 0 else 0
    wacc_breakdown = fcff.get("wacc_breakdown") or {}
    expected_market_return = wacc_breakdown.get("expected_market_return")
    risk_free_rate = wacc_breakdown.get("risk_free_rate")
    equity_risk_premium = wacc_breakdown.get("equity_risk_premium")
    if equity_risk_premium is None and isinstance(expected_market_return, (int, float)) and isinstance(risk_free_rate, (int, float)):
        equity_risk_premium = expected_market_return - risk_free_rate
    key_assumptions = {
        **wacc_breakdown,
        "equity_risk_premium": equity_risk_premium,
        "wacc": fcff.get("wacc"),
        "terminal_growth": fcff.get("terminal_growth") or fcfe.get("terminal_growth"),
        "net_borrowing": ((artifact.get("forecast") or {}).get("debt_schedule") or {}),
    }
    target_price = blend.get("target_price_dcf_vnd")
    current_price = artifact.get("current_price_vnd")
    upside = blend.get("upside_pct")
    recommendation = None
    if isinstance(upside, (int, float)):
        recommendation = "BUY" if upside > 0.15 else "SELL" if upside < -0.20 else "HOLD"
    summary.update({
        "selected_methods": ["FCFF", "FCFE"],
        "method_weights": {
            "FCFF": blend.get("fcff_weight", 0.6),
            "FCFE": blend.get("fcfe_weight", 0.4),
        },
        "approved_assumption_refs": ["auto_approve_assumptions" if run_id else "valuation_assumptions"],
        "key_assumptions": key_assumptions,
        "current_price": current_price,
        "recommendation": recommendation,
        "weighted_target_price": {
            "raw": target_price,
            "rounded": target_price,
            "upside_downside_vs_current_price": upside,
        },
        "sanity_checks": {
            "formula_trace_status": "pass" if formula_traces else "fail",
            "valuation_confidence": (artifact.get("valuation_confidence") or {}).get("final_rating"),
        },
        "sensitivity": artifact.get("sensitivity") or {},
        "fcff": {
            **fcff,
            "projected_fcff": {
                row.get("period") or row.get("label") or str(index): row.get("fcff")
                for index, row in enumerate(fcff.get("fcff_table") or [])
                if isinstance(row, dict)
            },
            "pv_of_fcff": fcff.get("sum_pv_fcff"),
            "pv_of_terminal_value": fcff.get("pv_terminal_value"),
            "cash_and_short_term_investments": cash,
            "debt": debt,
            "shares_outstanding": fcff.get("shares_mn"),
            "value_per_share": fcff.get("target_price_vnd"),
        },
        "fcfe": {
            **fcfe,
            "projected_fcfe": {
                row.get("period") or row.get("label") or str(index): row.get("fcfe")
                for index, row in enumerate(fcfe.get("fcfe_table") or [])
                if isinstance(row, dict)
            },
            "pv_of_fcfe": fcfe.get("sum_pv_fcfe"),
            "pv_of_terminal_value": fcfe.get("pv_terminal_value"),
            "shares_outstanding": fcfe.get("shares_mn"),
            "value_per_share": fcfe.get("target_price_vnd"),
        },
    })
    summary.update({
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
        "valuation_bridge": valuation_bridge,
        "storage_bucket": storage_bucket,
        "storage_path": storage_path,
    })
    refs = [
        ArtifactRef(
            artifact_id=f"{ticker}_valuation",
            artifact_type="valuation_result_json",
            section_key="valuation",
            is_locked=False,
            storage_bucket=storage_bucket,
            storage_path=storage_path,
            checksum=checksum,
            producer="VALUATION_RUN",
        )
    ]
    return _result(
        "VALUATION_DRAFT",
        "completed",
        summary,
        artifact_refs=refs,
    )


def run_forecast_tool(
    ticker: str,
    snapshot_id: str | None,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    run_id: str | None = None,
) -> ServiceNodeResult:
    """Build the authoritative deterministic forecast artifact for harness gates."""
    if not snapshot_id:
        return _result(
            "FORECAST_MODEL",
            "failed",
            {"ticker": ticker, "blocking_reason": "snapshot_id_missing"},
            blocking_reason="snapshot_id_missing",
        )

    from backend.analytics.forecasting import ForecastAssumptions, run_forecast
    from backend.dataops.snapshot import load_snapshot_facts
    from backend.facts.normalizer import (
        build_fact_table,
        compute_derived,
        load_golden_csv_supplement,
        to_analytics_vnd_bn,
    )

    raw_facts = load_snapshot_facts(snapshot_id)
    raw_facts += load_golden_csv_supplement(ticker, from_year=from_year, to_year=to_year)
    fact_table = compute_derived(to_analytics_vnd_bn(build_fact_table(raw_facts)))
    forecast = run_forecast(
        ticker=ticker,
        fact_table=fact_table,
        assumptions=ForecastAssumptions(assumption_status="default_unapproved"),
    ).to_dict()
    from backend.evaluation.report_quality import build_pharma_driver_model

    pharma_driver_model = build_pharma_driver_model(forecast)
    rows = {
        str(row.get("label")): row
        for row in forecast.get("forecast_years", [])
        if isinstance(row, dict) and row.get("label")
    }
    periods = sorted(rows)
    balance_passed = bool(rows) and all(
        all(row.get(key) is not None for key in ("total_assets", "equity", "total_debt", "other_liabilities"))
        and abs(
            float(row["total_assets"])
            - float(row["equity"])
            - float(row["total_debt"])
            - float(row["other_liabilities"])
        )
        <= 0.2
        for row in rows.values()
    )
    margin_passed = bool(rows) and all(
        row.get("gross_margin") is not None
        and 0 <= float(row["gross_margin"]) <= 1
        and row.get("net_margin") is not None
        and -1 <= float(row["net_margin"]) <= 1
        for row in rows.values()
    )
    cash_flow_passed = bool(rows) and all(
        row.get("depreciation") is not None
        and row.get("capex") is not None
        and (index == 0 or row.get("delta_nwc") is not None)
        for index, row in enumerate(rows.values())
    )
    wc_schedule = forecast.get("working_capital_schedule") or {}
    debt_schedule = forecast.get("debt_schedule") or {}
    cash_sweep = forecast.get("cash_sweep_artifact") or {}
    drivers = forecast.get("drivers") or {}
    summary = {
        "schema_version": "1.0",
        "ticker": ticker,
        "snapshot_id": snapshot_id,
        "producer": "deterministic_forecast_engine",
        "forecast_horizon": {
            "start_year": int(periods[0][:4]) if periods else None,
            "end_year": int(periods[-1][:4]) if periods else None,
            "explicit_years": [int(period[:4]) for period in periods],
        },
        "forecast_years": list(rows.values()),
        "revenue_forecast": {
            "by_channel": {
                "all_channels": {
                    "forecast": {period: row.get("revenue") for period, row in rows.items()},
                    "drivers": [drivers.get("revenue_growth") or "historical_revenue_growth"],
                    "status": "aggregate_only",
                },
            },
            "by_product_group": {
                "all_products": {
                    "forecast": {period: row.get("revenue") for period, row in rows.items()},
                    "drivers": [drivers.get("revenue_growth") or "historical_revenue_growth"],
                    "status": "aggregate_only",
                },
            },
        },
        "gross_margin_forecast": {
            "forecast": {period: row.get("gross_margin") for period, row in rows.items()},
            "assumptions": drivers,
        },
        "opex_forecast": {
            "selling_expense": {"status": "combined_sga_only"},
            "admin_expense": {"status": "combined_sga_only"},
            "combined_sga": {period: row.get("sga") for period, row in rows.items()},
            "assumptions": drivers,
        },
        "working_capital_forecast": {
            "receivable_days": wc_schedule.get("drivers") or wc_schedule,
            "inventory_days": wc_schedule.get("drivers") or wc_schedule,
            "payable_days": wc_schedule.get("drivers") or wc_schedule,
            "schedule": wc_schedule,
        },
        "capex_and_depreciation": {
            "capex_projects": {"status": "aggregate_capex_only"},
            "capex": {period: row.get("capex") for period, row in rows.items()},
            "depreciation": {period: row.get("depreciation") for period, row in rows.items()},
        },
        "debt_cash_interest": {
            "cash": cash_sweep,
            "short_term_debt": debt_schedule,
            "long_term_debt": debt_schedule,
            "interest_expense": {period: row.get("interest_expense") for period, row in rows.items()},
            "net_borrowing": {period: row.get("net_borrowing") for period, row in rows.items()},
        },
        "share_count": {
            period: row.get("diluted_shares") for period, row in rows.items()
        },
        "eps_forecast": {period: row.get("eps") for period, row in rows.items()},
        "forecast_financial_summary": {
            "forecast_years": list(rows.values()),
            "working_capital_schedule": wc_schedule,
            "debt_schedule": debt_schedule,
            "cash_sweep_artifact": cash_sweep,
        },
        "forecast_quality_checks": {
            "historical_continuity_check": bool(forecast.get("historical_periods")),
            "driver_support_check": bool(drivers),
            "margin_sanity_check": margin_passed,
            "balance_sheet_balance_check": balance_passed,
            "cash_flow_consistency_check": cash_flow_passed,
        },
        "pharma_driver_model": pharma_driver_model,
        "evidence_refs": [snapshot_id],
        "limitations": list(forecast.get("warnings") or []),
        "deterministic_forecast": forecast,
    }
    if run_id:
        storage_bucket, storage_path = _persist_run_json(run_id, "forecast.json", summary)
        summary["storage_bucket"] = storage_bucket
        summary["storage_path"] = storage_path
    return _result(
        "FORECAST_MODEL",
        "completed",
        summary,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_forecast",
                artifact_type="forecast_result_json",
                section_key="forecast_model",
                storage_bucket=summary.get("storage_bucket"),
                storage_path=summary.get("storage_path"),
                producer="FORECAST_RUN",
            )
        ],
    )


def read_valuation_artifact_tool(storage_path: str | None) -> ServiceNodeResult:
    if not storage_path:
        return _result(
            "READ_VALUATION_ARTIFACT",
            "failed",
            {"storage_path": storage_path, "blocking_reason": "valuation_artifact_path_missing"},
            blocking_reason="valuation_artifact_path_missing",
        )
    from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter
    artifact = SupabaseStorageAdapter().download_json(RUNS_BUCKET, storage_path)
    traces = artifact.get("formula_traces") or []
    summary = {
        "storage_path": storage_path,
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
                storage_bucket=RUNS_BUCKET,
                storage_path=storage_path,
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
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_snapshot_artifact",
                artifact_type="snapshot_json",
                section_key="snapshot",
                producer="READ_SNAPSHOT",
            )
        ],
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
    return _result(
        "READ_RATIO_ARTIFACT",
        "completed",
        ratio_payload,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_ratio_artifact",
                artifact_type="ratio_json",
                section_key="ratios",
                producer="READ_RATIO_ARTIFACT",
            )
        ],
    )


def evaluate_quality_tool(
    ticker: str,
    report_path: str | None = None,
    valuation_path: str | None = None,
    run_id: str | None = None,
) -> ServiceNodeResult:
    from scripts.evaluate_report_quality import run_quality_gate
    from scripts.evaluate_report_quality import _load_json

    from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter
    adapter = SupabaseStorageAdapter()
    valuation_artifact = adapter.download_json(RUNS_BUCKET, valuation_path) if valuation_path else None
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
    if report_path:
        report_md = adapter.download_bytes(RUNS_BUCKET, report_path).decode("utf-8")

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
    storage_bucket = storage_path = None
    if run_id:
        storage_bucket, storage_path = _persist_run_json(run_id, "quality_gate.json", summary)
    status = "failed" if summary.get("overall_status") == "FAIL" else "completed"
    return _result(
        "QUALITY_EVALUATION",
        status,
        summary,
        blocking_reason="quality_gate_failed" if status == "failed" else None,
        artifact_refs=[
            ArtifactRef(
                artifact_id=f"{ticker}_quality_gate",
                artifact_type="eval_result_json",
                section_key="quality",
                storage_bucket=storage_bucket,
                storage_path=storage_path,
            )
        ],
    )
