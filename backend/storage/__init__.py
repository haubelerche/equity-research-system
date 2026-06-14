"""Supabase Storage adapter and canonical object-key contract."""

from backend.storage.layout import (
    ARCHIVE_BUCKET,
    EXPORTS_BUCKET,
    REQUIRED_BUCKETS,
    RUNS_BUCKET,
    SOURCES_BUCKET,
    approved_export_key,
    archive_key,
    client_report_key,
    run_artifact_key,
    run_chart_key,
    source_document_key,
)
from backend.storage.supabase_adapter import SupabaseStorageAdapter

__all__ = [
    "ARCHIVE_BUCKET",
    "EXPORTS_BUCKET",
    "REQUIRED_BUCKETS",
    "RUNS_BUCKET",
    "SOURCES_BUCKET",
    "SupabaseStorageAdapter",
    "approved_export_key",
    "archive_key",
    "client_report_key",
    "run_artifact_key",
    "run_chart_key",
    "source_document_key",
]
