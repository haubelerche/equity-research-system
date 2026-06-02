"""Compatibility facade for report content manifest construction."""
from __future__ import annotations

from backend.reporting.client_report_view_model import (
    ChartArtifact,
    ClientReportDataMissing,
    ClientReportViewModel,
    Money,
    Percent,
    TableData,
    assert_client_final_ready,
    build_client_report_view_model,
)

__all__ = [
    "ChartArtifact",
    "ClientReportDataMissing",
    "ClientReportViewModel",
    "Money",
    "Percent",
    "TableData",
    "assert_client_final_ready",
    "build_client_report_view_model",
]
