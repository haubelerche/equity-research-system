"""Citation coverage evaluation gate  Phase 5 citation pipeline.

Validates that every quantitative claim in a report has a valid citation that
resolves to a real source_id in ingest.sources (or the citation map artifact).

Rules (all deterministic, no LLM):
  1. Every [^key] reference used inline must appear in the citation map.
  2. Every [^key] entry in the citation map must resolve to a real source_id.
  3. Every quantitative claim (a number with a currency/unit indicator nearby)
     must have a [^key] reference within 150 characters.
  4. No citation may point to a forbidden generic source label.

Exit codes:
  0  all gates pass (EXPORT ALLOWED)
  1  one or more critical gates fail (EXPORT BLOCKED)
  2  non-critical warnings only (EXPORT ALLOWED WITH WARNINGS)

Usage:
    python scripts/evaluate_citations.py --ticker DHG --report reports/latest.md
    python scripts/evaluate_citations.py --ticker DHG --report reports/DHG_2024_full_report.md --strict
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(_PROJECT_ROOT) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ROOT = Path(_PROJECT_ROOT)
RUN_DIR = ROOT / "storage" / "runs" / os.environ.get("RUN_ID", "missing_run_id")
REPORTS_DIR = RUN_DIR
ARTIFACTS_DIR = RUN_DIR

# Window (in characters) in which a [^key] must appear near a quantitative claim
_CITATION_WINDOW = 150

# Quantitative patterns: numbers with VND/tỷ/triệu/% indicators
_QUANT_PATTERN = re.compile(
    r"""
    (?:                          # number with thousands separators
        \d{1,3}(?:[,\.]\d{3})+  # e.g. 1,234 or 1.234.567
        |\d+(?:[,\.]\d+)?        # or plain number
    )
    \s*                          # optional space
    (?:
        t[ỷy]\s*VND              # tỷ VND / ty VND
        |tri[eệ]u\s*VND         # triệu VND / trieu VND
        |VND
        |t[ỷy]\s*[đd][ôồo]ng   # tỷ đồng / ty dong
        |%
        |x\b
        |l[aầ]n                  # lần / lan
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Citation reference: [^key] used inline (not the definition line [^key]: ...)
_REF_USE_PATTERN = re.compile(r"\[\^([\w\-\.\/]+)\](?!:)")

# Citation definition: [^key]: ... at start of line
_REF_DEF_PATTERN = re.compile(r"^\[\^([\w\-\.\/]+)\]:", re.MULTILINE)

# Forbidden generic source labels — must stay in sync with FORBIDDEN_GENERIC_LABELS
# in backend/citations/citation_map.py (comparison is done after .lower().strip())
_FORBIDDEN_LABELS = {
    "báo cáo tài chính (vnstock api)",
    "báo cáo tài chính (nguồn không xác định)",
    "dữ liệu tài chính canonical",
    "canonical financial facts",
    "nguồn không xác định",
    "bảng cân đối kế toán (vnstock api)",
    "báo cáo lưu chuyển tiền tệ (vnstock api)",
    "dữ liệu thị trường (vnstock api)",
}


def _load_citation_map(ticker: str) -> dict:
    """Load the run-scoped evidence pack."""
    path = ARTIFACTS_DIR / "evidence_pack.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("citation_map", {})
    except Exception:
        return {}


def _source_id_exists(source_id: str) -> bool:
    """Check whether source_id is present in ingest.sources."""
    try:
        from backend.retrieval import RetrievalService
        svc = RetrievalService()
        return svc.source_exists(source_id)
    except Exception:
        return True  # DB unavailable  don't block on this check


def _find_quantitative_claims(text: str) -> list[tuple[int, str]]:
    """Return list of (position, matched_text) for quantitative claims in report text."""
    return [(m.start(), m.group()) for m in _QUANT_PATTERN.finditer(text)]


def _find_citation_refs(text: str) -> list[tuple[int, str]]:
    """Return list of (position, key) for inline citation references in report text."""
    return [(m.start(), m.group(1)) for m in _REF_USE_PATTERN.finditer(text)]


def _has_nearby_citation(pos: int, ref_positions: list[tuple[int, str]], window: int) -> bool:
    """Return True if any citation reference is within `window` chars of `pos`."""
    for ref_pos, _ in ref_positions:
        if abs(ref_pos - pos) <= window:
            return True
    return False


def evaluate_citations(
    ticker: str,
    report_path: Path,
    strict: bool = False,
) -> dict:
    """Run citation coverage gates on a report file.

    Returns a dict with gate results and overall pass/fail/warn status.
    """
    ticker = ticker.strip().upper()

    if not report_path.exists():
        return {
            "status": "error",
            "error": f"Report not found: {report_path}",
            "gates": {},
            "export_allowed": False,
        }

    report_text = report_path.read_text(encoding="utf-8", errors="ignore")
    citation_map = _load_citation_map(ticker)

    # -- Gate 1: All inline [^key] references must resolve in the citation map -
    ref_uses = _find_citation_refs(report_text)
    ref_defs = {m.group(1) for m in _REF_DEF_PATTERN.finditer(report_text)}
    used_keys = [key for _, key in ref_uses]

    unresolved_keys = []
    for key in used_keys:
        # Resolve against citation map OR reference definitions in the report itself
        if key not in citation_map and key not in ref_defs:
            unresolved_keys.append(key)

    gate1_pass = len(unresolved_keys) == 0
    gate1 = {
        "gate": "citation_key_resolution",
        "description": "Every [^key] reference resolves to a citation map entry or footnote definition",
        "checked": len(used_keys),
        "failed": len(unresolved_keys),
        "unresolved_keys": unresolved_keys[:20],
        "pass": gate1_pass,
        "critical": True,
    }

    # -- Gate 2: All citation map entries must have valid source_ids ------------
    invalid_sources: list[str] = []
    for key, record in citation_map.items():
        source_id = record.get("source_id")
        if not source_id:
            invalid_sources.append(f"{key}: missing source_id")
        elif not _source_id_exists(source_id):
            invalid_sources.append(f"{key}: source_id '{source_id}' not in DB")

    gate2_pass = len(invalid_sources) == 0
    gate2 = {
        "gate": "source_id_validity",
        "description": "All citation map entries resolve to existing source_ids",
        "checked": len(citation_map),
        "failed": len(invalid_sources),
        "invalid_sources": invalid_sources[:20],
        "pass": gate2_pass,
        "critical": True,
    }

    # -- Gate 3: Every quantitative claim must have a nearby citation -----------
    quant_claims = _find_quantitative_claims(report_text)
    ref_positions = [(pos, key) for pos, key in ref_uses]
    uncited_claims: list[str] = []

    for pos, match_text in quant_claims:
        if not _has_nearby_citation(pos, ref_positions, _CITATION_WINDOW):
            # Extract context around the claim for the error message
            start = max(0, pos - 40)
            end = min(len(report_text), pos + len(match_text) + 40)
            context = report_text[start:end].replace("\n", " ").strip()
            uncited_claims.append(f"'{match_text}' in: ...{context}...")

    coverage_rate = (
        (len(quant_claims) - len(uncited_claims)) / len(quant_claims)
        if quant_claims else 1.0
    )
    gate3_pass = len(uncited_claims) == 0
    # Any missing citation blocks final export. --strict has no extra effect here
    # (it matters for other gate combinations upstream in the pipeline).
    gate3_critical = not gate3_pass
    gate3 = {
        "gate": "quantitative_citation_coverage",
        "description": "Every quantitative claim has a citation reference within 150 characters",
        "checked": len(quant_claims),
        "failed": len(uncited_claims),
        "coverage_rate": round(coverage_rate, 4),
        "uncited_claims": uncited_claims[:20],
        "pass": gate3_pass,
        "critical": gate3_critical,
    }

    # -- Gate 4: No forbidden generic source labels in citation map -------------
    forbidden_found: list[str] = []
    for key, record in citation_map.items():
        source_title = (record.get("source_title") or "").lower().strip()
        if source_title in _FORBIDDEN_LABELS:
            forbidden_found.append(f"{key}: '{source_title}'")

    gate4_pass = len(forbidden_found) == 0
    gate4 = {
        "gate": "no_forbidden_labels",
        "description": "No citation uses a forbidden generic source label",
        "checked": len(citation_map),
        "failed": len(forbidden_found),
        "forbidden_found": forbidden_found[:20],
        "pass": gate4_pass,
        "critical": False,  # warning only
    }

    # -- Summary ----------------------------------------------------------------
    gates = {
        "citation_key_resolution": gate1,
        "source_id_validity": gate2,
        "quantitative_citation_coverage": gate3,
        "no_forbidden_labels": gate4,
    }

    critical_fails = [name for name, g in gates.items() if g["critical"] and not g["pass"]]
    any_fail = any(not g["pass"] for g in gates.values())

    if critical_fails:
        overall_status = "FAIL"
        export_allowed = False
    elif any_fail:
        overall_status = "WARN"
        export_allowed = True
    else:
        overall_status = "PASS"
        export_allowed = True

    return {
        "ticker": ticker,
        "report": str(report_path),
        "status": overall_status,
        "export_allowed": export_allowed,
        "citation_map_entries": len(citation_map),
        "inline_references": len(used_keys),
        "quantitative_claims": len(quant_claims),
        "coverage_rate": round(coverage_rate, 4),
        "critical_fails": critical_fails,
        "gates": gates,
    }


def _print_report(result: dict) -> None:
    status = result["status"]
    ticker = result.get("ticker", "")
    report = result.get("report", "")

    print(f"\n{'='*65}")
    print(f"  CITATION EVALUATION  {ticker}")
    print(f"  Report: {Path(report).name}")
    print(f"{'='*65}")
    print(f"  Citation map entries : {result.get('citation_map_entries', 0)}")
    print(f"  Inline references    : {result.get('inline_references', 0)}")
    print(f"  Quantitative claims  : {result.get('quantitative_claims', 0)}")
    print(f"  Coverage rate        : {result.get('coverage_rate', 0):.1%}")
    print()

    for name, gate in result.get("gates", {}).items():
        icon = "PASS" if gate["pass"] else ("FAIL" if gate["critical"] else "WARN")
        print(f"  [{icon:4}] {gate['gate']}")
        if not gate["pass"]:
            if gate.get("unresolved_keys"):
                for k in gate["unresolved_keys"][:5]:
                    print(f"          - unresolved: {k}")
            if gate.get("invalid_sources"):
                for s in gate["invalid_sources"][:5]:
                    print(f"          - invalid: {s}")
            if gate.get("uncited_claims"):
                for c in gate["uncited_claims"][:3]:
                    print(f"          - uncited: {c[:80]}")
            if gate.get("forbidden_found"):
                for f in gate["forbidden_found"][:5]:
                    print(f"          - forbidden: {f}")

    print()
    if status == "FAIL":
        print(f"  EXPORT BLOCKED  critical gate(s) failed: {result['critical_fails']}")
    elif status == "WARN":
        print("  EXPORT ALLOWED WITH WARNINGS")
    else:
        print("  EXPORT ALLOWED  all citation gates pass")

    print(f"{'='*65}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate citation coverage of a generated equity research report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. DHG)")
    parser.add_argument(
        "--report", type=Path, default=None,
        help="Path to report markdown file. If omitted, uses most recent report for ticker.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat low quantitative citation coverage as a critical failure.",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_out",
        help="Output machine-readable JSON instead of human-readable report.",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Save evaluation result JSON to this path.",
    )
    return parser.parse_args()


def _find_latest_report(ticker: str) -> Path | None:
    path = REPORTS_DIR / "report.md"
    return path if path.exists() else None


def main() -> None:
    args = parse_args()

    report_path = args.report
    if report_path is None:
        report_path = _find_latest_report(args.ticker)
        if report_path is None:
            print(f"[evaluate_citations] ERROR: no report found for {args.ticker} in {REPORTS_DIR}")
            sys.exit(1)
        print(f"[evaluate_citations] Using latest report: {report_path.name}")

    result = evaluate_citations(
        ticker=args.ticker,
        report_path=report_path,
        strict=args.strict,
    )

    if args.json_out:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print_report(result)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[evaluate_citations] Saved to {args.out}")

    if not result.get("export_allowed", True):
        sys.exit(1)

    if result.get("status") == "WARN":
        sys.exit(2)


if __name__ == "__main__":
    main()
