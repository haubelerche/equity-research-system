"""Tests for using vnstock (DB production facts) as the OCR reconciliation source.

OCR pairing from flat text is noisy, so OCR facts are reconciled against a
trusted secondary source before promotion. CafeF was often empty, leaving no
source; vnstock production facts fill that role.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def test_db_facts_to_secondary_source_keys_and_values():
    from scripts.auto_ingest_official_documents import db_facts_to_secondary_source

    rows = [
        {"metric": "revenue.net", "period": "2025FY", "value": 5266.96},
        {"metric": "current_assets.ending", "period": "2025FY", "value": 3888.77},
    ]
    sec = db_facts_to_secondary_source(rows, "DHG", 2025)

    assert sec[("DHG", 2025, "FY", "revenue.net")] == 5266.96
    assert sec[("DHG", 2025, "FY", "current_assets.ending")] == 3888.77


def _candidate(metric: str, recon: str, confidence: float = 0.70):
    from backend.documents.ocr_candidate_facts import create_candidate_fact

    fact = create_candidate_fact(
        ocr_run_id="r", document_id="d", ticker="DHG", fiscal_year=2025,
        page_number=1, statement_type="balance_sheet", raw_label=metric,
        normalized_label=metric, metric_id=metric, raw_value="0",
        normalized_value=0.0, unit="vnd_bn", confidence=confidence,
    )
    fact.validation_status = "passed"
    fact.reconciliation_status = recon
    return fact


def test_matched_facts_get_confidence_raised_above_gate():
    from scripts.auto_ingest_official_documents import boost_confidence_for_matched

    matched = _candidate("current_assets.ending", "matched", 0.70)
    boost_confidence_for_matched([matched])
    assert matched.confidence >= 0.80


def test_unmatched_facts_keep_low_confidence():
    from scripts.auto_ingest_official_documents import boost_confidence_for_matched

    conflicted = _candidate("revenue.net", "conflicted", 0.70)
    missing = _candidate("admin_expense.total", "missing_secondary_source", 0.70)
    boost_confidence_for_matched([conflicted, missing])
    assert conflicted.confidence == 0.70
    assert missing.confidence == 0.70


def test_db_facts_to_secondary_source_filters_other_years_and_nulls():
    from scripts.auto_ingest_official_documents import db_facts_to_secondary_source

    rows = [
        {"metric": "revenue.net", "period": "2024FY", "value": 5000.0},  # wrong year
        {"metric": "gross_profit.total", "period": "2025FY", "value": None},  # null
        {"metric": "equity.parent", "period": "2025Q1", "value": 100.0},  # not FY
        {"metric": "revenue.net", "period": "2025FY", "value": 5266.96},
    ]
    sec = db_facts_to_secondary_source(rows, "DHG", 2025)

    assert sec == {("DHG", 2025, "FY", "revenue.net"): 5266.96}
