# DEV-ONLY — production runs use run_research.py
"""Render a report to HTML and optionally PDF.

Usage:
    python scripts/render_report.py --ticker DHG
    python scripts/render_report.py --ticker DHG --pdf
    python scripts/render_report.py --ticker DHG --run-id RUN_20260601
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.reporting.report_data_loader import load_report_context, _COMPANIES
from backend.reporting.section_builder import build_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.pdf_renderer import CLIENT_FORBIDDEN_PDF_TERMS, PDFRenderer
from backend.reporting.client_report_view_model import (
    ClientReportDataMissing,
    ClientReportViewModel,
    assert_client_final_ready,
    build_client_report_view_model,
)
from backend.reporting.client_section_builder import build_client_report_sections
from backend.reporting.section_builder import ReportContext


def _context_from_view_model(vm: ClientReportViewModel) -> ReportContext:
    """Adapt a client view model to the existing HTML template contract."""
    return ReportContext(
        ticker=vm.ticker,
        company_name=vm.company_name,
        exchange=vm.exchange,
        report_date=vm.report_date,
        data_cutoff=vm.report_date,
        rating=vm.recommendation,
        current_price=vm.current_price.amount if vm.current_price else None,
        target_price=vm.target_price.amount if vm.target_price else None,
        upside_pct=(vm.upside_downside.value * 100.0) if vm.upside_downside else None,
        risk_level="Trung bình",
        data_confidence="Professional report view",
        status="ANALYST_REVIEW" if vm.mode == "analyst_draft" else "CLIENT_FINAL",
        market_cap_bn=float(vm.market_statistics.get("Vốn hóa") or 0.0),
        _current_price_missing=vm.current_price is None,
        _target_price_missing=vm.target_price is None,
        _upside_missing=vm.upside_downside is None,
        _has_valuation=vm.target_price is not None,
        _has_forecast_table=bool(vm.valuation_model_table.rows),
        _has_sensitivity=False,
    )


def _write_review_packet(exc: ClientReportDataMissing, ticker: str, run_id: str) -> Path:
    """Write an internal review packet for missing client-final requirements."""
    output_dir = Path("artifacts/review_packets")
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{run_id}_" if run_id else ""
    path = output_dir / f"{prefix}{ticker}_client_final_review_packet.html"
    missing = "".join(f"<li>{field}</li>" for field in exc.missing_fields)
    sections = "".join(f"<li>{section}</li>" for section in exc.affected_sections)
    path.write_text(
        "<html><body>"
        f"<h1>Client final export blocked: {ticker}</h1>"
        "<h2>Missing fields</h2>"
        f"<ul>{missing}</ul>"
        "<h2>Affected sections</h2>"
        f"<ul>{sections}</ul>"
        "</body></html>",
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render equity research report")
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument("--pdf", action="store_true", help="Also render to PDF")
    parser.add_argument("--run-id", default="", dest="run_id", help="Optional run identifier")
    parser.add_argument(
        "--mode",
        choices=("client_final", "analyst_draft", "internal_debug"),
        default="analyst_draft",
        help="Report rendering mode",
    )
    parser.add_argument("--strict", action="store_true", help="Fail instead of rendering if required client data is missing")
    parser.add_argument(
        "--allow-latest-artifacts",
        action="store_true",
        dest="allow_latest_artifacts",
        default=False,
        help="[DEBUG ONLY] Allow artifact resolution via glob when --run-id is not provided.",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    if ticker not in _COMPANIES:
        raise SystemExit(
            f"Unknown ticker '{ticker}'. Supported: {', '.join(_COMPANIES)}"
        )

    import sys as _sys
    PRODUCTION_MODES = {"client_final", "analyst_draft"}
    _allows_glob = args.mode == "internal_debug" or getattr(args, "allow_latest_artifacts", False)
    if args.mode in PRODUCTION_MODES and not args.run_id and not _allows_glob:
        print(
            f"\n[ERROR] --run-id is required for production rendering (mode={args.mode!r}).\n"
            "Rendering without run_id means artifacts are resolved by glob (non-deterministic).\n"
            "\nOptions:\n"
            "  1. Provide run_id:  --run-id run_dhg_20260601T...\n"
            "  2. Allow glob (debug only):  --allow-latest-artifacts\n"
            "  3. Use debug mode:  --mode internal_debug\n",
            file=_sys.stderr,
        )
        _sys.exit(2)

    if args.mode == "internal_debug":
        ctx = load_report_context(
            ticker,
            run_id=args.run_id or None,
            allow_latest_artifacts=_allows_glob,
        )
        current_display = "N/A" if ctx._current_price_missing else f"{ctx.current_price:,.0f}"
        target_display = "N/A" if ctx._target_price_missing else f"{ctx.target_price:,.0f}"
        upside_display = "N/A" if ctx._upside_missing else f"{ctx.upside_pct:+.1f}%"
        print(
            f"[ctx] {ticker}: current={current_display} target={target_display} "
            f"upside={upside_display} rating={ctx.rating}"
        )
        sections = build_report_sections(ctx)
        forbidden_terms = None
    else:
        vm = build_client_report_view_model(
            ticker,
            args.mode,
            run_id=args.run_id or None,
            allow_latest_artifacts=_allows_glob,
        )
        try:
            if args.mode == "client_final" or args.strict:
                assert_client_final_ready(vm)
        except ClientReportDataMissing as exc:
            packet = _write_review_packet(exc, ticker, args.run_id)
            print(f"[review] client-final export blocked; packet saved: {packet}")
            raise SystemExit(2)
        ctx = _context_from_view_model(vm)
        current_display = "—" if vm.current_price is None else f"{vm.current_price.amount:,.0f}"
        target_display = "—" if vm.target_price is None else f"{vm.target_price.amount:,.0f}"
        upside_display = "—" if vm.upside_downside is None else f"{vm.upside_downside.value * 100:+.1f}%"
        print(
            f"[ctx] {ticker}: mode={args.mode} current={current_display} "
            f"target={target_display} upside={upside_display} recommendation={vm.recommendation}"
        )
        sections = build_client_report_sections(vm)
        forbidden_terms = CLIENT_FORBIDDEN_PDF_TERMS

    html_path = HTMLRenderer().render(
        sections,
        ctx,
        output_dir="artifacts/reports_html",
        run_id=args.run_id,
    )
    print(f"[html] saved: {html_path}")

    if args.pdf:
        # html_path filename already contains run_id (added by HTMLRenderer),
        # so pass run_id="" to PDFRenderer to avoid double-prefixing.
        pdf_path = PDFRenderer().render(
            html_path,
            output_dir="artifacts/reports_pdf",
            run_id="",
            forbidden_terms=forbidden_terms,
        )
        print(f"[pdf]  path : {pdf_path}")


if __name__ == "__main__":
    main()
