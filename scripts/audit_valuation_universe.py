"""Build valuation audit artifacts for a ticker cohort or whole universe.

Read-only with respect to pipeline inputs: this script loads existing valuation
artifacts, classifies failures, and writes `valuation_audit_{ticker}_{run_id}.json`
plus a batch summary. It does not run ingestion, forecasting, valuation, or PDF
rendering.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.valuation.audit import build_valuation_audit  # noqa: E402


DEFAULT_UNIVERSE = ROOT / "config" / "dataset" / "universe" / "pharma_vn_universe.csv"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "valuation_audit"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tickers_from_universe(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            str(row.get("ticker") or "").strip().upper()
            for row in csv.DictReader(handle)
            if str(row.get("ticker") or "").strip()
        ]


def _parse_tickers(value: str | None, universe_path: Path) -> list[str]:
    if value:
        return sorted({item.strip().upper() for item in value.split(",") if item.strip()})
    return _tickers_from_universe(universe_path)


def _candidate_valuation_paths(root: Path, ticker: str) -> list[Path]:
    candidates: list[Path] = []
    storage_root = root / "storage" / "runs"
    if storage_root.exists():
        candidates.extend(
            path for path in storage_root.rglob("valuation.json")
            if ticker in {path.parent.name.upper(), str(path.parent.name).split("_")[1].upper() if "_" in path.parent.name else ""}
        )
    output_path = root / "output" / f"{ticker}_valuation_audit.json"
    if output_path.exists():
        candidates.append(output_path)
    legacy_output = root / "output" / f"{ticker}_valuation.json"
    if legacy_output.exists():
        candidates.append(legacy_output)
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def _valuation_paths_from_args(args: argparse.Namespace) -> list[Path]:
    if args.valuation_paths:
        return [Path(item).resolve() for item in args.valuation_paths.split(",") if item.strip()]
    tickers = _parse_tickers(args.tickers, Path(args.universe))
    paths: list[Path] = []
    for ticker in tickers:
        found = _candidate_valuation_paths(ROOT, ticker)
        if found:
            paths.append(found[0])
        else:
            paths.append(Path(f"missing:{ticker}"))
    return paths


def _safe_run_id(payload: dict[str, Any], path: Path) -> str:
    raw = payload.get("run_id") or payload.get("generated_at") or path.parent.name
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(raw))[:80]


def _write_audit(path: Path, output_dir: Path) -> dict[str, Any]:
    if str(path).startswith("missing:"):
        ticker = str(path).split(":", 1)[1]
        audit = build_valuation_audit(None, ticker=ticker, run_id="missing_artifact")
    else:
        valuation = _read_json(path)
        ticker = str(valuation.get("ticker") or path.parent.name).strip().upper()
        audit = build_valuation_audit(valuation, ticker=ticker, run_id=_safe_run_id(valuation, path))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"valuation_audit_{audit['ticker']}_{audit['run_id']}.json"
    out_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = dict(audit["summary"])
    summary.update({
        "ticker": audit["ticker"],
        "run_id": audit["run_id"],
        "audit_path": str(out_path),
        "recommendation": audit["recommendation_status"]["recommendation"],
        "report_status": audit["recommendation_status"]["report_status"],
        "data_quality_status": (audit.get("gate_results") or {}).get("DATA_QUALITY_GATE", {}).get("status"),
        "primary_method": audit["policy"].get("primary_method"),
        "wacc": ((audit["valuation_results"].get("fcff") or {}).get("wacc")),
        "terminal_growth": ((audit["valuation_results"].get("fcff") or {}).get("terminal_growth")),
        "fcff_price": ((audit["valuation_results"].get("fcff") or {}).get("target_price_vnd")),
        "fcfe_price": ((audit["valuation_results"].get("fcfe") or {}).get("target_price_vnd")),
        "pe_price": (
            (audit["valuation_results"].get("pe_forward") or {}).get("price_pe_forward_vnd")
            or (audit["valuation_results"].get("multiples") or {}).get("implied_price_pe")
        ),
        "draft_only": audit["recommendation_status"]["draft_only"],
        "critical_warning_count": audit["critical_warning_count"],
    })
    return summary


def _write_summary(rows: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / "valuation_audit_summary.json"
    csv_path = output_dir / "valuation_audit_summary.csv"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    fieldnames = [
        "ticker", "run_id", "market_price", "target_price", "upside_downside",
        "recommendation", "report_status", "data_quality_status", "primary_method",
        "method_count_passed", "wacc", "terminal_growth", "fcff_price",
        "fcfe_price", "pe_price", "critical_warning_count", "draft_only",
        "critical_error_codes", "audit_path",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return json_path, csv_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", help="Comma-separated ticker cohort. Defaults to universe CSV.")
    parser.add_argument("--valuation-paths", help="Comma-separated valuation JSON paths; overrides ticker discovery.")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE), help="Universe CSV with a ticker column.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for audit artifacts.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir)
    rows = [_write_audit(path, output_dir) for path in _valuation_paths_from_args(args)]
    json_path, csv_path = _write_summary(rows, output_dir)
    print(f"[valuation_audit] wrote {len(rows)} audit rows")
    print(f"[valuation_audit] summary_json={json_path}")
    print(f"[valuation_audit] summary_csv={csv_path}")
    blocked = sum(row.get("draft_only") is True for row in rows)
    print(f"[valuation_audit] draft_or_blocked={blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
