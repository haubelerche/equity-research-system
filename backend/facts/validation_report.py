"""Generate a Data Validation Report in markdown format (Plan §19).

This module produces a human-readable gate document that aggregates all validation
results (coverage, core keys, source validation, reconciliation) into a single
markdown file for analyst review before valuation runs.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from backend.facts.normalizer import FactTable


def generate_data_validation_report(
    ticker: str,
    snapshot_id: str,
    fact_table: FactTable,
    fy_report: dict,
    reconciliation_report,   # ReconciliationReport from reconciliation.py
    created_at: str | None = None,
) -> str:
    """Generate a Data Validation Report in markdown format (Plan §19).

    Args:
        ticker: Stock ticker (e.g., "DHG")
        snapshot_id: Unique identifier for this validation snapshot
        fact_table: FactTable dict (taxonomy_key → period → value)
        fy_report: dict from build_fy_validation_report() with keys:
            - periods_available: list of periods that were collected
            - periods_missing: list of periods that were not collected
            - annual_reports_collected: int count
            - coverage_gate, core_keys_gate, source_validation_gate, reconciliation_gate: "pass"/"fail"/"warn"
            - valuation_ready: bool
            - blocking_reasons: list[str]
        reconciliation_report: ReconciliationReport from run_reconciliation()
            with attributes: checks, critical_failures, warnings, overall_status, valuation_blocked
        created_at: ISO format timestamp; defaults to now if None

    Returns:
        Full markdown string. Caller is responsible for writing to disk.
    """
    if created_at is None:
        created_at = datetime.now(UTC).isoformat() + "Z"

    # --- Section 1: Data Snapshot ---
    periods_available = fy_report.get("periods_available", [])
    periods_str = ", ".join(periods_available) if periods_available else "(none)"

    # Count total facts across all periods and metrics
    total_fact_count = sum(
        len(period_values)
        for period_values in fact_table.values()
    )

    # --- Section 2: Source Coverage ---
    coverage_rows = []
    for period in periods_available:
        # Mark ✓ for collected periods
        coverage_rows.append(f"| {period} | ✓ | pass |")

    periods_missing = fy_report.get("periods_missing", [])
    for period in periods_missing:
        # Mark ✗ for missing periods
        coverage_rows.append(f"| {period} | ✗ | fail |")

    coverage_table = "\n".join(coverage_rows) if coverage_rows else "| (no periods) | | |"

    coverage_gate_status = fy_report.get("coverage_gate", "unknown")
    coverage_gate_symbol = "✓" if coverage_gate_status == "pass" else "✗"

    # --- Section 3: Critical Fact Validation (Reconciliation) ---
    # Only include checks that have both expected and actual values
    reconciliation_rows = []
    if reconciliation_report and hasattr(reconciliation_report, "checks"):
        for check in reconciliation_report.checks:
            # Skip checks where expected/actual are both None
            if check.expected is None and check.actual is None:
                continue

            expected_str = f"{check.expected:.2f}" if check.expected is not None else "N/A"
            actual_str = f"{check.actual:.2f}" if check.actual is not None else "N/A"
            difference_str = f"{check.difference:.2f}" if check.difference is not None else "N/A"

            # Status symbols
            if check.status == "pass":
                status_symbol = "✓ PASS"
            elif check.status == "warn":
                status_symbol = "⚠ WARN"
            else:  # fail
                status_symbol = "✗ FAIL"

            reconciliation_rows.append(
                f"| {check.name} | {check.period} | {expected_str} | {actual_str} | {difference_str} | {status_symbol} |"
            )

    reconciliation_table = "\n".join(reconciliation_rows) if reconciliation_rows else "| (no checks) | | | | | |"

    reconciliation_status = reconciliation_report.overall_status if reconciliation_report else "unknown"

    # --- Section 4: Gate Summary ---
    def gate_symbol(status: str) -> str:
        if status == "pass":
            return "✓ pass"
        elif status == "warn":
            return "⚠ warn"
        else:
            return "✗ fail"

    coverage_gate_str = gate_symbol(fy_report.get("coverage_gate", "fail"))
    core_keys_gate_str = gate_symbol(fy_report.get("core_keys_gate", "fail"))
    source_validation_gate_str = gate_symbol(fy_report.get("source_validation_gate", "fail"))
    reconciliation_gate_str = gate_symbol(fy_report.get("reconciliation_gate", "fail"))

    valuation_ready = fy_report.get("valuation_ready", False)
    overall_valuation_gate = "✓ PASS" if valuation_ready else "✗ FAIL"

    # --- Section 5: Blocking Reasons ---
    blocking_reasons = fy_report.get("blocking_reasons", [])
    if blocking_reasons:
        blocking_reasons_str = "\n".join(f"- {reason}" for reason in blocking_reasons)
    else:
        blocking_reasons_str = "None — valuation may proceed"

    # --- Section 6: Valuation Readiness Decision ---
    # Block valuation if EITHER valuation_ready is False OR reconciliation_report.valuation_blocked is True
    should_block = (not valuation_ready) or (reconciliation_report is not None and reconciliation_report.valuation_blocked)
    if should_block:
        valuation_status = "VALUATION_BLOCKED"
        analyst_review = "Yes"
        readiness_message = "Fix blocking reasons above before valuation can run."
    else:
        valuation_status = "VALUATION_ALLOWED"
        analyst_review = "No"
        readiness_message = "All gates pass. Proceed to valuation."

    # --- Assemble markdown report ---
    report_md = f"""# Data Validation Report — {ticker}

## 1. Data Snapshot
- Ticker: {ticker}
- Snapshot ID: {snapshot_id}
- Created At: {created_at}
- Historical Periods: {periods_str}
- Number of Facts: {total_fact_count}
- Source: canonical fact table

## 2. Source Coverage
| Period | Annual Report Collected | Coverage Gate |
|---|---|---|
{coverage_table}

Overall coverage_gate: {coverage_gate_symbol} {coverage_gate_status}

## 3. Critical Fact Validation (Accounting Reconciliation)
| Check | Period | Expected | Actual | Difference | Status |
|---|---|---|---|---|---|
{reconciliation_table}

Overall reconciliation: {reconciliation_status}

## 4. Gate Summary
| Gate | Status |
|---|---|
| Coverage Gate | {coverage_gate_str} |
| Core Keys Gate | {core_keys_gate_str} |
| Source Validation Gate | {source_validation_gate_str} |
| Reconciliation Gate | {reconciliation_gate_str} |
| **Overall Valuation Gate** | {overall_valuation_gate} |

## 5. Blocking Reasons
{blocking_reasons_str}

## 6. Valuation Readiness Decision
**Status: {valuation_status}**

Analyst Review Required: {analyst_review}

{readiness_message}
"""
    return report_md


def write_data_validation_report(
    report_md: str,
    output_dir: str,
    ticker: str,
    snapshot_id: str,
) -> str:
    """Write the report markdown to disk.

    Args:
        report_md: Markdown string from generate_data_validation_report()
        output_dir: Directory to write the report to
        ticker: Stock ticker
        snapshot_id: Snapshot ID

    Returns:
        The absolute file path written.
    """
    filename = f"DATA_VALIDATION_REPORT_{ticker}_{snapshot_id}.md"
    path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_md)
    return path
