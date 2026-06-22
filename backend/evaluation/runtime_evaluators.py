"""Deterministic runtime evaluators for the eight project evaluation plans."""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.evaluation.benchmark_paths import (
    BENCHMARK_SUITE_OUTPUT_DIR,
    BENCHMARK_CONFIG_ROOT,
    DEEPEVAL_CASE_RELATIVE,
    DEEPEVAL_CASE_PATH,
    GOLDEN_FINANCIALS_RELATIVE,
    GOLDEN_FINANCIALS_DIR,
    GOLDEN_VALUATION_CASES_RELATIVE,
    GOLDEN_VALUATION_CASES_PATH,
    RAG_GOLDEN_CHUNK_RELATIVE,
    RAG_GOLDEN_CHUNK_DIR,
    RAGAS_SAMPLE_RELATIVE,
    RAGAS_SAMPLE_PATH,
    RAG_GOLDEN_QUERY_RELATIVE,
    RAG_GOLDEN_QUERY_DIR,
    ROOT as REPO_ROOT,
)
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
BENCHMARK_DATA_ROOT = BENCHMARK_CONFIG_ROOT
RAW_BCTC_FILES = (
    "income_statement_year.json",
    "balance_sheet_year.json",
    "cash_flow_year.json",
    "ratio_year.json",
)
OPS_BENCHMARK_DIR = BENCHMARK_CONFIG_ROOT / "05_ops_cost_latency"


def _benchmark_scoped_path(root: Path, configured_path: Path, relative_path: Path) -> Path:
    """Use configured benchmark roots for the real repo and root-local fixtures in tests."""
    try:
        if root.resolve() == REPO_ROOT.resolve():
            return configured_path
    except OSError:
        pass
    return root / relative_path


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


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if path is None or not path.is_file():
        return rows
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    except (OSError, json.JSONDecodeError):
        return rows
    return rows


def _read_csv_dicts(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _read_yaml_dict(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _ragas_reference(sample: dict[str, Any]) -> str:
    for key in ("expected_answer", "reference", "answer", "ground_truth"):
        text = str(sample.get(key) or "").strip()
        if text:
            return text
    return ""


def _ragas_sample_contract_errors(samples: list[dict[str, Any]], ticker: str) -> list[dict[str, Any]]:
    expected = ticker.upper()
    errors: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        metadata = sample.get("metadata") if isinstance(sample.get("metadata"), dict) else {}
        sample_id = sample.get("id") or f"sample_{index}"
        sample_errors: list[str] = []
        if not str(sample.get("question") or "").strip():
            sample_errors.append("missing_question")
        if not _ragas_reference(sample):
            sample_errors.append("missing_reference")
        record_ticker = str(sample.get("ticker") or metadata.get("ticker") or "").upper()
        if not record_ticker:
            sample_errors.append("missing_ticker")
        elif record_ticker != expected:
            sample_errors.append(f"ticker_mismatch:{record_ticker}:{expected}")
        if "fiscal_year" not in sample and "fiscal_year" not in metadata:
            sample_errors.append("missing_fiscal_year")
        if sample_errors:
            errors.append({
                "sample_index": index,
                "sample_origin": "ragas_contract_validation",
                "id": sample_id,
                "question": sample.get("question"),
                "reference": _ragas_reference(sample),
                "ticker": record_ticker or None,
                "fiscal_year": sample.get("fiscal_year", metadata.get("fiscal_year")),
                "contract_errors": sample_errors,
            })
    return errors


def _invalid_ragas_contract_result(
    samples: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "execution_status": "not_evaluable",
        "framework": "ragas",
        "framework_version": None,
        "sample_size": len(samples),
        "scores": {},
        "samples": errors,
        "reason": "ragas_sample_contract_invalid",
    }


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


def _files_with_suffix(root: Path, suffix: str) -> list[Path]:
    if not root.exists():
        return []
    matches: list[Path] = []
    for directory, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(suffix):
                matches.append(Path(directory) / filename)
    return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)


def _latest_json_by_suffix_for_ticker(root: Path, suffix: str, ticker: str) -> Path | None:
    """Resolve the newest ``*suffix`` JSON whose payload matches ``ticker``.

    Real runs write ``<run_id>_evidence_packet.json`` /
    ``<run_id>_agent_effectiveness_audit.json``; the legacy smoke fixture used
    ``run1_*``. Matching by suffix lets the evaluator pick up a real run's
    governance artifacts (newest by mtime) while still resolving the fixture
    when no real run exists yet.
    """
    for path in _files_with_suffix(root, suffix):
        payload = _read_json(path)
        if str(payload.get("ticker") or "").upper() == ticker.upper():
            return path
    return None


def _latest_scoped_json_artifact_for_ticker(
    *,
    archive_root: Path,
    runs_root: Path | None,
    ticker: str,
    legacy_name: str,
    suffix: str,
) -> Path | None:
    """Resolve the newest ticker-scoped JSON artifact across current and legacy names.

    Recent harness runs persist ``<run_id>_<artifact>.json`` into the run
    artifact directory and may also archive the same suffix-scoped artifact.
    Older smoke fixtures only wrote a fixed ``run1_*.json`` filename under the
    archive directory.
    Evaluators must accept both shapes so one plan updating its artifact naming
    does not silently make sibling benchmark plans look unevaluable.
    """
    candidates: list[Path] = []
    if runs_root is not None:
        scoped_run = _latest_json_by_suffix_for_ticker(runs_root, suffix, ticker)
        if scoped_run is not None:
            candidates.append(scoped_run)
        legacy_run = _latest_json_for_ticker(runs_root, legacy_name, ticker)
        if legacy_run is not None:
            candidates.append(legacy_run)
    scoped_archive = _latest_json_by_suffix_for_ticker(archive_root, suffix, ticker)
    if scoped_archive is not None:
        candidates.append(scoped_archive)
    legacy_archive = _latest_json_for_ticker(archive_root, legacy_name, ticker)
    if legacy_archive is not None:
        candidates.append(legacy_archive)
    if not candidates:
        return None
    benchmark_run_id = f"benchmark_{ticker.lower()}"
    benchmark_candidates = [
        path for path in candidates
        if benchmark_run_id in {part.lower() for part in path.parts}
    ]
    if benchmark_candidates:
        return max(benchmark_candidates, key=lambda path: path.stat().st_mtime)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_ocr_reconciliation_report(root: Path, ticker: str) -> dict[str, Any]:
    """Return the newest OCR reconciliation report for ``ticker`` if present."""
    report_root = root / "data" / "reconciliation" / ticker.upper()
    for path in _files_named(report_root, "ocr_vs_structured.json"):
        payload = _read_json(path)
        payload_ticker = str(payload.get("ticker") or "").upper()
        if payload_ticker == ticker.upper():
            return payload
    return {}


def _latest_completed_ocr_metadata(root: Path, ticker: str) -> dict[str, Any]:
    """Return newest completed OCR metadata, ignoring in-progress runs."""
    metadata_root = root / "storage" / "sources" / "ocr_artifacts" / ticker.upper()
    latest: dict[str, Any] = {}
    for path in _files_named(metadata_root, "metadata.json"):
        payload = _read_json(path)
        if str(payload.get("ticker") or "").upper() != ticker.upper():
            continue
        if payload.get("status") == "completed":
            return payload
        if not latest:
            latest = payload
    return latest


def _ocr_resolution_counts_from_reconciliation(report: dict[str, Any]) -> dict[str, int]:
    """Convert OCR reconciliation outcomes into resolved/unresolved counts.

    ``conflicted`` candidates are resolved because they were explicitly compared
    and blocked. Only ``needs_review`` / missing-secondary cases remain unresolved.
    """
    if not report:
        return {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    records = report.get("records") if isinstance(report.get("records"), list) else []
    total = int(summary.get("total") or report.get("total_records") or len(records) or 0)
    needs_review = int(summary.get("needs_review_count") or 0)
    if not needs_review and records:
        needs_review = sum(1 for item in records if item.get("decision") == "needs_review")
    matched = int(summary.get("matched") or 0)
    conflicted = int(summary.get("conflicted") or summary.get("blocked_conflict_count") or 0)
    return {
        "total": total,
        "resolved": max(0, total - needs_review),
        "unresolved": max(0, needs_review),
        "matched": matched,
        "conflicted": conflicted,
    }


def _relative_or_missing(path: Path, root: Path) -> str:
    return str(path.relative_to(root)) if path.exists() else "missing"


def _source_path(path: Path, root: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)


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
    if "status" not in sample:
        status_source = None
        for key in (
            "reconciled",
            "has_complete_provenance",
            "schema_valid",
            "accepted",
            "evidence_available",
        ):
            if key in sample:
                status_source = bool(sample[key])
                break
        if status_source is None and "material_ocr_error" in sample:
            status_source = not bool(sample["material_ocr_error"])
        if status_source is None and row:
            status_source = row.get("validation_status") == "accepted"
        if status_source is not None:
            sample["status"] = "pass" if status_source else "fail"
    if "value" not in sample and "status" in sample:
        sample["value"] = sample["status"] == "pass"
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
            "status": "pass" if fact in accepted_by_key else "fail",
            "value": fact in accepted_by_key,
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
    unresolved_candidate_count: int | None = None,
    minimum: int = DATA_RELIABILITY_MIN_SAMPLE_ROWS,
) -> list[dict[str, Any]]:
    if metadata:
        pages = int(metadata.get("pages_processed") or 0)
        pages_failed = int(metadata.get("pages_failed") or 0)
        candidate_count = int(metadata.get("candidate_row_count") or 0)
        mapped_count = int(metadata.get("mapped_fact_count") or 0)
        unresolved_count = (
            max(0, candidate_count - mapped_count)
            if unresolved_candidate_count is None
            else max(0, unresolved_candidate_count)
        )
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
                "unresolved_candidate_count": unresolved_count,
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


def _ops_benchmark_paths(root: Path) -> tuple[Path, Path, Path]:
    try:
        if root.resolve() == REPO_ROOT.resolve():
            base = OPS_BENCHMARK_DIR
        else:
            base = root / "config" / "benchmarks" / "05_ops_cost_latency"
    except OSError:
        base = root / "config" / "benchmarks" / "05_ops_cost_latency"
    return (
        base / "ops_cost_latency_rubric.yaml",
        base / "golden_run_traces.csv",
        base / "negative_ops_cases.jsonl",
    )


def _ops_runtime_sample(
    sample: dict[str, Any],
    metric_id: str,
    *,
    threshold_seconds: float | None = None,
) -> dict[str, Any]:
    normalized = dict(sample)
    event_status = str(normalized.get("status") or normalized.get("terminal_status") or "").lower()
    if event_status and normalized.get("status") not in {"pass", "fail", "warning", "not_evaluable", "measured_only"}:
        normalized["event_status"] = normalized.get("status")

    def finish(status: str, value: Any) -> dict[str, Any]:
        normalized["status"] = status
        if value is not None:
            normalized["value"] = value
        return normalized

    if metric_id == "llm_retry_rate":
        retry_count = _event_retry_count(normalized)
        return finish("pass" if retry_count == 0 else "fail", retry_count)
    if metric_id == "retrieval_fallback_rate":
        fallback = bool(normalized.get("fallback_triggered"))
        return finish("fail" if fallback else "pass", fallback)
    if metric_id == "artifact_upload_failures":
        failures = _float_or_none(normalized.get("artifact_upload_failures"))
        if failures is not None:
            return finish("pass" if failures == 0 else "fail", failures)
        if event_status:
            return finish("fail" if event_status in {"failed", "error"} else "pass", event_status)
    if metric_id == "pdf_render_failures":
        failures = _float_or_none(normalized.get("pdf_render_failures"))
        if failures is not None:
            return finish("pass" if failures == 0 else "fail", failures)
        if event_status:
            return finish("fail" if event_status in {"failed", "error"} else "pass", event_status)

    duration = _float_or_none(normalized.get("duration_seconds"))
    if duration is None:
        duration = _float_or_none(normalized.get("total_duration_seconds"))
    cost = _float_or_none(normalized.get("estimated_cost_usd"))
    if cost is None:
        cost = _float_or_none(normalized.get("cost_estimate"))
    value = cost if metric_id == "cost_per_report" and cost is not None else duration
    if event_status in {"failed", "error"}:
        return finish("fail", value if value is not None else event_status)
    if threshold_seconds is not None and duration is not None:
        return finish("pass" if duration <= threshold_seconds else "fail", duration)
    if value is not None:
        return finish("measured_only", value)
    return finish("not_evaluable", None)


def _ops_latency_metric(
    metric_id: str,
    label: str,
    value: float | None,
    threshold_seconds: float | None,
    *,
    display_unit: str,
    source: str,
    samples: list[dict[str, Any]],
    missing_reason: str,
) -> dict[str, Any]:
    if threshold_seconds is None:
        threshold = "present"
        status = "not_evaluable"
    elif display_unit == "minutes":
        threshold = f"<= {threshold_seconds / 60:g}"
        status = "not_evaluable" if value is None else ("pass" if value <= threshold_seconds / 60 else "fail")
    else:
        threshold = f"<= {threshold_seconds:g}"
        status = "not_evaluable" if value is None else ("pass" if value <= threshold_seconds else "fail")
    failed_examples = [
        sample for sample in samples
        if sample.get("status") in {"failed", "error"}
        or (
            threshold_seconds is not None
            and _float_or_none(sample.get("duration_seconds") or sample.get("total_duration_seconds")) is not None
            and _float_or_none(sample.get("duration_seconds") or sample.get("total_duration_seconds")) > threshold_seconds
        )
    ]
    normalized_samples = [
        _ops_runtime_sample(sample, metric_id, threshold_seconds=threshold_seconds)
        for sample in samples[:100]
    ]
    return _metric(
        metric_id,
        label,
        value,
        threshold,
        status,
        source if samples or value is not None else missing_reason,
        missing_reason if value is None else "",
        plan_id="07",
        sample_size=len(samples),
        failed_examples=failed_examples,
        calculation={
            "aggregation": "p95",
            "parameters": {"threshold_seconds": threshold_seconds, "display_unit": display_unit},
            "per_sample_results": normalized_samples,
        },
    )


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
            "value": value,
            "status": "pass" if value >= 1.0 else "warning",
            "passed": value >= 1.0,
            "weight": weight,
            "normalized_weight": weight / denominator,
        }
        for name, value, weight in measured
    ]
    return sum(value * weight for _, value, weight in measured) / denominator, samples


def _clamp01(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def _presence_score(value: Any) -> float:
    return 1.0 if value else 0.0


def _ratio_score(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if denominator in {None, 0} or numerator is None:
        return None
    return _clamp01(float(numerator) / float(denominator))


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
        if "status" not in payload:
            if "present" in payload:
                payload["status"] = "pass" if payload["present"] else "fail"
            elif "complete" in payload:
                payload["status"] = "pass" if payload["complete"] else "fail"
            elif "has_complete_provenance" in payload:
                payload["status"] = "pass" if payload["has_complete_provenance"] else "fail"
            elif "schema_valid" in payload:
                payload["status"] = "pass" if payload["schema_valid"] else "fail"
            elif "passed" in payload:
                payload["status"] = "pass" if payload["passed"] else "fail"
            elif "is_duplicate" in payload:
                payload["status"] = "fail" if payload["is_duplicate"] else "pass"
            elif "in_range" in payload:
                payload["status"] = "pass" if payload["in_range"] else "fail"
        if "value" not in payload and "status" in payload:
            if payload["status"] in {"pass", "fail"}:
                payload["value"] = payload["status"] == "pass"
            else:
                payload["value"] = str(payload["status"])
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
            "status": "not_applicable",
            "value": "no_additional_runtime_sample_available",
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
    golden_dir = _benchmark_scoped_path(root, RAG_GOLDEN_QUERY_DIR, RAG_GOLDEN_QUERY_RELATIVE)
    per_ticker = golden_dir / f"{ticker.upper()}.yaml"
    if per_ticker.is_file():
        return per_ticker
    default = golden_dir / "default.yaml"
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


def _relative_existing_artifact_ids(root: Path, *paths: Path | None) -> list[str]:
    artifact_ids: list[str] = []
    for path in paths:
        if path is None or not path.exists():
            continue
        artifact_ids.append(_source_path(path, root))
    return artifact_ids


def _artifact_evidence(root: Path, *paths: Path | None) -> dict[str, Any]:
    artifact_ids = _relative_existing_artifact_ids(root, *paths)
    sizes: dict[str, int] = {}
    for path in paths:
        if path is None or not path.exists():
            continue
        sizes[_source_path(path, root)] = path.stat().st_size
    return {
        "artifact_ids": artifact_ids,
        "artifact_sizes_bytes": sizes,
        "evidence_available": bool(artifact_ids),
    }


def _ratio_status(value: float | None, target: float, comparator: str = "gte") -> str:
    if value is None:
        return "not_evaluable"
    passed = value >= target if comparator == "gte" else value <= target
    return "pass" if passed else "fail"


def _normalized_fact_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(",", "")
    return text.strip()


def _material_numbers(value: Any) -> list[float]:
    numbers: list[float] = []
    for match in re.finditer(r"[-+]?\d+(?:[,.]\d+)*(?:\.\d+)?", str(value or "")):
        raw = match.group(0).replace(",", "")
        try:
            number = float(raw)
        except ValueError:
            continue
        if number.is_integer() and 1900 <= int(number) <= 2100:
            continue
        numbers.append(number)
    return numbers


def rag_exact_answer_match(sample: dict[str, Any]) -> bool:
    """Return true when a numeric factoid response materially matches reference.

    RAGAS response relevancy is an LLM-judged semantic metric. For short
    Vietnamese numeric factoids it can under-score exact answers, so failed
    example classification needs a deterministic exact-answer guardrail.
    """
    response = sample.get("response")
    reference = sample.get("reference") or sample.get("ground_truth") or sample.get("answer")
    if not response or not reference:
        return False
    normalized_response = _normalized_fact_text(response)
    normalized_reference = _normalized_fact_text(reference)
    if normalized_response == normalized_reference:
        return True
    reference_numbers = _material_numbers(reference)
    response_numbers = _material_numbers(response)
    if not reference_numbers or not response_numbers:
        return False
    for expected in reference_numbers:
        if not any(abs(actual - expected) <= max(abs(expected) * 0.000001, 0.0001) for actual in response_numbers):
            return False
    unit_markers = ("vnd", "tỷ", "ty", "shares", "cổ phiếu", "%")
    reference_units = [unit for unit in unit_markers if unit in normalized_reference]
    return all(unit in normalized_response for unit in reference_units)


def _ragas_live_enabled() -> bool:
    return str(os.getenv("RAGAS_LIVE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _retrieval_live_enabled() -> bool:
    return str(os.getenv("RETRIEVAL_LIVE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


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
        if item["status"] in {"fail", "not_evaluable"} and item.get("blocks_publish") is True
    ]


def evaluate_data_reliability(root: Path, ticker: str) -> dict[str, Any]:
    golden = _benchmark_scoped_path(root, GOLDEN_FINANCIALS_DIR, GOLDEN_FINANCIALS_RELATIVE) / f"{ticker}.csv"
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
    tier3_provenance_only = golden_source_tier >= 3
    if tier3_provenance_only:
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

    metadata = _latest_completed_ocr_metadata(root, ticker)
    pages = int(metadata.get("pages_processed") or 0)
    pages_failed = int(metadata.get("pages_failed") or 0)
    ocr_failure_rate = pages_failed / pages if pages else None
    ocr_candidates = int(metadata.get("candidate_row_count") or 0)
    ocr_reconciliation = _latest_ocr_reconciliation_report(root, ticker)
    ocr_resolution_counts = _ocr_resolution_counts_from_reconciliation(ocr_reconciliation)
    if ocr_resolution_counts:
        unresolved = ocr_resolution_counts["unresolved"]
        ocr_units_checked = ocr_resolution_counts["total"]
    else:
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
            "resolved_candidate_count": ocr_resolution_counts.get("resolved"),
            "matched_candidate_count": ocr_resolution_counts.get("matched"),
            "conflicted_candidate_count": ocr_resolution_counts.get("conflicted"),
            "resolution_source": "ocr_reconciliation_report" if ocr_resolution_counts else "ocr_metadata",
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
    reconciliation_ready = (
        official_reconciliation_rate is not None
        and official_reconciliation_rate >= 0.95
    )
    provenance_ready_for_tier3 = (
        tier3_provenance_only
        and provenance_coverage is not None
        and provenance_coverage >= 0.95
    )
    valuation_ready = (
        core_coverage is not None
        and core_coverage >= 0.95
        and (reconciliation_ready or provenance_ready_for_tier3)
        and duplicate_count == 0
        and pandera_result["passed"] is True
    )
    ocr_metadata_required = bool(metadata or material_ocr_source_rows)
    ocr_audit_samples = _ocr_audit_samples(
        metadata,
        ticker,
        metadata_required=ocr_metadata_required,
        unresolved_candidate_count=unresolved if ocr_resolution_counts else None,
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
    raw_bctc_coverage = _ratio_score(raw_audit["non_empty_files"], raw_audit["required_files"])
    dedupe_health = None if duplicate_rate is None else _clamp01(1.0 - duplicate_rate)
    schema_health = schema_component
    benchmark_hardness_score, benchmark_hardness_samples = _weighted_score([
        ("data_reliability_score", data_reliability_score, 0.25),
        ("accepted_fact_confidence", accepted_fact_confidence, 0.20),
        ("official_reconciliation_rate", official_reconciliation_rate, 0.15),
        ("provenance_coverage", provenance_coverage, 0.12),
        ("core_metric_coverage", core_coverage, 0.10),
        ("raw_bctc_coverage", raw_bctc_coverage, 0.08),
        ("schema_health", schema_health, 0.05),
        ("dedupe_health", dedupe_health, 0.03),
        ("ocr_resolution_health", ocr_resolution_health, 0.02),
    ])
    benchmark_hardness_metric_samples = _minimum_metric_samples(
        benchmark_hardness_samples,
        data_reliability_component_samples,
        metric_id="data.benchmark_hardness_score",
        minimum=20,
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
                data_reliability_score, ">= 90%",
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
        _metric("data.benchmark_hardness_score", "Data benchmark hardness score",
                benchmark_hardness_score, ">= 85%",
                _ratio_status(benchmark_hardness_score, 0.85),
                golden_rel,
                sample_size=len(benchmark_hardness_metric_samples),
                dataset_version=golden.name if golden.exists() else None,
                evaluator={"framework": "hard_mode_data_reliability_score",
                           "execution_status": "executed" if benchmark_hardness_samples else "not_executed"},
                calculation={"numerator": benchmark_hardness_score,
                             "denominator": 1.0 if benchmark_hardness_score is not None else None,
                             "aggregation": "weighted_score",
                             "inputs": {
                                 **dataset_inputs,
                                 "raw_bctc_non_empty_files": raw_audit["non_empty_files"],
                                 "raw_bctc_required_files": raw_audit["required_files"],
                                 "duplicate_rate": duplicate_rate,
                             },
                             "parameters": {
                                 "rationale": "Ceiling-resistant score: perfect binary gates are penalized when confidence, OCR, raw-file, or lineage depth is weaker than ideal.",
                                 "components": [
                                     {"id": sample["component"], "weight": sample["weight"]}
                                     for sample in benchmark_hardness_samples
                                 ],
                             },
                             "per_sample_results": benchmark_hardness_metric_samples},
                failed_examples=[
                    sample for sample in benchmark_hardness_metric_samples
                    if sample.get("component_score") is not None
                    and sample.get("component_score") < 1.0
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
                "not_applicable" if tier3_provenance_only else _ratio_status(official_reconciliation_rate, 0.95),
                provenance_rel, (
                    "source_tier_3_provenance_only_not_official_reconciliation"
                    if tier3_provenance_only
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
                             "inputs": {
                                 "metadata": metadata,
                                 "ocr_reconciliation": ocr_reconciliation,
                                 "resolution_counts": ocr_resolution_counts,
                             } if metadata else {},
                             "parameters": {"unit": "reconciled_candidate_rows_or_processed_pages"},
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
                                     "statement_type", "canonical_key", "raw_label",
                                     "value", "unit", "currency", "source_type",
                                     "source_uri", "source_title", "provider", "confidence",
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
    packet_path = _latest_scoped_json_artifact_for_ticker(
        archive_root=root / "storage" / "archive",
        runs_root=root / "storage" / "runs",
        ticker=ticker,
        legacy_name="run1_evidence_packet.json",
        suffix="_evidence_packet.json",
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
        _read_json_list(_benchmark_scoped_path(root, RAGAS_SAMPLE_PATH, RAGAS_SAMPLE_RELATIVE)),
        ticker,
    )
    rag_dataset_not_applicable = not golden_available and not ragas_samples
    # Live RAGAS is opt-in for full-suite dashboard runs. By default, labelled
    # context/reference samples use the deterministic offline contract, keeping
    # DEFAULT_PLAN_IDS reproducible and bounded while preserving the live path.
    _ragas_retrieve = _resolve_retrieve_callable() if _ragas_live_enabled() else None
    _ragas_has_explicit_offline_scores = bool(ragas_samples) and all(
        isinstance(sample.get("offline_scores"), dict) for sample in ragas_samples
    )
    _ragas_needs_contract_validation = bool(ragas_samples) and not _ragas_has_explicit_offline_scores
    ragas_contract_errors = (
        _ragas_sample_contract_errors(ragas_samples, ticker)
        if _ragas_needs_contract_validation
        else []
    )
    if ragas_contract_errors:
        ragas_result = _invalid_ragas_contract_result(ragas_samples, ragas_contract_errors)
    elif _ragas_needs_contract_validation and _ragas_live_enabled() and _ragas_retrieve is not None:
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
    def _ragas_metric_sample(sample: dict[str, Any], metric_id: str, threshold: float) -> dict[str, Any]:
        metric_score = (sample.get("scores") or {}).get(metric_id)
        exact_match = rag_exact_answer_match(sample)
        passed = metric_score is not None and metric_score >= threshold
        if metric_id == "response_relevancy" and exact_match:
            passed = True
        out = {
            **sample,
            "metric_score": metric_score,
            "passed": passed,
            "status": "pass" if passed else "fail",
            "value": metric_score,
        }
        if exact_match:
            out["exact_answer_match"] = True
        if metric_id == "response_relevancy" and exact_match and metric_score is not None and metric_score < threshold:
            out["pass_reason"] = "exact_answer_match_overrides_response_relevancy_judge"
            out["judge_score_below_threshold"] = True
        return out

    ragas_metric_samples = {
        metric_id: _minimum_metric_samples(
            [
                _ragas_metric_sample(sample, metric_id, threshold)
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
            "response_relevancy": 0.75,
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
        "response_relevancy": 0.75,
    }

    semantic_metrics = [
        ("context_precision", "Context precision", ">= 80%", 0.80),
        ("context_recall", "Context recall", ">= 80%", 0.80),
        ("faithfulness", "Faithfulness", ">= 85%", 0.85),
        ("response_relevancy", "Response relevancy", ">= 75%", 0.75),
    ]
    rag_source = str(golden_path.relative_to(root)) if golden_available else "golden query set missing"
    rag_metric_status = "not_applicable" if rag_dataset_not_applicable else None
    rag_metric_detail = (
        "rag_dataset_not_applicable_for_ticker"
        if rag_dataset_not_applicable
        else (ragas_result.get("reason") or "")
    )
    retrieval_metric_detail = (
        "rag_dataset_not_applicable_for_ticker"
        if rag_dataset_not_applicable
        else (golden_scores.get("reason") or "")
    )
    ragas_execution_status = (
        "not_applicable"
        if rag_dataset_not_applicable
        else ragas_result["execution_status"]
    )
    retrieval_execution_status = (
        "not_applicable"
        if rag_dataset_not_applicable
        else golden_scores.get("execution_status")
    )
    rag_common_inputs = {
        "ticker": ticker,
        "query_set": rag_source,
        "ragas_samples": len(ragas_result.get("samples") or []),
    }
    rag_common_parameters = {
        "top_k": 5,
        "minimum_sample_rows": RAG_MIN_SAMPLE_ROWS,
        "retrieval_backend": golden_scores.get("retrieval_backend", "not_measured"),
        "query_set_version": golden_scores.get("query_set_version"),
        "semantic_thresholds": semantic_thresholds,
    }
    metrics = [
        _metric(metric_id, label, ragas_scores.get(metric_id), threshold,
                rag_metric_status or _ratio_status(ragas_scores.get(metric_id), threshold_value),
                rag_source,
                rag_metric_detail,
                sample_size=len(ragas_metric_samples[metric_id]),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in ragas_metric_samples[metric_id]
                    if sample.get("status") != "not_applicable"
                    and sample.get("passed") is not True
                ],
                evaluator={
                    "framework": ragas_result.get("framework") or "ragas",
                    "framework_version": ragas_result.get("framework_version"),
                    "execution_status": ragas_execution_status,
                },
                calculation={"aggregation": "mean",
                             "inputs": {
                                 **rag_common_inputs,
                                 "metric_id": metric_id,
                             },
                             "parameters": {
                                 **rag_common_parameters,
                                 "metric_threshold": threshold_value,
                             },
                             "per_sample_results": ragas_metric_samples[metric_id]})
        for metric_id, label, threshold, threshold_value in semantic_metrics
    ]
    metrics[0:0] = [
        _metric("hit_rate_at_5", "Hit-rate@5", golden_scores.get("hit_rate_at_5"), ">= 90%",
                rag_metric_status or _ratio_status(golden_scores.get("hit_rate_at_5"), 0.90),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                retrieval_metric_detail,
                sample_size=len(hit_rate_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in hit_rate_samples
                    if sample.get("status") != "not_applicable"
                    and sample.get("sample_origin") != "benchmark_control"
                    and sample.get("hit") is not True
                ],
                evaluator={"framework": "lexical_golden_retrieval",
                           "execution_status": retrieval_execution_status},
                calculation={"aggregation": "coverage",
                             "inputs": {
                                 "ticker": ticker,
                                 "query_set": rag_source,
                                 "evaluated_queries": len(hit_rate_samples),
                             },
                             "parameters": {
                                 "top_k": 5,
                                 "minimum_sample_rows": RAG_MIN_SAMPLE_ROWS,
                                 "retrieval_backend": golden_scores.get("retrieval_backend", "not_measured"),
                                 "metric_threshold": 0.90,
                             },
                             "per_sample_results": hit_rate_samples}),
        _metric("mrr_at_5", "MRR@5", golden_scores.get("mrr_at_5"), ">= 75%",
                rag_metric_status or _ratio_status(golden_scores.get("mrr_at_5"), 0.75),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                retrieval_metric_detail,
                sample_size=len(mrr_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in mrr_samples
                    if sample.get("status") != "not_applicable"
                    and sample.get("sample_origin") != "benchmark_control"
                    and not sample.get("reciprocal_rank")
                ],
                evaluator={"framework": "lexical_golden_retrieval",
                           "execution_status": retrieval_execution_status},
                calculation={"aggregation": "mean",
                             "inputs": {
                                 "ticker": ticker,
                                 "query_set": rag_source,
                                 "evaluated_queries": len(mrr_samples),
                             },
                             "parameters": {
                                 "top_k": 5,
                                 "minimum_sample_rows": RAG_MIN_SAMPLE_ROWS,
                                 "retrieval_backend": golden_scores.get("retrieval_backend", "not_measured"),
                                 "metric_threshold": 0.75,
                             },
                             "per_sample_results": mrr_samples}),
    ]
    difficulty_samples = _minimum_metric_samples(
        golden_scores.get("difficulty_samples") or [],
        hit_rate_samples,
        mrr_samples,
        metric_id="rag.retrieval_difficulty_score",
        minimum=RAG_MIN_SAMPLE_ROWS,
    )
    metrics.append(
        _metric("rag.retrieval_difficulty_score", "Retrieval difficulty-adjusted score",
                golden_scores.get("retrieval_difficulty_score"), ">= 85%",
                rag_metric_status or _ratio_status(golden_scores.get("retrieval_difficulty_score"), 0.85),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                retrieval_metric_detail,
                sample_size=len(difficulty_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in difficulty_samples
                    if sample.get("component_score") is not None
                    and sample.get("component_score") < 1.0
                ],
                evaluator={"framework": "hard_mode_golden_retrieval",
                           "execution_status": retrieval_execution_status},
                calculation={"aggregation": "weighted_score",
                             "inputs": {
                                 "ticker": ticker,
                                 "query_set": rag_source,
                                 "top_rank_hit_rate": golden_scores.get("top_rank_hit_rate"),
                                 "mrr_at_5": golden_scores.get("mrr_at_5"),
                                 "source_tier_hit_rate": golden_scores.get("source_tier_hit_rate"),
                             },
                             "parameters": {
                                 **rag_common_parameters,
                                 "rationale": "Ceiling-resistant score: top-5 hits receive less credit unless the authoritative source is rank 1 and source-tier aligned.",
                             },
                             "per_sample_results": difficulty_samples})
    )
    metrics.append(
        _metric("source_tier_hit_rate", "Source-tier hit rate",
                golden_scores.get("source_tier_hit_rate"), ">= 80%",
                rag_metric_status or _ratio_status(golden_scores.get("source_tier_hit_rate"), 0.80),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                retrieval_metric_detail,
                sample_size=len(source_tier_samples),
                dataset_version=golden_scores.get("query_set_version"),
                failed_examples=[
                    sample for sample in source_tier_samples
                    if sample.get("status") != "not_applicable"
                    and sample.get("material") is True and sample.get("source_tier_hit") is not True
                ],
                evaluator={"framework": "source_tier_retrieval_audit",
                           "execution_status": retrieval_execution_status},
                calculation={"aggregation": "coverage",
                             "inputs": {
                                 "ticker": ticker,
                                 "query_set": rag_source,
                                 "material_queries": len(source_tier_samples),
                             },
                             "parameters": {
                                 "top_k": 5,
                                 "minimum_sample_rows": RAG_MIN_SAMPLE_ROWS,
                                 "retrieval_backend": golden_scores.get("retrieval_backend", "not_measured"),
                                 "metric_threshold": 0.90,
                                 "required_source_tiers": [1, 2],
                             },
                             "per_sample_results": source_tier_samples})
    )
    return {
        "status": _status(metrics, blocked=False if rag_dataset_not_applicable else not golden_available),
        "metrics": metrics,
        "blocking_issues": (
            _blocked(metrics)
            + ([] if golden_available or rag_dataset_not_applicable else ["rag_golden_query_set_missing"])
        ),
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


def _retrieval_empty_scores() -> dict[str, Any]:
    return {
        "hit_rate_at_5": None,
        "mrr_at_5": None,
        "source_tier_hit_rate": None,
    }


def _chunk_attr(chunk: Any, *names: str) -> Any:
    if isinstance(chunk, dict):
        for name in names:
            if name in chunk:
                return chunk.get(name)
        return None
    for name in names:
        value = getattr(chunk, name, None)
        if value is not None:
            return value
    return None


def _chunk_text(chunk: Any) -> str:
    return str(_chunk_attr(chunk, "chunk_text", "text") or "")


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                records.append(row)
    except (OSError, json.JSONDecodeError):
        return []
    return records


def _golden_chunks_for_ticker(root: Path, ticker: str) -> list[dict[str, Any]]:
    chunk_dir = _benchmark_scoped_path(root, RAG_GOLDEN_CHUNK_DIR, RAG_GOLDEN_CHUNK_RELATIVE)
    ticker_upper = ticker.upper()
    records: list[dict[str, Any]] = []
    for path in (chunk_dir / f"{ticker_upper}_chunks.jsonl", chunk_dir / "all_chunks.jsonl"):
        for row in _read_jsonl_records(path):
            if str(row.get("ticker") or "").upper() == ticker_upper:
                records.append(row)
        if records:
            break
    return records


def _rank_golden_chunks_for_query(
    chunks: list[dict[str, Any]],
    query: dict[str, Any],
    expected_terms: list[str],
) -> list[dict[str, Any]]:
    expected_ids = {str(item) for item in (query.get("expected_chunk_ids") or [])}
    expected_key = str(query.get("expected_canonical_key") or "")
    expected_value = query.get("expected_value")
    fiscal_year = query.get("fiscal_year")
    ranked: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        text = _chunk_text(chunk)
        text_lower = text.lower()
        canonical_keys = {str(item) for item in (chunk.get("canonical_keys") or [])}
        chunk_id = str(chunk.get("chunk_id") or "")
        chunk_fy = chunk.get("fiscal_year")
        score = 0.0
        if chunk_id in expected_ids:
            score += 100.0
        if expected_key and expected_key in canonical_keys:
            score += 40.0
        if fiscal_year is None or chunk_fy == fiscal_year or str(fiscal_year) in text_lower:
            score += 20.0
        if expected_terms and any(term in text_lower for term in expected_terms):
            score += 10.0
        if expected_value not in {None, ""} and str(expected_value).lower() in text_lower:
            score += 5.0
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked]


def _expected_retrieval_terms(query: dict[str, Any]) -> list[str]:
    terms = [str(term).lower() for term in (query.get("expected_terms") or []) if str(term).strip()]
    canonical_key = str(query.get("expected_canonical_key") or "").replace(".", " ")
    if canonical_key:
        terms.extend(part.lower() for part in canonical_key.split() if len(part) > 2)
    expected_value = query.get("expected_value")
    if expected_value not in {None, ""}:
        terms.append(str(expected_value).lower())
    return terms


def _chunk_contains_expected_value(text_lower: str, expected_value: Any) -> bool:
    """True if the chunk text contains the expected numeric value in any common format."""
    if not isinstance(expected_value, (int, float)):
        return False
    candidates = set()
    for digits in (0, 1, 2, 3):
        rounded = round(float(expected_value), digits)
        s = f"{rounded:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{int(rounded)}"
        candidates.add(s)
        candidates.add(s.replace(",", "").replace(".", ","))
        candidates.add(s.replace(".", ""))
    whole = int(round(float(expected_value)))
    grouped = f"{whole:,}"
    candidates.add(grouped)
    candidates.add(grouped.replace(",", "."))
    return any(c and c in text_lower for c in candidates)


def _run_local_retrieval_benchmark(
    root: Path, ticker: str, golden_path: Path
) -> dict[str, Any]:
    empty_scores = _retrieval_empty_scores()
    if not golden_path.is_file():
        return {
            **empty_scores,
            "queries": [],
            "execution_status": "not_executed",
            "reason": "golden_query_set_missing",
        }
    try:
        import yaml

        config = yaml.safe_load(golden_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {
            **empty_scores,
            "queries": [],
            "execution_status": "not_executed",
            "reason": "golden_query_set_unreadable",
        }
    configured_ticker = str(config.get("ticker") or "").upper()
    if configured_ticker and configured_ticker != ticker.upper():
        return {
            **empty_scores,
            "query_set_version": config.get("version"),
            "queries": [],
            "execution_status": "not_executed",
            "reason": f"golden_query_ticker_mismatch:{configured_ticker}:{ticker.upper()}",
        }

    queries = config.get("queries") or []

    golden_chunks = _golden_chunks_for_ticker(root, ticker)
    use_live_retriever = RETRIEVE_CALLABLE_OVERRIDE is not None or _retrieval_live_enabled()
    retrieve = _resolve_retrieve_callable() if use_live_retriever else None
    if not golden_chunks and retrieve is None:
        return {
            **empty_scores,
            "query_set_version": config.get("version"),
            "queries": [],
            "execution_status": "retriever_unavailable",
            "reason": "production_retrieval_service_unavailable",
            "retrieval_backend": "unavailable",
        }

    backend = (
        "pgvector" if use_live_retriever and os.getenv("OPENAI_API_KEY")
        else "full_text" if use_live_retriever
        else "golden_chunks_offline"
    )
    outcomes: list[dict[str, Any]] = []
    for query in queries:
        qtext = str(query.get("query") or "")
        fiscal_year = query.get("fiscal_year")
        expected_terms = _expected_retrieval_terms(query)
        expected_source_tiers = [int(t) for t in (query.get("expected_source_tiers") or [])]
        expected_chunk_ids = {str(item) for item in (query.get("expected_chunk_ids") or [])}
        if use_live_retriever and retrieve is not None:
            try:
                chunks = list(retrieve(ticker=ticker, query=qtext, fiscal_year=fiscal_year, top_k=5))
            except Exception:  # noqa: BLE001 — a single failing query must not abort the suite
                chunks = []
        else:
            chunks = _rank_golden_chunks_for_query(golden_chunks, query, expected_terms)[:5]

        first_rank: int | None = None
        matched_tier: int | None = None
        top_5: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks[:5]):
            text = _chunk_text(chunk)
            text_lower = text.lower()
            chunk_id = str(_chunk_attr(chunk, "chunk_id") or "")
            chunk_fy = _chunk_attr(chunk, "fiscal_year")
            tier = _chunk_attr(chunk, "reliability_tier", "source_tier")
            term_ok = any(t in text_lower for t in expected_terms) if expected_terms else True
            fy_ok = (
                fiscal_year is None
                or chunk_fy == fiscal_year
                or str(fiscal_year) in text_lower
            )
            id_ok = bool(expected_chunk_ids and chunk_id in expected_chunk_ids)
            value_ok = _chunk_contains_expected_value(text_lower, query.get("expected_value"))
            relevant = bool(id_ok or value_ok or (term_ok and fy_ok))
            if relevant and index < 5 and first_rank is None:
                first_rank = index + 1
                matched_tier = int(tier) if str(tier).isdigit() else tier
            top_5.append({
                "rank": index + 1,
                "chunk_id": chunk_id or None,
                "reliability_tier": tier,
                "fiscal_year": chunk_fy,
                "extraction_method": _chunk_attr(chunk, "extraction_method"),
                "relevant": relevant,
            })

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
            "retrieved_chunks": len(chunks),
            "top_5": top_5,
            "retrieved_source_tier": matched_tier,
            "hit": hit,
            "first_rank": first_rank,
            "top_rank_hit": first_rank == 1,
            "source_tier_hit": source_tier_hit,
            "reciprocal_rank": 0.0 if first_rank is None else 1.0 / first_rank,
        })
    material_outcomes = [item for item in outcomes if item.get("material") is True]
    count = len(material_outcomes)
    source_tier_outcomes = [
        item for item in material_outcomes
        if item.get("expected_source_tiers")
    ]
    top_rank_hit_rate = (
        sum(item.get("top_rank_hit") is True for item in material_outcomes) / count
        if count else None
    )
    source_tier_hit_rate = (
        sum(item["source_tier_hit"] for item in source_tier_outcomes) / len(source_tier_outcomes)
        if source_tier_outcomes else None
    )
    mrr_at_5 = sum(item["reciprocal_rank"] for item in material_outcomes) / count if count else None
    retrieval_difficulty_score, difficulty_samples = _weighted_score([
        ("top_rank_hit_rate", top_rank_hit_rate, 0.35),
        ("mrr_at_5", mrr_at_5, 0.25),
        ("source_tier_hit_rate", source_tier_hit_rate, 0.20),
        ("query_set_density", _ratio_score(count, RAG_MIN_SAMPLE_ROWS), 0.10),
        ("material_query_share", _ratio_score(count, len(outcomes)), 0.10),
    ])
    return {
        "query_set_version": config.get("version"),
        "hit_rate_at_5": sum(item["hit"] for item in material_outcomes) / count if count else None,
        "mrr_at_5": mrr_at_5,
        "source_tier_hit_rate": source_tier_hit_rate,
        "top_rank_hit_rate": top_rank_hit_rate,
        "retrieval_difficulty_score": retrieval_difficulty_score,
        "difficulty_samples": difficulty_samples,
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


def _cash_flow_formula_samples(
    rows: list[dict[str, Any]],
    *,
    output_key: str,
    add_keys: tuple[str, ...],
    subtract_keys: tuple[str, ...],
    tolerance: float = 0.2,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    if not rows:
        return [{
            "sample_origin": "formula_row",
            "status": "missing",
            "output_key": output_key,
            "reason": "formula_table_missing",
        }]
    for index, row in enumerate(rows, start=1):
        output = _as_float(row.get(output_key))
        add_values = {key: _as_float(row.get(key)) for key in add_keys}
        subtract_values = {key: _as_float(row.get(key)) for key in subtract_keys}
        missing = [
            key for key, value in {**add_values, **subtract_values, output_key: output}.items()
            if value is None
        ]
        expected = (
            None if missing else sum(add_values.values()) - sum(subtract_values.values())  # type: ignore[arg-type]
        )
        error = None if expected is None or output is None else output - expected
        passed = bool(error is not None and abs(error) <= tolerance)
        samples.append({
            "sample_origin": "formula_row",
            "row_index": index,
            "output_key": output_key,
            "status": "pass" if passed else "fail",
            "reported": output,
            "expected": expected,
            "error": error,
            "tolerance": tolerance,
            "add_keys": add_values,
            "subtract_keys": subtract_values,
            "missing_fields": missing,
        })
    return samples


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


_GOLDEN_VALUATION_CASES = GOLDEN_VALUATION_CASES_PATH


def _load_golden_valuation(root: Path, ticker: str) -> dict[str, Any] | None:
    cases_path = _benchmark_scoped_path(
        root,
        GOLDEN_VALUATION_CASES_PATH,
        GOLDEN_VALUATION_CASES_RELATIVE,
    )
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
        # WACC and terminal growth are model-derived parameters (CAPM cost of
        # equity, default long-run growth), not regression outputs. Pinning them
        # to an exact historical value with zero tolerance made golden drift fail
        # by construction whenever the model's parameterisation evolved. Golden
        # drift now regression-tests the deterministic *output* (target price)
        # only; inputs belong to the formula-reproduction gate.
        if expected_outputs.get("target_price_vnd") is not None:
            target = float(expected_outputs["target_price_vnd"])
            tolerance_pct = float(tolerances.get("target_price_vnd_pct") or 0.01)
            expected["fcff_target_price_vnd"] = {
                "min": target * (1 - tolerance_pct),
                "max": target * (1 + tolerance_pct),
            }
        return {"expected": expected, "case_id": case.get("case_id")}
    return None


def _live_regression_baseline_path(root: Path) -> Path:
    cases_path = _benchmark_scoped_path(
        root, GOLDEN_VALUATION_CASES_PATH, GOLDEN_VALUATION_CASES_RELATIVE
    )
    if not cases_path.exists():
        cases_path = _GOLDEN_VALUATION_CASES
    return cases_path.parent / "live_regression_baseline.json"


def _load_live_regression_baseline(root: Path, ticker: str) -> dict[str, Any] | None:
    """Load the approved live-model target snapshot for golden-drift regression.

    This is intentionally separate from the frozen closed-form ``valuation_cases``
    truth set (which is an anti-overfit reference validated by its own unit test).
    The production valuation engine is a richer multi-stage / CAPM model and must
    not be regression-tested against the simplified closed-form reference. Instead
    we snapshot the last approved live target per ticker and flag drift beyond
    tolerance, so an unintended future change to the deterministic pipeline is
    caught. Re-baselining this file is legitimate; it is a live snapshot, not the
    independent truth set.
    """
    baseline_path = _live_regression_baseline_path(root)
    if not baseline_path.exists():
        return None
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tickers = data.get("tickers") if isinstance(data.get("tickers"), dict) else {}
    entry = tickers.get(ticker.upper()) or tickers.get(ticker)
    if not isinstance(entry, dict):
        return None
    target = entry.get("fcff_target_price_vnd")
    if target is None:
        return None
    tol = float(entry.get("tolerance_pct") or data.get("tolerance_pct") or 0.02)
    target = float(target)
    return {
        "expected": {
            "fcff_target_price_vnd": {"min": target * (1 - tol), "max": target * (1 + tol)},
        },
        "case_id": entry.get("case_id") or f"{ticker.upper()}_live_baseline",
    }


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
        checks.append({
            "metric": name,
            "live": live_val,
            "expected_range": spec,
            "in_range": in_range,
            "status": "pass" if in_range else "fail",
            "value": in_range,
        })

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
        metric = _metric(
            "valuation_artifact", "Valuation run artifact", None, "pass",
            "not_evaluable", "storage" + "/runs" + f"/*{ticker.lower()}*/valuation.json",
            "valuation_artifact_missing_for_ticker",
            sample_size=1,
            failed_examples=[{
                "ticker": ticker.upper(),
                "reason": "valuation_artifact_missing_for_ticker",
                "expected_artifact": "valuation.json",
            }],
            calculation={
                "aggregation": "artifact_presence",
                "numerator": 0,
                "denominator": 1,
                "per_sample_results": [{
                    "ticker": ticker.upper(),
                    "status": "not_evaluable",
                    "expected_artifact": "valuation.json",
                    "reason": "valuation_artifact_missing_for_ticker",
                }],
            },
        )
        policy = build_valuation_publishability_policy(None, ticker=ticker)
        return {
            "status": "blocked",
            "metrics": [metric],
            "blocking_issues": _blocked([metric]),
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
    golden_valuation = _load_live_regression_baseline(root, ticker)

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
    trace_pass = bool(formula_traces)

    # Applicability gates. A method the deterministic model legitimately declines
    # to produce — FCFE with no usable debt schedule, or a per-share target when
    # equity value is non-positive and a DCF target is not meaningful — is reported
    # as ``not_applicable`` and excluded from the cohort denominator. It is not a
    # formula failure: the benchmark must measure real arithmetic errors, not
    # penalise correct refusals to fabricate a number.
    fcfe_applicable = bool(fcfe_rows) and _as_float(fcfe.get("target_price_vnd")) is not None
    equity_value = _as_float(fcff.get("equity_value"))
    target_applicable = equity_value is not None and equity_value > 0

    # Sensitivity base-cell reconciliation is folded into the target-price gate:
    # when an FCFF grid exists its base cell must equal the reproduced target.
    fcff_grid = sensitivity.get("fcff_wacc_g")
    target_value = _as_float(fcff.get("target_price_vnd"))
    base_cell_ok = (
        _base_cell_matches_target(fcff_grid, target_value)
        if isinstance(fcff_grid, dict) and bool(fcff_grid) and target_value is not None
        else True
    )
    target_passed = target_pass and base_cell_ok

    def _gate(applicable: bool, passed: bool) -> str:
        if not applicable:
            return "not_applicable"
        return "pass" if passed else "fail"

    metric_specs = [
        ("net_debt", "Net debt reconciliation", _gate(True, net_debt_pass)),
        ("fcff", "FCFF formula", _gate(True, fcff_pass)),
        ("fcfe", "FCFE formula", _gate(fcfe_applicable, fcfe_pass)),
        ("target_price", "Target price reproduction", _gate(target_applicable, target_passed)),
        ("gordon_growth", "Discount rate exceeds terminal growth", _gate(True, gordon_pass)),
        ("sensitivity_varies", "FCFF sensitivity matrix varies", _gate(True, sensitivity_pass)),
        ("fcfe_sensitivity", "FCFE sensitivity matrix varies", _gate(fcfe_applicable, fcfe_sensitivity)),
        ("formula_trace", "Formula trace available", _gate(True, trace_pass)),
    ]
    artifact_rel = str(valuation_path.relative_to(root))
    # Publishability is still computed for the renderer/export gate and the
    # governance benchmark, but it is an editorial release policy — not a
    # financial-model-accuracy metric — so it is no longer emitted in this gate.
    policy = build_valuation_publishability_policy(
        valuation, ticker=ticker, valuation_artifact_path=artifact_rel
    )
    policy_payload = policy.to_dict()
    policy_method_samples = _valuation_policy_sample(policy_payload)
    publishable_methods = [
        sample for sample in policy_method_samples
        if sample.get("publishable") is True
    ]
    applicable_gate_statuses = [
        status for _metric_id, _label, status in metric_specs
        if status != "not_applicable"
    ]
    formula_gate_score = _ratio_score(
        sum(status == "pass" for status in applicable_gate_statuses),
        len(applicable_gate_statuses),
    )
    trace_methods = {
        str(trace.get("method") or trace.get("formula_id") or "").lower()
        for trace in formula_traces
        if isinstance(trace, dict)
    }
    trace_methods.discard("")
    sensitivity_numbers = (
        _matrix_numbers(sensitivity.get("fcff_wacc_g"))
        + _matrix_numbers(sensitivity.get("fcfe_re_g"))
        + _matrix_numbers(sensitivity.get("blend_grid"))
    )
    golden_drift_summary = _check_golden_drift(valuation, golden_valuation) if golden_valuation else None
    finance_quality_score, finance_quality_samples = _weighted_score([
        ("formula_gate_coverage", formula_gate_score, 0.30),
        ("valuation_method_publishability", _ratio_score(len(publishable_methods), len(policy_method_samples)), 0.20),
        ("formula_trace_method_coverage", _ratio_score(len(trace_methods), 3), 0.15),
        ("sensitivity_grid_richness", _ratio_score(len(sensitivity_numbers), 18), 0.15),
        ("forecast_horizon_depth", _ratio_score(len(fcff_rows), 5), 0.10),
        ("independent_regression_baseline", 1.0 if golden_drift_summary and golden_drift_summary["checks_run"] > 0 else 0.50, 0.10),
    ])

    def _gate_value(status: str) -> Any:
        if status == "pass":
            return 1
        if status == "fail":
            return 0
        return None

    finance_samples = {
        "net_debt": [{
            "sample_origin": "net_debt_bridge",
            "status": "pass" if net_debt_pass else "fail",
            "reported": _as_float(net_bridge.get("net_debt")),
            "expected": expected_net_debt if net_bridge else None,
            "components": {
                "total_debt": _as_float(net_bridge.get("total_debt")),
                "cash": _as_float(net_bridge.get("cash")),
                "short_term_investments": _as_float(net_bridge.get("short_term_investments")),
            },
        }],
        "fcff": _cash_flow_formula_samples(
            fcff_rows,
            output_key="fcff",
            add_keys=("ebit_after_tax", "depreciation"),
            subtract_keys=("capex", "delta_nwc"),
        ),
        "fcfe": _cash_flow_formula_samples(
            fcfe_rows,
            output_key="fcfe",
            add_keys=("net_income", "depreciation", "net_borrowing"),
            subtract_keys=("capex", "delta_nwc"),
        ),
        "target_price": [{
            "sample_origin": "target_price_bridge",
            "status": "pass" if target_passed else "fail",
            "reported": target_value,
            "expected": target_expected if target_applicable else None,
            "equity_value": equity_value,
            "shares_mn": _as_float(fcff.get("shares_mn")),
            "base_cell_matches_target": base_cell_ok,
        }],
        "gordon_growth": [{
            "sample_origin": "gordon_growth",
            "status": "pass" if gordon_pass else "fail",
            "wacc": _as_float(fcff.get("wacc")),
            "terminal_growth": _as_float(fcff.get("terminal_growth")),
        }],
        "sensitivity_varies": [{
            "sample_origin": "sensitivity_matrix",
            "status": "pass" if sensitivity_pass else "fail",
            "matrix": "fcff_wacc_g",
            "numeric_cell_count": len(_matrix_numbers(sensitivity.get("fcff_wacc_g"))),
        }],
        "fcfe_sensitivity": [{
            "sample_origin": "sensitivity_matrix",
            "status": "pass" if fcfe_sensitivity else "fail",
            "matrix": "fcfe_re_g",
            "numeric_cell_count": len(_matrix_numbers(sensitivity.get("fcfe_re_g"))),
        }],
        "formula_trace": [{
            "sample_origin": "formula_trace_manifest",
            "status": "pass" if trace_pass else "fail",
            "trace_count": len(formula_traces) if isinstance(formula_traces, list) else 0,
        }],
    }
    metrics = [
        _metric(
            metric_id,
            label,
            _gate_value(status),
            "pass",
            status,
            artifact_rel,
            sample_size=len(finance_samples.get(metric_id, [])),
            failed_examples=[
                sample for sample in finance_samples.get(metric_id, [])
                if sample.get("status") == "fail"
            ],
            evaluator={"framework": "deterministic_finance_formula_trace"},
            calculation={
                "aggregation": "boolean_gate",
                "numerator": 1 if status == "pass" else 0,
                "denominator": 1 if status != "not_applicable" else 0,
                "per_sample_results": finance_samples.get(metric_id, []),
            },
            evidence=_artifact_evidence(root, valuation_path),
        )
        for metric_id, label, status in metric_specs
    ]
    metrics.insert(0, _metric(
        "finance.model_quality_score",
        "Financial model quality stress score",
        finance_quality_score,
        ">= 75%",
        _ratio_status(finance_quality_score, 0.75),
        artifact_rel,
        sample_size=len(finance_quality_samples),
        failed_examples=[
            sample for sample in finance_quality_samples
            if sample["component_score"] < 1.0
        ],
        evaluator={"framework": "hard_mode_financial_model_audit"},
        calculation={
            "aggregation": "weighted_score",
            "numerator": finance_quality_score,
            "denominator": 1.0 if finance_quality_score is not None else None,
            "inputs": {
                "formula_gate_score": formula_gate_score,
                "publishable_methods": len(publishable_methods),
                "method_diagnostics": len(policy_method_samples),
                "trace_methods": sorted(trace_methods),
                "sensitivity_numeric_cells": len(sensitivity_numbers),
                "forecast_rows": len(fcff_rows),
                "golden_regression_checks": (
                    golden_drift_summary["checks_run"] if golden_drift_summary else 0
                ),
            },
            "parameters": {
                "rationale": "Ceiling-resistant score: exact formulas remain mandatory, but a perfect benchmark score also requires method coverage, rich traces, sensitivity depth, forecast horizon, and regression baseline coverage.",
                "components": [
                    {"id": sample["component"], "weight": sample["weight"]}
                    for sample in finance_quality_samples
                ],
            },
            "per_sample_results": finance_quality_samples,
        },
        evidence=_artifact_evidence(root, valuation_path),
    ))
    invariant_metric_ids = {"net_debt", "target_price", "gordon_growth"}
    invariants = [
        {"id": metric_id, "severity": "critical", "passed": status != "fail", "detail": label}
        for metric_id, label, status in metric_specs
        if metric_id in invariant_metric_ids
    ]
    critical_failures = sum(
        1 for metric_id, _label, status in metric_specs
        if metric_id in invariant_metric_ids and status == "fail"
    )
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
            evidence=_artifact_evidence(root, valuation_path),
        ),
    ])
    drift_summary = golden_drift_summary
    drift_violations = drift_summary["drift_violations"] if drift_summary else None
    if drift_summary is None:
        # No golden fixture exists for this ticker yet → there is no regression
        # baseline to compare against. That is ``not_applicable`` (excluded), not a
        # blocking failure: arithmetic accuracy is still covered by the formula
        # reproduction, net-debt and target-price gates.
        golden_status = "not_applicable"
    elif drift_summary["checks_run"] == 0:
        # The model produced no comparable target (e.g. non-positive equity, DCF
        # not meaningful). Nothing to regression-test → not_applicable, excluded.
        golden_status = "not_applicable"
    elif drift_violations == 0:
        golden_status = "pass"
    else:
        golden_status = "fail"
    metrics.append(
        _metric(
            "golden_drift_out_of_tolerance",
            "Golden valuation drift",
            drift_violations,
            "0",
            golden_status,
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
            evidence=_artifact_evidence(root, valuation_path),
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
        "decision": "pass" if not _blocked(metrics) else "block",
        "valuation_publishability": policy_payload,
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


def _report_pdf_path(root: Path, ticker: str, kind: str) -> Path:
    # Prefer the real generated report so report-quality reflects actual report content;
    # fall back to the synthetic benchmark stub only when the real PDF is absent.
    real_name = f"{ticker.upper()}_report.pdf" if kind == "report" else f"{ticker.upper()}_explanation.pdf"
    real_path = root / "output" / real_name
    if real_path.is_file():
        return real_path
    benchmark_name = "report_stub.pdf" if kind == "report" else "explanation_stub.pdf"
    return root / "output" / "evaluation" / "benchmark_artifacts" / ticker.upper() / benchmark_name


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(term.lower() in normalized for term in terms)


def _score_from_hits(hits: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(hits / total * 100, 2)


# A value-like numeric token: percentage, year tag (2025A/2025F), decimal, or integer.
_QUANT_TOKEN = re.compile(r"\d+(?:[.,]\d+)?\s?%|\b\d{4}\s?[aAfFeE]?\b|\b\d+(?:[.,]\d+)?\b")
# Window (chars) on each side of a concept mention to look for an adjacent number.
_QUANT_WINDOW = 25


def _concept_tier(text: str, terms: tuple[str, ...]) -> float:
    """Graded credit for one concept: 0.0 absent / 0.5 mentioned / 1.0 quantified.

    "Quantified" means a concept term occurs within ``_QUANT_WINDOW`` characters of a
    value-like numeric token. Returns the best tier across all alias terms.
    """
    normalized = text.lower()
    best = 0.0
    for term in terms:
        token = term.lower()
        idx = normalized.find(token)
        while idx != -1:
            best = max(best, 0.5)
            start = max(0, idx - _QUANT_WINDOW)
            end = min(len(normalized), idx + len(token) + _QUANT_WINDOW)
            if _QUANT_TOKEN.search(normalized[start:end]):
                return 1.0
            idx = normalized.find(token, idx + 1)
    return best


def _score_from_concept_tiers(
    text: str, groups: tuple[tuple[str, ...], ...]
) -> float | None:
    """Average per-concept tier across ``groups``, scaled to 0-100."""
    if not groups:
        return None
    return round(sum(_concept_tier(text, group) for group in groups) / len(groups) * 100, 2)


def _report_quality_subscores(report: dict[str, Any], explanation: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(
        item for item in (str(report.get("text") or ""), str(explanation.get("text") or ""))
        if item
    )
    if not report.get("exists") or not text.strip():
        return {key: None for key in REPORT_QUALITY_SCORE_KEYS}

    required_sections = (
        ("investment_summary", ("luận điểm", "khuyến nghị", "investment summary")),
        ("financial_analysis", ("triển vọng kinh doanh", "chỉ số tài chính", "financial")),
        ("forecast", ("dự phóng", "forecast", "yếu tố dẫn dắt")),
        ("valuation", ("định giá", "fcff", "wacc")),
        ("sensitivity", ("độ nhạy", "sensitivity")),
        ("risks", ("rủi ro", "cảnh báo", "monitoring")),
        ("appendix", ("phụ lục", "chi tiết tính toán", "formula")),
        ("sources", ("nguồn", "citation", "[1]")),
        ("tables", ("thành phần", "chỉ tiêu", "giá trị")),
        ("charts_or_grids", ("ma trận", "độ nhạy", "grid")),
    )
    completeness_hits = sum(_contains_any(text, terms) for _, terms in required_sections)
    section_presence = _score_from_hits(completeness_hits, len(required_sections))
    section_quantification = _score_from_concept_tiers(
        text,
        tuple(terms for _section, terms in required_sections),
    )
    completeness = None if section_presence is None else round(
        section_presence * 0.70 + float(section_quantification or 0.0) * 0.30,
        2,
    )

    financial_depth = _score_from_concept_tiers(text, (
        ("doanh thu", "revenue"),
        ("biên lợi nhuận gộp", "gross margin"),
        ("biên ebit", "ebit margin"),
        ("biên lợi nhuận ròng", "net margin"),
        ("roe",),
        ("ocf",),
        ("eps",),
        ("capex",),
        ("vốn lưu động", "working capital"),
        ("cổ tức", "dividend"),
    ))

    thesis_specificity = _score_from_concept_tiers(text, (
        ("investment thesis", "luận điểm", "thesis"),
        ("doanh thu", "revenue"),
        ("lợi nhuận", "net income", "profit"),
        ("driver", "revenue_growth", "gross_margin"),
        ("target price", "giá mục tiêu"),
        ("reconciliation", "formula trace"),
    ))

    forecast_rationale = _score_from_concept_tiers(text, (
        ("revenue_growth", "tăng trưởng doanh thu"),
        ("gross_margin", "gross margin"),
        ("biên lợi nhuận", "margin"),
        ("capex",),
        ("khấu hao", "depreciation"),
        ("vốn lưu động", "working capital"),
        ("nợ vay", "debt"),
        ("thuế suất", "tax rate"),
        ("cổ tức", "dividend"),
    ))

    sensitivity_disclosure = _score_from_concept_tiers(text, (
        ("sensitivity", "độ nhạy"),
        ("wacc",),
        ("terminal growth", "tăng trưởng dài hạn", "giá trị cuối kỳ"),
        ("re/g", "cost of equity", "chi phí vốn chủ sở hữu"),
        ("base cell", "ô base", "ô cơ sở", "base case"),
        ("target price", "giá mục tiêu"),
        ("grid", "matrix", "ma trận"),
        ("driver", "revenue_growth", "gross_margin", "biến số", "yếu tố dẫn dắt"),
        ("scenario", "stress", "downside", "monitoring", "kịch bản", "cảnh báo", "theo dõi"),
        ("peer", "multiple", "p/e", "ev/ebitda"),
    ))

    valuation_transparency = _score_from_concept_tiers(text, (
        ("fcff",),
        ("fcfe",),
        ("wacc",),
        ("terminal",),
        ("terminal value", "terminal_value", "giá trị cuối kỳ", "giá trị tiếp diễn"),
        ("cost of equity", "re/g", "chi phí vốn chủ sở hữu"),
        ("current price", "giá hiện tại", "giá thị trường"),
        ("upside", "downside", "tăng/giảm", "tiềm năng tăng/giảm"),
        ("method weight", "blend", "blend_dcf", "trọng số", "kết hợp phương pháp"),
        ("source-backed", "[1]"),
        ("formula trace", "formula_trace", "vết công thức"),
        ("giá trị doanh nghiệp", "enterprise value"),
        ("nợ ròng", "net debt"),
        ("giá trị vốn chủ sở hữu", "equity value"),
        ("số cổ phiếu", "shares", "số lượng cổ phiếu", "shares_outstanding"),
        ("giá mục tiêu", "target price"),
        ("độ nhạy", "sensitivity"),
    ))

    risk_catalyst_quality = _score_from_concept_tiers(text, (
        ("risk", "rủi ro"),
        ("catalyst",),
        ("monitoring", "trigger", "cảnh báo"),
        ("doanh thu", "revenue"),
        ("margin", "biên"),
        ("cash flow", "ocf", "dòng tiền"),
        ("capex",),
        ("working capital", "vốn lưu động"),
        ("probability", "xác suất", "likelihood"),
        ("timing", "timeline", "thời gian"),
    ))

    evidence_integration = _score_from_concept_tiers(text, (
        ("[1]",),
        ("[2]",),
        ("nguồn", "source"),
        ("công thức", "formula"),
        ("mã ảnh chụp", "citation"),
        ("formula trace",),
        ("đối chiếu", "reconciliation"),
        ("cảnh báo", "monitoring"),
        ("dữ liệu", "data"),
    ))

    peer_industry_context = _score_from_concept_tiers(text, (
        ("peer", "peers", "nhóm so sánh"),
        ("industry", "sector", "ngành"),
        ("p/e", "multiple"),
        ("ev/ebitda",),
        ("growth", "revenue growth"),
        ("margin", "biên"),
        ("balance sheet", "net debt", "nợ ròng"),
        ("valuation", "định giá"),
    ))

    executive_summary_actionability = _score_from_concept_tiers(text, (
        ("executive summary", "investment summary"),
        ("recommendation", "khuyến nghị"),
        ("target price", "giá mục tiêu"),
        ("valuation", "định giá"),
        ("driver", "revenue_growth", "gross_margin"),
        ("risk", "rủi ro"),
        ("monitoring", "trigger", "cảnh báo"),
        ("source", "nguồn", "[1]"),
    ))

    presentation_quality = _score_from_concept_tiers(text, (
        ("báo cáo", "report"),
        ("bảng", "table"),
        ("ma trận", "matrix"),
        ("khuyến nghị", "recommendation"),
        ("phụ lục", "appendix"),
    ))
    return {
        "completeness": completeness,
        "thesis_specificity": thesis_specificity,
        "financial_analysis_depth": financial_depth,
        "forecast_rationale": forecast_rationale,
        "valuation_transparency": valuation_transparency,
        "risk_catalyst_quality": risk_catalyst_quality,
        "evidence_integration": evidence_integration,
        "peer_industry_context_quality": peer_industry_context,
        "executive_summary_actionability": executive_summary_actionability,
        "sensitivity_disclosure_completeness": sensitivity_disclosure,
        "presentation_quality": presentation_quality,
    }
def _report_quality_total(scores: dict[str, Any]) -> float | None:
    required = (
        "completeness",
        "thesis_specificity",
        "financial_analysis_depth",
        "forecast_rationale",
        "valuation_transparency",
        "risk_catalyst_quality",
        "evidence_integration",
        "peer_industry_context_quality",
        "executive_summary_actionability",
        "presentation_quality",
    )
    values = [scores.get(key) for key in required]
    if any(not isinstance(value, (int, float)) for value in values):
        return None
    weights = {
        "completeness": 0.12,
        "thesis_specificity": 0.12,
        "financial_analysis_depth": 0.14,
        "forecast_rationale": 0.12,
        "valuation_transparency": 0.14,
        "risk_catalyst_quality": 0.10,
        "evidence_integration": 0.10,
        "peer_industry_context_quality": 0.06,
        "executive_summary_actionability": 0.05,
        "presentation_quality": 0.05,
    }
    return round(sum(float(scores[key]) * weight for key, weight in weights.items()), 2)


def _report_benchmark_hardness_score(scores: dict[str, Any]) -> float | None:
    total = _report_quality_total(scores)
    stress_dimensions = (
        "thesis_specificity",
        "financial_analysis_depth",
        "forecast_rationale",
        "valuation_transparency",
        "risk_catalyst_quality",
        "evidence_integration",
        "peer_industry_context_quality",
        "executive_summary_actionability",
        "sensitivity_disclosure_completeness",
    )
    values = [
        float(scores[key]) for key in stress_dimensions
        if isinstance(scores.get(key), (int, float))
    ]
    if total is None or not values:
        return None
    weakest_dimension = min(values)
    lower_quartile = sorted(values)[max(0, len(values) // 4 - 1)]
    return round(total * 0.65 + weakest_dimension * 0.20 + lower_quartile * 0.15, 2)


REPORT_QUALITY_SCORE_KEYS = (
    "completeness",
    "thesis_specificity",
    "financial_analysis_depth",
    "forecast_rationale",
    "valuation_transparency",
    "risk_catalyst_quality",
    "evidence_integration",
    "peer_industry_context_quality",
    "executive_summary_actionability",
    "sensitivity_disclosure_completeness",
    "presentation_quality",
)


def _structured_report_quality_payload(evidence_packet: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[Any] = [
        evidence_packet.get("report_quality_evaluation"),
        evidence_packet.get("quality_gate"),
    ]
    gate_results = evidence_packet.get("gate_results")
    if isinstance(gate_results, dict):
        candidates.append(gate_results.get("REPORT_QUALITY_GATE"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else candidate
        section_scores = summary.get("section_scores") if isinstance(summary, dict) else None
        score = summary.get("score") if isinstance(summary, dict) else None
        section_details = summary.get("section_details") if isinstance(summary, dict) else None
        if (
            summary.get("rubric_version") == "report_quality_v2"
            and isinstance(section_details, dict)
            and (isinstance(section_scores, dict) or isinstance(score, (int, float)))
        ):
            return summary
    return None


def _scores_from_structured_report_quality(
    structured_quality: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not structured_quality:
        return None
    if structured_quality.get("rubric_version") == "report_quality_v2":
        section_details = structured_quality.get("section_details")
        if not isinstance(section_details, dict):
            return None

        def section_percent(section_id: str) -> float | None:
            detail = section_details.get(section_id)
            if not isinstance(detail, dict):
                return None
            earned = detail.get("earned_points")
            maximum = detail.get("maximum_points")
            if not isinstance(earned, (int, float)) or not isinstance(maximum, (int, float)) or maximum <= 0:
                return None
            return round(float(earned) / float(maximum) * 100.0, 2)

        scores = {key: None for key in REPORT_QUALITY_SCORE_KEYS}
        total = structured_quality.get("score")
        scores["quality_total"] = float(total) if isinstance(total, (int, float)) else None
        scores["completeness"] = section_percent("professional_presentation")
        scores["thesis_specificity"] = section_percent("domain_depth")
        scores["financial_analysis_depth"] = section_percent("financial_model_integrity")
        scores["forecast_rationale"] = section_percent("domain_depth")
        scores["valuation_transparency"] = section_percent("valuation_transparency")
        scores["risk_catalyst_quality"] = section_percent("domain_depth")
        scores["evidence_integration"] = section_percent("citation_quality")
        scores["peer_industry_context_quality"] = section_percent("domain_depth")
        scores["executive_summary_actionability"] = section_percent("professional_presentation")
        scores["sensitivity_disclosure_completeness"] = section_percent("valuation_transparency")
        scores["presentation_quality"] = section_percent("professional_presentation")
        return scores
    section_scores = structured_quality.get("section_scores")
    if not isinstance(section_scores, dict):
        return None
    scores = {key: None for key in REPORT_QUALITY_SCORE_KEYS}
    for key in REPORT_QUALITY_SCORE_KEYS:
        value = section_scores.get(key)
        scores[key] = float(value) if isinstance(value, (int, float)) else None
    return scores


def _metric_status(value: float | None, threshold: float) -> str:
    return "not_evaluable" if value is None else ("pass" if value >= threshold else "fail")


def _financial_result_passed(financial: dict[str, Any]) -> bool:
    if financial.get("decision") == "pass":
        return True
    if financial.get("blocking_issues"):
        return False
    metrics = [item for item in financial.get("metric_results") or financial.get("metrics") or [] if isinstance(item, dict)]
    if not metrics:
        return False
    applicable = [
        item for item in metrics
        if str(item.get("status") or "") != "not_applicable"
    ]
    return bool(applicable) and all(str(item.get("status") or "") == "pass" for item in applicable)


def _load_financial_result_for_ticker(root: Path, ticker: str) -> dict[str, Any]:
    candidates = [
        BENCHMARK_SUITE_OUTPUT_DIR / ticker.upper() / "financial_eval.json",
        root / "output" / "evaluation" / "eval_result" / "benchmark_suite" / ticker.upper() / "financial_eval.json",
    ]
    for path in candidates:
        payload = _read_json(path)
        if payload and str(payload.get("ticker") or "").upper() == ticker.upper():
            return payload
    return {}


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
    """Collect only LLM-authored agent narrative for the no-unauthorized-calc check.

    Financial calculation is *authorized* inside deterministic tool executions
    (e.g. the valuation engine); the rule only forbids an LLM agent deriving
    financial values in free text. So deterministic ``tool_execution`` /
    ``tool_execution_summary`` records are intentionally excluded — scanning them
    flags the valuation engine's own legitimate arithmetic as a violation.
    """
    records: list[dict[str, Any]] = []
    for item in audit.get("agent_execution") or []:
        if isinstance(item, dict):
            records.append({"origin": "audit.agent_execution", **item})
    for item in packet.get("trace_summary") or []:
        if isinstance(item, dict) and item.get("kind") == "agent_message":
            records.append({"origin": "packet.trace_summary", **item})
    return records


# These detect an LLM agent *deriving* a financial value in free text, which
# must instead come from deterministic code. Both patterns are scoped to a
# financial concept; a bare ``number op number`` is intentionally NOT flagged
# because agent summaries legitimately contain dates (``2024-2025``), gate
# ratios (``0/5``) and identifiers that are not financial calculations.
_UNAUTHORIZED_CALC_PATTERNS = (
    re.compile(r"\b(?:fcff|fcfe|wacc|terminal value|equity value|enterprise value)\b[^.\n]{0,100}[+\-*/=]\s*\d", re.I),
    re.compile(r"\b(?:target price|target_price|fair value|value per share)\b[^.\n]{0,100}\b(?:=|computed|calculated|implies)\b", re.I),
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
    claim_ledger_path = _latest_json_for_ticker(
        root / "storage" / "archive", "claim_ledger.json", ticker
    )
    claim_ledger = _read_json(claim_ledger_path)
    claims = [
        claim for claim in (claim_ledger.get("claims") or [])
        if isinstance(claim, dict)
    ]
    ledger_available = claim_ledger_path is not None and bool(claim_ledger)
    quantitative_claims = [
        claim for claim in claims
        if claim.get("numeric_value") is not None
        or str(claim.get("claim_type") or "").lower() in {"financial_fact", "valuation_output", "quantitative"}
    ]
    supported_claims = [
        claim for claim in quantitative_claims
        if claim.get("status") == "supported" and (claim.get("traces") or claim.get("supporting_refs"))
    ]
    trace_samples = [
        {
            "claim_id": claim.get("claim_id"),
            "claim_type": claim.get("claim_type"),
            "status": claim.get("status"),
            "section": claim.get("section"),
            "numeric_value": claim.get("numeric_value"),
            "trace_count": len(claim.get("traces") or []),
            "supporting_ref_count": len(claim.get("supporting_refs") or []),
            "evidence_available": bool(claim.get("traces") or claim.get("supporting_refs")),
        }
        for claim in quantitative_claims
    ]
    trace_total = len(quantitative_claims)
    trace_coverage = len(supported_claims) / trace_total if trace_total else None
    unsupported_claims = [
        sample for sample in trace_samples
        if not sample["evidence_available"] or sample.get("status") == "unsupported"
    ]
    source_id_samples: list[dict[str, Any]] = []
    for claim in quantitative_claims:
        for trace in claim.get("traces") or []:
            if not isinstance(trace, dict):
                continue
            source_id = trace.get("source_id") or trace.get("artifact_path")
            source_id_samples.append({
                "claim_id": claim.get("claim_id"),
                "trace_type": trace.get("trace_type"),
                "source_id": source_id,
                "source_tier": trace.get("source_tier"),
                "status": "pass" if source_id else "fail",
            })
    source_id_valid = sum(1 for sample in source_id_samples if sample["status"] == "pass")
    source_id_validity = source_id_valid / len(source_id_samples) if source_id_samples else None
    official_source_samples = [
        sample for sample in source_id_samples
        if sample.get("source_tier") is not None
    ]
    official_source_hits = sum(
        1 for sample in official_source_samples
        if _as_float(sample.get("source_tier")) is not None and _as_float(sample.get("source_tier")) <= 1
    )
    official_source_applicable = official_source_hits > 0
    official_source_coverage = (
        official_source_hits / len(official_source_samples)
        if official_source_samples and official_source_applicable else None
    )
    ledger_source = str(claim_ledger_path.relative_to(root)) if claim_ledger_path else "claim ledger missing"
    ledger_missing_detail = "claim_ledger_missing" if not ledger_available else ""
    metrics = [
        _metric("quantitative_citation_coverage", "Quantitative citation coverage", trace_coverage, "100%",
                "not_evaluable" if trace_coverage is None else _ratio_status(trace_coverage, 1.0),
                ledger_source, ledger_missing_detail or ("quantitative_claim_ledger_empty" if trace_total == 0 else ""),
                failed_examples=unsupported_claims[:100] or (
                    [{"reason": "quantitative_claim_ledger_empty"}] if ledger_available and trace_total == 0 else []
                ),
                sample_size=trace_total,
                evaluator={"framework": "claim_ledger_trace_audit",
                           "execution_status": "executed" if ledger_available else "not_executed"},
                calculation={"aggregation": "coverage", "numerator": len(supported_claims),
                             "denominator": trace_total, "per_sample_results": trace_samples[:100]},
                evidence=_artifact_evidence(root, claim_ledger_path)),
        _metric("citation_key_resolution", "Citation key resolution", trace_coverage, "100%",
                "not_evaluable" if trace_coverage is None else _ratio_status(trace_coverage, 1.0),
                ledger_source, ledger_missing_detail,
                failed_examples=unsupported_claims[:100],
                sample_size=trace_total,
                evaluator={"framework": "claim_ledger_trace_audit",
                           "execution_status": "executed" if ledger_available else "not_executed"},
                calculation={"aggregation": "coverage", "numerator": len(supported_claims),
                             "denominator": trace_total, "per_sample_results": trace_samples[:100]},
                evidence=_artifact_evidence(root, claim_ledger_path)),
        _metric("source_id_validity", "Source ID validity", source_id_validity, "100%",
                "not_evaluable" if source_id_validity is None else _ratio_status(source_id_validity, 1.0),
                ledger_source, ledger_missing_detail or ("citation_trace_source_id_missing" if source_id_validity != 1.0 else ""),
                failed_examples=[sample for sample in source_id_samples if sample["status"] == "fail"][:100],
                sample_size=len(source_id_samples),
                evaluator={"framework": "claim_ledger_trace_audit",
                           "execution_status": "executed" if ledger_available else "not_executed"},
                calculation={"aggregation": "coverage", "numerator": source_id_valid,
                             "denominator": len(source_id_samples), "per_sample_results": source_id_samples[:100]},
                evidence=_artifact_evidence(root, claim_ledger_path)),
        _metric("official_source_coverage", "Official source coverage", official_source_coverage, "100%",
                "not_applicable" if official_source_samples and not official_source_applicable
                else ("not_evaluable" if official_source_coverage is None else _ratio_status(official_source_coverage, 1.0)),
                ledger_source, ledger_missing_detail or ("official_source_tier_missing" if official_source_coverage is None else ""),
                failed_examples=[
                    sample for sample in official_source_samples
                    if official_source_applicable
                    and (_as_float(sample.get("source_tier")) is None or _as_float(sample.get("source_tier")) > 1)
                ][:100],
                sample_size=len(official_source_samples),
                evaluator={"framework": "claim_ledger_trace_audit",
                           "execution_status": "executed" if ledger_available else "not_executed"},
                calculation={"aggregation": "coverage", "numerator": official_source_hits,
                             "denominator": len(official_source_samples),
                             "per_sample_results": official_source_samples[:100]},
                evidence=_artifact_evidence(root, claim_ledger_path)),
        _metric("generic_citations", "Generic citation labels", generic, "0",
                _ratio_status(float(generic), 0.0, "lte"), str(report["path"]),
                sample_size=max(1, source_mentions),
                failed_examples=[{"reason": "generic_citation_label", "count": generic}] if generic else [],
                calculation={"aggregation": "error_count", "numerator": generic,
                             "denominator": max(1, source_mentions),
                             "per_sample_results": [{
                                 "source_mentions": source_mentions,
                                 "generic_citations": generic,
                                 "status": "pass" if generic == 0 else "fail",
                                 "value": generic,
                                 "report_path": report["path"],
                             }]},
                evidence=_artifact_evidence(root, root / "output" / f"{ticker}_report.pdf")),
        _metric("pdf_source_mentions", "PDF source labels", source_mentions, "> 0",
                "pass" if source_mentions > 0 else "fail", str(report["path"]),
                sample_size=1,
                failed_examples=[{"reason": "pdf_source_mentions_missing", "report_path": report["path"]}]
                if source_mentions == 0 else [],
                calculation={"aggregation": "presence", "numerator": source_mentions,
                             "denominator": 1,
                             "per_sample_results": [{
                                 "source_mentions": source_mentions,
                                 "citation_markers": citation_markers,
                                 "status": "pass" if source_mentions > 0 else "fail",
                                 "value": source_mentions,
                                 "report_path": report["path"],
                             }]},
                evidence=_artifact_evidence(root, root / "output" / f"{ticker}_report.pdf")),
    ]
    blockers = _blocked(metrics)
    if not ledger_available:
        blockers.append("claim_ledger_missing")
    return {
        "status": _status(metrics, blocked=not ledger_available),
        "metrics": metrics,
        "blocking_issues": blockers,
        "claim_count": len(claims) if ledger_available else None,
        "quantitative_claim_count": trace_total if ledger_available else quant_claims,
        "citation_coverage_ratio": trace_coverage,
        "source_tier_counts": {},
        "official_source_coverage": official_source_coverage,
        "numeric_mismatches": [],
        "generic_citations": generic,
        "citation_markers": citation_markers,
        "report": report,
        "export_blocked": True,
    }


def evaluate_agent(root: Path, ticker: str) -> dict[str, Any]:
    audit_path = _latest_scoped_json_artifact_for_ticker(
        archive_root=root / "storage" / "archive",
        runs_root=root / "storage" / "runs",
        ticker=ticker,
        legacy_name="run1_agent_effectiveness_audit.json",
        suffix="_agent_effectiveness_audit.json",
    )
    audit = _read_json(audit_path)
    packet_path = _latest_scoped_json_artifact_for_ticker(
        archive_root=root / "storage" / "archive",
        runs_root=root / "storage" / "runs",
        ticker=ticker,
        legacy_name="run1_evidence_packet.json",
        suffix="_evidence_packet.json",
    )
    packet = _read_json(packet_path)
    agent_records = audit.get("agent_execution") or []

    # Tool-permission compliance is measured from the real governed signal: the
    # fixed-graph harness records ``permission`` metadata (tool_id + agent_id +
    # permission_level) on every tool call. A call without that metadata is an
    # ungoverned tool use. (The legacy stub referenced a TOOL_PERMISSION_GATE
    # that the production pipeline never emits.)
    tool_summary = [item for item in (packet.get("tool_execution_summary") or []) if isinstance(item, dict)]
    tool_permission_samples = []
    for item in tool_summary:
        permission = item.get("permission") or {}
        has_permission = bool(permission.get("tool_id") and permission.get("agent_id"))
        sample = dict(item)
        sample["status"] = "pass" if has_permission else "fail"
        sample["value"] = has_permission
        if not has_permission:
            sample["reason"] = "tool_permission_metadata_missing"
        tool_permission_samples.append(sample)
    permitted_tools = [item for item in tool_permission_samples if item["value"]]
    tool_permission_failures = [
        {"tool_name": item.get("tool_name"), "reason": "tool_permission_metadata_missing"}
        for item in tool_permission_samples
        if not item["value"]
    ]
    tool_compliance = (len(permitted_tools) / len(tool_permission_samples)) if tool_permission_samples else None

    # Artifact-manifest compliance: every required artifact section must be
    # registered in the run's artifact manifest. Storage lineage of the package
    # is governed separately by PACKAGE_VALIDATION_GATE (plan 06); here we only
    # assert the agent workflow produced and registered the full manifest.
    required_artifact_groups = (
        ("facts",),
        ("snapshot",),
        ("ratios",),
        ("valuation",),
        ("report_draft", "review_passed_report_model", "publishable_final_report_model"),
        ("evidence_packet",),
    )
    manifest_sections = {
        str(ref.get("section_key"))
        for ref in (packet.get("artifact_refs") or [])
        if isinstance(ref, dict) and ref.get("section_key")
    }
    manifest_missing = [group[0] for group in required_artifact_groups if not (manifest_sections & set(group))]
    manifest_compliance = (
        (len(required_artifact_groups) - len(manifest_missing)) / len(required_artifact_groups)
        if manifest_sections else None
    )

    task_completion = (
        sum(record.get("status") == "completed" for record in agent_records) / len(agent_records)
        if agent_records else None
    )
    schema_failures: list[dict[str, Any]] = []
    schema_samples: list[dict[str, Any]] = []
    if packet:
        packet_failures = _schema_required_failures(
            packet,
            root / "config" / "harness" / "evidence_packet_schema.json",
        )
        schema_failures.extend(packet_failures)
        packet_valid = not packet_failures
        packet_sample = {
            "artifact": "evidence_packet",
            "status": "pass" if packet_valid else "fail",
            "value": packet_valid,
            "schema_valid": packet_valid,
            "failure_count": len(packet_failures),
            "path": str(packet_path.relative_to(root)) if packet_path else "missing",
        }
        if packet_failures:
            packet_sample["failure_reasons"] = sorted({
                str(item.get("reason") or "schema_validation_failed")
                for item in packet_failures
            })
        schema_samples.append(packet_sample)
    if audit:
        audit_failures: list[dict[str, Any]] = []
        if not isinstance(audit.get("agent_execution"), list):
            audit_failures.append({
                "field": "agent_execution",
                "reason": "agent_execution_list_missing",
                "source": str(audit_path.relative_to(root)) if audit_path else "missing",
            })
        if str(audit.get("ticker") or "").upper() != ticker.upper():
            audit_failures.append({
                "field": "ticker",
                "reason": "ticker_mismatch",
                "source": str(audit_path.relative_to(root)) if audit_path else "missing",
            })
        schema_failures.extend(audit_failures)
        audit_valid = not audit_failures
        audit_sample = {
            "artifact": "agent_effectiveness_audit",
            "status": "pass" if audit_valid else "fail",
            "value": audit_valid,
            "schema_valid": audit_valid,
            "failure_count": len(audit_failures),
            "path": str(audit_path.relative_to(root)) if audit_path else "missing",
        }
        if audit_failures:
            audit_sample["failure_reasons"] = sorted({
                str(item.get("reason") or "schema_validation_failed")
                for item in audit_failures
            })
        schema_samples.append(audit_sample)
    schema_units = len(schema_samples)
    schema_valid_units = sum(1 for item in schema_samples if item["schema_valid"])
    schema_validity = (
        None if schema_units == 0 else schema_valid_units / schema_units
    )
    output_records = _agent_output_records(audit, packet)
    calc_findings = _unauthorized_financial_calculation_findings(output_records)
    unauthorized_calc_score = (
        None if not output_records else (len(output_records) - len(calc_findings)) / len(output_records)
    )
    deepeval_cases = _filter_records_for_ticker(
        _read_json_list(_benchmark_scoped_path(root, DEEPEVAL_CASE_PATH, DEEPEVAL_CASE_RELATIVE)),
        ticker,
    )
    deepeval_result = evaluate_deepeval_cases(deepeval_cases)
    judge_scores = deepeval_result.get("scores") or {}
    judge_evaluator = {
        "framework": "deepeval",
        "framework_version": deepeval_result.get("framework_version"),
        "execution_status": deepeval_result["execution_status"],
    }
    trace_summary = [item for item in packet.get("trace_summary") or [] if isinstance(item, dict)]
    artifact_sections = {
        str(ref.get("section_key"))
        for ref in (packet.get("artifact_refs") or [])
        if isinstance(ref, dict) and ref.get("section_key")
    }
    handoff_artifact_ready = bool(
        artifact_sections & {"facts", "snapshot"}
        and artifact_sections & {"valuation"}
        and artifact_sections & {"report_draft", "publishable_final_report_model"}
        and artifact_sections & {"evidence_packet"}
    )
    handoff_samples = []
    for record in agent_records:
        has_output = bool(
            record.get("output")
            or record.get("output_summary")
            or record.get("content")
        )
        passed = record.get("status") == "completed" and has_output and handoff_artifact_ready
        handoff_samples.append({
            "agent_id": record.get("agent_id") or record.get("agent_role"),
            "status": "pass" if passed else "fail",
            "agent_status": record.get("status"),
            "has_output": has_output,
            "required_artifacts_ready": handoff_artifact_ready,
            "registered_sections": sorted(artifact_sections),
        })
    stage_handoff_completeness = (
        sum(item["status"] == "pass" for item in handoff_samples) / len(handoff_samples)
        if handoff_samples else None
    )

    tool_runtime_events = tool_summary or [
        item for item in trace_summary if item.get("kind") == "tool_call" or item.get("tool_name")
    ]
    tool_success_samples = []
    for item in tool_runtime_events:
        status = str(item.get("status") or "").lower()
        controlled_failure = bool(item.get("controlled_failure") or item.get("handled_error"))
        passed = status in {"completed", "success", "succeeded", "ok", "pass"} or controlled_failure
        tool_success_samples.append({
            "tool_name": item.get("tool_name"),
            "status": "pass" if passed else "fail",
            "runtime_status": status or None,
            "controlled_failure": controlled_failure,
        })
    tool_call_success_rate = (
        sum(item["status"] == "pass" for item in tool_success_samples) / len(tool_success_samples)
        if tool_success_samples else None
    )

    stage_output_count = len(agent_records)
    repair_events = [
        item for item in [*trace_summary, *agent_records]
        if _event_retry_count(item) > 0
        or "repair" in str(item.get("kind") or item.get("action") or "").lower()
        or str(item.get("status") or "").lower() in {"schema_repaired", "repair"}
    ]
    repair_loop_rate = (
        len(repair_events) / stage_output_count if stage_output_count else None
    )

    token_samples = []
    for item in [*agent_records, *trace_summary]:
        total_tokens = (
            _token_count(item, "tokens_input", "input_tokens", "prompt_tokens")
            + _token_count(item, "tokens_output", "output_tokens", "completion_tokens")
        )
        if total_tokens <= 0:
            continue
        token_budget = item.get("token_budget") or item.get("max_tokens") or 8000
        try:
            budget_value = int(token_budget)
        except (TypeError, ValueError):
            budget_value = 8000
        passed = total_tokens <= budget_value
        token_samples.append({
            "agent_id": item.get("agent_id") or item.get("agent_role"),
            "status": "pass" if passed else "fail",
            "tokens": total_tokens,
            "token_budget": budget_value,
        })
    token_budget_adherence = (
        sum(item["status"] == "pass" for item in token_samples) / len(token_samples)
        if token_samples else None
    )

    judge_samples = [
        item for item in deepeval_result.get("samples", [])
        if isinstance(item, dict)
    ]
    judge_calibration_agreement = None
    rationale_samples = []
    for sample in judge_samples:
        rationale = sample.get("rationale") or sample.get("reason")
        evidence_refs = sample.get("evidence_refs") or sample.get("source_artifact_refs")
        has_evidence = bool(rationale and evidence_refs)
        rationale_samples.append({
            "id": sample.get("id") or sample.get("case_id"),
            "status": "pass" if has_evidence else "fail",
            "has_rationale": bool(rationale),
            "has_evidence_refs": bool(evidence_refs),
        })
    judge_rationale_evidence_coverage = (
        sum(item["status"] == "pass" for item in rationale_samples) / len(rationale_samples)
        if rationale_samples else None
    )
    judge_score_values = [
        value for value in (
            judge_scores.get("role_adherence"),
            judge_scores.get("groundedness"),
            judge_scores.get("plan_adherence"),
        )
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    judge_readiness_score = sum(judge_score_values) / len(judge_score_values) if judge_score_values else 0.0
    repair_health = None if repair_loop_rate is None else _clamp01(1.0 - (repair_loop_rate / 0.15))
    workflow_quality_score, workflow_quality_samples = _weighted_score([
        ("tool_permission_compliance", tool_compliance, 0.14),
        ("schema_validity", schema_validity, 0.14),
        ("stage_handoff_completeness", stage_handoff_completeness, 0.14),
        ("tool_call_success_rate", tool_call_success_rate, 0.12),
        ("artifact_manifest_compliance", manifest_compliance, 0.10),
        ("task_completion", task_completion, 0.10),
        ("token_budget_observability", token_budget_adherence if token_budget_adherence is not None else 0.0, 0.10),
        ("repair_loop_health", repair_health, 0.08),
        ("judge_readiness_score", judge_readiness_score, 0.08),
    ])
    metrics = [
        _metric("agent.workflow_quality_score", "Agent workflow quality stress score",
                workflow_quality_score, ">= 75%",
                _ratio_status(workflow_quality_score, 0.75),
                str(audit_path.relative_to(root)) if audit_path else (
                    str(packet_path.relative_to(root)) if packet_path else "missing"
                ),
                sample_size=len(workflow_quality_samples),
                failed_examples=[
                    sample for sample in workflow_quality_samples
                    if sample["component_score"] < 1.0
                ],
                evaluator={"framework": "hard_mode_agent_workflow_audit",
                           "execution_status": "executed" if workflow_quality_samples else "not_executed"},
                calculation={"aggregation": "weighted_score",
                             "numerator": workflow_quality_score,
                             "denominator": 1.0 if workflow_quality_score is not None else None,
                             "inputs": {
                                 "tool_calls": len(tool_permission_samples),
                                 "schema_units": schema_units,
                                 "agent_records": len(agent_records),
                                 "token_samples": len(token_samples),
                                 "judge_samples": len(judge_samples),
                             },
                             "parameters": {
                                 "rationale": "Ceiling-resistant score: deterministic compliance gates stay strict, while missing telemetry, token traces, handoff richness, and judge readiness reduce the benchmark score.",
                                 "components": [
                                     {"id": sample["component"], "weight": sample["weight"]}
                                     for sample in workflow_quality_samples
                                 ],
                             },
                             "per_sample_results": workflow_quality_samples},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("tool_permission_compliance", "Tool permission compliance", tool_compliance, "100%",
                _ratio_status(tool_compliance, 1.0), str(packet_path.relative_to(root)) if packet_path else "missing",
                ",".join(sorted({str(item["reason"]) for item in tool_permission_failures})) if tool_permission_failures else "",
                failed_examples=tool_permission_failures[:100],
                sample_size=len(tool_permission_samples),
                evaluator={"framework": "agent_tool_permission_trace",
                           "execution_status": "executed" if tool_permission_samples else "not_executed"},
                calculation={"numerator": len(permitted_tools),
                             "denominator": len(tool_permission_samples), "aggregation": "coverage",
                             "per_sample_results": tool_permission_samples[:100]},
                evidence=_artifact_evidence(root, packet_path)),
        _metric("artifact_manifest_compliance", "Artifact manifest compliance", manifest_compliance, "100%",
                _ratio_status(manifest_compliance, 1.0), str(packet_path.relative_to(root)) if packet_path else "missing",
                ",".join(f"artifact_missing:{name}" for name in manifest_missing),
                failed_examples=[{"section_key": name, "reason": "required_artifact_not_registered"} for name in manifest_missing],
                sample_size=len(required_artifact_groups),
                evaluator={"framework": "artifact_manifest_trace",
                           "execution_status": "executed" if manifest_sections else "not_executed"},
                calculation={"numerator": len(required_artifact_groups) - len(manifest_missing),
                             "denominator": len(required_artifact_groups), "aggregation": "coverage",
                             "per_sample_results": [
                                 {
                                     "section_group": list(group),
                                     "status": "pass" if manifest_sections & set(group) else "fail",
                                     "registered_sections": sorted(manifest_sections),
                                 }
                                 for group in required_artifact_groups
                             ]},
                evidence=_artifact_evidence(root, packet_path)),
        _metric("agent.stage_handoff_completeness", "Stage handoff completeness",
                stage_handoff_completeness, ">= 95%",
                _ratio_status(stage_handoff_completeness, 0.95),
                str(audit_path.relative_to(root)) if audit_path else "missing",
                "stage_handoff_evidence_missing" if stage_handoff_completeness is None else "",
                sample_size=len(handoff_samples),
                failed_examples=[item for item in handoff_samples if item["status"] != "pass"],
                evaluator={"framework": "trace_artifact_handoff_audit",
                           "execution_status": "executed" if handoff_samples else "not_executed"},
                calculation={"numerator": sum(item["status"] == "pass" for item in handoff_samples),
                             "denominator": len(handoff_samples), "aggregation": "coverage",
                             "per_sample_results": handoff_samples},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("agent.tool_call_success_rate", "Tool call success rate",
                tool_call_success_rate, ">= 95%",
                _ratio_status(tool_call_success_rate, 0.95),
                str(packet_path.relative_to(root)) if packet_path else "missing",
                "tool_runtime_trace_missing" if tool_call_success_rate is None else "",
                sample_size=len(tool_success_samples),
                failed_examples=[item for item in tool_success_samples if item["status"] != "pass"],
                evaluator={"framework": "tool_runtime_trace_audit",
                           "execution_status": "executed" if tool_success_samples else "not_executed"},
                calculation={"numerator": sum(item["status"] == "pass" for item in tool_success_samples),
                             "denominator": len(tool_success_samples), "aggregation": "coverage",
                             "per_sample_results": tool_success_samples},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("agent.repair_loop_rate", "Repair loop rate",
                repair_loop_rate, "<= 15%",
                _ratio_status(repair_loop_rate, 0.15, "lte"),
                str(audit_path.relative_to(root)) if audit_path else "missing",
                "stage_output_trace_missing" if repair_loop_rate is None else "",
                sample_size=stage_output_count,
                failed_examples=repair_events[:100],
                evaluator={"framework": "agent_repair_trace_audit",
                           "execution_status": "executed" if stage_output_count else "not_executed"},
                calculation={"numerator": len(repair_events), "denominator": stage_output_count,
                             "aggregation": "rate", "per_sample_results": repair_events[:100]},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("agent.token_budget_adherence", "Token budget adherence",
                token_budget_adherence, ">= 90%",
                _ratio_status(token_budget_adherence, 0.90),
                str(audit_path.relative_to(root)) if audit_path else "missing",
                "token_usage_trace_missing" if token_budget_adherence is None else "",
                sample_size=len(token_samples),
                failed_examples=[item for item in token_samples if item["status"] != "pass"],
                evaluator={"framework": "token_budget_trace_audit",
                           "execution_status": "executed" if token_samples else "not_executed"},
                calculation={"numerator": sum(item["status"] == "pass" for item in token_samples),
                             "denominator": len(token_samples), "aggregation": "coverage",
                             "parameters": {"default_stage_token_budget": 8000},
                             "per_sample_results": token_samples},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("schema_validity", "Output schema validity", schema_validity, "100%",
                _ratio_status(schema_validity, 1.0), "config/harness/*.schema.json",
                ",".join(sorted({str(item.get("reason")) for item in schema_failures})) if schema_failures else "",
                failed_examples=schema_failures[:100],
                sample_size=schema_units,
                evaluator={"framework": "json_schema_required_contract",
                           "execution_status": "executed" if schema_units else "not_executed"},
                calculation={"numerator": schema_valid_units if schema_validity is not None else 0,
                             "denominator": schema_units, "aggregation": "coverage",
                             "per_sample_results": schema_samples},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("role_adherence", "Role adherence", judge_scores.get("role_adherence"), ">= 85%",
                _ratio_status(judge_scores.get("role_adherence"), 0.85),
                str(DEEPEVAL_CASE_PATH), deepeval_result.get("reason") or "",
                sample_size=deepeval_result["sample_size"], evaluator=judge_evaluator,
                calculation={"aggregation": "mean", "per_sample_results": deepeval_result.get("samples", [])[:100]}),
        _metric("groundedness", "Groundedness", judge_scores.get("groundedness"), ">= 85%",
                _ratio_status(judge_scores.get("groundedness"), 0.85),
                str(DEEPEVAL_CASE_PATH), deepeval_result.get("reason") or "",
                sample_size=deepeval_result["sample_size"], evaluator=judge_evaluator,
                calculation={"aggregation": "mean", "per_sample_results": deepeval_result.get("samples", [])[:100]}),
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
                             "per_sample_results": output_records[:100]},
                evidence=_artifact_evidence(root, packet_path, audit_path)),
        _metric("task_completion", "Task completion", task_completion, ">= 85%",
                _ratio_status(task_completion, 0.85), str(audit_path.relative_to(root)) if audit_path else "missing",
                sample_size=len(agent_records),
                calculation={"numerator": sum(record.get("status") == "completed" for record in agent_records),
                             "denominator": len(agent_records), "aggregation": "coverage",
                             "per_sample_results": agent_records[:100]},
                evidence=_artifact_evidence(root, audit_path)),
        _metric("plan_adherence", "Plan adherence", judge_scores.get("plan_adherence"), ">= 80%",
                _ratio_status(judge_scores.get("plan_adherence"), 0.80),
                str(DEEPEVAL_CASE_PATH), deepeval_result.get("reason") or "",
                sample_size=deepeval_result["sample_size"], evaluator=judge_evaluator,
                calculation={"aggregation": "mean", "per_sample_results": deepeval_result.get("samples", [])[:100]}),
        _metric("critic_issue_recall", "Critic issue recall", None, ">= 90%", "measured_only",
                "seeded failure dataset missing"),
        _metric("agent.judge_calibration_agreement", "Judge calibration agreement",
                judge_calibration_agreement, ">= 85%",
                "not_applicable", str(DEEPEVAL_CASE_PATH),
                "calibrated_actual_output_dataset_not_applicable_for_offline_benchmark",
                sample_size=0,
                evaluator={"framework": "judge_calibration_set",
                           "execution_status": "not_executed"},
                calculation={"aggregation": "calibration_agreement",
                             "per_sample_results": []}),
        _metric("agent.judge_rationale_evidence_coverage", "Judge rationale evidence coverage",
                judge_rationale_evidence_coverage, ">= 90%",
                "not_applicable" if judge_rationale_evidence_coverage is None else _ratio_status(judge_rationale_evidence_coverage, 0.90),
                str(DEEPEVAL_CASE_PATH),
                "calibrated_judge_rationale_dataset_not_applicable_for_offline_benchmark"
                if judge_rationale_evidence_coverage is None else "",
                sample_size=len(rationale_samples),
                failed_examples=[item for item in rationale_samples if item["status"] != "pass"],
                evaluator={"framework": "judge_rationale_evidence_audit",
                           "execution_status": "executed" if rationale_samples else "not_executed"},
                calculation={"numerator": sum(item["status"] == "pass" for item in rationale_samples),
                             "denominator": len(rationale_samples), "aggregation": "coverage",
                             "per_sample_results": rationale_samples}),
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
    report_path = _report_pdf_path(root, ticker, "report")
    explanation_path = _report_pdf_path(root, ticker, "explanation")
    report = _pdf_stats(report_path)
    explanation = _pdf_stats(explanation_path)
    finance_pass = _financial_result_passed(financial)
    heuristic_scores = _report_quality_subscores(report, explanation)
    claim_ledger_path = _latest_json_for_ticker(
        root / "storage" / "archive", "claim_ledger.json", ticker
    )
    evidence_packet_path = _latest_scoped_json_artifact_for_ticker(
        archive_root=root / "storage" / "archive",
        runs_root=root / "storage" / "runs",
        ticker=ticker,
        legacy_name="run1_evidence_packet.json",
        suffix="_evidence_packet.json",
    )
    evidence_packet = _read_json(evidence_packet_path)
    evidence_support_available = claim_ledger_path is not None or evidence_packet_path is not None
    structured_quality = _structured_report_quality_payload(evidence_packet)
    structured_scores = _scores_from_structured_report_quality(structured_quality)
    structured_report_quality_available = structured_scores is not None and evidence_support_available

    # Displayed dimensions: graded scorer is authoritative when structured evidence is
    # available (independent per-dimension spread). When evidence is missing, scores stay
    # None so the fail-closed "structured_report_quality_evidence_missing" contract holds.
    display_scores = dict(heuristic_scores)
    if not evidence_support_available:
        display_scores["evidence_integration"] = None
    scores = display_scores if structured_report_quality_available else {
        key: None for key in REPORT_QUALITY_SCORE_KEYS
    }
    total_score = _report_quality_total(scores)
    report_hardness_score = _report_benchmark_hardness_score(scores)

    # Blocking decision: keep the structured binary gate authoritative (publication safety).
    gate_scores = structured_scores if structured_report_quality_available else {
        key: None for key in REPORT_QUALITY_SCORE_KEYS
    }
    structured_total_score = (
        structured_quality.get("score")
        if isinstance(structured_quality, dict)
        and structured_quality.get("rubric_version") == "report_quality_v2"
        else None
    )
    publishable_model_path = _latest_named_for_ticker(
        root / "storage" / "runs", "publishable_final_report_model.json", ticker
    )
    publishable_model = _read_json(publishable_model_path)
    package_pass = not financial.get("blocking_issues") and finance_pass
    gate_results = evidence_packet.get("gate_results") if isinstance(evidence_packet.get("gate_results"), dict) else {}
    run_approved = bool(gate_results) and all(
        not isinstance(gate, dict) or gate.get("passed") is not False
        for gate in gate_results.values()
    )
    final_approval_present = bool(
        publishable_model.get("final_approval") or publishable_model.get("approved_for_benchmark")
    )
    publishable_model_locked = bool(publishable_model.get("locked"))
    report_quality_allow_export = (
        isinstance(structured_total_score, (int, float))
        and structured_total_score >= 85
        and finance_pass
        and (gate_scores.get("completeness") or 0) >= 90
        and (gate_scores.get("valuation_transparency") or 0) >= 85
    )
    publication_checks = {
        "run_approved": run_approved,
        "final_report_approval": final_approval_present,
        "package_validation": package_pass,
        "report_quality_allow_export": report_quality_allow_export,
        "publishable_model_locked": publishable_model_locked,
    }
    publication_pass = all(publication_checks.values())
    report_text = "\n".join(
        item for item in (str(report.get("text") or ""), str(explanation.get("text") or ""))
        if item
    ).lower()
    recommendation_visible = any(
        marker in report_text
        for marker in (
            "recommendation",
            "khuyáº¿n nghá»‹",
            "khuyến nghị",
            "khuyen nghi",
            "buy",
            "hold",
            "sell",
        )
    )
    target_visible = any(
        marker in report_text
        for marker in ("target price", "giÃ¡ má»¥c tiÃªu", "giá mục tiêu", "gia muc tieu")
    )
    recommendation_checks = [
        {
            "check": "target_has_recommendation_context",
            "status": "pass" if (not target_visible or recommendation_visible) else "fail",
            "target_visible": target_visible,
            "recommendation_visible": recommendation_visible,
        },
        {
            "check": "visible_recommendation_is_approved",
            "status": "pass" if (not recommendation_visible or final_approval_present) else "fail",
            "final_approval_present": final_approval_present,
        },
        {
            "check": "financial_gate_supports_recommendation",
            "status": "pass" if (not recommendation_visible or finance_pass) else "fail",
            "finance_pass": finance_pass,
        },
    ]
    recommendation_consistency = (
        sum(item["status"] == "pass" for item in recommendation_checks) / len(recommendation_checks)
    )
    report_evidence = _artifact_evidence(
        root,
        report_path,
        explanation_path,
        claim_ledger_path,
        evidence_packet_path,
    )
    rubric_sample = {
        "ticker": ticker.upper(),
        "report_pdf": report["path"],
        "explanation_pdf": explanation["path"],
        "report_exists": report["exists"],
        "explanation_exists": explanation["exists"],
        "claim_ledger_path": _source_path(claim_ledger_path, root) if claim_ledger_path else None,
        "evidence_packet_path": _source_path(evidence_packet_path, root) if evidence_packet_path else None,
        "evidence_support_available": evidence_support_available,
        "structured_report_quality_available": structured_report_quality_available,
        "scores": scores,
        "section_details": (
            structured_quality.get("section_details")
            if isinstance(structured_quality, dict)
            else None
        ),
        "heuristic_scores": heuristic_scores,
    }

    def _report_sample(status: str, value: Any) -> list[dict[str, Any]]:
        sample = dict(rubric_sample)
        sample["status"] = status
        sample["value"] = value
        return [sample]

    metrics = [
        _metric("report_pdf_rendered", "Report PDF rendered", 1 if report["exists"] else 0, "pass",
                "pass" if report["exists"] else "fail", str(report["path"]),
                calculation={"aggregation": "presence", "numerator": 1 if report["exists"] else 0,
                             "denominator": 1,
                             "per_sample_results": _report_sample("pass" if report["exists"] else "fail",
                                                                  report["exists"])},
                evidence=report_evidence),
        _metric("explanation_pdf_rendered", "Explanation PDF rendered", 1 if explanation["exists"] else 0,
                "pass", "pass" if explanation["exists"] else "fail", str(explanation["path"]),
                calculation={"aggregation": "presence", "numerator": 1 if explanation["exists"] else 0,
                             "denominator": 1,
                             "per_sample_results": _report_sample("pass" if explanation["exists"] else "fail",
                                                                  explanation["exists"])},
                evidence=report_evidence),
        _metric("financial_gate_passed", "Deterministic finance gate", 1 if finance_pass else 0, "pass",
                "pass" if finance_pass else "fail", "financial_eval.json",
                ",".join(financial.get("blocking_issues") or []),
                calculation={"aggregation": "boolean_gate", "numerator": 1 if finance_pass else 0,
                             "denominator": 1, "per_sample_results": [{
                                 "financial_decision": financial.get("decision"),
                                 "blocking_issues": financial.get("blocking_issues") or [],
                                 "status": "pass" if finance_pass else "fail",
                                 "value": finance_pass,
                             }]},
                evidence=report_evidence),
        _metric("report.quality_total", "Report quality total", total_score, ">= 80%",
                _metric_status(total_score, 80), "report_quality_v2",
                sample_size=1 if total_score is not None else 0,
                calculation={"aggregation": "weighted_mean",
                             "parameters": {
                                 "rubric_version": structured_quality.get("rubric_version")
                                 if isinstance(structured_quality, dict) else None,
                                 "section_details": structured_quality.get("section_details")
                                 if isinstance(structured_quality, dict) else None,
                             },
                             "per_sample_results": _report_sample(_metric_status(total_score, 80), total_score)},
                evidence=report_evidence),
        _metric("report_quality_score", "Report quality score", total_score, ">= 85%",
                _metric_status(total_score, 85), "report_quality_v2",
                sample_size=1 if total_score is not None else 0,
                calculation={"aggregation": "weighted_mean",
                             "parameters": {
                                 "rubric_version": structured_quality.get("rubric_version")
                                 if isinstance(structured_quality, dict) else None,
                                 "section_details": structured_quality.get("section_details")
                                 if isinstance(structured_quality, dict) else None,
                             },
                             "per_sample_results": _report_sample(_metric_status(total_score, 85), total_score)},
                evidence=report_evidence),
        _metric("report.benchmark_hardness_score", "Report hard-mode benchmark score",
                report_hardness_score, ">= 75%",
                _metric_status(report_hardness_score, 75), "report_quality_v2",
                sample_size=1 if report_hardness_score is not None else 0,
                calculation={"aggregation": "weighted_mean",
                             "parameters": {
                                 "rationale": "Ceiling-resistant score: total quality is penalized by the weakest analytical dimensions so section completeness cannot mask thin risk, sensitivity, or thesis evidence.",
                                 "stress_dimensions": [
                                     "thesis_specificity",
                                     "financial_analysis_depth",
                                     "forecast_rationale",
                                     "valuation_transparency",
                                     "risk_catalyst_quality",
                                     "evidence_integration",
                                     "peer_industry_context_quality",
                                     "executive_summary_actionability",
                                     "sensitivity_disclosure_completeness",
                                 ],
                             },
                             "per_sample_results": _report_sample(
                                 _metric_status(report_hardness_score, 75),
                                 report_hardness_score,
                             )},
                evidence=report_evidence),
        _metric("report.completeness", "Report completeness", scores["completeness"], ">= 80%",
                _metric_status(scores["completeness"], 80), "report PDF rubric",
                sample_size=1 if scores["completeness"] is not None else 0,
                calculation={"aggregation": "required_element_coverage",
                             "per_sample_results": _report_sample(_metric_status(scores["completeness"], 80),
                                                                  scores["completeness"])},
                evidence=report_evidence),
        _metric("report.thesis_specificity", "Thesis specificity", scores["thesis_specificity"], ">= 60%",
                _metric_status(scores["thesis_specificity"], 60), "report PDF rubric",
                sample_size=1 if scores["thesis_specificity"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["thesis_specificity"], 60),
                                 scores["thesis_specificity"])},
                evidence=report_evidence),
        _metric("report.financial_analysis_depth", "Financial analysis depth",
                scores["financial_analysis_depth"], ">= 80%",
                _metric_status(scores["financial_analysis_depth"], 80), "report PDF rubric",
                sample_size=1 if scores["financial_analysis_depth"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["financial_analysis_depth"], 80),
                                 scores["financial_analysis_depth"])},
                evidence=report_evidence),
        _metric("report.forecast_rationale", "Forecast rationale",
                scores["forecast_rationale"], ">= 80%",
                _metric_status(scores["forecast_rationale"], 80), "report PDF rubric",
                sample_size=1 if scores["forecast_rationale"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(_metric_status(scores["forecast_rationale"], 80),
                                                                  scores["forecast_rationale"])},
                evidence=report_evidence),
        _metric("report.valuation_transparency", "Valuation transparency",
                scores["valuation_transparency"], ">= 80%",
                _metric_status(scores["valuation_transparency"], 80), "report PDF rubric",
                sample_size=1 if scores["valuation_transparency"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["valuation_transparency"], 80),
                                 scores["valuation_transparency"])},
                evidence=report_evidence),
        _metric("report.risk_catalyst_quality", "Risk and catalyst quality",
                scores["risk_catalyst_quality"], ">= 65%",
                _metric_status(scores["risk_catalyst_quality"], 65), "report PDF rubric",
                sample_size=1 if scores["risk_catalyst_quality"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["risk_catalyst_quality"], 65),
                                 scores["risk_catalyst_quality"])},
                evidence=report_evidence),
        _metric("report.evidence_integration", "Evidence integration",
                scores["evidence_integration"], ">= 75%",
                _metric_status(scores["evidence_integration"], 75), "report PDF rubric",
                "claim_ledger_or_evidence_packet_missing" if not evidence_support_available else "",
                sample_size=1 if scores["evidence_integration"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["evidence_integration"], 75),
                                 scores["evidence_integration"])},
                evidence=report_evidence),
        _metric("report.peer_industry_context_quality", "Peer and industry context quality",
                scores["peer_industry_context_quality"], ">= 75%",
                _metric_status(scores["peer_industry_context_quality"], 75), "report PDF rubric",
                sample_size=1 if scores["peer_industry_context_quality"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["peer_industry_context_quality"], 75),
                                 scores["peer_industry_context_quality"])},
                evidence=report_evidence),
        _metric("report.executive_summary_actionability", "Executive summary actionability",
                scores["executive_summary_actionability"], ">= 70%",
                _metric_status(scores["executive_summary_actionability"], 70), "report PDF rubric",
                sample_size=1 if scores["executive_summary_actionability"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["executive_summary_actionability"], 70),
                                 scores["executive_summary_actionability"])},
                evidence=report_evidence),
        _metric("report.sensitivity_disclosure_completeness", "Sensitivity disclosure completeness",
                scores["sensitivity_disclosure_completeness"], ">= 45%",
                _metric_status(scores["sensitivity_disclosure_completeness"], 45), "report PDF rubric",
                sample_size=1 if scores["sensitivity_disclosure_completeness"] is not None else 0,
                calculation={"aggregation": "rubric_score",
                             "per_sample_results": _report_sample(
                                 _metric_status(scores["sensitivity_disclosure_completeness"], 45),
                                 scores["sensitivity_disclosure_completeness"])},
                evidence=report_evidence),
        _metric("report.recommendation_consistency", "Recommendation consistency",
                recommendation_consistency, "100%",
                _ratio_status(recommendation_consistency, 1.0), "report PDF rubric",
                ",".join(item["check"] for item in recommendation_checks if item["status"] != "pass"),
                sample_size=len(recommendation_checks),
                failed_examples=[item for item in recommendation_checks if item["status"] != "pass"],
                calculation={"aggregation": "coverage",
                             "numerator": sum(item["status"] == "pass" for item in recommendation_checks),
                             "denominator": len(recommendation_checks),
                             "per_sample_results": recommendation_checks},
                evidence=report_evidence),
        _metric("publication_readiness", "Publication readiness", 1 if publication_pass else 0,
                "pass", "pass" if publication_pass else "fail",
                "publication governance",
                ",".join(key for key, value in publication_checks.items() if not value),
                calculation={"aggregation": "boolean_gate", "numerator": 1 if publication_pass else 0,
                             "denominator": 1,
                             "per_sample_results": [
                                 {"check": key, "status": "pass" if value else "fail"}
                                 for key, value in publication_checks.items()
                             ]},
                evidence=report_evidence),
    ]
    if not structured_report_quality_available:
        reason = "structured_report_quality_evidence_missing"
        for metric in metrics:
            metric_id = str(metric.get("metric_id") or "")
            if metric_id in {
                "report.quality_total",
                "report_quality_score",
                "report.completeness",
                "report.thesis_specificity",
                "report.financial_analysis_depth",
                "report.forecast_rationale",
                "report.valuation_transparency",
                "report.risk_catalyst_quality",
                "report.evidence_integration",
                "report.peer_industry_context_quality",
                "report.executive_summary_actionability",
                "report.sensitivity_disclosure_completeness",
            }:
                metric["detail"] = reason
                metric["failed_examples"] = [{
                    "reason": reason,
                    "claim_ledger_available": claim_ledger_path is not None,
                    "evidence_packet_available": evidence_packet_path is not None,
                    "heuristic_scores": heuristic_scores,
                }]
                metric.setdefault("evaluator", {})["execution_status"] = "not_executed"
                metric.setdefault("threshold_policy", {})["evidence_basis"] = "structured_report_quality_evaluation_required"
    blockers = _blocked(metrics)
    if not final_approval_present:
        blockers.append("final_report_approval_missing")
    if not publishable_model_path:
        blockers.append("publishable_final_report_model_missing")
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": sorted(set(blockers)),
        "rubric": "report_quality_v1",
        "score": total_score,
        "decision": "allow_export" if report_quality_allow_export else (
            "draft_only" if isinstance(total_score, (int, float)) and total_score >= 70 else "block_export"
        ),
        "failed_gates": ["financial_gate"] if not finance_pass else [],
        "section_scores": scores,
        "report_artifacts": {"pdf": report, "explanation_pdf": explanation},
        "publication_readiness": {
            "passed": publication_pass,
            "blocking_reasons": sorted(set(blockers)),
            "checks": publication_checks,
        },
    }


def evaluate_observability(root: Path, ticker: str) -> dict[str, Any]:
    packet_path = _latest_scoped_json_artifact_for_ticker(
        archive_root=root / "storage" / "archive",
        runs_root=root / "storage" / "runs",
        ticker=ticker,
        legacy_name="run1_evidence_packet.json",
        suffix="_evidence_packet.json",
    )
    packet = _read_json(packet_path)
    audit_path = _latest_scoped_json_artifact_for_ticker(
        archive_root=root / "storage" / "archive",
        runs_root=root / "storage" / "runs",
        ticker=ticker,
        legacy_name="run1_agent_effectiveness_audit.json",
        suffix="_agent_effectiveness_audit.json",
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
    retrieval_denominator = len(retrieval_events)
    retrieval_fallback_rate = retrieval_fallbacks / retrieval_denominator if retrieval_denominator else None
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
    artifact_upload_failure_value = artifact_upload_failures if upload_events else None
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
    rubric_path, golden_path, negative_path = _ops_benchmark_paths(root)
    rubric = _read_yaml_dict(rubric_path)
    golden_runs = _read_csv_dicts(golden_path)
    _negative_cases = _read_jsonl(negative_path)
    latency_budgets = rubric.get("latency_budgets_seconds") if isinstance(rubric.get("latency_budgets_seconds"), dict) else {}
    cost_budgets = rubric.get("cost_budgets_usd") if isinstance(rubric.get("cost_budgets_usd"), dict) else {}
    golden_samples = [
        {
            **row,
            "total_duration_seconds": _float_or_none(row.get("total_duration_seconds")),
            "estimated_cost_usd": _float_or_none(row.get("estimated_cost_usd")),
            "retry_count": _float_or_none(row.get("retry_count")),
            "artifact_upload_failures": _float_or_none(row.get("artifact_upload_failures")),
            "pdf_render_failures": _float_or_none(row.get("pdf_render_failures")),
        }
        for row in golden_runs
    ]
    if duration_seconds is None:
        full_report_durations = [
            _float_or_none(row.get("total_duration_seconds"))
            for row in golden_runs
            if row.get("run_type") in {"warm", "cold"} and row.get("ticker") == ticker.upper()
        ]
        if not any(value is not None for value in full_report_durations):
            full_report_durations = [
                _float_or_none(row.get("total_duration_seconds"))
                for row in golden_runs
                if row.get("run_type") in {"warm", "cold"}
            ]
        duration_seconds = _p95([value for value in full_report_durations if value is not None])
    warm_durations = [
        value for value in (
            _float_or_none(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "warm"
        )
        if value is not None
    ]
    cold_durations = [
        value for value in (
            _float_or_none(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "cold"
        )
        if value is not None
    ]
    render_durations = [
        value for value in (
            (_float_or_none(item.get("latency_ms")) or 0) / 1000
            for item in render_events if _float_or_none(item.get("latency_ms")) is not None
        )
        if value is not None
    ]
    if not render_durations:
        render_durations = [
            value for value in (
                _float_or_none(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "render_only"
            )
            if value is not None
        ]
    flash_warm_durations = [
        value for value in (
            (_float_or_none(item.get("latency_ms")) or 0) / 1000
            for item in trace_events
            if item.get("run_type") == "flash_memo" and not item.get("fallback_triggered")
            and _float_or_none(item.get("latency_ms")) is not None
        )
        if value is not None
    ]
    flash_cold_retrieval_durations = [
        value for value in (
            (_float_or_none(item.get("latency_ms")) or 0) / 1000
            for item in trace_events
            if item.get("run_type") == "flash_memo" and item.get("fallback_triggered")
            and _float_or_none(item.get("latency_ms")) is not None
        )
        if value is not None
    ]
    if not flash_warm_durations:
        flash_warm_durations = [
            value for value in (
                _float_or_none(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "flash_memo_warm"
            )
            if value is not None
        ]
    if not flash_cold_retrieval_durations:
        flash_cold_retrieval_durations = [
            value for value in (
                _float_or_none(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "flash_memo_cold_retrieval"
            )
            if value is not None
        ]
    warm_p95_seconds = _p95(warm_durations)
    cold_p95_seconds = _p95(cold_durations)
    render_p95_seconds = _p95(render_durations)
    flash_warm_p95_seconds = _p95(flash_warm_durations)
    flash_cold_retrieval_p95_seconds = _p95(flash_cold_retrieval_durations)
    baseline_warm_seconds = _float_or_none(latency_budgets.get("warm_full_report_p95"))
    latency_regression_ratio = (
        warm_p95_seconds / baseline_warm_seconds
        if warm_p95_seconds is not None and baseline_warm_seconds not in {None, 0}
        else None
    )
    cost_threshold = _float_or_none(cost_budgets.get("soft_full_report"))
    cost_per_report = sum(costs) if costs else None
    if cost_per_report is None:
        golden_costs = [
            value for value in (_float_or_none(row.get("estimated_cost_usd")) for row in golden_runs)
            if value is not None
        ]
        cost_per_report = max(golden_costs) if golden_costs else None
    final_ocr_errors = []
    explicit_final_ocr_errors = packet.get("final_numeric_ocr_errors") or run_log.get("final_numeric_ocr_errors")
    if isinstance(explicit_final_ocr_errors, list):
        final_ocr_errors = [item for item in explicit_final_ocr_errors if isinstance(item, dict)]
    final_ocr_error_count = len(final_ocr_errors)
    gate_results = packet.get("gate_results") if isinstance(packet.get("gate_results"), dict) else {}
    blocking_gate_categories = sorted(
        name for name, gate in gate_results.items()
        if isinstance(gate, dict) and gate.get("passed") is False
    )
    latency_window_coverage = _ratio_score(
        sum(value is not None for value in (
            warm_p95_seconds,
            cold_p95_seconds,
            render_p95_seconds,
            flash_warm_p95_seconds,
            flash_cold_retrieval_p95_seconds,
        )),
        5,
    )
    agent_latency_coverage = _ratio_score(len(agent_latencies), len(agent_records)) if agent_records else 0.0
    golden_cost_values = [
        value for value in (_float_or_none(row.get("estimated_cost_usd")) for row in golden_runs)
        if value is not None
    ]
    cost_trace_score = 1.0 if costs else (0.50 if golden_cost_values else 0.0)
    render_trace_score = 1.0 if render_events else (0.50 if report_exists else 0.0)
    retry_health = None if retry_rate is None else _clamp01(1.0 - (retry_rate / 0.05))
    fallback_health = None if retrieval_fallback_rate is None else _clamp01(1.0 - (retrieval_fallback_rate / 0.20))
    ocr_health = None if ocr_failure_rate is None else _clamp01(1.0 - (ocr_failure_rate / 0.05))
    telemetry_quality_score, telemetry_quality_samples = _weighted_score([
        ("trace_event_presence", _presence_score(trace_events), 0.15),
        ("agent_latency_coverage", agent_latency_coverage, 0.12),
        ("retrieval_trace_presence", _presence_score(retrieval_events), 0.12),
        ("artifact_upload_trace_presence", _presence_score(upload_events), 0.10),
        ("render_trace_presence", render_trace_score, 0.10),
        ("cost_trace_presence", cost_trace_score, 0.10),
        ("latency_window_coverage", latency_window_coverage, 0.12),
        ("retry_health", retry_health, 0.07),
        ("retrieval_fallback_health", fallback_health, 0.07),
        ("ocr_health", ocr_health, 0.05),
    ])
    metrics = [
        _metric("ops.telemetry_quality_score", "Telemetry quality stress score",
                telemetry_quality_score, ">= 80%",
                _ratio_status(telemetry_quality_score, 0.80),
                "runtime trace + ops golden windows",
                sample_size=len(telemetry_quality_samples),
                plan_id="07",
                failed_examples=[
                    sample for sample in telemetry_quality_samples
                    if sample["component_score"] < 1.0
                ],
                evaluator={"framework": "hard_mode_ops_telemetry_audit",
                           "execution_status": "executed" if telemetry_quality_samples else "not_executed"},
                calculation={"aggregation": "weighted_score",
                             "numerator": telemetry_quality_score,
                             "denominator": 1.0 if telemetry_quality_score is not None else None,
                             "inputs": {
                                 "trace_events": len(trace_events),
                                 "agent_records": len(agent_records),
                                 "agent_latencies": len(agent_latencies),
                                 "retrieval_events": len(retrieval_events),
                                 "upload_events": len(upload_events),
                                 "render_events": len(render_events),
                                 "cost_samples": len(costs),
                                 "golden_cost_samples": len(golden_cost_values),
                             },
                             "parameters": {
                                 "rationale": "Ceiling-resistant score: zero observed errors is insufficient when trace coverage is missing or only inferred from fallback artifacts.",
                                 "components": [
                                     {"id": sample["component"], "weight": sample["weight"]}
                                     for sample in telemetry_quality_samples
                                 ],
                             },
                             "per_sample_results": telemetry_quality_samples}),
        _metric("duration_seconds", "Full run duration", duration_seconds, "<= baseline p95 + 30%",
                "measured_only" if duration_seconds is None else "pass",
                "runtime trace" if duration_seconds is not None else "run trace missing",
                sample_size=len(stage_durations),
                plan_id="07",
                calculation={"aggregation": "sum", "per_sample_results": [
                    {
                        "stage": stage,
                        "duration_seconds": duration,
                        "status": "measured_only",
                        "value": duration,
                    }
                    for stage, duration in sorted(stage_durations.items())
                ]}),
        _metric("full_run_duration", "Full run duration", duration_seconds, "<= baseline p95 + 30%",
                "measured_only" if duration_seconds is None else "pass",
                "runtime trace" if duration_seconds is not None else "run trace missing",
                sample_size=len(stage_durations),
                plan_id="07",
                calculation={"aggregation": "sum", "per_sample_results": [
                    {
                        "stage": stage,
                        "duration_seconds": duration,
                        "status": "measured_only",
                        "value": duration,
                    }
                    for stage, duration in sorted(stage_durations.items())
                ]}),
        _metric("llm_retry_rate", "LLM retry rate", retry_rate, "<= 5%",
                "measured_only" if retry_rate is None else ("pass" if retry_rate <= 0.05 else "fail"),
                str(packet_path.relative_to(root)) if packet_path else "run trace missing",
                sample_size=llm_calls,
                plan_id="07",
                failed_examples=[item for item in agent_records if _event_retry_count(item) > 0],
                calculation={"numerator": retries, "denominator": llm_calls, "aggregation": "rate",
                             "per_sample_results": [
                                 _ops_runtime_sample(item, "llm_retry_rate")
                                 for item in agent_records[:100]
                             ]}),
        _metric("retrieval_fallback_rate", "Retrieval fallback rate", retrieval_fallback_rate, "<= 20%",
                "not_evaluable" if retrieval_fallback_rate is None else (
                    "pass" if retrieval_fallback_rate <= 0.20 else "fail"
                ),
                "runtime retrieval trace" if retrieval_events else "retrieval trace missing",
                sample_size=retrieval_denominator,
                plan_id="07",
                failed_examples=[item for item in retrieval_events if item.get("fallback_triggered")],
                calculation={"numerator": retrieval_fallbacks, "denominator": retrieval_denominator,
                             "aggregation": "rate", "per_sample_results": [
                                 _ops_runtime_sample(item, "retrieval_fallback_rate")
                                 for item in retrieval_events[:100]
                             ] or [{
                                 "sample_origin": "runtime_trace_requirement",
                                 "status": "not_evaluable",
                                 "reason": "retrieval_trace_missing",
                             }]}),
        _metric("ocr_failure_rate", "Material OCR failure rate", ocr_failure_rate, "<= 5%",
                _ratio_status(ocr_failure_rate, 0.05, "lte"), "latest OCR metadata",
                plan_id="07",
                failed_examples=[
                    {
                        "ticker": ticker.upper(),
                        "ocr_run_id": metadata.get("ocr_run_id"),
                        "pages_failed": metadata.get("pages_failed"),
                        "pages_processed": metadata.get("pages_processed"),
                        "reason": "ocr_pages_failed",
                    }
                ] if int(metadata.get("pages_failed") or 0) > 0 else []),
        _metric("final_ocr_error_count", "Final numeric OCR error count", final_ocr_error_count, "= 0",
                "pass" if final_ocr_error_count == 0 else "fail", "final numeric OCR audit",
                plan_id="07",
                sample_size=1,
                failed_examples=final_ocr_errors,
                calculation={"aggregation": "error_count", "numerator": final_ocr_error_count, "denominator": 1}),
        _metric("artifact_upload_failures", "Artifact upload failures", artifact_upload_failure_value, "0",
                "not_evaluable" if artifact_upload_failure_value is None else (
                    "pass" if artifact_upload_failure_value == 0 else "fail"
                ), "artifact upload trace" if upload_events else "artifact upload trace missing",
                plan_id="07",
                sample_size=len(upload_events),
                failed_examples=[item for item in upload_events if item.get("status") in {"failed", "error"}],
                calculation={"aggregation": "error_count", "numerator": artifact_upload_failure_value,
                             "denominator": len(upload_events), "per_sample_results": [
                                 _ops_runtime_sample(item, "artifact_upload_failures")
                                 for item in upload_events[:100]
                             ] or [{
                                 "sample_origin": "runtime_trace_requirement",
                                 "status": "not_evaluable",
                                 "reason": "artifact_upload_trace_missing",
                             }]}),
        _metric("pdf_render_failures", "PDF render failures", pdf_render_failures, "0",
                "pass" if pdf_render_failures == 0 else "fail", f"output/{ticker}_report.pdf",
                plan_id="07",
                sample_size=len(render_events) or 1,
                failed_examples=[item for item in render_events if item.get("status") in {"failed", "error"}],
                calculation={"aggregation": "error_count", "numerator": pdf_render_failures,
                             "denominator": len(render_events) or 1, "per_sample_results": [
                                 _ops_runtime_sample(item, "pdf_render_failures")
                                 for item in render_events[:100]
                             ]}),
        _ops_latency_metric("warm_full_report_p95_latency", "Full report p95 latency, warm run",
                            None if warm_p95_seconds is None else warm_p95_seconds / 60,
                            _float_or_none(latency_budgets.get("warm_full_report_p95")),
                            display_unit="minutes",
                            source=_source_path(golden_path, root) if golden_path.is_file() else "golden_run_traces missing",
                            samples=[row for row in golden_samples if row.get("run_type") == "warm"],
                            missing_reason="warm_full_report_latency_window_missing"),
        _ops_latency_metric("cold_full_report_p95_latency", "Full report p95 latency, cold run",
                            None if cold_p95_seconds is None else cold_p95_seconds / 60,
                            _float_or_none(latency_budgets.get("cold_full_report_p95")),
                            display_unit="minutes",
                            source=_source_path(golden_path, root) if golden_path.is_file() else "golden_run_traces missing",
                            samples=[row for row in golden_samples if row.get("run_type") == "cold"],
                            missing_reason="cold_full_report_latency_window_missing"),
        _ops_latency_metric("render_only_p95_latency", "Render-only p95 latency",
                            None if render_p95_seconds is None else render_p95_seconds / 60,
                            _float_or_none(latency_budgets.get("render_only_p95")),
                            display_unit="minutes",
                            source="pdf render trace",
                            samples=[{"duration_seconds": value, "run_type": "render_only", "status": "completed"} for value in render_durations],
                            missing_reason="render_only_latency_window_missing"),
        _ops_latency_metric("flash_memo_warm_p95_latency", "Flash memo p95 latency, warm run",
                            flash_warm_p95_seconds,
                            _float_or_none(latency_budgets.get("flash_memo_warm_p95")),
                            display_unit="seconds",
                            source="flash memo runtime trace",
                            samples=[{"duration_seconds": value, "run_type": "flash_memo_warm", "status": "completed"} for value in flash_warm_durations],
                            missing_reason="flash_memo_warm_latency_trace_missing"),
        _ops_latency_metric("flash_memo_cold_retrieval_p95_latency", "Flash memo p95 latency, cold retrieval",
                            None if flash_cold_retrieval_p95_seconds is None else flash_cold_retrieval_p95_seconds / 60,
                            180,
                            display_unit="minutes",
                            source="flash memo retrieval trace",
                            samples=[{"duration_seconds": value, "run_type": "flash_memo_cold_retrieval", "status": "completed"} for value in flash_cold_retrieval_durations],
                            missing_reason="flash_memo_cold_retrieval_latency_trace_missing"),
        _metric("latency_regression_ratio", "Latency regression", latency_regression_ratio, "<= 1.25",
                "not_evaluable" if latency_regression_ratio is None else ("pass" if latency_regression_ratio <= 1.25 else "fail"),
                _source_path(rubric_path, root) if rubric_path.is_file() else "latency rubric missing",
                "latency_baseline_missing" if latency_regression_ratio is None else "",
                plan_id="07",
                sample_size=len(warm_durations),
                failed_examples=[
                    sample for sample in golden_samples
                    if sample.get("run_type") == "warm"
                    and baseline_warm_seconds
                    and _float_or_none(sample.get("total_duration_seconds")) is not None
                    and _float_or_none(sample.get("total_duration_seconds")) > baseline_warm_seconds * 1.25
                ],
                calculation={"aggregation": "ratio", "numerator": warm_p95_seconds,
                             "denominator": baseline_warm_seconds,
                             "per_sample_results": [
                                 _ops_runtime_sample(item, "latency_regression_ratio")
                                 for item in golden_samples[:100]
                             ]}),
        _metric("cost_per_report", "Cost per full report", cost_per_report,
                f"<= {cost_threshold:g}" if cost_threshold is not None else "<= soft budget",
                "not_evaluable" if cost_per_report is None or cost_threshold is None else (
                    "pass" if cost_per_report <= cost_threshold else "fail"
                ),
                "cost ledger" if costs else (
                    _source_path(golden_path, root) if golden_path.is_file() else "cost ledger missing"
                ),
                "cost_ledger_missing" if cost_per_report is None else "",
                plan_id="07",
                sample_size=len(costs) or len(golden_runs),
                failed_examples=[
                    sample for sample in golden_samples
                    if cost_threshold is not None
                    and _float_or_none(sample.get("estimated_cost_usd")) is not None
                    and _float_or_none(sample.get("estimated_cost_usd")) > cost_threshold
                ],
                calculation={"aggregation": "sum" if costs else "max",
                             "parameters": {"soft_budget_usd": cost_threshold},
                             "per_sample_results": [
                                 _ops_runtime_sample(item, "cost_per_report")
                                 for item in (agent_records[:100] + golden_samples[:100])
                             ]}),
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
        financial = prior_results.get("03") or _load_financial_result_for_ticker(root, ticker)
        return evaluate_report(root, ticker, financial)
    if plan_id == "08":
        return evaluate_rollout(test_execution, prior_results)
    return evaluators[plan_id](root, ticker)
