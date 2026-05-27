"""Persist data quality gate results to research.data_quality_reports.

Called by build_facts.py after build_fy_validation_report() runs, so every
fact-build has an auditable DQ record in the DB.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any

import psycopg2


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


@contextmanager
def _conn():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def persist_dq_report(
    ticker: str,
    report: dict[str, Any],
    from_year: int,
    to_year: int,
) -> int:
    """Insert a DQ gate summary from build_facts into research.data_quality_reports.

    Returns the new row id (or -1 on failure).
    """
    _KNOWN = {
        "ticker", "generated_at", "coverage_gate", "core_keys_gate",
        "source_validation_gate", "valuation_gate", "valuation_ready",
        "run_status", "blocking_reasons", "periods_available",
        "periods_missing", "annual_reports_collected",
    }
    details = {k: v for k, v in report.items() if k not in _KNOWN}

    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research.data_quality_reports (
                        ticker, run_type, from_year, to_year,
                        annual_reports_collected,
                        coverage_gate, core_keys_gate,
                        source_validation_gate, valuation_gate,
                        valuation_ready, run_status,
                        blocking_reasons_json,
                        periods_available_json,
                        periods_missing_json,
                        details_json
                    ) VALUES (
                        %s, 'build_facts', %s, %s,
                        %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb
                    )
                    RETURNING id
                    """,
                    (
                        ticker, from_year, to_year,
                        report.get("annual_reports_collected", 0),
                        report.get("coverage_gate", "fail"),
                        report.get("core_keys_gate", "fail"),
                        report.get("source_validation_gate", "fail"),
                        report.get("valuation_gate", "fail"),
                        report.get("valuation_ready", False),
                        report.get("run_status", "unknown"),
                        json.dumps(report.get("blocking_reasons") or []),
                        json.dumps(report.get("periods_available") or []),
                        json.dumps(report.get("periods_missing") or []),
                        json.dumps(details, default=str),
                    ),
                )
                row = cur.fetchone()
                return row[0] if row else -1
    except Exception as exc:  # noqa: BLE001
        print(f"[quality_report] WARNING: failed to persist DQ report for {ticker}: {exc}")
        return -1
