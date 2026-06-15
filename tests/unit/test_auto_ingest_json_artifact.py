"""Tests for machine-readable per-ticker JSON artifact emitted by auto_ingest.

The cohort coverage report (backend.dataops.ocr_coverage) consumes one JSON file
per ticker. These tests pin the serialization shape so the batch can aggregate it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def test_serialize_year_results_shape():
    from scripts.auto_ingest_official_documents import (
        IngestStatus,
        YearResult,
        serialize_year_results,
    )

    results = [
        YearResult(
            fiscal_year=2024,
            ingest_status=IngestStatus.OCR_PROMOTED,
            ocr_candidates=10,
            ocr_promoted=8,
            ocr_blocked=2,
            errors=["boom", "bang"],
        )
    ]

    rows = serialize_year_results(results)

    assert rows == [
        {
            "fiscal_year": 2024,
            "ingest_status": "OCR_PROMOTED",
            "ocr_candidates": 10,
            "ocr_promoted": 8,
            "ocr_blocked": 2,
            "errors": 2,
        }
    ]


def test_write_ticker_json_artifact_roundtrips(tmp_path):
    from scripts.auto_ingest_official_documents import (
        IngestStatus,
        YearResult,
        write_ticker_json_artifact,
    )

    results = [YearResult(fiscal_year=2023, ingest_status=IngestStatus.SOURCE_MISSING)]
    out = write_ticker_json_artifact("VHE", results, base_dir=tmp_path)

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ticker"] == "VHE"
    assert payload["years"][0]["ingest_status"] == "SOURCE_MISSING"
    assert payload["years"][0]["errors"] == 0
