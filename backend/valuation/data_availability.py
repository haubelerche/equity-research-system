"""Pre-valuation data availability matrix + gap report.

Compares VALUATION_DATA_REQUIREMENTS against a real FactTable (plus the set of
assumptions and market-data inputs the caller can supply) and reports, per
method, exactly which inputs are present and which are missing — BEFORE any
method runs. No fabrication: a field is 'available' only if a real FactEntry
exists for the latest period.
"""
from __future__ import annotations

from typing import Any

from backend.facts.metric_metadata import is_known_metric
from backend.facts.normalizer import FactTable
from backend.valuation.data_requirements import VALUATION_DATA_REQUIREMENTS


def _classify_missing_fact(canonical_field: str) -> str:
    """Best-effort, deterministic attribution for a missing fact.

    We can honestly distinguish only two cases without the raw-extraction log:
      - the canonical key is not even registered  → canonical_mapping_missing
      - the key is registered but no fact ingested → ingestion_or_source_absence
    Finer parser-vs-source attribution requires the connector's raw rows and is
    intentionally not guessed here.
    """
    if not is_known_metric(canonical_field):
        return "canonical_mapping_missing"
    return "ingestion_or_source_absence"


def _fact_detail(fact_table: FactTable, canonical_field: str, latest_period: str | None) -> dict[str, Any]:
    entry = None
    if latest_period is not None:
        entry = fact_table.get(canonical_field, {}).get(latest_period)
    if entry is not None:
        return {
            "canonical_field": canonical_field,
            "kind": "fact",
            "available": True,
            "latest_period": latest_period,
            "source_uri": entry.source_uri or None,
            "confidence": entry.confidence,
            "classification": "available",
        }
    return {
        "canonical_field": canonical_field,
        "kind": "fact",
        "available": False,
        "latest_period": None,
        "source_uri": None,
        "confidence": None,
        "classification": _classify_missing_fact(canonical_field),
    }


def _input_detail(name: str, present: bool, kind: str, missing_classification: str) -> dict[str, Any]:
    return {
        "canonical_field": name,
        "kind": kind,
        "available": present,
        "latest_period": None,
        "source_uri": None,
        "confidence": None,
        "classification": "available" if present else missing_classification,
    }


def build_data_availability_matrix(
    *,
    ticker: str,
    fact_table: FactTable,
    latest_period: str | None,
    available_assumptions: set[str],
    available_market_data: set[str],
) -> dict[str, dict[str, Any]]:
    """Return {method: availability_dict} for every registered method.

    availability_dict keys: method, required_count, available_count,
    missing_fields, field_details, status ('ready' | 'blocked').
    """
    matrix: dict[str, dict[str, Any]] = {}
    for method, req in VALUATION_DATA_REQUIREMENTS.items():
        details: list[dict[str, Any]] = []
        missing: list[str] = []

        for f in req.required_facts:
            d = _fact_detail(fact_table, f, latest_period)
            details.append(d)
            if not d["available"]:
                missing.append(f)

        for a in req.required_assumptions:
            present = a in available_assumptions
            details.append(_input_detail(a, present, "assumption", "missing_assumption"))
            if not present:
                missing.append(a)

        for md in req.required_market_data:
            present = md in available_market_data
            details.append(_input_detail(md, present, "market_data", "missing_market_data"))
            if not present:
                missing.append(md)

        required_count = (
            len(req.required_facts) + len(req.required_assumptions) + len(req.required_market_data)
        )
        available_count = required_count - len(missing)
        matrix[method] = {
            "method": method,
            "ticker": ticker,
            "required_count": required_count,
            "available_count": available_count,
            "missing_fields": missing,
            "field_details": details,
            "status": "ready" if not missing else "blocked",
        }
    return matrix
