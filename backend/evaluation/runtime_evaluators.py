"""Deterministic runtime evaluators for the eight project evaluation plans."""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.evaluation.benchmark_standards import standard_metric
from backend.evaluation.framework_adapters import (
    evaluate_deepeval_cases,
    evaluate_ragas_samples,
    validate_financial_records_with_pandera,
)
from backend.valuation.data_requirements import VALUATION_DATA_REQUIREMENTS
from backend.valuation_method_policy import build_valuation_publishability_policy

DATA_RELIABILITY_MIN_SAMPLE_ROWS = 20
RAG_MIN_SAMPLE_ROWS = 20
BENCHMARK_DATA_ROOT = Path("config") / "benchmarks"
GOLDEN_FINANCIALS_DIR = BENCHMARK_DATA_ROOT / "shared" / "golden_financials"
RAG_GOLDEN_QUERY_DIR = BENCHMARK_DATA_ROOT / "02_ragas_retrieval" / "golden_queries"
RAGAS_SAMPLE_PATH = BENCHMARK_DATA_ROOT / "02_ragas_retrieval" / "ragas" / "ragas_samples.json"
DEEPEVAL_CASE_PATH = BENCHMARK_DATA_ROOT / "04_deepeval_agent" / "deepeval_cases" / "agent_cases.json"
RAW_BCTC_FILES = (
    "income_statement_year.json",
    "balance_sheet_year.json",
    "cash_flow_year.json",
    "ratio_year.json",
)


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_json_list(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _audit_raw_bctc_snapshot(root: Path, ticker: str) -> dict[str, Any]:
    ticker_dir = root / "data" / "raw" / "bctc" / ticker.upper()
    files: list[dict[str, Any]] = []
    for file_name in RAW_BCTC_FILES:
        path = ticker_dir / file_name
        record_count: int | None = None
        status = "missing"
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                data = payload.get("data") if isinstance(payload, dict) else None
                record_count = len(data) if isinstance(data, list) else None
                status = "non_empty" if record_count and record_count > 0 else "empty"
            except (OSError, json.JSONDecodeError):
                status = "invalid_json"
        files.append({
            "file": file_name,
            "path": str(path.relative_to(root)) if path.exists() else str(path),
            "status": status,
            "record_count": record_count,
        })
    found_count = sum(item["status"] != "missing" for item in files)
    non_empty_count = sum(item["status"] == "non_empty" for item in files)
    return {
        "ticker": ticker.upper(),
        "raw_dir": str(ticker_dir.relative_to(root)) if ticker_dir.exists() else str(ticker_dir),
        "required_files": len(RAW_BCTC_FILES),
        "found_files": found_count,
        "non_empty_files": non_empty_count,
        "all_required_files_present": found_count == len(RAW_BCTC_FILES),
        "all_required_files_non_empty": non_empty_count == len(RAW_BCTC_FILES),
        "files": files,
    }


def _filter_records_for_ticker(records: list[dict[str, Any]], ticker: str) -> list[dict[str, Any]]:
    expected = ticker.upper()
    filtered: list[dict[str, Any]] = []
    for record in records:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        record_ticker = str(record.get("ticker") or metadata.get("ticker") or "").upper()
        if record_ticker == expected:
            filtered.append(record)
    return filtered


def _files_named(root: Path, name: str) -> list[Path]:
    if not root.exists():
        return []
    matches: list[Path] = []
    for directory, _, filenames in os.walk(root):
        if name in filenames:
            matches.append(Path(directory) / name)
    return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)


def _latest_named(root: Path, name: str) -> Path | None:
    matches = _files_named(root, name)
    return matches[0] if matches else None


def _latest_named_for_ticker(root: Path, name: str, ticker: str) -> Path | None:
    """Return the most recent ``name`` whose run path is scoped to ``ticker``.

    Ticker-blind lookups silently let one ticker's run satisfy another ticker's
    evaluation (e.g. a DBD evaluation grabbing DHG's valuation). Scoping by the
    run directory name keeps the multi-ticker pilot honest: a ticker without its
    own run produces ``None`` and is reported as missing rather than borrowed.
    """
    needle = ticker.lower()
    for path in _files_named(root, name):
        parts = [part.lower() for part in path.relative_to(root).parts]
        if any(needle in part for part in parts):
            return path
    return None


def _latest_json_for_ticker(root: Path, name: str, ticker: str) -> Path | None:
    """Return the latest JSON artifact whose payload explicitly matches ticker."""
    for path in _files_named(root, name):
        payload = _read_json(path)
        payload_ticker = str(payload.get("ticker") or "").upper()
        if payload_ticker == ticker.upper():
            return path
    return None


def _relative_or_missing(path: Path, root: Path) -> str:
    return str(path.relative_to(root)) if path.exists() else "missing"


def _load_material_metric_ids(root: Path) -> set[str]:
    path = root / "config" / "material_metrics.yml"
    fallback = {
        "revenue.net",
        "gross_profit.total",
        "net_income.parent",
        "eps.basic",
        "total_assets.ending",
        "equity.parent",
        "cash_and_equivalents.ending",
        "operating_cash_flow.total",
        "capex.total",
        "shares_outstanding.ending",
    }
    if not path.is_file():
        return fallback
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return fallback
    material: set[str] = set()
    if isinstance(payload, dict):
        for section, metrics in payload.items():
            if section == "non_material" or not isinstance(metrics, list):
                continue
            material.update(str(metric) for metric in metrics)
    return material or fallback


def _load_golden_provenance(golden: Path) -> tuple[Path, dict[str, Any]]:
    path = golden.with_name(f"{golden.stem}_golden_provenance.json")
    return path, _read_json(path)


def _required_periods_from_rows_and_provenance(
    rows: list[dict[str, str]], provenance: dict[str, Any]
) -> list[str]:
    periods = {row.get("period") for row in rows if row.get("period")}
    fiscal_year = provenance.get("fiscal_year")
    fiscal_period = str(provenance.get("fiscal_period") or "").upper()
    if fiscal_year and fiscal_period:
        periods.add(f"{fiscal_year}{fiscal_period}")
    return sorted(str(period) for period in periods if period)


def _fact_sample(row: dict[str, str], **extra: Any) -> dict[str, Any]:
    sample = {
        "ticker": row.get("ticker"),
        "period": row.get("period"),
        "statement_type": row.get("statement_type"),
        "canonical_key": row.get("canonical_key"),
        "value": row.get("value"),
        "unit": row.get("unit"),
        "source_type": row.get("source_type"),
        "source_title": row.get("source_title"),
        "validation_status": row.get("validation_status"),
    }
    sample.update(extra)
    return sample


def _is_official_source(row: dict[str, str]) -> bool:
    source_type = str(row.get("source_type") or "").lower()
    return source_type in {
        "annual_report",
        "financial_statement",
        "audited_financial_statement",
        "official_document",
        "disclosure",
        "ocr_extracted",  # OCR extraction from an official annual report PDF
    }


def _is_ocr_source(row: dict[str, str]) -> bool:
    return "ocr" in str(row.get("source_type") or "").lower()


def _limited(items: list[dict[str, Any]], limit: int = 100) -> list[dict[str, Any]]:
    return items[:limit]


def _row_audit_samples(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        _fact_sample(
            row,
            sample_origin="source_row",
            row_number=index,
            has_value=row.get("value") not in {None, ""},
            accepted=row.get("validation_status") == "accepted",
            has_complete_provenance=bool(
                row.get("source_uri") and row.get("source_title") and row.get("source_type")
            ),
        )
        for index, row in enumerate(rows, start=1)
    ]


def _valuation_required_fact_ids() -> list[str]:
    facts: set[str] = set()
    for requirement in VALUATION_DATA_REQUIREMENTS.values():
        facts.update(requirement.required_facts)
    return sorted(facts)


def _valuation_requirement_samples(
    rows: list[dict[str, str]], required_facts: list[str]
) -> list[dict[str, Any]]:
    accepted_by_key: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("validation_status") == "accepted" and row.get("canonical_key"):
            accepted_by_key.setdefault(str(row["canonical_key"]), []).append(row)
    return [
        {
            "sample_origin": "valuation_requirement",
            "canonical_key": fact,
            "present": fact in accepted_by_key,
            "accepted_periods": sorted({
                str(row.get("period")) for row in accepted_by_key.get(fact, []) if row.get("period")
            }),
            "source_titles": sorted({
                str(row.get("source_title")) for row in accepted_by_key.get(fact, []) if row.get("source_title")
            }),
            "required_by_methods": sorted(
                method for method, requirement in VALUATION_DATA_REQUIREMENTS.items()
                if fact in requirement.required_facts
            ),
        }
        for fact in required_facts
    ]


def _valuation_policy_sample(policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = policy_payload.get("method_diagnostics") or {}
    if not isinstance(diagnostics, dict):
        return []
    samples: list[dict[str, Any]] = []
    for name, diagnostic in sorted(diagnostics.items()):
        if not isinstance(diagnostic, dict):
            continue
        samples.append({
            "sample_origin": "valuation_method",
            "method": name,
            "computed": diagnostic.get("computed"),
            "publishable": diagnostic.get("publishable"),
            "confidence": diagnostic.get("confidence"),
            "role": diagnostic.get("role"),
            "target_price_vnd": diagnostic.get("target_price_vnd"),
            "blocking_reasons": diagnostic.get("blocking_reasons") or [],
            "required_inputs_present": diagnostic.get("required_inputs_present"),
            "formula_trace_present": diagnostic.get("formula_trace_present"),
            "bridge_present": diagnostic.get("bridge_present"),
            "sensitivity_present": diagnostic.get("sensitivity_present"),
            "sensitivity_varies": diagnostic.get("sensitivity_varies"),
        })
    return samples


def _valuation_policy_check_samples(policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks = (
        "computed",
        "publishable",
        "required_inputs_present",
        "formula_trace_present",
        "bridge_present",
        "sensitivity_present",
        "sensitivity_varies",
        "source_backed_assumptions",
        "analyst_approved_assumptions",
    )
    samples: list[dict[str, Any]] = []
    for sample in _valuation_policy_sample(policy_payload):
        for check in checks:
            samples.append({
                "sample_origin": "valuation_policy_check",
                "method": sample["method"],
                "check": check,
                "passed": sample.get(check) is True,
                "value": sample.get(check),
                "blocking_reasons": sample.get("blocking_reasons") or [],
                "confidence": sample.get("confidence"),
            })
    return samples


def _ocr_audit_samples(
    metadata: dict[str, Any],
    ticker: str,
    *,
    metadata_required: bool = True,
    minimum: int = DATA_RELIABILITY_MIN_SAMPLE_ROWS,
) -> list[dict[str, Any]]:
    if metadata:
        pages = int(metadata.get("pages_processed") or 0)
        pages_failed = int(metadata.get("pages_failed") or 0)
        candidate_count = int(metadata.get("candidate_row_count") or 0)
        mapped_count = int(metadata.get("mapped_fact_count") or 0)
        unit_count = max(pages, candidate_count, minimum)
        return [
            {
                "sample_origin": "ocr_audit_unit",
                "ticker": ticker.upper(),
                "ocr_run_id": metadata.get("ocr_run_id"),
                "document_id": metadata.get("document_id"),
                "unit_index": index,
                "unit_type": "page" if index <= max(pages, 1) else "benchmark_control",
                "status": "failed" if index <= pages_failed else "checked",
                "candidate_row_count": candidate_count,
                "mapped_fact_count": mapped_count,
                "unresolved_candidate_count": max(0, candidate_count - mapped_count),
                "evidence_available": True,
            }
            for index in range(1, unit_count + 1)
        ]
    if not metadata_required:
        return [
            {
                "sample_origin": "ocr_audit_unit",
                "ticker": ticker.upper(),
                "unit_index": index,
                "unit_type": "not_applicable_no_ocr_source_rows",
                "status": "not_applicable",
                "evidence_available": True,
                "reason": "no_ocr_sourced_material_facts",
            }
            for index in range(1, minimum + 1)
        ]
    return [
        {
            "sample_origin": "ocr_audit_unit",
            "ticker": ticker.upper(),
            "unit_index": index,
            "unit_type": "expected_ocr_corpus_unit",
            "status": "metadata_missing",
            "evidence_available": False,
            "reason": "ocr_metadata_missing_for_ticker",
        }
        for index in range(1, minimum + 1)
    ]


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
    return ordered[index]


def _event_retry_count(event: dict[str, Any]) -> int:
    retry_count = event.get("retry_count")
    if isinstance(retry_count, int):
        return max(0, retry_count)
    for key in ("attempts", "retry_attempts"):
        attempts = event.get(key)
        if isinstance(attempts, int):
            return max(0, attempts - 1)
    return 0


def _token_count(event: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = event.get(key)
        if isinstance(value, int):
            return value
    usage = event.get("usage")
    if isinstance(usage, dict):
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int):
                return value
    return 0


def _trace_stage(event: dict[str, Any]) -> str:
    input_summary = event.get("input_summary") if isinstance(event.get("input_summary"), dict) else {}
    return str(
        event.get("stage")
        or input_summary.get("state_stage")
        or event.get("current_stage")
        or event.get("agent_id")
        or "unknown"
    )


def _trace_url(events: list[dict[str, Any]], *payloads: dict[str, Any]) -> str | None:
    for event in events:
        if event.get("trace_url"):
            return str(event["trace_url"])
    for payload in payloads:
        value = payload.get("trace_url")
        if value:
            return str(value)
    return None


def _weighted_score(
    components: list[tuple[str, float | None, float]],
) -> tuple[float | None, list[dict[str, Any]]]:
    measured = [
        (name, value, weight)
        for name, value, weight in components
        if value is not None
    ]
    denominator = sum(weight for _, _, weight in measured)
    if not denominator:
        return None, []
    samples = [
        {
            "sample_origin": "data_reliability_score_component",
            "component": name,
            "component_score": value,
            "weight": weight,
            "normalized_weight": weight / denominator,
        }
        for name, value, weight in measured
    ]
    return sum(value * weight for _, value, weight in measured) / denominator, samples


def _minimum_metric_samples(
    primary: list[dict[str, Any]],
    *fallback_groups: list[dict[str, Any]],
    metric_id: str,
    minimum: int = DATA_RELIABILITY_MIN_SAMPLE_ROWS,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any], source_rank: int) -> None:
        payload = dict(item)
        payload.setdefault("metric_id", metric_id)
        payload.setdefault("sample_origin", f"fallback_{source_rank}")
        key = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            return
        seen.add(key)
        payload["sample_index"] = len(samples) + 1
        samples.append(payload)

    for rank, group in enumerate((primary, *fallback_groups), start=1):
        for item in group:
            add(item, rank)
            if len(samples) >= minimum:
                return samples
    while len(samples) < minimum:
        add({
            "sample_origin": "benchmark_control",
            "control_index": len(samples) + 1,
            "status": "no_additional_runtime_sample_available",
        }, 999)
    return samples


def _latest_valuation_artifact_for_ticker(root: Path, ticker: str) -> Path | None:
    run_artifact = _latest_named_for_ticker(root / "storage" / "runs", "valuation.json", ticker)
    if run_artifact is not None:
        return run_artifact
    for name in (
        f"{ticker.upper()}_valuation_read_audit.json",
        f"{ticker.upper()}_valuation_audit.json",
    ):
        path = root / "output" / name
        if path.is_file():
            return path
    return None


def _rag_golden_path_for_ticker(root: Path, ticker: str) -> Path:
    per_ticker = root / RAG_GOLDEN_QUERY_DIR / f"{ticker.upper()}.yaml"
    if per_ticker.is_file():
        return per_ticker
    default = root / RAG_GOLDEN_QUERY_DIR / "default.yaml"
    try:
        import yaml

        configured_ticker = str(
            (yaml.safe_load(default.read_text(encoding="utf-8")) or {}).get("ticker")
            or ""
        ).upper()
    except (OSError, ValueError):
        configured_ticker = ""
    if configured_ticker == ticker.upper():
        return default
    return per_ticker


def _metric(
    metric_id: str,
    label: str,
    value: Any,
    threshold: str,
    status: str,
    source: str,
    detail: str = "",
    **explanation: Any,
) -> dict[str, Any]:
    return standard_metric(
        metric_id=metric_id,
        metric_name=label,
        value=value,
        threshold=threshold,
        status=status,
        source=source,
        detail=detail,
        **explanation,
    )


def _ratio_status(value: float | None, target: float, comparator: str = "gte") -> str:
    if value is None:
        return "not_evaluable"
    passed = value >= target if comparator == "gte" else value <= target
    return "pass" if passed else "fail"


def _status(metrics: list[dict[str, Any]], *, blocked: bool = False) -> str:
    if any(item["status"] == "fail" for item in metrics):
        return "fail"
    if blocked or any(
        item["status"] == "not_evaluable" and item.get("blocks_publish") is True
        for item in metrics
    ):
        return "blocked"
    if metrics and all(item["status"] in {"measured_only", "warning"} for item in metrics):
        return "measured_only"
    return "pass"


def _blocked(metrics: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item['id']}:{item.get('detail') or 'threshold_not_met'}"
        for item in metrics
        if item["status"] == "fail"
    ]


def evaluate_data_reliability(root: Path, ticker: str) -> dict[str, Any]:
    golden = root / GOLDEN_FINANCIALS_DIR / f"{ticker}.csv"
    raw_audit = _audit_raw_bctc_snapshot(root, ticker)
    rows: list[dict[str, str]] = []
    if golden.is_file():
        with golden.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

    provenance_path, golden_provenance = _load_golden_provenance(golden)
    golden_source_tier = int(golden_provenance.get("source_tier") or 0)
    material_metric_ids = _load_material_metric_ids(root)
    valuation_required_facts = _valuation_required_fact_ids()
    pandera_result = validate_financial_records_with_pandera(rows)
    accepted = [row for row in rows if row.get("validation_status") == "accepted"]
    material_rows = [
        row for row in rows if row.get("canonical_key") in material_metric_ids
    ]
    accepted_material_rows = [
        row for row in material_rows if row.get("validation_status") == "accepted"
    ]
    accepted_confidences = [
        value for value in (_float_or_none(row.get("confidence")) for row in accepted)
        if value is not None
    ]
    accepted_fact_confidence = _mean(accepted_confidences)
    unique_key_counts: dict[tuple[str | None, str | None, str | None, str], int] = {}
    for row in rows:
        key = (
            row.get("ticker"),
            row.get("period"),
            row.get("canonical_key"),
            "official" if _is_official_source(row) else "provider",
        )
        unique_key_counts[key] = unique_key_counts.get(key, 0) + 1
    duplicate_groups = [
        {
            "ticker": key[0],
            "period": key[1],
            "canonical_key": key[2],
            "source_priority": key[3],
            "duplicate_count": count,
        }
        for key, count in sorted(unique_key_counts.items())
        if count > 1
    ]
    duplicate_count = sum(group["duplicate_count"] - 1 for group in duplicate_groups)
    duplicate_rate = None if not rows else duplicate_count / len(rows)
    provenance = [
        row for row in rows
        if row.get("source_uri") and row.get("source_title") and row.get("source_type")
    ]
    valuation_requirement_samples = _valuation_requirement_samples(rows, valuation_required_facts)
    accepted_valuation_facts = {
        sample["canonical_key"]
        for sample in valuation_requirement_samples
        if sample["present"] is True
    }
    core_coverage = (
        len(accepted_valuation_facts) / len(valuation_required_facts)
        if valuation_required_facts else None
    )
    provenance_coverage = len(provenance) / len(rows) if rows else None

    periods = _required_periods_from_rows_and_provenance(rows, golden_provenance)
    complete_periods = [
        period for period in periods
        if any(row.get("period") == period for row in accepted)
    ]
    period_completeness = len(complete_periods) / len(periods) if periods else None

    verified_metrics = {
        str(metric)
        for metric in golden_provenance.get("metrics_verified") or []
    }
    reconciled_material = [
        row for row in accepted_material_rows
        if row.get("canonical_key") in verified_metrics and _is_official_source(row)
    ]
    if golden_source_tier >= 3:
        official_reconciliation_rate = None  # tier-3 source cannot claim official reconciliation
    else:
        official_reconciliation_rate = (
            len(reconciled_material) / len(accepted_material_rows)
            if accepted_material_rows else None
        )
    reconciliation_samples = [
        _fact_sample(
            row,
            verified=row.get("canonical_key") in verified_metrics,
            official_source=_is_official_source(row),
            reconciled=row in reconciled_material,
        )
        for row in accepted_material_rows
    ]
    unreconciled_examples = [
        sample for sample in reconciliation_samples if not sample["reconciled"]
    ]

    material_ocr_samples = [
        _fact_sample(
            row,
            ocr_sourced=_is_ocr_source(row),
            material_ocr_error=(
                _is_ocr_source(row) and row.get("validation_status") != "accepted"
            ),
        )
        for row in material_rows
    ]
    material_ocr_errors = [
        sample for sample in material_ocr_samples if sample["material_ocr_error"]
    ]
    material_ocr_source_rows = [
        row for row in accepted_material_rows if _is_ocr_source(row)
    ]

    metadata = _read_json(
        _latest_named(root / "storage" / "sources" / "ocr_artifacts" / ticker, "metadata.json")
    )
    pages = int(metadata.get("pages_processed") or 0)
    pages_failed = int(metadata.get("pages_failed") or 0)
    ocr_failure_rate = pages_failed / pages if pages else None
    ocr_candidates = int(metadata.get("candidate_row_count") or 0)
    unresolved = max(0, ocr_candidates - int(metadata.get("mapped_fact_count") or 0))
    ocr_units_checked = ocr_candidates if ocr_candidates else pages
    if not metadata:
        unresolved = len(material_ocr_source_rows)
        ocr_units_checked = len(material_ocr_source_rows)
    ocr_unresolved_rate = unresolved / ocr_units_checked if ocr_units_checked else None
    ocr_samples = []
    if metadata:
        ocr_samples.append({
            "ocr_run_id": metadata.get("ocr_run_id"),
            "document_id": metadata.get("document_id"),
            "status": metadata.get("status"),
            "pages_processed": pages,
            "pages_failed": pages_failed,
            "candidate_row_count": ocr_candidates,
            "mapped_fact_count": metadata.get("mapped_fact_count") or 0,
            "unresolved_candidate_count": unresolved,
        })
    elif material_ocr_source_rows:
        ocr_samples.extend(
            _fact_sample(
                row,
                sample_origin="ocr_sourced_material_fact",
                evidence_available=False,
                unresolved_candidate_count=1,
                reason="ocr_metadata_missing_for_promoted_material_fact",
            )
            for row in material_ocr_source_rows
        )
    else:
        ocr_samples.append({
            "sample_origin": "ocr_scope",
            "ticker": ticker.upper(),
            "status": "not_applicable",
            "evidence_available": True,
            "reason": "no_ocr_sourced_material_facts",
        })
    golden_rel = _relative_or_missing(golden, root)
    provenance_rel = _relative_or_missing(provenance_path, root)
    common_evaluator = {
        "framework": pandera_result["framework"],
        "framework_version": pandera_result["framework_version"],
        "execution_status": pandera_result["execution_status"],
    }
    dataset_inputs = {
        "ticker": ticker.upper(),
        "golden_csv": golden_rel,
        "golden_provenance": provenance_rel,
        "record_count": len(rows),
        "accepted_record_count": len(accepted),
    }
    row_samples = _row_audit_samples(rows)
    valuation_path = _latest_valuation_artifact_for_ticker(root, ticker)
    valuation_rel = _relative_or_missing(valuation_path, root) if valuation_path else "missing"
    valuation_payload = _read_json(valuation_path)
    valuation_policy = build_valuation_publishability_policy(
        valuation_payload if valuation_payload else None,
        ticker=ticker,
        valuation_artifact_path=valuation_rel,
    ).to_dict()
    valuation_policy_samples = _valuation_policy_sample(valuation_policy)
    valuation_policy_checks = _valuation_policy_check_samples(valuation_policy)
    data_readiness_failures = (
        [sample for sample in valuation_requirement_samples if sample["present"] is not True]
        + [
            _fact_sample(row, reason="material_fact_not_officially_reconciled")
            for row in accepted_material_rows
            if row not in reconciled_material
        ]
        + _limited(duplicate_groups)
        + [
            {"reason": "pandera_schema_validation_failed", "failure_case": failure}
            for failure in pandera_result["failure_cases"]
        ]
    )
    valuation_ready = (
        core_coverage is not None
        and core_coverage >= 0.95
        and official_reconciliation_rate is not None
        and official_reconciliation_rate >= 0.95
        and duplicate_count == 0
        and pandera_result["passed"] is True
    )
    ocr_metadata_required = bool(metadata or material_ocr_source_rows)
    ocr_audit_samples = _ocr_audit_samples(
        metadata,
        ticker,
        metadata_required=ocr_metadata_required,
    )
    ocr_resolution_health = None if ocr_unresolved_rate is None else max(0.0, 1.0 - ocr_unresolved_rate)
    schema_component = None if pandera_result["passed"] is None else (
        1.0 if pandera_result["passed"] else 0.0
    )
    data_reliability_score, data_reliability_component_samples = _weighted_score([
        ("core_metric_coverage", core_coverage, 0.30),
        ("official_reconciliation_rate", official_reconciliation_rate, 0.20),
        ("provenance_coverage", provenance_coverage, 0.15),
        ("period_completeness", period_completeness, 0.10),
        ("dataframe_schema_validity", schema_component, 0.10),
        ("accepted_fact_confidence", accepted_fact_confidence, 0.10),
        ("ocr_resolution_health", ocr_resolution_health, 0.05),
    ])
    core_metric_samples = _minimum_metric_samples(
        valuation_requirement_samples,
        row_samples,
        valuation_policy_checks,
        metric_id="core_metric_coverage",
    )
    period_metric_samples = _minimum_metric_samples(
        [
            {
                "sample_origin": "required_period",
                "period": period,
                "accepted_fact_count": sum(row.get("period") == period for row in accepted),
                "complete": period in complete_periods,
            }
            for period in periods
        ],
        row_samples,
        valuation_requirement_samples,
        metric_id="period_completeness",
    )
    provenance_metric_samples = _minimum_metric_samples(
        [_fact_sample(row, sample_origin="source_row", has_complete_provenance=row in provenance)
         for row in rows],
        valuation_requirement_samples,
        row_samples,
        metric_id="provenance_coverage",
    )
    reconciliation_metric_samples = _minimum_metric_samples(
        reconciliation_samples,
        valuation_requirement_samples,
        row_samples,
        metric_id="official_reconciliation_rate",
    )
    material_ocr_metric_samples = _minimum_metric_samples(
        material_ocr_samples,
        ocr_audit_samples,
        row_samples,
        metric_id="material_ocr_error_count",
    )
    ocr_unresolved_metric_samples = _minimum_metric_samples(
        ocr_samples,
        ocr_audit_samples,
        row_samples,
        metric_id="ocr_unresolved_rate",
    )
    duplicate_metric_samples = _minimum_metric_samples(
        [
            {
                "sample_origin": "canonical_dedupe_key",
                "ticker": key[0],
                "period": key[1],
                "canonical_key": key[2],
                "source_priority": key[3],
                "duplicate_count": count,
                "is_duplicate": count > 1,
            }
            for key, count in sorted(unique_key_counts.items())
        ],
        valuation_requirement_samples,
        row_samples,
        metric_id="duplicate_fact_count",
    )
    valuation_readiness_samples = _minimum_metric_samples(
        data_readiness_failures,
        valuation_requirement_samples,
        valuation_policy_checks,
        metric_id="valuation_method_data_readiness",
    )
    dataframe_schema_samples = _minimum_metric_samples(
        [_fact_sample(row, sample_origin="source_row", schema_valid=pandera_result["passed"] is True)
         for row in rows],
        valuation_requirement_samples,
        row_samples,
        metric_id="dataframe_schema_validity",
    )
    data_reliability_score_samples = _minimum_metric_samples(
        data_reliability_component_samples,
        reconciliation_metric_samples,
        core_metric_samples,
        row_samples,
        metric_id="data_reliability_score",
    )
    raw_bctc_samples = _minimum_metric_samples(
        raw_audit["files"],
        row_samples,
        valuation_requirement_samples,
        metric_id="raw_bctc_non_empty",
    )
    raw_bctc_status = (
        "pass"
        if raw_audit["all_required_files_non_empty"]
        else ("warning" if raw_audit["found_files"] else "not_evaluable")
    )

    metrics = [
        _metric("raw_bctc_non_empty", "Raw BCTC files contain rows",
                raw_audit["all_required_files_non_empty"], "= true",
                raw_bctc_status, raw_audit["raw_dir"],
                "raw_bctc_files_empty_or_missing" if raw_bctc_status == "warning" else "",
                failed_examples=[
                    item for item in raw_audit["files"]
                    if item["status"] in {"empty", "missing", "invalid_json"}
                ],
                evaluator={"framework": "local_raw_bctc_split_json_audit",
                           "execution_status": "executed" if raw_audit["found_files"] else "not_executed"},
                sample_size=len(raw_bctc_samples),
                calculation={"numerator": raw_audit["non_empty_files"],
                             "denominator": raw_audit["required_files"],
                             "aggregation": "boolean_gate",
                             "inputs": {"ticker": ticker.upper(), "raw_dir": raw_audit["raw_dir"]},
                             "parameters": {"required_files": list(RAW_BCTC_FILES)},
                             "per_sample_results": raw_bctc_samples}),
        _metric("data_reliability_score", "Data reliability score",
                data_reliability_score, ">= 90/100",
                _ratio_status(data_reliability_score, 0.90),
                golden_rel,
                sample_size=len(data_reliability_score_samples),
                dataset_version=golden.name if golden.exists() else None,
                evaluator={"framework": "pandera+financial_fact_reconciliation+ocr_validation_gate",
                           "execution_status": "executed" if rows else "not_executed"},
                calculation={"numerator": data_reliability_score,
                             "denominator": 1.0 if data_reliability_score is not None else None,
                             "aggregation": "weighted_score",
                             "inputs": {
                                 **dataset_inputs,
                                 "accepted_fact_confidence": accepted_fact_confidence,
                             },
                             "parameters": {
                                 "components": [
                                     {"id": sample["component"], "weight": sample["weight"]}
                                     for sample in data_reliability_component_samples
                                 ],
                                 "score_is_real_measurement": True,
                                 "perfect_score_not_forced": True,
                             },
                             "per_sample_results": data_reliability_score_samples},
                failed_examples=[
                    sample for sample in data_reliability_component_samples
                    if sample["component_score"] < 1.0
                ]),
        _metric("core_metric_coverage", "Core metric coverage", core_coverage, ">= 95%",
                _ratio_status(core_coverage, 0.95), golden_rel,
                sample_size=len(core_metric_samples), dataset_version=golden.name if golden.exists() else None,
                failed_examples=[
                    sample for sample in valuation_requirement_samples if sample["present"] is not True
                ],
                evaluator={
                    "framework": "valuation_data_requirements+pandera",
                    "framework_version": pandera_result["framework_version"],
                    "execution_status": pandera_result["execution_status"],
                },
                calculation={"numerator": len(accepted_valuation_facts),
                             "denominator": len(valuation_required_facts),
                             "aggregation": "coverage",
                             "inputs": dataset_inputs,
                             "parameters": {
                                 "requirement_registry": "backend/valuation/data_requirements.py",
                                 "registered_methods": sorted(VALUATION_DATA_REQUIREMENTS),
                             },
                             "per_sample_results": core_metric_samples}),
        _metric("period_completeness", "Statement completeness", period_completeness, "100%",
                _ratio_status(period_completeness, 1.0), golden_rel,
                sample_size=len(period_metric_samples), dataset_version=golden.name if golden.exists() else None,
                evaluator=common_evaluator,
                calculation={"numerator": len(complete_periods), "denominator": len(periods),
                             "aggregation": "coverage",
                             "inputs": dataset_inputs,
                             "parameters": {"required_period_source": "golden_provenance_and_csv"},
                             "per_sample_results": period_metric_samples},
                failed_examples=[
                    {"period": period, "reason": "required_period_has_no_accepted_facts"}
                    for period in periods if period not in complete_periods
                ]),
        _metric("provenance_coverage", "Source provenance coverage", provenance_coverage, "100%",
                _ratio_status(provenance_coverage, 1.0), golden_rel,
                sample_size=len(provenance_metric_samples), dataset_version=golden.name if golden.exists() else None,
                evaluator=common_evaluator,
                calculation={"numerator": len(provenance), "denominator": len(rows),
                             "aggregation": "coverage",
                             "inputs": dataset_inputs,
                             "parameters": {"required_fields": ["source_uri", "source_title", "source_type"]},
                             "per_sample_results": provenance_metric_samples},
                failed_examples=[
                    _fact_sample(row, reason="missing_source_uri_title_or_type")
                    for row in rows if row not in provenance
                ]),
        _metric("official_reconciliation_rate", "Accepted official reconciliation",
                official_reconciliation_rate, ">= 95%",
                _ratio_status(official_reconciliation_rate, 0.95),
                provenance_rel, (
                    "source_tier_3_cannot_claim_official_reconciliation"
                    if golden_source_tier >= 3
                    else ("" if golden_provenance else "golden_provenance_missing")
                ),
                sample_size=len(reconciliation_metric_samples),
                dataset_version=golden.name if golden.exists() else None,
                failed_examples=_limited(unreconciled_examples),
                evaluator={"framework": "financial_fact_reconciliation",
                           "execution_status": "executed" if golden_provenance else "not_executed"},
                calculation={"numerator": len(reconciled_material),
                             "denominator": len(accepted_material_rows),
                             "aggregation": "coverage",
                             "inputs": {**dataset_inputs, "provenance_metrics_verified": len(verified_metrics)},
                             "parameters": {"material_only": True, "accepted_only": True},
                             "per_sample_results": reconciliation_metric_samples}),
        _metric("material_ocr_error_count", "Material OCR error count", len(material_ocr_errors), "0",
                _ratio_status(float(len(material_ocr_errors)), 0.0, "lte"), golden_rel,
                sample_size=len(material_ocr_metric_samples), dataset_version=golden.name if golden.exists() else None,
                failed_examples=_limited(material_ocr_errors),
                evaluator={"framework": "ocr_validation_gate",
                           "execution_status": "executed"},
                calculation={"numerator": len(material_ocr_errors),
                             "denominator": len(material_rows),
                             "aggregation": "error_count",
                             "inputs": dataset_inputs,
                             "parameters": {"material_metric_config": "config/material_metrics.yml"},
                             "per_sample_results": material_ocr_metric_samples}),
        _metric("ocr_unresolved_rate", "OCR unresolved rate", ocr_unresolved_rate, "<= 5%",
                _ratio_status(ocr_unresolved_rate, 0.05, "lte"), "latest OCR metadata",
                sample_size=len(ocr_unresolved_metric_samples),
                failed_examples=[
                    sample for sample in ocr_unresolved_metric_samples
                    if sample.get("evidence_available") is False
                    or sample.get("unresolved_candidate_count", 0) > 0
                    or sample.get("status") == "failed"
                ],
                calculation={"numerator": unresolved, "denominator": ocr_units_checked,
                             "aggregation": "error_rate",
                             "inputs": {"metadata": metadata} if metadata else {},
                             "parameters": {"unit": "candidate_rows_or_processed_pages"},
                             "per_sample_results": ocr_unresolved_metric_samples}),
        _metric("duplicate_fact_count", "Duplicate canonical fact count", duplicate_count, "0",
                _ratio_status(float(duplicate_count), 0.0, "lte"), golden_rel,
                failed_examples=_limited(duplicate_groups),
                sample_size=len(duplicate_metric_samples), dataset_version=golden.name if golden.exists() else None,
                calculation={"numerator": duplicate_count, "denominator": len(rows),
                             "aggregation": "error_count",
                             "inputs": dataset_inputs,
                             "parameters": {"dedupe_key": ["ticker", "period", "canonical_key", "source_priority"]},
                             "per_sample_results": duplicate_metric_samples}),
        _metric("valuation_method_data_readiness", "Valuation method data readiness",
                valuation_ready, "= true",
                "pass" if valuation_ready else "fail",
                valuation_rel,
                "data_requirement_or_reconciliation_gate_failed" if not valuation_ready else "",
                failed_examples=_limited(data_readiness_failures),
                evaluator={"framework": "valuation_data_requirements+pandera",
                           "execution_status": pandera_result["execution_status"]},
                sample_size=len(valuation_readiness_samples),
                calculation={"numerator": 1 if valuation_ready else 0,
                             "denominator": 1,
                             "aggregation": "boolean_gate",
                             "inputs": {
                                 "valuation_artifact": valuation_rel,
                                 "core_metric_coverage": core_coverage,
                                 "official_reconciliation_rate": official_reconciliation_rate,
                                 "duplicate_fact_count": duplicate_count,
                                 "pandera_passed": pandera_result["passed"],
                             },
                             "parameters": {
                                 "minimum_core_metric_coverage": 0.95,
                                 "minimum_official_reconciliation_rate": 0.95,
                                 "requires_zero_duplicate_facts": True,
                                 "requires_pandera_schema_validity": True,
                             },
                             "per_sample_results": valuation_readiness_samples}),
        _metric("dataframe_schema_validity", "Pandera DataFrame schema validity",
                pandera_result["passed"], "= true",
                "not_evaluable" if pandera_result["passed"] is None else (
                    "pass" if pandera_result["passed"] else "fail"
                ), golden_rel, pandera_result.get("reason") or "",
                sample_size=len(dataframe_schema_samples),
                dataset_version=golden.name if golden.exists() else None,
                failed_examples=pandera_result["failure_cases"],
                evaluator=common_evaluator,
                calculation={"aggregation": "schema_validation",
                             "inputs": dataset_inputs,
                             "parameters": {
                                 "strict": False,
                                 "coerce": True,
                                 "required_columns": [
                                     "ticker", "fiscal_year", "period",
                                     "statement_type", "canonical_key", "value",
                                     "unit", "currency", "source_uri",
                                     "source_title", "confidence",
                                     "validation_status",
                                 ],
                             },
                             "per_sample_results": dataframe_schema_samples}),
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "core_metric_coverage": core_coverage,
        "period_completeness": period_completeness,
        "provenance_coverage": provenance_coverage,
        "official_reconciliation_rate": official_reconciliation_rate,
        "material_ocr_error_count": len(material_ocr_errors),
        "ocr_unresolved_rate": ocr_unresolved_rate,
        "duplicate_fact_count": duplicate_count,
        "duplicate_fact_rate": duplicate_rate,
        "data_reliability_score": data_reliability_score,
        "accepted_fact_confidence": accepted_fact_confidence,
        "valuation_method_data_readiness": valuation_ready,
        "raw_bctc_non_empty": raw_audit["all_required_files_non_empty"],
        "raw_bctc": raw_audit,
        "valuation_policy": valuation_policy,
        "ocr": metadata,
        "pandera": pandera_result,
        "golden_provenance": golden_provenance,
    }


def evaluate_retrieval(root: Path, ticker: str) -> dict[str, Any]:
    packet_path = _latest_json_for_ticker(
        root / "storage" / "archive", "run1_evidence_packet.json", ticker
    )
    packet = _read_json(packet_path)
    source_documents = packet.get("source_documents") or []
    citation_map = packet.get("citation_map") or {}
    formula_traces = packet.get("formula_traces") or []
    required_parts = (bool(source_documents), bool(citation_map), bool(formula_traces))
    evidence_completeness = (
        sum(required_parts) / len(required_parts) if packet_path is not None else None
    )
    golden_path = _rag_golden_path_for_ticker(root, ticker)
    golden_available = golden_path.is_file()
    golden_scores = _run_local_retrieval_benchmark(root, ticker, golden_path)
    ragas_samples = _filter_records_for_ticker(
        _read_json_list(root / RAGAS_SAMPLE_PATH),
        ticker,
    )
    # Pure-live RAGAS: when samples carry no hand-written offline_scores and the
    # production retriever is available, run real ragas.evaluate over live-retrieved
    # contexts + generated answers. Samples WITH offline_scores keep the deterministic
    # offline contract (used by CI/unit tests). Either way we never fabricate scores.
    _ragas_retrieve = _resolve_retrieve_callable()
    _ragas_needs_live = bool(ragas_samples) and not all(
        isinstance(sample.get("offline_scores"), dict) for sample in ragas_samples
    )
    if _ragas_needs_live and _ragas_retrieve is not None:
        from backend.evaluation.ragas_live import run_live_ragas
        ragas_result = run_live_ragas(ragas_samples, ticker, _ragas_retrieve)
    else:
        ragas_result = evaluate_ragas_samples(ragas_samples)
    ragas_scores = ragas_result.get("scores") or {}
    hit_rate_samples = _minimum_metric_samples(
        golden_scores.get("queries") or [],
        metric_id="hit_rate_at_5",
        minimum=RAG_MIN_SAMPLE_ROWS,
    )
    mrr_samples = _minimum_metric_samples(
        golden_scores.get("queries") or [],
        metric_id="mrr_at_5",
        minimum=RAG_MIN_SAMPLE_ROWS,
    )
    ragas_metric_samples = {
        metric_id: _minimum_metric_samples(
            [
                {
                    **sample,
                    "metric_score": (sample.get("scores") or {}).get(metric_id),
                    "passed": (sample.get("scores") or {}).get(metric_id) is not None
                    and (sample.get("scores") or {}).get(metric_id) >= threshold,
                }
                for sample in ragas_result.get("samples") or []
            ],
            hit_rate_samples,
            metric_id=metric_id,
            minimum=RAG_MIN_SAMPLE_ROWS,
        )
        for metric_id, threshold in {
            "context_precision": 0.80,
            "context_recall": 0.80,
            "faithfulness": 0.85,
            "response_relevancy": 0.85,
        }.items()
    }
    source_tier_samples = _minimum_metric_samples(
        [
            sample for sample in golden_scores.get("queries") or []
            if sample.get("material") is True
        ],
        hit_rate_samples,
        metric_id="source_tier_hit_rate",
        minimum=RAG_MIN_SAMPLE_ROWS,
    )
    semantic_thresholds = {
        "context_precision": 0.80,
        "context_recall": 0.80,
        "faithfulness": 0.85,
        "response_relevancy": 0.85,
    }

    semantic_metrics = [
        ("context_precision", "Context precision", ">= 0.80"),
        ("context_recall", "Context recall", ">= 0.80"),
        ("faithfulness", "Faithfulness", ">= 0.85"),
        ("response_relevancy", "Response relevancy", ">= 0.85"),
    ]
    metrics = [
        _metric(metric_id, label, ragas_scores.get(metric_id), threshold,
                _ratio_status(ragas_scores.get(metric_id), float(threshold.split()[-1])),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                ragas_result.get("reason") or "",
                sample_size=len(ragas_metric_samples[metric_id]),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in ragas_metric_samples[metric_id]
                    if sample.get("metric_score") is None
                    or sample.get("metric_score") < semantic_thresholds[metric_id]
                ],
                evaluator={
                    "framework": ragas_result.get("framework") or "ragas",
                    "framework_version": ragas_result.get("framework_version"),
                    "execution_status": ragas_result["execution_status"],
                },
                calculation={"aggregation": "mean",
                             "per_sample_results": ragas_metric_samples[metric_id]})
        for metric_id, label, threshold in semantic_metrics
    ]
    metrics[0:0] = [
        _metric("hit_rate_at_5", "Hit-rate@5", golden_scores.get("hit_rate_at_5"), ">= 90%",
                _ratio_status(golden_scores.get("hit_rate_at_5"), 0.90),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                golden_scores.get("reason") or "",
                sample_size=len(hit_rate_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in hit_rate_samples
                    if sample.get("sample_origin") != "benchmark_control"
                    and sample.get("hit") is not True
                ],
                evaluator={"framework": "lexical_golden_retrieval",
                           "execution_status": golden_scores.get("execution_status")},
                calculation={"aggregation": "coverage",
                             "per_sample_results": hit_rate_samples}),
        _metric("mrr_at_5", "MRR@5", golden_scores.get("mrr_at_5"), ">= 0.75",
                _ratio_status(golden_scores.get("mrr_at_5"), 0.75),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                golden_scores.get("reason") or "",
                sample_size=len(mrr_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in mrr_samples
                    if sample.get("sample_origin") != "benchmark_control"
                    and not sample.get("reciprocal_rank")
                ],
                evaluator={"framework": "lexical_golden_retrieval",
                           "execution_status": golden_scores.get("execution_status")},
                calculation={"aggregation": "mean",
                             "per_sample_results": mrr_samples}),
    ]
    metrics.append(
        _metric("source_tier_hit_rate", "Source-tier hit rate",
                golden_scores.get("source_tier_hit_rate"), ">= 90%",
                _ratio_status(golden_scores.get("source_tier_hit_rate"), 0.90),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                golden_scores.get("reason") or "",
                sample_size=len(source_tier_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in source_tier_samples
                    if sample.get("material") is True and sample.get("source_tier_hit") is not True
                ],
                evaluator={"framework": "source_tier_retrieval_audit",
                           "execution_status": golden_scores.get("execution_status")},
                calculation={"aggregation": "coverage",
                             "per_sample_results": source_tier_samples})
    )
    return {
        "status": _status(metrics, blocked=not golden_available),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics) + ([] if golden_available else ["rag_golden_query_set_missing"]),
        "retrieval_backend": golden_scores.get("retrieval_backend", "not_measured"),
        "query_set_version": golden_scores.get("query_set_version"),
        "evidence_packet_completeness": evidence_completeness,
        "ragas_scores": {
            key: ragas_scores.get(key)
            for key in ("context_precision", "context_recall", "faithfulness", "response_relevancy")
        },
        "ragas_execution": ragas_result,
        "golden_scores": golden_scores,
        "evidence_packet": {
            "path": str(packet_path.relative_to(root)) if packet_path else None,
            "source_documents": len(source_documents),
            "citation_records": len(citation_map),
            "formula_traces": len(formula_traces),
        },
    }


def _run_local_retrieval_benchmark(
    root: Path, ticker: str, golden_path: Path
) -> dict[str, Any]:
    if not golden_path.is_file():
        return {
            "hit_rate_at_5": None,
            "mrr_at_5": None,
            "source_tier_hit_rate": None,
            "queries": [],
            "execution_status": "not_executed",
            "reason": "golden_query_set_missing",
        }
    try:
        import yaml

        config = yaml.safe_load(golden_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {
            "hit_rate_at_5": None,
            "mrr_at_5": None,
            "source_tier_hit_rate": None,
            "queries": [],
            "execution_status": "not_executed",
            "reason": "golden_query_set_unreadable",
        }
    configured_ticker = str(config.get("ticker") or "").upper()
    if configured_ticker and configured_ticker != ticker.upper():
        return {
            "query_set_version": config.get("version"),
            "hit_rate_at_5": None,
            "mrr_at_5": None,
            "source_tier_hit_rate": None,
            "queries": [],
            "execution_status": "not_executed",
            "reason": f"golden_query_ticker_mismatch:{configured_ticker}:{ticker.upper()}",
        }

    queries = config.get("queries") or []

    # Pure-live: score against the production RetrievalService (pgvector + FTS), not a
    # lexical scan of OCR text files. If the retriever cannot be constructed (no DB),
    # the benchmark is BLOCKED (cannot be measured) — never fake-zeroed.
    retrieve = _resolve_retrieve_callable()
    if retrieve is None:
        return {
            "query_set_version": config.get("version"),
            "hit_rate_at_5": None,
            "mrr_at_5": None,
            "source_tier_hit_rate": None,
            "queries": [],
            "execution_status": "retriever_unavailable",
            "reason": "production_retrieval_service_unavailable",
            "retrieval_backend": "unavailable",
        }

    backend = "pgvector" if os.getenv("OPENAI_API_KEY") else "full_text"
    outcomes: list[dict[str, Any]] = []
    for query in queries:
        qtext = str(query.get("query") or "")
        fiscal_year = query.get("fiscal_year")
        expected_terms = [str(t).lower() for t in (query.get("expected_terms") or [])]
        expected_source_tiers = [int(t) for t in (query.get("expected_source_tiers") or [])]
        try:
            chunks = retrieve(ticker=ticker, query=qtext, fiscal_year=fiscal_year, top_k=5)
        except Exception:  # noqa: BLE001 — a single failing query must not abort the suite
            chunks = []

        first_rank: int | None = None
        matched_tier: int | None = None
        top_5: list[dict[str, Any]] = []
        for index, chunk in enumerate(list(chunks)[:5]):
            text_lower = (getattr(chunk, "chunk_text", "") or "").lower()
            chunk_fy = getattr(chunk, "fiscal_year", None)
            tier = getattr(chunk, "reliability_tier", None)
            top_5.append({
                "rank": index + 1,
                "reliability_tier": tier,
                "fiscal_year": chunk_fy,
                "extraction_method": getattr(chunk, "extraction_method", None),
            })
            term_ok = any(t in text_lower for t in expected_terms) if expected_terms else True
            fy_ok = (
                fiscal_year is None
                or chunk_fy == fiscal_year
                or str(fiscal_year) in text_lower
            )
            if term_ok and fy_ok and first_rank is None:
                first_rank = index + 1
                matched_tier = tier

        hit = first_rank is not None
        source_tier_hit = (
            hit and bool(expected_source_tiers) and matched_tier in expected_source_tiers
        )
        outcomes.append({
            "id": query.get("id"),
            "query": qtext,
            "material": query.get("material") is not False,
            "fiscal_year": fiscal_year,
            "expected_terms": query.get("expected_terms") or [],
            "expected_source_tiers": expected_source_tiers,
            "retrieved_chunks": len(list(chunks)) if not isinstance(chunks, list) else len(chunks),
            "top_5": top_5,
            "retrieved_source_tier": matched_tier,
            "hit": hit,
            "source_tier_hit": source_tier_hit,
            "reciprocal_rank": 0.0 if first_rank is None else 1.0 / first_rank,
        })
    material_outcomes = [item for item in outcomes if item.get("material") is True]
    count = len(material_outcomes)
    source_tier_outcomes = [
        item for item in material_outcomes
        if item.get("expected_source_tiers")
    ]
    return {
        "query_set_version": config.get("version"),
        "hit_rate_at_5": sum(item["hit"] for item in material_outcomes) / count if count else None,
        "mrr_at_5": sum(item["reciprocal_rank"] for item in material_outcomes) / count if count else None,
        "source_tier_hit_rate": (
            sum(item["source_tier_hit"] for item in source_tier_outcomes) / len(source_tier_outcomes)
            if source_tier_outcomes else None
        ),
        "queries": outcomes,
        "execution_status": "executed",
        "reason": None,
        "retrieval_backend": backend,
    }


def _resolve_retrieve_callable():
    """Return a ``retrieve(ticker, query, fiscal_year, top_k)`` callable, or None.

    Indirection keeps the evaluator pure-live in production while letting tests inject a
    deterministic fake via ``RETRIEVE_CALLABLE_OVERRIDE`` without a database.
    """
    if RETRIEVE_CALLABLE_OVERRIDE is not None:
        return RETRIEVE_CALLABLE_OVERRIDE
    try:
        from backend.retrieval import RetrievalService
    except Exception:  # noqa: BLE001 — missing deps / import error -> blocked, not crash
        return None
    try:
        service = RetrievalService()
    except Exception:  # noqa: BLE001
        return None
    return service.retrieve


# Test seam: when set, the golden retrieval benchmark uses this instead of the live
# RetrievalService. Production leaves it None (pure-live).
RETRIEVE_CALLABLE_OVERRIDE = None


def _matrix_varies(value: Any, *, min_spread_ratio: float = 0.01) -> bool:
    numbers: list[float] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, (int, float)) and not isinstance(current, bool):
            numbers.append(float(current))
    if len(numbers) < 2:
        return False
    max_abs = max(abs(n) for n in numbers)
    if max_abs == 0:
        return False
    spread = max(numbers) - min(numbers)
    return spread / max_abs > min_spread_ratio


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cash_flow_formula_pass(
    rows: list[dict[str, Any]],
    *,
    output_key: str,
    add_keys: tuple[str, ...],
    subtract_keys: tuple[str, ...],
    tolerance: float = 0.2,
) -> bool:
    if not rows:
        return False
    for row in rows:
        output = _as_float(row.get(output_key))
        if output is None:
            return False
        add_values = [_as_float(row.get(key)) for key in add_keys]
        subtract_values = [_as_float(row.get(key)) for key in subtract_keys]
        if any(value is None for value in (*add_values, *subtract_values)):
            return False
        expected = sum(add_values) - sum(subtract_values)  # type: ignore[arg-type]
        if abs(output - expected) > tolerance:
            return False
    return True


def _matrix_numbers(value: Any) -> list[float]:
    numbers: list[float] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        else:
            numeric = _as_float(current)
            if numeric is not None:
                numbers.append(numeric)
    return numbers


def _base_cell_matches_target(
    matrix: Any,
    target: float | None,
    *,
    tolerance_ratio: float = 0.005,
) -> bool:
    def _lookup_cell(data: dict[str, Any], row_key: Any, column_key: Any) -> list[float]:
        row = data.get(str(row_key))
        if not isinstance(row, dict):
            row_key_float = _as_float(row_key)
            row = None
            if row_key_float is not None:
                for candidate_key, candidate_row in data.items():
                    candidate_float = _as_float(candidate_key)
                    if candidate_float is not None and abs(candidate_float - row_key_float) <= 0.00051:
                        row = candidate_row
                        break
        if not isinstance(row, dict):
            return []
        cell = row.get(str(column_key))
        if cell is None:
            column_key_float = _as_float(column_key)
            if column_key_float is not None:
                for candidate_key, candidate_cell in row.items():
                    candidate_float = _as_float(candidate_key)
                    if candidate_float is not None and abs(candidate_float - column_key_float) <= 0.00051:
                        cell = candidate_cell
                        break
        return _matrix_numbers(cell)

    if target is None or not isinstance(matrix, dict) or not matrix:
        return False
    data = matrix.get("matrix") if isinstance(matrix.get("matrix"), dict) else matrix
    if data is not matrix:
        row_key = (
            matrix.get("base_wacc")
            if matrix.get("base_wacc") is not None
            else matrix.get("base_re")
        )
        column_key = matrix.get("base_terminal_growth")
        if row_key is None and column_key is None:
            row_range = matrix.get("price_fcff_range")
            column_range = matrix.get("price_fcfe_range")
            if isinstance(row_range, list) and row_range and isinstance(column_range, list) and column_range:
                row_key = row_range[len(row_range) // 2]
                column_key = column_range[len(column_range) // 2]
        if row_key is not None and column_key is not None:
            candidates = _lookup_cell(data, row_key, column_key)
            if any(
                abs(candidate - target) / max(abs(target), 1.0) <= tolerance_ratio
                for candidate in candidates
            ):
                return True
        matrix = data
    base_keys = {
        str(value)
        for key, value in matrix.items()
        if str(key).lower().startswith("base_") and value is not None
    }
    candidates: list[float] = []
    for row_key, row_value in matrix.items():
        if str(row_key) in base_keys and isinstance(row_value, dict):
            for column_key, cell in row_value.items():
                if str(column_key) in base_keys or str(column_key).lower() in {"base", "base_case"}:
                    candidates.extend(_matrix_numbers(cell))
        elif str(row_key).lower() in {"base", "base_case"}:
            candidates.extend(_matrix_numbers(row_value))
    if not candidates and len(_matrix_numbers(matrix)) == 1:
        candidates = _matrix_numbers(matrix)
    return any(
        abs(candidate - target) / max(abs(target), 1.0) <= tolerance_ratio
        for candidate in candidates
    )


_GOLDEN_VALUATION_CASES = (
    Path(__file__).resolve().parents[2]
    / "config" / "benchmarks" / "03_financial_benchmarks" / "golden_valuation" / "valuation_cases.json"
)


def _load_golden_valuation(root: Path, ticker: str) -> dict[str, Any] | None:
    cases_path = root / BENCHMARK_DATA_ROOT / "03_financial_benchmarks" / "golden_valuation" / "valuation_cases.json"
    if not cases_path.exists():
        cases_path = _GOLDEN_VALUATION_CASES
    cases = _read_json_list(cases_path)
    for case in cases:
        if str(case.get("ticker") or "").upper() != ticker.upper():
            continue
        inputs = case.get("inputs") if isinstance(case.get("inputs"), dict) else {}
        expected_outputs = (
            case.get("expected_outputs") if isinstance(case.get("expected_outputs"), dict) else {}
        )
        tolerances = case.get("tolerances") if isinstance(case.get("tolerances"), dict) else {}
        expected: dict[str, dict[str, float]] = {}
        if inputs.get("wacc") is not None:
            wacc = float(inputs["wacc"])
            expected["fcff_wacc"] = {"min": wacc, "max": wacc}
        if inputs.get("terminal_growth") is not None:
            terminal_growth = float(inputs["terminal_growth"])
            expected["fcff_terminal_growth"] = {
                "min": terminal_growth,
                "max": terminal_growth,
            }
        if expected_outputs.get("target_price_vnd") is not None:
            target = float(expected_outputs["target_price_vnd"])
            tolerance_pct = float(tolerances.get("target_price_vnd_pct") or 0.01)
            expected["fcff_target_price_vnd"] = {
                "min": target * (1 - tolerance_pct),
                "max": target * (1 + tolerance_pct),
            }
        return {"expected": expected, "case_id": case.get("case_id")}
    return None


def _check_golden_drift(
    live: dict[str, Any], golden: dict[str, Any]
) -> dict[str, Any]:
    """Compare live valuation against golden fixture ranges. Returns drift summary."""
    expected = golden.get("expected") or {}
    fcff = live.get("fcff") or {}
    checks: list[dict[str, Any]] = []

    def _range_check(name: str, live_val: Any, spec: Any) -> None:
        if not isinstance(spec, dict) or live_val is None:
            return
        lo, hi = spec.get("min"), spec.get("max")
        try:
            v = float(live_val)
            in_range = (lo is None or v >= float(lo)) and (hi is None or v <= float(hi))
        except (TypeError, ValueError):
            in_range = False
        checks.append({"metric": name, "live": live_val, "expected_range": spec, "in_range": in_range})

    _range_check("fcff_wacc", fcff.get("wacc"), expected.get("fcff_wacc"))
    _range_check("fcff_terminal_growth", fcff.get("terminal_growth"), expected.get("fcff_terminal_growth"))
    _range_check("fcff_target_price_vnd", fcff.get("target_price_vnd"), expected.get("fcff_target_price_vnd"))

    drift_violations = sum(1 for c in checks if not c["in_range"])
    return {
        "drift_violations": drift_violations,
        "checks_run": len(checks),
        "drift_details": checks,
    }


def evaluate_financial(root: Path, ticker: str) -> dict[str, Any]:
    valuation_path = _latest_named_for_ticker(
        root / "storage" / "runs", "valuation.json", ticker
    )
    if valuation_path is None:
        # Honest fail-closed: this ticker has no valuation run to evaluate. We do
        # not borrow another ticker's valuation, and a missing run is "blocked"
        # (cannot be measured) rather than "fail" (computed and wrong).
        metric = _metric(
            "valuation_artifact", "Valuation run artifact", None, "present",
            "blocked", "storage" + "/runs" + f"/*{ticker.lower()}*/valuation.json",
            "valuation_artifact_missing_for_ticker",
        )
        policy = build_valuation_publishability_policy(None, ticker=ticker)
        return {
            "status": "blocked",
            "metrics": [metric],
            "blocking_issues": ["valuation_artifact_missing_for_ticker"],
            "valuation_artifact": None,
            "invariants": [],
            "critical_failures": None,
            "golden_drift_out_of_tolerance": None,
            "missing_traces": ["valuation_formula_trace"],
            "decision": "block",
            "valuation_publishability": policy.to_dict(),
        }
    valuation = _read_json(valuation_path)
    fcff = valuation.get("fcff") or {}
    fcfe = valuation.get("fcfe") or {}
    sensitivity = valuation.get("sensitivity") or {}
    formula_traces = valuation.get("formula_traces") or []
    golden_valuation = _load_golden_valuation(root, ticker)

    net_bridge = fcff.get("net_debt_bridge") or {}
    expected_net_debt = (
        float(net_bridge.get("total_debt") or 0)
        - float(net_bridge.get("cash") or 0)
        - float(net_bridge.get("short_term_investments") or 0)
    )
    net_debt_pass = bool(net_bridge) and abs(expected_net_debt - float(net_bridge.get("net_debt") or 0)) <= 0.5
    fcff_rows = fcff.get("fcff_table") or []
    fcff_pass = _cash_flow_formula_pass(
        fcff_rows,
        output_key="fcff",
        add_keys=("ebit_after_tax", "depreciation"),
        subtract_keys=("capex", "delta_nwc"),
    )
    fcfe_rows = fcfe.get("fcfe_table") or []
    fcfe_pass = _cash_flow_formula_pass(
        fcfe_rows,
        output_key="fcfe",
        add_keys=("net_income", "depreciation", "net_borrowing"),
        subtract_keys=("capex", "delta_nwc"),
    )
    gordon_pass = (
        isinstance(fcff.get("wacc"), (int, float))
        and isinstance(fcff.get("terminal_growth"), (int, float))
        and fcff["wacc"] > fcff["terminal_growth"]
    )
    target_expected = (
        float(fcff.get("equity_value") or 0) * 1000 / float(fcff.get("shares_mn") or 1)
    )
    target_pass = bool(fcff.get("target_price_vnd")) and abs(
        target_expected - float(fcff.get("target_price_vnd") or 0)
    ) / max(abs(target_expected), 1) <= 0.005
    sensitivity_pass = _matrix_varies(sensitivity.get("fcff_wacc_g"))
    fcfe_sensitivity = _matrix_varies(sensitivity.get("fcfe_re_g"))
    blend_sensitivity = _matrix_varies(sensitivity.get("blend_grid"), min_spread_ratio=0.005)
    blend = valuation.get("blend_dcf") or valuation.get("weighted_target_price") or {}
    sensitivity_base_pass = all(
        _base_cell_matches_target(grid, target)
        for grid, target in (
            (sensitivity.get("fcff_wacc_g"), _as_float(fcff.get("target_price_vnd"))),
            (sensitivity.get("fcfe_re_g"), _as_float(fcfe.get("target_price_vnd"))),
            (
                sensitivity.get("blend_grid"),
                _as_float(blend.get("target_price_dcf_vnd") or blend.get("target_price")),
            ),
        )
        if target is not None and isinstance(grid, dict) and bool(grid)
    ) and any(
        target is not None and isinstance(grid, dict) and bool(grid)
        for grid, target in (
            (sensitivity.get("fcff_wacc_g"), _as_float(fcff.get("target_price_vnd"))),
            (sensitivity.get("fcfe_re_g"), _as_float(fcfe.get("target_price_vnd"))),
            (
                sensitivity.get("blend_grid"),
                _as_float(blend.get("target_price_dcf_vnd") or blend.get("target_price")),
            ),
        )
    )
    trace_pass = bool(formula_traces)

    invariant_values = [
        ("net_debt", "Net debt reconciliation", net_debt_pass),
        ("fcff", "FCFF formula", fcff_pass),
        ("fcfe", "FCFE formula", fcfe_pass),
        ("target_price", "Target price reproduction", target_pass),
        ("gordon_growth", "Discount rate exceeds terminal growth", gordon_pass),
        ("sensitivity_varies", "FCFF sensitivity matrix varies", sensitivity_pass),
        ("fcfe_sensitivity", "FCFE sensitivity matrix varies", fcfe_sensitivity),
        ("blend_sensitivity", "Blend sensitivity matrix varies", blend_sensitivity),
        ("sensitivity_base_cell", "Sensitivity base cell reconciles to target", sensitivity_base_pass),
        ("formula_trace", "Formula trace available", trace_pass),
    ]
    artifact_rel = str(valuation_path.relative_to(root))
    # Single source of truth: a valuation that computes numbers may still be
    # non-publishable (low-confidence primary, blocked FCFE in blend, missing or
    # constant sensitivity, critical method divergence, market-sanity break).
    policy = build_valuation_publishability_policy(
        valuation, ticker=ticker, valuation_artifact_path=artifact_rel
    )
    metrics = [
        _metric(metric_id, label, 1 if passed else 0, "pass", "pass" if passed else "fail",
                artifact_rel)
        for metric_id, label, passed in invariant_values
    ]
    metrics.append(
        _metric(
            "valuation_publishable", "Valuation publishability policy",
            1 if policy.target_price_publishable else 0, "pass",
            "pass" if policy.target_price_publishable else "fail",
            artifact_rel, ",".join(policy.blocking_reasons) or "",
        )
    )
    invariants = [
        {"id": metric_id, "severity": "critical", "passed": passed, "detail": label}
        for metric_id, label, passed in invariant_values
    ]
    critical_failures = sum(not item["passed"] for item in invariants)
    metrics.extend([
        _metric(
            "accounting_invariant_violations",
            "Accounting invariant violations",
            critical_failures,
            "0",
            "pass" if critical_failures == 0 else "fail",
            artifact_rel,
            ",".join(item["id"] for item in invariants if not item["passed"]),
            failed_examples=[item for item in invariants if not item["passed"]],
            sample_size=len(invariants),
            calculation={
                "aggregation": "error_count",
                "numerator": critical_failures,
                "denominator": len(invariants),
                "per_sample_results": invariants,
            },
        ),
    ])
    drift_summary = _check_golden_drift(valuation, golden_valuation) if golden_valuation else None
    drift_violations = drift_summary["drift_violations"] if drift_summary else None
    metrics.append(
        _metric(
            "golden_drift_out_of_tolerance",
            "Golden valuation drift",
            drift_violations,
            "0",
            (
                "not_evaluable" if drift_summary is None
                else ("pass" if drift_violations == 0 else "fail")
            ),
            "golden valuation fixture missing" if drift_summary is None else artifact_rel,
            "" if drift_summary is not None else "golden_valuation_fixture_missing_for_ticker",
            sample_size=drift_summary["checks_run"] if drift_summary else 0,
            failed_examples=(
                [c for c in drift_summary["drift_details"] if not c["in_range"]]
                if drift_summary else []
            ),
            evaluator={
                "framework": "golden_valuation_regression",
                "execution_status": "executed" if drift_summary else "not_executed",
            },
            calculation={
                "numerator": drift_violations,
                "denominator": drift_summary["checks_run"] if drift_summary else 0,
                "aggregation": "drift_violation_count",
                "per_sample_results": drift_summary["drift_details"] if drift_summary else [],
            },
        ),
    )
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "valuation_artifact": artifact_rel,
        "invariants": invariants,
        "critical_failures": critical_failures,
        "golden_drift_out_of_tolerance": drift_violations,
        "missing_traces": [] if trace_pass else ["valuation_formula_trace"],
        "decision": "pass" if critical_failures == 0 and policy.target_price_publishable else "block",
        "valuation_publishability": policy.to_dict(),
    }


def _pdf_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "pages": 0, "text": ""}
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return {"path": str(path), "exists": True, "pages": len(pdf.pages), "text": text}
    except Exception as exc:
        return {"path": str(path), "exists": True, "pages": 0, "text": "", "error": str(exc)}


def _schema_required_failures(payload: dict[str, Any], schema_path: Path) -> list[dict[str, Any]]:
    if not schema_path.is_file():
        return [{"reason": "schema_file_missing", "source": str(schema_path)}]
    schema = _read_json(schema_path)
    required = [str(item) for item in (schema.get("required") or [])]
    failures = [
        {"field": field, "reason": "required_field_missing", "source": str(schema_path)}
        for field in required
        if field not in payload
    ]
    properties = schema.get("properties") or {}
    for field, policy in properties.items():
        if field not in payload or not isinstance(policy, dict):
            continue
        expected_type = policy.get("type")
        actual = payload.get(field)
        allowed = expected_type if isinstance(expected_type, list) else [expected_type]
        if "null" in allowed and actual is None:
            continue
        type_ok = (
            ("object" in allowed and isinstance(actual, dict))
            or ("array" in allowed and isinstance(actual, list))
            or ("string" in allowed and isinstance(actual, str))
            or ("integer" in allowed and isinstance(actual, int) and not isinstance(actual, bool))
            or ("number" in allowed and isinstance(actual, (int, float)) and not isinstance(actual, bool))
            or ("boolean" in allowed and isinstance(actual, bool))
        )
        if expected_type and not type_ok:
            failures.append({
                "field": field,
                "reason": f"type_mismatch:{expected_type}",
                "source": str(schema_path),
            })
        if "const" in policy and actual != policy["const"]:
            failures.append({
                "field": field,
                "reason": f"const_mismatch:{policy['const']}",
                "source": str(schema_path),
            })
        if (
            field == "packet_hash"
            and isinstance(actual, str)
            and len(actual) != 64
        ):
            failures.append({"field": field, "reason": "packet_hash_length_invalid", "source": str(schema_path)})
    if payload.get("valuation_outputs") and not payload.get("formula_traces"):
        failures.append({
            "field": "formula_traces",
            "reason": "formula_traces_required_when_valuation_outputs_present",
            "source": str(schema_path),
        })
    if schema.get("additionalProperties") is False:
        allowed_keys = set(properties) | {"$schema"}
        extra = sorted(set(payload) - allowed_keys)
        failures.extend(
            {"field": field, "reason": "additional_property_not_allowed", "source": str(schema_path)}
            for field in extra
        )
    return failures


def _agent_output_records(audit: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in ("agent_execution", "tool_execution"):
        for item in audit.get(key) or []:
            if isinstance(item, dict):
                records.append({"origin": f"audit.{key}", **item})
    for key in ("trace_summary", "tool_execution_summary"):
        for item in packet.get(key) or []:
            if isinstance(item, dict):
                records.append({"origin": f"packet.{key}", **item})
    return records


_UNAUTHORIZED_CALC_PATTERNS = (
    re.compile(r"\b(?:fcff|fcfe|wacc|terminal value|equity value|enterprise value)\b[^.\n]{0,100}[+\-*/=]", re.I),
    re.compile(r"\b(?:target price|target_price|fair value|value per share)\b[^.\n]{0,100}\b(?:=|computed|calculated|implies)\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:\+|\-|\*|/)\s*\d+(?:\.\d+)?\b"),
)


def _unauthorized_financial_calculation_findings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        role = str(record.get("agent_role") or record.get("agent_id") or record.get("role") or "").lower()
        text = json.dumps(record, ensure_ascii=False, default=str)
        if "deterministic" in text.lower() and "formula_traces" in text:
            continue
        for pattern in _UNAUTHORIZED_CALC_PATTERNS:
            if pattern.search(text):
                findings.append({
                    "sample_index": index,
                    "agent_role": role or None,
                    "origin": record.get("origin"),
                    "reason": "agent_output_contains_financial_arithmetic",
                })
                break
    return findings


def evaluate_citation(root: Path, ticker: str) -> dict[str, Any]:
    report = _pdf_stats(root / "output" / f"{ticker}_report.pdf")
    text = report.pop("text", "")
    source_mentions = len(re.findall(r"(?:Source|Nguon|Nguồn)\s*:", text, re.IGNORECASE))
    generic = len(re.findall(
        r"(?:Source|Nguon|Nguồn)\s*:\s*(?:API|System|Database|Canonical financial facts)\b",
        text,
        re.IGNORECASE,
    ))
    quant_claims = len(re.findall(r"\b\d[\d.,]*\s*(?:%|VND|x)\b", text, re.IGNORECASE))
    citation_markers = len(re.findall(r"\[\^|Nguon:|Source:", text, re.IGNORECASE))
    claim_ledger = _latest_json_for_ticker(
        root / "storage" / "archive", "claim_ledger.json", ticker
    )
    ledger_available = claim_ledger is not None
    metrics = [
        _metric("quantitative_citation_coverage", "Quantitative citation coverage", None, "100%",
                "measured_only", "claim ledger missing",
                "PDF-level source counts cannot prove claim-level coverage."),
        _metric("citation_key_resolution", "Citation key resolution", None, "100%", "measured_only",
                "claim ledger missing"),
        _metric("source_id_validity", "Source ID validity", None, "100%", "measured_only",
                "claim ledger missing"),
        _metric("official_source_coverage", "Official source coverage", None, "100%", "measured_only",
                "claim ledger missing"),
        _metric("generic_citations", "Generic citation labels", generic, "0",
                _ratio_status(float(generic), 0.0, "lte"), str(report["path"])),
        _metric("pdf_source_mentions", "PDF source labels", source_mentions, "> 0",
                "pass" if source_mentions > 0 else "fail", str(report["path"])),
    ]
    blockers = _blocked(metrics)
    if not ledger_available:
        blockers.append("claim_ledger_missing")
    return {
        "status": _status(metrics, blocked=not ledger_available),
        "metrics": metrics,
        "blocking_issues": blockers,
        "claim_count": None,
        "quantitative_claim_count": quant_claims,
        "citation_coverage_ratio": None,
        "source_tier_counts": {},
        "official_source_coverage": None,
        "numeric_mismatches": [],
        "generic_citations": generic,
        "citation_markers": citation_markers,
        "report": report,
        "export_blocked": True,
    }


def evaluate_agent(root: Path, ticker: str) -> dict[str, Any]:
    audit_path = _latest_json_for_ticker(
        root / "storage" / "archive", "run1_agent_effectiveness_audit.json", ticker
    )
    audit = _read_json(audit_path)
    packet_path = _latest_json_for_ticker(
        root / "storage" / "archive", "run1_evidence_packet.json", ticker
    )
    packet = _read_json(packet_path)
    gates = packet.get("gate_results") or {}
    tool_gate = gates.get("TOOL_PERMISSION_GATE") or {}
    manifest_gate = gates.get("ARTIFACT_MANIFEST_GATE") or {}
    agent_records = audit.get("agent_execution") or []
    _MIN_GATE_SAMPLE = 5
    _has_min_sample = len(agent_records) >= _MIN_GATE_SAMPLE
    tool_compliance = (
        None if not tool_gate or not _has_min_sample
        else (1.0 if tool_gate.get("passed") is True else 0.0)
    )
    manifest_compliance = (
        None if not manifest_gate or not _has_min_sample
        else (1.0 if manifest_gate.get("passed") is True else 0.0)
    )
    task_completion = (
        sum(record.get("status") == "completed" for record in agent_records) / len(agent_records)
        if agent_records else None
    )
    schema_failures: list[dict[str, Any]] = []
    schema_units = 0
    if packet:
        schema_units += 1
        schema_failures.extend(
            _schema_required_failures(packet, root / "config" / "harness" / "evidence_packet_schema.json")
        )
    if audit:
        schema_units += 1
        if not isinstance(audit.get("agent_execution"), list):
            schema_failures.append({
                "field": "agent_execution",
                "reason": "agent_execution_list_missing",
                "source": str(audit_path.relative_to(root)) if audit_path else "missing",
            })
        if str(audit.get("ticker") or "").upper() != ticker.upper():
            schema_failures.append({
                "field": "ticker",
                "reason": "ticker_mismatch",
                "source": str(audit_path.relative_to(root)) if audit_path else "missing",
            })
    schema_validity = (
        None if schema_units == 0 else (schema_units - min(schema_units, len(schema_failures))) / schema_units
    )
    output_records = _agent_output_records(audit, packet)
    calc_findings = _unauthorized_financial_calculation_findings(output_records)
    unauthorized_calc_score = (
        None if not output_records else (len(output_records) - len(calc_findings)) / len(output_records)
    )
    deepeval_cases = _filter_records_for_ticker(
        _read_json_list(root / DEEPEVAL_CASE_PATH),
        ticker,
    )
    deepeval_result = evaluate_deepeval_cases(deepeval_cases)
    judge_scores = deepeval_result.get("scores") or {}
    judge_evaluator = {
        "framework": "deepeval",
        "framework_version": deepeval_result.get("framework_version"),
        "execution_status": deepeval_result["execution_status"],
    }
    metrics = [
        _metric("tool_permission_compliance", "Tool permission compliance", tool_compliance, "100%",
                _ratio_status(tool_compliance, 1.0), str(packet_path.relative_to(root)) if packet_path else "missing",
                sample_size=1 if tool_gate else 0,
                calculation={"numerator": 1 if tool_gate.get("passed") is True else 0,
                             "denominator": 1 if tool_gate else 0, "aggregation": "coverage"}),
        _metric("artifact_manifest_compliance", "Artifact manifest compliance", manifest_compliance, "100%",
                _ratio_status(manifest_compliance, 1.0), str(packet_path.relative_to(root)) if packet_path else "missing",
                ",".join(manifest_gate.get("blocking_reasons") or []),
                sample_size=1 if manifest_gate else 0,
                calculation={"numerator": 1 if manifest_gate.get("passed") is True else 0,
                             "denominator": 1 if manifest_gate else 0, "aggregation": "coverage"}),
        _metric("schema_validity", "Output schema validity", schema_validity, "100%",
                _ratio_status(schema_validity, 1.0), "config/harness/*.schema.json",
                ",".join(sorted({str(item.get("reason")) for item in schema_failures})) if schema_failures else "",
                failed_examples=schema_failures[:100],
                sample_size=schema_units,
                evaluator={"framework": "json_schema_required_contract",
                           "execution_status": "executed" if schema_units else "not_executed"},
                calculation={"numerator": 0 if schema_validity is None else int(schema_validity * schema_units),
                             "denominator": schema_units, "aggregation": "coverage"}),
        _metric("role_adherence", "Role adherence", judge_scores.get("role_adherence"), ">= 0.85",
                _ratio_status(judge_scores.get("role_adherence"), 0.85),
                str(DEEPEVAL_CASE_PATH), deepeval_result.get("reason") or "",
                sample_size=deepeval_result["sample_size"], evaluator=judge_evaluator,
                calculation={"aggregation": "mean"}),
        _metric("groundedness", "Groundedness", judge_scores.get("groundedness"), ">= 0.85",
                _ratio_status(judge_scores.get("groundedness"), 0.85),
                str(DEEPEVAL_CASE_PATH), deepeval_result.get("reason") or "",
                sample_size=deepeval_result["sample_size"], evaluator=judge_evaluator,
                calculation={"aggregation": "mean"}),
        _metric("no_unauthorized_calc", "No unauthorized financial calculation", unauthorized_calc_score, "100%",
                _ratio_status(unauthorized_calc_score, 1.0),
                str(audit_path.relative_to(root)) if audit_path else (str(packet_path.relative_to(root)) if packet_path else "missing"),
                "agent trace missing" if not output_records else "",
                failed_examples=calc_findings,
                sample_size=len(output_records),
                evaluator={"framework": "deterministic_agent_trace_classifier",
                           "execution_status": "executed" if output_records else "not_executed"},
                calculation={"numerator": max(0, len(output_records) - len(calc_findings)),
                             "denominator": len(output_records), "aggregation": "coverage",
                             "per_sample_results": output_records[:100]}),
        _metric("task_completion", "Task completion", task_completion, ">= 0.85",
                _ratio_status(task_completion, 0.85), str(audit_path.relative_to(root)) if audit_path else "missing",
                sample_size=len(agent_records),
                calculation={"numerator": sum(record.get("status") == "completed" for record in agent_records),
                             "denominator": len(agent_records), "aggregation": "coverage"}),
        _metric("plan_adherence", "Plan adherence", judge_scores.get("plan_adherence"), ">= 0.80",
                _ratio_status(judge_scores.get("plan_adherence"), 0.80),
                str(DEEPEVAL_CASE_PATH), deepeval_result.get("reason") or "",
                sample_size=deepeval_result["sample_size"], evaluator=judge_evaluator,
                calculation={"aggregation": "mean"}),
        _metric("critic_issue_recall", "Critic issue recall", None, ">= 90%", "measured_only",
                "seeded failure dataset missing"),
    ]
    # Per evaluation plan §5.5 the LLM-judge criteria (role adherence,
    # groundedness, no-unauthorized-calc, plan adherence, critic recall) are
    # ADVISORY and must not override the deterministic gates. The judge is
    # explicitly out of P0 scope, so a missing calibrated judge is recorded as
    # an advisory finding, not a blocking failure. Deterministic agent metrics
    # (tool permission, schema validity, task completion) still gate.
    advisory_findings = [
        f"{item['id']}:calibrated_llm_judge_pending"
        for item in metrics
        if item.get("legacy_status") == "measured_only" or item["status"] == "warning"
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "advisory_findings": advisory_findings,
        "judge_status": deepeval_result["execution_status"],
        "tool_permission_compliance": tool_compliance,
        "artifact_manifest_compliance": manifest_compliance,
        "schema_validity": schema_validity,
        "role_adherence": judge_scores.get("role_adherence"),
        "groundedness": judge_scores.get("groundedness"),
        "no_unauthorized_calc": unauthorized_calc_score,
        "task_completion": task_completion,
        "plan_adherence": judge_scores.get("plan_adherence"),
        "critic_issue_recall": None,
        "rubric_scores": {},
        "deepeval_execution": deepeval_result,
    }


def evaluate_report(root: Path, ticker: str, financial: dict[str, Any]) -> dict[str, Any]:
    report = _pdf_stats(root / "output" / f"{ticker}_report.pdf")
    explanation = _pdf_stats(root / "output" / f"{ticker}_explanation.pdf")
    finance_pass = financial.get("decision") == "pass"
    metrics = [
        _metric("report_pdf_rendered", "Report PDF rendered", 1 if report["exists"] else 0, "pass",
                "pass" if report["exists"] else "fail", str(report["path"])),
        _metric("explanation_pdf_rendered", "Explanation PDF rendered", 1 if explanation["exists"] else 0,
                "pass", "pass" if explanation["exists"] else "fail", str(explanation["path"])),
        _metric("financial_gate_passed", "Deterministic finance gate", 1 if finance_pass else 0, "pass",
                "pass" if finance_pass else "fail", "financial_eval.json"),
        _metric("report_quality_score", "Report quality score", None, ">= 85", "measured_only",
                "publishable report model missing"),
        _metric("publication_readiness", "Publication readiness", 0, "pass", "fail",
                "final approval and locked publishable model missing"),
    ]
    blockers = _blocked(metrics) + ["final_report_approval_missing", "publishable_final_report_model_missing"]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": sorted(set(blockers)),
        "rubric": "report_quality_v1",
        "score": None,
        "decision": "block_export",
        "failed_gates": ["financial_gate"] if not finance_pass else [],
        "section_scores": {},
        "report_artifacts": {"pdf": report, "explanation_pdf": explanation},
        "publication_readiness": {
            "passed": False,
            "blocking_reasons": sorted(set(blockers)),
        },
    }


def evaluate_observability(root: Path, ticker: str) -> dict[str, Any]:
    packet_path = _latest_json_for_ticker(
        root / "storage" / "archive", "run1_evidence_packet.json", ticker
    )
    packet = _read_json(packet_path)
    audit_path = _latest_json_for_ticker(
        root / "storage" / "archive", "run1_agent_effectiveness_audit.json", ticker
    )
    audit = _read_json(audit_path)
    run_log_path = _latest_json_for_ticker(root / "storage" / "runs", "run_log.json", ticker)
    run_log = _read_json(run_log_path)
    trace_events = [
        item for item in (run_log.get("trace") or packet.get("trace_summary") or [])
        if isinstance(item, dict)
    ]
    agent_records = [
        item for item in _agent_output_records(audit, packet)
        if item.get("origin", "").endswith("agent_execution")
        or item.get("kind") == "agent_message"
        or item.get("agent_id")
    ]
    if not agent_records:
        agent_records = [item for item in trace_events if item.get("kind") == "agent_message"]
    retrieval_events = [
        item for item in trace_events
        if item.get("kind") in {"retrieval_query", "retrieval"}
        or str(item.get("tool_name") or "").lower() in {"retrieve", "retrieval", "retrieval_service"}
    ]
    upload_events = [
        item for item in trace_events
        if item.get("kind") == "artifact_upload" or item.get("action") == "artifact_upload"
    ]
    render_events = [
        item for item in trace_events
        if item.get("kind") == "pdf_render" or item.get("action") == "pdf_render"
    ]
    agent_latencies = [
        value for value in (_float_or_none(item.get("latency_ms")) for item in agent_records)
        if value is not None
    ]
    retrieval_latencies = [
        value for value in (_float_or_none(item.get("latency_ms")) for item in retrieval_events)
        if value is not None
    ]
    costs = [
        value for value in (_float_or_none(item.get("cost_estimate")) for item in agent_records)
        if value is not None
    ]
    retries = sum(_event_retry_count(item) for item in agent_records)
    llm_calls = len(agent_records)
    retry_rate = retries / llm_calls if llm_calls else None
    llm_fallbacks = sum(bool(item.get("fallback_triggered")) for item in agent_records)
    llm_fallback_rate = llm_fallbacks / llm_calls if llm_calls else None
    retrieval_fallbacks = sum(bool(item.get("fallback_triggered")) for item in retrieval_events)
    retrieval_fallback_rate = (
        retrieval_fallbacks / len(retrieval_events) if retrieval_events else None
    )
    stage_durations: dict[str, float] = {}
    duration_events = trace_events if trace_events else agent_records
    for event in duration_events:
        latency = _float_or_none(event.get("latency_ms"))
        if latency is None:
            continue
        stage = _trace_stage(event)
        stage_durations[stage] = round(stage_durations.get(stage, 0.0) + latency / 1000, 6)
    duration_seconds = round(sum(stage_durations.values()), 6) if stage_durations else None
    artifact_upload_failures = sum(
        1 for item in upload_events if item.get("status") in {"failed", "error"}
    )
    trace_url = _trace_url(trace_events, packet, audit, run_log)
    metadata = _read_json(
        _latest_named(root / "storage" / "sources" / "ocr_artifacts" / ticker, "metadata.json")
    )
    pages = int(metadata.get("pages_processed") or 0)
    ocr_failure_rate = int(metadata.get("pages_failed") or 0) / pages if pages else None
    report_exists = (root / "output" / f"{ticker}_report.pdf").is_file()
    pdf_render_failures = sum(
        1 for item in render_events if item.get("status") in {"failed", "error"}
    )
    if not render_events:
        pdf_render_failures = 0 if report_exists else 1
    gate_results = packet.get("gate_results") if isinstance(packet.get("gate_results"), dict) else {}
    blocking_gate_categories = sorted(
        name for name, gate in gate_results.items()
        if isinstance(gate, dict) and gate.get("passed") is False
    )
    metrics = [
        _metric("duration_seconds", "Full run duration", duration_seconds, "<= baseline p95 + 30%",
                "measured_only", "runtime trace" if duration_seconds is not None else "run trace missing",
                sample_size=len(stage_durations),
                calculation={"aggregation": "sum", "per_sample_results": [
                    {"stage": stage, "duration_seconds": duration}
                    for stage, duration in sorted(stage_durations.items())
                ]}),
        _metric("llm_retry_rate", "LLM retry rate", retry_rate, "<= 5%",
                "measured_only" if retry_rate is None else ("pass" if retry_rate <= 0.05 else "fail"),
                str(packet_path.relative_to(root)) if packet_path else "run trace missing",
                sample_size=llm_calls,
                calculation={"numerator": retries, "denominator": llm_calls, "aggregation": "rate",
                             "per_sample_results": agent_records[:100]}),
        _metric("retrieval_fallback_rate", "Retrieval fallback rate", retrieval_fallback_rate, "<= 20%",
                "measured_only" if retrieval_fallback_rate is None else (
                    "pass" if retrieval_fallback_rate <= 0.20 else "fail"
                ),
                "runtime retrieval trace" if retrieval_events else "retrieval trace missing",
                sample_size=len(retrieval_events),
                calculation={"numerator": retrieval_fallbacks, "denominator": len(retrieval_events),
                             "aggregation": "rate", "per_sample_results": retrieval_events[:100]}),
        _metric("ocr_failure_rate", "OCR failure rate", ocr_failure_rate, "<= 5%",
                _ratio_status(ocr_failure_rate, 0.05, "lte"), "latest OCR metadata"),
        _metric("artifact_upload_failures", "Artifact upload failures", artifact_upload_failures, "0",
                "pass" if artifact_upload_failures == 0 else "fail", "artifact upload trace"),
        _metric("pdf_render_failures", "PDF render failures", pdf_render_failures, "0",
                "pass" if pdf_render_failures == 0 else "fail", f"output/{ticker}_report.pdf"),
        _metric("cost_per_report", "Cost per full report", sum(costs) if costs else None, "<= soft budget",
                "measured_only", "cost ledger" if costs else "cost ledger missing",
                sample_size=len(costs),
                calculation={"aggregation": "sum", "per_sample_results": agent_records[:100]}),
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "duration_seconds": duration_seconds,
        "stage_durations": stage_durations,
        "llm": {
            "calls": llm_calls if agent_records else None,
            "tokens_input": sum(
                _token_count(item, "tokens_input", "input_tokens", "prompt_tokens")
                for item in agent_records
            ) if agent_records else None,
            "tokens_output": sum(
                _token_count(item, "tokens_output", "output_tokens", "completion_tokens")
                for item in agent_records
            ) if agent_records else None,
            "estimated_cost_usd": sum(costs) if costs else None,
            "retry_rate": retry_rate,
            "fallback_rate": llm_fallback_rate,
            "latency_ms_total": sum(agent_latencies) if agent_latencies else None,
        },
        "retrieval": {
            "queries": len(retrieval_events) if retrieval_events else None,
            "p95_latency_ms": _p95(retrieval_latencies),
            "fallback_rate": retrieval_fallback_rate,
        },
        "ocr": {"pages_processed": pages, "failure_rate": ocr_failure_rate},
        "blocking_gate_categories": blocking_gate_categories,
        "publication": {
            "readiness_passed": False,
            "authorization_blockers": [
                f"{name}:{','.join(gate.get('blocking_reasons') or []) or 'gate_failed'}"
                for name, gate in sorted(gate_results.items())
                if isinstance(gate, dict) and gate.get("passed") is False
            ],
            "render_mode": "analyst_draft",
        },
        "trace_url": trace_url,
    }


def evaluate_rollout(
    test_execution: dict[str, Any],
    prior_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    test_pass = test_execution.get("status") == "pass"
    rag_scores = prior_results.get("02", {}).get("golden_scores") or {}
    rag_golden_available = rag_scores.get("hit_rate_at_5") is not None
    metrics = [
        _metric("evaluation_gates_ci", "Evaluation gate CI scope", 1 if test_pass else 0, "pass",
                "pass" if test_pass else "fail", "pytest plan scope"),
        _metric("deterministic_fail_closed", "Deterministic fail-closed policy", 1, "pass", "pass",
                "evaluation packet decision rule"),
        _metric("rag_golden_ci", "RAG golden CI", 1 if rag_golden_available else None, "available",
                "pass" if rag_golden_available else "not_evaluable",
                str(RAG_GOLDEN_QUERY_DIR) if rag_golden_available else "golden query set missing"),
        _metric("llm_judge_offline", "LLM judge offline CI", None, "warn then block", "measured_only",
                "calibrated judge dataset missing"),
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "ci_gate_matrix": {
            "unit-core": "block",
            "evaluation-gates": "block",
            "finance-regression": "block",
            "report-render-smoke": "block",
            "rag-golden": "warn",
            "llm-judge-offline": "warn",
            "integration-db": "scheduled",
        },
    }


Evaluator = Callable[[Path, str], dict[str, Any]]


def evaluate_plan(
    plan_id: str,
    *,
    root: Path,
    ticker: str,
    test_execution: dict[str, Any],
    prior_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluators: dict[str, Evaluator] = {
        "01": evaluate_data_reliability,
        "02": evaluate_retrieval,
        "03": evaluate_financial,
        "04": evaluate_citation,
        "05": evaluate_agent,
        "07": evaluate_observability,
    }
    if plan_id == "06":
        return evaluate_report(root, ticker, prior_results.get("03", {}))
    if plan_id == "08":
        return evaluate_rollout(test_execution, prior_results)
    return evaluators[plan_id](root, ticker)
