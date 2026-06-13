from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.storage.layout import (
    ARCHIVE_BUCKET,
    EXPORTS_BUCKET,
    REQUIRED_BUCKETS,
    RUNS_BUCKET,
    SOURCES_BUCKET,
    approved_export_key,
    archive_key,
    run_artifact_key,
    run_chart_key,
    source_document_key,
)
from backend.storage.supabase_adapter import SupabaseStorageAdapter

ROOT = Path(__file__).resolve().parents[2]


def test_exact_bucket_and_path_contract() -> None:
    assert REQUIRED_BUCKETS == ("sources", "runs", "exports", "archive")
    assert source_document_key("dhg", 2025, "doc1") == "official_documents/DHG/2025/doc1.pdf"
    assert run_artifact_key("run_1", "forecast.json") == "run_1/forecast.json"
    assert run_artifact_key("run_1", "facts_report.html") == "run_1/facts_report.html"
    assert run_artifact_key("run_1", "facts_report.pdf") == "run_1/facts_report.pdf"
    assert run_artifact_key("run_1", "review_packet.json") == "run_1/review_packet.json"
    assert run_chart_key("run_1", "revenue") == "run_1/charts/revenue.png"
    assert approved_export_key("dhg", "run_1", "report.pdf") == "approved_reports/DHG/run_1/report.pdf"
    assert archive_key("failed_runs", "run_1/error.json") == "failed_runs/run_1/error.json"


def test_signed_urls_are_exports_only() -> None:
    adapter = object.__new__(SupabaseStorageAdapter)
    adapter.url = "https://example.supabase.co"
    adapter.service_role_key = "service-role"
    with pytest.raises(ValueError):
        adapter.signed_url(RUNS_BUCKET, "run_1/report.pdf", 60)


def test_production_python_has_no_forbidden_local_storage_literals_or_glob_fallback() -> None:
    forbidden = (
        "backend/data/",
        "backend\\data\\",
        "artifacts/",
        "artifacts\\",
        "storage/runs",
        "storage\\runs",
        "storage/sources",
        "storage\\sources",
        "data/ocr_artifacts",
        "data\\ocr_artifacts",
    )
    violations: list[str] = []
    for path in (ROOT / "backend").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                normalized = node.value.lower()
                if any(token.lower() in normalized for token in forbidden):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.value!r}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"glob", "rglob"}
                and path.name != "migrate.py"
            ):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:filesystem glob fallback")
    assert not violations, "\n".join(violations)
