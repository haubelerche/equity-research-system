"""Render a report to HTML and optionally PDF.

Usage:
    python scripts/render_report.py --ticker DHG
    python scripts/render_report.py --ticker DHG --pdf
    python scripts/render_report.py --ticker DHG --run-id RUN_20260601
"""
from __future__ import annotations

import argparse

from backend.reporting.report_data_loader import load_report_context, _COMPANIES
from backend.reporting.section_builder import build_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.pdf_renderer import PDFRenderer


def main() -> None:
    parser = argparse.ArgumentParser(description="Render equity research report")
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument("--pdf", action="store_true", help="Also render to PDF")
    parser.add_argument("--run-id", default="", dest="run_id", help="Optional run identifier")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    if ticker not in _COMPANIES:
        raise SystemExit(
            f"Unknown ticker '{ticker}'. Supported: {', '.join(_COMPANIES)}"
        )

    # Load a fully-populated context from valuation artifacts
    ctx = load_report_context(ticker)
    print(
        f"[ctx] {ticker}: current={ctx.current_price:,.0f} target={ctx.target_price:,.0f} "
        f"upside={ctx.upside_pct:+.1f}% rating={ctx.rating}"
    )

    sections = build_report_sections(ctx)

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
        )
        print(f"[pdf]  path : {pdf_path}")


if __name__ == "__main__":
    main()
