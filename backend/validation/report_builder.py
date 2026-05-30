"""DATA_VALIDATION_REPORT artifact builder (Plan Phase 7).

Generates a Markdown validation report from the DQ gate output BEFORE valuation runs.
File naming: DATA_VALIDATION_REPORT_{ticker}_{snapshot_id}.md

Sections:
  1. Data Snapshot
  2. Source Coverage
  3. Critical Fact Validation
  4. Accounting Reconciliation
  5. Time-series Warnings
  6. Market Data Alignment
  7. Valuation Readiness Gate
  8. Machine-Readable Summary (JSON)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from typing import Any


def _safe(val: Any, fmt: str = "", default: str = "N/A") -> str:
    if val is None:
        return default
    if fmt:
        try:
            return format(val, fmt)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _status_badge(status: str) -> str:
    mapping = {
        "pass": "✅ PASS",
        "warn": "⚠️ WARN",
        "fail": "❌ FAIL",
        "PASS": "✅ PASS",
        "FAIL": "❌ FAIL",
        "WARN": "⚠️ WARN",
    }
    return mapping.get(status, status.upper())


def build_validation_report_md(
    ticker: str,
    snapshot_id: str,
    fy_validation_report: dict,
    readiness_gate: dict,
    reconciliation_report: Any | None = None,
    market_alignment_issues: list[dict] | None = None,
    source_coverage_by_period: dict[str, dict] | None = None,
    fact_validation_rows: list[dict] | None = None,
    created_at: datetime | None = None,
) -> str:
    """Render a full DATA_VALIDATION_REPORT as a Markdown string.

    Args:
        ticker: Ticker symbol.
        snapshot_id: Snapshot ID string.
        fy_validation_report: Output of build_fy_validation_report().
        readiness_gate: Output of valuation_readiness_gate().
        reconciliation_report: ReconciliationReport dataclass instance (optional).
        market_alignment_issues: List of serialized MarketAlignmentIssue dicts (optional).
        source_coverage_by_period: {period: {tier1: source_name, tier3: source_name}} (optional).
        fact_validation_rows: List of {metric, period, value, source, cross_check, status, confidence}.
        created_at: Report generation datetime (default: now).

    Returns:
        Full Markdown string for the report.
    """
    if created_at is None:
        created_at = datetime.now(UTC)

    periods = fy_validation_report.get("periods_available", [])
    valuation_allowed = readiness_gate.get("valuation_allowed", False)
    overall_status = readiness_gate.get("overall_status", "fail").upper()
    blocking_reasons = fy_validation_report.get("blocking_reasons", [])

    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    lines += [
        f"# Data Validation Report — {ticker}",
        "",
        f"> Generated: {created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"> Snapshot: `{snapshot_id}`  ",
        f"> Overall Status: **{_status_badge(overall_status)}**  ",
        f"> Valuation Allowed: **{'YES' if valuation_allowed else 'NO'}**",
        "",
        "---",
        "",
    ]

    # ── Section 1: Data Snapshot ─────────────────────────────────────────────
    lines += [
        "## 1. Data Snapshot",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Ticker | {ticker} |",
        f"| Snapshot ID | `{snapshot_id}` |",
        f"| Created At | {created_at.strftime('%Y-%m-%d %H:%M:%S UTC')} |",
        f"| Historical Periods | {', '.join(periods) if periods else 'None'} |",
        f"| Annual Reports Collected | {fy_validation_report.get('annual_reports_collected', 0)} |",
        f"| Periods Missing | {', '.join(fy_validation_report.get('periods_missing', [])) or 'None'} |",
        f"| Latest FY | {_safe(fy_validation_report.get('latest_fiscal_year'))} |",
        f"| Data Age (days) | {_safe(fy_validation_report.get('data_age_days'))} |",
        "",
        "---",
        "",
    ]

    # ── Section 2: Source Coverage ──────────────────────────────────────────
    lines += ["## 2. Source Coverage", ""]
    tier3_only = fy_validation_report.get("tier3_only_periods", [])
    missing_t1 = fy_validation_report.get("missing_tier1_periods", [])
    tier_status = fy_validation_report.get("source_tier_coverage_status", "unknown")

    lines += [
        f"**Source Tier Gate:** {_status_badge(tier_status)}",
        "",
        "| Period | Has Tier 1/2 Source | Tier-3 Only | Notes |",
        "|---|---|---|---|",
    ]
    for period in periods:
        has_t1 = period not in missing_t1
        is_t3_only = period in tier3_only
        note = "⚠️ Tier-3 only — no audited source" if is_t3_only else ""
        lines.append(
            f"| {period} | {'✅ Yes' if has_t1 else '❌ No'} | "
            f"{'Yes' if is_t3_only else 'No'} | {note} |"
        )

    if source_coverage_by_period:
        lines += ["", "**Detailed Sources:**", ""]
        lines += ["| Period | Tier 1 Source | Tier 2 Source | Tier 3 Source | Status |", "|---|---|---|---|---|"]
        for period in periods:
            cov = source_coverage_by_period.get(period, {})
            t1 = cov.get("tier1", "—")
            t2 = cov.get("tier2", "—")
            t3 = cov.get("tier3", "—")
            st = "❌ Missing T1/T2" if period in missing_t1 else "✅ OK"
            lines.append(f"| {period} | {t1} | {t2} | {t3} | {st} |")

    lines += ["", "---", ""]

    # ── Section 3: Critical Fact Validation ─────────────────────────────────
    lines += ["## 3. Critical Fact Validation", ""]
    if fact_validation_rows:
        lines += [
            "| Metric | Period | Value | Primary Source | Cross-check | Status | Confidence |",
            "|---|---:|---:|---|---|---|---:|",
        ]
        for row in fact_validation_rows:
            lines.append(
                f"| {row.get('metric','?')} | {row.get('period','?')} "
                f"| {_safe(row.get('value'), '.2f')} "
                f"| {row.get('source','?')} | {row.get('cross_check','—')} "
                f"| {_status_badge(row.get('status','?'))} "
                f"| {_safe(row.get('confidence'), '.3f')} |"
            )
    else:
        src_gate = fy_validation_report.get("source_validation_gate", "unknown")
        non_accepted = fy_validation_report.get("non_accepted_facts") or []
        lines.append(f"**Source Validation Gate:** {_status_badge(src_gate)}")
        if non_accepted:
            lines += [
                "",
                "| Metric Key | Period | Validation Status |",
                "|---|---|---|",
            ]
            for item in non_accepted:
                lines.append(f"| {item['key']} | {item['period']} | {item['status']} |")
        else:
            lines.append("")
            lines.append("All core fact keys have `validation_status = accepted`.")

    lines += ["", "---", ""]

    # ── Section 4: Accounting Reconciliation ────────────────────────────────
    lines += ["## 4. Accounting Reconciliation", ""]

    recon_gate = fy_validation_report.get("reconciliation_gate", "unknown")
    lines.append(f"**Reconciliation Gate:** {_status_badge(recon_gate)}")
    lines.append("")

    recon_failures = fy_validation_report.get("reconciliation_critical_failures", [])
    recon_warnings = fy_validation_report.get("reconciliation_warnings", [])

    all_recon = (
        [{"status": "fail", **f} for f in recon_failures]
        + [{"status": "warn", **w} for w in recon_warnings]
    )

    if all_recon:
        lines += [
            "| Check | Period | Status | Message |",
            "|---|---|---|---|",
        ]
        for item in all_recon:
            lines.append(
                f"| {item.get('name','?')} | {item.get('period','?')} "
                f"| {_status_badge(item.get('status','?'))} | {item.get('message','?')} |"
            )
    else:
        lines.append("All accounting reconciliation checks passed.")

    lines += ["", "---", ""]

    # ── Section 5: Time-series Warnings ─────────────────────────────────────
    lines += ["## 5. Time-series Warnings", ""]

    ts_checks: list[dict] = []
    if reconciliation_report is not None:
        ts_checks = [
            {
                "name": c.name,
                "period": c.period,
                "expected": c.expected,
                "actual": c.actual,
                "difference": c.difference,
                "status": c.status,
                "message": c.message,
            }
            for c in reconciliation_report.checks
            if c.name.startswith("TS_")
        ]

    if ts_checks:
        lines += [
            "| Metric Check | Period | Threshold | Status | Message |",
            "|---|---|---|---|---|",
        ]
        for item in ts_checks:
            lines.append(
                f"| {item['name']} | {item['period']} "
                f"| — | {_status_badge(item['status'])} | {item['message']} |"
            )
    else:
        lines.append("No time-series anomalies detected.")

    lines += ["", "---", ""]

    # ── Section 6: Market Data Alignment ────────────────────────────────────
    lines += ["## 6. Market Data Alignment", ""]

    if market_alignment_issues:
        lines += [
            "| Check | Period | Label Used | Correct Label | Severity | Message |",
            "|---|---|---|---|---|---|",
        ]
        for issue in market_alignment_issues:
            lines.append(
                f"| {issue.get('check_id','?')} | {issue.get('period','?')} "
                f"| {issue.get('label_used','?')} | {issue.get('correct_label','?')} "
                f"| {issue.get('severity','?')} | {issue.get('message','?')} |"
            )
    else:
        lines.append("No market data alignment issues detected.")

    lines += ["", "---", ""]

    # ── Section 7: Valuation Readiness Gate ─────────────────────────────────
    lines += [
        "## 7. Valuation Readiness Gate",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Overall Status | **{_status_badge(overall_status)}** |",
        f"| Valuation Allowed | **{'✅ YES' if valuation_allowed else '❌ NO'}** |",
        f"| Blocked by DQ Gate | {_safe(readiness_gate.get('blocked_by_dq'))} |",
        f"| Blocked by Reconciliation | {_safe(readiness_gate.get('blocked_by_reconciliation'))} |",
        f"| Analyst Review Required | {'Yes' if not valuation_allowed else 'Recommended'} |",
        "",
    ]

    if blocking_reasons:
        lines += ["**Blocking Reasons:**", ""]
        for reason in blocking_reasons:
            lines.append(f"- `{reason}`")
        lines.append("")

    recon_block_failures = readiness_gate.get("reconciliation_critical_failures", [])
    if recon_block_failures:
        lines += ["**Reconciliation Failures:**", ""]
        for item in recon_block_failures:
            lines.append(f"- `{item.get('name','')}` @ {item.get('period','')}: {item.get('message','')}")
        lines.append("")

    lines += ["---", ""]

    # ── Section 8: Machine-Readable Summary ──────────────────────────────────
    critical_failures_list = [
        {"check_id": r, "severity": "CRITICAL", "message": r}
        for r in blocking_reasons
    ]

    high_warnings_list = [
        {"check_id": w.get("name", "?"), "message": w.get("message", "")}
        for w in (recon_warnings if recon_warnings else [])
    ]
    if market_alignment_issues:
        for issue in market_alignment_issues:
            if issue.get("severity") in ("HIGH", "CRITICAL"):
                high_warnings_list.append({
                    "check_id": issue.get("check_id", "?"),
                    "message": issue.get("message", ""),
                })

    machine_summary = {
        "ticker": ticker,
        "snapshot_id": snapshot_id,
        "validation_status": "DATA_VALIDATION_FAILED" if not valuation_allowed else "VALUATION_READY",
        "valuation_allowed": valuation_allowed,
        "allowed_output": "validation_report_only" if not valuation_allowed else "full_pipeline",
        "coverage_gate": fy_validation_report.get("coverage_gate"),
        "core_keys_gate": fy_validation_report.get("core_keys_gate"),
        "source_validation_gate": fy_validation_report.get("source_validation_gate"),
        "source_tier_coverage_status": fy_validation_report.get("source_tier_coverage_status"),
        "reconciliation_gate": fy_validation_report.get("reconciliation_gate"),
        "valuation_gate": fy_validation_report.get("valuation_gate"),
        "critical_failures": critical_failures_list,
        "high_warnings": high_warnings_list,
    }

    lines += [
        "## 8. Machine-Readable Summary",
        "",
        "```json",
        json.dumps(machine_summary, indent=2, ensure_ascii=False),
        "```",
        "",
    ]

    return "\n".join(lines)


def save_validation_report(
    report_md: str,
    ticker: str,
    snapshot_id: str,
    output_dir: str = "reports",
) -> str:
    """Write the validation report to disk and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    fname = f"DATA_VALIDATION_REPORT_{ticker}_{snapshot_id}.md"
    path = os.path.join(output_dir, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_md)
    return path
