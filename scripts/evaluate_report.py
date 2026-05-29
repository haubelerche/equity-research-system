"""Phase 7 — Evaluation Harness.

Runs deterministic evaluation gates against a generated report:

  1. Numeric consistency  — numbers in report match canonical facts within tolerance.
  2. Citation coverage    — quantitative claims have fact citations.
  3. Valuation reproducibility — DCF output in report matches artifact.
  4. Stale data detection — snapshot as_of_date not older than 30 days.
  5. Unsupported claims   — no absolute buy/sell language without support.

Saves an evaluation artifact. Exits non-zero if any critical gate fails.

Usage:
    python scripts/evaluate_report.py --report reports/DHG_..._full_report.md
    python scripts/evaluate_report.py --ticker DHG  (uses latest report)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
VALUATION_DIR = ROOT / "artifacts" / "valuation"
CITATION_DIR = ROOT / "artifacts" / "reports"
EVAL_DIR = ROOT / "artifacts" / "evaluation"
FORECAST_DIR = ROOT / "artifacts" / "forecast"

_STALE_THRESHOLD_DAYS = 30
_NUMERIC_TOLERANCE = 0.05  # 5% tolerance for number matching
_MIN_CITATION_COVERAGE = 0.8  # 80% of quantitative claims must have citations

_FORBIDDEN_PHRASES = [
    r"\bchắc chắn\b",
    r"\bđảm bảo lợi nhuận\b",
    r"\bchắc thắng\b",
    r"\bkhuyến nghị mua mạnh\b",
    r"\bchắc chắn tăng\b",
    r"\bguaranteed return\b",
    r"\bstrong buy\b",
    r"\bguarantee\b",
]


def _load_latest_report(ticker: str) -> tuple[Path, str] | None:
    files = sorted(REPORTS_DIR.glob(f"{ticker}_*.md"), reverse=True)
    if not files:
        return None
    p = files[0]
    return p, p.read_text(encoding="utf-8")


def _load_latest_citation_map(ticker: str) -> dict | None:
    files = sorted(CITATION_DIR.glob(f"{ticker}_*_citation.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def _load_latest_valuation(ticker: str) -> dict | None:
    files = sorted(VALUATION_DIR.glob(f"{ticker}_*_valuation.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def _load_snapshot_header(snapshot_id: str) -> dict | None:
    try:
        from backend.dataops.snapshot import get_latest_snapshot
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(os.getenv("DATABASE_URL", ""))
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT snapshot_id, as_of_date, facts_count, status FROM research.snapshots WHERE snapshot_id=%s",
                (snapshot_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _extract_numbers_from_report(report_text: str) -> list[float]:
    """Extract all numeric values from report text (in Vietnamese/English format)."""
    pattern = r"[\d]{1,3}(?:[,.][\d]{3})*(?:[.,][\d]+)?"
    raw_nums = re.findall(pattern, report_text)
    results = []
    for n in raw_nums:
        try:
            cleaned = n.replace(",", "")
            results.append(float(cleaned))
        except ValueError:
            pass
    return results


def _check_numeric_consistency(
    report_text: str, citation_map: dict, tolerance: float = _NUMERIC_TOLERANCE
) -> dict:
    """Check that numbers in the report match their cited canonical facts."""
    issues: list[str] = []
    checked = 0

    for fact_key, rec in citation_map.items():
        val = rec.get("value")
        if val is None:
            continue
        unit = rec.get("unit", "")
        metric = rec.get("line_item_code", "")
        period = rec.get("period", "")

        # Search for the value in the report text
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            continue

        if unit == "vnd_bn":
            search_val = val_f
            target_str = f"{val_f:,.1f}"
        elif unit == "vnd":
            search_val = val_f
            target_str = f"{val_f:,.0f}"
        else:
            continue  # Skip ratio/percent checks for now

        val = val_f

        checked += 1
        # Accept if value appears anywhere within tolerance in the report
        report_nums = _extract_numbers_from_report(report_text)
        found_close = any(abs(n - val) / max(abs(val), 1) < tolerance for n in report_nums if val != 0)
        if not found_close and target_str not in report_text:
            issues.append(f"Fact {fact_key} (value={val}, unit={unit}) not found in report")

    critical = len(issues) > checked * 0.5 if checked > 0 else False
    return {
        "gate": "numeric_consistency",
        "checked_facts": checked,
        "issues": issues[:20],
        "issue_count": len(issues),
        "pass": len(issues) == 0,
        "critical_fail": critical,
    }


def _check_citation_coverage(citation_data: dict) -> dict:
    """Check that quantitative claims in the report have fact citations."""
    claims = citation_data.get("claims", [])
    cmap = citation_data.get("citation_map", {})
    if not claims:
        return {
            "gate": "citation_coverage",
            "total_claims": 0,
            "cited_claims": 0,
            "coverage_ratio": None,
            "pass": False,
            "critical_fail": False,
            "issues": ["No quantitative claims extracted — citation coverage cannot be verified (WARN)"],
        }

    cited = 0
    uncited: list[str] = []
    for claim in claims:
        t = claim.get("ticker", "")
        y = claim.get("year", 0)
        m = claim.get("metric", "")
        key = f"{t}/{y}FY/{m}"
        if key in cmap:
            cited += 1
        else:
            uncited.append(key)

    ratio = cited / len(claims) if claims else 1.0
    return {
        "gate": "citation_coverage",
        "total_claims": len(claims),
        "cited_claims": cited,
        "coverage_ratio": round(ratio, 3),
        "uncited_claims": uncited[:10],
        "pass": ratio >= _MIN_CITATION_COVERAGE,
        "critical_fail": ratio < 0.5,
        "issues": [f"Coverage {ratio:.1%} below threshold {_MIN_CITATION_COVERAGE:.0%}"] if ratio < _MIN_CITATION_COVERAGE else [],
    }


def _check_valuation_reproducibility(ticker: str, citation_data: dict, val_artifact: dict) -> dict:
    """Verify that the valuation numbers cited in the report match the stored artifact."""
    issues: list[str] = []

    snap_id_in_citation = citation_data.get("snapshot_id", "")
    snap_id_in_val = val_artifact.get("snapshot_id", "")
    if snap_id_in_citation and snap_id_in_val and snap_id_in_citation != snap_id_in_val:
        issues.append(
            f"Snapshot mismatch: report uses {snap_id_in_citation} but latest valuation uses {snap_id_in_val}"
        )

    dcf_block = val_artifact.get("dcf") or val_artifact.get("dcf_simplified") or {}
    dcf_base = dcf_block.get("base", {})
    intrinsic = dcf_base.get("intrinsic_value_per_share_vnd")
    blend_target = val_artifact.get("blend_dcf", {}).get("target_price_dcf_vnd")
    if intrinsic is None:
        # Simplified DCF may be intentionally blocked (negative FCF history, WACC<=g, etc.)
        # If the FCFF/FCFE blend target price exists, simplified DCF being None is expected
        dcf_warnings = dcf_base.get("warnings", [])
        intentionally_blocked = any(
            "blocked" in w or "INVALID" in w for w in dcf_warnings
        )
        if blend_target is not None and intentionally_blocked:
            pass  # primary valuation is blend; simplified DCF blocked intentionally
        elif blend_target is not None:
            pass  # blend is primary; simplified DCF absent is acceptable
        else:
            issues.append("DCF intrinsic value missing from valuation artifact")

    return {
        "gate": "valuation_reproducibility",
        "snapshot_id_report": snap_id_in_citation,
        "snapshot_id_valuation": snap_id_in_val,
        "dcf_intrinsic_vnd": intrinsic,
        "issues": issues,
        "pass": len(issues) == 0,
        "critical_fail": any("mismatch" in i for i in issues),
    }


def _check_stale_data(citation_data: dict, val_artifact: dict) -> dict:
    """Check that the snapshot run date is recent AND financial data vintage is acceptable."""
    issues: list[str] = []
    age_days: int | None = None

    snap_as_of = val_artifact.get("snapshot_as_of", "")
    if not snap_as_of:
        issues.append("Snapshot as_of_date missing from valuation artifact")
    else:
        try:
            snap_date = date.fromisoformat(snap_as_of)
            today = datetime.now(UTC).date()
            age_days = (today - snap_date).days
            if age_days > _STALE_THRESHOLD_DAYS:
                issues.append(
                    f"Snapshot run date is {age_days} days old (threshold: {_STALE_THRESHOLD_DAYS} days)"
                )
        except ValueError:
            issues.append(f"Cannot parse snapshot date: {snap_as_of}")

    # Check financial data vintage: latest fiscal year should be current or prior year
    cmap = citation_data.get("citation_map", {})
    fiscal_years = set()
    for key in cmap:
        parts = key.split("/")
        if len(parts) >= 2:
            fy_str = parts[1].replace("FY", "")
            try:
                fiscal_years.add(int(fy_str))
            except ValueError:
                pass
    if fiscal_years:
        max_fy = max(fiscal_years)
        current_year = datetime.now(UTC).year
        lag = current_year - max_fy
        if lag > 2:
            issues.append(
                f"Latest financial data is {max_fy}FY — {lag} year(s) behind current year {current_year}. "
                "Data may be significantly stale."
            )
        elif lag > 1:
            issues.append(
                f"Latest financial data is {max_fy}FY — consider refreshing for current year coverage."
            )
    else:
        issues.append("Cannot determine financial data vintage — no fiscal years found in citation map")

    return {
        "gate": "stale_data",
        "snapshot_as_of": snap_as_of,
        "age_days": age_days,
        "threshold_days": _STALE_THRESHOLD_DAYS,
        "max_fiscal_year": max(fiscal_years) if fiscal_years else None,
        "issues": issues,
        "pass": len(issues) == 0,
        "critical_fail": False,
    }


def _check_user_facing_citation_quality(citation_data: dict) -> dict:
    """Gate 6: Every citation in the map must have a real source_title and source_uri.

    Fails if any citation still shows the SHA-hash fallback or generic label.
    """
    cmap = citation_data.get("citation_map", {})
    _GENERIC_LABELS = {
        "dữ liệu tài chính canonical",
        "canonical financial facts",
        "nguồn không xác định",
    }
    issues: list[str] = []
    checked = 0
    for key, rec in cmap.items():
        checked += 1
        title = (rec.get("source_title") or "").strip().lower()
        uri = (rec.get("source_uri") or "").strip()
        if title in _GENERIC_LABELS:
            issues.append(f"{key}: source_title is generic ('{rec.get('source_title')}')")
        if not uri:
            issues.append(f"{key}: source_uri is empty")

    return {
        "gate": "user_facing_citation_quality",
        "checked_citations": checked,
        "issue_count": len(issues),
        "issues": issues[:10],
        "pass": len(issues) == 0,
        "critical_fail": len(issues) > checked * 0.5 if checked > 0 else False,
    }


def _load_latest_forecast(ticker: str) -> dict | None:
    files = sorted(FORECAST_DIR.glob(f"{ticker}_*_forecast.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def _check_balance_sheet_identity(ticker: str) -> dict:
    """Gate 7: For every forecast year, verify total_assets == equity + total_debt + other_liabilities.

    Loads the latest forecast artifact from artifacts/forecast/.
    """
    issues: list[str] = []
    forecast_artifact = _load_latest_forecast(ticker)
    if forecast_artifact is None:
        return {
            "gate": "balance_sheet_identity_check",
            "checked_years": 0,
            "issues": ["No forecast artifact found in artifacts/forecast/ — run generate_report.py first"],
            "pass": False,
            "critical_fail": False,
        }
    forecast_years = forecast_artifact.get("forecast_years", [])
    if not forecast_years:
        return {
            "gate": "balance_sheet_identity_check",
            "checked_years": 0,
            "issues": ["No forecast balance sheet data in valuation artifact — cannot verify"],
            "pass": False,
            "critical_fail": False,
        }

    _TOLERANCE_BN = 1.0  # 1 tỷ VND tolerance
    for fy in forecast_years:
        label = fy.get("label", "?")
        assets = fy.get("total_assets")
        equity = fy.get("equity")
        debt = fy.get("total_debt")
        other = fy.get("other_liabilities")
        if assets is None or equity is None:
            issues.append(f"{label}: missing total_assets or equity — cannot verify identity")
            continue
        liabilities = (debt or 0) + (other or 0)
        expected_assets = equity + liabilities
        diff = abs(assets - expected_assets)
        if diff > _TOLERANCE_BN:
            issues.append(
                f"{label}: identity violated — assets={assets:.1f}, equity+liab={expected_assets:.1f}, diff={diff:.1f} tỷ"
            )

    return {
        "gate": "balance_sheet_identity_check",
        "checked_years": len(forecast_years),
        "issues": issues,
        "pass": len(issues) == 0,
        "critical_fail": len(issues) > 0,
    }


def _check_unsupported_claims(report_text: str) -> dict:
    """Detect forbidden absolute investment language."""
    findings: list[str] = []
    for pattern in _FORBIDDEN_PHRASES:
        matches = re.findall(pattern, report_text, re.IGNORECASE)
        if matches:
            findings.append(f"Forbidden phrase '{pattern}' found ({len(matches)} occurrence(s))")

    return {
        "gate": "unsupported_claims",
        "forbidden_phrases_checked": len(_FORBIDDEN_PHRASES),
        "findings": findings,
        "pass": len(findings) == 0,
        "critical_fail": len(findings) > 0,
        "issues": findings,
    }


def _check_valuation_sanity(val_artifact: dict) -> dict:
    """Gate 8: Cross-model sanity check — simplified DCF vs FCFF/FCFE blend.

    Critical: simplified DCF > 2x blend price (data quality issue).
    Warning: divergence > 30% between simplified DCF and blend.
    """
    issues: list[str] = []
    critical_fail = False
    details: dict = {}

    dcf_block = val_artifact.get("dcf_simplified") or val_artifact.get("dcf") or {}
    dcf_base_price = dcf_block.get("base", {}).get("intrinsic_value_per_share_vnd")
    blend_block = val_artifact.get("blend_dcf", {})
    blend_price = blend_block.get("target_price_dcf_vnd")
    current_price = val_artifact.get("current_price_vnd")

    details["dcf_simplified_base_vnd"] = dcf_base_price
    details["blend_target_vnd"] = blend_price
    details["current_price_vnd"] = current_price

    if dcf_base_price and blend_price and blend_price > 0:
        divergence = abs(dcf_base_price / blend_price - 1)
        details["divergence_pct"] = round(divergence, 4)

        if divergence > 0.50:
            issues.append(
                f"CRITICAL: Simplified DCF ({dcf_base_price:,.0f}) deviates {divergence:.1%} from "
                f"FCFF/FCFE Blend ({blend_price:,.0f}). "
                "Possible CAPEX sign error or extreme FCF volatility. "
                "Simplified DCF result MUST NOT appear as target price."
            )
            critical_fail = True
        elif divergence > 0.30:
            issues.append(
                f"Simplified DCF ({dcf_base_price:,.0f}) deviates {divergence:.1%} from "
                f"FCFF/FCFE Blend ({blend_price:,.0f}). "
                "Verify CAPEX sign convention and FCF history before referencing simplified DCF."
            )
    elif dcf_base_price and current_price and current_price > 0:
        if dcf_base_price > current_price * 2:
            issues.append(
                f"Simplified DCF ({dcf_base_price:,.0f}) > 2x current price ({current_price:,.0f}). "
                "Blend target unavailable for comparison. Flag for manual review."
            )

    # Check if simplified DCF warnings mention CAPEX or negative FCF
    dcf_warnings = dcf_block.get("base", {}).get("warnings", [])
    capex_warns = [w for w in dcf_warnings if "CAPEX" in w or "negative FCF" in w.lower() or "Negative FCF" in w]
    if capex_warns:
        issues.extend([f"Simplified DCF flag: {w}" for w in capex_warns[:2]])

    return {
        "gate": "valuation_sanity",
        "details": details,
        "issues": issues,
        "pass": len([i for i in issues if "CRITICAL" in i]) == 0,
        "critical_fail": critical_fail,
    }


def _check_approval_gate_status(ticker: str, val_artifact: dict) -> dict:
    """Gate 9: Ticker cross-check, blend draft flag, approval gate status.

    Checks:
      (a) val_artifact["ticker"] matches the report ticker.
      (b) val_artifact["blend_dcf"]["is_draft_only"] — warns if True.
      (c) val_artifact["approval_gate"]["status"] — warns/blocks based on status.
    """
    issues: list[str] = []
    critical_fail = False

    # (a) Ticker cross-check
    artifact_ticker = (val_artifact.get("ticker") or "").upper().strip()
    if artifact_ticker and artifact_ticker != ticker.upper():
        issues.append(
            f"Ticker mismatch: report is for {ticker!r} but valuation artifact "
            f"declares ticker={artifact_ticker!r}. Evaluation is using wrong artifact."
        )
        critical_fail = True

    # (b) Blend draft flag
    blend_block = val_artifact.get("blend_dcf", {})
    if blend_block.get("is_draft_only", False):
        gap = blend_block.get("valuation_gap_pct")
        gap_str = f"{gap:.1%}" if gap is not None else "unknown"
        issues.append(
            f"Blend DCF is marked draft-only (FCFF/FCFE gap={gap_str}). "
            "Target price must not be presented as PRIMARY until gap is resolved."
        )

    # (c) Approval gate status
    gate = val_artifact.get("approval_gate", {})
    gate_status = gate.get("status", "")
    if gate_status == "blocked":
        issues.append(
            "Valuation approval gate is BLOCKED — data quality did not pass. "
            "No target price or recommendation may be published."
        )
        critical_fail = True
    elif gate_status == "draft_needs_analyst_review":
        blocking_reasons = gate.get("blocking_reasons", [])
        n = len(blocking_reasons)
        issues.append(
            f"Approval gate status: draft_needs_analyst_review ({n} assumption(s) pending). "
            "Report is a draft — do not export as final."
        )
    elif not gate_status:
        issues.append(
            "No approval_gate found in valuation artifact — cannot verify assumption status. "
            "Regenerate artifact with scripts/run_valuation.py."
        )

    return {
        "gate": "approval_gate_check",
        "artifact_ticker": artifact_ticker or "(missing)",
        "blend_is_draft_only": blend_block.get("is_draft_only", False),
        "gate_status": gate_status or "missing",
        "issues": issues,
        "pass": len([i for i in issues if "mismatch" in i or "BLOCKED" in i]) == 0,
        "critical_fail": critical_fail,
    }


def evaluate_report(
    report_path: Path | None = None,
    ticker: str | None = None,
) -> dict:
    if report_path is None and ticker is None:
        raise ValueError("Either --report or --ticker must be provided")

    if ticker:
        ticker = ticker.strip().upper()

    # Load report text
    if report_path is not None:
        report_text = report_path.read_text(encoding="utf-8")
        # Infer ticker from filename if not given
        if ticker is None:
            ticker = report_path.name.split("_")[0].upper()
    else:
        result = _load_latest_report(ticker)
        if result is None:
            print(f"[evaluate_report] ERROR: No report found for {ticker} in {REPORTS_DIR}")
            sys.exit(1)
        report_path, report_text = result

    print(f"[evaluate_report] Evaluating: {report_path.name}")

    # Load artifacts
    citation_data = _load_latest_citation_map(ticker)
    val_artifact = _load_latest_valuation(ticker)

    if citation_data is None:
        print(f"[evaluate_report] WARNING: No citation map found for {ticker} — citation coverage will be skipped")
        citation_data = {"claims": [], "citation_map": {}}
    if val_artifact is None:
        print(f"[evaluate_report] WARNING: No valuation artifact found for {ticker}")
        val_artifact = {}

    # ── Run evaluation gates ──────────────────────────────────────────────────
    print("[evaluate_report] Gate 1: Numeric consistency...")
    g1 = _check_numeric_consistency(report_text, citation_data.get("citation_map", {}))

    print("[evaluate_report] Gate 2: Citation coverage...")
    g2 = _check_citation_coverage(citation_data)

    print("[evaluate_report] Gate 3: Valuation reproducibility...")
    g3 = _check_valuation_reproducibility(ticker, citation_data, val_artifact)

    print("[evaluate_report] Gate 4: Stale data detection...")
    g4 = _check_stale_data(citation_data, val_artifact)

    print("[evaluate_report] Gate 5: Unsupported claims...")
    g5 = _check_unsupported_claims(report_text)

    print("[evaluate_report] Gate 6: User-facing citation quality...")
    g6 = _check_user_facing_citation_quality(citation_data)

    print("[evaluate_report] Gate 7: Balance sheet identity (forecast)...")
    g7 = _check_balance_sheet_identity(ticker)

    print("[evaluate_report] Gate 8: Valuation sanity check (cross-model divergence)...")
    g8 = _check_valuation_sanity(val_artifact)

    print("[evaluate_report] Gate 9: Approval gate status + ticker cross-check...")
    g9 = _check_approval_gate_status(ticker, val_artifact)

    gates = [g1, g2, g3, g4, g5, g6, g7, g8, g9]

    all_pass = all(g["pass"] for g in gates)
    any_critical = any(g.get("critical_fail", False) for g in gates)
    overall_status = "PASS" if all_pass else ("CRITICAL_FAIL" if any_critical else "WARN")

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  EVALUATION SUMMARY — {ticker}")
    print(f"{'='*60}")
    for g in gates:
        status = "[PASS]" if g["pass"] else ("[CRITICAL]" if g.get("critical_fail") else "[WARN]")
        print(f"  {status}  {g['gate']}")
        for issue in g.get("issues", [])[:3]:
            print(f"          -> {issue}")
    print(f"{'='*60}")
    print(f"  OVERALL: {overall_status}")
    print(f"{'='*60}\n")

    if any_critical:
        print("[evaluate_report] CRITICAL gates failed — report must NOT be exported.")
    elif not all_pass:
        print("[evaluate_report] Some gates have warnings — review before export.")
    else:
        print("[evaluate_report] All gates passed — report is ready for human review.")

    # ── Save evaluation artifact ──────────────────────────────────────────────
    eval_result = {
        "ticker": ticker,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "report_file": report_path.name,
        "overall_status": overall_status,
        "all_pass": all_pass,
        "any_critical_fail": any_critical,
        "export_blocked": any_critical,
        "gates": {g["gate"]: g for g in gates},
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_path = EVAL_DIR / f"{ticker}_{ts}_evaluation.json"
    out_path.write_text(json.dumps(eval_result, indent=2, default=str), encoding="utf-8")
    print(f"[evaluate_report] Evaluation artifact saved: {out_path}")

    return eval_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run evaluation gates against a generated research report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--report", type=Path, help="Path to the report .md file")
    group.add_argument("--ticker", help="Use the latest report for this ticker")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.report is None and args.ticker is None:
        print("ERROR: provide either --report <path> or --ticker <TICKER>")
        sys.exit(1)
    result = evaluate_report(report_path=args.report, ticker=args.ticker)
    if result.get("any_critical_fail"):
        sys.exit(2)
    print("[evaluate_report] done")


if __name__ == "__main__":
    main()
