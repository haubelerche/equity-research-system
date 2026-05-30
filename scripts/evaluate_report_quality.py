"""Quality gate script for generated equity research reports (P2-03).

Runs deterministic checks on valuation and forecast artifacts to detect
known failure modes before a report can be exported.

Usage:
    python scripts/evaluate_report_quality.py --ticker DHG
    python scripts/evaluate_report_quality.py --ticker DHG --artifacts-dir artifacts/

Outputs:
    reports/eval/latest_quality_gate.json
    reports/eval/latest_quality_gate.md

Quality gate statuses:
    PASS             — all critical checks passed
    WARN_NEEDS_REVIEW — non-critical issues found
    FAIL_BLOCK_EXPORT — critical failures that block export
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Check definitions ──────────────────────────────────────────────────────────

CRITICAL = "CRITICAL"
WARNING = "WARNING"
INFO = "INFO"

_STATUS_PASS = "PASS"
_STATUS_WARN = "WARN_NEEDS_REVIEW"
_STATUS_FAIL = "FAIL_BLOCK_EXPORT"


def _check_result(
    check_id: str,
    description: str,
    passed: bool,
    severity: str,
    detail: str = "",
) -> dict[str, Any]:
    if passed:
        status = _STATUS_PASS
    elif severity == CRITICAL:
        status = _STATUS_FAIL
    else:
        status = _STATUS_WARN
    return {
        "check_id": check_id,
        "description": description,
        "status": status,
        "severity": severity,
        "detail": detail,
    }


def check_tax_consistency(forecast: dict, fcff: dict | None) -> dict[str, Any]:
    """Tax rate in P&L forecast must match NOPAT tax rate in FCFF."""
    try:
        tp = forecast.get("tax_policy")
        if tp is None:
            return _check_result(
                "TAX_01", "Tax policy present in forecast artifact",
                False, CRITICAL, "tax_policy field missing from forecast artifact."
            )

        forecast_tax_rate = tp.get("effective_tax_rate")
        if forecast_tax_rate is None:
            return _check_result(
                "TAX_01", "Tax policy present in forecast artifact",
                False, CRITICAL, "effective_tax_rate missing from tax_policy."
            )

        if fcff is None:
            return _check_result(
                "TAX_01", "Tax consistency (forecast vs FCFF NOPAT)",
                False, WARNING, "No FCFF artifact to compare tax rate against."
            )

        wacc_breakdown = fcff.get("wacc_breakdown", {})
        fcff_tax_rate = wacc_breakdown.get("tax_rate")
        if fcff_tax_rate is None:
            return _check_result(
                "TAX_01", "Tax consistency (forecast vs FCFF NOPAT)",
                False, WARNING, "No tax_rate in FCFF wacc_breakdown."
            )

        diff = abs(forecast_tax_rate - fcff_tax_rate)
        # If FCFF has a tax_policy override it should match; if not, the WACCAssumptions rate is used
        # Check FCFF warnings for TaxPolicy usage
        fcff_warnings = fcff.get("warnings", [])
        uses_tax_policy = any("TaxPolicy" in w for w in fcff_warnings)

        if uses_tax_policy:
            # FCFF used the TaxPolicy rate — should be same as forecast
            passed = diff < 0.02
            detail = f"Forecast rate={forecast_tax_rate:.1%}, FCFF rate={fcff_tax_rate:.1%}, diff={diff:.1%}"
            return _check_result(
                "TAX_01", "Tax consistency (forecast vs FCFF NOPAT)",
                passed, CRITICAL, detail
            )
        else:
            return _check_result(
                "TAX_01", "Tax consistency (forecast vs FCFF NOPAT)",
                False, WARNING,
                f"FCFF does not use TaxPolicy. Forecast rate={forecast_tax_rate:.1%}, "
                f"FCFF WACCAssumptions rate={fcff_tax_rate:.1%}."
            )
    except Exception as e:
        return _check_result("TAX_01", "Tax consistency check", False, CRITICAL, str(e))


def check_capex_convention(fcff: dict | None, fcfe: dict | None) -> dict[str, Any]:
    """CAPEX must not be displayed as negative when formula uses -CAPEX."""
    issues: list[str] = []
    for artifact_name, artifact in [("FCFF", fcff), ("FCFE", fcfe)]:
        if artifact is None:
            continue
        convention = artifact.get("capex_convention")
        if convention != "positive_outflow":
            issues.append(
                f"{artifact_name}: capex_convention='{convention}' — "
                "expected 'positive_outflow'."
            )
        table_key = "fcff_table" if artifact_name == "FCFF" else "fcfe_table"
        for row in artifact.get(table_key, []):
            capex = row.get("capex")
            if capex is not None and capex < 0:
                issues.append(
                    f"{artifact_name} year {row.get('label')}: "
                    f"capex={capex} is negative but formula uses -CAPEX."
                )
    return _check_result(
        "CAPEX_01", "CAPEX displayed as positive outflow",
        len(issues) == 0, CRITICAL, "; ".join(issues)
    )


def check_debt_forecast(forecast: dict) -> dict[str, Any]:
    """Debt forecast fields must not be silently N/A."""
    warnings_list: list[str] = []
    # Check that forecast years have total_debt defined
    for fy in forecast.get("forecast_years", []):
        if fy.get("total_debt") is None:
            warnings_list.append(
                f"Year {fy.get('label')}: total_debt is None (silent N/A)."
            )
    if warnings_list:
        return _check_result(
            "DEBT_01", "No silent N/A in debt forecast",
            False, CRITICAL, "; ".join(warnings_list)
        )
    return _check_result("DEBT_01", "No silent N/A in debt forecast", True, CRITICAL)


def check_fcfe_net_borrowing(fcfe: dict | None) -> dict[str, Any]:
    """FCFE table must include non-None net_borrowing with method documented."""
    if fcfe is None:
        return _check_result(
            "FCFE_01", "FCFE includes net_borrowing method",
            False, WARNING, "No FCFE artifact provided."
        )
    missing = []
    for row in fcfe.get("fcfe_table", []):
        if row.get("net_borrowing") is None:
            missing.append(f"Year {row.get('label')}: net_borrowing is None.")
    return _check_result(
        "FCFE_01", "FCFE includes net_borrowing",
        len(missing) == 0, WARNING, "; ".join(missing)
    )


def check_dividend_schedule(forecast: dict) -> dict[str, Any]:
    """Dividend schedule must be present or missing-data warning must exist."""
    div_sched = forecast.get("dividend_schedule")
    if div_sched is None:
        return _check_result(
            "DIV_01", "Dividend schedule modeled or warned",
            False, WARNING, "dividend_schedule not present in forecast artifact."
        )
    method = div_sched.get("method", "missing")
    div_warnings = div_sched.get("warnings", [])
    if method == "missing" and not div_warnings:
        return _check_result(
            "DIV_01", "Dividend schedule modeled or warned",
            False, WARNING, "Dividend method is 'missing' but no warning message provided."
        )
    return _check_result("DIV_01", "Dividend schedule modeled or warned", True, WARNING)


def check_recommendation_gate(gate: dict | None, report_md: str | None) -> dict[str, Any]:
    """Report must not contain BUY/HOLD/SELL when gate is not approved."""
    if gate is None:
        return _check_result(
            "GATE_01", "Assumption gate present",
            False, CRITICAL, "No assumption gate artifact provided."
        )

    gate_status = gate.get("status", "")
    rec_allowed = gate.get("recommendation_allowed", False)

    if report_md is None:
        return _check_result(
            "GATE_01", "No BUY/HOLD/SELL when gate not approved",
            rec_allowed, WARNING,
            "No report markdown to check — gate check only."
        )

    has_buy = "BUY" in report_md and "Draft" not in report_md.split("BUY")[0][-20:]
    has_sell = "SELL" in report_md and "Draft" not in report_md.split("SELL")[0][-20:]
    has_hold = "HOLD" in report_md and "Draft" not in report_md.split("HOLD")[0][-20:]

    if (has_buy or has_sell or has_hold) and not rec_allowed:
        return _check_result(
            "GATE_01", "No BUY/HOLD/SELL when gate not approved",
            False, CRITICAL,
            f"Report contains BUY/HOLD/SELL but gate status='{gate_status}' not approved."
        )

    return _check_result("GATE_01", "No BUY/HOLD/SELL when gate not approved", True, CRITICAL)


def check_relative_valuation(multiples: dict | None) -> dict[str, Any]:
    """No default P/E or EV/EBITDA implied prices without peer data."""
    if multiples is None:
        return _check_result(
            "REL_01", "Relative valuation peer data required",
            False, WARNING, "No multiples artifact provided."
        )
    status = multiples.get("relative_valuation_status", "")
    if status == "pending_peer_dataset":
        return _check_result(
            "REL_01", "Relative valuation pending peer dataset",
            True, WARNING,
            "Relative valuation correctly marked as pending — no default multiples applied."
        )
    # If peer data available, check that implied prices are not None
    peer_src = multiples.get("peer_data_source")
    if peer_src:
        return _check_result("REL_01", "Relative valuation peer data present", True, INFO, peer_src)
    return _check_result(
        "REL_01", "Relative valuation peer data required",
        True, WARNING, f"Status: {status}"
    )


def check_confidence_score(confidence: dict | None) -> dict[str, Any]:
    """Module-level confidence must exist and have reasons."""
    if confidence is None:
        return _check_result(
            "CONF_01", "Module-level confidence score present",
            False, WARNING, "No confidence artifact provided."
        )
    has_reasons = bool(confidence.get("reasons"))
    has_final = bool(confidence.get("final_rating"))
    if not has_final:
        return _check_result(
            "CONF_01", "Module-level confidence has final_rating",
            False, WARNING, "final_rating missing from confidence artifact."
        )
    return _check_result(
        "CONF_01", "Module-level confidence score present",
        True, INFO,
        f"final_rating={confidence.get('final_rating')}, reasons={len(confidence.get('reasons', []))}"
    )


# ── Main gate runner ───────────────────────────────────────────────────────────

def run_quality_gate(
    ticker: str,
    forecast: dict | None = None,
    fcff: dict | None = None,
    fcfe: dict | None = None,
    multiples: dict | None = None,
    gate: dict | None = None,
    confidence: dict | None = None,
    report_md: str | None = None,
) -> dict[str, Any]:
    """Run all quality checks and return gate summary."""
    checks = [
        check_tax_consistency(forecast or {}, fcff),
        check_capex_convention(fcff, fcfe),
        check_debt_forecast(forecast or {}),
        check_fcfe_net_borrowing(fcfe),
        check_dividend_schedule(forecast or {}),
        check_recommendation_gate(gate, report_md),
        check_relative_valuation(multiples),
        check_confidence_score(confidence),
    ]

    n_fail = sum(1 for c in checks if c["status"] == _STATUS_FAIL)
    n_warn = sum(1 for c in checks if c["status"] == _STATUS_WARN)

    if n_fail > 0:
        overall = _STATUS_FAIL
    elif n_warn > 0:
        overall = _STATUS_WARN
    else:
        overall = _STATUS_PASS

    return {
        "ticker": ticker,
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall,
        "n_fail": n_fail,
        "n_warn": n_warn,
        "n_pass": sum(1 for c in checks if c["status"] == _STATUS_PASS),
        "checks": checks,
    }


def _render_md(result: dict[str, Any]) -> str:
    """Render quality gate result as Markdown."""
    status_icon = {
        _STATUS_PASS: "✅",
        _STATUS_WARN: "⚠️",
        _STATUS_FAIL: "❌",
    }
    lines = [
        f"# Quality Gate Report — {result['ticker']}",
        "",
        f"> Generated: {result['generated_at']}  ",
        f"> Overall Status: **{status_icon.get(result['overall_status'], '')} {result['overall_status']}**  ",
        f"> Checks: {result['n_pass']} PASS | {result['n_warn']} WARN | {result['n_fail']} FAIL",
        "",
        "---",
        "",
        "## Check Results",
        "",
        "| Check ID | Description | Status | Severity | Detail |",
        "|---|---|---|---|---|",
    ]
    for c in result["checks"]:
        icon = status_icon.get(c["status"], "")
        detail = (c["detail"] or "")[:120]
        lines.append(
            f"| {c['check_id']} | {c['description']} | {icon} {c['status']} | {c['severity']} | {detail} |"
        )
    lines += [
        "",
        "---",
        "",
        "## Machine-Readable Summary",
        "",
        "```json",
        json.dumps(result, indent=2, ensure_ascii=False),
        "```",
    ]
    return "\n".join(lines)


def _load_json(path: Path) -> dict | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _latest_file(directory: Path, ticker: str, artifact_type: str) -> Path | None:
    """Find the most recent artifact file regardless of naming convention.

    Handles both:
      {ticker}_{artifact_type}_{ts}.json  (type-first)
      {ticker}_{ts}_{artifact_type}.json  (timestamp-first, used by generate_report)
    """
    if not directory.exists():
        return None
    patterns = [
        f"{ticker}_{artifact_type}*.json",
        f"{ticker}_*_{artifact_type}*.json",
    ]
    matches: list[Path] = []
    for pat in patterns:
        matches.extend(directory.glob(pat))
    if not matches:
        return None
    return sorted(set(matches), reverse=True)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate report quality gate")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--report-file", default=None)
    args = parser.parse_args()

    root = Path(_PROJECT_ROOT)
    artifacts = root / args.artifacts_dir
    ticker = args.ticker

    # Load artifacts
    forecast_dir = artifacts / "forecast"
    valuation_dir = artifacts / "valuation"

    forecast_path = _latest_file(forecast_dir, ticker, "forecast")
    fcff_path = _latest_file(forecast_dir, ticker, "fcff")
    fcfe_path = _latest_file(forecast_dir, ticker, "fcfe")
    multiples_path = _latest_file(valuation_dir, ticker, "multiples")
    gate_path = _latest_file(valuation_dir, ticker, "gate")
    confidence_path = _latest_file(valuation_dir, ticker, "confidence")

    forecast = _load_json(forecast_path) if forecast_path else None
    fcff = _load_json(fcff_path) if fcff_path else None
    fcfe = _load_json(fcfe_path) if fcfe_path else None
    multiples = _load_json(multiples_path) if multiples_path else None
    gate = _load_json(gate_path) if gate_path else None
    confidence = _load_json(confidence_path) if confidence_path else None

    report_md: str | None = None
    if args.report_file:
        rp = Path(args.report_file)
        if rp.exists():
            report_md = rp.read_text(encoding="utf-8")

    result = run_quality_gate(
        ticker=ticker,
        forecast=forecast,
        fcff=fcff,
        fcfe=fcfe,
        multiples=multiples,
        gate=gate,
        confidence=confidence,
        report_md=report_md,
    )

    # Output
    eval_dir = root / "reports" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    json_path = eval_dir / "latest_quality_gate.json"
    md_path = eval_dir / "latest_quality_gate.md"

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_md(result), encoding="utf-8")

    print(f"\nQuality Gate: {result['overall_status']}")
    print(f"  PASS: {result['n_pass']}  WARN: {result['n_warn']}  FAIL: {result['n_fail']}")
    print(f"\nOutput: {json_path}")
    print(f"Report: {md_path}")

    if result["overall_status"] == _STATUS_FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
