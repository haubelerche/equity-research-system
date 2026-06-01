"""Render a report to HTML and optionally PDF.

Usage:
    python scripts/render_report.py --ticker DHG
    python scripts/render_report.py --ticker DHG --pdf
    python scripts/render_report.py --ticker DHG --run-id RUN_20260601
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from backend.reporting.section_builder import ReportContext, build_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.pdf_renderer import PDFRenderer

_COMPANIES = {
    "DHG": ("Công ty CP Dược Hậu Giang", "HOSE"),
    "IMP": ("Công ty CP Dược phẩm Imexpharm", "HOSE"),
    "DMC": ("Công ty CP XNK Y tế Domesco", "HOSE"),
    "TRA": ("Công ty CP Traphaco", "HOSE"),
    "DBD": ("Công ty CP Dược Bình Định", "HNX"),
}


def _load_chart_paths(ticker: str) -> dict[str, str]:
    """Return a dict of chart key → file path for charts that exist."""
    charts_dir = Path("artifacts/charts")
    result: dict[str, str] = {}
    for n in range(1, 8):
        key = f"C{n}"
        candidate = charts_dir / f"{ticker}_{key}.png"
        if candidate.exists():
            result[key] = str(candidate)
    return result


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

    company_name, exchange = _COMPANIES[ticker]
    report_date = datetime.now().strftime("%Y-%m-%d")

    ctx = ReportContext(
        ticker=ticker,
        company_name=company_name,
        exchange=exchange,
        report_date=report_date,
        data_cutoff="2025-12-31",
        rating="UNDER_REVIEW",
        current_price=0,
        target_price=0,
        upside_pct=0,
        risk_level="—",
        data_confidence="Medium",
        status="DRAFT",
        chart_paths=_load_chart_paths(ticker),
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
